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
    page.tab_buttons["reference"].click()
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


# ------------------------------------------------------------------ equipment and arcana cards (0.2.487)
def test_the_slots_and_items_for_a_slot():
    d = b.fresh(CATALOG, "gladiator", "pve", 45)
    assert b.slots_for(CATALOG, "equipment")[:3] == ["MainHand", "SubHand", "Helmet"] and len(b.slots_for(CATALOG, "equipment")) == 20
    assert b.slots_for(CATALOG, "arcana") == ["Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror"]
    swords = b.available(CATALOG, d, "MainHand", "")
    assert swords and {c["category"] for c in swords} == {"Greatsword"} and all(c["required_level"] <= 45 for c in swords)
    assert [c["slug"] for c in b.available(CATALOG, d, "MainHand", "ABYSS")] == ["abyssal-claymore"]
    low = dict(d, level=20)
    assert all(c["required_level"] <= 20 for c in b.available(CATALOG, low, "MainHand", ""))
    assert [b.component_kind({"slot": s}) for s in ("Arcana Bell", "Pantheon", "Deity points", "Helmet", None)] == [
        "arcana", "pantheon", "pantheon", "equipment", "equipment"]
    assert b.stats_line({"stats": {"a": 1.5, "b": None, "c": [1, 2]}}) == "a: 1.5 · b:  · c: 1,2" and b.stats_line({}) == ""


def test_an_item_applied_with_its_rolls_and_card_levels():
    d = b.fresh(CATALOG, "gladiator", "pve", 45)
    sword = next(it for it in CATALOG["items"] if it["slug"] == "abyssal-claymore")
    comps = b.with_item(CATALOG, d, "MainHand", sword, 3, [{"stat": "Critical Attack", "value": 90}, {"stat": "HP", "value": 350}])
    # build-workspace.js's own answer: the fixed stats at +3, the modelled roll added through its unit, HP kept unscored
    assert comps == [{"slot": "MainHand", "item": "Abyssal Claymore +3", "icon": sword["icon"], "grade": "Unique", "enchant": 3,
                      "catalog_slug": "abyssal-claymore", "source": b.ITEM_SOURCE,
                      "rolls": [{"stat": "Critical Attack", "value": 90}, {"stat": "HP", "value": 350}], "arcana_skills": {},
                      "stats": {"weapon_min": 403, "weapon_max": 535, "accuracy": 100, "crit": 150, "block": 150, "crit_atk": 90}}]
    helm = next(it for it in CATALOG["items"] if it["slug"] == "abyssal-helm")
    assert b.with_item(CATALOG, d, "Helmet", helm, 0, [{"stat": "Natural MP Regen", "value": 25}])[0]["stats"] == {"mp_regen": 8.333333333333332}
    chalice = next(it for it in CATALOG["items"] if it["slug"] == "chalice-of-magic")
    card = b.with_item(CATALOG, d, "Arcana Chalice", chalice, 1, None, {KEEN: 3, "11010000": 2})[0]
    assert card["arcana_skills"] == {"11010000": 2, KEEN: 3} and b.stringify(card["arcana_skills"]) == '{"11010000":2,"11020000":3}'
    d["loadout"]["components"] = [{"slot": "MainHand", "item": "old", "stats": {}}, {"slot": "Other", "item": "x", "stats": {}}]
    assert [c["slot"] for c in b.with_item(CATALOG, d, "MainHand", sword, 0)] == ["Other", "MainHand"]   # put last
    assert b.without_slot(d, "MainHand") == [{"slot": "Other", "item": "x", "stats": {}}]
    for args, said in (((chalice, 0, None, {KEEN: 3, "11010000": 2}), b.OVER_CARD),
                       ((chalice, 0, None, {"999": 1}), b.OVER_CARD),
                       ((sword, 0, [{"stat": "Critical Attack", "value": 1}] * 5), b.MANY_ROLLS),
                       ((sword, 0, [5]), b.BAD_ROLL),
                       ((sword, 0, [{"stat": "Critical Attack", "value": 999}]), b.OUT_OF_RANGE),
                       ((sword, 0, [{"stat": "Critical Attack", "value": 90}, {"stat": "Critical Attack", "value": 90}]), b.OUT_OF_RANGE),
                       ((sword, 0, [{"stat": "Critical Attack"}]), b.OUT_OF_RANGE)):
        slot = "Arcana Chalice" if args[0] is chalice else "MainHand"
        with pytest.raises(b.BuildError) as raised:
            b.with_item(CATALOG, d, slot, *args)
        assert str(raised.value) == said
    d["loadout"]["components"] = [{"slot": f"Custom{i}", "stats": {}} for i in range(64)]
    with pytest.raises(b.BuildError, match="already has 64 components"):
        b.with_item(CATALOG, d, "MainHand", sword, 0)
    assert b.card_note(CATALOG, chalice, 1) == ("Each enhancement step adds one skill option: 5 at +1, 9 at +5. The bundled "
                                                "catalog lists no stat change per step.")


def _gladiator(page):
    page.class_box.setCurrentIndex(page.class_box.findData("gladiator"))
    page.class_box.activated.emit(page.class_box.findData("gladiator"))
    assert settle(lambda: page.draft["budgets"]["skill"] == 230)


def test_the_equipment_doll_and_an_items_options(made):
    page, *_rest = made
    _gladiator(page)
    page.tab_buttons["equipment"].click()
    assert list(page.tiles) == b.slots_for(CATALOG, "equipment") and page.tiles["MainHand"].isChecked()
    assert page.picker_words["chosen"] == bp.NO_DRAFT_ITEM and page.component_words["centre"] == [
        "GLADIATOR", "gladiator_45_PVE", bp.DOLL_NOTE]
    count = len(b.available(CATALOG, page.draft, "MainHand", ""))
    assert page.picker_words["count"] == bp.matching(count) and len(page.item_buttons) == min(80, count)
    page.gear_search_edit.setText("abyss")
    page.gear_search_edit.textEdited.emit("abyss")
    assert list(page.item_buttons) == ["abyssal-claymore"] and page.picker_words["count"] == "1 matching items"
    page.item_buttons["abyssal-claymore"].click()
    assert page.message_label.text() == bp.ITEM_APPLIED and page.tiles["MainHand"].name == "Abyssal Claymore +0"
    assert page.tiles["MainHand"].property("grade") == "Unique" and page.dirty
    page.enchant_box.setCurrentIndex(3)
    page.enchant_box.activated.emit(3)
    assert page.draft["loadout"]["components"][0]["enchant"] == 3
    assert page.picker_words["chosen"][1].startswith("weapon_min: 403 · weapon_max: 535")
    box, field, _options = page.roll_lines[0]
    box.setCurrentIndex(box.findData("Critical Attack"))
    box.activated.emit(box.findData("Critical Attack"))
    assert field.text() == "78" and field.isEnabled() and page.component_buffer
    field.setText("90")
    field.textEdited.emit("90")
    page.tiles["Helmet"].click()
    assert page.message_label.text() == bp.PENDING_ROLLS and page.gear_slot == "MainHand"
    page.gear_search_edit.setText("x")
    page.gear_search_edit.textEdited.emit("x")
    assert page.message_label.text() == bp.PENDING_SEARCH and page.gear_search_edit.text() == "abyss"
    page.tab_buttons["active"].click()
    assert page.message_label.text() == bp.APPLY_FIRST_TAB and page.tab == "equipment"
    page.save()
    assert page.message_label.text() == bp.APPLY_FIRST_SAVE
    page.option_buttons[0].click()
    comp = page.draft["loadout"]["components"][0]
    assert comp["rolls"] == [{"stat": "Critical Attack", "value": 90}] and comp["stats"]["crit_atk"] == 90
    assert not page.component_buffer and page.message_label.text() == bp.ITEM_APPLIED
    box = page.roll_lines[1][0]
    box.setCurrentIndex(box.findData("Accuracy"))
    box.activated.emit(box.findData("Accuracy"))
    page.roll_lines[1][1].setText("")
    page.option_buttons[0].click()
    assert page.message_label.text() == bp.NEED_VALUE
    page.option_buttons[1].click()
    assert page.message_label.text() == bp.EDITS_DISCARDED and not page.component_buffer
    assert page.roll_lines[1][0].currentData() == ""
    page.clear_button.click()
    assert page.draft["loadout"]["components"] == [] and page.tiles["MainHand"].name == bp.EMPTY_SLOT


def test_the_arcana_cards_and_their_skill_levels(made):
    page, *_rest = made
    _gladiator(page)
    page.tab_buttons["arcana"].click()
    assert page.gear_slot == "Arcana Chalice" and list(page.tiles) == b.slots_for(CATALOG, "arcana")
    page.item_buttons["chalice-of-magic"].click()
    assert page.picker_words["enchant_note"] == ("Each enhancement step adds one skill option: 4 at +0, 9 at +5. The bundled "
                                                 "catalog lists no stat change per step.")
    assert page.picker_words["panels"] == [[bp.CARD_HEAD, bp.cards_note(4, 4)]]
    for key, n in ((KEEN, 3), ("11010000", 2)):
        page.card_selects[key].setCurrentIndex(n)
        page.card_selects[key].activated.emit(n)
    page.option_buttons[0].click()
    assert page.message_label.text() == b.OVER_CARD and page.component_buffer
    page.option_buttons[1].click()
    page.card_selects[KEEN].setCurrentIndex(3)
    page.card_selects[KEEN].activated.emit(3)
    page.option_buttons[0].click()
    assert page.draft["loadout"]["components"][0]["arcana_skills"] == {KEEN: 3}
    assert page.card_selects[KEEN].currentData() == 3
    page.tab_buttons["active"].click()
    assert page.skill_widgets[KEEN]["words"][2] == "Effective level 4 · 3 card levels · 0 supporting slots"


def test_imported_contributions_and_recorded_equipment(made, tmp_path):
    page, _fake, _store, _asked, chosen = made
    _gladiator(page)
    page.mode_box.setCurrentIndex(1)
    page.mode_box.activated.emit(1)
    page.preset_button.click()
    assert settle(lambda: page.message_label.text() == bp.PRESET_LOADED)
    page.tab_buttons["equipment"].click()
    extra = page.component_words["extra"]
    assert extra[:2] == [["Main hand", "Spiritforged Greatsword +9"], ["Off-hand", "Spiritforged Guard +9"]]
    before = len(page.draft["loadout"]["components"])
    page.extra_buttons[0].click()
    assert len(page.draft["loadout"]["components"]) == before - 1 and page.component_words["extra"][0][0] == "Off-hand"
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"data": {"profile": {"characterName": "A"}, "equipment": {"equipmentList": [
        {"slotPosName": "MainHand", "name": "Recorded Sword", "enchantLevel": 5, "grade": "Unique"},
        {"slotPosName": "ArcanaChalice", "id": 99, "grade": "Epic"}, {"slotPosName": "Helmet", "itemName": "Helm"}]}}}),
        encoding="utf-8")
    chosen["file"] = str(profile)
    page.import_file()
    page.tab_buttons["equipment"].click()
    assert page.component_words["source"] == [["MainHand", "Recorded Sword", "+5 · Unique"], ["Helmet", "Helm", "+0 · "]]
    page.tab_buttons["arcana"].click()
    assert page.component_words["source"] == [["ArcanaChalice", "99", "+0 · Epic"]]


# ------------------------------------------------------------------ Pantheon, Genus Insight and evaluation (0.2.488)
EVALUATED = {"format": "a2build-evaluation", "version": 1, "evaluator": "0.2.488", "input_sha256": "0123456789abcdef" * 4,
             "arcana_options_supported": True, "search_priority": False, "note": "Modelled, not measured.",
             "scenarios": {"pve_boss": {"dps": 123456.78}, "pvp_duel": {"dps": 9876.04}}}


def test_the_pantheon_points_and_the_evaluations_words():
    d = b.fresh(CATALOG, "gladiator", "pve", 45)
    zikel = CATALOG["deities"][0]
    assert b.deity_words(zikel) == ("Z", "Destruction", "Zikel") and b.deity_words({"name": "Plain"}) == ("P", "Plain", "Plain")
    d["loadout"]["components"] = [{"slot": "Deity points", "item": "x", "stats": {"destruction": "4", "death": None}},
                                  {"slot": "Helmet", "item": "y", "stats": {"destruction": 9}}]
    rows = b.pantheon_rows(d)
    assert rows == [d["loadout"]["components"][0]] and b.deity_total(rows, "destruction") == 4 and b.deity_total(rows, "death") == 0
    b.with_deity_points(d, rows, zikel, 12.5)
    assert d["loadout"]["components"][0]["stats"] == {"death": None}                       # taken off every deity row
    assert d["loadout"]["components"][2] == {"slot": "Pantheon", "item": "Draft deity contributions", "stats": {"destruction": 12.5}}
    assert rows[-1] is d["loadout"]["components"][2] and b.deity_total(rows, "destruction") == 12.5
    full = b.fresh(CATALOG, "gladiator", "pve", 45)
    full["loadout"]["components"] = [{"slot": f"C{i}", "stats": {}} for i in range(64)]
    with pytest.raises(b.BuildError, match="64 component limit"):
        b.with_deity_points(full, b.pantheon_rows(full), zikel, 1)
    stats = [{"type": "Destruction", "value": 120}, {"name": "Life [Yustiel]", "value": 5}, None]
    assert b.recorded_stat(stats, zikel)["value"] == 120 and b.recorded_stat(stats, CATALOG["deities"][7])["value"] == 5
    assert b.recorded_stat(stats, CATALOG["deities"][1]) is None
    request = b.evaluation_request(d, True)
    assert list(request) == ["search_priority", "format", "version", "class", "mode", "level", "build", "budgets", "loadout",
                             "genus", "genus_mix"] and request["build"] is not d["build"] and request["search_priority"] is True
    assert [b.dps(x) for x in (123456.78, 9876.04, 1400.05, 0, -2.25, 1e21)] == ["123,456.8", "9,876", "1,400.1", "0", "-2.3",
                                                                                 "1,000,000,000,000,000,000,000"]
    words = b.evaluation_words(dict(EVALUATED, scenarios={"pve_boss": {"dps": 1500.25, "priority_search": {
        "evaluations": 96, "stop_reason": "budget", "baseline_dps": 1400.06, "note": "Fixed.",
        "actions": [{"name": "Keen Strike"}, {"name": "Rending Blow", "condition": "after a crit"}]}}}))
    assert words["source"] == "Evaluator 0.2.488 · input 0123456789abcdef"
    assert words["scenarios"] == ["pve_boss: 1,500.3 modeled DPS"] and words["note"] == "Modelled, not measured."
    assert words["searches"] == [{"title": "pve_boss priority search", "line": "96 evaluated priorities · budget · default 1,400.1 DPS",
                                  "actions": ["Keen Strike", "Rending Blow (after a crit)"], "note": "Fixed."}]
    assert words["detail"].startswith('{\n  "format": "a2build-evaluation",')


def test_the_pantheon_tab(made, tmp_path):
    page, _fake, _store, _asked, chosen = made
    _gladiator(page)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"data": {"profile": {"characterName": "A"}, "stat": {"statList": [
        {"type": "Destruction", "value": 120}, {"name": "Life [Yustiel]", "value": 5}]}}}), encoding="utf-8")
    chosen["file"] = str(profile)
    page.import_file()
    page.tab_buttons["pantheon"].click()
    words = page.pantheon_words
    assert [w["name"] for w in words][:3] == ["Destruction", "Death", "Wisdom"] and words[0]["lord"] == "Zikel"
    assert words[0]["recorded"] == "Source total: 120 (read-only)" and words[7]["recorded"] == "Source total: 5 (read-only)"
    assert [w["points"] is None for w in words] == [d["field"] is None for d in CATALOG["deities"]]
    field = page.deity_fields[0]
    field.setText("12.5")
    field.editingFinished.emit()
    assert page.message_label.text() == bp.POINTS_APPLIED and page.dirty
    assert b.pantheon_rows(page.draft) == [{"slot": "Pantheon", "item": "Draft deity contributions", "stats": {"destruction": 12.5}}]
    field.setText("-1")
    field.editingFinished.emit()
    assert page.message_label.text() == b.BAD_POINTS and field.text() == "12.5"
    page.deity_fields[1].setText("3")
    page.deity_fields[1].editingFinished.emit()
    assert b.pantheon_rows(page.draft)[0]["stats"] == {"destruction": 12.5, "death": 3}


def test_genus_lines_saved_into_the_draft(made):
    page, *_rest = made
    page.tab_buttons["genus"].click()
    editor = page.genus_editor
    editor.level.setText("4")
    editor.level.setModified(True)
    editor.level.editingFinished.emit()
    page.genus_editor.fields[(1, "stat")].setText("Cogni Damage Boost")
    page.genus_editor.fields[(1, "stat")].textEdited.emit("Cogni Damage Boost")
    page.tab_buttons["active"].click()
    assert page.message_label.text() == bp.APPLY_FIRST_TAB and page.tab == "genus"
    page.genus_editor.save_button.click()
    assert page.message_label.text() == bp.GENUS_APPLIED and page.genus_editor.message.startswith("Genus lines saved.")
    assert page.draft["genus"] == {"Cogni": {"level": 4, "lines": [{"slot": 1, "stat": "Cogni Damage Boost", "value": ""}]}}
    page.tab_buttons["active"].click()
    assert page.tab == "active"


def test_the_advanced_inputs_and_an_evaluation(made):
    page, fake, *_rest = made
    _gladiator(page)
    fake.answers[("POST", "/api/build/evaluate", None)] = [
        EVALUATED, dict(EVALUATED), _refused("/api/build/evaluate", 400, "Another model calculation is running"),
        dict(EVALUATED, arcana_options_supported=False)]
    page.tab_buttons["inputs"].click()
    assert page.inputs_words["components"] == bp.NO_LOADOUT and page.evaluation_shown == bp.NO_EVALUATION
    assert page.input_edits["genus_mix"].toPlainText() == b.stringify(b.GENUS_MIX, 2)
    page.input_edits["loadout"].setPlainText('{"components": [{"slot": "Weapon", "item": "Mine", "stats": {"attack": 25}}]}')
    assert page.evaluation_shown == bp.INPUTS_EDITED and page.pending_inputs()
    page.tab_buttons["active"].click()
    assert page.message_label.text() == bp.APPLY_FIRST_TAB
    page.evaluate()
    assert page.message_label.text() == bp.APPLY_BEFORE_EVALUATING
    page.apply_inputs()
    assert page.message_label.text() == bp.INPUTS_APPLIED and not page.pending_inputs()
    assert page.inputs_words["components"] == [["Weapon", "Mine", "attack"]]
    page.input_edits["genus_mix"].setPlainText("[1]")
    page.apply_inputs()
    assert page.message_label.text() == "Inputs not applied: Invalid genus_mix input."
    page.input_edits["genus_mix"].setPlainText("{bad")
    page.apply_inputs()
    assert page.message_label.text().startswith("Inputs not applied: ")
    page.input_edits["genus_mix"].setPlainText(b.stringify(b.GENUS_MIX, 2))
    page.evaluate()
    assert page.evaluate_button.text() == bp.EVALUATING and not page.evaluate_button.isEnabled()
    assert settle(lambda: page.message_label.text() == bp.EVALUATED)
    sent = [body for m, p, body in fake.calls if p == "/api/build/evaluate"]
    assert sent[-1]["search_priority"] is False and sent[-1]["loadout"]["components"][0]["stats"] == {"attack": 25}
    assert "reference" not in sent[-1] and "name" not in sent[-1]
    assert page.evaluation_shown["scenarios"] == ["pve_boss: 123,456.8 modeled DPS", "pvp_duel: 9,876 modeled DPS"]
    page.priority_box.setChecked(True)
    assert page.evaluation_shown == bp.NO_EVALUATION
    page.evaluate()
    assert settle(lambda: page.message_label.text() == "Evaluation failed: " + bp.NO_PRIORITY_SEARCH)
    page.priority_box.setChecked(False)
    page.evaluate()
    assert settle(lambda: page.message_label.text() == "Evaluation failed: Another model calculation is running")
    assert page.evaluate_button.isEnabled() and page.evaluate_button.text() == bp.EVALUATE
    page.level_edit.setText("30")
    page.level_edit.editingFinished.emit()
    assert not page.evaluate_button.isEnabled()
