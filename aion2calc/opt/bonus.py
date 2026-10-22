"""Bonus skill levels from gear rolls and arcana cards, as a resource the preset search allocates.

A level-45 character carries skill levels the common planner loadout has none of: the skill options
rolled on its accessories and armour and the options of its five arcana cards. The community presets
were searched without them, so no skill in a preset passed level 14 (10 trained plus the Daevanion
levels); the fifth supporting effect (level 16) and the third selection slot (level 20) were never
reached, and the presets undersold what a build can do. The log server now records the highest bonus
levels its contributors have (``skill_bonus`` in the point observation: the total over every skill and
the most on one skill) and publishes them in the scoring policy as ``bonus = {"levels", "per_skill"}``;
the search spends them like points and the preset names the skills to put them on.

``allocate_pool`` spends the pool on the per-skill level curves the Daevanion/skill-point program uses
(DPS at each effective level, with the best supporting effects at each level), greedily by the next
level's gain, within the pool's total, its per-skill cap and the curve's last level. The optimizer then
re-solves the trained levels and Daevanion nodes around that and polishes the result with full
simulations (``Optimizer.polish_bonus``).
"""
from __future__ import annotations

#: Bounds a policy's bonus allowance keeps to: more bonus levels than gear and cards can carry.
MAX_POOL_LEVELS = 400
MAX_PER_SKILL = 40


def valid_pool(pool) -> bool:
    """A bonus allowance ``{"levels": total, "per_skill": the most on one skill}``: whole numbers from
    one up to the bounds."""
    return (isinstance(pool, dict) and set(pool) == {"levels", "per_skill"}
            and all(type(v) is int and v >= 1 for v in pool.values())
            and pool["levels"] <= MAX_POOL_LEVELS and pool["per_skill"] <= MAX_PER_SKILL)


def allocate_pool(curves: dict, effective: dict, pool: dict, max_level=None) -> dict:
    """``{sid: bonus levels}`` spending ``pool`` on ``curves``.

    ``curves[sid][L]`` is the value at effective level ``L`` (index 0 unused, as the Daevanion program
    takes them); ``effective[sid]`` the level the skill has before the pool (trained, Daevanion and any
    fixed gear bonus); ``max_level`` the highest level a skill may reach (one number or per skill; the
    curve's last level otherwise). Each step takes the run of levels on one skill that gains most per
    level, one level or several: a skill whose next levels gain little until the fifth supporting effect
    at 16 or the third slot at 20 is judged on the run that reaches them, not on its first level alone.
    A tie goes to the lowest id and the shorter run; a run that gains nothing is not spent.
    """
    total, per_skill = int(pool["levels"]), int(pool["per_skill"])
    level = {sid: int(effective.get(sid, 1)) for sid in curves}

    def cap(sid):
        last = len(curves[sid]) - 1
        if isinstance(max_level, dict):
            return min(last, int(max_level.get(sid, last)))
        return last if max_level is None else min(last, int(max_level))

    out: dict = {}
    left = total
    while left > 0:
        best, rate = None, 0.0
        for sid in sorted(curves):
            start = level[sid]
            if start < 1:
                continue
            longest = min(cap(sid) - start, per_skill - out.get(sid, 0), left)
            for run in range(1, longest + 1):
                per_level = (curves[sid][start + run] - curves[sid][start]) / run
                if per_level > rate + 1e-12:
                    best, rate = (sid, run), per_level
        if best is None:
            break
        sid, run = best
        out[sid] = out.get(sid, 0) + run
        level[sid] += run
        left -= run
    return out


def trim(bonus: dict, pool: dict | None) -> dict:
    """``bonus`` (``{key: levels}``) cut down to ``pool``: nothing without an allowance, no skill over
    ``per_skill``, and the total brought under ``levels`` by taking levels off the skills with the most
    (ties by key). Zero and negative levels are dropped."""
    out = {k: int(v) for k, v in (bonus or {}).items() if type(v) is int and v > 0}
    if not pool:
        return {}
    out = {k: min(v, int(pool["per_skill"])) for k, v in out.items()}
    while sum(out.values()) > int(pool["levels"]):
        k = max(sorted(out), key=lambda key: out[key])
        out[k] -= 1
        if out[k] <= 0:
            del out[k]
    return out
