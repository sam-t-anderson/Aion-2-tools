"""The Pet Genus Insight editor and the row that reads the game's screen, in the native interface (0.2.442), as
genus-editor.js's ``A2GenusEditor.mount`` and pages/screen-read.js's ``screenReadPanel`` draw them, and both on My
Character's Genus panel: the draft's rules, the editor's tabs, level, ring, slots, JSON and saving, a read of the
game into the draft, and what an optimization asks first. Off screen, with made-up lines and a fake app.
"""
import base64
import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from aion2calc.gui import character as c  # noqa: E402
from aion2calc.gui import genus_editor as g  # noqa: E402
from aion2calc.gui import screen_read as s  # noqa: E402
from aion2calc.gui.genus_editor import GenusEditor  # noqa: E402
from aion2calc.gui.screen_read import ScreenRead  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_character import HITS, FakeApp, _imported, _page, _texts, sorcerer_view  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

STATE = {"Cogni": {"level": 7, "lines": [{"slot": 1, "stat": "Cogni Damage Boost", "value": "3.6%"},
                                         {"slot": 4, "stat": "Attack", "value": "120"}]},
         "Fera": {"level": 10, "lines": []}}


@pytest.fixture(scope="module")
def view():
    return sorcerer_view()


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


def test_the_draft_rules():
    assert g.valid_group(None) and g.valid_group({"level": 3}) and not g.valid_group({"lines": {}}) and not g.valid_group([1])
    assert not g.unusual(STATE) and g.unusual({"Other": {}}) and g.unusual({"Fera": "x"})
    assert g.unusual({"Cogni": {"lines": [{"slot": 0}]}}) and g.unusual({"Cogni": {"lines": [None]}}) and not g.unusual({"Fera": None})
    assert [g.tab_text(STATE, x) for x in ("Cogni", "Natura")] == ["Cogni · Lv 7", "Natura · Not recorded"]
    assert g.slot_row(STATE["Cogni"], 4) == {"slot": 4, "stat": "Attack", "value": "120"} and g.slot_row(STATE["Cogni"], 2) == {}
    assert g.has_line(STATE["Cogni"], 1) and not g.has_line({"lines": [{"slot": "1"}]}, 1)   # slots are numbers
    assert [g.slot_state(STATE["Cogni"], n) for n in (1, 4, 8)] == [(False, "Analysis line"), (False, "Genus damage-line slot"),
                                                                    (True, "Opens at level 8")]
    assert g.slot_state(None, 1) == (True, "Enter the Insight level first") and g.slot_state({"level": "7"}, 1)[0]
    # the level typed: a whole level from 0 to 10, or empty to remove it (only without lines)
    state = json.loads(json.dumps(STATE))
    assert g.level_change(state, "Cogni", "") == g.KEEP_LINES and state["Cogni"]["level"] == 7
    assert g.level_change(state, "Cogni", "11") == g.BAD_LEVEL and g.level_change(state, "Cogni", "2.5") == g.BAD_LEVEL
    assert g.level_change(state, "Cogni", "9") == "" and state["Cogni"]["level"] == 9
    assert g.level_change(state, "Fera", "") == "" and "Fera" not in state
    assert g.level_change(state, "Natura", "0") == "" and state["Natura"] == {"level": 0, "lines": []}
    # a read of the game: its genus chosen, the slots it read replacing those, what to check marked
    flags = {}
    read = {"kind": "genus", "genus": "Cogni", "level": 8, "notes": ["Two lines overlapped.", "The level was not read."],
            "lines": [{"slot": 4, "stat": "Cogni Damage Boost", "value": "5.2%", "check": "the value"},
                      {"slot": 8, "stat": "Attack", "value": 90}, {"slot": 12, "stat": "x", "value": "y"}]}
    assert g.apply_read(state, flags, "Fera", read) == ("Cogni", "Read from the game: 2 lines of Cogni Insight, level 8, 1 to "
                                                       "check (marked). Nothing is saved until you press Save genus lines. "
                                                       "Two lines overlapped.")
    assert state["Cogni"] == {"level": 8, "lines": [{"slot": 1, "stat": "Cogni Damage Boost", "value": "3.6%"},
                                                    {"slot": 4, "stat": "Cogni Damage Boost", "value": "5.2%"},
                                                    {"slot": 8, "stat": "Attack", "value": "90"}]}
    assert flags == {"Cogni": {4: "the value"}}
    assert g.apply_read(state, flags, "Cogni", {"kind": "genus", "genus": "Varian", "lines": [{"slot": 3}]})[1] == (
        "Read from the game: 1 line of Varian Insight, level not read (set to 3: correct it if needed). Nothing is saved "
        "until you press Save genus lines.")
    assert g.apply_read(state, flags, "Cogni", {"kind": "titles"}) is None
    assert g.json_text({"Fera": {"level": 2.0}}) == '{\n  "Fera": {\n    "level": 2\n  }\n}'


def test_the_genus_editor(qapp):
    saves = []
    editor = GenusEditor(STATE, saves.append)
    editor.resize(1000, 900)
    editor.show()
    QCoreApplication.processEvents()
    assert [t.text() for t in editor.tabs] == ["Cogni · Lv 7", "Fera · Lv 10", "Natura · Not recorded", "Varian · Not recorded",
                                               "Special · Not recorded"]
    assert editor.tabs[0].isChecked() and editor.level.text() == "7" and not editor.is_dirty()
    assert [state for state, _words in editor.ring.nodes] == ["filled", "unknown", "unknown", "filled"] + ["unknown"] * 3 + ["locked"] * 2
    assert editor.fields[(1, "stat")].text() == "Cogni Damage Boost" and editor.fields[(4, "value")].text() == "120"
    assert not editor.fields[(8, "stat")].isEnabled() and editor.fields[(8, "stat")].placeholderText() == "Cogni Damage Boost"
    assert [b.isEnabled() for b in editor.clears] == [True, False, False, True] + [False] * 5
    for words in (g.INTRO, g.LEVEL_HINT, g.RING_KEY, g.COPY_NOTE, g.JSON_NOTE):
        assert words in [label.text() for label in editor.findChildren(QLabel)]
    # a line typed: the draft, the JSON and the ring follow, and the editor is not saved
    editor.fields[(2, "stat")].setText("Attack")
    editor.fields[(2, "stat")].textEdited.emit("Attack")
    assert editor.state["Cogni"]["lines"][-1] == {"slot": 2, "stat": "Attack", "value": ""} and editor.is_dirty()
    assert json.loads(editor.json_box.toPlainText()) == editor.state and editor.ring.nodes[1][0] == "filled"
    editor.clears[0].click()
    assert [x["slot"] for x in editor.state["Cogni"]["lines"]] == [4, 2]
    # the level: a whole level from 0 to 10, never removed under saved lines
    editor.level.setText("12")
    editor.level.setModified(True)
    editor.level.editingFinished.emit()
    assert editor.status.text() == g.BAD_LEVEL and editor.level.text() == "7"
    editor.tabs[1].click()
    assert editor.selected == "Fera" and editor.status.text() == "" and editor.ring.level == "Lv 10 · MAX"
    # the JSON: what does not parse, what is not an object, then a draft applied
    editor.json_box.setPlainText("{bad")
    assert editor.json_draft == "{bad"
    editor.apply_button.click()
    assert editor.status.text().startswith("JSON could not be applied: ")
    editor.save_button.click()
    assert editor.status.text() == g.APPLY_FIRST and not saves
    editor.json_box.setPlainText("[1]")
    editor.apply_button.click()
    assert editor.status.text() == "JSON could not be applied: " + g.NOT_OBJECT
    editor.json_box.setPlainText('{"Varian": {"level": 4, "lines": [{"slot": 2, "stat": "Attack", "value": "50"}]}}')
    editor.apply_button.click()
    assert editor.status.text() == g.APPLIED and editor.state == {"Varian": {"level": 4, "lines": [{"slot": 2, "stat": "Attack", "value": "50"}]}}
    # saving: busy until the app answers, then saved, or why not
    editor.save_button.click()
    assert saves == [editor.state] and editor.save_button.text() == "Saving…" and not editor.save_button.isEnabled()
    assert not any(t.isEnabled() for t in editor.tabs) and editor.status.text() == g.SAVING
    editor.not_saved("Invalid genus slot")
    assert editor.status.text() == "Not saved: Invalid genus slot" and editor.save_button.isEnabled() and editor.is_dirty()
    editor.save_button.click()
    editor.saved({"Varian": {"level": 4, "lines": [{"slot": 2, "stat": "Attack", "value": "50"}]}})
    assert editor.status.text() == g.SAVED and not editor.is_dirty()
    # a read of the game: its tab chosen, the slot to check marked until it is typed in
    assert editor.apply_read({"kind": "genus", "genus": "Natura", "level": 5,
                              "lines": [{"slot": 3, "stat": "Natura Damage Boost", "value": "2.1%", "check": "the stat"}]})
    assert editor.selected == "Natura" and editor.tabs[2].isChecked() and editor.is_dirty()
    assert editor.flag_notes[2].text() == "Check: the stat" and editor.slot_frames[2].property("gflag")
    assert editor.status.text().startswith("Read from the game: 1 line of Natura Insight, level 5, 1 to check (marked).")
    editor.fields[(3, "value")].textEdited.emit("2.2%")
    assert editor.flag_notes[2] is None and not editor.slot_frames[2].property("gflag")
    assert not editor.apply_read({"kind": "titles"})
    editor.json_box.setPlainText("{}")                               # a JSON draft not applied: no read taken
    assert not editor.apply_read({"kind": "genus", "genus": "Fera", "lines": []}) and editor.status.text() == g.SAVE_FIRST
    # older data that is no object: kept in the JSON to repair, nothing else editable
    repair = GenusEditor([1, 2], saves.append)
    assert repair.status.text() == g.REPAIR and repair.is_dirty() and not repair.level.isEnabled()
    assert json.loads(repair.json_box.toPlainText()) == [1, 2]


class ReadApp:
    """The app as the read row asks it: whether reads work here, the reads since, and a read's record."""

    def __init__(self, available=True, reads=()):
        self.available, self.reads, self.posts, self.gets = available, list(reads), [], []

    def get(self, path, timeout=None):
        self.gets.append(path)
        if not self.available:
            return {"available": False, "message": "Reading the game screen needs Windows 10 or later.", "reads": []}
        return {"available": True, "message": "", "latest": 0, "reads": list(self.reads)}

    def post(self, path, body, timeout=None):
        self.posts.append((path, body))
        if body["action"] == "image" and body["image"].startswith("data:image/bmp"):
            raise ValueError("That is not a picture")
        return {"id": 99, "kind": "genus", "genus": "Fera", "level": 6, "lines": [{"slot": 1, "stat": "Attack", "value": "5", "check": "x"}]}


def test_the_screen_read_row(qapp, tmp_path, monkeypatch):
    monkeypatch.setitem(s.TAKEN, "genus", 0)
    off = ScreenRead(ReadApp(available=False), "genus", lambda record: None)
    off.show()
    settle(lambda: not off.button.isEnabled())
    assert off.status.text() == "Reading the game screen needs Windows 10 or later." and not off.choose.isEnabled()
    taken = []
    reads = [{"id": 5, "kind": "genus", "genus": "Cogni", "level": 7, "lines": [{"slot": 1, "check": "the value"}, {"slot": 2}]},
             {"id": 6, "kind": "titles", "titles": ["A"]}]
    app = ReadApp(reads=reads)
    row = ScreenRead(app, "genus", taken.append)
    row.show()
    settle(lambda: taken)
    QCoreApplication.processEvents()
    assert taken == [reads[0]] and app.gets[0] == "/api/screen-read?since=0" and s.TAKEN["genus"] == 6
    assert row.status.text() == "Read Cogni Insight Lv 7: 2 lines, 1 to check."    # a Title page is the other row's
    row.take(reads[0])
    assert len(taken) == 1                                                    # each read taken once
    row.take({"id": 7, "kind": "titles", "titles": []})                       # one read here that is a Title page
    assert row.status.text() == s.other_text("genus") and len(taken) == 1
    asked = len(app.gets)
    row.poll()
    row.poll()                                                                # one asking at a time
    settle(lambda: not row.polling)
    assert len(app.gets) == asked + 1
    assert s.read_text(reads[0])[0] == "Read Cogni Insight Lv 7: 2 lines, 1 to check."
    assert s.read_text({"kind": "titles", "titles": ["A", "B"], "unacquired_only": True})[0] == (
        "Read a page of the Title window: 2 titles, “Show unacquired titles only” ticked.")
    assert s.read_text({"error": "No game window", "seen": ["a", "b"]}) == ("No game window", ["a", "b"])
    assert s.read_text({})[0] == "Nothing was recognised on the screen."
    # the game screen after a countdown, a screenshot chosen, and one pasted
    row.read_screen()
    assert not row.button.isEnabled() and row.status.text() == "Reading in 3… switch to the game now."
    settle(lambda: len(taken) == 2)
    assert app.posts[0] == ("/api/screen-read", {"action": "read", "delay": 3}) and row.button.isEnabled()
    assert row.status.text() == "Read Fera Insight Lv 6: 1 line, 1 to check."
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    row.read_file(str(shot))
    settle(lambda: len(app.posts) == 2)
    assert app.posts[1][1] == {"action": "image", "image": "data:image/png;base64," + base64.b64encode(shot.read_bytes()).decode()}
    bad = tmp_path / "shot.bmp"
    bad.write_bytes(b"BM")
    row.read_file(str(bad))
    settle(lambda: row.status.text() == "Not read: That is not a picture")
    monkeypatch.setattr(s, "MOST_BYTES", 3)
    row.read_file(str(shot))
    assert row.status.text() == "That screenshot is larger than 24 MB."
    image = QImage(4, 4, QImage.Format_RGB32)
    image.fill(QColor("red"))
    QGuiApplication.clipboard().setImage(image)
    row.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_V, Qt.ControlModifier))
    settle(lambda: len(app.posts) == 4)
    assert app.posts[3][1]["image"].startswith("data:image/png;base64,")


def test_my_character_genus_panel(qapp, view, tmp_path):
    app = FakeApp(view)
    app.genus = json.loads(json.dumps(STATE))
    app.jobs["opt"] = {"reads": 2, "log": ["Searching"], "result": {"optimized": view, "summary": {"gain": 0.01}, "diff": ""}}
    page, _store = _page(app, tmp_path)
    _imported(page)
    settle(lambda: page.genus_editor is not None)
    assert "/api/inventory?character=eu%3A7%3Aid0" in app.calls
    editor = page.genus_editor
    assert editor.state == STATE and editor.level.text() == "7"
    reads = page.findChildren(ScreenRead)
    assert len(reads) == 1 and not app.calls.count("/api/screen-read?since=0")   # not asked while the panel is closed
    page.genus_fold.button.setChecked(True)
    settle(lambda: not reads[0].button.isEnabled())                       # this computer cannot read the game
    # an edit not saved: said before anything is sent
    editor.fields[(2, "stat")].textEdited.emit("Attack")
    page.optimize("pve")
    QCoreApplication.processEvents()
    assert c.SAVE_GENUS in _texts(page) and not any(p == "/api/character/optimize" for p, _b in app.posts)
    editor.save_button.click()
    settle(lambda: editor.status.text() == g.SAVED)
    assert app.posts[-1] == ("/api/inventory/genus", {"character": "eu:7:id0", "genus": editor.state})
    assert app.genus["Cogni"]["lines"][-1] == {"slot": 2, "stat": "Attack", "value": ""}
    page.optimize("pve")
    settle(lambda: any(p == "/api/character/optimize" for p, _b in app.posts))
    settle(lambda: page.opt["status"] == "done")
    # lines that could not be loaded: said, and an optimization counting them waits for them
    failing = FakeApp(view)
    failing.get = _failing(failing.get)
    (tmp_path / "other").mkdir()
    other, _store = _page(failing, tmp_path / "other")
    _imported(other)
    other.genus_fold.button.setChecked(True)
    settle(lambda: "Could not load Genus: No inventory here" in _texts(other))
    other.optimize("pve")
    QCoreApplication.processEvents()
    assert c.WAIT_GENUS in _texts(other)
    other.use_genus.setChecked(False)                                    # not counted: nothing to wait for
    other.optimize("pvp")
    settle(lambda: any(p == "/api/character/optimize" for p, _b in failing.posts))
    assert failing.posts[-1][1]["genus"] == {"enabled": False} and HITS[0]["character_id"] == failing.posts[-1][1]["character_id"]


def _failing(get):
    def answer(path, timeout=None):
        if path.startswith("/api/inventory?"):
            raise ValueError("No inventory here")
        return get(path, timeout)
    return answer
