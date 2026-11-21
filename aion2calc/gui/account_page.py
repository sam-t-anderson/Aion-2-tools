"""The native Account page (0.2.447; its logs and top parses since 0.2.448, whole since 0.2.449): Account as
pages/account.js and account-view.js show it.

- **Signed out:** why (a sign-in that ended, one on another server than Settings uses, no log server), what an account
  offers, **Create my account** with an optional name, and under **I already have an account**: **Sign in with
  Discord** (the browser opens; the page waits for it, ten minutes at most), **Link with a code** from the website,
  and **Recover with my uploads**.
- **Signed in:** the account's name, its logs and characters, and its tabs. **Sign-in & security** is drawn here: the
  name with **Rename**; the ways in (**Approve a website sign-in** by the code the website shows, after saying which
  browser asks and whether it started on this computer's connection; **Open the website signed in**) and the Discord,
  passkeys and desktop apps it has; where it is signed in, each with **Sign out**, and **Sign out everywhere else**;
  its recent activity; and **Close the account**.
- **My logs** (0.2.448): filtered by boss and upload days, paged; each log with its page, whether it is under review,
  its character, upload time, length, **visibility** to change, and **Edit** (its description) and **Delete**; and
  **Add this app's uploads**.
- **Top parses** (0.2.448): the best run on each boss and difficulty for each character with its parse, filtered by
  boss, difficulty, class and character, sorted by any column and paged; an older log server's whole list is filtered,
  sorted and paged here.
- **Legions** (0.2.449): your legions; one joined by an invite link (looked at first), found by server and name, or
  founded with one of your claimed characters; and a legion's own page: asking to join (or withdrawing), its members
  with their roles (a leader makes officers, hands over and removes; an officer removes members), who asks to join,
  its invite links (made, revoked, shown once), whether it shows on the featured encounters' pages, its shared logs,
  and leaving or disbanding it.

The app keeps the credential and talks to the server (``/api/account``); this page asks the app. **Sign out** stands
on the page, where the web page has it in its header's account menu.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

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


def _bare(layout):
    """A layout without margins of its own (a note's padding is enough)."""
    layout.setContentsMargins(0, 0, 0, 0)
    return layout


def _chip(words: str, gold: bool = False) -> QLabel:
    """A chip (``.chip``, ``.chip.gold``): "you", "claim lapsed", "under review"."""
    return _label(words, "chipGold" if gold else "chip", wrap=False)


def _with_chips(main: QLabel, *chips: QLabel) -> QWidget:
    """A cell's words with its chips after them (a table's cell keeps its own chips' look only as a widget)."""
    cell = QWidget()
    cell.setObjectName("plain")
    line = QHBoxLayout(cell)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(6)
    line.addWidget(main)
    for chip in chips:
        line.addWidget(chip, 0, Qt.AlignTop)
    line.addStretch(1)
    return cell


def _parse_pill(text: str, colour: str, provisional: bool, tip: str) -> QWidget:
    """A parse (``.parse-badge``): its number in its colour on a pill of it, paler when provisional."""
    tint = QColor(colour)
    pill = QLabel(text)
    pill.setAlignment(Qt.AlignCenter)
    pill.setMinimumWidth(38)
    pill.setToolTip(tip)
    pill.setStyleSheet(f"QLabel {{ color: {colour}; font-weight: {600 if provisional else 700}; border-radius: 10px; padding: 1px 7px; "
                       f"border: 1px solid rgba({tint.red()}, {tint.green()}, {tint.blue()}, 0.55); "
                       f"background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 0.14); }}")
    if provisional:
        effect = QGraphicsOpacityEffect(pill)
        effect.setOpacity(0.6)
        pill.setGraphicsEffect(effect)
    holder = QWidget()
    holder.setObjectName("plain")
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.addWidget(pill)
    line.addStretch(1)
    return holder


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
        self.mine = ac.fresh_filter()                    # My logs' page and filters (``st.mine``)
        self.parses = ac.fresh_parses()                  # Top parses' (``st.parses``); its page size kept for the visit
        self.parses_all: dict | None = None             # an older log server's whole list (``st.parsesAll``)
        self.logs_answer: dict = {}
        self.legion: str | None = None                   # the legion opened (``st.legion``)
        self.shared = ac.fresh_filter()                  # its logs' page and filters (``st.shared``)
        self.shared_for: str | None = None
        self.legion_answer: dict = {}
        self.after: dict = {}                            # what each action leads to, once done
        self.parses_answer: dict = {}
        self.busy: QPushButton | None = None            # the signed-out view's button whose request runs
        self.acting: dict = {}                           # what each action running says when done
        self.approving = False
        self.interval = 3.0
        self.message: QLabel | None = None
        self.sync_button: QPushButton | None = None
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
            QWidget#acctBody QLabel#chip {{ padding: 1px 6px; border-radius: 3px; background: rgba(57, 194, 224, 0.12);
                color: #9fe3f2; border: 1px solid rgba(57, 194, 224, 0.25); }}
            QPushButton#sortHead, QPushButton#sortHeadOn {{ background: transparent; border: none; padding: 6px 8px;
                text-align: left; font-weight: 600; color: {theme.COLORS['gold_dim']}; }}
            QPushButton#sortHeadOn {{ color: {theme.COLORS['gold']}; }}
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

    def act(self, name: str, method: str, path: str, body: dict | None, done, after=None) -> None:
        """An action on the account (``act``): what it did, or why not, is said over the tab drawn again; a log changed,
        an older server's whole list of parses is asked for again. ``after`` takes its answer first (the legion joined
        opens, the one left closes)."""
        self.parses_all = None
        self.acting[name], self.after[name] = done, after       # each action's own, should another run meanwhile
        self.call(f"act:{name}", method, path, body)

    def _replied(self, name: str, answer) -> None:
        if name == "status":
            self._draw(ac.status_view(answer))
        elif name.startswith("act:"):
            done, after = self.acting.pop(name[4:], None), self.after.pop(name[4:], None)
            if after is not None:
                after(answer if isinstance(answer, dict) else {})
            self.flash = (done(answer) if callable(done) else done) or ""
            self.render()
        elif name == "logs":
            self.logs_answer = answer if isinstance(answer, dict) else {}
            if self.tab == "logs":                       # still the tab shown
                self._logs()
        elif name == "sync":
            self.toast.say(ac.synced(answer))
            self.render()
        elif name == "parses":
            if ac.whole_list(answer):                     # log server 0.2.170: its whole list, paged here
                self.parses_all = {"parses": (answer or {}).get("parses") or [], "truncated": bool((answer or {}).get("truncated"))}
                answer = ac.locally(self.parses_all["parses"], self.parses)
            if self.tab == "parses":
                self._show_parses(answer)
        elif name == "legions":
            if self.tab == "legions" and self.legion is None:
                self._legions(answer)
        elif name == "preview":
            self._preview(answer)
        elif name == "found":
            self._found(answer)
        elif name == "legion":
            self.legion_answer = answer if isinstance(answer, dict) else {}
            if self.tab == "legions" and self.legion is not None:
                self._legion()
        elif name == "legion-logs":
            if self.tab == "legions" and self.legion is not None:
                self._legion_logs(answer)
        elif name == "invite":
            self._invite_made(answer)
        elif name == "sessions":
            self.security["sessions"] = answer
            self.call("activity", "GET", "/api/v1/account/activity")
        elif name == "activity":
            self.security["activity"] = answer
            if self.tab == "security":
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
        elif name in ("sessions", "activity", "logs"):
            if ac.signed_out_answer(why):
                self.render()
            else:
                self._tab_problem(words)
        elif name in ("legions", "legion"):
            if ac.signed_out_answer(why):
                self.render()
            else:
                self._tab_problem(words)
        elif name in ("preview", "found", "invite", "legion-logs"):
            holder = {"preview": "invite_out", "found": "find_out", "invite": "invite_out_made",
                      "legion-logs": "legion_logs"}[name]
            layout = getattr(self, holder, None)
            if layout is not None:
                _clear(layout)
                layout.addWidget(_note(words))
        elif name == "parses":
            if ac.signed_out_answer(why):
                self.render()
            else:
                self._tab_problem(ac.NOT_LISTED if ac.missing_parses(why) else words, note=False)
        elif name == "sync":
            self.toast.say(why)
            if self.sync_button is not None:
                self.sync_button.setEnabled(True)
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
        elif self.tab == "logs":
            self.body.addWidget(_label("Loading…", "muted"))
            self.call("logs", "GET", "/api/v1/account/logs?" + ac.list_query(self.mine))
        elif self.tab == "parses":
            self.body.addWidget(_label(ac.LOADING_PARSES, "muted"))
            self.fetch_parses()
        else:
            self.body.addWidget(_label("Loading…", "muted"))
            if self.legion is not None:
                self.call("legion", "GET", "/api/v1/legions/" + self.legion)
            else:
                self.call("legions", "GET", "/api/v1/legions/mine")

    def _tab_problem(self, words: str, note: bool = True) -> None:
        _clear(self.body)
        self.body.addWidget(_note(words) if note else _label(words, "muted"))

    def show_tab(self, key: str) -> None:
        self.tab = key
        self.legion = None
        self.render()

    # ---------------------------------------------------------------- my logs
    def _date_field(self, day: str, words: str) -> QDateEdit:
        """A day to filter by (``input type="date"``), empty until one is chosen."""
        field = QDateEdit()
        field.setCalendarPopup(True)
        field.setDisplayFormat("yyyy-MM-dd")
        field.setMinimumDate(QDate(2000, 1, 1))
        field.setSpecialValueText(" ")                   # the earliest day stands for none
        field.setAccessibleName(words)
        field.setDate(QDate.fromString(day, "yyyy-MM-dd") if day else field.minimumDate())
        return field

    @staticmethod
    def _day(field: QDateEdit) -> str:
        return "" if field.date() == field.minimumDate() else field.date().toString("yyyy-MM-dd")

    def _logs(self) -> None:
        """My logs (``renderLogs``)."""
        _clear(self.body)
        f, answer = self.mine, self.logs_answer
        self.boss_field = QLineEdit(f["boss"])
        self.boss_field.setPlaceholderText("Boss")
        self.boss_field.setAccessibleName("Filter your logs by boss")
        self.boss_field.returnPressed.connect(self.filter_logs)
        self.since_field = self._date_field(f["since"], "Uploaded on or after")
        self.until_field = self._date_field(f["until"], "Uploaded on or before")
        tools = [self.boss_field, _label("From", wrap=False), self.since_field, _label("To", wrap=False), self.until_field,
                 _button("Filter", self.filter_logs)]
        if ac.filtering(f):
            tools.append(_button("Clear", self.clear_logs))
        self.sync_button = _button(ac.SYNC, self.sync)
        self.sync_button.setToolTip(ac.SYNC_TIP)
        tools += [self.sync_button, _label(ac.logs_count(answer), "muted", wrap=False)]
        self.body.addWidget(_row(*tools))
        rows = ac.log_rows(answer)
        if rows:
            cells = []
            for row in rows:
                title = (f"<a href='web:{html.escape(row['page'])}' style='color: {theme.COLORS['accent']};'>"
                         f"{html.escape(row['title'])}</a>")
                if row["boss"]:
                    title += f"<br><span style='color: {theme.COLORS['muted']};'>{html.escape(row['boss'])}</span>"
                link = _label(title, rich=True)
                link.linkActivated.connect(self._link)
                if row["held"]:
                    link = _with_chips(link, _chip("under review"))
                visibility = QComboBox()
                for key, words in ac.VISIBILITY:
                    visibility.addItem(words, key)
                index = visibility.findData(row["visibility"])
                visibility.setCurrentIndex(index if index >= 0 else 0)
                visibility.setEnabled(not row["held"])
                visibility.setAccessibleName(f"Who can see {row['name']}")
                visibility.activated.connect(lambda _index, row=row, box=visibility: self.set_visibility(row, box.currentData()))
                cells.append([link, row["uploader"], row["uploaded"], row["duration"], visibility,
                              _button("Edit", lambda row=row: self.describe(row)), _button("Delete", lambda row=row: self.delete(row))])
            self.body.addWidget(GridTable(ac.LOG_COLUMNS, cells, {0: 4, 1: 2, 2: 2}, left=True))
            pages = ac.page_count(answer)
            pager = []
            if f["page"] > 1:
                pager.append(_button("Previous", lambda: self.logs_page(f["page"] - 1)))
            pager.append(_label(f"Page {f['page']} of {pages}", "muted", wrap=False))
            if f["page"] < pages:
                pager.append(_button("Next", lambda: self.logs_page(f["page"] + 1)))
            self.body.addWidget(_row(*pager))
        else:
            self.body.addWidget(_label(ac.NO_LOGS_MATCH if ac.filtering(f) else ac.NO_LOGS, "faint"))
        self.body.addWidget(_label(ac.LOGS_NOTE, "muted"))

    def _link(self, href: str) -> None:
        if href.startswith("web:") and self.open_web is not None:
            self.open_web(href[4:])

    def filter_logs(self) -> None:
        self.mine.update(boss=self.boss_field.text().strip(), since=self._day(self.since_field),
                         until=self._day(self.until_field), page=1)
        self.render()

    def clear_logs(self) -> None:
        self.mine = ac.fresh_filter()
        self.render()

    def logs_page(self, page: int) -> None:
        self.mine["page"] = page
        self.render()

    def set_visibility(self, row: dict, value: str) -> None:
        if value != row["visibility"]:
            self.act("visibility", "POST", f"/api/v1/account/logs/{row['id']}/visibility", {"visibility": value},
                     ac.now_visible(row, value))

    def describe(self, row: dict) -> None:
        title = self.ask(ac.DESCRIBE_ASK, row["describe"])
        if title and title.strip():
            self.act("title", "POST", f"/api/v1/account/logs/{row['id']}/title", {"title": title.strip()}, "Description saved")

    def delete(self, row: dict) -> None:
        if self.confirm(ac.delete_question(row)):
            self.act("delete", "POST", f"/api/v1/account/logs/{row['id']}/delete", {}, "Log deleted")

    def sync(self) -> None:
        """This app's uploads and characters added to the account (``afterLogs``)."""
        self.sync_button.setEnabled(False)
        self._post("sync", {"action": "sync"})

    # ---------------------------------------------------------------- legions
    def _choices(self, choices: list[tuple[str, str]], words: str) -> QComboBox:
        box = QComboBox()
        for value, shown in choices:
            box.addItem(shown, value)
        box.setAccessibleName(words)
        return box

    def _fold_note(self, title: str, opened: bool = False) -> tuple[QFrame, Fold]:
        note = QFrame()
        note.setObjectName("note")
        fold = Fold(title, opened)
        _bare(QVBoxLayout(note)).addWidget(fold)
        return note, fold

    def _claim_note(self) -> None:
        """No claimed character (``noCharacter``): where characters are claimed."""
        if not ac.characters(self.me):
            link = _button(ac.CLAIM_LINK, lambda: self.open_web(ac.CLAIM_PAGE) if self.open_web else None)
            self.body.addWidget(_note(ac.CLAIM_NOTE, link))

    def _legions(self, answer) -> None:
        """Your legions, and joining, finding or founding one (``renderLegions``)."""
        _clear(self.body)
        self._claim_note()
        self.body.addWidget(_label("Your legions", "acctHead"))
        rows = ac.my_legions(answer)
        if rows:
            cells = []
            for row in rows:
                name = (f"<a href='legion:{html.escape(row['id'])}' style='color: {theme.COLORS['accent']};'>"
                        f"{html.escape(row['name'])}</a>")
                if row["faction"]:
                    name += f" <span style='color: {theme.COLORS['muted']};'>{html.escape(row['faction'])}</span>"
                link = _label(name, rich=True)
                link.linkActivated.connect(self._open_legion)
                cells.append([link, row["world"], row["character"], row["role"], row["members"]])
            self.body.addWidget(GridTable(["Legion", "Server", "As", "Your role", "Members"], cells, {0: 3, 1: 2, 2: 2}))
        else:
            self.body.addWidget(_label(ac.NO_LEGION, "faint"))
        note, fold = self._fold_note(ac.JOIN_HEAD)
        self.invite_field = QLineEdit()
        self.invite_field.setPlaceholderText(ac.INVITE_HINT)
        self.invite_field.setAccessibleName("Invite link")
        self.invite_field.setMinimumWidth(360)
        fold.add(_row(self.invite_field, _button("Look", self.look)))
        holder = QWidget()
        holder.setObjectName("plain")
        self.invite_out = QVBoxLayout(holder)
        self.invite_out.setContentsMargins(0, 0, 0, 0)
        fold.add(holder)
        self.body.addWidget(note)
        note, fold = self._fold_note(ac.FIND_HEAD)
        self.find_server = self._choices([("", "Every server")] + ac.legion_servers(self.me), "Server")
        self.find_name = QLineEdit()
        self.find_name.setPlaceholderText("Legion name")
        self.find_name.setAccessibleName("Legion name")
        fold.add(_row(self.find_server, self.find_name, _button("Search", self.find)))
        holder = QWidget()
        holder.setObjectName("plain")
        self.find_out = QVBoxLayout(holder)
        self.find_out.setContentsMargins(0, 0, 0, 0)
        fold.add(holder)
        self.body.addWidget(note)
        note, fold = self._fold_note(ac.FOUND_HEAD)
        self.new_name = QLineEdit()
        self.new_name.setMaxLength(24)
        self.new_name.setPlaceholderText(ac.FOUND_NAME_HINT)
        self.new_name.setAccessibleName("Legion name")
        self.new_character = self._choices(ac.character_choices(self.me), "Your character")
        self.new_faction = self._choices([("", "Faction")] + [(f, f) for f in ac.FACTIONS], "Faction")
        self.new_description = QLineEdit()
        self.new_description.setMaxLength(200)
        self.new_description.setPlaceholderText(ac.FOUND_DESC_HINT)
        self.new_description.setAccessibleName("Description")
        fold.add(_row(self.new_name, self.new_character, self.new_faction, self.new_description,
                      _button("Found", self.found_legion, "primary")))
        fold.add(_label(ac.FOUND_NOTE, "muted"))
        self.body.addWidget(note)
        self.body.addWidget(_label(ac.LEGIONS_NOTE, "muted"))

    def _open_legion(self, href: str) -> None:
        if href.startswith("legion:"):
            self.legion = href[len("legion:"):]
            self.render()

    def look(self) -> None:
        """An invite link looked at before joining (``preview``)."""
        self.token = ac.invite_token(self.invite_field.text())
        _clear(self.invite_out)
        if not self.token:
            self.invite_out.addWidget(_note(ac.NOT_INVITE))
            return
        self.call("preview", "POST", "/api/v1/legions/invite/preview", {"invite": self.token})

    def _preview(self, answer) -> None:
        if getattr(self, "invite_out", None) is None:
            return
        _clear(self.invite_out)
        legion = (answer or {}).get("legion") or {}
        self.invite_out.addWidget(_label(ac.preview_line(answer)))
        self.join_character = self._choices(ac.character_choices(self.me, legion.get("server")), "Your character")
        self.invite_out.addWidget(_row(self.join_character, _button("Join", lambda: self.join(legion), "primary")))

    def join(self, legion: dict) -> None:
        character = self.join_character.currentData()
        self.act("join", "POST", "/api/v1/legions/join", {"invite": self.token, "character": int(character) if character else 0},
                 f"Welcome to {legion.get('name') or ''}", after=lambda joined: setattr(self, "legion", joined.get("id")))

    def find(self) -> None:
        self.call("found", "GET", "/api/v1/legions?" + ac.find_query(self.find_server.currentData(), self.find_name.text()))

    def _found(self, answer) -> None:
        if getattr(self, "find_out", None) is None:
            return
        _clear(self.find_out)
        rows = ac.found_rows(answer)
        if not rows:
            self.find_out.addWidget(_label(ac.NO_LEGION_FOUND, "faint"))
            return
        cells = []
        for row in rows:
            link = _label(f"<a href='legion:{html.escape(row['id'])}' style='color: {theme.COLORS['accent']};'>"
                          f"{html.escape(row['name'])}</a>", rich=True)
            link.linkActivated.connect(self._open_legion)
            cells.append([link, row["world"], row["faction"], row["leader"], row["members"]])
        self.find_out.addWidget(GridTable([], cells, {0: 3, 3: 2}))

    def found_legion(self) -> None:
        name = self.new_name.text().strip()
        character = self.new_character.currentData()
        body = {"name": name, "character": int(character) if character else 0, "faction": self.new_faction.currentData(),
                "description": self.new_description.text().strip()}
        self.act("found", "POST", "/api/v1/legions", body, f"{name} is founded. Make an invite link for your members.",
                 after=lambda made: setattr(self, "legion", made.get("id")))

    def _legion(self) -> None:
        """A legion's own page (``renderLegion``)."""
        _clear(self.body)
        legion, identifier = self.legion_answer, self.legion
        name = str(legion.get("name") or "")
        self.body.addWidget(_row(_button("← Legions", self.back)))
        self.body.addWidget(_label(name, "acctName"))
        self.body.addWidget(_label(ac.legion_line(legion), "muted"))
        if legion.get("description"):
            self.body.addWidget(_label(str(legion["description"])))
        role = legion.get("role")
        if not role:
            if legion.get("requested"):
                self.body.addWidget(_label(ac.REQUEST_WAITING))
                self.body.addWidget(_row(_button("Withdraw the request", lambda: self.act(
                    "withdraw", "POST", f"/api/v1/legions/{identifier}/request/withdraw", {}, "Request withdrawn"))))
            else:
                self.ask_character = self._choices(ac.character_choices(self.me, legion.get("server")), "Your character")
                self.ask_message = QLineEdit()
                self.ask_message.setMaxLength(200)
                self.ask_message.setPlaceholderText(ac.ASK_HINT)
                self.ask_message.setAccessibleName("Message")
                self.body.addWidget(_row(self.ask_character, self.ask_message, _button("Ask to join", self.ask_to_join, "primary")))
            return
        lead, staff = role == "leader", role in ("leader", "officer")
        self.body.addWidget(_label("Members", "acctHead"))
        cells = []
        for m in ac.roster(legion):
            chips = ([_chip("you", gold=True)] if m["you"] else []) + ([_chip("claim lapsed")] if m["lapsed"] else [])
            who = _with_chips(_label(m["character"]), *chips) if chips else _label(m["character"])
            tools = [_button(words, lambda member=m["member"], to=to: self.set_role(member, to)) for to, words in m["tools"]]
            if m["remove"]:
                tools.append(_button("Remove", lambda m=m: self.remove(m)))
            cells.append([who, m["role"], m["joined"], _row(*tools) if tools else ""])
        self.body.addWidget(GridTable(["Character", "Role", "Joined", ""], cells, {0: 3, 3: 3}, left=True))
        requests = ac.join_requests(legion) if staff else []
        if requests:
            self.body.addWidget(_label("Asking to join", "acctHead"))
            rows = [[r["character"], r["message"], r["when"],
                     _row(_button("Approve", lambda r=r: self.decide(r, True), "primary"), _button("Decline", lambda r=r: self.decide(r, False)))]
                    for r in requests]
            self.body.addWidget(GridTable([], rows, {1: 3}, left=True))
        if staff:
            self.body.addWidget(_label("Invite links", "acctHead"))
            made = ac.invites(legion)
            if made:
                self.body.addWidget(GridTable([], [[v["made"], v["until"], v["used"], _button(
                    "Revoke", lambda v=v: self.act("revoke", "POST", f"/api/v1/legions/{identifier}/invites/revoke", {"id": v["id"]},
                                                   "Invite link revoked"))] for v in made], {0: 2, 1: 2, 2: 2}, left=True))
            self.invite_days = self._choices([(str(d), many_days) for d, many_days in
                                              ((d, ac.many(d, "{0} day", "{0} days")) for d in ac.INVITE_DAYS)], "Lasts")
            self.invite_days.setCurrentIndex(ac.INVITE_DAYS.index(ac.INVITE_DAYS_FIRST))
            self.invite_uses = self._choices([(str(u), ac.many(u, "{0} player", "{0} players")) for u in ac.INVITE_USES], "Admits")
            self.invite_uses.setCurrentIndex(ac.INVITE_USES.index(ac.INVITE_USES_FIRST))
            self.body.addWidget(_row(_label("Lasts", wrap=False), self.invite_days, _label("Admits", wrap=False), self.invite_uses,
                                     _button("New invite link", self.new_invite, "primary")))
            holder = QWidget()
            holder.setObjectName("plain")
            self.invite_out_made = QVBoxLayout(holder)
            self.invite_out_made.setContentsMargins(0, 0, 0, 0)
            self.body.addWidget(holder)
        if lead:
            self.body.addWidget(_label("Featured encounters", "acctHead"))
            self.featured = QCheckBox(ac.FEATURED_LABEL)
            self.featured.setChecked(bool(legion.get("show_progress")))
            self.featured.toggled.connect(self.set_featured)
            self.body.addWidget(self.featured)
            self.body.addWidget(_label(ac.FEATURED_NOTE, "muted"))
        elif legion.get("show_progress"):
            self.body.addWidget(_label(ac.FEATURED_SHOWN, "muted"))
        self.body.addWidget(_label("The legion's logs", "acctHead"))
        holder = QWidget()
        holder.setObjectName("plain")
        self.legion_logs = QVBoxLayout(holder)
        self.legion_logs.setContentsMargins(0, 0, 0, 0)
        self.legion_logs.addWidget(_label("Loading…", "muted"))
        self.body.addWidget(holder)
        leave = [_button("Leave the legion", lambda: self.leave(name))]
        if lead:
            leave.append(_button("Disband", lambda: self.disband(name)))
        self.body.addWidget(_row(*leave))
        if self.shared_for != identifier:
            self.shared, self.shared_for = ac.fresh_filter(), identifier
        self.fetch_legion_logs()

    def back(self) -> None:
        self.legion = None
        self.render()

    def ask_to_join(self) -> None:
        character = self.ask_character.currentData()
        self.act("ask", "POST", f"/api/v1/legions/{self.legion}/request",
                 {"character": int(character) if character else 0, "message": self.ask_message.text()}, "Request sent")

    def set_role(self, member, role: str) -> None:
        if role == "leader" and not self.confirm(ac.HAND_OVER_ASK):
            return
        self.act("role", "POST", f"/api/v1/legions/{self.legion}/role", {"member": member, "role": role}, "Roles updated")

    def remove(self, member: dict) -> None:
        if self.confirm(f"Remove {member['name']} from the legion?"):
            self.act("remove", "POST", f"/api/v1/legions/{self.legion}/remove", {"member": member["member"]}, "Member removed")

    def decide(self, request: dict, approve: bool) -> None:
        self.act("decide", "POST", f"/api/v1/legions/{self.legion}/requests/decide", {"id": request["id"], "approve": approve},
                 "Approved" if approve else "Declined")

    def set_featured(self, shown: bool) -> None:
        self.act("progress", "POST", f"/api/v1/legions/{self.legion}/progress", {"show": shown},
                 "Shown on the featured encounters' pages" if shown else "Hidden from the featured encounters' pages")

    def new_invite(self) -> None:
        self.call("invite", "POST", f"/api/v1/legions/{self.legion}/invites",
                  {"days": int(self.invite_days.currentData()), "uses": int(self.invite_uses.currentData())})

    def _invite_made(self, answer) -> None:
        """A new invite link, shown once, with Copy."""
        if getattr(self, "invite_out_made", None) is None:
            return
        _clear(self.invite_out_made)
        link = ac.invite_link(str((answer or {}).get("invite") or ""))
        field = QLineEdit(link)
        field.setReadOnly(True)
        field.setAccessibleName("Invite link")
        field.setMinimumWidth(420)
        self.invite_out_made.addWidget(_note(ac.INVITE_ONCE))
        self.invite_out_made.addWidget(_row(field, _button("Copy", lambda: self.copy(link))))

    def copy(self, words: str) -> None:
        QGuiApplication.clipboard().setText(words)

    def leave(self, name: str) -> None:
        if self.confirm(f"Leave {name}?"):
            self.act("leave", "POST", f"/api/v1/legions/{self.legion}/leave", {}, f"You left {name}",
                     after=lambda _answer: setattr(self, "legion", None))

    def disband(self, name: str) -> None:
        typed = self.ask(ac.disband_ask(name), "")
        if typed:
            self.act("disband", "POST", f"/api/v1/legions/{self.legion}/disband", {"confirm": typed}, f"{name} is disbanded",
                     after=lambda _answer: setattr(self, "legion", None))

    def fetch_legion_logs(self) -> None:
        self.call("legion-logs", "GET", f"/api/v1/legions/{self.legion}/logs?" + ac.list_query(self.shared))

    def _legion_logs(self, answer) -> None:
        """The legion's logs (``legionLogs``): the filters and paging My logs has, drawn on their own."""
        layout = self.legion_logs
        _clear(layout)
        f = self.shared
        self.shared_boss = QLineEdit(f["boss"])
        self.shared_boss.setPlaceholderText("Boss")
        self.shared_boss.setAccessibleName("Filter the legion's logs by boss")
        self.shared_boss.returnPressed.connect(self.filter_shared)
        self.shared_since = self._date_field(f["since"], "Uploaded on or after")
        self.shared_until = self._date_field(f["until"], "Uploaded on or before")
        tools = [self.shared_boss, _label("From", wrap=False), self.shared_since, _label("To", wrap=False), self.shared_until,
                 _button("Filter", self.filter_shared)]
        if ac.filtering(f):
            tools.append(_button("Clear", self.clear_shared))
        tools.append(_label(ac.logs_count(answer), "muted", wrap=False))
        layout.addWidget(_row(*tools))
        rows = ac.legion_log_rows(answer)
        if rows:
            cells = []
            for row in rows:
                title = (f"<a href='web:{html.escape(row['page'])}' style='color: {theme.COLORS['accent']};'>"
                         f"{html.escape(row['title'])}</a>")
                if row["boss"]:
                    title += f"<br><span style='color: {theme.COLORS['muted']};'>{html.escape(row['boss'])}</span>"
                link = _label(title, rich=True)
                link.linkActivated.connect(self._link)
                cells.append([link, row["member"], row["uploaded"], row["duration"], row["visibility"]])
            layout.addWidget(GridTable(["Description", "Member", "Uploaded", "Duration", "Visibility"], cells, {0: 4, 1: 2, 2: 2}))
            pages = ac.page_count(answer)
            pager = []
            if f["page"] > 1:
                pager.append(_button("Previous", lambda: self.shared_page(f["page"] - 1)))
            pager.append(_label(f"Page {f['page']} of {pages}", "muted", wrap=False))
            if f["page"] < pages:
                pager.append(_button("Next", lambda: self.shared_page(f["page"] + 1)))
            layout.addWidget(_row(*pager))
        else:
            layout.addWidget(_label(ac.NO_LOGS_MATCH if ac.filtering(f) else ac.NO_SHARED_LOGS, "faint"))

    def filter_shared(self) -> None:
        self.shared.update(boss=self.shared_boss.text().strip(), since=self._day(self.shared_since),
                           until=self._day(self.shared_until), page=1)
        self.fetch_legion_logs()

    def clear_shared(self) -> None:
        self.shared = ac.fresh_filter()
        self.fetch_legion_logs()

    def shared_page(self, page: int) -> None:
        self.shared["page"] = page
        self.fetch_legion_logs()

    # ---------------------------------------------------------------- top parses
    def fetch_parses(self) -> None:
        """The parses asked for (``fetchParses``), or an older server's whole list paged here."""
        if self.parses_all is not None:
            self._show_parses(ac.locally(self.parses_all["parses"], self.parses))
        else:
            self.call("parses", "GET", "/api/v1/account/top-parses?" + ac.parses_query(self.parses))

    def _show_parses(self, answer: dict) -> None:
        """Top parses (``renderParses``)."""
        _clear(self.body)
        p = self.parses
        answer = answer if isinstance(answer, dict) else {}
        self.parses_answer = answer
        if isinstance(answer.get("page"), int):
            p["page"] = answer["page"]
        everything = answer.get("all") if answer.get("all") is not None else answer.get("total")
        if not everything:
            self.body.addWidget(_label(ac.NO_PARSES))
            self.body.addWidget(_label(ac.PARSES_NOTE, "muted"))
            return
        menus = []
        for key, words, every, items in ac.parse_menus(answer.get("facets"), p):
            menu = QComboBox()
            menu.addItem(every, "")
            for value, shown in items:
                menu.addItem(shown, value)
            index = menu.findData(p[key])
            menu.setCurrentIndex(index if index >= 0 else 0)
            menu.setAccessibleName(words)
            menu.activated.connect(lambda _index, key=key, box=menu: self.filter_parses(key, box.currentData()))
            menus += [_label(words, wrap=False), menu]
        reset = _button("Reset", self.reset_parses)
        reset.setEnabled(bool(p["boss"] or p["difficulty"] or p["cls"] or p["character"]))
        self.body.addWidget(_row(*menus, reset))
        rows = ac.parse_rows(answer)
        if rows:
            heads = []
            for key, words in ac.PARSE_COLUMNS:
                head = QPushButton(f"{words} {ac.sort_arrow(p, key)}".strip())
                head.setObjectName("sortHeadOn" if p["sort"] == key else "sortHead")
                head.setAccessibleName(f"Sort by {words}")
                head.clicked.connect(lambda _checked=False, key=key: self.sort_parses(key))
                heads.append(head)
            log = QPushButton("Log")                     # a head that sorts nothing
            log.setObjectName("sortHead")
            log.setFocusPolicy(Qt.NoFocus)
            cells = [heads + [log]]
            for row in rows:
                text, tier, provisional, tip = row["parse"]
                colour = ac.TIER_COLOURS[tier]
                badge = _parse_pill(text, colour, provisional, tip)
                character = _label(f"{html.escape(row['character'])} <span style='color: {theme.COLORS['muted']};'>"
                                   f"{html.escape(row['world'])}</span>", rich=True)
                dps = _label(row["dps"], wrap=False)
                dps.setToolTip(row["attempts"])
                link = _label(f"<a href='web:{html.escape(row['page'])}' style='color: {theme.COLORS['accent']};'>Open</a>", rich=True)
                link.linkActivated.connect(self._link)
                cells.append([row["boss"], row["difficulty"], character, row["class"], dps, badge, row["date"], link])
            self.body.addWidget(GridTable([], cells, {0: 3, 2: 3}, left=True))
        else:
            self.body.addWidget(_label(ac.NO_PARSES_MATCH))
        previous = _button("Previous", lambda: self.parses_page(-1))
        previous.setEnabled(int(answer.get("page") or 1) > 1)
        following = _button("Next", lambda: self.parses_page(1))
        following.setEnabled(int(answer.get("page") or 1) < int(answer.get("pages") or 1))
        size = QComboBox()
        for n in ac.PER_PAGE:
            size.addItem(str(n), n)
        size.setCurrentIndex(max(0, size.findData(p["limit"])))
        size.setAccessibleName("Per page")
        size.activated.connect(lambda _index, box=size: self.parses_per_page(box.currentData()))
        self.body.addWidget(_row(previous, _label(ac.parses_status(answer), "muted", wrap=False), following,
                                 _label("Per page", wrap=False), size))
        if self.parses_all is not None and self.parses_all["truncated"]:
            self.body.addWidget(_label(f"The best {len(self.parses_all['parses'])} by DPS are shown.", "muted"))
        self.body.addWidget(_label(ac.PARSES_NOTE, "muted"))

    def filter_parses(self, key: str, value: str) -> None:
        self.parses[key] = value or ""
        self.parses["page"] = 1
        self.fetch_parses()

    def reset_parses(self) -> None:
        self.parses.update(boss="", difficulty="", cls="", character="", page=1)
        self.fetch_parses()

    def sort_parses(self, key: str) -> None:
        self.parses = ac.sorted_by(self.parses, key)
        self.fetch_parses()

    def parses_page(self, step: int) -> None:
        self.parses["page"] += step
        self.fetch_parses()

    def parses_per_page(self, limit: int) -> None:
        """Another page size, kept for the visit (the web page keeps it in its browser)."""
        self.parses.update(limit=int(limit), page=1)
        self.fetch_parses()

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
        _bare(QVBoxLayout(note)).addWidget(fold)
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
        _bare(QVBoxLayout(note)).addWidget(fold)
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
