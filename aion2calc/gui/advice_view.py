"""An advice's view (0.2.444), as pages/advice.js's ``renderAdvice`` draws it, its windows one under another:

- **Top changes:** each change's area, words and gain, ranked by simulated DPS gain, and where the advice was saved;
- **Skill specialties:** each skill's effective level and slots, the effects recommended (all of them, folded), and
  its next unlock;
- **Equipment:** the paper doll, each slot's tile with its badge (a better item from your inventory, or the next goal's
  gain) and its first upgrade path step; a slot clicked shows its way from what you wear to the best in slot;
- **Upgrade path:** one change at a time, biggest gain first, each with its rolls to chase, its gain and the gain so
  far;
- **Your fights** and **Model calibration**.

The arcana, titles, pantheon and genus advice are not drawn here yet: ``open_web`` opens them on the web page.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLayout, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from . import advice as a_
from . import pictures
from . import results as r
from . import theme
from .chrome import FlowLayout
from .database_page import Icons, Window
from .result_windows import Across, GridTable, SkillIcon, _css_colour, icon_path
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


def _dimmed(frame: QFrame) -> QFrame:
    """A card with nothing in it, at half its strength (``.icard.empty``)."""
    effect = QGraphicsOpacityEffect(frame)
    effect.setOpacity(0.5)
    frame.setGraphicsEffect(effect)
    return frame


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


def _grade_edges() -> str:
    """Each grade's colour (``--gc``) on a doll tile's left edge and on the top edge of an item's card and a path step."""
    rules = []
    for grade, colour in r.GRADES.items():
        rules.append(f'QPushButton#dslot[grade="{grade}"] {{ border-left-color: {colour}; }}')
        rules.append(f'QFrame#icard[grade="{grade}"], QFrame#pstep[grade="{grade}"] {{ border-top-color: {colour}; }}')
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
        for part in (self._top, self._specialties, self._equipment, self._path, self._rest, self._fights):
            self.box.addWidget(part())
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
        self.way.addWidget(_label(way["title"], "gearHead"))
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

    # ---------------------------------------------------------------- the rest, on the web page for now
    def _rest(self) -> Window:
        window = self._window("Arcana, titles, pantheon and genus")
        window.body.addWidget(_label("These recommendations open in the web interface for now.", "muted"))
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
