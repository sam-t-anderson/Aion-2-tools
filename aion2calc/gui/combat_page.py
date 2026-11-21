"""The native Combat Logs page, part 1 (0.2.450): Combat → Combat Logs as pages/combat.js shows it.

- **Its views:** Browse logs, Completed-run speed, Boss progression, Highest observed build points and Personal
  records; and under Browse logs its lists: Community Combat Logs, My Uploads, Saved Logs and My Character Identities.
- **Saved Logs** is drawn here: a fight **analyzed** from an AbyssLogs or A2DIL link (for a party log, as a player
  named) or from a file (an AbyssLogs segment, gzipped or not, aion2calc JSON or CSV), its progress as the job runs,
  then its analysis; the folder every analyzed log is saved in, with **Open folder**; the **log server** shared to,
  with its upload key (only whether one is saved is shown) and who sees the uploads; and the **encounters analyzed**,
  each opened.
- The other views and lists, the recorded encounters by type, the recordings to upload, and an encounter's analysis
  open in the web interface for now.
"""
from __future__ import annotations

import html
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from . import combat as cb
from . import theme
from .api import AppApi, Job, Requests
from .database_page import Window
from .gathering_page import GatheringPage
from .pets_page import Toast
from .result_windows import STYLE as RESULT_STYLE, GridTable


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _button(words: str, action, name: str = "small") -> QPushButton:
    button = QPushButton(words)
    button.setObjectName(name)
    button.clicked.connect(lambda _checked=False: action())
    return button


def _head(words: str) -> QLabel:
    """A heading (``h3``); its margin would make it a frame, which indents a label's words."""
    label = _label(words, "combatHead")
    label.setIndent(0)
    return label


def _row(*widgets: QWidget) -> QWidget:
    row = QWidget()
    row.setObjectName("plain")
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(8)
    for widget in widgets:
        line.addWidget(widget)
    line.addStretch(1)
    return row


def _clear(layout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class CombatPage(QWidget):
    """Combat Logs. ``open_web`` opens a page of the web interface; ``choose_file`` and ``open_link`` stand in for the
    file dialog and the browser."""

    def __init__(self, api: AppApi | None, open_web=None, choose_file=None, open_link=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_web = api, open_web
        self.choose_file = choose_file or self._ask_file
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.view, self.list = "community", "community"              # ``st.logsTab``, ``st.listTab``
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.job = Job(api, self) if api is not None else None
        if self.job is not None:
            self.job.logged.connect(lambda log: self._say(cb.last_line(log)))
            self.job.done.connect(self._analyzed)
            self.job.failed.connect(self._say)
        self.setStyleSheet(GatheringPage._stylesheet() + RESULT_STYLE + f"""
            QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
            QPushButton#small[chosen="true"] {{ font-weight: 700; text-decoration: underline; }}
            QLabel#combatHead {{ color: {theme.COLORS['text']}; font-size: 15px; font-weight: 700; margin-top: 6px; }}
            QLabel#combatMessage {{ color: {theme.COLORS['muted']}; }}
            QLabel#faint {{ color: {theme.COLORS['faint']}; }}
            """ + Toast.STYLE)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        content = QWidget()
        self.scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        self.frame = Window("Combat logs", cb.SUBTITLE)
        layout.addWidget(self.frame)
        layout.addStretch(1)
        self.views = QHBoxLayout()
        self.views.setSpacing(6)
        self.frame.body.addLayout(self.views)
        holder = QWidget()
        holder.setObjectName("plain")
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(0, 6, 0, 0)
        self.body.setSpacing(10)
        self.frame.body.addWidget(holder)
        self.message: QLabel | None = None
        self.toast = Toast(self)
        self.draw()

    # ---------------------------------------------------------------- the views and lists
    def _tabs(self, layout: QHBoxLayout, tabs, chosen: str, pick, underlined: bool = False) -> None:
        """Tabs as ``.btn small``: the chosen list ``primary`` (log-tabs.js), the chosen view bold and underlined
        (logs-view.js)."""
        _clear(layout)
        for key, words in tabs:
            tab = QPushButton(words)
            tab.setObjectName("primary" if key == chosen and not underlined else "small")
            tab.setProperty("chosen", key == chosen)
            tab.setAccessibleName(words)
            tab.clicked.connect(lambda _checked=False, key=key: pick(key))
            layout.addWidget(tab)
        layout.addStretch(1)

    def draw(self) -> None:
        self._tabs(self.views, cb.VIEWS, self.view, self.show_view, underlined=True)
        _clear(self.body)
        self.message = None
        if self.view != "community":
            self.body.addWidget(_label(cb.ON_THE_WEB_VIEW, "muted"))
            self.body.addWidget(_row(_button("Open it on the web page", lambda: self._web("combat"))))
            return
        lists = QHBoxLayout()
        lists.setContentsMargins(0, 0, 0, 0)
        lists.setSpacing(6)
        holder = QWidget()
        holder.setObjectName("plain")
        holder.setLayout(lists)
        self._tabs(lists, cb.LISTS, self.list, self.show_list)
        self.body.addWidget(holder)
        if self.list != "saved":
            self.body.addWidget(_label(cb.ON_THE_WEB_LIST, "muted"))
            self.body.addWidget(_row(_button("Open it on the web page", lambda: self._web(cb.list_page(self.list)))))
            return
        self._saved()

    def show_view(self, key: str) -> None:
        self.view = key
        self.draw()

    def show_list(self, key: str) -> None:
        self.list = key
        self.draw()

    def _web(self, page: str) -> None:
        if self.open_web is not None:
            self.open_web(page)

    # ---------------------------------------------------------------- saved logs
    def _saved(self) -> None:
        """Saved Logs: a fight analyzed, where the logs are kept, the log server, and the encounters analyzed."""
        self.ref = QLineEdit()
        self.ref.setPlaceholderText(cb.REF_HINT)
        self.ref.setAccessibleName("AbyssLogs or A2DIL link")
        self.ref.setMinimumWidth(420)
        self.player = QLineEdit()
        self.player.setPlaceholderText(cb.PLAYER_HINT)
        self.player.setAccessibleName("Player")
        self.player.setMaximumWidth(180)
        self.analyze = _button("Analyze", self.import_link, "primary")
        self.message = _label("", "combatMessage", wrap=False)
        self.body.addWidget(_row(self.ref, self.player, self.analyze, _label("or", "muted", wrap=False),
                                 _button("Choose a file…", self.import_file), self.message))
        note = _label(cb.IMPORT_NOTE, "faint", rich=True)
        note.linkActivated.connect(self.open_link)
        self.body.addWidget(note)
        self.folder = _row()
        self.body.addWidget(self.folder)
        self.server = _row()
        self.body.addWidget(self.server)
        for head in ("Recorded encounters by type", "Upload recordings"):
            self.body.addWidget(_head(head))
            self.body.addWidget(_row(_label(cb.ON_THE_WEB_PART, "muted", wrap=False),
                                     _button("Open them on the web page", lambda: self._web(cb.list_page("saved")))))
        self.body.addWidget(_head("Analyzed encounters"))
        self.encounters_box = QWidget()
        self.encounters_box.setObjectName("plain")
        self.encounters = QVBoxLayout(self.encounters_box)
        self.encounters.setContentsMargins(0, 0, 0, 0)
        self.body.addWidget(self.encounters_box)
        if self.requests is not None:
            self.requests.get("logs", "/api/logs")
            self.requests.get("logserver", "/api/logserver")
            self.requests.get("encounters", "/api/encounters")

    def _replied(self, name: str, answer) -> None:
        if name == "logs":
            self._folder(answer)
        elif name == "logserver":
            self._server(answer)
        elif name == "saved-server":
            self.toast.say("Saved")
            if self.requests is not None:
                self.requests.get("logserver", "/api/logserver")
        elif name == "encounters":
            self._encounters(answer)

    def _failed(self, name: str, why: str) -> None:
        if name in ("open-folder", "saved-server"):
            self._say(why)
        elif name == "encounters":
            self._encounters([])
        # the folder and the log server rows stay empty when the app does not say (``.catch(() => {})``)

    def _alive(self, widget) -> bool:
        try:
            return widget is not None and widget.parent() is not None
        except RuntimeError:                              # drawn again since
            return False

    def _folder(self, answer) -> None:
        if self.list != "saved" or not self._alive(getattr(self, "folder", None)):
            return
        folder, files = cb.folder_line(answer)
        line = self.folder.layout()
        _clear(line)
        line.addWidget(_label("Every analyzed log is saved as a file in", "muted", wrap=False))
        line.addWidget(_label(f"<code>{html.escape(folder)}</code>", rich=True, wrap=False))
        line.addWidget(_label(files, "faint", wrap=False))
        line.addWidget(_button("Open folder", self.open_folder))
        line.addStretch(1)

    def _server(self, answer) -> None:
        if self.list != "saved" or not self._alive(getattr(self, "server", None)):
            return
        row = cb.server_row(answer)
        line = self.server.layout()
        _clear(line)
        self.server_url = QLineEdit(row["url"])
        self.server_url.setPlaceholderText(cb.SERVER_HINT)
        self.server_url.setAccessibleName("Log server")
        self.server_url.setMinimumWidth(260)
        self.server_key = QLineEdit()
        self.server_key.setEchoMode(QLineEdit.Password)
        self.server_key.setPlaceholderText(row["key_hint"])
        self.server_key.setAccessibleName("Upload key")
        self.server_key.setMaximumWidth(190)
        self.server_seen = QComboBox()
        for key, words in cb.VISIBILITY:
            self.server_seen.addItem(words, key)
        self.server_seen.setCurrentIndex(self.server_seen.findData(row["visibility"]))
        self.server_seen.setAccessibleName("Who can see your uploads")
        for widget in (_label("Share to a log server:", "muted", wrap=False), self.server_url, self.server_key, self.server_seen,
                       _button("Save", self.save_server)):
            line.addWidget(widget)
        line.addStretch(1)

    def _encounters(self, answer) -> None:
        if self.list != "saved" or not self._alive(getattr(self, "encounters_box", None)):
            return
        _clear(self.encounters)
        rows = cb.encounter_rows(answer)
        if not rows:
            self.encounters.addWidget(_label(cb.NO_ENCOUNTERS, "faint"))
            return
        cells = [[str(r["id"]), r["player"], r["class"], r["boss"], r["source"], r["duration"], r["dps"],
                  _button("Open", lambda identifier=r["id"]: self._web(cb.analysis_page(identifier)))] for r in rows]
        self.encounters.addWidget(GridTable(cb.ENCOUNTER_COLUMNS, cells, {column: 1 for column in range(1, 7)}, right=(5, 6)))

    def _say(self, words: str) -> None:
        if self.message is not None:
            try:
                self.message.setText(words)
            except RuntimeError:
                pass

    def import_link(self) -> None:
        """A fight analyzed from its link (``#imp``)."""
        if self.job is not None:
            self.job.start("/api/encounters/import", cb.import_body(self.ref.text(), self.player.text()))

    def import_file(self) -> None:
        """A fight analyzed from a file (``#file``): an AbyssLogs segment unpacked when it is gzipped."""
        path = self.choose_file()
        if not path:
            return
        try:
            text = cb.read_log_file(path)
        except (OSError, ValueError, EOFError) as problem:
            self._say(str(problem))
            return
        if self.job is not None:
            self.job.start("/api/encounters/import", cb.file_body(text, os.path.basename(path), self.player.text()))

    def _analyzed(self, result) -> None:
        """The fight analyzed: its analysis opened, and the list read again."""
        identifier = (result or {}).get("id") if isinstance(result, dict) else None
        if identifier is not None:
            self._web(cb.analysis_page(identifier))
        if self.requests is not None and self.list == "saved":
            self.requests.get("encounters", "/api/encounters")

    def open_folder(self) -> None:
        if self.requests is not None:
            self.requests.post("open-folder", "/api/logs/open", {})

    def save_server(self) -> None:
        if self.requests is not None:
            self.requests.post("saved-server", "/api/logserver",
                               cb.server_body(self.server_url.text(), self.server_key.text(), self.server_seen.currentData()))

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, "Analyze a combat log", "", cb.FILE_KINDS)
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.place()

    def closeEvent(self, event) -> None:
        for worker in (self.requests, self.job):
            if worker is not None:
                worker.stop()
        super().closeEvent(event)
