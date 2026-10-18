"""The Daevanion/SP program when HiGHS stops at its time limit with a poor incumbent."""
import pulp
import pytest

from aion2calc.kit.base import ClassData
from aion2calc.opt import daevanion as dv


@pytest.fixture(scope="module")
def sorc():
    return ClassData("sorcerer")


@pytest.fixture(scope="module")
def skill(sorc):
    """A skill with a level node on each crystal board, and those nodes."""
    sid = next(n["skillId"] for b in sorc.boards for n in b["nodes"] if n.get("skillId"))
    return sid, {n["id"] for b in sorc.boards if b["name"] in dv.CRYSTAL_BOARDS
                 for n in b["nodes"] if n.get("skillId") == sid}


class _Partial:
    """Stands in for HiGHS stopped at its time limit: returns ``nodes`` and the trained levels
    ``levels`` (level 1 elsewhere) as its solution, whatever the start was."""

    def __init__(self, nodes, levels=None):
        self.nodes, self.levels = set(nodes), levels or {}

    def actualSolve(self, lp):
        for name, var in lp.variablesDict().items():
            if name.startswith("x_"):
                var.varValue = float(int(name[2:]) in self.nodes)
            elif name.startswith("y_"):
                _, sid, level = name.split("_")
                var.varValue = float(int(level) == self.levels.get(int(sid), 1))
            else:
                var.varValue = 0.0
        lp.assignStatus(pulp.LpStatusOptimal, pulp.LpSolutionIntegerFeasible)
        return pulp.LpStatusOptimal


def _board(cd, size, board=0):
    """The first ``size`` nodes found walking out from a crystal board's centre."""
    b = [x for x in cd.boards if x["name"] in dv.CRYSTAL_BOARDS][board]
    pos = {(n["row"], n["col"]): n for n in b["nodes"]}
    order, seen = [next(n for n in b["nodes"] if n["type"] == "Start")], set()
    for n in order:
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = pos.get((n["row"] + dr, n["col"] + dc))
            if m and m["id"] not in seen and m["type"] != "Start":
                seen.add(m["id"])
                order.append(m)
    return {n["id"] for n in order[1:size + 1]}


def _cost(cd, nodes):
    return sum(cd.node_index[n][1]["cost"] for n in nodes)


def _affordable_gain(cd, nodes, values, room):
    """Untaken nodes next to the taken ones or a centre that fit ``room`` and are worth something."""
    out = []
    for b in cd.boards:
        if b["name"] not in dv.CRYSTAL_BOARDS:
            continue
        pos = {(n["row"], n["col"]): n for n in b["nodes"]}
        for n in b["nodes"]:
            if n["id"] in nodes or n["type"] == "Start" or n["cost"] > room or values.get(n["id"], 0) <= 0:
                continue
            near = (pos.get((n["row"] + dr, n["col"] + dc)) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if any(m and (m["id"] in nodes or m["type"] == "Start") for m in near):
                out.append(n["id"])
    return out


def test_a_partial_incumbent_is_filled_to_a_connected_spent_board(sorc, monkeypatch):
    values = {nid: 1.0 for nid, (b, n) in sorc.node_index.items() if n["type"] == "Stat"}
    partial = _board(sorc, 3)
    monkeypatch.setattr(dv, "solver", lambda **kw: _Partial(partial))
    sol = dv.solve(sorc, {}, values, daev_budget=40, sp_budget=0, time_limit=1)
    assert partial <= sol["nodes"]
    assert dv.connected(sorc, sol["nodes"])
    assert sol["daev_cost"] == 40 and sol["filled"] == 40 - _cost(sorc, partial)
    assert sol["objective"] == pytest.approx(sum(values.get(n, 0) for n in sol["nodes"]))
    assert not _affordable_gain(sorc, sol["nodes"], values, 40 - sol["daev_cost"])


def test_points_nothing_of_value_can_use_still_go_on_the_board(sorc, monkeypatch):
    near, harmful = _board(sorc, 3), _board(sorc, 1, board=1)
    values = {**dict.fromkeys(near, 1.0), **dict.fromkeys(harmful, -1.0)}
    monkeypatch.setattr(dv, "solver", lambda **kw: _Partial(set()))
    sol = dv.solve(sorc, {}, values, daev_budget=30, sp_budget=0, time_limit=1, spend_all=True)
    assert sol["nodes"] >= near and not sol["nodes"] & harmful
    assert sol["daev_cost"] == 30 and dv.connected(sorc, sol["nodes"])
    assert sol["objective"] == pytest.approx(3.0)
    # without spend_all (a feasibility search, say) nothing goes on nodes worth nothing
    assert dv.solve(sorc, {}, values, daev_budget=30, sp_budget=0, time_limit=1)["nodes"] == near


def test_skill_nodes_are_filled_by_their_curve_and_never_past_it(sorc, skill, monkeypatch):
    sid, skill_nodes = skill
    curve = [0.0] + [100.0 * level for level in range(1, 13)]      # worth taking, up to level 12
    monkeypatch.setattr(dv, "solver", lambda **kw: _Partial(set(), {sid: 10}))
    sol = dv.solve(sorc, {sid: curve}, {}, daev_budget=360, sp_budget=21, time_limit=1)
    # trained 10 + 2 nodes reaches the curve's end; a third node would pass it
    assert len(sol["nodes"] & skill_nodes) == 2
    assert dv.connected(sorc, sol["nodes"]) and sol["sp"] == {sid: 10}
    assert sol["objective"] == pytest.approx(curve[12])


def test_unspent_skill_points_are_retrained_for_the_filled_board(sorc, skill, monkeypatch):
    sid, skill_nodes = skill
    curve = [0.0] + [50.0 * level for level in range(1, 21)]
    monkeypatch.setattr(dv, "solver", lambda **kw: _Partial(set(), {sid: 1}))
    sol = dv.solve(sorc, {sid: curve}, {}, daev_budget=360, sp_budget=21, time_limit=1)
    assert sol["sp"] == {sid: 10} and sol["sp_cost"] == 21
    assert sol["nodes"] >= skill_nodes and len(skill_nodes) == 4
    assert sol["objective"] == pytest.approx(curve[14])


def test_the_result_is_never_worth_less_than_the_start(sorc, skill, monkeypatch):
    sid, _ = skill
    curve = [0.0] + [50.0 * level for level in range(1, 21)]
    values = {nid: 1.0 for nid, (b, n) in sorc.node_index.items() if n["type"] == "Stat"}
    start = _board(sorc, 25, board=1)

    def worth(nodes, level):
        return (sum(values.get(n, 0) for n in nodes)
                + curve[level + sum(sorc.node_index[n][1].get("skillId") == sid for n in nodes)])

    monkeypatch.setattr(dv, "solver", lambda **kw: _Partial(_board(sorc, 3), {sid: 1}))
    sol = dv.solve(sorc, {sid: curve}, values, daev_budget=60, sp_budget=21, time_limit=1,
                   start=(start, {sid: 10}))
    assert sol["warm_start"]
    assert sol["objective"] >= worth(start, 10) - 1e-6
    assert sol["sp"] == {sid: 10} and dv.connected(sorc, sol["nodes"]) and sol["daev_cost"] <= 60


def test_highs_cut_short_returns_at_least_its_start_and_says_so(sorc, skill):
    sid, _ = skill
    curve = [0.0] + [50.0 * level for level in range(1, 21)]
    values = {nid: 1.0 + (nid % 7) for nid, (b, n) in sorc.node_index.items() if n["type"] == "Stat"}
    start = _board(sorc, 30, board=2)
    start_worth = (sum(values.get(n, 0) for n in start)
                   + curve[4 + sum(sorc.node_index[n][1].get("skillId") == sid for n in start)])
    # no time at all: HiGHS stops before searching and hands back the completed start
    sol = dv.solve(sorc, {sid: curve}, values, daev_budget=120, sp_budget=6, time_limit=0,
                   start=(start, {sid: 4}))
    assert sol["warm_start"] and sol["time_limited"] and sol["status"].startswith("time limit")
    assert sol["objective"] >= start_worth - 1e-6
    assert dv.connected(sorc, sol["nodes"]) and sol["daev_cost"] <= 120
    assert not _affordable_gain(sorc, sol["nodes"], values, 120 - sol["daev_cost"])


def test_an_infeasible_start_is_not_used(sorc):
    values = {nid: 1.0 for nid, (b, n) in sorc.node_index.items() if n["type"] == "Stat"}
    cut_off = {min(_board(sorc, 30) - _board(sorc, 10))}        # not next to the centre
    for start in (cut_off, _board(sorc, 60)):                    # cut off; over the budget
        sol = dv.solve(sorc, {}, values, daev_budget=40, sp_budget=0, time_limit=30, start=(start, {}))
        assert not sol["warm_start"]
        assert dv.connected(sorc, sol["nodes"]) and sol["daev_cost"] <= 40


def test_the_optimizer_starts_the_program_from_the_build_it_has(sorc, skill, monkeypatch):
    from aion2calc.opt import pipeline
    from aion2calc.scenarios import SCENARIOS
    logged = []
    opt = pipeline.Optimizer("sorcerer", SCENARIOS["boss"]("sorcerer_l45_global_median"), verbose=False,
                             progress=logged.append)
    build = opt.initial_build()
    build.daevanion = _board(sorc, 20)
    sid, _ = skill
    seen, real = {}, dv.solve
    monkeypatch.setattr(dv, "solve", lambda *a, **kw: seen.update(kw) or real(*a, **kw))
    monkeypatch.setattr(pipeline, "DAEV_SOLVER_TIME_LIMIT", 0)
    monkeypatch.setattr(opt, "level_curves", lambda b, p: {sid: [0.0] + [10.0 * l for l in range(1, 21)]})
    monkeypatch.setattr(opt, "_stat_weights", lambda b, p, final=False: [])
    allocated, sol, _, _ = opt.allocate(build, [])
    assert seen["start"] == (build.daevanion, build.sp) and sol["warm_start"]
    assert allocated.daevanion >= build.daevanion
    # the log says the solve was cut short, where PuLP alone would have said "Optimal"
    assert any("solver finished (time limit" in line and "started from the current allocation" in line
               for line in logged)
