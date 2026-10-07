"""User-initiated installer flow for the separately licensed Npcap driver.

Npcap's free edition cannot be redistributed with this application.  This
module therefore discovers the current official installer only after the user
has chosen to install it in the Live Meter UI, downloads it from npcap.com,
and opens its normal interactive installer.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import urllib.request

from ..paths import home

_PAGE = "https://npcap.com/"
_MATCH = re.compile(r"(?:https?://npcap\.com/|/)?dist/(npcap-([0-9.]+)\.exe)", re.I)
_LOCK = threading.RLock()
_STATE: dict[str, object] = {"status": "idle", "version": None, "error": None}


def _installed_state() -> tuple[bool | None, str | None]:
    """Read service registration without launching a process or requesting elevation."""
    if sys.platform != "win32":
        return False, None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\npcap"):
            return True, None
    except FileNotFoundError:
        return False, None
    except (OSError, ImportError) as exc:
        return None, "Could not read Npcap's service registration: " + str(exc)


def installed() -> bool:
    """Whether the Npcap service is registered; not a capture-permission check."""
    return _installed_state()[0] is True


def status() -> dict:
    with _LOCK:
        state = dict(_STATE)
    present, error = _installed_state()
    return {"supported": sys.platform == "win32", "installed": present, "detection_error": error, **state}


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
        # CreateProcess cannot launch an elevation-required installer (WinError 740).
        # ShellExecute's runas verb asks Windows to display the normal UAC prompt.
        os.startfile(str(target), "runas", cwd=str(folder))
        _set(status="installer-opened", version=version)
    except Exception as err:  # the UI receives a concise, actionable status
        if getattr(err, "winerror", None) in (5, 740, 1223):
            message = ("Npcap installation needs administrator approval. Windows denied or cancelled the elevation request. "
                       "Choose Install Npcap again and approve the UAC prompt, or ask your administrator to install Npcap.")
        else:
            message = f"{type(err).__name__}: {err}"
        _set(status="error", error=message)


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
