"""The native Gear & Advice page, part 1 (0.2.443): the characters to choose, the advice run and kept, the inventory,
the item panel and the catalog's search, the Genus editor and the Title window pages read, as pages/gear.js shows
them, off screen over a fake app answering as the app does (a made-up character, items and lines).
"""
import json
import os
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import gear as g  # noqa: E402
from aion2calc.gui.gear_page import GearPage  # noqa: E402
from aion2calc.gui.screen_read import TitleReads  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

KEY = "nae:1101:test="
CHARACTERS = [{"key": KEY, "name": "TestSorc", "class_name": "Sorcerer", "region": "nae"},
              {"key": "eu:7:id0", "name": "Example", "class_name": "Sorcerer", "region": "eu"}]
ITEMS = [{"id": "e1", "source": "inventory", "slug": "test-earrings", "name": "Test Earrings", "grade": "Unique",
          "category": "Earrings", "enchant": 5, "rolls": [["Critical Hit", 40]], "rolls_text": "Critical Hit +40",
          "skills": [], "note": "warehouse"},
         {"id": "eq-MainHand", "source": "equipped", "slot": "MainHand", "slug": "test-book", "name": "Test Book",
          "grade": "Legend", "enchant": 10, "rolls_text": "Combat Speed,3.2%", "skills": [["Flame Arrow", 1]]},
         {"id": "eq-x", "source": "equipped", "slot": "Ring1", "slug": None, "name": "Old Ring", "enchant": 0}]
OPTIONS = {"slug": "test-earrings", "name": "Test Earrings", "category": "Earrings", "grade": "Unique", "item_level": 102,
           "arcana": False, "max_enchant": 20, "enchant_known": True,
           "enchant_steps": [{"level": 5, "stats": "Attack +26"}, {"level": 15, "stats": "Attack +80"},
                             {"level": 20, "stats": "Attack +120"}],
           "roll_count": 2, "rolls": [{"stat": "Critical Hit", "range": "+35 – +47", "min": 35, "max": 47, "percent": False, "scored": True},
                                      {"stat": "Damage Boost", "range": "+1% – +2%", "min": 1, "max": 2, "percent": True, "scored": False}],
           "skills": {"pool": ["Blaze"], "others": ["Frost Burst"], "max_level": 2, "base": 9, "per_enchant": 0}}
SUMMARY = {"pages": [{"id": 3, "at": 1700000000, "titles": ["Slayer", "Hero"], "unacquired_only": True},
                     {"id": 4, "at": 1700000060, "titles": ["Pioneer"], "unacquired_only": None}],
           "unacquired": ["Slayer", "Hero"], "owned": ["Pioneer", "Champion"], "basis": "catalog", "faction": "elyos",
           "faction_titles": 4, "collection": {"owned": 2, "total": 4},
           "notes": ["1 page did not show whether “Show unacquired titles only” was ticked: choose it for each in the list of pages."]}


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


class FakeApp:
    """The app as Gear & Advice asks it. ``kept`` is the advice kept (or None); the advice job ends after ``reads``."""

    def __init__(self, kept=None, reads=2):
        self.kept, self.reads = kept, reads
        self.calls, self.posts = [], []
        self.inventory = {"class": "sorcerer", "items": json.loads(json.dumps(ITEMS)), "genus": {}, "titles_owned": ["Hero"]}
        self.advice = {"character": {"name": "TestSorc"}, "dps": 41000}

    def get(self, path, timeout=None):
        self.calls.append(path)
        if path == "/api/characters":
            return json.loads(json.dumps(CHARACTERS))
        if path.startswith("/api/inventory?character="):
            return json.loads(json.dumps(self.inventory))
        if path.startswith("/api/advice/last?"):
            if self.kept is None:
                raise ValueError("No advice kept")
            return json.loads(json.dumps(self.kept))
        if path.startswith("/api/items?search="):
            return [{"slug": "test-earrings", "name": "Test Earrings", "grade": "Unique", "category": "Earrings", "item_level": 102}]
        if path.startswith("/api/items/test-earrings/options?class="):
            return json.loads(json.dumps(OPTIONS))
        if path.startswith("/api/items/"):
            raise ValueError("not in the catalog")
        if path.startswith("/api/screen-read/titles?"):
            return json.loads(json.dumps(SUMMARY))
        if path.startswith("/api/screen-read?since="):
            return {"available": False, "message": "Reading the game screen works on Windows only.", "reads": []}
        if path.startswith("/api/jobs/adv"):
            self.reads -= 1
            if self.reads > 0:
                return {"status": "running", "log": ["your recorded fights", "scoring the character as it is"]}
            return {"status": "done", "result": self.advice}
        raise AssertionError(path)

    def post(self, path, body, timeout=None):
        self.posts.append((path, json.loads(json.dumps(body))))
        if path == "/api/advice":
            return {"job": "adv"}
        if path == "/api/screen-read":
            return json.loads(json.dumps(SUMMARY))
        if path == "/api/inventory/genus":
            self.inventory["genus"] = body["genus"]
        if path == "/api/inventory/titles":
            self.inventory["titles_owned"] = [t for t in body["titles"] if t.strip()]
        return json.loads(json.dumps(self.inventory))


def _page(app, **kwargs):
    page = GearPage(app, **kwargs)
    page.advising.interval_ms = 10
    page.resize(1300, 2400)
    page.show()
    settle(lambda: page.combo is not None and page.inventory.count() > 3)
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    """The button shown with these words (once a part drawn again has shown it)."""
    def shown():
        return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)
    settle(lambda: shown() is not None)
    return shown()


def test_the_gear_words():
    assert g.character_line(CHARACTERS[0]) == "TestSorc · Sorcerer · nae"
    kept = {"at": 1700000000, "inputs_changed": True, "version_changed": True, "version": "0.2.400"}
    assert g.kept_text(kept).startswith("Your last advice, calculated 20")
    assert g.kept_text(kept).endswith(". Your gear, inventory, Genus lines or titles have changed since. Version 0.2.400 of "
                                      "the app calculated it. <b>Run advice</b> calculates it again with your current gear "
                                      "and fights.")
    assert "An earlier version of the app calculated it." in g.kept_text({"version_changed": True})
    assert g.kept_text({}) == "Your last advice, calculated —. <b>Run advice</b> calculates it again with your current gear and fights."
    running = g.progress({"status": "running", "started": 100.0, "log": [f"step {i}" for i in range(8)]}, 112.6)
    assert running == ("running", "Calculating advice · 12s · <b>step 7</b>", "\n".join(f"step {i}" for i in range(2, 8)))
    assert g.progress({"status": "running", "started": 5.0, "log": []}, 5.0)[1] == "Calculating advice · 0s · <b>Starting…</b>"
    assert g.progress({"status": "done"}, 0) == ("done", g.DONE, g.DONE_NOTE)
    assert g.progress({"status": "error"}, 0)[1] == "Advice did not complete: Unknown error"
    assert [g.rolls_of(e) for e in ITEMS] == ["Critical Hit +40", "Combat Speed,3.2%", ""]
    assert g.rolls_of({"rolls": [["Attack", 3], ["Crit", 1.5]]}) == "Attack +3, Crit +1.5"
    assert [g.skills_of(e) for e in ITEMS] == ["", "Flame Arrow +1", ""]
    assert [g.item_text(e) for e in ITEMS] == ["Test Earrings +5", "Test Book +10", "Old Ring +0"]
    assert [g.slot_text(e) for e in ITEMS] == ["Earrings", "MainHand", "Ring1"]
    assert g.search_path("ear ring&") == "/api/items?search=ear%20ring%26&limit=30"
    assert g.options_path("a/b", None) == "/api/items/a%2Fb/options?class="
    # the item panel: an entry's enchant (at most the item's), rolls, options and note
    ed = g.new_entry(OPTIONS, "test-earrings", {**ITEMS[0], "enchant": 25, "skills": [["Blaze", 2]]})
    assert ed == {"slug": "test-earrings", "id": "e1", "enchant": 20, "rolls": [{"stat": "Critical Hit", "value": 40}, None],
                  "skills": [["Blaze", 2]], "note": "warehouse"}
    assert g.new_entry(OPTIONS, "x", None)["rolls"] == [None, None] and g.new_entry(OPTIONS, "x", None)["id"] is None
    assert g.slots(OPTIONS, 5) == 9 and g.used({"skills": [["a", 2], ["b", "x"], ["c", "1"]]}) == 3
    assert [g.step_text(OPTIONS, n) for n in (0, 4, 5, 14, 15, 18, 20)] == [
        "", "", "Attack +26", "Attack +26", "Attack +80", "Attack +80", "Attack +80, then Attack +120"]
    assert g.heading(OPTIONS, ed) == ("Test Earrings", "Earrings · item level 102 · Unique", "editing your inventory entry")
    assert g.enchant_note(OPTIONS, {"enchant": 0}) == "enhances to +20"
    assert g.enchant_note({**OPTIONS, "enchant_known": False}, {"enchant": 0}) == "the catalog lists no enhancement limit for this item"
    assert g.enchant_note(OPTIONS, {"enchant": 5}) == "+5: Attack +26"
    assert g.roll_choices(OPTIONS) == [("", "— not entered —"), ("Critical Hit", "Critical Hit (+35 – +47)"),
                                       ("Damage Boost", "Damage Boost (+1% – +2%) · not scored")]
    assert g.skills_note(OPTIONS, ed) == "One option reaches +2; the pool lists what this item rolls for your class."
    arcana = {**OPTIONS, "arcana": True, "grade": "Legend", "skills": {"pool": [], "others": ["Frost"], "max_level": 4, "base": 3, "per_enchant": 1}}
    assert g.skills_note(arcana, {"enchant": 2}) == ("A Legend card holds 3 option levels plus one per enchant level, 5 at +2, "
                                                     "at most +4 on one skill.")
    assert g.skill_groups(OPTIONS) == [("This item's option pool", ["Blaze"]), ("Other skills", ["Frost Burst"])]
    assert g.skill_groups(arcana) == [("Skills", ["Frost"])]
    assert g.problem({"rolls": [{"stat": "Critical Hit", "value": ""}], "skills": []}) == g.ROLL_VALUE
    assert g.problem({"rolls": [None], "skills": [["", 1]]}) == g.SKILL_NAME and g.problem(ed) == ""
    assert g.save_body(KEY, ed) == ("/api/inventory/update", {"character": KEY, "enchant": 20, "rolls": [["Critical Hit", 40]],
                                                              "skills": [["Blaze", 2]], "note": "warehouse", "id": "e1"})
    assert g.save_body(KEY, {**ed, "id": None, "rolls": [{"stat": "Damage Boost", "value": "1.5"}]})[1]["rolls"] == [["Damage Boost", 1.5]]
    assert g.save_body(KEY, {**ed, "id": None})[0] == "/api/inventory/add"
    assert g.save_error("ValueError: Test Earrings enhances to +20") == "Test Earrings enhances to +20"
    # the Title window pages read
    shown = g.title_summary(SUMMARY)
    assert shown["line"] == ("Not acquired yet: <b>2</b> · you own: <b>2</b> · Elyos: 4 titles in the app's catalog · the game "
                             "counts 2 of 4")
    assert shown["owned"] == ["Pioneer", "Champion"] and len(shown["pages"]) == 2 and shown["notes"] == SUMMARY["notes"]
    assert "the titles you own are not worked out yet" in g.title_summary({**SUMMARY, "basis": None})["line"]
    assert g.title_summary({"error": "x"}) == {"error": "x"}
    assert [g.page_choice(p) for p in SUMMARY["pages"]] == ["true", ""]
    assert g.filled(["Pioneer", "Hero"], "Hero\n Slayer \n", add=True) == "Hero\nSlayer\nPioneer"
    assert g.filled(["Pioneer"], "Hero", add=False) == "Pioneer"


def test_the_gear_page_with_its_kept_advice(qapp):
    kept = {"advice": {"dps": 41000}, "at": 1700000000, "inputs_changed": True}
    opened, pages = [], []
    app = FakeApp(kept=kept)
    page = _page(app, show_page=pages.append, open_web=opened.append)
    assert [page.combo.itemText(i) for i in range(2)] == ["TestSorc · Sorcerer · nae", "Example · Sorcerer · eu"]
    settle(lambda: page.advice is not None)
    assert page.kept_line.isVisibleTo(page) and page.kept_line.text().startswith("Your last advice, calculated")
    assert not any(p == "/api/advice" for p, _b in app.posts)                    # kept: not run again
    texts = _texts(page)
    for words in (g.NOTE, "INVENTORY", "GENUS INSIGHT", "TITLES YOU OWN", g.TITLES_LIST_NOTE):
        assert words in texts
    assert any("Test Earrings +5" in t and "warehouse" in t for t in texts)
    edits = [b for b in page.findChildren(QPushButton) if b.text() == "Edit"]
    assert len(edits) == 1 and len([b for b in page.findChildren(QPushButton) if b.text() == "Remove"]) == 1   # added ones only
    _button(page, "Saved advice").click()
    assert opened == [] and pages == ["history"]
    assert page.titles.toPlainText() == "Hero"
    # the titles read: the pages, the counts, a page's choice, Forget, Start over, the list filled and saved
    reads = page.findChildren(TitleReads)[0]
    settle(lambda: reads.summary.get("pages"))
    assert "Not acquired yet: <b>2</b> · you own: <b>2</b>" in " ".join(_texts(reads))
    choice = [b for b in reads.findChildren(type(page.combo)) if b.accessibleName().startswith("Page 2")][0]
    choice.setCurrentIndex(0)
    choice.activated.emit(0)
    settle(lambda: app.posts and app.posts[-1][0] == "/api/screen-read")
    assert app.posts[-1][1] == {"action": "page", "page": 4, "unacquired_only": True, "character": KEY}
    _button(reads, "Add them to the list").click()
    assert page.titles.toPlainText() == "Hero\nPioneer\nChampion" and page.toast.text() == g.LIST_FILLED
    _button(page, "Save titles").click()
    settle(lambda: app.posts[-1][0] == "/api/inventory/titles")
    assert app.posts[-1][1] == {"character": KEY, "titles": ["Hero", "Pioneer", "Champion"]}
    settle(lambda: page.toast.text() == "Saved")


def test_the_item_panel(qapp):
    app = FakeApp(kept={"advice": {"dps": 1}, "at": 1})
    page = _page(app)
    _button(page, "Edit").click()
    settle(lambda: page.editor is not None)
    assert "/api/items/test-earrings/options?class=sorcerer" in app.calls
    assert page.enchant.count() == 21 and page.enchant.currentText() == "+5"
    assert [(s.currentData(), v.text(), v.isEnabled()) for s, v, _u in page.rolls] == [("Critical Hit", "40", True), ("", "", False)]
    texts = _texts(page)
    assert "editing your inventory entry" in texts and "+5: Attack +26" in texts
    page.enchant.setCurrentIndex(18)
    page.enchant.activated.emit(18)
    assert "+18: Attack +80" in _texts(page) and page.rolls[0][1].text() == "40"                   # what was set stays
    stat, value, unit = page.rolls[1]
    stat.setCurrentIndex(stat.findData("Damage Boost"))
    stat.activated.emit(stat.currentIndex())
    assert (value.text(), value.isEnabled(), unit.text()) == ("1", True, "%")
    _button(page, "Add a skill option").click()
    _button(page, "Save changes").click()
    assert page.editor_message.text() == g.SKILL_NAME
    skill, level = page.skill_rows[0]
    skill.setCurrentIndex(skill.findData("Blaze"))
    level.setCurrentIndex(1)
    stat, value, unit = page.rolls[1]                              # the panel drawn again: what was chosen stays
    assert (stat.currentData(), value.text(), unit.text()) == ("Damage Boost", "1", "%")
    value.setText("1.5")
    _button(page, "Save changes").click()
    settle(lambda: app.posts and app.posts[-1][0] == "/api/inventory/update")
    assert app.posts[-1][1] == {"character": KEY, "enchant": 18, "rolls": [["Critical Hit", 40], ["Damage Boost", 1.5]],
                                "skills": [["Blaze", 2]], "note": "warehouse", "id": "e1"}
    settle(lambda: page.toast.text() == "Saved" and page.editor is None)
    # the catalog's search: Add… opens the panel for a new entry
    page.search_field.setText("earring")
    page.search()
    settle(lambda: page.found.count())
    _button(page, "Add…").click()
    settle(lambda: page.editor is not None)
    assert "adding to your inventory" in _texts(page)
    _button(page, "Add to inventory").click()
    settle(lambda: app.posts[-1][0] == "/api/inventory/add")
    assert app.posts[-1][1]["slug"] == "test-earrings" and app.posts[-1][1]["rolls"] == []
    settle(lambda: page.toast.text() == "Added")
    settle(lambda: page.found.count())                              # the last search stays after an add
    _button(page, "Remove").click()
    settle(lambda: app.posts[-1][0] == "/api/inventory/remove")
    assert app.posts[-1][1] == {"character": KEY, "id": "e1"}


def test_running_the_advice(qapp):
    app = FakeApp(kept=None, reads=3)
    page = _page(app)
    settle(lambda: any(p == "/api/advice" for p, _b in app.posts))   # nothing kept: it runs
    assert app.posts[-1] == ("/api/advice", {"character": KEY})
    settle(lambda: page.advice_job and page.advice_job.get("log"))
    assert not page.run.isEnabled() and page.run.text() == g.CALCULATING and not page.combo.isEnabled()
    assert any(t.startswith("Calculating advice · ") and t.endswith("<b>scoring the character as it is</b>") for t in _texts(page))
    assert g.RUNNING_NOTE in _texts(page)
    settle(lambda: page.advice_job["status"] == "done")
    assert page.advice == app.advice and page.toast.text() == g.DONE_TOAST and page.run.isEnabled()
    _button(page, "View results ↓").click()                               # the advice's place scrolled into view
    # an edit of the Genus lines not saved: said, and nothing run
    page.genus_editor.fields[(1, "stat")].setEnabled(True)
    page.genus_editor.update_line(1, "stat", "Attack")
    page.run_advice()
    assert page.message.text() == g.SAVE_GENUS_FIRST and page.toast.text() == g.SAVE_GENUS_TOAST
    page.genus_editor.save_button.click()
    settle(lambda: page.genus_editor.status.text() == "Genus lines saved. Optimize or run advice again to recalculate.")
    assert page.advice is None and g.GENUS_SAVED in _texts(page) and page.genus_revision == 1
    # lines saved while it runs: the advice is not shown
    app.reads = 50
    page.run_advice()
    settle(lambda: page.advice_job.get("log"))
    page.genus_revision += 1
    app.reads = 1
    settle(lambda: page.advice_job["status"] == "error")
    assert g.GENUS_CHANGED in _texts(page) and page.advice is None
    # another character: its own inventory and advice
    app.kept = {"advice": {"dps": 2}, "at": 1}
    page.combo.setCurrentIndex(1)
    page.combo.activated.emit(1)
    settle(lambda: page.advice is not None)
    assert page.key == "eu:7:id0" and "/api/inventory?character=" + urllib.parse.quote("eu:7:id0", safe="") in app.calls


def test_the_window_draws_gear_and_advice_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("gear"), GearPage) and not isinstance(window.page("gear"), WebPage)
    assert isinstance(window.page("combat"), WebPage)                    # not moved over yet
