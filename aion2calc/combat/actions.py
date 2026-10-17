"""Rotation, effect-uptime, crowd-control and break-gauge summaries from an a2log segment's recorded
casts, effects, chain windows and break-gauge readings (recorded by the live meter since 0.2.306).

Everything here describes what was recorded: a cast is the game's own cast record, an effect window
runs from the effect's application to its removal (or its stated duration), and a break-gauge drop
is the game's own reading. Two labels come from the bundled skill descriptions rather than packets:
the crowd-control state a skill inflicts ("inflicts Knockdown for 2s") and its listed Stagger Gauge
Damage, which apportions a gauge drop shared by several hits in the same read."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import re

LIMIT = 100
#: The crowd-control states the skill descriptions name after "inflict(s)".
_CC = re.compile(r"\binflicts?\s+(?:an?\s+)?(Stun|Knockdown|Airborne|Fear|Root|Freeze|Sleep|Silence|Bind|Slow|Snare)\b", re.I)
_STAGGER = re.compile(r"\b(\d+) Stagger Gauge Damage\b")
HARD_CC = frozenset({"stun", "knockdown", "airborne", "fear", "root", "freeze", "sleep", "silence", "bind"})


@lru_cache(maxsize=1)
def _descriptions() -> dict[int, str]:
    """Skill family -> description, from the bundled class skill data."""
    out = {}
    try:
        from ..paths import list_names, read_json
        for cls in list_names("global", "classes"):
            try:
                doc = read_json("global", "classes", f"{cls}.json")
            except Exception:
                continue
            for skill in (doc.get("skills") or []) if isinstance(doc, dict) else []:
                sid, tip = skill.get("id"), skill.get("tip")
                if isinstance(sid, int) and not isinstance(sid, bool) and isinstance(tip, str):
                    out.setdefault(sid - sid % 10_000, tip)
    except Exception:
        pass
    return out


def _family(skill_id) -> int | None:
    from ..meter.a2parser.lookup import skill_family
    return skill_family(skill_id) if isinstance(skill_id, int) and skill_id > 0 else None


def cc_state(skill_id) -> str | None:
    """The crowd-control state this skill's description says it inflicts, or None."""
    match = _CC.search(_descriptions().get(_family(skill_id), ""))
    return match.group(1).capitalize() if match else None


def stagger_value(skill_id) -> int | None:
    """The Stagger Gauge Damage this skill's description lists, or None."""
    match = _STAGGER.search(_descriptions().get(_family(skill_id), ""))
    return int(match.group(1)) if match else None


def _median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else None


def _merged_seconds(spans, duration):
    total, current = 0.0, None
    for start, end in sorted((max(0.0, a), min(duration, b)) for a, b in spans if b > a):
        if current and start <= current[1]:
            current[1] = max(current[1], end)
        else:
            if current:
                total += current[1] - current[0]
            current = [start, end]
    if current:
        total += current[1] - current[0]
    return total


def pressed(records: list) -> tuple[list, str]:
    """One actor's cast records of one skill family, in time order -> (the presses, "skill" or "proc").
    One press can send several records of the family: the cast itself, which carries the skill's
    cooldown, then follow-up parts (aimed or self-targeted) without one. The cooldown-bearing records
    count when the skill has a cooldown, else its aimed records (a filler); a skill with neither is a
    passive or self effect (a proc). Records within 0.25 s of the previous one are the same press."""
    timed = [c for c in records if c.get("cooldown_ms")]
    aimed = [c for c in records if c.get("target")]
    rows, kind = (timed, "skill") if timed else (aimed, "skill") if aimed else (records, "proc")
    return [c for i, c in enumerate(rows) if i == 0 or c["t"] - rows[i - 1]["t"] > 0.25], kind


def rotation(segment: dict, players: set) -> dict:
    """Per player: casts by skill with cooldown usage, chain-skill use and dodges. Pets and summons
    act on their own, so their casts are left out of the rotation."""
    duration = max(0.001, segment["duration"])
    by_source = defaultdict(list)
    for cast in segment.get("casts") or []:
        if cast["source"] in players:
            by_source[cast["source"]].append(cast)
    skills, totals, dodges = [], [], []
    for source, casts in by_source.items():
        casts.sort(key=lambda c: c["t"])
        groups = defaultdict(list)
        for cast in casts:
            groups[_family(cast["skill_id"])].append(cast)
        presses = procs = 0
        for family, every in groups.items():
            rows, kind = pressed(every)
            if kind == "skill":
                presses += len(rows)
            else:
                procs += len(rows)
            times = [c["t"] for c in rows]
            gaps = [b - a for a, b in zip(times, times[1:])]
            cooldown = _median([c["cooldown_ms"] for c in rows if c.get("cooldown_ms")])
            # Casts that fit from the first one to the fight's end (a cast in its last half-second
            # would add nothing), for skills with a real cooldown.
            possible = (int(max(0.0, duration - max(0.0, times[0]) - 0.5) // (cooldown / 1000)) + 1
                        if cooldown and cooldown >= 1000 else None)
            name = rows[0].get("skill") or str(rows[0]["skill_id"])
            skills.append({"source": source, "skill_id": rows[0]["skill_id"], "skill": name, "kind": kind, "casts": len(rows),
                           "first": times[0], "last": times[-1], "average_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
                           "cooldown_ms": cooldown, "possible": possible,
                           "usage_pct": round(min(100.0, 100 * len(rows) / possible), 1) if possible else None,
                           "cast_ms": _median([c["cast_ms"] for c in rows if c.get("cast_ms") is not None])})
            if name == "Dodge":
                dodges.append({"source": source, "count": len(rows), "times": [round(t, 2) for t in times[:50]]})
        totals.append({"source": source, "casts": presses, "procs": procs, "per_minute": round(60 * presses / duration, 1)})
    casts_by_family = defaultdict(list)
    for cast in segment.get("casts") or []:
        casts_by_family[(cast["source"], _family(cast["skill_id"]))].append(cast["t"])
    chain_rows = {}
    for window in segment.get("chains") or []:
        key = (window["player"], window["next_id"])
        row = chain_rows.setdefault(key, {"player": window["player"], "skill_id": window["skill_id"], "next_id": window["next_id"],
                                          "next": window.get("next") or str(window["next_id"]), "opened": 0, "used": 0})
        row["opened"] += 1
        end = window.get("end", window["t"] + 10)
        if any(window["t"] <= t <= end + 0.3 for t in casts_by_family.get((window["player"], _family(window["next_id"])), ())):
            row["used"] += 1
    chains = [{**row, "used_pct": round(100 * row["used"] / row["opened"], 1)} for row in chain_rows.values()]
    return {"totals": sorted(totals, key=lambda r: -r["casts"]),
            "skills": sorted(skills, key=lambda r: (r["source"], -r["casts"])),
            "chains": sorted(chains, key=lambda r: -r["opened"]), "dodges": dodges}


def effects(segment: dict, friendly: set, entities: dict) -> dict:
    """Buff uptime on the party, debuff uptime on enemies, and crowd control the party landed."""
    duration = max(0.001, segment["duration"])
    groups = defaultdict(list)
    crowd = []
    for row in segment.get("effects") or []:
        target, source = row["target"], row.get("source")
        on_party = target in friendly
        side = "buff" if on_party and (source is None or source in friendly) else "incoming" if on_party else "debuff"
        groups[(side, target, _family(row["skill_id"]))].append(row)
        state = cc_state(row["skill_id"])
        if side == "debuff" and state and source in friendly:
            crowd.append({"t": row["t"], "end": row["end"], "seconds": round(row["end"] - row["t"], 2), "target": target,
                          "source": source, "skill_id": row["skill_id"], "skill": row.get("skill"), "state": state,
                          "hard": state.lower() in HARD_CC, "ended": row.get("ended"), "refreshes": row.get("refreshes", 0)})
    out = {"buffs": [], "incoming": [], "debuffs": []}
    for (side, target, family), rows in groups.items():
        seconds = _merged_seconds([(r["t"], r["end"]) for r in rows], duration)
        sources = defaultdict(int)
        for r in rows:
            sources[r.get("source") or ""] += 1
        out[{"buff": "buffs", "incoming": "incoming", "debuff": "debuffs"}[side]].append({
            "target": target, "skill_id": rows[0]["skill_id"], "skill": rows[0].get("skill") or str(rows[0]["skill_id"]),
            "applications": len(rows), "seconds": round(seconds, 2), "uptime_pct": round(100 * seconds / duration, 1),
            "sources": [{"source": s or None, "applications": n} for s, n in sorted(sources.items(), key=lambda kv: -kv[1])][:5],
            "boss": bool(entities.get(target, {}).get("is_boss"))})
    for key in out:
        out[key].sort(key=lambda r: (-r["boss"], -r["seconds"]))
    by_source = defaultdict(lambda: {"landed": 0, "seconds": 0.0, "hard": 0, "broken_early": 0})
    for row in crowd:
        summary = by_source[(row["source"], row["state"])]
        summary["landed"] += 1 + row["refreshes"]           # each re-application while held landed it again
        summary["seconds"] += row["seconds"]
        summary["hard"] += (1 + row["refreshes"]) * int(row["hard"])
        summary["broken_early"] += int(row["ended"] == "removed")
    out["crowd_control"] = sorted(crowd, key=lambda r: r["t"])
    out["crowd_control_by_source"] = sorted(({"source": source, "state": state, **summary, "seconds": round(summary["seconds"], 2)}
                                             for (source, state), summary in by_source.items()), key=lambda r: -r["seconds"])
    return out


def stagger(segment: dict, entities: dict) -> list:
    """Per boss with a break gauge: its breaks and each player's share of the gauge drained. A drop
    belongs to the hits on that boss in the same read; a drop shared by several hits is split by
    each skill's listed Stagger Gauge Damage (or the drop that skill showed alone, else equally)."""
    readings = defaultdict(list)
    for row in segment.get("gauge") or []:
        readings[row["entity"]].append(row)
    if not readings:
        return []
    hits = defaultdict(list)
    for hit in segment.get("hits") or []:
        if hit.get("target") in readings:
            hits[hit["target"]].append(hit)
    out = []
    for entity, rows in readings.items():
        rows.sort(key=lambda r: r["t"])
        at = defaultdict(list)
        for hit in hits.get(entity, ()):
            at[round(hit["t"], 3)].append(hit)
        alone = defaultdict(list)
        drops = []
        for previous, row in zip(rows, rows[1:]):
            drop = previous["current"] - row["current"]
            if drop <= 0:
                continue
            same = at.get(round(row["t"], 3), [])
            drops.append((row["t"], drop, same))
            if len(same) == 1:
                alone[_family(same[0].get("skill_id"))].append(drop)
        learned = {family: _median(values) for family, values in alone.items()}
        share, unattributed = defaultdict(float), 0
        for t, drop, same in drops:
            if not same:
                unattributed += drop
                continue
            weights = [stagger_value(h.get("skill_id")) or learned.get(_family(h.get("skill_id"))) or 1 for h in same]
            for hit, weight in zip(same, weights):
                share[hit["player"]] += drop * weight / sum(weights)
        breaks = []
        for previous, row in zip(rows, rows[1:]):
            if previous["current"] <= 0.05 * previous["max"] and row["current"] >= 0.9 * row["max"]:
                breaks.append({"t": previous["t"], "end": row["t"], "seconds": round(row["t"] - previous["t"], 2)})
        in_break = defaultdict(float)
        for hit in hits.get(entity, ()):
            if any(b["t"] <= hit["t"] <= b["end"] for b in breaks):
                in_break[hit["player"]] += hit["damage"]
        total = sum(share.values())
        out.append({"entity": entity, "boss": bool(entities.get(entity, {}).get("is_boss")), "max": rows[-1]["max"],
                    "readings": len(rows), "drained": round(total + unattributed), "unattributed": unattributed,
                    "breaks": breaks,
                    "players": sorted(({"player": p, "amount": round(v, 1), "share_pct": round(100 * v / total, 1) if total else None,
                                        "break_damage": round(in_break.get(p, 0.0))} for p, v in share.items()),
                                      key=lambda r: -r["amount"])})
    return out


def summarize(segment: dict, players: set, friendly: set, entities: dict) -> dict:
    """The segment's rotation, effects, crowd control and break-gauge summaries (empty when the
    recording carries no cast or effect records, e.g. an older log)."""
    result = {"rotation": rotation(segment, players), **effects(segment, friendly, entities),
              "stagger": stagger(segment, entities)}
    omitted = {}
    for key in ("buffs", "incoming", "debuffs", "crowd_control", "crowd_control_by_source"):
        omitted[key] = max(0, len(result[key]) - LIMIT)
        result[key] = result[key][:LIMIT]
    rotation_rows = result["rotation"]
    for key in ("skills", "chains"):
        omitted["rotation_" + key] = max(0, len(rotation_rows[key]) - 4 * LIMIT)
        rotation_rows[key] = rotation_rows[key][:4 * LIMIT]
    result["omitted_actions"] = omitted
    return result
