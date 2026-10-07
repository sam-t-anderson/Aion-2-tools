"""Frozen manual Genus Insight inputs for character optimization."""
from __future__ import annotations

import copy
import math

from ..plan.genus import GENUS_STATS, MAIN, line_stats, validate_state

SOURCE = "manual-genus-insight"
NOTE = ("Saved manual analysis lines are held fixed while skills, specialties and boards are optimized. "
        "Line gains remove one line from the final build without reoptimizing its rotation; they are not additive. "
        "Defensive effects, owned collection effects and roll probabilities are not simulated. "
        "Recommendations do not replace saved lines or assume new rolls were obtained.")


def prepare(state: dict, mode: str, options: dict | None = None) -> dict:
    options = {} if options is None else options
    if not isinstance(options, dict) or set(options) - {"enabled", "mix"}:
        raise ValueError("Genus options must contain only enabled and mix")
    enabled = options.get("enabled", True)
    if type(enabled) is not bool:
        raise ValueError("Genus enabled must be true or false")
    if mode not in ("pve", "pvp"):
        raise ValueError("Choose PvE or PvP for Genus scoring")
    mix = {g: .25 for g in MAIN}
    source = "Assumed equal mix of Cogni, Fera, Natura and Varian"
    if options.get("mix") is not None:
        raw = options["mix"]
        if not isinstance(raw, dict) or not raw or set(raw) - {*MAIN, "Special"}:
            raise ValueError("Genus mix must use the five known genera")
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > 100 for v in raw.values()):
            raise ValueError("Genus mix weights must be finite numbers from 0 to 100")
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("Give at least one genus a positive weight")
        mix = {g: v / total for g, v in raw.items()}
        source = "User-assumed enemy mix"
    clean = validate_state(state) if enabled else {}
    rows, stats = [], {}
    for genus, group in clean.items():
        for line in group["lines"]:
            conditional = any(line["stat"].startswith(g + " ") for g in (*MAIN, "Special"))
            values = line_stats(line["stat"], line["value"], genus, mix)
            reason = ""
            if mode == "pvp" and conditional:
                values = {}
                reason = "Genus-specific applicability to players is unverified"
            elif set(values) & {"might", "precision"}:
                values = {}
                reason = "Primary stats already come from official profile totals"
            elif conditional and "%" in line["value"] and GENUS_STATS.get(line["stat"].split(" ", 1)[1], (None, None))[1] == 1:
                values = {}
                reason = "Percentage form of this flat stat is unsupported"
            elif not values:
                reason = "Unsupported damage effect or defensive effect"
            elif mode == "pvp" and set(values) <= {"amp_pve", "pve_atk", "amp_boss", "boss_atk"}:
                values = {}
                reason = "PvE/boss effect does not apply to this player target"
            elif mode == "pve" and set(values) <= {"amp_pvp", "pvp_atk"}:
                values = {}
                reason = "PvP effect does not apply to this monster target"
            elif not any(values.values()):
                reason = "No share of the assumed enemy mix"
            rows.append({"genus": genus, **line, "stats": values, "reason": reason})
            for key, value in values.items():
                stats[key] = stats.get(key, 0.) + value
    return {"enabled": enabled, "mode": mode, "source": "Saved manual Genus Insight", "state": clean,
            "mix": mix if mode == "pve" else {}, "mix_source": source if mode == "pve" else "Not used for player targets",
            "stats": stats, "lines": rows, "note": NOTE + (" PvE uses a weighted-stat approximation, not separate simulations per genus."
            if mode == "pve" else " PvP is a stationary damage proxy, not a survivability or win-rate model.")}


def apply(loadout: dict, plan: dict | None) -> dict:
    result = copy.deepcopy(loadout)
    if plan is None:
        return result
    result["components"] = [c for c in result.get("components", []) if c.get("source") != SOURCE]
    if plan["enabled"] and plan["stats"]:
        result["components"].append({"slot": "Genus Insight", "item": "Saved manual analysis lines",
                                     "source": SOURCE, "stats": copy.deepcopy(plan["stats"])})
    return result


def assess(plan: dict | None, build, scenario, policy) -> dict | None:
    if plan is None:
        return None
    from ..report import _sim
    result = copy.deepcopy(plan)
    if not plan["enabled"] or not plan["stats"]:
        return result
    full = _sim(build, scenario, policy)[0].dps
    result["dps_with_lines"] = full
    from dataclasses import replace
    for row in result["lines"]:
        if row["reason"] or not any(row["stats"].values()):
            row["gain"] = None
            continue
        rest = copy.deepcopy(plan)
        for key, value in row["stats"].items():
            rest["stats"][key] -= value
        # Preserve all target/config choices from the scored scenario.
        lo = apply(scenario.loadout, rest)
        reduced = replace(scenario, loadout=lo)
        without = _sim(build, reduced, policy)[0].dps
        row["gain"] = full / without - 1 if without > 0 else None
    result["review_first"] = sorted(
        [{"genus": x["genus"], "slot": x["slot"], "gain": x.get("gain")} for x in result["lines"]],
        key=lambda x: x["gain"] if x["gain"] is not None else 0.)[:6]
    return result
