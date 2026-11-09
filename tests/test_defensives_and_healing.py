"""0.2.386: heal amounts, every class's defensives in World PvP, incoming crowd control, Storm Slice and the boss's
parries against Accuracy; 0.2.400: the heals over time's rates from what their ticks took."""
from dataclasses import replace

import pytest

from aion2calc.kit import defensives as D
from aion2calc.kit import healing as H
from aion2calc.kit.base import ClassData
from aion2calc.model.damage import parry_chance
from aion2calc.opt import world as W
from aion2calc.run import prepare
from aion2calc.scenarios import boss, dummy, pvp, pvp_world, typical_build
from aion2calc.sim.engine import BOSS_PARRY, PARRY_PER_ACCURACY, Sim

CLASSES = ("assassin", "chanter", "cleric", "gladiator", "ranger", "sorcerer", "spiritmaster", "templar")


def _sim(build, scen):
    _, _, kit, stats = prepare(build, scen)
    return Sim(stats.derived(), kit.actions, kit.policy, scen.target, scen.config, hooks=kit.hooks,
               cond_mods=kit.cond_mods).run(), kit, stats


# ----------------------------------------------------------------------------------------------------- healing
def test_a_heal_is_its_tooltip_value_times_one_plus_attack_over_two_thousand():
    cd = ClassData("cleric")
    b = typical_build("cleric")
    _, _, _, stats = prepare(b, boss("cleric_l45_global_median"))
    d = stats.derived()
    out = H.modelled_healing("cleric", b, cd, d)
    assert out["multiplier"] == pytest.approx(1 + d.attack() / 2000)
    levels = b.effective_levels(cd)
    row = next(r for r in out["by_skill"] if r["skill_id"] == 17100000)              # Healing Light
    v = cd.vals(17100000, levels[17100000])
    assert row["per_application"] == pytest.approx((v[0][0] + v[1][0]) / 2 * out["multiplier"])
    assert row["per_minute"] == pytest.approx(row["per_application"] * H.HEAL_RATES["cleric"][17100000][0])
    assert row["self_per_minute"] == pytest.approx(row["per_minute"] * 0.5)          # the caster and one more
    assert out["per_minute"] == pytest.approx(sum(r["per_minute"] for r in out["by_skill"]))
    assert sum(r["share"] for r in out["by_skill"]) == pytest.approx(1.0)
    # a stigma heal counts only when it is slotted
    assert all(r["skill_id"] not in b.stigmas or r["skill_id"] in (17160000, 17290000) for r in out["by_skill"])
    slotted = b.copy()
    slotted.stigmas[17160000] = 5
    assert any(r["skill_id"] == 17160000 for r in H.modelled_healing("cleric", slotted, cd, d)["by_skill"])
    # no modelled heals for the damage classes; the Chanter's Recuperation averages its heal and four ticks
    assert H.modelled_healing("sorcerer", typical_build("sorcerer"), ClassData("sorcerer"), d) is None
    ch = ClassData("chanter")
    v = ch.vals(18120000, 10)
    ticks = round(v[5]["ms"] / v[4]["ms"])
    assert H.tooltip_value(ch, 18120000, 10) == pytest.approx(((v[0][0] + v[1][0]) / 2 + ticks * v[3]) / (1 + ticks))


def test_the_heals_over_time_count_what_their_ticks_took():
    """0.2.400: Light of Regeneration's and Recuperation's rates are 0.2.386's times the share of their recorded healing
    that their ticks took in the same logs (10.6 % and 63.6 %; docs/methodology.md, "Heal rates from what the heals
    over time took"). The instant heals and Benevolence were read right and keep 0.2.386's rates."""
    cd = ClassData("cleric")
    lor = H.HEAL_RATES["cleric"][17090000][0]
    assert lor == pytest.approx(59.1 * 0.1059, abs=0.05)
    assert H.HEAL_RATES["chanter"][18120000][0] == pytest.approx(32.0 * 0.6362, abs=0.05)
    # one whole Light of Regeneration a cooldown on each of the five players it reaches is the most it can heal:
    # 0.2.386's 59.1 was six times that
    assert lor <= 60 / min(cd.skills[17090000]["cd"]) * 5
    assert {sid: rate for sid, (rate, _) in H.HEAL_RATES["cleric"].items() if sid != 17090000} == {
        17800000: 36.4, 17120000: 15.2, 17100000: 11.5, 17160000: 32.3, 17290000: 1.0}
    # the caster's shares are the tooltips', which the rebuild does not move
    assert H.HEAL_RATES["cleric"][17090000][1] == 0.20 and H.HEAL_RATES["chanter"][18120000][1] == pytest.approx(1 / 6)
    # so Light of Regeneration is no longer most of a typical Cleric's healing (80 % at 59.1)
    b = typical_build("cleric")
    _, pb, _, stats = prepare(b, boss("cleric_l45_global_median"))
    out = H.modelled_healing("cleric", pb, cd, stats.derived())
    assert next(r for r in out["by_skill"] if r["skill_id"] == 17090000)["share"] < 0.5


def test_a_healers_time_and_the_reports_carry_the_modelled_healing():
    assert H.heal_time_share("cleric") == pytest.approx(4.6 * 0.45 / 60)
    assert H.heal_time_share("chanter") == pytest.approx(1.2 * 0.56 / 60)
    assert H.heal_time_share("gladiator") == 0.0
    from aion2calc.app import views
    from aion2calc.model.character import load_loadout
    imp = type("Imp", (), {"cls": "cleric", "loadout": load_loadout("cleric_l45_global_median")})()
    out = views._modelled_healing(imp, ClassData("cleric"), typical_build("cleric"))
    assert out and out["hps"] == pytest.approx(out["per_minute"] / 60) and out["note"].startswith("Healing is modelled")


# -------------------------------------------------------------------------------------------------- defensives
def test_every_class_has_defensive_passives_that_read_at_its_levels():
    for cls in CLASSES:
        d = D.defensives(cls, typical_build(cls), 180.0)
        assert d.stats, cls
        assert d.status_resist > 0.1 and d.breaks == 3 and d.tenacity_s == pytest.approx(15.0), cls
    tmp = D.defensives("templar", typical_build("templar"), 180.0)
    cd = ClassData("templar")
    lv = typical_build("templar").effective_levels(cd)
    eh = cd.vals(12710000, lv[12710000])                                           # Enhance Health
    assert tmp.stats["hp"] == pytest.approx(eh[0]) and tmp.stats["hp_pct"] == pytest.approx(eh[1] / 100)
    # a higher passive level gives more; a stigma counts only when slotted, its options at their stigma level
    b = typical_build("templar")
    b.sp[12710000] = 10
    assert D.defensives("templar", b, 180.0).stats["hp"] > tmp.stats["hp"]
    assert "pvp_tol" in tmp.stats
    b2 = typical_build("templar")
    b2.stigmas[12190000] = 4                                                       # Second Skin, below level 20
    with_skin = D.defensives("templar", b2, 180.0)
    up = 10.0 / 90.0                                                                # 10 s at level 4 (14.5 at 10), cd 90 s
    v = cd.vals(12190000, 4)
    assert with_skin.stats["pvp_tol"] - tmp.stats["pvp_tol"] == pytest.approx(v[1] / 100 * v[2]["ms"] / 1000 / 90)
    assert up > 0
    b2.stigmas[12190000] = 20
    assert D.defensives("templar", b2, 180.0).stats["pvp_tol"] > with_skin.stats["pvp_tol"]    # +10 % at level 20


def test_defiances_options_and_the_lifesteal_unit():
    b = typical_build("assassin")
    cd = ClassData("assassin")
    base = D.defensives("assassin", b, 180.0)
    b.sp[13260000] = 10
    b.specs[13260000] = (13260030,)                                                  # 20 % HP on use (level 8)
    healed = D.defensives("assassin", b, 180.0)
    cooldown = cd.cd(13260000, b.effective_levels(cd)[13260000])
    assert healed.heal_share - base.heal_share == pytest.approx(0.20 * -(-180 // cooldown))
    # "Absorbs 500, 500% HP" restores 5 % of maximum HP a press (the recorded heals: 5.3-5.4 %)
    b.sp[13340000] = 8
    assert D.lifesteal_share("assassin", b, cd, 13340000) == 0.0                      # not chosen
    b.specs[13340000] = (13340010,)
    assert D.lifesteal_share("assassin", b, cd, 13340000) == pytest.approx(0.05)
    b.specs[13010000] = (13010020,)
    b.sp[13010000] = 8
    assert D.lifesteal_share("assassin", b, cd, 13010000) == pytest.approx(0.007)


def test_shields_on_presses_need_their_option_or_stigma_level():
    cd = ClassData("templar")
    b = typical_build("templar")
    b.stigmas[12070000] = 1
    assert D.shield_on_press("templar", b, cd, 12070000) == pytest.approx(0.05)      # Doom Shield
    assert D.shield_on_press("templar", b, cd, 12130000) == 0.0                     # Poach without its option
    b.sp[12130000] = 10
    b.specs[12130000] = (12130040,)
    assert D.shield_on_press("templar", b, cd, 12130000) == pytest.approx(0.10)
    sm = typical_build("spiritmaster")
    sm.stigmas[16060000] = 14
    assert D.shield_on_press("spiritmaster", sm, ClassData("spiritmaster"), 16060000) == 0.0
    sm.stigmas[16060000] = 15
    assert D.shield_on_press("spiritmaster", sm, ClassData("spiritmaster"), 16060000) == pytest.approx(0.30)


def test_status_effect_resist_and_defiance_keep_crowd_control_off():
    scen = pvp_world("gladiator_l45_global_median")
    b = typical_build("gladiator")
    _, _, stats, _, inputs = W._run("gladiator", b, scen)
    ref = W.reference("gladiator", scen)
    base = W.survival("gladiator", stats, 0.0, 180.0, ref, **inputs)
    attackers = W.WORLD["attackers"]["melee"]
    aimed = attackers * W.WORLD["incoming_control_s"] / 60
    assert base["control_landing"] == pytest.approx(min(0.5, aimed * (1 - base["status_resist"])))
    assert 0 < base["controlled_self"] < base["control_landing"]
    assert base["acting_share"] == pytest.approx(1 - base["controlled_self"])
    resist = stats.copy()
    resist.cc_resist = 0.30
    assert W.survival("gladiator", resist, 0.0, 180.0, ref, **inputs)["acting_share"] > base["acting_share"]
    no_defiance = dict(inputs, defense=replace(inputs["defense"], tenacity_s=0.0, breaks=0.0))
    assert W.survival("gladiator", stats, 0.0, 180.0, ref, **no_defiance)["acting_share"] < base["acting_share"]
    a = W.assess("gladiator", b, scen, None)
    assert a["score"] == pytest.approx(a["dps"] * a["alive_share"] * a["acting_share"])


def test_the_incoming_crowd_control_is_the_typical_rotations():
    per_min = []
    for cls in CLASSES:
        scen = pvp(f"{cls}_l45_global_median")
        res, _, _ = _sim(typical_build(cls), scen)
        per_min.append(60 * res.control / res.duration)
    assert sum(per_min) / len(per_min) == pytest.approx(W.WORLD["incoming_control_s"], rel=0.25)


def test_evasion_above_the_attackers_accuracy_evades_up_to_the_cap():
    assert W.evasion_chance(300.0, 300.0) == 0.0
    assert W.evasion_chance(500.0, 300.0) == pytest.approx(0.12)
    assert W.evasion_chance(5000.0, 300.0) == W.WORLD["evasion_cap"] == 0.30
    scen = pvp_world("ranger_l45_global_median")
    _, _, stats, _, inputs = W._run("ranger", typical_build("ranger"), scen)
    ref = W.reference("ranger", scen)
    base = W.survival("ranger", stats, 0.0, 180.0, ref, **inputs)
    agile = stats.copy()
    agile.evasion += 500.0
    more = W.survival("ranger", agile, 0.0, 180.0, ref, **inputs)
    assert more["evade_chance"] > base["evade_chance"] and more["alive_share"] > base["alive_share"]
    assert more["control_landing"] < base["control_landing"]                       # an evaded hit lands no control


# ------------------------------------------------------------------------------------------------- Storm Slice
def test_storm_slice_follows_defiances_option_in_the_player_target_kits():
    from aion2calc.kit.assassin import STORM_SLICE_FLAT, storm_slice
    cd = ClassData("assassin")
    b = typical_build("assassin")
    assert storm_slice(b, cd) is None
    b.sp[13260000] = 10
    b.specs[13260000] = (13260010,)
    a = storm_slice(b, cd)
    level = b.effective_levels(cd)[13260000]
    assert a.cooldown == pytest.approx(120 - 2 * (level - 1)) == pytest.approx(2 * cd.cd(13260000, level))
    assert (a.targets, a.reach, a.control) == (4, 4.0, 3.0) and len(STORM_SLICE_FLAT) == 40
    assert STORM_SLICE_FLAT[0] == 518 and STORM_SLICE_FLAT[9] == 1320 and STORM_SLICE_FLAT[39] == 2936
    res, kit, _ = _sim(b, pvp_world("assassin_l45_global_median"))
    assert kit.policy[0] == "storm_slice" and res.casts.get("storm_slice") == 2
    assert res.damage_by["Storm Slice"] > 0
    # a boss gives Defiance no opening: the boss kit has no Storm Slice
    _, _, boss_kit, _ = prepare(b, boss("assassin_l45_global_median"))
    assert "storm_slice" not in boss_kit.actions


def test_the_generic_kits_read_consecutive_uses():
    b = typical_build("assassin")
    _, _, kit, _ = prepare(b, pvp("assassin_l45_global_median"))
    assert kit.actions["flash_slice"].uses == 1
    b.sp[13050000] = 10
    b.specs[13050000] = (13050040,)
    _, _, kit, _ = prepare(b, pvp("assassin_l45_global_median"))
    assert kit.actions["flash_slice"].uses == 2


# ------------------------------------------------------------------------------------------- parries on bosses
def test_a_boss_parries_each_class_at_its_recorded_rate_less_with_accuracy():
    for cls in CLASSES:
        scen = boss(f"{cls}_l45_global_median")
        _, _, _, stats = prepare(typical_build(cls), scen)
        d = stats.derived()
        assert parry_chance(d, scen.target) == pytest.approx(BOSS_PARRY[cls][0], abs=0.0005), cls
        # the training dummy never parries
        _, _, _, plain = prepare(typical_build(cls), dummy(f"{cls}_l45_global_median"))
        assert parry_chance(plain.derived(), dummy().target) == 0.0
    scen = boss("spiritmaster_l45_global_median")
    b = typical_build("spiritmaster")
    _, _, kit, stats = prepare(b, scen)
    more = stats.copy()
    more.add({"accuracy": 20.0})
    assert parry_chance(more.derived(), scen.target) == pytest.approx(
        parry_chance(stats.derived(), scen.target) - 20 * PARRY_PER_ACCURACY, abs=1e-3)
    lots = stats.copy()
    lots.add({"accuracy": 500.0})
    assert parry_chance(lots.derived(), scen.target) == 0.0
    base, _, _ = _sim(b, scen)
    pve = stats.copy()
    pve.add({"pve_accuracy": 40.0})
    res = Sim(pve.derived(), kit.actions, kit.policy, scen.target, scen.config, hooks=kit.hooks,
              cond_mods=kit.cond_mods).run()
    assert res.dps > base.dps * 1.004                                                 # +40 PvE Accuracy: about +0.7 %
    # PvE Accuracy is not Accuracy against players
    pvp_stats = stats.copy()
    pvp_stats.pvp = True
    pvp_stats.add({"pve_accuracy": 40.0})
    assert pvp_stats.derived().accuracy == pytest.approx(stats.copy().derived().accuracy * 1.0, rel=0.2)
