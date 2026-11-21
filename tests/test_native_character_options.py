"""My Character's survival options and trained-skill reserves in the native interface (0.2.441), as pages/character.js's
``mountSurvivalOptions`` and ``mountSkillReserves`` draw them: their words, what they show of what was kept, what
an edit keeps, the imports of recorded incoming damage and of optimized opponents, and what an optimization sends.
Off screen, over the fake app of ``test_native_character`` and the bundled sorcerer build (made-up options and names).
"""
import json
import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from aion2calc.gui import character as c  # noqa: E402
from aion2calc.gui.character_options import SkillReserves, SurvivalOptions  # noqa: E402
from aion2calc.gui.character_page import WAIT_S  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_character import HITS, FakeApp, _imported, _page, _texts, sorcerer_view  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

HIT_KEY = '{"name":"Example","level":45,"server":"Testserver","character_id":"id0","server_id":7,"region":"eu"}'
TRACE = {"version": 1, "duration_s": 5.0, "total": 23456.5, "events": [[0.5, 5000.0], [1.25, 8456.5], [3.0, 10000.0]]}
SURVIVAL = {"preserve_hp": True, "min_node_hp": 2000, "current_hp": 48000,
            "opponents": [{"name": "Boss slam", "burst_damage": 12000, "pressure_dps": 800, "window_s": 6, "healing_hps": 300,
                           "healing_delay_s": 1.5, "healing_duration_s": None, "reserve_hp": 500,
                           "reductions": [{"name": "Shield", "kind": "defensive", "skill_id": 15050000, "min_trained": 5,
                                           "effect_id": 15050010, "cooldown_s": 30, "delay_s": 0, "duration_s": 4,
                                           "reduction_pct": 40},
                                          {"name": "Old link", "kind": "control", "skill_id": 99, "min_trained": 2,
                                           "effect_id": None, "cooldown_s": None, "delay_s": 1, "duration_s": 2,
                                           "reduction_pct": 25}]},
                          {"damage_trace": TRACE, "name": "gladiator · pvp_burst timed benchmark", "burst_damage": 0,
                           "pressure_dps": 0, "window_s": 5, "healing_hps": 0, "reserve_hp": 1,
                           "opponent_benchmark": {"source_start_s": 12.5, "source_end_s": 17.5, "method": "timed"}}],
            "action_windows": [{"name": "Dodge", "start_s": 10, "duration_s": 1.5, "skill_id": 15200000, "min_trained": 13,
                                "effect_id": None, "cooldown_s": 20, "reserve_cooldown": True},
                               {"name": "Tactical time 2", "start_s": 0, "duration_s": 0}]}
RESERVES = {"sp": {"15050000": 8}, "stigmas": {"15200000": 15}, "specs": {"15040000": [15040020]}}


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


def _store(tmp_path, **kept):
    store = QSettings(str(tmp_path / "options.ini"), QSettings.IniFormat)
    for key, value in kept.items():
        store.setValue(key, value)
    return store


def _typed(field, text):
    """Text typed in a field and the field left (a ``change``)."""
    field.setText(text)
    field.setModified(True)
    field.editingFinished.emit()


def test_the_options_words():
    # JavaScript's values: String(x), Number(x), JSON.stringify, and what a number field keeps
    assert [c.js_string(x) for x in (1e21, 1e16, 1.5e-7, 0.000001, -0.5, 5.0, True, None, [1, None, 2.5], {})] == [
        "1e+21", "10000000000000000", "1.5e-7", "0.000001", "-0.5", "5", "true", "null", "1,,2.5", "[object Object]"]
    assert [c.js_number(x) for x in ("", " 12 ", "0x1A", "Infinity", None, True, [5], "1.")] == [0, 12, 26, math.inf, 0, 1, 5, 1]
    assert all(math.isnan(c.js_number(x)) for x in ("1_000", "abc", "inf", {}, "1e"))
    assert c.store_text({"b": 1.0, "10": math.nan, "2": [2.5, math.inf]}) == '{"2":[2.5,null],"10":null,"b":1}'
    assert [c.field_value(x) for x in (" 5 ", "5.", "1e3", "abc", "-0.5", "+5")] == ["5", "", "1e3", "", "-0.5", ""]
    assert [c.field_text(x) for x in (2.5, "x", None, 1e21, "12", True)] == ["2.5", "", "", "1e+21", "12", ""]
    hit = json.loads(HIT_KEY)
    assert c.options_key(c.SURVIVAL_PREFIX, hit, {"key": "eu:7:id0"}) == "character-survival:" + HIT_KEY
    assert c.options_key(c.RESERVES_PREFIX, None, {"key": "eu:7:id0"}) == 'character-skill-reserves:"eu:7:id0"'
    assert c.options_key(c.RESERVES_PREFIX, {}, {"key": "k"}) == "character-skill-reserves:{}"   # an object is true
    # the reserves: the rows, what was kept, the minimum within 1 and the row's maximum
    v = {"skills": {"active": [{"id": 11, "name": "Blaze", "sp": 10, "buy_max": 8,
                                "specs": [{"id": 111, "n": 1, "unlock": 8, "text": "Absorbs"}, {"id": 112, "n": 2, "unlock": 12, "text": "Fast"}]}],
                    "passive": [{"id": 12, "name": "Robe", "sp": None, "buy_max": 0, "specs": []}]},
         "stigmas": [{"id": 13, "name": "Storm", "level": 25}]}
    rows = c.reserve_rows(v)
    assert [(r["field"], r["level"], r["max"]) for r in rows] == [("sp", 10, 8), ("sp", None, 10), ("stigmas", 25, 20)]
    assert [c.reserve_name(r) for r in rows] == ["Blaze", "Robe", "Storm · keep equipped"]
    saved = {"sp": {"11": 3, "12": "x"}, "stigmas": {"13": 0}, "specs": {"11": [112], "12": "1"}}
    assert [c.reserve_checked(saved, r) for r in rows] == [True, True, False]
    assert [c.reserve_level(saved, r) for r in rows] == ["3", "", "20"]   # "x" reads NaN: an empty field
    assert [c.effect_line(e) for e in c.reserve_effects(rows[0])] == ["1. Absorbs · effect Lv 8", "2. Fast · effect Lv 12"]
    assert [c.effect_checked(saved, rows[0], e) for e in rows[0]["specs"]] == [False, True]
    assert c.reserve_effects(rows[2]) == [] and c.effect_checked({"specs": {"11": "1112"}}, rows[0], {"id": 111})
    assert [c.level_ok(x, 8) for x in ("", "1", "8", "9", "0", "2.5", "abc", "1e0")] == [True, True, True, False, False, False,
                                                                                       False, True]
    plan, retained, through, problem = c.reserve_read(rows, [True, False, False], ["3", "", "20"], [[], [], []])
    assert (plan, retained, through, problem) == ({"sp": {"11": 3}, "stigmas": {}, "specs": {}}, [True, False, False], 3, "")
    plan, retained, through, problem = c.reserve_read(rows, [False, False, True], ["9", "", "21"], [[112], [], []])
    assert (retained, through, problem) == ([True, False, True], 1, c.RESERVE_BAD)                  # an effect retains its row
    assert c.reserve_read(rows, [False, True, False], ["5", "", "4"], [[], [], []])[0]["sp"] == {"12": 0}   # empty reads 0
    # the survival options: the defaults, then what was kept (eight of each)
    assert c.survival_settings(None) == {"preserve_hp": True, "min_node_hp": 0, "current_hp": None, "opponents": [],
                                         "action_windows": []}
    kept = c.survival_settings({"preserve_hp": False, "opponents": [{}] * 9, "action_windows": "x", "other": 1})
    assert (kept["preserve_hp"], len(kept["opponents"]), kept["action_windows"], kept["other"]) == (False, 8, [], 1)
    assert c.read_saved("{bad") is None and c.read_saved(None) is None
    # a link's lists: the skills (an action-time window's without the passive ones), the effects, the minimum's range
    choices = c.skill_choices(v)
    assert c.skill_options(choices, 11) == ([("", "Unlinked assumption"), ("11", "Blaze · active"), ("12", "Robe · passive"),
                                             ("13", "Storm · stigma")], 1)
    assert c.skill_options(choices, 12, actions_only=True) == ([("", "Unlinked assumption"), ("11", "Blaze · active"),
                                                                ("13", "Storm · stigma"), ("12", "Unavailable skill #12")], 3)
    assert c.skill_options(choices, None)[1] == 0 and c.skill_options(choices, "13")[1] == 3
    assert c.effect_options(choices, 11, 112) == ([("", "No specific effect"), ("111", "Absorbs · effect Lv 8"),
                                                   ("112", "Fast · effect Lv 12")], 2)
    assert c.effect_options(choices, 13, 5) == ([("", "No specific effect"), ("5", "Unavailable effect #5")], 1)
    assert [c.level_max(choices, x) for x in (11, 12, 13, None)] == [8, 10, 20, 10]
    assert [c.clamp_level(m, t) for m, t in ((8, "12"), (20, ""), (10, "3"), ("x", "3"))] == ["8", "1", "3", ""]
    # what the fields read: numbers, or none for an empty link
    assert c.read_action({"name": "Dodge", "start_s": "10", "duration_s": "", "skill_id": "", "min_trained": "1",
                          "effect_id": "", "cooldown_s": "", "reserve_cooldown": True}) == {
        "name": "Dodge", "start_s": 10, "duration_s": 0, "skill_id": None, "min_trained": 1, "effect_id": None,
        "cooldown_s": None, "reserve_cooldown": True}
    reduction = {"name": "Shield", "kind": "control", "skill_id": "11", "min_trained": "2", "effect_id": "112",
                 "cooldown_s": "0", "delay_s": "1.5", "duration_s": "4", "reduction_pct": "40"}
    fields = {"name": "Slam", "burst_damage": "12000", "pressure_dps": "", "window_s": "6", "healing_hps": "0",
              "healing_delay_s": "0", "healing_duration_s": "", "reserve_hp": "1"}
    row = c.read_pressure(fields, [reduction], {"damage_trace": TRACE, "recorded_evidence": {}, "opponent_benchmark": "",
                                                "name": "old"})
    assert row["healing_duration_s"] is None and row["pressure_dps"] == 0 and row["damage_trace"] == TRACE
    assert row["recorded_evidence"] == {} and "opponent_benchmark" not in row          # an empty object is true, "" not
    assert row["reductions"][0]["cooldown_s"] == 0 and row["reductions"][0]["skill_id"] == 11 and row["name"] == "Slam"
    assert c.read_survival(True, "", "", [], [])["current_hp"] is None and c.read_survival(False, "5", "9", [], [])["current_hp"] == 9
    # an imported opponent's timed hits, a scenario's windows, why benchmarks cannot be imported
    assert c.trace_line({"damage_trace": TRACE, "opponent_benchmark": {"source_start_s": 12.5, "source_end_s": 17.5}}) == (
        "Timed expected hits · 3 hits · 23,457 damage · source 12.5–17.5s")
    assert [c.windows_count(r) for r in ({"reductions": [{}, {}]}, {}, {"reductions": {"a": 1}})] == [2, 0, 0]
    assert [c.benchmark_problem(*x) for x in ((8, [1], "1"), (0, [], "1"), (7, [1, 1], "1"), (0, [21 * 2 ** 20], "1"),
                                              (0, [11 * 2 ** 20] * 2, "1"), (0, [1], ""), (0, [1], "1"))] == [
        c.FULL, c.NO_FILES, c.TOO_MANY, c.TOO_BIG, c.TOO_BIG, c.NO_SCALE, ""]
    assert c.benchmarks_imported(2) == ("2 opponent benchmarks imported. Review current HP, healing and defensive windows "
                                        "before optimizing.")


def test_the_skill_reserves_panel(qapp, view, tmp_path):
    key = "character-skill-reserves:" + HIT_KEY
    store = _store(tmp_path, **{key: json.dumps(RESERVES)})
    toasts = []
    panel = SkillReserves(store, key, view, toasts.append)
    assert panel.button.text() == c.RESERVES_TITLE and not panel.body.isVisibleTo(panel)            # closed
    names = [panel.table.cell(i + 1, 1).text() for i in range(len(panel.rows))]
    assert len(names) == 26 and names[:2] == ["Blaze", "Firestorm"] and names[-4] == "Cold Storm · keep equipped"
    retained = [i for i, box in enumerate(panel.boxes) if box.isChecked()]
    assert retained == [0, 1, 22]                         # kept, an effect kept (Firestorm), a stigma kept
    assert [panel.levels[i].text() for i in (0, 1, 11, 22, 25)] == ["8", "10", "1", "15", "8"]
    assert [f.isEnabled() for f in panel.levels] == [i in retained for i in range(26)]               # the others off
    assert [check.isChecked() for _e, check in panel.effects[1]] == [False, True, False, False, False]
    assert panel.effects[0][0][1].text() == "1. Absorbs 300, 300% HP · effect Lv 8" and panel.effects[13] == []
    # a box, a minimum and an effect: each kept at once
    panel.boxes[3].click()
    assert panel.levels[3].isEnabled()
    _typed(panel.levels[3], "7")
    panel.effects[2][1][1].click()                        # an effect retains its skill
    assert panel.boxes[2].isChecked() and panel.levels[2].isEnabled()
    assert json.loads(store.value(key)) == {"sp": {"15010000": 10, "15040000": 10, "15050000": 8, "15060000": 7},
                                            "stigmas": {"15200000": 15},
                                            "specs": {"15010000": [15010020], "15040000": [15040020]}}
    # a minimum outside its range: said, and not kept
    _typed(panel.levels[22], "21")
    assert toasts == [c.RESERVE_BAD] and json.loads(store.value(key))["stigmas"] == {"15200000": 15}
    with pytest.raises(ValueError, match="Reserve levels must be whole numbers"):
        panel.read()
    _typed(panel.levels[22], "20")
    assert panel.read()["stigmas"] == {"15200000": 20} and len(toasts) == 1
    # nothing kept: every minimum off at its trained level
    (tmp_path / "fresh").mkdir()
    fresh = SkillReserves(_store(tmp_path / "fresh"), key, view, toasts.append)
    assert not any(b.isChecked() for b in fresh.boxes) and not any(f.isEnabled() for f in fresh.levels)
    assert fresh.read() == {"sp": {}, "stigmas": {}, "specs": {}}


def test_the_survival_panel(qapp, view, tmp_path):
    key = "character-survival:" + HIT_KEY
    store = _store(tmp_path, **{key: json.dumps(SURVIVAL)})
    toasts = []
    panel = SurvivalOptions(store, key, view, lambda *a: None, toasts.append)
    panel.resize(1200, 2000)
    panel.show()
    QCoreApplication.processEvents()
    assert panel.button.text() == c.SURVIVAL_TITLE and not panel.body.isVisibleTo(panel)
    assert panel.preserve.isChecked() and (panel.floor.text(), panel.current.text()) == ("2000", "48000")
    assert panel.current.placeholderText() == "Optional"
    slam, bench = panel.pressure_rows
    assert {k: w.text() for k, (_kind, w) in slam["fields"].items()} == {
        "name": "Boss slam", "burst_damage": "12000", "pressure_dps": "800", "window_s": "6", "healing_hps": "300",
        "healing_delay_s": "1.5", "healing_duration_s": "", "reserve_hp": "500"}
    assert slam["fields"]["healing_duration_s"][1].placeholderText() == "Rest of window" and slam["trace"] is None
    assert bench["trace"].text() == "Timed expected hits · 3 hits · 23,457 damage · source 12.5–17.5s"
    assert bench["fields"]["window_s"][1].isReadOnly() and bench["fields"]["window_s"][1].toolTip() == c.WINDOW_LOCKED
    assert (slam["fold"].button.text(), bench["fold"].button.text()) == ("2 assumed windows", "0 assumed windows")
    shield, old = slam["reductions"]
    assert (shield["kind"][1].currentText(), shield["skill_id"][1].currentText(), shield["effect_id"][1].currentText()) == (
        "Defensive", "Blaze · active", "Absorbs 300, 300% HP · effect Lv 8")
    assert old["skill_id"][1].currentText() == "Unavailable skill #99" and old["cooldown_s"][1].placeholderText() == "Unknown"
    dodge, second = panel.action_rows
    assert [box.title() for box in panel.action_boxes] == ["Action-time window 1", "Action-time window 2"]
    assert dodge["skill_id"][1].currentText() == "Cold Storm · stigma" and dodge["reserve_cooldown"][1].isChecked()
    assert not any(dodge["skill_id"][1].itemText(i).endswith("· passive") for i in range(dodge["skill_id"][1].count()))
    assert [second[k][1].isEnabled() for k in ("min_trained", "effect_id", "cooldown_s")] == [False, False, False]
    texts = [label.text() for label in panel.findChildren(QLabel)]
    for note in (c.SURVIVAL_NOTE, c.HITS_NOTE, c.REDUCTIONS_NOTE, c.ACTION_NOTE, c.ACTION_LINKS_NOTE, c.RECORDED_NOTE,
                 c.BENCHMARK_NOTE, c.SCENARIOS_NOTE):
        assert note in texts
    # another skill linked: its effects, no effect or cooldown yet, no reserve, the minimum within its range
    box = dodge["skill_id"][1]
    box.setCurrentIndex(box.findData("15050000"))                                 # Blaze, at most 10
    assert dodge["effect_id"][1].count() == 6 and dodge["effect_id"][1].currentIndex() == 0
    assert (dodge["cooldown_s"][1].text(), dodge["reserve_cooldown"][1].isChecked(), dodge["min_trained"][1].text()) == (
        "", False, "10")
    box.setCurrentIndex(0)                                                        # unlinked: its fields off
    assert not dodge["min_trained"][1].isEnabled() and not dodge["effect_id"][1].isEnabled()
    kept = json.loads(store.value(key))
    assert kept["action_windows"][0] == {"name": "Dodge", "start_s": 10, "duration_s": 1.5, "skill_id": None, "min_trained": 10,
                                         "effect_id": None, "cooldown_s": None, "reserve_cooldown": False}
    assert kept["opponents"][1]["damage_trace"] == TRACE and kept["opponents"][1]["healing_duration_s"] is None
    assert list(kept) == ["preserve_hp", "min_node_hp", "current_hp", "action_windows", "opponents"]
    # typed values: a number, nothing, or what does not read as one (nothing)
    _typed(panel.current, "")
    _typed(slam["fields"]["burst_damage"][1], "abc")
    _typed(panel.floor, "1e3")
    kept = json.loads(store.value(key))
    assert (kept["current_hp"], kept["opponents"][0]["burst_damage"], kept["min_node_hp"]) == (None, 0, 1000)
    # adding and removing: the panel stays open, a scenario's windows open where one was added
    panel.button.setChecked(True)
    panel.pressure_rows[1]["add"].click()
    assert panel.button.isChecked() and panel.pressure_rows[1]["fold"].button.isChecked()
    assert panel.pressure_rows[1]["fold"].button.text() == "1 assumed windows"
    assert json.loads(store.value(key))["opponents"][1]["reductions"] == [c.new_reduction()]
    panel.pressure_rows[0]["removes"][0].click()
    assert [r["name"] for r in json.loads(store.value(key))["opponents"][0]["reductions"]] == ["Old link"]
    panel.add_window.click()
    assert [box.title() for box in panel.action_boxes][-1] == "Action-time window 3"
    assert panel.action_rows[2]["name"][1].text() == "Tactical time 3"
    panel.action_removes[0].click()
    assert [r["name"] for r in json.loads(store.value(key))["action_windows"]] == ["Tactical time 2", "Tactical time 3"]
    for _ in range(6):
        panel.add_scenario.click()
    assert len(panel.pressure_rows) == 8 and not panel.add_scenario.isEnabled() and panel.button.isChecked()
    assert panel.pressure_rows[7]["fields"]["name"][1].text() == "Pressure 8"
    panel.pressure_rows[0]["remove"].click()
    assert len(json.loads(store.value(key))["opponents"]) == 7 and panel.add_scenario.isEnabled()
    assert c.to_json(panel.save()) == json.loads(store.value(key))              # what is sent is what is kept
    assert not toasts


def test_the_survival_imports(qapp, view, tmp_path):
    app = FakeApp(view)
    page, store = _page(app, tmp_path)
    _imported(page)
    panel = page.survival
    log = tmp_path / "fight.json"
    log.write_text(json.dumps({"format": "a2log", "players": [{"id": "p1", "name": "Example"}]}), encoding="utf-8")
    # a recording: its encounters where players were hit, then one recipient's window imported as a scenario
    encounters = [{"index": 0, "label": "Boss", "mode": "pve", "targets": [{"id": "p1", "name": "Example"}]},
                  {"index": 2, "label": "Arena", "mode": "pvp", "targets": [{"id": "p2", "name": "Other"}, {"id": "p1", "name": "Example"}]}]
    scenario = {"name": "Other · Arena", "burst_damage": 4200.5, "pressure_dps": 0, "window_s": 5.0, "healing_hps": 0,
                "reserve_hp": 1, "recorded_evidence": {"title": "Arena", "damage": 4200.5}}
    app.answers["/api/character/pressure"] = [{"encounters": encounters}, {"scenario": scenario}]
    panel.use_recording(str(log))
    settle(lambda: getattr(panel, "use_pressure", None) is not None)
    assert app.posts[-1] == ("/api/character/pressure", {"log": json.loads(log.read_text())})
    assert [panel.encounter.itemText(i) for i in range(2)] == ["Boss · pve", "Arena · pvp"]
    panel.encounter.setCurrentIndex(1)
    assert [panel.recipient.itemText(i) for i in range(panel.recipient.count())] == ["Other", "Example"]
    _typed(panel.seconds, "7.5")
    panel.use_pressure.click()
    settle(lambda: len(panel.pressure_rows) == 1)
    assert app.posts[-1][1] == {"log": json.loads(log.read_text()), "segment": 2, "target": "p2", "window_s": 7.5}
    assert panel.pressure_rows[0]["fields"]["name"][1].text() == "Other · Arena" and panel.button.isChecked()
    assert page.toast.text() == c.PRESSURE_IMPORTED
    kept = json.loads(store.value(c.options_key(c.SURVIVAL_PREFIX, HITS[0], page.view)))
    assert kept["opponents"][0]["recorded_evidence"] == scenario["recorded_evidence"]
    assert app.waits[-1] == ("/api/character/pressure", WAIT_S)               # a large recording may take a while
    # a recording the app cannot read, and one too large to send
    app.answers["/api/character/pressure"] = [ValueError("Not an a2log")]
    panel.use_recording(str(log))
    settle(lambda: "Import failed: " in " ".join(_texts(panel)))
    assert "Import failed: Not an a2log" in _texts(panel) and panel.recording is None
    original = c.RECORDING_MIB
    c.RECORDING_MIB = 0
    try:
        panel.use_recording(str(log))
    finally:
        c.RECORDING_MIB = original
    QCoreApplication.processEvents()
    assert "Import failed: " + c.RECORDING_TOO_BIG in _texts(panel)
    # optimized opponents: the checks, then each result read in turn, all added or none
    panel.import_results()
    assert panel.status.text() == "Import failed: " + c.NO_FILES and panel.use_results.isEnabled()
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    for path in (one, two):
        path.write_text(json.dumps({"kind": "optimize-class", "result": {"class": "gladiator"}}), encoding="utf-8")
    panel.use_results_files([str(one), str(two)])
    assert panel.results_name.text() == "2 files"
    panel.import_results()
    assert panel.status.text() == "Import failed: " + c.NO_SCALE
    _typed(panel.scale, "0.8")
    bench = {"name": "gladiator · pvp_burst timed benchmark", "burst_damage": 0, "pressure_dps": 0, "window_s": 5,
             "healing_hps": 0, "reserve_hp": 1, "damage_trace": TRACE, "opponent_benchmark": {"source_start_s": 0, "source_end_s": 5}}
    app.answers["/api/character/opponent-pressure"] = [{"scenario": bench}, ValueError("This saved result is not an optimized PvP build")]
    panel.import_results()
    settle(lambda: panel.status.text().startswith("Import failed"))
    assert panel.status.text() == ("Import failed: two.json: This saved result is not an optimized PvP build. No scenarios from "
                                   "this batch were added.")
    assert len(panel.pressure_rows) == 1 and panel.use_results.isEnabled()
    assert app.posts[-1] == ("/api/character/opponent-pressure", {"result": json.loads(two.read_text()), "metric": "pvp_burst",
                                                                  "scale": 0.8, "window_s": 5, "method": "timed"})
    app.answers["/api/character/opponent-pressure"] = [{"scenario": bench}, {"scenario": dict(bench, name="second")}]
    panel.import_results()
    settle(lambda: len(panel.pressure_rows) == 3)
    assert [r["fields"]["name"][1].text() for r in panel.pressure_rows][1:] == [bench["name"], "second"]
    assert panel.pressure_rows[1]["trace"].text().startswith("Timed expected hits · 3 hits")
    assert page.toast.text() == c.benchmarks_imported(2) and panel.results_name.text() == "No file chosen"
    # an answer for a panel drawn before is not drawn on the character shown now
    app.answers["/api/character/pressure"] = [{"encounters": encounters}]
    panel.use_recording(str(log))
    _imported(page)
    settle(lambda: app.answers["/api/character/pressure"] == [])
    QCoreApplication.processEvents()
    assert page.survival is not panel and page.survival.recording is None


def test_an_optimization_sends_the_options(qapp, view, tmp_path):
    app = FakeApp(view)
    app.jobs["opt"] = {"reads": 3, "log": ["Searching"], "result": {"optimized": view, "summary": {"gain": 0.01}, "diff": ""}}
    page, store = _page(app, tmp_path)
    survival_key = c.options_key(c.SURVIVAL_PREFIX, HITS[0], view)
    store.setValue(survival_key, json.dumps(SURVIVAL))
    _imported(page)
    waits = dict(app.waits)                                                     # the page's requests wait as a browser would
    assert waits["/api/characters"] == waits["/api/ui"] == WAIT_S and waits["/api/character/import"] is None   # a job's own
    panel, reserves = page.survival, page.reserves
    _typed(panel.floor, "2500")
    reserves.boxes[0].click()
    _typed(reserves.levels[0], "11")                                            # above Blaze's 10: said, not sent
    page.optimize("pve")
    QCoreApplication.processEvents()
    assert c.RESERVE_BAD in _texts(page) and [p for p, _b in app.posts] == ["/api/character/import"]
    _typed(reserves.levels[0], "9")
    page.optimize("pvp")
    settle(lambda: any(p == "/api/character/optimize" for p, _b in app.posts))
    body = app.posts[-1][1]
    assert body["skill_reserves"] == {"sp": {"15050000": 9}, "stigmas": {}, "specs": {}}
    assert body["survival"]["min_node_hp"] == 2500 and body["survival"]["current_hp"] == 48000
    assert [r["name"] for r in body["survival"]["opponents"]] == ["Boss slam", "gladiator · pvp_burst timed benchmark"]
    assert body["survival"]["opponents"][0]["reductions"][1]["skill_id"] == 99 and body["survival"]["opponents"][1]["damage_trace"] == TRACE
    assert body["survival"]["action_windows"][0]["reserve_cooldown"] is True
    assert json.loads(store.value(survival_key)) == body["survival"]                # what was sent is kept
    settle(lambda: page.opt["status"] == "done")
