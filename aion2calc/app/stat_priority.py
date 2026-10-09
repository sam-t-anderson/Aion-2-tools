"""Cached display-only upgrade gains for presets missing report weights."""
from __future__ import annotations
from functools import lru_cache
import json

def for_summary(summary):
    if summary.get("weights"):
        return summary["weights"]
    payload = {k: summary.get(k) for k in ("class", "scenario", "scoring_policy", "build", "loadout", "loadout_snapshot", "budgets", "daevanion_budget", "policy")}
    return _calculate(json.dumps(payload, sort_keys=True, separators=(",", ":")))

@lru_cache(maxsize=24)
def _calculate(encoded):
    from .. import learn
    from ..report import build_from_summary
    from ..run import prepare
    from ..scenarios import SCENARIOS
    from ..opt.statweights import stat_weights
    summary = json.loads(encoded)
    build, policy = build_from_summary(summary)
    scenarios = (summary.get("scoring_policy") or {}).get("weights") or {summary.get("scenario") or "boss": 1.0}
    combined, base = {}, 0.0
    with learn.uncalibrated():
        for name, weight in scenarios.items():
            scenario = SCENARIOS[name](summary.get("loadout_snapshot") or summary.get("loadout"))
            _, _, kit, stats = prepare(build, scenario)
            rows = stat_weights(stats, kit, policy, scenario.target, scenario.config, reopt_timing=False)
            if rows:
                # pct is gain/base, so recover the common denominator from a nonzero row.
                reference = next((r for r in rows if abs(r["pct"]) > 1e-12), None)
                if reference:
                    base += weight*100*reference["dps_gain"]/reference["pct"]
            for row in rows:
                target = combined.setdefault(row["stat"], {**row, "dps_gain":0.0, "per_unit":0.0})
                target["dps_gain"] += weight*row["dps_gain"]
                target["per_unit"] += weight*row["per_unit"]
    for row in combined.values():
        row["pct"] = 100*row["dps_gain"]/base if base > 0 else 0.0
        row["attack_equiv"] = None
    return sorted(combined.values(), key=lambda row: -row["dps_gain"])
