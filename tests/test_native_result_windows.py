"""The native result windows' second to fifth parts (0.2.435 to 0.2.438): a saved build's Daevanion, Equipment,
Arcana, Titles, wings & pet, Skills hotbar, Macro & rotation and Pet Genus windows as pages/results.js draws them
(``winDaevanion``, ``slotTile``, ``winEquipment``, ``winArcana``, ``winTitles``, ``winHotbar``, ``winMacro``,
``winGenus`` with genus-editor.js's ``ringHTML``), off screen, over the app's own result view of the bundled sorcerer
build, that build dressed with every slot extra, arcana card and the pet the web page shows, and that build with saved
Genus Insight lines scored as the report scores them.
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
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QTableWidget, QToolButton, QToolTip  # noqa: E402

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
    enchant levels, Ariel crystal points, three arcana cards and a pet."""
    full = copy.deepcopy(view)
    full.update(name="Example", server="Testserver", combat_power=3512, equipment_source=None)
    slots = full["equipment"]["slots"]
    slots[0].update(enchant=10, rolls=[["Attack", "+30"], ["Critical Hit", "+16"]], manastones=[["Critical Hit", "+20"]],
                    theostones=["Theostone of Fury"], skills=[["Flame Arrow", 2]])
    slots[1].update(enchant=9, manastones=[["Accuracy", "+18"], ["Attack", "+5"]])
    slots[3].update(enchant=8, rolls=[["Attack", "+12"]])
    full["daevanion"].update(ariel_used=12, ariel_budget=40)
    full["arcana_items"] = [
        {"slot": "Chalice", "name": "Chalice of Vigor", "grade": "Unique", "enchant": 5, "icon": "/web/aion2/items/chalice.webp",
         "deity": {"label": "Time [Siel]", "points": 20.25}, "skills": [["Blaze", 2], ["Hellfire", 1]],
         "stats": [{"label": "Attack", "text": "+20"}, {"label": "Accuracy", "text": "+15"}]},
        {"slot": "Bell", "name": "Bell of Magic", "grade": "Legend", "enchant": 0, "deity": {"label": "Death [Triniel]", "points": "7"},
         "stats": [{"label": "HP", "text": "+300"}]},
        {"slot": "Mirror", "name": "Mirror of Purity", "grade": "Epic", "skills": [["Frost", 1]], "stats": []}]
    full["extras"] = {**full["extras"], "pet": {"name": "Pet one", "level": 30, "icon": "https://metabot.gg/web/aion2/pets/one.webp"}}
    return full


@pytest.fixture(scope="module")
def genus_view(view):
    """The build with three genera's Insight saved (Cogni at 6, Fera at 10, Natura at 3), prepared and given what to
    roll for as the report does, its lines' contributions set, and kept as a saved result keeps it (JSON: the roll
    table's slots keyed by text)."""
    from aion2calc.opt.genus import prepare
    from aion2calc.plan import genus as G
    from aion2calc.plan.context import PlanContext
    state = {"Cogni": {"level": 6, "lines": [{"slot": 4, "stat": "Cogni Damage Boost", "value": "3.6%"},
                                             {"slot": 1, "stat": "Boss Attack", "value": "12"},
                                             {"slot": 2, "stat": "Cogni Defense", "value": "54"}]},
             "Fera": {"level": 10, "lines": [{"slot": 1, "stat": "Attack", "value": "10"},
                                             {"slot": 7, "stat": "Fera Damage Boost", "value": "2.4%"}]},
             "Natura": {"level": 3, "lines": []}}
    plan = prepare(state, "pve")
    plan["roll_targets"] = G.roll_targets(PlanContext.for_class("sorcerer"), state, "pve", plan["mix"])
    for index, row in enumerate(plan["lines"]):
        row["gain"] = None if row["reason"] else 0.004 * (index + 1)
    return {**view, "genus": json.loads(json.dumps(plan))}


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


def test_the_arcana_words(view, dressed):
    assert r.arcana_deity({"label": "Time [Siel]", "points": 20}) == "Time [Siel] +20"
    assert [r.arcana_deity({"label": "L", "points": x}) for x in ("20.25", None, "x", -0.04, 2.675)] == [
        "L +20.3", "L +0", "L +0", "L +0", "L +2.7"]                  # toFixed(1), then the number as JavaScript writes it
    assert r.arcana_deity({"points": 3}) == r.arcana_deity({}) == r.arcana_deity(None) == ""
    first = r.arcana_cards(dressed)[0]
    assert first == {"icon": "/web/aion2/items/chalice.webp", "enchant": "+5", "grade": "Unique", "name": "Chalice of Vigor",
                     "deity": "Time [Siel] +20.3", "skills": ["Blaze +2", "Hellfire +1"], "stats": "Attack +20, Accuracy +15"}
    assert [(c["enchant"], c["deity"], c["skills"]) for c in r.arcana_cards(dressed)[1:]] == [
        ("+0", "Death [Triniel] +7", []), ("+0", "", ["Frost +1"])] and r.arcana_cards(view) == []
    assert r.arcana_picks(view)[:2] == [("Chalice / Grail", "Vigor or Frenzy", ["Vigor or Frenzy: Time +20", "Magic or Purity: Space +20"]),
                                        ("Parchment", "Either variant", ["Vigor or Frenzy: Life +20", "Magic or Purity: Destiny +20"])]
    rows = r.arcana_roll_rows(view)
    assert [row[0] for row in rows] == ["Compass", "Bell", "Parchment", "Chalice", "Mirror"]      # the best at +5 first
    assert rows[0] == ["Compass", "+0.1%", "+0.3%", "Bittercold Wind +0.1% / +0.1% · Ice Chain +0.0% / +0.1% · "
                       "Flame Scattershot +0.0% / +0.0% · Winter's Shackles +0.0% / +0.0%"]
    assert rows[2][1:3] == ["+-0.7%", "+-1.3%"]                                                    # the web page's own sign
    assert rows[4][3].endswith("Robe of Earth -6.8% / -3.6%")
    assert r.arcana_copy(view).split("\n") == ["Chalice / Grail: Vigor or Frenzy", "Parchment: either", "Compass: Magic or Purity",
                                                "Bell: Magic or Purity", "Mirror: Vigor or Frenzy"]
    assert r.arcana_copy(dressed).split("\n")[:3] == ["Chalice: Chalice of Vigor +5, Time [Siel] +20.3 — Blaze +2, Hellfire +1",
                                                      "Bell: Bell of Magic +0, Death [Triniel] +7", "Mirror: Mirror of Purity +0 — Frost +1"]
    assert r.arcana_copy({"arcana_items": [{"slot": "S", "name": "N", "deity": {}}]}) == "S: N +0, "   # {} is true in JavaScript
    assert r.deity_grid(view)[:2] == [("Might", "+21"), ("Precision", "+1")] and len(r.deity_grid(view)) == 9


def test_the_titles_words(view, dressed):
    tiles = r.title_tiles(view)
    assert [(t["slot"], t["item"], t["grade"]) for t in tiles] == [
        ("Attack title", "Guardian of Altgard / Verteron", ""), ("Other title", "Through Hell and Back", ""),
        ("Owned titles", "collection bonuses (estimate)", ""), ("Wings", "Ultimate Daeva Wings", "Unique")]
    assert tiles[2]["stats"].count("<b ") == 3 and r.slot_stats({"stats": [{"text": "+1", "label": "A"}] * 6}, None).count("<b ") == 6
    pet = r.title_tiles(dressed)[-1]
    assert (pet["slot"], pet["item"], pet["level"], pet["stats"], pet["icon"]) == (
        "Pet", "Pet one", "Lv 30", r.PET_NOTE, "https://metabot.gg/web/aion2/pets/one.webp")
    assert r.title_tiles({"extras": {"pet": {}}})[0]["level"] == "Lv " and r.title_tiles({"extras": {"pet": 0}}) == []
    assert r.title_tiles({"extras": {"wing": {"icon": "/w.webp"}, "wings": [{"item": "W"}]}})[0]["icon"] == "/w.webp"
    rows = r.title_rows(view)
    assert rows[0] == ("Unbound by Genus", "Unique", "PvE Damage Boost +4.5%, Attack Bonus +34, Critical Hit +68",
                       "PvE Damage Boost +1%") and len(rows) == 10
    assert r.titles_grid(view)[:2] == [("Attack", "+4"), ("Critical Hit", "+20")] and r.titles_grid({}) == []


def test_the_arcana_window(qapp, dressed):
    app, page, windows = _windows(dressed, "arcana")
    texts = _texts(windows)
    titles = [label.text() for label in _shown(windows, QLabel, "winTitle")]
    assert titles == ["ARCANA", "DEITY & PRIMARY STATS"] and r.ARCANA_SUB in texts
    cards = _shown(windows, QFrame, "arcanaCard")
    assert len(cards) == 3 + 5
    first = cards[0]
    icon = first.findChildren(w.SkillIcon)[0]
    assert icon.level == "+5" and icon.path.endswith("chalice.webp") and cards[1].findChildren(w.SkillIcon)[0].level == "+0"
    assert first.findChildren(QLabel, "gnameUnique")[0].text() == "Chalice of Vigor"
    assert [l.text() for l in _shown(first, QLabel) if l.objectName() in ("gold", "chip", "muted")] == [
        "Time [Siel] +20.3", "Blaze +2", "Hellfire +1", "Attack +20, Accuracy +15"]
    assert [l.text() for l in _shown(cards[4], QLabel)] == ["Parchment", "Either variant",
                                                           "Vigor or Frenzy: Life +20<br>Magic or Purity: Destiny +20"]
    for words in (r.PICKS_HEAD, r.ROLLS_TABLE_HEAD, "TOTALS"):
        assert words in texts
    rolls = _shown(windows, QTableWidget)[0]
    assert rolls.rowCount() == 5 and [rolls.horizontalHeaderItem(c).text() for c in range(4)] == r.ROLLS_COLUMNS
    assert (rolls.item(0, 0).text(), rolls.item(2, 1).text()) == ("Compass", "+-0.7%")
    assert _rgb(rolls.item(0, 0).foreground().color()) == _rgb(QColor(theme.COLORS["gold"]))
    _button(windows, "Copy as text").click()
    assert windows.copied == [r.arcana_copy(dressed)]
    # two columns of cards on a narrow window, five on a wide one
    deck = next(d for d in _shown(windows, w.Columns) if cards[0] in d.cards)
    assert deck.columns == 2 and deck.grid.getItemPosition(deck.grid.indexOf(cards[2]))[:2] == (1, 0)
    page.resize(1500, 1500)
    settle(lambda: deck.columns == 5)
    assert deck.grid.getItemPosition(deck.grid.indexOf(cards[2]))[:2] == (0, 2)


def test_an_arcana_window_without_arcana(qapp, view):
    bare = {**view, "extras": {k: v for k, v in view["extras"].items() if not k.startswith("arcana") and k != "deity"}}
    _app, _page_, windows = _windows(bare, "arcana")
    assert r.NO_ARCANA in _texts(windows) and _button(windows, "Copy as text") is None
    assert [label.text() for label in _shown(windows, QLabel, "winTitle")] == ["ARCANA"]       # no deity: no second window


def test_the_titles_window(qapp, dressed):
    app, page, windows = _windows(dressed, "titles")
    texts = _texts(windows)
    assert "TITLES, WINGS & PET" in texts and r.TITLES_HEAD in texts and r.TITLES_GRID.upper() in texts
    tiles = _shown(windows, w.SlotTile)
    assert [t.findChildren(QLabel, "slotName")[0].text() for t in tiles] == ["ATTACK TITLE", "OTHER TITLE", "OWNED TITLES",
                                                                           "WINGS", "PET"]
    wings, pet = tiles[3], tiles[4]
    assert wings.grade == "Unique" and _near(QColor(wings.grab().toImage().pixel(1, wings.height() // 2)), "#e9a43a", 20)
    assert pet.findChildren(QLabel, "gname")[0].text() == f"Pet one <span style='color: {theme.COLORS['muted']};'>Lv 30</span>"
    assert r.PET_NOTE in _texts(pet)
    icons = [t.findChildren(w.SkillIcon)[0] for t in tiles]
    assert [i.path for i in icons[:4]] == ["", "", "", ""] and icons[4].path.endswith("pets%2Fone.webp")
    assert not any(i.placeholder for i in icons)                                    # titles' pictures stay empty
    ranking = _shown(windows, QTableWidget)[0]
    assert ranking.rowCount() == 10 and ranking.item(0, 0).text() == "Unbound by Genus"
    assert _rgb(ranking.item(0, 0).foreground().color()) == _rgb(QColor("#e9a43a"))
    assert _rgb(ranking.item(0, 2).foreground().color()) == _rgb(QColor(theme.COLORS["muted"]))
    assert _button(windows, "Copy as text") is None


def test_the_hotbar_and_macro_words(view):
    rows = r.hotbar_rows(view)
    assert len(rows) == 1 and rows[0][0] == "0" and [s and s["binding"] for s in rows[0][1]] == ["1", "2", "3", "4"] + [None] * 8
    many = r.hotbar_rows({"hotbar": {"slots": [{"binding": str(i)} for i in range(13)]}})
    assert [number for number, _slots in many] == ["1", "0"] and many[0][1][0]["binding"] == "12"     # the last row first
    slots = view["hotbar"]["slots"]
    assert [r.hotbar_note(s) for s in slots] == ["Hold to charge"] + ["Macro key: 4 skills, cast in order"] * 3
    assert (r.hotbar_note({"manual": True}), r.hotbar_note({"stack": [{}]}), r.hotbar_note({})) == ("Manual", "Macro", "Macro")
    assert r.hotbar_tip(slots[0]) == "Hellfire (charge 3) — Manual; hold to charge" and r.hotbar_tip({"name": "X"}) == "X — Macro"
    assert (r.hotbar_key(slots[1]), r.hotbar_level(slots[1]), r.hotbar_level({})) == ("2", "Lv 20", "Lv —")
    assert r.hotbar_copy(view).split("\n") == [
        "1: Hellfire (charge 3) (manual hold to charge)", "2: Flame Scattershot › Fire Wall › Bittercold Wind › Frost (macro)",
        "3: Element Enhancement › Cold Storm › Wish of Concentration › Blaze (macro)",
        "4: Winter's Shackles › Delayed Explosion › Frost Burst › Firestorm (macro)", "Suggested macro key: Right-click"]
    assert r.hotbar_reserve(view).startswith("Reserve <span style='font-family: monospace;'>Right-click</span> for the macro")
    # the macro: each key once, the skills it holds, the manual skill, the estimate and the priority
    lines = r.macro_lines(view)
    assert [s["binding"] for s in lines] == ["2", "3", "4"] and [len(r.held(s)) for s in lines] == [4, 4, 4]
    twice = {"rotation": {"steps": [lines[0], lines[0], {"binding": "Assign key", "key": "a"}, {"binding": "Assign key", "key": "b"},
                                    {"binding": "Assign key", "key": "a"}]}}
    assert [s.get("key") or s["binding"] for s in r.macro_lines(twice)] == ["flame_scattershot", "a", "b"]
    assert r.held({"stack": []}) == [] and r.held({"name": "One"}) == [{"name": "One"}]          # an empty stack holds none
    assert r.chain_note({"chain_of": "Blaze"}) == "Blaze’s chain: press Blaze again while the chain is open"
    assert [r.cast_note(i, n) for i, n in ((0, 1), (0, 4), (2, 4))] == [
        "", "cast first, skipped if it cannot be cast", "then this one, skipped if it cannot be cast"]
    hellfire = r.manual_skills(view)[0]
    assert r.manual_words(hellfire) == "Hold this skill’s key to charge level 3, then release. Never add it as a macro tap."
    assert r.manual_words({"charged": True}) == "Hold this skill’s key to charge, then release. Never add it as a macro tap."
    assert r.manual_words({"condition": "at 60% MP"}) == "Press manually when ready. Use at 60% MP."
    assert r.macro_estimate(view) == ("Estimated macro + manual execution: 96.6% of the ideal priority rotation. This assumes "
                                      "you use the manual skills, including their charges.")
    shares = [r.macro_estimate({"macro": m}).split(": ")[1].split(" of")[0] for m in (
        {"dps_macro": 5, "dps_priority": 0}, {"dps_macro": 0, "dps_priority": 0}, {"dps_macro": None, "dps_priority": 4},
        {"dps_priority": 4}, {"dps_macro": -1, "dps_priority": 0})]
    assert shares == ["Infinity%", "—", "0.0%", "—", "-Infinity%"]                                 # as JavaScript divides
    assert r.macro_estimate({"macro": {"needs_refresh": True}}) == r.REFRESH
    assert r.priority_items(view)[0] == ("Blaze", ["with Element Enhancement timing"]) and len(r.priority_items(view)) == 15
    assert r.priority_items({"rotation": {"priority": [{"name": "C", "chain_of": "B", "condition": "x"}]}}) == [("C", ["B’s chain", "x"])]
    assert r.macro_copy(view).split("\n") == [
        "1. hotbar key 2: Flame Scattershot > Fire Wall > Bittercold Wind > Frost; delay 10 ms",
        "2. hotbar key 3: Element Enhancement > Cold Storm > Wish of Concentration > Blaze; delay 10 ms",
        "3. hotbar key 4: Winter's Shackles > Delayed Explosion > Frost Burst > Firestorm; delay 10 ms",
        "Manual: Hellfire (charge 3) (1; hold to charge)"]
    assert r.macro_instructions(view)[3].endswith("(suggested: <span style='font-family: monospace;'>Right-click</span>).")
    assert r.has_macro(view) and not r.has_macro({"macro": {}}) and r.has_macro({"macro": {}, "rotation": {}})


def test_the_hotbar_window(qapp, view):
    app, page, windows = _windows(view, "hotbar")
    texts = _texts(windows)
    assert r.HOTBAR_SUB in texts and r.HOTBAR_INTRO in texts and r.HOTBAR_MANUAL in texts and r.hotbar_reserve(view) in texts
    slots = _shown(windows, w.HotbarSlot)
    assert [s.objectName() for s in slots] == ["hotbarManual"] + ["hotbarSlot"] * 3 + ["hotbarEmpty"] * 8
    assert slots[0].toolTip() == "Hellfire (charge 3) — Manual; hold to charge"
    assert [l.text() for l in _shown(slots[0], QLabel)] == ["Hold to charge"] and _shown(slots[4], QLabel)[0].text() == "+"
    icons = [s.findChildren(w.HotbarIcon)[0] for s in slots[:4]]
    assert [(i.key, i.level, i.width()) for i in icons] == [("1", "Lv 20", 58), ("2", "Lv 20", 58), ("3", "Lv 20", 58), ("4", "Lv 14", 58)]
    settle(lambda: all(i.pixmap is not None for i in icons))
    assert len({s.width() for s in slots}) == 1                                    # twelve columns alike
    name = slots[1].findChildren(w.AnywhereText)[0]
    assert name.text == "Flame Scattershot › Fire Wall › Bittercold Wind › Frost"
    assert name.heightForWidth(40) > name.heightForWidth(400)                     # a word wider than the line breaks
    scroller = _shown(windows, w.Across)[0]
    settle(lambda: scroller.height() > 100)
    assert scroller.widget().minimumSizeHint().width() >= 24 + 12 * 70            # scrolled across on a narrow window
    _button(windows, "Copy as text").click()
    assert windows.copied == [r.hotbar_copy(view)]
    _app, _page_, empty = _windows({k: v for k, v in view.items() if k != "hotbar"}, "hotbar")
    assert r.NO_HOTBAR in _texts(empty) and _button(empty, "Copy as text") is None


def test_the_macro_window(qapp, view):
    app, page, windows = _windows(view, "macro")
    texts = _texts(windows)
    titles = [label.text() for label in _shown(windows, QLabel, "winTitle")]
    assert titles == ["SKILL MACRO & ROTATION"] and "Macro" in texts and "Save to Right-click in game" in texts
    assert any(text.startswith("<ol") and "Skill Queue" in text for text in texts)
    assert [l.text() for l in _shown(windows, QLabel, "macroNumber")] == ["1", "2", "3"]
    assert [l.text() for l in _shown(windows, QLabel, "macroDelay")] == ["10", "10"]
    icons = _shown(windows, w.HotbarIcon)
    assert [i.width() for i in icons] == [72] * 12 + [58] and [i.key for i in icons[:5]] == ["2", "2", "2", "2", "3"]
    assert texts.count("cast first, skipped if it cannot be cast") == 3 and texts.count("then this one, skipped if it cannot be cast") == 9
    assert "Hotbar key <span style='font-family: monospace;'>2</span>" in texts
    assert r.manual_words(view["rotation"]["manual"][0]) in texts and r.macro_estimate(view) in texts
    for words in (r.MANUAL_HEAD, r.READY_HEAD, r.READY_NOTE):
        assert words in texts
    priority = next(text for text in texts if text.startswith("<ol") and "Flame Arrow" in text)
    assert priority.count("<li>") == 15 and f"<span style='color: {theme.COLORS['muted']};'>(when MP is at least 60%)</span>" in priority
    _button(windows, "Copy as text").click()
    assert windows.copied == [r.macro_copy(view)]
    # the editor above its side on a narrow window (it stacks under 1050 px, after the others), beside it on a wide
    # one, at most 480 px
    split = next(s for s in _shown(windows, w.Split) if any(isinstance(p, QFrame) and p.objectName() == "macroEditor" for p in s.parts))
    editor, side = split.parts
    assert split.narrow is False and split.width() > w.MACRO_NARROW                   # 1,100 px: still side by side
    page.resize(1000, 1500)
    settle(lambda: split.narrow is True)
    QCoreApplication.processEvents()
    assert editor.geometry().bottom() < side.geometry().top()
    page.resize(1500, 1500)
    settle(lambda: split.narrow is False)
    QCoreApplication.processEvents()
    assert editor.width() == 480 and editor.geometry().right() < side.geometry().left()
    _app, _page_, empty = _windows({k: v for k, v in view.items() if k != "rotation"}, "macro")
    assert r.NO_MACRO in _texts(empty) and [l.text() for l in _shown(empty, QLabel, "winTitle")] == ["SKILL MACRO"]


def test_the_genus_words(view, genus_view):
    assert [r.genus_choice(x) for x in ("Fera", "Special", "Bogus", None)] == ["Fera", "Special", "Cogni", "Cogni"]
    assert r.genus_buttons(genus_view) == [("Cogni", "Lv 6"), ("Fera", "Lv 10"), ("Natura", "Lv 3"), ("Varian", "Not recorded"),
                                           ("Special", "Not recorded")]
    assert [r.genus_level({"level": x}) for x in (6, 10, 4.0, 4.5, "6", True, None)] == [
        "Lv 6", "Lv 10 · MAX", "Lv 4", "Level not recorded", "Level not recorded", "Level not recorded", "Level not recorded"]
    assert r.genus_subtitle(genus_view) == "PVE" and r.genus_subtitle(view) == ""
    assert [r._is(x, 4) for x in (4, 4.0, "4", True)] == [True, True, False, False]
    assert r._entries({"10": 1, "2": 2, "b": 3, "02": 4}) == [("2", 2), ("10", 1), ("b", 3), ("02", 4)]   # Object.entries
    cogni = r.genus_group(genus_view, "Cogni")
    assert r.ring_nodes(cogni) == [("filled", "Slot 1: Boss Attack 12"), ("filled", "Slot 2: Cogni Defense 54"),
                                   ("unknown", "Slot 3: Not recorded"), ("filled", "Slot 4: Cogni Damage Boost 3.6%"),
                                   ("unknown", "Slot 5: Not recorded"), ("unknown", "Slot 6: Not recorded"),
                                   ("locked", "Slot 7: Locked · opens at Lv 7"), ("locked", "Slot 8: Locked · opens at Lv 8"),
                                   ("locked", "Slot 9: Locked · opens at Lv 9")]
    rows = r.genus_rows(genus_view, "Cogni")
    assert rows[0] == ["1", "Boss Attack", "12", "0.40%", "Included in the damage model"]
    assert rows[1] == ["2", "Cogni Defense", "54", "—", "Unsupported damage effect or defensive effect"]
    assert rows[2] == ["3", "Not recorded", "—", "—", "—"] and rows[6] == ["7", "Locked · opens at Lv 7", "—", "—", "—"]
    assert r.genus_rows(view, "Fera")[8] == ["9", "Not recorded", "—", "—", "—"]               # no level: nothing locked
    # the note: lines scored, scoring off, nothing recorded; with the roll suggestions' sentence when there are some
    assert r.genus_note(genus_view).startswith("Saved manual lines included &quot;Roll for&quot; below scores every line")
    assert r.genus_note({"genus": {**genus_view["genus"], "enabled": False, "roll_targets": None}}).startswith(
        "Genus scoring disabled for this run The official profile")
    assert r.genus_note(view).startswith("No Genus analysis lines were recorded in this result. The official profile")
    assert "<a href='character'" in r.genus_note(view) and "<a href='gear'" in r.genus_note(view)
    # what to roll for: the best candidates, every slot in order (also with the slots' keys as text, out of order)
    rolls = r.genus_rolls(genus_view, "Cogni")
    assert rolls["best"] and all(gain.startswith(("+", "-")) for _slot, _stat, _grade, gain in rolls["best"])
    assert [row["slot"] for row in rolls["rows"]] == [str(n) for n in range(1, 10)]
    assert rolls["rows"][0]["saved"] == "Boss Attack 12" and rolls["rows"][2]["saved"] == "Not recorded"
    assert rolls["basis"].startswith("midpoint of each line's best listed grade")
    shuffled = json.loads(json.dumps(genus_view))
    slots = shuffled["genus"]["roll_targets"]["genera"]["Cogni"]["slots"]
    shuffled["genus"]["roll_targets"]["genera"]["Cogni"]["slots"] = dict(reversed(list(slots.items())))
    assert [row["slot"] for row in r.genus_rolls(shuffled, "Cogni")["rows"]] == [str(n) for n in range(1, 10)]
    assert r.genus_rolls(view, "Cogni") is None
    # the coverage and the roll targets
    coverage = r.genus_coverage(genus_view)
    assert coverage["line"] == "3 / 5 levels recorded · 5 saved lines · 4 damage effects included"
    assert coverage["rows"][:2] == [["Cogni", "6", "3 / 6 · 3 not recorded", "Lv 7 · slot 7"], ["Fera", "10", "2 / 9 · 7 not recorded", "Catalog level cap"]]
    assert coverage["rows"][3] == ["Varian", "Not recorded", "Unknown", "Enter level"]
    assert coverage["basis"].endswith("Current build applicability and owned collection completion are not verified.")
    targets = r.genus_targets(genus_view)
    assert targets["rows"][0] == ["Cogni · Lv 6", "4", "Cogni Damage Boost", "Cogni Damage Boost 3.6%", "4.8%",
                                  "Catalog range 2.4–4.8%", "Target roll"]
    assert targets["source"].startswith("Catalog basis: ") and r.genus_targets(view) is None and r.genus_coverage(view) is None
    assert r.genus_mix(genus_view) == "Cogni 25.0% · Fera 25.0% · Natura 25.0% · Varian 25.0%"
    assert r.genus_assumptions(genus_view)["mix"].startswith("Assumed equal mix of Cogni, Fera, Natura and Varian: Cogni 25.0%")
    assert r.genus_assumptions(view) is None


def test_the_genus_window(qapp, genus_view):
    app, page, windows = _windows(genus_view, "genus")
    windows.opened_web = []
    windows.open_web = windows.opened_web.append
    texts = _texts(windows)
    assert [label.text() for label in _shown(windows, QLabel, "winTitle")] == ["PET GENUS INSIGHT"] and "PVE" in texts
    note = next(label for label in _shown(windows, QLabel) if "My Character" in label.text())
    note.linkActivated.emit("character")                                          # its links open those pages
    assert windows.opened_web == ["character"]
    buttons = _shown(windows, w.GenusButton)
    assert [b.accessibleName() for b in buttons] == [f"{name} {level}" for name, level in r.genus_buttons(genus_view)]
    assert [b.objectName() for b in buttons] == ["genusOn"] + ["genus"] * 4 and buttons[0].isChecked()
    ring = _shown(windows, w.GenusRing)[0]
    assert ring.nodes == r.ring_nodes(r.genus_group(genus_view, "Cogni")) and ring.level == "Lv 6"
    settle(lambda: ring.width() >= 200)
    image = ring.grab().toImage()
    scale = min(ring.width(), ring.height()) / 320

    def at(index, dy=-11):
        spot = ring._spot(index)
        return QColor(image.pixel(round(spot.x() * scale), round((spot.y() + dy) * scale)))
    assert _near(at(0), theme.COLORS["gold"], 25)                                  # slot 1 saved: gold
    assert _near(at(2), theme.COLORS["panel2"], 6)                                 # slot 3 unrecorded: the panel's colour
    ground = QColor(image.pixel(1, 1))                                             # slot 9 locked: at 40% over the ground
    dim = QColor(*(round(0.4 * a + 0.6 * b) for a, b in zip(_rgb(QColor(theme.COLORS["panel2"])), _rgb(ground))))
    assert _near(at(8), dim.name(), 6)
    point = (ring._spot(0) * scale).toPoint()
    QApplication.sendEvent(ring, QHelpEvent(QEvent.ToolTip, point, ring.mapToGlobal(point)))
    assert QToolTip.text() == "Slot 1: Boss Attack 12"
    QToolTip.hideText()
    tables = _shown(windows, w.GridTable)
    assert len(tables) == 4 and tables[0].cell(0, 0).text() == "SLOT" and tables[0].cell(1, 1).text() == "Boss Attack"
    assert tables[0].cell(7, 1).text() == "Locked · opens at Lv 7" and tables[2].cell(1, 3).text() == "Lv 7 · slot 7"
    for words in ("Cogni Insight · Lv 6", "Roll for · Cogni", "Genus coverage", "Genus roll targets", r.RING_KEY,
                  "3 / 5 levels recorded · 5 saved lines · 4 damage effects included"):
        assert words in texts
    folds = [b for b in windows.findChildren(QToolButton) if b.isVisibleTo(windows) and b.text() in ("Catalog basis", r.ASSUMPTIONS)]
    assert len(folds) == 2 and not any(b.isChecked() for b in folds)                 # closed, as on the web page
    assert _button(windows, "Copy as text") is None
    # another genus: its button, ring, heading and roll suggestions
    buttons[1].click()
    QCoreApplication.processEvents()
    texts = _texts(windows)
    assert windows.state["genusTab"] == "Fera" and "Fera Insight · Lv 10 · MAX" in texts and "Roll for · Fera" in texts
    assert [b.objectName() for b in _shown(windows, w.GenusButton)][1] == "genusOn"
    # the analysis under the ring on a narrow window, beside it on a wide one
    layout = _shown(windows, w.GenusLayout)[0]
    assert layout.narrow and layout.analysis.geometry().top() > layout.ring.geometry().bottom()
    page.resize(1500, 1500)
    settle(lambda: layout.narrow is False)
    QCoreApplication.processEvents()
    assert layout.analysis.geometry().left() > layout.ring.geometry().right()


def test_a_genus_window_without_genus(qapp, view):
    _app, _page_, windows = _windows(view, "genus")
    texts = _texts(windows)
    assert any(text.startswith("No Genus analysis lines were recorded in this result.") for text in texts)
    assert [b.accessibleName() for b in _shown(windows, w.GenusButton)] == [f"{name} Not recorded" for name in r.GENERA]
    assert all(state == "unknown" for state, _words in _shown(windows, w.GenusRing)[0].nodes)
    assert len(_shown(windows, w.GridTable)) == 1 and "Cogni Insight · Level not recorded" in texts
    assert not [b for b in windows.findChildren(QToolButton) if b.isVisibleTo(windows) and b.text() == r.ASSUMPTIONS]
