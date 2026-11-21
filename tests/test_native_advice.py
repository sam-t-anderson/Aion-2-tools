"""An advice's view in the native interface (0.2.444), as pages/advice.js draws it: the top changes, the skill
specialties, the paper doll and each slot's way to its best item, the upgrade path, the arcana, titles and Pantheon
(0.2.445, with the recommended board), and the fights and calibration. Off screen, over the browser tests' kept advice
(tests/browser/kept_advice.json, a made-up Sorcerer's).
"""
import copy
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QCoreApplication, QEvent  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import advice as a_  # noqa: E402
from aion2calc.gui import news  # noqa: E402
from aion2calc.gui.advice_view import AdviceView  # noqa: E402
from aion2calc.gui.database_page import Window  # noqa: E402
from aion2calc.gui.pantheon_board import PantheonBoard  # noqa: E402
from aion2calc.gui.result_windows import icon_path  # noqa: E402
from aion2calc.gui.timers_page import Fold  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_gear import FakeApp, _page  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

KEPT = json.loads((pathlib.Path(__file__).parent / "browser" / "kept_advice.json").read_text(encoding="utf-8"))
NAHMA = "https://aion2hub.com/api/icon/items/1"
BOARD = {"slots": {"colossus": 1, "statue": 4, "artwork": 12}, "gain": 0.163, "faction": "asmodian",
         "note": "Modeled damage value per decoration.",
         "catalog": {"images": "Decoration pictures: the game's item icons, from aion2hub.com", "candidates": {"colossus": 4, "statue": 16}},
         "totals": {"Death [Triniel]": 12, "Destruction [Zikel]": 55, "Justice [Nezekan]": 55},
         "board": {"colossus": [{"id": 1, "short": "Nahma", "kind": "colossus", "grade": "Heroic", "points": 165, "gain": 0.044,
                                 "stats": {"Destruction [Zikel]": 55, "Justice [Nezekan]": 55}, "sources": ["Drops from Nahma"], "icon": NAHMA}],
                   "statue": [{"id": 2, "short": "Transcendent Bakarma", "kind": "statue", "grade": "Unique", "points": 12,
                               "gain": 0.005, "stats": {"Death [Triniel]": 12}, "sources": [], "faction": "asmodian",
                               "icon": "https://example.com/api/icon/items/2"}],
                   "artwork": []},
         "runners_up": {"colossus": [], "statue": [{"short": "Wise", "kind": "statue", "stats": {"Wisdom [Lumiel]": 10}, "gain": 0.001}],
                        "artwork": []}}
OWNED = [{"name": "Chalice of Magic", "grade": "Unique", "enchant": 3, "gain": -0.0123, "verdict": "replace", "equipped": True,
          "skills": {"Flame Arrow": 2, "Hellfire": 1}, "skill_ids": {"Hellfire": 99},
          "deity": {"label": "Space [Israphel]", "points": 18, "source": "catalog"}, "stats": [["Attack", "+12"]],
          "options": {"used": 3, "of": 7}},
         {"name": "Chalice of Vigor", "gain": 0.0074, "verdict": "keep", "equipped": False, "deity": {"label": "Time [Siel]", "points": 20.04}}]
GUARD = {"kinds": ["Damage Tolerance"], "equipped": 0.02, "best_owned": None,
         "best": [{"name": "Iron Wall", "grade": "Epic", "equip": "Damage Tolerance +5%", "owned_bonus": "—", "cut": 0.05, "owned": True},
                  {"name": "Stone Skin", "grade": "Unique", "equip": "—", "cut": 0.04}]}


def _more() -> dict:
    """The kept advice with cards you have, a Defense slot ranked by what its titles take off your hits, and a board."""
    a = copy.deepcopy(KEPT)
    a["arcana"]["slots"]["Arcana Chalice"]["owned"] = copy.deepcopy(OWNED)
    a["titles"]["slots"]["Defense"]["guard"] = copy.deepcopy(GUARD)
    a["pantheon"]["board"] = copy.deepcopy(BOARD)
    return a


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
    assert titles == ["TOP CHANGES", "SKILL SPECIALTIES", "EQUIPMENT", "UPGRADE PATH", "ARCANA", "TITLES", "PANTHEON",
                      "GENUS INSIGHT", "YOUR FIGHTS", "MODEL CALIBRATION"]
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
    assert copied == [a_.top_copy(KEPT), a_.specialties_copy(KEPT), a_.doll_copy(KEPT), a_.path_copy(KEPT), a_.arcana_copy(KEPT),
                      a_.titles_copy(KEPT), a_.pantheon_copy(KEPT)]
    next(b for b in view.findChildren(QPushButton) if b.text() == "Open them on the web page").click()
    fight = next(label for label in view.findChildren(QLabel) if "web:combat-log/analysis/1" in label.text())
    fight.linkActivated.emit("web:combat-log/analysis/1")
    assert opened == ["gear", "combat-log/analysis/1"] and len(links) == 1
    older = AdviceView(None, {**KEPT, "skill_specialties": None, "fights": None, "rotation": {}})
    assert a_.SPECIALTIES_OLD in [label.text() for label in older.findChildren(QLabel)]
    assert a_.NO_FIGHTS in [label.text() for label in older.findChildren(QLabel)]


def test_the_arcana_titles_and_pantheon_words():
    a, more = KEPT, _more()
    # arcana: each slot's variant, the options to chase at their target levels, its gains, and the cards you have
    card = a_.arcana_cards(a)[0]
    assert (card["slot"], card["priority"], card["name"], card["deity"], card["ideal"], card["average"], card["owned"]) == (
        "CHALICE", "#1", "Chalice of Vigor", "Time [Siel] +20", "+11.4%", "+4.0%", [])
    assert card["item"]["enchant"] == 5 and card["options"] == [
        ("Flame Arrow", "2", "https://metabot.gg/web/aion2/skills/15210000.webp"),
        ("Hellfire", "3", "https://metabot.gg/web/aion2/skills/15060000.webp"),
        ("Robe of Flame", "4", "https://metabot.gg/web/aion2/skills/15740000.webp")]
    replace, keep = a_.arcana_cards(more)[0]["owned"]
    assert (replace["name"], replace["gain"], replace["keep"], replace["deity"], replace["deity_tip"], replace["stats"],
            replace["facts"]) == ("Chalice of Magic +3", "-1.2%", False, "Space [Israphel] +18", a_.CATALOG_DEITY, "Attack +12",
                                  "Unique · 3 of 7 option levels · equipped")
    assert replace["options"] == [("Flame Arrow", "2", "https://metabot.gg/web/aion2/skills/15210000.webp"),
                                  ("Hellfire", "1", "https://metabot.gg/web/aion2/skills/99.webp")]     # the card's own skill id first
    assert (keep["name"], keep["keep"], keep["deity"], keep["deity_tip"], keep["options"], keep["facts"]) == (
        "Chalice of Vigor +0", True, "Time [Siel] +20", "this card's stat", [], "in your inventory")
    assert a_.arcana_copy(more) == ("Arcana Chalice: Chalice of Vigor (Time [Siel] +20) — Flame Arrow +2, Hellfire +3, Robe of Flame +4\n"
                                    "  yours: Chalice of Magic +3, Space [Israphel] +18 — Flame Arrow +2, Hellfire +1 (-1.2%, replace)\n"
                                    "  yours: Chalice of Vigor +0, Time [Siel] +20 — no skill options (+0.7%, keep)")
    assert a_.arcana_cards({"arcana": {"slots": {"Arcana Bell": {}, "Arcana Mirror": {"variant": {"name": "M"}}}}})[0]["priority"] == "#0"
    # titles: what is equipped (no gain), the best in slot, a slot ranked by what its titles take off your hits
    attack, defense, other = a_.title_columns(a)
    assert [c["title"] for c in (attack, defense, other)] == ["ATTACK TITLE", "DEFENSE TITLE", "OTHER TITLE"]
    equipped = attack["plates"][0]
    assert (equipped["label"], equipped["name"], equipped["equip"], equipped["gain"]) == ("Equipped", "❖ T ❖", "PvE Damage Boost +3%", None)
    first, second = attack["best"]
    assert (first["label"], first["gain"], second["label"]) == ("Best", ("+6.8%", True), "")
    assert first["how"] == "completing the achievement “Genus Genius”: Reach All Genus Insights Level 10" and first["how_full"].startswith("You earn")
    assert defense["plates"] == [{"label": "Equipped", "empty": True}] and defense["guard"] == {"note": a_.NO_DAMAGE_TITLE, "plates": []}
    assert other["guard"] is None and [p["name"] for p in other["best"]] == ["❖ Empty Closet ❖", "❖ Through Hell and Back ❖"]
    guarded = a_.title_columns(more)[1]["guard"]
    assert guarded["note"] == ("No title for this slot adds damage. Ranked by how much they cut a boss's damage (Damage Tolerance); "
                               "yours: −2.0%.")
    iron, stone = guarded["plates"]
    assert (iron["label"], iron["equip"], iron["owned"], iron["extra"]) == (
        "Best", "Damage Tolerance +5%", "", [("cut", "−5.0% damage taken"), ("owned", "owned")])
    assert (stone["label"], stone["equip"], stone["extra"]) == ("", "", [("cut", "−4.0% damage taken")])
    known = copy.deepcopy(more)
    known["titles"]["owned_known"] = True
    known["titles"]["slots"]["Defense"]["guard"]["best_owned"] = {"name": "Old Shield", "cut": 0.01}
    assert [p["label"] for p in a_.title_columns(known)[0]["plates"]] == ["Equipped", "Best you own"]
    assert a_.title_columns(known)[1]["guard"]["plates"][0]["extra"] == [("cut", "−1.0% damage taken")]
    assert "PvP" not in guarded["note"] and "another player's" in a_.title_columns(
        {"titles": {"slots": {"Attack": {"guard": {"kinds": ["PvP Damage Tolerance"]}}}}})[0]["guard"]["note"]
    collect = a_.titles_collect(a)
    assert [(p["label"], p["name"], p["equip"], p["owned"]) for p in collect] == [
        ("Collect", "❖ Alien ❖", "", "PvE Attack +4"), ("Collect", "❖ Guardian of Altgard ❖", "", "PvE Attack +4")]
    assert a_.titles_copy(a) == "Attack: Unbound by Genus\nDefense: -\nEtc: Empty Closet"
    assert a_.titles_copy(more).split("\n")[1] == "Defense: Iron Wall" and a_.titles_note(a).startswith("List the titles you own")
    assert a_.title_columns({}) is None and a_.titles_collect({}) == []
    # pantheon: the ten deities, the arcana's choices, and the board's stands and list
    tiles = a_.deity_tiles(a)
    assert [t["deity"] for t in tiles][:3] == ["Destruction", "Death", "Wisdom"] and len(tiles) == 10
    illusion = next(t for t in tiles if t["deity"] == "Illusion")
    death = next(t for t in tiles if t["deity"] == "Death")
    assert (illusion["lord"], illusion["sigil"], illusion["points"], illusion["share"], illusion["worth"], illusion["best"],
            illusion["dim"]) == ("KAISINEL", "K", "0", 100.0, "+1.1% / 10", True, False)
    assert (death["points"], death["share"], death["worth"], death["best"], death["dim"]) == ("30", 0.0, "+0.0% / 10", False, True)
    assert a_.deity_choices(a)[0] == {"source": "Arcana Chalice", "pick": "Chalice of Vigor", "deity": "Time [Siel]", "gain": "+0.7%"}
    stands = a_.board_stands(BOARD)
    assert stands["colossus"] == {"set": True, "icon": NAHMA, "name": "Nahma", "points": "+165",
                                  "tip": "Colossus: Nahma — Destruction +55, Justice +55 · +4.4% · Drops from Nahma"}
    assert stands["statues"][0] == {"set": True, "icon": "", "name": "Transcendent …", "points": "+12",   # not aion2hub's: no picture
                                    "tip": "Statue: Transcendent Bakarma — Death +12 · +0.5% · source unknown"}
    assert stands["statues"][1] == {"set": False, "icon": "", "name": "", "points": "stand 2", "tip": "Statue stand 2: no candidate"}
    assert stands["artworks"][0]["points"] == "" and stands["artworks"][11]["tip"] == "Artwork stand 12: no candidate"
    assert a_.board_stands({})["colossus"] == {"set": False, "icon": "", "name": "", "points": "Colossus",
                                                "tip": "Colossus stand: no candidate"}
    listed = a_.board_list(BOARD)
    assert listed["totals"] == [("Destruction", "55", "Destruction [Zikel]"), ("Justice", "55", "Justice [Nezekan]"),
                                ("Death", "12", "Death [Triniel]")] and listed["gain"] == "+16.3%"
    assert [r["head"] for r in listed["rings"]] == ["COLOSSUS · centre · 1/1", "STATUES · inner ring · 1/4", "ARTWORKS · outer ring · 0/12"]
    nahma = listed["rings"][0]["rows"][0]
    assert (nahma["icon"], nahma["colour"], nahma["stats"], nahma["gain"], nahma["sources"]) == (
        NAHMA, "#ee6c2a", [("Destruction", "+55"), ("Justice", "+55")], "+4.4%", "Drops from Nahma")
    bakarma = listed["rings"][1]["rows"][0]
    assert (bakarma["faction"], bakarma["sources"], bakarma["colour"]) == ("asmodian", "source not listed in the catalog", "#e9a43a")
    assert listed["rings"][1]["next_head"] == "Next best statues" and listed["rings"][1]["next"][0]["name"] == "Wise"
    assert listed["rings"][0]["next_head"] == "Next best colossuss" and listed["rings"][2]["rows"] == []   # the web page's words
    assert listed["note"] == ("Modeled damage value per decoration. Decoration pictures: the game's item icons, from aion2hub.com. "
                              "Candidates: 4 colossi, 16 statues, 0 artworks with a known effect (your faction: asmodian).")
    assert a_.board_list({**BOARD, "faction": None, "note": None, "catalog": {}})["note"] == (
        "  Candidates: 0 colossi, 0 statues, 0 artworks with a known effect (faction unknown: both factions' pieces shown).")
    assert a_.pantheon_copy(a) == "Illusion [Kaisinel]: +1.1% per 10\nWisdom [Lumiel]: +0.9% per 10"
    assert a_.pantheon_copy(more).split("\n")[2:] == ["", "Colossus: Nahma (Destruction +55, Justice +55) +4.4% — Drops from Nahma",
                                                       "Statue: Transcendent Bakarma (Death +12) +0.5% — "]
    assert [a_.shortened(x, 5) for x in ("Abcde", "Abcdef", None)] == ["Abcde", "Abcd…", ""]
    assert a_.decor_icon({"icon": NAHMA + "?x"}) == "" and a_.decor_icon({"icon": "https://aion2hub.com/api/icon/items/1234567890123"}) == ""


def _png() -> bytes:
    image = QImage(4, 4, QImage.Format_ARGB32)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def test_the_arcana_titles_and_pantheon_windows(qapp):
    copied = []
    view = AdviceView(None, _more(), clipboard=copied.append)
    view.resize(1240, 4000)
    view.show()
    QCoreApplication.processEvents()
    titles = [w.findChild(QLabel, "winTitle").text() for w in view.findChildren(Window)]
    assert titles[4:8] == ["ARCANA", "TITLES", "PANTHEON", "GENUS INSIGHT"]
    texts = _texts(view)
    for words in ("CHALICE", "#1", "Time [Siel] +20", "TARGET OPTIONS · UNIQUE +5", "Robe of Flame", "YOURS", "Chalice of Magic +3",
                  "replace", "keep", "No skill options", "Unique · 3 of 7 option levels · equipped",                 # arcana
                  "ATTACK TITLE", "BEST IN SLOT", a_.COLLECT_HEAD, "❖ Iron Wall ❖", "owned", "OTHER TITLE",          # titles
                  "KAISINEL", "best for damage", a_.BOARD_HEAD, "COLOSSUS · centre · 1/1",                            # pantheon
                  "source not listed in the catalog"):
        assert any(words in t for t in texts), words
    assert "Next best statues" in [fold.button.text() for fold in view.findChildren(Fold)]
    assert any("−5.0% damage taken" in t for t in texts) and any("ideal" in t and "+11.4%" in t for t in texts)
    # the board: its stands, the one under the pointer, and its pictures through the app's icon cache
    board = view.findChildren(PantheonBoard)[0]
    assert board.paths == {"colossus:0": icon_path(NAHMA)}                      # only aion2hub's item icons
    centre = board.stand_at(board.width() / 2, board.height() / 2)
    assert board.places[centre]["kind"] == "colossus" and board.stand(board.places[centre])["tip"].startswith("Colossus: Nahma")
    assert board.stand_at(1, 1) == -1
    view._icon(icon_path(NAHMA), _png())
    assert not board.pictures[icon_path(NAHMA)].isNull()
    board.grab()                                                                  # drawn with its picture
    for button in (b for b in view.findChildren(QPushButton) if b.text() == "Copy as text"):
        button.click()
    assert copied[4:7] == [a_.arcana_copy(view.advice), a_.titles_copy(view.advice), a_.pantheon_copy(view.advice)]
    # no titles or board in the advice: no Titles window, no board
    bare = AdviceView(None, {**KEPT, "titles": None})
    assert "TITLES" not in [w.findChild(QLabel, "winTitle").text() for w in bare.findChildren(Window)]
    assert not bare.findChildren(PantheonBoard)


def test_gear_and_advice_shows_the_advice_kept(qapp):
    app = FakeApp(kept={"advice": KEPT, "at": 1700000000})
    page = _page(app)
    settle(lambda: page.findChildren(AdviceView))
    view = page.findChildren(AdviceView)[0]
    assert view.advice == KEPT and page.kept_line.isVisibleTo(page)
