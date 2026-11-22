"""The window's header (0.2.494): the web pages' top bar (index.html, app.js, account-view.js and screenshot.js)."""
from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import shiboken6  # noqa: E402
from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QPoint  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit  # noqa: E402

from aion2calc.gui import header as hd  # noqa: E402
from aion2calc.gui import i18n, interface, theme  # noqa: E402
from aion2calc.gui import live_meter as lm  # noqa: E402
from test_native_overlay_toolbar import settle  # noqa: E402
from test_native_settings import FakeApp, _refused  # noqa: E402

SIGNED_IN = {"signed_in": True, "here": True, "server": "https://logs.example", "config": True,
             "account": {"name": "Daeva", "logs": 12, "characters": [{"name": "Daeva"}]}}
SIGNED_OUT = {"signed_in": False, "server": "https://logs.example", "config": True, "methods": {}}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window_of(qapp, monkeypatch):
    """A window for one test, not started (no app to read), its choices in a store of their own; dark again after."""
    from aion2calc.gui import window as native_window
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)
    made = []

    def make(app=None, width=1400):
        window = native_window.MainWindow(app)
        window.resize(width, 820)
        window.show()
        QCoreApplication.processEvents()
        made.append(window)
        return window
    yield make
    for window in made:
        if shiboken6.isValid(window):
            window.close()
    theme.apply_look("dark")


class OriginApp(FakeApp):
    """The fake app, noting which requests named the app's own origin."""

    def __init__(self, answers=None):
        super().__init__(answers)
        self.origins = []

    def post(self, path, payload, timeout=None, origin=False):
        self.origins.append((path, origin))
        return super().post(path, payload, timeout)


def test_the_header_s_words():
    # the game database: its update as it runs, else its items, the dot red after errors
    running = {"running": True, "phase": "items", "done": 120, "total": 480}
    assert hd.database_state({"sync": running, "db": {"items": 5}}) == ("run", "updating database · items 120/480")
    assert hd.database_state({"sync": {"running": True, "phase": "icons"}}) == ("run", "updating database · icons ")
    assert hd.database_state({"sync": {"running": True, "total": 9}}) == ("run", "updating database ·  undefined/9")
    assert hd.database_state({"sync": {"running": True, "done": None, "total": 9.0}})[1] == "updating database ·  null/9"
    assert hd.database_state({"sync": None, "db": {"items": 48213}}) == ("ok", "database 48,213 items")
    assert hd.database_state({"sync": {"errors": ["x"]}, "db": {"items": 1}}) == ("err", "database 1 items")
    assert hd.database_state({"sync": {"errors": []}, "db": {"items": None}}) == ("ok", "database — items")
    assert hd.database_state({"sync": {"errors": 3}, "db": 7}) == ("ok", "database — items")
    assert hd.database_state({"sync": {"errors": ["x"]}}) is None and hd.database_state(None) is None   # no database
    # ``n0``: rounded, grouped by commas; what reads as no number a dash
    assert [hd.n0(x) for x in (1234567.4, "12", True, [5], "", 2.5, -2.5, -0.4)] == [
        "1,234,567", "12", "1", "5", "0", "3", "-2", "-0"]
    assert [hd.n0(x) for x in (None, {}, "1,000", float("nan"))] == ["—"] * 4
    assert hd.n0(float("inf")) == "∞" and hd.n0(2 ** 60) == "1,152,921,504,606,847,000"
    # Quit's tip with the version; the theme's turns and tips
    assert hd.quit_tip({"version": "0.2.494"}) == "Stop the app (version 0.2.494)"
    assert hd.quit_tip({}) == hd.quit_tip({"version": 0}) == "Stop the app (version )"
    assert [hd.theme_after(t) for t in ("system", "light", "dark", "neon", None)] == [
        "light", "dark", "system", "system", "system"]
    assert hd.theme_tip("system") == "Theme: follow the computer (click to change)"
    assert hd.theme_tip("dark") == "Theme: dark (click to change)" and hd.theme_tip("neon") == "Theme: neon (click to change)"
    # the account the header names: none signed out, or signed in on another log server
    assert hd.account_name(SIGNED_IN) == "Daeva" and hd.account_name({**SIGNED_IN, "here": False}) is None
    assert hd.account_name(SIGNED_OUT) is None and hd.account_name(None) is None and hd.account_name("x") is None
    assert hd.account_name({"signed_in": True}) is None and hd.account_name({"signed_in": True, "account": {"name": ""}}) is None
    assert hd.account_name({"signed_in": True, "account": {"name": 42}}) == "42"
    # the PNG's limits: 30,000 pixels a side and 40 million in all
    assert lm.shot_scale(1400, 2000) == 1 and lm.shot_scale(1000, 60000) == 0.5
    assert lm.shot_scale(10000, 10000) == pytest.approx(0.6324555, rel=1e-6)


def test_the_header_shows_the_status_the_account_and_the_theme(qapp):
    opened = []
    language = QComboBox()
    header = hd.Header(language, open_link=opened.append)
    header.resize(1500, 60)
    header.show()
    said = {name: [] for name in ("tab", "item", "out", "theme", "quit", "shot")}
    header.account_tab.connect(said["tab"].append)
    header.account_item.connect(said["item"].append)
    header.sign_out.connect(said["out"].append)
    header.change_theme.connect(said["theme"].append)
    header.quit_app.connect(lambda: said["quit"].append(True))
    header.capture.connect(lambda: said["shot"].append(True))
    # as the page first draws it
    assert header.database.text() == "database" and header.dot.state == "ok" and header.quit_button.toolTip() == "Stop the app"
    assert header.account.text() == "Sign in" and header.account.menu() is None and header.theme_button.text() == "◐"
    assert header.language is language and language.parentWidget() is header
    # the database updating: the dot pulses; a status it cannot read leaves the line as it was
    header.show_status({"sync": {"running": True, "phase": "items", "done": 3, "total": 9}, "version": "0.2.494"})
    assert header.database.text() == "updating database · items 3/9" and header.dot.state == "run"
    assert header.dot.pulse.state() == QAbstractAnimation.State.Running and header.quit_button.toolTip() == "Stop the app (version 0.2.494)"
    header.show_status({"sync": {"errors": ["x"]}, "version": "0.2.495"})
    assert header.database.text() == "updating database · items 3/9" and header.dot.state == "run"
    assert header.quit_button.toolTip() == "Stop the app (version 0.2.494)"
    header.show_status({"sync": {"errors": ["x"]}, "db": {"items": 7}})
    assert header.database.text() == "database 7 items" and header.dot.state == "err"
    assert header.dot.pulse.state() == QAbstractAnimation.State.Stopped and header.dot.opacity == 1.0
    # a newer version, a link to its page; none
    header.show_newer({"words": "Version 0.2.500 available", "url": "https://example.org/r?a=1&b=2"})
    assert header.update_chip.isVisible() and 'href="https://example.org/r?a=1&amp;b=2"' in header.update_chip.text()
    header.show_newer(None)
    assert not header.update_chip.isVisible()
    # Sign in opens the Account page's sign-in; signed in, the name and what an account offers
    header.account.click()
    assert said["tab"] == [None]
    header.show_account("Daeva")
    actions = header.account.menu().actions()
    assert header.account.text() == "Daeva ▾" and [a.text() for a in actions] == [
        "My logs", "Top parses", "Legions", "Sign-in & security", "Approve a website sign-in", "Open the website signed in",
        "Sign out"]
    for action in actions:
        action.trigger()
    assert said["tab"] == [None, "logs", "parses", "legions", "security"] and said["item"] == ["approve", "website"]
    assert said["out"] == ["Daeva"]
    header.show_account(None)
    assert header.account.text() == "Sign in" and header.account.menu() is None
    # the theme: the next one; one that is none of them shows no sign and turns to the first
    header.theme_button.click()
    header.show_theme("neon")
    assert header.theme_button.text() == "" and header.theme_button.toolTip() == "Theme: neon (click to change)"
    header.theme_button.click()
    assert said["theme"] == ["light", "system"]
    header.show_theme("dark")
    assert header.theme_button.text() == "☾" and header.theme_button.toolTip() == "Theme: dark (click to change)"
    # the Discord, Application screenshot and Quit
    discord = next(b for b in header.findChildren(type(header.shot)) if b.toolTip() == hd.DISCORD_TIP)
    discord.click()
    header.shot.click()
    header.quit_button.click()
    assert opened == [hd.DISCORD_URL] and said["shot"] == [True] and said["quit"] == [True]
    header.close()


def test_the_header_s_line_wraps_as_the_top_bar_does(qapp):
    header = hd.Header(QComboBox())
    header.show_status({"db": {"items": 48213}})
    header.show_account("Daeva")
    one_line = header.line.sizeHint().width()
    header.resize(one_line + 40, header.heightForWidth(one_line + 40))
    header.show()
    QCoreApplication.processEvents()
    brand, pill = header.line.itemAt(0).widget(), header.line.push
    middles = [header.line.itemAt(i).widget().geometry().center().y() for i in range(header.line.count())
               if not header.line.itemAt(i).isEmpty()]
    assert max(middles) - min(middles) <= 1 and header.heightForWidth(one_line + 40) < 70     # one line
    assert pill.x() > brand.geometry().right() + 18 and header.quit_button.parentWidget() is header
    assert header.width() - header.quit_button.geometry().right() - 1 == 22                   # the rest pushed right
    narrow = header.heightForWidth(700)
    assert narrow > header.heightForWidth(one_line + 40)                                     # carried onto more lines
    assert header.line.minimumSize().width() <= brand.sizeHint().width() + 44
    # 1,180 pixels or less: the database's dot alone, the parts closer together
    header.fit(1180)
    assert not header.database.isVisibleTo(header) and header.line.gaps == (10, 10)
    assert header.line.contentsMargins().left() == 14
    header.fit(1181)
    assert header.database.isVisibleTo(header) and header.line.gaps == (18, 10)
    header.close()


def test_the_header_s_menu_in_the_language_shown(qapp, monkeypatch):
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    try:
        i18n.install("de")
        header = hd.Header(QComboBox())
        header.show_account("Daeva")
        assert [a.text() for a in header.account.menu().actions()][:2] == ["Meine Logs", "Beste Parses"]
        assert header.account.menu().actions()[-1].text() == "Abmelden"
        header.show_account(None)
        assert header.account.text() == "Anmelden"
        header.show_status({"version": "0.2.494", "db": {}})
        assert header.quit_button.toolTip() == "App beenden (Version 0.2.494)" and header.shot.text() == "Screenshot der App"
        header.close()
    finally:
        i18n.uninstall()


def test_the_window_s_header_shows_the_status_and_the_account(window_of):
    app = FakeApp({("GET", "/api/account", None): SIGNED_IN, ("POST", "/api/account", "signout"): {"ok": True},
                   ("POST", "/api/account", "website"): {"ok": True}})
    window = window_of(app)
    header = window.header
    assert window.language is header.language and window.update_chip is header.update_chip
    assert header.mapTo(window, QPoint(0, 0)).y() == 0
    assert window.side.mapTo(window.centralWidget(), QPoint(0, 0)).y() == header.height()
    window._status({"sync": {"running": True, "phase": "items", "done": 3, "total": 9}, "db": {"items": 5},
                    "version": "0.2.494", "update": {"version": "0.2.500", "url": "https://example.org/r"}})
    assert header.database.text() == "updating database · items 3/9" and header.update_chip.isVisible()
    assert header.quit_button.toolTip() == "Stop the app (version 0.2.494)"
    window._status({"sync": {"errors": ["x"]}, "version": "0.2.495"})       # a line it cannot read: nothing changes
    assert header.database.text() == "updating database · items 3/9" and header.update_chip.isVisible()
    assert header.quit_button.toolTip() == "Stop the app (version 0.2.494)" and header.dot.state == "run"
    window.resize(1100, 820)                                                 # the database's dot alone
    settle(lambda: not header.database.isVisible())
    # the account as the menu first reads it
    window.requests.get("account", "/api/account")
    settle(lambda: header.account.text() == "Daeva ▾")
    # Top parses from the menu: the Account page opened afresh on it
    account = window.page("account")
    account.shared["page"] = 3
    next(a for a in header.account.menu().actions() if a.text() == "Top parses").trigger()
    assert window.current_page() == "account" and account.tab == "parses" and account.shared["page"] == 1
    settle(lambda: account.state is not None and account.state.get("signed_in"))
    # the website signed in, and a website sign-in approved by its code: asked from any page, said at the window's foot
    window.show_page("meter")
    account.ask = lambda question, text: "ab12cd34"
    next(a for a in header.account.menu().actions() if a.text() == "Approve a website sign-in").trigger()
    settle(lambda: window.toast.isVisible())
    assert window.toast.text() and account.toast is window.toast and window.current_page() == "meter"
    next(a for a in header.account.menu().actions() if a.text() == "Open the website signed in").trigger()
    settle(lambda: app.sent("POST", "/api/account")[-1][2] == {"action": "website"})
    # Sign out, once asked: the header says Sign in once the page reads the account again
    asked = []
    account.confirm = lambda question: asked.append(question) or True
    app.answers[("GET", "/api/account", None)] = SIGNED_OUT
    next(a for a in header.account.menu().actions() if a.text() == "Sign out").trigger()
    settle(lambda: header.account.text() == "Sign in")
    assert asked == ["Sign out of Daeva?"] and {"action": "signout"} in [b for _m, _p, b in app.sent("POST", "/api/account")]
    # Sign in: the Account page, where an account is made
    account.state = None
    header.account.click()
    assert window.current_page() == "account" and account.tab == "logs"
    settle(lambda: account.state is not None)
    # an account status it cannot read: Sign in
    header.show_account("Daeva")
    app.answers[("GET", "/api/account", None)] = _refused("/api/account", 500, "down")
    window.requests.get("account", "/api/account")
    settle(lambda: header.account.text() == "Sign in")


def test_the_header_s_theme_button_turns_the_look(window_of):
    window = window_of()
    store = interface.store()
    assert window.header.theme_button.text() == "◐"
    window.header.theme_button.click()                                      # light: kept, the window drawn again in it
    again = window.again
    assert store.value("theme") == "light" and theme.LOOK["shown"] == "light"
    assert again.header.theme_button.text() == "☀" and again.header.theme_button.toolTip() == "Theme: light (click to change)"
    again.header.theme_button.click()
    assert store.value("theme") == "dark" and theme.LOOK["shown"] == "dark" and again.again.header.theme_button.text() == "☾"
    again.again.close()
    store.setValue("theme", "neon")                                          # none of them: no sign; the first next
    other = window_of()
    assert other.header.theme_button.text() == "" and other.header.theme_button.toolTip() == "Theme: neon (click to change)"
    other.header.theme_button.click()
    assert store.value("theme") == "system" and other.header.theme_button.text() == "◐"
    other.again.close()


def test_quit_stops_the_app_once_asked(window_of):
    app = FakeApp({("POST", "/api/quit", None): {"stopping": True}})
    window = window_of(app)
    asked, left = [], []
    window.confirm = lambda question: asked.append(question) or False
    window.leave_app = lambda: left.append(True)
    window.header.quit_button.click()
    assert asked == [hd.ASK_QUIT] and not app.sent("POST", "/api/quit")
    window.confirm = lambda question: True
    window.header.quit_button.click()
    settle(lambda: isinstance(window.centralWidget(), QLabel))
    assert window.centralWidget().text() == hd.STOPPED and app.sent("POST", "/api/quit") == [("POST", "/api/quit", {})]
    settle(lambda: left)                                                     # then the window closes
    assert not window.isVisible()
    # an app that stops before it answers: the same
    gone = window_of(FakeApp({("POST", "/api/quit", None): ConnectionResetError("closed")}))
    gone.confirm = lambda question: True
    gone.leave_app = lambda: None
    gone.header.quit_button.click()
    settle(lambda: isinstance(gone.centralWidget(), QLabel))
    assert gone.centralWidget().text() == hd.STOPPED


def test_application_screenshot_saves_the_window_with_the_page_whole(window_of, monkeypatch):
    from aion2calc.gui import window as native_window
    saved = {"file": "C:/aion2calc/screenshots/application-1.png", "bytes": 10}
    app = OriginApp({("POST", "/api/screenshot", None): [
        saved, _refused("/api/screenshot", 403, "This action requires the local application origin."),
        {"error": "Application PNG could not be validated."}, saved]})
    window = window_of(app, width=1200)
    window.show_page("settings")
    page = window.pages.currentWidget()
    area = hd.main_scroll(page)
    for i in range(60):                                                      # a page longer than the window
        area.widget().layout().addWidget(QLabel(f"Line {i}"))
    secret = QLineEdit("hunter2")
    secret.setEchoMode(QLineEdit.Password)
    area.widget().layout().addWidget(secret)
    settle(lambda: area.widget().height() > area.viewport().height() + 600)
    area.verticalScrollBar().setValue(200)
    frame, header = window.centralWidget(), window.header
    with hd.left_out(header):                                                # laid out as the picture shows it
        whole = hd.window_size(frame, header, page)
        lines = header.height() - header.heightForWidth(header.width())
    assert header.shot_box.isVisible() and whole.width() == frame.width()
    assert whole.height() == frame.height() + area.widget().height() - area.viewport().height() - max(0, lines)
    header.shot.click()
    assert header.shot_status.text() == lm.SHOT_SAVING and not header.shot.isEnabled()
    settle(lambda: header.shot.isEnabled())
    assert header.shot_status.text() == "Application screenshot saved: C:/aion2calc/screenshots/application-1.png"
    assert [origin for path, origin in app.origins if path == "/api/screenshot"] == [True]   # the app's own origin
    png = app.sent("POST", "/api/screenshot")[0][2]["png"]
    assert png.startswith("data:image/png;base64,")
    image = QImage.fromData(base64.b64decode(png.split(",", 1)[1]), "PNG")
    assert (image.width(), image.height()) == (whole.width(), whole.height())
    assert area.verticalScrollBar().value() == 200 and header.shot_box.isVisible()        # the window as it was
    assert secret.echoMode() == QLineEdit.Password and secret.text() == "hunter2"
    # refused, and refused in its answer: said
    header.shot.click()
    settle(lambda: header.shot.isEnabled())
    assert header.shot_status.text() == hd.SHOT_FAILED + "This action requires the local application origin."
    header.shot.click()
    settle(lambda: header.shot.isEnabled())
    assert header.shot_status.text() == hd.SHOT_FAILED + "Application PNG could not be validated."
    # past a PNG's limits: shrunk to fit and said so; too far past them, refused before anything is drawn
    monkeypatch.setattr(native_window, "picture_scale", lambda frame, header, page: 0.5)
    with hd.left_out(header):
        whole = hd.window_size(frame, header, page)
    header.shot.click()
    settle(lambda: header.shot.isEnabled())
    assert header.shot_status.text().endswith(" (scaled to fit PNG limits)")
    png = app.sent("POST", "/api/screenshot")[-1][2]["png"]
    image = QImage.fromData(base64.b64decode(png.split(",", 1)[1]), "PNG")
    assert (image.width(), image.height()) == (round(whole.width() / 2), round(whole.height() / 2))
    monkeypatch.setattr(native_window, "picture_scale", lambda frame, header, page: 0.19)
    sent = len(app.sent("POST", "/api/screenshot"))
    header.shot.click()
    assert header.shot_status.text() == hd.SHOT_FAILED + lm.SHOT_TOO_LARGE and header.shot.isEnabled()
    assert len(app.sent("POST", "/api/screenshot")) == sent
