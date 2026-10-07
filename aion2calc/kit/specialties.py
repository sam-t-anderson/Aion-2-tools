"""Explain modeled specialty choices and thresholds without assuming profile choices."""
from .base import SPEC_SLOT_LEVELS, spec_slots


def describe(cd, build):
    """build must already include gear levels (as returned by run.prepare)."""
    levels = build.effective_levels(cd)
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
                  "selected": level >= effect["unlock"] and (automatic or effect["id"] in chosen)}
                 for i, effect in enumerate(effects)]
        later = sorted({e["unlock"] for e in items if e["unlock"] > level})
        next_slot = next((n for n in SPEC_SLOT_LEVELS if n > level), None) if not automatic else None
        rows.append({"id": sid, "skill": skill["name"], "kind": skill["kind"], "level": level,
                     "slots": None if automatic else spec_slots(level), "automatic": automatic,
                     "effects": items, "next_effect_level": later[0] if later else None,
                     "next_slot_level": next_slot})
    return sorted(rows, key=lambda row: (row["automatic"], -row["level"], row["skill"]))
