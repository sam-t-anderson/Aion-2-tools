"""Explain modeled specialty choices and thresholds without assuming profile choices."""
import time

from .base import SPEC_SLOT_LEVELS, spec_slots


def free_marks(cd, build, evaluate, *, levels: dict | None = None, budget_s: float = 25.0) -> dict[int, set]:
    """The chosen effects the model is indifferent about (0.2.368): a chosen effect of an active skill that adds
    nothing to the simulated damage (the build scores the same without it). The optimizer keeps such a pick only
    because it fills a slot (its lowest-numbered option, usually a shield or a resource), so it is a choice for
    the player, not a recommendation. ``evaluate(build)`` returns the build's modeled DPS; the check stops
    after ``budget_s`` seconds and leaves the rest unmarked (decisive by default). ``levels`` are the effective
    levels that decide which effects are available (the prepared build's, gear included) when ``build`` is the
    bare build ``evaluate`` prepares itself."""
    levels = levels or build.effective_levels(cd)
    base = evaluate(build)
    out: dict[int, set] = {}
    started = time.monotonic()
    for sid, chosen in build.specs.items():
        skill = cd.skills.get(sid)
        if not skill or skill["kind"] != "active" or not chosen:
            continue
        if not any(e["unlock"] <= levels.get(sid, 1) for e in skill.get("specs", [])):
            continue
        for x in chosen:
            if time.monotonic() - started > budget_s:
                return out
            b2 = build.copy()
            b2.specs[sid] = tuple(e for e in chosen if e != x)
            if abs(evaluate(b2) - base) <= base * 1e-6:
                out.setdefault(sid, set()).add(x)
    return out


def describe(cd, build, free: dict | None = None):
    """build must already include gear levels (as returned by run.prepare). ``free`` (from :func:`free_marks`)
    names the chosen effects the model does not distinguish from their alternatives."""
    levels = build.effective_levels(cd)
    free = free or {}
    rows = []
    for sid, skill in cd.skills.items():
        effects = skill.get("specs") or []
        if not effects or skill["kind"] not in ("active", "stigma"):
            continue
        if skill["kind"] == "stigma" and sid not in build.stigmas:
            continue
        level = levels.get(sid, 1)
        automatic = skill["kind"] == "stigma"
        chosen = set(build.specs.get(sid, ()))
        items = [{"id": effect["id"], "number": i+1, "text": effect["text"],
                  "unlock": effect["unlock"], "available": level >= effect["unlock"],
                  "selected": level >= effect["unlock"] and (automatic or effect["id"] in chosen),
                  "free": effect["id"] in free.get(sid, ())}
                 for i, effect in enumerate(effects)]
        later = sorted({e["unlock"] for e in items if e["unlock"] > level})
        next_slot = next((n for n in SPEC_SLOT_LEVELS if n > level), None) if not automatic else None
        rows.append({"id": sid, "skill": skill["name"], "kind": skill["kind"], "level": level,
                     "slots": None if automatic else spec_slots(level), "automatic": automatic,
                     "effects": items, "next_effect_level": later[0] if later else None,
                     "next_slot_level": next_slot,
                     "free": sum(1 for e in items if e["selected"] and e["free"])})
    return sorted(rows, key=lambda row: (row["automatic"], -row["level"], row["skill"]))
