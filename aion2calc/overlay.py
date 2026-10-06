"""Open the compact meter / raid-plan overlay in a transparent, always-on-top window.

    python -m aion2calc.overlay                       # connects to the running app
    python -m aion2calc.overlay --url http://127.0.0.1:8765/overlay

A frameless, transparent, always-on-top window needs pywebview (``pip install pywebview``). Without
it the overlay opens in your default browser — a normal window you can size and place next to the
game. The overlay shows the live damage meter (from /api/meter) and plays your most recent raid plan.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import threading
import webbrowser


def _game_bounds() -> tuple[int, int, int, int] | None:
    """Return the visible Aion 2 game window bounds on Windows, when present."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_query_limited_information = 0x1000
    matches = ("aion2", "aion 2", "aion2-win64-shipping")
    found: list[tuple[int, int, int, int]] = []

    def process_name(pid: int) -> str:
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].casefold()
        finally:
            kernel32.CloseHandle(handle)
        return ""

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title_size = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(title_size + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not any(part in (title.value + " " + process_name(pid.value)).casefold() for part in matches):
            return True
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)) and rect.right - rect.left >= 400 and rect.bottom - rect.top >= 300:
            found.append((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
            return False
        return True

    user32.EnumWindows(visit, 0)
    return found[0] if found else None


def _attach_to_game(window) -> None:
    """Keep the frameless overlay aligned to Aion 2; wait quietly until the client starts."""
    closed = threading.Event()
    window.events.closed += closed.set
    previous = None
    while not closed.wait(1.0):
        bounds = _game_bounds()
        if bounds and bounds != previous:
            # Keep the native window compact so it never covers the game's input surface;
            # only its position follows the game client.
            left, top, _width, _height = bounds
            window.move(left + 16, top + 48)
            previous = bounds


def _default_url() -> str:
    """The overlay URL: what the app passed in the environment, else what it wrote on startup
    (home/app_url.txt), else the default port."""
    env = os.environ.get("AION2CALC_OVERLAY_URL")
    if env:
        return env
    try:
        from .paths import home
        f = home() / "app_url.txt"
        if f.is_file():
            return f.read_text(encoding="utf-8").strip().rstrip("/") + "/overlay"
    except Exception:
        pass
    return "http://127.0.0.1:8765/overlay"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aion2calc.overlay", description="aion2calc transparent overlay")
    ap.add_argument("--url", default=None, help="overlay URL (default: the running app's /overlay)")
    ap.add_argument("--width", type=int, default=300)
    ap.add_argument("--height", type=int, default=430)
    a = ap.parse_args(argv)
    url = a.url or _default_url()
    try:
        import webview  # pywebview, optional
    except Exception:
        print("pywebview is not installed; opening the overlay in your browser.\n"
              "For a transparent, always-on-top overlay:  pip install pywebview")
        webbrowser.open(url)
        return 0
    try:
        window = webview.create_window("aion2calc overlay", url, frameless=True, easy_drag=False,
                                       shadow=False, on_top=True, transparent=True, background_color="#000000",
                                       width=a.width, height=a.height)
        webview.start(_attach_to_game, args=(window,), gui="edgechromium")
    except Exception as err:          # a backend problem (missing WebView2, GTK, etc.): still show the overlay
        print(f"pywebview could not open a window ({type(err).__name__}: {err}); using the browser instead.")
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
