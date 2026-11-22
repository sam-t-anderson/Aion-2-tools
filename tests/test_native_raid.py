"""The native Raid Planner, its first part (0.2.490, ``gui/raid.py`` and ``gui/raid_page.py``), as raid.js keeps, reads
and changes a plan: the plans kept with the web page's (``a2plans``, ``a2plan-current``, ``a2plan-owners``), a share
code, a file and an ownership backup read, the keyframes, the map's tokens and their dragging, the moment and its
playback, the party buffs and the plan's own fields. The expected values are raid.js's own answers for the same input."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import builds as b  # noqa: E402
from aion2calc.gui import raid as r  # noqa: E402
from aion2calc.gui import raid_page as rp  # noqa: E402
from test_native_settings import FakeApp  # noqa: E402

NOW = 1_700_000_000_000


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def settle(done=lambda: False, rounds=300):
    import time
    for _ in range(rounds):
        QCoreApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if done():
            return True
        time.sleep(0.005)
    return bool(done())


# ------------------------------------------------------------------ the rules
def test_an_encounter_a_place_and_a_keyframe_as_raid_js_reads_them():
    assert r.clean_encounter({"npc_id": "215755", "map_id": [5], "boss": "  Ice Queen  "}) == {
        "npc_id": 215755, "map_id": 5, "boss": "Ice Queen"}
    assert r.clean_encounter({"npc_id": "4.7", "map_id": "1e3", "boss": " "}) == {"npc_id": 4, "map_id": 1}
    assert r.clean_encounter({"npc_id": 0, "map_id": 10 ** 10, "boss": 5}) == {} == r.clean_encounter([1]) == r.clean_encounter(None)
    assert r.clean_encounter({"boss": "é" * 79 + "😀x"})["boss"] == "é" * 79 + "\ud83d"        # cut in UTF-16 units
    assert r.aoe_span({"shape": "line", "length": 0.3}) == 0.3 and r.aoe_span({"radius": 0}) == 0.14
    assert r.aoe_span({"radius": -1}) == 0.005 and r.aoe_span({"radius": "0.3"}) == 0.3
    tk = {"keyframes": [{"t": 10, "x": 0.2, "y": 0.4}, {"t": 20, "x": 0.6, "y": 0.8}]}
    assert r.position(tk, 0) == (0.2, 0.4) and r.position(tk, 30) == (0.6, 0.8)
    assert r.position(tk, 15) == pytest.approx((0.4, 0.6)) and r.position({"keyframes": []}, 5) is None
    assert r.on_map({"from": 5, "until": 9}, 7) and not r.on_map({"from": 5}, 4) and r.on_map({"from": "5"}, 4)
    assert r.drawn({**tk, "hidden": True}, 15) is None and r.drawn({**tk, "until": 12}, 15) is None
    # a keyframe at a tenth of a second; one within 0.05 s moved; kept in time order; a recorded token's time widened
    tk = {"from": 8, "until": 12, "keyframes": [{"t": 10, "x": 0.5, "y": 0.5}]}
    r.set_keyframe(tk, 10.04, 1.5, -1)
    assert tk["keyframes"] == [{"t": 10, "x": 1.0, "y": 0.0}]
    r.set_keyframe(tk, 4.26, 0.25, 0.75)
    r.set_keyframe(tk, 15, 0.1, 0.1)
    assert [k["t"] for k in tk["keyframes"]] == [4.3, 10, 15] and "from" not in tk and "until" not in tk
    untimed = {"keyframes": [{"x": 0.5, "y": 0.5}, {"t": 23.29, "x": 0.5, "y": 0}, {"t": 74.8, "x": 0.6, "y": 0}]}
    r.set_keyframe(untimed, 56.47, 0.8, 0.3)                       # V8's sort: one without a time stays first
    assert [k.get("t") for k in untimed["keyframes"]] == [None, 23.29, 56.5, 74.8]


def test_share_codes_files_and_the_plans_kept():
    plan = r.new_plan("Raid", NOW)
    plan["tokens"] = [{"id": "a", "kind": "player", "label": "Cleric ✓", "keyframes": [{"t": 0, "x": 0.5, "y": 0.5}]}]
    code = r.plan_code(plan)
    assert r.plan_from_code("  " + code.rstrip("=") + "\n") == plan
    with pytest.raises(r.PlanError, match="Failed to execute 'atob'"):
        r.plan_from_code("not base64!")
    with pytest.raises(r.PlanError, match=r.NOT_A_CODE):
        r.plan_from_code(r.plan_code({"format": "other"}))
    # a plan from a file, a code or the server: kept as a new plan, what the planner draws from put in
    doc = {"format": "a2plan", "duration": "90", "tokens": [{"id": "x"}, None, 5, []], "buffs": "no",
           "encounter": {"npc_id": "12", "boss": " Boss "}}
    kept = {}
    key = r.import_doc(doc, kept, NOW, make_id=lambda: "new")
    assert key == "new" and kept["new"] is doc
    assert doc == {"format": "a2plan", "duration": 90, "tokens": [{"id": "x"}, []], "buffs": [],
                   "encounter": {"npc_id": 12, "boss": "Boss"}, "meta": {"updated": NOW}}
    with pytest.raises(r.PlanError, match="Cannot create property 'updated' on string 'x'"):
        r.import_doc({"format": "a2plan", "meta": "x"}, {}, NOW)
    owner = {"id": "abc123", "edit_token": "t" * 20, "revision": 3, "server": "https://logs.example", "url": "https://x/p"}
    assert r.ownership({"owner": owner, "plan": plan}) == (owner, plan)
    for bad in ({**owner, "id": "ab-12"}, {**owner, "edit_token": "short"}, {**owner, "revision": 2.5},
                {**owner, "server": "ftp://x"}):
        with pytest.raises(r.PlanError, match=r.BAD_OWNER):
            r.ownership({"owner": bad, "plan": plan})
    assert r.ownership({"owner": {k: v for k, v in owner.items() if k != "id"}, "plan": plan})  # "undefined" passes
    # the plans' order and names; the plan shown next; an untouched plan
    plans = {"b": {"meta": {"name": "Old", "updated": 1}}, "a": {"meta": {"name": "", "updated": 5},
                                                                  "encounter": {"boss": "Ice Queen"}}}
    assert r.order(plans) == ["a", "b"] and r.plan_label(plans["a"]) == "Untitled — Ice Queen"
    assert r.next_plan_id(plans, "b", "a") == "b" and r.next_plan_id(plans, None, "b") == "b"
    assert r.next_plan_id(plans, "gone", "gone") == "a" and r.next_plan_id({}, None, None) is None
    assert r.is_blank("x", r.new_plan(r.FIRST_PLAN, NOW), {}) and not r.is_blank("x", r.new_plan(r.NEW_PLAN, NOW), {"x": {}})
    assert not r.is_blank("x", {**r.new_plan(r.NEW_PLAN, NOW), "buffs": [{}]}, {})


def test_what_the_page_shows_of_a_plan():
    marker = {"kind": "marker", "label": "a"}
    assert r.glyph(marker) == "a" and r.glyph({"kind": "enemy"}) == "B" and r.glyph({"kind": "player", "cls": "cleric"}) == "C"
    assert r.glyph({"label": ["ab"]}) == "AB" and r.token_title({"kind": "aoe"}) == "AoE zone"
    assert r.token_title({"kind": 0}) == "0" and r.token_name({"cls": "Cleric"}) == "Cleric"
    p = {"duration": 40, "tokens": [{"kind": "player", "label": "Ann", "color": "#123456"}, {"kind": "player", "cls": "Cleric"},
                                    {"kind": "aoe", "hidden": True}, {"kind": "aoe"}],
         "buffs": [{"name": "Bless", "by": "Ann", "start": 4, "end": 14}, {"name": "Song & Dance", "start": "10", "end": 30}]}
    bars = r.buff_bars(p, 40)
    assert [(x["left"], x["width"], x["colour"], x["tip"]) for x in bars] == [
        (10, 25, "#123456", "Bless · Ann"), (25, 50, r.GOLD, "Song & Dance")]
    assert r.buffs_now(p, 12) == ["Bless · Ann", "Song & Dance"] and r.buffs_now(p, 20) == ["Song & Dance"]
    assert r.kinds_shown(p) == [{"kind": "player", "name": "Players", "on": 2, "all": 2},
                                {"kind": "aoe", "name": "AoE zones", "on": 1, "all": 2}]
    assert r.pick_colour(p) == "#e66a5a" and r.marker_label(p) == "A" and r.marker_label({"tokens": [marker] * 9}) == "B"
    assert r.time_words(12.25, p) == "12.3 / 40s" and r.time_words(0, {"duration": 0}) == "0.0 / 1s"
    tk = {"from": 2, "keyframes": [{"t": 2, "x": 0.125, "y": 0.5}, {"t": 7.25, "x": "0.3", "y": None}]}
    assert r.keyframe_rows(tk) == [{"go": 2, "time": "2.0s", "where": "x 13 · y 50", "deletable": True},
                                   {"go": 7.25, "time": "7.3s", "where": "x 30 · y 0", "deletable": True}]
    assert r.keyframes_head(tk) == "Keyframes (position over time) · 2" and r.current_keyframe(tk, 7.2) == 1
    assert r.on_map_words(tk) == "On the map from 2.0s, as the recording had it" and r.on_map_words({}) is None
    assert r.on_map_words({"until": 9}) == "On the map from 0.0s to 9.0s, as the recording had it"
    assert r.export_name({"meta": {"name": "Ice Queen: phase 2!"}}) == "Ice_Queen_phase_2_.a2plan"
    assert r.export_name({}) == "plan.a2plan" and r.colour_field("#ABC") == "#aabbcc" and r.colour_field("#A0B0C0") == "#a0b0c0"
    assert r.colour_field("#12345") == "#000000" and r.colour_field("#11223344") == "#112233" and r.colour_field("red") == "#39c2e0"
    assert [r.fixed(x, 1) for x in (0.05, 0.25, -0.04, -0.0, 2.45)] == ["0.1", "0.3", "-0.0", "0.0", "2.5"]


# ------------------------------------------------------------------ the page
class Picks:
    """``Math.random``'s answers, in turn; after them, others that differ each time (no two ids alike)."""

    def __init__(self, *values):
        self.values, self.n = list(values), 0

    def __call__(self):
        if self.values:
            return self.values.pop(0)
        self.n += 1
        return (0.123 + 0.0137 * self.n) % 1


@pytest.fixture
def made(qapp, tmp_path):
    """A Raid Planner over a fake app, its questions answered yes, its files in ``tmp_path``."""
    fake = FakeApp({("POST", "/api/plans/saved", None): {"ok": True}})
    store = QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)
    asked, chosen = [], {"answer": True, "file": "", "code": "", "colour": "", "copied": []}

    def confirm(words):
        asked.append(words)
        return chosen["answer"]
    picks = Picks()
    page = rp.RaidPage(fake, store=store, confirm=confirm, ask_text=lambda words: asked.append(words) or chosen["code"],
                       choose_file=lambda: chosen["file"], save_file=lambda name: chosen.setdefault("saved", []).append(name)
                       or str(tmp_path / "out.a2plan"), choose_colour=lambda start: chosen["colour"],
                       copy=chosen["copied"].append, now=lambda: NOW, pick=picks)
    page.resize(1400, 1000)
    page.show()
    assert settle(lambda: page.plan is not None)
    yield page, fake, store, asked, chosen, picks
    page.close()


def _plans(store):
    return json.loads(store.value(r.PLANS))


def _shown():
    """What was drawn last, shown: a widget added to a shown layout is shown by a queued call."""
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _texts(page):
    _shown()
    return [w.text() for w in page.findChildren(QLabel) if w.isVisibleTo(page)]


def _button(page, words):
    _shown()
    return next(x for x in page.findChildren(QPushButton) if x.accessibleName() == words and x.isVisibleTo(page))


def test_the_page_opens_on_a_first_plan_and_hands_the_plans_to_the_app(made):
    page, fake, store, *_rest = made
    plans = _plans(store)
    assert list(plans.values()) == [r.new_plan(r.FIRST_PLAN, NOW)] and store.value(r.CURRENT) == page.id
    assert page.plan_box.currentText() == r.FIRST_PLAN and page.name_edit.text() == r.FIRST_PLAN
    assert page.length_field.text() == "60" and page.arena_box.currentText() == "Square" and page.npc_field.text() == ""
    assert page.time_label.text() == "0.0 / 60s" and rp.SELECT_NOTE in _texts(page) and rp.NO_BUFFS in _texts(page)
    assert settle(lambda: fake.sent("POST", "/api/plans/saved"))                  # for the overlay, after 0.8 s
    assert fake.sent("POST", "/api/plans/saved")[-1][2] == {"plans": plans}
    # opened again: the plan it showed, the plan last shown when it is gone, else the newest
    page.leave()
    page.hide()
    page.show()
    assert settle(lambda: page.mounted) and page.id == list(plans)[0]


def test_tokens_added_selected_dragged_and_edited(made):
    page, _fake, store, *_rest, picks = made
    picks.values += [0.1, 0.5, 0.5]                                 # its id, then its place: the middle
    page.class_box.setCurrentIndex(6)
    _button(page, rp.ADD_PLAYER).click()
    tk = page.plan["tokens"][0]
    assert tk == {"id": r.uid(lambda: 0.1), "kind": "player", "label": "Cleric", "cls": "Cleric", "color": "#e66a5a",
                  "keyframes": [{"t": 0, "x": 0.5, "y": 0.5}]}
    assert page.sel == tk["id"] and page.label_edit.text() == "Cleric" and page.cls_box.currentText() == "Cleric"
    assert _plans(store)[page.id]["tokens"] == [tk]
    for n, words in enumerate((rp.ADD_ENEMY, rp.ADD_MARKER, rp.ADD_AOE)):
        picks.values += [0.2 + n / 10, 0.9, 0.9]                     # each its own id, placed down and right
        _button(page, words).click()
    assert [(t["kind"], t["label"], t["color"]) for t in page.plan["tokens"]] == [
        ("player", "Cleric", "#e66a5a"), ("enemy", "Boss", "#d33939"), ("marker", "A", "#e9cf8e"), ("aoe", "AoE", "#e9a43a")]
    assert page.radius_slider.value() == 16
    page.radius_slider.setValue(30)
    assert page.plan["tokens"][3]["radius"] == 0.3 and _plans(store)[page.id]["tokens"][3]["radius"] == 0.3
    # pressing the empty ground lets the selection go; pressing a token selects it; dragging it places it then
    arena = page.arena
    box = arena.frame_box()

    def mouse(kind, fx, fy):
        point = QPointF(box.left() + fx * box.width(), box.top() + fy * box.height())
        QCoreApplication.sendEvent(arena, QMouseEvent(kind, point, point, Qt.LeftButton,
                                                      Qt.LeftButton if kind != QEvent.MouseButtonRelease else Qt.NoButton,
                                                      Qt.NoModifier))
    mouse(QEvent.MouseButtonPress, 0.02, 0.02)
    mouse(QEvent.MouseButtonRelease, 0.02, 0.02)
    assert page.sel is None and rp.SELECT_NOTE in _texts(page)
    page.slider.setValue(125)                                         # 12.5 s
    assert page.t == 12.5 and page.time_label.text() == "12.5 / 60s"
    mouse(QEvent.MouseButtonPress, 0.5, 0.5)                          # the player, over the area beneath it
    assert page.sel == tk["id"]
    mouse(QEvent.MouseMove, 0.2, 0.3)
    mouse(QEvent.MouseButtonRelease, 0.2, 0.3)
    tk = page.find(page.sel)
    assert tk["keyframes"] == [{"t": 0, "x": 0.5, "y": 0.5}, {"t": 12.5, "x": pytest.approx(0.2, abs=0.002),
                                                             "y": pytest.approx(0.3, abs=0.002)}]
    assert [row.objectName() for row in page.frame_rows] == ["rpFrameRow", "rpFrameRowOn"]
    assert "Keyframes (position over time) · 2" in _texts(page)
    # a keyframe gone to and deleted; the place set at the moment; the label, colour and class
    _button(page, "0.0s").click()
    assert page.t == 0 and page.set_button.text() == "Set position at 12.5s"  # the button keeps the moment it was drawn at
    page.slider.setValue(60)
    page.set_here()
    assert [k["t"] for k in tk["keyframes"]] == [0, 6, 12.5] and tk["keyframes"][1]["x"] == pytest.approx(0.356, abs=0.002)
    page.delete_frame(0)
    assert [k["t"] for k in page.find(page.sel)["keyframes"]] == [6, 12.5]
    page.label_edit.setText("Healer")
    page.label_edit.editingFinished.emit()
    page.cls_box.setCurrentIndex(7)
    page.cls_box.activated.emit(7)
    assert page.find(page.sel)["cls"] == "Chanter" and page.find(page.sel)["label"] == "Healer"  # its own label kept
    made[4]["colour"] = "#00FF00"
    page.colour_button.click()
    assert page.find(page.sel)["color"] == "#00ff00"
    # shown on the map: one token, then a kind (half shown, then all)
    page.shown_box.click()
    assert page.find(page.sel)["hidden"] is True and page.kind_boxes["player"].checkState() == Qt.Unchecked
    page.kind_boxes["player"].click()
    assert "hidden" not in page.plan["tokens"][0]
    page.token_boxes[1].click()
    assert page.plan["tokens"][1]["hidden"] is True and "Enemies 0/1" in [x.text() for x in page.kind_boxes.values()]
    page.remove_token()
    assert [t["kind"] for t in page.plan["tokens"]] == ["enemy", "marker", "aoe"] and page.sel is None


def test_the_moment_its_playback_and_the_party_buffs(made):
    page, _fake, store, *_rest = made
    page.add("player")
    page.buff_name.setText("  ")
    page.add_buff()
    assert page.toast.text() == rp.NAME_BUFF and page.plan["buffs"] == []
    page.buff_name.setText(" Bless ")
    page.buff_by.setCurrentIndex(1)
    page.buff_start.setText("2")
    page.buff_end.setText("")
    page.add_buff()
    bf = page.plan["buffs"][0]
    assert (bf["name"], bf["by"], bf["start"], bf["end"], bf["note"]) == ("Bless", "Templar", 2, 0, "")
    page.buff_rows[0]["end"].setText("8")
    page.buff_rows[0]["end"].editingFinished.emit()
    assert page.plan["buffs"][0]["end"] == 8 and _plans(store)[page.id]["buffs"][0]["end"] == 8
    assert page.lane.bars[0]["tip"] == "Bless · Templar" and page.now_words == []
    page.go_to(5)
    assert page.now_words == ["Bless · Templar"]
    # played: a twentieth of a second each tick at the speed chosen, paused at the end
    page.speed_box.setCurrentIndex(3)
    page.speed_box.activated.emit(3)
    page.play()
    assert page.play_button.text() == rp.PAUSE
    page._tick()
    assert page.t == 5.2
    page.t = 59.9
    page._tick()
    assert page.t == 60 and not page.playing and page.play_button.text() == rp.PLAY
    page.to_start()
    assert page.t == 0 and page.slider.value() == 0
    page.buff_rows[0]["remove"].click()
    assert page.plan["buffs"] == []


def test_a_plans_own_fields_new_duplicate_and_delete(made):
    page, _fake, store, asked, chosen, picks = made
    first = page.id
    page.name_edit.setText("Ice Queen")
    page.name_edit.editingFinished.emit()
    assert _plans(store)[first]["meta"]["name"] == "Ice Queen" and page.plan_box.currentText() == r.FIRST_PLAN  # not redrawn
    page.length_field.setText("3")
    page.length_field.editingFinished.emit()
    assert page.plan["duration"] == 5 and page.length_field.text() == "5"
    page.length_field.setText("")
    page.length_field.editingFinished.emit()
    assert page.plan["duration"] == 60
    page.arena_box.setCurrentIndex(1)
    page.arena_box.activated.emit(1)
    assert page.plan["arena"] == {"kind": "circle"}
    page.boss_edit.setText("  Ice Queen  ")
    page.boss_edit.editingFinished.emit()
    page.npc_field.setText("215755")
    page.npc_field.editingFinished.emit()
    assert _plans(store)[first]["encounter"] == {"boss": "Ice Queen", "npc_id": 215755}
    page.notes_edit.setPlainText("Stack left")
    page.notes_edit.setFocus()
    QCoreApplication.sendEvent(page.notes_edit, QEvent(QEvent.FocusOut))
    assert page.plan["meta"]["notes"] == "Stack left"
    picks.values += [0.25]
    page.duplicate()
    assert page.plan["meta"]["name"] == "Ice Queen copy" and page.id == r.uid(lambda: 0.25)
    assert page.plan_box.currentText() == "Ice Queen copy — Ice Queen"
    page.new_plan()
    assert page.plan["meta"]["name"] == r.NEW_PLAN and len(_plans(store)) == 3
    page.plan_box.setCurrentIndex(page.plan_box.findData(first))
    page.plan_box.activated.emit(page.plan_box.findData(first))
    assert page.id == first and page.t == 0 and page.sel is None
    chosen["answer"] = False
    page.delete()
    assert asked == [rp.ASK_DELETE] and first in _plans(store)
    chosen["answer"] = True
    page.delete()
    assert first not in _plans(store) and page.id in _plans(store) and len(_plans(store)) == 2


def test_files_codes_and_an_ownership_backup(made, tmp_path):
    page, _fake, store, asked, chosen, picks = made
    page.add("enemy")
    page.export()
    assert chosen["saved"] == ["My_first_plan.a2plan"]
    written = (tmp_path / "out.a2plan").read_text(encoding="utf-8")
    assert written == b.stringify(page.plan, 2) and json.loads(written)["tokens"][0]["kind"] == "enemy"

    def import_text(text):
        path = tmp_path / "in.json"
        path.write_text(text, encoding="utf-8")
        chosen["file"] = str(path)
        page.import_file()
        return page.toast.text()
    shown = page.id
    assert import_text(json.dumps({"format": "a2plan", "meta": {"name": "From file"}, "tokens": [None, {"id": "z"}]})) == rp.IMPORTED
    assert page.plan["meta"] == {"name": "From file", "updated": NOW} and page.plan["tokens"] == [{"id": "z"}]
    assert page.id != shown and page.plan_box.currentText() == "From file"
    assert import_text(json.dumps({"format": "other"})) == r.NOT_A_PLAN
    assert import_text("null") == "Cannot read properties of null (reading 'format')"
    assert import_text(json.dumps({"format": "a2log"})) == r.NO_MOVEMENT                  # a recording: its fights offered
    assert page.moves == {"file": "in.json", "doc": {"format": "a2log"}, "fights": []}
    assert r.no_fight_words("in.json") in _texts(page)
    assert import_text(json.dumps({"format": "a2plan-owner", "owner": {"id": "x"}, "plan": {"format": "a2plan"}})) == r.BAD_OWNER
    owner = {"id": "abc123", "edit_token": "t" * 24, "revision": 2, "server": "https://logs.example",
             "url": "https://logs.example/plans/abc123"}
    assert import_text(json.dumps({"format": "a2plan-owner", "owner": owner, "plan": {"format": "a2plan",
                                                                                       "meta": {"name": "Mine"}}})) == rp.IMPORTED
    assert json.loads(store.value(r.OWNERS)) == {page.id: owner}
    assert page.published is not None and "revision 2" in page.published.text() and owner["url"] in page.published.text()
    # the share code copied, and read back as a new plan
    page.copy_code()
    assert chosen["copied"] == [r.plan_code(page.plan)] and page.toast.text() == rp.COPIED
    chosen["code"] = chosen["copied"][0]
    page.load_code()
    assert page.toast.text() == rp.LOADED and page.plan["meta"]["name"] == "Mine" and asked[-1] == rp.ASK_CODE
    chosen["code"] = "nope!"
    page.load_code()
    assert page.toast.text() == r.ATOB
    chosen["code"] = ""
    page.load_code()                                                   # cancelled: nothing
    assert page.toast.text() == r.ATOB and page.plan["meta"]["name"] == "Mine"


def test_the_window_draws_the_raid_planner_and_stops_its_playback_when_left(qapp, monkeypatch, tmp_path):
    from aion2calc.gui import interface
    from aion2calc.gui.window import MainWindow
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    window = MainWindow(None)
    page = window.page("raid")
    assert isinstance(page, rp.RaidPage)
    window.show_page("raid")
    page.mount()
    assert not [b_ for b_ in page.findChildren(QPushButton) if "web" in b_.accessibleName()]   # nothing left to the web
    page.play()
    window.show_page("timers")
    assert not page.playing and not page.mounted
    window.close()


# ------------------------------------------------------------------ publishing and browsing (0.2.491)
def test_publishing_words_and_the_browse_view_words():
    original = {"id": "abc123", "edit_token": "t" * 24, "revision": 2, "server": "https://logs.example", "note": "kept"}
    assert r.published_owner(original, {"revision": 3, "url": "https://logs.example/p/abc123"}, "https://other") == {
        "id": "abc123", "edit_token": "t" * 24, "revision": 3, "server": "https://logs.example", "note": "kept",
        "url": "https://logs.example/p/abc123"}
    fresh = r.published_owner(None, {"id": "new123", "edit_token": "e" * 24, "revision": 1}, "https://logs.example")
    assert json.loads(b.stringify(fresh)) == {"id": "new123", "edit_token": "e" * 24, "revision": 1,
                                              "server": "https://logs.example"}          # no url: left out, as JSON does
    assert r.copy_owner({"id": "c", "url": "u"}, "s") == {"id": "c", "edit_token": b._MISSING, "revision": b._MISSING,
                                                          "server": "s", "url": "u"}
    assert json.loads(r.owner_backup(original, {"format": "a2plan"})) == {"format": "a2plan-owner", "version": 1,
                                                                          "owner": original, "plan": {"format": "a2plan"}}
    assert r.safe_url("HTTPS://x") == "HTTPS://x" and r.safe_url("javascript:alert(1)") == "#" and r.safe_url(None) == "#"
    assert r.browse_path(None) == "/api/plans" and r.browse_path({"npc": "215755", "boss": "Ice"}) == "/api/plans?npc=215755"
    assert r.browse_path({"boss": "Ice Queen"}) == "/api/plans?boss=Ice%20Queen"
    menu = [{"boss": "Ice Queen", "npc_id": 215755, "plans": 3}, {"boss": "Unnamed", "plans": "2"}]
    assert [(x["words"], x["npc"], x["lit"]) for x in r.boss_buttons(menu, None)] == [
        ("All", "", True), ("Ice Queen (3)", "215755", False), ("Unnamed (2)", "", False)]
    # browsing a boss: neither All nor that boss is lit (the filter holds no ``npc_id``), but a boss without one is
    assert [x["lit"] for x in r.boss_buttons(menu, {"npc": "215755", "boss": "Ice Queen"})] == [False, False, True]
    assert r.plan_card({"id": "p1", "name": "", "boss": "Ice Queen", "duration": 89.5, "tokens": 4, "has_fight": 1,
                        "classes": ["Cleric", "Templar"]}) == {
        "name": "Plan", "boss": "Ice Queen", "line": "unknown · 90s · 4 tokens · with a fight",
        "classes": ["Cleric", "Templar"], "id": "p1"}
    assert r.visibility_index({"meta": {"visibility": "public"}}) == 1 and r.visibility_index({"meta": {"visibility": "x"}}) == 0
    assert r.import_refusal(None) == "Cannot read properties of null (reading 'meta')"
    assert r.import_refusal("x") == "Cannot create property 'meta' on string 'x'" and r.import_refusal({}) is None


@pytest.fixture
def online(qapp, tmp_path):
    """A Raid Planner whose app answers the log server's questions in turn, its questions answered yes."""
    from test_native_settings import _refused
    published = {"url": "https://logs.example/p/abc123", "id": "abc123", "edit_token": "t" * 24, "revision": 1}
    fake = FakeApp({("GET", "/api/logserver", None): {"url": "https://logs.example/"},
                    ("POST", "/api/plans/saved", None): {"ok": True},
                    ("POST", "/api/plans", None): [published, dict(published, revision=2, edit_token=None),
                                                   _refused("/api/plans", 409, "Plan server refused (409): stale revision"),
                                                   {"url": "https://logs.example/p/copy01", "id": "copy01",
                                                    "edit_token": "c" * 24, "revision": 1},
                                                   {"plan": {"format": "a2plan", "meta": {"name": "Server's"}, "tokens": []},
                                                    "revision": 5}],
                    ("GET", "/api/plans/bosses", None): {"bosses": [{"boss": "Ice Queen", "npc_id": 215755, "plans": 1}]},
                    ("GET", "/api/plans", None): {"plans": [{"id": "pub001", "name": "Queen's dance", "boss": "Ice Queen",
                                                             "author": "Ann", "duration": 120, "tokens": 6,
                                                             "classes": ["Cleric"]}]},
                    ("GET", "/api/plans?npc=215755", None): {"plans": []},
                    ("GET", "/api/plans?id=pub001", None): {"format": "a2plan", "meta": {"name": "Queen's dance"},
                                                            "tokens": [{"id": "q1", "kind": "enemy"}]}})
    store = QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)
    asked, chosen = [], {"answer": True, "copied": []}

    def confirm(words):
        asked.append(words)
        return chosen["answer"]
    page = rp.RaidPage(fake, store=store, confirm=confirm, save_file=lambda name: chosen.setdefault("saved", []).append(name)
                       or str(tmp_path / "backup.json"), copy=chosen["copied"].append, now=lambda: NOW, pick=Picks())
    page.resize(1400, 1000)
    page.show()
    assert settle(lambda: page.plan is not None and page.server() == "https://logs.example")
    yield page, fake, store, asked, chosen
    page.close()


def test_a_plan_published_updated_copied_refreshed_and_backed_up(online, tmp_path):
    page, fake, store, asked, chosen = online
    first = page.id
    assert page.publish_button.text() == r.PUBLISH and r.VISIBILITY_HINT in _texts(page)
    assert not any(b_.accessibleName() == r.REFRESH for b_ in page.findChildren(QPushButton) if b_.isVisibleTo(page))
    page.visibility_box.setCurrentIndex(1)
    page.visibility_box.activated.emit(1)
    assert _plans(store)[first]["meta"]["visibility"] == "public"
    page.publish()
    assert page.pub_line.text() == r.PUBLISHING and not page.publish_button.isEnabled()
    assert settle(lambda: r.OWNERS in store.allKeys())
    owner = json.loads(store.value(r.OWNERS))[first]
    assert owner == {"id": "abc123", "edit_token": "t" * 24, "revision": 1, "server": "https://logs.example",
                     "url": "https://logs.example/p/abc123"}
    assert fake.sent("POST", "/api/plans")[-1][2] == {"plan": page.plan, "visibility": "public"}     # no credential yet
    _shown()
    assert "Published (public):" in page.pub_line.text() and page.publish_button.text() == r.UPDATE
    page.pub_copy.click()
    assert chosen["copied"] == ["https://logs.example/p/abc123"]
    # updated: sent with its credential, its revision kept (the server gave no new token)
    page.publish()
    assert settle(lambda: json.loads(store.value(r.OWNERS))[first]["revision"] == 2)
    assert fake.sent("POST", "/api/plans")[-1][2]["owner"]["revision"] == 1
    assert json.loads(store.value(r.OWNERS))[first]["edit_token"] == "t" * 24
    # refused: said on the line
    page.publish()
    assert settle(lambda: page.pub_line.text() == "Plan server refused (409): stale revision")
    assert page.publish_button.isEnabled()
    # a new copy: a new local plan with its own credential
    _button(page, r.PUBLISH_COPY).click()
    assert settle(lambda: page.toast.text() == r.NEW_COPY)
    assert page.id != first and json.loads(store.value(r.OWNERS))[page.id]["id"] == "copy01"
    assert page.plan["meta"]["name"] == r.FIRST_PLAN
    # refreshed, once asked: the published revision in place of the plan
    chosen["answer"] = False
    _button(page, r.REFRESH).click()
    assert asked[-1] == r.ASK_REFRESH and len(fake.sent("POST", "/api/plans")) == 4
    chosen["answer"] = True
    _button(page, r.REFRESH).click()
    assert settle(lambda: page.plan["meta"].get("name") == "Server's")
    assert json.loads(store.value(r.OWNERS))[page.id]["revision"] == 5 and _plans(store)[page.id]["meta"]["updated"] == NOW
    assert fake.sent("POST", "/api/plans")[-1][2] == {"id": "copy01", "owner": json.loads(store.value(r.OWNERS))[page.id]
                                                      | {"revision": 1}}
    # the private backup, asked first
    _button(page, r.OWNER_BACKUP).click()
    assert asked[-1] == r.ASK_BACKUP and chosen["saved"] == [r.BACKUP_FILE]
    backup = json.loads((tmp_path / "backup.json").read_text(encoding="utf-8"))
    assert backup["format"] == "a2plan-owner" and backup["owner"]["id"] == "copy01" and backup["plan"] == page.plan


def test_published_plans_browsed_filtered_and_opened(online):
    page, fake, store, *_rest = online
    _button(page, r.BROWSE).click()
    assert settle(lambda: page.browse_frame.isVisible()) and not page.frame.isVisible()
    assert [p for _m, p, _b in fake.sent("GET")][-2:] == ["/api/plans/bosses", "/api/plans"]
    texts = _texts(page)
    assert "Queen's dance" in texts and "Ice Queen" in texts and "Ann · 120s · 6 tokens" in texts and "Cleric" in texts
    _button(page, "Ice Queen (1)").click()
    assert settle(lambda: r.NO_PLANS_BOSS in _texts(page))
    assert fake.sent("GET")[-1][1] == "/api/plans?npc=215755"
    _button(page, r.ALL).click()
    assert settle(lambda: "Queen's dance" in _texts(page))
    _button(page, r.OPEN).click()
    assert settle(lambda: page.toast.text() == r.OPENED)
    assert page.frame.isVisible() and page.plan["meta"]["name"] == "Queen's dance" and page.plan["tokens"] == [{"id": "q1", "kind": "enemy"}]
    assert page.plan_box.currentText() == "Queen's dance"
    _button(page, r.BROWSE).click()
    assert settle(lambda: page.browse_frame.isVisible())
    _button(page, r.BACK).click()
    assert page.frame.isVisible() and page.browsing is None


# ------------------------------------------------------------------ a fight compared, recorded movement, a replay (0.2.492)
def test_the_fight_compared_and_the_recordings_words(tmp_path):
    from aion2calc.gui.news import when
    e = {"id": 7, "player": "Ann", "boss": "Ice Queen", "duration": 119.5}
    assert r.fight_option(e) == ("#7 Ann Ice Queen 120s", "7")
    assert r.fight_option({"id": 8, "boss": ""}) == ("#8 0s", "8")         # white space run together, as a select shows it
    actual = r.actual_of({"rotation": [[1.5, "Slash"], [1.7, "Stab"], [30, "Slash"]], "summary": {"duration": 125.2}},
                         "7", e, 60)
    assert actual == {"id": 7, "rotation": [[1.5, "Slash"], [1.7, "Stab"], [30, "Slash"]], "buffs": [], "duration": 125.2,
                      "boss": "Ice Queen", "npc_id": b._MISSING, "map_id": b._MISSING}
    assert r.actual_of({}, "9", {}, "60")["duration"] == "60"                # the plan's own length
    assert r.fight_chosen(actual, e) and not r.fight_chosen(actual, {"id": "7"}) and not r.fight_chosen(None, e)
    assert r.fight_meta([{"id": "7", "boss": "X"}], "7.0") == {"id": "7", "boss": "X"} and r.fight_meta([], "7") == {}
    assert r.cast_ticks(actual, 150) == [1.0, 100 * 1.7 / 150, 20.0]
    assert r.casts_now(actual, 1.6) == ["Slash", "Stab"] and r.casts_now(actual, 10) == []
    assert r.offers_fight(actual) and not r.offers_fight({"boss": "", "npc_id": 0}) and not r.offers_fight(None)
    # Use selected fight: its boss, NPC and map, cleaned; what the fight does not name is left out
    assert r.fight_encounter({"boss": "Old", "map_id": 3}, {"boss": "Ice Queen", "npc_id": "215755"}) == {
        "npc_id": 215755, "boss": "Ice Queen"}
    rows = r.recording_rows({"rows": [
        {"file": "a.a2log.json", "updated": NOW / 1000, "contexts": [
            {"movement": 0, "boss": "X"}, {"movement": 5, "boss": "Ice Queen"}, {"movement": 3, "label": "Run 2"},
            {"movement": 1}, {"movement": 2, "boss": "Z"}]},
        {"file": "b.a2log.json", "updated": NOW / 1000, "contexts": [{"movement": 0}]}]})
    assert rows == [{"id": "a.a2log.json", "label": f"{when(NOW)} · Ice Queen, Run 2, fight +1"}]
    assert r.recording_rows({}) == [] and r.recording_rows({"rows": [{"contexts": [{"movement": 1}]}]})[0]["label"] == "— · fight"
    assert r.fight_to_import({"name": "Ice Queen", "duration": 59.5}) == "Ice Queen · 60 s"
    assert r.no_fight_words("x.a2log.json").startswith("No fight in x.a2log.json holds recorded movement")
    assert r.no_fight_words(b._MISSING).startswith("No fight in this recording holds")
    assert r.showing_words("Mine") == "The planner is showing Mine, a plan you have worked on. What should happen to it?"
    # a replay kept as a new plan, the one shown next
    store = QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)
    with pytest.raises(r.PlanError, match=r.INVALID_REPLAY):
        r.store_replay(store, {"format": "a2plan"}, NOW)
    replay = {"format": "a2plan", "meta": {"name": "Replay", "updated": 1}, "tokens": [], "encounter": {"npc_id": "12"}}
    assert r.store_replay(store, replay, NOW, make_id=lambda: "abc1234") == "abc1234"
    assert store.value(r.CURRENT) == "abc1234" and replay["meta"]["updated"] == 1             # a copy kept
    assert _plans(store)["abc1234"] == {"format": "a2plan", "meta": {"name": "Replay", "updated": NOW}, "tokens": [],
                                        "encounter": {"npc_id": 12}}


@pytest.fixture
def fights(qapp, tmp_path):
    """A Raid Planner whose app has saved fights to compare and saved recordings with movement."""
    from test_native_replay import CATALOG, _casting
    from test_native_settings import _refused
    rows = [{"file": "a.a2log.json", "updated": NOW / 1000, "contexts": [{"movement": 20, "boss": "Ice Queen"}]},
            {"file": "empty.a2log.json", "updated": NOW / 1000, "contexts": [{"movement": 3}]},
            {"file": "bad.a2log.json", "updated": NOW / 1000, "contexts": [{"movement": 3, "label": "Lost"}]}]
    fake = FakeApp({("POST", "/api/plans/saved", None): {"ok": True}, ("GET", "/api/logserver", None): {"url": ""},
                    ("GET", "/api/encounters", None): [[{"id": 7, "player": "Ann", "boss": "Ice Queen", "duration": 119.5},
                                                        {"id": 8, "player": "Bo", "boss": "", "duration": 30}]],
                    ("GET", "/api/encounters/7", None): {"rotation": [[1.5, "Slash"], [1.7, "Stab"], [100, "Slash"]],
                                                         "summary": {"duration": 125.2}},
                    ("GET", "/api/encounters/8", None): _refused("/api/encounters/8", 404, "Encounter 8 not found"),
                    ("GET", r.RECORDINGS_PATH, None): {"rows": rows},
                    ("GET", "/api/sessions?file=a.a2log.json", None): _casting(),
                    ("GET", "/api/sessions?file=empty.a2log.json", None): {"format": "a2log", "segments": [{"duration": 9}]},
                    ("GET", "/api/sessions?file=bad.a2log.json", None): _refused("/api/sessions", 500, "OSError: unreadable"),
                    ("GET", "/static/aoe-shapes.json", None): {"shapes": CATALOG}})
    store = QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)
    page = rp.RaidPage(fake, store=store, now=lambda: NOW, pick=Picks())
    page.resize(1400, 1000)
    page.show()
    assert settle(lambda: page.plan is not None and page.aoe_shapes is not None)
    yield page, fake, store
    page.close()


def _choose(box, index):
    box.setCurrentIndex(index)
    box.activated.emit(index)


def test_a_saved_fight_compared_on_the_plans_timeline(fights):
    page, fake, store = fights
    assert settle(lambda: page.fight_box.count() == 3)
    assert [page.fight_box.itemText(i) for i in range(3)] == [r.NO_FIGHT, "#7 Ann Ice Queen 120s", "#8 Bo 30s"]
    assert r.COMPARE_HEAD in _texts(page) and r.COMPARE_NOTE in _texts(page) and not page.cast_row.isVisible()
    # a fight chosen: its casts on their lane, the plan lengthened to hold it (to the whole second)
    _choose(page.fight_box, 1)
    assert settle(lambda: page.actual is not None)
    assert fake.sent("GET")[-1][1] == "/api/encounters/7"
    assert page.plan["duration"] == 126 and _plans(store)[page.id]["duration"] == 126
    assert page.cast_row.isVisible() and page.cast_lane.ticks == [100 * 1.5 / 126, 100 * 1.7 / 126, 100 * 100 / 126]
    assert page.fight_box.currentIndex() == 1                                  # drawn again with the fight chosen
    page.go_to(1.6)
    assert page.cast_chips == ["Slash", "Stab"] and r.CASTS_NOW in _texts(page)
    page.go_to(50)
    assert page.cast_chips == [] and r.NO_CASTS in _texts(page)
    # Use selected fight: the plan's boss, as the fight names it
    _button(page, r.USE_FIGHT).click()
    assert page.plan["encounter"] == {"boss": "Ice Queen"} and _plans(store)[page.id]["encounter"] == {"boss": "Ice Queen"}
    # one the app cannot read: said; none: the lane gone; another plan: the fight let go
    _choose(page.fight_box, 2)
    assert settle(lambda: page.toast.text() == "Encounter 8 not found") and page.actual is not None
    _choose(page.fight_box, 0)
    assert page.actual is None and not page.cast_row.isVisible() and not page.casts_now.isVisible()
    _choose(page.fight_box, 1)
    assert settle(lambda: page.actual is not None)
    page.new_plan()
    assert page.actual is None and not page.cast_row.isVisible()


def test_recorded_movement_imported_as_a_new_plan(fights):
    page, fake, store = fights
    from aion2calc.gui.news import when
    assert settle(lambda: page.moves_box.count() == 4)
    assert [page.moves_box.itemText(i) for i in range(4)] == [r.CHOOSE_RECORDING, f"{when(NOW)} · Ice Queen",
                                                              f"{when(NOW)} · fight", f"{when(NOW)} · Lost"]
    assert r.MOVES_HEAD in _texts(page) and r.MOVES_NOTE in _texts(page)
    shown = page.id
    _choose(page.moves_box, 1)
    assert page.moves == {"id": "a.a2log.json", "loading": True} and r.LOADING_RECORDING in _texts(page)
    assert settle(lambda: page.fight_pick is not None)
    assert fake.sent("GET")[-1][1] == "/api/sessions?file=a.a2log.json" and page.moves_box.currentIndex() == 1
    assert [page.fight_pick.itemText(i) for i in range(page.fight_pick.count())] == ["Ice Queen · 120 s"]
    _button(page, r.IMPORT_FIGHT).click()
    assert page.toast.text() == r.MOVES_IMPORTED and page.moves is None and page.id != shown
    plan = _plans(store)[page.id]
    assert plan["meta"] == {"name": "Ice Queen", "updated": NOW} and plan["arena"] == {"kind": "circle"}
    assert len(plan["tokens"]) == 19 and plan["duration"] == 120 and page.plan_box.currentText() == "Ice Queen"
    assert [t["label"] for t in plan["tokens"]][:3] == ["Ice Queen", "TestSorc ✓ · Zikel", "TestCleric"]
    assert [t["kind"] for t in plan["tokens"]].count("aoe") == 12                     # the bosses' measured areas
    # a recording without movement, one the app cannot read, and none
    _choose(page.moves_box, 2)
    assert settle(lambda: page.moves.get("fights") == [])
    assert r.no_fight_words(b._MISSING) in _texts(page) and page.fight_pick is None
    _choose(page.moves_box, 3)
    assert settle(lambda: page.moves.get("error") == "OSError: unreadable") and "OSError: unreadable" in _texts(page)
    _choose(page.moves_box, 0)
    assert page.moves is None and r.LOADING_RECORDING not in _texts(page)


def test_a_recording_given_to_import_file(made, tmp_path):
    from test_native_replay import _casting
    page, fake, store, asked, chosen, picks = made
    path = tmp_path / "session-1.a2log.json"
    path.write_text(json.dumps({**_casting(), "format": "a2log"}), encoding="utf-8")
    chosen["file"] = str(path)
    page.import_file()
    assert page.toast.text() == r.CHOOSE_FIGHT and page.moves["file"] == "session-1.a2log.json"
    assert page.moves_box.currentIndex() == 0                                  # no saved recording chosen
    _button(page, r.IMPORT_FIGHT).click()
    assert page.toast.text() == r.MOVES_IMPORTED and page.plan["meta"]["name"] == "Ice Queen"
    assert [t["kind"] for t in page.plan["tokens"]].count("aoe") == 0           # no catalog of areas from this app
    path.write_text(json.dumps({"format": "a2log", "segments": [{"duration": 3}]}), encoding="utf-8")
    page.import_file()
    assert page.toast.text() == r.NO_MOVEMENT and r.no_fight_words("session-1.a2log.json") in _texts(page)


def test_a_replay_opened_in_the_planner(made):
    page, fake, store, asked, chosen, picks = made
    first = page.id                                                    # "My first plan", untouched
    replay = {"format": "a2plan", "version": 1, "meta": {"name": "Recorded replay"}, "duration": 30,
              "arena": {"kind": "square"}, "tokens": [{"id": "b1", "kind": "enemy", "keyframes": [{"t": 0, "x": 0.5, "y": 0.5}]}],
              "buffs": []}
    work = []
    page.ask_work = lambda name: work.append(name) or "keep"
    assert page.open_replay(replay) is True
    assert work == [] and first not in _plans(store) and page.plan["meta"] == {"name": "Recorded replay", "updated": NOW}
    assert store.value(r.CURRENT) == page.id and page.plan_box.currentText() == "Recorded replay"
    # a plan worked on: asked first, then kept, discarded, or nothing done
    assert page.open_replay(replay) is True and work == ["Recorded replay"] and len(_plans(store)) == 2
    page.ask_work = lambda name: "discard"
    kept = set(_plans(store))
    assert page.open_replay(replay) is True and len(_plans(store)) == 2 and len(kept & set(_plans(store))) == 1
    page.ask_work = lambda name: "cancel"
    shown = page.id
    assert page.open_replay(replay) is False and page.id == shown and len(_plans(store)) == 2
    with pytest.raises(r.PlanError, match=r.INVALID_REPLAY):
        page.ask_work = lambda name: "keep"
        page.open_replay({"format": "a2plan", "tokens": None})


def test_the_window_opens_a_replay_in_the_raid_planner(qapp, monkeypatch, tmp_path):
    from aion2calc.gui import interface
    from aion2calc.gui.window import MainWindow
    from test_native_replay import _replay
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    window = MainWindow(None)
    window.show()
    planner = window.page("raid")
    plan = _replay().plan("circle")
    assert window.open_replay(plan) is True                          # the starter untouched: it gives way
    assert window.current_page() == "raid" and planner.plan["meta"]["name"] == "Ice Queen"
    assert planner.plan_box.currentText() == "Ice Queen" and len(r.raid_plans(planner.store)) == 1
    # over a plan worked on, cancelled: nothing opens
    window.show_page("meter")
    planner.ask_work = lambda name: "cancel"
    assert window.open_replay(plan) is False and window.current_page() == "meter"
    window.close()
