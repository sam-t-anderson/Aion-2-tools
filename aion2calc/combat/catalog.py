"""Bounded catalog coverage from recorded IDs; never guess names or classifications."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import hashlib
import json

from ..meter.a2parser.lookup import _table, npc_info
from ..meter.context import PVP_MAPS

LIMIT = 100


@lru_cache(maxsize=1)
def revision():
    from ..meter.a2parser.engine import OPEN_WORLD_MAPS
    tables = {key: _table(key, "en") for key in ("npcs", "dungeons")}
    tables.update(open_world_maps=sorted(OPEN_WORLD_MAPS), pvp_maps=PVP_MAPS, coverage_rules=5)
    return hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


@lru_cache(maxsize=1)
def source():
    try:
        manifest = json.loads(files("aion2calc.meter.a2parser").joinpath("data", "catalog-source.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return {}
    recorded = {row["file"]: row.get("sha256") for row in manifest.get("files", [])}
    matches = all(recorded.get(f"{category}/en.json") == hashlib.sha256(json.dumps(
        _table(category, "en"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        for category in ("npcs", "dungeons"))
    return {**{key: manifest.get(key) for key in ("repository", "revision", "checked_at", "game_build", "note")},
            "english_tables_match_source": matches}


def coverage(segment):
    from ..meter.a2parser.engine import OPEN_WORLD_MAPS
    valid_id = lambda value: value if isinstance(value, int) and not isinstance(value, bool) and 0 < value < 2**63 else 0
    instance = valid_id(segment.get("instance_id"))
    map_id = valid_id(segment.get("map_id"))
    dungeon = _table("dungeons", "en").get(str(instance), {})
    candidates = [e for e in segment.get("entities", [])
                  if e.get("kind") == "enemy" and not e.get("is_player") and not e.get("owner")]
    unresolved = {}
    unidentified = {}
    for entity in candidates:
        code = entity.get("mob_code")
        if not valid_id(code):
            actor = entity.get("id")
            if actor is not None:
                unidentified.setdefault(actor, {"entity": actor, "effects": None,
                    "recorded_damage_hits": entity.get("hits")})
            continue
        if npc_info(code).get("name"):
            continue
        row = unresolved.setdefault(code, {"kind": "npc", "code": code, "entities": set(), "effects": 0})
        row["entities"].add(entity["id"])
    counts = Counter()
    events = segment.get("events") or segment.get("hits", [])
    for event in events:
        # Count each recorded effect once per involved entity, including self effects.
        counts.update({event.get(k) for k in ("source", "target")} - {None})
    if "events" in segment or "hits" in segment:
        for actor, row in unidentified.items():
            row["effects"] = counts[actor]
    missing_rows = sorted(unidentified.values(), key=lambda row: str(row["entity"]))
    rows = []
    for row in unresolved.values():
        ids = row.pop("entities")
        row.update(entity_count=len(ids), effects=sum(counts[actor] for actor in ids))
        rows.append(row)
    if instance and not dungeon:
        rows.append({"kind": "instance", "code": instance, "entity_count": 0, "effects": 0})
    if map_id and map_id not in OPEN_WORLD_MAPS and map_id not in PVP_MAPS and not (map_id == instance and dungeon):
        rows.append({"kind": "map", "code": map_id, "entity_count": 0, "effects": 0})
    rows.sort(key=lambda r: (r["kind"], r["code"]))
    from ..meter.context import classify
    classification = segment.get("classification") or classify(map_id, instance, str(segment.get("encounter_type") or "").startswith("pvp_"), candidates)["classification"]
    return {"classification":classification, "catalog_revision": revision(), "catalog_source": source(), "map_id": map_id, "instance_id": instance,
            "catalog_zone": dungeon.get("name"), "catalog_difficulty": dungeon.get("difficulty"),
            "unmapped": rows[:LIMIT], "omitted": max(0, len(rows)-LIMIT),
            "npc_entities_without_type": len(missing_rows),
            "unidentified_entities": missing_rows[:LIMIT],
            "unidentified_omitted": max(0, len(missing_rows)-LIMIT),
            "note": "Unmapped means absent from this bundled catalog, not a verified new creature or zone. "
                    "Actor references without an NPC type are session-local, not reusable NPC catalog IDs. "
                    "They cannot be named reliably. Counts describe retained records, not unique kills. "
                    "Context suggestions use explicit NPC catalog category/tier fields only. Names, difficulty, category and game build are never guessed from damage or ID patterns."}
