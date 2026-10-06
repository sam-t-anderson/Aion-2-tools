"""Anonymous class builds, scored with a common Planner loadout on the server."""
from __future__ import annotations

import copy
import math

from .kit.base import ClassData, spec_slots
from .paths import list_names

BUDGETS = {"skill": 203, "stigma": 30, "daevanion": 360}
MAX_BYTES = 100_000


class InvalidPreset(ValueError):
    pass


def candidate(summary: dict) -> dict:
    """Strip character loadout names, gear, scores and report metadata at the source."""
    data = summary.get("build") or {}
    return {"format": "a2preset", "version": 1, "class": summary.get("class"),
            "build": {"class": summary.get("class"), "scenario": "boss",
                      "build": {k: copy.deepcopy(data.get(k, {} if k != "daevanion_nodes" else []))
                                for k in ("sp", "stigmas", "specs", "daevanion_nodes")},
                      "policy": copy.deepcopy(summary.get("policy", []))}}


def parse(doc: dict):
    """Accept only known skills, legal levels, connected boards and bounded policies."""
    from .opt.daevanion import CRYSTAL_BOARDS, connected
    from .opt.rotation import CONDITIONS
    from .report import build_from_summary
    from .run import prepare
    from .scenarios import SCENARIOS

    if not isinstance(doc, dict) or doc.get("format") != "a2preset" or doc.get("version") != 1:
        raise InvalidPreset("not an a2preset v1 document")
    cls = doc.get("class")
    if not isinstance(cls, str) or not cls.isalpha() or cls not in list_names("global", "classes"):
        raise InvalidPreset("unknown class")
    summary = doc.get("build")
    if not isinstance(summary, dict) or summary.get("class") != cls:
        raise InvalidPreset("build class does not match")
    data = summary.get("build")
    if not isinstance(data, dict):
        raise InvalidPreset("missing build allocation")
    cd = ClassData(cls)
    for field, kinds, cap in (("sp", ("active", "passive"), 10), ("stigmas", ("stigma",), 20)):
        values = data.get(field)
        if not isinstance(values, dict) or len(values) > len(cd.skills):
            raise InvalidPreset(f"invalid {field} allocation")
        for name, level in values.items():
            skill = cd.by_name.get(name)
            if not skill or skill["kind"] not in kinds or type(level) is not int or not 1 <= level <= cap:
                raise InvalidPreset(f"invalid {field} skill or level")
            if field == "sp" and level > skill.get("buyMax", 10):
                raise InvalidPreset("skill exceeds its purchasable level")
    if len(data["stigmas"]) > cd.budget(45)["slots"]:
        raise InvalidPreset("too many equipped stigmas")
    nodes = data.get("daevanion_nodes")
    if not isinstance(nodes, list) or len(nodes) > 1024 or any(type(n) is not int for n in nodes):
        raise InvalidPreset("invalid Daevanion nodes")
    if len(set(nodes)) != len(nodes) or any(n not in cd.node_index for n in nodes):
        raise InvalidPreset("unknown or duplicate Daevanion nodes")
    if any(cd.node_index[n][0]["name"] not in CRYSTAL_BOARDS for n in nodes):
        raise InvalidPreset("class presets use the four crystal boards")
    if not connected(cd, set(nodes)):
        raise InvalidPreset("Daevanion nodes must connect to their board centre")
    specs = data.get("specs")
    if not isinstance(specs, dict) or len(specs) > len(cd.skills):
        raise InvalidPreset("invalid specializations")
    for name, choices in specs.items():
        skill = cd.by_name.get(name)
        if not skill or not isinstance(choices, list) or len(choices) > 4 or any(not isinstance(x, str) for x in choices):
            raise InvalidPreset("invalid specialization choices")
        if len(set(choices)) != len(choices) or any(x not in {s["text"] for s in skill.get("specs", [])} for x in choices):
            raise InvalidPreset("unknown specialization")
    policy = summary.get("policy")
    if not isinstance(policy, list) or not 1 <= len(policy) <= 64 or any(not isinstance(p, str) or len(p) > 120 for p in policy):
        raise InvalidPreset("invalid rotation")
    clean = candidate(summary)["build"]
    build, rotation = build_from_summary(clean)
    if build.sp_spent() > BUDGETS["skill"] or build.stigma_spent() > BUDGETS["stigma"] or build.daevanion_cost(cd) > BUDGETS["daevanion"]:
        raise InvalidPreset("build exceeds the shared Planner budget (203 skill / 30 stigma / 360 Daevanion)")
    scen = SCENARIOS["boss"](f"{cls}_l45_global_median")
    _, geared, kit, _ = prepare(build, scen)
    # A real character may unlock more specializations through gear. Keep only those
    # available with the common class loadout used for the comparison.
    effective = geared.effective_levels(cd)
    for sid, choices in build.specs.items():
        build.specs[sid] = tuple(x for x in choices if any(s["id"] == x and s["unlock"] <= effective.get(sid, 1) for s in cd.skills[sid]["specs"]))[:spec_slots(effective.get(sid, 1))]
    _, _, kit, _ = prepare(build, scen)
    for entry in rotation:
        key, condition = entry if isinstance(entry, tuple) else (entry, None)
        if key not in kit.actions or (condition is not None and condition not in CONDITIONS):
            raise InvalidPreset("rotation uses an unavailable skill or condition")
    return build, rotation


def evaluate(doc: dict) -> dict:
    from .learn import uncalibrated
    with uncalibrated():
        return _evaluate(doc)


def _evaluate(doc: dict) -> dict:
    """Recompute DPS and display fields; never use a score or gear supplied by a client."""
    from . import __version__
    from .model.stats import crit_chance
    from .opt.rotation import describe
    from .report import _sim, _spec_text
    from .run import prepare
    from .scenarios import SCENARIOS

    build, policy = parse(doc)
    cls = build.cls
    loadout = f"{cls}_l45_global_median"
    scen = SCENARIOS["boss"](loadout)
    boss, _, _ = _sim(build, scen, policy)
    dummy, _, _ = _sim(build, SCENARIOS["dummy"](loadout), policy)
    if not math.isfinite(boss.dps) or boss.dps <= 0:
        raise InvalidPreset("build produces no finite damage")
    cd, geared, _, stats = prepare(build, scen)
    d = stats.derived()
    return {"class": cls, "level": 45, "scenario": "boss", "loadout": loadout,
            "budgets": dict(BUDGETS), "daevanion_budget": BUDGETS["daevanion"],
            "dps": {"boss": boss.dps, "dummy": dummy.dps},
            "build": {"sp": {cd.skills[k]["name"]: v for k, v in build.sp.items()},
                      "stigmas": {cd.skills[k]["name"]: v for k, v in build.stigmas.items()},
                      "specs": {cd.skills[k]["name"]: [_spec_text(cd, k, x) for x in v] for k, v in build.specs.items()},
                      "daevanion_nodes": sorted(build.daevanion), "sp_spent": build.sp_spent(),
                      "stigma_spent": build.stigma_spent(), "daevanion_cost": build.daevanion_cost(cd),
                      "effective_levels": {cd.skills[k]["name"]: v for k, v in geared.effective_levels(cd).items()}},
            "policy": describe(policy), "shares": boss.shares(),
            "opener": [(round(t, 2), k) for t, k in boss.timeline if t < 30],
            "stats": {"attack_avg": d.attack(), "crit_stat": d.crit_stat,
                      "crit_chance_vs_target": crit_chance(d.crit_stat, scen.target.crit_resist),
                      "cdr": d.cdr, "combat_speed": d.combat_speed, "boost_bucket": d.amp,
                      "double": d.double, "perfect": d.perfect, "multihit": d.multihit, "weapon_amp": d.weapon_amp},
            "evaluation": {"model": __version__, "loadout": loadout, "duration": 180}}
