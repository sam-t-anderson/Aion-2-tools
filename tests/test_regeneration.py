"""A hit the target's Regeneration answered counts whole, and what Regeneration gave back is the target's heal (0.2.406).

After a layout-6 hit's modifiers comes a varint. With modifier bit 0x20 (named Smite before 0.2.408) it is the HP the
target's Regeneration gave back of the hit, and without the bit 0. In the 14 archived captures it is a fifth of what
got past the target's shields in every hit it can be checked on: ``value // 5`` in all 473 hits no shield took part
of, ``(value - what the shields took) // 5`` in 49 of 50 that one did (the 50th shares its shield's absorbs with
another hit), and 0 where the hit was under 5 HP or the shields took it whole. The bit is the target's, never a
monster's; the hit's value is whole, where a block or Endurance halves it; and the target's HP drops by the value less
what the shields took and the fifth. The client's text says Regeneration "Recovers a portion of Damage as HP". 0.2.402
to 0.2.405 took the fifth off the hit's damage. From 128 on the varint takes two bytes, which the decoder read as one
before 0.2.402 (docs/open-investigations.md). Synthetic records only, with the fields the captures carry."""
from aion2calc.combat.healing import summarize as healing_summary
from aion2calc.meter.a2parser.lookup import REGENERATION_SKILL, skill_name
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent, SpecialDamage
from aion2calc.meter.a2parser.parser import decode_stream, parse_damage_packet
from aion2calc.meter.session import CombatSession
from test_arena_matches import _entered, STREAM
from test_shield_absorbs import _frame, _varint

RANGER, TEMPLAR = 12981, 4423
TEMPEST_SHOT = 14340000
PROTECTION_CIRCLE = 1_873_000_211             # a shield's effect number: the skill times 100 plus its index
LAYOUT_6, MULTI_HITS, SHIELDS, REGENERATION = 0x06, 0x20, 0x40, 0x20
BACK, FRONT = 1, 2


def _record(value, *, regenerated=0, power=10_830, mods=0, direction=0, hits=(), shields=(), damage_type=2):
    """One ``04 38`` hit of layout 6, the Ranger's on the Templar: target, switch, an unused varint, actor, skill (u32),
    uid, damage type; then the modifiers (u8), what Regeneration gave back (a varint), the direction (u8), the hit's own
    effect number (u32) and a u32; the power scalar and the hit's value (its multi-hits included); with switch bit 0x20
    its multi-hits (a count and each hit); with switch bit 0x40 the shields that took part of it (a count and each one's
    effect number); and the record's end."""
    mods |= REGENERATION if regenerated else 0
    switch = LAYOUT_6 | (MULTI_HITS if hits else 0) | (SHIELDS if shields else 0)
    body = (_varint(TEMPLAR) + _varint(switch) + _varint(0) + _varint(RANGER) + TEMPEST_SHOT.to_bytes(4, "little")
            + b"\x00" + _varint(damage_type) + bytes([mods]) + _varint(regenerated) + bytes([direction])
            + (TEMPEST_SHOT * 100 + 11).to_bytes(4, "little") + (1).to_bytes(4, "little")
            + _varint(power) + _varint(value))
    if hits:
        body += _varint(len(hits)) + b"".join(_varint(h) for h in hits)
    if shields:
        body += bytes([len(shields)]) + b"".join(s.to_bytes(4, "little") for s in shields)
    return b"\x04\x38" + body + b"\x01\x00"


def _hit(value, **fields):
    return _frame(_record(value, **fields))


def _events(frame):
    return parse_damage_packet(frame, timestamp_ms=5)


def _event(frame) -> DamageEvent:
    """The hit's damage event; any other event of the record is Regeneration's heal."""
    events = _events(frame)
    [event] = [e for e in events if isinstance(e, DamageEvent)]
    assert (event.actor_id, event.target_id) == (RANGER, TEMPLAR)
    assert all(isinstance(e, HealEvent) and e.skill_code == REGENERATION_SKILL for e in events if e is not event)
    return event


def _regeneration(frame) -> HealEvent | None:
    heals = [e for e in _events(frame) if isinstance(e, HealEvent)]
    assert len(heals) <= 1
    return heals[0] if heals else None


def test_the_hit_counts_whole_and_the_target_heals_itself_of_the_fifth():
    """The arena recording's case: a hit of 1,480 on the Templar, whose Regeneration gave back 296 (a fifth). The Templar
    took the whole 1,480 and healed 296 of it: their HP fell by 1,184."""
    frame = _hit(1_480, regenerated=296)
    event, heal = _events(frame)
    assert isinstance(event, DamageEvent)
    assert (event.damage, event.total_damage, event.power_scalar) == (1_480, 1_480, 10_830)
    assert isinstance(heal, HealEvent)
    assert (heal.actor_id, heal.target_id, heal.skill_code, heal.amount, heal.timestamp_ms) == (TEMPLAR, TEMPLAR, REGENERATION_SKILL, 296, 5)
    assert not heal.is_hot and not heal.absorb
    assert skill_name(REGENERATION_SKILL) == skill_name(REGENERATION_SKILL, "ko") == "Regeneration"


def test_a_two_byte_field_still_leaves_the_values_after_it():
    """296 takes two bytes: the values after it are read as before 0.2.406, the power scalar no hit's damage."""
    assert _varint(296) == b"\xa8\x02"
    assert _event(_hit(1_480, regenerated=296)).power_scalar == 10_830
    assert (_event(_hit(500, regenerated=100)).total_damage, _regeneration(_hit(500, regenerated=100)).amount) == (500, 100)


def test_without_the_bit_or_with_nothing_given_back_there_is_no_heal():
    """No bit 0x20, a field of 0: the hit counts its value and nothing heals. With the bit and a field of 0 (a hit
    under 5 HP, or one the shields took whole), too."""
    assert _events(_hit(1_480)) == [_event(_hit(1_480))] and _event(_hit(1_480)).total_damage == 1_480
    assert _regeneration(_hit(1_480, mods=REGENERATION)) is None
    assert _event(_hit(4, mods=REGENERATION)).total_damage == 4
    # The other modifiers are read as before
    event = _event(_hit(1_480, regenerated=296, mods=0x08 | 0x02))
    assert {SpecialDamage.DOUBLE, SpecialDamage.PARRY, SpecialDamage.REGENERATION} <= event.specials


def test_the_direction_is_read_after_the_field():
    """200 is ``c8 01``: the direction is the byte after both."""
    assert _varint(200) == b"\xc8\x01"
    event = _event(_hit(1_000, regenerated=200, direction=FRONT))
    assert SpecialDamage.FRONTAL in event.specials and SpecialDamage.BACK not in event.specials
    event = _event(_hit(1_000, regenerated=200, direction=BACK))
    assert SpecialDamage.BACK in event.specials and SpecialDamage.FRONTAL not in event.specials
    assert not {SpecialDamage.BACK, SpecialDamage.FRONTAL} & _event(_hit(1_000, regenerated=200)).specials


def test_the_multi_hits_and_a_critical_hit_count_whole_too():
    """A hit of 2,792 with four multi-hits of 279, a fifth 558: its multi-hits as recorded, its total 2,792. A critical
    hit of 2,890 that Regeneration gave 578 back of."""
    frame = _hit(2_792, regenerated=558, power=15_875, hits=[279] * 4)
    event = _event(frame)
    assert (event.multi_hit_count, event.multi_hit_damage, event.damage, event.total_damage) == (4, 1_116, 1_676, 2_792)
    assert _regeneration(frame).amount == 558
    frame = _hit(2_890, regenerated=578, power=13_584, damage_type=3)
    assert (_event(frame).total_damage, _regeneration(frame).amount) == (2_890, 578)
    assert SpecialDamage.CRITICAL in _event(frame).specials


def test_the_fifth_of_a_hit_a_shield_took_part_of_is_of_what_got_past_it():
    """The 15 October capture's case: a hit of 6,046 that the Chanter's Protection Circle took 1,056 of; Regeneration
    gave back 998, a fifth of the 4,990 that got past it. The hit counts whole, as with every shield."""
    frame = _hit(6_046, regenerated=998, shields=[PROTECTION_CIRCLE])
    assert (_event(frame).total_damage, _regeneration(frame).amount) == (6_046, 998)


def test_a_hit_read_from_inside_another_record_keeps_its_regeneration():
    """A hit found inside a record of another kind is read from there: its Regeneration comes with it."""
    data = _frame(b"\x10\x99" + _record(1_480, regenerated=296))
    events = list(decode_stream(data, 5, set()))
    assert [type(e) for e in events] == [DamageEvent, HealEvent]
    assert (events[0].total_damage, events[1].amount, events[1].actor_id, events[1].skill_code) == (1_480, 296, TEMPLAR, REGENERATION_SKILL)


def test_in_a_match_the_templar_takes_the_hit_whole_and_heals_the_fifth():
    """The live meter, the overlay's healing and the saved log: the Ranger's hit counts 1,480, and the Templar's
    healing is the 296 their Regeneration gave back, named so."""
    engine = _entered()
    s = CombatSession()
    s.begin_capture()
    s.observe(engine, [], timestamp_ms=101_500)
    t = 110_000
    events = engine.consume(_hit(1_480, regenerated=296), t, STREAM)
    assert [type(e) for e in events] == [DamageEvent, HealEvent]
    s.observe(engine, events + [DamageEvent(TEMPLAR, RANGER, 12010000, 1500, t + 100)], timestamp_ms=t + 200)
    assert engine.healers[TEMPLAR].healing == 296 and RANGER not in engine.healers
    row = next(p for p in s.snapshot("party")["players"] if p["id"] == str(TEMPLAR))
    assert row["healing"] == 296
    doc = s.to_a2log("party")
    [fight] = [seg for seg in doc["segments"] if seg["events"]]
    me = next(p["id"] for p in doc["players"] if p["name"] == "Testme")
    [hit] = [e for e in fight["events"] if e["kind"] == "damage" and e.get("target") == me]
    [heal] = [e for e in fight["events"] if e["kind"] == "heal"]
    assert hit["amount"] == 1_480
    assert (heal["source"], heal["target"], heal["amount"], heal["skill"], heal["skill_id"]) == (me, me, 296, "Regeneration", REGENERATION_SKILL)
    assert "absorb" not in heal


def test_the_review_counts_regeneration_as_healing_that_landed():
    """The reading before the hit showed the Templar at full HP, so an instant heal measured against it would be all
    overheal; but Regeneration gives back part of what the same read's hit took."""
    me = "p:1:1"
    segment = {"events": [{"kind": "damage", "t": 1.0, "source": "p:1:2", "target": me, "amount": 1480.0},
                          {"kind": "heal", "t": 1.0, "source": me, "target": me, "skill_id": REGENERATION_SKILL,
                           "skill": "Regeneration", "amount": 296.0}],
               "health": [{"t": 0.0, "entity": me, "current": 10000.0, "max": 10000.0},
                          {"t": 1.0, "entity": me, "current": 8816.0, "max": 10000.0}]}
    [healer] = healing_summary(segment, {me})["healers"]
    assert (healer["amount"], healer["effective"], healer["overheal"], healer["unknown"]) == (296, 296, 0, 0)
