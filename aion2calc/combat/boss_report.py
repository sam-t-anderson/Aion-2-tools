"""Opt-in, anonymous standalone boss-kill auto-report — the community
"world boss availability" signal without a full log upload.

When the meter finalises a session that contains a confirmed **open-world**
boss defeat, and only if the user has turned this on, we post one tiny,
anonymous report of that kill to the configured community server's
``/api/v1/boss-kill`` endpoint. It carries no account, character, IP-derived
or capture data — only what the kill feed needs to place and merge it:

* an anonymous, stable **per-install reporter key**, ``sha256(install_salt +
  ":boss-reporter")`` truncated, derived from the same random, local-only
  salt the heartbeat uses (the salt is never sent, and the key is distinct
  from the daily heartbeat token). Every install has its own salt, so two
  installs mint two distinct keys — and the server only surfaces a kill seen
  purely by standalone reports once **two distinct keys** agree;
* the boss NPC id, physical server, kill time, and bounded placement context
  (map, instance, region, difficulty, patch, boss name).

It is **opt-in** (off by default): nothing is transmitted until the user
enables "Report world-boss kills" in Settings. ``report`` is best-effort,
never raises, and reports each distinct kill at most once (a small local
marker file dedupes repeated finalise/checkpoint saves of the same fight).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import threading
import urllib.request

from .. import __version__
from ..paths import data_file, read_json, write_user_json
from . import beacon, heartbeat, share

_MARK_FILE = ("community", "boss_reports.json")
_ENDPOINT = "/api/v1/boss-kill"
#: Encounter types whose kills the community feed merges (open-world world bosses).
_OPEN_WORLD = ("pve_open_world",)
#: Keep the local dedup marker bounded; older signatures simply age out.
_MARK_LIMIT = 200
_SERVER_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
#: Honoured after a 429 so a spent per-IP bucket is not re-hit on every checkpoint save.
_BACKOFF = beacon.Backoff()


def reporter_key() -> str:
    """A stable, anonymous per-install reporter key. Derived from the local-only
    install salt, so it is the same across launches on one install and distinct
    between installs; it never reveals the salt and differs from the daily token."""
    salt = heartbeat._install_salt()
    return hashlib.sha256(f"{salt}:boss-reporter".encode("utf-8")).hexdigest()[:32]


def enabled(ui: dict | None = None) -> bool:
    """On by default (opt-out): report unless the user explicitly turned it off.
    Reporting uses an anonymous per-install key and is surfaced only once two
    distinct installs agree, so a single install's kill is never shown alone."""
    if ui is None:
        try:
            from ..app import server
            ui = server.ui_settings()
        except Exception:
            ui = {}
    return ui.get("meter_report_boss_kills", True) is not False


def _killed_at(seg: dict) -> float | None:
    """Unix seconds for when the boss died: the segment start plus its duration."""
    start = seg.get("start")
    if not isinstance(start, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    try:
        duration = float(seg.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return when.timestamp() + max(0.0, duration)


def _npc_id(seg: dict) -> int | None:
    """The killed boss's NPC id (mob code), if a boss entity in the segment died."""
    entities = {e.get("id"): e for e in (seg.get("entities") or []) if isinstance(e, dict)}
    dead = {ev.get("target") for ev in (seg.get("events") or [])
            if isinstance(ev, dict) and ev.get("kind") == "death"}
    for eid, entity in entities.items():
        if not entity.get("is_boss"):
            continue
        if eid not in dead:
            continue
        code = entity.get("mob_code")
        try:
            code = int(code)
        except (TypeError, ValueError):
            continue
        if 0 < code < 10 ** 10:
            return code
    return None


def _server(doc: dict) -> str | None:
    """The physical server to place the kill on: the most common home server among
    the recorded party identities (each player carries its own ``server``)."""
    counts: dict[str, int] = {}
    for player in (doc.get("players") or []):
        if not isinstance(player, dict):
            continue
        srv = player.get("server")
        if isinstance(srv, str) and _SERVER_RE.fullmatch(srv):
            counts[srv] = counts.get(srv, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda s: (counts[s], s))


def defeats_from_doc(doc: dict) -> list[dict]:
    """Every confirmed open-world boss defeat in a finalised a2log document, as
    ready-to-post report bodies. Only open-world kills with an identified boss
    NPC and a placeable physical server qualify; everything else is skipped."""
    if not isinstance(doc, dict):
        return []
    server = _server(doc)
    if not server:
        return []
    reporter = reporter_key()
    reports = []
    for seg in (doc.get("segments") or []):
        if not isinstance(seg, dict) or not seg.get("killed"):
            continue
        if str(seg.get("encounter_type") or "") not in _OPEN_WORLD:
            continue
        npc = _npc_id(seg)
        killed_at = _killed_at(seg)
        if npc is None or killed_at is None:
            continue
        body = {"reporter": reporter, "outcome": "kill", "npc_id": npc,
                "server": server, "killed_at": round(killed_at, 3), "client": __version__}
        for key, value in (("map_id", seg.get("map_id")), ("instance_id", seg.get("instance_id"))):
            if isinstance(value, int) and not isinstance(value, bool) and value:
                body[key] = value
        for key in ("region", "difficulty", "game_patch", "boss"):
            value = seg.get(key)
            if isinstance(value, str) and value.strip():
                body[key] = value.strip()
        reports.append(body)
    return reports


def _signature(body: dict) -> str:
    return f"{body['npc_id']}:{body['server']}:{int(body['killed_at'])}"


def _already_reported(signatures: set[str]) -> set[str]:
    try:
        seen = read_json(*_MARK_FILE).get("reported") if data_file(*_MARK_FILE).exists() else []
    except Exception:
        return set()
    return {s for s in seen if isinstance(s, str)} & signatures if isinstance(seen, list) else set()


def _mark_reported(new: list[str]) -> None:
    try:
        existing = read_json(*_MARK_FILE).get("reported") if data_file(*_MARK_FILE).exists() else []
        existing = [s for s in existing if isinstance(s, str)] if isinstance(existing, list) else []
    except Exception:
        existing = []
    merged = (existing + [s for s in new if s not in existing])[-_MARK_LIMIT:]
    try:
        write_user_json({"reported": merged}, *_MARK_FILE)
    except Exception:
        pass


def _post(base: str, body: dict, key: str | None) -> None:
    headers = {"Content-Type": "application/json", "User-Agent": "aion2calc"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + _ENDPOINT, data, headers, method="POST")
    with urllib.request.urlopen(req, timeout=8) as response:
        response.read()


def report(doc: dict, ui: dict | None = None) -> str:
    """Best-effort: post any not-yet-reported open-world boss defeats in ``doc``.
    Returns a short status string and never raises — a failure just means the
    kill is not reported. Each distinct kill is reported at most once per install."""
    try:
        if not enabled(ui):
            return "disabled"
        reports = defeats_from_doc(doc)
        if not reports:
            return "no-kill"
        server = share.effective()
        base = str(server.get("url") or "").rstrip("/")
        if not base:
            return "no-server"
        signatures = {_signature(b): b for b in reports}
        fresh = {sig: body for sig, body in signatures.items()
                 if sig not in _already_reported(set(signatures))}
        if not fresh:
            return "already"
        if _BACKOFF.paused():
            return "paused"
        key = server.get("key")
        sent, dropped = [], []
        for sig, body in fresh.items():
            try:
                _post(base, body, key)
                sent.append(sig)
            except Exception as exc:
                if beacon.permanent_rejection(exc):
                    dropped.append(sig)       # the server will never take this body: don't retry it
                    continue
                if beacon.rate_limited(exc):
                    _BACKOFF.pause(getattr(exc, "headers", None))
                break                         # refusing or down: try again later, never hammer
        if sent or dropped:
            _mark_reported(sent + dropped)
        if sent:
            return f"sent:{len(sent)}"
        return "paused" if _BACKOFF.paused() else ("rejected" if dropped else "error")
    except Exception as exc:   # a community beacon must never affect the app
        return "error:" + type(exc).__name__


def report_async(doc: dict, ui: dict | None = None) -> None:
    """Fire :func:`report` on a daemon thread so a finalise/save never blocks on
    the network. Snapshots the document defensively; failures are swallowed."""
    try:
        if not enabled(ui):
            return
        threading.Thread(target=report, args=(doc, ui), daemon=True,
                         name="aion2-boss-report").start()
    except Exception:
        pass
