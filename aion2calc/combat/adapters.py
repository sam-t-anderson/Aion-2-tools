"""Combat log sources -> one canonical encounter format.

Canonical encounter (plain JSON, stored in the local DB)::

    {"meta":  {"source", "ref", "class", "player", "target", "duration", "total", "dps",
               "started_at", "combat_power", "notes"},
     "hits":  [{"t": seconds, "skill_id", "skill", "damage", "crit", "double", "perfect",
                "multi", "dot", "front", "back"}],
     "buffs": [{"name", "skill_id", "uptime", "windows": [[start, end], ...]}],
     "specs": {"<skill name>": "1, 4, 5"}}

Sources
    * A2DIL training-dummy logs (Korean service, public): ``from_a2dil``
    * any tool that can export JSON in the format above, or CSV with the columns
      ``t, skill, damage, crit, double, perfect, multi, dot`` (``from_json``/``from_csv``)
    * a live packet capture can feed the same format through ``live.LiveSource``
"""
from __future__ import annotations

import csv
import io
import json
import re

from ..kit.base import ClassData
from ..scrape.metabot import CLASSES


def _class_of(skill_ids: list[int]) -> str | None:
    best, hits = None, 0
    for cls in CLASSES:
        try:
            ids = set(ClassData(cls).skills)
        except Exception:
            continue
        n = sum(1 for s in skill_ids if s in ids)
        if n > hits:
            best, hits = cls, n
    return best


#: hits some logs record without a skill id (chain follow-ups), Korean name -> label
KR_ALIASES = {"작렬": "Flame Arrow (Burst)", "열화": "Flame Arrow (Pyroclasm)"}


def _english(cls: str | None, sid, fallback: str) -> str:
    if not sid and fallback in KR_ALIASES:
        return KR_ALIASES[fallback]
    if cls and sid:
        try:
            sk = ClassData(cls).skills.get(int(sid))
            if sk:
                return sk["name"]
        except Exception:
            pass
    return fallback


def normalize(enc: dict) -> dict:
    """Fill derived meta (duration, total, dps, class, English names); sort hits."""
    hits = sorted(enc.get("hits", []), key=lambda h: h["t"])
    meta = enc.setdefault("meta", {})
    if not meta.get("class"):
        meta["class"] = _class_of([h.get("skill_id") for h in hits if h.get("skill_id")])
    for h in hits:
        h["skill"] = _english(meta.get("class"), h.get("skill_id"), h.get("skill") or str(h.get("skill_id")))
        for k in ("crit", "double", "perfect", "dot", "front", "back"):
            h[k] = bool(h.get(k))
        h["multi"] = int(h.get("multi") or 0)
        h["damage"] = float(h.get("damage") or 0)
    for b in enc.get("buffs", []):
        b["name"] = _english(meta.get("class"), b.get("skill_id"), b.get("name", ""))
    total = sum(h["damage"] for h in hits)
    dur = meta.get("duration") or ((hits[-1]["t"] - hits[0]["t"]) if len(hits) > 1 else 1.0)
    meta.update({"duration": dur, "total": total, "dps": total / dur if dur else 0.0})
    enc["hits"] = hits
    enc.setdefault("buffs", [])
    enc.setdefault("specs", {})
    return enc


def from_a2dil(ref: str) -> dict:
    """A2DIL record id or URL (https://a2dil.com/training-rankings/<uuid>)."""
    from ..scrape.http import fetch
    rid = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", ref)
    if not rid:
        raise ValueError("not an A2DIL record id or URL")
    rid = rid.group(1)
    html = fetch(f"https://a2dil.com/training-rankings/{rid}", max_age=30 * 86400)
    m = re.search(r'<script type="application/json" data-training-timeline-data>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("record has no timeline data")
    tl = json.loads(m.group(1))
    from ..scrape.a2dil import record
    rec = record(rid)
    hits = []
    for s in tl.get("skills", []):
        for p in s.get("usagePoints", []):
            hits.append({"t": p["elapsedMilliseconds"] / 1000, "skill_id": s.get("baseCode"),
                         "skill": s.get("name"), "damage": p["damage"], "crit": p.get("isCritical"),
                         "double": p.get("isHard"), "perfect": p.get("isPerfect"),
                         "multi": p.get("multiCount") or 0, "dot": p.get("isDamageOverTime"),
                         "front": p.get("isFront"), "back": p.get("isBack")})
    buffs = []
    for b in tl.get("buffs", []):
        code = re.search(r"(\d+)", b.get("key", ""))
        buffs.append({"name": b.get("name"), "skill_id": int(code.group(1)) if code else None,
                      "uptime": (b.get("uptimePercent") or 0) / 100,
                      "windows": [[w["startedAtMilliseconds"] / 1000, w["endedAtMilliseconds"] / 1000]
                                  for w in b.get("activeWindows", [])]})
    specs = {}
    for s in rec.get("skills", []):
        if s.get("specs"):
            specs[str(s.get("code"))] = s["specs"]
    enc = {"meta": {"source": "a2dil", "ref": rid, "target": "Training dummy",
                    "duration": tl.get("durationMilliseconds", 60000) / 1000,
                    "combat_power": (rec.get("combat_power_k") or 0) * 1000 or None,
                    "notes": ["Korean service training-dummy log (A2DIL)"]},
           "hits": hits, "buffs": buffs, "specs": specs}
    enc = normalize(enc)
    cls = enc["meta"]["class"]
    enc["specs"] = {_english(cls, k, k): v for k, v in specs.items()}
    return enc


def from_json(text: str) -> dict:
    return normalize(json.loads(text))


def from_csv(text: str, meta: dict | None = None) -> dict:
    rows = csv.DictReader(io.StringIO(text))
    hits = []
    for r in rows:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("damage"):
            continue
        hits.append({"t": float(r.get("t") or r.get("time") or 0), "skill": r.get("skill") or r.get("name"),
                     "skill_id": int(r["skill_id"]) if r.get("skill_id", "").isdigit() else None,
                     "damage": float(r["damage"].replace(",", "")),
                     **{k: r.get(k, "").lower() in ("1", "true", "yes", "y") for k in ("crit", "double", "perfect",
                                                                                        "dot", "front", "back")},
                     "multi": int(r.get("multi") or 0)})
    return normalize({"meta": {"source": "csv", **(meta or {})}, "hits": hits})


def load(path_or_ref: str) -> dict:
    """A2DIL URL/id, a .json file or a .csv file."""
    if "a2dil" in path_or_ref or re.fullmatch(r"[0-9a-f-]{36}", path_or_ref):
        return from_a2dil(path_or_ref)
    with open(path_or_ref, encoding="utf-8") as f:
        text = f.read()
    return from_csv(text, {"ref": path_or_ref}) if path_or_ref.lower().endswith(".csv") else from_json(text)
