"""The log review in the native Combat Logs page, part 1 (0.2.457), as combat-review.js draws a log's own page: a
session recorded on this computer (``#/combat-log/local/<file>``) or a log shared on the log server
(``#/combat-log/shared/<id>``). It is shown in place of Combat Logs' views, with **← Back to combat logs**.

Drawn here so far:
- the encounter chosen, by combat mode, run and encounter, and a player or a PvP opponent;
- the PvP and arena match notes, an opponent's records, the heals left out or rebuilt, and the sources;
- the capture's quality, with how a cut fight was joined, and the run timing and boss progression;
- the summary of every player's damage done and taken, healing and deaths, by the metric chosen, with each player's
  parse from the log server's rankings.
- Since 0.2.458 the rate chart, in either style, with the rates and the bosses' HP at any moment of it; the recorder's
  ping; the bosses' remaining HP; and the enemy encounters, any of which narrows the review to it.
- Since 0.2.459 the Table, Timeline and Events views: the events' list with a spreadsheet's column filters, a time and
  an amount range and its sort, a hundred at a time; and the recorded effect timeline, its window chosen, moved or
  scrubbed, its lanes shown, hidden or collapsed, and each effect inspected.
- Since 0.2.460 the abilities and skills: each player's abilities as bars and as a table, their skills' casts with
  cooldown usage, and the cast timeline.
- Since 0.2.461 the casts, buffs and break gauge: the rotation, the buffs and debuffs, the crowd control, the break
  gauge, the boss casts and the buff contribution estimate.
- Since 0.2.462 the player death recaps, each opened with its effects and HP samples.
- Since 0.2.463 the encounter insights, shown with **Encounter insights**; and the automatic encounter context and the
  mapping coverage, folded, the coverage's report exported to a file.
- Since 0.2.464 the matched public comparisons (each player's standings and the run's speed), the encounter's metadata
  (corrected and saved for a recording on this computer), a shared log's report to its server's operator, and a
  recording's upload.

The rest of the review (its comparisons with other logs and the movement replay) opens in the web interface for now,
from a button on the page.
"""
from __future__ import annotations

import html
import math
import os

from PySide6.QtCore import QRegularExpression, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QSlider, QVBoxLayout, QWidget)

from . import combat_review as cw
from . import combat_records as cr
from . import combat_views as cv
from . import theme
from .account import TIER_COLOURS
from .account_page import _parse_pill
from .api import AppApi, Requests
from .combat import safe_link
from .combat_community import _note
from .chrome import FlowLayout
from .combat_review_charts import HP, LINE, PingChart, RateChart
from .combat_review_views import ContributionBars, FilterPopup, GaugeChart, Placer, Timeline
from .combat_saved import TIMEOUT, Section, _button, _clear, _head, _label
from .database_page import Window
from .pictures import Pictures
from .result_windows import GridTable
from .results import _dict, _truthy, js_text

C = theme.COLORS
NUMBER = r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?"        # what a number field takes (``type="number"``)


def _plain(layout=QVBoxLayout, spacing: int = 0):
    box = QWidget()
    box.setObjectName("plain")
    line = layout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    return box, line


def _muted(words: str) -> QLabel:
    return _label(words, "small")


def _field_row(words: str, widget: QWidget) -> QWidget:
    """A field with its name before it (``<label>words <input></label>``)."""
    box, line = _plain(QHBoxLayout, 6)
    line.addWidget(_label(words, wrap=False))
    line.addWidget(widget)
    line.addStretch(1)
    return box


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
    opens here again); ``open_in_web`` opens a page in the web interface itself (the full review). ``uploaded`` says this
    recording was uploaded (``a2log-uploaded``)."""

    uploaded = Signal()

    def __init__(self, api: AppApi | None, open_web=None, open_in_web=None, parent: QWidget | None = None,
                 pictures: Pictures | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.open_web = open_web or (lambda page: None)
        self.open_in_web = open_in_web or self.open_web
        self.pictures = pictures
        self.names: dict | None = None                  # the community's NPC names, read once
        self.soon = QTimer(self)                         # pictures that come together, drawn once
        self.soon.setSingleShot(True)
        self.soon.setInterval(120)
        self.soon.timeout.connect(lambda: self.draw() if self.awaiting else None)
        self.awaiting = False                            # a portrait of this review's still being read
        if self.pictures is not None:
            self.pictures.changed.connect(self.soon.start)
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
        self.summary = None
        self.popup: FilterPopup | None = None          # a column's filter of the events, while it is open
        self.filter_buttons: dict = {}
        self._forget_timeline()
        self._forget_forms()
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(14)

    def stop(self) -> None:
        self.soon.stop()
        if self.popup is not None:
            self.popup.hide()
        if self.requests is not None:
            self.requests.stop()

    def _forget_forms(self) -> None:
        """The report, the metadata's save and the upload as a log opens: nothing written, sent or said (``reportReason``…)."""
        self.report = {"reason": "privacy", "details": "", "status": "", "busy": False}
        self.meta_result, self.meta_open, self.meta_busy = "", False, False
        self.publish = {"visibility": "public", "result": "", "busy": False}
        self.mapping_status = self.meta_parts = self.publish_parts = self.standings_box = None

    def _forget_timeline(self) -> None:
        """The timeline's lanes all shown and open again, its window at the start, nothing inspected: as another encounter
        opens (``timelineHidden.clear()``…)."""
        self.lanes_hidden: set = set()
        self.lanes_folded: set = set()
        self.effect = ""
        self.lanes_open = False                       # the lanes' visibility opened (kept while the encounter is)
        self.timeline_scroll: tuple | None = None
        self.timeline_place: tuple | None = None
        self.state["timeline_start"] = 0.0

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
        self._forget_timeline()
        self._forget_forms()
        for kind_of in ("log", "ranks"):
            self.asked[kind_of] = self.asked.get(kind_of, 0) + 1     # answers about the log shown before are let go
        _clear(self.box)
        self.box.addWidget(_label(cw.LOADING, "muted"))
        self._ask("ui", "/api/ui")
        if self.names is None:
            self._ask("names", "/api/v1/npc-portraits", proxied=True)
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
        elif kind == "names":
            self.names = cw.community_names(answer)
            self.draw()
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
        elif kind == "save":                                         # the metadata saved: the log as the app keeps it
            self.doc, self.meta_busy, self.meta_result = _dict(answer), False, cw.METADATA_SAVED
            self.ranks = None
            self.draw()
            self.ask_ranks()
        elif kind == "report":
            receipt = _dict(answer)
            self.report.update(busy=False, details="",
                               status=f"{cw.js_string(receipt.get('message'))} Receipt: {cw.js_string(receipt.get('id'))}")
            self.draw()
        elif kind == "publish":
            shared = _dict(answer)
            link = safe_link(shared.get("url"))
            words = f"<a href='{html.escape(link)}'>Open shared log</a>" if link else ""
            if _truthy(shared.get("ownership_warning")):
                words += f"<p>{html.escape(cw.js_string(shared['ownership_warning']))}</p>"
            self._published(words)
            self.uploaded.emit()

    def _failed(self, name: str, why: str) -> None:
        kind = self._current(name)
        if kind == "log":
            self._refused(why)
        elif kind == "ranks":
            self.ranks = {"error": why}
            self.draw()
        elif kind == "save":                                         # the form left as it is, to be sent again
            self.meta_busy, self.meta_result = False, why
            if self.meta_parts is not None:
                self.meta_parts["result"].setText(why)
                self.meta_parts["save"].setEnabled(True)
        elif kind == "report":
            self.report.update(busy=False, status=why)
            self.draw()
        elif kind == "publish":
            self._published(html.escape(why))

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
        state["page"] = 0
        if key == "mode":
            state["run"] = ""
            state["segment"] = max(0, next((i for i, s in enumerate(cw.segments(self.doc)) if cw.matches_mode(self.doc, s, value)), 0))
        if key == "run":
            state["segment"] = cw.first_of_run(self.doc, state)
        if key in ("mode", "run", "segment"):
            state["enemy"] = state["actor"] = ""
            self.ranks = None
            self._forget_timeline()
            self.draw()
            self.ask_ranks()
        else:
            self.draw()

    def choose_metric(self, key: str) -> None:
        """A metric chosen (``data-metric``). Not ``metric``: ``QWidget.metric()`` is Qt's own, asked for the page's paint
        metrics."""
        self.state["metric"] = key
        self.state["page"] = 0
        self.draw()

    def view(self, key: str) -> None:
        """A view chosen (``data-view``): the Table's summary, the Timeline (turned on when it is chosen), or the Events."""
        self.state["view"] = key
        if key == "timeline":
            self.state["timeline"] = True
        self.draw()

    def open_segment(self, index: int) -> None:
        """Another encounter of the log (``data-attempt-segment``)."""
        self.state.update(segment=index, enemy="", actor="")
        self.ranks = None
        self._forget_timeline()
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
        self.awaiting = False
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
        self.mapping_status = None
        for part in (self._context(d), self._mapping()):
            if part is not None:
                body.addWidget(part)
        if state["mode"]:
            body.addWidget(_muted(f"Showing only encounters recorded as {state['mode'].upper()}. Whole-run timing is hidden in "
                                  "this filtered view."))
        else:
            body.addWidget(self._runs(d))
        body.addWidget(self._tabs())
        body.addWidget(self._options())
        events = cw.visible_events(v, state)
        if state["graph"] and state["metric"] != "deaths":
            body.addWidget(self._graph(v, events))
        body.addWidget(self._ping(d))
        bosses = cw.boss_hp(d, state)
        if bosses:
            body.addWidget(_head("Remaining boss HP · latest recorded sample"))
            body.addWidget(self._table(["Boss", "Remaining HP", "Observed maximum", "Remaining %", "Sample time"], bosses))
            body.addWidget(_muted(cw.HP_NOTE))
        body.addWidget(self._enemies(d))
        self.recaps_box = None
        if state["metric"] == "deaths":
            body.addWidget(self._recaps(v))
        self.insights_fold = None
        if state.get("insights"):
            body.addWidget(self._insights(d))
        self.summary = self.timeline = None
        self.filter_buttons = {}
        if state["view"] == "table":                                 # the view chosen (``data-view``)
            parse_column = self.rankings() and not foe
            body.addWidget(_muted(cw.summary_note(d, v, foe, parse_column)))
            body.addWidget(self._summary(d, v, parse_column))
        elif state["view"] == "events":
            body.addWidget(self._events(d, events))
        if state["timeline"] and state["view"] == "timeline":
            body.addWidget(self._timeline(v, events))
        body.addWidget(self._details(d, v, events))
        body.addWidget(self._actions(v))
        notes = cw.notes_line(d)
        if notes:
            body.addWidget(_muted(notes))
        local, combined = self.where.get("kind") == "local", cw.reconstructed(doc)
        if self.where.get("kind") == "shared" and not combined:      # ``options.report``: a shared log's
            body.addWidget(self._report_form())
        body.addWidget(self._metadata(d))
        self.standings_box = None
        if self.rankings():
            body.addWidget(self._standings())
            row, line = _plain(QHBoxLayout)
            line.addWidget(_button(cw.REFRESH, self.ask_ranks))
            line.addStretch(1)
            body.addWidget(row)
        if local and not combined:                                   # ``options.publish``: a recording on this computer's
            body.addWidget(self._publish_form())
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
        insights = QCheckBox(cw.INSIGHTS)                            # the insights shown (``data-control="insights"``)
        insights.setChecked(bool(state.get("insights")))
        insights.toggled.connect(lambda checked: self._changed("insights", checked))
        line.addWidget(insights)
        line.addStretch(1)
        return box

    def _tabs(self) -> QWidget:
        """The metric shown (``data-metric``), which the summary sorts by; and at the right the view (``data-view``)."""
        box, line = _plain(QHBoxLayout, 6)
        for key, words in cw.METRICS:
            tab = _button(words, lambda key=key: self.choose_metric(key), "primary" if self.state["metric"] == key else "small")
            line.addWidget(tab)
        line.addStretch(1)
        for key, words in cw.VIEWS:
            tab = _button(words, lambda key=key: self.view(key), "primary" if self.state["view"] == key else "small")
            tab.setAccessibleName(f"{words} view")
            line.addWidget(tab)
        return box

    # ---------------------------------------------------------------- the options, graph, ping and enemies (0.2.458)
    def _options(self) -> QWidget:
        """What the review shows (``cr-options``): the graph, pets, and pets counted with their owner."""
        box, line = _plain(QHBoxLayout, 14)
        for key, words in cw.OPTIONS:
            tick = QCheckBox(words)
            tick.setChecked(bool(self.state.get(key, True)))
            tick.toggled.connect(lambda checked, key=key: self._option(key, checked))
            line.addWidget(tick)
        line.addStretch(1)
        return box

    def _option(self, key: str, checked: bool) -> None:
        """An option ticked (``data-control``): pets combined with their owner turn a pet chosen into its owner."""
        if key == "combine" and checked and self.state["actor"]:
            r = cw.refs(self.doc, self.state)
            self.state["actor"] = _dict(r.get(self.state["actor"])).get("owner") or self.state["actor"]
        self.state[key] = checked
        self.state["page"] = 0
        self.draw()

    def _graph(self, v: dict, events: list[dict]) -> QWidget:
        """The rate chart (``graph``) with its style, key, the rates at the moment inspected, and its series."""
        model = cw.graph(v, events, self.state, self.state["hidden"])
        box, column = _plain(spacing=6)
        head, line = _plain(QHBoxLayout, 10)
        line.addWidget(self._pick("Graph style", cw.GRAPH_MODES, model["mode"], self._graph_mode))
        line.addWidget(_label(model["words"], "small", wrap=False))
        line.addStretch(1)
        column.addWidget(head)
        key, line = _plain(QHBoxLayout, 14)
        if model["mode"] == "players":
            line.addWidget(_label("Class-colored lines: player rates · solid: damage done · dashed: damage taken · dotted: "
                                  "healing", "small"))
        else:
            line.addWidget(self._key(f"Bars: total {model['primary'].lower()} per second", "rgba(57, 194, 224, 0.28)", bar=True))
            line.addWidget(self._key("Gold line: trailing 10-second average", LINE.name()))
        if model["health"]:
            line.addWidget(self._key(f"Red line: {model['hp_of']} (right axis)", HP.name()))
        line.addStretch(1)
        column.addWidget(key)
        chart = RateChart(model, v["r"], self.colours)
        self.chart = chart
        chart.clicked.connect(lambda t: self._graph_clicked(model, t))
        column.addWidget(chart)
        detail = QFrame()
        detail.setObjectName("note")
        self.detail = QVBoxLayout(detail)
        self.detail.setContentsMargins(0, 0, 0, 0)
        self.detail.setSpacing(6)
        self.detail.addWidget(_label(cw.GRAPH_HINT, "small"))
        column.addWidget(detail)
        chart.inspected.connect(lambda t: self._inspected(model, v, t))
        buttons, line = _plain(QHBoxLayout, 6)
        for s in model["lines"]:
            colour = cr.class_colour(_dict(v["r"].get(s["actor"])).get("class"), self.colours)
            button = _button(f"{cw.actor_label(v['r'].get(s['actor']))} · {s['kind']}", lambda key=s["key"]: self._hide(key))
            button.setStyleSheet(f"color: {colour};")
            button.setAccessibleName(f"Hide {cw.actor_label(v['r'].get(s['actor']))} · {s['kind']}")
            line.addWidget(button)
        line.addWidget(_button("Show all series", self._show_all))
        line.addStretch(1)
        column.addWidget(buttons)
        return box

    @staticmethod
    def _key(words: str, colour: str, bar: bool = False) -> QWidget:
        """A key of the chart: its swatch and its words."""
        box, line = _plain(QHBoxLayout, 6)
        swatch = QFrame()
        swatch.setFixedSize(18 if bar else 24, 12 if bar else 2)
        swatch.setStyleSheet(f"background: {colour}; border: none;")
        line.addWidget(swatch, 0, Qt.AlignVCenter)
        line.addWidget(_label(words, "small", wrap=False))
        return box

    def _graph_clicked(self, model: dict, t: float) -> None:
        """In Timeline view, a click on the graph moves the timeline's window to that moment (``hit.onclick``)."""
        if self.state["view"] == "timeline":
            cw.centred_window(self.state, t, model["duration"])
            self.draw()

    def _graph_mode(self, mode) -> None:
        self.state["graph_mode"] = mode or "total"
        self.draw()

    def _hide(self, key: str) -> None:
        self.state["hidden"].add(key)
        self.draw()

    def _show_all(self) -> None:
        self.state["hidden"].clear()
        self.draw()

    def _inspected(self, model: dict, v: dict, t: float) -> None:
        """The rates and the bosses' HP at the moment inspected (``inspect``)."""
        detail = cw.graph_detail(model, t, v["r"], v["foe"])
        _clear(self.detail)
        head, words = detail["head"].split(" · ", 1)
        self.detail.addWidget(_label(f"<b>{html.escape(head)}</b> · {html.escape(words)}", rich=True))
        rows = [[self._name(v["r"].get(row["actor"]))] + row["cells"] for row in detail["rows"]]
        self.detail.addWidget(self._table(["Player", "Damage done", "Healing", "Damage taken"], rows))
        if detail["hp"]:
            self.detail.addWidget(self._table(detail["hp_head"], detail["hp"]))

    def _ping(self, d: dict) -> QWidget:
        """The recorder's ping (``latencyHTML``)."""
        ping = cw.latency(d)
        if ping is None:
            return _muted(cw.NO_PING)
        box, column = _plain(spacing=6)
        column.addWidget(_head(ping["title"]))
        column.addWidget(_label(ping["figures"]))
        column.addWidget(_muted(ping["source"]))
        column.addWidget(PingChart(ping))
        return box

    def _enemies(self, d: dict) -> QWidget:
        """The enemy encounters (``encounters``), each filtering the review to it, the unnamed summons folded."""
        found = cw.enemy_encounters(d, self.state, self.names)
        box, column = _plain(spacing=6)
        column.addWidget(_head("Enemy encounters"))
        column.addWidget(self._enemy_table(found["rows"]))
        if found["named_note"]:
            column.addWidget(_muted(cw.UNNAMED_NOTE))
        if found["folded"]:
            fold = Section(found["folded"]["title"], None, False)
            fold.body_layout.addWidget(_muted(found["folded"]["note"]))
            fold.body_layout.addWidget(self._enemy_table(found["folded"]["rows"]))
            column.addWidget(fold)
        row, line = _plain(QHBoxLayout)
        line.addWidget(_button(cw.ALL_ENEMIES, lambda: self._filter("")))
        line.addStretch(1)
        column.addWidget(row)
        return box

    def _enemy_table(self, rows: list[dict]) -> QWidget:
        cells = []
        for row in rows:
            cell, line = _plain(QHBoxLayout, 6)
            if not row["player"] and self.pictures is not None:
                portrait = self.pictures.portrait(row["code"])
                if portrait is None and self.pictures.has_portrait(row["code"]):
                    self.awaiting = True                  # drawn again once it comes, and only then
                if portrait is not None and not portrait.isNull():
                    face = QLabel()
                    face.setFixedSize(22, 22)
                    face.setScaledContents(True)
                    face.setPixmap(portrait)
                    line.addWidget(face)
            name = self._name(row["entity"]) if row["player"] else _label(html.escape(row["name"]), rich=True)
            if row["count"] > 1:
                name.setText(name.text() + f" <span style='color: {C['muted']};'>×{row['count']}</span>")
            name.setWordWrap(False)
            line.addWidget(name)
            chosen = self.state["enemy"] == row["ids"]
            filter_button = _button(row["filter"], lambda ids=row["ids"]: self._filter(ids), "primary" if chosen else "small")
            filter_button.setAccessibleName(f"Filter to {row['name']}")
            line.addWidget(filter_button)
            line.addStretch(1)
            cell.setProperty("fill", True)
            cells.append([cell, row["types"], row["damage"], row["lifespan"]])
        table = self._table(cw.ENEMY_COLUMNS, cells)
        if cells:
            return table
        box, column = _plain()
        column.addWidget(table)
        column.addWidget(_label("No recorded events.", "tcell"))
        return box

    def _filter(self, ids: str) -> None:
        """The review narrowed to some enemies, or to all again (``data-enemy-filter``, ``data-clear-enemy``)."""
        self.state["enemy"] = ids
        self.draw()

    def _name(self, actor) -> QLabel:
        """An actor in its class's colour (``actorHTML``)."""
        actor = _dict(actor)
        colour = cr.class_colour(actor.get("class"), self.colours)
        return _label(f"<span style='color: {colour};'>{html.escape(cw.actor_label(actor) if actor else cw.UNKNOWN)}</span>",
                      rich=True)

    # ---------------------------------------------------------------- the events' list (0.2.459)
    def _actor(self, actor) -> QLabel:
        """An actor in the events' list (``actorHTML``): a player in their class's colour, anyone else plainly."""
        if cw.is_character(actor, self.doc):
            return self._name(actor)
        return _label(cw.actor_label(actor))

    @staticmethod
    def _grid(columns, cells, stretch) -> QWidget:
        """A table (``table``), "No recorded events." under its head when it has no rows."""
        table = GridTable(columns, cells, stretch, left=True)
        if cells:
            return table
        box, column = _plain()
        column.addWidget(table)
        column.addWidget(_label("No recorded events.", "tcell"))
        return box

    def _events(self, d: dict, events: list[dict]) -> QWidget:
        """The events' list (``eventTable``): its filters, the kept events' summary, a page of them and the pager."""
        model = cw.event_list(d, events, self.state)
        self.event_model = model
        ef = model["ef"]
        box, column = _plain(spacing=6)
        bar = QWidget()
        bar.setObjectName("plain")
        flow = FlowLayout(bar, align=Qt.AlignLeft, gap=(12, 8))
        flow.addWidget(_label("Filter:", "small", wrap=False))
        placer = self._placer()
        for c in model["columns"]:
            button = _button(c["caption"] + " ▾", lambda c=c: self._open_filter(c),
                             "primary" if c["chosen"] is not None else "small")
            button.setAccessibleName(c["caption"])
            button.installEventFilter(placer)
            self.filter_buttons[c["key"]] = button
            flow.addWidget(button)
        flow.addWidget(self._range("Time", ("t0", "from", "Time from (seconds)"), ("t1", "to", "Time to (seconds)"), "s"))
        flow.addWidget(self._range("Amount", ("a0", "min", "Smallest amount"), ("a1", "max", "Largest amount"), ""))
        flow.addWidget(self._pick("Sort", cw.SORTS, ef.get("sort", "time"), self._sort))
        if model["clear"]:
            flow.addWidget(_button("Clear filters", self._clear_filters))
        column.addWidget(bar)
        summary = _label(model["summary"], "small", rich=True) if model["count"] else _label(cw.NO_MATCH, "small")
        summary.setAccessibleName("Events kept")
        self.events_summary = summary
        column.addWidget(summary)
        r = d["r"]
        cells = [[row["time"], row["kind"], self._actor(r.get(row["source"])), self._actor(r.get(row["target"])), row["skill"],
                  row["amount"]] for row in model["rows"]]
        table = self._grid(cw.EVENT_COLUMNS, cells, {0: 2, 1: 2, 2: 5, 3: 5, 4: 3, 5: 2})     # as the web table's share
        table.setAccessibleName("Events")
        self.events_table = table
        column.addWidget(table)
        pager, line = _plain(QHBoxLayout, 8)
        line.addWidget(_button("Previous", lambda: self._page(-1)))
        line.addWidget(_label(model["pager"], wrap=False))
        line.addWidget(_button("Next", lambda: self._page(1)))
        line.addStretch(1)
        column.addWidget(pager)
        return box

    def _range(self, words: str, low: tuple, high: tuple, unit: str) -> QWidget:
        """A time or an amount range (``data-ef-range``), each bound read once its field is left or Enter pressed."""
        ef = cw.filters_of(self.state)
        box, line = _plain(QHBoxLayout, 6)
        line.addWidget(_label(words, "small", wrap=False))
        for index, (key, hint, name) in enumerate((low, high)):
            if index:
                line.addWidget(_label("to", "small", wrap=False))
            field = QLineEdit(js_text(ef.get(key) or ""))
            field.setPlaceholderText(hint)
            field.setAccessibleName(name)
            field.setValidator(QRegularExpressionValidator(QRegularExpression(NUMBER), field))
            field.setFixedWidth(84)
            field.editingFinished.connect(lambda key=key, field=field: self._bound(key, field.text()))
            line.addWidget(field)
        if unit:
            line.addWidget(_label(unit, "small", wrap=False))
        return box

    def _placer(self) -> Placer:
        if self.popup is None:
            self.popup = FilterPopup(self)
            self.popup.kept.connect(self._keep)
            self.popup.searched.connect(lambda key, words: self.state["ef_search"].__setitem__(key, words))
            self.popup.closed.connect(lambda: self.state.__setitem__("ef_open", ""))
            self.placer = Placer(self.popup, self)
        return self.placer

    def _open_filter(self, column: dict) -> None:
        """A column's filter opened under its button (``data-ef-col``), or closed when it was open."""
        self._placer()
        popup = self.popup
        if popup.isVisible() and popup.key == column["key"]:
            popup.hide()
            return
        self.state["ef_open"] = column["key"]
        popup.open(column, self.state["ef_search"].get(column["key"], ""),
                   lambda key=column["key"]: self.filter_buttons.get(key))

    def _keep(self, key: str, chosen) -> None:
        """The values a column keeps (``keep``); all of them is no filter. Its filter stays open."""
        ef = cw.filters_of(self.state)
        if chosen is None:
            ef["sel"].pop(key, None)
        else:
            ef["sel"][key] = list(chosen)
        self.state["page"] = 0
        self.draw()

    def _bound(self, key: str, words: str) -> None:
        ef = cw.filters_of(self.state)
        if js_text(ef.get(key) or "") == words:                     # left unchanged (``change`` fires on a change)
            return
        ef[key] = words
        self.state["page"] = 0
        self.draw()

    def _sort(self, value) -> None:
        cw.filters_of(self.state)["sort"] = value or "time"
        self.state["page"] = 0
        self.draw()

    def _clear_filters(self) -> None:
        """Every filter and search let go (``data-ef-clear``)."""
        self.state.update(ef=None, ef_search={}, ef_open="", page=0)
        if self.popup is not None:
            self.popup.hide()
        self.draw()

    def _page(self, step: int) -> None:
        """The page before or after (``data-prev``, ``data-next``); the list keeps the page within its pages."""
        self.state["page"] = max(0, int(self.state.get("page") or 0) + step)
        self.draw()

    # ---------------------------------------------------------------- the abilities and skills (0.2.460)
    def _details(self, d: dict, v: dict, events: list[dict]) -> QWidget:
        """The abilities and skills (``detailsHTML``): the tab chosen's, or nothing (**Hide**)."""
        state = self.state
        box, column = _plain(spacing=8)
        self.details = box
        column.addWidget(_head("Abilities and skills"))
        tabs, line = _plain(QHBoxLayout, 6)
        for key, words in cw.DETAILS:
            tab = _button(words, lambda key=key: self._detail(key), "primary" if state["detail"] == key else "small")
            tab.setAccessibleName(f"{words} tab")
            line.addWidget(tab)
        line.addStretch(1)
        column.addWidget(tabs)
        self.ability_table = self.skills_table = self.casts = None
        detail = state["detail"]
        if detail in ("contribution", "abilities"):
            if state["metric"] == "deaths":
                column.addWidget(_muted(cw.DEATHS_ABILITIES))
                return box
            found = cw.abilities(d, v, events, state)
            if detail == "contribution":
                bars = cw.contribution(found, d["r"], state)
                column.addWidget(_label(bars["note"], "small", rich=True) if bars["bars"] else _muted(bars["note"]))
                if bars["bars"]:
                    r, colours = d["r"], self.colours
                    column.addWidget(ContributionBars(bars["bars"], lambda actor: cr.class_colour(_dict(r.get(actor)).get("class"),
                                                                                                 colours)))
            else:
                rows = cw.ability_table(found, v, state, cw.duration(d))
                table = self._grid(cw.ABILITY_COLUMNS, [[self._name(d["r"].get(row["actor"]))] + row["cells"] for row in rows],
                                   {0: 3, 1: 3, 2: 1, 3: 2, 4: 1, 5: 2, 6: 2, 7: 2, 8: 2})
                table.setAccessibleName("Abilities")
                self.ability_table = table
                column.addWidget(table)
        elif detail == "skills":
            column.addWidget(self._skills(v))
        elif detail == "casts":
            column.addWidget(self._casts(v))
        return box

    def _detail(self, key: str) -> None:
        """A tab of the abilities and skills chosen (``data-detail``)."""
        self.state["detail"] = key
        self.draw()

    def _hide_procs(self) -> QCheckBox:
        tick = QCheckBox(cw.HIDE_PROCS)
        tick.setChecked(bool(self.state.get("hide_procs", True)))
        tick.toggled.connect(lambda checked: self._option("hide_procs", checked))
        return tick

    def _skills(self, v: dict) -> QWidget:
        """The skills' casts (``skillsHTML``): each skill's casts, gaps, cooldown and its usage, cast time and span."""
        missing = cw.casts_missing(self.doc, v, self.state)
        if missing:
            return _label(missing, "small", rich=True)
        box, column = _plain(spacing=6)
        column.addWidget(_muted(cw.SKILLS_NOTE))
        column.addWidget(self._hide_procs())
        cells = [[self._actor(v["r"].get(row["source"])), self._skill_cell(row["skill_id"], row["skill"], row["proc"])]
                 + row["cells"] for row in cw.skill_rows(self.doc, v, self.state)]
        table = self._grid(cw.SKILL_COLUMNS, cells, {0: 3, 1: 4, 2: 1, 3: 2, 4: 2, 5: 3, 6: 2, 7: 3})
        table.setAccessibleName("Skills")
        self.skills_table = table
        column.addWidget(table)
        return box

    def _skill_cell(self, skill_id, name: str, proc: bool) -> QWidget:
        """A skill with its icon when the app bundles it (``skillCell``), a proc marked as one."""
        cell, line = _plain(QHBoxLayout, 6)
        address = cw.skill_icon(skill_id)
        picture = self.pictures.by_address(address) if self.pictures is not None and address else None
        if picture is None and self.pictures is not None and self.pictures.has_address(address):
            self.awaiting = True                                   # drawn again once it comes
        if picture is not None and not picture.isNull():
            icon = QLabel()
            icon.setFixedSize(18, 18)
            icon.setScaledContents(True)
            icon.setPixmap(picture)
            line.addWidget(icon)
        words = _label(html.escape(name) + (f" <span style='color: {C['muted']};'>proc</span>" if proc else ""), rich=True)
        words.setWordWrap(False)
        line.addWidget(words)
        line.addStretch(1)
        cell.setProperty("fill", True)
        return cell

    def _casts(self, v: dict) -> QWidget:
        """Every press over the fight (``castsHTML``)."""
        missing = cw.casts_missing(self.doc, v, self.state)
        if missing:
            return _label(missing, "small", rich=True)
        model = cw.cast_timeline(self.doc, v, self.state, self.colours)
        if model is None:
            return _muted(cw.NO_PLAYER_CASTS)
        box, column = _plain(spacing=6)
        column.addWidget(_label("<b>Cast timeline</b>", rich=True))
        column.addWidget(_muted(cw.CASTS_NOTE))
        column.addWidget(self._hide_procs())
        casts = Timeline(model, self._cast_lane_name, lambda lane: QWidget(), self._skill_picture)
        casts.setAccessibleName("Cast timeline")
        if self.pictures is not None:
            self.pictures.changed.connect(casts.tracks.update)
        self.casts, self.casts_model = casts, model
        column.addWidget(casts)
        return box

    def _cast_lane_name(self, lane: dict) -> QWidget:
        """A cast lane's name in its class's colour, with how many presses had no room (``.cr-lane-name``)."""
        cell = QFrame()
        cell.setObjectName("crLaneName")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        layout.addStretch(1)
        layout.addWidget(self._name(lane["actor"]))
        if lane.get("omitted"):
            layout.addWidget(_muted(f"{lane['omitted']} not drawn (overlap)"))
        layout.addStretch(1)
        return cell

    # ---------------------------------------------------------------- the casts, buffs and break gauge (0.2.461)
    def _actions(self, v: dict) -> QWidget:
        """The casts, buffs and break gauge (``actionsHTML``): the tab chosen's, or nothing (**Hide**); or why the log
        holds none."""
        doc, state = self.doc, self.state
        missing = cw.actions_missing(doc, v, state)
        self.actions_box = None
        if missing:
            return _muted(missing)
        box, column = _plain(spacing=8)
        self.actions_box = box
        column.addWidget(_head("Casts, buffs and break gauge"))
        tabs, line = _plain(QHBoxLayout, 6)
        for key, words in cw.ACTIONS:
            tab = _button(words.replace("&", "&&"), lambda key=key: self._actions_tab(key),   # "&" alone marks a mnemonic
                          "primary" if state["actions"] == key else "small")
            tab.setAccessibleName(f"{words} actions")
            line.addWidget(tab)
        line.addStretch(1)
        column.addWidget(tabs)
        tab = state["actions"]
        if tab == "rotation":
            t = cw.rotation_tab(doc, v, state)
            if t.get("missing"):
                column.addWidget(_label(t["missing"], "small", rich=True))
            else:
                column.addWidget(_muted(cw.ROTATION_NOTE))
                column.addWidget(self._rows(cw.ROTATION_COLUMNS, t["totals"], v))
                if t["mp"]:
                    column.addWidget(_label("<b>MP</b>", rich=True))
                    column.addWidget(_muted(cw.MP_NOTE))
                    column.addWidget(self._rows(cw.MP_COLUMNS, t["mp"], v))
                column.addWidget(_label(cw.SKILLS_ABOVE, "small", rich=True))
                if t["has_chains"]:
                    column.addWidget(_label("<b>Chain skills</b>", rich=True))
                    column.addWidget(_muted(cw.CHAINS_NOTE))
                    column.addWidget(self._rows(cw.CHAIN_COLUMNS, t["chains"], v))
        elif tab in ("effects", "cc"):
            t = cw.effects_tab(doc, v, state) if tab == "effects" else cw.cc_tab(doc, v, state)
            if t.get("missing"):
                column.addWidget(_muted(t["missing"]))
            else:
                column.addWidget(_muted(t["note"]))
                for table in t["tables"]:
                    if table["title"]:
                        column.addWidget(_label(f"<b>{html.escape(table['title'], quote=False)}</b>", rich=True))
                    if table.get("older"):
                        column.addWidget(_muted(cw.OLDER_ANALYSIS))
                        continue
                    if table.get("note"):
                        column.addWidget(_muted(table["note"]))
                    column.addWidget(self._rows(table["columns"], table["rows"], v))
        elif tab == "stagger":
            t = cw.stagger_tab(doc, v, state)
            column.addWidget(_muted(t["note"]))
            if not t["bosses"]:
                column.addWidget(_label(cw.NO_STAGGER))
            for b in t["bosses"]:
                column.addWidget(_label(f"<b>{html.escape(b['title'], quote=False)}</b>" + (cw._muted_html("elite") if b["elite"] else ""),
                                        rich=True))
                column.addWidget(_label(b["line"], "small"))
                if b["gauge"] is not None:
                    column.addWidget(GaugeChart(b["gauge"]))
                column.addWidget(self._rows(cw.STAGGER_COLUMNS, b["rows"], v))
        elif tab == "boss":
            t = cw.boss_tab(doc, v, state, self.names)
            column.addWidget(_label(t["note"], "small", rich=True))
            if t.get("missing"):
                column.addWidget(_label(t["missing"]))
            else:
                column.addWidget(self._rows(cw.BOSS_COLUMNS, t["skills"], v))
                column.addWidget(_label("<b>Casts in order</b>", rich=True))
                column.addWidget(_muted(cw.BOSS_ORDER_NOTE))
                column.addWidget(self._rows(cw.BOSS_ORDER_COLUMNS, t["order"], v))
                for words in t["notes"]:
                    column.addWidget(_muted(words))
        elif tab == "contribution":
            t = cw.contribution_tab(doc, v, state)
            if t.get("missing"):
                column.addWidget(_muted(t["missing"]))
            else:
                column.addWidget(_label(t["note"], "small", rich=True))
                column.addWidget(self._rows(cw.CONTRIBUTION_COLUMNS, t["players"], v))
                if t["unlisted"]:
                    column.addWidget(_muted(t["unlisted"]))
                column.addWidget(_label("<b>Who added what</b>", rich=True))
                column.addWidget(self._rows(cw.GIVEN_COLUMNS, t["given"], v))
                column.addWidget(_label("<b>Credited buffs</b>", rich=True))
                column.addWidget(self._rows(cw.CREDITED_COLUMNS, t["buffs"], v))
                if t["checks"]:
                    column.addWidget(_label("<b>Check against this fight's hits</b>", rich=True))
                    column.addWidget(_label(cw.CHECKS_NOTE, "small", rich=True))
                    column.addWidget(self._rows(cw.CHECK_COLUMNS, t["checks"], v))
        omitted = cw.omitted_actions(doc, state)
        if tab and omitted:
            column.addWidget(_muted(omitted))
        return box

    # ---------------------------------------------------------------- comparisons, metadata, report and upload (0.2.464)
    def _post_app(self, kind: str, path: str, body: dict) -> None:
        """A request to the app itself (``api(path, body)``): the metadata saved, the recording uploaded."""
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if self.requests is not None:
            self.requests.post(f"{kind}:{self.asked[kind]}", path, body)

    def _standings(self) -> QWidget:
        """The matched public comparisons (``ranksHTML``): each player's standings now and at upload, and the run's speed;
        or that they are loading, or why they could not be read."""
        model = cw.standings(self.ranks)
        if "loading" in model:
            return _muted(model["loading"])
        box, column = _plain(spacing=8)
        self.standings_box = box
        column.addWidget(_head(cw.STANDINGS_HEAD))
        column.addWidget(_muted(model["note"]))
        for words in (model["unranked"], html.escape(model["none"], quote=False)):
            if words:
                column.addWidget(_noted(_label(words, rich=True)))
        column.addWidget(self._grid(cw.STANDINGS_COLUMNS, [[row[0], self._scopes(row[1]), self._scopes(row[2])]
                                                          for row in model["rows"]], {0: 1, 1: 1, 2: 1}))
        column.addWidget(_label(f"<b>{html.escape(cw.RUN_HEAD, quote=False)}</b>", rich=True))
        column.addWidget(self._grid(cw.RUN_COLUMNS, [[self._scopes(cell) for cell in model["run"]]], {0: 1, 1: 1}))
        return box

    @staticmethod
    def _scopes(cell: dict) -> QWidget:
        """A cell of standings: Server, Region and World, each its own line, its reasons its tip (``title``)."""
        box, column = _plain(spacing=4)
        box.setProperty("fill", True)                                # across its column, as the web page's cell is
        for name, standing in cell["standings"]:
            line = _label(f"{name}: {standing['html']}", rich=True)
            if standing["tip"]:
                line.setToolTip(standing["tip"])
            column.addWidget(line)
        return box

    def _metadata(self, d: dict) -> QWidget:
        """The encounter's metadata (``metadataHTML``): its line; for a completed recording on this computer, its fields
        to correct and save, folded."""
        model = cw.metadata(self.doc, d, self.where.get("kind", ""))
        self.meta_parts = None
        if "line" in model:
            return _muted(model["line"])
        fold = Section(cw.METADATA_HEAD, None, self.meta_open or bool(self.meta_result) or self.meta_busy)
        fold.button.setAccessibleName(cw.METADATA_HEAD)
        fold.button.toggled.connect(lambda opened: setattr(self, "meta_open", opened))
        fold.body_layout.addWidget(_muted(cw.METADATA_NOTE))
        row = QWidget()
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        scope = QComboBox()
        scope.setAccessibleName("Apply changed fields to")
        scope.addItem("This encounter", "encounter")
        if model["run"]:
            scope.addItem("All encounters in this run", "run")
        kind = QComboBox()
        kind.setAccessibleName("Encounter type")
        for value, words in model["types"]:
            kind.addItem(words, value)
        kind.setCurrentIndex(max(0, kind.findData(model["type"])))
        fields: dict = {"encounter_type": kind}
        flow.addWidget(_field_row("Apply changed fields to", scope))
        flow.addWidget(_field_row("Encounter type", kind))
        for key, words, value in model["fields"]:
            edit = QLineEdit(value)
            edit.setMaxLength(200)
            edit.setAccessibleName(words)
            fields[key] = edit
            flow.addWidget(_field_row(words, edit))
        save = _button("Save metadata", lambda: self._save_metadata(fields, scope))
        save.setEnabled(not self.meta_busy)
        flow.addWidget(save)
        result = _label(self.meta_result, "small")
        flow.addWidget(result)
        self.meta_parts = {"save": save, "result": result}
        fold.body_layout.addWidget(row)
        return fold

    def _save_metadata(self, fields: dict, scope: QComboBox) -> None:
        """The metadata saved to the recording (``data-meta-save``): the fields changed, on this encounter or its run."""
        values = {key: (widget.currentData() if isinstance(widget, QComboBox) else widget.text()) for key, widget in fields.items()}
        try:
            log = cw.corrected(self.doc, self.state["segment"], values, scope.currentData() == "run")
        except ValueError as problem:
            self.meta_parts["result"].setText(str(problem))
            return
        self.meta_busy, self.meta_open = True, True
        self.meta_parts["save"].setEnabled(False)
        self._post_app("save", "/api/sessions", {"file": self.where.get("value"), "log": log})

    def _report_form(self) -> QWidget:
        """A shared log's report to its server's operator (``reportHTML``), folded; open while anything is written, sent
        or said."""
        report = self.report
        fold = Section(cw.REPORT_HEAD, None, bool(report["details"] or report["status"] or report["busy"]))
        fold.button.setAccessibleName(cw.REPORT_HEAD)
        layout = fold.body_layout
        layout.addWidget(_muted(cw.REPORT_NOTE))
        reason = QComboBox()
        reason.setAccessibleName("Reason")
        for value, words in cw.REPORT_REASONS:
            reason.addItem(words, value)
        reason.setCurrentIndex(max(0, reason.findData(report["reason"])))
        reason.activated.connect(lambda _i: report.update(reason=reason.currentData()))
        details = QPlainTextEdit(report["details"])
        details.setAccessibleName("Details")
        details.setFixedSize(260, 72)                                # ``rows="3"``

        def written() -> None:
            text = details.toPlainText()
            if len(text) > 1000:                                     # ``maxlength="1000"``
                details.setPlainText(text[:1000])
                return
            report["details"] = text
        details.textChanged.connect(written)
        send = _button("Send report", self._send_report)
        send.setEnabled(not report["busy"])
        row = QWidget()                                              # the reason, the details and Send on one line
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        flow.addWidget(_field_row("Reason", reason))
        flow.addWidget(_field_row("Details (10–1,000 characters)", details))
        flow.addWidget(send)
        layout.addWidget(row)
        layout.addWidget(_label(report["status"]))
        return fold

    def _send_report(self) -> None:
        """The report sent (``data-report-send``), once at a time."""
        if self.report["busy"]:
            return
        self.report["busy"] = True
        path = f"/api/v1/logs/{cw.encode_component(self.where.get('value', ''))}/reports"
        self._ask("report", path, body={"reason": self.report["reason"], "details": self.report["details"]})
        self.draw()

    def _publish_form(self) -> QWidget:
        """A recording's upload to the log server (``Publish this log``), folded; open once it is sent."""
        publish = self.publish
        fold = Section(cw.PUBLISH_HEAD, None, bool(publish["result"]) or publish["busy"])
        fold.button.setAccessibleName(cw.PUBLISH_HEAD)
        row, line = _plain(QHBoxLayout, 8)
        visibility = QComboBox()
        visibility.setAccessibleName("Upload visibility")
        for value in cw.VISIBILITIES:
            visibility.addItem(value, value)
        visibility.setCurrentIndex(max(0, visibility.findData(publish["visibility"])))
        visibility.activated.connect(lambda _i: publish.update(visibility=visibility.currentData()))
        line.addWidget(visibility)
        upload = _button("Upload saved session", self._upload)
        upload.setEnabled(not publish["busy"])
        line.addWidget(upload)
        result = _label(publish["result"], rich=True)
        result.setOpenExternalLinks(True)
        line.addWidget(result, 1)
        self.publish_parts = {"upload": upload, "result": result}
        fold.body_layout.addWidget(row)
        return fold

    def _upload(self) -> None:
        """The recording uploaded (``data-upload``) at the visibility chosen."""
        self.publish["busy"] = True
        self.publish_parts["upload"].setEnabled(False)
        self._post_app("publish", "/api/sessions/share", {"file": self.where.get("value"), "visibility": self.publish["visibility"]})

    def _published(self, words: str) -> None:
        """The upload's answer: its link and warning, or why it failed, the fold left as it is."""
        self.publish.update(busy=False, result=words)
        parts = self.publish_parts
        if parts is not None:
            try:
                parts["result"].setText(words)
                parts["upload"].setEnabled(True)
            except RuntimeError:                                     # drawn again meanwhile: the new fold shows it
                pass

    # ---------------------------------------------------------------- the encounter's context, mapping and insights (0.2.463)
    def _context(self, d: dict) -> QWidget | None:
        """The automatic encounter context, folded (``classificationHTML``); nothing when the log holds none."""
        c = cw.encounter_context(d)
        if c is None:
            return None
        fold = Section(c["summary"].replace("&", "&&"), None, False)
        fold.button.setAccessibleName("Automatic encounter context")
        layout = fold.body_layout
        for words in [c["note"], c["line"]] + c["notes"]:
            layout.addWidget(_label(words))
        if c["npcs"]:
            layout.addWidget(self._table(cw.CONTEXT_COLUMNS, c["npcs"]))
        if c["omitted"]:
            layout.addWidget(_label(c["omitted"]))
        return _noted(fold)

    def _mapping(self) -> QWidget | None:
        """The mapping coverage, folded (``catalogHTML``), with **Export mapping report**; nothing for an older log."""
        m = cw.mapping_coverage(self.doc, self.state)
        if m is None:
            return None
        fold = Section(m["summary"], None, False)
        fold.button.setAccessibleName("Mapping coverage")
        layout = fold.body_layout
        layout.addWidget(_label(m["note"]))
        layout.addWidget(_label(m["line"]))
        if m["source"]:
            layout.addWidget(_muted(m["source"]))
        layout.addWidget(self._grid(cw.UNMAPPED_COLUMNS, m["rows"], {c: 1 for c in range(len(cw.UNMAPPED_COLUMNS))}))
        if m["unidentified"] is not None:
            layout.addWidget(_label(f"<b>{cw.UNIDENTIFIED_HEAD}</b>", rich=True))
            layout.addWidget(_muted(m["unidentified"]["note"]))
            layout.addWidget(self._grid(cw.UNIDENTIFIED_COLUMNS, m["unidentified"]["rows"], {0: 1, 1: 1}))
        row, line = _plain(QHBoxLayout, 8)
        line.addWidget(_button(cw.EXPORT_MAPPINGS, lambda report=m["report"]: self._export_mappings(report)))
        self.mapping_status = _label("", "small")
        line.addWidget(self.mapping_status, 1)
        layout.addWidget(row)
        return _noted(fold)

    def _ask_where(self, name: str) -> str:
        """Where a file is saved, the computer's Downloads folder offered (where a browser puts a download)."""
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, cw.EXPORT_MAPPINGS, os.path.join(folder, name), "JSON (*.json)")
        return path

    def _export_mappings(self, report: dict) -> None:
        """The mapping report saved where the computer's user chooses (``data-export-mappings``)."""
        path = self._ask_where(cw.MAPPING_FILE)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(cw.mapping_report(report))
        except OSError as problem:
            words = f"The mapping report could not be saved: {problem}"
        else:
            words = f"Mapping report saved: {path}"
        if self.mapping_status is not None:
            self.mapping_status.setText(words)

    def _insights(self, d: dict) -> QWidget:
        """The encounter insights, open (``insightsHTML``); or why an older log holds none."""
        model = cw.insights(self.doc, d, self.state)
        if model.get("missing"):
            return _note(model["missing"])
        fold = Section(cw.INSIGHTS_HEAD, None, True)
        fold.button.setAccessibleName(cw.INSIGHTS)
        self.insights_fold = fold
        layout = fold.body_layout

        def part(words: str, note: str, columns=None, rows=None, rich: bool = False) -> None:
            layout.addWidget(_label(f"<b>{html.escape(words, quote=False)}</b>", rich=True))
            layout.addWidget(_label(note, "small", rich=rich))
            if columns is not None:
                layout.addWidget(self._rows(columns, rows, d))
        layout.addWidget(_label(model["intro"]))
        if model["limits"]:
            layout.addWidget(_label(model["limits"]))
        part("Evidence coverage", cw.COVERAGE_NOTE)
        if model["coverage"] is None:
            layout.addWidget(_label(cw.COVERAGE_OLDER))
        else:
            layout.addWidget(self._rows(cw.COVERAGE_COLUMNS, model["coverage"], d))
        pressure = model["pressure"]
        if pressure is not None:
            part("Peak recorded pressure windows", pressure["note"])
            layout.addWidget(_muted(pressure["line"]))
            layout.addWidget(self._rows(cw.PRESSURE_COLUMNS, pressure["windows"], d))
            part("Incoming abilities", cw.INCOMING_NOTE, cw.INCOMING_COLUMNS, pressure["incoming"])
        part("Boss HP milestones", cw.MILESTONES_NOTE, cw.MILESTONE_COLUMNS, model["milestones"])
        part("Healing relationships", model["healing_note"], cw.HEALING_COLUMNS, model["healing"])
        effective = model["effective"]
        if effective is not None:
            part("Effective healing and overheal", effective["note"], cw.HEALERS_COLUMNS, effective["healers"], rich=True)
            layout.addWidget(self._rows(cw.HEALING_PAIRS_COLUMNS, effective["pairs"], d))
            if effective["omitted"]:
                layout.addWidget(_muted(effective["omitted"]))
        part("Imported buff windows", model["buffs_note"], cw.BUFF_WINDOWS_COLUMNS, model["buffs"])
        part("Observed ability effects", cw.EFFECTS_NOTE, cw.EFFECTS_COLUMNS, model["effects"])
        part("Opening effect sequence", cw.OPENING_NOTE, cw.OPENING_COLUMNS, model["opening"])
        return _noted(fold)

    # ---------------------------------------------------------------- the death recaps (0.2.462)
    def _recaps(self, v: dict) -> QWidget:
        """The player death recaps (``recapsHTML``): the encounter's recaps, the one opened with its effects and HP
        samples; or why the log holds none."""
        model = cw.recaps(self.doc, v, self.state)
        if model.get("missing"):
            return _note(model["missing"])
        box, column = _plain(spacing=8)
        self.recaps_box = box
        column.addWidget(_head("Player death recaps"))
        column.addWidget(_muted(model["intro"]))
        # the columns shared out evenly: the web page's recap tables have no wide first column (its HP readings' two
        # columns sit near the middle)
        column.addWidget(self._rows(cw.RECAP_COLUMNS, model["rows"], v, first=1))
        chosen = model["selected"]
        if chosen is None:
            column.addWidget(_label(model["none"]))
            return box
        column.addWidget(_label(f"<b>{html.escape(chosen['title'], quote=False)}</b>", rich=True))
        column.addWidget(_muted(chosen["note"]))
        column.addWidget(self._rows(cw.RECAP_EFFECT_COLUMNS, chosen["events"], v, first=1))
        column.addWidget(self._rows(cw.RECAP_HP_COLUMNS, chosen["health"], v, first=1))
        return box

    def _recap(self, key: str) -> None:
        """A recap opened (``data-recap``)."""
        self.state["recap"] = key
        self.draw()

    def _actions_tab(self, key: str) -> None:
        """A tab of the casts, buffs and break gauge chosen (``data-actions``)."""
        self.state["actions"] = key
        self.draw()

    def _actor_html(self, actor) -> str:
        """An actor as rich text (``actorHTML``): a player in their class's colour, anyone else plainly."""
        words = html.escape(cw.actor_label(actor))
        if cw.is_character(actor, self.doc):
            return f"<span style='color: {cr.class_colour(_dict(actor).get('class'), self.colours)};'>{words}</span>"
        return words

    def _cell(self, cell, v: dict):
        """A cell of the model's rows: text, an actor (with **Open recap** under a recap's), a recap's last hit, a skill
        with its icon, rich text, or a list of actors with counts."""
        if not isinstance(cell, dict):
            return cell
        r = v["r"]
        if "recap" in cell:                                          # a recap's player, and **Open recap** under them
            box, column = _plain(spacing=4)
            column.addWidget(self._actor(r.get(cell["actor"])))
            row, line = _plain(QHBoxLayout)
            open_recap = _button(cw.OPEN_RECAP, lambda key=cell["recap"]: self._recap(key))
            open_recap.setAccessibleName(f"Open the recap of {cw.actor_label(r.get(cell['actor']))} at {cell['at']}")
            line.addWidget(open_recap)
            line.addStretch(1)
            column.addWidget(row)
            return box
        if "hit" in cell:                                            # a recap's last hit: its attacker, then its words
            return _label(self._actor_html(r.get(cell["hit"])) + html.escape(cell["words"], quote=False), rich=True)
        if "actor" in cell:
            if cell.get("boss"):
                return _label(self._actor_html(r.get(cell["actor"])) + cw._muted_html("boss"), rich=True)
            return self._actor(r.get(cell["actor"]))
        if "ref" in cell:
            return self._actor(cell["ref"])
        if "skill" in cell:
            return self._skill_cell(cell.get("skill_id"), cell["skill"], False)
        if "html" in cell:
            return _label(cell["html"], rich=True)
        if "sources" in cell:
            return _label(" ".join((f"{self._actor_html(r.get(source))} ×{cw.js_string(n)}" if source else
                                    f"Not recorded ×{cw.js_string(n)}") for source, n in cell["sources"]), rich=True)
        if "aimed" in cell:
            return _label(" ".join(f"{self._actor_html(r.get(target))} ×{cw.js_string(n)}" for target, n in cell["aimed"])
                          or "—", rich=True)
        return ""

    def _rows(self, columns: list[str], rows: list[list], v: dict, first: int = 2) -> QWidget:
        """One of the section's tables, its first column with a larger share (``first``), as the web page's tables share
        the width."""
        return self._grid(columns, [[self._cell(c, v) for c in row] for row in rows],
                          {c: first if c == 0 else 1 for c in range(len(columns))})

    # ---------------------------------------------------------------- the timeline (0.2.459)
    def _timeline(self, v: dict, events: list[dict]) -> QWidget:
        """The recorded effect timeline (``timeline``): whose lanes are shown, the window, the lanes, and the effect
        inspected."""
        state = self.state
        model = cw.timeline(v, events, state, self.lanes_hidden, self.lanes_folded, self.colours)
        self.timeline_model = model
        box, column = _plain(spacing=8)
        column.addWidget(_head("Recorded effect timeline"))
        fold = Section(model["visibility"], None, self.lanes_open)
        fold.button.setAccessibleName("Player timeline visibility")
        fold.button.toggled.connect(lambda opened: setattr(self, "lanes_open", opened))
        fold.body_layout.addWidget(_muted(cw.LANE_NOTE))
        row = QWidget()
        row.setObjectName("plain")
        flow = FlowLayout(row, align=Qt.AlignLeft, gap=(12, 6))
        for player in model["players"]:
            tick = QCheckBox(player["label"])
            tick.setChecked(player["shown"])
            tick.toggled.connect(lambda shown, actor=player["id"]: self._lane_shown(actor, shown))
            flow.addWidget(tick)
        flow.addWidget(_button("Show all", self._lanes_all))
        flow.addWidget(_button("Expand all", self._lanes_open_all))
        fold.body_layout.addWidget(row)
        self.lanes_fold = fold
        column.addWidget(_noted(fold))
        controls, line = _plain(QHBoxLayout, 10)
        chosen = next((value for value, _words in model["windows"] if value == model["window"]), None)
        line.addWidget(self._pick("Window", model["windows"], chosen, self._window))
        line.addWidget(_button("Earlier", lambda: self._move_window(v, -1), enabled=model["earlier"]))
        line.addWidget(_button("Later", lambda: self._move_window(v, 1), enabled=model["later"]))
        line.addWidget(_label("Start", wrap=False))
        start = QDoubleSpinBox()
        start.setAccessibleName("Start")
        start.setDecimals(1)
        start.setSingleStep(0.5)
        start.setRange(0.0, model["latest"])
        start.setValue(model["start"])
        start.setKeyboardTracking(False)
        start.valueChanged.connect(self._start)
        line.addWidget(start)
        line.addWidget(_label(model["range"], wrap=False))
        line.addStretch(1)
        column.addWidget(controls)
        scrub = QSlider(Qt.Horizontal)
        scrub.setAccessibleName("Timeline window start")
        scrub.setRange(0, math.floor(model["latest"] * 2))           # half seconds (``step=".5"``)
        scrub.setValue(theme.js_round(model["start"] * 2))
        scrub.sliderReleased.connect(lambda: self._start(scrub.value() / 2))
        scrub.valueChanged.connect(lambda value: None if scrub.isSliderDown() else self._start(value / 2))
        self.scrub = scrub
        column.addWidget(scrub)
        column.addWidget(_muted(model["note"]))
        timeline = Timeline(model, self._lane_name, self._lane_folded, self._skill_picture)
        place = (model["start"], model["span"])
        if self.timeline_place == place and self.timeline_scroll is not None:
            timeline.keep(self.timeline_scroll)                    # scrolled as it was, the window the same
        self.timeline_place, self.timeline_scroll = place, None
        for bar in (timeline.horizontalScrollBar(), timeline.verticalScrollBar()):
            bar.valueChanged.connect(lambda _value, timeline=timeline: setattr(self, "timeline_scroll", timeline.scrolled()))
        if self.pictures is not None:
            self.pictures.changed.connect(timeline.tracks.update)    # a skill's icon read since
        self.timeline = timeline
        column.addWidget(timeline)
        panel = QFrame()
        panel.setObjectName("note")
        panel_line = QVBoxLayout(panel)
        panel_line.setContentsMargins(0, 0, 0, 0)
        words = _label(self.effect or cw.EFFECT_HINT)
        words.setAccessibleName("Effect inspected")
        panel_line.addWidget(words)
        self.effect_words = words
        timeline.inspected.connect(lambda detail: self._inspect_effect(detail))
        column.addWidget(panel)
        return box

    def _inspect_effect(self, detail: str) -> None:
        """An effect inspected (``data-effect-detail``): it stays in the panel while the encounter is shown."""
        self.effect = detail
        self.effect_words.setText(detail)

    def _skill_picture(self, address: str):
        return self.pictures.by_address(address) if self.pictures is not None else None

    def _lane_name(self, lane: dict) -> QWidget:
        """A lane's name in its class's colour (``.cr-lane-name``), with its Collapse and Hide buttons when it is open."""
        cell = QFrame()
        cell.setObjectName("crLaneName")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addStretch(1)
        layout.addWidget(self._name(lane["actor"]))
        if not lane["collapsed"]:
            controls, line = _plain(QHBoxLayout, 4)
            line.addWidget(self._lane_button("Collapse", lane, self._lane_fold))
            line.addWidget(self._lane_button("Hide", lane, self._lane_hide))
            line.addStretch(1)
            layout.addWidget(controls)
        layout.addStretch(1)
        return cell

    def _lane_folded(self, lane: dict) -> QWidget:
        """A collapsed lane's own controls, where its markers would be (``.cr-lane-collapsed``)."""
        cell, line = _plain(QHBoxLayout, 4)
        line.setContentsMargins(10, 5, 10, 5)
        line.addWidget(self._lane_button("Expand", lane, self._lane_fold))
        line.addWidget(self._lane_button("Hide", lane, self._lane_hide))
        line.addWidget(_label("Timeline collapsed", "small", wrap=False))
        line.addStretch(1)
        return cell

    @staticmethod
    def _lane_button(words: str, lane: dict, action) -> QWidget:
        button = _button(words, lambda: action(lane["id"]))
        button.setAccessibleName(f"{words} {lane['label']}")
        return button

    def _lane_fold(self, actor) -> None:
        """A lane collapsed, or expanded again (``data-timeline-collapse``)."""
        self.lanes_folded ^= {actor}
        self.draw()

    def _lane_hide(self, actor) -> None:
        self.lanes_hidden.add(actor)
        self.draw()

    def _lane_shown(self, actor, shown: bool) -> None:
        """A player's lane shown or hidden from the lanes' visibility (``data-timeline-visible``)."""
        if shown:
            self.lanes_hidden.discard(actor)
        else:
            self.lanes_hidden.add(actor)
        self.draw()

    def _lanes_all(self) -> None:
        self.lanes_hidden.clear()
        self.draw()

    def _lanes_open_all(self) -> None:
        self.lanes_folded.clear()
        self.draw()

    def _window(self, value) -> None:
        """The window's length chosen (``data-timeline-window``): a number of seconds, or the whole encounter."""
        self.state["timeline_window"] = value if value is not None else 0
        self.draw()

    def _move_window(self, v: dict, direction: int) -> None:
        cw.moved_window(self.state, v["segment"].get("duration"), direction)
        self.draw()

    def _start(self, value) -> None:
        """The window's start typed or scrubbed to (``data-time-start``, ``data-time-scrub``)."""
        self.state["timeline_start"] = float(value)
        self.draw()

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
