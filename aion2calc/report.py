"""Run the full optimization for a class and write a report folder.

    python -m aion2calc optimize sorcerer --out results/sorcerer_l45
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import replace
from pathlib import Path

from .kit.base import ClassData
from .opt.macro import plan_macro
from .opt.pipeline import Optimizer
from .opt.rotation import describe, materialize, optimize_rotation
from .render.boards import render_boards
from .render.links import (gamers4life_build_url, gamers4life_daevanion_url, metabot_build_url,
                           metabot_daevanion_url)
from .run import kit_module, prepare
from .scenarios import SCENARIOS, community_build
from .sim.engine import Sim


def _sim(build, scenario, policy):
    cd, b, kit, stats = prepare(build, scenario)
    pol = [e for e in policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    sim = Sim(stats.derived(), kit.actions, materialize(pol), scenario.target, scenario.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods)
    return sim.run(), kit, stats


def arcana_skill_values(cls, build, scenario, policy) -> list[dict]:
    """Simulated DPS gain of each random skill option Unique arcana can roll for ``cls``."""
    path = Path(__file__).resolve().parent / "data" / "global" / "arcana_skill_pools.json"
    if not path.exists():
        return []
    pool = json.loads(path.read_text(encoding="utf-8")).get(cls, {})
    cd = ClassData(cls)
    base = _sim(build, scenario, policy)[0].dps
    rows = []
    for name in pool.get("skills", []):
        s = cd.by_name.get(name)
        if not s:
            continue
        gains = []
        for lv in range(1, (pool.get("max_level") or 4) + 1):
            b = build.copy()
            b.bonus = dict(b.bonus)
            b.bonus[s["id"]] = b.bonus.get(s["id"], 0) + lv
            gains.append(_sim(b, scenario, policy)[0].dps / base - 1)
        rows.append({"skill": name, "id": s["id"], "gain_pct": [100 * g for g in gains]})
    rows.sort(key=lambda r: -r["gain_pct"][-1])
    return rows


def kr_share_overlap(cls: str, shares: dict) -> dict | None:
    """Overlap (0-1) between simulated damage shares and KR A2DIL top dummy logs.

    KR runs at higher levels with more skills/specializations, so 100% is not
    expected; it is a fidelity indicator for the class kit, not a target.
    """
    path = Path(__file__).resolve().parent / "data" / "kr" / "a2dil" / f"{cls}.json"
    if not path.exists():
        return None
    cd = ClassData(cls)
    kr: dict = {}
    for v in json.loads(path.read_text(encoding="utf-8"))["skills"].values():
        if v["code"]:
            kr[v["code"]] = kr.get(v["code"], 0.0) + v["mean_share"]
    tot = sum(kr.values()) or 1.0
    kr = {k: v / tot for k, v in kr.items()}
    sim: dict = {}
    for name, v in shares.items():
        base = name.split(" (")[0]
        s = cd.by_name.get(base) or next((x for n, x in cd.by_name.items() if base.startswith(n)), None)
        if s:
            sim[s["id"]] = sim.get(s["id"], 0.0) + v
    missing = sum(v for k, v in kr.items() if k not in cd.skills)
    return {"overlap": sum(min(sim.get(k, 0.0), kr.get(k, 0.0)) for k in set(sim) | set(kr)),
            "kr_share_not_in_global_data": missing}


def _board_images(cd, build, comm, out: Path, daev_budget: int) -> None:
    cls = cd.cls
    dv = cd.daevanion_levels(build.daevanion)
    board_lines = ["## Skill levels from nodes"]
    board_lines += [f"{cd.skills[k]['name']}: +{v}" for k, v in sorted(dv.items(), key=lambda kv: -kv[1])]
    board_lines += ["", "## Stats from nodes"]
    raw = cd.daevanion_stats(build.daevanion)
    labels = cd.raw.get("stat_labels", {})
    for k, v in sorted(raw.items(), key=lambda kv: -kv[1]):
        rule_pct = k in ("CombatSpeed", "CoolTimeDecrease", "AmplifyAllDamage", "AmplifyCriticalDamage",
                         "AdditionalHitRate", "DecreaseDamage", "DecreaseCriticalDamage", "AdditionalHitResistRate")
        board_lines.append(f"{labels.get(k, k)}: +{v / 100:.1f}%" if rule_pct else f"{labels.get(k, k)}: +{v:g}")
    render_boards(cd, build.daevanion, str(out / "images" / "daevanion_optimized.png"),
                  f"{cls.capitalize()} L45 (global) — optimized Daevanion ({build.daevanion_cost(cd)}/{daev_budget} pts)",
                  summary_lines=board_lines, budget=daev_budget)
    comm_crystal = {n for n in comm.daevanion if cd.node_index[n][0]["name"] != "Azphel"}
    render_boards(cd, comm_crystal, str(out / "images" / "daevanion_community.png"),
                  f"{cls.capitalize()} L45 — most common global top-player Daevanion (metabot, aggregate)",
                  summary_lines=["## Note", "Aggregate of the most-picked nodes", "(not one player's board)"])


def build_from_summary(summary: dict):
    """Rebuild ``(Build, policy)`` from a ``build.json`` summary."""
    from .kit.base import Build
    cls = summary["class"]
    cd = ClassData(cls)
    byname = cd.by_name
    data = summary["build"]
    b = Build(cls)
    b.sp = {byname[k]["id"]: v for k, v in data["sp"].items()}
    b.stigmas = {byname[k]["id"]: v for k, v in data["stigmas"].items()}
    b.specs = {byname[k]["id"]: tuple(x["id"] for x in byname[k]["specs"] if x["text"] in v)
               for k, v in data["specs"].items()}
    b.daevanion = set(data["daevanion_nodes"])
    policy = [e if " [" not in e else (e.split(" [")[0], e.split(" [")[1][:-1]) for e in summary["policy"]]
    return b, policy


def rerender(out_dir: str) -> str:
    """Rewrite README.md from build.json (fills fields added after the run)."""
    from .model.character import load_loadout
    from .report_md import write_markdown
    path = Path(out_dir) / "build.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    cls = summary["class"]
    loadout = summary.get("loadout") or f"{cls}_l45_global_median"
    summary["loadout"] = loadout
    build, _ = build_from_summary(summary)
    (Path(out_dir) / "images").mkdir(parents=True, exist_ok=True)
    _board_images(ClassData(cls), build, community_build(cls), Path(out_dir), summary["daevanion_budget"])
    if "kr_fidelity" not in summary or "arcana_skill_values" not in summary:
        build, policy = build_from_summary(summary)
        dummy = SCENARIOS["dummy"](loadout)
        boss = SCENARIOS["boss"](loadout)
        summary.setdefault("kr_fidelity", kr_share_overlap(cls, _sim(build, dummy, policy)[0].shares()))
        summary.setdefault("arcana_skill_values", arcana_skill_values(cls, build, boss, policy))
        path.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return write_markdown(summary, out_dir, extra={
        "gear_lines": _gear_lines(loadout), "weapon_compare": summary.get("weapon_compare"),
        "loadout_name": load_loadout(loadout).get("name", loadout)})


def _spec_text(cd, sid, spid):
    return next((x["text"] for x in cd.skills[sid]["specs"] if x["id"] == spid), str(spid))


def sensitivity(build, scenario, policy, samples: int = 12, spread: float = 0.25, seed: int = 3):
    """Randomly perturb every action time by up to +-spread and compare the fixed policy
    against a re-optimized one: small losses mean the recommendation is robust."""
    rng = random.Random(seed)
    mod = kit_module(build.cls)
    base_timing = dict(getattr(mod, "TIMING", {}))
    out = []
    try:
        for _ in range(samples):
            if base_timing:
                for k, v in base_timing.items():
                    mod.TIMING[k] = v * (1 + rng.uniform(-spread, spread))
            cd, b, kit, stats = prepare(build, scenario)
            fixed = Sim(stats.derived(), kit.actions, materialize(policy), scenario.target,
                        scenario.config, hooks=kit.hooks, cond_mods=kit.cond_mods).run().dps
            r = optimize_rotation(stats.derived(), kit, scenario.target, scenario.config,
                                  start=[e for e in policy if not kit.actions[e[0] if isinstance(e, tuple) else e].is_filler],
                                  restarts=0, max_passes=3)
            out.append({"fixed": fixed, "reoptimized": r.dps, "loss_pct": 100 * (1 - fixed / r.dps)})
    finally:
        if base_timing:
            mod.TIMING.update(base_timing)
    return out


def run_report(cls: str, out_dir: str, scenario_name: str = "boss", daev_budget: int = 360,
               iterations: int = 3, loadout: str | None = None, verbose: bool = True) -> dict:
    t0 = time.time()
    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)
    loadout = loadout or f"{cls}_l45_global_median"
    scen = SCENARIOS[scenario_name](loadout)
    other = SCENARIOS["dummy" if scenario_name == "boss" else "boss"](loadout)
    cd = ClassData(cls)

    opt = Optimizer(cls, scen, daev_budget=daev_budget, verbose=verbose)
    res = opt.run(iterations=iterations)
    build, policy = res.build, res.policy

    # community baseline (most common global build) with a naive and an optimized rotation
    comm = community_build(cls)
    cd_, cb, ckit, cstats = prepare(comm, scen)
    naive = Sim(cstats.derived(), ckit.actions, ckit.policy, scen.target, scen.config,
                hooks=ckit.hooks, cond_mods=ckit.cond_mods).run()
    comm_rot = optimize_rotation(cstats.derived(), ckit, scen.target, scen.config, restarts=2)

    final, kit, stats = _sim(build, scen, policy)
    final_other, _, _ = _sim(build, other, policy)
    comm_other, _, _ = _sim(comm, other, comm_rot.policy)
    d = stats.derived()
    macro = plan_macro(d, kit, policy, scen.target, scen.config)
    sens = sensitivity(build, scen, policy, samples=8)

    eff = opt._with_gear(build).effective_levels(cd)
    dv = cd.daevanion_levels(build.daevanion)
    gear_bonus = opt._gear_bonus()

    def skill_rows(kind):
        rows = []
        for sid, s in cd.skills.items():
            if s["kind"] != kind:
                continue
            rows.append({"id": sid, "name": s["name"], "sp": build.sp.get(sid, 1), "daev": dv.get(sid, 0),
                         "gear": gear_bonus.get(sid, 0) + build.bonus.get(sid, 0), "eff": eff.get(sid, 1),
                         "specs": [{"id": x, "text": _spec_text(cd, sid, x)} for x in build.specs.get(sid, ())]})
        return sorted(rows, key=lambda r: (-r["eff"], r["name"]))

    actives, passives = skill_rows("active"), skill_rows("passive")
    stig_rows = []
    for sid, lv in build.stigmas.items():
        s = cd.skills[sid]
        stig_rows.append({"id": sid, "name": s["name"], "level": lv,
                          "specs": [x["text"] for x in s["specs"] if x["unlock"] <= lv]})

    timeline = [(round(t, 2), k) for t, k in final.timeline if t < 30]
    links = {
        "metabot_build": metabot_build_url(cd, build),
        "metabot_daevanion": metabot_daevanion_url(cd, build.daevanion),
        "gamers4life_daevanion": gamers4life_daevanion_url(cls, build.daevanion),
        "gamers4life_build": gamers4life_build_url(cls, build),
    }
    from .model.stats import crit_chance
    stat_summary = {
        "attack_avg": d.attack(), "attack_max": d.attack(perfect=True),
        "crit_stat": d.crit_stat, "crit_chance_vs_target": crit_chance(d.crit_stat, scen.target.crit_resist),
        "double": d.double, "perfect": d.perfect, "multihit": d.multihit, "boost_bucket": d.amp,
        "weapon_amp": d.weapon_amp, "combat_speed": d.combat_speed, "cdr": d.cdr,
        "accuracy": d.accuracy, "mp_max": d.mp_max,
    }
    summary = {
        "class": cls, "level": 45, "scenario": scenario_name, "daevanion_budget": daev_budget,
        "dps": {scenario_name: final.dps, other.target.hp_model and ("dummy" if scenario_name == "boss" else "boss"): final_other.dps},
        "baseline": {"community_naive": naive.dps, "community_optimized_rotation": comm_rot.dps,
                     "community_other_scenario": comm_other.dps},
        "build": {"sp": {cd.skills[k]["name"]: v for k, v in sorted(build.sp.items())},
                  "sp_spent": build.sp_spent(), "stigma_spent": build.stigma_spent(),
                  "stigmas": {cd.skills[k]["name"]: v for k, v in build.stigmas.items()},
                  "specs": {cd.skills[k]["name"]: [_spec_text(cd, k, x) for x in v]
                            for k, v in build.specs.items() if v},
                  "daevanion_nodes": sorted(build.daevanion),
                  "daevanion_cost": build.daevanion_cost(cd),
                  "effective_levels": {cd.skills[k]["name"]: v for k, v in eff.items() if v > 1}},
        "policy": describe(policy),
        "macro": {"steps": macro.macro_steps, "manual": describe(macro.manual),
                  "dps_macro": macro.dps_macro, "dps_priority": macro.dps_priority},
        "shares": final.shares(), "casts": final.casts, "uptime": final.uptime,
        "opener": timeline, "weights": res.weights, "stats": stat_summary,
        "sensitivity": sens, "links": links, "history": res.history,
        "runtime_s": time.time() - t0,
    }
    from .opt.gear import per_unit
    wc = weapon_compare(build, scen, policy, per_unit(res.weights))
    summary["weapon_compare"] = wc
    summary["loadout"] = loadout
    summary["arcana_skill_values"] = arcana_skill_values(cls, build, scen, policy)
    summary["kr_fidelity"] = kr_share_overlap(cls, final_other.shares() if scenario_name == "boss"
                                              else final.shares())
    (out / "build.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")

    # ---- images
    _board_images(cd, build, comm, out, daev_budget)
    try:
        from .render.buildcard import render_build_card
        pr = []
        for e in policy:
            k = e[0] if isinstance(e, tuple) else e
            a = kit.actions[k]
            note = {"sync_de": "wait for Delayed Explosion", "in_ee": "inside Element Enhancement",
                    "mp_hi": "only at MP >= 60%"}.get(
                e[1] if isinstance(e, tuple) else None, "")
            if a.is_filler and not isinstance(e, tuple):
                note = "filler"
            pr.append({"id": a.skill_id, "label": a.name, "note": note})
        names = {k: a.name for k, a in kit.actions.items()}
        stat_lines = [f"Attack (avg / max roll): {d.attack():.0f} / {d.attack(perfect=True):.0f}",
                      f"Critical Hit: {d.crit_stat:.0f}  ->  {100 * stat_summary['crit_chance_vs_target']:.1f}% crit",
                      f"Double (Smite): {100 * d.double:.1f}%   Perfect: {100 * d.perfect:.1f}%",
                      f"Multi-hit: {100 * d.multihit:.1f}%   Weapon Dmg Boost: {100 * d.weapon_amp:.0f}%",
                      f"Damage Boost bucket: {100 * d.amp:.1f}% (+20% Grace at >=25% MP)",
                      f"Combat Speed: {100 * d.combat_speed:.1f}%   Cooldown Red.: {100 * d.cdr:.1f}%",
                      f"DPS  boss: {final.dps:,.0f}   dummy: {final_other.dps:,.0f}" if scenario_name == "boss"
                      else f"DPS  dummy: {final.dps:,.0f}   boss: {final_other.dps:,.0f}",
                      f"vs community build: +{100 * (final.dps / comm_rot.dps - 1):.1f}% (same rotation optimizer)",
                      f"macro execution: {100 * macro.dps_macro / macro.dps_priority:.1f}% of ideal priority"]
        render_build_card(
            str(out / "images" / "build_card.png"),
            title=f"{cls.capitalize()} · Level 45 · Global client data",
            subtitle=f"Optimized for: {scenario_name} · Daevanion {build.daevanion_cost(cd)}/{daev_budget} · "
                     f"Skill points {build.sp_spent()}/203 · Stigma points {build.stigma_spent()}/30",
            skills=actives, passives=passives, stigmas=stig_rows, priority=pr,
            macro={"steps": [names[s] for s in macro.macro_steps],
                   "manual": [names[e[0] if isinstance(e, tuple) else e] for e in macro.manual],
                   "note": "Hold the macro key; press the manual skills when they come off cooldown."},
            stat_lines=stat_lines, weights=res.weights,
            shares=list(final.shares().items()), gear=_gear_lines(loadout),
            links=[f"{k}: {v[:118]}{'…' if len(v) > 118 else ''}" for k, v in links.items()])
    except Exception as err:  # images are a bonus; never fail the report on them
        print("build card failed:", err)
    from .report_md import write_markdown
    from .model.character import load_loadout
    write_markdown(summary, str(out), extra={"gear_lines": _gear_lines(loadout), "weapon_compare": wc,
                                             "loadout_name": load_loadout(loadout).get("name", loadout)})
    if verbose:
        print(f"report written to {out} in {time.time() - t0:.0f}s")
    return summary


def _roll_expectation(item: dict, n_rolls: int, best: int = 0, pu: dict | None = None) -> dict:
    """Expected stats from an item's random rolls (or the ``best`` most valuable ones)."""
    import re as _re
    from .model.character import LABEL_MAP
    pool = []
    for r in item.get("random", []):
        if r["stat"] not in LABEL_MAP:
            continue
        field, scale = LABEL_MAP[r["stat"]]
        nums = [float(x.replace(",", "")) for x in _re.findall(r"[\d,.]+", r["range"])]
        if not nums:
            continue
        pct = "%" in r["range"]
        if pct and scale == 1:
            continue
        ch = float(r["chance"].rstrip("%") or 0) / 100
        pool.append((field, sum(nums) / len(nums) * scale, ch))
    out: dict[str, float] = {}
    if best and pu:
        pool.sort(key=lambda x: -pu.get(x[0], 0.0) * x[1])
        for field, val, _ in pool[:best]:
            out[field] = out.get(field, 0.0) + val
        return out
    tot = sum(ch for _, _, ch in pool) or 1.0
    for field, val, ch in pool:
        out[field] = out.get(field, 0.0) + n_rolls * val * ch / tot
    return out


def weapon_compare(build, scenario, policy, pu) -> list[dict]:
    import copy
    from .model.character import load_loadout
    items = json.loads((Path(__file__).parent / "data" / "global" / "items.json").read_text(encoding="utf-8"))
    base_lo = load_loadout(scenario.loadout) if isinstance(scenario.loadout, str) else scenario.loadout
    main = next((c for c in base_lo["components"] if c["slot"] == "Main hand"), None)
    if build.cls != "sorcerer" or main is None:   # weapon tables below are spellbooks
        return []
    variants = [(f"{main['item']} (this loadout)", None)]
    rt = items.get("rupture-tome", {})
    lg = items.get("ludras-grimoire", {})
    if rt:
        core = {"weapon_min": 248 + 60, "weapon_max": 276 + 60, "crit": 100, "accuracy": 100}
        variants.append(("Rupture Tome +10, average rolls", {**core, **_roll_expectation(rt, 4)}))
        variants.append(("Rupture Tome +10, 3 best rolls", {**core, **_roll_expectation(rt, 4, best=3, pu=pu)}))
    if lg:
        core = {"weapon_min": 473 + 110, "weapon_max": 525 + 110, "crit": 100, "accuracy": 100}
        variants.append(("Ludra's Grimoire +10, average rolls", {**core, **_roll_expectation(lg, 3)}))
        variants.append(("Ludra's Grimoire +10, 3 best rolls", {**core, **_roll_expectation(lg, 3, best=3, pu=pu)}))
    rows, base = [], None
    for name, stats in variants:
        lo = copy.deepcopy(base_lo)
        if stats:
            for comp in lo["components"]:
                if comp["slot"] == "Main hand":
                    comp["stats"] = stats
                    comp["item"] = name
        sc = replace(scenario, loadout=lo)
        r, _, _ = _sim(build, sc, policy)
        if base is None:
            base = r.dps
        rows.append({"name": name, "dps": r.dps, "gain": r.dps / base - 1, "stats": stats})
    return rows


def _gear_lines(loadout: str) -> list[str]:
    from .model.character import load_loadout
    lo = load_loadout(loadout)
    return [f"{c['slot']}: {c['item']}" for c in lo.get("components", [])]
