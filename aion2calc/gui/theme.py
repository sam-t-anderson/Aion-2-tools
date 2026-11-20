"""The native interface's colours, fonts and number formats: the web interface's own (0.2.413).

The colours are ``app.css``'s dark theme and the overlay's class colours (``OVERLAY_CLASS_COLORS`` in
``overlay.js``); ``kfmt`` and ``sfmt`` write numbers as the overlay does, so a reading looks the same in both.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
import math

#: app.css's dark theme (``:root``).
COLORS = {
    "bg0": "#070a10", "bg1": "#0d1320", "bg2": "#121a2a", "panel": "#101623", "panel2": "#182032",
    "card_a": "#1c2236", "card_b": "#121726", "hover": "#1b2337", "line": "#263048", "line2": "#3a4562",
    "gold": "#e8cf8e", "gold_dim": "#b49a5c", "text": "#e9e6df", "muted": "#9aa3b5", "faint": "#848b9a",
    "accent": "#39c2e0", "good": "#6fcf7a", "bad": "#e66a5a", "warn": "#e9a43a",
}
#: The overlay card's background (overlay.css ``.ovcard``): rgb(27, 32, 42) at the overlay's opacity.
OVERLAY_CARD = (27, 32, 42)
#: Each class's bar colour on the overlay (overlay.js ``OVERLAY_CLASS_COLORS``).
CLASS_COLORS = {"sorcerer": "#3a86c8", "assassin": "#4caf6e", "templar": "#c9772b", "ranger": "#b9962a",
                "chanter": "#b84f9e", "gladiator": "#c8474f", "spiritmaster": "#7a63d8", "cleric": "#3fb4b0",
                "brawler": "#7f9a3a"}
FALLBACK_CLASS_COLOR = "#7d8aa3"
FONT_FAMILIES = ["Noto Sans", "Segoe UI", "Roboto", "sans-serif"]


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
    """The main window's Qt style sheet, from the dark theme."""
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
