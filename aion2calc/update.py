"""Check and stage GitHub releases; launch Windows installation on user request.

A newer release downloads quietly in the background while the app runs (0.2.353), the newest one when several
come out meanwhile; the app shows its progress, then offers Update now, and installs it when the app closes unless
the player turned that off. Portable/macOS/Linux downloads are offered for copying. Windows helpers wait for the
app to close, then open the installer. Disposable updater files have bounded retention; active or uninspectable
helpers and recent failure logs are preserved.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
import urllib.request
from pathlib import Path

from . import __version__
from .paths import home

RELEASES_API = "https://api.github.com/repos/sam-t-anderson/Aion-2-tools/releases/latest"
_FETCH_LOCK = threading.Lock()
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


def download(url: str, dest: Path, timeout: float = 300, progress=None) -> Path:
    """Download ``url`` to ``dest`` (through a ``.part`` file); ``progress(received, total)`` follows it, total 0
    when the server does not say."""
    req = urllib.request.Request(url, headers={
        "User-Agent": f"aion2calc/{__version__}", "Accept": "application/octet-stream"})
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        if progress is None:
            shutil.copyfileobj(r, f, 1024 * 1024)
        else:
            total, received = int(r.headers.get("Content-Length") or 0), 0
            while chunk := r.read(256 * 1024):
                f.write(chunk)
                received += len(chunk)
                progress(received, total)
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


def apply_installer(path: Path, silent: bool = True, launch: bool = True) -> bool:
    """Launch the installer after this process exits.

    Inno Setup cannot replace the running executable.  A detached PowerShell
    helper waits for our PID, then opens the staged installer.  The caller is
    responsible for shutting down the local app immediately after this returns.
    ``launch=False`` keeps a silent install from starting the app again (the
    player closed it: an update on close).
    """
    args = [str(path), "/NORESTART"]
    if silent:
        args += ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    if not launch:
        args.append("/NOLAUNCH")
    helper = home() / "updates" / f"apply-update-{uuid.uuid4().hex[:8]}.ps1"
    helper.parent.mkdir(parents=True, exist_ok=True)
    quoted_path = str(path).replace("'", "''")
    quoted_args = ", ".join("'" + arg.replace("'", "''") + "'" for arg in args[1:])
    log = str(helper.with_suffix(".log")).replace("'", "''")
    ready = helper.with_suffix(".ready")
    ready_path = str(ready).replace("'", "''")
    script = ("$ErrorActionPreference = 'Stop'\n"
              f"$log = '{log}'\n"
              "try {\n"
              f"  'helper ready; waiting for app PID {os.getpid()}' | Set-Content -LiteralPath $log\n"
              f"  'ready' | Set-Content -LiteralPath '{ready_path}'\n"
              f"  Wait-Process -Id {os.getpid()} -Timeout 30 -ErrorAction SilentlyContinue\n"
              f"  if (Get-Process -Id {os.getpid()} -ErrorAction SilentlyContinue) {{ throw 'Aion 2 Calc did not exit within 30 seconds.' }}\n"
              f"  Start-Process -FilePath '{quoted_path}' -ArgumentList @({quoted_args})\n"
              "  'installer launched' | Set-Content -LiteralPath $log\n"
              "} catch {\n"
              "  ($_ | Out-String) | Set-Content -LiteralPath $log\n"
              "  Add-Type -AssemblyName System.Windows.Forms\n"
              "  [System.Windows.Forms.MessageBox]::Show('Could not open the update installer. See ' + $log, 'Aion 2 Calc update') | Out-Null\n"
              "} finally {\n"
              f"  Remove-Item -LiteralPath '{ready_path}' -Force -ErrorAction SilentlyContinue\n"
              "  Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n"
              "}\n")
    try:
        helper.write_text(script, encoding="utf-8-sig")
        # Windows PowerShell exits silently under DETACHED_PROCESS without a console.
        # CREATE_NO_WINDOW keeps the helper independent and hidden while allowing it to run.
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        proc = subprocess.Popen([str(shell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                                 "-File", str(helper)], creationflags=flags, close_fds=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if ready.is_file():
                return True
            if proc.poll() is not None:
                return False
            time.sleep(0.05)
        proc.terminate()
    except OSError:
        return False
    return False


def cleanup_updates(current: Path | None = None) -> dict:
    """Retain two packages and bounded helper history; preserve active/unknown files."""
    from .maintenance import _files, _remove, clean_update_files, PACKAGE
    import re
    rows, _ = _files("updates")
    packages = [(p, info) for p, info in rows if re.fullmatch(PACKAGE, p.name)]
    current = current.resolve() if current else None
    packages.sort(key=lambda row: (row[0] == current, row[1].st_mtime), reverse=True)
    result = clean_update_files()
    for path, info in packages[2:]:
        result["deleted" if _remove(path, info) else "skipped"] += 1
    return result


def fetch(info: dict, progress=None) -> Path | None:
    """Download the release asset for this platform to the data folder; return its path. ``progress(received,
    total)`` follows a download that is needed."""
    asset = info.get("asset")
    if not asset or not asset.get("browser_download_url"):
        return None
    name = asset.get("name", "")
    if not name or Path(name).name != name:
        return None
    dest = home() / "updates" / name

    def valid(path):
        if not path.is_file() or path.stat().st_size == 0:
            return False
        if asset.get("size") and path.stat().st_size != asset["size"]:
            return False
        digest = asset.get("digest") or ""
        if digest.startswith("sha256:"):
            with path.open("rb") as stream:
                check = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    check.update(chunk)
                return check.hexdigest() == digest.partition(":")[2]
        return True

    with _FETCH_LOCK:
        if valid(dest):
            cleanup_updates(dest)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if progress is None:
                download(asset["browser_download_url"], dest)
            else:
                download(asset["browser_download_url"], dest, progress=progress)
            if valid(dest):
                cleanup_updates(dest)
                return dest
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def install_now() -> str:
    """Manual "Install update": download and apply. Ignores the once-per-version guard. The Windows
    installer is launched interactively so the player answers its prompts; portable, macOS and Linux
    builds are staged for the user to copy.

    It asks GitHub for the latest release when it runs, so a copy several versions behind installs
    the newest one directly, never the versions in between, even when the prompt named an older one
    (a release went out since the last check). A check that fails is not "up to date"."""
    release = latest_release()
    if release is None:
        return "check-failed"
    info = available(release)
    if not info:
        return "up-to-date"
    path = fetch(info)
    if not path:
        return "download-failed"
    if info["kind"] == "installer":
        return "launching" if apply_installer(path, silent=False) else "launch-failed"
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


# ------------------------------------------------------------------ quiet updates (0.2.353)
#: What the background download is doing, for the app's update bar: ``idle`` (nothing newer, or not checked yet),
#: ``downloading`` (``received`` of ``total`` bytes of ``version``), ``ready`` (staged at ``path``) or ``failed``
#: (tried again soon). ``launched`` once an installer helper waits for this process to exit.
_BG = {"state": "idle", "version": None, "url": None, "kind": None, "received": 0, "total": 0, "error": None,
       "path": None, "started": False, "launched": False}
_BG_WAKE = threading.Event()
#: How often the background download looks for a newer release, and how soon it retries one that failed.
CHECK_EVERY_S = 3600
RETRY_S = 300


def background_state() -> dict:
    """The background download for the page (no file path)."""
    return {k: _BG[k] for k in ("state", "version", "url", "kind", "received", "total", "error")}


def start_background() -> None:
    """Start the background download once, at the launch of a frozen build that updates itself."""
    if _BG["started"]:
        return
    _BG["started"] = True
    threading.Thread(target=_background, daemon=True, name="update-download").start()


def poke(version: str | None = None) -> None:
    """Look for a newer release now (a release check found ``version``, or the player asked); ignored when the
    background download already has that version or a newer one."""
    if not _BG["started"]:
        return
    if version is None or _BG["version"] is None or _vt(version) > _vt(_BG["version"]):
        _BG_WAKE.set()


def _background() -> None:
    while True:
        try:
            _download_newest()
        except Exception as exc:  # noqa: BLE001 - never let the updater thread die
            _BG.update(state="failed", error=f"{type(exc).__name__}: {exc}"[:200])
        _BG_WAKE.wait(RETRY_S if _BG["state"] == "failed" else CHECK_EVERY_S)
        _BG_WAKE.clear()


def _download_newest() -> None:
    """Stage the newest release for this platform, unless it is staged already: a release that comes out while an
    older one waits replaces it, so the newest one is what installs."""
    release = latest_release(timeout=10)
    if release is None:
        if _BG["state"] != "ready":
            _BG.update(state="failed", error="Could not reach GitHub for the update")
        return
    info = available(release)
    if not info or not info.get("asset"):
        if _BG["state"] != "ready":
            _BG.update(state="idle", error=None)
        return
    if _BG["state"] == "ready" and _vt(info["version"]) <= _vt(_BG["version"] or "0"):
        return
    size = int(info["asset"].get("size") or 0)
    _BG.update(state="downloading", version=info["version"], url=info.get("url"), kind=info["kind"],
               received=0, total=size, error=None, path=None)
    path = fetch(info, progress=lambda received, total: _BG.update(received=received, total=total or size))
    if path:
        _BG.update(state="ready", path=str(path), received=_BG["total"] or path.stat().st_size)
    else:
        _BG.update(state="failed", error="The download did not complete; it is tried again in a few minutes")


def install_ready() -> str:
    """Update now: the staged installer opens once the app has closed (interactively, as the player asked for it);
    without one staged, the newest release downloads first (``install_now``)."""
    if _BG["state"] == "ready" and _BG["kind"] == "installer" and _BG["path"] and Path(_BG["path"]).is_file():
        _BG["launched"] = apply_installer(Path(_BG["path"]), silent=False)
        return "launching" if _BG["launched"] else "launch-failed"
    status = install_now()
    _BG["launched"] = status == "launching"
    return status


def apply_on_close(enabled: bool) -> bool:
    """As the app exits: install the staged update quietly once it has closed, without starting the app again,
    unless the player turned "update when the app closes" off or an installer is already waiting."""
    if not enabled or _BG["launched"] or _BG["state"] != "ready" or _BG["kind"] != "installer" or not _BG["path"]:
        return False
    path = Path(_BG["path"])
    if not path.is_file():
        return False
    _BG["launched"] = apply_installer(path, silent=True, launch=False)
    return _BG["launched"]
