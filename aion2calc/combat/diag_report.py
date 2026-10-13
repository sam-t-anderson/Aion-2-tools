"""Opt-out, anonymous diagnostics beacons for the community log server.

Two tiny, best-effort beacons that never raise, mirroring the enemy-HP and heartbeat
reporters. They carry **no** account, character, server, IP-derived or combat-content
data — only a per-install rotating reporter token (derived from the local, never-sent
install salt), the client/game version, a coarse region string, and small integers:

* **unknown-ids** (``/api/v1/diag/unknown-ids``): the NPC mob codes and skill ids a
  finished session used that the **shipped catalog doesn't map yet** — new content
  whose id→name tables upstream hasn't published (e.g. the ``295xxxx`` NPC range). The
  server ranks these so catalog gaps get filled from what players actually encounter.
  Deduped per ``id`` + game build, so a code is reported at most once per build.
* **capture-health** (``/api/v1/diag/capture-health``): a whitelist of capture-pipeline
  counters from a finished session (rollover parts saved, decoder/processing/capture
  errors, dropped packets, …) so regressions — like a meter that rolls over and resets
  mid-fight — surface in aggregate across users instead of one shared diagnostics zip at
  a time. Sent once per session, on the final save.

Both are **opt-out (on by default)**; the ``meter_report_diagnostics`` Settings toggle
turns them off. Like the other beacons, a failure (or a server without the endpoint)
simply means no contribution — it never affects capture or the app.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import urllib.request

from .. import __version__
from ..paths import data_file, read_json, write_user_json
from . import heartbeat, share

_UNKNOWN_ENDPOINT = "/api/v1/diag/unknown-ids"
_HEALTH_ENDPOINT = "/api/v1/diag/capture-health"
_MARK_FILE = ("community", "diag_reports.json")
#: Keep the local dedup marker bounded; older signatures age out.
_MARK_LIMIT = 1000
#: Server contract for a game-build string (matches the enemy-HP reporter's).
_BUILD_RE = re.compile(r"[^A-Za-z0-9 ._:+-]")
#: Capture-pipeline counters worth aggregating. Only numeric, non-identifying totals;
#: anything present and a non-bool int/float is forwarded, anything else is dropped.
_HEALTH_KEYS = (
    "archive_parts_saved", "decoded_events", "decoder_errors", "processing_errors",
    "capture_errors", "shutdown_discarded_payloads", "shutdown_drained_payloads",
    "pcap_received", "pcap_dropped", "pcap_if_dropped", "status_error_count",
)


def reporter_key() -> str:
    """A stable, anonymous per-install reporter key, from the local-only install salt.
    Same across launches on one install, distinct between installs, never reveals the
    salt, and distinct from the heartbeat/enemy-HP/boss-kill tokens."""
    salt = heartbeat._install_salt()
    return hashlib.sha256(f"{salt}:diagnostics-reporter".encode("utf-8")).hexdigest()[:32]


def enabled(ui: dict | None = None) -> bool:
    """Opt-OUT: diagnostics beacons are ON unless the user turned them off. Nothing
    identifying is sent, so this helps every user by default; one Settings toggle
    (``meter_report_diagnostics``) disables both beacons."""
    if ui is None:
        try:
            from ..app import server
            ui = server.ui_settings()
        except Exception:
            ui = {}
    return ui.get("meter_report_diagnostics", True) is not False


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _build(doc: dict) -> str:
    """The game build to key observations on, sanitised to the server's character set.
    Prefers the content patch (what changes ids); empty when no build is known."""
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    for value in (meta.get("game_patch"), meta.get("installed_content_build"), meta.get("installed_build")):
        if isinstance(value, str) and value.strip():
            cleaned = _BUILD_RE.sub("", value.strip())[:48]
            if cleaned:
                return cleaned
    return ""


def _region(doc: dict) -> str:
    """A coarse region/world string for the session, or ``""``. Read from the segments
    or players as the enemy-HP reporter does; truncated, never anything identifying."""
    for seg in (doc.get("segments") or []):
        if isinstance(seg, dict) and isinstance(seg.get("region"), str) and seg["region"].strip():
            return seg["region"].strip()[:32]
    for player in (doc.get("players") or []):
        if isinstance(player, dict) and isinstance(player.get("region"), str) and player["region"].strip():
            return player["region"].strip()[:32]
    return ""


def _skill_known(skill_id: int) -> bool:
    """True if the skill id, or its base (the id floored to the 10000 family), is in the
    shipped table — so skill *variants* of a known skill aren't reported as unknown."""
    from ..meter.a2parser.lookup import has_skill
    return has_skill(skill_id) or has_skill(skill_id - skill_id % 10_000)


def unknown_from_doc(doc: dict) -> dict:
    """``{"npc": [codes], "skill": [ids]}`` — the ids used in ``doc`` that the shipped
    catalog has no name for, sorted and de-duplicated. NPC mob codes with no catalog
    entry and skill ids whose family is unknown; empty lists when the catalog covers
    everything seen."""
    from ..meter.a2parser.lookup import npc_info
    if not isinstance(doc, dict):
        return {"npc": [], "skill": []}
    npc: set[int] = set()
    skill: set[int] = set()
    for seg in (doc.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        for entity in (seg.get("entities") or []):
            if not isinstance(entity, dict) or entity.get("is_player") or entity.get("kind") == "player":
                continue
            try:
                code = int(entity.get("mob_code"))
            except (TypeError, ValueError):
                continue
            if 0 < code < 10 ** 10 and not npc_info(code).get("name"):
                npc.add(code)
        for hit in (seg.get("hits") or []):
            if not isinstance(hit, dict):
                continue
            sid = hit.get("skill_id")
            if isinstance(sid, int) and not isinstance(sid, bool) and 0 < sid < 10 ** 10 and not _skill_known(sid):
                skill.add(sid)
    return {"npc": sorted(npc), "skill": sorted(skill)}


def health_payload(doc: dict, diagnostics: dict) -> dict:
    """The capture-health body: the reporter token, versions, OS and the whitelisted
    numeric counters present in ``diagnostics`` (anything non-numeric or off-whitelist
    is dropped)."""
    counters = {}
    if isinstance(diagnostics, dict):
        for key in _HEALTH_KEYS:
            value = diagnostics.get(key)
            if _num(value) and 0 <= value <= 2 ** 53 - 1:
                counters[key] = int(value)
    seconds = 0.0
    for seg in (doc.get("segments") or []):
        if isinstance(seg, dict) and _num(seg.get("duration")):
            seconds += float(seg["duration"])
    body = {"reporter": reporter_key(), "client": __version__, "os": sys.platform,
            "game_build": _build(doc), "session_seconds": round(seconds, 1), "counters": counters}
    region = _region(doc)
    if region:
        body["region"] = region
    return body


def _read_marks() -> dict:
    try:
        return read_json(*_MARK_FILE) if data_file(*_MARK_FILE).exists() else {}
    except Exception:
        return {}


def _post(base: str, endpoint: str, body: dict, key: str | None) -> None:
    headers = {"Content-Type": "application/json", "User-Agent": "aion2calc"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + endpoint, data, headers, method="POST")
    with urllib.request.urlopen(req, timeout=8) as response:
        response.read()


def report(doc: dict, diagnostics: dict | None = None, ui: dict | None = None) -> str:
    """Best-effort: post the not-yet-reported unknown ids in ``doc`` and this session's
    capture-health. Returns a short status string and never raises."""
    try:
        if not enabled(ui):
            return "disabled"
        server = share.effective()
        base = str(server.get("url") or "").rstrip("/")
        if not base:
            return "no-server"
        key = server.get("key")
        marks = _read_marks()
        sent = []

        # --- unknown ids (deduped per id + build) ---
        build = _build(doc)
        unknown = unknown_from_doc(doc)
        reported = {s for s in marks.get("unknown", []) if isinstance(s, str)}
        fresh_npc = [c for c in unknown["npc"] if f"n:{c}:{build}" not in reported]
        fresh_skill = [c for c in unknown["skill"] if f"s:{c}:{build}" not in reported]
        if fresh_npc or fresh_skill:
            body = {"reporter": reporter_key(), "client": __version__, "game_build": build,
                    "npc": fresh_npc, "skill": fresh_skill}
            region = _region(doc)
            if region:
                body["region"] = region
            try:
                _post(base, _UNKNOWN_ENDPOINT, body, key)
                new = [f"n:{c}:{build}" for c in fresh_npc] + [f"s:{c}:{build}" for c in fresh_skill]
                reported = (list(reported) + new)[-_MARK_LIMIT:]
                marks["unknown"] = reported
                sent.append(f"unknown:{len(new)}")
            except Exception:
                pass

        # --- capture health (once per session) ---
        health = health_payload(doc, diagnostics or {})
        sig = str((doc.get("meta") or {}).get("archive", {}).get("id") or "") or str((doc.get("meta") or {}).get("title") or "")
        if health["counters"] and marks.get("health_sig") != sig:
            try:
                _post(base, _HEALTH_ENDPOINT, health, key)
                marks["health_sig"] = sig
                sent.append("health")
            except Exception:
                pass

        if sent:
            try:
                write_user_json(marks, *_MARK_FILE)
            except Exception:
                pass
            return "sent:" + ",".join(sent)
        return "nothing"
    except Exception as exc:   # a beacon must never affect the app
        return "error:" + type(exc).__name__


def report_async(doc: dict, diagnostics: dict | None = None, ui: dict | None = None) -> None:
    """Fire-and-forget :func:`report` on a daemon thread, so a save never waits on it."""
    try:
        threading.Thread(target=report, args=(doc, diagnostics, ui), daemon=True,
                         name="aion2-diag-report").start()
    except Exception:
        pass
