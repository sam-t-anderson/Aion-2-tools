"""The damage optimizer undervalued builds and misranked stats (0.2.254).

Two all-class fixes and a Gladiator calibration, pinned here so they do not regress:

* Precision and Freedom were missing from the stat ranking entirely — Precision
  (a crit stat) never appeared. Both are now evaluated for every class.
* Chain follow-ups were modelled at a flat 0.60x the base hit in every kit; a real
  Gladiator parse measured one at ~2.1x, so the shared estimate was raised to 0.85.
* The Gladiator kit gained the Upward Strike chain at its measured 2.1x, the basic
  attack combo (Smashing Blow, ~15% of real damage and previously unmodelled), a
  Murderous Burst internal cooldown, and a tempo-bound rotation — so its modelled
  dummy damage shares and DPS track a real parse far better."""
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


def test_chain_followup_default_raised_from_the_old_0_60_placeholder():
    from aion2calc.kit import assassin, chanter, cleric, ranger
    from aion2calc.kit.generic import CHAIN_FRAC
    assert CHAIN_FRAC >= 0.80
    for mod in (assassin, chanter, cleric, ranger):
        assert mod.ASSUME["chain_frac"] >= 0.80


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
    dmg = res.damage_by
    # The chain and the basic combo now exist and carry real weight (they did not before).
    assert dmg.get("Upward Strike", 0) > 0, sorted(dmg)
    assert dmg.get("Smashing Blow", 0) > 0, sorted(dmg)
    # Upward Strike is the biggest hit in the rotation, as in a real parse (2.1x Overhead).
    assert dmg["Upward Strike"] >= dmg.get("Overhead Slam", 0)
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
