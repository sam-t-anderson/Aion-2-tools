"""Optimize a real character: import it, score it as-is, find the best build for
the same gear and point budgets, and write the difference.

    python -m aion2calc character "Name" --server Zikel --optimize
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from .kit.base import ClassData
from .opt.rotation import describe
from .paths import write_user_json
from .run import prepare
from .scenarios import SCENARIOS, comparison_scenario
from .sources import official
from .sources.character import ImportedCharacter, from_profile

CRYSTAL_BOARDS = ("Nezekan", "Zikel", "Vaizel", "Triniel")


def find(name: str, region: str = "nae", server: str | int | None = None) -> list[dict]:
    hits = official.search(name, region=region)
    exact = [h for h in hits if h["name"].lower() == name.lower()] or hits
    if server is not None:
        s = str(server).lower()
        exact = [h for h in exact if str(h["server_id"]) == s or (h["server"] or "").lower() == s]
    return sorted(exact, key=lambda h: -(h["level"] or 0))


def import_character(character_id: str, server_id: int, region: str = "nae", progress=None,
                     use_cache: float = 0) -> ImportedCharacter:
    ch = official.fetch_character(character_id, server_id, region, progress=progress, use_cache=use_cache)
    imp = from_profile(ch)
    write_user_json(imp.loadout, "global", "loadouts", f"{imp.loadout_name()}.json")
    snapshot(imp)
    return imp


def snapshot(imp: ImportedCharacter) -> int:
    """Keep what the character has equipped now, so later fights can be matched to it."""
    from .db import store
    b = imp.build
    data = {"loadout": imp.loadout, "loadout_name": imp.loadout_name(), "level": imp.level,
            "combat_power": imp.combat_power, "server": imp.server,
            "build": {"sp": {str(k): v for k, v in b.sp.items()}, "stigmas": {str(k): v for k, v in b.stigmas.items()},
                      "daevanion": sorted(b.daevanion)},
            "equipment": [{"slot": r["slot"], "name": r["name"], "enchant": r.get("enchant")}
                          for r in imp.systems.get("equipment", []) + imp.systems.get("arcana", [])]}
    return store.put_snapshot(store.connect(), imp.key, imp.name, imp.cls, data)


def crystal_cost(cd: ClassData, nodes) -> int:
    return sum(cd.node_index[n][1]["cost"] for n in nodes
               if n in cd.node_index and cd.node_index[n][0]["name"] in CRYSTAL_BOARDS)


def budgets_of(imp: ImportedCharacter) -> dict:
    """Optimize with at least the resources the character has already spent."""
    cd = ClassData(imp.cls)
    bud = cd.budget(imp.level or 45)
    result = {"skill": max(imp.build.sp_spent(), bud["skill"]),
              "stigma": max(imp.build.stigma_spent(), bud["stigma"]),
              "daevanion": max(crystal_cost(cd, imp.build.daevanion), 1)}
    from .paths import read_json
    try:
        saved = read_json("character-points.json").get(imp.key, {})
        for key in result:
            if isinstance(saved.get(key), int) and not isinstance(saved[key], bool) and 0 <= saved[key] <= 10000:
                result[key] = max(result[key], saved[key])
    except (OSError, ValueError):
        pass
    return result


def evaluate_current(imp: ImportedCharacter, scenario_name: str = "boss", genus: dict | None = None, objective="primary") -> dict:
    """The character as it is (best legal specs for its levels, optimized rotation)."""
    cls = imp.cls
    from .opt.genus import apply as apply_genus
    frozen_loadout = apply_genus(imp.loadout, genus)
    scen = SCENARIOS[scenario_name](frozen_loadout)
    other_name = comparison_scenario(scenario_name)
    other = SCENARIOS[other_name](frozen_loadout)
    b = imp.build.copy()
    b.bonus = {}                       # gear skill rolls come from the loadout
    bud = budgets_of(imp)
    from .opt.weighted import optimizer_for, objective_summary
    opt = optimizer_for(cls, scen, other, objective, verbose=False, sp_budget=bud["skill"],
                        stigma_points=bud["stigma"], daev_budget=bud["daevanion"])
    from .run import kit_module
    policy = list(kit_module(cls, pvp=scen.target.is_player).build_kit(opt._with_gear(b), opt.cd).policy)
    b = opt.optimize_specs(b, policy)
    policy, dps, res = opt.optimize_rotation(b, policy)
    cd, bg, kit, stats = prepare(b, scen)
    from .report import _sim
    res_other, _, _ = _sim(b, other, policy)
    # Weighted rotation returns a composite scalar, not the primary DPS.
    res, _, _ = _sim(b, scen, policy)
    dps = res.dps
    d = stats.derived()
    from .model.stats import crit_chance
    eff = bg.effective_levels(cd)
    from .kit.specialties import describe as describe_specialties
    return {
        "class": cls, "loadout": imp.loadout_name(), "loadout_snapshot": frozen_loadout, "scenario": scenario_name, "kind": "current",
        "character": {"name": imp.name, "server": imp.server, "level": imp.level,
                      "combat_power": imp.combat_power, "warnings": imp.warnings},
        "dps": {scenario_name: dps, other_name: res_other.dps},
        "objective": objective_summary(objective, scenario_name, other_name,
                                       {scenario_name: dps, other_name: res_other.dps},
                                       {scenario_name: scen.config.duration, other_name: other.config.duration}),
        "budgets": bud,
        "stats": {"attack_avg": d.attack(), "crit_stat": d.crit_stat,
                  "crit_chance_vs_target": crit_chance(d.crit_stat, scen.target.crit_resist, midpoint=1024.52 if scen.target.is_player else None),
                  "cdr": d.cdr, "combat_speed": d.combat_speed, "boost_bucket": d.amp,
                  "double": d.double, "perfect": d.perfect, "multihit": d.multihit, "weapon_amp": d.weapon_amp},
        "build": {"sp": {cd.skills[k]["name"]: v for k, v in sorted(b.sp.items())},
                  "sp_spent": b.sp_spent(), "stigma_spent": b.stigma_spent(),
                  "stigmas": {cd.skills[k]["name"]: v for k, v in b.stigmas.items()},
                  "specs": {cd.skills[k]["name"]: [x["text"] for x in cd.skills[k]["specs"] if x["id"] in v]
                            for k, v in b.specs.items() if v},
                  "daevanion_nodes": sorted(b.daevanion),
                  "daevanion_cost": crystal_cost(cd, b.daevanion),
                  "effective_levels": {cd.skills[k]["name"]: v for k, v in eff.items() if v > 1},
                  "specialties": describe_specialties(cd,bg)},
        "policy": describe(policy),
        "policy_raw": [list(e) if isinstance(e, tuple) else e for e in policy],
        "weights": opt._stat_weights(b, policy, final=True),
        "shares": res.shares(),
        "systems": imp.systems, "genus": copy.deepcopy(genus),
    }


def optimize_character(imp: ImportedCharacter, out_dir: str, iterations: int = 2,
                       scenario_name: str = "boss", progress=None, budgets: dict | None = None, survival: dict | None = None, skill_reserves: dict | None = None, genus: dict | None = None, objective="primary") -> dict:
    from .diff import write_diff
    from .report import run_report
    out = Path(out_dir)
    t0 = time.time()
    from .opt.survival import prepare as prepare_survival
    survival_plan = prepare_survival(ClassData(imp.cls), imp.build, survival)
    if survival_plan and progress:
        progress(f"HP reserve: maximize damage while retaining at least {survival_plan['minimum_node_hp']:,.0f} flat crystal-board HP")
    from .plan import inventory as INV
    from .opt.genus import prepare as prepare_genus
    inv = INV.load(INV.profile_name(imp.cls, imp.loadout_name()), imp.cls)
    genus_plan = prepare_genus(inv.get("genus", {}), "pvp" if scenario_name.startswith("pvp") else "pve", genus)
    if progress:
        progress(f"Genus Insight: {len(genus_plan['lines'])} saved lines; {genus_plan['mode'].upper()} damage model")
    cur = evaluate_current(imp, scenario_name, genus_plan, objective)
    (out / "current").mkdir(parents=True, exist_ok=True)
    bud = dict(cur["budgets"])
    for key, value in (budgets or {}).items():
        if key not in bud or isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000:
            raise ValueError("Point budgets must be whole numbers from 0 to 10000")
        spent = {"skill": imp.build.sp_spent(), "stigma": imp.build.stigma_spent(), "daevanion": crystal_cost(ClassData(imp.cls), imp.build.daevanion)}[key]
        if value < spent:
            raise ValueError(f"{key} total cannot be lower than the {spent} points already spent")
        bud[key] = value
    if budgets:
        from .paths import read_json
        try:
            saved = read_json("character-points.json")
        except (OSError, ValueError):
            saved = {}
        saved[imp.key] = bud
        write_user_json(saved, "character-points.json")
    from .opt.reserves import prepare as prepare_reserves
    from .model.character import loadout_stats
    reserve_plan = prepare_reserves(ClassData(imp.cls), skill_reserves, bud, loadout_stats(imp.loadout).skill_bonus)
    if reserve_plan and progress:
        progress(f"Retaining trained minimums for {sum(len(reserve_plan[k]) for k in ("sp", "stigmas"))} skills/stigmas")
    cur["budgets"] = bud
    (out / "current" / "build.json").write_text(json.dumps(cur, indent=1, default=str), encoding="utf-8")
    best = run_report(imp.cls, str(out), scenario_name=scenario_name, daev_budget=bud["daevanion"],
                      iterations=iterations, loadout=imp.loadout_name(), sp_budget=bud["skill"],
                      stigma_points=bud["stigma"], progress=progress, survival=survival_plan, loadout_snapshot=imp.loadout, skill_reserves=reserve_plan, genus=genus_plan, objective=objective)
    write_diff(str(out / "current"), str(out), str(out / "DIFF.md"))
    current_score, optimized_score = cur["objective"]["score"], best["objective"]["score"]
    gain = optimized_score / current_score - 1 if current_score > 0 else None
    summary = {"character": cur["character"], "current_dps": cur["dps"], "optimized_dps": best["dps"],
               "gain": gain, "scenario": scenario_name,
               "objective": {**best["objective"], "current_score": current_score, "gain": gain}, "genus": best.get("genus"), "survival": best.get("survival"), "skill_reserves": best.get("skill_reserves"), "budgets": bud, "seconds": time.time() - t0}
    (out / "character.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
