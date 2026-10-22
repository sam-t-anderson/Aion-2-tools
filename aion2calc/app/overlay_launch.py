"""Launch the native transparent overlay from the running app, and keep it running.

The Live Meter page's "Open overlay" button posts to ``/api/overlay``; this starts the frameless,
transparent, always-on-top overlay in its own process (so pywebview owns a main thread of its own).

* Installed app (frozen): the bundled executable is re-run with ``AION2CALC_OVERLAY=1`` set, which
  :func:`aion2calc.launcher.main` routes to :func:`aion2calc.overlay.main`. pywebview is bundled on
  Windows, so this needs no Python install from the user.
* From source: ``python -m aion2calc.overlay`` is spawned instead.

When pywebview is not available the browser popup the page opens itself is the fallback, so the
response just says whether a native window was started (``{"native": true/false}``).

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
_LOCK = threading.Lock()
_RELAUNCHES = RelaunchLimiter()


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


def _start(url: str, party: bool) -> subprocess.Popen:
    """Spawn one overlay process and watch it. The caller holds the lock and stores the result."""
    proc = _spawn(url)
    threading.Thread(target=_watch, args=(proc, url, party), daemon=True,
                     name="overlay-supervisor" + ("-party" if party else "")).start()
    return proc


def _watch(proc: subprocess.Popen, url: str, party: bool) -> None:
    """Relaunch an overlay process that ended by itself with a non-zero code while the app still wants it.
    The slot is compared under the lock, so a process the app terminated (its slot already cleared) is
    never relaunched, and a normal close (code 0: Hide, or the app gone) is left alone."""
    global _PROCESS, _PARTY_PROCESS
    wait = getattr(proc, "wait", None)
    if wait is None:                 # not a process (a test's stand-in): nothing to supervise
        return
    code = wait()
    with _LOCK:
        if (_PARTY_PROCESS if party else _PROCESS) is not proc:
            return
        if party:
            _PARTY_PROCESS = None
        else:
            _PROCESS = None
        if code == 0:
            return
        which = "party overlay" if party else "overlay"
        if not _RELAUNCHES.allow(time.time()):
            _log(f"the {which} ended with code {code}; not started again (five restarts in ten minutes)")
            return
        _log(f"the {which} ended with code {code}; starting it again")
        try:
            fresh = _start(url, party)
        except Exception as err:                                              # noqa: BLE001 - report, keep serving
            _log(f"could not start the {which} again: {type(err).__name__}: {err}")
            return
        if party:
            _PARTY_PROCESS = fresh
        else:
            _PROCESS = fresh


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
    When the separate Party-DPS overlay is enabled, a second window is started too. With
    ``reload_if_open`` an overlay that is already open is asked to reload its page instead."""
    if not available():
        return {"native": False, "reason": "pywebview is not bundled on this platform"}
    global _PROCESS, _PARTY_PROCESS
    with _LOCK:
        already = _PROCESS is not None and _PROCESS.poll() is None
        try:
            if not already:
                _PROCESS = _start(url, False)
            elif reload_if_open:
                _ask_reload()
            # The optional party overlay is managed alongside the main one.
            if _party_enabled():
                if _PARTY_PROCESS is None or _PARTY_PROCESS.poll() is not None:
                    sep = "&" if "?" in url else "?"
                    _PARTY_PROCESS = _start(f"{url}{sep}view=party", True)
            elif _PARTY_PROCESS is not None and _PARTY_PROCESS.poll() is None:
                proc, _PARTY_PROCESS = _PARTY_PROCESS, None
                proc.terminate()
            return {"native": True, "already_open": already, "reason": ""}
        except Exception as err:                                              # noqa: BLE001 - report, keep serving
            _PROCESS = None
            return {"native": False, "reason": f"{type(err).__name__}: {err}"}


def close() -> None:
    """Close the native overlay(s) when the main desktop application exits."""
    global _PROCESS, _PARTY_PROCESS
    with _LOCK:
        procs, _PROCESS, _PARTY_PROCESS = (_PROCESS, _PARTY_PROCESS), None, None
        for proc in procs:
            if proc is not None and proc.poll() is None:
                proc.terminate()
