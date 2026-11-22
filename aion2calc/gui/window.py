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

from . import i18n, theme
from .account_page import AccountPage
from .builds_page import BuildsPage
from .combat_review import read_page
from .api import AppApi, Requests
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
from .raid_page import RaidPage
from .pets_page import PetsPage
from .timers_page import TimersPage
from .settings_page import SettingsPage, show_patch_notes
from .settings_words import patch_notes, text_scale

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
        self.shown_look = theme.LOOK["shown"]              # the theme drawn: the computer's, while it follows it
        self.setWindowTitle("Aion 2 Calc")
        self.resize(1280, 820)
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        side = QWidget()
        side.setObjectName("navside")
        side.setFixedWidth(200)
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        # the language, at the top as on the web page's (i18n.js ``picker``; 0.2.483)
        self.language = i18n.picker(self.change_language)
        column.addWidget(self.language)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        column.addWidget(self.nav, 1)
        self.pages = QStackedWidget()
        self.page_index: dict[str, int] = {}
        self.page_rows: dict[str, int] = {}
        for section, pages in SECTIONS:
            if section:
                heading = QListWidgetItem(i18n.t(section).upper())
                heading.setFlags(Qt.NoItemFlags)
                self.nav.addItem(heading)
            for key, title in pages:
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, key)
                self.nav.addItem(item)
                self.page_rows[key] = self.nav.count() - 1
                if key == "meter":
                    widget = MeterPage(api, open_page=self.show_page, open_in_web=self.open_in_web, open_web=self.open_web,
                                       open_builds=self.open_builds)
                elif key == "settings":
                    widget = SettingsPage(api, self.open_web, open_page=self.show_page,
                                          change_language=self.change_language, change_look=self.change_look)
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
                    widget = CombatPage(api, self.open_web, open_in_web=self.open_in_web, open_builds=self.open_builds)
                elif key == "builds":
                    widget = BuildsPage(api)
                elif key == "raid":
                    widget = RaidPage(api, self.open_in_web)
                else:
                    widget = WebPage(key, title, self.open_web)
                self.page_index[key] = self.pages.addWidget(widget)
        self.nav.currentItemChanged.connect(self._navigate)
        layout.addWidget(side)
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

    def current_page(self) -> str:
        item = self.nav.currentItem()
        key = item.data(Qt.UserRole) if item is not None else None
        return key if key in self.page_index else "meter"

    def change_language(self, lang: str) -> None:
        """Another language chosen: kept as the web pages keep it (``a2-lang``, in the app's interface data), and the
        window drawn again in it on the page shown, as the web page reloads (i18n.js ``set``)."""
        if not i18n.known(lang):
            return
        from . import interface
        interface.store().setValue(i18n.KEY, lang)
        i18n.install(lang)
        self.redraw()

    def change_look(self, then=None) -> None:
        """Another theme or accent chosen (kept with the web pages' choice by Settings): the window drawn again in it,
        as the web page draws itself again (0.2.484); with the same look, the Settings page alone drawn again (0.2.485,
        a customization profile applied). ``then`` is given the Settings page drawn, to say what was done there."""
        from . import interface
        before = dict(theme.LOOK)
        theme.apply_look(*theme.look_of(interface.store()))
        if theme.LOOK == before:
            page = self.page("settings")
            page.rerender()
        else:
            page = self.redraw().page("settings")
        if then is not None:
            then(page)

    def computer_look_changed(self) -> None:
        """The computer turned light or dark: the window drawn again where the theme follows it."""
        if theme.LOOK["theme"] == "system" and theme.apply_look("system", theme.LOOK["accent"]) != self.shown_look:
            self.redraw()

    def redraw(self) -> "MainWindow":
        """The window drawn again, on the page shown, in the language and the look chosen now."""
        again = MainWindow(self.api, self.web_base, self.current_page(), self.parent_process)
        again.setGeometry(self.geometry())
        again.setWindowState(self.windowState())
        self.again = again
        again.show()
        again.start()
        self.close()
        self.deleteLater()
        return again

    def show_page(self, key: str) -> None:
        self.nav.setCurrentRow(self.page_rows[key])

    def open_builds(self, context: dict, back=None) -> None:
        """A log's character opened in Builds (``openBuildWorkspace``, 0.2.489): the page opens on it, and its
        ← Back to log shows the page it came from again, then ``back`` (the log reopened there)."""
        origin = self.current_page()

        def again() -> None:
            self.show_page(origin)
            if back is not None:
                back()
        self.page("builds").prepare(context, again)
        self.show_page("builds")

    def _navigate(self, current, _previous) -> None:
        key = current.data(Qt.UserRole) if current is not None else None
        if key in self.page_index:
            left = self.pages.currentWidget()
            self.pages.setCurrentIndex(self.page_index[key])
            if left is not self.pages.currentWidget() and hasattr(left, "leave"):
                left.leave()                  # a page that starts afresh each time it is opened (Builds, 0.2.486)

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
        self._whats_new()

    def _whats_new(self) -> None:
        """What's new, once after an update (patch-notes.js ``check``): closing it tells the app, which then never
        shows it again (0.2.475)."""
        if self.api is None:
            return
        self._notes = Requests(self.api, self)
        self._notes.replied.connect(self._notes_read)
        self._notes.get("notes", "/api/patch-notes")

    def _notes_read(self, _name: str, answer) -> None:
        notes = patch_notes(answer)
        if notes["show"] and notes["notes"]:
            self.notes_dialog = show_patch_notes(self.api, self, notes, webbrowser.open, seen=True)


def _follow_the_computer(app) -> None:
    """The computer turning light or dark redraws the window shown, where its theme follows the computer's."""
    def changed(*_args):
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, MainWindow) and widget.isVisible():
                widget.computer_look_changed()
                return
    try:
        app.styleHints().colorSchemeChanged.connect(changed)
    except AttributeError:                          # a Qt without it: the theme read as the window opens
        pass


def scale_text(api: AppApi) -> None:
    """The window at the app's text size (Settings → Text size, ``app_text_scale``), every word and the layout with it
    as a browser's zoom scales them (0.2.475). Qt takes it as the window opens (``QT_SCALE_FACTOR``), so a new size
    shows the next time the window opens; a size set by hand in the environment is left as it is."""
    if os.environ.get("QT_SCALE_FACTOR"):
        return
    try:
        ui = api.get("/api/ui")
    except (OSError, ValueError):
        return
    size = text_scale(ui if isinstance(ui, dict) else {})
    if size != 100:
        os.environ["QT_SCALE_FACTOR"] = f"{size / 100:g}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aion2calc.gui", description="Aion 2 Calc native interface")
    parser.add_argument("--url", default="http://127.0.0.1:8765/", help="the app's address")
    args = parser.parse_args(argv)
    from ..overlay import _ParentProcess
    base, _, fragment = args.url.partition("#")
    page = fragment.strip("/") or "meter"
    if QApplication.instance() is None:
        scale_text(AppApi(base))
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from . import interface
    interface.connect(AppApi(base))                  # the window's choices, kept by the app with the web pages' (0.2.482)
    i18n.install(i18n.language())                    # in the language the web pages show (0.2.483)
    theme.apply_look(*theme.look_of(interface.store()))   # and their theme and accent (0.2.484)
    window = MainWindow(AppApi(base), base, page, _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")))
    _follow_the_computer(app)
    window.show()
    window.start()
    return app.exec()
