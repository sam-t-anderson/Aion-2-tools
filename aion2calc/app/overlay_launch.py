"""Launch the native transparent overlay from the running app, and keep it running.

The Live Meter page's "Open overlay" button posts to ``/api/overlay``; this starts the frameless,
transparent, always-on-top overlay in its own process (so pywebview owns a main thread of its own).

* Installed app (frozen): the bundled executable is re-run with ``AION2CALC_OVERLAY=1`` set, which
  :func:`aion2calc.launcher.main` routes to :func:`aion2calc.overlay.main`. pywebview is bundled on
  Windows, so this needs no Python install from the user.
* From source: ``python -m aion2calc.overlay`` is spawned instead.

When pywebview is not available the browser popup the page opens itself is the fallback, so the
response just says whether a native window was started (``{"native": true/false}``).

Two companion windows open beside the meter overlay while their settings are on: the Party-DPS overlay
(``view=party``, ``overlay_party_enabled``) and, since 0.2.329, the Hidden Cube radar's own small window
(``view=radar``, ``radar_enabled``). They follow their settings while the meter overlay is open
(:func:`sync_companions`), and each one's Hide closes that window alone (:func:`close_view`).

Each overlay process is watched: one that ends on its own with a non-zero code (its watchdog asked
for a restart because the page went blank or stopped answering, or it crashed) is started again, at
most five times in ten minutes; one the app closed, or that closed itself normally (Hide), is left
alone. Open overlay while the overlay is already open asks it to reload its page.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import time

from ..overlay_health import OverlayLog, RelaunchLimiter


_PROCESS: subprocess.Popen | None = None
_PARTY_PROCESS: subprocess.Popen | None = None
_RADAR_PROCESS: subprocess.Popen | None = None
_LOCK = threading.Lock()
_RELAUNCHES = RelaunchLimiter()
_URL = ""                       # the overlay URL of the last launch, for the companions' syncs
_HIDDEN: set[str] = set()       # companions closed with their own Hide, until Open overlay or their setting flips
COMPANIONS = ("party", "radar")


def available() -> bool:
    """Is pywebview importable in this interpreter (so a transparent window is possible)?"""
    try:
        return importlib.util.find_spec("webview") is not None
    except Exception:
        return False


def _spawn(url: str) -> subprocess.Popen:
    env = {**os.environ, "AION2CALC_OVERLAY": "1", "AION2CALC_OVERLAY_URL": url}
    if getattr(sys, "frozen", False):
        return subprocess.Popen([sys.executable], env=env, close_fds=True)
    return subprocess.Popen([sys.executable, "-m", "aion2calc.overlay", "--url", url], env=env, close_fds=True)


def _log(message: str) -> None:
    try:
        from ..paths import logs_dir
        OverlayLog(logs_dir() / "overlay.log", "app").write(message)
    except Exception:
        pass


def _party_enabled() -> bool:
    try:
        from .server import ui_settings
        return bool(ui_settings().get("overlay_party_enabled"))
    except Exception:
        return False


def _radar_enabled() -> bool:
    try:
        from .server import ui_settings
        return bool(ui_settings().get("radar_enabled"))
    except Exception:
        return False


def _kind(party) -> str:
    """The window a slot name or flag means: ``"meter"``, ``"party"`` or ``"radar"``."""
    if isinstance(party, str):
        return party
    return "party" if party else "meter"


def _get(kind: str):
    return {"meter": _PROCESS, "party": _PARTY_PROCESS, "radar": _RADAR_PROCESS}[kind]


def _set(kind: str, proc) -> None:
    global _PROCESS, _PARTY_PROCESS, _RADAR_PROCESS
    if kind == "party":
        _PARTY_PROCESS = proc
    elif kind == "radar":
        _RADAR_PROCESS = proc
    else:
        _PROCESS = proc


def _alive(kind: str) -> bool:
    proc = _get(kind)
    return proc is not None and proc.poll() is None


def _start(url: str, party="meter") -> subprocess.Popen:
    """Spawn one overlay process and watch it. The caller holds the lock and stores the result."""
    kind = _kind(party)
    proc = _spawn(url)
    threading.Thread(target=_watch, args=(proc, url, kind), daemon=True,
                     name="overlay-supervisor" + ("" if kind == "meter" else "-" + kind)).start()
    return proc


def _watch(proc: subprocess.Popen, url: str, party="meter") -> None:
    """Relaunch an overlay process that ended by itself with a non-zero code while the app still wants it.
    The slot is compared under the lock, so a process the app terminated (its slot already cleared) is
    never relaunched, and a normal close (code 0: Hide, or the app gone) is left alone."""
    kind = _kind(party)
    wait = getattr(proc, "wait", None)
    if wait is None:                 # not a process (a test's stand-in): nothing to supervise
        return
    code = wait()
    with _LOCK:
        if _get(kind) is not proc:
            return
        _set(kind, None)
        if code == 0:
            return
        which = {"meter": "overlay", "party": "party overlay", "radar": "radar overlay"}[kind]
        if not _RELAUNCHES.allow(time.time()):
            _log(f"the {which} ended with code {code}; not started again (five restarts in ten minutes)")
            return
        _log(f"the {which} ended with code {code}; starting it again")
        try:
            fresh = _start(url, kind)
        except Exception as err:                                              # noqa: BLE001 - report, keep serving
            _log(f"could not start the {which} again: {type(err).__name__}: {err}")
            return
        _set(kind, fresh)


def _companion_url(url: str, kind: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}view={kind}"


def _sync_companion(kind: str, wanted: bool, url: str) -> None:
    """Open or close one companion window to match its setting. The caller holds the lock."""
    if not wanted:
        _HIDDEN.discard(kind)                  # its setting went off: the next on opens it again
    if wanted and kind not in _HIDDEN:
        if not _alive(kind):
            _set(kind, _start(_companion_url(url, kind), kind))
    elif _alive(kind):
        proc = _get(kind)
        _set(kind, None)
        proc.terminate()


def sync_companions() -> None:
    """Make the companion windows match their settings while the meter overlay is open: the radar's
    window opens when the radar is turned on (Settings, or its hotkey) and closes when it is turned off,
    the Party-DPS overlay the same. Nothing happens while the meter overlay is closed; the next launch
    opens whatever is on."""
    with _LOCK:
        if not _URL or not _alive("meter"):
            return
        try:
            _sync_companion("party", _party_enabled(), _URL)
            _sync_companion("radar", _radar_enabled(), _URL)
        except Exception as err:                                              # noqa: BLE001 - report, keep serving
            _log(f"could not sync the companion overlays: {type(err).__name__}: {err}")


def close_view(kind: str) -> None:
    """A companion window's own Hide: close that window alone and keep it closed until Open overlay is
    pressed or its setting is turned off and on again. ``"meter"`` closes everything, as Hide there always did."""
    if kind not in COMPANIONS:
        close()
        return
    with _LOCK:
        _HIDDEN.add(kind)
        proc = _get(kind)
        _set(kind, None)
        if proc is not None and proc.poll() is None:
            proc.terminate()


def _ask_reload() -> None:
    """Open overlay while it is open: the overlay process reads the bumped counter on its next poll of
    ``/api/overlay/commands`` and reloads its page, whether or not that page still runs."""
    try:
        from .server import OVERLAY_COMMANDS
        OVERLAY_COMMANDS["reload_seq"] = OVERLAY_COMMANDS.get("reload_seq", 0) + 1
    except Exception:
        pass


def launch(url: str, reload_if_open: bool = False) -> dict:
    """Start the native overlay in its own process. Returns ``{"native": bool, "reason": str}``.
    The companion windows whose settings are on (the Party-DPS overlay, the radar's window) are started
    too, and ones hidden with their own Hide come back. With ``reload_if_open`` an overlay that is
    already open is asked to reload its page instead."""
    if not available():
        return {"native": False, "reason": "pywebview is not bundled on this platform"}
    global _PROCESS, _URL
    with _LOCK:
        _URL = url
        _HIDDEN.clear()
        already = _PROCESS is not None and _PROCESS.poll() is None
        try:
            if not already:
                _PROCESS = _start(url, "meter")
            elif reload_if_open:
                _ask_reload()
            # The optional companion windows are managed alongside the main one.
            _sync_companion("party", _party_enabled(), url)
            _sync_companion("radar", _radar_enabled(), url)
            return {"native": True, "already_open": already, "reason": ""}
        except Exception as err:                                              # noqa: BLE001 - report, keep serving
            _PROCESS = None
            return {"native": False, "reason": f"{type(err).__name__}: {err}"}


def close() -> None:
    """Close the native overlay(s) when the main desktop application exits."""
    global _PROCESS, _PARTY_PROCESS, _RADAR_PROCESS
    with _LOCK:
        procs = (_PROCESS, _PARTY_PROCESS, _RADAR_PROCESS)
        _PROCESS = _PARTY_PROCESS = _RADAR_PROCESS = None
        for proc in procs:
            if proc is not None and proc.poll() is None:
                proc.terminate()
