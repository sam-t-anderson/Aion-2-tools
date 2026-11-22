"""The community's combat log views in the native Combat Logs page (0.2.453), as logs-view.js draws them: Community
Combat Logs (Browse logs' first list), Completed-run speed, Boss progression and Highest observed build points. Each
reads the log server through the app's proxy (``/api/community``), as the web page does; a fight's log opens in its
review on this page (0.2.457).

The views share the server's facets, read once, and whether mini-bosses are shown (kept as the web page keeps it). A view
answers only its latest question: an answer to one asked before a filter changed is let go.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import combat as cb
from . import combat_views as cv
from . import theme
from .api import AppApi, Requests
from .combat_saved import TIMEOUT, _button, _clear, _label, _row
from .pictures import Pictures
from .result_windows import GridTable
from .results import _dict, _truthy, js_text

ICON = 22
CLASS_ICON = 20


class Community(QObject):
    """What the views share (``comm``): the server's facets once read, and whether mini-bosses are shown."""

    def __init__(self, store, parent: QObject | None = None):
        super().__init__(parent)
        self.store = store
        self.facets: dict | None = None
        self.mini = store.value(cb.MINI_KEY) == "1"

    def show_mini(self, shown: bool) -> None:
        self.mini = bool(shown)
        self.store.setValue(cb.MINI_KEY, "1" if self.mini else "0")


def _note(words: str) -> QFrame:
    """A note (``.note``): why a view could not be read."""
    note = QFrame()
    note.setObjectName("note")
    line = QVBoxLayout(note)
    line.setContentsMargins(0, 0, 0, 0)
    line.addWidget(_label(words))
    return note


def _empty(words: str) -> QLabel:
    label = _label(words, "empty")
    label.setAlignment(Qt.AlignCenter)
    return label


def _muted(words: str) -> QLabel:
    return _label(f"<span style='color: {theme.COLORS['muted']};'>{html.escape(words)}</span>", rich=True)


def _picture(pixmap, size: int, tip: str = "") -> QLabel | None:
    if pixmap is None or pixmap.isNull():
        return None
    face = QLabel()
    face.setFixedSize(size, size)
    face.setScaledContents(True)
    face.setPixmap(pixmap)
    if tip:
        face.setToolTip(tip)
    return face


class _View(QWidget):
    """A community view: its requests, the shared facets, and its latest question."""

    def __init__(self, api: AppApi | None, shared: Community, open_web=None, pictures: Pictures | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.shared, self.open_web, self.pictures = shared, open_web, pictures
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.soon = QTimer(self)                                # pictures that come together, drawn once
        self.soon.setSingleShot(True)
        self.soon.setInterval(120)
        self.soon.timeout.connect(self.redraw)
        if self.pictures is not None:
            self.pictures.changed.connect(self.soon.start)
        self.asking = 0                                         # the latest question; an older answer is let go
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)

    def stop(self) -> None:
        self.soon.stop()
        if self.requests is not None:
            self.requests.stop()

    def _ask(self, kind: str, path: str) -> None:
        self.asking += 1
        if self.requests is not None:
            self.requests.get(f"{kind}:{self.asking}", cv.community_path(path))

    def _answer(self, name: str) -> str | None:
        """The kind of a current answer, or None for one asked before the latest question."""
        kind, _, number = name.partition(":")
        return kind if number == str(self.asking) else None

    def _replied(self, name: str, answer) -> None:
        kind = self._answer(name)
        if kind is None:
            return
        if isinstance(answer, dict) and _truthy(answer.get("error")):     # app.js's api() refuses it
            self._refused(kind, js_text(answer["error"]))
        elif kind == "facets":
            self.shared.facets = answer if isinstance(answer, dict) else {}
            self.render()
        else:
            self.answered(kind, answer)

    def _failed(self, name: str, why: str) -> None:
        kind = self._answer(name)
        if kind is not None:
            self._refused(kind, why)

    def _refused(self, kind: str, why: str) -> None:
        if kind == "facets":                                    # without facets the filters offer nothing
            self.shared.facets = {}
            self.render()
        else:
            self.refused(kind, why or cv.NOT_REACHED)

    def _facets(self) -> bool:
        """Whether the server's facets are read; when not, they are asked for and the view says it is loading."""
        if self.shared.facets is not None:
            return True
        _clear(self.box)
        self.box.addWidget(_empty(cb.LOADING))
        self._ask("facets", "/api/v1/report-facets")
        return False

    def _open(self, log_id, mode: str, segment=None) -> None:
        if self.open_web is not None and _truthy(log_id):
            self.open_web(cv.shared_page(log_id, mode, segment))

    def _boss(self, name: str, icon) -> QWidget:
        """A boss with its portrait when the app bundles it (``boss-cell``)."""
        cell = QWidget()
        cell.setObjectName("plain")
        line = QHBoxLayout(cell)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        face = _picture(self.pictures.by_address(icon) if self.pictures is not None else None, ICON)
        if face is not None:
            line.addWidget(face)
        line.addWidget(_label(name, wrap=False))
        line.addStretch(1)
        return cell

    # the views' own parts
    def render(self) -> None:
        raise NotImplementedError

    def redraw(self) -> None:
        pass

    def answered(self, kind: str, answer) -> None:
        pass

    def refused(self, kind: str, why: str) -> None:
        pass

    def _filters(self, f: dict, choices: dict, mode: bool, changed, mini_changed, cleared) -> QWidget:
        """The filters (``pveFilters``, ``renderCommunity``): their names over them, the mini-bosses' tick by the boss."""
        row = QWidget()
        row.setObjectName("plain")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 4)
        line.setSpacing(10)

        def field(words: str, widget: QWidget) -> None:
            box = QWidget()
            box.setObjectName("plain")
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            column.addWidget(_label(words, "small", wrap=False))
            column.addWidget(widget)
            line.addWidget(box, 0, Qt.AlignBottom)

        def combo(key: str, words: str, values) -> None:
            pick = QComboBox()
            pick.setAccessibleName(words)
            pick.setMinimumWidth(195 if key == "boss" else 120)
            pick.addItem("any", "")
            for value, name in values:
                pick.addItem(name, js_text(value))
            pick.setCurrentIndex(max(0, pick.findData(js_text(f.get(key) or ""))))
            pick.activated.connect(lambda _i, key=key, pick=pick: changed(key, pick.currentData() or ""))
            field(words, pick)

        if mode:
            pick = QComboBox()
            pick.setAccessibleName("Mode")
            pick.setMinimumWidth(120)
            pick.addItem("PvE", "pve")
            pick.addItem("PvP", "pvp")
            pick.setCurrentIndex(1 if f.get("combat_mode") == "pvp" else 0)
            pick.activated.connect(lambda _i: changed("combat_mode", pick.currentData()))
            field("Mode", pick)
        if not (mode and f.get("combat_mode") == "pvp"):
            combo("boss", "Boss", choices["boss"])
            tick = QCheckBox("show")
            tick.setAccessibleName("Show mini-bosses")
            tick.setToolTip(cb.MINI_TIP)
            tick.setChecked(self.shared.mini)
            tick.toggled.connect(mini_changed)
            field("Mini-bosses", tick)
        for key, words in cv.FILTER_FIELDS:
            combo(key, words, choices[key])
        line.addWidget(_button("Clear", cleared), 0, Qt.AlignBottom)
        line.addStretch(1)
        return row


class CommunityLogs(_View):
    """Community Combat Logs (``renderCommunity``, ``loadCommunity``): every public fight on the log server, fifty to
    a page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.f: dict = {"combat_mode": "pve"}
        self.page = 1
        self.rows: list[dict] = []
        self._reset()
        self.table: QVBoxLayout | None = None
        self.render()

    def _reset(self) -> None:
        self.buf: list[dict] = []
        self.server_page, self.done, self.total = 0, False, 0

    def refresh(self) -> None:
        """Read again from the server's first page, the filters and page as they are."""
        self._reset()
        self.render()

    def render(self) -> None:
        """The filters, then the page of fights."""
        if not self._facets():
            return
        _clear(self.box)
        choices = cv.community_choices(self.shared.facets, self.f, self.shared.mini)
        self.box.addWidget(self._filters(self.f, choices, True, self._changed, self._mini, self._cleared))
        holder = QWidget()
        holder.setObjectName("plain")
        self.table = QVBoxLayout(holder)
        self.table.setContentsMargins(0, 0, 0, 0)
        self.table.setSpacing(8)
        self.box.addWidget(holder)
        self.load()

    def _changed(self, key: str, value: str) -> None:
        self.f[key] = value
        self.page = 1
        self._reset()
        if key == "combat_mode":                                # another mode: its own encounters and bosses
            self.f["encounter_type"] = self.f["boss"] = ""
            self.render()
        else:
            self.load()

    def _mini(self, shown: bool) -> None:
        self.shared.show_mini(shown)
        if not self.shared.mini and cv.is_mini(self.f.get("boss"), _dict(self.shared.facets).get("boss_roles")):
            self.f["boss"] = ""                                  # a hidden boss cannot stay chosen
        self.page = 1
        self._reset()
        self.render()

    def _cleared(self) -> None:
        self.f = {"combat_mode": self.f.get("combat_mode") or "pve"}
        self.page = 1
        self._reset()
        self.render()

    def load(self) -> None:
        """The page's fights, the server's pages read until it is full (``loadCommunity``)."""
        if self.table is None:
            return
        _clear(self.table)
        self.table.addWidget(_empty(cb.LOADING))
        self._fill()

    def _fill(self) -> None:
        if len(self.buf) < self.page * cv.COMM_PER_PAGE and not self.done:
            self.server_page += 1
            self._ask("logs", "/api/v1/logs?" + cv.community_query(self.f, self.server_page))
        else:
            self.redraw()

    def answered(self, kind: str, answer) -> None:
        if kind != "logs":
            return
        rows, total, logs = cv.community_page(answer, self.f, self.shared.mini, self.shared.facets)
        if total is not None:
            self.total = total
        self.buf = cv.newest_first(self.buf + rows)
        self.done = cv.community_done(logs, self.total, self.server_page)
        self._fill()

    def refused(self, kind: str, why: str) -> None:
        if self.table is not None:
            _clear(self.table)
            self.table.addWidget(_note(why))

    def redraw(self) -> None:
        """The page of fights as the buffer holds them."""
        if self.table is None or len(self.buf) < self.page * cv.COMM_PER_PAGE and not self.done:
            return
        _clear(self.table)
        start = (self.page - 1) * cv.COMM_PER_PAGE
        self.rows = self.buf[start:start + cv.COMM_PER_PAGE]
        if not self.rows:
            self.table.addWidget(_empty(cv.NO_COMM))
            return
        mode = self.f.get("combat_mode") or "pve"
        cells = []
        for r in self.rows:
            words = cv.community_row(r, mode)
            cells.append([self._boss(words["boss"], r.get("icon")), words["kind"], self._party(words, r["members"]),
                          words["time"], words["uploader"], _muted(words["date"]), _muted(words["patch"]),
                          _button("view", lambda r=r, mode=mode: self._open(r.get("id"), mode, r.get("segment")))])
        heads = ["Skirmish" if mode == "pvp" else "Boss", "Type" if mode == "pvp" else "Difficulty", "Party", "Time",
                 "Uploaded by", "Date", "Product", ""]
        self.table.addWidget(GridTable(heads, cells, {0: 2, 1: 1, 2: 1, 4: 2, 5: 2, 6: 1}, left=True, right=(3,)))
        more = len(self.buf) > self.page * cv.COMM_PER_PAGE or not self.done
        self.table.addWidget(_row(_button("← Prev", self.previous, enabled=self.page > 1),
                                  _label(cv.pager_line(self.page, start, len(self.rows)), "small", wrap=False),
                                  _button("Next →", self.next_page, enabled=more)))

    def _party(self, words: dict, people: list[dict]) -> QWidget:
        """The party's size (``?`` when the game's party list was not captured) and its players' classes."""
        cell = QWidget()
        cell.setObjectName("plain")
        line = QHBoxLayout(cell)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(3)
        size = _label(f"<b>{html.escape(words['party'])}</b>" + (
            f"<span style='color: {theme.COLORS['muted']};'>?</span>" if words["unknown"] else ""), rich=True, wrap=False)
        if words["unknown"]:
            size.setToolTip(cv.PARTY_UNKNOWN)
        line.addWidget(size)
        line.addSpacing(4)
        for m in people:
            cls = js_text(m.get("class")).lower() if _truthy(m.get("class")) else ""
            if not cls:
                continue
            emblem = self.pictures.by_address(cv.CLASS_ART.format(cls)) if self.pictures is not None else None
            face = _picture(emblem, CLASS_ICON, cv.member_tip(m))
            if face is not None:
                line.addWidget(face)
        line.addStretch(1)
        return cell

    def previous(self) -> None:
        if self.page > 1:
            self.page -= 1
            self.load()

    def next_page(self) -> None:
        self.page += 1
        self.load()


class _Ranked(_View):
    """A view of a server list under the PvE filters, drawn again whole as a filter changes (``renderSpeed``,
    ``renderProgression``)."""

    path = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.f: dict = {}
        self.answer = None
        self.problem: str | None = None
        self.content: QVBoxLayout | None = None
        self.render()

    def render(self) -> None:
        """The filters and the list, asked for again."""
        if not self._facets():
            return
        self.answer, self.problem = None, None
        _clear(self.box)
        choices = cv.pve_choices(self.shared.facets, self.shared.mini)
        self.box.addWidget(self._filters(self.f, choices, False, self._changed, self._mini, self._cleared))
        holder = QWidget()
        holder.setObjectName("plain")
        self.content = QVBoxLayout(holder)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(8)
        self.box.addWidget(holder)
        self.redraw()
        self._ask("list", self.query())

    def redraw(self) -> None:
        """The list as last answered (or why not), under the filters as they are."""
        if self.content is None:
            return
        _clear(self.content)
        if self.problem is not None:
            self.content.addWidget(_note(self.problem))
        elif self.answer is None:
            self.content.addWidget(_empty(cb.LOADING))
        else:
            self.draw(self.answer)
            note = cv.source_note(self.answer)
            if note:
                self.content.addWidget(_label(note, "small"))

    def answered(self, kind: str, answer) -> None:
        self.answer = answer
        self.redraw()

    def refused(self, kind: str, why: str) -> None:
        self.problem = why
        self.redraw()

    def _changed(self, key: str, value: str) -> None:
        self.f[key] = value
        self.render()

    def refresh(self) -> None:
        self.render()

    def _mini(self, shown: bool) -> None:
        self.shared.show_mini(shown)
        if not self.shared.mini and cv.is_mini(self.f.get("boss"), _dict(self.shared.facets).get("boss_roles")):
            self.f["boss"] = ""                                  # a hidden boss cannot stay chosen
        self.render()

    def _cleared(self) -> None:
        self.f = {}
        self.render()

    def query(self) -> str:
        raise NotImplementedError

    def draw(self, answer) -> None:
        raise NotImplementedError


class RunSpeed(_Ranked):
    """Completed-run speed (``renderSpeed``): each run ranked among runs of the same instance, route, difficulty and
    party size."""

    def query(self) -> str:
        return "/api/v1/run-leaderboard?" + cv.filter_query(self.f, (("limit", "100"),))

    def draw(self, answer) -> None:
        rows = cv.speed_rows(answer)
        if not rows:
            filtered = any(self.f.get(key) for key in cv.PVE_KEYS)
            self.content.addWidget(_empty(cv.NO_SPEED_MATCH if filtered else cv.NO_SPEED))
            return
        cells = []
        for r in rows:
            rank = html.escape(r["rank"]) + (f" <span style='color: {theme.COLORS['muted']};'>{html.escape(r['of'])}</span>"
                                             if r["of"] else "")
            log = _button("view", lambda r=r: self._open(r["log"], "pve")) if _truthy(r["log"]) else ""
            cells.append([_label(rank, rich=True, wrap=False), r["route"], r["kind"], r["time"], r["party"], log])
        self.content.addWidget(GridTable(cv.SPEED_COLUMNS, cells, {1: 2, 2: 2, 3: 1, 4: 1}, left=True, right=(0, 3, 4)))


class BossProgression(_Ranked):
    """Boss progression (``renderProgression``): each boss's engagements by difficulty, region and product."""

    def query(self) -> str:
        query = cv.filter_query(self.f)
        return "/api/v1/encounter-progression" + (f"?{query}" if query else "")

    def draw(self, answer) -> None:
        rows = cv.progression_rows(answer, self.f, self.shared.mini, self.shared.facets)
        if not rows:
            self.content.addWidget(_empty(cv.NO_PROGRESSION))
            return
        cells = [[self._boss(r["boss"], r["icon"]), r["difficulty"], r["region"], _muted(r["patch"]), r["attempts"],
                  r["kills"], r["wipes"], r["rate"], r["fastest"]] for r in rows]
        self.content.addWidget(GridTable(cv.PROGRESSION_COLUMNS, cells, {0: 2, 1: 1, 2: 1, 3: 1}, left=True,
                                         right=(4, 5, 6, 7, 8)))


class BuildPoints(_View):
    """Highest observed build points (``renderPoints``): each class's highest reported points."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.answer = None
        self.render()

    def render(self) -> None:
        _clear(self.box)
        self.box.addWidget(_empty(cb.LOADING))
        self._ask("points", "/api/v1/progression")

    refresh = render

    def answered(self, kind: str, answer) -> None:
        self.answer = answer
        _clear(self.box)
        rows = cv.points_rows(answer)
        if not rows:
            self.box.addWidget(_empty(cv.NO_POINTS))
        else:
            self.box.addWidget(_label(cv.POINTS_NOTE, "small"))
            cells = [[r["class"], r["skill"], r["stigma"], r["daevanion"], r["ariel"], r["total"], _muted(r["region"])]
                     for r in rows]
            self.box.addWidget(GridTable(cv.POINTS_COLUMNS, cells, {0: 2, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}, left=True,
                                         right=(1, 2, 3, 4, 5)))
        note = cv.source_note(answer)
        if note:
            self.box.addWidget(_label(note, "small"))

    def refused(self, kind: str, why: str) -> None:
        _clear(self.box)
        self.box.addWidget(_note(why))
