"""Conservative map classification; unknown content is deliberately left untyped."""
from .a2parser.lookup import _table


# Map 61 was observed in the user-confirmed arena diagnostic
# meter-20261006-203415-c458c5.zip (SHA-256 below). Its specific arena name
# is not established; map 60 has separate screenshot confirmation.
PVP_MAPS = {
    60: {"zone":"Fire Temple Arena", "evidence":"User-confirmed arena capture and result screenshot"},
    61: {"zone":"Arena (map 61)", "evidence":"User-confirmed arena capture c9277026181bf976ea62f8438b939cb35aeee34bba192c4208a9aac2c6f1b127; specific arena name unverified"},
}


def classify(map_id, instance_id, pvp):
    from .a2parser.engine import OPEN_WORLD_MAPS
    if pvp and map_id in PVP_MAPS:
        record = PVP_MAPS[map_id]
        return {"zone":record["zone"], "encounter_type":"pvp_arena",
                "zone_source":record["evidence"],
                "encounter_type_source":"Recorded map + identified player combat + confirmed arena capture"}
    result = {}
    dungeon = _table("dungeons", "en").get(str(instance_id), {})
    name = dungeon.get("name")
    if name:
        result.update(zone=name, zone_source="Recorded instance ID + bundled dungeon name table")
    if not pvp and dungeon.get("difficulty"):
        result.update(difficulty=dungeon["difficulty"],
                      difficulty_source="Recorded instance ID + exact bundled dungeon difficulty")
    if map_id in OPEN_WORLD_MAPS:
        result.update(encounter_type="pvp_open_world" if pvp else "pve_open_world",
                      encounter_type_source="Recorded map ID + bundled open-world map table")
    return result
