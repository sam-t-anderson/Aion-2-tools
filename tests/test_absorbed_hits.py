"""A hit a shield absorbed is no extra hit (0.2.400).

When a shield absorbs a hit, the ``04 38`` hit record sets bit 0x40 of its switch and, after the hit's values and its
multi-hits, names the shields: a count (one byte) and each shield's effect number (u32: the skill times 100 plus the
effect's index). With no multi-hits of the hit's own, the decoder read that count as a hit count and the effect
number's first bytes as a hit, whenever they fell in the multi-hit's range. Doom Shield's 1,207,000,711 is the bytes
``87 5e f1 47``, and ``87 5e`` is 12,039: such a hit Doom Shield absorbed decoded as one more hit of 12,039, 54 of them in
the 31 October arena recording, each adding 12,039 to the attacker's damage and the Templar's damage taken. A hit of
more than 12,039 had a hit of 12,039 carved out of it instead. Other shields' numbers read as hits of 57 to 14,743
(docs/open-investigations.md). Synthetic records only, laid out as the captures carry them."""
import pytest

from aion2calc.meter.a2parser.framing import read_varint
from aion2calc.meter.a2parser.models import DamageEvent, HealEvent
from aion2calc.meter.a2parser.parser import PoolCasters, decode_stream, parse_damage_packet
from test_shield_absorbs import APPLIED, UPDATE, _effect, _frame, _varint

RANGER, TEMPLAR = 12981, 4423
TEMPEST_SHOT, DOOM_SHIELD = 14340000, 12070007
#: Doom Shield's effect number: its skill times 100 plus its effect's index, 11
DOOM_SHIELD_EFFECT, GUARDING_SEAL_EFFECT = 1_207_000_711, 1_275_000_111
LAYOUT_6, MULTI_HITS, ABSORBED = 0x06, 0x20, 0x40

#: The effect numbers the archived captures' hits (15, 20, 21 and 31 October) name as their shields, and what the
#: decoder read their first bytes as: a hit when 50 to 500,000 (or the hit's damage)
SHIELDS = {
    1_207_000_711: 12_039,      # Doom Shield
    1_213_004_021: 1_260_661,   # Poach's shield
    1_222_000_021: 7_829,       # Grapple
    1_232_000_021: 21,          # Nezekan's Shield
    1_232_000_031: 31,
    1_232_000_041: 41,
    1_232_004_011: 1_814_955,   # (as the 0.2.399 notes give it)
    1_275_000_111: 47,          # Guarding Seal
    1_275_000_121: 57,
    1_516_001_011: 11_123,      # Steel Barrier
    1_516_002_011: 11_611,
    1_516_003_011: 12_099,
    1_516_004_011: 12_587,
    1_606_003_011: 67,          # Siphon
    1_742_001_011: 115,         # Yustiel's Power
    1_777_000_111: 221_949_743,  # Prayer of Concentration
    1_824_000_011: 11,          # Impeding Authority
    1_824_001_011: 1_523,
    1_824_003_011: 2_499,
    1_873_000_211: 19,          # Protection Circle
    1_873_000_311: 119,
    1_412_002_711: 14_743,      # the Ranger's Ambush Kick, one hit in the Abyss
}


def _hit(damage, *, hits=(), shields=(), switch=LAYOUT_6, values=None, end=b"\x01\x00"):
    """One ``04 38`` hit of layout 6, the Ranger's on the Templar: target, switch, an unused varint, actor, skill (u32),
    uid, damage type, ten bytes (modifiers and the hit's own effect), the values (a 0, the power scalar and the hit's
    whole damage, multi-hits included); then with 0x20 the multi-hits (a count and each hit), with 0x40 the shields
    that absorbed it (a count and each effect number, u32), and the record's end."""
    if hits:
        switch |= MULTI_HITS
    if shields:
        switch |= ABSORBED
    values = (0, 10_000, damage) if values is None else values
    body = (_varint(TEMPLAR) + _varint(switch) + _varint(0) + _varint(RANGER) + TEMPEST_SHOT.to_bytes(4, "little")
            + b"\x00" + _varint(2) + bytes(10) + b"".join(_varint(v) for v in values))
    if hits:
        body += _varint(len(hits)) + b"".join(_varint(h) for h in hits)
    if shields:
        body += bytes([len(shields)]) + b"".join(number.to_bytes(4, "little") for number in shields)
    return _frame(b"\x04\x38" + body + end)


def _decoded(frame):
    [event] = parse_damage_packet(frame, timestamp_ms=5)
    assert isinstance(event, DamageEvent) and (event.actor_id, event.target_id) == (RANGER, TEMPLAR)
    return event.damage, event.multi_hit_count, event.multi_hit_damage, event.total_damage


def test_a_hit_doom_shield_absorbed_is_no_extra_hit_of_12039():
    """The reported case: Doom Shield absorbs 236 of the Ranger's hit. The record's count 1 and Doom Shield's first
    two bytes, 12,039 as a varint, decoded as a multi-hit, so the hit counted 12,275."""
    assert read_varint(DOOM_SHIELD_EFFECT.to_bytes(4, "little"), 0).value == 12_039
    assert _decoded(_hit(236, shields=[DOOM_SHIELD_EFFECT])) == (236, 0, 0, 236)
    # The same hit with no shield, as the records without bit 0x40 carry it
    assert _decoded(_hit(236)) == (236, 0, 0, 236)


@pytest.mark.parametrize("damage", [236, 20_000])
@pytest.mark.parametrize("effect", sorted(SHIELDS))
def test_no_shields_effect_number_is_a_hit(effect, damage):
    """Every shield the captures' hits name: its effect number is no hit, whether its bytes fell in the multi-hit's
    range (one hit more, or one carved out of a larger hit) or not."""
    assert read_varint(effect.to_bytes(4, "little"), 0).value == SHIELDS[effect]
    assert _decoded(_hit(damage, shields=[effect])) == (damage, 0, 0, damage)


def test_two_shields_absorbing_one_hit_are_no_hits():
    """A record can name two or three shields (Doom Shield and Guarding Seal here): the count 2 read as two hits,
    12,039 and 9,201, 21,240 in all."""
    assert _decoded(_hit(244, shields=[DOOM_SHIELD_EFFECT, GUARDING_SEAL_EFFECT])) == (244, 0, 0, 244)
    assert _decoded(_hit(135, shields=[GUARDING_SEAL_EFFECT, DOOM_SHIELD_EFFECT])) == (135, 0, 0, 135)


def test_the_multi_hits_before_the_shields_are_kept():
    """A hit with multi-hits (0x20) names its shields after them: the multi-hits are read as before, and end there."""
    assert _decoded(_hit(1_000, hits=[100, 100])) == (800, 2, 200, 1_000)
    assert _decoded(_hit(1_000, hits=[100, 100], shields=[DOOM_SHIELD_EFFECT])) == (800, 2, 200, 1_000)
    assert _decoded(_hit(2_098, hits=[349] * 4, shields=[GUARDING_SEAL_EFFECT, 1_213_004_021])) == (702, 4, 1_396, 2_098)


def test_the_shields_after_an_unread_value_are_no_hit_count():
    """A hit whose values begin with two zeros: the decoder takes the third value as the hit's and leaves the fourth
    unread, then took the shields' count after it for a hit count, and Doom Shield for a hit of 12,039 carved out of
    the hit. The shields stay no hit."""
    damage, count, multi, total = _decoded(_hit(0, values=(0, 0, 14_969, 2_168), shields=[DOOM_SHIELD_EFFECT]))
    assert (count, multi) == (0, 0) and damage == total


def test_the_record_ends_after_the_shields():
    """The shields are followed by the record's end: a byte and a 0 (1 to 7 nearly always, up to 39 in the captures),
    or the frame's end."""
    for end in (b"\x02\x00\x01", b"\x25\x00", b""):
        assert _decoded(_hit(236, shields=[DOOM_SHIELD_EFFECT], end=end)) == (236, 0, 0, 236)


def test_the_hit_is_what_the_shield_took():
    """The read holds the hit and Doom Shield's absorb of it (a ``05 38`` update, 0.2.399): the Templar's shield took
    236, and the hit dealt 236."""
    pools = PoolCasters()
    assert list(decode_stream(_effect(TEMPLAR, APPLIED, TEMPLAR, 77, DOOM_SHIELD, 9_236), 4, set(), pools=pools)) == []
    absorb = _effect(TEMPLAR, UPDATE, RANGER, 77, DOOM_SHIELD, 9_000, took=236)
    hit, heal = decode_stream(absorb + _hit(236, shields=[DOOM_SHIELD_EFFECT]), 5, set(), pools=pools)
    assert isinstance(hit, DamageEvent) and (hit.total_damage, hit.multi_hit_count) == (236, 0)
    assert heal == HealEvent(TEMPLAR, DOOM_SHIELD, 236, 5, is_hot=False, target_id=TEMPLAR, absorb=True)
