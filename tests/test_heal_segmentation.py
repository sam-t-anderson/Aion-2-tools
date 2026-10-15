"""Targeted heals are healing, not damage -- and a live boss fight is one encounter.

Diagnosed from a real recording (a Transcendence run, Talisra of the Void / Ruthilis of Pain)
that uploaded as 200 + 67 "encounters" of the same boss. Every split lined up with a cleric or
chanter heal (Radiant Recovery, Radiant Benediction, Recuperation, Healing Light) landing on an
allied NPC the game registers as a player ("Midas"). The decoder recorded any effect on another
entity as damage, so each heal read as a party member damaging a non-party player: PvP. A
PvE<->PvP switch is a segment boundary, so every cast cut the fight in two and back again --
the overlay reset on each cast and showed only whoever had acted in that sliver -- and the
death bookkeeping then stretched every sliver that touched the boss to the kill, counting one
kill dozens of times over.
"""
import threading
from types import SimpleNamespace


from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.lookup import heal_skill_families, is_heal_skill
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.a2parser.parser import parse_damage_packet
from aion2calc.meter.session import CombatSession, Record

BOSS_CODE, BOSS2_CODE = 2300910, 2300908         # catalog bosses (Ferocious Horn Den)
HEAL, NUKE = 17120000, 15210000                   # Radiant Recovery / a sorcerer attack


# ------------------------------------------------------------------ decoder
def test_heal_skill_families_come_from_the_bundled_class_data():
    assert len(heal_skill_families()) >= 9
    for code in (17100000, 17120000, 17800000, 18120000, 18170000):   # cleric/chanter heals
        assert is_heal_skill(code), code
    assert is_heal_skill(17120010)                                      # a rank/spec variant is its family
    for code in (11340000, 15210000, 12730000, 2011101, 1800000):       # lifesteal, nuke, buff, potion, NPC attack
        assert not is_heal_skill(code), code
    assert is_heal_skill("nope") is False


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _effect_frame(actor, target, skill, amount):
    """One \\x04\\x38 skill-effect record (layout 5: a 12-byte modifier block), as
    parse_damage_packet reads it: target, switch, unused, actor, skill, uid, damage type,
    modifiers, then the two values (the second is the amount)."""
    return (_varint(1) + b"\x04\x38" + _varint(target) + _varint(0x05) + _varint(0) + _varint(actor)
            + skill.to_bytes(4, "little") + b"\x00" + _varint(0) + b"\x00" * 12 + _varint(1) + _varint(amount))


def test_decoder_records_a_targeted_heal_as_healing_of_that_target():
    out = parse_damage_packet(_effect_frame(1001, 2002, HEAL, 3318), timestamp_ms=5, known_players={1001, 2002})
    assert len(out) == 1 and isinstance(out[0], HealEvent)
    assert (out[0].actor_id, out[0].target_id, out[0].amount, out[0].skill_code) == (1001, 2002, 3318, HEAL)
    # The same record with an attack skill is still damage to the target.
    out = parse_damage_packet(_effect_frame(1001, 2002, NUKE, 3318), timestamp_ms=5, known_players={1001})
    assert len(out) == 1 and isinstance(out[0], DamageEvent)
    assert (out[0].actor_id, out[0].target_id, out[0].damage) == (1001, 2002, 3318)


# ------------------------------------------------------------------ session
ME, ALLY, BOSS, BOSS2, TRASH = 101, 503, 9001, 9002, 7777


def _session():
    s = CombatSession()
    s.pvp = False
    s.gap_seconds = 120
    s.identities[0] = {"names": {ME: "Me", ALLY: "Midas"}, "spawns": {BOSS: {"mobCode": BOSS_CODE}},
                       "jobs": {}, "local_id": ME, "owners": {}, "roster": {}, "observed_players": {ME, ALLY},
                       "player_ids": {ME, ALLY}}    # Midas: a non-party, player-registered ally
    s.runs = {1: {"instance_id": None, "start_observed": True}}
    s.run = 1
    return s


def _rec(event, seq, split=0):
    return Record(0, event, frozenset(), ME, split, 1, seq)


def _hit(target, t, dmg=500, skill=NUKE):
    return DamageEvent(actor_id=ME, target_id=target, skill_code=skill, damage=dmg, timestamp_ms=t)


def test_a_heal_on_a_non_party_ally_is_never_pvp_and_never_splits_the_boss_fight():
    s = _session()
    s.records = [_rec(_hit(BOSS, 1000), 1), _rec(_hit(BOSS, 2000), 2),
                 # the pre-fix decode of a heal on the ally: a "damage" record with a heal skill
                 _rec(DamageEvent(actor_id=ME, target_id=ALLY, skill_code=HEAL, damage=1338, timestamp_ms=3000), 3),
                 # and the fixed decode of one
                 _rec(HealEvent(ME, HEAL, 1338, 3500, False, ALLY), 4),
                 _rec(_hit(BOSS, 5000), 5)]
    allowed = s._allowances("self")
    assert s._pvp_damage(s.records[2], allowed(s.records[2])) is False   # healing is not a hostile act
    groups = s.groups("self")
    assert len(groups) == 1 and groups[0]["pvp"] is False               # one encounter, still PvE
    assert len(groups[0]["records"]) == 5                               # the heals ride along in it


def test_a_stray_pvp_looking_hit_mid_boss_fight_joins_the_fight_but_splits_once_the_boss_is_dead():
    s = _session()
    s.records = [_rec(_hit(BOSS, 1000), 1), _rec(_hit(BOSS, 2000), 2),
                 _rec(_hit(ALLY, 4000, 20892), 3),        # e.g. a pet / AoE clipping the player-registered ally
                 _rec(_hit(BOSS, 5000), 4),
                 _rec(_hit(ALLY, 60000), 5)]              # a real player fight after the boss is dead
    s.telemetry.append({"kind": "death", "entity": BOSS, "timestamp_ms": 50000, "epoch": 0})
    groups = s.groups("self")
    assert [g["pvp"] for g in groups] == [False, True]    # the boss fight stayed whole; PvP after the kill is its own
    assert len(groups[0]["records"]) == 4 and groups[0]["end"] == 50000   # ... and it ends at the kill
    assert len(groups[1]["records"]) == 1


def test_a_death_closes_only_the_latest_attempt_that_was_fighting_the_enemy():
    s = _session()
    s.records = [_rec(_hit(BOSS, 1000), 1, split=0), _rec(_hit(BOSS, 2000), 2, split=0),     # attempt 1 (wiped/leashed)
                 _rec(_hit(BOSS, 10000), 3, split=1), _rec(_hit(BOSS, 11000), 4, split=1)]   # attempt 2 -> kill
    s.telemetry.append({"kind": "death", "entity": BOSS, "timestamp_ms": 12000, "epoch": 0})
    first, second = s.groups("self")
    assert first["end"] == 2000                           # not stretched to the kill (it used to be: both "killed")
    assert second["end"] == 12000


def _engine():
    engine = MeterEngine()
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = 100_000
    engine.local_player_id = 4062
    engine.names = {4062: "Me", 4063: "Mate4063"}
    engine.known_players = {4062, 4063}
    engine.roster = {name: {} for name in engine.names.values()}
    engine.spawn_info = {BOSS: {"mobCode": BOSS_CODE}, BOSS2: {"mobCode": BOSS2_CODE}}
    return engine


def _party_hit(target, t):
    return DamageEvent(actor_id=4062, target_id=target, skill_code=NUKE, damage=500, timestamp_ms=t)


def test_overlay_starts_fresh_on_the_first_combat_after_the_boss_is_defeated():
    engine = _engine()
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    s.observe(engine, [_party_hit(BOSS, 105_000)], timestamp_ms=105_000)      # boss pull
    assert s._live_boss_reset_ms == 105_000
    engine.telemetry = [{"kind": "death", "entity": BOSS, "timestamp_ms": 110_000}]
    s.observe(engine, [], timestamp_ms=110_000)                                # ... killed
    engine.telemetry = []
    assert s._pull_ended_ms == 110_000
    assert s._live_boss_reset_ms == 105_000           # the final numbers stay up through the lull
    s.observe(engine, [_party_hit(TRASH, 120_000)], timestamp_ms=120_000)     # next combat (trash)
    assert s._live_boss_reset_ms == 120_000           # starts the overlay fresh
    assert s._pull_ended_ms is None
    s.observe(engine, [_party_hit(BOSS2, 130_000)], timestamp_ms=130_000)     # next boss resets again
    assert s._live_boss_reset_ms == 130_000


def test_overlay_does_not_move_the_reset_point_after_a_kill_when_boss_reset_is_off():
    engine = _engine()
    s = CombatSession()
    s.pvp = False
    s.reset_on_boss_start = False
    s.observe(engine, [], timestamp_ms=101_000)
    s.observe(engine, [_party_hit(BOSS, 105_000)], timestamp_ms=105_000)
    engine.telemetry = [{"kind": "death", "entity": BOSS, "timestamp_ms": 110_000}]
    s.observe(engine, [], timestamp_ms=110_000)
    engine.telemetry = []
    s.observe(engine, [_party_hit(TRASH, 120_000)], timestamp_ms=120_000)
    # The engage still records its point (the toggle is applied when the view is built), but
    # the post-kill combat does not move it.
    assert s._live_boss_reset_ms == 105_000 and s._pull_ended_ms is None


def test_a_wipe_releases_the_engaged_boss_so_the_re_pull_resets_the_overlay():
    s = CombatSession()
    s.pvp = False
    s.identities[0] = {"names": {4062: "Me", 4063: "Mate4063"}, "spawns": {}, "jobs": {}, "local_id": 4062,
                       "owners": {}, "roster": {}, "observed_players": {4062, 4063}}
    s._engaged_major = {(0, BOSS)}
    s._major_below = {(0, BOSS)}
    s._boss_attempt = {"context": (0, 0, 1), "roster": frozenset({"me", "mate4063"}), "members": {4062, 4063},
                       "dead": {4062, 4063}, "boss_hp": {BOSS: 500}, "bosses": {BOSS},
                       "last_activity": 1000, "last_death": 2000}
    engine = SimpleNamespace(roster_complete=True, roster={"Me": {}, "Mate4063": {}}, telemetry=[])
    s._check_boss_wipe(5000, engine)
    assert s.wipe_splits == 1
    assert s._engaged_major == set() and s._major_below == set()   # the re-pull is a fresh major
    assert s._pull_ended_ms == 5000
    # ... and continuation parts carry the new state.
    s._major_history = {(0, BOSS)}
    cont = s.continuation()
    assert cont._pull_ended_ms == 5000 and cont._major_history == {(0, BOSS)}


# ------------------------------------------------------------------ runner
def test_the_final_part_is_closed_once_capture_has_stopped():
    from aion2calc.app.meter_runner import Runner
    engine = _engine()
    s = CombatSession()
    s.pvp = False
    s.observe(engine, [], timestamp_ms=101_000)
    s.observe(engine, [_party_hit(BOSS, 105_000)], timestamp_ms=105_000)
    r = Runner.__new__(Runner)
    r.lock = threading.Lock()
    r.session, r.packet_engine, r.metadata, r.scope, r.capture_metadata = s, engine, {}, "party", None
    r.archive_id, r.archive_part, r.archive_part_token, r.archive_previous = "a" * 32, 1, "t" * 32, None
    r._metadata = lambda doc, **kw: doc
    r.running = True
    assert r.to_a2log()["meta"]["archive"]["closed"] is False     # live: an open part
    r.running = False
    assert r.to_a2log()["meta"]["archive"]["closed"] is True      # stopped: the finished final part
