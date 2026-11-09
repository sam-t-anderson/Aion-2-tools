"""A hit's damage is what it took off HP, and a two-byte field no longer shifts its values (0.2.402).

After a layout-6 hit's modifiers comes a varint: with modifier bit 0x20 (decoded as Smite) it is what the hit lost before
it reached HP, a fifth of its value when no shield took it, and without the bit 0. The target's HP drops by the value
less it (201 reads of the archived captures, none by the value). The decoder read it as one byte. From 128 on it takes
two, so for those hits the direction came from its second byte, and the values began with a second 0: the decoder took
the power scalar (9,000 to 17,060) for the hit's damage, 172 hits of the four captures. A hit whose field fit one byte
counted its whole value. Synthetic records only, with the fields the captures carry (docs/open-investigations.md)."""
from aion2calc.meter.a2parser.models import DamageEvent, SpecialDamage
from aion2calc.meter.a2parser.parser import parse_damage_packet
from test_shield_absorbs import _frame, _varint

RANGER, TEMPLAR = 12981, 4423
TEMPEST_SHOT = 14340000
LAYOUT_6, MULTI_HITS, LOST = 0x06, 0x20, 0x20
BACK, FRONT = 1, 2


def _hit(value, *, lost=0, power=10_830, mods=0, direction=0, hits=(), damage_type=2):
    """One ``04 38`` hit of layout 6, the Ranger's on the Templar: target, switch, an unused varint, actor, skill (u32),
    uid, damage type; then the modifiers (u8), what the hit lost before HP (a varint), the direction (u8), the hit's own
    effect number (u32) and a u32; the power scalar and the hit's value (its multi-hits included); with switch bit 0x20
    its multi-hits (a count and each hit); and the record's end."""
    mods |= LOST if lost else 0
    switch = LAYOUT_6 | (MULTI_HITS if hits else 0)
    body = (_varint(TEMPLAR) + _varint(switch) + _varint(0) + _varint(RANGER) + TEMPEST_SHOT.to_bytes(4, "little")
            + b"\x00" + _varint(damage_type) + bytes([mods]) + _varint(lost) + bytes([direction])
            + (TEMPEST_SHOT * 100 + 11).to_bytes(4, "little") + (1).to_bytes(4, "little")
            + _varint(power) + _varint(value))
    if hits:
        body += _varint(len(hits)) + b"".join(_varint(h) for h in hits)
    return _frame(b"\x04\x38" + body + b"\x01\x00")


def _event(frame) -> DamageEvent:
    [event] = parse_damage_packet(frame, timestamp_ms=5)
    assert isinstance(event, DamageEvent) and (event.actor_id, event.target_id) == (RANGER, TEMPLAR)
    return event


def test_a_two_byte_field_no_longer_makes_the_power_scalar_the_damage():
    """The arena recording's case: a hit of 1,480 that lost 296 (a fifth) took 1,184 off the Templar's HP. The field's
    two bytes made the values read 0, 0, 10,830, 1,480, and the decoder took the power scalar, 10,830, for the hit."""
    event = _event(_hit(1_480, lost=296))
    assert (event.damage, event.total_damage, event.power_scalar) == (1_184, 1_184, 10_830)
    assert _varint(296) == b"\xa8\x02"                                           # two bytes


def test_a_one_byte_field_is_taken_off_the_hit_too():
    """A hit of 500 that lost 100: the decoder read the field's one byte in place and counted the whole 500."""
    event = _event(_hit(500, lost=100))
    assert (event.damage, event.total_damage, event.power_scalar) == (400, 400, 10_830)


def test_without_the_bit_the_hit_counts_its_value():
    """No bit 0x20, a field of 0: the hit counts its value, as before. With the bit and a field of 0, too."""
    assert _event(_hit(1_480)).total_damage == 1_480
    assert _event(_hit(1_480, mods=LOST)).total_damage == 1_480
    # The other modifiers are read as before
    event = _event(_hit(1_480, lost=296, mods=0x08 | 0x02))
    assert {SpecialDamage.DOUBLE, SpecialDamage.PARRY, SpecialDamage.SMITE} <= event.specials


def test_the_direction_is_read_after_the_field():
    """With a two-byte field the decoder took its second byte for the direction: 200 is ``c8 01``, which read as a hit
    from behind, where the record says from the front."""
    assert _varint(200) == b"\xc8\x01"
    event = _event(_hit(1_000, lost=200, direction=FRONT))
    assert SpecialDamage.FRONTAL in event.specials and SpecialDamage.BACK not in event.specials
    event = _event(_hit(1_000, lost=200, direction=BACK))
    assert SpecialDamage.BACK in event.specials and SpecialDamage.FRONTAL not in event.specials
    assert not {SpecialDamage.BACK, SpecialDamage.FRONTAL} & _event(_hit(1_000, lost=200)).specials


def test_the_multi_hits_stay_as_recorded():
    """A hit of 2,792 with four multi-hits of 279 that lost 558: it took 2,234 off HP. The multi-hits keep their
    recorded values, and the main hit carries the loss."""
    event = _event(_hit(2_792, lost=558, power=15_875, hits=[279] * 4))
    assert (event.multi_hit_count, event.multi_hit_damage) == (4, 1_116)
    assert (event.damage, event.total_damage) == (1_118, 2_234)


def test_a_critical_hit_reads_the_same():
    """A critical hit (damage type 3) of 2,890 that lost 578."""
    event = _event(_hit(2_890, lost=578, power=13_584, damage_type=3))
    assert (event.total_damage, event.power_scalar) == (2_312, 13_584)
    assert SpecialDamage.CRITICAL in event.specials
