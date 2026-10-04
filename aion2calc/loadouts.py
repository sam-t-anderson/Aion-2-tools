"""Build 'global median' loadouts for every class from metabot's top-player gear stats.

All classes wear the same armor / accessory families at level 45 (metabot shows
the same items across classes), so only the main-hand weapon changes.  The
weapon is the class's most-used main hand among top tracked characters, at its
average enchant level, with stats from the global item table.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .kit.base import load_class
from .scrape import metabot

LOADOUTS = Path(__file__).resolve().parent / "data" / "global" / "loadouts"
TEMPLATE = "sorcerer_l45_global_median"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")


def _weapon_stats(slug: str, enchant: float) -> dict:
    it = metabot.item(slug)
    fixed = it.get("fixed", {})
    lo = hi = 0.0
    m = re.match(r"([\d,]+)–([\d,]+)", fixed.get("Max Attack", ""))
    if m:
        lo, hi = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
    per = 5.0
    if it.get("enchant"):
        mm = re.search(r"Max Attack (\d+)", it["enchant"][0]["stats"])
        if mm:
            per = float(mm.group(1))
    e = round(enchant)
    crit = float(fixed.get("Critical Hit", "0").replace("+", "").replace(",", "") or 0)
    acc = float(fixed.get("Accuracy", "0").replace("+", "").replace(",", "") or 0)
    return {"weapon_min": lo + per * e, "weapon_max": hi + per * e, "crit": crit, "accuracy": acc}


def make_loadout(cls: str, write: bool = True, user: bool = False) -> dict:
    """``user=True`` writes into the user data overlay (launch-time sync) instead of the package."""
    from .paths import read_json, write_user_json
    tmpl = read_json("global", "loadouts", f"{TEMPLATE}.json")
    lo = copy.deepcopy(tmpl)
    lo["name"] = f"Global L45 {cls.capitalize()} - median of top tracked characters (metabot)"
    tp = load_class(cls).get("top_players", {})
    main = (tp.get("gear", {}).get("Main hand") or [{}])[0]
    if main.get("item"):
        stats = _weapon_stats(_slug(main["item"]), main.get("avg_enchant") or 10)
        for comp in lo["components"]:
            if comp["slot"] == "Main hand":
                comp["item"] = f"{main['item']} +{round(main.get('avg_enchant') or 10)}"
                comp["source"] = "metabot global item table, class's most used main hand"
                comp["stats"] = stats
    deity = tp.get("deity_stats", {})
    prim = tp.get("primary_stats", {})
    if deity or prim:
        names = {"Destruction [Zikel]": "destruction", "Death [Triniel]": "death", "Wisdom [Lumiel]": "wisdom",
                 "Justice [Nezekan]": "justice", "Time [Siel]": "time", "Illusion [Kaisinel]": "illusion",
                 "Freedom [Vaizel]": "freedom", "Might": "might", "Precision": "precision"}
        st = {}
        for k, v in {**prim, **deity}.items():
            if k in names:
                st[names[k]] = v
        for comp in lo["components"]:
            if comp["slot"] == "Primary/deity stats":
                comp["stats"] = st
    if write and user:
        write_user_json(lo, "global", "loadouts", f"{cls}_l45_global_median.json")
    elif write:
        (LOADOUTS / f"{cls}_l45_global_median.json").write_text(json.dumps(lo, indent=1), encoding="utf-8")
    return lo


def make_all(classes=None, user: bool = False, verbose: bool = True):
    for cls in classes or metabot.CLASSES:
        if cls == "sorcerer":          # hand-built template
            continue
        lo = make_loadout(cls, user=user)
        if verbose:
            print(cls, lo["components"][0]["item"], lo["components"][0]["stats"])
