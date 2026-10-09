"""Mode-scoped common-loadout preset scoring, independent of client-reported DPS.

The server owns the policy. Budget observations are not a game maximum and do
not silently change this comparison's resources. These scores compare builds
within a class, mode and scope; they are not player rankings or win rates.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from .kit.base import ClassData
from .model.character import load_loadout
from .paths import list_names
from .presets import BUDGETS, InvalidPreset, candidate as legacy_candidate, parse

MODEL_VERSION = "0.3.1"  # Bump for evaluator/model changes, not capture/UI releases.
# 0.3.0: hand-written kits for all eight classes (was sorcerer only) — see aion2calc/kit/.
# Changes every class's modeled rotation, so the server re-scores all presets under it.
VERSION = 2
POLICY_VERSION = 1
MODES = {"pve": ("boss", "dummy"), "pvp": ("pvp", "pvp_burst")}
NOTE = ("Common-loadout damage comparison with fixed example budgets, not verified progression maxima. "
        "Each scenario contributes 50% of modeled DPS. Scores compare only the same class, mode and scope. "
        "Personal gear, Genus lines, HP reserves and trained skill constraints are not comparison inputs. "
        "The canonical build is the best evaluated eligible candidate, not proof of a global optimum.")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _context(cls: str, mode: str, budgets: dict | None = None):
    if not isinstance(cls, str) or cls not in list_names("global", "classes"):
        raise InvalidPreset("unknown class")
    if not isinstance(mode, str) or mode not in MODES:
        raise InvalidPreset("choose pve or pvp")
    observed = budgets is not None
    budgets = dict(BUDGETS) if budgets is None else budgets
    if (not isinstance(budgets, dict) or set(budgets) != set(BUDGETS)
            or any(type(v) is not int or not 0 <= v <= 10000 for v in budgets.values())):
        raise InvalidPreset("invalid comparison point budgets")
    cd = ClassData(cls)
    loadout_name = f"{cls}_l45_global_median"
    lo = copy.deepcopy(load_loadout(loadout_name))
    policy = {"version": 2 if observed else POLICY_VERSION, "model": MODEL_VERSION, "class": cls, "mode": mode,
              "budgets": dict(budgets), "loadout": loadout_name,
              "loadout_fingerprint": _digest(lo),
              "data_fingerprint": _digest({"class": cd.raw, "hit_profiles": cd.hit_profiles}),
              "score_kind": "weighted_modeled_dps", "weights": {s: .5 for s in MODES[mode]},
              "durations": {s: 30 if s == "pvp_burst" else 180 for s in MODES[mode]},
              "calibration": "disabled", "note": NOTE}
    if observed:
        policy["note"] = ("Common-loadout comparison using the highest server-reported resources for this class, "
                          "pooled across available region/build contexts. Reports and allocated lower bounds are not verified game caps. "
                          "Each scenario contributes 50% of modeled DPS. Scores compare only the same class, mode and scope. "
                          "Personal gear, Genus and survival constraints are excluded. Best evaluated eligible candidate, not proof of a global optimum.")
    if mode == "pvp":
        from .scenarios import PVP_NOTE
        policy["model_note"] = PVP_NOTE
    policy["scope"] = _digest(policy)
    return policy, lo


def scoring_policy(cls: str, mode: str, budgets: dict | None = None) -> dict:
    """Publish the exact comparison scope without exposing local inventory."""
    return _context(cls, mode, budgets)[0]


def candidate(summary: dict, policy: dict | None = None) -> dict:
    """Only allocations and priority leave the source character's report."""
    if not isinstance(summary, dict):
        raise InvalidPreset("missing build summary")
    if summary.get("survival") or summary.get("skill_reserves") or (summary.get("genus") or {}).get("stats"):
        raise InvalidPreset("personal constraints or Genus allocations require a separate common-loadout optimization")
    scenario = summary.get("scenario", "boss")
    if scenario not in ("boss", "dummy", "pvp", "pvp_burst"):
        raise InvalidPreset("unsupported preset scenario")
    mode = "pvp" if scenario.startswith("pvp") else "pve"
    cls = summary.get("class")
    policy = policy or scoring_policy(cls, mode)
    if not isinstance(policy, dict):
        raise InvalidPreset("missing preset scoring policy")
    if policy.get("class") != cls or policy.get("mode") != mode or not isinstance(policy.get("scope"), str):
        raise InvalidPreset("preset policy does not match class and mode")
    build = legacy_candidate(summary)["build"]
    build["scenario"] = MODES[mode][0]
    return {"format": "a2preset", "version": VERSION, "class": cls, "mode": mode,
            "scope": policy["scope"], "build": build}


def evaluate(document: dict, budgets: dict | None = None) -> dict:
    """Recompute the weighted score using only the server's current policy."""
    from .learn import uncalibrated
    if not isinstance(document, dict) or document.get("format") != "a2preset" or document.get("version") != VERSION:
        raise InvalidPreset("not an a2preset v2 document")
    cls, mode = document.get("class"), document.get("mode")
    policy, lo = _context(cls, mode, budgets)
    if document.get("scope") != policy["scope"]:
        raise InvalidPreset("preset scoring scope changed; fetch the current policy and resubmit")
    with uncalibrated():
        return _evaluate(document, policy, lo)


def _evaluate(document: dict, policy: dict, lo: dict) -> dict:
    from .model.stats import crit_chance
    from .opt.rotation import describe
    from .report import _sim, _spec_text
    from .run import prepare
    from .scenarios import SCENARIOS
    from .kit.specialties import describe as describe_specialties

    primary, secondary = MODES[policy["mode"]]
    legacy = {"format": "a2preset", "version": 1, "class": document["class"], "build": document.get("build")}
    build, rotation = parse(legacy, scenario_name=primary, loadout_snapshot=lo, budgets=policy["budgets"])
    scen = SCENARIOS[primary](lo)
    first, _, _ = _sim(build, scen, rotation)
    second, _, _ = _sim(build, SCENARIOS[secondary](lo), rotation)
    dps = {primary: first.dps, secondary: second.dps}
    if any(not math.isfinite(x) or x <= 0 for x in dps.values()):
        raise InvalidPreset("preset produces no finite damage in one or more comparison scenarios")
    score = sum(policy["weights"][s] * x for s, x in dps.items())
    cd, geared, _, stats = prepare(build, scen)
    d = stats.derived()
    return {"class": build.cls, "level": 45, "mode": policy["mode"], "scenario": primary,
            "loadout": policy["loadout"], "loadout_snapshot": copy.deepcopy(lo),
            "budgets": dict(policy["budgets"]), "daevanion_budget": policy["budgets"]["daevanion"],
            "dps": dps, "score": score, "scoring_policy": copy.deepcopy(policy),
            "model_note": policy.get("model_note"),
            "build": {"sp": {cd.skills[k]["name"]: v for k, v in build.sp.items()},
                      "stigmas": {cd.skills[k]["name"]: v for k, v in build.stigmas.items()},
                      "specs": {cd.skills[k]["name"]: [_spec_text(cd, k, x) for x in v] for k, v in build.specs.items()},
                      "daevanion_nodes": sorted(build.daevanion), "sp_spent": build.sp_spent(),
                      "stigma_spent": build.stigma_spent(), "daevanion_cost": build.daevanion_cost(cd),
                      "effective_levels": {cd.skills[k]["name"]: v for k, v in geared.effective_levels(cd).items()},
                      "specialties": describe_specialties(cd, geared)},
            "policy": describe(rotation), "shares": first.shares(),
            "opener": [(round(t, 2), k) for t, k in first.timeline if t < 30],
            "stats": {"attack_avg": d.attack(), "crit_stat": d.crit_stat,
                      "crit_chance_vs_target": crit_chance(d.crit_stat, scen.target.crit_resist,
                                                       midpoint=1024.52 if scen.target.is_player else None),
                      "cdr": d.cdr, "combat_speed": d.combat_speed, "boost_bucket": d.amp,
                      "double": d.double, "perfect": d.perfect, "multihit": d.multihit, "weapon_amp": d.weapon_amp},
            "evaluation": {"model": MODEL_VERSION, "scope": policy["scope"], "policy_version": policy["version"]}}
