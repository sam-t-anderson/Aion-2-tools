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
    gd = data()
    mix = content_mix(encounters, mix, fetch_missing)
    state = genus_state or {}
    lo_all = ctx.assemble(ctx.equipped)
    lo_all["components"].append(genus_component(state, mix))
    with_all = ctx.dps(loadout=lo_all)
    lines = []
    for g, s in state.items():
        for i, ln in enumerate(s.get("lines") or []):
            rest = {**state, g: {**s, "lines": [x for j, x in enumerate(s["lines"]) if j != i]}}
            lo = ctx.assemble(ctx.equipped)
            lo["components"].append(genus_component(rest, mix))
            gain = with_all / ctx.dps(loadout=lo) - 1
            lines.append({"genus": g, "slot": ln.get("slot"), "stat": ln.get("stat"), "value": ln.get("value"),
                          "gain": gain})
    lines.sort(key=lambda r: r["gain"])
    dmg = gd["genus_lines"]["damage_boost"]
    mid = sum(dmg["range_pct"]) / 2
    chase = []
    for g in MAIN:
        lo = ctx.assemble(ctx.equipped)
        lo["components"].append(genus_component({**state, "_": {"lines": [
            {"stat": f"{g} Damage Boost", "value": f"{mid}%"}]}}, mix))
        chase.append({"genus": g, "line": f"{g} Damage Boost", "value": f"{mid:.1f}% (range {dmg['range_pct'][0]}-"
                      f"{dmg['range_pct'][1]}%)", "slots": dmg["slots"], "share": mix.get(g, 0.0),
                      "gain": ctx.dps(loadout=lo) / with_all - 1})
    chase.sort(key=lambda r: -r["gain"])
    levels = []
    for g in sorted(GENERA, key=lambda g: -mix.get(g, 0.0)):
        lv = (state.get(g) or {}).get("level", 0)
        table = {x["level"]: x for x in (gd["genera"].get(g) or {}).get("levels", [])}
        nxt = table.get(lv + 1)
        levels.append({"genus": g, "level": lv, "share": mix.get(g, 0.0),
                       "next": nxt and {"level": nxt["level"], "opens_slot": nxt.get("slot_opened"),
                                        "grades": nxt.get("grades")}})
    return {"mix": mix, "dps_with_lines": with_all, "lines": lines,
            "reroll_first": [r for r in lines if r["gain"] <= 1e-6][:6],
            "chase": chase, "level_order": levels,
            "note": "Genus lines that only count against one genus are weighted by that genus's share of "
                    "your fight time."}
