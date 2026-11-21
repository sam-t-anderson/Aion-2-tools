"""An analyzed encounter's words (0.2.456), as pages/combat.js and pages/parse.js write them: a fight imported from an
AbyssLogs or A2DIL link, or from a file, broken down for one player. Its page shows the encounter's parse card, the
buffs' uptime and idle gaps, the comparison with the optimal rotation, and the comparison with the class's top logs.

The parse card (``renderParse``) is shared with the Live Meter. It is fed a normalized fight (``parseFromEncounter``
here), so a saved log and a live snapshot read the same.
"""
from __future__ import annotations

import math

from .results import _dict, _list, _number, _truthy, cap, e, js_text, n0, pct
from .theme import fixed, js_round, kfmt

#: Each of the five largest skills' colour on the donut, then the rest's (``PCOL``).
PALETTE = ("#e8cf8e", "#58a6ff", "#b18cff", "#6fcf7a", "#e68a5a", "#5ad1c4", "#e45a8a", "#d7c15a", "#8a92a8")
EMPTY_DONUT = "#2a3045"
SKILL_ART = "https://metabot.gg/web/aion2/skills/{}.webp"
TABS = (("dps", "DPS"), ("def", "Defense"), ("acc", "Accuracy"))
ACCURACY_NOTE = ("Rates use decoded outgoing hits. Hit chance requires attempted attacks and misses, which this source "
                 "does not currently provide.")
DEFENSE_NOTE = ("Damage received and the parry, shield block and Endurance flags are measured from decoded hits. Avoided "
                "attacks and pre-mitigation damage are unavailable; armor, mitigation and dodge percentages cannot be "
                "inferred from received damage alone.")
NO_INCOMING = "This source does not provide incoming-damage events."
NO_SKILLS = "No skills recorded."
SKILL_COLUMNS = ["Skill", "Hit", "DPS", "Avg", "Min", "Max", "Damage"]
OPTIMAL_COLUMNS = ["Skill", "Your share", "Optimal share", "Your casts", "Optimal casts"]
SPEC_COLUMNS = ["Skill", "In this log", "Optimized build"]
TOP_COLUMNS = ["Skill", "You", "Top logs", "Hits/min", "Top hits/min"]
LOADING = "Loading combat log…"
SHARE = "Share link"
SHARED = "Open shared log"


def _num(x):
    """A figure, or None for none (``x == null || isNaN(x)``)."""
    return _number(x)


def skill_art(skill_id) -> str:
    """A skill's icon by the address the web pages know it by (``skillIcon``): its family's, the id's ten thousands."""
    value = _num(skill_id)
    if value is None or not _truthy(skill_id):
        return ""
    return SKILL_ART.format(math.floor(value / 10000) * 10000)


def rate(x) -> str:
    """A rate as a whole percent (``rate``), "—" for none."""
    value = _num(x)
    return "—" if value is None else f"{js_round(100 * value)}%"


def share_of(part, whole) -> str:
    """``Math.round(100 * part / whole)`` as a percent."""
    return f"{js_round(100 * (_num(part) or 0.0) / whole)}%"


# ------------------------------------------------------------------ the fight, normalized
def parse_from_encounter(a) -> dict:
    """An analysis as the parse card reads a fight (``parseFromEncounter``)."""
    a = _dict(a)
    s, m = _dict(a.get("summary")), _dict(a.get("meta"))
    total = _num(s.get("total")) or 1.0
    duration = _num(s.get("duration")) or 1.0
    skills = [k for k in _list(a.get("skills")) if isinstance(k, dict)]
    ids = {js_text(k.get("skill")): k.get("skill_id") for k in skills if _truthy(k.get("skill_id"))}
    biggest = s.get("biggest_hit")
    return {
        "name": m.get("player"), "cls": m.get("class") or m.get("class_name"), "gs": None,
        "cp": m.get("combat_power") or None, "dmg": s.get("total"), "dps": s.get("dps"), "hits": s.get("hits"),
        "contrib": None, "duration": s.get("duration"), "boss": m.get("target"),
        "highest": _dict(biggest).get("damage") if _truthy(biggest) else None,
        "rates": {"crit": s.get("crit"), "double": s.get("double"), "perfect": s.get("perfect"), "multi": s.get("multi"),
                  "back": s.get("back"), "front": s.get("front")},
        "skills": [{"skill": k.get("skill"), "skill_id": k.get("skill_id"), "hits": k.get("hits"),
                    "dps": (_num(k.get("share")) or 0.0) * total / duration, "avg": k.get("avg_hit"), "min": None,
                    "max": k.get("max_hit"), "damage": (_num(k.get("share")) or 0.0) * total, "share": k.get("share")}
                   for k in skills],
        "rotation": [{"t": r[0], "skill": r[1], "skill_id": ids.get(js_text(r[1]))}
                     for r in _list(a.get("rotation")) if isinstance(r, (list, tuple)) and len(r) >= 2],
        "timeline": a.get("timeline"), "live": False,
    }


# ------------------------------------------------------------------ the parse card
def _damage(s: dict) -> float:
    return _num(s.get("damage")) or 0.0


def skills_by_damage(d: dict) -> list[dict]:
    return sorted((s for s in _list(d.get("skills")) if isinstance(s, dict)), key=lambda s: -_damage(s))


def total_damage(d: dict) -> float:
    """The fight's damage (``totDmg``): the card's own figure, else its skills' added up; never nothing."""
    return _num(d.get("dmg")) or sum(_damage(s) for s in skills_by_damage(d)) or 1.0


def donut(d: dict) -> list[dict]:
    """Damage by skill (``parts``): the five largest, then the rest as one; each its words, share and colour."""
    skills = skills_by_damage(d)
    whole = total_damage(d)
    parts = [{"label": js_text(s.get("skill")), "value": _damage(s), "colour": PALETTE[i % len(PALETTE)]}
             for i, s in enumerate(skills[:5])]
    rest = skills[5:]
    other = sum(_damage(s) for s in rest)
    if other > 0:
        parts.append({"label": f"Other ({len(rest)})", "value": other, "colour": PALETTE[8]})
    for part in parts:
        part["share"] = share_of(part["value"], whole)
    return parts


def donut_arcs(parts: list[dict]) -> list[tuple[float, float, str]]:
    """Each part's arc on the ring (``pdonut``): its start and its sweep in degrees, clockwise from the top, and its
    colour. A ring without parts is one empty arc; a part is never quite the whole circle."""
    shown = parts or [{"value": 1, "colour": EMPTY_DONUT}]
    whole = sum((_num(p.get("value")) or 0.0) for p in shown) or 1.0
    arcs, start = [], -90.0
    for p in shown:
        frac = min((_num(p.get("value")) or 0.0) / whole, 0.99999)
        if frac <= 0:
            continue
        arcs.append((start, frac * 360.0, p["colour"]))
        start += frac * 360.0
    return arcs


def skill_rows(d: dict) -> list[dict]:
    """The skills table (``srows``): each skill's hits, DPS, average, least and most, and damage with its share and
    its bar against the largest."""
    skills = skills_by_damage(d)
    whole = total_damage(d)
    largest = max([1.0] + [_damage(s) for s in skills])
    return [{"skill": js_text(s.get("skill")), "skill_id": s.get("skill_id"),
             "hits": "—" if s.get("hits") is None else js_text(s.get("hits")), "dps": kfmt(s.get("dps")),
             "avg": kfmt(s.get("avg")), "min": "—" if s.get("min") is None else kfmt(s.get("min")),
             "max": "—" if s.get("max") is None else kfmt(s.get("max")), "damage": kfmt(s.get("damage")),
             "share": share_of(_damage(s), whole), "bar": _damage(s) / largest} for s in skills]


def hits(d: dict):
    """The player's outgoing hits: the source's own count, else the skills' hits added up (``hits``)."""
    if d.get("hits") is not None:
        return d.get("hits")
    skills = skills_by_damage(d)
    if any(s.get("hits") is not None for s in skills):
        return sum((_num(s.get("hits")) or 0.0) for s in skills)
    return None


def accuracy(d: dict) -> list[tuple[str, str]]:
    """Accuracy's cards (``accPanel``)."""
    r = _dict(d.get("rates"))
    return [("Hits", n0(hits(d))), ("Crit", rate(r.get("crit"))), ("Back", rate(r.get("back"))), ("Front", rate(r.get("front"))),
            ("Double", rate(r.get("double"))), ("Perfect", rate(r.get("perfect"))), ("Multi", rate(r.get("multi"))),
            ("Parried", rate(r.get("parry")))]


def defense(d: dict) -> dict | None:
    """Defense's cards and attackers (``defPanel``), or None when the source has no incoming damage."""
    incoming = d.get("incoming")
    if not _truthy(incoming):
        return None
    incoming = _dict(incoming)
    cards = [("Damage taken", kfmt(incoming.get("damage"))), ("Incoming hits", n0(incoming.get("hits"))),
             ("Parried hits", n0(incoming.get("parries"))), ("Shield blocks", n0(incoming.get("shield_blocks"))),
             ("Endurance", n0(incoming.get("endurance"))), ("Healing done", kfmt(d.get("healing") or 0))]
    sources = sorted(_dict(incoming.get("sources")).items(), key=lambda kv: -(_num(kv[1]) or 0.0))
    return {"cards": cards, "attackers": [(js_text(name), kfmt(damage)) for name, damage in sources]}


def rotation(d: dict) -> list[dict]:
    """The skill rotation's first eighty casts (``rot``), each with its time to the second."""
    out = []
    for r in _list(d.get("rotation"))[:80]:
        r = _dict(r)
        t = _num(r.get("t"))
        out.append({"skill": js_text(r.get("skill") or ""), "skill_id": r.get("skill_id"),
                    "at": "" if r.get("t") is None or t is None else fixed(t, 0) + "s"})
    return out


def head_stats(d: dict) -> list[tuple[str, str, bool]]:
    """The card's figures (``pstats``): gear score and combat power when known, damage, DPS (gold) and contribution."""
    stats = []
    if d.get("gs") is not None:
        stats.append(("GS", n0(d.get("gs")), False))
    if d.get("cp") is not None:
        stats.append(("CP", kfmt(d.get("cp")), False))
    stats += [("DMG", kfmt(d.get("dmg")), False), ("DPS", kfmt(d.get("dps")), True)]
    if d.get("contrib") is not None:
        stats.append(("Contrib", f"{js_round(100 * (_num(d.get('contrib')) or 0.0))}%", False))
    return stats


def head_line(d: dict) -> str:
    """The class and the boss under the name (``psub``)."""
    return cap(js_text(d.get("cls") or "")) + (f" · {js_text(d['boss'])}" if _truthy(d.get("boss")) else "")


def chart(d: dict) -> dict | None:
    """The DPS over the fight (``lineChart``): each second's bar and the ten-second average's line, against the
    largest of either, and the peak ten seconds; None when the fight has no timeline."""
    timeline = d.get("timeline")
    if not _truthy(timeline):
        return None
    timeline = _dict(timeline)
    per = [(_num(v) or 0.0) for v in _list(timeline.get("per_second"))]
    roll = [(_num(v) or 0.0) for v in _list(timeline.get("rolling10"))]
    return {"per": per, "roll": roll, "top": max([1.0] + per + roll),
            "peak": f"peak 10 s: {n0(max(roll)) if roll else '—'}"}


# ------------------------------------------------------------------ the analysis page
def subtitle(a) -> str:
    """The encounter's line beside its title: the player, class, target, source and combat power."""
    m = _dict(_dict(a).get("meta"))
    line = (f"{js_text(m.get('player') or '')} · {cap(js_text(m.get('class') or m.get('class_name') or ''))} · "
            f"{js_text(m.get('target') or '')} · {js_text(m.get('source'))}")
    return line + (f" · CP {n0(m['combat_power'])}" if _truthy(m.get("combat_power")) else "")


def party(a) -> list[dict]:
    """The party's players, to analyze the fight as another of them, when there is more than one."""
    m = _dict(_dict(a).get("meta"))
    people = [p for p in _list(m.get("party")) if isinstance(p, dict)]
    if len(people) <= 1:
        return []
    return [{"name": js_text(p.get("name")), "class": js_text(p.get("class") or ""), "you": p.get("name") == m.get("player"),
             "tip": f"{js_text(p.get('class'))} · {n0(p.get('damage'))} damage"} for p in people]


def info(a) -> dict:
    """The encounter's notes, its AbyssLogs page and where it is saved."""
    a = _dict(a)
    m = _dict(a.get("meta"))
    return {"notes": " · ".join(js_text(n) for n in _list(m.get("notes"))), "url": m.get("url") if _truthy(m.get("url")) else "",
            "file": js_text(a.get("file")) if _truthy(a.get("file")) else ""}


def info_html(a, accent: str) -> str:
    """The notes line as rich text (``info``), the AbyssLogs page a link."""
    words = info(a)
    parts = [e(words["notes"])] if words["notes"] else []
    if words["url"]:
        parts.append(f"<a href='{e(words['url'])}' style='color: {accent};'>open on AbyssLogs</a>")
    if words["file"]:
        parts.append(f"saved as <code>{e(words['file'])}</code>")
    return " · ".join(parts)


def chips(a) -> list[tuple[str, str]]:
    """Casts a minute, multi-hits and idle time under the card (``extra``)."""
    s = _dict(_dict(a).get("summary"))
    cpm, idle = _num(s.get("cpm")), _num(s.get("idle_seconds"))
    return [("Casts / min", "—" if cpm is None else fixed(cpm, 0)), ("Multi-hit", pct(s.get("multi"))),
            ("Idle", "—" if idle is None else fixed(idle, 1) + " s")]


def buffs(a) -> list[dict]:
    """Each buff's uptime (``buffs``) as a bar's share and its words."""
    return [{"name": js_text(b.get("name")), "bar": max(0.0, min(1.0, _num(b.get("uptime")) or 0.0)),
             "words": pct(b.get("uptime"), 0)} for b in _list(_dict(a).get("buffs")) if isinstance(b, dict)]


def gaps(a) -> str:
    """The idle gaps, each from and to the second's tenth; nothing when there were none."""
    spans = [g for g in _list(_dict(a).get("gaps")) if isinstance(g, dict)]
    if not spans:
        return ""

    def at(x):
        value = _num(x)
        return "—" if value is None else fixed(value, 1)
    return "Idle gaps: " + ", ".join(f"{at(g.get('start'))}–{at(g.get('end'))}s" for g in spans)


def optimal(a) -> dict:
    """The comparison with the optimal rotation (``opt``): why it could not be made, or its note, overlap, DPS, tips and
    first sixteen skills."""
    o = _dict(_dict(a).get("vs_optimal"))
    if _truthy(o.get("error")):
        return {"error": js_text(o["error"])}
    dps = f" · optimal DPS {n0(o.get('sim_dps'))} vs yours {n0(o.get('actual_dps'))}" if _truthy(o.get("comparable_dps")) else ""
    rows = []
    for r in _list(o.get("skills"))[:16]:
        r = _dict(r)
        rows.append({"skill": js_text(r.get("skill")), "share": max(0.0, min(1.0, _num(r.get("share")) or 0.0)),
                     "share_words": pct(r.get("share")), "sim": max(0.0, min(1.0, _num(r.get("sim_share")) or 0.0)),
                     "sim_words": pct(r.get("sim_share")), "casts": js_text(r.get("casts")),
                     "sim_casts": js_text(r.get("sim_casts"))})
    return {"error": "", "note": js_text(o["note"]) if _truthy(o.get("note")) else "",
            "overlap": pct(o.get("share_overlap"), 0), "dps": dps, "tips": [js_text(t) for t in _list(o.get("tips"))],
            "rows": rows,
            "specs": [{"skill": js_text(s.get("skill")), "yours": js_text(s.get("yours") or "none"),
                       "optimal": js_text(s.get("optimal")), "differs": _truthy(s.get("differs"))}
                      for s in _list(o.get("specs")) if isinstance(s, dict)]}


def top(a) -> dict | None:
    """The comparison with the class's top logs (``top``), or None when there is none."""
    t = _dict(_dict(a).get("vs_top"))
    if not _truthy(t.get("rows")):
        return None

    def whole(x):
        value = _num(x)
        return "—" if value is None else fixed(value, 0)
    return {"overlap": pct(t.get("overlap"), 0),
            "rows": [[js_text(r.get("skill")), pct(r.get("share")), pct(r.get("top_share")), whole(r.get("hpm")),
                      whole(r.get("top_hpm"))] for r in _list(t.get("rows")) if isinstance(r, dict)]}


def import_body(a, player: str) -> dict:
    """The fight analyzed again as another of its party (``data-player``)."""
    return {"ref": _dict(_dict(a).get("meta")).get("url"), "player": player}
