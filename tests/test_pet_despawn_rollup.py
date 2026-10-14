"""Live view: a de-spawned summon rolls into its owner even with pets shown separately.

A Spiritmaster cycles many short-lived spirits. With "combine pets with owner" OFF, each
spirit is its own row; the de-spawned ones used to pile up as tiny dead rows that fall past
the overlay's row cap, taking their damage out of view. The live summary now folds a summon
that has gone quiet (idle >= PET_DESPAWN_IDLE_MS) into its owner, while the owner's still-
active spirits keep their own rows. (Fix lives in CombatSession._summary, the packet path
the overlay uses — not the legacy Meter.)"""
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession, BASIC_SPIRIT_NAMES


def _hit(actor, target, t, dmg=1000, skill=15210000):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=skill, damage=dmg, timestamp_ms=t)


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


def _engine_spirits(names, owners):
    e = MeterEngine()
    e.map_id = e.dungeon_id = 600002
    e.last_zone_reset_ms = None
    e.local_player_id = 5001
    e.names = dict(names)
    e.known_players = {5001}
    e.roster = {"Spirited": {}}
    e.summon_owners = dict(owners)
    return e


def test_new_basic_spirit_folds_the_replaced_one_immediately():
    # The Spiritmaster has only one basic spirit out at a time. When a new basic spirit is
    # summoned (Earth replacing Water here), the replaced one is gone and its damage must roll
    # into the owner at once — even though it dealt damage well inside the 8s idle window, so the
    # idle rule alone would not have folded it. Only the current (newest) basic spirit keeps a row.
    s = CombatSession(); s.pvp = False
    e = _engine_spirits({5001: "Spirited", 6001: "Water Spirit", 6002: "Earth Spirit"},
                        {6001: 5001, 6002: 5001})
    # Water Spirit is the basic spirit out for the first two seconds…
    s.observe(e, [_hit(5001, 9001, 1000), _hit(6001, 9001, 1000)], timestamp_ms=1000)
    s.observe(e, [_hit(5001, 9001, 2000), _hit(6001, 9001, 2000)], timestamp_ms=2000)
    # …then the player summons Earth Spirit, which replaces it. Water last acted at t=2000 — only
    # 1.5s before "now" (3500), comfortably inside the 8s idle window.
    s.observe(e, [_hit(5001, 9001, 3000), _hit(6002, 9001, 3000)], timestamp_ms=3000)
    s.observe(e, [_hit(5001, 9001, 3500), _hit(6002, 9001, 3500)], timestamp_ms=3500)

    rows = {p["name"]: p for p in s.snapshot(scope="party", combine_pets=False)["players"]}
    assert "Water Spirit" not in rows                       # replaced basic spirit folded in at once
    assert rows["Spirited"].get("includes_pets") is True
    assert rows["Spirited"]["damage"] == 6000               # owner 4000 + the replaced Water's 2000
    assert "Earth Spirit" in rows and rows["Earth Spirit"].get("owner")  # the current basic spirit stays
    assert rows["Earth Spirit"]["damage"] == 2000


def test_ancient_spirit_stays_out_alongside_the_current_basic_spirit():
    # Ancient Spirit (a stigma summon) is the one spirit that can be out at the same time as a
    # basic spirit, so the one-at-a-time replacement must never fold it. A basic spirit replaced
    # by a newer one still folds; the current basic spirit and the Ancient Spirit each keep a row.
    s = CombatSession(); s.pvp = False
    e = _engine_spirits({5001: "Spirited", 6001: "Water Spirit", 6002: "Earth Spirit",
                         6003: "Ancient Spirit"},
                        {6001: 5001, 6002: 5001, 6003: 5001})
    s.observe(e, [_hit(5001, 9001, 1000), _hit(6001, 9001, 1000)], timestamp_ms=1000)
    # Earth replaces Water, and the Ancient Spirit is summoned alongside it.
    s.observe(e, [_hit(5001, 9001, 3000), _hit(6002, 9001, 3000), _hit(6003, 9001, 3000)], timestamp_ms=3000)
    s.observe(e, [_hit(5001, 9001, 3500), _hit(6002, 9001, 3500), _hit(6003, 9001, 3500)], timestamp_ms=3500)

    rows = {p["name"]: p for p in s.snapshot(scope="party", combine_pets=False)["players"]}
    assert "Water Spirit" not in rows                        # replaced basic spirit folded into owner
    assert rows["Spirited"].get("includes_pets") is True
    assert "Earth Spirit" in rows and rows["Earth Spirit"].get("owner")   # current basic spirit
    assert "Ancient Spirit" in rows and rows["Ancient Spirit"].get("owner")  # coexists → keeps its row
    assert rows["Ancient Spirit"]["damage"] == 2000


def test_basic_spirit_replacement_classifies_by_skill_on_a_non_english_client():
    # On a non-English client the summoned entity's name is localized and won't match the
    # English spirit names, so classification must key on the (numeric, locale-independent)
    # skill IDs the spirit attacks with: Water's Discharge Chill (16110001) and Earth's Tackle
    # (16130001) mark these as basic spirits even though their names are not the English ones.
    WATER_SKILL, EARTH_SKILL = 16110001, 16130001
    s = CombatSession(); s.pvp = False
    e = _engine_spirits({5001: "Spirited", 6001: "물의 정령", 6002: "땅의 정령"},
                        {6001: 5001, 6002: 5001})
    assert "물의 정령" not in BASIC_SPIRIT_NAMES   # the name path cannot classify these
    s.observe(e, [_hit(5001, 9001, 1000), _hit(6001, 9001, 1000, skill=WATER_SKILL)], timestamp_ms=1000)
    s.observe(e, [_hit(5001, 9001, 2000), _hit(6001, 9001, 2000, skill=WATER_SKILL)], timestamp_ms=2000)
    # The earth spirit replaces the water spirit; water last acted 1.5s ago (inside the idle window),
    # so only the skill-based replacement rule can fold it in.
    s.observe(e, [_hit(5001, 9001, 3000), _hit(6002, 9001, 3000, skill=EARTH_SKILL)], timestamp_ms=3000)
    s.observe(e, [_hit(5001, 9001, 3500), _hit(6002, 9001, 3500, skill=EARTH_SKILL)], timestamp_ms=3500)

    rows = {p["name"]: p for p in s.snapshot(scope="party", combine_pets=False)["players"]}
    assert "물의 정령" not in rows                 # replaced basic spirit folded into owner
    assert rows["Spirited"].get("includes_pets") is True
    assert rows["Spirited"]["damage"] == 6000                      # owner 4000 + the replaced water's 2000
    assert "땅의 정령" in rows and rows["땅의 정령"].get("owner")  # current basic spirit stays
