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

The rest of the review (its timeline, events, abilities, actions, death recaps, insights, rankings, reports,
comparisons and movement replay) opens in the web interface for now, from a button on the page.
"""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import combat_review as cw
from . import combat_records as cr
from . import combat_views as cv
from . import theme
from .account import TIER_COLOURS
from .account_page import _parse_pill
from .api import AppApi, Requests
from .combat_community import _note
from .combat_review_charts import HP, LINE, PingChart, RateChart
from .combat_saved import TIMEOUT, Section, _button, _clear, _head, _label
from .database_page import Window
from .pictures import Pictures
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
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(14)

    def stop(self) -> None:
        self.soon.stop()
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

    def choose_metric(self, key: str) -> None:
        """A metric chosen (``data-metric``). Not ``metric``: ``QWidget.metric()`` is Qt's own, asked for the page's paint
        metrics."""
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
            tab = _button(words, lambda key=key: self.choose_metric(key), "primary" if self.state["metric"] == key else "small")
            line.addWidget(tab)
        line.addStretch(1)
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
