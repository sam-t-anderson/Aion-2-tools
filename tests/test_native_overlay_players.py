"""The player cards window of a PvP match, natively (0.2.499): the meter overlay's compact window holding a card for
every player of the match (``aion2calc/gui/players_window.py``), where until now it was the overlay page in pywebview
(``overlay?view=players``). The matches are ``tests/browser/test_browser_overlay_arena.py``'s, which the web window's
own tests draw; the window is drawn off screen.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import companions as cp  # noqa: E402
from aion2calc.gui import players_window as pw  # noqa: E402
from aion2calc.overlay import _GameWindow  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_arena import solo, team  # noqa: E402
from test_native_overlay_toolbar import FakeApp, settle  # noqa: E402
from test_native_overlay_window import Desktop  # noqa: E402


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


def _window(meter=None, api=None, **ui):
    window = pw.PlayersOverlay(api)
    window.apply_ui({"overlay_width": 340, "overlay_show_events": False, **ui})
    window.apply_meter(team() if meter is None else meter)
    window.show()
    QCoreApplication.processEvents()
    return window


def _shown(window, widget):
    return widget.isVisibleTo(window)


def test_the_words_are_the_web_windows():
    arena = team()["snapshot"]["arena"]
    assert pw.head_words(arena) == ("Players", "Arena of Cooperation · 2v2")
    assert pw.head_words(None) == ("Players", "PvP")
    assert pw.head_words({**arena, "label": None}) == ("Players", "PvP · 2v2")
    assert pw.status(arena) == "Arena of Cooperation · 4 players"
    assert pw.status(None) == "Player cards · waiting for a PvP match"
    allies, enemies = pw.sides(arena)
    assert [f["name"] for f in allies] == ["Ally", "Testme"] and [f["name"] for f in enemies] == ["Foe", "Fallen"]
    assert pw.match_of(team()["snapshot"], True) is not None and pw.match_of(team()["snapshot"], False) is None
    assert pw.match_of({"arena": {"fighters": []}}, True) is None and pw.match_of({}, True) is None
    me, foe = solo()["snapshot"]["arena"]["fighters"][1], solo()["snapshot"]["arena"]["fighters"][0]
    assert pw.facts(me) == [("cp", "46.9K"), ("word", "Rating"), ("bold", "1,530")]
    assert pw.facts({"gear_score": 2100}) == [("word", "GS"), ("bold", "2,100")] and pw.facts({}) == []
    assert pw.server_of(foe) == "Siel" and pw.server_of({"server": 2001}) == "server 2001" and pw.server_of({}) == ""
    assert pw.damage({"dps": 12_400}, 60.0) == "744K" and pw.damage({}, None) == "0"
    assert pw.hp_share({"hp_pct": 0.634}) == 0.63 and pw.hp_share({"dead": True}) == 0.0 and pw.hp_share({}) == 1.0
    assert pw.capitalised("gladiator") == "Gladiator" and pw.capitalised(None) == ""


def test_the_window_lists_the_matchs_players(qapp):
    window = _window()
    assert window.windowTitle() == "Aion 2 Calc Player Cards" and window.width() == 340
    assert window.head.words() == "Players ARENA OF COOPERATION · 2V2" and _shown(window, window.head)
    cards = window.cards.cards
    assert [card.fighter["name"] for card in cards] == ["Ally", "Testme", "Foe", "Fallen"]
    assert [card.texts() for card in cards[:2]] == [["Ally", "Sorcerer", "2.1M", "damage"],
                                                   ["Testme you", "Cleric", "603K", "damage"]]
    assert cards[3].texts()[1] == "Gladiator · dead" and cards[2].fighter["side"] == "enemy"
    assert [head.text() for head in window.cards.heads] == ["ALLIES · 2", "ENEMIES · 2"]
    assert window.status_text == "Arena of Cooperation · 4 players"
    # of the toolbar Lock and Hide alone; nothing else of the meter's window
    assert [key for key, button in window.tools.items() if _shown(window, button)] == ["lock", "hide"]
    for part in (window.metric_chip, window.target_card, window.arena_card, window.chips, window.graph, window.ping,
                 window.options, window.empty, *window.tabs.values()):
        assert not _shown(window, part)
    assert not any(_shown(window, grip) for grip in window.grips.values())
    kept = list(cards)
    meter = team()
    meter["snapshot"]["arena"]["fighters"][1]["dps"] = 30_000           # Testme now first of the allies
    window.apply_meter(meter)
    assert window.cards.cards == kept and [c.fighter["name"] for c in kept[:2]] == ["Testme", "Ally"]   # in place
    window.apply_ui({"overlay_width": 340, "overlay_players_style": "grid"})
    assert window.cards.cards != kept and all(card.mini for card in window.cards.cards)   # laid out afresh
    solo_window = _window(solo())
    first = solo_window.cards.cards[0]
    assert first.texts() == ["Testme Zikel you", "46.9K Rating 1,530", "744K", "damage"]


def test_the_grid_and_the_waiting_words(qapp):
    window = _window(overlay_players_style="grid")
    assert window.width() == 540 and all(card.mini for card in window.cards.cards)
    assert window.cards.cards[1].texts() == ["Testme", "you", "Cleric", "603K damage"]
    assert window.cards.cards[3].texts()[-1] == "1.4M damage · dead"
    window.apply_meter({"running": True, "snapshot": {"players": []}})
    assert window.head.words() == "Players PVP" and not _shown(window, window.cards)
    assert _shown(window, window.empty) and window.empty.text() == pw.WAITING
    window.apply_ui({"overlay_arena_mode": False})
    window.apply_meter(team())
    assert window.empty.text() == pw.ARENA_OFF and window.width() == 340
    window.apply_ui({"overlay_arena_mode": True, "overlay_font_scale": 130})   # 26.5em: the combat power steps aside
    window.apply_meter(solo())
    assert window.cards.cards[0].texts()[1] == "Rating 1,530"


def test_hide_closes_this_window_alone_and_its_place_is_its_own(qapp):
    api = FakeApp(team())
    window = _window(api=api)
    window.hide_overlay()
    settle(lambda: not window.isVisible())
    assert ("POST", "/api/overlay", {"action": "hide", "view": "players"}) in api.calls
    desktop = Desktop(_GameWindow(hwnd=99, bounds=(100, 50, 1600, 900)))
    placed = pw.PlayersOverlay(None, win32=desktop)
    placed.apply_ui({"overlay_players_pos_x": 400, "overlay_players_pos_y": 300,
                     "overlay_players_pos_layout": [[0, 0, 1920, 1080]], "overlay_pos_x": 5, "overlay_pos_y": 5})
    assert desktop.places[placed.host.hwnd()] == (400, 300) and placed.host.place == "overlay_players_pos"
    assert placed.host.saved_place()["overlay_players_pos_x"] == 400
    window = _window()
    window._commands({"lock_seq": 1, "reload_seq": 0})
    window._commands({"lock_seq": 2, "reload_seq": 0})
    assert window.locked                                                    # the screenshot hotkey locks it too
    window._meter_answered({"running": True, "snapshot": {"players": []}})
    assert window.head.words() == "Players ARENA OF COOPERATION · 2V2"      # held while locked


def test_it_takes_the_overlays_look(qapp):
    window = _window(overlay_text_colors={"target": "#ff0000"}, overlay_bg_mode="none")
    assert window.head.colour == "#ff0000" and window.head.shadow is not None and window.card.mode == "none"
    assert cp.window_class("players") is pw.PlayersOverlay and cp.view_of("http://x/overlay?view=players") == "players"
