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

VERSION = 1
CLASSES = ("gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter")
CLASS_ALIASES = {"elementalist": "spiritmaster", "brawler": "brawler"}
#: optional players[].stats keys (percent values as numbers)
PLAYER_STATS = ("critical_hit", "attack", "double_pct", "perfect_pct", "multihit_pct", "combat_speed_pct",
                "cooldown_pct", "accuracy")
LIMITS = {"players": 64, "segments": 200, "hits": 400_000, "buffs": 100_000, "hp": 50_000, "text": 200}

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
            "visibility": {"enum": ["public", "unlisted", "private"]},
            "contribute": {"enum": ["yes", "no"], "description": "use this fight in the anonymous class "
                           "statistics (default yes; private logs never are)"}}},
        "players": {"type": "array", "minItems": 1, "maxItems": LIMITS["players"], "items": {
            "type": "object", "required": ["id", "name"], "additionalProperties": True, "properties": {
                "id": {"type": "string"}, "name": {"type": "string"},
                "class": {"type": "string"}, "server": {"type": "string"},
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


class Invalid(ValueError):
    pass


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


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
            if not isinstance(h, dict) or not _num(h.get("t")) or not _num(h.get("damage")):
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
        out_segs.append({"id": _text(s.get("id"), "segment id") or str(i + 1),
                         "label": _text(s.get("label"), "segment label"), "boss": _text(s.get("boss"), "segment boss"),
                         "start": _text(s.get("start"), "segment start"), "duration": float(s["duration"]),
                         "killed": s.get("killed") is True, "hits": out_hits, "buffs": buffs, "hp": hp})
    return {"format": "a2log", "version": VERSION, "meta": clean_meta, "players": out_players, "segments": out_segs}


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
                          "killed": bool(m.get("boss_killed")), "hits": hits, "buffs": buffs}]}


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
    enc = normalize(enc)
    enc["specs"] = {k: ", ".join(map(str, v)) for k, v in (p.get("specs") or {}).items() if v}
    return enc
