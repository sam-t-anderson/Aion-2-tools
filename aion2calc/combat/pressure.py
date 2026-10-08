"""Bounded descriptive pressure windows from normalized combat effects."""
from bisect import bisect_left, bisect_right
from collections import defaultdict

LIMIT = 100
WINDOWS = (1, 3, 5)
NOTE = ("Windows maximize recorded gross amount, not net HP loss, effective healing or incoming raw skill damage. "
        "Damage/healing sources stay separate from pets. Windows never cross a recorded death of that actor; "
        "effects sharing its death timestamp are excluded because their order is unknown. Missing death markers "
        "can join separate lives. Window times are encounter-relative; short captures can have shorter observed spans. "
        "Healing in an incoming-damage window is recorded amount only and is never subtracted. "
        "Missing packets, sources and recipients can understate totals. These metrics do not establish avoidability, "
        "defensive usage, casts or PvP outcomes.")


def friendly_ids(players, entities):
    result = set(players)
    for entity in entities:
        current, seen = entity, set()
        while current not in seen and current in entities:
            if current in players:
                result.add(entity)
                break
            seen.add(current)
            current = entities[current].get("owner")
        if current in players:
            result.add(entity)
    return result


def peak(rows, deaths, width):
    """Linear rolling sum, split by explicit deaths; earliest maximum wins."""
    boundaries = set(deaths)
    left, running, best, start, last_epoch = 0, 0.0, None, 0.0, None
    clean = [(e, bisect_right(deaths, e["t"])) for e in rows if e["t"] not in boundaries]
    for right, (event, epoch) in enumerate(clean):
        t = event["t"]
        if epoch != last_epoch:
            left, running, last_epoch = right, 0.0, epoch
        running += event["amount"]
        while left < right and clean[left][0]["t"] < t-width-1e-9:
            running -= clean[left][0]["amount"]
            left += 1
        if best is None or running > best["amount"]:
            start = max(0.0, t-width, deaths[epoch-1] if epoch else 0.0)
            best = {"window_s": width, "start_s": start, "end_s": t, "observed_span_s": t-start,
                    "amount": running, "effects": right-left+1}
    return best


def summarize(segment, events, friendly):
    duration = segment["duration"]
    deaths, groups, received_heals, incoming = defaultdict(set), defaultdict(list), defaultdict(list), {}
    outside = 0
    for event in events:
        t, kind = event["t"], event["kind"]
        if not 0 <= t <= duration:
            outside += 1
            continue
        source, target = event.get("source"), event.get("target")
        if kind == "death" and target in friendly:
            deaths[target].add(t)
        if kind not in ("damage", "heal") or event.get("amount", 0) <= 0:
            continue
        if source in friendly:
            groups[(source, "damage_done" if kind == "damage" else "healing_done")].append(event)
        if kind == "heal" and target in friendly:
            received_heals[target].append(event)
        if kind == "damage" and target in friendly:
            groups[(target, "damage_taken")].append(event)
            key = (source, target, event.get("skill_id"), event.get("skill"))
            row = incoming.setdefault(key, {"source": source, "target": target, "skill_id": event.get("skill_id"),
                "skill": event.get("skill"), "amount": 0.0, "effects": 0, "largest_hit": 0.0, "first": t, "last": t})
            row["amount"] += event["amount"]
            row["effects"] += 1
            row["largest_hit"] = max(row["largest_hit"], event["amount"])
            row["first"], row["last"] = min(row["first"], t), max(row["last"], t)
    death_times = {actor: sorted(times) for actor, times in deaths.items()}
    heals = {}
    for actor, rows in received_heals.items():
        rows = sorted((e for e in rows if e["t"] not in deaths[actor]), key=lambda e: e["t"])
        times, totals = [], [0.0]
        for event in rows:
            times.append(event["t"])
            totals.append(totals[-1]+event["amount"])
        heals[actor] = times, totals
    windows = []
    boundary_effects = sum(e["t"] in deaths[actor] for (actor, _), rows in groups.items() for e in rows)
    for (actor, metric), rows in groups.items():
        rows.sort(key=lambda e: e["t"])
        for width in WINDOWS:
            result = peak(rows, death_times.get(actor, []), width)
            if result is None:
                continue
            if metric == "damage_taken":
                times, totals = heals.get(actor, ([], [0.0]))
                a, b = bisect_left(times, result["start_s"]-1e-9), bisect_right(times, result["end_s"]+1e-9)
                result["recorded_healing"] = totals[b]-totals[a]
                result["healing_effects"] = b-a
            windows.append({"actor": actor, "metric": metric, **result})
    windows.sort(key=lambda row: (-row["amount"], row["actor"], row["metric"], row["window_s"]))
    incoming = sorted(incoming.values(), key=lambda row: (-row["amount"], row["target"], str(row["source"])))
    return {"note": NOTE, "windows": windows[:LIMIT], "incoming": incoming[:LIMIT],
            "omitted_windows": max(0, len(windows)-LIMIT), "omitted_incoming": max(0, len(incoming)-LIMIT),
            "death_boundary_effect_references": boundary_effects, "outside_duration_effects": outside}
