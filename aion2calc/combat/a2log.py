"""The a2log format: an open JSON format for AION 2 combat logs.

aion2calc shares fights in this format (``share``) and reads it back for
analysis. ``SCHEMA`` is its JSON Schema; a server that accepts uploads
advertises its upload endpoint at ``/.well-known/a2log.json``.

A document is one fight (a boss pull, a dungeon run, a dummy parse) with any
number of players and segments::

    {"format": "a2log", "version": 1,
     "meta": {"source": "my-meter 1.2", "region": "na", "recorded_at": "2026-10-04T19:00:00Z",
              "title": "Gatekeeper Pinopi (Nightmare 2)"},
     "players": [{"id": "p1", "name": "Name", "class": "sorcerer", "combat_power": 70000,
                  "specs": {"Hellfire": [2, 4]}}],
     "segments": [{"label": "Gatekeeper Pinopi", "boss": "Gatekeeper Pinopi", "duration": 93.0, "killed": true,
                   "hits": [{"t": 0.0, "player": "p1", "skill": "Hellfire", "skill_id": 15060000,
                             "damage": 12345, "crit": true, "double": false, "perfect": false,
                             "multi": 2, "dot": false, "back": false}],
                   "buffs": [{"player": "p1", "name": "Element Enhancement", "skill_id": 15400000,
                              "start": 1.0, "end": 21.0}],
                   "hp": [[0.0, 1437663], [1.5, 1400000]]}]}

Times are seconds from the segment start. ``class`` is one of the class keys
below (the in-game name "Elementalist" is accepted for spiritmaster).
"""
from __future__ import annotations

import re
import math

VERSION = 1
PVP_TYPES = ("pvp_battleground", "pvp_arena", "pvp_abyss", "pvp_rift", "pvp_open_world", "pvp_other")
ENCOUNTER_TYPES = ("unknown", "pve_open_world", "pve_unverified", "transcendence", "daily", "expedition", "ascension", "nightmare", "sanctuary", *PVP_TYPES)


def combat_mode(doc, segment=None):
    kind = (segment or {}).get("encounter_type") or doc.get("meta", {}).get("encounter_type")
    return "pvp" if kind in PVP_TYPES else "pve"
CLASSES = ("gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter")
CLASS_ALIASES = {"elementalist": "spiritmaster", "brawler": "brawler"}
#: optional players[].stats keys (percent values as numbers)
PLAYER_STATS = ("critical_hit", "attack", "double_pct", "perfect_pct", "multihit_pct", "combat_speed_pct",
                "cooldown_pct", "accuracy")
LIMITS = {"players": 64, "segments": 200, "hits": 400_000, "buffs": 100_000, "hp": 50_000, "text": 200}


def profile_snapshot(value):
    if not isinstance(value,dict) or value.get("status") not in ("pending","ready","partial","unavailable"):
        return None
    import json
    try:
        if len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode())>512*1024:
            return None
    except (ValueError,TypeError):
        return None
    return value


HIT = {"type": "object", "required": ["t", "player", "damage"], "additionalProperties": True, "properties": {
    "t": {"type": "number", "minimum": 0, "description": "seconds from the segment start"},
    "player": {"type": "string", "description": "a players[].id"},
    "skill": {"type": "string"}, "skill_id": {"type": "integer"},
    "damage": {"type": "number", "minimum": 0},
    "crit": {"type": "boolean"}, "double": {"type": "boolean"}, "perfect": {"type": "boolean"},
    "multi": {"type": "integer", "minimum": 0, "description": "extra hits of a multi-hit"},
    "dot": {"type": "boolean"}, "back": {"type": "boolean"}, "front": {"type": "boolean"},
    "step": {"type": "string", "description": "chain follow-up name (e.g. Cold Wave of Ice Chain)"}}}

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "a2log-v1.json",
    "title": "a2log: AION 2 combat log",
    "type": "object",
    "required": ["format", "version", "players", "segments"],
    "properties": {
        "format": {"const": "a2log"},
        "version": {"const": VERSION},
        "meta": {"type": "object", "additionalProperties": True, "properties": {
            "source": {"type": "string", "description": "uploading tool and version"},
            "title": {"type": "string"}, "region": {"type": "string"}, "server": {"type": "string"},
            "recorded_at": {"type": "string", "format": "date-time"},
            "zone": {"type": "string"}, "difficulty": {"type": "string"},
            "installed_build": {"type": "string"}, "installed_build_namespace": {"type": "string"}, "installed_build_cohort": {"type": "string"}, "installed_build_source": {"type": "string"}, "region_source": {"type": "string"},
            "game_patch": {"type": "string"}, "game_patch_source": {"type": "string"}, "game_patch_basis": {"type": "string"}, "encounter_type": {"enum": list(ENCOUNTER_TYPES)},
            "capture_active": {"type": "boolean"}, "checkpoint_at": {"type": "number"},
            "capture_scope": {"enum": ["party", "self", "all"]},
            "reconstruction":{"type":"object", "description":"Bounded source-part manifest for unranked descriptive combined review"},
            "archive": {"type":"object", "properties":{"id":{"type":"string"}, "part":{"type":"integer", "minimum":1}, "closed":{"type":"boolean"}, "continuity":{"type":"object", "description":"Submitted retained-record ranges and predecessor token; not verified capture continuity"}}},
            "capture_quality": {"type": "object", "description": "Capture evidence and loss counters; eligibility is computed by the server"},
            "visibility": {"enum": ["public", "unlisted", "private"]},
            "contribute": {"enum": ["yes", "no"], "description": "use this fight in the anonymous class "
                           "statistics (default yes; private logs never are)"}}},
        "players": {"type": "array", "minItems": 1, "maxItems": LIMITS["players"], "items": {
            "type": "object", "required": ["id", "name"], "additionalProperties": True, "properties": {
                "id": {"type": "string"}, "name": {"type": "string"},
                "class": {"type": "string"}, "server": {"type": "string"},
                "profile_snapshot": {"type":"object", "description":"Optional immutable official upload-time profile with status, timestamps and data; not proof of encounter-time gear"},
                "combat_power": {"type": "number"}, "gear_score": {"type": "number"},
                "specs": {"type": "object", "description": "skill name -> chosen specialization slots (1-5)",
                          "additionalProperties": {"type": "array", "items": {"type": "integer"}}},
                "stats": {"type": "object", "description": "optional: the character's stats during the fight, as "
                          "the game shows them (percent values as numbers, 12.5 = 12.5%); lets the server "
                          "calibrate crit and the other rates",
                          "properties": {k: {"type": "number"} for k in PLAYER_STATS}}}}},
        "segments": {"type": "array", "minItems": 1, "maxItems": LIMITS["segments"], "items": {
            "type": "object", "required": ["duration", "hits"], "additionalProperties": True, "properties": {
                "id": {"type": "string"}, "label": {"type": "string"}, "boss": {"type": "string"},
                "start": {"type": "string", "format": "date-time"},
                "duration": {"type": "number", "exclusiveMinimum": 0},
                "killed": {"type": "boolean"},
                "hits": {"type": "array", "items": HIT},
                "buffs": {"type": "array", "items": {"type": "object", "required": ["player", "start", "end"],
                                                       "properties": {"player": {"type": "string"},
                                                                      "name": {"type": "string"},
                                                                      "skill_id": {"type": "integer"},
                                                                      "start": {"type": "number"},
                                                                      "end": {"type": "number"}}}},
                "hp": {"type": "array", "description": "boss HP samples [t, hp]",
                       "items": {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}]}}}}},
    },
}

# Compatible v1 extensions. Older logs without these arrays remain readable.
_segment_properties = SCHEMA["properties"]["segments"]["items"]["properties"]
_segment_properties.update({
    "classification":{"type":"object", "description":"Derived recorded-ID catalog context; recomputed, never trusted from uploads"},
    "recording_run":{"type":"object", "description":"Submitted stable run token, original record origin and observed entry/final-boss evidence across storage parts; not ranking eligibility"},
    "run_id":{"type":"string"}, "run_complete":{"type":"boolean"}, "run_end_reason":{"type":"string"},
    "run_start_observed":{"type":"boolean"}, "run_started_at":{"type":"string"}, "run_ended_at":{"type":"string"},
    "party_members":{"type":"array", "maxItems":64, "items":{"type":"string"}}, "party_roster_complete":{"type":"boolean"}, "party_roster_late":{"type":"boolean"}, "partial_capture":{"type":"boolean"},
    "instance_id":{"type":"integer"}, "map_id":{"type":"integer"},
    "zone_source":{"type":"string"}, "encounter_type_source":{"type":"string"}, "difficulty_source":{"type":"string"},
    "game_patch": {"type": "string"}, "game_patch_source": {"type": "string"}, "game_patch_basis": {"type": "string"}, "difficulty": {"type": "string"}, "encounter_type": {"enum": list(ENCOUNTER_TYPES)},
    "entities": {"type": "array", "maxItems": 2000, "description": "Observed enemies and pets: id, name, kind, mob_code, is_boss, owner"},
    "events": {"type": "array", "maxItems": LIMITS["hits"], "description": "Recorded damage/heal/death effects: t, kind, source, target, skill, skill_id, amount; unknown recipients omitted"},
    "health": {"type": "array", "maxItems": LIMITS["hp"], "description": "Entity HP samples: t, entity, current, optional max"},
    "positions": {"type": "array", "maxItems": LIMITS["hp"], "description": "Verified arena-normalized replay positions: t, entity, x and y in [0,1]"},
})
SCHEMA["properties"]["players"]["items"]["properties"].update({
    "character_id": {"type": "string", "description": "Observed database character ID, distinct from the session combat entity ID"},
    "region": {"type": "string"},
})


class Invalid(ValueError):
    pass


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _text(x, where: str, required: bool = False) -> str | None:
    if x is None:
        if required:
            raise Invalid(f"{where} is required")
        return None
    if not isinstance(x, str):
        raise Invalid(f"{where} must be a string")
    return x[:LIMITS["text"]]


def class_key(c) -> str | None:
    if not c:
        return None
    k = re.sub(r"[^a-z]", "", str(c).lower())
    k = CLASS_ALIASES.get(k, k)
    return k if k in CLASSES or k == "brawler" else None


def validate(doc) -> dict:
    """Check an upload and return a cleaned copy (raises :class:`Invalid` with the first problem)."""
    if not isinstance(doc, dict):
        raise Invalid("the body must be a JSON object")
    if doc.get("format") != "a2log":
        raise Invalid('"format" must be "a2log"')
    if doc.get("version") != VERSION:
        raise Invalid(f'"version" must be {VERSION}')
    meta = doc.get("meta") or {}
    if not isinstance(meta, dict):
        raise Invalid('"meta" must be an object')
    clean_meta = {k: _text(v, f"meta.{k}") for k, v in meta.items()
                  if isinstance(v, str) and k in SCHEMA["properties"]["meta"]["properties"]}
    if isinstance(meta.get("capture_active"), bool):
        clean_meta["capture_active"] = meta["capture_active"]
    if _num(meta.get("checkpoint_at")) and meta["checkpoint_at"] >= 0:
        clean_meta["checkpoint_at"] = meta["checkpoint_at"]
    if meta.get("capture_scope") in ("party", "self", "all"):
        clean_meta["capture_scope"] = meta["capture_scope"]
    from .quality import COUNTERS
    capture = meta.get("capture_quality")
    if isinstance(capture, dict):
        evidence = {k: capture[k][:100] for k in ("decoder", "app_version") if isinstance(capture.get(k), str)}
        for k in (*COUNTERS, "shutdown_drained_payloads", "tcp_pending_bytes", "pcap_received", "pcap_stats_reads"):
            if isinstance(capture.get(k), int) and not isinstance(capture[k], bool) and 0 <= capture[k] <= 2**53-1:
                evidence[k] = capture[k]
        for flag in ("transport_monitored", "pcap_stats_sampled", "pcap_stats_partial", "storage_boundary", "reconstructed"):
            if isinstance(capture.get(flag), bool):
                evidence[flag] = capture[flag]
        clean_meta["capture_quality"] = evidence
    from .reconstruction import clean_manifest
    manifest = clean_manifest(meta.get("reconstruction"))
    if "reconstruction" in meta and not manifest:
        raise Invalid("Invalid combined recording source manifest")
    if manifest:
        clean_meta["reconstruction"] = manifest
        clean_meta.setdefault("capture_quality", {})["reconstructed"] = True
    archive = meta.get("archive")
    if isinstance(archive, dict) and isinstance(archive.get("id"), str) and isinstance(archive.get("part"), int) and not isinstance(archive["part"], bool) and 1 <= archive["part"] <= 2**53-1:
        clean_meta["archive"] = {"id": archive["id"][:100], "part": archive["part"], "closed": archive.get("closed") is True}
        from .archive import clean_continuity
        continuity = clean_continuity(archive.get("continuity"))
        if continuity:
            clean_meta["archive"]["continuity"] = continuity
    if clean_meta.get("encounter_type") not in (None, *ENCOUNTER_TYPES):
        raise Invalid("Unknown encounter_type")
    if clean_meta.get("visibility") not in (None, "public", "unlisted", "private"):
        raise Invalid('meta.visibility must be "public", "unlisted" or "private"')
    players = doc.get("players")
    if not isinstance(players, list) or not players or len(players) > LIMITS["players"]:
        raise Invalid(f'"players" must hold 1 to {LIMITS["players"]} players')
    ids, out_players = set(), []
    for i, p in enumerate(players):
        if not isinstance(p, dict):
            raise Invalid(f"players[{i}] must be an object")
        pid = _text(p.get("id"), f"players[{i}].id", True)
        if pid in ids:
            raise Invalid(f"players[{i}].id {pid!r} is used twice")
        ids.add(pid)
        q = {"id": pid, "name": _text(p.get("name"), f"players[{i}].name", True),
             "class": class_key(p.get("class")), "server": _text(p.get("server"), f"players[{i}].server")}
        snapshot = profile_snapshot(p.get("profile_snapshot"))
        if snapshot is not None:
            q["profile_snapshot"] = snapshot
        for k in ("character_id", "region"):
            if p.get(k) is not None:
                q[k] = _text(str(p[k]), f"players[{i}].{k}")
        for k in ("combat_power", "gear_score"):
            if _num(p.get(k)):
                q[k] = p[k]
        specs = p.get("specs") or {}
        if isinstance(specs, dict):
            q["specs"] = {str(k)[:80]: [int(x) for x in v if isinstance(x, int) and 1 <= x <= 5]
                          for k, v in list(specs.items())[:80] if isinstance(v, list)}
        stats = p.get("stats") or {}
        if isinstance(stats, dict):
            q["stats"] = {k: float(v) for k, v in stats.items() if k in PLAYER_STATS and _num(v) and 0 <= v < 1e7}
        out_players.append(q)
    segs = doc.get("segments")
    if not isinstance(segs, list) or not segs or len(segs) > LIMITS["segments"]:
        raise Invalid(f'"segments" must hold 1 to {LIMITS["segments"]} segments')
    total_hits, out_segs = 0, []
    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            raise Invalid(f"segments[{i}] must be an object")
        if not _num(s.get("duration")) or s["duration"] <= 0:
            raise Invalid(f"segments[{i}].duration must be a positive number of seconds")
        hits = s.get("hits")
        if not isinstance(hits, list):
            raise Invalid(f"segments[{i}].hits must be a list")
        total_hits += len(hits)
        if total_hits > LIMITS["hits"]:
            raise Invalid(f"too many hits (limit {LIMITS['hits']})")
        out_hits = []
        for j, h in enumerate(hits):
            w = f"segments[{i}].hits[{j}]"
            if not isinstance(h, dict) or not _num(h.get("t")) or not _num(h.get("damage")) or h["t"] < 0 or h["damage"] < 0:
                raise Invalid(f"{w} needs numeric t and damage")
            if h.get("player") not in ids:
                raise Invalid(f"{w}.player must be one of the players' ids")
            x = {"t": float(h["t"]), "player": h["player"], "damage": float(h["damage"])}
            if isinstance(h.get("skill"), str):
                x["skill"] = h["skill"][:80]
            if isinstance(h.get("skill_id"), int) and not isinstance(h.get("skill_id"), bool):
                x["skill_id"] = h["skill_id"]
            if isinstance(h.get("step"), str):
                x["step"] = h["step"][:80]
            for k in ("target", "source", "pet"):
                if isinstance(h.get(k), str):
                    x[k] = h[k][:200]
            for k in ("crit", "double", "perfect", "dot", "back", "front"):
                if h.get(k) is True:
                    x[k] = True
            if isinstance(h.get("multi"), int) and h["multi"] > 0:
                x["multi"] = min(int(h["multi"]), 10)
            out_hits.append(x)
        buffs = []
        for j, b in enumerate((s.get("buffs") or [])[:LIMITS["buffs"]]):
            if isinstance(b, dict) and b.get("player") in ids and _num(b.get("start")) and _num(b.get("end")):
                buffs.append({"player": b["player"], "name": _text(b.get("name"), "buff name") or "",
                              "skill_id": b.get("skill_id") if isinstance(b.get("skill_id"), int) else None,
                              "start": float(b["start"]), "end": float(b["end"])})
        hp = [[float(a), float(b)] for a, b in (x for x in (s.get("hp") or [])[:LIMITS["hp"]]
                                               if isinstance(x, list) and len(x) == 2 and _num(x[0]) and _num(x[1]))]
        entities = []
        for entity in (s.get("entities") or [])[:2000]:
            if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
                continue
            row = {k: str(entity[k])[:200] for k in ("id", "name", "kind", "owner") if entity.get(k) is not None}
            if entity.get("owner") not in ids:
                row.pop("owner", None)
            snapshot = profile_snapshot(entity.get("profile_snapshot"))
            if snapshot is not None:
                row["profile_snapshot"] = snapshot
            row["is_boss"] = entity.get("is_boss") is True
            row["is_player"] = entity.get("is_player") is True
            for key in ("class", "server", "character_id"):
                if isinstance(entity.get(key), str):
                    row[key] = _text(entity[key], "entity." + key)
            if isinstance(entity.get("mob_code"), int):
                row["mob_code"] = entity["mob_code"]
            entities.append(row)
        references = ids | {e["id"] for e in entities}
        events = []
        for event in (s.get("events") or [])[:LIMITS["hits"]]:
            if not isinstance(event, dict) or event.get("kind") not in ("damage", "heal", "death"):
                continue
            if not _num(event.get("t")) or not 0 <= event["t"] <= s["duration"] + 1:
                continue
            row = {"kind": event["kind"], "t": float(event["t"])}
            for k in ("source", "target"):
                if event.get(k) in references:
                    row[k] = event[k]
            if event["kind"] == "death" and "target" not in row:
                continue
            if event["kind"] != "death":
                if not _num(event.get("amount")) or event["amount"] < 0:
                    continue
                row["amount"] = float(event["amount"])
            if isinstance(event.get("skill_id"), int):
                row["skill_id"] = event["skill_id"]
            if isinstance(event.get("skill"), str):
                row["skill"] = event["skill"][:80]
            events.append(row)
        health = []
        for sample in (s.get("health") or [])[:LIMITS["hp"]]:
            if (isinstance(sample, dict) and sample.get("entity") in references
                    and _num(sample.get("t")) and 0 <= sample["t"] <= s["duration"] + 1
                    and _num(sample.get("current")) and sample["current"] >= 0):
                row = {"t": float(sample["t"]), "entity": sample["entity"], "current": float(sample["current"])}
                if _num(sample.get("max")) and sample["max"] > 0:
                    row["max"] = float(sample["max"])
                health.append(row)
        positions = []
        for sample in (s.get("positions") or [])[:LIMITS["hp"]]:
            if (isinstance(sample, dict) and sample.get("entity") in references
                    and all(_num(sample.get(k)) for k in ("t", "x", "y"))
                    and 0 <= sample["t"] <= s["duration"] and 0 <= sample["x"] <= 1 and 0 <= sample["y"] <= 1):
                positions.append({k: sample[k] for k in ("t", "entity", "x", "y")})
        out_segs.append({"id": _text(s.get("id"), "segment id") or str(i + 1),
                         "label": _text(s.get("label"), "segment label"), "boss": _text(s.get("boss"), "segment boss"),
                         "start": _text(s.get("start"), "segment start"), "duration": float(s["duration"]),
                         "killed": s.get("killed") is True, "hits": out_hits, "buffs": buffs, "hp": hp,
                         "entities": entities, "events": events, "health": health, "positions": positions})
        from .reconstruction import clean_run
        run_evidence = clean_run(s.get("recording_run"))
        if run_evidence:
            out_segs[-1]["recording_run"] = run_evidence
        for key in ("run_id", "run_end_reason", "zone", "zone_source", "encounter_type_source", "difficulty_source", "run_started_at", "run_ended_at"):
            if isinstance(s.get(key),str):
                out_segs[-1][key] = s[key][:200]
        if isinstance(s.get("run_complete"),bool):
            out_segs[-1]["run_complete"] = s["run_complete"]
        for key in ("run_start_observed", "party_roster_complete", "party_roster_late", "partial_capture"):
            if isinstance(s.get(key),bool):
                out_segs[-1][key] = s[key]
        if isinstance(s.get("party_members"),list):
            members = s["party_members"]
            if len(members)>64 or any(not isinstance(p,str) or p not in ids for p in members):
                raise Invalid("party_members must reference at most 64 players")
            out_segs[-1]["party_members"] = list(dict.fromkeys(members))
        for key in ("instance_id", "map_id"):
            if isinstance(s.get(key),int) and 0 <= s[key] <= 2**32-1:
                out_segs[-1][key] = s[key]
        for key in ("game_patch", "game_patch_source", "game_patch_basis", "difficulty", "encounter_type"):
            if isinstance(s.get(key), str):
                if key == "encounter_type" and s[key] not in ENCOUNTER_TYPES:
                    raise Invalid("Unknown segment encounter_type")
                out_segs[-1][key] = s[key][:200]
    # Optional arrays are filtered/capped above. Make any loss visible after round trips.
    removed = sum(max(0, len(s.get(key) or []) - len(out.get(key) or []))
                  for s, out in zip(segs, out_segs)
                  for key in ("events", "health", "positions", "entities", "buffs", "hp"))
    if removed:
        evidence = clean_meta.setdefault("capture_quality", {})
        evidence["validation_discarded"] = min(2**53-1, evidence.get("validation_discarded", 0) + removed)
    result = {"format": "a2log", "version": VERSION, "meta": clean_meta, "players": out_players, "segments": out_segs}
    from ..meter.context import enrich
    enrich(result)
    from .quality import assess
    for segment in out_segs:
        segment["quality"] = assess(result, segment)
    from .runs import summarize
    result["run_analysis"] = summarize(result)
    from .recaps import summarize as death_recaps
    result["death_analysis"] = death_recaps(result)
    from .insights import summarize as encounter_insights
    result["encounter_insights"] = encounter_insights(result)
    if clean_meta.get("reconstruction"):
        from .reconstruction import summarize as recording_summary
        result["recording_summary"] = recording_summary(result)
        from .reconstruction import run_summary
        result["recording_runs"] = run_summary(result)
    return result


# ------------------------------------------------------------- conversions
def from_encounter(enc: dict, source: str = "aion2calc", stats: dict | None = None) -> dict:
    """An aion2calc encounter (one player's side of a fight) -> a2log."""
    m = enc.get("meta", {})
    pid = "p1"
    specs = {k: [int(x) for x in str(v).replace(" ", "").split(",") if x.isdigit()]
             for k, v in (enc.get("specs") or {}).items()}
    hits = [{k: v for k, v in {"t": h["t"], "player": pid, "skill": h.get("skill"), "skill_id": h.get("skill_id"),
                               "damage": h["damage"], "crit": h.get("crit") or None, "double": h.get("double") or None,
                               "perfect": h.get("perfect") or None, "multi": h.get("multi") or None,
                               "dot": h.get("dot") or None, "back": h.get("back") or None,
                               "front": h.get("front") or None, "step": h.get("step")}.items() if v is not None}
            for h in enc.get("hits", [])]
    buffs = [{"player": pid, "name": b.get("name"), "skill_id": b.get("skill_id"), "start": a, "end": z}
             for b in enc.get("buffs", []) for a, z in (b.get("windows") or [])]
    return {"format": "a2log", "version": VERSION,
            "meta": {"source": source, "title": m.get("target"), "region": m.get("region"),
                     "recorded_at": m.get("started_at")},
            "players": [{"id": pid, "name": m.get("player") or "player", "class": m.get("class"),
                         "combat_power": m.get("combat_power"), "specs": specs, "stats": stats or {}}],
            "segments": [{"label": m.get("target"), "boss": m.get("target"), "duration": m.get("duration") or 1.0,
                          "killed": bool(m.get("boss_killed")), "hits": hits, "buffs": buffs,
                          "partial_capture":m.get("learning_excluded") is True}]}


def damage_interval(segment: dict) -> tuple[float, float]:
    """Shared outgoing damage clock; individual deaths never shorten it."""
    times = [h["t"] for h in segment.get("hits", [])]
    return (min(times), max(times)) if times else (0.0, 0.0)


def damage_buckets(segment: dict) -> tuple[float, list[int]]:
    """One-second party-active buckets, anchored to the first outgoing hit."""
    first, _ = damage_interval(segment)
    return first, sorted({int(max(0,h["t"]-first)) for h in segment.get("hits", [])})


def damage_duration(segment: dict) -> float:
    _, buckets = damage_buckets(segment)
    return float(max(1,len(buckets)))


def to_encounter(doc: dict, player_id: str, segment: int = 0) -> dict:
    """One player's side of one segment -> an aion2calc encounter (for the analyzer)."""
    from .adapters import normalize
    seg = doc["segments"][segment]
    p = next(x for x in doc["players"] if x["id"] == player_id)
    from .abysslogs import chain_parent, skill_base
    cd = None
    if p.get("class"):
        try:
            from ..kit.base import ClassData
            cd = ClassData(p["class"])
        except Exception:
            cd = None
    hits = []
    for h in seg["hits"]:
        if h["player"] != player_id:
            continue
        sid, name, step = h.get("skill_id"), h.get("skill") or str(h.get("skill_id") or "?"), h.get("step")
        if cd and sid and sid not in cd.skills:          # variant codes -> the class skill
            base = skill_base(sid, cd)
            if base is None and (parent := chain_parent(name, cd)):
                base, step = parent, step or name
            sid = base or sid
        hits.append({"t": h["t"], "skill_id": sid, "skill": name, "damage": h["damage"], "crit": h.get("crit"),
                     "double": h.get("double"), "perfect": h.get("perfect"), "multi": h.get("multi", 0),
                     "dot": h.get("dot"), "back": h.get("back"), "front": h.get("front"), "step": step})
    wins: dict = {}
    for b in seg.get("buffs", []):
        if b["player"] == player_id:
            wins.setdefault((b.get("name"), b.get("skill_id")), []).append([b["start"], b["end"]])
    buffs = [{"name": n or str(sid), "skill_id": sid, "windows": w,
              "uptime": min(1.0, sum(z - a for a, z in w) / seg["duration"])} for (n, sid), w in wins.items()]
    enc = {"meta": {"source": "a2log", "player": p["name"], "class": p.get("class"), "target": seg.get("boss") or
                    seg.get("label"), "duration": seg["duration"], "combat_power": p.get("combat_power")},
           "hits": hits, "buffs": buffs, "specs": {}}
    from .quality import assess
    excluded = {"partial_capture", "party_roster_late", "classification_npc_only", "classification_conflict"}.intersection(assess(doc, seg)["reasons"])
    enc["meta"]["learning_excluded"] = bool(excluded)
    enc["meta"]["learning_exclusion_reasons"] = sorted(excluded)
    enc = normalize(enc)
    enc["specs"] = {k: ", ".join(map(str, v)) for k, v in (p.get("specs") or {}).items() if v}
    return enc
