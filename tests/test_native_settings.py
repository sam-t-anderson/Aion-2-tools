"""The native Settings page (0.2.414; as the web page draws it since 0.2.475, a part at a time).

The page's tabs and App & data are pages/settings.js's (``aion2calc/gui/settings_words``): each row's words, its
controls saving their settings through the app's ``/api/ui`` as the web page's do, and its actions asking the app what
the web page asks it. The other tabs' rows are still drawn from ``aion2calc/gui/settings_schema``: every control the
schema names saves one setting, so each key must be one of the app's settings and each default must fit its control;
a row the native page does not draw in full opens the web page. Off screen, over a made-up app.
"""
import io
import json
import os
import urllib.error

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.app import server  # noqa: E402
from aion2calc.gui import image_health  # noqa: E402
from aion2calc.gui import settings_words as sw  # noqa: E402
from aion2calc.gui.result_windows import GridTable  # noqa: E402
from aion2calc.gui.settings_page import PatchNotes, SettingsPage  # noqa: E402
from aion2calc.gui.settings_schema import GROUPS, ROWS, Bool, Choice  # noqa: E402
from aion2calc.gui.window import MainWindow, scale_text  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402

CONTROLS = [control for row in ROWS for control in row.controls]
#: The controls drawn as the web page draws them (App & data since 0.2.475, Meter and Server since 0.2.476) and the
#: settings they save, as the web page's handlers save them.
SYSTEM_KEYS = ("interface_native", "app_window", "app_text_scale", "performance_mode", "app_default_page",
               "character_auto_open", "character_auto_refresh", "tray_on_close", "auto_update", "update_on_close")
RECORD_KEYS = tuple(key for key, *_rest in sw.RECORD_CHECKS) + tuple(sw.RECORD_NUMBERS) + ("meter_log_cache_mb",)
SERVER_KEYS = ("community_heartbeat", "community_contribute_character")
PET_KEYS = ("pettracker_enabled", "pettracker_overlay", "pettracker_overlay_style", "pettracker_path")


def _described(items):
    """The settings a row described in settings_words saves (0.2.478)."""
    keys = []
    for item in items:
        if item[0] == "check":
            keys.append(item[1])
        elif item[0] == "row":
            keys += [control[1] for control in item[1]]
        elif item[0] == "check-number":
            keys += [item[1][1], item[2][1]]
    return tuple(keys)


OVERLAY_KEYS = _described(sw.LIVE_OVERLAY) + _described(sw.RTSS) + _described(sw.LAYOUT)
RADAR_KEYS = ("radar_enabled", "radar_sensitivity", "hotkeys")
DRAWN_KEYS = SYSTEM_KEYS + RECORD_KEYS + SERVER_KEYS + PET_KEYS + OVERLAY_KEYS + RADAR_KEYS
DRAWN_GROUPS = ("system", "meter", "server", "pettracker")
DRAWN_OVERLAY = ("Live meter overlay", "In-game (RTSS)", "Streaming (OBS / Discord)", "Overlay layout",
                 "Hidden Cube radar", "Hotkeys (Windows)")
T0 = 1700000000
STATUS = {"home": "/data/aion2calc", "version": "0.2.475", "db": {"items": 12345, "last_sync": {"at": T0}},
          "update": None, "update_state": {"checked_at": T0}, "update_download": {}}
NEWER = {**STATUS, "update": {"version": "0.2.476", "url": "https://example.invalid/release"},
         "update_download": {"state": "ready"}}
NOTES = {"version": "0.2.475", "all": "https://example.invalid/releases", "show": True, "notes": [
    {"version": "0.2.475", "title": "Settings in the native interface", "html": "<p>App &amp; data is native.</p>"},
    {"version": "0.2.474", "title": "An upload's log", "html": "<ul><li>Review</li></ul>"}]}
MAINTENANCE = {"note": "Managed files only.", "external_web_cache": True, "truncated": False, "groups": [
    {"category": "Web cache", "files": 12, "bytes": 3 * 1048576, "oldest_days": 9, "eligible_files": 4,
     "eligible_bytes": 1048576},
    {"category": "Updates", "files": 3, "bytes": 157286400, "oldest_days": 40, "eligible_files": 1,
     "eligible_bytes": 52428800}]}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists, as in test_native_interface.py:
    a window left for Python to collect at exit crashed the process on its way out."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


def _refused(path, status, message):
    return urllib.error.HTTPError("http://127.0.0.1:9" + path, status, "refused", {},
                                  io.BytesIO(json.dumps({"error": message}).encode()))


class FakeApp:
    """The app's local API as the page asks it: ``answers`` maps ``(method, path, action)`` to what the app says (a
    dict; an exception it raises; or a list of either, given in turn). Unknown requests are not found."""

    def __init__(self, answers=None):
        self.answers = {key: list(value) if isinstance(value, list) else value for key, value in (answers or {}).items()}
        self.calls = []

    def _answer(self, method, path, body):
        key = (method, path, (body or {}).get("action") if method == "POST" else None)
        self.calls.append((method, path, body))
        if key not in self.answers:
            raise _refused(path, 404, "not found")
        found = self.answers[key]
        if isinstance(found, list):
            found = found.pop(0) if len(found) > 1 else found[0]
        if isinstance(found, BaseException):
            raise found
        return json.loads(json.dumps(found))

    def get(self, path, timeout=None):
        return self._answer("GET", path, None)

    def get_bytes(self, path, timeout=None):
        raise _refused(path, 404, "not found")

    def post(self, path, payload, timeout=None, origin=False):
        return self._answer("POST", path, payload)

    def sent(self, method=None, path=None):
        return [(m, p, b) for m, p, b in self.calls if (method is None or m == method) and (path is None or p == path)]


def _store(tmp_path):
    return QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)


def _answers(more=None):
    answers = {("GET", "/api/status", None): STATUS, ("GET", "/api/logserver", None): {"url": "https://logs.example"},
               ("GET", "/api/ui", None): server.ui_settings(), ("POST", "/api/ui", None): {"ok": True}}
    answers.update(more or {})
    return answers


def _page(tmp_path, app=None, **kwargs):
    kwargs.setdefault("store", _store(tmp_path))
    page = SettingsPage(app, kwargs.pop("open_web", lambda page: None), **kwargs)
    page.resize(1200, 900)
    page.show()
    if page.job is not None:
        page.job.interval_ms = 10
    QCoreApplication.processEvents()
    return page


def _shown(widget, kind=QLabel):
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents()
    return [w for w in widget.findChildren(kind) if w.isVisibleTo(widget)]


def _texts(widget):
    return [label.text() for label in _shown(widget)]


def _button(widget, words, index=0):
    return [b for b in _shown(widget, QPushButton) if b.text() == words][index]


def _row(page, title):
    return next(row for row in page.rows if row.title == title)


# ------------------------------------------------------------------ the rows still drawn from the schema
def test_every_control_saves_one_of_the_apps_settings_and_its_default_fits(home):
    defaults = server.ui_settings()
    assert len(ROWS) == 9 and len(CONTROLS) == 2   # App & data, Meter, Server, Pet Tracker and most of Overlay drawn here
    assert len({control.key for control in CONTROLS}) == len(CONTROLS)                 # one control per setting
    assert not {control.key for control in CONTROLS} & set(DRAWN_KEYS)
    for control in CONTROLS:
        assert control.key in defaults, control.key
        value = defaults[control.key]
        if isinstance(control, Bool):
            assert isinstance(value, bool), control.key
        elif isinstance(control, Choice):
            assert control.cast(value) in [option for option, _text in control.options], control.key
        else:
            assert control.minimum <= value <= control.maximum, control.key
    assert {row.group for row in ROWS} <= {key for key, _title in GROUPS} - set(DRAWN_GROUPS)
    assert [key for key, _title in GROUPS] == [key for key, _title in sw.TABS]
    for key in DRAWN_KEYS:                                                             # the drawn rows' saves too
        assert key in defaults, key
    for key, (_words, _unit, low, high, shown) in {**sw.RECORD_NUMBERS, "meter_log_cache_mb": sw.LOG_CACHE}.items():
        assert low <= defaults[key] <= high and low <= shown <= high, key
    drawn = {r for r in sw.ROW_ORDER if r[0] in DRAWN_GROUPS or (r[0] == "overlay" and r[1] in DRAWN_OVERLAY)}
    assert len(OVERLAY_KEYS) == len(set(OVERLAY_KEYS)) == 62                 # 24 + 5 + 33, one each
    assert {(row.group, row.title) for row in ROWS} | drawn == set(sw.ROW_ORDER) and len(sw.ROW_ORDER) == 39


def test_the_page_shows_the_settings_without_saving_them_back(qapp, home):
    page = _page(home)
    ui = {**server.ui_settings(), "overlay_show_weekly_runs": False, "overlay_width": 420, "overlay_bg_mode": "top",
          "app_text_scale": 120, "interface_native": False, "tray_on_close": 1, "app_default_page": "account"}
    page.apply(ui)
    assert page.saved == []
    assert page.controls["overlay_show_weekly_runs"].box.isChecked() is False
    assert page.controls["overlay_show_odyle"].box.isChecked() is True
    assert page.controls["overlay_width"].value() == 420
    assert page.controls["overlay_bg_mode"].currentData() == "top"
    assert page.controls["app_text_scale"].currentData() == 120
    assert not page.controls["interface_native"].box.isChecked() and page.controls["tray_on_close"].box.isChecked()
    assert page.controls["app_window"].box.isChecked() and not page.controls["performance_mode"].box.isChecked()
    assert page.controls["app_default_page"].currentData() == "meter"                 # none of them: the first


def test_each_control_saves_its_setting(qapp, home):
    page = _page(home)
    page.apply(server.ui_settings())
    page.controls["overlay_show_weekly_runs"].box.setChecked(False)
    page.controls["overlay_show_weekly_runs"].label.mousePressEvent(None)            # the label toggles it too
    choice = page.controls["overlay_bg_mode"]
    choice.setCurrentIndex(choice.findData("none"))
    page.controls["app_text_scale"].setCurrentIndex(page.controls["app_text_scale"].findData(90))
    assert page.saved == [("overlay_show_weekly_runs", False), ("overlay_show_weekly_runs", True),
                          ("overlay_bg_mode", "none"), ("app_text_scale", 90)]
    page.controls["overlay_font_scale"].setValue(110)                                 # a schema row's number:
    page.controls["overlay_font_scale"].setValue(120)                                 # saved once, when still
    clock = QElapsedTimer()
    clock.start()
    while len(page.saved) < 5 and clock.elapsed() < 3000:
        QCoreApplication.processEvents()
    assert page.saved[4:] == [("overlay_font_scale", 120)] and page.toast.text() == "Saved"


def test_the_tabs_and_the_rows_on_the_web(qapp, home):
    opened = []
    store = _store(home)
    page = _page(home, open_web=opened.append, store=store)
    assert [b.text() for b in _shown(page, QPushButton)][:7] == [words for _key, words in sw.TABS]
    assert page.tab == "appearance" and [r.title for r in page.rows if r.isVisibleTo(page)] == [
        "Theme", "Accent colour", "Combat class colors"]
    page.tab_buttons["overlay"].click()
    shown = [r for r in page.rows if r.isVisibleTo(page)]
    assert {r.group for r in shown} == {"overlay"} and shown[0].title == "Live meter overlay"
    assert page.tab_buttons["overlay"].property("on") is True and page.tab_buttons["system"].property("on") is False
    assert store.value(sw.TAB_KEY) == "overlay"
    again = _page(home, store=store)                                                   # the tab chosen last, kept
    assert again.tab == "overlay"
    store.setValue(sw.TAB_KEY, "nowhere")
    assert _page(home, store=store).tab == "appearance"
    web = [row for row in ROWS if row.web]
    assert {row.title for row in web} >= {"Settings backup", "Overlay colors & fonts", "Overlay look presets"}
    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "Open the web Settings page"]
    assert len(buttons) == len(web) + 1                                               # and Language's
    buttons[0].click()
    assert opened == ["settings"]


def test_a_narrow_page_puts_each_rows_name_above_it(qapp, home):
    page = _page(home)
    page.show_tab("system")
    row = _row(page, "Native interface")
    assert row.line.direction() == row.line.Direction.LeftToRight and row.name.width() == 200
    page.resize(800, 900)
    QCoreApplication.processEvents()
    assert row.line.direction() == row.line.Direction.TopToBottom


# ------------------------------------------------------------------ App & data (0.2.475)
def test_app_and_data_as_the_web_page_draws_it(qapp, home):
    app = FakeApp(_answers())
    page = _page(home, app)
    page.show_tab("system")
    settle(lambda: page.home.text() == "/data/aion2calc" and page.ui)
    assert [r.title for r in page.rows if r.isVisibleTo(page)] == [title for group, title in sw.ROW_ORDER
                                                                   if group == "system"]
    assert {(m, p) for m, p, _b in app.calls} == {("GET", "/api/status"), ("GET", "/api/logserver"), ("GET", "/api/ui"),
                                                   ("GET", "/api/pettracker"),           # Pet Tracker's (0.2.477)
                                                   ("GET", "/api/rtss"),                 # RTSS's (0.2.478)
                                                   ("GET", "/api/radar")}                # the radar's (0.2.479)
    texts = _texts(page)
    for words in (sw.NATIVE, sw.NATIVE_NOTE, sw.APP_WINDOW, sw.APP_WINDOW_NOTE, sw.TEXT_LABEL, sw.TEXT_NOTE,
                  sw.TEXT_NATIVE, sw.PERFORMANCE_NOTE, sw.LANGUAGE_WEB, sw.LAUNCH_LABEL, sw.LAUNCH_NOTE,
                  sw.CHARACTER_NOTE, sw.TRAY, "/data/aion2calc", sw.MAINTENANCE_NOTE, sw.AUTO_UPDATE,
                  sw.UPDATE_ON_CLOSE, sw.UPDATES_NOTE, "Aion 2 Calc 0.2.475", sw.PATCH_NOTE, sw.AUTHOR, "— questions, builds and help"):
        assert words in texts, words
    assert f"12,345 items · last update {sw.when(T0 * 1000)}" in texts
    assert f"· up to date (checked {sw.when(T0 * 1000)[11:]})" in texts
    assert any(t.startswith(sw.PERFORMANCE) and sw.OFF_BY_DEFAULT in t for t in texts)
    assert any(t.startswith(sw.CHARACTER_REFRESH) and sw.CHARACTER_REFRESH_DEFAULT in t for t in texts)
    assert any(sw.DISCORD_URL in t and sw.DISCORD in t for t in texts)
    assert any(sw.PATCH_NOTES_URL in t and sw.ALL_NOTES in t for t in texts)
    assert sw.NATIVE_NOTE.startswith("On by default since 0.2.426. Every page but Raid Planner and Builds is native")
    pages = page.controls["app_default_page"]
    assert [pages.itemText(i) for i in range(pages.count())][:3] == ["Live Meter", "Combat Logs", "Raid Planner"]
    assert pages.count() == 16 and pages.findData("account") < 0
    sizes = page.controls["app_text_scale"]
    assert [sizes.itemText(i) for i in range(sizes.count())] == [f"{p}%" for p in (70, 80, 90, 100, 110, 120, 130, 140, 150)]
    # each control saves its setting, then says so; the tray's applies on the next launch
    page.controls["interface_native"].box.setChecked(False)
    settle(lambda: app.sent("POST", "/api/ui"))
    assert app.sent("POST", "/api/ui")[-1][2] == {"interface_native": False}
    settle(lambda: page.toast.isVisible() and page.toast.text() == "Saved")
    page.controls["tray_on_close"].box.setChecked(True)
    settle(lambda: page.toast.text() == sw.SAVED_NEXT_LAUNCH)
    page.controls["app_default_page"].setCurrentIndex(pages.findData("gear"))
    page.controls["app_text_scale"].setCurrentIndex(sizes.findData(130))
    page.controls["character_auto_refresh"].label.mousePressEvent(None)
    settle(lambda: len(app.sent("POST", "/api/ui")) == 5)
    assert [b for _m, _p, b in app.sent("POST", "/api/ui")][2:] == [
        {"app_default_page": "gear"}, {"app_text_scale": 130}, {"character_auto_refresh": True}]
    # a save the app refuses says why (the web page says nothing)
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "ValueError: not a setting")
    page.controls["auto_update"].box.setChecked(False)
    settle(lambda: page.toast.text() == "Could not save it: ValueError: not a setting")
    # shown again: read again, as the web page reads it each time it opens
    page.hide()
    page.show()
    settle(lambda: len(app.sent("GET", "/api/status")) == 2)


def test_your_data_and_the_game_database(qapp, home, tmp_path):
    image_health.retry()
    saved = []
    app = FakeApp(_answers({("POST", "/api/open", None): [{"ok": True}, _refused("/api/open", 400, "No file manager")],
                              ("POST", "/api/sync", None): {"ok": True},
                              ("POST", "/api/assets/reindex", None): {"job": "j1"},
                              ("GET", "/api/jobs/j1", None): [{"status": "running", "log": ["Profiles 1 of 2"]},
                                                              {"status": "done", "result": {"profiles": 2, "references": 1500,
                                                                                            "skipped": 3}}],
                              ("GET", "/api/assets", None): {"items": {"total": 10}}}))
    target = tmp_path / "coverage.json"
    page = _page(home, app, save_file=lambda name: (saved.append(name), str(target))[1])
    page.show_tab("system")
    settle(lambda: page.home.text())
    # each folder opened by the app; a refusal said
    _button(page, "Open folder").click()
    _button(page, "Combat logs").click()
    settle(lambda: len(app.sent("POST", "/api/open")) == 2)
    assert [b for _m, _p, b in app.sent("POST", "/api/open")] == [{"what": "data"}, {"what": "logs"}]
    settle(lambda: page.toast.text() == "No file manager")
    assert _button(page, "Advice & results")
    # the game database checked
    _button(page, sw.CHECK_NOW).click()
    settle(lambda: page.toast.text() == sw.SYNCING)
    assert app.sent("POST", "/api/sync")[0][2] == {}
    # the cached icons re-indexed as a job: its progress, then what it did
    page.reindex()
    assert not page.reindex_button.isEnabled() and page.asset_message.text() in (sw.REINDEXING, "Profiles 1 of 2")
    settle(lambda: page.asset_message.text().startswith("Re-indexed"))
    assert page.asset_message.text() == ("Re-indexed 2 profiles · 1,500 references examined · 3 skipped. Reopen the "
                                         "affected view to reload icons.")
    assert page.reindex_button.isEnabled() and page.toast.text() == sw.REINDEXED_TOAST
    # the image coverage: the app's report with this window's picture failures, saved where asked
    image_health.failed("https://metabot.gg/web/aion2/skills/11010000.webp")
    image_health.failed("https://metabot.gg/web/aion2/skills/11010000.webp")
    image_health.failed("http://127.0.0.1:9/static/x.png")                            # not a public host: not kept
    page.export_images()
    settle(lambda: page.asset_message.text().startswith("Image coverage saved"))
    assert saved == [sw.IMAGES_FILE] and page.asset_message.text() == f"Image coverage saved: {target}"
    report = json.loads(target.read_text())
    assert report["items"] == {"total": 10} and report["browser_images"]["version"] == 2
    [failure] = report["browser_images"]["failures"]
    assert failure["host"] == "metabot.gg" and failure["count"] == 2 and failure["skill_id"] == "11010000"
    assert failure["references"] == [{"namespace": "metabot", "kind": "skill", "id": "11010000"}]
    # Retry images: the failures forgotten, each reader told
    told = []

    class Reader:
        def retry_pictures(self):
            told.append(True)
    reader = Reader()
    image_health.watch(reader)
    _button(page, sw.RETRY_IMAGES).click()
    assert page.asset_message.text() == sw.RETRIED and told == [True] and image_health.report()["failures"] == []


def test_storage_maintenance(qapp, home):
    app = FakeApp(_answers({("GET", "/api/maintenance", None): MAINTENANCE,
                              ("POST", "/api/maintenance", "caches"): {"deleted": 4, "skipped": 1},
                              ("POST", "/api/maintenance", "updates"): _refused("/api/maintenance", 400, "Busy")}))
    page = _page(home, app)
    page.show_tab("system")
    _button(page, sw.INSPECT).click()
    settle(lambda: page.findChildren(GridTable))
    texts = _texts(page)
    assert "Managed files only." in texts and sw.EXTERNAL_CACHE in texts and sw.SCAN_LIMIT not in texts
    assert [t for t in texts if t in ("WEB CACHE", "Web cache", "12", "3.00", "9", "4 files / 1.00 MiB")] == [
        "Web cache", "12", "3.00", "9", "4 files / 1.00 MiB"]
    assert "1 files / 50.00 MiB" in texts and "150.00" in texts
    assert [w.upper() for w in sw.MAINTENANCE_COLUMNS] == [t for t in texts if t in [w.upper() for w in sw.MAINTENANCE_COLUMNS]]
    _button(page, sw.CLEAN_CACHE).click()
    assert page.storage_message.text() == sw.CLEANING and not page.clean_buttons["caches"].isEnabled()
    settle(lambda: page.storage_message.text().startswith("Removed"))
    assert page.storage_message.text() == "Removed 4 files; 1 changed, active, locked or uninspectable files preserved."
    assert page.clean_buttons["caches"].isEnabled()
    settle(lambda: len(app.sent("GET", "/api/maintenance")) == 2)                     # inspected again
    _button(page, sw.CLEAN_UPDATES).click()
    settle(lambda: page.storage_message.text() == "Busy")
    assert page.clean_buttons["updates"].isEnabled()


def test_the_version_its_check_and_its_update(qapp, home):
    app = FakeApp(_answers({("POST", "/api/update/check", None): [{"update_state": {"error": "no network"}},
                                                                  {"update": {"version": "0.2.476"}}],
                              ("POST", "/api/update", None): [{"status": "download-failed"}, {"status": "odd-state"},
                                                             {"status": "launching"}]}))
    page = _page(home, app)
    page.show_tab("system")
    settle(lambda: page.check_button is not None and page.status)
    # up to date: checked again on request, a failed check said as such
    page.check_button.click()
    assert page.update_state.text() == sw.CHECKING and not page.check_button.isEnabled()
    settle(lambda: "could not check" in page.update_state.text())
    assert page.update_state.text() == "· could not check for updates (no network); trying again shortly"
    # a release is out: the page read again, with Update now and the release's notes
    app.answers[("GET", "/api/status", None)] = NEWER
    page.check_button.click()
    settle(lambda: page.update_button is not None)
    texts = _texts(page)
    assert "· version 0.2.476 downloaded" in texts and any("https://example.invalid/release" in t for t in texts)
    page.update_button.click()
    assert page.update_message.text() == sw.OPENING_INSTALLER and not page.update_button.isEnabled()
    settle(lambda: page.update_message.text() == "download failed")
    assert page.update_button.isEnabled()
    page.update_button.click()
    settle(lambda: page.update_message.text() == "odd-state")
    page.update_button.click()                                                          # the installer opens: the page goes
    settle(lambda: sw.CLOSING in [label.text() for label in page.findChildren(QLabel)])


def test_the_patch_notes_and_quitting(qapp, home):
    links, quits, asked = [], [], []
    answers = [False, True]
    app = FakeApp(_answers({("GET", "/api/patch-notes?force=1", None): [NOTES, {**NOTES, "notes": []}],
                              ("POST", "/api/quit", None): {"ok": True}}))
    page = _page(home, app, open_link=links.append, quit_app=lambda: quits.append(True),
                 confirm=lambda words: (asked.append(words), answers.pop(0))[1])
    page.show_tab("system")
    _button(page, sw.WHATS_NEW).click()
    settle(lambda: page.notes_dialog is not None and page.notes_dialog.isVisible())
    dialog = page.notes_dialog
    assert isinstance(dialog, PatchNotes) and dialog.windowTitle() == "What's new in Aion 2 Calc 0.2.475"
    html = dialog.body.toHtml()
    assert "Settings in the native interface" in html and "App &amp; data is native." in html and "Review" in html
    assert html.index("0.2.475") < html.index("0.2.474")                              # newest first
    dialog.close_button.click()
    assert not dialog.isVisible() and not app.sent("POST", "/api/patch-notes")       # Settings' notes: nothing to record
    _button(page, sw.WHATS_NEW).click()
    settle(lambda: page.notes_message.text() == sw.NO_NOTES)
    # the app stopped once asked, then this window closed
    _button(page, sw.QUIT).click()
    assert asked == [sw.ASK_QUIT] and not app.sent("POST", "/api/quit") and quits == []
    _button(page, sw.QUIT).click()
    settle(lambda: quits)
    assert app.sent("POST", "/api/quit")[0][2] == {}


# ------------------------------------------------------------------ Meter and Server (0.2.476)
def test_combat_records_as_the_web_page_draws_it(qapp, home):
    app = FakeApp(_answers({("GET", "/api/ui", None): {**server.ui_settings(), "meter_reset_after_battle": True,
                                                        "meter_auto_upload": False, "meter_reset_delay": "7",
                                                        "meter_max_records": None, "meter_log_cache_mb": 0}}))
    page = _page(home, app)
    page.show_tab("meter")
    settle(lambda: page.ui)
    assert [r.title for r in page.rows if r.isVisibleTo(page)] == ["Combat records"]
    row = _row(page, "Combat records")
    texts = _texts(row)
    for _key, words, _muted, _on, _saved in sw.RECORD_CHECKS:
        assert any(t.startswith(words.replace("&", "&amp;")) or t == words for t in texts), words
    for note in (sw.LOG_CACHE_NOTE, sw.PRUNE_NOTE, sw.PER_FIGHT_NOTE, sw.BOSS_KILLS_NOTE, sw.ENEMY_HP_NOTE,
                 sw.GATHERING_NOTE, sw.DIAGNOSTICS_NOTE, sw.RECORDS_NOTE):
        assert note in texts, note
    for words in ("Reset delay", "Keep up to", "past combats", "Keep the logs folder under", "MB",
                  "Training-dummy parse window"):
        assert words in texts, words
    # shown by the web page's rules: on unless false, on only when true; a number the app has none of, its default
    checked = {key: page.controls[key].box.isChecked() for key, *_rest in sw.RECORD_CHECKS}
    assert checked["meter_reset_after_battle"] and not checked["meter_auto_upload"] and checked["meter_upload_per_fight"]
    assert not checked["meter_show_server_name"]
    assert page.controls["meter_reset_delay"].value() == 7 and page.controls["meter_max_records"].value() == 20
    assert page.controls["meter_log_cache_mb"].value() == 0 and page.controls["meter_dummy_record_seconds"].value() == 60
    assert page.controls["meter_log_cache_mb"].singleStep() == 128
    # each checkbox saves its setting and says what the web page says
    page.controls["meter_save_records"].box.setChecked(False)
    settle(lambda: page.toast.text() == "Saved · applies to the next capture")
    page.controls["meter_autostart"].box.setChecked(False)
    settle(lambda: page.toast.text() == sw.SAVED_NEXT_LAUNCH)
    page.controls["share_gathering"].label.mousePressEvent(None)
    settle(lambda: page.toast.text() == "Saved" and len(app.sent("POST", "/api/ui")) == 3)
    assert [b for _m, _p, b in app.sent("POST", "/api/ui")] == [{"meter_save_records": False}, {"meter_autostart": False},
                                                                {"share_gathering": False}]
    # a number saved once typed and left, or stepped; said beside them
    delay = page.controls["meter_reset_delay"]
    assert not delay.keyboardTracking() and (delay.minimum(), delay.maximum()) == (1, 120)
    delay.setValue(12)
    settle(lambda: page.records_message.text() == "Saved")
    assert app.sent("POST", "/api/ui")[-1][2] == {"meter_reset_delay": 12}
    page.controls["meter_dummy_record_seconds"].setValue(90)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"meter_dummy_record_seconds": 90})
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "ValueError: busy")
    page.controls["meter_max_records"].setValue(30)
    settle(lambda: page.records_message.text() == "ValueError: busy")
    app.answers[("POST", "/api/ui", None)] = {"ok": True}
    # the logs folder's cap: saved, then said for a moment; 0 turns auto-delete off
    cache = page.controls["meter_log_cache_mb"]
    cache.setValue(2048)
    settle(lambda: page.log_cache_message.text() == "Saved · logs kept under 2048 MB")
    assert app.sent("POST", "/api/ui")[-1][2] == {"meter_log_cache_mb": 2048} and page._log_cache_clear.isActive()
    page._log_cache_clear.timeout.emit()
    assert page.log_cache_message.text() == ""
    cache.setValue(0)
    settle(lambda: page.log_cache_message.text() == "Saved · auto-delete off")
    # shown again: the values set from the app without saving them back
    sent = len(app.sent("POST", "/api/ui"))
    page.apply(server.ui_settings())
    assert len(app.sent("POST", "/api/ui")) == sent


def test_the_log_server_and_community_stats(qapp, home):
    default = {"url": "https://logs.example", "is_default": True, "has_key": False, "visibility": "unlisted"}
    app = FakeApp(_answers({("GET", "/api/logserver", None): default,
                            ("POST", "/api/logserver", None): [{"url": "https://mine.example"}, {"url": "https://mine.example"},
                                                              _refused("/api/logserver", 400, "Enter an https address")],
                            ("GET", "/api/logserver/check", None): [
                                {"ok": True, "name": "A&B logs", "software": {"server": "1.4", "analyzer": "2.0"}},
                                {"ok": False, "detail": "timed out"},
                                {"ok": True, "software": {}},
                                {"ok": False},
                                _refused("/api/logserver/check", 500, "Probe failed")]}))
    page = _page(home, app)
    page.show_tab("server")
    settle(lambda: page.server)
    assert [r.title for r in page.rows if r.isVisibleTo(page)] == ["Log server", "Community stats"]
    # the community default in use: its address as the hint, the field empty, and the line saying so
    assert page.server_url.text() == "" and page.server_url.placeholderText() == "https://logs.example (default)"
    assert page.server_key.placeholderText() == "upload key (optional)" and page.server_key.echoMode() == page.server_key.EchoMode.Password
    assert page.server_visibility.currentData() == "unlisted" and page.server_default.isVisibleTo(page)
    assert [page.server_visibility.itemText(i) for i in range(4)] == ["public", "unlisted", "legion only", "private"]
    assert page.server_visibility.toolTip() == sw.VISIBILITY_TIP
    # saved, then probed from this computer: reachable with its name and versions, else why not
    page.server_url.setText("https://mine.example")
    page.server_key.setText("s3cret")
    page.server_visibility.setCurrentIndex(page.server_visibility.findData("private"))
    page.server_save.click()
    settle(lambda: page.server_message.text().startswith("saved · server reachable"))
    assert app.sent("POST", "/api/logserver")[0][2] == {"url": "https://mine.example", "key": "s3cret", "visibility": "private"}
    assert page.server_message.text() == "saved · server reachable — A&B logs · server 1.4 · analyzer 2.0"
    page.server_key.setText("")
    page.server_save.click()
    settle(lambda: page.server_message.text() == "saved · can't reach the server (timed out)")
    assert app.sent("POST", "/api/logserver")[1][2]["key"] is None                     # no key typed: none sent
    page.server_save.click()                                                           # refused: said, nothing checked
    settle(lambda: page.toast.text() == "Could not save it: Enter an https address")
    # the saved server checked
    page.server_check_button.click()
    assert page.server_message.text() == sw.CHECKING_SERVER and not page.server_check_button.isEnabled()
    settle(lambda: page.server_message.text() == "Server reachable · runtime versions not reported by this server")
    assert page.server_check_button.isEnabled()
    page.server_check_button.click()
    settle(lambda: page.server_message.text() == "Check failed: unavailable")
    page.server_check_button.click()
    settle(lambda: page.server_message.text() == "Probe failed")
    # a server of your own: its address, its key saved, no default line
    page.apply_server({"url": "https://mine.example", "has_key": True, "visibility": "legion"})
    assert page.server_url.text() == "https://mine.example" and page.server_key.placeholderText() == "key saved"
    assert page.server_visibility.currentData() == "legion" and not page.server_default.isVisibleTo(page)
    # Community stats
    row = _row(page, "Community stats")
    assert all(w in _texts(row) for w in (sw.HEARTBEAT, sw.HEARTBEAT_NOTE, sw.CONTRIBUTE, sw.CONTRIBUTE_NOTE))
    assert page.controls["community_heartbeat"].box.isChecked()
    page.controls["community_contribute_character"].box.setChecked(False)
    settle(lambda: app.sent("POST", "/api/ui") and app.sent("POST", "/api/ui")[-1][2] == {"community_contribute_character": False})


# ------------------------------------------------------------------ Pet Tracker (0.2.477)
PT_INSTALLING = {"supported": True, "installed": None, "setup": {"status": "downloading", "version": "2.0"}}
PT_INSTALLED = {"supported": True, "installed": {"version": "1.9", "folder": "C:/Pet Tracker"}, "enabled": True,
                "connected": True, "status": "Live", "character": "TestSorc",
                "update": {"available": True, "latest": "2.0", "installed": "1.9"}}


def test_the_pet_tracker_tab(qapp, home):
    opened = []
    app = FakeApp(_answers({("GET", "/api/ui", None): {**server.ui_settings(), "pettracker_overlay": True,
                                                        "pettracker_overlay_style": "pettracker",
                                                        "pettracker_path": "D:/PT portable"},
                            ("GET", "/api/pettracker", None): [PT_INSTALLING, PT_INSTALLED],
                            ("POST", "/api/pettracker", "update"): [{**PT_INSTALLED, "message": "Pet Tracker is updating."},
                                                                    {"error": "Pet Tracker did not answer"}],
                            ("POST", "/api/pettracker", "install"): _refused("/api/pettracker", 400, "No signed release")}))
    page = _page(home, app, open_page=opened.append)
    page.show_tab("pettracker")
    assert [r.title for r in page.rows if r.isVisibleTo(page)] == ["Pet Tracker", "Use Pet Tracker", "Pet Tracker overlay",
                                                                  "Pet Tracker folder"]
    # not installed, its install under way: the button waits, the install says what it does, read again in 2 s
    settle(lambda: sw.NOT_INSTALLED in _texts(page))
    texts = _texts(page)
    assert "Downloading Pet Tracker 2.0…" in texts and sw.PET_INSTALL_NOTE in texts
    assert not _button(page, sw.INSTALL_PETS).isEnabled() and page.pet_timer.isActive()
    assert page.pet_timer.interval() == 2000
    page.pet_timer.timeout.emit()
    settle(lambda: any(t.startswith("Installed: version 1.9") for t in _texts(page)))
    assert "Installed: version 1.9, in C:/Pet Tracker. TestSorc · Live" in _texts(page) and not page.pet_timer.isActive()
    assert "Pet Tracker 2.0 is available (you have 1.9)." in _texts(page)
    # the update: Pet Tracker's words, then its state read again; a refusal said
    _button(page, "Update Pet Tracker").click()
    settle(lambda: page.pet_note.text() == "Pet Tracker is updating.")
    settle(lambda: len(app.sent("GET", "/api/pettracker")) == 3)
    _button(page, "Update Pet Tracker").click()
    settle(lambda: page.pet_note.text() == "Pet Tracker did not answer")
    # the intro's link: the Pet Tracker page, in the window
    intro = next(label for label in _shown(page) if label.text().startswith(sw.PET_INTRO.replace("'", "&#x27;")) or
                 sw.PET_PAGE in label.text())
    intro.linkActivated.emit("pets")
    assert opened == ["pets"]
    # the settings shown as the web page reads them, and saved
    assert not page.controls["pettracker_enabled"].box.isChecked() and page.controls["pettracker_overlay"].box.isChecked()
    assert page.controls["pettracker_overlay_style"].currentData() == "pettracker"
    assert page.pet_folder.text() == "D:/PT portable" and page.pet_folder.placeholderText() == sw.PET_FOLDER_HINT
    for words in (sw.USE_PETS_NOTE, sw.PET_OVERLAY_NOTE, sw.PET_FOLDER_NOTE):
        assert words in _texts(page), words
    page.controls["pettracker_enabled"].box.setChecked(True)                           # saved, then Pet Tracker read again
    settle(lambda: page.toast.text() == "Saved" and page.pet_timer.isActive())
    assert page.pet_timer.interval() == sw.PET_ENABLED_READ_MS
    page.controls["pettracker_overlay_style"].setCurrentIndex(0)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"pettracker_overlay_style": "app"})
    page.pet_folder.setText("  E:/PT  ")
    _button(page, sw.SAVE).click()
    settle(lambda: page.pet_folder_message.text() == "Saved")
    assert app.sent("POST", "/api/ui")[-1][2] == {"pettracker_path": "E:/PT"}
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "ValueError: no such folder")
    _button(page, sw.SAVE).click()
    settle(lambda: page.pet_folder_message.text() == "ValueError: no such folder")


def test_pet_tracker_elsewhere_and_not_installed(qapp, home):
    app = FakeApp(_answers({("GET", "/api/pettracker", None): [{"supported": False},
                                                              {"supported": True, "installed": None, "setup": {}}],
                            ("POST", "/api/pettracker", "install"): _refused("/api/pettracker", 400, "No signed release")}))
    page = _page(home, app)
    page.show_tab("pettracker")
    settle(lambda: sw.PETS_UNSUPPORTED in _texts(page))
    page.read_pets()
    settle(lambda: sw.NOT_INSTALLED in _texts(page))
    assert _button(page, sw.INSTALL_PETS).isEnabled() and not page.pet_timer.isActive()
    _button(page, sw.INSTALL_PETS).click()                                             # refused: said in its place
    settle(lambda: "No signed release" in _texts(page))


# ------------------------------------------------------------------ Overlay, first part (0.2.478)
def test_the_live_meter_overlay_and_rtss(qapp, home, tmp_path):
    sound = tmp_path / "chime.ogg"
    sound.write_bytes(b"OggS" + b"\0" * 60)
    big = tmp_path / "long.wav"
    big.write_bytes(b"\0" * (1024 * 1024 + 1))
    chosen = [str(big), str(sound), ""]
    app = FakeApp(_answers({("GET", "/api/ui", None): {**server.ui_settings(), "overlay_close_on_stop": True,
                                                        "overlay_show_target": False, "overlay_cooldowns_min_s": "x",
                                                        "overlay_cooldowns_max": 0, "overlay_cooldowns_position": "top",
                                                        "overlay_events_sound_set": True, "rtss_metric": "nope",
                                                        "rtss_interval_ms": 250},
                            ("GET", "/api/rtss", None): [{"supported": True, "enabled": False},
                                                         {"supported": True, "enabled": True, "connected": True, "slot": 3,
                                                          "version": "2.21", "updates": 42}],
                            ("POST", "/api/overlay/event-sound", None): [{"overlay_events_sound_set": True},
                                                                         {"overlay_events_sound_set": False}]}))
    page = _page(home, app)
    page.choose_sound = lambda: chosen.pop(0)
    page.show_tab("overlay")
    settle(lambda: page.ui and page.rtss_message.text() == "Off.")
    texts = _texts(page)
    for item in sw.LIVE_OVERLAY + sw.RTSS:
        if item[0] == "note":
            assert item[1] in texts, item[1]
    assert sw.SOUND_NATIVE in texts
    # shown by the web page's rules
    assert page.controls["overlay_close_on_stop"].box.isChecked() and not page.controls["overlay_show_target"].box.isChecked()
    assert page.controls["overlay_show_contribution"].box.isChecked() and not page.controls["overlay_show_ttk"].box.isChecked()
    assert page.controls["overlay_cooldowns_min_s"].value() == 3 and page.controls["overlay_cooldowns_max"].value() == 1
    assert page.controls["overlay_cooldowns_position"].currentData() == "top"
    assert page.controls["rtss_metric"].currentData() == "dps" and page.controls["rtss_interval_ms"].value() == 250
    assert page.controls["rtss_interval_ms"].singleStep() == 50 and page.sound_message.text() == sw.SOUND_SET
    assert page.controls["overlay_show_odyle"].toolTip().startswith("The game's own count")
    # each saved with what the web page says
    page.controls["overlay_open_on_app_start"].box.setChecked(False)
    settle(lambda: page.toast.text() == sw.SAVED_NEXT_LAUNCH)
    page.controls["overlay_cooldowns_max"].setValue(12)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"overlay_cooldowns_max": 12} and page.toast.text() == "Saved")
    page.controls["rtss_style"].setCurrentIndex(1)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"rtss_style": "colored"})
    # Show overlay when starting: a refusal puts it back and says so
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "busy")
    page.controls["overlay_on_start"].box.setChecked(False)
    settle(lambda: page.toast.text() == "Could not save overlay preference: busy")
    assert page.controls["overlay_on_start"].box.isChecked() and len(app.sent("POST", "/api/ui")) == 4   # not sent again
    app.answers[("POST", "/api/ui", None)] = {"ok": True}
    # RTSS: saved, then its state read again 800 ms later
    page.controls["rtss_enabled"].box.setChecked(True)
    settle(lambda: page.rtss_timer.isActive())
    assert page.rtss_timer.interval() == sw.RTSS_READ_MS
    page.rtss_timer.timeout.emit()
    settle(lambda: page.rtss_message.text() == "Drawing in RTSS OSD slot 3 (shared memory v2.21, 42 updates).")
    app.answers[("GET", "/api/rtss", None)] = _refused("/api/rtss", 500, "gone")
    page.read_rtss()
    settle(lambda: page.rtss_message.text() == sw.RTSS_UNAVAILABLE)
    # the event sound: too big, then uploaded as a data address, then the built-in chime again
    _button(page, sw.SOUND_UPLOAD).click()
    assert page.sound_message.text() == sw.SOUND_TOO_BIG and not app.sent("POST", "/api/overlay/event-sound")
    _button(page, sw.SOUND_UPLOAD).click()
    settle(lambda: page.sound_message.text() == sw.SOUND_SAVED)
    data = app.sent("POST", "/api/overlay/event-sound")[0][2]["data"]
    import base64
    assert data.startswith("data:audio/ogg;base64,") and base64.b64decode(data.partition(",")[2]) == sound.read_bytes()
    _button(page, sw.SOUND_UPLOAD).click()                                             # nothing chosen: nothing sent
    _button(page, sw.SOUND_DEFAULT).click()
    settle(lambda: page.sound_message.text() == sw.SOUND_CLEARED)
    assert app.sent("POST", "/api/overlay/event-sound")[-1][2] == {"clear": True}
    assert len(app.sent("POST", "/api/overlay/event-sound")) == 2


def test_the_streaming_address_and_the_overlay_layout(qapp, home):
    app = FakeApp(_answers({("GET", "/api/ui", None): {**server.ui_settings(), "overlay_max_players": 0,
                                                        "overlay_height": None, "overlay_name_mode": "number",
                                                        "overlay_me_cosmetic": "aether", "overlay_always_visible": False}}))
    app.base = "http://127.0.0.1:9123/"
    page = _page(home, app)
    page.show_tab("overlay")
    settle(lambda: page.ui)
    # the overlay's address for a browser source, copied and said for 2 s; the notes as the web page words them
    assert page.stream_url.text() == "http://127.0.0.1:9123/overlay" and page.stream_url.isReadOnly()
    _button(page, sw.STREAM_COPY).click()
    assert QApplication.clipboard().text() == "http://127.0.0.1:9123/overlay"
    assert page.stream_message.text() == sw.STREAM_COPIED and page._stream_clear.isActive()
    page._stream_clear.timeout.emit()
    assert page.stream_message.text() == ""
    assert any("<b>OBS / Streamlabs Browser Source</b>" in t for t in _texts(page))
    # the layout: a number the app has none of, its default; the lists; the checkboxes' rules
    assert page.controls["overlay_max_players"].value() == 8 and page.controls["overlay_height"].value() == 0
    assert page.controls["overlay_name_mode"].currentData() == "number"
    assert page.controls["overlay_me_cosmetic"].currentData() == "aether"
    assert [page.controls["overlay_top_cosmetic"].itemText(i) for i in range(7)][:2] == ["None", "Gold: a turning gold frame and a diamond"]
    assert not page.controls["overlay_always_visible"].box.isChecked() and page.controls["overlay_remember_position"].box.isChecked()
    assert page.controls["overlay_hover_interact"].contentsMargins().left() == 22
    # the numbers checked and said beside their row; the interval inside its checkbox's line
    page.controls["overlay_width"].setValue(400)
    settle(lambda: page.number_messages["layout"].text() == "Saved")
    assert app.sent("POST", "/api/ui")[-1][2] == {"overlay_width": 400}
    page.controls["overlay_interpolate_ms"].setValue(150)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"overlay_interpolate_ms": 150})
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "ValueError: too wide")
    page.controls["overlay_width"].setValue(500)
    settle(lambda: page.number_messages["layout"].text() == "ValueError: too wide")
    app.answers[("POST", "/api/ui", None)] = {"ok": True}
    # each checkbox with what the web page says once saved
    page.controls["overlay_click_through"].box.setChecked(True)
    settle(lambda: page.toast.text() == sw.SAVED_OPEN_OVERLAY)
    page.controls["overlay_snap_edge"].box.setChecked(True)
    settle(lambda: page.toast.text() == sw.SAVED_RELAUNCH_OVERLAY)
    page.controls["overlay_bar_style"].setCurrentIndex(1)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"overlay_bar_style": "gradient"})


# ------------------------------------------------------------------ Overlay: the radar and the hotkeys (0.2.479)
RADAR_READY = {"supported": True, "setting": True, "enabled": True, "listening": True, "ready": True, "heard": True,
               "direction": "ahead", "proximity": 0.9, "match": 0.5,
               "model": {"cubes": 2, "backgrounds": 1, "front_back": "learned"},
               "samples": [{"id": "s1", "kind": "background", "at": "2026-11-22T01:02:03"},
                           {"id": "s2", "kind": "cube", "level_db": 0, "notes": True}]}


def test_the_hidden_cube_radar(qapp, home):
    asked, answers = [], [False, True]
    app = FakeApp(_answers({("GET", "/api/ui", None): {**server.ui_settings(), "radar_sensitivity": 11,
                                                        "hotkeys": {"radar_learn_cube": "Alt+F2", "radar_learn_other": ""}},
                            ("GET", "/api/radar", None): [{"supported": True, "setting": False, "model": {}},
                                                          {"supported": True, "learning": {"kind": "background",
                                                                                           "phase": "countdown", "seconds": 4.2}},
                                                          RADAR_READY],
                            ("POST", "/api/radar", "learn"): {"ok": True},
                            ("POST", "/api/radar", "clear"): {"error": "The radar is learning"},
                            ("POST", "/api/radar", "forget"): {"ok": True}}))
    page = _page(home, app, confirm=lambda words: (asked.append(words), answers.pop(0))[1])
    page.show_tab("overlay")
    settle(lambda: page.ui and page.radar_message.text().startswith("Nothing learned yet"))
    assert page.radar_message.text() == "Nothing learned yet: step 1, then step 2. Off."
    assert page.radar_slider.value() == 5 and not page.controls["radar_enabled"].box.isChecked()   # 11: none of 1 to 10
    # the notes name each step's key: a default, one changed, one cleared (its button then)
    notes = page.radar_notes.text()
    assert "<b>Ctrl+1</b> where no cube" in notes and "<b>Alt+F2</b> facing a Hidden Cube" in notes
    assert "<b>Ctrl+3</b> from where" in notes and "The “not a cube” button while" in notes
    # read twice a second while the tab shows it
    assert page.radar_poll.isActive() and page.radar_poll.interval() == 500
    page.radar_poll.timeout.emit()
    settle(lambda: page.radar_message.text() == "Learning the background in 5 s: switch to the game.")
    assert page.radar_cancel.isVisibleTo(page)
    page.show_tab("system")                                                             # not shown: not read
    reads = len(app.sent("GET", "/api/radar"))
    page.radar_poll.timeout.emit()
    QCoreApplication.processEvents()
    assert len(app.sent("GET", "/api/radar")) == reads
    page.show_tab("overlay")
    page.radar_poll.timeout.emit()
    settle(lambda: page.radar_message.text().startswith("Learned 2 cube samples"))
    assert page.radar_message.text() == ("Learned 2 cube samples, 1 background sample. It tells ahead from behind. Hearing "
                                         "a cube ahead, right here (match 50 %).")
    assert not page.radar_cancel.isVisibleTo(page) and page.radar_samples_box.isVisibleTo(page)
    assert "• Background · 2026-11-22 01:02:03" in _texts(page) and "• Cube, facing it · the loudest · with its notes" in _texts(page)
    forget = [b for b in _shown(page, QPushButton) if b.text() == sw.RADAR_FORGET]
    page.radar_poll.timeout.emit()                                                      # the same samples: kept as drawn
    settle(lambda: len(app.sent("GET", "/api/radar")) == reads + 2)
    assert [b for b in _shown(page, QPushButton) if b.text() == sw.RADAR_FORGET] == forget
    forget[1].click()
    settle(lambda: app.sent("POST", "/api/radar"))
    assert app.sent("POST", "/api/radar")[0][2] == {"action": "forget", "sample": "s2"}
    # a learn step asked, then read again; Forget every sample once asked, and the app's refusal said
    _button(page, "3. Learn the cube behind you").click()
    settle(lambda: len(app.sent("POST", "/api/radar")) == 2)
    assert app.sent("POST", "/api/radar")[1][2] == {"action": "learn", "kind": "cube", "facing": "behind"}
    _button(page, sw.RADAR_CLEAR).click()
    assert asked == [sw.RADAR_ASK_CLEAR] and len(app.sent("POST", "/api/radar")) == 2
    _button(page, sw.RADAR_CLEAR).click()
    settle(lambda: page.toast.text() == "The radar is learning")
    # the radar on, then read again 400 ms later; the sensitivity once let go
    page.controls["radar_enabled"].box.setChecked(True)
    settle(lambda: page.radar_timer.isActive())
    assert page.radar_timer.interval() == sw.RADAR_ENABLED_READ_MS
    page.radar_slider.setValue(8)
    settle(lambda: app.sent("POST", "/api/ui")[-1][2] == {"radar_sensitivity": 8})
    page.radar_poll.stop()


def test_the_hotkeys(qapp, home):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from aion2calc.gui.settings_page import key_combo
    app = FakeApp(_answers({("GET", "/api/ui", None): {**server.ui_settings(), "hotkeys": {"toggle_overlay": "Ctrl+Shift+O",
                                                                                           "radar_learn_cube": ""}}}))
    page = _page(home, app)
    page.show_tab("overlay")
    settle(lambda: page.ui)
    fields = page.hotkey_fields
    assert list(fields) == [action for action, _words in sw.HOTKEY_ACTIONS] and len(fields) == 20
    assert fields["toggle_overlay"].text() == "Ctrl+Shift+O" and fields["radar_learn_background"].text() == "Ctrl+1"
    assert fields["radar_learn_cube"].text() == "" and fields["quit"].placeholderText() == sw.HOTKEY_HINT
    assert sw.HOTKEYS_RADAR_NOTE in _texts(page) and any("<strong>Save hotkeys</strong>" in t for t in _texts(page))
    # keys pressed in a field, named as the web page names them
    field = fields["clear_meter"]
    for key, mods, text in ((Qt.Key_Control, Qt.ControlModifier, ""), (Qt.Key_M, Qt.ControlModifier | Qt.ShiftModifier, "\r")):
        field.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, mods, text))
    assert field.text() == "Ctrl+Shift+M"
    field.event(QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.AltModifier, "\t"))
    assert field.text() == "Alt+Tab"
    assert key_combo(Qt.Key_F13, Qt.NoModifier) == "F13" and key_combo(Qt.Key_Escape, Qt.MetaModifier) == "Win+Esc"
    assert key_combo(Qt.Key_Exclam, Qt.ShiftModifier, "!") == "Shift+!" and key_combo(Qt.Key_1, Qt.ControlModifier) == "Ctrl+1"
    assert key_combo(Qt.Key_Shift, Qt.ShiftModifier) is None and key_combo(Qt.Key_VolumeUp, Qt.NoModifier) is None
    # Clear, then saved together: the learn steps even when cleared; a combo bound twice said, nothing sent
    _button(page, sw.HOTKEY_CLEAR, 0).click()
    assert fields["toggle_overlay"].text() == ""
    fields["toggle_meter"].setText("Ctrl+1")
    _button(page, sw.HOTKEYS_SAVE).click()
    assert page.hotkeys_message.text() == "Ctrl+1 is bound to two actions; give each action its own keys."
    assert not app.sent("POST", "/api/ui")
    fields["toggle_meter"].setText("F9")
    _button(page, sw.HOTKEYS_SAVE).click()
    settle(lambda: page.hotkeys_message.text() == "Saved")
    assert app.sent("POST", "/api/ui")[-1][2] == {"hotkeys": {
        "toggle_meter": "F9", "clear_meter": "Alt+Tab", "radar_learn_background": "Ctrl+1", "radar_learn_cube": "",
        "radar_learn_cube_behind": "Ctrl+3", "radar_learn_other": "Ctrl+4"}}
    app.answers[("POST", "/api/ui", None)] = _refused("/api/ui", 400, "ValueError: Unknown hotkey action")
    _button(page, sw.HOTKEYS_SAVE).click()
    settle(lambda: page.hotkeys_message.text() == "ValueError: Unknown hotkey action")
    page.radar_poll.stop()


def test_the_settings_words():
    assert sw.chosen_tab("pettracker") == "pettracker" and sw.chosen_tab(None) == "appearance"
    assert sw.text_scale({"app_text_scale": "120abc"}) == 120 and sw.text_scale({}) == 100
    assert sw.text_scale({"app_text_scale": 105}) == 70 and sw.text_scale({"app_text_scale": 0}) == 100
    assert sw.launch_page({"app_default_page": "maps"}) == "maps" and sw.launch_page({"app_default_page": ""}) == "meter"
    assert sw.database_line({"db": {}}) == "— items · last update never"
    assert sw.database_line({"db": {"items": 3, "last_sync": {"other": 1}}}) == "3 items · last update —"
    assert sw.update_state_text(None) == "· up to date" and sw.update_state_text({"checking": True}) == sw.CHECKING
    assert sw.version({"version": "1", "update": {"version": "2", "url": "u"}})["update"]["words"] == "· version 2 available"
    assert sw.install_words("launch-failed").startswith("The installer helper did not start.")
    assert sw.cleaned({"deleted": 0}) == "Removed 0 files; 0 changed, active, locked or uninspectable files preserved."
    assert sw.maintenance({})["rows"] == [] and sw.maintenance({"groups": [{"bytes": "x"}]})["rows"][0][2] == "NaN"
    notes = sw.patch_notes({"version": "9", "notes": [{"title": "T", "version": "9", "html": "<p>x</p>"}]})
    assert notes["title"] == "What's new in Aion 2 Calc 9" and notes["notes"][0]["html"] == "<p>x</p>"
    # Meter and Server (0.2.476)
    assert sw.record_number({"meter_reset_delay": 0}, "meter_reset_delay") == 5 and sw.record_number({}, "meter_max_records") == 20
    assert sw.log_cache({"meter_log_cache_mb": None}) == 0 and sw.log_cache({"meter_log_cache_mb": "x"}) == 1024
    assert sw.number_check("500", 1, 120) == (None, "Enter a whole number from 1 to 120.") and sw.number_check(7, 1, 120) == (7, "")
    assert sw.log_cache_value(2_000_000) == 1048576 and sw.log_cache_value(-3) == 0 and sw.log_cache_value("127.5") == 128
    assert sw.server_form({})["placeholder"] == sw.SERVER_PLACEHOLDER and sw.server_form({})["visibility"] == "public"
    assert sw.server_versions({"software": {"analyzer": "2"}}) == " · server not reported · analyzer 2"
    assert sw.saved_check({"ok": True}) == "saved · server reachable · runtime versions not reported by this server"
    assert sw.server_check({"ok": False, "detail": "refused"}) == "Check failed: refused"
    # Pet Tracker (0.2.477)
    assert sw.pet_status({})["text"] == sw.PETS_UNSUPPORTED
    started = sw.pet_status({"supported": True, "setup": {"status": "started"}})
    assert started["install"] is True and started["busy"] and started["setup"].startswith("Pet Tracker's installer is running")
    assert sw.pet_status({"supported": True, "installed": {"folder": "X"}})["text"].startswith("Installed, in X. ")
    # Overlay, first part (0.2.478)
    assert sw.shown_number({"overlay_width": "0"}, "overlay_width", 340, "or") == 340
    assert sw.shown_number({"rtss_rows": 0}, "rtss_rows", 5, "finite") == 0 and sw.shown_number({}, "rtss_rows", 5, "finite") == 5
    assert sw.clamped("300", 1, 120, 3) == 120 and sw.clamped("", 1, 120, 3) == 3 and sw.clamped("0", 1, 16, 8) == 8
    assert sw.rtss_status({"supported": True, "enabled": True, "error": "RTSS is not running"}) == "RTSS is not running"
    assert sw.rtss_status({"supported": True, "enabled": True}) == "Waiting for RTSS…" and sw.rtss_status({}).endswith("Windows only.")
    assert sw.stream_url("https://host.example:8443/x/") == "https://host.example:8443/overlay"
    # the radar and the hotkeys (0.2.479)
    assert sw.radar_sensitivity({"radar_sensitivity": "7"}) == 7 and sw.radar_sensitivity({"radar_sensitivity": 2.5}) == 5
    assert sw.radar_status({"supported": True, "error": "no audio device", "model": {}}).endswith("Not listening: no audio device.")
    assert sw.radar_status({"supported": True, "learning": {"kind": "other", "seconds": 2.1}}) == (
        "Listening to a sound that is not a cube… 3 s left.")
    stereo = {"supported": True, "ready": True, "model": {"cubes": 1}, "channels": 2}
    assert sw.radar_learned(stereo) == ("Learned 1 cube sample, no background (step 1 improves it). Learn it behind you too "
                                        "(step 3) to tell ahead from behind.")
    assert sw.radar_sample({"kind": "other", "alike": True}) == "Not a cube · sounds the same as the cube, so it is not used"
    assert sw.hotkeys_to_save({"quit": " ", "radar_learn_other": " "}) == ({"radar_learn_other": ""}, "")


def test_the_image_failures_kept_as_the_web_page_keeps_them():
    image_health.retry()
    for n in range(image_health.LIMIT + 3):
        image_health.failed(f"https://assets.playnccdn.com/icon/{n}.png")
    image_health.failed("https://user:pw@metabot.gg/x.webp")                          # a credential in it: not kept
    image_health.failed("https://metabot.gg:8443/x.webp")
    report = image_health.report()
    assert len(report["failures"]) == image_health.LIMIT and report["evicted_resources"] == 3
    assert report["failures"][0]["host"] == "assets.playnccdn.com" and report["failures"][0]["skill_id"] is None
    assert report["scope"].startswith("This window's lifetime")
    image_health.retry()
    assert image_health.report()["failures"] == [] and image_health.report()["evicted_resources"] == 0


# ------------------------------------------------------------------ the window
def test_the_window_draws_settings_natively(qapp, home):
    window = MainWindow(None, "http://127.0.0.1:8765/", page="settings")
    assert isinstance(window.page("settings"), SettingsPage)
    assert window.pages.currentWidget() is window.page("settings")


def test_whats_new_once_after_an_update(qapp, home):
    app = FakeApp({("POST", "/api/patch-notes", "seen"): {"seen": "0.2.475"}})
    window = MainWindow(None, "http://127.0.0.1:8765/", page="settings")
    window.api = app
    window._notes_read("notes", {**NOTES, "show": False})                              # seen already: nothing shown
    assert getattr(window, "notes_dialog", None) is None
    window._notes_read("notes", NOTES)
    dialog = window.notes_dialog
    assert dialog.isVisible() and dialog.windowTitle() == "What's new in Aion 2 Calc 0.2.475"
    dialog.close_button.click()
    settle(lambda: app.sent("POST", "/api/patch-notes"))
    assert app.sent("POST", "/api/patch-notes") == [("POST", "/api/patch-notes", {"action": "seen"})]


def test_the_window_opens_at_the_text_size(monkeypatch):
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    scale_text(FakeApp({("GET", "/api/ui", None): {"app_text_scale": 120}}))
    assert os.environ["QT_SCALE_FACTOR"] == "1.2"
    monkeypatch.setenv("QT_SCALE_FACTOR", "2")                                         # set by hand: left as it is
    scale_text(FakeApp({("GET", "/api/ui", None): {"app_text_scale": 80}}))
    assert os.environ["QT_SCALE_FACTOR"] == "2"
    monkeypatch.delenv("QT_SCALE_FACTOR")
    scale_text(FakeApp({("GET", "/api/ui", None): {"app_text_scale": 100}}))           # the size it ships with: none
    scale_text(FakeApp())                                                               # the app not answering: none
    assert "QT_SCALE_FACTOR" not in os.environ
