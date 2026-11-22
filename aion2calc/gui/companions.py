"""The overlay's companion windows, natively (0.2.497): the Party-DPS window and the Hidden Cube radar's window, each a
small frameless Qt window over the game beside the meter overlay's, where until now each was the overlay page in a
pywebview window of its own (``overlay?view=party``, ``overlay?view=radar``).

They keep that page's older look (overlay.css without ``#ov.ov-nm``): a header with the green dot, the window's
buttons as words and, in the party window, Start/Stop at its right end; then what the window shows; then the opacity
slider and the app's name.

- **The Party-DPS window** (overlay.js ``renderParty``): the party's DPS, HPS, damage taken a second and total damage,
  each summed over the players of the meter's latest fight, or why there are none yet; the events strip and the live
  graph, as the meter overlay has them. Lock, New, Hide and Start/Stop act as the meter overlay's; Copy copies
  nothing, as on the web overlay, whose party window has no text of its own to copy.
- **The Hidden Cube radar's window** (``setupRadar``, ``renderRadar``): where a cube's jingle comes from on a circle
  around you (ahead at the top), how loud it is and whether it grows louder, read from the app three times a second
  (``/api/radar``), with Lock and Hide.

Each window keeps its own place (``overlay_party_pos_*``, ``overlay_radar_pos_*``), shows and hides with the game,
follows it and passes clicks through to it as the meter overlay does (``WindowHost``), takes the overlay's look (its
fonts, colours and effects, its background mode and image), locks with the screenshot hotkey, and ends with the
app. The party window's opacity is the meter overlay's and the radar's its own, as the web overlay keeps them.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy,
                               QSlider, QVBoxLayout, QWidget)

from . import events as schedule
from . import theme
from .api import AppApi, Poller, Requests
from .chrome import FlowLayout
from .chrome import font as sized_font
from .host import WindowHost
from .look import (ANIMATION_MS, TextEffect, TextLook, contrast_colour, cycled, draw_text, forget_pictures,
                   reduced_motion, sheen_brush)
from .overlay import (BACKGROUND_LIMIT, DEFAULT_OPACITY, GRAPH_LIMIT, START_SCOPE, SparkGraph, _Card, _app_base, _num,
                      filter_label, overlay_store)

#: The companion windows and what each is called on the desktop (the web overlay host's titles).
TITLES = {"party": "Aion 2 Calc Party Overlay", "radar": "Aion 2 Calc Radar Overlay", "pets": "Aion 2 Calc Pet Tracker"}
#: Where each keeps its place in the app's settings (the web overlay host's ``_save_overlay_position``).
PLACES = {"party": "overlay_party_pos", "radar": "overlay_radar_pos", "pets": "overlay_pets_pos"}
#: Where each keeps its opacity among the overlay's own values: the party window the meter overlay's, as the web
#: overlay keeps ``ovopacity`` for both, the radar's window its own (``ovopacity-radar``).
OPACITY_KEYS = {"party": "opacity", "radar": "opacity-radar", "pets": "opacity-pets"}
#: The older layout's card (overlay.css ``.ovcard``): rgba(27, 32, 42) at the window's opacity.
CARD = (27, 32, 42)
RADAR_WIDTH = 232                         # ``#ov.ov-radar .ovcard { width: 232px }``
RADAR_MS = 300                            # the radar's own poll (``setInterval(pollRadar, 300)``)
#: How near a cube is, by how loud it is (overlay.js ``RADAR_NEAR``).
RADAR_NEAR = ((0.8, "right here"), (0.5, "close"), (0.25, "nearby"), (0.0, "far"))
RADAR_TIP = ("The cube's jingle, heard in the game's sound, on a circle around you (ahead at the top): louder is "
             "closer. Once the radar has learned the cube's sound with it behind you (Settings → Overlay, step 3) and "
             "the game's 3D audio is on, or the sound plays in surround, it shows whether the cube is ahead or behind; "
             "until then two hollow marks show both places it can be: turn towards it (a cube ahead moves to the "
             "middle) or walk forward (one ahead grows louder). Empyrean Trace feathers sound alike: teach the radar "
             "one as a sound that is not a cube.")
#: The text's shadow where the card leaves it over the game (``#ov.ov-bg-none .ovhd``, ``.ovfoot``: ``0 1px 2px
#: #000, 0 0 4px #000``).
BARE_SHADOW = ((QColor(0, 0, 0), 1, 2), (QColor(0, 0, 0), 0, 4))
DOT = "#51e18c"                           # the header's dot (``.ovhd::before``)
LABEL_GREY = "#9aa3b5"                    # ``.ovpstat .ovplabel``, ``.muted``
GOLD = "#e8cf8e"                          # the header's and the rates' colour unless the look gives another
BUTTON_FAMILIES = ["Segoe UI", *[f for f in theme.FONT_FAMILIES if f != "Segoe UI"]]   # the buttons' own font


# ---------------------------------------------------------------------------------------------- what they show
def _js_text(value) -> str:
    """A value as JavaScript writes it into text."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def party_players(answer) -> list[dict]:
    """The players of the meter's latest fight (``snap.players || []``)."""
    snap = answer.get("snapshot") if isinstance(answer, dict) and isinstance(answer.get("snapshot"), dict) else {}
    players = snap.get("players")
    return [p for p in players if isinstance(p, dict)] if isinstance(players, list) else []


def party_stats(answer) -> list[tuple[str, str]]:
    """The party window's figures (overlay.js ``renderParty``): the party's DPS, HPS and damage taken a second, and
    its total damage, each summed over the fight's players; none while there are no players."""
    players = party_players(answer)
    if not players:
        return []
    total = {key: sum(_num(p.get(key)) for p in players) for key in ("dps", "hps", "dtps", "damage")}
    return [("Party DPS", theme.kfmt(total["dps"]) + "/s"), ("Party HPS", theme.kfmt(total["hps"]) + "/s"),
            ("Damage taken/s", theme.kfmt(total["dtps"]) + "/s"), ("Total damage", theme.kfmt(total["damage"]))]


def party_waiting(answer) -> str:
    """Why the party window has no figures yet: the capture runs and no player has acted, or there is no fight."""
    running = isinstance(answer, dict) and answer.get("running") is True
    return "Waiting for combat data…" if running else "No fight yet. Start the meter in the app."


def party_status(answer) -> str:
    """The party window's status (``#ovstatus``, which its stylesheet folds away with the metric row): the boss or
    whether it records, the players and the damage filter."""
    answer = answer if isinstance(answer, dict) else {}
    snap = answer.get("snapshot") if isinstance(answer.get("snapshot"), dict) else {}
    boss = snap.get("boss")
    what = _js_text(boss) if boss not in (None, "", 0, False) else ("recording" if answer.get("running") else "idle")
    filtered = filter_label(answer)
    return f"Party · {what} · {len(party_players(answer))} players" + (f" · {filtered}" if filtered else "")


def radar_text(r) -> str:
    """The radar's line (overlay.js ``radarText``): a learn step under way, one just done, why it cannot listen, what
    it waits for, or where the cube is, how near and whether it is getting closer."""
    r = r if isinstance(r, dict) else {}
    learning = r.get("learning")
    if learning:
        learning = learning if isinstance(learning, dict) else {}
        kind = learning.get("kind")
        what = ("the background" if kind == "background" else "a sound that is not a cube" if kind == "other"
                else "the cube's sound behind you" if learning.get("facing") == "behind" else "the cube's sound")
        seconds = _js_text(math.ceil(_num(learning.get("seconds"))))
        if learning.get("phase") == "countdown":
            return f"Learning {what} in {seconds} s: switch to the game"
        return f"Listening to {what}… {seconds} s"
    since = r.get("last_learn_s")
    if r.get("last_learn") and since is not None and _num(since) < 6:
        last = r["last_learn"]
        return _js_text(last.get("message") if isinstance(last, dict) else None)
    if not r.get("supported"):
        return "Hidden Cube radar: Windows only"
    if r.get("error"):
        return "Hidden Cube radar: " + _js_text(r["error"])
    if not r.get("ready"):
        return "Hidden Cube radar: teach it the cube's sound in Settings → Overlay"
    if not r.get("heard"):
        heard = r.get("since")
        ago = f" last heard {theme.js_round(_num(heard))} s ago" if heard is not None and _num(heard) < 60 else ""
        return "Listening for a Hidden Cube…" + ago
    proximity = _num(r.get("proximity"))
    near = next((words for least, words in RADAR_NEAR if proximity >= least), RADAR_NEAR[-1][1])
    trend = r.get("trend")
    trend = " · getting closer" if trend == "louder" else " · moving away" if trend == "quieter" else ""
    direction = r.get("direction")
    return f"Hidden Cube {_js_text(direction) if direction else 'nearby'} · {near}{trend}"


def blip_place(angle, proximity) -> tuple[float, float]:
    """Where a blip sits in the radar's 120 × 120 (overlay.js ``placeBlip``): ``angle`` degrees clockwise from ahead
    (up), nearer the middle the louder (``proximity``, 0 to 1), the rim the farthest it hears."""
    a = _num(angle) * math.pi / 180
    d = 6 + 50 * (1 - _num(proximity))
    return round(60 + d * math.sin(a), 1), round(60 - d * math.cos(a), 1)


def blip_opacity(since) -> float:
    """A blip fades in the 2.5 s after the cube was last heard, to a third of its colour (``renderRadar``)."""
    return round(max(0.35, 1 - _num(since) / 2.5), 2)


# ---------------------------------------------------------------------------------------------- the pieces
def look_as(look: TextLook, blend: bool = True, glows: bool = True) -> TextLook:
    """The look for words the web overlay draws with less of it: without the blend (``blend``), which it gives only
    to the readings it lists (``#ov.ov-ac-blend :is(...)``: the figures, the events, the notes and the app's name),
    and without the glow and the halo (``glows``) for a button's words, whose own ``text-shadow: none`` drops them."""
    if (blend or not look.blend) and (glows or not (look.glow or look.halo)):
        return look
    less = TextLook({})
    less.__dict__.update(vars(look))
    less.blend = less.blend and blend
    if not glows:
        less.glow = less.halo = False
    return less


class Dot(QWidget):
    """The header's green dot (``.ovhd::before``): 8 px, glowing, a pixel in from the edge and 7 px before what
    follows it, in the middle of the header's line; it turns with the colour cycle, as the whole header does."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.seconds: float | None = None
        self.setFixedSize(16, 20)                 # the line's height, so its glow is not cut above and below

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colour = QColor(DOT)
        if self.seconds is not None:
            colour = cycled(colour, self.seconds)
        middle = QPointF(5, self.height() / 2)
        glow = QRadialGradient(middle, 8)         # ``box-shadow: 0 0 6px rgba(81, 225, 140, .9)``
        edge = QColor(colour)
        edge.setAlphaF(0.6)
        glow.setColorAt(0.5, edge)
        glow.setColorAt(1.0, QColor(colour.red(), colour.green(), colour.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(middle, 8, 8)
        painter.setBrush(colour)
        painter.drawEllipse(middle, 4, 4)


class HeaderButton(QAbstractButton):
    """A button of the older header (overlay.css ``#ovlock``, ``#ovsplit``, ``#ovcopy``, ``#ovhide``; ``capture`` for
    ``#ovcapture``): its words at 10.5 px in a faint frame that shows under the pointer, Lock green while on; Start
    green and Stop red in a round frame of their colour. The words keep their own size whatever the overlay's, take
    the outline and turn with the colour cycle as the header does, and with the sheen on they are painted in the
    header's colour with its band (``#ov.ov-retro .ovhd``)."""

    def __init__(self, text: str, tip: str, capture: bool = False, parent=None, margins: tuple[int, int] = (0, 1)):
        super().__init__(parent)
        self.capture = capture
        self.margins = (0, 0) if capture else margins   # its room each side (``margin: 0 1px 0 0``; Hide's 1 and 2)
        self.on = False                           # Lock locked, or the capture running (``.on``)
        self.look = TextLook({})
        self.header_colour = GOLD
        self.seconds: float | None = None         # the colour cycle's moment, None held still
        self.sheen: float | None = None           # the sheen's moment over the header (``sheen_rect``), None without it
        self.sheen_rect = QRectF()
        self.setText(text)
        self.setAccessibleName(text)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)           # the overlay never takes the keyboard from the game
        self.setAttribute(Qt.WA_Hover)

    def words_font(self) -> QFont:
        return sized_font(BUTTON_FAMILIES, 10.5, 700 if self.capture else 600)

    def sizeHint(self):
        """Its words, ``padding: 2px 5px`` (8 px across for Start/Stop) and the frame's pixel each side; its line is
        10.5 px at 1.35."""
        words = QFontMetricsF(self.words_font()).horizontalAdvance(self.text())
        return QSize(math.ceil(words + (16 if self.capture else 10) + 2) + sum(self.margins), 20)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _colours(self) -> tuple[QColor, QColor | None, QColor | None]:
        """The words', the frame's and the ground's colours as the web overlay's rules give them now."""
        hovered = self.isEnabled() and self.underMouse()
        if self.capture:
            if self.on:
                words, frame, ground = QColor("#ff8585"), QColor(255, 110, 110, 128), QColor(255, 110, 110, 26)
            else:
                words, frame, ground = QColor("#6fe3a3"), QColor(81, 225, 140, 128), QColor(81, 225, 140, 31)
            if hovered:                           # ``filter: brightness(1.18)``
                words, frame, ground = (QColor.fromRgbF(min(1, c.redF() * 1.18), min(1, c.greenF() * 1.18),
                                                        min(1, c.blueF() * 1.18), c.alphaF())
                                        for c in (words, frame, ground))
            return words, frame, ground
        words, frame, ground = QColor("#8e97ad"), None, None
        if hovered:
            words, frame, ground = QColor("#f1f3f8"), QColor(255, 255, 255, 31), QColor(255, 255, 255, 15)
        if self.isDown():
            ground = QColor("#1c2438")
        if self.on:                               # ``#ovlock.on``
            words, frame = QColor("#8fd0a0"), QColor(143, 208, 160, 153)
        return words, frame, ground

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.55)
        words, frame, ground = self._colours()
        turn = (lambda colour: cycled(colour, self.seconds)) if self.seconds is not None else (lambda colour: colour)
        inner = QRectF(self.rect()).adjusted(self.margins[0], 0, -self.margins[1], 0)
        box = inner.adjusted(0.5, 0.5, -0.5, -0.5)
        radius = box.height() / 2 if self.capture else 6
        if ground is not None or frame is not None:
            path = QPainterPath()
            path.addRoundedRect(box, radius, radius)
            if ground is not None:
                painter.fillPath(path, turn(ground))
            if frame is not None:
                painter.setPen(QPen(turn(frame), 1))
                painter.drawPath(path)
        shown, brush = turn(words), None
        if self.sheen is not None or self.look.retro:   # painted with the header's band, in the header's colour
            shown = turn(QColor(self.header_colour))
            area = QRectF(self.sheen_rect) if self.sheen_rect.width() > 0 else QRectF(self.rect())
            brush = sheen_brush(area, shown, self.sheen or 0.0)
        draw_text(painter, inner, self.text(), self.words_font(), shown, Qt.AlignHCenter,
                  look_as(self.look, blend=False, glows=False), brush=brush,
                  shift=(lambda colour: cycled(colour, self.seconds)) if self.seconds is not None else None)


class Words(QWidget):
    """One line of words drawn with the overlay's look (``draw_text``): its effects, the colour cycle (``seconds``),
    the sheen (``sheen``) and a shadow where the card leaves it over the game; cut with an ellipsis where the line
    is too short for it (``text-overflow: ellipsis``). The radar's title and the party window's figures."""

    def __init__(self, parent=None, align=Qt.AlignLeft):
        super().__init__(parent)
        self.text = ""
        self.font_ = QFont()
        self.colour = GOLD
        self.align = align
        self.look = TextLook({})
        self.seconds: float | None = None
        self.sheen: float | None = None
        self.shadow = None
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_words(self, text: str, font: QFont, colour: str, look: TextLook, shadow=None) -> None:
        if (text, font.key(), colour, vars(look), shadow) != (self.text, self.font_.key(), self.colour,
                                                              vars(self.look), self.shadow):
            self.text, self.font_, self.colour, self.look, self.shadow = text, QFont(font), colour, look, shadow
            self.updateGeometry()
            self.update()

    def sizeHint(self):
        """Its words' width, and its line: its size at 1.35 (``line-height: 1.35``)."""
        metrics = QFontMetricsF(self.font_)
        px = self.font_.pixelSize() if self.font_.pixelSize() > 0 else self.font_.pointSizeF() / 0.75
        return QSize(math.ceil(metrics.horizontalAdvance(self.text)), math.ceil(px * 1.35))

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def shown(self) -> str:
        """The words as they fit: whole, or cut with an ellipsis."""
        return QFontMetricsF(self.font_).elidedText(self.text, Qt.ElideRight, self.width())

    def paintEvent(self, event):
        if not self.text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colour = QColor(self.colour)
        shift = None
        if self.seconds is not None:
            colour = cycled(colour, self.seconds)
            shift = lambda c: cycled(c, self.seconds)   # noqa: E731 - the effects turn with it
        brush = sheen_brush(QRectF(self.rect()), colour, self.sheen) if self.sheen is not None else None
        draw_text(painter, QRectF(self.rect()), self.shown(), self.font_, colour, self.align, self.look,
                  brush=brush, shift=shift, shadow=self.shadow)


class StatRow(QWidget):
    """One of the party window's figures (``.ovpstat``): its name at the left in grey, the figure at the right in
    the rate's colour and font, a little larger, on one baseline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = Words(self)
        self.value = Words(self, Qt.AlignRight)
        self.label_text = self.value_text = ""
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_stat(self, label: str, value: str, look: TextLook, px: int) -> None:
        self.label_text, self.value_text = label, value
        label_font = QFont()
        label_font.setFamilies(look.families())
        label_font.setPixelSize(px)
        label_font.setWeight(QFont.Weight(400))
        self.label.set_words(label, label_font, LABEL_GREY, look)
        rate = look.font("rate", px * 1.15, look.weight)
        self.value.set_words(value, rate, look.colour("rate", GOLD), look)
        height = math.ceil(max(px, rate.pixelSize()) * 1.35) + 4      # its line, and ``padding: 2px 0``
        self.setFixedHeight(height)
        self._place()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place()

    def _place(self) -> None:
        """Both on one baseline (``align-items: baseline``), the figure whole at the right, the name in the room
        left of it. Each line's baseline lies half its leading below its top, then the font's ascent."""
        width, height = self.width(), self.height() - 4
        value_width = min(width, self.value.sizeHint().width())
        label_metrics, value_metrics = QFontMetricsF(self.label.font_), QFontMetricsF(self.value.font_)
        value_height, label_height = self.value.sizeHint().height(), self.label.sizeHint().height()
        value_top = 2 + (height - value_height) // 2
        base = value_top + (value_height - value_metrics.height()) / 2 + value_metrics.ascent()
        label_top = round(base - (label_height - label_metrics.height()) / 2 - label_metrics.ascent())
        self.value.setGeometry(width - value_width, value_top, value_width, value_height)
        self.label.setGeometry(0, label_top, max(0, width - value_width - 4), label_height)


class RadarDial(QWidget):
    """The radar's circle (overlay.js ``renderRadar``'s SVG, a 120 × 120 view drawn at 76 px): three rings, the line
    ahead and the line across, you as an arrow in the middle, and the cube's blip where it is heard, fading in the
    2.5 s after; two hollow blips where it cannot tell ahead from behind."""

    def __init__(self, parent=None, side: int = 76):
        super().__init__(parent)
        self.blips: list[tuple[float, float, bool]] = []   # (x, y, hollow) in the 120 × 120 view
        self.opacity = 1.0
        self.setFixedSize(side, side)

    def set_reading(self, r: dict | None) -> None:
        """The blips for a reading: none until a cube is heard (or while the radar learns)."""
        blips = []
        if isinstance(r, dict) and r.get("heard") and not r.get("learning"):
            mirrored = r.get("mirror") is not None
            blips.append((*blip_place(r.get("angle"), r.get("proximity")), mirrored))
            if mirrored:
                blips.append((*blip_place(r.get("mirror"), r.get("proximity")), True))
            self.opacity = blip_opacity(r.get("since"))
        if blips != self.blips:
            self.blips = blips
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = self.width() / 120
        painter.scale(scale, scale)
        ring = QPen(QColor(232, 207, 142, 89), 1.2)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(ring)
        for radius in (56, 38, 20):
            painter.drawEllipse(QPointF(60, 60), radius, radius)
        for alpha, line in ((64, (60, 60, 60, 4)), (31, (4, 60, 116, 60))):   # ahead, and across (``.ovrside``)
            pen = QPen(QColor(232, 207, 142, alpha), 1)
            pen.setCapStyle(Qt.FlatCap)           # an SVG stroke's own ends (``stroke-linecap: butt``)
            pen.setDashPattern([2, 3])
            painter.setPen(pen)
            painter.drawLine(QPointF(*line[:2]), QPointF(*line[2:]))
        me = QPainterPath()
        me.moveTo(60, 53)
        for x, y in ((65, 65), (60, 62), (55, 65)):
            me.lineTo(x, y)
        me.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.fillPath(me, QColor("#cdd6e6"))
        painter.setOpacity(self.opacity)
        for x, y, hollow in self.blips:
            if hollow:                            # ``.ovrhollow``, ``.ovrghost``
                pen = QPen(QColor("#f0c36a"), 1.6)
                pen.setCapStyle(Qt.FlatCap)
                pen.setDashPattern([3 / 1.6, 2 / 1.6])   # ``stroke-dasharray: 3 2``, in the pen's widths
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
            else:
                painter.setPen(QPen(QColor("#fff3d0"), 1))
                painter.setBrush(QColor("#f0c36a"))
            painter.drawEllipse(QPointF(x, y), 5, 5)


class Foot(QWidget):
    """The opacity slider and the app's name under a faint line (overlay.css ``.ovfoot``)."""

    def __init__(self, parent=None, top: int = 7):
        super().__init__(parent)
        self.top = top                            # ``margin-top`` above the line
        self.line = True                          # the line, gone where the card leaves the foot over the game
        row = QHBoxLayout(self)
        row.setContentsMargins(0, top + 7, 0, 0)  # the margin, the line and ``padding-top: 6px``
        row.setSpacing(8)
        self.label = QLabel("Opacity", self)
        self.label.setObjectName("ovfootlabel")
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setObjectName("ovop")
        self.slider.setRange(20, 100)
        self.slider.setFixedHeight(16)
        self.slider.setToolTip("The card's opacity behind the readings")
        self.slider.setFocusPolicy(Qt.NoFocus)
        faded = QGraphicsOpacityEffect(self.slider)   # ``.ovfoot input[type=range] { opacity: .75 }``, gold accent
        faded.setOpacity(0.75)
        self.slider.setGraphicsEffect(faded)
        self.brand = QLabel("Aion 2 Calc", self)
        self.brand.setObjectName("ovbrand")
        row.addWidget(self.label)
        row.addWidget(self.slider, 1)
        row.addWidget(self.brand)
        self.setFixedHeight(top + 7 + 16)

    def paintEvent(self, event):
        if not self.line:
            return
        painter = QPainter(self)
        painter.setPen(QColor(255, 255, 255, 18))   # ``border-top: 1px solid rgba(255, 255, 255, .07)``
        painter.drawLine(QPointF(0, self.top + 0.5), QPointF(self.width(), self.top + 0.5))


# ---------------------------------------------------------------------------------------------- the windows
class CompanionWindow(QWidget):
    """A companion window: frameless, on top and see-through, its card the overlay's older card, with the header, the
    window's own part (``build``) and the foot. ``api`` is the app's local API (None in tests, which hand it the
    readings), ``store`` keeps its opacity with the overlay's own values, ``win32`` is the platform's help for its
    place and click-through (``native_overlay()``)."""

    VIEW = ""
    WIDTH: int | None = None                      # its card's own width, else the overlay's (``overlay_width``)
    PADDING = (12, 10, 12, 9)                     # the card's edge and padding (``padding: 9px 11px 8px``)
    HEADER_GAP = 6                                # under the header (``.ovhd { margin-bottom: 6px }``)
    FOOT_TOP = 7
    OPACITY = DEFAULT_OPACITY                     # its opacity until one is kept
    FOLLOWS_LOOK = True                           # whether it takes the overlay's look (overlay.js ``syncColors``)
    SETTINGS_MS = 3000                            # how often it reads the overlay's settings
    LOCK_HOTKEY = True                            # whether the screenshot hotkey locks it

    def __init__(self, api: AppApi | None = None, parent_process=None, store=None, win32=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle(TITLES[self.VIEW])
        self.api, self.parent_process, self.store = api, parent_process, store
        self.ui: dict = {}
        self.locked = False
        self.click_through = False
        self.text_look = TextLook({})
        self.host = WindowHost(self, win32, place=PLACES[self.VIEW])
        self._drag: QPoint | None = None
        self._press: QPoint | None = None
        self._seqs: dict = {}
        self._effects: dict[QLabel, TextEffect] = {}
        self._bg_image: QImage | None = None
        self._bg_pixmap: QPixmap | None = None
        self._bg_wanted = self._bg_asking = self._bg_failed = False
        self._contrast_key, self._contrast = None, None
        self._perf = False
        self._still = True
        self._sheet = self._base_sheet = ""
        self._shown_look = None                   # the look as last handed out, to tell when it changes
        self._kept_opacity: float | None = None
        self._anim_start = time.monotonic()
        self._anim_timer = QTimer(self)           # the colour cycle and the sheen
        self._anim_timer.setInterval(ANIMATION_MS)
        self._anim_timer.timeout.connect(self._animate)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = _Card(self)
        self.card.colour = CARD
        outer.addWidget(self.card)
        self.box = QVBoxLayout(self.card)
        self.box.setContentsMargins(*self.PADDING)
        self.box.setSpacing(0)
        self.header = QWidget(self.card)
        self.header.setAttribute(Qt.WA_TranslucentBackground)
        self.header_line = FlowLayout(self.header, Qt.AlignLeft, (1, 4))   # ``gap: 4px 1px``
        self.dot = Dot(self.header)
        self.header_line.addWidget(self.dot)
        self.title = Words(self.header)           # ``#ovviewtitle``: the room the buttons leave, cut short to it
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.title.hide()
        self.header_line.addWidget(self.title)
        self.header_line.grow(self.title)
        self.buttons: dict[str, HeaderButton] = {}
        self.box.addWidget(self.header)
        self.box.addSpacing(self.HEADER_GAP)
        self.foot = Foot(self.card, self.FOOT_TOP)   # made first, laid out last, under the window's own part
        self.build()
        self.box.addWidget(self.foot)
        self.box.addStretch(1)                    # a card taller than its parts (``overlay_height``) ends empty
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self._pollers: list[Poller] = []
        self._settings_poller = None
        if api is not None:
            self._settings_poller = Poller(api, "/api/ui", self.SETTINGS_MS, self)
            self._settings_poller.answered.connect(self.apply_ui)
            commands = Poller(api, "/api/overlay/commands", 1000, self)   # the screenshot hotkey, Open overlay
            commands.answered.connect(self._commands)
            self._pollers = [self._settings_poller, commands]
        self._kept_opacity = self._stored(OPACITY_KEYS[self.VIEW], self.OPACITY)
        self.set_opacity(self._kept_opacity)
        self.foot.slider.valueChanged.connect(lambda value: self.set_opacity(value / 100))
        if parent_process is not None and getattr(parent_process, "watched", lambda: False)():
            self._parent_timer = QTimer(self)
            self._parent_timer.timeout.connect(self._check_parent)
            self._parent_timer.start(2000)

    # ------------------------------------------------------------------ building
    def build(self) -> None:
        """The window's own part, between the header and the foot."""

    def add_button(self, key: str, text: str, tip: str, action, capture: bool = False) -> HeaderButton:
        button = HeaderButton(text, tip, capture, self.header, (1, 2) if key == "hide" else (0, 1))
        button.clicked.connect(action)
        self.header_line.addWidget(button)
        if capture:
            self.header_line.push(button)         # ``#ovcapture { margin-left: auto }``
        self.buttons[key] = button
        return button

    def start(self) -> None:
        for poller in self._pollers:
            poller.start()
        self.host.start()

    def _stored(self, key: str, default: float) -> float:
        if self.store is None:
            return default
        try:
            value = float(self.store.value(key, default))
        except (TypeError, ValueError):
            return default
        return value if 0.2 <= value <= 1 else default

    def _check_parent(self) -> None:
        if not self.parent_process.alive():
            QApplication.quit()

    def closeEvent(self, event):
        self.host.stop()
        for poller in self._pollers:
            poller.stop()
        if self.requests is not None:
            self.requests.stop()
        self._anim_timer.stop()
        forget_pictures()
        super().closeEvent(event)

    # ------------------------------------------------------------------ the settings and the look
    def apply_ui(self, ui: dict) -> None:
        """Take the overlay's settings from the app's answer to ``/api/ui``."""
        if not isinstance(ui, dict):
            return
        first = not self.ui
        self.ui = ui
        look = ui if self.FOLLOWS_LOOK else {}    # a window of its own look reads only its place and click-through
        self.text_look = TextLook(look)
        self.setFixedWidth(self.WIDTH or theme.clamp_int(ui.get("overlay_width"), 260, 800, 340))
        self.card.setMinimumHeight(theme.clamp_int(look.get("overlay_height"), 0, 800, 0))
        mode = look.get("overlay_bg_mode")
        self.card.mode = mode if mode in ("card", "top", "none") else "card"
        self._perf = look.get("performance_mode") is True
        self._want_background(look)
        self.apply_settings(ui)
        self._apply_look()
        self.set_click_through(ui.get("overlay_click_through") is True)
        if first:                                 # where it was last put, if that is still on a monitor
            self.host.restore(ui)
        self.redraw()

    def apply_settings(self, ui: dict) -> None:
        """The window's own settings."""

    def redraw(self) -> None:
        """Draw what the window shows again, then fit the window to it."""
        self._relayout()

    def _px(self) -> int:
        """The overlay's text size: 12 px at its font size (``overlay_font_scale``, 80% to 160%)."""
        return max(8, round(12 * self.text_look.scale))

    def _bare(self) -> bool:
        """Whether the header's words lie over the game (``#ov.ov-bg-none .ovhd``)."""
        return self.card.mode == "none"

    def _apply_look(self) -> None:
        """Hand the look to all that draws words: the header, the window's own part, the foot, and the colour cycle
        and the sheen while either moves."""
        tl = self.text_look
        self._still = self._perf or reduced_motion()
        moving = (tl.cycle or tl.retro) and not self._still
        if moving and not self._anim_timer.isActive():
            self._anim_start = time.monotonic()
            self._anim_timer.start()
        elif not moving:
            self._anim_timer.stop()
        header = tl.colour("header", GOLD)
        title = tl.font("header", self._px(), 700)
        self.title.set_words(self.title.text, title, header, look_as(tl, blend=False),
                             BARE_SHADOW if self._bare() else None)
        for button in self.buttons.values():
            button.look, button.header_colour = tl, header
            button.update()
        bare_foot = self.card.mode != "card"      # ``#ov.ov-bg-none .ovfoot``, ``#ov.ov-bg-top .ovfoot``
        self.foot.line = not bare_foot
        self.foot.update()
        families = ", ".join(f'"{family}"' for family in tl.families())
        sheet = (
            f"QWidget {{ font-family: {families}; }}"
            f"QLabel {{ background: transparent; }}"
            f"QLabel#ovfootlabel {{ color: #7f8aa3; font-size: 10px; font-weight: 400; }}"
            f"QLabel#ovbrand {{ color: rgba(185, 152, 79, 217); font-size: 10px; font-weight: 700;"
            f" letter-spacing: 0.3px; }}"
            f"QLabel#ovmuted {{ color: {LABEL_GREY}; font-size: {self._px()}px; font-weight: 400; }}"
            f"QLabel#ovevents {{ color: {LABEL_GREY}; font-size: 10px; font-weight: 400; }}"
            f"QLabel#ovrtext {{ color: {tl.colour('label', GOLD)}; font-size: 11px; font-weight: 600; }}"
            f"QSlider#ovop::groove:horizontal {{ height: 6px; border: 1px solid #858585; border-radius: 4px;"
            f" background: #3b3b3b; }}"
            f"QSlider#ovop::sub-page:horizontal {{ border: 1px solid {GOLD}; border-radius: 4px; background: {GOLD}; }}"
            f"QSlider#ovop::handle:horizontal {{ width: 14px; height: 14px; margin: -4px 0; border-radius: 7px;"
            f" background: {GOLD}; }}")
        self._base_sheet = sheet
        self.restyle_sheet()
        self.look_settings(tl)
        changed = (vars(tl), self.card.mode) != self._shown_look
        self._shown_look = (dict(vars(tl)), self.card.mode)
        if changed:
            self._sync_effects()
        self._paint_moment(time.monotonic() - self._anim_start if moving else None)

    def look_settings(self, tl: TextLook) -> None:
        """The window's own part in the look."""

    def extra_sheet(self) -> str:
        """The window's own rules, after the card's."""
        return ""

    def restyle_sheet(self) -> None:
        """The window's style sheet, set again only when it changes (the settings come every few seconds)."""
        sheet = self._base_sheet + self.extra_sheet()
        if sheet != self._sheet:
            self._sheet = sheet
            self.setStyleSheet(sheet)

    def text_labels(self) -> list[tuple[QLabel, tuple | None, TextLook]]:
        """The labels that draw words through an effect, each with the shadow it takes where the card leaves it over
        the game and its look: the foot's (its words not blended, the app's name blended), and the window's own."""
        tl, shadow = self.text_look, BARE_SHADOW if self.card.mode != "card" else None
        return [(self.foot.label, shadow, look_as(tl, blend=False)), (self.foot.brand, shadow, tl)]

    def _sync_effects(self) -> None:
        """Each label's effect (``TextEffect``): the outline, glow or halo, the blend, and the shadow over the game;
        none otherwise, since drawn through one a label's words lose their sub-pixel smoothing."""
        for label, shadow, look in self.text_labels():
            wanted = look.painted or shadow is not None
            effect = self._effects.get(label)
            if wanted and effect is None:
                effect = TextEffect(look, label, shadow)
                label.setGraphicsEffect(effect)
                self._effects[label] = effect
            elif wanted:
                effect.set_look(look, shadow)
            elif effect is not None:
                label.setGraphicsEffect(None)    # Qt deletes it
                del self._effects[label]

    def _animate(self) -> None:
        self._paint_moment(time.monotonic() - self._anim_start)

    def _paint_moment(self, seconds: float | None) -> None:
        """The colour cycle and the sheen ``seconds`` in (None: held still): the header turning through the hues,
        unless the sheen's animation takes the cycle's place there (``#ov.ov-retro .ovhd``), and the sheen across the
        header's words and the window's figures."""
        tl = self.text_look
        turning = seconds if tl.cycle and not tl.retro and seconds is not None else None
        sheen = (seconds or 0.0) if tl.retro else None
        header_rect = QRectF(self.header.rect())
        self.dot.seconds = turning
        self.dot.update()
        self.title.seconds, self.title.sheen = turning, sheen
        self.title.update()
        for button in self.buttons.values():
            button.seconds, button.sheen = turning, sheen
            corner = button.mapFrom(self.header, QPoint(0, 0))
            button.sheen_rect = header_rect.translated(corner.x(), corner.y())
            button.update()
        self.paint_moment(sheen)

    def paint_moment(self, sheen: float | None) -> None:
        """The sheen across the window's own figures."""

    # ------------------------------------------------------------------ the background image
    def _want_background(self, ui: dict) -> None:
        """The background image's settings (overlay.js ``applyBackground``): with one set and its opacity above 0 it
        is read from the app once, and again when it could not be read, with the next settings."""
        card = self.card
        card.bg_opacity = theme.clamp_int(ui.get("overlay_bg_opacity"), 0, 100, 100) / 100
        card.bg_zoom = theme.clamp_int(ui.get("overlay_bg_zoom"), 50, 200, 100) / 100
        card.bg_darken = theme.clamp_int(ui.get("overlay_bg_darken"), 0, 100, 20) / 100
        wanted = ui.get("overlay_bg_set") is True and card.bg_opacity > 0
        if not wanted:
            self._bg_image = self._bg_pixmap = None
            self._bg_failed = False
        elif not self._bg_wanted or self._bg_failed:
            self._fetch_background()
        self._bg_wanted = wanted
        self._show_background()

    def _fetch_background(self) -> None:
        if self.requests is None or self._bg_asking:
            return
        self._bg_asking, self._bg_failed = True, False
        self.requests.get_bytes("background", f"/overlay-background?v={int(time.time() * 1000)}")

    def _show_background(self) -> None:
        """The image in the card but in the none mode, and the words' colour for it (``applyAutoContrast``)."""
        tl, card = self.text_look, self.card
        card.background = self._bg_pixmap if self._bg_wanted and card.mode != "none" else None
        tl.contrast, tl.blend = None, False
        if self._bg_wanted and tl.autocontrast == "blend":
            tl.contrast, tl.blend = "#ffffff", True
        elif self._bg_wanted and tl.autocontrast == "luminance":
            if self._bg_image is not None:
                key = (self._bg_image.cacheKey(), card.bg_darken)
                if key != self._contrast_key:
                    self._contrast_key, self._contrast = key, contrast_colour(self._bg_image, card.bg_darken)
                tl.contrast = self._contrast
            elif self._bg_failed:
                tl.contrast = "#f4f1ea"
        card.update()

    def _background_read(self, data) -> None:
        self._bg_asking = False
        image = QImage.fromData(bytes(data)) if isinstance(data, (bytes, bytearray)) and data else QImage()
        if image.isNull():
            self._background_lost()
            return
        if max(image.width(), image.height()) > BACKGROUND_LIMIT:
            image = image.scaled(BACKGROUND_LIMIT, BACKGROUND_LIMIT, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._bg_image, self._bg_pixmap, self._bg_failed = image, QPixmap.fromImage(image), False
        self._restyle()

    def _background_lost(self) -> None:
        self._bg_asking, self._bg_failed = False, True
        self._bg_image = self._bg_pixmap = None
        self._restyle()

    def _restyle(self) -> None:
        self._show_background()
        self._apply_look()
        self.redraw()

    # ------------------------------------------------------------------ the window
    def _relayout(self) -> None:
        """Lay the card out for what it holds, then size the window to it (``fit``), as the meter overlay does."""
        for widget in reversed(self.card.findChildren(QWidget)):
            layout = widget.layout()
            if layout is not None and not widget.isHidden():
                layout.activate()
        self.box.activate()
        self.layout().activate()
        layout = self.layout()
        height = (layout.totalHeightForWidth(self.width()) if layout.hasHeightForWidth()
                  else layout.totalSizeHint().height())
        self.resize(self.width(), max(height, layout.totalMinimumSize().height()))

    def set_opacity(self, value: float) -> None:
        """The card's opacity, 20% to 100% (the slider), kept for the next time it opens."""
        value = max(0.2, min(1.0, float(value)))
        self.card.opacity = value
        self.card.update()
        slider = self.foot.slider
        if slider.value() != round(value * 100):
            slider.blockSignals(True)
            slider.setValue(round(value * 100))
            slider.blockSignals(False)
        if self.store is not None and value != self._kept_opacity:
            self.store.setValue(OPACITY_KEYS[self.VIEW], value)
        self._kept_opacity = value

    def set_click_through(self, on: bool) -> None:
        """Let clicks pass through to the game (the overlay's own setting): by the control on Windows, its buttons
        still pressed (``WindowHost``), else the whole window."""
        if on == self.click_through:
            return
        self.click_through = on
        if self.host.native:
            self.host.set_click_through(on)
            return
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        if visible:
            self.show()

    def toggle_lock(self) -> None:
        """Lock: the window stays where it is and holds what it shows for a screenshot; a second press resumes."""
        self.locked = not self.locked
        button = self.buttons["lock"]
        button.setText("Unlock" if self.locked else "Lock")
        button.setAccessibleName(button.text())
        button.on = self.locked
        button.updateGeometry()
        button.update()
        self.card.locked = self.locked
        self.card.update()
        self.card.setToolTip("Locked for a screenshot: it stays in place and frozen until the camera button unlocks "
                             "it" if self.locked else "")
        self.header_line.invalidate()
        self._relayout()
        if not self.locked:
            self.unlocked()

    def unlocked(self) -> None:
        """Read again what the lock held still."""

    def hide_window(self) -> None:
        """Hide: the app closes this window alone, and keeps it closed until Open overlay or its setting comes back."""
        if self.requests is None:
            self._close_now()
            return
        self.buttons["hide"].setEnabled(False)
        self.requests.post("hide", "/api/overlay", {"action": "hide", "view": self.VIEW})

    def _close_now(self) -> None:
        self.close()
        QApplication.quit()                       # a close of our own: the app does not start it again

    def _commands(self, answer) -> None:
        """The app's command counters (``/api/overlay/commands``): the screenshot hotkey toggles the lock in every
        overlay window, and Open overlay while it is open brings it forward with a fresh reading. The first reading
        is the baseline."""
        if not isinstance(answer, dict):
            return
        for name in ("lock_seq", "reload_seq"):
            try:
                seq = int(answer.get(name) or 0)
            except (TypeError, ValueError):
                continue
            seen = self._seqs.get(name)
            self._seqs[name] = seq if seen is None else max(seen, seq)
            if seen is None or seq <= seen:
                continue
            if name == "reload_seq":
                self.refresh()
            elif self.LOCK_HOTKEY:
                self.toggle_lock()

    def refresh(self) -> None:
        self.show()
        self.raise_()
        if self._bg_wanted:
            self._fetch_background()
        if self._settings_poller is not None:
            self._settings_poller.poll()

    def _replied(self, name: str, answer) -> None:
        if name == "background":
            self._background_read(answer)
        elif name == "hide":
            self._close_now()

    def _failed(self, name: str, why: str) -> None:
        if name == "background":
            self._background_lost()
        elif name == "hide":
            self._close_now()                     # the app is gone or refused: the window closes all the same

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._drag = None if self.locked else self._press - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        offset = event.globalPosition().toPoint() - self._press
        dragging = self._drag is not None
        self._press = self._drag = None
        if math.hypot(offset.x(), offset.y()) > 4 and dragging:
            self.save_position()

    def save_position(self) -> None:
        """Keep the window's place where the web overlay's host keeps it, with the monitors it was put on."""
        if self.api is None or self.ui.get("overlay_remember_position") is False:
            return
        try:
            self.api.post("/api/ui", self.host.saved_place())
        except (OSError, ValueError):
            pass

    def set_hover_state(self, state: str) -> None:
        """Hover to interact as the host has it: the card's edge shows it."""
        self.card.hover = state if state in ("arming", "open") else "off"
        self.card.setToolTip({"arming": "Keep the pointer here to use the overlay",
                              "open": "The overlay takes clicks until the pointer leaves it"}.get(self.card.hover, ""))
        self.card.update()


class PartyWindow(CompanionWindow):
    """The Party-DPS window (overlay.js ``renderParty``)."""

    VIEW = "party"

    def build(self) -> None:
        self.answer: dict = {}
        self.status_text = party_status({})      # ``#ovstatus``, folded away with the metric row as on the web overlay
        self.capture_busy = False
        self.graph_metric = "dps"                 # the meter overlay's, kept with its values (not ``metric``: Qt's)
        self._graph: list[tuple] = []
        self._graph_duration = -1.0
        self._catalog: dict | None = None
        self._catalog_asked = False
        self._announced: set[str] = set()
        self._primed = False
        self.events_clock = lambda: time.time() * 1000
        self.add_button("lock", "Lock", "Freeze the overlay in place for a screenshot", self.toggle_lock)
        self.add_button("split", "New", "Start a new fight — the next combat event begins a fresh encounter (same as "
                                        "Split now in the app)", self.new_fight)
        self.add_button("copy", "Copy", "Copy the current meter as text, to paste in chat or Discord", self.copy)
        self.add_button("hide", "Hide", "Hide overlay", self.hide_window)
        self.add_button("capture", "Start", "Start or stop capturing combat (same as Start/Stop in the app)",
                        self.toggle_capture, capture=True)
        self.events = QLabel("", self.card)       # ``#ovevents``
        self.events.setObjectName("ovevents")
        self.events.setTextFormat(Qt.RichText)
        self.events.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.events.setContentsMargins(0, 2, 0, 5)
        self.events.hide()
        self.box.addWidget(self.events)
        self.content = QWidget(self.card)         # ``#ovcontent``: the figures, or why there are none
        self.content.setAttribute(Qt.WA_TranslucentBackground)
        column = QVBoxLayout(self.content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.stats = [StatRow(self.content) for _ in range(4)]
        for stat in self.stats:
            column.addWidget(stat)
            stat.hide()
        self.muted = QLabel("", self.content)
        self.muted.setObjectName("ovmuted")
        self.muted.setWordWrap(True)
        column.addWidget(self.muted)
        self.box.addWidget(self.content)
        self.card.rows_part = self.content       # the top portion's panel ends where the figures begin
        self.graph = SparkGraph(self.card, 42)   # ``.ovgraph``: 34 px, ``margin: 6px 0 2px``
        self.graph.setContentsMargins(0, 6, 0, 2)
        self.graph.hide()
        self.box.addWidget(self.graph)
        if self.store is not None:                # the metric the meter overlay shows, as the web overlay's ``ovmetric``
            metric = str(self.store.value("metric", "dps") or "dps")
            self.graph_metric = metric if metric in ("dps", "hps", "dtps") else "dps"
        self._meter_poller = None
        if self.api is not None:
            self._meter_poller = Poller(self.api, "/api/meter?view=latest", 500, self)
            self._meter_poller.answered.connect(self._meter_answered)
        self._events_timer = QTimer(self)
        self._events_timer.setInterval(1000)
        self._events_timer.timeout.connect(self.render_events)
        self._events_timer.start()

    def start(self) -> None:
        super().start()
        if self._meter_poller is not None:
            self._meter_poller.start()

    def closeEvent(self, event):
        if self._meter_poller is not None:
            self._meter_poller.stop()
        self._events_timer.stop()
        super().closeEvent(event)

    def apply_settings(self, ui: dict) -> None:
        if ui.get("overlay_dps_graph") is not True:
            self._graph = []
        if ui.get("overlay_show_events") is not False and self._catalog is None and not self._catalog_asked \
                and self.requests is not None:
            self._catalog_asked = True            # the schedule the Timers page reads, once
            self.requests.get("catalog", "/static/event-schedules.json")

    def look_settings(self, tl: TextLook) -> None:
        for stat in self.stats:
            stat.set_stat(stat.label_text, stat.value_text, tl, self._px())

    def text_labels(self):
        tl = self.text_look
        return [*super().text_labels(), (self.muted, None, tl), (self.events, BARE_SHADOW if self._bare() else None, tl)]

    def paint_moment(self, sheen: float | None) -> None:
        for stat in self.stats:
            stat.value.sheen = sheen
            stat.value.update()

    def _meter_answered(self, answer) -> None:
        if not self.locked:                       # locked, it holds what it shows
            self.apply_meter(answer)

    def apply_meter(self, answer) -> None:
        """Draw the meter's reading (the app's answer to ``/api/meter?view=latest``): the party's figures, the graph
        and the capture's button."""
        if not isinstance(answer, dict):
            return
        self.answer = answer
        self._record_graph(answer)
        self.redraw()
        self._sync_capture()
        if self._meter_poller is not None:        # twice a second in a fight, once a second out of one
            running = answer.get("running") is True
            self._meter_poller.set_interval((500 if running else 1000) * (2 if self._perf else 1))

    def redraw(self) -> None:
        tl, px = self.text_look, self._px()
        stats = party_stats(self.answer)
        for stat, figure in zip(self.stats, stats or [None] * 4):
            if figure is None:
                stat.hide()
                continue
            stat.set_stat(figure[0], figure[1], tl, px)
            stat.show()
        self.muted.setText("" if stats else party_waiting(self.answer))
        self.muted.setVisible(not stats)
        self.status_text = party_status(self.answer)
        self._draw_graph()
        self.render_events(relayout=False)
        self._relayout()

    def _record_graph(self, answer: dict) -> None:
        """One reading on the live graph (overlay.js ``recordGraph``): the party's totals while the fight runs."""
        if self.ui.get("overlay_dps_graph") is not True:
            self._graph = []
            return
        snap = answer.get("snapshot") if isinstance(answer.get("snapshot"), dict) else {}
        duration = _num(snap.get("duration"))
        if duration + 0.001 < self._graph_duration:   # the fight clock went back: a new fight began
            self._graph = []
        self._graph_duration = duration
        if answer.get("running") is True and snap.get("paused") is not True and snap.get("battle_over") is not True:
            players = party_players(answer)
            self._graph.append(tuple(sum(_num(p.get(key)) for p in players) for key in ("dps", "hps", "dtps")))
            del self._graph[:-GRAPH_LIMIT]

    def _draw_graph(self) -> None:
        column = {"dps": 0, "hps": 1, "dtps": 2}[self.graph_metric]
        series = [sample[column] for sample in self._graph]
        shown = self.ui.get("overlay_dps_graph") is True and len(series) >= 2
        if shown:
            label = {"hps": "HPS", "dtps": "Taken"}.get(self.graph_metric, "DPS")
            self.graph.set_series(series, f"{label} · now {theme.kfmt(series[-1])} · peak "
                                          f"{theme.kfmt(max(max(series), 1.0))}",
                                  self.text_look.glow_colour)   # ``.ovgline``: the glow's colour, set or not
        self.graph.setVisible(shown)

    def render_events(self, relayout: bool = True) -> None:
        """The strip of the next events (overlay.js ``renderEvents``), as the meter overlay has it, on one line."""
        ui = self.ui
        shown_before = not self.events.isHidden()
        if ui.get("overlay_show_events") is False:
            self._primed = False
            self._announced.clear()
            self.events.hide()
        else:
            snap = self.answer.get("snapshot") if isinstance(self.answer.get("snapshot"), dict) else {}
            region = ui.get("event_region") if isinstance(ui.get("event_region"), str) else ""
            group = ui.get("event_group") if isinstance(ui.get("event_group"), str) else ""
            now, bosses = self.events_clock(), ui.get("overlay_show_field_bosses") is not False
            if not region and not schedule.observed_kills(snap.get("field_bosses"), now, bosses):
                self._primed = False
                self._announced.clear()
                self.events.hide()
            else:
                shown = schedule.strip(self._catalog, region, group, snap.get("field_bosses"), now, bosses)
                keys = {f"{event['id']}:{'active' if event['active'] else 'soon'}" for event in shown}
                if not self._primed:
                    self._announced, self._primed = set(keys), True
                else:
                    fresh = keys - self._announced
                    self._announced = (self._announced & keys) | keys
                    if fresh and ui.get("overlay_events_sound") is True:
                        QApplication.beep()
                if shown:
                    self._show_strip(shown)
                self.events.setVisible(bool(shown))
        if relayout and shown_before != (not self.events.isHidden()):
            self._relayout()

    def _show_strip(self, shown: list[dict]) -> None:
        """The events that fit whole on the line, then "…" (``text-overflow: ellipsis``)."""
        tl = self.text_look
        bold = QFont(self.events.font())
        bold.setPixelSize(10)
        bold.setBold(True)
        room, metrics = max(40, self.width() - self.PADDING[0] - self.PADDING[2]), QFontMetricsF(bold)
        lead = QFontMetricsF(tl.font("label", 10, 600)).horizontalAdvance("Events ")
        count = len(shown)
        while count > 1 and lead + metrics.horizontalAdvance(
                " · ".join(event["text"] for event in shown[:count]) + (" …" if count < len(shown) else "")) > room:
            count -= 1
        label = tl.inline("label", "Events", 10, GOLD, 600)
        self.events.setText(schedule.strip_html(shown[:count], label) + (" …" if count < len(shown) else ""))
        self.events.setToolTip("\n".join(event["tip"] for event in shown))

    def _sync_capture(self) -> None:
        if self.capture_busy:                     # mid-request: the pending label stays
            return
        running, finalizing = self.answer.get("running") is True, self.answer.get("finalizing") is True
        button = self.buttons["capture"]
        words = "Stopping…" if finalizing else "Stop" if running else "Start"
        if button.text() != words:
            button.setText(words)
            button.setAccessibleName(words)
            button.updateGeometry()
            self.header_line.invalidate()
        button.setEnabled(not finalizing)
        button.on = running or finalizing
        button.setToolTip("Stop capturing combat (same as Stop in the app)" if running else
                          "Start capturing combat (same as Start in the app)")
        button.update()

    def unlocked(self) -> None:
        if self._meter_poller is not None:
            self._meter_poller.poll()

    def refresh(self) -> None:
        super().refresh()
        if self._meter_poller is not None:
            self._meter_poller.poll()

    def new_fight(self) -> None:
        """New: a new fight begins with the next combat event (Split now in the app); the graph starts over."""
        if self.requests is None:
            return
        self.buttons["split"].setEnabled(False)
        self.requests.post("split", "/api/meter", {"action": "split"})

    def copy(self) -> None:
        """Copy: the web overlay's party window has no text of its own to copy, so nothing is copied."""

    def toggle_capture(self) -> None:
        """Start or Stop: the capture, as the meter overlay's button. Stop pressed here never closes the overlay."""
        if self.requests is None or self.capture_busy:
            return
        running = self.answer.get("running") is True
        payload = ({"action": "stop", "from_overlay": True} if running else
                   {"action": "start", "source": "a2tools", "auto_port": True, "scope": START_SCOPE})
        self.capture_busy = True
        button = self.buttons["capture"]
        button.setEnabled(False)
        self._say(button, "Stopping…" if running else "Starting…")
        self.requests.post("capture", "/api/meter", payload)

    def _say(self, button: HeaderButton, words: str) -> None:
        button.setText(words)
        button.setAccessibleName(words)
        button.updateGeometry()
        self.header_line.invalidate()
        self._relayout()

    def _replied(self, name: str, answer) -> None:
        if name == "catalog":
            if isinstance(answer, dict) and answer.get("version") == 1:
                self._catalog = answer
                self.render_events()
            return
        if name == "capture":
            self._capture_done()
        elif name == "split":
            self._graph = []                      # the graph starts clean for the new fight
            self._say(self.buttons["split"], "New ✓")
            QTimer.singleShot(1200, self, self._split_back)
            if self._meter_poller is not None:
                self._meter_poller.poll()
        else:
            super()._replied(name, answer)

    def _failed(self, name: str, why: str) -> None:
        if name == "catalog":
            self._catalog_asked = False           # asked again with the next settings
            return
        if name == "capture":
            button = self.buttons["capture"]
            button.setToolTip(why[:256])
            self._say(button, "Error")
            QTimer.singleShot(1400, self, self._capture_done)
        elif name == "split":
            self._say(self.buttons["split"], "Error")
            QTimer.singleShot(1200, self, self._split_back)
        else:
            super()._failed(name, why)

    def _capture_done(self) -> None:
        self.capture_busy = False
        self.buttons["capture"].setEnabled(True)
        if self._meter_poller is not None:
            self._meter_poller.poll()
        self._sync_capture()
        self._relayout()

    def _split_back(self) -> None:
        button = self.buttons["split"]
        button.setEnabled(True)
        self._say(button, "New")


class RadarWindow(CompanionWindow):
    """The Hidden Cube radar's window (overlay.js ``setupRadar``, ``renderRadar``): its title, Lock and Hide, the
    circle and its line, nothing of the meter; narrow, never resized, the window fitting it."""

    VIEW = "radar"
    WIDTH = RADAR_WIDTH
    PADDING = (10, 8, 10, 7)                      # ``#ov.ov-radar .ovcard { padding: 7px 9px 6px }``
    HEADER_GAP = 4
    FOOT_TOP = 5

    def build(self) -> None:
        self.reading: dict | None = None
        self.busy = False
        self.title.set_words("Hidden Cube radar", self.title.font_, GOLD, self.text_look)
        self.title.show()
        self.add_button("lock", "Lock", "Freeze the overlay in place for a screenshot", self.toggle_lock)
        self.add_button("hide", "Hide", "Hide overlay", self.hide_window)
        self.radar = QWidget(self.card)           # ``#ovradar``: the circle and its line, 8 px apart
        self.radar.setAttribute(Qt.WA_TranslucentBackground)
        self.radar.setToolTip(RADAR_TIP)
        self.radar.setAccessibleName("Hidden Cube radar")
        line = QHBoxLayout(self.radar)
        line.setContentsMargins(0, 2, 0, 2)
        line.setSpacing(8)
        self.dial = RadarDial(self.radar)
        self.words = QLabel("", self.radar)       # ``.ovrtext``
        self.words.setObjectName("ovrtext")
        self.words.setWordWrap(True)
        self.words.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        line.addWidget(self.dial, 0, Qt.AlignVCenter)
        line.addWidget(self.words, 1, Qt.AlignVCenter)
        self.radar.hide()
        self.box.addWidget(self.radar)
        # With the top portion only behind it, the web overlay's radar window has no panel: what it measures the
        # portion to (``#ovcontent``) is not shown there. A part that is never laid out ends it at the top.
        self.card.rows_part = QWidget(self.card)
        self.card.rows_part.hide()
        self._radar_timer = QTimer(self)
        self._radar_timer.setInterval(RADAR_MS)
        self._radar_timer.timeout.connect(self.poll_radar)

    def apply_settings(self, ui: dict) -> None:
        """The radar runs while its setting is on (``setupRadar``): its poll then, and nothing shown without it."""
        on = ui.get("radar_enabled") is True
        if on and not self._radar_timer.isActive():
            self._radar_timer.start()
            self.poll_radar()
        elif not on:
            self._radar_timer.stop()
        if not on:
            self.reading = None

    def look_settings(self, tl: TextLook) -> None:
        self.title.set_words("Hidden Cube radar", tl.font("header", self._px(), 700), tl.colour("header", GOLD),
                             look_as(tl, blend=False), BARE_SHADOW if self._bare() else None)

    def text_labels(self):
        return [*super().text_labels(), (self.words, None, look_as(self.text_look, blend=False))]

    def closeEvent(self, event):
        self._radar_timer.stop()
        super().closeEvent(event)

    def poll_radar(self) -> None:
        if self.busy or self.locked or self.requests is None:
            return
        self.busy = True
        self.requests.get("radar", "/api/radar")

    def unlocked(self) -> None:
        self.poll_radar()

    def show_radar(self, r) -> None:
        """A reading of the radar (``renderRadar``): the blips moved, and the line and the window's height only where
        they change, as it comes three times a second."""
        self.reading = r if isinstance(r, dict) else None
        if self._show():
            self._relayout()

    def redraw(self) -> None:
        self._show()
        self._relayout()

    def _show(self) -> bool:
        """Show the reading while the radar runs; whether its line or the radar's showing changed."""
        shown, changed = self.ui.get("radar_enabled") is True and self.reading is not None, False
        if shown:
            self.dial.set_reading(self.reading)
            text = radar_text(self.reading)
            if self.words.text() != text:
                self.words.setText(text)
                changed = True
        if shown == self.radar.isHidden():
            self.radar.setVisible(shown)
            changed = True
        return changed

    def _replied(self, name: str, answer) -> None:
        if name == "radar":
            self.busy = False
            self.show_radar(answer)
        else:
            super()._replied(name, answer)

    def _failed(self, name: str, why: str) -> None:
        if name == "radar":
            self.busy = False                     # best effort: the next poll asks again
        else:
            super()._failed(name, why)


VIEWS = ("party", "radar", "pets", "players")


def window_class(view: str):
    """The window class of a companion's view: the Pet Tracker window's (0.2.498) and the player cards window's
    (0.2.499) in modules of their own."""
    if view == "pets":
        from .pets_window import PetsWindow
        return PetsWindow
    if view == "players":
        from .players_window import PlayersOverlay
        return PlayersOverlay
    return {"party": PartyWindow, "radar": RadarWindow}.get(view)


def view_of(url: str) -> str:
    """The window an overlay address names (``?view=party``, ``?view=radar``, ``?view=pets``, ``?view=players``), else
    ``meter``."""
    for view in VIEWS:
        if f"view={view}" in url:
            return view
    return "meter"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aion2calc.gui.companions",
                                     description="Aion 2 Calc native companion overlay window")
    parser.add_argument("--url", default=None, help="the app's overlay address with its view (?view=party, ?view=radar)")
    args = parser.parse_args(argv)
    from ..overlay import _ParentProcess, _default_url, native_overlay
    url = args.url or _default_url()
    view = view_of(url)
    if view not in VIEWS:
        from .overlay import main as meter
        return meter(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    from .app_icon import apply as apply_icon
    apply_icon(app)                               # the app's icon, not Qt's placeholder (0.2.501)
    from . import interface
    base = _app_base(url.split("?")[0])
    interface.connect(AppApi(base))
    window = window_class(view)(AppApi(base), _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")), overlay_store(),
                                native_overlay())
    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
