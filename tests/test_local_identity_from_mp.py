"""The local player from its MP record. The self record (``33 36``) comes only with a zone load, so a
meter started inside a zone (the app opened, or restarted to update, after the load) named the party
from the roster and spawn records but not the recording player until the next load: the overlay
listed everyone but its recorder, whose hits went uncredited. The game sends the MP record (``00 8d``,
``01 01 01``) for the local player only, every few seconds while its MP changes, so it names the
local actor meanwhile; a self record still replaces it."""
from aion2calc.meter.a2parser.engine import MeterEngine
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
