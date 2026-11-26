"""Bosses with more than 100 million HP, and Corroded Decontamination Facility's final boss (0.2.514).

The 25 November raid's bosses come with more HP than any before: Black Blood Blatt 171,460,800, Terminator Bargott
244,944,000. The HP feed (``00 8d`` entity ``02 01 00``, the HP in the low half of a u64) was taken only up to
100,000,000, a ceiling against records of other data in the feed's shape, so the meter saw Bargott's HP only from 41 %
down: the overlay held the boss at full for most of the fight, and a wipe above that (the boss back at full) never started a
new attempt. A reading above the ceiling now counts up to the maximum HP the boss's own spawn record gave it.

The raid's final boss was taken for the Surveillance Device, its first boss (the highest boss code of the instance):
every run there ended at its death. Terminator Bargott, after Black Blood Blatt, ends the raid.
"""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.lookup import dungeon_final_bosses, npc_info
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.a2parser.parser import HP_FEED_CEILING, scan_hp_updates, scan_spawn_metadata
from aion2calc.meter.session import CombatSession

from test_combat_actions import _frame, _u32, _varint

STREAM = "1.2.3.4:13328->192.168.1.9:57424"
RAID = 620011
BARGOTT, BLATT, SURVEILLANCE_DEVICE = 2301208, 2301207, 2301216
BARGOTT_HP = 244_944_000
BOSS, ME, MATE = 17017, 5001, 5002


def _spawn(entity, code, hp):
    """A spawn record (``40 36``): the entity, its NPC code (3 bytes), ``00 40 02``, then ``01`` and its HP and maximum
    HP (varints)."""
    return _frame(b"\x40\x36", _varint(entity) + code.to_bytes(3, "little") + b"\x00\x40\x02\x01" + _varint(hp) + _varint(hp))


def _feed(entity, hp):
    """The HP feed: ``00 8d``, the entity, ``02 01 00`` and the HP in the low half of a u64."""
    return _frame(b"\x00\x8d", _varint(entity) + b"\x02\x01\x00" + _u32(hp) + b"\x00" * 4)


def _hit(actor, target, t, damage=500_000):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=damage, timestamp_ms=t)


def _in_the_raid():
    s = CombatSession()
    s.pvp = False
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = RAID
    engine.last_zone_reset_ms = None
    engine.local_player_id = ME
    engine.names = {ME: "Me"}
    engine.roster = {"Me": {}}
    return s, engine


def test_the_raids_bosses_are_catalog_bosses_of_the_raid():
    for code in (BARGOTT, BLATT, SURVEILLANCE_DEVICE):
        assert npc_info(code).get("isBoss") is True and npc_info(code).get("dungeonId") == RAID
    assert scan_spawn_metadata(_spawn(BOSS, BARGOTT, BARGOTT_HP)) == {
        BOSS: {"mobCode": BARGOTT, "currentHp": BARGOTT_HP, "maxHp": BARGOTT_HP}}


def test_a_reading_above_the_ceiling_counts_up_to_the_spawn_records_maximum():
    reading = _feed(BOSS, 150_000_000)
    assert scan_hp_updates(reading) == ({}, {})                                   # no maximum to check it against
    assert scan_hp_updates(reading, lambda entity: BARGOTT_HP)[0] == {BOSS: 150_000_000}
    assert scan_hp_updates(_feed(BOSS, BARGOTT_HP), lambda entity: BARGOTT_HP)[0] == {BOSS: BARGOTT_HP}   # back at full
    assert scan_hp_updates(_feed(BOSS, BARGOTT_HP + 1), lambda entity: BARGOTT_HP) == ({}, {})
    # a record of other data in the feed's shape: 4,043,461,478 HP for an enemy whose spawn record gave it 17,540
    assert scan_hp_updates(_feed(10067, 4_043_461_478), lambda entity: 17_540) == ({}, {})
    assert scan_hp_updates(_feed(10067, 4_043_461_478), lambda entity: None) == ({}, {})
    # up to the ceiling a reading counts as before, whatever the maximum
    assert scan_hp_updates(_feed(BOSS, HP_FEED_CEILING), lambda entity: 17_540)[0] == {BOSS: HP_FEED_CEILING}
    assert scan_hp_updates(_feed(BOSS, 99_969_473))[0] == {BOSS: 99_969_473}


def test_the_engine_reads_bargotts_hp_from_the_pull():
    engine = MeterEngine()
    engine.consume(_spawn(BOSS, BARGOTT, BARGOTT_HP), 1_000, STREAM)
    assert engine.spawn_info[BOSS]["reportedMaxHp"] == BARGOTT_HP
    engine.consume(_feed(BOSS, 199_000_000), 2_000, STREAM)                      # 81 %: until 0.2.514 never seen
    assert engine.live_hp[BOSS] == 199_000_000
    assert {(t["current"], t["timestamp_ms"]) for t in engine.telemetry if t["kind"] == "hp"} == {(199_000_000, 2_000)}
    engine.consume(_feed(BOSS, 4_043_461_478), 3_000, STREAM)                    # more than the boss has: not its HP
    assert engine.live_hp[BOSS] == 199_000_000 and not [t for t in engine.telemetry if t["kind"] == "hp"]
    # an enemy whose spawn record the meter missed is read from 100 million down, as before
    engine.consume(_feed(BOSS + 1, 150_000_000), 4_000, STREAM)
    assert BOSS + 1 not in engine.live_hp


def test_a_wipe_with_bargott_above_100_million_starts_a_new_attempt():
    """The boss back at full after the party's damage paused is a wipe's reset: a new attempt, a new fight."""
    s, engine = _in_the_raid()
    t = 1_795_663_463_000
    engine.consume(_spawn(BOSS, BARGOTT, BARGOTT_HP), t, STREAM)
    s.observe(engine, [], timestamp_ms=t)
    engine.consume(_feed(BOSS, 180_000_000), t + 60_000, STREAM)                 # the party has the boss at 73 %
    s.observe(engine, [_hit(ME, BOSS, t + 60_000)], timestamp_ms=t + 60_000)
    assert (s.epoch, BOSS) in s._major_below
    splits = s.manual_split
    engine.consume(_feed(BOSS, BARGOTT_HP), t + 100_000, STREAM)                 # wiped: back at full 40 s on
    s.observe(engine, [], timestamp_ms=t + 100_000)
    assert s.reset_splits == 1 and s.manual_split == splits + 1


def test_the_party_wiping_on_bargott_above_100_million_ends_the_attempt():
    """The whole party dead while the boss has HP left is a wipe, and the attempt ends there. That takes a reading of the
    boss's HP, and until 0.2.514 none came above 100 million: one recording ran three attempts at Bargott, 22 minutes,
    into one fight, each wiped above it."""
    s, engine = _in_the_raid()
    engine.names = {ME: "Me", MATE: "Mate"}
    engine.roster = {"Me": {}, "Mate": {}}
    engine.roster_complete = True
    t = 1_795_658_958_000
    engine.consume(_spawn(BOSS, BARGOTT, BARGOTT_HP), t, STREAM)
    s.observe(engine, [], timestamp_ms=t)
    engine.consume(_feed(BOSS, 205_000_000), t + 30_000, STREAM)
    s.observe(engine, [_hit(ME, BOSS, t + 30_000), _hit(MATE, BOSS, t + 30_000)], timestamp_ms=t + 30_000)
    engine.telemetry = [{"entity": ME, "kind": "death", "timestamp_ms": t + 41_000},
                        {"entity": MATE, "kind": "death", "timestamp_ms": t + 42_000}]
    s.observe(engine, [], timestamp_ms=t + 42_000)
    engine.telemetry = []
    s.observe(engine, [], timestamp_ms=t + 45_000)
    assert s.wipe_splits == 1


def test_terminator_bargott_ends_the_raid_and_the_surveillance_device_does_not():
    assert dungeon_final_bosses(RAID) == frozenset({BARGOTT})
    s, engine = _in_the_raid()
    first = s.run
    engine.spawn_info = {9001: {"mobCode": SURVEILLANCE_DEVICE}, 9002: {"mobCode": BLATT}, 9003: {"mobCode": BARGOTT}}
    for entity, start in ((9001, 100_000), (9002, 400_000), (9003, 900_000)):
        engine.telemetry = [{"entity": entity, "kind": "hp", "current": 500, "max": 1000, "timestamp_ms": start + 1_000},
                            {"entity": entity, "kind": "death", "timestamp_ms": start + 80_000}]
        s.observe(engine, [_hit(ME, entity, start), _hit(ME, entity, start + 79_000)], timestamp_ms=start + 80_000)
        run = s.runs[s.run]
        if entity != 9003:
            assert not run.get("complete") and run.get("end_reason") != "configured_final_boss_death", entity
    assert run.get("end_reason") == "configured_final_boss_death"
    assert run.get("recorded_final_boss") == BARGOTT and run.get("complete") is True
    assert s.run == first and list(s.runs) == [first]                           # one run, from the first boss to the last
