"""Character stat block and the conversions from raw stats to combat rates.

Everything that turns a stat into a probability or a multiplier lives here so
the assumptions are in one place.  Sources for each conversion are listed in
``docs/methodology.md``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields

# --- conversion constants -------------------------------------------------

#: Primary and deity stats give +0.1% per point to each of their effects in the
#: global client (metabot "Stats explained", read from the client stat table).
STAT_POINT_PCT = 0.001

#: Community-measured crit chance curve (Taiwanese Bahamut tests, KR Season 1,
#: wooden dummy; 1048 -> 56%, 1220 -> 80%, 1326 -> 90%).  Capped at 80% for
#: normal skills as the community DPS calculators do.
CRIT_A, CRIT_K, CRIT_X0, CRIT_CAP = 1.0461, 0.0060, 1024.52, 0.80

#: Base crit multiplier (x1.5 PvE); Critical Damage Boost adds linearly.
CRIT_BASE = 0.5

#: Each multi-hit proc adds up to 4 extra hits worth 10% each; community
#: calculators use +12.5% expected extra damage per proc.
MULTIHIT_BONUS = 0.125

#: Weapon Damage Boost is applied at 66% efficiency (community calculator).
WEAPON_AMP_EFF = 0.66

#: Penetration adds ~1/10 of its value as flat damage (TW tests).
PEN_FLAT = 0.1

#: Combat Speed / Cooldown Reduction caps.
CDR_CAP = 0.60


@dataclass
class Stats:
    """Additive stat totals.  Percent stats are stored as fractions (0.05 = 5%)."""

    level: int = 45
    # attack
    weapon_min: float = 0.0
    weapon_max: float = 0.0
    attack: float = 0.0            # flat "Attack" / "Attack Bonus" from every source
    attack_pct: float = 0.0        # "Attack increase" (Might, Destruction, rolls, buffs)
    # crit / hit types
    crit: float = 0.0              # Critical Hit stat points
    crit_pct: float = 0.0          # "Critical Hit increase" (Precision, Death)
    crit_dmg: float = 0.0          # Critical Damage Boost
    crit_atk: float = 0.0          # Critical Attack (flat, only on crit)
    double: float = 0.0            # Double (Smite) chance
    perfect: float = 0.0           # Perfect chance
    multihit: float = 0.0          # Multi-hit chance
    # damage boost groups
    amp_all: float = 0.0           # Damage Boost
    amp_pve: float = 0.0           # PvE Damage Boost
    amp_boss: float = 0.0          # Boss Damage Boost
    weapon_amp: float = 0.0        # Weapon Damage Boost
    front_amp: float = 0.0
    back_amp: float = 0.0
    fire_amp: float = 0.0          # Fire Attack % (Element Enhancement)
    water_amp: float = 0.0
    # flat damage adds
    pve_atk: float = 0.0           # PvE Attack (flat)
    boss_atk: float = 0.0          # Boss Attack (flat)
    front_atk: float = 0.0         # Front Attack (flat, frontal hits)
    back_atk: float = 0.0
    pen: float = 0.0               # Penetration
    # tempo / resources
    combat_speed: float = 0.0
    cdr: float = 0.0
    accuracy: float = 0.0
    mp_max: float = 0.0
    mp_max_pct: float = 0.0
    mp_regen: float = 0.0          # natural MP regen per second
    mp_cost_red: float = 0.0       # Wisdom: MP consumption reduction
    # deity / primary points (converted in ``derived``)
    might: float = 0.0
    precision: float = 0.0
    destruction: float = 0.0
    death: float = 0.0
    wisdom: float = 0.0
    justice: float = 0.0
    time: float = 0.0
    illusion: float = 0.0
    freedom: float = 0.0
    # skill level bonuses from gear/arcana: {skill_id: levels}
    skill_bonus: dict = field(default_factory=dict)

    def add(self, other: "Stats | dict") -> "Stats":
        items = other.items() if isinstance(other, dict) else (
            (f.name, getattr(other, f.name)) for f in fields(other))
        for k, v in items:
            if k == "level":
                continue
            if k == "skill_bonus":
                for sid, lv in (v or {}).items():
                    self.skill_bonus[sid] = self.skill_bonus.get(sid, 0) + lv
                continue
            if not hasattr(self, k):
                raise KeyError(f"unknown stat {k!r}")
            setattr(self, k, getattr(self, k) + v)
        return self

    def copy(self) -> "Stats":
        s = Stats(**{f.name: getattr(self, f.name) for f in fields(self) if f.name != "skill_bonus"})
        s.skill_bonus = dict(self.skill_bonus)
        return s

    # ------------------------------------------------------------------
    def derived(self) -> "Derived":
        """Fold primary/deity points into the stats they feed."""
        p = STAT_POINT_PCT
        atk_pct = self.attack_pct + p * (self.might + self.destruction)
        crit_stat = self.crit * (1 + self.crit_pct + p * (self.precision + self.death))
        return Derived(
            atk_flat=self.attack, atk_pct=atk_pct,
            weapon_min=self.weapon_min, weapon_max=self.weapon_max,
            crit_stat=crit_stat, crit_dmg=self.crit_dmg, crit_atk=self.crit_atk,
            double=self.double + p * self.wisdom,
            perfect=self.perfect + p * self.justice,
            multihit=self.multihit,
            amp=self.amp_all + self.amp_pve + self.amp_boss,
            weapon_amp=self.weapon_amp, front_amp=self.front_amp,
            fire_amp=self.fire_amp, water_amp=self.water_amp,
            flat_add=self.pve_atk + self.boss_atk + PEN_FLAT * self.pen,
            front_atk=self.front_atk,
            combat_speed=self.combat_speed + p * self.time,
            cdr=min(CDR_CAP, self.cdr + p * self.illusion),
            accuracy=self.accuracy * (1 + p * self.freedom),
            mp_max=self.mp_max * (1 + self.mp_max_pct),
            mp_regen=self.mp_regen,
            mp_cost_red=self.mp_cost_red + p * self.wisdom,
        )


@dataclass
class Derived:
    atk_flat: float
    atk_pct: float
    weapon_min: float
    weapon_max: float
    crit_stat: float
    crit_dmg: float
    crit_atk: float
    double: float
    perfect: float
    multihit: float
    amp: float
    weapon_amp: float
    front_amp: float
    fire_amp: float
    water_amp: float
    flat_add: float
    front_atk: float
    combat_speed: float
    cdr: float
    accuracy: float
    mp_max: float
    mp_regen: float
    mp_cost_red: float

    def attack(self, perfect: bool = False, extra_pct: float = 0.0) -> float:
        w = self.weapon_max if perfect else 0.5 * (self.weapon_min + self.weapon_max)
        return (self.atk_flat + w) * (1 + self.atk_pct + extra_pct)


def set_crit_midpoint(x0: float) -> None:
    """Shift the crit curve (Crit value with ~52% chance); 1024.52 is the measured fit."""
    global CRIT_X0
    CRIT_X0 = float(x0)


def crit_chance(crit_stat: float, target_crit_resist: float = 0.0) -> float:
    eff = max(0.0, crit_stat - target_crit_resist)
    p = CRIT_A / (1 + math.exp(-CRIT_K * (eff - CRIT_X0)))
    return max(0.0, min(CRIT_CAP, p))
