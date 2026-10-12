"""The live meter can show each player's home server (world) next to their name. That
needs the per-player server id on the live snapshot rows — taken from the party roster,
or the local profile for yourself. (The id -> world name lookup and the off-by-default
toggle live in the app layer; this guards the snapshot plumbing the feature rests on.)"""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def test_live_snapshot_carries_each_players_home_server():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600001
    engine.last_zone_reset_ms = None
    engine.local_player_id = 4062
    engine.names = {4062: "Me", 4063: "MateA"}
    engine.known_players = {4062, 4063}
    engine.local_profile = {"serverId": 2102}        # your own server, from the profile
    engine.roster = {"Me": {"serverId": 2102}, "MateA": {"serverId": 3001}}  # party roster carries servers

    s.observe(engine, [_hit(4062, 9001, 1000), _hit(4063, 9001, 2000)], timestamp_ms=2000)
    snap = s.snapshot(scope="party", segment_id=None)
    by_name = {p["name"]: p for p in snap["players"]}
    # Your server comes from the profile; a party member's from the roster — both on the row.
    assert by_name["Me"].get("server") == "2102"
    assert by_name["MateA"].get("server") == "3001"


def test_server_is_absent_when_the_roster_has_none():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600001
    engine.last_zone_reset_ms = None
    engine.local_player_id = 4062
    engine.names = {4062: "Me"}
    engine.known_players = {4062}
    engine.local_profile = {}                         # no server known yet
    engine.roster = {"Me": {}}
    s.observe(engine, [_hit(4062, 9001, 1000)], timestamp_ms=1000)
    snap = s.snapshot(scope="party", segment_id=None)
    # No server recorded -> the row simply omits it (no crash, no empty string injected).
    assert snap["players"][0].get("server") is None
