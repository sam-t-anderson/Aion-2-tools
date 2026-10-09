"""Shared helpers for the hand-written class kits.

Each hand-written kit (``gladiator.py``, ``templar.py`` ...) encodes one class's
real skill interactions — chains, self-applied crowd control that gates a
follow-up, stacking passives and damage-amp buffs with real uptime — reading
every damage number from ``data/global/classes/<cls>.json`` at the build's
effective level.  The pieces that are the same for every class live here:

* :class:`Kit` — the container the simulator consumes (defined in
  :mod:`aion2calc.kit.sorcerer`, re-exported so kits import it from one place).
* :func:`fallback_to_generic` — any active/stigma the hand-written kit does not
  model is pulled from the tooltip-driven :mod:`aion2calc.kit.generic`, so new
  content is simulated without code changes (exactly as ``sorcerer.py`` does).
* :func:`spec_options` — the legal specialization combinations per skill, used
  by the optimizer.

Numbers the client does not expose (animation lengths, the size of a few
"extra damage" effects, how often a boss can be broken) are collected in each
kit's ``TIMING`` / ``ASSUME`` tables so they are easy to audit and to tune once
real combat-log captures are available.
"""
from __future__ import annotations

from .base import ClassData, spec_slots
from .sorcerer import Kit  # single definition of the container; re-exported here

__all__ = ["Kit", "ms", "fallback_to_generic", "spec_options"]


def ms(v) -> float:
    """A duration value: ``{"ms": 3000}`` -> 3.0 seconds, or a bare number."""
    return v["ms"] / 1000.0 if isinstance(v, dict) and "ms" in v else float(v)


def fallback_to_generic(A: dict, policy: list, build, cd: ClassData, notes: list,
                        *, pvp: bool = False, exclude: set | None = None) -> None:
    """Fill in any active/stigma the hand-written kit does not model.

    Mutates ``A`` and ``policy`` in place.  Only skills the build actually has
    (all actives, plus equipped stigmas) that are not already modeled by hand
    are added, each from its generic tooltip reading, inserted just before the
    filler so bespoke skills keep priority.  ``exclude`` lists skill ids the
    hand-written kit accounts for elsewhere (e.g. a pet's damage folded into a
    background stream) so the generic reading does not double-count them.
    """
    known = {a.skill_id for a in A.values()} | (exclude or set())
    unknown = {sid for sid, s in cd.skills.items()
               if sid not in known and s["kind"] in ("active", "stigma")
               and (s["kind"] != "stigma" or sid in build.stigmas)}
    if not unknown:
        return
    from . import generic
    g = generic.build_kit(build, cd, pvp=pvp)
    for k, a in g.actions.items():
        if a.skill_id in unknown and k not in A and not a.is_filler:
            A[k] = a
            policy.insert(max(0, len(policy) - 1), k)
            notes.append(f"{a.name}: not in the hand-written kit, simulated from its tooltip")


def spec_options(cd: ClassData, build) -> dict[int, list[tuple]]:
    """All legal spec combinations per active skill at the build's levels."""
    from itertools import combinations
    L = build.effective_levels(cd)
    out: dict[int, list[tuple]] = {}
    for sid, s in cd.skills.items():
        if s["kind"] != "active" or not s.get("specs"):
            continue
        lvl = L.get(sid, 1)
        avail = [x["id"] for x in s["specs"] if x["unlock"] <= lvl]
        k = min(spec_slots(lvl), len(avail))
        out[sid] = [tuple(c) for c in combinations(avail, k)] if k > 0 else [()]
    return out
