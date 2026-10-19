"""What kind of PvP a fight was, from recorded ids (0.2.320).

Older clients split dungeon fights into "PvP" fragments when one hit was misread; 13 of the 39
logs the log server listed as PvP on 19 October held PvP only inside dungeons. Only the party is
inside a group instance, so a PvP flag there is typed by the instance instead. PvP in the open
world is named by its zone (the Abyss, Altgard, Verteron), and the log lists show the PvP type."""
import pathlib

from aion2calc.meter.context import classify, enrich, open_world_zone

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_pvp_inside_a_group_instance_is_typed_by_the_instance():
    r = classify(600092, 600092, True, [])                  # Ferocious Horn Den
    assert r["encounter_type"] == "expedition" and r["zone"] == "Ferocious Horn Den"
    assert r["classification"]["pvp_in_group_instance"] is True
    assert "PvP flag inside a group instance" in r["encounter_type_source"]


def test_a_group_instance_named_only_by_its_map_or_behind_a_stale_map_counts_too():
    assert classify(600065, 0, True, [])["encounter_type"] == "transcendence"     # map id is the instance
    assert classify(200003, 0, True, [])["encounter_type"] == "nightmare"
    stale = classify(1110, 600068, True, [])                 # Altgard's map id, a transcendence instance id
    assert stale["encounter_type"] == "transcendence" and stale["classification"]["stale_map"] is True


def test_open_world_pvp_is_named_by_its_zone():
    abyss = classify(20, 0, True, [])
    assert abyss["encounter_type"] == "pvp_open_world" and abyss["zone"] == "Abyss"
    assert classify(1110, 0, True, [])["zone"] == "Altgard"
    assert open_world_zone(1000) == "Verteron" and open_world_zone(62) is None


def test_arenas_stay_arenas_and_an_unknown_pvp_map_stays_unknown():
    assert classify(60, 0, True, [])["encounter_type"] == "pvp_arena"
    unknown = classify(62, 0, True, [])
    assert "encounter_type" not in unknown and "zone" not in unknown


def test_pve_classification_is_unchanged():
    assert classify(600092, 600092, False, [])["encounter_type"] == "expedition"
    assert "zone" not in classify(20, 0, False, [])          # open-world PvE keeps its boss names


def _doc(segment):
    return {"meta": {}, "players": [{"id": 1, "name": "A"}], "segments": [dict(segment, hits=[], events=[], entities=[])]}


def test_stored_logs_lose_their_dungeon_pvp_on_re_import():
    doc = enrich(_doc({"map_id": 600022, "instance_id": 600022, "encounter_type": "pvp_other"}))
    assert doc["segments"][0]["encounter_type"] == "expedition"
    # The meter typed it open-world PvP from a stale map id; that type is replaced too.
    doc = enrich(_doc({"map_id": 1110, "instance_id": 600068, "encounter_type": "pvp_open_world",
                       "encounter_type_source": "Recorded map ID + bundled open-world map table"}))
    assert doc["segments"][0]["encounter_type"] == "transcendence"


def test_stored_open_world_pvp_keeps_its_type_and_gains_its_zone():
    doc = enrich(_doc({"map_id": 20, "instance_id": 0, "encounter_type": "pvp_open_world",
                       "encounter_type_source": "Recorded map ID + bundled open-world map table"}))
    segment = doc["segments"][0]
    assert segment["encounter_type"] == "pvp_open_world" and segment["zone"] == "Abyss"


def test_the_log_lists_show_the_pvp_type_and_name_skirmishes_by_zone():
    for path in ("site/logs.js", "aion2calc/app/static/logs-view.js"):
        js = (ROOT / path).read_text(encoding="utf-8")
        assert 'mode === "pvp" ? "Type" : "Difficulty"' in js, path
        assert 'pvp_arena: "Arena", pvp_battleground: "Battlefield"' in js and '"Other PvP"' in js, path
        assert '(comm.f.combat_mode === "pvp" && c.zone) || c.boss' in js, path
        assert "type: c.encounter_type" in js, path
        # A count without the game's party list is marked: it counts only the players recorded.
        assert "partyKnown: !!c.party_size" in js and "PARTY_UNKNOWN" in js, path
