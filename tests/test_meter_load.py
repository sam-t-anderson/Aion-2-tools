"""Keeping the live meter responsive in a crowd (world / field bosses).

Replaying a real 18-minute capture at 50-100x the players showed where the pipeline stalls:
the live snapshot walks every record under the capture lock (seconds in a big fight), a forced
mid-fight storage rollover serialised the whole part on the decoder thread, the 15-second
checkpoint save competed for the CPU, and each hit re-derived the party's allowed sets for
every scope. These tests pin the structural fixes: the part is detached in milliseconds and
written on a worker while recording continues in a continuation; the checkpoint cadence
stretches when saves are slow; after the first reading, snapshot recomputes run off the lock on
a detached copy and the last completed reading is served meanwhile; and "is combat active" is
tracked per scope as records arrive instead of scanning the history.
"""
import threading
import time

import pytest

from aion2calc.app import meter_runner as MR
from aion2calc.combat import sessions
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def _engine():
    e = MeterEngine()
    e.names = {5001: "Me", 5002: "Ally"}
    e.known_players = {5001, 5002}
    e.roster = {"Me": {}, "Ally": {}}
    e.roster_complete = True
    e.local_player_id = 5001
    e.local_identity_from_game = True
    e.map_id = e.dungeon_id = 600022
    e.last_zone_reset_ms = None
    return e


def _runner(records=3):
    r = MR.Runner()
    r.scope = "party"
    r.save_records = True
    r.packet_engine = _engine()
    r.session = CombatSession()
    r.session.pvp = False
    now = int(time.time() * 1000)
    for i in range(records):
        r.session.observe(r.packet_engine, [DamageEvent(5001, 9001, 15210000, 100 + i, now - 300_000 + i * 1000)],
                          timestamp_ms=now - 300_000 + i * 1000)
    return r


def _force_due(r):
    # The rollover thresholds are counts of records/telemetry/groups/players; a group count of
    # 100 under the selected scope makes the part "due" without a hundred thousand records.
    r.session._storage_groups["party"] = 100


def test_rollover_detaches_the_part_at_once_and_writes_it_on_a_worker(home, monkeypatch):
    saved = []
    def fake_save(doc, name):
        saved.append((threading.current_thread().name, doc, name))
        return home / name
    monkeypatch.setattr(sessions, "save", fake_save)
    r = _runner()
    _force_due(r)
    live_before, file_before = r.session, r.session_file
    r._rollover_session()
    # Recording continues immediately in a continuation: a new session object, the next part
    # number, a new file, and the detached part queued for the worker.
    assert r.session is not live_before and not r.session.records
    assert r.archive_part == 2 and r.session_file != file_before and r.archive_previous is not None
    assert r._flush_thread is not None
    r._flush_thread.join(5)
    assert not r._unsaved_parts
    thread, doc, name = saved[0]
    assert thread == "part-flush" and name == file_before
    assert doc["meta"]["archive"] == {"id": r.archive_id, "part": 1, "closed": True, "continuity": r.archive_previous}
    assert doc["meta"]["capture_active"] is False and doc["segments"][0]["run_end_reason"] == "storage_rollover"
    assert r.diagnostics["archive_parts_saved"] == 1 and r.diagnostics["archive_last_part"].endswith(file_before)


def test_rollover_waits_while_nothing_is_identified_under_the_scope(home):
    r = _runner()
    _force_due(r)
    r.session._storage_players["party"] = set()      # nothing identified under the selected filter
    live = r.session
    r._rollover_session()
    assert r.session is live and r.archive_part == 1 and not r._unsaved_parts
    assert "waiting for player data" in r.diagnostics["archive_deferred"]


def test_rollover_is_deferred_while_the_scope_is_still_fighting(home):
    r = _runner()
    _force_due(r)
    r.session._last_outgoing["party"] = int(time.time() * 1000) - 5_000   # hit the boss 5 s ago
    live = r.session
    r._rollover_session()
    assert r.session is live and r.archive_part == 1
    assert "after combat pauses" in r.diagnostics["archive_deferred"]


def test_a_part_that_cannot_be_written_yet_is_retried_never_lost(home, monkeypatch):
    attempts = []
    def flaky_save(doc, name):
        attempts.append(name)
        if len(attempts) == 1:
            raise OSError("disk busy")
        return home / name
    monkeypatch.setattr(sessions, "save", flaky_save)
    r = _runner()
    _force_due(r)
    r._rollover_session()
    r._flush_thread.join(5)
    assert len(r._unsaved_parts) == 1 and "disk busy" in r.diagnostics["archive_save_error"]
    r._flush_parts()                                   # the next save retries it
    assert not r._unsaved_parts and len(attempts) == 2 and "archive_save_error" not in r.diagnostics


def test_checkpoint_cadence_stretches_with_slow_saves(home, monkeypatch):
    r = MR.Runner()
    spawned = []
    monkeypatch.setattr(r, "_spawn_save", lambda: spawned.append(1) or True)
    r._last_save_cost = 10.0                           # a save that takes ten seconds
    r._last_checkpoint = time.monotonic() - 20
    r._checkpoint_session()
    assert not spawned                                 # 15 s is no longer enough
    r._last_checkpoint = time.monotonic() - 41
    r._checkpoint_session()
    assert spawned                                     # four times the save cost has passed
    r._last_save_cost = 0.3
    r._last_checkpoint = time.monotonic() - 16
    r._checkpoint_session()
    assert len(spawned) == 2                           # quick saves: back to 15 s


class _CountingSession:
    computed = []

    def snapshot(self, scope, segment_id, enemy_id, combine_pets):
        _CountingSession.computed.append(threading.current_thread().name)
        return {"players": [], "reading": len(_CountingSession.computed)}


def test_snapshot_recomputes_off_the_lock_and_serves_the_last_reading():
    _CountingSession.computed.clear()
    r = MR.Runner()
    r.session = _CountingSession()
    first = r._live_snapshot(True)
    assert first["reading"] == 1 and _CountingSession.computed == ["MainThread"]   # the first reading is immediate
    assert r._live_snapshot(True) is first                                          # within the interval: cached
    time.sleep(0.27)
    served = r._live_snapshot(True)
    assert served is first                                                          # stale reading served at once...
    r._snap_thread.join(2)
    assert _CountingSession.computed[-1] == "live-snapshot"                         # ...while a worker recomputed
    assert r._live_snapshot(True)["reading"] == 2                                   # the new reading replaces it


class _SlowSession(_CountingSession):
    release = threading.Event()

    def snapshot(self, scope, segment_id, enemy_id, combine_pets):
        if _CountingSession.computed:
            _SlowSession.release.wait(5)   # every reading after the first waits for the test
        return super().snapshot(scope, segment_id, enemy_id, combine_pets)


def test_a_recompute_for_a_previous_session_is_discarded():
    _CountingSession.computed.clear()
    _SlowSession.release.clear()
    r = MR.Runner()
    r.session = _SlowSession()
    first = r._live_snapshot(True)
    time.sleep(0.27)
    r._live_snapshot(True)             # the worker starts its reading of this session...
    r.session = _SlowSession()         # ...a rollover/restart swaps the live session meanwhile
    _SlowSession.release.set()
    r._snap_thread.join(2)
    assert len(_CountingSession.computed) == 2
    assert r._snap_cache[2] is first   # the worker's reading of the old session never shows


def test_observe_tracks_last_outgoing_damage_per_scope():
    e = _engine()
    s = CombatSession()
    s.pvp = False
    s.observe(e, [DamageEvent(5001, 9001, 15210000, 100, 1_000)], timestamp_ms=1_000)
    s.observe(e, [DamageEvent(9001, 5001, 15210000, 50, 2_000)], timestamp_ms=2_000)   # incoming: not outgoing
    assert s._last_outgoing["party"] == 1_000 and s._last_outgoing["self"] == 1_000
    s.observe(e, [DamageEvent(5002, 9001, 15210000, 70, 3_000)], timestamp_ms=3_000)
    assert s._last_outgoing["party"] == 3_000 and s._last_outgoing["self"] == 1_000     # an ally's hit is party, not self
    assert s.continuation()._last_outgoing == s._last_outgoing


def test_party_scope_keeps_only_effects_that_involve_the_party_once_identified():
    e = _engine()
    s = CombatSession()
    s.pvp = False
    s.retain_scope = "party"
    e.names[7777] = "Stranger"; e.known_players.add(7777)          # another player at the world boss
    hits = [DamageEvent(5001, 9001, 15210000, 100, 1_000),          # me -> boss: kept
            DamageEvent(7777, 9001, 15210000, 100, 1_001),          # stranger -> boss: not ours
            DamageEvent(9001, 5002, 15210000, 30, 1_002),           # boss -> ally: kept (incoming)
            DamageEvent(9001, 7777, 15210000, 30, 1_003)]           # boss -> stranger: not ours
    e.telemetry = [{"kind": "hp", "entity": 7777, "current": 10, "max": 20, "timestamp_ms": 1_004},
                   {"kind": "hp", "entity": 5002, "current": 10, "max": 20, "timestamp_ms": 1_005},
                   {"kind": "death", "entity": 7777, "timestamp_ms": 1_006}]
    s.observe(e, hits, timestamp_ms=1_010)
    assert [r.event.actor_id for r in s.records] == [5001, 9001]
    assert [r.sequence for r in s.records] == [1, 2]                 # retained records stay contiguous
    assert [t["entity"] for t in s.telemetry] == [5002]
    assert s.out_of_scope == 4 and s.discarded == 0                  # by design, never "capture loss"
    assert s.to_a2log("party", "t")["meta"]["capture_quality"]["out_of_scope_effects"] == 4
    assert s.continuation().retain_scope == "party"


def test_everything_is_kept_while_identity_is_unknown_or_under_all():
    e = _engine()
    e.names[7777] = "Stranger"; e.known_players.add(7777)
    stranger = [DamageEvent(7777, 9001, 15210000, 100, 1_001)]
    unknown_roster = CombatSession(); unknown_roster.pvp = False; unknown_roster.retain_scope = "party"
    e.roster = {}                                                     # no roster packet yet: late reconciliation needs the history
    unknown_roster.observe(e, stranger, timestamp_ms=1_010)
    assert len(unknown_roster.records) == 1
    e.roster = {"Me": {}, "Ally": {}}
    unknown_self = CombatSession(); unknown_self.pvp = False; unknown_self.retain_scope = "self"
    e.local_player_id = None
    unknown_self.observe(e, stranger, timestamp_ms=1_010)
    assert len(unknown_self.records) == 1
    e.local_player_id = 5001
    everyone = CombatSession(); everyone.pvp = False; everyone.retain_scope = "all"
    everyone.observe(e, stranger, timestamp_ms=1_010)
    assert len(everyone.records) == 1
    legacy = CombatSession(); legacy.pvp = False                      # no retention scope: as before
    legacy.observe(e, stranger, timestamp_ms=1_010)
    assert len(legacy.records) == 1


def test_the_runner_hands_its_scope_to_the_session(home, monkeypatch):
    monkeypatch.setattr(MR, "capture_packets", lambda *a, **k: None)
    r = MR.Runner()
    try:
        r.start("a2tools", port=50349, auto_port=True, scope="party")
        assert r.session.retain_scope == "party"
        r.configure_view({"scope": "all"})                   # a live scope change widens retention from now on
        assert r.scope == "all" and r.session.retain_scope == "all"
    finally:
        r.stop()


def test_a_world_boss_crowd_in_scope_does_not_force_rollovers(home):
    r = _runner()
    r.scope = "all"
    r.session.retain_scope = "all"
    r.session._storage_players["all"] = {f"player{i}" for i in range(120)}   # a hundred-odd players in scope
    live = r.session
    r._rollover_session()
    assert r.session is live and r.archive_part == 1 and not r._unsaved_parts   # neither due nor forced
    r.session._storage_players["all"] = {f"player{i}" for i in range(MR._ROLLOVER_PLAYERS_HARD)}
    r._rollover_session()
    assert r.archive_part == 2                                                  # the export limit still guards


def test_the_party_roster_is_carried_through_chained_zone_loads():
    e = _engine()
    s = CombatSession()
    s.pvp = False
    s.retain_scope = "party"
    e.last_zone_reset_ms = 1_000
    s.observe(e, [DamageEvent(5001, 9001, 15210000, 100, 1_000)], timestamp_ms=1_000)   # roster known
    e.roster = {}                                                       # a teleport clears it...
    e.last_zone_reset_ms = 2_000
    s.observe(e, [], timestamp_ms=2_000)
    e.last_zone_reset_ms = 2_500                                        # ...and the destination loads again
    s.observe(e, [], timestamp_ms=2_500)
    e.names[7777] = "Stranger"; e.known_players.add(7777)
    s.observe(e, [DamageEvent(5002, 9001, 15210000, 70, 3_000), DamageEvent(7777, 9001, 15210000, 70, 3_001)], timestamp_ms=3_000)
    identity = s.identities[s.epoch]
    assert s.epoch == 3 and identity["carried_roster"] == frozenset({"me", "ally"})   # epochs: first reset, teleport, load
    # The ally's hit is in scope (kept, not roster-late); the stranger's is not retained.
    assert [r.event.actor_id for r in s.records if r.epoch == 3] == [5002]
    assert s.snapshot("party")["party_roster_late"] is False
