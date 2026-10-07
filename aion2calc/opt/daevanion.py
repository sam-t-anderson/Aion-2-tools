"""Joint Daevanion-node + skill-point allocation as an integer program.

Variables
    x[v]      node v of a Daevanion Crystal board is taken
    f[u,v]    flow on the board graph (connectivity: every taken node must be
              reachable from the board's centre through taken nodes)
    y[s,l]    skill s is trained to level l with skill points
    z[s,k]    effective level of skill s is at least k

Objective
    sum_s sum_k dV[s][k] * z[s,k]  +  sum_v w[v] * x[v]

where dV comes from simulated per-skill DPS curves and w from stat weights.
"""
from __future__ import annotations

import pulp

from ..kit.base import SP_COST, ClassData
from .solver import solver

CRYSTAL_BOARDS = ("Nezekan", "Zikel", "Vaizel", "Triniel")


def _neighbors(board):
    pos = {(n["row"], n["col"]): n for n in board["nodes"]}
    for n in board["nodes"]:
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = pos.get((n["row"] + dr, n["col"] + dc))
            if m:
                yield n, m


def solve(cd: ClassData, skill_curves: dict[int, list[float]], node_value: dict[int, float],
          daev_budget: int = 360, sp_budget: int = 203, bonus: dict | None = None,
          max_level: int = 20, fixed_sp: dict | None = None, time_limit: int = 120,
          boards: tuple = CRYSTAL_BOARDS, gap: float = 0.0005, min_node_hp: float = 0) -> dict:
    """``skill_curves[sid][L]`` = DPS with skill at effective level L (index 0 unused)."""
    bonus = bonus or {}
    prob = pulp.LpProblem("daevanion", pulp.LpMaximize)
    x, flows, obj = {}, [], []
    node_skill: dict[int, list] = {}
    for b in cd.boards:
        if b["name"] not in boards:
            continue
        M = len(b["nodes"])
        for n in b["nodes"]:
            if n["type"] == "Start":
                continue
            x[n["id"]] = pulp.LpVariable(f"x_{n['id']}", cat="Binary")
            if n.get("skillId"):
                node_skill.setdefault(n["skillId"], []).append(x[n["id"]])
            w = node_value.get(n["id"], 0.0)
            if w:
                obj.append(w * x[n["id"]])
        inflow: dict[int, list] = {}
        outflow: dict[int, list] = {}
        for u, v in _neighbors(b):
            if v["type"] == "Start":
                continue
            f = pulp.LpVariable(f"f_{u['id']}_{v['id']}", lowBound=0)
            flows.append(f)
            inflow.setdefault(v["id"], []).append(f)
            outflow.setdefault(u["id"], []).append(f)
            prob += f <= M * x[v["id"]]
            if u["type"] != "Start":
                prob += f <= M * x[u["id"]]
        for n in b["nodes"]:
            if n["type"] == "Start":
                continue
            prob += (pulp.lpSum(inflow.get(n["id"], [])) - pulp.lpSum(outflow.get(n["id"], []))
                     == x[n["id"]])
    cost = {nid: cd.node_index[nid][1]["cost"] for nid in x}
    prob += pulp.lpSum(cost[n] * x[n] for n in x) <= daev_budget

    if min_node_hp > 0:
        hp_terms = []
        for nid, var in x.items():
            hp = sum(float(s["value"]) for s in cd.node_index[nid][1].get("stats", []) if s.get("stat") == "HPMax")
            hp_terms.append(hp * var)
        prob += pulp.lpSum(hp_terms) >= min_node_hp, "minimum_flat_crystal_hp"

    # skill points
    y, z = {}, {}
    sp_terms = []
    for sid, curve in skill_curves.items():
        s = cd.skills[sid]
        buy = s.get("buyMax", 10)
        levels = range(1, buy + 1)
        if fixed_sp and sid in fixed_sp:
            levels = [fixed_sp[sid]]
        y[sid] = {l: pulp.LpVariable(f"y_{sid}_{l}", cat="Binary") for l in levels}
        prob += pulp.lpSum(y[sid].values()) == 1
        sp_terms += [sum(SP_COST[:l]) * y[sid][l] for l in levels]
        kmax = min(max_level, len(curve) - 1)
        z[sid] = {k: pulp.LpVariable(f"z_{sid}_{k}", cat="Binary") for k in range(1, kmax + 1)}
        for k in range(1, kmax):
            prob += z[sid][k] >= z[sid][k + 1]
        eff = (pulp.lpSum(l * v for l, v in y[sid].items()) + pulp.lpSum(node_skill.get(sid, []))
               + bonus.get(sid, 0))
        prob += pulp.lpSum(z[sid].values()) <= eff
        prob += pulp.lpSum(z[sid].values()) >= eff - 0  # exact when eff <= kmax
        for k in range(1, kmax + 1):
            obj.append((curve[k] - curve[k - 1]) * z[sid][k])
    # skills without a curve keep any nodes free of value; cap their eff implicitly
    prob += pulp.lpSum(sp_terms) <= sp_budget
    prob += pulp.lpSum(obj)
    import os
    status = prob.solve(solver(time_limit=time_limit, gap=gap, threads=min(4, os.cpu_count() or 1)))
    nodes = {nid for nid, var in x.items() if var.value() and var.value() > 0.5}
    sp = {}
    for sid, ys in y.items():
        for l, var in ys.items():
            if var.value() and var.value() > 0.5:
                sp[sid] = l
    if min_node_hp > 0:
        from .survival import node_hp
        variables = list(x.values()) + [v for values in y.values() for v in values.values()] + [v for values in z.values() for v in values.values()]
        integral = all(v.value() is not None and abs(v.value()-round(v.value())) <= 1e-5 for v in variables)
        if (not integral or not prob.valid(1e-5) or pulp.LpStatus[status] in ("Infeasible", "Unbounded", "Undefined")
                or not connected(cd, nodes) or sum(cost[n] for n in nodes) > daev_budget
                or sum(sum(SP_COST[:l]) for l in sp.values()) > sp_budget
                or len(sp) != len(y) or node_hp(cd, nodes)+1e-6 < min_node_hp):
            raise ValueError("No feasible HP-reserve allocation was found within the budgets and solver time limit. Lower the reserve or adjust your assumptions; no unconstrained fallback was published.")
    return {"status": pulp.LpStatus[status], "nodes": nodes, "sp": sp,
            "objective": pulp.value(prob.objective),
            "daev_cost": sum(cost[n] for n in nodes),
            "sp_cost": sum(sum(SP_COST[:l]) for l in sp.values())}


def connected(cd: ClassData, nodes: set) -> bool:
    """Check the planner rule: each taken node touches the centre through taken nodes."""
    for b in cd.boards:
        ids = {n["id"] for n in b["nodes"]}
        taken = nodes & ids
        if not taken:
            continue
        pos = {(n["row"], n["col"]): n for n in b["nodes"]}
        root = next(n for n in b["nodes"] if n["type"] == "Start")
        seen, stack = {root["id"]}, [root]
        while stack:
            n = stack.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                m = pos.get((n["row"] + dr, n["col"] + dc))
                if m and m["id"] in taken and m["id"] not in seen:
                    seen.add(m["id"])
                    stack.append(m)
        if taken - seen:
            return False
    return True
