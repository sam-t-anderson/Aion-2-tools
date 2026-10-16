"""Identity after a zone reset without a new self record (a same-map Kibelisk teleport reassigns
actor ids; the game does not always resend the local-player record): the engine keeps the
game-verified local name across the reset and re-binds the local player to the one actor that
carries it again. Exactly one match, never a guess; a real self record from the game still wins."""
from aion2calc.meter.a2parser.engine import MeterEngine


def _identified(engine, actor=4062, name="Spirited"):
    engine.names[actor] = name
    engine.known_players.add(actor)
    engine.local_player_id = actor
    engine.local_identity_from_game = True


def test_name_rebinds_the_local_player_after_a_reset_without_a_self_record():
    engine = MeterEngine()
    _identified(engine)
    engine._reset_zone(1_000)
    assert engine.local_player_id is None and engine._local_name_hint == "Spirited"
    engine.names[7493] = "Spirited"                 # the player's new actor id, named by a party/roster record
    engine.names[9001] = "Somebody"
    engine._bind_hinted_name()
    assert engine.local_player_id == 7493 and engine.local_identity_rebound is True
    assert 7493 in engine.known_players and engine.local_identity_from_game is False   # inferred, not game-verified


def test_two_actors_with_the_name_never_bind_and_pets_are_ignored():
    engine = MeterEngine()
    _identified(engine)
    engine._reset_zone(1_000)
    engine.names[7493] = "Spirited"
    engine.names[7494] = "Spirited"
    engine._bind_hinted_name()
    assert engine.local_player_id is None            # ambiguous: wait for the game
    del engine.names[7494]
    engine.summons.add(7493)                         # a summon named after its owner is not the owner
    engine._bind_hinted_name()
    assert engine.local_player_id is None


def test_a_game_self_record_wins_and_the_hint_follows_it():
    engine = MeterEngine()
    _identified(engine)
    engine._reset_zone(1_000)
    engine.names[7493] = "Spirited"
    engine._bind_hinted_name()
    assert engine.local_player_id == 7493
    # The game then sends its own self record for a different id: it replaces the inferred one.
    engine.names[9925] = "Spirited"
    engine.local_player_id, engine.local_identity_from_game = 9925, True
    engine._bind_hinted_name()                       # nothing to do while an id is bound
    assert engine.local_player_id == 9925
    engine._reset_zone(2_000)
    assert engine._local_name_hint == "Spirited" and engine.local_identity_rebound is False


def test_no_hint_without_a_game_verified_identity_and_hint_carries_to_the_next_engine():
    engine = MeterEngine()
    engine.names[4062] = "Spirited"
    engine.local_player_id = 4062                   # bound by the user-typed name, not by the game
    engine._reset_zone(1_000)
    assert engine._local_name_hint == ""
    verified = MeterEngine()
    _identified(verified)
    verified._reset_zone(1_000)
    successor = MeterEngine()
    successor.adopt_identity(verified)               # a continuation engine keeps the hint
    assert successor._local_name_hint == "Spirited"
