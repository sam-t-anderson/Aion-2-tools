"""The app's native interface (0.2.413, a preview): its windows drawn by Qt (PySide6) in Python instead of a browser.

Each window is its own process, as the browser window and the pywebview overlay are: it reads and changes the
app through the same local API the web pages use (``api.AppApi``), so the meter, the logs and every setting stay
where they are. ``Settings → Interface → Use the native interface`` (``interface_native``) turns it on; without
PySide6 installed, or with the setting off, the app opens its web interface as before. The pages are moved over
one at a time: a page the native window does not draw yet opens in the web interface from it.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

#: The environment variable a re-run of the installed app's executable reads to open a native window instead of
#: the app (as ``AION2CALC_OVERLAY`` opens the pywebview overlay): "window" or "overlay", the address beside it.
ENV_KIND, ENV_URL = "AION2CALC_GUI", "AION2CALC_GUI_URL"


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
    return ui.get("interface_native") is True and available()


def spawn(kind: str, url: str) -> subprocess.Popen:
    """Start a native window's process: ``kind`` "window" (the app) or "overlay" (the meter overlay), on ``url``.
    The app's own PID rides along so the window can end with the app."""
    if kind not in ("window", "overlay"):
        raise ValueError("kind must be window or overlay")
    env = {**os.environ, ENV_KIND: kind, ENV_URL: url, "AION2CALC_PARENT_PID": str(os.getpid())}
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
