"""The movement replay of a log's review (combat-review.js ``replay``), in the native interface since 0.2.468: the
fight's recorded positions played back on the ground they covered, north up.

This module is the replay's model; ``combat_replay_view`` draws it. Since 0.2.468:

- **the view** (``frameMovement``): a 100 × 100 view of the fight's ground, with a boss fight's arena as a circle and as
  a square (``enclosingCircle``); anything beyond the view is drawn faded at its edge;
- **the tokens**: each player, pet and enemy that moved, where it was at a moment (``place``: a step between two
  positions at most 6 s apart, else the last known place), on its side (``sideOf``), of its kind (``kindOf``) and in
  its colour (``shade``). A token last seen over 8 s ago, or outside the view, is faded. One unseen for 20 s leaves
  (a player or a boss after a minute), and a player is greyed while dead;
- **the trails**: a boss's and a player's movement in the last 6 seconds.

Since 0.2.469 why everyone moved:

- **the boss casts**: each drawn for a few seconds from its time, a ring on the caster, a marker where it was aimed and a
  wedge for the way the caster faced, with the skill's measured area (``aoe-shapes.json``: a circle, a ring, a cone, a
  line, a dash or trail along the caster's path, or wedges with safe gaps between them);
- **the appearances, deaths and revives, and the add hits**: an enemy ringed where it first appeared, a ✕ where a
  player fell, a ring as they were revived, and where a boss's add or clone struck a player;
- **the list beside the arena** (``listEvents``): each of them in time order, the same at the same moment one row with
  a count, the rows in progress marked as the replay plays.

An older recording holds only ``positions``, already on the view's scale, and has neither the arena nor the trails.
"""
from __future__ import annotations

import math
import re
from bisect import bisect_left

from . import theme
from .character import js_number
from .combat import js_string
from .combat_records import class_colour
from .combat_review import _UNNAMED, _num, actor_label, fixed, is_character, npc_name
from .results import _dict, _list, _truthy

ROOM_KEY = "a2-replay-arena"            # the arena's shape, kept for every log: a circle unless a square was chosen
SPEED_KEY = "a2-replay-speed"           # the playback speed, kept: 1× plays the fight in real seconds
SPEEDS = (0.25, 0.5, 1, 2, 4, 8)
SHAPES = (("circle", "Circle"), ("square", "Square"))
GONE, GONE_LONG = 20, 60                # unseen this long, a token leaves the replay (a player or a boss: a minute)
TRAIL = 6                               # a trail's seconds
FADED = 8                               # last seen longer ago than this, a token is faded
SKILL_CLASS = {11: "gladiator", 12: "templar", 13: "assassin", 14: "ranger", 15: "sorcerer", 16: "spiritmaster",
               17: "cleric", 18: "chanter", 19: "brawler"}
ENEMY_RED = "#ef6262"                   # a boss, and its adds and clones
NEUTRAL_GREY = "#9a9a9a"                # another enemy
HEAD = "Recorded movement replay"
NO_MOVEMENT = "This recording holds no movement (recordings made before 0.2.350 have none)."
MAY_HOLD = " Another public recording of this fight may hold it."
ARENA_TIP = "Arena: the ground this fight covered, with room to spare"
SIZES = {"boss": 3.0, "player": 2.0, "add": 1.8}      # a token's radius in view units; any other 1.4
CAST_SHOW, SPAWN_SHOW, LIFE_SHOW, HIT_SHOW = 2.5, 3, 3, 2   # how long a cast, an appearance, a death or revive and a hit show
NEAR = 60                               # an aim this close to the target or the caster is at them (game units)
EVENTS_HEAD = "Casts and events"
EVENTS_HINT = " · select one to go to it"
NO_EVENTS = "The key hides every cast and event."
ATTACK = "1800000"                      # the plain Attack's skill, named only when it is another


def _js_round(x: float) -> int:
    """``Math.round``: a half rounds up."""
    return math.floor(x + 0.5)


def _finite(x) -> bool:
    """``Number.isFinite``: a number, and not infinite or NaN."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def skill_class(skill_id) -> str | None:
    """A skill's class by its id's first two digits (``skillClass``): 16 xx xx xx is a Spiritmaster's, a spirit's
    included."""
    n = js_number(skill_id)
    return SKILL_CLASS.get(math.floor(n / 1e6)) if 11e6 <= n < 2e7 else None


def room_shape(saved) -> str:
    """The arena's shape kept (``roomShape``): a square only when one was chosen."""
    return "square" if saved == "square" else "circle"


def replay_speed(saved) -> float:
    """The playback speed kept (``replaySpeed``): one of SPEEDS, else 1×."""
    value = js_number(saved)
    return value if value in SPEEDS else 1


def speed_words(speed) -> str:
    return f"{js_string(speed)}×"


def js_key_order(keys) -> list:
    """Keys in the order a JavaScript object lists them (``Object.keys``): whole numbers first, smallest first, then
    the rest as they were added."""
    def whole(key) -> bool:
        text = js_string(key)
        return bool(re.fullmatch(r"0|[1-9][0-9]*", text)) and int(text) < 2 ** 32 - 1
    keys = list(keys)
    return sorted((k for k in keys if whole(k)), key=lambda k: int(js_string(k))) + [k for k in keys if not whole(k)]


def enclosing_circle(points) -> dict:
    """The smallest circle holding every point, as ``{"x", "y", "r"}`` (``enclosingCircle``): Welzl's incremental
    algorithm over the points' convex hull, which keeps it to a few dozen corners however long the fight."""
    pts = sorted((float(x), float(y)) for x, y in points)
    if not pts:
        return {"x": 0.0, "y": 0.0, "r": 0.0}

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def chain(items):
        hull = []
        for p in items:
            while len(hull) >= 2 and cross(hull[-2], hull[-1], p) <= 0:
                hull.pop()
            hull.append(p)
        hull.pop()
        return hull

    hull = pts if len(pts) < 3 else chain(pts) + chain(pts[::-1])

    def holds(c, p):
        return math.hypot(p[0] - c["x"], p[1] - c["y"]) <= c["r"] + 1e-6 * (1 + c["r"])

    def two(a, b):
        return {"x": (a[0] + b[0]) / 2, "y": (a[1] + b[1]) / 2, "r": math.hypot(a[0] - b[0], a[1] - b[1]) / 2}

    def three(a, b, c):
        det = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(det) < 1e-9:                                         # in a line: the widest pair
            best = two(a, b)
            for other in (two(a, c), two(b, c)):
                if other["r"] > best["r"]:
                    best = other
            return best
        sa, sb, sc = a[0] * a[0] + a[1] * a[1], b[0] * b[0] + b[1] * b[1], c[0] * c[0] + c[1] * c[1]
        x = (sa * (b[1] - c[1]) + sb * (c[1] - a[1]) + sc * (a[1] - b[1])) / det
        y = (sa * (c[0] - b[0]) + sb * (a[0] - c[0]) + sc * (b[0] - a[0])) / det
        return {"x": x, "y": y, "r": math.hypot(a[0] - x, a[1] - y)}

    circle = {"x": hull[0][0], "y": hull[0][1], "r": 0.0}
    for i in range(1, len(hull)):
        if not holds(circle, hull[i]):
            circle = {"x": hull[i][0], "y": hull[i][1], "r": 0.0}
            for j in range(i):
                if not holds(circle, hull[j]):
                    circle = two(hull[i], hull[j])
                    for k in range(j):
                        if not holds(circle, hull[k]):
                            circle = three(hull[i], hull[j], hull[k])
    return circle


def _bounds(items) -> tuple[float, float, float, float]:
    x0, x1, y0, y1 = math.inf, -math.inf, math.inf, -math.inf
    for p in items:
        x0, x1, y0, y1 = min(x0, p["x"]), max(x1, p["x"]), min(y0, p["y"]), max(y1, p["y"])
    return x0, x1, y0, y1


def frame_movement(world: list, is_boss, boss_named: bool):
    """A fight's recorded movement on a 100 × 100 view, north up (``frameMovement``): ``at(position)`` is where it is
    drawn (clamped to the view) and whether it fell outside, ``rooms`` a boss fight's arena as a circle and as a square
    in view units (else None), and ``scale`` a length in view units. The view frames the bosses' ground with room
    around it, or without a boss the middle 90% of the positions; anything outside it (a party member back at a
    respawn point) is drawn faded at its edge."""
    def quantile(values, f):
        ordered = sorted(values)
        return ordered[_js_round(f * (len(ordered) - 1))]

    bosses = [p for p in world if is_boss(p.get("entity"))]
    basis, f = (bosses, 0) if bosses else (world, 0.05)
    bx, by = [p["x"] for p in basis], [p["y"] for p in basis]
    bx0, bx1, by0, by1 = quantile(bx, f), quantile(bx, 1 - f), quantile(by, f), quantile(by, 1 - f)
    pad = max(3000 if bosses else 500, (bx1 - bx0) / 2, (by1 - by0) / 2)
    ground = [p for p in world if bx0 - pad <= p["x"] <= bx1 + pad and by0 - pad <= p["y"] <= by1 + pad]
    x0, x1, y0, y1 = _bounds(ground)
    span, cx, cy = max(1, x1 - x0, y1 - y0) * 1.1, (x0 + x1) / 2, (y0 + y1) / 2
    rooms = None
    if bosses or boss_named:
        # A boss fight's room: the ground the fight covered, as the smallest circle holding it or as its bounding
        # square, a tenth larger since nobody stands against the walls. It leaves out the farthest hundredth of the
        # positions from their middle (someone walking in or out). The view fits both shapes.
        mx, my = quantile([p["x"] for p in ground], 0.5), quantile([p["y"] for p in ground], 0.5)

        def reach(p):
            return math.hypot(p["x"] - mx, p["y"] - my)
        far = sorted(reach(p) for p in ground)
        limit = far[len(far) - 1 - len(far) // 100]
        floor = [p for p in ground if reach(p) <= limit]
        f0, f1, g0, g1 = _bounds(floor)

        def room(r):
            return max(800, 1.1 * r)
        c = enclosing_circle([(p["x"], p["y"]) for p in floor])
        rooms = {"circle": {"x": c["x"], "y": c["y"], "r": room(c["r"])},
                 "square": {"x": (f0 + f1) / 2, "y": (g0 + g1) / 2, "r": room(max(f1 - f0, g1 - g0) / 2)}}
        shapes = list(rooms.values())
        ux0, ux1 = min(a["x"] - a["r"] for a in shapes), max(a["x"] + a["r"] for a in shapes)
        uy0, uy1 = min(a["y"] - a["r"] for a in shapes), max(a["y"] + a["r"] for a in shapes)
        span, cx, cy = 1.04 * max(ux1 - ux0, uy1 - uy0), (ux0 + ux1) / 2, (uy0 + uy1) / 2
        for a in shapes:
            a.update(x=50 + 100 * (a["x"] - cx) / span, y=50 - 100 * (a["y"] - cy) / span, r=100 * a["r"] / span)

    def at(p) -> tuple[float, float, bool]:
        x, y = 50 + 100 * (p["x"] - cx) / span, 50 - 100 * (p["y"] - cy) / span
        return min(99, max(1, x)), min(99, max(1, y)), x < 0 or x > 100 or y < 0 or y > 100

    return at, rooms, (lambda r: 100 * r / span)


def add_name(e, names: dict | None = None) -> str:
    """A boss's add or clone by name (``addNameOf``): the game data's, else the community's for its code, else
    "Clone"."""
    name = npc_name(e, names) if isinstance(e, dict) else ""
    if name and not _UNNAMED.match(name) and not re.fullmatch(r"#[0-9]+", name):
        return name
    code = _dict(e).get("mob_code")
    return ((names or {}).get(js_string(code)) if code is not None else None) or "Clone"


def _placed(rows) -> list[dict]:
    """A recording's positions that have a time and a place (the a2log format's: every one of them)."""
    out, numbers, finite = [], (int, float), math.isfinite
    for p in _list(rows):
        if isinstance(p, dict):
            t, x, y = p.get("t"), p.get("x"), p.get("y")
            if (type(t) in numbers and type(x) in numbers and type(y) in numbers    # never True or False
                    and finite(t) and finite(x) and finite(y)):
                out.append(p)
    return out


def metres(u) -> str:
    """A length in game units as metres (``metres``): a tenth's place under ten metres."""
    v = _num(u)
    return f"{fixed(None if v is None else v / 100, 1 if v is not None and v < 1000 else 0)} m"


def aoe_life(a: dict) -> float:
    """How long a measured area shows (``aoeLife``): the longer of 1.5 s and its first hit's delay and one."""
    return max(1.5, (_num(_dict(a).get("delay")) or 0) + 1)


def aoe_extras(a: dict) -> tuple[dict | None, dict | None]:
    """A skill's dash or trail and its wedges (``aoeExtras``): its own ``path`` and ``arcs``, or itself as one."""
    a = _dict(a)
    path = a.get("path") if _truthy(a.get("path")) else (a if a.get("shape") in ("dash", "trail") else None)
    arcs = a.get("arcs") if _truthy(a.get("arcs")) else (a if a.get("shape") == "arcs" else None)
    return _dict(path) if path is not None else None, _dict(arcs) if arcs is not None else None


def area_life(a: dict) -> float:
    """How long a cast's area stays (``areaLife``): a dash through its span and a moment, a trail through its last part,
    wedges as an area."""
    path, arcs = aoe_extras(a)
    life = 0.0
    if path is not None:
        life = max(life, (_num(path.get("span")) or 0) + ((_num(path.get("duration")) or 0) if path.get("shape") == "trail"
                                                           else 0.6))
    if arcs is not None:
        life = max(life, aoe_life(arcs))
    return life or aoe_life(a)


def _old_text(a: dict) -> str:
    shape = a.get("shape")
    if shape == "circle_aim":
        return f"circle of {metres(a.get('radius'))} around the aim"
    if shape == "circle_caster":
        return f"circle of {metres(a.get('radius'))} around the caster"
    if shape == "cone":
        angle = _num(a.get("angle"))
        return f"{'NaN' if angle is None else js_string(2 * angle)}° cone {metres(a.get('radius'))} long"
    if shape == "line":
        half = _num(a.get("half_width"))
        return f"line {metres(a.get('length'))} long, {metres(None if half is None else 2 * half)} wide"
    if shape == "ring":
        return f"ring from {metres(a.get('inner'))} to {metres(a.get('radius'))} around the caster"
    return js_string(shape) if shape is not None else "undefined"


def _path_text(p: dict) -> str:
    trail = p.get("shape") == "trail"
    text = (f"{'trail' if trail else 'dash'} {metres(2 * (_num(p.get('half_width')) or 0))} wide along its path for "
            f"{fixed(_num(p.get('span')) or 0, 1)} s")
    return text + (f", each part staying {fixed(_num(p.get('duration')) or 0, 1)} s" if trail else "")


def _arcs_text(a: dict) -> str:
    n = len(_list(a.get("segments")))
    return (f"{n} wedge{'' if n == 1 else 's'} of {metres(_num(a.get('radius')) or 0)} around the caster"
            + (", safe between them" if n > 1 else ""))


def aoe_text(a: dict) -> str:
    """A measured area in words (``aoeText``)."""
    path, arcs = aoe_extras(a)
    if path is not None or arcs is not None:
        return " and ".join(x for x in (path is not None and _path_text(path), arcs is not None and _arcs_text(arcs)) if x)
    return _old_text(_dict(a))


def _fit_text(f: dict) -> str:
    parts = [js_string(f["confidence"]) if _truthy(f.get("confidence")) else "",
             f"{js_string(f['casts'])} casts" if f.get("casts") is not None else "",
             f"{_js_round(f['accuracy'] * 100)}% of the positions explained" if _finite(f.get("accuracy")) else ""]
    return "(" + ", ".join(x for x in parts if x) + ")"


def measured_text(a: dict) -> str:
    """A measured area and how well it fits (``measuredText``)."""
    a = _dict(a)
    path, arcs = aoe_extras(a)
    if path is not None or arcs is not None:
        return " and ".join(x for x in (path is not None and f"{_path_text(path)} {_fit_text({**a, **path})}",
                                        arcs is not None and f"{_arcs_text(arcs)} {_fit_text({**a, **arcs})}") if x)
    return f"{_old_text(a)} {_fit_text(a)}"


def before(frames: list, t: float) -> int:
    """The last of the frames (in time order) at or before ``t``, -1 for none."""
    lo, hi = 0, len(frames)
    while lo < hi:
        m = (lo + hi) >> 1
        if frames[m]["t"] <= t:
            lo = m + 1
        else:
            hi = m
    return lo - 1


class Replay:
    """One fight's replay (``replay``'s model): its positions by token, the view, the fight's actors, and each
    token's side, kind and colour. ``colours`` are the user's class colours and ``names`` the community's NPC names."""

    def __init__(self, doc: dict, d: dict, colours=None, names: dict | None = None):
        segment = _dict(d.get("segment"))
        self.doc, self.segment, self.colours, self.names = doc, segment, colours, names
        self.duration = segment.get("duration") if _finite(segment.get("duration")) else 0
        self.recorder = segment.get("ping_recorder")
        self.world = _placed(segment.get("movement"))
        self.flat = _placed(segment.get("positions"))
        self.tokens: dict = {}
        self.at = lambda p: (100 * p["x"], 100 * p["y"], False)
        self.rooms, self.scale, self.note = None, None, ""
        r_in = _dict(d.get("r"))
        if self.world:
            self.at, self.rooms, self.scale = frame_movement(
                self.world, lambda key: _truthy(_dict(r_in.get(key)).get("is_boss")), _truthy(segment.get("boss")))
            for p in self.world:
                self.tokens.setdefault(p.get("entity"), []).append(p)
            own = self.tokens.get(self.recorder) or []
            stamps = sum(1 for p in own if p.get("src") in ("applied", "targeted"))
            borrowed = sum(1 for p in own if _truthy(p.get("via")))
            self.note = f"{len(self.world)} recorded positions of {len(self.tokens)} players and enemies."
            if own:
                self.note += (f" The recording player's own movement comes from {borrowed} positions in the other "
                              f"recordings of this fight; {stamps} more are where they applied an effect or a cast aimed "
                              "at them." if borrowed else
                              f" The game does not send the recording player's own movement: {stamps} of their {len(own)} "
                              "positions are where they applied an effect or a cast aimed at them, and the path is drawn "
                              "between them. A party member's upload of the same fight records their movement.")
        else:
            for p in self.flat:
                self.tokens.setdefault(p.get("entity"), []).append(p)
        for frames in self.tokens.values():
            frames.sort(key=lambda p: p["t"])
        self.order = js_key_order(self.tokens)                   # ``Object.entries(tokens)``: the order drawn
        # the fight's actors, and a player of the log who only moved in it; an add that only moved
        players = [_dict(p) for p in _list(doc.get("players"))]
        r = dict(r_in)
        for p in players:
            if p.get("id") in self.tokens and not _truthy(r.get(p.get("id"))):
                r[p.get("id")] = p
        for e in _list(segment.get("entities")):
            if _truthy(e) and isinstance(e, dict) and e.get("id") in self.tokens and not _truthy(r.get(e.get("id"))):
                r[e.get("id")] = e
        self.r = r
        self._kinds: dict = {}
        self._sides(players)
        # Deaths and revives: a player who died is greyed until revived.
        self.lives: list[dict] = []
        for ev in self.events:
            ev = _dict(ev)
            if (ev.get("kind") not in ("death", "revive") or not _finite(ev.get("t")) or ev.get("target") not in self.tokens
                    or not is_character(r.get(ev.get("target")), doc)):
                continue
            if not any(life["id"] == ev["target"] and life["kind"] == ev["kind"] and abs(life["t"] - ev["t"]) < 0.05
                       for life in self.lives):
                self.lives.append({"kind": ev["kind"], "t": ev["t"], "id": ev["target"]})
        self.lives.sort(key=lambda life: life["t"])
        # when each death or revive is followed by the player's next one: a death is theirs until then (``deadSince``)
        self._life_ends, last = [math.inf] * len(self.lives), {}
        for i, life in enumerate(self.lives):
            if life["id"] in last:
                self._life_ends[last[life["id"]]] = life["t"]
            last[life["id"]] = i
        self.shapes = None                         # the measured areas (``aoeShapes``), once the app has given them
        # The bosses' casts with a caster on the replay; the enemies that first appeared during the fight; where a
        # boss's add or clone (or another enemy NPC) struck a player.
        self.casts = sorted((_dict(c) for c in _list(segment.get("npc_casts"))
                             if _dict(c).get("source") in self.tokens and _finite(_dict(c).get("t"))),
                            key=lambda c: c["t"]) if self.world else []
        self.spawns = sorted(({"id": key, "t": self.tokens[key][0]["t"], "frame": self.tokens[key][0]} for key in self.order
                              if self.tokens[key][0]["t"] > 1 and self.kind_of(key) in ("enemy", "add")
                              and js_string(key) != js_string(self.recorder)),
                             key=lambda sp: sp["t"]) if self.world else []
        self.add_hits = sorted((ev for ev in (_dict(e) for e in self.events)
                                if ev.get("kind") == "damage" and _finite(ev.get("t")) and ev.get("target") in self.tokens
                                and is_character(r.get(ev.get("target")), doc) and _truthy(r.get(ev.get("source")))
                                and not _truthy(_dict(r.get(ev.get("source"))).get("is_boss"))
                                and not is_character(r.get(ev.get("source")), doc)
                                and self.kind_of(ev.get("source")) in ("enemy", "add")),
                               key=lambda ev: ev["t"]) if self.world else []
        # their times, to find the first still showing at a moment without walking the fight from its start
        self._cast_times = [c["t"] for c in self.casts]
        self._spawn_times = [sp["t"] for sp in self.spawns]
        self._hit_times = [h["t"] for h in self.add_hits]

    @property
    def shapes(self) -> dict | None:
        return self._shapes

    @shapes.setter
    def shapes(self, shapes: dict | None) -> None:
        self._shapes = shapes
        self._cast_areas = None                    # each cast's area and how long it shows, found again for these

    def _areas_shown(self) -> tuple[list, list, float]:
        """Each cast's measured area, how long it shows (the longer of 2.5 s and its area's life) and the longest."""
        if self._cast_areas is None:
            areas = [self.aoe_of(c) for c in self.casts]
            shows = [max(CAST_SHOW, area_life(a) if a else 0) for a in areas]
            self._cast_areas = areas, shows, max(shows, default=CAST_SHOW)
        return self._cast_areas

    @property
    def ticked(self) -> bool:
        """Whether the fight has casts or events to list and tick on the slider."""
        return bool(self.casts or self.spawns or self.lives or self.add_hits)

    def ticks(self) -> list[float]:
        """The slider's ticks (``cr-ticks``): each cast's and event's time, to a tenth."""
        times = [c["t"] for c in self.casts] + [sp["t"] for sp in self.spawns] + [life["t"] for life in self.lives] + \
                [h["t"] for h in self.add_hits]
        return [float(t) for t in dict.fromkeys(fixed(t, 1) for t in times)]

    def aoe_of(self, c: dict) -> dict | None:
        """A cast's measured area (``aoeOf``): by its skill, else by its caster's name and skill; none without the
        catalog or a view to scale it to."""
        if not self.shapes or self.scale is None:
            return None
        caster = _dict(self.r.get(c.get("source"))).get("name")
        skill = js_string(c.get("skill_id")) if "skill_id" in c else "undefined"
        found = self.shapes.get(skill) or self.shapes.get(f"{js_string(caster) if _truthy(caster) else ''}|{skill}")
        return found if isinstance(found, dict) and found else None

    def name_of(self, key) -> str:
        """A token's name (``nameOf``): an add's or clone's own, else the actor's name or label."""
        if self.kind_of(key) == "add":
            return add_name(self.r.get(key), self.names)
        e = self.r.get(key)
        return js_string(_dict(e)["name"]) if _truthy(_dict(e).get("name")) else actor_label(e)

    @staticmethod
    def hit_skill(h: dict) -> str:
        """A hit's skill unless it is the plain Attack (``hitSkill``)."""
        if js_string(h.get("skill_id")) == ATTACK or h.get("skill") == "Attack" or not (_truthy(h.get("skill"))
                                                                                       or _truthy(h.get("skill_id"))):
            return ""
        return js_string(h["skill"] if _truthy(h.get("skill")) else h.get("skill_id"))

    def struck_text(self, key) -> str:
        """The player struck, with their class (``struckText``)."""
        cls = _dict(self.r.get(key)).get("class")
        return self.name_of(key) + (f" · {js_string(cls)[:1].upper()}{js_string(cls)[1:]}" if _truthy(cls) else "")

    @staticmethod
    def world_at(frames, t: float):
        """The last frame at or before ``t`` (``worldAt``), None before the first."""
        if not frames:
            return None
        i = before(frames, t)
        return frames[i] if i >= 0 else None

    def where_of(self, c: dict) -> str:
        """Where a cast was aimed (``whereOf``): at its target, around the caster itself, or on the ground."""
        target = self.name_of(c["target"]) if _truthy(c.get("target")) and _truthy(self.r.get(c.get("target"))) else ""
        pos = c.get("pos")
        if not _truthy(pos):
            return f"at {target}" if target else ""
        cw = self.world_at(self.tokens.get(c.get("source")), c["t"])
        tw = self.world_at(self.tokens.get(c.get("target")), c["t"]) if _truthy(c.get("target")) else None
        dc = math.hypot(pos[0] - cw["x"], pos[1] - cw["y"]) if cw else math.inf
        dt = math.hypot(pos[0] - tw["x"], pos[1] - tw["y"]) if tw else math.inf
        if dt <= NEAR and target:
            return f"at {target}"
        return "around itself" if dc <= NEAR else "on the ground" + (f" near {target}" if target else "")

    def _aim(self, c: dict, bw: dict) -> dict | None:
        tw = self.world_at(self.tokens.get(c.get("target")), c["t"]) if _truthy(c.get("target")) else None
        return {"x": c["pos"][0], "y": c["pos"][1]} if _truthy(c.get("pos")) else tw

    def facing_of(self, c: dict, bw: dict):
        """The way a cast faced (``facingOf``): its own, else the caster's heading, else toward a distant aim."""
        if c.get("facing") is not None:
            return c["facing"]
        if bw.get("heading") is not None:
            return bw["heading"]
        aim = self._aim(c, bw)
        if aim and math.hypot(aim["x"] - bw["x"], aim["y"] - bw["y"]) > 100:
            return math.degrees(math.atan2(aim["y"] - bw["y"], aim["x"] - bw["x"]))
        return None

    def track(self, frames: list, t0: float, t1: float) -> list[tuple[float, float]]:
        """The caster's track from ``t0`` to ``t1`` in view units (``track``): its place then, each position between,
        its place at ``t1``."""
        pts = []
        a = self.place(frames, t0)
        if a:
            pts.append((a[0], a[1]))
        i = before(frames, t0) + 1
        while i < len(frames) and frames[i]["t"] < t1:
            if frames[i]["t"] > t0:
                pts.append(self.at(frames[i])[:2])
            i += 1
        b = self.place(frames, t1) if t1 > t0 else None
        if b:
            pts.append((b[0], b[1]))
        return pts

    def event_rows(self) -> list[dict]:
        """The list beside the arena (``listEvents``): every cast, appearance, death, revive and add hit with its
        time, the same at the same moment (within half a second) one row with a count."""
        rows = []
        areas, shows, _longest = self._areas_shown()
        for c, area, show in zip(self.casts, areas, shows):
            rows.append({"kind": "cast", "t": c["t"], "last": c["t"], "show": show,
                         "who": self.name_of(c.get("source")),
                         "what": js_string(c["skill"] if _truthy(c.get("skill")) else c.get("skill_id")),
                         "where": self.where_of(c), "area": aoe_text(area) if area else ""})
        for sp in self.spawns:
            rows.append({"kind": "spawn", "t": sp["t"], "last": sp["t"], "show": SPAWN_SHOW, "who": self.name_of(sp["id"]),
                         "what": "", "where": "", "area": ""})
        for life in self.lives:
            cls = _dict(self.r.get(life["id"])).get("class")
            who = self.name_of(life["id"]) + (f" · {js_string(cls)[:1].upper()}{js_string(cls)[1:]}" if _truthy(cls) else "")
            rows.append({"kind": life["kind"], "t": life["t"], "last": life["t"], "show": LIFE_SHOW, "who": who, "what": "",
                         "where": "", "area": ""})
        for h in self.add_hits:
            rows.append({"kind": "hit", "t": h["t"], "last": h["t"], "show": HIT_SHOW, "who": self.name_of(h.get("source")),
                         "what": self.hit_skill(h), "where": self.struck_text(h.get("target")), "area": ""})
        rows.sort(key=lambda e: e["t"])
        out: list[dict] = []
        for e in rows:
            key = "|".join((e["kind"], e["who"], e["what"], e["where"], e["area"]))
            same = None
            i = len(out) - 1
            while i >= 0 and e["t"] - out[i]["t"] <= 0.5:
                if out[i]["key"] == key:
                    same = out[i]
                    break
                i -= 1
            if same is not None:
                same["n"] += 1
                same["last"] = e["t"]
            else:
                out.append({**e, "key": key, "n": 1})
        return out

    @staticmethod
    def event_state(e: dict, t: float) -> str:
        """A row's state at ``t`` (``markEvents``): "next" before it, "now" while it shows, else "past"."""
        return "next" if e["t"] > t else "now" if t - e["last"] <= e["show"] else "past"

    def marks(self, t: float) -> list[dict]:
        """What the arena draws under the tokens at ``t`` (``drawMarks``), in drawing order: the casts' areas, rings,
        facing wedges and aims; the appearances; the deaths and revives; the add hits. Each has its geometry in view
        units, how opaque it is and its tip."""
        out: list[dict] = []
        areas, shows, longest = self._areas_shown()
        for i in range(bisect_left(self._cast_times, t - longest - 1e-6), len(self.casts)):   # those before have gone
            c, area = self.casts[i], areas[i]
            if c["t"] > t:
                break
            if t - c["t"] > shows[i]:
                continue
            gone, age = t - c["t"] > CAST_SHOW, min(1.0, (t - c["t"]) / CAST_SHOW)
            here = self.place(self.tokens[c["source"]], t)
            if not here:
                continue
            x, y = here[0], here[1]
            where = self.where_of(c)
            title = (f"{self.name_of(c['source'])}: {js_string(c['skill'] if _truthy(c.get('skill')) else c.get('skill_id'))}"
                     f"{' ' + where if where else ''} · {fixed(c['t'], 1)}s")
            if area:
                out.extend(self._areas(area, c, t, f"{title} · measured {measured_text(area)}"))
            if not gone:
                out.append({"kind": "castring", "x": x, "y": y, "r": 3.2 + 3 * age, "alpha": 1 - age, "tip": title})
            if not gone and c.get("facing") is not None:
                length, a0, a1 = 9, math.radians(c["facing"] - 30), math.radians(c["facing"] + 30)
                out.append({"kind": "face", "alpha": 0.25 * (1 - age), "tip": "",
                            "points": [(x, y), (x + length * math.cos(a0), y - length * math.sin(a0)),
                                       (x + length * math.cos(a1), y - length * math.sin(a1))]})
            if not gone and _truthy(c.get("pos")):
                ax, ay, _out = self.at({"x": c["pos"][0], "y": c["pos"][1]})
                if math.hypot(ax - x, ay - y) > 1.5:
                    out.append({"kind": "aimline", "x1": x, "y1": y, "x2": ax, "y2": ay, "alpha": 1 - age, "tip": ""})
                out.append({"kind": "aim", "x": ax, "y": ay, "r": 2 + 2.5 * age, "alpha": 1 - age, "tip": title})
        for i in range(bisect_left(self._spawn_times, t - SPAWN_SHOW - 1e-6), len(self.spawns)):
            sp = self.spawns[i]
            if sp["t"] > t:
                break
            if t - sp["t"] > SPAWN_SHOW:
                continue
            age = (t - sp["t"]) / SPAWN_SHOW
            x, y, _out = self.at(sp["frame"])
            out.append({"kind": "spawn", "x": x, "y": y, "r": 2.5 + 6 * age, "alpha": 1 - age,
                        "tip": f"{self.name_of(sp['id'])} appeared here at {fixed(sp['t'], 1)}s"})
        for life, until in zip(self.lives, self._life_ends):
            if life["t"] > t:
                break
            if life["kind"] == "death":
                if until <= t:                                       # revived, or dead again, since
                    continue
                spot = self.place(self.tokens[life["id"]], life["t"]) or self.place(self.tokens[life["id"]], t)
                if not spot:
                    continue
                out.append({"kind": "death", "x": spot[0], "y": spot[1] + 2.1, "alpha": 1.0,
                            "tip": f"{self.name_of(life['id'])} died here at {fixed(life['t'], 1)}s"})
            elif t - life["t"] <= LIFE_SHOW:
                here = self.place(self.tokens[life["id"]], t)
                if not here:
                    continue
                age = (t - life["t"]) / LIFE_SHOW
                out.append({"kind": "revive", "x": here[0], "y": here[1], "r": 2.4 + 4 * age, "alpha": 1 - age,
                            "tip": f"{self.name_of(life['id'])} revived at {fixed(life['t'], 1)}s"})
        for i in range(bisect_left(self._hit_times, t - HIT_SHOW - 1e-6), len(self.add_hits)):
            h = self.add_hits[i]
            if h["t"] > t:
                break
            if t - h["t"] > HIT_SHOW:
                continue
            here = self.place(self.tokens[h["target"]], h["t"])
            if not here:
                continue
            age = (t - h["t"]) / HIT_SHOW
            skill = self.hit_skill(h)
            out.append({"kind": "hit", "x": here[0], "y": here[1], "r": 2 + 4 * age, "alpha": 1 - age,
                        "tip": f"{self.name_of(h.get('source'))} hit {self.struck_text(h.get('target'))}"
                               f"{' · ' + skill if skill else ''} · {fixed(h['t'], 1)}s"})
        return out

    def _areas(self, a: dict, c: dict, t: float, title: str) -> list[dict]:
        """A cast's measured area where it happened (``aoeSVG``): around its aim or its caster, along the caster's
        facing, or its dash, trail or wedges; none once its time is past or without the facing it needs."""
        path, arcs = aoe_extras(a)
        if path is not None or arcs is not None:
            return (self._arcs(arcs, c, t, title) if arcs is not None else []) + \
                   (self._path(path, c, t, title) if path is not None else [])
        frames = self.tokens[c["source"]]
        t0 = c["t"] + (_num(a.get("delay")) or 0) if a.get("anchor") == "hit" else c["t"]
        bw = self.world_at(frames, t0) or self.world_at(frames, t)
        if not bw:
            return []
        aim = self._aim(c, bw) or bw
        age = (t - c["t"]) / aoe_life(a)
        if age > 1:
            return []
        bx, by, _o = self.at(bw)
        ax, ay, _o = self.at(aim)
        opacity = 0.9 * (1 - age)
        facing = c["facing"] if c.get("facing") is not None else bw.get("heading")
        if facing is None and math.hypot(aim["x"] - bw["x"], aim["y"] - bw["y"]) > 100:
            facing = math.degrees(math.atan2(aim["y"] - bw["y"], aim["x"] - bw["x"]))
        shape, radius = a.get("shape"), self.scale(_num(a.get("radius")) or 0)
        angle = _num(a.get("angle"))
        if shape == "circle_aim":
            return [{"kind": "area", "shape": "circle", "x": ax, "y": ay, "r": radius, "opacity": opacity, "tip": title}]
        if shape == "circle_caster" or (shape == "cone" and angle is not None and angle >= 180):
            return [{"kind": "area", "shape": "circle", "x": bx, "y": by, "r": radius, "opacity": opacity, "tip": title}]
        if shape == "ring":
            inner = self.scale(_num(a.get("inner")) or 0)
            return [{"kind": "area", "shape": "ring", "x": bx, "y": by, "r": (radius + inner) / 2,
                     "width": max(0.4, radius - inner), "opacity": opacity, "tip": title}]
        if facing is None:
            return []
        if shape == "cone" and angle is not None:
            return [{"kind": "area", "shape": "cone", "x": bx, "y": by, "r": radius, "from": facing - angle,
                     "sweep": 2 * angle, "opacity": opacity, "tip": title}]
        if shape == "line":
            length, half = self.scale(_num(a.get("length")) or 0), self.scale(_num(a.get("half_width")) or 0)
            f = math.radians(facing)
            ux, uy = math.cos(f), -math.sin(f)
            px, py = -uy, ux
            return [{"kind": "area", "shape": "polygon", "opacity": opacity, "tip": title,
                     "points": [(bx + px * half, by + py * half), (bx + ux * length + px * half, by + uy * length + py * half),
                                (bx + ux * length - px * half, by + uy * length - py * half),
                                (bx - px * half, by - py * half)]}]
        return []

    def _arcs(self, a: dict, c: dict, t: float, title: str) -> list[dict]:
        """Wedges with safe gaps (``arcsSVG``): each ``[a0, a1]`` degrees off the caster's facing at the cast, within its
        radius (beyond its inner one) of where it stood."""
        frames = self.tokens[c["source"]]
        t0 = c["t"] + (_num(a.get("delay")) or 0) if a.get("anchor") == "hit" else c["t"]
        bw = self.world_at(frames, t0) or self.world_at(frames, t)
        if not bw:
            return []
        age, facing = (t - c["t"]) / aoe_life(a), self.facing_of(c, bw)
        if age > 1 or facing is None:
            return []
        bx, by, _o = self.at(bw)
        outer, inner = self.scale(_num(a.get("radius")) or 0), self.scale(_num(a.get("inner")) or 0)
        wedges = []
        for segment in _list(a.get("segments")):
            a0, a1 = (_num(v) for v in (list(segment) + [None, None])[:2])
            if a0 is None or a1 is None:
                continue
            sweep = min(359.9, a1 - a0)
            if not (sweep > 0) or not (outer > 0):
                continue
            wedges.append({"from": facing + a0, "sweep": sweep})
        if not wedges:
            return []
        return [{"kind": "area", "shape": "wedges", "x": bx, "y": by, "r": outer, "inner": inner, "wedges": wedges,
                 "opacity": 0.9 * (1 - age), "tip": title}]

    def _path(self, p: dict, c: dict, t: float, title: str) -> list[dict]:
        """A dash or a trail (``pathSVG``): the caster's track from the cast for its span, or the part of it passed in
        the last ``duration`` seconds, ``half_width`` either side; a dash fades once the caster is through."""
        span, trail, lasts = _num(p.get("span")) or 0, p.get("shape") == "trail", _num(p.get("duration")) or 0
        if t > c["t"] + span + (lasts if trail else 0.6):
            return []
        start = max(c["t"], t - lasts) if trail else c["t"]
        end = min(t, c["t"] + span) if trail else c["t"] + span
        if end < start:
            return []
        pts = self.track(self.tokens[c["source"]], start, end)
        if not pts:
            return []
        if len(pts) < 2:
            pts = [pts[0], (pts[0][0] + 0.01, pts[0][1])]
        fade = 0.9 if trail or t <= c["t"] + span else 0.9 * (1 - (t - c["t"] - span) / 0.6)
        return [{"kind": "area", "shape": "path", "points": pts, "width": max(0.4, 2 * self.scale(_num(p.get("half_width")) or 0)),
                 "opacity": fade, "tip": title}]

    def _sides(self, players: list[dict]) -> None:
        """Which side each token fights on. The recording side is the log's players and the summons they own; the
        enemy side the bosses, their adds and clones, the other side's players and the summons those own. A summon
        follows its owner; one the recording did not link to an owner is placed by what it did: the class of its
        skills, striking the enemy side or healing the party. Nothing to tell leaves it a summon of neither side."""
        r = self.r
        self.friendly = {p.get("id") for p in players}
        self.events = _list(self.segment.get("events"))
        evs = [_dict(ev) for ev in self.events]
        others = [e for e in r.values() if _truthy(e) and isinstance(e, dict) and e.get("id") not in self.friendly
                  and (_truthy(e.get("is_player")) or e.get("kind") == "player")]
        def lowered(e) -> str:                                   # ``String(e.class || "").toLowerCase()``
            return js_string(e.get("class")).lower() if _truthy(e.get("class")) else ""
        ally_classes = {lowered(p) for p in players} - {""}
        foe_classes = {lowered(e) for e in others} - {""}
        other_ids = {e.get("id") for e in others}
        for ev in evs:
            if ev.get("source") in other_ids:
                c = skill_class(ev.get("skill_id"))
                if c:
                    foe_classes.add(c)
        by_source: dict = {}                                     # each actor's events, in their order
        for ev in evs:
            by_source.setdefault(ev.get("source"), []).append(ev)
        self.unlinked: dict = {}
        for e in list(r.values()):
            if not _truthy(e) or not isinstance(e, dict) or e.get("kind") != "pet" or _truthy(e.get("owner")):
                continue
            ally = foe = 0
            struck, seen = set(), {}
            for ev in by_source.get(e.get("id"), []):
                c, t = skill_class(ev.get("skill_id")), _dict(r.get(ev.get("target")))
                if c:
                    seen[c] = seen.get(c, 0) + 1
                if c and c in ally_classes and c not in foe_classes:
                    ally += 1
                elif c and c in foe_classes and c not in ally_classes:
                    foe += 1
                if ev.get("kind") == "damage":
                    if t and t.get("id") not in self.friendly and (_truthy(t.get("is_boss")) or t.get("kind") == "enemy"
                                                                   or _truthy(t.get("is_player"))):
                        ally += 1
                    elif ev.get("target") in self.friendly:
                        struck.add(ev.get("target"))
                if ev.get("kind") == "heal" and ev.get("target") in self.friendly:
                    ally += 1
            if len(struck) > 1:                                  # a summon striking several party members is the other side's
                foe += len(struck)
            cls = max(seen.items(), key=lambda item: item[1])[0] if seen else None   # the first of the most seen
            if cls and not _truthy(e.get("class")):
                r[e.get("id")] = {**e, "class": cls}
            self.unlinked[e.get("id")] = ("ally" if not others and foe == 0 else "ally" if ally > foe
                                          else "enemy" if foe > ally else "neutral")
        # A boss fight's NPC of the boss's side, no one's summon, that struck the party (or cast) is its add or clone.
        self.boss_fight = any(_truthy(_dict(e).get("is_boss")) for e in r.values())
        self.struck_party = set()
        if self.boss_fight:
            self.struck_party = {ev.get("source") for ev in evs
                                 if ev.get("kind") == "damage" and ev.get("target") in self.friendly}
            for c in _list(self.segment.get("npc_casts")):
                caster = _dict(r.get(_dict(c).get("source")))
                if not _truthy(caster.get("is_boss")) and not _truthy(caster.get("owner")) and caster.get("kind") != "pet":
                    self.struck_party.add(_dict(c).get("source"))

    def side_of(self, key, depth: int = 0) -> str:
        """``sideOf``: "ally", "enemy" or "neutral"."""
        e = self.r.get(key)
        if key in self.friendly:
            return "ally"
        if not _truthy(e) or not isinstance(e, dict):
            return "neutral"
        if _truthy(e.get("is_boss")):
            return "enemy"
        if _truthy(e.get("owner")) and depth < 8:
            return self.side_of(e["owner"], depth + 1) if _truthy(self.r.get(e["owner"])) else "neutral"
        if _truthy(e.get("is_player")) or e.get("kind") == "player":
            return "enemy"
        return (self.unlinked.get(key) or "neutral") if e.get("kind") == "pet" else "enemy"

    def kind_of(self, key) -> str:
        """``kindOf``: "boss", "player", "pet", "add" (a boss's add or clone) or "enemy"."""
        if key not in self._kinds:
            self._kinds[key] = self._kind(key)
        return self._kinds[key]

    def _kind(self, key) -> str:
        e = _dict(self.r.get(key))
        if _truthy(e.get("is_boss")):
            return "boss"
        if is_character(self.r.get(key), self.doc):
            return "player"
        if (e.get("kind") == "pet" or _truthy(e.get("owner"))) and self.side_of(key) != "enemy":
            return "pet"
        if not _truthy(e.get("owner")) and e.get("kind") != "pet" and key in self.struck_party:
            return "add"
        return "enemy"

    def shade(self, key) -> str:
        """A token's colour (``shade``): a boss's and its adds' red, a player's and a pet's class colour, else grey."""
        e, kind = self.r.get(key), self.kind_of(key)
        if kind in ("boss", "add"):
            return ENEMY_RED
        if _truthy(e) and kind in ("player", "pet"):
            return class_colour(_dict(e).get("class"), self.colours)
        return NEUTRAL_GREY

    def place(self, frames: list, t: float):
        """Where a token is at ``t`` (``place``): ``(x, y, stale, last, index, outside)``, a step between the last
        frame at or before ``t`` and the next when they are at most 6 s apart (stale 0), else the last frame's place and
        how long ago it was; None before its first."""
        i = before(frames, t)
        if i < 0:
            return None
        a = frames[i]
        b = frames[i + 1] if i + 1 < len(frames) else None
        f = (t - a["t"]) / max(0.001, b["t"] - a["t"]) if b is not None and b["t"] - a["t"] <= 6 else 0
        ax, ay, ao = self.at(a)
        if not f:
            return ax, ay, t - a["t"], a, i, ao
        bx, by, bo = self.at(b)
        return ax + (bx - ax) * f, ay + (by - ay) * f, 0, a, i, ao or bo

    def dead_since(self, key, t: float) -> dict | None:
        """The death a player is dead from at ``t`` (``deadSince``), None while alive."""
        dead = None
        for life in self.lives:
            if life["t"] > t:
                break
            if life["id"] == key:
                dead = life if life["kind"] == "death" else None
        return dead

    def source_name(self, index) -> str:
        """Which other recording a borrowed position came from (``sourceName``)."""
        return "another recording"

    def frame(self, t: float) -> list[dict]:
        """The tokens drawn at ``t`` (``draw``), in drawing order: each with its place, radius, colour, how opaque, the
        recording player's ring, its trail and its tip."""
        out = []
        for key in self.order:
            frames = self.tokens[key]
            here = self.place(frames, t)
            if here is None:
                continue
            x, y, stale, last, i, outside = here
            e, kind = self.r.get(key), self.kind_of(key)
            if stale > (GONE_LONG if kind in ("player", "boss") else GONE):
                continue
            dead = self.dead_since(key, t) if kind == "player" else None
            first = i
            while first > 0 and frames[first - 1]["t"] >= t - TRAIL:
                first -= 1
            trail = []
            if self.world and (_truthy(_dict(e).get("is_boss")) or is_character(e, self.doc)):
                trail = [self.at(p)[:2] for p in frames[first:i + 1]] + [(x, y)]
            tip = add_name(e, self.names) if kind == "add" else actor_label(e)
            if dead is not None:
                tip += f" · dead since {theme.fixed(dead['t'], 1)}s"
            if _truthy(last.get("src")):
                tip += f" · {js_string(last['src'])} at {theme.fixed(last['t'], 1)}s"
            if _truthy(last.get("via")):
                tip += f" · from {self.source_name(last['via'])}"
            if outside:
                tip += " · outside the fight area"
            out.append({"id": key, "x": x, "y": y, "radius": SIZES.get(kind, 1.4), "colour": self.shade(key),
                        "opacity": 0.2 if dead is not None else 0.35 if stale > FADED or outside else 1.0,
                        "ring": key == self.recorder, "trail": trail, "tip": tip, "kind": kind})
        return out
