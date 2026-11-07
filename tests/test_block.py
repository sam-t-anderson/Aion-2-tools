"""Block against Accuracy (0.2.386; docs/methodology.md "Block against Accuracy"). A direct hit from the front or the
side is blocked, which the game records as a parry, with the chance its target's Block exceeds the attacker's
Accuracy by: 0.1 % a point, never more than half the hits. A hit from behind never is, and a blocked hit deals half.
Against monsters the attacker's Accuracy is Accuracy plus PvE Accuracy, against players Accuracy plus PvP Accuracy;
against players the target's Block is Block plus PvP Block."""
import pytest

from aion2calc.model.character import DAEV_MAP, parse_bonus_text
from aion2calc.model.damage import HitContext, expected_hit
from aion2calc.model.stats import BLOCK_CAP, Stats, block_chance
from aion2calc.sim.engine import BOSS_POSITIONS, Target
from aion2calc.sources.character import OFFICIAL_IDS, PROFILE_STATS

CTX = HitContext(flat=1000.0, coef=2.0, element=None, tags=(), mult=1.0)


def _ratio(d, ctx=CTX, **target) -> float:
    """A hit's expected damage on a target with this Block, against the same target without one."""
    plain = {k: v for k, v in target.items() if k != "block"}
    return expected_hit(d, {}, Target(**target), ctx) / expected_hit(d, {}, Target(**plain), ctx)


def test_the_block_chance_is_a_tenth_of_a_percent_a_point_over_the_accuracy_and_at_most_half():
    assert block_chance(1100, 1100) == 0.0 and block_chance(900, 1100) == 0.0     # Accuracy met: nothing blocked
    assert block_chance(1100, 1000) == pytest.approx(0.10)
    # the community tests: +199, +72 and +59 Accuracy short of a boss's Block, 19.7, 6.9 and 6.1 % more hits landed
    for more, measured in ((199, 0.1968), (72, 0.0688), (59, 0.0607)):
        assert block_chance(1100, 800) - block_chance(1100, 800 + more) == pytest.approx(measured, abs=0.005)
    assert block_chance(1100, 600) == block_chance(5000, 0) == BLOCK_CAP == 0.5


def test_a_blocked_hit_deals_half_from_the_front_or_side_and_a_hit_from_behind_is_never_blocked():
    d = Stats(attack=1000, crit=500, accuracy=900).derived()
    assert _ratio(d, block=1100) == pytest.approx(1 - 0.5 * 0.2)                            # every hit from the front
    assert _ratio(d, block=1100, positions=(0.0, 0.0)) == pytest.approx(1 - 0.5 * 0.2)      # every hit from the side
    assert _ratio(d, block=1100, frontal=False) == pytest.approx(1.0)                       # every hit from behind
    assert _ratio(d, block=1100, positions=(0.5, 0.5)) == pytest.approx(1 - 0.5 * 0.5 * 0.2)
    assert _ratio(d, block=5000) == pytest.approx(1 - 0.5 * BLOCK_CAP)                      # at most half blocked
    assert _ratio(d, block=900) == pytest.approx(1.0)
    guaranteed = HitContext(flat=1000.0, coef=2.0, element=None, tags=("crit",), mult=1.0)
    assert _ratio(d, guaranteed, block=5000) == pytest.approx(1.0)                          # as the recordings show
    # a fixed parry chance still applies: the larger of it and the Block's chance counts
    assert _ratio(d, block=1100, parry=0.5) == pytest.approx(1.0)
    assert _ratio(d, block=1100, parry=0.1) == pytest.approx((1 - 0.5 * 0.2) / (1 - 0.5 * 0.1))


def test_pve_accuracy_counts_against_monsters_and_pvp_accuracy_against_players():
    d = Stats(attack=1000, accuracy=900, pve_accuracy=100, pvp_accuracy=200, freedom=100).derived()
    monster, player = Target(), Target(is_player=True, is_boss=False, tolerance=0.0)
    assert d.accuracy == pytest.approx(990)                         # Freedom raises Accuracy, +0.1 % a point
    assert d.accuracy_against(monster) == pytest.approx(1090) and d.accuracy_against(player) == pytest.approx(1190)
    assert _ratio(d, block=1190) == pytest.approx(1 - 0.5 * 0.1)                             # 1,090 against a monster
    assert _ratio(d, block=1190, is_player=True, is_boss=False, tolerance=0.0) == pytest.approx(1.0)   # 1,190: met


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
    accuracy = ref[0].accuracy_against(Target(is_player=True))
    assert stats.defenses({}).block == 0.0
    base = world.survival(cls, stats, 0.0, 180.0, ref)

    def with_block(points):
        s = stats.copy()
        s.add({"pvp_block": points})
        return world.survival(cls, s, 0.0, 180.0, ref)
    assert with_block(accuracy)["effective_hp"] == pytest.approx(base["effective_hp"])        # met: no blocks
    above = with_block(accuracy + 200.0)                                                      # a fifth blocked
    assert above["damage_taken"] == pytest.approx(base["damage_taken"] * (1 - 0.5 * 0.2))
    assert above["effective_hp"] == pytest.approx(base["effective_hp"] / (1 - 0.5 * 0.2))
    assert above["alive_share"] > base["alive_share"]
    assert with_block(accuracy + 5000.0)["effective_hp"] == pytest.approx(base["effective_hp"] / (1 - 0.5 * BLOCK_CAP))
    assert "Block" in world.note() and "Block, Evasion" not in world.note()


def test_a_boss_given_a_block_parries_the_hits_of_a_character_short_of_its_accuracy():
    """The boss scenario assumes the Accuracy met (the recordings: bosses parried under 1 % of most classes' hits);
    given a Block it parries the front and side hits by what the character lacks, so a class that fights from behind
    loses less."""
    from aion2calc.run import prepare, simulate
    from aion2calc.scenarios import BOSS_BLOCK, boss, typical_build
    assert boss().target.block == 0.0 and BOSS_BLOCK
    loss = {}
    for cls in ("templar", "assassin"):
        lo, b = f"{cls}_l45_global_median", typical_build(cls)
        _, _, _, stats = prepare(b, boss(lo))
        accuracy = stats.derived().accuracy_against(boss(lo).target)
        met = simulate(b, boss(lo)).dps
        assert simulate(b, boss(lo, block=accuracy)).dps == pytest.approx(met)
        loss[cls] = 1 - simulate(b, boss(lo, block=accuracy + 300.0)).dps / met
        front, back = BOSS_POSITIONS[cls]
        assert 0.0 < loss[cls] <= 0.5 * 0.3 * (1 - back) + 1e-9           # a hit from behind is never blocked
    assert loss["templar"] > 2 * loss["assassin"] > 0.0


def test_the_block_and_accuracy_stats_are_read_from_every_source():
    assert parse_bonus_text("Block +100, PvP Block +40, PvE Accuracy +50, PvP Accuracy +30") == {
        "block": 100.0, "pvp_block": 40.0, "pve_accuracy": 50.0, "pvp_accuracy": 30.0}
    assert DAEV_MAP["PvEAccuracy"] == ("pve_accuracy", 1) and DAEV_MAP["PvPAccuracy"] == ("pvp_accuracy", 1)
    assert OFFICIAL_IDS["Block"] == ("block", 1) and OFFICIAL_IDS["PvPBlock"] == ("pvp_block", 1)
    assert OFFICIAL_IDS["PvEAccuracy"] == ("pve_accuracy", 1) and OFFICIAL_IDS["PvPAccuracy"] == ("pvp_accuracy", 1)
    assert PROFILE_STATS["Space"] == "space"


def test_genus_block_and_accuracy_lines_say_what_they_do():
    from aion2calc.plan.genus import ACCURACY_REASON, BLOCK_REASON, line_stats, unscored_reason
    for stat in ("Block", "Fera Block", "Varian Block"):
        assert unscored_reason(stat, line_stats(stat, "30", "Fera", {"Fera": 1.0})) == BLOCK_REASON
    for stat in ("PvE Accuracy", "Accuracy Bonus", "Cogni Accuracy"):
        assert unscored_reason(stat, line_stats(stat, "30", "Cogni", {"Cogni": 1.0})) == ACCURACY_REASON
    assert "Block" in ACCURACY_REASON and "World PvP" in BLOCK_REASON
