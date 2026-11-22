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
    assert import_text(json.dumps({"format": "a2log"})) == rp.MOVEMENT_ELSEWHERE
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
    opened = []
    window = MainWindow(None)
    page = window.page("raid")
    assert isinstance(page, rp.RaidPage)
    page.open_web = opened.append
    window.show_page("raid")
    page.mount()
    _button(page, rp.OPEN_WEB).click()
    assert opened == ["raid"]
    page.play()
    window.show_page("timers")
    assert not page.playing and not page.mounted
    window.close()
