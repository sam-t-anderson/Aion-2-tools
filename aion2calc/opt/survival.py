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
        "after mitigation. Positive headroom is not a guarantee of survival or a PvP win prediction.")


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
        reserve = number(row.get("reserve_hp", 1), "HP reserve", minimum=1)
        required = burst + max(0, pressure-healing)*window + reserve
        rows.append({"name": str(row.get("name") or "Incoming pressure")[:100], "burst_damage": burst,
                     "pressure_dps": pressure, "window_s": window, "healing_hps": healing,
                     "reserve_hp": reserve, "required_hp": required, "source": "user_assumption"})
        evidence = row.get("recorded_evidence")
        if isinstance(evidence, dict):
            # Provenance is user-imported context, never authenticated telemetry.
            rows[-1]["recorded_evidence"] = {k: str(evidence[k])[:200] for k in
                ("title", "recipient", "recipient_id", "segment", "window_s", "start_s", "end_s", "damage", "largest_hit", "damage_events") if k in evidence}
    if rows and hp is None:
        raise ValueError("Enter your current maximum HP before using incoming-damage scenarios")
    if not preserve and floor == 0 and not rows:
        return None
    if rows:
        floor = max(floor, reference + max(r["required_hp"] for r in rows) - hp)
    available = node_hp(cd, {nid for nid, (_, node) in cd.node_index.items() if node.get("type") != "Start"})
    if floor > available+1e-6:
        raise ValueError(f"Requested crystal HP reserve {floor:,.0f} exceeds the catalog's total {available:,.0f}, even before point/connectivity costs. Lower the reserve or incoming-damage assumptions.")
    return {"version": 1, "preserve_hp": preserve, "reference_node_hp": reference,
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
