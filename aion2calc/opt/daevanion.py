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

HiGHS often stops at its time limit with the best allocation it has found so
far, and on a busy machine that can leave much of the board unspent. So the
program starts from the current allocation, completed first: unspent points go
along the cheapest connected paths to the nodes worth most per point, and the
skill points are retrained for that board, until neither adds value. The result
is never worth less, in this objective, than that start, and the solver's own
result is completed the same way.
"""
from __future__ import annotations

import heapq
from collections import Counter

import pulp

from ..kit.base import SP_COST, ClassData
from .solver import outcome, solver

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
          boards: tuple = CRYSTAL_BOARDS, gap: float = 0.0005, min_node_hp: float = 0, min_sp: dict | None = None,
          min_effective: dict | None = None, start: tuple | None = None, spend_all: bool = False) -> dict:
    """``skill_curves[sid][L]`` = DPS with skill at effective level L (index 0 unused).

    ``start`` = (nodes, trained levels) of the current allocation. When it satisfies the
    program the solver starts from it, and the result is never worth less than it.
    ``spend_all`` puts points nothing of value can use on nodes worth nothing (never less).
    """
    bonus = bonus or {}
    min_effective = min_effective or {}
    if (set(min_effective) | set(min_sp or {})) - set(skill_curves):
        raise ValueError("Reserved skills require allocation curves")
    prob = pulp.LpProblem("daevanion", pulp.LpMaximize)
    x, flows, obj = {}, {}, []
    node_skill: dict[int, list] = {}
    adjacent: dict[int, list] = {}
    roots = set()
    for b in cd.boards:
        if b["name"] not in boards:
            continue
        M = len(b["nodes"])
        for n in b["nodes"]:
            if n["type"] == "Start":
                roots.add(n["id"])
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
            adjacent.setdefault(u["id"], []).append(v["id"])
            if v["type"] == "Start":
                continue
            f = pulp.LpVariable(f"f_{u['id']}_{v['id']}", lowBound=0)
            flows[u["id"], v["id"]] = f
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

    hp = {nid: sum(float(s["value"]) for s in cd.node_index[nid][1].get("stats", []) if s.get("stat") == "HPMax")
          for nid in x}
    if min_node_hp > 0:
        prob += pulp.lpSum(hp[nid] * var for nid, var in x.items()) >= min_node_hp, "minimum_flat_crystal_hp"

    # skill points
    y, z = {}, {}
    sp_terms = []
    for sid, curve in skill_curves.items():
        s = cd.skills[sid]
        buy = s.get("buyMax", 10)
        levels = range(1, buy + 1)
        if fixed_sp and sid in fixed_sp:
            levels = [fixed_sp[sid]]
        if min_sp and sid in min_sp:
            levels = [level for level in levels if level >= min_sp[sid]]
        y[sid] = {l: pulp.LpVariable(f"y_{sid}_{l}", cat="Binary") for l in levels}
        prob += pulp.lpSum(y[sid].values()) == 1
        sp_terms += [sum(SP_COST[:l]) * y[sid][l] for l in levels]
        kmax = min(max_level, len(curve) - 1)
        z[sid] = {k: pulp.LpVariable(f"z_{sid}_{k}", cat="Binary") for k in range(1, kmax + 1)}
        for k in range(1, kmax):
            prob += z[sid][k] >= z[sid][k + 1]
        eff = (pulp.lpSum(l * v for l, v in y[sid].items()) + pulp.lpSum(node_skill.get(sid, []))
               + bonus.get(sid, 0))
        if sid in min_effective:
            prob += eff >= min_effective[sid], f"minimum_effective_{sid}"
        prob += pulp.lpSum(z[sid].values()) <= eff
        prob += pulp.lpSum(z[sid].values()) >= eff - 0  # exact when eff <= kmax
        for k in range(1, kmax + 1):
            obj.append((curve[k] - curve[k - 1]) * z[sid][k])
    # skills without a curve keep any nodes free of value; cap their eff implicitly
    prob += pulp.lpSum(sp_terms) <= sp_budget
    prob += pulp.lpSum(obj)

    # the same program, checked, scored and completed for a whole allocation (nodes, trained levels)
    skill_of = {nid: cd.node_index[nid][1]["skillId"] for nid in x if cd.node_index[nid][1].get("skillId")}

    def points(nodes):
        return sum(cost[n] for n in nodes)

    def effective(nodes, sp):
        from_nodes = Counter(skill_of[n] for n in nodes if n in skill_of)
        return {sid: sp[sid] + from_nodes[sid] + bonus.get(sid, 0) for sid in y}

    def feasible(nodes, sp):
        if any(sp.get(sid) not in levels for sid, levels in y.items()):
            return False
        eff = effective(nodes, sp)
        return (sum(sum(SP_COST[:l]) for l in sp.values()) <= sp_budget
                and points(nodes) <= daev_budget
                and sum(hp[n] for n in nodes) + 1e-6 >= min_node_hp
                and all(min_effective.get(sid, 0) <= eff[sid] <= len(z[sid]) for sid in y)
                and connected(cd, nodes))

    def value(nodes, sp):
        eff = effective(nodes, sp)
        return (sum(node_value.get(n, 0.0) for n in nodes)
                + sum(skill_curves[sid][eff[sid]] - skill_curves[sid][0] for sid in y))

    def path_value(path, eff):
        """What taking ``path`` in order adds; None if it would raise a skill past its curve."""
        total, extra = 0.0, Counter()
        for n in path:
            total += node_value.get(n, 0.0)
            sid = skill_of.get(n)
            if sid in eff:
                level = eff[sid] + extra[sid]
                if level >= len(z[sid]):
                    return None
                total += skill_curves[sid][level + 1] - skill_curves[sid][level]
                extra[sid] += 1
        return total

    def fill(nodes, sp, floor=1e-9):
        """Spend unspent points: repeatedly take the cheapest connected path (by node cost) to the
        untaken node worth most per point, while one fits the budget and is worth over ``floor``."""
        nodes = set(nodes)
        while True:
            room = daev_budget - points(nodes)
            eff = effective(nodes, sp)
            worth = {n: path_value([n], eff) for n in x if n not in nodes}
            best = None
            for path in _paths(adjacent, nodes | roots, cost,
                               {n: w for n, w in worth.items() if w is not None}).values():
                spent, gain = points(path), path_value(path, eff)
                if spent <= room and gain is not None and gain > floor and (
                        best is None or (gain / spent, gain, -spent) > best[0]):
                    best = (gain / spent, gain, -spent), path
            if best is None:
                return nodes
            nodes.update(best[1])

    def trained(nodes):
        """The best trained levels for a fixed board: a knapsack over the skill-point budget."""
        from_nodes = Counter(skill_of[n] for n in nodes if n in skill_of)
        plans = {0: (0.0, {})}
        for sid, levels in y.items():
            fixed = from_nodes[sid] + bonus.get(sid, 0)
            options = [(sum(SP_COST[:l]), skill_curves[sid][l + fixed], l) for l in levels
                       if min_effective.get(sid, 0) <= l + fixed <= len(z[sid])]
            updated = {}
            for spent, (worth, plan) in plans.items():
                for price, gain, l in options:
                    total = spent + price
                    if total <= sp_budget and (total not in updated or worth + gain > updated[total][0]):
                        updated[total] = (worth + gain, {**plan, sid: l})
            plans = updated
        return max(plans.values(), key=lambda p: p[0])[1] if plans else None

    def complete(nodes, sp):
        """Fill the board, then retrain the skill points for it, until neither adds value."""
        while True:
            nodes = fill(nodes, sp)
            better = trained(nodes)
            if better is None or value(nodes, better) <= value(nodes, sp) + 1e-9:
                return nodes, sp
            sp = better

    warm = None
    if start is not None:
        nodes, sp = set(start[0]) & set(x), {sid: start[1].get(sid, 1) for sid in y}
        if feasible(nodes, sp):
            # HiGHS's own heuristics rarely complete a board in the time it has, so hand it a
            # complete one: from there it can prune, and often prove the optimum in time
            nodes, sp = complete(nodes, sp)
            warm = nodes, sp
            eff, through = effective(nodes, sp), _flows(cd, nodes)
            for nid, var in x.items():
                var.setInitialValue(int(nid in nodes))
            for edge, var in flows.items():
                var.setInitialValue(through.get(edge, 0))
            for sid, ys in y.items():
                for l, var in ys.items():
                    var.setInitialValue(int(l == sp[sid]))
                for k, var in z[sid].items():
                    var.setInitialValue(int(k <= eff[sid]))

    import os
    status = prob.solve(solver(time_limit=time_limit, gap=gap, threads=min(4, os.cpu_count() or 1),
                               warm_start=warm is not None))
    nodes = {nid for nid, var in x.items() if var.value() and var.value() > 0.5}
    sp = {}
    for sid, ys in y.items():
        for l, var in ys.items():
            if var.value() and var.value() > 0.5:
                sp[sid] = l
    # A time-limited incumbent can be worth less than the start (if HiGHS could not use it)
    # or leave points unspent: keep the best feasible allocation at hand and complete it.
    lowest = set(), {sid: min(ys, default=0) for sid, ys in y.items()}
    found = [a for a in ((nodes, sp) if prob.sol_status > 0 else None, warm, lowest)
             if a is not None and feasible(*a)]
    report, reached, filled = outcome(prob), None, 0
    if found:
        nodes, sp = max(found, key=lambda a: value(*a))
        before = points(nodes)
        nodes, sp = complete(nodes, sp)
        if spend_all:
            # nodes worth nothing here (defensive stats in PvE), as the optimizer spends left-over
            # skill points; not for a feasibility search, where nothing is worth anything
            nodes = fill(nodes, sp, floor=-1e-9)
        filled = points(nodes) - before
        objective = value(nodes, sp)
        if report["bound"] is not None:
            reached = max(0.0, report["bound"] - objective) / max(abs(objective), 1.0)
    elif min_node_hp > 0 or min_sp or min_effective:
        if min_sp or min_effective:
            raise ValueError("No feasible skill/HP reserve allocation was found within the budgets and solver time limit. No unconstrained fallback was published.")
        raise ValueError("No feasible HP-reserve allocation was found within the budgets and solver time limit. Lower the reserve or adjust your assumptions; no unconstrained fallback was published.")
    else:
        objective = pulp.value(prob.objective)
    text = pulp.LpStatus[status]
    if report["time_limited"]:
        # PuLP calls this "Optimal" when HiGHS has any solution
        text = "time limit, " + ("no bound proven" if reached is None else f"gap {reached:.2%}")
    return {"status": text, "nodes": nodes, "sp": sp,
            "objective": objective,
            "daev_cost": sum(cost[n] for n in nodes),
            "sp_cost": sum(sum(SP_COST[:l]) for l in sp.values()),
            "time_limited": report["time_limited"], "gap": reached,
            "warm_start": warm is not None, "filled": filled}


def _paths(adjacent: dict, sources: set, cost: dict, worth: dict) -> dict:
    """Cheapest connected path (by node cost; equal costs by worth) from ``sources`` through the
    nodes that can be taken (``worth``'s keys) to each one reached: {node: [path, sources' end first]}."""
    best = dict.fromkeys(sources, (0, 0.0))
    came = {}
    heap = [(0, 0.0, s) for s in sources]
    heapq.heapify(heap)
    while heap:
        spent, minus, u = heapq.heappop(heap)
        if (spent, minus) > best[u]:
            continue
        for v in adjacent.get(u, ()):
            if v not in worth:
                continue
            key = (spent + cost[v], minus - worth[v])
            if v not in best or key < best[v]:
                best[v], came[v] = key, u
                heapq.heappush(heap, (*key, v))
    paths = {}
    for v in came:
        path = [v]
        while path[-1] in came:
            path.append(came[path[-1]])
        paths[v] = path[-2::-1]
    return paths


def _tree(cd: ClassData, nodes: set):
    """Each taken node's parent on a path from its board's centre through taken nodes, and the
    nodes in the order found (parents first); None when a taken node is cut off."""
    parent, order = {}, []
    for b in cd.boards:
        taken = nodes & {n["id"] for n in b["nodes"]}
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
                    parent[m["id"]] = n["id"]
                    order.append(m["id"])
                    stack.append(m)
        if taken - seen:
            return None
    return parent, order


def _flows(cd: ClassData, nodes: set) -> dict:
    """A feasible flow for connected ``nodes``: along a tree from each board's centre, every
    taken node draws one unit and passes on what the taken nodes beyond it draw."""
    parent, order = _tree(cd, nodes)
    through = dict.fromkeys(order, 1)
    for nid in reversed(order):
        if parent[nid] in through:
            through[parent[nid]] += through[nid]
    return {(parent[nid], nid): through[nid] for nid in order}


def connected(cd: ClassData, nodes: set) -> bool:
    """Check the planner rule: each taken node touches the centre through taken nodes."""
    return _tree(cd, nodes) is not None
