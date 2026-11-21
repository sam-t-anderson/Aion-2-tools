"""The log review's Events and Timeline views (0.2.459), as combat-review.js draws them.

- **A column's filter of the events** (``.cr-ef-pop``): the column's values, each with how many events have it, ticked
  to keep; a search finds values, and **All**, **None** and **Only the found** keep them at once. It opens under its
  button and closes on a click elsewhere, as a menu does (the web page's stays open until its button is pressed
  again).
- **The recorded effect timeline** (``.cr-timeline``): the window's ruler over a lane per player. Each lane's name stays
  at the left and the ruler at the top as the lanes scroll under them (the web page's ``position: sticky``). Its
  markers are drawn as the web page's SVG draws them, and an effect is inspected by the pointer, a click, or the arrow
  keys once the lanes have the focus (left and right along a lane, up and down to the lanes beside it).
- Since 0.2.460 **the cast timeline** (``castTimeline``) in the same box: its geometry is the model's (``ruler``,
  ``lane``, ``bottom``, ``corner``, ``empty``), and a press is drawn as its skill's small tile with its cast time's line.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QStyle,
                               QToolTip, QVBoxLayout, QWidget)

from . import combat_review as cw
from . import theme

C = theme.COLORS
NAME_WIDTH = 180                        # a lane's name (``grid-template-columns: 180px …``)
RULER = 35                              # the ruler's 34 px and its line
LANE = 85                               # a lane's 84 px and its line
FOLDED = 47                             # a collapsed lane: its controls' 36 px and their padding, and its line
MOST = 650                              # ``max-height: 650px``
SHADE = QColor(136, 136, 136, 17)       # ``#8881``: every other lane
RULE = QColor(136, 136, 136, 68)        # ``#8884``: the line under a lane
EDGE = QColor(136, 136, 136, 85)        # ``#8885``: the box's edge and the names' edge


# ---------------------------------------------------------------- a column's filter
class FilterPopup(QFrame):
    """A column's filter of the events (``.cr-ef-pop``). ``kept`` says the values to keep (None: all of them),
    ``searched`` what the search holds, ``closed`` that it closed."""

    kept = Signal(str, object)
    searched = Signal(str, str)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("efPop")
        self.setFixedWidth(340)
        self.key = ""
        self.values: list[dict] = []
        self.ticks: list[QCheckBox] = []
        self.rows: list[QWidget] = []
        self.anchor = lambda: None              # the column's button as the page draws it now
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._searched)
        layout.addWidget(self.search)
        row = QWidget()
        row.setObjectName("plain")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        for words, action, tip in (("All", self.keep_all, ""), ("None", self.keep_none, ""),
                                   ("Only the found", self.keep_found, "Keep only the values the search finds")):
            button = QPushButton(words)
            button.setObjectName("small")
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, action=action: action())
            line.addWidget(button)
        line.addStretch(1)
        layout.addWidget(row)
        self.area = QScrollArea()
        self.area.setObjectName("plain")
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.area.setMaximumHeight(280)
        layout.addWidget(self.area)
        self.setStyleSheet(f"QFrame#efPop {{ background: {C['panel']}; border: 1px solid {C['line2']}; border-radius: 8px; }}")

    def open(self, column: dict, search: str, anchor) -> None:
        """The column's values listed, ticked as kept, found by the search as it was left, under its button."""
        self.key, self.values, self.anchor = column["key"], column["values"], anchor
        self.search.setAccessibleName(f"Find a value of {column['name']}")
        self.search.blockSignals(True)
        self.search.setText(search)
        self.search.blockSignals(False)
        chosen = column["chosen"]
        box = QWidget()
        box.setObjectName("plain")
        lines = QVBoxLayout(box)
        lines.setContentsMargins(0, 0, 0, 0)
        lines.setSpacing(2)
        self.ticks, self.rows = [], []
        for value in self.values:
            row = QWidget()
            row.setObjectName("plain")
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 4, 0)
            line.setSpacing(6)
            tick = QCheckBox(value["name"])
            tick.setChecked(chosen is None or value["value"] in chosen)
            tick.toggled.connect(lambda _on: self._ticked())
            line.addWidget(tick, 1)
            count = QLabel(cw.number(value["count"]))
            count.setObjectName("small")
            count.setStyleSheet(f"color: {C['muted']};")
            line.addWidget(count)
            lines.addWidget(row)
            self.ticks.append(tick)
            self.rows.append(row)
        if not self.values:
            none = QLabel("No values.")
            none.setObjectName("small")
            lines.addWidget(none)
        lines.addStretch(1)
        old = self.area.takeWidget()
        if old is not None:
            old.deleteLater()
        self.area.setWidget(box)
        self._find(search)
        self.place()
        self.show()
        self.search.setFocus()

    def place(self, anchor: QWidget | None = None) -> None:
        """Under its button, kept on the button's screen; above the button when there is no room below."""
        anchor = anchor or self.anchor()
        if anchor is None or not anchor.isVisible():
            return
        self.adjustSize()
        where = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = anchor.screen().availableGeometry() if anchor.screen() is not None else None
        if screen is not None:
            if where.y() + self.height() > screen.bottom():
                where.setY(max(screen.top(), anchor.mapToGlobal(QPoint(0, 0)).y() - 4 - self.height()))
            where.setX(max(screen.left(), min(where.x(), screen.right() - self.width())))
        self.move(where)

    # the values kept
    def chosen(self) -> list | None:
        kept = [value["value"] for value, tick in zip(self.values, self.ticks) if tick.isChecked()]
        return None if len(kept) == len(self.values) else kept         # every value: no filter (``undefined``)

    def _ticked(self) -> None:
        self.kept.emit(self.key, self.chosen())

    def _keep(self, keep) -> None:
        for value, tick in zip(self.values, self.ticks):
            tick.blockSignals(True)
            tick.setChecked(keep(value))
            tick.blockSignals(False)
        self._ticked()

    def keep_all(self) -> None:
        self._keep(lambda _value: True)

    def keep_none(self) -> None:
        self._keep(lambda _value: False)

    def keep_found(self) -> None:
        """Only the values the search finds (``data-ef-found``), whether they were ticked or not."""
        found = {id(value) for value, row in zip(self.values, self.rows) if not row.isHidden()}
        self._keep(lambda value: id(value) in found)

    # the search
    def _searched(self, text: str) -> None:
        self.searched.emit(self.key, text)
        self._find(text)

    def _find(self, text: str) -> None:
        q = text.strip().lower()
        for value, row in zip(self.values, self.rows):
            row.setHidden(bool(q) and q not in value["name"].lower())

    # opening and closing
    def showEvent(self, event) -> None:
        self.setAttribute(Qt.WA_NoMouseReplay, False)
        super().showEvent(event)

    def mousePressEvent(self, event) -> None:
        """A press outside closes it, as a menu's does; on its own button it only closes it (a menu's button's press
        is not given again to the button, which would open it again)."""
        if not self.rect().contains(event.position().toPoint()):
            anchor = self.anchor()
            if anchor is not None and anchor.isVisible() and anchor.rect().contains(
                    anchor.mapFromGlobal(event.globalPosition().toPoint())):
                self.setAttribute(Qt.WA_NoMouseReplay)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.closed.emit()


class Placer(QObject):
    """Keeps an open filter under its button as the page is drawn again and its button moves."""

    def __init__(self, popup: FilterPopup, parent: QObject | None = None):
        super().__init__(parent)
        self.popup = popup

    def eventFilter(self, watched, event) -> bool:
        if (event.type() in (QEvent.Move, QEvent.Resize, QEvent.Show) and self.popup.isVisible()
                and watched is self.popup.anchor()):
            self.popup.place(watched)
        return False


# ---------------------------------------------------------------- the abilities as bars (0.2.460)
class ContributionBars(QWidget):
    """The abilities as bars (``.cr-bars``): each row its player's and ability's name, its bar against the largest in the
    player's class colour, and its amount; both on hover. The columns share the width as ``minmax(6em, 2fr)
    minmax(3em, 3fr) auto`` do, ten pixels apart."""

    ROW, GAP = 22, 4

    def __init__(self, bars: list[dict], colour_of, parent: QWidget | None = None):
        super().__init__(parent)
        self.bars, self.colour_of = bars, colour_of
        self.setAccessibleName("Amount by player and ability")
        self.setFixedHeight(max(0, len(bars) * (self.ROW + self.GAP) - self.GAP))

    def sizeHint(self) -> QSize:
        return QSize(600, self.height())

    def _columns(self) -> tuple[float, float, float]:
        from PySide6.QtGui import QFontInfo
        em = QFontInfo(self.font()).pixelSize() or 13
        metrics = self.fontMetrics()
        value = max([5.5 * em] + [metrics.horizontalAdvance(b["value"]) for b in self.bars])
        room = max(0.0, self.width() - value - 20)
        name = max(6 * em, room * 2 / 5)
        return name, max(3 * em, room - name), value

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        name_w, track_w, value_w = self._columns()
        metrics = self.fontMetrics()
        ink = QColor(C["text"])
        track_colour = QColor(136, 136, 136, 34)                   # ``#8882``
        edge = QColor(0, 0, 0, 71)                                 # ``inset 0 0 0 1px rgba(0,0,0,.28)``
        for i, bar in enumerate(self.bars):
            y = i * (self.ROW + self.GAP)
            painter.setPen(ink)
            painter.drawText(QRectF(0, y, name_w, self.ROW), Qt.AlignLeft | Qt.AlignVCenter,
                             metrics.elidedText(bar["name"], Qt.ElideRight, int(name_w)))
            track = QRectF(name_w + 10, y + (self.ROW - 18) / 2, track_w, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(track_colour)
            painter.drawRoundedRect(track, 3, 3)
            fill = QRectF(track.left(), track.top(), max(2.0, track_w * bar["share"] / 100), 18)
            painter.setBrush(QColor(self.colour_of(bar["actor"])))
            painter.setPen(QPen(edge, 1))
            painter.drawRoundedRect(fill.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(ink)
            painter.drawText(QRectF(name_w + 20 + track_w, y, value_w, self.ROW), Qt.AlignRight | Qt.AlignVCenter, bar["value"])
        painter.end()

    def row_at(self, y: float) -> int | None:
        index = int(y // (self.ROW + self.GAP))
        return index if 0 <= index < len(self.bars) and y - index * (self.ROW + self.GAP) < self.ROW else None

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            index = self.row_at(event.pos().y())
            if index is None:
                QToolTip.hideText()
            else:
                QToolTip.showText(event.globalPos(), f"{self.bars[index]['name']} · {self.bars[index]['value']}", self)
            return True
        return super().event(event)


# ---------------------------------------------------------------- the timeline
def _geometry(model: dict) -> tuple[int, int]:
    """The ruler's height and a lane's, each with the line under it: the effect timeline's unless the model says."""
    return model.get("ruler", RULER), model.get("lane", LANE)


def _lane_heights(model: dict) -> list[int]:
    lane = _geometry(model)[1]
    return [FOLDED if lane_["collapsed"] else lane for lane_ in model["lanes"]]


class _Ruler(QWidget):
    """The window's ruler (``.cr-time-axis``): a tick a second, five or more, its time every fifth."""

    def __init__(self, model: dict, parent: QWidget):
        super().__init__(parent)
        self.model = model
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ruler = _geometry(self.model)[0]
        bottom = self.model.get("bottom", 32)
        painter.fillRect(self.rect(), QColor(C["panel"]))
        painter.setPen(QPen(RULE, 1))
        painter.drawLine(QPointF(0, ruler - 0.5), QPointF(self.width(), ruler - 0.5))
        ink = QColor(C["text"])
        faint = QColor(ink)
        faint.setAlphaF(0.6)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        for tick in self.model["ticks"]:
            painter.setPen(QPen(faint, 1))
            top = tick["top"] if "top" in tick else 17 if tick["long"] else 24
            painter.drawLine(QPointF(tick["x"], top), QPointF(tick["x"], bottom))
            if tick["text"]:
                painter.setPen(ink)
                painter.drawText(QRectF(tick["at"] - 40, 0, 80, 16), Qt.AlignHCenter | Qt.AlignBottom, tick["text"])
        painter.end()


class _Tracks(QWidget):
    """The lanes' markers (``.cr-track``): a hit or heal as its skill's tile, three stacks deep, a death as a red line
    with its cross."""

    inspected = Signal(str)

    def __init__(self, model: dict, icon, parent: QWidget):
        super().__init__(parent)
        self.model, self.icon = model, icon
        self.tops: list[int] = []
        top = 0
        for height in _lane_heights(model):
            self.tops.append(top)
            top += height
        self.current: tuple[int, int] | None = None     # the marker with the focus: its lane and its place in it
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Recorded effects")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        ink = QColor(C["text"])
        width = self.width()
        lane_height = _geometry(self.model)[1]
        for index, lane in enumerate(self.model["lanes"]):
            top = self.tops[index]
            height = FOLDED if lane["collapsed"] else lane_height
            if index % 2 == 0:                                  # ``.cr-lane:nth-child(even)``, the ruler the first
                painter.fillRect(QRectF(0, top, width, height - 1), SHADE)
            painter.setPen(QPen(RULE, 1))
            painter.drawLine(QPointF(0, top + height - 0.5), QPointF(width, top + height - 0.5))
            if lane["collapsed"]:
                continue
            if not lane["marks"]:
                font = painter.font()
                font.setPixelSize(12)
                painter.setFont(font)
                painter.setPen(ink)
                painter.drawText(QPointF(12, top + 25), self.model.get("empty", cw.NO_EFFECTS))
                continue
            for number, mark in enumerate(lane["marks"]):
                self._mark(painter, mark, top, (index, number) == self.current and self.hasFocus())
        painter.end()

    def _mark(self, painter: QPainter, mark: dict, top: int, focused: bool) -> None:
        fill = QColor(mark["fill"])
        x, y = mark["x"], top + mark["y"]
        if mark.get("style") == "cast":                         # a press: a 16 px tile, its cast time's line under it
            tile = QColor(fill)
            tile.setAlphaF(0.45)
            painter.setPen(QPen(QColor(C["text"]), 2) if focused else Qt.NoPen)
            painter.setBrush(tile)
            painter.drawRoundedRect(QRectF(x, y, 16, 16), 2, 2)
            painter.setBrush(Qt.NoBrush)
            picture = self.icon(mark["icon"]) if mark["icon"] else None
            if picture is not None and not picture.isNull():
                painter.drawPixmap(QRectF(x + 1, y + 1, 14, 14), picture, QRectF(picture.rect()))
            if mark.get("cast") is not None:
                painter.setPen(QPen(fill, 2))
                painter.drawLine(QPointF(x, y + 17), QPointF(x + mark["cast"], y + 17))
            return
        if mark.get("death"):
            painter.setPen(QPen(fill, 2))
            painter.drawLine(QPointF(x + 11, top), QPointF(x + 11, top + 84))
            font = painter.font()
            font.setPixelSize(21)
            painter.setFont(font)
            painter.setPen(fill)
            painter.drawText(QPointF(x, top + 20), "✝")
            return
        tile = QColor(fill)
        tile.setAlphaF(0.45)
        painter.setPen(QPen(QColor(C["text"]), 2) if focused else Qt.NoPen)
        painter.setBrush(tile)
        painter.drawRoundedRect(QRectF(x, y, 23, 23), 2, 2)
        painter.setBrush(Qt.NoBrush)
        font = painter.font()
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor(C["text"]))
        painter.drawText(QRectF(x - 8, y + 6, 39, 12), Qt.AlignCenter, mark["tag"])
        picture = self.icon(mark["icon"]) if mark["icon"] else None
        if picture is not None and not picture.isNull():
            painter.drawPixmap(QRectF(x + 1, y + 1, 21, 21), picture, QRectF(picture.rect()))
        painter.setPen(QPen(fill, 2))
        painter.drawLine(QPointF(x, y + 24), QPointF(x + 23, y + 24))

    # finding a marker
    @staticmethod
    def _bounds(mark: dict, top: int) -> list[QRectF]:
        if mark.get("style") == "cast":
            return [QRectF(mark["x"], top + mark["y"], 16, 18)]
        if mark.get("death"):
            return [QRectF(mark["x"], top, 18, 24), QRectF(mark["x"] + 8, top, 6, 84)]
        return [QRectF(mark["x"], top + mark["y"], 23, 25)]

    def at(self, point: QPointF) -> tuple[int, int] | None:
        """The marker under a point, the one drawn last when they overlap."""
        for index in range(len(self.model["lanes"]) - 1, -1, -1):
            lane, top = self.model["lanes"][index], self.tops[index]
            if lane["collapsed"] or not (top <= point.y() < top + _geometry(self.model)[1]):
                continue
            for number in range(len(lane["marks"]) - 1, -1, -1):
                if any(r.contains(point) for r in self._bounds(lane["marks"][number], top)):
                    return index, number
        return None

    def _show(self, place: tuple[int, int], tip_at: QPoint | None = None) -> None:
        index, number = place
        mark = self.model["lanes"][index]["marks"][number]
        self.inspected.emit(mark["detail"])
        if tip_at is None:
            box = self._bounds(mark, self.tops[index])[0]
            tip_at = self.mapToGlobal(QPoint(round(box.left()), round(box.bottom())))
        QToolTip.showText(tip_at + QPoint(12, 22), mark["detail"], self)

    def mouseMoveEvent(self, event) -> None:
        place = self.at(event.position())
        if place is None:
            QToolTip.hideText()
        else:
            self._show(place, event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        place = self.at(event.position())
        if place is not None:
            self.current = place
            self.setFocus(Qt.MouseFocusReason)
            self._show(place, event.globalPosition().toPoint())
            self.update()
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)

    # the keys
    def _marked(self) -> list[int]:
        return [i for i, lane in enumerate(self.model["lanes"]) if not lane["collapsed"] and lane["marks"]]

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        marked = self._marked()
        if self.current is None and marked:
            self.current = (marked[0], 0)
        if self.current is not None and event.reason() != Qt.MouseFocusReason:
            self.reveal()
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        marked = self._marked()
        if self.current is None or not marked or key not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
                                                              Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            super().keyPressEvent(event)
            return
        index, number = self.current
        lanes = self.model["lanes"]
        if key in (Qt.Key_Left, Qt.Key_Right):
            number = max(0, min(len(lanes[index]["marks"]) - 1, number + (1 if key == Qt.Key_Right else -1)))
        elif key in (Qt.Key_Up, Qt.Key_Down):
            at = marked.index(index) + (1 if key == Qt.Key_Down else -1)
            if 0 <= at < len(marked):
                x = lanes[index]["marks"][number]["x"]
                index = marked[at]
                number = min(range(len(lanes[index]["marks"])), key=lambda n: abs(lanes[index]["marks"][n]["x"] - x))
        self.current = (index, number)
        self.reveal()
        self.update()
        event.accept()

    def reveal(self) -> None:
        """The marker with the focus scrolled into view, its effect shown."""
        index, number = self.current
        mark = self.model["lanes"][index]["marks"][number]
        area = self.parent().parent().parent() if self.parent() is not None else None
        if isinstance(area, QScrollArea):
            ruler = _geometry(self.model)[0]
            area.ensureVisible(NAME_WIDTH + round(mark["x"]) + 11, ruler + self.tops[index] + 14, NAME_WIDTH + 40, ruler + 30)
        self._show(self.current)


class Timeline(QScrollArea):
    """The recorded effect timeline (``.cr-timeline``). ``name_cell(lane)`` gives a lane's name with its Collapse and
    Hide buttons, ``folded_cell(lane)`` a collapsed lane's Expand and Hide buttons; ``icon(address)`` a skill's icon
    the app bundles, or None (the marker keeps its ID tile). ``inspected`` gives the effect a marker holds."""

    inspected = Signal(str)

    def __init__(self, model: dict, name_cell, folded_cell, icon, parent: QWidget | None = None):
        super().__init__(parent)
        self.model = model
        self.setObjectName("crTimeline")
        self.setWidgetResizable(False)
        self.setStyleSheet(f"QScrollArea#crTimeline {{ border: 1px solid {EDGE.name(QColor.HexArgb)}; background: {C['bg1']}; }}"
                           f" QWidget#crSheet {{ background: {C['bg1']}; }}"
                           f" QFrame#crLaneName {{ background: {C['panel']}; border: none;"
                           f" border-right: 1px solid {EDGE.name(QColor.HexArgb)}; border-bottom: 1px solid {RULE.name(QColor.HexArgb)}; }}"
                           f" QLabel#crCorner {{ background: {C['panel']}; padding-left: 8px;"
                           f" border-right: 1px solid {EDGE.name(QColor.HexArgb)}; border-bottom: 1px solid {RULE.name(QColor.HexArgb)}; }}")
        heights = _lane_heights(model)
        self.ruler_height = ruler = _geometry(model)[0]
        width = math.ceil(model["width"])
        self.content_width = NAME_WIDTH + width
        lanes_height = sum(heights)
        self.sheet = QWidget()
        self.sheet.setObjectName("crSheet")
        self.sheet.setFixedSize(NAME_WIDTH + width, ruler + max(lanes_height, 32 if not heights else 0))
        self.tracks = _Tracks(model, icon, self.sheet)
        self.tracks.setGeometry(NAME_WIDTH, ruler, width, lanes_height)
        self.tracks.inspected.connect(self.inspected)
        top = ruler
        self.folded: list[QWidget] = []
        for lane, height in zip(model["lanes"], heights):
            if lane["collapsed"]:
                cell = folded_cell(lane)
                cell.setParent(self.sheet)
                cell.setGeometry(NAME_WIDTH, top, width, height - 1)
                self.folded.append(cell)
            top += height
        self.names = QWidget(self.sheet)
        self.names.setObjectName("plain")
        self.names.setGeometry(0, ruler, NAME_WIDTH, lanes_height)
        top = 0
        self.cells: list[QWidget] = []
        for lane, height in zip(model["lanes"], heights):
            cell = name_cell(lane)
            cell.setParent(self.names)
            cell.setGeometry(0, top, NAME_WIDTH, height)
            self.cells.append(cell)
            top += height
        if not heights:
            empty = QLabel(cw.NO_LANES, self.sheet)
            empty.setObjectName("plain")
            empty.move(8, ruler + 6)
            empty.adjustSize()
        self.ruler = _Ruler(model, self.sheet)
        self.ruler.setGeometry(NAME_WIDTH, 0, width, ruler)
        self.corner = QLabel(model.get("corner", "Encounter time"), self.sheet)
        self.corner.setObjectName("crCorner")
        self.corner.setGeometry(0, 0, NAME_WIDTH, ruler)
        self.names.raise_()
        self.ruler.raise_()
        self.corner.raise_()
        self.setWidget(self.sheet)
        self.horizontalScrollBar().valueChanged.connect(self._stick)
        self.verticalScrollBar().valueChanged.connect(self._stick)
        self.pending: tuple[int, int] | None = None
        self.setMinimumHeight(40)

    def _stick(self) -> None:
        """The names kept at the left and the ruler at the top (``position: sticky``)."""
        x, y = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        self.names.move(x, self.ruler_height)
        self.ruler.move(NAME_WIDTH, y)
        self.corner.move(x, y)

    def keep(self, scrolled: tuple[int, int] | None) -> None:
        """Scrolled as the timeline drawn before it was, once it has its size."""
        self.pending = scrolled

    def scrolled(self) -> tuple[int, int]:
        return self.horizontalScrollBar().value(), self.verticalScrollBar().value()

    def sizeHint(self) -> QSize:
        return QSize(NAME_WIDTH + 400, self._height(NAME_WIDTH + 400))

    def _height(self, width: int) -> int:
        frame = 2 * self.frameWidth()
        bar = self.style().pixelMetric(QStyle.PM_ScrollBarExtent, None, self)
        tall = self.sheet.height() + frame > MOST
        wide = self.content_width > width - frame - (bar if tall else 0)
        return min(MOST, self.sheet.height() + frame + (bar if wide else 0))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = max(self.content_width, self.viewport().width())     # the lanes as wide as the box (``min-width: 100%``)
        if self.sheet.width() != wide:
            self.sheet.setFixedWidth(wide)
            self.tracks.resize(wide - NAME_WIDTH, self.tracks.height())
            self.ruler.resize(wide - NAME_WIDTH, self.ruler_height)
            for cell in self.folded:
                cell.resize(wide - NAME_WIDTH, cell.height())
        height = self._height(self.width())
        if self.height() != height:
            self.setFixedHeight(height)
        if self.pending is not None:
            x, y = self.pending
            self.horizontalScrollBar().setValue(x)
            self.verticalScrollBar().setValue(y)
            self.pending = None
