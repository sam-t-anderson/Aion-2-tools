"""Boss enrage timers, for the live meter's estimated time-to-enrage (0.2.386).

``data/global/boss_enrage.json`` holds each timed boss's seconds from the pull until it enrages, by NPC code
(dungeon final bosses 300 s, Conquest Hard 240 s, the raids 480-600 s; Exploration tiers and mini-bosses have no
timer). The fight clock is the target's own: the party's first hit on it to the latest, the clock the time-to-kill
uses (``session``'s ``target_secs``).
"""
from __future__ import annotations

import math
from functools import lru_cache

from ..paths import read_json


@lru_cache(maxsize=1)
def _index() -> dict:
    doc = read_json("global", "boss_enrage.json")
    return {int(code): boss for boss in doc["bosses"] for code in boss["codes"]}


def enrage_timer(mob_code) -> dict | None:
    """The enrage entry for an NPC code, or None when the boss has no known timer."""
    try:
        code = int(mob_code)
    except (TypeError, ValueError):
        return None
    return _index().get(code)


def estimate(mob_code, elapsed_s: float, ttk: float | None = None) -> dict | None:
    """Seconds left before the boss enrages after ``elapsed_s`` of the fight, and whether the time-to-kill runs
    past it. None for a boss with no known timer."""
    timer = enrage_timer(mob_code)
    if timer is None:
        return None
    left = float(timer["enrage_s"]) - max(0.0, float(elapsed_s or 0.0))
    before_kill = (ttk is not None and math.isfinite(ttk) and ttk > max(0.0, left)) if left > 0 else False
    return {"enrage_s": timer["enrage_s"], "enrage_in": max(0.0, left), "enraged": left <= 0,
            "before_kill": bool(before_kill), "confidence": timer["confidence"], "measured": timer["measured"]}
