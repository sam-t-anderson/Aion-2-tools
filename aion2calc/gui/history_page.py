"""The native Saved Results page (0.2.434): Character → Saved Results as the web page shows it (pages/history.js):
the optimizations and advice saved on this computer, newest first, each opened, exported or imported.

- **The list:** each saved run's title and when it was recorded, with **Open** and **Export**; or that none is saved
  yet.
- **Import previous result:** an exported result (a JSON file of at most 20 MiB) saved again, through the app's
  ``POST /api/history``, which checks it.
- **Export:** the saved result as the web page exports it (``aion2calc-result-<id>.json``), where you choose.
- **Open:** the snapshot under the list. A build opens in the result windows (``result_windows.py``: Overview, Skills,
  Stigma, Daevanion and Equipment drawn here, the others on the web page for now); an advice's text in its box; an
  advice's full view is on the web page for now.

The list is read each time the page is shown.
"""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QStandardPaths, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import result_windows, results, theme
from .api import AppApi, Requests
from .database_page import Window
from .gathering_page import GatheringPage
from .news import when

NO_RUNS = "No saved runs yet. Completed optimizations and advice save here automatically."
TOO_LARGE = "Result exceeds 20 MiB"
LIMIT = 20 * 1024 * 1024
ADVICE_NOTE = "The advice view is drawn in the web interface for now."


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


class HistoryPage(QWidget):
    """Character → Saved Results. ``open_web`` opens a page of the web interface; ``choose_file`` and ``save_as``
    stand in for the file dialogs."""

    def __init__(self, api: AppApi | None, open_web=None, choose_file=None, save_as=None, clipboard=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_web = api, open_web
        self.choose_file = choose_file or self._ask_file
        self.save_as = save_as or self._ask_where
        self.rows: list[dict] = []
        self.opened: dict | None = None
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.setStyleSheet(GatheringPage._stylesheet() + result_windows.STYLE + f"""
            QLabel#runHead {{ color: {theme.COLORS['gold_dim']}; font-weight: 600; }}
            QFrame#runRow {{ background: transparent; border: none; border-bottom: 1px solid #1d2539; }}
            QFrame#runRow QLabel {{ background: transparent; }}
            QPlainTextEdit#diff {{ background: rgba(6, 9, 15, 0.65); border: 1px solid {theme.COLORS['line']}; border-radius: 6px;
                                   padding: 10px; }}
            """)

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
        window = Window("Saved results", "Previous optimizations and advice, stored on this computer")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_label("Import previous result", wrap=False))
        choose = QPushButton("Choose a file…")
        choose.clicked.connect(self.import_result)
        row.addWidget(choose)
        self.message = _label("", "muted")
        row.addWidget(self.message, 1)
        window.body.addLayout(row)
        listed = QWidget()
        listed.setObjectName("plain")
        self.list = QVBoxLayout(listed)
        self.list.setContentsMargins(0, 0, 0, 0)
        self.list.setSpacing(0)
        window.body.addWidget(listed)
        layout.addWidget(window)
        view = QWidget()
        view.setObjectName("plain")
        self.view = QVBoxLayout(view)
        self.view.setContentsMargins(0, 0, 0, 0)
        self.view.setSpacing(10)
        layout.addWidget(view)
        layout.addStretch(1)
        self.windows: result_windows.ResultWindows | None = None
        self.reveal = QTimer(self)
        self.reveal.setSingleShot(True)
        self.reveal.timeout.connect(lambda: self.scroll.ensureWidgetVisible(view, 0, 0))

    # ------------------------------------------------------------------ reading
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        if self.requests is not None:
            self.requests.get("list", "/api/history")

    def open(self, identifier: str) -> None:
        if self.requests is not None:
            self.requests.get("open:" + identifier, "/api/history?id=" + identifier)

    def export(self, identifier: str) -> None:
        if self.requests is not None:
            self.requests.get("export:" + identifier, "/api/history?id=" + identifier)

    def import_result(self) -> None:
        """An exported result read and saved again (``#result-import``)."""
        path = self.choose_file()
        if not path:
            return
        try:
            if os.path.getsize(path) > LIMIT:
                raise ValueError(TOO_LARGE)
            with open(path, encoding="utf-8") as file:
                document = json.load(file)
        except (OSError, ValueError) as problem:
            self.message.setText(str(problem))
            return
        if self.requests is not None:
            self.requests.post("import", "/api/history", document)

    def _replied(self, name: str, answer) -> None:
        if name == "list":
            self.rows = [row for row in answer if isinstance(row, dict)] if isinstance(answer, list) else []
            self._draw_list()
        elif name.startswith("open:"):
            self._show(answer if isinstance(answer, dict) else {})
        elif name.startswith("export:"):
            self._save(name[len("export:"):], answer)
        elif name == "import":
            self.message.setText("Result imported")
            self.refresh()

    def _failed(self, name: str, why: str) -> None:
        if name != "list":
            self.message.setText(why)

    # ------------------------------------------------------------------ drawing
    def _draw_list(self) -> None:
        while self.list.count():
            child = self.list.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if not self.rows:
            self.list.addWidget(_label(NO_RUNS))
            return
        head = QFrame()
        head.setObjectName("runRow")
        line = QGridLayout(head)
        line.setContentsMargins(8, 6, 8, 6)
        for column, words in enumerate(("RUN", "RECORDED", "")):
            line.addWidget(_label(words, "runHead", wrap=False), 0, column)
        self._columns(line)
        self.list.addWidget(head)
        for row in self.rows:
            frame = QFrame()
            frame.setObjectName("runRow")
            line = QGridLayout(frame)
            line.setContentsMargins(8, 6, 8, 6)
            line.addWidget(_label(str(row.get("title") or "")), 0, 0)
            line.addWidget(_label(when((row.get("created") or 0) * 1000), wrap=False), 0, 1)
            actions = QHBoxLayout()
            actions.setSpacing(4)
            identifier = str(row.get("id") or "")
            opener = QPushButton("Open")
            opener.setAccessibleName(f"Open {row.get('title')}")
            opener.clicked.connect(lambda _checked=False, i=identifier: self.open(i))
            actions.addWidget(opener)
            exporter = QPushButton("Export")
            exporter.setAccessibleName(f"Export {row.get('title')}")
            exporter.clicked.connect(lambda _checked=False, i=identifier: self.export(i))
            actions.addWidget(exporter)
            actions.addStretch(1)
            line.addLayout(actions, 0, 2)
            self._columns(line)
            self.list.addWidget(frame)

    @staticmethod
    def _columns(line: QGridLayout) -> None:
        line.setColumnStretch(0, 5)
        line.setColumnStretch(1, 4)
        line.setColumnStretch(2, 3)

    def _show(self, doc: dict) -> None:
        """The saved result under the list (``#history-view``): its date, then its windows, its text or the advice."""
        if self.windows is not None:
            self.windows.stop()
        while self.view.count():
            child = self.view.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.windows = None
        self.opened = doc
        self.view.addWidget(_label(results.saved_line(when((doc.get("created") or 0) * 1000)), "muted"))
        kind = doc.get("kind")
        if kind == "advice-text":
            text = QPlainTextEdit(str((doc.get("result") or {}).get("text") or ""))
            text.setObjectName("diff")
            text.setReadOnly(True)
            text.setFont(QFont("monospace"))
            text.setMaximumHeight(420)
            self.view.addWidget(text)
        elif kind == "advice":
            window = Window("Advice")
            window.body.addWidget(_label(ADVICE_NOTE, "muted"))
            button = QPushButton("Open the web Saved Results page")
            button.clicked.connect(lambda: self.open_web("history") if self.open_web else None)
            window.body.addWidget(button, 0, Qt.AlignLeft)
            self.view.addWidget(window)
        else:
            self.windows = result_windows.ResultWindows(self.api, self.open_web, "history", when=when)
            self.view.addWidget(self.windows)
            self.windows.set_view(results.view_of(doc) or {})
        self.reveal.start(0)                                    # scrolled to it once it is laid out

    def _save(self, identifier: str, doc) -> None:
        """A saved result exported as the web page exports it."""
        path = self.save_as(f"aion2calc-result-{identifier}.json")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(doc, file, indent=2, ensure_ascii=False)
        except OSError as problem:
            self.message.setText(f"Could not save the result: {problem.strerror or problem}")
            return
        self.message.setText(f"Result saved to {path}.")

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, "Import previous result", "", "JSON (*.json)")
        return path

    def _ask_where(self, name: str) -> str:
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, "Export", os.path.join(folder, name), "JSON (*.json)")
        return path

    def closeEvent(self, event) -> None:
        if self.windows is not None:
            self.windows.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)
