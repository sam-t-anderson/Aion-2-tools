"""A fresh anonymous optimization, never a trimmed personal build."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..canonical_presets import MODES, candidate, evaluate, scoring_policy
from ..paths import home
from ..presets import MAX_BYTES


def generate(cls: str, mode: str, progress=None) -> tuple[dict, bool]:
    """Reuse a current-scope result or search both common comparison scenarios."""
    from ..kit.base import ClassData
    from ..learn import uncalibrated
    from ..model.character import load_loadout
    from ..opt.pipeline import Optimizer
    from ..opt.rotation import describe
    from ..report import _spec_text
    from ..scenarios import SCENARIOS

    policy = scoring_policy(cls, mode)
    cache = home() / "cache" / "community-comparisons" / (policy["scope"] + ".json")
    try:
        if cache.stat().st_size <= MAX_BYTES:
            summary = json.loads(cache.read_text(encoding="utf-8"))
            if summary["scoring_policy"]["scope"] == policy["scope"]:
                scored = evaluate(candidate(summary))
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
                progress(f"Common comparison {index}/2: optimizing {objective}; personal gear and constraints are not inputs")
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
            scored = evaluate(candidate(summary, policy))
            scored["candidate_generation"] = {"objective": objective, "iterations": 1, "calibration": "disabled"}
            scores.append(scored)
    winner = max(scores, key=lambda item: item["score"])
    winner["candidate_generation"]["selection"] = {
        "method": "Highest weighted modeled DPS among two separately optimized common-loadout candidates",
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
