"""The Templar kit measured from the log server's uploads (0.2.315): Punishing Strike as Pummel's
chain press, the basic-attack chain one step a press, Doom Shield's Judgment window and knockdown,
and the trigger windows read from the tooltips."""
from dataclasses import replace

import pytest

from aion2calc.kit import templar
from aion2calc.kit.base import ClassData
from aion2calc.opt.rotation import with_essentials
from aion2calc.run import prepare
from aion2calc.scenarios import dummy, typical_build
from aion2calc.sim.engine import Sim


def _sim(policy=None, *, build=None, duration=120.0):
    scen = dummy("templar_l45_global_median")
    scen = replace(scen, config=replace(scen.config, duration=duration))
    _, _, kit, stats = prepare(build or typical_build("templar"), scen)
    sim = Sim(stats.derived(), kit.actions, policy or kit.policy, scen.target, scen.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim.run(), kit


def test_punishing_strike_follows_pummel_once_per_press():
    res, _ = _sim(["punishing_strike", "vicious_strike"])
    assert res.casts.get("punishing_strike", 0) == 0             # nothing opens it without Pummel
    res, kit = _sim(["punishing_strike", "pummel", "vicious_strike"])
    pummels, strikes = res.casts["pummel"], res.casts["punishing_strike"]
    assert 0.9 * pummels <= strikes <= pummels                  # one per Pummel: the press spends the window
    # its measured share of Pummel's press (three strikes for the tooltip's damage)
    per = res.damage_by["Punishing Strike"] / res.hits_by["Punishing Strike"]
    assert per == pytest.approx(templar.ASSUME["punishing_frac"] * res.damage_by["Pummel"] / res.hits_by["Pummel"], rel=0.15)
    assert kit.actions["punishing_strike"].skill_id == templar.PUNISHING_STRIKE


def test_the_basic_chain_is_one_step_a_press():
    res, kit = _sim(["vicious_strike"], duration=30.0)
    steps = [res.hits_by.get(name, 0) for name, _, _ in templar.WEAVE["steps"]]
    assert sum(steps) == res.casts["vicious_strike"]
    assert max(steps) - min(steps) <= 1                         # Vicious -> Decisive -> Desperate in turn
    assert kit.actions["vicious_strike"].cast == templar.TIMING["vicious_strike"]


def test_the_rotation_fires_judgment_and_punishing_strike():
    # the kit dealt all three chain steps in one 0.8 s action, which outdamaged everything: the
    # optimized rotation pressed nothing else and never fired Judgment
    res, _ = _sim()
    for key in ("judgment", "punishing_strike", "pummel", "punishment"):
        assert res.casts.get(key, 0) > 0, key
    shares = res.shares()
    basic = sum(v for k, v in shares.items() if k.split(" (")[0] in {n for n, _, _ in templar.WEAVE["steps"]})
    assert basic < 0.35
    assert any(k.endswith("(woven)") for k in shares)


def test_doom_shield_opens_judgment_and_knocks_down():
    build = typical_build("templar")
    assert templar.SID["DOOM"] in build.stigmas
    res, _ = _sim(["judgment", "doom", "vicious_strike"], build=build, duration=60.0)
    assert res.casts.get("judgment", 0) > 0                     # the only trigger in the list
    res, _ = _sim(["annihilate", "doom", "vicious_strike"], build=build, duration=60.0)
    assert res.casts.get("annihilate", 0) > 0                   # its knockdown opens Annihilate


def test_trigger_windows_come_from_the_tooltips():
    cd = ClassData("templar")
    assert templar._judgment_window(cd, templar.SID["SMITE"], 10) == pytest.approx(2.0)
    assert templar._judgment_window(cd, templar.SID["WARD"], 10) == pytest.approx(2.0)
    assert templar._judgment_window(cd, templar.SID["SRUSH"], 10) == pytest.approx(2.0)
    assert templar._judgment_window(cd, templar.SID["DOOM"], 6) == pytest.approx(3.0)
    assert templar._judgment_window(cd, templar.SID["PUM"], 10) == templar.ASSUME["judgment_window"]


def test_pummel_costs_mp_and_vicious_strikes_fourth_spec_cuts_warding_strike():
    cd = ClassData("templar")
    build = typical_build("templar")
    kit = templar.build_kit(build, cd)
    level = build.effective_levels(cd)[templar.SID["PUM"]]
    assert kit.actions["pummel"].mp == pytest.approx(cd.mp(templar.SID["PUM"], level))
    cheaper = typical_build("templar")
    cheaper.specs = {templar.SID["PUM"]: (templar.SID["PUM"] + 10,)}
    assert templar.build_kit(cheaper, cd).actions["pummel"].mp == pytest.approx(0.8 * kit.actions["pummel"].mp)
    # "-2s [Warding Strike] cooldown on hit" is Vicious Strike's fourth spec; the second absorbs HP
    pol = ["warding_strike", "vicious_strike"]
    wardings = {}
    for idx in (2, 4):
        b = typical_build("templar")
        b.specs = {templar.SID["VIC"]: (templar.SID["VIC"] + 10 * idx,)}
        wardings[idx] = _sim(pol, build=b)[0].casts["warding_strike"]
    assert wardings[4] > wardings[2]


def test_a_saved_list_from_before_punishing_strike_gets_it():
    kit = templar.build_kit(typical_build("templar"), ClassData("templar"))
    old = ["afury", "punishment", "annihilate", "judgment", "pummel", "vicious_strike"]
    assert with_essentials(old, kit)[0] == "punishing_strike"
    assert with_essentials(kit.policy, kit) == kit.policy


# ---------------------------------------------------------------- 0.2.320: the guide's support stigmas
from aion2calc.scenarios import boss  # noqa: E402


def _kit_with(stigmas=None, specs=None):
    cd = ClassData("templar")
    build = typical_build("templar")
    if stigmas is not None:
        build.stigmas = stigmas
    if specs is not None:
        build.specs = specs
    return templar.build_kit(build, cd), build


def _boss_sim(policy, *, build, duration=120.0):
    scen = boss("templar_l45_global_median")
    scen = replace(scen, config=replace(scen.config, duration=duration))
    _, _, kit, stats = prepare(build, scen)
    sim = Sim(stats.derived(), kit.actions, policy, scen.target, scen.config, hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim, sim.run()


def test_taunts_shrink_lowers_the_targets_damage_tolerance_from_stigma_level_5():
    taunt = templar.SID["TAUNT"]
    weak, _ = _kit_with({taunt: 3})
    strong, build = _kit_with({taunt: 15})
    assert strong.actions["taunt"].cooldown == pytest.approx(weak.actions["taunt"].cooldown - 5.0)   # -5 s at 15
    build.stigmas = {taunt: 15}
    sim, _ = _boss_sim(["taunt", "vicious_strike"], build=build, duration=5.0)
    shrink = sim.debuffs["shrink"]
    assert shrink.stats == {"tol_red": 0.10} and shrink.until > 14.0      # 15 s from the first press
    build.stigmas = {taunt: 3}
    sim, _ = _boss_sim(["taunt", "vicious_strike"], build=build, duration=5.0)
    assert "shrink" not in sim.debuffs


def test_noble_armor_multiplies_insulting_roar_and_fury_by_one_and_a_half():
    noble = templar.SID["NOBLE"]
    kit, build = _kit_with({noble: 15})
    sim, _ = _boss_sim(["noble", "vicious_strike"], build=build, duration=3.0)
    stats = sim.buffs["noble_armor"].stats
    cd = ClassData("templar")
    lv = build.effective_levels(cd)
    roar = cd.vals(templar.SID["ROAR"], lv[templar.SID["ROAR"]])[1] / 100.0
    fury = cd.vals(templar.SID["FURY"], lv[templar.SID["FURY"]])[0] / 100.0
    assert stats["attack_pct"] == pytest.approx(0.5 * roar) and stats["front_amp"] == pytest.approx(0.5 * fury)
    kit, _ = _kit_with({noble: 5})
    assert "noble" in kit.actions                               # the action exists; the x1.5 comes at 10 and 15
    sim, _ = _boss_sim(["noble", "vicious_strike"], build=_kit_with({noble: 5})[1], duration=3.0)
    assert sim.buffs["noble_armor"].stats == {}


def test_furys_block_buff_counts_in_a_boss_fight_only():
    kit, build = _kit_with()
    cd = ClassData("templar")
    fury = cd.vals(templar.SID["FURY"], build.effective_levels(cd)[templar.SID["FURY"]])[1] / 100.0
    sim, _ = _boss_sim(["vicious_strike"], build=build, duration=2.0)
    assert sim.target.party_damage
    assert sim.stat_mods(sim.t)["amp"] == pytest.approx(fury * templar.ASSUME["fury_block_uptime"])
    # a dummy never attacks, so the Templar never blocks there
    scen = dummy("templar_l45_global_median")
    _, _, kit, stats = prepare(build, scen)
    dummy_sim = Sim(stats.derived(), kit.actions, ["vicious_strike"], scen.target, scen.config,
                    hooks=kit.hooks, cond_mods=kit.cond_mods)
    assert not scen.target.party_damage and "amp" not in dummy_sim.stat_mods(0.0)


def test_pummels_fourth_spec_cuts_punishments_cooldown():
    pum = templar.SID["PUM"]
    pol = ["punishment", "pummel", "vicious_strike"]
    counts = {}
    for idx in (3, 4):
        _, b = _kit_with(specs={pum: (pum + 10 * idx,)})
        counts[idx] = _sim(pol, build=b)[0].casts["punishment"]
    assert counts[4] > counts[3]


def test_woven_vicious_strikes_carry_its_specializations():
    vic = templar.SID["VIC"]
    pol = ["warding_strike", "pummel", "vicious_strike"]        # Pummel weaves basic-chain steps after it
    wardings = {}
    for idx in (2, 4):
        _, b = _kit_with(specs={vic: (vic + 10 * idx,)})
        wardings[idx] = _sim(pol, build=b)[0].casts["warding_strike"]
    assert wardings[4] > wardings[2]                            # -2 s Warding Strike per woven Vicious Strike too


def test_shield_rush_comes_no_oftener_than_after_the_recorded_dodges():
    kit, build = _kit_with()
    assert kit.actions["shield_rush"].cooldown == pytest.approx(60.0 / templar.ASSUME["shield_rush_per_minute"])
    assert not kit.actions["shield_rush"].affected_by_cdr
    res, _ = _sim(["shield_rush", "judgment", "vicious_strike"], build=build)
    assert res.casts.get("shield_rush", 0) <= 2                 # 120 s at 0.93 a minute


def test_battlefield_banners_specializations_last_as_long_as_it():
    banner = templar.SID["BANNER"]
    _, build = _kit_with({banner: 10})
    sim, _ = _boss_sim(["banner", "vicious_strike"], build=build, duration=3.0)
    assert sim.buffs["battlefield_banner"].stats == {"multihit": 0.10, "weapon_amp": 0.10}


def _spec(key, idx):
    sid = templar.SID[key]
    return {sid: (sid + 10 * idx,)}


def test_annihilates_third_spec_doubles_it_on_a_dungeon_boss_only():
    # "+100% damage to targets with Incapacitated Immunity": recorded Annihilates on bosses deal twice the hit
    pol = ["shield_smite", "annihilate", "vicious_strike"]
    per_press = {}
    for idx in (2, 3):
        _, build = _kit_with(specs=_spec("ANNI", idx))
        build.sp[templar.SID["ANNI"]] = 10                          # the typical build's level 4 has no specs
        _, boss_res = _boss_sim(pol, build=build, duration=30.0)
        dummy_res, _ = _sim(pol, build=build, duration=30.0)
        per_press[idx] = [r.damage_by["Annihilate"] / r.casts["annihilate"] for r in (boss_res, dummy_res)]
    assert per_press[3][0] == pytest.approx(2.0 * per_press[2][0])
    assert per_press[3][1] == pytest.approx(per_press[2][1])        # a training dummy is taken not to have it


def test_punishments_second_spec_ticks_six_times_in_three_seconds():
    pol = ["punishment", "vicious_strike"]
    _, build = _kit_with(specs=_spec("PUNISH", 2))
    res, _ = _sim(pol, build=build, duration=10.0)
    assert res.casts["punishment"] == 1 and res.hits_by["Punishment (DoT)"] == 6
    tick = res.damage_by["Punishment (DoT)"] / 6
    assert 0.03 < tick / res.damage_by["Punishment"] < 0.08        # 0.076 of a plain hit; the press can crit
    _, build = _kit_with(specs=_spec("PUNISH", 1))
    res, _ = _sim(pol, build=build, duration=10.0)
    assert "Punishment (DoT)" not in res.hits_by


def test_a_basic_step_restores_what_the_gladiators_step_was_measured_to():
    assert templar.ASSUME["step_mp"] == 150                         # the tooltip says 100
    for idx, gained in ((2, 150), (1, 180)):                         # +20% with its first spec
        _, build = _kit_with(specs=_spec("VIC", idx))
        scen = dummy("templar_l45_global_median")
        scen = replace(scen, config=replace(scen.config, duration=0.3))
        _, _, kit, stats = prepare(build, scen)
        sim = Sim(stats.derived(), kit.actions, ["vicious_strike"], scen.target, scen.config,
                  hooks=kit.hooks, cond_mods=kit.cond_mods, mp_start=0.0)
        sim.run()
        assert sim.casts["vicious_strike"] == 1
        assert sim.mp == pytest.approx(gained + stats.derived().mp_regen * 0.3)
