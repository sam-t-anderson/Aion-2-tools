"""Draw the live meter inside the game through RivaTuner Statistics Server (RTSS).

RTSS (the statistics server MSI Afterburner ships, also installed on its own) renders an
on-screen display inside Direct3D/Vulkan/OpenGL applications. Third-party programs hand it text
through a named shared-memory block, ``RTSSSharedMemoryV2``, whose layout its SDK header
``RTSSSharedMemory.h`` defines: a header (signature ``'RTSS'``, version ``(major << 16) + minor``,
the OSD slot array's entry size, offset and count, and a global OSD frame counter) followed by OSD
slots of ``szOSD[256]`` (text), ``szOSDOwner[256]`` (owner id) and, from v2.7, ``szOSDEx[4096]``
(extended text). A client claims a free slot by writing its owner id, writes its text, and bumps
the frame counter so the server redraws; slot 0 is left to the primary clients (Afterburner,
Precision). That is all this module does: it writes text into RTSS's own shared memory. RTSS
itself hooks the game to draw -- the meter never touches the game process, injects nothing and
loads nothing into it; running RTSS is the user's choice, under RTSS's own terms.

Windows only and off by default. The shared-memory mechanics are kept behind a small byte-view
interface so the slot logic is unit-tested on any platform against an in-memory block; only
``open_view`` touches Win32.
"""
from __future__ import annotations

import ctypes
import re
import struct
import sys
import threading

MAPPING_NAME = "RTSSSharedMemoryV2"
SIGNATURE = 0x52545353          # 'RTSS' as the DWORD the header compares against
MIN_VERSION = 0x00020000        # v2.0 structure
EXTENDED_TEXT_VERSION = 0x00020007   # szOSDEx exists from v2.7
OWNER = "Aion2Calc"
OSD_TEXT_BYTES = 256
OSD_OWNER_BYTES = 256
OSD_EX_BYTES = 4096
HEADER = struct.Struct("<9I")   # signature, version, appEntrySize, appArrOffset, appArrSize, osdEntrySize, osdArrOffset, osdArrSize, osdFrame
FILE_MAP_ALL_ACCESS = 0x000F001F
WIN32_ERROR_FILE_NOT_FOUND = 2


class RTSSError(RuntimeError):
    pass


class NotRunning(RTSSError):
    """RTSS is not running (its shared memory does not exist)."""


# ---- byte views ----------------------------------------------------------------------------------

class MemoryView:
    """A writable block of bytes, for tests and as the interface the Win32 view implements."""

    def __init__(self, block: bytearray):
        self.block = block

    def read(self, offset: int, size: int) -> bytes:
        if offset < 0 or offset + size > len(self.block):
            raise RTSSError("read outside the shared memory block")
        return bytes(self.block[offset:offset + size])

    def write(self, offset: int, data: bytes) -> None:
        if offset < 0 or offset + len(data) > len(self.block):
            raise RTSSError("write outside the shared memory block")
        self.block[offset:offset + len(data)] = data

    def close(self) -> None:
        pass


class _Win32View(MemoryView):
    """``RTSSSharedMemoryV2`` mapped for the duration of one update (the SDK sample's pattern:
    open, map, write, unmap, close -- so an RTSS restart between updates is harmless)."""

    def __init__(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)   # pragma: no cover - Windows only
        kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        kernel32.OpenFileMappingW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t)
        kernel32.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self._k = kernel32
        self._handle = kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, 0, MAPPING_NAME)
        if not self._handle:
            code = ctypes.get_last_error()
            raise NotRunning("RTSS is not running" if code == WIN32_ERROR_FILE_NOT_FOUND else f"OpenFileMapping failed ({code})")
        self._base = kernel32.MapViewOfFile(self._handle, FILE_MAP_ALL_ACCESS, 0, 0, 0)
        if not self._base:
            code = ctypes.get_last_error()
            kernel32.CloseHandle(self._handle)
            raise RTSSError(f"MapViewOfFile failed ({code})")
        self.block = None   # not a bytearray; read/write go through ctypes

    def read(self, offset: int, size: int) -> bytes:
        return ctypes.string_at(self._base + offset, size)

    def write(self, offset: int, data: bytes) -> None:
        ctypes.memmove(self._base + offset, data, len(data))

    def close(self) -> None:
        if self._base:
            self._k.UnmapViewOfFile(self._base)
            self._base = None
        if self._handle:
            self._k.CloseHandle(self._handle)
            self._handle = None


def supported() -> bool:
    return sys.platform == "win32"


def open_view() -> MemoryView:
    """RTSS's shared memory, or ``NotRunning`` / ``RTSSError``. Windows only."""
    if not supported():
        raise RTSSError("RTSS is available on Windows only")
    return _Win32View()   # pragma: no cover - Windows only


# ---- the shared-memory block -------------------------------------------------------------------

class Header:
    def __init__(self, view: MemoryView):
        (self.signature, self.version, self.app_entry_size, self.app_arr_offset, self.app_arr_size,
         self.osd_entry_size, self.osd_arr_offset, self.osd_arr_size, self.osd_frame) = HEADER.unpack(view.read(0, HEADER.size))
        if self.signature != SIGNATURE:
            raise NotRunning("RTSS shared memory is not initialised (signature mismatch)")
        if self.version < MIN_VERSION:
            raise RTSSError("RTSS shared memory is older than v2.0; update RTSS")
        if not (OSD_TEXT_BYTES + OSD_OWNER_BYTES <= self.osd_entry_size <= 1 << 20) or self.osd_arr_size < 2 or self.osd_arr_size > 64:
            raise RTSSError("RTSS shared memory layout is not one this build understands")

    @property
    def extended_text(self) -> bool:
        return self.version >= EXTENDED_TEXT_VERSION and self.osd_entry_size >= OSD_TEXT_BYTES + OSD_OWNER_BYTES + OSD_EX_BYTES

    def entry_offset(self, index: int) -> int:
        return self.osd_arr_offset + index * self.osd_entry_size


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


def _cbytes(text: str, size: int) -> bytes:
    data = text.encode("utf-8", "replace")[:size - 1]
    while data and data[-1] & 0xC0 == 0x80:   # never cut inside a UTF-8 sequence
        data = data[:-1]
    return data + b"\x00" * (size - len(data))


def find_slot(view: MemoryView, header: Header, owner: str = OWNER) -> int | None:
    """The slot we already own, else the first free one (claimed), else None. Slot 0 is the
    primary clients' and is never touched."""
    for index in range(1, header.osd_arr_size):
        at = header.entry_offset(index)
        if _cstr(view.read(at + OSD_TEXT_BYTES, OSD_OWNER_BYTES)) == owner:
            return index
    for index in range(1, header.osd_arr_size):
        at = header.entry_offset(index)
        if not _cstr(view.read(at + OSD_TEXT_BYTES, OSD_OWNER_BYTES)):
            view.write(at + OSD_TEXT_BYTES, _cbytes(owner, OSD_OWNER_BYTES))
            return index
    return None


def write_text(view: MemoryView, text: str, owner: str = OWNER) -> dict:
    """Put ``text`` in our slot (claiming one when needed) and ask RTSS to redraw."""
    header = Header(view)
    slot = find_slot(view, header, owner)
    if slot is None:
        raise RTSSError("every RTSS OSD slot is taken by another program")
    at = header.entry_offset(slot)
    if header.extended_text:
        view.write(at + OSD_TEXT_BYTES + OSD_OWNER_BYTES, _cbytes(text, OSD_EX_BYTES))
        view.write(at, _cbytes("", OSD_TEXT_BYTES))
    else:
        view.write(at, _cbytes(text, OSD_TEXT_BYTES))
    view.write(HEADER.size - 4, struct.pack("<I", (header.osd_frame + 1) & 0xFFFFFFFF))
    return {"slot": slot, "version": header.version, "extended": header.extended_text}


def release(view: MemoryView, owner: str = OWNER) -> bool:
    """Clear our slot so the text disappears from the game; True when one was ours."""
    header = Header(view)
    cleared = False
    for index in range(1, header.osd_arr_size):
        at = header.entry_offset(index)
        if _cstr(view.read(at + OSD_TEXT_BYTES, OSD_OWNER_BYTES)) == owner:
            view.write(at, b"\x00" * header.osd_entry_size)
            cleared = True
    if cleared:
        view.write(HEADER.size - 4, struct.pack("<I", (header.osd_frame + 1) & 0xFFFFFFFF))
    return cleared


def fake_block(version: int = 0x0002000F, slots: int = 8, apps: int = 0) -> bytearray:
    """An RTSS-shaped shared-memory block for tests and the preview."""
    entry = OSD_TEXT_BYTES + OSD_OWNER_BYTES + (OSD_EX_BYTES if version >= EXTENDED_TEXT_VERSION else 0)
    osd_offset = HEADER.size
    app_entry, app_offset = 1024, osd_offset + slots * entry
    block = bytearray(app_offset + apps * app_entry + 64)
    block[:HEADER.size] = HEADER.pack(SIGNATURE, version, app_entry, app_offset, apps, entry, osd_offset, slots, 0)
    return block


# ---- what the meter draws ----------------------------------------------------------------------

CLASS_COLORS = {"sorcerer": "3A86C8", "assassin": "4CAF6E", "templar": "C9772B", "ranger": "B9962A",
                "chanter": "B84F9E", "gladiator": "C8474F", "spiritmaster": "7A63D8", "cleric": "3FB4B0"}
_TAG = re.compile(r"[<>]")


def _k(value) -> str:
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def _plain(text) -> str:
    """Player names and boss names drawn verbatim: angle brackets would read as RTSS tags."""
    return _TAG.sub("", str(text or ""))


def render(status: dict, *, rows: int = 5, metric: str = "dps", style: str = "plain", title: str = "Aion 2 Calc") -> str:
    """The OSD text for one meter status (the same document the overlay polls)."""
    snap = (status or {}).get("snapshot") or {}
    players = [p for p in snap.get("players") or [] if isinstance(p, dict)]
    key = {"dps": ("dps", "damage"), "hps": ("hps", "healing"), "dtps": ("dtps", None)}.get(metric, ("dps", "damage"))
    players.sort(key=lambda p: -(float(p.get(key[0]) or 0)))
    total = sum(float(p.get(key[1]) or 0) for p in players) if key[1] else 0
    colored = style == "colored"
    lines = []
    head = _plain(snap.get("boss") or ("Live meter" if status.get("running") else "Meter stopped"))
    duration = snap.get("duration")
    if isinstance(duration, (int, float)) and duration > 0:
        head += f"  {int(duration) // 60}:{int(duration) % 60:02d}"
    lines.append((f"<C=E8CF8E>{head}<C>" if colored else head) + f"  {metric.upper()}")
    for p in players[:max(1, rows)]:
        name = _plain(p.get("name") or p.get("id") or "?")[:14]
        rate = _k(p.get(key[0]))
        share = f" {100 * float(p.get(key[1]) or 0) / total:.0f}%" if total and key[1] else ""
        line = f"{name:<14} {rate:>7}/s{share}"
        if colored:
            color = CLASS_COLORS.get(str(p.get("class") or "").lower())
            line = f"<C={color}>{line}<C>" if color else line
        lines.append(line)
    if not players:
        lines.append("waiting for combat")
    text = "\n".join(lines)
    return text[:OSD_EX_BYTES - 1]


# ---- the pusher ---------------------------------------------------------------------------------

class Pusher:
    """Keeps RTSS's slot up to date from a status callback on its own thread. ``state()`` is what
    the Settings page shows. Everything is best-effort: a missing RTSS is reported, never raised."""

    RETRY_S = 5.0

    def __init__(self, status_fn, settings_fn, view_factory=open_view):
        self._status_fn, self._settings_fn, self._view_factory = status_fn, settings_fn, view_factory
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.state = {"enabled": False, "supported": supported(), "connected": False, "slot": None,
                      "version": None, "error": None, "updates": 0, "last_text": ""}

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="rtss-osd")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._clear()

    def _clear(self) -> None:
        try:
            view = self._view_factory()
            try:
                release(view)
            finally:
                view.close()
        except Exception:
            pass
        self.state.update(connected=False, slot=None, enabled=False)

    def push_once(self) -> bool | None:
        """One update: True when RTSS took the text, False when RTSS could not be reached (retried
        slowly), None when the meter had no reading to give -- its data lock stayed busy with no
        reading cached yet -- in which case the last text stays in the game and the next update
        comes at the normal pace."""
        settings = self._settings_fn() or {}
        try:
            status = self._status_fn() or {}
        except Exception as exc:   # noqa: BLE001 - a busy or failing meter must never end the pusher
            self.state["error"] = f"Meter reading unavailable: {type(exc).__name__}: {exc}"[:300]
            return None
        text = render(status, rows=int(settings.get("rtss_rows") or 5),
                      metric=str(settings.get("rtss_metric") or "dps"), style=str(settings.get("rtss_style") or "plain"))
        try:
            view = self._view_factory()
        except NotRunning as exc:
            self.state.update(connected=False, slot=None, error=str(exc))
            return False
        except Exception as exc:   # noqa: BLE001 - reported to the Settings page, never raised
            self.state.update(connected=False, slot=None, error=f"{type(exc).__name__}: {exc}")
            return False
        try:
            if text == self.state.get("last_text") and self.state.get("connected"):
                self.state["error"] = None
                return True
            info = write_text(view, text)
        except Exception as exc:   # noqa: BLE001
            self.state.update(connected=False, slot=None, error=f"{type(exc).__name__}: {exc}")
            return False
        finally:
            view.close()
        self.state.update(connected=True, slot=info["slot"], version="%d.%d" % (info["version"] >> 16, info["version"] & 0xFFFF),
                          error=None, updates=self.state["updates"] + 1, last_text=text)
        return True

    def _run(self) -> None:
        self.state["enabled"] = True
        while not self._stop.is_set():
            ok, interval = None, 0.5
            try:
                settings = self._settings_fn() or {}
                if not settings.get("rtss_enabled"):
                    break
                interval = max(0.1, min(5.0, float(settings.get("rtss_interval_ms") or 500) / 1000))
                ok = self.push_once()
            except Exception as exc:   # noqa: BLE001 - one failed update must never end the pusher
                self.state["error"] = f"{type(exc).__name__}: {exc}"[:300]
            # Only an unreachable RTSS waits the long retry; a meter hiccup retries at the normal pace.
            self._stop.wait(self.RETRY_S if ok is False else interval)
        self._clear()
        self.state["enabled"] = False
