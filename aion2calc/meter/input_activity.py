"""When this computer last had keyboard or mouse input in the game, for the live meter's identity rule.

The game sends a cast's end for the local player's presses (and NPCs'), so while the meter has not
named its player yet, a cast-end that arrives when nobody has touched the keyboard or mouse for a
while cannot be the player's own press: that actor goes on the engine's "not my player" list
(``MeterEngine._observe_local_cast``). Windows only: ``GetLastInputInfo`` gives the time of the last
input event and ``GetAsyncKeyState`` whether a mouse button is held (an auto attack held on the left
button repeats with no new input). Neither reads which keys were pressed, and nothing is stored.
The rule only reads input while the game's window is in the foreground: clicks and typing in another
window say nothing about the game. A gamepad's input does not reach ``GetLastInputInfo``; the engine
stops using the rule when its player turns out to be on the list.
"""
from __future__ import annotations

import sys
import time

_MOUSE_BUTTONS = (0x01, 0x02, 0x04, 0x05, 0x06)      # left, right, middle, X1, X2


def _game_in_focus(user32, kernel32) -> bool:
    """Whether the foreground window belongs to the game's process (the overlay's executable names)."""
    import ctypes
    from ctypes import wintypes
    from ..overlay import _is_game_process
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)      # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        return bool(kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))) and _is_game_process(buf.value)
    finally:
        kernel32.CloseHandle(handle)


def read() -> tuple[float | None, bool]:
    """``(wall-clock seconds of the last input or None, whether a mouse button is held)``; ``None``
    (unknown) off Windows and while the game is not the foreground window."""
    if sys.platform != "win32":
        return None, False
    import ctypes
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32.OpenProcess.restype = wintypes.HANDLE
    if not _game_in_focus(user32, kernel32):
        return None, False
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return None, False
    idle_ms = (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    held = any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MOUSE_BUTTONS)
    return time.time() - idle_ms / 1000, held
