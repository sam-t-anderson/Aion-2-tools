"""Marginal DPS value of each stat (finite differences on the full simulation)."""
from __future__ import annotations

from ..sim.engine import Sim
from .rotation import materialize

#: (field, step, label) — step sizes chosen to be a realistic single upgrade.
STAT_STEPS = [
    ("attack", 30, "Attack +30"),
    ("weapon_max", 30, "Weapon max attack +30 (min too)"),
    ("crit", 50, "Critical Hit +50"),
    ("crit_dmg", 0.03, "Critical Damage Boost +3%"),
    ("double", 0.02, "Double (Smite) chance +2%"),
    ("perfect", 0.03, "Perfect chance +3%"),
    ("multihit", 0.03, "Multi-hit chance +3%"),
    ("amp_pve", 0.03, "PvE / Damage Boost +3%"),
    ("weapon_amp", 0.03, "Weapon Damage Boost +3%"),
    ("combat_speed", 0.03, "Combat Speed +3%"),
    ("cdr", 0.03, "Cooldown Reduction +3%"),
    ("pen", 300, "Penetration +300"),
    ("pve_atk", 30, "PvE Attack +30"),
    ("crit_atk", 50, "Critical Attack +50"),
    ("mp_max", 300, "MP +300"),
    ("might", 10, "Might +10 (Attack +1%)"),
    ("destruction", 10, "Destruction +10 (Attack +1%)"),
    ("death", 10, "Death +10 (Crit +1%)"),
    ("wisdom", 10, "Wisdom +10 (Double +1%)"),
    ("justice", 10, "Justice +10 (Perfect +1%)"),
    ("time", 10, "Time +10 (Combat Speed +1%)"),
    ("illusion", 10, "Illusion +10 (Cooldown -1%)"),
]


def stat_weights(stats, kit, policy, target, config, steps=STAT_STEPS) -> list[dict]:
    def dps(st):
        sim = Sim(st.derived(), kit.actions, materialize(policy), target, config,
                  hooks=kit.hooks, cond_mods=kit.cond_mods)
        return sim.run().dps

    base = dps(stats)
    atk = stats.copy()
    atk.add({"attack": 30})
    per_attack = (dps(atk) - base) / 30
    out = []
    for field, step, label in steps:
        s2 = stats.copy()
        if field == "weapon_max":
            s2.add({"weapon_max": step, "weapon_min": step})
        else:
            s2.add({field: step})
        gain = dps(s2) - base
        out.append({"stat": field, "step": step, "label": label, "dps_gain": gain,
                    "pct": 100 * gain / base, "per_unit": gain / step,
                    "attack_equiv": gain / per_attack if per_attack > 0 else None})
    out.sort(key=lambda r: -r["dps_gain"])
    return out


def node_values(cd, weights: list[dict]) -> dict[int, float]:
    """DPS value of each Daevanion stat node from the stat weights."""
    from ..model.character import DAEV_MAP
    per_unit = {w["stat"]: w["per_unit"] for w in weights}
    per_unit.setdefault("amp_all", per_unit.get("amp_pve", 0.0))
    out = {}
    for nid, (b, n) in cd.node_index.items():
        v = 0.0
        for st in n.get("stats", []):
            if st["stat"] in DAEV_MAP:
                field, sc = DAEV_MAP[st["stat"]]
                v += per_unit.get(field, 0.0) * st["value"] * sc
        if v:
            out[nid] = v
    return out
