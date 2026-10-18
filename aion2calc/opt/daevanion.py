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

import heapq

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
          boards: tuple = CRYSTAL_BOARDS, gap: float = 0.0005, min_node_hp: float = 0, min_sp: dict | None = None,
          min_effective: dict | None = None) -> dict:
    """``skill_curves[sid][L]`` = DPS with skill at effective level L (index 0 unused)."""
    bonus = bonus or {}
    min_effective = min_effective or {}
    if (set(min_effective) | set(min_sp or {})) - set(skill_curves):
        raise ValueError("Reserved skills require allocation curves")
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
    import os
    status = prob.solve(solver(time_limit=time_limit, gap=gap, threads=min(4, os.cpu_count() or 1)))
    nodes = {nid for nid, var in x.items() if var.value() and var.value() > 0.5}
    sp = {}
    for sid, ys in y.items():
        for l, var in ys.items():
            if var.value() and var.value() > 0.5:
                sp[sid] = l
    solved_cost = sum(cost[n] for n in nodes)
    nodes, filled_value = fill_unspent(cd, nodes, node_value, skill_curves, sp, bonus, daev_budget,
                                       max_level=max_level, boards=boards)
    if min_node_hp > 0 or min_sp or min_effective:
        from .survival import node_hp
        variables = list(x.values()) + [v for values in y.values() for v in values.values()] + [v for values in z.values() for v in values.values()]
        integral = all(v.value() is not None and abs(v.value()-round(v.value())) <= 1e-5 for v in variables)
        if (not integral or not prob.valid(1e-5) or pulp.LpStatus[status] in ("Infeasible", "Unbounded", "Undefined")
                or not connected(cd, nodes) or sum(cost[n] for n in nodes) > daev_budget
                or sum(sum(SP_COST[:l]) for l in sp.values()) > sp_budget
                or len(sp) != len(y) or node_hp(cd, nodes)+1e-6 < min_node_hp
                or any(sp.get(sid,1)<level for sid,level in (min_sp or {}).items())
                or any(sp.get(sid,1)+cd.daevanion_levels(nodes).get(sid,0)+bonus.get(sid,0)<level
                       for sid,level in min_effective.items())):
            if min_sp or min_effective:
                raise ValueError("No feasible skill/HP reserve allocation was found within the budgets and solver time limit. No unconstrained fallback was published.")
            raise ValueError("No feasible HP-reserve allocation was found within the budgets and solver time limit. Lower the reserve or adjust your assumptions; no unconstrained fallback was published.")
    return {"status": pulp.LpStatus[status], "nodes": nodes, "sp": sp,
            "objective": pulp.value(prob.objective) + filled_value,
            "daev_cost": sum(cost[n] for n in nodes),
            "filled": sum(cost[n] for n in nodes) - solved_cost,
            "sp_cost": sum(sum(SP_COST[:l]) for l in sp.values())}


def fill_unspent(cd: ClassData, nodes: set, node_value: dict[int, float], skill_curves: dict[int, list[float]],
                 sp: dict[int, int], bonus: dict[int, int], daev_budget: int, *, max_level: int = 20,
                 boards: tuple = CRYSTAL_BOARDS) -> tuple[set, float]:
    """Spend points a solve stopped at its time limit left unused.

    The integer program can stop with an incumbent that leaves points unspent (the Spiritmaster's
    first solve kept 165 of 360 points even with the machine to itself). Take the cheapest
    connected path of untaken nodes to the node that adds the most value per point, again and
    again, while it fits the budget and adds value: stat nodes count their stat value, skill-level
    nodes their skill curve's next level, never past the curve's end (``max_level`` for skills
    without a curve). An optimal solution has no such path, so it comes back unchanged.
    """
    nodes = set(nodes)
    cost = {n["id"]: n["cost"] for b in cd.boards for n in b["nodes"]}
    levels = {sid: sp.get(sid, 1) + bonus.get(sid, 0) for sid in cd.skills}
    for nid in nodes:
        sid = cd.node_index[nid][1].get("skillId")
        if sid:
            levels[sid] = levels.get(sid, 1) + 1
    cap = {sid: min(max_level, len(curve) - 1) for sid, curve in skill_curves.items()}

    def gains(path):
        """Value of taking ``path``, or None when it raises a skill past its cap."""
        extra, total = {}, 0.0
        for nid in path:
            total += node_value.get(nid, 0.0)
            sid = cd.node_index[nid][1].get("skillId")
            if sid:
                level = levels.get(sid, 1) + extra.get(sid, 0)
                if level + 1 > cap.get(sid, max_level):
                    return None
                extra[sid] = extra.get(sid, 0) + 1
                if sid in skill_curves:
                    total += skill_curves[sid][level + 1] - skill_curves[sid][level]
        return total

    spent, added = sum(cost[n] for n in nodes), 0.0
    while True:
        candidates = []
        for b in cd.boards:
            if b["name"] not in boards:
                continue
            pos = {(n["row"], n["col"]): n for n in b["nodes"]}

            def around(n):
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    m = pos.get((n["row"] + dr, n["col"] + dc))
                    if m is not None and m["type"] != "Start" and m["id"] not in nodes:
                        yield m

            dist, prev, heap = {}, {}, []
            for n in b["nodes"]:
                if n["type"] == "Start" or n["id"] in nodes:
                    for m in around(n):
                        if cost[m["id"]] < dist.get(m["id"], float("inf")):
                            dist[m["id"]], prev[m["id"]] = cost[m["id"]], None
                            heapq.heappush(heap, (dist[m["id"]], m["id"]))
            while heap:
                d, nid = heapq.heappop(heap)
                if d > dist[nid]:
                    continue
                if spent + d <= daev_budget:
                    path, cur = [], nid
                    while cur is not None:
                        path.append(cur)
                        cur = prev[cur]
                    candidates.append((d, path))
                for m in around(cd.node_index[nid][1]):
                    if d + cost[m["id"]] < dist.get(m["id"], float("inf")):
                        dist[m["id"]], prev[m["id"]] = d + cost[m["id"]], nid
                        heapq.heappush(heap, (dist[m["id"]], m["id"]))
        best = None
        for d, path in candidates:
            value = gains(path)
            if value is not None and value > 1e-9 and (best is None or value / d > best[0]):
                best = (value / d, d, path, value)
        if best is None:
            return nodes, added
        _, d, path, value = best
        for nid in path:
            sid = cd.node_index[nid][1].get("skillId")
            if sid:
                levels[sid] = levels.get(sid, 1) + 1
        nodes.update(path)
        spent += d
        added += value


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
