"""The native Build Planner page (0.2.439): the welcome card, the builds and Optimize, and the chosen build's result
windows as pages/planner.js shows them, off screen, over a fake app answering as the app does (its presets,
classes, builds, the log server's reported budgets and its jobs), with the app's own result view of the bundled
sorcerer build.
"""
import json
import os
import pathlib
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import planner as p  # noqa: E402
from aion2calc.gui import result_windows as w  # noqa: E402
from aion2calc.gui.api import Job  # noqa: E402
from aion2calc.gui.planner_page import PlannerPage  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRESETS = [
    {"path": "results/sorcerer_l45/build.json", "class": "sorcerer", "mode": "pve", "canonical": False,
     "preset_label": "sorcerer_45_global_PvE", "scenario": "boss", "dps": {"boss": 49658.2}},
    {"path": "community/gladiator_pvp.json", "class": "gladiator", "mode": "pvp", "canonical": True,
     "preset_label": "Gladiator PvP", "scoring_policy": {"mode": "pvp"}, "score": 30123.6},
]
OBSERVATIONS = [
    {"class_name": "sorcerer", "skill": 383, "stigma": 188, "daevanion": 417, "ariel": 12},
    {"class_name": "sorcerer", "skill": 380.0, "stigma": 190, "daevanion": 400},
    {"class_name": "sorcerer", "skill": 390, "stigma": 10001, "daevanion": 400},           # out of range: left out
    {"class_name": "gladiator", "skill": 999, "stigma": 999, "daevanion": 999},
]


@pytest.fixture(scope="module")
def view():
    from aion2calc.app.views import build_view
    return build_view(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))


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
    """The app as the Build Planner asks it: its builds, classes and jobs (each read ``reads`` times before it ends)."""

    def __init__(self, view, weight_job=None, fail_build=False):
        self.view, self.weight_job, self.fail_build = view, weight_job, fail_build
        self.calls, self.posts, self.jobs = [], [], {}

    def get(self, path):
        self.calls.append(path)
        if path == "/api/planner/presets":
            return json.loads(json.dumps(PRESETS))
        if path == "/api/classes":
            return ["gladiator", "sorcerer"]
        if path.startswith("/api/build?path="):
            if self.fail_build:
                raise OSError("The build could not be read")
            chosen = urllib.parse.unquote(path.split("=", 1)[1])
            built = json.loads(json.dumps(self.view))
            if chosen.startswith("community/"):
                built.update({"class": "gladiator", "scenario": "pvp_boss"})
            if self.weight_job:
                built.update(weight_job=self.weight_job, weights=[])
            return built
        if path.startswith("/api/community?path="):
            asked = urllib.parse.unquote(path.split("=", 1)[1])
            assert asked.startswith("/api/v1/progression?class=")
            return {"observations": OBSERVATIONS}
        if path.startswith("/api/jobs/"):
            job = self.jobs[path.rsplit("/", 1)[1]]
            job["reads"] -= 1
            if job["reads"] > 0:
                return {"status": "running", "log": job["log"]}
            return {"status": "error", "error": job["error"]} if job.get("error") else {"status": "done", "result": job["result"]}
        raise AssertionError(path)

    def get_bytes(self, path):
        raise OSError("no pictures here")

    def post(self, path, body):
        self.posts.append((path, body))
        name = {"/api/optimize": "opt", "/api/planner/presets/refresh": "ref"}[path]
        return {"job": name}


def _page(app, tmp_path, **kwargs):
    store = QSettings(str(tmp_path / "native.ini"), QSettings.IniFormat)
    page = PlannerPage(app, store=store, **kwargs)
    for job in (page.optimizing, page.refreshing):
        job.interval_ms = 10
    page.weights.setInterval(10)
    page.resize(1300, 1800)
    page.show()
    settle(lambda: page.windows.isVisible() or page.note.isVisible() and page.note.text() not in ("", p.LOADING))
    settle(lambda: page.budget_note.text() not in ("", p.LOADING_BUDGETS))
    QCoreApplication.processEvents()
    return page, store


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    QCoreApplication.processEvents()
    return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)


def test_the_planner_words():
    assert p.preset_line(PRESETS[0]) == "Example · sorcerer_45_global_PvE · 49,658 boss DPS"
    assert p.preset_line(PRESETS[1]) == "Community · Gladiator PvP · 30,124 weighted DPS"
    assert p.preset_line({"class": "templar"}) == "Example · Templar · — DPS"
    state = {"path": "community/gladiator_pvp.json"}
    assert p.chosen_path(PRESETS, state) == "community/gladiator_pvp.json"
    assert p.chosen_path(PRESETS, {"path": "gone", "choice": {"class": "gladiator", "mode": "pvp"}}) == "community/gladiator_pvp.json"
    assert p.chosen_path(PRESETS, {}) == PRESETS[0]["path"] and p.chosen_path([], {}) == ""
    assert [p.mode_of({"scenario": s}) for s in ("pvp_world", "pvp_boss", "boss", None)] == ["world", "pvp", "pve", "pve"]
    assert p.progression_path("sorcerer") == "/api/v1/progression?class=sorcerer"
    assert p.progression_path("sorcerer", {"region": "eu", "game_patch": "1.2"}) == "/api/v1/progression?class=sorcerer&region=eu&game_patch=1.2"
    found = p.budgets({"observations": OBSERVATIONS}, "sorcerer")
    assert found["points"] == {"skill": 383, "stigma": 190, "daevanion": 417, "ariel": 12} and len(found["rows"]) == 2
    assert found["note"].startswith("Highest server-reported totals from 2 class/context observations")
    assert found["note"].endswith("Region/build is unspecified; available contexts are pooled.")
    assert p.budgets({"observations": OBSERVATIONS}, "sorcerer", {"region": "eu", "game_patch": "1"})["note"].endswith("Matched region/build only.")
    none = p.budgets({}, "cleric")
    assert none["points"] == {"skill": None, "stigma": None, "daevanion": None, "ariel": None}
    assert none["note"] == "No server-reported totals for this class/context. Enter available points explicitly."
    with pytest.raises(ValueError):
        p.budgets(None, "cleric")
    assert [p.whole(x) for x in ("", " 12 ", "12.0", "1e3", "x", "1.5")] == [None, 12, 12, 1000, None, None]
    fields = {"skill": "383", "stigma": "188", "daevanion": "417", "ariel": ""}
    assert p.optimize_problem(fields) == ""
    assert p.optimize_problem({**fields, "stigma": ""}) == p.optimize_problem({**fields, "skill": "10001"}) == p.NEED_BUDGETS
    assert p.optimize_problem({**fields, "ariel": "-1"}) == p.optimize_problem({**fields, "ariel": "2.5"}) == p.BAD_ARIEL
    assert p.optimize_body("sorcerer", "pve", fields) == {"class": "sorcerer", "mode": "pve", "skill_points": 383,
                                                          "stigma_points": 188, "daevanion": 417}
    assert p.optimize_body("sorcerer", "world", {**fields, "ariel": "12"})["ariel"] == 12
    assert (p.last(["a", "b"], "x"), p.last([], "x"), p.last(["a", ""], "x")) == ("b", "x", "x")
    assert p.done_message({"preset_submission": {"reason": "Shared"}}) == "Shared" and p.done_message({}) == "done"
    assert p.weight_status({"status": "error", "error": "boom"}) == "Stat priority failed: boom"
    assert p.weight_status({"status": "running", "log": ["Step 2"]}) == "Step 2"
    assert p.weight_status({"status": "running"}) == "Calculating stat priority…"


def test_the_planner_shows_a_build(qapp, view, tmp_path):
    app, shown, opened, links = FakeApp(view, weight_job="w1"), [], [], []
    app.jobs["w1"] = {"reads": 25, "log": ["Weighing Attack"], "result": [{"label": "Attack +30", "pct": 2.5}] * 14}
    store = QSettings(str(tmp_path / "native.ini"), QSettings.IniFormat)
    page = PlannerPage(app, show_page=shown.append, open_web=opened.append, open_link=links.append, store=store)
    page.weights.setInterval(10)
    assert app.calls == []                                                      # nothing asked before it is shown
    page.resize(1300, 1800)
    page.show()
    settle(lambda: page.windows.isVisible())
    settle(lambda: page.budget_note.text() not in ("", p.LOADING_BUDGETS))
    assert [page.presets.itemText(i) for i in range(page.presets.count())] == [p.preset_line(r) for r in PRESETS]
    assert page.presets.currentData() == PRESETS[0]["path"] and page.state["choice"] == {"class": "sorcerer", "mode": "pve"}
    assert page.cls.currentText() == "sorcerer" and page.mode.currentData() == "pve"
    assert [page.fields[k].text() for k in ("skill", "stigma", "daevanion", "ariel")] == ["383", "190", "417", "12"]
    assert page.budget_note.text().startswith("Highest server-reported totals from 2")
    assert "/api/build?path=results%2Fsorcerer_l45%2Fbuild.json" in app.calls
    # its stat priority, while its job runs and when it ends
    status = page.windows.findChild(QLabel, "weightStatus")
    settle(lambda: status.text() == "Weighing Attack")
    settle(lambda: page.windows.findChild(QLabel, "weightStatus") is None)
    QCoreApplication.processEvents()                                            # the windows drawn again are shown
    assert page.view["weights"][0] == {"label": "Attack +30", "pct": 2.5} and len(page.view["weights"]) == 12
    assert len([b for b in page.windows.findChildren(w.Bar) if b.isVisibleTo(page.windows)]) == 24   # 12 stats, 12 shares
    # another build: the community preset, its class and mode
    page.presets.setCurrentIndex(1)
    page.presets.activated.emit(1)
    settle(lambda: page.cls.currentText() == "gladiator")
    assert page.state["path"] == "community/gladiator_pvp.json" and page.mode.currentData() == "pvp"
    # the links: Saved results, the welcome card's steps and the Discord
    _button(page, "Saved results").click()
    for words in ("My Character", "Gear && Advice", "Live Meter"):
        _button(page, words).click()
    assert shown == ["history", "character", "gear", "meter"]
    join = next(label for label in page.findChildren(QLabel) if "Join the Discord" in label.text())
    join.linkActivated.emit(p.DISCORD)
    assert links == [p.DISCORD]
    # Hide: gone now, and the next time the page is made
    assert page.welcome is not None and p.HERO_TEXT in _texts(page)
    _button(page, "Hide").click()
    QCoreApplication.processEvents()
    assert page.welcome is None and store.value("welcome-hidden") == "1" and p.HERO_TEXT not in _texts(page)
    again = PlannerPage(None, store=store)
    assert again.welcome is None


def test_optimize_and_refresh_presets(qapp, view, tmp_path):
    app = FakeApp(view)
    optimized = {**json.loads(json.dumps(view)), "preset_submission": {"reason": "Shared with the community"}}
    app.jobs["opt"] = {"reads": 2, "log": ["Searching skills"], "result": optimized}
    app.jobs["ref"] = {"reads": 2, "log": ["Checking presets"], "result": {"checked": True}}
    page, _store = _page(app, tmp_path)
    page.fields["stigma"].clear()
    page.optimize()
    assert page.message.text() == p.NEED_BUDGETS and not app.posts
    page.fields["stigma"].setText("188")
    page.fields["ariel"].setText("x")
    page.optimize()
    assert page.message.text() == p.BAD_ARIEL
    page.fields["ariel"].setText("")
    page.mode.setCurrentIndex(page.mode.findData("world"))
    page.optimize()
    assert not page.go.isEnabled()
    settle(lambda: page.message.text() == "Shared with the community")
    assert app.posts[0] == ("/api/optimize", {"class": "sorcerer", "mode": "world", "skill_points": 383, "stigma_points": 188,
                                              "daevanion": 417})
    assert page.go.isEnabled() and page.view is not None and page.view.get("preset_submission")
    # the job's log while it runs
    app.jobs["opt"] = {"reads": 50, "log": ["Searching skills"], "result": optimized}
    page.optimize()
    settle(lambda: page.message.text() == "Searching skills")
    page.optimizing.stop()
    page.optimizing = Job(app, page)                                            # a fresh runner for the next job
    # a job that fails says why
    app.jobs["opt"] = {"reads": 1, "error": "No budget left"}
    page.optimizing.interval_ms = 10
    page.optimizing.failed.connect(page._optimize_failed)
    page.optimizing.done.connect(page._optimized)
    page.optimize()
    settle(lambda: page.message.text() == "No budget left")
    assert page.go.isEnabled()
    # Refresh presets: its job, then the builds read again
    asked = app.calls.count("/api/planner/presets")
    page.refresh_button.click()
    settle(lambda: page.message.text() == p.CHECKED)
    assert app.posts[-1] == ("/api/planner/presets/refresh", {}) and page.refresh_button.isEnabled()
    settle(lambda: app.calls.count("/api/planner/presets") > asked)


def test_a_build_that_cannot_be_read(qapp, view, tmp_path):
    page, _store = _page(FakeApp(view, fail_build=True), tmp_path)
    assert page.note.isVisible() and page.note.text() == "The build could not be read" and page.note.objectName() == "bad"
    assert not page.windows.isVisible()


def test_the_window_draws_the_planner_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("planner"), PlannerPage) and not isinstance(window.page("planner"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                             # not moved over yet
