"""Bounded evaluation of local allocation drafts, with optional fixed-allocation priority search; nothing is published."""
from __future__ import annotations

from dataclasses import fields
import hashlib
import json
import math

from .kit.base import Build, ClassData, spec_slots
from .model.stats import Stats

CLASSES = {"gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter"}
CRYSTALS = {"Nezekan", "Zikel", "Vaizel", "Triniel"}
MAX_BYTES = 128 * 1024
NOTE = ("Entered equipment/stat contributions and Genus lines are assumptions. Source profile stats are not recalculated or verified. "
        "The neutral, uncalibrated damage model evaluates the selected allocation with its default class priority; no allocation, supporting effect or rotation is optimized. "
        "This is not a community ranking, survival guarantee or competitive PvP prediction.")


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def arcana_bonuses(doc, cd):
    """Validate explicit card options against the same bundled browser catalog."""
    from pathlib import Path
    catalog = json.loads((Path(__file__).parent / "app/static/build-catalog.json").read_bytes())
    pools = catalog.get("arcana_pools", {}).get(cd.cls, {})
    items = {item["slug"]: item for item in catalog.get("items", [])}
    out, seen = {}, set()
    loadout = doc.get("loadout")
    if not isinstance(loadout, dict):
        raise ValueError("Supply an equipment loadout")
    components = loadout.get("components", [])
    if not isinstance(components, list) or len(components) > 64:
        raise ValueError("Supply at most 64 equipment components")
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("Invalid equipment component")
        values = component.get("arcana_skills", {})
        if not isinstance(values, dict):
            raise ValueError("Arcana options must be a skill-level map")
        if not values:
            continue
        slot = component.get("slot")
        if not isinstance(slot, str) or slot not in pools or slot in seen:
            raise ValueError("Unknown or duplicate arcana slot")
        seen.add(slot)
        item = items.get(component.get("catalog_slug")) if isinstance(component.get("catalog_slug"), str) else None
        enchant = component.get("enchant")
        if not item or item["category"] not in catalog["equipment_slots"][slot] or item["required_level"] > doc["level"] or not integer(enchant, 0, len(item["levels"])-1):
            raise ValueError("Choose a compatible catalog arcana and enhancement")
        pool = pools[slot]
        allowed = {str(sk["id"]) for sk in pool["skills"]}
        base = catalog["arcana_base_rolls"].get(item["grade"])
        if base is None or any(key not in allowed or not integer(value, 0, pool["max_level"]) for key,value in values.items()) or sum(values.values()) > base + enchant:
            raise ValueError("Arcana options exceed the bundled pool, per-skill cap or grade/enhancement budget")
        for key,value in values.items():
            sid = int(key)
            out[sid] = out.get(sid, 0) + value
    return out


def normalize(doc):
    if not isinstance(doc, dict) or len(json.dumps(doc, allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError("Evaluation input must be an object under 128 KiB")
    if doc.get("format") != "a2build" or not integer(doc.get("version"), 1, 1) or (not isinstance(doc.get("class"), str) or doc["class"] not in CLASSES):
        raise ValueError("Choose an a2build v1 draft with a known class")
    if not isinstance(doc.get("mode"), str) or doc["mode"] not in {"pve", "pvp"} or not integer(doc.get("level"), 1, 45):
        raise ValueError("Choose PvE/PvP and character level 1–45")
    if doc["level"] != 45:
        raise ValueError("Draft evaluation currently supports level 45; lower-level drafts can still be edited and exported")
    cd = ClassData(doc["class"])
    raw, budgets = doc.get("build"), doc.get("budgets")
    if not isinstance(raw, dict) or not isinstance(budgets, dict):
        raise ValueError("Missing allocations or entered budgets")
    for key in ("skill", "stigma", "daevanion"):
        if not integer(budgets.get(key), 0, 10000):
            raise ValueError("Invalid entered point budget")
    board_budgets = budgets.get("boards", {})
    if not isinstance(board_budgets, dict) or any(k not in {b["name"] for b in cd.boards} or not integer(v, 0, 10000) for k, v in board_budgets.items()):
        raise ValueError("Invalid separate board budget")
    build = Build(doc["class"], level=doc["level"])
    for field in ("sp", "stigmas", "bonus", "specs"):
        values = raw.get(field, {})
        if not isinstance(values, dict) or len(values) > len(cd.skills):
            raise ValueError("Invalid skill allocation")
        for key, value in values.items():
            if not isinstance(key, str) or not key.isascii() or not key.isdigit() or str(int(key)) != key or int(key) not in cd.skills:
                raise ValueError("Unknown skill ID")
            sid, skill = int(key), cd.skills[int(key)]
            if field == "specs":
                if skill["kind"] != "active" or not isinstance(value, list) or len(value) > 5 or any(type(n) is not int for n in value) or len(set(value)) != len(value):
                    raise ValueError("Invalid supporting effect selection")
                build.specs[sid] = tuple(value)
            else:
                cap = 30 if field == "bonus" else 20 if field == "stigmas" else min(10, skill.get("buyMax") or 10)
                kind_ok = skill["kind"] == "stigma" if field == "stigmas" else skill["kind"] in {"active", "passive"}
                if not kind_ok or not integer(value, 0 if field == "bonus" else 1, cap):
                    raise ValueError("Invalid skill level")
                getattr(build, field)[sid] = value
    nodes = raw.get("daevanion_nodes", [])
    if not isinstance(nodes, list) or len(nodes) > 2048 or any(type(n) is not int or n not in cd.node_index for n in nodes) or len(set(nodes)) != len(nodes):
        raise ValueError("Unknown or duplicate board nodes")
    build.daevanion = set(nodes)
    for sid,value in arcana_bonuses(doc, cd).items():
        build.bonus[sid] = build.bonus.get(sid, 0) + value
        if build.bonus[sid] > 30:
            raise ValueError("Combined manual and arcana skill bonuses exceed the input bound")
    levels = build.effective_levels(cd)
    if build.sp_spent() > budgets["skill"] or build.stigma_spent() > budgets["stigma"] or len(build.stigmas) > cd.budget(build.level)["slots"]:
        raise ValueError("Allocation exceeds entered budgets or equipped stigma slots")
    for sid, skill in cd.skills.items():
        trained = build.stigmas.get(sid, 0) if skill["kind"] == "stigma" else build.sp.get(sid, 1)
        need = skill.get("unlock") or 1
        if skill["kind"] != "stigma" and skill.get("need"):
            need = skill["need"][min(trained - 1, len(skill["need"]) - 1)] or need
        if (trained > 1 or skill["kind"] == "stigma" and trained > 0 or build.specs.get(sid)) and build.level < need:
            raise ValueError("Character level gate not reached: " + skill["name"])
        if skill.get("max") and levels.get(sid, 0) > skill["max"]:
            raise ValueError("Effective level exceeds catalog maximum: " + skill["name"])
        chosen = build.specs.get(sid, ())
        options = {e["id"]: e for e in skill.get("specs", [])}
        if len(chosen) > spec_slots(levels.get(sid, 1)) or any(n not in options or options[n]["unlock"] > levels.get(sid, 1) for n in chosen):
            raise ValueError("Supporting effect is locked or exceeds available slots")
    crystal_cost = 0
    for board in cd.boards:
        taken = [n for n in board["nodes"] if n["id"] in build.daevanion]
        if not taken:
            continue
        if build.level < board["needLevel"] or any(build.level < (n.get("needLevel") or board["needLevel"]) for n in taken):
            raise ValueError("Board character level gate not reached")
        start = next((n for n in board["nodes"] if n["type"] == "Start"), None)
        stack, seen = ([start], {start["id"]}) if start else ([], set())
        positions = {(n["row"], n["col"]): n for n in board["nodes"]}
        while stack:
            node = stack.pop()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = positions.get((node["row"] + dr, node["col"] + dc))
                if nxt and nxt["id"] in build.daevanion and nxt["id"] not in seen:
                    seen.add(nxt["id"])
                    stack.append(nxt)
        if any(n["id"] not in seen for n in taken):
            raise ValueError("Board nodes must connect to their centre")
        cost = sum(n.get("cost", 0) for n in taken)
        if board["name"] in CRYSTALS:
            crystal_cost += cost
        elif cost > board_budgets.get(board["name"], 0):
            raise ValueError("Separate board budget exceeded")
    if crystal_cost > budgets["daevanion"]:
        raise ValueError("Daevanion budget exceeded")
    loadout = doc.get("loadout")
    if not isinstance(loadout, dict) or not isinstance(loadout.get("components"), list) or len(loadout["components"]) > 64:
        raise ValueError("Supply at most 64 equipment/stat components")
    numeric = {f.name for f in fields(Stats)} - {"level", "pvp", "skill_bonus"}
    clean = []
    for component in loadout["components"]:
        if not isinstance(component, dict) or not isinstance(component.get("stats"), dict):
            raise ValueError("Each equipment component needs a stats object")
        if component.get("source") == "manual-genus-insight":
            continue  # Reapply the explicit Genus state once below.
        stats = component["stats"]
        if any(k not in numeric or type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= (10 if k not in {"weapon_min", "weapon_max", "attack", "crit", "crit_atk", "pvp_atk", "pve_atk", "boss_atk", "front_atk", "back_atk", "pen", "accuracy", "mp_max", "mp_regen", "might", "precision", "destruction", "death", "wisdom", "justice", "time", "illusion", "freedom"} else 1000000) for k, v in stats.items()):
            raise ValueError("Unknown, negative or out-of-range stat; percentage stats use fractions")
        clean.append({"slot": str(component.get("slot", "Entered component"))[:80], "item": str(component.get("item", "Entered stats"))[:200], "stats": dict(stats)})
    total = {key: sum(c["stats"].get(key, 0) for c in clean) for key in numeric}
    if not 0 < total["weapon_max"] <= 1000000 or not 0 <= total["weapon_min"] <= total["weapon_max"] or any(v > (20 if k not in {"weapon_min", "weapon_max", "attack", "crit", "crit_atk", "pvp_atk", "pve_atk", "boss_atk", "front_atk", "back_atk", "pen", "accuracy", "mp_max", "mp_regen", "might", "precision", "destruction", "death", "wisdom", "justice", "time", "illusion", "freedom"} else 1000000) for k, v in total.items()):
        raise ValueError("Supply a valid weapon range and bounded aggregate stats")
    from .opt.genus import prepare
    genus = prepare(doc.get("genus") or {}, doc["mode"], {"mix": doc.get("genus_mix")} if doc.get("genus_mix") else None)
    return build, {"level": build.level, "components": clean}, genus


def evaluate(doc):
    from .learn import uncalibrated
    with uncalibrated():
        return _evaluate(doc)


def _evaluate(doc):
    build, loadout, genus = normalize(doc)
    search = doc.get("search_priority", False)
    if type(search) is not bool:
        raise ValueError("Priority search must be true or false")
    from .opt.genus import apply
    from .run import simulate
    from .scenarios import SCENARIOS
    from . import __version__
    loadout = apply(loadout, genus)
    names = ("pvp", "pvp_burst") if doc["mode"] == "pvp" else ("boss", "dummy")
    scores = {}
    for name in names:
        scenario = SCENARIOS[name](loadout)
        detail = None
        if search:
            from .run import prepare
            from .opt.rotation import bounded_search
            _, _, kit, stats = prepare(build, scenario)
            searched, detail = bounded_search(stats.derived(), kit, scenario.target, scenario.config)
            result = searched.result
        else:
            result = simulate(build, scenario)
        if not math.isfinite(result.dps):
            raise ValueError("Evaluation produced non-finite damage")
        scores[name] = {"dps": result.dps, "shares": result.shares()}
        if detail is not None:
            scores[name]["priority_search"] = detail
    from .model.stats import CALIBRATION, CRIT_X0
    from .sim.engine import SKILL_MULT
    calibration = {"rates": dict(CALIBRATION), "crit_midpoint": CRIT_X0, "skill_multipliers": dict(SKILL_MULT),
                   "basis": "Neutral model; personal/community learned calibration excluded"}
    identity = {"calibration": calibration, "class": build.cls, "level": build.level, "mode": doc["mode"], "build": doc["build"], "budgets": doc["budgets"], "effective_bonus": build.bonus, "loadout": loadout, "genus": genus, "search_priority": search, "selected_priorities": {k:v.get("priority_search", {}).get("policy") for k,v in scores.items()}}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {"format": "a2build-evaluation", "version": 1, "evaluator": __version__, "input_sha256": digest,
            "class": build.cls, "level": build.level, "mode": doc["mode"], "scenarios": scores, "calibration": calibration,
            "genus": genus, "arcana_options_supported": True, "search_priority": search,
            "note": (NOTE.replace("with its default class priority; no allocation, supporting effect or rotation is optimized.",
                    "with bounded priority search; allocations and supporting effects are held fixed.") if search else NOTE)}
