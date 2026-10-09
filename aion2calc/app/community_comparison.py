"""A fresh anonymous optimization, never a trimmed personal build."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..canonical_presets import MODES, candidate, evaluate, scoring_policy
from ..paths import home, bundled_model_data
from ..presets import MAX_BYTES


@bundled_model_data
def generate(cls: str, mode: str, progress=None) -> tuple[dict, bool]:
    """Seed from both scenarios, then refine the exact common weighted objective."""
    from ..kit.base import ClassData
    from ..learn import uncalibrated
    from ..model.character import load_loadout
    from ..opt.pipeline import Optimizer
    from ..opt.weighted import WeightedOptimizer
    from ..presets import parse
    from ..opt.rotation import describe
    from ..report import _spec_text
    from ..scenarios import SCENARIOS

    from ..combat.preset_sync import _base, _request
    policy = scoring_policy(cls, mode)
    base = _base()
    if base:
        remote = _request(base, f"/api/v2/presets/{cls}/{mode}/policy")
        selected = remote.get("budgets") if remote.get("version") == 2 else None
        expected = scoring_policy(cls, mode, selected)
        if remote.get("scope") != expected["scope"]:
            different = [key for key in ("model", "version", "class", "mode", "budgets", "loadout_fingerprint", "data_fingerprint", "weights", "durations")
                         if remote.get(key) != expected.get(key)]
            raise ValueError("Community comparison policy differs from this evaluator (" + ", ".join(different or ["scope"]) +
                             "); check client/server releases and their bundled game data")
        policy = expected
    observed_budgets = policy["budgets"] if policy["version"] == 2 else None
    def score(document):
        return evaluate(document, observed_budgets)
    cache = home() / "cache" / "community-comparisons" / (policy["scope"] + ".json")
    try:
        if cache.stat().st_size <= MAX_BYTES:
            summary = json.loads(cache.read_text(encoding="utf-8"))
            if (summary["scoring_policy"]["scope"] == policy["scope"]
                    and summary.get("candidate_generation", {}).get("search_revision") == 2):
                scored = score(candidate(summary, policy))
                scored["candidate_generation"] = summary.get("candidate_generation", {})
                if progress:
                    progress("Reusing the saved common comparison for this scoring scope")
                return scored, True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass

    cd = ClassData(cls)
    lo = load_loadout(policy["loadout"])
    scores = []
    with uncalibrated():
        for index, objective in enumerate(MODES[mode], 1):
            if progress:
                progress(f"Common comparison seed {index}/2: optimizing {objective}; personal gear and constraints are not inputs")
            opt = Optimizer(cls, SCENARIOS[objective](lo), verbose=False, progress=progress,
                            sp_budget=policy["budgets"]["skill"], stigma_points=policy["budgets"]["stigma"],
                            daev_budget=policy["budgets"]["daevanion"])
            result = opt.run(iterations=1)
            build = result.build
            summary = {"class": cls, "scenario": objective, "policy": describe(result.policy),
                       "build": {"sp": {cd.skills[k]["name"]: v for k, v in build.sp.items()},
                                 "stigmas": {cd.skills[k]["name"]: v for k, v in build.stigmas.items()},
                                 "specs": {cd.skills[k]["name"]: [_spec_text(cd, k, x) for x in v]
                                           for k, v in build.specs.items()},
                                 "daevanion_nodes": sorted(build.daevanion)}}
            scored = score(candidate(summary, policy))
            scored["candidate_generation"] = {"objective": objective, "iterations": 1, "calibration": "disabled"}
            scores.append(scored)
        seed = max(scores, key=lambda item: item["score"])
        primary = MODES[mode][0]
        document = candidate(seed, policy)
        build, rotation = parse({"format": "a2preset", "version": 1, "class": cls,
                                 "build": document["build"]}, scenario_name=primary, loadout_snapshot=lo, budgets=policy["budgets"])
        if progress:
            progress("Common comparison refinement: optimizing the weighted objective across both scenarios")
        scenarios = [(policy["weights"][name], SCENARIOS[name](lo, duration=policy["durations"][name])) for name in MODES[mode]]
        opt = WeightedOptimizer(cls, scenarios, verbose=False, progress=progress,
                                sp_budget=policy["budgets"]["skill"], stigma_points=policy["budgets"]["stigma"],
                                daev_budget=policy["budgets"]["daevanion"])
        result = opt.run(iterations=1, initial_build=build, initial_policy=rotation)
        refined = {"class": cls, "scenario": primary, "policy": describe(result.policy),
                   "build": {"sp": {cd.skills[k]["name"]: v for k, v in result.build.sp.items()},
                             "stigmas": {cd.skills[k]["name"]: v for k, v in result.build.stigmas.items()},
                             "specs": {cd.skills[k]["name"]: [_spec_text(cd, k, x) for x in v]
                                       for k, v in result.build.specs.items()},
                             "daevanion_nodes": sorted(result.build.daevanion)}}
        scored = score(candidate(refined, policy))
        scored["candidate_generation"] = {"objective": "weighted", "iterations": 1, "calibration": "disabled"}
        scores.append(scored)
    winner = max(scores, key=lambda item: item["score"])
    winner["candidate_generation"]["search_revision"] = 2
    winner["candidate_generation"]["selection"] = {
        "method": "Two scenario seeds followed by direct weighted-objective refinement; retain the best evaluated candidate",
        "candidates": [{"objective": item["candidate_generation"]["objective"], "score": item["score"],
                        "dps": item["dps"]} for item in scores]}
    payload = json.dumps(winner, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("Common comparison exceeds its cache limit")
    cache.parent.mkdir(parents=True, exist_ok=True)
    fd, pending = tempfile.mkstemp(dir=cache.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, cache)
    finally:
        Path(pending).unlink(missing_ok=True)
    return winner, False
