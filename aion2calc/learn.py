"""Learn from your own fights.

Every saved fight is matched to what its player had equipped at the time (the
equipment snapshot taken at each character import, nearest before the fight).
For each match the model's predictions for that exact gear are compared with
what the log recorded:

* crit, double, perfect and multi-hit rates (stats -> chance conversions)
* damage per cast of each skill (the skill's damage model)
* casts per minute and idle time (how the rotation is played; kept for the
  advice, never folded into the model)

The comparisons are stored (``observations`` in ``aion2.db``) and pooled into a
per-class calibration (``data/calibration/<class>.json`` in the user folder):
a shifted crit curve, factors for double / perfect / multi-hit, and per-skill
damage factors. Each factor is shrunk toward 1 until enough fights back it and
is bounded, so one odd log cannot swing the model. The planners and the
character advice use the calibration once two or more fights are matched;
the published class reports never do.
"""
from __future__ import annotations

import math
import time
from contextlib import contextmanager
from datetime import datetime

from .db import store
from .model import stats as S
from .paths import data_file, read_json, write_user_json

MIN_FIGHTS = 2
BOUNDS = {"rate": (0.6, 1.6), "skill": (0.75, 1.33), "crit_shift": 250.0}
SHRINK = 8.0          # fights' worth of prior weight on "the model is right"


def _ts(enc: dict) -> float:
    m = enc.get("meta", {})
    if m.get("started_at"):
        try:
            return datetime.fromisoformat(str(m["started_at"]).replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return m.get("imported_at") or time.time()


def _build_of(cls: str, snap: dict, encounter: dict):
    from .kit.base import Build, ClassData
    cd = ClassData(cls)
    b = Build(cls, level=snap.get("level") or 45)
    b.sp = {int(k): v for k, v in snap["build"]["sp"].items()}
    b.stigmas = {int(k): v for k, v in snap["build"]["stigmas"].items()}
    b.daevanion = set(snap["build"]["daevanion"])
    for name, text in (encounter.get("specs") or {}).items():          # specs recorded in the log
        sk = cd.by_name.get(name)
        if not sk:
            continue
        slots = [int(x) for x in str(text).replace(" ", "").split(",") if x.isdigit()]
        ids = [x["id"] for x in sk.get("specs", [])]
        b.specs[sk["id"]] = tuple(ids[i - 1] for i in slots if 0 < i <= len(ids))
    return b


def observe(encounter_id: int, conn=None) -> dict | None:
    """Compare one saved fight with the model for the gear its player wore then."""
    conn = conn or store.connect()
    enc = store.encounter(conn, encounter_id)
    if not enc:
        return None
    m = enc["meta"]
    if m.get("learning_excluded") is True:
        return None
    cls, player = m.get("class"), m.get("player")
    if not cls or not player:
        return None
    from .combat.analyze import analyze
    a = analyze(enc)
    sm = a["summary"]
    obs = {"encounter_id": encounter_id, "class": cls, "player": player, "target": m.get("target"),
           "duration": sm["duration"], "hits": sm["hits"], "dps": sm["dps"],
           "observed": {"crit": sm["crit"], "double": sm["double"], "perfect": sm["perfect"], "multihit": sm["multi"],
                        "cpm": sm["cpm"], "idle": sm["idle_seconds"]},
           "skills": {}}
    for r in a["skills"]:                              # chain steps count with their skill
        s = obs["skills"].setdefault(r["skill"].split(" (")[0], {"damage": 0.0, "casts": 0, "kind": r.get("kind")})
        s["damage"] += r["damage"]
        s["casts"] += r["casts"]
    snap = store.snapshot_for(conn, player, cls, _ts(enc))
    if snap:
        obs["snapshot_id"] = snap["id"]
        with uncalibrated():
            obs.update(_predict(cls, snap["data"], enc))
    store.put_observation(conn, encounter_id, snap and snap["id"], cls, player, obs)
    return obs


def _predict(cls: str, snap: dict, enc: dict) -> dict:
    from dataclasses import replace

    from .opt.rotation import materialize
    from .report import build_from_summary
    from .run import prepare
    from .scenarios import SCENARIOS
    from .sim.engine import Sim
    from .app.views import result_roots
    import json
    b = _build_of(cls, snap, enc)
    scen = SCENARIOS["dummy" if "scarecrow" in str(enc["meta"].get("target", "")).lower() else "boss"](snap["loadout"])
    scen = replace(scen, config=replace(scen.config, duration=max(10.0, enc["meta"]["duration"])))
    cd, bb, kit, st = prepare(b, scen)
    d = st.derived()
    pol = None
    for root in result_roots():
        p = root / f"{cls}_l45" / "build.json"
        if p.exists():
            pol = build_from_summary(json.loads(p.read_text(encoding="utf-8")))[1]
            break
    pol = [e for e in (pol or kit.policy) if (e[0] if isinstance(e, tuple) else e) in kit.actions]
    res = Sim(d, kit.actions, materialize(pol), scen.target, scen.config, hooks=kit.hooks,
              cond_mods=kit.cond_mods).run()
    per_cast = {}
    for k, a in kit.actions.items():
        dmg = sum(v for src, v in res.damage_by.items() if src.split(" (")[0] == a.name)
        n = res.casts.get(k, 0)
        if n:
            prev = per_cast.get(a.name, {"damage": 0.0, "casts": 0})
            per_cast[a.name] = {"damage": prev["damage"] + dmg, "casts": prev["casts"] + n}
    return {"predicted": {"crit": S.crit_chance(d.crit_stat, scen.target.crit_resist), "double": d.double,
                          "perfect": d.perfect, "multihit": d.multihit, "cpm": 60 * sum(res.casts.values()) /
                          scen.config.duration, "dps": res.dps},
            "crit_stat": d.crit_stat, "crit_resist": scen.target.crit_resist, "sim_skills": per_cast}


def _shrunk(ratio: float, n: float, lo: float, hi: float) -> float:
    r = 1 + (ratio - 1) * n / (n + SHRINK)
    return max(lo, min(hi, r))


def fit(cls: str, conn=None) -> dict:
    """Pool the observations of a class into a calibration and save it."""
    conn = conn or store.connect()
    obs = [o["data"] for o in store.observations(conn, cls) if o["data"].get("predicted")]
    cal = {"class": cls, "fights": len(obs), "updated_at": time.time(), "active": len(obs) >= MIN_FIGHTS,
           "crit_x0": S.CRIT_X0, "rates": {}, "skills": {}, "players": {}}
    if obs:
        lo, hi = BOUNDS["rate"]
        for k in ("double", "perfect", "multihit"):
            num = sum(o["observed"][k] * o["hits"] for o in obs)
            den = sum(o["predicted"][k] * o["hits"] for o in obs)
            if den > 0:
                cal["rates"][k] = _shrunk(num / den, len(obs), lo, hi)
        xs, ws = [], []
        for o in obs:
            p = o["observed"]["crit"]
            if 0.03 < p < S.CRIT_CAP - 0.02:
                xs.append(o["crit_stat"] - o.get("crit_resist", 0) + math.log(S.CRIT_A / p - 1) / S.CRIT_K)
                ws.append(o["hits"])
        if xs:
            x0 = sum(x * w for x, w in zip(xs, ws)) / sum(ws)
            shift = (x0 - S.CRIT_X0) * len(xs) / (len(xs) + SHRINK)
            lim = BOUNDS["crit_shift"]
            cal["crit_x0"] = S.CRIT_X0 + max(-lim, min(lim, shift))
        lo, hi = BOUNDS["skill"]
        per: dict = {}
        for o in obs:
            for name, s in o["skills"].items():
                sim = (o.get("sim_skills") or {}).get(name)
                if not sim or s["casts"] < 5 or sim["casts"] < 3 or s.get("kind") == "passive":
                    continue
                r = (s["damage"] / s["casts"]) / (sim["damage"] / sim["casts"])
                per.setdefault(name, []).append((r, s["casts"]))
        for name, rows in per.items():
            r = math.exp(sum(math.log(x) * w for x, w in rows) / sum(w for _, w in rows))
            cal["skills"][name] = _shrunk(r, len(rows), lo, hi)
    for o in store.observations(conn, cls):
        d = o["data"]
        p = cal["players"].setdefault(d["player"], {"fights": 0, "cpm": [], "cpm_model": [], "idle": []})
        p["fights"] += 1
        p["cpm"].append(d["observed"]["cpm"])
        p["idle"].append(d["observed"]["idle"])
        if d.get("predicted"):
            p["cpm_model"].append(d["predicted"]["cpm"])
    for p in cal["players"].values():
        p["cpm"] = sum(p["cpm"]) / len(p["cpm"])
        p["idle"] = sum(p["idle"]) / len(p["idle"])
        p["cpm_model"] = sum(p["cpm_model"]) / len(p["cpm_model"]) if p["cpm_model"] else None
    write_user_json(cal, "calibration", f"{cls}.json")
    return cal


def update(encounter_id: int) -> dict | None:
    """Observe a newly saved fight and refit its class (called after every import)."""
    o = observe(encounter_id)
    return fit(o["class"]) if o else None


def calibration(cls: str) -> dict | None:
    return read_json("calibration", f"{cls}.json") if data_file("calibration", f"{cls}.json").exists() else None


_DEFAULT_X0 = S.CRIT_X0


def community(cls: str, max_age: float = 86400, fetch: bool = True) -> dict | None:
    """The community calibration of your log server (cached for a day), if one is set."""
    import json as _json
    import urllib.request
    name = ("calibration", f"community_{cls}.json")
    cached = read_json(*name) if data_file(*name).exists() else None
    if cached and time.time() - cached.get("fetched_at", 0) < max_age:
        return cached
    if not fetch:
        return cached
    try:
        from .combat.share import effective
        url = (effective().get("url") or "").rstrip("/")
        if not url:
            return cached
        with urllib.request.urlopen(f"{url}/api/v1/calibration/{cls}", timeout=10) as r:
            got = _json.load(r)
        got["fetched_at"] = time.time()
        write_user_json(got, *name)
        return got
    except Exception:
        return cached


def community_stats(cls: str, max_age: float = 86400) -> dict | None:
    """Class statistics of your log server (top players' skills and specializations), cached."""
    import json as _json
    import urllib.request
    name = ("calibration", f"community_stats_{cls}.json")
    cached = read_json(*name) if data_file(*name).exists() else None
    if cached and time.time() - cached.get("fetched_at", 0) < max_age:
        return cached
    try:
        from .combat.share import effective
        url = (effective().get("url") or "").rstrip("/")
        if not url:
            return cached
        with urllib.request.urlopen(f"{url}/api/v1/stats/{cls}", timeout=10) as r:
            got = _json.load(r)
        got["fetched_at"] = time.time()
        write_user_json(got, *name)
        return got
    except Exception:
        return cached


def merged(cls: str, use_community: bool = True) -> dict | None:
    """Your calibration on top of the community one: your own fights win where they exist."""
    local = calibration(cls)
    local = local if local and local.get("active") else None
    com = community(cls) if use_community else None
    com = com if com and com.get("active") else None
    if not local and not com:
        return None
    out = {"class": cls, "active": True, "crit_x0": S.CRIT_X0, "rates": {}, "skills": {}, "sources": []}
    for c, label in ((com, "community"), (local, "yours")):
        if not c:
            continue
        out["sources"].append(f"{label}: {c.get('fights', 0)} fights")
        if abs(c.get("crit_x0", S.CRIT_X0) - _DEFAULT_X0) > 1e-6:
            out["crit_x0"] = c["crit_x0"]
        out["rates"].update(c.get("rates") or {})
        out["skills"].update(c.get("skills") or {})
    return out


def apply(cls: str) -> dict | None:
    """Switch the model to the class's learned calibration: your fights, filled in by the
    community calibration of your log server."""
    from .sim import engine
    reset()
    cal = merged(cls)
    if not cal:
        return None
    S.set_crit_midpoint(cal["crit_x0"])
    S.CALIBRATION.update(cal.get("rates") or {})
    engine.SKILL_MULT.update(cal.get("skills") or {})
    return cal


@contextmanager
def calibrated(cls: str):
    """Run a block with the class's calibration on (model restored afterwards)."""
    try:
        yield apply(cls)
    finally:
        reset()


@contextmanager
def uncalibrated():
    saved = (S.CRIT_X0, dict(S.CALIBRATION))
    from .sim import engine
    skills = dict(engine.SKILL_MULT)
    reset()
    try:
        yield
    finally:
        S.set_crit_midpoint(saved[0])
        S.CALIBRATION.update(saved[1])
        engine.SKILL_MULT.update(skills)


def reset() -> None:
    from .sim import engine
    S.set_crit_midpoint(_DEFAULT_X0)
    S.CALIBRATION.update({"double": 1.0, "perfect": 1.0, "multihit": 1.0})
    engine.SKILL_MULT.clear()


def summary(cal: dict | None) -> list[str]:
    """Plain-language lines for the app and the advice."""
    if not cal:
        return ["No fights matched to an imported character yet: import the character, then its fights."]
    out = [f"{cal['fights']} fight(s) matched to equipped gear" +
           ("" if cal.get("active") else f" (the calibration turns on at {MIN_FIGHTS})")]
    if abs(cal["crit_x0"] - _DEFAULT_X0) > 1:
        out.append(f"crit curve: {'more' if cal['crit_x0'] > _DEFAULT_X0 else 'less'} Critical Hit needed for the "
                   f"same chance than the community curve ({cal['crit_x0'] - _DEFAULT_X0:+.0f})")
    for k, v in (cal.get("rates") or {}).items():
        if abs(v - 1) > 0.01:
            out.append(f"{k}: {v:.2f}x the predicted rate")
    big = sorted((cal.get("skills") or {}).items(), key=lambda kv: -abs(kv[1] - 1))[:5]
    for name, v in big:
        if abs(v - 1) > 0.02:
            out.append(f"{name}: {v:.2f}x the modeled damage per cast")
    return out
