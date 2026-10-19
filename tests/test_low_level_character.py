"""A character below level 45. The optimizer treated every character as level 45: four stigma
slots, every skill trainable to 10, every Daevanion board open, level-45 base stats. A level-24
Templar with no stigma points (one slot opens at 22, and its profile had none slotted) stopped
with "No feasible stigma allocation fits the reserved levels and budget" after a minute of
silently scoring the current build, which looked like the optimizer hanging there. The
character's level now gates the stigma slots, each skill's trained level (its ``need`` levels),
the boards and the base stats, and a skill not learned yet is left out of the kit."""
from pathlib import Path

import pytest

from aion2calc.kit.base import Build, ClassData, stigma_points_to_reach, trainable_level
from aion2calc.opt import daevanion as dv
from aion2calc.opt.pipeline import Optimizer
from aion2calc.run import prepare
from aion2calc.scenarios import SCENARIOS, typical_build

APP_JS = (Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def templar():
    return ClassData("templar")


def _skill(cd, name):
    return cd.by_name[name]


def _optimizer(**kw):
    return Optimizer("templar", SCENARIOS["boss"]("templar_l45_global_median"), verbose=False, **kw)


def test_a_skills_trained_level_follows_the_character_level(templar):
    vicious = _skill(templar, "Vicious Strike")         # level 10 needs character level 25
    assert trainable_level(vicious, 24) == 9 and trainable_level(vicious, 25) == 10
    assert trainable_level(_skill(templar, "Defiance"), 24) == 4
    assert trainable_level(_skill(templar, "Block Pain"), 24) == 1      # learned at 25: no points
    for s in templar.skills.values():                   # a level-45 character: the purchase cap
        if s["kind"] != "stigma":
            assert trainable_level(s, 45) == min(10, s.get("buyMax", 10))


def test_a_skill_not_learned_yet_is_left_out_of_the_kit(templar):
    low = Build("templar", 10)
    assert low.effective_levels(templar)[_skill(templar, "Annihilate")["id"]] == 0    # learned at 12
    _, _, kit, _ = prepare(low, SCENARIOS["boss"]("templar_l45_global_median"))
    assert "annihilate" not in kit.actions and "punishment" not in kit.actions
    assert not any((e[0] if isinstance(e, tuple) else e) in ("annihilate", "punishment") for e in kit.policy)
    _, _, kit, _ = prepare(Build("templar", 45), SCENARIOS["boss"]("templar_l45_global_median"))
    assert "annihilate" in kit.actions and "punishment" in kit.actions


def test_a_level_24_character_with_no_stigma_points_gets_a_starting_build():
    opt = _optimizer(level=24, sp_budget=70, stigma_points=0, daev_budget=40)
    assert opt.slots == 1 and opt.stigma_slots == 0
    assert opt.boards == ("Nezekan", "Zikel")
    b = opt.initial_build()                             # raised "No feasible stigma allocation ..."
    assert b.level == 24 and b.stigmas == {}
    assert all(level <= trainable_level(opt.cd.skills[sid], 24) for sid, level in b.sp.items())
    assert b.sp_spent() <= 70
    assert opt.optimize_stigmas(b, []) is b              # nothing to search


def test_stigmas_fill_the_slots_the_level_opens_with_the_points_there_are():
    opt = _optimizer(level=24, stigma_points=3)
    b = opt.initial_build()
    assert opt.stigma_slots == 1 and len(b.stigmas) == 1
    assert sum(stigma_points_to_reach(v) for v in b.stigmas.values()) <= 3
    opt = _optimizer(level=45, stigma_points=2)         # fewer points than slots: the rest stay empty
    assert opt.stigma_slots == 2 and len(opt.initial_build().stigmas) == 2


def test_a_level_45_optimizer_keeps_every_slot_board_and_level():
    opt = _optimizer()
    assert opt.level == 45 and opt.slots == 4 and opt.stigma_slots == 4
    assert opt.boards == dv.CRYSTAL_BOARDS
    assert all(opt._top(sid) == min(10, s.get("buyMax", 10)) for sid, s in opt.cd.skills.items() if s["kind"] != "stigma")
    assert opt.initial_build().level == 45


def test_the_program_trains_no_skill_past_its_gate_and_stays_on_open_boards(templar):
    # every level of every skill and every node worth something: only the gates hold it back
    curves = {sid: [0.0] + [float(k) for k in range(1, 21)] for sid, s in templar.skills.items()
              if s["kind"] != "stigma" and (s.get("unlock") or 1) <= 24}
    values = {n["id"]: 1.0 for b in templar.boards for n in b["nodes"]}
    caps = {sid: trainable_level(s, 24) for sid, s in templar.skills.items() if s["kind"] != "stigma"}
    sol = dv.solve(templar, curves, values, daev_budget=40, sp_budget=500, time_limit=30,
                   boards=("Nezekan", "Zikel"), max_sp=caps)
    assert all(level <= caps[sid] for sid, level in sol["sp"].items())
    assert {templar.node_index[n][0]["name"] for n in sol["nodes"]} <= {"Nezekan", "Zikel"}
    assert sol["daev_cost"] <= 40


def test_the_typical_build_baseline_holds_to_the_characters_level_and_budgets(templar):
    # the report's "typical top build" took the top players' whole board on every open board: at
    # level 24 it outscored the optimized build, which had only the character's points
    b = typical_build("templar", sp_budget=70, stigma_points=0, level=24, daev_budget=40)
    assert b.level == 24 and b.stigmas == {}            # 0 points is no stigma, not the level's default
    assert {templar.node_index[n][0]["name"] for n in b.daevanion} <= {"Nezekan", "Zikel"}
    assert b.daevanion_cost(templar) <= 40 and dv.connected(templar, b.daevanion)
    assert all(level <= trainable_level(templar.skills[sid], 24) for sid, level in b.sp.items())
    full = typical_build("templar")
    assert full.level == 45 and len(full.stigmas) == 4
    assert typical_build("templar", daev_budget=10000).daevanion == full.daevanion


def test_a_saved_result_is_rebuilt_at_its_characters_level():
    from aion2calc.report import build_from_summary
    # an older priority list gains the kit's essential summons, but not one learned at level 3
    summary = {"class": "spiritmaster", "level": 2, "policy": ["cold_shock"],
               "build": {"sp": {}, "stigmas": {}, "specs": {}, "daevanion_nodes": []}}
    b, policy = build_from_summary(summary)             # was always rebuilt at level 45
    assert b.level == 2 and "summon_fire" in policy and "summon_water" not in policy
    _, _, kit, _ = prepare(b, SCENARIOS["boss"]("spiritmaster_l45_global_median"))
    assert all((e[0] if isinstance(e, tuple) else e) in kit.actions for e in policy)
    assert build_from_summary({**summary, "level": None})[0].level == 45                # older results


def test_the_page_fills_community_totals_only_at_the_level_cap():
    # the highest reported totals come from level-45 characters; the only Templar report was a
    # level-24 character's, which the page then offered every Templar as the budget
    guard = APP_JS[APP_JS.index("const levelCap=v.level_cap||45;"):]
    guard = guard[:guard.index("A2ProgressionBudgets.read(communityAPI,v.class")]
    assert "(v.level??levelCap)<levelCap" in guard and "else " in guard
    assert "Community point totals are not filled in below level" in guard
