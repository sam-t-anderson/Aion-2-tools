"""The My Character page's words (0.2.440), as pages/character.js writes them: the search, the characters imported
before, the character's counts, budgets and notes, the request an optimization sends, and its progress and result.
The page (``character_page.py``) draws them.
"""
from __future__ import annotations

import json
import math
import urllib.parse

from .planner import whole
from .results import _dict, _list, _whole_number, cap, js_text, n0, pct

TITLE_SUB = "import from the official AION 2 character page, then optimize it with the same gear"
REGIONS = (("nae", "North America"), ("eu", "Europe"), ("as", "Asia"), ("la", "Latin America"))
#: The three optimizations: their mode, button and how the progress names them.
MODES = (("pve", "Optimize PvE build", "PvE build"), ("pvp", "Optimize PvP damage (experimental)", "PvP damage (experimental)"),
         ("world", "Optimize World PvP (experimental)", "World PvP (experimental)"))
WORLD_TIP = "Large fights: area skills on several players, survival and crowd control weighed in"
OBJECTIVES = (("primary", "Primary scenario (existing behavior)"), ("balanced", "Balanced: PvE boss/dummy or PvP sustained/burst"))
POINTS_NOTE = ("The profile gives allocated points. Unspent points and some quest rewards may be absent. Enter the total "
               "available in your game window (spent + unspent) before optimizing. These values are the observed lower "
               "bound, not a verified maximum.")
PVP_NOTE = ("PvP optimization is an experimental damage-only estimate against a stationary player proxy. It does not score "
            "survival, crowd control or win chance. PvE and PvP results are saved separately.")
BALANCED_NOTE = ("Balanced uses 50% of each modeled DPS score and may trade primary damage for the combined score. HP and "
                 "trained-skill reserves still apply. Rotation search takes longer; macro and skill-share views describe the "
                 "primary scenario.")
ARIEL_TIP = "Daevanion Crystal: Ariel, the level-45 Ariel board's own points"
RUNNING_NOTE = ("Runs the rotation, stigma, Daevanion and skill-point search. Progress stays visible during the stigma and "
                "skill-level searches; the full optimization may take a few minutes.")
GENUS_NOTE = ("Use the saved analysis lines from this character's Gear & Advice inventory. Save edits before optimizing. "
              "Current-build and optimized scores use identical lines; Genus rolls are held fixed.")
MIX_NOTE = ("PvE enemy mix (relative weights; default equal). PvP ignores this mix and excludes genus-specific effects whose "
            "applicability to players is unverified.")
GENERA = ("Cogni", "Fera", "Natura", "Varian", "Special")
#: What the web page keeps in its browser, kept by the native page in its own settings under the same names.
BUDGETS_KEY, PATCH_KEY, OBJECTIVE_KEY = "character-point-budgets-v2", "point-game-patch", "character-damage-objective"


def search_path(name: str, region: str) -> str:
    return f"/api/character/search?name={urllib.parse.quote(name, safe='')}&region={region}"


def known_line(c: dict) -> str:
    """A character imported before (its button): name, class and combat power."""
    return f"{js_text(c.get('name'))} · {js_text(c.get('class_name'))} · {n0(c.get('combat_power'))}"


def known_hit(c: dict) -> dict:
    """What importing a character imported before asks for: its ids, region and name."""
    return {"character_id": c.get("character_id"), "server_id": c.get("server_id"), "region": c.get("region"),
            "name": c.get("name")}


def hit_row(h: dict) -> list[str]:
    return [js_text(h.get("name")), js_text(h.get("level")), js_text(h.get("server"))]


def importing(hit: dict, cache) -> str:
    """While a character is read: its last snapshot opened, or the official site asked."""
    return (f"opening the last snapshot of {js_text(hit.get('name') or 'the character')}…" if cache
            else "importing from the official site…")


def subtitle(v: dict) -> str:
    return (f"{cap(v.get('class'))} · Lv {js_text(v.get('level'))} · {js_text(v.get('server'))} · "
            f"Combat Power {n0(v.get('combat_power'))}")


def budget_keys(v: dict) -> list[str]:
    """The budgets the character has: skill, stigma and Daevanion, and the Ariel crystal's when its view counts it."""
    return ["skill", "stigma", "daevanion"] + (["ariel"] if _whole_number(_dict(v.get("points")).get("ariel")) is not None
                                                else [])


def budget_label(key: str) -> str:
    return "Ariel crystal" if key == "ariel" else cap(key)


def kpis(v: dict) -> list[tuple[str, str]]:
    """The character's counts: its DPS in each scenario, then its points spent of each budget."""
    tiles = [(f"{js_text(k)} {'saved build DPS' if v.get('genus') else 'imported DPS (without manual Genus)'}", n0(x))
             for k, x in _dict(v.get("dps")).items()]
    points, budgets = _dict(v.get("points")), _dict(v.get("budgets"))
    for key, name in (("skill", "Skill points"), ("stigma", "Stigma points"), ("daevanion", "Daevanion")):
        budget = budgets.get(key)
        tiles.append((name, f"{js_text(points.get(key))} / {'Unknown' if budget is None else js_text(budget)}"))
    if "ariel" in budget_keys(v):
        budget = budgets.get("ariel")
        tiles.append(("Ariel crystal", f"{js_text(points.get('ariel'))} / {'Unknown' if budget is None else js_text(budget)}"))
    return tiles


def available(v: dict, saved: dict) -> dict[str, float]:
    """The totals in the budget fields: what the profile shows spent, or the total typed for this character (kept
    only above it), or the budget the view gives, never below what is spent."""
    points, budgets = _dict(v.get("points")), _dict(v.get("budgets"))
    shown = {}
    for key in budget_keys(v):
        spent = points.get(key)
        other = saved.get(key) if saved.get(key) is not None else budgets.get(key) if budgets.get(key) is not None else spent
        numbers = [x for x in (spent, other) if isinstance(x, (int, float)) and not isinstance(x, bool)]
        shown[key] = max(numbers) if numbers else spent
    return shown


def remembered(v: dict, values: dict) -> dict:
    """The totals kept for this character: those typed above what the profile shows spent."""
    points = _dict(v.get("points"))
    return {k: n for k, n in values.items() if isinstance(points.get(k), (int, float)) and n is not None and n > points[k]}


def read_store(text) -> dict:
    """What the web page keeps as JSON, read back (an object, else nothing)."""
    try:
        value = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def field_values(texts: dict[str, str]) -> dict:
    """The budget fields read as numbers (``+e.value``): a whole number, else none."""
    return {k: whole(text) for k, text in texts.items()}


def community_note(points: dict, keys: list[str]) -> str:
    """The class's highest reported totals, for reference only (never put in the fields), when there are any."""
    shown = [k for k in keys if points.get(k) is not None]
    if not shown:
        return ""
    totals = ", ".join(f"{'Ariel crystal' if k == 'ariel' else k} {points[k]}" for k in shown)
    return (f"Highest totals reported for the class: {totals}. The optimizer uses your totals above; type yours in if you "
            "have points left unspent.")


def at_level_cap(v: dict) -> bool:
    cap_level = v.get("level_cap") or 45
    level = v.get("level") if v.get("level") is not None else cap_level
    return isinstance(level, (int, float)) and isinstance(cap_level, (int, float)) and level >= cap_level


def genus_choice(enabled: bool, mix: dict[str, str], mode: str) -> dict:
    """What the Genus panel sends (``read``): whether the saved lines count, and the PvE mix; or why it cannot."""
    numbers = {g: _float(mix.get(g, "")) for g in GENERA}
    if mode == "pve" and enabled and (any(x is None or not math.isfinite(x) or x < 0 or x > 100 for x in numbers.values())
                                      or not any(x is not None and x > 0 for x in numbers.values())):
        raise ValueError("Set a positive PvE Genus mix using weights from 0 to 100.")
    return {"enabled": enabled} if mode != "pve" or not enabled else {"enabled": enabled, "mix": numbers}


def _float(text: str) -> float | None:
    """``Number(e.value)`` of a number field: empty reads 0, what does not read as a number none."""
    text = str(text).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


#: What an optimization sends for the panels the native page has not drawn yet (as a browser that never opened them).
SURVIVAL_DEFAULT = {"preserve_hp": True, "min_node_hp": 0, "current_hp": None, "opponents": [], "action_windows": []}
RESERVES_DEFAULT = {"sp": {}, "stigmas": {}, "specs": {}}


def optimize_body(hit: dict, mode: str, objective: str, budgets: dict, genus: dict, game_patch: str) -> dict:
    """What ``/api/character/optimize`` is asked: the character, the mode and objective, the budgets, the survival and
    reserve options, the Genus choice and the game version."""
    return {**hit, "mode": mode, "objective": objective, "budgets": budgets, "survival": dict(SURVIVAL_DEFAULT),
            "skill_reserves": json.loads(json.dumps(RESERVES_DEFAULT)), "genus": genus, "game_patch": game_patch.strip()}


def running(mode: str, log: list) -> tuple[str, str]:
    """A running optimization's line (its mode and its log's last line) and the log's last eight lines."""
    name = dict((m, words) for m, _button, words in MODES).get(mode, "PvE build")
    last = js_text(log[-1]) if log else "starting…"
    return f"Optimizing {name} — {last}", "\n".join(js_text(x) for x in log[-8:])


def elsewhere(name) -> str:
    return f"Optimizing {js_text(name or 'another character')}: open that character to follow it; a new optimization can start when it finishes."


def result(r: dict) -> dict:
    """A finished optimization (``renderOptResult``): its score and gain, the model's note, the preset's word, and
    what changes."""
    summary, optimized = _dict(r.get("summary")), _dict(r.get("optimized"))
    scenario = summary.get("scenario") or optimized.get("scenario") or "boss"
    objective = _dict(summary.get("objective") or optimized.get("objective"))
    score = objective.get("score") if objective.get("score") is not None else _dict(optimized.get("dps")).get(scenario)
    label = objective.get("label") or ("PvP proxy DPS" if scenario == "pvp" else "boss DPS")
    gain = summary.get("gain")
    preset = _dict(r.get("preset"))
    if preset.get("submitted"):
        words = ("This build is now the community preset for its class." if preset.get("accepted") else
                 "The server kept its current Planner preset: " + js_text(preset.get("reason") or "no improvement at the shared budgets"))
    else:
        words = f"Community preset: {js_text(preset.get('reason'))}" if preset.get("reason") else ""
    return {"label": f"Optimized {js_text(label)}", "score": n0(score),
            "gain": "Unavailable" if gain is None else ("+" if gain >= 0 else "") + pct(gain), "good": bool(gain) and gain > 0,
            "model_note": js_text(optimized.get("model_note") or ""), "preset": words, "accepted": bool(preset.get("accepted")),
            "diff": js_text(r.get("diff"))}


def optimized_view(r: dict, meta: dict) -> dict:
    """The optimized build as the windows show it: the optimization's view with the character's name and counts."""
    return {**_dict(r.get("optimized")), **meta}


def meta(v: dict) -> dict:
    return {k: v.get(k) for k in ("key", "name", "level", "warnings", "server", "combat_power")}


def warnings(v: dict) -> list[str]:
    return [f"• {js_text(w)}" for w in _list(v.get("warnings"))]

