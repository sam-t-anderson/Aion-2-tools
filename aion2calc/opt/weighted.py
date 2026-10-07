"""Direct multi-scenario refinement of anonymous common-loadout candidates."""
from __future__ import annotations

import math

from ..run import prepare
from .pipeline import Optimizer
from .rotation import Evaluator, optimize_rotation
from .statweights import stat_weights


class WeightedOptimizer(Optimizer):
    def __init__(self, cls, scenarios, **kwargs):
        self.scenarios = tuple(scenarios)
        if (not self.scenarios or any(not math.isfinite(w) or w <= 0 for w, _ in self.scenarios)
                or not math.isclose(sum(w for w, _ in self.scenarios), 1.0)):
            raise ValueError("Scenario weights must be positive and sum to one")
        primary = self.scenarios[0][1]
        if any(s.target.is_player != primary.target.is_player or s.loadout != primary.loadout
               for _, s in self.scenarios):
            raise ValueError("Weighted scenarios must share a combat mode and loadout")
        super().__init__(cls, primary, **kwargs)

    def _evaluator(self, build):
        cases = []
        for weight, scenario in self.scenarios:
            _, _, kit, stats = prepare(build, scenario)
            cases.append((weight, Evaluator(stats.derived(), kit, scenario.target, scenario.config)))
        cache = {}

        def score(policy):
            key = tuple(policy)
            if key not in cache:
                values = [(weight, evaluator(policy)) for weight, evaluator in cases]
                # The timeline remains the primary scenario's; the scalar is
                # the exact weighted objective at each scenario's full duration.
                cache[key] = (sum(weight * value[0] for weight, value in values), values[0][1][1])
            return cache[key]

        return score

    def evaluate(self, build, policy, cfg=None, filler=None):
        _, _, kit, _ = prepare(build, self.scenario)
        return self._evaluator(build)(self._fit_policy(policy, kit))[0]

    def optimize_rotation(self, build, policy=None, restarts=2):
        _, _, kit, stats = prepare(build, self.scenario)
        start = None
        if policy:
            start = [entry for entry in self._fit_policy(policy, kit)
                     if isinstance(entry, tuple) or not kit.actions[entry].is_filler]
        result = optimize_rotation(stats.derived(), kit, self.scenario.target, self.scenario.config,
                                   start=start, restarts=restarts, evaluator=self._evaluator(build))
        self._rotation_keys = set(kit.actions)
        return result.policy, result.dps, result.result

    def _stat_weights(self, build, policy, *, final=False):
        # These finite differences are a separable proposal for the board solver.
        # Timing slopes retain the existing per-scenario rotation approximation.
        # The resulting allocation is accepted only by the full weighted score.
        combined = {}
        for weight, scenario in self.scenarios:
            _, _, kit, stats = prepare(build, scenario)
            rows = stat_weights(stats, kit, policy, scenario.target, scenario.config,
                                progress=None if final else self.log)
            for row in rows:
                item = combined.setdefault(row["stat"], {**row, "dps_gain": 0.0, "per_unit": 0.0})
                item["dps_gain"] += weight * row["dps_gain"]
                item["per_unit"] += weight * row["per_unit"]
        base = self.evaluate(build, policy)
        attack = combined.get("attack", {}).get("per_unit", 0.0)
        for row in combined.values():
            row["pct"] = 100 * row["dps_gain"] / base if base > 0 else 0.0
            row["attack_equiv"] = row["dps_gain"] / attack if attack > 0 else None
        return sorted(combined.values(), key=lambda row: -row["dps_gain"])
