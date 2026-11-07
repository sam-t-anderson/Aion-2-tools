"""Kit gaps the recorded action times exposed (0.2.309): the Spiritmaster's summon cycle with
Dimensional Control and Elemental Fusion as presses, Smashing Blow only after Rending Blow, the
Cleric's Thunder and Lightning step and Condemnation / Chain of Torment specializations, and the
basic-attack steps woven between skills."""
from dataclasses import replace

import pytest

from aion2calc.kit.base import ClassData
from aion2calc.opt.rotation import with_essentials
from aion2calc.run import prepare
from aion2calc.scenarios import boss, dummy, typical_build
from aion2calc.sim.engine import Action, Sim, SimConfig, Target


def _sim(cls, policy=None, *, build=None, duration=120.0, derived=None, scen=None):
    scen = scen or dummy(f"{cls}_l45_global_median")
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


def _assassin(stigmas=None, specs=None, bonus=None, sp=None):
    b = typical_build("assassin")
    if stigmas is not None:
        b.stigmas = dict(stigmas)
    if sp:
        b.sp = {**b.sp, **sp}
    if specs:
        b.specs = {**b.specs, **specs}
    if bonus:
        b.bonus = {**b.bonus, **bonus}
    return b


def test_heart_gore_comes_back_on_a_crit_and_has_no_cooldown_under_illusive_clone():
    """The Assassin measured from the log server (0.2.368): Heart Gore's Lv 16 effect resets its cooldown on a crit,
    and Illusive Clone removes the cooldown while it lasts, so the kit presses it at the recorded cadence instead of
    once every five seconds. The clone's damage is its tooltip's fifth of every active skill's hit, its own hits and
    the Lv 20 Clone Attack hits (0.2.383): 20.8-21.2 % of the damage dealt in its windows, recorded."""
    hgore = 13350000
    plain = _assassin(stigmas={})
    reset = _assassin(stigmas={}, specs={hgore: (13350040, 13350050)}, bonus={hgore: 6})     # Lv 16 for the reset
    scen = dummy("assassin_l45_global_median")
    _, _, _, stats = prepare(plain, scen)
    crit = replace(stats.derived(), crit_stat=1800.0)                                       # a high-crit Assassin
    pol = ["heart_gore", "quick_slice"]
    _, base, _ = _sim("assassin", pol, build=plain, derived=crit)
    _, with_reset, _ = _sim("assassin", pol, build=reset, derived=crit)
    assert with_reset.casts["heart_gore"] > 1.4 * base.casts["heart_gore"]
    assert "Illusive Clone" not in with_reset.damage_by
    clone = _assassin(stigmas={13310000: 20})
    traced = replace(scen, config=replace(scen.config, record_damage=True))
    _, res, kit = _sim("assassin", ["illusive_clone", "heart_gore", "quick_slice"], build=clone, derived=crit,
                       scen=traced)
    # 60 s since the global patch of 28 October 2026 (90 s before): it comes back twice in the 120 s fight
    assert kit.actions["illusive_clone"].cooldown == 60.0 and res.casts["illusive_clone"] >= 3
    assert res.casts["heart_gore"] > 1.4 * base.casts["heart_gore"]
    windows = [(t, t + 20.0) for t, key in res.timeline if key == "illusive_clone"]             # Lv 20: 20 s
    inside = sum(d for t, d in res.damage_events if any(lo <= t < hi for lo, hi in windows))
    clone_damage = res.damage_by["Illusive Clone"] + res.damage_by["Clone Attack"]
    assert 0.18 < clone_damage / inside < 0.23                            # a fifth of the damage in its windows
    assert 0.05 < clone_damage / res.total < 0.12                         # for 20 s in 60
    assert res.damage_by["Clone Attack"] > 0                              # the Lv 20 extra hits on crits


def test_illusive_clone_echoes_a_fifth_of_every_active_skills_hit():
    """0.2.383: inside an Illusive Clone window every hit of an active skill is followed by a hit of the tooltip's 20 %
    of it (recorded 0.198-0.201, one to a hit), Storm Rampage's and the woven basic steps' too, and never a passive's
    proc or a damage-over-time tick. The model counts it as the clone's, besides the clone's own hits (``clone_echo``)
    and Clone Attack (``clone_attack_echo``), which echo every hit; a recorded fight credits it to the skill it echoes,
    and the comparisons with recorded fights do too (``SimResult.as_recorded``)."""
    from aion2calc.kit.assassin import ASSUME
    storm = 13340000
    b = _assassin(stigmas={13310000: 20}, specs={storm: (13340040, 13340050)}, sp={storm: 10}, bonus={storm: 6})
    scen = boss("assassin_l45_global_median")
    # a stagger inside the clone's first 20 s, and the fight no longer than that: every hit lands in the window
    scen = replace(scen, target=replace(scen.target, stagger_windows=((1.0, 9.0),), hp_model="linear"),
                   config=replace(scen.config, duration=19.5))
    pol = ["illusive_clone", "storm_rampage", "heart_gore", "insignia_explosion", "savage_roar", "quick_slice"]
    _, res, kit = _sim("assassin", pol, build=b, duration=19.5, scen=scen)
    echoed = res.echo_of["Illusive Clone"]
    assert {"Storm Rampage", "Heart Gore", "Savage Roar", "Savage Smash"} <= set(echoed)
    assert any(name.endswith("(woven)") for name in echoed)                # the steps woven after the train
    for name, v in echoed.items():
        assert v == pytest.approx(0.20 * res.damage_by[name], rel=1e-9), name
    procs = ("Exploit Weakness", "Ambush Stance", "Determination", "Apply Poison")
    assert all(name in res.damage_by for name in procs)
    assert not set(procs) & set(echoed)
    # the clone's own hits and Clone Attack: shares of every hit's damage, procs and ticks included
    landed = sum(v for name, v in res.damage_by.items() if name not in ("Illusive Clone", "Clone Attack"))
    own = res.damage_by["Illusive Clone"] - sum(echoed.values())
    assert own == pytest.approx(ASSUME["clone_echo"] * landed, rel=1e-9)
    assert res.damage_by["Clone Attack"] == pytest.approx(ASSUME["clone_attack_echo"] * landed, rel=1e-9)
    # credited as a recorded fight credits it: the echo with its skill, the clone's own hits under its name
    recorded = res.as_recorded()
    assert recorded["Heart Gore"] == pytest.approx(1.2 * res.damage_by["Heart Gore"], rel=1e-9)
    assert recorded["Illusive Clone"] == pytest.approx(own, rel=1e-9)
    assert sum(recorded.values()) == pytest.approx(res.total, rel=1e-9)
    assert sum(res.recorded_shares().values()) == pytest.approx(1.0)
    from aion2calc.calibrate import _sim_shares                            # compared with recorded shares
    clone = _assassin(stigmas={13310000: 20})
    _, plain, _ = _sim("assassin", build=clone, duration=180.0)            # the same dummy fight and priority
    assert _sim_shares("assassin", build=clone) == pytest.approx(plain.recorded_shares(), rel=1e-9)
    assert plain.recorded_shares()["Illusive Clone"] < 0.5 * plain.shares()["Illusive Clone"]


def test_an_echo_skips_the_tagged_hits_and_keeps_its_own_key():
    """``Sim.echo``: an echo deals its share of every hit that lands while it lasts, except hits with a ``skip`` tag;
    two echoes may share a name under their own keys, and a second call with a key replaces the first."""
    from aion2calc.scenarios import typical_build as tb
    _, _, _, stats = prepare(tb("assassin"), dummy("assassin_l45_global_median"))

    def cast(sim, a):
        if sim.t < 1e-9:
            sim.echo("Clone", 0.2, 5.0, skip=("proc", "dot"), key="fifth", as_source=True)
            sim.echo("Clone", 0.1, 5.0)
            sim.echo("Clone", 0.05, 5.0)                                   # replaces the 0.1 one (the same key)
        sim.hit("Strike", 1000.0, 0.0)
        sim.hit("Proc", 1000.0, 0.0, tags=("proc",))
    actions = {"x": Action("x", "X", 1, 1.0, on_cast=cast)}
    sim = Sim(stats.derived(), actions, ["x"], Target(), SimConfig(duration=10.0))
    res = sim.run()
    hit = res.damage_by["Strike"] / res.hits_by["Strike"]
    inside = sum(1 for t, _ in res.timeline if t <= 5.0)                  # the hits land as cast; the echoes end at 5 s
    assert 4 <= inside < res.casts["x"]
    # the fifth on the strikes only, the other echo (0.05, the 0.1 replaced) on the strikes and the procs alike
    assert res.damage_by["Clone"] == pytest.approx(inside * hit * (0.2 + 0.05 + 0.05), rel=1e-9)
    assert res.echo_of == {"Clone": {"Strike": pytest.approx(inside * hit * 0.2, rel=1e-9)}}


def test_triniels_dagger_and_swift_contract_grow_at_their_stigma_steps():
    """Triniel's Dagger Lv 10 takes a tenth off every cooldown on hit, so Illusive Clone comes back sooner; Swift
    Contract Lv 10 and 15 raise Rear Smite and Assault Stance by half for its duration (the stigma levels the
    recorded Assassin ranks first, 0.2.368)."""
    iclone, triniel, swift = 13310000, 13300000, 13390000
    second = {}
    for level in (9, 10):
        _, res, _ = _sim("assassin", ["illusive_clone", "triniel", "quick_slice"], duration=240.0,
                         build=_assassin(stigmas={iclone: 20, triniel: level}))
        second[level] = [t for t, key in res.timeline if key == "illusive_clone"][1]
    assert second[10] < second[9] - 10.0                                   # two Triniel hits before it, 9 s each
    dps = {}
    for level in (9, 10, 15):
        _, res, _ = _sim("assassin", ["swift", "quick_slice"], build=_assassin(stigmas={swift: level}))
        dps[level] = res.total
    assert dps[9] < dps[10] < dps[15]


def test_savage_roar_brings_its_chain_steps_and_determination_procs_late_in_the_fight():
    """The recorded Assassin's chain records open Savage Back Kick after Savage Roar and Savage Smash after that
    (567 and 548 chains; a Savage Fang opens nothing), each step about as much damage again as the Roar."""
    _, res, kit = _sim("assassin", ["savage_roar", "quick_slice"])
    assert res.casts["savage_roar"] >= 10
    roar, kick, smash = res.damage_by["Savage Roar"], res.damage_by["Savage Back Kick"], res.damage_by["Savage Smash"]
    assert 0.9 < kick / roar < 1.3 and 0.9 < smash / roar < 1.35          # measured 1.10 and 1.12
    assert res.hits_by["Savage Back Kick"] == 4 * res.casts["savage_roar"]
    assert kit.actions["savage_roar"].cast > 2.0                           # the Roar and its two chain presses
    fang = _assassin(stigmas={13270000: 15})
    _, res, _ = _sim("assassin", ["sfang", "quick_slice"], build=fang)
    assert res.casts["sfang"] >= 2 and "Savage Smash" not in res.damage_by
    # Determination: a hit on a target under its HP threshold, once a second, late in a boss fight
    _, res, _ = _sim("assassin", ["quick_slice"], duration=180.0, scen=boss("assassin_l45_global_median"))
    assert res.damage_by["Determination"] > 0
    # Exploit Weakness's clones proc on crits throughout
    assert res.damage_by["Exploit Weakness"] > 0


def test_a_staggered_boss_takes_critical_hits():
    """Measured from the recorded Assassin (0.2.368): 89–98 % of the hits inside a stagger crit, 50 % outside,
    every skill alike; the engine lands every hit in a stagger window as a crit, for every class."""
    _, _, _, stats = prepare(typical_build("assassin"), dummy("assassin_l45_global_median"))
    actions = {"x": Action("x", "X", 1, 1.0, on_cast=lambda sim, a: sim.hit("X", 1000.0, 0.0))}
    sim = Sim(stats.derived(), actions, ["x"], Target(stagger_windows=((10.0, 20.0),)),
              SimConfig(duration=30.0, record_damage=True))
    sim.run()
    outside = [d for t, d in sim.damage_events if not 10.0 <= t < 20.0]
    inside = [d for t, d in sim.damage_events if 10.0 <= t < 20.0]
    assert inside and outside and max(outside) < min(inside)
    sim = Sim(stats.derived(), actions, ["x"], Target(stagger_windows=((10.0, 20.0),), stagger_crit=False),
              SimConfig(duration=30.0, record_damage=True))
    sim.run()
    assert len({round(d, 6) for t, d in sim.damage_events}) == 1


def test_storm_rampage_fires_in_the_stagger_windows_and_pulls_every_cooldown_in():
    """Storm Rampage, usable only on a staggered boss, lands the recorded Assassins' 19 hits a stagger (0.2.380), with
    its Lv 12 Multi-Hit too: the option lands four extra hits inside each hit's record, 20 % more (the damage model's
    certain Multi-Hit since 0.2.382), where the kit doubled the hits (the hits of a fifth that follow each one in an
    Illusive Clone window are the clone's, on every skill). With its Lv 16 option each hit takes a second off every
    cooldown: the recorded Assassin's Illusive Clone came back every 46 s against its 53 s cooldown (60 s since the
    global patch of 28 October 2026, less the player's 11.1 % Cooldown Reduction; 0.2.368 compared it with 80 s, from
    the 90 s the bundled data still had)."""
    from aion2calc.model.stats import MULTI_HIT_ON_HIT, MULTIHIT_BONUS
    storm, iclone = 13340000, 13310000
    scen = boss("assassin_l45_global_median")
    plain = _assassin(stigmas={iclone: 20}, sp={storm: 10}, bonus={storm: 6})
    multi = _assassin(stigmas={iclone: 20}, specs={storm: (13340040,)}, sp={storm: 10}, bonus={storm: 6})
    full = _assassin(stigmas={iclone: 20}, specs={storm: (13340040, 13340050)}, sp={storm: 10}, bonus={storm: 6})
    pol = ["storm_rampage", "illusive_clone", "heart_gore", "quick_slice"]
    sim, a, _ = _sim("assassin", pol, build=plain, duration=180.0, scen=scen)
    _, m, _ = _sim("assassin", pol, build=multi, duration=180.0, scen=scen)
    _, b, _ = _sim("assassin", pol, build=full, duration=180.0, scen=scen)
    assert a.casts["storm_rampage"] == b.casts["storm_rampage"] == len(scen.target.stagger_windows) == 3
    assert a.hits_by["Storm Rampage"] == m.hits_by["Storm Rampage"] == b.hits_by["Storm Rampage"] == 3 * 19
    # Multi-Hit's four extra hits, against the Multi-Hit chance a hit without the option has
    assert m.damage_by["Storm Rampage"] / a.damage_by["Storm Rampage"] == \
        pytest.approx((1 + MULTI_HIT_ON_HIT) / (1 + sim.base.multihit * MULTIHIT_BONUS), rel=1e-6)
    first_a = [t for t, key in a.timeline if key == "illusive_clone"]
    first_b = [t for t, key in b.timeline if key == "illusive_clone"]
    train = [t for t, key in b.timeline if key == "storm_rampage"]
    # 19 s off its cooldown per stagger: less than that is left of the clone's 60 s when the first train lands, so the
    # clone is pressed as soon as the train ends, and the later windows come earlier too
    assert train[0] < first_b[1] < train[0] + 4.0 < first_a[1]
    assert first_b[2] < first_a[2] - 5.0
    assert "Storm Rampage" not in _sim("assassin", pol, build=full)[1].damage_by      # a dummy never staggers


@pytest.mark.parametrize("cls, key, sid, unlock", [("gladiator", "zikel", 11250000, 15),
                                                    ("ranger", "bowbless", 14220000, 5)])
def test_the_multi_hit_buffs_make_every_multi_hit_whole(cls, key, sid, unlock):
    """0.2.382: while Zikel's Blessing (its Lv 15 option) or Bow of Blessing (Lv 5) lasts, the recorded Gladiators' and
    Rangers' Multi-Hits came about 0.46 more often and 915 of 916 landed all four extra hits, where outside them they
    land one to four: "+50% Multi-Hit chance" adds 0.5 to the chance and values every Multi-Hit at the four, for the
    buff's own duration (10 s and 0.5 s a level), not the 20 s the kit gives its other stats. Below the option's level
    there is none."""
    from aion2calc.kit.common import ms
    from aion2calc.model.stats import MULTIHIT_FULL
    for level in (unlock - 1, unlock, 20):
        b = typical_build(cls)
        b.stigmas = {**b.stigmas, sid: level}
        sim, res, _ = _sim(cls, [key], build=b, duration=1.0)
        assert res.casts[key] == 1
        multi = sim.buffs.get(f"{key}_multihit")
        if level < unlock:
            assert multi is None
            continue
        assert multi.stats == {"multihit": 0.5, MULTIHIT_FULL: 1.0}
        dur = ms(ClassData(cls).vals(sid, level)[-1])
        assert dur == 10.0 + 0.5 * (level - 1) or (level == 20 and dur == 20.0)
        assert multi.until - sim.buffs[key].until == pytest.approx(dur - 20.0)


#: Options the kits read as no Multi-Hit, or as +50 % Multi-Hit chance, until 0.2.382; the recorded hits dealt with each
#: certain one landed four extra hits (Drill Dart 190 of 193, Incandescent Blow 147 of 148 and its Bursting Blow 77 of
#: 77, Rushing Smash 15 of 15, Heat Wave Blow 7 of 7, Wave Blow 44 of 44). (class, action, hits, skill, slot, before)
MULTI_OPTIONS = [("ranger", "drill_dart", ("Drill Dart",), 14050000, 4, ()),
                 ("chanter", "incandescent_blow", ("Incandescent Blow", "Bursting Blow"), 18040000, 5, ()),
                 ("chanter", "rushing_smash", ("Rushing Smash",), 18090000, 5, ()),
                 ("chanter", "heat_wave_blow", ("Heat Wave Blow",), 18150000, 4, ()),
                 ("chanter", "wave_blow", ("Wave Blow",), 18080000, 1, ("impactful_crush",)),
                 ("chanter", "tremor_crush", ("Tremor Crush",), 18210000, 3, ())]


@pytest.mark.parametrize("cls, key, names, sid, slot, before", MULTI_OPTIONS)
def test_every_multi_hit_option_is_worth_its_recorded_extra_hits(cls, key, names, sid, slot, before):
    """0.2.382: "Multi-Hit on hit" and "lands as Multi-Hit" are a certain Multi-Hit on every skill, four extra hits
    (+20 %) with no Multi-Hit chance on top; "+50% Multi-Hit on hit" adds 0.5 to the chance (Tremor Crush's, which
    the Chanter kit left out). Each hit, with the option against without it."""
    from aion2calc.model.stats import MULTI_HIT_ON_HIT, MULTIHIT_BONUS
    per_hit = {}
    for specs in ((), (sid + 10 * slot,)):
        b = typical_build(cls)
        b.sp, b.bonus, b.specs = {**b.sp, sid: 10}, {**b.bonus, sid: 6}, {**b.specs, sid: specs}
        sim, res, _ = _sim(cls, list(before) + [key], build=b, duration=12.0)
        assert res.casts.get(key, 0) >= 1
        per_hit[specs] = {n: res.damage_by[n] / res.hits_by[n] for n in names if res.hits_by.get(n)}
    p = sim.base.multihit
    certain = "Tremor" not in names[0]
    want = (1 + (MULTI_HIT_ON_HIT if certain else (p + 0.5) * MULTIHIT_BONUS)) / (1 + p * MULTIHIT_BONUS)
    plain, multi = per_hit[()], per_hit[(sid + 10 * slot,)]
    assert set(plain) == set(multi) and names[0] in plain
    for n in plain:
        assert multi[n] / plain[n] == pytest.approx(want, rel=1e-6), n


def test_the_specialty_marks_tell_a_modeled_pick_from_a_filler():
    """0.2.368: a chosen effect the model cannot tell from the skill's other open effects is marked free ("either"):
    Storm Rampage's shield and MP restore are, Heart Gore's multi-hit is not."""
    from aion2calc.kit.specialties import describe, free_marks
    storm, hgore = 13340000, 13350000
    b = _assassin(stigmas={}, specs={storm: (13340010, 13340020), hgore: (13350010, 13350040)}, bonus={storm: 6, hgore: 6})
    scen = dummy("assassin_l45_global_median")
    cd, prepared, _, _ = prepare(b, scen)

    def evaluate(build):
        return _sim("assassin", ["heart_gore", "quick_slice"], build=build)[1].dps
    free = free_marks(cd, b, evaluate, levels=prepared.effective_levels(cd))
    assert free[storm] == {13340010, 13340020}
    assert 13350010 in free.get(hgore, set()) and 13350040 not in free.get(hgore, set())
    rows = {r["skill"]: r for r in describe(cd, prepared, free)}
    assert rows["Storm Rampage"]["free"] == 2 and all(e["free"] for e in rows["Storm Rampage"]["effects"] if e["selected"])
    assert rows["Heart Gore"]["free"] == 1
    assert [e["free"] for e in rows["Heart Gore"]["effects"] if e["selected"]] == [True, False]


#: Each class's stagger-only skill and its action (0.2.379): no cooldown, so the generic reading took it for a filler
#: and left it out of the class kits. The Assassin's and the Sorcerer's had their own models until 0.2.380.
STAGGER = {"gladiator": (11280000, "sword_aura_rampage"), "templar": (12340000, "flash_rampage"),
           "assassin": (13340000, "storm_rampage"), "ranger": (14330000, "arrow_scattershot"),
           "sorcerer": (15010000, "flame_scattershot"), "spiritmaster": (16340000, "rapid_scattershot"),
           "cleric": (17370000, "lightning_strike_scattershot"), "chanter": (18300000, "gust_rampage")}


def _staggered(cls, specs=(), level=16):
    """The typical build with the stagger skill trained to 10 and raised to ``level``, with ``specs``."""
    sid, _ = STAGGER[cls]
    b = typical_build(cls)
    b.sp = {**b.sp, sid: 10}
    b.bonus = {**b.bonus, sid: level - 10}
    b.specs = {**b.specs, sid: tuple(specs)}
    return b


def _alone(cls, specs, policy_extra=None, *, derived_mods=None, duration=12.0, mp_start=None):
    """The class kit's stagger action on its own (and ``policy_extra`` in front of it) in a short fight with one
    stagger window, shorter than the action's 8 s, from 1 s on."""
    sid, key = STAGGER[cls]
    _, _, kit, stats = prepare(_staggered(cls, specs), dummy(f"{cls}_l45_global_median"))
    derived = replace(stats.derived(), **(derived_mods or {}))
    actions = {key: kit.actions[key], **{a.key: a for a in (policy_extra or [])}}
    policy = [a.key for a in (policy_extra or [])] + [key]
    sim = Sim(derived, actions, policy, Target(stagger_windows=((1.0, 8.5),)), SimConfig(duration=duration),
              mp_start=mp_start)
    return sim, sim.run(), kit


@pytest.mark.parametrize("cls", sorted(STAGGER))
def test_each_class_presses_its_stagger_skill_once_a_stagger_at_the_recorded_hits(cls):
    """0.2.379: the recorded players press their class's stagger-only skill back to back once their opening skills are
    out, one train of presses a stagger, four hits a press. The kit lands that train once in each of the boss's three
    stagger windows, with the recorded hits a stagger, inside the window, and never on a training dummy."""
    from aion2calc.run import kit_module
    sid, key = STAGGER[cls]
    mod = kit_module(cls)
    scen = boss(f"{cls}_l45_global_median")
    _, res, kit = _sim(cls, build=_staggered(cls), duration=180.0, scen=scen)
    a = kit.actions[key]
    assert a.skill_id == sid and a.requires == ("stagger",) and not a.affected_by_cdr
    assert a.cast == mod.TIMING[key] and a.cooldown == 8.0 and kit.policy[0] == key
    windows = scen.target.stagger_windows
    starts = [t for t, k in res.timeline if k == key]
    assert len(starts) == res.casts[key] == len(windows) == 3
    assert sorted(next(i for i, (s, e) in enumerate(windows) if s <= t < e) for t in starts) == [0, 1, 2]
    assert res.hits_by[a.name] == 3 * round(mod.ASSUME[f"{key}_hits"])
    assert sum(1 for x in kit.actions.values() if x.skill_id == sid) == 1      # the generic reading adds no second one
    _, res, _ = _sim(cls, build=_staggered(cls))
    assert a.name not in res.damage_by                                          # a dummy never staggers


@pytest.mark.parametrize("cls", sorted(STAGGER))
def test_a_stagger_hit_is_the_measured_share_of_the_tooltip(cls):
    """Each hit lands the share of the tooltip's value measured against the class's own reference skill (0.2.379); the
    tooltip split evenly over a press's four hits, as the generic reading deals it, would be 0.25. Without the per-hit
    additions (PvE and Boss Attack, Penetration, Critical Attack) the hits differ by exactly that ratio."""
    from aion2calc.kit import generic
    from aion2calc.run import kit_module
    sid, key = STAGGER[cls]
    bare = {"flat_add": 0.0, "crit_atk": 0.0, "front_atk": 0.0, "back_atk": 0.0}
    _, res, kit = _alone(cls, (), derived_mods=bare, duration=6.0)
    mine = res.damage_by[kit.actions[key].name] / res.hits_by[kit.actions[key].name]
    _, prepared, _, stats = prepare(_staggered(cls), dummy(f"{cls}_l45_global_median"))
    gen = generic.build_kit(prepared, ClassData(cls)).actions[key]
    assert gen.is_filler                                                        # why the kits never took it
    sim = Sim(replace(stats.derived(), **bare), {key: gen}, [key], Target(stagger_windows=((1.0, 8.5),)),
              SimConfig(duration=6.0))
    plain = sim.run()
    split = plain.damage_by[gen.name] / plain.hits_by[gen.name]
    assert mine / split == pytest.approx(kit_module(cls).ASSUME[f"{key}_hit"] / 0.25, rel=1e-6)


@pytest.mark.parametrize("cls", sorted(STAGGER))
def test_the_stagger_skills_options_act_as_their_texts_say(cls):
    """Lv 16 "-1s all skill cooldowns on hit" takes a second off every other cooldown at each hit of the train; Lv 12
    "Multi-Hit on hit" lands four extra hits inside every hit's record, 20 % more (0.2.380: measured; since 0.2.382
    the damage model's value for every certain Multi-Hit, so the helper needs no factor of its own); the Lv 8 MP
    option restores its MP a press, or a hit where its text says "on hit" (the Templar's, the Assassin's and the
    Ranger's)."""
    from aion2calc.model.stats import MULTI_HIT_ON_HIT, MULTIHIT_BONUS
    from aion2calc.run import kit_module
    sid, key = STAGGER[cls]
    n = round(kit_module(cls).ASSUME[f"{key}_hits"])
    probe = Action("probe", "Probe", 1, 0.5, cooldown=100.0)
    for specs, off in (((), 0), ((sid + 50,), n), ((sid + 40, sid + 50), n)):
        sim, res, _ = _alone(cls, specs, [probe])
        assert res.casts["probe"] == 1 and res.casts[key] == 1
        assert sim.ready["probe"] == pytest.approx(100.0 * (1.0 - sim.base.cdr) - off)
    sim, plain, kit = _alone(cls, ())
    _, multi, _ = _alone(cls, (sid + 40,))
    name = kit.actions[key].name
    assert multi.hits_by[name] == plain.hits_by[name] == n
    # four extra hits a hit, against the Multi-Hit chance a hit without the option has
    assert multi.damage_by[name] / plain.damage_by[name] == \
        pytest.approx((1 + MULTI_HIT_ON_HIT) / (1 + sim.base.multihit * MULTIHIT_BONUS), rel=1e-6)
    text = next(x["text"] for x in ClassData(cls).skills[sid]["specs"] if x["id"] == sid + 20)
    mp = {}
    for specs in ((), (sid + 20,)):
        sim, _, _ = _alone(cls, specs, derived_mods={"mp_regen": 0.0, "mp_max": 1e6}, duration=6.0, mp_start=0.0)
        mp[specs] = sim.mp
    per = n if text.endswith("on hit") else -(-n // 4)                          # a hit, or a press of four hits
    assert mp[(sid + 20,)] - mp[()] == pytest.approx(120.0 * per)


def test_the_optimizer_chooses_the_stagger_skills_cooldown_effect():
    """0.2.376's linked-effects search reads every class's "-1s all skill cooldowns on hit" (each stagger skill is a
    group of its own); with the skill simulated it now pays, and the search takes it: a Gladiator's Sword Aura Rampage
    at Lv 16 moves from its shield and mobile options to the cooldown effect."""
    from aion2calc.opt.pipeline import Optimizer
    from aion2calc.scenarios import SCENARIOS
    for cls, (sid, _) in STAGGER.items():
        groups, links = Optimizer(cls, SCENARIOS["boss"](f"{cls}_l45_global_median"), verbose=False)._spec_links()
        assert (sid,) in groups and links[sid] == {sid + 50}, cls
    sid, _ = STAGGER["gladiator"]
    opt = Optimizer("gladiator", SCENARIOS["boss"]("gladiator_l45_global_median"), verbose=False)
    b = _staggered("gladiator", (sid + 10, sid + 30))
    _, _, kit, _ = prepare(b, opt.scenario)
    policy = [k for k in kit.policy if not kit.actions[k].is_filler]
    best, pol = opt.optimize_linked_specs(b, policy, groups=[(sid,)])
    assert sid + 50 in best.specs[sid]
    assert opt.evaluate(best, pol) > 1.03 * opt.evaluate(b, policy)
