"""Expected damage of a single hit.

Formula (community-verified pieces, see docs/methodology.md)::

    Attack      = (Attack bonuses + weapon roll) x (1 + Attack increase%)
    base        = Attack x coefficient + skill flat + PvE/Boss Attack + Pen/10 - Defense/10
    boost       = 1 + (Damage Boost + PvE Boost + Boss Boost + buffs) - target Damage Tolerance
                  (less Damage Tolerance reductions on the target, never below 0)
    element     = 1 + Fire/Water Attack%           (multiplicative)
    vulnerable  = 1 + "damage taken from caster" debuffs (multiplicative)
    weapon      = 1 + 0.66 x max(Weapon Damage Boost - target tolerance, 0)
    crit        = 1 + P(crit) x (0.5 + Crit Damage Boost)   [+ Critical Attack flat on crit]
    double      = Double (Smite) doubles damage; Perfect uses max weapon roll; they are exclusive
    multi-hit   = 1 + P(multi) x 0.125

A direct hit lands from the front, from behind or from the side, in the target's shares (each
class's recorded mix on bosses). Front / Back Attack add flat damage, Front / Back Attack Damage
Boost is its own multiplier and Front / Back Attack Critical Hit adds Critical Hit, each on hits
from its side only; a hit from behind is never parried. The expected hit is the share-weighted sum.

Damage-over-time ticks ignore defense and position and never crit / double / perfect / multi-hit.
"""
from __future__ import annotations

from dataclasses import dataclass

from .stats import (CRIT_BASE, MULTIHIT_BONUS, PEN_FLAT, WEAPON_AMP_EFF, Derived,
                    crit_chance)


@dataclass
class HitContext:
    flat: float
    coef: float
    element: str | None = None
    tags: tuple = ()
    mult: float = 1.0


def _positions(d: Derived, target) -> tuple[float, float]:
    """(front, back) shares of direct hits: the class's recorded mix when the target asks for it."""
    if getattr(target, "class_positions", False) and d.positions:
        return d.positions
    return target.hit_positions()


def crit_probability(d: Derived, target, extra: float = 0.0) -> float:
    """Chance a direct hit crits, over the hit positions (Front / Back Attack Critical Hit apply
    to hits from their side)."""
    front, back = _positions(d, target)
    midpoint = 1024.52 if getattr(target, "is_player", False) else None
    stat = d.crit_stat + extra
    p = crit_chance(stat, target.crit_resist, midpoint=midpoint)
    side = 1.0 - front - back
    total = side * p
    for share, bonus in ((front, d.front_crit), (back, d.back_crit)):
        if share > 0.0:
            total += share * (crit_chance(stat + bonus, target.crit_resist, midpoint=midpoint) if bonus else p)
    return total


def expected_hit(d: Derived, mods: dict, target, ctx: HitContext) -> float:
    g = mods.get
    atk_pct = d.atk_pct + g("attack_pct", 0.0)
    atk_flat = d.atk_flat + g("attack", 0.0)
    w_avg = 0.5 * (d.weapon_min + d.weapon_max)
    a_avg = (atk_flat + w_avg) * (1 + atk_pct)
    a_max = (atk_flat + d.weapon_max) * (1 + atk_pct)

    dot = "dot" in ctx.tags
    add = d.flat_add + g("flat_add", 0.0)
    base_avg = a_avg * ctx.coef + ctx.flat + add
    base_max = a_max * ctx.coef + ctx.flat + add

    boost_add = d.amp + g("amp", 0.0)
    if ctx.element == "fire":
        boost_add += g("amp_fire", 0.0)
    tolerance = max(0.0, target.tolerance - g("tol_red", 0.0))
    boost = max(0.1, 1.0 + boost_add - tolerance)
    elem = 1.0
    if ctx.element == "fire":
        elem += d.fire_amp + g("fire_amp", 0.0)
    elif ctx.element == "water":
        elem += d.water_amp + g("water_amp", 0.0)
    vuln = 1.0 + g("vuln", 0.0)
    if ctx.element == "fire":
        vuln += g("vuln_fire", 0.0)
    if dot:
        return base_avg * boost * elem * vuln * ctx.mult

    # penetration is already credited through flat_add (+Pen/10)
    cut = target.defense * PEN_FLAT if target.defense > 0 else 0.0
    weapon = 1.0 + WEAPON_AMP_EFF * max(d.weapon_amp + g("weapon_amp", 0.0) - target.weapon_tol, 0.0)
    guaranteed = "crit" in ctx.tags
    crit_stat = d.crit_stat + g("crit", 0.0)
    midpoint = 1024.52 if getattr(target, "is_player", False) else None
    crit_mult = CRIT_BASE + d.crit_dmg + g("crit_dmg", 0.0) - target.crit_dmg_tol
    crit_flat = d.crit_atk * (1.0 + crit_mult)
    p_d = min(1.0, max(0.0, d.double + g("double", 0.0) - target.double_resist))
    p_p = min(1.0, max(0.0, d.perfect + g("perfect", 0.0)))
    p_m = 1.0 if "multi" in ctx.tags else min(1.0, d.multihit + g("multihit", 0.0))
    w_avg_roll = (1 - p_d) * (1 - p_p) + 2.0 * p_d     # Double doubles the average roll
    w_max_roll = (1 - p_d) * p_p                        # Perfect uses the maximum roll
    parry = 0.0
    if target.parry > 0 and not guaranteed and "noparry" not in ctx.tags:
        parry = 0.5 * target.parry

    # Front / Back Attack Damage Boost is its own multiplicative bucket (it does not share the
    # Damage Boost bucket). Each position's hit is (roll x crit + Critical Attack) x its bucket.
    front, back = _positions(d, target)
    p_plain = None
    total = 0.0
    for share, flat, amp, crit_add, parried in (
            (front, d.front_atk, d.front_amp + g("front_amp", 0.0), d.front_crit, True),
            (back, d.back_atk, d.back_amp + g("back_amp", 0.0), d.back_crit, False),
            (1.0 - front - back, 0.0, 0.0, 0.0, True)):
        if share <= 0.0:
            continue
        lo, hi = base_avg + flat, base_max + flat
        if cut:
            lo, hi = max(1.0, lo - cut), max(1.0, hi - cut)
        if guaranteed:
            p_c = 1.0
        elif crit_add:
            p_c = crit_chance(crit_stat + crit_add, target.crit_resist, midpoint=midpoint)
        else:
            if p_plain is None:
                p_plain = crit_chance(crit_stat, target.crit_resist, midpoint=midpoint)
            p_c = p_plain
        hit = ((w_avg_roll * lo + w_max_roll * hi) * (1 + p_c * crit_mult) + p_c * crit_flat) * (1.0 + amp)
        if parried and parry:
            hit *= 1.0 - parry
        total += share * hit
    return total * boost * elem * vuln * weapon * (1 + p_m * MULTIHIT_BONUS) * ctx.mult
