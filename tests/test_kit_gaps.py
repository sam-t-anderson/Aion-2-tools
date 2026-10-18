"""Kit gaps the recorded action times exposed (0.2.309): the Spiritmaster's summon cycle with
Dimensional Control and Elemental Fusion as presses, Smashing Blow only after Rending Blow, the
Cleric's Thunder and Lightning step and Condemnation / Chain of Torment specializations, and the
basic-attack steps woven between skills."""
from dataclasses import replace

import pytest

from aion2calc.kit.base import ClassData
from aion2calc.opt.rotation import with_essentials
from aion2calc.run import prepare
from aion2calc.scenarios import dummy, typical_build
from aion2calc.sim.engine import Sim


def _sim(cls, policy=None, *, build=None, duration=120.0, derived=None):
    scen = dummy(f"{cls}_l45_global_median")
    scen = replace(scen, config=replace(scen.config, duration=duration))
    _, _, kit, stats = prepare(build or typical_build(cls), scen)
    sim = Sim(derived or stats.derived(), kit.actions, policy or kit.policy, scen.target, scen.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim, sim.run(), kit


def test_spiritmaster_presses_its_summons_and_the_windows_they_open():
    sim, res, kit = _sim("spiritmaster")
    for key in ("summon_fire", "summon_earth", "summon_water", "summon_wind", "dimensional_control",
                "elemental_fusion"):
        assert res.casts.get(key, 0) > 0, key
    # every summon is pressed on its cooldown, not spammed (15 s, less Cooldown Reduction)
    assert 6 <= res.casts["summon_fire"] <= 9
    # the Spirits' skills are the summon skills (credited like the meter does) and drive the presses
    uses = sum(res.hits_by.get(n, 0) for n in ("Summon: Fire Spirit", "Summon: Earth Spirit",
                                                "Summon: Water Spirit", "Summon: Wind Spirit"))
    assert res.casts["dimensional_control"] <= uses + res.hits_by.get("Ancient Spirit Skill", 0) + \
        res.hits_by.get("Summon: Ancient Spirit", 0)
    # four elements per Elemental Fusion, plus the Ancient Spirit's outright grants
    ancient = res.hits_by.get("Ancient Spirit Skill", 0) + res.hits_by.get("Summon: Ancient Spirit", 0)
    assert res.casts["elemental_fusion"] <= uses / 4 + ancient + 1
    # Combustion no longer takes the summon, Dimensional Control and Fusion time (it was ~112/min)
    assert res.casts["combustion"] * 60 / 120 < 85


def test_dimensional_control_needs_a_spirit_skill_and_spends_the_window():
    # without summons (and the Ancient Spirit) no Spirit ever casts, so neither press is possible
    _, res, _ = _sim("spiritmaster", ["dimensional_control", "elemental_fusion", "combustion", "cold_shock"])
    assert res.casts.get("dimensional_control", 0) == 0
    assert res.casts.get("elemental_fusion", 0) == 0
    assert "Spirit's Descent" not in res.damage_by        # only within 10 s of a summon
    # one summon opens one window: a single Dimensional Control, however high it sits in the priority
    sim, res, _ = _sim("spiritmaster", ["dimensional_control", "summon_wind", "combustion", "cold_shock"],
                       duration=8.0)
    assert res.casts["summon_wind"] == 1
    assert res.casts.get("dimensional_control", 0) == 1


def test_spirit_hits_do_not_feed_the_casters_procs():
    from aion2calc.kit.spiritmaster import build_kit
    b = typical_build("spiritmaster")
    kit = build_kit(b, ClassData("spiritmaster"))
    _, res, _ = _sim("spiritmaster", ["summon_fire", "summon_earth", "summon_water", "summon_wind", "cold_shock"])
    caster_hits = res.hits_by.get("Cold Shock", 0)
    # Corrode and Spirit's Descent each have a 1 s internal cooldown and fire on the caster's hits only
    assert res.hits_by.get("Corrode", 0) <= caster_hits
    assert res.hits_by.get("Spirit's Descent", 0) <= caster_hits
    assert kit.essential == ("dimensional_control", "elemental_fusion", "summon_fire", "summon_earth",
                             "summon_water", "summon_wind")


def test_a_saved_priority_list_from_before_the_summons_gets_them_back():
    from aion2calc.kit.spiritmaster import build_kit
    kit = build_kit(typical_build("spiritmaster"), ClassData("spiritmaster"))
    old = ["soul_cry", "ancient_spirit", "jointstrike_curse", ("combustion", "mp_hi")]
    assert with_essentials(old, kit) == list(kit.essential) + old
    # a list made with the summons is the optimizer's own and stays as it is, even with one dropped
    new = ["summon_fire", "dimensional_control", "combustion"]
    assert with_essentials(new, kit) == new
    # kits without essential actions are untouched
    from aion2calc.kit.sorcerer import build_kit as sorc
    skit = sorc(typical_build("sorcerer"), ClassData("sorcerer"))
    assert with_essentials(["blaze"], skit) == ["blaze"]
    # and the planner's replay of a build saved before the summons does the same
    from aion2calc.report import build_from_summary
    import json
    summary = json.loads(open("results/compare/spiritmaster/build.json", encoding="utf-8").read())
    summary["policy"] = ["soul_cry", "ancient_spirit", "jointstrike_curse", "enhance", "siphon", "jdestruct",
                         "combustion"]
    b, policy = build_from_summary(summary)
    essential = list(build_kit(b, ClassData("spiritmaster")).essential)
    assert essential and policy[:len(essential)] == essential


def test_smashing_blow_only_follows_rending_blow():
    sim, res, kit = _sim("gladiator")
    assert kit.filler == "keen_strike" and kit.actions["keen_strike"].is_filler
    assert not kit.actions["basic_combo"].is_filler
    assert res.casts["basic_combo"] <= res.casts["rending_blow"]
    last_rend, spent = None, True
    for t, key in res.timeline:
        if key == "rending_blow":
            last_rend, spent = t, False
        elif key == "basic_combo":
            assert last_rend is not None and not spent and t - last_rend <= sim.cfg.chain_window + 1e-9
            spent = True
    # with nothing to follow, Smashing Blow is never pressed
    _, res, _ = _sim("gladiator", ["basic_combo", "keen_strike"])
    assert res.casts.get("basic_combo", 0) == 0
    # the basic chain pressed on its own walks its three steps
    assert {"Keen Strike", "Rupture Strike", "Wrathful Strike"} <= set(res.damage_by)


def test_thunder_and_lightning_follows_earths_retribution():
    sim, res, kit = _sim("cleric", ["thunder_and_lightning", "earths_retribution"])
    assert res.casts["thunder_and_lightning"] > 0
    prev = None
    for _, key in res.timeline:
        if key == "thunder_and_lightning":
            assert prev == "earths_retribution"
        prev = key
    _, res, _ = _sim("cleric", ["thunder_and_lightning", "condemnation", "chain_of_torment", "bolt",
                                "judgment_thunder"])
    assert res.casts.get("thunder_and_lightning", 0) == 0


def test_condemnation_resets_on_crits_and_chain_of_torment_specs():
    base = typical_build("cleric")
    reset = typical_build("cleric")
    reset.specs = {17350000: (17350020, 17350040)}
    scen = dummy("cleric_l45_global_median")
    _, _, _, stats = prepare(base, scen)
    crit = replace(stats.derived(), crit_stat=2000.0)           # a high-crit Cleric
    pol = ["chain_of_torment", "condemnation", "earths_retribution"]
    _, plain, _ = _sim("cleric", pol, build=base, derived=crit)
    _, with_reset, _ = _sim("cleric", pol, build=reset, derived=crit)
    assert with_reset.casts["condemnation"] > 1.5 * plain.casts["condemnation"]
    # +3 s Damage over Time and the halved interval each add Chain of Torment ticks
    longer = typical_build("cleric")
    longer.specs = {17070000: (17070020,)}
    faster = typical_build("cleric")
    faster.specs = {17070000: (17070050,)}
    faster.bonus = {17070000: 3}                                 # the spec unlocks at skill level 16
    pol = ["chain_of_torment", "earths_retribution"]
    ticks = {name: _sim("cleric", pol, build=b)[1].hits_by["Chain of Torment (DoT)"]
             for name, b in (("base", base), ("longer", longer), ("faster", faster))}
    assert ticks["longer"] > ticks["base"]
    assert ticks["faster"] > 1.8 * ticks["base"]


@pytest.mark.parametrize("cls, filler, step", [
    ("gladiator", "keen_strike", "Keen Strike"), ("spiritmaster", "cold_shock", "Cold Shock"),
    ("sorcerer", "flame_arrow", "Flame Arrow"), ("chanter", "onslaught", "Onslaught"),
    ("assassin", "quick_slice", "Quick Slice"), ("ranger", "snipe", "Snipe"),
    ("templar", "vicious_strike", "Vicious Strike")])
def test_woven_steps_land_whole_at_the_recorded_rate(cls, filler, step):
    from aion2calc.run import kit_module
    weave = kit_module(cls).WEAVE
    sim, res, kit = _sim(cls)
    woven = {n: res.hits_by.get(f"{n} (woven)", 0) for n, _, _ in weave["steps"]}
    expected = sum(c * weave["after"].get(k, weave["per_press"]) for k, c in res.casts.items() if k != filler)
    # the boss-fight rate per press, landed as whole steps (the remainder carries over)
    assert sum(woven.values()) == pytest.approx(expected, abs=1.0)
    assert woven[step] > 0
    # each woven step is one full hit of its step, not a fraction spread over every press
    s1 = res.damage_by[f"{step} (woven)"] / woven[step]
    assert s1 > 0.5 * res.damage_by.get(step, s1 * woven[step]) / max(1, res.hits_by.get(step, woven[step]))


def test_the_cleric_weaves_nothing():
    # the recorded Cleric wove one step in a hundred presses
    from aion2calc.kit import cleric
    assert not hasattr(cleric, "WEAVE")
    _, res, _ = _sim("cleric")
    assert not any(n.endswith("(woven)") for n in res.damage_by)
