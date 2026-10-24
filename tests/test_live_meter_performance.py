"""The live meter's cost follows the current fight, not the session (0.2.336): ``groups`` carries its
last result on by the records that arrived since and gives what a fresh walk gives; a reading is served
again, its clock fields brought up to date, while the session's state signature is unchanged; and the
HP helpers read the telemetry from its newest sample back."""
import copy
import time

import pytest

from aion2calc.app import meter_runner as MR
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.session import CombatSession

CLOCK = ("idle_ms", "boss_alive", "potential_reset", "battle_over", "paused")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _hp(entity, current, maximum, t):
    return {"entity": entity, "kind": "hp", "current": current, "max": maximum, "timestamp_ms": t}


def _death(entity, t):
    return {"entity": entity, "kind": "death", "timestamp_ms": t}


def _session():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me", 5002: "Ally"}
    engine.roster = {"Me": {}, "Ally": {}}
    engine.known_players = {5001, 5002}
    return s, engine


def _shape(groups):
    return [(g["id"], g["epoch"], g["start"], g["end"], g["last_damage"], g["damage_start"], g["split"], g["run"], g["pvp"],
             g["kind_damage"], tuple(sorted(g["majors"])), tuple(r.sequence for r in g["records"])) for g in groups]


def _fresh(s, scope="party"):
    carried, s._grouping = s._grouping, None
    result = _shape(s.groups(scope))
    s._grouping = carried
    return result


def _strip(snap):
    return {k: v for k, v in snap.items() if k not in CLOCK}


def test_carried_groups_match_a_fresh_walk_as_the_session_grows(monkeypatch):
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, e = _session()
    e.spawn_info = {9001: {"mobCode": 777}, 9002: {"mobCode": 12}, 9003: {"mobCode": 12}}
    # A first pull, a heal inside it, trash, a lull longer than the pull gap, then a boss pulled twice
    # with its death closing the second fight, and a party member's death: each step is compared.
    steps = [
        ([_hit(5001, 9002, 100_000), _hit(5002, 9002, 100_400)], [], 100_400),
        ([HealEvent(actor_id=5002, target_id=5001, skill_code=11000000, amount=300, timestamp_ms=100_900)], [], 100_900),
        ([_hit(5001, 9003, 101_500), _hit(9003, 5002, 101_600)], [_hp(9003, 100, 1000, 101_600), _death(9003, 101_700)], 101_700),
        ([_hit(5001, 9001, 300_000), _hit(5002, 9001, 300_500)], [_hp(9001, 900, 1000, 300_500)], 300_500),
        ([_hit(9001, 5002, 301_000)], [_death(5002, 301_000)], 301_000),
        ([_hit(5001, 9001, 460_000)], [_hp(9001, 300, 1000, 460_000)], 460_000),
        ([_hit(5001, 9001, 461_000)], [_death(9001, 461_500)], 461_500),
        ([_hit(5001, 9002, 470_000)], [], 470_000),
    ]
    for events, telemetry, now in steps:
        e.telemetry = list(telemetry)
        s.observe(e, events, timestamp_ms=now)
        e.telemetry = []
        for scope in ("party", "self"):
            assert _shape(s.groups(scope)) == _fresh(s, scope), (scope, now)
        assert _strip(s.snapshot("party", None, None, True)) == _strip(s.snapshot("party", None, None, True))
    assert len(s.groups("party")) >= 3
    carried = s._grouping
    assert carried is not None and carried.last_seq == s.records[-1].sequence
    assert s._carry_grouping("party", (s.pvp, s.gap_seconds, s.automatic_splits), s._allowances("party")) is carried
    # A detached copy shares the carried result and walks on from it; the live session can adopt its advance.
    clone = copy.deepcopy(s)
    assert clone._grouping is carried
    s.observe(e, [_hit(5001, 9002, 471_000)], timestamp_ms=471_000)
    assert _shape(s.groups("party")) == _fresh(s)
    assert s._grouping is not carried and clone._grouping is carried
    clone.adopt_grouping(s._grouping)
    assert clone._grouping is s._grouping


def test_carried_groups_are_walked_again_when_what_they_read_changes(monkeypatch):
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": code == 777})
    s, e = _session()
    e.spawn_info = {9002: {"mobCode": 12}}
    s.observe(e, [_hit(5001, 9002, 100_000), _hit(7777, 5001, 100_200), _hit(5001, 7777, 100_300)], timestamp_ms=100_300)
    before = s.groups("party")
    config = (s.pvp, s.gap_seconds, s.automatic_splits)
    assert s._carry_grouping("party", config, s._allowances("party")) is s._grouping
    # The stranger who hit us becomes a known player: the hit on them is now player-versus-player, which
    # a fresh walk cuts into its own fight. The carried result notices and is walked again.
    e.known_players = {5001, 5002, 7777}
    e.names[7777] = "Stranger"
    s.observe(e, [], timestamp_ms=100_400)
    assert s._carry_grouping("party", config, s._allowances("party")) is None
    after = s.groups("party")
    assert _shape(after) == _fresh(s) and 7777 in s._grouping.players and len(after) == len(before)
    # Another scope or a changed setting is never carried across.
    assert s._carry_grouping("self", config, s._allowances("self")) is None
    s.gap_seconds = 300
    assert s._carry_grouping("party", (s.pvp, s.gap_seconds, s.automatic_splits), s._allowances("party")) is None
    assert _shape(s.groups("party")) == _fresh(s)


def test_an_enemy_death_before_the_open_fight_is_settled_and_a_later_one_re_applied(monkeypatch):
    import aion2calc.meter.session as session
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": False})
    s, e = _session()
    e.spawn_info = {9002: {"mobCode": 12}, 9003: {"mobCode": 12}}
    s.observe(e, [_hit(5001, 9002, 100_000), _hit(5001, 9002, 100_500)], timestamp_ms=100_500)
    e.telemetry = [_death(9002, 100_900)]
    s.observe(e, [], timestamp_ms=100_900)
    e.telemetry = []
    first = s.groups("party")
    assert first[-1]["end"] == 100_900                      # the kill closes the fight it was still fighting
    assert s._grouping.settled == 0                         # the open fight is the one it closed: re-applied each call
    s.observe(e, [_hit(5001, 9003, 400_000)], timestamp_ms=400_000)   # a new fight after the pull gap
    second = s.groups("party")
    assert second[0]["end"] == 100_900 and s._grouping.settled == 1   # settled into the closed fight for good
    assert _shape(second) == _fresh(s)
    e.telemetry = [_death(9003, 400_300)]
    s.observe(e, [], timestamp_ms=400_300)
    e.telemetry = []
    third = s.groups("party")
    assert third[-1]["end"] == 400_300 and _shape(third) == _fresh(s)


def test_the_history_cap_trims_the_carried_fights(monkeypatch):
    import aion2calc.meter.session as session
    from collections import deque
    monkeypatch.setattr(session, "npc_info", lambda code: {"isBoss": False})
    s, e = _session()
    s.records = deque(maxlen=6)
    e.spawn_info = {9002: {"mobCode": 12}}
    s.observe(e, [_hit(5001, 9002, 100_000 + i * 100) for i in range(4)], timestamp_ms=100_300)
    s.groups("party")
    s.observe(e, [_hit(5001, 9002, 300_000 + i * 100) for i in range(4)], timestamp_ms=300_300)   # evicts two records
    carried = s.groups("party")
    assert len(s.records) == 6 and s.discarded == 2
    assert [len(g["records"]) for g in carried] == [2, 4]
    assert [r.sequence for r in carried[0]["records"]] == [3, 4]
    assert _shape(carried)[1] == _fresh(s)[1]               # the open fight reads as a fresh walk reads it
    s.observe(e, [_hit(5001, 9002, 301_000 + i * 100) for i in range(5)], timestamp_ms=301_400)   # the first fight is gone
    carried, fresh = s.groups("party"), _fresh(s)
    assert len(carried) == len(fresh) == 1
    # The oldest surviving fight keeps the start it had (its records before the cap are gone, the fight
    # did begin then), where a fresh walk opens it at its first surviving record; the rest reads alike.
    assert (carried[0]["start"], carried[0]["damage_start"]) == (300_000, 300_000) and fresh[0][2] == 300_300
    kept = _shape(carried)[0]
    assert kept[3:5] + kept[6:] == fresh[0][3:5] + fresh[0][6:]      # end, last hit, split, run, kind, majors, records


def test_state_signature_changes_with_what_a_reading_reads_and_refresh_clock_matches_a_recompute(monkeypatch):
    s, e = _session()
    e.spawn_info = {9002: {"mobCode": 12}}
    now = int(time.time() * 1000)
    s.observe(e, [_hit(5001, 9002, now - 1_000)], timestamp_ms=now - 1_000)
    first = s.state_signature()
    assert s.state_signature() == first                       # nothing happened: the same
    s.observe(e, [], timestamp_ms=now - 900)                   # an empty packet changes nothing either
    assert s.state_signature() == first
    s.observe(e, [_hit(5002, 9002, now - 800)], timestamp_ms=now - 800)
    second = s.state_signature()
    assert second != first
    e.telemetry = [_hp(9002, 500, 1000, now - 700)]
    s.observe(e, [], timestamp_ms=now - 700)
    e.telemetry = []
    assert s.state_signature() != second                       # telemetry counts too
    s.reset_after_battle = True
    assert s.state_signature() != second                       # and the settings a reading applies
    # The clock fields of a reading served again are exactly what a recompute sets.
    s.reset_delay_seconds = 1
    reading = s.snapshot("party", None, None, True)
    clock = s.clock_inputs
    assert clock is not None and clock[1] == now - 800 and clock[4] is True
    assert reading["paused"] is False and reading["battle_over"] is False
    later = now + 3_000
    monkeypatch.setattr(session_time(), "time", lambda: later / 1000)
    fresh = s.snapshot("party", None, None, True)
    s.refresh_clock(reading, clock)
    assert {k: reading[k] for k in CLOCK} == {k: fresh[k] for k in CLOCK}
    assert reading["paused"] is True and reading["battle_over"] is True and reading["idle_ms"] == later - (now - 800)
    empty = {}
    s.refresh_clock(empty, None)
    assert empty == {"idle_ms": None, "boss_alive": False, "potential_reset": False, "battle_over": False, "paused": False}


def session_time():
    import aion2calc.meter.session as session
    return session.time


def test_hp_helpers_read_from_the_newest_sample_back():
    s, e = _session()
    e.spawn_info = {9001: {"mobCode": 777}}
    e.telemetry = [_hp(9001, 1000, 1000, 1_000), _hp(9001, 900, 1000, 2_000), _hp(9001, 800, 1000, 20_000),
                   _hp(9001, 700, 1000, 21_000), _hp(9001, 650, 1000, 21_000), _hp(9001, 600, 1000, 23_000)]
    s.observe(e, [_hit(5001, 9001, 1_500)], timestamp_ms=23_000)
    e.telemetry = []
    epochs = {s.epoch}
    assert s._latest_hp(9001, epochs) == (600, 1000)
    rate = s._hp_decline_rate(9001, epochs)
    assert rate is not None and abs(rate - (800 - 600) / 3.0) < 1e-9        # the 20 s window: 20 s .. 23 s
    assert s._latest_hp(9001, {s.epoch + 1}) == (None, None)                 # another epoch: nothing
    assert s._hp_decline_rate(9001, {s.epoch + 1}) is None
    # Of two samples at the same time the one recorded last is the current reading, as before.
    e.telemetry = [_hp(9001, 550, 1000, 24_000), _hp(9001, 540, 1000, 24_000)]
    s.observe(e, [], timestamp_ms=24_000)
    assert s._latest_hp(9001, epochs)[0] == 540


def test_the_live_reading_is_served_again_until_the_session_changes(home):
    r = MR.Runner()
    s, e = _session()
    r.session, r.packet_engine = s, e
    e.spawn_info = {9002: {"mobCode": 12}}
    now = int(time.time() * 1000)
    s.observe(e, [_hit(5001, 9002, now - 1_000)], timestamp_ms=now - 1_000)
    first = r._live_snapshot(True)
    assert first["players"][0]["damage"] == 500
    assert r._live_snapshot(True) is first                    # unchanged: the same reading, never recomputed
    r._last_snap_cost = 0.0
    r._snap_cache = (r._snap_cache[0], time.monotonic() - 1.0, *r._snap_cache[2:])   # well past the interval
    assert r._live_snapshot(True) is first and r._snap_thread is None
    s.observe(e, [_hit(5002, 9002, now - 500)], timestamp_ms=now - 500)
    assert r._live_snapshot(True) is first                    # changed: the stale reading, while a worker recomputes
    r._snap_thread.join(5)
    second = r._live_snapshot(True)
    assert second is not first and sum(p["damage"] for p in second["players"]) == 1000
    assert s._grouping is not None and s._grouping.last_seq == s.records[-1].sequence   # the live session adopted the worker's walk


def test_review_log_is_served_again_while_nothing_changed(home):
    r = MR.Runner()
    s, e = _session()
    r.session, r.packet_engine = s, e
    e.spawn_info = {9002: {"mobCode": 12}}
    s.observe(e, [_hit(5001, 9002, 100_000), _hit(5001, 9002, 100_500)], timestamp_ms=100_500)
    first = r.review_log()
    assert first["review_cost_ms"] >= 0 and first["segments"]
    assert r.review_log() is first
    s.observe(e, [_hit(5002, 9002, 101_000)], timestamp_ms=101_000)
    second = r.review_log()
    assert second is not first and sum(h["damage"] for h in second["segments"][-1]["hits"]) == 1500
