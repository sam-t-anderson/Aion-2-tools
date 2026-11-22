"""The overlay's companion windows, natively (0.2.497): the Party-DPS window and the Hidden Cube radar's window as
small Qt windows of their own (``aion2calc/gui/companions.py``), where until now each was the overlay page in
pywebview (``overlay?view=party``, ``?view=radar``).

The words are the web overlay's (overlay.js ``renderParty``, ``radarText``, ``placeBlip``); the windows are drawn off
screen over a stand-in for the app's local API, which notes each request and answers it.
"""
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.app import overlay_launch  # noqa: E402
from aion2calc import gui  # noqa: E402
from aion2calc.gui import companions as cp  # noqa: E402
from aion2calc.gui import overlay as native_overlay  # noqa: E402
from aion2calc.gui.interface import OVERLAY, InterfaceStore, _Shared  # noqa: E402
from aion2calc.overlay import _GameWindow  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, settle  # noqa: E402
from test_native_overlay_window import Desktop  # noqa: E402

HEARD = {"supported": True, "ready": True, "heard": True, "since": 0.3, "proximity": 0.62, "angle": 40, "mirror": None,
         "direction": "ahead right", "trend": "louder"}


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


class Radar(FakeApp):
    """The app's local API with the radar's reading (``/api/radar``) too."""

    def __init__(self, meter=None, radar=None):
        super().__init__(meter)
        self.radar = HEARD if radar is None else radar

    def _answer(self, method, path, payload):
        if path == "/api/radar":
            self.calls.append((method, path, payload))
            return self.radar
        return super()._answer(method, path, payload)


def _store():
    return InterfaceStore(OVERLAY, shared=_Shared())             # the overlay's own values, in this test alone


def _party(meter=None, api=None, store=None, **ui):
    window = cp.PartyWindow(api, store=store)
    window.apply_ui({"overlay_width": 340, "overlay_show_events": False, **ui})
    window.apply_meter(fight() if meter is None else meter)
    window.show()
    return window


def _radar(reading=None, api=None, store=None, **ui):
    window = cp.RadarWindow(api, store=store)
    window.apply_ui({"radar_enabled": True, **ui})
    window.show_radar(HEARD if reading is None else reading)
    window.show()
    return window


def _shown(window, widget):
    return widget.isVisibleTo(window)


# ---------------------------------------------------------------------------------------------- the words
def test_the_party_windows_figures_and_status():
    meter = fight()
    assert cp.party_stats(meter) == [("Party DPS", "45.70K/s"), ("Party HPS", "0/s"), ("Damage taken/s", "0/s"),
                                     ("Total damage", "3.43M")]
    assert cp.party_status(meter) == "Party · Atiel · 3 players"
    meter["targets"] = ["boss"]
    assert cp.party_status(meter) == "Party · Atiel · 3 players · Boss damage only"
    odd = {"running": True, "snapshot": {"boss": "", "players": [{"dps": "12", "hps": None, "dtps": "x",
                                                                  "damage": 1500}, "not a player"]}}
    assert cp.party_stats(odd) == [("Party DPS", "12/s"), ("Party HPS", "0/s"), ("Damage taken/s", "0/s"),
                                   ("Total damage", "1.50K")]          # ``Number(x) || 0``, a row that is not one skipped
    assert cp.party_status(odd) == "Party · recording · 1 players"
    for idle in ({"running": False, "snapshot": {"players": []}}, {}, None, {"running": True, "snapshot": {"players": 3}}):
        assert cp.party_stats(idle) == []
    assert cp.party_waiting({"running": True}) == "Waiting for combat data…"
    assert cp.party_waiting({"running": False}) == cp.party_waiting(None) == "No fight yet. Start the meter in the app."
    assert cp.party_status({"running": False, "snapshot": {"boss": 7, "players": []}}) == "Party · 7 · 0 players"
    assert cp.party_status(None) == "Party · idle · 0 players"


def test_the_radars_line_says_what_it_does_and_where_the_cube_is():
    rt = cp.radar_text
    assert rt({"learning": {"kind": "background", "phase": "countdown", "seconds": 2.1}}) == \
        "Learning the background in 3 s: switch to the game"
    assert rt({"learning": {"kind": "cube", "facing": "behind", "phase": "listening", "seconds": 4}}) == \
        "Listening to the cube's sound behind you… 4 s"
    assert rt({"learning": {"kind": "other", "phase": "listening", "seconds": 0.2}}) == \
        "Listening to a sound that is not a cube… 1 s"
    assert rt({"learning": {"kind": "cube", "phase": "countdown", "seconds": 1}}) == \
        "Learning the cube's sound in 1 s: switch to the game"
    assert rt({"supported": True, "last_learn": {"message": "Learned the background"}, "last_learn_s": 2.5}) == \
        "Learned the background"                                         # a learn just finished, for 6 s
    assert rt({"supported": False, "last_learn": {"message": "x"}, "last_learn_s": 6}) == "Hidden Cube radar: Windows only"
    assert rt({}) == rt(None) == "Hidden Cube radar: Windows only"
    assert rt({"supported": True, "error": "no audio device"}) == "Hidden Cube radar: no audio device"
    assert rt({"supported": True, "ready": False}) == "Hidden Cube radar: teach it the cube's sound in Settings → Overlay"
    assert rt({"supported": True, "ready": True, "heard": False, "since": None}) == "Listening for a Hidden Cube…"
    assert rt({"supported": True, "ready": True, "heard": False, "since": 12.5}) == \
        "Listening for a Hidden Cube… last heard 13 s ago"
    assert rt({"supported": True, "ready": True, "heard": False, "since": 61}) == "Listening for a Hidden Cube…"
    assert rt(HEARD) == "Hidden Cube ahead right · close · getting closer"
    for proximity, near in ((0.8, "right here"), (0.79, "close"), (0.5, "close"), (0.25, "nearby"), (0.1, "far"),
                            (None, "far")):
        assert rt({**HEARD, "proximity": proximity, "trend": None}) == f"Hidden Cube ahead right · {near}"
    assert rt({**HEARD, "direction": None, "trend": "quieter"}) == "Hidden Cube nearby · close · moving away"
    assert rt({**HEARD, "trend": "steady"}) == "Hidden Cube ahead right · close"


def test_the_radars_blips_sit_where_the_cube_is_heard():
    assert cp.blip_place(0, 1) == (60.0, 54.0)                           # ahead and loud: just above you
    assert cp.blip_place(90, 0) == (116.0, 60.0)                         # to the right at the rim
    assert cp.blip_place(180, 0.5) == (60.0, 91.0)
    assert cp.blip_place(-60, 0.3) == (24.5, 39.5)
    assert cp.blip_place(None, None) == (60.0, 4.0)
    assert [cp.blip_opacity(s) for s in (0, 0.3, 1.4, 2.5, 9, None)] == [1.0, 0.88, 0.44, 0.35, 0.35, 1.0]


# ---------------------------------------------------------------------------------------------- the party window
def test_the_party_window_shows_the_partys_figures(qapp):
    window = _party()
    assert window.windowTitle() == "Aion 2 Calc Party Overlay" and window.width() == 340
    assert [(s.label_text, s.value_text) for s in window.stats if _shown(window, s)] == [
        ("Party DPS", "45.70K/s"), ("Party HPS", "0/s"), ("Damage taken/s", "0/s"), ("Total damage", "3.43M")]
    assert not _shown(window, window.muted) and not _shown(window, window.title)
    assert [b.text() for b in window.buttons.values()] == ["Lock", "New", "Copy", "Hide", "Stop"]
    stop = window.buttons["capture"]
    assert stop.on and stop.geometry().right() == window.header.width() - 1           # Start/Stop at the right end
    assert window.status_text == "Party · Atiel · 3 players"
    window.apply_meter({"running": False, "snapshot": {"players": []}})
    assert not any(_shown(window, s) for s in window.stats)
    assert _shown(window, window.muted) and window.muted.text() == "No fight yet. Start the meter in the app."
    assert window.buttons["capture"].text() == "Start" and not window.buttons["capture"].on
    small = window.height()
    window.apply_meter({"running": True, "finalizing": True, "snapshot": {"players": []}})
    assert window.muted.text() == "Waiting for combat data…"
    assert window.buttons["capture"].text() == "Stopping…" and not window.buttons["capture"].isEnabled()
    window.apply_meter(fight())
    assert window.height() > small                                      # the window fits what it shows
    window.apply_ui({"overlay_width": 600, "overlay_show_events": False, "overlay_height": 300})
    assert window.width() == 600 and window.height() >= 300
    window.apply_ui({"overlay_width": 9999})                             # out of its range: the default (``clampInt``)
    assert window.width() == 340


def test_the_party_windows_buttons_do_what_the_overlays_do(qapp):
    api = FakeApp(fight())
    window = _party(api=api)
    window.copy()
    assert QGuiApplication.clipboard().text() != "Party DPS" and api.calls == []   # nothing of its own to copy
    window.new_fight()
    settle(lambda: window.buttons["split"].text() == "New ✓")
    assert ("POST", "/api/meter", {"action": "split"}) in api.calls
    window.toggle_capture()
    settle(lambda: not window.capture_busy)
    assert ("POST", "/api/meter", {"action": "stop", "from_overlay": True}) in api.calls
    api.refuse["/api/meter"] = "The capture is busy"
    window.answer = {"running": False, "snapshot": {"players": []}}
    window.toggle_capture()
    settle(lambda: window.buttons["capture"].text() == "Error")
    assert window.buttons["capture"].toolTip() == "The capture is busy"
    assert ("POST", "/api/meter", {"action": "start", "source": "a2tools", "auto_port": True, "scope": "party"}) in api.calls
    window.hide_window()
    settle(lambda: not window.isVisible())
    assert ("POST", "/api/overlay", {"action": "hide", "view": "party"}) in api.calls


def test_lock_holds_the_party_window_and_the_hotkey_locks_it(qapp):
    window = _party()
    window._commands({"lock_seq": 3, "reload_seq": 1})                   # the first reading is the baseline
    assert not window.locked
    window._commands({"lock_seq": 4, "reload_seq": 1})                   # the screenshot hotkey
    assert window.locked and window.buttons["lock"].text() == "Unlock" and window.buttons["lock"].on
    assert window.card.locked
    window._meter_answered({"running": False, "snapshot": {"players": []}})
    assert window.stats[0].value_text == "45.70K/s"                       # held still
    window.toggle_lock()
    assert not window.locked and window.buttons["lock"].text() == "Lock" and not window.card.locked
    window._meter_answered({"running": False, "snapshot": {"players": []}})
    assert window.muted.text() == "No fight yet. Start the meter in the app."


def test_the_party_windows_graph_and_events(qapp):
    window = _party(overlay_dps_graph=True)
    assert not _shown(window, window.graph)                              # one reading is not a line yet
    meter = fight()
    meter["snapshot"]["duration"] = 80.0
    window.apply_meter(meter)
    assert _shown(window, window.graph) and window.graph.label == "DPS · now 45.70K · peak 45.70K"
    window.apply_ui({"overlay_width": 340, "overlay_show_events": False, "overlay_dps_graph": False})
    window.apply_meter(meter)
    assert not _shown(window, window.graph)
    kill = {"faction": 1, "server": 2001, "server_name": "Siel", "kills": [
        {"boss": "Grendal", "zone": "Ereshuu", "killed_at": 1000.0, "expected_at": 4000.0, "reports": 2}]}
    meter["snapshot"]["field_bosses"] = kill
    window.events_clock = lambda: 3_700_000                             # five minutes before Grendal is back
    window.apply_ui({"overlay_width": 340})
    window.apply_meter(meter)
    assert _shown(window, window.events) and "Grendal" in window.events.text() and "back in 5m" in window.events.text()
    assert window.events.toolTip().startswith("Grendal — observed kill")
    window.apply_ui({"overlay_width": 340, "overlay_show_events": False})
    assert not _shown(window, window.events)


def test_the_party_window_keeps_the_meter_overlays_opacity(qapp):
    store = _store()
    store.setValue("opacity", 0.5)
    window = _party(store=store)
    assert window.card.opacity == 0.5 and window.foot.slider.value() == 50
    window.foot.slider.setValue(80)
    assert store.value("opacity") in (0.8, "0.8") and window.card.opacity == 0.8
    radar = _radar(store=store)
    assert radar.card.opacity == native_overlay.DEFAULT_OPACITY           # the radar's is its own
    radar.foot.slider.setValue(40)
    assert float(store.value("opacity-radar")) == 0.4 and float(store.value("opacity")) == 0.8


# ---------------------------------------------------------------------------------------------- the radar window
def test_the_radar_window_shows_the_radar(qapp):
    window = _radar()
    assert window.windowTitle() == "Aion 2 Calc Radar Overlay" and window.width() == 232
    assert _shown(window, window.title) and window.title.text == "Hidden Cube radar"
    assert [b.text() for b in window.buttons.values()] == ["Lock", "Hide"]
    assert _shown(window, window.radar) and window.words.text() == "Hidden Cube ahead right · close · getting closer"
    assert window.dial.blips == [(*cp.blip_place(40, 0.62), False)] and window.dial.opacity == 0.88
    title, lock, hide = window.title.geometry(), window.buttons["lock"].geometry(), window.buttons["hide"].geometry()
    assert title.right() < lock.left() and lock.center().y() == hide.center().y() == title.center().y()
    window.show_radar({**HEARD, "mirror": -120, "angle": -60, "proximity": 0.3, "direction": "left", "trend": None,
                       "since": 1.4})
    assert window.dial.blips == [(24.5, 39.5, True), (24.5, 80.5, True)] and window.words.text() == "Hidden Cube left · nearby"
    window.show_radar({"supported": True, "ready": True, "heard": False, "learning": {"kind": "cube", "phase":
                                                                                    "countdown", "seconds": 2.3}})
    assert window.dial.blips == [] and window.words.text() == "Learning the cube's sound in 3 s: switch to the game"
    window.apply_ui({"radar_enabled": False})                            # the radar off: nothing of it shows
    assert not _shown(window, window.radar)


def test_the_radar_window_reads_the_radar_while_it_is_on(qapp):
    api = Radar()
    window = cp.RadarWindow(api)
    window.show()
    window.apply_ui({"radar_enabled": False})
    assert not window._radar_timer.isActive() and api.calls == []
    window.apply_ui({"radar_enabled": True})
    assert window._radar_timer.isActive() and window._radar_timer.interval() == 300
    settle(lambda: window.reading is not None)
    assert ("GET", "/api/radar", None) in api.calls and _shown(window, window.radar)
    window.toggle_lock()                                                 # locked: it holds still
    asked = len(api.calls)
    window.poll_radar()
    assert len(api.calls) == asked
    window.toggle_lock()
    settle(lambda: len(api.calls) > asked)
    window.hide_window()
    settle(lambda: not window.isVisible())
    assert ("POST", "/api/overlay", {"action": "hide", "view": "radar"}) in api.calls


def test_the_title_gives_way_rather_than_wrap_lock_and_hide(qapp):
    window = _radar(overlay_font_scale=160)                              # as test_browser_overlay.py's
    title = window.title
    assert title.shown().endswith("…") and title.shown() != title.text
    middles = {w.geometry().center().y() for w in (title, window.buttons["lock"], window.buttons["hide"])}
    assert len(middles) == 1


# ---------------------------------------------------------------------------------------------- their place and look
def test_each_window_keeps_its_own_place(qapp):
    api, desktop = Radar(fight()), Desktop()
    desktop.screens = [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)]
    for kind, make in (("party", cp.PartyWindow), ("radar", cp.RadarWindow)):
        window = make(api, win32=desktop)
        window.apply_ui({"overlay_pos_x": 5, "overlay_pos_y": 5, f"overlay_{kind}_pos_x": 2100, f"overlay_{kind}_pos_y": 300,
                         f"overlay_{kind}_pos_layout": [[0, 0, 1920, 1080], [1920, 0, 2560, 1440]]})
        assert desktop.places[window.host.hwnd()] == (2100, 300)          # its own, not the meter overlay's
        desktop.places[window.host.hwnd()] = (2200, 320)
        window.save_position()
        assert api.calls[-1] == ("POST", "/api/ui", {f"overlay_{kind}_pos_x": 2200, f"overlay_{kind}_pos_y": 320,
                                                     f"overlay_{kind}_pos_layout": [[0, 0, 1920, 1080],
                                                                                    [1920, 0, 2560, 1440]]})
    desktop = Desktop(_GameWindow(hwnd=99, bounds=(100, 50, 1600, 900)))
    window = cp.RadarWindow(None, win32=desktop)
    window.apply_ui({"radar_enabled": True})
    window.host._follow_game()                                          # nothing kept: by the game window's corner
    assert desktop.moves == [(116, 98)]
    window.ui["overlay_always_visible"] = False
    desktop.foreground = 5
    window.host._follow_game()
    assert not window.isVisible()                                       # with the game, as the meter overlay


def test_click_through_and_hover_follow_the_overlays_settings(qapp):
    desktop = Desktop()
    window = cp.PartyWindow(None, win32=desktop)
    window.apply_ui({"overlay_click_through": True, "overlay_hover_interact": True})
    assert window.click_through and window.host._hit.isActive()
    desktop.cursor = (40, 15)                                            # over Lock
    window.host._hit_test()
    assert desktop.passing[-1] is False
    desktop.cursor = (200, 80)                                           # over the figures: the game's
    window.host._hit_test()
    assert desktop.passing[-1] is True
    window.apply_ui({"overlay_click_through": False})
    assert not window.host._hit.isActive() and desktop.passing[-1] is False


def test_the_windows_take_the_overlays_look(qapp):
    window = _party(overlay_text_colors={"header": "#ff0000", "rate": "#00ff00"}, overlay_font_scale=130)
    assert window.stats[0].value.colour == "#00ff00" and window.stats[0].value.font_.pixelSize() == round(12 * 1.3 * 1.15)
    assert window.stats[0].label.font_.pixelSize() == round(12 * 1.3) and window.stats[0].label.colour == "#9aa3b5"
    assert window.buttons["lock"].header_colour == "#ff0000"
    assert window.buttons["lock"].words_font().pointSizeF() == 10.5 * 0.75   # the buttons keep their own size
    radar = _radar(overlay_text_colors={"header": "#ff0000", "label": "#00ffff"})
    assert radar.title.colour == "#ff0000" and "#00ffff" in radar.styleSheet()
    window.apply_ui({"overlay_bg_mode": "none", "overlay_text_outline": True})
    assert window.card.mode == "none" and not window.foot.line
    assert window._effects[window.foot.label].shadow == cp.BARE_SHADOW   # over the game, a shadow under its words
    assert window.title.shadow == cp.BARE_SHADOW
    window.apply_ui({"overlay_bg_mode": "top"})
    assert window.card.mode == "top" and window.card.rows_part is window.content and window.title.shadow is None
    window.apply_ui({"overlay_text_retro": True, "performance_mode": True})   # held still: the sheen at its start
    assert window.stats[0].value.sheen == 0.0 and window.buttons["lock"].sheen == 0.0
    assert not window._anim_timer.isActive()
    window.apply_ui({"overlay_color_cycle": True})
    if not native_overlay.reduced_motion():
        assert window._anim_timer.isActive()
        window._paint_moment(3.0)
        assert window.dot.seconds == 3.0 and window.buttons["capture"].seconds == 3.0


# ---------------------------------------------------------------------------------------------- opening them
def test_the_app_opens_the_party_and_radar_windows_natively(monkeypatch):
    spawned = []
    monkeypatch.setattr(gui, "spawn", lambda kind, url, parent_pid=None: spawned.append((kind, url)) or object())
    monkeypatch.setattr(gui, "enabled", lambda ui=None: True)
    monkeypatch.setattr(overlay_launch, "_webview", lambda: False)
    for view in ("party", "radar"):
        overlay_launch._spawn(f"http://127.0.0.1:8765/overlay?view={view}")
        assert spawned[-1] == ("overlay", f"http://127.0.0.1:8765/overlay?view={view}")
    with pytest.raises(OSError):                                         # the player cards window is still a page
        overlay_launch._spawn("http://127.0.0.1:8765/overlay?view=players")
    assert overlay_launch._view("http://x/overlay") == "meter" and overlay_launch._view("http://x/overlay?view=pets") == "pets"
    ran = []
    monkeypatch.setattr(cp, "main", lambda argv: ran.append(argv) or 7)
    assert native_overlay.main(["--url", "http://127.0.0.1:8765/overlay?view=radar"]) == 7
    assert ran == [["--url", "http://127.0.0.1:8765/overlay?view=radar"]]
    assert cp.view_of("http://x/overlay?view=party") == "party" and cp.view_of("http://x/overlay?view=players") == "meter"


def test_a_companion_window_ends_with_the_app(qapp, monkeypatch):
    class Gone:
        def watched(self):
            return True

        def alive(self):
            return False

    quits = []
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(1))
    window = cp.RadarWindow(None, parent_process=Gone())
    assert window._parent_timer.isActive()
    window._check_parent()
    assert quits == [1]
    time.sleep(0)
