"""Hit positions (0.2.308): each class's recorded front/back mix on bosses, Back Attack in the damage
formula, Front/Back Attack Critical Hit, no parries from behind, and the Genus lines left unscored."""
import pytest

from aion2calc.model.character import parse_bonus_text
from aion2calc.model.damage import HitContext, crit_probability, expected_hit
from aion2calc.model.stats import Stats, crit_chance
from aion2calc.plan.genus import ACCURACY_REASON, line_stats, unscored_reason
from aion2calc.sim.engine import BOSS_POSITIONS, Target


def _derived(**kw):
    s = Stats(weapon_min=100, weapon_max=100, attack=900, crit=600)
    s.add(kw)
    return s.derived()


def _hit(d, target, **ctx):
    return expected_hit(d, {}, target, HitContext(flat=100, coef=0.5, **ctx))


FRONT, BACK, SIDE = Target(tolerance=0.0, positions=(1.0, 0.0)), Target(tolerance=0.0, positions=(0.0, 1.0)), \
    Target(tolerance=0.0, positions=(0.0, 0.0))


def test_a_mixed_target_is_the_share_weighted_sum_of_its_positions():
    d = _derived(front_atk=80, back_atk=120, front_amp=0.04, back_amp=0.06, front_crit=40, back_crit=60)
    mixed = Target(tolerance=0.0, positions=(0.25, 0.5))
    expected = 0.25 * _hit(d, FRONT) + 0.5 * _hit(d, BACK) + 0.25 * _hit(d, SIDE)
    assert _hit(d, mixed) == pytest.approx(expected, rel=1e-9)


def test_each_positional_stat_counts_only_from_its_side():
    base = _derived()
    for field, side in (("front_atk", FRONT), ("front_amp", FRONT), ("front_crit", FRONT),
                        ("back_atk", BACK), ("back_amp", BACK), ("back_crit", BACK)):
        d = _derived(**{field: 0.05 if field.endswith("amp") else 100})
        for target in (FRONT, BACK, SIDE):
            if target is side:
                assert _hit(d, target) > _hit(base, target), field
            else:
                assert _hit(d, target) == pytest.approx(_hit(base, target), rel=1e-12), field
    # the damage boost is its own multiplier on that side's hits
    assert _hit(_derived(back_amp=0.1), BACK) == pytest.approx(1.1 * _hit(base, BACK), rel=1e-9)


def test_back_attack_reaches_the_damage_formula():
    assert Stats(back_atk=50).derived().back_atk == 50
    d = _derived(back_atk=100)
    # +100 flat on every hit from behind, through the crit factor (Critical Attack aside)
    p = crit_chance(d.crit_stat)
    assert _hit(d, BACK) - _hit(_derived(), BACK) == pytest.approx(100 * (1 + 0.5 * p), rel=1e-9)
    assert parse_bonus_text("Back Attack +20, Back Attack Critical Hit +30") == {"back_atk": 20, "back_crit": 30}


def test_hits_from_behind_are_never_parried():
    d = _derived()
    for positions, factor in (((0.0, 1.0), 1.0), ((1.0, 0.0), 0.9), ((0.0, 0.0), 0.9)):
        parried = Target(tolerance=0.0, positions=positions, parry=0.2)
        clean = Target(tolerance=0.0, positions=positions)
        assert _hit(d, parried) == pytest.approx(factor * _hit(d, clean), rel=1e-12)


def test_positional_crit_scales_like_critical_hit_and_feeds_on_crit_procs():
    d = Stats(crit=500, back_crit=100, precision=100).derived()
    assert d.back_crit == pytest.approx(110)            # +10% from Precision, as Critical Hit gets
    half_back = Target(positions=(0.0, 0.5))
    assert crit_probability(d, half_back) == pytest.approx(
        0.5 * crit_chance(d.crit_stat) + 0.5 * crit_chance(d.crit_stat + 110), rel=1e-12)


def test_the_frontal_flag_still_means_every_hit_from_one_side():
    assert Target().hit_positions() == (1.0, 0.0)
    assert Target(frontal=False).hit_positions() == (0.0, 1.0)
    with pytest.raises(ValueError):
        Target(positions=(0.7, 0.5))


def test_the_boss_scenario_uses_each_classes_recorded_mix():
    from aion2calc.run import prepare
    from aion2calc.scenarios import boss, dummy, typical_build
    assert set(BOSS_POSITIONS) == {"assassin", "chanter", "cleric", "gladiator", "ranger", "sorcerer",
                                   "spiritmaster", "templar"}
    assert all(0 <= f and 0 <= b and f + b <= 1 for f, b in BOSS_POSITIONS.values())
    assert BOSS_POSITIONS["assassin"][1] > 0.6 > BOSS_POSITIONS["templar"][1]   # behind vs tanking
    for cls in ("assassin", "templar"):
        _, _, _, stats = prepare(typical_build(cls), boss(f"{cls}_l45_global_median"))
        assert stats.positions == BOSS_POSITIONS[cls]
        d = stats.derived()
        assert d.positions == BOSS_POSITIONS[cls]
        # the training dummy keeps its own target: every hit from the front
        _, _, _, plain = prepare(typical_build(cls), dummy(f"{cls}_l45_global_median"))
        assert plain.positions is None
    # the class mix stays on the character, not the stat sum
    s = Stats(positions=(0.2, 0.3))
    assert s.copy().positions == (0.2, 0.3)
    assert s.add({"crit": 1}).positions == (0.2, 0.3)


def test_genus_lines_without_a_damage_model_say_why():
    assert unscored_reason("Max Attack", {}).startswith("Not modeled")
    assert unscored_reason("Power Shard Damage Bonus", {}).startswith("Not modeled")
    assert unscored_reason("PvE Accuracy", {}) == ACCURACY_REASON
    assert unscored_reason("Accuracy Bonus", line_stats("Accuracy Bonus", "30", "Cogni", {})) == ACCURACY_REASON
    for stat in ("Back Attack", "Front Attack Critical Hit", "Back Attack Damage Boost", "Critical Hit"):
        assert unscored_reason(stat, line_stats(stat, "2%" if "Boost" in stat else "30", "Varian", {})) == ""
    from aion2calc.opt.genus import prepare
    plan = prepare({"Special": {"level": 3, "lines": [
        {"slot": 1, "stat": "Max Attack", "value": "15"},
        {"slot": 3, "stat": "Back Attack Critical Hit", "value": "30"}]}}, "pve")
    reasons = {row["stat"]: row["reason"] for row in plan["lines"]}
    assert reasons["Max Attack"].startswith("Not modeled")
    assert reasons["Back Attack Critical Hit"] == ""
    assert plan["stats"] == {"back_crit": 30.0}
