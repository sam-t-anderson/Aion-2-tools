"""Bounded, evidence-only windows before explicit player death markers."""
from bisect import bisect_left, bisect_right

WINDOW = 10.0
MAX_RECAPS = 200
MAX_EVENTS = 200
NOTE = ("Recaps use explicit player death markers and up to 10 seconds of this encounter's recorded history. "
        "The last incoming hit is not a confirmed killing blow; equal timestamps do not prove event order. "
        "Healing amounts are recorded effects, not verified effective healing. Unattributed healing is omitted. "
        "Missing HP, hits or death markers are unavailable, not evidence of survival or avoidable damage. "
        "Mitigation, defensives, resources and cause of death are not inferred. Pet deaths are not owner deaths.")


def summarize(doc):
    players = {p["id"] for p in doc.get("players", [])}
    recaps, total = [], 0
    for index, segment in enumerate(doc.get("segments", [])):
        deaths = sorted({(e["t"], e["target"]) for e in segment.get("events", [])
                         if e.get("kind") == "death" and e.get("target") in players})
        if not deaths:
            continue
        victims = {p for _, p in deaths}
        effects = {p:[] for p in victims}
        for event in segment.get("events", []):
            if event.get("kind") in ("damage", "heal") and event.get("target") in victims:
                effects[event["target"]].append(event)
        health = {p:[] for p in victims}
        for sample in segment.get("health", []):
            if sample["entity"] in victims:
                health[sample["entity"]].append(sample)
        for rows in (*effects.values(), *health.values()):
            rows.sort(key=lambda e:e["t"])
        times = {p:[e["t"] for e in rows] for p,rows in effects.items()}
        hp_times = {p:[e["t"] for e in rows] for p,rows in health.items()}
        totals = {}
        for player, rows in effects.items():
            damage, healing, damage_indices = [0.0], [0.0], []
            for position, event in enumerate(rows):
                damage.append(damage[-1]+(event["amount"] if event["kind"] == "damage" else 0))
                healing.append(healing[-1]+(event["amount"] if event["kind"] == "heal" else 0))
                if event["kind"] == "damage":
                    damage_indices.append(position)
            totals[player] = damage, healing, damage_indices
        previous = {}
        for death, player in deaths:
            total += 1
            if len(recaps) >= MAX_RECAPS:
                continue
            start = max(0,death-WINDOW,previous.get(player,0))
            left = bisect_left(times[player], start)
            if player in previous and previous[player] >= start:
                left = bisect_right(times[player],previous[player])
            right = bisect_right(times[player], death)
            rows = effects[player][max(left,right-MAX_EVENTS):right]
            hp_left, hp_right = bisect_left(hp_times[player],start), bisect_right(hp_times[player],death)
            samples = health[player][max(hp_left,hp_right-MAX_EVENTS):hp_right]
            damage, healing, positions = totals[player]
            position = bisect_left(positions,right)-1
            last_hit = effects[player][positions[position]] if position >= 0 and positions[position] >= left else None
            recaps.append({"segment":index,"player":player,"t":death,"window_start":start,
                "window_seconds":death-start,"short_window":death-start < WINDOW,
                "incoming_damage":damage[right]-damage[left],
                "received_healing":healing[right]-healing[left],
                "last_incoming_hit":last_hit,
                "last_hp":samples[-1] if samples else None,
                "events":rows,"omitted_events":max(0,right-left-MAX_EVENTS),
                "health":samples,"omitted_health":max(0,hp_right-hp_left-MAX_EVENTS)})
            previous[player] = death
    return {"recaps":recaps,"total_death_markers":total,"omitted_recaps":max(0,total-len(recaps)),"note":NOTE}
