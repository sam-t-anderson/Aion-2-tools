"""The My Character page's words (0.2.440), as pages/character.js writes them: the search, the characters imported
before, the character's counts, budgets and notes, the request an optimization sends, and its progress and result;
and (0.2.441) the survival options and trained-skill reserves, with what their fields send. The page
(``character_page.py``, the two panels in ``character_options.py``) draws them.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse

from .planner import whole
from .results import _dict, _entries, _list, _truthy, _whole_number, cap, js_text, n0, pct

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


def optimize_body(hit: dict, mode: str, objective: str, budgets: dict, survival: dict, reserves: dict, genus: dict,
                  game_patch: str) -> dict:
    """What ``/api/character/optimize`` is asked: the character, the mode and objective, the budgets, the survival and
    reserve options (as their panels read them), the Genus choice and the game version."""
    return {**hit, "mode": mode, "objective": objective, "budgets": budgets, "survival": to_json(survival),
            "skill_reserves": to_json(reserves), "genus": genus, "game_patch": game_patch.strip()}


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



# ------------------------------------------------------------------ JavaScript's values, as the panels' fields hold them
#: A number field's value (the HTML "valid floating-point number"): what a browser keeps of what is typed in one.
_FIELD_NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")
_DECIMAL = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _number_text(x: float) -> str:
    """``String(x)`` of a number: its shortest digits, written out up to 21 places, else with an exponent."""
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    mantissa, _, power = repr(abs(x)).partition("e")
    whole_part, _, fraction = mantissa.partition(".")
    digits = (whole_part + fraction).lstrip("0")
    point = len(whole_part) - (len(whole_part + fraction) - len(digits)) + (int(power) if power else 0)
    digits = digits.rstrip("0")
    sign, k = "-" if x < 0 else "", len(digits)
    if k <= point <= 21:
        return sign + digits + "0" * (point - k)
    if 0 < point <= 21:
        return sign + digits[:point] + "." + digits[point:]
    if -6 < point <= 0:
        return sign + "0." + "0" * -point + digits
    exponent = point - 1
    return f"{sign}{digits[0]}{'.' + digits[1:] if k > 1 else ''}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"


def js_string(value) -> str:
    """``String(value)``: a number as JavaScript writes it, true/false, null, an array's items joined by commas."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value) if abs(value) < 10 ** 21 else _number_text(float(value))
    if isinstance(value, float):
        return _number_text(value)
    if isinstance(value, list):
        return ",".join("" if x is None else js_string(x) for x in value)
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def esc_text(value) -> str:
    """What ``esc(value)`` shows: nothing for none, else ``String(value)``."""
    return "" if value is None else js_string(value)


def js_number(value) -> float:
    """``Number(value)``: none reads 0, text a decimal (or hexadecimal, octal, binary) number or NaN, true 1."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return js_number(js_string(value))
    if not isinstance(value, str):
        return math.nan
    text = value.strip()
    if not text:
        return 0.0
    if text in ("Infinity", "+Infinity", "-Infinity"):
        return -math.inf if text.startswith("-") else math.inf
    if _DECIMAL.fullmatch(text):
        return float(text)
    based = re.fullmatch(r"0([xXoObB])([0-9a-fA-F]+)", text)
    if based:
        try:
            return float(int(based.group(2), {"x": 16, "o": 8, "b": 2}[based.group(1).lower()]))
        except ValueError:
            return math.nan
    return math.nan


def to_json(value):
    """A value as ``JSON.stringify`` sends it: a whole number as one, NaN and the infinities as null, an object's keys
    that read as indices first (``Object.entries``)."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value) if value.is_integer() and abs(value) < 1e21 else value
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in _entries(value)}
    if isinstance(value, list):
        return [to_json(x) for x in value]
    return value


def store_text(value) -> str:
    """What the web page keeps in its browser (``JSON.stringify``)."""
    return json.dumps(to_json(value), separators=(",", ":"), ensure_ascii=False)


def field_value(text: str) -> str:
    """A number field's value as the web page reads it: its text when that is a number, else empty."""
    text = text.strip()
    return text if _FIELD_NUMBER.fullmatch(text) else ""


def field_text(value) -> str:
    """What a number field shows for a value (``value="${esc(x)}"``): a number, else nothing."""
    text = esc_text(value)
    return text if _FIELD_NUMBER.fullmatch(text) else ""


def _js_min(*xs: float) -> float:
    return math.nan if any(math.isnan(x) for x in xs) else min(xs)


def _js_max(*xs: float) -> float:
    return math.nan if any(math.isnan(x) for x in xs) else max(xs)


def _same(a, b) -> bool:
    """``a === b`` for the values a page compares: numbers by value (NaN never), else text and others as they are."""
    a_number = isinstance(a, (int, float)) and not isinstance(a, bool)
    b_number = isinstance(b, (int, float)) and not isinstance(b, bool)
    if a_number or b_number:
        return a_number and b_number and a == b
    return type(a) is type(b) and a == b


def _includes(values, item) -> bool:
    """``values.includes(item)``: an array's item (NaN included), or a text's part."""
    if isinstance(values, list):
        return any(_same(x, item) or (isinstance(x, float) and isinstance(item, float) and math.isnan(x) and math.isnan(item))
                   for x in values)
    if isinstance(values, str):
        return js_string(item) in values
    return False


def _number_is(number: float, value) -> bool:
    """``number === value``: ``value`` a number (not text) equal to ``number``."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and number == value


def options_key(prefix: str, hit, v: dict) -> str:
    """The key a character's options are kept under: the search hit it was imported from, else its key or loadout
    (``JSON.stringify(st.hit || v.key || v.loadout)``)."""
    for value in (hit, v.get("key"), v.get("loadout")):
        if _truthy(value):
            return prefix + store_text(value)
    return prefix + "undefined"


# ------------------------------------------------------------------ trained-skill reserves (``mountSkillReserves``)
RESERVES_PREFIX = "character-skill-reserves:"
RESERVES_TITLE = "Retain trained skills and equipped stigmas"
RESERVES_NOTE = ("Optional minimums for skills you rely on for defense, control or movement. Applies to both PvE and PvP. "
                 "Damage is optimized within these constraints. You can also reserve supporting effects on active skills. "
                 "Trained points, fixed gear bonuses and connected Daevanion nodes jointly fund their unlocks and selection "
                 "slots within your budgets. Infeasible requests are rejected. Other specialties may change. Use utility "
                 "skills manually when absent from the rotation. This does not simulate defensive skill use, crowd "
                 "control, movement or opponent matchups.")
RESERVES_HEADS = ["Retain", "Skill", "Minimum trained level", "Retain supporting effects"]
RESERVE_BAD = "Reserve levels must be whole numbers within the shown range."


def reserve_rows(v: dict) -> list[dict]:
    """The skills a minimum can be kept for: the active and passive skills (their trained level, at most what can be
    bought), then the equipped stigmas (at most 20)."""
    skills = _dict(v.get("skills"))
    rows = [{**row, "field": "sp", "level": row.get("sp"), "max": row.get("buy_max") if _truthy(row.get("buy_max")) else 10}
            for row in _list(skills.get("active")) + _list(skills.get("passive")) if isinstance(row, dict)]
    return rows + [{**row, "field": "stigmas", "max": 20} for row in _list(v.get("stigmas")) if isinstance(row, dict)]


def reserve_name(row: dict) -> str:
    return esc_text(row.get("name")) + (" · keep equipped" if row["field"] == "stigmas" else "")


def _kept(saved: dict, row: dict):
    """``saved[row.field]?.[row.id]``."""
    return _dict(saved.get(row["field"])).get(js_string(row.get("id")))


def reserve_checked(saved: dict, row: dict) -> bool:
    return _truthy(_kept(saved, row))


def reserve_level(saved: dict, row: dict) -> str:
    """The minimum field's first value: the level kept, else the trained level, else 1, within 1 and the row's
    maximum."""
    kept = _kept(saved, row)
    pick = kept if _truthy(kept) else row.get("level") if _truthy(row.get("level")) else 1
    return field_text(_js_max(1.0, _js_min(js_number(row["max"]), js_number(pick))))


def reserve_effects(row: dict) -> list[dict]:
    """An active or passive skill's supporting effects that can be kept (a stigma's are not offered)."""
    return [e for e in _list(row.get("specs")) if isinstance(e, dict)] if row["field"] == "sp" else []


def effect_line(effect: dict) -> str:
    return f"{js_string(effect.get('n'))}. {esc_text(effect.get('text'))} · effect Lv {js_string(effect.get('unlock'))}"


def effect_checked(saved: dict, row: dict, effect: dict) -> bool:
    """``saved.specs?.[row.id]?.includes(effect.id)``."""
    return _includes(_dict(saved.get("specs")).get(js_string(row.get("id"))), effect.get("id"))


def level_ok(text: str, maximum) -> bool:
    """``checkValidity`` of a minimum field (``min="1" max="${row.max}"``, whole steps from 1): empty, or a whole
    number from 1 to the maximum."""
    value = field_value(text)
    if not value:
        return not text.strip()                       # what does not read as a number is a bad input
    x = float(value)
    top = js_number(field_text(maximum)) if field_text(maximum) else math.inf
    return x >= 1 and (math.isnan(top) or x <= top) and (x - 1).is_integer()


def reserve_read(rows: list[dict], retained: list[bool], levels: list[str], effects: list[list]) -> tuple[dict, list[bool], int, str]:
    """``read``: the minimums kept (a retained row's level; the effects chosen, which retain their row), the rows'
    Retain boxes after it, how many rows it went through (their minimum fields enabled when retained), and why it
    stopped (the first retained level outside its range), else nothing."""
    plan: dict = {"sp": {}, "stigmas": {}, "specs": {}}
    retained = list(retained)
    for index, row in enumerate(rows):
        key = js_string(row.get("id"))
        chosen = [js_number(js_string(e)) for e in effects[index]]
        if chosen:
            retained[index] = True
            plan["specs"][key] = chosen
        if retained[index]:
            if not level_ok(levels[index], row["max"]):
                return plan, retained, index + 1, RESERVE_BAD
            plan[row["field"]][key] = js_number(field_value(levels[index]))
    return plan, retained, len(rows), ""


# ------------------------------------------------------------------ survival options (``mountSurvivalOptions``)
SURVIVAL_PREFIX = "character-survival:"
SURVIVAL_TITLE = "Survivability · preserve HP while optimizing damage"
SURVIVAL_NOTE = ("Protects flat HP from crystal-board nodes. It does not model armor, defensive skills or CC. Incoming "
                 "scenarios are explicit assumptions, with optional timed expected-hit benchmarks from optimized PvP "
                 "opponents; these are not decoded boss mechanics or reactive duels.")
HITS_NOTE = ("Use hits and incoming DPS after your mitigation. The requirement is one hit plus the largest ongoing pressure "
             "deficit plus a positive HP reserve. Healing begins after the chosen delay and lasts for the entered duration "
             "(blank means the rest of the window). Excess healing is not banked. Healing never absorbs the initial hit. "
             "These timings are assumptions, not decoded defensive abilities or CC rules. Total HP uses only a flat "
             "node-delta proxy; verify the result in game.")
PRESSURE_HEADS = ["Encounter / opponent", "Hit damage", "Incoming DPS", "Seconds", "Assumed HPS", "Healing delay (s)",
                  "Healing duration (s)", "HP reserve", "Timed pressure reductions", ""]
#: A scenario's number fields and what each shows when it has no value.
PRESSURE_FIELDS = (("burst_damage", 0), ("pressure_dps", 0), ("window_s", 5), ("healing_hps", 0), ("healing_delay_s", 0),
                   ("healing_duration_s", ""), ("reserve_hp", 1))
WINDOW_LOCKED = "Re-import this opponent to change its timed window"
REDUCTION_KINDS = ("defensive", "control", "movement")
#: A reduction window's last three fields: their key, label and what each shows when it has no value.
REDUCTION_TIMES = (("delay_s", "Start (s)", 0), ("duration_s", "Duration (s)", 0), ("reduction_pct", "Pressure reduced (%)", 0))
REDUCTIONS_NOTE = ("Timed reductions apply to ongoing incoming DPS and imported timed hits. Enter assumed successful "
                   "defense, control or movement windows explicitly; times are relative to the scenario start. No catalog "
                   "coefficient, immunity, cooldown or success chance is inferred. Overlaps use the strongest percentage, "
                   "never stack. The initial hit is unchanged. Do not reduce damage twice if your incoming DPS already "
                   "includes the same effect. Optionally link a skill and supporting effect: their minimums are "
                   "automatically merged with your reserves below, including zero-duration windows. Unlinked windows "
                   "remain assumptions. Links retain allocations; they do not cast skills or subtract their time from "
                   "outgoing DPS. Optionally enter an effective cooldown for each linked skill (blank = unknown, zero = no "
                   "reuse gap). Repeat spacing is checked within each scenario, with all skills initially ready. "
                   "Same-start entries count as one activation; the largest entered cooldown for a skill applies. Review "
                   "this assumption if gear or cooldown reduction changes. Charges, resets and shared cooldown groups are "
                   "not modeled.")
ACTION_LEGEND = "Outgoing action-time assumptions"
ACTION_NOTE = ("Pause new offensive actions while spending time on defense or movement. Enter one fight's rotation clock, "
               "starting at zero. This schedule applies once to each damage scenario and is clipped to its duration; "
               "overlaps count once. Actions must finish before a pause. Already scheduled hits, DoTs, pets, cooldown "
               "recovery and regeneration continue. Incoming-pressure windows use separate clocks and are not copied here. "
               "No tactical skill cast, MP cost, cooldown or defensive success is inferred. Current-character damage uses "
               "the same pauses; community references remain unpaused.")
ACTION_LINKS_NOTE = ("Optional links retain the selected skill/stigma and supporting effect within your budgets, including "
                     "zero-duration and clipped-out windows. Passive skills cannot be action-time links. A cooldown checks "
                     "only assumed reuse in each outgoing scenario: blank is unknown, zero imposes no gap. Positive-duration "
                     "windows starting before scenario end count as uses; same-start entries count once. The largest "
                     "entered cooldown for a linked skill applies. Incoming-pressure scenarios stay separate. Enable Reserve "
                     "cooldown in rotation to keep matching modeled skill IDs and explicit cooldown groups available for the "
                     "assumed use. This requires an entered cooldown: before the use, the larger of that assumption and the "
                     "modeled offensive cooldown determines the hold; afterward, the group stays excluded for the entered "
                     "cooldown. Fixed exclusions ignore reset hooks. Unmatched skills are reported. Cross-skill hooks and "
                     "resource readiness are not verified; exclusions do not prove tactical availability. No tactical MP, "
                     "damage, shields or success is modeled; unrecorded shared groups and charges remain unknown.")
RECORDED_LEGEND = "Import recorded incoming damage"
RECORDED_NOTE = ("Choose an exported a2log JSON file. Uses the largest gross damage window received by the selected player, "
                 "from all recorded attackers. Healing is excluded; recorded deaths reset the window. Missing death markers "
                 "can join separate lives. Missing packets understate damage; damage reflects that recipient's gear and "
                 "defenses. Imported values remain editable assumptions for your build, not a simulated opponent matchup.")
NO_RECIPIENTS = ("No player-recipient damage events found. Older logs with only outgoing skill hits cannot supply incoming "
                 "pressure.")
READING_EVENTS = "Reading damage events…"
RECORDING_TOO_BIG = "Choose an a2log JSON file below 32 MiB."
PRESSURE_IMPORTED = "Recorded pressure imported. Enter your current maximum HP and review the reserve before optimizing."
BENCHMARK_LEGEND = "Import optimized PvP opponent benchmark"
METHODS = (("timed", "Timed hits · greatest gross-damage window"), ("average", "Average pressure · supports older results"))
METRICS = (("pvp_burst", "Burst average (30s by default)"), ("pvp", "Sustained average (180s by default)"))
BENCHMARK_NOTE = ("Select up to eight optimized PvP results from Saved Results (re-optimize for timed hits). Timed mode "
                  "imports each result’s greatest gross-damage window from its complete expected-hit simulation. Healing "
                  "and reduction windows then use time relative to that selected window. This selection does not maximize "
                  "the mitigated HP requirement across every possible defense/healing alignment. Choose a scale explicitly "
                  "for your assumed incoming damage; target defenses are not converted. Average mode uses scalar DPS for "
                  "older results. These are stationary opponent benchmarks; reactions, random critical spikes, immunity and "
                  "win probability are not simulated.")
FULL = "Remove a scenario first (maximum eight)."
NO_FILES = "Choose exported optimized PvP result JSON files."
TOO_MANY = "Use at most eight incoming scenarios in total."
TOO_BIG = "Selected results must total at most 20 MiB."
NO_SCALE = "Enter an explicit incoming damage scale; your mitigation is not inferred."
SCENARIOS_NOTE = ("Up to eight scenarios; the strictest HP requirement constrains the build. For PvP, compare several "
                  "optimized opponent benchmarks; their damage is evaluated separately and the strictest HP requirement "
                  "wins. Explicit defensive, control and movement windows can retain your skills and supporting effects. "
                  "Matchup mitigation, reactive opponent behavior and win probability remain unmodeled.")
MOST = 8                                              # scenarios, action-time windows, and a scenario's reductions
RECORDING_MIB, RESULTS_MIB = 32, 20
#: Each part's fields in the order a page reads them; a link's skill, effect and cooldown read none when empty.
PRESSURE_KEYS = ("name",) + tuple(key for key, _fallback in PRESSURE_FIELDS)
REDUCTION_KEYS = ("name", "kind", "skill_id", "min_trained", "effect_id", "cooldown_s", "delay_s", "duration_s",
                  "reduction_pct")
ACTION_KEYS = ("name", "start_s", "duration_s", "skill_id", "min_trained", "effect_id", "cooldown_s", "reserve_cooldown")
LINKS = ("skill_id", "effect_id", "cooldown_s")
CARRIED = ("recorded_evidence", "damage_trace", "opponent_benchmark")


def survival_settings(saved) -> dict:
    """The options a character's panel opens with: the defaults, then what was kept (at most eight scenarios and
    eight action-time windows)."""
    settings = {"preserve_hp": True, "min_node_hp": 0, "current_hp": None, "opponents": [], "action_windows": []}
    if isinstance(saved, dict):
        settings = {**settings, **saved,
                    "opponents": saved["opponents"][:MOST] if isinstance(saved.get("opponents"), list) else [],
                    "action_windows": saved["action_windows"][:MOST] if isinstance(saved.get("action_windows"), list) else []}
    return settings


def read_saved(text):
    """``JSON.parse(text || "null")``, or none when it does not parse."""
    try:
        return json.loads(text or "null")
    except (TypeError, ValueError):
        return None


def name_text(row: dict, fallback: str) -> str:
    """A name field's value (``row.name || fallback``)."""
    return js_string(row.get("name")) if _truthy(row.get("name")) else fallback


def or_value(row: dict, key: str, fallback):
    """``row[key] ?? fallback``."""
    return fallback if row.get(key) is None else row[key]


def trace_line(row: dict) -> str:
    """An imported opponent's timed hits, under its name."""
    trace, bench = _dict(row.get("damage_trace")), _dict(row.get("opponent_benchmark"))
    events = trace.get("events")
    count = len(events) if isinstance(events, (list, str)) else "undefined"
    return (f"Timed expected hits · {count} hits · {n0(trace.get('total'))} damage · source "
            f"{esc_text(bench.get('source_start_s'))}–{esc_text(bench.get('source_end_s'))}s")


def windows_count(row: dict) -> int:
    """``row.reductions?.length || 0``."""
    reductions = row.get("reductions")
    return len(reductions) if isinstance(reductions, (list, str)) else 0


def skill_choices(v: dict) -> list[dict]:
    """The skills a window can link: the active and passive skills and the equipped stigmas."""
    skills = _dict(v.get("skills"))
    return ([{**s, "kind": "active"} for s in _list(skills.get("active")) if isinstance(s, dict)]
            + [{**s, "kind": "passive"} for s in _list(skills.get("passive")) if isinstance(s, dict)]
            + [{**s, "kind": "stigma"} for s in _list(v.get("stigmas")) if isinstance(s, dict)])


def _linked(choices: list[dict], chosen):
    number = js_number(chosen)
    return next((s for s in choices if _number_is(number, s.get("id"))), None)


def skill_options(choices: list[dict], chosen, actions_only: bool = False) -> tuple[list[tuple[str, str]], int]:
    """A link's skill list (``skillOptions``): each option's value and words, and the one chosen. A skill kept that the
    character no longer has stays, as unavailable."""
    shown = [s for s in choices if not actions_only or s["kind"] != "passive"]
    number = js_number(chosen)
    options, selected = [("", "Unlinked assumption")], 0
    for s in shown:
        options.append((js_string(s.get("id")), f"{esc_text(s.get('name'))} · {s['kind']}"))
        if _number_is(number, s.get("id")):
            selected = len(options) - 1
    if chosen is not None and not any(_number_is(number, s.get("id")) for s in shown):
        options.append((esc_text(chosen), f"Unavailable skill #{esc_text(chosen)}"))
        selected = len(options) - 1
    return options, selected


def effect_options(choices: list[dict], skill, effect) -> tuple[list[tuple[str, str]], int]:
    """A link's effect list (``effectOptions``): the linked active skill's supporting effects, and the one chosen."""
    linked = _linked(choices, skill)
    effects = ([e for e in _list(linked.get("specs")) if isinstance(e, dict)]
               if linked is not None and linked["kind"] == "active" else [])
    number = js_number(effect)
    options, selected = [("", "No specific effect")], 0
    for e in effects:
        options.append((js_string(e.get("id")), f"{esc_text(e.get('text'))} · effect Lv {esc_text(e.get('unlock'))}"))
        if _number_is(number, e.get("id")):
            selected = len(options) - 1
    if effect is not None and not any(_number_is(number, e.get("id")) for e in effects):
        options.append((esc_text(effect), f"Unavailable effect #{esc_text(effect)}"))
        selected = len(options) - 1
    return options, selected


def level_max(choices: list[dict], skill):
    """A linked skill's highest minimum: 20 for a stigma, else what can be bought (10 when unknown)."""
    linked = _linked(choices, skill)
    if linked is not None and linked["kind"] == "stigma":
        return 20
    return linked.get("buy_max") if linked is not None and _truthy(linked.get("buy_max")) else 10


def clamp_level(maximum, text: str) -> str:
    """A minimum field after its link changes: within 1 and the new maximum (1 when it was empty)."""
    current = js_number(field_value(text))
    pick = current if current and not math.isnan(current) else 1.0
    return field_text(_js_max(1.0, _js_min(js_number(js_string(maximum)), pick)))


def _read(values: dict, keys: tuple, texts: tuple, flags: tuple = (), empty_none: tuple = LINKS) -> dict:
    out = {}
    for key in keys:
        value = values[key]
        if key in texts:
            out[key] = value
        elif key in flags:
            out[key] = bool(value)
        elif key in empty_none and value == "":
            out[key] = None
        else:
            out[key] = js_number(value)
    return out


def read_action(values: dict) -> dict:
    """An action-time window from its fields' values (a number field's as ``field_value`` reads it, a list's chosen
    value, the box's state)."""
    return _read(values, ACTION_KEYS, ("name",), ("reserve_cooldown",))


def read_reduction(values: dict) -> dict:
    return _read(values, REDUCTION_KEYS, ("name", "kind"))


def read_pressure(values: dict, reductions: list[dict], before) -> dict:
    """A scenario from its fields, its reduction windows, and what an import gave it (its evidence, timed hits and
    benchmark), kept from before."""
    out = _read(values, PRESSURE_KEYS, ("name",), empty_none=("healing_duration_s",))
    out["reductions"] = [read_reduction(r) for r in reductions]
    before = before if isinstance(before, dict) else {}
    for key in CARRIED:
        if _truthy(before.get(key)):
            out[key] = before[key]
    return out


def read_survival(preserve: bool, floor: str, current: str, actions: list[dict], opponents: list[dict]) -> dict:
    """The options (``read``): the HP kept, the current HP for the scenarios, the action-time windows and scenarios."""
    return {"preserve_hp": preserve, "min_node_hp": js_number(floor), "current_hp": None if current == "" else js_number(current),
            "action_windows": actions, "opponents": opponents}


def new_pressure(count: int) -> dict:
    return {"name": f"Pressure {count + 1}", "burst_damage": 0, "pressure_dps": 0, "window_s": 5, "healing_hps": 0,
            "healing_delay_s": 0, "healing_duration_s": None, "reserve_hp": 1}


def new_reduction() -> dict:
    return {"name": "Assumed reduction", "kind": "defensive", "delay_s": 0, "duration_s": 0, "reduction_pct": 0}


def new_action(count: int) -> dict:
    return {"name": f"Tactical time {count + 1}", "start_s": 0, "duration_s": 0}


def encounter_line(e: dict) -> str:
    return f"{esc_text(e.get('label'))} · {esc_text(e.get('mode'))}"


def benchmark_problem(scenarios: int, sizes: list[int], scale: str) -> str:
    """Why opponent benchmarks cannot be imported (in the web page's order), else nothing: no room, no files, too many
    or too large, no scale."""
    if scenarios >= MOST:
        return FULL
    if not sizes:
        return NO_FILES
    if len(sizes) + scenarios > MOST:
        return TOO_MANY
    if any(size > RESULTS_MIB * 1024 * 1024 for size in sizes) or sum(sizes) > RESULTS_MIB * 1024 * 1024:
        return TOO_BIG
    if scale == "":
        return NO_SCALE
    return ""


def reading_opponent(index: int, count: int, name: str) -> str:
    return f"Reading opponent {index + 1} of {count}: {name}"


def benchmark_failed(name: str, why: str) -> str:
    return f"{name}: {why}. No scenarios from this batch were added."


def benchmarks_imported(count: int) -> str:
    return f"{count} opponent benchmarks imported. Review current HP, healing and defensive windows before optimizing."
