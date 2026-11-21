"""The log review in the native Combat Logs page, part 1 (0.2.457), as combat-review.js draws a log's own page: a
session recorded on this computer (``#/combat-log/local/<file>``) or a log shared on the log server
(``#/combat-log/shared/<id>``). It is shown in place of Combat Logs' views, with **← Back to combat logs**.

Drawn here so far:
- the encounter chosen, by combat mode, run and encounter, and a player or a PvP opponent;
- the PvP and arena match notes, an opponent's records, the heals left out or rebuilt, and the sources;
- the capture's quality, with how a cut fight was joined, and the run timing and boss progression;
- the summary of every player's damage done and taken, healing and deaths, by the metric chosen, with each player's
  parse from the log server's rankings.

The rest of the review (its graph, timeline, events, abilities, actions, death recaps, insights, rankings, reports,
comparisons and movement replay) opens in the web interface for now, from a button on the page.
"""
from __future__ import annotations

import html

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import combat_review as cw
from . import combat_records as cr
from . import combat_views as cv
from . import theme
from .account import TIER_COLOURS
from .account_page import _parse_pill
from .api import AppApi, Requests
from .combat_community import _note
from .combat_saved import TIMEOUT, Section, _button, _clear, _head, _label
from .database_page import Window
from .result_windows import GridTable
from .results import _dict, _truthy, js_text

C = theme.COLORS


def _plain(layout=QVBoxLayout, spacing: int = 0):
    box = QWidget()
    box.setObjectName("plain")
    line = layout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    return box, line


def _muted(words: str) -> QLabel:
    return _label(words, "small")


def _noted(widget: QWidget) -> QFrame:
    """A part in a note's frame (``.note``), as a ``details`` of the web page's is."""
    frame = QFrame()
    frame.setObjectName("note")
    line = QVBoxLayout(frame)
    line.setContentsMargins(0, 0, 0, 0)
    line.addWidget(widget)
    return frame


class ReviewPage(QWidget):
    """A log's own page (``pageCombatLog``, ``A2CombatReview.mount``). ``open_web`` opens a page of the app (another log
    opens here again); ``open_in_web`` opens a page in the web interface itself (the full review)."""

    def __init__(self, api: AppApi | None, open_web=None, open_in_web=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.open_web = open_web or (lambda page: None)
        self.open_in_web = open_in_web or self.open_web
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.asked: dict[str, int] = {}
        self.colours: dict = {}
        self.doc: dict | None = None
        self.where: dict = {}
        self.state = cw.fresh_state()
        self.ranks = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(14)

    def stop(self) -> None:
        if self.requests is not None:
            self.requests.stop()

    # ---------------------------------------------------------------- questions and answers
    def _ask(self, kind: str, path: str, proxied: bool = False, body: dict | None = None) -> None:
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if self.requests is None:
            return
        name = f"{kind}:{self.asked[kind]}"
        if body is not None:
            self.requests.post(name, "/api/community", {"path": path, "body": body})
        else:
            self.requests.get(name, cv.community_path(path) if proxied else path)

    def _current(self, name: str) -> str | None:
        kind, _, number = name.partition(":")
        return kind if number == str(self.asked.get(kind)) else None

    def show_log(self, kind: str, value: str, mode=None, segment=None) -> None:
        """A log's page opened (``pageCombatLog``): its log read, then drawn at the mode and encounter asked for."""
        self.where = {"kind": kind, "value": value}
        self.doc, self.ranks = None, None
        self.state = cw.fresh_state(mode, segment)
        for kind_of in ("log", "ranks"):
            self.asked[kind_of] = self.asked.get(kind_of, 0) + 1     # answers about the log shown before are let go
        _clear(self.box)
        self.box.addWidget(_label(cw.LOADING, "muted"))
        self._ask("ui", "/api/ui")
        path, proxied = cw.log_path(kind, value)
        self._ask("log", path, proxied)

    def reload(self) -> None:
        """The log read again, the choices kept."""
        if self.where:
            path, proxied = cw.log_path(self.where["kind"], self.where["value"])
            self._ask("ui", "/api/ui")
            self._ask("log", path, proxied)

    def _replied(self, name: str, answer) -> None:
        kind = self._current(name)
        if kind == "ui":
            self.colours = _dict(_dict(answer).get("combat_colors"))
        elif kind == "log":
            if isinstance(answer, dict) and _truthy(answer.get("error")):
                self._refused(js_text(answer["error"]))
                return
            first = self.doc is None
            self.doc = _dict(answer)
            segments = cw.segments(self.doc)
            asked = self.state["segment"]
            if first and not (0 <= asked < len(segments)):          # an encounter the log hasn't: its first
                self.state["segment"] = 0
            self.draw()
            if first:
                self.ask_ranks()
        elif kind == "ranks":
            self.ranks = answer if isinstance(answer, dict) else {}
            self.draw()

    def _failed(self, name: str, why: str) -> None:
        kind = self._current(name)
        if kind == "log":
            self._refused(why)
        elif kind == "ranks":
            self.ranks = {"error": why}
            self.draw()

    def _refused(self, why: str) -> None:
        _clear(self.box)
        self.box.addWidget(_note(why or "Could not read the combat log."))

    def rankings(self) -> bool:
        """Whether the log server ranks this log (``options.rankings``): never a combined review of several parts."""
        return self.doc is not None and not cw.reconstructed(self.doc)

    def ask_ranks(self) -> None:
        """The encounter's parses asked for (``requestRanks``); until they come every parse reads "·"."""
        if not self.rankings() or self.state["segment"] < 0:
            return
        self.ranks = None
        path, body = cw.rankings_question(self.where["kind"], self.where["value"], self.state["segment"], self.doc)
        self._ask("ranks", path, proxied=body is None, body=body)

    # ---------------------------------------------------------------- choices
    def _changed(self, key: str, value) -> None:
        """A choice made (``data-control``): the mode and the run pick their first encounter; another encounter forgets
        the player and the parses."""
        state = self.state
        state[key] = value
        if key == "mode":
            state["run"] = ""
            state["segment"] = max(0, next((i for i, s in enumerate(cw.segments(self.doc)) if cw.matches_mode(self.doc, s, value)), 0))
        if key == "run":
            state["segment"] = cw.first_of_run(self.doc, state)
        if key in ("mode", "run", "segment"):
            state["enemy"] = state["actor"] = ""
            self.ranks = None
            self.draw()
            self.ask_ranks()
        else:
            self.draw()

    def metric(self, key: str) -> None:
        self.state["metric"] = key
        self.draw()

    def open_segment(self, index: int) -> None:
        """Another encounter of the log (``data-attempt-segment``)."""
        self.state.update(segment=index, enemy="", actor="")
        self.ranks = None
        self.draw()
        self.ask_ranks()

    def _open_other(self, log) -> None:
        """Another log the server links this fight to (``data-open-shared``)."""
        if _truthy(log):
            self.open_web(cv.shared_page(log, self.state["mode"]))

    def full_review(self) -> None:
        """The whole review, in the web interface (its graph, timeline, events and the rest)."""
        if not self.where:
            return
        if self.where["kind"] == "local":
            page = cw.local_page(self.where["value"], self.state["mode"], self.state["segment"])
        else:
            page = cv.shared_page(self.where["value"], self.state["mode"], self.state["segment"])
        self.open_in_web(page)

    # ---------------------------------------------------------------- drawing
    def draw(self) -> None:
        doc = self.doc
        if doc is None:
            return
        _clear(self.box)
        state = self.state
        cw.settle_segment(doc, state)
        if state["segment"] < 0:                                     # nothing in this mode (``No encounters recorded``)
            frame = Window(cw.title(doc))
            frame.body.addWidget(_note(cw.NO_MODE_ENCOUNTERS))
            frame.body.addWidget(_button(cw.SHOW_ALL, lambda: self._changed("mode", ""), "small"))
            self.box.addWidget(frame)
            return
        d = cw.data(doc, state)
        foes = cw.opponents_of(doc, d)
        foe = state["actor"] if any(e.get("id") == state["actor"] for e in foes) else ""
        v = cw.data(doc, state, foe) if foe else d
        frame = Window(cw.title(doc), f"{theme.fixed(cw.duration(d), 1)}s")
        body = frame.body
        body.addWidget(self._controls(d, foes))
        if cw.is_pvp(doc, d):
            arena = cw.arena(d)
            body.addWidget(self._arena(arena) if arena is not None else _note(cw.PVP_NOTE))
        if foe:
            body.addWidget(self._opponent(cw.opponent(v)))
        else:
            if foes:
                body.addWidget(_muted(cw.CHOOSE_OPPONENT))
            line = cw.unattributed_line(v["unattributed"])
            if line:
                body.addWidget(_muted(line))
        rebuilt = cw.rebuilt_line(d["segment"].get("heals_over_time"))
        if rebuilt:
            body.addWidget(_muted(rebuilt))
        source = cw.source_line(doc, d)
        if source:
            body.addWidget(_muted(source))
        body.addWidget(self._quality(d))
        cut = cw.pieces(doc, state)
        if cut:
            words = _muted("The meter cut this boss fight in two; this encounter is the whole fight, joined from its pieces, "
                           "which are still listed on their own (unranked).")
            body.addWidget(words)
            row, line = _plain(QHBoxLayout, 6)
            for index in cut:
                line.addWidget(_button("Open a piece", lambda index=index: self.open_segment(index)))
            line.addStretch(1)
            body.addWidget(row)
        if state["mode"]:
            body.addWidget(_muted(f"Showing only encounters recorded as {state['mode'].upper()}. Whole-run timing is hidden in "
                                  "this filtered view."))
        else:
            body.addWidget(self._runs(d))
        body.addWidget(self._tabs())
        elsewhere = QFrame()
        elsewhere.setObjectName("note")
        line = QVBoxLayout(elsewhere)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        line.addWidget(_label(cw.ELSEWHERE))
        row, row_line = _plain(QHBoxLayout)
        row_line.addWidget(_button(cw.OPEN_WEB, self.full_review))
        row_line.addStretch(1)
        line.addWidget(row)
        body.addWidget(elsewhere)
        parse_column = self.rankings() and not foe
        body.addWidget(_muted(cw.summary_note(d, v, foe, parse_column)))
        body.addWidget(self._summary(d, v, parse_column))
        if self.rankings():
            row, line = _plain(QHBoxLayout)
            line.addWidget(_button(cw.REFRESH, self.ask_ranks))
            line.addStretch(1)
            body.addWidget(row)
        self.box.addWidget(frame)

    def _pick(self, words: str, values, chosen, changed, groups=None) -> QWidget:
        """A choice with its name (``label`` around a ``select``); ``groups`` add an ``optgroup`` of their own."""
        box, line = _plain(QHBoxLayout, 6)
        line.addWidget(_label(words, wrap=False))
        pick = QComboBox()
        pick.setAccessibleName(words)
        for value, name in values:
            pick.addItem(name, value)
        for group, items in (groups or []):
            pick.addItem(group, None)
            pick.model().item(pick.count() - 1).setEnabled(False)       # the group's name
            for value, name in items:
                pick.addItem(f"  {name}", value)
        pick.setCurrentIndex(max(0, pick.findData(chosen)))
        pick.activated.connect(lambda _i: changed(pick.currentData()))
        line.addWidget(pick)
        return box

    def _controls(self, d: dict, foes: list[dict]) -> QWidget:
        """The mode, run, encounter and player (``data-control``)."""
        doc, state = self.doc, self.state
        box, line = _plain(QHBoxLayout, 14)
        line.addWidget(self._pick("Combat mode", cw.MODES, state["mode"], lambda value: self._changed("mode", value)))
        runs = cw.runs(doc, state)
        if any(run != "legacy" for run in runs):
            line.addWidget(self._pick("Run", [("", "All runs")] + [(run, f"Run {run}") for run in runs], state["run"],
                                      lambda value: self._changed("run", value)))
            run = _label(cw.run_line(d), "small", wrap=False)
            line.addWidget(run)
        line.addWidget(self._pick("Encounter", cw.segment_choices(doc, state), state["segment"],
                                  lambda value: self._changed("segment", int(value))))
        players = [(js_text(p.get("id")), cw.actor_label(p)) for p in d["rows"]]
        groups = [("Opponents", [(js_text(e.get("id")), cw.actor_label(e)) for e in foes])] if foes else None
        line.addWidget(self._pick("Player", [("", "All players")] + players, state["actor"],
                                  lambda value: self._changed("actor", value or ""), groups))
        line.addStretch(1)
        return box

    def _tabs(self) -> QWidget:
        """The metric shown (``data-metric``): the summary sorts by it."""
        box, line = _plain(QHBoxLayout, 6)
        for key, words in cw.METRICS:
            tab = _button(words, lambda key=key: self.metric(key), "primary" if self.state["metric"] == key else "small")
            line.addWidget(tab)
        line.addStretch(1)
        return box

    def _name(self, actor) -> QLabel:
        """An actor in its class's colour (``actorHTML``)."""
        actor = _dict(actor)
        colour = cr.class_colour(actor.get("class"), self.colours)
        return _label(f"<span style='color: {colour};'>{html.escape(cw.actor_label(actor) if actor else cw.UNKNOWN)}</span>",
                      rich=True)

    def _summary(self, d: dict, v: dict, parse_column: bool) -> QWidget:
        """Every player's totals (``summary``), with their parses."""
        cells = []
        for row in cw.summary_rows(d, v, self.state):
            line = [self._name(row["actor"])]
            if parse_column:
                badge = cw.parse_badge(self.ranks, row["id"], _dict(row["actor"]).get("class"))
                line.append(_parse_pill(badge["text"], TIER_COLOURS[badge["tier"]], badge["provisional"], badge["tip"]))
            deaths = (html.escape(js_text(row["deaths_count"])) + (f" <span style='color: {C['muted']};'>(revived "
                                                                    f"{row['revives']})</span>" if row["revives"] else "")
                      if row["deaths_count"] else "No markers")
            line += [row["class"], row["damage"], row["dps"], row["taken"], row["healing"], row["hps"], _label(deaths, rich=True)]
            cells.append(line)
        table = GridTable(cw.summary_columns(parse_column), cells, {0: 3}, left=True)
        table.setAccessibleName("Summary")
        self.summary = table
        if cells:
            return table
        box, column = _plain()
        column.addWidget(table)
        column.addWidget(_label("No recorded events.", "tcell"))
        return box

    def _quality(self, d: dict) -> QFrame:
        """The capture's quality, folded (``qualityHTML``), with how a cut fight was joined (``stitchedHTML``)."""
        q = cw.quality(self.ranks, d)
        fold = Section(q["summary"], None, False)
        fold.button.setAccessibleName("Capture quality")
        self.quality_fold = fold
        layout = fold.body_layout
        for message in q["messages"]:
            layout.addWidget(_label("• " + message))
        for words in (q["note"], q["driver"], q["processing"]):
            if words:
                layout.addWidget(_label(words))
        for line in cw.stitched(self.ranks, d, self.doc):
            layout.addWidget(_label(line["words"]))
            if line.get("segment") is not None:
                layout.addWidget(_button(line["action"], lambda index=line["segment"]: self.open_segment(index)))
            elif _truthy(line.get("log")):
                layout.addWidget(_button(line["action"], lambda log=line["log"]: self._open_other(log)))
        return _noted(fold)

    def _table(self, columns, rows, stretch=None) -> GridTable:
        """A note's table, its columns sharing the width as the web page's tables do."""
        return GridTable(columns, rows, stretch or {c: 2 if c == 0 else 1 for c in range(len(columns))}, left=True)

    def _runs(self, d: dict) -> QWidget:
        """Run timing and boss progression, folded (``runsHTML``)."""
        runs = cw.run_tables(self.doc, d, self.state, self.ranks)
        if runs["kind"] == "none":
            return _muted(runs["note"])
        fold = Section(runs["title"], None, False)
        fold.button.setAccessibleName(runs["title"])
        self.runs_fold = fold
        layout = fold.body_layout
        if runs["note"]:
            layout.addWidget(_muted(runs["note"]))
        layout.addWidget(self._table(runs["columns"], runs["rows"]))
        progression = runs.get("progression")
        if progression:
            layout.addWidget(_head(progression["title"]))
            layout.addWidget(self._table(progression["columns"], progression["rows"]))
            layout.addWidget(self._table(progression["attempts_columns"], progression["attempts"]))
        return _noted(fold)

    def _arena(self, a: dict) -> QFrame:
        """An arena match from the game's own records (``arenaHTML``)."""
        frame = QFrame()
        frame.setObjectName("note")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(_head(a["title"]))

        def who(x):
            if x["actor"]:
                return self._name(x["actor"])
            colour = cr.class_colour(x["class"], self.colours)
            return _label(f"<span style='color: {colour};'>{html.escape(x['name'])}</span>", rich=True)
        fighters = []
        for f in a["fighters"]:
            name = who(f)
            if f["self"]:
                name.setText(name.text() + f" <span style='color: {C['muted']};'>(recording player)</span>")
            fighters.append([name, f["class"], f["server"], f["faction"], f["rating"], f["won"]])
        layout.addWidget(self._table(["Fighter", "Class", "Server", "Faction", "Rating before", "Rounds won here"], fighters))
        layout.addWidget(self._table(["Round", "Ended at", "Winner", "Loser"],
                                     [[x["round"], x["at"], who(x["winner"]), who(x["loser"])] for x in a["rounds"]]))
        layout.addWidget(_muted(cw.ARENA_NOTE))
        return frame

    def _opponent(self, o: dict) -> QFrame:
        """A PvP opponent chosen under Player (``opponentHTML``)."""
        frame = QFrame()
        frame.setObjectName("note")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        colour = cr.class_colour(o["actor"].get("class"), self.colours)
        heading = (f"Opponent · <span style='color: {colour};'>{html.escape(cw.actor_label(o['actor']))}</span>"
                   + (f" · {html.escape(o['class'][:1].upper() + o['class'][1:])}" if o["class"] else ""))
        layout.addWidget(_label(heading, "combatHead", rich=True))
        layout.addWidget(_muted(cw.OPPONENT_NOTE))
        layout.addWidget(_label(o["recorded"]))
        for title, rows, columns in (("Damage done by target", o["dealt"], ["Target", "Damage", "Share", "Hits", "Largest hit", "DPS"]),
                                     ("Damage taken by source", o["taken"],
                                      ["Source", "Damage", "Share", "Hits", "Largest hit", "Per second"])):
            layout.addWidget(_label(f"<b>{title}</b>", rich=True))
            cells = [[self._name(r["actor"]), r["amount"], r["share"], r["hits"], r["max"], r["rate"]] for r in rows]
            layout.addWidget(self._table(columns, cells))
        return frame
