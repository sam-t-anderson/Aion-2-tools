"""The Build Planner page's words (0.2.439), as pages/planner.js and progression-budgets.js write them: the welcome
card, the builds' list, the modes, the server-reported point budgets, the checks before an optimization and the
messages of its jobs. The page (``planner_page.py``) draws them.
"""
from __future__ import annotations

import urllib.parse

from .results import _dict, _list, _number, _whole_number, cap, js_text, n0

DISCORD = "https://discord.gg/9y6zkUyvBv"
WELCOME_SUB = "three steps to your best build"
HERO_TITLE = "Aion 2 Calc"
HERO_TEXT = ("Plan your AION 2 build, check your gear and learn from your fights. Everything runs on this computer; the game "
             "database updates itself.")
#: The welcome card's three steps: the numeral, the title, the words, the button and the page it opens.
STEPS = (("I", "Import your character", "Search your name on the official site: gear, rolls, skills, stigmas and Daevanion "
          "come in.", "My Character", "character"),
         ("II", "Get your advice", "Best gear from your inventory, goal gear, arcana, titles, pantheon and genus insight, "
          "ranked by DPS gain.", "Gear & Advice", "gear"),
         ("III", "Add your fights", "Record them with the Live Meter, or import an AbyssLogs link under Combat Logs: see "
          "your rotation against the optimum, and the model learns from them.", "Live Meter", "meter"))
PLANNER_SUB = "optimized builds — copy each window into the game"
MODES = (("pve", "PvE"), ("pvp", "PvP damage (experimental)"), ("world", "World PvP (experimental)"))
#: The four budgets' fields: their key, placeholder and tooltip (as the web page's inputs).
FIELDS = (("skill", "Skill budget", "Highest server-reported skill points, or enter explicitly"),
          ("stigma", "Stigma budget", "Highest server-reported stigma points, or enter explicitly"),
          ("daevanion", "Daevanion budget", ""),
          ("ariel", "Ariel crystal (optional)", "Daevanion Crystal: Ariel for the level-45 Ariel board: highest "
           "server-reported, or enter explicitly; empty spends none unless the server reports a total"))
NO_BUILDS = "No optimized builds yet — pick a class and press Optimize."
LOADING = "loading"
LOADING_BUDGETS = "Loading server-reported budgets…"
NO_BUDGETS = "Server budgets unavailable. Enter your available points explicitly."
NEED_BUDGETS = "Enter all three available point budgets (0–10000)."
BAD_ARIEL = "The Ariel crystal budget is a whole number from 0 to 10000, or empty."
CHECKED = "Community presets checked."
UNCHECKED = "Showing saved presets or examples; server refresh unavailable."
KEYS = ("skill", "stigma", "daevanion")


def preset_line(r: dict) -> str:
    """A build in the list: the community's or an example, its label (or class), and its weighted or scenario DPS."""
    label = r.get("preset_label") or cap(r.get("class"))
    figure = (f"{n0(r.get('score'))} weighted DPS" if r.get("scoring_policy") else
              f"{n0(_dict(r.get('dps')).get(r.get('scenario')) if isinstance(r.get('scenario'), str) else None)} "
              f"{js_text(r.get('scenario') or '')} DPS")
    line = f"{'Community · ' if r.get('canonical') else 'Example · '}{js_text(label)} · {figure}"
    return " ".join(line.split())                         # as an <option> shows it: its spaces collapsed


def chosen_path(results: list[dict], state: dict) -> str:
    """The build to show: the one shown last, else one of the class and mode chosen last, else the first."""
    paths = [r.get("path") for r in results]
    if state.get("path") in paths:
        return state["path"]
    choice = _dict(state.get("choice"))
    if choice:
        for r in results:
            if r.get("class") == choice.get("class") and r.get("mode") == choice.get("mode"):
                return r.get("path")
    return paths[0] if paths else ""


def mode_of(view: dict) -> str:
    """The mode a build was optimized for, as the mode list names it."""
    if view.get("scenario") == "pvp_world":
        return "world"
    return "pvp" if js_text(view.get("scenario") or "").startswith("pvp") else "pve"


def progression_path(cls: str, context: dict | None = None) -> str:
    """The log server's reported totals for a class (through the app's community proxy)."""
    query = {"class": cls}
    for key in ("region", "game_patch"):
        if (context or {}).get(key):
            query[key] = (context or {})[key]
    return "/api/v1/progression?" + urllib.parse.urlencode(query)


def _budget(value) -> int | None:
    number = _whole_number(value)
    return number if number is not None and 0 <= number <= 10000 else None


def budgets(result, cls: str, context: dict | None = None) -> dict:
    """The highest server-reported totals for a class (progression-budgets.js ``read``): its points (the Ariel
    crystal's optional), the observations they come from, and the note that they are not verified caps."""
    if not isinstance(result, dict):
        raise ValueError("No progression answer")
    rows = [r for r in _list(result.get("observations")) if isinstance(r, dict) and r.get("class_name") == cls
            and all(_budget(r.get(key)) is not None for key in KEYS)]
    points = {key: max(_budget(r.get(key)) for r in rows) if rows else None for key in KEYS}
    seen = [n for n in (_budget(r.get("ariel")) for r in rows) if n is not None]
    points["ariel"] = max(seen) if seen else None
    if rows:
        pooled = not (context or {}).get("region") or not (context or {}).get("game_patch")
        note = (f"Highest server-reported totals from {len(rows)} class/context observations; reported totals and allocated "
                "lower bounds are not verified game caps. " + ("Region/build is unspecified; available contexts are pooled."
                                                               if pooled else "Matched region/build only."))
    else:
        note = "No server-reported totals for this class/context. Enter available points explicitly."
    return {"points": points, "rows": rows, "note": note}


def whole(text: str) -> int | None:
    """A budget field's whole number, as ``+value`` of a number input reads it; None when empty or not whole."""
    number = _number(text.strip()) if text.strip() else None
    return int(number) if number is not None and number.is_integer() else None


def optimize_problem(fields: dict[str, str]) -> str:
    """Why an optimization cannot start: a budget missing or out of range, or the Ariel crystal's; else nothing."""
    for key in KEYS:
        number = whole(fields.get(key, ""))
        if number is None or not 0 <= number <= 10000:
            return NEED_BUDGETS
    ariel = fields.get("ariel", "").strip()
    if ariel and (whole(ariel) is None or not 0 <= whole(ariel) <= 10000):
        return BAD_ARIEL
    return ""


def optimize_body(cls: str, mode: str, fields: dict[str, str]) -> dict:
    """What ``/api/optimize`` is asked: the class, the mode and the budgets (the Ariel crystal's when given)."""
    body = {"class": cls, "mode": mode, "skill_points": whole(fields["skill"]),
            "stigma_points": whole(fields["stigma"]), "daevanion": whole(fields["daevanion"])}
    if fields.get("ariel", "").strip():
        body["ariel"] = whole(fields["ariel"])
    return body


def last(log, otherwise: str) -> str:
    """A job's last line (``log.at(-1)``), or what to say while it has none."""
    return js_text(log[-1]) if isinstance(log, list) and log and log[-1] else otherwise


def done_message(view) -> str:
    """After an optimization: why its preset was or was not submitted, else done."""
    return js_text(_dict(_dict(view).get("preset_submission")).get("reason") or "done")


def weight_status(job: dict) -> str:
    """The stat priority's line while its job runs, or why it failed."""
    if job.get("status") == "error":
        return f"Stat priority failed: {js_text(job.get('error'))}"
    return last(job.get("log"), "Calculating stat priority…")
