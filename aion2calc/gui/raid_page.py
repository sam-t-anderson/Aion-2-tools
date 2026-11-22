"""Combat → Raid Planner (0.2.490): the web planner (raid.js ``A2Raid.mount``) drawn by the app, with the plans it
keeps (``gui/raid.py``).

The page is the web page's: the plan chosen from those kept, its name, author, length, arena and the boss it is for;
its file, its share code; the map with each token at the moment chosen, which a token is dragged on to place it then;
the transport and the party buffs' lane; the panel to add tokens, edit the one selected, choose which the map shows,
the buffs and the notes. Each change keeps the plan at once, as the web page does, and hands the app the plans for its
overlay.

Publishing and browsing plans, a saved fight compared and recorded movement imported are drawn on the web Raid
Planner for now (its button opens it): the plans are the same.
"""
from __future__ import annotations

import html
import math
import os
import random
import re
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QBoxLayout, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QToolTip, QVBoxLayout, QWidget)

from . import builds as b
from . import raid as r
from . import theme
from .api import AppApi, Requests
from .builds import _MISSING, get
from .builds_page import NumberField, _row
from .combat_page import stylesheet as combat_stylesheet
from .database_page import Window
from .pets_page import Toast, _clear
from .planner_page import interface_store
from .settings_looks import js_parse
from .timers_page import Fold

# ------------------------------------------------------------------ the page's words (raid.js)
PLAN = "Plan"
NEW, DUPLICATE, DELETE = "New", "Duplicate", "Delete"
NAME_HINT, AUTHOR_HINT = "Plan name", "Author (optional)"
LENGTH, SECONDS, ARENA = "Length", "s", "Arena"
ARENAS = (("square", "Square"), ("circle", "Circle"))
BOSS, BOSS_HINT, NPC, NPC_HINT = "Boss", "Boss / mini-boss name", "NPC id", "mob code"
LINK_NOTE = "Link this plan to an encounter so the overlay can auto-play it for that fight."
EXPORT, IMPORT, COPY_CODE, LOAD_CODE = "Export file", "Import file", "Copy share code", "Load from code"
ON_THE_WEB = ("Publishing and browsing plans, comparing with a saved fight and importing recorded movement are on the "
              "web Raid Planner for now. It shows these plans too.")
OPEN_WEB = "Open the web Raid Planner"
PUBLISHED = "Published link: "
ARENA_HINT = "Add players, enemies, markers or AoE zones from the panel, then drag them on the map."
BACK_TO_START, PLAY, PAUSE = "⏮", "▶ Play", "⏸ Pause"
SPEED_TIP, MOMENT = "Playback speed", "Moment in the fight"
BUFF_LANE, BUFF_LANE_HINT = "Party buffs", "add buffs in the panel →"
BUFFS_NOW, NONE_NOW = "Buffs now:", "none"
ADD, SELECTED, SHOWN, BUFFS, NOTES = "ADD", "SELECTED TOKEN", "SHOWN ON THE MAP", "PARTY BUFFS", "NOTES"
ADD_PLAYER, ADD_ENEMY, ADD_MARKER, ADD_AOE = "+ Player", "+ Enemy", "+ Marker", "+ AoE"
ADD_NOTE = ("Move the slider to a moment, then drag a token to where it should be then. The planner interpolates the "
            "movement in between.")
SELECT_NOTE = "Select a token on the map to edit it."
LABEL_HINT, RADIUS, NO_FRAMES = "Label", "Radius", "none"
DELETE_FRAME = "Delete this keyframe"
SHOWN_BOX, REMOVE = "Shown on the map", "Remove token"
EACH = "Each token"
NO_BUFFS, BUFF_HINT, SOURCE, ADD_BUFF = "none yet", "Buff name", "source…", "Add"
NOTES_HINT = "Callouts, phases, assignments…"
PANEL_ELSEWHERE = "Compare with a fight and Import recorded movement are on the web Raid Planner for now."
# what is said (``toast``) and asked
COPIED, COPY_FAILED = "Copied to clipboard", "Copy failed"
IMPORTED, LOADED, NAME_BUFF = "Plan imported", "Plan loaded", "Name the buff"
MOVEMENT_ELSEWHERE = "Recorded movement is imported on the web Raid Planner for now."
ASK_DELETE = "Delete this plan?"
ASK_CODE = "Paste an a2plan share code:"
TOAST_MS = 1800                                       # raid.js ``toast``'s time
WIDE = 1000                                           # narrower than this, the panel goes under the map


def _label(words: str = "", name: str = "", wrap: bool = True) -> QLabel:
    label = QLabel(words)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _button(words: str, action, name: str = "small", tip: str = "") -> QPushButton:
    button = QPushButton(words.replace("&", "&&"))
    button.setObjectName(name)
    button.setAccessibleName(words)
    if tip:
        button.setToolTip(tip)
    button.clicked.connect(lambda _checked=False: action())
    return button


def _head(words: str) -> QLabel:
    """``h4.gold.small``."""
    return _label(words, "rpHead")


def _edit(value: str, hint: str, width: int, name: str = "") -> QLineEdit:
    edit = QLineEdit(value)
    edit.setPlaceholderText(hint)
    edit.setAccessibleName(name or hint)
    edit.setFixedWidth(width)
    edit.kept = value
    return edit


def _finished(edit: QLineEdit, action) -> None:
    """A text field's ``change``: its text changed, then left or Enter pressed."""
    def done():
        if edit.text() != edit.kept:
            edit.kept = edit.text()
            action(edit.text())
    edit.editingFinished.connect(done)


def _choice(items, chosen: int, name: str, action, width: int | None = None) -> QComboBox:
    """A ``select``: ``action(index)`` when another is chosen (``change``)."""
    box = QComboBox()
    for words, value in items:
        box.addItem(words, value)
    box.setCurrentIndex(max(0, chosen))
    box.setAccessibleName(name)
    if width:
        box.setFixedWidth(width)
    box.kept = box.currentIndex()

    def chose(index: int) -> None:
        if index != box.kept:
            box.kept = index
            action(index)
    box.activated.connect(chose)
    return box


def css_colour(words: str | None) -> QColor | None:
    """A CSS hex colour (``#rgb``, ``#rgba``, ``#rrggbb``, ``#rrggbbaa``); None for one CSS does not read."""
    if not words or not words.startswith("#"):
        return None
    h = words[1:]
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    if len(h) not in (6, 8):
        return None
    try:
        rgb = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
    except ValueError:
        return None
    return QColor(rgb[0], rgb[1], rgb[2], rgb[3] if len(rgb) == 4 else 255)


def _mixed(colour: QColor | None, share: float) -> QColor | None:
    """``color-mix(in srgb, colour share, transparent)``."""
    if colour is None:
        return None
    out = QColor(colour)
    out.setAlphaF(colour.alphaF() * share)
    return out


def _finite(x: float) -> float:
    """A place that does not read as a number: where the browser leaves it, at the arena's corner."""
    return x if math.isfinite(x) else 0.0


# ------------------------------------------------------------------ the map
class Arena(QWidget):
    """The plan's map (``#arena``): a square (or a circle that hides what is outside it) with its 10% grid, the
    selected token's path and keyframes, and each token at the moment shown: a player's (30 px) and an enemy's
    (36 px) round letter, a marker's (24 px), an area's shape at a third of its colour. A token pressed is selected;
    dragged, it is placed there at the moment shown."""

    SIDE = 680
    MARGIN = 24                                            # room for a token past a square arena's edge

    def __init__(self, page: "RaidPage"):
        super().__init__()
        self.page = page
        self.drag: dict | None = None
        self.pressed: str | None = None                    # the token pressed, by its text id, until let go
        self.side = self.SIDE
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAccessibleName("Plan map")
        self.set_side(self.SIDE)

    def set_side(self, side: int) -> None:
        self.side = side
        self.setFixedSize(side + 2 * self.MARGIN, side + 2 * self.MARGIN)

    def sizeHint(self):
        return QSize(self.side + 2 * self.MARGIN, self.side + 2 * self.MARGIN)

    def frame_box(self) -> QRectF:
        """The arena's own box (``#arena``, its 1 px frame included)."""
        return QRectF(self.MARGIN, self.MARGIN, self.side, self.side)

    def inner(self) -> QRectF:
        """The padding box, inside the 1 px frame: what places and areas are shares of."""
        return self.frame_box().adjusted(1, 1, -1, -1)

    # ---------------------------------------------------------------- what is drawn
    def tokens(self) -> list[tuple[int, object, QPointF]]:
        """Each token drawn now, by its place in the plan's list, and its centre (``layout``)."""
        page, out = self.page, []
        inner = self.inner()
        for i, tk in enumerate(r._list(get(page.plan, "tokens", _MISSING))):
            if self.drag is not None and self.drag["index"] == i and self.drag["moved"]:
                box = self.frame_box()
                out.append((i, tk, QPointF(box.left() + self.drag["x"] * box.width(),
                                           box.top() + self.drag["y"] * box.height())))
                continue
            place = r.drawn(tk, page.t)
            if place is None:
                continue
            out.append((i, tk, QPointF(inner.left() + _finite(place[0]) * inner.width(),
                                       inner.top() + _finite(place[1]) * inner.height())))
        return out

    def chosen(self, tk) -> bool:
        """Outlined: the token selected (``.sel``), or, while pressed, each token with its id's text."""
        if self.pressed is not None:
            return r.text(get(tk, "id", _MISSING)) == self.pressed
        return self.page.sel is not None and r.strictly(get(tk, "id", _MISSING), self.page.sel)

    def box(self, tk, centre: QPointF) -> tuple[QRectF, str]:
        """A token's box and its shape: ``circle``, ``round`` (rounded) or ``square``."""
        kind = get(tk, "kind", _MISSING)
        if r.strictly(kind, "aoe"):
            side = r.aoe_span(tk) * 2 * self.inner().width()
            shaped = bool(_shape(tk))
            return QRectF(centre.x() - side / 2, centre.y() - side / 2, side, side), "square" if shaped else "circle"
        side = 36 if r.strictly(kind, "enemy") else 24 if r.strictly(kind, "marker") else 30
        shape = "round" if side in (36, 24) else "circle"
        return QRectF(centre.x() - side / 2, centre.y() - side / 2, side, side), shape

    @staticmethod
    def corner(tk) -> float:
        """A rounded token's corner: an enemy's 6 px, a marker's 4."""
        return 6.0 if r.strictly(get(tk, "kind", _MISSING), "enemy") else 4.0

    def order(self) -> list:
        """The tokens in the order they are painted: areas (z-index 1), then the others (2), the selected one on top
        (4); among the same, as listed."""
        drawn = self.tokens()

        def level(item):
            tk = item[1]
            if r.strictly(get(tk, "kind", _MISSING), "aoe"):
                return 1
            return 4 if self.chosen(tk) else 2
        return sorted(drawn, key=level)

    def hit(self, point: QPointF):
        """The token under ``point``, the one painted last first; within a circle arena, only inside it."""
        if r.strictly(get(get(self.page.plan, "arena", _MISSING), "kind", _MISSING), "circle"):
            box = self.frame_box()
            if math.hypot(point.x() - box.center().x(), point.y() - box.center().y()) > box.width() / 2:
                return None
        for i, tk, centre in reversed(self.order()):
            rect, shape = self.box(tk, centre)
            if shape == "circle":
                radius = rect.width() / 2
                if math.hypot(point.x() - centre.x(), point.y() - centre.y()) <= radius:
                    return i, tk
            elif rect.contains(point):
                return i, tk
        return None

    # ---------------------------------------------------------------- painting
    def paintEvent(self, _event) -> None:
        page = self.page
        c = theme.COLORS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        circle = r.strictly(get(get(page.plan, "arena", _MISSING), "kind", _MISSING), "circle")
        box = self.frame_box()
        outer = box.adjusted(0.5, 0.5, -0.5, -0.5)
        inner = self.inner()
        ground = QPainterPath()
        if circle:
            ground.addEllipse(box)
        else:
            ground.addRoundedRect(box, 8, 8)
        painter.setClipPath(ground)
        painter.fillRect(box, theme.qcolor("inset"))
        grid = theme.qcolor("line_soft")
        for i in range(10):                                  # a 1 px line at the start of each tenth
            x = inner.left() + inner.width() * i / 10
            y = inner.top() + inner.height() * i / 10
            painter.fillRect(QRectF(x, inner.top(), 1, inner.height()), grid)
            painter.fillRect(QRectF(inner.left(), y, inner.width(), 1), grid)
        self._shadow(painter, inner, circle)
        if not circle:                                       # only a circle arena hides what is past its edge
            painter.setClipping(False)
        self._path(painter, inner)
        for i, tk, centre in self.order():
            self._token(painter, tk, centre)
        if not r._list(get(page.plan, "tokens", _MISSING)):
            painter.setPen(QColor(c["faint"]))
            painter.drawText(inner.adjusted(24, 24, -24, -24), Qt.AlignCenter | Qt.TextWordWrap, ARENA_HINT)
        painter.setClipping(False)
        painter.setPen(QPen(theme.qcolor("frame"), 1))
        painter.setBrush(Qt.NoBrush)
        if circle:
            painter.drawEllipse(outer)
        else:
            painter.drawRoundedRect(outer, 8, 8)

    @staticmethod
    def _shadow(painter: QPainter, inner: QRectF, circle: bool) -> None:
        """``box-shadow: inset 0 0 60px rgba(0, 0, 0, .35)``, near enough: dark at the edge, gone 60 px in."""
        from PySide6.QtGui import QLinearGradient, QRadialGradient
        if circle:
            g = QRadialGradient(inner.center(), inner.width() / 2)
            g.setColorAt(max(0.0, 1 - 60 / max(1.0, inner.width() / 2)), QColor(0, 0, 0, 0))
            g.setColorAt(1.0, QColor(0, 0, 0, 45))
            painter.fillRect(inner, g)
            return
        for start, end in ((inner.topLeft(), QPointF(inner.left(), inner.top() + 60)),
                           (inner.bottomLeft(), QPointF(inner.left(), inner.bottom() - 60)),
                           (inner.topLeft(), QPointF(inner.left() + 60, inner.top())),
                           (inner.topRight(), QPointF(inner.right() - 60, inner.top()))):
            g = QLinearGradient(start, end)
            g.setColorAt(0, QColor(0, 0, 0, 45))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            painter.fillRect(inner, g)

    def _path(self, painter: QPainter, inner: QRectF) -> None:
        """The selected token's keyframes (``#rpath``): a dashed gold line through them, a dot at each, the one the
        moment is at in the accent colour; while it is dragged, the line through its new place."""
        page = self.page
        sx, sy = inner.width() / 100, inner.height() / 100

        def at(x, y):
            return QPointF(inner.left() + _finite(x) * 100 * sx, inner.top() + _finite(y) * 100 * sy)
        if self.drag is not None and self.drag["moved"]:
            tk = page.find(self.drag["tid"])
            if tk is None:
                return
            q = (self.drag["x"], self.drag["y"])
            frames = r._list(get(tk, "keyframes", _MISSING))
            points = [at(*q) if abs(r.number_of(get(k, "t", _MISSING)) - page.t) < 0.06 else
                      at(r.number_of(get(k, "x", _MISSING)), r.number_of(get(k, "y", _MISSING))) for k in frames]
            self._line(painter, points, sx)
            self._dot(painter, at(*q), 2.2 * sx, theme.qcolor("accent"))
            return
        tk = page.find(page.sel) if page.sel is not None else None
        frames = get(tk, "keyframes", _MISSING) if tk is not None else _MISSING
        if not isinstance(frames, list) or not r.yes(frames):
            return
        points = [at(r.number_of(get(k, "x", _MISSING)), r.number_of(get(k, "y", _MISSING))) for k in frames]
        if len(points) > 1:
            self._line(painter, points, sx)
        current = r.current_keyframe(tk, page.t)
        gold = QColor(theme.COLORS["gold"])
        gold.setAlphaF(0.55)
        for i, point in enumerate(points):
            if i == current:
                self._dot(painter, point, 2.2 * sx, theme.qcolor("accent"))
            else:
                self._dot(painter, point, 1.6 * sx, gold)

    @staticmethod
    def _line(painter: QPainter, points: list, unit: float) -> None:
        if len(points) < 2:
            return
        gold = QColor(theme.COLORS["gold"])
        gold.setAlphaF(0.8)
        pen = QPen(gold, 0.6 * unit)
        pen.setDashPattern([2 / 0.6, 1.5 / 0.6])              # ``stroke-dasharray: 2 1.5`` in the line's widths
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QPolygonF(points))

    @staticmethod
    def _dot(painter: QPainter, point: QPointF, radius: float, colour: QColor) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(point, radius, radius)

    def _token(self, painter: QPainter, tk, centre: QPointF) -> None:
        rect, shape = self.box(tk, centre)
        tc = css_colour(r.col(get(tk, "color", _MISSING)))
        kind = get(tk, "kind", _MISSING)
        if r.strictly(kind, "aoe"):
            body = _shape(tk)
            if body:
                self._shaped(painter, tk, rect, tc, body)
            else:
                fill = _mixed(tc, 0.34)
                painter.setBrush(fill if fill is not None else Qt.NoBrush)
                if tc is not None:
                    pen = QPen(tc, 1)
                    pen.setStyle(Qt.DashLine)
                    painter.setPen(pen)
                else:
                    painter.setPen(Qt.NoPen)
                painter.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        else:
            corner = self.corner(tk)
            shadow = QRectF(rect).translated(0, 2).adjusted(-2, -2, 2, 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 60))
            self._shape_path(painter, shadow, shape, corner + 2)
            painter.setBrush(tc if tc is not None else Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 89), 2))
            self._shape_path(painter, rect.adjusted(1, 1, -1, -1), shape, corner - 1)
            font = QFont(self.font())
            font.setPixelSize(16)
            font.setWeight(QFont.ExtraBold)
            painter.setFont(font)
            words = r.glyph(tk)
            painter.setPen(QColor(255, 255, 255, 77))
            painter.drawText(rect.translated(0, 1), Qt.AlignCenter, words)
            painter.setPen(QColor("#ffffff") if r.strictly(kind, "enemy") else QColor("#0b0f18"))
            painter.drawText(rect, Qt.AlignCenter, words)
        if self.chosen(tk):                                   # ``outline: 2px solid gold; outline-offset: 2px``
            painter.setPen(QPen(QColor(theme.COLORS["gold"]), 2))
            painter.setBrush(Qt.NoBrush)
            self._shape_path(painter, rect.adjusted(-3, -3, 3, 3), shape, self.corner(tk) + 3)

    @staticmethod
    def _shape_path(painter: QPainter, rect: QRectF, shape: str, corner: float = 0) -> None:
        if shape == "circle":
            painter.drawEllipse(rect)
        elif shape == "round":
            painter.drawRoundedRect(rect, corner, corner)
        else:
            painter.drawRect(rect)

    @staticmethod
    def _shaped(painter: QPainter, tk, rect: QRectF, tc: QColor | None, body: str) -> None:
        """``aoeShapeSVG``: a ring from its inner radius out, a cone of its half-angle about its facing, or a line
        along its facing, in the token's box (``viewBox -1 -1 2 2``)."""
        half = rect.width() / 2
        cx, cy = rect.center().x(), rect.center().y()
        fill = _mixed(tc, 0.34)
        facing = r.num(get(tk, "facing", _MISSING)) * math.pi / 180
        if body == "ring":
            inner = max(0.0, min(0.98, r.num(get(tk, "inner", _MISSING)) / r.aoe_span(tk)))
            stroke = _mixed(tc, 0.40)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(stroke, (1 - inner) * half) if stroke is not None else Qt.NoPen)
            middle = (1 + inner) / 2 * half
            painter.drawEllipse(QPointF(cx, cy), middle, middle)
            return
        painter.setBrush(fill if fill is not None else Qt.NoBrush)
        painter.setPen(QPen(tc, 0.01 * rect.width()) if tc is not None else Qt.NoPen)
        if body == "cone":
            angle = r.number_of(get(tk, "angle", _MISSING))
            a0 = facing - angle * math.pi / 180
            path = QPainterPath(QPointF(cx, cy))
            path.lineTo(cx + half * math.cos(a0), cy - half * math.sin(a0))
            path.arcTo(QRectF(cx - half, cy - half, 2 * half, 2 * half), math.degrees(a0), 2 * angle)
            path.closeSubpath()
            painter.drawPath(path)
            return
        width = r.number_of(get(tk, "width", _MISSING))
        w = max(0.01, (width if r.yes(width) else 0.02) / 2 / r.aoe_span(tk))
        ux, uy = math.cos(facing), -math.sin(facing)
        px, py = -uy * w, ux * w
        points = [(px, py), (ux + px, uy + py), (ux - px, uy - py), (-px, -py)]
        painter.drawPolygon(QPolygonF([QPointF(cx + x * half, cy + y * half) for x, y in points]))

    # ---------------------------------------------------------------- dragging (``pointerdown``, ``pointermove``)
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        page = self.page
        hit = self.hit(event.position())
        if hit is None and not self.frame_box().contains(event.position()):
            return                                           # past the arena, not on a token: not the arena's
        if hit is None:                                      # empty ground: nothing selected any more
            if page.sel is not None:
                page.sel = None
                page.render()
            return
        if page.playing:
            page.pause()
        index, tk = hit
        tid = r.text(get(tk, "id", _MISSING))
        page.sel = tid
        self.pressed = tid
        self.drag = {"index": index, "tid": tid, "moved": False, "x": 0.0, "y": 0.0}
        page.show_moment()

    def mouseMoveEvent(self, event) -> None:
        if self.drag is None:
            return
        point, box = event.position(), self.frame_box()
        self.drag.update(x=max(0.0, min(1.0, (point.x() - box.left()) / max(1.0, box.width()))),
                         y=max(0.0, min(1.0, (point.y() - box.top()) / max(1.0, box.height()))), moved=True)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.drag is None:
            return
        drag, self.drag = self.drag, None
        self.pressed = None
        page = self.page
        if drag["moved"]:
            tk = page.find(drag["tid"])
            if isinstance(tk, dict):
                r.set_keyframe(tk, page.t, drag["x"], drag["y"])
                page.persist()
        page.render()


def _shape(tk) -> str:
    """The shape an area is drawn as (``aoeShapeSVG``): a ring, a cone (an angle between 0 and 180), a line; ""
    for a plain circle."""
    shape = get(tk, "shape", _MISSING)
    if r.strictly(shape, "ring"):
        return "ring"
    angle = r.number_of(get(tk, "angle", _MISSING))
    if r.strictly(shape, "cone") and 0 < angle < 180:
        return "cone"
    if r.strictly(shape, "line"):
        return "line"
    return ""


class BuffLane(QWidget):
    """The party buffs' lane (``#buflane``): each buff's bar along the plan's length, lit while the moment is in it;
    or the hint to add one."""

    def __init__(self, page: "RaidPage"):
        super().__init__()
        self.page = page
        self.bars: list[dict] = []
        self.setFixedHeight(24)
        self.setMinimumWidth(60)
        self.setAccessibleName(BUFF_LANE)

    def place(self, bar: dict) -> QRectF:
        inner = QRectF(1, 1, self.width() - 2, self.height() - 2)
        left = inner.left() + inner.width() * bar["left"] / 100
        width = max(3.0, inner.width() * bar["width"] / 100)
        return QRectF(left, inner.top() + 2, width, inner.height() - 4)

    def paintEvent(self, _event) -> None:
        c = theme.COLORS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 5, 5)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), theme.qcolor("inset"))
        if not self.bars:
            painter.setPen(QColor(c["faint"]))
            painter.drawText(QRectF(7, 0, self.width() - 7, self.height()), Qt.AlignVCenter | Qt.AlignLeft, BUFF_LANE_HINT)
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        t = self.page.t
        for bar in self.bars:
            rect = self.place(bar)
            tc = QColor(c["gold"]) if bar["colour"] == r.GOLD else css_colour(bar["colour"])
            on = bar["start"] <= t <= bar["end"]
            painter.setOpacity(1.0 if on else 0.6)
            fill = _mixed(tc, 0.70)
            painter.setBrush(fill if fill is not None else Qt.NoBrush)
            painter.setPen(QPen(tc, 1) if tc is not None else Qt.NoPen)
            painter.drawRoundedRect(rect, 3, 3)
            if on:
                painter.setPen(QPen(QColor(c["gold"]), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)
            painter.setPen(QColor("#0b0f18"))
            painter.save()
            painter.setClipRect(rect.adjusted(5, 0, -5, 0), Qt.IntersectClip)
            painter.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignVCenter | Qt.AlignLeft, bar["name"])
            painter.restore()
        painter.setOpacity(1.0)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(c["line"]), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(box, 5, 5)

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:                    # a bar's ``title``
            point = event.position() if hasattr(event, "position") else QPointF(event.pos())
            tip = next((bar["tip"] for bar in reversed(self.bars) if self.place(bar).contains(point)), "")
            if tip:
                QToolTip.showText(event.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class PlanToast(Toast):
    """raid.js's ``toast``: a word at the foot of the page for 1.8 s."""

    def say(self, words: str) -> None:
        super().say(words)
        self.timer.start(TOAST_MS)


# ------------------------------------------------------------------ the page
def stylesheet() -> str:
    c = theme.COLORS
    return combat_stylesheet() + f"""
        QLabel#rpHead {{ color: {c['gold']}; font-size: 13px; font-weight: 700; margin-top: 8px; }}
        QFrame#rpPanel {{ border: 1px solid {c['line']}; border-radius: 8px; background: {theme.css('panel2')}; }}
        QFrame#rpPanel QLabel, QFrame#rpPanel QCheckBox, QFrame#rpPanel QWidget#plain {{ background: transparent; }}
        QLabel#rpLane {{ color: {c['muted']}; letter-spacing: 1px; }}
        QLabel#rpTime {{ color: {c['muted']}; }}
        QLabel#rpChip {{ background: rgba(233, 203, 128, 0.12); color: {c['gold']}; border: 1px solid {theme.css('frame')};
            border-radius: 3px; padding: 1px 6px; }}
        QPushButton#rpFrame, QPushButton#rpFrameOn {{ text-align: left; }}
        QWidget#rpFrameRow {{ border-left: 3px solid transparent; border-radius: 4px; background: transparent; }}
        QWidget#rpFrameRowOn {{ border-left: 3px solid {c['gold']}; border-radius: 4px; background: rgba(233, 203, 128, 0.16); }}
        QScrollArea#rpFrames {{ background: transparent; border: none; }}
        QPlainTextEdit#rpNotes {{ background: {c['bg2']}; border: 1px solid {c['line2']}; border-radius: 5px; }}
        """


class RaidPage(QWidget):
    """Combat → Raid Planner. ``open_web`` opens a page of the web interface; ``store`` keeps the plans (the app's
    interface data); ``confirm``, ``ask_text``, ``choose_file``, ``save_file``, ``choose_colour`` and ``copy`` stand in
    for the questions, the file and colour dialogs and the clipboard; ``now`` and ``pick`` for the clock and chance."""

    def __init__(self, api: AppApi | None, open_web=None, parent: QWidget | None = None, store=None, confirm=None,
                 ask_text=None, choose_file=None, save_file=None, choose_colour=None, copy=None, now=None, pick=None):
        super().__init__(parent)
        self.api = api
        self.open_web = open_web or (lambda page: None)
        self.store = store if store is not None else interface_store()
        self.confirm = confirm or self._ask
        self.ask_text = ask_text or self._ask_text
        self.choose_file = choose_file or self._ask_file
        self.save_file = save_file or self._ask_where
        self.choose_colour = choose_colour or self._ask_colour
        self.copy = copy or self._copy
        self.now = now or (lambda: int(time.time() * 1000))
        self.pick = pick or random.random
        self.requests = Requests(api, self) if api is not None else None
        # raid.js's ``st``: the plan shown, the moment, the speed, the token selected, playing
        self.id = None
        self.plan: dict | None = None
        self.t = 0.0
        self.speed: float = 1
        self.sel: str | None = None
        self.playing = False
        self.show_list = False                               # Each token opened
        self.mounted = False
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.share_timer = QTimer(self)                      # the plans handed to the app 0.8 s after the last save
        self.share_timer.setSingleShot(True)
        self.share_timer.setInterval(800)
        self.share_timer.timeout.connect(self._share)
        self.frame_rows: list[QWidget] = []
        self.frame_scroll: QScrollArea | None = None
        self.frames_at = None
        self.setStyleSheet(stylesheet())
        self._build()

    # ---------------------------------------------------------------- the frame, drawn once
    def _build(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        page = QVBoxLayout(content)
        page.setContentsMargins(24, 20, 24, 20)
        self.frame = Window(r.TITLE, r.SUBTITLE)
        page.addWidget(self.frame)
        page.addStretch(1)
        body = self.frame.body
        self.header = QVBoxLayout()
        self.header.setSpacing(8)
        body.addLayout(self.header)
        self.columns = QBoxLayout(QBoxLayout.LeftToRight)
        self.columns.setSpacing(16)
        body.addLayout(self.columns)
        left = QWidget()
        left.setObjectName("plain")
        self.left = QVBoxLayout(left)
        self.left.setContentsMargins(0, 0, 0, 0)
        self.left.setSpacing(8)
        self.arena = Arena(self)
        self.left.addWidget(self.arena, 0, Qt.AlignHCenter)
        transport = QWidget()
        transport.setObjectName("plain")
        line = QHBoxLayout(transport)
        line.setContentsMargins(0, 2, 0, 0)
        line.setSpacing(8)
        self.start_button = _button(BACK_TO_START, self.to_start, tip="Back to start")
        self.play_button = _button(PLAY, self.toggle, "primary")
        self.speed_box = _choice([(f"{r.text(x)}×", x) for x in r.SPEEDS], r.SPEEDS.index(1), SPEED_TIP, self._speed)
        self.speed_box.setToolTip(SPEED_TIP)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setAccessibleName(MOMENT)
        self.slider.valueChanged.connect(self._scrubbed)
        self.time_label = _label("", "rpTime", wrap=False)
        for widget in (self.start_button, self.play_button, self.speed_box):
            line.addWidget(widget)
        line.addWidget(self.slider, 1)
        line.addWidget(self.time_label)
        self.left.addWidget(transport)
        lane = QWidget()
        lane.setObjectName("plain")
        lane_line = QHBoxLayout(lane)
        lane_line.setContentsMargins(0, 0, 0, 0)
        lane_line.setSpacing(8)
        head = _label(BUFF_LANE.upper(), "rpLane", wrap=False)
        head.setMinimumWidth(90)                             # ``grid-template-columns: 90px 1fr``, its words whole
        head.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lane_line.addWidget(head)
        self.lane = BuffLane(self)
        lane_line.addWidget(self.lane, 1)
        self.left.addWidget(lane)
        now = QWidget()
        now.setObjectName("plain")
        self.now_line = QHBoxLayout(now)
        self.now_line.setContentsMargins(0, 0, 0, 0)
        self.now_line.setSpacing(5)
        self.left.addWidget(now)
        self.left.addStretch(1)
        self.columns.addWidget(left, 1)
        self.panel = QFrame()
        self.panel.setObjectName("rpPanel")
        self.panel.setFixedWidth(340)
        self.side = QVBoxLayout(self.panel)
        self.side.setContentsMargins(14, 12, 14, 12)
        self.side.setSpacing(6)
        self.columns.addWidget(self.panel, 0, Qt.AlignTop)
        self.toast = PlanToast(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = self.width() >= WIDE
        self.columns.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
        self.panel.setFixedWidth(340) if wide else self.panel.setMaximumWidth(16777215)
        if not wide:
            self.panel.setMinimumWidth(0)
        room = max(160, self.width() - 48 - 28 - (356 if wide else 0) - 2 * Arena.MARGIN)
        self.arena.set_side(min(Arena.SIDE, room))
        for i in range(1, self.left.count()):
            widget = self.left.itemAt(i).widget()
            if widget is not None:
                widget.setMaximumWidth(Arena.SIDE)
        self.toast.place()

    # ---------------------------------------------------------------- opening and leaving (``mount``)
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.mounted:
            self.mount()

    def leave(self) -> None:
        """Another page shown: the playback stops (``the arena gone from the page``); the page opens again on the
        plan it showed."""
        self.pause()
        self.mounted = False

    def mount(self) -> None:
        """``mount``: the playback stopped, the plan shown (or the one last shown, or the newest, or a first plan)
        put in place, the plans handed to the app, then drawn."""
        self.mounted = True
        self.pause()
        self.mount_plan()
        self.share()
        self.render()

    def mount_plan(self) -> None:
        """``mountPlan``: the plan shown kept where it still is, else the next one, else a first plan made."""
        plans = r.raid_plans(self.store)
        if not self.id or not r.yes(plans.get(self.id, _MISSING)):
            self.id = r.next_plan_id(plans, self.id, r.remembered(self.store))
            if not self.id:
                self.id = r.uid(self.pick)
                plans[self.id] = r.new_plan(r.FIRST_PLAN, self.now())
                self.save_plans(plans)
        self.plan = r.raid_plans(self.store).get(self.id)

    # ---------------------------------------------------------------- keeping
    def save_plans(self, plans: dict) -> None:
        """``saveRaidPlans``: kept, then handed to the app for its overlay."""
        r.save_raid_plans(self.store, plans)
        self.share()

    def share(self) -> None:
        """``sharePlans``: the whole set to the app 0.8 s after the last save."""
        if self.requests is not None:
            self.share_timer.start()

    def _share(self) -> None:
        if self.requests is not None:
            self.requests.post("plans", "/api/plans/saved", {"plans": r.raid_plans(self.store)})

    def persist(self) -> None:
        """``persist``: the plan shown kept, its time of saving now."""
        if not self.id or self.plan is None:
            return
        meta = self.plan.get("meta", _MISSING)
        if not r.yes(meta):
            meta = self.plan["meta"] = {}
        if isinstance(meta, dict):
            meta["updated"] = self.now()
        plans = r.raid_plans(self.store)
        plans[self.id] = self.plan
        self.save_plans(plans)

    def find(self, tid):
        """``p.tokens.find((x) => x.id === tid)``."""
        if tid is None:
            return None
        return next((tk for tk in r._list(get(self.plan, "tokens", _MISSING))
                     if r.strictly(get(tk, "id", _MISSING), tid)), None)

    def say(self, words: str) -> None:
        self.toast.say(words)

    # ---------------------------------------------------------------- drawing (``render``)
    def render(self) -> None:
        p = self.plan if self.plan is not None else {}
        self.length = r.num(get(p, "duration", _MISSING)) or 1
        r.remember(self.store, self.id)
        if isinstance(p, dict):
            p["encounter"] = r.clean_encounter(p.get("encounter", _MISSING))
        self._header(p)
        self._side(p)
        self.lane.bars = r.buff_bars(p, self.length)
        top = max(0, math.floor(round(self.length * 10, 6)))
        self.slider.blockSignals(True)
        self.slider.setRange(0, top)
        self.slider.blockSignals(False)
        self._play_words()
        self.show_moment()
        self.arena.update()
        self.lane.update()

    def _header(self, p) -> None:
        _clear(self.header)
        plans = r.raid_plans(self.store)
        ids = r.order(plans)
        chosen = ids.index(self.id) if self.id in ids else 0
        self.plan_box = _choice([(r.plan_label(plans[k]), k) for k in ids], chosen, PLAN, self._chose_plan)
        self.plan_box.setMinimumWidth(206)
        plan_name = _label(PLAN, "small", wrap=False)
        self.header.addWidget(_row(plan_name, self.plan_box, _button(NEW, self.new_plan),
                                   _button(DUPLICATE, self.duplicate), _button(DELETE, self.delete)))
        meta = get(p, "meta", _MISSING)
        self.name_edit = _edit(r.text(get(meta, "name", _MISSING) if r.yes(get(meta, "name", _MISSING)) else ""),
                               NAME_HINT, 229)
        _finished(self.name_edit, lambda v: self._meta("name", v))
        self.author_edit = _edit(r.text(get(meta, "author", _MISSING) if r.yes(get(meta, "author", _MISSING)) else ""),
                                 AUTHOR_HINT, 183, "Author")
        _finished(self.author_edit, lambda v: self._meta("author", v))
        self.length_field = NumberField(self.length, 92)
        self.length_field.setAccessibleName(LENGTH)
        self.length_field.changed.connect(self._length)
        circle = r.strictly(get(get(p, "arena", _MISSING), "kind", _MISSING), "circle")
        self.arena_box = _choice([(w, v) for v, w in ARENAS], 1 if circle else 0, ARENA, self._arena, 110)
        self.header.addWidget(_row(self.name_edit, self.author_edit, _label(LENGTH, "small", wrap=False),
                                   self.length_field, _label(SECONDS, "small", wrap=False),
                                   _label(ARENA, "small", wrap=False), self.arena_box))
        enc = get(p, "encounter", _MISSING)
        self.boss_edit = _edit(r.text(get(enc, "boss", _MISSING)), BOSS_HINT, 206, BOSS)
        _finished(self.boss_edit, lambda v: self._encounter("boss", v))
        npc = get(enc, "npc_id", _MISSING)
        self.npc_field = NumberField(npc if r.yes(npc) else None, 126)
        self.npc_field.setPlaceholderText(NPC_HINT)
        self.npc_field.setAccessibleName(NPC)
        self.npc_field.changed.connect(lambda v: self._encounter("npc_id", v))
        self.header.addWidget(_row(_label(BOSS, "small", wrap=False), self.boss_edit, _label(NPC, "small", wrap=False),
                                   self.npc_field, _label(LINK_NOTE, "faint")))
        self.header.addWidget(_row(_button(EXPORT, self.export), _button(IMPORT, self.import_file),
                                   _button(COPY_CODE, self.copy_code), _button(LOAD_CODE, self.load_code),
                                   _button(OPEN_WEB, lambda: self.open_web("raid"))))
        self.header.addWidget(_label(ON_THE_WEB, "faint"))
        owned = get(r.owners(self.store), self.id, _MISSING) if self.id else _MISSING
        if r.yes(owned):
            url = r.text(get(owned, "url", _MISSING))
            shown = (f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>" if re.match(r"https?://", url, re.I)
                     else html.escape(url))
            link = QLabel(f"{PUBLISHED}{shown} · revision {html.escape(r.text(get(owned, 'revision', _MISSING)))}")
            link.setTextFormat(Qt.RichText)
            link.setOpenExternalLinks(True)
            link.setObjectName("small")
            self.published = link
            self.header.addWidget(link)
        else:
            self.published = None

    def _side(self, p) -> None:
        _clear(self.side)
        self.kind_boxes, self.token_boxes = {}, []
        tokens = r._list(get(p, "tokens", _MISSING))
        sel = self.find(self.sel)
        add_note = _label(ADD_NOTE, "faint")
        self.class_box = _choice([(c, c) for c in r.RAID_CLASSES], 0, "Class of the player to add", lambda i: None)
        self.side.addWidget(_head(ADD))
        self.side.addWidget(_row(self.class_box, _button(ADD_PLAYER, lambda: self.add("player"), "primary")))
        self.side.addWidget(_row(_button(ADD_ENEMY, lambda: self.add("enemy")), _button(ADD_MARKER, lambda: self.add("marker")),
                                 _button(ADD_AOE, lambda: self.add("aoe"))))
        self.side.addWidget(add_note)
        self.side.addWidget(_head(SELECTED))
        self.frame_rows, self.frame_scroll, self.frames_at = [], None, None
        if sel is None:
            self.side.addWidget(_label(SELECT_NOTE, "faint"))
        else:
            self._editor(sel)
        if tokens:
            self._shown(p, tokens)
        self.side.addWidget(_head(BUFFS))
        self._buffs(p)
        self.side.addWidget(_label(PANEL_ELSEWHERE, "faint"))
        self.side.addWidget(_head(NOTES))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("rpNotes")
        self.notes_edit.setPlaceholderText(NOTES_HINT)
        self.notes_edit.setAccessibleName("Notes")
        meta = get(p, "meta", _MISSING)
        notes = get(meta, "notes", _MISSING)
        self.notes_edit.setPlainText(r.text(notes) if r.yes(notes) else "")
        self.notes_edit.setFixedHeight(self.notes_edit.fontMetrics().lineSpacing() * 4 + 14)
        self.notes_edit.kept = self.notes_edit.toPlainText()
        self.notes_edit.installEventFilter(self)
        self.side.addWidget(self.notes_edit)

    def eventFilter(self, watched, event) -> bool:
        if watched is getattr(self, "notes_edit", None) and event.type() == QEvent.FocusOut:
            text = watched.toPlainText()
            if text != watched.kept:                           # ``change``: edited, then left
                watched.kept = text
                self._meta("notes", text)
        return super().eventFilter(watched, event)

    def _editor(self, sel) -> None:
        """The selected token's editor."""
        kind = get(sel, "kind", _MISSING)
        self.label_edit = _edit(r.text(get(sel, "label", _MISSING) if r.yes(get(sel, "label", _MISSING)) else ""),
                                LABEL_HINT, 138)
        _finished(self.label_edit, lambda v: self._token_value("label", v))
        colour = r.colour_field(get(sel, "color", _MISSING))
        self.colour_button = QPushButton()
        self.colour_button.setObjectName("plain")
        self.colour_button.setFixedSize(46, 26)
        self.colour_button.setAccessibleName("Colour")
        self.colour_button.setStyleSheet(f"QPushButton {{ background: {colour}; border: 1px solid {theme.COLORS['line2']}; "
                                         "border-radius: 4px; }")
        self.colour_button.clicked.connect(lambda _c=False, start=colour: self._colour(start))
        parts = [self.label_edit, self.colour_button]
        if r.strictly(kind, "player"):
            cls = get(sel, "cls", _MISSING)
            index = next((i for i, c in enumerate(r.RAID_CLASSES) if r.strictly(c, cls)), 0)
            self.cls_box = _choice([(c, c) for c in r.RAID_CLASSES], index, "Class", self._cls)
            parts.append(self.cls_box)
        self.side.addWidget(_row(*parts))
        if r.strictly(kind, "aoe"):
            radius = get(sel, "radius", _MISSING)
            n = r.number_of(radius if r.yes(radius) else 0.14) * 100
            value = r.js_round(n) if math.isfinite(n) else 27          # a range field's default: its middle
            self.radius_slider = QSlider(Qt.Horizontal)
            self.radius_slider.setRange(4, 50)
            self.radius_slider.setValue(max(4, min(50, value)))
            self.radius_slider.setAccessibleName(RADIUS)
            self.radius_slider.valueChanged.connect(self._radius)
            self.radius_slider.sliderReleased.connect(self.persist)
            line = QWidget()
            line.setObjectName("plain")
            box = QHBoxLayout(line)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(_label(RADIUS, "small", wrap=False))
            box.addWidget(self.radius_slider, 1)
            self.side.addWidget(line)
        self.side.addWidget(_label(r.keyframes_head(sel), "small"))
        rows = r.keyframe_rows(sel)
        if rows:
            holder = QWidget()
            holder.setObjectName("plain")
            column = QVBoxLayout(holder)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            for i, row in enumerate(rows):
                line = QWidget()
                line.setObjectName("rpFrameRow")
                box = QHBoxLayout(line)
                box.setContentsMargins(4, 2, 4, 2)
                box.setSpacing(8)
                box.addWidget(_button(row["time"], lambda go=row["go"]: self.go_to(go)))
                box.addWidget(_label(row["where"], "small", wrap=False))
                box.addStretch(1)
                if row["deletable"]:
                    box.addWidget(_button("✕", lambda i=i: self.delete_frame(i), tip=DELETE_FRAME))
                column.addWidget(line)
                self.frame_rows.append(line)
            scroll = QScrollArea()
            scroll.setObjectName("rpFrames")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(holder)
            scroll.setMaximumHeight(240)
            scroll.setMinimumHeight(min(240, holder.sizeHint().height()))
            self.frame_scroll = scroll
            self.side.addWidget(scroll)
        else:
            self.side.addWidget(_label(NO_FRAMES, "faint"))
        words = r.on_map_words(sel)
        if words is not None:
            self.side.addWidget(_label(words, "small"))
        self.set_button = _button(f"Set position at {r.fixed(r.num(self.t), 1)}s", self.set_here)
        self.side.addWidget(_row(self.set_button))
        self.shown_box = QCheckBox(SHOWN_BOX)
        self.shown_box.setChecked(not r.yes(get(sel, "hidden", _MISSING)))
        self.shown_box.clicked.connect(lambda on: self._hide(self.find(self.sel), not on))
        self.side.addWidget(self.shown_box)
        self.side.addWidget(_row(_button(REMOVE, self.remove_token)))

    def _shown(self, p, tokens) -> None:
        """``SHOWN ON THE MAP``: each kind, ticked when all of it is shown, half when some is; then each token."""
        self.side.addWidget(_head(SHOWN))
        boxes = []
        for g in r.kinds_shown(p):
            box = QCheckBox(f"{g['name']} {g['on']}/{g['all']}")
            box.setAccessibleName(g["name"])
            box.setTristate(True)
            box.setCheckState(Qt.Checked if g["on"] == g["all"] else Qt.PartiallyChecked if g["on"] else Qt.Unchecked)
            box.clicked.connect(lambda _on=False, g=g: self._show_kind(g["kind"], not g["on"] == g["all"]))
            boxes.append(box)
            self.kind_boxes[g["kind"]] = box
        self.side.addWidget(_row(*boxes))
        fold = Fold(EACH, opened=self.show_list)
        fold.button.toggled.connect(lambda on: setattr(self, "show_list", on))
        for tk in tokens:
            line = QWidget()
            line.setObjectName("plain")
            box = QHBoxLayout(line)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(6)
            tick = QCheckBox()
            tick.setChecked(not r.yes(get(tk, "hidden", _MISSING)))
            name = r.token_name(tk)
            tick.setAccessibleName(name)
            tid = r.text(get(tk, "id", _MISSING))
            tick.clicked.connect(lambda on, tid=tid: self._hide(self.find(tid), not on))
            swatch = QLabel()
            swatch.setFixedSize(12, 12)
            tc = css_colour(r.col(get(tk, "color", _MISSING)))
            swatch.setStyleSheet(f"background: {tc.name(QColor.HexArgb) if tc is not None else 'transparent'}; "
                                 "border-radius: 6px;")
            box.addWidget(tick)
            box.addWidget(swatch)
            box.addWidget(_label(name, wrap=False), 1)
            fold.add(line)
            self.token_boxes.append(tick)
        self.side.addWidget(fold)

    def _buffs(self, p) -> None:
        """``PARTY BUFFS``: each buff to edit, then the line to add one."""
        who = r.players(p)
        names = [(r.giver(pl), r.giver_value(pl)) for pl in who]
        buffs = r._list(get(p, "buffs", _MISSING))
        self.buff_rows = []
        if not buffs:
            self.side.addWidget(_label(NO_BUFFS, "faint"))
        for i, bf in enumerate(buffs):
            name = _edit(r.text(get(bf, "name", _MISSING)), "", 126, "Buff name")
            _finished(name, lambda v, i=i: self._buff_value(i, "name", v))
            by = get(bf, "by", _MISSING)
            chosen = 0
            for n, (_words, value) in enumerate(names):
                if r.strictly(value, by):
                    chosen = n + 1                           # the last that matches, as a select keeps it
            values = [""] + [w for w, _v in names]
            giver = _choice([("—", "")] + [(w, w) for w, _v in names], chosen, "Who gives the buff",
                            lambda index, i=i, values=values: self._buff_value(i, "by", values[index]), 103)
            start = NumberField(r.num(get(bf, "start", _MISSING)), 67)
            start.setAccessibleName("Buff starts at (seconds)")
            start.changed.connect(lambda v, i=i: self._buff_value(i, "start", v))
            end = NumberField(r.num(get(bf, "end", _MISSING)), 67)
            end.setAccessibleName("Buff ends at (seconds)")
            end.changed.connect(lambda v, i=i: self._buff_value(i, "end", v))
            remove = _button("✕", lambda i=i: self.remove_buff(i))
            remove.setAccessibleName("Remove buff")
            self.side.addWidget(_row(name, giver, start, _label("–", "faint", wrap=False), end, remove))
            self.buff_rows.append({"name": name, "by": giver, "start": start, "end": end, "remove": remove})
        self.buff_name = _edit("", BUFF_HINT, 126)
        self.buff_by = _choice([(SOURCE, "")] + [(w, w) for w, _v in names], 0, "Who gives the buff", lambda i: None, 103)
        self.buff_start = NumberField(0, 60)
        self.buff_start.setAccessibleName("Buff starts at (seconds)")
        self.buff_end = NumberField(10, 60)
        self.buff_end.setAccessibleName("Buff ends at (seconds)")
        self.side.addWidget(_row(self.buff_name, self.buff_by, self.buff_start, _label("–", "faint", wrap=False),
                                 self.buff_end, _button(ADD_BUFF, self.add_buff)))

    # ---------------------------------------------------------------- the moment (``layout``)
    def show_moment(self) -> None:
        """``layout``: the map, the path, the keyframe the moment is at, the time, the slider, the buffs on."""
        p = self.plan if self.plan is not None else {}
        t = self.t
        self.arena.update()
        self.lane.update()
        self.time_label.setText(r.time_words(t, p))
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(r.js_round(r.slider_step(t, self.length) * 10))
            self.slider.blockSignals(False)
        sel = self.find(self.sel)
        at = r.current_keyframe(sel, t) if sel is not None else -1
        if self.frame_rows and self.frames_at != at:
            self.frames_at = at
            for i, row in enumerate(self.frame_rows):
                row.setObjectName("rpFrameRowOn" if i == at else "rpFrameRow")
                row.setAccessibleDescription("current" if i == at else "")
                row.style().unpolish(row)
                row.style().polish(row)
            if self.frame_scroll is not None:
                bar = self.frame_scroll.verticalScrollBar()
                if not 0 <= at < len(self.frame_rows):
                    bar.setValue(0)
                else:
                    row = self.frame_rows[at]
                    view = self.frame_scroll.viewport().height()
                    if row.y() < bar.value() or row.y() + row.height() > bar.value() + view:
                        bar.setValue(max(0, int(row.y() - view / 3)))
        _clear(self.now_line)
        self.now_line.addWidget(_label(BUFFS_NOW, "small", wrap=False))
        chips = r.buffs_now(p, t)
        for words in chips:
            self.now_line.addWidget(_label(words, "rpChip", wrap=False))
        if not chips:
            self.now_line.addWidget(_label(NONE_NOW, "faint", wrap=False))
        self.now_line.addStretch(1)
        self.now_words = chips

    def _play_words(self) -> None:
        self.play_button.setText(PAUSE if self.playing else PLAY)
        self.play_button.setAccessibleName(PAUSE if self.playing else PLAY)

    # ---------------------------------------------------------------- playing (``play``, ``pause``)
    def toggle(self) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        self.playing = True
        self._play_words()
        if not self.timer.isActive():
            self.timer.start()

    def pause(self) -> None:
        self.timer.stop()
        self.playing = False
        self._play_words()

    def _tick(self) -> None:
        if not self.isVisible():
            self.pause()
            return
        self.t = r.js_round((self.t + 0.05 * (self.speed or 1)) * 100) / 100
        end = r.num(get(self.plan, "duration", _MISSING)) or 1
        if self.t >= end:
            self.t = end
            self.show_moment()
            self.pause()
            return
        self.show_moment()

    def to_start(self) -> None:
        self.t = 0.0
        self.show_moment()

    def go_to(self, t: float) -> None:
        """A keyframe's moment (``data-kgo``)."""
        self.t = t
        self.show_moment()

    def _speed(self, index: int) -> None:
        self.speed = self.speed_box.itemData(index)

    def _scrubbed(self, value: int) -> None:
        """The slider moved (``input``): the playback paused, the moment taken from it."""
        if self.playing:
            self.pause()
        self.t = value / 10
        self.show_moment()

    # ---------------------------------------------------------------- the plans (``reload`` and the header)
    def reload(self) -> None:
        self.plan = r.raid_plans(self.store).get(self.id)
        self.sel, self.t = None, 0.0
        self.render()

    def _chose_plan(self, index: int) -> None:
        self.id = self.plan_box.itemData(index)
        self.reload()

    def new_plan(self) -> None:
        plans, key = r.raid_plans(self.store), r.uid(self.pick)
        plans[key] = r.new_plan(r.NEW_PLAN, self.now())
        self.save_plans(plans)
        self.id = key
        self.reload()

    def duplicate(self) -> None:
        p = self.plan or {}
        plans, key, copy = r.raid_plans(self.store), r.uid(self.pick), b.copy(p)
        meta = copy.get("meta", _MISSING)
        if not isinstance(meta, dict):                           # ``copy.meta.name = …`` throws: nothing happens
            return
        name = get(get(p, "meta", _MISSING), "name", _MISSING)
        meta["name"] = (r.text(name) if r.yes(name) else "Plan") + " copy"
        meta["created"] = meta["updated"] = self.now()
        plans[key] = copy
        self.save_plans(plans)
        self.id = key
        self.reload()

    def delete(self) -> None:
        if not self.confirm(ASK_DELETE):
            return
        plans = r.raid_plans(self.store)
        plans.pop(self.id, None)
        self.save_plans(plans)
        self.id, self.plan = None, None
        self.mount_plan()
        self.render()

    def _meta(self, key: str, value: str) -> None:
        meta = get(self.plan, "meta", _MISSING)
        if isinstance(meta, dict):
            meta[key] = value
            self.persist()

    def _length(self, value: str) -> None:
        n = r.number_of(value)
        self.plan["duration"] = r._plain(r.js_max(5.0, n if r.yes(n) else 60.0))
        self.persist()
        self.render()

    def _arena(self, index: int) -> None:
        arena = get(self.plan, "arena", _MISSING)
        if isinstance(arena, dict):                               # ``p.arena.kind = …`` throws with none
            arena["kind"] = self.arena_box.itemData(index)
            self.persist()
            self.render()

    def _encounter(self, key: str, value: str) -> None:
        enc = dict(get(self.plan, "encounter", _MISSING) if isinstance(get(self.plan, "encounter", _MISSING), dict) else {})
        enc[key] = value
        self.plan["encounter"] = r.clean_encounter(enc)
        self.persist()

    def export(self) -> None:
        """Export file: the plan as an .a2plan (its JSON, indented two)."""
        path = self.save_file(r.export_name(self.plan or {}))
        if path:
            with open(path, "w", encoding="utf-8", newline="") as file:
                file.write(b.stringify(self.plan or {}, 2))

    def import_file(self) -> None:
        """Import file: a plan, or a private ownership backup (its plan kept, and its credential)."""
        path = self.choose_file()
        if not path:
            return
        try:
            with open(path, "rb") as file:
                doc = js_parse(file.read())
            if doc is None:
                raise r.PlanError("Cannot read properties of null (reading 'format')")
            kind = get(doc, "format", _MISSING)
            if r.strictly(kind, "a2plan-owner"):
                owner, plan = r.ownership(doc)
                self._imported(plan)
                r.save_owner(self.store, owner, self.id)
            elif r.strictly(kind, "a2log"):
                self.say(MOVEMENT_ELSEWHERE)
                return
            else:
                if not r.strictly(kind, "a2plan") or not isinstance(doc, dict):
                    raise r.PlanError(r.NOT_A_PLAN)
                self._imported(doc)
            self.render()
            self.say(IMPORTED)
        except (OSError, ValueError, RecursionError) as problem:
            self.say(str(problem))

    def _imported(self, p) -> None:
        """``importDoc``: kept as a new plan, and shown."""
        if not isinstance(p, dict):
            raise r.PlanError("Cannot set properties of " + ("null" if p is None else "undefined") + " (setting 'meta')")
        plans = r.raid_plans(self.store)
        key = r.import_doc(p, plans, self.now(), make_id=lambda: r.uid(self.pick))
        self.save_plans(plans)
        self.id, self.plan, self.sel, self.t = key, p, None, 0.0

    def copy_code(self) -> None:
        try:
            self.copy(r.plan_code(self.plan or {}))
            self.say(COPIED)
        except Exception:                                      # noqa: BLE001 - a clipboard that refused
            self.say(COPY_FAILED)

    def load_code(self) -> None:
        code = self.ask_text(ASK_CODE)
        if not code:
            return
        try:
            self._imported(r.plan_from_code(code))
            self.render()
            self.say(LOADED)
        except (ValueError, RecursionError) as problem:
            self.say(str(problem))

    # ---------------------------------------------------------------- tokens
    def add(self, kind: str) -> None:
        """``+ Player`` (of the class chosen), ``+ Enemy``, ``+ Marker`` or ``+ AoE``: near the middle at the start,
        and selected."""
        p = self.plan
        tk = r.new_token(kind, p, self.class_box.currentData() if kind == "player" else "", make_id=lambda: r.uid(self.pick))
        r.set_keyframe(tk, 0, 0.5 + (self.pick() - 0.5) * 0.3, 0.5 + (self.pick() - 0.5) * 0.3)
        p.setdefault("tokens", [])
        if not isinstance(p["tokens"], list):
            p["tokens"] = []
        p["tokens"].append(tk)
        self.sel = tk["id"]
        self.persist()
        self.render()

    def _token_value(self, key: str, value) -> None:
        tk = self.find(self.sel)
        if isinstance(tk, dict):
            tk[key] = value
            self.persist()
            self.render()

    def _colour(self, start: str) -> None:
        chosen = self.choose_colour(start)
        if chosen and chosen.lower() != start.lower():           # ``change``: a colour other than the one shown
            self._token_value("color", chosen.lower())

    def _cls(self, index: int) -> None:
        tk = self.find(self.sel)
        if not isinstance(tk, dict):
            return
        value = self.cls_box.itemData(index)
        tk["cls"] = value
        label = tk.get("label", _MISSING)
        if not r.yes(label) or any(r.strictly(label, c) for c in r.RAID_CLASSES):
            tk["label"] = value
        self.persist()
        self.render()

    def _radius(self, value: int) -> None:
        """The radius slider moved (``input``): the area drawn at it; kept when let go (``change``)."""
        tk = self.find(self.sel)
        if isinstance(tk, dict):
            tk["radius"] = value / 100
            self.show_moment()
            if not self.radius_slider.isSliderDown():
                self.persist()

    def set_here(self) -> None:
        """Set position at the moment shown: where the token is then."""
        tk = self.find(self.sel)
        if not isinstance(tk, dict):
            return
        place = r.position(tk, self.t) or (0.5, 0.5)
        r.set_keyframe(tk, self.t, place[0], place[1])
        self.persist()
        self.render()

    def delete_frame(self, index: int) -> None:
        tk = self.find(self.sel)
        if isinstance(tk, dict) and isinstance(tk.get("keyframes"), list) and index < len(tk["keyframes"]):
            del tk["keyframes"][index]
            self.persist()
            self.render()

    def remove_token(self) -> None:
        p = self.plan
        p["tokens"] = [x for x in r._list(get(p, "tokens", _MISSING)) if not r.strictly(get(x, "id", _MISSING), self.sel)]
        self.sel = None
        self.persist()
        self.render()

    def _hide(self, tk, hide: bool) -> None:
        """``setHidden``: a token not drawn, here, in the overlay's playback or for whoever opens the plan."""
        if not isinstance(tk, dict):
            return
        if hide:
            tk["hidden"] = True
        else:
            tk.pop("hidden", None)
        self.persist()
        self.render()

    def _show_kind(self, kind: str, show: bool) -> None:
        for tk in r._list(get(self.plan, "tokens", _MISSING)):
            if isinstance(tk, dict) and r.strictly(get(tk, "kind", _MISSING), kind):
                if show:
                    tk.pop("hidden", None)
                else:
                    tk["hidden"] = True
        self.persist()
        self.render()

    # ---------------------------------------------------------------- buffs
    def _buff_value(self, index: int, key: str, value) -> None:
        buffs = r._list(get(self.plan, "buffs", _MISSING))
        if index >= len(buffs) or not isinstance(buffs[index], dict):
            return
        if key in ("start", "end"):
            n = r.number_of(value)
            value = r._plain(n) if r.yes(n) else 0
        buffs[index][key] = value
        self.persist()
        self.render()

    def remove_buff(self, index: int) -> None:
        buffs = r._list(get(self.plan, "buffs", _MISSING))
        if index < len(buffs):
            del buffs[index]
            self.persist()
            self.render()

    def add_buff(self) -> None:
        name = r.js_trim(self.buff_name.text())
        if not name:
            self.say(NAME_BUFF)
            return

        def number(field):
            n = r.number_of(field.value())
            return r._plain(n) if r.yes(n) else 0
        p = self.plan
        if not isinstance(p.get("buffs"), list):
            p["buffs"] = []
        p["buffs"].append({"id": r.uid(self.pick), "name": name, "by": self.buff_by.currentData() or "",
                           "start": number(self.buff_start), "end": number(self.buff_end), "note": ""})
        self.persist()
        self.render()

    # ---------------------------------------------------------------- the computer's dialogs
    def _ask(self, words: str) -> bool:
        return QMessageBox.question(self, "Aion 2 Calc", words) == QMessageBox.Yes

    def _ask_text(self, words: str) -> str:
        text, ok = QInputDialog.getText(self, "Aion 2 Calc", words)
        return text if ok else ""

    def _ask_file(self) -> str:
        path, _kind = QFileDialog.getOpenFileName(self, IMPORT, "", "Plans (*.json *.a2plan *.a2log)")
        return path

    def _ask_where(self, name: str) -> str:
        """Where the plan is saved, the computer's Downloads folder offered (where a browser puts a download)."""
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        path, _kind = QFileDialog.getSaveFileName(self, EXPORT, os.path.join(folder, name), "Plan (*.a2plan)")
        return path

    def _ask_colour(self, start: str) -> str:
        colour = QColorDialog.getColor(QColor(start), self, "Colour")
        return colour.name() if colour.isValid() else ""

    @staticmethod
    def _copy(words: str) -> None:
        QGuiApplication.clipboard().setText(words)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)
