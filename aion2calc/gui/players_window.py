"""The player cards window of a PvP match, natively (0.2.499): a card for every player of an arena or battlefield
match, in a Qt window of its own beside the meter overlay, where until now it was the overlay page in pywebview
(``overlay?view=players``, overlay.js ``renderPlayers`` and arena-view.js ``players``).

It is the meter overlay's compact window (``MeterOverlay``), with its look, background, place and click-through,
holding what that page holds in its player cards view:

- **its head** in the target card's place (``playersHead``): *Players*, and the match with how many players each
  side has (*Arena of Cooperation · 2v2*), or *PvP* while there is no match;
- **the cards** in the rows' place, allies then enemies, each side under a head of its own with its count, most DPS
  first: the class's emblem, the name, the server and *you* on your own card; the combat power, gear score and arena
  rating (or the class) and *dead*; the HP bar; and the damage dealt in the match. As a list (340 px) or, with
  **Player cards: Grid** in the overlay's options, the two sides side by side, two small cards a row (540 px);
- or why there is none: *Waiting for an arena or battlefield match*, or that arena mode is off;
- **of the toolbar only Lock and Hide**, Hide closing this window alone.

It reads the meter as the meter overlay does, keeps its own place (``overlay_players_pos_*``) and the meter overlay's
opacity, which its page has no slider to change either. The edges' resize grips are left out: the page's changed the
meter overlay's own width.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from . import arena as A
from . import theme
from .arena import Section, sized, swords
from .chrome import TEAL
from .look import CHIP_SHADOW, ROW_SHADOW, TextLook, draw_text
from .overlay import MeterOverlay

ALLIES, ENEMIES = "#7cc4ff", "#ff8f86"     # ``.arn-allies``, ``.arn-enemies``
ALLY_EDGE, FOE_EDGE = "#5aa9e6", "#e05a5a"  # a card's edge by its side
ROW_GROUND = QColor(10, 12, 15, 140)       # ``--nm-row: rgba(10, 12, 15, .55)``, over the game
WHOLE_GROUND = QColor(255, 255, 255, 11)   # on the whole card a faint light (``#ov.ov-nm.ov-whole``: rgba(255, 255, 255, .045))
BADGE_GROUND = QColor(99, 211, 230, 41)    # ``.arn-badge``: rgba(99, 211, 230, .16)
HP_TRACK, HP_FILL = QColor(255, 255, 255, 26), QColor("#5bd16b")
NAME, SMALL, FACTS, BOLD = "#eef1f4", "#a3abb5", "#aab3bd", "#e9edf1"
WAITING = "Waiting for an arena or battlefield match: its players show here as cards."
ARENA_OFF = "Arena mode is off (the overlay's options): turn it on for the player cards."
LIST_WIDTH, GRID_WIDTH = 340, 540          # ``--ov-width`` in the window (overlay.js)
EMBLEM = 24                                 # ``#ov.ov-nm .ovcicon``: 24 px, 8 px before what follows


# ---------------------------------------------------------------------------------------------- the words
def match_of(snap: dict, on: bool) -> dict | None:
    """The match the window shows (``renderPlayers``): arena mode on, and a reading of one with its fighters."""
    arena = snap.get("arena") if isinstance(snap, dict) else None
    return arena if on and isinstance(arena, dict) and A.fighters(arena) else None


def head_words(arena: dict | None) -> tuple[str, str]:
    """The head's title and its tag (``playersHead``): the match and its sides' counts, or "PvP"."""
    if arena is None:
        return "Players", "PvP"
    counts = [0, 0]
    for fighter in A.fighters(arena):
        counts[1 if fighter.get("side") == "enemy" else 0] += 1
    label = arena.get("label")
    return "Players", f"{_text(label) if label else 'PvP'} · {counts[0]}v{counts[1]}"


def status(arena: dict | None) -> str:
    """The window's status (``#ovstatus``, folded away with the metric row as on its page)."""
    if arena is None:
        return "Player cards · waiting for a PvP match"
    return f"{_text(arena.get('label'))} · {len(A.fighters(arena))} players"


def sides(arena: dict) -> tuple[list[dict], list[dict]]:
    """The allies and the enemies, each most DPS first (``players``' ``order``; a tie keeps the reading's order)."""
    allies = [f for f in A.fighters(arena) if f.get("side") != "enemy"]
    enemies = [f for f in A.fighters(arena) if f.get("side") == "enemy"]
    order = lambda group: sorted(group, key=lambda f: -A.num(f.get("dps")))   # noqa: E731
    return order(allies), order(enemies)


def server_of(fighter: dict) -> str:
    return _text(fighter.get("server_name") or (f"server {_text(fighter['server'])}" if fighter.get("server") else ""))


def facts(fighter: dict) -> list[tuple[str, str]]:
    """A card's facts (``playerCard``): the combat power (a chip), then "GS" and "Rating" with their figures, each as
    (kind, words): "cp", "word" or "bold"."""
    out: list[tuple[str, str]] = []
    if fighter.get("combat_power"):
        out.append(("cp", theme.sfmt(fighter["combat_power"])))
    for key, words in (("gear_score", "GS"), ("rating", "Rating")):
        if fighter.get(key):
            out += [("word", words), ("bold", A.grouped(fighter[key]))]
    return out


def capitalised(value) -> str:
    """``cap``: the first letter upper case."""
    text = _text(value) if value else ""
    return text[:1].upper() + text[1:]


def damage(fighter: dict, duration) -> str:
    """The damage dealt in the match: the DPS times the fight's length, short (``sfmt``)."""
    return theme.sfmt(A.num(fighter.get("dps")) * A.num(duration))


def hp_share(fighter: dict) -> float:
    """The HP bar's fill, whole percent: the HP, else none for the dead and all for the rest."""
    hp = A.hp_of(fighter)
    if hp is not None:
        return theme.js_round(hp) / 100
    return 0.0 if fighter.get("dead") else 1.0


def _text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------------------------- the pieces
class PlayersHead(QWidget):
    """The window's head (``.arn-head`` in the compact target card): *Players* at 1.12em, 700, then its tag, teal on
    a teal ground, .7em, 800, spaced .8 px, in capitals; 8 px apart, 2 px in. The target card's room round it: 6 px
    above, 2 px in and 4 below on the whole card, 7, 10 and 9 elsewhere (``#ov.ov-nm .ovcard > #ovtarget``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title, self.tag = "Players", "PvP"
        self.look = TextLook({})
        self.px = 12
        self.colour = "#f4f6f8"
        self.shadow = None
        self.room = (2, 6, 2, 4)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_head(self, title: str, tag: str, look: TextLook, px: int, shadow=None, whole: bool = True) -> None:
        self.title, self.tag, self.look, self.px, self.shadow = title, tag, look, px, shadow
        self.colour = look.colour("target", "#f4f6f8")
        self.room = (2, 6, 2, 4) if whole else (10, 7, 10, 9)
        self.setFixedHeight(self.room[1] + 2 + round(self._title_font().pixelSize() * 1.35) + self.room[3])
        self.update()

    def _title_font(self) -> QFont:
        return self.look.font("target", self.px * 1.12, 700)

    def _tag_font(self) -> QFont:
        return sized(self.look.font("target", self.px, 800), self.look.size("target", self.px) * 0.7, 800, 0.8)

    def words(self) -> str:
        return f"{self.title} {self.tag.upper()}"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        title, tag = self._title_font(), self._tag_font()
        left, top, right, bottom = self.room     # and ``.arn-head { padding: 2px 2px 0 }``
        line = QRectF(left + 2, top + 2, self.width() - left - right - 4, self.height() - top - bottom - 2)
        width = draw_text(painter, line, self.title, title, QColor(self.colour), Qt.AlignLeft, self.look,
                          shadow=self.shadow)
        metrics = QFontMetricsF(tag)
        words = self.tag.upper()
        box = QRectF(line.left() + width + 8, line.center().y() - (metrics.height() + 2) / 2,
                     metrics.horizontalAdvance(words) + 12, metrics.height() + 2)
        ground = QPainterPath()
        ground.addRoundedRect(box, 4, 4)
        painter.fillPath(ground, BADGE_GROUND)
        draw_text(painter, box.adjusted(6, 1, -6, -1), words, tag, QColor(self.look.contrast or TEAL), Qt.AlignLeft,
                  self.look, shadow=self.shadow)


def _emblem(painter: QPainter, picture: QPixmap | None, rect: QRectF) -> None:
    """A class's emblem in its square (``background-size: contain``), its shape in black at 60% a pixel under it
    (``drop-shadow(0 1px 1px rgba(0, 0, 0, .6))``)."""
    if picture is None or picture.isNull():
        return
    scaled = picture.size().scaled(round(rect.width()), round(rect.height()), Qt.KeepAspectRatio)
    target = QRectF(rect.center().x() - scaled.width() / 2, rect.center().y() - scaled.height() / 2,
                    scaled.width(), scaled.height())
    shade = QPixmap(picture.size())
    shade.fill(Qt.transparent)
    inner = QPainter(shade)
    inner.drawPixmap(0, 0, picture)
    inner.setCompositionMode(QPainter.CompositionMode_SourceIn)
    inner.fillRect(shade.rect(), QColor(0, 0, 0, 153))
    inner.end()
    painter.save()
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(target.translated(0, 1), shade, QRectF(shade.rect()))
    painter.drawPixmap(target, picture, QRectF(picture.rect()))
    painter.restore()


class Card(QWidget):
    """A player's card (``.arn-card``, or ``.arn-mini`` in the grid): on the rows' ground, its side's colour along
    its edge, faded where the player is dead. ``set_card`` draws a fighter on it."""

    def __init__(self, parent=None, mini: bool = False):
        super().__init__(parent)
        self.mini = mini
        self.fighter: dict = {}
        self.picture: QPixmap | None = None
        self.look = TextLook({})
        self.px = 12
        self.damage = ""
        self.cp_room = True                       # the combat power's chip shown (``@container (max-width: 26.5em)``)
        self.whole = True                         # on the whole card, or over the game
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_card(self, fighter: dict, picture: QPixmap | None, look: TextLook, px: int, damage_: str, cp_room: bool,
                 whole: bool = True):
        self.fighter, self.picture, self.look, self.px = fighter, picture, look, px
        self.damage, self.cp_room, self.whole = damage_, cp_room, whole
        self.setFixedHeight(self._height())
        self.update()

    # ---- sizes
    def _font(self, scale: float, weight: int) -> QFont:
        return sized(self.look.font("name", self.px, weight), self.px * scale, weight)

    def _height(self) -> int:
        if self.mini:                             # ``padding: 6px 7px``, its 3 px top edge, its lines and the bar
            l1 = max(round(self.px * 1.35), EMBLEM)
            l2 = round(3 * self.px * 0.78 * 1.35)
            return 3 + 6 + l1 + 3 + l2 + 4 + 3 + 6
        l1 = round(self.px * 1.35)
        l2 = round(self.px * 0.8 * 1.35)
        return 6 + max(l1 + 2 + l2 + 4 + 3, EMBLEM) + 6

    def sizeHint(self):
        return QSize(120, self._height())

    def texts(self) -> list[str]:
        """The card's words, line by line, as a reader would read them."""
        lines = self._lines()
        return [" ".join(part[1] for part in line if part[1]) for line in lines] + ([self.damage, "damage"]
                                                                                  if not self.mini else [])

    def _lines(self) -> list[list[tuple[str, str]]]:
        """The card's lines as (kind, words) parts: its name line, then its facts' lines."""
        f = self.fighter
        name = [("name", _text(f.get("name")))]
        server = server_of(f)
        shown = [part for part in facts(f) if part[0] != "cp" or self.cp_room]
        dead = [("dot", "·"), ("dead", "dead")] if f.get("dead") else []
        if self.mini:                             # the server in the line's own words (``.arn-mini .l2``)
            first = [("word", server)] + ([("you", "you")] if f.get("self") else [])
            joined: list[tuple[str, str]] = []
            for index, part in enumerate(shown):
                if index and part[0] != "bold":
                    joined.append(("word", "·"))
                joined.append(part)
            second = joined or [("word", capitalised(f.get("class")))]
            third = [("bold", self.damage), ("word", "damage")] + dead
            return [name, first, second, third]
        first = name + [("small", server)] + ([("you", "you")] if f.get("self") else [])
        second = (shown or [("word", capitalised(f.get("class")))]) + dead
        return [first, second]

    # ---- drawing
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        f = self.fighter
        if f.get("dead"):
            painter.setOpacity(0.42)
        whole = QRectF(self.rect())
        ground = QPainterPath()
        ground.addRoundedRect(whole, 8, 8)
        painter.fillPath(ground, WHOLE_GROUND if self.whole else ROW_GROUND)
        edge = QColor(FOE_EDGE if f.get("side") == "enemy" else ALLY_EDGE)
        painter.save()
        painter.setClipPath(ground)
        if self.mini:                             # ``border-top: 3px solid``
            painter.fillRect(QRectF(0, 0, whole.width(), 3), edge)
        else:                                     # ``border-left: 3px solid``
            painter.fillRect(QRectF(0, 0, 3, whole.height()), edge)
        painter.restore()
        if self.mini:
            self._paint_mini(painter, whole)
        else:
            self._paint_card(painter, whole)

    def _parts(self, painter: QPainter, x: float, top: float, height: float, parts, base: QFont, gap: float,
               room: float, inline: bool = False) -> float:
        """A line's parts from ``x``: each in its kind's colour and weight, ``gap`` px apart (a flex line's) or a
        space apart (``inline``); the name and the server cut short where the room ends. Answers where it ended."""
        start, drawn = x, False
        for kind, words in parts:
            if not words and (inline or kind != "small"):   # an empty ``<small>`` is still a flex line's item
                continue
            if drawn:                             # a space between words inline (none before the first), else the gap
                x += gap if not inline else QFontMetricsF(base).horizontalAdvance(" ")
            drawn = True
            font, colour = base, FACTS
            if kind == "name":
                font, colour = sized(base, base.pixelSize(), 700), NAME
            elif kind == "small":
                font, colour = sized(base, base.pixelSize() * 0.8, 600), SMALL
            elif kind == "you":
                font, colour = sized(base, base.pixelSize(), 700), TEAL
            elif kind == "bold":
                font, colour = sized(base, base.pixelSize(), 700), BOLD
            elif kind == "dead":                  # bold, in the line's bold colour (``.l2 b`` over ``.arn-deadtxt``)
                font, colour = sized(base, base.pixelSize(), 700), BOLD
            elif kind == "cp":
                font, colour = sized(base, base.pixelSize(), 700), TEAL
            metrics = QFontMetricsF(font)
            left = room - (x - start)
            text = metrics.elidedText(words, Qt.ElideRight, max(0.0, left)) if kind in ("name", "small") else words
            if kind == "cp":                      # the crossed swords, 1.3em, 3 px before the figure
                side = 1.3 * font.pixelSize()
                swords(painter, x, top + height / 2, side, QColor(self.look.contrast or colour))
                x += side + 3
            x += draw_text(painter, QRectF(x, top, metrics.horizontalAdvance(text) + 1, height), text, font,
                           QColor(self.look.contrast or colour), Qt.AlignLeft, self.look, shadow=ROW_SHADOW)
        return x

    def _bar(self, painter: QPainter, rect: QRectF) -> None:
        track = QPainterPath()
        track.addRoundedRect(rect, 2, 2)
        painter.fillPath(track, HP_TRACK)
        share = hp_share(self.fighter)
        if share > 0:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(rect.left(), rect.top(), rect.width() * share, rect.height()), 2, 2)
            painter.fillPath(fill, HP_FILL)

    def _paint_card(self, painter: QPainter, whole: QRectF) -> None:
        """The list's card: ``padding: 6px 9px 6px 7px`` inside its 3 px edge, the emblem, then the name line, the facts'
        line and the HP bar, the damage at the right; 8 px apart."""
        inner = whole.adjusted(3 + 7, 6, -9, -6)
        x = inner.left()
        if self.picture is not None:
            _emblem(painter, self.picture, QRectF(x, inner.center().y() - EMBLEM / 2, EMBLEM, EMBLEM))
            x += EMBLEM + 8 + 8
        big = sized(self.look.font("name", self.px, 800), self.px * 1.02, 800)
        small = sized(big, self.px * 1.02 * 0.72, 600)
        right = max(QFontMetricsF(big).horizontalAdvance(self.damage), QFontMetricsF(small).horizontalAdvance("damage"))
        dmg_top = inner.center().y() - (round(big.pixelSize() * 1.1) + round(small.pixelSize() * 1.1)) / 2
        draw_text(painter, QRectF(inner.right() - right, dmg_top, right, round(big.pixelSize() * 1.1)), self.damage, big,
                  QColor(self.look.contrast or "#ffffff"), Qt.AlignRight, self.look, shadow=ROW_SHADOW)
        draw_text(painter, QRectF(inner.right() - right, dmg_top + round(big.pixelSize() * 1.1), right,
                                  round(small.pixelSize() * 1.1)), "damage", small,
                  QColor(self.look.contrast or FACTS), Qt.AlignRight, self.look, shadow=ROW_SHADOW)
        room = inner.right() - right - 8 - x
        first, second = self._lines()
        l1 = round(self.px * 1.35)
        l2 = round(self.px * 0.8 * 1.35)
        block = l1 + 2 + l2 + 4 + 3
        top = inner.center().y() - block / 2
        base = sized(self.look.font("name", self.px, 700), self.px, 700)
        self._parts(painter, x, top, l1, first, base, 6, room)
        facts_font = sized(base, self.px * 0.8, 400)
        self._parts(painter, x, top + l1 + 2, l2, second, facts_font, 6, room)
        self._bar(painter, QRectF(x, top + l1 + 2 + l2 + 4, room, 3))

    def _paint_mini(self, painter: QPainter, whole: QRectF) -> None:
        """The grid's small card: ``padding: 6px 7px`` under its 3 px edge, the emblem and the name, three short
        lines at .78em, then the HP bar."""
        inner = whole.adjusted(7, 3 + 6, -7, -6)
        l1 = max(round(self.px * 1.35), EMBLEM)
        x = inner.left()
        if self.picture is not None:
            _emblem(painter, self.picture, QRectF(x, inner.top() + (l1 - EMBLEM) / 2, EMBLEM, EMBLEM))
            x += EMBLEM + 8 + 6
        name, first, second, third = self._lines()
        base = sized(self.look.font("name", self.px, 700), self.px, 700)
        self._parts(painter, x, inner.top(), l1, name, base, 6, inner.right() - x)
        small = sized(base, self.px * 0.78, 400)
        line = round(self.px * 0.78 * 1.35)
        top = inner.top() + l1 + 3
        for parts in (first, second, third):
            self._parts(painter, inner.left(), top, line, parts, small, 0, inner.width(), inline=True)
            top += line
        self._bar(painter, QRectF(inner.left(), top + 4, inner.width(), 3))


class CardsPart(QWidget):
    """The cards in the rows' place (``A2Arena.players``): each side's head and its cards, as a list, or in the grid
    the two sides side by side (``.arn-grid``: two columns 10 px apart, each two small cards a row 5 px apart)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(0)
        self.heads = [Section(self), Section(self)]
        self.cards: list[Card] = []
        self.whole = True
        self.shape = None                         # the sides' sizes and the style the cards are laid out for

    def set_match(self, arena: dict, grid: bool, pictures, look: TextLook, px: int, duration, cp_room: bool,
                  base: QFont, whole: bool = True) -> None:
        """Draw the match: each card drawn anew in place while the sides keep their sizes and the style, laid out
        afresh when either changes (a reading comes twice a second)."""
        self.whole = whole
        allies, enemies = sides(arena)
        groups = ((self.heads[0], "Allies", ALLIES, allies), (self.heads[1], "Enemies", ENEMIES, enemies))
        shape = (grid, len(allies), len(enemies))
        if shape != self.shape:
            self.shape = shape
            self._lay_out(grid, groups)
        for head, words, colour, group in groups:
            head.set_runs([(f"{words} · {len(group)}", colour)], look, base)
        for card, fighter in zip(self.cards, allies + enemies):
            card.set_card(fighter, pictures.emblem(fighter.get("class")) if pictures is not None else None, look, px,
                          damage(fighter, duration), cp_room, whole)

    def _lay_out(self, grid: bool, groups) -> None:
        """The heads and as many cards as the sides hold, as a list or the grid."""
        _empty(self.column)
        for card in self.cards:
            card.hide()
            card.deleteLater()
        self.cards = []
        if grid:
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(10)
            for head, _words, _colour, group in groups:
                side = QVBoxLayout()
                side.setContentsMargins(0, 0, 0, 0)
                side.setSpacing(0)
                head.show()
                side.addWidget(head)
                cells = QGridLayout()
                cells.setContentsMargins(0, 0, 0, 0)
                cells.setSpacing(5)
                for index, _fighter in enumerate(group):
                    cells.addWidget(self._card(True), index // 2, index % 2)
                cells.setColumnStretch(0, 1)
                cells.setColumnStretch(1, 1)
                side.addLayout(cells)
                side.addStretch(1)
                line.addLayout(side, 1)
            self.column.addLayout(line)
            return
        for number, (head, _words, _colour, group) in enumerate(groups):
            head.show()
            self.column.addWidget(head)
            for index, _fighter in enumerate(group):
                self.column.addWidget(self._card(False))
                if number or index < len(group) - 1:   # ``margin: 0 0 5px``, folded into the next head's 7 px above it
                    self.column.addSpacing(5)

    def _card(self, mini: bool) -> Card:
        card = Card(self, mini)
        card.show()
        self.cards.append(card)
        return card


def _empty(layout) -> None:
    """A layout's items taken out, its inner layouts' too (the widgets stay theirs to keep or let go)."""
    while layout.count():
        item = layout.takeAt(0)
        if item.layout() is not None:
            _empty(item.layout())


# ---------------------------------------------------------------------------------------------- the window
class PlayersOverlay(MeterOverlay):
    """The player cards window: the meter overlay's window holding the match's players (overlay.js
    ``renderPlayers``)."""

    def __init__(self, api=None, parent_process=None, store=None, win32=None):
        super().__init__(api, parent_process, store, win32)
        self.setWindowTitle("Aion 2 Calc Player Cards")
        self.host.place = "overlay_players_pos"
        for key in ("split", "copy", "options", "capture"):   # of the toolbar only Lock and Hide (``#ov.ov-players``)
            self.tools[key].hide()
        for tab in self.tabs.values():
            tab.hide()
        self.metric_chip.hide()
        self.head = PlayersHead(self.card)        # in the target card's place
        self.box.insertWidget(self.box.indexOf(self.target_card), self.head)
        self.cards = CardsPart(self.content)
        self.content_box.addWidget(self.cards)
        self.match: dict | None = None
        self.apply_meter(self.answer)

    def apply_ui(self, ui: dict) -> None:
        super().apply_ui(ui)
        if not isinstance(ui, dict):
            return
        grid = ui.get("overlay_players_style") == "grid"
        self.setFixedWidth(GRID_WIDTH if grid else LIST_WIDTH)
        for grip in self.grips.values():          # the page's grips changed the meter overlay's own width
            grip.hide()
        self.fps.run(False)
        self.fps.hide()
        self.apply_meter(self.answer)

    def render_events(self) -> None:
        """No events strip here (``#ov.ov-players #ovevents``)."""
        if hasattr(self, "events"):
            self.events.hide()

    def apply_meter(self, answer) -> None:
        """Draw the match's players (``renderPlayers``), the rest of the meter's window left out."""
        if not isinstance(answer, dict) or not hasattr(self, "cards"):
            if isinstance(answer, dict):
                self.answer = answer
            return
        self.answer = answer
        snap = answer.get("snapshot") if isinstance(answer.get("snapshot"), dict) else {}
        on = self._arena_setting("overlay_arena_mode") is not False
        arena = match_of(snap, on)
        self.match = arena
        tl, px = self.text_look, self._px()
        title, tag = head_words(arena)
        bare, whole = self.card.mode == "none", self.card.mode == "card"
        self.head.set_head(title, tag, tl, px, CHIP_SHADOW if bare else None, whole)
        self.head.show()
        self.status_text = status(arena)
        for part in (self.connection, self.lines_part, self.target_card, self.arena_card, self.dummy, self.warning,
                     self.plan_map, self.panel_scroll, self.graph, self.cooldowns, self.clock, self.contribution,
                     self.identity, self.events, self.ping, self.fps, self.options, self.chips):
            part.hide()
        for row in self.rows:
            row.hide()
        for pool in self._arena_pool.values():
            for widget in pool:
                widget.hide()
        grid = self.ui.get("overlay_players_style") == "grid"
        if arena is None:
            self.cards.hide()
            self.empty.setText(WAITING if on else ARENA_OFF)
            self.empty.show()
        else:
            self.empty.hide()
            margins = self.box.contentsMargins()
            room = self.width() - margins.left() - margins.right()
            self.cards.set_match(arena, grid, self.pictures, tl, px, snap.get("duration"), room > 26.5 * px,
                                 QFont(self.font()), whole)
            self.cards.show()
        self.content_box.setContentsMargins(0, 6, 0, 0)
        self._sync_tools()
        if self._meter_poller is not None:        # twice a second in a fight, once a second out of one
            running = answer.get("running") is True
            self._meter_poller.set_interval((500 if running else 1000) * (2 if self._perf else 1))
        self._relayout()
        self.card.update()

    def hide_overlay(self) -> None:
        """Hide: this window alone closes (``view: "players"``)."""
        if self.requests is None:
            self._close_now()
            return
        self.tools["hide"].setEnabled(False)
        self.requests.post("hide", "/api/overlay", {"action": "hide", "view": "players"})
