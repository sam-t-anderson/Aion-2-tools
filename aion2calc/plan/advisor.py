"""Everything the planners say about one character, ranked by DPS gain.

``advise`` runs, on the character's own gear and points (and on the model
calibrated from its fights when there are enough):

* gear: the best set from the inventory, the goal items per slot and an upgrade path
* arcana: variant, options to chase, keep / replace for owned arcana
* pantheon: deity stats by value per point and the choices that move them
* genus insight: line values, rerolls, which genus to level
* rotation: what the character's saved fights show (casts per skill against the
  optimal rotation, idle time, specializations)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import learn
from ..db import store
from . import inventory as INV
from .arcana import plan_arcana
from .context import PlanContext
from .gear import best_equip, goal_gear, upgrade_path
from .genus import plan_genus
from .pantheon import plan_pantheon


def fights_of(name: str, cls: str) -> list[dict]:
    conn = store.connect()
    return [e for e in store.encounters(conn, cls) if (e.get("player") or "").lower() == name.lower()]


def rotation_findings(name: str, cls: str, build=None, limit: int = 8) -> dict:
    """Patterns across the character's fights (each compared with the optimal rotation)."""
    from ..combat.analyze import vs_optimal
    conn = store.connect()
    tips: dict = {}
    specs: dict = {}
    idle, n = 0.0, 0
    for row in fights_of(name, cls)[:limit]:
        enc = store.encounter(conn, row["id"])
        try:
            o = vs_optimal(enc, build=build) if build is not None else vs_optimal(enc)
        except Exception:
            continue
        if "error" in o:
            continue
        n += 1
        from ..combat.analyze import analyze
        idle += analyze(enc)["summary"]["idle_seconds"] / max(1.0, enc["meta"]["duration"])
        for r in o["skills"]:
            if r["sim_casts"] >= 3 and r["casts"] < 0.8 * r["sim_casts"]:
                t = tips.setdefault(r["skill"], {"skill": r["skill"], "fights": 0, "casts": 0, "optimal": 0})
                t["fights"] += 1
                t["casts"] += r["casts"]
                t["optimal"] += r["sim_casts"]
        for d in o.get("specs") or []:
            if d["differs"]:
                specs[d["skill"]] = d
    under = sorted(tips.values(), key=lambda t: -(t["optimal"] - t["casts"]))
    return {"fights": n, "idle_share": idle / n if n else None,
            "under_cast": [{**t, "text": f"{t['skill']}: cast {t['casts']}x where the optimal rotation casts "
                                         f"{t['optimal']}x, in {t['fights']} of {n} fights"} for t in under],
            "specs": list(specs.values())}


def advise(imp, inv: dict | None = None, evaluation: dict | None = None, steps: int = 10,
           genus_mix: dict | None = None, progress=None) -> dict:
    say = progress or (lambda m: None)
    t0 = time.time()
    inv = inv or INV.from_character(imp)
    with learn.calibrated(imp.cls) as cal:
        say("scoring the character as it is")
        ctx = PlanContext.from_character(imp, inv, evaluation)
        base = ctx.dps(ctx.equipped)
        say("best gear from your inventory")
        equip = best_equip(ctx, inv)
        say("goal gear per slot")
        goals = goal_gear(ctx)
        say("upgrade path")
        path = upgrade_path(ctx, goals["slots"], steps=steps)
        say("arcana")
        arc = plan_arcana(ctx, inv)
        say("pantheon")
        pan = plan_pantheon(ctx, imp.systems, arc)
        say("genus insight")
        fights = fights_of(imp.name, imp.cls)
        gen = plan_genus(ctx, inv.get("genus"), fights, genus_mix)
        say("your fights")
        rot = rotation_findings(imp.name, imp.cls, ctx.build)
    top = []
    for c in equip["changes"]:
        top.append({"area": "gear (inventory)", "text": f"{c['slot']}: wear {c['to']} instead of {c['from'] or 'nothing'}",
                    "gain": c["gain"]})
    for s in path["steps"][:5]:
        top.append({"area": "gear (upgrade)", "text": f"{s['slot']}: {s['action']}", "gain": s["gain"]})
    for slot in arc["priority"][:3]:
        a = arc["slots"][slot]
        best = ", ".join(f"{k} +{v}" for k, v in a["ideal"]["skills"].items())
        top.append({"area": "arcana", "text": f"{slot}: {a['variant']['name'] if a['variant'] else ''} with {best}",
                    "gain": a["ideal"]["gain"]})
    for ch in pan["choices"]:
        if ch["source"].startswith("Bracelet"):
            top.append({"area": "pantheon", "text": f"bracelet deity roll: {ch['pick']} ({ch['points']})",
                        "gain": ch["gain"]})
    for c in gen["chase"][:1]:
        top.append({"area": "genus insight", "text": f"{c['line']} in slot 4 or 7 ({c['value']})", "gain": c["gain"]})
    for r in gen["reroll_first"][:2]:
        top.append({"area": "genus insight", "text": f"reroll {r['genus']} slot {r['slot']} ({r['stat']} {r['value']}: "
                                                     "no damage)", "gain": None})
    for t in rot["under_cast"][:3]:
        top.append({"area": "rotation", "text": t["text"], "gain": None})
    for d in rot["specs"][:3]:
        top.append({"area": "specializations", "text": f"{d['skill']}: specs {d['yours']} in your fights, "
                                                       f"{d['optimal']} in the optimized build", "gain": None})
    cs = learn.community_stats(imp.cls)
    mine = {d["skill"]: d["yours"] for d in rot["specs"]}
    for row in ((cs or {}).get("top_quarter") or {}).get("specs", [])[:40]:
        pick = row["picks"][0] if row.get("picks") else None
        if pick and pick["share"] >= 0.5 and row["skill"] in mine and mine[row["skill"]] != pick["specs"]:
            top.append({"area": "community", "text": f"{row['skill']}: {100 * pick['share']:.0f}% of the top players on "
                                                     f"your log server pick specs {pick['specs']} (you: {mine[row['skill']]})",
                        "gain": None})
    top.sort(key=lambda r: -(r["gain"] if r["gain"] is not None else -1))
    return {"character": {"name": imp.name, "server": imp.server, "class": imp.cls, "level": imp.level},
            "dps": base, "calibration": learn.summary(learn.calibration(imp.cls)) + [
                f"community calibration from your log server: {c['fights']} fights" for c in
                [learn.community(imp.cls, fetch=False)] if c and c.get("active")], "calibrated": bool(cal),
            "top": top, "equip": equip, "goals": goals, "upgrade_path": path, "arcana": arc,
            "pantheon": pan, "genus": gen, "rotation": rot, "community": cs, "seconds": time.time() - t0}


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:+.1f}%"


def write_markdown(adv: dict, out: Path) -> Path:
    c = adv["character"]
    L = [f"# Advice for {c['name']} ({c['server']}), {c['class'].title()} Lv {c['level']}", "",
         f"Simulated boss DPS as equipped: **{adv['dps']:,.0f}**"
         + (" (model calibrated from your fights)" if adv["calibrated"] else ""), "",
         "## Top changes", "", "| Area | Change | DPS |", "|---|---|---:|"]
    L += [f"| {r['area']} | {r['text']} | {_pct(r['gain'])} |" for r in adv["top"]]
    L += ["", "## Gear", "", f"Best set from your inventory: {_pct(adv['equip']['gain'])}", ""]
    L += [f"* {x['slot']}: {x['to']} (was {x['from']}), {_pct(x['gain'])}" for x in adv["equip"]["changes"]]
    if adv["equip"].get("empty_slots"):
        L += ["", "No inventory items for: " + ", ".join(adv["equip"]["empty_slots"])]
    L += ["", "### Goal gear", "", "| Slot | Next goal | Best |", "|---|---|---|"]
    for slot, g in adv["goals"]["slots"].items():
        n, b = g.get("next"), g["best"][0]
        nxt = f"[{n['name']}]({n['url']}) {_pct(n['gain'])}" if n else "—"
        L.append(f"| {slot} | {nxt} | [{b['name']}]({b['url']}) +{b['enchant']} {_pct(b['gain'])} |")
    L += ["", "### Upgrade path (toward the next goals)", "", "| # | Slot | Step | Gain | Total |", "|---:|---|---|---:|---:|"]
    L += [f"| {s['step']} | {s['slot']} | {s['action']} | {_pct(s['gain'])} | {_pct(s['total_gain'])} |"
          for s in adv["upgrade_path"]["steps"]]
    L += ["", "## Arcana", "", "| Slot | Variant | Chase | Ideal Unique +5 | Expected +5 |", "|---|---|---|---|---:|"]
    for slot in adv["arcana"]["priority"]:
        a = adv["arcana"]["slots"][slot]
        L.append(f"| {slot} | {a['variant']['name'] if a['variant'] else ''} ({a['variant']['deity'] if a['variant'] else ''}) | "
                 + ", ".join(x["skill"] for x in a["chase"][:3]) + " | "
                 + ", ".join(f"{k} +{v}" for k, v in a["ideal"]["skills"].items()) + f" ({_pct(a['ideal']['gain'])}) | "
                 + f"{_pct(a['expected'].get('unique_5'))} |")
        for o in a["owned"]:
            L.append(f"|  | owned: {o['name']} +{o['enchant']} | {', '.join(f'{k} +{v}' for k, v in o['skills'].items())} | "
                     f"{_pct(o['gain'])} | {o['verdict']} |")
    L += ["", "## Pantheon", "", "| Deity stat | DPS per 10 points | You have |", "|---|---:|---:|"]
    for r in adv["pantheon"]["per_point"]:
        L.append(f"| {r['deity']} | {_pct(r['gain_per_point'] * 10)} | {adv['pantheon']['current'].get(r['deity'], 0):g} |")
    L += ["", "## Genus insight", "", "Fight time by genus: " + ", ".join(f"{g} {100 * v:.0f}%" for g, v in adv["genus"]["mix"].items())]
    for r in adv["genus"]["lines"]:
        L.append(f"* {r['genus']} slot {r['slot']}: {r['stat']} {r['value']} → {_pct(r['gain'])}")
    for r in adv["genus"]["level_order"][:3]:
        L.append(f"* level {r['genus']} (Lv {r['level']}, {100 * r['share']:.0f}% of your fight time)")
    rot = adv["rotation"]
    L += ["", "## Your fights", ""]
    if rot["fights"]:
        L.append(f"{rot['fights']} fight(s); idle {100 * (rot['idle_share'] or 0):.0f}% of the time.")
        L += [f"* {t['text']}" for t in rot["under_cast"][:6]]
    else:
        L.append("No saved fights for this character yet: import AbyssLogs links on the Combat Logs page.")
    L += ["", "## Model calibration", ""] + [f"* {x}" for x in adv["calibration"]]
    out.mkdir(parents=True, exist_ok=True)
    (out / "advice.json").write_text(json.dumps(adv, indent=1, default=str), encoding="utf-8")
    p = out / "ADVICE.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p
