"""Recorded run timing and conservative boss progression, shared by all viewers."""
from __future__ import annotations

from datetime import datetime
import math

from .quality import assess
from ..meter.a2parser.lookup import npc_info

NOTE = ("Timing uses recorded wall-clock boundaries and the union of encounter intervals, not time spent actively pressing skills. "
        "Unknown outcomes are not wipes. Missing HP or death markers are unavailable, not zero. "
        "Speed eligibility uses submitted entry/final-boss evidence, not an official result or authenticity guarantee.")


def stamp(value):
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        result = parsed.timestamp() if parsed.tzinfo is not None else None
        return result if result is not None and math.isfinite(result) else None
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return None


def union_seconds(intervals):
    total, end = 0.0, None
    for start, stop in sorted(intervals):
        total += max(0, stop-max(start, end if end is not None else start))
        end = max(stop, end if end is not None else stop)
    return total


def _boss_attempt(segment, boss, quality):
    identity = boss["id"]
    events = segment.get("events", [])
    health = [s for s in segment.get("health", []) if s["entity"] == identity]
    killed = any(e.get("kind") == "death" and e.get("target") == identity for e in events) or any(s["current"] == 0 for s in health)
    full = any(s.get("t", 1) == 0 and s.get("max", 0) > 0 and s["current"] == s["max"] for s in health)
    percentages = [100*s["current"]/s["max"] for s in health if s.get("max", 0) > 0 and 0 <= s["current"] <= s["max"]]
    members = set(segment.get("party_members", []))
    dead = set()
    # HP after a death is evidence of revival; heal effects alone do not establish it.
    evidence = [(e["t"], 1, e["target"], 0) for e in events if e.get("kind") == "death" and e.get("target") in members]
    evidence += [(s["t"], 0, s["entity"], s["current"]) for s in segment.get("health", []) if s["entity"] in members]
    for _, _, actor, hp in sorted(evidence):
        if hp == 0:
            dead.add(actor)
        else:
            dead.discard(actor)
    latest = max(health, key=lambda s:s["t"], default=None)
    wiped = (not killed and members and segment.get("party_roster_complete") is True and members <= dead
             and latest and latest["current"] > 0 and latest["t"] >= segment["duration"]-3)
    reasons = [r for r in quality["reasons"] if r not in ("end_unverified", "start_unverified")]
    wall = stamp(segment.get("start"))
    effects = [h["t"] for h in segment.get("hits", []) if h.get("target") == identity]
    end_effects = effects+[e["t"] for e in events if e.get("kind") == "death" and e.get("target") == identity]
    end_effects += [s["t"] for s in health if s["current"] == 0]
    return {"boss":boss.get("name") or str(boss["mob_code"]), "boss_key":"npc:"+str(boss["mob_code"]),
            "entity":identity, "outcome":"kill" if killed else "wipe" if wiped else "unknown",
            "started_at":wall+min(effects) if wall is not None and effects else None,
            "ended_at":wall+(segment["duration"] if wiped else max(end_effects,default=segment["duration"])) if wall is not None else None,
            "start_observed":full, "best_remaining_hp_pct":0.0 if killed else min(percentages, default=None),
            "quality_reasons":reasons}


def summarize(doc):
    from ..meter.builds import comparison_document
    doc = comparison_document(doc)
    groups = {}
    for index, segment in enumerate(doc.get("segments", [])):
        key = segment.get("run_id") or "legacy"
        groups.setdefault(key, []).append((index, segment))
    result = []
    for identifier, selected in groups.items():
        selected.sort(key=lambda item:(stamp(item[1].get("start")) if stamp(item[1].get("start")) is not None else float("inf"), item[0]))
        segments = [s for _, s in selected]
        intervals, timing_ok = [], True
        for segment in segments:
            start = stamp(segment.get("start"))
            if start is None:
                timing_ok = False
            else:
                intervals.append((start, start+segment["duration"]))
        first = min((a for a, _ in intervals), default=None)
        last = max((b for _, b in intervals), default=None)
        combat = union_seconds(intervals) if timing_ok else None
        span = last-first if timing_ok and first is not None else None
        entries = {s.get("run_started_at") for s in segments}
        entry = stamp(next(iter(entries))) if len(entries) == 1 else None
        ends = {s.get("run_ended_at") for s in segments}
        ended = stamp(next(iter(ends))) if len(ends) == 1 else None
        start_observed = bool(entry is not None and all(s.get("run_start_observed") is True for s in segments))
        complete = all(s.get("run_complete") is True for s in segments)
        elapsed = ended-entry if (timing_ok and start_observed and complete and ended is not None
                                  and entry <= first <= last <= ended) else None
        reasons = []
        if not start_observed:
            reasons.append("Instance entry was not observed.")
        if not complete or any(s.get("run_end_reason") != "configured_final_boss_death" for s in segments):
            reasons.append("A configured final-boss completion was not observed.")
        if elapsed is None or elapsed <= 0:
            reasons.append("Complete, consistent start/end timestamps are unavailable.")
        contexts = {(s.get("encounter_type") or doc.get("meta", {}).get("encounter_type") or "unknown",
                     s.get("game_patch") or doc.get("meta", {}).get("game_patch") or "",
                     s.get("difficulty") or doc.get("meta", {}).get("difficulty") or "",
                     s.get("instance_id") or 0) for s in segments}
        if len(contexts) != 1:
            reasons.append("Run contains different encounter categories or rulesets.")
        kind, patch, difficulty, instance = next(iter(contexts))
        if kind not in ("transcendence", "daily", "expedition", "ascension", "nightmare", "sanctuary") or not patch or not difficulty or not instance:
            reasons.append("An identified PvE instance, build and difficulty are required.")
        attempts, open_attempts = [], {}
        participants = set()
        for index, segment in selected:
            participants.update(h["player"] for h in segment.get("hits", []))
            participants.update(segment.get("party_members", []))
            quality = assess(doc, segment)
            common = set(quality["reasons"])-{"boss_unverified", "start_unverified", "end_unverified"}
            if common:
                reasons.append("One or more encounters have incomplete capture/identity evidence.")
            for boss in segment.get("entities", []):
                if (not boss.get("is_boss") or not boss.get("mob_code") or boss.get("is_player") or boss.get("owner")):
                    continue
                catalog = npc_info(boss["mob_code"])
                if not catalog.get("isBoss") or catalog.get("isDummy"):
                    continue
                # Merely seeing a boss is not an attempt; require recorded engagement.
                if not any(h.get("target") == boss["id"] for h in segment.get("hits", [])):
                    continue
                attempt = _boss_attempt(segment, boss, quality)
                previous = open_attempts.get(boss["id"])
                if previous is not None:
                    previous["segments"].append(index)
                    previous["outcome"] = attempt["outcome"]
                    previous["ended_at"] = attempt["ended_at"]
                    values = [v for v in (previous["best_remaining_hp_pct"],attempt["best_remaining_hp_pct"]) if v is not None]
                    previous["best_remaining_hp_pct"] = min(values, default=None)
                    previous["quality_reasons"] = sorted(set(previous["quality_reasons"]+attempt["quality_reasons"]))
                    attempt = previous
                else:
                    attempt.update(segments=[index], attempt=len(attempts)+1)
                    attempts.append(attempt)
                if attempt["outcome"] == "unknown":
                    open_attempts[boss["id"]] = attempt
                else:
                    open_attempts.pop(boss["id"], None)
        if not attempts or any(not a["start_observed"] or a["outcome"] == "unknown" or a["quality_reasons"] for a in attempts):
            reasons.append("Boss attempts lack a complete observed start and kill/wipe outcome.")
        if not attempts or attempts[-1]["outcome"] != "kill":
            reasons.append("The final recorded boss attempt is not an observed kill.")
        progression, previous_boss = {}, {}
        for a in attempts:
            a["recorded_seconds"] = max(0,a["ended_at"]-a["started_at"]) if a["ended_at"] is not None and a["started_at"] is not None else None
            row = progression.setdefault(a["boss_key"], {"boss":a["boss"], "boss_key":a["boss_key"], "attempts":0,
                "kills":0, "wipes":0, "unknown":0, "attempts_to_first_clear":None, "best_wipe_hp_pct":None, "wipe_recovery_seconds":[]})
            previous = previous_boss.get(a["boss_key"])
            if previous and previous["outcome"] == "wipe" and previous["ended_at"] is not None and a["started_at"] is not None and a["started_at"] >= previous["ended_at"]:
                row["wipe_recovery_seconds"].append(a["started_at"]-previous["ended_at"])
            previous_boss[a["boss_key"]] = a
            row["attempts"] += 1
            row[{"kill":"kills", "wipe":"wipes", "unknown":"unknown"}[a["outcome"]]] += 1
            if a["outcome"] == "kill" and row["attempts_to_first_clear"] is None:
                row["attempts_to_first_clear"] = row["attempts"]
            if a["outcome"] == "wipe" and a["best_remaining_hp_pct"] is not None:
                old = row["best_wipe_hp_pct"]
                row["best_wipe_hp_pct"] = min(old, a["best_remaining_hp_pct"]) if old is not None else a["best_remaining_hp_pct"]
        roster = [p for p in doc.get("players", []) if p["id"] in participants]
        if (any(not s.get("party_roster_complete") for s in segments)
                or len({tuple(sorted(s.get("party_members", []))) for s in segments}) != 1
                or any(not p.get("name") or not p.get("class") or not p.get("server") for p in roster)):
            reasons.append("A complete, stable identified party roster is required.")
        route = list(dict.fromkeys(a["boss_key"] for a in attempts))
        result.append({"id":identifier, "segments":[i for i, _ in selected], "duration":sum(s["duration"] for s in segments),
            "complete":complete, "end_reason":segments[-1].get("run_end_reason", ""), "instance_id":instance,
            "map_id":segments[0].get("map_id"), "encounter_type":kind, "game_patch":patch, "difficulty":difficulty,
            "region":doc.get("meta", {}).get("region", ""), "start_observed":start_observed,
            "recorded_span_seconds":span, "elapsed_seconds":elapsed, "combat_seconds":combat,
            "downtime_seconds":max(0,(elapsed if elapsed is not None else span)-combat) if combat is not None and span is not None else None,
            "party_size":len(roster), "servers":sorted({p["server"] for p in roster if p.get("server")}),
            "boss_route":route, "speed_eligible":not reasons, "speed_reasons":list(dict.fromkeys(reasons)),
            "attempts":attempts, "progression":list(progression.values())})
    return {"runs":result, "note":NOTE}
