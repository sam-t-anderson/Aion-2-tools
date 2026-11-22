"""The native Builds page, its first part (0.2.486, ``gui/builds.py`` and ``gui/builds_page.py``), as
build-workspace.js keeps, checks and draws a draft: the bundled catalog's rules and the entered budgets' checks in the
web page's words, an optimizer's build and a file read as a draft, the drafts kept with the web page's
(``a2-build-drafts-v1``), the frame, the skills, stigmas and boards, the class's budgets and the community preset.
The expected checks and texts are build-workspace.js's own answers for the same drafts."""
import json
import os
import pathlib
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtGui import QFocusEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import builds as b  # noqa: E402
from aion2calc.gui import builds_page as bp  # noqa: E402
from test_native_settings import FakeApp, _refused  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "aion2calc" / "app" / "static" / "build-catalog.json").read_text(encoding="utf-8"))
SUMMARY = json.loads((ROOT / "results" / "pvp" / "gladiator" / "build.json").read_text(encoding="utf-8"))
KEEN, SURVIVAL, BLADE, FORCED = "11020000", "11710000", "11080000", "11430000"


def community(path: str) -> tuple:
    return ("GET", "/api/community?path=" + urllib.parse.quote(path, safe="-_.!~*'()"), None)


def a_draft(**more) -> dict:
    d = b.fresh(CATALOG, "gladiator", "pve", 30)
    d["build"].update(sp={KEEN: 5}, bonus={KEEN: 3}, specs={KEEN: [11020010, 11020020, 11020040]},
                      stigmas={BLADE: 6, FORCED: 20}, daevanion_nodes=[110098, 110097, 110033, 150098])
    d["budgets"] = {"skill": 3, "stigma": 10, "daevanion": 1, "boards": {"Ariel": 0}}
    d.update(more)
    return d


# ------------------------------------------------------------------ the rules
def test_json_is_written_as_javascript_writes_it():
    value = {"b": 1, "a": [1, 2, {}], "10": "x", "2": [], "01": 1, "4294967295": 3, "4294967294": 4,
             "n": [1.5, -0.0, 1e21, 1e-7, 0.000001, 45.0], "t": "é😀 \u0001\"\\\ud800"}
    # JSON.stringify's answers: the keys that are array indices first, in their order; numbers as JavaScript writes
    # them; a lone surrogate escaped
    assert b.stringify(value) == ('{"2":[],"10":"x","4294967294":4,"b":1,"a":[1,2,{}],"01":1,"4294967295":3,'
                                  '"n":[1.5,0,1e+21,1e-7,0.000001,45],"t":"é😀 \\u0001\\"\\\\\\ud800"}')
    assert b.stringify({"z": {"y": {}, "x": [1, {"m": None}]}}, 2) == (
        '{\n  "z": {\n    "y": {},\n    "x": [\n      1,\n      {\n        "m": null\n      }\n    ]\n  }\n}')
    assert b.size({"t": "é"}) == 10 and b.copy({"2": 1.0, "1": [2.5]}) == {"1": [2.5], "2": 1}
    assert [k for k, _v in b.entries({"b": 1, "3": 2, "1": 3})] == ["1", "3", "b"]
    assert b.integer(5.0, 1, 5) and not b.integer(True, 0, 1) and not b.integer("5", 0, 9) and not b.integer(1.5, 0, 9)


def test_a_fresh_draft_and_a_document_read_as_one():
    d = b.fresh(CATALOG, "templar", "pvp", 12)
    assert d["name"] == "templar_12_PVP" and d["catalog_revision"] == CATALOG["revision"]
    assert d["genus_mix"] == {"Cogni": 25, "Fera": 25, "Natura": 25, "Varian": 25, "Special": 0}
    assert b.normalize(CATALOG, d) == dict(d, source={"log": "", "actor": "", "basis": ""})   # an object: its three fields
    doc = dict(a_draft(), name="😀" * 70, notes=7, catalog_revision=None, local_id="x",
               source={"log": "L" * 20, "actor": 5, "basis": None}, reference={"snapshot": {"status": "ok"}})
    out = b.normalize(CATALOG, doc)
    assert out["name"] == "😀" * 60 and out["notes"] == "7" and out["catalog_revision"] == "unknown"   # 120 UTF-16 units
    assert out["source"] == {"log": "L" * 16, "actor": "5", "basis": ""} and "local_id" not in out
    assert out["reference"] == {"snapshot": {"status": "ok"}} and out["reference"] is not doc["reference"]
    for wrong, said in (({"format": "x"}, "Choose an a2build v1 document with a known class."),
                        ({"class": "nobody"}, "Choose an a2build v1 document with a known class."),
                        ({"level": 46}, "Choose level 1–45 and PvE or PvP."),
                        ({"mode": "PVE"}, "Choose level 1–45 and PvE or PvP."),
                        ({"budgets": []}, "Missing budgets or allocations."),
                        ({"budgets": {"skill": 1, "stigma": -1, "daevanion": 0}}, "Invalid stigma budget."),
                        ({"budgets": {"skill": 1, "stigma": 1, "daevanion": 0, "boards": {"Nezekan2": 1}}},
                         "Unknown board budget."),
                        ({"build": dict(a_draft()["build"], sp={KEEN: 11})}, "Invalid sp level for Keen Strike."),
                        ({"build": dict(a_draft()["build"], sp={"123": 1})}, "Unknown skill ID 123."),
                        ({"build": dict(a_draft()["build"], bonus={BLADE: 1})}, "Invalid bonus level for Blade Toss."),
                        ({"build": dict(a_draft()["build"], specs={KEEN: [11020010, 11020010]})},
                         "Invalid supporting effects for Keen Strike."),
                        ({"build": dict(a_draft()["build"], daevanion_nodes=[110098, 110098])},
                         "Unknown or duplicate Daevanion nodes."),
                        ({"reference": "r"}, "Reference is too large or invalid."),
                        ({"loadout": {"components": [{"stats": 1}]}},
                         "Equipment input must contain at most 64 components / 128 KiB."),
                        ({"genus_mix": []}, "Invalid genus_mix input.")):
        with pytest.raises(b.BuildError) as raised:
            b.normalize(CATALOG, dict(a_draft(), **wrong))
        assert str(raised.value) == said, wrong


def test_the_checks_are_the_web_pages():
    a = b.assessment(CATALOG, a_draft())
    assert a["errors"] == ["Skill cost 5 exceeds entered budget 3.", "Stigma cost 82 exceeds entered budget 10.",
                           "Keen Strike: too many supporting effects for the effective level.",
                           "Keen Strike: selected supporting effect is locked.",
                           "Nezekan: selected nodes must connect to the centre through selected nodes.",
                           "Ariel: character level gate not reached.",
                           "Ariel: cost exceeds its separate entered board budget.",
                           "Daevanion cost 6 exceeds entered budget 1."]
    assert (a["sp"], a["stigma"], a["crystal"]) == (5, 82, 6)
    assert a["boardCosts"] == {"Nezekan": 6, "Zikel": 0, "Vaizel": 0, "Triniel": 0, "Ariel": 1, "Azphel": 0}
    assert a["levels"][KEEN] == 8
    clean = b.fresh(CATALOG, "gladiator", "pve", 45)
    assert b.assessment(CATALOG, clean)["errors"] == []


def test_an_arcana_card_counts_and_its_limits():
    d = b.fresh(CATALOG, "gladiator", "pve", 45)
    pool = CATALOG["arcana_pools"]["gladiator"]["Arcana Chalice"]
    item = next(it for it in CATALOG["items"] if it["category"] == "Chalice" and it["grade"] == "Unique")
    card = {"slot": "Arcana Chalice", "catalog_slug": item["slug"], "enchant": 0, "stats": {},
            "arcana_skills": {str(pool["skills"][0]["id"]): 2}}
    d["loadout"]["components"] = [card]
    assert b.card_bonuses(CATALOG, d) == {str(pool["skills"][0]["id"]): 2}
    assert b.levels(CATALOG, d)[str(pool["skills"][0]["id"])] == 3
    card["arcana_skills"] = {str(pool["skills"][0]["id"]): 4, str(pool["skills"][1]["id"]): 1}
    with pytest.raises(b.BuildError, match="exceed the grade/enhancement budget"):
        b.card_bonuses(CATALOG, d)
    assert b.safe_card_bonuses(CATALOG, d) == {}
    assert "Card options exceed the grade/enhancement budget." in b.assessment(CATALOG, d)["errors"]
    d["loadout"]["components"] = [dict(card, arcana_skills={str(pool["skills"][0]["id"]): 1}),
                                  dict(card, arcana_skills={str(pool["skills"][0]["id"]): 1})]
    with pytest.raises(b.BuildError, match="Choose distinct compatible catalog cards"):
        b.card_bonuses(CATALOG, d)


def test_an_optimizer_build_and_a_file_read_as_a_draft():
    s = b.from_summary(CATALOG, SUMMARY)
    assert (s["name"], s["level"], s["mode"]) == ("gladiator_45_PVP", 45, "pvp")
    assert s["budgets"] == {"skill": 383, "stigma": 260, "daevanion": 416, "boards": {}}
    assert s["build"]["bonus"][KEEN] == 6 and s["build"]["bonus"]["11170000"] == 10
    assert s["build"]["specs"][KEEN] == [11020030, 11020040, 11020050]
    assert s["build"]["stigmas"] == {"11130000": 15, "11250000": 20, "11390000": 20, "11450000": 20}
    assert len(s["build"]["daevanion_nodes"]) == 288 and list(s["reference"]["optimizer"]) == ["class", "scenario", "dps", "stats"]
    assert s["source"]["basis"].startswith("Imported optimizer allocation.")
    wrong = json.loads(json.dumps(SUMMARY))
    wrong["build"]["sp"] = {"No such skill": 1}
    with pytest.raises(b.BuildError, match="Unknown imported skill No such skill"):
        b.from_summary(CATALOG, wrong)
    with pytest.raises(b.BuildError, match="Unsupported optimizer summary."):
        b.from_summary(CATALOG, None)
    current = b.fresh(CATALOG, "cleric", "pvp", 20)
    assert b.imported(CATALOG, current, s) == (s, False)
    assert b.imported(CATALOG, current, SUMMARY)[0] == s
    profile = {"data": {"profile": {"characterName": "A"}}}
    nxt, shown = b.imported(CATALOG, current, profile)
    assert shown and nxt["class"] == "cleric" and nxt["level"] == 45 and nxt["mode"] == "pvp"
    assert nxt["reference"] == {"snapshot": profile} and nxt["source"]["basis"] == b.PROFILE_BASIS
    assert b.imported(CATALOG, current, {"profile": {"x": 1}})[0]["reference"] == {
        "snapshot": {"status": "imported", "data": {"profile": {"x": 1}}}}
    for value, said in (({"hello": 1}, b.NOT_IMPORTABLE), ([], b.NOT_IMPORTABLE), (5, b.NOT_IMPORTABLE),
                        (None, "Cannot read properties of null (reading 'format')")):
        with pytest.raises(b.BuildError) as raised:
            b.imported(CATALOG, current, value)
        assert str(raised.value) == said
    assert b.export_name("My build ✓ 😀") == "My_build_____.a2build.json" and b.export_name("") == "build.a2build.json"


def test_the_drafts_kept():
    assert b.saved(None) == [] and b.saved("{") == [] and b.saved('{"a": 1}') == []
    assert b.saved(json.dumps(list(range(12)))) == list(range(10))
    d = b.fresh(CATALOG, "gladiator", "pve", 45)
    rows, ident = b.saved_with(CATALOG, d, None, {}, None, now_ms=1700000000000, pick=lambda letters: "a")
    assert ident == "1700000000000-aaaaaa" and rows == [{"id": ident, "updated_at": 1700000000000, "draft": b.normalize(CATALOG, d)}]
    kept = b.stringify(rows)
    d["local_id"] = ident
    again, same_id = b.saved_with(CATALOG, d, None, {}, kept, now_ms=1700000000500)
    assert same_id == ident and len(again) == 1 and again[0]["updated_at"] == 1700000000500
    ten = b.stringify([{"id": str(i), "draft": {}} for i in range(10)])
    with pytest.raises(b.BuildError, match="Ten local drafts are saved."):
        b.saved_with(CATALOG, b.fresh(CATALOG, "gladiator", "pve", 45), None, {}, ten)
    # a row without an id gives way to a draft never kept, as the web page's filter lets it
    rows, _ = b.saved_with(CATALOG, b.fresh(CATALOG, "gladiator", "pve", 45), None, {}, b.stringify([{"draft": {}}, 5]))
    assert len(rows) == 1
    big = b.fresh(CATALOG, "gladiator", "pve", 45)
    with pytest.raises(b.BuildError, match="Saved drafts exceed 2 MiB."):
        b.saved_with(CATALOG, big, {"x": "y" * (2 * 1024 * 1024 - 100)}, {}, None)
    assert [x["id"] for x in b.without(ten, "3")] == [str(i) for i in range(10) if i != 3]
    assert b.find_row(ten, "4") == {"id": "4", "draft": {}} and b.find_row(ten, "x") is None
    assert b.row_name({"draft": {"name": 0}}) == "Unnamed draft" and b.row_name({"draft": {"name": "Mine"}}) == "Mine"
    with pytest.raises(b.BuildError, match="reading 'id'"):
        b.without(b.stringify([None]), "1")


# ------------------------------------------------------------------ the page
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


ASSASSIN = {"observations": [{"class_name": "assassin", "skill": 200, "stigma": 100, "daevanion": 250},
                             {"class_name": "assassin", "skill": 210, "stigma": 90, "daevanion": 260}]}
GLADIATOR = {"observations": [{"class_name": "gladiator", "skill": 230, "stigma": 140, "daevanion": 300}]}


@pytest.fixture
def made(qapp, tmp_path):
    """A Builds page over a fake app, its questions answered yes, its files in ``tmp_path``."""
    fake = FakeApp({("GET", "/static/build-catalog.json", None): CATALOG,
                    community("/api/v1/progression?class=assassin"): ASSASSIN,
                    community("/api/v1/progression?class=gladiator"): [GLADIATOR, _refused("/api/community", 502, "log server unavailable"), GLADIATOR],
                    community("/api/v2/presets/gladiator/pvp"): {"build": SUMMARY}})
    store = QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)
    asked, chosen = [], {"answer": True, "file": ""}

    def confirm(words):
        asked.append(words)
        return chosen["answer"]
    page = bp.BuildsPage(fake, store=store, confirm=confirm, choose_file=lambda: chosen["file"],
                         save_file=lambda name: chosen.setdefault("saved_as", []).append(name) or str(tmp_path / "out.json"),
                         read_picture=lambda url: b"")
    page.resize(1300, 900)
    page.show()
    assert settle(lambda: page.frame is not None and "Highest" in page.message_label.text())
    yield page, fake, store, asked, chosen
    page.close()


def test_the_page_opens_on_an_empty_draft_with_the_classs_budgets(made):
    page, fake, _store, _asked, _chosen = made
    assert [p for _m, p, _b in fake.calls if "community" in p or "catalog" in p][:2] == [
        "/static/build-catalog.json", community("/api/v1/progression?class=assassin")[1]]
    assert page.class_box.currentData() == "assassin" and page.name_edit.text() == "assassin_45_PVE"
    assert page.level_edit.text() == "45" and page.mode_box.currentData() == "pve" and page.tab == "active"
    assert page.message_label.text().startswith("Highest server-reported totals from 2 class/context observations")
    assert page.draft["budgets"] == {"skill": 210, "stigma": 100, "daevanion": 260, "boards": {}} and page.dirty
    assert page.budget_field.text() == "210" and page.body_words["used"] == "Used: 0 / 210 points."
    assert page.body_words["errors"] == [] and page.saved_buttons == []
    assert [page.tab_buttons[k].objectName() for k in ("active", "passive")] == ["tabOn", "tab"]
    skills = [s for s in CATALOG["classes"]["assassin"]["skills"] if s["kind"] == "active"]
    assert list(page.skill_widgets) == [str(s["id"]) for s in skills]
    first = page.skill_widgets[str(skills[0]["id"])]
    assert first["words"] == ["active", skills[0]["name"], "Effective level 1 · 0 supporting slots"]
    assert first["trained"].count() == min(10, skills[0].get("buyMax") or 10) and first["bonus"].text() == "0"


def test_a_skills_levels_effects_and_the_checks(made):
    page, _fake, _store, asked, chosen = made
    chosen["answer"] = False                                          # the class kept when the question is refused
    page.class_box.setCurrentIndex(page.class_box.findData("gladiator"))
    page.class_box.activated.emit(page.class_box.findData("gladiator"))
    assert asked == [bp.ASK_CLASS] and page.class_box.currentData() == "assassin" and page.draft["class"] == "assassin"
    chosen["answer"] = True
    page.class_box.setCurrentIndex(page.class_box.findData("gladiator"))
    page.class_box.activated.emit(page.class_box.findData("gladiator"))
    assert settle(lambda: page.draft["budgets"]["skill"] == 230)
    keen = page.skill_widgets[KEEN]
    keen["trained"].setCurrentIndex(keen["trained"].findData(5))
    keen["trained"].activated.emit(keen["trained"].findData(5))
    page.skill_widgets[KEEN]["bonus"].setText("3")
    page.skill_widgets[KEEN]["bonus"].editingFinished.emit()
    assert page.draft["build"]["sp"] == {KEEN: 5} and page.draft["build"]["bonus"] == {KEEN: 3}
    assert page.skill_widgets[KEEN]["words"][2] == "Effective level 8 · 1 supporting slots"
    page.skill_widgets[KEEN]["bonus"].setText("31")
    page.skill_widgets[KEEN]["bonus"].editingFinished.emit()
    assert page.message_label.text() == bp.BAD_BONUS and page.skill_widgets[KEEN]["bonus"].text() == "3"
    for effect in (11020010, 11020020, 11020040):
        page.skill_widgets[KEEN]["effects"][effect].tick.setChecked(True)
    assert page.draft["build"]["specs"] == {KEEN: [11020010, 11020020, 11020040]}
    assert page.body_words["errors"] == ["Keen Strike: too many supporting effects for the effective level.",
                                         "Keen Strike: selected supporting effect is locked."]
    assert page.skill_widgets[KEEN]["effects"][11020040].plain == "4 · " + next(
        e["text"] for e in CATALOG["classes"]["gladiator"]["skills"][0]["specs"] if e["id"] == 11020040) + " (effect Lv 12 · locked)"
    page.search_edit.setText("slam")
    assert [w["words"][1] for w in page.skill_widgets.values()] == ["Leaping Slam", "Overhead Slam"]
    page.budget_field.setText("1e")                                    # what a number field holds: no number
    page.budget_field.editingFinished.emit()
    assert page.message_label.text() == bp.BAD_BUDGET and page.budget_field.text() == "230"
    page.search_edit.setText("")                                       # the search stays with the page, as on the web page
    page.tab_buttons["stigma"].click()
    assert page.message_label.text() == "" and page.budget_field.accessibleName() == "stigma budget"
    blade = page.skill_widgets[BLADE]
    assert [blade["trained"].itemData(i) for i in (0, blade["trained"].count() - 1)] == [0, 20] and blade["bonus"] is None
    blade["trained"].setCurrentIndex(6)
    blade["trained"].activated.emit(6)
    assert page.draft["build"]["stigmas"] == {BLADE: 6}
    effects = list(page.skill_widgets[BLADE]["effects"].values())
    assert [(e.tick.isChecked(), e.tick.isEnabled()) for e in effects[:2]] == [(True, False), (False, False)]
    assert effects[0].plain.endswith("(effect Lv 5 · automatic)")
    page.skill_widgets[BLADE]["trained"].setCurrentIndex(0)
    page.skill_widgets[BLADE]["trained"].activated.emit(0)
    assert page.draft["build"]["stigmas"] == {}


def test_the_daevanion_boards(made):
    page, *_rest = made
    page.class_box.setCurrentIndex(page.class_box.findData("gladiator"))
    page.class_box.activated.emit(page.class_box.findData("gladiator"))
    assert settle(lambda: page.draft["budgets"]["skill"] == 230)
    page.tab_buttons["daevanion"].click()
    assert page.board_name == "Nezekan" and page.board_tabs["Nezekan"].objectName() == "tabOn"
    assert page.board_budget_field is None and page.budget_field.accessibleName() == "Daevanion budget"
    start = page.node_buttons[110113]
    assert not start.isEnabled() and start.objectName() == "bwNodeOn" and start.mark == "★"
    page.node_buttons[110098].click()
    page.node_buttons[110033].click()
    assert page.draft["build"]["daevanion_nodes"] == [110098, 110033]
    assert page.node_buttons[110098].mark == "✓" and page.node_buttons[110098].objectName() == "bwNodeOn"
    assert "Nezekan: selected nodes must connect to the centre through selected nodes." in page.body_words["errors"]
    assert page.board_tabs["Nezekan"].accessibleName() == "Nezekan · cost 5"
    page.node_buttons[110033].click()
    assert page.draft["build"]["daevanion_nodes"] == [110098]
    page.board_tabs["Ariel"].click()
    assert page.board_text.startswith("Ariel · opens at character Lv 45.") and page.board_budget_field.text() == "0"
    page.board_budget_field.setText("-")
    page.board_budget_field.editingFinished.emit()
    assert page.message_label.text() == bp.BAD_BOARD_BUDGET and page.board_budget_field.text() == "-"   # not put back
    page.board_budget_field.setText("4")
    page.board_budget_field.editingFinished.emit()
    assert page.draft["budgets"]["boards"] == {"Ariel": 4}
    tip = page.node_buttons[150098].toolTip()
    assert " · cost 1 · " in tip
    page.level_edit.setText("50")
    page.level_edit.editingFinished.emit()
    assert page.message_label.text() == bp.BAD_LEVEL and page.level_edit.text() == "45"
    page.level_edit.setText("30")
    page.level_edit.editingFinished.emit()
    assert page.draft["level"] == 30 and "level locked" in page.node_buttons[150098].toolTip()
    page.mode_box.setCurrentIndex(1)
    page.mode_box.activated.emit(1)
    assert page.draft["mode"] == "pvp" and page.message_label.text() == bp.MODE_CHANGED


def test_drafts_saved_loaded_removed_and_exported(made, tmp_path):
    page, _fake, store, asked, chosen = made
    page.name_edit.setText("Mine ✓")
    page.name_edit.editingFinished.emit()
    page.notes_edit.setPlainText("For the raid")
    page.notes_edit.focusOutEvent(QFocusEvent(QEvent.FocusOut))
    assert page.draft["name"] == "Mine ✓" and page.draft["notes"] == "For the raid"
    page.save()
    assert page.message_label.text() == bp.SAVED_OK and not page.dirty
    rows = json.loads(store.value(b.STORE))
    assert len(rows) == 1 and rows[0]["draft"]["name"] == "Mine ✓" and page.draft["local_id"] == rows[0]["id"]
    assert [load.accessibleName() for _k, load, _r in page.saved_buttons] == ["Mine ✓"]
    page.download()
    assert chosen["saved_as"] == ["Mine__.a2build.json"]
    written = (tmp_path / "out.json").read_text(encoding="utf-8")
    assert json.loads(written)["name"] == "Mine ✓" and written.startswith('{\n  "format": "a2build",\n  "version": 1,')
    assert page.message_label.text() == f"Build exported: {tmp_path / 'out.json'}. Source stats were not recalculated."
    page.new_draft()
    assert asked == [] and page.draft["name"] == "assassin_45_PVE" and "local_id" not in page.draft
    assert settle(lambda: page.dirty)                                  # the budgets read for the new draft
    page.saved_buttons[0][1].click()
    assert asked == [bp.ASK_LOAD] and page.message_label.text() == bp.LOADED and page.draft["name"] == "Mine ✓"
    page.saved_buttons[0][2].click()
    assert page.message_label.text() == bp.REMOVED and json.loads(store.value(b.STORE)) == []
    assert "local_id" not in page.draft and page.saved_buttons == []
    first = next(s for s in CATALOG["classes"]["assassin"]["skills"] if s["kind"] == "active")
    page.draft["build"]["sp"], page.draft["budgets"]["skill"] = {str(first["id"]): 10}, 0     # more than the budget
    page.download()
    assert page.message_label.text() == bp.EXPORT_BLOCKED


def test_files_presets_and_budgets(made, tmp_path):
    page, _fake, _store, asked, chosen = made
    draft = tmp_path / "draft.a2build.json"
    draft.write_text(b.stringify(b.from_summary(CATALOG, SUMMARY), 2), encoding="utf-8")
    for content, said in (("{not json", "Import failed: "), (json.dumps({"hello": 1}), "Import failed: " + b.NOT_IMPORTABLE)):
        bad = tmp_path / "bad.json"
        bad.write_text(content, encoding="utf-8")
        chosen["file"] = str(bad)
        page.import_file()
        assert page.message_label.text().startswith(said)
    chosen["file"] = str(draft)
    page.import_file()
    assert asked[-1] == bp.ASK_IMPORT and page.message_label.text() == bp.IMPORTED
    assert page.draft["class"] == "gladiator" and page.draft["build"]["stigmas"]["11130000"] == 15
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"data": {"profile": {"characterName": "A"}}}), encoding="utf-8")
    chosen["file"] = str(profile)
    page.import_file()
    assert page.tab == "reference" and page.tab_buttons["reference"].objectName() == "tabOn"
    assert page.reference == {"snapshot": {"data": {"profile": {"characterName": "A"}}}}
    page.tab_buttons["active"].click()
    page.server_budgets()                                              # the class's budgets: the first answer
    assert settle(lambda: page.draft["budgets"]["skill"] == 230)
    page.server_budgets()                                              # then the log server refuses
    assert settle(lambda: page.message_label.text() == "log server unavailable")
    assert page.body_words["budget_note"] == "log server unavailable" and page.draft["budgets"]["skill"] == 230
    page.preset_button.click()
    assert page.message_label.text() == bp.LOADING_PRESET and not page.preset_button.isEnabled()
    assert settle(lambda: page.message_label.text() == bp.PRESET_LOADED)
    assert page.draft == b.from_summary(CATALOG, SUMMARY) and page.preset_button.isEnabled()


def test_leaving_the_page_starts_it_afresh(made):
    page, fake, *_rest = made
    page.tab_buttons["daevanion"].click()
    page.node_buttons[110098].click() if 110098 in page.node_buttons else None
    page.leave()
    page.hide()
    page.show()
    assert settle(lambda: page.frame is not None and page.tab == "active" and "Highest" in page.message_label.text())
    assert page.draft["build"]["daevanion_nodes"] == [] and page.class_box.currentData() == "assassin"
    assert [p for _m, p, _b in fake.calls].count("/static/build-catalog.json") == 1     # the catalog read once


def test_the_other_tabs_open_the_web_page(made):
    page, *_rest = made
    opened = []
    page.open_web = opened.append
    page.tab_buttons["equipment"].click()
    texts = [w.text() for w in page.findChildren(bp.QLabel)]
    assert bp.ON_THE_WEB in texts
    next(btn for btn in page.findChildren(bp.QPushButton) if btn.text() == bp.OPEN_WEB).click()
    assert opened == ["builds"]


def test_the_window_draws_builds_and_lets_it_go_when_left(qapp, monkeypatch, tmp_path):
    from aion2calc.gui import interface
    from aion2calc.gui.window import MainWindow
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    window = MainWindow(None)
    page = window.page("builds")
    assert isinstance(page, bp.BuildsPage)
    window.show_page("builds")
    page.mounted = True
    window.show_page("timers")
    assert not page.mounted
    window.close()
