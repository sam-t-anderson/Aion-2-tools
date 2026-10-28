"""The name supplement: DBAion2's names for the NPC and dungeon ids the community catalog has no row
for (friendly NPCs a DPS meter's catalog leaves out, instances it cannot name), and the coverage
rules that stop counting an id the catalogs know as unresolved. Names only: no boss flag,
category, tier or difficulty comes from it."""
import json

import pytest

from aion2calc.combat import catalog
from aion2calc.combat.catalog import coverage, known_instance
from aion2calc.meter.a2parser import lookup
from aion2calc.meter.a2parser.lookup import npc_info, supplement_dungeon
from aion2calc.meter.context import SUPPLEMENT_ZONE, classify
from aion2calc.scrape import supplement

NPCS = [{"id": 2000925, "name": "Rafflesia", "npcType": "Monster"},          # in the community catalog
        {"id": 2951048, "name": "Trainee Merchant", "npcType": "Citizen"},
        {"id": 2999990, "name": " Gate Lever ", "npcType": "Etc"}]
DUNGEONS = [{"name": "Krao Cave", "type": "Party", "difficulties": [{"id": 600001, "difficulty": "Normal", "name": "Conquest"}]},
            {"name": "Deus Research Base", "type": "Party", "difficulties": [{"id": 610052, "difficulty": "Hard", "name": "Transcendence"}]},
            {"name": "Daeva Bio-Research Base", "type": "Daily", "difficulties": [{"id": 900001, "difficulty": "None", "name": "None"}]}]


def test_the_supplement_takes_only_what_the_community_catalog_lacks():
    rows = supplement.build(NPCS, DUNGEONS, {"2000925": {"name": "Rafflesia", "isBoss": False}}, {"600001": {"name": "Krao Cave"}})
    assert rows["npcs"] == {"2951048": {"name": "Trainee Merchant", "type": "Citizen"}, "2999990": {"name": "Gate Lever", "type": "Etc"}}
    assert rows["dungeons"] == {"610052": {"name": "Deus Research Base", "type": "Party", "difficulty_name": "Transcendence"},
                                "900001": {"name": "Daeva Bio-Research Base", "type": "Daily"}}


def test_a_changed_source_shape_stops_the_staging(tmp_path):
    with pytest.raises(ValueError):
        supplement.validate("npcs", [{"id": "2951048", "name": "Trainee Merchant"}])        # id not a number
    with pytest.raises(ValueError):
        supplement.validate("dungeons", [{"name": "Krao Cave", "difficulties": [{"name": "Conquest"}]}])
    tables = {supplement.SOURCES["npcs"]: json.dumps(NPCS).encode(), supplement.SOURCES["dungeons"]: json.dumps(DUNGEONS).encode()}
    staged = supplement.stage(tmp_path / "stage", log=lambda *_: None, fetch=tables.__getitem__)
    written = json.loads((tmp_path / "stage" / "catalog-supplement.json").read_text(encoding="utf-8"))
    assert written == staged and written["source"]["name"] == "DBAion2" and set(written["source"]["sha256"]) == {"npcs", "dungeons"}
    audit = json.loads((tmp_path / "stage" / "catalog-supplement-audit.json").read_text(encoding="utf-8"))
    assert audit["diffs"]["dungeons"]["counts"]["rows"] == 2
    with pytest.raises(ValueError):
        supplement.stage(tmp_path / "stage", log=lambda *_: None, fetch=tables.__getitem__)  # never overwrites


def test_a_friendly_npc_gets_its_name_and_type_but_no_catalog_role():
    info = npc_info(2951048)                                   # a merchant on an event map (bundled supplement)
    assert info["name"] == "Trainee Merchant" and info["supplement"] is True and info["npc_type"] == "Citizen"
    assert not any(info.get(k) for k in ("isBoss", "category", "tier", "dungeonId"))
    assert npc_info(2343616)["name"] == "Gelcos" and "supplement" not in npc_info(2343616)   # the community row wins
    assert supplement_dungeon(610052)["name"] == "Deus Research Base" and supplement_dungeon(600092) == {}


def _rows(segment):
    return {(r["kind"], r["code"]) for r in coverage(segment)["unmapped"]}


def test_ids_the_catalogs_know_are_not_unresolved():
    # a dungeon recorded as the map (no instance id sent), the Nightmare map its NPCs live in, a
    # Transcendence tier only the supplement names, and a friendly NPC
    entities = [{"id": "a", "kind": "enemy", "mob_code": 2951048}, {"id": "b", "kind": "enemy", "mob_code": 2999998}]
    assert _rows({"map_id": 600092, "instance_id": 0, "entities": entities}) == {("npc", 2999998)}
    assert _rows({"map_id": 200003, "instance_id": 0}) == set() and _rows({"map_id": 610052, "instance_id": 610052}) == set()
    assert known_instance(910034) and known_instance(900001) and not known_instance(320001)
    assert _rows({"map_id": 320001, "instance_id": 0}) == {("map", 320001)}     # a story map no source names
    assert _rows({"map_id": 1, "instance_id": 999_999_001}) == {("instance", 999_999_001)}
    assert coverage({"map_id": 610052, "instance_id": 610052})["catalog_zone"] == "Deus Research Base"


def test_the_supplement_names_zones_and_daily_dungeons_but_never_sets_a_difficulty():
    tier = classify(610052, 610052, False, [{"id": "e", "kind": "enemy", "mob_code": 2346616}])
    assert tier["zone"] == "Deus Research Base" and tier["zone_source"].endswith(SUPPLEMENT_ZONE)
    assert tier["encounter_type"] == "transcendence" and tier["difficulty_source"].endswith("exact NPC tier")
    daily = classify(900001, 0, False, [])
    assert daily["zone"] == "Daeva Bio-Research Base" and daily["encounter_type"] == "daily" and "difficulty" not in daily


def test_the_catalog_revision_follows_the_supplement(monkeypatch):
    before = catalog.revision()
    monkeypatch.setattr(lookup, "_supplement", lambda: {"npcs": {"1": {"name": "x"}}, "dungeons": {}})
    monkeypatch.setattr(catalog, "_supplement", lookup._supplement)
    catalog.revision.cache_clear()
    try:
        assert catalog.revision() != before                    # a refreshed supplement re-indexes coverage
    finally:
        catalog.revision.cache_clear()
    assert catalog.supplement_source()["npc_names"] > 3000 and catalog.supplement_source()["name"] == "DBAion2"
