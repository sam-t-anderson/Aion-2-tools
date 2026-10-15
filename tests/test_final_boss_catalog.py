"""A dungeon run auto-completes (and so can rank) when the party kills the dungeon's final
boss, with no manual ``final_boss_ids`` configuration — the final boss is read from a curated
catalog map. This is the fix for complete live runs never ranking because no final boss was
ever designated ("A configured final-boss completion was not observed").

The curated map is hand-checked, so this also guards its integrity: every mapped code is a
catalog boss whose dungeonId matches its key, and the deliberately-unmapped dungeons (the
300-boss Nightmare hub, the ambiguous Blazing Guardian Sword raids) stay unmapped."""
import json
import pathlib

from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.lookup import dungeon_final_bosses, npc_info
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

DATA = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "meter" / "a2parser" / "data" / "dungeon_final_bosses.json"

# Fire Temple (dungeon 600021): final boss Kromede's Desire (2310371); Silver Blade Rotan
# (2310310) is an earlier boss in the same dungeon that must NOT complete the run.
FIRE_TEMPLE, KROMEDE, SILVER_BLADE = 600021, 2310371, 2310310


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _session_in(dungeon_id):
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = dungeon_id
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me"}
    engine.roster = {"Me": {}}
    return s, engine


def test_lookup_returns_curated_codes_and_empty_for_unknown():
    assert dungeon_final_bosses(FIRE_TEMPLE) == frozenset({KROMEDE})
    assert dungeon_final_bosses(999999) == frozenset()     # unmapped dungeon
    assert dungeon_final_bosses(0) == frozenset()           # not a dungeon


def test_killing_the_catalog_final_boss_auto_completes_the_run():
    # No manual designation — the catalog alone must mark the run complete.
    s, engine = _session_in(FIRE_TEMPLE)
    assert s.final_boss_ids == set()
    engine.spawn_info = {9001: {"mobCode": KROMEDE}}
    engine.telemetry = [{"entity": 9001, "kind": "hp", "current": 500, "max": 1000, "timestamp_ms": 101000},
                        {"entity": 9001, "kind": "death", "timestamp_ms": 105000}]
    s.observe(engine, [_hit(5001, 9001, 100000), _hit(5001, 9001, 104000)], timestamp_ms=105000)
    run = s.runs[s.run]
    assert run.get("end_reason") == "configured_final_boss_death"
    assert run.get("recorded_final_boss") == KROMEDE
    assert run.get("complete") is True


def test_killing_an_earlier_boss_does_not_complete_the_run():
    # An earlier boss of the same dungeon is not the final boss, so the run stays open.
    s, engine = _session_in(FIRE_TEMPLE)
    engine.spawn_info = {9001: {"mobCode": SILVER_BLADE}}
    engine.telemetry = [{"entity": 9001, "kind": "hp", "current": 500, "max": 1000, "timestamp_ms": 101000},
                        {"entity": 9001, "kind": "death", "timestamp_ms": 105000}]
    s.observe(engine, [_hit(5001, 9001, 100000), _hit(5001, 9001, 104000)], timestamp_ms=105000)
    run = s.runs[s.run]
    assert run.get("end_reason") != "configured_final_boss_death"
    assert not run.get("complete")


def test_an_explicit_designation_still_wins():
    # A manual final_boss_ids (e.g. from an analysis request) overrides/augments the catalog:
    # the designated boss completes the run even if the catalog would not have.
    s, engine = _session_in(FIRE_TEMPLE)
    s.final_boss_ids = {SILVER_BLADE}
    engine.spawn_info = {9001: {"mobCode": SILVER_BLADE}}
    engine.telemetry = [{"entity": 9001, "kind": "hp", "current": 500, "max": 1000, "timestamp_ms": 101000},
                        {"entity": 9001, "kind": "death", "timestamp_ms": 105000}]
    s.observe(engine, [_hit(5001, 9001, 100000), _hit(5001, 9001, 104000)], timestamp_ms=105000)
    assert s.runs[s.run].get("end_reason") == "configured_final_boss_death"


def test_curated_map_integrity():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    fb = doc["final_bosses"]
    assert len(fb) >= 90                                    # the catalog has ~100 mappable dungeons
    # Deliberately unmapped (ambiguous / anomaly) dungeons stay out.
    for omitted in ("200003", "620021", "620022"):
        assert omitted not in fb, f"{omitted} should be unmapped"
    # Every mapped code is a catalog boss whose dungeonId matches its key (no stray/mis-keyed codes).
    for did, codes in fb.items():
        assert codes, f"{did} has no codes"
        for code in codes:
            info = npc_info(code)
            assert info.get("isBoss") is True, f"{code} in {did} is not a catalog boss"
            assert info.get("dungeonId") == int(did), f"{code} dungeonId {info.get('dungeonId')} != {did}"
