"""Effective healing and overheal from a fight's recorded heals and the party HP feed (0.2.307).

A heal on a player restores at most the HP they are missing, so its effective part is
``min(amount, max HP - HP before)`` and the rest is overheal. HP before is the target's last HP
reading from an earlier read than the heal, plus the effective part of heals already counted in the
same read; max HP is the reading's maximum (else the target's last known one). The game sends a
player's HP after every change, so the last reading stands until the next one.

Each read that healed a player is checked against the target's HP after it: it should equal the HP
before plus the read's effective healing. In the diagnostic captures, in arrival order, 215 heals
raised HP by exactly their amount and 18 stopped at max HP (docs/open-investigations.md). A heal
with no earlier reading or no maximum is left unknown, never guessed. Pets and enemies are not
covered.

Only instant heals are measured. A heal over time ("restores ... HP every 1s for 14s") is recorded
once with its whole amount while the HP feed rises tick by tick, and a shield the game reports as
healing ("a Protective Shield that blocks damage") restores no HP: both are listed apart, by the
skill's description (potions, which have none, heal over time).
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import defaultdict

LIMIT = 100
#: A next reading further than this after the heal belongs to something else.
CHECK_WINDOW_S = 1.0


_OVER_TIME = re.compile(r"\bHP every\b")
_SHIELD = re.compile(r"\bShield\b.*\bblocks damage\b")


def heal_kind(skill_id, skill: str | None = None) -> str:
    """``shield`` (absorbs damage, restores no HP), ``over_time`` (one record for a heal the game
    delivers in ticks) or ``instant``, from the skill's description."""
    from .actions import _descriptions, _family
    tip = _descriptions().get(_family(skill_id), "") if isinstance(skill_id, int) else ""
    if _SHIELD.search(tip):
        return "shield"
    if _OVER_TIME.search(tip) or "Potion" in (skill or ""):
        return "over_time"
    return "instant"


def _readings(segment: dict, targets: set) -> dict:
    out = defaultdict(list)
    for sample in segment.get("health") or []:
        if sample.get("entity") in targets:
            out[sample["entity"]].append((sample["t"], sample["current"], sample.get("max")))
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


def summarize(segment: dict, players: set, healers: set | None = None) -> dict | None:
    """Per healer and per healer/recipient pair: recorded, effective and overheal amounts, plus the
    check against the HP feed. ``healers`` limits the sources (the party's players and pets; an
    enemy's records are not healing). None when no instant heal on a player could be measured."""
    sources = healers if healers is not None else players
    heals = [e for e in segment.get("events") or []
             if e.get("kind") == "heal" and e.get("target") in players and e.get("source") in sources]
    if not heals:
        return None
    heals.sort(key=lambda e: e["t"])           # stable: equal times keep the recorded order
    readings = _readings(segment, {e["target"] for e in heals})
    times = {target: [r[0] for r in rows] for target, rows in readings.items()}
    known_max = {}                             # target -> the last maximum seen up to each reading
    for target, rows in readings.items():
        last, running = None, []
        for row in rows:
            last = row[2] or last
            running.append(last)
        known_max[target] = running
    same_read = defaultdict(float)             # (target, t) -> effective healing already counted
    reads = {}                                 # (target, t) -> [index of the prior reading, maximum, effective, amount]
    pairs, by_healer = {}, {}
    kinds = {}
    for heal in heals:
        target, t, amount = heal["target"], heal["t"], float(heal["amount"])
        key = (heal.get("skill_id"), heal.get("skill"))
        kind = kinds[key] if key in kinds else kinds.setdefault(key, heal_kind(*key))
        rows, at = readings.get(target, []), times.get(target, [])
        i = bisect_left(at, t)                  # rows[i - 1] is the last reading of an earlier read
        prior = rows[i - 1] if i else None
        maximum = known_max[target][i - 1] if prior else None
        effective = None
        if kind == "instant" and prior and maximum:
            before = min(maximum, prior[1] + same_read[(target, t)])
            effective = max(0.0, min(amount, maximum - before))
            same_read[(target, t)] += effective
        read = reads.setdefault((target, t), [i - 1, maximum, 0.0, 0.0])
        if effective is None:
            read[1] = None                      # an unmeasured heal in the read: it cannot be checked
        else:
            read[2] += effective
            read[3] += amount
        for row_key, table in (((heal["source"], target), pairs), (heal["source"], by_healer)):
            row = table.setdefault(row_key, {"amount": 0.0, "effective": 0.0, "overheal": 0.0, "unknown": 0.0,
                                             "over_time": 0.0, "shield": 0.0, "heals": 0})
            row["amount"] += amount
            row["heals"] += 1
            if kind != "instant":
                row[kind] += amount
            elif effective is None:
                row["unknown"] += amount
            else:
                row["effective"] += effective
                row["overheal"] += amount - effective

    # The check, per read that healed a player: the target's HP after the read (its last reading in
    # that read, else the next within a second) against the HP before plus the effective healing.
    check = {"reads": len(reads), "exact": 0, "capped": 0, "other": 0, "unchecked": 0}
    for (target, t), (index, maximum, effective, amount) in reads.items():
        rows, at = readings.get(target, []), times.get(target, [])
        after = bisect_right(at, t)
        following = (rows[after - 1] if after and at[after - 1] == t else
                     rows[after] if after < len(rows) and rows[after][0] - t <= CHECK_WINDOW_S else None)
        if maximum is None or index < 0 or following is None:
            check["unchecked"] += 1
        elif following[1] - rows[index][1] == amount:
            check["exact"] += 1                 # every heal landed in full
        elif following[1] >= maximum and following[1] - rows[index][1] == effective:
            check["capped"] += 1                # topped up to maximum HP; the rest was overheal
        else:
            check["other"] += 1                 # damage or a missed reading in between

    def finish(row):
        known = row["effective"] + row["overheal"]
        return {**{k: round(v) if isinstance(v, float) else v for k, v in row.items()},
                "overheal_pct": round(100 * row["overheal"] / known, 1) if known else None}

    if not any(row["effective"] or row["overheal"] for row in by_healer.values()):
        return None                             # nothing measurable: no instant heal with a reading
    pair_rows = sorted(({"source": s, "target": tg, **finish(r)} for (s, tg), r in pairs.items()), key=lambda r: -r["amount"])
    return {"healers": sorted(({"source": s, **finish(r)} for s, r in by_healer.items()), key=lambda r: -r["amount"]),
            "pairs": pair_rows[:LIMIT], "omitted_pairs": max(0, len(pair_rows) - LIMIT), "check": check}
