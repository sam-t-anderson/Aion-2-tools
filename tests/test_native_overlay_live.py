"""The native overlay's fourth part (0.2.417): what the web overlay shows of the fight beside the rows.

The fight's mark, the ping, the identity line, the live graph and the player panel's sparkline, the rows' live tick
between readings, the actor id beside a name two players share, the community standing, the target's others struck
in the same instant, and the pace the overlay reads the meter at, on the browser tests' meter answers, off screen.
"""
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui.overlay import MeterOverlay, identity_line, ping_texts  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, laid_out_apart  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _overlay(meter=None, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _rows(window):
    return [row for row in window.rows if not row.isHidden()]


def _reading(duration, paused=False, **snapshot):
    """A new reading of the fight (a new answer, as each poll brings) at ``duration`` seconds."""
    meter = fight()
    meter["snapshot"].update(duration=duration, recorded_duration=duration, paused=paused, **snapshot)
    return meter


def test_the_ping_pill_and_its_whole_reading():
    assert ping_texts(None) == ("Ping —", "Ping: no recorded samples")
    assert ping_texts({"current": 45.4, "avg": 52.5, "min": 31, "max": 120}) == (
        "Ping 45 ms", "Ping 45 ms · Avg 53 ms · Min 31 / Max 120 ms")              # halves up, as toFixed


def test_the_ping_and_the_identity_line_on_the_overlay(qapp):
    window = _overlay()
    assert window.ping.text() == "Ping —" and window.ping.toolTip().startswith("Ping: no recorded samples — Passive")
    assert window.identity.isHidden()                                          # you are named: all is well
    meter = fight()
    meter["snapshot"]["ping"] = {"current": 45, "avg": 52, "min": 31, "max": 120}
    meter["snapshot"]["identity_status"].update(unnamed_actors=2, linked_pets=1)
    window.apply_meter(meter)
    assert window.ping.text() == "Ping 45 ms"
    assert window.identity.text() == ("Self identified · 2 unnamed actors · 1 linked pets. Grouping needs recorded "
                                      "owner links.") and not window.identity.isHidden()
    window.apply_ui({"overlay_width": 340, "overlay_only_in_combat": True})
    window.apply_meter({**meter, "running": False})
    assert window.identity.isHidden() and window.ping.isHidden()               # collapsed between fights


def test_the_identity_line_reads_as_the_web_overlays():
    meter = fight()
    snap, players = meter["snapshot"], meter["snapshot"]["players"]
    ranked = sorted(players, key=lambda p: p["dps"], reverse=True)
    assert identity_line(snap, players, players, ranked, False, True) == ("You: Nyxara · #2 of 3 · CP 123.46K", True)
    assert identity_line(snap, players, players, ranked, False, False)[0] == "You: Nyxara · #2 of 3"
    snap["identity_status"]["self_identified"] = False
    text, fine = identity_line(snap, players, players, ranked, True, True)
    assert not fine and text == ("Self identity not received — teleport or change instances to refresh it · 0 unnamed "
                                 "actors · 0 linked pets. Grouping needs recorded owner links. Matching names have "
                                 "separate combat actor IDs; names alone do not establish shared identity or "
                                 "ownership.")
    snap["identity_status"].update(self_identified=True, local_name="Player #7")
    players[1]["name"], players[2]["inferred_identity"] = "Player #7", True
    text, fine = identity_line(snap, players, players, ranked, False, True)
    assert fine and text == ("You · #2 of 3 · your name comes with the next zone load Combined a player’s "
                             "re-registered actor IDs (matched by name, class and timing).")
    assert identity_line({}, [], [], [], False, True) == ("", False)


def test_the_fights_mark_says_whether_it_runs(qapp):
    window = _overlay()
    assert not window.mark.isHidden() and "#5ee04a" in window.mark.styleSheet()   # green while it runs
    window.apply_meter(_reading(75.0, paused=True))
    assert "#e3b35a" in window.mark.styleSheet()                                 # amber while the clock is paused
    stopped = fight()
    stopped["running"] = False
    window.apply_meter(stopped)
    assert "#6b7380" in window.mark.styleSheet()
    stopped["snapshot"]["battle_over"] = True
    window.apply_meter(stopped)
    assert window.mark.isHidden()


def test_the_live_graph_follows_the_fight(qapp):
    window = _overlay()
    for second in (1.0, 2.0):
        window.apply_meter(_reading(second))
    assert window.graph.isHidden() and window._graph == []                      # off by default
    window.apply_ui({"overlay_width": 340, "overlay_dps_graph": True})
    for second in (3.0, 4.0, 5.0):
        window.apply_meter(_reading(second))
    assert not window.graph.isHidden() and len(window._graph) == 3
    assert window.graph.label == "DPS · now 45.70K · peak 45.70K"
    window.apply_meter(window.answer)                                           # the same reading drawn again
    window.apply_ui({"overlay_width": 340, "overlay_dps_graph": True})
    assert len(window._graph) == 3
    window.apply_meter(_reading(6.0, paused=True))                              # a paused fight adds nothing
    assert len(window._graph) == 3
    window.set_metric("hps")
    assert window.graph.label == "HPS · now 0 · peak 1"
    window.set_metric("dps")
    window.toggle_detail("0")
    assert not window.panel.spark.isHidden() and window.panel.spark.series == [23400.0] * 3
    assert window.panel.spark.color.name() == "#3a86c8"                         # the sorcerer's colour
    window.grab()                                                               # the graphs paint
    window.apply_meter(_reading(2.0))                                           # the clock went back: a new fight
    assert len(window._graph) == 1 and window.graph.isHidden()
    window._replied("split", {"ok": True})                                      # New starts it clean too
    assert window._graph == [] and window._player_hist == {}
    window.apply_ui({"overlay_width": 340})
    assert window.graph.isHidden() and window.panel.spark.isHidden()


def _value(row) -> float:
    """A row's rate as a number (its text is whole digits, grouped)."""
    return float(row.rate.removesuffix("/s").replace(",", ""))


def test_live_ticking_rates_head_for_the_fights_elapsing_time(qapp):
    window = _overlay(overlay_dps_interpolate=True, overlay_interpolate_ms=100)
    assert window._tick_timer.isActive() and window._tick_timer.interval() == 100
    first = _rows(window)[0]
    assert first.rate == "23,400/s"                                             # the reading's own rate at first
    window._render_at = time.monotonic() - 5                                    # five seconds without a reading
    window._live_tick()
    # Seraphel: 1,755,000 damage at 23,400/s, five seconds on: 1,755,000 / (75 + 5) s. In whole digits the rate
    # moves with the milliseconds the test takes, so it is read within two.
    assert _value(first) == pytest.approx(21937.5, abs=2) and first.fill == pytest.approx(21937.5 / 23400, abs=1e-4)
    window._render_at = time.monotonic() - 10
    window._live_tick()
    assert _value(first) == pytest.approx(21421.3, abs=2)                        # 40% of the way to 20,647
    window.apply_meter(fight())                                                 # a reading: it eases from there
    assert _value(first) == pytest.approx(21421.3, abs=2)
    window._live_tick()
    assert _value(first) == pytest.approx(22212.8, abs=2)                        # 40% of the way back to 23,400
    window.apply_meter(_reading(75.0, paused=True))                             # paused: the time stops
    for _ in range(30):
        window._live_tick()
    assert first.rate == "23,400/s"
    window.toggle_lock()
    window._shown_rates[first.key] = 1.0
    window._live_tick()
    assert first.rate == "23,400/s"                                             # locked: it holds
    window.toggle_lock()
    window.apply_ui({"overlay_width": 340, "overlay_dps_interpolate": True, "performance_mode": True})
    assert not window._tick_timer.isActive() and window._shown_rates == {}      # performance mode holds still
    assert window._cooldown_timer.interval() == 500


def test_shared_names_carry_their_actor_id_and_the_community_standing_shows(qapp):
    meter = fight()
    players = meter["snapshot"]["players"]
    players.append(dict(players[2], id="9", key="9", dps=5000, damage=375_000))
    players[0]["community_rank"] = {"text": "Top 5%"}
    window = _overlay(meter, overlay_show_combat_power=False)
    labels = [row.label() for row in _rows(window)]
    assert labels == ["Seraphel", "Nyxara", "Velmira  #2", "Velmira  #9"]
    assert window.identity.text().startswith("You: Nyxara") and "Matching names" in window.identity.text()
    window.apply_ui({"overlay_width": 340, "overlay_show_combat_power": False, "overlay_show_community_rank": True})
    assert _rows(window)[0].segments() == [("Seraphel", "name"), ("Top 5%", "crank")]
    window.apply_ui({"overlay_width": 340, "overlay_name_mode": "number", "overlay_show_combat_power": False})
    assert [row.label() for row in _rows(window)][2:] == ["P?", "P?"]           # no names, no actor ids
    window.grab()


def test_the_target_names_the_others_struck_in_the_same_instant(qapp):
    meter = fight()
    meter["snapshot"]["current_target"]["also_targets"] = ["Lesser Atiel", "Spawn"]
    window = _overlay(meter)
    assert window.target_text == "Atiel +2 (Lesser Atiel, Spawn)"
    assert "(and 2 more struck in the same instant)" in window.target.toolTip()
    assert window.target.toolTip().endswith("\nAlso being hit right now: Lesser Atiel, Spawn")


def test_the_meter_is_read_less_often_out_of_a_fight_and_in_performance_mode(qapp):
    api = FakeApp(fight())
    window = _overlay(api=api)
    assert window._meter_poller._timer.interval() == 500
    stopped = fight()
    stopped["running"] = False
    window.apply_meter(stopped)
    assert window._meter_poller._timer.interval() == 1000
    window.apply_ui({"overlay_width": 340, "performance_mode": True})
    assert window._meter_poller._timer.interval() == 2000
    window.apply_meter(fight())
    assert window._meter_poller._timer.interval() == 1000


def test_a_tall_overlay_keeps_each_part_in_its_own_place(qapp):
    """The graph, a wrapped identity line and the player panel at once: the window takes the height they need,
    which adjustSize kept to two thirds of the screen."""
    window = _overlay(overlay_dps_graph=True)
    for second in range(30, 40):
        meter = _reading(float(second))
        meter["snapshot"]["players"].append(dict(meter["snapshot"]["players"][2], id="9", key="9", dps=5000,
                                                 damage=375_000))
        window.apply_meter(meter)
    window.show()
    window.toggle_detail("0")
    assert not window.identity.isHidden() and window.identity.height() > 2 * window.identity.fontMetrics().height()
    assert not window.graph.isHidden() and not window.panel_scroll.isHidden()
    assert window.height() > window.screen().availableGeometry().height() * 2 // 3
    laid_out_apart(window)
