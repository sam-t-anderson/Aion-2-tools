"""The compact native meter / raid-plan overlay (or a browser fallback)."""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import json
import logging
import ntpath
import os
import sys
import threading
import time
import webbrowser

from .overlay_health import RESTART_EXIT_CODE, BlankDetector, HealPolicy, OverlayLog


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
    positions = {"meter": None, "party": None, "radar": None}
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

    def set_locked(self, value):
        # Screenshot lock: keep the overlay visible and stationary while locked.
        self._locked = bool(value)

    def set_click_through(self, enabled):
        # Called from the overlay page when the setting changes. The hit-test loop
        # (Windows) picks this up and starts/stops passing clicks through.
        self._click_through = bool(enabled)

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

        self._on_ui(configure)
        self._windows_ready = True

    def set_opacity(self, value):
        self._opacity = max(0.2, min(1.0, float(value)))
        if self._windows_ready:
            self._on_ui(lambda: setattr(self._window.native, "Opacity", self._opacity))

    def fit(self, width, height):
        size = (max(self._min_width, min(800, int(width))), max(70, min(800, int(height))))
        if size != self._size:
            self._size = size
            self._window.resize(*size)


def _watch_parent(app_base: str, closed: threading.Event, window, api=None) -> None:
    """Close the overlay once the app that launched it is gone, and take the app's commands.

    The overlay is a separate process; if the main window is closed, the app is
    quit, or its process is killed outright, the normal teardown that terminates
    this process can be missed and a stale meter would otherwise stay pinned on
    top forever. Polling the app keeps the overlay's lifetime tied to the app on
    every platform, independent of process-termination signals. The same poll reads
    the app's command counters: a bumped ``reload_seq`` (Open overlay pressed while
    the overlay is already open) makes the watchdog reload the page, which a page
    that no longer runs its own poll could not do for itself.
    """
    import urllib.request

    status = f"{app_base.rstrip('/')}/api/status"
    commands = f"{app_base.rstrip('/')}/api/overlay/commands"
    misses = 0
    seen = None
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

    def __init__(self, window, api, win32, clock=time.time):
        self.window, self.api, self.win32, self.clock = window, api, win32, clock
        self.policy, self.detector = HealPolicy(), BlankDetector()
        self.probe = None
        self.exit = os._exit

    def tick(self):
        api, now = self.api, self.clock()
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
            action = self.policy.observe(now, alive, blank)
        if action:
            api.log.write(f"{action}: {self.policy.reason}" + (f" ({note})" if note else ""))
            self.heal(action)
        return action

    def heal(self, action):
        window, api = self.window, self.api

        def act():
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
        try:
            watchdog.tick()
        except Exception as err:
            api.log.write(f"watchdog error: {type(err).__name__}: {err}")


def _view_key(party) -> str:
    """The window a flag or name means: ``"meter"``, ``"party"`` or ``"radar"``."""
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
    prefix = {"meter": "overlay_pos", "party": "overlay_party_pos", "radar": "overlay_radar_pos"}[view]
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
    while not closed.wait(0.033):
        try:
            hwnd = window.native.Handle.ToInt64()
            if not api._click_through:
                if applied:                       # was passing clicks through — restore input once
                    api._on_ui(lambda h=hwnd: win32.set_click_through(h, False))
                    applied = False
                continue
            pos = win32.cursor_in_client(hwnd)
            over_control = False
            if pos is not None:
                cx, cy = pos
                for l, t, r, b in api._interactive:
                    if l <= cx <= r and t <= cy <= b:
                        over_control = True
                        break
            want_transparent = not over_control    # click through everywhere but the controls
            if want_transparent != applied:
                api._on_ui(lambda h=hwnd, v=want_transparent: win32.set_click_through(h, v))
                applied = want_transparent
        except Exception:
            # A transient bridge/window hiccup must never kill the loop.
            continue


def _run_overlay(window, api, app_base: str | None = None, party: bool = False) -> None:
    closed = threading.Event()
    window.events.closed += closed.set
    if app_base:
        threading.Thread(target=_watch_parent, args=(app_base, closed, window, api),
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
    window.show()
    api._visible = True
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
        position = _follow_position(previous, game.bounds, win32.rect(hwnd), snap=snap, expand_up=expand_up)
        if position != win32.rect(hwnd)[:2]:
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
    # The overlay URL is the app's own /overlay page (optionally ?view=party, or ?view=radar for the
    # Hidden Cube radar's own small window); its base is the app to watch, derived without the path/query.
    app_base = url.split("/overlay")[0] if "/overlay" in url else None
    prefs = _overlay_prefs()
    party = "party" if "view=party" in url else "radar" if "view=radar" in url else "meter"
    try:
        import webview
    except Exception:
        webbrowser.open(url)
        return 0
    try:
        api = _OverlayAPI(min_width=180 if party == "radar" else 260)
        api.url = url
        api.log = OverlayLog(_log_path(), "overlay" if party == "meter" else f"overlay[{party}]")
        api.log.write(f"started (pid {os.getpid()})")
        # Stable card content is draggable; JS stops events at the tabs and slider.
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = False
        title = {"meter": "Aion 2 Calc Overlay", "party": "Aion 2 Calc Party Overlay", "radar": "Aion 2 Calc Radar Overlay"}[party]
        window = webview.create_window(title, url, frameless=True, easy_drag=False,
                                       shadow=False, on_top=True, hidden=True, focus=False,
                                       transparent=sys.platform != "win32", background_color="#010203",
                                       width=a.width, height=a.height, min_size=(180 if party == "radar" else 260, 70),
                                       resizable=bool(prefs["resizable"]) and party != "radar", js_api=api)
        api._window = window
        webview.start(_run_overlay, args=(window, api, app_base, party),
                      gui="edgechromium" if sys.platform == "win32" else None)
        if api._restart:
            api.log.write("ending so the app starts the overlay again")
            return RESTART_EXIT_CODE
    except Exception as err:
        print(f"Could not open the overlay ({type(err).__name__}: {err}); using the browser instead.")
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
