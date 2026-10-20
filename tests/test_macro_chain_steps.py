"""A chain step is no skill of its own. Punishing Strike (the Templar's), Smashing Blow (the
Gladiator's) and Thunder and Lightning (the Cleric's) are their parent skill's key pressed again
while its chain is open: none is in the class's skill list. The macro page listed each as a skill
with a hotbar key of its own, no icon and level 1, so a Templar went looking for a "Punishing
Strike" to bind."""
import pytest

from aion2calc.app import views
from aion2calc.kit.base import Build, ClassData
from aion2calc.opt.macro import MODEL_VERSION

CASES = [
    ("templar", "punishing_strike", "pummel", "Pummel",
     ["annihilate", "pummel", "shield_smite", "punishing_strike", "vicious_strike"]),
    ("gladiator", "basic_combo", "rending_blow", "Rending Blow", ["rending_blow", "basic_combo", "keen_strike"]),
    ("cleric", "thunder_and_lightning", "earths_retribution", "Earth's Retribution",
     ["earths_retribution", "thunder_and_lightning"]),
]


@pytest.mark.parametrize("cls,step,parent,parent_name,steps", CASES)
def test_a_chain_step_is_its_parents_key_pressed_again(cls, step, parent, parent_name, steps):
    cd = ClassData(cls)
    summary = {"scenario": "boss", "policy": steps,
               "macro": {"model_version": MODEL_VERSION, "steps": steps, "manual": []}}
    view = views.rotation_view(cd, Build(cls), {}, summary)
    shown = {s["key"]: s for s in view["rotation"]["steps"]}
    assert shown[step]["chain_of"] == parent_name
    assert shown[step]["binding"] == shown[parent]["binding"] != "Assign key"
    assert shown[step]["icon"] == shown[parent]["icon"] and shown[step]["level"] == shown[parent]["level"]
    assert shown[parent]["chain_of"] is None
    slots = [s["key"] for s in view["hotbar"]["slots"]]
    assert parent in slots and step not in slots            # no hotbar slot of its own
    assert next(p for p in view["rotation"]["priority"] if p["key"] == step)["chain_of"] == parent_name


def test_the_macro_plan_names_each_chain_steps_parent():
    from aion2calc.opt.macro import describe_plan, plan_macro
    from aion2calc.run import Scenario, prepare
    scen = Scenario(loadout="templar_l45_global_median")
    _, _, kit, stats = prepare(Build("templar"), scen)
    plan = plan_macro(stats.derived(), kit, list(kit.policy), scen.target, scen.config)
    assert describe_plan(plan)["chains"] == {"punishing_strike": "pummel"}


@pytest.mark.parametrize("cls,parent,step", [("templar", "pummel", "punishing_strike"), ("gladiator", "rending_blow", "basic_combo"),
                                             ("cleric", "earths_retribution", "thunder_and_lightning")])
def test_a_chain_skill_never_repeats_while_its_chain_is_open(cls, parent, step):
    # its key presses the chain step then: a Pummel right after a Pummel is a Punishing Strike in the game. With
    # the step costing MP (0.2.323) the Templar's optimizer had dropped Punishing Strike for Pummels alone
    from aion2calc.run import Scenario, prepare
    from aion2calc.sim.engine import Sim
    scen = Scenario(loadout=f"{cls}_l45_global_median")
    _, _, kit, stats = prepare(Build(cls), scen)
    filler = next(k for k, a in kit.actions.items() if a.is_filler and k != parent)
    result = Sim(stats.derived(), kit.actions, [parent, filler], scen.target, scen.config,
                 hooks=kit.hooks, cond_mods=kit.cond_mods).run()
    presses = [t for t, key in result.timeline if key == parent]
    assert len(presses) > 10 and step not in result.casts
    assert min(b - a for a, b in zip(presses, presses[1:])) >= scen.config.chain_window - 1e-6


@pytest.mark.parametrize("cls,parent,step", [("templar", "pummel", "punishing_strike"), ("gladiator", "rending_blow", "basic_combo"),
                                             ("cleric", "earths_retribution", "thunder_and_lightning")])
def test_a_macro_step_presses_what_its_key_would(cls, parent, step):
    # a chain step's macro step is its parent added again, and that key presses the chain step while the chain
    # is open and the parent otherwise: a macro of either step alone presses both (the model had a step for the
    # chain step press nothing until another step opened the chain)
    from aion2calc.opt.macro import MacroPolicy
    from aion2calc.run import Scenario, prepare
    from aion2calc.sim.engine import Sim
    scen = Scenario(loadout=f"{cls}_l45_global_median")
    _, _, kit, stats = prepare(Build(cls), scen)
    filler = next(k for k, a in kit.actions.items() if a.is_filler and k != parent)
    for steps in ([parent, filler], [step, filler]):
        result = Sim(stats.derived(), kit.actions, MacroPolicy([], steps), scen.target, scen.config,
                     hooks=kit.hooks, cond_mods=kit.cond_mods).run()
        assert result.casts.get(parent) and result.casts.get(step), steps
