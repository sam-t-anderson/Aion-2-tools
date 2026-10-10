"""Calibrate the hand-written kits' audited ``TIMING`` / ``ASSUME`` knobs
against real combat-log captures.

The hand-written kits read every damage *number* from the global client's
skill tables, but a handful of values the client never exposes live in each
kit's :data:`TIMING` (animation / recovery lengths) and :data:`ASSUME`
(chain fractions, proc/break uptimes, pet windows) tables.  Those are the only
free parameters in a kit, and the kit docstrings say outright that they are to
be tuned once real combat-log captures are available.  This module is that
tuner.

Ground truth comes from two places:

* **KR A2DIL** aggregate training-dummy logs — ``data/kr/a2dil/<cls>.json`` —
  the public Korean top-player damage-share distribution per skill.  This is
  bundled, so calibration runs with no input.  Korean logs are at higher level
  with specializations and skills the global build does not have, so a share of
  their damage (:func:`report.kr_share_overlap`'s ``kr_share_not_in_global_data``)
  can never be matched; the achievable ceiling is ``1 - that``.
* **A user's own A2Parser capture** — any ``.a2log.json`` the meter saved, or an
  encounter from :mod:`aion2calc.combat.adapters`.  :func:`from_capture` turns a
  capture into the same per-skill share target, so the knobs can be fitted to
  the player's actual fights instead of (or alongside) the KR aggregate.

Only the float knobs are tuned, and each stays within a bounded multiple of its
authored value (probabilities / fractions / uptimes additionally clamp to
``[0, 1]``).  Integer mechanics (stack counts, knockdown uses) and boolean
mechanic flags (``boss_breakable``) are left untouched — those are game rules,
not estimates, and this module never invents one.
"""
from __future__ import annotations

import json
from dataclasses import replace

from .kit.base import ClassData
from .report import kr_share_overlap
from .run import kit_module, prepare
from .scenarios import dummy, typical_build
from .sim.engine import Sim

CLASSES = ("gladiator", "templar", "assassin", "ranger", "sorcerer", "spiritmaster", "cleric", "chanter")

#: Names whose value is a probability / fraction / uptime: tuned, but clamped to [0, 1].
_UNIT = ("frac", "uptime", "rate", "prob", "chance", "share")


def _is_unit(name: str) -> bool:
    return any(w in name for w in _UNIT)


def _tunable(table: dict) -> dict:
    """The float entries of a ``TIMING`` / ``ASSUME`` table (ints/bools are mechanics)."""
    return {k: float(v) for k, v in table.items()
            if isinstance(v, float) or (isinstance(v, int) and not isinstance(v, bool) and _is_unit(k))}


def _bounds(name: str, value: float) -> tuple[float, float]:
    lo, hi = 0.5 * value, 1.5 * value
    if value <= 0:
        lo, hi = 0.0, 0.05
    if _is_unit(name):
        lo, hi = max(0.0, lo), min(1.0, max(hi, value))
    return lo, hi


def _scenario(cls: str, duration: float = 180.0):
    scen = dummy(f"{cls}_l45_global_median")
    return replace(scen, config=replace(scen.config, duration=duration, record_damage=True))


def _optimized_policy(cls: str, build=None, *, duration: float = 180.0, restarts: int = 1):
    """Freeze one optimized priority for ``cls`` — the rotation the tool recommends.

    Over the small knob ranges the tuner sweeps the optimal order is stable, so
    the policy is optimized once and reused, which keeps calibration tractable.
    """
    from .opt.rotation import optimize_rotation
    build = build or typical_build(cls)
    scen = _scenario(cls, duration)
    _, _, kit, stats = prepare(build, scen)
    return optimize_rotation(stats.derived(), kit, scen.target, scen.config, restarts=restarts).policy


def _sim_shares(cls: str, *, duration: float = 180.0, build=None, policy=None) -> dict:
    """Per-skill-name simulated damage shares for ``cls``.

    Uses the given frozen ``policy`` (an optimized priority), else the kit's
    default priority order.
    """
    build = build or typical_build(cls)
    scen = _scenario(cls, duration)
    _, _, kit, stats = prepare(build, scen)
    pol = policy if policy is not None else kit.policy
    from .opt.rotation import materialize
    pol = [e for e in pol if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    res = Sim(stats.derived(), kit.actions, materialize(pol), scen.target, scen.config,
              hooks=kit.hooks, cond_mods=kit.cond_mods).run()
    return res.shares()


def _target_shares(cls: str) -> dict:
    """KR A2DIL damage shares keyed by skill id, restricted to the global skill set."""
    from .paths import data_file
    path = data_file("kr", "a2dil", f"{cls}.json")
    if not path.exists():
        return {}
    cd = ClassData(cls)
    kr: dict = {}
    for v in json.loads(path.read_text(encoding="utf-8"))["skills"].values():
        if v["code"]:
            kr[v["code"]] = kr.get(v["code"], 0.0) + v["mean_share"]
    tot = sum(kr.values()) or 1.0
    return {k: v / tot for k, v in kr.items()}, cd


def gaps(cls: str, shares: dict | None = None, *, limit: int = 8, policy=None) -> dict:
    """Where the simulated share distribution diverges most from the KR logs.

    Returns the overlap, the achievable ceiling (``1 - KR-only mass``) and the
    skills the simulation most over- or under-weights relative to the KR logs,
    each as ``{skill, sim, kr, delta}`` where ``delta = sim - kr``.  Evaluated
    against the tool's optimized rotation unless a ``policy`` is given.
    """
    if shares is None:
        shares = _sim_shares(cls, policy=policy if policy is not None else _optimized_policy(cls))
    overlap = kr_share_overlap(cls, shares) or {"overlap": 0.0, "kr_share_not_in_global_data": 0.0}
    kr, cd = _target_shares(cls)
    sim: dict = {}
    for name, v in shares.items():
        base = name.split(" (")[0]
        s = cd.by_name.get(base) or next((x for n, x in cd.by_name.items() if base.startswith(n)), None)
        if s:
            sim[s["id"]] = sim.get(s["id"], 0.0) + v
    rows = []
    for sid in set(sim) | set(kr):
        name = cd.skills[sid]["name"] if sid in cd.skills else str(sid)
        rows.append({"skill": name, "sim": sim.get(sid, 0.0), "kr": kr.get(sid, 0.0),
                     "delta": sim.get(sid, 0.0) - kr.get(sid, 0.0)})
    rows.sort(key=lambda r: -abs(r["delta"]))
    ceiling = 1.0 - overlap["kr_share_not_in_global_data"]
    return {"class": cls, "overlap": overlap["overlap"], "ceiling": ceiling,
            "fidelity": overlap["overlap"] / ceiling if ceiling else 0.0,
            "kr_only_mass": overlap["kr_share_not_in_global_data"], "gaps": rows[:limit]}


def _overlap_for(cls: str, target: dict | None, policy=None) -> float:
    """Current share overlap of the live kit against ``target`` (KR if None)."""
    shares = _sim_shares(cls, policy=policy)
    if target is None:
        ov = kr_share_overlap(cls, shares)
        return ov["overlap"] if ov else 0.0
    # target is a {skill_id: share} map; project sim shares onto skill ids
    cd = ClassData(cls)
    sim: dict = {}
    for name, v in shares.items():
        base = name.split(" (")[0]
        s = cd.by_name.get(base) or next((x for n, x in cd.by_name.items() if base.startswith(n)), None)
        if s:
            sim[s["id"]] = sim.get(s["id"], 0.0) + v
    return sum(min(sim.get(k, 0.0), target.get(k, 0.0)) for k in set(sim) | set(target))


def tune(cls: str, *, target: dict | None = None, rounds: int = 3, grid: int = 5) -> dict:
    """Coordinate-descent fit of the kit's float ``TIMING`` / ``ASSUME`` knobs to
    the ground-truth share distribution (KR A2DIL unless ``target`` is given).

    Each knob is swept over a bounded grid around its authored value while the
    others are held, keeping any change that raises the share overlap; booleans
    and integer mechanics are never touched.  The kit module's tables are
    restored before returning, so this is side-effect free — it reports the
    suggested values, it does not write them.
    """
    mod = kit_module(cls)
    tables = {name: getattr(mod, name) for name in ("TIMING", "ASSUME") if isinstance(getattr(mod, name, None), dict)}
    original = {name: dict(t) for name, t in tables.items()}
    knobs = [(name, k) for name, t in tables.items() for k in _tunable(t)]
    policy = _optimized_policy(cls)                           # freeze the recommended rotation
    start = _overlap_for(cls, target, policy)
    best = start
    try:
        for _ in range(rounds):
            improved = False
            for name, k in knobs:
                cur = tables[name][k]
                lo, hi = _bounds(k, original[name][k])
                if hi <= lo:
                    continue
                candidates = [round(lo + (hi - lo) * i / (grid - 1), 4) for i in range(grid)] + [cur]
                best_v, best_ov = cur, best
                for v in candidates:
                    tables[name][k] = v
                    ov = _overlap_for(cls, target, policy)
                    if ov > best_ov + 1e-6:
                        best_ov, best_v = ov, v
                tables[name][k] = best_v
                if best_v != cur:
                    improved = True
                best = best_ov
            if not improved:
                break
        suggested = {name: {k: tables[name][k] for k in _tunable(original[name])
                            if tables[name][k] != original[name][k]} for name in tables}
    finally:
        for name, t in original.items():                      # never leave the module mutated
            tables[name].clear()
            tables[name].update(t)
    suggested = {name: v for name, v in suggested.items() if v}
    return {"class": cls, "overlap_before": start, "overlap_after": best,
            "gain": best - start, "suggested": suggested}


def encounter_from_capture(path_or_ref: str, *, player: str | None = None, segment: int | None = None) -> dict:
    """Turn a real A2Parser capture (or any supported log) into one encounter.

    A saved ``.a2log.json`` from the meter is routed through
    :func:`aion2calc.combat.a2log.to_encounter` for its local recording player
    (meter order puts them first) and its longest recorded segment, so a partial
    multi-encounter capture still yields its most informative fight.  Everything
    else (A2DIL records, AbyssLogs references, canonical JSON/CSV) goes through
    :func:`aion2calc.combat.adapters.load`.
    """
    from pathlib import Path
    p = Path(path_or_ref)
    if p.exists() and p.suffix.lower() in (".json", ".a2log") or str(path_or_ref).endswith(".a2log.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
        if isinstance(doc, dict) and doc.get("format") == "a2log":
            from .combat import a2log as F
            players = doc.get("players") or []
            segs = doc.get("segments") or []
            idx = segment if segment is not None else max(
                range(len(segs)), key=lambda i: len(segs[i].get("hits") or []), default=0)
            pid = player
            if pid is None:                                    # the recording (local) player, else the top damage
                pid = next((p["id"] for p in players if p.get("local")), None)
                if pid is None and segs:
                    dmg: dict = {}
                    for h in segs[idx].get("hits") or []:
                        who = h.get("player") or h.get("source")
                        if who:
                            dmg[who] = dmg.get(who, 0.0) + (h.get("damage") or 0.0)
                    ids = {p["id"] for p in players}
                    ranked = sorted((k for k in dmg if not ids or k in ids), key=lambda k: -dmg[k])
                    pid = ranked[0] if ranked else (players[0]["id"] if players else None)
                elif pid is None and players:
                    pid = players[0]["id"]
            return F.to_encounter(doc, pid, idx)
    from .combat.adapters import load
    return load(path_or_ref, player=player)


def from_capture(path_or_ref: str, *, player: str | None = None, segment: int | None = None) -> dict:
    """Compare the simulation to a real A2Parser capture (or any supported log).

    Returns the per-skill share and cast comparison against the class's optimal
    simulation (:func:`aion2calc.combat.analyze.vs_optimal`) and against the KR
    aggregate (:func:`~aion2calc.combat.analyze.vs_top`), so the knobs can be
    judged — and, with :func:`tune`, fitted — against the player's own fight.
    """
    from .combat.analyze import vs_optimal, vs_top
    enc = encounter_from_capture(path_or_ref, player=player, segment=segment)
    return {"source": enc["meta"].get("source"), "class": enc["meta"].get("class"),
            "duration": enc["meta"].get("duration"), "dps": enc["meta"].get("dps"),
            "vs_sim": vs_optimal(enc), "vs_top": vs_top(enc)}


def capture_target(path_or_ref: str, *, player: str | None = None, segment: int | None = None) -> tuple[str, dict]:
    """``(class, {skill_id: share})`` from a real capture, for :func:`tune`'s ``target``."""
    enc = encounter_from_capture(path_or_ref, player=player, segment=segment)
    from .combat.analyze import analyze
    cls = enc["meta"]["class"]
    cd = ClassData(cls)
    shares: dict = {}
    for r in analyze(enc)["skills"]:
        base = r["skill"].split(" (")[0]
        s = cd.by_name.get(base) or next((x for n, x in cd.by_name.items() if base.startswith(n)), None)
        if s:
            shares[s["id"]] = shares.get(s["id"], 0.0) + r["share"]
    return cls, shares


def report(classes=CLASSES) -> list[dict]:
    """Fidelity of every kit against the KR logs, worst first."""
    rows = [gaps(c) for c in classes]
    rows.sort(key=lambda r: r["fidelity"])
    return rows
