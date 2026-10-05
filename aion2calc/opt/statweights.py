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


#: Stats that move the timeline.  A priority list tuned to exact timings can lose
#: DPS when they shift by a few percent (an alignment artifact, not a real loss),
#: so each is measured as one slope with the rotation re-optimized on both sides
#: of a wide (+-6%) step; deity stats that feed them reuse that slope.
TIMING_FIELDS = {"combat_speed": 0.06, "cdr": 0.06}
DEITY_OF = {"time": ("combat_speed", 0.001), "illusion": ("cdr", 0.001)}

_CTX: dict = {}


def _reopt_worker(job):
    from .rotation import optimize_rotation
    stats, kit, policy, target, config = _CTX["sw"]
    field, delta = job
    s2 = stats.copy()
    s2.add({field: delta})
    key = lambda e: e[0] if isinstance(e, tuple) else e  # noqa: E731
    start = [e for e in policy if isinstance(e, tuple) or not kit.actions[key(e)].is_filler]
    r = optimize_rotation(s2.derived(), kit, target, config, start=start, restarts=0, max_passes=2)
    return job, r.dps


def stat_weights(stats, kit, policy, target, config, steps=STAT_STEPS, reopt_timing: bool = True,
                 progress=None) -> list[dict]:
    policy = [e for e in policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    def dps(st):
        sim = Sim(st.derived(), kit.actions, materialize(policy), target, config,
                  hooks=kit.hooks, cond_mods=kit.cond_mods)
        return sim.run().dps

    reopt_gain = {}
    if reopt_timing:
        from .pipeline import _pmap
        _CTX["sw"] = (stats, kit, policy, target, config)
        jobs = [(f, sgn * h) for f, h in TIMING_FIELDS.items() for sgn in (1, -1)]
        res = dict(_pmap(
            _reopt_worker, jobs, ctx={"sw": _CTX["sw"]},
            progress=(lambda done, total: progress(f"stat weights: timing simulations {done}/{total}")
                      if progress else None),
            fallback=progress,
        ))
        slope = {f: (res[(f, h)] - res[(f, -h)]) / (2 * h) for f, h in TIMING_FIELDS.items()}
        for f, st, _ in steps:
            if f in slope:
                reopt_gain[f] = slope[f] * st
            elif f in DEITY_OF:
                base_f, scale = DEITY_OF[f]
                reopt_gain[f] = slope[base_f] * scale * st

    base = dps(stats)
    atk = stats.copy()
    atk.add({"attack": 30})
    per_attack = (dps(atk) - base) / 30
    out = []
    if progress:
        progress("stat weights: evaluating finite differences")
    report_every = max(1, len(steps) // 10)
    for index, (field, step, label) in enumerate(steps, 1):
        s2 = stats.copy()
        if field == "weapon_max":
            s2.add({"weapon_max": step, "weapon_min": step})
        else:
            s2.add({field: step})
        gain = reopt_gain[field] if field in reopt_gain else dps(s2) - base
        out.append({"stat": field, "step": step, "label": label, "dps_gain": gain,
                    "pct": 100 * gain / base, "per_unit": gain / step,
                    "attack_equiv": gain / per_attack if per_attack > 0 else None})
        if progress and (index % report_every == 0 or index == len(steps)):
            progress(f"stat weights: {index}/{len(steps)} stats")
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
