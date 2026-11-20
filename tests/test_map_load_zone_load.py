"""A map load stands in for the zone load (0.2.410).

Since the game's 18 November 2026 patch no recording counts a zone load: the self zone change (``23 36``) is no
longer recognised, so a run's entry was seen only when its party came straight from the open world. Every Vakron
Sky Island run, entered from elsewhere, was a partial capture, and the previous zone's players stayed on. The map
load (``21 36``) still comes with every load: in the October captures it came 0.1 to 7.7 s before the zone change,
with a count of 1 to 43, while other records sharing its opcode read a count in the billions and maps that do not
exist. A map load within those bounds now resets the zone, with the zone change's own rules, and the zone change
that follows it is the same load. Once a zone change has followed a map load, the client still sends it (one from
before the patch, or a region not yet patched) and the zone change alone resets, as it always did; a map load with
none after it hands the resets back to the map loads.
"""
import pytest

from aion2calc.meter.a2parser import engine as engine_module
from aion2calc.meter.a2parser.engine import MeterEngine, OPEN_WORLD_MAPS
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.a2parser.parser import scan_map_load, scan_zone_state
from aion2calc.meter.session import CombatSession

STREAM = "1.2.3.4:13328->192.168.1.9:57424"
TOWN, VAKRON = 200003, 600073               # a town the open-world list leaves out, and Vakron Sky Island (hard)
ME, MATE, BOSS = 4062, 4063, 9001


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _frame(opcode, body):
    inner = opcode + body
    return _varint(len(inner) + 4) + inner


def _map(map_id, count=1):
    return _frame(b"\x21\x36", count.to_bytes(4, "little") + map_id.to_bytes(4, "little") + bytes(35))


def _zone_change():
    return _frame(b"\x23\x36", _varint(0) + bytes(8))


def _hit(actor, target, t, dmg=500):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _engine():
    engine = MeterEngine()
    engine.set_server_port(13328)
    return engine


# ------------------------------------------------------------------ decoder
def test_a_map_load_within_its_bounds_names_its_map():
    assert TOWN not in OPEN_WORLD_MAPS and VAKRON not in OPEN_WORLD_MAPS
    assert scan_map_load(_map(VAKRON, count=43)) == VAKRON
    assert scan_zone_state(_map(VAKRON))[1] == VAKRON                     # the map is still named as before


@pytest.mark.parametrize("frame", [
    _map(VAKRON, count=2_381_440_308),          # a "count" in the billions: another record with the same opcode bytes
    _map(2_934_728_738),                        # a map that does not exist
    _map(0),
    _frame(b"\x21\x36", (1).to_bytes(4, "little") + b"\x73"),            # cut short before its map
    _zone_change(),
])
def test_other_records_are_no_map_load(frame):
    assert scan_map_load(frame) is None


# ------------------------------------------------------------------ engine
def test_with_map_loads_alone_each_load_resets_the_zone():
    engine = _engine()
    engine.consume(_map(TOWN), 10_000, STREAM)
    assert engine.last_zone_reset_ms == 10_000
    engine.consume(_map(VAKRON), 60_000, STREAM)
    assert engine.last_zone_reset_ms == 60_000 and engine.map_id == VAKRON
    engine.consume(_map(VAKRON, count=2_381_440_308), 120_000, STREAM)   # not a map load: no reset
    assert engine.last_zone_reset_ms == 60_000


def test_a_map_load_follows_the_zone_changes_rules():
    engine = _engine()
    engine.consume(_map(TOWN), 10_000, STREAM)
    engine.consume(_map(TOWN), 12_000, STREAM)                           # within 4 s of the last load
    assert engine.last_zone_reset_ms == 10_000
    engine.last_damage_time_ms = 59_000
    engine.consume(_map(VAKRON), 60_000, STREAM)                         # within 1.5 s of damage
    assert engine.last_zone_reset_ms == 10_000


def test_the_zone_change_after_its_map_load_is_the_same_load():
    engine = _engine()
    engine.consume(_map(VAKRON), 60_000, STREAM)
    engine.names[ME] = "Me"                                              # the new zone's names, read after its map load
    engine.consume(_zone_change(), 66_000, STREAM)                       # 6 s later, as before the patch
    assert engine.last_zone_reset_ms == 60_000 and engine.names[ME] == "Me"
    engine.consume(_map(TOWN), 200_000, STREAM)
    engine.consume(_zone_change(), 212_000, STREAM)                      # past the 10 s window: a load of its own
    assert engine.last_zone_reset_ms == 212_000


def test_a_zone_change_after_damage_is_a_new_load():
    engine = _engine()
    engine.consume(_map(VAKRON), 60_000, STREAM)
    engine.last_damage_time_ms = 62_000                                  # a fight since the map load
    engine.consume(_zone_change(), 66_000, STREAM)
    assert engine.last_zone_reset_ms == 66_000


def test_a_zone_change_alone_still_resets():
    engine = _engine()
    engine.consume(_zone_change(), 60_000, STREAM)
    assert engine.last_zone_reset_ms == 60_000


def test_a_client_that_still_sends_the_zone_change_resets_at_it_as_before():
    """A client from before the patch (or a region not yet patched): once a zone change has followed a map load, the
    map loads wait for theirs, and each load resets where it always did."""
    engine = _engine()
    engine.consume(_map(TOWN), 10_000, STREAM)                           # the first load: its map load resets
    engine.consume(_zone_change(), 13_000, STREAM)                       # its zone change: the same load
    assert engine.last_zone_reset_ms == 10_000
    engine.consume(_map(VAKRON), 60_000, STREAM)
    assert engine.last_zone_reset_ms == 10_000                           # waits for its zone change
    engine.consume(_zone_change(), 64_000, STREAM)
    assert engine.last_zone_reset_ms == 64_000


def test_a_client_that_stops_sending_it_is_read_from_its_map_loads():
    engine = _engine()
    engine.consume(_map(TOWN), 10_000, STREAM)
    engine.consume(_zone_change(), 13_000, STREAM)
    engine.consume(_map(VAKRON), 60_000, STREAM)                         # no zone change after this one
    engine.consume(_map(TOWN), 200_000, STREAM)                          # so this map load is the load
    assert engine.last_zone_reset_ms == 200_000


# ------------------------------------------------------------------ session
def _enter_vakron_from_town(engine, session):
    engine.consume(_map(TOWN), 10_000, STREAM)
    session.observe(engine, [], timestamp_ms=10_000)
    engine.consume(_map(VAKRON), 60_000, STREAM)                         # the load into the dungeon, and no zone change
    engine.local_player_id = ME
    engine.names.update({ME: "Me", MATE: "Mate"})
    engine.known_players.update({ME, MATE})
    engine.roster = {"me": {}, "mate": {}}
    engine.dungeon_id = VAKRON                                           # the party roster names the instance
    session.observe(engine, [], timestamp_ms=60_100)
    session.observe(engine, [_hit(ME, BOSS, 70_000), _hit(MATE, BOSS, 71_000)], timestamp_ms=71_000)


def test_a_dungeon_entered_from_a_town_with_map_loads_alone_has_its_entry():
    engine, session = _engine(), CombatSession()
    session.begin_capture()
    session.pvp = False
    _enter_vakron_from_town(engine, session)
    run = session.runs[session.run]
    assert run["start_observed"] is True and run["instance_id"] == VAKRON
    assert session.snapshot(scope="party")["partial_capture"] is False


def test_without_the_map_load_the_same_entry_was_a_partial_capture(monkeypatch):
    """What every recording since the patch did: nothing counted as a zone load."""
    monkeypatch.setattr(engine_module, "scan_map_load", lambda data: None)
    engine, session = _engine(), CombatSession()
    session.begin_capture()
    session.pvp = False
    _enter_vakron_from_town(engine, session)
    run = session.runs[session.run]
    assert not run.get("start_observed")
    assert session.snapshot(scope="party")["partial_capture"] is True
