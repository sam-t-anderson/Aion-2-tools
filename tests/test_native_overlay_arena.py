"""The native overlay's tenth part (0.2.423): arena mode as the web overlay draws it (arena-view.js ``A2Arena``,
overlay.css ``.arn-*``), off screen, over the browser tests' own matches (tests/browser/test_browser_overlay_arena.py):
the Arena of Solitude's one against one and the Arena of Cooperation's two against two.

The opponent's (or your target's) card in the target card's place, the three metrics in the layout picked (stacked,
compact, versus), your three first in a team match and the party in the metric chip's metric or all three, the match in
the clock, and the arena's options saved as settings. Arena mode off draws the meter as ever.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import arena as A  # noqa: E402
from aion2calc.gui.arena import Section, TableHead, Tug  # noqa: E402
from aion2calc.gui.overlay import ArenaRow, MeterOverlay, PlayerRow  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_arena import solo, team  # noqa: E402
from test_browser_overlay_look import fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, laid_out_apart, settle  # noqa: E402


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


def _overlay(meter, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter)
    return window


def _drawn(window) -> list[str]:
    """Arena mode's rows as drawn, top to bottom: a section's words in brackets, the table's head in braces, a row
    as its name, rate and share, a row of three figures or a table's row as its name and figures, a tug as its
    three words."""
    out = []
    for widget in window._arena_order:
        if isinstance(widget, Section):
            out.append(f"[{widget.text()}]")
        elif isinstance(widget, TableHead):
            out.append("{" + widget.first + "}")
        elif isinstance(widget, Tug):
            out.append(" | ".join(widget.texts()))
        elif isinstance(widget, ArenaRow):
            out.append(f"{widget.kind} {widget.name}: {widget.right()}")
        elif isinstance(widget, PlayerRow):
            out.append(f"{widget.name} {widget.rate} {widget.share}")
    return out


def _near(image: QImage, colour: str, box: QRectF | None = None, reach: int = 40) -> int:
    want, count = QColor(colour), 0
    box = box or QRectF(0, 0, image.width(), image.height())
    for y in range(max(0, int(box.top())), min(image.height(), int(box.bottom()))):
        for x in range(max(0, int(box.left())), min(image.width(), int(box.right()))):
            pixel = image.pixelColor(x, y)
            if max(abs(pixel.red() - want.red()), abs(pixel.green() - want.green()),
                   abs(pixel.blue() - want.blue())) <= reach and pixel.alpha() > 150:
                count += 1
    return count


def _me(snap):
    local = snap["identity_status"]["local_name"].casefold()
    return lambda player: str(player.get("name") or "").casefold() == local


# ------------------------------------------------------------------ the reading's arithmetic
def test_the_match_reads_as_the_arena_views():
    snap = solo()["snapshot"]
    arena = A.arena_of(snap, False, True)
    them, me = A.foe(arena), A.you(arena, snap["players"], _me(snap))
    assert (them["name"], me["name"]) == ("Testfoe", "Testme")
    assert A.where(them) == "Siel · Elyos" and A.hp_of(them) == pytest.approx(63.0)
    assert A.power(them) == ("48.2K", [("Gladiator", False), (" · ", False), ("Lv 45", False), (" · ", False),
                                       ("Rating ", False), ("1,842", True)])
    assert A.match(arena, them) == [("Round 2 · you lead ", False), ("1–0", True)]
    assert A.clock_tail(arena, snap["players"], _me(snap), "dps", False) == [
        ("Arena of Solitude", False), (" · ", False), ("1–0", True)]
    arena.update(result="win", won=2, lost=1, rating_after=1_561)
    assert A.match(arena, them) == [("You won ", False), ("2–1", True), (" · rating now ", False), ("1,561", True)]
    assert A.arena_of(snap, True, True) is None and A.arena_of(snap, False, False) is None   # cleared, or mode off
    assert A.arena_of({"arena": {"fighters": []}}, False, True) is None
    team_snap = team()["snapshot"]
    arena = A.arena_of(team_snap, False, True)
    assert A.foe(arena)["name"] == "Foe" and A.match(arena, A.foe(arena)) == [
        ("Dealt ", False), ("38%", True), (" of the damage you took", False)]
    assert A.clock_tail(arena, team_snap["players"], _me(team_snap), "hps", False) == [
        ("Arena of Cooperation · Party HPS ", False), ("10.00K", True)]
    assert A.share(1, 0) == "—" and A.share(8_200, 19_300) == "42.5%"
    assert A.name_of({"name": "Player #7", "self": True}) == "You" and A.name_of({"name": "Player #7"}) == "Player #7"


# ------------------------------------------------------------------ one against one
def test_a_one_against_one_match_shows_the_opponents_card_and_the_compact_table(qapp):
    window = _overlay(solo())
    card = window.arena_card
    assert not card.isHidden() and window.target_card.isHidden() and card.kind == "foe"
    assert card.texts() == ["TestfoeSiel · ElyosOPPONENT  63.0%", "48.2KGladiator · Lv 45 · Rating 1,842",
                            "Round 2 · you lead 1–0"]
    assert [run.kind for run in card.head.left] == ["", "", "tag"] and card.power.left[0].kind == "cp"
    assert card.hp.fraction == pytest.approx(0.63) and card.toolTip().startswith("Your opponent")
    assert _drawn(window) == ["{Fighter}", "table Testme: 12.4K  10.6K  4.1K", "table Testfoe: 10.6K  12.4K  1.2K"]
    mine = next(widget for widget in window._arena_order if isinstance(widget, ArenaRow) and widget.mine)
    assert mine.name == "Testme" and mine.fill == 0                            # your row, its green dot; no bar
    assert window.clock.text() == "01:00 Arena of Solitude · 1–0"
    assert window.contribution.isHidden() and all(row.isHidden() for row in window.rows)
    laid_out_apart(window)


def test_the_stacked_and_versus_layouts(qapp):
    window = _overlay(solo(), overlay_arena_layout="stacked")
    assert _drawn(window) == ["[DPS]", "Testme 12,400/s 53.9%", "Testfoe 10,600/s 46.1%",
                              "[D.TAKEN]", "Testme 10,600/s 46.1%", "Testfoe 12,400/s 53.9%",
                              "[HPS]", "Testme 4,100/s 77.4%", "Testfoe 1,200/s 22.6%"]
    rows = [widget for widget in window._arena_order if isinstance(widget, PlayerRow)]
    assert rows[0].cp == "46.9K" and rows[2].cp == "" and rows[0].fill == 1.0   # the chip in the first section only
    window.apply_ui({"overlay_width": 340, "overlay_arena_layout": "versus"})
    assert _drawn(window) == ["[YOU VS TESTFOE]", "12.4K/s | DPS | 10.6K/s", "10.6K/s | D.TAKEN | 12.4K/s",
                              "4.1K/s | HPS | 1.2K/s"]
    tug = next(widget for widget in window._arena_order if isinstance(widget, Tug))
    assert tug.share() == pytest.approx(100 * 12_400 / 23_000)
    card = window.arena_card
    assert card.kind == "versus" and card.texts() == ["Testme", "CP 46.9K", "Rating 1,530", "Zikel",
                                                      "Testfoe", "CP 48.2K", "Rating 1,842", "Siel · Elyos"]
    assert card.sides[1][3].fraction == pytest.approx(0.63) and card.sides[1][3].right
    laid_out_apart(window)


# ------------------------------------------------------------------ a team match
def test_a_team_match_shows_your_three_then_the_party_and_all_three_on_request(qapp):
    window = _overlay(team(), overlay_arena_layout="stacked")
    assert window.arena_card.texts() == ["FoeTARGET  41.0%", "Assassin", "Dealt 38% of the damage you took"]
    assert _drawn(window) == ["[YOU · TESTME]", "DPS 6,700/s 22.3%", "D.Taken 8,200/s 42.5%", "HPS 9,600/s 96.0%",
                              "[PARTY · DPS]", "Ally 23,400/s 77.7%", "Testme 6,700/s 22.3%"]
    assert window.clock.text() == "01:30 Arena of Cooperation · Party DPS 30.10K"
    window.set_metric("hps")                     # the party in the chip's metric
    assert _drawn(window)[4:] == ["[PARTY · HPS]", "Testme 9,600/s 96.0%", "Ally 400/s 4.0%"]
    assert window.clock.text().endswith("Party HPS 10.00K")
    window.set_metric("dps")
    window.apply_ui({"overlay_width": 340, "overlay_arena_layout": "stacked", "overlay_arena_all3": True})
    assert _drawn(window)[4:] == ["[PARTY · DPS · D.TAKEN · HPS]", "tri Ally: 23.4K  11.1K  400",
                                 "tri Testme: 6.7K  8.2K  9.6K"]
    window.apply_ui({"overlay_width": 340, "overlay_arena_layout": "compact", "overlay_arena_all3": True})
    assert _drawn(window) == ["{Party}", "table Ally: 23.4K  11.1K  400", "table Testme: 6.7K  8.2K  9.6K"]
    window.apply_ui({"overlay_width": 340, "overlay_arena_layout": "compact"})
    assert _drawn(window) == ["{You}", "table Testme: 6.7K  8.2K  9.6K", "[PARTY · DPS]", "Ally 23,400/s 77.7%",
                              "Testme 6,700/s 22.3%"]
    window.apply_ui({"overlay_width": 340, "overlay_arena_layout": "versus"})
    assert window.arena_card.texts() == ["Testme", "6.7K · 8.2K · 9.6K", "Foe"]
    laid_out_apart(window)


def test_arena_mode_off_draws_the_meter_as_ever(qapp):
    window = _overlay(solo(), overlay_arena_mode=False)
    assert window.arena_card.isHidden() and _drawn(window) == []
    assert [row.name for row in window.rows if not row.isHidden()] == ["Testme"]
    plain = _overlay(fight())
    assert plain.arena_card.isHidden() and plain._arena_order == []                # no match: the meter
    window = _overlay(solo(), overlay_show_target=False)
    assert window.arena_card.isHidden() and len(_drawn(window)) == 3               # the card behind its setting


def test_the_arena_rows_are_drawn_in_their_colours(qapp):
    window = _overlay(solo())
    window.show()
    QCoreApplication.processEvents()
    table = next(widget for widget in window._arena_order if isinstance(widget, ArenaRow))
    image = table.grab().toImage()
    for colour in ("#f1d27c", "#ff8f86", "#7fe0a0"):                              # each figure's bar
        assert _near(image, colour, QRectF(image.width() * 0.44, 0, image.width(), image.height()), 20) > 3
    head = next(widget for widget in window._arena_order if isinstance(widget, TableHead))
    columns = head.columns()
    assert columns[0].left() == 7 and columns[3].right() == pytest.approx(head.width() - 12)   # 3 px and 9 in


# ------------------------------------------------------------------ the options
def test_the_arena_options_are_saved_as_settings(qapp):
    api = FakeApp(solo())
    window = _overlay(solo(), api)
    window.toggle_options()
    checks, picks = window.arena_checks, window.arena_picks
    assert checks["overlay_arena_mode"].isChecked() and not checks["overlay_arena_all3"].isChecked()
    assert picks["overlay_arena_layout"].currentData() == "compact" and picks["overlay_players_style"].currentData() == "list"
    picks["overlay_arena_layout"].setCurrentIndex(picks["overlay_arena_layout"].findData("stacked"))
    picks["overlay_arena_layout"].activated.emit(picks["overlay_arena_layout"].currentIndex())
    settle(lambda: picks["overlay_arena_layout"].isEnabled())
    assert ("POST", "/api/ui", {"overlay_arena_layout": "stacked"}) in api.calls
    assert len([w for w in window._arena_order if isinstance(w, Section)]) == 3   # drawn by it at once
    checks["overlay_players_enabled"].click()
    settle(lambda: checks["overlay_players_enabled"].isEnabled())
    assert ("POST", "/api/ui", {"overlay_players_enabled": True}) in api.calls
    api.refuse["/api/ui"] = "read-only settings"
    checks["overlay_arena_mode"].click()
    settle(lambda: checks["overlay_arena_mode"].isEnabled())
    assert checks["overlay_arena_mode"].isChecked() and window.message.text() == "Could not change the arena setting"
    assert not window.arena_card.isHidden()                                      # still on
