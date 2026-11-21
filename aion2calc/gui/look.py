"""The native overlay's look (0.2.420): its fonts, its text colours and effects, and its background image, from the
settings the web overlay reads (overlay.js ``syncColors``, overlay.css).

Each text element the web overlay styles on its own has a key: ``rate`` and ``total`` (a row's rate and its share),
``name``, ``header`` (the status line, the metric buttons and the toolbar), ``target``, ``hp``, ``ttk``, ``label``
(the "Dummy parse" and "Events" labels), ``also`` (the others struck), ``ping`` (the ping and the counter lines) and
``identity``. A colour (``overlay_text_colors``) or font (``overlay_text_fonts``: family, size 80–160%, weight
400–800) set for a key replaces the native overlay's own for that element; one left blank keeps it.
``overlay_font_family`` is every element's family unless its own says otherwise.

The effects are the web overlay's: an outline (``-webkit-text-stroke``), a glow and a halo (``text-shadow``; the
compact layout shows the halo alone when both are on), the header and the names turning through the hues in 12 s
(``filter: hue-rotate``) and a sheen sweeping across the names (``ov-retro-sheen``). Auto-contrast, with a
background image, paints the text one colour by the image's relative luminance (WCAG) less its darkening, or
("blend") paints it white and inverts it against what lies behind each glyph (``mix-blend-mode: difference``).
"""
from __future__ import annotations

from collections import OrderedDict
import math
import re
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsEffect

from . import theme

TEXT_KEYS = ("rate", "total", "name", "header", "target", "hp", "ttk", "label", "also", "ping", "identity")
CYCLE_S = 12.0                            # overlay.css ``ovhue``: a whole turn of the hues
SHEEN_S = 3.5                             # ``ov-retro-sheen``
ANIMATION_MS = 50                         # how often the cycle and the sheen move on
HALO_BLURS = (12, 6, 2)                   # ``text-shadow: 0 0 2px, 0 0 6px, 0 0 12px``
GLOW_BLURS = (8, 4)                       # ``0 0 4px, 0 0 8px``
#: The outline: a ring a pixel round the glyphs, at the strength of the web overlay's 0.6 px stroke (measured
#: against Chromium's drawing of the same text: a whole pixel at full strength put four times its colour round it).
OUTLINE_OPACITY = 0.25
_RING = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1))
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_UNSAFE = re.compile(r"[\"'\\;:{}<>]")         # what would end a family's quotes in a style sheet or rich text


def family_name(value) -> str:
    """A font family as typed in the settings, without what would break the style sheet or the rich text it is
    written into ("" for none)."""
    return _UNSAFE.sub("", value).strip() if isinstance(value, str) else ""


def hex_colour(value) -> str | None:
    """A ``#rrggbb`` colour, or None for anything else (a blank setting keeps the element's own colour)."""
    return value if isinstance(value, str) and _HEX.fullmatch(value) else None


def _within(value, low: float, high: float) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if low <= value <= high else None


class TextLook:
    """The overlay's text look from its settings. The overlay sets ``contrast``, the one colour every text then
    takes, and ``blend`` from its background image."""

    def __init__(self, ui: dict):
        colours = ui.get("overlay_text_colors") if isinstance(ui.get("overlay_text_colors"), dict) else {}
        fonts = ui.get("overlay_text_fonts") if isinstance(ui.get("overlay_text_fonts"), dict) else {}
        self.colours = {key: colour for key in TEXT_KEYS if (colour := hex_colour(colours.get(key)))}
        self.fonts: dict[str, tuple] = {}
        for key in TEXT_KEYS:
            entry = fonts.get(key) if isinstance(fonts.get(key), dict) else {}
            family = family_name(entry.get("family"))
            scale, weight = _within(entry.get("scale"), 80, 160), _within(entry.get("weight"), 400, 800)
            if family or scale or weight:
                self.fonts[key] = (family or None, scale / 100 if scale else None, int(weight) if weight else None)
        self.family = family_name(ui.get("overlay_font_family"))
        self.scale = theme.clamp_int(ui.get("overlay_font_scale"), 80, 160, 100) / 100
        self.weight = theme.clamp_int(ui.get("overlay_font_weight"), 400, 800, 600)
        self.outline = ui.get("overlay_text_outline") is True
        self.outline_colour = hex_colour(ui.get("overlay_outline_color")) or "#000000"
        self.glow = ui.get("overlay_glow") is True
        self.glow_colour = hex_colour(ui.get("overlay_glow_color")) or "#e8cf8e"
        self.halo = ui.get("overlay_text_halo") is True
        self.halo_colour = hex_colour(ui.get("overlay_halo_color")) or "#e8cf8e"
        self.retro = ui.get("overlay_text_retro") is True
        self.cycle = ui.get("overlay_color_cycle") is True
        self.ttk_colour = hex_colour(ui.get("overlay_ttk_color")) or "#8fb3d0"
        mode = ui.get("overlay_text_autocontrast")
        self.autocontrast = mode if mode in ("blend", "luminance") else "off"
        self.contrast: str | None = None
        self.blend = False

    @property
    def effects(self) -> bool:
        return self.outline or self.glow or self.halo

    @property
    def painted(self) -> bool:
        """Whether the text is drawn as more than its plain glyphs: with effects, or blended with what is behind."""
        return self.effects or self.blend

    def families(self, key: str | None = None) -> list[str]:
        own = self.fonts.get(key, (None,))[0] if key else None
        lead = own or self.family
        return ([lead] if lead else []) + [f for f in theme.FONT_FAMILIES if f != lead]

    def colour(self, key: str, default: str) -> str:
        return self.contrast or self.colours.get(key) or default

    def size(self, key: str, px: float) -> int:
        """An element's size: its own px (from the overlay's font size) times its own size setting."""
        scale = self.fonts.get(key, (None, None, None))[1]
        return max(6, round(px * (scale or 1)))

    def weight_of(self, key: str, weight: int) -> int:
        return self.fonts.get(key, (None, None, None))[2] or weight

    def font(self, key: str, px: float, weight: int) -> QFont:
        font = QFont()
        font.setFamilies(self.families(key))
        font.setPixelSize(self.size(key, px))
        font.setWeight(QFont.Weight(max(100, min(900, self.weight_of(key, weight)))))
        return font

    def css(self, key: str, px: float, weight: int, colour: str | None = None) -> str:
        """A style sheet's font for an element, and its colour when ``colour`` (its own default) is given: its own
        where set, else these. The family is the window's (the overlay's own, or ``overlay_font_family``) unless
        the element has one of its own."""
        parts = [f"color: {self.colour(key, colour)};"] if colour else []
        if self.fonts.get(key, (None,))[0]:
            parts.append("font-family: " + ", ".join(f'"{name}"' for name in self.families(key)) + ";")
        parts += [f"font-size: {self.size(key, px)}px;", f"font-weight: {self.weight_of(key, weight)};"]
        return " ".join(parts)

    def style(self, key: str, px: float, colour: str | None = None, weight: int | None = None) -> str:
        """Rich text's style for an element inside a line: its own colour, family, size and weight where those
        are set (the contrast colour over all), else ``colour`` and ``weight``, else the line's own."""
        family, scale, own_weight = self.fonts.get(key, (None, None, None))
        parts = []
        if shade := self.contrast or self.colours.get(key) or colour:
            parts.append(f"color:{shade}")
        if family:
            parts.append("font-family:" + ", ".join(f"'{name}'" for name in self.families(key)))
        if scale:
            parts.append(f"font-size:{self.size(key, px)}px")
        if own_weight or weight:
            parts.append(f"font-weight:{own_weight or weight}")
        return "; ".join(parts)

    def inline(self, key: str, text: str, px: float, colour: str | None = None, weight: int | None = None) -> str:
        """``text`` (already escaped) as rich text in the element's own look, or as it is when it has none."""
        style = self.style(key, px, colour, weight)
        return f'<span style="{style}">{text}</span>' if style else text


def cycled(colour: str | QColor, seconds: float) -> QColor:
    """``filter: hue-rotate`` at ``seconds`` into the colour cycle's 12 s: the Filter Effects matrix on the sRGB
    values, as browsers apply it. A colour turns through the hues; a grey, the overlay's light text among them,
    stays as it is."""
    colour = QColor(colour)
    angle = (seconds % CYCLE_S) / CYCLE_S * 2 * math.pi
    c, s = math.cos(angle), math.sin(angle)
    matrix = ((0.213 + 0.787 * c - 0.213 * s, 0.715 - 0.715 * c - 0.715 * s, 0.072 - 0.072 * c + 0.928 * s),
              (0.213 - 0.213 * c + 0.143 * s, 0.715 + 0.285 * c + 0.140 * s, 0.072 - 0.072 * c - 0.283 * s),
              (0.213 - 0.213 * c - 0.787 * s, 0.715 - 0.715 * c + 0.715 * s, 0.072 + 0.928 * c + 0.072 * s))
    rgb = (colour.redF(), colour.greenF(), colour.blueF())
    turned = [max(0.0, min(1.0, sum(weight * value for weight, value in zip(row, rgb)))) for row in matrix]
    return QColor.fromRgbF(*turned, colour.alphaF())


def sheen_brush(rect: QRectF, colour: QColor, seconds: float) -> QLinearGradient:
    """``ov-retro-sheen`` at ``seconds`` into its 3.5 s: over the names' room (``rect``), a 100° gradient three times
    its width, the text's colour with a near-white band at its middle, moved six widths to the right in each turn
    (``background-position`` 0 to −300%, repeated), so the band crosses the names twice. One band at most lies
    over them at a time: the nearest is drawn, the colour flat beyond it."""
    width, height = max(1.0, rect.width()), rect.height()
    tile = 3 * width
    middle = rect.left() + tile / 2 + (seconds % SHEEN_S) / SHEEN_S * 2 * tile
    middle -= round((middle - rect.center().x()) / tile) * tile
    angle = math.radians(100)
    step = QPointF(math.sin(angle), -math.cos(angle))
    length = tile * abs(step.x()) + height * abs(step.y())
    centre = QPointF(middle, rect.center().y())
    gradient = QLinearGradient(centre - step * (length / 2), centre + step * (length / 2))
    gradient.setColorAt(0.0, colour)
    gradient.setColorAt(0.42, colour)
    gradient.setColorAt(0.5, QColor(255, 255, 255, 235))
    gradient.setColorAt(0.58, colour)
    gradient.setColorAt(1.0, colour)
    return gradient


def _pad(look: TextLook) -> int:
    """The room the effects take round the text."""
    return 16 if look.halo else 10 if look.glow else 2 if look.outline else 0


def _tinted(pixmap: QPixmap, paint) -> QPixmap:
    """The pixmap's shape filled with ``paint``, a colour or a brush (the sheen)."""
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(QRectF(0, 0, out.width(), out.height()), paint if isinstance(paint, QBrush) else QColor(paint))
    painter.end()
    return out


def _blurred(pixmap: QPixmap, radius: float) -> QPixmap:
    """``text-shadow``'s blur: the pixmap shrunk ``radius`` times and grown back smoothly, a box and a tent whose
    spread together is about the Gaussian's (a standard deviation of half the radius)."""
    width, height = pixmap.width(), pixmap.height()
    step = max(1, round(radius * pixmap.devicePixelRatio()))
    small = pixmap.scaled(max(1, width // step), max(1, height // step), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    out = small.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    return out


def _masks(source: QPixmap, look: TextLook) -> tuple[QPixmap | None, QPixmap | None]:
    """The effects of a text's picture, white, to be tinted: the halo's or the glow's spread (the compact layout
    shows the halo alone when both are on), and the outline's ring a pixel round the glyphs."""
    behind = ring = None
    white = _tinted(source, "#ffffff") if look.effects else None
    if look.halo or look.glow:
        behind = _clear(source)
        painter = QPainter(behind)
        for radius in HALO_BLURS if look.halo else GLOW_BLURS:
            painter.drawPixmap(0, 0, _blurred(white, radius))
        painter.end()
    if look.outline:
        ring = _clear(source)
        painter = QPainter(ring)
        for dx, dy in _RING:
            painter.drawPixmap(dx, dy, white)
        painter.end()
    return behind, ring


def _clear(like: QPixmap) -> QPixmap:
    out = QPixmap(like.size())
    out.setDevicePixelRatio(like.devicePixelRatio())
    out.fill(Qt.transparent)
    return out


def _layer(source: QPixmap, look: TextLook, masks, fill=None, shift=None) -> QPixmap:
    """The text's picture (``source``, on a clear ground with room round it) with its effects (``masks``) behind it
    in their colours, turned by ``shift`` (the colour cycle) when given, then the text itself, as it is or filled
    with ``fill``."""
    behind, ring = masks
    turn = shift or (lambda colour: colour)
    layer = _clear(source)
    painter = QPainter(layer)
    if behind is not None:
        painter.drawPixmap(0, 0, _tinted(behind, turn(QColor(look.halo_colour if look.halo else look.glow_colour))))
    if ring is not None:
        painter.setOpacity(OUTLINE_OPACITY)
        painter.drawPixmap(0, 0, _tinted(ring, turn(QColor(look.outline_colour))))
        painter.setOpacity(1.0)
    painter.drawPixmap(0, 0, source if fill is None else _tinted(source, fill))
    painter.end()
    return layer


_GLYPHS: OrderedDict = OrderedDict()      # the rows' texts as pictures with their effects' masks, the latest kept
_GLYPHS_KEPT = 64


def forget_pictures() -> None:
    """Let the kept pictures go (the overlay closing), so none outlives Qt's application."""
    _GLYPHS.clear()


def draw_text(painter: QPainter, rect: QRectF, text: str, font: QFont, colour: QColor, align, look: TextLook,
              brush=None, shift=None) -> float:
    """Draw ``text`` in ``rect`` (left or right aligned, centred upright) in ``colour`` or ``brush`` (the sheen),
    with the look's effects as the labels have them (``TextEffect``), their colours turned by ``shift`` (the colour
    cycle), and blended with what lies behind it in the blend mode; answers its width. The text's picture and its
    effects' masks are kept for the next drawing of the same text, so a frame of the cycle or the sheen only tints
    them."""
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text)
    if not look.painted and brush is None:
        painter.setFont(font)
        painter.setPen(colour)
        painter.drawText(rect, align | Qt.AlignVCenter, text)
        return width
    x = rect.right() - width if align & Qt.AlignRight else rect.left()
    pad = _pad(look)
    box = QRectF(round(x) - pad, round(rect.top()) - pad, math.ceil(width) + 2 * pad + 1, rect.height() + 2 * pad)
    ratio = painter.device().devicePixelRatioF()
    key = (text, font.key(), ratio, box.width(), box.height(), round(x - box.left(), 3),
           round(rect.top() - box.top(), 3), look.halo, look.glow, look.outline)
    kept = _GLYPHS.pop(key, None)
    if kept is None:
        glyphs = QPixmap(max(1, math.ceil(box.width() * ratio)), max(1, math.ceil(box.height() * ratio)))
        glyphs.setDevicePixelRatio(ratio)
        glyphs.fill(Qt.transparent)
        inner = QPainter(glyphs)
        inner.setFont(font)
        inner.setPen(QColor(255, 255, 255))
        inner.drawText(QRectF(x - box.left(), rect.top() - box.top(), width + 1, rect.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, text)
        inner.end()
        kept = (glyphs, _masks(glyphs, look))
        while len(_GLYPHS) >= _GLYPHS_KEPT:
            _GLYPHS.popitem(last=False)
    _GLYPHS[key] = kept
    glyphs, masks = kept
    fill = colour
    if brush is not None:                     # the sheen, moved into the picture's own place
        fill = QBrush(brush)
        fill.setTransform(QTransform.fromTranslate(-box.left(), -box.top()))
    painter.save()
    if look.blend:                            # the text and its effects as one, inverted against what is behind
        painter.setCompositionMode(QPainter.CompositionMode_Difference)
    painter.drawPixmap(box.topLeft(), _layer(glyphs, look, masks, fill, shift))
    painter.restore()
    return width


class TextEffect(QGraphicsEffect):
    """The halo or glow and the outline round a label's text, its blend in the blend mode, and (``tint``) the
    header's colour as it turns through the hues, its effects turning with it (``shift``). The overlay's labels draw their text alone on a clear background,
    so the label's picture is the glyphs' shape: tinted and spread for the halo and glow, stamped a pixel round for
    the outline, then the text over them, the whole drawn at once. Keep a reference to it: the label alone does not,
    and an effect without one is not asked to draw."""

    def __init__(self, look: TextLook, parent=None):
        super().__init__(parent)
        self.look = look
        self.tint: QColor | None = None
        self.shift = None
        self._kept = (None, (None, None))         # the label's picture as last drawn, and its effects' masks

    def set_look(self, look: TextLook) -> None:
        self.look = look
        self.updateBoundingRect()
        self.update()

    def boundingRectFor(self, rect):
        pad = _pad(self.look)
        return rect.adjusted(-pad, -pad, pad, pad)

    def draw(self, painter):
        look = self.look
        if not look.painted and self.tint is None:
            self.drawSource(painter)
            return
        source = self.sourcePixmap(Qt.LogicalCoordinates)   # padded to boundingRectFor (PySide gives no offset)
        at = self.boundingRectFor(self.sourceBoundingRect(Qt.LogicalCoordinates)).toAlignedRect().topLeft()
        key = (source.cacheKey(), look.halo, look.glow, look.outline)
        if key != self._kept[0]:                  # Qt keeps the picture while the label is unchanged
            self._kept = (key, _masks(source, look))
        painter.save()
        if look.blend:
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
        painter.drawPixmap(at, _layer(source, look, self._kept[1], self.tint, self.shift))
        painter.restore()


def contrast_colour(image: QImage, darken: float) -> str:
    """overlay.js ``computeBgContrast``: the image's mean relative luminance (WCAG, weighted by its alpha) under its
    darkening, and the text colour that stands out from it: near-black over a light image, near-white over a dark."""
    small = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_ARGB32)

    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    total = weight = 0.0
    for y in range(small.height()):
        for x in range(small.width()):
            pixel = small.pixelColor(x, y)
            alpha = pixel.alpha() / 255
            total += (0.2126 * linear(pixel.red()) + 0.7152 * linear(pixel.green())
                      + 0.0722 * linear(pixel.blue())) * alpha
            weight += alpha
    luminance = (total / weight if weight else 0.0) * (1 - max(0.0, min(1.0, darken)))
    return "#0a0e16" if luminance > 0.179 else "#f4f1ea"


def background_rect(box: QRectF, image_width: int, image_height: int, zoom: float) -> QRectF:
    """Where the background image lies in its box (overlay.css ``#ovbg``, ``background-size: zoom%`` and
    ``background-position: center``): ``zoom`` of the box's width wide, its height in proportion, centred."""
    width = box.width() * zoom
    height = width * image_height / image_width if image_width else 0.0
    return QRectF(box.center().x() - width / 2, box.center().y() - height / 2, width, height)


def reduced_motion() -> bool:
    """Whether the system asks for less motion, which holds the colour cycle and the sheen still as the web
    overlay's ``prefers-reduced-motion`` does: on Windows "Show animations in Windows" turned off, which is what the
    browser reads there. Elsewhere Qt has no way to ask, and they move."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        on = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0):   # SPI_GETCLIENTAREAANIMATION
            return not on.value
    except (AttributeError, OSError):
        pass
    return False
