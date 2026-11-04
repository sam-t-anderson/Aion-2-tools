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
* :func:`add_stagger_skill` — the skill every class can use only on a staggered
  boss, at the recorded number of hits a stagger (all eight classes since 0.2.380).

Numbers the client does not expose (animation lengths, the size of a few
"extra damage" effects, how often a boss can be broken) are collected in each
kit's ``TIMING`` / ``ASSUME`` tables so they are easy to audit and to tune once
real combat-log captures are available.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Callable

from ..model.stats import MULTIHIT_BONUS
from ..sim.engine import Action
from .base import ClassData, spec_slots
from .sorcerer import Kit  # single definition of the container; re-exported here

__all__ = ["Kit", "ms", "fallback_to_generic", "spec_options", "add_weave", "learned_only", "add_stagger_skill"]

#: The boss scenario's stagger windows last 8 s (``scenarios.boss``): a stagger skill held to one train of presses
#: a window comes back after that long, whatever cooldowns its own hits or other skills take off.
STAGGER_WINDOW = 8.0
#: Hits a press of a stagger skill lands, 0.15 s apart (the recorded presses; the KR hit profiles say 4 too).
PRESS_HITS = 4
#: What "Multi-Hit on hit" adds to a hit (0.2.380). The game folds a Multi-Hit's extra hits into the hit's own record,
#: each a tenth of its total, and the option always lands four. Against the same player's hits of the same skill
#: without one, within 3 s (the same buffs), a hit with k extra hits is 1.05, 1.10, 1.16 and 1.20 times as large for
#: k = 1 to 4, critical or not, over 15-23 skills in the captures: about 5 % an extra hit, not the damage model's
#: 12.5 % for any Multi-Hit (docs/methodology.md "Storm Rampage and Flame Scattershot from the recordings").
MULTI_HIT_ON_HIT = 0.20


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


def add_stagger_skill(A: dict, build, cd: ClassData, levels: dict, sid: int, key: str, *, hits: float, hit: float,
                      cast: float, element: str | None = None) -> Action | None:
    """The skill a class can use only on a staggered boss (0.2.379; docs/methodology.md "The stagger skills from
    the recordings"): the Gladiator's Sword Aura Rampage, the Templar's Flash Rampage, the Ranger's Arrow Scattershot,
    the Spiritmaster's Rapid Scattershot, the Cleric's Lightning Strike Scattershot, the Chanter's Gust Rampage, and
    since 0.2.380 the Assassin's Storm Rampage and the Sorcerer's Flame Scattershot.

    It has no cooldown, so the generic reading takes it for a filler and :func:`fallback_to_generic` leaves it out.
    A press lands four hits 0.15 s apart, and the recorded players press it back to back for the rest of a stagger
    once their opening skills are out, one train of presses a stagger. The action is that train: ``hits`` hits in
    ``cast`` seconds at 0 % Combat Speed, each ``hit`` of the tooltip's value (the tooltip split evenly over a
    press's four hits would be 0.25), of ``element``, at most once a stagger window. Its options come from their
    texts: "Multi-Hit on hit" lands four extra hits with every hit, which adds :data:`MULTI_HIT_ON_HIT` to it,
    "-1s all skill cooldowns on hit" takes that off every other cooldown at each hit (one record a hit: the extra
    hits are inside it), and "Restores N MP" restores it a press (a hit, with "on hit"); the shield and the mobile
    option change nothing the simulation models. Mutates ``A``; returns the action, or None when the skill is not
    learned.
    """
    s = cd.skills.get(sid)
    level = levels.get(sid, 0)
    pairs = [x for x in (cd.vals(sid, level) or []) if isinstance(x, list) and len(x) == 2] if s and level > 0 else []
    if not pairs:
        return None
    flat, coef = float(pairs[0][0]), float(pairs[0][1]) / 100.0
    picked = set(build.specs.get(sid, ()))
    texts = [x.get("text") or "" for x in s.get("specs", []) if x["id"] in picked and x["unlock"] <= level]
    multi = any(t.strip() == "Multi-Hit on hit" for t in texts)
    cdr = sum(float(m.group(1)) for t in texts
              if (m := re.search(r"-(\d+(?:\.\d+)?)s (?:to )?all (?:skill )?cooldowns on hit", t)))
    mp_press = mp_hit = 0.0
    for t in texts:
        if m := re.search(r"Restores (\d+) MP( on hit)?", t):
            if m.group(2):
                mp_hit += float(m.group(1))
            else:
                mp_press += float(m.group(1))
    n = max(1, round(hits))
    # the "multi" tag is a certain Multi-Hit (no Multi-Hit chance on top) at the damage model's generic 12.5 %; the
    # factor brings it to what four extra hits add
    tags = ("multi",) if multi else ()
    gain = (1.0 + MULTI_HIT_ON_HIT) / (1.0 + MULTIHIT_BONUS) if multi else 1.0

    def each(sim, t, i):
        if cdr:
            sim.reduce_cd("all", cdr)          # its own cooldown is the stagger window's and stays
        gain = mp_hit + (mp_press if i % PRESS_HITS == 0 else 0.0)
        if gain:
            sim.gain_mp(gain)

    def on_cast(sim, a):
        cs = sim.base.combat_speed + sim.stat_mods(sim.t).get("combat_speed", 0.0) + a.skill_speed
        pressing = a.cast / max(0.2, 1.0 + cs)
        sim.hit(a.name, flat * hit * n, coef * hit * n, n=n, spread=pressing * (n - 1) / n, tags=tags, mult=gain,
                element=element, on_each=each if (cdr or mp_press or mp_hit) else None)
    A[key] = Action(key, s["name"], sid, cast, cooldown=STAGGER_WINDOW, affected_by_cdr=False,
                    requires=("stagger",), on_cast=on_cast, element=element)
    return A[key]


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
