"""A critical hit of 25 or less counts its value, not its attacker's power scalar (0.2.405).

A rule took a critical layout-6 hit's first value for its damage when the second was 25 or less. But the first value is
the power scalar and the second the hit, a critical one's as any other's: in all 298 such hits read directly from the
archived captures the first value was a power scalar (10,000 to 17,250), the target's HP fell by the second in 204 reads
and by the first in none, and a shield's absorb took the second in all 51 it was on. A critical hit of 1 counted 10,000 or
more (docs/open-investigations.md). Synthetic records only, with the fields the captures carry."""
from aion2calc.meter.a2parser.models import SpecialDamage
from test_damage_lost_before_hp import _event, _hit

CRITICAL = 3


def test_a_critical_hit_of_one_counts_one():
    event = _event(_hit(1, power=13_254, damage_type=CRITICAL))
    assert (event.damage, event.total_damage, event.power_scalar) == (1, 1, 13_254)
    assert SpecialDamage.CRITICAL in event.specials


def test_up_to_twenty_five_and_beyond_read_alike():
    """25 was the largest value the rule took the power scalar for; 26 and up were always read as the hit."""
    for value in (25, 26, 2_890):
        event = _event(_hit(value, power=17_250, damage_type=CRITICAL))
        assert (event.total_damage, event.power_scalar) == (value, 17_250)


def test_its_multi_hits_are_read_after_its_value():
    """The rule also read the multi-hits from the hit's value on: the Abyss recording's critical hit of 2 with a
    multi-hit of 1 is a hit of 1 and a multi-hit of 1, 2 in all."""
    event = _event(_hit(2, power=13_254, damage_type=CRITICAL, hits=[1]))
    assert (event.damage, event.multi_hit_count, event.multi_hit_damage, event.total_damage) == (1, 1, 1, 2)


def test_a_small_hit_that_is_not_critical_reads_as_before():
    event = _event(_hit(1, power=13_254))
    assert (event.total_damage, event.power_scalar) == (1, 13_254)
