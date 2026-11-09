"""A boss's adds and clones (0.2.394): an NPC spawned near a catalog boss being fought, or striking the party or
casting at it during the fight, is the boss's add or clone, and its casts and positions are kept and exported like
the boss's, in the boss's fights, so the log server can measure their areas and the replay can show where they are.

In the two Ferocious Horn Den captures of 19 and 20 October the decoder read every cast and position of Nuakum's
summons (mob 2920604, spawned some two hundred times a run and casting 1802012 at once, 2920601 and Condensed
Energy 2920605: 708 casts and 1,105 positions in the 20 October capture), but the session kept casts only for
catalog bosses and positions only for bosses and enemies the party had hit: the fight exported none of them."""
from aion2calc.combat import a2log
from aion2calc.combat.actions import boss_casts
from aion2calc.meter.a2parser.models import DamageEvent
from aion2calc.meter.session import CombatSession

from test_combat_actions import ALLY, BOSS, ME, OVERHEAD_SLAM, _engine

CLONE, ENERGY, TRASH, SPIRIT = 61001, 61002, 61003, 61004
CLONE_CODE, ENERGY_CODE, TRASH_CODE, SPIRIT_CODE = 2920604, 2920605, 2920150, 2920999
LEAP, PULSE, SLASH = 1802012, 1802151, 1800000


def _engine_with_adds():
    engine = _engine()
    engine.spawn_info.update({CLONE: {"mobCode": CLONE_CODE}, ENERGY: {"mobCode": ENERGY_CODE},
                              TRASH: {"mobCode": TRASH_CODE}, SPIRIT: {"mobCode": SPIRIT_CODE}})
    return engine


def _observe(session, engine, t, events=(), actions=(), positions=()):
    engine.actions = [{**a, "timestamp_ms": t} for a in actions]
    engine.positions = [{**p, "timestamp_ms": t} for p in positions]
    session.observe(engine, list(events), timestamp_ms=t)
    engine.actions, engine.positions = [], []


def _hit(actor, target, t, skill=OVERHEAD_SLAM):
    return DamageEvent(actor_id=actor, target_id=target, skill_code=skill, damage=1000, timestamp_ms=t)


def _at(entity, x, y, src):
    return {"entity": entity, "x": float(x), "y": float(y), "z": 10.0, "src": src}


def _cast(actor, skill, target=None, pos=(500.0, 600.0, 10.0), facing=90.0):
    return {"kind": "cast", "actor": actor, "skill": skill, "seq": 1, "at_target": target is not None,
            "target": target, "npc": True, "position": pos, "facing": facing}


def _fight():
    """A boss fight: before it a trash NPC spawns and casts; during it the boss's clone spawns at once with its
    first cast, moves and strikes the party, Condensed Energy (no spawn seen) casts at a player, and a player's
    summon spawns and casts."""
    engine, s = _engine_with_adds(), CombatSession()
    s.pvp = False
    engine.summon_owners = {SPIRIT: ALLY}
    _observe(s, engine, 101_000)
    # before the boss is engaged: trash spawning and casting is no add
    _observe(s, engine, 103_000, actions=[_cast(TRASH, SLASH)], positions=[_at(TRASH, 50, 50, "spawn")])
    _observe(s, engine, 110_000, events=[_hit(ME, BOSS, 110_000)])
    # the clone spawns with its first cast in the same read; the spawn marks it before the cast is kept
    _observe(s, engine, 112_000, events=[_hit(ALLY, BOSS, 112_000)],
             actions=[_cast(CLONE, LEAP, pos=(900.0, 100.0, 10.0), facing=180.0)],
             positions=[_at(CLONE, 900, 100, "spawn")])
    _observe(s, engine, 113_000, actions=[_cast(CLONE, LEAP, pos=(950.0, 120.0, 10.0))],
             positions=[_at(CLONE, 950, 120, "targeted")])
    _observe(s, engine, 114_000, events=[_hit(CLONE, ME, 114_000, SLASH)])
    # Condensed Energy: no spawn record, its cast aimed at a player marks it
    _observe(s, engine, 115_000, actions=[_cast(ENERGY, PULSE, target=ALLY)], positions=[_at(ENERGY, 300, 300, "applied")])
    _observe(s, engine, 116_000, actions=[_cast(ENERGY, PULSE + 1)], positions=[_at(ENERGY, 310, 300, "targeted")])
    # a party member's summon spawned mid-fight is no add
    _observe(s, engine, 117_000, events=[_hit(ME, BOSS, 117_000)],
             actions=[_cast(SPIRIT, 16990002)], positions=[_at(SPIRIT, 200, 200, "spawn")])
    return engine, s


def test_a_boss_fight_exports_its_adds_casts_and_positions():
    _, s = _fight()
    doc = s.to_a2log()
    seg = doc["segments"][-1]
    ents = {e["id"]: e for e in seg["entities"]}
    by_code = {e.get("mob_code"): e["id"] for e in ents.values()}
    clone, energy = by_code[CLONE_CODE], by_code[ENERGY_CODE]
    assert ents[clone]["kind"] == "enemy" and not ents[clone]["is_boss"]
    casts = [(c["source"], c["skill_id"]) for c in seg["npc_casts"]]
    assert casts == [(clone, LEAP), (clone, LEAP), (energy, PULSE), (energy, PULSE + 1)]
    first = seg["npc_casts"][0]
    assert first["pos"] == [900.0, 100.0, 10.0] and first["facing"] == 180.0     # where the clone aimed, its facing
    assert seg["npc_casts"][2]["target"] in {p["id"] for p in doc["players"]}
    moves = [(r["entity"], r["src"], r["x"]) for r in seg["movement"] if r["entity"] in (clone, energy)]
    assert moves == [(clone, "spawn", 900.0), (clone, "targeted", 950.0), (energy, "applied", 300.0), (energy, "targeted", 310.0)]
    # the trash before the fight and the player's summon are not adds: no casts, and the trash no positions
    assert TRASH_CODE not in by_code
    assert all(ents.get(c["source"], {}).get("mob_code") not in (TRASH_CODE, SPIRIT_CODE) for c in seg["npc_casts"])
    assert (s.epoch, SPIRIT) not in s._boss_adds and (s.epoch, TRASH) not in s._boss_adds
    # the validator, the server's included (any listed entity may cast), keeps them all
    clean = a2log.validate(doc)["segments"][-1]
    assert clean["npc_casts"] == seg["npc_casts"]
    assert [r for r in clean["movement"] if r["entity"] in (clone, energy)] == [r for r in seg["movement"] if r["entity"] in (clone, energy)]


def test_an_npc_striking_the_party_mid_boss_becomes_an_add_from_then_on():
    engine, s = _engine_with_adds(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, BOSS, 110_000)])
    _observe(s, engine, 111_000, actions=[_cast(TRASH, SLASH)])                      # not yet: no strike, no spawn seen
    _observe(s, engine, 112_000, events=[_hit(TRASH, ALLY, 112_000, SLASH)])
    _observe(s, engine, 113_000, actions=[_cast(TRASH, SLASH, pos=(1.0, 2.0, 3.0))], positions=[_at(TRASH, 1, 2, "move")])
    _observe(s, engine, 114_000, events=[_hit(ME, BOSS, 114_000)])                  # the fight goes on
    seg = s.to_a2log()["segments"][-1]
    trash = next(e["id"] for e in seg["entities"] if e.get("mob_code") == TRASH_CODE)
    assert [(c["source"], c["t"]) for c in seg["npc_casts"]] == [(trash, 3.0)]
    assert [(r["entity"], r["src"]) for r in seg["movement"] if r["entity"] == trash] == [(trash, "move")]


def test_an_npc_spawning_far_from_the_boss_is_no_add():
    """A clone spawns near the boss it serves (up to 70 m from Nuakum in October); an NPC coming into view 120 m away
    while the boss is fought is not taken for one."""
    engine, s = _engine_with_adds(), CombatSession()
    s.pvp = False
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, BOSS, 110_000)], positions=[_at(BOSS, 0, 0, "targeted")])
    _observe(s, engine, 111_000, positions=[_at(TRASH, 12_000, 0, "spawn"), _at(CLONE, 4200, 5600, "spawn")])
    assert (s.epoch, CLONE) in s._boss_adds and (s.epoch, TRASH) not in s._boss_adds


def test_a_fight_without_the_boss_exports_no_adds_casts():
    """An add of a boss fight that turns up in a later fight without the boss: that fight's enemies are the ones the
    party fought, and the add's casts stay out of it."""
    engine, s = _fight()
    _observe(s, engine, 300_000, events=[_hit(ME, TRASH, 300_000)], actions=[_cast(CLONE, LEAP)])
    _observe(s, engine, 302_000, events=[_hit(CLONE, ME, 302_000, SLASH), _hit(ME, TRASH, 302_000)])
    segments = s.to_a2log()["segments"]
    boss, later = segments[-2], segments[-1]
    assert any(e.get("is_boss") for e in boss["entities"]) and not any(e.get("is_boss") for e in later["entities"])
    assert any(e.get("mob_code") == CLONE_CODE for e in later["entities"])        # it struck the party: listed
    assert later["npc_casts"] == [] and len(boss["npc_casts"]) == 4


def test_the_oldest_adds_are_forgotten_first_and_their_kept_casts_stay(monkeypatch):
    monkeypatch.setattr(CombatSession, "MAX_BOSS_ADDS", 4)
    engine, s = _engine_with_adds(), CombatSession()
    s.pvp = False
    engine.spawn_info.update({70_000 + i: {"mobCode": CLONE_CODE} for i in range(6)})
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, BOSS, 110_000)])
    _observe(s, engine, 111_000, actions=[_cast(70_000, LEAP)], positions=[_at(70_000, 10, 10, "spawn")])
    _observe(s, engine, 112_000, positions=[_at(70_000 + i, 10, 10, "spawn") for i in range(1, 6)])
    _observe(s, engine, 113_000, events=[_hit(ME, BOSS, 113_000)])
    assert (s.epoch, 70_000) not in s._boss_adds and len(s._boss_adds) == 4         # the first one forgotten
    assert [c["skill_id"] for c in s.to_a2log()["segments"][-1]["npc_casts"]] == [LEAP]   # its kept cast is not


def test_no_boss_no_adds():
    """Trash fought without a boss keeps its old treatment: no casts, positions only once the party hits it."""
    engine, s = _engine_with_adds(), CombatSession()
    s.pvp = False
    engine.spawn_info.pop(BOSS)
    _observe(s, engine, 101_000)
    _observe(s, engine, 110_000, events=[_hit(ME, TRASH, 110_000)],
             actions=[_cast(CLONE, LEAP)], positions=[_at(CLONE, 900, 100, "spawn")])
    _observe(s, engine, 111_000, events=[_hit(CLONE, ME, 111_000, SLASH)], actions=[_cast(CLONE, LEAP)])
    assert not s._boss_adds
    seg = s.to_a2log()["segments"][-1]
    assert seg["npc_casts"] == []


def test_a_fight_keeps_its_boss_casts_first_when_the_adds_overflow(monkeypatch):
    monkeypatch.setitem(a2log.LIMITS, "npc_casts", 3)
    entities = {"b": {"is_boss": True}, "a": {}, "q": {}}
    rows = [{"t": 1.0, "source": "q"}, {"t": 2.0, "source": "a"}, {"t": 3.0, "source": "b"}, {"t": 4.0, "source": "q"},
            {"t": 5.0, "source": "a"}]
    events = [{"kind": "damage", "source": "a", "target": "p"}]
    kept = CombatSession._cap_npc_casts(rows, entities, events)
    assert [(r["t"], r["source"]) for r in kept] == [(2.0, "a"), (3.0, "b"), (5.0, "a")]   # the boss, then the add that struck
    assert CombatSession._cap_npc_casts(rows[:3], entities, events) == rows[:3]


def test_the_boss_cast_list_counts_the_adds_by_kind_and_keeps_its_order_for_the_bosses():
    """Hundreds of clones casting would fill the Boss casts list: their skills follow the bosses', one row per kind of
    add with how many cast it, and the casts in order stay the bosses' own."""
    entities = [{"id": "b", "is_boss": True}, {"id": "c1", "mob_code": CLONE_CODE}, {"id": "c2", "mob_code": CLONE_CODE},
                {"id": "e", "mob_code": ENERGY_CODE}]
    casts = [{"t": 1.0, "source": "c1", "skill_id": LEAP}, {"t": 2.0, "source": "b", "skill_id": SLASH, "target": "p1"},
             {"t": 3.0, "source": "c2", "skill_id": LEAP, "target": "p1"}, {"t": 4.0, "source": "e", "skill_id": PULSE},
             {"t": 5.0, "source": "b", "skill_id": SLASH, "target": "p2"}]
    result = boss_casts({"npc_casts": casts, "entities": entities})
    assert [(k["source"], k["skill_id"], k["casts"], k.get("casters")) for k in result["skills"]] == [
        ("b", SLASH, 2, None), ("c1", LEAP, 2, 2), ("e", PULSE, 1, 1)]
    assert result["skills"][1]["add"] and result["skills"][1]["targets"] == [{"target": "p1", "casts": 1}]
    assert [(c["t"], c["source"]) for c in result["timeline"]] == [(2.0, "b"), (5.0, "b")] and result["add_casts"] == 3
    # a log that lists no entities, or one from before 0.2.394 (every caster a boss), is listed as before
    assert [c["t"] for c in boss_casts({"npc_casts": casts})["timeline"]] == [1.0, 2.0, 3.0, 4.0, 5.0]
