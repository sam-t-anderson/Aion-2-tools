"""The native Settings page (0.2.414), as pages/settings.js draws it since 0.2.475, a part at a time.

- **Its tabs:** Appearance, Overlay, Pet Tracker, Meter, Server, Profiles & backup and App & data, one group of rows
  shown at a time, the one chosen last kept (``a2-settab``) as the web page keeps it in its browser.
- **App & data** is the web page's (settings_words.py has its words): the native interface, the app's own window,
  the text size, performance mode, the page at launch, My Character at launch and the tray; your data's folders; the
  game database with its check, the cached icons' re-index, the image coverage and the pictures read again; the
  storage maintenance; the updates and the version, checked and installed from here; the patch notes; the Discord;
  stopping the app; and the author. The language is the web interface's own, chosen on its Settings page.
- Since 0.2.476 **Meter** (Combat records, its numbers checked and saved as the web page checks them) and **Server**
  (the log server, saved and probed from this computer, and the community stats) too.
- **The other tabs' rows** are still the early ones, drawn from ``settings_schema``: each control saves its one
  setting, and a row the native page does not draw in full yet opens the web Settings page for the rest.

Each control saves its setting through the app's ``/api/ui`` the moment it changes, as the web page's does, and says
so for a moment at the page's foot; the page reads the app's settings, its state and its log server each time it is
shown, as the web page does when it opens.
"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTextBrowser, QVBoxLayout,
                               QWidget)

from . import image_health
from . import settings_words as sw
from . import theme
from .api import AppApi, Job, Requests
from .chrome import FlowLayout
from .combat import js_text
from .database_page import Window
from .pets_page import Toast
from .result_windows import GridTable
from .results import _dict, _truthy
from .settings_schema import ROWS, Bool, Choice

#: What the page reads as it is shown (``pageSettings``): the app's state, its log server and its settings.
READINGS = (("status", "/api/status"), ("server", "/api/logserver"), ("ui", "/api/ui"))
#: How the rows look (app.css ``.settabs``, ``.setrow``): a pill per tab, the chosen one gold.
STYLE = f"""
    QPushButton#settab {{ background: {theme.COLORS['bg2']}; color: {theme.COLORS['muted']};
        border: 1px solid {theme.COLORS['line2']}; border-radius: 15px; padding: 6px 14px; font-weight: 600;
        font-size: 15px; }}
    QPushButton#settab:hover {{ color: {theme.COLORS['gold']}; border-color: {theme.COLORS['gold_dim']}; }}
    QPushButton#settab[on="true"] {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ecd79f, stop:1 #b9984f);
        color: #10131a; border-color: {theme.COLORS['gold_dim']}; }}
    QFrame#setrow {{ border: none; border-bottom: 1px solid {theme.COLORS['line']}; background: transparent; }}
    QFrame#setrow[top="true"] {{ border-top: 1px solid {theme.COLORS['line']}; }}
    QFrame#setrow QWidget {{ background: transparent; }}
    QLabel#setlbl {{ color: {theme.COLORS['muted']}; font-weight: 600; }}
    QLabel#setnote {{ color: {theme.COLORS['muted']}; font-size: 12px; }}
    QLabel#setcode {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; color: {theme.COLORS['gold']}; }}
    QPushButton#small {{ padding: 3px 10px; }}
""" + Toast.STYLE
NARROW = 900                                       # below this width a row's name goes above it (``@media``)
READ_TIMEOUT = 30                                  # the page's readings and saves may take this long (a browser waits)
SLOW_TIMEOUT = 900                                 # an update's download, a scan of the cache: as long as they take


class WrapCheck(QWidget):
    """A checkbox with words that wrap (a ``label`` around an ``input``); a click on the words toggles it too. The
    words may carry a muted part (``<span class="muted">``)."""

    def __init__(self, text: str, parent=None, muted: str = ""):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.box = QCheckBox()
        self.box.setAccessibleName(text)
        self.label = QLabel()
        self.label.setWordWrap(True)
        if muted:
            self.label.setTextFormat(Qt.RichText)
            self.label.setText(f"{_html(text)} <span style='color: {theme.COLORS['muted']};'>{_html(muted)}</span>")
        else:
            self.label.setTextFormat(Qt.PlainText)
            self.label.setText(text)
        self.label.mousePressEvent = lambda _event: self.box.toggle()
        row.addWidget(self.box, 0, Qt.AlignTop)
        row.addWidget(self.label, 1)


def _html(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _note(text: str, indent: int = 0) -> QLabel:
    """A row's note (``p.small.muted``), set in by ``indent`` where the web page sets it in (``margin-left``)."""
    label = QLabel(text)
    label.setObjectName("setnote")
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    if indent:
        label.setContentsMargins(indent, 0, 0, 0)
    return label


def _words(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


def _button(words: str, action) -> QPushButton:
    button = QPushButton(words)
    button.setObjectName("small")
    button.clicked.connect(lambda _checked=False: action())
    return button


def _link(words: str, url: str, open_link) -> QLabel:
    label = QLabel(f"<a href='{_html(url)}' style='color: {theme.COLORS['accent']};'>{_html(words)}</a>")
    label.setTextFormat(Qt.RichText)
    label.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
    label.linkActivated.connect(open_link)
    return label


def _flow(*widgets: QWidget, gap=(14, 10)) -> QWidget:
    """A ``.row``: its parts side by side, on as many lines as the width needs."""
    holder = QWidget()
    flow = FlowLayout(holder, align=Qt.AlignLeft, gap=gap)
    for widget in widgets:
        flow.addWidget(widget)
    return holder


class SetRow(QFrame):
    """A row (``.setrow``): its name in a column of its own, 200 px wide, then its controls; on a narrow page the name
    goes above them."""

    def __init__(self, group: str, title: str, top: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.group, self.title = group, title
        self.setObjectName("setrow")
        self.setProperty("top", top)
        self.line = QHBoxLayout(self)
        self.line.setContentsMargins(0, 10, 0, 10)
        self.line.setSpacing(14)
        self.name = QLabel(title)
        self.name.setObjectName("setlbl")
        self.name.setWordWrap(True)
        self.name.setFixedWidth(200)
        self.line.addWidget(self.name, 0, Qt.AlignTop)
        holder = QWidget()
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(4)
        self.line.addWidget(holder, 1)

    def narrow(self, narrow: bool) -> None:
        self.line.setDirection(QHBoxLayout.TopToBottom if narrow else QHBoxLayout.LeftToRight)
        self.name.setFixedWidth(16777215 if narrow else 200)
        if narrow:
            self.name.setMinimumWidth(0)


class PatchNotes(QDialog):
    """What's new (patch-notes.js ``open``): each version's notes, newest first, then the link to all of them and
    Close. Escape and Close close it; ``closed`` runs once it has."""

    def __init__(self, notes: dict, open_link, parent: QWidget | None = None, closed=None):
        super().__init__(parent)
        self.setWindowTitle(notes["title"])
        self.setModal(True)
        self.resize(720, 640)
        self._closed = closed
        box = QVBoxLayout(self)
        heading = QLabel(notes["title"])
        heading.setObjectName("heading")
        heading.setWordWrap(True)
        box.addWidget(heading)
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(lambda url: open_link(url.toString()))
        self.body.setHtml("".join(f"<h3>{_html(n['title'])} <span style='color: {theme.COLORS['muted']};'>"
                                  f"{_html(n['version'])}</span></h3>{n['html']}" for n in notes["notes"]))
        box.addWidget(self.body, 1)
        foot = QHBoxLayout()
        foot.addWidget(_link(sw.ALL_NOTES, notes["all"] or sw.PATCH_NOTES_URL, open_link))
        foot.addStretch(1)
        self.close_button = QPushButton(sw.CLOSE)
        self.close_button.clicked.connect(self.accept)
        foot.addWidget(self.close_button)
        box.addLayout(foot)
        self.finished.connect(self._done)
        self.close_button.setFocus()

    def _done(self, _result) -> None:
        if self._closed is not None:
            closed, self._closed = self._closed, None
            closed()


def show_patch_notes(api: AppApi | None, parent: QWidget, notes: dict, open_link, seen: bool = False) -> PatchNotes:
    """The notes in their dialog; ``seen`` tells the app once it is closed, so they do not show again."""
    def closed():
        if seen and api is not None:
            requests = Requests(api, parent)
            requests.post("seen", "/api/patch-notes", {"action": "seen"})
    dialog = PatchNotes(notes, open_link, parent, closed=closed)
    dialog.show()
    return dialog


class SettingsPage(QWidget):
    """The Settings page. ``api`` is the app's local API (None in tests); ``open_web(page)`` opens a page of the web
    interface; ``store`` keeps the tab chosen (what the web page keeps in its browser); ``confirm`` asks a question,
    ``save_file`` where a file goes, ``open_link`` opens an address in the browser and ``quit_app`` closes this window
    once the app has stopped."""

    def __init__(self, api: AppApi | None, open_web, parent=None, store=None, confirm=None, save_file=None,
                 open_link=None, quit_app=None):
        super().__init__(parent)
        from .planner_page import interface_store
        self.api, self.open_web = api, open_web
        self.store = store if store is not None else interface_store()
        self.confirm = confirm or self._ask
        self.save_file = save_file or self._ask_where
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.quit_app = quit_app or QApplication.quit
        # the readings, the saves and the quick actions; the long ones (an update's download, a scan of the cache, the
        # image coverage, the patch notes) on a queue of their own, so a save never waits behind them
        self.requests = Requests(api, self, timeout=READ_TIMEOUT) if api is not None else None
        self.slow = Requests(api, self, timeout=SLOW_TIMEOUT) if api is not None else None
        for queue in (self.requests, self.slow):
            if queue is not None:
                queue.replied.connect(self._replied)
                queue.failed.connect(self._failed)
        self.job = Job(api, self) if api is not None else None          # the cached icons' re-index
        if self.job is not None:
            self.job.logged.connect(lambda log: self.asset_message.setText(js_text(log[-1]) if log else sw.REINDEX_RUNNING))
            self.job.done.connect(self._reindexed)
            self.job.failed.connect(self._reindex_failed)
        self.status: dict = {}
        self.server: dict = {}
        self.ui: dict = {}
        self.controls: dict[str, QWidget] = {}          # each setting's control, by its key
        self.rows: list[SetRow] = []
        self.saved: list[tuple[str, object]] = []        # what this page saved, latest last
        self.notes_dialog: PatchNotes | None = None
        self._pending: dict[str, QTimer] = {}
        self._latest: dict[str, object] = {}
        self._loading = False
        self.tab = sw.chosen_tab(self.store.value(sw.TAB_KEY))
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll)
        content = QWidget()
        self.scroll.setWidget(content)
        page = QVBoxLayout(content)
        page.setContentsMargins(24, 20, 24, 20)
        self.frame = Window("Settings")
        page.addWidget(self.frame)
        page.addStretch(1)
        tabs = QWidget()
        tabs_flow = FlowLayout(tabs, align=Qt.AlignLeft, gap=(6, 6))
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, words in sw.TABS:
            button = QPushButton(words)
            button.setObjectName("settab")
            button.setAccessibleName(words)
            button.clicked.connect(lambda _checked=False, key=key: self.show_tab(key))
            tabs_flow.addWidget(button)
            self.tab_buttons[key] = button
        self.frame.body.addWidget(tabs)
        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {theme.COLORS['line']};")
        self.frame.body.addWidget(rule)
        self._build()
        self.toast = Toast(self)
        self.show_tab(self.tab)

    # ------------------------------------------------------------------ building
    def _build(self) -> None:
        system = {"Native interface": self._native, "Open as its own window": self._app_window,
                  "Text size": self._text_size, "Performance mode": self._performance, "Language": self._language,
                  "Page at launch": self._launch, "My Character at launch": self._character,
                  "Collapse to tray": self._tray, "Your data": self._data, "Game database": self._database,
                  "Storage maintenance": self._maintenance, "Updates": self._updates, "Version": self._version,
                  "Patch notes": self._patch_notes, "Community": self._community, "Stop the app": self._quit,
                  "Author": self._author}
        drawn = {("system", title): build for title, build in system.items()}
        drawn.update({("meter", "Combat records"): self._records, ("server", "Log server"): self._log_server,
                      ("server", "Community stats"): self._community_stats})
        schema = {(row.group, row.title): row for row in ROWS}
        for group, title in sw.ROW_ORDER:
            row = SetRow(group, title, top=title == "Author")
            if (group, title) in drawn:
                drawn[(group, title)](row)
            else:
                self._schema_row(row, schema[(group, title)])
            self.frame.body.addWidget(row)
            self.rows.append(row)

    def _check(self, row: SetRow, key: str, words: str, muted: str = "", saved: str = sw.SAVED) -> WrapCheck:
        """A checkbox saving ``key`` as it changes, with what the web page says once it is saved."""
        widget = WrapCheck(words, muted=muted)
        widget.box.toggled.connect(lambda on, key=key, saved=saved: self.save(key, bool(on), saved))
        self.controls[key] = widget
        row.body.addWidget(widget)
        return widget

    def _native(self, row: SetRow) -> None:
        self._check(row, "interface_native", sw.NATIVE)
        row.body.addWidget(_note(sw.NATIVE_NOTE))

    def _app_window(self, row: SetRow) -> None:
        self._check(row, "app_window", sw.APP_WINDOW)
        row.body.addWidget(_note(sw.APP_WINDOW_NOTE))

    def _text_size(self, row: SetRow) -> None:
        box = QComboBox()
        box.setAccessibleName(sw.TEXT_LABEL)
        for size in sw.TEXT_SCALES:
            box.addItem(f"{size}%", size)
        box.currentIndexChanged.connect(lambda _i, b=box: self.save("app_text_scale", int(b.currentData() or 100)))
        self.controls["app_text_scale"] = box
        row.body.addWidget(_flow(_words(sw.TEXT_LABEL), box, gap=(4, 4)))
        row.body.addWidget(_note(sw.TEXT_NOTE))
        row.body.addWidget(_note(sw.TEXT_NATIVE))

    def _performance(self, row: SetRow) -> None:
        self._check(row, "performance_mode", sw.PERFORMANCE, sw.OFF_BY_DEFAULT)
        row.body.addWidget(_note(sw.PERFORMANCE_NOTE))

    def _language(self, row: SetRow) -> None:
        row.body.addWidget(_flow(_words(sw.LANGUAGE_WEB, "setnote"),
                                 _button(sw.OPEN_WEB_SETTINGS, lambda: self.open_web("settings"))))

    def _launch(self, row: SetRow) -> None:
        box = QComboBox()
        box.setAccessibleName(sw.LAUNCH_LABEL)
        for key, words in sw.LAUNCH_PAGES:
            box.addItem(words, key)
        box.currentIndexChanged.connect(lambda _i, b=box: self.save("app_default_page", b.currentData()))
        self.controls["app_default_page"] = box
        row.body.addWidget(_flow(_words(sw.LAUNCH_LABEL), box, gap=(4, 4)))
        row.body.addWidget(_note(sw.LAUNCH_NOTE))

    def _character(self, row: SetRow) -> None:
        self._check(row, "character_auto_open", sw.CHARACTER_OPEN, sw.OFF_BY_DEFAULT)
        row.body.addWidget(_note(sw.CHARACTER_NOTE))
        self._check(row, "character_auto_refresh", sw.CHARACTER_REFRESH, sw.CHARACTER_REFRESH_DEFAULT)

    def _tray(self, row: SetRow) -> None:
        self._check(row, "tray_on_close", sw.TRAY, saved=sw.SAVED_NEXT_LAUNCH)

    def _data(self, row: SetRow) -> None:
        self.home = _words("", "setcode")
        self.home.setTextInteractionFlags(Qt.TextSelectableByMouse)
        buttons = [_button(words, lambda what=what: self.open_folder(what)) for what, words in sw.FOLDERS]
        row.body.addWidget(_flow(self.home, *buttons, gap=(6, 4)))

    def _database(self, row: SetRow) -> None:
        self.database = _words("")
        self.sync_button = _button(sw.CHECK_NOW, self.sync)
        self.reindex_button = _button(sw.REINDEX, self.reindex)
        self.export_button = _button(sw.EXPORT_IMAGES, self.export_images)
        self.retry_button = _button(sw.RETRY_IMAGES, self.retry_images)
        self.asset_message = _words("", "setnote")
        row.body.addWidget(_flow(self.database, self.sync_button, self.reindex_button, self.export_button,
                                 self.retry_button, self.asset_message, gap=(6, 4)))

    def _maintenance(self, row: SetRow) -> None:
        self.inspect_button = _button(sw.INSPECT, self.inspect)
        self.clean_buttons = {"caches": _button(sw.CLEAN_CACHE, lambda: self.clean("caches")),
                              "updates": _button(sw.CLEAN_UPDATES, lambda: self.clean("updates"))}
        row.body.addWidget(_flow(self.inspect_button, *self.clean_buttons.values(), gap=(14, 10)))
        row.body.addWidget(_note(sw.MAINTENANCE_NOTE))
        self.storage_message = _words("")
        self.storage_message.setAccessibleName("Storage maintenance status")
        row.body.addWidget(self.storage_message)
        holder = QWidget()
        self.maintenance_box = QVBoxLayout(holder)
        self.maintenance_box.setContentsMargins(0, 0, 0, 0)
        self.maintenance_box.setSpacing(6)
        row.body.addWidget(holder)

    def _updates(self, row: SetRow) -> None:
        self._check(row, "auto_update", sw.AUTO_UPDATE)
        self._check(row, "update_on_close", sw.UPDATE_ON_CLOSE)
        row.body.addWidget(_note(sw.UPDATES_NOTE))

    def _version(self, row: SetRow) -> None:
        holder = QWidget()
        self.version_box = QHBoxLayout(holder)
        self.version_box.setContentsMargins(0, 0, 0, 0)
        row.body.addWidget(holder)
        self.update_message = _words("", "setnote")
        self.update_button: QPushButton | None = None
        self.check_button: QPushButton | None = None
        self.update_state: QLabel | None = None

    def _patch_notes(self, row: SetRow) -> None:
        self.notes_message = _words("", "setnote")
        row.body.addWidget(_flow(_button(sw.WHATS_NEW, self.whats_new), _link(sw.ALL_NOTES, sw.PATCH_NOTES_URL, self.open_link),
                                 self.notes_message, gap=(14, 10)))
        row.body.addWidget(_note(sw.PATCH_NOTE))

    def _community(self, row: SetRow) -> None:
        row.body.addWidget(_flow(_link(sw.DISCORD, sw.DISCORD_URL, self.open_link), _words(sw.DISCORD_REST.strip()),
                                 gap=(4, 4)))

    def _quit(self, row: SetRow) -> None:
        row.body.addWidget(_flow(_button(sw.QUIT, self.quit)))

    def _author(self, row: SetRow) -> None:
        row.body.addWidget(_words(sw.AUTHOR, "muted"))

    # ---------------------------------------------------------------- Meter (0.2.476)
    def _records(self, row: SetRow) -> None:
        """Combat records: the live meter's resets, the records kept and uploaded, what is shared, the dummy's parse."""
        checks = {key: (words, muted, saved) for key, words, muted, _on, saved in sw.RECORD_CHECKS}

        def check(key):
            words, muted, saved = checks[key]
            self._check(row, key, words, muted, saved or sw.SAVED)
        check("meter_reset_after_battle")
        check("meter_reset_on_boss_start")
        self.records_message = _words("", "setnote")
        self.records_message.setAccessibleName("Combat records status")
        row.body.addWidget(_flow(self._record_number("meter_reset_delay"), self._record_number("meter_max_records"),
                                 self.records_message, gap=(14, 10)))
        check("meter_save_records")
        words, unit, low, high, _shown = sw.LOG_CACHE
        box = self._spin("meter_log_cache_mb", words, low, high, step=128)
        box.valueChanged.connect(self._save_log_cache)
        self.log_cache_message = _words("", "setnote")
        self.log_cache_message.setAccessibleName("Logs folder status")
        self._log_cache_clear = QTimer(self)
        self._log_cache_clear.setSingleShot(True)
        self._log_cache_clear.timeout.connect(lambda: self.log_cache_message.setText(""))
        row.body.addWidget(_flow(_flow(_words(words), box, _words(unit), gap=(4, 4)), self.log_cache_message,
                                 gap=(14, 10)))
        row.body.addWidget(_note(sw.LOG_CACHE_NOTE, indent=14))
        check("meter_upload_before_prune")
        row.body.addWidget(_note(sw.PRUNE_NOTE, indent=14))
        for key in ("meter_autostart", "meter_show_server_name", "meter_auto_upload", "meter_catch_up_uploads",
                    "meter_upload_per_fight"):
            check(key)
        row.body.addWidget(_note(sw.PER_FIGHT_NOTE, indent=14))
        for key, note in (("meter_report_boss_kills", sw.BOSS_KILLS_NOTE), ("meter_report_enemy_hp", sw.ENEMY_HP_NOTE),
                          ("share_gathering", sw.GATHERING_NOTE), ("meter_report_diagnostics", sw.DIAGNOSTICS_NOTE)):
            check(key)
            row.body.addWidget(_note(note, indent=14))
        check("meter_show_dummy_parse")
        row.body.addWidget(_flow(self._record_number("meter_dummy_record_seconds")))
        row.body.addWidget(_note(sw.RECORDS_NOTE))

    def _spin(self, key: str, words: str, low: int, high: int, step: int = 1) -> QSpinBox:
        """A number field (``input type=number``) that tells its value once it is typed and left, or stepped."""
        box = QSpinBox()
        box.setRange(low, high)
        box.setSingleStep(step)
        box.setKeyboardTracking(False)                 # ``change``: once typed and left, or at each step
        box.setAccessibleName(words)
        self.controls[key] = box
        return box

    def _record_number(self, key: str) -> QWidget:
        """One of the numbers checked before they are saved (``saveRecNum``), its words around it."""
        words, unit, low, high, _shown = sw.RECORD_NUMBERS[key]
        box = self._spin(key, words, low, high)
        box.valueChanged.connect(lambda value, key=key: self._save_number(key, value))
        return _flow(_words(words), box, _words(unit), gap=(4, 4))

    def _save_number(self, key: str, value) -> None:
        if self._loading:
            return
        _words_, _unit, low, high, _shown = sw.RECORD_NUMBERS[key]
        number, why = sw.number_check(value, low, high)
        if number is None:
            self.records_message.setText(why)
            return
        self.saved.append((key, number))
        self.ui[key] = number
        if self.requests is None:
            self.records_message.setText(sw.SAVED)
            return
        self.requests.post(f"number:{key}", "/api/ui", {key: number})

    def _save_log_cache(self, value) -> None:
        """The logs folder's cap, kept within its bounds, then said for a moment (``#rec-logcache``)."""
        if self._loading:
            return
        number = sw.log_cache_value(value)
        self.saved.append(("meter_log_cache_mb", number))
        self.ui["meter_log_cache_mb"] = number
        if self.requests is None:
            self._log_cache_said(number)
            return
        self.requests.post(f"cache:{number}", "/api/ui", {"meter_log_cache_mb": number})

    def _log_cache_said(self, number: int) -> None:
        self.log_cache_message.setText(sw.log_cache_saved(number))
        self._log_cache_clear.start(2500)

    # ---------------------------------------------------------------- Server (0.2.476)
    def _log_server(self, row: SetRow) -> None:
        """The log server uploads go to: its address, its upload key, who sees the uploads; saved and checked."""
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText(sw.SERVER_PLACEHOLDER)
        self.server_url.setAccessibleName("Log server address")
        self.server_url.setMinimumWidth(320)
        self.server_key = QLineEdit()
        self.server_key.setEchoMode(QLineEdit.Password)
        self.server_key.setPlaceholderText(sw.KEY_OPTIONAL)
        self.server_key.setAccessibleName("Upload key")
        self.server_key.setMinimumWidth(229)
        self.server_visibility = QComboBox()
        for value, words in sw.VISIBILITIES:
            self.server_visibility.addItem(words, value)
        self.server_visibility.setAccessibleName(sw.VISIBILITY_LABEL)
        self.server_visibility.setToolTip(sw.VISIBILITY_TIP)
        self.server_save = _button(sw.SAVE, self.save_server)
        self.server_check_button = _button(sw.CHECK_SERVER, self.check_server)
        self.server_message = _words("", "setnote")
        self.server_message.setAccessibleName("Log server status")
        row.body.addWidget(_flow(self.server_url, self.server_key, self.server_visibility, self.server_save,
                                 self.server_check_button, self.server_message, gap=(14, 10)))
        self.server_default = _note(sw.DEFAULT_SERVER)
        self.server_default.setVisible(False)
        row.body.addWidget(self.server_default)

    def _community_stats(self, row: SetRow) -> None:
        self._check(row, "community_heartbeat", sw.HEARTBEAT)
        row.body.addWidget(_note(sw.HEARTBEAT_NOTE))
        self._check(row, "community_contribute_character", sw.CONTRIBUTE)
        row.body.addWidget(_note(sw.CONTRIBUTE_NOTE))

    def apply_server(self, server) -> None:
        """The log server's form as the page opens (``srv``)."""
        self.server = _dict(server)
        form = sw.server_form(self.server)
        self.server_url.setText(form["url"])
        self.server_url.setPlaceholderText(form["placeholder"])
        self.server_key.setPlaceholderText(form["key"])
        index = self.server_visibility.findData(form["visibility"])
        self.server_visibility.setCurrentIndex(index)               # none of them: none chosen, as a list shows it
        self.server_default.setVisible(form["default"])

    def save_server(self) -> None:
        """The log server saved, then probed from this computer (``#ssave``)."""
        if self.requests is None:
            return
        visibility = self.server_visibility.currentData() if self.server_visibility.currentIndex() >= 0 else ""
        self.requests.post("server-save", "/api/logserver", {"url": self.server_url.text(),
                                                             "key": self.server_key.text() or None,
                                                             "visibility": visibility})

    def check_server(self) -> None:
        """The saved server probed (``#scheck``)."""
        if self.slow is None:
            return
        self.server_check_button.setEnabled(False)
        self.server_message.setText(sw.CHECKING_SERVER)
        self.slow.get("server-check", "/api/logserver/check")

    # the rows of the tabs not drawn as the web page draws them yet (settings_schema)
    def _schema_row(self, row: SetRow, spec) -> None:
        for control in spec.controls:
            row.body.addWidget(self._control(control))
        if spec.web:
            row.body.addWidget(_flow(_words("More of this setting is on the web Settings page for now." if spec.controls
                                            else "This setting is on the web Settings page for now.", "muted"),
                                     _button("Open the web Settings page", lambda: self.open_web("settings"))))

    def _control(self, control) -> QWidget:
        if isinstance(control, Bool):
            widget = WrapCheck(control.label)
            widget.box.toggled.connect(lambda on, key=control.key: self.save(key, bool(on)))
            self.controls[control.key] = widget
            return widget
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        if control.label:
            row.addWidget(QLabel(control.label))
        if isinstance(control, Choice):
            box = QComboBox()
            for value, text in control.options:
                box.addItem(text, value)
            box.currentIndexChanged.connect(lambda _i, key=control.key, b=box, cast=control.cast:
                                            self.save(key, cast(b.currentData())))
        else:
            box = QSpinBox()
            box.setRange(control.minimum, control.maximum)
            if control.unit:
                box.setSuffix(" " + control.unit)
            box.valueChanged.connect(lambda value, key=control.key: self._save_later(key, int(value)))
        row.addWidget(box)
        row.addStretch(1)
        self.controls[control.key] = box
        return holder

    # ------------------------------------------------------------------ the tabs
    def show_tab(self, key: str) -> None:
        """One group of rows (``data-settab``), the choice kept."""
        self.tab = sw.chosen_tab(key)
        self.store.setValue(sw.TAB_KEY, self.tab)
        for name, button in self.tab_buttons.items():
            button.setProperty("on", name == self.tab)
            button.style().unpolish(button)
            button.style().polish(button)
        for row in self.rows:
            row.setVisible(row.group == self.tab)

    def resizeEvent(self, event) -> None:
        narrow = event.size().width() < NARROW
        for row in self.rows:
            row.narrow(narrow)
        super().resizeEvent(event)

    # ------------------------------------------------------------------ reading
    def start(self) -> None:
        """What the page shows, read from the app (``pageSettings``)."""
        if self.requests is None:
            return
        for name, path in READINGS:
            self.requests.get(name, path)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not event.spontaneous():
            self.start()

    def _replied(self, name: str, answer) -> None:
        kind, _, key = name.partition(":")
        if kind == "status":
            self.apply_status(answer)
        elif kind == "server":
            self.apply_server(answer)
        elif kind == "number":
            self.records_message.setText(sw.SAVED)
        elif kind == "cache":
            self._log_cache_said(int(key))
        elif kind == "server-save":
            self.server_message.setText(sw.SAVED_CHECKING)
            self.slow.get("server-saved", "/api/logserver/check")
        elif kind == "server-saved":
            self.server_message.setText(sw.saved_check(answer))
        elif kind == "server-check":
            self.server_check_button.setEnabled(True)
            self.server_message.setText(sw.server_check(answer))
        elif kind == "ui":
            self.apply(_dict(answer))
        elif kind == "save":
            self.toast.say(key.partition("|")[2] or sw.SAVED)
        elif kind == "open" and _truthy(_dict(answer).get("error")):
            self.toast.say(js_text(answer["error"]))
        elif kind == "sync":
            self.toast.say(sw.SYNCING)
        elif kind == "assets":
            self._export(answer)
        elif kind == "maintenance":
            self._show_maintenance(answer)
        elif kind == "clean":
            self.clean_buttons[key].setEnabled(True)
            self.storage_message.setText(sw.cleaned(answer))
            self.inspect()
        elif kind == "check":
            if self.check_button is not None:
                self.check_button.setEnabled(True)
            if _truthy(_dict(answer).get("update")):
                self.requests.get("status", "/api/status")          # a release is out: Update now
            elif self.update_state is not None:
                self.update_state.setText(sw.update_state_text(_dict(answer).get("update_state")))
        elif kind == "update":
            self._updated(_dict(answer))
        elif kind == "notes":
            self._notes(answer)
        elif kind == "quit":
            self.quit_app()

    def _failed(self, name: str, why: str) -> None:
        kind, _, key = name.partition(":")
        if kind == "save":
            self.toast.say(f"Could not save it: {why}")
        elif kind == "number":
            self.records_message.setText(why)
        elif kind in ("cache", "server-save"):                     # the web page says nothing; the page says why
            self.toast.say(f"Could not save it: {why}")
        elif kind == "server-saved":
            self.server_message.setText(sw.saved_unchecked(why))
        elif kind == "server-check":
            self.server_check_button.setEnabled(True)
            self.server_message.setText(why)
        elif kind == "open":
            self.toast.say(why)
        elif kind == "assets":
            self.export_button.setEnabled(True)
            self.asset_message.setText(sw.images_failed(why))
        elif kind == "maintenance":
            self._clear(self.maintenance_box)
            self.maintenance_box.addWidget(_words(why))
        elif kind == "clean":
            self.clean_buttons[key].setEnabled(True)
            self.storage_message.setText(why)
        elif kind == "check":
            if self.check_button is not None:
                self.check_button.setEnabled(True)
            if self.update_state is not None:
                self.update_state.setText(sw.check_failed(why))
        elif kind == "update":
            self.update_message.setText(why)
            if self.update_button is not None:
                self.update_button.setEnabled(True)
        elif kind == "notes":
            self.notes_message.setText(why)
        elif kind == "quit":
            self.quit_app()                                        # stopped or not, the web page goes too

    def apply_status(self, status) -> None:
        """The app's state: your data's folder, the game database's line, the version and its update."""
        self.status = _dict(status)
        self.home.setText(js_text(self.status.get("home")))
        self.database.setText(sw.database_line(self.status))
        self._draw_version()

    def _draw_version(self) -> None:
        self._clear(self.version_box)
        v = sw.version(self.status)
        parts: list[QWidget] = [_words(f"Aion 2 Calc {v['version']}")]
        self.update_button = self.check_button = self.update_state = None
        if v["update"] is not None:
            parts.append(_words(v["update"]["words"]))
            self.update_button = _button(sw.UPDATE_NOW, self.install_update)
            parts += [self.update_button, _link(sw.RELEASE_NOTES, v["update"]["url"], self.open_link)]
        else:
            self.update_state = _words(v["state"], "muted")
            self.check_button = _button(sw.CHECK_NOW, self.check_update)
            parts += [self.update_state, self.check_button]
        self.update_message = _words("", "setnote")
        parts.append(self.update_message)
        holder = _flow(*parts, gap=(6, 4))
        self.version_box.addWidget(holder, 1)

    def apply(self, ui: dict) -> None:
        """Show the app's settings (its answer to ``/api/ui``) without saving them back."""
        self.ui = dict(ui)
        self._loading = True
        try:
            on = {"interface_native": ui.get("interface_native") is not False, "app_window": ui.get("app_window") is not False,
                  "performance_mode": ui.get("performance_mode") is True,
                  "character_auto_open": ui.get("character_auto_open") is True,
                  "character_auto_refresh": ui.get("character_auto_refresh") is True,
                  "tray_on_close": _truthy(ui.get("tray_on_close")), "auto_update": ui.get("auto_update") is not False,
                  "update_on_close": ui.get("update_on_close") is not False}
            for key, _words_, _muted, default_on, _saved in sw.RECORD_CHECKS:
                on[key] = ui.get(key) is not False if default_on else ui.get(key) is True
            on["community_heartbeat"] = ui.get("community_heartbeat") is not False
            on["community_contribute_character"] = ui.get("community_contribute_character") is not False
            for key, value in on.items():
                self.controls[key].box.setChecked(value)
            self._choose(self.controls["app_text_scale"], sw.text_scale(ui))
            self._choose(self.controls["app_default_page"], sw.launch_page(ui))
            for key in sw.RECORD_NUMBERS:
                self.controls[key].setValue(sw.record_number(ui, key))
            self.controls["meter_log_cache_mb"].setValue(sw.log_cache(ui))
            for spec in ROWS:
                for control in spec.controls:
                    widget, value = self.controls[control.key], ui.get(control.key)
                    if isinstance(control, Bool):
                        widget.box.setChecked(value is True)
                    elif isinstance(control, Choice):
                        index = widget.findData(value)
                        if index < 0 and value is not None:
                            index = widget.findData(control.cast(value)) if _castable(control.cast, value) else -1
                        if index >= 0:
                            widget.setCurrentIndex(index)
                    elif isinstance(value, (int, float)) and not isinstance(value, bool):
                        widget.setValue(int(value))
        finally:
            self._loading = False

    @staticmethod
    def _choose(box: QComboBox, value) -> None:
        index = box.findData(value)
        box.setCurrentIndex(index if index >= 0 else 0)

    # ------------------------------------------------------------------ saving
    def _save_later(self, key: str, value) -> None:
        """A number saves once its field has been still for a moment, not at every keystroke."""
        if self._loading:
            return
        self._latest[key] = value
        timer = self._pending.get(key)
        if timer is None:
            timer = self._pending[key] = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(400)
            timer.timeout.connect(lambda key=key: self.save(key, self._latest[key]))
        timer.start()

    def save(self, key: str, value, saved: str = sw.SAVED) -> None:
        """One setting saved through the app's ``/api/ui``, as the web page saves it, then said (``toast``)."""
        if self._loading:
            return
        self.saved.append((key, value))
        self.ui[key] = value
        if self.requests is None:
            self.toast.say(saved)
            return
        self.requests.post(f"save:{key}|{saved}", "/api/ui", {key: value})

    # ------------------------------------------------------------------ App & data's actions
    def open_folder(self, what: str) -> None:
        """One of your data's folders opened by the app (``data-open``)."""
        if self.requests is not None:
            self.requests.post(f"open:{what}", "/api/open", {"what": what})

    def sync(self) -> None:
        """The game database checked for updates (``#sync``)."""
        if self.requests is not None:
            self.requests.post("sync", "/api/sync", {})

    def reindex(self) -> None:
        """The cached official icons re-indexed, as a job (``#asset-reindex``)."""
        if self.job is None or self.job.running:
            return
        self.reindex_button.setEnabled(False)
        self.asset_message.setText(sw.REINDEXING)
        self.job.start("/api/assets/reindex", {})

    def _reindexed(self, result) -> None:
        self.reindex_button.setEnabled(True)
        self.asset_message.setText(sw.reindexed(result))
        self.toast.say(sw.REINDEXED_TOAST)

    def _reindex_failed(self, why: str) -> None:
        self.reindex_button.setEnabled(True)
        self.asset_message.setText(sw.reindex_failed(why))

    def export_images(self) -> None:
        """The app's image coverage and this window's picture failures saved to a file (``#asset-report``)."""
        if self.requests is None:
            return
        self.export_button.setEnabled(False)
        self.asset_message.setText(sw.COLLECTING)
        self.slow.get("assets", "/api/assets")

    def _export(self, data) -> None:
        self.export_button.setEnabled(True)
        report = {**_dict(data), "browser_images": image_health.report()}
        path = self.save_file(sw.IMAGES_FILE)
        if not path:
            self.asset_message.setText("")
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(report, file, indent=2)
        except OSError as problem:
            self.asset_message.setText(sw.images_failed(str(problem)))
        else:
            self.asset_message.setText(sw.images_saved(path))

    def retry_images(self) -> None:
        """Every picture that could not be read asked for again when next shown (``#retry-images``)."""
        image_health.retry()
        self.asset_message.setText(sw.RETRIED)

    def inspect(self) -> None:
        """The managed cache and update files listed (``showMaintenance``)."""
        if self.requests is None:
            return
        self._clear(self.maintenance_box)
        self.maintenance_box.addWidget(_words(sw.INSPECTING))
        self.slow.get("maintenance", "/api/maintenance")

    def _show_maintenance(self, answer) -> None:
        m = sw.maintenance(answer)
        self._clear(self.maintenance_box)
        self.maintenance_box.addWidget(_note(m["note"]))
        if m["external"]:
            self.maintenance_box.addWidget(_words(sw.EXTERNAL_CACHE))
        if m["truncated"]:
            self.maintenance_box.addWidget(_words(sw.SCAN_LIMIT))
        self.maintenance_box.addWidget(GridTable(sw.MAINTENANCE_COLUMNS, m["rows"], {0: 3, 4: 3}, left=True))

    def clean(self, action: str) -> None:
        """Old disposable cache or old update files removed (``#storage-cache``, ``#storage-updates``)."""
        if self.requests is None:
            return
        self.clean_buttons[action].setEnabled(False)
        self.storage_message.setText(sw.CLEANING)
        self.slow.post(f"clean:{action}", "/api/maintenance", {"action": action})

    def check_update(self) -> None:
        """The latest release checked again (``#chkupd``)."""
        if self.requests is None or self.check_button is None:
            return
        self.check_button.setEnabled(False)
        if self.update_state is not None:
            self.update_state.setText(sw.CHECKING)
        self.slow.post("check", "/api/update/check", {})

    def install_update(self) -> None:
        """The newer version installed (``#instupd``): downloaded and checked first when it is not ready."""
        if self.requests is None or self.update_button is None:
            return
        self.update_button.setEnabled(False)
        ready = _dict(self.status.get("update_download")).get("state") == "ready"
        self.update_message.setText(sw.OPENING_INSTALLER if ready else sw.DOWNLOADING)
        self.slow.post("update", "/api/update", {})

    def _updated(self, answer: dict) -> None:
        if answer.get("status") == "launching":
            self._closing()
            return
        if self.update_button is not None:
            self.update_button.setEnabled(True)
        self.update_message.setText(sw.install_words(answer.get("status")))

    def _closing(self) -> None:
        """The app closes for its installer: the page says so in place of everything (the web page's body)."""
        self.scroll.takeWidget().deleteLater()
        closing = _words(sw.CLOSING, "muted")
        closing.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        closing.setContentsMargins(0, 160, 0, 0)
        self.scroll.setWidget(closing)

    def whats_new(self) -> None:
        """This version's notes (``#whatsnew``), whatever was seen."""
        if self.requests is not None:
            self.notes_message.setText("")
            self.slow.get("notes", "/api/patch-notes?force=1")

    def _notes(self, answer) -> None:
        notes = sw.patch_notes(answer)
        if not notes["notes"]:
            self.notes_message.setText(sw.NO_NOTES)
            return
        self.notes_dialog = show_patch_notes(self.api, self, notes, self.open_link)

    def quit(self) -> None:
        """The app stopped once asked (``#quit``), then this window closed."""
        if not self.confirm(sw.ASK_QUIT):
            return
        if self.requests is None:
            self.quit_app()
            return
        self.requests.post("quit", "/api/quit", {})

    # ------------------------------------------------------------------ helpers
    def _ask(self, words: str) -> bool:
        return QMessageBox.question(self, "Aion 2 Calc", words) == QMessageBox.Yes

    def _ask_where(self, name: str) -> str:
        """Where a file is saved, the computer's Downloads folder offered (where a browser puts a download)."""
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, "Export", os.path.join(folder, name), "JSON (*.json)")
        return path

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget() is not None:
                child.widget().deleteLater()

    def sizeHint(self) -> QSize:
        return QSize(1000, 800)


def _castable(cast, value) -> bool:
    try:
        cast(value)
        return True
    except (TypeError, ValueError):
        return False
