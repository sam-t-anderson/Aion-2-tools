"""A picture of the game's screen.

The game window is found as the overlay finds it (``overlay._Windows.game_window``): the client area of
the largest visible window of the game's process, measured in physical pixels. The picture is what the
screen shows there, so the game must be in front (or at least not covered) when it is taken; a game
window that is minimized, or not found, gives the whole primary screen instead.
"""
from __future__ import annotations

import ctypes
import sys

from .ocr import Unavailable

#: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2: window sizes in physical pixels, as Pillow grabs them
_PER_MONITOR_V2 = -4


def _game_bounds() -> tuple[int, int, int, int] | None:
    from ..overlay import _Windows
    game = _Windows().game_window()
    if game is None or game.minimized:
        return None
    return game.bounds


def game_screen():
    """``(picture, where)``: a PIL image of the game window (``where`` is "game window") or of the
    primary screen ("screen") when the game window is not found."""
    if sys.platform != "win32":
        raise Unavailable("Reading the game screen works on Windows only; paste a screenshot instead.")
    from PIL import ImageGrab
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    set_context = getattr(user32, "SetThreadDpiAwarenessContext", None)     # Windows 10 1607 and later
    previous = None
    if set_context is not None:
        set_context.argtypes, set_context.restype = [ctypes.c_void_p], ctypes.c_void_p
        previous = set_context(ctypes.c_void_p(_PER_MONITOR_V2))
    try:
        bounds = _game_bounds()
        if bounds is None:
            return ImageGrab.grab(), "screen"
        x, y, w, h = bounds
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True), "game window"
    finally:
        if set_context is not None and previous:
            set_context(ctypes.c_void_p(previous))
