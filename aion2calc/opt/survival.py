"""Explicit flat crystal-board HP constraints and assumed incoming damage scenarios.

No armor, percentage HP, skill shields, CC, movement or win probability formulas
are inferred. Observed HP plus a flat node delta is labeled a proxy.
"""
from __future__ import annotations

import math

from .daevanion import CRYSTAL_BOARDS

NOTE = ("Flat crystal-board HP reserve only. Total HP headroom uses entered current HP plus the "
        "change in flat HPMax nodes; percentage HP, defensive passives, armor, shields, healing skills, "
        "crowd control and movement are not inferred. Timed pressure reductions are explicit user assumptions, "
        "not skill casts, guaranteed control or successful avoidance. Linked skills/effects are retained as allocation constraints. Entered effective cooldowns check repeat spacing only; missing cooldowns remain unknown. Overlap uses the strongest reduction only. "
        "Incoming damage/healing are user assumptions "
        "after mitigation. Healing timing is assumed, excess healing is not banked and the separate initial burst remains protected. Timed expected hits use explicit reduction windows; selected opponent windows maximize gross damage before healing/defense, not the mitigated HP requirement across all possible timings. Expected hits do not model random critical spikes or real opponent reactions. Positive headroom is not a guarantee of survival or a PvP win prediction.")


def node_hp(cd, nodes):
    return sum(float(s["value"]) for nid in nodes if nid in cd.node_index
               and cd.node_index[nid][0]["name"] in CRYSTAL_BOARDS
               for s in cd.node_index[nid][1].get("stats", []) if s.get("stat") == "HPMax")


def number(value, name, maximum=1e9, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be a finite number from {minimum:g} to {maximum:g}")
    return float(value)



def pressure_deficit(pressure, window, healing, healing_start, healing_end, reductions=()):
    """Exact peak of reflected, piecewise-constant pressure minus assumed healing.

    The strongest active reduction wins; overlap never adds percentages or
    multiplies them. Initial burst, shields and outgoing damage are separate.
    """
    boundaries = sorted({0.0, window, healing_start, healing_end,
                         *(w["start_s"] for w in reductions), *(w["end_s"] for w in reductions)})
    deficit = peak = peak_time = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        reduction = max((w["reduction_pct"]/100 for w in reductions
                         if w["start_s"] <= start < w["end_s"]), default=0.0)
        hps = healing if healing_start <= start < healing_end else 0.0
        deficit = max(0.0, deficit + (pressure*(1-reduction)-hps)*(end-start))
        if deficit > peak:
            peak, peak_time = deficit, end
    return peak, peak_time


def damage_trace(value, *, maximum_duration=3600):
    """Normalize complete expected hits; never silently truncate imported traces."""
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Missing or unsupported timed damage trace; re-optimize this opponent or use average pressure")
    duration = number(value.get("duration_s"), "Trace duration", maximum_duration, .1)
    total = number(value.get("total"), "Trace total", 1e12)
    events = value.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 50000:
        raise ValueError("Timed damage traces need 1 to 50,000 complete hits")
    clean, previous = [], -1.0
    for event in events:
        if not isinstance(event, list) or len(event) != 2:
            raise ValueError("Invalid timed damage hit")
        t = number(event[0], "Hit time", duration)
        amount = number(event[1], "Expected hit damage")
        if t < previous:
            raise ValueError("Timed damage hits must be chronological")
        clean.append([t, amount])
        previous = t
    if not math.isclose(sum(e[1] for e in clean), total, rel_tol=1e-8, abs_tol=1e-5):
        raise ValueError("Timed damage trace total does not match its hits")
    return {"version": 1, "duration_s": duration, "total": total, "events": clean}


def timed_deficit(trace, pressure, window, healing, healing_start, healing_end, reductions=()):
    """Reflected pressure deficit with instantaneous hits and continuous healing.

    Same-time hits land together; healing cannot pre-pay a hit. Reduction
    intervals are half-open, so a hit exactly at their end is unprotected.
    """
    hits = {}
    for t, amount in trace["events"]:
        hits[t] = hits.get(t, 0.0) + amount
    boundaries = sorted({0.0, window, healing_start, healing_end, *hits,
                         *(w["start_s"] for w in reductions), *(w["end_s"] for w in reductions)})
    deficit = peak = peak_time = 0.0
    previous = 0.0
    for t in boundaries:
        reduction = max((w["reduction_pct"]/100 for w in reductions
                         if w["start_s"] <= previous < w["end_s"]), default=0.0)
        hps = healing if healing_start <= previous < healing_end else 0.0
        deficit = max(0.0, deficit + (pressure*(1-reduction)-hps)*(t-previous))
        if deficit > peak:
            peak, peak_time = deficit, t
        hit_reduction = max((w["reduction_pct"]/100 for w in reductions
                             if w["start_s"] <= t < w["end_s"]), default=0.0)
        deficit += hits.get(t, 0.0)*(1-hit_reduction)
        if deficit > peak:
            peak, peak_time = deficit, t
        previous = t
    return peak, peak_time


def peak_trace_window(trace, window, factor):
    """Select the greatest gross-damage window, before user healing/defense."""
    events = trace["events"]
    left, running, best, start = 0, 0.0, -1.0, 0.0
    for t, amount in events:
        running += amount
        while events[left][0] < t-window-1e-9:
            running -= events[left][1]
            left += 1
        if running > best:
            best = running
            start = min(max(0.0, t-window), trace["duration_s"]-window)
    selected = [[min(window, max(0.0, t-start)), amount*factor] for t, amount in events if start-1e-9 <= t <= start+window+1e-9]
    return start, {"version": 1, "duration_s": window,
                   "total": sum(e[1] for e in selected), "events": selected}


def window_requirement(cd, item, *, action=False):
    sid, effect = item.get("skill_id"), item.get("effect_id")
    requirement = None
    if sid is not None:
        if type(sid) is not int or sid not in cd.skills:
            raise ValueError("Link a known skill from your class to the timing window")
        skill = cd.skills[sid]
        if action and skill["kind"] not in ("active", "stigma"):
            raise ValueError("Outgoing action-time links need an active skill or stigma, not a passive")
        cap = 20 if skill["kind"] == "stigma" else min(10, skill.get("buyMax",10))
        trained = item.get("min_trained", 1)
        if type(trained) is not int or not 1 <= trained <= cap:
            raise ValueError("Linked skill trained minimum must fit its purchasable range")
        catalog = {e["id"]: e for e in skill.get("specs", [])}
        if effect is not None and (type(effect) is not int or skill["kind"] != "active" or effect not in catalog):
            raise ValueError("Link a supporting effect belonging to the selected active skill")
        requirement = {"id": sid, "name": skill["name"], "kind": skill["kind"], "minimum": trained,
                       "effect_id": effect, "effect": catalog[effect]["text"] if effect is not None else None}
    elif effect is not None:
        raise ValueError("Choose a skill before linking its supporting effect")
    cooldown = item.get("cooldown_s")
    if cooldown is not None:
        cooldown = number(cooldown, "Assumed effective cooldown", 3600)
        if sid is None:
            raise ValueError("Link a skill before entering its cooldown")
    return {"skill_requirement": requirement, "skill_id": sid, "effect_id": effect,
            "min_trained": requirement["minimum"] if requirement else 1, "cooldown_s": cooldown}


def reduction_windows(cd, row, window):
    values = row.get("reductions", [])
    if not isinstance(values, list) or len(values) > 8:
        raise ValueError("Use at most eight pressure-reduction windows per scenario")
    result = []
    for item in values:
        if not isinstance(item, dict) or item.get("kind", "defensive") not in ("defensive", "control", "movement"):
            raise ValueError("Choose defensive, control or movement for a pressure window")
        delay = number(item.get("delay_s", 0), "Reduction delay", 120)
        duration = number(item.get("duration_s", 0), "Reduction duration", 120)
        reduction = number(item.get("reduction_pct", 0), "Assumed pressure reduction percent", 100)
        link = window_requirement(cd, item)
        start = min(window, delay)
        end = min(window, delay+duration)
        result.append({"name": str(item.get("name") or "Assumed reduction")[:100],
                       "kind": item.get("kind", "defensive"), "delay_s": delay,
                       "duration_s": duration, "reduction_pct": reduction,
                       "start_s": start, "end_s": end, "active_s": end-start,
                       **link})
    return result


def cooldown_checks(reductions, *, action_duration=None):
    """Validate only user-assumed reuse spacing, separately per encounter.

    All linked skills start ready. A shared start represents one activation
    with multiple effect entries. No charges, resets or shared groups inferred.
    """
    skills = {}
    for w in reductions:
        req = w.get("skill_requirement")
        if req is None:
            continue
        row = skills.setdefault(req["id"], {"skill_id": req["id"], "skill": req["name"],
                                           "starts": set(), "cooldowns": []})
        if w.get("cooldown_s") is not None:
            row["cooldowns"].append(w["cooldown_s"])
        active = (w["duration_s"] > 0 and w["start_s"] < action_duration
                  if action_duration is not None else w["active_s"] > 0 and w["reduction_pct"] > 0)
        if active:
            row["starts"].add(w["start_s"])
    result = []
    for row in skills.values():
        starts = sorted(row["starts"])
        cooldown = max(row["cooldowns"], default=None)
        gap = min((b-a for a,b in zip(starts, starts[1:])), default=None)
        if cooldown is not None and gap is not None and gap+1e-9 < cooldown:
            label = "action-time windows" if action_duration is not None else "pressure windows"
            raise ValueError(f"{row['skill']}: {label} reuse the skill after {gap:g}s, "
                             f"before the assumed {cooldown:g}s cooldown. Adjust the starts or assumption.")
        result.append({"skill_id": row["skill_id"], "skill": row["skill"], "activation_starts_s": starts,
                       "cooldown_s": cooldown, "shortest_reuse_gap_s": gap,
                       "status": "no_active_windows" if not starts else "unknown" if cooldown is None else "assumed_spacing_satisfied",
                       "mixed_assumptions": len(set(row["cooldowns"])) > 1})
    return result


ACTION_NOTE = ("Explicit no-new-offensive-action windows on the rotation clock, starting at zero. "
               "The same one-fight schedule applies once to each damage scenario, clipped to its duration; overlaps use their union. "
               "Actions must finish before a pause. Scheduled hits, DoTs, pets, cooldown recovery and regeneration continue. "
               "Linked active skills/stigmas and effects are allocation reserves, even for zero-duration or clipped-out windows. "
               "Entered effective cooldowns check assumed reuse separately in each damage scenario; blank remains unknown. "
               "Same-start entries represent one assumed use, and the largest entered cooldown for a skill applies. "
               "Reserve cooldown in rotation is optional and requires an entered cooldown. Matching modeled skill IDs and explicit cooldown groups are held before the assumed use, using the larger of modeled offensive cooldown and entered cooldown, and excluded until the entered cooldown expires afterward. "
               "Modeled resets do not shorten this fixed exclusion; unmatched skills are reported. Cross-skill hooks and resource readiness are not verified, so an exclusion is not proof of tactical availability. No tactical damage, MP, shields, CC or success is inferred. "
               "Pressure scenarios have independent clocks; their windows are not automatically copied. Community baselines remain untimed references.")


def prepare_action_windows(cd, options):
    values = options.get("action_windows", [])
    if not isinstance(values, list) or len(values) > 8:
        raise ValueError("Use at most eight outgoing action-time windows")
    windows = []
    for row in values:
        if not isinstance(row, dict):
            raise ValueError("Invalid outgoing action-time window")
        start = number(row.get("start_s"), "Action-time start", 3600)
        duration = number(row.get("duration_s"), "Action-time duration", 120)
        link = window_requirement(cd, row, action=True)
        reserve = row.get("reserve_cooldown", False)
        if type(reserve) is not bool:
            raise ValueError("Reserve cooldown in rotation must be true or false")
        if reserve and (link["skill_id"] is None or link["cooldown_s"] is None):
            raise ValueError("Link a skill and enter an assumed effective cooldown before reserving it in rotation")
        windows.append({"name": str(row.get("name") or "Tactical time")[:100],
                        "start_s": start, "duration_s": duration, "end_s": start+duration,
                        **link, "reserve_cooldown": reserve})
    return windows


def with_action_timing(scenario, plan):
    from dataclasses import replace
    from ..sim.engine import action_blocks
    windows = (plan or {}).get("action_windows", [])
    if not windows:
        return scenario
    checks = cooldown_checks(windows, action_duration=scenario.config.duration)
    blocks = action_blocks(tuple(scenario.config.action_blocks) + tuple((w["start_s"], w["end_s"]) for w in windows),
                           scenario.config.duration)
    if sum(end-start for start, end in blocks) >= scenario.config.duration-1e-9:
        raise ValueError("Action-time windows cover the entire damage scenario; leave time for offensive actions")
    from ..sim.engine import tactical_uses
    cooldowns = {c["skill_id"]: c["cooldown_s"] for c in checks}
    uses = tactical_uses(tuple(scenario.config.tactical_uses) + tuple(
        (w["skill_id"], w["start_s"], cooldowns[w["skill_id"]]) for w in windows
        if w.get("reserve_cooldown") and w["duration_s"] > 0), scenario.config.duration)
    return replace(scenario, config=replace(scenario.config, action_blocks=blocks, tactical_uses=uses))


def action_timing_summary(plan, scenarios, results=None):
    if not (plan or {}).get("action_windows"):
        return None
    return {"note": ACTION_NOTE, "windows": plan["action_windows"], "cases": {
        name: {"duration_s": scenario.config.duration, "blocks": list(scenario.config.action_blocks),
               "paused_s": sum(end-start for start, end in scenario.config.action_blocks),
               "cooldown_checks": cooldown_checks(plan["action_windows"], action_duration=scenario.config.duration),
               "rotation_reservations": getattr((results or {}).get(name), "action_reservations", [])}
        for name, scenario in scenarios.items()}}


def prepare(cd, current, options=None):
    if options is None:
        return None
    if not isinstance(options, dict):
        raise ValueError("Invalid survival options")
    windows = prepare_action_windows(cd, options)
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
        reductions = reduction_windows(cd, row, window)
        timing_checks = cooldown_checks(reductions)
        peak_pressure, peak_time = pressure_deficit(pressure, window, healing, healing_start, healing_end, reductions)
        unprotected_peak, _ = pressure_deficit(pressure, window, healing, healing_start, healing_end)
        trace = row.get("damage_trace")
        if trace is not None:
            trace = damage_trace(trace, maximum_duration=120)
            if not math.isclose(trace["duration_s"], window, rel_tol=0, abs_tol=1e-8):
                raise ValueError("Timed scenario duration is fixed by its imported trace; re-import to change the window")
            peak_pressure, peak_time = timed_deficit(trace, pressure, window, healing, healing_start, healing_end, reductions)
            unprotected_peak, _ = timed_deficit(trace, pressure, window, healing, healing_start, healing_end)
        reserve = number(row.get("reserve_hp", 1), "HP reserve", minimum=1)
        required = burst + peak_pressure + reserve
        rows.append({"name": str(row.get("name") or "Incoming pressure")[:100], "burst_damage": burst,
                     "pressure_dps": pressure, "window_s": window, "healing_hps": healing,
                     "healing_delay_s": delay, "healing_duration_s": duration,
                     "healing_active_s": healing_end-healing_start,
                     "peak_pressure_hp": peak_pressure, "peak_pressure_at_s": peak_time,
                     "reserve_hp": reserve, "required_hp": required, "source": "user_assumption",
                     "reductions": reductions, "cooldown_checks": timing_checks, "unprotected_required_hp": burst+unprotected_peak+reserve,
                     "assumed_requirement_reduction_hp": max(0, unprotected_peak-peak_pressure)})
        if trace is not None:
            rows[-1]["damage_trace"] = trace
        evidence = row.get("recorded_evidence")
        if isinstance(evidence, dict):
            # Provenance is user-imported context, never authenticated telemetry.
            rows[-1]["recorded_evidence"] = {k: str(evidence[k])[:200] for k in
                ("title", "recipient", "recipient_id", "segment", "window_s", "start_s", "end_s", "damage", "largest_hit", "damage_events") if k in evidence}
        benchmark = row.get("opponent_benchmark")
        if isinstance(benchmark, dict):
            rows[-1]["opponent_benchmark"] = {k: str(benchmark[k])[:500] for k in
                ("title", "created", "class", "metric", "modeled_dps", "scale", "source_duration_s", "duration_source", "model_note", "method", "source_start_s", "source_end_s", "trace_hits") if k in benchmark}
    if rows and hp is None:
        raise ValueError("Enter your current maximum HP before using incoming-damage scenarios")
    if not preserve and floor == 0 and not rows and not windows:
        return None
    if rows:
        floor = max(floor, reference + max(r["required_hp"] for r in rows) - hp)
    available = node_hp(cd, {nid for nid, (_, node) in cd.node_index.items() if node.get("type") != "Start"})
    if floor > available+1e-6:
        raise ValueError(f"Requested crystal HP reserve {floor:,.0f} exceeds the catalog's total {available:,.0f}, even before point/connectivity costs. Lower the reserve or incoming-damage assumptions.")
    return {"version": 9, "action_windows": windows, "action_timing_note": ACTION_NOTE, "preserve_hp": preserve, "reference_node_hp": reference,
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
            "worst_headroom_hp": min((r["headroom_hp"] for r in rows), default=None),
            "binding_opponents": [r["name"] for r in rows if math.isclose(r["required_hp"], max(x["required_hp"] for x in rows))]}


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


def opponent_pressure(document, metric, scale, window_s, method="average"):
    """Import a bounded saved PvP average or timed expected-hit benchmark."""
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
    if not isinstance(objective, dict):
        raise ValueError("Invalid saved objective metadata")
    durations = objective.get("durations") or {}
    if not isinstance(durations, dict):
        raise ValueError("Invalid saved objective durations")
    source_duration = number(durations.get(metric, 30 if metric == "pvp_burst" else 180), "Benchmark duration", 3600, .1)
    if window > source_duration:
        raise ValueError("Pressure window cannot exceed the source benchmark duration")
    if method not in ("average", "timed"):
        raise ValueError("Choose average or timed opponent pressure")
    pressure = number(dps * factor, "Scaled incoming damage per second")
    trace = None
    start = 0.0
    if method == "timed":
        traces = view.get("damage_traces")
        trace = damage_trace(traces.get(metric) if isinstance(traces, dict) else None)
        if not math.isclose(trace["duration_s"], source_duration, abs_tol=1e-8):
            raise ValueError("Trace duration does not match the saved damage scenario")
        if not math.isclose(trace["total"]/trace["duration_s"], dps, rel_tol=1e-8, abs_tol=1e-5):
            raise ValueError("Trace damage does not match the saved DPS estimate")
        start, trace = peak_trace_window(trace, window, factor)
        trace = damage_trace(trace, maximum_duration=120)
        pressure = 0.0
    evidence = {"title": doc["title"], "created": doc["created"], "class": view["class"],
                "metric": metric, "modeled_dps": dps, "scale": factor,
                "source_duration_s": source_duration,
                "duration_source": "saved objective" if metric in durations else "legacy scenario default",
                "model_note": str(view.get("model_note") or "Original model assumptions not recorded")[:500]}
    evidence.update({"method": method, "source_start_s": start, "source_end_s": start+window,
                     "trace_hits": len(trace["events"]) if trace else 0})
    return {"scenario": {**({"damage_trace": trace} if trace else {}),
                         "name": f"{view['class']} · {metric} {method} benchmark"[:100],
                         "burst_damage": 0, "pressure_dps": pressure, "window_s": window,
                         "healing_hps": 0, "reserve_hp": 1, "opponent_benchmark": evidence}}
