"""The native Account page, part 1 (0.2.447): the account offered when signed out and its ways in (a new account, a
link code, recovery, Discord), the signed-in page's name and tabs, and Sign-in & security (rename, a website sign-in
approved or denied, the website opened, the places signed in, the recent activity, closing the account), as
pages/account.js and account-view.js show them, off screen over a fake app answering as the app does.
"""
import json
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from aion2calc.gui import account as ac  # noqa: E402
from aion2calc.gui.account_page import AccountPage  # noqa: E402
from aion2calc.gui.news import when as moment  # noqa: E402
from aion2calc.gui.timers_page import Fold  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

SERVER = "https://logs.example"
SESSIONS = {"sessions": [{"id": 7, "label": "Desktop-1", "kind": "app", "created_at": 1700000000, "last_used": 1700003600,
                          "current": True},
                         {"id": 9, "label": "Firefox on Linux", "kind": "web", "created_at": 1700001000, "last_used": None}]}
ACTIVITY = {"activity": [{"created_at": 1700000000, "action": "created", "note": ""},
                         {"created_at": 1700000500, "action": "signin_approved", "note": "Firefox on Linux"},
                         {"created_at": 1700000600, "action": "something_new", "note": "x"}]}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


class FakeApp:
    """The app as the Account page asks it (``/api/account``), signed out until a way in succeeds."""

    def __init__(self, signed_in=False, discord=True, server=SERVER, here=True, polls=("pending", "approved")):
        self.signed_in, self.discord, self.server, self.here = signed_in, discord, server, here
        self.name = "Daeva" if signed_in else None
        self.polls = list(polls)
        self.calls, self.posts = [], []

    def status(self):
        if not self.signed_in:
            return {"signed_in": False, "server": self.server, "account_server": None,
                    "config": {"methods": {"discord": self.discord}} if self.server else None}
        return {"signed_in": True, "here": self.here, "server": self.server, "account_server": "https://other.example",
                "account": {"id": 1, "name": self.name, "logs": 12, "characters": [{"id": 1}],
                            "discord": {"name": "daeva#1"}, "passkeys": 1, "apps": 2}}

    def get(self, path, timeout=None):
        self.calls.append(path)
        assert path == "/api/account"
        return self.status()

    def post(self, path, body, timeout=None):
        assert path == "/api/account"
        self.posts.append(json.loads(json.dumps(body)))
        action = body["action"]
        if action == "register":
            if body.get("name") == "taken":
                raise ValueError("ValueError: That name is taken")
            return self._in(body.get("name") or "Daeva1")
        if action == "link":
            if body.get("code") != "ABCD-EFGH":
                raise ValueError("That code is not valid")
            return self._in("Linked")
        if action == "recover":
            return self._in("Recovered")
        if action == "discord-start":
            return {"waiting": True, "interval": 0.01}
        if action == "discord-poll":
            status = self.polls.pop(0) if self.polls else "expired"
            return self._in("FromDiscord") | {"status": "approved"} if status == "approved" else {"status": status}
        if action in ("signout",):
            self.signed_in = False
            return {"signed_in": False}
        if action == "website":
            return {"opened": True}
        if action == "request":
            return self.request(body["method"], body["path"], body.get("body"))
        raise AssertionError(body)

    def _in(self, name):
        self.signed_in, self.name = True, name
        return self.status()

    def request(self, method, path, body):
        if (method, path) == ("GET", "/api/v1/account/sessions"):
            return json.loads(json.dumps(SESSIONS))
        if (method, path) == ("GET", "/api/v1/account/activity"):
            return json.loads(json.dumps(ACTIVITY))
        if method == "GET" and path.startswith("/api/v1/account/signin/lookup?code="):
            return {"code": "AB12CD34", "browser": "Firefox on Linux", "same_network": False}
        if path in ("/api/v1/account/signin/approve", "/api/v1/account/signin/deny"):
            return {}
        if path == "/api/v1/account/name":
            if body["name"] == "x":
                raise ValueError("Choose 2-24 letters or digits")
            self.name = body["name"]
            return {"account": {"name": self.name}}
        if path == "/api/v1/account/sessions/revoke":
            return {"signed_out": 1 if "id" in body else 2}
        if path == "/api/v1/account/delete":
            self.signed_in = False
            return {"deleted": True}
        raise AssertionError((method, path))


def _page(app, **kwargs):
    page = AccountPage(app, **kwargs)
    page.resize(1100, 1600)
    page.show()
    settle(lambda: page.state is not None)
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _sent(app, path):
    """The last request for the account sent to this path."""
    return next(p for p in reversed(app.posts) if p.get("path") == path)


def _button(widget, words):
    def shown():
        return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)
    settle(lambda: shown() is not None)
    return shown()


def test_the_account_words():
    elsewhere = ac.status_view({"signed_in": True, "here": False, "account_server": "https://other.example", "server": SERVER})
    assert elsewhere["signed_in"] is False and elsewhere["elsewhere"] == "https://other.example"
    assert ac.status_view({"signed_in": True, "here": True})["signed_in"] is True and ac.status_view(None) == {}
    assert ac.signed_out_notes(elsewhere | {"ended": "Your sign-in ended", "config": {}}) == [
        ("ended", "Your sign-in ended"),
        ("elsewhere", f"This app is signed in on https://other.example, not on the server Settings uses now ({SERVER}).")]
    assert ac.signed_out_notes({"server": ""}) == [("server", ac.CHOOSE_SERVER)]
    assert ac.signed_out_notes({"server": SERVER, "error": "offline", "config": None}) == [("error", "offline")]
    assert ac.signed_out_notes({"server": SERVER, "error": "offline", "config": {"methods": {}}}) == []
    assert ac.can_create({"server": SERVER, "config": {}}) and not ac.can_create({"server": SERVER, "config": None})
    assert not ac.can_create({"server": SERVER, "config": {}, "elsewhere": "x"}) and not ac.can_create({"config": {}})
    assert ac.discord_offered({"config": {"methods": {"discord": True}}}) and not ac.discord_offered({"config": None})
    assert ac.title_line({"name": "Daeva", "logs": 1, "characters": []}) == ("Daeva", "1 log · 0 characters")
    assert ac.title_line({"name": "Daeva", "characters": [{}]}) == ("Daeva", "0 logs · 1 character")
    assert ac.ways_line({"discord": {"name": "daeva#1"}, "passkeys": 1, "apps": 2}) == "Discord: daeva#1 · 1 passkey · 2 desktop apps"
    assert ac.ways_line({}) == "Discord: not linked · 0 passkeys · 0 desktop apps"
    current, other = ac.session_rows(SESSIONS)
    assert current == {"where": "Desktop-1", "kind": "desktop app", "since": moment(1700000000000),
                       "used": moment(1700003600000), "current": True, "id": 7}
    assert (other["kind"], other["used"], other["current"]) == ("website", "—", False)
    assert ac.activity_rows(ACTIVITY) == [(moment(1700000000000), "Account created", ""),
                                          (moment(1700000500000), "Website sign-in approved", "Firefox on Linux"),
                                          (moment(1700000600000), "something_new", "x")]
    assert ac.approve_question({"browser": "Edge", "same_network": True}) == (
        "Sign in Edge on the website as your account?\n\nIt started on this computer's internet connection.\n\n"
        "Approve only a sign-in you started yourself.")
    assert "did NOT start" in ac.approve_question({"same_network": False}) and "cannot tell" in ac.approve_question({})
    assert ac.when(0) == "—" and ac.when(None) == "—" and ac.when("1700000000") == moment(1700000000000)
    assert ac.plain("PermissionError: The app does not send that request") == "The app does not send that request"
    assert ac.lookup_path("ab 12/cd") == "/api/v1/account/signin/lookup?code=ab%2012%2Fcd"
    assert ac.signed_out_answer("Sign in again on this app") and not ac.signed_out_answer("offline")
    assert ac.revoked({"signed_out": 2}) == "2 signed out" and ac.signed_in_as({"account": {"name": "Daeva"}}) == "Signed in as Daeva"


def test_signed_out_and_the_ways_in(qapp):
    app = FakeApp()
    page = _page(app)
    texts = _texts(page)
    assert ac.INTRO in texts and ac.NO_PASSWORD in texts and page.create.isEnabled()
    # a new account: refused with why, the button on again; then made, and signed in
    page.name_field.setText("taken")
    page.create.click()
    settle(lambda: page.message.text() == "That name is taken")
    assert page.create.isEnabled() and app.posts[-1] == {"action": "register", "name": "taken"}
    page.name_field.setText("  Daeva  ")
    page.create.click()
    settle(lambda: page.state.get("signed_in"))
    assert app.posts[-1] == {"action": "register", "name": "Daeva"} and page.toast.text() == "Signed in as Daeva"
    assert "Daeva" in _texts(page) and "12 logs · 1 character" in _texts(page)
    # signed out from the page (the web page's header menu), once asked
    asked = []
    page.confirm = lambda question: asked.append(question) or True
    _button(page, "Sign out").click()
    settle(lambda: page.state is not None and not page.state.get("signed_in"))
    assert asked == ["Sign out of Daeva?"] and app.posts[-1] == {"action": "signout"}
    # a link code from the website, refused then taken; recovery
    page.code_field.setText("WRONG")
    page.link.click()
    settle(lambda: page.message.text() == "That code is not valid")
    page.code_field.setText("ABCD-EFGH")
    page.link.click()
    settle(lambda: page.state.get("signed_in"))
    assert app.posts[-1] == {"action": "link", "code": "ABCD-EFGH"} and page.toast.text() == "Signed in as Linked"
    app.signed_in = False
    page.render()
    settle(lambda: not page.state.get("signed_in"))
    page.recover.click()
    settle(lambda: page.state.get("signed_in"))
    assert app.posts[-1] == {"action": "recover"}


def test_discord_sign_in(qapp):
    app = FakeApp()
    page = _page(app)
    page.discord_button.click()
    settle(lambda: page.message.text() == ac.DISCORD_WAIT or page.state.get("signed_in"))
    settle(lambda: page.state.get("signed_in"))                              # pending, then approved
    assert [p["action"] for p in app.posts] == ["discord-start", "discord-poll", "discord-poll"]
    assert page.toast.text() == "Signed in as FromDiscord"
    ended = FakeApp(polls=("pending", "expired"))
    page = _page(ended)
    page.discord_button.click()
    settle(lambda: page.message.text() == ac.DISCORD_ENDED)
    assert page.discord_button.isEnabled() and not ended.signed_in
    none = _page(FakeApp(discord=False))
    assert none.discord_button is None and ac.DISCORD not in [b.text() for b in none.findChildren(QPushButton)]


def test_signed_out_notes(qapp):
    elsewhere = FakeApp(signed_in=True, here=False)
    page = _page(elsewhere)
    texts = _texts(page)
    assert any(t.startswith("This app is signed in on https://other.example") for t in texts) and not page.create.isEnabled()
    _button(page, "Sign out").click()
    settle(lambda: elsewhere.posts and not page.state.get("elsewhere"))
    assert elsewhere.posts[-1] == {"action": "signout"} and page.create.isEnabled()
    serverless = _page(FakeApp(server=""))
    assert ac.CHOOSE_SERVER in _texts(serverless) and not serverless.create.isEnabled()


def test_signed_in_and_security(qapp):
    opened, asked, said = [], [], []
    answers = {ac.RENAME_ASK: "NewName", ac.CODE_ASK: "  ab12cd34 "}
    app = FakeApp(signed_in=True)
    page = _page(app, open_web=opened.append, ask=lambda question, text: (asked.append((question, text)), answers[question])[1],
                 confirm=lambda question: (asked.append(question), True)[1], alert=said.append)
    texts = _texts(page)
    assert "Daeva" in texts and ac.ON_THE_WEB["logs"] in texts                          # My logs: on the web page for now
    _button(page, "Open them on the web page").click()
    assert opened == ["account/logs"]
    tab = next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Sign-in & security")
    tab.click()
    settle(lambda: any(t == "Recent activity" for t in _texts(page)))
    texts = _texts(page)
    for words in ("Ways in", ac.WAYS_NOTE, "Discord: daeva#1 · 1 passkey · 2 desktop apps", "this one", ac.RECENT_NOTE,
                  "Website sign-in approved", "something_new"):
        assert any(words in t for t in texts), words
    assert any("Firefox on Linux" in t and "website" in t for t in texts)
    # rename: asked with the name as it is, then said over the tab
    _button(page, "Rename").click()
    settle(lambda: "Renamed" in _texts(page))
    assert asked[0] == (ac.RENAME_ASK, "Daeva") and app.name == "NewName" and page.tab == "security"
    answers[ac.RENAME_ASK] = "x"
    _button(page, "Rename").click()
    settle(lambda: "Choose 2-24 letters or digits" in _texts(page))               # refused: why, over the tab
    # sign out one place, then everywhere else once asked
    def session_button():
        return next((b for b in page.findChildren(QPushButton) if b.text() == "Sign out" and b.isVisibleTo(page)
                     and b.parentWidget() is not None and b.parentWidget().objectName() == "tcellBox"), None)
    settle(lambda: session_button() is not None)                                  # the tab's places, read again
    session_button().click()
    settle(lambda: "Signed out there" in _texts(page))
    assert _sent(app, "/api/v1/account/sessions/revoke")["body"] == {"id": 9}
    _button(page, "Sign out everywhere else").click()
    settle(lambda: "2 signed out" in _texts(page))
    assert ac.END_ALL_ASK in asked and _sent(app, "/api/v1/account/sessions/revoke")["body"] == {"all": True}
    # a website sign-in: looked up by its code, said, approved; then denied
    _button(page, ac.APPROVE).click()
    settle(lambda: page.toast.text() == "Website signed in")
    lookup = next(p for p in app.posts if p.get("path", "").startswith("/api/v1/account/signin/lookup"))
    assert lookup["path"] == "/api/v1/account/signin/lookup?code=ab12cd34"
    assert any(isinstance(q, str) and q.startswith("Sign in Firefox on Linux on the website") and "did NOT start" in q for q in asked)
    assert _sent(app, "/api/v1/account/signin/approve") == {"action": "request", "method": "POST",
                                                            "path": "/api/v1/account/signin/approve", "body": {"code": "AB12CD34"}}
    page.confirm = lambda question: False
    _button(page, ac.APPROVE).click()
    settle(lambda: page.toast.text() == "Sign-in denied")
    assert _sent(app, "/api/v1/account/signin/deny")["body"] == {"code": "AB12CD34"}
    _button(page, ac.WEBSITE).click()
    settle(lambda: app.posts[-1] == {"action": "website"})
    # closing the account (folded): the words typed first, then closed with its logs
    next(f for f in page.findChildren(Fold) if f.button.text() == ac.CLOSE).button.click()
    page.close_words.setText("delete it")
    _button(page, ac.CLOSE).click()
    assert said == [ac.CLOSE_TYPE]
    page.close_words.setText("delete my account")
    page.close_logs.setChecked(True)
    _button(page, ac.CLOSE).click()
    settle(lambda: page.state is not None and not page.state.get("signed_in"))
    assert _sent(app, "/api/v1/account/delete")["body"] == {"confirm": "delete my account", "delete_logs": True}
    assert ac.INTRO in _texts(page)


def test_the_window_draws_account_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("account"), AccountPage) and not isinstance(window.page("account"), WebPage)
    assert isinstance(window.page("builds"), WebPage)                    # not moved over yet
