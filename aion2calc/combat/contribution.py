"""Estimated buff contribution: how much of each player's damage came from other players' damage
buffs and debuffs, and how much their own buffs added to other players' damage (an rDPS-style split).

These are estimates, not records, and they are kept out of rankings and parse percentiles until they
have been checked against real data (:func:`pool_checks`). The recorded parts are each effect's window,
who applied it and the hits it covered (meter 0.2.306 or later). The estimated parts:

* **The buff's size** comes from the caster's skill level: the official profile uploaded with the log
  when it lists the skill, else the level the effect record carries (inferred: a stigma aura's effect id
  names the level band it reached, 5-9, 10-14 and so on, and a passive's names its level), else the
  typical top player's level for that skill.
* **How much a +X % boost adds to one hit** follows the damage formula's additive boost bucket: a hit
  with the buff did ``1 + B + X - tolerance`` times its base, so ``X / (1 + B + X - tolerance)`` of it
  came from the buff. ``B`` (the player's other damage boosts) is not recorded, so it is the typical
  build's for the player's class; the tolerance is 30 % against a boss and 10 % otherwise, the values
  the optimizer's scenarios use.

Only buffs whose effect on damage is a known number are credited: the PvE Damage Boost auras
(Undefeated Mantra, Light of Protection), the party PvE Damage Boost on block (Fury, Experienced
Counterstrike) and the enemy PvE Damage Tolerance cuts (Chain of Torment, Earth's Promise). Defense cuts
need the boss's Defense and Combat Speed buffs change how many hits land, so neither is credited.
Pet hits are left unadjusted (whether party buffs reach pets is not known)."""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from functools import lru_cache

#: The credited buffs. ``field`` is the PvE value's index in the skill's per-level values (percent),
#: ``group`` the effects that do not stack with each other (the strongest applies), ``on`` whether it
#: sits on the party ("party") or on the enemy ("enemy"), ``level`` how its effect id encodes the level.
BUFFS = {
    18190000: {"name": "Undefeated Mantra", "cls": "chanter", "field": 0, "group": "aura", "on": "party", "level": "band"},
    17410000: {"name": "Light of Protection", "cls": "cleric", "field": 0, "group": "aura", "on": "party", "level": "band"},
    12780000: {"name": "Fury", "cls": "templar", "field": 1, "group": "block", "on": "party", "level": "direct"},
    11780000: {"name": "Experienced Counterstrike", "cls": "gladiator", "field": 1, "group": "block", "on": "party", "level": "direct"},
    17070000: {"name": "Chain of Torment", "cls": "cleric", "field": 2, "group": "tolerance", "on": "enemy", "level": None},
    18780000: {"name": "Earth's Promise", "cls": "chanter", "field": 0, "group": "tolerance", "on": "enemy", "level": "direct"},
}
#: Earth's Promise's cut does not apply while Chain of Torment's does (its description says so).
YIELDS = {18780000: 17070000}
BOSS_TOLERANCE, OTHER_TOLERANCE = 0.30, 0.10
GROUPS = ("aura", "block", "tolerance")
LIMIT = 100


def _family(skill_id):
    return skill_id - skill_id % 10_000 if isinstance(skill_id, int) and not isinstance(skill_id, bool) and skill_id > 0 else None


@lru_cache(maxsize=None)
def _class_data(cls):
    from ..kit.base import ClassData
    return ClassData(cls)


@lru_cache(maxsize=None)
def typical_boost(cls):
    """The typical build's own additive damage boosts (the ``B`` of the boost bucket) for a class."""
    try:
        from ..run import Scenario, prepare
        from ..scenarios import typical_build
        _, _, _, stats = prepare(typical_build(cls), Scenario(loadout=f"{cls}_l45_global_median"))
        return round(stats.derived().amp, 4)
    except Exception:
        return 0.2


@lru_cache(maxsize=None)
def typical_level(family):
    """The typical top player's level of a credited skill (its class's typical build)."""
    info = BUFFS[family]
    try:
        from ..scenarios import typical_build
        cd = _class_data(info["cls"])
        build = typical_build(info["cls"])
        return int(build.stigmas.get(family) or build.effective_levels(cd).get(family) or 1)
    except Exception:
        return 1


def value_pct(family, level):
    """The credited PvE value (percent) of a skill at a level, from the bundled skill table."""
    info = BUFFS[family]
    try:
        cd = _class_data(info["cls"])
        top = len(cd.skills[family].get("vals") or []) or 1
        value = cd.vals(family, max(1, min(top, int(level))))[info["field"]]
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    except Exception:
        return None


def level_from_effect(family, effect_id):
    """``(level, low, high)`` the effect id names, or None. Effect ids are the skill variant x 10 plus a
    stack digit; a stigma aura's variant names the level band it reached (thresholds at 5, 10, 15, 20,
    25: ``x1`` = 5-9 ... ``x4`` = 20-24) and a passive's names its level. Inferred from the captures, not a
    published rule: Power of the Storm's band 1 matched the level 5 its 12 s duration implies, and a
    passive's code matched the level its duration implies."""
    info = BUFFS.get(family)
    if not info or not info["level"] or not isinstance(effect_id, int) or effect_id < 100_000_000:
        return None
    variant = effect_id // 10
    if variant - variant % 10_000 != family:
        return None
    code = variant % 10_000
    if info["level"] == "band":
        band = code // 10
        if not 0 <= band <= 5:
            return None
        low, high = (1, 4) if band == 0 else (5 * band, min(25, 5 * band + 4))
        return (low + high) // 2, low, high
    return (code, code, code) if 1 <= code <= 40 else None


def profile_level(player, family):
    """The skill's level in the player's uploaded official profile, or None."""
    snapshot = (player or {}).get("profile_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("status") not in ("ready", "partial"):
        return None
    for skill in ((snapshot.get("data") or {}).get("skill") or {}).get("skillList") or []:
        if isinstance(skill, dict) and skill.get("id") == family:
            level = skill.get("skillLevel")
            return int(level) if isinstance(level, int) and not isinstance(level, bool) and level > 0 else None
    return None


def _resolve(family, source_player, effect_id):
    """``(value_fraction, level, basis)`` for one application of a credited buff."""
    if BUFFS[family]["level"] is None:
        value = value_pct(family, 1)
        return (value / 100 if value is not None else None), None, "fixed"
    level = profile_level(source_player, family)
    basis = "profile"
    if level is None:
        found = level_from_effect(family, effect_id)
        if found:
            level, basis = found[0], "effect"
    if level is None:
        level, basis = typical_level(family), "typical"
    value = value_pct(family, level)
    return (value / 100 if value is not None else None), level, basis


def _windows(segment, friendly, by_id):
    """Credited effect windows: ``(start, end, side, target, family, source, value, level, basis)``."""
    out, resolved = [], {}
    for row in segment.get("effects") or []:
        family = _family(row.get("skill_id"))
        info = BUFFS.get(family)
        if not info:
            continue
        target, source = row.get("target"), row.get("source")
        if info["on"] == "party" and target not in friendly:
            continue
        if info["on"] == "enemy" and target in friendly:
            continue
        key = (family, source, row.get("effect_id"))
        if key not in resolved:
            resolved[key] = _resolve(family, by_id.get(source), row.get("effect_id"))
        value, level, basis = resolved[key]
        if value is None or row.get("end") is None or row["end"] <= row["t"]:
            continue
        out.append((row["t"], row["end"], info["on"], target, family, source, value, level, basis))
    return out


def _applied(entries):
    """The credited entries that apply to one hit: per non-stacking group the strongest (ties shared)."""
    by_group = defaultdict(list)
    families = {e[0] for e in entries}
    for family, source, value in entries:
        if YIELDS.get(family) in families:
            continue
        by_group[BUFFS[family]["group"]].append((family, source, value))
    out = []
    for group in GROUPS:
        rows = by_group.get(group)
        if not rows:
            continue
        top = max(v for _, _, v in rows)
        winners = [r for r in rows if r[2] >= top - 1e-9]
        # One buff from several casters (two Chanters' Mantras) applies once: the credit is shared.
        out += [(family, source, value, len(winners)) for family, source, value in winners]
    return out


def summarize(doc: dict, index: int) -> dict | None:
    """The estimated buff contribution for one segment, or None when it cannot be estimated (no
    recorded effect windows, or a PvP segment: PvP boosts and tolerances differ)."""
    from .a2log import combat_mode
    from .pressure import friendly_ids
    segment = doc["segments"][index]
    if combat_mode(doc, segment) == "pvp" or not segment.get("effects"):
        return None
    players = {p["id"] for p in doc.get("players", [])}
    by_id = {p["id"]: p for p in doc.get("players", [])}
    entities = {e["id"]: e for e in segment.get("entities", [])}
    friendly = friendly_ids(players, entities)
    windows = _windows(segment, friendly, by_id)
    if not windows:
        return None
    classes = {p["id"]: str(p.get("class") or "").lower() for p in doc.get("players", [])}
    boosts = {pid: typical_boost(cls) if cls in ("gladiator", "templar", "assassin", "ranger", "sorcerer",
                                                 "spiritmaster", "cleric", "chanter") else 0.2
              for pid, cls in classes.items()}
    # Break windows multiply everyone's damage, so the check leaves out the hits that land in one.
    from .actions import stagger
    breaks = defaultdict(list)
    for boss in stagger(segment, entities):
        breaks[boss["entity"]] = [(b["t"], b["end"]) for b in boss["breaks"]]
    hits = sorted((h for h in segment.get("hits") or []
                   if h.get("player") in players and h.get("target") not in friendly and not h.get("pet")),
                  key=lambda h: h["t"])
    # Sweep the hits in time order against the windows that cover them.
    events = sorted(((w[0], i) for i, w in enumerate(windows)))
    ends, active = [], defaultdict(dict)            # (side, target) -> {window index: (family, source, value)}
    received, given = defaultdict(float), defaultdict(float)
    pairs = defaultdict(float)                       # (source, recipient, family) -> damage
    covered = defaultdict(float)
    check = defaultdict(lambda: defaultdict(lambda: [[], [], 0.0]))   # group -> (player, skill) -> [off, on, pred]
    cursor = 0
    for hit in hits:
        t = hit["t"]
        while cursor < len(events) and events[cursor][0] <= t:
            i = events[cursor][1]
            w = windows[i]
            active[(w[2], w[3])][i] = (w[4], w[5], w[6])
            heapq.heappush(ends, (w[1], i))
            cursor += 1
        while ends and ends[0][0] < t:
            _, i = heapq.heappop(ends)
            active[(windows[i][2], windows[i][3])].pop(i, None)
        player = hit["player"]
        entries = list(active.get(("party", player), {}).values()) + list(active.get(("enemy", hit.get("target")), {}).values())
        applied = _applied(entries)
        boss = bool(entities.get(hit.get("target"), {}).get("is_boss"))
        tolerance = BOSS_TOLERANCE if boss else OTHER_TOLERANCE
        total = sum(value / share for _, _, value, share in applied)
        multiplier = max(0.1, 1 + boosts.get(player, 0.2) + total - tolerance)
        damage = hit["damage"]
        for family, source, value, share in applied:
            credit = damage * value / share / multiplier
            covered[family] += damage / share
            if source == player:
                continue                          # a player's own buff is their own damage
            received[player] += credit
            given[source if source is not None else ""] += credit
            pairs[(source if source is not None else "", player, family)] += credit
        # The check: the same player's same skill with only one buff group up (another player's) against
        # nothing credited up, on plain hits (no critical, double, perfect or periodic damage) outside breaks.
        if not (hit.get("crit") or hit.get("double") or hit.get("perfect") or hit.get("dot")
                or any(a <= t <= b for a, b in breaks.get(hit.get("target"), ()))):
            skill = (player, hit.get("skill_id"))
            if not applied:
                for group in GROUPS:
                    check[group][skill][0].append(damage)
            elif all(s != player for _, s, _, _ in applied) and len({BUFFS[f]["group"] for f, _, _, _ in applied}) == 1:
                group = BUFFS[applied[0][0]]["group"]
                cell = check[group][skill]
                cell[1].append(damage)
                base = max(0.1, 1 + boosts.get(player, 0.2) - tolerance)
                cell[2] += math.log((base + total) / base)
    damage_by = defaultdict(float)
    for h in segment.get("hits") or []:
        if h.get("player") in players:
            damage_by[h["player"]] += h["damage"]
    rows = []
    for pid in sorted(set(damage_by) | set(received) | {s for s in given if s in players},
                      key=lambda p: -damage_by.get(p, 0.0)):
        damage = damage_by.get(pid, 0.0)
        rows.append({"player": pid, "damage": round(damage), "received": round(received.get(pid, 0.0)),
                     "given": round(given.get(pid, 0.0)),
                     "adjusted_damage": round(damage - received.get(pid, 0.0)),
                     "contribution_damage": round(damage - received.get(pid, 0.0) + given.get(pid, 0.0)),
                     "received_pct": round(100 * received.get(pid, 0.0) / damage, 1) if damage else None,
                     "boost_assumed": boosts.get(pid)})
    unlisted = sum(v for s, v in given.items() if s not in players)
    buffs = {}
    for w in windows:
        key = (w[4], w[5])
        row = buffs.setdefault(key, {"source": w[5], "skill_id": w[4], "skill": BUFFS[w[4]]["name"],
                                     "group": BUFFS[w[4]]["group"], "value_pct": round(100 * w[6], 2),
                                     "level": w[7], "basis": w[8], "windows": 0})
        row["windows"] += 1
    checks = []
    for group, cells in check.items():
        weight = weighted_log = weighted_pred = 0.0
        on = off = used = 0
        for (player, skill), (off_hits, on_hits, pred) in cells.items():
            if len(off_hits) >= 5 and len(on_hits) >= 5:
                w = min(len(off_hits), len(on_hits))
                weight += w
                weighted_log += w * math.log((sum(on_hits) / len(on_hits)) / (sum(off_hits) / len(off_hits)))
                weighted_pred += w * pred / len(on_hits)
                on += len(on_hits)
                off += len(off_hits)
                used += 1
        if weight:
            checks.append({"group": group, "pairs": used, "hits_on": on, "hits_off": off, "weight": weight,
                           "weighted_log": weighted_log, "weighted_predicted_log": weighted_pred,
                           "measured_pct": round(100 * (math.exp(weighted_log / weight) - 1), 1),
                           "estimated_pct": round(100 * (math.exp(weighted_pred / weight) - 1), 1)})
    return {"players": rows,
            "given": sorted(({"source": s or None, "recipient": r, "skill_id": f, "skill": BUFFS[f]["name"],
                              "damage": round(v)} for (s, r, f), v in pairs.items() if v >= 0.5),
                            key=lambda r: -r["damage"])[:LIMIT],
            "unlisted_source_damage": round(unlisted),
            "buffs": sorted(buffs.values(), key=lambda r: (r["group"], -r["value_pct"]))[:LIMIT],
            "covered_damage": {BUFFS[f]["name"]: round(v) for f, v in covered.items()},
            "checks": sorted(checks, key=lambda c: GROUPS.index(c["group"])),
            "assumptions": {"boss_tolerance": BOSS_TOLERANCE, "other_tolerance": OTHER_TOLERANCE,
                            "ranked": False}}


def pool_checks(results) -> list[dict]:
    """Pool the per-fight checks of several fights: per buff group, the measured gain in the same
    skill's average non-critical hit while the group was up (and no other credited buff was) against
    the gain the estimate predicts for those hits."""
    pooled = defaultdict(lambda: {"fights": 0, "pairs": 0, "hits_on": 0, "hits_off": 0, "weight": 0.0,
                                  "weighted_log": 0.0, "weighted_predicted_log": 0.0})
    for result in results:
        for c in (result or {}).get("checks") or []:
            p = pooled[c["group"]]
            p["fights"] += 1
            for key in ("pairs", "hits_on", "hits_off", "weight", "weighted_log", "weighted_predicted_log"):
                p[key] += c[key]
    out = []
    for group in GROUPS:
        p = pooled.get(group)
        if not p or not p["weight"]:
            continue
        out.append({"group": group, "fights": p["fights"], "pairs": p["pairs"], "hits_on": p["hits_on"],
                    "hits_off": p["hits_off"],
                    "measured_pct": round(100 * (math.exp(p["weighted_log"] / p["weight"]) - 1), 1),
                    "estimated_pct": round(100 * (math.exp(p["weighted_predicted_log"] / p["weight"]) - 1), 1)})
    return out
