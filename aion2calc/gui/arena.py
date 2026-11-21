"""The native overlay's arena mode (0.2.423): what the meter overlay shows in the Arena of Solitude, the Arena of
Cooperation and a battlefield, as the web overlay's arena view draws it (arena-view.js ``A2Arena``, overlay.css
``.arn-*``), from the meter's ``arena`` reading (aion2calc/meter/session.py ``_live_arena``).

The layouts are the web overlay's:
- **stacked**: the opponent's card, then DPS, D.Taken and HPS as three sections of the usual rows;
- **compact**: one row per fighter with the three side by side, the default;
- **versus**: you and the opponent face each other on one card, and each metric is a tug-of-war bar.

In a team match your own three come first, then the party in the metric the metric chip picks, or all three for
everyone with *All 3 for party* on. This module holds the reading's arithmetic, kept apart from what draws it so it
can be tested alone; every figure is the meter's own.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme
from .look import CHIP_SHADOW, ROW_SHADOW, TextLook, draw_text

#: The three metrics, in the arena view's order: key, words, colour (``.arn-sec .d``, ``.t``, ``.h``).
METRICS = (("dps", "DPS", "#f1d27c"), ("dtps", "D.Taken", "#ff8f86"), ("hps", "HPS", "#7fe0a0"))
LAYOUTS = ("stacked", "compact", "versus")
_UNNAMED = re.compile(r"Player #\d+")


def num(value) -> float:
    """A reading's number, 0 for anything else (``Number(v) || 0``)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def share(value: float, total: float) -> str:
    """A value's share of the total to a tenth, "—" with no total (arena-view.js ``pct``)."""
    return theme.fixed(100 * value / total, 1) + "%" if total > 0 else "—"


def fighters(arena) -> list[dict]:
    found = arena.get("fighters") if isinstance(arena, dict) else None
    return [f for f in found if isinstance(f, dict)] if isinstance(found, list) else []


def find(arena: dict, key) -> dict | None:
    return next((f for f in fighters(arena) if f.get("key") == key), None) if key else None


def solo(arena) -> bool:
    return isinstance(arena, dict) and arena.get("kind") == "solitude"


def you(arena: dict, players: list, is_me) -> dict | None:
    """Your fighter, else your meter row (a match without a roster names you through the party list)."""
    own = find(arena, arena.get("you")) or next((f for f in fighters(arena) if f.get("self")), None)
    if own is not None:
        return own
    row = next((p for p in players if is_me(p)), None)
    if row is None:
        return None
    return {"key": f"row:{row.get('key') or row.get('id')}", "name": row.get("name"), "class": row.get("class"),
            "side": "ally", "self": True, "dps": row.get("dps"), "dtps": row.get("dtps"), "hps": row.get("hps")}


def foe(arena: dict) -> dict | None:
    """The card's fighter: the opponent of a one-against-one match, else your current target among the enemies."""
    return find(arena, arena.get("opponent")) or find(arena, arena.get("target"))


def name_of(fighter: dict) -> str:
    """A fighter's name as the rows show it: your own unnamed one reads "You" (overlay.js ``arenaContext.name``)."""
    name = str(fighter.get("name") or "")
    return "You" if fighter.get("self") and _UNNAMED.fullmatch(name) else name


def where(fighter: dict) -> str:
    """The server and the faction: "Siel · Elyos"."""
    server = fighter.get("server_name") or (f"server {fighter['server']}" if fighter.get("server") else "")
    faction = str(fighter.get("faction") or "")
    faction = faction[:1].upper() + faction[1:]
    return " · ".join(part for part in (str(server), faction) if part)


def hp_of(fighter: dict) -> float | None:
    """A fighter's HP in percent, 0 to 100, or None where the meter has none."""
    hp = fighter.get("hp_pct")
    if hp is None or isinstance(hp, bool):
        return None
    try:
        hp = float(hp)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, 100 * hp)) if math.isfinite(hp) else None


def grouped(value) -> str:
    """``Number(v).toLocaleString()`` of a whole count (a rating, a gear score), grouped as the system groups them."""
    return theme.digits(num(value))


def power(fighter: dict) -> tuple[str | None, list[tuple[str, str]]]:
    """The card's first line (``powerLine``): the combat power for its chip, if any, then the rest as runs of text and
    whether each is bold: the gear score, the class, the level and the arena rating, " · " between them."""
    chip = theme.sfmt(fighter["combat_power"]) if fighter.get("combat_power") else None
    bits: list[list[tuple[str, bool]]] = []
    if fighter.get("gear_score"):
        bits.append([("GS ", False), (grouped(fighter["gear_score"]), True)])
    if fighter.get("class"):
        bits.append([(str(fighter["class"]).capitalize(), False)])
    if fighter.get("level"):
        bits.append([(f"Lv {fighter['level']}", False)])
    if fighter.get("rating"):
        bits.append([("Rating ", False), (grouped(fighter["rating"]), True)])
    runs: list[tuple[str, bool]] = []
    for index, bit in enumerate(bits):
        if index:
            runs.append((" · ", False))
        runs += bit
    return chip, runs


def match(arena: dict, fighter: dict) -> list[tuple[str, bool]]:
    """The card's second line (``matchLine``), as runs of text and whether each is bold: in the Arena of Solitude
    the result or the round and the score, elsewhere the share of the damage you took that this fighter dealt and
    its deaths."""
    if solo(arena):
        won, lost = int(num(arena.get("won"))), int(num(arena.get("lost")))
        if arena.get("result"):
            after = arena.get("rating_after")
            return ([("You won " if arena["result"] == "win" else "You lost ", False), (f"{won}–{lost}", True)]
                    + ([(" · rating now ", False), (grouped(after), True)] if after else []))
        if arena.get("round"):
            lead = "you lead" if won > lost else "you trail" if won < lost else "level"
            return [(f"Round {arena['round']} · {lead} ", False), (f"{won}–{lost}", True)]
        return []
    runs: list[tuple[str, bool]] = []
    if fighter.get("share_of_your_damage_taken") is not None:
        runs += [("Dealt ", False), (f"{theme.js_round(100 * num(fighter['share_of_your_damage_taken']))}%", True),
                 (" of the damage you took", False)]
    if fighter.get("deaths"):
        runs += ([(" · ", False)] if runs else []) + [("Deaths ", False), (f"{int(num(fighter['deaths']))}", True)]
    return runs


def party(arena: dict, players: list, is_me) -> list[dict]:
    """The party's fighters: the meter's own rows (the same players, order and figures as outside arena mode), each
    with what the arena knows of them; without rows, the arena's allies (``partyFighters``)."""
    out = []
    for player in players:
        own = next((f for f in fighters(arena) if f.get("id") is not None and str(f.get("id")) == str(player.get("id"))),
                   None) or {}
        out.append({**own, "key": f"row:{player.get('key') or player.get('id')}", "name": player.get("name"),
                    "class": player.get("class") or own.get("class"), "side": "ally",
                    "self": bool(is_me(player) or own.get("self")), "dps": player.get("dps"), "dtps": player.get("dtps"),
                    "hps": player.get("hps"), "dead": player.get("dead"),
                    "combat_power": player.get("combat_power") or own.get("combat_power")})
    return out or [f for f in fighters(arena) if f.get("side") == "ally"]


def most(group: list[dict]) -> list[float]:
    """Each metric's highest value among ``group`` (its bars' whole), 0 at the least."""
    return [max([0.0] + [num(f.get(key)) for f in group]) for key, _words, _colour in METRICS]


def total(group: list[dict]) -> list[float]:
    """Each metric's sum over ``group`` (its shares' whole)."""
    return [sum(num(f.get(key)) for f in group) for key, _words, _colour in METRICS]


def metric_key(metric: str) -> str:
    """The arena's metric for the metric chip's: DPS, damage taken or HPS."""
    return {"hps": "hps", "dtps": "dtps"}.get(metric, "dps")


def clock_tail(arena: dict, players: list, is_me, metric: str, all3: bool) -> list[tuple[str, bool]]:
    """What the clock says after the time in arena mode (``A2Arena.clock``): the match and its score in the Arena of
    Solitude; elsewhere the match and the party's total in the chip's metric (DPS with all three on), as runs of text
    and whether each is the bold figure."""
    label = str(arena.get("label") or "PvP match")
    if solo(arena):
        score = arena.get("round") or arena.get("result")
        return [(label, False)] + ([(" · ", False), (f"{int(num(arena.get('won')))}–{int(num(arena.get('lost')))}",
                                                       True)] if score else [])
    key = "dps" if all3 else metric_key(metric)
    short = {"hps": "HPS", "dtps": "DTPS"}.get(key, "DPS")
    return [(f"{label} · Party {short} ", False),
            (theme.kfmt(sum(num(f.get(key)) for f in party(arena, players, is_me))), True)]


def arena_of(snap: dict, cleared: bool, on: bool) -> dict | None:
    """The arena reading the overlay draws, or None: arena mode on, the fight not cleared, and a PvP match the meter
    names, with its fighters (overlay.js ``arenaOf``)."""
    arena = snap.get("arena") if isinstance(snap, dict) else None
    return arena if on and not cleared and isinstance(arena, dict) and fighters(arena) else None


def body(arena: dict, players: list, is_me, layout: str, metric: str, all3: bool) -> list[tuple]:
    """The rows' part in arena mode (``A2Arena.body``), as the items to draw, top to bottom:

    - ``("section", runs)``: a section's head, its words as runs of text and their colours (None: the head's own);
    - ``("row", fighter, value, total, most, label, cp)``: a row of the meter, its bar the value's share of ``most``,
      its rate the value and its share of ``total``; ``label`` in place of the name (your three: the metric's words),
      ``cp`` whether its combat-power chip shows;
    - ``("tri", fighter, most_dps)``: a row with all three of a fighter's figures, its bar its DPS;
    - ``("head", first)``: the compact table's head, ``first`` over its names;
    - ``("table", fighter, mosts)``: a compact table's row, each figure over a bar of its share of the most;
    - ``("tug", runs, a, b, colour_a, colour_b)``: a tug of war between you (``a``) and the opponent (``b``)."""
    if solo(arena):
        return _solo(arena, players, is_me, layout)
    return _team(arena, players, is_me, layout, metric, all3)


def _label(key: str) -> tuple[str, str]:
    words, colour = next((w, c) for k, w, c in METRICS if k == key)
    return words, colour


def _solo(arena: dict, players: list, is_me, layout: str) -> list[tuple]:
    me, them = you(arena, players, is_me), foe(arena)
    pair = [f for f in (me, them) if f is not None]
    if not pair:
        return []
    if layout == "compact":
        mosts = most(pair)
        return [("head", "Fighter")] + [("table", f, mosts) for f in pair]
    if layout == "versus" and me is not None and them is not None:
        a, b = theme.class_color(me.get("class")), theme.class_color(them.get("class"))
        items: list[tuple] = [("section", [("You ", None), ("vs", "#f1d27c", 4.0), (f" {them.get('name') or ''}", None)])]
        for key, words, colour in METRICS:
            items.append(("tug", [(words, colour)], num(me.get(key)), num(them.get(key)), a, b))
        return items
    mosts, totals = most(pair), total(pair)
    items = []
    for index, (key, words, colour) in enumerate(METRICS):
        items.append(("section", [(words, colour)]))
        items += [("row", f, num(f.get(key)), totals[index], mosts[index], None, index == 0) for f in pair]
    return items


def _team(arena: dict, players: list, is_me, layout: str, metric: str, all3: bool) -> list[tuple]:
    group = party(arena, players, is_me)
    me = you(arena, players, is_me)
    mosts = most(group if group else [f for f in (me,) if f is not None])
    totals = total(group)
    items: list[tuple] = []
    # Compact with "All 3 for party" is one table, your row marked among the party's (0.2.396).
    if me is not None and layout != "versus" and not (layout == "compact" and all3):
        if layout == "compact":
            items += [("head", "You"), ("table", me, mosts)]
        else:
            items.append(("section", [(f"You · {name_of(me)}", None)]))
            items += [("row", me, num(me.get(key)), totals[index], mosts[index], words, False)
                      for index, (key, words, _colour) in enumerate(METRICS)]
    if all3:
        if layout == "compact":
            return [("head", "Party")] + [("table", f, mosts) for f in group]
        heads: list[tuple[str, str | None]] = [("Party · ", None)]
        for index, (_key, words, colour) in enumerate(METRICS):
            heads += ([(" · ", None)] if index else []) + [(words, colour)]
        return items + [("section", heads)] + [("tri", f, mosts[0]) for f in group]
    key = metric_key(metric)
    index = [k for k, _w, _c in METRICS].index(key)
    words, colour = _label(key)
    ranked = sorted(group, key=lambda f: num(f.get(key)), reverse=True)
    return (items + [("section", [("Party · ", None), (words, colour)])]
            + [("row", f, num(f.get(key)), totals[index], mosts[index], None, True) for f in ranked])


# ---------------------------------------------------------------------------------------------------------------------
# What draws it: the card's lines, the sections' heads, the compact table's head and the tug of war. The rows are the
# overlay's own (``PlayerRow``, and ``ArenaRow`` for all three figures or the compact table).
LINE = QColor(255, 255, 255, 20)          # ``--nm-line``
TAG_GROUND = QColor(232, 90, 90, 46)      # ``.arn-tag``: rgba(232, 90, 90, .18)
#: The combat power's crossed swords (``--nm-ic-cp``), its strokes in a 24-unit square.
SWORDS = ((4, 4, 15, 15), (13, 17, 17, 13), (15, 15, 19, 19), (20, 4, 9, 15), (7, 13, 11, 17), (9, 15, 5, 19))


def sized(font: QFont, px: float, weight: int | None = None, spacing: float = 0.0) -> QFont:
    """``font`` at ``px`` pixels (whole), ``weight`` and ``spacing`` px between its letters."""
    made = QFont(font)
    made.setPixelSize(max(6, round(px)))
    if weight is not None:
        made.setWeight(QFont.Weight(weight))
    if spacing:
        made.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return made


@dataclass
class Run:
    """A span of a card's line: its words, font and colour, the room before it (``margin``), and what it is: plain,
    a tag on its own ground (``.arn-tag``), or a combat power after its crossed swords (``.ovcp``)."""
    text: str
    font: QFont
    colour: str
    margin: float = 0.0
    kind: str = ""

    def width(self) -> float:
        width = QFontMetricsF(self.font).horizontalAdvance(self.text)
        if self.kind == "tag":
            width += 10                            # ``padding: 1px 5px``
        elif self.kind == "cp":
            width += 1.3 * self.font.pixelSize() + 3   # the swords, 1.3em, and 3 px
        return width


def swords(painter: QPainter, x: float, middle: float, side: float, colour: QColor) -> None:
    """The crossed swords before a combat power, ``side`` px square, upright in the middle at ``middle``."""
    painter.save()
    painter.translate(x, middle - side / 2)
    painter.scale(side / 24, side / 24)
    painter.setPen(QPen(colour, 2.2, Qt.SolidLine, Qt.RoundCap))
    for x1, y1, x2, y2 in SWORDS:
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    painter.restore()


class Line(QWidget):
    """A line of the arena's card, its spans on one baseline as the web overlay's (``align-items: baseline``):
    ``left`` from the left, cut short with "…" where it runs out of room, ``right`` against the right edge ``gap`` px
    from it. Drawn with the look's effects, over the chips' shadow where the card has nothing behind it."""

    def __init__(self, parent=None, line_height: float = 1.35):
        super().__init__(parent)
        self.left: list[Run] = []
        self.right: list[Run] = []
        self.look = TextLook({})
        self.shadow = None
        self.align = Qt.AlignLeft                  # ``right``: the versus card's opponent, its line to the right
        self.line_height = line_height
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_runs(self, left: list[Run], right: list[Run], look: TextLook, shadow=None) -> None:
        self.left, self.right, self.look, self.shadow = left, right, look, shadow
        self.setFixedHeight(self._height())
        self.update()

    def text(self) -> str:
        return "".join(run.text for run in self.left) + ("  " + "".join(run.text for run in self.right)
                                                         if self.right else "")

    def _height(self) -> int:
        runs = self.left + self.right
        return max([round(run.font.pixelSize() * self.line_height) for run in runs] + [1])

    def sizeHint(self):
        return QSize(int(sum(r.margin + r.width() for r in self.left + self.right)) + 1, self._height())

    def paintEvent(self, event):
        runs = self.left + self.right
        if not runs:
            return
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        metrics = [QFontMetricsF(run.font) for run in runs]
        ascent = max(m.ascent() for m in metrics)
        descent = max(m.descent() for m in metrics)
        baseline = (self.height() - ascent - descent) / 2 + ascent
        right_width = sum(run.margin + run.width() for run in self.right)
        room = self.width() - (right_width + 8 if self.right else 0)
        left_width = sum(run.margin + run.width() for run in self.left)
        x = self.width() - min(left_width, room) if self.align & Qt.AlignRight else 0.0
        painter.save()
        painter.setClipRect(QRectF(0, 0, max(0.0, room), self.height()))
        cut = left_width > room + 0.5
        for run in self.left:
            x += run.margin
            x += self._run(painter, run, x, baseline, room if cut else None)
        painter.restore()
        x = self.width() - right_width
        for run in self.right:
            x += run.margin
            x += self._run(painter, run, x, baseline, None)

    def _run(self, painter: QPainter, run: Run, x: float, baseline: float, room) -> float:
        metrics = QFontMetricsF(run.font)
        text = run.text
        if room is not None and x + run.width() > room:   # ``text-overflow: ellipsis``
            text = metrics.elidedText(text, Qt.ElideRight, max(0.0, room - x - (10 if run.kind == "tag" else 0)))
        width = metrics.horizontalAdvance(text)
        top = baseline - metrics.ascent()
        colour = QColor(self.look.contrast or run.colour)
        if run.kind == "tag":                      # its own ground, raised 2 px (``vertical-align: 2px``)
            top -= 2
            ground = QPainterPath()
            ground.addRoundedRect(QRectF(x, top - 1, width + 10, metrics.height() + 2), 4, 4)
            painter.fillPath(ground, TAG_GROUND)
            draw_text(painter, QRectF(x + 5, top, width + 1, metrics.height()), text, run.font, colour,
                      Qt.AlignLeft, self.look, shadow=self.shadow)
            return width + 10
        if run.kind == "cp":                       # ``.ovcp::before``: the swords, 1.3em, 3 px before the figure
            side = 1.3 * run.font.pixelSize()
            swords(painter, x, top + metrics.height() / 2, side, colour)
            draw_text(painter, QRectF(x + side + 3, top, width + 1, metrics.height()), text, run.font, colour,
                      Qt.AlignLeft, self.look, shadow=self.shadow)
            return side + 3 + width
        draw_text(painter, QRectF(x, top, width + 1, metrics.height()), text, run.font, colour, Qt.AlignLeft,
                  self.look, shadow=self.shadow)
        return width


class Section(QWidget):
    """A section's head in the rows (``.arn-sec``): its words in capitals at 10 px of the text size, 800, spaced
    .9 px, each part in its colour or the head's grey, over the chips' shadow, then a fine line to the edge; 7 px
    above it, 4 below, 3 px in. Its parts are flex items, 6 px apart with the spaces at their ends gone, a part's own
    margin (``.arn-vsword``) on both its sides."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.runs: list[tuple[str, str | None]] = []
        self.look = TextLook({})
        self.base = QFont()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_runs(self, runs: list[tuple[str, str | None]], look: TextLook, base: QFont) -> None:
        self.runs, self.look, self.base = runs, look, base
        self.setFixedHeight(7 + round(self._font().pixelSize() * 1.35) + 4)
        self.update()

    def text(self) -> str:
        return " ".join(run[0].strip() for run in self.runs if run[0].strip()).upper()

    def _font(self) -> QFont:
        return sized(self.base, 10 * self.look.scale, 800, 0.9)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        made = self._font()
        rect = QRectF(3, 7, self.width() - 6, self.height() - 11)
        x, first = rect.left(), True
        for run in self.runs:
            text, colour, margin = run[0].strip(), run[1], (run[2] if len(run) > 2 else 0.0)
            if not text:
                continue
            x += (0 if first else 6) + margin
            first = False
            x += draw_text(painter, QRectF(x, rect.top(), max(1.0, rect.right() - x), rect.height()), text.upper(),
                           made, QColor(self.look.contrast or colour or "#aab3bd"), Qt.AlignLeft, self.look,
                           shadow=CHIP_SHADOW) + margin
        if x + 6 < rect.right():                   # ``::after``: the line over what is left
            painter.fillRect(QRectF(x + 6, round(rect.center().y()), rect.right() - x - 6, 1), LINE)


class TableHead(QWidget):
    """The compact table's head (``.arn-thead``): the names' column, then DPS, D.Taken and HPS over theirs in their
    colours, 9.5 px of the text size, 800, spaced .8 px, in capitals; 6 px above, 3 below, 3 px in, 9 px to the right
    (``grid-template-columns: 44% 1fr 1fr 1fr; gap: 8px``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.first = ""
        self.look = TextLook({})
        self.base = QFont()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_head(self, first: str, look: TextLook, base: QFont) -> None:
        self.first, self.look, self.base = first, look, base
        self.setFixedHeight(6 + round(self._font().pixelSize() * 1.35) + 3)
        self.update()

    def _font(self) -> QFont:
        return sized(self.base, 9.5 * self.look.scale, 800, 0.8)

    def columns(self) -> list[QRectF]:
        """Its four columns' places."""
        width = self.width() - 6 - 9
        first = 0.44 * width
        rest = max(0.0, (width - first - 3 * 8) / 3)
        top, height = 6.0, self.height() - 9.0
        places = [QRectF(3 + 4, top, first - 4, height)]
        x = 3 + first + 8
        for _index in range(3):
            places.append(QRectF(x, top, rest, height))
            x += rest + 8
        return places

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        made = self._font()
        places = self.columns()
        draw_text(painter, places[0], self.first.upper(), made, QColor(self.look.contrast or "#aab3bd"),
                  Qt.AlignLeft, self.look, shadow=CHIP_SHADOW)
        for place, (_key, words, colour) in zip(places[1:], METRICS):
            draw_text(painter, place, words.upper(), made, QColor(self.look.contrast or colour), Qt.AlignRight,
                      self.look, shadow=CHIP_SHADOW)


class Tug(QWidget):
    """A tug of war between you and the opponent (``.arn-tug``): a row's pill, your share of the two from the left
    in your class's colour and theirs from the right in theirs (each darkening toward its own edge, at 85%), your
    figure at the left, theirs at the right, and the metric's words in capitals in the middle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label: list[tuple[str, str]] = []
        self.a = self.b = 0.0
        self.colours = (QColor(), QColor())
        self.look = TextLook({})
        self.base = QFont()
        self.whole = True
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_tug(self, label, a: float, b: float, colour_a: str, colour_b: str, look: TextLook, base: QFont,
                whole: bool) -> None:
        self.label, self.a, self.b = label, a, b
        self.colours = (QColor(colour_a), QColor(colour_b))
        self.look, self.base, self.whole = look, base, whole
        self.update()

    def share(self) -> float:
        """Your share of the two, in percent (an even half with neither)."""
        both = self.a + self.b
        return 100 * self.a / both if both > 0 else 50.0

    def texts(self) -> tuple[str, str, str]:
        return (f"{theme.sfmt(self.a)}/s", "".join(words for words, _colour in self.label).upper(),
                f"{theme.sfmt(self.b)}/s")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        pill = QPainterPath()
        pill.addRoundedRect(rect, 7, 7)
        painter.fillPath(pill, QColor(255, 255, 255, 11) if self.whole else QColor(10, 12, 15, 140))
        painter.save()
        painter.setClipPath(pill)
        painter.setOpacity(0.85)
        split = rect.width() * self.share() / 100
        for side, colour in ((QRectF(0, 0, split, rect.height()), self.colours[0]),
                             (QRectF(split, 0, rect.width() - split, rect.height()), self.colours[1])):
            if side.width() <= 0:
                continue
            gradient = QLinearGradient(side.topLeft(), side.topRight())
            darker = QColor(round(colour.red() * 0.85), round(colour.green() * 0.85), round(colour.blue() * 0.85))
            first, last = (darker, colour) if side.left() == 0 else (colour, darker)
            gradient.setColorAt(0, first)
            gradient.setColorAt(1, last)
            painter.fillRect(side, gradient)
        painter.restore()
        figure = sized(self.base, 12 * self.look.scale * 1.02, 800)
        mine, words, theirs = self.texts()
        white = QColor(self.look.contrast or "#ffffff")
        draw_text(painter, QRectF(9, 0, rect.width() / 2, rect.height()), mine, figure, white, Qt.AlignLeft,
                  self.look, shadow=ROW_SHADOW)
        draw_text(painter, QRectF(rect.width() / 2, 0, rect.width() / 2 - 9, rect.height()), theirs, figure, white,
                  Qt.AlignRight, self.look, shadow=ROW_SHADOW)
        middle = sized(self.base, 12 * self.look.scale * 0.72, 800, 1.0)   # ``.mid``: the metric in near white
        width = QFontMetricsF(middle).horizontalAdvance(words)
        draw_text(painter, QRectF((rect.width() - width) / 2, 0, width + 1, rect.height()), words, middle,
                  QColor("#f3f5f7"), Qt.AlignLeft, self.look, shadow=ROW_SHADOW)
