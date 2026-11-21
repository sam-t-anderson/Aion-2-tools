"""The native result windows' second part (0.2.435): a saved build's Daevanion and Equipment windows as
pages/results.js draws them (``winDaevanion``, ``slotTile``, ``winEquipment``), off screen, over the app's own result
view of the bundled sorcerer build, and that build dressed with every slot extra the web page shows.
"""
import copy
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF  # noqa: E402
from PySide6.QtGui import QColor, QHelpEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QToolTip  # noqa: E402

from aion2calc.gui import result_windows as w  # noqa: E402
from aion2calc.gui import results as r  # noqa: E402
from aion2calc.gui import theme  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_history import ID, FakeApp, _button, _doc, _opened, _page, _texts  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLANNER = "https://metabot.gg/en/aion-2/daevanion/sorcerer#61-0.1"


@pytest.fixture(scope="module")
def view():
    from aion2calc.app.views import build_view
    return build_view(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def dressed(view):
    """The build as a character's: a name, server and combat power, every kind of chip on its weapons and necklace,
    enchant levels, and Ariel crystal points."""
    full = copy.deepcopy(view)
    full.update(name="Example", server="Testserver", combat_power=3512, equipment_source=None)
    slots = full["equipment"]["slots"]
    slots[0].update(enchant=10, rolls=[["Attack", "+30"], ["Critical Hit", "+16"]], manastones=[["Critical Hit", "+20"]],
                    theostones=["Theostone of Fury"], skills=[["Flame Arrow", 2]])
    slots[1].update(enchant=9, manastones=[["Accuracy", "+18"], ["Attack", "+5"]])
    slots[3].update(enchant=8, rolls=[["Attack", "+12"]])
    full["daevanion"].update(ariel_used=12, ariel_budget=40)
    return full


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


def _windows(view, choose, **page_kwargs):
    """The page with ``view`` saved and opened, ``choose`` its window; the windows' clipboard and links recorded."""
    app = FakeApp({ID: _doc("optimize-class", view)})
    page = _page(app, open_web=lambda name: None, **page_kwargs)
    _opened(page, ID)
    windows = page.windows
    windows.copied, windows.links = [], []
    windows.clipboard, windows.open_link = windows.copied.append, windows.links.append
    windows.choose(choose)
    QCoreApplication.processEvents()
    return app, page, windows


def _shown(widget, kind, name=None):
    QCoreApplication.processEvents()
    found = widget.findChildren(kind, name) if name else widget.findChildren(kind)
    return [child for child in found if child.isVisibleTo(widget)]


def _rgb(colour):
    return colour.red(), colour.green(), colour.blue()


def _near(colour, wanted, slack=12):
    wanted = QColor(wanted)
    return all(abs(a - b) <= slack for a, b in zip(_rgb(colour), _rgb(wanted)))


def test_the_daevanion_words(view):
    d = view["daevanion"]
    assert r.board_tabs(view) == [(0, "Nezekan", "108/134"), (1, "Zikel", "96/134"), (2, "Vaizel", "96/134"),
                                  (3, "Triniel", "117/168"), (4, "Ariel", "0/232"), (5, "Azphel", "0/232")]
    # the board shown: the one chosen, else the first (out of range, or not a board); none without boards
    assert r.daevanion_board(view, 4)["name"] == "Ariel"
    assert r.daevanion_board(view, 9)["name"] == r.daevanion_board(view, -1)["name"] == "Nezekan"
    assert r.daevanion_board({"daevanion": {"boards": [None, {"name": "B"}]}}, 0) is None
    assert r.daevanion_board({"daevanion": {"boards": [{"name": "A"}, None]}}, 1) == {"name": "A"}
    assert r.daevanion_board({}, 0) is None and r.daevanion_board({"daevanion": {"boards": []}}, 0) is None
    # the side's counters and lines
    assert r.points_used(d) == "417 / 417" and r.points_used({"used": 3, "budget": None}) == "3 / Unknown"
    assert r.ariel_used(d) == "" and r.ariel_used({"ariel_used": 12, "ariel_budget": 40}) == "12 / 40"
    assert r.ariel_used({"ariel_used": None, "ariel_budget": 40}) == "0 / 40"
    assert r.ariel_used({"ariel_used": 5, "ariel_budget": None}) == "5 / Unknown"
    board = r.daevanion_board(view, 0)
    assert r.board_line(board) == "108 / 134 points · 68 nodes"
    assert r.daevanion_skills(d)[:2] == [("Flame Scattershot", "+4"), ("Hellfire", "+4")] and len(r.daevanion_skills(d)) == 20
    assert r.daevanion_stats(d)[:2] == [("HP", "+3,100"), ("Defense Bonus", "+900")] and len(r.daevanion_stats(d)) == 11
    # the nodes: a stat, a skill level, the start, a hidden one
    nodes = {(nd["row"], nd["col"]): nd for nd in r.board_nodes(board)}
    speed, earth, start = nodes[(3, 3)], nodes[(3, 7)], nodes[(8, 8)]
    assert (r.node_shape(speed), r.node_lit(speed), r.node_fill(speed), r.node_text(speed), r.node_icon(speed)) == (
        "stat", True, "#f0bf4a", "+1.5%", "")
    assert r.node_tip(speed) == "Combat Speed +1.5% (Unique, 4 pt)"
    assert (r.node_shape(earth), r.node_lit(earth), r.node_fill(earth), r.node_text(earth)) == ("skill", False, "#4aa3e6", "RoE")
    assert r.node_tip(earth) == "Robe of Earth +1 (Rare, 2 pt)"
    assert r.node_icon(earth) == "https://metabot.gg/web/aion2/skills/15720000.webp"
    assert (r.node_shape(start), r.node_lit(start), r.node_fill(start), r.node_text(start), r.node_tip(start)) == (
        "start", True, "#4fd1b3", "", "Start")
    assert r.node_shape({"type": "None"}) == "none" and r.node_fill({"grade": "Epic"}) == r.node_fill({}) == r.NODE_OFF
    # a skill's initials: each word's first letter, at most three; its picture only for a whole id above 0
    assert [r.node_text({"type": "SkillLevel", "skill": s}) for s in (" Frost  Burst ", "A B C D", "", None)] == ["FB", "ABC", "", ""]
    icons = [r.node_icon({"type": "SkillLevel", "skill_id": x}) for x in ("15720000", 15720000.0, 0, -3, 1.5, 2 ** 53, 2 ** 53 - 1, None, "x")]
    assert icons == [r.node_icon(earth), r.node_icon(earth), "", "", "", "", f"https://metabot.gg/web/aion2/skills/{2 ** 53 - 1}.webp", "", ""]
    # the copy: each board's points, then the planner's link
    copied = r.daevanion_copy(view).split("\n")
    assert copied[:2] == ["Nezekan: 108/134 pts", "Zikel: 96/134 pts"] and copied[6].startswith("Planner link: https://metabot.gg/")
    assert r.daevanion_copy({**view, "links": {}}).split("\n")[-1] == "Azphel: 0/232 pts" and r.planner_link({}) == ""


def test_the_equipment_words(view, dressed):
    left, right = r.equipment_slots(view)
    assert [s["slot"] for s in left] == ["Main hand", "Off-hand", "Armor x7"]
    assert [s["slot"] for s in right] == ["Necklace", "Earrings x2", "Rings x2", "Accessory rolls", "Bracelets x2", "Amulet", "Rune"]
    weapon, armour, rune = left[0], left[2], right[-1]
    assert (r.slot_grade(weapon), r.slot_grade(armour), r.slot_grade(rune), r.slot_grade({"grade": "Bogus"})) == ("Unique", "", "Special", "")
    assert r.slot_item(weapon) == "Spiritforged Spellbook +10" and r.slot_item({"name": "Named"}) == "Named"
    bold = f"<b style='color: {theme.COLORS['text']};'>"
    assert r.slot_stats(weapon) == (f"{bold}+256</b> Weapon min attack · {bold}+279</b> Weapon max attack · "
                                    f"{bold}+116</b> Critical Hit · {bold}+100</b> Accuracy")           # the first four
    assert r.slot_extras(weapon) == []
    assert r.slot_extras(dressed["equipment"]["slots"][0]) == [
        ("chip", "Attack +30"), ("chip", "Critical Hit +16"), ("manastone", "Critical Hit +20"), ("gold", "Theostone of Fury"),
        ("skill", "Flame Arrow +2")]
    assert r.slot_extras({"rolls": [["Only"]], "skills": "x"}) == [("chip", "Only ")]
    assert r.doll(view) == ("Sorcerer", view["loadout_name"], "")
    assert r.doll(dressed) == ("Sorcerer", "Example · Testserver", "Combat Power 3,512")
    assert r.equipment_sub(view) == "Saved run loadout" and r.equipment_sub(dressed) == "current gear (official profile)"
    assert r.equipment_sub({}) == "loadout used for this build"
    rolls = r.roll_rows(view)
    assert len(rolls) == 8 and rolls[0] == ("spiritforged spellbook", "Might › Critical Hit › MP")
    assert rolls[-1] == ("spiritforged guard", "Might › Accuracy") and r.roll_rows({"equipment": {"rolls": {}}}) == []
    assert r.enchant_rows(view)[0] == ("Weapon (Spiritforged / Rupture)", "150.1") and r.enchant_rows(view)[-1] == ("Armor pieces", "0.0")
    ties = r.enchant_rows({"equipment": {"enchant": [{"slot": "S", "dps": x} for x in (0.25, 0.35, 2.675, -0.04, None)]}})
    assert [dps for _slot, dps in ties] == ["0.3", "0.3", "2.7", "-0.0", "—"]              # toFixed(1), halves up
    assert r.equipment_copy(view).split("\n")[:2] == ["Main hand: Spiritforged Spellbook +10", "Off-hand: Spiritforged Guard +9"]
    assert r.equipment_grid(view)[0] == ("Attack", "+909") and len(r.equipment_grid(view)) == 12


def test_the_daevanion_window(qapp, dressed):
    app, page, windows = _windows(dressed, "daevanion")
    window_texts = _texts(windows)
    # the tabs, the first chosen; the side's counters and lines
    tabs = _shown(windows, w.BoardTab)
    assert [t.accessibleName() for t in tabs] == [f"{name} {count}" for _i, name, count in r.board_tabs(dressed)]
    assert [t.objectName() for t in tabs] == ["tabOn"] + ["tab"] * 5
    counters = _shown(windows, QLabel, "counter")
    assert [c.accessibleName() for c in counters] == ["Points used 417 / 417", "Ariel crystal used 12 / 40"]
    assert counters[1].toolTip() == r.ARIEL_TIP
    for words in ("NEZEKAN BOARD", "108 / 134 points · 68 nodes", "SKILL LEVELS", "STATS (ALL BOARDS)", "STATS FROM THIS SYSTEM",
                  r.LEGEND_NOTE, "Epic 3 pt"):
        assert words in window_texts
    assert f"Flame Scattershot <b style='color: {theme.COLORS['gold']};'>+4</b>" in window_texts and "HP <b>+3,100</b>" in window_texts
    # the board: 13 by 13 squares 5 px apart in its padding, each skill's picture asked for once
    board = _shown(windows, w.NodeBoard)[0]
    assert (board.width(), board.height()) == (13 * 39 - 5 + 28, 13 * 39 - 5 + 28) and len(board.nodes) == 89
    settle(lambda: len(board.pictures) == 17)
    asked = [call for call in app.calls if "skills%2F" in call]
    assert len(asked) == len(set(asked)) == 17
    frame = _shown(windows, w.BoardFrame)[0]
    settle(lambda: frame.height() == board.height() + 2)                     # laid out: the frame as tall as the board
    image = frame.grab().toImage()
    at = board.mapTo(frame, QPoint(0, 0))

    def pixel(x, y):
        return QColor(image.pixel(at.x() + x, at.y() + y))
    corner = 14 + 2 * 39                                                     # the node at row 3, column 3
    assert _near(pixel(corner + 17, corner + 4), "#f0bf4a")                  # a Unique stat taken: bright
    assert min(_rgb(pixel(corner - 1, corner + 17))) > 150                   # its white ring
    dim = pixel(14 + 4 * 39 + 17, corner + 4)                                # a Common stat left: dim
    assert 40 < max(_rgb(dim)) < 140 and abs(dim.red() - dim.blue()) < 25
    assert _near(pixel(14 + 7 * 39 + 17, 14 + 7 * 39 + 17), "#4fd1b3")       # the start's hexagon
    assert _near(pixel(14 + 8 * 39 + 17, corner + 17), "#c87828")            # Wish of Concentration's picture
    # a node's words as its tooltip; nothing over the gaps
    point = QPointF(corner + 17, corner + 17)
    assert board.node_at(point)["label"] == "Combat Speed +1.5%" and board.node_at(QPointF(corner + 36, corner + 17)) is None
    QApplication.sendEvent(board, QHelpEvent(QEvent.ToolTip, point.toPoint(), board.mapToGlobal(point.toPoint())))
    assert QToolTip.text() == "Combat Speed +1.5% (Unique, 4 pt)"
    QToolTip.hideText()
    # the copy and the planner
    _button(windows, "Copy as text").click()
    _button(windows, "Open in metabot planner").click()
    assert windows.copied == [r.daevanion_copy(dressed)] and windows.links == [r.planner_link(dressed)]
    # another board: its tab chosen, its 15 by 15 squares, the pictures already read kept
    tabs[4].click()
    QCoreApplication.processEvents()
    assert windows.state["board"] == 4 and [t.objectName() for t in _shown(windows, w.BoardTab)][4] == "tabOn"
    ariel = _shown(windows, w.NodeBoard)[0]
    assert ariel.width() == 15 * 39 - 5 + 28 and not ariel.wanted and "ARIEL BOARD" in _texts(windows)
    assert "0 / 232 points · 0 nodes" in _texts(windows)


def test_the_daevanion_side_beside_its_board_or_above_it(qapp, view):
    _app, page, windows = _windows(view, "daevanion")
    split = next(s for s in _shown(windows, w.Split) if any(isinstance(p, QFrame) and p.objectName() == "daevside" for p in s.parts))
    side, column = split.parts
    assert split.width() <= w.NARROW and split.narrow                         # 1,100 px: one column, as under app.css's breakpoint
    assert side.geometry().bottom() < column.geometry().top() and side.width() == column.width()
    assert len(_shown(windows, QLabel, "counter")) == 1                       # no Ariel crystal points: no counter for them
    page.resize(1500, 1500)
    settle(lambda: split.narrow is False)
    QCoreApplication.processEvents()
    assert side.width() == 260 and side.geometry().right() < column.geometry().left()
    assert split.width() > w.NARROW


def test_a_daevanion_window_without_boards_or_planner(qapp, view):
    _app, _page_, windows = _windows({**view, "daevanion": {"boards": []}}, "daevanion")
    assert r.NO_BOARD in _texts(windows) and _button(windows, "Copy as text") is None and not _shown(windows, w.NodeBoard)
    _app, _page_, windows = _windows({**view, "links": {"metabot_daevanion": "file:///etc/passwd"}}, "daevanion")
    assert _button(windows, "Copy as text") and _button(windows, "Open in metabot planner") is None   # only a web address opens


def test_the_equipment_window(qapp, dressed):
    app, page, windows = _windows(dressed, "equipment")
    texts = _texts(windows)
    assert "current gear (official profile)" in texts
    tiles = _shown(windows, w.SlotTile)
    names = [next(l.text() for l in tile.findChildren(QLabel, "slotName")) for tile in tiles]
    assert names == [s["slot"].upper() for s in r.equipment_slots(dressed)[0] + r.equipment_slots(dressed)[1]]
    weapon, armour, rune = tiles[0], tiles[2], tiles[-1]
    assert (weapon.grade, armour.grade, rune.grade) == ("Unique", "", "Special")
    assert weapon.findChildren(QLabel, "gnameUnique")[0].text() == "Spiritforged Spellbook +10"
    assert armour.findChildren(QLabel, "gname")[0].text() == "Vakron / Bakarma / Divine Canyon ~+5"
    chips = [(c.objectName(), c.text(), c.toolTip()) for c in _shown(weapon, QLabel) if c.objectName().startswith("chip")]
    assert chips == [("chip", "Attack +30", ""), ("chip", "Critical Hit +16", ""), ("chipGold", "Critical Hit +20", "Manastone"),
                     ("chipGold", "Theostone of Fury", ""), ("chipSkill", "Flame Arrow +2", "")]
    assert "metabot item table (206-229, +5/enchant)" in _texts(weapon)
    # the pictures: an enchant level on the weapon, the placeholder where the build names no picture
    icons = {tile: tile.findChildren(w.SkillIcon)[0] for tile in (weapon, armour)}
    assert (icons[weapon].level, icons[armour].level, icons[armour].placeholder, icons[armour].path) == ("+10", "", "◇", "")
    settle(lambda: icons[weapon].pixmap is not None)
    asked = [call for call in app.calls if "items%2F" in call]
    assert len(asked) == len(set(asked)) == 5                                 # the five slots with a picture, once each
    # the tiles' edges in their grades' colours
    for tile, colour in ((weapon, "#e9a43a"), (rune, "#34b798"), (armour, theme.COLORS["line2"])):
        assert _near(QColor(tile.grab().toImage().pixel(1, tile.height() // 2)), colour, 20)
    # the doll, the rolls and enchant priority, the gear's stats
    for words in ("SORCERER", "Example · Testserver", "Combat Power 3,512", r.ROLLS_HEAD, r.ENCHANT_HEAD,
                  "<b>spiritforged spellbook</b>: Might › Critical Hit › MP", "Weapon (Spiritforged / Rupture) <b>150.1</b> DPS / level",
                  r.EQUIPMENT_GRID.upper()):
        assert words in texts
    _button(windows, "Copy as text").click()
    assert windows.copied == [r.equipment_copy(dressed)]
    # narrow, the doll between its two sides; wide, beside them
    split = next(s for s in _shown(windows, w.Split) if any(isinstance(p, w.Doll) for p in s.parts))
    left, doll, right = split.parts
    assert split.narrow and left.geometry().bottom() < doll.geometry().top() < right.geometry().top()
    page.resize(1500, 1500)
    settle(lambda: split.narrow is False)
    QCoreApplication.processEvents()
    assert doll.width() == 220 and left.geometry().right() < doll.geometry().left() < right.geometry().left()
    assert doll.height() >= right.height() - 1                               # the doll as tall as its row


def test_an_equipment_window_without_gear(qapp, view):
    _app, _page_, windows = _windows({k: v for k, v in view.items() if k not in ("equipment", "equipment_source")}, "equipment")
    texts = _texts(windows)
    assert "loadout used for this build" in texts and "SORCERER" in texts and not _shown(windows, w.SlotTile)
    assert _button(windows, "Copy as text") is None and r.ROLLS_HEAD not in texts and r.EQUIPMENT_GRID.upper() not in texts
