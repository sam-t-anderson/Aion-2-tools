"""The compact native meter / raid-plan overlay (or a browser fallback)."""
from __future__ import annotations

import argparse
import collections
import ctypes
from dataclasses import dataclass
import json
import logging
import ntpath
import os
import sys
import threading
import time

from .overlay_health import (RESTART_EXIT_CODE, UNAVAILABLE_EXIT_CODE, WAITING_HTML, BlankDetector, HealPolicy,
                             OverlayLog, app_answers)


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


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


class _NativeOverlay:
    """The platform-specific operations the overlay's tracking loop needs to drive a
    frameless always-on-top window: find and measure the game window, move the overlay,
    read the screen/monitor geometry, hit-test the cursor, and toggle click-through.

    ``_Windows`` is the implemented backend. ``_MacOS`` and ``_Linux`` are scaffolds for
    the parity work (their real API approach is documented inline). Each backend declares
    ``supported``; the overlay only engages native control when that is true, and
    otherwise runs in its browser/plain-window fallback, so an unimplemented platform
    changes nothing. Keeping this one interface means the cross-platform logic (e.g.
    ``resolve_remembered_position``) stays platform-agnostic and unit-tested."""

    platform = ""
    supported = False

    def game_window(self):
        """The foreground AION 2 window as a ``_GameWindow`` (bounds in screen px), or None."""
        raise NotImplementedError

    def rect(self, handle):
        """The overlay window's (x, y, width, height) in screen px."""
        raise NotImplementedError

    def move(self, handle, x, y):
        """Move the overlay window's top-left to (x, y) in screen px."""
        raise NotImplementedError

    def virtual_screen(self):
        """The bounding box (x, y, width, height) of all monitors."""
        raise NotImplementedError

    def monitors(self):
        """Each monitor's (left, top, width, height); empty if unavailable."""
        return []

    def cursor_in_client(self, handle):
        """The cursor in the overlay's client coordinates (physical px), or None."""
        return None

    def set_click_through(self, handle, enabled):
        """Make the overlay window pass mouse input through to the game, or stop."""
        raise NotImplementedError


class _Windows(_NativeOverlay):
    """Win32 calls with pointer-sized signatures (HWND/HANDLE are 64 bit on x64)."""

    platform = "win32"
    supported = True


    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self._process_names: dict[int, tuple[bool, float]] = {}   # pid -> (is the game, remembered until)
        self._game_hwnd = None          # the game window found last, measured directly while it lasts
        self._rescan_at = 0.0           # when every window is enumerated again
        signatures = {
            "EnumWindows": ([self.callback, w.LPARAM], w.BOOL),
            "IsWindowVisible": ([w.HWND], w.BOOL),
            "IsWindow": ([w.HWND], w.BOOL),
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
            # Cursor hit-testing for click-through: where is the pointer, and in the
            # overlay's own client coordinates?
            "GetCursorPos": ([ctypes.POINTER(w.POINT)], w.BOOL),
            "ScreenToClient": ([w.HWND, ctypes.POINTER(w.POINT)], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.user32, name)
            fn.argtypes, fn.restype = args, result
        # Extended-style get/set for the click-through (WS_EX_TRANSPARENT) toggle.
        # Pointer-sized like the HWND calls above (64-bit safe).
        self.user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        self.user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel32.OpenProcess.restype = w.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = w.BOOL
        self.kernel32.CloseHandle.argtypes = [w.HANDLE]
        self.kernel32.CloseHandle.restype = w.BOOL
        # Capturing the overlay window for the watchdog's blank check: PrintWindow with
        # PW_RENDERFULLCONTENT reads what DWM composes, the WebView2 child included.
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.user32.GetDC.argtypes, self.user32.GetDC.restype = [w.HWND], ctypes.c_void_p
        self.user32.ReleaseDC.argtypes, self.user32.ReleaseDC.restype = [w.HWND, ctypes.c_void_p], ctypes.c_int
        self.user32.PrintWindow.argtypes, self.user32.PrintWindow.restype = [w.HWND, ctypes.c_void_p, w.UINT], w.BOOL
        for name, (args, result) in {
            "CreateCompatibleDC": ([ctypes.c_void_p], ctypes.c_void_p),
            "CreateCompatibleBitmap": ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
            "SelectObject": ([ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p),
            "GetDIBits": ([ctypes.c_void_p, ctypes.c_void_p, w.UINT, w.UINT, ctypes.c_void_p, ctypes.c_void_p, w.UINT], ctypes.c_int),
            "DeleteObject": ([ctypes.c_void_p], w.BOOL),
            "DeleteDC": ([ctypes.c_void_p], w.BOOL),
        }.items():
            fn = getattr(self.gdi32, name)
            fn.argtypes, fn.restype = args, result

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

    #: How long a process id's image name is remembered, and how long a found game window is
    #: followed before every top-level window is enumerated again for a larger one.
    _PROCESS_NAME_TTL_S = 10.0
    _RESCAN_S = 3.0

    def _is_game_pid(self, pid: int) -> bool:
        """Whether ``pid`` is the game, from a cache of process image names: the follow loop
        asked four times a second, and each ask opened every visible window's process
        (0.2.336). A process id is reused only after its process has gone, so a name is
        remembered for a few seconds."""
        if pid == os.getpid():
            return False
        now = time.monotonic()
        known = self._process_names.get(pid)
        if known is None or known[1] <= now:
            if len(self._process_names) > 512:
                self._process_names.clear()
            known = (_is_game_process(self.process_name(pid)), now + self._PROCESS_NAME_TTL_S)
            self._process_names[pid] = known
        return known[0]

    def _measure(self, hwnd) -> _GameWindow | None:
        """The game window's client bounds on screen, or None once it is gone or too small."""
        if not self.user32.IsWindowVisible(hwnd):
            return None
        rect, point = self.w.RECT(), self.w.POINT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        minimized = bool(self.user32.IsIconic(hwnd))
        if not minimized and (rect.right < 400 or rect.bottom < 300):
            return None
        self.user32.ClientToScreen(hwnd, ctypes.byref(point))
        return _GameWindow(hwnd, (point.x, point.y, rect.right, rect.bottom), minimized)

    def game_window(self) -> _GameWindow | None:
        # The window found last is measured again directly while it is still the game's; every
        # top-level window is enumerated only every few seconds (a larger game window may have
        # appeared) or once it is gone.
        now = time.monotonic()
        last = self._game_hwnd
        if last is not None and now < self._rescan_at and self.user32.IsWindow(last):
            pid = self.w.DWORD()
            self.user32.GetWindowThreadProcessId(last, ctypes.byref(pid))
            if self._is_game_pid(pid.value):
                game = self._measure(last)
                if game is not None:
                    return game
        found = []

        @self.callback
        def visit(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            pid = self.w.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not self._is_game_pid(pid.value):
                return True
            game = self._measure(hwnd)
            if game is not None:
                found.append(game)
            return True

        self.user32.EnumWindows(visit, 0)
        game = max(found, key=lambda g: g.bounds[2] * g.bounds[3], default=None)
        self._game_hwnd = game.hwnd if game is not None else None
        self._rescan_at = now + self._RESCAN_S
        return game

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

    def monitors(self) -> list[tuple[int, int, int, int]]:
        """Each connected monitor's screen rectangle (left, top, width, height) in
        virtual-desktop coordinates, via EnumDisplayMonitors. Used to restore a
        remembered overlay position by the monitor layout, so a rearranged multi-monitor
        setup lands the overlay back on the right screen. Empty on failure (the caller
        then falls back to the virtual-screen box)."""
        found: list[tuple[int, int, int, int]] = []
        RECT = self.w.RECT

        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.POINTER(RECT), ctypes.c_void_p)
        def _visit(hmonitor, hdc, lprect, lparam):
            r = lprect.contents
            found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return 1

        try:
            self.user32.EnumDisplayMonitors(None, None, _visit, 0)
        except Exception:
            _LOG.exception("EnumDisplayMonitors failed; falling back to the virtual screen")
            return []
        return found

    def cursor_in_client(self, hwnd) -> tuple[int, int] | None:
        """The mouse position in the overlay's client coordinates (physical px),
        or None if it can't be read. Used to hit-test the overlay's own controls
        while click-through is on."""
        point = self.w.POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            return None
        if not self.user32.ScreenToClient(hwnd, ctypes.byref(point)):
            return None
        return point.x, point.y

    def set_click_through(self, hwnd, enabled: bool) -> None:
        """Toggle WS_EX_TRANSPARENT (0x20) so mouse input falls through the overlay
        to the game behind it (True) or is received again (False). The window is
        already layered via its WinForms Opacity, so the transparent bit alone
        decides hit-testing. Only call this when the state actually changes."""
        GWL_EXSTYLE, WS_EX_TRANSPARENT = -20, 0x00000020
        style = self.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        new = (style | WS_EX_TRANSPARENT) if enabled else (style & ~WS_EX_TRANSPARENT)
        if new != style:
            self.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)

    def capture(self, hwnd):
        """The overlay window's pixels as a top-down 32-bit BGRA buffer, or None when it cannot be read.
        PrintWindow with PW_RENDERFULLCONTENT (Windows 8.1 and later) renders what DWM composes for the
        window, so the WebView2 child's content is in it; its own opacity is not applied."""
        rect = self.w.RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0 or width * height > 4_000_000:
            return None
        screen = self.user32.GetDC(None)
        if not screen:
            return None
        memory = bitmap = previous = None
        try:
            memory = self.gdi32.CreateCompatibleDC(screen)
            bitmap = self.gdi32.CreateCompatibleBitmap(screen, width, height)
            if not memory or not bitmap:
                return None
            previous = self.gdi32.SelectObject(memory, bitmap)
            if not self.user32.PrintWindow(hwnd, memory, 2):      # PW_RENDERFULLCONTENT
                return None
            info = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=width, biHeight=-height,
                                     biPlanes=1, biBitCount=32, biCompression=0)
            buffer = ctypes.create_string_buffer(width * height * 4)
            lines = self.gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), 0)
            return buffer.raw if lines == height else None
        finally:
            if previous:
                self.gdi32.SelectObject(memory, previous)
            if bitmap:
                self.gdi32.DeleteObject(bitmap)
            if memory:
                self.gdi32.DeleteDC(memory)
            self.user32.ReleaseDC(None, screen)


class _MacOS(_NativeOverlay):
    """Scaffold for native overlay control on macOS. Not yet implemented, so
    ``supported`` is False and the overlay runs in its browser/plain-window fallback.

    To implement (via pyobjc, which pywebview already uses for its Cocoa window):
      * game_window / monitors / virtual_screen: ``Quartz.CGWindowListCopyWindowInfo``
        for the AION 2 window bounds, ``AppKit.NSScreen.screens()`` for monitor frames
        (note Cocoa's bottom-left origin — flip Y to match the Windows top-left frame
        this interface uses).
      * move: ``NSWindow.setFrameOrigin_`` (Y-flipped).
      * always-on-top: ``NSWindow.setLevel_(NSStatusWindowLevel)`` and
        ``NSWindowCollectionBehaviorCanJoinAllSpaces``.
      * set_click_through: ``NSWindow.setIgnoresMouseEvents_`` for the whole window, or
        an AppKit hit-test against the control rects for the dynamic (hover-only) mode.
      * cursor_in_client: ``NSEvent.mouseLocation`` converted to window coordinates.
    Flip ``supported = True`` once these are implemented and validated on a real Mac."""

    platform = "darwin"
    supported = False


class _Linux(_NativeOverlay):
    """Scaffold for native overlay control on Linux (X11; Wayland is more restricted).
    Not yet implemented, so ``supported`` is False and the overlay uses its fallback.

    To implement (X11, e.g. via python-xlib):
      * game_window / monitors / virtual_screen: find the AION 2 window and read its
        geometry; enumerate monitors via the RandR/Xinerama extension.
      * move: ``XMoveWindow`` / configure the window.
      * always-on-top: set ``_NET_WM_STATE_ABOVE`` (EWMH).
      * set_click_through: apply an empty input shape with the XShape extension
        (``XShapeCombineRectangles`` on ShapeInput), or an input region covering only
        the control rects for the hover-only mode.
      * cursor_in_client: ``XQueryPointer`` translated into window coordinates.
    Wayland generally forbids global always-on-top/input-shape from an app, so this may
    stay X11-only. Flip ``supported = True`` once implemented and validated on Linux."""

    platform = "linux"
    supported = False


def native_overlay() -> _NativeOverlay | None:
    """The native overlay backend for this OS, or None when the platform has no
    implemented backend (the overlay then runs in its browser/plain-window fallback).
    Single source of truth for platform selection; constructing the Windows backend can
    still fail (missing user32 symbols), in which case this returns None."""
    import sys as _sys
    cls = {"win32": _Windows, "darwin": _MacOS, "linux": _Linux}.get(
        "linux" if _sys.platform.startswith("linux") else _sys.platform)
    if cls is None:
        return None
    try:
        backend = cls()
    except Exception:
        _LOG.exception("Could not initialize the %s overlay backend", getattr(cls, "platform", "native"))
        return None
    return backend if backend.supported else None


#: How much of an overlay larger than the game window stays on the game (px): its header, the part a press moves it
#: by. The whole of a smaller overlay stays on the game, as it always has.
FOLLOW_KEEP = 120


def _follow_room(span, size):
    """How far the overlay's near edge may sit from the game window's along one axis: the whole overlay inside the
    game window when it fits, else its first FOLLOW_KEEP pixels. Until 0.2.373 an overlay larger than the game had
    no room at all and was held at the game's top or left edge, so it could not be moved there (a player's panel
    open in a windowed game)."""
    return span - size if size <= span else max(0, span - FOLLOW_KEEP)


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
    dx = max(0, min(dx, _follow_room(width, overlay_width)))
    if expand_up:
        ny = top + max(0, height - overlay_height - 48)
    else:
        dy = max(0, min(dy, _follow_room(height, overlay_height)))
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


def _follow_move(api, previous, bounds, rect, snap=False, expand_up=False):
    """Where one tick of following the game moves the overlay, or None to leave it where it is. While the player
    moves the window (begin_drag) it goes where the cursor takes it: until 0.2.373 the follow loop pulled it back
    inside the game four times a second as it moved, and an overlay with no room left (a player's panel open) could
    not be moved at all. The spot a move ends at is the new offset from the game, kept inside it from the next tick."""
    if api._dragging:
        return None
    position = _follow_position(previous, bounds, rect, snap=snap, expand_up=expand_up)
    return position if position != tuple(rect[:2]) else None


def _norm_monitors(layout):
    """A list of monitor rectangles as clean (left, top, width, height) int tuples,
    dropping anything malformed or non-positive in size."""
    out = []
    for m in layout or []:
        try:
            left, top, width, height = (int(v) for v in m)
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0:
            out.append((left, top, width, height))
    return out


def resolve_remembered_position(saved_x, saved_y, saved_layout, monitors, margin=40):
    """Where to re-open a remembered overlay, or ``None`` to fall back to game-anchoring.

    ``saved_x``/``saved_y`` is the overlay's top-left when it was last dragged,
    ``saved_layout`` the monitor rectangles it was saved under, and ``monitors`` the
    current ones (each ``(left, top, width, height)``). Keeping a position by the whole
    virtual-desktop box alone is wrong on multi-monitor setups: rearranging or
    renumbering screens keeps the box but moves the sub-screens, so the old absolute
    coordinates land on the wrong monitor. So:

    * **layout unchanged** → keep the exact saved position (if its top-left still lands
      on a monitor, leaving a grabbable ``margin``);
    * **layout changed but the monitor it was on still exists** (same size) → re-place it
      at the same offset within that monitor, so a rearranged setup restores correctly;
    * **otherwise** → ``None`` (never restore a stale, off-screen position).

    Pure and side-effect free; the native layer supplies the monitor rectangles.
    """
    mons = _norm_monitors(monitors)
    if not mons:
        return None
    try:
        sx, sy = int(saved_x), int(saved_y)
    except (TypeError, ValueError):
        return None

    def on_monitor(mon, x, y):
        left, top, width, height = mon
        return left <= x <= left + width - margin and top <= y <= top + height - margin

    saved = _norm_monitors(saved_layout)
    if saved:
        if sorted(saved) == sorted(mons):
            return (sx, sy) if any(on_monitor(m, sx, sy) for m in mons) else None
        # Layout changed: re-seat within the same monitor if it still exists.
        host = next((m for m in saved if m[0] <= sx < m[0] + m[2] and m[1] <= sy < m[1] + m[3]), None)
        if host is not None:
            off_x, off_y = sx - host[0], sy - host[1]
            same = [m for m in mons if m[2] == host[2] and m[3] == host[3]]
            pick = next((m for m in same if (m[0], m[1]) == (host[0], host[1])), None) or (same[0] if same else None)
            if pick is not None:
                nx = min(max(pick[0] + off_x, pick[0]), pick[0] + pick[2] - margin)
                ny = min(max(pick[1] + off_y, pick[1]), pick[1] + pick[3] - margin)
                return (nx, ny)
        return None
    # No saved layout (older data): accept the position if it lands on any monitor.
    return (sx, sy) if any(on_monitor(m, sx, sy) for m in mons) else None


def _overlay_prefs() -> dict:
    """Native overlay preferences read from the user's settings (defaults keep the
    historical behaviour). Read once at launch, so changes apply on reopen."""
    # always_visible defaults to True: the overlay stays on top even when the game
    # is not the foreground window, so focusing another overlay, the app window, or
    # a game loot/reward popup never hides it. The read below uses each key's own
    # default, so an absent key keeps True here and False for the others.
    prefs = {"resizable": False, "snap_edge": False, "expand_up": False, "always_visible": True,
             "remember_position": True, "click_through": False}
    # Remembered drag positions (per overlay), restored at launch instead of
    # re-anchoring to the game window. Machine/monitor-specific, so they live only
    # in ui.json (never the shareable settings backup).
    positions = {"meter": None, "party": None, "radar": None, "pets": None, "players": None}
    try:
        from .paths import data_file, read_json
        if data_file("ui.json").exists():
            ui = read_json("ui.json")
            for key in prefs:
                prefs[key] = ui.get("overlay_" + key, prefs[key]) is True

            def _pos(px, py, pl):
                x, y = ui.get(px), ui.get(py)
                if not (isinstance(x, int) and not isinstance(x, bool)
                        and isinstance(y, int) and not isinstance(y, bool)):
                    return None
                layout = ui.get(pl) if isinstance(ui.get(pl), list) else None
                return {"xy": (int(x), int(y)), "layout": layout}
            positions["meter"] = _pos("overlay_pos_x", "overlay_pos_y", "overlay_pos_layout")
            positions["party"] = _pos("overlay_party_pos_x", "overlay_party_pos_y", "overlay_party_pos_layout")
            positions["radar"] = _pos("overlay_radar_pos_x", "overlay_radar_pos_y", "overlay_radar_pos_layout")
            positions["pets"] = _pos("overlay_pets_pos_x", "overlay_pets_pos_y", "overlay_pets_pos_layout")
            positions["players"] = _pos("overlay_players_pos_x", "overlay_players_pos_y", "overlay_players_pos_layout")
    except Exception:
        pass
    prefs["positions"] = positions
    return prefs


class _OverlayAPI:
    def __init__(self, min_width: int = 260):
        self._window = None
        self._opacity = 0.72
        self._size = None
        self._min_width = min_width          # the radar's small window may be narrower than the meter's
        self._windows_ready = False
        self._locked = False
        # Click-through: when on, the window ignores mouse input (WS_EX_TRANSPARENT)
        # so clicks reach the game, EXCEPT while the cursor is over one of the
        # interactive rects (the overlay's buttons/sliders), which stay usable. The
        # rects are pushed from the web page in device pixels relative to the client
        # area; the hit-test loop reads them and toggles the style. Assigned as whole
        # new objects so the loop thread never sees a half-updated value.
        self._click_through = False
        self._interactive = ()
        self._hover_interact = False   # with click-through on, resting the pointer on the overlay opens it (0.2.371)
        self._dragging = False      # a native move of the window is following the cursor (begin_drag)
        self._drag_thread = None    # the thread that moves it
        self._drag_stop = None      # set once the press that began the move is over (end_drag, or a new press)
        self._drag_seq = None       # the page's number for that press
        self._drags_ended = collections.deque(maxlen=16)   # presses the page has said are over: an end can come first
        self._drag_lock = threading.Lock()
        self._drag_unread_said = False   # overlay.log has said that Windows answers the button's state with 0
        # The window's shape (0.2.368): in the "top portion only" and "none" background modes the page reports
        # the rectangles it draws (the header panel, each row, the panels under the rows) and the host clips the
        # window to them, so the game shows through everywhere else and takes the clicks there. The host paints
        # an opaque card-coloured window (see _configure_windows), which is why the page's transparent card
        # alone changed nothing on screen. None = the whole window.
        self._shape = None
        # What overlay.log last said of the shape and when it said it, so a shape that changes every poll (a
        # readout that grew a digit) is logged when its kind changes, at most six times a minute. Whether the
        # last region Windows reported holding, and what the log said of the window's backdrop.
        self._shape_said, self._shape_said_times = None, []
        self._shape_errors_said_at = 0.0
        self._region_said = None
        self._backdrop_said = None
        self._hwnd = None
        self._user32_dll = None
        # The watchdog's state (overlay_health): whether the tracking loop has the window shown, a
        # WebView2 process failure waiting to be acted on, reloads the app asked for, and whether the
        # process is ending to be started again.
        self.url = ""
        self.log = OverlayLog(os.devnull)
        self._visible = True
        self._failure = None
        self._hooked = False
        self._reload_requested = 0
        self._restart = False
        # The app's address and whether the window waits for it (0.2.390): the window opens on its own waiting card
        # (WAITING_HTML) and goes to the app's page only once the app answers. A load that fails anyway, or a heal
        # step that would load the page while the app does not answer, puts the card back and waits again, so the
        # browser's own error page ("127.0.0.1 refused to connect") never shows. The parent watch closes the
        # overlay meanwhile once the app is gone for good.
        self.app_base = None
        self._waiting = False
        self._wait_lock = threading.Lock()
        self._closed = None
        self._navigation_hooked = False
        self._ever_shown = False
        self._load_failures = 0       # failed loads of the page in a row: the waiter waits longer after each

    def hook_process_failures(self):
        """Subscribe to WebView2's ProcessFailed once its core exists (it is created after the window is
        shown). Called from the probe thread, which has a timeout, never from the watchdog itself."""
        if self._hooked or self._window is None:
            return

        def hook():
            core = getattr(self._window.native.webview, "CoreWebView2", None)
            if core is None:
                return
            core.ProcessFailed += self._on_process_failed
            self._hooked = True

        try:
            self._on_ui(hook)
        except Exception:
            pass

    def _on_process_failed(self, sender, args):
        try:
            kind = str(args.ProcessFailedKind)
            detail = f"{kind} (reason {getattr(args, 'Reason', '?')}, exit code {getattr(args, 'ExitCode', '?')})"
        except Exception:
            kind = detail = "an unknown process failure"
        self._failure = (kind, detail)

    def prepare_navigation(self):
        """Turn WebView2's own error page off and hear how each load ends (0.2.390), once its core exists (shortly
        after the window is made). Returns whether it is in place. With the error page off, a load that fails shows
        nothing rather than "can't reach this page", and ``_on_navigation_completed`` puts the waiting card there."""
        if self._navigation_hooked or self._window is None:
            return self._navigation_hooked

        def hook():
            core = getattr(self._window.native.webview, "CoreWebView2", None)
            if core is None:
                return
            try:
                core.Settings.IsBuiltInErrorPageEnabled = False
            except Exception as err:
                self.log.write(f"the browser's error page stays on ({type(err).__name__}: {err})")
            core.NavigationCompleted += self._on_navigation_completed
            self._navigation_hooked = True

        try:
            self._on_ui(hook)
        except Exception as err:
            self.log.write(f"loads not followed ({type(err).__name__}: {err})")
        return self._navigation_hooked

    def _on_navigation_completed(self, sender, args):
        """A load of the app's page that failed (the app gone, or not answering yet): the waiting card, and the page
        again once the app answers. Runs on the UI thread, so it only starts the waiter. A load another load replaced
        (``OperationCanceled``: the waiting card's own, as the page loads over it) is no failure."""
        try:
            source = str(getattr(sender, "Source", "") or "")
            ours = not self.app_base or source.startswith(self.app_base)
            if bool(args.IsSuccess):
                if ours:
                    self._load_failures = 0
                return
            status = str(getattr(args, "WebErrorStatus", "an error"))
            if self._waiting or not ours or status.endswith("OperationCanceled"):
                return
        except Exception:
            return
        self._load_failures += 1
        self.wait_for_app(f"the page did not load ({status})")

    def wait_for_app(self, reason, show=True):
        """Show the waiting card and load the app's page once the app answers; one waiter at a time. Returns
        whether this call started the wait."""
        with self._wait_lock:
            if self._waiting:
                return False
            self._waiting = True
        self.log.write(f"waiting for the app: {reason}")
        if show:
            try:
                self._window.load_html(WAITING_HTML)
            except Exception as err:
                self.log.write(f"the waiting card did not show ({type(err).__name__}: {err})")
        threading.Thread(target=self._await_app, daemon=True, name="overlay-wait-for-app").start()
        return True

    def _await_app(self, interval=1.0, answers=None):
        answers = answers or app_answers
        closed = self._closed
        # A page that failed to load more than once in a row while the app answered waits longer each time (2, 4, ...
        # up to 30 s), so a page the app cannot serve is not loaded every second.
        backoff = min(30.0, interval * 2 ** (self._load_failures - 1)) if self._load_failures > 1 else 0.0
        if backoff and closed is not None:
            closed.wait(backoff)
        while not (closed is not None and closed.is_set()):
            if answers(self.app_base):
                self.open_page("the app answers")
                return
            if closed is not None:
                closed.wait(interval)
            else:
                time.sleep(interval)

    def open_page(self, why):
        """Load the app's page (the app answered just now)."""
        self.log.write(f"loading the page: {why}")
        with self._wait_lock:
            self._waiting = False         # before the load: its failure, if it fails, starts a new wait
        self._reload_requested = 0        # a fresh load is the reload the app asked for meanwhile
        try:
            self._window.load_url(self.url)
        except Exception as err:
            self.log.write(f"the page did not load ({type(err).__name__}: {err})")

    def open_app(self, first_wait=3.0, answers=None, clock=time.monotonic, sleep=time.sleep):
        """The window's first load (0.2.390): the app's page as soon as the app answers, within ``first_wait``
        seconds; otherwise the waiting card the window opened on stays, and a waiter loads the page once the app
        answers. Until then the window went to the app's address at once and showed the browser's error page
        whenever nothing listened there yet or any more. Returns whether the page was loaded."""
        answers = answers or app_answers
        deadline = clock() + first_wait
        while True:
            if answers(self.app_base):
                self.open_page("the app answers")
                return True
            if clock() >= deadline or (self._closed is not None and self._closed.is_set()):
                break
            sleep(0.25)
        self.wait_for_app(f"the app did not answer in {first_wait:.0f} s", show=False)
        return False

    def set_locked(self, value):
        # Screenshot lock: keep the overlay visible and stationary while locked.
        self._locked = bool(value)

    def set_click_through(self, enabled):
        # Called from the overlay page when the setting changes. The hit-test loop
        # (Windows) picks this up and starts/stops passing clicks through.
        self._click_through = bool(enabled)

    def set_hover_interact(self, enabled):
        """Called from the overlay page (0.2.371): with click-through on, the pointer resting on the overlay for
        HOVER_INTERACT_S seconds makes the whole overlay take clicks until the pointer leaves it."""
        self._hover_interact = bool(enabled)

    def _say_hover(self, state):
        """Tell the page how the hover stands ("arming", "open" or "off") so the card can show it. Off the loop's
        thread: the loop never waits on the page."""
        window = self._window
        if window is None:
            return
        script = f"window.A2OverlayHover && window.A2OverlayHover({json.dumps(state)})"
        threading.Thread(target=lambda: _quietly(window.evaluate_js, script), daemon=True,
                         name="overlay-hover-say").start()

    def begin_drag(self, seq=None):
        """Called by the page when a press lands on the card outside its controls (0.2.371): the window follows the
        cursor from here, in screen pixels, until the press is over. pywebview's own dragging moved the window from
        the page's mouse events instead, which stop once the cursor outruns the window, so a release outside it was
        never seen and the window went on chasing the cursor; and it placed the window from a position in
        display-independent pixels, so on a second display scaled differently the window jumped. ``seq`` is the
        page's number for the press, which its end_drag names. A new press ends any move before it; the screenshot
        lock keeps the window where it is."""
        if sys.platform != "win32" or self._window is None or self._locked:
            return
        with self._drag_lock:
            if seq is not None and seq in self._drags_ended:
                return                     # its end came first: the bridge runs each call on a thread of its own
            if self._drag_stop is not None:
                self._drag_stop.set()
            stop = self._drag_stop = threading.Event()
            self._drag_seq = seq
            self._dragging = True
            self._drag_thread = threading.Thread(target=self._drag, args=(stop,), daemon=True, name="overlay-drag")
            self._drag_thread.start()

    def end_drag(self, seq=None):
        """Called by the page when the press that began a move is over (its pointerup or pointercancel): the move ends
        there (0.2.374). Until then only the button's state ended it, read with GetAsyncKeyState, which Windows
        answers with 0 (the button up) for a program that is not elevated whenever the window in front belongs to
        one that is (UI Privilege Isolation): the overlay never takes the foreground (its windows do not activate),
        so over a game run as administrator every move ended as it began and no overlay window would move."""
        with self._drag_lock:
            if seq is not None:
                self._drags_ended.append(seq)
            if self._drag_stop is not None and (seq is None or seq == self._drag_seq):
                self._drag_stop.set()

    def _drag(self, stop=None, poll=0.008, limit=600.0, threshold=4):
        """Move the window with the cursor until ``stop`` is set (the page's end_drag, or a new press) or the primary
        button, once read down, reads up. The button alone cannot say the press is over: Windows answers its state
        with 0 under an elevated window in front, so a button never read down leaves the end to the page. The window
        moves once the cursor has gone ``threshold`` pixels from the press, so a click never nudges it."""
        stop = stop if stop is not None else threading.Event()
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetAsyncKeyState.restype = ctypes.c_short
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            hwnd = ctypes.c_void_p(self._window.native.Handle.ToInt64())
            button = 0x02 if user32.GetSystemMetrics(23) else 0x01     # the primary button: right when swapped
            cursor, rect = (ctypes.c_long * 2)(), (ctypes.c_long * 4)()
            user32.GetCursorPos(cursor)
            user32.GetWindowRect(hwnd, rect)
            pressed_at = (cursor[0], cursor[1])
            dx, dy = rect[0] - cursor[0], rect[1] - cursor[1]
            where, until = (rect[0], rect[1]), time.monotonic() + limit
            held = moving = False
            while not stop.is_set() and time.monotonic() < until:
                if user32.GetAsyncKeyState(button) & 0x8000:
                    held = True
                elif held:
                    break                                            # read down, now up: the press is over
                user32.GetCursorPos(cursor)
                moving = moving or max(abs(cursor[0] - pressed_at[0]), abs(cursor[1] - pressed_at[1])) >= threshold
                to = (cursor[0] + dx, cursor[1] + dy)
                if moving and to != where:
                    user32.SetWindowPos(hwnd, None, to[0], to[1], 0, 0, 0x0001 | 0x0004 | 0x0010)   # no size, z-order, focus
                    where = to
                stop.wait(poll)
            if moving and not held and not self._drag_unread_said:
                self._drag_unread_said = True
                self.log.write("moving the window: the mouse button reads as up while it is held (Windows answers so "
                               "under a program run as administrator in front), so the overlay page says when each move ends")
        except Exception as err:
            self.log.write(f"moving the window failed: {type(err).__name__}: {err}")
        finally:
            with self._drag_lock:
                if self._drag_stop is stop or self._drag_stop is None:
                    self._dragging = False

    def set_interactive_rects(self, rects):
        # Called from the overlay page with its controls' bounding boxes, each
        # [left, top, right, bottom] in device px relative to the client area.
        parsed = []
        if isinstance(rects, (list, tuple)):
            for r in rects:
                if isinstance(r, (list, tuple)) and len(r) == 4:
                    try:
                        l, t, rt, b = (float(r[0]), float(r[1]), float(r[2]), float(r[3]))
                    except (TypeError, ValueError):
                        continue
                    if rt > l and b > t:
                        parsed.append((l, t, rt, b))
        self._interactive = tuple(parsed)

    def set_window_shape(self, rects):
        """Called from the overlay page with the rectangles it draws, each [left, top, right, bottom] in device
        px relative to the client area, or null for the whole window. Windows clips the window to their union.
        A fifth number rounds that rectangle's corners by that radius (device px): the see-through modes' compact
        layout (0.2.370) draws rounded pieces, and the window takes their outline."""
        parsed = []
        if isinstance(rects, (list, tuple)):
            for r in rects:
                if isinstance(r, (list, tuple)) and len(r) in (4, 5):
                    try:
                        l, t, rt, b = (float(r[0]), float(r[1]), float(r[2]), float(r[3]))
                        radius = float(r[4]) if len(r) == 5 else 0.0
                    except (TypeError, ValueError):
                        continue
                    if rt > l and b > t:
                        box = (int(l), int(t), int(rt + 0.999), int(b + 0.999))
                        corner = min(int(radius + 0.5), (box[2] - box[0]) // 2, (box[3] - box[1]) // 2) if radius > 0 else 0
                        parsed.append(box + (corner,) if corner > 0 else box)
        self._shape = tuple(parsed) if rects is not None and parsed else None
        self._say_shape()
        if self._windows_ready:
            try:
                self._on_ui(self._apply_shape)
            except Exception as err:   # logged, at most every 30 s: a shape that fails fails on every poll
                now = time.monotonic()
                if now - self._shape_errors_said_at >= 30:
                    self._shape_errors_said_at = now
                    self.log.write(f"window shape not applied: {type(err).__name__}: {err}")

    def _say_shape(self):
        """One overlay.log line when the shape's kind changes (the whole window, or how many pieces, with the box
        around them), at most six a minute (0.2.371): the log says what the window was cut to, the first evidence
        when the game does not show between the pieces. A change held back by the limit is said at the next call
        after it, since the kind it would have recorded is left unrecorded."""
        shape = self._shape
        kind = f"{len(shape)} piece{'s' if len(shape) != 1 else ''}" if shape else "the whole window"
        if kind == self._shape_said:
            return
        now = time.monotonic()
        self._shape_said_times = [t for t in self._shape_said_times if now - t < 60]
        if len(self._shape_said_times) >= 6:
            return
        self._shape_said_times.append(now)
        self._shape_said = kind
        box = f" within [{min(p[0] for p in shape)}, {min(p[1] for p in shape)}, {max(p[2] for p in shape)}, " \
              f"{max(p[3] for p in shape)}]" if shape else ""
        self.log.write(f"window shape: {kind}{box}")

    def _apply_shape(self):
        native = self._window.native
        if not self._shape:
            native.Region = None
        else:
            try:
                native.Region = self._shape_region(rounded=True)
            except Exception as err:   # rounded corners are a nicety: never lose the shape over them
                self.log.write(f"rounded window shape failed ({type(err).__name__}: {err}); using square corners")
                native.Region = self._shape_region(rounded=False)
        self._check_region(bool(self._shape))   # after the region: a host that cannot read it back keeps it

    def _user32(self):
        if self._user32_dll is None:
            self._user32_dll = ctypes.WinDLL("user32", use_last_error=True)
            self._user32_dll.GetWindowRgnBox.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self._user32_dll.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        return self._user32_dll

    def _region_held(self, hwnd):
        """The region Windows holds for the window (GetWindowRgnBox): whether there is one, and its box."""
        box = (ctypes.c_long * 4)()
        kind = self._user32().GetWindowRgnBox(ctypes.c_void_p(hwnd), box)
        return kind in (2, 3), list(box)

    def _check_region(self, expected):
        """Read back the region Windows holds for the window and log it when that changes (0.2.371). A shape that
        left no region behind is set again through user32 directly, in case the WinForms property did not reach
        the window."""
        try:
            hwnd = self._window.native.Handle.ToInt64()
            held, box = self._region_held(hwnd)
        except Exception as err:
            if self._region_said != "unread":
                self._region_said = "unread"
                self.log.write(f"the window region could not be read back ({type(err).__name__}: {err})")
            return
        note = ""
        if expected and not held:
            try:
                self._raw_region(hwnd)
                held, box = self._region_held(hwnd)
                note = " after setting it again through user32"
            except Exception as err:
                note = f"; setting it through user32 failed ({type(err).__name__}: {err})"
        state = (expected, held)
        if state != self._region_said:
            self._region_said = state
            said = f"within {box}" if held else "none" + (" although the page sent a shape" if expected else ", the whole window")
            self.log.write(f"window region: {said}{note}")

    def _raw_region(self, hwnd):
        """The shape's union as a GDI region, handed to the window with SetWindowRgn (the window owns it after)."""
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        for fn in (gdi32.CreateRectRgn, gdi32.CreateRoundRectRgn):
            fn.restype = ctypes.c_void_p
        gdi32.CombineRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        combined = gdi32.CreateRectRgn(0, 0, 0, 0)
        for piece in self._shape:
            l, t, r, b = piece[:4]
            corner = piece[4] if len(piece) == 5 else 0
            part = gdi32.CreateRoundRectRgn(l, t, r + 1, b + 1, 2 * corner, 2 * corner) if corner else gdi32.CreateRectRgn(l, t, r, b)
            gdi32.CombineRgn(combined, combined, part, 2)   # RGN_OR
            gdi32.DeleteObject(part)
        if not self._user32().SetWindowRgn(ctypes.c_void_p(hwnd), combined, 1):
            gdi32.DeleteObject(combined)
            raise OSError(ctypes.get_last_error(), "SetWindowRgn refused the region")

    def _shape_region(self, rounded):
        """The union of the shape's rectangles as a System.Drawing.Region, a rectangle with a corner radius as a
        rounded rectangle (its four corner arcs) when ``rounded``."""
        from System.Drawing import Rectangle, Region
        region = None
        for piece in self._shape:
            l, t, r, b = piece[:4]
            corner = piece[4] if rounded and len(piece) == 5 else 0
            if corner:
                from System.Drawing.Drawing2D import GraphicsPath
                d = 2 * corner
                part = GraphicsPath()
                part.AddArc(Rectangle(l, t, d, d), 180.0, 90.0)
                part.AddArc(Rectangle(r - d, t, d, d), 270.0, 90.0)
                part.AddArc(Rectangle(r - d, b - d, d, d), 0.0, 90.0)
                part.AddArc(Rectangle(l, b - d, d, d), 90.0, 90.0)
                part.CloseFigure()
            else:
                part = Rectangle(l, t, r - l, b - t)
            if region is None:
                region = Region(part)
            else:
                region.Union(part)
        return region

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
            # host instead so the visible overlay accepts mouse input. The host is
            # the card's own colour: the card fills the window, and an edge pixel
            # left by rounding then blends in instead of showing as a dark frame.
            background = Color.FromArgb(27, 32, 42)
            native.BackColor = background
            native.TransparencyKey = Color.Empty
            native.webview.DefaultBackgroundColor = background
            native.Opacity = self._opacity
            self._hwnd = native.Handle.ToInt64()
            self._drop_backdrop()
            # pywebview asks for the backdrop again on every change of the user's preferences (its handler of this
            # same event): drop it again just after, and the watchdog checks it every few seconds too.
            try:
                from Microsoft.Win32 import SystemEvents
                self._preference_handler = lambda *_: threading.Timer(0.1, self._drop_backdrop).start()
                SystemEvents.UserPreferenceChanged += self._preference_handler
            except Exception as err:
                self.log.write(f"preference changes not followed ({type(err).__name__}: {err})")

        self._on_ui(configure)
        self._windows_ready = True
        self.log.write(f"window set up ({self._host_facts()}), opacity {self._opacity:.2f}")
        if self._shape:
            self._on_ui(self._apply_shape)

    def _drop_backdrop(self):
        """No system backdrop behind the window (DWMWA_SYSTEMBACKDROP_TYPE = DWMSBT_NONE, 0.2.371). When Windows runs
        apps dark, pywebview asks DWM for a Mica backdrop on every window it makes (update_title_bar_theme), and DWM
        paints that backdrop, a dark grey wherever Mica itself cannot show, across the whole window rectangle: outside
        the window's region too, so the see-through modes showed a dark box around their pieces on a dark desktop
        while the region was in place and the clicks went through to the game. Safe from any thread; on a Windows
        without system backdrops the call is refused and nothing changes."""
        if not self._hwnd:
            return
        try:
            dwm, hwnd, kind = ctypes.windll.dwmapi, ctypes.c_void_p(self._hwnd), ctypes.c_int(0)
            if dwm.DwmGetWindowAttribute(hwnd, 38, ctypes.byref(kind), ctypes.sizeof(kind)) == 0 and kind.value == 1:
                said = "none"                              # already none: nothing to ask DWM again
            else:
                kind.value = 1
                result = dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(kind), ctypes.sizeof(kind)) & 0xFFFFFFFF
                said = "none" if result == 0 else f"left as it is (DwmSetWindowAttribute 0x{result:08x})"
        except Exception as err:
            said = f"not set ({type(err).__name__}: {err})"
        if said != self._backdrop_said:
            self._backdrop_said = said
            self.log.write(f"window backdrop: {said}")

    def _host_facts(self):
        """What overlay.log needs to tell one player's window from another's (0.2.371): the pywebview and Windows
        versions, the window's DPI and whether Windows runs apps dark (pywebview then asks for a dark frame and a
        Mica backdrop on the window)."""
        facts = []
        try:
            from importlib.metadata import version
            facts.append(f"pywebview {version('pywebview')}")
        except Exception:
            pass
        try:
            v = sys.getwindowsversion()
            facts.append(f"Windows {v.major}.{v.minor}.{v.build}")
        except Exception:
            pass
        try:
            hwnd = self._window.native.Handle.ToInt64()
            facts.append(f"{ctypes.windll.user32.GetDpiForWindow(ctypes.c_void_p(hwnd))} DPI")
        except Exception:
            pass
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                facts.append("dark apps" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0 else "light apps")
        except Exception:
            pass
        return ", ".join(facts) or "no details"

    def set_opacity(self, value):
        self._opacity = max(0.2, min(1.0, float(value)))
        if self._windows_ready:
            self._on_ui(lambda: setattr(self._window.native, "Opacity", self._opacity))

    def fit(self, width, height):
        size = (max(self._min_width, min(800, int(width))), max(70, min(800, int(height))))
        if size != self._size:
            self._size = size
            self._window.resize(*size)


class _ParentProcess:
    """The app process that started this overlay, watched so the overlay ends with it (0.2.331).

    On Windows a handle is opened on it while it is alive, so a PID the system hands out again later is
    never mistaken for it; elsewhere the process is our parent, and a parent that has gone leaves us
    reparented. An overlay whose app cannot be identified (no PID in the environment, the handle refused)
    keeps to the address poll alone, as before."""

    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0

    def __init__(self, pid):
        self.pid = int(pid) if pid else None
        self._handle = None
        self._kernel = None
        self._is_parent = False
        if not self.pid:
            return
        if sys.platform == "win32":
            try:
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = ctypes.c_void_p
                kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
                kernel.WaitForSingleObject.restype = ctypes.c_uint32
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                self._handle = kernel.OpenProcess(self.SYNCHRONIZE, False, self.pid) or None
                self._kernel = kernel
            except Exception:
                self._handle = None
        else:
            try:
                self._is_parent = os.getppid() == self.pid
            except Exception:
                self._is_parent = False

    def watched(self) -> bool:
        """Whether the process can be told from a reused PID and so watched at all."""
        return bool(self.pid) and (self._handle is not None or sys.platform != "win32")

    def alive(self) -> bool:
        """False once the process has ended; True while it runs, and when it cannot be watched."""
        if not self.watched():
            return True
        if sys.platform == "win32":
            try:   # signalled (WAIT_OBJECT_0) once the process has ended; a wait that fails is not a verdict
                return self._kernel.WaitForSingleObject(self._handle, 0) != self.WAIT_OBJECT_0
            except Exception:
                return True
        if self._is_parent:
            return os.getppid() == self.pid
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        except Exception:
            return True
        return True


def _end(window, api, why: str, closed: threading.Event, exit=os._exit, grace: float = 5.0) -> None:
    """End the overlay because the app is gone: close the window, and end the process outright if the
    window has not closed within ``grace`` seconds (a hung UI thread cannot close its window)."""
    if api is not None:
        api.log.write(f"closing: {why}")
    try:
        threading.Thread(target=window.destroy, daemon=True, name="overlay-destroy").start()
    except Exception:
        pass
    timer = threading.Timer(grace, lambda: None if closed.is_set() else exit(0))
    timer.daemon = True
    timer.start()


def _watch_parent(app_base: str | None, closed: threading.Event, window, api=None, parent=None, exit=os._exit,
                  interval: float = 2.0) -> None:
    """Close the overlay once the app that launched it is gone, and take the app's commands.

    The overlay is a separate process; if the main window is closed, the app is
    quit, or its process is killed outright, the normal teardown that terminates
    this process can be missed and a stale meter would otherwise stay pinned on
    top forever. The app's process is watched directly (``parent``), so the overlay
    ends within seconds of it on every platform, independent of process-termination
    signals; polling the app's address covers an overlay with no process to watch,
    and an app that runs but no longer serves. The address poll alone was not enough:
    an app launched again within the poll's twelve seconds answered it, and the
    overlay of the previous launch lived on beside the new launch's own (0.2.331).
    The same poll reads the app's command counters: a bumped ``reload_seq`` (Open
    overlay pressed while the overlay is already open) makes the watchdog reload the
    page, which a page that no longer runs its own poll could not do for itself.
    """
    import urllib.request

    status = f"{app_base.rstrip('/')}/api/status" if app_base else None
    commands = f"{app_base.rstrip('/')}/api/overlay/commands" if app_base else None
    misses = 0
    seen = None
    while not closed.wait(interval):
        if parent is not None and not parent.alive():
            _end(window, api, "the app's process has ended", closed, exit)
            return
        if status is None:
            continue
        try:
            with urllib.request.urlopen(status, timeout=2) as response:
                response.read(1)
            misses = 0
        except Exception:
            misses += 1
            if misses >= 6:                 # ~12s unreachable: the app is gone, not just busy
                _end(window, api, "the app has not answered for twelve seconds", closed, exit)
                return
            continue
        if api is None:
            continue
        try:
            with urllib.request.urlopen(commands, timeout=2) as response:
                seq = int(json.loads(response.read(4096).decode("utf-8")).get("reload_seq") or 0)
            if seen is None:
                seen = seq                  # the first reading is the baseline, never a command
            elif seq > seen:
                seen = seq
                api._reload_requested += 1
        except Exception:
            pass


class _Probe(threading.Thread):
    """One look at the page: does it answer (``document.readyState`` straight through WebView2, with no
    pywebview script needed) and, while the window is shown, what the window draws. It runs apart from the
    watchdog so a hang is a timeout there, not a stall."""

    def __init__(self, window, api, win32, shown):
        super().__init__(daemon=True, name="overlay-probe")
        self.window, self.api, self.win32, self.shown = window, api, win32, shown
        self.alive, self.capture = False, None

    def run(self):
        self.api.hook_process_failures()
        try:
            state = self.window.native.browser.evaluate_js("document.readyState", False)
            self.alive = state in ("complete", "interactive")
        except Exception:
            self.alive = False
        self.script = None
        if self.alive:
            try:   # what the page's own script says of itself: "starting" once it runs, "ready" once its startup is through
                self.script = self.window.native.browser.evaluate_js("window.A2OverlayUp || null", False)
            except Exception:
                self.script = None
        if self.alive and self.shown and self.win32 is not None:
            try:
                self.capture = self.win32.capture(self.window.native.Handle.ToInt64())
            except Exception:
                self.capture = None


class _Watchdog:
    """The overlay's watchdog (see ``overlay_health``): each tick asks the page whether it is loaded and,
    while the window is shown, captures the window to see whether it drew anything, then heals in steps
    when it did not. Probes and heal steps run in their own threads with timeouts, so a hung UI thread
    counts as a miss and ends in a restart instead of stalling the watchdog. ``tick`` is separate from
    the loop so it can be exercised with stand-ins."""

    PROBE_TIMEOUT = 6.0
    HEAL_TIMEOUT = 10.0
    #: A page that answers but whose script never reached the end of its startup (its stylesheet or script
    #: refused at launch, see ``overlay.html``'s guard) is reloaded after this many looks (30 s), at most
    #: twice a process and a minute apart: a script that fails every time is left, and logged, not looped.
    SCRIPT_MISSES = 6
    SCRIPT_RELOADS = 2
    SCRIPT_SPACING = 60.0

    def __init__(self, window, api, win32, clock=time.time):
        self.window, self.api, self.win32, self.clock = window, api, win32, clock
        self.policy, self.detector = HealPolicy(), BlankDetector()
        self.probe = None
        self.exit = os._exit
        self.script_misses, self.script_reloads, self.script_last = 0, 0, None

    def tick(self):
        api, now = self.api, self.clock()
        if api._waiting:
            # The waiting card is up (0.2.390): the app does not answer, and its waiter loads the page when it does.
            # Nothing to heal meanwhile, and a reload would only send the window to an address that does not answer.
            self.script_misses = 0
            return None
        action, note = None, ""
        failure, api._failure = api._failure, None
        if failure:
            kind, detail = failure
            api.log.write(f"WebView2 reported {detail}")
            if "Browser" in kind:
                action = self.policy.force(now, "restart", f"WebView2 {kind}")
            elif "Render" in kind:
                action = self.policy.force(now, "reload", f"WebView2 {kind}")
        if action is None and api._reload_requested:
            api._reload_requested = 0
            action = self.policy.force(now, "reload", "the app asked for a reload")
        if action is None:
            if self.probe is None or not self.probe.is_alive():
                self.probe = _Probe(self.window, api, self.win32, api._visible)
                self.probe.start()
            self.probe.join(self.PROBE_TIMEOUT)
            if self.probe.is_alive():
                alive, blank, note = False, None, f"no answer in {self.PROBE_TIMEOUT:.0f} s"
            else:
                probe, self.probe = self.probe, None
                alive = probe.alive
                armed = self.detector.armed
                blank = self.detector.verdict(probe.capture) if alive and probe.shown else None
                fraction = self.detector.last_fraction
                if self.detector.armed and not armed:
                    api.log.write(f"blank detection armed: the window's capture shows content (host colour {fraction:.4f})")
                note = ("the page answered" if alive else "the page did not answer") + (
                    f", host colour {fraction:.4f}" if fraction is not None else "")
                self.script_misses = self.script_misses + 1 if alive and probe.script != "ready" else 0
            action = self.policy.observe(now, alive, blank)
            if action is None and self.script_misses >= self.SCRIPT_MISSES:
                self.script_misses = 0
                if self.script_reloads < self.SCRIPT_RELOADS and (self.script_last is None or now - self.script_last >= self.SCRIPT_SPACING):
                    self.script_reloads += 1
                    self.script_last = now
                    action = self.policy.force(now, "reload", "the page loaded without its script")
                elif self.script_reloads >= self.SCRIPT_RELOADS and self.script_last is not None:
                    api.log.write("the page still runs without its script; not reloading it again")
                    self.script_last = None
        if action:
            api.log.write(f"{action}: {self.policy.reason}" + (f" ({note})" if note else ""))
            self.heal(action)
        return action

    def heal(self, action):
        window, api = self.window, self.api

        def act():
            if action in ("reload", "navigate") and not app_answers(api.app_base):
                # Loading the page now would show the browser's error page (0.2.390): wait for the app instead.
                api.wait_for_app(f"{action} put off: the app does not answer")
                return
            try:
                native = window.native
                if action == "nudge":
                    def nudge():
                        native.webview.Visible = False
                        native.webview.Visible = True
                    api._on_ui(nudge)
                elif action == "reload":
                    def reload():
                        core = getattr(native.webview, "CoreWebView2", None)
                        if core is not None:
                            core.Reload()
                        else:
                            native.browser.load_url(api.url)
                    api._on_ui(reload)
                elif action == "navigate":
                    window.load_url(api.url)
                elif action == "restart":
                    api._restart = True
                    window.destroy()
            except Exception as err:
                api.log.write(f"{action} failed: {type(err).__name__}: {err}")

        worker = threading.Thread(target=act, daemon=True, name="overlay-heal")
        worker.start()
        worker.join(self.HEAL_TIMEOUT)
        if worker.is_alive() and action != "restart":
            api.log.write(f"{action} did not finish in {self.HEAL_TIMEOUT:.0f} s; restarting the overlay")
            action = "restart"
            api._restart = True
            threading.Thread(target=window.destroy, daemon=True, name="overlay-destroy").start()
        if action == "restart":
            # Closing the window ends the process with the restart code; a dead UI thread cannot close it.
            timer = threading.Timer(5.0, lambda: self.exit(RESTART_EXIT_CODE))
            timer.daemon = True
            timer.start()


def _health_loop(window, api, win32, closed: threading.Event) -> None:
    watchdog = _Watchdog(window, api, win32)
    api.log.write("watching the page")
    while not closed.wait(5.0):
        api._drop_backdrop()
        try:
            watchdog.tick()
        except Exception as err:
            api.log.write(f"watchdog error: {type(err).__name__}: {err}")


def _view_key(party) -> str:
    """The window a flag or name means: ``"meter"``, ``"party"``, ``"radar"``, ``"players"`` or ``"pets"``."""
    if isinstance(party, str):
        return party
    return "party" if party else "meter"


def _save_overlay_position(app_base, party, pos, layout=None) -> None:
    """Persist a dragged overlay position to the app (ui.json) via its local API,
    keyed per overlay (``party`` is the window: a flag for the Party-DPS one, or its name,
    ``"radar"`` for the radar's window), so it is restored next launch. ``layout`` is the
    current monitor rectangles, stored alongside so the position can be restored by the
    monitor layout. Best-effort; failures are swallowed so a transient app hiccup never
    disturbs the overlay."""
    if not app_base:
        return
    import json as _json, urllib.request
    view = _view_key(party)
    prefix = {"meter": "overlay_pos", "party": "overlay_party_pos", "radar": "overlay_radar_pos",
              "pets": "overlay_pets_pos", "players": "overlay_players_pos"}[view]
    keys = (prefix + "_x", prefix + "_y")
    layout_key = prefix + "_layout"
    payload = {keys[0]: int(pos[0]), keys[1]: int(pos[1])}
    if layout:
        payload[layout_key] = [[int(v) for v in m] for m in layout]
    body = _json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(app_base.rstrip("/") + "/api/ui", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as response:
            response.read(1)
    except Exception:
        pass


HOVER_INTERACT_S = 5.0          # how long the pointer rests on a click-through overlay before it takes clicks


def _quietly(fn, *args):
    try:
        fn(*args)
    except Exception:
        pass


def _over_overlay(shape, pos) -> bool:
    """Whether a client-area point is over what the overlay draws: anywhere on the window, or with a shape (the
    see-through modes) inside one of its pieces, so the game between the pieces does not count."""
    if pos is None:
        return False
    if not shape:
        return True
    x, y = pos
    return any(piece[0] <= x <= piece[2] and piece[1] <= y <= piece[3] for piece in shape)


class _HoverOpen:
    """Hover-to-interact (0.2.371): the pointer over the overlay for ``hold`` seconds opens it to clicks, and it
    closes again when the pointer leaves. ``update`` answers whether it is open, and the change to tell the page
    ("arming", "open", "off") or None."""

    def __init__(self, hold: float | None = None):
        self.hold, self.since, self.open = HOVER_INTERACT_S if hold is None else hold, None, False

    def update(self, enabled: bool, over: bool, now: float):
        if not (enabled and over):
            was = self.since is not None
            self.since, self.open = None, False
            return False, ("off" if was else None)
        if self.since is None:
            self.since = now
            return False, "arming"
        if not self.open and now - self.since >= self.hold:
            self.open = True
            return True, "open"
        return self.open, None


def _click_through_loop(window, api, win32, closed: threading.Event) -> None:
    """Pass mouse clicks through the overlay to the game while click-through is on,
    except over the overlay's own controls so they stay usable.

    WS_EX_TRANSPARENT makes the *whole* window click-through, so to keep the
    buttons working we poll the cursor (~30 Hz) and drop the transparent bit only
    while the pointer is over one of the interactive rects the web page reports.
    The style is changed on the UI thread and only when the state actually flips,
    so idle cost is a cursor read per tick and nothing else. Windows-only.
    """
    applied = None   # None = untouched; True = transparent (pass-through); False = opaque (interactive)
    hover = _HoverOpen()
    while not closed.wait(0.033):
        try:
            hwnd = window.native.Handle.ToInt64()
            if not api._click_through:
                if applied:                       # was passing clicks through — restore input once
                    api._on_ui(lambda h=hwnd: win32.set_click_through(h, False))
                    applied = False
                _, said = hover.update(False, False, time.monotonic())
                if said:
                    api._say_hover(said)
                continue
            pos = win32.cursor_in_client(hwnd)
            over_control = False
            if pos is not None:
                cx, cy = pos
                for l, t, r, b in api._interactive:
                    if l <= cx <= r and t <= cy <= b:
                        over_control = True
                        break
            # Hover-to-interact: resting on the overlay opens all of it to clicks until the pointer leaves.
            opened, said = hover.update(api._hover_interact, _over_overlay(api._shape, pos), time.monotonic())
            if said:
                api._say_hover(said)
            want_transparent = not (over_control or opened)    # click through everywhere but the controls
            if want_transparent != applied:
                api._on_ui(lambda h=hwnd, v=want_transparent: win32.set_click_through(h, v))
                applied = want_transparent
        except Exception:
            # A transient bridge/window hiccup must never kill the loop.
            continue


def _run_overlay(window, api, app_base: str | None = None, party: bool = False, parent_pid=None) -> None:
    closed = threading.Event()
    window.events.closed += closed.set
    api._closed = closed
    parent = _ParentProcess(parent_pid)
    if app_base or parent.watched():
        threading.Thread(target=_watch_parent, args=(app_base, closed, window, api, parent),
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
        except Exception as err:
            _LOG.exception("Could not configure the native Windows overlay")
            api.log.write(f"window setup failed: {type(err).__name__}: {err}")
        # Opacity/style setup must not disable foreground tracking. native_overlay()
        # is the single platform selector; today only Windows has a supported backend,
        # so on macOS/Linux this stays None and the overlay keeps its fallback.
        try:
            win32 = native_overlay()
        except Exception:
            _LOG.exception("Could not initialize overlay foreground tracking")
        if win32 is not None:
            threading.Thread(target=_click_through_loop, args=(window, api, win32, closed),
                             daemon=True, name="overlay-click-through").start()
        # WebView2's core comes up shortly after the window: its error page off and its loads followed before the
        # window goes to the app (0.2.390).
        for _ in range(50):
            if api.prepare_navigation() or closed.is_set():
                break
            time.sleep(0.1)
    # The window opened on its waiting card: the app's page once the app answers (0.2.390).
    api.open_app()
    window.show()
    api._visible = api._ever_shown = True
    if sys.platform == "win32":
        threading.Thread(target=_health_loop, args=(window, api, win32, closed),
                         daemon=True, name="overlay-watchdog").start()
    prefs = _overlay_prefs()
    snap, expand_up = prefs["snap_edge"], prefs["expand_up"]
    always_visible = prefs["always_visible"]
    # Remember-position: restore the overlay where the user last dragged it instead
    # of following the game window. Off by default (the game-follow behaviour below
    # is unchanged). Windows-only (needs the native window rect).
    remember_position = prefs["remember_position"]
    saved_pos = prefs["positions"].get(_view_key(party))
    last_pos, pending_pos, pending_ticks, anchored = None, None, 0, False
    if win32 and remember_position and saved_pos and saved_pos.get("xy"):
        try:
            hwnd0 = window.native.Handle.ToInt64()
            sx, sy = saved_pos["xy"]
            # Restore by the monitor layout so a rearranged multi-monitor setup lands the
            # overlay back on the right screen. Fall back to the virtual-screen box when
            # per-monitor enumeration is unavailable.
            mons = win32.monitors()
            if not mons:
                vx, vy, vw, vh = win32.virtual_screen()
                mons = [(vx, vy, vw, vh)] if vw > 0 and vh > 0 else []
            place = resolve_remembered_position(sx, sy, saved_pos.get("layout"), mons)
            if place:
                win32.move(hwnd0, *place)
                last_pos = place
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
                visible = api._visible = True
            continue
        if visible != should_show:
            win32.user32.ShowWindow(hwnd, 4 if should_show else 0)  # no activation
            visible = api._visible = should_show
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
            if last_pos is None and saved_pos is None and not anchored:
                # First run with nothing saved yet: place the overlay near the game
                # window once (the historical default anchor) so it starts in a sane
                # spot, record it, then stay put. Without this the frameless window
                # would open at the OS default corner and never follow the game.
                anchor = _follow_position(None, game.bounds, win32.rect(hwnd), snap=snap, expand_up=expand_up)
                if _view_key(party) == "pets":
                    # the Pet Tracker window opens with or without the meter: below the meter's corner, not on it
                    anchor = (anchor[0], game.bounds[1] + max(48, int(game.bounds[3] * 0.4)))
                if anchor != cur:
                    win32.move(hwnd, *anchor)
                    cur = anchor
                _save_overlay_position(app_base, party, cur, win32.monitors())
                last_pos, anchored = cur, True
                continue
            if cur != last_pos:
                if cur == pending_pos:
                    pending_ticks += 1
                else:
                    pending_pos, pending_ticks = cur, 0
                if pending_ticks >= 4:
                    _save_overlay_position(app_base, party, cur, win32.monitors())
                    last_pos, pending_pos, pending_ticks = cur, None, 0
            continue
        if game.hwnd != previous_hwnd:
            previous = None
        position = _follow_move(api, previous, game.bounds, win32.rect(hwnd), snap=snap, expand_up=expand_up)
        if position is not None:
            win32.move(hwnd, *position)
        previous, previous_hwnd = game.bounds, game.hwnd


def _log_path():
    try:
        from .paths import logs_dir
        return logs_dir() / "overlay.log"
    except Exception:
        return os.path.join(os.path.expanduser("~"), "aion2calc-overlay.log")


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
    # The overlay URL is the app's own /overlay page (optionally ?view=party, ?view=radar for the Hidden Cube
    # radar's own small window, or ?view=pets for the Pet Tracker window); its base is the app to watch,
    # derived without the path/query.
    app_base = url.split("/overlay")[0] if "/overlay" in url else None
    prefs = _overlay_prefs()
    party = ("party" if "view=party" in url else "radar" if "view=radar" in url
             else "pets" if "view=pets" in url else "players" if "view=players" in url else "meter")
    try:                                 # the app that started this overlay, to end with it (overlay_launch sets it)
        parent_pid = int(os.environ.get("AION2CALC_PARENT_PID") or 0) or None
    except ValueError:
        parent_pid = None
    log = OverlayLog(_log_path(), "overlay" if party == "meter" else f"overlay[{party}]")
    # Never a browser window (0.2.390): a window that cannot open ends with UNAVAILABLE_EXIT_CODE, and the app lets
    # the page's own small window stand in. The overlay used to open its address in the default browser instead, a
    # full-size window with a title bar, and when that came as the app was going away (an error while the window
    # closed) the browser showed "127.0.0.1 refused to connect".
    try:
        import webview
    except Exception as err:
        log.write(f"cannot open: pywebview is not available ({type(err).__name__}: {err})")
        print(f"The native overlay needs pywebview ({type(err).__name__}: {err}).")
        return UNAVAILABLE_EXIT_CODE
    api = None
    try:
        min_width = {"radar": 180, "pets": 240}.get(party, 260)
        api = _OverlayAPI(min_width=min_width)
        api.url, api.app_base, api.log = url, app_base, log
        api.log.write(f"started (pid {os.getpid()})")
        # The card moves the window through begin_drag (0.2.371), not pywebview's drag regions. The window opens on
        # its own waiting card at its own size, and goes to the app's page once the app answers (0.2.390).
        title ={"meter": "Aion 2 Calc Overlay", "party": "Aion 2 Calc Party Overlay", "radar": "Aion 2 Calc Radar Overlay",
                 "pets": "Aion 2 Calc Pet Tracker", "players": "Aion 2 Calc Player Cards"}[party]
        window = webview.create_window(title, html=WAITING_HTML, frameless=True, easy_drag=False,
                                       shadow=False, on_top=True, hidden=True, focus=False,
                                       transparent=sys.platform != "win32", background_color="#010203",
                                       width=a.width, height=a.height, min_size=(min_width, 70),
                                       resizable=bool(prefs["resizable"]) and party not in ("radar", "pets"), js_api=api)
        api._window = window
        webview.start(_run_overlay, args=(window, api, app_base, party, parent_pid),
                      gui="edgechromium" if sys.platform == "win32" else None)
        if api._restart:
            api.log.write("ending so the app starts the overlay again")
            return RESTART_EXIT_CODE
    except Exception as err:
        log.write(f"the window failed: {type(err).__name__}: {err}")
        if api is not None and api._restart:
            return RESTART_EXIT_CODE
        if api is not None and api._ever_shown:
            return 0                     # it ran, then failed as it closed: nothing to open again
        print(f"Could not open the overlay ({type(err).__name__}: {err}).")
        return UNAVAILABLE_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
