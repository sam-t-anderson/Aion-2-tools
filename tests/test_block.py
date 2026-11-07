"""Block against Accuracy (0.2.387; docs/methodology.md "Block against Accuracy"). A direct hit from the front or the
side is blocked, which the game records as a parry, with the chance its target's Block exceeds the attacker's
Accuracy by: 0.1 % a point (``PARRY_PER_ACCURACY``), never more than half the hits (``PARRY_CAP``). A hit from behind
never is, and a blocked hit deals half. The same slope sets how Accuracy lowers a boss's recorded parries (0.2.386).
Against monsters the attacker's Accuracy is Accuracy plus PvE Accuracy, against players Accuracy plus PvP Accuracy;
against players the target's Block is Block (raised by Dexterity and Space) plus PvP Block."""
from dataclasses import replace

import pytest

from aion2calc.model.character import DAEV_MAP, parse_bonus_text
from aion2calc.model.damage import HitContext, block_chance, expected_hit, parry_chance
from aion2calc.model.stats import Stats
from aion2calc.sim.engine import BOSS_PARRY, PARRY_CAP, PARRY_PER_ACCURACY, Target
from aion2calc.sources.character import OFFICIAL_IDS, PROFILE_STATS

CTX = HitContext(flat=1000.0, coef=2.0, element=None, tags=(), mult=1.0)


def _ratio(d, ctx=CTX, **target) -> float:
    """A hit's expected damage on a target with this Block, against the same target without one."""
    plain = {k: v for k, v in target.items() if k != "block"}
    return expected_hit(d, {}, Target(**target), ctx) / expected_hit(d, {}, Target(**plain), ctx)


def test_the_block_chance_is_a_tenth_of_a_percent_a_point_over_the_accuracy_and_at_most_half():
    assert PARRY_PER_ACCURACY == 0.001 and PARRY_CAP == 0.5
    assert block_chance(1100, 1100) == 0.0 and block_chance(900, 1100) == 0.0     # Accuracy met: nothing blocked
    assert block_chance(1100, 1000) == pytest.approx(0.10)
    # the Korean test against a Transcendence 10 boss (Block about 1,100), 600 hits a setting: +199, +72 and +59
    # Accuracy landed 19.7, 6.9 and 6.1 % more hits unparried
    for start, more, measured in ((756, 199, 0.1968), (957, 72, 0.0688), (1029, 59, 0.0607)):
        assert block_chance(1100, start) - block_chance(1100, start + more) == pytest.approx(measured, abs=0.005)
    assert block_chance(1100, 600) == block_chance(5000, 0) == PARRY_CAP


def test_a_blocked_hit_deals_half_from_the_front_or_side_and_a_hit_from_behind_is_never_blocked():
    d = Stats(attack=1000, crit=500, accuracy=900).derived()
    assert _ratio(d, block=1100) == pytest.approx(1 - 0.5 * 0.2)                            # every hit from the front
    assert _ratio(d, block=1100, positions=(0.0, 0.0)) == pytest.approx(1 - 0.5 * 0.2)      # every hit from the side
    assert _ratio(d, block=1100, frontal=False) == pytest.approx(1.0)                       # every hit from behind
    assert _ratio(d, block=1100, positions=(0.5, 0.5)) == pytest.approx(1 - 0.5 * 0.5 * 0.2)
    assert _ratio(d, block=5000) == pytest.approx(1 - 0.5 * PARRY_CAP)                      # at most half blocked
    assert _ratio(d, block=900) == pytest.approx(1.0)
    guaranteed = HitContext(flat=1000.0, coef=2.0, element=None, tags=("crit",), mult=1.0)
    assert _ratio(d, guaranteed, block=5000) == pytest.approx(1.0)                          # as the recordings show
    # a fixed parry chance still applies: the larger of it and the Block's chance counts
    assert _ratio(d, block=1100, parry=0.5) == pytest.approx(1.0)
    assert _ratio(d, block=1100, parry=0.1) == pytest.approx((1 - 0.5 * 0.2) / (1 - 0.5 * 0.1))


def test_a_bosss_given_block_takes_the_place_of_its_recorded_parries_and_accuracy_lowers_both_alike():
    from aion2calc.run import prepare
    from aion2calc.scenarios import boss, typical_build
    scen = boss("spiritmaster_l45_global_median")
    _, _, _, stats = prepare(typical_build("spiritmaster"), scen)
    d = stats.derived()
    recorded = parry_chance(d, scen.target)
    assert recorded == pytest.approx(BOSS_PARRY["spiritmaster"][0], abs=0.0005)        # the class's recorded rate
    assert parry_chance(d, replace(scen.target, block=d.accuracy + 250)) == pytest.approx(0.25)
    assert parry_chance(d, replace(scen.target, block=d.accuracy)) == 0.0               # a Block the Accuracy meets
    more = stats.copy()
    more.add({"accuracy": 10})
    gained = more.derived().accuracy - d.accuracy                                        # Freedom raises it too
    assert 10 <= gained and recorded > gained * PARRY_PER_ACCURACY
    assert parry_chance(more.derived(), scen.target) == pytest.approx(recorded - gained * PARRY_PER_ACCURACY)


def test_pve_accuracy_counts_against_monsters_and_pvp_accuracy_against_players():
    s = Stats(attack=1000, accuracy=900, pve_accuracy=100, pvp_accuracy=200, freedom=100)
    assert s.derived().accuracy == pytest.approx(900 * 1.1 + 100)          # Freedom raises Accuracy, +0.1 % a point
    s.pvp = True
    assert s.derived().accuracy == pytest.approx(900 * 1.1 + 200)


def test_dexterity_and_space_raise_block_and_pvp_block_adds_to_it_against_players():
    s = Stats(block=1000.0, dexterity=100.0, space=50.0, pvp_block=40.0)
    assert s.defenses({}).block == pytest.approx(1000 * (1 + 0.001 * 150) + 40)
    assert Stats().defenses({}).block == 0.0


def test_block_counts_in_world_pvp_survival_above_the_reference_attackers_accuracy():
    """World PvP's effective HP is HP over the share of the reference attacker's hit you take: Block (and PvP Block)
    above its Accuracy and PvP Accuracy blocks that share of its hits, each for half (its hits come from the front)."""
    from aion2calc.opt import world
    from aion2calc.run import prepare
    from aion2calc.scenarios import pvp_world, typical_build
    cls = "templar"
    scen = pvp_world(f"{cls}_l45_global_median")
    _, _, _, stats = prepare(typical_build(cls), scen)
    ref = world.reference(cls, scen)
    accuracy = ref[0].accuracy
    assert stats.defenses({}).block == 0.0
    base = world.survival(cls, stats, 0.0, 180.0, ref)
    assert base["block_chance"] == 0.0

    def with_block(points):
        s = stats.copy()
        s.add({"pvp_block": points})
        return world.survival(cls, s, 0.0, 180.0, ref)
    assert with_block(accuracy)["effective_hp"] == pytest.approx(base["effective_hp"])        # met: no blocks
    above = with_block(accuracy + 200.0)                                                      # a fifth blocked
    assert above["block_chance"] == pytest.approx(0.2)
    assert above["damage_taken"] == pytest.approx(base["damage_taken"] * (1 - 0.5 * 0.2))
    assert above["effective_hp"] == pytest.approx(base["effective_hp"] / (1 - 0.5 * 0.2))
    assert above["alive_share"] > base["alive_share"]
    assert with_block(accuracy + 5000.0)["effective_hp"] == pytest.approx(base["effective_hp"] / (1 - 0.5 * PARRY_CAP))
    assert "Block and PvP Block" in world.note() and "Block, movement" not in world.note()


def test_the_block_and_accuracy_stats_are_read_from_every_source():
    assert parse_bonus_text("Block +100, PvP Block +40, PvE Accuracy +50, PvP Accuracy +30") == {
        "block": 100.0, "pvp_block": 40.0, "pve_accuracy": 50.0, "pvp_accuracy": 30.0}
    assert DAEV_MAP["PvEAccuracy"] == ("pve_accuracy", 1) and DAEV_MAP["PvPAccuracy"] == ("pvp_accuracy", 1)
    assert OFFICIAL_IDS["Block"] == ("block", 1) and OFFICIAL_IDS["PvPBlock"] == ("pvp_block", 1)
    assert OFFICIAL_IDS["PvEAccuracy"] == ("pve_accuracy", 1) and OFFICIAL_IDS["PvPAccuracy"] == ("pvp_accuracy", 1)
    assert PROFILE_STATS["Space"] == "space"


def test_genus_block_lines_say_why_they_score_no_damage():
    from aion2calc.plan.genus import BLOCK_REASON, line_stats, unscored_reason
    for stat in ("Block", "Fera Block", "Varian Block"):
        assert unscored_reason(stat, line_stats(stat, "30", "Fera", {"Fera": 1.0})) == BLOCK_REASON
    assert "World PvP" in BLOCK_REASON


def test_simulate_takes_a_targets_block(capsys):
    """``simulate --target-block``: the boss parries at the Block's chance against the build's Accuracy instead of
    its class's recorded rate."""
    from aion2calc.__main__ import main
    from aion2calc.run import simulate
    from aion2calc.scenarios import boss, typical_build
    main(["simulate", "templar", "--target-block", "1100"])
    shown = capsys.readouterr().out.splitlines()[0]
    scen = boss("templar_l45_global_median")
    blocked = simulate(typical_build("templar"), replace(scen, target=replace(scen.target, block=1100.0))).dps
    assert shown == f"DPS {blocked:,.0f}"
    assert blocked < 0.9 * simulate(typical_build("templar"), scen).dps
