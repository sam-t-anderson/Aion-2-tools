"""Healing amounts, measured from the log server's uploads (0.2.386).

**A heal restores its tooltip's value at the skill's level times (1 + Attack / 2,000).** Each healer's recorded
heals were set against the tooltip's mid value at the healer's own skill level (the official profile's, which the
uploads carry), with the healer's Attack as the app's import of the same profile computes it (Genus Insight, pets
and buffs are not on the profile):

* the ratio is the same for two heals of one healer (Radiant Recovery's over Healing Light's 0.91-1.12 for 30
  Clerics), so a heal scales by a multiplier of the healer, not by an added value;
* that multiplier grows with Attack: 1 + Attack / 1,914 over 68 Cleric rows (Healing Light, Radiant Recovery,
  Absolution; recorded over predicted 0.96-1.06 between the quartiles), 1 + Attack / 1,993 over 38 Chanter rows
  (Recuperation). :data:`HEAL_ATTACK_SCALE` is the round 2,000 both sit on.

The game reports what a heal restored, at most the HP its target was missing, so a heal over time's recorded ticks
sit below the formula (Light of Regeneration's median at 0.55-0.70 of it) while their tenth largest match it
(6,843 recorded against 6,440 predicted, 8,431 against 8,274). What healers do in a boss fight is therefore kept as
recorded: :data:`HEAL_RATES` holds, per heal skill, the recorded healing over the healer's predicted full value of one
application, in applications a minute; a build's modelled healing is those rates times its own values (its skill
levels and its Attack). Pooled over 335 Cleric-minutes and 334 Chanter-minutes of boss fights in 20 recordings (6
November 2026; a fight several party members uploaded counts once).

Only the healers are modelled: the other classes' heals are their potions and a few self-heals, and the simulator
spreads a healer's heal presses over the rotation's time without simulating them (``sim.engine.Action.heal``).
"""
from __future__ import annotations

#: A heal's multiplier is 1 + Attack / HEAL_ATTACK_SCALE (fitted 1,914 for Clerics, 1,993 for Chanters).
HEAL_ATTACK_SCALE = 2000.0

#: Per class, per heal skill: (full-value applications a minute in a boss fight, the share that heals the caster).
#: The caster's share is the tooltip's: Healing Light heals the caster and the lowest-HP member (half), the party
#: heals the caster and the party within 40 m (the recordings reach five players a cast, the Chanter's six).
HEAL_RATES = {
    "cleric": {
        17090000: (59.1, 0.20),       # Light of Regeneration: a tick every 2 s for 30 s on everyone in range
        17800000: (36.4, 0.20),       # Radiant Benediction (passive): a heal on landing an attack, once in 5 s
        17120000: (15.2, 0.20),       # Radiant Recovery
        17100000: (11.5, 0.50),       # Healing Light: the caster and the party member with the lowest HP
        17160000: (32.3, 0.20),       # Benevolence (stigma): a tick every 2 s for 20 s, when slotted (4 healers)
        17290000: (1.0, 0.20),        # Absolution (stigma), when slotted (3 healers)
    },
    "chanter": {
        18120000: (32.0, 1 / 6),      # Recuperation: a heal, then a tick every 2 s for 8 s
    },
}

NOTE = ("Healing is modelled for the healers: each heal restores its tooltip's value at the skill's level times "
        "(1 + Attack / 2,000), measured from recorded heals (Clerics 1 + Attack / 1,914, Chanters 1 + Attack / 1,993). "
        "How often a healer heals and how much of it lands on missing HP are the recorded healers' in boss fights; a "
        "different party, a different fight or more damage taken change both.")


def tooltip_value(cd, sid: int, level: int) -> float | None:
    """The mid value of one application of a heal at ``level``: an instant heal's range, a tick of a heal over time,
    or for Recuperation the heal and its four ticks averaged over the five."""
    try:
        v = cd.vals(sid, level)
    except KeyError:
        return None
    if not v:
        return None
    try:
        if sid == 17090000:                                   # [lo, hi, tick, duration]
            return (float(v[0]) + float(v[1])) / 2
        if sid == 17160000:                                   # [duration, [lo, %], [hi, %], tick]
            return (float(v[1][0]) + float(v[2][0])) / 2
        if sid == 18120000:                                   # [[lo, %], [hi, %], debuffs, tick value, tick, duration]
            ticks = round(float(v[5]["ms"]) / float(v[4]["ms"]))
            return ((float(v[0][0]) + float(v[1][0])) / 2 + ticks * float(v[3])) / (1 + ticks)
        return (float(v[0][0]) + float(v[1][0])) / 2           # [[lo, %], [hi, %], ...]
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def heal_multiplier(derived) -> float:
    return 1.0 + max(0.0, derived.attack()) / HEAL_ATTACK_SCALE


def modelled_healing(cls: str, build, cd, derived) -> dict | None:
    """A healer build's healing a minute in a boss fight: per heal skill its value at the build's level times the
    Attack multiplier, at the recorded healers' rate; ``self_per_minute`` is the part that heals the caster. None for
    a class with no modelled heals."""
    rates = HEAL_RATES.get(cls)
    if not rates:
        return None
    levels = build.effective_levels(cd)
    mult = heal_multiplier(derived)
    rows = []
    for sid, (per_min, caster) in rates.items():
        level = levels.get(sid, 0)
        skill = cd.skills.get(sid) or {}
        if level <= 0 or (skill.get("kind") == "stigma" and sid not in getattr(build, "stigmas", {})):
            continue
        value = tooltip_value(cd, sid, level)
        if not value:
            continue
        amount = value * mult
        rows.append({"skill_id": sid, "skill": skill.get("name") or str(sid), "level": level,
                     "per_application": amount, "applications_per_minute": per_min,
                     "per_minute": amount * per_min, "self_per_minute": amount * per_min * caster})
    total = sum(r["per_minute"] for r in rows)
    for r in rows:
        r["share"] = r["per_minute"] / total if total > 0 else 0.0
    return {"per_minute": total, "hps": total / 60.0, "self_per_minute": sum(r["self_per_minute"] for r in rows),
            "multiplier": mult, "by_skill": sorted(rows, key=lambda r: -r["per_minute"]), "note": NOTE}


def heal_time_share(cls: str) -> float:
    """The share of a fight a healer's heal presses take, at the latency-free press time: the kit's recorded presses
    a minute at its measured press time (Cleric 4.6 at 0.45 s, Chanter 1.2 at 0.56 s; ``kit.cleric`` and
    ``kit.chanter`` charge the same in a boss fight). 0 for a class with no modelled heals."""
    if cls not in HEAL_RATES:
        return 0.0
    import importlib
    mod = importlib.import_module(f"aion2calc.kit.{cls}")
    per_min = float(mod.ASSUME.get("heals_per_minute", 0.0))
    return min(0.5, per_min * float(mod.TIMING.get("heal", 0.0)) / 60.0)
