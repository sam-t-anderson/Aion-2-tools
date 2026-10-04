"""Break an encounter down (AionFlex-style) and compare it with the optimizer.

``analyze``      per-skill table, rates, DPS timeline, idle gaps, buffs, cooldown use
``vs_optimal``   the same fight simulated with the character's build: what the
                 optimal rotation does differently (shares, casts, DPS)
``vs_top``       the class's top Korean training-dummy logs (A2DIL aggregate)
"""
from __future__ import annotations

from collections import defaultdict

from ..kit.base import ClassData


def casts_of(hits: list[dict], cd: ClassData | None = None, level: int = 14, gap: float = 0.35) -> list[dict]:
    """Estimate casts from hit timing.

    Logs record hits, not button presses: multi-hits, zone ticks and delayed hits
    of one cast are grouped (a new cast needs ``gap`` seconds of silence, or 70%
    of the skill's cooldown for skills that have one), and passive procs are not
    casts at all.
    """
    last_hit: dict = {}
    last_cast: dict = {}
    casts = []
    for h in hits:
        if h["dot"]:
            continue
        sid = h.get("skill_id")
        sk = cd.skills.get(sid) if cd and sid else None
        if sk and sk.get("kind") == "passive":
            continue
        key = sid or h["skill"]
        cool = cd.cd(sid, level) if sk else 0.0
        need = max(gap, 0.7 * cool) if cool else gap
        new = key not in last_cast or (h["t"] - last_hit[key] > gap and h["t"] - last_cast[key] >= need)
        if new:
            casts.append({"t": h["t"], "skill": h["skill"], "skill_id": sid})
            last_cast[key] = h["t"]
        last_hit[key] = h["t"]
    return casts


def _rate(rows, key):
    return sum(1 for h in rows if h[key]) / len(rows) if rows else 0.0


def analyze(enc: dict, idle_gap: float = 2.0, level: int = 14) -> dict:
    meta, hits = enc["meta"], enc["hits"]
    dur = meta["duration"] or 1.0
    total = meta["total"] or 1.0
    try:
        cdata = ClassData(meta["class"]) if meta.get("class") else None
    except Exception:
        cdata = None
    casts = casts_of(hits, cdata, level)
    by_skill: dict = defaultdict(list)
    for h in hits:
        by_skill[h["skill"]].append(h)
    cast_n: dict = defaultdict(int)
    first: dict = {}
    for c in casts:
        cast_n[c["skill"]] += 1
        first.setdefault(c["skill"], c["t"])
    cd = cdata
    rows = []
    for name, hs in by_skill.items():
        direct = [h for h in hs if not h["dot"]]
        dmg = sum(h["damage"] for h in hs)
        sid = next((h.get("skill_id") for h in hs if h.get("skill_id")), None)
        cool = cd.cd(sid, level) if cd and sid in getattr(cd, "skills", {}) else 0.0
        possible = (1 + int(dur // cool)) if cool > 0 else None
        kind = cd.skills[sid].get("kind") if cd and sid in cd.skills else None
        rows.append({
            "skill": name, "skill_id": sid, "kind": kind, "damage": dmg, "share": dmg / total, "hits": len(hs),
            "casts": cast_n.get(name, 0), "cpm": 60 * cast_n.get(name, 0) / dur,
            "crit": _rate(direct, "crit"), "double": _rate(direct, "double"), "perfect": _rate(direct, "perfect"),
            "multi": sum(1 for h in direct if h["multi"] > 0) / len(direct) if direct else 0.0,
            "avg_hit": dmg / len(hs) if hs else 0.0, "max_hit": max((h["damage"] for h in hs), default=0.0),
            "dot_share": sum(h["damage"] for h in hs if h["dot"]) / dmg if dmg else 0.0,
            "first_cast": first.get(name), "cooldown": cool or None,
            "cooldown_use": min(1.0, cast_n.get(name, 0) / possible) if possible else None})
    rows.sort(key=lambda r: -r["damage"])

    # DPS timeline: damage per second and a 10 s moving average
    secs = int(dur) + 1
    per_s = [0.0] * secs
    for h in hits:
        per_s[min(secs - 1, int(h["t"]))] += h["damage"]
    rolling = [sum(per_s[max(0, i - 9):i + 1]) / min(10, i + 1) for i in range(secs)]

    # idle time: gaps between cast starts longer than ``idle_gap``
    gaps = []
    for a, b in zip(casts, casts[1:]):
        if b["t"] - a["t"] > idle_gap:
            gaps.append({"start": a["t"], "end": b["t"], "length": b["t"] - a["t"]})
    direct = [h for h in hits if not h["dot"]]
    biggest = max(hits, key=lambda h: h["damage"]) if hits else None
    return {
        "meta": meta,
        "summary": {"dps": meta["dps"], "total": total, "duration": dur, "hits": len(hits), "casts": len(casts),
                    "cpm": 60 * len(casts) / dur, "crit": _rate(direct, "crit"), "double": _rate(direct, "double"),
                    "perfect": _rate(direct, "perfect"),
                    "multi": sum(1 for h in direct if h["multi"] > 0) / len(direct) if direct else 0.0,
                    "front": _rate(direct, "front"), "back": _rate(direct, "back"),
                    "dot_share": sum(h["damage"] for h in hits if h["dot"]) / total,
                    "idle_seconds": sum(g["length"] for g in gaps), "peak_10s": max(rolling, default=0.0),
                    "biggest_hit": biggest and {"skill": biggest["skill"], "damage": biggest["damage"],
                                                "t": biggest["t"]}},
        "skills": rows,
        "timeline": {"per_second": per_s, "rolling10": rolling},
        "gaps": gaps,
        "rotation": [(round(c["t"], 2), c["skill"]) for c in casts[:60]],
        "buffs": sorted(({"name": b["name"], "uptime": b.get("uptime")} for b in enc.get("buffs", [])),
                        key=lambda b: -(b["uptime"] or 0)),
        "specs": enc.get("specs", {}),
    }


def vs_optimal(enc: dict, build=None, loadout: str | None = None, policy=None) -> dict:
    """Simulate the same fight length with ``build`` (default: the class's optimized
    report) and compare shares and casts per skill."""
    import json
    from dataclasses import replace
    from pathlib import Path

    from ..opt.rotation import materialize, optimize_rotation
    from ..report import build_from_summary
    from ..run import prepare
    from ..scenarios import SCENARIOS
    from ..sim.engine import Sim

    cls = enc["meta"]["class"]
    if build is None:
        rep = Path("results") / f"{cls}_l45" / "build.json"
        if not rep.exists():
            rep = Path("results") / "compare" / cls / "build.json"
        if not rep.exists():
            return {"error": f"no optimized build for {cls}; run `python -m aion2calc optimize {cls}` first"}
        summ = json.loads(rep.read_text(encoding="utf-8"))
        build, policy = build_from_summary(summ)
        loadout = loadout or summ.get("loadout")
    loadout = loadout or f"{cls}_l45_global_median"
    scen = SCENARIOS["dummy"](loadout)
    scen = replace(scen, config=replace(scen.config, duration=max(10.0, enc["meta"]["duration"])))
    _, _, kit, stats = prepare(build, scen)
    if policy is None:
        policy = optimize_rotation(stats.derived(), kit, scen.target, scen.config, restarts=1).policy
    pol = [e for e in policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    res = Sim(stats.derived(), kit.actions, materialize(pol), scen.target, scen.config, hooks=kit.hooks,
              cond_mods=kit.cond_mods).run()
    sim_share = res.shares()
    names = {a.name: k for k, a in kit.actions.items()}
    casts_by_sid: dict = {}
    for k, a in kit.actions.items():          # Hellfire charge levels etc. are one skill
        casts_by_sid[a.skill_id] = casts_by_sid.get(a.skill_id, 0) + res.casts.get(k, 0)
    act = analyze(enc)
    rows = []
    for r in act["skills"]:
        base = r["skill"]
        s_share = sum(v for k, v in sim_share.items() if k.split(" (")[0] == base)
        key = names.get(base)
        s_casts = casts_by_sid.get(r.get("skill_id")) if r.get("skill_id") in casts_by_sid else \
            (res.casts.get(key, 0) if key else 0)
        rows.append({"skill": base, "share": r["share"], "sim_share": s_share, "casts": r["casts"],
                     "sim_casts": s_casts, "cast_delta": r["casts"] - s_casts})
    for k, v in sim_share.items():
        base = k.split(" (")[0]
        if base not in {r["skill"] for r in rows}:
            key = names.get(base)
            rows.append({"skill": base, "share": 0.0, "sim_share": v, "casts": 0,
                         "sim_casts": res.casts.get(key, 0) if key else 0,
                         "cast_delta": -(res.casts.get(key, 0) if key else 0)})
    overlap = sum(min(r["share"], r["sim_share"]) for r in rows)
    rows.sort(key=lambda r: -max(r["share"], r["sim_share"]))
    tips = []
    kinds = {r["skill"]: r.get("kind") for r in act["skills"]}
    for r in rows:
        if kinds.get(r["skill"]) == "passive":
            continue
        if r["sim_casts"] >= 3 and r["casts"] < 0.8 * r["sim_casts"]:
            tips.append(f"{r['skill']}: cast {r['casts']}x, the optimal rotation casts it {r['sim_casts']}x "
                        f"in {enc['meta']['duration']:.0f}s — use it on cooldown")
        elif r["sim_casts"] == 0 and r["casts"] >= 3 and r["share"] < 0.02:
            tips.append(f"{r['skill']}: {r['casts']} casts for {100 * r['share']:.1f}% of damage — the optimal "
                        "rotation skips it")
    return {"sim_dps": res.dps, "actual_dps": enc["meta"]["dps"], "share_overlap": overlap, "skills": rows,
            "tips": tips[:8], "comparable_dps": enc["meta"].get("source") not in ("a2dil",),
            "note": None if enc["meta"].get("source") not in ("a2dil",) else
            "Korean logs are on higher-level gear than the global simulation: compare shares and casts, not DPS."}


def vs_top(enc: dict) -> dict:
    """Shares and hits/min against the class's top-10 A2DIL logs."""
    from ..paths import data_file
    import json
    cls = enc["meta"]["class"]
    p = data_file("kr", "a2dil", f"{cls}.json")
    if not p.exists():
        return {}
    top = json.loads(p.read_text(encoding="utf-8"))["skills"]
    cd = ClassData(cls)
    agg: dict = {}
    for v in top.values():
        name = cd.skills[v["code"]]["name"] if v.get("code") in cd.skills else None
        if name:
            a = agg.setdefault(name, {"share": 0.0, "hpm": 0.0})
            a["share"] += v["mean_share"]
            a["hpm"] += v["mean_hits_per_min"]
    act = {r["skill"]: r for r in analyze(enc)["skills"]}
    rows = []
    for name in sorted(set(agg) | set(act), key=lambda n: -max(agg.get(n, {}).get("share", 0),
                                                                act.get(n, {}).get("share", 0))):
        a, t = act.get(name, {}), agg.get(name, {})
        rows.append({"skill": name, "share": a.get("share", 0.0), "top_share": t.get("share", 0.0),
                     "hpm": 60 * a.get("hits", 0) / enc["meta"]["duration"], "top_hpm": t.get("hpm", 0.0)})
    return {"rows": rows[:20], "overlap": sum(min(r["share"], r["top_share"]) for r in rows)}
