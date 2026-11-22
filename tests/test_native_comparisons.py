"""A result's community comparison, generated in the native interface (0.2.500) as pages/results.js's
``renderCommonComparisons`` generates it under the Overview's **Contribute a community comparison**, where until now
the window only offered the web page. Over the bundled sorcerer build (``views.build_view`` of
results/sorcerer_l45/build.json) and a stand-in for the app's job, off screen.
"""
import io
import json
import os
import pathlib
import sys
import urllib.error

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from aion2calc.gui import comparisons as cp  # noqa: E402
from aion2calc.gui import results as r  # noqa: E402
from aion2calc.gui.comparisons import ComparisonPanel  # noqa: E402
from aion2calc.gui.result_windows import ResultWindows  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402
from test_native_pets import _png  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAVED = {"class": "sorcerer", "mode": "pve", "score": 123456.4, "dps": {"Boss": 120000, "Adds": 98765.5},
         "model": "stationary-v3", "reused": False,
         "submission": {"submitted": True, "accepted": True, "candidate_score": 120500}}


@pytest.fixture(scope="module")
def view():
    from aion2calc.app.views import build_view
    return build_view(json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    """Each test with the window's comparisons afresh, read every 10 ms; its windows closed and deleted after."""
    monkeypatch.setattr(cp, "_COMPARISONS", cp.CommonComparisons(interval_ms=10))
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
    """The app's comparison job: started (``POST /api/planner/presets/contribute``, refused with ``refuse``), then
    read (``/api/jobs/<id>``), each reading the next of ``readings`` (the last one again once they run out)."""

    def __init__(self, readings=(), refuse=None):
        self.readings, self.refuse = list(readings), refuse
        self.posts, self.reads = [], 0

    def post(self, path, body):
        self.posts.append((path, body))
        if self.refuse:
            raise urllib.error.HTTPError(path, 400, "Bad Request", {}, io.BytesIO(json.dumps({"error": self.refuse}).encode()))
        return {"job": "job7"}

    def get(self, path):
        assert path == "/api/jobs/job7"
        self.reads += 1
        return self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]

    def get_bytes(self, path):
        return _png((200, 120, 40), 8)


def _panel(app, view):
    """The Overview's comparison, its fold opened."""
    windows = ResultWindows(app)
    windows.resize(1100, 1400)
    windows.set_view(view)
    windows.show()
    QCoreApplication.processEvents()
    next(b for b in windows.findChildren(QToolButton) if b.text() == "Contribute a community comparison").click()
    QCoreApplication.processEvents()
    panel = next(p for p in windows.findChildren(ComparisonPanel) if p.isVisibleTo(windows))
    return windows, panel


def _shown(panel):
    return (panel.button.text(), panel.button.isEnabled(), panel.status.text(), panel.status.objectName(),
            panel.figures.text() if panel.figures.isVisibleTo(panel) else None)


def test_the_comparison_words():
    assert r.comparison_key({"class": "sorcerer", "scenario": "pvp-duel"}) == ("sorcerer", "pvp")
    assert r.comparison_key({"class": "cleric", "scenario": "boss"}) == ("cleric", "pve") and r.comparison_key({}) == ("", "pve")
    assert r.comparison_button({}) == (r.COMPARISON_START, True)
    assert r.comparison_button({"status": "running"}) == (r.COMPARISON_RUNNING, False)
    assert r.comparison_button({"status": "done", "result": SAVED}) == (r.COMPARISON_AGAIN, True)
    assert r.comparison_button({"status": "error", "message": "x"}) == (r.COMPARISON_START, True)
    assert r.comparison_status({}) == ("", False) and r.comparison_status({"message": "Seeding"}) == ("Seeding", False)
    assert r.comparison_status({"status": "done", "message": "Seeding", "result": SAVED}) == (
        "Comparison saved · 123,456 weighted modeled DPS (stationary-v3). Community preset updated.", True)
    kept = {**SAVED, "reused": True, "submission": {"accepted": False}}
    assert r.comparison_status({"result": kept}) == (
        "Saved comparison reused · 123,456 weighted modeled DPS (stationary-v3). Current community preset retained.", False)
    said = {**SAVED, "submission": {"submitted": False, "reason": "The configured server does not support it"}}
    assert r.comparison_status({"result": said})[0].endswith("(stationary-v3). The configured server does not support it")
    assert r.comparison_lines(SAVED) == ["Boss: 120,000 modeled DPS · Adds: 98,766 modeled DPS",
                                         "Server evaluation: 120,500 weighted modeled DPS (server policy)."]
    assert r.comparison_lines({"dps": {}, "submission": {}}) == [""] and r.comparison_lines(None) == [""]
    assert r.comparison_reading(["Seeding", "Refining 2/5"]) == "Refining 2/5"
    assert r.comparison_reading([]) == r.comparison_reading(None) == r.comparison_reading([""]) == r.COMPARISON_WAITING


def test_a_comparison_generated_and_resubmitted(qapp, view):
    app = FakeApp([{"status": "running", "log": []}, {"status": "running", "log": ["Seeding 1/4"]},
                   {"status": "running", "log": ["Seeding 1/4", "Refining 2/5"]},
                   {"status": "done", "log": ["Seeding 1/4", "Refining 2/5", "Community preset updated"], "result": SAVED}])
    windows, panel = _panel(app, view)
    assert (panel.cls, panel.mode) == ("sorcerer", "pve")
    assert _shown(panel) == (r.COMPARISON_START, True, "", "comparisonStatus", None)
    assert not panel.status.isVisibleTo(panel)                             # the page's empty line takes no room
    panel.button.click()
    assert _shown(panel) == (r.COMPARISON_RUNNING, False, r.COMPARISON_STARTING, "comparisonStatus", None)
    assert panel.status.isVisibleTo(panel)
    settle(lambda: app.reads >= 1)
    settle(lambda: panel.status.text() in (r.COMPARISON_WAITING, "Seeding 1/4", "Refining 2/5") or app.reads > 1)
    panel.button.click()                                                    # pressed again while it runs: nothing
    settle(lambda: panel.button.isEnabled())
    assert app.posts == [(r.COMPARISON_PATH, {"class": "sorcerer", "mode": "pve"})]
    assert _shown(panel) == (r.COMPARISON_AGAIN, True,
                             "Comparison saved · 123,456 weighted modeled DPS (stationary-v3). Community preset updated.",
                             "comparisonGood", "Boss: 120,000 modeled DPS · Adds: 98,766 modeled DPS\n"
                                               "Server evaluation: 120,500 weighted modeled DPS (server policy).")
    # the same class and mode in another of the window's results shows the same comparison
    other, again = _panel(app, view)
    assert _shown(again) == _shown(panel)
    # resubmitted: its result let go while it runs again, as the web page's state is replaced
    app.readings = [{"status": "running", "log": ["Reusing the saved comparison"]},
                    {"status": "done", "log": [], "result": {**SAVED, "reused": True}}]
    again.button.click()
    assert _shown(panel)[:2] == (r.COMPARISON_RUNNING, False) and _shown(panel)[4] is None
    settle(lambda: panel.button.isEnabled())
    assert panel.status.text().startswith("Saved comparison reused · 123,456") and len(app.posts) == 2


def test_it_goes_on_while_its_window_is_gone(qapp, view):
    app = FakeApp([{"status": "running", "log": ["Seeding 1/4"]}] * 3 + [{"status": "done", "log": [], "result": SAVED}])
    windows, panel = _panel(app, view)
    panel.button.click()
    windows.close()
    windows.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    settle(lambda: cp.comparisons().state("sorcerer:pve").get("status") == "done")
    _windows, shown = _panel(app, view)                                     # the Overview opened again
    assert _shown(shown)[0] == r.COMPARISON_AGAIN and shown.figures.isVisibleTo(shown)


def test_a_comparison_refused_or_failed(qapp, view):
    _windows, alone = _panel(None, view)                                    # without the app, the button asks nothing
    alone.button.click()
    assert _shown(alone)[0] == r.COMPARISON_START and cp.comparisons().state("sorcerer:pve") == {}
    windows, panel = _panel(FakeApp(refuse="Unknown class"), view)
    panel.button.click()
    settle(lambda: panel.button.isEnabled())
    assert _shown(panel) == (r.COMPARISON_START, True, "Unknown class", "comparisonStatus", None)
    failing = FakeApp([{"status": "running", "log": ["Seeding 1/4"]},
                       {"status": "error", "log": ["Seeding 1/4"], "error": "The optimizer stopped"}])
    _windows, panel = _panel(failing, {"class": "cleric", "scenario": "pvp"})
    panel.button.click()
    settle(lambda: panel.button.isEnabled())
    assert _shown(panel) == (r.COMPARISON_START, True, "The optimizer stopped", "comparisonStatus", None)
    assert failing.posts == [(r.COMPARISON_PATH, {"class": "cleric", "mode": "pvp"})]
