"""Player deaths are recorded from the HP update that reads 0.

The game sends the in-combat death flag the decoder scans for NPCs, but a player's death
only shows as their HP dropping to 0 (a lethal hit, an HP update of 0, no actions until a
resurrection brings the HP back). A 37-minute dungeon recording carried 154 enemy death
markers, 25 player HP readings of 0 and not one player death — the viewer said "No markers"
for everyone. The engine now emits one death marker per player death from those readings.
"""
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
    engine.known_players = {5001, 5002}
    engine.roster = {"Me": {}, "Ally": {}}
    return s, engine


def test_a_players_zero_hp_reading_is_one_death_until_they_revive():
    engine = MeterEngine()
    engine.known_players = {5002}
    assert engine._player_deaths_from_hp({5002: 6741}, 1000) == []
    assert engine._player_deaths_from_hp({5002: 0}, 2000) == [{"kind": "death", "entity": 5002, "timestamp_ms": 2000}]
    assert engine._player_deaths_from_hp({5002: 0}, 2001) == []          # the duplicate 0 reading the scans produce
    assert engine._player_deaths_from_hp({5002: 19359}, 5000) == []      # resurrected to full
    assert engine._player_deaths_from_hp({5002: 0}, 9000) == [{"kind": "death", "entity": 5002, "timestamp_ms": 9000}]   # dies again later


def test_enemies_keep_their_flag_based_deaths_only():
    engine = MeterEngine()
    engine.known_players = {5001}
    assert engine._player_deaths_from_hp({9001: 0}, 1000) == []           # an NPC at 0 HP is not a player death
    assert engine._player_deaths_from_hp({5001: 0, 9001: 0}, 1000) == [{"kind": "death", "entity": 5001, "timestamp_ms": 1000}]


def test_the_death_marker_reaches_the_log_and_the_overlay_and_clears_on_revive():
    s, engine = _session()
    s.observe(engine, [_hit(5001, 9001, 1000, 2000), _hit(5002, 9001, 1500, 1000)], timestamp_ms=1500)
    # Ally's HP update reads 0 after a lethal hit: the engine turns it into a death marker.
    engine.telemetry = [{"kind": "hp", "entity": 5002, "current": 0, "max": 19359, "timestamp_ms": 3000}]
    engine.telemetry.extend(engine._player_deaths_from_hp({5002: 0}, 3000))
    s.observe(engine, [_hit(5001, 9001, 3000, 500)], timestamp_ms=3000)
    players = {row["name"]: row for row in s.snapshot(scope="auto", segment_id=None)["players"]}
    assert players["Ally"]["dead"] is True and players["Me"]["dead"] is False
    doc = s.to_a2log(scope="party", title="t")
    seg = doc["segments"][0]
    ally = next(p["id"] for p in doc["players"] if p["name"] == "Ally")
    deaths = [e for e in seg["events"] if e["kind"] == "death" and e["target"] == ally]
    assert len(deaths) == 1 and deaths[0]["t"] == 2.0            # 3000 ms into a fight that began at 1000 ms
    # Resurrection: an HP update above 0 clears the indicator.
    engine.telemetry = [{"kind": "hp", "entity": 5002, "current": 19359, "max": 19359, "timestamp_ms": 6000}]
    engine.telemetry.extend(engine._player_deaths_from_hp({5002: 19359}, 6000))
    s.observe(engine, [_hit(5002, 9001, 6000, 700)], timestamp_ms=6000)
    players = {row["name"]: row for row in s.snapshot(scope="auto", segment_id=None)["players"]}
    assert players["Ally"]["dead"] is False
    # A second death later is a second marker (the duplicate 0 readings in between are not).
    engine.telemetry = [{"kind": "hp", "entity": 5002, "current": 0, "max": 19359, "timestamp_ms": 9000}]
    engine.telemetry.extend(engine._player_deaths_from_hp({5002: 0}, 9000))
    engine.telemetry.extend(engine._player_deaths_from_hp({5002: 0}, 9001))
    s.observe(engine, [_hit(5001, 9001, 9000, 500)], timestamp_ms=9000)
    seg = s.to_a2log(scope="party", title="t")["segments"][0]
    assert [e["t"] for e in seg["events"] if e["kind"] == "death" and e["target"] == ally] == [2.0, 8.0]
