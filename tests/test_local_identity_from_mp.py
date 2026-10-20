"""The local player from its MP record. The self record (``33 36``) comes only with a zone load, so a
meter started inside a zone (the app opened, or restarted to update, after the load) named the party
from the roster and spawn records but not the recording player until the next load: the overlay
listed everyone but its recorder, whose hits went uncredited. The game sends the MP record (``00 8d``,
``01 01 01``) for the local player only, every few seconds while its MP changes, so it names the
local actor meanwhile; a self record still replaces it."""
from aion2calc.meter.a2parser.engine import CAST_GUESS_LEAD, CAST_GUESS_MIN, MeterEngine
from aion2calc.meter.session import CombatSession

from test_combat_actions import ALLY, BOSS, ME, OVERHEAD_SLAM, _frame, _hit, _observe, _u32, _varint

STREAM = "1.2.3.4:13328->192.168.1.9:57424"
STALE, PET = 3111, 4100


def _mp(entity, current=2807):
    return _frame(b"\x00\x8d", _varint(entity) + b"\x01\x01\x01" + _u32(current) + b"\x00" * 4)


def _self_record(entity, name):
    raw = name.encode()
    return _frame(b"\x33\x36", _varint(entity) + b"\x00" * 4 + b"\x01" + bytes([len(raw)]) + raw + b"\x00\x00" + _u32(0) + b"\x00" * 8)


def _engine():
    engine = MeterEngine()
    engine.set_server_port(13328)
    return engine


def test_a_meter_started_inside_a_zone_knows_its_player_from_the_mp_record():
    engine = _engine()
    engine.consume(_mp(ME), 1_000, STREAM)
    assert engine.local_player_id == ME and engine.local_identity_from_mp and engine.local_identity_from_game
    assert ME in engine.known_players
    engine.consume(_self_record(ME, "Recorder"), 2_000, STREAM)       # the next zone load's self record
    assert engine.local_player_id == ME and not engine.local_identity_from_mp
    assert engine.names[ME] == "Recorder"


def test_a_self_record_for_another_actor_still_wins():
    engine = _engine()
    engine.consume(_mp(ME), 1_000, STREAM)
    engine.consume(_self_record(ALLY, "Recorder"), 2_000, STREAM)
    assert engine.local_player_id == ALLY and not engine.local_identity_from_mp


def test_a_local_id_that_no_longer_fits_gives_way_to_two_mp_records_in_a_row():
    # adopted from a capture stopped in another zone, or a zone load the capture missed
    engine = _engine()
    engine.local_player_id, engine.local_identity_from_game = STALE, True
    engine.consume(_mp(ME), 1_000, STREAM)
    assert engine.local_player_id == STALE                          # one record is not enough
    engine.consume(_mp(STALE), 1_500, STREAM)                       # the bound actor's own MP
    engine.consume(_mp(ME), 2_000, STREAM)
    assert engine.local_player_id == STALE
    engine.consume(_mp(ME, 2700), 3_000, STREAM)
    assert engine.local_player_id == ME and engine.local_identity_from_mp


def test_a_summons_or_an_npcs_record_is_not_the_player():
    engine = _engine()
    engine.summons.add(PET)
    engine.spawn_info[BOSS] = {"mobCode": 2300615}
    for entity in (PET, BOSS):
        engine.consume(_mp(entity), 1_000, STREAM)
    assert engine.local_player_id is None


def test_a_zone_load_forgets_it_and_carries_over_on_a_restart():
    engine = _engine()
    engine.consume(_mp(ME), 1_000, STREAM)
    successor = MeterEngine()
    successor.adopt_identity(engine)
    assert successor.local_player_id == ME and successor.local_identity_from_mp
    engine._reset_zone(5_000)
    assert engine.local_player_id is None and not engine.local_identity_from_mp


def test_the_party_view_includes_the_recorder_it_names():
    engine = _engine()
    engine.map_id = engine.dungeon_id = 600053
    engine.last_zone_reset_ms = 100_000
    engine.names = {ALLY: "Ally"}                                   # named by a spawn record; the recorder is not
    engine.known_players = {ALLY}
    engine.roster = {"Ally": {}, "Recorder": {}}
    engine.roster_complete = True
    engine.spawn_info = {BOSS: {"mobCode": 2300615}}
    engine.consume(_mp(ME), 100_500, STREAM)
    s = CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, OVERHEAD_SLAM, 110_000, 5000), _hit(ALLY, OVERHEAD_SLAM, 110_100, 3000)])
    snap = s.snapshot(scope="party")
    players = {p["id"]: p for p in snap["players"]}
    assert set(players) == {str(ME), str(ALLY)} and players[str(ME)]["damage"] == 5000
    assert snap["identity_status"]["self_identified"] and snap["identity_status"]["local_id"] == ME


def test_the_overlay_calls_an_unnamed_recorder_you():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")
    assert 'unnamedSelf(p)?"You":p.name' in js and "localId = snap.identity_status" in js
    assert "your name comes with the next zone load" in js


TEMPLAR_SKILL, MOUNT_SKILL = 12010000, 1229000          # a class skill (Templar) and a non-class one


def _cast_end(actor, skill=TEMPLAR_SKILL):
    return _frame(b"\x06\x38", _varint(actor) + _u32(skill) + b"\x01\x00")


def test_the_first_class_skill_cast_end_names_the_player_before_its_mp_record():
    # the game sends a cast's end for the local player and NPCs only, never another player's, so the
    # first skill press names the recorder (the left-click idea, from the game's own records)
    engine = _engine()
    engine.consume(_cast_end(ME), 1_000, STREAM)
    assert engine.local_player_id == ME and engine.local_identity_from_mp and ME in engine.known_players
    engine.consume(_self_record(ME, "Recorder"), 2_000, STREAM)
    assert engine.local_player_id == ME and not engine.local_identity_from_mp


def test_npcs_summons_and_non_class_skills_name_no_one():
    engine = _engine()
    engine.summons.add(PET)
    engine.spawn_info[BOSS] = {"mobCode": 2300615}
    engine.consume(_cast_end(PET), 1_000, STREAM)
    engine.consume(_cast_end(BOSS), 1_100, STREAM)
    engine.consume(_cast_end(ME, MOUNT_SKILL), 1_200, STREAM)        # a mount or gathering cast
    assert engine.local_player_id is None


SORC_SKILL = 15010000                                     # a Sorcerer class skill that is not an auto attack


def _casts(engine, actor, skill, start, n):
    for k in range(n):
        engine.consume(_cast_end(actor, skill), start + 100 * k, STREAM)


def test_class_skills_guess_only_after_four_casts_and_one_mp_record_replaces_the_guess():
    # a pet summoned before the meter started has no owner link and casts its owner's class skills
    engine = _engine()
    _casts(engine, PET, SORC_SKILL, 1_000, CAST_GUESS_MIN - 1)
    assert engine.local_player_id is None
    engine.consume(_cast_end(PET, SORC_SKILL), 1_900, STREAM)
    assert engine.local_player_id == PET and engine.local_identity_from_mp
    engine.consume(_mp(ME), 2_000, STREAM)                              # the game's MP record: exact
    assert engine.local_player_id == ME


def test_an_auto_attack_takes_over_a_guess_from_other_skills_and_a_lead_does_too():
    engine = _engine()
    _casts(engine, PET, SORC_SKILL, 1_000, CAST_GUESS_MIN)
    engine.consume(_cast_end(ME), 2_000, STREAM)                        # the Templar's auto attack
    assert engine.local_player_id == ME
    other = _engine()
    _casts(other, PET, SORC_SKILL, 1_000, CAST_GUESS_MIN)
    _casts(other, ME, 12090000, 2_000, CAST_GUESS_MIN + CAST_GUESS_LEAD - 1)
    assert other.local_player_id == PET                                 # level: no lead yet
    other.consume(_cast_end(ME, 12090000), 3_000, STREAM)
    assert other.local_player_id == ME                                  # three casts ahead


def test_a_self_record_or_mp_identity_is_not_moved_by_casts():
    engine = _engine()
    engine.consume(_mp(ME), 1_000, STREAM)
    _casts(engine, ALLY, 12010000, 1_100, 10)
    assert engine.local_player_id == ME


def test_casts_with_no_input_go_on_the_not_my_player_list_while_the_game_is_in_focus():
    engine = _engine()
    now = __import__("time").time()
    engine.input_activity = lambda: (now - 60, False)                 # nothing pressed for a minute
    engine.consume(_cast_end(ALLY, 12010000), int(now * 1000), STREAM)
    assert engine.local_player_id is None and ALLY in engine.not_local
    engine.input_activity = lambda: (now, False)                      # a key was just pressed
    engine.consume(_cast_end(ALLY, 12010000), int(now * 1000) + 100, STREAM)
    assert engine.local_player_id is None                             # listed: never guessed
    engine.consume(_cast_end(ME, 12010000), int(now * 1000) + 200, STREAM)
    assert engine.local_player_id == ME


def test_unknown_input_held_buttons_and_pets_never_list_an_actor():
    engine = _engine()
    now = __import__("time").time()
    engine.input_activity = lambda: (None, False)                     # not Windows, or the game not in focus
    engine.consume(_cast_end(ALLY, SORC_SKILL), int(now * 1000), STREAM)
    engine.input_activity = lambda: (now - 60, True)                  # an auto attack held on the mouse
    engine.consume(_cast_end(ALLY, SORC_SKILL), int(now * 1000) + 100, STREAM)
    engine.summons.add(PET)
    engine.input_activity = lambda: (now - 60, False)
    engine.consume(_cast_end(PET, SORC_SKILL), int(now * 1000) + 200, STREAM)
    assert not engine.not_local


def test_the_idle_rule_stands_down_when_its_list_held_the_player():
    # a gamepad's presses do not reach GetLastInputInfo: the player itself could be listed
    engine = _engine()
    now = __import__("time").time()
    engine.input_activity = lambda: (now - 60, False)
    engine.consume(_cast_end(ME, 12010000), int(now * 1000), STREAM)
    assert ME in engine.not_local
    engine.consume(_mp(ME), int(now * 1000) + 500, STREAM)
    assert engine.local_player_id == ME and not engine.not_local and engine._idle_rule_off


def test_a_wrong_guess_hands_its_hits_to_the_corrected_player():
    # the recorder's hits before the correction are credited to it once its MP record moves the identity
    engine = _engine()
    engine.map_id = engine.dungeon_id = 600053
    engine.spawn_info = {BOSS: {"mobCode": 2300615}}
    _casts(engine, PET, SORC_SKILL, 100_100, CAST_GUESS_MIN)           # an unlinked pet's casts: a wrong guess
    assert engine.local_player_id == PET
    s = CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000, events=[_hit(ME, OVERHEAD_SLAM, 101_000, 5000)])
    engine.consume(_mp(ME), 102_000, STREAM)
    engine.consume(_mp(ME, 2700), 103_000, STREAM)
    _observe(s, engine, 104_000, events=[_hit(ME, OVERHEAD_SLAM, 104_000, 3000)])
    snap = s.snapshot(scope="party")
    players = {p["id"]: p for p in snap["players"]}
    assert snap["identity_status"]["local_id"] == ME
    assert players[str(ME)]["damage"] == 8000
