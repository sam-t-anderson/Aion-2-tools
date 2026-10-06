"""Self-update from GitHub Releases.

The desktop app checks the latest release on launch and, when a newer one exists,
updates itself. The **Windows installer** build is applied silently (the new
setup.exe runs with ``/VERYSILENT``, replaces the files and relaunches). The
portable, macOS and Linux builds are downloaded and offered for the user to copy
over, because silently self-replacing a running app is not reliable there. Auto
apply can be turned off in Settings; a manual "Install update" always works.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import __version__
from .paths import home

RELEASES_API = "https://api.github.com/repos/sam-t-anderson/Aion-2-tools/releases/latest"
_STATE = "update_state.json"          # remembers the version we last tried, so a failed apply does not loop


def _vt(v) -> tuple:
    return tuple(int(x) for x in str(v).split(".")[:3] if x.isdigit())


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_kind() -> str:
    """How this copy was installed: ``installer`` / ``portable`` (Windows), ``macapp``,
    ``linux``, or ``source`` (run from a checkout)."""
    if not frozen():
        return "source"
    if sys.platform == "win32":
        exe = str(Path(sys.executable)).lower().replace("\\", "/")
        la = os.environ.get("LOCALAPPDATA", "").lower().replace("\\", "/").rstrip("/")
        return "installer" if la and exe.startswith(la + "/programs/") else "portable"
    if sys.platform == "darwin":
        return "macapp"
    return "linux"


def latest_release(timeout: float = 5) -> dict | None:
    try:
        req = urllib.request.Request(RELEASES_API, headers={
            "Accept": "application/vnd.github+json", "User-Agent": f"aion2calc/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def _asset_match(kind: str):
    return {
        "installer": lambda n: n.startswith("aion2calc-setup-") and n.endswith(".exe"),
        "portable": lambda n: "windows-portable" in n and n.endswith(".zip"),
        "macapp": lambda n: n.endswith("-macos.zip"),
        "linux": lambda n: n.endswith("-linux.tar.gz"),
    }.get(kind)


def pick_asset(release: dict, kind: str) -> dict | None:
    match = _asset_match(kind)
    if not match:
        return None
    return next((a for a in release.get("assets", []) if match(a.get("name", ""))), None)


def available(release: dict | None = None) -> dict | None:
    """``{version, url, asset, kind, silent}`` if a newer release exists for this platform, else None."""
    rel = release if release is not None else latest_release()
    if not rel:
        return None
    ver = str(rel.get("tag_name") or "").lstrip("v")
    if not ver or _vt(ver) <= _vt(__version__):
        return None
    kind = install_kind()
    asset = pick_asset(rel, kind)
    return {"version": ver, "url": rel.get("html_url"), "asset": asset, "kind": kind,
            "silent": kind == "installer" and asset is not None}


def download(url: str, dest: Path, timeout: float = 300) -> Path:
    req = urllib.request.Request(url, headers={
        "User-Agent": f"aion2calc/{__version__}", "Accept": "application/octet-stream"})
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1024 * 1024)
    tmp.replace(dest)
    return dest


def _state() -> dict:
    p = home() / _STATE
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def _save_state(d: dict) -> None:
    try:
        (home() / _STATE).write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def apply_installer(path: Path, silent: bool = True) -> bool:
    """Launch the installer after this process exits.

    Inno Setup cannot replace the running executable.  A detached PowerShell
    helper waits for our PID, then opens the staged installer.  The caller is
    responsible for shutting down the local app immediately after this returns.
    """
    args = [str(path)]
    if silent:
        args += ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    args += ["/MERGETASKS=!desktopicon"]
    helper = home() / "updates" / "apply-update.ps1"
    helper.parent.mkdir(parents=True, exist_ok=True)
    quoted_path = str(path).replace("'", "''")
    quoted_args = ", ".join("'" + arg.replace("'", "''") + "'" for arg in args[1:])
    log = str(helper.with_suffix(".log")).replace("'", "''")
    script = ("$ErrorActionPreference = 'Stop'\n"
              f"$log = '{log}'\n"
              "try {\n"
              f"  Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
              f"  Start-Process -FilePath '{quoted_path}' -ArgumentList @({quoted_args})\n"
              "  'installer launched' | Set-Content -LiteralPath $log\n"
              "} catch {\n"
              "  ($_ | Out-String) | Set-Content -LiteralPath $log\n"
              "}\n")
    try:
        helper.write_text(script, encoding="utf-8")
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                          "-File", str(helper)], creationflags=flags, close_fds=True)
        return True
    except OSError:
        return False


def fetch(info: dict) -> Path | None:
    """Download the release asset for this platform to the data folder; return its path."""
    asset = info.get("asset")
    if not asset or not asset.get("browser_download_url"):
        return None
    dest = home() / "updates" / asset["name"]
    if dest.exists() and dest.stat().st_size > 0:
        return dest                   # already staged this version: don't re-download on every launch
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        return download(asset["browser_download_url"], dest)
    except Exception:
        return None


def install_now() -> str:
    """Manual "Install update": download and apply. Ignores the once-per-version guard. The Windows
    installer is launched interactively so a SmartScreen / install prompt on the unsigned build can be
    approved; portable, macOS and Linux builds are staged for the user to copy."""
    info = available()
    if not info:
        return "up-to-date"
    path = fetch(info)
    if not path:
        return "download-failed"
    if info["kind"] == "installer" and apply_installer(path, silent=False):
        return "launching"            # the installer window opens; it closes and relaunches the app
    return "downloaded"               # the UI reveals the file for the user to run/copy


def auto_update(quit_cb=None) -> str:
    """On launch (frozen builds): download a newer release in the background so the app can offer a
    one-click install via the header chip / Settings. We no longer apply it silently and quit: a fully
    silent apply of an *unsigned* installer can be blocked by Windows with no prompt, which looked like
    the app closing and nothing happening. The interactive "Install now" is the reliable path. Never
    raises. ``quit_cb`` is accepted for backwards compatibility and no longer used."""
    try:
        info = available()
        if not info:
            return "up-to-date"
        return "downloaded" if fetch(info) else "download-failed"
    except Exception:
        return "error"
