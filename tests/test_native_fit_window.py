"""The native window's pages fit the window's width (0.2.509): a row of a log's series, tabs or choices is laid out on
as many lines as the window needs, as the web page's rows wrap, where a raid's log made the log's review (and the Live
Meter's review of the session) tens of thousands of pixels wide, off the window's right side. Off screen.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QPushButton, QScrollArea, QWidget  # noqa: E402

from aion2calc.gui import interface, theme  # noqa: E402
from aion2calc.gui import window as native_window  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_combat import FakeApp, ShareServer  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

CLASSES = ("sorcerer", "cleric", "templar", "ranger", "assassin", "gladiator", "chanter", "spiritmaster")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _raid(players: int = 48) -> dict:
    """A raid's log: each player strikes the boss, is struck and heals, so that the graph has three series for each."""
    people = [{"id": f"p{i}", "name": f"Raider{i:02d}", "class": CLASSES[i % len(CLASSES)]} for i in range(players)]
    events = []
    for i, person in enumerate(people):
        events += [{"kind": "damage", "t": 0.5 + i * 0.1, "source": person["id"], "target": "b1", "amount": 1000 + i,
                    "skill": "Flame Burst"},
                   {"kind": "damage", "t": 1.0 + i * 0.1, "source": "b1", "target": person["id"], "amount": 500,
                    "skill": "Frost Breath"},
                   {"kind": "heal", "t": 1.5 + i * 0.1, "source": person["id"], "target": person["id"], "amount": 300,
                    "skill": "Heal"}]
    return {"meta": {"title": "Raid night"}, "players": people,
            "segments": [{"label": "Ice Queen", "boss": "Ice Queen", "duration": 120,
                          "entities": [{"id": "b1", "name": "Ice Queen", "kind": "enemy", "is_boss": True}],
                          "events": events}]}


def _wider(root: QWidget, within: QWidget) -> list[str]:
    """What is wider than the room it is shown in: a scroll area scrolling sideways, or a widget past its parent's
    right side."""
    found = []
    for area in root.findChildren(QAbstractScrollArea):
        if area.isVisibleTo(within) and area.horizontalScrollBar().maximum() > 0 and area.objectName() != "crTimeline":
            found.append(f"{type(area).__name__}#{area.objectName()} scrolls {area.horizontalScrollBar().maximum()} px")
    return found


def test_a_raids_log_review_fits_the_window(qapp):
    from aion2calc.gui.combat_page import CombatPage
    app = FakeApp()
    app.log_server.review_log = _raid()
    page = CombatPage(app, identity_call=ShareServer())
    page.resize(1000, 900)
    page.show()
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: any(b.text() == "Show all series" for b in view.findChildren(QPushButton) if b.isVisibleTo(view)))
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        QCoreApplication.processEvents()
    row = next(b for b in view.findChildren(QPushButton) if b.text() == "Show all series").parentWidget()
    series = [b for b in row.findChildren(QPushButton) if b.isVisibleTo(view)]
    assert len(series) > 100                                       # a button for each raider's damage, healing, hits
    assert all(b.geometry().right() <= row.width() for b in series)
    assert len({b.y() for b in series}) > 10                       # on many lines, not one 20,000 px long
    scroll = page.scroll
    assert scroll.horizontalScrollBar().maximum() == 0 and scroll.widget().width() <= scroll.viewport().width()
    assert _wider(page, page) == []


@pytest.mark.parametrize("width", [1280, 1100])
def test_every_page_fits_the_window(qapp, monkeypatch, width):
    """Every page of a window as large as it opens (1,280 by 820), or narrower, without its contents scrolling
    sideways: the Raid Planner's map left its page 16 pixels wider than the window, and Combat Logs' filters 60."""
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    window = native_window.MainWindow(None)
    window.resize(width, 820)
    window.show()
    QCoreApplication.processEvents()
    wider = {}
    for key in window.page_index:
        window.show_page(key)
        for _ in range(3):
            QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)
            QCoreApplication.processEvents()
        found = _wider(window.page(key), window)
        if found:
            wider[key] = found
    assert window.width() == width and wider == {}
    theme.apply_look("dark")


def test_the_community_logs_filters_wrap(qapp):
    """Combat Logs' community filters, eight choices and Clear: on as many lines as the page's width needs."""
    from aion2calc.gui.combat_page import CombatPage
    page = CombatPage(FakeApp(), identity_call=ShareServer())
    page.resize(800, 900)
    page.show()
    page.show_view("community")
    settle(lambda: any(b.text() == "Clear" for b in page.findChildren(QPushButton) if b.isVisibleTo(page)))
    QCoreApplication.processEvents()
    clear = next(b for b in page.findChildren(QPushButton) if b.text() == "Clear" and b.isVisibleTo(page))
    row = clear.parentWidget().parentWidget()                      # Clear, in its field, in the filters' row
    fields = [w for w in row.findChildren(QWidget, options=__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.FindDirectChildrenOnly)
              if w.isVisibleTo(page)]
    assert len(fields) >= 8 and len({w.y() for w in fields}) > 1
    assert all(w.geometry().right() <= row.width() for w in fields)
    scroll = next(s for s in page.findChildren(QScrollArea) if s.isVisibleTo(page))
    assert scroll.horizontalScrollBar().maximum() == 0
