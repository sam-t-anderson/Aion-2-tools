"""Conservative map classification; unknown content is deliberately left untyped."""
from .a2parser.lookup import _table


def classify(map_id, instance_id, pvp):
    from .a2parser.engine import OPEN_WORLD_MAPS
    if pvp and map_id == 60:
        return {"zone": "Fire Temple Arena", "encounter_type": "pvp_arena",
                "zone_source": "Map 60 + identified player combat; user-confirmed arena capture",
                "encounter_type_source": "Observed map catalog v1"}
    result = {}
    name = _table("dungeons", "en").get(str(instance_id), {}).get("name")
    if name:
        result.update(zone=name, zone_source="Recorded instance ID + bundled dungeon name table")
    if map_id in OPEN_WORLD_MAPS:
        result.update(encounter_type="pvp_open_world" if pvp else "pve_open_world",
                      encounter_type_source="Recorded map ID + bundled open-world map table")
    return result
