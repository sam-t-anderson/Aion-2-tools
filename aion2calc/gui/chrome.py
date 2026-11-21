"""The native overlay's chrome (0.2.422): what the web overlay's compact layout (overlay.css ``#ov.ov-nm``) puts round
the target card and the player rows. Under the rows, the fight's clock, your contribution, the identity line and the
events strip, each a chip of its own; on a line under them the ping, the overlay's frame rate and the toolbar, the
metric chip at its head and an icon for each of its buttons, their words in the tooltips.

A chip floats with nothing behind it of its own (``--nm-float``), its text over a shadow (``--nm-shadow``) that the
glow and the halo replace. The web overlay's Windows window could not leave text floating with nothing behind it, so
there each chip sits on a dark ground of its own; the native window can, and its chips float as the web overlay's
do everywhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from PySide6.QtCore import QByteArray, QEvent, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLayout, QSizePolicy, QToolTip, QWidget

from .look import CHIP_SHADOW, TextLook, _blurred, _tinted, cycled, draw_text

TEAL = "#63d3e6"                          # ``--nm-teal``
TEAL_HOVER = "#9be7f3"
GREEN, RED = "#6fe3a3", "#ff8585"         # how a press went (``data-state``), the lock on, the capture's start or stop
HEADER = "#c9d1db"                        # the toolbar's colour (``--ov-header-color``'s default in the compact layout)
HOVER_GROUND = QColor(255, 255, 255, 23)  # ``rgba(255, 255, 255, .09)`` under the pointer
#: The clock's time: ``ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace``.
MONOSPACE = ["Cascadia Mono", "Consolas", "Menlo", "SF Mono", "DejaVu Sans Mono", "Liberation Mono", "monospace"]


def _svg(body: str, width: str = "2", join: bool = True, cap: bool = True, filled: bool = False,
         box: str = "0 0 24 24") -> str:
    paint = ("fill='#fff'" if filled else
             f"fill='none' stroke='#fff' stroke-width='{width}'" + (" stroke-linecap='round'" if cap else "")
             + (" stroke-linejoin='round'" if join else ""))
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{box}' {paint}>{body}</svg>"


#: The toolbar's and the ping's icons (overlay.css ``--nm-ic-*``), drawn white and tinted.
ICONS = {
    "camera": _svg("<path d='M3 8.5A1.5 1.5 0 0 1 4.5 7H7l1.5-2h7L17 7h2.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 "
                   "1.5h-15A1.5 1.5 0 0 1 3 17.5z'/><circle cx='12' cy='12.5' r='3.5'/>"),
    "new": _svg("<path d='M20 12a8 8 0 1 1-2.34-5.66'/><path d='M20 4v5h-5'/>"),
    "copy": _svg("<rect x='6' y='3' width='13' height='18' rx='2'/>"
                 "<path d='M4 7h3M4 12h3M4 17h3M10 8h6M10 12h6M10 16h4'/>"),
    "options": _svg("<path d='M4 8h9M17 8h3M4 16h3M11 16h9'/><circle cx='15' cy='8' r='2'/>"
                    "<circle cx='9' cy='16' r='2'/>"),
    "play": _svg("<path d='M8 5.5v13l10.5-6.5z'/>", filled=True),
    "stop": _svg("<rect x='6.5' y='6.5' width='11' height='11' rx='2'/>", filled=True),
    "close": _svg("<path d='M6 6l12 12M18 6L6 18'/>", width="2.2", join=False),
    "plan": _svg("<path d='M9 4L3.5 6v14L9 18l6 2 5.5-2V4L15 6z'/><path d='M9 4v14M15 6v14'/>", cap=False),
    # The counters' (overlay.css ``.ovkeyicon``, ``.ovticketicon``, ``.ovrunicon``), filled.
    "key": _svg("<path d='M14.5 2a7.5 7.5 0 0 0-7.1 9.9L2 17.3V22h4.7l1.3-1.3v-2h2v-2h2l1.4-1.4A7.5 7.5 0 1 0 14.5 2zm2.5 "
                "7a2 2 0 1 1 0-4 2 2 0 0 1 0 4z'/>", filled=True),
    "ticket": _svg("<path d='M22 10V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v4a2 2 0 0 1 0 4v4a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-4a2 "
                   "2 0 0 1 0-4zm-9 7.5h-2v-2h2v2zm0-4.5h-2v-2h2v2zm0-4.5h-2v-2h2v2z'/>", filled=True),
    "runs": _svg("<path d='M7 2v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2H7zM5 "
                 "9h14v11H5V9zm2 2v2h2v-2H7zm4 0v2h2v-2h-2zm4 0v2h2v-2h-2z'/>", filled=True),
    "meter": _svg("<path d='M6 20v-7M12 20V5M18 20v-10'/>", width="2.6", join=False),
    "signal": _svg("<rect x='0' y='11' width='3.5' height='5' rx='1'/><rect x='5.5' y='7.5' width='3.5' "
                   "height='8.5' rx='1'/><rect x='11' y='4' width='3.5' height='12' rx='1'/><rect x='16.5' y='0' "
                   "width='3.5' height='16' rx='1'/>", filled=True, box="0 0 20 16"),
}
_ICONS: dict = {}                         # each icon as drawn, by its size and colour


def forget_icons() -> None:
    """Let the drawn icons go (the overlay closing), so none outlives Qt's application."""
    _ICONS.clear()


def icon(name: str, width: float, height: float, colour, ratio: float = 1.0) -> QPixmap:
    """``name``'s icon in a ``width`` × ``height`` box, as large as fits and centred (``mask: center / contain``), in
    ``colour``, for a screen of ``ratio`` device pixels to the pixel."""
    colour = QColor(colour)
    key = (name, round(width * ratio), round(height * ratio), ratio, colour.rgba())
    picture = _ICONS.get(key)
    if picture is None:
        renderer = QSvgRenderer(QByteArray(ICONS[name].encode()))
        picture = QPixmap(max(1, key[1]), max(1, key[2]))
        picture.fill(Qt.transparent)
        painter = QPainter(picture)
        painter.setRenderHint(QPainter.Antialiasing)
        box = renderer.viewBoxF()
        scale = min(picture.width() / box.width(), picture.height() / box.height())
        drawn = QSizeF(box.width() * scale, box.height() * scale)
        renderer.render(painter, QRectF((picture.width() - drawn.width()) / 2,
                                        (picture.height() - drawn.height()) / 2, drawn.width(), drawn.height()))
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(picture.rect(), colour)
        painter.end()
        picture.setDevicePixelRatio(ratio)
        if len(_ICONS) > 256:
            _ICONS.clear()
        _ICONS[key] = picture
    return picture


SHADOW_PAD = 6                            # the room the chips' shadow takes round an icon


def icon_shadow(name: str, width: float, height: float, ratio: float = 1.0) -> QPixmap:
    """The shadow under a toolbar icon: the chips' (``--nm-shadow``), its layers dropped and blurred from the icon's
    shape, with ``SHADOW_PAD`` of room round it. The web overlay draws its icons as masks, which take no text shadow;
    there its Windows window sets the toolbar on a dark chip of its own, and a floating icon with no shadow at all
    would vanish over a bright game."""
    key = ("shadow", name, round(width * ratio), round(height * ratio), ratio)
    picture = _ICONS.get(key)
    if picture is None:
        shape = QPixmap(math.ceil((width + 2 * SHADOW_PAD) * ratio), math.ceil((height + 2 * SHADOW_PAD) * ratio))
        shape.setDevicePixelRatio(ratio)
        shape.fill(Qt.transparent)
        painter = QPainter(shape)
        painter.drawPixmap(QPointF(SHADOW_PAD, SHADOW_PAD), icon(name, width, height, "#ffffff", ratio))
        painter.end()
        picture = QPixmap(shape.size())
        picture.setDevicePixelRatio(ratio)
        picture.fill(Qt.transparent)
        painter = QPainter(picture)
        for colour, dy, blur in CHIP_SHADOW:
            painter.drawPixmap(QPointF(0, dy), _tinted(_blurred(shape, blur), colour))
        painter.end()
        _ICONS[key] = picture
    return picture


def font(families: list[str], px: float, weight: int, spacing: float = 0.0) -> QFont:
    """A font at ``px`` pixels (a fraction by its points, at the 96 dpi Qt gives every screen), ``weight`` and
    ``spacing`` px between its letters."""
    made = QFont()
    made.setFamilies(families)
    if float(px).is_integer():
        made.setPixelSize(max(1, int(px)))
    else:
        made.setPointSizeF(px * 0.75)
    made.setWeight(QFont.Weight(max(100, min(900, int(weight)))))
    if spacing:
        made.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    if families and families[0] in MONOSPACE:
        made.setStyleHint(QFont.TypeWriter)
    return made


@dataclass
class Part:
    """A part of a chip: its runs of text side by side (each its words, font and colour), on a line ``line`` px high
    (CSS ``line-height``), or a mark drawn for it (``mark(painter, rect)``, ``size`` px), or both, the mark ``space``
    px before the words (a counter's icon); ``tip`` its own tooltip."""
    runs: list = field(default_factory=list)
    line: float = 0.0
    mark: object = None
    size: QSizeF | None = None
    tip: str = ""
    space: float = 5.0

    def words(self) -> float:
        return sum(QFontMetricsF(run[1]).horizontalAdvance(run[0]) for run in self.runs)

    def measure(self) -> QSizeF:
        if self.mark is not None and not self.runs:
            return QSizeF(self.size)
        if self.mark is not None:
            return QSizeF(self.size.width() + self.space + self.words(), max(self.size.height(), self.line))
        return QSizeF(self.words(), self.line)

    def key(self) -> tuple:
        mark = None if self.mark is None else (getattr(self.mark, "key", id(self.mark)), self.size.width(),
                                               self.size.height())
        return (tuple((text, made.key(), QColor(colour).rgba()) for text, made, colour in self.runs), self.line,
                mark, self.tip)


class Chip(QWidget):
    """A chip of the compact layout: its parts side by side ``gap`` apart, upright in the middle of their line
    (``align-items: center``), on to another line where it is narrower than they are (``flex-wrap: wrap``); its text
    drawn with the chips' shadow and the look's effects. ``padding`` is left, top, right, bottom."""

    def __init__(self, parent=None, padding=(8, 3, 8, 3), gap=(4.0, 2.0)):
        super().__init__(parent)
        self.parts: list[Part] = []
        self.look = TextLook({})
        self.shadow = CHIP_SHADOW                 # under its words: the chips' (None: none, as the top parts' on a card)
        self.padding, self.gap = padding, gap
        self._key = None
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_parts(self, parts: list[Part], look: TextLook) -> None:
        key = (tuple(part.key() for part in parts), repr(sorted(vars(look).items())))
        if key == self._key:
            return
        self._key, self.parts, self.look = key, parts, look
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        """The chip's words, its parts apart (for its tests and its accessible name)."""
        return " ".join("".join(run[0] for run in part.runs) for part in self.parts if part.runs)

    def _lines(self, width: float) -> list[tuple[list[tuple[Part, QSizeF]], float, float]]:
        """The parts in lines within ``width``: each line's parts with their sizes, its width and its height."""
        lines, line, used = [], [], 0.0
        for part in self.parts:
            size = part.measure()
            if line and used + self.gap[0] + size.width() > width + 0.5:
                lines.append((line, used, max(s.height() for _p, s in line)))
                line, used = [], 0.0
            used += (self.gap[0] if line else 0.0) + size.width()
            line.append((part, size))
        if line:
            lines.append((line, used, max(s.height() for _p, s in line)))
        return lines

    def _extent(self, lines) -> QSizeF:
        left, top, right, bottom = self.padding
        width = max((used for _line, used, _tall in lines), default=0.0)
        height = sum(tall for _line, _used, tall in lines) + self.gap[1] * max(0, len(lines) - 1)
        return QSizeF(width + left + right, height + top + bottom)

    def sizeHint(self):
        if not self.parts:                        # nothing yet: a pixel, there to be drawn (the frame rate's count)
            return QSize(1, 1)
        extent = self._extent(self._lines(float("inf")))
        return QSize(int(extent.width() + 0.999), int(extent.height() + 0.999))

    def minimumSizeHint(self):
        if not self.parts:
            return QSize(1, 1)
        left, top, right, bottom = self.padding
        widest = max((part.measure().width() for part in self.parts), default=0.0)
        return QSize(int(widest + left + right + 0.999), self.sizeHint().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        if not self.parts:
            return 1
        left, _top, right, _bottom = self.padding
        return int(self._extent(self._lines(width - left - right)).height() + 0.999)

    def _places(self):
        """Each part's place, as the chip is now."""
        left, top, right, _bottom = self.padding
        y = float(top)
        for line, _used, tall in self._lines(self.width() - left - right):
            x = float(left)
            for part, size in line:
                yield part, QRectF(x, y + (tall - size.height()) / 2, size.width(), size.height())
                x += size.width() + self.gap[0]
            y += tall + self.gap[1]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        for part, rect in self._places():
            x = rect.left()
            if part.mark is not None:
                size = part.size
                part.mark(painter, QRectF(x, rect.center().y() - size.height() / 2, size.width(), size.height()))
                if not part.runs:
                    continue
                x += size.width() + part.space
            for text, made, colour in part.runs:
                x += draw_text(painter, QRectF(x, rect.top(), max(1.0, rect.right() - x + 1), rect.height()), text,
                               made, QColor(colour), Qt.AlignLeft, self.look, shadow=self.shadow)

    def event(self, event):
        if event.type() == QEvent.ToolTip:        # a part's own tooltip (a note's), else the chip's
            point = QPointF(event.pos())
            tip = next((part.tip for part, rect in self._places() if part.tip and rect.contains(point)),
                       self.toolTip())
            if tip:
                QToolTip.showText(event.globalPos(), tip, self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)


GLOW_PAD = 9                              # the room the clock mark's glow takes round it


def _glow(size: QSizeF, ratio: float) -> QPixmap:
    """The clock mark's glow (``box-shadow: 0 0 6px rgba(94, 224, 74, .55)``): its shape blurred as a text shadow is,
    with room round it."""
    key = ("glow", size.width(), size.height(), ratio)
    picture = _ICONS.get(key)
    if picture is None:
        shape = QPixmap(math.ceil((size.width() + 2 * GLOW_PAD) * ratio),
                        math.ceil((size.height() + 2 * GLOW_PAD) * ratio))
        shape.setDevicePixelRatio(ratio)
        shape.fill(Qt.transparent)
        painter = QPainter(shape)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(94, 224, 74, 140))
        painter.drawRoundedRect(QRectF(GLOW_PAD, GLOW_PAD, size.width(), size.height()), 2, 2)
        painter.end()
        picture = _blurred(shape, 6)
        _ICONS[key] = picture
    return picture


def clock_mark(colour: str, glow: bool):
    """The clock's mark (``.ovclkbar``): 3 × 15 px, its corners 2 px, glowing while the fight runs."""
    def draw(painter: QPainter, rect: QRectF) -> None:
        if glow:
            painter.drawPixmap(rect.topLeft() - QPointF(GLOW_PAD, GLOW_PAD),
                               _glow(rect.size(), painter.device().devicePixelRatioF()))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colour))
        painter.drawRoundedRect(rect, 2, 2)
        painter.restore()
    draw.key = ("clock", colour, glow)
    return draw


def icon_mark(name: str, colour: str):
    """An icon drawn as a chip's part (the ping's signal, a counter's)."""
    def draw(painter: QPainter, rect: QRectF) -> None:
        ratio = painter.device().devicePixelRatioF()
        painter.drawPixmap(rect.topLeft(), icon(name, rect.width(), rect.height(), colour, ratio))
    draw.key = ("icon", name, colour)
    return draw


def picture_mark(picture: QPixmap):
    """A picture drawn as a chip's part, as large as fits and centred (``background: center / contain``)."""
    def draw(painter: QPainter, rect: QRectF) -> None:
        if picture.isNull():
            return
        scale = min(rect.width() / picture.width(), rect.height() / picture.height())
        width, height = picture.width() * scale, picture.height() * scale
        painter.drawPixmap(QRectF(rect.center().x() - width / 2, rect.center().y() - height / 2, width, height),
                           picture, QRectF(picture.rect()))
    draw.key = ("picture", picture.cacheKey())
    return draw


class FpsChip(Chip):
    """The overlay's own frame rate (``overlay_show_fps``, ``#ovfps``): while it runs it asks for a frame at each
    turn of the screen's refresh, as the web overlay's frame loop does, and counts the frames drawn each second. Until
    the first second is counted it shows nothing, a pixel the frames are drawn into (the web overlay's empty readout
    is hidden)."""

    def __init__(self, parent=None):
        super().__init__(parent, padding=(8, 3, 8, 3), gap=(3.0, 2.0))
        self.rate: int | None = None
        self.frames = 0
        self.since = time.monotonic()
        self.clock = time.monotonic
        self._frame = QTimer(self)
        self._frame.timeout.connect(self.update)
        self._second = QTimer(self)
        self._second.setInterval(1000)
        self._second.timeout.connect(self.count)
        self.on_count = None                       # the overlay's: the readout changed

    def running(self) -> bool:
        return self._second.isActive()

    def run(self, on: bool) -> None:
        if on and not self._second.isActive():
            screen = self.screen()
            hertz = screen.refreshRate() if screen is not None else 60.0
            self._frame.start(max(4, round(1000 / max(30.0, min(240.0, hertz or 60.0)))))
            self.frames, self.since, self.rate = 0, self.clock(), None
            self._second.start()
        elif not on:
            self._frame.stop()
            self._second.stop()
            self.rate = None

    def count(self) -> None:
        now = self.clock()
        if now - self.since >= 1.0:
            self.rate = round(self.frames / (now - self.since))
            self.frames, self.since = 0, now
            if self.on_count is not None:
                self.on_count()

    def paintEvent(self, event):
        self.frames += 1
        super().paintEvent(event)


class IconButton(QAbstractButton):
    """A toolbar button of the compact layout (``#ov.ov-nm .ovhd button``): its icon, 16 px in a 26 × 24 button, both
    at the text's size (``scale``), in the toolbar's colour; under the pointer white on a faint ground. Its colour
    says how a press went (``state``: "ok" green, "err" red) or what it is (``tone``: the lock while on, the options
    while open, the capture's start or stop), and it turns with the colour cycle (``seconds``). Its words are its
    accessible name; its tooltip says what it does."""

    def __init__(self, name: str, text: str, tip: str, parent=None):
        super().__init__(parent)
        self.icon_name = name
        self.state = ""
        self.tone: str | None = None
        self.colour = HEADER
        self.scale = 1.0
        self.seconds: float | None = None
        self.setText(text)
        self.setAccessibleName(text)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)           # the overlay never takes the keyboard from the game
        self.setAttribute(Qt.WA_Hover)

    def sizeHint(self):
        return QSize(round(26 * self.scale), round(24 * self.scale))

    def minimumSizeHint(self):
        return self.sizeHint()

    def shown_colour(self) -> QColor:
        """Its colour as drawn now: its tone over how a press went over the pointer over the toolbar's colour
        (the web overlay's rules in their order of precedence), turned by the colour cycle."""
        hovered = self.isEnabled() and self.underMouse()
        colour = QColor(self.tone or {"ok": GREEN, "err": RED}.get(self.state) or ("#ffffff" if hovered else
                                                                                     self.colour))
        return cycled(colour, self.seconds) if self.seconds is not None else colour

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.55)
        if self.isEnabled() and self.underMouse():
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, HOVER_GROUND)
        side = 16 * self.scale
        box = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        ratio = self.devicePixelRatioF()
        painter.drawPixmap(box.topLeft() - QPointF(SHADOW_PAD, SHADOW_PAD),
                           icon_shadow(self.icon_name, side, side, ratio))
        painter.drawPixmap(box.topLeft(), icon(self.icon_name, side, side, self.shown_colour(), ratio))


class MetricChip(QAbstractButton):
    """The metric chip at the toolbar's head (``#ovmetrics button.on``): the metric shown, teal at 800 with the chips'
    shadow, 24 px high at the text's size; a click moves on to the next metric."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.look = TextLook({})
        self.scale = 1.0
        self.families: list[str] = []
        self.seconds: float | None = None
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)

    def set_look(self, look: TextLook, scale: float, families: list[str]) -> None:
        self.look, self.scale, self.families = look, scale, families
        self.updateGeometry()
        self.update()

    def label_font(self) -> QFont:
        return font(self.families, 12 * self.scale, 800, 0.3)

    def sizeHint(self):
        width = QFontMetricsF(self.label_font()).horizontalAdvance(self.text())
        return QSize(int(width + 14 + 0.999), round(24 * self.scale))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        hovered = self.underMouse()
        if hovered:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, HOVER_GROUND)
        colour = QColor(TEAL_HOVER if hovered else TEAL)
        shift = None
        if self.seconds is not None:
            colour = cycled(colour, self.seconds)
            seconds = self.seconds
            shift = lambda shade: cycled(shade, seconds)   # noqa: E731 - the effects turn with the toolbar
        draw_text(painter, QRectF(7, 0, max(1.0, self.width() - 14), self.height()), self.text(), self.label_font(),
                  colour, Qt.AlignLeft, self.look, shift=shift, shadow=CHIP_SHADOW)


class FlowLayout(QLayout):
    """Widgets side by side, on to another line where there is no room (``flex-wrap: wrap``). ``align`` is where a
    line's widgets sit (the toolbar's to the right, ``justify-content: flex-end``; the chips to the left; a card's
    chips in its middle, ``text-align: center``), ``gap`` the
    room between them across and down, ``lead`` the room above the first line (the first line's ``margin-top``;
    nothing when no widget is shown), ``centre`` whether a line's widgets sit in its middle (``align-items:
    center``) or at its top (``flex-start``). A widget wider than a line takes the line (``max-width: 100%``) at its
    height for that width; a widget ``push``ed takes the room its line has to spare before it (``margin-left:
    auto``)."""

    def __init__(self, parent=None, align=Qt.AlignRight, gap=(0, 0), lead: int = 0, centre: bool = True):
        super().__init__(parent)
        self._items: list = []
        self.align, self.gap, self.lead, self.centre = align, gap, lead, centre
        self._pushed: set[int] = set()
        self.setContentsMargins(0, 0, 0, 0)

    def push(self, widget: QWidget) -> None:
        self._pushed.add(id(widget))

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self):
        margins = self.contentsMargins()
        shown = [item.sizeHint() for item in self._items if not item.isEmpty()]
        if not shown:
            return QSize(0, 0)
        width = sum(hint.width() for hint in shown) + self.gap[0] * (len(shown) - 1)
        height = max(hint.height() for hint in shown) + self.lead
        return QSize(width + margins.left() + margins.right(), height + margins.top() + margins.bottom())

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        if size.isEmpty():
            return QSize(0, 0)
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom() + self.lead)

    def _arrange(self, rect: QRect, place: bool) -> int:
        """Lay the items out in lines within ``rect`` (when ``place``) and answer the height they take."""
        margins = self.contentsMargins()
        across, down = self.gap
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        lines, line, used = [], [], 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if hint.width() > area.width():       # wider than a line: the line's width, and its height for it
                width = max(1, area.width())
                height = item.heightForWidth(width) if item.hasHeightForWidth() else hint.height()
                hint = QSize(width, max(height, item.minimumSize().height()))
            if line and used + across + hint.width() > area.width():
                lines.append((line, used))
                line, used = [], 0
            used += (across if line else 0) + hint.width()
            line.append((item, hint))
        if line:
            lines.append((line, used))
        if not lines:
            return 0
        y = area.y() + self.lead
        for line, used in lines:
            tall = max(hint.height() for _item, hint in line)
            spare = max(0, area.width() - used)
            pushed = any(id(item.widget()) in self._pushed for item, _hint in line if item.widget() is not None)
            x = area.x() + (spare if self.align & Qt.AlignRight and not pushed else
                            spare // 2 if self.align & Qt.AlignHCenter and not pushed else 0)
            for item, hint in line:
                if pushed and item.widget() is not None and id(item.widget()) in self._pushed:
                    x += spare
                if place:
                    top = y + ((tall - hint.height()) // 2 if self.centre else 0)
                    item.setGeometry(QRect(QPoint(x, top), hint))
                x += hint.width() + across
            y += tall + down
        return y - down - rect.y() + margins.bottom()
