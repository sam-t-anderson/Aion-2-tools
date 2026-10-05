"""Launch the native transparent overlay from the running app.

The Live Meter page's "Open overlay" button posts to ``/api/overlay``; this starts the frameless,
transparent, always-on-top overlay in its own process (so pywebview owns a main thread of its own).

* Installed app (frozen): the bundled executable is re-run with ``AION2CALC_OVERLAY=1`` set, which
  :func:`aion2calc.launcher.main` routes to :func:`aion2calc.overlay.main`. pywebview is bundled on
  Windows, so this needs no Python install from the user.
* From source: ``python -m aion2calc.overlay`` is spawned instead.

When pywebview is not available the browser popup the page opens itself is the fallback, so the
response just says whether a native window was started (``{"native": true/false}``).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys


def available() -> bool:
    """Is pywebview importable in this interpreter (so a transparent window is possible)?"""
    try:
        return importlib.util.find_spec("webview") is not None
    except Exception:
        return False


def launch(url: str) -> dict:
    """Start the native overlay in its own process. Returns ``{"native": bool, "reason": str}``."""
    if not available():
        return {"native": False, "reason": "pywebview is not bundled on this platform"}
    env = {**os.environ, "AION2CALC_OVERLAY": "1", "AION2CALC_OVERLAY_URL": url}
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable], env=env, close_fds=True)      # re-run the bundle as the overlay
        else:
            subprocess.Popen([sys.executable, "-m", "aion2calc.overlay", "--url", url], env=env, close_fds=True)
        return {"native": True, "reason": ""}
    except Exception as err:                                                  # noqa: BLE001 - report, keep serving
        return {"native": False, "reason": f"{type(err).__name__}: {err}"}
