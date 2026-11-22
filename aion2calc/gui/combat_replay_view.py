"""The movement replay's drawing and controls (combat-review.js ``replay``'s SVG and its buttons), in the native
interface since 0.2.468; its model is ``combat_replay``.

- **The arena** (``.cr-arena``): 320 px tall across the width, its 100 × 100 view in the middle (``xMidYMid meet``) on
  a faint ground. The boss room is behind the tokens, then each token's trail and the token. The tip of whatever is
  under the pointer shows, as the SVG's ``title`` does.
- **The controls**: Play and Pause, Rewind, the speed (kept), the time slider and its clock, and the arena's shape
  (kept). At 1× the replay plays the fight in real seconds, on a 16 ms timer in place of the web page's animation
  frames.
- Since 0.2.469 **the marks** between the arena and the tokens (the casts' rings, aims, facing wedges and measured
  areas; the appearances, deaths, revives and add hits), **the list of casts and events** beside the arena
  (``.cr-events``: its rows marked before, in or after the replay's time, followed as it plays, a row chosen going to
  its time; a model whose rows in view alone are drawn, so a long fight's thousands of rows cost little) and **the
  slider's ticks** at each of them.
"""
from __future__ import annotations

import math
import time
from bisect import bisect_left, bisect_right
from collections import OrderedDict

from PySide6.QtCore import (QAbstractListModel, QEvent, QLineF, QModelIndex, QPoint, QPointF, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import (QColor, QFont, QFontInfo, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QPen,
                           QPolygonF, QTextCharFormat, QTextLayout, QTextOption)
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QComboBox, QFrame, QLabel, QListView, QSlider, QStyle,
                               QStyledItemDelegate, QStyleOptionSlider, QToolTip, QVBoxLayout, QWidget)

from . import combat_replay as rp
from . import theme
from .chrome import FlowLayout
from .combat_saved import _button, _head, _label
from .combat import js_string

GROUND = QColor(136, 136, 136, 34)       # ``background: #8882``
TEXT = QColor(theme.COLORS["text"])      # ``currentColor``
HEIGHT = 320                             # ``.cr-arena { height: 320px }``
SCRUB_MOST = 500                         # ``[data-scrub] { width: min(50%, 500px) }``
GOLD_MARK = QColor("#f0c050")            # a cast's ring, aim and facing
GREEN_MARK = QColor("#9fd36f")           # an appearance
RED_MARK = QColor("#ef6262")             # an add's hit
AREA = QColor("#f06060")                 # a measured area
NARROW = 535                             # ``@media (max-width: 760px)``: the list under the arena once the replay is
                                         # narrower than in a 760 px window (534 px, the review zoomed 1.25)
EVENTS_LEAST, EVENTS_SHARE = 260, 0.34   # ``grid-template-columns: minmax(0, 1fr) minmax(260px, 34%)``
SMALL_PX = 12                            # the Combat Logs page's small text (``QLabel#small``)


def _with(colour: QColor | str, alpha: float) -> QColor:
    shade = QColor(colour)
    shade.setAlphaF(alpha)
    return shade


def _pen(colour: QColor, width: float, dashes: list[float] | None = None, round_ends: bool = False) -> QPen:
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.RoundCap if round_ends else Qt.FlatCap)     # SVG's butt ends and mitred corners, or round ones
    pen.setJoinStyle(Qt.RoundJoin if round_ends else Qt.MiterJoin)
    if dashes:
        pen.setDashPattern([d / width for d in dashes])           # ``stroke-dasharray`` in view units
    return pen


def _sector(x: float, y: float, outer: float, inner: float, start: float, sweep: float) -> QPainterPath:
    """A wedge from ``start`` degrees, counter-clockwise as an SVG arc with sweep-flag 0 is drawn: from the middle, or
    between two radii."""
    path = QPainterPath()
    if inner > 0:
        a0 = math.radians(start)
        path.moveTo(x + inner * math.cos(a0), y - inner * math.sin(a0))
        path.lineTo(x + outer * math.cos(a0), y - outer * math.sin(a0))
        path.arcTo(QRectF(x - outer, y - outer, 2 * outer, 2 * outer), start, sweep)
        a1 = math.radians(start + sweep)
        path.lineTo(x + inner * math.cos(a1), y - inner * math.sin(a1))
        path.arcTo(QRectF(x - inner, y - inner, 2 * inner, 2 * inner), start + sweep, -sweep)
    else:
        path.moveTo(x, y)
        path.arcTo(QRectF(x - outer, y - outer, 2 * outer, 2 * outer), start, sweep)
    path.closeSubpath()
    return path


def _circle(x: float, y: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(x, y), r, r)
    return path


def _polyline(points) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    return path


def mark_drawing(mark: dict) -> list[tuple[QPainterPath, QPen | None, QColor | None, float]]:
    """How a mark is drawn (the replay's SVG and its ``.cr-*`` styles): each part's path, pen, fill and opacity."""
    kind, a = mark["kind"], mark.get("alpha", 1.0)
    if kind == "castring":                                       # ``.cr-castring``
        return [(_circle(mark["x"], mark["y"], mark["r"]), _pen(_with(GOLD_MARK, a), 0.6), None, 1.0)]
    if kind == "face":                                           # ``.cr-face``
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(*point) for point in mark["points"]]))
        path.closeSubpath()
        return [(path, None, _with(GOLD_MARK, a), 1.0)]
    if kind == "aimline":                                        # ``.cr-aimline``
        return [(_polyline([(mark["x1"], mark["y1"]), (mark["x2"], mark["y2"])]),
                 _pen(_with(GOLD_MARK, a), 0.4, [1, 0.8]), None, 1.0)]
    if kind == "aim":                                            # ``.cr-aim``: fill a third as clear as its edge
        return [(_circle(mark["x"], mark["y"], mark["r"]), _pen(_with(GOLD_MARK, a), 0.5), _with(GOLD_MARK, 0.35 * a), 1.0)]
    if kind == "spawn":                                          # ``.cr-spawn``
        return [(_circle(mark["x"], mark["y"], mark["r"]), _pen(_with(GREEN_MARK, a), 0.6, [1.2, 0.8]), None, 1.0)]
    if kind == "revive":                                         # ``.cr-revive``
        return [(_circle(mark["x"], mark["y"], mark["r"]), _pen(_with(TEXT, a), 0.5, [1, 0.6]), None, 1.0)]
    if kind == "hit":                                            # ``.cr-hit``: a fading ring, and a dot whose edge stays
        return [(_circle(mark["x"], mark["y"], mark["r"]), _pen(_with(RED_MARK, a), 0.6), None, 1.0),
                (_circle(mark["x"], mark["y"], 1.1), _pen(RED_MARK, 0.6), _with(RED_MARK, a), 1.0)]
    if kind == "death":                                          # ``.cr-death``: drawn as text, see ``_death``
        return []
    shape, opacity = mark.get("shape"), mark.get("opacity", 1.0)
    edge, fill = _pen(_with(AREA, 0.9), 0.5), _with(AREA, 0.22)  # ``.cr-aoe``
    if shape == "circle":
        return [(_circle(mark["x"], mark["y"], mark["r"]), edge, fill, opacity)]
    if shape == "ring":                                          # ``.cr-aoe-ring``: its band, a third as clear
        return [(_circle(mark["x"], mark["y"], mark["r"]), _pen(_with(AREA, 0.3), mark["width"]), None, opacity)]
    if shape == "cone":
        return [(_sector(mark["x"], mark["y"], mark["r"], 0, mark["from"], mark["sweep"]), edge, fill, opacity)]
    if shape == "polygon":
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(*point) for point in mark["points"]]))
        path.closeSubpath()
        return [(path, edge, fill, opacity)]
    if shape == "wedges":
        return [(_sector(mark["x"], mark["y"], mark["r"], mark["inner"], w["from"], w["sweep"]), edge, fill, opacity)
                for w in mark["wedges"]]
    if shape == "path":                                          # ``.cr-aoe-band`` under ``.cr-aoe-way``
        line = _polyline(mark["points"])
        return [(line, _pen(_with(AREA, 0.3), mark["width"], round_ends=True), None, opacity),
                (line, _pen(_with(AREA, 0.9), 0.4, [1.2, 0.8], round_ends=True), None, opacity)]
    return []


class Arena(QWidget):
    """The replay's arena (``.cr-arena``): the room, the marks and the tokens at the moment shown."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.tokens: list[dict] = []
        self.marks: list[dict] = []
        self.room: dict | None = None             # the arena drawn: its shape, and its middle and radius in view units
        self.setFixedHeight(HEIGHT)
        self.setAccessibleName("Recorded positions")

    def sizeHint(self) -> QSize:
        return QSize(HEIGHT, HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, HEIGHT)

    def view(self) -> tuple[float, float, float]:
        """Where the 100-unit view sits (``preserveAspectRatio="xMidYMid meet"``): its left, its top, and a unit's
        pixels."""
        unit = min(self.width(), self.height()) / 100
        return (self.width() - 100 * unit) / 2, (self.height() - 100 * unit) / 2, unit

    def show_moment(self, tokens: list[dict], room: dict | None, marks: list[dict] | None = None) -> None:
        self.tokens, self.room = tokens, room
        if marks is not None:
            self.marks = marks
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), GROUND)
        left, top, unit = self.view()
        painter.translate(left, top)
        painter.scale(unit, unit)
        a = self.room
        if a is not None:                                            # ``.cr-room``
            painter.setPen(self._pen(_with(TEXT, 0.6), 0.6))
            painter.setBrush(_with(TEXT, 0.06))
            if a["shape"] == "circle":
                painter.drawEllipse(QPointF(a["x"], a["y"]), a["r"], a["r"])
            else:
                painter.drawRect(QRectF(a["x"] - a["r"], a["y"] - a["r"], 2 * a["r"], 2 * a["r"]))
        for mark in self.marks:                                      # ``data-marks``, under the tokens
            if mark["kind"] == "death":
                self._death(painter, mark)
                continue
            for path, pen, fill, opacity in mark_drawing(mark):
                painter.setOpacity(opacity)
                painter.setPen(pen if pen is not None else Qt.NoPen)
                painter.setBrush(fill if fill is not None else Qt.NoBrush)
                painter.drawPath(path)
            painter.setOpacity(1.0)
        for token in self.tokens:
            if token["trail"]:
                painter.setPen(self._pen(_with(token["colour"], 0.35), 0.6))
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in token["trail"]]))
            if token["ring"]:                                        # the recording player: a white dashed edge
                pen = self._pen(QColor("#ffffff"), 0.5)
                pen.setDashPattern([2, 2])                           # ``stroke-dasharray="1 1"`` in pen widths
                painter.setPen(pen)
            else:
                painter.setPen(Qt.NoPen)
            painter.setBrush(_with(token["colour"], token["opacity"]))
            painter.drawEllipse(QPointF(token["x"], token["y"]), token["radius"], token["radius"])
        painter.end()

    @staticmethod
    def _pen(colour: QColor, width: float) -> QPen:
        return _pen(colour, width)

    @staticmethod
    def _death(painter: QPainter, mark: dict) -> None:
        """A ✕ where a player fell (``.cr-death``): bold, in the text's colour, over a faint grey edge."""
        font = QFont(painter.font())
        font.setBold(True)
        font.setPixelSize(62)                                    # ``font-size: 6.2`` in view units, drawn a tenth as large
        path = QPainterPath()
        path.addText(0, 0, font, "✕")
        box = path.boundingRect()
        painter.save()
        painter.translate(mark["x"], mark["y"])
        painter.scale(0.1, 0.1)
        painter.translate(-box.center().x(), 0)                  # ``text-anchor: middle`` on the baseline
        painter.setPen(_pen(QColor(136, 136, 136, 102), 5))      # ``stroke: #8886; stroke-width: .5``, under the fill
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(TEXT)
        painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _mark_hit(mark: dict, vx: float, vy: float) -> bool:
        """Whether a point of the view is on a mark as the SVG's pointer finds it: a filled shape anywhere inside, an
        unfilled one on its line."""
        if mark["kind"] == "death":
            return abs(vx - mark["x"]) <= 2.2 and -4.4 <= vy - mark["y"] <= 0.6
        for path, pen, fill, _opacity in mark_drawing(mark):
            if fill is not None and path.contains(QPointF(vx, vy)):
                return True
            if pen is not None:
                stroker = QPainterPathStroker()
                stroker.setWidth(max(pen.widthF(), 0.4))
                if stroker.createStroke(path).contains(QPointF(vx, vy)):
                    return True
        return False

    def tip_at(self, x: float, y: float) -> str:
        """The tip under a point of the widget: the topmost token's, else the arena's."""
        left, top, unit = self.view()
        vx, vy = (x - left) / unit, (y - top) / unit
        for token in reversed(self.tokens):
            if math.hypot(vx - token["x"], vy - token["y"]) <= token["radius"] + (0.25 if token["ring"] else 0):
                return token["tip"]
        for mark in reversed(self.marks):
            if mark.get("tip") and self._mark_hit(mark, vx, vy):
                return mark["tip"]
        a = self.room
        if a is not None:
            edge = a["r"] + 0.3                                      # the edge's half width
            inside = (math.hypot(vx - a["x"], vy - a["y"]) <= edge if a["shape"] == "circle"
                      else abs(vx - a["x"]) <= edge and abs(vy - a["y"]) <= edge)
            if inside:
                return rp.ARENA_TIP
        return ""

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            tip = self.tip_at(event.pos().x(), event.pos().y())
            if tip:
                QToolTip.showText(event.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


# ``.cr-ev.is-now button`` gold, an appearance's green (``.cr-ev-spawn.is-now``). The stylesheet's red for a death's and
# a hit's rows comes before the gold rule, of the same weight, so the web page draws them gold too.
NOW_EDGES = {"spawn": GREEN_MARK}
HOVER = QColor(136, 136, 136, 34)        # ``.cr-ev button:hover { background: #8882 }``
STATE_ROLE = Qt.UserRole + 1             # a row's state at the replay's time: "next", "now" or "past"


def row_runs(e: dict) -> list[tuple[str, bool, bool]]:
    """A row's words (``.cr-ev-text``) as runs of text, each bold or not and muted or not: who, then what they cast,
    whom they hit or what happened to them, how many times, where and the measured area."""
    runs = [(e["who"], False, False)]
    if e["kind"] == "cast":
        runs += [(": ", False, False), (e["what"], True, False)]
    elif e["kind"] == "hit":
        runs.append((f" hit {e['where']}", False, False))
        if e["what"]:
            runs += [(" ", False, False), ("· ", False, True), (e["what"], True, True)]
    if e["n"] > 1:
        runs += [(" ", False, False), (f"×{e['n']}", True, False)]
    if e["kind"] == "spawn":
        runs += [(" ", False, False), ("appeared", False, True)]
    elif e["kind"] in ("death", "revive"):
        runs += [(" ", False, False), ("died" if e["kind"] == "death" else "revived", True, False)]
    if e["where"] and e["kind"] != "hit":
        runs += [(" ", False, False), (e["where"], False, True)]
    if e["area"]:
        runs += [(" ", False, False), (f"· {e['area']}", False, True)]
    return runs


def _units(text: str) -> int:
    """A text's length as Qt counts it (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


class EventModel(QAbstractListModel):
    """The list's rows (``listEvents``): each cast's and event's words, as read out with its time, and its state at
    the replay's time."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.events: list[dict] = []
        self.runs: list[list] = []
        self.words: list[str] = []
        self.states: list[str] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.events)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.events):
            return None
        if role in (Qt.DisplayRole, Qt.AccessibleTextRole):
            return self.words[index.row()]
        if role == STATE_ROLE:
            return self.states[index.row()]
        return None

    def show(self, events: list[dict]) -> None:
        """New rows, each to come."""
        self.beginResetModel()
        self.events = events
        self.runs = [row_runs(e) for e in events]
        self.words = [f"{rp.fixed(e['t'], 1)}s " + "".join(text for text, _bold, _muted in runs)
                      for e, runs in zip(events, self.runs)]
        self.states = ["next"] * len(events)
        self.endResetModel()

    def set_states(self, first: int, states: list[str]) -> list[int]:
        """The states of the rows from ``first`` on, and which rows changed. (The view draws those again itself: a
        ``dataChanged`` would have it lay every row out again.)"""
        changed = [i for i, state in enumerate(states, first) if self.states[i] != state]
        self.states[first:first + len(states)] = states
        return changed


class EventDelegate(QStyledItemDelegate):
    """A row drawn (``.cr-ev``): its time and words inside a 3 px edge; its ground and edge marked while it is in
    progress, its ground while the pointer is over it, and the row dimmed while it is to come. Each row's height is
    kept for the list's width; only the rows drawn last keep their words set out."""

    KEPT = 256

    def __init__(self, view: QListView):
        super().__init__(view)
        self.view = view
        self.times: dict = {}                    # row: its time and how wide it is drawn
        self.heights: dict = {}                  # row: the width its words were wrapped to, and their height
        self.kept: OrderedDict = OrderedDict()   # the rows drawn last: their words set out, wrapped to a width

    def forget(self) -> None:
        self.times.clear()
        self.heights.clear()
        self.kept.clear()

    def _time(self, row: int) -> tuple[str, int]:
        found = self.times.get(row)
        if found is None:
            font, time = self.view.font(), f"{rp.fixed(self.view.model().events[row]['t'], 1)}s"
            # ``.cr-ev time { min-width: 4.2em }``
            found = self.times[row] = time, max(math.ceil(4.2 * QFontInfo(font).pixelSize()),
                                                math.ceil(QFontMetricsF(font).horizontalAdvance(time)))
        return found

    def _words_width(self, row: int, width: int) -> int:
        """What a row as wide as the list leaves its words: ``padding: 4px 10px`` inside the edge, its time, 10 px."""
        return max(20, width - (3 + 10 + self._time(row)[1] + 10) - 10)

    def _words(self, row: int, width: int) -> list:
        """A row's words set out and wrapped to ``width``, and their height."""
        kept = self.kept.get(row)
        if kept is None:
            runs = self.view.model().runs[row]
            layout = QTextLayout("".join(text for text, _bold, _muted in runs), self.view.font())
            ranges, at = [], 0
            for text, bold, muted in runs:
                if bold or muted:
                    shape = QTextCharFormat()
                    if bold:
                        shape.setFontWeight(QFont.Bold)
                    if muted:
                        shape.setForeground(QColor(theme.COLORS["muted"]))
                    part = QTextLayout.FormatRange()
                    part.start, part.length, part.format = at, _units(text), shape
                    ranges.append(part)
                at += _units(text)
            layout.setFormats(ranges)
            option = QTextOption()
            option.setWrapMode(QTextOption.WordWrap)
            layout.setTextOption(option)
            kept = [layout, None, 0.0]
        if kept[1] != width:
            layout, height = kept[0], 0.0
            layout.beginLayout()
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                line.setPosition(QPointF(0, height))
                height += line.height()
            layout.endLayout()
            kept[1], kept[2] = width, height
        self.kept[row] = kept
        self.kept.move_to_end(row)
        if len(self.kept) > self.KEPT:
            self.kept.popitem(last=False)
        return kept

    def sizeHint(self, option, index) -> QSize:
        width = self.view.viewport().width()
        row = index.row()
        words_width = self._words_width(row, width)
        found = self.heights.get(row)
        if found is None or found[0] != words_width:
            found = self.heights[row] = words_width, self._words(row, words_width)[2]
        return QSize(width, math.ceil(max(QFontMetricsF(self.view.font()).height(), found[1])) + 8)

    def paint(self, painter: QPainter, option, index) -> None:
        model = self.view.model()
        row = index.row()
        e, state = model.events[row], model.states[row]
        rect = QRectF(option.rect)
        painter.save()
        if state == "next":                                          # ``.cr-ev.is-next { opacity: .55 }``
            painter.setOpacity(0.55)
        if state == "now":                                           # ``.cr-ev.is-now button``
            edge = NOW_EDGES.get(e["kind"], GOLD_MARK)
            painter.fillRect(rect, _with(edge, 38 / 255))
            painter.fillRect(QRectF(rect.x(), rect.y(), 3, rect.height()), edge)
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(rect, HOVER)
        if option.state & QStyle.State_HasFocus and self.view.hasFocus():   # the button's focus ring
            painter.setPen(QPen(_with(GOLD_MARK, 0.8), 1))
            painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        time, time_width = self._time(row)
        layout = self._words(row, self._words_width(row, option.rect.width()))[0]
        font = self.view.font()
        painter.setFont(font)
        painter.setPen(_with(TEXT, 0.75))                            # ``.cr-ev time { opacity: .75 }``
        painter.drawText(QPointF(rect.x() + 13, rect.y() + 4 + QFontMetricsF(font).ascent()), time)
        painter.setPen(TEXT)
        layout.draw(painter, QPointF(rect.x() + 13 + time_width + 10, rect.y() + 4))
        painter.restore()


class EventView(QListView):
    """The rows in a box of their own size that scrolls (``.cr-events ol``). A row chosen with the pointer, or with
    Enter or Space, sends the replay to its time."""

    seek = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("crEventsList")
        self.setAccessibleName("Boss casts and events")
        self.setModel(EventModel(self))
        self.delegate = EventDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setResizeMode(QListView.Adjust)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFrameShape(QFrame.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover)
        self.viewport().setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._chosen)

    def _chosen(self, index) -> None:
        if index.isValid():
            self.seek.emit(float(self.model().events[index.row()]["t"]))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and self.currentIndex().isValid():
            self._chosen(self.currentIndex())
            return
        super().keyPressEvent(event)


class EventList(QFrame):
    """The casts and events beside the arena (``.cr-events``): its head, then its rows, following the replay: each
    marked before, in or after its time, and the row reached brought into view a third of the way down. Only the rows
    near the replay's time are looked at as it plays: those before are past, those after to come."""

    seek = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("crEvents")
        self.setFixedHeight(HEIGHT)
        self.setStyleSheet("""
            QFrame#crEvents { border: 1px solid rgba(136, 136, 136, 68); border-radius: 8px;
                               background: rgba(136, 136, 136, 17); }
            QLabel#crEventsHead { padding: 6px 10px; border: none; border-bottom: 1px solid rgba(136, 136, 136, 68);
                                   background: transparent; }
            QListView#crEventsList { background: transparent; border: none; padding: 2px 0; }
        """)
        column = QVBoxLayout(self)
        column.setContentsMargins(1, 1, 1, 1)
        column.setSpacing(0)
        head = QLabel(f"<b>{rp.EVENTS_HEAD}</b><span style=\"color:{theme.COLORS['muted']}; font-size:{SMALL_PX}px\">"
                      f"{rp.EVENTS_HINT}</span>")                # ``<span class="small muted">``
        head.setObjectName("crEventsHead")
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)
        column.addWidget(head)
        self.view = EventView()
        self.view.seek.connect(self.seek)
        column.addWidget(self.view, 1)
        self.none = QLabel(rp.NO_EVENTS)                         # ``.cr-ev-none``
        self.none.setObjectName("small")
        self.none.setContentsMargins(10, 8, 10, 8)
        self.none.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.none.hide()
        column.addWidget(self.none, 1)
        self.times: list[float] = []
        self.span = 0.0                          # the longest a row stays in progress after its first time
        self.past = 0                            # the rows before this are past; those after ``coming`` are to come
        self.coming = -1
        self.reached = -2

    @property
    def model(self) -> EventModel:
        return self.view.model()

    def show_events(self, events: list[dict]) -> None:
        """The rows (``listEvents``), each to come, the list scrolled to its top."""
        self.view.delegate.forget()
        self.model.show(events)
        self.view.setVisible(bool(events))
        self.none.setVisible(not events)
        self.times = [e["t"] for e in events]
        self.span = max((e["last"] - e["t"] + e["show"] for e in events), default=0.0)
        self.past, self.coming, self.reached = 0, -1, -2
        self.view.verticalScrollBar().setValue(0)

    def _shown(self, first: int, last: int) -> bool:
        """Whether any of the rows from ``first`` to ``last`` is in view."""
        port = self.view.viewport()
        top, bottom = self.view.indexAt(QPoint(1, 1)), self.view.indexAt(QPoint(1, port.height() - 2))
        lowest = top.row() if top.isValid() else 0
        highest = bottom.row() if bottom.isValid() else self.model.rowCount() - 1
        return first <= highest and last >= lowest

    def mark(self, t: float) -> None:
        """Each row before, in or after the replay's time (``markEvents``); when another row is reached it is brought
        into view."""
        events = self.model.events
        if not events:
            return
        reached = bisect_right(self.times, t) - 1
        past = bisect_left(self.times, t - self.span - 1e-6)        # these and the rows before have gone by
        first, last = min(past, self.past), max(reached, self.coming)
        if first <= last:
            changed = self.model.set_states(first, [rp.Replay.event_state(events[i], t) for i in range(first, last + 1)])
            if changed and self._shown(changed[0], changed[-1]):     # the rows in view drawn again
                self.view.viewport().update()
        self.past, self.coming = past, reached
        if reached == self.reached:
            return
        self.reached = reached
        bar = self.view.verticalScrollBar()
        if reached < 0:
            bar.setValue(0)
            return
        rect, height = self.view.visualRect(self.model.index(reached)), self.view.viewport().height()
        if rect.top() < 0 or rect.bottom() + 1 > height:
            bar.setValue(max(0, int(bar.value() + rect.top() - height / 3)))


class TickedSlider(QSlider):
    """The time slider with a tick under it at each cast and event (``list="cr-ticks"``): where each falls is worked
    out once for the slider's size, one tick to a pixel."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(Qt.Horizontal, parent)
        self.ticks: list[int] = []
        self._drawn: tuple | None = None
        self._lines: list[QLineF] = []

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.ticks or self.maximum() <= self.minimum():
            return
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
        key = (groove.x(), groove.width(), handle.width(), self.height(), self.minimum(), self.maximum(), id(self.ticks),
               len(self.ticks))
        if key != self._drawn:
            span, bottom = max(1, groove.width() - handle.width()), self.height() - 1
            places = {QStyle.sliderPositionFromValue(self.minimum(), self.maximum(), value, span) for value in self.ticks}
            left = groove.x() + handle.width() / 2
            self._lines = [QLineF(left + x, bottom - 3, left + x, bottom) for x in sorted(places)]
            self._drawn = key
        painter = QPainter(self)
        painter.setPen(QPen(_with(TEXT, 0.6), 1))
        painter.drawLines(self._lines)
        painter.end()


class ReplayPanel(QWidget):
    """The replay with its controls (``replay``'s box): its heading and note, Play and Rewind, the speed, the time
    slider and its clock, the arena's shape, and the arena. ``store`` keeps the speed and the shape for every log."""

    def __init__(self, replay: rp.Replay, store, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.replay, self.store = replay, store
        self.clock = 0.0                          # the replay's own time: the slider's tenths would swallow a frame's ms
        self.speed = rp.replay_speed(store.value(rp.SPEED_KEY))
        self.shape = rp.room_shape(store.value(rp.ROOM_KEY))
        self.now = time.monotonic
        self.last = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(_head(rp.HEAD))
        if replay.note:
            column.addWidget(_label(replay.note, "small"))
        controls = QWidget()
        controls.setObjectName("plain")
        flow = FlowLayout(controls, align=Qt.AlignLeft, gap=(8, 6))
        self.play = _button("Play", self.toggle)
        flow.addWidget(self.play)
        flow.addWidget(_button("Rewind", self.rewind))
        speed = QComboBox()
        speed.setAccessibleName("Playback speed")
        for value in rp.SPEEDS:
            speed.addItem(rp.speed_words(value), value)
        speed.setCurrentIndex(rp.SPEEDS.index(self.speed))
        speed.activated.connect(lambda _index: self._speed_chosen(speed.currentData()))
        flow.addWidget(self._named("Speed", speed))
        self.scrub = TickedSlider()
        self.scrub.setAccessibleName("Replay time")
        self.scrub.setRange(0, max(0, math.floor(replay.duration * 10 + 1e-9)))   # tenths of a second (``step="0.1"``)
        if replay.ticked:
            self.scrub.ticks = [rp._js_round(t * 10) for t in replay.ticks()]
        self.scrub.valueChanged.connect(self._scrubbed)
        flow.addWidget(self.scrub)
        self.clock_label = QLabel()
        flow.addWidget(self.clock_label)
        if replay.rooms is not None:
            shape = QComboBox()
            shape.setAccessibleName("Arena")
            for value, words in rp.SHAPES:
                shape.addItem(words, value)
            shape.setCurrentIndex(0 if self.shape == "circle" else 1)
            shape.activated.connect(lambda _index: self._shape_chosen(shape.currentData()))
            flow.addWidget(self._named("Arena", shape))
        column.addWidget(controls)
        body = QWidget()
        body.setObjectName("plain")
        self.body = QBoxLayout(QBoxLayout.LeftToRight, body)     # ``.cr-replay-body``: the list beside the arena
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        self.arena = Arena()
        self.body.addWidget(self.arena, 1)
        self.events: EventList | None = None
        if replay.ticked:
            self.events = EventList()
            self.events.seek.connect(self.seek)
            self.events.show_events(replay.event_rows())
            self.body.addWidget(self.events)
        column.addWidget(body)
        self.draw(0.0)

    @staticmethod
    def _named(words: str, field: QWidget) -> QWidget:
        """A choice with its name before it (``<label>Speed <select>``)."""
        box = QWidget()
        box.setObjectName("plain")
        line = FlowLayout(box, align=Qt.AlignLeft, gap=(6, 0))
        line.addWidget(_label(words, wrap=False))
        line.addWidget(field)
        return box

    def resizeEvent(self, event) -> None:
        self.scrub.setFixedWidth(max(60, min(self.width() // 2, SCRUB_MOST)))
        if self.events is not None:                              # under 760 px the list goes under the arena, 220 px tall
            narrow = self.width() < NARROW
            self.body.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
            if narrow:
                self.events.setMinimumWidth(0)
                self.events.setMaximumWidth(16777215)
                self.events.setFixedHeight(220)
            else:
                self.events.setFixedWidth(max(EVENTS_LEAST, int(self.width() * EVENTS_SHARE)))
                self.events.setFixedHeight(HEIGHT)
        super().resizeEvent(event)

    def room(self) -> dict | None:
        """The arena drawn: the room in the shape chosen (``drawRoom``)."""
        rooms = self.replay.rooms
        return {**rooms[self.shape], "shape": self.shape} if rooms is not None else None

    def draw(self, t: float) -> None:
        """The moment ``t`` (``draw``): the slider, the clock and the arena."""
        self.clock = t
        self.scrub.blockSignals(True)
        self.scrub.setValue(min(rp._js_round(t * 10), self.scrub.maximum()))
        self.scrub.blockSignals(False)
        self.clock_label.setText(f"{theme.fixed(t, 1)}s")
        self.arena.show_moment(self.replay.frame(t), self.room(), self.replay.marks(t))
        if self.events is not None:
            self.events.mark(t)

    def playing(self) -> bool:
        return self.timer.isActive()

    def toggle(self) -> None:
        """Play, or Pause while playing (``data-play``)."""
        if self.timer.isActive():
            self.pause()
            return
        self.last = self.now()
        self.play.setText("Pause")
        self.timer.start()

    def _tick(self) -> None:
        now = self.now()
        t = min(self.replay.duration, self.clock + max(0.0, now - self.last) * self.speed)
        self.last = now
        self.draw(t)
        if t >= self.replay.duration:
            self.pause()

    def pause(self) -> None:
        self.timer.stop()
        self.play.setText("Play")

    def rewind(self) -> None:
        """Back to the fight's start (``data-rewind``)."""
        self.pause()
        self.draw(0.0)

    def seek(self, t: float) -> None:
        """A row of the list chosen (``data-seek``): the replay paused at its time."""
        self.pause()
        self.draw(min(self.replay.duration, t))

    def set_shapes(self, shapes: dict | None) -> None:
        """The measured areas come (``aoeRedraw``): the list and the moment drawn again with them."""
        self.replay.shapes = shapes
        if self.events is not None:
            self.events.show_events(self.replay.event_rows())
        self.draw(self.clock)

    def _scrubbed(self, value: int) -> None:
        """A time chosen on the slider (``data-scrub``)."""
        self.pause()
        self.draw(value / 10)

    def _speed_chosen(self, value) -> None:
        """The playback speed (``data-speed``): kept for every log."""
        self.speed = value or 1
        self.store.setValue(rp.SPEED_KEY, js_string(self.speed))

    def _shape_chosen(self, value) -> None:
        """The arena's shape (``data-room-shape``): kept for every log."""
        self.shape = rp.room_shape(value)
        self.store.setValue(rp.ROOM_KEY, self.shape)
        self.arena.show_moment(self.arena.tokens, self.room(), self.arena.marks)

    def stop(self) -> None:
        """Playing stopped (the web page's ``cancelAnimationFrame`` as it draws the review again)."""
        self.timer.stop()
