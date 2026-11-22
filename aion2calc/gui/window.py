"""The native app window (0.2.413; the native interface is the default since 0.2.426): the app's navigation and
pages drawn by Qt.

The navigation lists the web interface's sections and pages in its order (``SECTIONS``, after index.html). The
pages are moved over one at a time: the Live Meter page first (as the web page draws it since 0.2.471,
``meter_page``), then Settings (0.2.414), then News (0.2.427), Timers (0.2.428), Database (0.2.429) and Gathering
(0.2.430). A page the native window does not draw yet says so and opens in the web interface, so every page stays a
click away while the move goes on.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import theme
from .account_page import AccountPage
from .combat_review import read_page
from .api import AppApi
from .news import NewsPage
from .crafting_page import CraftingPage
from .database_page import DatabasePage
from .gathering_page import GatheringPage
from .gear_page import GearPage
from .history_page import HistoryPage
from .character_page import CharacterPage
from .combat_page import CombatPage
from .maps_page import MapsPage
from .meter_page import MeterPage
from .planner_page import PlannerPage
from .pets_page import PetsPage
from .timers_page import TimersPage
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
                    widget = MeterPage(api, open_page=self.show_page, open_in_web=self.open_in_web)
                elif key == "settings":
                    widget = SettingsPage(api, self.open_web)
                elif key == "news":
                    widget = NewsPage(api)
                elif key == "timers":
                    widget = TimersPage(api, self.open_web)
                elif key == "database":
                    widget = DatabasePage(api)
                elif key == "gathering":
                    widget = GatheringPage(api, self.show_page)
                elif key == "pets":
                    widget = PetsPage(api)
                elif key == "crafting":
                    widget = CraftingPage(api)
                elif key == "maps":
                    widget = MapsPage(api)
                elif key == "history":
                    widget = HistoryPage(api, self.open_web)
                elif key == "planner":
                    widget = PlannerPage(api, self.show_page, self.open_web)
                elif key == "character":
                    widget = CharacterPage(api, self.open_web)
                elif key == "gear":
                    widget = GearPage(api, self.show_page, self.open_web)
                elif key == "account":
                    widget = AccountPage(api, self.open_web)
                elif key == "combat":
                    widget = CombatPage(api, self.open_web, open_in_web=self.open_in_web)
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
        """Open a page: here when this window draws it (an analyzed encounter since 0.2.456, a log's review since
        0.2.457), else in the web interface."""
        if not self._open_here(page):
            self.open_in_web(page)

    def open_in_web(self, page: str) -> None:
        """Open a page in the web interface, the app's own window for it when Edge or Chrome is there."""
        url = f"{self.web_base.rstrip('/')}/#/{page}"
        try:
            from ..launcher import open_window
            open_window(url, True, native=False)
        except Exception:
            webbrowser.open(url)

    def _open_here(self, page: str) -> bool:
        """A page this window draws itself, shown on Combat Logs: an analyzed encounter, or a recorded or shared log."""
        if "combat" not in self.page_index:
            return False
        match = re.fullmatch(r"combat-log/analysis/([^/?#]+)", page or "")
        log = read_page(page)
        if match is None and log is None:
            return False
        self.show_page("combat")
        if match is not None:
            self.page("combat").open_analysis(urllib.parse.unquote(match.group(1)))
        else:
            self.page("combat").open_review(log["kind"], log["value"], log["mode"], log["segment"])
        return True

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
