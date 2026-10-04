"""Scraper for metabot.gg's AION 2 pages.

metabot reads the **global** game client, so it is the primary source for
global-launch values: skill coefficients per level, specializations, skill and
stigma point budgets, Daevanion boards, item stats, titles, and live usage
statistics of the top tracked level-45 characters per class.
"""
from __future__ import annotations

import re

from .http import fetch
from .rsc import find_object, flight, text_lines

BASE = "https://metabot.gg/en/aion-2"
CLASSES = ["gladiator", "templar", "assassin", "ranger",
           "sorcerer", "spiritmaster", "cleric", "chanter"]


def class_data(cls: str, fresh: bool = False) -> dict:
    """Skills, budgets, Daevanion boards and base stats for one class (``fresh`` skips the page cache)."""
    age = 0 if fresh else 7 * 86400
    build_data = flight(fetch(f"{BASE}/classes/{cls}/build", max_age=age))
    build = find_object(build_data, '{"skills":[{"id":')
    daev = find_object(flight(fetch(f"{BASE}/daevanion/{cls}", max_age=age)), '{"boards":[')
    class_page = flight(fetch(f"{BASE}/classes/{cls}", max_age=age))
    base_stats = _base_stats(class_page)
    return {
        "class": cls,
        "source": f"{BASE}/classes/{cls}/build",
        "skills": build["skills"],
        "budget": build["budget"],
        "level_cap": build["levelCap"],
        "spec_slots": build["specSlots"],
        "stigma_slot_levels": build["stigmaSlotLevels"],
        "daevanion_map": build["daevanionMap"],
        "preset": build.get("preset"),
        "boards": daev["boards"],
        "stat_labels": daev.get("statLabels", {}),
        "base_stats": base_stats,
        "top_players": parse_top_players(text_lines(build_data), cls),
    }


def _base_stats(data: str) -> dict:
    i = data.find('"children":"Level"}]')
    seg = data[max(0, i - 200): i + 12000]
    pat = (r'\["\$","tr","\d+",\{"children":\[\["\$","th","0",\{"scope":"row",'
           r'"className":"\$undefined","children":"(\d+)"\}\],'
           r'\["\$","td","1",\{[^}]*"children":"([\d,]+)"\}\],'
           r'\["\$","td","2",\{[^}]*"children":"([\d,]+)"\}\],'
           r'\["\$","td","3",\{[^}]*"children":"([\d,]+)"\}\]')
    out = {}
    for lvl, hp, dfn, atk in re.findall(pat, seg):
        out[lvl] = {"hp": int(hp.replace(",", "")), "defense": int(dfn.replace(",", "")),
                    "attack": int(atk.replace(",", ""))}
    return out


_PCT = re.compile(r"^([\d.]+)%$")
_NUM = re.compile(r"^[\d,]+$")


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("%", "").replace("+", ""))


def parse_top_players(lines: list[str], cls: str) -> dict:
    """Turn the 'What top <Class> players run' section into structured data."""
    title = cls.capitalize()
    try:
        start = lines.index(f"What top {title} players run")
    except ValueError:
        return {}
    L = lines[start:]
    out: dict = {"skills": {}, "passives": {}, "stigmas": {}, "skill_nodes": {},
                 "gear": {}, "enchant": {}, "arcana": {}, "titles": {}, "wings": [],
                 "pets": [], "primary_stats": {}, "deity_stats": {}}

    def after(label, default=None):
        try:
            return L[L.index(label) + 1]
        except ValueError:
            return default

    for key, label in [("tracked", "Top players tracked"), ("median_cp", "Median combat power"),
                       ("top10_cp", "Top 10% from"), ("avg_item_level", "Avg. item level")]:
        v = after(label)
        if v and _NUM.match(v):
            out[key] = _num(v)

    def triples(i, stop_words):
        res = []
        while i + 2 < len(L) and L[i] not in stop_words:
            name, pct, extra = L[i], L[i + 1], L[i + 2]
            if _PCT.match(pct):
                res.append((name, _num(pct), extra))
                i += 3
            else:
                i += 1
        return res, i

    def lv(extra):
        m = re.search(r"(\d+(?:\.\d+)?)", extra)
        return float(m.group(1)) if m else None

    if "Active skills on the bar" in L:
        i = L.index("Active skills on the bar") + 1
        res, i = triples(i, {"Passive skills"})
        out["skills"] = {n: {"pick": p, "avg_level": lv(x)} for n, p, x in res}
        res, i = triples(i + 1, {"Load the most common build in the planner"})
        out["passives"] = {n: {"pick": p, "avg_level": lv(x)} for n, p, x in res}
    head = f"Most used {title} stigmas"
    if head in L:
        i = L.index(head) + 3
        res, _ = triples(i, {f"Daevanion picks of top {title} players"})
        out["stigmas"] = {n: {"pick": p, "avg_level": lv(x)} for n, p, x in res}
    if "Most picked skill nodes" in L:
        i = L.index("Most picked skill nodes") + 1
        while i + 1 < len(L) and _PCT.match(L[i + 1]):
            out["skill_nodes"][L[i]] = _num(L[i + 1])
            i += 2
    slots = ["Main hand", "Off-hand", "Helmet", "Shoulders", "Chest", "Legs", "Gloves",
             "Boots", "Cape", "Necklace", "Earring", "Ring", "Bracelet", "Belt", "Amulet", "Rune"]
    gear_head = f"Most used {title} gear by slot"
    if gear_head in L:
        i = L.index(gear_head) + 3
        end = L.index("Enchant levels by slot") if "Enchant levels by slot" in L else len(L)
        cur = None
        while i < end:
            if L[i] in slots:
                cur = L[i]
                out["gear"][cur] = []
                i += 1
                continue
            if cur and i + 2 < end and _PCT.match(L[i + 1]):
                out["gear"][cur].append({"item": L[i], "pick": _num(L[i + 1]),
                                         "avg_enchant": lv(L[i + 2])})
                i += 3
            else:
                i += 1
        i = end + 3
        while i + 2 < len(L) and L[i] != "Arcana by slot":
            if L[i] in slots and L[i + 1].startswith("avg."):
                out["enchant"][L[i]] = {"avg": lv(L[i + 1]), "mode": L[i + 2]}
                i += 3
            else:
                i += 1
    if "Arcana by slot" in L:
        i = L.index("Arcana by slot") + 2
        cur = None
        while i < len(L) and L[i] != "Titles, wings and pets":
            if L[i].startswith("Arcana slot"):
                cur = L[i]
                out["arcana"][cur] = []
                i += 1
            elif cur and i + 2 < len(L) and _PCT.match(L[i + 1]):
                out["arcana"][cur].append({"item": L[i], "pick": _num(L[i + 1]),
                                           "avg_enchant": lv(L[i + 2])})
                i += 3
            else:
                i += 1
    for tslot in ["Attack title", "Defense title", "Other title"]:
        if tslot in L:
            i = L.index(tslot) + 1
            res = []
            while i + 1 < len(L) and _PCT.match(L[i + 1]):
                res.append({"title": L[i], "pick": _num(L[i + 1])})
                i += 2
            out["titles"][tslot] = res
    for sec, key in [("Wings", "wings"), ("Pets", "pets")]:
        if sec in L:
            i = L.index(sec) + 1
            while i + 2 < len(L) and _PCT.match(L[i + 1]):
                out[key].append({"name": L[i], "pick": _num(L[i + 1]), "extra": L[i + 2]})
                i += 3
    for sec, key, stop in [("Primary stats", "primary_stats", "Deity stats"),
                           ("Deity stats", "deity_stats", f"Top 10 {title} players")]:
        if sec in L:
            i = L.index(sec) + 1
            while i + 1 < len(L) and L[i] != stop:
                try:
                    out[key][L[i]] = float(L[i + 1])
                    i += 2
                except ValueError:
                    i += 1
    return out


def item(slug: str, cache: bool = True) -> dict:
    """Fixed stats, random stat pool and enchant table of a global item."""
    lines = text_lines(flight(fetch(f"{BASE}/items/{slug}", cache=cache)))
    return _parse_item(lines, slug)


def item_full(slug: str, cache: bool = False) -> dict:
    """Everything the planner database stores about one item page."""
    html = fetch(f"{BASE}/items/{slug}", cache=cache)
    lines = text_lines(flight(html))
    out = _parse_item(lines, slug)
    out["skill_pools"] = _skill_pools(lines)
    sb = next((k for k, x in enumerate(lines) if x.endswith(" set bonus")), None)
    if sb is not None:
        bonuses = {}
        for k in range(sb, min(sb + 40, len(lines) - 1)):
            m = re.fullmatch(r"(\d+) pieces?", lines[k])
            if m:
                bonuses[int(m.group(1))] = lines[k + 1]
        out["set"] = {"name": lines[sb][: -len(" set bonus")], "bonuses": bonuses}
    ld = next((x for x in lines if x.startswith('{"@context"') and '"Thing"' in x), None)
    if ld:
        import json as _json
        try:
            j = _json.loads(ld)
            out["name"] = j.get("name")
            out["icon"] = j.get("image")
            out["description"] = j.get("description")
        except ValueError:
            pass
    name = out.get("name")
    if name and name in lines:
        i = lines.index(name)
        head = lines[i:i + 8]
        grades = {"Common", "Rare", "Legend", "Unique", "Epic", "Mythic", "Special"}
        out["grade"] = next((x for x in head if x in grades), None)
        lvl = next((x for x in head if x.startswith("Item Level ")), None)
        out["item_level"] = int(lvl.split()[-1]) if lvl and lvl.split()[-1].isdigit() else None
        if out["grade"]:
            gi = head.index(out["grade"])
            out["category"] = head[gi + 1] if gi + 1 < len(head) and not head[gi + 1].startswith("Item Level") \
                else out["meta"].get("Category")
    out.setdefault("category", out["meta"].get("Category"))
    return out


def category_slugs(category: str) -> list[str]:
    """Item slugs listed on a metabot category page (weapons, armor, accessories, arcana, godstones)."""
    h = fetch(f"{BASE}/{category}", max_age=86400)
    return sorted(set(re.findall(r'/en/aion-2/items/([a-z0-9-]+)', h)))


def sitemap(name: str) -> dict[str, str]:
    """{english url: lastmod} from one metabot sitemap."""
    sm = fetch(f"https://metabot.gg/sitemaps/{name}.xml", max_age=3600)
    return {u: m for u, m in re.findall(r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?", sm)
            if "/en/" in u}


def _parse_item(lines: list[str], slug: str) -> dict:
    out: dict = {"slug": slug, "fixed": {}, "random": [], "enchant": [], "meta": {}}
    try:
        i = next(k for k, s in enumerate(lines) if s.startswith("Fixed stats come with every copy"))
    except StopIteration:
        return out
    # meta block (grade, category, item level, ...) precedes "Stats"
    j = max(0, i - 40)
    meta = lines[j:i]
    for key in ["Category", "Item Level", "Required Level", "Max enhance", "Class"]:
        if key in meta:
            out["meta"][key] = meta[meta.index(key) + 1]
    k = i + 1
    stops = ("Attack range", "Sockets", "Random stats", "Enhancement levels", "Random skill options",
             "Similar items", "Pieces")
    while k + 1 < len(lines) and not lines[k].startswith(stops) \
            and not lines[k].endswith("used by top players") and not lines[k].endswith("set bonus"):
        name, val = lines[k], lines[k + 1]
        if re.match(r"^[+\-]?[\d,.]+(%|–[\d,.]+)?$", val) or re.match(r"^[\d,]+–[\d,]+$", val):
            out["fixed"][name] = val
            k += 2
            if k < len(lines) and "of the best" in lines[k]:
                k += 1
        else:
            k += 1
    if "Roll chance" in lines[k:k + 40]:
        k = lines.index("Roll chance", k) + 1
        while k + 2 < len(lines) and re.match(r"^[+\-]", lines[k + 1]):
            out["random"].append({"stat": lines[k], "range": lines[k + 1], "chance": lines[k + 2]})
            k += 3
    for m, s in enumerate(lines):
        if re.match(r"^\+\d+ → \+\d+$", s):
            # the stat line follows the cost columns; find the first line with a stat label
            for t in lines[m + 1:m + 14]:
                if re.search(r"(Attack|Defense|HP|Penetration|Damage|Tolerance|Boost)", t) \
                        and not t.startswith("Enhance Stone"):
                    out["enchant"].append({"step": s, "stats": t})
                    break
    return out


def titles(fresh: bool = False) -> list[dict]:
    lines = text_lines(flight(fetch(f"{BASE}/titles", max_age=0 if fresh else 7 * 86400)))
    grades = {"Common", "Rare", "Epic", "Unique", "Legend", "Legendary", "Mythic", "Special"}
    facs = {"Both factions", "Elyos", "Asmodian"}
    out, seen = [], set()
    for i in range(len(lines) - 4):
        if lines[i + 1] in grades and lines[i + 2] in facs:
            key = (lines[i], lines[i + 2])
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": lines[i], "grade": lines[i + 1], "faction": lines[i + 2],
                        "equip": lines[i + 3], "owned": lines[i + 4]})
    return out


def _skill_pools(lines: list[str]) -> dict:
    """Parse an item page's "Random skill options" table: {class: {max_level, chance, skills}}."""
    out: dict = {}
    try:
        i = lines.index("Random skill options")
    except ValueError:
        return out
    names = {c.capitalize(): c for c in CLASSES}
    names["Spiritmaster"] = "spiritmaster"
    k = i + 1
    while k < len(lines) and not lines[k].startswith("Similar items"):
        if lines[k] in names and k + 1 < len(lines) and "skills" in lines[k + 1]:
            cls = names[lines[k]]
            head = " ".join(lines[k + 1:k + 4])
            m = re.search(r"up to Lv\. (\d+)", head)
            ch = re.search(r"([\d.]+)% each", head)
            j = k + 1
            while j < len(lines) and not lines[j].startswith("up to Lv."):
                j += 1
            skills, chances = [], {}
            j += 1
            while j < len(lines) and lines[j] not in names and not lines[j].startswith("Similar items"):
                pc = re.fullmatch(r"([\d.]+)%", lines[j])
                if pc and skills:                      # per-skill chance follows the skill name
                    chances[skills[-1]] = float(pc.group(1)) / 100
                elif lines[j].strip():
                    skills.append(lines[j])
                j += 1
            even = float(ch.group(1)) / 100 if ch else (1 / len(skills) if skills else None)
            out[cls] = {"max_level": int(m.group(1)) if m else None,
                        "chances": {sk: chances.get(sk, even) for sk in skills}, "skills": skills}
            k = j
        else:
            k += 1
    return out


def item_skill_pools(slug: str) -> dict:
    """Random skill option pools of one item (arcana, accessories)."""
    return _skill_pools(text_lines(flight(fetch(f"{BASE}/items/{slug}"))))


#: The five arcana slots; Chalice, Parchment and Compass roll active skills,
#: Bell and Mirror roll passives (official guide; the pools below confirm it).
ARCANA_SLOTS = ("chalice", "parchment", "compass", "bell", "mirror")


def arcana_skill_pools() -> dict:
    """{arcana slug: {class: pool}} for every Unique arcana found in the sitemap."""
    sm = fetch("https://metabot.gg/sitemaps/aion-2-items-1.xml", max_age=86400)
    slugs = re.findall(r"<loc>https://metabot.gg/en/aion-2/items/([^<]+)</loc>", sm)
    arc = sorted(x for x in slugs if re.fullmatch(r"(%s)-of-[a-z]+" % "|".join(ARCANA_SLOTS), x))
    return {slug: item_skill_pools(slug) for slug in arc}
