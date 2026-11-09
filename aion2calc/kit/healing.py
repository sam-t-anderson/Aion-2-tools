"""Healing amounts, measured from the log server's uploads (0.2.386; the heals over time re-measured in 0.2.400).

**A heal restores its tooltip's value at the skill's level times (1 + Attack / 2,000).** Each healer's recorded
heals were set against the tooltip's mid value at the healer's own skill level (the official profile's, which the
uploads carry), with the healer's Attack as the app's import of the same profile computes it (Genus Insight, pets
and buffs are not on the profile):

* the ratio is the same for two heals of one healer (Radiant Recovery's over Healing Light's 0.91-1.12 for 30
  Clerics), so a heal scales by a multiplier of the healer, not by an added value;
* that multiplier grows with Attack: 1 + Attack / 1,914 over 68 Cleric rows (Healing Light, Radiant Recovery,
  Absolution; recorded over predicted 0.96-1.06 between the quartiles), 1 + Attack / 1,993 over 38 Chanter rows
  (Recuperation). :data:`HEAL_ATTACK_SCALE` is the round 2,000 both sit on.

What healers do in a boss fight is kept as recorded: :data:`HEAL_RATES` holds, per heal skill, the recorded healing
over the healer's predicted full value of one application, in applications a minute; a build's modelled healing is
those rates times its own values (its skill levels and its Attack). Pooled over the boss fights of 20 recordings (6
November 2026; a fight several party members uploaded counts once).

**Heals over time (0.2.400).** A heal over time holds an HP pool. Light of Regeneration's is the formula's value (its
recorded pools' median at 1.04 of it, over 1,796 pools) and each of its fifteen ticks takes a fifteenth of it. Meters
before 0.2.399 recorded the pool when it was cast and then what was left of it at every tick, the sequence 0.2.386
read as ticks capped by missing HP (a median of 0.55-0.70 of the formula, the tenth largest at it), and the rates
of Light of Regeneration and Recuperation counted it. Each is now 0.2.386's rate times the share of its recorded
healing that its ticks took in the same 20 recordings, the drops from one record of a pool to the next: Light of
Regeneration 10.6 % (59.1 to 6.3 full heals a minute), Recuperation 63.6 % with its instant heals (32.0 to 20.4).
Benevolence's ticks are recorded one by one and the instant heals whole, so their rates stand (docs/methodology.md,
"Heal rates from what the heals over time took").

Only the healers are modelled: the other classes' heals are their potions and a few self-heals, and the simulator
spreads a healer's heal presses over the rotation's time without simulating them (``sim.engine.Action.heal``).
"""
from __future__ import annotations

#: A heal's multiplier is 1 + Attack / HEAL_ATTACK_SCALE (fitted 1,914 for Clerics, 1,993 for Chanters).
HEAL_ATTACK_SCALE = 2000.0

#: Per class, per heal skill: (full-value applications a minute in a boss fight, the share that heals the caster).
#: The caster's share is the tooltip's: Healing Light heals the caster and the lowest-HP member (half), the party
#: heals the caster and the party within 40 m (the recordings reach five players a cast, the Chanter's six). The two
#: heals over time whose records counted what was left of them are 0.2.386's rates times the share of the recorded
#: healing their ticks took (0.2.400).
HEAL_RATES = {
    "cleric": {
        17090000: (6.3, 0.20),        # Light of Regeneration: its whole heal, 15 ticks in 30 s, on everyone in
                                      # range (0.2.386's 59.1 x 10.6 %)
        17800000: (36.4, 0.20),       # Radiant Benediction (passive): a heal on landing an attack, once in 5 s
        17120000: (15.2, 0.20),       # Radiant Recovery
        17100000: (11.5, 0.50),       # Healing Light: the caster and the party member with the lowest HP
        17160000: (32.3, 0.20),       # Benevolence (stigma): a tick every 2 s for 20 s, when slotted (4 healers)
        17290000: (1.0, 0.20),        # Absolution (stigma), when slotted (3 healers)
    },
    "chanter": {
        18120000: (20.4, 1 / 6),      # Recuperation: a heal, then a heal over time ticking every 2 s for 8 s
                                      # (0.2.386's 32.0 x 63.6 %)
    },
}

NOTE = ("Healing is modelled for the healers: each heal restores its tooltip's value at the skill's level times "
        "(1 + Attack / 2,000), measured from recorded heals (Clerics 1 + Attack / 1,914, Chanters 1 + Attack / 1,993). "
        "How often a healer heals is the recorded healers' in boss fights, a heal over time counted by what its ticks "
        "took; a different party, a different fight or more damage taken change it.")


def tooltip_value(cd, sid: int, level: int) -> float | None:
    """The mid value of one application of a heal at ``level``: an instant heal's range; Light of Regeneration's
    whole heal over time (its tooltip's range, which by the records is the pool its fifteen ticks share, not a
    tick); a tick of Benevolence; or for Recuperation 0.2.386's unit, the heal and four times the tooltip's
    over-time value averaged over the five (by the records that value is the whole heal over time: a pool of four
    ticks holds 0.95 of it times the multiplier)."""
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
