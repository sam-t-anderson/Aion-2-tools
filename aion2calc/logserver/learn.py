"""Community learning: what every uploaded fight teaches, pooled per class.

Each upload (public or unlisted; private logs are never used) is broken down
per player and segment into an anonymous **observation**: DPS, crit / double /
perfect / multi-hit rates, casts per minute, idle share, damage and casts per
skill, chosen specializations, combat power, and (when the uploader sends them)
the character's stats. Names are not kept.

From the observations of a class the server derives

* **statistics** (``/api/v1/stats/<class>``, the ``/stats`` page): DPS by
  combat-power bracket, typical rates, the skill shares, cast rates and the
  specializations of the top quarter of players;
* a **community calibration** (``/api/v1/calibration/<class>``), in the same
  shape as the local one (:mod:`aion2calc.learn`), which aion2calc apps pull
  as a starting point before they have enough fights of their own:
    - per-skill damage factors: each skill's damage per cast relative to the
      player's own DPS, against the same ratio in the simulation. Being
      relative, it needs no gear data, and the factors are normalized so the
      overall damage level is untouched;
    - rate factors and the crit curve, from uploads that include ``stats``.
"""
from __future__ import annotations

import math
import statistics as st
import threading
import time
from collections import Counter

from .format import to_encounter

MIN_HITS, MIN_SECONDS = 20, 20.0
SHRINK = 8.0
BOUNDS = {"rate": (0.6, 1.6), "skill": (0.75, 1.33), "crit_shift": 250.0}
_SIM: dict = {}
_LOCK = threading.Lock()


def observe_doc(doc: dict) -> list[dict]:
    """One observation per player per segment with enough data."""
    from ..combat.analyze import analyze
    roster = {p["id"]: p for p in doc["players"]}
    out = []
    for si, seg in enumerate(doc["segments"]):
        if seg["duration"] < MIN_SECONDS:
            continue
        counts = Counter(h["player"] for h in seg["hits"])
        for pid, n in counts.items():
            p = roster[pid]
            if n < MIN_HITS or not p.get("class"):
                continue
            enc = to_encounter(doc, pid, si)
            a = analyze(enc)
            sm = a["summary"]
            skills = {}
            for r in a["skills"]:
                s = skills.setdefault(r["skill"].split(" (")[0], {"damage": 0.0, "casts": 0, "kind": r.get("kind")})
                s["damage"] += r["damage"]
                s["casts"] += r["casts"]
            out.append({"segment": si, "player": pid, "class": p["class"], "boss": seg.get("boss"),
                        "combat_power": p.get("combat_power"), "duration": sm["duration"], "dps": sm["dps"],
                        "hits": sm["hits"], "crit": sm["crit"], "double": sm["double"], "perfect": sm["perfect"],
                        "multihit": sm["multi"], "cpm": sm["cpm"], "idle_share": sm["idle_seconds"] / sm["duration"],
                        "skills": skills, "specs": p.get("specs") or {}, "stats": p.get("stats") or {}})
    return out


def _q(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def aggregate(rows: list[dict]) -> dict:
    """Statistics of one class (optionally one boss)."""
    if not rows:
        return {"observations": 0}
    dps = [r["dps"] for r in rows]
    p75 = _q(dps, 0.75)
    top = [r for r in rows if r["dps"] >= p75] or rows
    brackets: dict = {}
    for r in rows:
        if r.get("combat_power"):
            b = int(r["combat_power"] // 10000) * 10000
            brackets.setdefault(b, []).append(r["dps"])

    def skill_table(rs):
        names = {k for r in rs for k, s in r["skills"].items()
                 if s.get("kind") != "passive" and not k.startswith("Theostone")}
        tab = []
        for nm in names:
            shares = [r["skills"].get(nm, {}).get("damage", 0.0) / max(1.0, r["dps"] * r["duration"]) for r in rs]
            cpm = [60 * r["skills"].get(nm, {}).get("casts", 0) / r["duration"] for r in rs]
            tab.append({"skill": nm, "share": st.median(shares), "cpm": st.median(cpm),
                        "used_by": sum(1 for r in rs if nm in r["skills"]) / len(rs)})
        return sorted(tab, key=lambda x: -x["share"])[:25]

    specs: dict = {}
    for r in top:
        for nm, slots in r["specs"].items():
            specs.setdefault(nm, Counter())[", ".join(map(str, sorted(slots)))] += 1
    spec_rows = [{"skill": nm, "picks": [{"specs": k, "share": v / sum(c.values())} for k, v in c.most_common(3)],
                  "players": sum(c.values())} for nm, c in sorted(specs.items())]
    return {"observations": len(rows), "bosses": Counter(r["boss"] for r in rows if r.get("boss")).most_common(10),
            "dps": {"median": _q(dps, 0.5), "p75": p75, "p90": _q(dps, 0.9), "max": max(dps)},
            "by_combat_power": [{"from": b, "to": b + 9999, "players": len(v), "median_dps": _q(v, 0.5)}
                                for b, v in sorted(brackets.items())],
            "rates": {k: _q([r[k] for r in rows], 0.5) for k in ("crit", "double", "perfect", "multihit")},
            "tempo": {"cpm": _q([r["cpm"] for r in rows], 0.5), "idle_share": _q([r["idle_share"] for r in rows], 0.5)},
            "top_quarter": {"players": len(top), "skills": skill_table(top), "specs": spec_rows,
                            "tempo": {"cpm": _q([r["cpm"] for r in top], 0.5),
                                      "idle_share": _q([r["idle_share"] for r in top], 0.5)}},
            "all": {"skills": skill_table(rows)}}


def sim_profile(cls: str) -> dict | None:
    """Damage per cast of each skill and the DPS of the class's optimized build (cached)."""
    with _LOCK:
        if cls in _SIM:
            return _SIM[cls]
    try:
        from ..plan.context import PlanContext
        from ..opt.rotation import materialize
        from ..run import prepare
        from ..scenarios import SCENARIOS
        from ..sim.engine import Sim
        ctx = PlanContext.for_class(cls)
        scen = SCENARIOS["boss"](ctx.loadout)
        _, _, kit, stats = prepare(ctx.build, scen)
        pol = [e for e in ctx.policy if (e[0] if isinstance(e, tuple) else e) in kit.actions]
        res = Sim(stats.derived(), kit.actions, materialize(pol), scen.target, scen.config, hooks=kit.hooks,
                  cond_mods=kit.cond_mods).run()
        per = {}
        for k, a in kit.actions.items():
            n = res.casts.get(k, 0)
            if n:
                dmg = sum(v for s, v in res.damage_by.items() if s.split(" (")[0] == a.name)
                prev = per.get(a.name, (0.0, 0))
                per[a.name] = (prev[0] + dmg, prev[1] + n)
        prof = {"dps": res.dps, "dpc": {k: d / n for k, (d, n) in per.items() if n},
                "crit_resist": scen.target.crit_resist}
    except Exception:
        prof = None
    with _LOCK:
        _SIM[cls] = prof
    return prof


def _shrunk(r: float, n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, 1 + (r - 1) * n / (n + SHRINK)))


def calibration(cls: str, rows: list[dict], server: str = "") -> dict:
    from ..model import stats as S
    cal = {"class": cls, "source": "community", "server": server, "fights": len(rows), "updated_at": time.time(),
           "active": False, "crit_x0": S.CRIT_X0, "rates": {}, "skills": {}}
    prof = sim_profile(cls)
    if prof and rows:
        per: dict = {}
        for r in rows:
            for nm, s in r["skills"].items():
                sim = prof["dpc"].get(nm)
                if not sim or s["casts"] < 5 or s.get("kind") == "passive" or r["dps"] <= 0:
                    continue
                ratio = (s["damage"] / s["casts"] / r["dps"]) / (sim / prof["dps"])
                if ratio > 0:
                    per.setdefault(nm, []).append((math.log(ratio), s["casts"], s["damage"]))
        raw = {nm: math.exp(sum(lg * w for lg, w, _ in v) / sum(w for _, w, _ in v)) for nm, v in per.items()}
        weight = {nm: sum(d for _, _, d in v) for nm, v in per.items()}
        if raw:
            # normalize: damage-weighted geometric mean = 1 (relative strengths only)
            norm = math.exp(sum(math.log(x) * weight[nm] for nm, x in raw.items()) / sum(weight.values()))
            lo, hi = BOUNDS["skill"]
            cal["skills"] = {nm: _shrunk(x / norm, len(per[nm]), lo, hi) for nm, x in raw.items()}
    with_stats = [r for r in rows if r.get("stats")]
    if with_stats:
        lo, hi = BOUNDS["rate"]
        for k, key in (("double", "double_pct"), ("perfect", "perfect_pct"), ("multihit", "multihit_pct")):
            sub = [r for r in with_stats if r["stats"].get(key)]
            num = sum(r[k] * r["hits"] for r in sub)
            den = sum(r["stats"][key] / 100 * r["hits"] for r in sub)
            if den > 0:
                cal["rates"][k] = _shrunk(num / den, len(sub), lo, hi)
        resist = (prof or {}).get("crit_resist", 0.0)
        xs, ws = [], []
        for r in with_stats:
            c, p = r["stats"].get("critical_hit"), r["crit"]
            if c and 0.03 < p < S.CRIT_CAP - 0.02:
                xs.append(c - resist + math.log(S.CRIT_A / p - 1) / S.CRIT_K)
                ws.append(r["hits"])
        if xs:
            x0 = sum(x * w for x, w in zip(xs, ws)) / sum(ws)
            lim = BOUNDS["crit_shift"]
            cal["crit_x0"] = S.CRIT_X0 + max(-lim, min(lim, (x0 - S.CRIT_X0) * len(xs) / (len(xs) + SHRINK)))
    cal["with_stats"] = len(with_stats)
    cal["active"] = len(rows) >= 5
    return cal
