"""The log review's charts (0.2.458), as combat-review.js draws them in SVG: the rate chart (``graph``) and the
recorder's ping (``latencyHTML``). Each keeps the web chart's viewBox, scaled to its width.

The rate chart says what it holds at a moment of the fight: a move of the pointer over it, a click on it, or the
left and right arrow keys once it has the focus (``inspect``) emit ``inspected`` with that time.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QToolTip, QWidget

from . import combat_review as cw
from . import combat_records as cr
from . import theme

C = theme.COLORS
BAR = QColor(57, 194, 224, 71)                 # --chart-bar
LINE = QColor(C["gold"])                       # --chart-line
HP = QColor("#ef6262")
PING = QColor("#6bd7ef")


class RateChart(QWidget):
    """The rate chart (``graph``, ``viewBox="0 0 1000 220"``): the total as bars under its ten-second average, or each
    player's series in their class's colour (dashed for damage taken, dotted for healing), with the bosses' HP in red on
    the right scale."""

    inspected = Signal(float)

    def __init__(self, model: dict, r: dict, colours: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.model, self.r, self.colours = model, r, colours
        self.at: float | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(140)
        self.setAccessibleName("Combat rate chart")

    def sizeHint(self) -> QSize:
        return QSize(1000, 220)

    def heightForWidth(self, width: int) -> int:
        return max(140, round(width * 0.22))

    def hasHeightForWidth(self) -> bool:
        return True

    def _scale(self) -> tuple[float, float]:
        return self.width() / 1000.0, self.height() / 220.0

    def _x(self, t: float) -> float:
        return 60 + 880 * t / self.model["duration"]

    def _y(self, v: float) -> float:
        return 180 - v * 160 / self.model["maximum"]

    def paintEvent(self, _event) -> None:
        m = self.model
        sx, sy = self._scale()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(sx, sy)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        ink = QColor(C["text"])
        faint = QColor(ink)
        faint.setAlphaF(0.12)
        for f in (0, 0.25, 0.5, 0.75, 1):                           # the grid and its figures
            y = 180 - f * 160
            painter.setPen(QPen(faint, 1))
            painter.drawLine(QPointF(60, y), QPointF(940, y))
            painter.setPen(ink)
            painter.drawText(QRectF(0, y - 8, 52, 16), Qt.AlignRight | Qt.AlignVCenter, cw.number(m["maximum"] * f))
        for i in range(7):                                          # the times under it
            painter.drawText(QRectF(60 + i * 880 / 6 - 40, 194, 80, 16), Qt.AlignCenter, cw.clock(m["duration"] * i / 6))
        step, duration = m["step"], m["duration"]
        if m["mode"] == "players":
            for s in m["lines"]:
                colour = QColor(cr.class_colour(self.r.get(s["actor"], {}).get("class"), self.colours))
                pen = QPen(colour, 2)
                if s["kind"] == "Damage taken":
                    pen.setDashPattern([3.5, 2])
                elif s["kind"] == "Healing":
                    pen.setDashPattern([1, 1.5])
                painter.setPen(pen)
                painter.drawPolyline(QPolygonF([QPointF(self._x(min(duration, (i + 0.5) * step)), self._y(v))
                                                for i, v in enumerate(s["values"])]))
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(BAR)
            for i, v in enumerate(m["total"]):
                width = max(0.5, 880 * min(step, duration - i * step) / duration - 1)
                painter.drawRect(QRectF(self._x(i * step), self._y(v), width, 180 - self._y(v)))
            painter.setPen(QPen(LINE, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF([QPointF(self._x(min(duration, (i + 0.5) * step)), self._y(v))
                                            for i, v in enumerate(m["roll"])]))
        if m["health"]:                                             # the bosses' HP on the right scale
            painter.setPen(QPen(HP, 1.5))
            for entity in dict.fromkeys(s.get("entity") for s in m["health"]):
                points = [QPointF(self._x(cw._num(s.get("t")) or 0.0),
                                  180 - (cw._num(s.get("current")) or 0.0) * 160 / m["hp_max"])
                          for s in m["health"] if s.get("entity") == entity]
                painter.drawPolyline(QPolygonF(points))
            painter.drawText(QRectF(948, 15, 52, 14), Qt.AlignLeft | Qt.AlignVCenter, cw.number(m["hp_max"]))
            painter.drawText(QRectF(948, 174, 52, 14), Qt.AlignLeft | Qt.AlignVCenter, "0 HP")
        if self.at is not None:                                     # the moment inspected
            pen = QPen(ink, 1)
            pen.setDashPattern([3, 3])
            painter.setPen(pen)
            x = self._x(self.at)
            painter.drawLine(QPointF(x, 20), QPointF(x, 180))
        painter.end()

    def inspect(self, t: float) -> None:
        """A moment of the fight inspected: the cursor drawn there, and ``inspected`` emitted."""
        self.at = max(0.0, min(self.model["duration"], t))
        self.update()
        self.inspected.emit(self.at)

    def _time(self, x: float) -> float:
        sx, _sy = self._scale()
        return (x / sx - 60) / 880 * self.model["duration"]

    def _inside(self, x: float, y: float) -> bool:
        sx, sy = self._scale()
        return 60 <= x / sx <= 940 and 20 <= y / sy <= 180

    def mouseMoveEvent(self, event) -> None:
        position = event.position()
        if self._inside(position.x(), position.y()):
            self.inspect(self._time(position.x()))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        position = event.position()
        if self._inside(position.x(), position.y()):
            self.setFocus()
            self.inspect(self._time(position.x()))
        super().mousePressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.inspect(self.at or 0.0)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            self.inspect((self.at or 0.0) + (-1 if event.key() == Qt.Key_Left else 1) * self.model["step"])
            event.accept()
            return
        super().keyPressEvent(event)


class PingChart(QWidget):
    """The recorder's ping over the fight (``viewBox="0 0 1000 160"``): each sample a dot, its time and latency on
    hover."""

    def __init__(self, ping: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.ping = ping
        self.setMouseTracking(True)
        self.setMinimumHeight(110)
        self.setAccessibleName("Recorder ping over encounter time")

    def sizeHint(self) -> QSize:
        return QSize(1000, 160)

    def heightForWidth(self, width: int) -> int:
        return max(110, round(width * 0.16))

    def hasHeightForWidth(self) -> bool:
        return True

    def _place(self, t: float, ms: float) -> QPointF:
        p = self.ping
        return QPointF(60 + 880 * t / p["duration"], 130 - 110 * ms / p["scale"])

    def paintEvent(self, _event) -> None:
        p = self.ping
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(self.width() / 1000.0, self.height() / 160.0)
        font = painter.font()
        font.setPixelSize(12)
        painter.setFont(font)
        ink = QColor(C["text"])
        painter.setPen(ink)
        painter.drawText(QPointF(5, 25), f"{theme.fixed(p['scale'], 1)} ms")
        painter.drawText(QPointF(10, 130), "0 ms")
        painter.drawText(QPointF(60, 150), "0:00")
        painter.drawText(QPointF(900, 150), cw.clock(p["duration"]))
        axis = QColor(ink)
        axis.setAlphaF(0.3)
        painter.setPen(QPen(axis, 1))
        painter.drawPolyline(QPolygonF([QPointF(60, 20), QPointF(60, 130), QPointF(940, 130)]))
        painter.setPen(Qt.NoPen)
        painter.setBrush(PING)
        for t, ms in p["points"]:
            painter.drawEllipse(self._place(t, ms), 2.5, 2.5)
        painter.end()

    def event(self, event) -> bool:
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.ToolTip:
            sx, sy = self.width() / 1000.0, self.height() / 160.0
            best = None
            for t, ms in self.ping["points"]:
                place = self._place(t, ms)
                distance = abs(place.x() * sx - event.pos().x()) + abs(place.y() * sy - event.pos().y())
                if best is None or distance < best[0]:
                    best = (distance, f"{cw.clock(t, True)} · {theme.fixed(ms, 1)} ms")
            if best is not None and best[0] <= 8:
                QToolTip.showText(event.globalPos(), best[1], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)
