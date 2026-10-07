"""Explicit trained-level/equipped-stigma constraints, without utility coefficients."""
from __future__ import annotations

from ..kit.base import sp_to_reach, stigma_points_to_reach

NOTE = ("User-selected trained skill/stigma minimums. Reserved stigmas stay equipped. "
        "Daevanion/gear bonuses and selected specialties may change; effective-level unlocks are not locked. "
        "Use utility skills manually when they are absent from the damage rotation. These constraints "
        "do not simulate CC, mobility, shields, opponent defenses or win probability. Damage baselines "
        "and stat priorities remain unconstrained references.")


def prepare(cd, options, budgets):
    if options is None:
        return None
    if not isinstance(options, dict) or set(options)-{"sp", "stigmas"}:
        raise ValueError("Skill reserves need sp and stigmas allocation objects")
    result = {"sp": {}, "stigmas": {}}
    for field, kinds, cap in (("sp", ("active", "passive"), 10), ("stigmas", ("stigma",), 20)):
        values = options.get(field, {})
        if not isinstance(values, dict) or len(values)>len(cd.skills):
            raise ValueError("Invalid skill reserve allocation")
        for key, level in values.items():
            if isinstance(key, bool) or not str(key).isascii() or not str(key).isdigit():
                raise ValueError("Reserve a known skill ID")
            sid = int(key)
            skill = cd.skills.get(sid)
            if (not skill or skill["kind"] not in kinds or type(level) is not int
                    or not 1 <= level <= min(cap, skill.get("buyMax", cap) if field=="sp" else cap)):
                raise ValueError("Reserve levels must fit the skill's purchasable range")
            result[field][sid] = level
    if len(result["stigmas"])>cd.budget(45)["slots"]:
        raise ValueError("Too many reserved stigmas for the available equip slots")
    if sum(sp_to_reach(lv) for lv in result["sp"].values())>budgets["skill"]:
        raise ValueError("Reserved trained skills exceed the skill-point budget")
    if sum(stigma_points_to_reach(lv) for lv in result["stigmas"].values())>budgets["stigma"]:
        raise ValueError("Reserved stigmas exceed the stigma-point budget")
    return result if any(result.values()) else None


def meets(build, plan):
    return not plan or (all(build.sp.get(sid,1)>=lv for sid,lv in plan["sp"].items())
        and all(sid in build.stigmas and build.stigmas[sid]>=lv for sid,lv in plan["stigmas"].items()))


def describe(cd, build, plan):
    if not plan:
        return None
    return {"version": 1, "note": NOTE, "met": meets(build,plan),
            "skills": [{"id":sid,"name":cd.skills[sid]["name"],"kind":cd.skills[sid]["kind"],
                        "minimum":level,"selected":(build.stigmas if field=="stigmas" else build.sp).get(sid,1)}
                       for field in ("sp","stigmas") for sid,level in sorted(plan[field].items())]}
