"""Upload a saved fight to a log server that accepts the a2log format.

The server address and upload key are kept in the user folder
(``data/logserver.json``); set them in the app (Combat Logs page) or with
``python -m aion2calc share --server https://logs.example.com --key a2l_...``.
"""
from __future__ import annotations

import gzip
import json
import re
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
_OBSOLETE_HOST = "try" + "cloudflare.com"  # retired quick-tunnel host


def settings() -> dict:
    """The user's own saved log-server settings (empty until they save any)."""
    if not data_file(*_FILE).exists():
        return {}
    settings = read_json(*_FILE)
    # Retired quick-tunnel addresses expire. Migrate an old saved choice so it cannot
    # indefinitely override the project's live Tailscale default.
    if _OBSOLETE_HOST in str(settings.get("url", "")).casefold():
        replacement = _bundled_default().get("url", "")
        if replacement:
            settings["url"] = replacement.rstrip("/")
            write_user_json(settings, *_FILE)
    return settings


def _remote_default(max_age: float = 21600) -> dict:
    """The repo's default_server.json, fetched and cached ~6h, so a changed Tailscale
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
    client = _client_json()
    for src in (_remote_default(), _bundled_default(), client):
        if src.get("url") and _OBSOLETE_HOST not in str(src["url"]).casefold():
            result = {"url": src["url"].rstrip("/"), "visibility": src.get("visibility") or "unlisted"}
            # The deliberately public community-upload key is scoped to its
            # configured server. Never transfer it to a changed/custom server.
            if client.get("key") and str(client.get("url") or "").rstrip("/") == result["url"]:
                result["key"] = client["key"]
            return result
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
            return {"url": c.get("logserver_url"), "visibility": c.get("visibility"), "key": c.get("key")}
        except ValueError:
            return {}
    return {}


def effective() -> dict:
    """The server actually used: the user's saved settings, or the project default when they have
    not chosen one. ``is_default`` marks which it is (so the UI can show it)."""
    s = settings()
    if s.get("url"):
        if not s.get("key"):
            d = default_server()
            if str(s["url"]).rstrip("/") == d.get("url") and d.get("key"):
                s = {**s, "key":d["key"]}
        return {**s, "is_default": False}
    d = default_server()
    if d.get("url"):
        return {**d, "key": s.get("key") or d.get("key"), "is_default": True}
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


def upload(doc: dict, url: str | None = None, key: str | None = None, visibility: str | None = None, request_id: str | None = None) -> dict:
    s = effective()
    url = (url or s.get("url") or "").rstrip("/")
    key = key or (s.get("key") if url == str(s.get("url") or "").rstrip("/") else None)
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
    if request_id is not None:
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise ValueError("Invalid upload request ID")
        headers["Idempotency-Key"] = request_id
    req = urllib.request.Request(f"{target}?visibility={vis}", body, headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.load(r)
        from .ownership import remember
        try:
            if not result.get("replayed"):
                remember(url,result,doc.get("meta",{}).get("title", ""))
        except (OSError, ValueError, KeyError) as exc:
            result["ownership_warning"] = "Uploaded, but could not save ownership locally: " + str(exc)
        return result
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(msg).get("error", msg)
        except ValueError:
            pass
        raise RuntimeError(f"upload refused ({e.code}): {msg}") from None


def plan_request(plan: dict | None = None, visibility: str = "unlisted", plan_id: str | None = None, owner: dict | None = None) -> dict:
    """Publish/browse plans using the desktop's configured server and upload key."""
    from urllib.parse import quote
    settings = effective()
    base = (settings.get("url") or "").rstrip("/")
    if not base:
        raise ValueError("Set the share server in Settings before publishing or browsing plans.")
    target = base + "/api/v1/plans"
    headers = {"User-Agent": "aion2calc"}
    body = None
    method = "GET"
    summary = None
    if owner:
        if str(owner.get("server") or "").rstrip("/") != base:
            raise ValueError("Choose the original publication server before using this ownership credential")
        headers["X-Plan-Token"] = str(owner.get("edit_token") or "")
    if plan is not None:
        if visibility not in ("public", "unlisted", "private"):
            raise ValueError("visibility must be public, unlisted or private")
        if not isinstance(plan, dict) or plan.get("format") != "a2plan":
            raise ValueError("Not an a2plan document")
        if owner:
            plan_id = str(owner.get("id") or "")
            if not plan_id.isalnum() or not 6 <= len(plan_id) <= 16:
                raise ValueError("Invalid published plan ID")
            target += "/" + plan_id
            headers["If-Match"] = str(int(owner["revision"]))
            method = "PUT"
        else:
            method = "POST"
        target += "?visibility=" + visibility
        body = json.dumps(plan, separators=(",", ":"), allow_nan=False).encode()
        if len(body) > 5 * 1024 * 1024:
            raise ValueError("Plan exceeds 5 MiB")
        headers["Content-Type"] = "application/json"
        if settings.get("key"):
            headers["Authorization"] = "Bearer " + settings["key"]
    elif plan_id is not None:
        if not plan_id.isalnum():
            raise ValueError("Invalid plan ID")
        target += "/" + quote(plan_id, safe="")
        summary_target = target if owner else None
        target += "/raw"
    try:
        if owner and plan is None and plan_id:
            with urllib.request.urlopen(urllib.request.Request(summary_target, headers=headers), timeout=30) as response:
                summary = json.load(response)
        request = urllib.request.Request(target, body, headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            doc = json.load(response)
            return {"plan": doc, "revision": summary["revision"]} if owner and plan is None and plan_id else doc
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        try:
            text = json.loads(text).get("error", text)
        except ValueError:
            pass
        raise RuntimeError(f"Plan server refused ({err.code}): {text}") from None


def community_request(path: str, body: dict | None = None) -> dict:
    """Read community reports or preview local ranks through the configured server."""
    import re
    allowed = re.fullmatch(r"/api/v1/(news|boss-status|run-leaderboard|encounter-progression|progression|report-facets|performance|records|logs|logs/[A-Za-z0-9]{6,16}/(raw|rankings|reports)|rankings)(\?[^#]*)?", path)
    if not allowed or (body is not None and path not in ("/api/v1/rankings", "/api/v1/progression") and not re.fullmatch(r"/api/v1/logs/[A-Za-z0-9]{6,16}/reports",path)):
        raise ValueError("Invalid community API path")
    settings = effective()
    base = str(settings.get("url") or "").rstrip("/")
    if not base:
        raise ValueError("Set a community server in Settings")
    headers = {"User-Agent": "aion2calc"}
    if settings.get("key"):
        headers["Authorization"] = "Bearer " + settings["key"]
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body, allow_nan=False).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, payload, headers), timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read()).get("error", exc.reason)
        except ValueError:
            message = exc.reason
        raise RuntimeError(f"Community server ({exc.code}): {message}") from None


def submit_preset(summary: dict) -> dict:
    """Send only anonymous allocations and rotation. The server recomputes all scores."""
    if (summary.get("genus") or {}).get("stats"):
        return {"submitted": False, "reason": "Personal Genus builds remain local; shared presets use a common loadout."}
    if summary.get("skill_reserves"):
        return {"submitted": False, "reason": "Personal skill-reserve builds remain local; shared presets compare damage-only objectives."}
    if summary.get("survival"):
        return {"submitted": False, "reason": "HP-reserve builds remain local; shared presets currently compare damage-only objectives."}
    if str(summary.get("scenario", "")).startswith("pvp"):
        return {"submitted": False, "reason": "Experimental PvP builds are stored locally; PvE community presets are separate."}
    from ..presets import MAX_BYTES, candidate
    s = effective()
    base = (s.get("url") or "").rstrip("/")
    if not base:
        return {"submitted": False, "reason": "No community server configured."}
    body = json.dumps(candidate(summary), separators=(",", ":"), allow_nan=False).encode()
    if len(body) > MAX_BYTES:
        return {"submitted": False, "reason": "Build submission is too large."}
    headers = {"Content-Type": "application/json", "User-Agent": "aion2calc"}
    if s.get("key"):
        headers["Authorization"] = "Bearer " + s["key"]
    try:
        req = urllib.request.Request(base + "/api/v1/presets", body, headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as response:
            return {"submitted": True, **json.load(response)}
    except Exception as err:
        return {"submitted": False, "reason": f"Community server unavailable: {err}"}


def sync_presets() -> list[str]:
    """Refresh validated class presets atomically; cached builds remain usable offline."""
    from ..paths import list_names, write_user_json
    from ..presets import MAX_BYTES, candidate, parse
    base = (effective().get("url") or "").rstrip("/")
    if not base:
        return []
    changed = []
    try:
        with urllib.request.urlopen(base + "/api/v1/presets", timeout=8) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return []
            rows = json.loads(raw).get("presets", [])
        if not isinstance(rows, list):
            return []
        classes = set(list_names("global", "classes"))
        for row in rows[:len(classes)]:
            if not isinstance(row, dict):
                continue
            cls = row.get("class_name") or row.get("class")
            if cls not in classes:
                continue
            try:
                cached = read_json("community_presets", f"{cls}.json")
            except (OSError, ValueError):
                cached = {}
            if cached.get("source") == base and cached.get("updated_at") == row.get("updated_at"):
                continue
            try:
                with urllib.request.urlopen(base + "/api/v1/presets/" + cls, timeout=8) as response:
                    raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    continue
                remote = json.loads(raw)
                summary = remote["build"]
                if summary.get("class") != cls or summary.get("loadout") != f"{cls}_l45_global_median":
                    continue
                parse(candidate(summary))
                # The source is trusted for score computation; never import a character loadout path.
                write_user_json({"source": base, "updated_at": remote["updated_at"], "build": summary},
                                "community_presets", f"{cls}.json")
                changed.append(cls)
            except (OSError, ValueError, KeyError, TypeError):
                continue
    except (OSError, ValueError, TypeError):
        pass
    return changed


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
