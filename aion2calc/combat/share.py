"""Upload a saved fight to a log server that accepts the a2log format.

The server address and upload key are kept in the user folder
(``data/logserver.json``); set them in the app (Combat Logs page) or with
``python -m aion2calc share --server https://logs.example.com --key a2l_...``.
"""
from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request

from ..db import store
from .a2log import from_encounter, validate
from ..paths import data_file, read_json, write_user_json

_FILE = ("logserver.json",)


#: the project's default log server for new users, updatable without a rebuild (clients read the
#: committed file at runtime). A user's own choice in Settings always overrides it.
DEFAULT_SERVER_RAW = ("https://raw.githubusercontent.com/sam-t-anderson/Aion-2-tools/"
                      "main/aion2calc/data/global/default_server.json")
_DEFAULT_CACHE = ("cache", "default_server.json")


def settings() -> dict:
    """The user's own saved log-server settings (empty until they save any)."""
    return read_json(*_FILE) if data_file(*_FILE).exists() else {}


def _remote_default(max_age: float = 21600) -> dict:
    """The repo's default_server.json, fetched and cached ~6h, so a changed (e.g. quick-tunnel)
    URL reaches clients without a new build. Falls back to the last cache, then nothing."""
    import time
    p = data_file(*_DEFAULT_CACHE)
    if p.exists() and time.time() - p.stat().st_mtime < max_age:
        try:
            return read_json(*_DEFAULT_CACHE)
        except ValueError:
            pass
    try:
        with urllib.request.urlopen(DEFAULT_SERVER_RAW, timeout=5) as r:
            d = json.load(r)
        write_user_json(d, *_DEFAULT_CACHE)
        return d
    except Exception:
        try:
            return read_json(*_DEFAULT_CACHE) if p.exists() else {}
        except ValueError:
            return {}


def default_server() -> dict:
    """Where new users share by default: the remote default, else the bundled one, else a
    ``client.json`` baked in by a build (A2LOGS_PUBLIC_URL). ``{}`` if none is configured."""
    for src in (_remote_default(), _bundled_default(), _client_json()):
        if src.get("url"):
            return {"url": src["url"].rstrip("/"), "visibility": src.get("visibility") or "unlisted"}
    return {}


def _bundled_default() -> dict:
    try:
        return read_json("global", "default_server.json")
    except (FileNotFoundError, ValueError):
        return {}


def _client_json() -> dict:
    from ..paths import resource_root
    p = resource_root() / "client.json"
    if p.exists():
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            return {"url": c.get("logserver_url"), "visibility": c.get("visibility")}
        except ValueError:
            return {}
    return {}


def effective() -> dict:
    """The server actually used: the user's saved settings, or the project default when they have
    not chosen one. ``is_default`` marks which it is (so the UI can show it)."""
    s = settings()
    if s.get("url"):
        return {**s, "is_default": False}
    d = default_server()
    if d.get("url"):
        return {**d, "key": s.get("key"), "is_default": True}
    return {"is_default": False}


def save_settings(url: str | None = None, key: str | None = None, visibility: str | None = None) -> dict:
    s = settings()
    if url is not None:
        s["url"] = url.rstrip("/")
    if key is not None:
        s["key"] = key
    if visibility is not None:
        s["visibility"] = visibility
    write_user_json(s, *_FILE)
    return s


def discover(url: str) -> dict:
    """The server's /.well-known/a2log.json (upload URL, auth, limits)."""
    with urllib.request.urlopen(url.rstrip("/") + "/.well-known/a2log.json", timeout=20) as r:
        return json.load(r)


def upload(doc: dict, url: str | None = None, key: str | None = None, visibility: str | None = None) -> dict:
    s = effective()
    url = (url or s.get("url") or "").rstrip("/")
    key = key or s.get("key")
    vis = visibility or s.get("visibility") or "unlisted"
    if not url:
        raise ValueError("no log server set: pass --server (or set it on the Combat Logs page)")
    doc = validate(doc)
    try:
        target = discover(url).get("upload_url") or url + "/api/v1/logs"
    except Exception:
        target = url + "/api/v1/logs"
    body = gzip.compress(json.dumps(doc, separators=(",", ":")).encode())
    headers = {"Content-Type": "application/json", "Content-Encoding": "gzip", "User-Agent": "aion2calc"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(f"{target}?visibility={vis}", body, headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(msg).get("error", msg)
        except ValueError:
            pass
        raise RuntimeError(f"upload refused ({e.code}): {msg}") from None


def fight_stats(enc: dict) -> dict:
    """The player's stats during the fight, from the equipment snapshot nearest before it
    (lets the log server calibrate crit and the other rates). Empty when unknown."""
    try:
        from dataclasses import replace

        from .. import learn
        from ..run import prepare
        from ..scenarios import SCENARIOS
        m = enc["meta"]
        snap = store.snapshot_for(store.connect(), m.get("player") or "", m.get("class"), learn._ts(enc))
        if not snap:
            return {}
        with learn.uncalibrated():
            b = learn._build_of(m["class"], snap["data"], enc)
            scen = SCENARIOS["boss"](snap["data"]["loadout"])
            scen = replace(scen, config=replace(scen.config, duration=max(10.0, m.get("duration") or 60)))
            _, _, _, stats = prepare(b, scen)
            d = stats.derived()
        return {"critical_hit": round(d.crit_stat, 1), "attack": round(d.attack(), 1),
                "double_pct": round(100 * d.double, 2), "perfect_pct": round(100 * d.perfect, 2),
                "multihit_pct": round(100 * d.multihit, 2), "combat_speed_pct": round(100 * d.combat_speed, 2),
                "cooldown_pct": round(100 * d.cdr, 2), "accuracy": round(d.accuracy, 1)}
    except Exception:
        return {}


def share_encounter(enc_id: int, **kw) -> dict:
    enc = store.encounter(store.connect(), enc_id)
    if not enc:
        raise FileNotFoundError(f"no encounter {enc_id}")
    res = upload(from_encounter(enc, stats=fight_stats(enc)), **kw)
    links = settings().get("shared", {})
    links[str(enc_id)] = res.get("url")
    s = settings()
    s["shared"] = links
    write_user_json(s, *_FILE)
    return res
