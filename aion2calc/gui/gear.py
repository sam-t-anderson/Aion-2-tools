"""The Gear & Advice page's words (0.2.443), as pages/gear.js writes them: the characters to choose, the advice kept
from a run and its progress, the inventory's rows, the item panel (enchant level, random rolls, skill options, note)
and its checks, and the catalog's search; and pages/screen-read.js's summary of the Title window pages read. The page
(``gear_page.py``) draws them.
"""
from __future__ import annotations

import html
import urllib.parse

from . import character as c
from .news import when
from .results import _dict, _list, cap

SUBTITLE = "what to wear from your inventory, goal gear, upgrade path, arcana, pantheon, genus insight — on simulated DPS"
NO_CHARACTERS = "Import a character on My Character first."
NOTE = ("Import the character on My Character first. The official page shows only equipped items: add bag and warehouse "
        "items below so the planner can use them. Fights you import on Combat Logs are matched to the gear the character "
        "wore and calibrate the model.")
INVENTORY_HEADS = ["Slot", "Item", "Rolls", "Skill options", "Source", ""]
INVENTORY_NOTE = ("Search the catalog below to add bag and warehouse items. The item panel takes the enchant level, the "
                  "rolled stats and the skill options; <b>Edit</b> changes them later. An item added without its rolls "
                  "counts the expected rolls of its pool.")
SEARCH_HINT = "search the catalog to add an item"
TITLES_NOTE = ("The official page shows only equipped titles. To read the ones you own from the game, open its Title "
               "window, tick <b>Show unacquired titles only</b> and read every page (scroll for the next): each title of "
               "your faction that no page lists is one you own, and the game's <i>Total Collection Status</i> checks the "
               "count.")
TITLES_LIST_NOTE = ("One title name per line: type them, or put the titles read above in the list. Nothing is saved until "
                    "you press Save titles.")
NOT_IN_CATALOG = "This entry is not in the catalog: remove it and add it again."
SAVE_GENUS_FIRST = "Save your Genus lines before running advice."
SAVE_GENUS_TOAST = "Save your Genus lines first."
CALCULATING = "Calculating advice…"
DONE = "Advice complete."
DONE_NOTE = "Scroll down below your inventory to see the recommendations."
DONE_TOAST = "Advice complete. Scroll down or choose View results."
GENUS_CHANGED = "Genus allocations changed during calculation. Run advice again."
GENUS_SAVED = "Genus lines saved. Run advice again to update recommendations."
ROLL_VALUE = "Enter a value for every chosen roll."
SKILL_NAME = "Choose a skill on every option line, or remove the line."
LIST_FILLED = "The list is filled in: check it, then press Save titles."


def character_line(row: dict) -> str:
    return f"{c.esc_text(row.get('name'))} · {c.esc_text(row.get('class_name'))} · {c.esc_text(row.get('region'))}"


def kept_text(kept: dict) -> str:
    """The line over the advice kept from the last run (``keptAdviceText``, rich text): when it was calculated, what
    has changed since."""
    since = []
    if c._truthy(kept.get("inputs_changed")):
        since.append("Your gear, inventory, Genus lines or titles have changed since.")
    if c._truthy(kept.get("version_changed")):
        since.append(f"Version {html.escape(c.esc_text(kept['version']))} of the app calculated it."
                     if c._truthy(kept.get("version")) else "An earlier version of the app calculated it.")
    at = kept.get("at")
    moment = when(at * 1000 if isinstance(at, (int, float)) and not isinstance(at, bool) else None)
    return (f"Your last advice, calculated {html.escape(moment)}. {''.join(t + ' ' for t in since)}<b>Run advice</b> "
            "calculates it again with your current gear and fights.")


RUNNING_NOTE = ("Working through your build and recommendations. Results will appear below your inventory; a View "
                "results button will be shown here when ready.")


def progress(job: dict, now: float) -> tuple[str, str, str]:
    """The advice job's place (``renderAdviceProgress``): running (its line, rich text with the log's last line in
    bold, and the log's last six lines), done, or failed (why)."""
    if job.get("status") == "running":
        elapsed = max(0, int(now - job.get("started", now)))
        lines = job.get("log") or []
        last = c.esc_text(lines[-1]) if lines and c._truthy(lines[-1]) else "Starting…"
        return ("running", f"Calculating advice · {elapsed}s · <b>{html.escape(last)}</b>",
                "\n".join(c.esc_text(x) for x in lines[-6:]))
    if job.get("status") == "done":
        return "done", DONE, DONE_NOTE
    return "error", f"Advice did not complete: {c.esc_text(job.get('error') or 'Unknown error')}", ""


# ------------------------------------------------------------------ the inventory
def rolls_of(entry: dict) -> str:
    """An entry's rolls: their text, else each stat and value."""
    if c._truthy(entry.get("rolls_text")):
        return c.js_string(entry["rolls_text"])
    rolls = entry.get("rolls")
    if isinstance(rolls, list) and rolls:
        return ", ".join(f"{c.esc_text(r[0] if isinstance(r, list) and r else None)} +"
                         f"{c.esc_text(r[1] if isinstance(r, list) and len(r) > 1 else None)}" for r in rolls)
    return ""


def skills_of(entry: dict) -> str:
    return ", ".join(f"{c.esc_text(s[0] if isinstance(s, list) and s else None)} +"
                     f"{c.esc_text(s[1] if isinstance(s, list) and len(s) > 1 else None)}" for s in _list(entry.get("skills")))


def item_text(entry: dict) -> str:
    """An entry's name and enchant level, and its note."""
    enchant = entry.get("enchant") if c._truthy(entry.get("enchant")) else 0
    return f"{c.esc_text(entry.get('name'))} +{c.js_string(enchant)}"


def slot_text(entry: dict) -> str:
    return c.esc_text(entry.get("slot") or entry.get("category") or "")


def search_path(query: str) -> str:
    return f"/api/items?search={urllib.parse.quote(query, safe='')}&limit=30"


def options_path(slug: str, cls) -> str:
    return (f"/api/items/{urllib.parse.quote(str(slug), safe='')}/options?class="
            f"{urllib.parse.quote(c.esc_text(cls) if c._truthy(cls) else '', safe='')}")


# ------------------------------------------------------------------ the item panel
def new_entry(opt: dict, slug: str, entry: dict | None) -> dict:
    """What the item panel starts from: an entry's enchant level (at most the item's), rolls, skill options and note,
    or a new entry's."""
    entry = entry or {}
    rolls = entry.get("rolls") if isinstance(entry.get("rolls"), list) else []
    count = int(c.js_number(opt.get("roll_count")) or 0)
    enchant = c.js_number(entry.get("enchant") if c._truthy(entry.get("enchant")) else 0)
    return {"slug": slug, "id": entry.get("id") or None,
            "enchant": int(min(enchant, c.js_number(opt.get("max_enchant")))),
            "rolls": [({"stat": rolls[i][0], "value": rolls[i][1]} if i < len(rolls) and c._truthy(rolls[i]) else None)
                      for i in range(count)],
            "skills": [[s[0], s[1]] for s in _list(entry.get("skills")) if isinstance(s, list) and len(s) >= 2],
            "note": entry.get("note") or ""}


def slots(opt: dict, enchant: int) -> int:
    skills = _dict(opt.get("skills"))
    return int(c.js_number(skills.get("base")) + c.js_number(skills.get("per_enchant")) * enchant)


def used(ed: dict) -> float:
    """The option levels the panel's lines take (``+l || 0`` each)."""
    total = 0.0
    for _name, level in ed["skills"]:
        x = c.js_number(level)
        total += x if x == x else 0.0
    return total


def step_text(opt: dict, level: int) -> str:
    """The catalog's stats at an enchant level (``stepText``): the step reached, after +15's when past it."""
    if not level:
        return ""
    steps = [s for s in _list(opt.get("enchant_steps")) if isinstance(s, dict)]
    reached = [s for s in steps if s.get("level", 0) <= level and (level <= 15 or s.get("level", 0) > 15)]
    at = reached[-1] if reached else None
    base = next((s for s in steps if s.get("level") == 15), None) if level > 15 else None
    return ", then ".join(s.get("stats") for s in (base, at) if s is not None and c._truthy(s.get("stats")))


def heading(opt: dict, ed: dict) -> tuple[str, str, str]:
    """The panel's name, the item's category, level and grade, and whether it adds or edits."""
    level = f"item level {c.js_string(opt['item_level'])}" if c._truthy(opt.get("item_level")) else ""
    facts = " · ".join(c.esc_text(x) for x in (opt.get("category"), level, opt.get("grade")) if c._truthy(x))
    return c.esc_text(opt.get("name")), facts, "editing your inventory entry" if ed.get("id") else "adding to your inventory"


def enchant_note(opt: dict, ed: dict) -> str:
    step = step_text(opt, ed["enchant"])
    if step:
        return f"+{ed['enchant']}: {step}"
    return (f"enhances to +{c.js_string(opt.get('max_enchant'))}" if c._truthy(opt.get("enchant_known"))
            else "the catalog lists no enhancement limit for this item")


def rolls_note(opt: dict) -> str:
    return (f"{c.js_string(opt.get('roll_count'))} on this item, each a different stat. Leave every line empty if you do not "
            "know them: the planner then assumes the expected rolls of its pool.")


def roll_choices(opt: dict) -> list[tuple[str, str]]:
    """A roll line's stats: none, then each of the item's pool with its range (and whether it is scored)."""
    return [("", "— not entered —")] + [
        (c.esc_text(r.get("stat")), f"{c.esc_text(r.get('stat'))} ({c.esc_text(r.get('range'))})"
                                    + ("" if c._truthy(r.get("scored")) else " · not scored"))
        for r in _list(opt.get("rolls")) if isinstance(r, dict)]


def roll_option(opt: dict, stat) -> dict | None:
    return next((r for r in _list(opt.get("rolls")) if isinstance(r, dict) and r.get("stat") == stat), None)


def skills_note(opt: dict, ed: dict) -> str:
    skills = _dict(opt.get("skills"))
    if c._truthy(opt.get("arcana")):
        return (f"A {c.esc_text(opt.get('grade') or '')} card holds {c.js_string(skills.get('base'))} option levels plus one "
                f"per enchant level, {slots(opt, ed['enchant'])} at +{ed['enchant']}, at most "
                f"+{c.js_string(skills.get('max_level'))} on one skill.")
    return (f"One option reaches +{c.js_string(skills.get('max_level'))}; "
            + ("the pool lists what this item rolls for your class." if _list(skills.get("pool"))
               else "the catalog lists no option pool for this item."))


def skill_groups(opt: dict) -> list[tuple[str, list[str]]]:
    """A skill option's choices: the item's option pool, then the class's other skills."""
    skills = _dict(opt.get("skills"))
    pool, others = [c.esc_text(x) for x in _list(skills.get("pool"))], [c.esc_text(x) for x in _list(skills.get("others"))]
    groups = []
    if pool:
        groups.append(("This item's option pool", pool))
    if others:
        groups.append(("Other skills" if pool else "Skills", others))
    return groups


def problem(ed: dict) -> str:
    """Why the panel cannot be saved: a chosen roll without its value, or an option line without its skill."""
    if any(r is not None and c.field_value(c.esc_text(r.get("value"))) == "" for r in ed["rolls"]):
        return ROLL_VALUE
    if any(not name for name, _level in ed["skills"]):
        return SKILL_NAME
    return ""


def save_body(character: str, ed: dict) -> tuple[str, dict]:
    """What the panel sends: its entry to update, or the catalog item to add."""
    body = {"character": character, "enchant": ed["enchant"],
            "rolls": [[r["stat"], c.js_number(c.field_value(c.esc_text(r["value"])))] for r in ed["rolls"] if r is not None],
            "skills": [[name, level] for name, level in ed["skills"]], "note": ed["note"]}
    if ed.get("id"):
        return "/api/inventory/update", c.to_json({**body, "id": ed["id"]})
    return "/api/inventory/add", c.to_json({**body, "slug": ed["slug"]})


def save_error(why: str) -> str:
    """A refusal as the panel says it (``e.message.replace(/^\\w*Error:\\s*/, "")``)."""
    import re
    return re.sub(r"^\w*Error:\s*", "", why)


# ------------------------------------------------------------------ the Title window pages read
def title_summary(t: dict) -> dict:
    """What the pages read say (``titleReadSummary``'s ``draw``): its error, its notes, the pages, the counts' line, the
    titles owned and not acquired."""
    if t.get("error"):
        return {"error": c.esc_text(t["error"])}
    notes = [c.esc_text(n) for n in _list(t.get("notes"))]
    pages = [p for p in _list(t.get("pages")) if isinstance(p, dict)]
    owned, unacquired = _list(t.get("owned")), _list(t.get("unacquired"))
    line = (f"Not acquired yet: <b>{len(unacquired)}</b> · "
            + (f"you own: <b>{len(owned)}</b>" if c._truthy(t.get("basis")) else "the titles you own are not worked out yet")
            + (f" · {html.escape(cap(t['faction']))}: {c.esc_text(t.get('faction_titles'))} titles in the app's catalog"
               if c._truthy(t.get("faction")) else "")
            + (f" · the game counts {c.esc_text(_dict(t['collection']).get('owned'))} of "
               f"{c.esc_text(_dict(t['collection']).get('total'))}" if c._truthy(t.get("collection")) else ""))
    return {"notes": notes, "pages": pages, "line": line, "owned": [c.esc_text(x) for x in owned],
            "unacquired": [c.esc_text(x) for x in unacquired]}


def page_choice(page: dict) -> str:
    """A page's "Show unacquired titles only" as its list holds it: "true", "false" or "" (not seen)."""
    value = page.get("unacquired_only")
    return "" if value is None else c.js_string(value)


def filled(names: list[str], have: str, add: bool) -> str:
    """The titles list filled with the titles owned: in place of its lines, or added to them."""
    if not add:
        return "\n".join(names)
    kept = [x.strip() for x in have.split("\n") if x.strip()]
    return "\n".join(kept + [name for name in names if name not in kept])
