"""A build's result windows' words (0.2.434), as pages/results.js writes them for the Build Planner, My Character and
Saved Results: the windows' list, and the Overview, Skills and Stigma windows' figures, lines and notes; since
0.2.435 the Daevanion window's boards, nodes and points and the Equipment window's paper doll, rolls and enchant
priority; since 0.2.436 the Arcana window's cards, variants and skill rolls with the deity totals, and the titles,
wings and pet. The native windows (``result_windows.py``) draw them; the notes are rich text in the subset Qt's text engine
draws, the ``<details>`` of the web page opened in place.
"""
from __future__ import annotations

import html
import math
import re

from . import theme

#: The windows of a result (results.js ``WINDOWS``): key, title, icon.
WINDOWS = (("overview", "Overview", "◆"), ("skills", "Skills", "✦"), ("stigma", "Stigma", "⬢"),
           ("daevanion", "Daevanion", "✧"), ("genus", "Pet Genus", "◈"), ("equipment", "Equipment", "⚔"),
           ("arcana", "Arcana", "❖"), ("titles", "Titles & wings", "♛"), ("hotbar", "Skills hotbar", "▦"),
           ("macro", "Macro & rotation", "⌨"))
NATIVE = ("overview", "skills", "stigma", "daevanion", "equipment", "arcana", "titles")   # the native windows so far
COMPARISON = ("Generate a separate {mode} example with common gear and the server’s published point budgets (highest "
              "reported totals when available; explicitly labeled example fallback otherwise). Your personal build, "
              "Genus and HP/skill reserves stay saved separately. Seed searches and weighted refinement can take several "
              "minutes; completed comparisons are reused until the scoring inputs change. Only anonymous allocations are "
              "submitted. Stationary damage comparison, not a survival or win-rate model.")
MUTED, FAINT, GOLD, ACCENT = theme.COLORS["muted"], theme.COLORS["faint"], theme.COLORS["gold"], theme.COLORS["accent"]
TEXT = theme.COLORS["text"]


def e(value) -> str:
    """``esc``: what a result holds, as text in rich text."""
    return html.escape("" if value is None else str(value))


def _number(value):
    """``isNaN``'s reading of a value: a number, or None for none or what does not read as one."""
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def n0(value) -> str:
    """``n0``: a whole number grouped by commas, "—" for none."""
    x = _number(value)
    return "—" if x is None or math.isinf(x) else f"{theme.js_round(x):,}"


def pct(value, digits: int = 1) -> str:
    """``pct``: a share as a percent to ``digits`` places, "—" for none."""
    x = _number(value)
    return "—" if x is None else theme.fixed(100 * x, digits) + "%"


def sp(value) -> str:
    """``sp``: a signed percent to one place."""
    x = _number(value)
    return "—" if x is None else ("+" if x >= 0 else "") + theme.fixed(100 * x, 1) + "%"


def cap(text) -> str:
    text = str(text or "")
    return text[:1].upper() + text[1:]


def js_text(value) -> str:
    """A number in a sentence as JavaScript writes it (``${x}``): 180 rather than 180.0."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return "" if value is None else str(value)


def muted(text: str) -> str:
    return f"<span style='color: {MUTED};'>{text}</span>"


def small_muted(text: str) -> str:
    return f"<p style='color: {MUTED};'>{text}</p>"


def table(headers: list[str], rows: list[list[str]]) -> str:
    """A table (``table.t``) in rich text: its headings in gold, its cells as given."""
    head = "".join(f"<th align='left' style='color: {theme.COLORS['gold_dim']};'>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table cellspacing='0' cellpadding='4' width='100%'><tr>{head}</tr>{body}</table>"


def details(summary: str, body: str) -> str:
    """A ``<details>`` opened in place: its summary as a heading of its own."""
    return f"<p><i>{summary}</i></p>{body}"


# ------------------------------------------------------------------ the Overview
def kpis(v: dict) -> list[tuple[str, str]]:
    """The Overview's counts: each scenario's DPS, the typical top build, crit chance, cooldown reduction and combat
    speed."""
    out = [(f"{k} DPS", n0(x)) for k, x in (v.get("dps") or {}).items()]
    if v.get("baseline"):
        out.append(("Typical top build", n0(v["baseline"].get("community_optimized_rotation"))))
    stats = v.get("stats") or {}
    out += [("Crit chance", pct(stats.get("crit_chance_vs_target"))), ("Cooldown red.", pct(stats.get("cdr"))),
            ("Combat speed", pct(stats.get("combat_speed")))]
    return out


def objective(v: dict) -> str:
    """The objective's note: its score, its scenarios' weights, durations and DPS."""
    goal = v.get("objective")
    if not goal:
        return ""
    parts = []
    for name, weight in (goal.get("weights") or {}).items():
        duration = (goal.get("durations") or {}).get(name)
        parts.append(f"{e(name)} {pct(weight)}" + (f" · {n0(duration)}s" if duration else "") +
                     f" · {n0((goal.get('components') or {}).get(name))} DPS")
    return (f"<b>{e(goal.get('label'))}: {n0(goal.get('score'))}</b><br>" + " · ".join(parts) +
            small_muted(e(goal.get("note"))))


def scoring_policy(v: dict, when) -> str:
    """A community or common comparison preset's note, with its assumptions opened."""
    policy = v.get("scoring_policy")
    if not policy:
        return ""
    mode = str(policy.get("mode") or "")
    head = (f"{'Community' if v.get('preset_source') == 'community' else 'Common comparison'} {e(mode.upper())} preset · "
            f"{n0(v.get('score'))} weighted modeled DPS")
    pace = ("sustained and burst player-target damage" if mode == "pvp" else "boss and training-dummy damage")
    checked = f"Last checked {e(when(v['preset_checked_at'] * 1000))}" if v.get("preset_checked_at") else ""
    inner = f"{e(policy.get('note'))}<br>Evaluator {e(policy.get('model'))}"
    generation = v.get("candidate_generation")
    if generation:
        inner += (f"<br>Candidate search: {e(generation.get('objective'))} · {e(generation.get('iterations'))} "
                  "iteration(s). Selected by the common weighted score; not a global optimum.")
        selection = generation.get("selection")
        if selection:
            inner += f"<br>{e(selection.get('method'))}" + "".join(
                f"<br>{e(c.get('objective'))}: {n0(c.get('score'))} weighted modeled DPS"
                for c in selection.get("candidates") or [])
    return (f"{head}<br><small>Equal weighting of {pace}. Common gear and comparison point budgets. {checked}</small>"
            + details("Comparison assumptions", inner))


def world_pvp(w) -> str:
    """The world PvP measures beside the typical build's (``worldPvpHTML``)."""
    if not w:
        return ""
    typical = w.get("typical_build") or {}

    def row(label, x, y, fmt):
        return [label, fmt(x), "—" if y is None else fmt(y)]
    rows = [row("Score (DPS × share survived × share not controlled)", w.get("score"), typical.get("score"), n0),
            row(f"Damage on up to {e((w.get('assumptions') or {}).get('enemies_in_reach', 3))} players (DPS)",
                w.get("dps"), typical.get("dps"), n0),
            row("Share of the fight survived", w.get("alive_share"), typical.get("alive_share"), pct),
            row("Share of it not crowd-controlled", w.get("acting_share"), typical.get("acting_share"), pct),
            row("Effective HP (with shields and heals)", w.get("effective_hp"), typical.get("effective_hp"), n0),
            row("Hard crowd control you deal (s per minute)", w.get("control_s_per_min"), typical.get("control_s_per_min"),
                lambda x: theme.fixed(x, 1)),
            row("Crowd control you take (share of the fight)", w.get("controlled_self"), typical.get("controlled_self"), pct)]
    line = (f"{e(w.get('attackers'))} attackers · {pct(w.get('controlled'))} of their time under your crowd control · "
            f"damage taken {pct(w.get('damage_taken'))} of an undefended player's"
            + (f" · {pct(w['evade_chance'])} of hits evaded" if w.get("evade_chance") else "")
            + (f" · {pct(w['block_chance'])} of the rest blocked (half damage)" if w.get("block_chance") else "")
            + f" · Status Effect Resist {pct(w.get('status_resist') or 0)} · {len(w.get('defensives') or [])} defensive "
              "effects counted.")
    return ("<h4>World PvP</h4>" + table(["", "This build", "Typical build"], rows) + small_muted(line)
            + small_muted(e(w.get("note") or "")))


def progression(p) -> str:
    """The point budgets' provenance (``progressionHTML``), the body of its fold."""
    if not p:
        return ""
    rows = [[e(cap(r.get("resource"))), n0(r.get("observed_spent")), n0(r.get("available_assumption")),
             n0(r.get("assumed_unspent")), e(r.get("source")),
             "Unknown" if r.get("verified_maximum") is None else n0(r.get("verified_maximum"))]
            for r in p.get("resources") or []]
    return table(["Resource", "Observed spent", "Assumed available", "Assumed unspent", "Basis", "Verified maximum"], rows) \
        + small_muted(e(p.get("note")))


def _requirement(window: dict) -> str:
    need = window.get("skill_requirement")
    if not need:
        return " · Unlinked assumption"
    return (f"<br>Requested retention: {e(need.get('name'))} · trained Lv {e(need.get('minimum'))}"
            + (f" · {e(need.get('effect'))}" if need.get("effect") else ""))


def cooldowns(checks, scope: str = "reduction windows") -> str:
    """``cooldownSummary``."""
    if not checks:
        return ""
    items = []
    for c in checks:
        starts = ", ".join(f"{e(t)}s" for t in c.get("activation_starts_s") or []) or "none"
        if c.get("status") == "no_active_windows":
            what = f"No active {e(scope)}"
        elif c.get("cooldown_s") is None:
            what = "Cooldown unknown · reuse not assessed"
        else:
            gap = ("No repeated activation" if c.get("shortest_reuse_gap_s") is None
                   else f"shortest reuse gap {e(c['shortest_reuse_gap_s'])}s")
            what = f"Assumed effective cooldown {e(c['cooldown_s'])}s · {gap} · assumed spacing satisfied"
        items.append(f"<li>{e(c.get('skill'))} · starts: {starts} · {what}"
                     + (" · largest of differing assumptions used" if c.get("mixed_assumptions") else "") + "</li>")
    return "<ul>" + "".join(items) + "</ul>"


def reservations(rows) -> str:
    """``rotationReservationSummary``."""
    if not rows:
        return ""
    items = "".join(
        f"<li>Skill #{e(r.get('skill_id'))} · assumed use {e(r.get('start_s'))}s · entered cooldown {e(r.get('cooldown_s'))}s · "
        + (f"reserved in modeled group(s): {', '.join(e(g) for g in r.get('cooldown_groups') or [])} · matching actions: "
           f"{', '.join(e(a) for a in r.get('matched_actions') or [])}" if r.get("status") == "reserved" else
           "Unavailable: no matching modeled action; no rotation cooldown reserved") + "</li>" for r in rows)
    return f"<h4>Cooldown reservations in the damage rotation</h4><ul>{items}</ul>"


def action_timing(timing) -> str:
    """``actionTimingSummary``: the outgoing action-time assumptions."""
    if not timing:
        return ""
    windows = "".join(
        f"<li>{e(w.get('name'))} · {e(w.get('start_s'))}–{e(w.get('end_s'))}s"
        + (" · Rotation cooldown reservation requested" if w.get("reserve_cooldown") else "") + _requirement(w) + "</li>"
        for w in timing.get("windows") or [])
    cases = "".join(
        f"<p>{e(name)} · {e(c.get('paused_s'))}s unavailable for new actions / {e(c.get('duration_s'))}s · clipped interval "
        f"union: {', '.join(f'{e(a)}–{e(b)}s' for a, b in c.get('blocks') or []) or 'none'}</p>"
        + cooldowns(c.get("cooldown_checks"), "action-time windows in this scenario") + reservations(c.get("rotation_reservations"))
        for name, c in (timing.get("cases") or {}).items())
    return f"<h3>Outgoing action-time assumptions</h3><ul>{windows}</ul>{cases}" + small_muted(e(timing.get("note")))


def survival(plan) -> str:
    """``survivalSummary``: the HP reserve of a constrained damage optimization."""
    if not plan:
        return ""
    out = (f"<h3>HP reserve · constrained damage optimization</h3><p>Crystal-board flat HP: <b>{n0(plan.get('selected_node_hp'))}</b>"
           f" · requested floor: {n0(plan.get('minimum_node_hp'))} · previous contribution: {n0(plan.get('reference_node_hp'))}. "
           f"{'Reserve met.' if plan.get('meets_node_floor') else 'Reserve not met.'}</p>")
    if plan.get("estimated_total_hp_proxy") is not None:
        out += (f"<p>Estimated total HP proxy: {n0(plan['estimated_total_hp_proxy'])} · worst assumed headroom: "
                f"{'Not assessed' if plan.get('worst_headroom_hp') is None else n0(plan['worst_headroom_hp'])}</p>")
    opponents = plan.get("opponents") or []
    if opponents:
        rows = []
        for row in opponents:
            cell = e(row.get("name"))
            evidence = row.get("recorded_evidence")
            cell += (f"<br><small>{'Imported recording · editable assumption' if evidence else 'User assumption'} · "
                     f"{js_text(row.get('window_s'))}s window"
                     + (f"<br>{e(evidence.get('title'))} · {e(evidence.get('recipient'))} · recorded peak "
                        f"{e(evidence.get('damage'))} HP ({e(evidence.get('start_s'))}–{e(evidence.get('end_s'))}s)" if evidence else "")
                     + "</small>")
            bench = row.get("opponent_benchmark")
            if bench:
                cell += (f"<br><small>Opponent benchmark (editable assumption): {e(bench.get('title'))} · {e(bench.get('metric'))} "
                         f"{e(bench.get('modeled_dps'))} modeled DPS × {e(bench.get('scale'))} · source duration "
                         f"{e(bench.get('source_duration_s'))}s. Not measured incoming damage.</small>"
                         + details("Source benchmark assumptions",
                                   f"<small>Class: {e(bench.get('class'))} · saved timestamp: {e(bench.get('created'))} · duration: "
                                   f"{e(bench.get('duration_source'))}<br>{e(bench.get('model_note'))}<br>Source model version and "
                                   "cross-version comparability are not verified. The original score remains separate from the "
                                   "editable pressure fields.</small>"))
            if row.get("peak_pressure_hp") is not None:
                cell += (f"<br><small>Peak ongoing pressure {n0(row['peak_pressure_hp'])} HP at {e(row.get('peak_pressure_at_s'))}s · "
                         f"healing delay {e(row.get('healing_delay_s'))}s · active {e(row.get('healing_active_s'))}s</small>")
            if row.get("reductions"):
                items = "".join(
                    f"<li>{e(w.get('name'))} · {e(w.get('kind'))}: {e(w.get('reduction_pct'))}% from {e(w.get('start_s'))}s to "
                    f"{e(w.get('end_s'))}s ({e(w.get('active_s'))}s active)"
                    + (f"<br>Retain {e(w['skill_requirement'].get('name'))} · trained Lv {e(w['skill_requirement'].get('minimum'))}"
                       + (f" · {e(w['skill_requirement'].get('effect'))}" if w['skill_requirement'].get('effect') else "")
                       if w.get("skill_requirement") else " · Unlinked assumption") + "</li>"
                    for w in row["reductions"])
                cell += details("Assumed defense / control / movement timing",
                                f"<ul>{items}</ul><small>Same healing without added reductions: {n0(row.get('unprotected_required_hp'))} HP "
                                f"required. Assumed requirement reduction: {n0(row.get('assumed_requirement_reduction_hp'))} HP. Initial hit "
                                "unchanged; strongest overlap only. No skill casts or tactical success are simulated.</small>"
                                + cooldowns(row.get("cooldown_checks")))
            rows.append([cell, n0(row.get("required_hp")),
                         f"{n0(row.get('headroom_hp'))} · " + ("Meets assumed HP requirement" if row.get("meets_assumed_pressure")
                                                                 else "Below requirement")])
        out += table(["Assumed encounter / opponent", "Hit + pressure + reserve", "HP headroom (proxy)"], rows)
    binding = plan.get("binding_opponents") or []
    out += f"<p>{'Strictest incoming requirement: ' + ' · '.join(e(b) for b in binding) if binding else ''}</p>"
    out += small_muted(e(plan.get("note")))
    traced = [r for r in opponents if r.get("damage_trace")]
    if traced:
        inner = ""
        for r in traced:
            events = r["damage_trace"].get("events") or []
            bench = r.get("opponent_benchmark") or {}
            inner += (f"<h4>{e(r.get('name'))}</h4><p>Source {e(bench.get('source_start_s'))}–{e(bench.get('source_end_s'))}s · "
                      f"{len(events)} hits · {n0(r['damage_trace'].get('total'))} scaled damage · peak deficit at "
                      f"{e(r.get('peak_pressure_at_s'))}s</p>"
                      + table(["Window time", "Expected incoming damage"],
                              [[f"{theme.fixed(t, 3)}s", n0(amount)] for t, amount in events[:200]])
                      + (small_muted("First 200 hits displayed; all saved hits are evaluated.") if len(events) > 200 else ""))
        out += details("Imported expected-hit schedules", inner)
    return out + small_muted("DPS is maximized subject to this HP floor. These personal constraints are not compared "
                             "against damage-only community presets.")


def skill_reserves(plan) -> str:
    """``skillReserveSummary``: the trained-skill reserves."""
    if not plan:
        return ""
    out = (f"<h3>Trained skill reserves · {'met' if plan.get('met') else 'not met'}</h3>"
           + table(["Skill", "Minimum", "Selected"], [[e(r.get("name")), js_text(r.get("minimum")), js_text(r.get("selected"))]
                                                      for r in plan.get("skills") or []]))
    if plan.get("effects"):
        out += "<h4>Reserved supporting effects</h4><ul>" + "".join(
            f"<li>{e(x.get('skill'))} · {e(x.get('text'))} (effect Lv {e(x.get('unlock'))}) · "
            f"{'retained' if x.get('selected') else 'missing'}</li>" for x in plan["effects"]) + "</ul>"
    if plan.get("effective_levels"):
        out += "<h4>Required effective levels</h4><ul>" + "".join(
            f"<li>{e(r.get('name'))} · Lv {e(r.get('selected'))} / required {e(r.get('minimum'))} (trained {e(r.get('trained'))} + "
            f"Daevanion {e(r.get('daevanion'))} + fixed bonuses {e(r.get('gear'))})</li>" for r in plan["effective_levels"]) + "</ul>"
    return out + small_muted(e(plan.get("note")))


def weight_rows(v: dict) -> list[tuple[str, str, float]]:
    """Stat priority: each upgrade, its DPS gain and its bar's length (a quarter of a percent a percent)."""
    rows = []
    for x in v.get("weights") or []:
        gain = _number(x.get("pct")) or 0.0
        rows.append((str(x.get("label") or ""), ("+" if gain >= 0 else "") + theme.fixed(gain, 2) + "%",
                     max(0.0, min(100.0, gain * 25))))
    return rows


def share_rows(shares, most: int = 12) -> list[tuple[str, str, float]]:
    """Damage (or healing) share: the first twelve skills, each with its share and its bar beside the largest's."""
    shares = shares or {}
    top = max([*(float(x) for x in shares.values()), 0.0]) or 1.0
    return [(str(name), pct(x), 100 * float(x) / top) for name, x in list(shares.items())[:most]]


def healing(v: dict) -> dict | None:
    """The healing share's box (0.2.368, 0.2.386): None where the web page draws none, else its lines and rows."""
    recorded = v.get("healing") if isinstance(v.get("healing"), dict) and (v["healing"].get("shares") or {}) else None
    modelled = v.get("modelled_healing") if isinstance(v.get("modelled_healing"), dict) and v["modelled_healing"].get("per_minute") else None
    if "healing" not in v and not modelled:
        return None
    lines = []
    if modelled:
        lines.append(f"Modelled: {n0(modelled.get('hps'))} HPS in a boss fight ("
                     + ", ".join(f"{e(r.get('skill'))} {pct(r.get('share'))}" for r in (modelled.get("by_skill") or [])[:3])
                     + f"): each heal at this character's level times {theme.fixed(modelled.get('multiplier') or 0, 2)} for its "
                       "Attack, as often as recorded healers heal.")
    if recorded:
        fights, recordings = recorded.get("fights"), recorded.get("recordings")
        lines.append(f"Recorded: {n0(recorded.get('hps'))} HPS over {fights} fight{'' if fights == 1 else 's'} "
                     f"({n0((recorded.get('seconds') or 0) / 60)} min) in {recordings} recording{'' if recordings == 1 else 's'} "
                     "saved on this computer.")
    else:
        lines.append("No recorded healing by this character yet. Fights recorded with the live meter on this computer fill "
                     "this in" + ("" if modelled else "; the model simulates heal amounts for Clerics and Chanters only") + ".")
    return {"lines": lines, "rows": share_rows(recorded.get("shares")) if recorded else []}


def overview_notes(v: dict, when) -> list[str]:
    """The Overview's notes between its counts and its tables, in the web page's order, each rich text (the model
    note and world PvP are one; the provenance is its own fold, ``progression``)."""
    notes = []
    for text in (objective(v), scoring_policy(v, when)):
        if text:
            notes.append(text)
    if v.get("world_pvp"):
        notes.append(world_pvp(v["world_pvp"]))
    return notes


def model_note(v: dict) -> str:
    return "" if v.get("world_pvp") else str(v.get("model_note") or "")


def comparison_text(v: dict) -> str:
    return COMPARISON.format(mode="PvP" if str(v.get("scenario") or "").startswith("pvp") else "PvE")


# ------------------------------------------------------------------ Skills
def skill_counter(v: dict) -> tuple[str, str]:
    """The Skills window's counter (``.counter``): its words, and the points spent of the budget."""
    return "Skill points", f"{n0((v.get('points') or {}).get('skill'))} / {n0((v.get('budgets') or {}).get('skill'))}"


def skill_level(s: dict) -> str:
    """A skill's level and where it comes from: rich text, "<b>Lv 20</b> = SP 10 + Daevanion 4 + gear 6"."""
    source = f"= SP {e(s.get('sp'))} + Daevanion {e(s.get('daev'))}" + (f" + gear {e(s['gear'])}" if s.get("gear") else "")
    return f"<b>Lv {e(s.get('eff'))}</b> <span style='color: {ACCENT};'>{source}</span>"


def skill_slots(s: dict) -> str:
    """Its selection slots, how many effects are recommended, and the next effect's level."""
    if not s.get("specs"):
        return ""
    chosen = sum(1 for x in s["specs"] if x.get("chosen"))
    return (f"{e(s.get('slots'))} selection slot(s)\n{chosen} recommended"
            + (f"\nNext effect at Lv {e(s['next_effect_level'])}" if s.get("next_effect_level") else ""))


def effect_state(x: dict) -> str:
    return "Recommended" if x.get("chosen") else "Available" if x.get("available") else "Locked"


def skills_copy(v: dict) -> str:
    """The Skills window as text (``Copy as text``)."""
    lines = []
    for s in (v.get("skills") or {}).get("active", []) + (v.get("skills") or {}).get("passive", []):
        chosen = [x for x in s.get("specs") or [] if x.get("chosen")]
        if (s.get("sp") or 0) > 1 or chosen:
            lines.append(f"{s.get('name')}: train to {js_text(s.get('sp'))} (Lv {js_text(s.get('eff'))})" + (
                " — specialties " + "; ".join(f"{x.get('n')}: {x.get('text')} (effect Lv {e(x.get('unlock'))})" for x in chosen)
                if chosen else ""))
    text = "\n".join(lines)
    chase = bonus_levels(v)
    return text + ("\nBonus levels from gear rolls and arcana cards: " + chase if chase else "")


def bonus_levels(v: dict) -> str:
    """A community preset's bonus levels: the skills to put gear rolls and arcana card options on."""
    return ", ".join(f"{r.get('name')} +{js_text(r.get('levels'))}" + (f" ({', '.join(r['arcana'])})" if r.get("arcana") else "")
                     for r in v.get("bonus_levels") or [])


def skills_grid(v: dict) -> list[tuple[str, str]]:
    """The Skills window's figures (``statGrid``, "From this system")."""
    rows = [("Skill points spent", f"{n0((v.get('points') or {}).get('skill'))} / {n0((v.get('budgets') or {}).get('skill'))}")]
    rolls = ", ".join(f"{r.get('name')} +{js_text(r.get('levels'))}" for r in v.get("gear_skill_rolls") or [])
    if rolls:
        rows.append(("Skill levels from gear", rolls))
    chase = bonus_levels(v)
    if chase:
        rows.append(("Bonus levels to chase: gear rolls and arcana cards (the cards that can roll each skill)", chase))
    return rows


# ------------------------------------------------------------------ Stigma
def stigma_counter(v: dict) -> tuple[str, str]:
    return "Stigma points", f"{n0((v.get('points') or {}).get('stigma'))} / {n0((v.get('budgets') or {}).get('stigma'))}"


def stigmas_copy(v: dict) -> str:
    return "\n".join(f"{s.get('name')}: Lv {js_text(s.get('level'))}" for s in v.get("stigmas") or [])


def stigmas_grid(v: dict) -> list[tuple[str, str]]:
    return [(str(s.get("name")), f"Lv {js_text(s.get('level'))} · {sum(1 for x in s.get('specs') or [] if x.get('active'))} effects")
            for s in v.get("stigmas") or []]


def stigma_effect(x: dict) -> str:
    """A stigma's effect (rich text): its number in gold, its words, its level faint; muted while inactive."""
    words = f"<b style='color: {GOLD};'>{e(x.get('n'))}</b> {e(x.get('text'))} <span style='color: {FAINT};'>(Lv {e(x.get('unlock'))})</span>"
    return words if x.get("active") else f"<span style='color: {MUTED};'>{words}</span>"


# ------------------------------------------------------------------ Daevanion
#: A node's colour by its grade (``.node[data-grade]``); a node of any other grade is the board's off colour.
NODE_FILL = {"Common": "#c9ccd3", "Rare": "#4aa3e6", "Legend": "#a46cf0", "Unique": "#f0bf4a"}
NODE_OFF, NODE_START = "#232c42", "#4fd1b3"
#: The board's key (``.legend``): each grade's colour and cost, then what the shapes mean.
LEGEND = (("#c9ccd3", "Common 1 pt"), ("#4aa3e6", "Rare 2 pt"), ("#a46cf0", "Epic 3 pt"), ("#f0bf4a", "Unique 4 pt"))
LEGEND_NOTE = "squares = stats · circles = +1 skill level · bright = take it"
NO_BOARD = "No board data"
ARIEL_TIP = "Daevanion Crystal: Ariel, the Ariel board's own points"
PLANNER = "Open in metabot planner"


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _truthy(value) -> bool:
    """JavaScript's reading of a value as a condition: an object or array is true even when empty."""
    return isinstance(value, (dict, list)) or (bool(value) and not (isinstance(value, float) and math.isnan(value)))


def daevanion_board(v: dict, index: int) -> dict | None:
    """The board shown (``d.boards[boardIdx] || d.boards[0]``), or None when the build has none."""
    boards = _list(_dict(v.get("daevanion")).get("boards"))
    for board in (boards[index] if 0 <= index < len(boards) else None, boards[0] if boards else None):
        if isinstance(board, dict):
            return board
    return None


def board_tabs(v: dict) -> list[tuple[int, str, str]]:
    """Each board's tab: its place among the boards, its name, and its points used of its total."""
    return [(index, js_text(x.get("name")), f"{js_text(x.get('used'))}/{js_text(x.get('total'))}")
            for index, x in enumerate(_list(_dict(v.get("daevanion")).get("boards"))) if isinstance(x, dict)]


def board_nodes(b: dict) -> list[dict]:
    return [nd for nd in _list(b.get("nodes")) if isinstance(nd, dict)]


def node_shape(nd: dict) -> str:
    """A node's kind (``.node``): the start's hexagon, a skill level's circle, a hidden one, or a stat's square."""
    kind = nd.get("type")
    return "start" if kind == "Start" else "skill" if kind == "SkillLevel" else "none" if kind == "None" else "stat"


def node_lit(nd: dict) -> bool:
    """Whether a node is bright (``.sel``): one the build takes, and the start."""
    return bool(nd.get("selected")) or nd.get("type") == "Start"


def node_fill(nd: dict) -> str:
    if nd.get("type") == "Start":
        return NODE_START
    grade = nd.get("grade")
    return NODE_FILL.get(grade, NODE_OFF) if isinstance(grade, str) else NODE_OFF


def node_tip(nd: dict) -> str:
    """A node's tooltip: a skill level's skill, grade and cost; a stat's words, grade and cost; or the start."""
    kind = nd.get("type")
    if kind == "SkillLevel":
        return f"{js_text(nd.get('skill'))} +1 ({js_text(nd.get('grade'))}, {js_text(nd.get('cost'))} pt)"
    if kind == "Start":
        return "Start"
    return f"{js_text(nd.get('label'))} ({js_text(nd.get('grade'))}, {js_text(nd.get('cost'))} pt)"


def node_text(nd: dict) -> str:
    """The words on a node: a skill's initials (at most three), a stat's short figure, nothing on the start."""
    kind = nd.get("type")
    if kind == "SkillLevel":
        return "".join(word[:1] for word in re.split(r"\s+", str(nd.get("skill") or "")))[:3]
    return "" if kind == "Start" else js_text(nd.get("short") or "")


def node_icon(nd: dict) -> str:
    """A skill level's picture on metabot.gg, for a skill id that is a whole number above 0
    (``Number.isSafeInteger``); none for any other node."""
    if nd.get("type") != "SkillLevel":
        return ""
    number = _number(nd.get("skill_id"))
    if number is None or not number.is_integer() or not 0 < number <= 2 ** 53 - 1:
        return ""
    return f"https://metabot.gg/web/aion2/skills/{js_text(nd.get('skill_id'))}.webp"


def points_used(d: dict) -> str:
    budget = d.get("budget")
    return f"{js_text(d.get('used'))} / {'Unknown' if budget is None else js_text(budget)}"


def ariel_used(d: dict) -> str:
    """The Ariel crystal's own points, when the build has any; else nothing."""
    used, budget = d.get("ariel_used"), d.get("ariel_budget")
    if not (used or budget):
        return ""
    return f"{0 if used is None else js_text(used)} / {'Unknown' if budget is None else js_text(budget)}"


def board_line(b: dict) -> str:
    taken = sum(1 for nd in board_nodes(b) if nd.get("selected"))
    return f"{js_text(b.get('used'))} / {js_text(b.get('total'))} points · {taken} nodes"


def daevanion_skills(d: dict) -> list[tuple[str, str]]:
    """The skill levels the boards give: each skill and its levels."""
    return [(js_text(s.get("name")), f"+{js_text(s.get('levels'))}") for s in _list(d.get("skills")) if isinstance(s, dict)]


def daevanion_stats(d: dict) -> list[tuple[str, str]]:
    """The stats all the boards give (the side's list and the window's ``statGrid``)."""
    return [(js_text(s.get("label")), js_text(s.get("text"))) for s in _list(d.get("stats")) if isinstance(s, dict)]


def planner_link(v: dict) -> str:
    """The build's boards in metabot's Daevanion planner, if it has the link."""
    link = _dict(v.get("links")).get("metabot_daevanion")
    return str(link) if link else ""


def daevanion_copy(v: dict) -> str:
    boards = "\n".join(f"{name}: {used} pts" for _index, name, used in board_tabs(v))
    link = planner_link(v)
    return boards + (f"\nPlanner link: {link}" if link else "")


# ------------------------------------------------------------------ Equipment
#: The slots on the paper doll's left (``LEFT_SLOTS``): the weapons and armour; the others are on its right.
LEFT_SLOTS = ("MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt",
              "Main hand", "Off-hand", "Armor x7")
#: An item's colour by its grade (``--g-*``): its name, and its tile's left edge.
GRADES = {"Common": "rgba(255, 255, 255, 0.88)", "Rare": "#52b35c", "Legend": "#3d94d8", "Unique": "#e9a43a",
          "Epic": "#ee6c2a", "Mythic": "#d33939", "Special": "#34b798"}
EQUIPMENT_GRID = "Stats from equipment, rolls and manastones"
ROLLS_HEAD, ENCHANT_HEAD = "KEEP / REROLL TOWARD (best first)", "ENCHANT PRIORITY"


def equipment_slots(v: dict) -> tuple[list[dict], list[dict]]:
    """The paper doll's slots: those on its left, and those on its right, each in the build's order."""
    slots = [s for s in _list(_dict(v.get("equipment")).get("slots")) if isinstance(s, dict)]
    return [s for s in slots if s.get("slot") in LEFT_SLOTS], [s for s in slots if s.get("slot") not in LEFT_SLOTS]


def slot_grade(s: dict) -> str:
    grade = s.get("grade")
    return grade if isinstance(grade, str) and grade in GRADES else ""


def slot_item(s: dict) -> str:
    return js_text(s.get("item") or s.get("name") or "")


def slot_stats(s: dict, most: int | None = 4) -> str:
    """A slot's stats (rich text), its first four unless ``most`` says otherwise: each figure bold, then its stat."""
    return " · ".join(f"<b style='color: {TEXT};'>{e(x.get('text'))}</b> {e(x.get('label'))}"
                      for x in _list(s.get("stats"))[:most] if isinstance(x, dict))


def _pairs(rows) -> list[tuple]:
    return [(row[0] if row else None, row[1] if len(row) > 1 else None) for row in _list(rows) if isinstance(row, list)]


def slot_extras(s: dict) -> list[tuple[str, str]]:
    """A slot's chips (``.chip``): its rolls, then its manastones and theostones (gold), then its skill levels."""
    chips = [("chip", f"{js_text(k)} {js_text(val)}") for k, val in _pairs(s.get("rolls"))]
    chips += [("manastone", f"{js_text(k)} {js_text(val)}") for k, val in _pairs(s.get("manastones"))]
    chips += [("gold", js_text(t)) for t in _list(s.get("theostones"))]
    chips += [("skill", f"{js_text(k)} +{js_text(lv)}") for k, lv in _pairs(s.get("skills"))]
    return chips


def doll(v: dict) -> tuple[str, str, str]:
    """The paper doll's middle: the class, who wears it (a character and server, or the loadout), its combat power."""
    who = f"{js_text(v.get('name'))} · {js_text(v.get('server'))}" if v.get("name") else js_text(v.get("loadout_name") or "")
    power = f"Combat Power {n0(v.get('combat_power'))}" if v.get("combat_power") else ""
    return cap(v.get("class")), who, power


def equipment_sub(v: dict) -> str:
    if v.get("equipment_source"):
        return js_text(v.get("equipment_source"))
    return "current gear (official profile)" if v.get("name") else "loadout used for this build"


def roll_rows(v: dict) -> list[tuple[str, str]]:
    """The rolls to keep or reroll toward, best first, for the first eight items: the item, and its stats in order."""
    rolls = _dict(_dict(v.get("equipment")).get("rolls"))
    return [(str(slug).replace("-", " "), " › ".join(js_text(r.get("stat")) for r in _list(rows) if isinstance(r, dict)))
            for slug, rows in list(rolls.items())[:8]]


def enchant_rows(v: dict) -> list[tuple[str, str]]:
    """Where an enchant level is worth most: each slot and its DPS a level (``toFixed(1)``)."""
    rows = []
    for r in _list(_dict(v.get("equipment")).get("enchant")):
        if isinstance(r, dict):
            dps = _number(r.get("dps"))
            rows.append((js_text(r.get("slot")), "—" if dps is None else theme.fixed(dps, 1)))
    return rows


def equipment_copy(v: dict) -> str:
    slots = [s for s in _list(_dict(v.get("equipment")).get("slots")) if isinstance(s, dict)]
    return "\n".join(f"{js_text(s.get('slot'))}: {js_text(s.get('item') or s.get('name'))}" for s in slots)


def equipment_grid(v: dict) -> list[tuple[str, str]]:
    return [(js_text(r.get("label")), js_text(r.get("text"))) for r in _list(_dict(v.get("equipment")).get("total"))
            if isinstance(r, dict)]


# ------------------------------------------------------------------ Arcana
ARCANA_SUB = "Chalice, Parchment, Compass roll active skills · Bell, Mirror roll passives"
NO_ARCANA = "No arcana data"
PICKS_HEAD = "RECOMMENDED VARIANT PER SLOT"
ROLLS_TABLE_HEAD = "SKILL ROLLS — value of each arcana slot (Unique: 4 rolls at +0, 9 at +5)"
ROLLS_COLUMNS = ["Slot", "Unique +0", "Unique +5", "Best rolls (+1 / +2)"]


def arcana_deity(d) -> str:
    """An arcana card's deity stat as the game shows it (``arcanaDeityText``): "Time [Siel] +20"."""
    d = _dict(d)
    if not d.get("label"):
        return ""
    return f"{js_text(d.get('label'))} +{js_text(float(theme.fixed(_number(d.get('points')) or 0.0, 1)))}"


def arcana_cards(v: dict) -> list[dict]:
    """A character's arcana cards (``.card``): each one's picture and enchant level, its name and grade, its deity stat,
    its skill levels and its stats."""
    return [{"icon": a.get("icon") or "", "enchant": f"+{js_text(a.get('enchant') or 0)}", "grade": slot_grade(a),
             "name": js_text(a.get("name")), "deity": arcana_deity(a.get("deity")) if _truthy(a.get("deity")) else "",
             "skills": [f"{js_text(k)} +{js_text(lv)}" for k, lv in _pairs(a.get("skills"))],
             "stats": ", ".join(f"{js_text(s.get('label'))} {js_text(s.get('text'))}" for s in _list(a.get("stats"))
                                if isinstance(s, dict))}
            for a in _list(v.get("arcana_items")) if isinstance(a, dict)]


def arcana_picks(v: dict) -> list[tuple[str, str, list[str]]]:
    """The recommended variant for each arcana slot: the slot, the variant (or either), and each variant's stat."""
    return [(js_text(a.get("slot")), "Either variant" if a.get("tie") else js_text(a.get("pick")),
             [f"{js_text(k)}: {js_text(s)}" for k, s in _dict(a.get("variants")).items()])
            for a in _list(_dict(v.get("extras")).get("arcana")) if isinstance(a, dict)]


def _signed(x: float) -> str:
    return ("+" if x >= 0 else "") + theme.fixed(x, 1)


def arcana_roll_rows(v: dict) -> list[list[str]]:
    """The value of each arcana slot's skill rolls (``table.t``), the best at +5 first: the slot, its expected gain with
    a Unique card at +0 and at +5, and its four best skills with their gains at +1 and +2."""
    rolls = _dict(_dict(v.get("extras")).get("arcana_rolls"))
    rows = []
    for slot, a in sorted(rolls.items(), key=lambda item: -(_number(_dict(item[1]).get("expected_unique_5")) or 0.0)):
        a = _dict(a)
        skills = [(k, g) for k, g in _dict(a.get("skills")).items() if isinstance(g, list) and len(g) > 1]
        skills = sorted(skills, key=lambda item: -(_number(item[1][1]) or 0.0))[:4]
        rows.append([cap(slot), f"+{theme.fixed(_number(a.get('expected_unique_0')) or 0.0, 1)}%",
                     f"+{theme.fixed(_number(a.get('expected_unique_5')) or 0.0, 1)}%",
                     " · ".join(f"{js_text(k)} {_signed(_number(g[0]) or 0.0)}% / {_signed(_number(g[1]) or 0.0)}%"
                                for k, g in skills)])
    return rows


def arcana_copy(v: dict) -> str:
    """The Arcana window's text: each card with its enchant level, deity stat and skill levels, then each slot's pick."""
    lines = []
    for a in _list(v.get("arcana_items")):
        if isinstance(a, dict):
            skills = _pairs(a.get("skills"))
            lines.append(f"{js_text(a.get('slot'))}: {js_text(a.get('name'))} +{js_text(a.get('enchant') or 0)}"
                         + (f", {arcana_deity(a.get('deity'))}" if _truthy(a.get("deity")) else "")
                         + (" — " + ", ".join(f"{js_text(k)} +{js_text(lv)}" for k, lv in skills) if skills else ""))
    lines += [f"{js_text(a.get('slot'))}: {'either' if a.get('tie') else js_text(a.get('pick'))}"
              for a in _list(_dict(v.get("extras")).get("arcana")) if isinstance(a, dict)]
    return "\n".join(lines)


def deity_grid(v: dict) -> list[tuple[str, str]]:
    """The deity and primary stats' totals (a window of their own under Arcana)."""
    return [(js_text(s.get("label")), js_text(s.get("text"))) for s in _list(_dict(v.get("extras")).get("deity"))
            if isinstance(s, dict)]


# ------------------------------------------------------------------ Titles, wings & pet
TITLES_TITLE = "Titles, wings & pet"
TITLES_HEAD = "BEST TITLES FOR THIS BUILD"
TITLE_COLUMNS = ["Title", "Equip bonus", "Owned bonus"]
TITLES_GRID = "Stats from equipped titles"
PET_NOTE = "Pet bonuses are mostly against one monster genus."


def title_tiles(v: dict) -> list[dict]:
    """The titles, wings and pet the build wears (``.slot``): each one's slot, name, grade, stats (rich text), picture
    and, for the pet, its level."""
    ex = _dict(v.get("extras"))
    tiles = [{"slot": js_text(t.get("slot")), "item": js_text(t.get("item")), "grade": "", "stats": slot_stats(t, None),
              "icon": "", "level": ""} for t in _list(ex.get("titles")) if isinstance(t, dict)]
    wing = _dict(ex.get("wing")).get("icon") or ""
    tiles += [{"slot": "Wings", "item": js_text(w.get("item")), "grade": "Unique", "stats": slot_stats(w, None),
               "icon": wing, "level": ""} for w in _list(ex.get("wings")) if isinstance(w, dict)]
    if _truthy(ex.get("pet")):
        pet = _dict(ex.get("pet"))
        tiles.append({"slot": "Pet", "item": js_text(pet.get("name")), "grade": "", "stats": e(PET_NOTE),
                      "icon": pet.get("icon") or "", "level": f"Lv {js_text(pet.get('level'))}"})
    return tiles


def title_rows(v: dict) -> list[tuple[str, str, str, str]]:
    """The best titles for the build (``table.t``): each one's name, grade, equip bonus and owned bonus."""
    return [(js_text(t.get("name")), slot_grade(t), js_text(t.get("equip")), js_text(t.get("owned")))
            for t in _list(_dict(v.get("extras")).get("title_ranking")) if isinstance(t, dict)]


def titles_grid(v: dict) -> list[tuple[str, str]]:
    return [(js_text(s.get("label")), js_text(s.get("text"))) for s in _list(_dict(v.get("extras")).get("titles_total"))
            if isinstance(s, dict)]


# ------------------------------------------------------------------ Saved Results
def saved_line(when_text: str) -> str:
    return f"Saved result from {when_text}. This is a snapshot; advice may change as gear or game data changes."


def view_of(doc: dict) -> dict | None:
    """The build a saved result shows in the result windows: an optimized character's optimized build, or the
    result itself."""
    result = doc.get("result") if isinstance(doc, dict) else None
    if not isinstance(result, dict):
        return None
    view = result.get("optimized") if doc.get("kind") == "optimize-character" else result
    return view if isinstance(view, dict) else None
