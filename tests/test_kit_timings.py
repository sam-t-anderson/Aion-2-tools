"""Kit action times measured from recorded casts (0.2.307).

The kits' TIMING values come from the time between a player's presses in real captures. A chain
skill is its own press in the game, so a kit that folds a chain hit into its parent action also
charges the chain press's time to that action, but only when the build takes the chain (the
Cleric's Discharge procs on its own, so it is charged at its chance). A skill the hand-written kit
leaves to the generic reader keeps its measured time, and ``calibrate`` turns a measured press
into a TIMING value the same way the kits were derived."""
import pytest

from aion2calc.kit.base import ClassData
from aion2calc.run import kit_module
from aion2calc.scenarios import typical_build


def _kit(cls, specs=None):
    b = typical_build(cls)
    b.bonus = {sid: 7 for sid in b.sp}          # effective levels high enough for the chain specs
    b.specs = specs or {}
    return kit_module(cls).build_kit(b, ClassData(cls)).actions, kit_module(cls)


def test_a_folded_chain_press_is_timed_only_when_the_chain_is_taken():
    plain, mod = _kit("gladiator")
    chained, _ = _kit("gladiator", {11170000: (11170030,)})                 # Overhead Slam -> Upward Strike
    T, A = mod.TIMING, mod.ASSUME
    assert plain["overhead_slam"].cast == T["overhead_slam"]
    assert chained["overhead_slam"].cast == pytest.approx(T["overhead_slam"] + A["upward_chance"] * T["upward_strike"])

    plain, mod = _kit("chanter")
    chained, _ = _kit("chanter", {18100000: (18100040,)})                   # Dark Crush -> Piercing Strike
    T, A = mod.TIMING, mod.ASSUME
    assert plain["dark_crush"].cast == T["dark_crush"]
    assert chained["dark_crush"].cast == pytest.approx(T["dark_crush"] + A["piercing_chance"] * T["piercing_strike"])
    # Bursting Blow is Incandescent Blow's own chain (0.2.319), so its press is always charged, at its rate.
    for actions in (plain, chained):
        assert actions["incandescent_blow"].cast == pytest.approx(T["incandescent_blow"] + A["bursting_chance"] * T["bursting_blow"])

    plain, mod = _kit("ranger")
    chained, _ = _kit("ranger", {14020000: (14020050,)})                    # Snipe -> Tempest Arrow
    assert plain["snipe"].cast == mod.TIMING["snipe"]
    assert chained["snipe"].cast == pytest.approx(mod.TIMING["snipe"] + mod.TIMING["tempest_arrow"])


def test_the_cleric_discharge_press_is_charged_at_its_chance():
    plain, mod = _kit("cleric")
    spec, _ = _kit("cleric", {17010000: (17010020,)})                       # +20% Discharge chance
    T, A = mod.TIMING, mod.ASSUME
    assert plain["earths_retribution"].cast == pytest.approx(T["earths_retribution"] + A["discharge_chance"] * T["discharge"])
    assert spec["earths_retribution"].cast == pytest.approx(
        T["earths_retribution"] + (A["discharge_chance"] + 0.20) * T["discharge"])


def test_a_generic_fallback_skill_keeps_the_kits_measured_time():
    actions, mod = _kit("gladiator")
    assert "crushing_wave" in actions and actions["crushing_wave"].cast == mod.TIMING["crushing_wave"]


def test_calibrate_turns_a_measured_press_into_a_timing_value():
    from aion2calc.calibrate import kit_action_time
    assert kit_action_time(0.40, "gladiator") == 0.40       # (0.40 - 0.03) x ~1.08 typical Combat Speed
    assert kit_action_time(0.03, "gladiator") == 0.0        # never below zero
    assert kit_action_time(1.03, "sorcerer") == pytest.approx(1.08, abs=0.01)
