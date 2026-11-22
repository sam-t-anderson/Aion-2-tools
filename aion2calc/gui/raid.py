"""The Raid Planner's rules (raid.js, 0.2.490), as the web planner keeps, reads and changes a plan, in its words.

A plan is an "a2plan" document: tokens (players, enemies, markers, AoE zones) whose places are keyframed over the
plan's length and drawn in between along a straight line, and party-buff windows. The plans are the web planner's own:
kept under ``a2plans`` in the app's interface data (the browser's storage until 0.2.482), so the app's window and the
web page share them, with the plan shown last (``a2plan-current``) and a published plan's credential
(``a2plan-owners``). Each save also hands the app the whole set for its overlay (``/api/plans/saved``).

What a plan holds reaches the page as raid.js lets it: text as text, a number only as a number (``num``) and a colour
only as a hex colour (``col``).
"""
from __future__ import annotations

import base64
import functools
import math
import random
import re
from decimal import ROUND_HALF_UP, Decimal

from . import builds as b
from .builds import _MISSING, get, truthy
from .character import js_number, js_string
from .settings_looks import _JS_SPACE, _atob, js_parse, js_trim
from .theme import js_round

# ------------------------------------------------------------------ what the planner keeps
PLANS = "a2plans"                          # every plan, by its id
OWNERS = "a2plan-owners"                   # a published plan's credential, by the plan's id
CURRENT = "a2plan-current"                 # the plan last shown, so the planner reopens on it

RAID_CLASSES = ("Templar", "Gladiator", "Assassin", "Ranger", "Sorcerer", "Spiritmaster", "Cleric", "Chanter")
TOKEN_COLORS = ("#e66a5a", "#39c2e0", "#6fcf7a", "#e9a43a", "#a46cf0", "#f05a8c", "#5bc0de", "#b9984f", "#7fd6a8",
                "#6fa8dc", "#d4b45a", "#9fd36f")
RAID_MARKERS = ("A", "B", "C", "D", "1", "2", "3", "4")
KINDS = (("player", "Players"), ("enemy", "Enemies"), ("marker", "Markers"), ("aoe", "AoE zones"))
SPEEDS = (0.5, 1, 2, 4)
TOKEN = "#39c2e0"                          # a token's colour where the plan gives none that is one
GOLD = "gold"                              # a buff's colour when no player gives it (``var(--gold)``)
BASE = "abcdefghijklmnopqrstuvwxyz0123456789"

# ------------------------------------------------------------------ its words
TITLE = "Raid & boss planner"
SUBTITLE = "drag player tokens on the map and scrub the timeline to plan movement, cooldowns and party buffs"
NEW_PLAN = "New plan"
FIRST_PLAN = "My first plan"
UNTITLED = "Untitled"
NOT_A_CODE = "That is not an a2plan share code"
NOT_A_PLAN = "Not an a2plan file"
BAD_OWNER = "Invalid ownership backup"
ATOB = "Failed to execute 'atob' on 'Window': The string to be decoded is not correctly encoded."


class PlanError(ValueError):
    """What the planner throws (``throw new Error(...)``), its words as given."""


# ------------------------------------------------------------------ JavaScript's values
def text(value) -> str:
    """``esc(value)``'s text: ``String(value ?? "")``."""
    return "" if value is None or value is _MISSING else js_string(value)


def yes(value) -> bool:
    """``value`` as a condition: a property the object has not (``undefined``) false."""
    return value is not _MISSING and truthy(value)


def js_str(value) -> str:
    """``String(value)``: a property the object has not "undefined"."""
    return "undefined" if value is _MISSING else js_string(value)


def number_of(value) -> float:
    """``Number(value)``, a property the object has not (``undefined``) NaN."""
    return math.nan if value is _MISSING else js_number(value)


def num(value, fallback: float = 0.0) -> float:
    """``num(v, fallback)``: the number a value reads as, or ``fallback`` where it reads as none that is finite."""
    n = number_of(value)
    return n if math.isfinite(n) else fallback


def col(value, fallback: str = TOKEN) -> str:
    """``col(c)``: a colour only as a hex colour (``#rgb`` to ``#rrggbbaa``), else ``fallback``."""
    words = js_str(value)
    return words if re.fullmatch(r"#[0-9a-fA-F]{3,8}", words) else fallback


def finite(value) -> bool:
    """``Number.isFinite(value)``: a number, not a text that reads as one."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fixed(value: float, digits: int) -> str:
    """``value.toFixed(digits)``: a half rounded up, as the decimal the number exactly is."""
    if math.isnan(value):
        return "NaN"
    if abs(value) >= 1e21:
        return js_string(value)
    if value == 0:
        value = 0.0                                          # (-0).toFixed is "0"
    return format(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), "f")


def js_slice(words: str, size: int) -> str:
    """``words.slice(0, size)``, in UTF-16 code units: a character cut in two keeps its first half."""
    return words.encode("utf-16-le", "surrogatepass")[: 2 * size].decode("utf-16-le", "surrogatepass")


def parse_int(value):
    """``parseInt(value, 10)``: the whole number ``String(value)`` starts with (after white space), or None (NaN)."""
    m = re.match(r"[+-]?[0-9]+", js_str(value).lstrip(_JS_SPACE))
    return int(m.group(0)) if m else None


def js_min(*values: float) -> float:
    """``Math.min``: NaN when any is."""
    return math.nan if any(math.isnan(v) for v in values) else min(values)


def js_max(*values: float) -> float:
    """``Math.max``: NaN when any is."""
    return math.nan if any(math.isnan(v) for v in values) else max(values)


def _plus(a, n: float) -> float:
    """``a + n`` read back as a number: a text (or an object, as its text) is joined to the number's, as JavaScript
    joins them."""
    if a is not _MISSING and isinstance(a, (str, list, dict)):
        return number_of(js_string(a) + js_string(n))
    return number_of(a) + n


def js_sort(items: list, compare) -> None:
    """``items.sort(compare)`` as V8 sorts: below 64 items, the first ascending (or strictly descending, reversed)
    run, then each other item put in by binary search; a comparison that is not a number reads as equal. Longer
    lists by Python's own stable sort, which orders them the same when the comparison is consistent."""
    n = len(items)
    if n < 2:
        return
    if n >= 64:
        items.sort(key=functools.cmp_to_key(compare))
        return
    run, descending = 2, compare(items[1], items[0]) < 0
    for i in range(2, n):
        order_ = compare(items[i], items[i - 1])
        if (order_ >= 0) if descending else (order_ < 0):
            break
        run += 1
    if descending:
        items[:run] = items[:run][::-1]
    for start in range(run, n):
        pivot, left, right = items[start], 0, start
        while left < right:
            mid = left + ((right - left) >> 1)
            if compare(pivot, items[mid]) < 0:
                right = mid
            else:
                left = mid + 1
        items[left + 1:start + 1] = items[left:start]
        items[left] = pivot


def strictly(a, b_) -> bool:
    """``a === b`` (``builds.same``)."""
    return b.same(a, b_)


# ------------------------------------------------------------------ a plan
def uid(pick=random.random) -> str:
    """``Math.random().toString(36).slice(2, 9)``: seven of a–z and 0–9."""
    seed = pick()
    out = []
    for _ in range(7):
        seed *= 36
        digit = int(seed)
        out.append("0123456789abcdefghijklmnopqrstuvwxyz"[digit])
        seed -= digit
    return "".join(out)


def new_plan(name: str, now: int) -> dict:
    """``newPlan(name)``: an empty plan of a minute on a square arena."""
    return {"format": "a2plan", "version": 1,
            "meta": {"name": name or NEW_PLAN, "author": "", "notes": "", "created": now, "updated": now},
            "arena": {"kind": "square"}, "duration": 60, "tokens": [], "buffs": [], "source": {}, "encounter": {}}


def clean_encounter(enc) -> dict:
    """``cleanEncounter(enc)``: the boss a plan is for, kept to its NPC code, its map and its name (80 at most)."""
    if not isinstance(enc, dict):
        return {}
    out = {}
    npc = parse_int(enc.get("npc_id", _MISSING))
    if npc is not None and 0 < npc < 1e10:
        out["npc_id"] = npc
    where = parse_int(enc.get("map_id", _MISSING))
    if where is not None and 0 < where < 1e10:
        out["map_id"] = where
    boss = enc.get("boss")
    if isinstance(boss, str) and js_trim(boss):
        out["boss"] = js_slice(js_trim(boss), 80)
    return out


def aoe_span(tk) -> float:
    """``aoeSpan(tk)``: an area's reach from its place, as a share of the arena: its radius, or a line's length."""
    n = number_of(get(tk, "length" if strictly(get(tk, "shape", _MISSING), "line") else "radius", _MISSING))
    return max(0.005, n if yes(n) else 0.14)


def position(tk, t: float):
    """``tokenPos(tk, t)``: a token's place at ``t`` along its keyframes, held at the first before it and at the last
    after it; None with none. A place that does not read as a number is NaN, as there."""
    frames = get(tk, "keyframes", _MISSING)
    if not isinstance(frames, list) or not frames:
        return None

    def at(k, key):
        return number_of(get(k, key, _MISSING))
    first, last = frames[0], frames[-1]
    if t <= at(first, "t"):
        return at(first, "x"), at(first, "y")
    if t >= at(last, "t"):
        return at(last, "x"), at(last, "y")
    for i in range(1, len(frames)):
        if t <= at(frames[i], "t"):
            a, b_ = frames[i - 1], frames[i]
            f = (t - at(a, "t")) / js_max(1e-6, at(b_, "t") - at(a, "t"))
            return (_plus(get(a, "x", _MISSING), (at(b_, "x") - at(a, "x")) * f),
                    _plus(get(a, "y", _MISSING), (at(b_, "y") - at(a, "y")) * f))
    return at(last, "x"), at(last, "y")


def on_map(tk, t: float) -> bool:
    """``onMap(tk, t)``: within its ``from`` and ``until``, where it has them (a recorded add, a faded summon)."""
    since, until = get(tk, "from", _MISSING), get(tk, "until", _MISSING)
    return not (finite(since) and t < since) and not (finite(until) and t > until)


def drawn(tk, t: float):
    """Where the map draws a token at ``t`` (``layout``): None when hidden, off the map then, or without a place."""
    if yes(get(tk, "hidden", _MISSING)) or not on_map(tk, t):
        return None
    return position(tk, t)


def set_keyframe(tk: dict, t: float, x: float, y: float) -> None:
    """``setKeyframe(tk, t, x, y)``: its place at ``t`` (to a tenth of a second) set, or one within 0.05 s moved;
    placed outside the time a recording had it, it is on the map then too."""
    t = js_round(t * 10) / 10
    if finite(tk.get("from")) and t < tk["from"]:
        del tk["from"]
    if finite(tk.get("until")) and t > tk["until"]:
        del tk["until"]
    x, y = js_max(0.0, js_min(1.0, x)), js_max(0.0, js_min(1.0, y))
    frames = tk.get("keyframes")
    if not isinstance(frames, list):
        frames = tk["keyframes"] = []
    for frame in frames:
        if isinstance(frame, dict) and abs(number_of(frame.get("t", _MISSING)) - t) < 0.05:
            frame["x"], frame["y"] = x, y
            return
    frames.append({"t": t, "x": x, "y": y})
    js_sort(frames, _by_time)


def _by_time(a, b_) -> float:
    """``(a, b) => a.t - b.t``: a difference that is not a number reads as equal."""
    d = number_of(get(a, "t", _MISSING)) - number_of(get(b_, "t", _MISSING))
    return 0 if math.isnan(d) else d


def plan_code(p: dict) -> str:
    """``planToCode(p)``: the plan's JSON in UTF-8, as base64."""
    return base64.b64encode(b.stringify(p).encode("utf-8")).decode("ascii")


def plan_from_code(code: str) -> dict:
    """``codeToPlan(code)``: a share code read back, its encounter cleaned; PlanError where it is not one."""
    try:
        raw = _atob(js_trim(code))
    except ValueError as problem:
        raise PlanError(ATOB) from problem
    p = js_parse(raw)
    if not isinstance(p, dict) or not strictly(p.get("format", _MISSING), "a2plan"):
        raise PlanError(NOT_A_CODE)
    p["encounter"] = clean_encounter(p.get("encounter"))
    return p


def import_doc(p: dict, plans: dict, now: int, make_id=uid) -> str:
    """``importDoc(p)``: a plan from a file, a code or the server, kept as a new plan; its id. What the planner draws
    from is put in where it is left out: its tokens and buffs (objects only), a length (60 s)."""
    meta = p.get("meta", _MISSING)
    if not yes(meta):
        meta = p["meta"] = {}
    if isinstance(meta, dict):
        meta["updated"] = now
    elif not isinstance(meta, list):                          # a text, a number or true: strict mode's TypeError
        kind = "string" if isinstance(meta, str) else "boolean" if isinstance(meta, bool) else "number"
        raise PlanError(f"Cannot create property 'updated' on {kind} '{js_string(meta)}'")
    p["encounter"] = clean_encounter(p.get("encounter"))
    p["tokens"] = [t for t in p["tokens"] if isinstance(t, (dict, list))] if isinstance(p.get("tokens"), list) else []
    p["buffs"] = [x for x in p["buffs"] if isinstance(x, (dict, list))] if isinstance(p.get("buffs"), list) else []
    length = number_of(p.get("duration", _MISSING))
    p["duration"] = _plain(length) if length > 0 else 60
    key = make_id()
    plans[key] = p
    return key


def _plain(n: float):
    """A number as JSON keeps it: a whole one whole."""
    return int(n) if math.isfinite(n) and n.is_integer() and abs(n) < 2 ** 53 else n


def ownership(doc) -> tuple:
    """A private ownership backup read (``a2plan-owner``): its credential and its plan; PlanError where it is not a
    valid one (an id of 6 to 16 letters and digits, an edit token of 20 or more, a whole revision, the log server's
    address, an a2plan)."""
    o = get(doc, "owner", _MISSING)
    token, revision = get(o, "edit_token", _MISSING), get(o, "revision", _MISSING)
    whole = (isinstance(revision, int) and not isinstance(revision, bool)) or (
        isinstance(revision, float) and revision.is_integer())
    if (not yes(o) or not re.fullmatch(r"[A-Za-z0-9]{6,16}", js_str(get(o, "id", _MISSING)))
            or not isinstance(token, str) or _units(token) < 20 or not whole
            or not re.match(r"https?://", js_str(get(o, "server", _MISSING)))
            or not strictly(get(get(doc, "plan", _MISSING), "format", _MISSING), "a2plan")):
        raise PlanError(BAD_OWNER)
    return o, doc["plan"]


def _units(words: str) -> int:
    return len(words.encode("utf-16-le", "surrogatepass")) // 2


# ------------------------------------------------------------------ the plans kept
def _kept(store, key: str) -> dict:
    """``JSON.parse(localStorage.getItem(key) || "{}")``, {} where it does not read as an object."""
    try:
        value = b.parse(store.value(key) or "{}")
    except (ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def raid_plans(store) -> dict:
    """``raidPlans()``: every plan kept, by id."""
    return _kept(store, PLANS)


def save_raid_plans(store, plans: dict) -> None:
    """``saveRaidPlans(all)``: the plans kept (their JSON as the web page writes it)."""
    store.setValue(PLANS, b.stringify(plans))


def owners(store) -> dict:
    """``owners()``: the published plans' credentials, by plan."""
    return _kept(store, OWNERS)


def save_owner(store, value: dict, key: str) -> None:
    """``saveOwner(value, id)``."""
    every = owners(store)
    every[key] = value
    store.setValue(OWNERS, b.stringify(every))


def remembered(store):
    """``rememberedCurrent()``: the plan shown last, or None."""
    try:
        return store.value(CURRENT) or None
    except Exception:                                        # noqa: BLE001 - a store that cannot be read
        return None


def remember(store, key) -> None:
    """``rememberCurrent()``."""
    if key:
        store.setValue(CURRENT, key)


def updated(p) -> float:
    """``p.meta?.updated || 0`` as the sort subtracts it."""
    value = get(get(p, "meta", _MISSING), "updated", _MISSING)
    return number_of(value) if yes(value) else 0.0


def order(plans: dict) -> list:
    """The plans' ids, the most recently saved first (``.sort((a, b) => b.updated - a.updated)``, stable)."""
    def key(item):
        n = updated(item[1])
        return -n if not math.isnan(n) else 0.0
    return [k for k, _p in sorted(b.entries(plans), key=key)]


def next_plan_id(plans: dict, current, kept):
    """``nextPlanId(all)``: the plan shown, else the one last shown, else the newest; None with none."""
    if current and yes(plans.get(current, _MISSING)):
        return current
    if kept and yes(plans.get(kept, _MISSING)):
        return kept
    ids = order(plans)
    return ids[0] if ids and ids[0] else None


def is_blank(key, p, owned: dict) -> bool:
    """``isBlank(id, p)``: an untouched plan, the starter or a New plan nothing was put in or written on, never
    published."""
    if not yes(p):
        return False
    meta = get(p, "meta", _MISSING)
    return (not _length(get(p, "tokens", _MISSING)) and not _length(get(p, "buffs", _MISSING))
            and not js_trim(text(_or_text(get(meta, "notes", _MISSING))))
            and not js_trim(text(_or_text(get(meta, "author", _MISSING))))
            and not clean_encounter(get(p, "encounter", _MISSING))
            and js_trim(text(_or_text(get(meta, "name", _MISSING)))) in (FIRST_PLAN, NEW_PLAN, "")
            and not yes(get(owned, key, _MISSING) if isinstance(key, str) else _MISSING))


def _or_text(value):
    """``value || ""``."""
    return value if yes(value) else ""


def _length(value) -> int:
    """``(value || []).length`` as a condition."""
    if isinstance(value, (list, str)):
        return len(value)
    return 0


# ------------------------------------------------------------------ what the page shows of it
def plan_label(p) -> str:
    """A plan in the Plan list: its name, and the boss it is for."""
    meta, enc = get(p, "meta", _MISSING), get(p, "encounter", _MISSING)
    name = get(meta, "name", _MISSING)
    boss = get(enc, "boss", _MISSING)
    return text(name if yes(name) else UNTITLED) + (" — " + text(boss) if yes(boss) else "")


def token_name(tk) -> str:
    """``tk.label || tk.cls || tk.kind``."""
    for key in ("label", "cls", "kind"):
        value = get(tk, key, _MISSING)
        if yes(value):
            return text(value)
    return text(get(tk, "kind", _MISSING))


def glyph(tk) -> str:
    """The letter on a token: a marker's label (or "?"); else the first letter of its label or class, or B for an
    enemy and P for a player, in capitals."""
    if strictly(get(tk, "kind", _MISSING), "marker"):
        label = get(tk, "label", _MISSING)
        return text(label if yes(label) else "?")
    label, cls = get(tk, "label", _MISSING), get(tk, "cls", _MISSING)
    first = (_first(label) if yes(label) else _MISSING)
    if not yes(first):
        first = _first(cls) if yes(cls) else _MISSING
    if not yes(first):
        first = "B" if strictly(get(tk, "kind", _MISSING), "enemy") else "P"
    return text(first).upper()


def _first(value):
    """``value[0]``: a text's first code unit, an array's first item."""
    if isinstance(value, str):
        return js_slice(value, 1) if value else _MISSING
    if isinstance(value, list):
        return value[0] if value else _MISSING
    return _MISSING


def token_title(tk) -> str:
    """A token's tip: an area's label (or "AoE zone"), else its label, class or kind."""
    if strictly(get(tk, "kind", _MISSING), "aoe"):
        label = get(tk, "label", _MISSING)
        return text(label if yes(label) else "AoE zone")
    return token_name(tk)


def players(p) -> list:
    """The plan's player tokens."""
    return [t for t in _list(get(p, "tokens", _MISSING)) if strictly(get(t, "kind", _MISSING), "player")]


def _list(value) -> list:
    return value if isinstance(value, list) else []


def giver(pl) -> str:
    """A player as a buff's source names it: ``label || cls``."""
    label = get(pl, "label", _MISSING)
    return text(label if yes(label) else get(pl, "cls", _MISSING))


def giver_value(pl):
    """``pl.label || pl.cls``, as compared with a buff's ``by``."""
    label = get(pl, "label", _MISSING)
    return label if yes(label) else get(pl, "cls", _MISSING)


def buff_colour(bf, plan_players: list) -> str:
    """``buffColor(bf)``: the colour of the player who gives it, else gold."""
    by = get(bf, "by", _MISSING)
    found = next((pl for pl in plan_players if strictly(giver_value(pl), by)), None)
    return col(get(found, "color", _MISSING), GOLD) if found is not None else GOLD


def buff_bars(p, length: float) -> list[dict]:
    """The party buffs' bars on the lane (``.bufbar``): where each starts and how long it is, in hundredths of the
    plan's length, its colour, its tip and its name."""
    out, who = [], players(p)
    for bf in _list(get(p, "buffs", _MISSING)):
        start, end = num(get(bf, "start", _MISSING)), num(get(bf, "end", _MISSING))
        name, by = get(bf, "name", _MISSING), get(bf, "by", _MISSING)
        out.append({"start": start, "end": end, "left": 100 * max(0.0, start) / length,
                    "width": 100 * max(0.0, end - start) / length, "colour": buff_colour(bf, who),
                    "tip": text(name) + (" · " + text(by) if yes(by) else ""), "name": text(name)})
    return out


def buffs_now(p, t: float) -> list[str]:
    """The buffs on at ``t`` (``Buffs now``): each one's name and who gives it."""
    out = []
    for bf in _list(get(p, "buffs", _MISSING)):
        start, end = get(bf, "start", _MISSING), get(bf, "end", _MISSING)
        if number_of(start) <= t <= number_of(end):
            by = get(bf, "by", _MISSING)
            out.append(text(get(bf, "name", _MISSING)) + (" · " + text(by) if yes(by) else ""))
    return out


def time_words(t: float, p) -> str:
    """The moment shown (``#rtime``): ``t.toFixed(1) / length s``."""
    length = get(p, "duration", _MISSING)
    return fixed(t, 1) + " / " + text(length if yes(length) else 1) + "s"


def keyframe_rows(tk) -> list[dict]:
    """The selected token's keyframes (``.kfrow``): the moment to go to, its words, where it is, and whether it can
    be deleted (a token keeps its last)."""
    frames = _list(get(tk, "keyframes", _MISSING))
    return [{"go": num(get(k, "t", _MISSING)), "time": fixed(num(get(k, "t", _MISSING)), 1) + "s",
             "where": f"x {fixed(number_of(get(k, 'x', _MISSING)) * 100, 0)} · y {fixed(number_of(get(k, 'y', _MISSING)) * 100, 0)}",
             "deletable": len(frames) > 1} for k in frames]


def keyframes_head(tk) -> str:
    """``Keyframes (position over time)``, with how many when more than one."""
    frames = _list(get(tk, "keyframes", _MISSING))
    return "Keyframes (position over time)" + (f" · {len(frames)}" if len(frames) > 1 else "")


def on_map_words(tk):
    """When a recorded token is on the map, as the recording had it; None for one on the map throughout."""
    since, until = get(tk, "from", _MISSING), get(tk, "until", _MISSING)
    if not finite(since) and not finite(until):
        return None
    return (f"On the map from {fixed(num(since), 1)}s"
            + (f" to {fixed(num(until), 1)}s, as the recording had it" if finite(until) else ", as the recording had it"))


def current_keyframe(tk, t: float) -> int:
    """The keyframe the moment shown is at or past (``at``): the last at or before ``t`` + 0.05; -1 for none."""
    at = -1
    for i, k in enumerate(_list(get(tk, "keyframes", _MISSING))):
        if number_of(get(k, "t", _MISSING)) <= t + 0.05:
            at = i
    return at


def kinds_shown(p) -> list[dict]:
    """``SHOWN ON THE MAP``: each kind the plan has, how many of it are shown and how many there are."""
    tokens = _list(get(p, "tokens", _MISSING))
    out = []
    for kind, name in KINDS:
        of = [t for t in tokens if strictly(get(t, "kind", _MISSING), kind)]
        on = len([t for t in of if not yes(get(t, "hidden", _MISSING))])
        if of:
            out.append({"kind": kind, "name": name, "on": on, "all": len(of)})
    return out


def pick_colour(p) -> str:
    """``pickColor()``: the first token colour no token has, else the next round."""
    tokens = _list(get(p, "tokens", _MISSING))
    used = [get(t, "color", _MISSING) for t in tokens]
    return next((c for c in TOKEN_COLORS if not any(strictly(u, c) for u in used)),
                TOKEN_COLORS[len(tokens) % len(TOKEN_COLORS)])


def marker_label(p) -> str:
    """The next marker's label: A, B, C, D, 1, 2, 3, 4, then round again."""
    used = len([t for t in _list(get(p, "tokens", _MISSING)) if strictly(get(t, "kind", _MISSING), "marker")])
    return RAID_MARKERS[used % len(RAID_MARKERS)]


def new_token(kind: str, p, cls: str = "", make_id=uid) -> dict:
    """A token added from the panel (``+ Player``, ``+ Enemy``, ``+ Marker``, ``+ AoE``), before its first place."""
    if kind == "player":
        return {"id": make_id(), "kind": "player", "label": cls, "cls": cls, "color": pick_colour(p), "keyframes": []}
    if kind == "enemy":
        return {"id": make_id(), "kind": "enemy", "label": "Boss", "color": "#d33939", "keyframes": []}
    if kind == "marker":
        return {"id": make_id(), "kind": "marker", "label": marker_label(p), "color": "#e9cf8e", "keyframes": []}
    return {"id": make_id(), "kind": "aoe", "label": "AoE", "color": "#e9a43a", "radius": 0.16, "keyframes": []}


def export_name(p) -> str:
    """The exported file's name: the plan's name with each run of other characters than letters, digits, _ and -
    as one _, then .a2plan."""
    name = get(get(p, "meta", _MISSING), "name", _MISSING)
    words = text(name) if yes(name) else "plan"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", words) + ".a2plan"


def colour_field(value) -> str:
    """What a colour field shows (``input type=color``): ``col``'s colour as the browser reads a CSS hex colour
    (``#rgb``, ``#rgba``, ``#rrggbb``, ``#rrggbbaa``), written ``#rrggbb`` in small letters without its alpha; black
    for one it does not read."""
    h = col(value)[1:]
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    return "#" + h[:6].lower() if len(h) in (6, 8) else "#000000"


def slider_step(value: float, length: float) -> float:
    """Where a range field (``min=0 max=length step=0.1``) puts a value: on its nearest step, within its ends."""
    top = math.floor(round(length * 10, 6)) / 10 if length > 0 else 0.0
    v = min(max(0.0, value), top)
    return min(top, js_round(v * 10) / 10)
