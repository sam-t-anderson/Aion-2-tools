"""An advice's view in the native interface (0.2.444), as pages/advice.js draws it: the top changes, the skill
specialties, the paper doll and each slot's way to its best item, the upgrade path, and the fights and calibration.
Off screen, over the browser tests' kept advice (tests/browser/kept_advice.json, a made-up Sorcerer's).
"""
import copy
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import advice as a_  # noqa: E402
from aion2calc.gui import news  # noqa: E402
from aion2calc.gui.advice_view import AdviceView  # noqa: E402
from aion2calc.gui.database_page import Window  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_gear import FakeApp, _page  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

KEPT = json.loads((pathlib.Path(__file__).parent / "browser" / "kept_advice.json").read_text(encoding="utf-8"))


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


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def test_the_advice_words():
    a = KEPT
    assert a_.top_subtitle(a) == "ranked by simulated DPS gain · model calibrated from fights"
    assert a_.top_subtitle({}) == "ranked by simulated DPS gain"
    assert [(mark, gain) for mark, _area, _text, gain in a_.top_rows(a)] == [("⇧", "+30.0%"), ("⇧", "+23.7%")]
    assert a_.top_rows({"top": [{"area": "else", "text": "x", "gain": None}]}) == [("•", "else", "x", "")]
    assert a_.top_copy(a).split("\n")[1] == "gear (upgrade): Amulet: replace with Revelation Amulet (+0) +23.7%"
    # the specialties: what is recommended, every effect's state, the next unlock; none in older advice
    flame = a_.specialty_rows(a)[0]
    assert flame == {"skill": "Flame Arrow · Lv 12", "slots": "2 selection slot(s)", "chosen": [("1", "+20% MP restored", "effect Lv 8")],
                     "every": ["#1 · Lv 8 · Recommended: +20% MP restored", "#2 · Lv 8 · Available: Absorbs 100, 100% HP"],
                     "unlock": "Effect Lv 16\nSelection slot Lv 20"}
    stigma = {"skill_specialties": [{"skill": "Cold Storm", "level": 20, "automatic": True, "effects": [
        {"number": 1, "text": "Root", "unlock": 5, "selected": True, "free": True}, {"number": 2, "text": "x", "unlock": 9}]}]}
    row = a_.specialty_rows(stigma)[0]
    assert (row["slots"], row["chosen"], row["every"][1], row["unlock"]) == (
        "Automatic stigma effects", [("1", "Root", "effect Lv 5 · either")], "#2 · Lv 9 · Locked: x", "All effects unlocked")
    assert a_.specialties_copy(stigma) == "Cold Storm · effective Lv 20: #1: Root (effect Lv 5, either)"
    assert a_.specialty_rows({}) is None
    # the paper doll: a slot's badge (better from the inventory before the next goal), its step, and its way
    assert a_.doll_tile(a, "MainHand")["badge"] == ("goal", "◆ +23.6%") and a_.doll_tile(a, "MainHand")["name"] == "Book"
    worn_better = copy.deepcopy(a)
    worn_better["doll"]["SubHand"].update(wear={"name": "Guard", "enchant": 7}, wear_gain=0.05, steps=[3, 5])
    tile = a_.doll_tile(worn_better, "SubHand")
    assert (tile["badge"], tile["step"], tile["slot_name"]) == (("up", "▲ +5.0%"), "#3", "Off-hand")
    assert a_.first_slot(worn_better) == "SubHand" and a_.first_slot(a) == "MainHand" and a_.first_slot({}) == "MainHand"
    assert a_.doll_copy(worn_better).split("\n")[1] == "SubHand: wear Guard +7; "
    way = a_.slot_way(a, "MainHand")
    assert way["title"] == "MAIN HAND" and way["worn"][1] == [("Combat Speed 3.2%", False)]
    assert way["next"][0]["name"] == "Courage Spellbook" and way["next"][0]["gain"] == "+23.6%"
    assert way["next"][0]["meta"] == "iLv 41 · +15" and way["next"][1] == ["Damage Boost +4.4% – +5.2%", "Weapon Damage Boost +5.9% – +6.8%"]
    assert way["wear"][0] == {"label": "From your inventory", "empty": True}
    kept_item = copy.deepcopy(a)
    kept_item["doll"]["MainHand"].update(next=None, keep={"gain": 0.04})
    assert a_.slot_way(kept_item, "MainHand")["keep"].endswith("(+4.0%): enchant and reroll it, as the upgrade path says.")
    assert [a_.roll_text(x) for x in ({"stat": "Attack", "range": "+3"}, ["Crit", "40"], None, 5)] == ["Attack +3", "Crit 40", "", "5"]
    # the upgrade path: each step's mark, gains and its share of the gain at its end
    steps = a_.path_steps(a)
    assert [(s["step"], s["slot"], s["mark"], s["gain"], s["total"], round(s["share"])) for s in steps] == [
        ("#1", "Off-hand", "⇄", "+30.0%", "+30.0%", 49), ("#2", "Amulet", "⇄", "+23.7%", "+60.8%", 100)]
    assert steps[0]["rolls"] == ["Damage Boost +3.4% – +4%", "Weapon Damage Boost +4.5% – +5.3%"]
    assert a_.path_copy(a) == ("1. SubHand: replace with Fantasy Guard (+0, rolls: Damage Boost +3.4% – +4%, Weapon Damage Boost "
                               "+4.5% – +5.3%, Combat Speed +5.9% – +6.9%, Front Attack +45 – +59) (+30.0%)\n"
                               "2. Amulet: replace with Revelation Amulet (+0) (+23.7%)")
    # the fights: from where, the rotation compared, the recent ones; or why not
    fights = a_.fights(a)
    assert fights["summary"] == "1 saved fight(s): 1 from AbyssLogs."
    assert fights["compared"] == "1 fight(s) compared with the optimal rotation; idle 0% of the time." and len(fights["tips"]) == 4
    assert fights["recent"][0] == {"id": 1, "boss": "Black Smoke Murute", "page": "combat-log/analysis/1", "length": "30 s",
                                   "dps": "1,900", "source": "AbyssLogs", "when": news.when(KEPT["fights"]["recent"][0]["started_at"])}
    imported = a_.fights({"fights": {"count": 1, "recent": [{"boss": "", "imported_at": 1700000000, "duration": 2.5, "dps": 1e4}]}})
    assert imported["recent"][0] == {"id": None, "boss": "fight", "page": "", "length": "3 s", "dps": "10,000", "source": "",
                                     "when": news.when(1700000000000)}
    assert a_.fights({"fights": {"count": 2, "sources": {"session": 2}}, "rotation": {}})["missing"] == a_.NOT_COMPARED
    assert a_.fights({})["missing"] == a_.NO_FIGHTS and a_.fights({})["summary"] == ""
    assert a_.calibration(a)[1] == "community calibration from your log server: 40 fights"
    assert a_.character_lines(a) == ("Sorcerer", "TestSorc · Siel", "1,805")


def test_the_advice_view(qapp):
    copied, opened, links = [], [], []
    view = AdviceView(None, KEPT, opened.append, copied.append, links.append)
    view.resize(1240, 2600)
    view.show()
    QCoreApplication.processEvents()
    titles = [w.findChild(QLabel, "winTitle").text() for w in view.findChildren(Window)]
    assert titles == ["TOP CHANGES", "SKILL SPECIALTIES", "EQUIPMENT", "UPGRADE PATH", "ARCANA, TITLES, PANTHEON AND GENUS",
                      "YOUR FIGHTS", "MODEL CALIBRATION"]
    texts = _texts(view)
    for words in ("gear (upgrade)", "Amulet: replace with Revelation Amulet (+0)", "Flame Arrow · Lv 12", "Black Smoke Murute",
                  "community calibration from your log server: 40 fights", a_.EQUIPMENT_SUB):
        assert any(words in t for t in texts), words
    assert len(view.tiles) == 25 and view.tiles["MainHand"].isChecked()                 # the first slot with a goal
    assert "MAIN HAND" in texts and any("Courage Spellbook" in t for t in texts)
    view.tiles["Amulet"].click()
    assert view.tiles["Amulet"].isChecked() and not view.tiles["MainHand"].isChecked() and "AMULET" in _texts(view)
    view.tiles["MainHand"].click()
    link = next(label for label in view.findChildren(QLabel) if "Courage Spellbook" in label.text() and "href" in label.text())
    link.linkActivated.emit("https://metabot.gg/en/aion-2/items/courage-spellbook")
    assert links == ["https://metabot.gg/en/aion-2/items/courage-spellbook"]
    for button in (b for b in view.findChildren(QPushButton) if b.text() == "Copy as text"):
        button.click()
    assert copied == [a_.top_copy(KEPT), a_.specialties_copy(KEPT), a_.doll_copy(KEPT), a_.path_copy(KEPT)]
    next(b for b in view.findChildren(QPushButton) if b.text() == "Open them on the web page").click()
    fight = next(label for label in view.findChildren(QLabel) if "web:combat-log/analysis/1" in label.text())
    fight.linkActivated.emit("web:combat-log/analysis/1")
    assert opened == ["gear", "combat-log/analysis/1"] and len(links) == 1
    older = AdviceView(None, {**KEPT, "skill_specialties": None, "fights": None, "rotation": {}})
    assert a_.SPECIALTIES_OLD in [label.text() for label in older.findChildren(QLabel)]
    assert a_.NO_FIGHTS in [label.text() for label in older.findChildren(QLabel)]


def test_gear_and_advice_shows_the_advice_kept(qapp):
    app = FakeApp(kept={"advice": KEPT, "at": 1700000000})
    page = _page(app)
    settle(lambda: page.findChildren(AdviceView))
    view = page.findChildren(AdviceView)[0]
    assert view.advice == KEPT and page.kept_line.isVisibleTo(page)
