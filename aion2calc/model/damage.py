"""Expected damage of a single hit.

Formula (community-verified pieces, see docs/methodology.md)::

    Attack      = (Attack bonuses + weapon roll) x (1 + Attack increase%)
    base        = Attack x coefficient + skill flat + PvE/Boss Attack + Pen/10 - Defense/10
    boost       = 1 + (Damage Boost + PvE Boost + Boss Boost + buffs) - target Damage Tolerance
    element     = 1 + Fire/Water Attack%           (multiplicative)
    vulnerable  = 1 + "damage taken from caster" debuffs (multiplicative)
    weapon      = 1 + 0.66 x max(Weapon Damage Boost - target tolerance, 0)
    crit        = 1 + P(crit) x (0.5 + Crit Damage Boost)   [+ Critical Attack flat on crit]
    double      = Double (Smite) doubles damage; Perfect uses max weapon roll; they are exclusive
    multi-hit   = 1 + P(multi) x 0.125

Damage-over-time ticks ignore defense and never crit / double / perfect / multi-hit.
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


def expected_hit(d: Derived, mods: dict, target, ctx: HitContext) -> float:
    g = mods.get
    atk_pct = d.atk_pct + g("attack_pct", 0.0)
    atk_flat = d.atk_flat + g("attack", 0.0)
    w_avg = 0.5 * (d.weapon_min + d.weapon_max)
    a_avg = (atk_flat + w_avg) * (1 + atk_pct)
    a_max = (atk_flat + d.weapon_max) * (1 + atk_pct)

    dot = "dot" in ctx.tags
    add = d.flat_add + g("flat_add", 0.0)
    if target.frontal and not dot:
        add += d.front_atk
    base_avg = a_avg * ctx.coef + ctx.flat + add
    base_max = a_max * ctx.coef + ctx.flat + add
    if not dot and target.defense > 0:
        # penetration is already credited through flat_add (+Pen/10)
        cut = target.defense * PEN_FLAT
        base_avg = max(1.0, base_avg - cut)
        base_max = max(1.0, base_max - cut)

    boost_add = d.amp + g("amp", 0.0)
    if ctx.element == "fire":
        boost_add += g("amp_fire", 0.0)
    boost = max(0.1, 1.0 + boost_add - target.tolerance)
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

    weapon = 1.0 + WEAPON_AMP_EFF * max(d.weapon_amp + g("weapon_amp", 0.0) - target.weapon_tol, 0.0)
    if "crit" in ctx.tags:
        p_c = 1.0
    else:
        p_c = crit_chance(d.crit_stat + g("crit", 0.0), target.crit_resist)
    crit_dmg = d.crit_dmg + g("crit_dmg", 0.0) - target.crit_dmg_tol
    p_d = min(1.0, max(0.0, d.double + g("double", 0.0) - target.double_resist))
    p_p = min(1.0, max(0.0, d.perfect + g("perfect", 0.0)))
    p_m = 1.0 if "multi" in ctx.tags else min(1.0, d.multihit + g("multihit", 0.0))

    roll = (1 - p_d) * ((1 - p_p) * base_avg + p_p * base_max) + p_d * 2.0 * base_avg
    crit = roll * (1 + p_c * (CRIT_BASE + crit_dmg)) + p_c * d.crit_atk * (1.0 + CRIT_BASE + crit_dmg)
    parry = 1.0
    if target.parry > 0 and "crit" not in ctx.tags and "noparry" not in ctx.tags:
        parry = 1.0 - 0.5 * target.parry
    return crit * boost * elem * vuln * weapon * (1 + p_m * MULTIHIT_BONUS) * parry * ctx.mult
