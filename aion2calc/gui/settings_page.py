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
- Since 0.2.477 **Pet Tracker**: whether it is installed and how it is doing, its install and update, its use with
  the app, its overlay and the folder of a copy unpacked by hand.
- Since 0.2.478 the first half of **Overlay**: the live meter overlay (with the event sound), In-game (RTSS) with its
  state, the streaming address to copy, and the overlay's layout.
- Since 0.2.479 the **Hidden Cube radar** (its learn steps, its sensitivity, what it hears and its samples, read twice
  a second while shown) and the **Hotkeys**, each action's keys pressed in its field and saved together.
- Since 0.2.480 the rest of **Overlay** (settings_looks.py has its words): the text's colours and the fonts, the text
  effects and each element's own font, the background image with its sliders and auto-contrast, and the look presets,
  the web page's starter presets and your own, applied, saved, deleted, and copied or pasted as share codes.
- Since 0.2.481 the **Combat class colors** (the log review's own panel) and the **Settings backup**, exported to a file
  in your data folder or imported from one.
- **The other rows** (the theme, the accent colour and the customization profiles) are still on the web Settings page,
  which the row opens.

Each control saves its setting through the app's ``/api/ui`` the moment it changes, as the web page's does, and says
so where the web page says it; the page reads the app's settings, its state and its log server each time it is shown,
as the web page does when it opens, and its rows' words start afresh, as the web page's do when it draws itself again.
"""
from __future__ import annotations

import base64
import json
import os

from PySide6.QtCore import QEvent, QSize, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
                               QSlider, QSpinBox, QTextBrowser, QVBoxLayout, QWidget)

from . import image_health
from . import settings_looks as looks
from . import settings_words as sw
from . import theme
from .api import AppApi, Job, Requests
from .chrome import FlowLayout
from .combat import js_text
from .database_page import Window
from .pets_page import Toast
from .result_windows import GridTable
from .results import _dict, _truthy
from .settings_schema import ROWS

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


def _inline(text: str) -> QLabel:
    """A control's words beside it, on one line (a ``label``'s text in a ``.row``)."""
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
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


#: Keys named as the web page names them (``comboFromEvent``'s ``NAMED``).
_KEY_NAMES = {Qt.Key_Space: "Space", Qt.Key_Escape: "Esc", Qt.Key_Up: "Up", Qt.Key_Down: "Down", Qt.Key_Left: "Left",
              Qt.Key_Right: "Right", Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter", Qt.Key_Tab: "Tab",
              Qt.Key_Backtab: "Tab", Qt.Key_Backspace: "Backspace", Qt.Key_Delete: "Delete", Qt.Key_Insert: "Insert",
              Qt.Key_Home: "Home", Qt.Key_End: "End", Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown"}
_MODIFIER_KEYS = (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_Super_L, Qt.Key_Super_R, Qt.Key_AltGr)


def key_combo(key: int, modifiers, text: str = "") -> str | None:
    """A key press as the web page writes it (``comboFromEvent``): Ctrl, Alt, Shift and Win, then the key; None for a
    modifier alone or a key it does not name."""
    if key in _MODIFIER_KEYS:
        return None
    mods = [name for flag, name in ((Qt.ControlModifier, "Ctrl"), (Qt.AltModifier, "Alt"), (Qt.ShiftModifier, "Shift"),
                                    (Qt.MetaModifier, "Win")) if modifiers & flag]
    if key in _KEY_NAMES:
        name = _KEY_NAMES[key]
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        name = f"F{key - Qt.Key_F1 + 1}"
    elif len(text) == 1 and text.isprintable() and text != " ":
        name = text.upper()
    elif 0x21 <= key <= 0x7E:                          # with Ctrl the event's text is a control character
        name = chr(key).upper()
    else:
        return None
    return "+".join(mods + [name])


class HotkeyEdit(QLineEdit):
    """A hotkey's capture field (``hotkey-input``): it shows the keys pressed in it, Tab and Esc too."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def event(self, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(event)                  # the web page keeps Tab for the field too
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        combo = key_combo(event.key(), event.modifiers(), event.text())
        if combo:
            self.setText(combo)
        event.accept()


class ColourPick(QPushButton):
    """A colour picker (``input type="color"``): its colour as a swatch. A click asks for another (``ask(start, words)``,
    a ``QColor`` or None), and ``picked`` tells one other than the colour it had, as the picker's ``change`` does."""

    picked = Signal(str)

    def __init__(self, words: str, ask, parent: QWidget | None = None):
        super().__init__(parent)
        self.words, self.ask, self.value = words, ask, ""
        self.setAccessibleName(words)
        self.setFixedSize(44, 22)
        self.clicked.connect(lambda _checked=False: self.choose())
        self.set_value("#000000")

    def set_value(self, colour: str) -> None:
        """The colour shown, told to nobody."""
        self.value = colour
        self.setToolTip(colour)
        self.setStyleSheet(f"QPushButton {{ background: {colour}; border: 1px solid {theme.COLORS['line2']}; "
                           "border-radius: 3px; }")

    def choose(self) -> None:
        chosen = self.ask(self.value, self.words)
        if chosen is None or not chosen.isValid():
            return
        colour = chosen.name().lower()
        if colour != self.value:
            self.set_value(colour)
            self.picked.emit(colour)


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
                 open_link=None, quit_app=None, open_page=None):
        super().__init__(parent)
        from .planner_page import interface_store
        self.api, self.open_web = api, open_web
        self.open_page = open_page or open_web           # another page of the window (the Pet Tracker page)
        self.store = store if store is not None else interface_store()
        self.confirm = confirm or self._ask
        self.save_file = save_file or self._ask_where
        self.choose_sound = self._ask_sound                # where the event sound's file is (a test hands one over)
        self.choose_image = self._ask_image                # where the overlay background's image is
        self.choose_backup = self._ask_backup              # a settings file to import
        self.ask_text = self._ask_text                     # a name or a share code asked for (``prompt``)
        self.ask_colour = lambda start, words: QColorDialog.getColor(QColor(start), self, words)
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
        # the rows drawn from settings_words' descriptions: each control's key and how it reads the app's value
        self.data_checks: list[tuple[str, str]] = []
        self.data_numbers: list[tuple[str, int, str]] = []
        self.data_selects: list[tuple[str, str]] = []
        self.number_messages: dict[str, QLabel] = {}     # a checked number's row's words (``#ov-layout-msg``)
        self.controls: dict[str, QWidget] = {}          # each setting's control, by its key
        self.rows: list[SetRow] = []
        self.saved: list[tuple[str, object]] = []        # what this page saved, latest last
        self.notes_dialog: PatchNotes | None = None
        # the overlay's look (0.2.480): each row's words, its checkboxes and colours, each element's own font, and the
        # settings of a shared preset being saved
        self.look_messages: dict[str, QLabel] = {}
        self.look_checks: list[str] = []
        self.look_colours: list[tuple[str, str]] = []
        self.element_fonts: dict = {}
        self.shared_settings: dict = {}
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
                      ("server", "Community stats"): self._community_stats, ("pettracker", "Pet Tracker"): self._pets,
                      ("pettracker", "Use Pet Tracker"): self._use_pets,
                      ("pettracker", "Pet Tracker overlay"): self._pet_overlay,
                      ("pettracker", "Pet Tracker folder"): self._pet_folder,
                      ("overlay", "Live meter overlay"): lambda row: self._items(row, sw.LIVE_OVERLAY),
                      ("overlay", "In-game (RTSS)"): lambda row: self._items(row, sw.RTSS),
                      ("overlay", "Streaming (OBS / Discord)"): self._streaming,
                      ("overlay", "Overlay layout"): lambda row: self._items(row, sw.LAYOUT),
                      ("overlay", "Hidden Cube radar"): self._radar, ("overlay", "Hotkeys (Windows)"): self._hotkeys,
                      ("overlay", "Overlay colors & fonts"): self._look_colours,
                      ("overlay", "Overlay text effects & per-element fonts"): self._look_effects,
                      ("overlay", "Overlay background"): self._look_background,
                      ("overlay", "Overlay look presets"): self._look_presets,
                      ("backup", "Settings backup"): self._backup,
                      ("appearance", "Combat class colors"): self._class_colours})
        on_the_web = {(row.group, row.title) for row in ROWS}
        for group, title in sw.ROW_ORDER:
            row = SetRow(group, title, top=title == "Author")
            if (group, title) in drawn:
                drawn[(group, title)](row)
            elif (group, title) in on_the_web:
                self._on_the_web(row)
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

    # ---------------------------------------------------------------- Pet Tracker (0.2.477)
    def _pets(self, row: SetRow) -> None:
        """What Pet Tracker is, whether it is installed and how it is doing, and its install or update (``ptStatus``)."""
        intro = QLabel(f"{_html(sw.PET_INTRO)}<a href='pets' style='color: {theme.COLORS['accent']};'>"
                       f"{_html(sw.PET_PAGE)}</a>.")
        intro.setTextFormat(Qt.RichText)
        intro.setWordWrap(True)
        intro.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        intro.linkActivated.connect(lambda _page: self.open_page("pets"))
        row.body.addWidget(intro)
        holder = QWidget()
        self.pet_box = QVBoxLayout(holder)
        self.pet_box.setContentsMargins(0, 0, 0, 0)
        self.pet_box.setSpacing(4)
        self.pet_box.addWidget(_words(sw.CHECKING_PETS, "setnote"))
        row.body.addWidget(holder)
        self.pet_note = _words("")
        self.pet_note.setAccessibleName("Pet Tracker update")
        row.body.addWidget(self.pet_note)
        self.pet_timer = QTimer(self)
        self.pet_timer.setSingleShot(True)
        self.pet_timer.timeout.connect(self.read_pets)

    def _use_pets(self, row: SetRow) -> None:
        self._check(row, "pettracker_enabled", sw.USE_PETS, sw.WINDOWS_OFF)
        row.body.addWidget(_note(sw.USE_PETS_NOTE))

    def _pet_overlay(self, row: SetRow) -> None:
        check = WrapCheck(sw.PET_OVERLAY)
        check.box.toggled.connect(lambda on: self.save("pettracker_overlay", bool(on)))
        self.controls["pettracker_overlay"] = check
        style = QComboBox()
        style.setAccessibleName(sw.PET_WINDOW_LABEL)
        for value, words in sw.PET_WINDOWS:
            style.addItem(words, value)
        style.currentIndexChanged.connect(lambda _i, b=style: self.save("pettracker_overlay_style", b.currentData()))
        self.controls["pettracker_overlay_style"] = style
        row.body.addWidget(_flow(check, style, gap=(14, 10)))
        row.body.addWidget(_note(sw.PET_OVERLAY_NOTE))

    def _pet_folder(self, row: SetRow) -> None:
        self.pet_folder = QLineEdit()
        self.pet_folder.setPlaceholderText(sw.PET_FOLDER_HINT)
        self.pet_folder.setAccessibleName(sw.PET_FOLDER_LABEL)
        self.pet_folder.setMinimumWidth(380)
        self.pet_folder_message = _words("", "setnote")
        self.pet_folder_message.setAccessibleName("Pet Tracker folder status")
        row.body.addWidget(_flow(self.pet_folder, _button(sw.SAVE, self.save_pet_folder), self.pet_folder_message,
                                 gap=(14, 10)))
        row.body.addWidget(_note(sw.PET_FOLDER_NOTE))

    def read_pets(self) -> None:
        """Pet Tracker's state (``/api/pettracker``)."""
        self.pet_timer.stop()
        if self.requests is not None:
            self.requests.get("pets", "/api/pettracker")

    def _pets_shown(self, state) -> None:
        self._clear(self.pet_box)
        status = sw.pet_status(state)
        if status["install"] is None:
            self.pet_box.addWidget(_words(status["text"], "setnote"))
        else:
            install = _button(sw.INSTALL_PETS, lambda: self.pet_control("install"))
            install.setEnabled(status["install"])
            self.pet_install = install
            self.pet_box.addWidget(_flow(_words(status["text"], "setnote"), install,
                                         _words(status["setup"], "setnote"), gap=(6, 4)))
            self.pet_box.addWidget(_words(sw.PET_INSTALL_NOTE, "setnote"))
        if status["notice"] is not None:
            words, button_words, link = status["notice"]
            notice = QFrame()
            notice.setObjectName("note")
            line = QHBoxLayout(notice)
            line.setContentsMargins(8, 6, 8, 6)
            line.addWidget(_words(words))
            if button_words:
                line.addWidget(_button(button_words, lambda: self.pet_control("update")))
            else:
                line.addWidget(_link("Download it from Pet Tracker's releases", link, self.open_link))
            line.addStretch(1)
            self.pet_box.addWidget(notice)
        if status["busy"]:
            self.pet_timer.start(2000)

    def pet_control(self, action: str) -> None:
        """Pet Tracker installed or updated (``A2Pets.control``)."""
        if self.requests is not None:
            self.requests.post(f"pet:{action}", "/api/pettracker", {"action": action})

    def save_pet_folder(self) -> None:
        """The folder of a copy of Pet Tracker unpacked by hand, saved; then its state read again."""
        if self.requests is not None:
            self.requests.post("pet-folder", "/api/ui", {"pettracker_path": self.pet_folder.text().strip()})

    # ---------------------------------------------------------------- Overlay, first part (0.2.478)
    def _items(self, row: SetRow, items) -> None:
        """A row described in settings_words (its checkboxes, notes, number fields and lists), drawn as the web page's
        template draws it."""
        for item in items:
            kind = item[0]
            if kind == "check":
                row.body.addWidget(self._data_check(item))
            elif kind == "note":
                _kind, text, indent, rich = item
                label = _note(text, indent)
                if rich:
                    label.setTextFormat(Qt.RichText)
                row.body.addWidget(label)
            elif kind == "row":
                _kind, controls, indent, message = item
                parts = [self._data_control(control, message) for control in controls]
                if message:
                    words = _words("", "setnote")
                    words.setAccessibleName("Overlay layout status")
                    self.number_messages[message] = words
                    parts.append(words)
                holder = _flow(*parts, gap=(10, 6))
                holder.setContentsMargins(indent, 0, 0, 0)
                row.body.addWidget(holder)
            elif kind == "check-number":
                _kind, box_item, number_item = item
                holder = _flow(self._data_check(box_item), self._data_control(number_item, "layout"), gap=(6, 4))
                row.body.addWidget(holder)
            elif kind == "sound":
                self._sound(row)
            elif kind == "rtss-status":
                self.rtss_message = _note(sw.RTSS_UNKNOWN, indent=22)
                self.rtss_message.setAccessibleName("RTSS status")
                row.body.addWidget(self.rtss_message)
                self.rtss_timer = QTimer(self)
                self.rtss_timer.setSingleShot(True)
                self.rtss_timer.timeout.connect(self.read_rtss)

    def _data_check(self, item) -> WrapCheck:
        _kind, key, words, muted, rule, saved, tip, indent = item
        widget = WrapCheck(words, muted=muted)
        if tip:
            widget.setToolTip(tip)
        if indent:
            widget.setContentsMargins(indent, 0, 0, 0)
        widget.box.toggled.connect(lambda on, key=key, saved=saved: self.save(key, bool(on), saved))
        self.controls[key] = widget
        self.data_checks.append((key, rule))
        return widget

    def _data_control(self, control, message: str = "") -> QWidget:
        """A number field or a list with its words around it (a ``label`` in a ``.row``)."""
        if control[0] == "select":
            _kind, key, before, options, fallback = control
            box = QComboBox()
            box.setAccessibleName(before)
            for value, words in options:
                box.addItem(words, value)
            box.currentIndexChanged.connect(lambda _i, key=key, b=box: self.save(key, b.currentData()))
            self.controls[key] = box
            self.data_selects.append((key, fallback))
            return _flow(_words(before), box, gap=(4, 4))
        _kind, key, before, after, low, high, fallback, shown, save, step, muted, name = control
        box = self._spin(key, name, low, high, step=step)
        if save == "checked":
            box.valueChanged.connect(lambda value, key=key, low=low, high=high, message=message:
                                     self._save_checked(key, value, low, high, message))
        else:
            box.valueChanged.connect(lambda value, key=key, low=low, high=high, fallback=fallback:
                                     self.save(key, sw.clamped(value, low, high, fallback)))
        self.data_numbers.append((key, fallback, shown))
        parts = [w for w in (_words(before) if before else None, box, _words(after) if after else None) if w is not None]
        if muted:
            parts.append(_words(muted, "setnote"))
        return _flow(*parts, gap=(4, 4))

    def _save_checked(self, key: str, value, low: int, high: int, message: str) -> None:
        """A number checked before it is saved (``saveLayoutNum``), said beside its row."""
        if self._loading:
            return
        words = self.number_messages.get(message)
        number, why = sw.number_check(value, low, high)
        if number is None:
            if words is not None:
                words.setText(why)
            return
        self.saved.append((key, number))
        self.ui[key] = number
        if self.requests is None:
            if words is not None:
                words.setText(sw.SAVED)
            return
        self.requests.post(f"checked:{key}|{message}", "/api/ui", {key: number})

    def _sound(self, row: SetRow) -> None:
        """The event notification's sound: a file of your own uploaded, tried, or the built-in chime again."""
        self.sound_message = _words(sw.SOUND_BUILT_IN, "setnote")
        self.sound_message.setAccessibleName("Event sound status")
        holder = _flow(_button(sw.SOUND_UPLOAD, self.upload_sound), _button(sw.SOUND_TEST, QApplication.beep),
                       _button(sw.SOUND_DEFAULT, self.clear_sound), self.sound_message, gap=(6, 4))
        holder.setContentsMargins(22, 0, 0, 0)
        row.body.addWidget(holder)
        row.body.addWidget(_note(sw.SOUND_NATIVE, indent=22))

    def upload_sound(self) -> None:
        """A short sound of your own for the event notification (``#ov-events-sound-file``): 1 MB at most."""
        path = self.choose_sound()
        if not path:
            return
        try:
            size = os.path.getsize(path)
        except OSError as problem:
            self.sound_message.setText(str(problem))
            return
        if size > 1024 * 1024:
            self.sound_message.setText(sw.SOUND_TOO_BIG)
            return
        self.sound_message.setText(sw.SOUND_UPLOADING)
        try:
            with open(path, "rb") as file:
                raw = file.read()
        except OSError:
            self.sound_message.setText(sw.SOUND_READ_FAILED)
            return
        import base64
        kind = sw.SOUND_TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        data = f"data:{kind};base64,{base64.b64encode(raw).decode('ascii')}"
        if self.requests is not None:
            self.requests.post("sound", "/api/overlay/event-sound", {"data": data})

    def clear_sound(self) -> None:
        if self.requests is not None:
            self.requests.post("sound-clear", "/api/overlay/event-sound", {"clear": True})

    def _ask_sound(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, sw.SOUND_UPLOAD, "", "Audio (*.mp3 *.ogg *.wav *.webm)")
        return path

    def read_rtss(self) -> None:
        """RTSS's state (``rtssStatus``)."""
        self.rtss_timer.stop()
        if self.requests is not None:
            self.requests.get("rtss", "/api/rtss")

    def _streaming(self, row: SetRow) -> None:
        """The overlay's address for an OBS browser source, to copy."""
        base = getattr(self.api, "base", "") or "http://127.0.0.1:8765/"
        self.stream_url = QLineEdit(sw.stream_url(base))
        self.stream_url.setReadOnly(True)
        self.stream_url.setAccessibleName(sw.STREAM_LABEL)
        self.stream_url.setMinimumWidth(343)
        self.stream_message = _words("", "setnote")
        self.stream_message.setAccessibleName("Streaming status")
        self._stream_clear = QTimer(self)
        self._stream_clear.setSingleShot(True)
        self._stream_clear.timeout.connect(lambda: self.stream_message.setText(""))
        row.body.addWidget(_flow(self.stream_url, _button(sw.STREAM_COPY, self.copy_stream), self.stream_message,
                                 gap=(14, 10)))
        for text in sw.STREAM_NOTES:
            label = _note(text)
            label.setTextFormat(Qt.RichText)
            row.body.addWidget(label)

    def copy_stream(self) -> None:
        """The address copied (``#ov-stream-copy``), said for 2 s."""
        self.stream_url.selectAll()
        QApplication.clipboard().setText(self.stream_url.text())
        self.stream_message.setText(sw.STREAM_COPIED)
        self._stream_clear.start(2000)

    # ---------------------------------------------------------------- Overlay: the Hidden Cube radar (0.2.479)
    def _radar(self, row: SetRow) -> None:
        """The radar: on or off, its learn steps, its sensitivity, what it is doing and its samples, read twice a second
        while the tab shows it (``radarStatus``)."""
        self._check(row, "radar_enabled", sw.RADAR_ON, sw.WINDOWS_OFF)
        note = _note(sw.RADAR_NOTE, indent=22)
        note.setTextFormat(Qt.RichText)
        row.body.addWidget(note)
        buttons = [_button(words, lambda body=body: self.radar_control(body)) for words, body in sw.RADAR_LEARN]
        self.radar_cancel = _button(sw.RADAR_CANCEL, lambda: self.radar_control({"action": "cancel"}))
        self.radar_cancel.setVisible(False)
        clear = _button(sw.RADAR_CLEAR, self.radar_clear)
        self.radar_slider = QSlider(Qt.Horizontal)
        self.radar_slider.setRange(1, 10)
        self.radar_slider.setTracking(False)            # ``change``: once let go, or at each step
        self.radar_slider.setFixedWidth(110)
        self.radar_slider.setAccessibleName(sw.RADAR_SENSITIVITY)
        self.radar_slider.valueChanged.connect(lambda value: self.save("radar_sensitivity", sw.clamped(value, 1, 10, 5)))
        self.controls["radar_sensitivity"] = self.radar_slider
        line = _flow(*buttons, self.radar_cancel, clear, _flow(_words(sw.RADAR_SENSITIVITY), self.radar_slider, gap=(4, 4)),
                     gap=(6, 6))
        line.setContentsMargins(22, 0, 0, 0)
        row.body.addWidget(line)
        self.radar_message = _note(sw.RADAR_UNKNOWN, indent=22)
        self.radar_message.setAccessibleName("Radar status")
        row.body.addWidget(self.radar_message)
        holder = QWidget()
        holder.setAccessibleName(sw.RADAR_SAMPLES)
        self.radar_samples = QVBoxLayout(holder)
        self.radar_samples.setContentsMargins(40, 0, 0, 0)
        self.radar_samples.setSpacing(2)
        self.radar_samples_box = holder
        holder.setVisible(False)
        row.body.addWidget(holder)
        self.radar_shown_samples = None                 # the samples drawn, rebuilt only when they change
        self.radar_notes = _note("", indent=22)
        self.radar_notes.setTextFormat(Qt.RichText)
        row.body.addWidget(self.radar_notes)
        self.radar_timer = QTimer(self)
        self.radar_timer.setSingleShot(True)
        self.radar_timer.timeout.connect(self.read_radar)
        self.radar_poll = QTimer(self)
        self.radar_poll.setInterval(sw.RADAR_POLL_MS)
        self.radar_poll.timeout.connect(lambda: self.read_radar() if self.radar_message.isVisible() else None)

    def read_radar(self) -> None:
        self.radar_timer.stop()
        if self.requests is not None:
            self.requests.get("radar", "/api/radar")

    def radar_control(self, body: dict) -> None:
        """A learn step, Cancel, Forget every sample or a sample's Forget (``radarControl``), then the radar read again."""
        if self.requests is not None:
            self.requests.post("radar-control", "/api/radar", body)

    def radar_clear(self) -> None:
        if self.confirm(sw.RADAR_ASK_CLEAR):
            self.radar_control({"action": "clear"})

    def _radar_shown(self, state) -> None:
        r = _dict(state)
        self.radar_cancel.setVisible(_truthy(r.get("learning")))
        self.radar_message.setText(sw.radar_status(r))
        samples = r.get("samples") if isinstance(r.get("samples"), list) else []
        key = json.dumps(samples, sort_keys=True, default=str)
        if key == self.radar_shown_samples:
            return                                      # kept as they are, so a Forget button keeps its focus
        self.radar_shown_samples = key
        self._clear(self.radar_samples)
        for sample in samples:
            forget = _button(sw.RADAR_FORGET, lambda sample=sample: self.radar_control(
                {"action": "forget", "sample": _dict(sample).get("id")}))
            forget.setAccessibleName("Forget this sample")
            self.radar_samples.addWidget(_flow(_words("• " + sw.radar_sample(sample)), forget, gap=(6, 2)))
        self.radar_samples_box.setVisible(bool(samples))

    # ---------------------------------------------------------------- Overlay: Hotkeys (0.2.479)
    def _hotkeys(self, row: SetRow) -> None:
        """A capture field per action (``hotkey-rows``): its keys pressed, cleared, then all saved together."""
        self.hotkey_fields: dict[str, HotkeyEdit] = {}
        for action, words in sw.HOTKEY_ACTIONS:
            label = _words(words)
            label.setMinimumWidth(230)
            field = HotkeyEdit()
            field.setPlaceholderText(sw.HOTKEY_HINT)
            field.setAccessibleName(words)
            field.setFixedWidth(206)
            self.hotkey_fields[action] = field
            clear = _button(sw.HOTKEY_CLEAR, field.clear)
            row.body.addWidget(_flow(label, field, clear, gap=(8, 2)))
        row.body.addWidget(_note(sw.HOTKEYS_RADAR_NOTE))
        self.hotkeys_message = _words("", "setnote")
        self.hotkeys_message.setAccessibleName("Hotkeys status")
        row.body.addWidget(_flow(_button(sw.HOTKEYS_SAVE, self.save_hotkeys), self.hotkeys_message, gap=(14, 6)))
        note = _note(sw.HOTKEYS_NOTE)
        note.setTextFormat(Qt.RichText)
        row.body.addWidget(note)

    def save_hotkeys(self) -> None:
        """Every action's keys saved together (``#hotkeys-save``), once no combo is bound twice."""
        hotkeys, clash = sw.hotkeys_to_save({action: field.text() for action, field in self.hotkey_fields.items()})
        if clash:
            self.hotkeys_message.setText(clash)
            return
        self.hotkeys_message.setText(sw.HOTKEYS_SAVING)
        self.saved.append(("hotkeys", hotkeys))
        if self.requests is None:
            self.hotkeys_message.setText(sw.SAVED)
            return
        self.requests.post("hotkeys", "/api/ui", {"hotkeys": hotkeys})

    # ---------------------------------------------------------------- Overlay: the look (0.2.480)
    def _look_message(self, kind: str, name: str) -> QLabel:
        """A look row's words (``#ov-color-msg``, ``#ov-font-msg`` …), where its saves are said."""
        words = _words("", "setnote")
        words.setAccessibleName(name)
        self.look_messages[kind] = words
        return words

    def _colour_pick(self, key: str, words: str) -> ColourPick:
        pick = ColourPick(words, lambda start, words: self.ask_colour(start, words))
        self.controls[key] = pick
        return pick

    def _look_item(self, item, message: str) -> QWidget:
        """A checkbox or a colour of the font line or the effects' line, saved and said where the fonts are
        (``saveFont``)."""
        kind, key, words, extra = item
        if kind == "check":
            widget = WrapCheck(words)
            if extra:
                widget.setToolTip(extra)
            widget.box.toggled.connect(lambda on, key=key: self._save_look(message, {key: bool(on)}))
            self.controls[key] = widget
            self.look_checks.append(key)
            return widget
        pick = self._colour_pick(key, words)
        pick.picked.connect(lambda colour, key=key: self._save_look(message, {key: colour}))
        self.look_colours.append((key, extra))
        return _flow(_inline(words), pick, gap=(4, 4))

    def _look_colours(self, row: SetRow) -> None:
        """The text's colours with Reset number colors; then the overlay's font, size and weight, its glow, the bars'
        colours, the outline and the colour cycle (``Overlay colors & fonts``)."""
        self.text_colours: dict[str, ColourPick] = {}
        parts = []
        for element, words in looks.TEXT_COLOURS:
            pick = ColourPick(words, lambda start, words: self.ask_colour(start, words))
            pick.picked.connect(lambda _colour: self.save_text_colours())
            self.text_colours[element] = pick
            parts.append(_flow(_inline(words), pick, gap=(4, 4)))
        parts += [_button(looks.COLOURS_RESET, self.reset_text_colours),
                  self._look_message("colour", "Overlay colors status")]
        row.body.addWidget(_flow(*parts, gap=(14, 10)))
        self.font_family = QComboBox()
        self.font_family.setAccessibleName(looks.FONT)
        for family in looks.FONTS:
            self.font_family.addItem(family or looks.DEFAULT_FONT, family)
        self.font_family.currentIndexChanged.connect(
            lambda _i: self._save_look("font", {"overlay_font_family": self.font_family.currentData()}))
        self.controls["overlay_font_family"] = self.font_family
        scale = self._spin("overlay_font_scale", looks.SIZE, 80, 160)
        scale.valueChanged.connect(self._save_font_scale)
        self.font_weight = QComboBox()
        self.font_weight.setAccessibleName(looks.WEIGHT)
        for weight in looks.WEIGHTS:
            self.font_weight.addItem(str(weight), weight)
        self.font_weight.currentIndexChanged.connect(
            lambda _i: self._save_look("font", {"overlay_font_weight": self.font_weight.currentData()}))
        self.controls["overlay_font_weight"] = self.font_weight
        line = [_flow(_inline(looks.FONT), self.font_family, gap=(4, 4)),
                _flow(_inline(looks.SIZE), scale, _inline("%"), gap=(4, 4)),
                _flow(_inline(looks.WEIGHT), self.font_weight, gap=(4, 4))]
        line += [self._look_item(item, "font") for item in looks.FONT_LINE]
        line.append(self._look_message("font", "Overlay fonts status"))
        row.body.addWidget(_flow(*line, gap=(14, 10)))
        row.body.addWidget(_note(looks.COLOURS_NOTE))

    def save_text_colours(self) -> None:
        """Every text colour saved together as one is chosen (``saveOverlayColors``)."""
        self._save_look("colour", {"overlay_text_colors": {element: pick.value
                                                           for element, pick in self.text_colours.items()}})

    def reset_text_colours(self) -> None:
        """The rate's and the total's colours as the overlay's own, then every colour saved (``#ov-color-reset``)."""
        for element in looks.RESET_COLOURS:
            self.text_colours[element].set_value(looks.TEXT_DEFAULTS[element])
        self.save_text_colours()

    def _save_font_scale(self, value) -> None:
        """The overlay's text size (``#ov-font-scale``), saved when it is 80–160 %."""
        if self._loading:
            return
        number = sw.parse_int(value)
        if number is None or not 80 <= number <= 160:
            self.look_messages["font"].setText(looks.SIZE_RANGE)
            return
        self._save_look("font", {"overlay_font_scale": number})

    def _look_effects(self, row: SetRow) -> None:
        """The halo, its colour and the retroreflection, said where the fonts are; then each element's own font, size and
        weight, with Reset element (``Overlay text effects & per-element fonts``)."""
        row.body.addWidget(_flow(*[self._look_item(item, "font") for item in looks.EFFECTS], gap=(14, 10)))
        self.element = QComboBox()
        self.element.setAccessibleName(looks.ELEMENT)
        for value, words in looks.ELEMENTS:
            self.element.addItem(words, value)
        self.element.currentIndexChanged.connect(lambda _i: self.load_element())
        self.element_family = QComboBox()
        self.element_family.setAccessibleName("Element font")
        for family in looks.FONTS:
            self.element_family.addItem(family or looks.INHERIT, family)
        self.element_size = QSpinBox()
        self.element_size.setRange(79, 160)                       # 79: none (the field left empty), shown as auto
        self.element_size.setSpecialValueText(looks.AUTO_SIZE)
        self.element_size.setKeyboardTracking(False)
        self.element_size.setAccessibleName("Element size")
        self.element_weight = QComboBox()
        self.element_weight.setAccessibleName("Element weight")
        self.element_weight.addItem(looks.AUTO, "")
        for weight in looks.WEIGHTS:
            self.element_weight.addItem(str(weight), weight)
        self.element_family.currentIndexChanged.connect(lambda _i: self.save_element())
        self.element_size.valueChanged.connect(lambda _value: self.save_element())
        self.element_weight.currentIndexChanged.connect(lambda _i: self.save_element())
        row.body.addWidget(_flow(_flow(_inline(looks.ELEMENT), self.element, gap=(4, 4)),
                                 _flow(_inline(looks.FONT), self.element_family, gap=(4, 4)),
                                 _flow(_inline(looks.SIZE), self.element_size, _inline("%"), gap=(4, 4)),
                                 _flow(_inline(looks.WEIGHT), self.element_weight, gap=(4, 4)),
                                 _button(looks.ELEMENT_RESET, self.reset_element),
                                 self._look_message("element", "Element fonts status"), gap=(14, 10)))
        row.body.addWidget(_note(looks.ELEMENTS_NOTE))

    def load_element(self) -> None:
        """The chosen element's font, size and weight shown in their fields (``feLoad``), nothing saved. A font or
        weight none of the list's shows none, as a list given a value it lacks does."""
        family, scale, weight = looks.element_shown(self.element_fonts, self.element.currentData())
        was, self._loading = self._loading, True
        try:
            self.element_family.setCurrentIndex(self.element_family.findData(family))
            self.element_size.setValue(self.element_size.minimum() if scale is None else int(scale))
            self.element_weight.setCurrentIndex(0 if weight is None else next(
                (i for i in range(1, self.element_weight.count()) if self.element_weight.itemData(i) == weight), -1))
        finally:
            self._loading = was

    def save_element(self) -> None:
        """The chosen element's font saved from its fields (``feSave``): what of it is set, or the element left out when
        none is; every element's sent together."""
        if self._loading:
            return
        family = self.element_family.currentData() if self.element_family.currentIndex() >= 0 else ""
        size = self.element_size.value()
        scale = None if size == self.element_size.minimum() else size
        if scale is not None and not 80 <= scale <= 160:
            self.look_messages["element"].setText(looks.SIZE_RANGE)
            return
        weight = self.element_weight.currentData() if self.element_weight.currentIndex() > 0 else None
        entry = looks.element_entry(family or "", scale, weight)
        element = self.element.currentData()
        if entry:
            self.element_fonts[element] = entry
        else:
            self.element_fonts.pop(element, None)
        self._save_look("element", {"overlay_text_fonts": dict(self.element_fonts)})

    def reset_element(self) -> None:
        """The chosen element's own font forgotten, its fields emptied, then saved (``#ov-fe-clear``)."""
        self.element_fonts.pop(self.element.currentData(), None)
        self.load_element()
        self.save_element()

    def _look_background(self, row: SetRow) -> None:
        """The image behind the overlay's card, chosen or removed; its visibility, zoom and darkening; and the text's
        auto-contrast (``Overlay background``)."""
        self.bg_message = self._look_message("background", "Overlay background status")
        row.body.addWidget(_flow(_button(looks.BG_CHOOSE, self.choose_background),
                                 _button(looks.BG_REMOVE, self.remove_background), self.bg_message, gap=(14, 10)))
        numbers = []
        for key, words, low, high, _shown_, _rule in looks.BG_NUMBERS:
            box = self._spin(key, words, low, high)
            box.valueChanged.connect(lambda value, key=key, low=low, high=high:
                                     self._save_background_number(key, value, low, high))
            numbers.append(_flow(_inline(words), box, _inline("%"), gap=(4, 4)))
        row.body.addWidget(_flow(*numbers, gap=(14, 10)))
        box = QComboBox()
        box.setAccessibleName(looks.AUTOCONTRAST)
        for value, words in looks.AUTOCONTRASTS:
            box.addItem(words, value)
        box.currentIndexChanged.connect(lambda _i, b=box: self.save("overlay_text_autocontrast", b.currentData()))
        self.controls["overlay_text_autocontrast"] = box
        row.body.addWidget(_flow(_flow(_inline(looks.AUTOCONTRAST), box, gap=(4, 4))))
        note = _note(looks.BG_NOTE)
        note.setTextFormat(Qt.RichText)
        row.body.addWidget(note)

    def _save_background_number(self, key: str, value, low: int, high: int) -> None:
        """A background number (``saveBgNum``): saved when it is within its limits, then said."""
        if self._loading:
            return
        number = sw.parse_int(value)
        if number is None or not low <= number <= high:
            self.look_messages["background"].setText(looks.bg_range(low, high))
            return
        self._save_look("background", {key: number}, saying="")

    def choose_background(self) -> None:
        """An image of your own behind the overlay's card (``#ov-bg-file``): 8 MB at most, sent as a data address, as
        the web page's ``FileReader`` reads it."""
        path = self.choose_image()
        if not path:
            return
        words = self.look_messages["background"]
        try:
            size = os.path.getsize(path)
        except OSError as problem:
            words.setText(str(problem))
            return
        if size > looks.BG_LIMIT:
            words.setText(looks.BG_TOO_BIG)
            return
        words.setText(looks.BG_UPLOADING)
        try:
            with open(path, "rb") as file:
                raw = file.read()
        except OSError:
            words.setText(looks.BG_READ_FAILED)
            return
        kind = looks.BG_TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        if self.requests is not None:
            self.requests.post("background", "/api/overlay/background",
                               {"data": f"data:{kind};base64,{base64.b64encode(raw).decode('ascii')}"})

    def remove_background(self) -> None:
        if self.requests is not None:
            self.requests.post("background-clear", "/api/overlay/background", {"clear": True})

    def _ask_image(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, looks.BG_CHOOSE, "", looks.BG_FILES)
        return path

    def _look_presets(self, row: SetRow) -> None:
        """The presets' list, with Apply, Save current look as…, Delete, Copy share code and Paste a shared code…
        (``Overlay look presets``)."""
        self.preset_box = QComboBox()
        self.preset_box.setAccessibleName(looks.PRESET)
        self.preset_box.setMinimumWidth(229)
        self.preset_box.currentIndexChanged.connect(lambda _i: self.preset_chosen())
        self._list_presets({})
        row.body.addWidget(_flow(self.preset_box, _button(looks.APPLY, self.apply_preset),
                                 _button(looks.SAVE_AS, self.save_preset), _button(looks.DELETE, self.delete_preset),
                                 _button(looks.COPY, self.copy_preset), _button(looks.PASTE, self.paste_preset),
                                 self._look_message("preset", "Overlay look presets status"), gap=(14, 10)))
        note = _note(looks.PRESETS_NOTE)
        note.setTextFormat(Qt.RichText)
        row.body.addWidget(note)

    def _list_presets(self, ui) -> None:
        """The presets' list (``overlayPresetOptions``): each group's name in bold, not to be chosen (an ``optgroup``),
        its presets under it; the first preset chosen, as a page just drawn has it."""
        box = self.preset_box
        box.blockSignals(True)
        try:
            box.clear()
            for heading, choices in looks.preset_groups(ui):
                box.addItem(heading, None)
                item = box.model().item(box.count() - 1)
                item.setEnabled(False)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                for value, name in choices:
                    box.addItem("  " + name, value)
            box.setCurrentIndex(next((i for i in range(box.count()) if box.itemData(i) is not None), -1))
        finally:
            box.blockSignals(False)

    def preset_chosen(self) -> None:
        """Another preset chosen (``#ov-preset``'s change): what a starter preset looks like, or that it is yours."""
        choice = self.preset_box.currentData()
        if choice:
            self.look_messages["preset"].setText(looks.preset_said(choice))

    def apply_preset(self) -> None:
        """The chosen preset's settings saved (``#ov-preset-apply``), then the page drawn again from the app's."""
        choice = self.preset_box.currentData()
        if not choice:
            return
        settings = looks.preset_settings(choice, self.ui)
        if not _truthy(settings):
            self.look_messages["preset"].setText(looks.NOT_FOUND)
            return
        self.look_messages["preset"].setText(looks.APPLYING)
        if self.requests is not None:
            self.requests.post("preset-apply", "/api/ui", settings)

    def save_preset(self) -> None:
        """The look as the app has it now, saved under a name asked for (``#ov-preset-save``); one of the same name,
        whatever its case, replaced. The app's settings are read first, as the web page reads them."""
        name = looks.js_trim(self.ask_text(looks.NAME_IT, ""))
        if not name:
            return
        if looks.js_units(name) > looks.NAME_LIMIT:
            self.look_messages["preset"].setText(looks.NAME_TOO_LONG)
            return
        self.look_messages["preset"].setText(looks.SAVING)
        if self.requests is not None:
            self.requests.get(f"preset-save:{name}", "/api/ui")

    def delete_preset(self) -> None:
        """The chosen saved preset deleted (``#ov-preset-delete``); a starter preset cannot be."""
        choice = self.preset_box.currentData() or ""
        if choice[:1] != "s":
            self.look_messages["preset"].setText(looks.PICK_SAVED)
            return
        self.look_messages["preset"].setText(looks.DELETING)
        if self.requests is not None:
            self.requests.get(f"preset-delete:{choice[3:]}", "/api/ui")

    def copy_preset(self) -> None:
        """The chosen preset's share code copied (``#ov-preset-copy``); with none to copy, the look the app has now, as
        "My overlay look"."""
        choice = self.preset_box.currentData() or ""
        settings = looks.preset_settings(choice, self.ui) if choice else None
        if _truthy(settings):
            self._copy_code(choice[3:], settings)
        elif self.requests is not None:
            self.requests.get("preset-look", "/api/ui")

    def _copy_code(self, name: str, settings) -> None:
        QApplication.clipboard().setText(looks.encode_preset(name, settings))
        self.look_messages["preset"].setText(looks.COPIED)

    def paste_preset(self) -> None:
        """A share code pasted (``#ov-preset-import``), then saved under the name asked for, its own offered."""
        code = looks.js_trim(self.ask_text(looks.PASTE_IT, ""))
        if not code:
            return
        try:
            preset = looks.decode_preset(code)
        except ValueError:
            self.look_messages["preset"].setText(looks.NOT_A_CODE)
            return
        name = looks.js_trim(self.ask_text(looks.SAVE_SHARED_AS, preset["name"]))
        if not name:
            return
        if looks.js_units(name) > looks.NAME_LIMIT:
            self.look_messages["preset"].setText(looks.NAME_TOO_LONG)
            return
        self.look_messages["preset"].setText(looks.SAVING)
        self.shared_settings = preset["settings"]
        if self.requests is not None:
            self.requests.get(f"preset-share:{name}", "/api/ui")

    def _ask_text(self, question: str, text: str = "") -> str | None:
        answer, ok = QInputDialog.getText(self, "Settings", question, QLineEdit.Normal, text)
        return answer if ok else None

    def _save_look(self, message: str, body: dict, saying: str = looks.SAVING) -> None:
        """A look setting saved, said in its row's words (``msg.textContent``): ``saying`` it, then "Saved", or why
        not."""
        if self._loading:
            return
        for key, value in body.items():
            self.saved.append((key, value))
            self.ui[key] = value
        words = self.look_messages[message]
        if saying:
            words.setText(saying)
        if self.requests is None:
            words.setText(sw.SAVED)
            return
        self.requests.post(f"look:{message}", "/api/ui", body)

    def rerender(self) -> None:
        """The page drawn again from the app's (``pageSettings()``, after a preset is applied, saved or deleted)."""
        self.start()

    # ---------------------------------------------------------------- Appearance and Profiles & backup (0.2.481)
    def _class_colours(self, row: SetRow) -> None:
        """The class colours' panel, the log review's own (``A2CombatReview.settings``): saved to the app as they change,
        as the review pages read them."""
        from .class_colours import ClassColours
        self.class_colours = ClassColours({}, ask_colour=lambda start, words: self.ask_colour(start, words))
        self.class_colours.saved.connect(self._save_class_colours)
        row.body.addWidget(self.class_colours)

    def _save_class_colours(self, preference: dict) -> None:
        """The class colours kept by the app (``/api/ui``'s ``combat_colors``); the web page says nothing of it."""
        self.saved.append(("combat_colors", preference))
        self.ui["combat_colors"] = preference
        if self.requests is not None:
            self.requests.post("classes", "/api/ui", {"combat_colors": preference})

    def _backup(self, row: SetRow) -> None:
        """The settings saved to a file in your data folder, or a file of them imported (``Settings backup``)."""
        self.backup_export = _button(sw.BACKUP_EXPORT, self.export_settings)
        self.backup_message = _words("", "setnote")
        self.backup_message.setAccessibleName("Settings backup status")
        row.body.addWidget(_flow(self.backup_export, _button(sw.BACKUP_IMPORT, self.import_settings), self.backup_message,
                                 gap=(14, 10)))
        row.body.addWidget(_note(sw.BACKUP_NOTE))

    def export_settings(self) -> None:
        """The settings written to a file by the app (``#settings-export``): the button waits until it is."""
        if self.requests is None:
            return
        self.backup_export.setEnabled(False)
        self.backup_message.setText(sw.EXPORTING)
        self.requests.post("backup-export", "/api/ui/export", {})

    def import_settings(self) -> None:
        """A settings file read as the web page reads it (``file.text()``, ``JSON.parse``) and imported; then the page
        is drawn again, and says what was imported."""
        path = self.choose_backup()
        if not path:
            return
        self.backup_message.setText(sw.IMPORTING)
        try:
            with open(path, "rb") as file:
                document = looks.js_parse(file.read())
        except (OSError, ValueError, RecursionError) as problem:
            self.backup_message.setText(sw.could_not_import(str(problem)))
            return
        if self.requests is not None:
            self.requests.post("backup-import", "/api/ui/import", {"document": document})

    def _ask_backup(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, sw.BACKUP_IMPORT, "", sw.BACKUP_FILES)
        return path

    # the rows not drawn as the web page draws them yet (settings_schema): each opens the web Settings page
    def _on_the_web(self, row: SetRow) -> None:
        row.body.addWidget(_flow(_words("This setting is on the web Settings page for now.", "muted"),
                                 _button("Open the web Settings page", lambda: self.open_web("settings"))))

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
        """What the page shows, read from the app (``pageSettings``), each row's words afresh."""
        self._fresh()
        if self.requests is None:
            return
        for name, path in READINGS:
            self.requests.get(name, path)
        self.read_pets()
        self.read_rtss()
        self.read_radar()
        self.radar_poll.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not event.spontaneous():
            self.start()

    def _fresh(self) -> None:
        """Each row's words as a page just drawn has them: the web page draws itself again each time it opens, and after
        a preset is applied, saved or deleted. What the page reads as it opens (Pet Tracker, RTSS, the radar, the
        version) is said again once read."""
        for words in (self.asset_message, self.storage_message, self.notes_message, self.records_message,
                      self.log_cache_message, self.server_message, self.pet_note, self.pet_folder_message,
                      self.stream_message, self.hotkeys_message, self.backup_message, *self.number_messages.values(),
                      *self.look_messages.values()):
            words.setText("")
        self._clear(self.maintenance_box)

    def _replied(self, name: str, answer) -> None:
        kind, _, key = name.partition(":")
        if kind == "status":
            self.apply_status(answer)
        elif kind == "server":
            self.apply_server(answer)
        elif kind == "number":
            self.records_message.setText(sw.SAVED)
        elif kind == "checked":
            words = self.number_messages.get(key.partition("|")[2])
            if words is not None:
                words.setText(sw.SAVED)
        elif kind == "sound":
            self.sound_message.setText(sw.SOUND_SAVED)
        elif kind == "sound-clear":
            self.sound_message.setText(sw.SOUND_CLEARED)
        elif kind == "rtss":
            self.rtss_message.setText(sw.rtss_status(answer))
        elif kind == "radar":
            self._radar_shown(answer)
        elif kind == "radar-control":
            if _truthy(_dict(answer).get("error")):                              # ``api()``: an error is a failure
                return self._failed(name, js_text(answer["error"]))
            self.read_radar()
        elif kind == "hotkeys":
            self.hotkeys_message.setText(sw.SAVED)
        elif kind == "look":
            self.look_messages[key].setText(sw.SAVED)
        elif kind == "background":
            self.look_messages["background"].setText(looks.BG_UPLOADED)
        elif kind == "background-clear":
            self.look_messages["background"].setText(looks.BG_REMOVED)
        elif kind.startswith("preset-"):
            self._preset_replied(kind, key, answer)
        elif kind == "backup-export":
            self.backup_export.setEnabled(True)
            self.backup_message.setText(sw.exported(answer))
        elif kind == "backup-import":                  # the page drawn again, saying what was imported
            self.rerender()
            self.backup_message.setText(sw.imported(answer))
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
            setting, _, words = key.partition("|")
            self.toast.say(sw.SAVED if words in ("", "revert") else words)
            if setting == "pettracker_enabled":                                  # Pet Tracker starting or stopping
                self.pet_timer.start(sw.PET_ENABLED_READ_MS)
            elif setting == "rtss_enabled":                                      # RTSS drawing or not
                self.rtss_timer.start(sw.RTSS_READ_MS)
            elif setting == "radar_enabled":                                     # the radar listening or not
                self.radar_timer.start(sw.RADAR_ENABLED_READ_MS)
        elif kind == "pets":
            self._pets_shown(answer)
        elif kind == "pet":
            if _truthy(_dict(answer).get("error")):                              # ``control``: an error is a failure
                return self._failed(name, js_text(answer["error"]))
            if key == "update":
                self.pet_note.setText(js_text(_dict(answer).get("message")) if _truthy(_dict(answer).get("message")) else "")
            self.read_pets()
        elif kind == "pet-folder":
            self.pet_folder_message.setText(sw.SAVED)
            self.read_pets()
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
        if kind == "save" and key.endswith("|revert"):                          # ``#ov-on-start``: put back, then said
            setting = key.partition("|")[0]
            self._loading = True
            try:
                self.controls[setting].box.setChecked(not self.controls[setting].box.isChecked())
            finally:
                self._loading = False
            self.toast.say(sw.COULD_NOT_SAVE_OVERLAY.format(why))
        elif kind == "save":
            self.toast.say(f"Could not save it: {why}")
        elif kind == "checked":
            words = self.number_messages.get(key.partition("|")[2])
            if words is not None:
                words.setText(why)
        elif kind in ("sound", "sound-clear"):
            self.sound_message.setText(why)
        elif kind == "rtss":
            self.rtss_message.setText(sw.RTSS_UNAVAILABLE)
        elif kind == "radar":
            self.radar_message.setText(sw.RADAR_UNAVAILABLE)
        elif kind == "radar-control":
            self.toast.say(why)
        elif kind == "hotkeys":
            self.hotkeys_message.setText(why)
        elif kind == "look":
            self.look_messages[key].setText(why)
        elif kind in ("background", "background-clear"):
            self.look_messages["background"].setText(why)
        elif kind in ("preset-share", "preset-shared"):
            self.look_messages["preset"].setText(looks.could_not_save(why))
        elif kind.startswith("preset-"):
            self.look_messages["preset"].setText(why)
        elif kind == "backup-export":
            self.backup_export.setEnabled(True)
            self.backup_message.setText(why)
        elif kind == "backup-import":
            self.backup_message.setText(sw.could_not_import(why))
        elif kind == "classes":                        # the web page says nothing; the page says why
            self.toast.say(f"Could not save it: {why}")
        elif kind == "number":
            self.records_message.setText(why)
        elif kind in ("cache", "server-save"):                     # the web page says nothing; the page says why
            self.toast.say(f"Could not save it: {why}")
        elif kind == "server-saved":
            self.server_message.setText(sw.saved_unchecked(why))
        elif kind == "pets":
            self._clear(self.pet_box)
            self.pet_box.addWidget(_words(why, "setnote"))
        elif kind == "pet":
            if key == "update":
                self.pet_note.setText(why)
            else:
                self._clear(self.pet_box)
                self.pet_box.addWidget(_words(why, "setnote"))
        elif kind == "pet-folder":
            self.pet_folder_message.setText(why)
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

    def _preset_replied(self, kind: str, name: str, answer) -> None:
        """A preset's step done: the app's settings read (then the presets saved with the change), or the change saved
        (then said, and the page drawn again), as the web page's handlers do."""
        fresh = _dict(answer)
        if kind == "preset-save":
            self.requests.post("preset-saved", "/api/ui",
                               {"overlay_presets": looks.with_preset(fresh, name, looks.look_of(fresh))})
        elif kind == "preset-delete":
            self.requests.post("preset-deleted", "/api/ui", {"overlay_presets": looks.without_preset(fresh, name)})
        elif kind == "preset-share":
            self.requests.post("preset-shared", "/api/ui",
                               {"overlay_presets": looks.with_preset(fresh, name, self.shared_settings)})
        elif kind == "preset-look":
            self._copy_code(looks.MY_LOOK, looks.look_of(fresh))
        else:
            self.toast.say({"preset-apply": looks.APPLIED, "preset-saved": looks.SAVED_IT,
                            "preset-deleted": looks.DELETED, "preset-shared": looks.SHARED_SAVED}[kind])
            self.rerender()

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
            on["pettracker_enabled"] = ui.get("pettracker_enabled") is True
            on["pettracker_overlay"] = ui.get("pettracker_overlay") is True
            for key, value in on.items():
                self.controls[key].box.setChecked(value)
            self._choose(self.controls["app_text_scale"], sw.text_scale(ui))
            self._choose(self.controls["app_default_page"], sw.launch_page(ui))
            for key in sw.RECORD_NUMBERS:
                self.controls[key].setValue(sw.record_number(ui, key))
            self._choose(self.controls["pettracker_overlay_style"],
                         "pettracker" if ui.get("pettracker_overlay_style") == "pettracker" else "app")
            for key, rule in self.data_checks:
                self.controls[key].box.setChecked(ui.get(key) is not False if rule == "on" else ui.get(key) is True)
            for key, fallback, shown in self.data_numbers:
                self.controls[key].setValue(sw.shown_number(ui, key, fallback, shown))
            for key, fallback in self.data_selects:
                self._choose(self.controls[key], ui.get(key) if _truthy(ui.get(key)) else fallback)
            self.sound_message.setText(sw.SOUND_SET if _truthy(ui.get("overlay_events_sound_set")) else sw.SOUND_BUILT_IN)
            self.controls["radar_enabled"].box.setChecked(ui.get("radar_enabled") is True)
            self.radar_slider.setValue(sw.radar_sensitivity(ui))
            self.radar_notes.setText(sw.radar_notes(ui))
            for action, field in self.hotkey_fields.items():
                field.setText(sw.hotkey_shown(ui, action))
            self.pet_folder.setText(js_text(ui.get("pettracker_path")) if _truthy(ui.get("pettracker_path")) else "")
            self.controls["meter_log_cache_mb"].setValue(sw.log_cache(ui))
            self._apply_look(ui)
            self.class_colours.show_preference(_dict(ui.get("combat_colors")))
            self.class_colours.palette.setCurrentIndex(0)
        finally:
            self._loading = False

    def _apply_look(self, ui: dict) -> None:
        """The overlay's look as the app has it (0.2.480): each colour, font, effect and background number by the web
        page's template's rules; the first element's own font; the presets' list, its first chosen."""
        colours = looks.text_colours(ui)
        for element, pick in self.text_colours.items():
            pick.set_value(colours[element])
        self._choose(self.font_family, looks.font_family(ui))
        self.controls["overlay_font_scale"].setValue(sw.shown_number(ui, "overlay_font_scale", 100, "or"))
        self._choose(self.font_weight, looks.font_weight(ui))
        for key in self.look_checks:
            self.controls[key].box.setChecked(ui.get(key) is True)
        for key, fallback in self.look_colours:
            self.controls[key].set_value(looks.hex_colour(ui.get(key), fallback))
        self.element_fonts = looks.element_fonts(ui)
        self.element.setCurrentIndex(0)
        self.load_element()
        self.look_messages["background"].setText(looks.bg_message(ui))
        for key, _words_, _low, _high, fallback, rule in looks.BG_NUMBERS:
            self.controls[key].setValue(sw.shown_number(ui, key, fallback, rule))
        self._choose(self.controls["overlay_text_autocontrast"], looks.autocontrast(ui))
        self._list_presets(ui)

    @staticmethod
    def _choose(box: QComboBox, value) -> None:
        index = box.findData(value)
        box.setCurrentIndex(index if index >= 0 else 0)

    # ------------------------------------------------------------------ saving
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

