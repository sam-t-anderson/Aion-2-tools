"""The native Combat Logs page, part 1 (0.2.450): its views and lists, and Saved Logs (a fight analyzed from a link or a
file with its progress, the logs folder, the log server shared to, the encounters analyzed), as pages/combat.js shows
them; since 0.2.451 Saved Logs' recorded encounters by type (saved-logs.js) and its upload queue (archive-upload.js).
Off screen over a fake app answering as the app does (made-up logs, recordings and encounters).
"""
import gzip
import hashlib
import json
import os
import sys
import urllib.parse
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton  # noqa: E402

from aion2calc.gui import combat as cb  # noqa: E402
from aion2calc.gui.combat_page import CombatPage  # noqa: E402
from aion2calc.gui.combat_saved import RecordedEncounters, Section, UploadQueue  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

ENCOUNTERS = [{"id": 3, "player": "TestSorc", "class_name": "sorcerer", "boss": "Ice Queen", "source": "abysslogs",
               "duration": 92.4, "dps": 41234.5}]
T0 = datetime(2026, 11, 1, 12, 0).timestamp()       # noon on 1 November, in this computer's clock
DAY = 86400
#: The recordings this computer saved, newest first as the app lists them.
RECORDINGS = [
    {"file": "session-3.a2log.json", "title": "Raid night", "updated": T0 + 3 * DAY, "segments": 2, "unfinished": False,
     "archive": {"id": "rec-1", "part": 2, "closed": True},
     "contexts": [{"segment": 0, "boss": "Ice Queen", "boss_code": 2001, "category": "raid", "role": "final",
                   "difficulty": "hard", "duration": 125.4, "encounter_type": "sanctuary"},
                  {"segment": 1, "boss": "Frost Hound", "boss_code": 2002, "category": "raid", "role": "mini",
                   "difficulty": "hard", "duration": 40, "encounter_type": "sanctuary"}]},
    {"file": "session-2.a2log.json", "title": "", "updated": T0 + DAY, "segments": 1, "unfinished": True, "archive": None,
     "contexts": [{"segment": 0, "boss": None, "category": "pvp", "role": None, "difficulty": "unknown", "duration": 61,
                   "encounter_type": "pvp_arena"}]},
    {"file": "session-1.a2log.json", "title": "Field run", "updated": T0, "segments": 2, "unfinished": False, "archive": None,
     "contexts": [{"segment": 0, "boss": None, "category": "other", "duration": 5, "encounter_type": "unknown"},
                  {"segment": 1, "boss": "Ash Wyrm", "boss_code": 3001, "category": "field_boss", "role": "field",
                   "difficulty": "unknown", "duration": 302, "encounter_type": "pve_open_world"}]},
]
#: An older recording, on the next page.
OLDER = [{"file": "session-0.a2log.json", "title": "Old raid", "updated": T0 - 30 * DAY, "segments": 1, "unfinished": False,
          "archive": {"id": "rec-1", "part": 1, "closed": True},
          "contexts": [{"segment": 0, "boss": "Ice Queen", "boss_code": 2001, "category": "raid", "role": "final",
                        "difficulty": "normal", "duration": 200, "encounter_type": "sanctuary"}]}]
PORTRAIT = "https://img.example/npc/2001.png"


def _red_png() -> bytes:
    image = QImage(8, 8, QImage.Format_ARGB32)
    image.fill(QColor("#ff0000"))
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


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
    """The app as Combat Logs asks it; an analysis runs for ``reads`` readings. The recordings come a page at a time
    (``RECORDINGS``, then ``OLDER``); ``refusals`` holds what the log server says to a file's next upload, ``prints``
    a file's fingerprint when it is not its name's."""

    def __init__(self, reads=2, open_refused=False, older=True, recordings_refused=None):
        self.reads, self.open_refused = reads, open_refused
        self.calls, self.posts = [], []
        self.encounters = json.loads(json.dumps(ENCOUNTERS))
        self.recordings = json.loads(json.dumps(RECORDINGS))
        self.older = json.loads(json.dumps(OLDER)) if older else []
        self.recordings_refused = recordings_refused
        self.server = {"url": "https://logs.example", "has_key": True, "visibility": "legion"}
        self.refusals: dict[str, str] = {}
        self.prints: dict[str, str] = {}
        self.queue_kept = None
        self.uploads = 0

    def fingerprint(self, file):
        return self.prints.get(file) or hashlib.sha256(file.encode()).hexdigest()

    def sessions(self, query):
        if self.recordings_refused:
            raise ValueError(self.recordings_refused)
        offset, limit, archive = int(query["offset"][0]), int(query["limit"][0]), query.get("archive", [""])[0]
        rows = [*self.recordings, *self.older]
        if archive:
            rows = sorted((r for r in rows if (r.get("archive") or {}).get("id") == archive), key=lambda r: r["archive"]["part"])
            return {"rows": rows[offset:offset + limit], "has_more": offset + limit < len(rows), "archive": archive}
        page = self.recordings if offset == 0 else self.older if offset == limit else []
        return {"rows": json.loads(json.dumps(page)), "has_more": offset == 0 and bool(self.older)}

    def get_bytes(self, path, timeout=None):
        self.calls.append(path)
        if path == "/static/game-assets/npc/2001.png":
            return _red_png()
        raise OSError("no such picture")

    def get(self, path, timeout=None):
        self.calls.append(path)
        if path == "/api/logs":
            return {"folder": "/data/logs", "files": 12}
        if path == "/api/logserver":
            return dict(self.server)
        if path == "/api/encounters":
            return json.loads(json.dumps(self.encounters))
        if path == "/static/game-assets.json":
            return {"assets": {PORTRAIT: "game-assets/npc/2001.png"}, "npc_portraits": {"2001": PORTRAIT}}
        if path == "/api/upload-queue":
            return json.loads(json.dumps(self.queue_kept))
        if path.startswith("/api/sessions?"):
            query = urllib.parse.parse_qs(path.split("?", 1)[1], keep_blank_values=True)
            if "fingerprint" in query:
                return {"fingerprint": self.fingerprint(query["fingerprint"][0])}
            return self.sessions(query)
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
        if path == "/api/upload-queue":
            self.queue_kept = json.loads(json.dumps(body))
            return {"ok": True}
        if path == "/api/sessions/share":
            if body["file"] in self.refusals:
                raise ValueError(self.refusals.pop(body["file"]))
            self.uploads += 1
            report = f"rep{self.uploads:04d}"
            secret = "?key=s3cret" if body["visibility"] == "private" else ""
            return {"id": report, "url": f"https://logs.example/log/{report}{secret}", "visibility": body["visibility"]}
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
    _button(page.encounters_box, "Open").click()
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


def _store(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)


def test_the_recorded_encounters_words():
    found = cb.recorded({"rows": RECORDINGS, "has_more": True})
    assert [(e["boss"], e["category"], e["segment"]) for e in found] == [
        ("Ice Queen", "raid", 0), ("Frost Hound", "raid", 1), (None, "pvp", 0), ("Ash Wyrm", "field_boss", 1)]
    assert found[0]["date"] == T0 + 3 * DAY and found[0]["file"] == "session-3.a2log.json"   # an empty fight is left out
    assert cb.recorded({"rows": [{"contexts": [{"boss": "X"}], "updated": 1}]})[0]["category"] == "other"
    assert cb.recorded(None) == [] and cb.recorded({"rows": [None, {"contexts": None}]}) == []
    f = dict(cb.NO_FILTERS)
    assert [e["boss"] for e in found if cb.shown(e, f, False)] == ["Ice Queen", None, "Ash Wyrm"]   # a mini-boss hidden
    assert [e["boss"] for e in found if cb.shown(e, f, True)] == ["Ice Queen", "Frost Hound", None, "Ash Wyrm"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "boss": "Frost Hound"}, False)] == ["Frost Hound"]  # chosen
    assert [e["boss"] for e in found if cb.shown(e, {**f, "role": "mini"}, False)] == ["Frost Hound"]
    assert [e["category"] for e in found if cb.shown(e, {**f, "role": "pvp"}, False)] == ["pvp"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "difficulty": "hard"}, True)] == ["Ice Queen", "Frost Hound"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "category": "field_boss"}, False)] == ["Ash Wyrm"]
    # the days saved, in the computer's clock: From's midnight up to the midnight after To
    assert [e["boss"] for e in found if cb.shown(e, {**f, "from": "2026-11-02"}, False)] == ["Ice Queen", None]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "to": "2026-11-02"}, False)] == [None, "Ash Wyrm"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "from": "2026-11-04", "to": "2026-11-04"}, False)] == ["Ice Queen"]
    assert cb.recorded_choices(found, False) == {
        "boss": [("Ash Wyrm", "Ash Wyrm"), ("Ice Queen", "Ice Queen")],
        "category": [("pvp", "PvP encounters"), ("field_boss", "Field bosses"), ("raid", "Raids")],      # in their order
        "role": [("final", "Final boss"), ("mini", "Mini-boss"), ("pvp", "PvP"), ("field", "Field boss")],
        "difficulty": [("hard", "Hard")]}
    assert [b for b, _ in cb.recorded_choices(found, True)["boss"]] == ["Ash Wyrm", "Frost Hound", "Ice Queen"]
    assert sorted(["beta", "Alpha", "alpha", "Émile", "Echo"], key=cb.locale_key) == ["alpha", "Alpha", "beta", "Echo", "Émile"]
    sections = cb.recorded_sections(found + cb.recorded({"rows": OLDER}), f, False)
    assert [(s["title"], s["count"]) for s in sections] == [("PvP encounters", 1), ("Field bosses", 1), ("Raids", 2)]
    raid = sections[2]["rows"]
    assert [(r["boss"], r["role"], r["difficulty"], r["time"]) for r in raid] == [
        ("Ice Queen", "Final boss", "Hard", "2:05"), ("Ice Queen", "Final boss", "Normal", "3:20")]   # newest first
    assert sections[0]["rows"][0] == {"boss": "—", "code": None, "role": "Arena", "difficulty": "—", "time": "1:01",
                                      "date": cb.saved_at(T0 + DAY), "file": "session-2.a2log.json", "segment": 0}
    assert sections[1]["rows"][0]["difficulty"] == "—" and sections[1]["rows"][0]["role"] == "Field boss"
    assert cb.saved_at(T0) == "2026-11-01 12:00:00" and cb.saved_at(None) == "—"
    many = [dict(found[0], date=T0 + i) for i in range(cb.PER_SECTION + 3)]
    capped = cb.recorded_sections(many, f, False)[0]
    assert len(capped["rows"]) == cb.PER_SECTION and capped["more"] == 3 and capped["count"] == cb.PER_SECTION + 3
    assert cb.secs(None) == "—" and cb.secs(59.5) == "1:00" and cb.secs(3725) == "62:05"
    assert cb.role_label({"category": "pvp", "enc_type": "nope"}) == "PvP" and cb.role_label({"role": "odd"}) == ""
    assert cb.no_match(True) == "No recorded encounters match these filters among the recordings loaded so far."
    assert cb.no_match(False) == "No recorded encounters match these filters."
    assert cb.local_page("session 1.json", 2) == "combat-log/local/session%201.json?segment=2"
    assert cb.local_page("a(b)'!*~.json") == "combat-log/local/a(b)'!*~.json"       # as encodeURIComponent leaves them
    assert cb.sessions_path(25, 25, "rec/1") == "/api/sessions?paged=1&offset=25&limit=25&archive=rec%2F1"


def test_the_upload_queue_words(tmp_path):
    fp, fp2, rid = "a" * 64, "b" * 64, "c" * 32
    kept = {"format": "a2log-upload-checkpoint", "version": 1, "server": "https://logs.example/", "visibility": "private",
            "parts": [{"file": "s1.json", "title": "Raid", "fingerprint": fp, "request_id": rid, "status": "uploaded",
                       "id": "Abc123"},
                      {"file": "s2.json", "fingerprint": fp2, "status": "uploading"}]}
    clean = cb.clean_checkpoint(kept)
    assert clean["server"] == "https://logs.example" and clean["visibility"] == "private"
    assert clean["parts"][1] == {"file": "s2.json", "name": "s2.json", "title": "s2.json", "fingerprint": fp2,
                                 "request_id": None, "status": "uploading", "id": None}

    def refusal(change=None, part=None):
        value = json.loads(json.dumps(kept))
        value.update(change or {})
        value["parts"][0].update(part or {})
        with pytest.raises(ValueError) as problem:
            cb.clean_checkpoint(value)
        return str(problem.value)
    limit = "Choose an upload recovery checkpoint with at most 100 files."
    assert refusal({"format": "other"}) == limit and refusal({"version": True}) == limit and refusal({"version": 2}) == limit
    assert refusal({"parts": [{"file": f"f{i}"} for i in range(101)]}) == limit
    assert refusal({"parts": [{"file": "x", "title": "t" * 300000}]}) == limit
    for server in ("ftp://logs.example", "https://user:pw@logs.example", "https://logs.example/?key=1",
                   "https://logs.example/#k", "logs.example", "https://"):
        assert refusal({"server": server}) == "Invalid checkpoint server.", server
    assert refusal({"visibility": "legion"}) == "Invalid checkpoint visibility."
    assert refusal({"parts": [{"file": "a"}, {"file": "a"}]}) == "Invalid or duplicate checkpoint filename."
    assert refusal(part={"file": ""}) == refusal(part={"file": 5}) == "Invalid or duplicate checkpoint filename."
    assert refusal(part={"fingerprint": "XYZ"}) == "Invalid file fingerprint."
    assert refusal(part={"request_id": "short"}) == "Invalid upload request ID."
    assert refusal(part={"status": "done"}) == "Invalid checkpoint status."
    assert refusal(part={"id": "a b"}) == "Invalid uploaded report ID."
    assert refusal(part={"id": None}) == "Successful records require a server, ID and fingerprint."
    assert refusal({"server": ""}) == "Successful records require a server, ID and fingerprint."
    # restored: an interrupted upload is uncertain; nothing kept is no queue
    batch, chosen, selected, results = cb.restored(kept)
    assert batch == {"url": "https://logs.example", "visibility": "private"} and chosen == "private"
    assert list(selected) == ["s1.json", "s2.json"] and selected["s1.json"]["request_id"] == rid
    assert results["s1.json"] == {"status": "uploaded", "id": "Abc123", "fingerprint": fp}
    assert results["s2.json"]["status"] == "unknown"
    for nothing in (None, {}, {"parts": []}, []):
        with pytest.raises(ValueError, match="No saved upload queue is available."):
            cb.restored(nothing)
    # the checkpoint kept: never a key, a link or a credential
    rows = {"s3.json": {"file": "s3.json", "title": "", "fingerprint": fp, "request_id": rid}}
    point = cb.checkpoint(rows, {"s3.json": {"status": "failed", "error": "HTTP 400"}}, None, "unlisted")
    assert point == {"format": "a2log-upload-checkpoint", "version": 1, "server": "", "visibility": "unlisted",
                     "parts": [{"file": "s3.json", "name": "s3.json", "title": "s3.json", "fingerprint": fp,
                                "request_id": rid, "status": "failed", "id": None}]}
    # the results manifest: a private report's link and a link with a secret left out
    queued = {"a": {"file": "a", "archive": {"id": "rec-1", "part": 2, "closed": True}}, "b": {"file": "b"},
              "c": {"file": "c"}, "d": {"file": "d"}}
    results = {"a": {"status": "uploaded", "id": "rep1", "url": "https://Logs.Example:443/log/rep1", "visibility": "public"},
               "b": {"status": "uploaded", "id": "rep2", "url": "https://logs.example/log/rep2?key=s", "visibility": "unlisted"},
               "c": {"status": "uploaded", "id": "rep3", "url": "https://logs.example/log/rep3", "visibility": "private"},
               "d": {"status": "failed", "error": "HTTP 413: too large"}}
    doc = cb.manifest(queued, results, {"url": "https://logs.example", "visibility": "public", "has_key": True})
    assert doc == {"format": "a2log-upload-manifest", "version": 1, "server": "https://logs.example", "visibility": "public",
                   "parts": [{"file": "a", "archive": {"id": "rec-1", "part": 2, "closed": True}, "status": "uploaded",
                              "id": "rep1", "url": "https://logs.example/log/rep1"},
                             {"file": "b", "status": "uploaded", "id": "rep2"},
                             {"file": "c", "status": "uploaded", "id": "rep3"},
                             {"file": "d", "status": "failed", "error": "HTTP 413: too large"}]}
    assert "server" not in cb.manifest({}, {}, None)
    assert cb.archive_meta({"id": "r", "part": True}) is None and cb.archive_meta({"id": "r", "part": 0}) is None
    assert cb.archive_meta({"id": "r" * 120, "part": 3.0})["id"] == "r" * 100
    assert cb.safe_link("javascript:alert(1)") == "" and cb.safe_link("https://x.example") == "https://x.example/"
    # which refusals fail a file, which leave it uncertain, and which stop the batch
    assert cb.refused("ValueError: HTTP 409: already uploaded") == ("failed", True)
    assert cb.refused("ValueError: HTTP 400: bad log") == ("failed", False)
    assert cb.refused("ValueError: HTTP 413: too large") == ("failed", False)
    assert cb.refused("ValueError: File changed since fingerprint verification") == ("failed", False)
    assert cb.refused("timed out") == ("unknown", True)
    assert cb.refused("ValueError: Upload server changed. Start a new batch with the intended server.") == ("unknown", True)
    assert cb.batch_message(1, 2, True, True) == (
        "1 / 2 uploaded. Cancelled between uploads. Stopped after a connection, authentication or rate-limit error; "
        "remaining files are pending. Known successful files are skipped only when their fingerprints match.")
    # the page's files a filter lets through, and the queue's limit
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "rec-1", "")] == ["session-3.a2log.json"]
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "ARENA", "")] == ["session-2.a2log.json"]
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "", "pve_open_world")] == ["session-1.a2log.json"]
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "2", "sanctuary")] == ["session-3.a2log.json"]  # its part
    full = {f"f{i}": {"file": f"f{i}"} for i in range(cb.QUEUE_LIMIT)}
    with pytest.raises(ValueError, match="Queue limit is 100 files"):
        cb.pick(full, {}, {"file": "one more"})
    again = {"file": "f1"}
    cb.pick(full, {"f1": {"fingerprint": fp}}, again)
    assert full["f1"] is again and again["fingerprint"] == fp            # picked again, with the fingerprint seen
    assert len(cb.request_id()) == 32 and cb.request_id() != cb.request_id()


def _recorded(app, tmp_path, **kwargs):
    widget = RecordedEncounters(app, store=_store(tmp_path), **kwargs)
    widget.resize(1100, 900)
    widget.show()
    return widget


def _labels(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _folds(widget):
    QCoreApplication.processEvents()
    return [f for f in widget.findChildren(Section) if f.isVisibleTo(widget)]


def _find(widget, kind, test):
    """The first shown ``kind`` passing ``test``, once what was drawn last has shown."""
    QCoreApplication.processEvents()
    return next(w for w in widget.findChildren(kind) if test(w) and w.isVisibleTo(widget))


def test_recorded_encounters(qapp, tmp_path):
    opened = []
    app = FakeApp()
    widget = _recorded(app, tmp_path, open_web=opened.append)
    settle(lambda: not widget.loading and widget.findChildren(Section))
    texts, every = _labels(widget), [label.text() for label in widget.findChildren(QLabel)]
    assert cb.RECORDED_NOTE + cb.RECORDED_LOADED in texts
    assert "Ice Queen" in every and "Frost Hound" not in every                         # a mini-boss hidden
    folds = _folds(widget)
    assert [(f.button.text(), f.body.isVisibleTo(widget)) for f in folds] == [
        ("PvP encounters", True), ("Field bosses", False), ("Raids", False)]             # the first one open
    assert "(1)" in texts and "Arena" in texts and "1:01" in texts
    folds[2].button.click()
    assert "2:05" in _labels(widget) and "Final boss" in _labels(widget) and "Hard" in _labels(widget)
    # the boss's portrait comes; a boss without one keeps the app's logo
    face = next(label for label, code in widget.faces if code == 2001)

    def centre(label):
        image = label.pixmap().toImage()
        return image.pixelColor(image.width() // 2, image.height() // 2)
    settle(lambda: centre(face) == QColor("#ff0000"))
    assert centre(next(label for label, code in widget.faces if code == 3001)) != QColor("#ff0000")
    _find(widget, QPushButton, lambda b: b.text() == "view").click()
    assert opened == ["combat-log/local/session-2.a2log.json?segment=0"]
    # mini-bosses shown, and kept so
    boss = _find(widget, QComboBox, lambda c: c.accessibleName() == "Boss")
    assert [boss.itemText(i) for i in range(boss.count())] == ["any", "Ash Wyrm", "Ice Queen"]
    _find(widget, QCheckBox, lambda c: c.accessibleName() == "Show mini-bosses").setChecked(True)
    assert widget.store.value(cb.MINI_KEY) == "1"
    boss = _find(widget, QComboBox, lambda c: c.accessibleName() == "Boss")
    assert [boss.itemText(i) for i in range(boss.count())] == ["any", "Ash Wyrm", "Frost Hound", "Ice Queen"]
    assert _recorded(app, tmp_path).mini                                    # the next time too
    # a filter: by kind, then by the days saved, then cleared
    kind = _find(widget, QComboBox, lambda c: c.accessibleName() == "Type")
    kind.setCurrentIndex(kind.findData("field_boss"))
    kind.activated.emit(kind.currentIndex())
    assert [f.button.text() for f in _folds(widget)] == ["Field bosses"]
    widget.f["category"] = ""
    widget._filter("from", "2026-11-05")
    assert cb.no_match(True) in _labels(widget)
    _find(widget, QPushButton, lambda b: b.text() == "Clear").click()
    assert widget.f == cb.NO_FILTERS and len(_folds(widget)) == 3
    # the next fifty recordings
    _find(widget, QPushButton, lambda b: b.text() == "Load more recordings").click()
    settle(lambda: not widget.loading and not widget.more)
    assert "/api/sessions?paged=1&offset=50&limit=50&archive=" in app.calls
    assert "(3)" in _labels(widget) and cb.RECORDED_NOTE in _labels(widget)       # the older raid, mini-bosses shown
    assert not any(b.text() == "Load more recordings" for b in widget.findChildren(QPushButton) if b.isVisibleTo(widget))
    # nothing recorded yet, and the recordings not read
    empty = FakeApp(older=False)
    empty.recordings = []
    widget = _recorded(empty, tmp_path)
    settle(lambda: cb.NO_RECORDED in _labels(widget))
    widget = _recorded(FakeApp(recordings_refused="OSError: the logs folder cannot be read"), tmp_path)
    settle(lambda: "OSError: the logs folder cannot be read" in _labels(widget))
    assert any(b.text() == "Retry" for b in widget.findChildren(QPushButton) if b.isVisibleTo(widget))


def _queue(app, **kwargs):
    queue = UploadQueue(app, **kwargs)
    queue.resize(1100, 900)
    queue.show()
    settle(lambda: not queue.busy)
    return queue


def _click(widget, words):
    button = _find(widget, QPushButton, lambda b: b.text() == words)
    assert button.isEnabled(), words
    button.click()


def _picks(queue):
    QCoreApplication.processEvents()
    return {b.accessibleName(): b for b in queue.findChildren(QCheckBox) if b.accessibleName().startswith("Select ")
            and b.isVisibleTo(queue)}


def test_the_upload_queue(qapp, tmp_path):
    links, opened = [], []
    app = FakeApp()
    queue = _queue(app, open_link=links.append, open_web=opened.append)
    texts = _labels(queue)
    assert cb.QUEUE_HEAD in texts and "rec-1 · Part 2" in texts and "Unfinished checkpoint" in texts and "File slots 1–25" in texts
    picks = _picks(queue)
    assert sorted(picks) == ["Select Field run", "Select Raid night", "Select session-2.a2log.json"]
    assert not picks["Select session-2.a2log.json"].isEnabled()           # an unfinished checkpoint stays out
    _click(queue, "Select eligible rows on this page")
    assert list(queue.selected) == ["session-3.a2log.json", "session-1.a2log.json"] and "2 selected" in _labels(queue)
    settle(lambda: app.queue_kept is not None and len(app.queue_kept["parts"]) == 2)
    assert app.queue_kept["server"] == "" and app.queue_kept["visibility"] == "public"
    queue.visibility.setCurrentText("unlisted")
    queue.visibility.activated.emit(queue.visibility.currentIndex())
    settle(lambda: app.queue_kept["visibility"] == "unlisted")
    # the second file refused with a conflict: the batch stops there
    app.refusals["session-1.a2log.json"] = "ValueError: HTTP 409: already uploaded"
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == cb.batch_message(1, 2, False, True)
    shares = [body for path, body in app.posts if path == "/api/sessions/share"]
    assert [body["file"] for body in shares] == ["session-3.a2log.json", "session-1.a2log.json"]
    assert shares[0]["visibility"] == "unlisted" and shares[0]["server"] == "https://logs.example"
    assert shares[0]["completed_only"] is True and shares[0]["fingerprint"] == app.fingerprint("session-3.a2log.json")
    assert len(shares[0]["request_id"]) == 32 and shares[0]["request_id"] != shares[1]["request_id"]
    assert queue.results["session-1.a2log.json"]["status"] == "failed"
    assert app.queue_kept["server"] == "https://logs.example" and [p["status"] for p in app.queue_kept["parts"]] == [
        "uploaded", "failed"]
    texts = _labels(queue)
    assert any(t.startswith("Raid night: uploaded") and "Open uploaded report" in t for t in texts)
    assert any(t == "Field run: failed — ValueError: HTTP 409: already uploaded" for t in texts)
    report = next(label for label in queue.findChildren(QLabel) if "Open uploaded report" in label.text())
    report.linkActivated.emit("https://logs.example/log/rep0001")
    assert links == ["https://logs.example/log/rep0001"]
    # again: the uploaded one skipped (its fingerprint unchanged), the other uploaded
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == cb.batch_message(2, 2, False, False) and app.uploads == 2
    retried = [body for path, body in app.posts if path == "/api/sessions/share"][-1]
    assert retried["file"] == "session-1.a2log.json" and retried["request_id"] == shares[1]["request_id"]  # the same request
    # an outcome not known: retried only once allowed
    app.prints["session-3.a2log.json"] = "d" * 64
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == "File changed: Raid night. Clear the queue and review the new content before uploading."
    del app.prints["session-3.a2log.json"]
    queue.results["session-1.a2log.json"] = {"status": "unknown", "fingerprint": app.fingerprint("session-1.a2log.json")}
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message.startswith("Uncertain upload outcome for Field run. Check My uploads")
    _find(queue, QCheckBox, lambda b: b.text() == cb.RETRY_UNKNOWN).setChecked(True)
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == cb.batch_message(2, 2, False, False) and app.uploads == 3
    # a batch for another server or visibility, and no server at all
    queue.visibility.setCurrentText("private")
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == "Server or visibility changed. Clear the queue before starting a different batch."
    # cancelled before the next upload
    _click(queue, "Clear queue")
    assert queue.message == cb.CLEARED and not queue.selected and queue.batch is None
    settle(lambda: app.queue_kept["parts"] == [])
    _click(queue, "Select eligible rows on this page")
    _click(queue, "Upload selected / retry remaining")
    cancel = next(b for b in queue.findChildren(QPushButton) if b.text() == "Cancel after current upload")
    assert cancel.isEnabled() and queue.busy
    cancel.click()                                       # before the batch's first answer comes back
    assert queue.message == cb.CANCELLING
    settle(lambda: not queue.busy)
    assert queue.message.startswith("0 / 2 uploaded. Cancelled between uploads.")
    app.server["url"] = ""
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == "Set an upload server first."
    # a file opened at its page; one recording's parts; the next page
    _find(queue, QPushButton, lambda b: b.text() == "Open").click()
    assert opened == ["combat-log/local/session-3.a2log.json"]
    _click(queue, "Show recording")
    settle(lambda: not queue.busy and queue.recording == "rec-1")
    assert app.calls[-1] == "/api/sessions?paged=1&offset=0&limit=25&archive=rec-1"
    assert "Recording rec-1 · parts remain separate reports" in _labels(queue)
    assert sorted(_picks(queue)) == ["Select Old raid", "Select Raid night"]
    _click(queue, "All recordings")
    settle(lambda: not queue.busy and queue.recording == "")
    _click(queue, "Older")
    settle(lambda: not queue.busy and queue.offset == 25)
    assert "File slots 26–50" in _labels(queue) and sorted(_picks(queue)) == ["Select Old raid"]
    _click(queue, "Newer")
    settle(lambda: not queue.busy and queue.offset == 0)
    words = _find(queue, QLineEdit, lambda w: w.accessibleName() == "Filter this page")
    words.setText("field")
    words.editingFinished.emit()
    assert sorted(_picks(queue)) == ["Select Field run"]


def test_the_upload_queue_recovery(qapp, tmp_path):
    fp = hashlib.sha256(b"session-3.a2log.json").hexdigest()
    kept = {"format": "a2log-upload-checkpoint", "version": 1, "server": "https://logs.example", "visibility": "private",
            "parts": [{"file": "session-3.a2log.json", "title": "Raid night", "fingerprint": fp, "status": "uploading",
                       "request_id": "e" * 32}]}
    app = FakeApp()
    app.queue_kept = kept
    saved = tmp_path / "out.json"
    recovery = tmp_path / "recovery.json"
    chosen = [str(recovery)]
    queue = _queue(app, choose_file=lambda: chosen[0], save_file=lambda name: str(saved) if name else "")
    _click(queue, "Restore saved queue")
    settle(lambda: not queue.busy and queue.selected)
    assert queue.message == cb.RESTORED and queue.chosen == "private" and queue.visibility.currentText() == "private"
    assert queue.results["session-3.a2log.json"]["status"] == "unknown"             # it may have been taken
    assert queue.batch == {"url": "https://logs.example", "visibility": "private"}
    assert not _find(queue, QPushButton, lambda b: b.text() == "Restore saved queue").isEnabled()
    _click(queue, "Export recovery file")
    assert json.loads(saved.read_text(encoding="utf-8"))["parts"][0]["status"] == "unknown"
    _click(queue, "Export upload results")
    assert json.loads(saved.read_text(encoding="utf-8"))["parts"] == [{"file": "session-3.a2log.json", "status": "unknown",
                                                                       "id": None}]
    # a recovery file: too large, unreadable, then one restored and kept
    _click(queue, "Clear queue")
    recovery.write_text("x" * (cb.RECOVERY_LIMIT + 1), encoding="utf-8")
    _click(queue, "Import recovery file…")
    assert queue.message == "Recovery file exceeds 256 KiB." and not queue.busy
    recovery.write_text("{not json", encoding="utf-8")
    _click(queue, "Import recovery file…")
    assert queue.message.startswith("Expecting property name") and not queue.selected
    recovery.write_text(json.dumps(dict(kept, visibility="unlisted", server="")), encoding="utf-8")
    _click(queue, "Import recovery file…")
    settle(lambda: not queue.busy)
    assert list(queue.selected) == ["session-3.a2log.json"] and queue.chosen == "unlisted" and queue.batch is None
    assert app.queue_kept["visibility"] == "unlisted"
    _click(queue, "Clear queue")
    app.queue_kept = None
    _click(queue, "Restore saved queue")
    settle(lambda: not queue.busy)
    assert queue.message == "No saved upload queue is available."
    chosen[0] = ""
    _click(queue, "Import recovery file…")                                # nothing chosen: nothing happens
    assert queue.message == "No saved upload queue is available."


def test_saved_logs_keep_their_queue(qapp, tmp_path):
    app = FakeApp()
    page = _page(app, store=_store(tmp_path))
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    settle(lambda: page.queue is not None and not page.queue.busy and page.recorded is not None and not page.recorded.loading)
    queue, recorded = page.queue, page.recorded
    _click(queue, "Select eligible rows on this page")
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "My Uploads").click()
    assert not page.saved_panel.isVisible() and cb.ON_THE_WEB_LIST in _texts(page)
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    assert page.queue is queue and page.recorded is recorded and len(queue.selected) == 2     # the same queue
    logs = app.calls.count("/api/logs")
    page.hide()
    page.show()                                                            # shown again: read again
    settle(lambda: app.calls.count("/api/logs") == logs + 1 and not recorded.loading and not queue.busy)
    assert len(queue.selected) == 2


def test_the_window_draws_combat_logs_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("combat"), CombatPage) and not isinstance(window.page("combat"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                      # not moved over yet
