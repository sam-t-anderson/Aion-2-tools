"""The measured boss skill areas the replay draws, kept fresh from the configured log server (0.2.366).

The app ships a catalog (``static/aoe-shapes.json``, measured at release time). The log server re-measures its
whole public corpus nightly and serves its own at the same path, so the app fetches that copy at most every twelve
hours into the user's data folder and serves whichever is newer at ``/static/aoe-shapes.json``; the review page
notices nothing. Everything here is best-effort: no server, no network or a bad answer leaves the bundled catalog
in place."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

from ..paths import user_data

MAX_AGE_S = 12 * 3600
LIMIT_BYTES = 4_000_000


def cache_path() -> Path:
    return user_data() / "cache" / "aoe-shapes.json"


def bundled_path() -> Path:
    return Path(__file__).resolve().parent / "static" / "aoe-shapes.json"


def _stamp(data: dict) -> str:
    meta = data.get("meta") if isinstance(data, dict) else None
    return str((meta or {}).get("generated_at") or "")


def _valid(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("shapes"), dict) and bool(data["shapes"])


def current_bytes() -> bytes:
    """The catalog to serve: the log server's copy when it is at least as new as the bundled one, else the bundled."""
    bundled = bundled_path().read_bytes()
    try:
        cached = cache_path()
        if cached.is_file():
            raw = cached.read_bytes()
            data = json.loads(raw)
            if _valid(data) and _stamp(data) >= _stamp(json.loads(bundled)):
                return raw
    except (OSError, ValueError):
        pass
    return bundled


def source() -> str:
    """Where the served catalog comes from: ``server`` or ``bundled`` (for the diagnostics)."""
    try:
        return "server" if current_bytes() is not bundled_path().read_bytes() and cache_path().is_file() and \
            _stamp(json.loads(cache_path().read_text("utf-8"))) >= _stamp(json.loads(bundled_path().read_text("utf-8"))) else "bundled"
    except (OSError, ValueError):
        return "bundled"


def refresh(force: bool = False, timeout: float = 20.0) -> str:
    """Fetch the configured log server's catalog at most every twelve hours. Returns a short status; never raises."""
    try:
        from ..combat import share
        base = str(share.effective().get("url") or "").rstrip("/")
        if not base:
            return "no-server"
        path = cache_path()
        if not force and path.is_file() and time.time() - path.stat().st_mtime < MAX_AGE_S:
            return "fresh"
        request = urllib.request.Request(base + "/static/aoe-shapes.json", headers={"User-Agent": "aion2calc"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(LIMIT_BYTES + 1)
        if len(raw) > LIMIT_BYTES:
            return "too-large"
        data = json.loads(raw)
        if not _valid(data):
            return "invalid"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(path)
        return "updated"
    except Exception as exc:                       # noqa: BLE001 - a background convenience never surfaces
        return f"failed: {type(exc).__name__}"


def refresh_later(delay: float = 20.0) -> threading.Timer:
    """Refresh off the main thread a little after launch (the app's window comes first)."""
    timer = threading.Timer(delay, refresh)
    timer.daemon = True
    timer.start()
    return timer
