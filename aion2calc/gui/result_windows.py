"""A build's result windows in the native interface (0.2.434), as pages/results.js's ``renderWindows`` draws them for
the Build Planner, My Character and Saved Results: the side menu of the ten windows and the window chosen.

The native interface draws the Overview (its counts, notes, stat priority, damage and healing shares), Skills (active
and passive, each skill's level and supporting effects) and Stigma windows so far; each of the others says it is
drawn in the web interface for now, with the web page's button. The words are ``results.py``'s.
"""
from __future__ import annotations

import html
import urllib.parse

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from . import pictures
from . import results as r
from . import theme
from .database_page import Icons, Kpi, Window, pairs_grid
from .timers_page import Fold

WEB_NOTE = "This window is drawn in the web interface for now."
COMPARISON_NOTE = "Generating a comparison is on the web page for now."


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

    def __init__(self, size: int, level: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.level, self.pixmap = level, None
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
        painter.setPen(QColor(theme.COLORS["line2"]))
        painter.drawPath(frame)
        if self.level:
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(12)
            painter.setFont(font)
            width = painter.fontMetrics().horizontalAdvance(self.level) + 8
            height = painter.fontMetrics().height()
            badge = QRectF(1, self.height() - height - 1, width, height)
            painter.fillRect(badge, QColor(0, 0, 0, 184))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge, int(Qt.AlignCenter), self.level)
        painter.end()


class ResultWindows(QWidget):
    """A result's windows: the side menu and the chosen window (``renderWindows``). ``open_web`` opens a page of the
    web interface (the windows not drawn here yet); ``state`` keeps the chosen window and tabs, as the web page's
    state object does."""

    def __init__(self, api=None, open_web=None, web_page: str = "history", clipboard=None, when=None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.open_web, self.web_page = open_web, web_page
        self.clipboard = clipboard or (lambda text: QGuiApplication.clipboard().setText(text))
        self.when = when or (lambda ms: str(ms))
        self.view: dict = {}
        self.state = {"win": "overview", "skilltab": "active"}
        self.icons = Icons(api, self)
        self.icons.loaded.connect(self._icon)
        self.pixmaps: dict[str, QPixmap] = {}
        self.shown_icons: list[SkillIcon] = []
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
        self.shown_icons = []
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
        elif key == "overview":
            self.body.addWidget(self._overview())
            self.body.addWidget(self._comparison())
        else:
            self.body.addWidget(self._web_window(dict((k, t) for k, t, _m in r.WINDOWS)[key]))

    # ------------------------------------------------------------------ parts
    def _window(self, title: str, counter: str = "", copy: str = "") -> Window:
        window = Window(title)
        if counter:
            label = _label(counter, "counter", wrap=False)
            window.head.insertWidget(1, label)
            window.head.insertStretch(2, 1)                      # the counter beside the title, the tools at the end
        if copy:
            button = QPushButton("Copy as text")
            button.setObjectName("small")
            button.clicked.connect(lambda: self.clipboard(copy))
            window.tool(button)
        return window

    def _web_window(self, title: str) -> Window:
        window = self._window(title)
        window.body.addWidget(_label(WEB_NOTE, "muted"))
        window.body.addWidget(self._web_button(), 0, Qt.AlignLeft)
        return window

    def _web_button(self) -> QPushButton:
        button = QPushButton("Open the web Saved Results page" if self.web_page == "history" else "Open the web page")
        button.clicked.connect(lambda: self.open_web(self.web_page) if self.open_web else None)
        return button

    def _stat_grid(self, rows: list[tuple[str, str]], title: str) -> QWidget:
        box = QFrame()
        box.setObjectName("statsum")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_label(title.upper(), "statTitle"))
        columns = max(1, min(4, (max(self.width() - 246, 480) + 18) // (210 + 18)))
        layout.addWidget(pairs_grid([(name, html.escape(value)) for name, value in rows], columns))
        return box

    def _icon_widget(self, url, size: int, level: str) -> SkillIcon:
        widget = SkillIcon(size, level)
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

    # ------------------------------------------------------------------ the Overview
    def _overview(self) -> Window:
        v = self.view
        window = self._window("Overview")
        if v.get("loadout_name"):
            window.subtitle.setText(str(v["loadout_name"]))
            window.subtitle.show()
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
            column.addWidget(_label("Calculating stat priority…" if v.get("weight_job") else
                                    "Stat priority is unavailable for this build."))
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
        window.body.addWidget(self._stat_grid(r.skills_grid(v), "From this system"))
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
        window.body.addWidget(self._stat_grid(r.stigmas_grid(v), "Stats from this system"))
        return window

    def stop(self) -> None:
        self.icons.stop()


STYLE = f"""
QPushButton#sideItem, QPushButton#sideItemOn {{ text-align: left; padding: 9px 10px; border-radius: 4px; font-weight: 600;
    background: transparent; border: 1px solid transparent; color: {theme.COLORS['muted']}; }}
QPushButton#sideItemOn, QPushButton#sideItem:hover {{ color: {theme.COLORS['gold']}; background: rgba(232, 207, 142, 0.07);
    border-color: rgba(206, 182, 122, 0.28); }}
QLabel#counter {{ padding: 4px 10px; border: 1px solid rgba(206, 182, 122, 0.28); border-radius: 4px;
    background: rgba(6, 9, 15, 0.65); font-weight: 700; }}
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
"""
