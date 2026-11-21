"""The native Account page, part 1 (0.2.447): Account as pages/account.js and account-view.js show it.

- **Signed out:** why (a sign-in that ended, one on another server than Settings uses, no log server), what an account
  offers, **Create my account** with an optional name, and under **I already have an account**: **Sign in with
  Discord** (the browser opens; the page waits for it, ten minutes at most), **Link with a code** from the website,
  and **Recover with my uploads**.
- **Signed in:** the account's name, its logs and characters, and its tabs. **Sign-in & security** is drawn here: the
  name with **Rename**; the ways in (**Approve a website sign-in** by the code the website shows, after saying which
  browser asks and whether it started on this computer's connection; **Open the website signed in**) and the Discord,
  passkeys and desktop apps it has; where it is signed in, each with **Sign out**, and **Sign out everywhere else**;
  its recent activity; and **Close the account**.
- **My logs**, **Top parses** and **Legions** open in the web interface for now.

The app keeps the credential and talks to the server (``/api/account``); this page asks the app. **Sign out** stands
on the page, where the web page has it in its header's account menu.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import account as ac
from . import theme
from .api import AppApi, Requests
from .database_page import Window
from .gathering_page import GatheringPage
from .pets_page import Toast
from .result_windows import STYLE as RESULT_STYLE, GridTable
from .timers_page import Fold

TIMEOUT = 40                       # the server's answers may take a while (the app waits 30 s on it)


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


def _note(text: str, *extra: QWidget) -> QFrame:
    note = QFrame()
    note.setObjectName("note")
    line = QHBoxLayout(note)
    line.setContentsMargins(0, 0, 0, 0)
    line.addWidget(_label(text), 1)
    for widget in extra:
        line.addWidget(widget, 0, Qt.AlignVCenter)
    return note


def _clear(layout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class AccountPage(QWidget):
    """Account. ``open_web`` opens a page of the web interface; ``ask(question, text)`` and ``confirm(question)`` stand
    in for the web page's prompt and confirm, ``alert(words)`` for its alert."""

    def __init__(self, api: AppApi | None, open_web=None, ask=None, confirm=None, alert=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.api, self.open_web = api, open_web
        self.ask = ask or self._ask
        self.confirm = confirm or self._confirm
        self.alert = alert or self._alert
        self.tab = "logs"
        self.flash = ""                                  # what the last action did, over the tab once
        self.state: dict | None = None
        self.me: dict = {}
        self.security: dict = {}
        self.busy: QPushButton | None = None            # the signed-out view's button whose request runs
        self.acting = None                               # what the action running says when done
        self.approving = False
        self.interval = 3.0
        self.message: QLabel | None = None
        self.body: QVBoxLayout | None = None
        self.discord = QTimer(self)
        self.discord.setSingleShot(True)
        self.discord.timeout.connect(self._discord_poll)
        self.waited = 0.0
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.setStyleSheet(GatheringPage._stylesheet() + RESULT_STYLE + f"""
            QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
                border: 1px solid rgba(233, 203, 128, 0.65); color: #fff3cf; border-radius: 4px; padding: 5px 12px; font-weight: 600; }}
            QPushButton#primary:disabled, QPushButton#small:disabled {{ color: {theme.COLORS['faint']}; }}
            QLabel#acctName {{ color: {theme.COLORS['gold']}; font-size: 22px; font-weight: 700; }}
            QLabel#acctHead {{ color: {theme.COLORS['gold']}; font-weight: 700; letter-spacing: 0.6px; }}
            QLabel#acctMessage {{ color: {theme.COLORS['muted']}; }}
            QWidget#acctBody QLabel {{ background: transparent; }}
            QWidget#acctBody QLabel#thead {{ color: {theme.COLORS['gold_dim']}; font-weight: 600; padding: 6px 8px;
                border: none; border-bottom: 1px solid {theme.COLORS['line']}; }}
            QWidget#acctBody QLabel#tcell {{ padding: 5px 8px; border: none; border-bottom: 1px solid #1d2539; }}
            QWidget#acctBody QFrame#tcellBox {{ background: transparent; border: none; border-bottom: 1px solid #1d2539; }}
            QWidget#acctBody QLabel#chipGold {{ padding: 1px 6px; border-radius: 3px; background: rgba(233, 203, 128, 0.12);
                color: {theme.COLORS['gold']}; border: 1px solid rgba(206, 182, 122, 0.28); }}
            QFrame#note QToolButton#fold {{ color: #f1d4a3; font-weight: 700; }}
            """ + Toast.STYLE)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        content = QWidget()
        self.scroll.setWidget(content)
        self.box = QVBoxLayout(content)
        self.box.setContentsMargins(24, 20, 24, 20)
        self.box.setSpacing(14)
        self.box.addStretch(1)
        self.toast = Toast(self)

    # ---------------------------------------------------------------- asking the app
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.render()

    def render(self) -> None:
        """The account as it is now (``render``): the app's status first, then the tab's own requests."""
        if self.requests is not None:
            self.requests.get("status", "/api/account")

    def _post(self, name: str, body: dict) -> None:
        if self.requests is not None:
            self.requests.post(name, "/api/account", body)

    def call(self, name: str, method: str, path: str, body: dict | None = None) -> None:
        """A request to the server for the account, through the app (``accountCall``)."""
        self._post(name, {"action": "request", "method": method, "path": path, "body": body})

    def act(self, name: str, method: str, path: str, body: dict | None, done) -> None:
        """An action on the account (``act``): what it did, or why not, is said over the tab drawn again."""
        self.acting = done
        self.call(f"act:{name}", method, path, body)

    def _replied(self, name: str, answer) -> None:
        if name == "status":
            self._draw(ac.status_view(answer))
        elif name.startswith("act:"):
            done = self.acting
            self.flash = (done(answer) if callable(done) else done) or ""
            self.render()
        elif name == "sessions":
            self.security["sessions"] = answer
            self.call("activity", "GET", "/api/v1/account/activity")
        elif name == "activity":
            self.security["activity"] = answer
            self._security()
        elif name in ("register", "link", "recover"):
            self._signed_in(answer)
        elif name == "discord-start":
            self._say(ac.DISCORD_WAIT)
            self.interval = float((answer or {}).get("interval") or 3)          # the app's: two seconds or more
            self.waited = 0.0
            self.discord.start(int(self.interval * 1000))
        elif name == "discord-poll":
            status = (answer or {}).get("status")
            if status == "approved":
                self._signed_in(answer)
            elif status != "pending":
                self._discord_failed(ac.DISCORD_ENDED)
            elif self.waited >= ac.DISCORD_WAIT_S or not self.isVisible():
                self._enable()
            else:
                self.discord.start(int(self.interval * 1000))
        elif name in ("signout", "elsewhere-out"):
            self.render()
        elif name == "lookup":
            self._approve(answer)
        elif name == "approved":
            self.toast.say("Website signed in" if self.approving else "Sign-in denied")

    def _failed(self, name: str, why: str) -> None:
        words = ac.plain(why)
        if name == "status":
            self._draw_problem(words)
        elif name.startswith("act:"):
            self.flash = words
            self.render()
        elif name in ("sessions", "activity"):
            if ac.signed_out_answer(why):
                self.render()
            else:
                self._tab_problem(words)
        elif name in ("register", "link", "recover"):
            self._say(words)
            self._enable()
        elif name in ("discord-start", "discord-poll"):
            self._discord_failed(words)
        elif name in ("signout", "elsewhere-out"):
            self.render()
        elif name in ("lookup", "approved", "website"):
            self.toast.say(words)

    # ---------------------------------------------------------------- drawing
    def _fresh(self) -> QVBoxLayout:
        """The page emptied, its stretch kept at the foot."""
        self.discord.stop()
        _clear(self.box)
        self.box.addStretch(1)
        return self.box

    def _add(self, widget: QWidget) -> QWidget:
        self.box.insertWidget(self.box.count() - 1, widget)
        return widget

    def _draw_problem(self, words: str) -> None:
        self._fresh()
        self._add(_note(words))

    def _draw(self, s: dict) -> None:
        self.state = s
        if not s.get("signed_in"):
            self._signed_out(s)
            return
        self.me = s.get("account") or {}
        self._fresh()
        name, counts = ac.title_line(self.me)
        title = _row(_label(name, "acctName", wrap=False), _label(counts, "muted"))
        title.layout().addWidget(_button("Sign out", self.sign_out))
        self._add(title)
        tabs = QWidget()
        tabs.setObjectName("plain")
        line = QHBoxLayout(tabs)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        for key, words in ac.TABS:
            tab = QPushButton(words.replace("&", "&&"))  # ``.tabs button``, the chosen one gold; "&" is no shortcut
            tab.setObjectName("tabOn" if key == self.tab else "tab")
            tab.setAccessibleName(words)
            tab.clicked.connect(lambda _checked=False, key=key: self.show_tab(key))
            line.addWidget(tab)
        line.addStretch(1)
        self._add(tabs)
        if self.flash:
            self._add(_note(self.flash))
            self.flash = ""
        holder = QWidget()
        holder.setObjectName("acctBody")
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        self._add(holder)
        if self.tab == "security":
            self.body.addWidget(_label("Loading…", "muted"))
            self.security = {}
            self.call("sessions", "GET", "/api/v1/account/sessions")
        else:
            self.body.addWidget(_label(ac.ON_THE_WEB[self.tab], "muted"))
            self.body.addWidget(_row(_button("Open them on the web page",
                                             lambda: self.open_web(f"account/{self.tab}") if self.open_web else None)))

    def _tab_problem(self, words: str) -> None:
        _clear(self.body)
        self.body.addWidget(_note(words))

    def show_tab(self, key: str) -> None:
        self.tab = key
        self.render()

    # ---------------------------------------------------------------- signed out
    def _signed_out(self, s: dict) -> None:
        self._fresh()
        window = Window("Account")
        window.head.addStretch(1)
        for kind, words in ac.signed_out_notes(s):
            extra = [_button("Sign out", lambda: self._post("elsewhere-out", {"action": "signout"}))] if kind == "elsewhere" else []
            window.body.addWidget(_note(words, *extra))
        window.body.addWidget(_label(ac.INTRO))
        window.body.addWidget(_label(ac.NO_PASSWORD, "muted"))
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(24)
        self.name_field.setPlaceholderText(ac.NAME_HINT)
        self.name_field.setAccessibleName("Your name")
        self.name_field.setMinimumWidth(190)
        self.create = _button(ac.CREATE, lambda: self._run(self.create, "register", {"action": "register",
                                                                                     "name": self.name_field.text().strip()}),
                              "primary")
        self.create.setEnabled(ac.can_create(s))
        window.body.addWidget(_row(self.name_field, self.create))
        fold = Fold(ac.HAVE_ONE)
        self.discord_button = None
        if ac.discord_offered(s):
            self.discord_button = _button(ac.DISCORD, self._discord_start)
            fold.add(_row(self.discord_button, _label(ac.DISCORD_NOTE, "muted")))
        self.code_field = QLineEdit()
        self.code_field.setPlaceholderText(ac.CODE_HINT)
        self.code_field.setAccessibleName("Link code")
        self.code_field.setMaximumWidth(140)
        self.link = _button(ac.LINK, lambda: self._run(self.link, "link", {"action": "link", "code": self.code_field.text()}))
        fold.add(_row(self.code_field, self.link, _label(ac.LINK_NOTE, "muted")))
        self.recover = _button(ac.RECOVER, lambda: self._run(self.recover, "recover", {"action": "recover"}))
        fold.add(_row(self.recover, _label(ac.RECOVER_NOTE, "muted")))
        note = QFrame()
        note.setObjectName("note")
        QVBoxLayout(note).addWidget(fold)
        window.body.addWidget(note)
        self.message = _label("", "acctMessage")
        window.body.addWidget(self.message)
        self._add(window)

    def _say(self, words: str) -> None:
        if self.message is not None:
            try:
                self.message.setText(words)
            except RuntimeError:                         # drawn again since
                pass

    def _run(self, button: QPushButton, name: str, body: dict) -> None:
        """A way in (``run``): its button off while it runs; signed in, or why not with the button on again."""
        button.setEnabled(False)
        self.busy = button
        self._post(name, body)

    def _enable(self) -> None:
        if self.busy is not None:
            try:
                self.busy.setEnabled(True)
            except RuntimeError:
                pass
        self.busy = None

    def _signed_in(self, answer) -> None:
        self.busy = None
        self.discord.stop()
        self.toast.say(ac.signed_in_as(answer))
        self.render()

    def _discord_start(self) -> None:
        self.discord_button.setEnabled(False)
        self.busy = self.discord_button
        self._post("discord-start", {"action": "discord-start"})

    def _discord_poll(self) -> None:
        self.waited += self.interval
        self._post("discord-poll", {"action": "discord-poll"})

    def _discord_failed(self, words: str) -> None:
        self.discord.stop()
        self._say(words)
        self._enable()

    # ---------------------------------------------------------------- signed in: Sign-in & security
    def _security(self) -> None:
        _clear(self.body)
        me = self.me
        self.body.addWidget(_row(_label(f"Name: <b>{html.escape(str(me.get('name') or ''))}</b>", rich=True, wrap=False),
                                 _button("Rename", self.rename)))
        self.body.addWidget(_label("Ways in", "acctHead"))
        self.body.addWidget(_row(_button(ac.APPROVE, self.approve, "primary"), _button(ac.WEBSITE, self.website)))
        self.body.addWidget(_label(ac.WAYS_NOTE, "muted"))
        self.body.addWidget(_label(ac.ways_line(me)))
        self.body.addWidget(_label("Signed in", "acctHead"))
        rows = []
        for session in ac.session_rows(self.security.get("sessions")):
            where = _label(f"{html.escape(session['where'])} <span style='color: {theme.COLORS['muted']};'>"
                           f"{html.escape(session['kind'])}</span>", rich=True)
            end = (_row(_label("this one", "chipGold", wrap=False)) if session["current"] else    # a cell's own chip
                   _button("Sign out", lambda identifier=session["id"]: self.end(identifier)))
            rows.append([where, session["since"], session["used"], end])
        self.body.addWidget(GridTable(["Where", "Since", "Last used", ""], rows, {0: 3, 1: 2, 2: 2}, left=True))
        self.body.addWidget(_row(_button("Sign out everywhere else", self.end_all)))
        self.body.addWidget(_label("Recent activity", "acctHead"))
        self.body.addWidget(_label(ac.RECENT_NOTE, "muted"))
        activity = [list(row) for row in ac.activity_rows(self.security.get("activity"))]
        self.body.addWidget(GridTable([], activity, {1: 2, 2: 3}))           # no heads, as on the web page
        fold = Fold(ac.CLOSE)
        fold.add(_label(ac.CLOSE_NOTE))
        self.close_logs = QCheckBox(ac.CLOSE_LOGS)
        fold.add(self.close_logs)
        self.close_words = QLineEdit()
        self.close_words.setPlaceholderText(ac.CLOSE_WORDS)
        self.close_words.setAccessibleName('Type delete my account')
        fold.add(_row(self.close_words, _button(ac.CLOSE, self.close_account)))
        note = QFrame()
        note.setObjectName("note")
        QVBoxLayout(note).addWidget(fold)
        self.body.addWidget(note)

    def rename(self) -> None:
        name = self.ask(ac.RENAME_ASK, str(self.me.get("name") or ""))
        if name and name.strip():
            self.act("name", "POST", "/api/v1/account/name", {"name": name.strip()}, "Renamed")

    def end(self, identifier) -> None:
        self.act("end", "POST", "/api/v1/account/sessions/revoke", {"id": identifier}, "Signed out there")

    def end_all(self) -> None:
        if self.confirm(ac.END_ALL_ASK):
            self.act("end-all", "POST", "/api/v1/account/sessions/revoke", {"all": True}, ac.revoked)

    def close_account(self) -> None:
        typed = self.close_words.text().strip()
        if typed != ac.CLOSE_WORDS:
            self.alert(ac.CLOSE_TYPE)
            return
        self.act("close", "POST", "/api/v1/account/delete", {"confirm": typed, "delete_logs": self.close_logs.isChecked()}, "")

    def approve(self) -> None:
        """A website sign-in approved by the code it shows (``approveWebsiteSignIn``), once it is said which browser
        asks and where it started."""
        code = (self.ask(ac.CODE_ASK, "") or "").strip()
        if code:
            self.call("lookup", "GET", ac.lookup_path(code))

    def _approve(self, seen) -> None:
        self.approving = self.confirm(ac.approve_question(seen))
        self.call("approved", "POST", "/api/v1/account/signin/" + ("approve" if self.approving else "deny"),
                  {"code": (seen or {}).get("code")})

    def website(self) -> None:
        self._post("website", {"action": "website"})

    def sign_out(self) -> None:
        """Sign out (the header menu's, on the web page), once asked."""
        if self.confirm(f"Sign out of {self.me.get('name') or ''}?"):
            self._post("signout", {"action": "signout"})

    # ---------------------------------------------------------------- the dialogs
    def _ask(self, question: str, text: str) -> str | None:
        answer, ok = QInputDialog.getText(self, "Account", question, QLineEdit.Normal, text)
        return answer if ok else None

    def _confirm(self, question: str) -> bool:
        return QMessageBox.question(self, "Account", question) == QMessageBox.Yes

    def _alert(self, words: str) -> None:
        QMessageBox.information(self, "Account", words)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast.place()

    def closeEvent(self, event) -> None:
        self.discord.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)
