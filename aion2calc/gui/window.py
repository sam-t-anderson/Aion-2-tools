"""The native app window (0.2.413; the native interface is the default since 0.2.426): the app's navigation and
pages drawn by Qt.

The navigation lists the web interface's sections and pages in its order (``SECTIONS``, after index.html). The
pages are moved over one at a time: the Live Meter page first, then Settings (0.2.414). A page the native window does not draw yet
says so and opens in the web interface, so every page stays a click away while the move goes on.
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme
from .api import AppApi, Poller
from .overlay import START_SCOPE, counter_lines
from .settings_page import SettingsPage

#: The web interface's navigation (index.html): each section's pages, then Settings and Account.
SECTIONS = (
    ("Combat", (("meter", "Live Meter"), ("combat", "Combat Logs"), ("raid", "Raid Planner"))),
    ("Character", (("planner", "Build Planner"), ("builds", "Builds"), ("character", "My Character"),
                   ("gear", "Gear & Advice"), ("history", "Saved Results"))),
    ("Game", (("timers", "Timers"), ("maps", "Maps"), ("database", "Database"), ("crafting", "Crafting"),
              ("gathering", "Gathering"), ("pets", "Pet Tracker"), ("news", "News"))),
    ("", (("settings", "Settings"), ("account", "Account"))),
)
PAGE_TITLES = {page: title for _section, pages in SECTIONS for page, title in pages}


class WebPage(QWidget):
    """A page the native window does not draw yet: it opens in the web interface."""

    def __init__(self, page: str, title: str, open_web, parent=None):
        super().__init__(parent)
        self.page = page
        box = QVBoxLayout(self)
        box.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(title)
        heading.setObjectName("heading")
        box.addWidget(heading)
        note = QLabel(f"{title} is not in the native interface yet. It opens in the web interface meanwhile, "
                      "with everything it does there.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        box.addWidget(note)
        self.button = QPushButton(f"Open {title} in the web interface")
        self.button.clicked.connect(lambda: open_web(page))
        row = QHBoxLayout()
        row.addWidget(self.button)
        row.addStretch(1)
        box.addLayout(row)
        box.addStretch(1)


class MeterPage(QWidget):
    """The Live Meter page: the capture's state with Start, Stop and Open overlay, the players of the current fight
    and the counter lines, from the app's ``/api/meter`` as the web page reads it."""

    COLUMNS = ("Player", "Class", "DPS", "Damage", "Share", "Hits", "Crit")

    def __init__(self, api: AppApi | None, parent=None):
        super().__init__(parent)
        self.api = api
        self.answer: dict = {}
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 20, 24, 20)
        box.setSpacing(10)
        heading = QLabel("Live Meter")
        heading.setObjectName("heading")
        box.addWidget(heading)
        self.state = QLabel("Waiting for the app")
        self.state.setObjectName("muted")
        box.addWidget(self.state)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start capture")
        self.stop_button = QPushButton("Stop")
        self.overlay_button = QPushButton("Open overlay")
        self.start_button.clicked.connect(self.start_capture)
        self.stop_button.clicked.connect(self.stop_capture)
        self.overlay_button.clicked.connect(self.open_overlay)
        for button in (self.start_button, self.stop_button, self.overlay_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        self.fight = QLabel("")
        box.addWidget(self.fight)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        box.addWidget(self.table, 1)
        self.lines = QLabel("")
        self.lines.setWordWrap(True)
        box.addWidget(self.lines)
        self.ping = QLabel("")
        self.ping.setObjectName("muted")
        box.addWidget(self.ping)
        self.apply({})
        self.poller = None
        if api is not None:
            self.poller = Poller(api, "/api/meter", 1000, self)
            self.poller.answered.connect(self.apply)
            self.poller.failed.connect(lambda why: self.state.setText("The app does not answer: " + why))

    def start(self) -> None:
        if self.poller is not None:
            self.poller.start()

    def _post(self, payload: dict, path: str = "/api/meter") -> dict | None:
        if self.api is None:
            return None
        try:
            return self.api.post(path, payload)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Live Meter", f"The app did not take it: {exc}")
            return None

    def start_capture(self) -> None:
        # Self + Party, the web Live Meter page's own choice until one is picked there (0.2.416: the app took a
        # start without one for Automatic)
        self._post({"action": "start", "source": "a2tools", "auto_port": True, "scope": START_SCOPE})

    def stop_capture(self) -> None:
        self._post({"action": "stop"})

    def open_overlay(self) -> None:
        self._post({}, "/api/overlay")

    def apply(self, answer: dict) -> None:
        """Show the app's answer to ``/api/meter``."""
        if not isinstance(answer, dict):
            return
        self.answer = answer
        running = answer.get("running") is True
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        error = answer.get("error")
        if error:
            self.state.setText(f"Capture stopped: {error}")
        else:
            self.state.setText("Capturing" if running else "Not capturing")
        snap = answer.get("snapshot") or {}
        players = sorted((p for p in (snap.get("players") or []) if isinstance(p, dict)),
                         key=lambda p: float(p.get("dps") or 0), reverse=True)
        if players:
            raid = sum(float(p.get("dps") or 0) for p in players)
            self.fight.setText(f"{snap.get('boss') or 'Combat'} · {float(snap.get('duration') or 0):.0f}s · "
                               f"{theme.kfmt(raid)} raid DPS")
        else:
            self.fight.setText("No fight yet")
        self.table.setRowCount(len(players))
        for row, player in enumerate(players):
            crit = player.get("crit")
            cells = (str(player.get("name") or "?"), str(player.get("class") or "").title(),
                     theme.kfmt(player.get("dps")), theme.kfmt(player.get("damage")),
                     f"{100 * float(player.get('share') or 0):.1f}%", f"{int(player.get('hits') or 0):,}",
                     f"{100 * float(crit):.1f}%" if isinstance(crit, (int, float)) else "—")
            for column, text in enumerate(cells):
                item = self.table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(row, column, item)
                if item.text() != text:
                    item.setText(text)
                if column >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lines = counter_lines(snap)
        self.lines.setText("\n".join(text for _key, text, _short in lines))
        self.lines.setVisible(bool(lines))
        ping = snap.get("ping")
        if isinstance(ping, dict) and ping.get("samples"):
            self.ping.setText(f"Ping {theme.kfmt(ping.get('current'))} ms now · {theme.kfmt(ping.get('avg'))} ms "
                              f"capture avg · {theme.kfmt(ping.get('min'))}–{theme.kfmt(ping.get('max'))} ms range")
            self.ping.show()
        else:
            self.ping.hide()


class MainWindow(QMainWindow):
    """The app window: the navigation on the left, the page on the right."""

    def __init__(self, api: AppApi | None, web_base: str = "", page: str = "meter", parent_process=None):
        super().__init__()
        self.api, self.web_base, self.parent_process = api, web_base, parent_process
        self.setWindowTitle("Aion 2 Calc")
        self.resize(1280, 820)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(200)
        self.pages = QStackedWidget()
        self.page_index: dict[str, int] = {}
        self.page_rows: dict[str, int] = {}
        for section, pages in SECTIONS:
            if section:
                heading = QListWidgetItem(section.upper())
                heading.setFlags(Qt.NoItemFlags)
                self.nav.addItem(heading)
            for key, title in pages:
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, key)
                self.nav.addItem(item)
                self.page_rows[key] = self.nav.count() - 1
                if key == "meter":
                    widget = MeterPage(api)
                elif key == "settings":
                    widget = SettingsPage(api, self.open_web)
                else:
                    widget = WebPage(key, title, self.open_web)
                self.page_index[key] = self.pages.addWidget(widget)
        self.nav.currentItemChanged.connect(self._navigate)
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(theme.app_stylesheet())
        self.show_page(page if page in self.page_index else "meter")
        if parent_process is not None and getattr(parent_process, "watched", lambda: False)():
            self._parent_timer = QTimer(self)
            self._parent_timer.timeout.connect(lambda: self.parent_process.alive() or QApplication.quit())
            self._parent_timer.start(2000)

    def page(self, key: str) -> QWidget:
        return self.pages.widget(self.page_index[key])

    def show_page(self, key: str) -> None:
        self.nav.setCurrentRow(self.page_rows[key])

    def _navigate(self, current, _previous) -> None:
        key = current.data(Qt.UserRole) if current is not None else None
        if key in self.page_index:
            self.pages.setCurrentIndex(self.page_index[key])

    def open_web(self, page: str) -> None:
        """Open a page in the web interface: the app's own window for it when Edge or Chrome is there."""
        url = f"{self.web_base.rstrip('/')}/#/{page}"
        try:
            from ..launcher import open_window
            open_window(url, True, native=False)
        except Exception:
            webbrowser.open(url)

    def start(self) -> None:
        self.page("meter").start()
        self.page("settings").start()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aion2calc.gui", description="Aion 2 Calc native interface")
    parser.add_argument("--url", default="http://127.0.0.1:8765/", help="the app's address")
    args = parser.parse_args(argv)
    from ..overlay import _ParentProcess
    base, _, fragment = args.url.partition("#")
    page = fragment.strip("/") or "meter"
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(AppApi(base), base, page, _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")))
    window.show()
    window.start()
    return app.exec()
