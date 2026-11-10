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

Only instant heals are measured. A heal over time ("restores ... HP every 1s for 14s") and a shield
("a Protective Shield that blocks damage") are listed apart: the event's own ``absorb`` marks a
shield's absorb (meter 0.2.399 and later), else the skill's description tells (potions, which have
none, heal over time). Since 0.2.399 a heal over time is recorded tick by tick and a shield as the
damage each hit it took lost to it, credited to its caster; a meter before recorded the whole pool or
shield when it was cast and then, at each tick or absorb, what was left of it.

Regeneration's heal (meter 0.2.406 and later, ``lookup.REGENERATION_SKILL``) gives back a fifth of what the same
read's hit took off the target, so it lands in full, though the reading before the hit may show full HP.
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


def drop_restores(segment) -> int:
    """Leave out of ``segment``'s events, in place, the heal records that are the Stamina or MP their
    skill restores (``lookup.restored_resource``), which a meter of 0.2.354 or earlier recorded as
    healing: Defiance's 1,000 Stamina counted as a heal of 100,000. How many there were."""
    from ..meter.a2parser.lookup import restored_resource
    events = segment.get("events") if isinstance(segment, dict) else None
    if not isinstance(events, list):
        return 0
    kept = [e for e in events if not (isinstance(e, dict) and e.get("kind") == "heal"
                                      and restored_resource(e.get("skill_id"), e.get("amount")))]
    if len(kept) < len(events):
        segment["events"] = kept
    return len(events) - len(kept)


#: How many skills a segment's ``unattributed_heals`` names.
UNATTRIBUTED_SKILLS = 12


def unattributed_heals(segment, players) -> dict | None:
    """Leave out of a PvP ``segment``'s events, in place, the heal records between the two sides, and count them
    in ``segment["unattributed_heals"]`` (``records``, ``amount``, ``skills``: skill name -> records), adding to a
    count already there. A meter before 0.2.399 recorded a shield's absorb of a hit as a heal with the attacker as
    its source and what was left of the shield as its amount: your party's shields as an opponent's heals on you,
    an opponent's as your heals on them (a public PvP log of 9 November held 925 on its Templar, each one below
    the record before it of the same shield, and 287 on the opponents). The shield's caster is not in that record,
    so the log cannot credit it:
    the records are nobody's healing. A side is the party (``players`` and their summons) or an enemy (an entity
    of kind ``enemy`` and its summons); a heal from or onto anyone else stays. Returns the count, None for none."""
    if not isinstance(segment, dict) or not str(segment.get("encounter_type") or "").startswith("pvp_"):
        return None
    events = segment.get("events")
    if not isinstance(events, list):
        return None
    entities = {e["id"]: e for e in segment.get("entities") or [] if isinstance(e, dict) and isinstance(e.get("id"), str)}

    def side(actor):
        seen = set()
        while actor in entities and entities[actor].get("owner") and actor not in seen:
            seen.add(actor)
            actor = entities[actor]["owner"]
        if actor in players:
            return "party"
        return "enemy" if entities.get(actor, {}).get("kind") == "enemy" else None

    kept, left = [], []
    for e in events:
        if isinstance(e, dict) and e.get("kind") == "heal":
            ours, theirs = side(e.get("source")), side(e.get("target"))
            if ours and theirs and ours != theirs:
                left.append(e)
                continue
        kept.append(e)
    if not left:
        return None
    segment["events"] = kept
    count = segment.get("unattributed_heals") if isinstance(segment.get("unattributed_heals"), dict) else {}
    skills = dict(count.get("skills") or {})
    for e in left:
        name = str(e.get("skill") or e.get("skill_id") or "Unknown")[:80]
        skills[name] = skills.get(name, 0) + 1
    count = {"records": int(count.get("records") or 0) + len(left),
             "amount": float(count.get("amount") or 0) + sum(float(e.get("amount") or 0) for e in left),
             "skills": dict(sorted(skills.items(), key=lambda kv: (-kv[1], kv[0]))[:UNATTRIBUTED_SKILLS])}
    segment["unattributed_heals"] = count
    return count


#: The meter version from which a heal over time is recorded tick by tick (0.2.399). A meter before recorded its
#: ``05 38`` pool as a heal of the whole pool when it was cast and then, at each tick, a heal of what was left of it.
TICKS_RECORDED_SINCE = (0, 2, 399)

#: The heals over time whose ``05 38`` records hold an HP pool that ticks, by skill family:
#: ``(ticks a cast, seconds between ticks, the option a pool needs, whether an instant heal shares the pool's id)``.
#: Read from the 15, 20, 21 and 31 October captures: a pool of N ticks loses ``pool // N`` at each tick, one tick
#: interval after it is cast, and what is left at the end is below N (docs/methodology.md, "Heals over time in
#: older logs, rebuilt when read (0.2.404)"). A skill not listed keeps its records as they are.
HEALS_OVER_TIME = {
    17090000: (15, 2.0, None, False),   # Light of Regeneration (its "+20 %" option adds a second pool beside it)
    18120000: (4, 2.0, None, True),     # Recuperation: 6 ticks with option 3, "+4s healing duration"; its heal and
                                        # its "+5 % HP restored" carry 18120000 too
    17290000: (5, 2.0, 4, False),       # Absolution's option 4, "Restores 1.5% HP every 2s for 10s"
    12350000: (5, 2.0, 3, False),       # Warding Strike's option 3, "Heal over Time during Warding"
    16190000: (10, 1.0, None, True),    # Enhance: Spirit's Benediction, every 1 s (option 1 heals on cast)
    2011101: (5, 2.0, None, False),     # Life Potion: two pools a use
    2011102: (5, 2.0, None, False),     # Superior Life Potion: two pools a use
}
#: The 2 s and 1 s tick clocks jitter by about 0.1 s in the recorded times.
TICK_TOLERANCE_S = 0.4
#: How many skills a segment's ``heals_over_time`` names.
HEALS_OVER_TIME_SKILLS = 12


def _options(skill_id: int) -> set[int]:
    """The specialization slots a skill id carries in its digits (``lookup.decode_spec_flags``)."""
    suffix, slots = (skill_id % 10_000) // 10, set()
    while suffix:
        if not 1 <= suffix % 10 <= 5:
            return set()
        slots.add(suffix % 10)
        suffix //= 10
    return slots


def pool_shape(skill_id) -> tuple[int, float, bool] | None:
    """``(ticks a cast, seconds a tick, whether a lone record is an instant heal)`` for a skill id whose heal records
    a meter before 0.2.399 made from a ticking pool, else None. A lone record under Recuperation's or Spirit's
    Benediction's own id is its instant heal; under any other pool id it is a pool seen once, which healed nothing a
    record can show (cast as the fight ended, or Light of Regeneration's second pool left unused)."""
    if not isinstance(skill_id, int) or isinstance(skill_id, bool):
        return None
    family = skill_id - skill_id % 10_000 if 10_000_000 <= skill_id <= 99_999_999 else skill_id
    shape = HEALS_OVER_TIME.get(family)
    if shape is None:
        return None
    ticks, interval, needs, shared = shape
    options = _options(skill_id) if family != skill_id else set()
    if needs is not None and needs not in options:
        return None                                     # the skill's own heal: its pool needs that option
    if family == 18120000 and 3 in options:
        ticks = 6
    return ticks, interval, shared and skill_id == family


class _Pool:
    __slots__ = ("rem", "tick", "last_t", "records", "first_is_tick")

    def __init__(self, index: int, amount: float, t: float):
        self.rem, self.tick, self.last_t = amount, None, t
        self.records = [[index, None]]                   # [event index, what it took]
        self.first_is_tick = False


def _continues(pool: _Pool, amount: float, t: float, ticks: int, interval: float):
    """How ``amount`` at ``t`` continues ``pool`` (a rank, lower is better), or None. The records of one pool sit on
    its tick clock and step down by whole ticks: a pool whose tick is known takes a record a whole number of ticks
    below it, no more than the tick slots since its last record; a pool seen once takes one whose drop is its
    record // ``ticks`` (that record was the application), or one slot later one that leaves both remainders below
    ``ticks`` with fewer than ``ticks`` ticks in the pool (that record was already a tick: cast before the fight)."""
    if amount >= pool.rem or t < pool.last_t:
        return None
    slots = round((t - pool.last_t) / interval)
    if slots < 1 or slots > ticks or abs(t - pool.last_t - slots * interval) > TICK_TOLERANCE_S:
        return None
    drop = pool.rem - amount
    if pool.tick:
        covered = drop / pool.tick
        return (0, covered, 0) if drop % pool.tick == 0 and 1 <= covered <= slots else None
    if drop == pool.rem // ticks:
        return (1, 1, 0)
    if slots == 1 and pool.rem // drop < ticks and amount % drop < ticks:
        return (2, 1, 1)
    return None


def _pools(records, ticks: int, interval: float) -> list[_Pool]:
    """``records``: ``[(event index, t, amount)]`` of one (source, target, skill id) chain in recorded order, made
    into the pools they belong to. Pools of one chain can run at once (Light of Regeneration's second pool, a
    potion's two, Recuperation's stacking), and each record goes to the one it continues, else opens its own."""
    pools: list[_Pool] = []
    for index, t, amount in records:
        best, rank = None, None
        for pool in pools:
            r = _continues(pool, amount, t, ticks, interval)
            if r is not None and (rank is None or r < rank or (r == rank and pool.last_t > best.last_t)):
                best, rank = pool, r
        if best is None:
            pools.append(_Pool(index, amount, t))
            continue
        drop = best.rem - amount
        if best.tick is None:
            best.tick, best.first_is_tick = drop, bool(rank[2])
        best.records.append([index, drop])
        best.rem, best.last_t = amount, t
    return pools


def heals_over_time(segment) -> dict | None:
    """Rebuild, in place, the heal-over-time records of a ``segment`` a meter before 0.2.399 recorded into what each
    tick took, as a meter of 0.2.399 or later records them, and count them in ``segment["heals_over_time"]``
    (``records`` rebuilt, ``amount`` as recorded, ``rebuilt``, ``skills``: skill name -> records).

    Such a meter recorded a heal over time's pool when it was cast and then, at each tick, what was left of it, so a
    Light of Regeneration counted about ten times what it healed. Each (source, target, skill id) chain of
    :data:`HEALS_OVER_TIME`'s records is split back into its pools (:func:`_pools`): a record that continues a pool
    becomes a heal of the drop since the pool's last record (the ticks between them), a pool's first record a heal
    of one tick when it was already a tick, else (the pool being cast) nothing; a lone record is the skill's instant
    heal, kept, or a pool seen once, left out. A segment already counted is left alone, so a log read twice is rebuilt
    once. The caller decides that the log is that old (:func:`records_pools`). Returns the count, None for none."""
    if not isinstance(segment, dict) or isinstance(segment.get("heals_over_time"), dict):
        return None
    events = segment.get("events")
    if not isinstance(events, list):
        return None
    chains, shapes = defaultdict(list), {}
    for index, e in enumerate(events):
        if not isinstance(e, dict) or e.get("kind") != "heal" or e.get("absorb"):
            continue
        sid, t, amount = e.get("skill_id"), e.get("t"), e.get("amount")
        shape = pool_shape(sid)
        if shape is None or type(t) not in (int, float) or type(amount) not in (int, float) or amount <= 0:
            continue
        shapes[sid] = shape
        chains[(e.get("source"), e.get("target"), sid)].append((index, float(t), float(amount)))
    if not chains:
        return None
    took = {}
    for (_source, _target, sid), records in chains.items():
        ticks, interval, instant = shapes[sid]
        records.sort(key=lambda r: r[1])                # in time order; a pool's records at one time keep theirs
        for pool in _pools(records, ticks, interval):
            if len(pool.records) == 1:
                index = pool.records[0][0]
                took[index] = float(events[index]["amount"]) if instant else 0.0
                continue
            pool.records[0][1] = pool.tick if pool.first_is_tick else 0.0
            took.update((index, float(drop)) for index, drop in pool.records)
    kept, skills, recorded, rebuilt = [], {}, 0.0, 0.0
    for index, e in enumerate(events):
        if index not in took:
            kept.append(e)
            continue
        recorded += float(e["amount"])
        name = str(e.get("skill") or e.get("skill_id") or "Unknown")[:80]
        skills[name] = skills.get(name, 0) + 1
        if took[index] > 0:
            e["amount"] = took[index]
            rebuilt += took[index]
            kept.append(e)
    segment["events"] = kept
    count = {"records": len(took), "amount": recorded, "rebuilt": rebuilt,
             "skills": dict(sorted(skills.items(), key=lambda kv: (-kv[1], kv[0]))[:HEALS_OVER_TIME_SKILLS])}
    segment["heals_over_time"] = count
    return count


def meter_version(doc) -> tuple[int, int, int] | None:
    """The version of the meter that recorded ``doc`` (``meta.capture_quality.app_version``), or None when the log
    names no version or no meter of this client made it."""
    from .quality import DECODER
    meta = doc.get("meta") if isinstance(doc, dict) else None
    quality = meta.get("capture_quality") if isinstance(meta, dict) else None
    if not isinstance(quality, dict) or quality.get("decoder") != DECODER:
        return None
    found = re.match(r"(\d{1,6})\.(\d{1,6})\.(\d{1,6})", str(quality.get("app_version") or ""))
    return tuple(int(x) for x in found.groups()) if found else None


def records_pools(doc) -> bool:
    """Whether ``doc``'s heals over time are as a meter before 0.2.399 recorded them (the pool, then what was left
    of it), which :func:`heals_over_time` rebuilds. A log that names no meter version keeps its records as they
    are."""
    version = meter_version(doc)
    return version is not None and version < TICKS_RECORDED_SINCE


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
    from ..meter.a2parser.lookup import REGENERATION_SKILL
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
        kind = ("shield" if heal.get("absorb") is True
                else kinds[key] if key in kinds else kinds.setdefault(key, heal_kind(*key)))
        rows, at = readings.get(target, []), times.get(target, [])
        i = bisect_left(at, t)                  # rows[i - 1] is the last reading of an earlier read
        prior = rows[i - 1] if i else None
        maximum = known_max[target][i - 1] if prior else None
        effective = None
        if kind == "instant" and heal.get("skill_id") == REGENERATION_SKILL:
            # Regeneration gives back a fifth of what the same read's hit took off this target (0.2.406): it all lands,
            # whatever HP the target had before the hit, which no earlier reading shows.
            effective = amount
            same_read[(target, t)] += effective
        elif kind == "instant" and prior and maximum:
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
