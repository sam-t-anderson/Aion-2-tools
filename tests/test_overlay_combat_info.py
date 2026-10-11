"""Packet-sourced combat info the overlay shows: the local player's contribution
(share of the shown encounter) and the current target (the enemy the local player
hits most) with each contributor's damage/DPS. Both are derived from recorded
damage only — never invented."""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _session():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me", 5002: "Ally"}
    engine.roster = {"Me": {}, "Ally": {}}
    return s, engine


def test_contribution_is_the_local_players_share():
    s, engine = _session()
    # Me deals 3000 to the boss, Ally deals 1000 → Me's share is 75%.
    s.observe(engine, [_hit(5001, 9001, 1000, 2000), _hit(5001, 9001, 2000, 1000),
                       _hit(5002, 9001, 2000, 1000)], timestamp_ms=2000)
    snap = s.snapshot(scope="auto", segment_id=None)
    c = snap["contribution"]
    assert c is not None
    assert c["name"] == "Me"
    assert c["damage"] == 3000
    assert round(c["share"], 2) == 0.75


def test_current_target_is_the_enemy_the_local_player_hits_most():
    s, engine = _session()
    # Me hits boss 9001 harder than trash 9002; Ally also hits the boss.
    s.observe(engine, [_hit(5001, 9001, 1000, 5000), _hit(5001, 9002, 1500, 200),
                       _hit(5002, 9001, 2000, 2000)], timestamp_ms=2000)
    snap = s.snapshot(scope="auto", segment_id=None)
    target = snap["current_target"]
    assert target is not None
    assert str(9001) in target["key"]                 # the boss, not the trash mob
    assert target["is_player"] is False
    names = [c["name"] for c in target["contributors"]]
    assert names[0] == "Me"                            # ranked by damage to that target
    assert "Ally" in names
    me = next(c for c in target["contributors"] if c["name"] == "Me")
    assert me["damage"] == 5000 and me["dps"] > 0


def test_no_target_or_contribution_before_any_damage():
    s, engine = _session()
    s.observe(engine, [], timestamp_ms=1000)
    snap = s.snapshot(scope="auto", segment_id=None)
    assert snap["current_target"] is None
    assert snap["contribution"] is None
