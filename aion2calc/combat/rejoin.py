"""Encounters the live meter of 0.2.354 and earlier cut wrongly, put right in recordings already made.

These segmentation faults, fixed in the meter at 0.2.354 and 0.2.355, are undone here, so the log
server (which applies this whenever it loads a stored recording; the stored upload is never changed)
sees each fight once and whole:

* **A stretched fight.** A death closed the most recent earlier fight that had involved the entity,
  even when the next fight had already begun: a player dying in the next fight, or one of its adds,
  stretched the earlier segment across it. That segment then held the next fight's deaths, health,
  movement and actions a second time, and could claim its kill. Each segment is clipped where the
  next segment of its session begins, at its own last hit or effect.
* **A boss fight cut in two.** An elite left behind mid-dungeon, healing back to full once out of
  combat, read as a wipe's reset and cut the fight in progress: a first half without the kill and a
  second without the start, neither rankable. Two consecutive segments of one recorded run that fight
  the same boss entity are one fight when the boss was alive at the cut, its health carried on (not
  back at full, never higher than it was) and the second half resumed within ``RESUME_SECONDS``.

* **A boss fight's stray pieces** (0.2.355). A zone load into the boss's room begins the fight's
  segment, and the boss split armed by the previous kill still fired at the party's first hit: the
  boss's opening blow was an encounter of its own, a few milliseconds long. It joins the fight. And a
  dead boss still striking the party once the fight was won (Ultimate Berk, for some 17 s) opened an
  encounter with no party damage, past the run's end; it is marked as the fight's.

The whole fight takes the second half's index (links to it stay valid); the first half keeps its own
and is marked ``continued_in`` the whole fight's, which leaves it out of rankings (``quality``). A
boss seen at zero health in a segment is its kill, as a death record would be. Recorded samples are
only moved onto one clock, never changed, and nothing is inferred from names or damage patterns.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

RESUME_SECONDS = 30
#: A boss's blows before the party's first hit on it are that fight's within this many seconds.
OPENING_SECONDS = 5
#: The boss's first reading after the cut may sit this share of its maximum above its last reading
#: before it (a regeneration tick, rounding); more than that is a heal, and a full reading a reset.
HP_SLACK = 0.01
#: A boss at or above this share of its maximum is at full health (``quality.FULL_HEALTH_TOLERANCE``).
FULL = 0.995

#: The time-stamped lists of a segment: the item fields holding seconds from the segment's start
#: (an index for the ``[t, value]`` pairs of ``hp`` and ``ping``), the first being when it begins.
SHIFTED = (("hits", ("t",)), ("events", ("t",)), ("health", ("t",)), ("hp", (0,)), ("positions", ("t",)),
           ("movement", ("t",)), ("ping", (0,)), ("buffs", ("start", "end")), ("casts", ("t",)),
           ("effects", ("t", "end")), ("gauge", ("t",)), ("chains", ("t", "end")), ("resources", ("t",)),
           ("npc_casts", ("t",)))


def _stamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _get(item, field):
    if isinstance(item, dict):
        return item.get(field) if isinstance(field, str) else None
    if isinstance(item, (list, tuple)) and isinstance(field, int) and len(item) > field:
        return item[field]
    return None


def _shift(item, fields, offset):
    if isinstance(item, (list, tuple)):
        item = list(item)
        for field in fields:
            if isinstance(field, int) and len(item) > field and _num(item[field]):
                item[field] = item[field] + offset
        return item
    item = dict(item)
    for field in fields:
        if _num(item.get(field)):
            item[field] = item[field] + offset
    return item


def _epoch(segment):
    """The meter session (epoch) a segment came from: the ``<epoch>-<ms>-<seq>`` id's first part."""
    parts = str(segment.get("id") or "").split("-")
    return parts[0] if len(parts) == 3 and parts[0].isdigit() else None


def engaged_bosses(segment) -> dict:
    """The catalog bosses the party fought in a segment (struck at least once), by entity id. A boss
    the party never touched -- an untargetable copy, a vine, a second boss elsewhere in the room --
    is not part of the fight it was recorded in."""
    targets = {h.get("target") for h in segment.get("hits") or [] if isinstance(h, dict)}
    return {e["id"]: e for e in segment.get("entities") or []
            if isinstance(e, dict) and e.get("is_boss") and e.get("mob_code") and not e.get("is_player")
            and not e.get("owner") and e.get("id") in targets}


def dead_entities(segment) -> set:
    """Entities with a death record, or seen at zero health, in a segment."""
    dead = {e.get("target") for e in segment.get("events") or [] if isinstance(e, dict) and e.get("kind") == "death"}
    dead.update(s.get("entity") for s in segment.get("health") or [] if isinstance(s, dict) and s.get("current") == 0)
    return dead


def _clip(segment, cut):
    """The segment ending at ``cut`` seconds (where the next fight began): its samples after its own
    last hit or effect before then dropped, intervals ended there."""
    kept = [_get(item, "t") for key in ("hits", "events") for item in segment.get(key) or []]
    kept = [t for t in kept if _num(t) and t <= cut]
    end = max(kept, default=cut)
    for key, fields in SHIFTED:
        items = segment.get(key)
        if not isinstance(items, list):
            continue
        out = []
        for item in items:
            start = _get(item, fields[0])
            if _num(start) and start > end:
                continue
            if len(fields) > 1 and isinstance(item, dict) and _num(item.get(fields[1])) and item[fields[1]] > end:
                item = {**item, fields[1]: end}
            out.append(item)
        segment[key] = out
    segment["duration"] = max(0.001, end)
    bosses = {e.get("id") for e in segment.get("entities") or [] if isinstance(e, dict) and e.get("is_boss")}
    segment["killed"] = bool(bosses & {e.get("target") for e in segment.get("events") or []
                                       if isinstance(e, dict) and e.get("kind") == "death"})
    return segment


def _boss_hp(segment, boss, last):
    rows = [s for s in segment.get("health") or [] if isinstance(s, dict) and s.get("entity") == boss
            and _num(s.get("current")) and _num(s.get("max")) and s["max"] > 0]
    rows.sort(key=lambda s: s.get("t") or 0)
    return (rows[-1] if last else rows[0]) if rows else None


def same_fight(first, second) -> bool:
    """Whether two consecutive segments of one session are one boss fight the meter cut in two."""
    if _epoch(first) is None or _epoch(first) != _epoch(second):
        return False
    if first.get("run_id") is None or first.get("run_id") != second.get("run_id"):
        return False
    a, b = _stamp(first.get("start")), _stamp(second.get("start"))
    if a is None or b is None or not -1.0 <= b - (a + float(first.get("duration") or 0)) <= RESUME_SECONDS:
        return False
    bosses, continued, dead = engaged_bosses(first), engaged_bosses(second), dead_entities(first)
    for boss, entity in bosses.items():
        if boss in dead or boss not in continued or continued[boss].get("mob_code") != entity.get("mob_code"):
            continue
        before, after = _boss_hp(first, boss, last=True), _boss_hp(second, boss, last=False)
        if (before and after and after["current"] < after["max"] * FULL
                and after["current"] <= before["current"] + HP_SLACK * after["max"]):
            return True
    return False


def _continue_effects(merged, first, shifted):
    """An effect still held at the cut is in both halves: the first half's row runs to its end and
    the second half's row is marked ``before``. Extend the first row instead of counting it twice."""
    open_rows = {}
    for row in merged.get("effects") or []:
        if isinstance(row, dict) and float(row.get("end") or 0) >= float(first.get("duration") or 0) - 0.5:
            open_rows[(row.get("target"), row.get("skill_id"), row.get("source"))] = row
    kept = []
    for row in shifted:
        held = open_rows.get((row.get("target"), row.get("skill_id"), row.get("source"))) if row.get("before") else None
        if held is None:
            kept.append(row)
            continue
        held["end"] = max(float(held.get("end") or 0), float(row.get("end") or 0))
        refreshes = int(held.get("refreshes") or 0) + int(row.get("refreshes") or 0)
        if refreshes:
            held["refreshes"] = refreshes
        if row.get("ended"):                     # how it ended is the second half's to say
            held["ended"] = row["ended"]
        else:
            held.pop("ended", None)
    return kept


def merge_segments(first, second) -> dict:
    """One encounter from two halves: the first half's start, every sample of the second half shifted
    by the time between their starts, entities and party unioned, the outcome from the second half.
    Shared with the log server's stitching of a fight cut by an archive rollover."""
    offset = (_stamp(second.get("start")) or 0) - (_stamp(first.get("start")) or 0)
    merged = deepcopy(first)
    merged["duration"] = max(float(first.get("duration") or 0), offset + float(second.get("duration") or 0))
    for key, fields in SHIFTED:
        if not (first.get(key) or second.get(key)):
            continue
        shifted = [_shift(item, fields, offset) for item in second.get(key) or []]
        if key == "effects":
            shifted = _continue_effects(merged, first, [r for r in shifted if isinstance(r, dict)])
        merged[key] = list(merged.get(key) or []) + shifted
    merged["events"] = sorted(merged.get("events") or [], key=lambda e: e.get("t", 0) if isinstance(e, dict) else 0)
    entities = {e["id"]: dict(e) for e in first.get("entities") or [] if isinstance(e, dict) and "id" in e}
    for entity in second.get("entities") or []:
        if isinstance(entity, dict) and "id" in entity:
            entities.setdefault(entity["id"], {}).update(entity)
    merged["entities"] = list(entities.values())
    merged["party_members"] = list(dict.fromkeys([*(first.get("party_members") or []), *(second.get("party_members") or [])]))
    merged["party_roster_complete"] = bool(first.get("party_roster_complete")) and bool(second.get("party_roster_complete"))
    merged["party_roster_late"] = bool(first.get("party_roster_late")) or bool(second.get("party_roster_late"))
    merged["killed"] = bool(second.get("killed"))
    for key in ("id", "label", "boss"):
        if second.get(key) is not None:
            merged[key] = second[key]
    if isinstance(first.get("capture_loss"), dict) and isinstance(second.get("capture_loss"), dict):
        merged["capture_loss"] = {k: (first["capture_loss"].get(k) or 0) + (second["capture_loss"].get(k) or 0)
                                  for k in set(first["capture_loss"]) | set(second["capture_loss"])}
    else:
        merged.pop("capture_loss", None)
    if isinstance(first.get("validation"), dict) and isinstance(second.get("validation"), dict):
        merged["validation"] = {k: (first["validation"].get(k) or 0) + (second["validation"].get(k) or 0)
                                for k in set(first["validation"]) | set(second["validation"])}
    merged.pop("quality", None)                  # judged afresh (quality.assess)
    return merged


def _party_damage(segment) -> bool:
    return any(isinstance(h, dict) and _num(h.get("damage")) and h["damage"] > 0 for h in segment.get("hits") or [])


def _strikers(segment) -> set:
    return {e.get("source") for e in segment.get("events") or []
            if isinstance(e, dict) and e.get("kind") == "damage" and e.get("source") is not None}


def after_kill(fight, after) -> bool:
    """Whether ``after`` holds only what ``fight``'s dead did once it was won: no party damage, every
    blow struck by an entity that died in ``fight``, begun within ``RESUME_SECONDS`` of its end
    (Ultimate Berk strikes the party for some 17 s after its death)."""
    if _epoch(fight) is None or _epoch(fight) != _epoch(after) or _party_damage(after):
        return False
    a, b = _stamp(fight.get("start")), _stamp(after.get("start"))
    if a is None or b is None or not -1.0 <= b - (a + float(fight.get("duration") or 0)) <= RESUME_SECONDS:
        return False
    strikers = _strikers(after)
    return bool(strikers) and strikers <= dead_entities(fight)


def opening_blow(before, fight) -> bool:
    """Whether ``before`` holds only the first blows of a boss the party fights in ``fight``, struck
    within ``OPENING_SECONDS`` before the party's first hit on it, with no party damage of its own."""
    if _epoch(before) is None or _epoch(before) != _epoch(fight) or _party_damage(before):
        return False
    a, b = _stamp(before.get("start")), _stamp(fight.get("start"))
    if a is None or b is None or not 0 <= b - a <= OPENING_SECONDS or float(before.get("duration") or 0) > OPENING_SECONDS:
        return False
    strikers = _strikers(before)
    return bool(strikers) and strikers <= set(engaged_bosses(fight))


def rejoin(doc):
    """A copy of ``doc`` with stretched segments clipped, boss fights cut in two made whole and a boss
    fight's stray pieces put with it, or ``doc`` itself when nothing needed it. ``meta.repairs`` says
    what was done."""
    if not isinstance(doc, dict) or not isinstance(doc.get("segments"), list) or len(doc["segments"]) < 1:
        return doc
    if isinstance(doc.get("meta"), dict) and doc["meta"].get("repairs"):
        return doc          # repaired already (an upload never carries the mark: a2log.validate drops it)
    segments = doc["segments"]
    clipped, rejoined, killed = [], [], []
    out = list(segments)
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if not isinstance(a, dict) or not isinstance(b, dict) or _epoch(a) is None or _epoch(a) != _epoch(b):
            continue
        start_a, start_b = _stamp(a.get("start")), _stamp(b.get("start"))
        if start_a is None or start_b is None or not _num(a.get("duration")):
            continue
        cut = start_b - start_a
        if 0 <= cut < a["duration"] - 0.001:
            out[i] = _clip(deepcopy(a), cut)
            clipped.append(i)
    for i, segment in enumerate(out):
        # A boss seen at zero health died there, whether or not its death record was kept.
        if isinstance(segment, dict) and not segment.get("killed") and set(engaged_bosses(segment)) & dead_entities(segment):
            out[i] = {**segment, "killed": True}
            killed.append(i)
    recorded, whole, start = list(out), None, None   # whole: the fight so far, from segment ``start``
    for i in range(len(out) - 1):
        a, b = whole if whole is not None else out[i], out[i + 1]
        if not (isinstance(a, dict) and isinstance(b, dict) and same_fight(a, b)):
            whole = None
            continue
        start = i if whole is None else start
        whole = out[i + 1] = merge_segments(a, b)
        for part in range(start, i + 1):            # a fight cut more than once: every piece points to the whole
            out[part] = {**recorded[part], "continued_in": i + 1}
            out[part].pop("quality", None)
        rejoined.append([i, i + 1])
    # A boss fight's stray pieces (meter 0.2.354 and earlier): the boss's opening blow cut off at the
    # party's first hit, when a zone load had already begun the fight's own segment, joins the fight;
    # what its dead struck once the fight was won is marked as the fight's, not an encounter.
    openings, afters = [], []
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if not (isinstance(a, dict) and isinstance(b, dict)) or a.get("continued_in") is not None or b.get("continued_in") is not None:
            continue
        if opening_blow(a, b):
            out[i + 1] = merge_segments(a, b)
            out[i] = {**a, "continued_in": i + 1, "fragment": "opening_blow"}
            out[i].pop("quality", None)
            openings.append([i, i + 1])
        elif after_kill(a, b):
            out[i + 1] = {**b, "continued_in": i, "fragment": "after_kill"}
            out[i + 1].pop("quality", None)
            afters.append([i, i + 1])
    if not (clipped or rejoined or killed or openings or afters):
        return doc
    meta = dict(doc.get("meta") or {})
    meta["repairs"] = {"version": 2, "clipped": clipped, "rejoined": rejoined, "killed_at_zero_health": killed,
                       "opening_blows": openings, "after_kills": afters,
                       "note": "Segments stretched across the next fight by a later death are clipped where it began; "
                               "a boss fight the meter cut in two (the same boss entity alive at the cut, its health "
                               "carrying on, resumed within 30 s) is one encounter at the second half's index, the "
                               "first half marked continued_in it. Meter 0.2.354 records neither fault. A boss's opening "
                               "blow cut off before the party's first hit joins the fight; what a fight's dead struck "
                               "after it was won (no party damage) is marked continued_in it. Meter 0.2.355 records "
                               "neither."}
    return {**doc, "meta": meta, "segments": out}
