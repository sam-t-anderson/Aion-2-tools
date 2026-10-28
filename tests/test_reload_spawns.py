"""A zone load that keeps every actor id (a revive or a teleport inside the instance, the open world and
the Nightmare map of one server) sends no spawn record for an NPC still standing there: the type the
load cleared is carried over to an NPC that acts with no spawn record of its own since, once the
recording player turns out to keep their id too (0.2.354). A load that gives the player a new id
reassigned them all, so nothing is carried; nor to another map, to an NPC that was dead, or past an HP
record that disagrees. In the 20 October capture the final boss of Kromede's Desire, re-engaged after
a wipe and an in-place revive, otherwise fought on with no type."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

BOSS, ROCK, GUARD = 2300371, 2920091, 2950012        # Kromede's Desire, Gas Rock, Guard


def _engine(local=5001):
    e = MeterEngine()
    e.map_id = e.dungeon_id = 600022
    e.names, e.known_players = {local: "Me"}, {local}
    e.local_player_id, e.local_identity_from_game = local, True
    e.last_zone_reset_ms = None
    for entity, info in {9001: {"mobCode": BOSS, "maxHp": 4_000_000, "reportedMaxHp": 4_000_000, "currentHp": 2_500_000},
                         9002: {"mobCode": ROCK, "maxHp": 50_000, "reportedMaxHp": 50_000, "currentHp": 0},
                         9003: {"mobCode": GUARD, "maxHp": 80_000, "reportedMaxHp": 80_000, "currentHp": 80_000}}.items():
        e.spawn_info[entity] = dict(info)
        e._note_spawn(entity, info)                        # decoded on this map
    return e


def _hit(actor, target, t=20_000):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=11010000, damage=500, timestamp_ms=t)


def _code(e, entity):
    return (e.spawn_info.get(entity) or {}).get("mobCode")


def test_an_npc_standing_through_an_in_place_reload_keeps_its_type():
    e = _engine()
    e._reset_zone(10_000)
    assert e.spawn_info == {} and e._left_kept is None
    e.local_player_id = 5001                               # the player's record after the load: the same id
    e._carry_left_spawns([_hit(5001, 9001), _hit(9002, 5001)])
    assert _code(e, 9001) == BOSS and e.spawn_info[9001]["reportedMaxHp"] == 4_000_000
    assert _code(e, 9002) is None                          # it was dead when the load came
    assert _code(e, 9003) is None                          # carried only once it acts
    e._carry_left_spawns([_hit(9003, 5001)])
    assert _code(e, 9003) == GUARD


def test_the_npcs_acting_before_the_player_is_known_wait_for_it():
    e = _engine()
    e._reset_zone(10_000)
    e._carry_left_spawns([_hit(9001, 5001)])               # the load's first records: no self record yet
    assert _code(e, 9001) is None and e._left_waiting == {9001}
    e.local_player_id = 5001
    e._carry_left_spawns([])
    assert _code(e, 9001) == BOSS and not e._left_waiting


def test_a_load_that_gives_the_player_a_new_id_carries_nothing():
    e = _engine()
    e._reset_zone(10_000)
    e.local_player_id = 6001                               # entering an instance, leaving one: every id reassigned
    e._carry_left_spawns([_hit(6001, 9001)])
    assert _code(e, 9001) is None and e._left_spawns == {}
    e = _engine()
    e._cast_guess = {5001: 1}                              # a guess from casts tells nothing about the load
    e._reset_zone(10_000)
    assert e._left_kept is False and e._left_spawns == {}


def test_a_spawn_record_another_map_or_a_disagreeing_hp_record_wins():
    e = _engine()
    e._reset_zone(10_000)
    e.local_player_id = 5001
    e.spawn_info[9001] = {"mobCode": 2920347}               # the id was given to another NPC: its record came
    e._note_spawn(9001, e.spawn_info[9001])
    e.spawn_info[9003] = {"currentHp": 300_000, "maxHp": 300_000, "reportedMaxHp": 300_000}   # not the guard's HP
    e._carry_left_spawns([_hit(5001, 9001), _hit(5001, 9003)])
    assert _code(e, 9001) == 2920347 and _code(e, 9003) is None
    e = _engine()
    e._reset_zone(10_000)
    e._note_map(200003)                                    # the load went to another map
    e.local_player_id = 5001
    e._carry_left_spawns([_hit(5001, 9001)])
    assert _code(e, 9001) is None


def test_the_fight_after_the_reload_exports_its_boss():
    s, e = CombatSession(), _engine()
    s.pvp = False
    t0 = 1_000_000
    for i in range(3):
        s.observe(e, [_hit(5001, 9001, t0 + i * 1000)], timestamp_ms=t0 + i * 1000)
    e._reset_zone(t0 + 30_000)                              # a wipe and a revive in place
    e.names, e.known_players, e.local_player_id = {5001: "Me"}, {5001}, 5001
    e._note_map(600022)
    for i in range(3):
        t = t0 + 60_000 + i * 1000
        events = [_hit(5001, 9001, t)]
        e._carry_left_spawns(events)
        s.observe(e, events, timestamp_ms=t)
    after = [x for seg in s.to_a2log("party")["segments"] for x in seg["entities"] if x["id"].endswith(":9001")]
    assert len(after) == 2 and {x["id"].split(":")[0] for x in after} == {"0", "1"}
    assert all(x["mob_code"] == BOSS and x["is_boss"] for x in after)
