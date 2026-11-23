"""An analyzed encounter's page in the native Combat Logs page (0.2.456), as pages/combat.js draws
``#/combat-log/analysis/<id>``: a fight imported from an AbyssLogs or A2DIL link, or from a file, broken down for one
player. It is shown in place of the views, with **← Back to combat logs**.

- **Encounter:** the party, to analyze the fight as another of them; **Share link**; the notes, the AbyssLogs page and
  the file it is saved in; the parse card; and the casts a minute, multi-hits and idle time.
- **Buff uptime**, with the idle gaps.
- **Compared with your optimal rotation:** the same fight length simulated with the class's optimized build.
- **Compared with top players:** the class's top Korean training-dummy logs (A2DIL), when the app has them.

The parse card (``ParseCard``, parse.js ``renderParse``) has the player's figures and three tabs: DPS (damage by skill,
the DPS over the fight, the skills), Defense and Accuracy, then the skill rotation. From 900 px wide it shows every
section at once in two columns, as the web card does.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import combat_analysis as ca
from . import theme
from .api import AppApi, Job, Requests
from .combat import encode_component
from .combat_community import _note
from .combat_saved import _button, _clear, _label
from .database_page import Window
from .pictures import Pictures
from .results import _dict, _truthy, js_text

C = theme.COLORS
INSET = theme.Shade("inset", whole=True)
STYLE = theme.Sheet(lambda: f"""
    QFrame#parse {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {C['card_a']}, stop:1 {C['card_b']});
        border: 1px solid {C['line']}; border-radius: 10px; }}
    QFrame#parse QLabel, QFrame#parse QWidget#plain {{ background: transparent; }}
    QFrame#pHead {{ background: transparent; border: none; border-bottom: 1px solid {C['line']}; }}
    QLabel#pName {{ color: {C['gold']}; font-family: serif; font-size: 14px; font-weight: 700; }}
    QLabel#pSub {{ color: {C['muted']}; }}
    QLabel#pStatName {{ color: {C['faint']}; font-size: 12px; letter-spacing: 0.5px; }}
    QLabel#pStat {{ font-weight: 700; }}
    QLabel#pStatGold {{ color: {C['gold']}; font-weight: 700; }}
    QPushButton#pTab {{ background: {INSET}; border: 1px solid {C['line']}; color: {C['muted']}; border-radius: 6px;
        padding: 4px 14px; font-weight: 600; }}
    QPushButton#pTab[on="true"] {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {theme.COLORS['btn_a']}, stop:1 {theme.COLORS['btn_b']});
        color: {C['gold']}; border-color: {theme.css('frame_hi')}; }}
    QLabel#pHeading {{ color: {C['gold']}; font-family: serif; font-size: 13px; font-weight: 700; letter-spacing: 1px; }}
    QFrame#parse QFrame#pBox {{ background: {INSET}; border: 1px solid {C['line']}; border-radius: 8px; }}
    QLabel#pBoxName {{ color: {C['faint']}; font-size: 12px; letter-spacing: 0.6px; }}
    QLabel#pBig {{ color: {C['gold']}; font-size: 22px; font-weight: 800; }}
    QLabel#pRate {{ font-size: 17px; font-weight: 800; }}
    QLabel#pShare {{ color: {C['muted']}; }}
    QFrame#parse QLabel#pTh {{ color: {C['faint']}; font-weight: 600; font-size: 12px; letter-spacing: 0.4px;
        padding: 4px 8px; border: none; border-bottom: 1px solid {C['line']}; }}
    QFrame#parse QLabel#pTd {{ padding: 5px 8px; border: none; border-bottom: 1px solid {INSET}; }}
    QFrame#parse QFrame#pTdBox {{ background: transparent; border: none; border-bottom: 1px solid {INSET}; }}
    QFrame#pRotation {{ background: transparent; border: none; border-top: 1px solid {C['line']}; }}
    QLabel#pFaint {{ color: {C['faint']}; font-size: 12px; }}
    QFrame#parse QLabel#pIcon {{ background: {theme.COLORS['icon_bg']}; border: 1px solid {C['line']}; border-radius: 5px; }}
    QFrame#parse QLabel#pNoData {{ color: {C['muted']}; background: {INSET}; border: 1px dashed {C['line2']};
        border-radius: 8px; padding: 14px; }}
    QFrame#tip {{ background: rgba(57, 194, 224, 0.06); border: none; border-left: 3px solid {C['accent']};
        border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
    QFrame#tip QLabel {{ background: transparent; }}
    QFrame#parse QLabel#pClass {{ background: {theme.COLORS['icon_bg']}; border-radius: 6px; }}
    QLabel#specHead {{ color: {C['gold']}; font-size: 12px; font-weight: 700; margin-top: 14px; }}
    """)
WIDE = 900                     # the card's width from which it shows every section at once (``@container pcard``)
_TAB = {"chosen": "dps"}       # the tab chosen last, for every card (``_ptab``)


def _plain(layout=QVBoxLayout, spacing: int = 0):
    box = QWidget()
    box.setObjectName("plain")
    line = layout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    return box, line


def _icon(pixmap, size: int, tip: str = "", name: str = "pIcon") -> QLabel:
    """A picture in its frame, or the frame alone when the app has none."""
    face = QLabel()
    face.setObjectName(name)
    face.setFixedSize(size, size)
    face.setAlignment(Qt.AlignCenter)
    if pixmap is not None and not pixmap.isNull():
        face.setPixmap(pixmap.scaled(size - 2, size - 2, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    if tip:
        face.setToolTip(tip)
    return face


#: The placeholders drawn, by size and gold (0.2.506): a parse card drawn again with each of the Live Meter's readings
#: shows the same picture, where a new one each time left Qt's picture cache an entry for each until it was full.
_PLACEHOLDERS: dict[tuple[int, str], QPixmap] = {}


def placeholder(size: int) -> QPixmap:
    """A skill without art (``SKILL_PLACEHOLDER``): a gold diamond's outline on the frame's blue, drawn once for each
    size (and each gold: the theme's)."""
    key = (size, C["gold"])
    if key not in _PLACEHOLDERS:
        _PLACEHOLDERS[key] = _drawn_placeholder(size)
    return _PLACEHOLDERS[key]


def _drawn_placeholder(size: int) -> QPixmap:
    picture = QPixmap(size, size)
    picture.fill(Qt.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.Antialiasing)
    scale = size / 24.0
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#263048"))
    painter.drawRoundedRect(QRectF(0, 0, size, size), 4 * scale, 4 * scale)
    diamond = QPainterPath()
    diamond.moveTo(12 * scale, 4 * scale)
    for x, y in ((19, 12), (12, 20), (5, 12)):
        diamond.lineTo(x * scale, y * scale)
    diamond.closeSubpath()
    painter.setPen(QPen(QColor(C["gold"]), 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(diamond)
    painter.end()
    return picture


class Bar(QWidget):
    """A share as a bar with its words over it (``.bar``): blue, or gold (``alt``)."""

    def __init__(self, fraction: float, words: str, alt: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.fraction, self.words, self.alt = max(0.0, min(1.0, fraction)), words, alt
        self.setMinimumWidth(120)
        self.setFixedHeight(18)
        self.setProperty("fill", True)
        self.setAccessibleName(words)

    def sizeHint(self) -> QSize:
        return QSize(200, 18)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor("inset"))                     # ``.bar``'s ground
        painter.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)
        if self.fraction > 0:
            fill = QLinearGradient(0, 0, w * self.fraction, 0)
            if self.alt:
                fill.setColorAt(0, QColor("#8a6d2b"))
                fill.setColorAt(1, QColor("#e8cf8e"))
                painter.setOpacity(0.85)
            else:
                fill.setColorAt(0, QColor("#2a8fb0"))
                fill.setColorAt(1, QColor("#39c2e0"))
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(0, 0, w * self.fraction, h), 3, 3)
            painter.setOpacity(1.0)
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor(C["text"]))
        painter.drawText(QRectF(6, 0, w - 6, h), Qt.AlignLeft | Qt.AlignVCenter, self.words)
        painter.end()


class Donut(QWidget):
    """Damage by skill as a ring (``pdonut``), the DPS in its middle."""

    def __init__(self, arcs: list[tuple[float, float, str]], value: str, size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.arcs, self.value = arcs, value
        self.setFixedSize(size, size)
        self.setAccessibleName(f"{value} DPS")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = self.width() / 190.0
        outer, inner = 86 * scale, 55 * scale
        middle, thickness = (outer + inner) / 2, outer - inner
        centre = QPointF(self.width() / 2, self.height() / 2)
        ring = QRectF(centre.x() - middle, centre.y() - middle, 2 * middle, 2 * middle)
        for start, sweep, colour in self.arcs:
            pen = QPen(QColor(colour), thickness)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            painter.drawArc(ring, int(round(-start * 16)), int(round(-sweep * 16)))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(17)
        painter.setFont(font)
        painter.setPen(QColor(C["gold"]))
        painter.drawText(QRectF(0, centre.y() - 22, self.width(), 24), Qt.AlignCenter, self.value)
        font.setBold(False)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor(C["faint"]))
        painter.drawText(QRectF(0, centre.y() + 2, self.width(), 18), Qt.AlignCenter, "DPS")
        painter.end()


class DpsChart(QWidget):
    """The DPS over the fight (``lineChart``): each second's damage as a bar, the ten-second average as a gold line."""

    def __init__(self, per: list[float], roll: list[float], top: float, parent: QWidget | None = None, height: int = 190):
        super().__init__(parent)
        self.per, self.roll, self.top, self.height_hint = per, roll, top or 1.0, height
        self.setMinimumHeight(150)
        self.setMaximumHeight(360)
        self.setAccessibleName("DPS over the fight")

    def sizeHint(self) -> QSize:
        return QSize(600, self.height_hint)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        n = len(self.per) or 1
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor("chart_bar"))                 # ``fill:var(--chart-bar)``
        for i, v in enumerate(self.per):
            height = v / self.top * h
            painter.drawRect(QRectF(i / n * w, h - height, max(1.0, w / n - w / 1000.0), height))
        if self.roll:
            painter.setPen(QPen(QColor(C["chart_line"]), 2))         # ``stroke:var(--chart-line)``
            painter.drawPolyline(QPolygonF([QPointF((i + 0.5) / n * w, h - v / self.top * h) for i, v in enumerate(self.roll)]))
        painter.end()


class _DamageCell(QLabel):
    """A skill's damage with its share, over a faint bar against the largest skill's (``.dmg``)."""

    def __init__(self, words: str, fraction: float):
        super().__init__(words)
        self.fraction = max(0.0, min(1.0, fraction))
        self.setObjectName("pTd")
        self.setTextFormat(Qt.RichText)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(233, 203, 128, 36))
        painter.drawRoundedRect(QRectF(0, 2, self.width() * self.fraction, self.height() - 5), 3, 3)
        painter.end()
        super().paintEvent(event)


class ParseCard(QFrame):
    """One fight's parse card (``renderParse``), fed a normalized fight (``parse_from_encounter``). ``pictures`` gives
    the class's emblem and the skills' icons the app bundles."""

    def __init__(self, d: dict, pictures: Pictures | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("parse")
        self.d, self.pictures = _dict(d), pictures
        self.wide: bool | None = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(14, 12, 14, 12)
        self.box.setSpacing(10)
        self.soon = QTimer(self)                            # a redraw after a resize or the pictures, once
        self.soon.setSingleShot(True)
        self.soon.setInterval(0)
        self.soon.timeout.connect(lambda: self.draw(self.width() >= WIDE))
        if self.pictures is not None:
            self.pictures.changed.connect(self._pictures)
        self.draw(False)

    def _pictures(self) -> None:
        self.soon.setInterval(120)
        self.soon.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if (self.width() >= WIDE) != self.wide:
            self.soon.setInterval(0)
            self.soon.start()

    def choose(self, tab: str) -> None:
        """A tab chosen (``data-ptab``): the one every card opens on from now on."""
        _TAB["chosen"] = tab
        self.draw(bool(self.wide))

    # ---------------------------------------------------------------- drawing
    def draw(self, wide: bool) -> None:
        self.wide = wide
        _clear(self.box)
        chart = ca.chart(self.d)
        self.box.addWidget(self._head())
        if wide:
            grid = QGridLayout()
            grid.setHorizontalSpacing(28)
            grid.setVerticalSpacing(16)
            if chart is not None:       # "dmg acc" "dmg def" "chart def": the chart's row takes what the right needs
                grid.addWidget(self._damage(True), 0, 0, 2, 1, Qt.AlignTop)
                grid.addWidget(self._accuracy(True), 0, 1, Qt.AlignTop)
                defense = self._defense(True)
                grid.addWidget(defense, 1, 1, 2, 1, Qt.AlignTop if ca.defense(self.d) else Qt.Alignment())
                grid.addWidget(self._chart(chart, True), 2, 0)
            else:                       # "dmg acc" "def def"
                grid.addWidget(self._damage(True), 0, 0, Qt.AlignTop)
                grid.addWidget(self._accuracy(True), 0, 1, Qt.AlignTop)
                grid.addWidget(self._defense(True), 1, 0, 1, 2, Qt.AlignTop)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.box.addLayout(grid)
            self.box.addWidget(self._skills(True))
        else:
            self.box.addWidget(self._tabs())
            chosen = _TAB["chosen"]
            if chosen == "def":
                self.box.addWidget(self._defense(False))
            elif chosen == "acc":
                self.box.addWidget(self._accuracy(False))
            else:
                self.box.addWidget(self._damage(False))
                if chart is not None:
                    self.box.addWidget(self._chart(chart, False))
                self.box.addWidget(self._skills(False))
        rotation = self._rotation()
        if rotation is not None:
            self.box.addWidget(rotation)

    def _heading(self, words: str, column: QVBoxLayout, note: str = "") -> None:
        """A section's heading, shown only with every section at once (``psh``); its tooltip holds the section's note."""
        heading = _label(words.upper(), "pHeading", wrap=False)
        if note:
            heading.setToolTip(note)
            heading.setCursor(Qt.WhatsThisCursor)
        column.addWidget(heading)

    def _head(self) -> QFrame:
        """The player, class and boss, and the fight's figures (``phead``)."""
        head = QFrame()
        head.setObjectName("pHead")
        line = QHBoxLayout(head)
        line.setContentsMargins(0, 0, 0, 10)
        line.setSpacing(9)
        cls = js_text(self.d.get("cls") or "")
        if cls:
            emblem = self.pictures.emblem(cls.lower()) if self.pictures is not None else None
            line.addWidget(_icon(emblem, 26, name="pClass"))
        line.addWidget(_label(js_text(self.d.get("name")) or "—", "pName", wrap=False))
        line.addWidget(_label(ca.head_line(self.d), "pSub", wrap=False))
        line.addStretch(1)
        for words, value, gold in ca.head_stats(self.d):
            stat, column = _plain(spacing=0)
            name = _label(words.upper(), "pStatName", wrap=False)
            name.setAlignment(Qt.AlignRight)
            figure = _label(value, "pStatGold" if gold else "pStat", wrap=False)
            figure.setAlignment(Qt.AlignRight)
            column.addWidget(name)
            column.addWidget(figure)
            line.addWidget(stat)
            line.addSpacing(8)
        return head

    def _tabs(self) -> QWidget:
        box, line = _plain(QHBoxLayout, 6)
        for key, words in ca.TABS:
            tab = QPushButton(words)
            tab.setObjectName("pTab")
            tab.setProperty("on", key == _TAB["chosen"])
            tab.setCursor(Qt.PointingHandCursor)
            tab.clicked.connect(lambda _checked=False, key=key: self.choose(key))
            line.addWidget(tab)
        line.addStretch(1)
        return box

    def _box(self, name: str, value: str, value_name: str) -> QFrame:
        """A figure in a box (``phi``, ``rc``): its name over it."""
        frame = QFrame()
        frame.setObjectName("pBox")
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(2)
        for words, kind in ((name.upper(), "pBoxName"), (value, value_name)):
            label = _label(words, kind, wrap=False)
            label.setAlignment(Qt.AlignCenter)
            column.addWidget(label)
        frame.setAccessibleName(f"{name}: {value}")
        return frame

    def _damage(self, wide: bool) -> QWidget:
        """Damage by skill (``pdmg``): the highest hit, then the ring beside the five largest skills."""
        box, column = _plain(spacing=12)
        if wide:
            self._heading("Damage by skill", column)
        if self.d.get("highest") is not None:
            column.addWidget(self._box("Highest hit", theme.kfmt(self.d.get("highest")), "pBig"))
        split, line = _plain(QHBoxLayout, 20 if wide else 16)
        parts = ca.donut(self.d)
        size = 165 if wide else 190
        ring, ring_line = _plain(QHBoxLayout)
        ring.setFixedWidth(size if wide else 200)
        ring_line.addWidget(Donut(ca.donut_arcs(parts), theme.kfmt(self.d.get("dps")), size), 0, Qt.AlignCenter)
        line.addWidget(ring)
        top, rows = _plain(spacing=6)
        if not parts:
            rows.addWidget(_label(ca.NO_SKILLS, "muted"))
        for part in parts:
            row, row_line = _plain(QHBoxLayout, 8)
            swatch = QLabel()
            swatch.setFixedSize(10, 10)
            swatch.setStyleSheet(f"background: {part['colour']}; border-radius: 2px;")
            row_line.addWidget(swatch)
            name = _label(part["label"], wrap=False)
            name.setToolTip(part["label"])
            row_line.addWidget(name, 1)
            share = _label(part["share"], "pShare", wrap=False)
            share.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_line.addWidget(share)
            rows.addWidget(row)
        line.addWidget(top, 1, Qt.AlignVCenter)
        column.addWidget(split)
        return box

    def _chart(self, chart: dict, wide: bool) -> QWidget:
        """The DPS over the fight (``pchart``), with what its bars and line are."""
        box, column = _plain(spacing=6)
        if wide:
            self._heading("DPS over the fight", column)
        graph = DpsChart(chart["per"], chart["roll"], chart["top"], height=150 if wide else 190)
        if not wide:
            graph.setFixedHeight(190)
        column.addWidget(graph, 1)
        legend, line = _plain(QHBoxLayout, 12)
        line.addWidget(_label("bars: damage per second", "small", wrap=False))
        gold = _label("line: 10 s average", "small", wrap=False)
        gold.setStyleSheet(f"color: {C['gold']};")
        line.addWidget(gold)
        line.addWidget(_label(chart["peak"], "small", wrap=False))
        line.addStretch(1)
        column.addWidget(legend)
        return box

    def _skill_icon(self, skill_id, name: str, size: int) -> QLabel:
        """A skill's icon the app bundles, else the web page's placeholder."""
        art = ca.skill_art(skill_id)
        pixmap = self.pictures.by_address(art) if self.pictures is not None and art else None
        return _icon(pixmap if pixmap is not None else placeholder(size - 2), size, name)

    def _skills(self, wide: bool) -> QWidget:
        """The skills (``pskills``): each one's hits, DPS, average, least, most and damage."""
        box, column = _plain(spacing=0)
        if wide:
            self._heading("Skills", column)
            column.addSpacing(10)
        table = QWidget()
        table.setObjectName("plain")
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        for c, words in enumerate(ca.SKILL_COLUMNS):
            head = _label(words.upper(), "pTh", wrap=False)
            head.setAlignment((Qt.AlignLeft if c == 0 else Qt.AlignRight) | Qt.AlignVCenter)
            grid.addWidget(head, 0, c)
        for r, row in enumerate(ca.skill_rows(self.d), start=1):
            name = QFrame()
            name.setObjectName("pTdBox")
            line = QHBoxLayout(name)
            line.setContentsMargins(8, 3, 8, 3)
            line.setSpacing(7)
            line.addWidget(self._skill_icon(row["skill_id"], row["skill"], 20))
            line.addWidget(_label(row["skill"], wrap=False), 1)
            grid.addWidget(name, r, 0)
            for c, key in enumerate(("hits", "dps", "avg", "min", "max"), start=1):
                cell = _label(row[key], "pTd", wrap=False)
                cell.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                grid.addWidget(cell, r, c)
            grid.addWidget(_DamageCell(f"{html.escape(row['damage'])}<span style='color: {C['muted']};'>&nbsp;&nbsp;"
                                       f"{html.escape(row['share'])}</span>", row["bar"]), r, 6)
        for c, factor in enumerate((3, 1, 1, 1, 1, 1, 3)):
            grid.setColumnStretch(c, factor)
        column.addWidget(table)
        return box

    def _rates(self, cards: list[tuple[str, str]], wide: bool) -> QWidget:
        """Figures in boxes, four a row with every section at once, else as many as fit (``prates``)."""
        box = QWidget()
        box.setObjectName("plain")
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        across = 4 if wide else max(1, min(len(cards), (max(self.width(), 400) - 28 + 10) // 100))
        for i, (name, value) in enumerate(cards):
            grid.addWidget(self._box(name, value, "pRate"), i // across, i % across)
        for c in range(across):
            grid.setColumnStretch(c, 1)
        return box

    def _accuracy(self, wide: bool) -> QWidget:
        """Accuracy (``pacc``): the outgoing hits and their rates."""
        box, column = _plain(spacing=10)
        if wide:
            self._heading("Accuracy", column, ca.ACCURACY_NOTE)
        column.addWidget(self._rates(ca.accuracy(self.d), wide))
        if not wide:
            column.addWidget(_label(ca.ACCURACY_NOTE, "small"))
        return box

    def _defense(self, wide: bool) -> QWidget:
        """Defense (``pdef``): the damage taken and its flags, and each attacker's damage; or why there is none."""
        box, column = _plain(spacing=10)
        defense = ca.defense(self.d)
        if wide:
            self._heading("Defense", column, ca.DEFENSE_NOTE if defense else "")
        if defense is None:
            note = _label(ca.NO_INCOMING, "pNoData")
            note.setAlignment(Qt.AlignCenter)
            if wide:                                        # down to the chart's foot, as the web card's grid stretches it
                note.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            column.addWidget(note, 1)
            return box
        column.addWidget(self._rates(defense["cards"], wide))
        table = QWidget()
        table.setObjectName("plain")
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        for c, words in enumerate(("Attacker", "Damage")):
            grid.addWidget(_label(words.upper(), "pTh", wrap=False), 0, c)
        for r, (name, damage) in enumerate(defense["attackers"], start=1):
            grid.addWidget(_label(name, "pTd"), r, 0)
            grid.addWidget(_label(damage, "pTd", wrap=False), r, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        column.addWidget(table)
        if not wide:
            column.addWidget(_label(ca.DEFENSE_NOTE, "small"))
        return box

    def _rotation(self) -> QFrame | None:
        """The skill rotation's first eighty casts, side by side, scrolling sideways (``prot``)."""
        casts = ca.rotation(self.d)
        if not casts:
            return None
        frame = QFrame()
        frame.setObjectName("pRotation")
        column = QVBoxLayout(frame)
        column.setContentsMargins(0, 8, 0, 0)
        column.setSpacing(5)
        column.addWidget(_label("SKILL ROTATION", "pFaint", wrap=False))
        strip, line = _plain(QHBoxLayout, 4)
        for cast in casts:
            item, item_line = _plain(spacing=1)
            item.setFixedWidth(34)
            item.setToolTip(cast["skill"])
            item_line.addWidget(self._skill_icon(cast["skill_id"], cast["skill"], 30), 0, Qt.AlignHCenter)
            at = _label(cast["at"], "pFaint", wrap=False)
            at.setAlignment(Qt.AlignHCenter)
            item_line.addWidget(at)
            line.addWidget(item)
        line.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("plain")
        scroll.setWidget(strip)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(strip.sizeHint().height() + 14)
        scroll.setAccessibleName("Skill rotation")
        column.addWidget(scroll)
        return frame


# ---------------------------------------------------------------------- the analysis page
class AnalysisPage(QWidget):
    """An analyzed encounter's page (``#/combat-log/analysis/<id>``). ``open_link`` opens an address in the browser;
    ``opened(id)`` opens another analysis (the fight analyzed as another of its party); ``say`` shows a passing
    message (``toast``)."""

    def __init__(self, api: AppApi | None, opened, open_link=None, say=None, pictures: Pictures | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.opened, self.pictures = opened, pictures
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.say = say or (lambda words: None)
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.job = Job(api, self) if api is not None else None
        if self.job is not None:
            self.job.logged.connect(lambda log: self.say(js_text(log[-1]) if log else "Analyzing…"))
            self.job.done.connect(self._analyzed)
            self.job.failed.connect(self._refused_player)
        self.asked = 0
        self.answer: dict | None = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(14)

    def stop(self) -> None:
        for worker in (self.requests, self.job):
            if worker is not None:
                worker.stop()

    def show_encounter(self, identifier) -> None:
        """An analysis read and drawn; an answer to one opened before is let go."""
        self.asked += 1
        self.identifier, self.answer = identifier, None
        _clear(self.box)
        self.box.addWidget(_label(ca.LOADING, "muted"))
        if self.requests is not None:
            self.requests.get(f"encounter:{self.asked}", f"/api/encounters/{encode_component(identifier)}")

    def _replied(self, name: str, answer) -> None:
        kind, _, number = name.partition(":")
        if kind == "encounter" and number == str(self.asked):
            if isinstance(answer, dict) and _truthy(answer.get("error")):
                self._refused(js_text(answer["error"]))
            else:
                self.answer = _dict(answer)
                self.draw()
        elif kind == "share" and number == str(self.asked):
            self._shared(_dict(answer))

    def _failed(self, name: str, why: str) -> None:
        kind, _, number = name.partition(":")
        if number != str(self.asked):
            return
        if kind == "encounter":
            self._refused(why)
        elif kind == "share":
            self._share_said(why)
            self.share.setEnabled(True)

    def _refused(self, why: str) -> None:
        _clear(self.box)
        self.box.addWidget(_note(why or "Could not read the encounter."))

    # ---------------------------------------------------------------- drawing
    def draw(self) -> None:
        a = self.answer or {}
        _clear(self.box)
        encounter = Window("Encounter", ca.subtitle(a))
        body = encounter.body
        people = ca.party(a)
        if people:
            row, line = _plain(QHBoxLayout, 6)
            line.addWidget(_label("Party:", "muted", wrap=False))
            for person in people:
                button = QPushButton(person["name"] + (f"  {person['class']}" if person["class"] else ""))
                button.setObjectName("primary" if person["you"] else "small")
                button.setToolTip(person["tip"])
                button.setAccessibleName(f"Analyze as {person['name']}")
                button.clicked.connect(lambda _checked=False, who=person["name"], b=button: self.analyze_as(who, b))
                line.addWidget(button)
            line.addStretch(1)
            body.addWidget(row)
        if _truthy(a.get("id")):
            row, line = _plain(QHBoxLayout, 8)
            self.share = _button(ca.SHARE, self.share_link, "primary")
            line.addWidget(self.share)
            self.shared_box, self.shared_line = _plain(QHBoxLayout)
            line.addWidget(self.shared_box)
            line.addStretch(1)
            body.addWidget(row)
        notes = _label(ca.info_html(a, C["accent"]), "small", rich=True)
        notes.linkActivated.connect(self.open_link)
        body.addWidget(notes)
        body.addWidget(ParseCard(ca.parse_from_encounter(a), self.pictures))
        chips, line = _plain(QHBoxLayout, 10)
        for name, value in ca.chips(a):
            line.addWidget(_label(f"{html.escape(name)}: <b>{html.escape(value)}</b>", "small", rich=True, wrap=False))
        line.addStretch(1)
        body.addWidget(chips)
        self.box.addWidget(encounter)
        self.box.addWidget(self._buffs(a))
        self.box.addWidget(self._optimal(a))
        top = ca.top(a)
        if top is not None:
            self.box.addWidget(self._top(top))

    def _table(self, heads: list[str], rows: list[list], stretch: dict, right=()) -> QWidget:
        from .result_windows import GridTable
        return GridTable(heads, rows, stretch, left=True, right=right)

    def _buffs(self, a) -> Window:
        """Each buff's uptime as a gold bar, and the idle gaps (``Buff uptime``)."""
        window = Window("Buff uptime")
        table = QWidget()
        table.setObjectName("plain")
        grid = QGridLayout(table)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for r, buff in enumerate(ca.buffs(a)):
            grid.addWidget(_label(buff["name"]), r, 0)
            grid.addWidget(Bar(buff["bar"], buff["words"], alt=True), r, 1)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        window.body.addWidget(table)
        gaps = ca.gaps(a)
        if gaps:
            window.body.addWidget(_label(gaps, "small"))
        return window

    def _optimal(self, a) -> Window:
        """The comparison with the optimal rotation (``opt``, ``specs``)."""
        window = Window("Compared with your optimal rotation", "same fight length, simulated")
        o = ca.optimal(a)
        if o["error"]:
            window.body.addWidget(_note(o["error"]))
            return window
        if o["note"]:
            window.body.addWidget(_note(o["note"]))
        window.body.addWidget(_label(f"Share overlap with the optimal rotation: <b style='color: {C['gold']};'>"
                                     f"{html.escape(o['overlap'])}</b>{html.escape(o['dps'])}", rich=True))
        for words in o["tips"]:
            tip = QFrame()
            tip.setObjectName("tip")
            line = QVBoxLayout(tip)
            line.setContentsMargins(10, 7, 10, 7)
            line.addWidget(_label(words))
            window.body.addWidget(tip)
        rows = [[r["skill"], Bar(r["share"], r["share_words"]), Bar(r["sim"], r["sim_words"], alt=True), r["casts"],
                 r["sim_casts"]] for r in o["rows"]]
        window.body.addWidget(self._table(ca.OPTIMAL_COLUMNS, rows, {0: 3, 1: 2, 2: 2}, right=(3, 4)))
        if o["specs"]:
            window.body.addWidget(_label("SPECIALIZATIONS (from the log)", "specHead"))
            rows = [[s["skill"], _label(f"<span style='color: {C['bad'] if s['differs'] else C['text']};'>"
                                        f"{html.escape(s['yours'])}</span>", rich=True),
                     _label(f"<span style='color: {C['gold']};'>{html.escape(s['optimal'])}</span>", rich=True)]
                    for s in o["specs"]]
            window.body.addWidget(self._table(ca.SPEC_COLUMNS, rows, {0: 1, 1: 1, 2: 1}))
        return window

    def _top(self, top: dict) -> Window:
        """The comparison with the class's top logs (``top``)."""
        window = Window("Compared with top players", "A2DIL top-10 dummy logs")
        window.body.addWidget(_label("Share overlap with the top Korean logs for this class: "
                                     f"<b style='color: {C['gold']};'>{html.escape(top['overlap'])}</b>", rich=True))
        window.body.addWidget(self._table(ca.TOP_COLUMNS, top["rows"], {0: 3, 1: 1, 2: 1, 3: 1, 4: 1}, right=(3, 4)))
        return window

    # ---------------------------------------------------------------- the actions
    def share_link(self) -> None:
        """The encounter shared to the log server (``data-share``): its link, or why not."""
        if self.requests is None or self.answer is None:
            return
        self.share.setEnabled(False)
        self.requests.post(f"share:{self.asked}", f"/api/encounters/{encode_component(self.answer.get('id'))}/share", {})

    def _shared(self, result: dict) -> None:
        self.share.setEnabled(True)
        _clear(self.shared_line)
        url = js_text(result.get("url") or "")
        link = _label(f"<a href='{html.escape(url, quote=True)}' style='color: {C['accent']};'>{ca.SHARED}</a>", rich=True,
                      wrap=False)
        link.linkActivated.connect(self.open_link)
        self.shared_line.addWidget(link)
        if _truthy(result.get("ownership_warning")):
            self.say(js_text(result["ownership_warning"]))

    def _share_said(self, words: str) -> None:
        _clear(self.shared_line)
        self.shared_line.addWidget(_label(words, "muted", wrap=False))

    def analyze_as(self, player: str, button: QPushButton) -> None:
        """The fight analyzed again as another of its party (``data-player``), then opened."""
        if self.job is None or self.answer is None:
            return
        button.setEnabled(False)
        self.waiting = button
        self.job.start("/api/encounters/import", ca.import_body(self.answer, player))

    def _analyzed(self, result) -> None:
        identifier = _dict(result).get("id")
        if identifier is not None:
            self.opened(identifier)

    def _refused_player(self, why: str) -> None:
        self.say(why)
        button = getattr(self, "waiting", None)
        try:
            if button is not None:
                button.setEnabled(True)
        except RuntimeError:                                 # drawn again since
            pass
