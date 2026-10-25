"""Pet Tracker inside Aion 2 Calc: a third client of Pet Tracker's capture worker.

Pet Tracker (https://github.com/0Fox2Give/PetTracker, by 0Fox2Give, GPL-3.0, used with its author's permission)
is a separate Windows program that reads the game's traffic to show your pet ranks and the souls you still need.
It is built in two parts:

* ``PetTracker.Capture.exe``, the worker: it watches the game, keeps your collection in
  ``%LOCALAPPDATA%\\PetTracker`` and answers on a named pipe that only your Windows account can open;
* ``PetTracker.exe``, its window, which asks the worker for its state once a second.

The pipe takes one JSON command per connection (``{"Action": "status"}``, ``patch``, ``pin``, ...) and answers
with one JSON view (protocol 3): your collection, recent soul rewards, the pet mobs the game reported nearby,
the farming session and Pet Tracker's settings. Aion 2 Calc talks to the same worker the same way, so

* :func:`find_install` finds an installed Pet Tracker (its own installer's folder, the older offline
  installer's, or one the user picked in Settings);
* :class:`Client` speaks the protocol over the pipe (:class:`_Win32` does the Windows part);
* :class:`Service` starts the worker when Pet Tracker is turned on in Aion 2 Calc and it is not running yet,
  caches its view, and renders it for the app: :func:`render` builds the overlay rows with the rules Pet
  Tracker's own overlay uses (``Activity.Select``), so both show the same pets.

Pet Tracker's window and Aion 2 Calc can run together: they share the one worker and its data.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_EXE = "PetTracker.exe"
WORKER_EXE = "PetTracker.Capture.exe"
PROTOCOL = 3
SOURCE_URL = "https://github.com/0Fox2Give/PetTracker"
DATA_FOLDER = "PetTracker"
#: Pet Tracker's catalog categories and the family names its overlay shows for them.
FAMILIES = {"Intellect": "Cogni", "Feral": "Fera", "Nature": "Natura", "Trans": "Varian", "Special": "Special"}
#: Souls a pet needs at each owned rank: unlock 5, Rank 2 takes 25, Rank 3 / MAX takes 75 (``PetStages``).
STAGE_GOALS = {0: 5, 1: 25, 2: 75}
MAX_ANSWER = 8 * 1024 * 1024
_MIN_TIME = datetime(1, 1, 1, tzinfo=timezone.utc)


class PetTrackerError(Exception):
    """Pet Tracker did not do what was asked; the message is for the person reading it."""


class NotRunning(PetTrackerError):
    """No Pet Tracker worker answers on the pipe."""


class Unsupported(PetTrackerError):
    """The worker speaks another protocol version than this app knows."""


# ------------------------------------------------------------------ finding Pet Tracker

def install_candidates(custom: str = "", local_appdata: str | None = None) -> list[tuple[str, Path]]:
    """Where Pet Tracker may be installed, in the order looked at: a folder picked in Settings, its own
    installer's (Velopack: ``%LOCALAPPDATA%\\PetTracker.Desktop\\current``), the older offline installer's
    (``%LOCALAPPDATA%\\Programs\\PetTracker``)."""
    found: list[tuple[str, Path]] = []
    if custom:
        found.append(("custom", Path(custom)))
    base = local_appdata if local_appdata is not None else os.environ.get("LOCALAPPDATA")
    if base:
        found.append(("installer", Path(base) / "PetTracker.Desktop" / "current"))
        found.append(("offline", Path(base) / "Programs" / "PetTracker"))
    return found


def _installed_version(folder: Path) -> str | None:
    """The version Pet Tracker's installer recorded beside it (Velopack's ``sq.version`` nuspec), if any."""
    try:
        text = (folder / "sq.version").read_text(encoding="utf-8", errors="replace")[:65536]
    except OSError:
        return None
    match = re.search(r"<version>\s*([0-9][0-9A-Za-z.+-]{0,40})\s*</version>", text)
    return match.group(1) if match else None


def find_install(custom: str = "", local_appdata: str | None = None) -> dict | None:
    """The first folder holding both Pet Tracker programs, as ``{"kind", "folder", "app", "worker", "version"}``."""
    for kind, folder in install_candidates(custom, local_appdata):
        app, worker = folder / APP_EXE, folder / WORKER_EXE
        try:
            if app.is_file() and worker.is_file():
                return {"kind": kind, "folder": str(folder), "app": str(app), "worker": str(worker),
                        "version": _installed_version(folder)}
        except OSError:
            continue
    return None


def _upper_invariant(text: str) -> str:
    """.NET's ``ToUpperInvariant``: one character in, one out. Python's ``upper`` can expand a character
    (``ß`` to ``SS``), which .NET keeps as it is."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def pipe_name(root: str, user: str) -> str:
    """The worker's pipe for a data folder, as Pet Tracker's ``Storage.Pipe`` names it on Windows:
    ``PetTracker-`` and the first 20 hex digits of SHA-256(user name + the folder's full path in capitals)."""
    path = ntpath.normpath(root)                     # GetFullPath on an absolute path
    if len(path) > 3 and path[-1] in "\\/":          # TrimEndingDirectorySeparator keeps a drive root
        path = path[:-1]
    digest = hashlib.sha256((user + _upper_invariant(path)).encode("utf-8")).hexdigest().upper()
    return "PetTracker-" + digest[:20]


# ------------------------------------------------------------------ Windows

class _Win32:
    """The Windows calls the bridge needs, through ctypes: the LocalAppData folder and the user name as .NET
    reads them (so the pipe name matches Pet Tracker's), the running programs, and one request on a named
    pipe with real timeouts (overlapped I/O, so a worker that stops answering never hangs the app)."""

    GENERIC_RW = 0x80000000 | 0x40000000
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    SECURITY_SQOS_PRESENT = 0x00100000      # with SECURITY_ANONYMOUS (0): the worker cannot act as this user
    ERROR_FILE_NOT_FOUND, ERROR_BROKEN_PIPE, ERROR_PIPE_BUSY = 2, 109, 231
    ERROR_MORE_DATA, ERROR_IO_PENDING = 234, 997
    WAIT_OBJECT_0 = 0
    CREATE_NO_WINDOW = 0x08000000

    def __init__(self):
        import ctypes
        from ctypes import wintypes as w
        self.ctypes, self.w = ctypes, w
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateFileW": ([w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
            "WaitNamedPipeW": ([w.LPCWSTR, w.DWORD], w.BOOL),
            "CreateEventW": ([ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR], w.HANDLE),
            "WriteFile": ([w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p], w.BOOL),
            "ReadFile": ([w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p], w.BOOL),
            "GetOverlappedResult": ([w.HANDLE, ctypes.c_void_p, ctypes.POINTER(w.DWORD), w.BOOL], w.BOOL),
            "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
            "CancelIoEx": ([w.HANDLE, ctypes.c_void_p], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Process32FirstW": ([w.HANDLE, ctypes.c_void_p], w.BOOL),
            "Process32NextW": ([w.HANDLE, ctypes.c_void_p], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(k, name)
            fn.argtypes, fn.restype = args, result
        self.k = k
        self.invalid = ctypes.c_void_p(-1).value

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                        ("Offset", w.DWORD), ("OffsetHigh", w.DWORD), ("hEvent", w.HANDLE)]

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                        ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", w.LONG), ("dwFlags", w.DWORD),
                        ("szExeFile", w.WCHAR * 260)]
        self.OVERLAPPED, self.PROCESSENTRY32W = OVERLAPPED, PROCESSENTRY32W

    # -- what .NET's Environment reports
    def local_appdata(self) -> str | None:
        """``Environment.GetFolderPath(LocalApplicationData)``: the known folder, which can differ from the
        LOCALAPPDATA variable."""
        ctypes, w = self.ctypes, self.w
        try:
            shell32, ole32 = ctypes.WinDLL("shell32"), ctypes.WinDLL("ole32")

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]
            folder = GUID(0xF1B32785, 0x6FBA, 0x4FCF, (ctypes.c_ubyte * 8)(0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91))
            path = ctypes.c_wchar_p()
            shell32.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, w.DWORD, w.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            shell32.SHGetKnownFolderPath.restype = ctypes.c_long
            if shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(path)) != 0:
                return None
            try:
                return path.value
            finally:
                ole32.CoTaskMemFree(path)
        except (OSError, AttributeError):
            return None

    def user_name(self) -> str | None:
        """``Environment.UserName``: the account part of ``GetUserNameExW(NameSamCompatible)``."""
        ctypes, w = self.ctypes, self.w
        try:
            secur32 = ctypes.WinDLL("secur32")
            secur32.GetUserNameExW.argtypes = [ctypes.c_int, w.LPWSTR, ctypes.POINTER(w.ULONG)]
            secur32.GetUserNameExW.restype = ctypes.c_ubyte          # BOOLEAN: one byte
            size = w.ULONG(512)
            buffer = ctypes.create_unicode_buffer(512)
            if secur32.GetUserNameExW(2, buffer, ctypes.byref(size)):
                return buffer.value.split("\\", 1)[-1]
        except (OSError, AttributeError):
            pass
        return os.environ.get("USERNAME")

    def processes(self) -> dict[str, list[int]]:
        """Running program file names (lower case) and their process ids."""
        ctypes, k = self.ctypes, self.k
        snap = k.CreateToolhelp32Snapshot(0x2, 0)
        if snap in (None, self.invalid):
            return {}
        try:
            entry = self.PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            found: dict[str, list[int]] = {}
            ok = k.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                found.setdefault(entry.szExeFile.lower(), []).append(entry.th32ProcessID)
                ok = k.Process32NextW(snap, ctypes.byref(entry))
            return found
        finally:
            k.CloseHandle(snap)

    # -- one request on the pipe
    def request(self, name: str, payload: bytes, timeout: float) -> bytes:
        """Connect to ``\\\\.\\pipe\\<name>``, write ``payload`` (one line) and read one line back. The worker
        serves one client at a time and makes a fresh pipe after every answer, so a busy or briefly missing pipe
        is waited for; a pipe that stays missing means no worker runs."""
        ctypes, k = self.ctypes, self.k
        path = "\\\\.\\pipe\\" + name
        start = time.monotonic()
        deadline, missing_until = start + timeout, start + 0.4
        while True:
            handle = k.CreateFileW(path, self.GENERIC_RW, 0, None, self.OPEN_EXISTING,
                                   self.FILE_FLAG_OVERLAPPED | self.SECURITY_SQOS_PRESENT, None)
            if handle not in (None, self.invalid):
                break
            error, now = ctypes.get_last_error(), time.monotonic()
            if error == self.ERROR_PIPE_BUSY and now < deadline:
                k.WaitNamedPipeW(path, max(1, min(250, int((deadline - now) * 1000))))
                missing_until = time.monotonic() + 0.4      # it answers someone else, then re-arms its pipe
            elif error == self.ERROR_FILE_NOT_FOUND and now < min(missing_until, deadline):
                time.sleep(0.03)
            elif error == self.ERROR_FILE_NOT_FOUND:
                raise NotRunning("Pet Tracker's capture is not running.")
            elif error == self.ERROR_PIPE_BUSY:
                raise TimeoutError("Pet Tracker's capture stayed busy.")
            else:
                raise ctypes.WinError(error)
        event = k.CreateEventW(None, True, False, None)
        if not event:
            error = ctypes.get_last_error()
            k.CloseHandle(handle)
            raise ctypes.WinError(error)
        try:
            self._io(handle, event, k.WriteFile, payload, deadline)
            data = bytearray()
            while b"\n" not in data:
                chunk = self._io(handle, event, k.ReadFile, 65536, deadline)
                if not chunk:
                    break                                   # the worker closed its end
                data += chunk
                if len(data) > MAX_ANSWER:
                    raise PetTrackerError("Pet Tracker's answer was too large.")
            return bytes(data).split(b"\n", 1)[0]
        finally:
            k.CloseHandle(event)
            k.CloseHandle(handle)

    def _io(self, handle, event, call, data, deadline):
        """One overlapped WriteFile (``data`` bytes) or ReadFile (``data`` = how many bytes at most) that gives up
        at ``deadline``; a read returns ``b""`` once the worker has closed the pipe."""
        ctypes, k = self.ctypes, self.k
        overlapped = self.OVERLAPPED()
        overlapped.hEvent = event
        if isinstance(data, (bytes, bytearray)):
            buffer, size = ctypes.create_string_buffer(bytes(data), len(data)), len(data)
        else:
            buffer, size = ctypes.create_string_buffer(data), data
        done = self.w.DWORD(0)
        if not call(handle, buffer, size, None, ctypes.byref(overlapped)):
            error = ctypes.get_last_error()
            if error == self.ERROR_BROKEN_PIPE:
                return b""
            if error == self.ERROR_IO_PENDING:
                wait = max(0, int((deadline - time.monotonic()) * 1000))
                if k.WaitForSingleObject(event, wait) != self.WAIT_OBJECT_0:
                    k.CancelIoEx(handle, ctypes.byref(overlapped))
                    # the cancelled request still owns the buffer until it completes: wait for that first
                    k.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done), True)
                    raise TimeoutError("Pet Tracker's capture did not answer in time.")
            elif error != self.ERROR_MORE_DATA:
                raise ctypes.WinError(error)
        if not k.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(done), False):
            error = ctypes.get_last_error()
            if error == self.ERROR_BROKEN_PIPE:
                return b""
            if error != self.ERROR_MORE_DATA:
                raise ctypes.WinError(error)
        return buffer.raw[:done.value]

    def spawn(self, args: list[str], cwd: str, hidden: bool) -> None:
        subprocess.Popen(args, cwd=cwd, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=self.CREATE_NO_WINDOW if hidden else 0)


def _platform():
    if sys.platform != "win32":
        return None
    try:
        return _Win32()
    except (OSError, AttributeError):
        return None


def self_check(win=None) -> str:
    """Windows: the pipe client against pipes made the way Pet Tracker's worker makes its own (byte mode, one
    instance, one command line in and one answer line back per connection, closed as soon as the answer is
    written), and the folder, user name and process list it reads. The packaged app's smoke test runs it, so
    the ctypes calls are checked on Windows itself. Raises :class:`PetTrackerError` on the first failure."""
    import _winapi
    win = win or _Win32()
    base, line = f"aion2calc-check-{os.getpid()}-{time.monotonic_ns()}", b'{"Action":"status"}\n'

    def pipe(name):
        return _winapi.CreateNamedPipe("\\\\.\\pipe\\" + name, _winapi.PIPE_ACCESS_DUPLEX, 0, 1, 65536, 65536, 0,
                                       _winapi.NULL)

    def serve(handle, answer, got, hold):
        try:
            try:
                _winapi.ConnectNamedPipe(handle, False)
            except OSError as err:
                if err.winerror != 535:            # ERROR_PIPE_CONNECTED: the client came first
                    raise
            data = b""
            while b"\n" not in data:
                chunk, _ = _winapi.ReadFile(handle, 65536)
                if not chunk:
                    break
                data += chunk
            got.append(data)
            if answer is None:
                hold.wait(10)                      # a worker that stops answering
            else:
                _winapi.WriteFile(handle, answer)
        except OSError:
            pass
        finally:
            _winapi.CloseHandle(handle)

    def serving(name, answer, got, hold):
        thread = threading.Thread(target=serve, args=(pipe(name), answer, got, hold), daemon=True)
        thread.start()
        return thread

    # a view larger than one read, in UTF-8, with the CRLF .NET's WriteLine ends it with
    view = {"Protocol": PROTOCOL, "Ready": True, "Character": "Ärger", "Padding": "x" * 200_000}
    got, hold = [], threading.Event()
    server = serving(base, json.dumps(view, ensure_ascii=False).encode("utf-8") + b"\r\n", got, hold)
    answer = parse_answer(win.request(base, line, 5.0))
    server.join(5)
    if got != [line] or answer != view:
        raise PetTrackerError("a command and its answer did not arrive whole")

    # a worker that takes the command and never answers: the request gives up on time, and a second request
    # meanwhile finds the one pipe taken and reports it busy
    silent, got, outcome = base + "-silent", [], []
    server = serving(silent, None, got, hold)

    def first():
        try:
            win.request(silent, line, 1.5)
            outcome.append("answered")
        except Exception as err:
            outcome.append(type(err).__name__)
    waiting = threading.Thread(target=first, daemon=True)
    waiting.start()
    started = time.monotonic()
    while not got and time.monotonic() - started < 5:
        time.sleep(0.01)
    try:
        win.request(silent, line, 0.3)
        busy = "answered"
    except Exception as err:
        busy = type(err).__name__
    waiting.join(5)
    hold.set()
    server.join(5)
    if outcome != ["TimeoutError"] or busy != "TimeoutError" or waiting.is_alive():
        raise PetTrackerError(f"a worker that never answers: {outcome or ['still waiting']}, busy pipe: {busy}")

    started = time.monotonic()
    try:
        win.request(base + "-missing", line, 3.0)
        raise PetTrackerError("a pipe that does not exist answered")
    except NotRunning:
        pass
    if time.monotonic() - started > 2.0:
        raise PetTrackerError("a missing worker took too long to notice")

    folder, user, programs = win.local_appdata(), win.user_name(), win.processes()
    mine = [exe for exe, pids in programs.items() if os.getpid() in pids]
    if not folder or not user or len(mine) != 1 or not mine[0].endswith(".exe"):
        raise PetTrackerError(f"folder {bool(folder)}, user name {bool(user)}, this program listed as {mine}")
    return f"OK (round trip, timeout, busy, missing worker; {mine[0]} in {len(programs)} programs)"


# ------------------------------------------------------------------ the protocol

def parse_answer(raw: bytes) -> dict:
    """The worker's answer: its view (protocol 3), or ``{"Error": ...}`` when it refused the command."""
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise PetTrackerError("Pet Tracker sent an answer that could not be read.") from None
    if not isinstance(doc, dict):
        raise PetTrackerError("Pet Tracker sent an answer that could not be read.")
    if "Protocol" not in doc:
        raise PetTrackerError(str(doc.get("Error") or "Pet Tracker sent an answer that could not be read."))
    if doc.get("Protocol") != PROTOCOL:
        raise Unsupported(f"This Pet Tracker speaks protocol {doc.get('Protocol')}, and this Aion 2 Calc protocol "
                          f"{PROTOCOL}. Update whichever is older.")
    return doc


class Client:
    """Commands to the worker: one JSON line per pipe connection, as Pet Tracker's own window sends them. The
    worker's pipe name depends on the data folder's exact path, so each candidate folder's pipe is tried, the
    one that answered last first."""

    def __init__(self, roots: list[str], user: str, request):
        self.roots, self.user, self.request = list(roots), user, request
        self.last: str | None = None

    def endpoints(self) -> list[str]:
        names = list(dict.fromkeys(pipe_name(root, self.user) for root in self.roots))
        if self.last in names:
            names.remove(self.last)
            names.insert(0, self.last)
        return names

    def send(self, command: dict, timeout: float = 4.0) -> dict:
        line = (json.dumps(command, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        for name in self.endpoints():
            try:
                raw = self.request(name, line, timeout)
            except NotRunning:
                continue
            self.last = name
            return parse_answer(raw)
        raise NotRunning("Pet Tracker's capture is not running.")


# ------------------------------------------------------------------ the view, as Pet Tracker's overlay shows it

def parse_time(value) -> datetime:
    """A .NET DateTimeOffset from the view (``2026-10-25T05:00:00.1234567+00:00``); the earliest time when absent."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return _MIN_TIME
    text = re.sub(r"(\.\d{6})\d+", r"\1", value.strip().replace("Z", "+00:00"))
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return _MIN_TIME
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def pet_name(pet: dict) -> str:
    """``PetNames.Resolve``: the name the player gave the pet, else its catalog name."""
    display, catalog = pet.get("DisplayName") or "", pet.get("CatalogName") or ""
    if display and display != catalog:
        return display
    if catalog:                                          # BlackDragon_01 -> Black Dragon
        base = re.sub(r"_\d+$", "", catalog).replace("_", " ")
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base).strip() or catalog
    return f"Pet #{pet.get('Id')}"


def family(pet: dict) -> str:
    return FAMILIES.get(pet.get("Category") or "", "")


def current_souls(pet: dict):
    estimated = _int(pet.get("EstimatedSouls"))
    return estimated if estimated is not None else _int(pet.get("Souls"))


def is_max(pet: dict) -> bool:
    level = _int(pet.get("Level"))
    return level is not None and level >= 3


def ratio(pet: dict) -> float:
    goal, souls = _int(pet.get("Goal")), current_souls(pet)
    return max(0.0, min(1.0, souls / goal)) if goal and goal > 0 and souls is not None else 0.0


def known_rank(pet: dict):
    """``PetCollection.KnownRank``: a rank the game synchronized, or MAX reached from tracked souls."""
    level = _int(pet.get("Level"))
    if level is None or not 0 <= level <= 3:
        return None
    return level if pet.get("LevelVerified") or (pet.get("LevelDerivedFromSouls") and level >= 3) else None


def rank_increase_pending(pet: dict) -> bool:
    level, goal, souls = _int(pet.get("Level")), _int(pet.get("Goal")), current_souls(pet)
    return bool(pet.get("ProgressNeedsSync")) and level in (0, 1) and goal == STAGE_GOALS[level] \
        and souls is not None and souls >= goal


def souls_remaining(pet: dict):
    """``PetCollection.SoulsRemaining``: souls to the next rank, only when the count is exact."""
    rank, souls, goal = known_rank(pet), _int(pet.get("Souls")), _int(pet.get("Goal"))
    if rank not in (0, 1, 2) or pet.get("ProgressNeedsSync") or not pet.get("CounterVerified") \
            or pet.get("EstimatedSouls") is not None or souls is None or souls < 0 or goal != STAGE_GOALS[rank]:
        return None
    return max(0, goal - souls)


def goal_text(pet: dict, synced: bool) -> str:
    """``FarmingGoals.Describe``: the souls left to a pet's farming goal."""
    target = _int(pet.get("TargetRank"))
    if target is None:
        return ""
    rank = known_rank(pet)
    if synced and rank is not None and rank >= target:
        return f"Rank {target} goal reached"
    souls, goal = current_souls(pet), _int(pet.get("Goal"))
    exact = pet.get("CounterVerified") or (pet.get("EstimatedSouls") is not None and pet.get("CollectionImportedUtc"))
    if not synced or rank is None or pet.get("ProgressNeedsSync") or not exact or souls is None \
            or goal != STAGE_GOALS.get(rank):
        return f"Goal: Rank {target} · waiting for collection sync"
    left = max(0, goal - souls) + sum(STAGE_GOALS[stage] for stage in range(rank + 1, target))
    return f"{'About ' if pet.get('EstimatedSouls') is not None else ''}{left} soul{'' if left == 1 else 's'} to Rank {target}"


def pins(settings: dict) -> list[int]:
    """The pinned pets, in pinned order (``AppSettings.Pins``, with its older single-pin field)."""
    ids = settings.get("PinnedPetIds")
    if ids is None:
        legacy = _int(settings.get("PinnedPetId"))
        ids = [legacy] if legacy is not None else []
    if not isinstance(ids, list):
        return []
    return [i for i in dict.fromkeys(i for i in ids if _int(i) is not None)]


def _setting(settings: dict, key: str, default: int) -> int:
    value = _int(settings.get(key))
    return value if value is not None else default


def select_activities(view: dict, now: datetime) -> list[dict]:
    """``Activity.Select``: which pets the overlay lists and in what order. Pinned pets first, in their pinned
    order; then recent soul rewards (or, in Nearby mode, the pet mobs the game reported recently), expired
    after the inactive time unless pinned, maxed pets hidden on request, sorted as Pet Tracker's Sort setting
    says; at most the row limit, always one row more than the pins."""
    settings = view.get("Settings") or {}
    pets = (view.get("Profile") or {}).get("Pets") or {}

    def pet(activity):
        return pets.get(str(activity.get("PetId")))

    nearby_mode = settings.get("TrackerMode") == "Nearby"
    if nearby_mode:
        stale = _setting(settings, "NearbyStaleSeconds", 60)
        source = [{"PetId": p.get("PetId"), "NpcId": None, "CreatureName": p.get("CreatureName") or "",
                   "SeenUtc": p.get("SeenUtc"), "IsNearby": True}
                  for p in view.get("Nearby") or []
                  if parse_time(p.get("SeenUtc")) <= now and (now - parse_time(p.get("SeenUtc"))).total_seconds() < stale]
    else:
        source = list(view.get("Recent") or [])
    rows = [a for a in source if _int(a.get("PetId")) is not None and pet(a) is not None]
    if settings.get("HideMaxed"):
        rows = [a for a in rows if not is_max(pet(a))]
    if settings.get("ExpireInactive", True):
        inactive = _setting(settings, "InactiveSeconds", 20) + 0.18
        rows = [a for a in rows if a.get("IsNearby") or (now - parse_time(a.get("SeenUtc"))).total_seconds() < inactive]

    def name(a):
        return pet_name(pet(a)).upper()
    order = settings.get("Sort")
    if order == "Recent only":
        rows.sort(key=lambda a: (-parse_time(a.get("SeenUtc")).timestamp(), a["PetId"]))
    elif order == "Closest to next rank":
        rows.sort(key=lambda a: (is_max(pet(a)), -(0.0 if is_max(pet(a)) else ratio(pet(a))), name(a), a["PetId"]))
    else:   # "Unfinished first": unmaxed first, newest first; Nearby and maxed rows by name so traffic cannot shuffle them
        rows.sort(key=lambda a: (is_max(pet(a)),
                                 0.0 if nearby_mode or is_max(pet(a)) else -parse_time(a.get("SeenUtc")).timestamp(),
                                 name(a), a["PetId"]))
    pinned_ids = [i for i in pins(settings) if str(i) in pets]
    pinned = [next((a for a in source if a.get("PetId") == i),
                   {"PetId": i, "NpcId": None, "CreatureName": "", "SeenUtc": None, "IsNearby": False})
              for i in pinned_ids]
    limit = max(_setting(settings, "RowLimit", 5), len(pinned_ids) + 1)
    return (pinned + [a for a in rows if a["PetId"] not in pinned_ids])[:limit]


def observation_notice(activity: dict, settings: dict, now: datetime) -> str:
    """``Activity.ObservationNotice``: in Nearby mode, how fresh a sighting is."""
    if settings.get("TrackerMode") != "Nearby":
        return ""
    if not activity.get("IsNearby"):
        return "Not currently observed"
    age = (now - parse_time(activity.get("SeenUtc"))).total_seconds()
    if age < 0 or age >= _setting(settings, "NearbyStaleSeconds", 60):
        return "Not currently observed"
    return "" if age < 15 else f"Last seen {int(age)}s ago"


def empty_text(view: dict, now: datetime) -> str:
    """``Activity.EmptyText``: what the overlay says when it lists no pet."""
    if not view.get("Ready"):
        return view.get("Status") or "Connecting to capture…"
    settings = view.get("Settings") or {}
    pets = (view.get("Profile") or {}).get("Pets") or {}
    if settings.get("TrackerMode") == "Nearby":
        stale = _setting(settings, "NearbyStaleSeconds", 60)
        nearby = [p for p in view.get("Nearby") or [] if str(p.get("PetId")) in pets
                  and parse_time(p.get("SeenUtc")) <= now and (now - parse_time(p.get("SeenUtc"))).total_seconds() < stale]
        if nearby and settings.get("HideMaxed") and all(is_max(pets[str(p["PetId"])]) for p in nearby):
            return "Nearby pets are maxed. Turn off Hide maxed to see them."
        return "No pet mobs detected nearby. Explore to discover more."
    recent = [a for a in view.get("Recent") or [] if str(a.get("PetId")) in pets]
    expire = settings.get("ExpireInactive", True)
    inactive = _setting(settings, "InactiveSeconds", 20) + 0.18
    current = [a for a in recent if a.get("IsNearby") or not expire
               or (now - parse_time(a.get("SeenUtc"))).total_seconds() < inactive]
    if current and settings.get("HideMaxed") and all(is_max(pets[str(a["PetId"])]) for a in current):
        return "Recent pets are maxed. Turn off Hide maxed to see them."
    if recent and not current and expire:
        return ""
    if view.get("Status") == "Collection sync needed":
        return "Connected. Waiting for collection totals; pet rewards will still appear here."
    return "Recent pet rewards will appear here."


def _row(pet: dict, activity: dict | None, view: dict, now: datetime, paused: bool, synced: bool) -> dict:
    settings = view.get("Settings") or {}
    pet_id = _int(pet.get("Id"))
    level, goal, souls = _int(pet.get("Level")), _int(pet.get("Goal")), current_souls(pet)
    maxed, pinned = is_max(pet), pet_id in pins(settings)
    notice = "Rank increase pending" if rank_increase_pending(pet) else ("Pinned" if pinned else "")
    increase = view.get("Increase") or {}
    if not maxed and increase.get("PetId") == pet_id and now - parse_time(increase.get("SeenUtc")) < timedelta(seconds=20):
        notice = "Rank increased"
    if activity is not None:
        seen = observation_notice(activity, settings, now)
        if seen:
            notice = f"{notice} · {seen}" if notice else seen
    return {
        "id": pet_id, "name": pet_name(pet), "family": family(pet), "level": level, "rank": known_rank(pet),
        "rank_text": "Unranked" if level == 0 else f"Rank {level if level is not None else '?'}",
        "max": maxed, "souls": souls, "goal": goal, "estimated": pet.get("EstimatedSouls") is not None,
        "progress": "MAX" if maxed else f"{souls if souls is not None else '?'} / {goal if goal is not None else '?'}",
        "ratio": round(ratio(pet), 4), "paused": bool(paused or pet.get("ProgressNeedsSync")),
        "remaining": souls_remaining(pet) if synced else None, "pinned": pinned, "notice": notice,
        "creature": (activity or {}).get("CreatureName") or "", "goal_rank": _int(pet.get("TargetRank")),
        "goal_text": goal_text(pet, synced), "portrait": f"/api/pettracker/portrait/{pet_id}.png",
    }


def render(view: dict, now: datetime, collection: bool = False) -> dict:
    """The worker's view as the app's overlay and page draw it."""
    settings = view.get("Settings") or {}
    pets = (view.get("Profile") or {}).get("Pets") or {}
    ready, synced = bool(view.get("Ready")), bool(view.get("CollectionSynced"))
    paused = ready and not synced
    rows = [_row(pets[str(a["PetId"])], a, view, now, paused, synced)
            for a in (select_activities(view, now) if ready else [])]
    ranks = [known_rank(p) for p in pets.values()]
    farming = view.get("Farming") or {}
    session_pets = [{"id": _int(r.get("PetId")), "name": pet_name(pets.get(str(r.get("PetId"))) or {"Id": r.get("PetId")}),
                     "souls": _int(r.get("Souls")) or 0, "rank_ups": _int(r.get("RankUps")) or 0}
                    for r in farming.get("Pets") or []]
    out = {
        "status": view.get("Status") or "", "detail": view.get("Detail") or "", "ready": ready, "synced": synced,
        "character": view.get("Character") or view.get("DetectedCharacter") or "",
        "capture": {"devices": _int(view.get("Devices")) or 0, "received": _int(view.get("Received")) or 0,
                    "dropped": _int(view.get("Dropped")) or 0},
        "rows": rows, "empty": "" if rows else empty_text(view, now),
        "sync_notice": paused and view.get("Status") == "Collection sync needed",
        "options": {"mode": "Nearby" if settings.get("TrackerMode") == "Nearby" else "Recent",
                    "hide_maxed": bool(settings.get("HideMaxed")), "sort": settings.get("Sort") or "Unfinished first",
                    "row_limit": _setting(settings, "RowLimit", 5), "pin_limit": _setting(settings, "PinLimit", 3),
                    "pins": pins(settings), "portraits": settings.get("Portraits", True) is not False,
                    "progress_bars": settings.get("ProgressBars", True) is not False,
                    "compact": bool(settings.get("Compact")), "accent": settings.get("Accent") or "Gold",
                    "own_window_visible": settings.get("Visible", True) is not False},
        "session": {"started": farming.get("StartedUtc"), "incomplete": bool(farming.get("Incomplete")),
                    "souls": sum(p["souls"] for p in session_pets),
                    "ranked": sum(1 for p in session_pets if p["rank_ups"] > 0), "pets": session_pets},
        "summary": {"total": len(ranks), "collected": sum(1 for r in ranks if r is not None and r > 0),
                    "maxed": sum(1 for r in ranks if r == 3), "unknown": sum(1 for r in ranks if r is None)},
    }
    if collection:
        out["collection"] = sorted((_row(p, None, view, now, paused, synced) for p in pets.values()),
                                   key=lambda r: (r["name"].upper(), r["id"] or 0))
    return out


# ------------------------------------------------------------------ the service the app runs

class Service:
    """Pet Tracker for the running app. Off until Settings → Pet Tracker turns it on; then the worker is
    started if it does not run yet (so the collection syncs when you log in), its view is fetched when the
    overlay or the app asks (at most once per ``MAX_AGE``, shared between them), and a worker this app
    started is asked to save and stop when the app quits, unless Pet Tracker's own window still uses it."""

    MAX_AGE = 0.8
    LAUNCH_SPACING = 15.0

    def __init__(self, platform=None, clock=time.monotonic, now=None):
        self.platform = platform if platform is not None else _platform()
        self.clock = clock
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.lock = threading.RLock()
        self.enabled, self.custom_path = False, ""
        self.view: dict | None = None
        self.view_at: float | None = None
        self.error = ""
        self.failed_at: float | None = None
        self.launched_at: float | None = None
        self.started_worker = False
        #: what this app did to Pet Tracker's own overlay: "hidden" (for Aion 2 Calc's window) or "shown" (its style)
        self.own_window: str | None = None
        self._client: Client | None = None
        self._roots: tuple | None = None

    # -- configuration and discovery
    def configure(self, enabled: bool, path: str = "") -> None:
        with self.lock:
            if (enabled, path) != (self.enabled, self.custom_path):
                self.view, self.view_at, self.failed_at, self._client = None, None, None, None
            self.enabled, self.custom_path = bool(enabled), path or ""

    def install(self) -> dict | None:
        local = self.platform.local_appdata() if self.platform else None
        return find_install(self.custom_path, local or os.environ.get("LOCALAPPDATA"))

    def roots(self) -> list[str]:
        """Pet Tracker's data folder as .NET finds it (the known LocalAppData folder) and as the environment
        names it, when the two differ."""
        bases = [self.platform.local_appdata() if self.platform else None, os.environ.get("LOCALAPPDATA")]
        return list(dict.fromkeys(ntpath.join(b, DATA_FOLDER) for b in bases if b))

    def client(self) -> Client:
        roots = tuple(self.roots())
        if self._client is None or roots != self._roots:
            user = (self.platform.user_name() if self.platform else None) or os.environ.get("USERNAME", "")
            self._client, self._roots = Client(list(roots), user, self.platform.request), roots
        return self._client

    def running(self) -> dict:
        names = self.platform.processes() if self.platform else {}
        return {"app": APP_EXE.lower() in names, "worker": WORKER_EXE.lower() in names}

    # -- the worker
    def ensure_worker(self) -> str:
        """Start the worker when it should run and does not: ``running``, ``started``, ``waiting`` (started a
        moment ago), ``off``, ``missing`` (not installed) or ``unsupported``."""
        with self.lock:
            if self.platform is None:
                return "unsupported"
            if not self.enabled:
                return "off"
            info = self.install()
            if info is None:
                return "missing"
            if self.running()["worker"]:
                return "running"
            now = self.clock()
            if self.launched_at is not None and now - self.launched_at < self.LAUNCH_SPACING:
                return "waiting"
            roots = self.roots()
            if not roots:
                return "missing"
            self.platform.spawn([info["worker"], "--data", roots[0]], info["folder"], True)
            self.launched_at, self.started_worker = now, True
            return "started"

    def send(self, command: dict, timeout: float = 4.0) -> dict:
        """One command; the answer is the worker's fresh view, which becomes the cached one."""
        if self.platform is None:
            raise PetTrackerError("Pet Tracker runs on Windows only.")
        with self.lock:
            view = self.client().send(command, timeout)
            self.view, self.view_at, self.error, self.failed_at = view, self.clock(), "", None
            return view

    def fetch(self, max_age: float | None = None) -> dict | None:
        """The worker's view, fetched when the cached one is older than ``max_age``; None when no worker answers
        (one is started if Pet Tracker is on). A failure is shared for as long as a view would be, so the overlay
        and the page do not both wait on a worker that is not there."""
        with self.lock:
            max_age = self.MAX_AGE if max_age is None else max_age
            now = self.clock()
            if self.view is not None and self.view_at is not None and now - self.view_at < max_age:
                return self.view
            if self.view is None and self.failed_at is not None and now - self.failed_at < max_age:
                return None
            try:
                return self.send({"Action": "status"})
            except NotRunning as err:
                self.view, self.view_at, self.error, self.failed_at = None, None, str(err), self.clock()
                self.ensure_worker()
            except (PetTrackerError, TimeoutError, OSError) as err:
                self.view, self.view_at, self.error, self.failed_at = None, None, str(err), self.clock()
            return None

    def wait_ready(self, timeout: float) -> dict | None:
        """The worker's view once it answers: a worker started a moment ago takes a little while to open its pipe."""
        deadline = time.monotonic() + timeout
        while True:
            view = self.fetch(max_age=0)
            if view is not None or time.monotonic() >= deadline:
                return view
            time.sleep(0.25)

    def patch(self, **fields) -> dict:
        return self.send({"Action": "patch", "Patch": fields})

    def show_own_window(self, visible: bool) -> str:
        """Pet Tracker's own overlay window: shown by launching Pet Tracker when it is not running (a normal
        launch shows it), otherwise through its Visible setting, which its window follows within a second."""
        if visible and not self.running()["app"]:
            return "launched" if self.launch_app() else "missing"
        self.patch(Visible=bool(visible))
        return "shown" if visible else "hidden"

    def follow_overlay(self, ours: bool, theirs: bool) -> str:
        """Pet Tracker's own overlay next to Aion 2 Calc's, as Settings → Pet Tracker chose: shown for the "Pet
        Tracker's window" style (``theirs``), hidden while Aion 2 Calc's own window shows the pets (``ours``) so one
        pet overlay shows, and put back once neither applies. Only a running Pet Tracker is changed: a normal launch
        of Pet Tracker shows its overlay again by itself."""
        with self.lock:
            if theirs:
                result = self.show_own_window(True)
                self.own_window = "shown"
                return result
            if not self.running()["app"]:
                self.own_window = None
                return "not running"
            if ours:
                view = self.fetch(max_age=0)
                if view is None or (view.get("Settings") or {}).get("Visible", True) is False:
                    return "unchanged"
                self.patch(Visible=False)
                self.own_window = None if self.own_window == "shown" else "hidden"
                return "hidden"
            previous, self.own_window = self.own_window, None
            if previous is None:
                return "unchanged"
            self.patch(Visible=previous == "hidden")
            return "shown" if previous == "hidden" else "hidden"

    def launch_app(self, minimized: bool = False) -> bool:
        """Start Pet Tracker's own window (its finder, maps, merchant list and settings) unless it runs."""
        with self.lock:
            info = self.install()
            if self.platform is None or info is None or self.running()["app"]:
                return False
            self.platform.spawn([info["app"]] + (["--minimized"] if minimized else []), info["folder"], False)
            return True

    def shutdown(self) -> None:
        """App quitting, or Pet Tracker turned off in it: Pet Tracker's own overlay shows again if this app hid it,
        and a worker this app started saves and stops, unless Pet Tracker's window still uses it."""
        with self.lock:
            if self.platform is None:
                return
            try:
                if self.own_window == "hidden" and self.running()["app"]:
                    self.patch(Visible=True)
            except (PetTrackerError, TimeoutError, OSError):
                pass
            self.own_window = None
            if not self.started_worker:
                return
            self.started_worker = False
            try:
                if self.running()["app"]:
                    return
                self.client().send({"Action": "exit"}, timeout=3.0)
            except (PetTrackerError, TimeoutError, OSError):
                pass

    # -- the app's view
    def state(self, collection: bool = False) -> dict:
        from . import pettracker_setup
        info = self.install() if self.platform is not None else None
        out = {"supported": self.platform is not None, "enabled": self.enabled, "source": SOURCE_URL,
               "installed": None if info is None else {k: info[k] for k in ("kind", "folder", "version")},
               "setup": pettracker_setup.status(), "running": {"app": False, "worker": False},
               "connected": False, "problem": ""}
        if self.platform is None:
            out["problem"] = "Pet Tracker runs on Windows only."
            return out
        out["running"] = self.running()
        if not self.enabled or info is None:
            return out
        view = self.fetch()
        out["problem"] = self.error
        if view is not None:
            out["connected"] = True
            out.update(render(view, self.now(), collection))
        return out


_SERVICE: Service | None = None
_SERVICE_LOCK = threading.Lock()


def service() -> Service:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = Service()
        return _SERVICE


def portrait_path(pet_id: int, install: dict | None, roots: list[str]) -> Path | None:
    """A pet's portrait, where Pet Tracker's own window looks for it: its data folder, then beside its program."""
    for folder in [*roots, *([install["folder"]] if install else [])]:
        path = Path(folder) / "portraits" / f"{int(pet_id)}.png"
        if path.is_file():
            return path
    return None
