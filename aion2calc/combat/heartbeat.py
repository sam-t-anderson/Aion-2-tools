"""Anonymous daily usage heartbeat — the community "daily active meters" signal.

At most one tiny, anonymous beacon per UTC day tells the configured community log
server that *a* meter ran today, so the public stats can show a daily-active count.
It is **opt-out** (on by default) and carries **no** personal, account, character,
server, IP-derived or capture data — only:

* a per-day **rotating token**, ``sha256(install_salt + ":" + utc_date)``, that is
  different every day and not reversible to the install. The salt is random,
  generated once and kept **locally** (never sent), so the server sees an opaque
  token it cannot correlate across days or back to a machine;
* today's UTC date; and
* the client version.

The server counts distinct daily tokens into a retention-bounded aggregate and
exposes only the count. ``send`` is best-effort and never raises: a failure (or a
server that does not yet implement the endpoint) simply means no count today.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import secrets
import urllib.request

from .. import __version__
from ..paths import data_file, read_json, write_user_json
from . import share

_SALT_FILE = ("community", "install.json")
_MARK_FILE = ("community", "heartbeat.json")
_ENDPOINT = "/api/v1/heartbeat"


def _utc_date() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _install_salt() -> str:
    """A random per-install salt, generated once and kept locally. Never sent."""
    try:
        if data_file(*_SALT_FILE).exists():
            salt = read_json(*_SALT_FILE).get("salt")
            if isinstance(salt, str) and len(salt) >= 16:
                return salt
    except Exception:
        pass
    salt = secrets.token_hex(16)
    try:
        write_user_json({"salt": salt}, *_SALT_FILE)
    except Exception:
        pass
    return salt


def daily_token(date: str | None = None) -> str:
    """An anonymous token for the given UTC day — different each day, not reversible
    to the install, so it cannot be correlated across days or back to a person."""
    date = date or _utc_date()
    return hashlib.sha256(f"{_install_salt()}:{date}".encode("utf-8")).hexdigest()[:24]


def enabled(ui: dict | None = None) -> bool:
    """Opt-out: contribute unless the user explicitly turned it off."""
    if ui is None:
        try:
            from ..app import server
            ui = server.ui_settings()
        except Exception:
            ui = {}
    return ui.get("community_heartbeat", True) is not False


def _already_sent_today() -> bool:
    try:
        return data_file(*_MARK_FILE).exists() and read_json(*_MARK_FILE).get("date") == _utc_date()
    except Exception:
        return False


def payload(date: str | None = None) -> dict:
    """The exact anonymous body posted — token, date and client version only."""
    date = date or _utc_date()
    return {"token": daily_token(date), "date": date, "client": __version__}


def send(force: bool = False, ui: dict | None = None) -> str:
    """Post today's heartbeat at most once per UTC day, best-effort. Returns a short
    status string and never raises — a failure just means no count today."""
    try:
        if not enabled(ui):
            return "disabled"
        if not force and _already_sent_today():
            return "already"
        server = share.effective()
        base = str(server.get("url") or "").rstrip("/")
        if not base:
            return "no-server"
        body = json.dumps(payload()).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "aion2calc"}
        key = server.get("key")
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(base + _ENDPOINT, body, headers, method="POST")
        with urllib.request.urlopen(req, timeout=8) as response:
            response.read()
        write_user_json({"date": _utc_date()}, *_MARK_FILE)
        return "sent"
    except Exception as exc:   # a beacon must never affect the app
        return "error:" + type(exc).__name__
