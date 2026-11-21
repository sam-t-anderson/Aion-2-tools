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

An older recording holds only ``positions``, already on the view's scale, and has neither the arena nor the trails.
"""
from __future__ import annotations

import math
import re

from . import theme
from .character import js_number
from .combat import js_string
from .combat_records import class_colour
from .combat_review import _UNNAMED, actor_label, is_character, npc_name
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
