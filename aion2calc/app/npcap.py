"""User-initiated installer flow for the separately licensed Npcap driver.

Npcap's free edition cannot be redistributed with this application.  This
module therefore discovers the current official installer only after the user
has chosen to install it in the Live Meter UI, downloads it from npcap.com,
and opens its normal interactive installer.
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import urllib.request

from ..paths import home

_PAGE = "https://npcap.com/"
_MATCH = re.compile(r"(?:https?://npcap\.com/|/)?dist/(npcap-([0-9.]+)\.exe)", re.I)
_LOCK = threading.RLock()
_STATE: dict[str, object] = {"status": "idle", "version": None, "error": None}


def _creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def installed() -> bool:
    """Whether Windows reports the Npcap service as installed."""
    if sys.platform != "win32":
        return False
    try:
        return subprocess.run(["sc.exe", "query", "npcap"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=3,
                              creationflags=_creation_flags()).returncode == 0
    except OSError:
        return False


def status() -> dict:
    with _LOCK:
        state = dict(_STATE)
    return {"supported": sys.platform == "win32", "installed": installed(), **state}


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _latest() -> tuple[str, str]:
    request = urllib.request.Request(_PAGE, headers={"User-Agent": "aion2calc Npcap setup"})
    with urllib.request.urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", "replace")
    choices = [(version, f"https://npcap.com/dist/{filename}")
               for filename, version in _MATCH.findall(page)]
    if not choices:
        raise RuntimeError("could not find the official Npcap installer")
    return max(choices, key=lambda row: _version_key(row[0]))


def _set(**values) -> None:
    with _LOCK:
        _STATE.update(values)


def _download_and_open() -> None:
    try:
        _set(status="finding", error=None)
        version, url = _latest()
        folder = home() / "drivers"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"npcap-{version}.exe"
        if not target.exists() or target.stat().st_size == 0:
            _set(status="downloading", version=version)
            temporary = target.with_suffix(".exe.part")
            request = urllib.request.Request(url, headers={"User-Agent": "aion2calc Npcap setup"})
            with urllib.request.urlopen(request, timeout=300) as response, open(temporary, "wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            temporary.replace(target)
        _set(status="opening", version=version)
        subprocess.Popen([str(target)], cwd=str(folder), creationflags=_creation_flags())
        _set(status="installer-opened", version=version)
    except Exception as err:  # the UI receives a concise, actionable status
        _set(status="error", error=f"{type(err).__name__}: {err}")


def begin_install() -> dict:
    """Start the official interactive installer after an explicit UI confirmation."""
    if sys.platform != "win32":
        return {"supported": False, "status": "unsupported", "error": "Npcap is only needed on Windows"}
    with _LOCK:
        if _STATE.get("status") in {"finding", "downloading", "opening"}:
            return status()
        _STATE.update(status="finding", version=None, error=None)
    threading.Thread(target=_download_and_open, daemon=True, name="npcap-setup").start()
    return status()


def install_now() -> dict:
    """Download and open Npcap synchronously for the installer post-install action."""
    if sys.platform != "win32":
        return {"supported": False, "status": "unsupported", "error": "Npcap is only needed on Windows"}
    _download_and_open()
    return status()
