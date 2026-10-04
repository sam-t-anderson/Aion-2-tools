"""Scraper for gamers4.life's AION 2 database (Korean live-service data).

Used as a fallback / supplement to the global client data: per-skill hit counts
and PvP coefficients live in its skill detail pages, and its build calculator /
Daevanion planner accept share links we generate for screenshots.
"""
from __future__ import annotations

import html as htmllib
import json
import re

from .http import fetch
from .rsc import flight, rows

BASE = "https://gamers4.life/aion-2/database"


def class_skill_ids(cls: str) -> list[str]:
    data = flight(fetch(f"{BASE}/en/classes/{cls}/"))
    for r in rows(data).values():
        if '"skills":[{"id":' in r and "BuildCalculator" not in r[:40]:
            m = re.search(r'"skills":(\[.*?\]),"stigmaMax"', r)
            if m:
                return [s["id"] for s in json.loads(m.group(1)) if s.get("cls") == cls]
    return []


def skill_detail(skill_id: str) -> dict:
    """Record fields + JSON detail blocks (levels, specializations, placeholders)."""
    h = fetch(f"{BASE}/en/skill/{skill_id}/")
    out: dict = {"id": skill_id}
    m = re.search(r'<h2>Record fields</h2>\s*<div class="table">(.*?)</div>\s*</div>', h, re.S)
    if m:
        kv = re.findall(r'<div class="k">(.*?)</div><div class="v">(.*?)</div>', m.group(1), re.S)
        out["record"] = {k: htmllib.unescape(v) for k, v in kv}
    for name, pre in re.findall(r"<summary>([^<]+)</summary><pre>(.*?)</pre>", h, re.S):
        try:
            out[name] = json.loads(htmllib.unescape(pre))
        except Exception:
            out[name] = htmllib.unescape(pre)
    t = re.search(r"<title>(.*?)</title>", h)
    out["name"] = htmllib.unescape(t.group(1)).split(" - ")[0] if t else skill_id
    return out


def hit_profile(detail: dict) -> dict:
    """Summarise the damage placeholders of a skill: hits, coefficients, PvP values."""
    dd = detail.get("descriptionData") or {}
    out = {}
    for key, ph in (dd.get("placeholders") or {}).items():
        base = (ph.get("base") or {}).get("values") or []
        if ph.get("type") == "se_dmg" and len(base) > 4:
            eff = key.split(":")[1]
            out[eff] = {"flat_l1": _f(base[0]), "coef": _f(base[2]) / 100.0,
                        "hits": int(_f(base[4]) or 1),
                        "pvp_coef": _f(base[23]) / 100.0 if len(base) > 23 else None}
        elif ph.get("type") == "abe" and len(base) > 6 and base[1] == "TRUE":
            eff = key.split(":")[1]
            out[eff + ":dot"] = {"interval_ms": _f(base[0]), "flat_l1": _f(base[3]),
                                 "coef": _f(base[5]) / 100.0}
    return out


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def daevanion(cls: str) -> list:
    return json.loads(fetch(f"{BASE}/db/daevanion/{cls}.json"))


def gear_db(lang: str = "en") -> list:
    return json.loads(fetch(f"{BASE}/db/gear/{lang}.json", max_age=30 * 86400))
