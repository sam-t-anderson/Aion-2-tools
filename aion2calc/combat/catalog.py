"""Bounded catalog coverage from recorded IDs; never guess names or classifications."""
from collections import Counter
from functools import lru_cache
import hashlib
import json

from ..meter.a2parser.lookup import _table, npc_info

LIMIT = 100


@lru_cache(maxsize=1)
def revision():
    tables = {key: _table(key, "en") for key in ("npcs", "dungeons")}
    return hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def coverage(segment):
    from ..meter.a2parser.engine import OPEN_WORLD_MAPS
    valid_id = lambda value: value if isinstance(value, int) and not isinstance(value, bool) and 0 < value < 2**63 else 0
    instance = valid_id(segment.get("instance_id"))
    map_id = valid_id(segment.get("map_id"))
    dungeon = _table("dungeons", "en").get(str(instance), {})
    candidates = [e for e in segment.get("entities", [])
                  if e.get("kind") == "enemy" and not e.get("is_player") and not e.get("owner")]
    unresolved = {}
    missing = 0
    for entity in candidates:
        code = entity.get("mob_code")
        if not valid_id(code):
            missing += 1
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
    rows = []
    for row in unresolved.values():
        ids = row.pop("entities")
        row.update(entity_count=len(ids), effects=sum(counts[actor] for actor in ids))
        rows.append(row)
    if instance and not dungeon:
        rows.append({"kind": "instance", "code": instance, "entity_count": 0, "effects": 0})
    if map_id and map_id not in OPEN_WORLD_MAPS and map_id != 60:
        rows.append({"kind": "map", "code": map_id, "entity_count": 0, "effects": 0})
    rows.sort(key=lambda r: (r["kind"], r["code"]))
    return {"catalog_revision": revision(), "map_id": map_id, "instance_id": instance,
            "catalog_zone": dungeon.get("name"), "catalog_difficulty": dungeon.get("difficulty"),
            "unmapped": rows[:LIMIT], "omitted": max(0, len(rows)-LIMIT),
            "npc_entities_without_type": missing,
            "note": "Unmapped means absent from this bundled catalog, not a verified new creature or zone. "
                    "IDs without an NPC type cannot be named reliably. Counts describe retained records, not unique kills. "
                    "Names, difficulty, category and game patch are never guessed from damage or ID patterns."}
