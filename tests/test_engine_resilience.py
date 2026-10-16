"""The engine survives what the Fire Temple recordings showed: a spawn-less final boss and a
capture restart that forgets everyone.

- Both final-boss fights recorded the boss only as ``Enemy #id`` (its spawn packet, carrying the
  mob code, was lost), so the kill was never recognised. A catalog boss's max HP is remembered
  when seen; an enemy without a mob code whose HP is within 1% of a remembered final boss of the
  current dungeon is taken for that boss.
- Restarting capture inside a dungeon made a fresh engine that knew nobody until the next zone
  load. The new engine adopts the previous one's identities.
"""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.lookup import dungeon_final_bosses, npc_info

FIRE_TEMPLE = 600022
KROMEDE = 2300371


def test_catalog_knows_fire_temples_final_boss():
    assert KROMEDE in dungeon_final_bosses(FIRE_TEMPLE) and npc_info(KROMEDE).get("isBoss")


def test_a_boss_seen_once_is_recognised_by_its_hp_when_its_spawn_is_lost():
    engine = MeterEngine()
    engine.dungeon_id = FIRE_TEMPLE
    engine.spawn_info[23816] = {"mobCode": KROMEDE}
    engine._identify_boss_by_hp({}, {23816: 15_504_000})            # first run: spawn decoded, max HP learned
    assert engine.boss_hp_seen == {KROMEDE: 15_504_000.0}
    # Second run: the boss's spawn packet is lost; only its HP packets arrive.
    engine._identify_boss_by_hp({38988: 15_501_104}, {})
    assert engine.spawn_info[38988]["mobCode"] == KROMEDE and engine.spawn_info[38988]["inferred"] == "hp_signature"
    assert 38988 in engine.known_entities
    # A trash mob, or an enemy far from the signature, is never promoted.
    engine._identify_boss_by_hp({40001: 120_000, 40002: 14_000_000}, {})
    assert "mobCode" not in engine.spawn_info.get(40001, {}) and "mobCode" not in engine.spawn_info.get(40002, {})
    # Outside this dungeon the signature does not apply.
    other = MeterEngine(); other.dungeon_id = 600002; other.boss_hp_seen[KROMEDE] = 15_504_000.0
    other._identify_boss_by_hp({38988: 15_501_104}, {})
    assert 38988 not in other.spawn_info


def test_the_map_id_stands_in_when_the_dungeon_id_is_not_known_yet():
    engine = MeterEngine()
    engine.map_id = FIRE_TEMPLE                   # the roster packet (which carries dungeon_id) was lost
    engine.boss_hp_seen[KROMEDE] = 15_504_000.0
    engine._identify_boss_by_hp({7: 15_500_000}, {})
    assert engine.spawn_info[7]["mobCode"] == KROMEDE


def test_a_restarted_engine_adopts_the_previous_identities():
    old = MeterEngine()
    old.names = {5001: "Me", 5002: "Ally"}; old.jobs = {5001: "gladiator"}
    old.known_players = {5001, 5002}; old.roster = {"Me": {}, "Ally": {}}; old.roster_complete = True
    old.local_player_id = 5001; old.local_identity_from_game = True; old.local_character_name = "Me"
    old.map_id = old.dungeon_id = FIRE_TEMPLE
    old.spawn_info = {9001: {"mobCode": KROMEDE}}; old.boss_hp_seen = {KROMEDE: 15_504_000.0}
    new = MeterEngine()
    new.adopt_identity(old)
    assert new.local_player_id == 5001 and new.local_identity_from_game and new.local_character_name == "Me"
    assert new.names == old.names and new.known_players == {5001, 5002} and new.roster_complete
    assert new.dungeon_id == FIRE_TEMPLE and new.spawn_info[9001]["mobCode"] == KROMEDE
    assert new.boss_hp_seen == {KROMEDE: 15_504_000.0}
    assert new.names is not old.names                                    # its own state from here on
