"""The native Account page (0.2.447): the account offered when signed out and its ways in (a new account, a link code,
recovery, Discord), the signed-in page's name and tabs, Sign-in & security (rename, a website sign-in approved or
denied, the website opened, the places signed in, the recent activity, closing the account), since 0.2.448 My logs and
Top parses, and since 0.2.449 Legions, as pages/account.js and account-view.js show them, off screen over a fake app
answering as the app does.
"""
import json
import os
import sys
import urllib.parse

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton  # noqa: E402

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
LOGS = [{"id": "lg1", "title": "Best pull", "boss": "Black Smoke Murute", "uploader": "TestSorc", "created_at": 1700000000,
         "duration": 125, "visibility": "public", "segment": 2},
        {"id": "lg2", "title": "", "boss": "Ice Queen", "uploader": None, "created_at": 1700000300, "duration": 3725,
         "visibility": "private", "held": True}]
PARSES = [{"boss": "Black Smoke Murute", "difficulty": "normal", "character": "TestSorc", "server": 2102, "class": "sorcerer",
           "dps": 41234.6, "parse": 99.4, "parse_rank": 2, "parse_runs": 40, "uploaded_at": 1700000000, "log": "lg1",
           "segment": 2, "attempts": 3},
          {"boss": "Ice Queen", "difficulty": "hard", "character": "Alt", "server": 2102, "class": "cleric", "dps": 9000,
           "parse": None, "uploaded_at": 1700000300, "log": "lg2"},
          {"boss": "Black Smoke Murute", "difficulty": "hard", "character": "TestSorc", "server": 2102, "class": "sorcerer",
           "dps": 52000, "parse": 100, "parse_rank": 1, "parse_runs": 4, "provisional": True, "uploaded_at": 1700000600,
           "log": "lg3"}]
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

    def __init__(self, signed_in=False, discord=True, server=SERVER, here=True, polls=("pending", "approved"), old_server=False):
        self.signed_in, self.discord, self.server, self.here = signed_in, discord, server, here
        self.name = "Daeva" if signed_in else None
        self.polls = list(polls)
        self.calls, self.posts = [], []
        self.logs = json.loads(json.dumps(LOGS))
        self.old_server = old_server                     # log server 0.2.170: the whole list of parses, unpaged

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
        if action == "sync":
            return {"logs": 3, "characters": 1}
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
        if method == "GET" and path.startswith("/api/v1/account/logs?"):
            query = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
            rows = [log for log in self.logs if not query.get("boss") or log["boss"] == query["boss"]]
            return {"logs": rows if query["page"] == "1" else rows[:1], "total": 60 if not query.get("boss") else len(rows), "limit": 50}
        if method == "POST" and path.startswith("/api/v1/account/logs/"):
            identifier, what = path.split("/")[-2:]
            log = next(log for log in self.logs if log["id"] == identifier)
            if what == "visibility":
                log["visibility"] = body["visibility"]
            elif what == "title":
                log["title"] = body["title"]
            elif what == "delete":
                self.logs.remove(log)
            return {}
        if method == "GET" and path.startswith("/api/v1/account/top-parses?"):
            if self.old_server:
                return {"parses": json.loads(json.dumps(PARSES)), "truncated": True}
            query = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
            from aion2calc.gui import account as accounts
            return accounts.locally(json.loads(json.dumps(PARSES)), {
                "page": int(query["page"]), "limit": int(query["limit"]), "sort": query["sort"], "order": query["order"],
                "boss": query.get("boss", ""), "difficulty": query.get("difficulty", ""), "cls": query.get("class", ""),
                "character": (query["character"] + "|" + query.get("server", "")) if query.get("character") else ""})
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


def _store(**values):
    """The interface data of a page of its own, as the app gives it (each value a text)."""
    from aion2calc.gui import interface
    store = interface.InterfaceStore(shared=interface._Shared())
    for key, value in values.items():
        store.setValue(key, value)
    return store


def _page(app, **kwargs):
    kwargs.setdefault("store", _store())
    page = AccountPage(app, **kwargs)
    page.resize(1100, 1600)
    page.show()
    settle(lambda: page.state is not None)
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _did(app, action):
    """The last request to the app for this action (another tab's reads may come after it)."""
    return next(p for p in reversed(app.posts) if p.get("action") == action)


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
    assert page.create.isEnabled() and _did(app, "register") == {"action": "register", "name": "taken"}
    page.name_field.setText("  Daeva  ")
    page.create.click()
    settle(lambda: page.state.get("signed_in"))
    assert _did(app, "register") == {"action": "register", "name": "Daeva"} and page.toast.text() == "Signed in as Daeva"
    assert "Daeva" in _texts(page) and "12 logs · 1 character" in _texts(page)
    # signed out from the header's account menu, once asked (no Sign out of its own beside the name)
    assert not any(b.text() == "Sign out" and b.isVisibleTo(page) for b in page.findChildren(QPushButton))
    asked = []
    page.confirm = lambda question: asked.append(question) or True
    page.sign_out("Daeva")
    settle(lambda: page.state is not None and not page.state.get("signed_in"))
    assert asked == ["Sign out of Daeva?"] and _did(app, "signout") == {"action": "signout"}
    # a link code from the website, refused then taken; recovery
    page.code_field.setText("WRONG")
    page.link.click()
    settle(lambda: page.message.text() == "That code is not valid")
    page.code_field.setText("ABCD-EFGH")
    page.link.click()
    settle(lambda: page.state.get("signed_in"))
    assert _did(app, "link") == {"action": "link", "code": "ABCD-EFGH"} and page.toast.text() == "Signed in as Linked"
    app.signed_in = False
    page.render()
    settle(lambda: not page.state.get("signed_in"))
    page.recover.click()
    settle(lambda: page.state.get("signed_in"))
    assert _did(app, "recover") == {"action": "recover"}


def test_discord_sign_in(qapp):
    app = FakeApp()
    page = _page(app)
    page.discord_button.click()
    settle(lambda: page.message.text() == ac.DISCORD_WAIT or page.state.get("signed_in"))
    settle(lambda: page.state.get("signed_in"))                              # pending, then approved
    assert [p["action"] for p in app.posts if p["action"] != "request"] == ["discord-start", "discord-poll", "discord-poll"]
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
    assert _did(elsewhere, "signout") == {"action": "signout"} and page.create.isEnabled()
    serverless = _page(FakeApp(server=""))
    assert ac.CHOOSE_SERVER in _texts(serverless) and not serverless.create.isEnabled()


def test_signed_in_and_security(qapp):
    opened, asked, said = [], [], []
    answers = {ac.RENAME_ASK: "NewName", ac.CODE_ASK: "  ab12cd34 "}
    app = FakeApp(signed_in=True)
    page = _page(app, open_web=opened.append, ask=lambda question, text: (asked.append((question, text)), answers[question])[1],
                 confirm=lambda question: (asked.append(question), True)[1], alert=said.append)
    assert "Daeva" in _texts(page)
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
    settle(lambda: any(p == {"action": "website"} for p in app.posts))
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
    from aion2calc.gui.raid_page import RaidPage
    assert isinstance(window.page("raid"), RaidPage)                     # the last page moved over (0.2.490)


def test_the_logs_and_parses_words():
    f = ac.fresh_filter()
    assert ac.list_query(f) == "page=1&limit=50" and not ac.filtering(f)
    since = ac.list_query({**f, "boss": "Ice Queen", "since": "2026-11-20", "until": "2026-11-21", "page": 2})
    query = dict(urllib.parse.parse_qsl(since))
    from datetime import datetime, timezone
    def instant(text):
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc).astimezone()
    assert query["boss"] == "Ice Queen" and query["page"] == "2"
    assert (instant(query["since"]).strftime("%Y-%m-%d %H:%M"), instant(query["until"]).strftime("%Y-%m-%d %H:%M")) == (
        "2026-11-20 00:00", "2026-11-22 00:00")                                         # the computer's own days
    assert [ac.length(x) for x in (125, 3725, None, "x", -5, 59.6)] == ["2:05", "1:02:05", "0:00", "0:00", "0:00", "1:00"]
    first, second = ac.log_rows({"logs": LOGS})
    assert (first["title"], first["page"], first["held"], first["uploader"], first["duration"], first["uploaded"]) == (
        "Best pull", "combat-log/shared/lg1?segment=2", False, "TestSorc", "2:05", moment(1700000000000))
    assert (second["title"], second["page"], second["held"], second["uploader"], second["name"], second["describe"]) == (
        "Ice Queen", "combat-log/shared/lg2", True, "—", "lg2", "")                    # its boss, then its id, names it
    assert ac.logs_count({"total": 1}) == "1 log" and ac.page_count({"total": 60, "limit": 50}) == 2 and ac.page_count({}) == 1
    assert ac.delete_question(first) == "Delete Best pull from the server for everyone? This cannot be undone."
    assert ac.now_visible(first, "legion") == "Best pull is now Legion only" and ac.vis_label("odd") == "odd"
    assert ac.synced({"logs": 3, "characters": 1}) == "3 logs and 1 characters added"
    # top parses: the tiers, a run's parse, the query, an older server's whole list, the menus and the rows
    assert [ac.parse_tier(p, None) for p in (100, 99, 95, 75, 50, 25, 10)] == ["gold", "pink", "orange", "purple", "blue",
                                                                               "green", "grey"]
    assert ac.parse_tier(40, 1) == "gold" and ac.parse_tier(40, True) == "green"            # rank 1: the bracket's best
    assert ac.parse_cell(PARSES[0]) == ("99", "pink", False, "Parse 99.4, rank 2 of 40 ranked runs of this class on this encounter")
    assert ac.parse_cell(PARSES[1]) == ("·", "none", False, ac.NO_PARSE_TIP)
    assert ac.parse_cell(PARSES[2])[1:3] == ("gold", True) and ac.parse_cell(PARSES[2])[3].endswith("Provisional: fewer than 5 runs.")
    p = ac.fresh_parses()
    assert ac.parses_query(p) == "page=1&limit=25&sort=parse&order=desc"
    picked = {**p, "cls": "sorcerer", "character": ac.pick("TestSorc", 2102)}
    assert ac.parses_query(picked) == "page=1&limit=25&sort=parse&order=desc&class=sorcerer&character=TestSorc&server=2102"
    assert ac.unpick("A|b|2102") == ("A|b", "2102") and ac.unpick("plain") == ("plain", "")
    whole = ac.locally(PARSES, p)
    assert [r["parse"] for r in whole["parses"]] == [100, 99.4, None] and (whole["total"], whole["all"], whole["pages"]) == (3, 3, 1)
    assert whole["facets"]["bosses"] == [{"value": "Black Smoke Murute", "count": 2}, {"value": "Ice Queen", "count": 1}]
    assert whole["facets"]["characters"] == [{"character": "Alt", "server": "2102", "count": 1},
                                             {"character": "TestSorc", "server": "2102", "count": 2}]
    assert [r["dps"] for r in ac.locally(PARSES, ac.sorted_by(p, "dps"))["parses"]] == [52000, 41234.6, 9000]
    assert [r["boss"] for r in ac.locally(PARSES, ac.sorted_by(p, "boss"))["parses"]] == [
        "Black Smoke Murute", "Black Smoke Murute", "Ice Queen"]
    assert [r["log"] for r in ac.locally(PARSES, {**p, "difficulty": "HARD"})["parses"]] == ["lg3", "lg2"]
    assert [r["log"] for r in ac.locally(PARSES, picked)["parses"]] == ["lg3", "lg1"]
    paged = ac.locally(PARSES, {**p, "limit": 2, "page": 9})
    assert (paged["page"], paged["pages"], len(paged["parses"])) == (2, 2, 1)                # a page past the end: the last
    assert ac.sorted_by(p, "parse")["order"] == "asc" and ac.sorted_by(p, "boss")["order"] == "asc"
    assert ac.sort_arrow(p, "parse") == "▼" and ac.sort_arrow(p, "dps") == ""
    assert ac.whole_list({"parses": []}) and not ac.whole_list(whole)
    menus = ac.parse_menus(whole["facets"], p)
    assert [m[:3] for m in menus] == [("boss", "Boss", "All bosses"), ("difficulty", "Difficulty", "All difficulties"),
                                     ("cls", "Class", "All classes"), ("character", "Character", "All characters")]
    assert menus[1][3] == [("hard", "Hard (2)"), ("normal", "Normal (1)")]
    assert menus[3][3][0] == ("Alt|2102", "Alt (Zikel) (1)")
    row = ac.parse_rows(whole)[1]
    assert (row["boss"], row["difficulty"], row["world"], row["class"], row["dps"], row["attempts"], row["page"]) == (
        "Black Smoke Murute", "Normal", "Zikel", "Sorcerer", "41,235", "Best of 3 ranked runs", "combat-log/shared/lg1?segment=2")
    assert ac.parses_status(whole) == "Page 1 of 1 · 3 parses"
    assert ac.missing_parses("Not Found") and ac.missing_parses("The app does not send that request")


def test_my_logs(qapp):
    opened, asked = [], []
    app = FakeApp(signed_in=True)
    page = _page(app, open_web=opened.append, ask=lambda question, text: (asked.append((question, text)), "  New words ")[1],
                 confirm=lambda question: (asked.append(question), True)[1])
    settle(lambda: any(t == "60 logs" for t in _texts(page)))                      # My logs, the tab shown first
    texts = _texts(page)
    assert "Page 1 of 2" in texts and ac.LOGS_NOTE in texts and any("Best pull" in t and "Black Smoke Murute" in t for t in texts)
    assert "under review" in texts and any(t.startswith("<a href='web:combat-log/shared/lg2'") and "Ice Queen" in t for t in texts)
    link = next(label for label in page.findChildren(QLabel) if "web:combat-log/shared/lg1?segment=2" in label.text())
    link.linkActivated.emit("web:combat-log/shared/lg1?segment=2")
    assert opened == ["combat-log/shared/lg1?segment=2"]
    boxes = [box for box in page.findChildren(QComboBox) if box.accessibleName().startswith("Who can see")]
    assert [b.currentData() for b in boxes] == ["public", "private"] and not boxes[1].isEnabled()   # under review: fixed
    boxes[0].setCurrentIndex(boxes[0].findData("legion"))
    boxes[0].activated.emit(boxes[0].currentIndex())
    settle(lambda: "Best pull is now Legion only" in _texts(page))
    assert app.logs[0]["visibility"] == "legion"
    _button(page, "Edit").click()                                                   # once the list is read again
    settle(lambda: "Description saved" in _texts(page))
    assert asked[0] == (ac.DESCRIBE_ASK, "Best pull") and app.logs[0]["title"] == "New words"
    _button(page, "Delete").click()
    settle(lambda: "Log deleted" in _texts(page))
    assert asked[1] == "Delete New words from the server for everyone? This cannot be undone." and len(app.logs) == 1
    # the next page, a boss filter (and Clear), and this app's uploads added
    _button(page, "Next").click()
    settle(lambda: "Page 2 of 2" in _texts(page))
    assert page.mine["page"] == 2 and _button(page, "Previous") is not None
    page.boss_field.setText("Nobody")
    _button(page, "Filter").click()
    settle(lambda: ac.NO_LOGS_MATCH in _texts(page))
    assert page.mine == {"page": 1, "boss": "Nobody", "since": "", "until": ""}
    _button(page, "Clear").click()
    settle(lambda: page.mine == ac.fresh_filter() and any(t == "60 logs" for t in _texts(page)))
    _button(page, ac.SYNC).click()
    settle(lambda: page.toast.text() == "3 logs and 1 characters added")
    assert {"action": "sync"} in app.posts


def test_top_parses(qapp):
    for old_server in (False, True):
        app = FakeApp(signed_in=True, old_server=old_server)
        page = _page(app)
        next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Top parses").click()
        settle(lambda: any(t == "Page 1 of 1 · 3 parses" for t in _texts(page)))
        texts = _texts(page)
        assert ac.PARSES_NOTE in texts and any("TestSorc" in t and "Zikel" in t for t in texts)
        best = next(label for label in page.findChildren(QLabel) if label.text() == "100" and label.isVisibleTo(page))
        assert "color: #e5cc80" in best.styleSheet() and best.graphicsEffect() is not None    # gold, paler: provisional
        heads = [b.text() for b in page.findChildren(QPushButton) if b.objectName() in ("sortHead", "sortHeadOn")]
        assert heads == ["Boss", "Difficulty", "Character", "Class", "DPS", "Parse ▼", "Date", "Log"]
        next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Sort by DPS").click()
        settle(lambda: page.parses["sort"] == "dps" and any(b.text() == "DPS ▼" for b in page.findChildren(QPushButton)))
        menu = next(box for box in page.findChildren(QComboBox) if box.accessibleName() == "Difficulty")
        menu.setCurrentIndex(menu.findData("hard"))
        menu.activated.emit(menu.currentIndex())
        settle(lambda: any(t == "Page 1 of 1 · 2 parses" for t in _texts(page)))
        assert next(b for b in page.findChildren(QPushButton) if b.text() == "Reset").isEnabled()
        _button(page, "Reset").click()
        settle(lambda: any(t == "Page 1 of 1 · 3 parses" for t in _texts(page)))
        size = next(box for box in page.findChildren(QComboBox) if box.accessibleName() == "Per page")
        size.setCurrentIndex(size.findData(50))
        size.activated.emit(size.currentIndex())
        assert page.store.value(ac.PER_PAGE_KEY) == "50"                          # with the web page's choice
        def asked():
            return [p["path"] for p in app.posts if p.get("path", "").startswith("/api/v1/account/top-parses")]
        settle(lambda: old_server or len(asked()) == 5)                          # the page size asked for
        asked = asked()
        if old_server:                                   # its whole list asked for once, then sorted and paged here
            assert len(asked) == 1 and page.parses_all is not None and "The best 3 by DPS are shown." in _texts(page)
        else:
            assert len(asked) == 5 and "sort=dps&order=desc" in asked[1] and "difficulty=hard" in asked[2]
    missing = FakeApp(signed_in=True)
    missing.request = lambda method, path, body: (_ for _ in ()).throw(ValueError("Not Found"))
    page = _page(missing)
    settle(lambda: page.body is not None)
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Top parses").click()
    settle(lambda: ac.NOT_LISTED in _texts(page))


def test_top_parses_open_at_the_page_size_kept(qapp):
    assert [ac.kept_per_page(x) for x in (None, "", "50", "100", " 25 ", "75", "x")] == [25, 25, 50, 100, 25, 25, 25]
    store = _store(**{ac.PER_PAGE_KEY: "100"})                                    # here or on the web page
    page = AccountPage(None, store=store)
    assert page.parses["limit"] == 100
    page.parses_per_page(50)
    assert store.value(ac.PER_PAGE_KEY) == "50" and page.parses["limit"] == 50
    page.parses["page"] = 3
    page.open("parses")                                                          # opened afresh: page 1, the size kept
    assert page.parses["limit"] == 50 and page.parses["page"] == 1 and page.tab == "parses"
    assert AccountPage(None, store=_store()).parses["limit"] == 25


LEGION = "lg_00000000000a"
TOKEN = "a2inv_" + "x" * 24


class LegionApp(FakeApp):
    """The app with legions: one you lead (its members, a request, an invite link and shared logs), one found."""

    def __init__(self, **kwargs):
        super().__init__(signed_in=True, **kwargs)
        self.role = "leader"
        self.mine = [{"id": LEGION, "name": "Dawn", "faction": "Asmodian", "server": 2102, "character": "TestSorc",
                      "role": "leader", "members": 3}]

    def status(self):
        s = super().status()
        if s.get("account"):
            s["account"]["characters"] = [{"id": 1, "name": "TestSorc", "server": 2102, "status": "active"},
                                          {"id": 2, "name": "Gone", "server": 2102, "status": "lapsed"}]
        return s

    def legion(self):
        return {"id": LEGION, "name": "Dawn", "server": 2102, "faction": "Asmodian", "members": 3, "leader": "TestSorc",
                "description": "Weekend raids", "role": self.role, "show_progress": False, "requested": False,
                "roster": [{"member": 1, "character": "TestSorc", "role": "leader", "you": True, "claim": "active", "joined_at": 1700000000},
                           {"member": 2, "character": "Officer1", "role": "officer", "claim": "active", "joined_at": 1700000100},
                           {"member": 3, "character": "Member1", "role": "member", "claim": "lapsed", "joined_at": 1700000200}],
                "requests": [{"id": "rq1", "character": "Asker", "message": "Hi!", "created_at": 1700000300}],
                "invites": [{"id": "iv1", "created_at": 1700000000, "expires_at": 1700600000, "uses": 2, "max_uses": 25}]}

    def request(self, method, path, body):
        if path == "/api/v1/legions/mine":
            return {"legions": json.loads(json.dumps(self.mine))}
        if path == "/api/v1/legions/invite/preview":
            if body["invite"] != TOKEN:
                raise ValueError("That invite has expired")
            return {"legion": {"name": "Dusk", "server": 2102, "members": 7, "leader": "Lead"}}
        if path == "/api/v1/legions/join":
            return {"id": LEGION}
        if method == "GET" and path.startswith("/api/v1/legions?"):
            return {"legions": [{"id": LEGION, "name": "Dawn", "server": 2102, "faction": "Asmodian", "leader": "TestSorc",
                                 "members": 3}] if "q=Dawn" in path else []}
        if path == "/api/v1/legions":
            return {"id": LEGION}
        if path == f"/api/v1/legions/{LEGION}":
            return self.legion()
        if path.startswith(f"/api/v1/legions/{LEGION}/logs?"):
            return {"logs": [{"id": "lg9", "title": "", "boss": "Ice Queen", "member": "Officer1", "created_at": 1700000000,
                              "duration": 90, "visibility": "legion"}], "total": 1, "limit": 50}
        if path.startswith(f"/api/v1/legions/{LEGION}/"):
            what = path[len(f"/api/v1/legions/{LEGION}/"):]
            if what == "invites":
                return {"invite": TOKEN}
            return {}
        return super().request(method, path, body)


def _legions_tab(page):
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Legions").click()


def test_the_legions_words():
    me = {"characters": [{"id": 1, "name": "TestSorc", "server": 2102, "status": "active"}, {"id": 2, "status": "lapsed"}]}
    assert ac.characters(me) == me["characters"][:1] and ac.character_choices(me) == [("1", "TestSorc (Zikel)")]
    assert ac.character_choices(me, 2101) == [("", "No claimed character on " + ac.world(2101))]
    assert ac.character_choices({}) == [("", "No claimed character yet")] and ac.legion_servers(me) == [("2102", "Zikel")]
    row = ac.my_legions({"legions": [{"id": LEGION, "name": "Dawn", "faction": "Asmodian", "server": 2102, "role": "officer",
                                      "members": 3}]})[0]
    assert (row["world"], row["character"], row["role"], row["members"]) == ("Zikel", "—", "Officer", "3")
    assert ac.invite_token(f"https://x.example/account.html#a2invite={TOKEN}") == TOKEN and ac.invite_token("nothing") == ""
    assert ac.invite_link(TOKEN) == ac.SITE + "account.html#a2invite=" + TOKEN
    assert ac.preview_line({"legion": {"name": "Dusk", "server": 2102, "members": 1}}) == "Dusk · Zikel · 1 member"
    assert ac.legion_line({"server": 2102, "faction": "Elyos", "members": 2, "leader": "L"}) == "Zikel · Elyos · 2 members · led by L"
    assert ac.find_query("2102", " Dawn ") == "server=2102&q=Dawn" and ac.find_query("", "") == ""
    leader, officer, member = ac.roster(LegionApp().legion())
    assert (leader["you"], leader["tools"], leader["remove"]) == (True, [], False)
    assert officer["tools"] == [("member", "Make member"), ("leader", "Hand over")] and officer["remove"]
    assert member["tools"] == [("officer", "Make officer"), ("leader", "Hand over")] and member["lapsed"] and member["remove"]
    as_officer = {**LegionApp().legion(), "role": "officer"}
    assert [(m["tools"], m["remove"]) for m in ac.roster(as_officer)] == [([], False), ([], False), ([], True)]   # members only
    assert ac.join_requests(as_officer)[0] == {"id": "rq1", "character": "Asker", "message": "Hi!", "when": moment(1700000300000)}
    assert ac.invites(as_officer)[0]["used"] == "2 of 25 used"
    shared = ac.legion_log_rows({"logs": [{"id": "lg9", "boss": "Ice Queen", "uploader": "U", "duration": 90, "visibility": "legion"}]})
    assert (shared[0]["title"], shared[0]["member"], shared[0]["visibility"]) == ("Ice Queen", "U", "Legion only")
    assert ac.disband_ask("Dawn") == "This ends Dawn for every member. Type its name to disband it."


def test_the_legions(qapp):
    opened = []
    app = LegionApp()
    page = _page(app, open_web=opened.append)
    _legions_tab(page)
    settle(lambda: "Your legions" in _texts(page))
    texts = _texts(page)
    assert ac.LEGIONS_NOTE in texts and "Zikel" in texts and "Leader" in texts and not any(ac.CLAIM_NOTE in t for t in texts)
    # an invite looked at: refused, nothing like one, then the legion with the characters on its server, and joined
    for fold in page.findChildren(Fold):
        fold.button.setChecked(True)
    page.invite_field.setText("no link here")
    _button(page, "Look").click()
    assert ac.NOT_INVITE in _texts(page)
    page.invite_field.setText("a2inv_" + "y" * 24)
    _button(page, "Look").click()
    settle(lambda: "That invite has expired" in _texts(page))
    page.invite_field.setText(f"https://x.example/account.html#a2invite={TOKEN}")
    _button(page, "Look").click()
    settle(lambda: "Dusk · Zikel · 7 members · led by Lead" in _texts(page))
    _button(page, "Join").click()
    settle(lambda: "Welcome to Dusk" in _texts(page) and page.legion == LEGION)
    assert _sent(app, "/api/v1/legions/join")["body"] == {"invite": TOKEN, "character": 1}
    _button(page, "← Legions").click()
    settle(lambda: "Your legions" in _texts(page))
    # found by name, or none; then founded
    for fold in page.findChildren(Fold):
        fold.button.setChecked(True)
    page.find_name.setText("Nobody")
    _button(page, "Search").click()
    settle(lambda: ac.NO_LEGION_FOUND in _texts(page))
    page.find_name.setText("Dawn")
    _button(page, "Search").click()
    settle(lambda: "led by TestSorc" in _texts(page))
    page.new_name.setText("Twilight")
    page.new_faction.setCurrentIndex(page.new_faction.findData("Elyos"))
    _button(page, "Found").click()
    settle(lambda: page.legion == LEGION and any("Twilight is founded" in t for t in _texts(page)))
    assert _sent(app, "/api/v1/legions")["body"] == {"name": "Twilight", "character": 1, "faction": "Elyos", "description": ""}


def test_a_legion_you_lead(qapp):
    opened, asked = [], []
    copied = []
    app = LegionApp()
    page = _page(app, open_web=opened.append, ask=lambda question, text: (asked.append(question), "Dawn")[1],
                 confirm=lambda question: (asked.append(question), True)[1])
    page.copy = copied.append
    _legions_tab(page)
    settle(lambda: "Your legions" in _texts(page))
    link = next(label for label in page.findChildren(QLabel) if f"legion:{LEGION}" in label.text())
    link.linkActivated.emit(f"legion:{LEGION}")
    settle(lambda: "Weekend raids" in _texts(page) and any("Ice Queen" in t for t in _texts(page)))
    texts = _texts(page)
    for words in ("Zikel · Asmodian · 3 members · led by TestSorc", "Members", "Asking to join", "Hi!", "Invite links",
                  "2 of 25 used", "Featured encounters", ac.FEATURED_NOTE, "The legion's logs", "1 log", "Legion only"):
        assert any(words in t for t in texts), words
    assert "you" in texts and "claim lapsed" in texts and "Member1" in texts
    _button(page, "Make member").click()
    settle(lambda: "Roles updated" in _texts(page))
    assert _sent(app, f"/api/v1/legions/{LEGION}/role")["body"] == {"member": 2, "role": "member"}
    _button(page, "Hand over").click()
    settle(lambda: ac.HAND_OVER_ASK in asked and "Roles updated" in _texts(page) and len(app.posts) > 0
           and _sent(app, f"/api/v1/legions/{LEGION}/role")["body"] == {"member": 2, "role": "leader"})
    settle(lambda: any("Ice Queen" in t for t in _texts(page)))                 # drawn again, its logs read
    _button(page, "Remove").click()
    settle(lambda: "Member removed" in _texts(page))
    assert "Remove Officer1 from the legion?" in asked
    _button(page, "Approve").click()
    settle(lambda: "Approved" in _texts(page))
    assert _sent(app, f"/api/v1/legions/{LEGION}/requests/decide")["body"] == {"id": "rq1", "approve": True}
    _button(page, "Revoke").click()
    settle(lambda: "Invite link revoked" in _texts(page))
    settle(lambda: page.legion_answer and any("Ice Queen" in t for t in _texts(page)))
    page.featured.setChecked(True)
    settle(lambda: "Shown on the featured encounters' pages" in _texts(page))
    assert _sent(app, f"/api/v1/legions/{LEGION}/progress")["body"] == {"show": True}
    _button(page, "New invite link").click()
    settle(lambda: ac.INVITE_ONCE in _texts(page))
    assert _sent(app, f"/api/v1/legions/{LEGION}/invites")["body"] == {"days": 7, "uses": 25}
    _button(page, "Copy").click()
    assert copied == [ac.invite_link(TOKEN)]
    log = next(label for label in page.findChildren(QLabel) if "web:combat-log/shared/lg9" in label.text())
    log.linkActivated.emit("web:combat-log/shared/lg9")
    assert opened == ["combat-log/shared/lg9"]
    _button(page, "Disband").click()
    settle(lambda: "Dawn is disbanded" in _texts(page) and page.legion is None)
    assert ac.disband_ask("Dawn") in asked and _sent(app, f"/api/v1/legions/{LEGION}/disband")["body"] == {"confirm": "Dawn"}


def test_a_legion_you_are_not_in(qapp):
    app = LegionApp()
    app.role = None
    page = _page(app)
    page.legion = LEGION
    _legions_tab(page)
    page.legion = LEGION                                  # the tab opened on the legion's page
    page.render()
    settle(lambda: any(b.text() == "Ask to join" for b in page.findChildren(QPushButton)))
    page.ask_message.setText("Let me in")
    _button(page, "Ask to join").click()
    settle(lambda: "Request sent" in _texts(page))
    assert _sent(app, f"/api/v1/legions/{LEGION}/request")["body"] == {"character": 1, "message": "Let me in"}
    unclaimed = LegionApp()
    unclaimed.status = lambda: FakeApp.status(unclaimed)                       # no claimed character
    page = _page(unclaimed)
    _legions_tab(page)
    settle(lambda: any(ac.CLAIM_NOTE in t for t in _texts(page)))
