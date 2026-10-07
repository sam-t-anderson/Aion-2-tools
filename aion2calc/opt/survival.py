"""Explicit flat crystal-board HP constraints and assumed incoming damage scenarios.

No armor, percentage HP, skill shields, CC, movement or win probability formulas
are inferred. Observed HP plus a flat node delta is labeled a proxy.
"""
from __future__ import annotations

import math

from .daevanion import CRYSTAL_BOARDS

NOTE = ("Flat crystal-board HP reserve only. Total HP headroom uses entered current HP plus the "
        "change in flat HPMax nodes; percentage HP, defensive passives, armor, shields, healing skills, "
        "crowd control and movement are not simulated. Incoming damage/healing are user assumptions "
        "after mitigation. Healing timing is assumed, excess healing is not banked and the initial burst remains protected separately. Positive headroom is not a guarantee of survival or a PvP win prediction.")


def node_hp(cd, nodes):
    return sum(float(s["value"]) for nid in nodes if nid in cd.node_index
               and cd.node_index[nid][0]["name"] in CRYSTAL_BOARDS
               for s in cd.node_index[nid][1].get("stats", []) if s.get("stat") == "HPMax")


def number(value, name, maximum=1e9, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be a finite number from {minimum:g} to {maximum:g}")
    return float(value)


def prepare(cd, current, options=None):
    if options is None:
        return None
    if not isinstance(options, dict):
        raise ValueError("Invalid survival options")
    preserve = options.get("preserve_hp", True)
    if type(preserve) is not bool:
        raise ValueError("Preserve HP must be true or false")
    reference = node_hp(cd, current.daevanion)
    floor = max(reference if preserve else 0, number(options.get("min_node_hp", 0), "Minimum crystal HP"))
    hp = options.get("current_hp")
    if hp is not None:
        hp = number(hp, "Current maximum HP", minimum=1)
    scenarios = options.get("opponents", [])
    if not isinstance(scenarios, list) or len(scenarios) > 8:
        raise ValueError("Use at most eight incoming-damage scenarios")
    rows = []
    for row in scenarios:
        if not isinstance(row, dict):
            raise ValueError("Invalid incoming-damage scenario")
        burst = number(row.get("burst_damage", 0), "Burst damage")
        pressure = number(row.get("pressure_dps", 0), "Incoming damage per second")
        window = number(row.get("window_s", 5), "Pressure window", 120, .1)
        healing = number(row.get("healing_hps", 0), "Assumed healing per second")
        delay = number(row.get("healing_delay_s", 0), "Healing delay", 120)
        duration = row.get("healing_duration_s")
        if duration is not None:
            duration = number(duration, "Healing duration", 120)
        healing_start = min(window, delay)
        healing_end = window if duration is None else min(window, healing_start + duration)
        # Healing repays ongoing pressure only. Excess healing cannot be banked,
        # and the initial burst remains a separate minimum HP requirement.
        deficit = peak_pressure = pressure * healing_start
        peak_time = healing_start if peak_pressure else 0.0
        deficit = max(0, deficit + (pressure-healing) * (healing_end-healing_start))
        if deficit > peak_pressure:
            peak_pressure, peak_time = deficit, healing_end
        deficit += pressure * (window-healing_end)
        if deficit > peak_pressure:
            peak_pressure, peak_time = deficit, window
        reserve = number(row.get("reserve_hp", 1), "HP reserve", minimum=1)
        required = burst + peak_pressure + reserve
        rows.append({"name": str(row.get("name") or "Incoming pressure")[:100], "burst_damage": burst,
                     "pressure_dps": pressure, "window_s": window, "healing_hps": healing,
                     "healing_delay_s": delay, "healing_duration_s": duration,
                     "healing_active_s": healing_end-healing_start,
                     "peak_pressure_hp": peak_pressure, "peak_pressure_at_s": peak_time,
                     "reserve_hp": reserve, "required_hp": required, "source": "user_assumption"})
        evidence = row.get("recorded_evidence")
        if isinstance(evidence, dict):
            # Provenance is user-imported context, never authenticated telemetry.
            rows[-1]["recorded_evidence"] = {k: str(evidence[k])[:200] for k in
                ("title", "recipient", "recipient_id", "segment", "window_s", "start_s", "end_s", "damage", "largest_hit", "damage_events") if k in evidence}
        benchmark = row.get("opponent_benchmark")
        if isinstance(benchmark, dict):
            rows[-1]["opponent_benchmark"] = {k: str(benchmark[k])[:500] for k in
                ("title", "created", "class", "metric", "modeled_dps", "scale", "source_duration_s", "duration_source", "model_note") if k in benchmark}
    if rows and hp is None:
        raise ValueError("Enter your current maximum HP before using incoming-damage scenarios")
    if not preserve and floor == 0 and not rows:
        return None
    if rows:
        floor = max(floor, reference + max(r["required_hp"] for r in rows) - hp)
    available = node_hp(cd, {nid for nid, (_, node) in cd.node_index.items() if node.get("type") != "Start"})
    if floor > available+1e-6:
        raise ValueError(f"Requested crystal HP reserve {floor:,.0f} exceeds the catalog's total {available:,.0f}, even before point/connectivity costs. Lower the reserve or incoming-damage assumptions.")
    return {"version": 2, "preserve_hp": preserve, "reference_node_hp": reference,
            "minimum_node_hp": max(0, floor), "current_hp": hp, "opponents": rows, "note": NOTE}


def assessment(cd, build, plan):
    if plan is None:
        return None
    hp = node_hp(cd, build.daevanion)
    total = None if plan["current_hp"] is None else plan["current_hp"] + hp - plan["reference_node_hp"]
    rows = [{**r, "headroom_hp": total-r["required_hp"], "meets_assumed_pressure": total >= r["required_hp"]}
            for r in plan["opponents"]]
    return {**plan, "selected_node_hp": hp, "meets_node_floor": hp+1e-6 >= plan["minimum_node_hp"],
            "estimated_total_hp_proxy": total, "opponents": rows,
            "worst_headroom_hp": min((r["headroom_hp"] for r in rows), default=None)}


def recorded_pressure(document, segment=None, target=None, window_s=5):
    """Extract gross recorded damage windows, without inferring mitigation or healing."""
    from ..combat.a2log import validate, combat_mode
    doc = validate(document)
    names = {p["id"]: p["name"] for p in doc["players"]}
    choices = []
    for index, fight in enumerate(doc["segments"]):
        targets = sorted({e["target"] for e in fight.get("events", [])
                          if e["kind"] == "damage" and e.get("target") in names and e["amount"] > 0})
        if targets:
            choices.append({"index": index, "label": fight.get("label") or f"Encounter {index+1}",
                            "mode": combat_mode(doc, fight),
                            "targets": [{"id": pid, "name": names[pid]} for pid in targets]})
    if segment is None:
        return {"encounters": choices}
    if type(segment) is not int or not 0 <= segment < len(doc["segments"]):
        raise ValueError("Choose an encounter from this recording")
    fight = doc["segments"][segment]
    window = number(window_s, "Recorded damage window", 120, .1)
    if target not in names:
        raise ValueError("Choose a recorded player recipient")
    events = sorted((e for e in fight.get("events", []) if e["kind"] == "damage"
                     and e.get("target") == target and e["amount"] > 0), key=lambda e: e["t"])
    if not events:
        raise ValueError("No damage with this player as recipient was recorded")
    from collections import deque
    deaths = [e for e in fight.get("events", []) if e["kind"] == "death" and e.get("target") == target]
    records = sorted(events + deaths, key=lambda e: (e["t"], e["kind"] == "death"))
    # Inclusive windows preserve simultaneous hits; recorded deaths separate lives.
    active = deque()
    running = peak = 0.0
    start = end = 0.0
    for event in records:
        if event["kind"] == "death":
            active.clear()
            running = 0.0
            continue
        active.append(event)
        running += event["amount"]
        while event["t"] - active[0]["t"] > window:
            running -= active.popleft()["amount"]
        if running > peak:
            peak, start, end = running, active[0]["t"], event["t"]
    number(peak, "Recorded peak damage")
    label = fight.get("label") or f"Encounter {segment+1}"
    evidence = {"title": str(doc.get("meta", {}).get("title") or label)[:200],
                "recipient": names[target], "recipient_id": target, "segment": segment,
                "window_s": window, "start_s": start, "end_s": end, "damage": peak,
                "largest_hit": max(e["amount"] for e in events), "damage_events": len(events)}
    return {"scenario": {"name": f"{names[target]} · {label}"[:100], "burst_damage": peak,
                         "pressure_dps": 0, "window_s": window, "healing_hps": 0,
                         "reserve_hp": 1, "recorded_evidence": evidence}}


def opponent_pressure(document, metric, scale, window_s):
    """Use a saved optimized PvP score as an explicit, user-scaled pressure assumption."""
    from ..app.history import validate
    from ..combat.a2log import CLASSES
    doc = validate(document)
    if doc["kind"] not in ("optimize-character", "optimize-class"):
        raise ValueError("Choose an exported optimized PvP result, not advice or a combat log")
    view = doc["result"].get("optimized") if doc["kind"] == "optimize-character" else doc["result"]
    if not isinstance(view, dict) or view.get("scenario") not in ("pvp", "pvp_burst") or view.get("class") not in CLASSES:
        raise ValueError("This saved result is not an optimized PvP build")
    if metric not in ("pvp", "pvp_burst"):
        raise ValueError("Choose sustained or burst PvP benchmark")
    scores = view.get("dps")
    if not isinstance(scores, dict) or metric not in scores:
        raise ValueError("This result does not include the selected PvP damage estimate")
    dps = number(scores[metric], "Saved PvP modeled DPS")
    factor = number(scale, "Assumed incoming damage scale", 10)
    window = number(window_s, "Opponent pressure window", 120, .1)
    objective = view.get("objective") or {}
    durations = objective.get("durations") or {}
    source_duration = number(durations.get(metric, 30 if metric == "pvp_burst" else 180), "Benchmark duration", 3600, .1)
    if window > source_duration:
        raise ValueError("Pressure window cannot exceed the source benchmark duration")
    pressure = number(dps * factor, "Scaled incoming damage per second")
    evidence = {"title": doc["title"], "created": doc["created"], "class": view["class"],
                "metric": metric, "modeled_dps": dps, "scale": factor,
                "source_duration_s": source_duration,
                "duration_source": "saved objective" if metric in durations else "legacy scenario default",
                "model_note": str(view.get("model_note") or "Original model assumptions not recorded")[:500]}
    return {"scenario": {"name": f"{view['class']} · {metric} benchmark"[:100],
                         "burst_damage": 0, "pressure_dps": pressure, "window_s": window,
                         "healing_hps": 0, "reserve_hp": 1, "opponent_benchmark": evidence}}
