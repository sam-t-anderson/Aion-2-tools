"""A final boss recorded as a player (0.2.375). A party wiped on a final boss, revived in place and
killed it at the next pull; the meter finished the run on that boss's death, but the export typed the
boss by a two-letter name read for its entity after the revive, as a player: its fight had no boss and
no kill, and the run's last boss attempt was the wipe before it ("never defeated"). An NPC's spawn
record outranks a name read for the same entity, and the log server types such a boss again in
recordings already made from the run's own record of the final boss's death. Synthetic data only."""
from datetime import datetime, timedelta, timezone

from aion2calc.combat.rejoin import recorded_final_boss, rejoin
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.lookup import npc_name
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

VAKRON, THORN_VINES = 2320812, 2920367      # the catalog's final boss of Vakron Sky Island (600073), one of its adds
ME, BOSS, STRANGER = 4062, 42617, 5150


def _engine(names, spawns):
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600073
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = ME
    engine.names, engine.known_players, engine.roster = {ME: "Me", **names}, {ME}, {"Me": {}}
    engine.spawn_info = {entity: {"mobCode": code} for entity, code in spawns.items()}
    return engine


def _fight(engine, attacker=ME, skill=15210000):
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    for t in range(110_000, 230_001, 10_000):
        s.observe(engine, [DamageEvent(actor_id=attacker, target_id=BOSS, skill_code=skill, damage=500, timestamp_ms=t)],
                  timestamp_ms=t)
    engine.telemetry = [{"kind": "death", "entity": BOSS, "timestamp_ms": 231_000}]
    s.observe(engine, [], timestamp_ms=231_000)
    engine.telemetry = []
    return s


def test_a_final_boss_with_a_name_read_for_its_entity_is_exported_as_the_boss_and_its_kill():
    s = _fight(_engine({BOSS: "Qv"}, {BOSS: VAKRON}))
    assert s.runs[s.run]["end_reason"] == "configured_final_boss_death"
    segment = s.to_a2log("party")["segments"][0]
    boss = next(e for e in segment["entities"] if e["id"].endswith(f":{BOSS}"))
    assert boss["kind"] == "enemy" and boss["is_boss"] and not boss["is_player"]
    assert boss["mob_code"] == VAKRON and boss["name"] == npc_name(VAKRON) == "Vakron"
    assert segment["boss"] == "Vakron" and segment["killed"]


def test_an_entity_that_struck_with_a_players_class_skill_keeps_the_name_read_for_it():
    # A player is not made an NPC by a spawn record: a class skill of its own outranks the record.
    engine = _engine({STRANGER: "Qv"}, {STRANGER: VAKRON, BOSS: VAKRON})
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    s.observe(engine, [DamageEvent(actor_id=STRANGER, target_id=ME, skill_code=15210000, damage=500, timestamp_ms=110_000),
                       DamageEvent(actor_id=ME, target_id=BOSS, skill_code=15210000, damage=500, timestamp_ms=110_000)],
              timestamp_ms=110_000)
    entities = {e["id"].split(":")[-1]: e for e in s.to_a2log("party")["segments"][0]["entities"]}
    assert entities[str(STRANGER)]["name"] == "Qv" and entities[str(STRANGER)]["is_player"]
    assert s.name(s.epoch, STRANGER) == "Qv" and s.name(s.epoch, BOSS) == "Vakron"


def _old_segment(*, died_at=173.913, more_deaths=(), struck=("25:1",), typed=False):
    """A segment as meter 0.2.374 exported the kill after a revive: the final boss as a player."""
    start = datetime(2026, 1, 5, 12, 0, 3, 751000, tzinfo=timezone.utc)
    boss = {"id": "25:1", "name": "Qv", "kind": "player", "is_boss": False, "is_player": True,
            "profile_snapshot": {"status": "unavailable"}}
    if typed:
        boss = {"id": "25:1", "name": "Vakron", "kind": "enemy", "is_boss": True, "is_player": False, "mob_code": VAKRON}
    vines = {"id": "25:2", "name": "Vakron's Thorn Vines", "kind": "enemy", "is_boss": True, "is_player": False,
             "mob_code": THORN_VINES}
    stranger = {"id": "25:3", "name": "Zx", "kind": "player", "is_boss": False, "is_player": True}
    return {"id": f"25-{int(start.timestamp() * 1000)}-1", "run_id": "14", "start": start.isoformat(),
            "duration": 173.913, "boss": "Vakron's Thorn Vines", "label": "Vakron's Thorn Vines", "killed": False,
            "recording_run": {"version": 1, "token": "t", "origin_sequence": 1, "final_boss_id": VAKRON,
                              "finished_at": (start + timedelta(seconds=173.913)).isoformat()},
            "entities": [boss, vines, stranger],
            "hits": [{"t": 1.0, "player": "p:1:1", "target": target, "damage": 500.0} for target in struck],
            "events": [{"kind": "death", "t": died_at, "target": "25:1"}]
                      + [{"kind": "death", "t": 173.913, "target": target} for target in more_deaths],
            "health": [{"t": 0.0, "entity": "25:1", "current": 27_913_066.0, "max": 27_918_000.0}]}


def test_the_log_server_types_a_recorded_final_boss_again_from_the_runs_record_of_its_death():
    doc = {"format": "a2log", "version": 1, "meta": {}, "segments": [_old_segment()]}
    fixed = rejoin(doc)
    segment = fixed["segments"][0]
    boss = next(e for e in segment["entities"] if e["id"] == "25:1")
    assert boss == {"id": "25:1", "name": "Vakron", "kind": "enemy", "is_boss": True, "is_player": False, "mob_code": VAKRON}
    assert segment["boss"] == segment["label"] == "Vakron" and segment["killed"] is True
    assert fixed["meta"]["repairs"]["final_boss_typed"] == [0] and fixed["meta"]["repairs"]["version"] == 3
    assert doc["segments"][0]["entities"][0]["kind"] == "player"        # the stored upload is never changed


def test_only_the_one_entity_that_died_at_the_recorded_finish_is_typed():
    assert recorded_final_boss(_old_segment(died_at=150.0)) is None                  # not the instant the run finished
    both = _old_segment(more_deaths=("25:3",), struck=("25:1", "25:3"))
    assert recorded_final_boss(both) is None                                          # two struck untyped deaths: no guess
    assert recorded_final_boss(_old_segment(more_deaths=("25:3",)))["id"] == "25:1"   # one the party never struck
    assert recorded_final_boss(_old_segment(struck=())) is None                       # the party never struck it
    assert recorded_final_boss(_old_segment(typed=True)) is None                      # typed already
    assert recorded_final_boss(_old_segment(more_deaths=("25:2",)))["id"] == "25:1"   # a typed add dying with it
    doc = {"format": "a2log", "version": 1, "meta": {}, "segments": [_old_segment(died_at=150.0)]}
    assert rejoin(doc) is doc
