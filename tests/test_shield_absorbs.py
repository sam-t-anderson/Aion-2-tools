"""Shields and heals over time are credited to their caster, as what they took (0.2.399).

A heal over time or a shield holds an HP pool, and the game reports it in ``05 38`` records with the effect's instance
number (docs/open-investigations.md). Its application (effect type ``09``) names the caster as its actor and carries
the whole pool or the shield's size; it restores no HP. Each update (``0b``) carries what is left and, after it, what
the update took: the HP a tick restored, or the damage the shield absorbed of a hit. A tick names its caster; an
absorb names the attacker whose hit it took. The decoder read the amount, what was left, as the heal, and the actor
as the healer, so in a PvP recording a Templar's own Guarding Seal and Nezekan's Shield were the Ranger's heals on
them, each worth what the shield still held, and in the 31 October recording a Light of Regeneration worth 5,946
counted 47,616. Now an update is the heal of what it took, credited to the caster its application named. An absorb
whose application the capture did not see names no caster, and a stored log's heals between the two sides of a PvP
fight, recorded so by an older meter, count for no one and are counted. Synthetic records only."""
from aion2calc.combat import a2log
from aion2calc.combat.healing import summarize as healing_summary, unattributed_heals
from aion2calc.combat.unnamed import relabel
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.a2parser.parser import PoolCasters, decode_stream, parse_dot_packet
from aion2calc.meter.session import CombatSession
from test_arena_matches import FOE, ME, STREAM, _entered

GUARDING_SEAL, NEZEKANS_SHIELD, LIGHT_OF_REGENERATION = 12750001, 12320040, 17090120
TEMPEST_SHOT, SPIRITS_BENEDICTION = 14340000, 16190000
CLERIC, RANGER, TEMPLAR = 7001, 12981, 4423
APPLIED, UPDATE = 0x09, 0x0B


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _frame(inner):
    return _varint(len(inner) + 4) + inner


def _effect(target, kind, actor, instance, skill, amount, took=None, index=11):
    """One ``05 38`` record as the captures carry them: target, the effect type, actor, the effect's instance, its
    effect number (the skill times 100 plus the effect's index), the amount, for an update what it took, and the
    skill that applied it."""
    return _frame(b"\x05\x38" + _varint(target) + bytes([kind]) + _varint(actor) + _varint(instance)
                  + (skill * 100 + index).to_bytes(4, "little") + _varint(amount)
                  + (_varint(took) if took is not None else b"") + skill.to_bytes(4, "little"))


def _hit(actor, target, skill, amount):
    """One ``04 38`` hit (layout 5): target, switch, unused, actor, skill, uid, damage type, modifiers, two values."""
    return _frame(b"\x04\x38" + _varint(target) + _varint(0x05) + _varint(0) + _varint(actor) + skill.to_bytes(4, "little")
                  + b"\x00" + _varint(1) + b"\x00" * 12 + _varint(1) + _varint(amount))


def _read(data, pools, t=5):
    return list(decode_stream(data, t, set(), pools=pools))


# ------------------------------------------------------------------ decoder
def test_a_shield_absorb_is_the_casters_heal_of_what_it_took_not_the_attackers_of_what_was_left():
    """The reported case: the Templar's Guarding Seal (8,707) takes 2,366 of the Ranger's hit, and the record names the
    Ranger as its actor with 6,341 left. It is the Templar's heal, of 2,366."""
    pools = PoolCasters()
    assert _read(_effect(TEMPLAR, APPLIED, TEMPLAR, 81, GUARDING_SEAL, 8707), pools) == []    # restores no HP
    [heal] = _read(_effect(TEMPLAR, UPDATE, RANGER, 81, GUARDING_SEAL, 6341, took=2366), pools, t=6)
    assert heal == HealEvent(TEMPLAR, GUARDING_SEAL, 2366, 6, is_hot=False, target_id=TEMPLAR, absorb=True)
    # The next hit's record names the Ranger again: still the Templar's
    [heal] = _read(_effect(TEMPLAR, UPDATE, RANGER, 81, GUARDING_SEAL, 5517, took=824), pools, t=7)
    assert (heal.actor_id, heal.amount, heal.absorb) == (TEMPLAR, 824, True)


def test_a_heal_over_time_tick_is_the_hp_it_restored():
    """A Light of Regeneration of 5,946 on a party member restores 396 a tick, and each tick names its caster."""
    pools = PoolCasters()
    _read(_effect(TEMPLAR, APPLIED, CLERIC, 188, LIGHT_OF_REGENERATION, 5946), pools)
    ticks = [_read(_effect(TEMPLAR, UPDATE, CLERIC, 188, LIGHT_OF_REGENERATION, left, took=396), pools)[0]
             for left in (5550, 5154, 4758)]
    assert [(h.actor_id, h.target_id, h.amount, h.is_hot, h.absorb) for h in ticks] == [(CLERIC, TEMPLAR, 396, True, False)] * 3


def test_an_update_without_its_application_names_its_caster_only_as_a_tick_does():
    """With no application seen (cast out of view, or before the capture began): an update of a skill that absorbs,
    or one whose actor struck the target in the same read, is an absorb with no caster in any record. Any other
    names its caster, as a tick does, and so does an update naming its target itself."""
    [heal] = _read(_effect(TEMPLAR, UPDATE, RANGER, 90, NEZEKANS_SHIELD, 7826, took=687), PoolCasters())
    assert (heal.actor_id, heal.amount, heal.absorb) == (None, 687, True)                          # Nezekan's Shield absorbs
    unknown = 19990001                                                                             # a skill nothing names
    [hit, heal] = _read(_effect(TEMPLAR, UPDATE, RANGER, 91, unknown, 900, took=100) + _hit(RANGER, TEMPLAR, TEMPEST_SHOT, 100),
                        PoolCasters())                                                             # the absorb after its hit
    assert isinstance(hit, DamageEvent) and (heal.actor_id, heal.absorb) == (None, True)          # the hit came with it
    [heal] = _read(_effect(TEMPLAR, UPDATE, CLERIC, 92, SPIRITS_BENEDICTION, 2979, took=331), PoolCasters())
    assert (heal.actor_id, heal.amount, heal.is_hot) == (CLERIC, 331, True)
    [heal] = _read(_effect(CLERIC, UPDATE, CLERIC, 93, unknown, 600, took=300), PoolCasters())
    assert heal.actor_id == CLERIC


def test_a_skill_seen_absorbing_is_an_absorb_when_its_application_is_missed_later():
    """A shield the archived captures did not hold is learned from its first absorb of a known caster."""
    pools, shield = PoolCasters(), 19980001
    _read(_effect(TEMPLAR, APPLIED, TEMPLAR, 81, shield, 3000), pools)
    [heal] = _read(_effect(TEMPLAR, UPDATE, RANGER, 81, shield, 2900, took=100), pools)
    assert (heal.actor_id, heal.absorb) == (TEMPLAR, True)                                         # learned: it absorbs
    [heal] = _read(_effect(CLERIC, UPDATE, RANGER, 82, shield, 2800, took=200), pools)
    assert (heal.actor_id, heal.absorb) == (None, True)


def test_another_healers_tick_is_theirs():
    """In a crowd of healers (the Abyss, 21 October), one Chanter's Recuperation ticks under the instance another
    applied, whose own application the capture missed. Recuperation's updates have named their casters, so it is a
    heal over time: the tick is that Chanter's, not the first one's, and no absorb."""
    pools, recuperation, other = PoolCasters(), 18120010, 6401
    _read(_effect(TEMPLAR, APPLIED, CLERIC, 9349, recuperation, 1500), pools)
    [tick] = _read(_effect(TEMPLAR, UPDATE, CLERIC, 9349, recuperation, 1250, took=250), pools)
    assert (tick.actor_id, tick.is_hot) == (CLERIC, True)                                      # it ticks
    [tick] = _read(_effect(TEMPLAR, UPDATE, other, 9349, recuperation, 1000, took=250), pools)
    assert (tick.actor_id, tick.amount, tick.is_hot, tick.absorb) == (other, 250, True, False)
    [tick] = _read(_effect(RANGER, UPDATE, other, 77, recuperation, 900, took=300), pools)      # no application at all
    assert (tick.actor_id, tick.absorb) == (other, False) and 18120000 not in pools.absorbing


def test_a_skill_with_a_shield_and_a_heal_over_time_tells_them_apart_by_effect():
    """Steel Barrier holds a shield (its effect 11), whose updates name the attackers, and a pool that ticks (its
    effect 14), whose updates name the caster: each update is read by its own effect."""
    pools, barrier, sorcerer = PoolCasters(), 15160020, 12334
    _read(_effect(sorcerer, APPLIED, sorcerer, 110, barrier, 4142, index=11)
          + _effect(sorcerer, APPLIED, sorcerer, 110, barrier, 2608, index=14), pools)
    [tick] = _read(_effect(sorcerer, UPDATE, sorcerer, 110, barrier, 2522, took=86, index=14), pools)
    [absorb] = _read(_effect(sorcerer, UPDATE, RANGER, 110, barrier, 3330, took=812, index=11), pools)
    assert (tick.actor_id, tick.is_hot, tick.absorb) == (sorcerer, True, False)
    assert (absorb.actor_id, absorb.amount, absorb.absorb) == (sorcerer, 812, True)                 # learned: it absorbs
    # A later Steel Barrier the capture saw no application of: its shield's absorb is nobody's, its tick the caster's
    [absorb] = _read(_effect(sorcerer, UPDATE, RANGER, 120, barrier, 3000, took=500, index=11), pools)
    [tick] = _read(_effect(sorcerer, UPDATE, sorcerer, 120, barrier, 2400, took=97, index=14), pools)
    assert (absorb.actor_id, absorb.absorb) == (None, True) and (tick.actor_id, tick.absorb) == (sorcerer, False)


def test_an_application_is_kept_across_reads_and_parse_dot_packet_takes_the_same_rules():
    pools = PoolCasters()
    assert parse_dot_packet(_effect(TEMPLAR, APPLIED, TEMPLAR, 81, GUARDING_SEAL, 8707), 5, pools) is None
    heal = parse_dot_packet(_effect(TEMPLAR, UPDATE, RANGER, 81, GUARDING_SEAL, 6341, took=2366), 6, pools)
    assert (heal.actor_id, heal.amount) == (TEMPLAR, 2366)
    pools.clear()                                                                                  # a zone load
    heal = parse_dot_packet(_effect(TEMPLAR, UPDATE, RANGER, 81, GUARDING_SEAL, 5517, took=824), 7, pools)
    assert (heal.actor_id, heal.absorb) == (None, True)
    # An application of another skill under the same instance number names no caster for this one
    pools.applied(TEMPLAR, 81, TEMPLAR, NEZEKANS_SHIELD)
    assert pools.caster(TEMPLAR, 81, GUARDING_SEAL) is None and pools.caster(TEMPLAR, 81, NEZEKANS_SHIELD) == TEMPLAR


# ------------------------------------------------------------------ the meter and its log
def test_an_arena_templars_shields_are_their_healing_and_hps():
    """In an arena match the Templar's Guarding Seal absorbs the opponent's hits: the healing is the Templar's, in the
    live meter, the overlay's HPS and the saved log, where each absorb is marked as one."""
    engine = _entered()
    s = CombatSession()
    s.begin_capture()
    s.observe(engine, [], timestamp_ms=101_500)
    t = 110_000
    s.observe(engine, engine.consume(_effect(ME, APPLIED, ME, 81, GUARDING_SEAL, 8707), t, STREAM), timestamp_ms=t)
    for i, (left, took) in enumerate(((6341, 2366), (5517, 824), (4070, 1447))):
        at = t + 1000 * (i + 1)
        events = engine.consume(_effect(ME, UPDATE, FOE, 81, GUARDING_SEAL, left, took=took) + _hit(FOE, ME, TEMPEST_SHOT, took), at, STREAM)
        assert [type(e) for e in events] == [DamageEvent, HealEvent]                    # the absorb after the hit it took
        s.observe(engine, events + [DamageEvent(ME, FOE, 12010000, 1500, at + 100)], timestamp_ms=at + 200)
    assert engine.healers[ME].healing == 2366 + 824 + 1447 and FOE not in engine.healers
    row = next(p for p in s.snapshot("party")["players"] if p["id"] == str(ME))
    assert row["healing"] == 4637
    [fight] = [seg for seg in s.to_a2log("party")["segments"] if seg["events"]]
    heals = [e for e in fight["events"] if e["kind"] == "heal"]
    me = next(p["id"] for p in s.to_a2log("party")["players"] if p["name"] == "Testme")
    assert [(e["source"], e["target"], e["amount"], e.get("absorb")) for e in heals] == [(me, me, 2366, True), (me, me, 824, True), (me, me, 1447, True)]


def test_an_absorb_with_no_caster_is_nobodys_healing():
    engine = _entered()
    events = engine.consume(_effect(ME, UPDATE, FOE, 95, NEZEKANS_SHIELD, 7826, took=687), 110_000, STREAM)
    assert [(e.actor_id, e.amount, e.absorb) for e in events] == [(None, 687, True)]
    assert engine.healers == {}
    s = CombatSession()
    s.begin_capture()
    s.observe(engine, [DamageEvent(FOE, ME, TEMPEST_SHOT, 687, 109_900), *events], timestamp_ms=110_100)
    [fight] = [seg for seg in s.to_a2log("party")["segments"] if seg["events"]]
    [heal] = [e for e in fight["events"] if e["kind"] == "heal"]
    assert "source" not in heal and heal["absorb"] is True and heal["amount"] == 687


def test_healing_lists_an_absorb_as_a_shield_whatever_its_skill_says():
    """Guarding Seal's text names no shield ("Grants a Guarding Seal that blocks damage"): its absorb is still no
    instant heal to measure against the HP feed."""
    me = "p:1:1"
    segment = {"events": [{"kind": "heal", "t": 1.0, "source": me, "target": me, "skill_id": GUARDING_SEAL,
                           "skill": "Guarding Seal", "amount": 2366.0, "absorb": True},
                          {"kind": "heal", "t": 2.0, "source": me, "target": me, "skill_id": 12350340, "skill": "Warding Strike", "amount": 500.0}],
               "health": [{"t": 0.0, "entity": me, "current": 9000.0, "max": 10000.0}, {"t": 2.0, "entity": me, "current": 9500.0, "max": 10000.0}]}
    [healer] = healing_summary(segment, {me})["healers"]
    assert (healer["shield"], healer["effective"], healer["amount"]) == (2366, 500, 2866)


# ------------------------------------------------------------------ stored logs
def _stored(encounter_type="pvp_arena"):
    """A fight as a meter before 0.2.399 saved it: the Templar's shields as the Ranger's heals on them, of what was
    left, the Ranger's own shield as the Templar's heal on the Ranger, and the heals that are what they say."""
    me, foe, pet, stranger = "p:2102:1", "2:12981", "2:18043", "2:5005"
    heal = lambda t, source, target, skill, name, amount: {"kind": "heal", "t": t, "source": source, "target": target,  # noqa: E731
                                                           "skill_id": skill, "skill": name, "amount": amount}
    events = [heal(1.0, me, me, GUARDING_SEAL, "Guarding Seal", 8707.0),                  # the application, by its caster
              heal(1.3, foe, me, GUARDING_SEAL, "Guarding Seal", 6341.0),
              heal(1.4, foe, me, GUARDING_SEAL, "Guarding Seal", 5517.0),
              heal(2.0, pet, me, NEZEKANS_SHIELD, "Nezekan's Shield", 7826.0),               # a hit of the Ranger's summon
              heal(3.0, me, foe, 14790000, "Revitalization Contract", 1500.0),               # the Ranger's shield, under my name
              heal(4.0, foe, foe, 14790000, "Revitalization Contract", 1500.0),              # the Ranger's own
              heal(5.0, stranger, me, 17100000, "Healing Light", 2000.0),                    # a stranger of my faction
              {"kind": "damage", "t": 1.3, "source": foe, "target": me, "skill_id": TEMPEST_SHOT, "skill": "Tempest Shot", "amount": 2366.0}]
    return {"format": "a2log", "version": 1, "meta": {"title": "Arena"},
            "players": [{"id": me, "name": "Testtemplar", "class": "templar"}],
            "segments": [{"duration": 10.0, "encounter_type": encounter_type, "hits": [], "events": events,
                          "entities": [{"id": foe, "name": "Testranger", "kind": "enemy", "is_player": True},
                                       {"id": pet, "name": "Spirit", "kind": "pet", "owner": foe},
                                       {"id": stranger, "name": "Testcleric", "kind": "player", "is_player": True}]}]}


def test_a_stored_pvp_logs_heals_between_the_sides_count_for_no_one_and_are_counted():
    doc = relabel(_stored())
    segment = doc["segments"][0]
    kept = [(e["source"], e["target"], e["amount"]) for e in segment["events"] if e["kind"] == "heal"]
    assert kept == [("p:2102:1", "p:2102:1", 8707.0), ("2:12981", "2:12981", 1500.0), ("2:5005", "p:2102:1", 2000.0)]
    assert segment["unattributed_heals"] == {"records": 4, "amount": 21184.0,
                                             "skills": {"Guarding Seal": 2, "Nezekan's Shield": 1, "Revitalization Contract": 1}}
    assert relabel(doc)["segments"][0]["unattributed_heals"]["records"] == 4                     # nothing left to take out
    clean = a2log.validate(doc)                                                                    # kept with the log
    assert clean["segments"][0]["unattributed_heals"] == segment["unattributed_heals"]


def test_a_pve_fight_keeps_its_heals():
    doc = _stored("pve_open_world")
    assert unattributed_heals(doc["segments"][0], {"p:2102:1"}) is None
    assert sum(e["kind"] == "heal" for e in relabel(doc)["segments"][0]["events"]) == 7
