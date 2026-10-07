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
    """Dungeon boss: 30% Damage Tolerance, HP falls linearly, three 8 s stagger windows."""
    windows = tuple((s, s + 8.0) for s in (40.0, 100.0, 160.0) if s < duration)
    return Scenario(loadout=loadout,
                    target=Target(tolerance=0.30, hp_model="linear", stagger_windows=windows),
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


def comparison_scenario(name):
    return "pvp_burst" if name == "pvp" else "pvp" if name == "pvp_burst" else "dummy" if name == "boss" else "boss"


SCENARIOS = {"dummy": dummy, "boss": boss, "pvp": pvp, "pvp_burst": pvp_burst}


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


def typical_build(cls: str, sp_budget: int | None = None, stigma_points: int | None = None) -> Build:
    """What a typical top tracked global L45 player runs (metabot live statistics).

    * Daevanion: the most-picked nodes (metabot preset, crystal boards only)
    * skill points: each skill's average level among top players minus the
      levels those nodes give, fitted to the 203-point budget (most-levelled
      skills keep their points first)
    * stigmas: the four most-picked damage stigmas at their average levels,
      fitted to 30 points (least-picked gives way first)

    Specializations are not published; callers give this build the best legal
    specs for its levels (benefit of the doubt).
    """
    from .kit.base import sp_to_reach, stigma_points_to_reach
    cd = ClassData(cls)
    tp = cd.raw.get("top_players", {})
    p = cd.raw.get("preset") or {}
    b = Build(cls, level=p.get("level", 45))
    b.daevanion = {n for n in decode_metabot_daevanion(cd, p.get("daevanion", ""))
                   if cd.node_index[n][0]["name"] != "Azphel"}
    dv = cd.daevanion_levels(b.daevanion)
    avg = {**tp.get("skills", {}), **tp.get("passives", {})}
    want = {}
    for name, row in avg.items():
        s = cd.by_name.get(name)
        if not s or s["kind"] == "stigma" or not row.get("avg_level"):
            continue
        want[s["id"]] = max(1, min(s.get("buyMax", 10), round(row["avg_level"] - dv.get(s["id"], 0))))
    order = sorted(want, key=lambda sid: -avg[cd.skills[sid]["name"]]["avg_level"])
    bud = sp_budget or cd.budget(b.level)["skill"]
    while sum(sp_to_reach(v) for v in want.values()) > bud:      # trim the least-levelled skills
        sid = next(x for x in reversed(order) if want[x] > 1)
        want[sid] -= 1
    for sid in order:                                            # spend what is left
        while want[sid] < cd.skills[sid].get("buyMax", 10) and \
                sum(sp_to_reach(v) for v in want.values()) - sp_to_reach(want[sid]) \
                + sp_to_reach(want[sid] + 1) <= bud:
            want[sid] += 1
    b.sp = {sid: v for sid, v in want.items() if v > 1}
    stig = [(n, r) for n, r in tp.get("stigmas", {}).items() if n not in _DEFENSIVE and n in cd.by_name]
    stig = sorted(stig, key=lambda nr: -nr[1]["pick"])[: cd.budget(b.level)["slots"]]
    lv = {cd.by_name[n]["id"]: max(1, round(r.get("avg_level") or 1)) for n, r in stig}
    points = stigma_points or cd.budget(b.level)["stigma"] + 1
    for sid in reversed(list(lv)):                               # least-picked gives way first
        while sum(stigma_points_to_reach(v) for v in lv.values()) > points and lv[sid] > 1:
            lv[sid] -= 1
    b.stigmas = lv
    return b
