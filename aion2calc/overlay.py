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
            "GetSystemMetrics": ([ctypes.c_int], ctypes.c_int),
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

    def virtual_screen(self) -> tuple[int, int, int, int]:
        """The bounding box of all monitors (SM_*VIRTUALSCREEN), for validating a
        remembered overlay position still lands on a connected screen."""
        g = self.user32.GetSystemMetrics
        return g(76), g(77), g(78), g(79)   # x, y, width, height


def _follow_position(previous, bounds, current, snap=False, expand_up=False):
    """Preserve the user's dragged offset as the game moves/resizes.

    ``snap`` pulls the overlay flush to a game-window edge when it is within a few
    pixels of it. ``expand_up`` anchors the overlay near the bottom edge so it
    grows upward as rows are added. With both false this returns exactly the
    historical position, so the default overlay behaviour is unchanged.
    """
    left, top, width, height = bounds
    x, y, overlay_width, overlay_height = current
    dx, dy = (x - previous[0], y - previous[1]) if previous else (16, 48)
    dx = max(0, min(dx, max(0, width - overlay_width)))
    if expand_up:
        ny = top + max(0, height - overlay_height - 48)
    else:
        dy = max(0, min(dy, max(0, height - overlay_height)))
        ny = top + dy
    nx = left + dx
    if snap:
        if abs((nx + overlay_width) - (left + width)) <= 24:
            nx = left + width - overlay_width
        if nx - left <= 24:
            nx = left
        if not expand_up:
            if abs((ny + overlay_height) - (top + height)) <= 24:
                ny = top + height - overlay_height
            elif ny - top <= 24:
                ny = top
    return nx, ny


def _overlay_prefs() -> dict:
    """Native overlay preferences read from the user's settings (defaults keep the
    historical behaviour). Read once at launch, so changes apply on reopen."""
    # always_visible defaults to True: the overlay stays on top even when the game
    # is not the foreground window, so focusing another overlay, the app window, or
    # a game loot/reward popup never hides it. The read below uses each key's own
    # default, so an absent key keeps True here and False for the others.
    prefs = {"resizable": False, "snap_edge": False, "expand_up": False, "always_visible": True,
             "remember_position": False}
    # Remembered drag positions (per overlay), restored at launch instead of
    # re-anchoring to the game window. Machine/monitor-specific, so they live only
    # in ui.json (never the shareable settings backup).
    positions = {"meter": None, "party": None}
    try:
        from .paths import data_file, read_json
        if data_file("ui.json").exists():
            ui = read_json("ui.json")
            for key in prefs:
                prefs[key] = ui.get("overlay_" + key, prefs[key]) is True

            def _pos(px, py):
                x, y = ui.get(px), ui.get(py)
                return (int(x), int(y)) if isinstance(x, int) and not isinstance(x, bool) \
                    and isinstance(y, int) and not isinstance(y, bool) else None
            positions["meter"] = _pos("overlay_pos_x", "overlay_pos_y")
            positions["party"] = _pos("overlay_party_pos_x", "overlay_party_pos_y")
    except Exception:
        pass
    prefs["positions"] = positions
    return prefs


class _OverlayAPI:
    def __init__(self):
        self._window = None
        self._opacity = 0.72
        self._size = None
        self._windows_ready = False
        self._locked = False

    def set_locked(self, value):
        # Screenshot lock: keep the overlay visible and stationary while locked.
        self._locked = bool(value)

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
            set_style(handle, -20, (style & ~(0x00040000 | 0x00000020)) | 0x00000080)
            # A color-keyed WinForms parent can be hit-test transparent even where
            # the separate WebView2 child draws the card. Use alpha on a compact
            # dark host instead so the visible overlay accepts mouse input.
            background = Color.FromArgb(10, 14, 22)
            native.BackColor = background
            native.TransparencyKey = Color.Empty
            native.webview.DefaultBackgroundColor = background
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


def _watch_parent(app_base: str, closed: threading.Event, window) -> None:
    """Close the overlay once the app that launched it is gone.

    The overlay is a separate process; if the main window is closed, the app is
    quit, or its process is killed outright, the normal teardown that terminates
    this process can be missed and a stale meter would otherwise stay pinned on
    top forever. Polling the app keeps the overlay's lifetime tied to the app on
    every platform, independent of process-termination signals.
    """
    import urllib.request

    status = f"{app_base.rstrip('/')}/api/status"
    misses = 0
    while not closed.wait(2.0):
        try:
            with urllib.request.urlopen(status, timeout=2) as response:
                response.read(1)
            misses = 0
        except Exception:
            misses += 1
            if misses >= 6:                 # ~12s unreachable: the app is gone, not just busy
                try:
                    window.destroy()
                except Exception:
                    pass
                return


def _save_overlay_position(app_base, party, pos) -> None:
    """Persist a dragged overlay position to the app (ui.json) via its local API,
    keyed per overlay, so it is restored next launch. Best-effort; failures are
    swallowed so a transient app hiccup never disturbs the overlay."""
    if not app_base:
        return
    import json as _json, urllib.request
    keys = ("overlay_party_pos_x", "overlay_party_pos_y") if party else ("overlay_pos_x", "overlay_pos_y")
    body = _json.dumps({keys[0]: int(pos[0]), keys[1]: int(pos[1])}).encode("utf-8")
    try:
        req = urllib.request.Request(app_base.rstrip("/") + "/api/ui", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as response:
            response.read(1)
    except Exception:
        pass


def _run_overlay(window, api, app_base: str | None = None, party: bool = False) -> None:
    closed = threading.Event()
    window.events.closed += closed.set
    if app_base:
        threading.Thread(target=_watch_parent, args=(app_base, closed, window),
                         daemon=True, name="overlay-parent-watch").start()
    # pywebview starts this worker before constructing its native window.
    if not window.events.shown.wait(30):
        _LOG.error("Overlay native window did not initialize")
        window.destroy()
        return
    win32 = None
    if sys.platform == "win32":
        try:
            api._configure_windows()
        except Exception:
            _LOG.exception("Could not configure the native Windows overlay")
        # Opacity/style setup must not disable foreground tracking.
        try:
            win32 = _Windows()
        except Exception:
            _LOG.exception("Could not initialize overlay foreground tracking")
    window.show()
    prefs = _overlay_prefs()
    snap, expand_up = prefs["snap_edge"], prefs["expand_up"]
    always_visible = prefs["always_visible"]
    # Remember-position: restore the overlay where the user last dragged it instead
    # of following the game window. Off by default (the game-follow behaviour below
    # is unchanged). Windows-only (needs the native window rect).
    remember_position = prefs["remember_position"]
    saved_pos = prefs["positions"].get("party" if party else "meter")
    last_pos, pending_pos, pending_ticks = None, None, 0
    if win32 and remember_position and saved_pos:
        try:
            hwnd0 = window.native.Handle.ToInt64()
            vx, vy, vw, vh = win32.virtual_screen()
            sx, sy = saved_pos
            # Only restore when the saved top-left still lands on a connected screen
            # (leave a small grabbable margin); otherwise fall back to game-anchoring.
            if vw > 0 and vh > 0 and vx <= sx <= vx + vw - 40 and vy <= sy <= vy + vh - 40:
                win32.move(hwnd0, sx, sy)
                last_pos = (sx, sy)
        except Exception:
            _LOG.exception("Could not restore the remembered overlay position")
    previous = None
    previous_hwnd = None
    visible = True
    while not closed.wait(0.25):
        if not win32:
            continue
        game = win32.game_window()
        hwnd = window.native.Handle.ToInt64()
        # Keep the overlay shown whenever the game is running and not minimized. By
        # default (always_visible) it stays up even when the game is not the
        # foreground window, so focusing another overlay window, the app, or a game
        # loot/reward popup never hides it. With always_visible off, it is shown only
        # while the game (or the overlay itself) is the foreground window. Either way
        # a missing or minimized game hides it, so it never sits over unrelated apps.
        should_show = game is not None and not game.minimized and (
                      always_visible or win32.user32.GetForegroundWindow() in (game.hwnd, hwnd))
        if api._locked:
            # Keep the overlay shown and in place so it can be screenshotted even
            # when the game is not the foreground window.
            if not visible:
                win32.user32.ShowWindow(hwnd, 4)
                visible = True
            continue
        if visible != should_show:
            win32.user32.ShowWindow(hwnd, 4 if should_show else 0)  # no activation
            visible = should_show
        if game is None:
            previous = previous_hwnd = None
            continue
        if game.minimized:
            continue
        if remember_position:
            # Don't follow the game; keep the overlay where the user put it and save
            # the new spot once a drag settles (~1s stable), so it returns there next
            # launch. Persisted per overlay (meter vs party).
            cur = win32.rect(hwnd)[:2]
            if cur != last_pos:
                if cur == pending_pos:
                    pending_ticks += 1
                else:
                    pending_pos, pending_ticks = cur, 0
                if pending_ticks >= 4:
                    _save_overlay_position(app_base, party, cur)
                    last_pos, pending_pos, pending_ticks = cur, None, 0
            continue
        if game.hwnd != previous_hwnd:
            previous = None
        position = _follow_position(previous, game.bounds, win32.rect(hwnd), snap=snap, expand_up=expand_up)
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
    # The overlay URL is the app's own /overlay page (optionally ?view=party); its
    # base is the app to watch, derived without the path/query.
    app_base = url.split("/overlay")[0] if "/overlay" in url else None
    prefs = _overlay_prefs()
    party = "view=party" in url
    try:
        import webview
    except Exception:
        webbrowser.open(url)
        return 0
    try:
        api = _OverlayAPI()
        # Stable card content is draggable; JS stops events at the tabs and slider.
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = False
        window = webview.create_window("Aion 2 Calc Party Overlay" if party else "Aion 2 Calc Overlay",
                                       url, frameless=True, easy_drag=False,
                                       shadow=False, on_top=True, hidden=True, focus=False,
                                       transparent=sys.platform != "win32", background_color="#010203",
                                       width=a.width, height=a.height, min_size=(260, 70),
                                       resizable=bool(prefs["resizable"]), js_api=api)
        api._window = window
        webview.start(_run_overlay, args=(window, api, app_base, party),
                      gui="edgechromium" if sys.platform == "win32" else None)
    except Exception as err:
        print(f"Could not open the overlay ({type(err).__name__}: {err}); using the browser instead.")
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
