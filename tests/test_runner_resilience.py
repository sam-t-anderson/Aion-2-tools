"""The live runner: checkpoint saves leave the decoder thread, a restart keeps identities, and
the boss HP memory survives on disk."""
import json
import threading
import time

import pytest

from aion2calc.app import meter_runner as MR
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def test_checkpoint_saves_run_on_a_worker_and_never_overlap(home, monkeypatch):
    r = MR.Runner()
    calls, started, release = [], threading.Event(), threading.Event()

    def slow_save(active):
        calls.append((threading.current_thread().name, active))
        started.set()
        release.wait(5)
    monkeypatch.setattr(r, "_save_session", slow_save)
    r._last_checkpoint = time.monotonic() - 30
    r._checkpoint_session()
    assert started.wait(2) and calls[0] == ("session-save", True)       # off the calling thread
    r._last_checkpoint = time.monotonic() - 30
    r._checkpoint_session()                                              # the previous save is still running
    assert len(calls) == 1                                               # not started a second one
    release.set()
    r._save_thread.join(2)
    r._last_checkpoint = time.monotonic() - 30
    r._checkpoint_session()
    r._save_thread.join(2)
    assert len(calls) == 2


def test_a_restart_mid_recording_adopts_the_last_engines_identities(home, monkeypatch):
    monkeypatch.setattr(MR, "capture_packets", lambda *a, **k: None)     # no real sniffer
    r = MR.Runner()
    previous = MeterEngine()
    previous.names = {5001: "Me", 5002: "Ally"}; previous.known_players = {5001, 5002}
    previous.roster = {"Me": {}, "Ally": {}}; previous.roster_complete = True
    previous.local_player_id = 5001; previous.local_identity_from_game = True
    previous.map_id = previous.dungeon_id = 600022
    r.packet_engine = previous
    r.session = CombatSession()
    r.session.pvp = False
    previous.last_zone_reset_ms = None
    r.session.observe(previous, [DamageEvent(5001, 9001, 15210000, 100, 1000)], timestamp_ms=1000)   # mid-recording
    assert r.session.records
    try:
        r.start("a2tools", port=50349, auto_port=True)
        assert r.packet_engine is not previous
        assert r.packet_engine.local_player_id == 5001 and r.packet_engine.roster_complete
        assert r.packet_engine.names == {5001: "Me", 5002: "Ally"} and r.packet_engine.dungeon_id == 600022
    finally:
        r.stop()


def test_boss_hp_memory_round_trips_through_disk(home, monkeypatch):
    r = MR.Runner()
    monkeypatch.setattr(r, "_game_build", lambda: "version:product:1.0.21.0")
    r.packet_engine = MeterEngine()
    r.packet_engine.boss_hp_seen = {2300371: 15_504_000.0}
    r._store_boss_hp()
    from aion2calc.paths import data_file
    stored = json.loads(data_file("community", "boss_hp_seen.json").read_text(encoding="utf-8"))
    assert stored["builds"]["version:product:1.0.21.0"]["2300371"] == 15_504_000.0
    fresh = MeterEngine()
    r._seed_boss_hp(fresh)
    assert fresh.boss_hp_seen == {2300371: 15_504_000.0}
    monkeypatch.setattr(r, "_game_build", lambda: "version:product:9.9.9.9")   # another build: its own table
    other = MeterEngine()
    r._seed_boss_hp(other)
    assert other.boss_hp_seen == {}
