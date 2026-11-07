"""Every class's defensive skills in the World PvP survival model (0.2.386), read from their tooltips at the
build's levels (``data/global/classes/<class>.json``):

* **Always on.** Passives that raise HP, Max HP, Defense, Critical Hit Resist, PvP Damage Tolerance, Block or
  Evasion (Enhance Health, Survival Stance, Immortal Veil, Robe of Cold, ...) and the auras the Chanter and the
  Cleric leave on (Undefeated Mantra, Light of Protection) add to the survival stats ``opt.world`` reads.
* **Timed.** A buff counts for the share of the fight it is up, pressed on cooldown (Second Skin, Arctic Armor,
  Warding Strike's Warding, ...). One that triggers when you are struck, crowd-controlled or below half HP counts
  once a cooldown too: the pressure World PvP assumes keeps you struck, controlled and low, the rule Guarding
  Seal has followed since 0.2.363, so these are the most the effects can give.
* **Shields** count as the HP they absorb, once a cooldown, or on each press that carries them (Doom Shield,
  Poach's specialization, Siphon's and Grapple's stigma options: ``shield_on_press``, counted by the simulation).
  **Immunity** counts as the damage it keeps off, and damage it blocks as a share as that share.
* **Heals** count as the HP they restore: the healers' heals from ``kit.healing``, and every class's own
  (Warding Strike, Blood Absorption, Sprint Mantra, Spirit Communion, Defiance's specialization, the heals at 10 %
  HP) at their tooltip's values; the lifesteal options ("Absorbs N, N% HP") restore N hundredths of a percent of
  maximum HP a press (``lifesteal_share``). The recorded self-heals bear these out (docs/methodology.md "Every
  class's defensives in World PvP").
* **Crowd control.** Status Effect Resist lowers the share of the crowd control aimed at you that lands; Defiance
  breaks it and its Tenacity keeps it off, as the immunity stigmas do.

Heals on Block and on Evasion are listed but not counted: a heal per block or evade needs how often the attackers
hit, which the model does not keep (the Block and Evasion themselves count, ``opt.world``, 0.2.387), and the
Evasion this model can see rarely exceeds an attacker's Accuracy. Options that multiply a passive ("x1.5 [Ironclad
Defense] effect for the duration"), death prevention (Barrier Spell) and damage split to MP (Arctic Armor's Magic
Displacement) are not counted either.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .base import STIGMA_SPEC_LEVELS, Build, ClassData

#: Stats an always-on or timed effect adds to (``model.stats.Stats`` fields; percentages as fractions).
STATS = ("hp", "hp_pct", "defense_pct", "crit_resist", "pvp_tol", "block", "evasion")


@dataclass(frozen=True)
class Effect:
    """One defensive effect of a skill. ``value`` and ``duration`` are an index into the skill's tooltip values
    at the build's level, a constant, or for a heal a (low, high) pair of indexes."""
    sid: int
    what: str                       # a STATS field, "shield", "heal" (a share of Max HP), "heal_hp", "reduce",
                                    # "immune" (damage and crowd control), "resist" (Status Effect Resist), "tenacity"
    value: object = None
    pct: bool = True                # the value is a percentage
    on: str = "use"                 # "always", "use" (pressed on cooldown), "struck", "controlled", "low_hp",
                                    # "hit" (on landing an attack, once its cooldown), "block", "evade"
    duration: object = None         # seconds it lasts once triggered (index or constant)
    cooldown: object = None         # seconds between triggers: an index or a constant; None is the skill's own
    chance: float = 1.0             # its chance to trigger
    option: int | None = None       # the specialization (active skill) or stigma option it needs
    scale: float = 1.0              # a multiplier on the value
    cooldown_cut: tuple = ()        # (option, seconds): an option that shortens the cooldown (Steel Barrier's -15 s)
    label: str = ""


def _defiance(sid: int) -> tuple:
    """Defiance (every class): breaks Stun, Knockdown, Airborne, Grab, Frost and Fear and grants Tenacity (Status
    Effect Immunity) for 5 s, pressed when controlled; its cooldown is 60 s at level 1, a second less a level and
    unaffected by cooldown reduction. Specializations: +2 s Tenacity (12), +25 % PvP Damage Tolerance for the
    Tenacity (16), 20 % HP on use (Lv 8, the Assassin's Storm Slice chain shares that slot)."""
    return (Effect(sid, "tenacity", 0, pct=False, on="controlled", label="Defiance: Tenacity"),
            Effect(sid, "tenacity", 2.0, pct=False, on="controlled", option=sid + 40, label="Defiance: +2 s Tenacity"),
            Effect(sid, "pvp_tol", 25.0, on="controlled", duration=0, option=sid + 50,
                   label="Defiance: PvP Damage Tolerance during Tenacity"),
            Effect(sid, "heal", 20.0, on="controlled", option=sid + 30, label="Defiance: 20 % HP on use"))


def _willpower(sid: int) -> tuple:
    """Survival Willpower (Chanter, Cleric, Gladiator, Templar): Status Effect Resist, and PvP Damage Tolerance for
    5 s when controlled, cooldown 60 s."""
    return (Effect(sid, "resist", 0, on="always", label="Survival Willpower: Status Effect Resist"),
            Effect(sid, "pvp_tol", 2, on="controlled", duration=3, cooldown=6,
                   label="Survival Willpower: PvP Damage Tolerance when controlled"))


def _contract(sid: int) -> tuple:
    """Revitalization Contract (Assassin, Ranger, Sorcerer, Spiritmaster): Status Effect Resist, and an instant
    heal of a share of Max HP at 10 % HP, cooldown 60 s."""
    return (Effect(sid, "resist", 0, on="always", label="Revitalization Contract: Status Effect Resist"),
            Effect(sid, "heal", 3, on="low_hp", cooldown=4, label="Revitalization Contract: heal at 10 % HP"))


#: Per class, the defensive effects of its skills, passives and stigmas.
EFFECTS: dict[str, tuple] = {
    "assassin": (
        Effect(13710000, "hp", 1, pct=False, on="always", label="Heightened Sixth Sense: HP"),
        Effect(13710000, "hp_pct", 2, on="always", label="Heightened Sixth Sense: Max HP"),
        Effect(13710000, "evasion", 0, pct=False, on="always", label="Heightened Sixth Sense: Evasion"),
        Effect(13710000, "heal_hp", (3, 4), pct=False, on="evade", cooldown=5,
               label="Heightened Sixth Sense: heal on Evasion"),
        Effect(13370000, "evasion", 0, pct=False, duration=1, label="Evasion Contract: Evasion"),
        Effect(13370000, "evasion", 100.0, pct=False, duration=1, option=13370040, label="Evasion Contract: +100 Evasion"),
        Effect(13140000, "evasion", 200.0, pct=False, duration=10.0, option=13140030, label="Shadowstep: +200 Evasion"),
        *_contract(13790000), *_defiance(13260000)),
    "chanter": (
        Effect(18710000, "hp", 0, pct=False, on="always", label="Blessing of Life: HP"),
        Effect(18710000, "hp_pct", 1, on="always", label="Blessing of Life: Max HP"),
        Effect(18720000, "block", 0, pct=False, on="always", label="Crossguard: Block"),
        Effect(18720000, "heal_hp", (1, 2), pct=False, on="block", cooldown=3, label="Crossguard: heal on Block"),
        Effect(18750000, "defense_pct", 2, on="always", label="Attack Preparation: Defense"),
        Effect(18730000, "reduce", 4, on="low_hp", duration=3, cooldown=6,
               label="Protection Circle: Noble Protective Shield below half HP"),
        # Divine Barrier: its stacks come from landed attacks, 10 to a barrier; the recordings show 3.5 barriers a
        # minute on the Chanter itself (15.4 a minute per Chanter, 23 % of them on the caster; 151 Chanters)
        Effect(18730000, "shield", 1, on="use", cooldown=60 / 3.5, label="Protection Circle: Divine Barrier"),
        Effect(18190000, "pvp_tol", 1, on="always", label="Undefeated Mantra: PvP Damage Tolerance"),
        Effect(18240000, "shield", 0, label="Impeding Authority: shield"),
        Effect(18160000, "heal_hp", (2, 3), pct=False, on="hit", cooldown=4, chance=0.15,
               label="Sprint Mantra: heal on landing an attack"),
        *_willpower(18790000), *_defiance(18200000)),
    "cleric": (
        Effect(17710000, "hp_pct", 0, on="always", label="Warm Benediction: Max HP"),
        Effect(17720000, "block", 0, pct=False, on="always", label="Empyrean Lords' Benediction: Block"),
        Effect(17720000, "heal_hp", (1, 2), pct=False, on="block", cooldown=3,
               label="Empyrean Lords' Benediction: heal on Block"),
        Effect(17750000, "defense_pct", 0, on="always", label="Immortal Veil: Defense"),
        Effect(17750000, "crit_resist", 1, pct=False, on="always", label="Immortal Veil: Critical Hit Resist"),
        Effect(17410000, "pvp_tol", 1, on="always", label="Light of Protection: PvP Damage Tolerance"),
        Effect(17090000, "pvp_tol", 2.5, duration=3, option=17090050,
               label="Light of Regeneration: PvP Damage Tolerance while healing"),
        Effect(17090000, "defense_pct", 5.0, duration=3, option=17090010, label="Light of Regeneration: Defense while healing"),
        Effect(17420000, "pvp_tol", 1, duration=2, label="Yustiel's Power: PvP Damage Tolerance"),
        Effect(17420000, "pvp_tol", 5.0, duration=2, option=17420040, label="Yustiel's Power: +5 % PvP Damage Tolerance"),
        Effect(17420000, "shield", 10.0, option=17420010, label="Yustiel's Power: shield"),
        Effect(17420000, "block", 100.0, pct=False, duration=2, option=17420020, label="Yustiel's Power: +100 Block"),
        Effect(17420000, "evasion", 100.0, pct=False, duration=2, option=17420020, label="Yustiel's Power: +100 Evasion"),
        Effect(17270000, "immune", 0, pct=False, label="Salvation: immunity"),
        *_willpower(17790000), *_defiance(17240000)),
    "gladiator": (
        Effect(11710000, "hp", 0, pct=False, on="always", label="Survival Stance: HP"),
        Effect(11710000, "hp_pct", 1, on="always", label="Survival Stance: Max HP"),
        Effect(11710000, "pvp_tol", 4, on="always", label="Survival Stance: PvP Damage Tolerance"),
        Effect(11720000, "block", 0, pct=False, on="always", label="Protection Armor: Block"),
        Effect(11720000, "heal_hp", (1, 2), pct=False, on="block", cooldown=3, label="Protection Armor: heal on Block"),
        Effect(11750000, "defense_pct", 2, on="always", label="Attack Preparation: Defense"),
        Effect(11730000, "heal_hp", (1, 2), pct=False, on="hit", cooldown=5, chance=0.5,
               label="Blood Absorption: heal on landing an attack"),
        Effect(11730000, "heal", 3, on="hit", cooldown=5, chance=0.5, label="Blood Absorption: Max HP on landing an attack"),
        Effect(11730000, "heal", 4, on="low_hp", cooldown=6, label="Blood Absorption: heal at half HP"),
        Effect(11190000, "pvp_tol", 10.0, duration=3.0, option=11190040, label="Leaping Slam: PvP Damage Tolerance"),
        Effect(11380000, "immune", 0, pct=False, label="Tenaciousness: immunity"),
        Effect(11380000, "pvp_tol", 2, duration=3, label="Tenaciousness: PvP Damage Tolerance after it"),
        *_willpower(11790000), *_defiance(11260000)),
    "ranger": (
        Effect(14710000, "evasion", 0, pct=False, on="always", label="Vigilant Eye: Evasion"),
        Effect(14710000, "hp_pct", 1, on="always", label="Vigilant Eye: Max HP"),
        Effect(14710000, "heal_hp", (2, 3), pct=False, on="evade", cooldown=4, label="Vigilant Eye: heal on Evasion"),
        Effect(14350000, "pvp_tol", 1, duration=3, label="Mother Nature's Breath: PvP Damage Tolerance"),
        Effect(14350000, "pvp_tol", 10.0, duration=3, option=14350040,
               label="Mother Nature's Breath: +10 % PvP Damage Tolerance"),
        *_contract(14790000), *_defiance(14260000)),
    "sorcerer": (
        Effect(15750000, "defense_pct", 0, on="always", label="Robe of Cold: Defense"),
        Effect(15750000, "crit_resist", 1, pct=False, on="always", label="Robe of Cold: Critical Hit Resist"),
        Effect(15160000, "shield", 0, cooldown_cut=(15160040, 15.0), label="Steel Barrier: shield"),
        Effect(15230000, "pvp_tol", 1, duration=4, label="Arctic Armor: PvP Damage Tolerance"),
        Effect(15230000, "pvp_tol", 10.0, duration=4, option=15230040, label="Arctic Armor: +10 % PvP Damage Tolerance"),
        Effect(15410000, "immune", 0, pct=False, label="Hibernation: immunity"),
        Effect(15410000, "immune", 2.0, pct=False, option=15410030, label="Hibernation: +2 s"),
        *_contract(15790000), *_defiance(15240000)),
    "spiritmaster": (
        Effect(16720000, "defense_pct", 0, on="always", label="Spirit Protection: Defense"),
        Effect(16190000, "pvp_tol", 3, duration=6, label="Enhance: Spirit's Benediction: PvP Damage Tolerance"),
        Effect(16190000, "pvp_tol", 12.5, duration=6, option=16190040,
               label="Enhance: Spirit's Benediction: +12.5 % PvP Damage Tolerance"),
        Effect(16140000, "reduce", 10.0, duration=4, label="Jointstrike: Curse: cursed enemies deal 10 % less"),
        Effect(16770000, "heal_hp", (2, 3), pct=False, on="hit", cooldown=1.0, chance=0.10,
               label="Spirit Communion: heal on landing an attack"),
        Effect(16120000, "heal_hp", (2, 3), pct=False, label="Summon: Wind Spirit: heal"),
        *_contract(16790000), *_defiance(16200000)),
    "templar": (
        Effect(12710000, "hp", 0, pct=False, on="always", label="Enhance Health: HP"),
        Effect(12710000, "hp_pct", 1, on="always", label="Enhance Health: Max HP"),
        Effect(12720000, "block", 0, pct=False, on="always", label="Warding Shield: Block"),
        Effect(12720000, "heal_hp", (1, 2), pct=False, on="block", cooldown=3, label="Warding Shield: heal on Block"),
        Effect(12740000, "defense_pct", 0, on="always", label="Ironclad Defense: Defense"),
        Effect(12800000, "pvp_tol", 2, on="struck", duration=0, cooldown=3, label="Block Pain: PvP Damage Tolerance"),
        Effect(12350000, "pvp_tol", 7, duration=4, cooldown_cut=(12350010, 5.0), label="Warding Strike: Warding"),
        Effect(12350000, "heal_hp", (2, 3), pct=False, cooldown_cut=(12350010, 5.0), label="Warding Strike: heal"),
        Effect(12190000, "pvp_tol", 1, duration=2, label="Second Skin: PvP Damage Tolerance"),
        Effect(12230000, "hp_pct", 0, duration=1, label="Noble Armor: Max HP"),
        Effect(12230000, "defense_pct", 5.0, duration=1, option=12230010, label="Noble Armor: +5 % Defense"),
        Effect(12230000, "heal", 2, label="Noble Armor: heal"),
        Effect(12190000, "pvp_tol", 10.0, duration=2, option=12190040, label="Second Skin: +10 % PvP Damage Tolerance"),
        *_willpower(12790000), *_defiance(12260000)),
}

#: Shields on a damage press, as a share of maximum HP (``Action.absorb``): the sid, the share or its tooltip
#: index, and the option it needs. The simulation counts the presses.
SHIELD_ON_PRESS: dict[str, tuple] = {
    "templar": ((12070000, 4, None),          # Doom Shield: 5 % of Max HP on hit
                (12130000, 10.0, 12130040),   # Poach, level-12 specialization: 10 %
                (12220000, 20.0, 12220020)),  # Grapple, stigma level 10: 20 % for 10 s
    "ranger": ((14120000, 10.0, 14120020),),  # Ambush Kick, stigma level 10: 10 % for 5 s on hit
    "spiritmaster": ((16060000, 30.0, 16060030),),   # Siphon, stigma level 15: 30 % for 30 s
}

#: Heals on Block and on Evasion wait on a verified Block and Evasion formula.
UNCOUNTED = ("block", "evade")


def _seconds(v) -> float | None:
    if isinstance(v, dict) and "ms" in v:
        return float(v["ms"]) / 1000.0
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _number(v) -> float | None:
    if isinstance(v, (list, tuple)) and v and isinstance(v[0], (int, float)):
        return float(v[0])                    # a heal's [flat, %] pair: the flat amount
    if isinstance(v, dict):
        return _seconds(v)
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _read(vals, ref, number=_number):
    """A value from the tooltip: an index into ``vals`` or a constant; a (low, high) pair is the range's middle."""
    if isinstance(ref, tuple):
        lo, hi = (_read(vals, r, number) for r in ref)
        return None if lo is None or hi is None else (lo + hi) / 2
    if isinstance(ref, int) and not isinstance(ref, bool):
        return number(vals[ref]) if vals and 0 <= ref < len(vals) else None
    if isinstance(ref, float):
        return ref
    return None


def _active(eff: Effect, build: Build, cd: ClassData, levels: dict) -> int:
    """The level an effect works at, 0 when the build lacks the skill, its stigma or its option."""
    skill = cd.skills.get(eff.sid)
    if not skill:
        return 0
    level = levels.get(eff.sid, 0)
    if level <= 0 or (skill.get("kind") == "stigma" and eff.sid not in build.stigmas):
        return 0
    if eff.option is not None:
        base = eff.option - eff.option % 10000                 # the option's own skill (Second Skin's on Ironclad)
        idx = (eff.option - base) // 10
        own = cd.skills.get(base) or {}
        if own.get("kind") == "stigma":
            if build.stigmas.get(base, 0) < STIGMA_SPEC_LEVELS[idx - 1]:
                return 0
        else:
            spec = next((s for s in own.get("specs") or () if s["id"] == eff.option), None)
            if (spec is None or eff.option not in set(build.specs.get(base, ()))
                    or spec["unlock"] > levels.get(base, 0)):
                return 0
    return level


@dataclass
class Defensives:
    """What a build's defensive skills give over a fight, for ``opt.world.survival``."""
    stats: dict = field(default_factory=dict)      # added to the survival stats (time-averaged where timed)
    shield_share: float = 0.0                      # shields, in shares of maximum HP over the fight
    heal_share: float = 0.0                        # heals of a share of maximum HP, over the fight
    heal_hp: float = 0.0                           # heals of a flat amount, over the fight
    reduction: float = 0.0                         # share of incoming damage kept off (immunity, blocked shares)
    status_resist: float = 0.0                     # Status Effect Resist (fraction)
    tenacity_s: float = 0.0                        # seconds a fight of crowd-control immunity (Tenacity, immunity)
    breaks: float = 0.0                            # crowd control broken (Defiance) over the fight
    rows: list = field(default_factory=list)       # per effect: what it gives, for display


def _uptime(eff: Effect, duration: float, cooldown: float) -> float:
    if eff.on == "always":
        return 1.0
    if cooldown <= 0:
        return 1.0 if duration > 0 else 0.0
    return min(1.0, duration / cooldown)


def _triggers(fight: float, cooldown: float) -> int:
    """Times an effect pressed (or triggered) on cooldown fires in a fight: once a cooldown window, the first at
    the start (``kit.templar.defensive_absorb_share``'s count)."""
    if fight <= 0:
        return 0
    return max(1, int(math.ceil(fight / max(cooldown, 1.0) - 1e-9)))


def defensives(cls: str, build: Build | None, fight: float, *, casts_per_s: float = 1.0) -> Defensives:
    """The defensive effects a build has over a fight of ``fight`` seconds. ``casts_per_s`` is how often the
    rotation lands an attack (an effect "on landing an attack" fires at most once its cooldown)."""
    out = Defensives()
    effects = EFFECTS.get(cls)
    if build is None or not effects or fight <= 0:
        return out
    cd = ClassData(cls)
    levels = build.effective_levels(cd)
    for eff in effects:
        level = _active(eff, build, cd, levels)
        if not level:
            continue
        try:
            vals = cd.vals(eff.sid, level) or []
        except KeyError:
            continue
        value = _read(vals, eff.value)
        if value is None:
            continue
        value *= eff.scale
        if eff.pct:
            value /= 100.0
        cooldown = _read(vals, eff.cooldown, _seconds) if eff.cooldown is not None else cd.cd(eff.sid, level)
        cooldown = float(cooldown or 0.0)
        if eff.cooldown_cut and _active(Effect(eff.sid, eff.what, option=eff.cooldown_cut[0]), build, cd, levels):
            cooldown = max(0.0, cooldown - eff.cooldown_cut[1])
        dur = (_read(vals, eff.duration, _seconds) or 0.0) if eff.duration is not None else 0.0
        row = {"skill_id": eff.sid, "effect": eff.label, "what": eff.what, "level": level, "value": value,
               "on": eff.on, "cooldown_s": cooldown or None, "counted": eff.on not in UNCOUNTED}
        if eff.on in UNCOUNTED:
            out.rows.append(row)
            continue
        if eff.on == "hit":                    # at most once its cooldown, as often as attacks land
            period = max(cooldown, 1.0 / max(casts_per_s, 1e-6))
            count = eff.chance * fight / period
        else:
            count = _triggers(fight, cooldown) if eff.on != "always" else 0
        if eff.what in STATS:
            up = _uptime(eff, dur, cooldown)
            out.stats[eff.what] = out.stats.get(eff.what, 0.0) + value * up
            row["uptime"] = up
        elif eff.what == "shield":
            out.shield_share += value * count
            row["count"] = count
        elif eff.what == "heal":
            out.heal_share += value * count
            row["count"] = count
        elif eff.what == "heal_hp":
            out.heal_hp += value * count
            row["count"] = count
        elif eff.what == "reduce":
            up = _uptime(eff, dur, cooldown)
            out.reduction = 1 - (1 - out.reduction) * (1 - value * up)
            row["uptime"] = up
        elif eff.what == "immune":
            secs = _seconds(value * 100.0 if eff.pct else value) or 0.0      # immunity: its seconds a trigger
            up = min(1.0, secs / cooldown) if cooldown > 0 else 0.0
            out.reduction = 1 - (1 - out.reduction) * (1 - up)
            out.tenacity_s += secs * count
            row["uptime"] = up
        elif eff.what == "resist":
            out.status_resist += value
        elif eff.what == "tenacity":
            out.tenacity_s += value * 100.0 * count if eff.pct else value * count
            if eff.option is None:
                out.breaks += count
            row["count"] = count
        out.rows.append(row)
    return out


def shield_on_press(cls: str, build: Build, cd: ClassData, sid: int) -> float:
    """The shield one press of ``sid`` grants the caster, as a share of maximum HP (0 when the build lacks it)."""
    levels = None
    best = 0.0
    for skill, ref, option in SHIELD_ON_PRESS.get(cls, ()):
        if skill != sid:
            continue
        if levels is None:
            levels = build.effective_levels(cd)
        eff = Effect(skill, "shield", ref, option=option)
        level = _active(eff, build, cd, levels)
        if not level:
            continue
        value = _read(cd.vals(skill, level) or [], ref)
        if value:
            best += value / 100.0
    return best


_ABSORBS = re.compile(r"[Aa]bsorbs (\d+)")


def lifesteal_share(cls: str, build: Build, cd: ClassData, sid: int) -> float:
    """The HP one press of ``sid`` restores through a chosen "Absorbs N, N% HP" option, as a share of maximum HP:
    N hundredths of a percent. The recorded heals settle the unit: the Rampage and Scattershot options' 500 restore
    5.3-5.4 % of maximum HP (median of each), Quick Slice's and Onslaught's 70 restore 0.7 % (the log server's boss
    fights, 2026-10-13 to 11-07; docs/methodology.md "Every class's defensives in World PvP")."""
    skill = cd.skills.get(sid) or {}
    levels = None
    for sp in skill.get("specs") or ():
        m = _ABSORBS.search(sp.get("text") or "")
        if not m:
            continue
        if levels is None:
            levels = build.effective_levels(cd)
        if _active(Effect(sid, "heal", option=sp["id"]), build, cd, levels):
            return int(m.group(1)) / 10000.0
    return 0.0
