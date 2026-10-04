"""Scraper for A2DIL (a2dil.com) 60-second training-dummy logs (Korean service).

The public ranking pages expose per-hit timelines of the top dummy runs for
each class.  We use them as a reference for damage shares, buff uptimes and
which specializations top players actually run.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import urllib.parse

from .http import fetch

BASE = "https://a2dil.com"
KR_CLASS = {"gladiator": "검성", "templar": "수호성", "assassin": "살성", "ranger": "궁성",
            "sorcerer": "마도성", "spiritmaster": "정령성", "cleric": "치유성",
            "chanter": "호법성", "brawler": "권성"}


def record_ids(cls: str) -> list[str]:
    job = urllib.parse.quote(KR_CLASS[cls])
    h = fetch(f"{BASE}/training-rankings?job={job}&band=all&support=all", max_age=86400)
    return sorted(set(re.findall(r"/training-rankings/([0-9a-f-]{36})", h)))


def record(rec_id: str) -> dict:
    h = fetch(f"{BASE}/training-rankings/{rec_id}", max_age=30 * 86400)
    m = re.search(r'<script type="application/json" data-training-timeline-data>(.*?)</script>', h, re.S)
    tl = json.loads(m.group(1)) if m else {"skills": [], "buffs": []}
    specs = {}
    for row in re.findall(r'<tr style="--skill-damage-share.*?</tr>', h, re.S):
        sid = re.search(r"skill-thumbnails/(\d+)\.", row)
        sp = re.search(r'aria-label="특화 ([^"]*)"', row)
        if sid:
            specs[sid.group(1)] = sp.group(1) if sp else ""
    txt = htmllib.unescape(re.sub(r"<[^>]+>", "\n", re.sub(r"<script.*?</script>", "", h, flags=re.S)))
    header = {}
    for key in ["타수", "치명", "강타", "완벽", "다단", "DPS", "전방", "후방"]:
        mm = re.search(r"\n" + key + r"\n\s*([\d.,%]+)", txt)
        if mm:
            header[key] = mm.group(1)
    cp = re.search(r"전투력 (\d+)", txt)
    skills = []
    for s in tl.get("skills", []):
        pts = s["usagePoints"]
        skills.append({
            "code": s.get("baseCode"), "name": s["name"], "hits": len(pts),
            "damage": sum(p["damage"] for p in pts),
            "dot_hits": sum(1 for p in pts if p["isDamageOverTime"]),
            "crit": _rate(pts, "isCritical"), "double": _rate(pts, "isHard"),
            "perfect": _rate(pts, "isPerfect"),
            "multi": _rate(pts, "multiCount", lambda v: v > 0),
            "specs": specs.get(str(s.get("baseCode"))),
        })
    buffs = [{"name": b["name"], "uptime": b["uptimePercent"]} for b in tl.get("buffs", [])]
    return {"id": rec_id, "combat_power_k": int(cp.group(1)) if cp else None,
            "header": header, "skills": skills, "buffs": buffs}


def _rate(points, key, pred=bool):
    if not points:
        return 0.0
    return sum(1 for p in points if pred(p.get(key))) / len(points)


def class_summary(cls: str, limit: int = 10) -> dict:
    recs = [record(r) for r in record_ids(cls)[:limit]]
    agg: dict[str, dict] = {}
    for r in recs:
        tot = sum(s["damage"] for s in r["skills"]) or 1
        for s in r["skills"]:
            a = agg.setdefault(s["name"], {"code": s["code"], "share": [], "hits": [], "specs": []})
            a["share"].append(s["damage"] / tot)
            a["hits"].append(s["hits"])
            if s["specs"]:
                a["specs"].append(s["specs"])
    summary = {}
    for name, a in agg.items():
        n = len(recs)
        summary[name] = {"code": a["code"], "mean_share": sum(a["share"]) / n,
                         "mean_hits_per_min": sum(a["hits"]) / n,
                         "spec_modes": _mode(a["specs"])}
    return {"class": cls, "records": len(recs), "skills": summary, "raw": recs}


def _mode(xs):
    counts: dict[str, int] = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:3]
