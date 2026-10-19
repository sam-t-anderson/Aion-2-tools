"""Named fight scenarios and the community baseline build."""
from __future__ import annotations

from .kit.base import Build, ClassData
from .run import Scenario
from .sim.engine import SimConfig, Target


def dummy(loadout: str = "sorcerer_l45_global_median", duration: float = 180.0) -> Scenario:
    """Training dummy: 10% Damage Tolerance (community measurement), always 100% HP."""
    return Scenario(loadout=loadout, target=Target(tolerance=0.10, hp_model="dummy"),
                    config=SimConfig(duration=duration))


def boss(loadout: str = "sorcerer_l45_global_median", duration: float = 180.0) -> Scenario:
    """Dungeon boss: 30% Damage Tolerance, HP falls linearly, three 8 s stagger windows; each
    class's direct hits land from the front, behind and the side in its recorded shares, and the
    party takes damage, so a healer heals at the recorded rate."""
    windows = tuple((s, s + 8.0) for s in (40.0, 100.0, 160.0) if s < duration)
    return Scenario(loadout=loadout,
                    target=Target(tolerance=0.30, hp_model="linear", stagger_windows=windows,
                                  class_positions=True, party_damage=True),
                    config=SimConfig(duration=duration))


PVP_NOTE = ("Experimental PvP damage-only proxy: 180 seconds against a stationary player target "
            "with neutral mitigation, full HP and no stagger windows. PvE/boss bonuses and learned "
            "proc/skill multipliers are excluded. Generic skill data is used for every class; "
            "PvP-specific damage coefficients, opponent gear, movement, crowd control, survival "
            "and win probability are not modeled. Uses the existing skill, stigma and crystal-board "
            "budgets; dedicated PvP progression is not optimized. A separate 30-second proxy score "
            "evaluates the same build and priority. This is not a verified competitive PvP build.")


def pvp(loadout: str = "sorcerer_l45_global_median", duration: float = 180.0) -> Scenario:
    return Scenario(loadout=loadout,
                    target=Target(tolerance=0, is_boss=False, is_player=True),
                    config=SimConfig(duration=duration))


def pvp_burst(loadout: str = "sorcerer_l45_global_median", duration: float = 30.0) -> Scenario:
    return pvp(loadout, duration)


def pvp_world(loadout: str = "sorcerer_l45_global_median", duration: float = 180.0) -> Scenario:
    """World PvP: several player targets in reach of area skills, and recurring windows with no enemy
    in melee reach (``opt.world``: the assumptions and the survival-weighted objective)."""
    from .opt.world import with_world
    return with_world(pvp(loadout, duration))


def comparison_scenario(name):
    return {"pvp": "pvp_burst", "pvp_burst": "pvp", "pvp_world": "pvp", "boss": "dummy"}.get(name, "boss")


SCENARIOS = {"dummy": dummy, "boss": boss, "pvp": pvp, "pvp_burst": pvp_burst, "pvp_world": pvp_world}


def decode_metabot_daevanion(cd: ClassData, h: str) -> set:
    nodes = set()
    for part in (h or "").split("_"):
        if "-" not in part:
            continue
        bid, idx = part.split("-", 1)
        board = next((b for b in cd.boards if str(b["id"]) == bid), None)
        if not board:
            continue
        for i in idx.split("."):
            try:
                nodes.add(board["nodes"][int(i, 36)]["id"])
            except (ValueError, IndexError):
                pass
    return nodes


def community_build(cls: str) -> Build:
    """metabot's 'most common build' among the top tracked global L45 players."""
    cd = ClassData(cls)
    p = cd.raw.get("preset") or {}
    b = Build(cls, level=p.get("level", 45))
    for s in p.get("skills", []):
        sid = s["id"]
        if sid not in cd.skills:
            continue
        if cd.skills[sid]["kind"] == "stigma":
            b.stigmas[sid] = s["level"]
        else:
            b.sp[sid] = min(10, s["level"])
            b.specs[sid] = tuple(s.get("specs", ()))
    stig = p.get("stigmas") or []
    b.stigmas = {sid: b.stigmas.get(sid, 1) for sid in stig if sid in cd.skills}
    b.daevanion = decode_metabot_daevanion(cd, p.get("daevanion", ""))
    return b


#: Stigmas without damage; a typical damage build still lists the top damage picks.
_DEFENSIVE = {"Steel Barrier", "Arctic Armor", "Hibernation", "Curse: Tree"}


def _fit_board(cd: ClassData, nodes: set, budget: int) -> set:
    """The nodes of ``nodes`` nearest their board centres that fit ``budget``, kept connected:
    a node is taken only next to its centre or to a node already taken."""
    from collections import deque
    steps = ((1, 0), (-1, 0), (0, 1), (0, -1))
    order = []
    for board in cd.boards:
        mine = {n["id"] for n in board["nodes"]} & nodes
        start = next((n for n in board["nodes"] if n["type"] == "Start"), None)
        if not mine or start is None:
            continue
        pos = {(n["row"], n["col"]): n for n in board["nodes"]}
        dist, queue = {start["id"]: 0}, deque([start])
        while queue:
            n = queue.popleft()
            for dr, dc in steps:
                m = pos.get((n["row"] + dr, n["col"] + dc))
                if m and m["id"] in mine and m["id"] not in dist:
                    dist[m["id"]] = dist[n["id"]] + 1
                    order.append((dist[m["id"]], m["id"]))
                    queue.append(m)
    taken, spent = set(), 0
    for _, nid in sorted(order):
        board, node = cd.node_index[nid]
        pos = {(n["row"], n["col"]): n for n in board["nodes"]}
        near = (pos.get((node["row"] + dr, node["col"] + dc)) for dr, dc in steps)
        if spent + node["cost"] <= budget and any(m and (m["type"] == "Start" or m["id"] in taken) for m in near):
            taken.add(nid)
            spent += node["cost"]
    return taken


def typical_build(cls: str, sp_budget: int | None = None, stigma_points: int | None = None,
                  level: int | None = None, daev_budget: int | None = None) -> Build:
    """What a typical top tracked global L45 player runs (metabot live statistics).

    * Daevanion: the most-picked nodes (metabot preset, crystal boards only)
    * skill points: each skill's average level among top players minus the
      levels those nodes give, fitted to the 203-point budget (most-levelled
      skills keep their points first)
    * stigmas: the four most-picked damage stigmas at their average levels,
      fitted to 30 points (least-picked gives way first)

    Specializations are not published; callers give this build the best legal
    specs for its levels (benefit of the doubt). ``level`` holds it to what a
    character of that level can have: the boards it has open, its skill-level
    gates and its stigma slots. ``daev_budget`` keeps the nodes nearest each
    board's centre that fit it, when the most-picked nodes cost more.
    """
    from .kit.base import sp_to_reach, stigma_points_to_reach, trainable_level
    cd = ClassData(cls)
    tp = cd.raw.get("top_players", {})
    p = cd.raw.get("preset") or {}
    b = Build(cls, level=level or p.get("level", 45))
    b.daevanion = {n for n in decode_metabot_daevanion(cd, p.get("daevanion", ""))
                   if cd.node_index[n][0]["name"] != "Azphel"
                   and (cd.node_index[n][0].get("needLevel") or 1) <= b.level}
    if daev_budget is not None and b.daevanion_cost(cd) > daev_budget:
        b.daevanion = _fit_board(cd, b.daevanion, daev_budget)
    dv = cd.daevanion_levels(b.daevanion)
    avg = {**tp.get("skills", {}), **tp.get("passives", {})}
    want = {}
    for name, row in avg.items():
        s = cd.by_name.get(name)
        if not s or s["kind"] == "stigma" or not row.get("avg_level"):
            continue
        want[s["id"]] = max(1, min(trainable_level(s, b.level), round(row["avg_level"] - dv.get(s["id"], 0))))
    order = sorted(want, key=lambda sid: -avg[cd.skills[sid]["name"]]["avg_level"])
    bud = sp_budget if sp_budget is not None else cd.budget(b.level)["skill"]
    while sum(sp_to_reach(v) for v in want.values()) > bud:      # trim the least-levelled skills
        sid = next(x for x in reversed(order) if want[x] > 1)
        want[sid] -= 1
    for sid in order:                                            # spend what is left
        while want[sid] < trainable_level(cd.skills[sid], b.level) and \
                sum(sp_to_reach(v) for v in want.values()) - sp_to_reach(want[sid]) \
                + sp_to_reach(want[sid] + 1) <= bud:
            want[sid] += 1
    b.sp = {sid: v for sid, v in want.items() if v > 1}
    stig = [(n, r) for n, r in tp.get("stigmas", {}).items() if n not in _DEFENSIVE and n in cd.by_name]
    points = stigma_points if stigma_points is not None else cd.budget(b.level)["stigma"] + 1
    # a stigma costs a point at level 1: fewer points than slots leave the rest empty
    stig = sorted(stig, key=lambda nr: -nr[1]["pick"])[: min(cd.budget(b.level)["slots"], points)]
    lv = {cd.by_name[n]["id"]: max(1, round(r.get("avg_level") or 1)) for n, r in stig}
    for sid in reversed(list(lv)):                               # least-picked gives way first
        while sum(stigma_points_to_reach(v) for v in lv.values()) > points and lv[sid] > 1:
            lv[sid] -= 1
    b.stigmas = lv
    return b
