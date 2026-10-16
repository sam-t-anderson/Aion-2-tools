"""Checkpoint copies are cheap, a teleport keeps the party, and a dead player who casts is alive.

- ``copy.deepcopy(session)`` (every 15 s checkpoint and every rollover, under the capture lock)
  shares the immutable records instead of copying 100k of them: a true deep copy took seconds and
  stalled the decoder and the overlay.
- A zone load inside an instance (the teleport to a boss room) clears the engine's roster until
  the next roster packet; the records before it were "roster late" and the fight unranked. The
  previous epoch's roster is carried so the party is known from the first hit.
- A player marked dead who lands a full cast is alive even if the resurrection's HP sample was
  lost (84% packet loss in the reported recording), so the overlay indicator clears.
- The saved log carries a ``revive`` marker at a player's first HP above zero after a death.
"""
import copy
import time

from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession, Record


def _hit(actor, target, t, dmg, dot=False):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t, is_dot=dot)


def _engine():
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me", 5002: "Ally"}
    engine.known_players = {5001, 5002}
    engine.roster = {"Me": {}, "Ally": {}}
    engine.roster_complete = True
    return engine


def test_deepcopy_shares_records_and_stays_a_snapshot():
    s = CombatSession()
    party = frozenset({"me", "ally"})
    for i in range(50_000):
        s.records.append(Record(0, _hit(5001, 9001, 1000 + i * 40, 100), party, 5001, 0, 1, i))
    for i in range(5_000):
        s.telemetry.append({"kind": "hp", "entity": 9001, "current": 100, "max": 200, "timestamp_ms": 1000 + i, "epoch": 0})
    t0 = time.perf_counter()
    clone = copy.deepcopy(s)
    assert time.perf_counter() - t0 < 1.0                            # milliseconds, not seconds
    assert len(clone.records) == 50_000 and clone.records[0] is s.records[0]   # shared frozen records
    s.records.append(Record(0, _hit(5001, 9001, 5_000_000, 100), party, 5001, 0, 1, 50_000))
    assert len(clone.records) == 50_000                               # the clone is a snapshot
    assert clone.runs is not s.runs and clone.runs == s.runs          # small state is a real copy


def test_a_teleport_carries_the_party_so_the_boss_room_fight_is_not_roster_late():
    s = CombatSession(); s.pvp = False
    engine = _engine()
    s.observe(engine, [_hit(5001, 9001, 1000, 500), _hit(5002, 9001, 1500, 500)], timestamp_ms=1500)
    # The boss-room teleport: a zone reset clears the roster; the first hits land before the
    # roster packet is seen again (names arrive with the spawn/binding packets, the roster later).
    engine.last_zone_reset_ms = 200_000
    engine.roster = {}
    engine.roster_complete = False
    engine.names = {5001: "Me", 5002: "Ally"}
    s.observe(engine, [_hit(5001, 9101, 201_000, 800), _hit(5002, 9101, 201_500, 800)], timestamp_ms=201_500)
    engine.roster = {"Me": {}, "Ally": {}}          # the roster packet arrives mid-fight
    engine.roster_complete = True
    s.observe(engine, [_hit(5001, 9101, 203_000, 800), _hit(5002, 9101, 203_500, 800)], timestamp_ms=203_500)
    doc = s.to_a2log(scope="party", title="t")
    last = doc["segments"][-1]
    assert sorted(p["name"] for p in doc["players"] if p["id"] in last["party_members"]) == ["Ally", "Me"]
    assert last["party_roster_late"] is False
    assert last["party_roster_complete"] is True


def test_a_dead_player_who_lands_a_full_cast_is_alive_again():
    s = CombatSession(); s.pvp = False
    engine = _engine()
    s.observe(engine, [_hit(5001, 9001, 1000, 500), _hit(5002, 9001, 1500, 500)], timestamp_ms=1500)
    engine.telemetry = [{"kind": "death", "entity": 5002, "timestamp_ms": 3000}]
    s.observe(engine, [_hit(5001, 9001, 3000, 500)], timestamp_ms=3000)
    assert {r["name"]: r["dead"] for r in s.snapshot(scope="auto", segment_id=None)["players"]}["Ally"] is True
    engine.telemetry = []
    s.observe(engine, [_hit(5002, 9001, 4000, 50, dot=True)], timestamp_ms=4000)      # a lingering DoT tick: still dead
    assert {r["name"]: r["dead"] for r in s.snapshot(scope="auto", segment_id=None)["players"]}["Ally"] is True
    s.observe(engine, [_hit(5002, 9001, 5000, 900)], timestamp_ms=5000)               # a full cast: alive (the revive HP sample was lost)
    assert {r["name"]: r["dead"] for r in s.snapshot(scope="auto", segment_id=None)["players"]}["Ally"] is False


def test_the_saved_log_marks_the_resurrection():
    s = CombatSession(); s.pvp = False
    engine = _engine()
    s.observe(engine, [_hit(5001, 9001, 1000, 500), _hit(5002, 9001, 1500, 500)], timestamp_ms=1500)
    engine.telemetry = [{"kind": "hp", "entity": 5002, "current": 0, "max": 9000, "timestamp_ms": 3000},
                        {"kind": "death", "entity": 5002, "timestamp_ms": 3000}]
    s.observe(engine, [_hit(5001, 9001, 3000, 500)], timestamp_ms=3000)
    engine.telemetry = [{"kind": "hp", "entity": 5002, "current": 0, "max": 9000, "timestamp_ms": 4000},   # still dead
                        {"kind": "hp", "entity": 5002, "current": 9000, "max": 9000, "timestamp_ms": 6000}]  # resurrected
    s.observe(engine, [_hit(5002, 9001, 6500, 700)], timestamp_ms=6500)
    seg = s.to_a2log(scope="party", title="t")["segments"][0]
    ally = next(p["id"] for p in s.to_a2log(scope="party", title="t")["players"] if p["name"] == "Ally")
    marks = [(e["kind"], e["t"]) for e in seg["events"] if e["kind"] in ("death", "revive") and e["target"] == ally]
    assert marks == [("death", 2.0), ("revive", 5.0)]
    from aion2calc.combat.a2log import validate
    kept = validate(s.to_a2log(scope="party", title="t"))
    assert any(e["kind"] == "revive" for e in kept["segments"][0]["events"])      # the format keeps the marker
