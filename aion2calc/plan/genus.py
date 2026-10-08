"""Genus Insight planning (the stat side of the Pets window).

Each genus (Cogni, Fera, Natura, Varian, Special) has its own Insight with nine
analysis slots, one stat line each; slots open with the genus's Insight level
(Lv. 1-9, Lv. 10 raises the grade chances). Lines named after a genus
("Cogni Attack", "Fera Damage Boost") only count against monsters of that
genus, so their value depends on what you fight: the planner weighs them by the
genus mix of your saved fights (boss genus from metabot), or a mix you give.

Your lines are entered in the app (Gear page) or the inventory JSON::

    "genus": {"Cogni": {"level": 7, "lines": [{"slot": 4, "stat": "Cogni Damage Boost", "value": "3.6%"}]}}
"""
from __future__ import annotations

import re
import math

from ..model.character import LABEL_MAP
from ..paths import read_json
from ..sources.monsters import GENERA, genus_of
from .context import PlanContext

DEFENSIVE = ("Defense", "Evasion", "Block", "Resist", "Tolerance", "HP", "MP", "Regen", "Move Speed",
             "Stamina", "Mount", "Flight")
#: words after the genus name -> Stats field and scale (percent values divided by 100)
GENUS_STATS = {"Attack": ("attack", 1), "Damage Boost": ("amp_all", 0.01), "Damage Amplification": ("amp_all", 0.01),
               "Critical Hit": ("crit", 1), "Accuracy": ("accuracy", 1), "Penetration": ("pen", 1)}
MAIN = ("Cogni", "Fera", "Natura", "Varian")


def data() -> dict:
    return read_json("global", "genus_insight.json")


def validate_state(value):
    """Validate manual allocations before replacing a saved inventory's genus state."""
    if not isinstance(value, dict) or len(value) > 5:
        raise ValueError("Genus allocations must be an object with at most five genera")
    result = {}
    for genus, state in value.items():
        if genus not in (*MAIN, "Special") or not isinstance(state, dict):
            raise ValueError("Choose Cogni, Fera, Natura, Varian or Special")
        level = state.get("level", 0)
        if type(level) is not int or not 0 <= level <= 10:
            raise ValueError(f"{genus}: Insight level must be an integer from 0 to 10")
        lines = state.get("lines", [])
        if not isinstance(lines, list) or len(lines) > 9:
            raise ValueError(f"{genus}: use at most nine analysis lines")
        seen, clean = set(), []
        for line in lines:
            if not isinstance(line, dict):
                raise ValueError(f"{genus}: each analysis line must be an object")
            slot = line.get("slot")
            if type(slot) is not int or not 1 <= slot <= min(level, 9) or slot in seen:
                raise ValueError(f"{genus}: use each unlocked slot once (slots 1–{min(level, 9)})")
            stat = line.get("stat")
            if not isinstance(stat, str) or not stat.strip() or len(stat.strip()) > 100:
                raise ValueError(f"{genus} slot {slot}: enter a stat name (up to 100 characters)")
            raw = line.get("value")
            text = str(raw).strip()
            if isinstance(raw, bool) or len(text) > 40 or not re.fullmatch(r"\+?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?", text):
                raise ValueError(f"{genus} slot {slot}: enter a nonnegative number, with % when shown in game")
            number = float(text.rstrip("%").replace(",", ""))
            if not math.isfinite(number) or number > 1e9:
                raise ValueError(f"{genus} slot {slot}: value exceeds the supported range")
            seen.add(slot)
            clean.append({"slot": slot, "stat": stat.strip(), "value": text})
        result[genus] = {"level": level, "lines": sorted(clean, key=lambda row: row["slot"])}
    return result


def coverage(state, lines=()):
    """Coverage of manually recorded allocations, never inferred ownership."""
    rows = []
    for genus in (*MAIN, "Special"):
        group = state.get(genus)
        level = group["level"] if group is not None else None
        unlocked = min(level, 9) if level is not None else None
        saved = len(group["lines"]) if group is not None else 0
        modeled = sum(1 for line in lines if line["genus"] == genus and not line.get("reason")
                      and any(line.get("stats", {}).values()))
        rows.append({"genus": genus, "level": level, "unlocked_slots": unlocked,
                     "recorded_lines": saved, "modeled_lines": modeled,
                     "missing_lines": unlocked-saved if unlocked is not None else None,
                     "next_slot_level": level+1 if level is not None and level < 9 else None,
                     "next_grade_level": 10 if level == 9 else None,
                     "status": "not_recorded" if level is None else "complete" if saved == unlocked else "partial"})
    return {"genera": rows, "recorded_genera": sum(r["level"] is not None for r in rows),
            "recorded_lines": sum(r["recorded_lines"] for r in rows),
            "modeled_lines": sum(r["modeled_lines"] for r in rows),
            "catalog_max_level": 10, "catalog_slots": 9,
            "source": data().get("source", "Bundled Genus catalog"),
            "note": "Missing levels and lines are not zero-valued or empty in-game slots. Catalog limits are not proof of owned progression. Unsupported and defensive effects are preserved, not recommended for reroll based on damage."}


def content_mix(encounters: list[dict] | None = None, given: dict | None = None,
                fetch_missing: bool = True) -> dict:
    """Share of fight time per genus: ``given``, else the saved fights, else even."""
    if given:
        tot = sum(given.values()) or 1.0
        return {g: v / tot for g, v in given.items()}
    t: dict = {}
    for e in encounters or []:
        g = genus_of(e.get("boss"), fetch_missing=fetch_missing)
        if g:
            t[g] = t.get(g, 0.0) + (e.get("duration") or 0.0)
    if t:
        tot = sum(t.values())
        return {g: v / tot for g, v in sorted(t.items(), key=lambda kv: -kv[1])}
    return {g: 1 / len(MAIN) for g in MAIN}


def line_stats(stat: str, value, genus: str, mix: dict) -> dict:
    """One analysis line -> Stats fields, genus lines scaled by that genus's share."""
    text = str(value)
    nums = re.findall(r"-?\d[\d,]*\.?\d*", text)
    if not nums:
        return {}
    v = float(nums[0].replace(",", ""))
    pct = "%" in text
    stat = stat.strip()
    if any(w in stat for w in DEFENSIVE):
        return {}
    for g in GENERA:
        if stat.startswith(g + " "):
            rest = stat[len(g) + 1:]
            if rest in GENUS_STATS:
                f, sc = GENUS_STATS[rest]
                val = v / 100 if pct else v * sc
                return {f: val * mix.get(g, 0.0)}
            return {}
    if stat in LABEL_MAP:
        f, sc = LABEL_MAP[stat]
        if pct and sc == 1:
            return {}
        return {f: v / 100 if pct else v * sc}
    return {}


def genus_component(genus_state: dict, mix: dict) -> dict:
    st: dict = {}
    for g, s in (genus_state or {}).items():
        for ln in s.get("lines") or []:
            for k, v in line_stats(ln.get("stat", ""), ln.get("value", ""), g, mix).items():
                st[k] = st.get(k, 0.0) + v
    return {"slot": "Genus Insight", "item": "pet genus insight lines", "stats": st}


def plan_genus(ctx: PlanContext, genus_state: dict | None, encounters: list[dict] | None = None,
               mix: dict | None = None, fetch_missing: bool = True) -> dict:
    """Value of every line you have, what to reroll first, and which genus to level."""
    from ..opt.genus import prepare, apply
    import copy
    mode = "pvp" if ctx.scenario.startswith("pvp") else "pve"
    mix = content_mix(encounters, mix, fetch_missing)
    plan = prepare(genus_state or {}, mode, {"mix": mix})
    state = plan["state"]
    base_loadout = ctx.assemble(ctx.equipped)
    with_all = ctx.dps(loadout=apply(base_loadout, plan))
    lines = []
    for scored in plan["lines"]:
        line = copy.deepcopy(scored)
        line["gain"] = None
        if not line["reason"] and any(line["stats"].values()):
            rest = copy.deepcopy(plan)
            for key, value in line["stats"].items():
                rest["stats"][key] -= value
            without = ctx.dps(loadout=apply(base_loadout, rest))
            line["gain"] = with_all/without-1 if without > 0 else None
        lines.append(line)
    lines.sort(key=lambda row: row["gain"] if row["gain"] is not None else float("inf"))
    chase = []
    gd = data()
    dmg = gd["genus_lines"]["damage_boost"]
    mid = sum(dmg["range_pct"])/2
    if mode == "pve":
        for genus, group in state.items():
            if genus not in MAIN:
                continue
            for slot in dmg["slots"]:
                if slot > group["level"]:
                    continue
                old = next((line for line in group["lines"] if line["slot"] == slot), None)
                score = next((line for line in lines if line["genus"] == genus and line["slot"] == slot), None)
                # A defensive/unsupported line must not be called a damage-free reroll.
                if score and (score["reason"] or score["gain"] is None):
                    continue
                candidate = copy.deepcopy(state)
                candidate[genus]["lines"] = [line for line in group["lines"] if line["slot"] != slot]
                candidate[genus]["lines"].append({"slot": slot, "stat": f"{genus} Damage Boost", "value": f"{mid}%"})
                proposed = prepare(candidate, mode, {"mix": mix})
                gain = ctx.dps(loadout=apply(base_loadout, proposed))/with_all-1 if with_all > 0 else None
                if gain is None or gain <= 1e-6:
                    continue
                chase.append({"genus": genus, "slot": slot, "slots": [slot], "line": f"{genus} Damage Boost",
                              "value": f"{mid:g}% (catalog range {dmg['range_pct'][0]}–{dmg['range_pct'][1]}%)",
                              "share": mix.get(genus, 0), "gain": gain, "replaces": old,
                              "assumption": "Replaces the recorded line" if old else "Assumes the unrecorded target slot is empty; actual gain unknown"})
    chase.sort(key=lambda row: -row["gain"])
    cov = coverage(state, lines)
    levels = [{"genus": row["genus"], "level": row["level"], "share": mix.get(row["genus"], 0),
               "next": ({"level": row["next_slot_level"], "opens_slot": row["next_slot_level"]}
                        if row["next_slot_level"] is not None else
                        {"level": 10, "opens_slot": None} if row["next_grade_level"] else None)}
              for row in cov["genera"]]
    levels.sort(key=lambda row: (row["level"] is None, -row["share"], row["genus"]))
    return {"mode": mode, "state": state, "mix": plan["mix"], "mix_source": plan["mix_source"],
            "dps_with_lines": with_all, "lines": lines, "coverage": cov,
            "reroll_first": [], "chase": chase, "level_order": levels,
            "note": plan["note"] + " Candidate gains replace a single unlocked slot and are not additive; absent target lines assume an empty slot. No roll probability, cost or defensive tradeoff is optimized."}
