"""The featured encounters in the native Combat Logs page (0.2.455), as featured.js draws them. These are the
encounters the log server's operator puts at the top of Combat Logs.

- **FeaturedSection:** the landing cards above the views. Each encounter has its portrait, title, boss and difficulty,
  and its pages. Its cards are: progress, speed and execution by team; the all stars by role; and each role's classes
  by median DPS. It draws nothing when no encounter is featured, or when the server can't be reached.
- **FeaturedPage:** one encounter's page, shown in place of the views. It has five views:
  - the race summary: the phases over one bar, the teams under the phase each is on, and a closer look at the leaders;
  - progress: the teams by progress, and the final-boss kills;
  - all reports: the public logs of the encounter;
  - rankings: the characters by DPS or healing, or the teams by speed;
  - statistics: each class's spread.

Everything is read from the log server through the app's proxy, as the web page reads it. A log opens in its review
on Combat Logs (0.2.457). A name is drawn in its class's colour: the user's palette from Settings when one is set, else
the log review's own.
"""
from __future__ import annotations

import html

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import combat_featured as cf
from . import combat_records as cr
from . import combat_views as cv
from . import theme
from .api import AppApi, Requests
from .combat_community import _note
from .combat_saved import TIMEOUT, _button, _clear, _head, _label
from .pictures import Pictures
from .result_windows import GridTable
from .results import _dict, _truthy, cap, js_text

C = theme.COLORS
LINE2 = theme.Shade("line2")
STYLE = theme.Sheet(lambda: f"""
    QLabel#feHeading {{ color: {C['gold']}; font-family: serif; font-size: 19px; font-weight: 700; letter-spacing: 1px; }}
    QFrame#feZone, QFrame#fePage {{ background: {theme.css('panel')}; border: 1px solid {LINE2}; border-radius: 6px; }}
    QFrame#feZone QLabel, QFrame#fePage QLabel {{ background: transparent; }}
    QFrame#feZoneHead {{ background: transparent; border: none; border-bottom: 1px solid {LINE2}; }}
    QLabel#feTitle {{ color: {C['gold']}; font-family: serif; font-size: 17px; font-weight: 700; }}
    QLabel#feTitleBig {{ color: {C['gold']}; font-family: serif; font-size: 21px; font-weight: 700; }}
    QLabel#feSub {{ color: {C['muted']}; font-size: 12px; }}
    QFrame#feZone QLabel#fePortrait, QFrame#fePage QLabel#fePortrait {{ border: 1px solid {theme.css('frame')};
        border-radius: 6px; background: {theme.COLORS['icon_bg']}; }}
    QPushButton#feNav {{ color: {C['text']}; background: transparent; border: none; border-bottom: 2px solid transparent;
        border-radius: 0px; padding: 4px 2px; }}
    QPushButton#feNav:hover, QPushButton#feNav[current="true"] {{ color: {C['gold']}; border-bottom-color: {C['gold']}; }}
    QFrame#feCard, QFrame#feCloser {{ border: 1px solid {LINE2}; border-radius: 6px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {C['card_a']}, stop:1 {C['card_b']}); }}
    QFrame#feCard QLabel, QFrame#feCloser QLabel, QFrame#feRaceWrap QLabel {{ background: transparent; }}
    QLabel#feCardTitle {{ color: {C['text']}; font-size: 14px; font-weight: 700; }}
    QLabel#feVal {{ color: {C['good']}; }}
    QPushButton#feLink {{ color: {C['accent']}; background: transparent; border: none; padding: 0px;
        text-decoration: underline; text-align: left; }}
    QFrame#feCard QLabel#feMedal1, QFrame#feCard QLabel#feMedal2, QFrame#feCard QLabel#feMedal3,
    QFrame#feCard QLabel#feMedalN {{ color: #1b1b1b; font-weight: 700; font-size: 12px; border-radius: 13px; }}
    QFrame#feCard QLabel#feMedal1 {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffe08a, stop:1 #c99a2e); }}
    QFrame#feCard QLabel#feMedal2 {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f1f3f6, stop:1 #a8adb6); }}
    QFrame#feCard QLabel#feMedal3 {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f0b98a, stop:1 #a8642e); }}
    QFrame#feCard QLabel#feMedalN {{ background: #b9bec8; }}
    QLabel#feTeam {{ color: {C['accent']}; font-weight: 600; }}
    QLabel#feLegion {{ color: {C['gold']}; font-weight: 600; }}
    QLabel#feCaption {{ color: {C['gold']}; font-weight: 600; padding: 6px 0px; }}
    QFrame#feRaceWrap {{ border: 1px solid {LINE2}; border-radius: 6px; background: {theme.css('panel2')}; }}
    QLabel#feDone {{ color: {C['gold']}; font-size: 16px; font-weight: 700; }}
    QLabel#feCloserTeam {{ color: {C['accent']}; font-size: 19px; font-weight: 700; letter-spacing: 1px; }}
    QLabel#feCloserLegion {{ color: {C['gold']}; font-size: 19px; font-weight: 700; letter-spacing: 1px; }}
    QLabel#feCloserSub {{ color: {C['muted']}; font-size: 16px; font-weight: 700; letter-spacing: 1px; }}
    QFrame#feCloser QLabel#feRank {{ border: 2px solid {theme.css('frame_hi')}; background: {theme.css('inset')};
        color: {C['gold']}; font-family: serif; font-size: 18px; border-radius: 20px; }}
    QLabel#feCloserLabel {{ color: {C['muted']}; font-size: 12px; letter-spacing: 1px; }}
    QLabel#feBig {{ font-size: 21px; font-weight: 700; }}
    QLabel#feState {{ font-weight: 700; letter-spacing: 1px; }}
    QFrame#fePage QLabel#thead {{ color: {C['gold_dim']}; font-weight: 600; padding: 6px 8px; border: none;
        border-bottom: 1px solid {theme.css('frame')}; }}
    QFrame#fePage QLabel#tcell {{ padding: 5px 8px; border: none; border-bottom: 1px solid {theme.COLORS['line_soft']}; }}
    QFrame#fePage QFrame#tcellBox {{ background: transparent; border: none; border-bottom: 1px solid {theme.COLORS['line_soft']}; }}
    """)
ZONE_WIDTH = 820            # an encounter's least width side by side with another (``.fe-zones``)
ZONE_GAP = 16


def _plain(layout=QVBoxLayout, spacing: int = 0) -> tuple[QWidget, QVBoxLayout | QHBoxLayout]:
    box = QWidget()
    box.setObjectName("plain")
    line = layout(box)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(spacing)
    return box, line


def _muted(words: str, small: bool = True) -> QLabel:
    return _label(words, "small" if small else "muted")


def _link(words: str, action, enabled: bool = True) -> QPushButton:
    """A link (``a``): accent and underlined."""
    link = _button(words, action, "feLink", enabled=enabled)
    link.setCursor(Qt.PointingHandCursor)
    link.setFlat(True)
    return link


def _link_label(words: str, action) -> QLabel:
    """A link whose words may wrap (a log's title)."""
    label = _label(f"<a href='open' style='color: {C['accent']};'>{html.escape(words)}</a>", rich=True)
    label.setCursor(Qt.PointingHandCursor)
    label.linkActivated.connect(lambda _href: action())
    return label


def _named(name: str, cls: str, colours: dict) -> str:
    """A name in its class's colour (``named``), as rich text."""
    return f"<span style='color: {cr.class_colour(cls, colours)};'>{html.escape(name)}</span>"


class _Painted(QLabel):
    """A picture in a frame (``fe-portrait``), or the frame alone when the app has none (``fe-portrait-none``)."""

    def __init__(self, pixmap, size: int, tip: str = ""):
        super().__init__()
        self.setObjectName("fePortrait")
        self.setFixedSize(size, size)
        if pixmap is not None and not pixmap.isNull():
            self.setPixmap(pixmap.scaled(size - 2, size - 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            self.setAlignment(Qt.AlignCenter)
        if tip:
            self.setToolTip(tip)


class _Segment(QWidget):
    """One phase's part of the race's bar (``fe-race-seg``), filled in gold as far as the leading team got."""

    def __init__(self, fill: int, first: bool, last: bool):
        super().__init__()
        self.fill, self.first, self.last = max(0, min(100, fill)), first, last
        self.setFixedHeight(14)
        self.setAccessibleName(f"{self.fill}%")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h, r = float(self.width()), float(self.height()), 7.0
        left = 0.0 if self.first else -r                   # only the bar's two ends are rounded
        right = w if self.last else w + r
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(left, 0, right - left, h), r, r)
        painter.setClipPath(shape)
        painter.fillRect(QRectF(0, 0, w, h), theme.qcolor("inset"))
        painter.fillRect(QRectF(0, 0, w * self.fill / 100.0, h), QColor(C["gold"]))
        painter.end()


class _Spread(QWidget):
    """A class's middle half and median against the best 95th percentile (``fe-bar``)."""

    def __init__(self, box, mark, colour: str):
        super().__init__()
        self.box, self.mark, self.colour = box, mark, QColor(colour)
        self.setMinimumWidth(140)
        self.setFixedHeight(16)

    def sizeHint(self) -> QSize:
        return QSize(160, 16)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.qcolor("inset"))
        painter.drawRoundedRect(QRectF(0, 2, w, 12), 6, 6)
        if self.box is not None:
            left, width = self.box
            colour = QColor(self.colour)
            colour.setAlphaF(0.85)
            painter.setBrush(colour)
            painter.drawRoundedRect(QRectF(w * left, 4, w * width, 8), 4, 4)
        if self.mark is not None:
            painter.setBrush(QColor(C["text"]))
            painter.drawRect(QRectF(w * self.mark, 0, 2, 16))
        painter.end()


class _Closer(QFrame):
    """A team's card in the closer look (``fe-closer``): the encounter's boss faint behind it."""

    def __init__(self, art):
        super().__init__()
        self.setObjectName("feCloser")
        self.art = art if art is not None and not art.isNull() else None
        self.setMinimumHeight(180)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.art is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(0.22)
        h = self.height() - 2
        w = min(self.art.width() * h / max(1, self.art.height()), self.width() * 0.6)
        painter.setClipRect(QRectF(1, 1, self.width() - 2, h))
        target = QRectF(self.width() - 1 - w, 1, w, h)
        source = QRectF(self.art.rect())
        scale = max(w / source.width(), h / source.height())          # ``object-fit: cover``
        sw, sh = w / scale, h / scale
        painter.drawPixmap(target, self.art, QRectF((source.width() - sw) / 2, (source.height() - sh) / 2, sw, sh))
        painter.end()


class _Featured(QWidget):
    """What the section and the page share: their requests, the class colours, the pictures and the drawing of a
    team, a character or a class."""

    def __init__(self, api: AppApi | None, pictures: Pictures | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.pictures = pictures
        self.requests = Requests(api, self, timeout=TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.asked: dict[str, int] = {}                     # each kind's latest question; an older answer is let go
        self.colours: dict = {}
        self.soon = QTimer(self)                            # pictures that come together, drawn once
        self.soon.setSingleShot(True)
        self.soon.setInterval(120)
        self.soon.timeout.connect(self.redraw)
        if self.pictures is not None:
            self.pictures.changed.connect(self.soon.start)

    def stop(self) -> None:
        self.soon.stop()
        if self.requests is not None:
            self.requests.stop()

    def _ask(self, kind: str, path: str, proxied: bool = True) -> None:
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if self.requests is not None:
            self.requests.get(f"{kind}:{self.asked[kind]}", cv.community_path(path) if proxied else path)

    def _colours(self) -> None:
        """The class colours, asked for before what they colour: the answers come in the order asked."""
        self._ask("ui", "/api/ui", proxied=False)

    def _current(self, name: str) -> str | None:
        kind, _, number = name.partition(":")
        return kind if number == str(self.asked.get(kind)) else None

    def _replied(self, name: str, answer) -> None:
        kind = self._current(name)
        if kind == "ui":
            self.colours = _dict(_dict(answer).get("combat_colors"))
        elif kind is not None:
            if isinstance(answer, dict) and _truthy(answer.get("error")):        # app.js's api() refuses it
                self.refused(kind, js_text(answer["error"]))
            else:
                self.answered(kind, answer)

    def _failed(self, name: str, why: str) -> None:
        kind = self._current(name)
        if kind is not None and kind != "ui":
            self.refused(kind, why or cf.NOT_REACHED)

    def answered(self, kind: str, answer) -> None:
        pass

    def refused(self, kind: str, why: str) -> None:
        pass

    def redraw(self) -> None:
        pass

    # the pieces
    def _art(self, key, icon):
        """A boss's portrait (``portraitURL``): the art the app bundles for its NPC, else for the one the server names;
        None when the app has neither, or has not read it yet."""
        if self.pictures is None:
            return None
        code = cf.npc_code(key)
        art = self.pictures.portrait(code) if code is not None else None
        return art if art is not None else self.pictures.by_address(icon)

    def _portrait(self, key, icon, size: int, tip: str = "") -> QLabel:
        """A boss's portrait in its frame (``portrait``)."""
        return _Painted(self._art(key, icon), size, tip)

    def _class_icon(self, cls: str, size: int = 20) -> QLabel | None:
        """A class's emblem (``classIcon``), for the eight classes the game has."""
        if cls not in cf.CLASSES or self.pictures is None:
            return None
        pixmap = self.pictures.emblem(cls)
        if pixmap is None or pixmap.isNull():
            return None
        face = QLabel()
        face.setFixedSize(size, size)
        face.setScaledContents(True)
        face.setPixmap(pixmap)
        face.setToolTip(cap(cls))
        return face

    def _icon_cell(self, cls: str, size: int = 20) -> QWidget | str:
        """A class's emblem in a table's cell, kept whole by a box around it."""
        icon = self._class_icon(cls, size)
        if icon is None:
            return ""
        box, line = _plain(QHBoxLayout)
        line.addWidget(icon)
        return box

    def _team(self, team: dict, closer: bool = False) -> QWidget:
        """A team (``teamHTML``): its name, a legion's in gold, its members on hover, and where it plays."""
        box, column = _plain(spacing=1)
        name = _label(team["name"].upper() if closer else team["name"],
                      ("feCloserLegion" if team["legion"] else "feCloserTeam") if closer else (
                          "feLegion" if team["legion"] else "feTeam"))
        if team["tip"]:
            name.setToolTip(team["tip"])
        column.addWidget(name)
        if team["sub"]:
            column.addWidget(_label(team["sub"].upper() if closer else team["sub"], "feCloserSub" if closer else "feSub"))
        box.setProperty("fill", True)
        return box

    def _player(self, player: dict) -> QWidget:
        """A character (``playerHTML``): its name in its class's colour, and its server."""
        box, column = _plain(spacing=1)
        column.addWidget(_label(_named(player["name"], player["class"], self.colours), rich=True))
        if player["sub"]:
            column.addWidget(_label(player["sub"], "feSub"))
        box.setProperty("fill", True)
        return box

    def _class(self, cls: str, name: str, size: int = 20) -> QWidget:
        """A class: its emblem and its name in its colour."""
        box, line = _plain(QHBoxLayout, 4)
        icon = self._class_icon(cls, size)
        if icon is not None:
            line.addWidget(icon)
        line.addWidget(_label(_named(name, cls, self.colours), rich=True, wrap=False))
        line.addStretch(1)
        return box

    def _nav(self, f: dict, current: str | None, opened) -> QWidget:
        """A featured encounter's pages (``nav``), the one shown marked."""
        box, line = _plain(QHBoxLayout, 14)
        for view, words in cf.VIEWS:
            link = QPushButton(words)
            link.setObjectName("feNav")
            link.setFlat(True)
            link.setCursor(Qt.PointingHandCursor)
            link.setProperty("current", view == current)
            link.setAccessibleName(f"{js_text(f.get('title'))} {words}")
            link.clicked.connect(lambda _checked=False, view=view: opened(f.get("id"), view, None))
            line.addWidget(link)
        return box


# ---------------------------------------------------------------------- the landing cards
class _Zones(QWidget):
    """The encounters one under another, side by side wherever two fit (``.fe-zones``)."""

    def __init__(self, zones: list[QWidget]):
        super().__init__()
        self.setObjectName("plain")
        self.zones = zones
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(ZONE_GAP)
        self.columns = 0
        self._place(1)

    def _place(self, columns: int) -> None:
        if columns == self.columns:
            return
        self.columns = columns
        for zone in self.zones:
            self.grid.removeWidget(zone)
        for i, zone in enumerate(self.zones):
            self.grid.addWidget(zone, i // columns, i % columns)
        for column in range(max(1, len(self.zones))):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        fits = (self.width() + ZONE_GAP) // (ZONE_WIDTH + ZONE_GAP)
        self._place(max(1, min(len(self.zones), fits)))


class FeaturedSection(_Featured):
    """The landing cards of every featured encounter (``section``); nothing when there is none. ``opened(id, view,
    metric)`` opens one of an encounter's pages."""

    def __init__(self, api: AppApi | None, opened, pictures: Pictures | None = None, parent: QWidget | None = None):
        super().__init__(api, pictures, parent)
        self.setObjectName("plain")
        self.opened = opened
        self.answer = None
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(10)
        self.setVisible(False)
        self.load()

    def load(self) -> None:
        """The featured encounters, read again; the cards stay as they are until the server answers."""
        self._colours()
        self._ask("featured", "/api/v1/featured")

    def answered(self, kind: str, answer) -> None:
        if kind == "featured":
            self.answer = answer
            self.redraw()

    def refused(self, kind: str, why: str) -> None:
        if kind == "featured":                                  # the section draws nothing (``.catch``)
            self.answer = None
            self.redraw()

    def redraw(self) -> None:
        _clear(self.box)
        featured = cf.featured_list(self.answer)
        self.setVisible(bool(featured))
        if not featured:
            return
        heading = _label(cf.HEADING, "feHeading")
        heading.setIndent(0)
        self.box.addWidget(heading)
        self.box.addWidget(_Zones([self._zone(f) for f in featured]))
        words = cf.note(self.answer)
        if words:
            self.box.addWidget(_muted(words))

    def _zone(self, f: dict) -> QFrame:
        """One encounter (``zone``): its head with its portrait, title and pages; its cards; and what they count."""
        zone = QFrame()
        zone.setObjectName("feZone")
        column = QVBoxLayout(zone)
        column.setContentsMargins(13, 13, 13, 13)
        column.setSpacing(10)
        head = QFrame()
        head.setObjectName("feZoneHead")
        line = QHBoxLayout(head)
        line.setContentsMargins(0, 0, 0, 10)
        line.setSpacing(12)
        line.addWidget(self._portrait(f.get("boss_key"), f.get("icon"), 56, js_text(f.get("boss"))), 0, Qt.AlignTop)
        title, words = _plain(spacing=2)
        title.setAccessibleName(js_text(f.get("title")))
        words.addWidget(_label(js_text(f.get("title")), "feTitle"))
        words.addWidget(_label(cf.title_line(f), "feSub"))
        line.addWidget(title, 1)
        line.addWidget(self._nav(f, None, self.opened), 0, Qt.AlignVCenter)
        column.addWidget(head)
        cards = QGridLayout()
        cards.setSpacing(10)
        for i, card in enumerate(cf.zone_cards(f)):
            cards.addWidget(self._card(f, card), i // 3, i % 3)
        for c in range(3):
            cards.setColumnStretch(c, 1)
        column.addLayout(cards)
        column.addWidget(_muted(cf.zone_note(f)))
        return zone

    def _card(self, f: dict, card: dict) -> QFrame:
        """A card (``card``): its title, its top rows with their medals, and the page with more."""
        frame = QFrame()
        frame.setObjectName("feCard")
        frame.setAccessibleName(card["title"])
        column = QVBoxLayout(frame)
        column.setContentsMargins(12, 10, 12, 10)
        column.setSpacing(8)
        column.addWidget(_label(card["title"], "feCardTitle"))
        if card["rows"]:
            rows = QGridLayout()
            rows.setHorizontalSpacing(8)
            rows.setVerticalSpacing(6)
            for i, (kind, who, value) in enumerate(card["rows"]):
                rows.addWidget(_medal(i + 1), i, 0, Qt.AlignVCenter)
                rows.addWidget(self._team(who) if kind == "team" else self._player(who) if kind == "player"
                               else self._class(who["class"], who["name"]), i, 1)
                val = _label(value, "feVal", wrap=False)
                val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rows.addWidget(val, i, 2)
            rows.setColumnStretch(1, 1)
            column.addLayout(rows)
        else:
            column.addWidget(_muted(cf.NO_RECORDS))
        column.addStretch(1)
        view, metric = card["more"]
        column.addWidget(_link(cf.MORE, lambda: self.opened(f.get("id"), view, metric)), 0, Qt.AlignHCenter)
        return frame


def _medal(rank: int) -> QLabel:
    """A row's place (``fe-medal``): gold, silver and bronze for the first three."""
    medal = QLabel(str(rank))
    medal.setObjectName(f"feMedal{rank if rank <= 3 else 'N'}")
    medal.setFixedSize(26, 26)
    medal.setAlignment(Qt.AlignCenter)
    return medal


# ---------------------------------------------------------------------- one encounter's page
class FeaturedPage(_Featured):
    """One featured encounter's page (``page``): its head and pages, then the view chosen. ``open_web`` opens a log's
    review; ``opened(id, view, metric)`` opens another of its pages (``show_page`` when not given)."""

    def __init__(self, api: AppApi | None, open_web=None, pictures: Pictures | None = None, parent: QWidget | None = None,
                 opened=None):
        super().__init__(api, pictures, parent)
        self.setObjectName("plain")
        self.open_web = open_web
        self.opened = opened or self.show_page            # another of its pages, opened as the web page links to it
        self.fid, self.view = "", "race"
        self.state: dict = {}
        self.f: dict | None = None                         # the encounter, once read
        self.answer = None                                 # the view's last answer
        self.problem: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName("fePage")
        outer.addWidget(self.frame)
        self.column = QVBoxLayout(self.frame)
        self.column.setContentsMargins(13, 13, 13, 13)
        self.column.setSpacing(12)
        self.head, self.head_line = _plain(QHBoxLayout, 12)
        self.column.addWidget(self.head)
        self.body_box, self.body = _plain(spacing=10)
        self.column.addWidget(self.body_box)

    def show_page(self, fid, view=None, metric=None) -> None:
        """An encounter's page as the web page opens it, every choice as it starts: its first page, its own boss, every
        region, every class."""
        self.view, metric = cf.featured_page(view, metric)
        self.fid = fid if isinstance(fid, str) else js_text(fid)
        self.state = {"page": 1, "boss": "", "region": "", "metric": metric, "cls": ""}
        self.f, self.answer, self.problem = None, None, None
        for kind in ("encounter", "view"):
            self.asked[kind] = self.asked.get(kind, 0) + 1          # an answer to the page shown before is let go
        _clear(self.head_line)
        _clear(self.body)
        self.head.setVisible(False)
        if not cf.valid_id(self.fid):
            self.body.addWidget(_note(cf.NO_ADDRESS))
            return
        self.body.addWidget(_muted(cf.LOADING, small=False))
        self._colours()
        self._ask("encounter", f"/api/v1/featured/{cf.encode_component(self.fid)}")

    def reload(self) -> None:
        """The encounter and its view read again, the choices as they are."""
        if not cf.valid_id(self.fid):
            return
        self._colours()
        self._ask("encounter", f"/api/v1/featured/{cf.encode_component(self.fid)}")

    def load(self) -> None:
        """The view asked for again (``load``); what it shows stays until the server answers."""
        self._ask("view", cf.featured_path(self.fid, self.view, self.state))

    def answered(self, kind: str, answer) -> None:
        if kind == "encounter":
            self.f = _dict(answer)
            if not self.state.get("boss"):
                self.state["boss"] = js_text(self.f.get("boss_key") or "")
            self._head()
            if self.answer is None and self.problem is None:
                _clear(self.body)
                self.body.addWidget(_muted(cf.LOADING, small=False))
            self.load()
        elif kind == "view":
            self.answer, self.problem = answer, None
            self._body()

    def refused(self, kind: str, why: str) -> None:
        if kind == "encounter":                               # the page says why, and nothing else
            self.f = None
            self.head.setVisible(False)
            _clear(self.head_line)
        self.problem = why
        _clear(self.body)
        self.body.addWidget(_note(why))

    def redraw(self) -> None:
        if self.f is not None:
            self._head()
        if self.answer is not None and self.problem is None:
            self._body()

    def _head(self) -> None:
        """The encounter's head (``fe-head-page``): its portrait, title, boss, difficulty and race, and its pages."""
        f = self.f or {}
        _clear(self.head_line)
        self.head_line.addWidget(self._portrait(f.get("boss_key"), f.get("icon"), 72, js_text(f.get("boss"))), 0, Qt.AlignTop)
        title, words = _plain(spacing=2)
        words.addWidget(_label(js_text(f.get("title")), "feTitleBig"))
        words.addWidget(_label(cf.header_line(f), "feSub"))
        self.head_line.addWidget(title, 1)
        self.head_line.addWidget(self._nav(f, self.view, self.opened), 0, Qt.AlignVCenter)
        self.head.setVisible(True)

    def _open_log(self, log_id, segment=None) -> None:
        if self.open_web is not None and _truthy(log_id):
            self.open_web(cf.log_page(log_id, segment))

    def _log(self, log_id, segment=None, words: str = "Log") -> QWidget:
        """A log's link, opening it in the web interface; nothing when the server names no log."""
        if not _truthy(log_id):
            return _label("")
        return _link(words, lambda: self._open_log(log_id, segment))

    # the views
    def _body(self) -> None:
        _clear(self.body)
        d = _dict(self.answer)
        if self.view in ("race", "progress"):
            self._controls(self._region(d))
        draw = {"race": self._race, "progress": self._progress, "reports": self._reports, "rankings": self._rankings,
                "statistics": self._statistics}[self.view]
        draw(d)
        words = cf.note(d)
        if words:
            self.body.addWidget(_muted(words))

    def _controls(self, *parts) -> None:
        """The choices over a view (``controls``), when it has any."""
        shown = [part for part in parts if part is not None]
        if not shown:
            return
        box, line = _plain(QHBoxLayout, 14)
        for part in shown:
            line.addWidget(part)
        line.addStretch(1)
        self.body.addWidget(box)

    def _pick(self, words: str, values, chosen: str, changed) -> QWidget:
        """A choice with its name (``label`` around a ``select``)."""
        box, line = _plain(QHBoxLayout, 6)
        line.addWidget(_label(words, wrap=False))
        pick = QComboBox()
        pick.setAccessibleName(words)
        for value, name in values:
            pick.addItem(name, value)
        pick.setCurrentIndex(max(0, pick.findData(chosen)))
        pick.activated.connect(lambda _i: changed(pick.currentData()))
        line.addWidget(pick)
        return box

    def _set(self, key: str, value, first_page: bool = False) -> None:
        self.state[key] = value or ""
        if first_page:
            self.state["page"] = 1
        self.load()

    def _region(self, d: dict) -> QWidget | None:
        offered = cf.regions_offered(d)
        if not offered:
            return None
        return self._pick("Region", [("", cf.ALL_REGIONS)] + offered, self.state.get("region") or "",
                          lambda value: self._set("region", value, first_page=True))

    def _boss(self) -> QWidget:
        return self._pick("Boss", cf.boss_choices(self.f), self.state.get("boss") or "", lambda value: self._set("boss", value))

    def _caption(self, words: str) -> None:
        caption = _label(words, "feCaption")
        caption.setIndent(0)
        self.body.addWidget(caption)

    def _table(self, heads: list[str], cells: list[list], empty: str, stretch: dict) -> None:
        """A table (``table.t.fe-table``), with its words across it when it has no row."""
        table = GridTable(heads, cells, stretch, left=True)
        self.body.addWidget(table)
        if not cells:
            self.body.addWidget(_label(empty, "tcell"))

    def _pager(self, d: dict, size) -> None:
        turn = cf.pager(d, size)
        if turn is None:
            return
        box, line = _plain(QHBoxLayout, 10)
        line.addWidget(_button("Previous", lambda: self._page(turn["page"] - 1), enabled=turn["previous"]))
        line.addWidget(_label(turn["words"], wrap=False))
        line.addWidget(_button("Next", lambda: self._page(turn["page"] + 1), enabled=turn["next"]))
        line.addStretch(1)
        self.body.addWidget(box)

    def _page(self, page: int) -> None:
        self.state["page"] = page
        self.load()

    def _race(self, d: dict) -> None:
        """The race (``raceHTML``)."""
        r = cf.race(d, self.f)
        wrap = QFrame()
        wrap.setObjectName("feRaceWrap")
        wrap.setAccessibleName(r["label"])
        grid = QGridLayout(wrap)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(8)
        n = len(r["phases"])
        for i, p in enumerate(r["phases"]):
            head, line = _plain(QHBoxLayout, 8)
            line.addStretch(1)
            line.addWidget(self._portrait(p["key"], p["icon"], 40))
            words, column = _plain(spacing=0)
            column.addWidget(_label(f"<b>{html.escape(p['title'])}</b>", rich=True, wrap=False))
            column.addWidget(_label(p["boss"], "small"))
            line.addWidget(words)
            line.addStretch(1)
            grid.addWidget(head, 0, i)
            grid.setColumnMinimumWidth(i, 140)
            grid.setColumnStretch(i, 1)
        done = _label("Complete!", "feDone", wrap=False)
        done.setAlignment(Qt.AlignCenter)
        grid.addWidget(done, 0, n)
        grid.setColumnMinimumWidth(n, 160)
        grid.setColumnStretch(n, 1)
        for i, fill in enumerate(r["fills"]):
            grid.addWidget(_Segment(fill, i == 0, False), 1, i)
        grid.addWidget(_Segment(r["done_fill"], n == 0, True), 1, n)
        for i, stat in enumerate(r["stats"]):
            words = html.escape(stat["line"]) + (f"<br>{html.escape(stat['first'])}" if stat["first"] else "")
            label = _label(words, "small", rich=True)
            label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            grid.addWidget(label, 2, i)
        complete = _label(r["complete"], "small")
        complete.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        grid.addWidget(complete, 2, n)
        for i, rows in enumerate(r["lists"]):
            grid.addWidget(_standing(rows), 3, i, Qt.AlignTop)
        grid.addWidget(_standing(r["done"]) if r["done"] else _muted(cf.NO_TEAM_YET), 3, n, Qt.AlignTop)
        self.body.addWidget(wrap)
        self.body.addWidget(_head(cf.CLOSER))
        if not r["closers"]:
            self.body.addWidget(_muted(cf.NO_ATTEMPT, small=False))
            return
        closers = QGridLayout()
        closers.setSpacing(10)
        art = self._art((self.f or {}).get("boss_key"), (self.f or {}).get("icon"))
        for i, c in enumerate(r["closers"]):
            closers.addWidget(self._closer(c, art), i // 2, i % 2)
        closers.setColumnStretch(0, 1)
        closers.setColumnStretch(1, 1)
        self.body.addLayout(closers)

    def _closer(self, c: dict, art) -> QFrame:
        """A team in the closer look: its name and rank, its members, its progress, pulls and where it is."""
        card = _Closer(art)
        card.setAccessibleName(c["team"]["name"])
        column = QVBoxLayout(card)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(6)
        top, line = _plain(QHBoxLayout, 10)
        line.addWidget(self._team(c["team"], closer=True), 1, Qt.AlignTop)
        rank = QLabel(c["rank"])
        rank.setObjectName("feRank")
        rank.setFixedSize(40, 40)
        rank.setAlignment(Qt.AlignCenter)
        rank.setAccessibleName(f"Rank {c['rank']}")
        line.addWidget(rank, 0, Qt.AlignTop)
        column.addWidget(top)
        if c["members"]:
            column.addWidget(_label(", ".join(_named(m["name"], m["class"], self.colours) for m in c["members"]), rich=True))
        elif c["team"]["legion"]:
            column.addWidget(_muted("Legion"))
        column.addStretch(1)
        foot, line = _plain(QHBoxLayout, 12)
        left, words = _plain(spacing=0)
        words.addWidget(_label("PROGRESS", "feCloserLabel", wrap=False))
        words.addWidget(_label(c["progress"], "feBig", wrap=False))
        line.addWidget(left, 0, Qt.AlignBottom)
        line.addStretch(1)
        right, words = _plain(spacing=2)
        for label in (_label(c["pulls"], wrap=False), _label(c["state"].upper(), "feState", wrap=False),
                      _label(c["detail"], wrap=False)):
            label.setAlignment(Qt.AlignRight)
            words.addWidget(label, 0, Qt.AlignRight)
        words.addWidget(self._log(c["log"], words=cf.OPEN_LOG), 0, Qt.AlignRight)
        line.addWidget(right, 0, Qt.AlignBottom)
        column.addWidget(foot)
        return card

    def _progress(self, d: dict) -> None:
        """Progress (``progressHTML``): the teams by progress, then the final-boss kills."""
        cells = []
        for row in cf.progress_rows(d, self.f):
            killed, line = _plain(QHBoxLayout, 3)
            for key, icon, boss in row["killed"]:
                line.addWidget(self._portrait(key, icon, 24, boss))
            line.addStretch(1)
            cells.append([row["rank"], self._team(row["team"]), row["progress"], killed, row["pulls"], row["at"]])
        self._caption(cf.PROGRESS_CAPTION)
        self._table(cf.PROGRESS_COLUMNS, cells, cf.NO_ATTEMPT, {1: 2, 2: 2, 3: 2, 4: 1, 5: 2})
        self._pager(d, 50)
        cells = []
        for row in cf.kill_rows(d):
            party, line = _plain(QHBoxLayout, 2)
            for cls, count in row["composition"]:
                icon = self._class_icon(cls, 18)
                if icon is not None:
                    line.addWidget(icon)
                line.addWidget(_label(count, wrap=False))
                line.addSpacing(6)
            line.addStretch(1)
            cells.append([row["rank"], self._team(row["team"]), row["patch"], party, row["at"], row["time"], row["deaths"],
                          self._log(row["log"])])
        self._caption(cf.KILLS_CAPTION)
        self._table(cf.KILLS_COLUMNS, cells, cf.NO_KILL, {1: 2, 2: 2, 3: 2, 4: 2, 5: 1, 6: 1})

    def _reports(self, d: dict) -> None:
        """All reports (``reportsHTML``)."""
        cells = []
        for row in cf.report_rows(d):
            log, column = _plain(spacing=1)
            column.addWidget(_link_label(row["title"], lambda log_id=row["id"]: self._open_log(log_id))
                             if _truthy(row["id"]) else _label(row["title"]))
            column.addWidget(_label(row["uploader"], "feSub"))
            log.setProperty("fill", True)
            players = _label(", ".join(_named(p["name"], p["class"], self.colours) for p in row["players"]), rich=True)
            cells.append([row["at"], log, row["bosses"], row["time"], players])
        self._caption(cf.REPORTS_CAPTION)
        self._table(cf.REPORTS_COLUMNS, cells, cf.NO_REPORT, {0: 2, 1: 2, 2: 3, 3: 1, 4: 2})
        self._pager(d, _dict(d).get("limit") or 30)

    def _rankings(self, d: dict) -> None:
        """Rankings (``rankingsHTML``): the characters by DPS or healing, or the teams by speed."""
        speed = self.state["metric"] == "speed"
        self._controls(None if speed else self._boss(),
                       self._pick("Ranking", [(v, w) for v, w in cf.RANKING_METRICS], self.state["metric"],
                                  lambda value: self._set("metric", value)),
                       None if speed else self._pick("Class", [("", cf.ALL_CLASSES)] + [(c, c.capitalize()) for c in cf.CLASSES],
                                                     self.state.get("cls") or "", lambda value: self._set("cls", value)),
                       self._region(d))
        if speed:
            cells = [[r["rank"], self._team(r["team"]), r["time"], r["patch"], r["at"], self._log(r["log"])]
                     for r in cf.speed_rows(d)]
            self._caption(cf.SPEED_CAPTION)
            self._table(cf.SPEED_COLUMNS, cells, cf.NO_SPEED, {1: 2, 2: 1, 3: 2, 4: 2})
            return
        cells = []
        for r in cf.ranking_rows(d):
            cells.append([r["rank"], self._player(r["player"]), self._icon_cell(r["class"]), r["score"], r["parse"],
                          r["time"], r["at"], self._log(r["log"], r["segment"])])
        self._caption(cf.ranking_caption(self.f, self.state))
        self._table(cf.ranking_columns(self.state["metric"]), cells, cf.NO_RANKED, {1: 2, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2})

    def _statistics(self, d: dict) -> None:
        """Statistics (``statisticsHTML``): each class's figures and spread."""
        self._controls(self._boss(),
                       self._pick("Rate", [(v, w) for v, w in cf.RATE_METRICS], self.state["metric"],
                                  lambda value: self._set("metric", value)),
                       self._region(d))
        rows, _top = cf.statistics_rows(d)
        cells = []
        for r in rows:
            spread = _Spread(r["box"], r["mark"], cr.class_colour(r["class"], self.colours))
            spread.setProperty("fill", True)
            cells.append([self._class(r["class"], r["name"]), r["role"], r["count"], r["p25"], r["median"], r["p75"], r["p95"],
                          r["max"], spread])
        self._caption(cf.statistics_caption(self.state["metric"]))
        self._table(cf.STATISTICS_COLUMNS, cells, cf.NO_SAMPLE, {0: 2, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 2})
        self.body.addWidget(_muted(cf.ROLES_NOTE))


def _standing(rows: list[dict]) -> QWidget:
    """The teams on a phase (``fe-standing``): each one's rank, name, and its best try or when it finished."""
    box, column = _plain(spacing=3)
    for row in rows:
        muted = C["muted"]
        column.addWidget(_label(f"<span style='color: {muted};'>{html.escape(row['rank'])}</span> {html.escape(row['name'])} "
                                f"<span style='color: {muted}; font-size: 12px;'>{html.escape(row['small'])}</span>", rich=True))
    return box
