"""Automatic context from recorded IDs and explicit community catalog fields."""
from functools import lru_cache
import re

from .a2parser.lookup import _table, npc_info

PVP_MAPS = {
    60: {"zone":"Fire Temple Arena", "evidence":"User-confirmed arena capture and result screenshot"},
    61: {"zone":"Arena (map 61)", "evidence":"User-confirmed arena capture c9277026181bf976ea62f8438b939cb35aeee34bba192c4208a9aac2c6f1b127; specific arena name unverified"},
}
CATEGORIES = {"Dungeon":"expedition", "Transcendence":"transcendence", "Nightmare":"nightmare",
              "Ascension Trial":"ascension", "Raid":"sanctuary"}
AUTO = "Automatic catalog: "
NOTE = ("Community catalog matches use recorded IDs, not names, HP or damage patterns. "
        "NPC-only instance candidates do not establish instance entry or complete capture. "
        "Catalog applicability to this installed build is not independently verified. "
        "Unmapped NPCs are listed separately and cannot corroborate a match.")


def _id(value):
    return value if type(value) is int and 0 < value <= 2**32-1 else 0


def _difficulty(value):
    if value in ("Exploration", "Conquest [Normal]", "Conquest [Hard]"):
        return {"Exploration":"exploration", "Conquest [Normal]":"normal", "Conquest [Hard]":"hard"}[value]
    if value in ("Easy", "Normal", "Hard", "Extreme", "Insane", "Hell", "Ordeal", "Doom"):
        return value.lower()
    if isinstance(value, str) and re.fullmatch(r"(?:Stage|Level) [1-9][0-9]?", value):
        return value.lower()
    return None


@lru_cache(maxsize=1)
def _instances():
    result = {}
    for row in _table("npcs", "en").values():
        if not _id(row.get("dungeonId")) or row.get("isDummy"):
            continue
        group = result.setdefault(row["dungeonId"], {"categories":set(), "tiers":set()})
        if row.get("category") in CATEGORIES:
            group["categories"].add(CATEGORIES[row["category"]])
        if tier := _difficulty(row.get("tier")):
            group["tiers"].add(tier)
    return result


def classify(map_id, instance_id, pvp, entities=()):
    from .a2parser.engine import OPEN_WORLD_MAPS
    map_id, instance_id = _id(map_id), _id(instance_id)
    result, conflicts = {}, []
    rows = {}
    for entity in entities:
        if entity.get("kind") != "enemy" or entity.get("is_player") or entity.get("owner"):
            continue
        code = _id(entity.get("mob_code"))
        row = npc_info(code)
        if code and _id(row.get("dungeonId")) and not row.get("isDummy"):
            rows[code] = {"npc_id":code, "instance_id":row["dungeonId"],
                          "category":row.get("category"), "tier":row.get("tier")}
    npc_instances = sorted({r["instance_id"] for r in rows.values()})
    evidence = {"version":1, "status":"unavailable", "basis":"none", "recorded_map_id":map_id,
                "recorded_instance_id":instance_id, "npc_instance_ids":npc_instances[:100],
                "npcs":sorted(rows.values(), key=lambda r:r["npc_id"])[:100],
                "omitted_npcs":max(0,len(rows)-100), "conflicts":conflicts, "ambiguities":[], "note":NOTE}
    result["classification"] = evidence
    if pvp:
        if map_id in PVP_MAPS:
            record = PVP_MAPS[map_id]
            result.update(zone=record["zone"], encounter_type="pvp_arena", zone_source=record["evidence"],
                          encounter_type_source="Recorded map + identified player combat + confirmed arena capture")
        elif map_id in OPEN_WORLD_MAPS:
            result.update(encounter_type="pvp_open_world", encounter_type_source="Recorded map ID + bundled open-world map table")
        if result.get("encounter_type"):
            evidence.update(status="map_match", basis="recorded_map")
        return result
    dungeons = _table("dungeons", "en")
    candidate = instance_id
    basis = "recorded_instance" if candidate else "none"
    if not candidate and map_id and (str(map_id) in dungeons or map_id in _instances()):
        candidate, basis = map_id, "recorded_map"
    if not candidate and len(npc_instances) == 1:
        candidate, basis = npc_instances[0], "npc_only"
    if len(npc_instances) > 1:
        conflicts.append("Recorded NPCs belong to multiple catalog instances")
    if candidate and any(value != candidate for value in npc_instances):
        conflicts.append("Recorded map/instance and NPC catalog instance disagree")
    if map_id in OPEN_WORLD_MAPS:
        result.update(encounter_type="pve_open_world", encounter_type_source="Recorded map ID + bundled open-world map table")
        if candidate or npc_instances:
            conflicts.append("Open-world map conflicts with dungeon instance evidence")
        else:
            evidence.update(status="map_match", basis="recorded_map")
            return result
    dungeon = dungeons.get(str(candidate), {})
    prefix = AUTO + ("recorded NPC IDs" if basis == "npc_only" else "recorded map ID" if basis == "recorded_map" else "recorded instance ID")
    if dungeon.get("name") and not conflicts:
        result.update(zone=dungeon["name"], zone_source=prefix + " + exact dungeon name")
    if candidate:
        evidence.update(catalog_instance_id=candidate, basis=basis)
    if conflicts:
        evidence["status"] = "conflict"
        return result
    group = _instances().get(candidate, {})
    categories = group.get("categories", set())
    tiers = {_difficulty(row["tier"]) for row in rows.values() if row["instance_id"] == candidate}
    tiers.discard(None)
    if not tiers:
        tiers = group.get("tiers", set())
    direct = dungeon.get("difficulty")
    if direct and tiers and tiers != {direct}:
        conflicts.append("Dungeon difficulty and NPC catalog tiers disagree")
        evidence["status"] = "conflict"
        return result
    if len(categories) > 1:
        evidence["ambiguities"].append("Multiple catalog categories; encounter type is ambiguous")
    if len(categories) == 1:
        result.update(encounter_type=next(iter(categories)), encounter_type_source=prefix + " + exact NPC category")
    if direct:
        result.update(difficulty=direct, difficulty_source=prefix + " + exact dungeon difficulty")
    elif len(tiers) == 1:
        result.update(difficulty=next(iter(tiers)), difficulty_source=prefix + " + exact NPC tier")
    if len(tiers) > 1:
        evidence["ambiguities"].append("Multiple NPC catalog tiers; difficulty is ambiguous")
    evidence["status"] = "conflict" if conflicts else "ambiguous" if evidence["ambiguities"] else "catalog_match" if any(result.get(k) for k in ("zone", "difficulty", "encounter_type")) else "unavailable"
    evidence["suggested"] = {k:result[k] for k in ("zone", "difficulty", "encounter_type") if result.get(k)}
    return result


def enrich(doc):
    """Recompute derived evidence, filling absent/automatic context only."""
    meta = doc.get("meta") or {}
    for segment in doc.get("segments", []):
        friendly = {p["id"] for p in doc.get("players", [])}
        owners = {e["id"]:e.get("owner") for e in segment.get("entities", []) if e.get("owner")}
        for actor in owners:
            seen, parent = set(), actor
            while parent in owners and parent not in seen:
                seen.add(parent)
                parent = owners[parent]
            if parent in friendly:
                friendly.add(actor)
        involved = {h.get("target") for h in segment.get("hits", [])}
        for event in segment.get("events", []):
            if event.get("kind") == "damage" and (event.get("source") in friendly or event.get("target") in friendly):
                involved.update((event.get("source"), event.get("target")))
        entities = [e for e in segment.get("entities", []) if e.get("id") in involved]
        kind = str(segment.get("encounter_type") or meta.get("encounter_type") or "")
        detected = classify(segment.get("map_id"), segment.get("instance_id"), kind.startswith("pvp_"), entities)
        segment["classification"] = detected["classification"]
        for field in ("zone", "encounter_type", "difficulty"):
            old = segment.get(field) or meta.get(field)
            origin = str(segment.get(field+"_source") or "")
            automatic = origin.startswith(AUTO)
            if automatic:
                segment.pop(field, None)
                segment.pop(field+"_source", None)
            if detected.get(field) and (automatic or (str(old or "").strip().casefold() in ("", "unknown", "unavailable", "pve_unverified", "pvp_other"))):
                segment[field], segment[field+"_source"] = detected[field], detected[field+"_source"]
        # Mode remains identifiable even when a prior automatic category is invalidated.
        if not segment.get("encounter_type") and not meta.get("encounter_type"):
            segment["encounter_type"] = "pvp_other" if kind.startswith("pvp_") else "pve_unverified"
    return doc
