"""The dungeon's weekly runs left, on the overlay and the Live Meter page (0.2.411).

The game's counter table holds a count of runs left for each weekly dungeon entry, counters 60000002 onwards, but not
which dungeon each belongs to. In the 20 October recording counter 60000009 went from 4 to 3 in Fire Temple (600022)
as its reward was claimed, a minute and a half after its final boss died, while the Ferocious Horn Den run before it
spent Odyle Energy and moved no weekly counter. So the meter learns the pair when a weekly counter goes down inside a
dungeon, the app keeps it for the next capture, and the overlay shows that counter whenever the player is inside.
"""
import os
import time

import pytest

from aion2calc.app import meter_runner as MR
from aion2calc.app import server
from aion2calc.app.settings_backup import _clean
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.parser import ODYLE_ENERGY_ID, WEEKLY_COUNTERS
from aion2calc.meter.session import CombatSession
from aion2calc.paths import write_user_json
from test_odyle_energy import SERVER, _bundle, _table, _update

FIRE_TEMPLE, VAKRON, OPEN_WORLD = 600022, 600073, 1110
COUNTER = 60_000_009                                     # 14 runs left in the test table, as every weekly counter there


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def _engine():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_bundle([_table(840, 50)]), 1_000, SERVER)
    return engine


def _inside(engine, instance):
    engine.map_id = engine.dungeon_id = instance


def test_a_weekly_counter_going_down_inside_a_dungeon_is_that_dungeons():
    assert COUNTER in WEEKLY_COUNTERS and ODYLE_ENERGY_ID not in WEEKLY_COUNTERS
    engine = _engine()
    _inside(engine, FIRE_TEMPLE)
    assert engine.weekly_runs_left() is None                                     # not known yet
    engine.consume(_update(13, 0, reason=3, counter_id=COUNTER), 2_000, SERVER)  # a run's reward claimed
    assert engine.weekly_counters == {FIRE_TEMPLE: COUNTER} and engine.weekly_learned == [(FIRE_TEMPLE, COUNTER)]
    assert engine.weekly_runs_left() == {"instance": FIRE_TEMPLE, "counter": COUNTER, "regular": 13, "bonus": 0,
                                         "timestamp_ms": 2_000}


def test_nothing_is_learned_outside_a_dungeon_from_a_counter_going_up_or_from_another_counter():
    engine = _engine()
    engine.map_id = OPEN_WORLD
    engine.consume(_update(13, 0, reason=3, counter_id=COUNTER), 2_000, SERVER)  # down, but in the open world
    _inside(engine, FIRE_TEMPLE)
    engine.consume(_update(14, 0, reason=2, counter_id=COUNTER), 3_000, SERVER)  # up: the weekly reset
    engine.consume(_update(760, 50, reason=3, counter_id=ODYLE_ENERGY_ID), 4_000, SERVER)   # Odyle Energy spent
    assert engine.weekly_counters == {} and engine.weekly_learned == [] and engine.weekly_runs_left() is None


def test_a_known_pair_shows_from_the_start_and_only_inside_its_dungeon():
    engine = _engine()
    engine.weekly_counters[VAKRON] = COUNTER                                     # learned by an earlier capture
    _inside(engine, VAKRON)
    assert engine.weekly_runs_left()["regular"] == 14
    engine.consume(_update(12, 1, reason=3, counter_id=COUNTER), 2_000, SERVER)  # the game's later count, followed
    assert (engine.weekly_runs_left()["regular"], engine.weekly_runs_left()["bonus"]) == (12, 1)
    engine.map_id, engine.dungeon_id = OPEN_WORLD, 0
    assert engine.weekly_runs_left() is None


def test_a_restarted_capture_keeps_the_pairs():
    engine = _engine()
    _inside(engine, FIRE_TEMPLE)
    engine.consume(_update(13, 0, reason=3, counter_id=COUNTER), 2_000, SERVER)
    restarted = MeterEngine()
    restarted.adopt_identity(engine)
    assert restarted.weekly_counters == {FIRE_TEMPLE: COUNTER}


def test_the_app_keeps_what_was_learned_for_the_next_capture(home):
    assert MR.load_weekly_counters() == {}
    MR.save_weekly_counters([(FIRE_TEMPLE, COUNTER)])
    MR.save_weekly_counters([(VAKRON, 60_000_004), (FIRE_TEMPLE, COUNTER)])
    assert MR.load_weekly_counters() == {FIRE_TEMPLE: COUNTER, VAKRON: 60_000_004}
    runner = MR.Runner()
    runner.packet_engine = _engine()
    runner.packet_engine.weekly_learned = [(600002, 60_000_002)]
    runner._keep_weekly_counters()
    assert runner.packet_engine.weekly_learned == [] and MR.load_weekly_counters()[600002] == 60_000_002


def _runner_inside(instance):
    runner = MR.Runner()
    session, engine = CombatSession(), _engine()
    session.pvp = False
    _inside(engine, instance)
    engine.local_player_id, engine.names, engine.known_players = 5001, {5001: "Me"}, {5001}
    engine.weekly_counters[instance] = COUNTER
    runner.session, runner.packet_engine = session, engine
    session.observe(engine, [], timestamp_ms=int(time.time() * 1000))
    return runner


def test_the_overlay_reading_names_the_dungeon_and_its_runs_left(home):
    snap = _runner_inside(VAKRON).status()["snapshot"]
    assert snap["weekly_runs"]["regular"] == 14 and snap["weekly_runs"]["counter"] == COUNTER
    assert (snap["weekly_runs"]["zone"], snap["weekly_runs"]["difficulty"]) == ("Vakron Sky Island", "hard")


def test_a_setting_on_by_default_shows_or_hides_it(home):
    assert server.ui_settings()["overlay_show_weekly_runs"] is True
    assert _clean({"overlay_show_weekly_runs": False}) == {"overlay_show_weekly_runs": False}
    with pytest.raises(ValueError):
        _clean({"overlay_show_weekly_runs": "no"})
    write_user_json({**server.ui_settings(), "overlay_show_weekly_runs": False}, "ui.json")
    assert "weekly_runs" not in _runner_inside(VAKRON).status()["snapshot"]


def test_the_overlay_and_the_live_meter_page_show_the_line():
    static = os.path.join(os.path.dirname(__file__), "..", "aion2calc", "app", "static")
    read = lambda name: open(os.path.join(static, name), encoding="utf-8").read()
    overlay, html, meter = read("overlay.js"), read("overlay.html"), read(os.path.join("pages", "meter.js"))
    assert 'id="ovweekly"' in html and "snap.weekly_runs" in overlay and ".ovrunicon{" in read("overlay.css")
    assert overlay.count('"#ovweekly"') == 4 and '$("#ovweekly").hidden=true' in overlay   # hidden with the rest
    assert "weeklyLine(snap.weekly_runs)" in meter and 'class="runicon"' in meter
    assert "p.odyle .runicon {" in read("app.css")
    assert 'id="ov-weekly"' in read(os.path.join("pages", "settings.js"))
