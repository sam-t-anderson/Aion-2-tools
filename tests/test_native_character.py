"""The native My Character page (0.2.440): the search, an import, the character's counts and budgets, the Genus choice,
an optimization's request, progress and result, and the character's result windows, as pages/character.js shows them,
off screen, over a fake app answering as the app does. The character is the bundled sorcerer build dressed with a
made-up character's name, server and points (no real character).
"""
import json
import os
import pathlib
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton  # noqa: E402

from aion2calc.gui import character as c  # noqa: E402
from aion2calc.gui.character_page import LONG_AGO, CharacterPage  # noqa: E402
from aion2calc.gui.database_page import Kpi  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
KNOWN = [{"character_id": f"id{i}", "server_id": 7, "region": "eu", "name": f"Example{i}", "class_name": "sorcerer",
          "combat_power": 3500 + i} for i in range(10)]
HITS = [{"name": "Example", "level": 45, "server": "Testserver", "character_id": "id0", "server_id": 7, "region": "eu"},
        {"name": "Example Two", "level": 30, "server": "Other", "character_id": "id9", "server_id": 8, "region": "eu"}]


def sorcerer_view() -> dict:
    """The bundled sorcerer build as the app's view of it, dressed as a made-up character."""
    from aion2calc.app.views import build_view
    built = build_view(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))
    built.update(key="eu:7:id0", name="Example", server="Testserver", level=45, level_cap=45, combat_power=3512,
                 warnings=["Some gear could not be read"], dps={"boss": 41000.4, "dummy": 39000},
                 points={"skill": 380, "stigma": 180, "daevanion": 410, "ariel": 0},
                 budgets={"skill": 383, "stigma": 188, "daevanion": 417, "ariel": 12})
    return built


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


class FakeApp:
    """The app as My Character asks it: the characters imported before, the settings, the search, the import and
    optimization jobs (each read ``reads`` times before it ends), and the survival panel's imports (``answers``: a
    path's answers in turn, an exception raised)."""

    def __init__(self, view, ui=None, known=KNOWN):
        self.view, self.ui, self.known = view, ui or {}, known
        self.calls, self.posts, self.waits = [], [], []
        self.jobs = {"imp": {"reads": 2, "log": ["Reading the profile"], "result": view}}
        self.answers = {}
        self.genus = {}                                  # the character's saved Genus lines
        self.screen = {"available": False, "message": "Reading the game screen needs Windows 10 or later."}

    def get(self, path, timeout=None):
        self.waits.append((path, timeout))
        self.calls.append(path)
        if path == "/api/characters":
            return json.loads(json.dumps(self.known))
        if path == "/api/ui":
            return dict(self.ui)
        if path.startswith("/api/character/search?"):
            return json.loads(json.dumps(HITS))
        if path.startswith("/api/community?path="):
            assert urllib.parse.unquote(path.split("=", 1)[1]).startswith("/api/v1/progression?class=sorcerer")
            return {"observations": [{"class_name": "sorcerer", "skill": 390, "stigma": 190, "daevanion": 420, "ariel": 30}]}
        if path.startswith("/api/inventory?character="):
            return {"genus": json.loads(json.dumps(self.genus))}
        if path.startswith("/api/screen-read?since="):
            return dict(self.screen)
        if path.startswith("/api/jobs/"):
            job = self.jobs[path.rsplit("/", 1)[1]]
            job["reads"] -= 1
            if job["reads"] > 0:
                return {"status": "running", "log": job["log"]}
            return {"status": "error", "error": job["error"]} if job.get("error") else {"status": "done", "result": job["result"]}
        raise AssertionError(path)

    def get_bytes(self, path):
        raise OSError("no pictures here")

    def post(self, path, body, timeout=None):
        self.waits.append((path, timeout))
        self.posts.append((path, json.loads(json.dumps(body))))
        if path in self.answers:
            answer = self.answers[path].pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        if path == "/api/inventory/genus":
            self.genus = json.loads(json.dumps(body["genus"]))
            return {"genus": json.loads(json.dumps(self.genus))}
        return {"job": {"/api/character/import": "imp", "/api/character/optimize": "opt"}[path]}


def _page(app, tmp_path, **kwargs):
    store = QSettings(str(tmp_path / "native.ini"), QSettings.IniFormat)
    page = CharacterPage(app, store=store, **kwargs)
    for job in (page.importing, page.optimizing):
        job.interval_ms = 10
    page.resize(1300, 1800)
    page.show()
    settle(lambda: "/api/characters" in app.calls and (not app.known or page.known))
    QCoreApplication.processEvents()
    return page, store


def _imported(page, hit=None):
    page.import_character(hit or HITS[0])
    settle(lambda: page.character is not None)
    QCoreApplication.processEvents()


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    QCoreApplication.processEvents()
    return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)


def test_the_character_words(view):
    assert c.search_path("Ex ample&", "eu") == "/api/character/search?name=Ex%20ample%26&region=eu"
    assert c.known_line(KNOWN[1]) == "Example1 · sorcerer · 3,501"
    assert c.known_hit(KNOWN[0]) == {"character_id": "id0", "server_id": 7, "region": "eu", "name": "Example0"}
    assert c.hit_row(HITS[0]) == ["Example", "45", "Testserver"]
    assert c.importing({"name": "Example"}, LONG_AGO) == "opening the last snapshot of Example…"
    assert c.importing({}, 5) == "opening the last snapshot of the character…" and c.importing({}, 0) == "importing from the official site…"
    assert c.subtitle(view) == "Sorcerer · Lv 45 · Testserver · Combat Power 3,512"
    assert c.budget_keys(view) == ["skill", "stigma", "daevanion", "ariel"]
    assert c.budget_keys({"points": {"skill": 1}}) == ["skill", "stigma", "daevanion"]
    assert c.kpis(view) == [("boss imported DPS (without manual Genus)", "41,000"), ("dummy imported DPS (without manual Genus)", "39,000"),
                            ("Skill points", "380 / 383"), ("Stigma points", "180 / 188"), ("Daevanion", "410 / 417"),
                            ("Ariel crystal", "0 / 12")]
    assert c.kpis({**view, "genus": {"x": 1}, "budgets": {}})[0][0] == "boss saved build DPS"
    assert c.kpis({**view, "budgets": {}})[2] == ("Skill points", "380 / Unknown")
    # the totals in the fields: the budget, a total typed above it, never below what is spent
    assert c.available(view, {}) == {"skill": 383, "stigma": 188, "daevanion": 417, "ariel": 12}
    assert c.available(view, {"skill": 400, "stigma": 100}) == {"skill": 400, "stigma": 180, "daevanion": 417, "ariel": 12}
    assert c.remembered(view, {"skill": 400, "stigma": 180, "daevanion": None}) == {"skill": 400}
    assert c.read_store("{bad") == {} and c.read_store("[1]") == {} and c.read_store(None) == {}
    assert c.field_values({"skill": " 383 ", "stigma": "x"}) == {"skill": 383, "stigma": None}
    assert c.community_note({"skill": 390, "stigma": None, "daevanion": 420, "ariel": 30}, ["skill", "stigma", "daevanion", "ariel"]) == (
        "Highest totals reported for the class: skill 390, daevanion 420, Ariel crystal 30. The optimizer uses your totals "
        "above; type yours in if you have points left unspent.")
    assert c.community_note({"skill": None}, ["skill"]) == ""
    assert c.at_level_cap(view) and not c.at_level_cap({"level": 30}) and c.at_level_cap({})
    # the Genus choice: the PvE mix, checked; PvP and off send only whether
    mix = {"Cogni": "25", "Fera": "25", "Natura": "25", "Varian": "25", "Special": "0"}
    assert c.genus_choice(True, mix, "pve") == {"enabled": True, "mix": {"Cogni": 25.0, "Fera": 25.0, "Natura": 25.0,
                                                                         "Varian": 25.0, "Special": 0.0}}
    assert c.genus_choice(True, mix, "pvp") == {"enabled": True} and c.genus_choice(False, mix, "pve") == {"enabled": False}
    for wrong in ({**mix, "Cogni": "101"}, {g: "0" for g in mix}, {**mix, "Fera": "x"}):
        with pytest.raises(ValueError, match="Set a positive PvE Genus mix"):
            c.genus_choice(True, wrong, "pve")
    assert c.genus_choice(True, {**mix, "Special": ""}, "pve")["mix"]["Special"] == 0.0           # Number("") is 0
    survival = {"preserve_hp": True, "min_node_hp": 2000.0, "current_hp": float("nan"), "action_windows": [], "opponents": []}
    body = c.optimize_body(HITS[0], "world", "balanced", {"skill": 383}, survival, {"sp": {"15": 8.0}, "stigmas": {}, "specs": {}},
                           {"enabled": False}, " 1.2 ")
    assert body["mode"] == "world" and body["objective"] == "balanced" and body["game_patch"] == "1.2"
    assert body["survival"] == {"preserve_hp": True, "min_node_hp": 2000, "current_hp": None, "action_windows": [], "opponents": []}
    assert body["skill_reserves"] == {"sp": {"15": 8}, "stigmas": {}, "specs": {}} and isinstance(body["survival"]["min_node_hp"], int)
    assert body["character_id"] == "id0" and body["budgets"] == {"skill": 383} and body["genus"] == {"enabled": False}
    # the run's progress and result
    assert c.running("world", []) == ("Optimizing World PvP (experimental) — starting…", "")
    line, tail = c.running("pve", [f"step {i}" for i in range(10)])
    assert line == "Optimizing PvE build — step 9" and tail.split("\n") == [f"step {i}" for i in range(2, 10)]
    assert c.elsewhere("Example") == "Optimizing Example: open that character to follow it; a new optimization can start when it finishes."
    done = c.result({"summary": {"gain": 0.0525, "objective": {"score": 51000, "label": "weighted DPS"}},
                     "optimized": {"model_note": "A note"}, "preset": {"submitted": True, "accepted": True}, "diff": "+ Blaze 10"})
    assert (done["label"], done["score"], done["gain"], done["good"]) == ("Optimized weighted DPS", "51,000", "+5.3%", True)
    assert done["preset"] == "This build is now the community preset for its class." and done["diff"] == "+ Blaze 10"
    kept = c.result({"summary": {"scenario": "pvp"}, "optimized": {"dps": {"pvp": 900}}, "preset": {"submitted": True}})
    assert (kept["label"], kept["score"], kept["gain"]) == ("Optimized PvP proxy DPS", "900", "Unavailable")
    assert kept["preset"] == "The server kept its current Planner preset: no improvement at the shared budgets"
    assert c.result({"summary": {"gain": -0.01}, "preset": {"reason": "offline"}})["preset"] == "Community preset: offline"
    assert c.optimized_view({"optimized": {"class": "sorcerer", "name": "x"}}, {"name": "Example"}) == {"class": "sorcerer", "name": "Example"}


def test_the_search_an_import_and_the_characters_before(qapp, view, tmp_path):
    app = FakeApp(view)
    page, _store = _page(app, tmp_path)
    known = [b.text() for b in page.findChildren(QPushButton) if b.text().startswith("Example") and b.isVisibleTo(page)]
    assert known == [c.known_line(k) for k in KNOWN[:8]]                         # at most eight, newest first
    page.name.setText("Example")
    page.region.setCurrentIndex(page.region.findData("eu"))
    _button(page, "Search").click()
    settle(lambda: page.message.text() == "2 found")
    assert "/api/character/search?name=Example&region=eu" in app.calls
    assert "Example Two" in _texts(page) and "Testserver" in _texts(page)
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Import Example").click()
    settle(lambda: page.character is not None)
    assert app.posts[0] == ("/api/character/import", HITS[0])
    texts = _texts(page)
    assert "EXAMPLE" in texts and c.subtitle(view) in texts and c.POINTS_NOTE in texts and "• Some gear could not be read" in texts
    tiles = [(k.findChild(QLabel, "kpiName").text(), k.value.text()) for k in page.character.findChildren(Kpi)]
    assert tiles == [(name.upper(), value) for name, value in c.kpis(view)]
    assert {k: f.text() for k, f in page.fields.items()} == {"skill": "383", "stigma": "188", "daevanion": "417", "ariel": "12"}
    settle(lambda: page.community.isVisibleTo(page))
    assert page.community.text().startswith("Highest totals reported for the class: skill 390, stigma 190")
    assert page.windows.isVisible() and page.windows.view["name"] == "Example"
    # a character imported before: fetched again by its ids
    next(b for b in page.findChildren(QPushButton) if b.text() == c.known_line(KNOWN[1])).click()
    settle(lambda: len(app.posts) == 2)
    assert app.posts[1] == ("/api/character/import", c.known_hit(KNOWN[1]))


def test_budgets_kept_and_an_optimization(qapp, view, tmp_path):
    app = FakeApp(view)
    optimized = json.loads(json.dumps(view))
    optimized["name"] = "Optimized name the windows should not show"
    app.jobs["opt"] = {"reads": 4, "log": ["Searching stigmas"], "result": {
        "optimized": optimized, "summary": {"gain": 0.04, "scenario": "boss"}, "diff": "+ Blaze 10\n- Frost 1",
        "preset": {"submitted": True, "accepted": False, "reason": "already better"}}}
    page, store = _page(app, tmp_path)
    _imported(page)
    page.fields["skill"].setText("400")
    page.fields["stigma"].setText("150")                                       # below what is spent: not kept
    page.fields["skill"].editingFinished.emit()
    assert json.loads(store.value(c.BUDGETS_KEY)) == {"eu:7:id0": {"skill": 400, "daevanion": 417, "ariel": 12}}   # above spent
    page.patch.setText(" 1.2.3 ")
    page.patch.editingFinished.emit()
    page.objective.setCurrentIndex(1)
    page.objective.activated.emit(1)
    assert (store.value(c.PATCH_KEY), store.value(c.OBJECTIVE_KEY)) == ("1.2.3", "balanced")
    # a mix that cannot be: said, and nothing sent
    page.mix["Cogni"].setText("200")
    page.optimize("pve")
    assert "Set a positive PvE Genus mix using weights from 0 to 100." in _texts(page) and len(app.posts) == 1
    page.mix["Cogni"].setText("25")
    _button(page, "Optimize PvE build").click()
    settle(lambda: any("Searching stigmas" in t for t in _texts(page)))
    assert all(not b.isEnabled() for b in page.buttons)                          # one run at a time
    log = page.run_log                                                          # a reading updates the run in place
    page._opt_logged(["Searching stigmas", "Searching skill levels"])
    assert page.run_log is log and log.toPlainText() == "Searching stigmas\nSearching skill levels"
    assert page.run_line.text() == "Optimizing PvE build — Searching skill levels"
    path, body = app.posts[-1]
    assert path == "/api/character/optimize" and body["mode"] == "pve" and body["objective"] == "balanced"
    assert body["budgets"] == {"skill": 400, "stigma": 150, "daevanion": 417, "ariel": 12} and body["game_patch"] == "1.2.3"
    assert body["genus"] == {"enabled": True, "mix": {"Cogni": 25.0, "Fera": 25.0, "Natura": 25.0, "Varian": 25.0, "Special": 0.0}}
    assert body["survival"] == {"preserve_hp": True, "min_node_hp": 0, "current_hp": None, "action_windows": [], "opponents": []}
    assert body["skill_reserves"] == {"sp": {}, "stigmas": {}, "specs": {}} and body["character_id"] == "id0"
    assert json.loads(store.value("character-genus-options:eu:7:id0"))["enabled"] is True
    settle(lambda: page.opt["status"] == "done")
    QCoreApplication.processEvents()
    texts = _texts(page)
    assert "+4.0%" in texts and "The server kept its current Planner preset: already better" in texts
    assert any(box.toPlainText() == "+ Blaze 10\n- Frost 1" for box in page.findChildren(QPlainTextEdit))
    assert page.windows.view["name"] == "Example" and all(b.isEnabled() for b in page.buttons)   # the character's own name


def test_another_characters_run_and_a_failed_one(qapp, view, tmp_path):
    app = FakeApp(view)
    app.jobs["opt"] = {"reads": 400, "log": ["Searching"], "result": {}}
    page, _store = _page(app, tmp_path)
    _imported(page)
    page.optimize("pvp")
    settle(lambda: page.opt["log"])
    other = {**json.loads(json.dumps(view)), "key": "eu:8:id9", "name": "Example Two"}
    app.jobs["imp"] = {"reads": 1, "result": other}
    page.import_character(HITS[1])
    settle(lambda: page.view["key"] == "eu:8:id9")
    QCoreApplication.processEvents()
    assert c.elsewhere("Example") in _texts(page) and all(not b.isEnabled() for b in page.buttons)
    # a reading of the run answered in the turn the page is read: what is shown stays shown (not drawn again)
    QTimer.singleShot(0, lambda: page._opt_logged(["Searching", "Still searching"]))
    assert c.elsewhere("Example") in _texts(page)
    assert app.posts[1][1]["genus"] == {"enabled": True}                       # PvP sends whether, not the mix
    page.optimizing.stop()
    page.opt = None
    page._draw_opt()
    app.jobs["opt"] = {"reads": 1, "error": "The rotation search stopped"}
    page.optimizing = type(page.optimizing)(app, page)
    page.optimizing.interval_ms = 10
    page.optimizing.done.connect(page._opt_done)
    page.optimizing.failed.connect(page._opt_failed)
    page.optimize("pve")
    settle(lambda: page.opt["status"] == "error")
    assert "The rotation search stopped" in _texts(page) and all(b.isEnabled() for b in page.buttons)


def test_the_character_opened_last_at_launch(qapp, view, tmp_path):
    app = FakeApp(view, ui={"character_auto_open": True})
    page, _store = _page(app, tmp_path)
    settle(lambda: page.character is not None)
    assert app.posts[0] == ("/api/character/import", {**c.known_hit(KNOWN[0]), "cache": LONG_AGO})
    page.hide()
    page.show()                                                                 # once each time the app runs
    QCoreApplication.processEvents()
    assert len(app.posts) == 1
    fresh = FakeApp(view, ui={"character_auto_open": True, "character_auto_refresh": True})
    refreshed, _store = _page(fresh, tmp_path)
    settle(lambda: fresh.posts)
    assert fresh.posts[0] == ("/api/character/import", c.known_hit(KNOWN[0]))    # refreshed from the official site
    quiet = FakeApp(view)
    _page(quiet, tmp_path)
    QCoreApplication.processEvents()
    assert not quiet.posts


def test_the_window_draws_my_character_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("character"), CharacterPage) and not isinstance(window.page("character"), WebPage)
    assert isinstance(window.page("gear"), WebPage)                             # not moved over yet
