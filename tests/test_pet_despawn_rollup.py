"""Live view: a de-spawned summon rolls into its owner even with pets shown separately.

A Spiritmaster cycles many short-lived spirits. With "combine pets with owner" OFF, each
spirit is its own row; the de-spawned ones used to pile up as tiny dead rows that fall past
the overlay's row cap, taking their damage out of view. The live summary now folds a summon
that has gone quiet (idle >= PET_DESPAWN_IDLE_MS) into its owner, while the owner's still-
active spirits keep their own rows. (Fix lives in CombatSession._summary, the packet path
the overlay uses — not the legacy Meter.)"""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession


def _hit(actor, target, t, dmg=1000):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=15210000, damage=dmg, timestamp_ms=t)


def _engine():
    e = MeterEngine()
    e.map_id = e.dungeon_id = 600002
    e.last_zone_reset_ms = None
    e.local_player_id = 5001
    e.names = {5001: "Spirited", 6001: "Earth Spirit", 6002: "Water Spirit"}
    e.known_players = {5001}
    e.roster = {"Spirited": {}}
    e.summon_owners = {6001: 5001, 6002: 5001}    # both spirits belong to the spiritmaster
    return e


def test_despawned_pet_folds_into_owner_while_active_pet_stays_separate():
    s = CombatSession(); s.pvp = False
    e = _engine()
    # The owner and both spirits open on the boss…
    s.observe(e, [_hit(5001, 9001, 1000), _hit(6001, 9001, 1000), _hit(6002, 9001, 1000)], timestamp_ms=1000)
    # …then 19s on, only the owner and the Water Spirit are still hitting; the Earth Spirit
    # has gone silent (de-spawned, idle well past the 8s threshold).
    s.observe(e, [_hit(5001, 9001, 20000), _hit(6002, 9001, 20000)], timestamp_ms=20000)

    rows = {p["name"]: p for p in s.snapshot(scope="party", combine_pets=False)["players"]}
    assert "Earth Spirit" not in rows                      # de-spawned spirit no longer its own row
    assert rows["Spirited"].get("includes_pets") is True   # its damage rolled onto the owner
    assert rows["Spirited"]["damage"] == 3000              # owner 2000 + de-spawned Earth Spirit 1000
    assert "Water Spirit" in rows and rows["Water Spirit"].get("owner")  # the active spirit stays separate
    assert rows["Water Spirit"]["damage"] == 2000

    # With combine ON, every spirit (active or not) folds into the owner, as before.
    combined = {p["name"]: p for p in s.snapshot(scope="party", combine_pets=True)["players"]}
    assert "Earth Spirit" not in combined and "Water Spirit" not in combined
    assert combined["Spirited"]["damage"] == 5000          # everything on the owner


def test_active_pets_stay_separate_when_none_have_despawned():
    # Guard against over-folding: while a spirit is still actively dealing damage, pets-OFF
    # keeps it as its own row (nothing idle past the threshold yet).
    s = CombatSession(); s.pvp = False
    e = _engine()
    s.observe(e, [_hit(5001, 9001, 1000), _hit(6002, 9001, 1000)], timestamp_ms=1000)
    s.observe(e, [_hit(5001, 9001, 4000), _hit(6002, 9001, 4000)], timestamp_ms=4000)  # 3s gap < 8s
    rows = {p["name"]: p for p in s.snapshot(scope="party", combine_pets=False)["players"]}
    assert "Water Spirit" in rows and rows["Water Spirit"].get("owner")   # still active → own row
    assert not rows["Spirited"].get("includes_pets")                      # owner did not absorb it
