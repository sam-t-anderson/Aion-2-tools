"""A build's result windows in the native interface (0.2.434), as pages/results.js's ``renderWindows`` draws them for
the Build Planner, My Character and Saved Results: the side menu of the ten windows and the window chosen.

The native interface draws the Overview (its counts, notes, stat priority, damage and healing shares), Skills (active
and passive, each skill's level and supporting effects) and Stigma windows, and since 0.2.435 the Daevanion window
(each board's nodes, the points used, and the skill levels and stats the boards give) and the Equipment window (the
paper doll's slots, the rolls to keep and where an enchant level is worth most), and since 0.2.436 the Arcana window
(a character's cards, the variant for each slot and the value of each slot's skill rolls, with the deity totals) and
the Titles, wings & pet window, since 0.2.437 the Skills hotbar (its rows of keys) and the Macro & rotation window
(the macro's lines, the manual skills and the priority list), and since 0.2.438 the Pet Genus window (each genus's
Insight ring and lines, what to roll for, the coverage and the roll targets): every window of a result. The words are
``results.py``'s.
"""
from __future__ import annotations

import html
import math
import urllib.parse

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics, QFontMetricsF, QGuiApplication, QLinearGradient,
                           QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF, QRadialGradient, QTextLayout,
                           QTextOption)
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton,
                               QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget)

from . import pictures
from . import results as r
from . import theme
from .chrome import FlowLayout
from .database_page import Icons, Kpi, Window, pairs_grid
from .gathering_page import table
from .timers_page import Fold

COMPARISON_NOTE = "Generating a comparison is on the web page for now."
#: A window's two- and three-column parts take one column at this width or less (app.css's 1100 px breakpoint, where
#: ``.daev``, ``.paperdoll`` and ``.grid2`` stack, less the page's margins and the windows' menu).
NARROW = 780
MACRO_NARROW = 730                                       # .macro-layout stacks under 1050 px
ICON_BG = "#0b0f18"                                      # --icon-bg: a node's words, a picture's ground
BOARD_LIGHT, BOARD_DARK = "#18233a", "#0a0f19"           # --board-a, --board-b
INSET = QColor(6, 9, 15, 166)                            # --inset


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def _plain() -> QWidget:
    box = QWidget()
    box.setObjectName("plain")
    return box


def _note(rich_text: str) -> QFrame:
    """A note (``.note``): rich text in its gold-edged box."""
    box = QFrame()
    box.setObjectName("note")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    text = _label(rich_text, rich=True)
    text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(text)
    return box


def _rich_counter(words: str, figure: str) -> QLabel:
    """A counter (``.counter``): its words muted, then its figure, in its box."""
    label = _label(f"<span style='color: {theme.COLORS['muted']}; font-weight: 600;'>{html.escape(words)}</span>"
                   f"&nbsp;&nbsp;{html.escape(figure)}", "counter", rich=True, wrap=False)
    label.setAccessibleName(f"{words} {figure}")
    return label


def icon_path(url) -> str:
    """The app's cached copy of a picture (app.js ``icon``): a path on metabot.gg is that site's."""
    if not url:
        return ""
    url = str(url)
    return "/api/icon?u=" + urllib.parse.quote("https://metabot.gg" + url if url.startswith("/") else url, safe="")


class Bar(QWidget):
    """A bar (``.bar``): 18 px, filled to ``share`` per cent in the accent's gradient, with its words on it."""

    def __init__(self, share: float, words: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.share, self.words = max(0.0, min(100.0, share)), words
        self.setFixedHeight(18)
        self.setMinimumWidth(120)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QPainterPath()
        track.addRoundedRect(QRectF(self.rect()), 3, 3)
        painter.fillPath(track, QColor(6, 9, 15, 166))
        width = self.width() * self.share / 100
        if width > 0:
            painter.setClipPath(track)
            fill = QLinearGradient(0, 0, width, 0)
            fill.setColorAt(0, QColor("#2a8fb0"))
            fill.setColorAt(1, QColor("#39c2e0"))
            painter.fillRect(QRectF(0, 0, width, self.height()), fill)
        if self.words:
            font = QFont(self.font())
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(theme.COLORS["text"]))
            painter.drawText(QRectF(6, 0, self.width() - 6, self.height()), int(Qt.AlignLeft | Qt.AlignVCenter), self.words)
        painter.end()


def bar_rows(rows: list[tuple[str, str, float]], words_on_bar: bool) -> QWidget:
    """Rows of a figure and its bar (``table.t`` with ``.bar``): the stat priority's label, gain and bar, or a share's
    name and its bar with its percent on it."""
    box = _plain()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(0)
    for index, (name, value, share) in enumerate(rows):
        cell = QFrame()
        cell.setObjectName("barRow")
        line = QHBoxLayout(cell)
        line.setContentsMargins(8, 5, 8, 5)
        line.setSpacing(10)
        line.addWidget(_label(name), 3)
        if not words_on_bar:
            figure = _label(value, "figure", wrap=False)
            figure.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line.addWidget(figure, 0)
        line.addWidget(Bar(share, value if words_on_bar else ""), 4)
        grid.addWidget(cell, index, 0)
    return box


class SkillIcon(QWidget):
    """A skill's picture (``.icon``) in its square with its level (``.lv``) at the corner."""

    def __init__(self, size: int, level: str = "", parent: QWidget | None = None, placeholder: str = "",
                 badge: int = 12):
        super().__init__(parent)
        self.level, self.pixmap = level, None
        self.placeholder, self.badge = placeholder, badge      # ``.asset-placeholder``: drawn until a picture is read
        self.path = ""
        self.setFixedSize(size, size)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self.pixmap = pixmap
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 5, 5)
        painter.fillPath(frame, QColor(theme.COLORS["bg0"]))
        if self.pixmap is not None and not self.pixmap.isNull():
            painter.save()
            painter.setClipPath(frame)
            shown = self.pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap((self.width() - shown.width()) // 2, (self.height() - shown.height()) // 2, shown)
            painter.restore()
        elif self.placeholder:
            font = QFont(self.font())
            font.setPixelSize(16)
            painter.setFont(font)
            painter.setPen(QColor(theme.COLORS["gold"]))
            painter.drawText(QRectF(self.rect()), int(Qt.AlignCenter), self.placeholder)
        painter.setPen(QColor(theme.COLORS["line2"]))
        painter.drawPath(frame)
        if self.level:
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(self.badge)
            painter.setFont(font)
            width = painter.fontMetrics().horizontalAdvance(self.level) + 8
            height = painter.fontMetrics().height()
            badge = QRectF(1, self.height() - height - 1, width, height)
            painter.fillRect(badge, QColor(0, 0, 0, 184))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge, int(Qt.AlignCenter), self.level)
        painter.end()


def _whole(value) -> int:
    """A grid line as the board's CSS reads it: a whole number (up to a thousand), else none (0)."""
    number = r._number(value)
    return int(number) if number is not None and number.is_integer() and 0 < number <= 1000 else 0


def _shape(rect: QRectF, shape: str, radius: float = 4) -> QPainterPath:
    """A node's outline: a skill level's circle, the start's hexagon (``clip-path``), a stat's rounded square."""
    path = QPainterPath()
    if shape == "skill":
        path.addEllipse(rect)
    elif shape == "start":
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        path.addPolygon(QPolygonF([QPointF(x + 0.25 * w, y + 0.05 * h), QPointF(x + 0.75 * w, y + 0.05 * h),
                                   QPointF(x + w, y + 0.5 * h), QPointF(x + 0.75 * w, y + 0.95 * h),
                                   QPointF(x + 0.25 * w, y + 0.95 * h), QPointF(x, y + 0.5 * h)]))
        path.closeSubpath()
    else:
        path.addRoundedRect(rect, radius, radius)
    return path


def _glow(painter: QPainter, rect: QRectF, shape: str) -> None:
    """A taken node's light (``.node.sel``'s shadows): a gold glow blurred over 12 px, under a 2 px white ring."""
    painter.save()
    painter.setBrush(Qt.NoBrush)
    for step in range(12):
        reach = step + 0.5                                 # a blurred edge fades as the normal curve's tail (sigma 6 px)
        alpha = 0.55 * 0.5 * math.erfc(reach / 6 / math.sqrt(2))
        painter.setPen(QPen(QColor(233, 203, 128, round(255 * alpha)), 1))
        painter.drawPath(_shape(rect.adjusted(-reach, -reach, reach, reach), shape, 4 + reach))
    painter.setPen(QPen(QColor(255, 255, 255, 191), 2))
    painter.drawPath(_shape(rect.adjusted(-1, -1, 1, 1), shape, 5))
    painter.restore()


def _cover(painter: QPainter, target: QRectF, pixmap: QPixmap) -> None:
    """A picture filling ``target`` without changing its shape, its middle kept (``object-fit: cover``)."""
    source = QRectF(pixmap.rect())
    if source.isEmpty():
        return
    scale = max(target.width() / source.width(), target.height() / source.height())
    width, height = target.width() / scale, target.height() / scale
    painter.drawPixmap(target, pixmap, QRectF(source.center().x() - width / 2, source.center().y() - height / 2,
                                              width, height))


class NodeBoard(QWidget):
    """A Daevanion board (``.board``), in its frame's padding: its nodes on a grid of 34 px squares 5 px apart, each in
    its grade's colour; those the build takes bright, ringed and glowing, the others dim; a skill level a circle with
    its skill's picture (its initials until the picture is read), the start a hexagon. A node's words are its tooltip.
    The board is drawn once and kept until a picture arrives."""

    CELL, STEP, PAD = 34, 39, 14

    def __init__(self, board: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.name = r.js_text(board.get("name"))
        self.nodes: list[tuple[dict, QRectF]] = []
        rows, cols = _whole(board.get("rows")), _whole(board.get("cols"))
        for nd in r.board_nodes(board):
            row, col = _whole(nd.get("row")), _whole(nd.get("col"))
            if not row or not col:
                continue                                   # a node without its place on the grid (the app makes none)
            rows, cols = max(rows, row), max(cols, col)
            self.nodes.append((nd, QRectF(self.PAD + (col - 1) * self.STEP, self.PAD + (row - 1) * self.STEP,
                                          self.CELL, self.CELL)))
        self.wanted = {icon_path(r.node_icon(nd)) for nd, _rect in self.nodes if r.node_icon(nd)}
        self.pictures: dict[str, QPixmap] = {}
        self._cache: QPixmap | None = None
        self.setFixedSize(max(0, cols * self.STEP - 5) + 2 * self.PAD, max(0, rows * self.STEP - 5) + 2 * self.PAD)
        self.setAccessibleName(f"{self.name} board")

    def picture(self, path: str, pixmap: QPixmap) -> None:
        if path in self.wanted:
            self.pictures[path] = pixmap
            self._cache = None
            self.update()

    def node_at(self, point: QPointF) -> dict | None:
        for nd, rect in reversed(self.nodes):             # the one drawn last is on top
            shape = r.node_shape(nd)
            if shape != "none" and _shape(rect, shape).contains(point):
                return nd
        return None

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            nd = self.node_at(QPointF(event.pos()))
            if nd is None:
                QToolTip.hideText()
                event.ignore()
            else:
                QToolTip.showText(event.globalPos(), r.node_tip(nd), self)
            return True
        return super().event(event)

    def paintEvent(self, _event) -> None:
        ratio = self.devicePixelRatioF()
        if self._cache is None or self._cache.devicePixelRatio() != ratio:
            self._cache = QPixmap(round(self.width() * ratio), round(self.height() * ratio))
            self._cache.setDevicePixelRatio(ratio)
            self._cache.fill(Qt.transparent)
            painter = QPainter(self._cache)
            self._draw(painter, ratio)
            painter.end()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)
        painter.end()

    def _draw(self, painter: QPainter, ratio: float) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, -0.2)
        for nd, rect in self.nodes:
            shape = r.node_shape(nd)
            if shape == "none":
                continue                                   # .node.none: its place kept, nothing drawn
            lit = r.node_lit(nd)
            if lit and shape != "start":                   # the start's hexagon cuts its own light away
                _glow(painter, rect, shape)
            painter.setOpacity(1.0 if lit else 0.38)       # the whole node at once, as CSS's opacity does
            painter.drawPixmap(rect.topLeft(), self._node(nd, shape, font, ratio))
            painter.setOpacity(1.0)

    def _node(self, nd: dict, shape: str, font: QFont, ratio: float) -> QPixmap:
        """One node, at full strength: its colour, its faint edge, its words and its picture."""
        image = QPixmap(round(self.CELL * ratio), round(self.CELL * ratio))
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(0, 0, self.CELL, self.CELL)
        painter.fillPath(_shape(rect, shape), QColor(r.node_fill(nd)))
        if shape != "start":                               # the hexagon cuts its square's edge away
            painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(_shape(rect.adjusted(0.5, 0.5, -0.5, -0.5), shape, 3.5))
        inner = rect.adjusted(1, 1, -1, -1)
        text = r.node_text(nd)
        if text:
            painter.save()
            painter.setClipPath(_shape(inner, shape, 3))
            painter.setFont(font)
            painter.setPen(QColor(ICON_BG))
            wide = QFontMetricsF(font).horizontalAdvance(text) > inner.width()   # wider: from its left, cut at its right
            painter.drawText(inner, int((Qt.AlignLeft if wide else Qt.AlignHCenter) | Qt.AlignVCenter), text)
            painter.restore()
        pixmap = self.pictures.get(icon_path(r.node_icon(nd))) if shape == "skill" else None
        if pixmap is not None and not pixmap.isNull():
            spot = QRectF(4, 4, 26, 26)                    # .node-skill-icon: 26 px, 3 px inside the edge, round
            clip = QPainterPath()
            clip.addEllipse(spot)
            painter.setClipPath(clip)
            _cover(painter, spot, pixmap)
        painter.end()
        return image


class BoardFrame(QFrame):
    """The board's frame (``.board-wrap``): a dark radial glow from its middle within its line and rounded corners, the
    board in its middle, scrolled across when the frame is narrower than the board."""

    def __init__(self, board: NodeBoard, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("boardWrap")
        self.board = board
        self.scroll = QScrollArea()
        self.scroll.setObjectName("boardScroll")
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(board)
        board.setAutoFillBackground(False)                 # set by setWidget; the frame's light shows round the nodes
        self.scroll.viewport().setObjectName("boardView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self.scroll)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._fit()

    def _fit(self) -> None:
        """The board's height, and the scroll bar's under it when the board is wider than the frame."""
        across = self.board.width() > self.width() - 2
        height = self.board.height() + (self.scroll.horizontalScrollBar().sizeHint().height() if across else 0)
        if self.scroll.minimumHeight() != height or self.scroll.maximumHeight() != height:
            self.scroll.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        outline = QPainterPath()
        outline.addRoundedRect(rect, 6, 6)
        light = QRadialGradient(rect.center(), max(1.0, 0.7 * math.hypot(self.width() / 2, self.height() / 2)))
        light.setColorAt(0, QColor(BOARD_LIGHT))
        light.setColorAt(1, QColor(BOARD_DARK))
        painter.fillPath(outline, light)
        painter.setPen(QPen(QColor(theme.COLORS["line"]), 1))
        painter.drawPath(outline)
        painter.end()


class BoardTab(QPushButton):
    """A board's tab (``.tabs button``): its name, then its points used of its total, faint; the chosen one gold."""

    def __init__(self, name: str, count: str, chosen: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tabOn" if chosen else "tab")
        self.setAccessibleName(f"{name} {count}")
        self.setCursor(Qt.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(15, 8, 15, 8)              # the tab's padding, and its edge
        line.setSpacing(4)
        for words, kind in ((name, "tabName"), (count, "tabCount")):
            label = _label(words, kind, wrap=False)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            line.addWidget(label)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.layout().sizeHint()


class Swatch(QWidget):
    """A colour in the board's key (``.legend i``): a 12 px square, its corners rounded."""

    def __init__(self, colour: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.colour = QColor(colour)
        self.setFixedSize(12, 12)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()), 3, 3)
        painter.fillPath(outline, self.colour)
        painter.end()


def _legend() -> QWidget:
    """The board's key (``.legend``): each grade's colour and cost, then what the shapes mean."""
    box = _plain()
    flow = FlowLayout(box, align=Qt.AlignLeft, gap=(12, 12))
    for colour, words in r.LEGEND:
        item = _plain()
        line = QHBoxLayout(item)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        line.addWidget(Swatch(colour), 0, Qt.AlignVCenter)
        line.addWidget(_label(words, "muted", wrap=False))
        flow.addWidget(item)
    flow.addWidget(_label(r.LEGEND_NOTE, "muted", wrap=False))
    return box


class Split(QWidget):
    """A window's parts side by side, one under another when the window is narrow (``.daev``, ``.paperdoll`` and
    ``.grid2``, which app.css stacks under its 1100 px breakpoint; ``.macro-layout`` under 1050 px). ``widths`` holds
    each part's width side by side: a width, 0 for an equal share of the rest, or the least and most it takes before
    the others share the rest (``minmax``). ``top`` keeps the parts at their own heights (``align-items: start``)."""

    def __init__(self, parts: list[QWidget], widths: list, gap: int, parent: QWidget | None = None,
                 narrow_at: int = NARROW, top: bool = False):
        super().__init__(parent)
        self.setObjectName("plain")
        self.parts, self.widths, self.narrow_at, self.top = parts, widths, narrow_at, top
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(gap)
        self.narrow: bool | None = None
        self.place(False)

    def place(self, narrow: bool) -> None:
        if narrow == self.narrow:
            return
        self.narrow = narrow
        for part in self.parts:
            self.grid.removeWidget(part)
        for index in range(len(self.parts)):
            self.grid.setColumnStretch(index, 0)
        align = Qt.AlignTop if self.top else Qt.Alignment()
        for index, (part, width) in enumerate(zip(self.parts, self.widths)):
            if narrow:
                part.setMinimumWidth(0)
                part.setMaximumWidth(16777215)
                self.grid.addWidget(part, index, 0, align)
            else:
                if isinstance(width, tuple):                 # its least and most, before the others share the rest
                    part.setMinimumWidth(width[0])
                    part.setMaximumWidth(width[1])
                    stretch = 100
                elif width:
                    part.setFixedWidth(width)
                    stretch = 0
                else:
                    stretch = 1
                self.grid.addWidget(part, 0, index, align)
                self.grid.setColumnStretch(index, stretch)
        if narrow:
            self.grid.setColumnStretch(0, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(event.size().width() <= self.narrow_at)


class SlotTile(QFrame):
    """A slot (``.slot``): its picture (an item's with its enchant level), the slot, the item in its grade's colour (a
    pet's level after it), its stats, its rolls, stones and skill levels as chips, and where it comes from; a 3 px
    edge on its left in the grade's colour. The paper doll's slots, and the titles, wings and pet."""

    def __init__(self, slot: str, item: str, grade: str, stats: str, icon: QWidget, chips=(), source: str = "",
                 level: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("slotTile")
        self.grade = grade
        self.edge = _css_colour(r.GRADES[grade]) if grade else QColor(theme.COLORS["line2"])
        self.setMinimumHeight(52)
        row = QHBoxLayout(self)
        row.setContentsMargins(11, 7, 9, 7)                # 6 px 8 px inside its edges (the left one 3 px)
        row.setSpacing(16)                                 # the picture's 42 px column (34 px used), then 8 px
        row.addWidget(icon, 0, Qt.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(1)
        words.addWidget(_label(slot.upper(), "slotName"))
        if level:
            words.addWidget(_label(f"{html.escape(item)} <span style='color: {theme.COLORS['muted']};'>"
                                   f"{html.escape(level)}</span>", "gname" + grade, rich=True))
        else:
            words.addWidget(_label(item, "gname" + grade))
        if stats:
            words.addWidget(_label(stats, "slotStats", rich=True))
        if chips:
            holder = _plain()
            flow = FlowLayout(holder, align=Qt.AlignLeft, gap=(3, 2), centre=False)
            for kind, text in chips:
                chip = _label(text, {"chip": "chip", "manastone": "chipGold", "gold": "chipGold", "skill": "chipSkill"}[kind],
                              wrap=False)
                if kind == "manastone":
                    chip.setToolTip("Manastone")
                flow.addWidget(chip)
            words.addWidget(holder)
        if source:
            words.addWidget(_label(source, "faint"))
        row.addLayout(words, 1)

    @classmethod
    def of(cls, s: dict, icon: QWidget) -> "SlotTile":
        """A slot of the paper doll (``slotTile``): its first four stats, its chips and its source."""
        return cls(r.js_text(s.get("slot")), r.slot_item(s), r.slot_grade(s), r.slot_stats(s), icon, r.slot_extras(s),
                   r.js_text(s.get("source")) if s.get("source") else "")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        outline = QPainterPath()
        outline.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        painter.fillPath(outline, QColor(theme.COLORS["panel2"]))
        painter.setPen(QPen(QColor(theme.COLORS["line"]), 1))
        painter.drawPath(outline)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 5, 5)
        painter.setClipPath(clip)
        painter.fillRect(QRectF(0, 0, 3, rect.height()), self.edge)
        painter.end()


def _table(headers: list[str], rows: list[list[str]], right: tuple[int, ...] = (), stretch: int = 0):
    """A table of every row (``table.t``; the Gathering page's), its rows as tall as their words once its columns have
    their widths."""
    widget = table(headers, rows, right, stretch)
    widget.horizontalHeader().sectionResized.connect(lambda *_: (widget.resizeRowsToContents(), widget.updateGeometry()))
    return widget


def _faint(text: str) -> str:
    return f"<span style='color: {theme.COLORS['faint']};'>{html.escape(text)}</span>"


def _gain(text: str) -> str:
    """A gain (``.gain.up``): bold, in the gain's green."""
    return f"<b style='color: #8fe08f;'>{html.escape(text)}</b>"


def _css_colour(text: str) -> QColor:
    """A colour as app.css writes it: ``#rrggbb``, or ``rgba(r, g, b, a)`` with ``a`` from 0 to 1."""
    if text.startswith("rgba("):
        red, green, blue, alpha = (float(x) for x in text[5:-1].split(","))
        return QColor(round(red), round(green), round(blue), round(alpha * 255))
    return QColor(text)


class Doll(QFrame):
    """The paper doll's middle (``.doll``): the class, who wears the gear and its combat power, in the middle of a faint
    gold glow."""

    def __init__(self, cls: str, who: str, power: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("doll")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(17, 17, 17, 17)
        layout.setSpacing(2)
        layout.addStretch(1)
        for text, kind in ((cls.upper(), "dollClass"), (who, "dollWho"), (power, "dollPower")):
            if text:
                label = _label(text, kind)
                label.setAlignment(Qt.AlignHCenter)
                layout.addWidget(label)
        layout.addStretch(1)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        outline = QPainterPath()
        outline.addRoundedRect(rect, 6, 6)
        painter.fillPath(outline, INSET)
        middle = QPointF(self.width() * 0.5, self.height() * 0.4)
        reach = math.hypot(max(middle.x(), self.width() - middle.x()), max(middle.y(), self.height() - middle.y()))
        glow = QRadialGradient(middle, max(1.0, 0.6 * reach))   # circle at 50% 40%, gone at 60% of its farthest corner
        glow.setColorAt(0, QColor(232, 207, 142, 31))
        glow.setColorAt(1, QColor(232, 207, 142, 0))
        painter.fillPath(outline, glow)
        painter.setPen(QPen(QColor(theme.COLORS["line"]), 1))
        painter.drawPath(outline)
        painter.end()


class Columns(QWidget):
    """Cards in equal columns (``.cards``): five, or two on a narrow window, as app.css has them under its 1100 px
    breakpoint; a row's cards as tall as its tallest."""

    def __init__(self, cards: list[QWidget], wide: int = 5, narrow: int = 2, gap: int = 12,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.cards, self.wide, self.narrow = cards, wide, narrow
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(gap)
        self.columns = 0
        self.place(wide)

    def place(self, columns: int) -> None:
        if columns == self.columns:
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(max(self.wide, self.narrow)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(self.narrow if event.size().width() <= NARROW else self.wide)


def _card() -> tuple[QFrame, QVBoxLayout]:
    """A card (``.card``): its gold-edged box, its words in its middle."""
    card = QFrame()
    card.setObjectName("arcanaCard")
    column = QVBoxLayout(card)
    column.setContentsMargins(13, 13, 13, 13)
    column.setSpacing(3)
    return card, column


def _centred(text: str, name: str = "", rich: bool = False) -> QLabel:
    label = _label(text, name, rich=rich)
    label.setAlignment(Qt.AlignHCenter)
    return label


def _pick_card(slot: str, pick: str, variants: list[str]) -> QFrame:
    """A slot's recommended variant (``.card``): the slot, the variant, and what each variant gives."""
    card, column = _card()
    column.addWidget(_centred(slot, "cardSlot"))
    column.addSpacing(6)
    column.addWidget(_centred(pick, "cardPick"))
    column.addSpacing(6)
    column.addWidget(_centred("<br>".join(html.escape(line) for line in variants), "faint", rich=True))
    column.addStretch(1)
    return card


class HotbarIcon(QWidget):
    """A skill's picture as the hotbar shows it (``.hotbar-icon``, ``rotationIcon``): its key at the top left, its level
    at the bottom right."""

    def __init__(self, size: int, key: str = "", level: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.key, self.level, self.pixmap, self.path = key, level, None, ""
        self.setFixedSize(size, size)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self.pixmap = pixmap
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 3, 3)
        painter.fillPath(frame, QColor(ICON_BG))
        if self.pixmap is not None and not self.pixmap.isNull():
            painter.save()
            painter.setClipPath(frame)
            _cover(painter, QRectF(1, 1, self.width() - 2, self.height() - 2), self.pixmap)
            painter.restore()
        painter.setPen(QColor(theme.COLORS["line"]))
        painter.drawPath(frame)
        font = QFont(self.font())
        font.setPixelSize(13)
        painter.setFont(font)
        if self.key:                                       # .hotbar-key: on black, 3 px either side
            box = QRectF(1, 1, painter.fontMetrics().horizontalAdvance(self.key) + 6, painter.fontMetrics().height())
            painter.fillRect(box, QColor(0, 0, 0, 199))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(box, int(Qt.AlignCenter), self.key)
        if self.level:                                     # .hotbar-level: bold, its shadow under it
            font.setBold(True)
            painter.setFont(font)
            place = QRectF(0, 0, self.width() - 3, self.height() - 1)
            painter.setPen(QColor(0, 0, 0, 230))
            for dx, dy in ((0, 1), (1, 1), (-1, 1)):
                painter.drawText(place.translated(dx, dy), int(Qt.AlignRight | Qt.AlignBottom), self.level)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(place, int(Qt.AlignRight | Qt.AlignBottom), self.level)
        painter.end()


class AnywhereText(QWidget):
    """Words in the middle of their line that break inside a word wider than the line (``overflow-wrap: anywhere``),
    as a hotbar slot's skill name does."""

    def __init__(self, text: str, least: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.text, self.least = text, least
        policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _laid(self, width: float) -> tuple[QTextLayout, float]:
        option = QTextOption(Qt.AlignHCenter)
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout = QTextLayout(self.text, self.font())
        layout.setTextOption(option)
        layout.beginLayout()
        height = 0.0
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1.0, width))
            line.setPosition(QPointF(0, height))
            height += line.height()
        layout.endLayout()
        return layout, height

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(self.least, math.ceil(self._laid(width)[1]))

    def sizeHint(self) -> QSize:
        width = min(QFontMetrics(self.font()).horizontalAdvance(self.text), 120)
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return QSize(1, max(self.least, QFontMetrics(self.font()).height()))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.WindowText))
        layout, _height = self._laid(self.width())
        layout.draw(painter, QPointF(0, 0))
        painter.end()


class HotbarSlot(QFrame):
    """A hotbar slot (``.hotbar-slot``): the skill's picture with its key and level, its name, and how it is used;
    edged in gold when it is pressed by hand. ``s`` None is an empty slot."""

    def __init__(self, s: dict | None, icon: QWidget | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        manual = bool(s and s.get("manual"))
        self.setObjectName("hotbarEmpty" if s is None else "hotbarManual" if manual else "hotbarSlot")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)        # the row's twelve columns alike
        self.setMinimumWidth(70)
        column = QVBoxLayout(self)
        column.setContentsMargins(6, 6, 6, 6)
        column.setSpacing(0)
        if s is None:
            plus = _label("+", "hotbarPlus", wrap=False)
            plus.setAlignment(Qt.AlignCenter)
            column.addWidget(plus)
            return
        self.setToolTip(r.hotbar_tip(s))
        column.addWidget(icon, 0, Qt.AlignHCenter)
        column.addSpacing(5)
        column.addWidget(AnywhereText(r.js_text(s.get("name")), 30))
        note = _label(r.hotbar_note(s), "hotbarNoteGold" if manual else "hotbarNote")
        note.setAlignment(Qt.AlignHCenter)
        note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        column.addWidget(note)
        column.addStretch(1)


class Across(QScrollArea):
    """A part that can be wider than the window (``overflow-x: auto``): scrolled across, as tall as what it holds."""

    def __init__(self, content: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("across")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(content)
        content.setAutoFillBackground(False)
        self.viewport().setObjectName("acrossView")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _fit(self) -> None:
        content = self.widget()
        least = content.minimumSizeHint().width()
        width = max(self.width(), least)
        height = content.heightForWidth(width) if content.hasHeightForWidth() else -1
        height = (height if height > 0 else content.sizeHint().height()) + (
            self.horizontalScrollBar().sizeHint().height() if least > self.width() else 0)
        if self.minimumHeight() != height or self.maximumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit()


def _delay() -> QWidget:
    """The pause between two macro lines (``.macro-delay``): Delay 10 ms between two rules."""
    box = _plain()
    line = QHBoxLayout(box)
    line.setContentsMargins(0, 4, 0, 4)
    line.setSpacing(10)
    for part in ("rule", "Delay", "10", "ms", "rule"):
        if part == "rule":
            rule = QFrame()
            rule.setObjectName("macroRule")
            rule.setFixedHeight(1)
            line.addWidget(rule, 1, Qt.AlignVCenter)
        else:
            line.addWidget(_label(part, "macroDelay" if part == "10" else "muted", wrap=False))
    return box


class GenusRing(QWidget):
    """A genus's Insight ring (genus-editor.js ``ringHTML``): its nine analysis slots round the genus's sigil, name and
    level, a saved line's slot in gold, an unrecorded one gray, a locked one dim; a slot's words as its tooltip. Drawn
    to its width, at most 340 px, as the web page's SVG is."""

    def __init__(self, genus: str, group, parent: QWidget | None = None):
        super().__init__(parent)
        self.genus, self.nodes, self.level = genus, r.ring_nodes(group), r.genus_level(group)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumWidth(200)
        self.setMaximumWidth(340)
        self.setAccessibleName(f"{genus} Insight: nine analysis slots")

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return min(width, 340)

    def sizeHint(self) -> QSize:
        return QSize(320, 320)

    def set_group(self, group) -> None:
        """The ring drawn again for the genus's lines as they now are (the Genus editor's, as they are typed)."""
        self.nodes, self.level = r.ring_nodes(group), r.genus_level(group)
        self.update()

    def _spot(self, index: int) -> QPointF:
        angle = math.radians(-90 + index * 40)
        return QPointF(160 + 124 * math.cos(angle), 160 + 124 * math.sin(angle))

    def node_at(self, point: QPointF) -> int | None:
        scale = min(self.width(), self.height()) / 320
        for index in range(9):
            spot = self._spot(index) * scale
            if math.hypot(point.x() - spot.x(), point.y() - spot.y()) <= 18 * scale:
                return index
        return None

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            index = self.node_at(QPointF(event.pos()))
            if index is None:
                QToolTip.hideText()
                event.ignore()
            else:
                QToolTip.showText(event.globalPos(), self.nodes[index][1], self)
            return True
        return super().event(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width(), self.height()) / 320
        painter.scale(scale, scale)
        gold, muted = QColor(theme.COLORS["gold"]), QColor(theme.COLORS["muted"])
        middle = QPointF(160, 160)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(206, 182, 122, 71), 8))                     # the track, in the frame's colour
        painter.drawEllipse(middle, 124, 124)
        painter.setBrush(INSET)
        painter.setPen(QPen(gold, 2))
        painter.drawEllipse(middle, 87, 87)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(theme.COLORS["line"]), 1))
        painter.drawEllipse(middle, 78, 78)

        def words(text: str, y: float, size: int, colour: QColor, bold: bool = False, family: str = "",
                  x: float = 160) -> None:
            font = QFont(self.font())
            if family:
                font.setFamily(family)
            font.setPixelSize(size)
            font.setBold(bold)
            painter.setFont(font)
            painter.setPen(colour)
            ascent = painter.fontMetrics().ascent()                            # y is the line's baseline, as in SVG
            painter.drawText(QRectF(x - 160, y - ascent, 320, painter.fontMetrics().height()),
                             int(Qt.AlignHCenter | Qt.AlignTop), text)
        words("✦" if self.genus == "Special" else self.genus[:1], 145, 48, gold, family="serif")
        words(f"{self.genus} Insight", 178, 16, gold, bold=True)
        words(self.level, 202, 16, muted)
        for index, (state, _words) in enumerate(self.nodes):
            spot = self._spot(index)
            painter.setOpacity(0.4 if state == "locked" else 1.0)
            filled = state == "filled"
            painter.setBrush(gold if filled else QColor(theme.COLORS["panel2"]))
            painter.setPen(QPen(QColor(233, 203, 128, 166) if filled else muted, 2))
            painter.drawEllipse(spot, 18, 18)
            words(str(index + 1), spot.y() + 5, 16, QColor(6, 9, 15) if filled else QColor(theme.COLORS["text"]), bold=True,
                  x=spot.x())
            painter.setOpacity(1.0)
        painter.end()


class GenusButton(QPushButton):
    """A genus's button (``.genus-selectors .btn``): its name over its recorded level; the chosen one's ``primary``."""

    def __init__(self, name: str, level: str, chosen: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("genusOn" if chosen else "genus")
        self.setAccessibleName(f"{name} {level}")
        self.setCheckable(True)
        self.setChecked(chosen)                                                 # aria-pressed
        self.setCursor(Qt.PointingHandCursor)
        column = QVBoxLayout(self)
        column.setContentsMargins(11, 10, 11, 10)
        column.setSpacing(4)
        for words, kind in ((name, "genusName"), (level, "genusLevel")):
            label = _label(words, kind, wrap=False)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            column.addWidget(label)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.layout().sizeHint()


class GenusLayout(QWidget):
    """The genus buttons, the ring and the analysis side by side (``.genus-report-layout``: 120 px, 230 to 340 px, and
    the rest); on a narrow window, or one too narrow for the three, the buttons beside the ring and the analysis under
    both. It asks its window for no more room than the narrow arrangement needs, so the window can always choose it."""

    def __init__(self, buttons: QWidget, ring: QWidget, analysis: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.buttons, self.ring, self.analysis = buttons, ring, analysis
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 12, 0, 12)
        self.grid.setSpacing(14)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.narrow: bool | None = None
        self.place(False)

    def _wide_least(self) -> int:
        return 120 + 14 + self.ring.minimumSizeHint().width() + 14 + self.analysis.minimumSizeHint().width()

    def minimumSizeHint(self) -> QSize:
        least = max(110 + 14 + self.ring.minimumSizeHint().width(), self.analysis.minimumSizeHint().width())
        return QSize(least, self.grid.minimumSize().height())

    def place(self, narrow: bool) -> None:
        if narrow == self.narrow:
            return
        self.narrow = narrow
        for part in (self.buttons, self.ring, self.analysis):
            self.grid.removeWidget(part)
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
        self.buttons.setFixedWidth(110 if narrow else 120)
        self.grid.addWidget(self.buttons, 0, 0, Qt.AlignVCenter)
        self.grid.addWidget(self.ring, 0, 1, Qt.AlignVCenter)
        if narrow:
            self.grid.addWidget(self.analysis, 1, 0, 1, 2)
            self.grid.setColumnStretch(1, 1)
        else:
            self.grid.addWidget(self.analysis, 0, 2, Qt.AlignVCenter)
            self.grid.setColumnStretch(2, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = event.size().width()
        self.place(width <= NARROW or width < self._wide_least())


def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    """A note of the window (``section.note``): its heading, then what it holds."""
    box = QFrame()
    box.setObjectName("note")
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(6)
    column.addWidget(_label(title, "noteHead"))
    return box, column


def coverage_section(v: dict) -> QFrame | None:
    """The genera's coverage (``genusCoverageHTML``) as a note of the window, or none; the advice's genus shows it too."""
    coverage = r.genus_coverage(v)
    if coverage is None:
        return None
    box, column = _section("Genus coverage")
    column.addWidget(_label(coverage["line"]))
    column.addWidget(GridTable(r.COVERAGE_COLUMNS, coverage["rows"], {2: 2, 3: 2}))
    column.addWidget(_label(coverage["note"], "muted"))
    fold = Fold("Catalog basis")
    fold.add(_label(coverage["basis"], "muted"))
    column.addWidget(fold)
    return box


def targets_section(v: dict) -> QFrame | None:
    """The genus roll targets (``genusTargetsHTML``) as a note of the window, or none; the advice's genus shows them
    too."""
    targets = r.genus_targets(v)
    if targets is None:
        return None
    box, column = _section("Genus roll targets")
    if targets["rows"]:
        rows = [[a, b, c, d, _cell(f"<b>{html.escape(e)}</b><br><small>{html.escape(f)}</small>"), g]
                for a, b, c, d, e, f, g in targets["rows"]]
        column.addWidget(GridTable(r.TARGET_COLUMNS, rows, {0: 2, 2: 2, 3: 2, 4: 2, 5: 3}))
    column.addWidget(_label(targets["note"], "muted"))
    if targets["source"]:
        column.addWidget(_label(targets["source"], "muted"))
    return box


def _cell(rich: str) -> QLabel:
    """A table's cell of rich text (bold, faint and gain words)."""
    return _label(rich, rich=True)


class GridTable(QWidget):
    """A table as the web page draws ``table.t``: its heads gold and upper-case over a line, each row over a faint
    line, the words wrapping in their columns. A cell is text, a label of rich text, or another widget (a row's
    button, at the cell's end; a form's field at its start, with ``left``; across its column, with its ``fill``
    property set); ``stretch`` gives columns their share of the room to spare, and the columns in ``right`` (``.r``)
    have their words and heads at their ends."""

    def __init__(self, headers: list[str], rows: list[list], stretch: dict[int, int] | None = None,
                 parent: QWidget | None = None, left: bool = False, right: tuple[int, ...] = ()):
        super().__init__(parent)
        self.setObjectName("plain")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        for column, words in enumerate(headers):
            head = _label(words.upper(), "thead")
            if column in right:
                head.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.grid.addWidget(head, 0, column)
        for index, row in enumerate(rows, start=1):
            for column, cell in enumerate(row):
                if isinstance(cell, QWidget) and not isinstance(cell, QLabel):
                    box = QFrame()                             # the row's line under a widget too
                    box.setObjectName("tcellBox")
                    line = QHBoxLayout(box)
                    line.setContentsMargins(8, 3, 8, 3)
                    fill = bool(cell.property("fill"))           # a cell's words across its column
                    if not left and not fill:
                        line.addStretch(1)
                    line.addWidget(cell, 1 if fill else 0)
                    if left and not fill:
                        line.addStretch(1)
                    self.grid.addWidget(box, index, column)
                    continue
                label = cell if isinstance(cell, QLabel) else _label(str(cell))
                label.setObjectName("tcell")
                label.setAlignment((Qt.AlignRight if column in right else Qt.AlignLeft) | Qt.AlignVCenter)
                self.grid.addWidget(label, index, column)
        for column, factor in (stretch or {}).items():
            self.grid.setColumnStretch(column, factor)

    def cell(self, row: int, column: int) -> QLabel:
        """The label in a row (0 is the heads) and column."""
        return self.grid.itemAtPosition(row, column).widget()


class ResultWindows(QWidget):
    """A result's windows: the side menu and the chosen window (``renderWindows``). ``open_web`` opens a page of the
    web interface (the windows not drawn here yet); ``state`` keeps the chosen window and tabs, as the web page's
    state object does."""

    def __init__(self, api=None, open_web=None, web_page: str = "history", clipboard=None, when=None,
                 parent: QWidget | None = None, open_link=None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.open_web, self.web_page = open_web, web_page
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.clipboard = clipboard or (lambda text: QGuiApplication.clipboard().setText(text))
        self.when = when or (lambda ms: str(ms))
        self.view: dict = {}
        self.state = {"win": "overview", "skilltab": "active", "board": 0, "genusTab": "Cogni"}
        self.icons = Icons(api, self)
        self.icons.loaded.connect(self._icon)
        self.pixmaps: dict[str, QPixmap] = {}
        self.shown_icons: list[SkillIcon] = []
        self.boards: list[NodeBoard] = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        menu = QFrame()
        menu.setObjectName("win")
        menu.setFixedWidth(230)
        items = QVBoxLayout(menu)
        items.setContentsMargins(8, 8, 8, 8)
        items.setSpacing(2)
        self.menu: dict[str, QPushButton] = {}
        for key, title, mark in r.WINDOWS:
            button = QPushButton(f"{mark}   {title.replace('&', '&&')}")      # "&" is no shortcut here
            button.setObjectName("sideItem")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=key: self.choose(key))
            items.addWidget(button)
            self.menu[key] = button
        holder = QVBoxLayout()
        holder.addWidget(menu)
        holder.addStretch(1)
        row.addLayout(holder)
        body = _plain()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        row.addWidget(body, 1)

    # ------------------------------------------------------------------ choosing
    def set_view(self, view: dict, state: dict | None = None) -> None:
        self.view = view or {}
        if state:
            self.state.update(state)
        self.draw()

    def choose(self, key: str) -> None:
        self.state["win"] = key
        self.draw()

    def draw(self) -> None:
        while self.body.count():
            child = self.body.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.shown_icons, self.boards = [], []
        key = self.state.get("win") or "overview"
        for name, button in self.menu.items():
            wanted = "sideItemOn" if name == key else "sideItem"
            if button.objectName() != wanted:
                button.setObjectName(wanted)
                button.style().unpolish(button)
                button.style().polish(button)
        if key == "skills":
            self.body.addWidget(self._skills())
        elif key == "stigma":
            self.body.addWidget(self._stigmas())
        elif key == "daevanion":
            self.body.addWidget(self._daevanion())
        elif key == "equipment":
            self.body.addWidget(self._equipment())
        elif key == "arcana":
            for window in self._arcana():
                self.body.addWidget(window)
        elif key == "titles":
            self.body.addWidget(self._titles())
        elif key == "hotbar":
            self.body.addWidget(self._hotbar())
        elif key == "macro":
            self.body.addWidget(self._macro())
        elif key == "genus":
            self.body.addWidget(self._genus())
        else:                                                    # results.js's default: the Overview
            self.body.addWidget(self._overview())
            if key == "overview":
                self.body.addWidget(self._comparison())

    # ------------------------------------------------------------------ parts
    def _window(self, title: str, counter: tuple[str, str] | None = None, copy: str = "", subtitle: str = "") -> Window:
        """A window (``win``): its title, then its counter or its subtitle, its tools at the head's end."""
        window = Window(title, subtitle)
        if counter:
            window.head.insertWidget(1, _rich_counter(*counter))
            window.head.insertStretch(2, 1)                      # the counter beside the title, the tools at the end
        elif not subtitle:
            window.head.addStretch(1)
        if copy:
            button = QPushButton("Copy as text")
            button.setObjectName("small")
            button.clicked.connect(lambda: self.clipboard(copy))
            window.tool(button)
        return window

    def _web_button(self) -> QPushButton:
        button = QPushButton("Open the web Saved Results page" if self.web_page == "history" else "Open the web page")
        button.clicked.connect(lambda: self.open_web(self.web_page) if self.open_web else None)
        return button

    def _stat_grid(self, window: Window, rows: list[tuple[str, str]], title: str) -> None:
        """A window's figures under its title (``statGrid``); none when it has none."""
        if not rows:
            return
        box = QFrame()
        box.setObjectName("statsum")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_label(title.upper(), "statTitle"))
        columns = max(1, min(4, (max(self.width() - 246, 480) + 18) // (210 + 18)))
        layout.addWidget(pairs_grid([(name, html.escape(value)) for name, value in rows], columns))
        window.body.addWidget(box)

    def _icon_widget(self, url, size: int, level: str, placeholder: str = "", badge: int = 12) -> SkillIcon:
        return self._picture(SkillIcon(size, level, placeholder=placeholder, badge=badge), url)

    def _picture(self, widget, url):
        """A picture widget (with ``path`` and ``set_pixmap``) given its picture through the app's icon cache, once."""
        path = icon_path(url)
        widget.path = path
        if path in self.pixmaps:
            widget.set_pixmap(self.pixmaps[path])
        elif path:
            self.icons.ask(path)
        self.shown_icons.append(widget)
        return widget

    def _icon(self, path: str, data: bytes) -> None:
        image = pictures.decoded(data)
        if image.isNull():
            return
        self.pixmaps[path] = QPixmap.fromImage(image)
        for widget in self.shown_icons:
            if widget.path == path:
                widget.set_pixmap(self.pixmaps[path])
        for board in self.boards:
            board.picture(path, self.pixmaps[path])

    # ------------------------------------------------------------------ the Overview
    def _overview(self) -> Window:
        v = self.view
        window = self._window("Overview", subtitle=str(v.get("loadout_name") or ""))
        counts = _plain()
        grid = QGridLayout(counts)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        tiles = r.kpis(v)
        columns = max(1, min(len(tiles), (max(self.width() - 274, 600) + 10) // 160))
        for index, (name, value) in enumerate(tiles):
            tile = Kpi(name)
            tile.value.setText(value)
            grid.addWidget(tile, index // columns, index % columns)
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        window.body.addWidget(counts)
        for text in r.overview_notes(v, self.when):
            window.body.addWidget(_note(text))
        if r.model_note(v):
            window.body.addWidget(_label(r.model_note(v), "muted"))
        if v.get("progression"):
            fold = Fold("Point budget provenance")
            fold.add(_label(r.progression(v["progression"]), rich=True))
            box = QFrame()
            box.setObjectName("note")
            QVBoxLayout(box).addWidget(fold)
            box.layout().setContentsMargins(0, 0, 0, 0)
            window.body.addWidget(box)
        for text in (r.action_timing(v.get("action_timing")), r.survival(v.get("survival")),
                     r.skill_reserves(v.get("skill_reserves"))):
            if text:
                window.body.addWidget(_note(text))
        tables = _plain()
        pair = QGridLayout(tables)
        pair.setContentsMargins(0, 14, 0, 0)
        pair.setHorizontalSpacing(16)
        pair.setVerticalSpacing(6)
        priority = _plain()
        column = QVBoxLayout(priority)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(_label("STAT PRIORITY (DPS PER UPGRADE)", "goldHead"))
        weights = r.weight_rows(v)
        if weights:
            column.addWidget(bar_rows(weights, words_on_bar=False))
        else:
            status = _label("Calculating stat priority…" if v.get("weight_job") else
                            "Stat priority is unavailable for this build.")
            status.setObjectName("weightStatus")           # [data-weight-status]: the Build Planner writes its job's line
            column.addWidget(status)
        if v.get("scoring_policy"):
            column.addWidget(_label("Weighted upgrade gains with the saved rotation held fixed; timing is not re-optimized.",
                                    "muted"))
        column.addStretch(1)
        pair.addWidget(priority, 0, 0)
        shares = _plain()
        column = QVBoxLayout(shares)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(_label("DAMAGE SHARE", "goldHead"))
        column.addWidget(bar_rows(r.share_rows(v.get("shares")), words_on_bar=True))
        column.addStretch(1)
        pair.addWidget(shares, 0, 1)
        heal = r.healing(v)
        if heal is not None:
            box = _plain()
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.addWidget(_label("HEALING SHARE", "goldHead"))
            for line in heal["lines"]:
                column.addWidget(_label(line, "muted", rich=True))
            if heal["rows"]:
                column.addWidget(bar_rows(heal["rows"], words_on_bar=True))
            column.addStretch(1)
            pair.addWidget(box, 1, 0, 1, 2)
        pair.setColumnStretch(0, 1)
        pair.setColumnStretch(1, 1)
        window.body.addWidget(tables)
        return window

    def _comparison(self) -> QFrame:
        """Contribute a community comparison (closed, as on the web page): what it does, and the web page's button."""
        box = QFrame()
        box.setObjectName("win")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 10)
        fold = Fold("Contribute a community comparison")
        fold.add(_label(r.comparison_text(self.view), "muted"))
        fold.add(_label(COMPARISON_NOTE))
        fold.add(self._web_button())
        layout.addWidget(fold)
        return box

    # ------------------------------------------------------------------ Skills
    def _skills(self) -> Window:
        v = self.view
        tab = self.state.get("skilltab") or "active"
        window = self._window("Skills", r.skill_counter(v), r.skills_copy(v))
        tabs = _plain()
        line = QHBoxLayout(tabs)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        for name in ("active", "passive"):
            button = QPushButton(r.cap(name))
            button.setObjectName("tabOn" if name == tab else "tab")
            button.clicked.connect(lambda _checked=False, name=name: self._skill_tab(name))
            line.addWidget(button)
        line.addStretch(1)
        window.body.addWidget(tabs)
        for skill in (v.get("skills") or {}).get(tab) or []:
            window.body.addWidget(self._skill(skill))
        self._stat_grid(window, r.skills_grid(v), "From this system")
        return window

    def _skill_tab(self, name: str) -> None:
        self.state["skilltab"] = name
        self.draw()

    def _skill(self, s: dict) -> QFrame:
        """One skill (``.skill``): its picture and level, name and level's sources, its slots; then its supporting
        effects, each with its number, words, level and whether it is recommended."""
        card = QFrame()
        card.setObjectName("skill")
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(14)
        left = QVBoxLayout()
        heading = QHBoxLayout()
        heading.setSpacing(10)
        heading.addWidget(self._icon_widget(s.get("icon"), 52, f"Lv{r.js_text(s.get('eff'))}"), 0, Qt.AlignTop)
        title = QVBoxLayout()
        title.setSpacing(2)
        title.addWidget(_label(str(s.get("name") or ""), "strong"))
        title.addWidget(_label(r.skill_level(s), rich=True))
        heading.addLayout(title, 1)
        left.addLayout(heading)
        slots = r.skill_slots(s)
        if slots:
            left.addWidget(_label(slots, "muted"))
        left.addStretch(1)
        row.addLayout(left, 9)
        specs = s.get("specs") or []
        if specs:
            effects = QFrame()
            effects.setObjectName("specs")
            column = QVBoxLayout(effects)
            column.setContentsMargins(12, 0, 0, 0)
            column.setSpacing(9)
            for x in specs:
                state = r.effect_state(x)
                line = QHBoxLayout()
                line.setSpacing(8)
                badge = _label(r.e(x.get("n")), "specOn" if x.get("chosen") else "specAv" if x.get("available") else "spec",
                               wrap=False)
                badge.setFixedSize(26, 26)
                badge.setAlignment(Qt.AlignCenter)
                badge.setToolTip(state)
                line.addWidget(badge, 0, Qt.AlignTop)
                words = QVBoxLayout()
                words.setSpacing(3)
                words.addWidget(_label(str(x.get("name") or x.get("text") or "")))
                colour = (theme.COLORS["gold"] if x.get("chosen") else theme.COLORS["faint"])
                words.addWidget(_label(f"<span style='color: {colour};'>Lv {r.e(x.get('unlock'))} · {state}</span>", rich=True))
                line.addLayout(words, 1)
                column.addLayout(line)
            row.addWidget(effects, 11)
        if (s.get("eff") or 0) <= 1:
            dim = QGraphicsOpacityEffect(card)
            dim.setOpacity(0.55)
            card.setGraphicsEffect(dim)
        return card

    # ------------------------------------------------------------------ Stigma
    def _stigmas(self) -> Window:
        v = self.view
        window = self._window("Stigma", r.stigma_counter(v), r.stigmas_copy(v))
        stigmas = v.get("stigmas") or []
        if not stigmas:
            window.body.addWidget(_label("No stigmas", "muted"))
        cards = _plain()
        grid = QGridLayout(cards)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for index, s in enumerate(stigmas):
            card = QFrame()
            card.setObjectName("stigma")
            column = QVBoxLayout(card)
            column.setContentsMargins(12, 12, 12, 12)
            column.setSpacing(4)
            column.addWidget(self._icon_widget(s.get("icon"), 64, f"Lv{r.js_text(s.get('level'))}"), 0, Qt.AlignHCenter)
            name = _label(str(s.get("name") or ""), "stigmaName")
            name.setAlignment(Qt.AlignHCenter)
            column.addWidget(name)
            level = _label(f"Level {r.js_text(s.get('level'))}", "muted")
            level.setAlignment(Qt.AlignHCenter)
            column.addWidget(level)
            for x in s.get("specs") or []:
                effect = _label(r.stigma_effect(x), "stigmaEffect", rich=True)
                column.addWidget(effect)
            column.addStretch(1)
            grid.addWidget(card, index // 4, index % 4)
        for col in range(4):
            grid.setColumnStretch(col, 1)
        window.body.addWidget(cards)
        self._stat_grid(window, r.stigmas_grid(v), "Stats from this system")
        return window

    # ------------------------------------------------------------------ Daevanion
    def _daevanion(self) -> Window:
        """The Daevanion window: the boards' tabs; the points used, the board's points and nodes, and the skill levels
        and stats all the boards give at its side; the board and its key; the stats again under them."""
        v = self.view
        d = r._dict(v.get("daevanion"))
        index = self.state.get("board") or 0
        board = r.daevanion_board(v, index)
        if board is None:
            window = self._window("Daevanion")
            empty = _label(r.NO_BOARD, "empty")
            empty.setAlignment(Qt.AlignCenter)
            window.body.addWidget(empty)
            return window
        window = self._window("Daevanion", copy=r.daevanion_copy(v))
        link = r.planner_link(v)
        if QUrl(link).scheme() in ("http", "https"):     # the planner in the browser; no other kind of address opens
            button = QPushButton(r.PLANNER)
            button.setObjectName("small")
            button.clicked.connect(lambda: self.open_link(link))
            window.tool(button)
        tabs = _plain()
        flow = FlowLayout(tabs, align=Qt.AlignLeft, gap=(4, 4))
        for place, name, count in r.board_tabs(v):
            tab = BoardTab(name, count, place == index)
            tab.clicked.connect(lambda _checked=False, place=place: self._board(place))
            flow.addWidget(tab)
        window.body.addWidget(tabs)
        nodes = NodeBoard(board)
        for path in nodes.wanted:
            if path in self.pixmaps:
                nodes.picture(path, self.pixmaps[path])
            else:
                self.icons.ask(path)
        self.boards.append(nodes)
        column = _plain()
        stack = QVBoxLayout(column)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(10)
        stack.addWidget(BoardFrame(nodes))
        stack.addWidget(_legend())
        stack.addStretch(1)
        window.body.addWidget(Split([self._daevside(d, board), column], [260, 0], 14))
        self._stat_grid(window, r.daevanion_stats(d), "Stats from this system")
        return window

    def _daevside(self, d: dict, board: dict) -> QFrame:
        """The board's side (``.daevside``): the points used (and the Ariel crystal's), the board's points and nodes,
        the skill levels and the stats."""
        side = QFrame()
        side.setObjectName("daevside")
        column = QVBoxLayout(side)
        column.setContentsMargins(13, 13, 13, 13)
        column.setSpacing(2)
        counters = _plain()
        flow = FlowLayout(counters, align=Qt.AlignLeft, gap=(0, 4))
        flow.addWidget(_rich_counter("Points used", r.points_used(d)))
        ariel = r.ariel_used(d)
        if ariel:
            counter = _rich_counter("Ariel crystal used", ariel)
            counter.setToolTip(r.ARIEL_TIP)
            flow.addWidget(counter)
        column.addWidget(counters)
        gold = theme.COLORS["gold"]
        sections = (
            (f"{r.js_text(board.get('name'))} board", [_label(r.board_line(board))]),
            ("Skill levels", [_label(f"{html.escape(name)} <b style='color: {gold};'>{html.escape(levels)}</b>", rich=True)
                              for name, levels in r.daevanion_skills(d)] or [_label("none", "faint")]),
            ("Stats (all boards)", [_label(f"{html.escape(name)} <b>{html.escape(text)}</b>", rich=True)
                                    for name, text in r.daevanion_stats(d)]),
        )
        for head, rows in sections:
            column.addSpacing(8)
            column.addWidget(_label(head.upper(), "daevHead"))
            column.addSpacing(4)
            for row in rows:
                column.addWidget(row)
        column.addStretch(1)
        return side

    def _board(self, place: int) -> None:
        self.state["board"] = place
        self.draw()

    # ------------------------------------------------------------------ Equipment
    def _equipment(self) -> Window:
        """The Equipment window: the paper doll (the weapons and armour on its left, the accessories on its right, the
        class in its middle), the rolls to keep and where an enchant level is worth most, then the gear's stats."""
        v = self.view
        window = self._window("Equipment", copy=r.equipment_copy(v), subtitle=r.equipment_sub(v))
        left, right = r.equipment_slots(v)
        window.body.addWidget(Split([self._slots(left), Doll(*r.doll(v)), self._slots(right)], [0, 220, 0], 12))
        rolls = r.roll_rows(v)
        if rolls:
            halves = []
            for head, rows in ((r.ROLLS_HEAD, [f"<b>{html.escape(slug)}</b>: {html.escape(stats)}" for slug, stats in rolls]),
                               (r.ENCHANT_HEAD, [f"{html.escape(slot)} <b>{html.escape(dps)}</b> DPS / level"
                                                 for slot, dps in r.enchant_rows(v)])):
                half = _plain()
                column = QVBoxLayout(half)
                column.setContentsMargins(0, 0, 0, 0)
                column.setSpacing(2)
                column.addWidget(_label(head, "goldHead"))
                column.addSpacing(8)
                for row in rows:
                    column.addWidget(_label(row, rich=True))
                column.addStretch(1)
                halves.append(half)
            window.body.addSpacing(2)
            window.body.addWidget(Split(halves, [0, 0], 16))
        self._stat_grid(window, r.equipment_grid(v), r.EQUIPMENT_GRID)
        return window

    def _slots(self, slots: list[dict]) -> QWidget:
        """One side of the paper doll (``.slots``): its slots' tiles, 6 px apart."""
        box = _plain()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        for s in slots:
            enchant = f"+{r.js_text(s.get('enchant'))}" if s.get("enchant") else ""
            column.addWidget(SlotTile.of(s, self._icon_widget(s.get("icon"), 34, enchant, placeholder="◇", badge=13)))
        column.addStretch(1)
        return box

    # ------------------------------------------------------------------ Arcana
    def _arcana(self) -> list[Window]:
        """The Arcana window: a character's cards, the variant recommended for each slot and the value of each slot's
        skill rolls; then the deity and primary stats' totals in a window of their own."""
        v = self.view
        window = self._window("Arcana", copy=r.arcana_copy(v), subtitle=r.ARCANA_SUB)
        cards, picks, rows = r.arcana_cards(v), r.arcana_picks(v), r.arcana_roll_rows(v)
        if cards:
            window.body.addWidget(Columns([self._arcana_card(card) for card in cards]))
        if picks:
            window.body.addSpacing(2)
            window.body.addWidget(_label(r.PICKS_HEAD, "goldHead"))
            window.body.addWidget(Columns([_pick_card(*pick) for pick in picks]))
        if rows:
            window.body.addSpacing(4)
            window.body.addWidget(_label(r.ROLLS_TABLE_HEAD, "goldHead"))
            rolls = _table(r.ROLLS_COLUMNS, rows, right=(1, 2), stretch=3)
            for row in range(len(rows)):
                rolls.item(row, 0).setForeground(QColor(theme.COLORS["gold"]))
            window.body.addWidget(rolls)
        if not (cards or picks or rows):
            empty = _label(r.NO_ARCANA, "empty")
            empty.setAlignment(Qt.AlignCenter)
            window.body.addWidget(empty)
        shown = [window]
        deity = r.deity_grid(v)
        if deity:
            totals = self._window("Deity & primary stats")
            self._stat_grid(totals, deity, "Totals")
            shown.append(totals)
        return shown

    def _arcana_card(self, card: dict) -> QFrame:
        """A character's arcana card (``.card``): its picture and enchant level, its name in its grade's colour, its
        deity stat, its skill levels and its stats."""
        box, column = _card()
        column.addWidget(self._icon_widget(card["icon"], 52, card["enchant"]), 0, Qt.AlignHCenter)
        column.addSpacing(3)
        column.addWidget(_centred(card["name"], "gname" + card["grade"]))
        if card["deity"]:
            column.addWidget(_centred(card["deity"], "gold"))
        if card["skills"]:
            holder = _plain()
            flow = FlowLayout(holder, align=Qt.AlignHCenter, gap=(3, 2), centre=False)
            for words in card["skills"]:
                flow.addWidget(_label(words, "chip", wrap=False))
            column.addWidget(holder)
        if card["stats"]:
            column.addWidget(_centred(card["stats"], "muted"))
        column.addStretch(1)
        return box

    # ------------------------------------------------------------------ Titles, wings & pet
    def _titles(self) -> Window:
        """The Titles, wings & pet window: the titles, wings and pet the build wears beside the best titles for it,
        then the stats from its titles."""
        v = self.view
        window = self._window(r.TITLES_TITLE)
        worn = _plain()
        column = QVBoxLayout(worn)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        for tile in r.title_tiles(v):
            column.addWidget(SlotTile(tile["slot"], tile["item"], tile["grade"], tile["stats"],
                                      self._icon_widget(tile["icon"], 34, ""), level=tile["level"]))
        column.addStretch(1)
        best = _plain()
        column = QVBoxLayout(best)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(_label(r.TITLES_HEAD, "goldHead"))
        rows = r.title_rows(v)
        ranking = _table(r.TITLE_COLUMNS, [[name, equip, owned] for name, _grade, equip, owned in rows], stretch=1)
        for row, (_name, grade, _equip, _owned) in enumerate(rows):
            name = ranking.item(row, 0)
            name.setForeground(_css_colour(r.GRADES[grade]) if grade else QColor(theme.COLORS["text"]))
            font = QFont(name.font())
            font.setWeight(QFont.DemiBold)
            name.setFont(font)
            ranking.item(row, 2).setForeground(QColor(theme.COLORS["muted"]))
        column.addWidget(ranking)
        column.addStretch(1)
        window.body.addWidget(Split([worn, best], [0, 0], 16))
        self._stat_grid(window, r.titles_grid(v), r.TITLES_GRID)
        return window

    # ------------------------------------------------------------------ Skills hotbar
    def _hotbar(self) -> Window:
        """The Skills hotbar window: where to put each skill and its key, the last row of twelve first; then how to use
        the manual skills and which key to keep for the macro."""
        v = self.view
        if not r._truthy(v.get("hotbar")):
            window = self._window("Skills hotbar")
            empty = _label(r.NO_HOTBAR, "empty")
            empty.setAlignment(Qt.AlignCenter)
            window.body.addWidget(empty)
            return window
        window = self._window("Skills hotbar", copy=r.hotbar_copy(v), subtitle=r.HOTBAR_SUB)
        window.body.addWidget(_label(r.HOTBAR_INTRO))
        rows = _plain()
        grid = QGridLayout(rows)
        grid.setContentsMargins(0, 12, 0, 12)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(14)
        for index, (number, slots) in enumerate(r.hotbar_rows(v)):
            label = _label(number, "hotbarRow", wrap=False)
            grid.addWidget(label, index, 0, Qt.AlignVCenter)
            for place, s in enumerate(slots, start=1):
                icon = self._picture(HotbarIcon(58, r.hotbar_key(s), r.hotbar_level(s)), s.get("icon")) if s else None
                grid.addWidget(HotbarSlot(s, icon), index, place)
        grid.setColumnMinimumWidth(0, 24)
        for place in range(1, 13):
            grid.setColumnStretch(place, 1)
        window.body.addWidget(Across(rows))
        window.body.addWidget(_label(r.HOTBAR_MANUAL, rich=True))
        window.body.addWidget(_label(r.hotbar_reserve(v), rich=True))
        return window

    # ------------------------------------------------------------------ Macro & rotation
    def _macro(self) -> Window:
        """The Macro & rotation window: how to set the macro up; the macro's lines, each hotbar key with the skills it
        holds, the delays and the key to save it to; the manual skills, the macro's estimate and the optimizer's
        priority."""
        v = self.view
        if not r.has_macro(v):
            window = self._window("Skill Macro")
            empty = _label(r.NO_MACRO, "empty")
            empty.setAlignment(Qt.AlignCenter)
            window.body.addWidget(empty)
            return window
        window = self._window(r.MACRO_TITLE, copy=r.macro_copy(v))
        steps = "".join(f"<li style='margin-bottom: 5px;'>{step}</li>" for step in r.macro_instructions(v))
        window.body.addWidget(_label(f"<ol style='margin-left: 0px; -qt-list-indent: 1;'>{steps}</ol>", rich=True))
        window.body.addWidget(Split([self._macro_editor(v), self._macro_side(v)], [(300, 480), 0], 24,
                                    narrow_at=MACRO_NARROW, top=True))
        return window

    def _macro_editor(self, v: dict) -> QFrame:
        """The macro as the game's editor lists it (``.macro-editor``): its numbered lines, the delays between them, and
        the key to save it to."""
        editor = QFrame()
        editor.setObjectName("macroEditor")
        column = QVBoxLayout(editor)
        column.setContentsMargins(17, 17, 17, 17)
        column.setSpacing(0)
        title = _label("Macro", "macroTitle")
        title.setAlignment(Qt.AlignHCenter)
        column.addWidget(title)
        column.addSpacing(10)
        lines = r.macro_lines(v)
        for index, s in enumerate(lines):
            column.addWidget(self._macro_step(index, s))
            if index < len(lines) - 1:
                column.addWidget(_delay())
        if not lines:
            column.addWidget(_label(r.ONLY_MANUAL, "muted"))
        column.addSpacing(18)
        save = _label(f"Save to {r.macro_binding(v)} in game", "macroSave")
        save.setAlignment(Qt.AlignCenter)
        column.addWidget(save)
        return editor

    def _macro_step(self, index: int, s: dict) -> QWidget:
        """A macro line (``.macro-step``): its number, the skills its hotbar key holds in the order they are cast, and
        the key."""
        step = _plain()
        grid = QGridLayout(step)
        grid.setContentsMargins(0, 10, 0, 10)
        grid.setHorizontalSpacing(10)
        number = _label(str(index + 1), "macroNumber", wrap=False)
        number.setAlignment(Qt.AlignCenter)
        number.setFixedWidth(28)
        grid.addWidget(number, 0, 0)
        stack = _plain()
        column = QVBoxLayout(stack)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        held = r.held(s)
        for place, h in enumerate(held):
            if place:
                column.addSpacing(6)
            column.addWidget(self._picture(HotbarIcon(72, r.hotbar_key(h), r.hotbar_level(h)), h.get("icon")), 0,
                             Qt.AlignHCenter)
            for words, kind in ((r.js_text(h.get("name")), "strong"), (r.chain_note(h), "muted"),
                                (r.cast_note(place, len(held)), "muted")):
                if words:
                    label = _label(words, kind)
                    label.setAlignment(Qt.AlignHCenter)
                    column.addWidget(label)
        grid.addWidget(stack, 0, 1)
        key = _label(f"Hotbar key {r.kbd(s.get('binding'))}", "muted", rich=True)
        key.setAlignment(Qt.AlignCenter)
        key.setFixedWidth(100)
        grid.addWidget(key, 0, 2)
        grid.setColumnStretch(1, 1)
        return step

    def _macro_side(self, v: dict) -> QWidget:
        """The macro's side: the manual skills, the macro's estimate, and the optimizer's priority."""
        side = _plain()
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(_label(r.MANUAL_HEAD, "goldHead"))
        manual = r.manual_skills(v)
        for s in manual:
            row = _plain()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 4, 0, 4)
            line.setSpacing(12)
            line.addWidget(self._picture(HotbarIcon(58, r.hotbar_key(s), r.hotbar_level(s)), s.get("icon")), 0,
                           Qt.AlignVCenter)
            words = QVBoxLayout()
            words.setSpacing(2)
            words.addWidget(_label(r.js_text(s.get("name")), "strong"))
            for note in (r.chain_note(s), r.manual_words(s)):
                if note:
                    words.addWidget(_label(note, "muted"))
            line.addLayout(words, 1)
            column.addWidget(row)
        if not manual:
            column.addWidget(_label(r.NO_MANUAL, "muted"))
        column.addWidget(_label(r.macro_estimate(v), "muted"))
        column.addSpacing(6)
        column.addWidget(_label(r.READY_HEAD, "goldHead"))
        column.addWidget(_label(r.READY_NOTE, "muted"))
        muted = theme.COLORS["muted"]
        items = "".join(f"<li>{html.escape(name)}" + "".join(f" <span style='color: {muted};'>({html.escape(part)})</span>"
                                                            for part in parts) + "</li>"
                        for name, parts in r.priority_items(v))
        column.addWidget(_label(f"<ol style='margin-left: 0px; -qt-list-indent: 1;'>{items}</ol>", rich=True))
        column.addStretch(1)
        return side

    # ------------------------------------------------------------------ Pet Genus
    def _genus(self) -> Window:
        """The Pet Genus window: whether lines were saved and where to enter them; the genera, the chosen one's ring and
        its nine slots' analysis; what to roll for, the coverage and the roll targets; the model's assumptions."""
        v = self.view
        genus = r.genus_choice(self.state.get("genusTab"))
        group = r.genus_group(v, genus)
        window = self._window(r.GENUS_TITLE, subtitle=r.genus_subtitle(v))
        note = QFrame()
        note.setObjectName("note")
        holder = QVBoxLayout(note)
        holder.setContentsMargins(0, 0, 0, 0)
        words = _label(r.genus_note(v), rich=True)
        words.setTextInteractionFlags(Qt.TextBrowserInteraction)
        words.setOpenExternalLinks(False)
        words.linkActivated.connect(lambda page: self.open_web(page) if self.open_web else None)
        holder.addWidget(words)
        window.body.addWidget(note)
        buttons = _plain()
        column = QVBoxLayout(buttons)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        for name, level in r.genus_buttons(v):
            button = GenusButton(name, level, name == genus)
            button.clicked.connect(lambda _checked=False, name=name: self._genus_tab(name))
            column.addWidget(button)
        ring = _plain()
        stack = QVBoxLayout(ring)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(GenusRing(genus, group), 0, Qt.AlignHCenter)
        stack.addWidget(_label(r.RING_KEY, "muted"))
        analysis = _plain()
        stack = QVBoxLayout(analysis)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(8)
        stack.addWidget(_label(f"{genus} Insight · {r.genus_level(group)}", "genusHead"))
        stack.addWidget(GridTable(r.ANALYSIS_COLUMNS, r.genus_rows(v, genus), {1: 3, 4: 3}))
        window.body.addWidget(GenusLayout(buttons, ring, analysis))
        rolls = r.genus_rolls(v, genus)
        if rolls is not None:
            box, column = _section(f"Roll for · {genus}")
            if rolls["best"]:
                items = "".join(f"<li>Slot {html.escape(slot)}: <b>{html.escape(stat)}</b> {_faint(grade)} {_gain(gain)}</li>"
                                for slot, stat, grade, gain in rolls["best"])
                column.addWidget(_label(f"<ol style='margin-left: 0px; -qt-list-indent: 1;'>{items}</ol>", rich=True))
            else:
                column.addWidget(_label(r.NO_CANDIDATE, "faint"))
            table_rows = []
            for row in rolls["rows"]:
                aim = (f"<b>{html.escape(row['aim'][0])}</b> {_faint(row['aim'][1])} {_gain(row['aim'][2])}" if row["aim"]
                       else _faint("No modeled line"))
                then = "<br>".join(f"{html.escape(stat)} {_faint(gain)}" for stat, gain in row["then"])
                table_rows.append([row["slot"], _cell(aim), _cell(then), row["saved"], row["status"], row["options"]])
            column.addWidget(GridTable(r.ROLL_COLUMNS, table_rows, {1: 3, 2: 3, 3: 2, 4: 2, 5: 1}))
            column.addWidget(_label(rolls["basis"], "muted"))
            window.body.addWidget(box)
        for section in (coverage_section(v), targets_section(v)):
            if section is not None:
                window.body.addWidget(section)
        assumptions = r.genus_assumptions(v)
        if assumptions is not None:
            fold = Fold(r.ASSUMPTIONS)
            fold.add(_label(assumptions["note"], "muted"))
            if assumptions["mix"]:
                fold.add(_label(assumptions["mix"]))
            fold.add(_label(r.ASSUMPTIONS_NOTE, "muted"))
            window.body.addWidget(fold)
        return window

    def _genus_tab(self, name: str) -> None:
        self.state["genusTab"] = name
        self.draw()

    def stop(self) -> None:
        self.icons.stop()


STYLE = f"""
QPushButton#sideItem, QPushButton#sideItemOn {{ text-align: left; padding: 9px 10px; border-radius: 4px; font-weight: 600;
    background: transparent; border: 1px solid transparent; color: {theme.COLORS['muted']}; }}
QPushButton#sideItemOn, QPushButton#sideItem:hover {{ color: {theme.COLORS['gold']}; background: rgba(232, 207, 142, 0.07);
    border-color: rgba(206, 182, 122, 0.28); }}
QLabel#counter, QFrame#win QLabel#counter {{ padding: 4px 10px; border: 1px solid rgba(206, 182, 122, 0.28);
    border-radius: 4px; background: rgba(6, 9, 15, 0.65); font-weight: 700; }}
QPushButton#tab, QPushButton#tabOn {{ border: 1px solid {theme.COLORS['line']}; background: rgba(6, 9, 15, 0.65);
    color: {theme.COLORS['muted']}; padding: 7px 14px; border-radius: 4px; font-weight: 600; }}
QPushButton#tabOn {{ color: #10131a; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ecd79f, stop:1 #b9984f);
    border-color: rgba(233, 203, 128, 0.65); }}
QFrame#skill, QFrame#stigma {{ background: {theme.COLORS['panel2']}; border: 1px solid {theme.COLORS['line']}; border-radius: 5px; }}
QFrame#skill QLabel, QFrame#stigma QLabel, QFrame#specs {{ background: transparent; }}
QFrame#specs {{ border: none; border-left: 1px solid {theme.COLORS['line']}; }}
QFrame#skill QLabel#spec, QFrame#skill QLabel#specAv, QFrame#skill QLabel#specOn {{ border: 1px solid {theme.COLORS['line2']};
    border-radius: 4px; font-weight: 700; background: rgba(6, 9, 15, 0.65); color: {theme.COLORS['faint']}; }}
QFrame#skill QLabel#specAv {{ color: {theme.COLORS['muted']}; }}
QFrame#skill QLabel#specOn {{ color: #1b1404; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f1dc9f,
    stop:1 #c39c45); border-color: #f5dfa0; }}
QLabel#strong {{ font-weight: 700; }}
QLabel#stigmaName {{ color: {theme.COLORS['gold']}; font-weight: 700; }}
QLabel#stigmaEffect {{ border: none; border-top: 1px dashed {theme.COLORS['line']}; padding: 3px 0; }}
QLabel#goldHead {{ color: {theme.COLORS['gold']}; font-weight: 700; }}
QLabel#statTitle {{ color: {theme.COLORS['gold']}; font-weight: 700; letter-spacing: 1px; }}
QFrame#statsum {{ background: transparent; border: none; border-top: 1px solid rgba(206, 182, 122, 0.28); }}
QFrame#barRow {{ background: transparent; border: none; border-bottom: 1px solid #1d2539; }}
QFrame#barRow QLabel {{ background: transparent; }}
QLabel#figure {{ font-weight: 600; }}
QFrame#note {{ background: rgba(233, 164, 58, 0.07); border: 1px solid rgba(233, 164, 58, 0.35); border-radius: 5px;
    padding: 9px 12px; }}
QFrame#note QLabel, QFrame#note QToolButton, QFrame#note QWidget#foldBody {{ background: transparent; border: none; }}
QFrame#note QLabel {{ color: #f1d4a3; }}
QFrame#note QLabel#muted {{ color: {theme.COLORS['muted']}; }}
QWidget#foldBody, QWidget#plain {{ background: transparent; }}
QToolButton#fold {{ border: none; padding: 2px 0; color: {theme.COLORS['text']}; }}
QFrame#daevside {{ background: rgba(6, 9, 15, 0.65); border: 1px solid {theme.COLORS['line']}; border-radius: 6px; }}
QFrame#win QLabel#daevHead {{ color: {theme.COLORS['gold']}; font-weight: 700; }}
QScrollArea#boardScroll, QWidget#boardView {{ background: transparent; border: none; }}
QFrame#win QLabel#empty {{ color: {theme.COLORS['faint']}; padding: 18px; }}
QPushButton#tab QLabel, QPushButton#tabOn QLabel {{ font-weight: 600; }}
QPushButton#tab QLabel#tabName {{ color: {theme.COLORS['muted']}; }}
QPushButton#tabOn QLabel#tabName {{ color: #10131a; }}
QPushButton#tab QLabel#tabCount, QPushButton#tabOn QLabel#tabCount {{ color: {theme.COLORS['faint']}; }}
QFrame#win QLabel#slotName {{ color: {theme.COLORS['faint']}; }}
QFrame#win QLabel#gname {{ color: {theme.COLORS['text']}; font-weight: 600; }}
QFrame#win QLabel#slotStats {{ color: {theme.COLORS['muted']}; }}
QFrame#win QLabel#chip, QFrame#win QLabel#chipGold, QFrame#win QLabel#chipSkill {{ padding: 1px 6px; border-radius: 3px;
    background: rgba(57, 194, 224, 0.12); color: #9fe3f2; border: 1px solid rgba(57, 194, 224, 0.25); }}
QFrame#win QLabel#chipGold {{ background: rgba(233, 203, 128, 0.12); color: {theme.COLORS['gold']};
    border-color: rgba(206, 182, 122, 0.28); }}
QFrame#win QLabel#chipSkill {{ color: {theme.COLORS['gold']}; }}
QFrame#win QLabel#dollClass {{ color: {theme.COLORS['gold']}; font-size: 18px; font-weight: 700; }}
QFrame#win QLabel#dollWho {{ color: {theme.COLORS['muted']}; }}
QFrame#win QLabel#dollPower {{ color: {theme.COLORS['gold']}; }}
QFrame#arcanaCard {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {theme.COLORS['card_a']},
    stop:1 {theme.COLORS['card_b']}); border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 8px; }}
QFrame#win QLabel#gold {{ color: {theme.COLORS['gold']}; }}
QFrame#win QLabel#cardSlot {{ color: {theme.COLORS['gold']}; font-weight: 700; }}
QFrame#win QLabel#cardPick {{ font-weight: 700; }}
QFrame#hotbarSlot, QFrame#hotbarManual, QFrame#hotbarEmpty {{ background: rgba(6, 9, 15, 0.65);
    border: 1px solid {theme.COLORS['line']}; }}
QFrame#hotbarManual {{ border-color: {theme.COLORS['gold']}; }}
QFrame#win QLabel#hotbarNote {{ color: {theme.COLORS['muted']}; }}
QFrame#win QLabel#hotbarNoteGold {{ color: {theme.COLORS['gold']}; }}
QFrame#win QLabel#hotbarPlus {{ color: rgba(132, 139, 154, 0.45); font-size: 16px; }}
QFrame#win QLabel#hotbarRow {{ color: {theme.COLORS['muted']}; font-size: 19px; }}
QScrollArea#across, QWidget#acrossView {{ background: transparent; border: none; }}
QFrame#macroEditor {{ background: rgba(6, 9, 15, 0.65); border: 1px solid {theme.COLORS['line']}; }}
QFrame#win QLabel#macroTitle {{ color: {theme.COLORS['gold']}; font-size: 15px; font-weight: 700; }}
QFrame#win QLabel#macroNumber {{ color: {theme.COLORS['gold']}; font-size: 22px; }}
QFrame#win QLabel#macroDelay {{ background: {theme.COLORS['panel2']}; padding: 3px 14px; font-weight: 700; }}
QFrame#macroRule {{ background: {theme.COLORS['line']}; border: none; }}
QFrame#win QLabel#macroSave {{ border: 1px solid {theme.COLORS['gold']}; padding: 10px; color: {theme.COLORS['gold']}; }}
QPushButton#genus, QPushButton#genusOn {{ text-align: left; border-radius: 4px; padding: 0;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b3550, stop:1 #1c2438); border: 1px solid rgba(206, 182, 122, 0.28); }}
QPushButton#genusOn {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523, stop:1 #3f3215);
    border-color: rgba(233, 203, 128, 0.65); }}
QPushButton#genus QLabel, QPushButton#genusOn QLabel {{ background: transparent; }}
QPushButton#genus QLabel#genusName {{ font-weight: 700; }}
QPushButton#genusOn QLabel#genusName, QPushButton#genusOn QLabel#genusLevel {{ color: #fff3cf; }}
QPushButton#genusOn QLabel#genusName {{ font-weight: 700; }}
QFrame#win QLabel#genusHead {{ font-size: 15px; font-weight: 700; }}
QFrame#note QLabel#noteHead {{ font-weight: 700; }}
QFrame#win QLabel#thead {{ color: {theme.COLORS['gold_dim']}; font-weight: 600; padding: 6px 8px;
    border: none; border-bottom: 1px solid rgba(206, 182, 122, 0.28); }}
QFrame#win QLabel#tcell {{ padding: 5px 8px; border: none; border-bottom: 1px solid #1d2539; }}
QFrame#win QFrame#tcellBox {{ background: transparent; border: none; border-bottom: 1px solid #1d2539; }}
""" + "".join(
    f"QFrame#win QLabel#gname{grade} {{ color: {colour}; font-weight: 600; }}\n" for grade, colour in r.GRADES.items())
