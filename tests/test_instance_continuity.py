"""A zone load back into the same instance (a revive after a wipe, an in-instance teleport)
keeps the instance id, and a final boss whose own spawn is never decoded is named by the HP
signature of its same-named copies."""
from aion2calc.meter.a2parser.engine import MeterEngine, OPEN_WORLD_MAPS


def test_a_reload_into_the_same_instance_map_keeps_the_instance_id():
    e = MeterEngine()
    e.map_id, e.dungeon_id = 600058, 600058
    e._reset_zone(10_000)                                   # the revive's zone load
    assert e.dungeon_id == 0 and e._left_instance == (600058, 600058) and not e.instance_restored
    e._note_map(600058)                                     # the zone state packet names the same map
    assert e.dungeon_id == 600058 and e.instance_restored
    e._update_roster({"Me": {}}, True, 600058)              # a roster packet names the instance itself
    assert e.dungeon_id == 600058 and not e.instance_restored


def test_leaving_for_the_open_world_or_another_map_forgets_the_instance():
    e = MeterEngine()
    e.map_id, e.dungeon_id = 600058, 600058
    e._reset_zone(10_000)
    e._note_map(next(iter(OPEN_WORLD_MAPS)))
    assert e.dungeon_id == 0 and not e.instance_restored
    e.map_id, e.dungeon_id = 600058, 600058
    e._reset_zone(20_000)
    e._note_map(600022)                                     # a different instance map: nothing to restore
    assert e.dungeon_id == 0 and not e.instance_restored


def test_the_decoder_restores_the_instance_where_it_reads_the_zone_state():
    import inspect
    from aion2calc.meter.a2parser import engine as module
    src = inspect.getsource(module)
    zone = src.index("zone_change, map_id = scan_zone_state(complete)")
    assert "self._note_map(map_id)" in src[zone:zone + 6000]


def test_a_spawnless_final_boss_is_named_by_its_copies_hp_signature():
    e = MeterEngine()
    e.map_id, e.dungeon_id = 600022, 600022                 # Fire Temple (Conquest [Normal]); final boss 2300371
    # the phase copies spawn with a non-boss catalog code but the boss's own name and max HP
    e.spawn_info[25431] = {"mobCode": 2920347, "maxHp": 15_504_000, "currentHp": 15_504_000, "reportedMaxHp": 15_504_000}
    e._identify_boss_by_hp({23816: 15_501_104.0}, {})      # the body: no spawn, HP packets only
    assert e.boss_hp_seen[2300371] == 15_504_000.0
    assert e.spawn_info[23816]["mobCode"] == 2300371 and e.spawn_info[23816]["inferred"] == "hp_signature"
    # trash at another HP is never promoted
    e._identify_boss_by_hp({99: 1_200_000.0}, {})
    assert 99 not in e.spawn_info
