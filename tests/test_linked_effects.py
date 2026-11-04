"""Supporting effects that act on each other's cooldowns are tried together (0.2.376). A Sorcerer reported that the
optimizer never kept Wish of Concentration's -10 s to every cooldown or Blaze's -3 s to Wish's, and that their own build
scored better than the one it suggested. The optimizer changed one skill's effects at a time under a fixed rotation:
Wish's effect alone fell 6 % and Blaze's 3 %, while together, with a rotation searched for them, they were 15 % above the
effects it kept, on the reporter's own skill levels. Synthetic scores stand in for the simulation below."""
import pytest

from aion2calc.kit.base import Build
from aion2calc.opt.pipeline import Optimizer
from aion2calc.scenarios import SCENARIOS

BLAZE, FA, WISH = 15050000, 15210000, 15310000
FS, HF, IC, SHACK, FROST, FB, BW, SCAT = 15040000, 15060000, 15090000, 15110000, 15150000, 15220000, 15280000, 15010000
WISH_ALL, BLAZE_WISH = WISH + 50, BLAZE + 50          # "-10s all skill cooldowns", "-3s [Wish of Concentration] cooldown"


@pytest.fixture
def opt():
    return Optimizer("sorcerer", SCENARIOS["boss"]("sorcerer_l45_global_median"), verbose=False)


def test_the_linking_effects_are_read_from_their_text(opt):
    groups, links = opt._spec_links()
    assert sorted(groups) == sorted([(BLAZE, FA, WISH), (IC, SHACK), (FS, HF), (FROST, FB, BW), (SCAT,)])
    assert links[WISH] == {WISH_ALL} and links[BLAZE] == {BLAZE_WISH} and links[FA] == {FA + 50}     # resets Blaze
    assert links[FS] == {FS + 40} and links[BW] == {BW + 50} and links[FROST] == {FROST + 30} and HF not in links


def _build():
    b = Build("sorcerer", 45)
    b.sp = {WISH: 10, BLAZE: 10}
    b.bonus = {WISH: 6, BLAZE: 6}                     # Lv 16: two slots, the -3 s and -10 s effects open
    b.specs = {WISH: (WISH + 20, WISH + 40), BLAZE: (BLAZE + 30, BLAZE + 40)}
    return b


def _scores(opt, monkeypatch, searched_pair):
    """Under the fixed rotation each linking effect alone loses and the pair gains a little; with its own rotation the
    pair gains ``searched_pair``. Any other skill's change scores far below."""
    def score(b):
        wish, blaze = WISH_ALL in b.specs.get(WISH, ()), BLAZE_WISH in b.specs.get(BLAZE, ())
        others = any(set(b.specs.get(sid, ())) != set(_build().specs.get(sid, ())) for sid in b.specs if sid not in (WISH, BLAZE))
        return (100.0 - 50 * others + (1.0 if wish and blaze else -6.0 if wish else -3.0 if blaze else 0.0))
    searched = []

    def rotation(b, policy, restarts=2):
        searched.append(b)
        both = WISH_ALL in b.specs.get(WISH, ()) and BLAZE_WISH in b.specs.get(BLAZE, ())
        return ["searched"], (searched_pair if both else score(b) + 0.5), None
    monkeypatch.setattr(opt, "evaluate", lambda b, policy, cfg=None, filler=None: score(b))
    monkeypatch.setattr(opt, "optimize_rotation", rotation)
    return searched


def test_two_linking_effects_are_taken_together_with_their_own_rotation(opt, monkeypatch):
    searched = _scores(opt, monkeypatch, searched_pair=115.0)
    b, policy = opt.optimize_linked_specs(_build(), ["kept"])
    assert WISH_ALL in b.specs[WISH] and BLAZE_WISH in b.specs[BLAZE] and policy == ["searched"]
    assert len(searched) == 1                                  # the pair scored best under the old rotation: searched first


def test_the_build_stays_when_no_candidate_beats_it_with_its_own_rotation(opt, monkeypatch):
    searched = _scores(opt, monkeypatch, searched_pair=99.0)
    b, policy = opt.optimize_linked_specs(_build(), ["kept"])
    assert b.specs[WISH] == _build().specs[WISH] and b.specs[BLAZE] == _build().specs[BLAZE] and policy == ["kept"]
    assert len(searched) == 2                                  # the best two, both within reach of the build's own score


def test_the_level_curves_try_a_skills_linking_effect_with_a_linked_skills(opt):
    builds = opt._linked_builds(_build(), WISH)
    pairs = {(b.specs[WISH], b.specs[BLAZE]) for b in builds}
    assert pairs and all(WISH_ALL in w and BLAZE_WISH in z for w, z in pairs)
    assert len(pairs) == len(builds) == 16                    # Wish's four pairs with -10 s, times Blaze's four with -3 s


def test_the_search_keeps_its_starting_build_when_it_ends_below_it(opt, monkeypatch):
    """An imported character's own build is where its optimization starts, and the result is never below it (0.2.376):
    started from a typical top player's build, a Sorcerer's search lowered Wish of Concentration below the level that
    opens its cooldown effect and ended 13 % under the character as it was."""
    start = _build()
    start.specs[WISH] = (WISH + 20, WISH_ALL)
    elsewhere = _build()                                      # what the stand-in search wanders to

    def rotation(b, policy, restarts=2):
        return ["searched"], (100.0 if WISH_ALL in b.specs.get(WISH, ()) else 90.0), None
    monkeypatch.setattr(opt, "optimize_rotation", rotation)
    monkeypatch.setattr(opt, "evaluate", lambda b, policy, cfg=None, filler=None: rotation(b, policy)[1])
    for step in ("optimize_stigmas", "polish_sp", "spend_remaining_sp", "polish_bonus"):
        monkeypatch.setattr(opt, step, lambda b, policy, **kw: b)
    monkeypatch.setattr(opt, "optimize_specs", lambda b, policy, passes=2: elsewhere.copy())
    monkeypatch.setattr(opt, "optimize_linked_specs", lambda b, policy, **kw: (b, policy))
    monkeypatch.setattr(opt, "allocate", lambda b, policy: (b, {"status": "stub", "daev_cost": 0, "sp_cost": 0}, {}, []))
    monkeypatch.setattr(opt, "_stat_weights", lambda b, policy, final=False: [])
    result = opt.run(iterations=1, initial_build=start, initial_policy=["mine"])
    assert WISH_ALL in result.build.specs[WISH] and result.dps == 100.0
    plain = opt.run(iterations=1)                              # no starting build: the search's own result
    assert WISH_ALL not in plain.build.specs.get(WISH, ()) and plain.dps == 90.0


def _closed_wish():
    """Wish of Concentration at Lv 12, below the 16 that opens its -10 s; Blaze's and Flame Arrow's effects open."""
    b = _build()
    b.sp[FA] = 10
    b.bonus = {WISH: 2, BLAZE: 6, FA: 6}
    b.specs = {WISH: (WISH + 20,), BLAZE: (BLAZE + 30, BLAZE_WISH), FA: (FA + 40, FA + 50)}
    return b


def test_a_closed_linking_effect_is_measured_at_the_level_that_opens_it(opt, monkeypatch):
    """The level curves judge one skill at a time under a fixed rotation, so a level that opens effects paying off only
    together never showed a gain (0.2.376). A probe raises the closed skill to that level for free and measures the
    group's linking effects there with their own rotation, once per group and closed levels: the allocation counts
    the gain only when every closed skill reaches its level."""
    b = _closed_wish()
    searches = []

    def score(build, policy, cfg=None, filler=None):
        return 100.0 + (12.0 if WISH_ALL in build.specs.get(WISH, ()) and policy == ["searched"] else 0.0)

    def rotation(build, policy, restarts=2):
        searches.append(build)
        return ["searched"], score(build, ["searched"]), None
    monkeypatch.setattr(opt, "evaluate", score)
    monkeypatch.setattr(opt, "optimize_rotation", rotation)
    terms = opt._linked_probe_terms(b, ["kept"])
    assert terms == [({WISH: 16}, 12.0)]           # Blaze's and Flame Arrow's are open; the other groups gain nothing
    n = len(searches)
    assert opt._linked_probe_terms(b, ["kept"]) == terms and len(searches) == n   # each group searched once


def test_what_the_searched_rotation_gains_alone_is_not_the_linking_effects(opt, monkeypatch):
    def score(build, policy, cfg=None, filler=None):
        searched = policy == ["searched"]                     # worth 5 with or without the linking effects
        return 100.0 + 5.0 * searched + 12.0 * (searched and WISH_ALL in build.specs.get(WISH, ()))
    monkeypatch.setattr(opt, "evaluate", score)
    monkeypatch.setattr(opt, "optimize_rotation",
                        lambda build, policy, restarts=2: (["searched"], score(build, ["searched"]), None))
    assert opt._linked_probe_terms(_closed_wish(), ["kept"]) == [({WISH: 16}, 12.0)]


def test_a_level_no_allocation_reaches_is_not_probed(opt, monkeypatch):
    """On median gear 10 trained levels and the 4 level nodes on the boards make 14: Wish's -10 s at 16 is out of
    reach, and its group is not probed."""
    b = _closed_wish()
    b.bonus[WISH] = 0
    searched = []

    def rotation(build, policy, restarts=2):
        searched.append(build)
        return ["searched"], 100.0, None
    monkeypatch.setattr(opt, "evaluate", lambda build, policy, cfg=None, filler=None: 100.0)
    monkeypatch.setattr(opt, "optimize_rotation", rotation)
    assert opt._level_reach(b)[WISH] == 14 and opt._level_reach(_closed_wish())[WISH] == 16
    assert opt._linked_probe_terms(b, ["kept"]) == []
    assert searched and not any(x.bonus.get(WISH, 0) for x in searched)    # the other groups' probes only


def test_the_allocation_is_handed_the_joint_gains_and_keeps_their_skills_curves(opt, monkeypatch):
    from aion2calc.opt import daevanion as dv
    from aion2calc.opt import pipeline
    terms = [({WISH: 16, BLAZE: 16}, 50.0)]
    seen, kept, real = {}, [], dv.solve
    monkeypatch.setattr(opt, "_linked_probe_terms", lambda b, p: terms)

    def curves(b, p, keep=()):
        kept.append(set(keep))
        return {sid: [0.0] * 21 for sid in keep}
    monkeypatch.setattr(opt, "level_curves", curves)
    monkeypatch.setattr(opt, "_stat_weights", lambda b, p, final=False: [])
    monkeypatch.setattr(dv, "solve", lambda *a, **kw: seen.update(kw) or real(*a, **kw))
    monkeypatch.setattr(pipeline, "DAEV_SOLVER_TIME_LIMIT", 20)
    start = opt.initial_build()
    start.bonus = {WISH: 4, BLAZE: 4}                          # 10 trained, 4 on the boards: 18 within reach
    b, sol, _, _ = opt.allocate(start, [])
    assert kept[0] == {WISH, BLAZE} and seen["joint"] == terms
    levels = opt._with_gear(b).effective_levels(opt.cd)
    assert levels[WISH] >= 16 and levels[BLAZE] >= 16 and sol["objective"] == pytest.approx(50.0)
