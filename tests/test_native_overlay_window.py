"""The native overlay's window on the desktop (0.2.418): ``WindowHost`` does for the native overlay what the web
overlay's host does around its page (``aion2calc/overlay.py``): it shows and hides with the game window, opens where
it was last put by the monitor layout, follows the game window with remember position off, and passes clicks through
to the game but over its own buttons, hover to interact opening it. A stand-in for the Windows backend
(``native_overlay``) plays the desktop, off screen.
"""
import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui.overlay import MeterOverlay  # noqa: E402
from aion2calc.overlay import _GameWindow  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp  # noqa: E402

GAME = _GameWindow(hwnd=99, bounds=(100, 50, 1600, 900))


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


class Desktop:
    """The Windows backend's part the overlay uses: the game window, the overlay's place in the screen's pixels,
    the monitors, the cursor over the overlay and click-through, as a desktop of one 1920 x 1080 monitor."""

    def __init__(self, game=GAME):
        self.game, self.foreground, self.cursor = game, game.hwnd if game else 0, None
        self.places, self.moves, self.passing = {}, [], []
        self.screens = [(0, 0, 1920, 1080)]
        self.user32 = SimpleNamespace(GetForegroundWindow=lambda: self.foreground)

    def game_window(self):
        return self.game

    def rect(self, hwnd):
        return (*self.places.get(hwnd, (0, 0)), 340, 200)

    def move(self, hwnd, x, y):
        self.places[hwnd] = (x, y)
        self.moves.append((x, y))

    def monitors(self):
        return list(self.screens)

    def virtual_screen(self):
        return (0, 0, 1920, 1080)

    def cursor_in_client(self, hwnd):
        return self.cursor

    def set_click_through(self, hwnd, enabled):
        self.passing.append(enabled)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _overlay(desktop, api=None, **ui):
    window = MeterOverlay(api, win32=desktop)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(fight())
    window.show()
    return window


def test_the_overlay_shows_and_hides_with_the_game_window(qapp):
    desktop = Desktop()
    window = _overlay(desktop)
    host = window.host
    assert host.native and not window.host._follow.isActive()                 # it starts with the app's start()
    window.host.start()
    assert window.host._follow.isActive() and window.host._follow.interval() == 250
    host._follow_game()
    assert window.isVisible()
    desktop.game = None                                                        # the game closed
    host._follow_game()
    assert not window.isVisible()
    desktop.game = _GameWindow(hwnd=99, bounds=GAME.bounds, minimized=True)
    host._follow_game()
    assert not window.isVisible()
    desktop.game = GAME
    host._follow_game()
    assert window.isVisible()
    desktop.foreground = 5                                                     # another program has the focus
    host._follow_game()
    assert window.isVisible()                                                  # always visible, by default
    window.ui["overlay_always_visible"] = False
    host._follow_game()
    assert not window.isVisible()
    desktop.foreground = window.host.hwnd()                                    # the overlay itself has it
    host._follow_game()
    assert window.isVisible()
    desktop.game = None
    window.toggle_lock()                                                       # locked for a screenshot: it stays
    host._follow_game()
    assert window.isVisible()
    window.toggle_lock()
    host.follow_tick()
    assert not window.isVisible()


def test_it_opens_where_it_was_put_by_the_monitor_layout(qapp):
    desktop = Desktop()
    window = _overlay(desktop, overlay_pos_x=300, overlay_pos_y=200, overlay_pos_layout=[[0, 0, 1920, 1080]])
    assert desktop.moves == [(300, 200)] and window.host.placed
    moved = Desktop()                                                          # its second monitor is gone: the
    _overlay(moved, overlay_pos_x=2000, overlay_pos_y=100,                     # same place on a monitor its size
             overlay_pos_layout=[[0, 0, 1920, 1080], [1920, 0, 1920, 1080]])
    assert moved.moves == [(80, 100)]
    api = FakeApp(fight())
    lost = Desktop()
    window = _overlay(lost, api, overlay_pos_x=5000, overlay_pos_y=5000)       # off every monitor: not there
    assert lost.moves == [] and not window.host.placed
    window.host._follow_game()                                                 # by the game window's corner
    assert lost.moves == [(116, 98)] and window.host.placed
    assert ("POST", "/api/ui", {"overlay_pos_x": 116, "overlay_pos_y": 98,
                                "overlay_pos_layout": [[0, 0, 1920, 1080]]}) in api.calls
    lost.game = _GameWindow(hwnd=99, bounds=(400, 300, 1600, 900))
    window.host._follow_game()
    assert lost.moves == [(116, 98)]                                           # kept: it does not follow the game


def test_with_remember_position_off_it_follows_the_game_window(qapp):
    desktop = Desktop()
    window = _overlay(desktop, overlay_remember_position=False, overlay_pos_x=300, overlay_pos_y=200)
    host = window.host
    assert desktop.moves == []                                                 # no remembered place
    host._follow_game()
    assert desktop.moves == [(116, 98)]                                        # the game's corner
    desktop.game = _GameWindow(hwnd=99, bounds=(300, 150, 1600, 900))          # the game window moved
    host._follow_game()
    assert desktop.moves[-1] == (316, 198)                                     # and the overlay with it
    window._drag = object()                                                    # the player moves the overlay
    desktop.game = _GameWindow(hwnd=99, bounds=(310, 150, 1600, 900))
    host._follow_game()
    assert desktop.moves[-1] == (316, 198)
    window._drag = None
    window.ui.update(overlay_snap_edge=True)
    desktop.places[host.hwnd()] = (1550, 160)                                  # near the game's right edge
    host._follow_game()
    assert desktop.moves[-1] == (310 + 1600 - 340, 150)                        # flush with it, and its top
    window.ui.update(overlay_snap_edge=False, overlay_expand_up=True)
    host._follow_game()
    assert desktop.moves[-1][1] == 150 + 900 - 200 - 48                        # grows upward from near the bottom


def test_click_through_keeps_the_overlays_buttons_live(qapp):
    desktop = Desktop()
    window = _overlay(desktop, overlay_click_through=True)
    host = window.host
    assert window.click_through and not window.windowFlags() & Qt.WindowTransparentForInput   # not the whole window
    assert host._hit.isActive() and host._hit.interval() == 33
    host._hit_test()
    assert desktop.passing == [True]                                           # the pointer elsewhere: the game's
    lock = window.tools["lock"]
    corner = lock.mapTo(window, lock.rect().center())
    ratio = window.devicePixelRatioF()
    desktop.cursor = (corner.x() * ratio, corner.y() * ratio)
    host._hit_test()
    assert desktop.passing == [True, False]                                    # over Lock: the overlay's
    row = window.rows[0]
    middle = row.mapTo(window, row.rect().center())
    desktop.cursor = (middle.x() * ratio, middle.y() * ratio)
    host._hit_test()
    assert desktop.passing == [True, False, True]                              # over a row: the game's
    host._hit_test()
    assert desktop.passing == [True, False, True]                              # set once, not every tick
    window.apply_ui({"overlay_width": 340, "overlay_click_through": False})
    assert desktop.passing[-1] is False and not host._hit.isActive()


def test_hover_to_interact_opens_the_overlay_to_clicks(qapp):
    desktop, clock = Desktop(), Clock()
    window = MeterOverlay(None, win32=desktop)
    window.host.clock = clock
    window.apply_ui({"overlay_width": 340, "overlay_click_through": True, "overlay_hover_interact": True})
    window.apply_meter(fight())
    window.show()
    host = window.host
    row = window.rows[0]
    middle = row.mapTo(window, row.rect().center())
    desktop.cursor = (middle.x(), middle.y())                                  # resting on the overlay
    host._hit_test()
    assert window.card.hover == "arming" and desktop.passing[-1] is True
    clock.now += 4.9
    host._hit_test()
    assert window.card.hover == "arming" and desktop.passing[-1] is True
    clock.now += 0.2                                                           # five seconds on it
    host._hit_test()
    assert window.card.hover == "open" and desktop.passing[-1] is False        # the whole overlay takes clicks
    assert window.card.toolTip().startswith("The overlay takes clicks")
    window.grab()                                                              # its edge paints
    desktop.cursor = None                                                      # the pointer left
    host._hit_test()
    assert window.card.hover == "off" and desktop.passing[-1] is True


def test_a_drag_keeps_the_place_with_the_monitors_it_was_put_on(qapp):
    api, desktop = FakeApp(fight()), Desktop()
    desktop.screens = [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)]
    window = _overlay(desktop, api)
    desktop.places[window.host.hwnd()] = (2100, 300)                           # the screen's pixels, not Qt's
    window.save_position()
    assert api.calls[-1] == ("POST", "/api/ui", {"overlay_pos_x": 2100, "overlay_pos_y": 300, "overlay_pos_layout": [
        [0, 0, 1920, 1080], [1920, 0, 2560, 1440]]})
    window.ui["overlay_remember_position"] = False
    window.save_position()
    assert len([call for call in api.calls if call[1] == "/api/ui"]) == 1      # not kept with it off


def test_without_the_platforms_help_the_overlay_keeps_its_own_place(qapp):
    window = MeterOverlay(None)
    assert not window.host.native
    window.apply_ui({"overlay_pos_x": 120, "overlay_pos_y": 80, "overlay_pos_layout": [[0, 0, 9, 9]]})
    assert (window.x(), window.y()) == (0, 0)                                  # saved under other monitors
    again = MeterOverlay(None)
    again.apply_ui({"overlay_pos_x": 120, "overlay_pos_y": 80})
    assert (again.x(), again.y()) == (120, 80)
    assert again.host.saved_place()["overlay_pos_layout"] == [list(s.geometry().getRect()) for s in qapp.screens()]
    again.start()
    assert not again.host._follow.isActive()                                   # no game window to follow
