"""Boss area-of-effect shapes measured from recordings (0.2.365).

No packet names an effect's shape or size: a boss's cast record carries the aim point and the caster's facing and
nothing else ([open investigations](../../docs/open-investigations.md)), and the game's own data tables (as the
public databases read them) name the skills and their cast times without a range or an area. The shape is
therefore *measured*: for each boss cast, where every player stood when the skill's damage landed and which of
them it hit. Over many casts the hit and unhit positions separate along one of a few candidate shapes -- a circle
around the aim point, a circle around the caster, a cone from the caster, a line from the caster, a ring -- and
the candidate that separates them best, with its size, is the skill's measured shape.

The damage a boss deals is recorded under the generic *Attack* id for most of its skills, so hits are attributed
to casts by time: the damage the boss deals after a cast, until its next cast or ``WINDOW`` seconds, counts for
that cast. Positions come from the recording's movement rows (the recording player's own, the party's status
updates and the places casts and effects were aimed), interpolated between fixes as the replay does.

Distances are in the game's world units; the recordings put melee hits at 250-300 units, so a unit is about a
centimetre and a metre about 100 units.
"""
from __future__ import annotations

import bisect
import json
import math
import statistics
from collections import defaultdict

TRACK_GAP = 6.0       # s: interpolate between two fixes at most this far apart (the replay's rule)
STALE = 4.0           # s: a fix older than this (or further ahead) does not place an entity
WINDOW = 5.0          # s: damage after a cast counts for it until the boss's next cast or this long
NEAR_FIGHT = 4000.0   # units: a player further than this from the boss is out of the fight, not "unhit"
NEAR = 60.0           # units: an aim this close to the target (the caster) was aimed at it (around itself)
SHAPES = ("single_target", "circle_caster", "circle_aim", "cone", "line", "ring")   # plus "everyone": raid-wide
SIMPLER_BY = 0.03
SAMPLES_VERSION = 1       # bumped when cast_samples changes what it keeps: cached per-log samples are then redone     # a shape with more parameters must beat a simpler one by this much balanced accuracy
UNIT_NOTE = "game units; melee hits land at 250-300, so about 100 units to a metre"


def _track(rows):
    """Per-entity movement tracks: sorted (t, x, y, heading or None)."""
    tracks = defaultdict(list)
    for row in rows or []:
        try:
            tracks[row["entity"]].append((float(row["t"]), float(row["x"]), float(row["y"]), row.get("heading")))
        except (KeyError, TypeError, ValueError):
            continue
    for rows_ in tracks.values():
        rows_.sort(key=lambda r: r[0])
    return {entity: ([r[0] for r in rows_], rows_) for entity, rows_ in tracks.items()}


def position(track, t):
    """Where an entity was at ``t``: between two fixes at most TRACK_GAP apart, else the nearest fix within STALE."""
    if not track:
        return None
    times, rows = track
    i = bisect.bisect_right(times, t)
    before = rows[i - 1] if i > 0 else None
    after = rows[i] if i < len(rows) else None
    if before and after and after[0] - before[0] <= TRACK_GAP and after[0] > before[0]:
        f = (t - before[0]) / (after[0] - before[0])
        return (before[1] + (after[1] - before[1]) * f, before[2] + (after[2] - before[2]) * f, before[3])
    nearest = min((r for r in (before, after) if r), key=lambda r: abs(r[0] - t), default=None)
    if nearest and abs(nearest[0] - t) <= STALE:
        return (nearest[1], nearest[2], nearest[3])
    return None


def _angle_between(ax, ay, bx, by):
    """The unsigned angle in degrees between two direction vectors."""
    na, nb = math.hypot(ax, ay), math.hypot(bx, by)
    if na < 1e-9 or nb < 1e-9:
        return None
    c = max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))
    return math.degrees(math.acos(c))


def cast_samples(doc):
    """Every boss cast of a saved log with its hit and unhit players: ``(key, cast, samples)`` where ``key`` is
    ``(boss name, skill_id)``, ``cast`` describes the cast (``hits``, ``aim`` kind, ``delay``) and each sample is a
    player's geometry at the hit time: distance to the aim point and to the caster, angle off the caster's facing
    (None when the facing is unknown), distance along and across the facing line, whether it was hit, whether it was
    the cast's target."""
    players = {p.get("id") for p in doc.get("players") or [] if isinstance(p, dict)}
    out = []
    for segment in doc.get("segments") or []:
        casts = [c for c in segment.get("npc_casts") or [] if isinstance(c, dict) and isinstance(c.get("t"), (int, float))]
        if not casts:
            continue
        entities = {e.get("id"): e for e in segment.get("entities") or [] if isinstance(e, dict)}
        tracks = _track(segment.get("movement"))
        damage = defaultdict(list)       # boss id -> [(t, target)] sorted
        for e in segment.get("events") or []:
            if e.get("kind") == "damage" and e.get("target") in players and e.get("source") in entities:
                damage[e["source"]].append((float(e["t"]), e["target"]))
        for rows in damage.values():
            rows.sort()
        by_boss = defaultdict(list)
        for c in casts:
            if entities.get(c.get("source"), {}).get("is_boss"):
                by_boss[c["source"]].append(c)
        for boss, boss_casts in by_boss.items():
            boss_casts.sort(key=lambda c: c["t"])
            rows = damage.get(boss) or []
            times = [r[0] for r in rows]
            name = entities[boss].get("name") or boss
            for i, c in enumerate(boss_casts):
                start = c["t"] - 0.05
                end = min(c["t"] + WINDOW, boss_casts[i + 1]["t"] - 0.05 if i + 1 < len(boss_casts) else float("inf"))
                if end <= start:
                    continue
                hits = rows[bisect.bisect_left(times, start):bisect.bisect_right(times, end)]
                if not hits:
                    continue
                hit_time = {}
                for t, target in hits:
                    hit_time.setdefault(target, t)
                t_ref = statistics.median(hit_time.values())
                here = position(tracks.get(boss), c["t"])
                there = position(tracks.get(boss), t_ref) or here     # where the caster was when the hits landed: a leap lands elsewhere
                here = here or there
                if here is None:
                    continue
                bx, by, heading = here
                hx, hy, hheading = there
                target = c.get("target") if c.get("target") in players else None
                if isinstance(c.get("pos"), list) and len(c["pos"]) >= 2:
                    ax, ay = float(c["pos"][0]), float(c["pos"][1])
                elif target and position(tracks.get(target), c["t"]):
                    ax, ay, _ = position(tracks.get(target), c["t"])
                else:
                    ax, ay = bx, by
                facing = c.get("facing")
                if facing is None and heading is not None:
                    facing = heading
                if facing is None and math.hypot(ax - bx, ay - by) > 100:
                    facing = math.degrees(math.atan2(ay - by, ax - bx))
                fx, fy = (math.cos(math.radians(facing)), math.sin(math.radians(facing))) if facing is not None else (None, None)
                # the facing at the hit anchor: the cast's own, else the heading there, else the way from there to a distant aim
                facing2 = c.get("facing")
                if facing2 is None and hheading is not None:
                    facing2 = hheading
                if facing2 is None and math.hypot(ax - hx, ay - hy) > 100:
                    facing2 = math.degrees(math.atan2(ay - hy, ax - hx))
                gx, gy = (math.cos(math.radians(facing2)), math.sin(math.radians(facing2))) if facing2 is not None else (None, None)
                tpos = position(tracks.get(target), c["t"]) if target else None
                aim = ("target" if tpos and math.hypot(ax - tpos[0], ay - tpos[1]) <= NEAR
                       else "self" if math.hypot(ax - bx, ay - by) <= NEAR else "ground")
                samples = []
                for p in players:
                    t_p = hit_time.get(p, t_ref)
                    at = position(tracks.get(p), t_p)
                    if at is None:
                        continue
                    px, py, _ = at
                    d_boss, d_hit = math.hypot(px - bx, py - by), math.hypot(px - hx, py - hy)
                    if min(d_boss, d_hit) > NEAR_FIGHT:
                        continue
                    sample = {"d_aim": math.hypot(px - ax, py - ay), "d_boss": d_boss, "d_hit": d_hit, "hit": p in hit_time,
                              "target": p == target, "angle": None, "along": None, "across": None,
                              "angle_hit": None, "along_hit": None, "across_hit": None}
                    if fx is not None:
                        sample["angle"] = _angle_between(fx, fy, px - bx, py - by)
                        sample["along"] = (px - bx) * fx + (py - by) * fy
                        sample["across"] = abs(-(px - bx) * fy + (py - by) * fx)
                    if gx is not None:
                        sample["angle_hit"] = _angle_between(gx, gy, px - hx, py - hy)
                        sample["along_hit"] = (px - hx) * gx + (py - hy) * gy
                        sample["across_hit"] = abs(-(px - hx) * gy + (py - hy) * gx)
                    samples.append(sample)
                if not samples:
                    continue
                out.append(((name, int(c.get("skill_id") or 0)), {"t": c["t"], "hits": len(hit_time), "aim": aim,
                            "delay": round(t_ref - c["t"], 2), "skill": c.get("skill"), "facing": facing is not None,
                            "moved": round(math.hypot(hx - bx, hy - by))}, samples))
    return out


def _balanced(pred, hit):
    tp = sum(1 for p, h in zip(pred, hit) if p and h)
    tn = sum(1 for p, h in zip(pred, hit) if not p and not h)
    pos = sum(1 for h in hit if h)
    neg = len(hit) - pos
    if not pos or not neg:
        return 0.0
    return (tp / pos + tn / neg) / 2


def _thresholds(values, cap=80):
    """Candidate cut points: midpoints between sorted distinct values, thinned to ``cap``."""
    distinct = sorted(set(round(v, 1) for v in values))
    if len(distinct) < 2:
        return distinct
    mids = [(a + b) / 2 for a, b in zip(distinct, distinct[1:])]
    if len(mids) > cap:
        step = len(mids) / cap
        mids = [mids[int(i * step)] for i in range(cap)]
    return mids


def _top(best, cand):
    """``max`` for the candidate tuples (score first, then the parameters negated so the tighter one wins a tie):
    the first candidate replaces the None-padded start outright. ``max`` on the start would compare a 0.0 score
    with 0.0 and go on to compare a number with None, which is what a candidate that separates hit from unhit
    exactly backwards (a balanced accuracy of 0.0) did to the log server's first pass over 701 recordings."""
    return cand if best[1] is None else max(best, cand)


def fit(samples):
    """The best-separating shape for one skill's pooled samples: ``(shape, params, accuracy, scores)`` where
    ``scores`` holds every candidate's best balanced accuracy."""
    hit = [s["hit"] for s in samples]
    scores, params = {}, {}
    # single target: the cast's target and nobody else
    scores["single_target"] = _balanced([s["target"] for s in samples], hit)
    params["single_target"] = {}
    best = (0.0, None)
    for r in _thresholds([s["d_aim"] for s in samples]):
        best = _top(best, (_balanced([s["d_aim"] <= r for s in samples], hit), -r))
    scores["circle_aim"], params["circle_aim"] = best[0], {"radius": round(-best[1]) if best[1] is not None else None}
    # the shapes around the caster, from where it was at the cast and from where it was when the hits landed (a leap
    # or a charge lands elsewhere); each shape keeps its better anchor, the cast's on a tie
    def keep(shape, score, p):
        margin = 0.01 if p.get("anchor") == "hit" else 0.0        # the hit anchor has to earn its place
        if shape not in scores or score > scores[shape] + margin:
            scores[shape], params[shape] = score, p
    for anchor in ("cast", "hit"):
        sfx = "" if anchor == "cast" else "_hit"
        dist = [s.get("d_hit", s["d_boss"]) if sfx else s["d_boss"] for s in samples]
        best = (0.0, None)
        for r in _thresholds(dist):
            best = _top(best, (_balanced([d <= r for d in dist], hit), -r))
        keep("circle_caster", best[0], {"radius": round(-best[1]) if best[1] is not None else None, "anchor": anchor})
        faced = [(s["hit"], s.get("angle" + sfx, s["angle"]), s.get("along" + sfx, s["along"]), s.get("across" + sfx, s["across"]), d)
                 for s, d in zip(samples, dist)]
        faced = [f for f in faced if f[1] is not None]
        if len(faced) >= 6 and any(f[0] for f in faced) and any(not f[0] for f in faced):
            fhit = [f[0] for f in faced]
            best = (0.0, None, None)
            ranges = _thresholds([f[4] for f in faced], cap=30)
            for a in range(15, 181, 15):
                for R in ranges:
                    best = _top(best, (_balanced([f[1] <= a and f[4] <= R for f in faced], fhit), -a, -R))
            keep("cone", best[0], {"angle": -best[1] if best[1] is not None else None,
                                  "radius": round(-best[2]) if best[2] is not None else None, "anchor": anchor})
            best = (0.0, None, None)
            lengths = _thresholds([f[2] for f in faced if f[2] > 0], cap=30)
            for w in (25, 50, 75, 100, 150, 200, 300, 400, 600):
                for L in lengths:
                    best = _top(best, (_balanced([0 <= f[2] <= L and f[3] <= w for f in faced], fhit), -w, -L))
            keep("line", best[0], {"half_width": -best[1] if best[1] is not None else None,
                                  "length": round(-best[2]) if best[2] is not None else None, "anchor": anchor})
        radii = _thresholds(dist, cap=25)
        best = (0.0, None, None)
        for i, r1 in enumerate(radii):
            for r2 in radii[i + 1:]:
                best = _top(best, (_balanced([r1 <= d <= r2 for d in dist], hit), -(r2 - r1), r1))
        keep("ring", best[0], {"inner": round(best[2]) if best[2] is not None else None,
                              "radius": round(best[2] - best[1]) if best[1] is not None else None, "anchor": anchor})
    # the simplest shape wins unless a more complex one beats it clearly
    chosen = None
    for shape in SHAPES:
        if shape not in scores:
            continue
        if chosen is None or scores[shape] >= scores[chosen] + SIMPLER_BY:
            chosen = shape
    return chosen, params.get(chosen, {}), round(scores.get(chosen, 0.0), 3), {k: round(v, 3) for k, v in scores.items()}


def measure(docs=(), extracted=()):
    """Shape rows for every boss skill the saved logs hold: one row per (boss, skill id), measured from the casts
    that dealt damage, with the sample counts a reader needs to weigh it. ``docs`` are saved-log documents;
    ``extracted`` are per-log lists as ``cast_samples`` returns them (kept from an earlier pass)."""
    pooled = defaultdict(lambda: {"samples": [], "casts": 0, "hits": 0, "aims": defaultdict(int), "delays": [],
                                  "logs": set(), "skill": None, "faced": 0, "moved": 0})
    per_log = [cast_samples(doc) for doc in docs] + [list(rows) for rows in extracted]
    for n, rows in enumerate(per_log):
        for key, cast, samples in rows:
            key = tuple(key)
            row = pooled[key]
            row["samples"].extend(samples)
            row["casts"] += 1
            row["hits"] += cast["hits"]
            row["aims"][cast["aim"]] += 1
            row["delays"].append(cast["delay"])
            row["logs"].add(n)
            row["faced"] += cast["facing"]
            row["moved"] += cast.get("moved", 0) > 100
            row["skill"] = row["skill"] or cast.get("skill")
    out = []
    for (boss, skill_id), row in pooled.items():
        samples = row["samples"]
        hit_n = sum(1 for s in samples if s["hit"])
        unhit_n = len(samples) - hit_n
        if hit_n and unhit_n:
            shape, params, accuracy, scores = fit(samples)
        elif hit_n >= 12 and row["casts"] >= 4 and not unhit_n and row["hits"] >= 2 * row["casts"]:
            # every player present was hit every time, two or more a cast (a lone player proves nothing): a raid-wide
            # effect, nothing to measure the edge of
            shape, params, accuracy, scores = "everyone", {}, 1.0, {"everyone": 1.0}
        else:
            shape, params, accuracy, scores = None, {}, 0.0, {}
        if shape == "everyone":
            confidence = "measured"
        elif row["casts"] >= 8 and hit_n >= 12 and unhit_n >= 12 and accuracy >= 0.85:
            confidence = "measured"
        elif row["casts"] >= 4 and hit_n >= 6 and unhit_n >= 6 and accuracy >= 0.75:
            confidence = "tentative"
        elif row["casts"] >= 8 and hit_n >= 12 and unhit_n >= 12:
            confidence = "unclear"            # plenty of casts, but no candidate shape separates hit from unhit
        else:
            confidence = "insufficient"
        out.append({"boss": boss, "skill_id": skill_id, "skill": row["skill"] or f"Skill {skill_id}",
                    "shape": shape, **params, "accuracy": accuracy, "scores": scores, "confidence": confidence,
                    "casts": row["casts"], "hit": hit_n, "unhit": unhit_n,
                    "hits_per_cast": round(row["hits"] / row["casts"], 2) if row["casts"] else 0,
                    "aim": {k: round(v / row["casts"], 2) for k, v in row["aims"].items()},
                    "delay": round(statistics.median(row["delays"]), 2) if row["delays"] else None,
                    "facing_known": round(row["faced"] / row["casts"], 2) if row["casts"] else 0,
                    "moved": round(row["moved"] / row["casts"], 2) if row["casts"] else 0,
                    "logs": len(row["logs"])})
    order = {"measured": 0, "tentative": 1, "unclear": 2, "insufficient": 3}
    out.sort(key=lambda r: (order[r["confidence"]], r["boss"], -r["casts"]))
    return out


def public_docs(base_url=None, key=None, limit=100, timeout=120, before=None):
    """The newest public logs' raw documents (movement, casts and events included), one at a time."""
    import urllib.request
    from .share import default_server
    base = (base_url or default_server().get("url") or "").rstrip("/")
    if not base:
        return
    key = key or default_server().get("key")

    def _get(path):
        request = urllib.request.Request(base + path, headers={"User-Agent": "Aion2Calc", "Accept": "application/json",
                                                               **({"X-Upload-Key": key} if key else {})})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    try:
        listing = _get(f"/api/v1/logs?limit={int(limit)}" + (f"&before={before}" if before else ""))
    except Exception:
        return
    rows = listing.get("logs", listing) if isinstance(listing, (dict, list)) else []
    for row in rows if isinstance(rows, list) else []:
        log_id = row.get("id") if isinstance(row, dict) else None
        if not log_id or not row.get("boss") or str(row.get("boss")).startswith("Combat"):
            continue
        try:
            yield _get("/api/v1/logs/" + str(log_id) + "/raw")
        except Exception:
            continue


def catalog(rows):
    """The shapes the replay draws: the measured and tentative rows keyed by skill id (a boss skill's id is its
    own; a generic id such as the plain *Attack* is kept per boss)."""
    out = {}
    for row in rows:
        if row["confidence"] not in ("measured", "tentative") or row["shape"] in (None, "single_target", "everyone"):
            continue
        key = str(row["skill_id"]) if row["skill_id"] % 10000 else f"{row['boss']}|{row['skill_id']}"
        if key in out and out[key]["casts"] >= row["casts"]:
            continue
        entry = {k: row[k] for k in ("boss", "skill", "shape", "accuracy", "confidence", "casts", "delay") if k in row}
        for k in ("radius", "angle", "length", "half_width", "inner", "anchor"):
            if row.get(k) is not None:
                entry[k] = row[k]
        out[key] = entry
    import time
    return {"unit": UNIT_NOTE, "meta": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "skills": len(rows),
                                        "measured": sum(1 for r in rows if r["confidence"] == "measured"),
                                        "tentative": sum(1 for r in rows if r["confidence"] == "tentative"),
                                        "sample_version": SAMPLES_VERSION}, "shapes": out}


def report(rows):
    """A Markdown table of the measured shapes, strongest evidence first."""
    lines = ["| Boss | Skill | Shape | Size (units) | Accuracy | Casts | Hit / unhit samples | Hits a cast | Aim | Delay (s) | Caster moved | Logs | Evidence |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        size = ", ".join(f"{k} {r[k]}" for k in ("radius", "angle", "length", "half_width", "inner") if r.get(k) is not None) or "—"
        if r.get("anchor") == "hit":
            size += " (from where the caster was when the hits landed)"
        aim = ", ".join(f"{k} {int(v * 100)}%" for k, v in sorted(r["aim"].items(), key=lambda kv: -kv[1])) or "—"
        lines.append(f"| {r['boss']} | {r['skill']} ({r['skill_id']}) | {r['shape'] or '—'} | {size} | {r['accuracy']:.2f} | {r['casts']} "
                     f"| {r['hit']} / {r['unhit']} | {r['hits_per_cast']} | {aim} | {r['delay'] if r['delay'] is not None else '—'} | {int(r.get('moved', 0) * 100)}% | {r['logs']} | {r['confidence']} |")
    return "\n".join(lines) + "\n"


def load_docs(paths):
    """Saved logs from files and folders (``*.a2log.json`` and ``*.json`` documents with segments)."""
    from pathlib import Path
    for raw in paths:
        p = Path(raw)
        files = sorted(p.rglob("*.json")) if p.is_dir() else [p]
        for f in files:
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and isinstance(doc.get("segments"), list):
                yield doc


def write_outputs(rows, static_dir, docs_dir):
    """The replay's catalog (static/aoe-shapes.json) and the findings table (docs/generated/aoe-shapes.md)."""
    from pathlib import Path
    cat = catalog(rows)
    out = Path(static_dir) / "aoe-shapes.json"
    out.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    md = Path(docs_dir) / "aoe-shapes.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    head = ("# Boss area-of-effect shapes, measured from recordings\n\n"
            "Generated by `python -m aion2calc aoe-shapes --write`. For each boss cast that dealt damage, where every player "
            "stood when the damage landed and who was hit; the shape that separates hit from unhit best, with its size in "
            f"{UNIT_NOTE} (a cone's angle is its half-angle from the facing, a line's half_width the reach either side of "
            "its centre line, a ring runs from inner to radius around the caster; a shape *from where the caster was when the hits landed* is anchored there rather than at the cast, as a leap or charge lands elsewhere, and *Caster moved* is the share of casts in which the caster was over a metre from its cast position when the hits landed). *measured*: 8+ casts, 12+ hit and 12+ unhit "
            "samples, accuracy 0.85+; *tentative*: 4+ casts, 6+ and 6+, 0.75+; *unclear*: enough samples but no shape "
            "separates the hit from the unhit (the drawn aim may not be the effect's place, or the hits come late); the rest "
            "is *insufficient*. *everyone* is a raid-wide effect that hit the whole party wherever it stood. Only measured and "
            "tentative shapes are drawn.\n\n")
    md.write_text(head + report(rows), encoding="utf-8")
    return out, md
