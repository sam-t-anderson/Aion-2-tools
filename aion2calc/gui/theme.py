"""The native interface's colours, fonts and number formats: the web interface's own (0.2.413).

The colours are ``app.css``'s, read from it: its dark theme, its light one and its accent colours (since 0.2.484;
until then the dark theme alone), and the overlay's class colours (``OVERLAY_CLASS_COLORS`` in ``overlay.js``);
``kfmt`` and ``sfmt`` write numbers as the overlay does, so a reading looks the same in both.

``COLORS`` holds the look shown, each of app.css's custom properties under its name with "_" for "-"
(``--gold-dim`` is ``gold_dim``), as a colour Qt reads: a translucent one (``--panel``, ``--frame``) as the colour
it is drawn with, without its transparency, where ``CSS`` keeps it whole, as app.css writes it. ``apply_look``
puts another theme or accent in them, in place, before the window is drawn (again).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
import functools
import math
import pathlib
import re

APP_CSS = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "app.css"
#: app.js ``THEMES`` and ``ACCENTS``: the themes (the computer's, or one chosen) and the accent colours.
THEMES = ("system", "light", "dark")
ACCENTS = ("gold", "crimson", "emerald", "azure", "amethyst", "rose")


def _rules(css: str) -> dict[str, dict[str, str]]:
    """app.css's ``:root`` rules that start a line, each selector's custom properties (the ones inside its
    ``prefers-color-scheme`` block, indented, say the same as these)."""
    rules = {}
    for m in re.finditer(r"^(:root[^{]*)\{([^}]*)\}", css, re.M):
        rules[m.group(1).strip()] = {name: value.strip() for name, value in
                                     re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(2))}
    return rules


def opaque(value: str) -> str:
    """A colour as Qt reads it: ``#rrggbb`` as it is, ``rgba(r, g, b, a)`` without its transparency."""
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)", value.strip())
    return "#%02x%02x%02x" % tuple(int(x) for x in m.groups()) if m else value.strip()


@functools.lru_cache(maxsize=None)
def palette(shown: str = "dark", accent: str = "gold") -> dict[str, str]:
    """app.css's custom properties for a theme shown ("dark" or "light") and an accent, by their names here."""
    rules = _rules(APP_CSS.read_text(encoding="utf-8"))
    values = dict(rules.get(":root", {}))
    if shown == "light":
        values.update(rules.get(":root[data-theme=light]", {}))
    if accent != "gold":
        values.update(rules.get(f":root[data-accent={accent}]", {}))
        if shown == "light":
            values.update(rules.get(f":root[data-accent={accent}][data-theme=light]", {}))
    return {name.replace("-", "_"): value for name, value in values.items()}


#: The look shown: the theme chosen, the accent, and the theme drawn ("system" is the computer's).
LOOK = {"theme": "system", "accent": "gold", "shown": "dark"}
CSS: dict[str, str] = {}
COLORS: dict[str, str] = {}


def apply_look(theme: str = "system", accent: str = "gold", computer_light: bool | None = None) -> str:
    """Show ``theme`` (one of ``THEMES``) with ``accent`` (one of ``ACCENTS``): app.js ``setTheme`` and
    ``setAccent``. "system" follows the computer's light or dark (``computer_light``, else Qt's reading of it).
    Returns the theme drawn. What is drawn after this has the colours; the window draws itself again for them."""
    theme = theme if theme in THEMES else "system"
    accent = accent if accent in ACCENTS else "gold"
    if theme == "system":
        light = computer_light if computer_light is not None else _computer_light()
        shown = "light" if light else "dark"
    else:
        shown = theme
    values = palette(shown, accent)
    CSS.clear()
    CSS.update(values)
    COLORS.clear()
    COLORS.update({name: opaque(value) for name, value in values.items()})
    LOOK.update(theme=theme, accent=accent, shown=shown)
    return shown


def _computer_light() -> bool:
    """Whether the computer's own look is light (``prefers-color-scheme: light``)."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance() is None:
            return False
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light
    except (ImportError, AttributeError, RuntimeError):
        return False


def look_of(store) -> tuple[str, str]:
    """The theme and accent the web pages keep (app.js ``getTheme`` and ``getAccent``): "system" and "gold" where
    there is none, or one that is not theirs."""
    try:
        chosen, accent = store.value("theme"), store.value("accent")
    except Exception:
        chosen = accent = None
    return chosen if chosen in THEMES else "system", accent if accent in ACCENTS else "gold"


_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")


def chosen_theme(store) -> str:
    """The theme as the web page's Settings shows it chosen (app.js ``getTheme``): what the web pages keep, unchecked,
    "system" where there is none. One that is none of ``THEMES`` shows no button chosen, and the computer's look."""
    try:
        return store.value("theme") or "system"
    except Exception:
        return "system"


def css(name: str) -> str:
    """A custom property for a Qt style sheet: as app.css writes it, an alpha with its leading zero
    (``rgba(206, 182, 122, 0.28)``)."""
    value = CSS[name]
    m = _RGBA.fullmatch(value)
    if m is None or m.group(4) is None:
        return value
    r, g, b, a = m.groups()
    return f"rgba({r}, {g}, {b}, {float(a):g})" if float(a) >= 1 else f"rgba({r}, {g}, {b}, {float(a):.4g})".replace(
        ", .", ", 0.")


def qcolor(name: str):
    """A custom property as a QColor, with its transparency (``--inset``'s .65 is 166 of 255)."""
    from PySide6.QtGui import QColor
    m = _RGBA.fullmatch(CSS[name])
    if m is None:
        return QColor(CSS[name])
    r, g, b, a = m.groups()
    return QColor(int(r), int(g), int(b), round(float(a) * 255) if a is not None else 255)


class Shade:
    """A colour of the look shown, read each time it is written (``f"color: {GAIN}"``), so a page drawn after the
    look changes writes the new one; ``whole`` keeps a translucent colour's transparency (``css``)."""

    __slots__ = ("name", "whole")

    def __init__(self, name: str, whole: bool = False):
        self.name, self.whole = name, whole

    def __str__(self) -> str:
        return css(self.name) if self.whole else COLORS[self.name]

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)

    def __eq__(self, other) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"Shade({self.name!r}: {str(self)!r})"


class Sheet:
    """A style sheet written in the look shown each time it is used (a page's ``STYLE``): ``str(sheet)``, or added
    to another style sheet, as a text is."""

    __slots__ = ("write",)

    def __init__(self, write):
        self.write = write

    def __str__(self) -> str:
        return self.write()

    def __format__(self, spec: str) -> str:
        return format(self.write(), spec)

    def __add__(self, other):
        return self.write() + str(other)

    def __radd__(self, other):
        return str(other) + self.write()

    def __eq__(self, other) -> bool:
        return self.write() == str(other)

    def __hash__(self) -> int:
        return id(self)


class Shades(dict):
    """A table of colours of the look shown by name (the grades'): each value read as the look has it now."""

    def __getitem__(self, key):
        return str(super().__getitem__(key))

    def get(self, key, default=None):
        return self[key] if key in self else default

    def values(self):
        return [self[key] for key in self]

    def items(self):
        return [(key, self[key]) for key in self]


apply_look("dark")                                # the dark theme until the window applies the one chosen
#: The overlay card's background (overlay.css ``--nm-card``, the compact layout's): rgb(12, 14, 17) at the overlay's
#: opacity.
OVERLAY_CARD = (12, 14, 17)
#: Each class's bar colour on the overlay (overlay.js ``OVERLAY_CLASS_COLORS``).
CLASS_COLORS = {"sorcerer": "#3a86c8", "assassin": "#4caf6e", "templar": "#c9772b", "ranger": "#b9962a",
                "chanter": "#b84f9e", "gladiator": "#c8474f", "spiritmaster": "#7a63d8", "cleric": "#3fb4b0",
                "brawler": "#7f9a3a"}
FALLBACK_CLASS_COLOR = "#7d8aa3"
FONT_FAMILIES = ["Noto Sans", "Segoe UI", "Roboto", "sans-serif"]


def clamp_int(value, low: int, high: int, default: int) -> int:
    """A whole-number setting in its range, else its default (overlay.js ``clampInt``)."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def class_color(cls) -> str:
    return CLASS_COLORS.get(str(cls or "").lower(), FALLBACK_CLASS_COLOR)


def fixed(value: float, digits: int) -> str:
    """JavaScript's ``toFixed``: the value rounded half away from zero, as the web pages round (Python's own
    formatting rounds a half to the even digit, so 1.125 would read 1.12 where the web overlay reads 1.13)."""
    value = float(value) or 0.0                  # -0 reads 0, as in JavaScript
    if not math.isfinite(value) or abs(value) >= 1e21:
        return str(value)                        # toFixed writes these as String(x) does
    return str(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def js_round(value: float) -> int:
    """JavaScript's ``Math.round``: a half goes up (Python's ``round`` goes to the even number)."""
    return math.floor(float(value) + 0.5)


@functools.lru_cache(maxsize=1)
def _digit_locale():
    from PySide6.QtCore import QLocale
    languages = [name for name in QLocale().uiLanguages() if name not in ("C", "POSIX")]
    return QLocale(languages[0]) if languages else QLocale(QLocale.English, QLocale.UnitedStates)


def digits(value) -> str:
    """``Math.round(value).toLocaleString()``: whole digits grouped as the system's language groups them, as the web
    pages write them in the browser's language (the system's); in English where the system names no language."""
    return _digit_locale().toString(js_round(value))


def number(value, most: int = 3) -> str:
    """``Number(value).toLocaleString(undefined, {maximumFractionDigits: most})``: the value to at most ``most``
    places without trailing zeros, its whole digits grouped as ``digits`` groups them. As the browser does, it rounds
    the value's shortest decimal form (1.0005 reads 1.001), a half away from zero, and keeps the sign of a negative
    value that rounds to nothing ("-0")."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "NaN"
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "∞" if x > 0 else "-∞"
    rounded = Decimal(repr(x)).quantize(Decimal(1).scaleb(-most), rounding=ROUND_HALF_UP)
    whole, _, part = f"{abs(rounded):f}".partition(".")
    part = part.rstrip("0")
    locale = _digit_locale()
    grouped = (locale.toString(int(whole)) if int(whole) < 2 ** 63 else      # beyond Qt's whole numbers: in threes
               locale.groupSeparator().join(f"{int(whole):,}".split(",")))
    return ("-" if rounded.is_signed() else "") + grouped + (locale.decimalPoint() + part if part else "")


def kfmt(x) -> str:
    """A rate or amount as the overlay writes it: 1.23M, 45.60K, 812; a dash when there is none."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(x):
        return "—"
    a = abs(x)
    if a >= 1e6:
        return fixed(x / 1e6, 2) + "M"
    if a >= 1e3:
        return fixed(x / 1e3, 2) + "K"
    return str(js_round(x))


def sfmt(x) -> str:
    """A short amount (combat power, counts): 1.5B, 12.3M, 4K, 812."""
    try:
        x = float(x or 0)
    except (TypeError, ValueError):
        x = 0.0
    if not math.isfinite(x):
        x = 0.0
    a = abs(x)
    for limit, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= limit:
            text = fixed(x / limit, 1)
            return (text[:-2] if text.endswith(".0") else text) + unit
    return str(js_round(x))


def count(regular, bonus=0) -> str:
    """A counter as the game writes it: the total, with the regular and bonus parts when there is a bonus."""
    regular, bonus = int(regular or 0), int(bonus or 0)
    total = f"{regular + bonus:,}"
    return f"{total} ({regular:,} + {bonus:,} bonus)" if bonus else total


def short_count(regular, bonus=0) -> str:
    """The narrow overlay's form: the regular count, then the bonus in brackets (``12(+4)``)."""
    regular, bonus = int(regular or 0), int(bonus or 0)
    return f"{regular:,}(+{bonus:,})" if bonus else f"{regular:,}"


def app_stylesheet() -> str:
    """The main window's Qt style sheet, in the look shown."""
    c = COLORS
    return f"""
    QWidget {{ background: {c['bg1']}; color: {c['text']}; font-family: "Noto Sans", "Segoe UI", sans-serif; font-size: 13px; }}
    QListWidget#nav {{ background: {c['bg0']}; border: none; border-right: 1px solid {c['line']}; padding: 6px 0; }}
    QListWidget#nav::item {{ padding: 7px 14px; color: {c['muted']}; }}
    QListWidget#nav::item:selected {{ background: {c['hover']}; color: {c['gold']}; border-left: 3px solid {c['gold']}; }}
    QListWidget#nav::item:disabled {{ color: {c['gold_dim']}; font-weight: 700; padding-top: 12px; }}
    QLabel#heading {{ color: {c['gold']}; font-size: 20px; font-weight: 700; }}
    QLabel.muted, QLabel#muted {{ color: {c['muted']}; }}
    QPushButton {{ background: {c['card_a']}; border: 1px solid {c['line2']}; border-radius: 6px; padding: 5px 12px; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:disabled {{ color: {c['faint']}; }}
    QTableWidget {{ background: {c['bg2']}; gridline-color: {c['line']}; border: 1px solid {c['line']}; }}
    QHeaderView::section {{ background: {c['card_b']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['line']}; padding: 4px 6px; }}
    QComboBox, QLineEdit, QSpinBox {{ background: {c['bg2']}; border: 1px solid {c['line2']}; border-radius: 5px; padding: 3px 6px; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {c['line2']}; border-radius: 3px; background: {c['bg2']}; }}
    QCheckBox::indicator:hover {{ border-color: {c['gold_dim']}; }}
    QCheckBox::indicator:checked {{ background: {c['gold']}; border-color: {c['gold']}; }}
    """
