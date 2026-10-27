"""Movement (0.2.350): where entities were, decoded from the server's movement records (``1c 37``, ``1a``/``1b 37``,
``2f 37``, ``3c 37``, ``41 36``), the effect record's applier position, a targeted cast's target position and a party
member's status, kept per entity for the party and the enemies that matter, and exported per segment as ``movement``.
The layouts come from the 20 and 23 October captures (docs/open-investigations.md, *Movement for encounter replay*)."""
import copy
import struct

import pytest

from aion2calc.combat import a2log
from aion2calc.combat.reconstruction import combine
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.a2parser.parser import scan_actions, scan_party_status, scan_positions
from aion2calc.meter.session import CombatSession

ME, ALLY, BOSS, STRANGER = 4062, 4063, 51000, 77001
WAVE_BLOW, RUINOUS_BLOW = 18080000, 11100000
STREAM = "1.2.3.4:13328->192.168.1.9:57424"


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


def _xyz(x, y, z):
    return struct.pack("<3f", x, y, z)


def _move(entity, x, y, z, heading=0, flags=b"\x04"):
    return _frame(b"\x1c\x37", _varint(entity) + flags + _xyz(x, y, z) + heading.to_bytes(2, "little") + b"\x00\x01")


def _effect(target, source, x, y, z):
    return _frame(b"\x2b\x38", _varint(target) + b"\x13" + _varint(2634) + (WAVE_BLOW * 10 + 1).to_bytes(4, "little")
                  + (3000).to_bytes(8, "little") + (1792114870012).to_bytes(8, "little") + _varint(source) + b"\x0c"
                  + WAVE_BLOW.to_bytes(4, "little") + b"\x01\x02" + _xyz(x, y, z))


def _cast(actor, target, x, y, z):
    return _frame(b"\x02\x38", _varint(actor) + b"\x00" + (RUINOUS_BLOW + 450).to_bytes(4, "little") + bytes([8, 2])
                  + _varint(target) + struct.pack("<f", 173.2) + _xyz(x, y, z) + _varint(12609) + b"\x01" + _varint(40900))


def _status(character_id, x, y, z, server=2102):
    dbid = (server << 48) | character_id
    body = (dbid.to_bytes(8, "little") + (20).to_bytes(4, "little") + (20).to_bytes(4, "little") + (1).to_bytes(4, "little")
            + (602).to_bytes(4, "little") + _xyz(x, y, z) + (45).to_bytes(4, "little") + bytes(4) + (2575).to_bytes(4, "little")
            + b"\x00" + (2).to_bytes(4, "little") + b"\x01" + (127_918).to_bytes(8, "little") + b"\x01")
    return _frame(b"\x1c\x92", body)


def _hp(entity):
    return _frame(b"\x1b\x92", _varint(entity) + _varint(27_061) + _varint(27_061) + bytes(24))


# ------------------------------------------------------------------ decoder
def test_each_movement_record_gives_the_entity_and_where_it_is():
    [move] = scan_positions(_move(BOSS, 13631.1, -9851.9, 93124.0, heading=16384))
    assert move == {"kind": "position", "entity": BOSS, "x": 13631.1, "y": -9851.9, "z": 93124.0, "src": "move", "heading": 90.0}
    # an odd first flag byte means a second one before X
    [odd] = scan_positions(_move(BOSS, 100.5, 200.5, 300.5, heading=32768, flags=b"\x05\x02"))
    assert (odd["x"], odd["y"], odd["z"], odd["heading"]) == (100.5, 200.5, 300.5, 180.0)
    for opcode, src in ((b"\x1a\x37", "start"), (b"\x1b\x37", "stop")):
        [row] = scan_positions(_frame(opcode, _varint(ALLY) + b"\x01\x00" + _xyz(50148.0, -48674.9, 20422.0) + b"\x00"))
        assert (row["entity"], row["src"], row["x"], row["y"], row["z"]) == (ALLY, src, 50148.0, -48674.9, 20422.0)
        assert "heading" not in row
    [fast] = scan_positions(_frame(b"\x2f\x37", _varint(BOSS) + b"\x02" + _xyz(-1500.0, 2500.0, 10.0) + bytes(16)))
    assert (fast["src"], fast["x"], fast["y"]) == ("fast", -1500.0, 2500.0)
    land_body = _varint(ME) + b"\x00" + _xyz(74760.3, -22831.5, 3470.6) + struct.pack("<f", 271.5) + b"\x00\x00\x01" + (11000100).to_bytes(4, "little")
    [land] = scan_positions(_frame(b"\x3c\x37", land_body))
    assert (land["entity"], land["src"], land["heading"], land["skill"]) == (ME, "land", 271.5, 11000100)
    spawn_body = _varint(BOSS) + bytes(9) + _xyz(1200.0, 3400.0, 56.0) + struct.pack("<f", 45.0) + bytes(6)
    [spawn] = scan_positions(_frame(b"\x41\x36", spawn_body))
    assert (spawn["src"], spawn["x"], spawn["heading"]) == ("spawn", 1200.0, 45.0)


def test_records_that_do_not_read_as_a_position_are_ignored():
    assert scan_positions(_move(BOSS, 0.2, 0.4, 5000.0)) == []                          # the origin: not a place
    assert scan_positions(_move(BOSS, float("nan"), 1000.0, 1000.0)) == []
    assert scan_positions(_move(BOSS, 2_000_000.0, 1000.0, 1000.0)) == []              # off any map
    assert scan_positions(_move(42, 1000.0, 1000.0, 1000.0)) == []                     # not an entity id
    assert scan_positions(_move(BOSS, 1000.0, 1000.0, 1000.0)[:-10]) == []             # cut short
    assert scan_positions(_frame(b"\x1d\x37", _varint(BOSS) + b"\x04" + _xyz(1000.0, 1000.0, 1000.0))) == []   # not decoded
    assert scan_positions(b"") == []


def test_an_effect_carries_its_appliers_position_and_a_targeted_cast_its_targets():
    [effect] = scan_actions(_effect(BOSS, ME, 74760.3, -22831.5, 3470.6))
    assert (effect["target"], effect["source"], effect["position"]) == (BOSS, ME, [74760.3, -22831.5, 3470.6])
    [cast] = scan_actions(_cast(BOSS, ME, 13631.1, -9851.9, 93124.0))
    assert (cast["actor"], cast["target"], cast["position"]) == (BOSS, ME, [13631.1, -9851.9, 93124.0])
    [blank] = scan_actions(_cast(BOSS, ME, 0.0, 0.0, 0.0))                             # no position, the rest still read
    assert "position" not in blank and blank["cooldown_ms"] == 40900
    assert scan_party_status(_status(322_274, 50148.0, -48674.9, 20422.0))["position"] == [50148.0, -48674.9, 20422.0]
    assert "position" not in scan_party_status(_status(322_274, 0.0, 0.0, 0.0))


def test_the_engine_gathers_each_reads_positions_with_their_sources():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.local_player_id = ME
    engine.names.update({ME: "Me", ALLY: "Ally"})
    batch = (_move(BOSS, 1000.0, 2000.0, 30.0, heading=16384) + _effect(BOSS, ME, 1010.0, 2010.0, 30.0)
             + _cast(BOSS, ME, 1020.0, 2020.0, 30.0) + _hp(ALLY) + _status(322_274, 1030.0, 2030.0, 30.0))
    engine.consume(batch, 5_000, STREAM)
    rows = sorted((p["src"], p["entity"], p["x"], p["timestamp_ms"]) for p in engine.positions)
    assert rows == [("applied", ME, 1010.0, 5_000),     # where the recording player stood when they applied the effect
                    ("move", BOSS, 1000.0, 5_000),
                    ("party", ALLY, 1030.0, 5_000),     # the member's status, once the batch paired them with their entity
                    ("targeted", ME, 1020.0, 5_000)]    # the boss's cast aimed at the recording player
    engine.consume(_frame(b"\x05\xe0", _varint(BOSS) + b"\x03\x01" + (1200).to_bytes(4, "little") + (990).to_bytes(4, "little") + b"\x02"),
                   6_000, STREAM)
    assert engine.positions == []                        # positions are per read


# ------------------------------------------------------------------ session
def _engine():
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600053
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = ME
    engine.names = {ME: "Me", ALLY: "Ally"}
    engine.known_players = {ME, ALLY}
    engine.roster = {"Me": {}, "Ally": {}}
    engine.spawn_info = {BOSS: {"mobCode": 2300615}}
    return engine


def _at(entity, t, x, src="move", heading=None):
    row = {"kind": "position", "entity": entity, "x": x, "y": -500.0, "z": 20.0, "src": src, "timestamp_ms": t}
    if heading is not None:
        row["heading"] = heading
    return row


def _observe(session, engine, t, events=(), positions=()):
    engine.positions = list(positions)
    session.observe(engine, list(events), timestamp_ms=t)
    engine.positions = []


def _hit(actor, t):
    return DamageEvent(actor_id=actor, target_id=BOSS, skill_code=RUINOUS_BLOW, damage=1000, timestamp_ms=t)


def _fight():
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 105_000, positions=[_at(BOSS, 105_000, 900.0, "spawn", heading=12.3),
                                            _at(ALLY, 104_000, 950.0), _at(ALLY, 105_000, 960.0)])
    _observe(s, engine, 110_000, events=[_hit(ME, 110_000)],
             positions=[_at(ME, 110_000, 1000.0, "applied"), _at(BOSS, 110_000, 1100.0, heading=90.0),
                        _at(STRANGER, 110_000, 5000.0)])                                  # nobody the party knows
    _observe(s, engine, 110_100, positions=[_at(BOSS, 110_100, 1101.0),                   # within 250 ms of the last
                                            _at(BOSS, 110_200, 1102.0, "stop")])          # a stop is always kept
    _observe(s, engine, 112_000, events=[_hit(ALLY, 112_000)], positions=[_at(ALLY, 112_000, 1200.0, "party")])
    _observe(s, engine, 113_000, events=[_hit(ME, 113_000)], positions=[_at(ME, 113_000, 1300.0, "targeted")])
    return s


def test_a_segment_exports_where_its_party_and_boss_were():
    s = _fight()
    doc = s.to_a2log()
    segment = doc["segments"][-1]
    ref = {p["name"]: p["id"] for p in doc["players"]}
    boss = next(e["id"] for e in segment["entities"] if e.get("mob_code") == 2300615)
    rows = [(m["t"], m["entity"], m["x"], m["src"], m.get("heading")) for m in segment["movement"]]
    assert rows == [
        (0.0, boss, 900.0, "spawn", 12.3),             # the last place known before the fight, at t = 0
        (0.0, ref["Ally"], 960.0, "move", None),
        (0.0, ref["Me"], 1000.0, "applied", None),
        (0.0, boss, 1100.0, "move", 90.0),
        (0.2, boss, 1102.0, "stop", None),             # the move at 0.1 s fell inside the 250 ms throttle
        (2.0, ref["Ally"], 1200.0, "party", None),
        (3.0, ref["Me"], 1300.0, "targeted", None)]
    assert all(m["entity"] in {*ref.values(), boss} for m in segment["movement"])       # the stranger is left out
    cleaned = a2log.validate(doc)["segments"][-1]
    assert [m["x"] for m in cleaned["movement"]] == [m["x"] for m in segment["movement"]]


def test_kept_positions_are_packed_and_a_detached_copy_needs_no_throttle_state():
    s = _fight()
    assert all(isinstance(row, bytes) and len(row) == 31 for row in s.positions)
    clone = copy.deepcopy(s)
    assert list(clone.positions) == list(s.positions) and clone._position_kept == {} and s._position_kept
    assert clone.to_a2log()["segments"][-1]["movement"] == s.to_a2log()["segments"][-1]["movement"]


def test_the_validator_keeps_only_well_formed_movement():
    doc = {"format": "a2log", "version": 1, "meta": {}, "players": [{"id": "p1", "name": "Me"}],
           "segments": [{"duration": 10, "hits": [], "entities": [{"id": "b", "name": "Boss", "kind": "enemy", "is_boss": True}],
                         "movement": [{"t": 1, "entity": "p1", "x": 1.5, "y": 2.5, "z": 3.5, "src": "applied", "heading": 90},
                                      {"t": 2, "entity": "b", "x": 1, "y": 2, "z": 3, "src": "move", "heading": 400},   # heading dropped
                                      {"t": 2, "entity": "nobody", "x": 1, "y": 2, "z": 3, "src": "move"},
                                      {"t": 2, "entity": "b", "x": 1, "y": 2, "z": 3, "src": "teleport"},
                                      {"t": 11, "entity": "b", "x": 1, "y": 2, "z": 3, "src": "move"},
                                      {"t": 2, "entity": "b", "x": 1e7, "y": 2, "z": 3, "src": "move"},
                                      {"t": 2, "entity": "b", "x": "1", "y": 2, "z": 3, "src": "move"},
                                      "not a row"]}]}
    segment = a2log.validate(doc)["segments"][0]
    assert segment["movement"] == [{"t": 1.0, "entity": "p1", "x": 1.5, "y": 2.5, "z": 3.5, "src": "applied", "heading": 90.0},
                                   {"t": 2.0, "entity": "b", "x": 1.0, "y": 2.0, "z": 3.0, "src": "move"}]
    assert segment["validation"]["filtered"] == 6


def test_a_recording_from_before_movement_has_none():
    doc = {"format": "a2log", "version": 1, "meta": {}, "players": [{"id": "p1", "name": "Me"}],
           "segments": [{"duration": 10, "hits": [], "entities": []}]}
    assert a2log.validate(doc)["segments"][0]["movement"] == []


def test_a_combined_review_points_movement_at_the_combined_references(tmp_path, monkeypatch):
    import uuid
    from aion2calc.combat import sessions
    from aion2calc.combat.archive import retained_range
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    archive = uuid.uuid4().hex
    engine = _engine()
    part1 = CombatSession()
    part1.pvp = False
    _observe(part1, engine, 101_000)
    _observe(part1, engine, 110_000, events=[_hit(ME, 110_000), _hit(ALLY, 110_500)],
             positions=[_at(ME, 110_000, 1000.0, "applied"), _at(BOSS, 110_000, 1100.0)])
    doc1 = part1.to_a2log("party", "Part 1")
    cont1 = retained_range(part1, uuid.uuid4().hex, None)
    doc1["meta"]["archive"] = {"id": archive, "part": 1, "closed": True, "continuity": cont1}
    engine.last_zone_reset_ms = None
    part2 = part1.continuation()
    _observe(part2, engine, 400_000, events=[_hit(ME, 400_000), _hit(ALLY, 400_500)],
             positions=[_at(ALLY, 400_000, 2000.0), _at(BOSS, 400_000, 2100.0)])
    doc2 = part2.to_a2log("party", "Part 2")
    doc2["meta"]["archive"] = {"id": archive, "part": 2, "closed": False,
                               "continuity": retained_range(part2, uuid.uuid4().hex, cont1)}
    sessions.save(doc1, "session-20261027-000001-aaaaaa.a2log.json")
    combined = combine(sessions.live_archive_sources(doc2))
    players = {p["id"] for p in combined["players"]}
    for segment in combined["segments"]:
        known = players | {e["id"] for e in segment["entities"]}
        assert segment["movement"] and all(m["entity"] in known for m in segment["movement"])
    assert [m["x"] for s in combined["segments"] for m in s["movement"]] == [1000.0, 1100.0, 2000.0, 2100.0]


@pytest.mark.parametrize("src", ["start", "land", "spawn"])
def test_moments_that_matter_skip_the_throttle(src):
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, 110_000)],
             positions=[_at(BOSS, 110_000, 1001.0), _at(BOSS, 110_050, 1002.0, src), _at(BOSS, 110_100, 1003.0)])
    _observe(s, engine, 111_000, events=[_hit(ME, 111_000)])
    assert [m["x"] for m in s.to_a2log()["segments"][-1]["movement"]] == [1001.0, 1002.0]


def test_an_observe_without_a_new_read_keeps_nothing_twice():
    # Naming the character in Settings observes again with no new read: the last read's positions and actions
    # are not kept a second time.
    engine, s = _engine(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    engine.positions = [_at(BOSS, 110_000, 1100.0, "stop")]
    engine.actions = [{"kind": "cast", "actor": ME, "skill": RUINOUS_BLOW + 450, "seq": 8, "at_target": True,
                       "target": BOSS, "timestamp_ms": 110_000}]
    s.observe(engine, [_hit(ME, 110_000)], timestamp_ms=110_000)
    s.observe(engine, [])
    assert len(s.positions) == 1 and len(s.actions) == 1
    engine.positions = [_at(BOSS, 110_500, 1101.0, "stop")]                  # the next read is kept
    s.observe(engine, [], timestamp_ms=110_500)
    assert len(s.positions) == 2
