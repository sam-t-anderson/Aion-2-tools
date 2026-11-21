"""An advice's view (0.2.444), as pages/advice.js's ``renderAdvice`` draws it, its windows one under another:

- **Top changes:** each change's area, words and gain, ranked by simulated DPS gain, and where the advice was saved;
- **Skill specialties:** each skill's effective level and slots, the effects recommended (all of them, folded), and
  its next unlock;
- **Equipment:** the paper doll, each slot's tile with its badge (a better item from your inventory, or the next goal's
  gain) and its first upgrade path step; a slot clicked shows its way from what you wear to the best in slot;
- **Upgrade path:** one change at a time, biggest gain first, each with its rolls to chase, its gain and the gain so
  far;
- **Arcana** (0.2.445): each slot's variant, the skill options to chase at their target levels, its ideal and average
  gains, and the cards you have with keep or replace and what each holds;
- **Titles** (0.2.445): each slot's title equipped, the best you own and the best in slot (a slot no title adds damage to
  ranked by what its titles take off the hits you take), and the titles worth collecting;
- **Pantheon** (0.2.445): the ten deities with your points and what 10 more are worth, the arcana's deity choices, and
  the recommended board (``pantheon_board``) with its list;
- **Your fights** and **Model calibration**.

The genus advice is not drawn here yet: ``open_web`` opens it on the web page.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                               QLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from . import advice as a_
from . import pictures
from . import results as r
from . import theme
from .chrome import FlowLayout
from .database_page import Icons, Window
from .pantheon_board import PantheonBoard
from .result_windows import Across, Bar, GridTable, SkillIcon, _css_colour, icon_path
from .timers_page import Fold

GAIN = "#8fe08f"
DOWN = theme.COLORS["bad"]
FRAME = "rgba(206, 182, 122, 0.28)"                     # app.css's --frame, --frame-hi and --inset
FRAME_HI = "rgba(233, 203, 128, 0.65)"
INSET = "rgba(6, 9, 15, 0.65)"


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


def _grade(item) -> str:
    grade = r._dict(item).get("grade")
    return grade if isinstance(grade, str) and grade in r.GRADES else ""


def _colour(item) -> str:
    grade = _grade(item)
    return _css_colour(r.GRADES[grade]).name() if grade else theme.COLORS["text"]


def _centred(label: QLabel) -> QLabel:
    label.setAlignment(Qt.AlignHCenter)
    return label


def _dimmed(frame: QFrame, opacity: float = 0.5) -> QFrame:
    """A card with nothing in it, at half its strength (``.icard.empty``), or a deity of no use to damage."""
    effect = QGraphicsOpacityEffect(frame)
    effect.setOpacity(opacity)
    frame.setGraphicsEffect(effect)
    return frame


class Columns(QWidget):
    """Cells in ``wide`` columns as wide as each other (``grid-template-columns: repeat(5, minmax(0, 1fr))``), or in
    ``narrow`` ones where the view is narrower than ``below`` (the web page's narrow window); a row's cells as tall as
    each other."""

    def __init__(self, cells: list[QWidget], wide: int, narrow: int, gap: int = 10, below: int = 900,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.cells, self.wide, self.narrow, self.below = cells, wide, narrow, below
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(gap)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.columns = 0
        self.place(wide)

    def place(self, columns: int) -> None:
        if columns == self.columns:
            return
        for cell in self.cells:
            self.grid.removeWidget(cell)
        for index, cell in enumerate(self.cells):
            self.grid.addWidget(cell, index // columns, index % columns)
        for column in range(max(self.columns, columns)):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self.columns = columns
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place(self.wide if event.size().width() >= self.below else self.narrow)


class Sigil(QWidget):
    """A deity's sigil (``.sigil``): its lord's initial on a disc of the deity's colour, lit from the upper left."""

    def __init__(self, letter: str, colour: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.letter, self.colour = letter, QColor(colour)
        self.setFixedSize(34, 34)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        disc = QRectF(1, 1, 32, 32)
        painter.setPen(QPen(QColor(0, 0, 0, 136), 2))
        painter.setBrush(self.colour)
        painter.drawEllipse(disc)
        light = QRadialGradient(QPointF(1 + 32 * 0.35, 1 + 32 * 0.30), 32 * 0.45)
        light.setColorAt(0, QColor(255, 255, 255, 136))
        light.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(light)
        painter.drawEllipse(disc)
        font = QFont(self.font())
        font.setPixelSize(16)
        font.setWeight(QFont.ExtraBold)
        painter.setFont(font)
        painter.setPen(QColor("#10131a"))
        painter.drawText(disc, int(Qt.AlignCenter), self.letter)
        painter.end()


def _chip(words: str, gold: bool = False) -> QLabel:
    """A chip (``.chip``, ``.chip.gold``): a roll or an option, its words wrapping where it is wider than its card."""
    chip = _label(words, "chipGold" if gold else "chip")
    chip.setAlignment(Qt.AlignHCenter)
    return chip


class ItemIcon(SkillIcon):
    """An item's picture (``itemIcon``): in its grade's colour, its enchant level at the corner."""

    def __init__(self, size: int, item=None, parent: QWidget | None = None):
        item = r._dict(item)
        super().__init__(size, f"+{r.js_text(item['enchant'])}" if item.get("enchant") else "", parent, placeholder="◇")
        self.edge = QColor(_colour(item)) if _grade(item) else QColor(theme.COLORS["line2"])

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 5, 5)
        painter.setPen(self.edge)
        painter.drawPath(frame)
        painter.end()


def _plate_light(colour: str) -> str:
    """A title plate's light (``.tplate``): its grade's colour at a tenth across its middle, over the panel."""
    tint, panel = _css_colour(colour), QColor(theme.COLORS["panel2"])
    share = 0.1 * tint.alphaF()
    mid = QColor(*(round(share * a + (1 - share) * b) for a, b in ((tint.red(), panel.red()), (tint.green(), panel.green()),
                                                                     (tint.blue(), panel.blue()))))
    return (f"qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 {panel.name()}, stop: 0.5 {mid.name()}, "
            f"stop: 1 {panel.name()})")


def _grade_edges() -> str:
    """Each grade's colour (``--gc``) on a doll tile's left edge, on the top edge of an item's card, a path step and an
    arcana card, and lighting a title plate."""
    rules = []
    for grade, colour in r.GRADES.items():
        rules.append(f'QPushButton#dslot[grade="{grade}"] {{ border-left-color: {colour}; }}')
        rules.append(f'QFrame#icard[grade="{grade}"], QFrame#pstep[grade="{grade}"], QFrame#acard[grade="{grade}"] '
                     f'{{ border-top-color: {colour}; }}')
        rules.append(f'QFrame#tplate[grade="{grade}"] {{ background: {_plate_light(colour)}; }}')
    return "\n".join(rules)


STYLE = f"""
QLabel#chip {{ background: rgba(57, 194, 224, 0.10); border: 1px solid rgba(57, 194, 224, 0.35); border-radius: 9px;
               padding: 1px 7px; color: #9fe3f2; }}
QLabel#chipGold {{ background: rgba(233, 203, 128, 0.10); border: 1px solid rgba(233, 203, 128, 0.45); border-radius: 9px;
                   padding: 1px 7px; color: {theme.COLORS['gold']}; }}
QFrame#topRow {{ background: {theme.COLORS['panel2']}; border: 1px solid {theme.COLORS['line']}; border-radius: 5px; }}
QFrame#topRow QLabel {{ background: transparent; }}
QLabel#topMark {{ background: {INSET}; border: 1px solid {FRAME}; border-radius: 13px; color: {theme.COLORS['gold']}; }}
QLabel#tip {{ padding: 7px 10px; border-left: 3px solid {theme.COLORS['accent']}; background: rgba(57, 194, 224, 0.06);
              border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
QPushButton#dslot {{ text-align: left; background: {theme.COLORS['panel2']}; border: 1px solid {theme.COLORS['line']};
                     border-left: 3px solid {theme.COLORS['line2']}; border-radius: 5px; padding: 4px; }}
QPushButton#dmini {{ background: {theme.COLORS['panel2']}; border: 1px solid {theme.COLORS['line']}; border-radius: 5px; padding: 2px; }}
QLabel#dsl {{ color: {theme.COLORS['faint']}; letter-spacing: 0.6px; }}
QFrame#dcenter {{ border: 1px solid {theme.COLORS['line']}; border-radius: 6px;
                  background: qradialgradient(cx: 0.5, cy: 0.35, radius: 0.6, fx: 0.5, fy: 0.35, stop: 0 #29292a, stop: 1 #0a0e16); }}
QFrame#dcenter QLabel {{ background: transparent; }}
QLabel#dcls {{ color: {theme.COLORS['gold']}; font-size: 22px; font-weight: 700; letter-spacing: 1px; }}
QLabel#badgeUp {{ background: rgba(92, 184, 92, 0.18); color: {GAIN}; border: 1px solid rgba(92, 184, 92, 0.45);
                  border-radius: 3px; padding: 0 5px; font-weight: 700; }}
QLabel#badgeGoal {{ background: rgba(233, 203, 128, 0.12); color: {theme.COLORS['gold']}; border: 1px solid {FRAME};
                    border-radius: 3px; padding: 0 5px; font-weight: 700; }}
QLabel#badgeStep {{ background: rgba(57, 194, 224, 0.12); color: #9fe3f2; border: 1px solid rgba(57, 194, 224, 0.3);
                    border-radius: 3px; padding: 0 5px; font-weight: 700; }}
QFrame#icard {{ background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 {theme.COLORS['card_a']}, stop: 1 {theme.COLORS['card_b']});
                border: 1px solid {FRAME}; border-top: 3px solid {FRAME}; border-radius: 7px; }}
QFrame#icard QLabel {{ background: transparent; }}
QLabel#ilabel {{ color: {theme.COLORS['faint']}; letter-spacing: 0.7px; }}
QLabel#arr {{ color: {theme.COLORS['gold_dim']}; font-size: 20px; }}
QFrame#pstep {{ background: {theme.COLORS['panel2']}; border: 1px solid {theme.COLORS['line']}; border-top: 3px solid {theme.COLORS['line2']};
                border-radius: 6px; }}
QFrame#pstep QLabel {{ background: transparent; }}
QLabel#pn {{ color: {theme.COLORS['gold']}; font-weight: 800; }}
QLabel#kind {{ background: #0b0f18; border: 1px solid {FRAME}; color: {theme.COLORS['gold']}; border-radius: 11px; }}
QLabel#gold {{ color: {theme.COLORS['gold']}; font-weight: 700; }}
QLabel#aHead {{ color: {theme.COLORS['gold']}; font-weight: 700; letter-spacing: 0.6px; }}
QLabel#faint {{ color: {theme.COLORS['faint']}; }}
QFrame#acard {{ background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 {theme.COLORS['card_a']}, stop: 1 {theme.COLORS['card_b']});
                border: 1px solid {FRAME}; border-top: 3px solid {FRAME}; border-radius: 8px; }}
QFrame#acard QLabel, QFrame#acard QWidget#plain {{ background: transparent; }}
QLabel#acardTitle {{ color: {theme.COLORS['gold']}; font-weight: 800; letter-spacing: 0.8px; }}
QLabel#deity {{ color: {theme.COLORS['accent']}; }}
QLabel#asub {{ color: {theme.COLORS['faint']}; letter-spacing: 0.8px; margin-top: 8px; }}
QFrame#ownedRow {{ border: none; border-top: 1px dashed {theme.COLORS['line']}; background: transparent; }}
QFrame#tplate {{ border: 1px solid {FRAME}; border-radius: 6px; background: {_plate_light(theme.COLORS['gold'])}; }}
QFrame#tplate QLabel, QFrame#tplate QWidget#plain {{ background: transparent; }}
QFrame#dtile {{ background: {theme.COLORS['panel2']}; border: 1px solid {theme.COLORS['line']}; border-radius: 6px; }}
QFrame#dtile[best="true"] {{ border-color: {FRAME_HI}; }}
QFrame#dtile QLabel {{ background: transparent; }}
QLabel#dn {{ font-weight: 700; }}
QLabel#pts {{ color: {theme.COLORS['gold']}; font-size: 20px; font-weight: 800; }}
QFrame#prow {{ background: {INSET}; border: 1px solid #1d2539; border-radius: 6px; }}
QFrame#prow QLabel, QFrame#prow QWidget#plain {{ background: transparent; }}
QProgressBar#cum {{ background: {INSET}; border: none; border-radius: 3px; min-height: 18px; max-height: 18px; text-align: center;
                    font-weight: 700; color: {theme.COLORS['text']}; }}
QProgressBar#cum::chunk {{ background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #3c7a3c, stop: 1 #5cb85c); border-radius: 3px; }}
{_grade_edges()}
QPushButton#dslot:hover, QPushButton#dslot:checked, QPushButton#dmini:hover, QPushButton#dmini:checked {{
    border-color: {FRAME_HI}; background: {theme.COLORS['hover']}; }}
"""


class AdviceView(QWidget):
    """An advice's windows. ``open_web`` opens the web page (for the parts not drawn here yet), ``clipboard`` takes
    the words a window's "Copy as text" copies and ``open_link`` an item's page; both default to the system's."""

    def __init__(self, api, advice: dict, open_web=None, clipboard=None, open_link=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.advice, self.open_web = advice if isinstance(advice, dict) else {}, open_web
        self.clipboard = clipboard or (lambda text: QGuiApplication.clipboard().setText(text))
        self.open_link = open_link or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.icons = Icons(api, self)
        self.icons.loaded.connect(self._icon)
        self.pixmaps: dict[str, QPixmap] = {}
        self.shown_icons: list[SkillIcon] = []
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(14)
        self.tiles: dict[str, QPushButton] = {}
        for part in (self._top, self._specialties, self._equipment, self._path, self._arcana, self._titles,
                     self._pantheon, self._rest, self._fights):
            widget = part()
            if widget is not None:                         # no titles in the advice: no window
                self.box.addWidget(widget)
        self.box.addStretch(1)
        self.show_slot(a_.first_slot(self.advice))

    # ---------------------------------------------------------------- pictures
    def _picture(self, widget: SkillIcon, url) -> SkillIcon:
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
            try:
                if widget.path == path:
                    widget.set_pixmap(self.pixmaps[path])
            except RuntimeError:                       # a picture of a slot drawn again since
                pass
        for board in self.findChildren(PantheonBoard):
            board.set_picture(path, self.pixmaps[path])

    def item_icon(self, size: int, item) -> ItemIcon:
        return self._picture(ItemIcon(size, item), r._dict(item).get("icon"))

    def _window(self, title: str, subtitle: str = "", copy: str = "") -> Window:
        window = Window(title, subtitle)
        if not subtitle:
            window.head.addStretch(1)
        if copy:
            button = QPushButton("Copy as text")
            button.setObjectName("small")
            button.clicked.connect(lambda _checked=False: self.clipboard(copy))
            window.tool(button)
        return window

    # ---------------------------------------------------------------- top changes
    def _top(self) -> Window:
        a = self.advice
        window = self._window("Top changes", a_.top_subtitle(a), a_.top_copy(a))
        for mark, area, text, gain in a_.top_rows(a):
            row = QFrame()                               # ``.top``
            row.setObjectName("topRow")
            line = QHBoxLayout(row)
            line.setContentsMargins(10, 6, 10, 6)
            line.setSpacing(10)
            sign = _label(mark, "topMark", wrap=False)
            sign.setAlignment(Qt.AlignCenter)
            sign.setFixedSize(26, 26)
            line.addWidget(sign, 0, Qt.AlignVCenter)
            words = _plain()
            column = QVBoxLayout(words)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            column.addWidget(_label(area, "muted"))
            column.addWidget(_label(text))
            line.addWidget(words, 1)
            if gain:
                line.addWidget(_label(f"<b style='color: {GAIN};'>{html.escape(gain)}</b>", rich=True, wrap=False), 0, Qt.AlignVCenter)
            window.body.addWidget(row)
        window.body.addWidget(_label(f"Saved as <code>{html.escape(r.js_text(a.get('file') or ''))}</code>", "faint", rich=True))
        return window

    # ---------------------------------------------------------------- skill specialties
    def _specialties(self) -> Window:
        a = self.advice
        rows = a_.specialty_rows(a)
        if rows is None:
            window = self._window("Skill specialties")
            window.body.addWidget(_label(a_.SPECIALTIES_OLD, "muted"))
            return window
        window = self._window("Skill specialties", a_.SPECIALTIES_SUB, a_.specialties_copy(a))
        window.body.addWidget(_label(a_.SPECIALTIES_NOTE, "muted", rich=True))
        cells = []
        for row in rows:
            skill = _label(f"{html.escape(row['skill'])}<br>{r.muted(html.escape(row['slots']))}", rich=True)
            chosen = _plain()
            column = QVBoxLayout(chosen)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            if row["chosen"]:
                for number, text, unlock in row["chosen"]:
                    column.addWidget(_label(f"<b>#{html.escape(number)}</b> {html.escape(text)} "
                                            f"<span style='color: {theme.COLORS['faint']};'>({html.escape(unlock)})</span>", rich=True))
            else:
                column.addWidget(_label("None unlocked/selected"))
            fold = Fold("All effects and requirements")
            for line in row["every"]:
                fold.add(_label(line, "muted"))
            column.addWidget(fold)
            chosen.setProperty("fill", True)
            cells.append([skill, chosen, row["unlock"]])
        window.body.addWidget(GridTable(["Skill / effective level", "Recommended specialties", "Next unlock"], cells,
                                        {0: 2, 1: 4, 2: 1}, left=True))
        return window

    # ---------------------------------------------------------------- the paper doll
    def _tile(self, slot: str) -> QPushButton:
        t = a_.doll_tile(self.advice, slot)
        button = QPushButton()
        button.setObjectName("dslot")
        button.setProperty("grade", _grade(t["item"]))
        button.setCheckable(True)
        button.setAccessibleName(f"{t['slot_name']}: {t['name']}")
        button.setMinimumHeight(48)
        line = QHBoxLayout(button)
        line.setContentsMargins(6, 4, 6, 4)
        line.setSpacing(8)
        line.addWidget(self.item_icon(36, t["item"]))
        words = _plain()
        words.setAttribute(Qt.WA_TransparentForMouseEvents)
        column = QVBoxLayout(words)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(_label(t["slot_name"].upper(), "dsl", wrap=False))
        column.addWidget(_label(f"<span style='color: {_colour(t['item'])}; font-weight: 600;'>{html.escape(t['name'])}</span>",
                                rich=True, wrap=False))
        line.addWidget(words, 1)
        if t["badge"] or t["step"]:
            marks = _plain()                               # ``.badge`` at the tile's top right, ``.badge.step`` under it
            column = QVBoxLayout(marks)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            if t["badge"]:
                kind, badge = t["badge"]
                column.addWidget(_label(badge, "badgeUp" if kind == "up" else "badgeGoal", wrap=False), 0, Qt.AlignRight)
            column.addStretch(1)
            if t["step"]:
                column.addWidget(_label(t["step"], "badgeStep", wrap=False), 0, Qt.AlignRight)
            line.addWidget(marks)
        for child in button.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        button.clicked.connect(lambda _checked=False, slot=slot: self.show_slot(slot))
        self.tiles[slot] = button
        return button

    def _equipment(self) -> Window:
        a = self.advice
        window = self._window("Equipment", a_.EQUIPMENT_SUB, a_.doll_copy(a))
        doll = _plain()
        grid = QGridLayout(doll)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        for index, slot in enumerate(a_.DOLL_LEFT):
            grid.addWidget(self._tile(slot), index, 0)
        for index, slot in enumerate(a_.DOLL_RIGHT):
            grid.addWidget(self._tile(slot), index, 2)
        middle = QFrame()
        middle.setObjectName("dcenter")
        middle.setFixedWidth(240)
        column = QVBoxLayout(middle)
        column.setContentsMargins(14, 14, 14, 14)
        column.setSpacing(8)
        cls, who, dps = a_.character_lines(a)
        column.addStretch(1)
        column.addWidget(_label(cls.upper(), "dcls", wrap=False), 0, Qt.AlignHCenter)
        column.addWidget(_label(who, wrap=False), 0, Qt.AlignHCenter)
        column.addWidget(_centred(_label(f"<span style='font-size: 26px; font-weight: 800;'>{html.escape(dps)}</span><br>"
                                         f"<span style='color: {theme.COLORS['muted']}; font-weight: 600;'>boss DPS</span>",
                                         rich=True, wrap=False)), 0, Qt.AlignHCenter)
        legend = _plain()                                  # ``.legend2``
        rows = QGridLayout(legend)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setHorizontalSpacing(6)
        rows.setVerticalSpacing(5)
        for index, (mark, name, words) in enumerate((("▲", "badgeUp", "better item in your inventory"),
                                                     ("◆", "badgeGoal", "next goal gain"), ("#", "badgeStep", "upgrade path step"))):
            rows.addWidget(_label(mark, name, wrap=False), index, 0, Qt.AlignRight | Qt.AlignTop)
            rows.addWidget(_label(words, "muted"), index, 1)
        column.addWidget(legend)
        arcana = _plain()
        row = QHBoxLayout(arcana)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for slot in a_.ARCANA_SLOTS:
            worn = r._dict(r._dict(r._dict(a.get("doll")).get(slot)).get("worn")) or None
            mini = QPushButton()
            mini.setObjectName("dmini")
            mini.setCheckable(True)
            mini.setToolTip(slot)
            mini.setAccessibleName(slot)
            box = QHBoxLayout(mini)
            box.setSizeConstraint(QLayout.SetMinimumSize)     # a button's own size leaves its picture out
            box.setContentsMargins(3, 3, 3, 3)
            box.addWidget(self.item_icon(30, worn))
            mini.clicked.connect(lambda _checked=False, slot=slot: self.show_slot(slot))
            self.tiles[slot] = mini
            row.addWidget(mini)
        column.addWidget(arcana, 0, Qt.AlignHCenter)
        column.addStretch(1)
        grid.addWidget(middle, 0, 1, len(a_.DOLL_LEFT), 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        window.body.addWidget(doll)
        holder = _plain()
        self.way = QVBoxLayout(holder)                       # ``#dslotinfo``
        self.way.setContentsMargins(0, 8, 0, 0)
        self.way.setSpacing(6)
        window.body.addWidget(holder)
        return window

    def _card(self, card: dict, extra: list[QWidget]) -> QFrame:
        """A card of the slot's way (``itemCard``), its words in its middle."""
        frame = QFrame()
        frame.setObjectName("icard")
        frame.setMinimumWidth(150)
        frame.setMaximumWidth(220)
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(4)
        column.addWidget(_centred(_label(card["label"].upper(), "ilabel")))
        if card["empty"]:
            column.addWidget(_centred(_label("—", "faint")))
            column.addStretch(1)
            return _dimmed(frame)
        frame.setProperty("grade", _grade(card["item"]))
        column.addWidget(self.item_icon(60, card["item"]), 0, Qt.AlignHCenter)
        colour = _colour(card["item"])
        if card["url"]:
            name = _label(f"<a href='{html.escape(card['url'])}' style='color: {colour}; font-weight: 600;'>"
                          f"{html.escape(card['name'])}</a>", rich=True)
            name.linkActivated.connect(self._link)
        else:
            name = _label(f"<span style='color: {colour}; font-weight: 600;'>{html.escape(card['name'])}</span>", rich=True)
        column.addWidget(_centred(name))
        column.addWidget(_centred(_label(card["meta"], "muted")))
        if card["gain"] is not None:
            column.addWidget(_centred(_label(f"<b style='color: {DOWN if card['down'] else GAIN};'>"
                                             f"{html.escape(card['gain'])}</b>", rich=True)))
        for widget in extra:
            column.addWidget(_centred(widget) if isinstance(widget, QLabel) else widget)
        column.addStretch(1)
        return frame

    def _chips(self, chips: list[tuple[str, bool]], align=Qt.AlignHCenter) -> QWidget:
        row = _plain()
        flow = FlowLayout(row, align=align, gap=(4, 4))
        for words, gold in chips:
            flow.addWidget(_chip(words, gold))
        return row

    def show_slot(self, slot: str) -> None:
        """A slot's way (``bindDoll``'s ``show``), its tile marked."""
        for key, tile in self.tiles.items():
            tile.setChecked(key == slot)
        while self.way.count():
            child = self.way.takeAt(0)
            if child.widget() is not None:
                child.widget().hide()
                child.widget().deleteLater()
        way = a_.slot_way(self.advice, slot)
        self.way.addWidget(_label(way["title"], "aHead"))
        flow = _plain()
        line = QHBoxLayout(flow)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        worn, worn_chips = way["worn"]
        wear, wear_chips = way["wear"]
        nxt, nxt_chase = way["next"]
        best, best_chase = way["best"]
        cards = [self._card(worn, [self._chips(worn_chips)] if worn_chips else []),
                 self._card(wear, [self._chips(wear_chips)] if wear_chips else [])]
        if way["keep"]:
            keep = QFrame()                               # ``.icard.empty[data-keep]``
            keep.setObjectName("icard")
            keep.setMinimumWidth(150)
            keep.setMaximumWidth(220)
            column = QVBoxLayout(keep)
            column.setContentsMargins(10, 10, 10, 10)
            column.addWidget(_centred(_label("NEXT GOAL", "ilabel")))
            column.addWidget(_centred(_label(way["keep"])))
            column.addStretch(1)
            cards.append(_dimmed(keep))
        else:
            cards.append(self._card(nxt, self._chase(nxt_chase)))
        cards.append(self._card(best, self._chase(best_chase)))
        for index, card in enumerate(cards):
            if index:
                line.addWidget(_label("➜", "arr", wrap=False), 0, Qt.AlignVCenter)
            line.addWidget(card, 1)
        line.addStretch(0)
        self.way.addWidget(flow)
        if way["steps"]:
            self.way.addWidget(_label(way["steps"], "muted"))

    def _chase(self, rolls: list[str]) -> list[QWidget]:
        if not rolls:
            return []
        return [_label("roll toward", "faint"), self._chips([(roll, True) for roll in rolls])]

    # ---------------------------------------------------------------- the upgrade path
    def _path(self) -> Window:
        a = self.advice
        window = self._window("Upgrade path", a_.PATH_SUB, a_.path_copy(a))
        steps = _plain()
        flow = QHBoxLayout(steps)                         # ``.path``: one row, scrolled across
        flow.setContentsMargins(0, 0, 0, 6)
        flow.setSpacing(10)
        for step in a_.path_steps(a):
            frame = QFrame()
            frame.setObjectName("pstep")
            frame.setProperty("grade", _grade(step["item"]))
            frame.setFixedWidth(150)
            column = QVBoxLayout(frame)
            column.setContentsMargins(8, 8, 8, 10)
            column.setSpacing(3)
            head = _plain()
            line = QHBoxLayout(head)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            line.addWidget(_label(step["step"], "pn", wrap=False))
            line.addWidget(_label(step["slot"].upper(), "dsl", wrap=False))
            line.addStretch(1)
            column.addWidget(head)
            picture = _plain()
            icon_row = QHBoxLayout(picture)
            icon_row.setContentsMargins(0, 0, 0, 0)
            icon_row.setSpacing(4)
            icon_row.addStretch(1)
            icon_row.addWidget(self.item_icon(60, step["item"]))
            mark = _label(step["mark"], "kind", wrap=False)      # ``.kind``, at the picture's corner
            mark.setAlignment(Qt.AlignCenter)
            mark.setFixedSize(22, 22)
            mark.setToolTip(step["kind"])
            icon_row.addWidget(mark, 0, Qt.AlignTop)
            icon_row.addStretch(1)
            column.addWidget(picture)
            column.addWidget(_centred(_label(f"<span style='color: {_colour(step['item'])}; font-weight: 600;'>"
                                             f"{html.escape(step['name'])}</span>", rich=True)))
            column.addWidget(_centred(_label(step["action"], "faint")))
            if step["rolls"]:
                column.addWidget(self._chips([(roll, True) for roll in step["rolls"]]))
            column.addWidget(_centred(_label(f"<b style='color: {GAIN};'>{html.escape(step['gain'])}</b>", rich=True)))
            bar = QProgressBar()                          # ``.cum``: the gain so far, its share of the path's
            bar.setObjectName("cum")
            bar.setRange(0, 1000)
            bar.setValue(round(step["share"] * 10))
            bar.setFormat(step["total"])
            bar.setAlignment(Qt.AlignCenter)
            column.addWidget(bar)
            column.addStretch(1)
            flow.addWidget(frame)
        flow.addStretch(1)
        window.body.addWidget(Across(steps))
        return window

    # ---------------------------------------------------------------- arcana
    def skill_icon(self, size: int, level: str, url: str) -> SkillIcon:
        return self._picture(SkillIcon(size, level, placeholder="◇"), url)

    def _option(self, name: str, level: str, url: str) -> QWidget:
        """A skill option (``arcanaOption``): the skill's picture with the option's level, beside its name."""
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        icon = self.skill_icon(32, f"+{level}", url)
        icon.setToolTip(f"{name} +{level}")
        line.addWidget(icon)
        line.addWidget(_label(name), 1)
        return row

    def _arcana_card(self, card: dict) -> QFrame:
        frame = QFrame()                                  # ``.acard``
        frame.setObjectName("acard")
        frame.setProperty("grade", card["grade"])
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(3)
        head = _plain()
        grid = QGridLayout(head)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(_label(card["slot"], "acardTitle", wrap=False), 0, 0, Qt.AlignHCenter)
        grid.addWidget(_label(card["priority"], "muted", wrap=False), 0, 0, Qt.AlignRight)
        column.addWidget(head)
        column.addWidget(self.item_icon(78, card["item"]), 0, Qt.AlignHCenter)
        column.addWidget(_centred(_label(f"<span style='color: {_colour(card['item'])}; font-weight: 600;'>"
                                         f"{html.escape(card['name'])}</span>", rich=True)))
        column.addWidget(_centred(_label(card["deity"], "deity")))
        column.addWidget(_centred(_label("TARGET OPTIONS · UNIQUE +5", "asub")))
        for name, level, url in card["options"]:
            column.addWidget(self._option(name, level, url))
        values = _label(f"ideal <b style='color: {GAIN};'>{html.escape(card['ideal'])}</b>&nbsp;&nbsp;&nbsp;"
                        f"average <b style='color: {GAIN};'>{html.escape(card['average'])}</b>", "muted", rich=True)
        column.addWidget(_centred(values))
        if card["owned"]:
            column.addWidget(_centred(_label("YOURS", "asub")))
            for owned in card["owned"]:
                column.addWidget(self._owned(owned))
        column.addStretch(1)
        return frame

    def _owned(self, o: dict) -> QWidget:
        """A card you have (``arcanaOwned``): keep or replace, then what it holds."""
        box = _plain()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(5)
        row = QFrame()                                    # ``.owned``
        row.setObjectName("ownedRow")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 3, 0, 3)
        line.setSpacing(5)
        line.addWidget(self.item_icon(24, o["item"]))
        name, gain = _label(o["name"]), _label(o["gain"], wrap=False)
        if not o["keep"]:
            for label in (name, gain):
                label.setStyleSheet(f"color: {DOWN};")
        line.addWidget(name, 1)
        line.addWidget(gain)
        line.addWidget(_chip("keep" if o["keep"] else "replace", gold=o["keep"]), 0, Qt.AlignVCenter)
        column.addWidget(row)
        if o["deity"]:
            deity = _centred(_label(o["deity"], "deity"))
            deity.setToolTip(o["deity_tip"])
            column.addWidget(deity)
        if o["stats"]:
            column.addWidget(_centred(_label(o["stats"], "muted")))
        if o["options"]:
            for name, level, url in o["options"]:
                column.addWidget(self._option(name, level, url))
        else:
            column.addWidget(_centred(_label("No skill options", "faint")))
        if o["facts"]:
            column.addWidget(_centred(_label(o["facts"], "faint")))
        return box

    def _arcana(self) -> Window:
        a = self.advice
        window = self._window("Arcana", a_.ARCANA_SUB, a_.arcana_copy(a))
        cards = [self._arcana_card(card) for card in a_.arcana_cards(a)]
        if cards:
            window.body.addWidget(Columns(cards, 5, 2))
        return window

    # ---------------------------------------------------------------- titles
    def _plate(self, plate: dict) -> QFrame:
        """A title's plate (``titlePlate``)."""
        frame = QFrame()
        frame.setObjectName("tplate")
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(2)
        head = _plain()
        grid = QGridLayout(head)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(_centred(_label(plate["label"].upper(), "ilabel")), 0, 0)
        column.addWidget(head)
        if plate["empty"]:
            column.addWidget(_centred(_label("—", "faint")))
            return _dimmed(frame)
        frame.setProperty("grade", plate["grade"])
        if plate["gain"] is not None:
            gain, up = plate["gain"]
            grid.addWidget(_label(f"<b style='color: {GAIN if up else DOWN};'>{html.escape(gain)}</b>", rich=True, wrap=False),
                           0, 0, Qt.AlignRight | Qt.AlignTop)
        column.addWidget(_centred(_label(f"<span style='color: {_colour(plate)}; font-weight: 600;'>"
                                         f"{html.escape(plate['name'])}</span>", rich=True)))
        for label, words in (("equipped", plate["equip"]), ("owned", plate["owned"])):
            if words:
                column.addWidget(_centred(_label(f"<span style='color: {theme.COLORS['muted']};'>{label}:</span> "
                                                 f"{html.escape(words)}", rich=True)))
        if plate["how"]:
            how = _centred(_label(plate["how"], "faint"))
            how.setToolTip(plate["how_full"])
            column.addWidget(how)
        for kind, words in plate["extra"]:
            if kind == "cut":
                cut = _centred(_label(f"<b style='color: {GAIN};'>{html.escape(words)}</b>", rich=True))
                cut.setToolTip("Damage Tolerance lowers the attacker's damage boost")
                column.addWidget(cut)
            else:
                column.addWidget(_chip(words, gold=True), 0, Qt.AlignHCenter)
        column.addStretch(1)
        return frame

    def _titles(self) -> Window | None:
        a = self.advice
        columns = a_.title_columns(a)
        if columns is None:
            return None
        window = self._window("Titles", a_.TITLES_SUB, a_.titles_copy(a))
        cells = []
        for col in columns:
            cell = _plain()
            column = QVBoxLayout(cell)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(6)
            column.addWidget(_label(col["title"], "acardTitle"))
            for plate in col["plates"]:
                column.addWidget(self._plate(plate))
            column.addWidget(_label("BEST IN SLOT", "asub"))
            if col["guard"] is not None:
                column.addWidget(_label(col["guard"]["note"], "faint"))
                for plate in col["guard"]["plates"]:
                    column.addWidget(self._plate(plate))
            for plate in col["best"]:
                column.addWidget(self._plate(plate))
            column.addStretch(1)
            cells.append(cell)
        window.body.addWidget(Columns(cells, 3, 1))
        note = a_.titles_note(a)
        if note:
            window.body.addWidget(_label(note, "faint"))
        collect = a_.titles_collect(a)
        if collect:
            window.body.addWidget(_label(a_.COLLECT_HEAD, "aHead"))
            window.body.addWidget(Columns([self._plate(plate) for plate in collect], 4, 1, gap=8))
        return window

    # ---------------------------------------------------------------- pantheon
    def _deity(self, tile: dict) -> QFrame:
        frame = QFrame()                                  # ``.dtile``
        frame.setObjectName("dtile")
        frame.setProperty("best", tile["best"])
        column = QVBoxLayout(frame)
        column.setContentsMargins(6, 8, 6, 8)
        column.setSpacing(2)
        column.addWidget(Sigil(tile["sigil"], tile["colour"]), 0, Qt.AlignHCenter)
        column.addWidget(_centred(_label(tile["deity"], "dn")))
        column.addWidget(_centred(_label(tile["lord"], "dsl")))
        column.addWidget(_centred(_label(tile["points"], "pts")))
        fx = _centred(_label(tile["fx"], "muted"))
        fx.setMinimumHeight(26)
        column.addWidget(fx)
        bar = Bar(tile["share"], tile["worth"])
        bar.setMinimumWidth(0)
        column.addWidget(bar)
        if tile["best"]:
            column.addWidget(_chip("best for damage", gold=True), 0, Qt.AlignHCenter)
        column.addStretch(1)
        if tile["dim"]:
            return _dimmed(frame, 0.55)
        if tile["best"]:                                   # ``box-shadow: 0 0 12px``
            glow = QGraphicsDropShadowEffect(frame)
            glow.setBlurRadius(12)
            glow.setOffset(0, 0)
            glow.setColor(QColor(233, 203, 128, 64))
            frame.setGraphicsEffect(glow)
        return frame

    def _decoration(self, row: dict) -> QFrame:
        """A decoration in the board's list (``.prow``)."""
        frame = QFrame()
        frame.setObjectName("prow")
        grid = QGridLayout(frame)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        name = _plain()
        line = QHBoxLayout(name)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        if row["icon"]:
            line.addWidget(self._picture(SkillIcon(32, ""), row["icon"]))
        colour = f" style='color: {row['colour']};'" if row["colour"] else ""
        words = f"<b{colour}>{html.escape(row['name'])}</b>"
        if row["faction"]:
            words += f" <span style='color: {theme.COLORS['faint']};'>{html.escape(row['faction'])}</span>"
        line.addWidget(_label(words, rich=True))
        if row["grade"]:
            line.addWidget(_chip(row["grade"]), 0, Qt.AlignVCenter)
        line.addStretch(1)
        grid.addWidget(name, 0, 0)
        grid.addWidget(_label(" · ".join(f"{html.escape(d)} <b>{html.escape(v)}</b>" for d, v in row["stats"]), rich=True), 0, 1)
        grid.addWidget(_label(f"<b style='color: {GAIN};'>{html.escape(row['gain'])}</b>", rich=True, wrap=False), 0, 2,
                       Qt.AlignRight)
        grid.addWidget(_label(row["sources"], "muted"), 1, 0, 1, 3)
        grid.setColumnStretch(0, 12)
        grid.setColumnStretch(1, 16)
        return frame

    def _board_list(self, board: dict) -> QWidget:
        listed = a_.board_list(board)
        box = _plain()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        totals = _plain()
        flow = FlowLayout(totals, align=Qt.AlignLeft, gap=(4, 4))
        flow.addWidget(_label("<b>Board total</b>", rich=True, wrap=False))
        for short, points, deity in listed["totals"]:
            chip = _chip(f"{short} {points}")
            chip.setToolTip(deity)
            flow.addWidget(chip)
        flow.addWidget(_label(f"<b style='color: {GAIN};'>{html.escape(listed['gain'])}</b> vs an empty board", rich=True,
                              wrap=False))
        column.addWidget(totals)
        for ring in listed["rings"]:
            column.addWidget(_label(ring["head"], "aHead"))
            if ring["rows"]:
                for row in ring["rows"]:
                    column.addWidget(self._decoration(row))
            else:
                column.addWidget(_label(a_.NO_DECORATION, "faint"))
            if ring["next"]:
                fold = Fold(ring["next_head"])
                for row in ring["next"]:
                    fold.add(self._decoration(row))
                column.addWidget(fold)
        column.addWidget(_label(listed["note"], "faint"))
        return box

    def _pantheon(self) -> Window:
        a = self.advice
        p = r._dict(a.get("pantheon"))
        window = self._window("Pantheon", a_.PANTHEON_SUB, a_.pantheon_copy(a))
        window.body.addWidget(Columns([self._deity(tile) for tile in a_.deity_tiles(a)], 10, 2, gap=8))
        for choice in a_.deity_choices(a):
            deity = f" <span>({html.escape(choice['deity'])})</span>" if choice["deity"] else ""
            window.body.addWidget(_label(f"<span style='color: {theme.COLORS['muted']};'>{html.escape(choice['source'])}</span> "
                                         f"<b>{html.escape(choice['pick'])}</b>{deity} "
                                         f"<b style='color: {GAIN};'>{html.escape(choice['gain'])}</b>", rich=True))
        if r._truthy(p.get("board")):
            board = r._dict(p["board"])
            window.body.addWidget(_label(a_.BOARD_HEAD, "aHead"))
            window.body.addWidget(_label(a_.BOARD_NOTE, "muted"))
            stands = a_.board_stands(board)
            paths = {}
            for kind, rows in (("colossus", [stands["colossus"]]), ("statue", stands["statues"]), ("artwork", stands["artworks"])):
                for index, stand in enumerate(rows):
                    if stand["icon"]:
                        paths[f"{kind}:{index}"] = icon_path(stand["icon"])
            drawn = PantheonBoard(stands, paths)
            for path in set(paths.values()):
                if path in self.pixmaps:
                    drawn.set_picture(path, self.pixmaps[path])
                else:
                    self.icons.ask(path)
            pair = _plain()                                # ``.pwrap``
            line = QHBoxLayout(pair)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(16)
            line.addWidget(drawn, 0, Qt.AlignTop)
            line.addWidget(self._board_list(board), 1)
            window.body.addWidget(pair)
        return window

    # ---------------------------------------------------------------- the genus, on the web page for now
    def _rest(self) -> Window:
        window = self._window("Genus Insight")
        window.body.addWidget(_label("The genus recommendations open in the web interface for now.", "muted"))
        button = QPushButton("Open them on the web page")
        button.setObjectName("small")
        button.clicked.connect(lambda _checked=False: self.open_web("gear") if self.open_web else None)
        row = _plain()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(button)
        line.addStretch(1)
        window.body.addWidget(row)
        return window

    # ---------------------------------------------------------------- the fights and the calibration
    def _fights(self) -> QWidget:
        a = self.advice
        f = a_.fights(a)
        pair = _plain()
        grid = QGridLayout(pair)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)
        fights = self._window("Your fights")
        for words in (f["summary"], f["compared"]):
            if words:
                fights.body.addWidget(_label(words))
        for tip in f["tips"]:
            fights.body.addWidget(_label(tip, "tip"))
        if f["missing"]:
            fights.body.addWidget(_label(f["missing"], "muted"))
        if f["recent"]:
            rows = [[self._fight(x), x["length"], x["dps"], x["source"],
                     _label(f"<span style='color: {theme.COLORS['faint']};'>{html.escape(x['when'])}</span>", rich=True)]
                    for x in f["recent"]]
            fights.body.addWidget(GridTable(["Fight", "Length", "DPS", "Source", "When"], rows, {0: 3}))
        if f["note"]:
            fights.body.addWidget(_label(f["note"], "faint"))
        calibration = self._window("Model calibration", a_.CALIBRATION_SUB)
        for line in a_.calibration(a):
            calibration.body.addWidget(_label(line))
        grid.addWidget(fights, 0, 0, Qt.AlignTop)
        grid.addWidget(calibration, 0, 1, Qt.AlignTop)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return pair

    def _fight(self, fight: dict) -> QLabel:
        """A recent fight's name, a link to its analysis on Combat Logs (on the web page for now)."""
        if not fight["page"]:
            return _label(fight["boss"])
        label = _label(f"<a href='web:{html.escape(fight['page'])}' style='color: {theme.COLORS['accent']};'>"
                       f"{html.escape(fight['boss'])}</a>", rich=True)
        label.linkActivated.connect(self._link)
        return label

    def _link(self, href: str) -> None:
        """A link clicked: a page of the web interface (``web:``) or an item's page elsewhere."""
        if href.startswith("web:"):
            if self.open_web is not None:
                self.open_web(href[4:])
        else:
            self.open_link(href)

    def stop(self) -> None:
        self.icons.stop()
