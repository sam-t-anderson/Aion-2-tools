"""The native window opens where it was left (0.2.504): its size, its position, its screen and whether it was
maximized, kept in the interfaces' data a moment after each move, resize or maximize (at once as it closes, where one
is waiting), and put back as it opens; until now it opened at 1280x820 wherever Qt put it. Drawn off screen (one
800x800 screen).
"""
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from aion2calc.gui import interface, theme  # noqa: E402
from aion2calc.gui import window as native_window  # noqa: E402
from aion2calc.gui import window_place as wp  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402
from test_native_settings import FakeApp  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(monkeypatch):
    """The interfaces' data of one test (in memory: no app), its writes noted."""
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    kept = interface.store()
    kept.writes = []
    set_value = kept.setValue
    kept.setValue = lambda key, value: (kept.writes.append((key, value)), set_value(key, value))[1]
    monkeypatch.setattr(interface, "store", lambda prefix="": kept)
    yield kept
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
    theme.apply_look("dark")


def _shown(window):
    window.show()
    QCoreApplication.processEvents()
    return window


def _place_of(window) -> str:
    return bytes(window.saveGeometry().toBase64()).decode("ascii")


def test_a_window_is_put_back_where_it_was_left(qapp, store):
    window = QMainWindow()
    window.resize(500, 350)
    place = wp.WindowPlace(window, store, save_ms=10)
    assert not place.restore() and store.writes == []                        # nothing kept yet: as it is
    _shown(window)
    window.resize(560, 380)                                                  # moved about, then left
    window.move(100, 80)
    passed = _place_of(window)
    window.resize(600, 400)
    window.move(120, 90)
    settle(lambda: store.value(wp.KEY) == _place_of(window))                 # a moment after the last change
    assert {key for key, _ in store.writes} == {wp.KEY}
    assert passed not in [value for _, value in store.writes]                # not where it only passed
    again = QMainWindow()
    assert wp.WindowPlace(again, store, save_ms=10).restore()
    _shown(again)
    assert again.size().toTuple() == (600, 400) and again.pos().toTuple() == (120, 90)
    # kept only where it changed
    sent = len(store.writes)
    place.save()
    assert len(store.writes) == sent
    # maximized, and put back maximized
    window.showMaximized()
    settle(lambda: store.value(wp.KEY) == _place_of(window))
    third = QMainWindow()
    wp.WindowPlace(third, store, save_ms=10).restore()
    assert _shown(third).isMaximized()
    # a hidden window's place is not kept
    window.showNormal()
    window.hide()
    QCoreApplication.processEvents()
    sent = len(store.writes)
    place.save()
    assert len(store.writes) == sent


def test_a_place_off_the_screens_or_unreadable(qapp, store):
    window = _shown(QMainWindow())
    window.resize(400, 300)
    window.move(5000, 5000)                                                    # a screen since gone
    place = wp.WindowPlace(window, store, save_ms=10)
    place.save()
    again = QMainWindow()
    assert wp.WindowPlace(again, store).restore()
    _shown(again)
    screen = again.screen().availableGeometry()
    assert screen.contains(again.geometry().center())                         # on a screen that is there
    for kept in ("", "not a place!", "AAAA", "é", 12):
        store.setValue(wp.KEY, kept)
        other = QMainWindow()
        other.resize(321, 234)
        assert not wp.WindowPlace(other, store).restore() and other.size().toTuple() == (321, 234)


def _waited(seconds=0.05):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def test_the_apps_window_keeps_its_place(qapp, store, monkeypatch):
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)
    monkeypatch.setattr(wp, "SAVE_MS", 10)
    # without the app, or with a store that is not the app's (a test's): none kept, none put back
    for alone in (native_window.MainWindow(None), native_window.MainWindow(FakeApp())):
        _shown(alone).resize(640, 480)
        _waited()
        assert alone.place is None
    assert wp.KEY not in [key for key, _ in store.writes]
    monkeypatch.setattr(interface._shared, "api", FakeApp())                   # the store the app's, as it opens
    assert interface.connected()
    window = _shown(native_window.MainWindow(FakeApp()))
    assert window.place is not None and window.size().toTuple() == (1280, 820)  # nothing kept: as before
    settle(lambda: store.value(wp.KEY))                                        # where it opened, kept
    window.resize(700, 500)
    window.move(60, 40)
    window.close()                                                             # at once, before the moment is up
    again = _shown(native_window.MainWindow(FakeApp()))
    assert again.size().toTuple() == (700, 500) and again.pos().toTuple() == (60, 40)
    again.showMaximized()
    again.close()
    third = _shown(native_window.MainWindow(FakeApp()))
    assert third.isMaximized()
    third.showNormal()
    QCoreApplication.processEvents()
    assert third.size().toTuple() == (700, 500)                               # its size before it was maximized


def test_a_window_drawn_again_keeps_its_place(qapp, store, monkeypatch):
    """Drawn again in another language or look (``redraw``): maximized with its size from before, which it lost
    there until 0.2.504 (un-maximized, it stayed as large as the screen), and minimized where it was."""
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)
    window = native_window.MainWindow(None)
    window.resize(600, 400)
    window.move(50, 40)
    _shown(window).showMaximized()
    QCoreApplication.processEvents()
    again = window.redraw()
    QCoreApplication.processEvents()
    assert again.isMaximized()
    again.showNormal()
    QCoreApplication.processEvents()
    assert again.size().toTuple() == (600, 400) and again.pos().toTuple() == (50, 40)
    again.showMinimized()                                                      # the computer turns light or dark
    QCoreApplication.processEvents()
    third = again.redraw()
    QCoreApplication.processEvents()
    assert third.isMinimized() and third.size().toTuple() == (600, 400)
