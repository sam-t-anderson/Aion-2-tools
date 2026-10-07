"""Assemble a character :class:`Stats` block from gear, titles, deity stats, Daevanion..."""
from __future__ import annotations

import re
from pathlib import Path

from .stats import Stats

DATA = Path(__file__).resolve().parent.parent / "data"

#: metabot / in-game stat labels -> (Stats field, scale).  Percent labels are
#: converted to fractions.  Defensive stats map to None (ignored for DPS).
LABEL_MAP = {
    "Attack": ("attack", 1), "Attack Bonus": ("attack", 1),
    "Critical Hit": ("crit", 1), "Critical Attack": ("crit_atk", 1),
    "Critical Damage Boost": ("crit_dmg", 0.01),
    "Accuracy": ("accuracy", 1), "Accuracy Bonus": ("accuracy", 1),
    "Damage Boost": ("amp_all", 0.01), "PvE Damage Boost": ("amp_pve", 0.01),
    "Boss Damage Boost": ("amp_boss", 0.01), "Weapon Damage Boost": ("weapon_amp", 0.01),
    "Perfect Chance": ("perfect", 0.01), "Double Chance": ("double", 0.01),
    "Multi-hit Chance": ("multihit", 0.01), "Combat Speed": ("combat_speed", 0.01),
    "Cooldown Reduction": ("cdr", 0.01), "Penetration": ("pen", 1),
    "PvP Damage Boost": ("amp_pvp", 0.01), "PvP Attack": ("pvp_atk", 1),
    "PvE Attack": ("pve_atk", 1), "Boss Attack": ("boss_atk", 1),
    "Front Attack": ("front_atk", 1), "Back Attack": ("back_atk", 1),
    "Might": ("might", 1), "Precision": ("precision", 1), "MP": ("mp_max", 1),
    "Attack increase": ("attack_pct", 0.01), "Natural MP Regen": ("mp_regen", 1 / 3),
    "Combat Natural MP Regen": ("mp_regen", 1 / 3),
}

#: Daevanion node stat keys (global client) -> (Stats field, scale)
DAEV_MAP = {
    "FixingDamage": ("attack", 1), "Critical": ("crit", 1),
    "CombatSpeed": ("combat_speed", 1e-4), "CoolTimeDecrease": ("cdr", 1e-4),
    "AmplifyAllDamage": ("amp_all", 1e-4), "AmplifyCriticalDamage": ("crit_dmg", 1e-4),
    "AdditionalHitRate": ("multihit", 1e-4), "MPMax": ("mp_max", 1),
}

#: deity stat display names -> Stats field
DEITY_MAP = {"Destruction [Zikel]": "destruction", "Death [Triniel]": "death",
             "Wisdom [Lumiel]": "wisdom", "Justice [Nezekan]": "justice",
             "Time [Siel]": "time", "Illusion [Kaisinel]": "illusion",
             "Freedom [Vaizel]": "freedom"}
PRIMARY_MAP = {"Might": "might", "Precision": "precision"}


def parse_bonus_text(text: str) -> dict:
    """'PvE Damage Boost +3%, Penetration +210' -> {'amp_pve': 0.03, 'pen': 210}"""
    out: dict[str, float] = {}
    for part in re.split(r",\s*", text or ""):
        m = re.match(r"(.+?)\s*\+([\d.]+)(%?)$", part.strip())
        if not m:
            continue
        label, val, pct = m.group(1).strip(), float(m.group(2)), m.group(3)
        if label not in LABEL_MAP:
            continue
        field, scale = LABEL_MAP[label]
        if pct and scale == 1:
            continue
        out[field] = out.get(field, 0.0) + val * scale
    return out


def daevanion_to_stats(raw: dict) -> dict:
    out: dict[str, float] = {}
    for k, v in raw.items():
        if k in DAEV_MAP:
            f, sc = DAEV_MAP[k]
            out[f] = out.get(f, 0.0) + v * sc
    return out


def load_loadout(name: str) -> dict:
    from ..paths import read_json
    return read_json("global", "loadouts", f"{name}.json")


def loadout_stats(loadout: dict) -> Stats:
    """Sum every component of a loadout JSON into a Stats block."""
    s = Stats(level=loadout.get("level", 45))
    for comp in loadout.get("components", []):
        stats = comp.get("stats", {})
        s.add({k: v for k, v in stats.items() if k != "skill_bonus"})
        if "skill_bonus" in stats:
            s.add({"skill_bonus": {int(k): v for k, v in stats["skill_bonus"].items()}})
    return s
