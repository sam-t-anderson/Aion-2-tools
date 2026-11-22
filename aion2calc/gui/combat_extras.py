"""Personal records in the native Combat Logs page (0.2.454), as community.js draws the app's "Personal records" tab:
its filters (mode, metric, encounter type, game version, boss, difficulty, region, party size), the recorded boss
defeats (read once opened), each class's performance as a distribution per encounter, and a character's best records,
every matching attempt, and its consistency and trends. Everything is read from the log server through the app's
proxy; a log opens in its review on this page (0.2.457).
"""
from __future__ import annotations

import html

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QToolTip, QVBoxLayout, QWidget

from . import combat as cb
from . import combat_records as cr
from . import combat_views as cv
from . import theme
from .api import AppApi, Requests
from .combat_community import Community, _empty, _note
from .combat_saved import TIMEOUT, Section, _button, _clear, _head, _label, _row
from .result_windows import GridTable
from .results import _dict, _truthy, js_text


class BoxPlot(QWidget):
    """A class's distribution (``svg viewBox="0 0 360 32"``): its range as a line, its quartiles as a box in the class's
    colour, its median as a mark."""

    def __init__(self, box: dict, maximum: float, colour: str, tip: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.box, self.maximum, self.colour = box, maximum or 1.0, QColor(colour)
        self.setToolTip(tip)
        self.setMinimumWidth(230)
        self.setMaximumWidth(500)
        self.setFixedHeight(32)

    def sizeHint(self) -> QSize:
        return QSize(360, 32)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = self.width() / 360.0
        x = lambda v: v / self.maximum * 350 * scale        # noqa: E731
        ink = QColor(theme.COLORS["text"])
        painter.setPen(QPen(ink, 1))
        painter.drawLine(QPointF(x(self.box["min"]), 16), QPointF(x(self.box["max"]), 16))
        painter.fillRect(QRectF(x(self.box["q1"]), 6, max(2.0 * scale, x(self.box["q3"]) - x(self.box["q1"])), 20), self.colour)
        painter.drawLine(QPointF(x(self.box["median"]), 3), QPointF(x(self.box["median"]), 29))
        painter.end()


class TrendChart(QWidget):
    """A character's recorded rates in upload order (``svg viewBox="0 0 600 115"``): a line through its samples, each a
    dot whose words show on hover."""

    def __init__(self, points: list[tuple[float, float, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.points = points
        self.setFixedHeight(115)
        self.setMaximumWidth(800)

    def sizeHint(self) -> QSize:
        return QSize(600, 115)

    def _place(self, x: float, y: float) -> QPointF:
        return QPointF(x * self.width() / 600.0, y * self.height() / 115.0)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ink = QColor(theme.COLORS["text"])
        painter.setPen(QPen(ink, 2))
        painter.drawPolyline(QPolygonF([self._place(x, y) for x, y, _words in self.points]))
        painter.setPen(Qt.NoPen)
        painter.setBrush(ink)
        for x, y, _words in self.points:
            painter.drawEllipse(self._place(x, y), 3, 3)
        painter.end()

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            near = [(abs(self._place(x, y).x() - event.pos().x()) + abs(self._place(x, y).y() - event.pos().y()), words)
                    for x, y, words in self.points]
            best = min(near, default=None)
            if best is not None and best[0] <= 8:
                QToolTip.showText(event.globalPos(), best[1], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class PersonalRecords(QWidget):
    """Personal records (community.js with its boss defeats, class performance and records). ``open_web`` opens a
    page of the app (a log's review); ``shared`` holds the server's facets the community views read too."""

    def __init__(self, api: AppApi | None, shared: Community, open_web=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.shared, self.open_web = shared, open_web
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.query: dict = {"combat_mode": "pve", "metric": "dps"}
        self.identity: dict | None = None
        self.record_page = 1
        self.asked: dict[str, int] = {}                      # each part's latest question; an older answer is let go
        self.boss_answer = None
        self.colours: dict = {}
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(_label(cr.RECORDS_NOTE, "small"))
        self.filters_box = QWidget()
        self.filters_box.setObjectName("plain")
        self.filters = QVBoxLayout(self.filters_box)
        self.filters.setContentsMargins(0, 0, 0, 0)
        self.filters.setSpacing(6)
        box.addWidget(self.filters_box)
        # the recorded boss defeats, read once opened
        self.bosses = Section("Recorded boss defeats", None, False)
        self.bosses.button.toggled.connect(lambda opened: self.load_bosses() if opened and self.boss_answer is None else None)
        self.bosses.body_layout.addWidget(_label(cr.BOSSES_NOTE, "small"))
        self.boss_search = QLineEdit()
        self.boss_search.setPlaceholderText("Boss name or NPC ID")
        self.boss_search.setAccessibleName("Search displayed boss observations")
        self.boss_search.textChanged.connect(lambda _text: self._bosses())
        self.boss_refresh = _button("Refresh boss observations", self.load_bosses)
        self.bosses.body_layout.addWidget(_row(_label("Search displayed bosses", "small", wrap=False), self.boss_search,
                                               self.boss_refresh))
        self.boss_said = _label(cr.BOSSES_WAITING, "small")
        self.bosses.body_layout.addWidget(self.boss_said)
        self.boss_rows = QVBoxLayout()
        self.boss_rows.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setObjectName("plain")
        holder.setLayout(self.boss_rows)
        self.bosses.body_layout.addWidget(holder)
        box.addWidget(self.bosses)
        # class performance
        box.addWidget(_head("Class performance"))
        box.addWidget(_label(cr.PERFORMANCE_NOTE, "small"))
        self.performance = self._part(box)
        # personal records
        box.addWidget(_head("Personal records"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Character name")
        self.name.setAccessibleName("Character name")
        self.server = QComboBox()
        self.server.setAccessibleName("Character server")
        self.server.addItem("Choose a server", "")
        for group, servers in cr.server_groups():
            self.server.addItem(group, None)
            index = self.server.count() - 1
            self.server.model().item(index).setEnabled(False)         # an ``optgroup``'s label
            for value, world in servers:
                self.server.addItem(f"  {world}", value)
        self.character = QLineEdit()
        self.character.setPlaceholderText("Database character ID (optional)")
        self.character.setAccessibleName("Database character ID")
        box.addWidget(_row(self.name, self.server, self.character, _button("Find records", self.find_records)))
        self.record_note = _label("", "small")
        box.addWidget(self.record_note)
        self.records = self._part(box)
        self.history = self._part(box)
        box.addWidget(_head("Character consistency and trends"))
        self.consistency = self._part(box)
        self.consistency.addWidget(_label(cr.CONSISTENCY_WAITING))
        self.record_line = _label("", wrap=False)
        self.record_previous = _button("Previous records", lambda: self._turn(-1), enabled=False)
        self.record_next = _button("Next records", lambda: self._turn(1), enabled=False)
        box.addWidget(_row(self.record_previous, self.record_line, self.record_next))
        self._ask("ui", "/api/ui", proxied=False)
        self._ask("facets", "/api/v1/report-facets")

    @staticmethod
    def _part(box: QVBoxLayout) -> QVBoxLayout:
        holder = QWidget()
        holder.setObjectName("plain")
        part = QVBoxLayout(holder)
        part.setContentsMargins(0, 0, 0, 0)
        part.setSpacing(6)
        box.addWidget(holder)
        return part

    def stop(self) -> None:
        if self.requests is not None:
            self.requests.stop()

    # ---------------------------------------------------------------- questions and answers
    def _ask(self, kind: str, path: str, proxied: bool = True) -> None:
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if self.requests is not None:
            self.requests.get(f"{kind}:{self.asked[kind]}", cv.community_path(path) if proxied else path)

    def _current(self, name: str) -> str | None:
        kind, _, number = name.partition(":")
        return kind if number == str(self.asked.get(kind)) else None

    def _replied(self, name: str, answer) -> None:
        kind = self._current(name)
        if kind is None:
            return
        if kind != "ui" and isinstance(answer, dict) and _truthy(answer.get("error")):   # app.js's api() refuses it
            self._failed(name, js_text(answer["error"]))
        elif kind == "ui":
            self.colours = _dict(_dict(answer).get("combat_colors"))
        elif kind == "facets":
            self.shared.facets = answer if isinstance(answer, dict) else {}
            self.query["game_patch"] = js_text(_dict(answer).get("latest_submitted_patch") or "")
            self._filters()
            self.load()
        elif kind == "bosses":
            self.boss_answer = answer
            self.boss_refresh.setEnabled(True)
            self._bosses()
        elif kind == "performance":
            self._performance(answer)
        elif kind == "records":
            self._records(answer)
        elif kind == "consistency":
            self._consistency(answer)

    def _failed(self, name: str, why: str) -> None:
        kind = self._current(name)
        if kind is None or kind == "ui":
            return
        if kind == "facets":                                      # the filters as they are, said where the web page says it
            _clear(self.performance)
            self.performance.addWidget(_label(why))
        elif kind == "bosses":
            self.boss_answer = None
            self.boss_said.setText(cr.BOSSES_FAILED)
            _clear(self.boss_rows)
            self.boss_refresh.setEnabled(True)
        elif kind == "performance":
            _clear(self.performance)
            self.performance.addWidget(_note(why))
        elif kind == "records":
            self.record_note.setText(why)
        elif kind == "consistency":
            _clear(self.consistency)
            self.consistency.addWidget(_label(f"Consistency unavailable: {why}"))

    # ---------------------------------------------------------------- the filters
    def _filters(self) -> None:
        _clear(self.filters)
        rows = [QHBoxLayout(), QHBoxLayout()]
        for index, key in enumerate(cr.FILTER_KEYS):
            pick = QComboBox()
            pick.setAccessibleName(cr.filter_name(key))
            for value, words in cr.filter_choices(key, self.shared.facets):
                pick.addItem(words, value)
            pick.setCurrentIndex(max(0, pick.findData(self.query.get(key, ""))))
            pick.activated.connect(lambda _i, key=key, pick=pick: self.choose(key, pick.currentData() or ""))
            rows[index // 4].addWidget(_label(cr.filter_name(key), "small", wrap=False))
            rows[index // 4].addWidget(pick)
        rows[1].addWidget(_button("Refresh", self.load))
        for line in rows:
            line.setSpacing(6)
            line.addStretch(1)
            holder = QWidget()
            holder.setObjectName("plain")
            holder.setLayout(line)
            self.filters.addWidget(holder)

    def choose(self, key: str, value: str) -> None:
        """A filter chosen: the parts read again, and the records when a character was searched."""
        self.query = cr.query_after(self.query, key, value)
        self._filters()
        self.load()
        if self.identity and self.identity.get("server"):
            self.record_page = 1
            self.find(self.identity)

    # ---------------------------------------------------------------- boss defeats and class performance
    def load(self) -> None:
        """The class performance, and the boss defeats as the mode allows (``load``)."""
        self._sync_bosses()
        _clear(self.performance)
        self.performance.addWidget(_empty(cb.LOADING))
        self._ask("performance", "/api/v1/performance?" + cr.params(self.query))

    def _sync_bosses(self) -> None:
        self.asked["bosses"] = self.asked.get("bosses", 0) + 1        # an answer under way is let go
        self.boss_answer = None
        self.bosses.setVisible(self.query.get("combat_mode") == "pve")
        _clear(self.boss_rows)
        self.boss_refresh.setEnabled(True)
        self.boss_said.setText(cr.BOSSES_WAITING)
        if self.bosses.isVisibleTo(self) and self.bosses.button.isChecked():
            self.load_bosses()

    def load_bosses(self) -> None:
        if self.query.get("combat_mode") != "pve" or not self.bosses.button.isChecked():
            return
        self.boss_said.setText(cr.BOSSES_LOADING)
        self.boss_refresh.setEnabled(False)
        self._ask("bosses", cr.bosses_path(self.query))

    def _bosses(self) -> None:
        if self.boss_answer is None:
            return
        groups = cr.boss_groups(self.boss_answer, self.boss_search.text())
        self.boss_said.setText(cr.bosses_message(self.boss_answer, len(groups)))
        _clear(self.boss_rows)
        cells = []
        for g in groups:
            row = cr.boss_row(g)
            when = f"{html.escape(row['defeated'])}<br><span style='color: {theme.COLORS['muted']};'>{html.escape(row['age'])}</span>"
            if row["basis"]:
                when += f"<br><span style='color: {theme.COLORS['muted']};'>{html.escape(row['basis'])}</span>"
            source = (_button(row["source"], lambda log=row["log"]: self._open(log, "pve")) if row["log"]
                      else row["source"])
            cells.append([_label(f"{html.escape(row['boss'])}<br><span style='color: {theme.COLORS['muted']};'>"
                                 f"{html.escape(row['npc'])}</span>", rich=True),
                          f"{row['region']}\n{row['build']}", row["place"], _label(when, rich=True), row["observations"],
                          f"{row['engaged']}\n{row['roster']}",
                          _label(f"Unknown<br><span style='color: {theme.COLORS['muted']};'>Respawn rule and location scope "
                                 "unverified</span>", rich=True), source])
        self.boss_rows.addWidget(GridTable(cr.BOSS_COLUMNS, cells, {0: 2, 1: 2, 2: 1, 3: 2, 5: 2, 6: 2}, left=True))
        if not cells:
            self.boss_rows.addWidget(_label(cr.NO_SUBMISSIONS, "tcell"))
        self.boss_rows.addWidget(_label(cr.BOSSES_FOOT, "small"))

    def _performance(self, answer) -> None:
        _clear(self.performance)
        self.performance.addWidget(_label(cr.performance_note(answer), "small"))
        metric = js_text(self.query.get("metric") or "dps").upper()
        for title, groups in cr.performance_buckets(answer):
            self.performance.addWidget(_label(title, "bucketHead"))
            maximum = cr.bucket_maximum(groups)
            cells = []
            for g in groups:
                row = cr.performance_row(g)
                colour = cr.class_colour(row["class"], self.colours)
                cells.append([_label(f"<span style='color: {colour};'>{html.escape(row['class'])}</span>", rich=True, wrap=False),
                              BoxPlot(row["box"], maximum, colour, row["tip"]), row["median"], row["range"], row["parses"],
                              row["coverage"]])
            heads = ["Class", f"{metric} distribution (min / quartiles / max)", f"Median {metric}", "Range",
                     "Parses · distinct characters", "Coverage"]
            self.performance.addWidget(GridTable(heads, cells, {1: 3, 5: 2}, left=True))

    # ---------------------------------------------------------------- personal records
    def find_records(self) -> None:
        """A character's records (``Find records``): by name, server and, when known, its database ID."""
        self.record_page = 1
        self.find({"name": self.name.text().strip(), "server": (self.server.currentData() or "").strip(),
                   "character_id": self.character.text().strip()})

    def find(self, identity: dict) -> None:
        self.identity = identity
        query = cr.records_query(self.query, identity, self.record_page)
        _clear(self.consistency)
        self.consistency.addWidget(_label(cr.CONSISTENCY_LOADING))
        self._ask("consistency", "/api/v1/consistency?" + query)
        self._ask("records", "/api/v1/records?" + query)

    def _turn(self, step: int) -> None:
        if self.identity is not None:
            self.record_page = max(1, self.record_page + step)
            self.find(self.identity)

    def _records(self, answer) -> None:
        d = _dict(answer)
        self.record_note.setText(f"{js_text(d.get('identity'))}. {js_text(d.get('note'))}")
        metric = js_text(self.query.get("metric") or "dps").upper()
        mode = self.query.get("combat_mode") or "pve"
        _clear(self.records)
        rows = cr.record_rows(answer, metric)
        cells = [[_button(r["boss"], lambda r=r: self._open(r["log"], mode)), r["context"], r["class"], r["best"], r["attempts"]]
                 for r in rows]
        self.records.addWidget(GridTable(["Encounter", "Type · version · difficulty", "Class", f"Best {metric}", "Attempts"], cells,
                                         {1: 3, 2: 1}, left=True))
        if not cells:
            self.records.addWidget(_label(cr.NO_SUBMISSIONS, "tcell"))
        _clear(self.history)
        self.history.addWidget(_label(cr.HISTORY_TITLE, "bucketHead"))
        cells = []
        for r in cr.history_rows(answer):
            who = html.escape(r["name"]) + (" <span style='color: #6fcf7a;' title='Verified: claimed by its player'>✓</span>"
                                            if r["verified"] else "")
            who += f" <span style='color: {theme.COLORS['muted']};'>(hidden by its player)</span>" if r["pseudonym"] else ""
            who += f" · {html.escape(r['server'])}"
            cells.append([_button(r["boss"], lambda r=r: self._open(r["log"], mode)), _label(who, rich=True), r["score"],
                          r["ranking"], r["recorded"]])
        self.history.addWidget(GridTable(["Encounter", "Character · server", metric, "Ranking status", "Recorded"], cells,
                                         {1: 3, 3: 1, 4: 1}, left=True))
        if not cells:
            self.history.addWidget(_label(cr.NO_SUBMISSIONS, "tcell"))
        pager = cr.records_pager(answer, self.record_page)
        self.record_line.setText(pager["line"])
        self.record_previous.setEnabled(pager["previous"])
        self.record_next.setEnabled(pager["next"])

    def _consistency(self, answer) -> None:
        _clear(self.consistency)
        self.consistency.addWidget(_label(cr.consistency_note(answer), "small"))
        metric = js_text(_dict(answer).get("metric") or "").upper()
        mode = self.query.get("combat_mode") or "pve"
        for g in [g for g in (_dict(answer).get("groups") or []) if isinstance(g, dict)]:
            group = cr.consistency_group(g, metric)
            fold = Section(group["title"], None, False)
            fold.body_layout.addWidget(_label(group["spread"]))
            fold.body_layout.addWidget(_label(group["trend"]))
            fold.body_layout.addWidget(_label(group["samples"], "small"))
            fold.body_layout.addWidget(TrendChart(group["points"]))
            cells = [[r["uploaded"], r["score"], r["deaths"], _button(r["open"], lambda r=r: self._open(r["log"], mode))]
                     for r in group["rows"]]
            fold.body_layout.addWidget(GridTable(["Upload received", metric, "Recorded player deaths", "Log"], cells,
                                                 {0: 2, 1: 1, 2: 2}, left=True))
            if not cells:
                fold.body_layout.addWidget(_label(cr.NO_SUBMISSIONS, "tcell"))
            self.consistency.addWidget(fold)

    def _open(self, log_id, mode: str) -> None:
        if self.open_web is not None and _truthy(log_id):
            self.open_web(cv.shared_page(log_id, mode))

    def refresh(self) -> None:
        self.load()
