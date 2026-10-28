"""Bounded catalog coverage from recorded IDs; never guess names or classifications."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import hashlib
import json

from ..meter.a2parser.lookup import _supplement, _table, dungeon_final_bosses, npc_info, supplement_dungeon
from ..meter.context import OBSERVED_ZONES, PVP_MAPS

LIMIT = 100


@lru_cache(maxsize=1)
def revision():
    from ..meter.a2parser.engine import OPEN_WORLD_MAPS
    tables = {key: _table(key, "en") for key in ("npcs", "dungeons")}
    tables.update(open_world_maps=sorted(OPEN_WORLD_MAPS), pvp_maps=PVP_MAPS, observed_zones=OBSERVED_ZONES,
                  supplement=_supplement(), coverage_rules=6)
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


@lru_cache(maxsize=1)
def supplement_source():
    """Where the bundled name supplement (``catalog-supplement.json``) came from and what it names."""
    try:
        doc = json.loads(files("aion2calc.meter.a2parser").joinpath("data", "catalog-supplement.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return {}
    source = doc.get("source") if isinstance(doc, dict) else None
    if not isinstance(source, dict):
        return {}
    return {**{key: source.get(key) for key in ("name", "urls", "retrieved_at", "note")},
            "npc_names": len(doc.get("npcs") or {}), "dungeon_names": len(doc.get("dungeons") or {})}


def gaps():
    """The catalog's own gap lists, for reporting upstream: named dungeon tiers with no curated or
    derived final boss, instances with a curated final boss but no dungeon name (labelled by that
    boss, marked derived, in reports), and final-boss codes the NPC table cannot back. Read from
    the bundled tables only; nothing is inferred and no name is invented."""
    from datetime import datetime, timezone
    from ..meter.context import derived_zone_label
    try:
        doc = json.loads(files("aion2calc.meter.a2parser").joinpath("data", "dungeon_final_bosses.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        doc = {}
    dungeons, npcs = _table("dungeons", "en"), _table("npcs", "en")
    curated = {int(k): [c for c in v if isinstance(c, int)] for k, v in (doc.get("final_bosses") or {}).items() if str(k).isdigit()}
    derived = {int(k): v for k, v in (doc.get("derived_final_bosses") or {}).items() if str(k).isdigit()}
    tiers = [{"instance_id": int(i), "name": row.get("name"), "difficulty": row.get("difficulty")}
             for i, row in sorted(dungeons.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0)
             if str(i).isdigit() and int(i) not in curated and int(i) not in derived]
    unnamed = []
    for instance, codes in sorted(curated.items()):
        if dungeons.get(str(instance), {}).get("name"):
            continue
        names = sorted({npcs.get(str(c), {}).get("name") for c in codes} - {None, ""})
        unnamed.append({"instance_id": instance, "final_bosses": names, "codes": sorted(codes),
                        "label": derived_zone_label(instance),
                        # what reports show instead of the label (the name supplement, DBAion2), else None
                        "supplement_name": supplement_dungeon(instance).get("name")})
    codes_without_npc = []
    for instance, codes in sorted(curated.items()):
        for code in sorted(codes):
            row = npcs.get(str(code))
            problem = ("no NPC record" if row is None else "no name" if not row.get("name")
                       else None if row.get("isBoss") else "not flagged as a boss")
            if problem:
                codes_without_npc.append({"instance_id": instance, "code": code, "problem": problem})
    return {"format": "a2catalog-gaps", "version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "catalog_revision": revision(), "catalog_source": source(),
            "counts": {"named_tiers_without_final_boss": len(tiers), "unnamed_instances_with_final_boss": len(unnamed),
                       "final_boss_codes_without_npc": len(codes_without_npc), "curated_instances": len(curated),
                       "derived_tiers": len(derived)},
            "named_tiers_without_final_boss": tiers, "unnamed_instances_with_final_boss": unnamed,
            "final_boss_codes_without_npc": codes_without_npc,
            "note": "Read from the bundled community catalog and the curated final-boss table only. Unnamed instances are "
                    "shown in reports as '<Final boss> (instance N)', marked derived; a dungeon name is never inferred. "
                    "Report the lists upstream with the catalog source revision; a capture of a boss in an unmapped tier "
                    "is what resolves the first list."}


def known_instance(code) -> bool:
    """Whether the catalogs know an instance id: a dungeon either table names (the community
    catalog's, or the supplement's), an instance the NPC catalog places its NPCs in (the Nightmare
    map, the Ascension trials) or one with a curated final boss. Recorded as a map (a map-instanced
    dungeon, or an entry whose instance id was not sent) it is the same instance."""
    from ..meter.context import _instances
    return bool(code) and (str(code) in _table("dungeons", "en") or bool(supplement_dungeon(code))
                           or code in _instances() or bool(dungeon_final_bosses(code)))


def struck_as_players(segment):
    """The entities a segment's damage records show striking with a player's own class skills and never
    with an NPC's: players the recording had no identity record for (an arena opponent, a stranger in
    the Abyss), which a meter of 0.2.353 or earlier exported as enemies without an NPC type."""
    from ..meter.a2parser.engine import NPC_SKILLS, _own_class_skill
    classes, npcs = set(), set()
    for event in segment.get("events") or ():
        skill = event.get("skill_id")
        if event.get("kind") != "damage" or event.get("source") is None or type(skill) is not int:
            continue
        if _own_class_skill(skill):
            classes.add(event["source"])
        elif NPC_SKILLS[0] <= skill < NPC_SKILLS[1]:
            npcs.add(event["source"])
    return classes - npcs


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
    players = struck_as_players(segment)
    unnamed_players = 0
    for entity in candidates:
        code = entity.get("mob_code")
        if not valid_id(code):
            actor = entity.get("id")
            if actor in players:
                unnamed_players += 1           # a player, not an NPC whose type is missing
                continue
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
    if instance and not known_instance(instance):
        rows.append({"kind": "instance", "code": instance, "entity_count": 0, "effects": 0})
    if (map_id and map_id not in OPEN_WORLD_MAPS and map_id not in PVP_MAPS and map_id not in OBSERVED_ZONES
            and not known_instance(map_id)):
        rows.append({"kind": "map", "code": map_id, "entity_count": 0, "effects": 0})
    rows.sort(key=lambda r: (r["kind"], r["code"]))
    from ..meter.context import classify
    classification = segment.get("classification") or classify(map_id, instance, str(segment.get("encounter_type") or "").startswith("pvp_"), candidates)["classification"]
    return {"classification":classification, "catalog_revision": revision(), "catalog_source": source(), "map_id": map_id, "instance_id": instance,
            "catalog_zone": dungeon.get("name") or supplement_dungeon(instance).get("name"), "catalog_difficulty": dungeon.get("difficulty"),
            "unmapped": rows[:LIMIT], "omitted": max(0, len(rows)-LIMIT),
            "npc_entities_without_type": len(missing_rows),
            "unidentified_entities": missing_rows[:LIMIT],
            "unidentified_omitted": max(0, len(missing_rows)-LIMIT),
            "unnamed_players": unnamed_players,
            "note": "Unmapped means absent from this bundled catalog and its name supplement, not a verified new creature or zone. "
                    "Actor references without an NPC type are session-local, not reusable NPC catalog IDs; one that struck only with a player's class skills is counted as an unnamed player instead. "
                    "They cannot be named reliably. Counts describe retained records, not unique kills. "
                    "Context suggestions use explicit NPC catalog category/tier fields only. Names, difficulty, category and game build are never guessed from damage or ID patterns."}
