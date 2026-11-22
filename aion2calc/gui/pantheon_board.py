"""The recommended Pantheon board (0.2.445), as pages/advice.js's ``pantheonBoardHTML`` draws it: the colossus in the
centre, four statue stands on the inner ring and twelve artwork stands on the outer ring, each showing the decoration
recommended for it (its picture and deity points, or its name), with the piece's points, gain and sources when
hovered.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme

VIEW = 460.0                      # the board's viewBox, scaled to the widget
CENTRE, INNER, OUTER = 230.0, 108.0, 190.0


def hexagon(x: float, y: float, r: float) -> QPolygonF:
    """A stand's hexagon, a point at the top (``hex``)."""
    return QPolygonF([QPointF(x + r * math.cos(math.radians(-90 + i * 60)), y + r * math.sin(math.radians(-90 + i * 60)))
                      for i in range(6)])


def stand_places() -> list[dict]:
    """Where each stand is on the board: the twelve artworks round the outer ring from the top, the four statues on
    the inner ring from the lower right, then the colossus in the centre (drawn last, over the rings)."""
    places = []
    for i in range(12):
        a = math.radians(-90 + i * 30)
        places.append({"kind": "artwork", "index": i, "x": CENTRE + OUTER * math.cos(a), "y": CENTRE + OUTER * math.sin(a),
                       "r": 27.0})
    for i in range(4):
        a = math.radians(45 + i * 90)
        places.append({"kind": "statue", "index": i, "x": CENTRE + INNER * math.cos(a), "y": CENTRE + INNER * math.sin(a),
                       "r": 40.0})
    places.append({"kind": "colossus", "index": 0, "x": CENTRE, "y": CENTRE, "r": 58.0})
    return places


class PantheonBoard(QWidget):
    """The board of ``advice.board_stands``. ``pictures`` holds the decorations' pictures read so far, by their
    address in the app's icon cache; ``paths`` names each stand's."""

    def __init__(self, stands: dict, paths: dict[str, str] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.stands = stands
        self.paths = paths or {}
        self.pictures: dict[str, QPixmap] = {}
        self.hovered = -1
        self.places = stand_places()
        self.setMouseTracking(True)
        self.setMinimumSize(280, 280)
        self.setMaximumWidth(460)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName("Recommended Pantheon board")

    def stand(self, place: dict) -> dict:
        if place["kind"] == "colossus":
            return self.stands["colossus"]
        return self.stands["statues" if place["kind"] == "statue" else "artworks"][place["index"]]

    def set_picture(self, path: str, pixmap: QPixmap) -> None:
        if path in self.paths.values():
            self.pictures[path] = pixmap
            self.update()

    # ---------------------------------------------------------------- size
    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return min(width, 460)

    def sizeHint(self) -> QSize:
        return QSize(460, 460)

    # ---------------------------------------------------------------- where the mouse is
    def _scale(self) -> tuple[float, float, float]:
        side = min(self.width(), self.height())
        return side / VIEW, (self.width() - side) / 2, (self.height() - side) / 2

    def stand_at(self, x: float, y: float) -> int:
        """The stand under a point of the widget, -1 for none (the colossus over the rings, then the others)."""
        scale, left, top = self._scale()
        bx, by = (x - left) / scale, (y - top) / scale
        for index in range(len(self.places) - 1, -1, -1):
            place = self.places[index]
            if math.hypot(bx - place["x"], by - place["y"]) <= place["r"]:
                return index
        return -1

    def mouseMoveEvent(self, event) -> None:
        index = self.stand_at(event.position().x(), event.position().y())
        if index != self.hovered:
            self.hovered = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered = -1
        self.update()
        super().leaveEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            index = self.stand_at(event.pos().x(), event.pos().y())
            if index < 0:
                QToolTip.hideText()
                event.ignore()
            else:
                QToolTip.showText(event.globalPos(), self.stand(self.places[index])["tip"], self)
            return True
        return super().event(event)

    # ---------------------------------------------------------------- drawing
    def _text(self, painter: QPainter, x: float, y: float, words: str, colour: str, size: int = 16, bold: bool = True,
              spacing: float = 0.0) -> None:
        """Words centred on ``x`` with their baseline at ``y`` (``text-anchor="middle"``)."""
        if not words:
            return
        font = QFont(self.font())
        font.setPixelSize(size)
        font.setBold(bold)
        if spacing:
            font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        painter.setFont(font)
        painter.setPen(QColor(colour))
        width = painter.fontMetrics().horizontalAdvance(words)
        painter.drawText(QPointF(x - width / 2, y), words)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scale, left, top = self._scale()
        painter.translate(left, top)
        painter.scale(scale, scale)
        ring = QPen(theme.qcolor("frame"), 1.5)                       # app.css --frame
        ring.setDashPattern([4 / 1.5, 6 / 1.5])
        painter.setPen(ring)
        painter.setBrush(Qt.NoBrush)
        for radius in (OUTER, INNER):
            painter.drawEllipse(QPointF(CENTRE, CENTRE), radius, radius)
        for index, place in enumerate(self.places):
            self._stand(painter, index, place)
        painter.end()

    def _stand(self, painter: QPainter, index: int, place: dict) -> None:
        stand, kind = self.stand(place), place["kind"]
        x, y, r = place["x"], place["y"], place["r"]
        colossus = kind == "colossus"
        fill = ((QColor(theme.COLORS["board_a"]) if colossus else QColor(theme.COLORS["panel2"])) if stand["set"]
                else theme.qcolor("inset"))
        edge = QPen(QColor(theme.COLORS["gold"]) if colossus and stand["set"] else theme.qcolor("frame_hi") if stand["set"]
                    else QColor(theme.COLORS["line2"]), 2.5 if colossus and stand["set"] else 1.5)
        if index == self.hovered:
            edge = QPen(QColor(theme.COLORS["accent"]), 2.5)
        painter.setPen(edge)
        painter.setBrush(fill)
        if kind == "artwork":
            painter.drawEllipse(QPointF(x, y), r, r)
        else:
            painter.drawPolygon(hexagon(x, y, r))
        faint, gold, text = theme.COLORS["faint"], theme.COLORS["gold"], theme.COLORS["text"]
        name_colour = faint if not stand["set"] else gold if colossus else text
        points_colour = faint if not stand["set"] else gold
        picture = self.pictures.get(self.paths.get(f"{kind}:{place['index']}", ""))
        drawn = bool(stand["icon"]) and picture is not None and not picture.isNull()   # its name until it is read
        size, below = {"artwork": (34, (-23, 23)), "statue": (40, (-30, 26)), "colossus": (46, (-50, 11))}[kind]
        if drawn:
            frame = QPainterPath()
            frame.addRoundedRect(QRectF(x - size / 2, y + below[0], size, size), 4, 4)
            painter.save()
            painter.setClipPath(frame)
            painter.drawPixmap(QRectF(x - size / 2, y + below[0], size, size), picture, QRectF(picture.rect()))
            painter.restore()
            self._text(painter, x, y + below[1], stand["points"], points_colour, bold=True)
        else:
            name_at, points_at = {"artwork": (-2, 11), "statue": (-4, 12), "colossus": (-8, 10)}[kind]
            self._text(painter, x, y + name_at, stand["name"], name_colour)
            self._text(painter, x, y + points_at, stand["points"], points_colour)
        if colossus:
            self._text(painter, x, y + (28 if drawn else 26), "COLOSSUS", faint, bold=False, spacing=1.2)
