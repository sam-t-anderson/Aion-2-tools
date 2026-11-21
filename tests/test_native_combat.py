"""The native Combat Logs page, part 1 (0.2.450): its views and lists, and Saved Logs (a fight analyzed from a link or a
file with its progress, the logs folder, the log server shared to, the encounters analyzed), as pages/combat.js shows
them, off screen over a fake app answering as the app does (made-up logs and encounters).
"""
import gzip
import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import combat as cb  # noqa: E402
from aion2calc.gui.combat_page import CombatPage  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

ENCOUNTERS = [{"id": 3, "player": "TestSorc", "class_name": "sorcerer", "boss": "Ice Queen", "source": "abysslogs",
               "duration": 92.4, "dps": 41234.5}]


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
    """The app as Combat Logs asks it; an analysis runs for ``reads`` readings."""

    def __init__(self, reads=2, open_refused=False):
        self.reads, self.open_refused = reads, open_refused
        self.calls, self.posts = [], []
        self.encounters = json.loads(json.dumps(ENCOUNTERS))

    def get(self, path, timeout=None):
        self.calls.append(path)
        if path == "/api/logs":
            return {"folder": "/data/logs", "files": 12}
        if path == "/api/logserver":
            return {"url": "https://logs.example", "has_key": True, "visibility": "legion"}
        if path == "/api/encounters":
            return json.loads(json.dumps(self.encounters))
        if path == "/api/jobs/imp":
            self.reads -= 1
            if self.reads > 0:
                return {"status": "running", "log": ["fetching the log", "reading 812 hits"]}
            self.encounters.append({"id": 4, "player": "Party", "class_name": "cleric", "boss": "Ice Queen", "source": "file",
                                    "duration": 30, "dps": 900})
            return {"status": "done", "result": {"id": 4}}
        raise AssertionError(path)

    def post(self, path, body, timeout=None):
        self.posts.append((path, json.loads(json.dumps(body))))
        if path == "/api/logs/open":
            if self.open_refused:
                raise ValueError("No file manager on this computer")
            return {}
        if path == "/api/logserver":
            return {"url": body["url"], "has_key": True, "visibility": body["visibility"]}
        if path == "/api/encounters/import":
            return {"job": "imp"}
        raise AssertionError(path)


def _page(app, **kwargs):
    page = CombatPage(app, **kwargs)
    page.job.interval_ms = 10
    page.resize(1200, 1400)
    page.show()
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    def shown():
        return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)
    settle(lambda: shown() is not None)
    return shown()


def test_the_combat_words(tmp_path):
    assert cb.folder_line({"folder": "/data/logs", "files": 3}) == ("/data/logs", "(3 files)")
    assert cb.server_row({"url": "https://logs.example", "has_key": True, "visibility": "legion"}) == {
        "url": "https://logs.example", "key_hint": "key saved", "visibility": "legion"}
    assert cb.server_row({}) == {"url": "", "key_hint": "upload key", "visibility": "public"}
    assert cb.server_row({"visibility": "odd"})["visibility"] == "public"
    assert cb.server_body("https://x", "", "private") == {"url": "https://x", "key": None, "visibility": "private"}
    assert cb.server_body("https://x", "k1", "public")["key"] == "k1"                        # a key typed is sent
    row = cb.encounter_rows(ENCOUNTERS)[0]
    assert row == {"id": 3, "player": "TestSorc", "class": "Sorcerer", "boss": "Ice Queen", "source": "abysslogs",
                   "duration": "92s", "dps": "41,235"}
    assert cb.encounter_rows([{"id": 1}, None])[0]["duration"] == "0s" and cb.encounter_rows("nope") == []
    assert cb.analysis_page(4) == "combat-log/analysis/4" and cb.list_page("owned") == "combat/owned"
    assert cb.import_body("https://abysslogs.com/e/1", "") == {"ref": "https://abysslogs.com/e/1", "player": ""}
    plain, packed = tmp_path / "fight.csv", tmp_path / "segment.json.gz"
    plain.write_text("t,skill,damage\n0,Flame Arrow,100\n", encoding="utf-8")
    packed.write_bytes(gzip.compress(b'{"segment": 1}'))
    assert cb.read_log_file(str(plain)).startswith("t,skill") and cb.read_log_file(str(packed)) == '{"segment": 1}'
    assert cb.file_body("x", "a.csv", "P") == {"text": "x", "name": "a.csv", "player": "P"}
    assert cb.last_line(["a", "b"]) == "b" and cb.last_line([]) == "" and cb.last_line(None) == ""


def test_the_views_and_lists(qapp):
    opened = []
    page = _page(FakeApp(), open_web=opened.append)
    chosen = {b.text(): b.objectName() for b in page.findChildren(QPushButton) if b.property("chosen")}
    assert chosen == {"Browse logs": "small", "Community Combat Logs": "primary"}  # the view underlined, the list gold
    assert cb.ON_THE_WEB_LIST in _texts(page)                       # the community's logs: on the web page for now
    _button(page, "Open it on the web page").click()
    assert opened == ["combat/community"]
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Boss progression").click()
    assert cb.ON_THE_WEB_VIEW in _texts(page)
    _button(page, "Open it on the web page").click()
    assert opened[-1] == "combat"
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Browse logs").click()
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "My Uploads").click()
    _button(page, "Open it on the web page").click()
    assert opened[-1] == "combat/owned"


def test_saved_logs(qapp, tmp_path):
    opened, links = [], []
    packed = tmp_path / "segment.json.gz"
    packed.write_bytes(gzip.compress(b'{"segment": 1}'))
    app = FakeApp()
    page = _page(app, open_web=opened.append, choose_file=lambda: str(packed), open_link=links.append)
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    settle(lambda: "Every analyzed log is saved as a file in" in _texts(page) and "Ice Queen" in _texts(page))
    texts = _texts(page)
    assert "(12 files)" in texts and "<code>/data/logs</code>" in texts and "41,235" in texts and "92s" in texts
    assert "Sorcerer" in texts and "Recorded encounters by type" in texts and "Upload recordings" in texts
    assert page.server_url.text() == "https://logs.example" and page.server_key.placeholderText() == "key saved"
    assert page.server_seen.currentData() == "legion"
    note = next(label for label in page.findChildren(QLabel) if "AbyssLogs meter" in label.text())
    note.linkActivated.emit(cb.ABYSSLOGS)
    assert links == [cb.ABYSSLOGS]
    _button(page, "Open").click()
    assert opened == ["combat-log/analysis/3"]
    _button(page, "Open folder").click()
    settle(lambda: ("/api/logs/open", {}) in app.posts)
    page.server_seen.setCurrentIndex(page.server_seen.findData("private"))
    _button(page, "Save").click()
    settle(lambda: page.toast.text() == "Saved")
    assert ("/api/logserver", {"url": "https://logs.example", "key": None, "visibility": "private"}) in app.posts
    # a fight analyzed from its link: its progress, then its analysis opened and the list read again
    page.ref.setText("https://abysslogs.com/e/123")
    page.player.setText("TestSorc")
    page.analyze.click()
    settle(lambda: page.message.text() == "reading 812 hits")
    settle(lambda: opened[-1] == "combat-log/analysis/4")
    settle(lambda: "Party" in _texts(page))
    assert ("/api/encounters/import", {"ref": "https://abysslogs.com/e/123", "player": "TestSorc"}) in app.posts
    # and from a file, an AbyssLogs segment unpacked
    app.reads = 1
    _button(page, "Choose a file…").click()
    settle(lambda: any(path == "/api/encounters/import" and body.get("name") == "segment.json.gz" for path, body in app.posts))
    sent = next(body for path, body in app.posts if body.get("name") == "segment.json.gz")
    assert sent == {"text": '{"segment": 1}', "name": "segment.json.gz", "player": "TestSorc"}
    # a folder the computer cannot open: why, by the Analyze button
    refused = _page(FakeApp(open_refused=True))
    next(b for b in refused.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    _button(refused, "Open folder").click()
    settle(lambda: refused.message.text() == "No file manager on this computer")


def test_the_window_draws_combat_logs_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("combat"), CombatPage) and not isinstance(window.page("combat"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                      # not moved over yet
