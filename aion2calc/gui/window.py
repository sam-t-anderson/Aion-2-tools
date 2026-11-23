"""The native app window (0.2.413; the native interface is the default since 0.2.426): the app's navigation and
pages drawn by Qt.

The navigation lists the web interface's sections and pages in its order (``SECTIONS``, after index.html). The
pages are moved over one at a time: the Live Meter page first (as the web page draws it since 0.2.471,
``meter_page``), then Settings (0.2.414), then News (0.2.427), Timers (0.2.428), Database (0.2.429) and Gathering
(0.2.430), and so on until every page was drawn here (the Raid Planner last, 0.2.490). A page the native window does
not draw says so and opens in the web interface. Since 0.2.500 a link to any page of the app opens it here, as the web
interface shows it at that address (``web_route``).
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import urllib.parse
import webbrowser

from PySide6.QtCore import QBuffer, QByteArray, QCoreApplication, QEvent, QIODevice, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from . import i18n, theme
from . import live_meter as lm
from .app_icon import app_icon, apply as apply_icon
from .account_page import AccountPage
from .builds_page import BuildsPage
from .combat_review import read_page
from .api import AppApi, Requests
from .news import NewsPage
from .crafting_page import CraftingPage
from .database_page import DatabasePage
from .gathering_page import GatheringPage
from .gear_page import GearPage
from .header import (ASK_QUIT, SHOT_FAILED, STOPPED, Header, account_name, database_state, left_out, picture_scale,
                     window_picture)
from .header import stylesheet as header_stylesheet
from .history_page import HistoryPage
from .character_page import CharacterPage
from .combat_page import CombatPage
from .maps_page import MapsPage
from .meter_page import MeterPage
from .planner_page import PlannerPage
from .raid_page import RaidPage
from .pets_page import PetsPage, Toast
from .results import _dict, _truthy, js_text
from .timers_page import TimersPage
from .settings_page import SettingsPage, show_patch_notes
from .settings_words import launch_page, patch_notes, text_scale
from .update_bar import CLOSING as UPDATE_CLOSING, UpdateBar, UpdateWatch, available, bar_state
from .update_bar import stylesheet as update_stylesheet

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
#: The lists of Combat Logs an address can open (``#/combat/<list>``, pages/combat.js), and the Account page's tabs
#: (``#/account/<tab>``, pages/account.js).
COMBAT_LISTS = ("community", "owned", "saved", "identities")
ACCOUNT_TABS = ("logs", "parses", "legions", "security")


def web_route(page: str, pages=None) -> dict:
    """A page of the web interface read as app.js's ``route`` reads its address (``#/<page>``): the page shown (the
    Live Meter for none, the Build Planner for one not among ``pages``, the navigation's by default), and what that
    page reads after it: the list of Combat Logs asked for (``combat/<list>``), a featured encounter and its page
    (``featured/<id>/<view>?metric=``), or the Account page's tab and the legion opened on it
    (``account/<tab>/<legion>``)."""
    page = page if isinstance(page, str) else ""
    pages = PAGE_TITLES if pages is None else pages
    first = (page or "meter").split("/")[0]
    if first == "combat":
        asked = (re.split(r"[/?]", page) + [""])[1]
        return {"page": "combat", "list": asked if asked in COMBAT_LISTS else None}
    if first == "featured":
        pieces = page.split("?")
        parts = pieces[0].split("/")
        query = urllib.parse.parse_qs(pieces[1] if len(pieces) > 1 else "", keep_blank_values=True)
        return {"page": "featured", "id": urllib.parse.unquote(parts[1] if len(parts) > 1 else ""),
                "view": (parts[2] if len(parts) > 2 else "") or "race", "metric": (query.get("metric") or [None])[0]}
    if first == "account":
        parts = page.split("?")[0].split("/")
        tab = parts[1] if len(parts) > 1 and parts[1] in ACCOUNT_TABS else "logs"
        legion = parts[2] if len(parts) > 2 and re.fullmatch(r"lg_[0-9a-f]{12}", parts[2]) else None
        legion = legion if tab == "legions" else None
        return {"page": "account", "tab": tab, "legion": legion}
    return {"page": first if first in pages or first == "combat-log" else "planner"}


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
        self.setWindowIcon(app_icon())                   # the app's own icon, not Qt's placeholder (0.2.501)
        self.resize(1280, 820)
        self.leave_app = QApplication.quit                 # once the app has stopped (Quit)
        self.confirm = self._confirm
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # the header over everything, as the web pages' top bar (0.2.494): the game database, a newer version, the
        # account, the Discord, Application screenshot, the language (i18n.js ``picker``; 0.2.483), the theme and Quit
        self.language = i18n.picker(self.change_language)
        self.header = Header(self.language)
        self.update_chip = self.header.update_chip
        outer.addWidget(self.header)
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        outer.addWidget(body, 1)
        side = self.side = QWidget()
        side.setObjectName("navside")
        side.setFixedWidth(200)
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
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
                    widget = MeterPage(api, open_page=self.show_page, open_web=self.open_web, open_builds=self.open_builds,
                                       open_replay=self.open_replay)
                elif key == "settings":
                    widget = SettingsPage(api, self.open_in_web, open_page=self.show_page,
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
                    widget = CombatPage(api, self.open_web, open_builds=self.open_builds, open_replay=self.open_replay)
                elif key == "builds":
                    widget = BuildsPage(api)
                elif key == "raid":
                    widget = RaidPage(api)
                else:
                    widget = WebPage(key, title, self.open_in_web)
                self.page_index[key] = self.pages.addWidget(widget)
        self.nav.currentItemChanged.connect(self._navigate)
        layout.addWidget(side)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        # the quiet update (0.2.493): the status asked for as the web pages' top bar asks, its bar at the bottom left
        self.watch = UpdateWatch(api, self)
        self.update_bar = UpdateBar(central, self.watch.update_now, self.watch.on_close)
        self.toast = Toast(central)
        self.watch.changed.connect(self._status)
        self.watch.said.connect(self.toast.say)
        self.watch.closing.connect(self._closing)
        # the header's account: the Account page's own status read, its actions and its messages at the window's foot
        account = self.page("account")
        account.toast = self.toast
        account.status_read.connect(self._account_read)
        self.header.account_tab.connect(self.open_account)
        self.header.account_item.connect(lambda key: account.approve() if key == "approve" else account.website())
        self.header.sign_out.connect(account.sign_out)
        self.header.change_theme.connect(self.change_theme)
        self.header.quit_app.connect(self.quit_app)
        self.header.capture.connect(self.capture)
        self.page("settings").ui_saved.connect(self._ui_saved)
        from . import interface
        self.header.show_theme(theme.chosen_theme(interface.store()))
        self.shot_scaled = False
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.setStyleSheet(theme.app_stylesheet() + header_stylesheet() + update_stylesheet() + str(Toast.STYLE))
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

    def open_replay(self, plan: dict) -> bool:
        """A log's movement replay opened in the Raid Planner (``importPlan``, 0.2.492): the planner shown on it once
        it is the plan there (a plan worked on kept or discarded as asked); nothing when cancelled."""
        opened = self.page("raid").open_replay(plan)
        if opened:
            self.show_page("raid")
        return opened

    def _navigate(self, current, _previous) -> None:
        key = current.data(Qt.UserRole) if current is not None else None
        if key in self.page_index:
            left = self.pages.currentWidget()
            self.pages.setCurrentIndex(self.page_index[key])
            if left is not self.pages.currentWidget() and hasattr(left, "leave"):
                left.leave()                  # a page that starts afresh each time it is opened (Builds, 0.2.486)

    def open_web(self, page: str) -> None:
        """Open a page of the app: here when this window draws it (every page since 0.2.500, an analyzed encounter
        since 0.2.456 and a log's review since 0.2.457), else in the web interface."""
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
        """A page this window draws, shown as the web interface shows it at that address (``web_route``): an analyzed
        encounter, or a recorded or shared log, on Combat Logs; since 0.2.500 Combat Logs at the list asked for, back
        from a page shown in place of its views; a featured encounter's page there; the Account page on its tab, and
        any other page. A log's address this window cannot read opens in the web interface."""
        route = web_route(page, self.page_index)
        key = route["page"]
        if key == "combat-log":
            return self._open_log(page)
        shown = "combat" if key == "featured" else key
        if shown not in self.page_index:
            return False
        if key == "combat":
            combat = self.page("combat")
            combat.close_featured()
            if route["list"] is not None:
                combat.show_list(route["list"])
        elif key == "featured":
            self.page("combat").open_featured(route["id"], route["view"], route["metric"])
        elif key == "account":
            self.open_account(route["tab"], route["legion"])
            return True
        self.show_page(shown)
        return True

    def _open_log(self, page: str) -> bool:
        """An analyzed encounter, or a recorded or shared log, shown on Combat Logs (0.2.456, 0.2.457)."""
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
        self.watch.start()
        if self.requests is not None:                    # the header's account, as its menu reads it at first
            self.requests.get("account", "/api/account")
        self.read_ui()

    def read_ui(self) -> None:
        """The app's interface settings as the web page reads them as it loads: performance mode
        (``applyPerformanceMode``)."""
        if self.requests is not None:
            self.requests.get("ui", "/api/ui")

    def _ui_saved(self, key: str, value) -> None:
        if key == "performance_mode":                   # Settings' check box, applied as it is saved
            self.header.calm(value is True)

    def _status(self, s) -> None:
        """The app's status (``syncPill``): the game database's line and Quit's version in the header, the update's
        bar, else the newer release named where nothing downloads. A status the database's line cannot read changes
        nothing, as the web page's stops there."""
        if database_state(s) is None:
            return
        self.header.show_status(s)
        quiet = self.update_bar.show_state(bar_state(s))
        self.header.show_newer(available(s, quiet))

    # ---------------------------------------------------------------- the header
    def _account_read(self, s) -> None:
        self.header.show_account(account_name(s))

    def open_account(self, tab, legion=None) -> None:
        """A tab of the Account page from the header's menu, opened afresh (``None``: Sign in, the page's sign-in), or
        from an address (``#/account/<tab>``), with the legion it opens on its Legions tab."""
        self.page("account").open(tab, legion)
        self.show_page("account")

    def change_theme(self, chosen: str) -> None:
        """The header's theme button (``setTheme``): the next theme kept with the web pages' and shown."""
        from . import interface
        interface.store().setValue("theme", chosen)
        self.header.show_theme(chosen)
        self.change_look()

    def quit_app(self) -> None:
        """Quit (app.js ``#quit``): once asked, the app stops, the window says so in place of everything and closes."""
        if not self.confirm(ASK_QUIT):
            return
        if self.requests is None:
            self._stopped()
        else:
            self.requests.post("quit", "/api/quit", {})

    def _stopped(self) -> None:
        self.watch.stop()
        stopped = QLabel(STOPPED)
        stopped.setObjectName("muted")
        stopped.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        stopped.setContentsMargins(0, int(self.height() * 0.2), 0, 0)
        self.kept_while_closing = self.takeCentralWidget()
        self.setCentralWidget(stopped)
        QTimer.singleShot(250, self._leave)

    def _leave(self) -> None:
        self.close()
        self.leave_app()

    def capture(self) -> None:
        """Application screenshot (``A2Screenshot.capture``): the window with the page shown whole, below the fold too,
        shrunk to fit a PNG's limits, which the app saves among its screenshots; its button and what it says left out
        of the picture, as are a password's dots."""
        header = self.header
        header.shot.setEnabled(False)
        header.say(lm.SHOT_RENDERING)
        QCoreApplication.sendPostedEvents(None, QEvent.LayoutRequest)   # laid out as it is now
        frame, page = self.centralWidget(), self.pages.currentWidget()
        with left_out(header):
            scale = picture_scale(frame, header, page)
            image = window_picture(frame, header, self.side, page, scale) if scale >= 0.2 else None
        if image is None:
            self._shot_failed(lm.SHOT_TOO_LARGE)
            return
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        header.say(lm.SHOT_SAVING)
        self.shot_scaled = scale < 1
        png = "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")
        if self.requests is None:
            self._shot_failed("the app is not running")
            return
        self.requests.post("shot", "/api/screenshot", {"png": png}, origin=True)

    def _shot_failed(self, why: str) -> None:
        self.header.say(SHOT_FAILED + why)
        self.header.shot.setEnabled(True)

    def _replied(self, name: str, answer) -> None:
        if name == "account":
            self._account_read(answer)
        elif name == "ui":
            self.header.calm(_dict(answer).get("performance_mode") is True)
        elif name == "quit":
            self._stopped()
        elif name == "shot":
            error = _dict(answer).get("error")
            if _truthy(error):                            # refused in its answer (``api``)
                self._shot_failed(js_text(error))
                return
            self.header.say(lm.shot_words(answer, self.shot_scaled))
            self.header.shot.setEnabled(True)

    def _failed(self, name: str, why: str) -> None:
        if name == "account":
            self.header.show_account(None)
        elif name == "quit":
            self._stopped()                               # the app may stop before it answers
        elif name == "shot":
            self._shot_failed(why)

    def _confirm(self, question: str) -> bool:
        return QMessageBox.question(self, "Aion 2 Calc", question) == QMessageBox.Yes

    def _closing(self) -> None:
        """The app closes for its installer: the window says so in place of everything (the web page's body)."""
        closing = QLabel(UPDATE_CLOSING)
        closing.setObjectName("muted")
        closing.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        closing.setContentsMargins(0, int(self.height() * 0.2), 0, 0)
        self.kept_while_closing = self.takeCentralWidget()       # the pages kept, unseen, as the app closes
        self.setCentralWidget(closing)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "header", None) is not None:
            self.header.fit(self.width())
        if getattr(self, "update_bar", None) is not None and self.update_bar.isVisible():
            self.update_bar.place()

    def closeEvent(self, event) -> None:
        if getattr(self, "watch", None) is not None:
            self.watch.stop()
        if getattr(self, "requests", None) is not None:
            self.requests.stop()
        super().closeEvent(event)

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


def ui_settings(api: AppApi) -> dict:
    """The app's interface settings as the web page reads them as it starts (``/api/ui``); none where it does not
    answer."""
    try:
        ui = api.get("/api/ui")
    except (OSError, ValueError):
        return {}
    return ui if isinstance(ui, dict) else {}


def scale_text(api: AppApi, ui: dict | None = None) -> None:
    """The window at the app's text size (Settings → Text size, ``app_text_scale``), every word and the layout with it
    as a browser's zoom scales them (0.2.475). Qt takes it as the window opens (``QT_SCALE_FACTOR``), so a new size
    shows the next time the window opens; a size set by hand in the environment is left as it is. ``ui``: the settings
    already read."""
    if os.environ.get("QT_SCALE_FACTOR"):
        return
    size = text_scale(ui if ui is not None else ui_settings(api))
    if size != 100:
        os.environ["QT_SCALE_FACTOR"] = f"{size / 100:g}"


def first_page(fragment: str, ui: dict) -> str:
    """The page the window opens on (app.js's launch, 0.2.495): the one its address names (``#/settings`` from the
    tray's Settings), else the one Settings → App & data → **Page at launch** chose, else the Live Meter."""
    return fragment.strip("/") or launch_page(ui)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aion2calc.gui", description="Aion 2 Calc native interface")
    parser.add_argument("--url", default="http://127.0.0.1:8765/", help="the app's address")
    args = parser.parse_args(argv)
    from . import errors
    errors.record("window")                          # its errors on record, with no console to show them (0.2.503)
    from ..overlay import _ParentProcess
    base, _, fragment = args.url.partition("#")
    ui = ui_settings(AppApi(base))
    page = first_page(fragment, ui)
    if QApplication.instance() is None:
        scale_text(AppApi(base), ui)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_icon(app)                                  # the app's icon on its windows and dialogs (0.2.501)
    from . import interface
    interface.connect(AppApi(base))                  # the window's choices, kept by the app with the web pages' (0.2.482)
    i18n.install(i18n.language())                    # in the language the web pages show (0.2.483)
    theme.apply_look(*theme.look_of(interface.store()))   # and their theme and accent (0.2.484)
    window = MainWindow(AppApi(base), base, page, _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")))
    _follow_the_computer(app)
    window.show()
    window.start()
    return app.exec()
