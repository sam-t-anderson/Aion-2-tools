"""The compact native meter / raid-plan overlay (or a browser fallback)."""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import logging
import ntpath
import os
import sys
import threading
import webbrowser


_LOG = logging.getLogger(__name__)
_GAME_EXECUTABLES = {"aion2.exe", "aion2-win64.exe", "aion2-win64-shipping.exe"}


def _is_game_process(path: str) -> bool:
    # Titles also match browsers, the launcher, and Aion 2 Calc itself.
    return ntpath.basename(path).casefold() in _GAME_EXECUTABLES


@dataclass(frozen=True)
class _GameWindow:
    hwnd: int
    bounds: tuple[int, int, int, int]
    minimized: bool = False


class _Windows:
    """Win32 calls with pointer-sized signatures (HWND/HANDLE are 64 bit on x64)."""

    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = {
            "EnumWindows": ([self.callback, w.LPARAM], w.BOOL),
            "IsWindowVisible": ([w.HWND], w.BOOL),
            "IsIconic": ([w.HWND], w.BOOL),
            "GetWindowThreadProcessId": ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            "GetClientRect": ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            "GetWindowRect": ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            "ClientToScreen": ([w.HWND, ctypes.POINTER(w.POINT)], w.BOOL),
            "GetForegroundWindow": ([], w.HWND),
            "SetWindowPos": ([w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, w.UINT], w.BOOL),
            "ShowWindow": ([w.HWND, ctypes.c_int], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.user32, name)
            fn.argtypes, fn.restype = args, result
        self.kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel32.OpenProcess.restype = w.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = w.BOOL
        self.kernel32.CloseHandle.argtypes = [w.HANDLE]
        self.kernel32.CloseHandle.restype = w.BOOL

    def process_name(self, pid: int) -> str:
        handle = self.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            size = self.w.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            self.kernel32.CloseHandle(handle)
        return ""

    def game_window(self) -> _GameWindow | None:
        found = []

        @self.callback
        def visit(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            pid = self.w.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid() or not _is_game_process(self.process_name(pid.value)):
                return True
            rect, point = self.w.RECT(), self.w.POINT()
            if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
                return True
            minimized = bool(self.user32.IsIconic(hwnd))
            if not minimized and (rect.right < 400 or rect.bottom < 300):
                return True
            self.user32.ClientToScreen(hwnd, ctypes.byref(point))
            found.append(_GameWindow(hwnd, (point.x, point.y, rect.right, rect.bottom), minimized))
            return True

        self.user32.EnumWindows(visit, 0)
        return max(found, key=lambda g: g.bounds[2] * g.bounds[3], default=None)

    def rect(self, hwnd) -> tuple[int, int, int, int]:
        rect = self.w.RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    def move(self, hwnd, x: int, y: int) -> None:
        # Physical pixels avoid inconsistent pywebview DPI conversions across versions.
        self.user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)


def _follow_position(previous, bounds, current):
    """Preserve the user's dragged offset as the game moves/resizes."""
    left, top, width, height = bounds
    x, y, overlay_width, overlay_height = current
    dx, dy = (x - previous[0], y - previous[1]) if previous else (16, 48)
    dx = max(0, min(dx, max(0, width - overlay_width)))
    dy = max(0, min(dy, max(0, height - overlay_height)))
    return left + dx, top + dy


class _OverlayAPI:
    def __init__(self):
        self._window = None
        self._opacity = 0.72
        self._size = None
        self._windows_ready = False

    def _on_ui(self, callback):
        from System import Action
        native = self._window.native
        if native.InvokeRequired:
            native.Invoke(Action(callback))
        else:
            callback()

    def _configure_windows(self):
        from System.Drawing import Color

        def configure():
            native = self._window.native
            # Change the extended style without recreating the WinForms HWND.
            # ShowInTaskbar=False recreates it during WebView2 initialization.
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            get_style = user32.GetWindowLongPtrW
            set_style = user32.SetWindowLongPtrW
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t
            handle = native.Handle.ToInt64()
            style = get_style(handle, -20)
            set_style(handle, -20, (style & ~0x00040000) | 0x00000080)
            # WebView2 transparency alone leaves WinForms' opaque white client area.
            # A color key clears that host surface; Opacity gives the card real alpha.
            key = Color.FromArgb(1, 2, 3)
            native.BackColor = key
            native.TransparencyKey = key
            native.webview.DefaultBackgroundColor = Color.Transparent
            native.Opacity = self._opacity

        self._on_ui(configure)
        self._windows_ready = True

    def set_opacity(self, value):
        self._opacity = max(0.2, min(1.0, float(value)))
        if self._windows_ready:
            self._on_ui(lambda: setattr(self._window.native, "Opacity", self._opacity))

    def fit(self, width, height):
        size = (max(260, min(800, int(width))), max(70, min(800, int(height))))
        if size != self._size:
            self._size = size
            self._window.resize(*size)


def _run_overlay(window, api) -> None:
    closed = threading.Event()
    window.events.closed += closed.set
    # pywebview starts this worker before constructing its native window.
    if not window.events.shown.wait(30):
        _LOG.error("Overlay native window did not initialize")
        window.destroy()
        return
    win32 = None
    if sys.platform == "win32":
        try:
            api._configure_windows()
            win32 = _Windows()
        except Exception:
            _LOG.exception("Could not configure the native Windows overlay")
    window.show()
    previous = None
    previous_hwnd = None
    visible = True
    while not closed.wait(0.5):
        if not win32:
            continue
        game = win32.game_window()
        hwnd = window.native.Handle.ToInt64()
        # Wait visibly before the game starts; once attached, follow only the game.
        should_show = game is None or (not game.minimized and
                      win32.user32.GetForegroundWindow() in (game.hwnd, hwnd))
        if visible != should_show:
            win32.user32.ShowWindow(hwnd, 4 if should_show else 0)  # no activation
            visible = should_show
        if game is None:
            previous = previous_hwnd = None
            continue
        if game.minimized:
            continue
        if game.hwnd != previous_hwnd:
            previous = None
        position = _follow_position(previous, game.bounds, win32.rect(hwnd))
        if position != win32.rect(hwnd)[:2]:
            win32.move(hwnd, *position)
        previous, previous_hwnd = game.bounds, game.hwnd


def _default_url() -> str:
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
    ap = argparse.ArgumentParser(prog="python -m aion2calc.overlay", description="Aion 2 Calc transparent overlay")
    ap.add_argument("--url", default=None, help="overlay URL (default: the running app's /overlay)")
    ap.add_argument("--width", type=int, default=340)
    ap.add_argument("--height", type=int, default=120)
    a = ap.parse_args(argv)
    url = a.url or _default_url()
    try:
        import webview
    except Exception:
        webbrowser.open(url)
        return 0
    try:
        api = _OverlayAPI()
        # Stable card content is draggable; JS stops events at the tabs and slider.
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = False
        window = webview.create_window("Aion 2 Calc Overlay", url, frameless=True, easy_drag=False,
                                       shadow=False, on_top=True, hidden=True, focus=False,
                                       transparent=sys.platform != "win32", background_color="#010203",
                                       width=a.width, height=a.height, min_size=(260, 70),
                                       resizable=False, js_api=api)
        api._window = window
        webview.start(_run_overlay, args=(window, api),
                      gui="edgechromium" if sys.platform == "win32" else None)
    except Exception as err:
        print(f"Could not open the overlay ({type(err).__name__}: {err}); using the browser instead.")
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
