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
* :func:`add_weave` — the damage of the basic-attack steps players weave between
  skills, at each class's recorded rate.

Numbers the client does not expose (animation lengths, the size of a few
"extra damage" effects, how often a boss can be broken) are collected in each
kit's ``TIMING`` / ``ASSUME`` tables so they are easy to audit and to tune once
real combat-log captures are available.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .base import ClassData, spec_slots
from .sorcerer import Kit  # single definition of the container; re-exported here

__all__ = ["Kit", "ms", "fallback_to_generic", "spec_options", "add_weave", "learned_only"]


def learned_only(kit: Kit, cd: ClassData, level: int) -> Kit:
    """Leave out the active skills a character of ``level`` has not learned yet (``unlock``): the
    kits are written for a level-45 character, who has every skill. Their passives already drop out
    at the effective level of 0 :meth:`Build.effective_levels` gives a skill not learned yet."""
    locked = {key for key, a in kit.actions.items()
              if (cd.skills.get(a.skill_id) or {}).get("kind") == "active"
              and (cd.skills[a.skill_id].get("unlock") or 1) > level}
    if not locked:
        return kit
    kept = lambda entry: (entry[0] if isinstance(entry, tuple) else entry) not in locked
    kit.actions = {key: a for key, a in kit.actions.items() if key not in locked}
    kit.policy = [entry for entry in kit.policy if kept(entry)]
    kit.essential = tuple(entry for entry in kit.essential if kept(entry))
    return kit


def ms(v) -> float:
    """A duration value: ``{"ms": 3000}`` -> 3.0 seconds, or a bare number."""
    return v["ms"] / 1000.0 if isinstance(v, dict) and "ms" in v else float(v)


def fallback_to_generic(A: dict, policy: list, build, cd: ClassData, notes: list,
                        *, pvp: bool = False, exclude: set | None = None, timing: dict | None = None) -> None:
    """Fill in any active/stigma the hand-written kit does not model.

    Mutates ``A`` and ``policy`` in place.  Only skills the build actually has
    (all actives, plus equipped stigmas) that are not already modeled by hand
    are added, each from its generic tooltip reading, inserted just before the
    filler so bespoke skills keep priority.  ``exclude`` lists skill ids the
    hand-written kit accounts for elsewhere (e.g. a pet's damage folded into a
    background stream) so the generic reading does not double-count them.
    ``timing`` is the kit's ``TIMING``: a skill it times (a measured action time)
    keeps that time instead of the generic default.
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
            A[k] = replace(a, cast=timing[k]) if timing and k in timing else a
            policy.insert(max(0, len(policy) - 1), k)
            notes.append(f"{a.name}: not in the hand-written kit, simulated from its tooltip")


def add_weave(A: dict, weave: dict, flat: float, coef: float, *, mp: float = 0.0,
              element: str | None = None, skip: tuple = (), step_mods: dict | None = None,
              on_step: Callable | None = None) -> None:
    """Woven basic-attack steps (0.2.309).

    Between two skills players tap a step of the class's basic-attack chain and
    cancel it after 0.10-0.16 s.  The kits' measured action times already hold
    that time (docs/methodology.md "Measured action times"); this adds the steps'
    damage and MP: ``weave["after"][key]`` steps after a skill recorded often
    enough, ``weave["per_press"]`` after any other, none after ``skip`` (the basic
    chain pressed on its own).  The rate accumulates and each whole step lands as
    one hit, so per-hit bonuses (Critical Attack, flat additions) count once a
    step.  ``weave["steps"]`` gives each step's name, its share of the woven steps
    and its damage per press against the first step (``flat`` / ``coef``); steps
    are dealt to keep those shares.  A woven step is a press of that step, so the
    specializations of the skill it is ride along: ``step_mods`` gives a step
    index's per-hit stat adds and ``on_step(sim, index)`` runs after each step.
    Mutates ``A`` in place.
    """
    after, default, steps = weave.get("after", {}), weave.get("per_press", 0.0), weave["steps"]
    for key, a in list(A.items()):
        n = after.get(key, default)
        if key in skip or n <= 0:
            continue

        def on_cast(sim, act, inner=a.on_cast, n=n):
            if inner is not None:
                inner(sim, act)
            st = sim.kit_state.setdefault("weave", {"due": 0.0, "dealt": [0] * len(steps)})
            st["due"] += n
            while st["due"] >= 1.0 - 1e-9:
                st["due"] -= 1.0
                total = sum(st["dealt"]) + 1
                i = max(range(len(steps)), key=lambda j: steps[j][1] * total - st["dealt"][j])
                st["dealt"][i] += 1
                name, _, ratio = steps[i]
                sim.hit(f"{name} (woven)", flat * ratio, coef * ratio, element=element,
                        mods=(step_mods or {}).get(i))
                if mp:
                    sim.gain_mp(mp)
                if on_step is not None:
                    on_step(sim, i)
        A[key] = replace(a, on_cast=on_cast)


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
