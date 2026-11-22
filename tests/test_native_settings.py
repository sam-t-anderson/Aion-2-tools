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
DRAWN_KEYS = SYSTEM_KEYS + RECORD_KEYS + SERVER_KEYS
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
    assert len(ROWS) == 19 and len(CONTROLS) == 69                     # App & data's, Meter's and Server's drawn here
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
    assert {row.group for row in ROWS} <= {key for key, _title in GROUPS} - {"system", "meter", "server"}
    assert [key for key, _title in GROUPS] == [key for key, _title in sw.TABS]
    for key in DRAWN_KEYS:                                                             # the drawn rows' saves too
        assert key in defaults, key
    for key, (_words, _unit, low, high, shown) in {**sw.RECORD_NUMBERS, "meter_log_cache_mb": sw.LOG_CACHE}.items():
        assert low <= defaults[key] <= high and low <= shown <= high, key
    drawn = {r for r in sw.ROW_ORDER if r[0] in ("system", "meter", "server")}
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
    page.controls["overlay_width"].setValue(500)
    page.controls["overlay_width"].setValue(520)                                       # typed on: saved once, when still
    clock = QElapsedTimer()
    clock.start()
    while len(page.saved) < 5 and clock.elapsed() < 3000:
        QCoreApplication.processEvents()
    assert page.saved[4:] == [("overlay_width", 520)] and page.toast.text() == "Saved"


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
    assert {row.title for row in web} >= {"Hotkeys (Windows)", "Settings backup", "Overlay colors & fonts"}
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
    assert {(m, p) for m, p, _b in app.calls} == {("GET", "/api/status"), ("GET", "/api/logserver"), ("GET", "/api/ui")}
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
