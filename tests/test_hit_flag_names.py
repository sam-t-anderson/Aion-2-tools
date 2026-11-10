"""The decoder's hit flags are named for what the record says (0.2.408).

Bit 0x20 of a hit's modifiers is the target's Regeneration, which gave back the HP that follows the modifiers; bit 0x40
a block that took all of the hit but 1 HP, only ever with a parry (0x02) or a shield block (0x01), never from behind.
The decoder named them Smite and Power Shard. Double, bit 0x08, is the Smite, and no record the meter reads marks a
Power Shard, so the planner no longer says no recorded hit used one (docs/open-investigations.md). Synthetic records
only."""
from aion2calc.meter.a2parser.models import SpecialDamage
from aion2calc.meter.a2parser.parser import FULL_BLOCK, REGENERATION, SHIELD_BLOCK
from aion2calc.plan.genus import UNSCORED
from test_regeneration import _event, _hit

PARRY, DOUBLE = 0x02, 0x08


def test_bit_0x20_is_regeneration_and_bit_0x40_a_full_block():
    assert (REGENERATION, FULL_BLOCK) == (0x20, 0x40)
    assert SpecialDamage.REGENERATION in _event(_hit(1_480, regenerated=296)).specials
    assert {SpecialDamage.PARRY, SpecialDamage.FULL_BLOCK} <= _event(_hit(1, mods=PARRY | FULL_BLOCK)).specials
    assert {SpecialDamage.SHIELD_BLOCK, SpecialDamage.FULL_BLOCK} <= _event(_hit(1, mods=SHIELD_BLOCK | FULL_BLOCK)).specials
    assert SpecialDamage.DOUBLE in _event(_hit(2_000, mods=DOUBLE)).specials
    assert not {SpecialDamage.REGENERATION, SpecialDamage.FULL_BLOCK} & _event(_hit(1_000)).specials


def test_the_old_names_are_gone():
    assert not {"SMITE", "POWER_SHARD"} & {flag.name for flag in SpecialDamage}
    assert {"regeneration", "fullblock"} <= {flag.value for flag in SpecialDamage}
    reason = UNSCORED["Power Shard Damage Bonus"]
    assert reason.startswith("Not modeled") and "no record the meter reads says when a Power Shard was used" in reason
