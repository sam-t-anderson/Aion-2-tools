"""View models for the app: one dict per in-game window, plus "stats from this system".

Every builder takes plain data (a report summary, an imported character, an
encounter) and returns JSON-ready dicts the front end renders as game screens.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..kit.base import ClassData, spec_slots
from ..model.character import load_loadout, loadout_stats
from ..opt.gear import ARCANA, arcana_choice, enchant_value, per_unit, roll_priorities, title_ranking

SKILL_ICON = "https://metabot.gg/web/aion2/skills/{}.webp"
STIGMA_ICON = "https://metabot.gg/web/aion2/stigma/{}.webp"

#: Stats field -> (label, kind) where kind is "pct" for fractions, "num" otherwise
FIELD_LABELS = {
    "attack": ("Attack", "num"), "weapon_min": ("Weapon min attack", "num"),
    "weapon_max": ("Weapon max attack", "num"), "attack_pct": ("Attack increase", "pct"),
    "crit": ("Critical Hit", "num"), "crit_atk": ("Critical Attack", "num"),
    "crit_dmg": ("Critical Damage Boost", "pct"), "double": ("Double chance", "pct"),
    "perfect": ("Perfect chance", "pct"), "multihit": ("Multi-hit chance", "pct"),
    "amp_all": ("Damage Boost", "pct"), "amp_pve": ("PvE Damage Boost", "pct"),
    "amp_boss": ("Boss Damage Boost", "pct"), "weapon_amp": ("Weapon Damage Boost", "pct"),
    "pve_atk": ("PvE Attack", "num"), "boss_atk": ("Boss Attack", "num"), "front_atk": ("Front Attack", "num"),
    "back_atk": ("Back Attack", "num"), "pen": ("Penetration", "num"), "combat_speed": ("Combat Speed", "pct"),
    "cdr": ("Cooldown Reduction", "pct"), "accuracy": ("Accuracy", "num"), "mp_max": ("MP", "num"),
    "mp_regen": ("MP regen / s", "num"), "might": ("Might", "num"), "precision": ("Precision", "num"),
    "destruction": ("Destruction [Zikel]", "num"), "death": ("Death [Triniel]", "num"),
    "wisdom": ("Wisdom [Lumiel]", "num"), "justice": ("Justice [Nezekan]", "num"),
    "time": ("Time [Siel]", "num"), "illusion": ("Illusion [Kaisinel]", "num"),
    "freedom": ("Freedom [Vaizel]", "num"),
}
DAEV_LABELS = {"FixingDamage": ("Attack", 1, "num"), "Critical": ("Critical Hit", 1, "num"),
               "CombatSpeed": ("Combat Speed", 1e-4, "pct"), "CoolTimeDecrease": ("Cooldown Reduction", 1e-4, "pct"),
               "AmplifyAllDamage": ("Damage Boost", 1e-4, "pct"),
               "AmplifyCriticalDamage": ("Critical Damage Boost", 1e-4, "pct"),
               "AdditionalHitRate": ("Multi-hit chance", 1e-4, "pct"), "MPMax": ("MP", 1, "num"),
               "HPMax": ("HP", 1, "num"), "ArmorDefense": ("Defense", 1, "num"),
               "CriticalResist": ("Critical Hit Resist", 1, "num"),
               "DecreaseDamage": ("Damage Tolerance", 1e-4, "pct"),
               "DecreaseCriticalDamage": ("Critical Damage Tolerance", 1e-4, "pct"),
               "AdditionalHitResistRate": ("Multi-hit Resist", 1e-4, "pct")}


def fmt_stats(stats: dict) -> list[dict]:
    """{field: value} -> [{"label", "value", "text"}] in a stable, readable order."""
    out = []
    order = list(FIELD_LABELS)
    for k in sorted(stats, key=lambda k: order.index(k) if k in order else 999):
        v = stats[k]
        if k == "skill_bonus" or not isinstance(v, (int, float)) or abs(v) < 1e-9:
            continue
        label, kind = FIELD_LABELS.get(k, (k, "num"))
        text = f"{100 * v:+.1f}%" if kind == "pct" else f"{v:+,.0f}" if abs(v) >= 1 else f"{v:+.2f}"
        out.append({"label": label, "value": v, "text": text})
    return out


def _sum(dicts) -> dict:
    tot: dict = {}
    for d in dicts:
        for k, v in d.items():
            if k != "skill_bonus" and isinstance(v, (int, float)):
                tot[k] = tot.get(k, 0) + v
    return tot


def daevanion_view(cd: ClassData, nodes: set, budget: int | None = None) -> dict:
    boards = []
    for b in cd.boards:
        taken = [n for n in b["nodes"] if n["id"] in nodes]
        boards.append({
            "id": b["id"], "name": b["name"],
            "rows": max(n["row"] for n in b["nodes"]), "cols": max(n["col"] for n in b["nodes"]),
            "used": sum(n["cost"] for n in taken), "total": sum(n["cost"] for n in b["nodes"]),
            "nodes": [{"id": n["id"], "row": n["row"], "col": n["col"], "type": n["type"], "grade": n.get("grade"),
                       "cost": n.get("cost", 0), "label": n.get("label") or "", "short": n.get("short") or "",
                       "skill": n.get("skillName"), "skill_id": n.get("skillId"), "selected": n["id"] in nodes}
                      for n in b["nodes"]]})
    raw = cd.daevanion_stats(nodes)
    stats = []
    for k, v in sorted(raw.items(), key=lambda kv: -abs(kv[1])):
        label, scale, kind = DAEV_LABELS.get(k, (cd.raw.get("stat_labels", {}).get(k, k), 1, "num"))
        x = v * scale
        stats.append({"label": label, "text": f"{100 * x:+.1f}%" if kind == "pct" else f"{x:+,.0f}"})
    lv = cd.daevanion_levels(nodes)
    return {"boards": boards, "budget": budget,
            "used": sum(cd.node_index[n][1]["cost"] for n in nodes if n in cd.node_index
                        and cd.node_index[n][0]["name"] != "Azphel"),
            "stats": stats,
            "skills": [{"name": cd.skills[k]["name"], "levels": v} for k, v in sorted(lv.items(), key=lambda kv: -kv[1])]}


def skills_view(cd: ClassData, build, gear_bonus: dict, levels_override: dict | None = None) -> dict:
    dv = cd.daevanion_levels(build.daevanion)
    rows = {"active": [], "passive": []}
    for sid, s in cd.skills.items():
        if s["kind"] not in rows:
            continue
        sp = build.sp.get(sid, 1)
        eff = (levels_override or {}).get(sid) or (sp + dv.get(sid, 0) + gear_bonus.get(sid, 0) + build.bonus.get(sid, 0))
        chosen = set(build.specs.get(sid, ()))
        rows[s["kind"]].append({
            "id": sid, "name": s["name"], "icon": SKILL_ICON.format(sid), "sp": sp, "daev": dv.get(sid, 0),
            "gear": gear_bonus.get(sid, 0), "eff": eff, "slots": spec_slots(eff),
            "specs": [{"id": x["id"], "n": i + 1, "unlock": x["unlock"], "text": x["text"],
                       "chosen": x["id"] in chosen, "available": x["unlock"] <= eff}
                      for i, x in enumerate(s.get("specs", []))]})
    for k in rows:
        rows[k].sort(key=lambda r: (-r["eff"], r["name"]))
    return rows


def stigmas_view(cd: ClassData, build) -> list[dict]:
    out = []
    for sid, lv in build.stigmas.items():
        s = cd.skills[sid]
        out.append({"id": sid, "name": s["name"], "level": lv, "icon": SKILL_ICON.format(sid),
                    "specs": [{"n": i + 1, "unlock": x["unlock"], "text": x["text"], "active": x["unlock"] <= lv,
                               "icon": STIGMA_ICON.format(x["id"])}
                              for i, x in enumerate(s.get("specs", []))]})
    return out


def _catalog_look(name: str) -> dict:
    """Icon and grade for a loadout item name ("Aulamus / Liberator Earrings ~+6" -> Aulamus Earrings)."""
    import re as _re
    try:
        from ..db import store
        conn = store.connect()
    except Exception:
        return {}
    base = _re.sub(r"\s*[~+]\+?\d+.*$", "", name or "").strip()
    first = base.split(" / ")[0].strip()
    if " / " in base and len(first.split()) == 1:          # "Aulamus / Liberator Earrings"
        first = first + " " + base.split()[-1]
    for cand in (base, first):
        row = conn.execute("SELECT icon, grade FROM items WHERE name = ? COLLATE NOCASE LIMIT 1", (cand,)).fetchone()
        if row:
            return {"icon": row[0], "grade": row[1]}
    return {}


def _class_ok(item: dict, cls: str | None) -> bool:
    c = ((item or {}).get("meta") or {}).get("Class")
    if not c or not cls:
        return True
    names = {cls.lower(), "elementalist" if cls == "spiritmaster" else cls.lower()}
    return any(n in c.lower() for n in names)


def equipment_view(lo: dict, weights: list | None, cls: str | None = None) -> dict:
    comps = lo.get("components", [])
    gear_like = [c for c in comps if not c["slot"].startswith(("Title", "Attack title", "Other title",
                                                               "Defense title", "Owned titles", "Wings",
                                                               "Primary/deity", "Gear skill", "Arcana"))]
    slots = [{"slot": c["slot"], "item": c.get("item"), "source": c.get("source"), **_catalog_look(c.get("item", "")),
              "stats": fmt_stats({k: v for k, v in c.get("stats", {}).items() if k != "skill_bonus"})}
             for c in gear_like]
    pu = per_unit(weights) if weights else {}
    rolls = {}
    if pu:
        from ..paths import read_json
        ref = read_json("global", "items.json")
        rolls = {k: v for k, v in roll_priorities(pu, ref).items() if _class_ok(ref.get(k), cls)}
    return {"slots": slots, "total": fmt_stats(_sum(c.get("stats", {}) for c in gear_like)),
            "rolls": {k: v[:5] for k, v in rolls.items()},
            "enchant": enchant_value(pu) if pu else []}


def extras_view(lo: dict, weights: list | None, summary: dict | None) -> dict:
    comps = lo.get("components", [])
    titles = [c for c in comps if "title" in c["slot"].lower()]
    wings = [c for c in comps if c["slot"] == "Wings"]
    deity = [c for c in comps if c["slot"].startswith("Primary/deity")]
    pu = per_unit(weights) if weights else {}
    arc = arcana_choice(pu) if pu else {}
    return {
        "titles": [{"slot": c["slot"], "item": c.get("item"), "stats": fmt_stats(c.get("stats", {}))} for c in titles],
        "titles_total": fmt_stats(_sum(c.get("stats", {}) for c in titles)),
        "title_ranking": title_ranking(pu)[:10] if pu else [],
        "wings": [{"item": c.get("item"), "stats": fmt_stats(c.get("stats", {}))} for c in wings],
        "deity": fmt_stats(_sum(c.get("stats", {}) for c in deity)),
        "arcana": [{"slot": slot, "pick": a["pick"], "stat": a["stat"], "tie": a.get("tie"),
                    "variants": {name: f"{st.capitalize()} +{pts}" for name, (st, pts) in ARCANA[slot].items()}}
                   for slot, a in arc.items()],
        "arcana_rolls": (summary or {}).get("arcana_rolls") or {},
    }


def build_view(summary: dict) -> dict:
    """A report summary (build.json) -> every planner window."""
    from ..report import build_from_summary
    cls = summary["class"]
    cd = ClassData(cls)
    build, policy = build_from_summary(summary)
    loadout = summary.get("loadout") or f"{cls}_l45_global_median"
    lo = load_loadout(loadout)
    gear = loadout_stats(lo).skill_bonus
    weights = summary.get("weights") or []
    budgets = summary.get("budgets") or {"skill": 203, "stigma": 30,
                                         "daevanion": summary.get("daevanion_budget", 360)}
    return {
        "class": cls, "loadout": loadout, "loadout_name": lo.get("name"), "scenario": summary.get("scenario"),
        "dps": summary.get("dps"), "baseline": summary.get("baseline"), "budgets": budgets,
        "points": {"skill": build.sp_spent(), "stigma": build.stigma_spent(), "daevanion": build.daevanion_cost(cd)},
        "skills": skills_view(cd, build, gear),
        "stigmas": stigmas_view(cd, build),
        "daevanion": daevanion_view(cd, build.daevanion, budgets.get("daevanion")),
        "equipment": equipment_view(lo, weights, cls),
        "extras": extras_view(lo, weights, summary),
        "macro": summary.get("macro"), "policy": summary.get("policy"), "opener": summary.get("opener"),
        "stats": summary.get("stats"), "weights": weights[:12], "shares": summary.get("shares"),
        "links": summary.get("links"), "gear_skill_rolls": [{"name": cd.skills[k]["name"], "levels": v}
                                                            for k, v in gear.items() if k in cd.skills],
    }


def list_results(root: str | Path = "results") -> list[dict]:
    """Optimized builds, main class reports first (results/<class>_l45*), then comparisons."""
    out = []
    for p in sorted(Path(root).glob("**/build.json")):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if "class" not in s or s.get("kind") == "current":
            continue
        out.append({"path": str(p.parent), "class": s["class"], "loadout": s.get("loadout"),
                    "dps": s.get("dps"), "scenario": s.get("scenario"), "budgets": s.get("budgets")})
    out.sort(key=lambda r: (len(Path(r["path"]).parts), "compare" in r["path"], "characters" in r["path"],
                            r["class"] != "sorcerer", r["path"]))
    return out


def character_view(imp, evaluation: dict | None = None) -> dict:
    """An imported character in the same windows as the planner, plus its real gear details."""
    cd = ClassData(imp.cls)
    sysm = imp.systems
    totals = {}
    for s in sysm.get("skills", []):
        sk = cd.skills.get(s["id"]) or cd.by_name.get(s["name"])
        if sk:
            totals[sk["id"]] = s["level"]
    gear_bonus = {}
    for row in sysm.get("equipment", []) + sysm.get("arcana", []):
        for nm, lv in row.get("skills", []):
            sk = cd.by_name.get(nm)
            if sk:
                gear_bonus[sk["id"]] = gear_bonus.get(sk["id"], 0) + lv
    build = imp.build.copy()
    for name, texts in ((evaluation or {}).get("build") or {}).get("specs", {}).items():
        sk = cd.by_name.get(name)
        if sk:                       # the profile does not publish specs: show the assumed best ones
            build.specs[sk["id"]] = tuple(x["id"] for x in sk.get("specs", []) if x["text"] in texts)
    eq_rows = []
    for row in sysm.get("equipment", []):
        eq_rows.append({"slot": row["slot"], "item": f"{row['name']} +{row.get('enchant') or 0}",
                        "name": row["name"], "grade": row.get("grade"), "enchant": row.get("enchant"),
                        "icon": row.get("icon"), "rolls": row.get("rolls"), "manastones": row.get("manastones"),
                        "theostones": row.get("theostones"), "skills": row.get("skills"),
                        "stats": fmt_stats(row.get("stats", {}))})
    arcana = [{"slot": r["slot"], "name": r["name"], "grade": r.get("grade"), "enchant": r.get("enchant"),
               "icon": r.get("icon"), "skills": r.get("skills"), "stats": fmt_stats(r.get("stats", {}))}
              for r in sysm.get("arcana", [])]
    weights = (evaluation or {}).get("weights") or []
    lo = imp.loadout
    return {
        "class": imp.cls, "key": imp.key, "name": imp.name, "server": imp.server, "level": imp.level,
        "combat_power": imp.combat_power, "loadout": imp.loadout_name(),
        "warnings": imp.warnings + (["specializations are not on the official profile; the skill window shows the "
                                     "best legal ones for your levels (used for the as-is score)"] if evaluation else []),
        "dps": (evaluation or {}).get("dps"), "budgets": (evaluation or {}).get("budgets"),
        "points": {"skill": build.sp_spent(), "stigma": build.stigma_spent(),
                   "daevanion": daevanion_view(cd, build.daevanion)["used"]},
        "skills": skills_view(cd, build, gear_bonus, levels_override=totals),
        "stigmas": stigmas_view(cd, build),
        "daevanion": daevanion_view(cd, build.daevanion),
        "equipment": {"slots": eq_rows, "total": fmt_stats(_sum(r.get("stats", {}) for r in sysm.get("equipment", []))),
                      "rolls": {}, "enchant": []},
        "arcana_items": arcana,
        "extras": {**extras_view(lo, weights, None), "pet": sysm.get("pet"), "wing": sysm.get("wings"),
                   "titles_detail": sysm.get("titles")},
        "profile_stats": sysm.get("profile_stats"),
        "stats": (evaluation or {}).get("stats"), "weights": weights[:12], "policy": (evaluation or {}).get("policy"),
        "shares": (evaluation or {}).get("shares"),
    }
