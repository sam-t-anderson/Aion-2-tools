"""Explicit trained-level/equipped-stigma constraints, without utility coefficients."""
from __future__ import annotations

from ..kit.base import sp_to_reach, stigma_points_to_reach, SPEC_SLOT_LEVELS

NOTE = ("User-selected and linked-window trained skill/stigma minimums. Reserved stigmas stay equipped. "
        "Reserved supporting effects stay selected; their effective-level unlock and slot requirements constrain trained points, fixed gear bonuses and connected Daevanion nodes. Other bonuses and specialties may change. "
        "Use utility skills manually when they are absent from the damage rotation. These constraints "
        "do not simulate CC, mobility, shields, opponent defenses or win probability. Damage baselines "
        "and stat priorities remain unconstrained references.")


def prepare(cd, options, budgets, gear_bonus=None):
    if options is None:
        return None
    if not isinstance(options, dict) or set(options)-{"sp", "stigmas", "specs"}:
        raise ValueError("Skill reserves need sp, stigmas and optional specs allocation objects")
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
    effects = options.get("specs", {})
    if not isinstance(effects, dict) or len(effects) > len(cd.skills):
        raise ValueError("Invalid supporting-effect reserves")
    required, minimum_effective = {}, {}
    for key, chosen in effects.items():
        if isinstance(key, bool) or not str(key).isascii() or not str(key).isdigit():
            raise ValueError("Reserve effects on a known active skill")
        sid = int(key)
        skill = cd.skills.get(sid)
        if not skill or skill["kind"] != "active" or not isinstance(chosen, list) or not 1 <= len(chosen) <= len(SPEC_SLOT_LEVELS):
            raise ValueError("Reserve one to three supporting effects on an active skill")
        catalog = {effect["id"]: effect for effect in skill.get("specs", [])}
        if any(type(effect) is not int or effect not in catalog for effect in chosen) or len(set(chosen)) != len(chosen):
            raise ValueError("Choose distinct supporting effects from this skill's catalog")
        unlock = max(SPEC_SLOT_LEVELS[len(chosen)-1], *(catalog[effect]["unlock"] for effect in chosen))
        minimum_effective[sid] = unlock
        required[sid] = tuple(sorted(chosen))
    if required:
        result["specs"] = required
        result["effective"] = minimum_effective
    if len(result["stigmas"])>cd.budget(45)["slots"]:
        raise ValueError("Too many reserved stigmas for the available equip slots")
    if sum(sp_to_reach(lv) for lv in result["sp"].values())>budgets["skill"]:
        raise ValueError("Reserved trained skills exceed the skill-point budget")
    if sum(stigma_points_to_reach(lv) for lv in result["stigmas"].values())>budgets["stigma"]:
        raise ValueError("Reserved stigmas exceed the stigma-point budget")
    return result if any(result.values()) else None


def meets(build, plan, cd=None):
    return not plan or (all(build.sp.get(sid,1)>=lv for sid,lv in plan["sp"].items())
        and all(sid in build.stigmas and build.stigmas[sid]>=lv for sid,lv in plan["stigmas"].items())
        and all(set(chosen) <= set(build.specs.get(sid, ())) for sid,chosen in plan.get("specs", {}).items())
        and (not plan.get("effective") or (cd is not None and
             all(build.effective_levels(cd).get(sid,1)>=level for sid,level in plan["effective"].items()))))


def describe(cd, build, plan):
    if not plan:
        return None
    return {"version": 3, "note": NOTE, "met": meets(build,plan,cd),
            "effective_levels": [{"id": sid, "name": cd.skills[sid]["name"], "minimum": level,
                                  "selected": build.effective_levels(cd).get(sid,1),
                                  "trained": build.sp.get(sid,1),
                                  "daevanion": cd.daevanion_levels(build.daevanion).get(sid,0),
                                  "gear": build.bonus.get(sid,0)}
                                 for sid,level in sorted(plan.get("effective", {}).items())],
            "effects": [{"skill": cd.skills[sid]["name"], "id": effect["id"], "text": effect["text"], "unlock": effect["unlock"], "selected": effect["id"] in build.specs.get(sid, ())}
                        for sid,chosen in plan.get("specs", {}).items() for effect in cd.skills[sid].get("specs", []) if effect["id"] in chosen],
            "skills": [{"id":sid,"name":cd.skills[sid]["name"],"kind":cd.skills[sid]["kind"],
                        "minimum":level,"selected":(build.stigmas if field=="stigmas" else build.sp).get(sid,1)}
                       for field in ("sp","stigmas") for sid,level in sorted(plan[field].items())]}


def include_survival(cd, plan, survival, budgets, gear_bonus=None):
    """Union validated personal reserves with linked timing requirements.

    Never overwrite a stricter user minimum or silently drop an effect to fit
    slots/budgets. Reuse normal reserve validation for the combined request.
    """
    linked = [w["skill_requirement"] for row in (survival or {}).get("opponents", [])
              for w in row.get("reductions", []) if w.get("skill_requirement")]
    if not linked:
        return plan
    raw = {field: dict((plan or {}).get(field, {})) for field in ("sp", "stigmas")}
    raw["specs"] = {sid: list(chosen) for sid,chosen in (plan or {}).get("specs", {}).items()}
    for req in linked:
        field = "stigmas" if req["kind"] == "stigma" else "sp"
        sid = req["id"]
        raw[field][sid] = max(raw[field].get(sid,1), req["minimum"])
        if req["effect_id"] is not None:
            raw["specs"][sid] = sorted(set(raw["specs"].get(sid, [])) | {req["effect_id"]})
    return prepare(cd, raw, budgets, gear_bonus)
