"""The damage optimizer undervalued builds and misranked stats (0.2.254-0.2.256).

All-class fixes and per-class calibrations from real parses, pinned here so they do not regress:

* Precision and Freedom were missing from the stat ranking entirely — Precision
  (a crit stat) never appeared. Both are now evaluated for every class.
* Chain follow-ups ("Adds [X] Chain Skill") were modelled at a flat 0.60/0.85x the base; a
  Gladiator parse measured one at ~2.1x and community L45 parses measured chanter Piercing
  Strike 1.65x, sorcerer Winter's Illusion 1.86x and ranger Shackling 1.38x — so the shared
  estimate was raised to 1.5 (0.2.256). These are finishers, not weak taps.
* The Gladiator kit gained the Upward Strike chain at its measured 2.1x, the basic
  attack combo (Smashing Blow, ~15% of real damage and previously unmodelled), a
  Murderous Burst internal cooldown, and a tempo-bound rotation.
* Hand-written kits that modelled a base skill directly silently dropped its chain/variant
  follow-up (the generic chain reader only fires for skills it is left to read). 0.2.256 adds
  the biggest dropped skills from community parses: chanter Piercing Strike (~22%) + Bursting
  Blow (~15%), cleric Divine Punishment (~11%), the assassin Quick Slice basic combo (Swift +
  Breaking Slice) with Savage Roar demoted from a spammed filler to a cadenced upkeep skill,
  and the templar Vicious Strike combo (Decisive + Desperate Strike)."""
from aion2calc.kit.base import Build
from aion2calc.opt.statweights import STAT_STEPS
from aion2calc.run import Scenario, simulate
from aion2calc.sim.engine import SimConfig, Target


def test_precision_and_freedom_are_ranked_for_every_class():
    fields = {f for f, _step, _label in STAT_STEPS}
    # Both were missing before 0.2.254; Precision especially (a crit stat) never showed.
    assert "precision" in fields
    assert "freedom" in fields
    # The full set of deity stats is now covered.
    assert {"might", "destruction", "precision", "death", "wisdom", "justice",
            "time", "illusion", "freedom"} <= fields


def test_chain_followup_coefficient_is_a_finisher_not_a_tap():
    # Community L45 parses (0.2.256) measured "Adds [X] Chain Skill" finishers at ~1.4-1.9x the
    # base hit (chanter Piercing Strike 1.65x, sorcerer Winter's Illusion 1.86x, ranger Shackling
    # 1.38x) — far above the old 0.60/0.85 placeholders that dropped most of a chain's damage.
    from aion2calc.kit import assassin, cleric, ranger, spiritmaster, templar
    from aion2calc.kit.generic import CHAIN_FRAC
    assert CHAIN_FRAC >= 1.4
    for mod in (assassin, cleric, ranger, spiritmaster, templar):
        assert mod.ASSUME["chain_frac"] >= 1.4


def test_chanter_models_its_two_dropped_nukes():
    # Piercing Strike (Dark Crush chain, ~22% of real damage) and Bursting Blow (Incandescent
    # Blow variant, ~15%) were both dropped because the hand-written casts bypassed the generic
    # chain reader; they are now modelled at their measured coefficients.
    from aion2calc.kit.chanter import ASSUME
    assert ASSUME["piercing_frac"] > 1.3
    assert ASSUME["bursting_frac"] > 1.5


def test_cleric_models_divine_punishment():
    from aion2calc.kit.cleric import ASSUME
    assert ASSUME["divine_punishment_frac"] >= 1.0   # Judgment Thunder's companion strike, ~11% of damage


def test_assassin_models_the_basic_combo():
    from aion2calc.kit.assassin import ASSUME
    assert ASSUME["swift_frac"] > 0.5 and ASSUME["breaking_frac"] > 0.5


def _gladiator_build():
    SID = dict(KEEN=11020000, REND=11010000, LEAP=11190000, MOCK=11290000, OVER=11170000,
        SAR=11280000, ANKLE=11200000, CRUSH=11050000, RUSH=11360000, AERIAL=11300000, RUIN=11100000,
        IDENT=11740000, ATKPREP=11750000, IMPACT=11760000, DESTIMP=11770000, EXPCOUNTER=11780000,
        SURVWILL=11790000, MURDER=11800000, BLOOD=11730000, SURV=11710000, PROT=11720000,
        LUNGE=11400000, ZIKEL=11250000, FOCUSBLOCK=11110000, RAGE=11390000)
    sp = {SID[k]: 10 for k in ("KEEN", "REND", "LEAP", "MOCK", "OVER", "ANKLE", "CRUSH", "RUSH",
          "AERIAL", "RUIN", "ATKPREP", "IDENT", "IMPACT", "DESTIMP", "EXPCOUNTER", "MURDER",
          "SURVWILL", "BLOOD")}
    sp[SID["SAR"]] = 2
    b = Build("gladiator")
    b.sp = sp
    b.specs = {SID["OVER"]: (11170030, 11170050), SID["RUIN"]: (11100030, 11100040),
               SID["ANKLE"]: (11200020, 11200040), SID["REND"]: (11010010, 11010040)}
    b.stigmas = {SID["LUNGE"]: 15, SID["ZIKEL"]: 11, SID["RAGE"]: 5}
    b.bonus = {sid: 7 for sid in sp}       # push effective levels up so the high specs unlock
    return b


def test_gladiator_models_upward_strike_and_the_basic_combo():
    b = _gladiator_build()
    res = simulate(b, Scenario(loadout="gladiator_l45_global_median",
                               target=Target(hp_model="dummy"), config=SimConfig(duration=120.0)))
    dmg, hits = res.damage_by, res.hits_by
    # The chain and the basic combo now exist and carry real weight (they did not before).
    assert dmg.get("Upward Strike", 0) > 0, sorted(dmg)
    assert dmg.get("Smashing Blow", 0) > 0, sorted(dmg)
    # Upward Strike is the biggest hit in the rotation, as in a real parse (2.1x Overhead).
    assert dmg["Upward Strike"] / hits["Upward Strike"] > 1.5 * dmg["Overhead Slam"] / hits["Overhead Slam"]
    # Overhead Slam + Upward Strike dominate the single-target rotation.
    assert (dmg["Upward Strike"] + dmg.get("Overhead Slam", 0)) / res.total > 0.4
    # Ruinous Blow is modelled as a multi-strike, so it is a meaningful share (~its
    # measured 7.7%) instead of a single hit — this is what lifts Cooldown Reduction.
    assert dmg.get("Ruinous Blow", 0) / res.total > 0.04


def test_gladiator_upward_chain_uses_the_measured_fraction():
    from aion2calc.kit.gladiator import ASSUME
    assert ASSUME["upward_frac"] > 1.5          # measured ~2.1x; never the old 0.60 placeholder
    assert "knockdown_uses" not in ASSUME       # the dead constant was removed
    assert ASSUME["ruinous_hits"] >= 2          # Ruinous Blow is a multi-strike (lifts Cooldown Reduction)


def test_gladiator_basic_string_sustains_mp_and_skips_crowd_control_on_a_dummy():
    # The basic-attack steps restore MP, woven between skills and pressed on their own (0.2.309;
    # until then a flat restore on Smashing Blow stood in for them), so the MP-costly Rending Blow
    # weaves at a real share instead of starving at 0 MP; and because the basic chain is always
    # available and out-prioritises the low-DPS gap-closers, a dummy rotation skips the
    # crowd-control skills entirely, as a real parse does.
    from aion2calc.kit.gladiator import WEAVE
    assert WEAVE["after"]["rending_blow"] > 0
    b = _gladiator_build()
    res = simulate(b, Scenario(loadout="gladiator_l45_global_median",
                               target=Target(hp_model="dummy"), config=SimConfig(duration=120.0)))
    dmg, total = res.damage_by, res.total
    assert dmg.get("Rending Blow", 0) / total > 0.06    # was ~3.9% when MP-starved
    cc = sum(dmg.get(k, 0) for k in ("Ankle Slice", "Rush Strike", "Mocking Blade",
                                     "Leaping Slam", "Crushing Wave", "Aerial Snare"))
    assert cc / total < 0.03                             # the dummy DPS rotation never needs these


def _dummy(cls, duration=120.0):
    from aion2calc.scenarios import typical_build
    b = typical_build(cls)
    b.bonus = {sid: 7 for sid in b.sp}          # push effective levels so high-unlock specs are active
    return b, Scenario(loadout=f"{cls}_l45_global_median",
                       target=Target(hp_model="dummy"), config=SimConfig(duration=duration))


def test_chanter_piercing_and_bursting_land_when_their_specs_are_on():
    # Both were dropped entirely before 0.2.256 (the hand cast bypassed the generic chain reader).
    b, sc = _dummy("chanter")
    b.specs = {18040000: (18040040,), 18100000: (18100040,)}   # Bursting (Incand), Piercing (Dark Crush)
    dmg = simulate(b, sc).damage_by
    assert dmg.get("Piercing Strike", 0) > 0, sorted(dmg)
    assert dmg.get("Bursting Blow", 0) > 0, sorted(dmg)
    # Bursting Blow lands at ~2.2x Incandescent Blow, so per cast it clearly out-hits it.
    assert dmg["Bursting Blow"] / max(1, dmg.get("Incandescent Blow", 1)) > 0.5


def test_cleric_divine_punishment_rides_judgment_thunder():
    b, sc = _dummy("cleric")
    dmg = simulate(b, sc).damage_by
    assert dmg.get("Divine Punishment", 0) > 0, sorted(dmg)
    # It is roughly as large as Judgment Thunder itself (a real parse put the two near-equal).
    assert dmg["Divine Punishment"] / max(1, dmg.get("Judgment Thunder", 1)) > 0.6


def test_assassin_basic_combo_lands_and_savage_roar_is_not_a_third_of_damage():
    # Savage Roar used to be a second filler and spammed to ~27% of damage; a real parse put it
    # at ~5%. It is now a cadenced Insignia-upkeep skill, and the Quick Slice combo is the filler.
    b, sc = _dummy("assassin")
    res = simulate(b, sc)
    dmg, total = res.damage_by, res.total
    assert dmg.get("Swift Slice", 0) > 0 and dmg.get("Breaking Slice", 0) > 0, sorted(dmg)
    assert dmg.get("Savage Roar", 0) / total < 0.15
