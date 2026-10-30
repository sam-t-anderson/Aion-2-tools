"""Performance mode (Settings → App & data, 0.2.355) for a low-spec PC. The live reading is worked out at
most once a second and from a smaller share of the time it takes, and movement is kept once a second; the
overlay and the app's pages poll less often and hold still between polls (tests/browser). It is off by
default, the meter reads a change within seconds, and a settings backup leaves it on the computer it was
chosen for."""
import time

import pytest

from aion2calc.app import meter_runner as MR
from aion2calc.app import settings_backup
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession
from aion2calc.paths import write_user_json


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(CombatSession, "POSITION_EVERY_MS", 250)   # performance_mode() sets the class's own
    monkeypatch.setitem(MR._performance, "on", False)
    monkeypatch.setitem(MR._performance, "read_at", float("-inf"))
    return tmp_path


def _choose(on: bool) -> None:
    from aion2calc.app.server import ui_settings
    write_user_json({**ui_settings(), "performance_mode": on}, "ui.json")


def test_it_is_off_by_default_and_read_again_within_seconds(home, monkeypatch):
    from aion2calc.app.server import ui_settings
    assert ui_settings()["performance_mode"] is False
    assert MR.performance_mode() is False and CombatSession.POSITION_EVERY_MS == 250
    _choose(True)
    assert MR.performance_mode() is False                      # read at most every five seconds
    later = time.monotonic() + 5.0
    monkeypatch.setattr(MR.time, "monotonic", lambda: later)
    assert MR.performance_mode() is True and CombatSession.POSITION_EVERY_MS == 1000
    _choose(False)
    monkeypatch.setattr(MR.time, "monotonic", lambda: later + 5.0)
    assert MR.performance_mode() is False and CombatSession.POSITION_EVERY_MS == 250


def test_movement_is_kept_once_a_second(home):
    # A player walking for three seconds, a position every 100 ms: four kept at the usual 250 ms per point
    # would be twelve; once a second, three. A move's start and stop are kept whatever the sampling.
    _choose(True)
    MR.performance_mode()
    session = CombatSession()
    identity = {"names": {5001: "Me"}, "owners": {}, "spawns": {}, "local_id": 5001}
    walk = [{"entity": 5001, "timestamp_ms": ms, "src": "move", "x": ms / 100, "y": 0.0, "z": 0.0}
            for ms in range(0, 3000, 100)]
    session._keep_positions(walk, identity)
    assert len(session.positions) == 3
    session._keep_positions([{**walk[-1], "timestamp_ms": 3050, "src": "stop"}], identity)
    assert len(session.positions) == 4


def _runner():
    r = MR.Runner()
    s = CombatSession()
    s.pvp = False
    e = MeterEngine()
    e.map_id = e.dungeon_id = 600002
    e.last_zone_reset_ms = None
    e.local_player_id = 5001
    e.names = {5001: "Me", 5002: "Ally"}
    e.roster = {"Me": {}, "Ally": {}}
    e.known_players = {5001, 5002}
    e.spawn_info = {9002: {"mobCode": 12}}
    r.session, r.packet_engine = s, e
    return r, s, e


def _hit(actor, t):
    return DamageEvent(actor_id=actor, target_id=9002, skill_code=15210000, damage=500, timestamp_ms=t)


@pytest.mark.parametrize("on, recomputed", [(False, True), (True, False)])
def test_the_live_reading_is_worked_out_at_most_once_a_second(home, on, recomputed):
    _choose(on)
    r, s, e = _runner()
    now = int(time.time() * 1000)
    s.observe(e, [_hit(5001, now - 1_000)], timestamp_ms=now - 1_000)
    first = r._live_snapshot(True)
    r._last_snap_cost = 0.0
    r._snap_cache = (r._snap_cache[0], time.monotonic() - 0.7, *r._snap_cache[2:])   # the last reading, 0.7 s old
    s.observe(e, [_hit(5002, now - 500)], timestamp_ms=now - 500)
    assert r._live_snapshot(True) is first                     # the last reading is served either way
    assert (r._snap_thread is not None) is recomputed           # recomputed after half a second, or not before one
    if r._snap_thread is not None:
        r._snap_thread.join(5)


def test_a_settings_backup_leaves_it_on_this_computer(home):
    from aion2calc.app.server import ui_settings
    _choose(True)
    assert "performance_mode" in settings_backup.LOCAL_ONLY
    assert "performance_mode" not in settings_backup.backed_up(ui_settings())
