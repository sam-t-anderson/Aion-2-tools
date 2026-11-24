"""The app's native interface (0.2.413; the default since 0.2.426): its windows drawn by Qt (PySide6) in Python instead
of a browser.

Each window is its own process, as the browser window and the pywebview overlay are: it reads and changes the
app through the same local API the web pages use (``api.AppApi``), so the meter, the logs and every setting stay
where they are. ``Settings → Native interface`` (``interface_native``, on unless turned off) chooses it; with the
setting off, or without PySide6 (a requirement of the package and bundled with the builds since 0.2.426), the app
opens its web interface. Every page the window lists is native since 0.2.490, and a link to a page of the app
opens it in the window since 0.2.500.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

#: The environment variable a re-run of the installed app's executable reads to open a native window instead of
#: the app (as ``AION2CALC_OVERLAY`` opens the pywebview overlay): "window" or "overlay", the address beside it.
ENV_KIND, ENV_URL = "AION2CALC_GUI", "AION2CALC_GUI_URL"

#: A native window that ends with an error this soon after it was started failed as it started (0.2.426): Qt could not
#: open its window on this computer, say. The native interface is then given up on until the app is started again,
#: and the app and the overlay open in the web interface (:func:`mark_failed`).
FAILS_WITHIN = 10.0
_FAILED: dict = {}


def available() -> bool:
    """Whether PySide6 is installed, so the native windows can open."""
    try:
        return importlib.util.find_spec("PySide6") is not None
    except (ImportError, ValueError):
        return False


def enabled(ui: dict | None = None) -> bool:
    """Whether the app should open its native windows: the setting is on and PySide6 is there."""
    if ui is None:
        try:
            from ..app.server import ui_settings
            ui = ui_settings()
        except Exception:
            return False
    return ui.get("interface_native") is True and available() and not _FAILED


def failed() -> str:
    """Why the native interface was given up on in this run of the app (:func:`mark_failed`); "" while it was not."""
    return _FAILED.get("reason", "")


def mark_failed(reason: str) -> None:
    """Give up on the native interface until the app is started again: a native window failed as it started, so the
    app and the overlay open in the web interface instead (0.2.426). The first reason is kept."""
    _FAILED.setdefault("reason", reason)


def failed_at_start(proc, within: float | None = None) -> int | None:
    """The exit code of a native window's process that ended with an error within ``within`` seconds of its start
    (``FAILS_WITHIN``), else None: it runs on, or it was closed normally. Waits for up to that long."""
    wait = getattr(proc, "wait", None)
    if wait is None:                              # not a process (a test's stand-in)
        return None
    try:
        code = wait(timeout=FAILS_WITHIN if within is None else within)
    except subprocess.TimeoutExpired:
        return None
    return code or None


def spawn(kind: str, url: str, parent_pid: int | None = None) -> subprocess.Popen:
    """Start a native window's process: ``kind`` "window" (the app) or "overlay" (the meter overlay), on ``url``.
    The app's PID rides along so the window can end with the app: this process's, or ``parent_pid`` when the app
    runs in another (0 when it is not known: the window is then not tied to a process)."""
    if kind not in ("window", "overlay"):
        raise ValueError("kind must be window or overlay")
    pid = os.getpid() if parent_pid is None else parent_pid
    env = {**os.environ, ENV_KIND: kind, ENV_URL: url, "AION2CALC_PARENT_PID": str(pid) if pid else ""}
    if getattr(sys, "frozen", False):
        return subprocess.Popen([sys.executable], env=env, close_fds=True)
    module = "aion2calc.gui" if kind == "window" else "aion2calc.gui.overlay"
    return subprocess.Popen([sys.executable, "-m", module, "--url", url], env=env, close_fds=True)


def run_from_env() -> int:
    """The installed app's executable re-run for a native window (``ENV_KIND``): open it and return its exit code."""
    kind, url = os.environ.get(ENV_KIND), os.environ.get(ENV_URL) or ""
    if kind == "overlay":
        from .overlay import main
    else:
        from .window import main
    return main(["--url", url] if url else [])
