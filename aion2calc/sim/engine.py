"""Deterministic expected-value combat simulator.

The simulator advances one action at a time.  Between actions it resolves the
scheduled events (delayed hits, damage-over-time ticks, buff expiry) in time
order.  Every hit is evaluated with the *expected* damage formula of
``aion2calc.model.damage`` so a single run gives the mean DPS; chance-based
procs use an accumulator so their long-run rate is correct.

Kits (``aion2calc.kit``) describe skills as :class:`Action` objects whose
``on_cast`` callbacks call the small API below (``hit``, ``dot``, ``buff``,
``debuff``, ``reduce_cd`` ...).  Anything class specific lives in the kit.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Callable

from ..model.damage import HitContext, expected_hit
from ..model.stats import Derived

EPS = 1e-9

#: Safety bounds so one pathological build can never hang the simulator (and with it the
#: optimizer UI). A hit's hook may schedule more work (a proc) at the same instant; with extreme
#: imported gear a proc can re-trigger on its own hit and schedule same-instant events without end,
#: which would spin ``_advance_to`` forever. These caps are far above any legitimate fight (a 3-minute
#: parse lands a few thousand events) so they never fire in a healthy sim; when one does, the sim
#: stops draining and terminates with a bounded, slightly-approximate result instead of hanging.
_MAX_EVENTS_PER_ADVANCE = 300_000
_MAX_RUN_STEPS = 5_000_000
#: A hit's hook may land another hit at the same instant (``delay=0`` lands inline), so a
#: self-triggering proc recurses hook -> hit -> land -> hook. Real procs nest a step or two; this
#: caps the synchronous depth so a degenerate chain stops (bounded, flagged) instead of raising
#: RecursionError. Each level is a few stack frames, so keep this well under Python's ~1000-frame
#: limit; real procs nest only a step or two, so this is still far above any legitimate kit.
_MAX_LAND_DEPTH = 50
#: Last-resort per-run wall-clock bound. A search sim runs in well under a millisecond; nothing
#: legitimate approaches this, so it only trips on a pathological build and turns a would-be hang
#: into a bounded, flagged result rather than freezing the optimizer UI.
_SIM_WALL_LIMIT_S = 20.0


#: Where each class's direct hits land on a boss: (front, back) shares, the rest from the side.
#: The mean over characters with 500+ direct boss hits of their own shares, from the hit records'
#: position byte in the archived sharing-server logs and the diagnostic captures (one row per
#: character; docs/open-investigations.md, 17 October). Characters: Assassin 6, Chanter 7,
#: Cleric 13, Gladiator 4, Ranger 8, Sorcerer 5, Spiritmaster 8, Templar 3.
BOSS_POSITIONS = {
    "assassin": (0.12, 0.70), "chanter": (0.22, 0.55), "cleric": (0.27, 0.24),
    "gladiator": (0.31, 0.51), "ranger": (0.34, 0.35), "sorcerer": (0.43, 0.30),
    "spiritmaster": (0.29, 0.34), "templar": (0.48, 0.31),
}


@dataclass
class Target:
    """The thing being hit.  Defaults model a stationary training dummy."""
    tolerance: float = 0.10        # Damage Tolerance subtracted from the boost bucket
    crit_resist: float = 0.0
    crit_dmg_tol: float = 0.0
    double_resist: float = 0.0
    weapon_tol: float = 0.0
    defense: float = 0.0
    parry: float = 0.0             # chance a non-back, non-guaranteed hit is parried (-50%)
    frontal: bool = True           # without positions: every direct hit from the front (False: behind)
    positions: tuple | None = None  # (front, back) shares of direct hits; the rest land from the side
    class_positions: bool = False  # each class's recorded mix on bosses (BOSS_POSITIONS) instead
    stagger_windows: tuple = ()    # ((start, end), ...) seconds
    is_boss: bool = True
    party_damage: bool = False     # the party takes damage a healer answers (a dungeon boss; a dummy deals none)
    hp_model: str = "dummy"        # "dummy" (always 100%) or "linear" (100% -> 0% over the fight)

    is_player: bool = False
    # World PvP: how many enemies an area skill reaches, and the windows when no enemy is within
    # ``reach_m`` (only skills that reach at least that far can be used then)
    aoe_targets: int = 1
    out_of_reach: tuple = ()
    reach_m: float = 10.0

    def __post_init__(self):
        if self.positions is not None:
            front, back = (float(x) for x in self.positions)
            if not (0.0 <= front <= 1.0 and 0.0 <= back <= 1.0 and front + back <= 1.0 + EPS):
                raise ValueError("Target positions must be front and back shares that sum to at most 1")
            self.positions = (front, back)

    def hit_positions(self, cls: str | None = None) -> tuple[float, float]:
        """(front, back): the shares of direct hits landing from the front and from behind."""
        if self.class_positions and cls in BOSS_POSITIONS:
            return BOSS_POSITIONS[cls]
        if self.positions is not None:
            return self.positions
        return (1.0, 0.0) if self.frontal else (0.0, 1.0)

    def hp_pct(self, t: float, duration: float) -> float:
        if self.hp_model == "linear":
            return max(0.0, 1.0 - t / max(duration, 1e-9))
        return 1.0


#: per-skill damage factors learned from your own fights (``aion2calc.learn``); empty = none
SKILL_MULT: dict[str, float] = {}


@dataclass
class SimConfig:
    duration: float = 180.0
    latency: float = 0.03          # seconds added to every action (input/ping)
    tick: float = 0.2625           # server tick
    quantize: bool = False         # round action times up to whole ticks
    chain_window: float = 3.0      # seconds before a chain skill resets
    action_blocks: tuple = ()     # explicit no-new-action intervals on the rotation clock
    tactical_uses: tuple = ()     # (skill ID, assumed use start, effective cooldown)
    record_damage: bool = False   # final reports only; no hit trace allocation during scoring


def action_blocks(values, duration):
    """Validate, clip and union explicit action-unavailability intervals."""
    if not isinstance(values, (tuple, list)) or len(values) > 32:
        raise ValueError("Use a bounded list of action-time intervals")
    merged = []
    intervals = []
    for pair in values:
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pair)
                or not 0 <= pair[0] <= pair[1] <= 3720):
            raise ValueError("Invalid action-time interval")
        start, end = min(duration, pair[0]), min(duration, pair[1])
        if end > start + EPS:
            intervals.append((float(start), float(end)))
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + EPS:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return tuple(merged)


def tactical_uses(values, duration):
    """Bounded explicit uses; repeated skill/start entries use the largest CD."""
    if not isinstance(values, (tuple, list)) or len(values) > 32:
        raise ValueError("Use a bounded list of tactical cooldown reservations")
    uses = {}
    for row in values:
        if (not isinstance(row, (tuple, list)) or len(row) != 3 or type(row[0]) is not int or row[0] <= 0
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                       or not 0 <= v <= 3600 for v in row[1:])):
            raise ValueError("Invalid tactical cooldown reservation")
        sid, start, cooldown = row
        if start < duration:
            uses[(sid, float(start))] = max(uses.get((sid, float(start)), 0), float(cooldown))
    return tuple((sid, start, cooldown) for (sid, start), cooldown in sorted(uses.items()))


@dataclass
class Action:
    key: str
    name: str
    skill_id: int
    cast: float                    # action time at 0% combat speed (seconds)
    cooldown: float = 0.0
    cd_group: str | None = None
    mp: float = 0.0
    requires: tuple = ()           # target debuff names that must be active
    on_cast: Callable | None = None
    affected_by_cdr: bool = True
    skill_speed: float = 0.0
    element: str | None = None
    is_filler: bool = False
    tags: tuple = ()
    requires_charge: bool = False  # an in-game macro cannot hold the skill button
    charge_level: int | None = None
    targets: int = 1               # enemies one cast can hit ("up to N enemies")
    reach: float | None = None     # metres from the caster the skill reaches (None: not stated)
    control: float = 0.0           # expected seconds of hard crowd control per enemy hit, per cast
    heal: bool = False             # a heal press (no damage, ``cooldown`` = its period): never chosen, its time
                                   # spread over the other actions when the party takes damage (Target.party_damage)

    def group(self) -> str:
        return self.cd_group or self.key


@dataclass(order=True)
class _Event:
    t: float
    seq: int
    fn: Callable = field(compare=False)


@dataclass
class Buff:
    name: str
    until: float
    stats: dict


class Sim:
    def __init__(self, derived: Derived, actions: dict[str, Action], policy: list,
                 target: Target | None = None, config: SimConfig | None = None,
                 hooks: list | None = None, cond_mods: list | None = None,
                 mp_start: float | None = None):
        self.base = derived
        self.actions = actions
        self.policy = policy
        self.target = target or Target()
        self.cfg = config or SimConfig()
        self.hooks = hooks or []           # fn(sim, t, hit_info) after each hit
        self.cond_mods = cond_mods or []   # fn(sim, t) -> dict of temporary stat adds
        self.t = 0.0
        self._degenerate = False           # set if a safety cap trips (non-terminating same-instant chain)
        self._land_depth = 0               # synchronous hook -> hit -> land recursion depth
        self.events: list[_Event] = []
        self._seq = itertools.count()
        self.ready: dict[str, float] = {}
        # The share of the time heals take while the party takes damage, spread evenly over every other
        # action: what a heal at an unknown moment costs on average, so no build gains by where its heals fall.
        self.heal_share = min(0.5, sum((a.cast / max(0.2, 1.0 + derived.combat_speed) + self.cfg.latency) / a.cooldown
                                       for a in actions.values() if a.heal and a.cooldown > 0)) \
            if self.target.party_damage else 0.0
        self.buffs: dict[str, Buff] = {}
        self.debuffs: dict[str, Buff] = {}
        self.dots: dict[str, dict] = {}
        self.mp = derived.mp_max if mp_start is None else mp_start
        self.chain: dict[str, tuple[int, float]] = {}
        self.icd: dict[str, float] = {}
        self.proc_acc: dict[str, float] = {}
        self.kit_state: dict[str, dict] = {}  # Mutable kit state belongs to this run, never shared closures.
        self.damage_by: dict[str, float] = {}
        self.hits_by: dict[str, int] = {}
        self.casts: dict[str, int] = {}
        self.buff_time: dict[str, float] = {}
        self.timeline: list[tuple[float, str]] = []
        self.damage_events: list = []
        self.action_blocks = action_blocks(self.cfg.action_blocks, self.cfg.duration)
        self.tactical_uses = tactical_uses(self.cfg.tactical_uses, self.cfg.duration)
        self._tactical_groups = {}
        self._reservation_report = []
        for sid, start, cooldown in self.tactical_uses:
            matches = sorted(key for key, action in self.actions.items() if action.skill_id == sid)
            groups = sorted({self.actions[key].group() for key in matches})
            for group in groups:
                uses = self._tactical_groups.setdefault(group, {})
                uses[start] = max(uses.get(start, 0), cooldown)
            self._reservation_report.append({"skill_id": sid, "start_s": start, "cooldown_s": cooldown,
                                             "matched_actions": matches, "cooldown_groups": groups,
                                             "status": "reserved" if groups else "no_modeled_action"})
        for group, uses in self._tactical_groups.items():
            ordered = sorted(uses.items())
            if any(next_start+EPS < start+cooldown for (start, cooldown), (next_start, _) in zip(ordered, ordered[1:])):
                raise ValueError(f"Tactical uses conflict in modeled cooldown group {group}; adjust starts or assumed cooldowns")
        self.total = 0.0
        self.mp_floor = self.mp
        self._ver = 0
        self._mods_cache = (None, None, None)
        self.control_s = 0.0

    # ------------------------------------------------------------------ API
    def schedule(self, t: float, fn: Callable) -> None:
        heapq.heappush(self.events, _Event(t, next(self._seq), fn))

    def has_buff(self, name: str, t: float | None = None) -> bool:
        b = self.buffs.get(name)
        return b is not None and b.until > (self.t if t is None else t) + EPS

    def has_debuff(self, name: str, t: float | None = None) -> bool:
        b = self.debuffs.get(name)
        return b is not None and b.until > (self.t if t is None else t) + EPS

    def buff(self, name: str, duration: float, stats: dict | None = None, t: float | None = None):
        t = self.t if t is None else t
        self.buffs[name] = Buff(name, t + duration, stats or {})
        self._ver += 1

    def debuff(self, name: str, duration: float, stats: dict | None = None, t: float | None = None):
        t = self.t if t is None else t
        cur = self.debuffs.get(name)
        until = t + duration
        if cur is not None and cur.until > until:
            until = cur.until
        self.debuffs[name] = Buff(name, until, stats or {})
        self._ver += 1

    def remaining_cd(self, group: str) -> float:
        return max(0.0, self.ready.get(group, 0.0) - self.t)

    def reduce_cd(self, group: str, seconds: float) -> None:
        if group == "all":
            for g in list(self.ready):
                if self._cdr_ok(g):
                    self.ready[g] = max(self.t, self.ready[g] - seconds)
            return
        if group in self.ready:
            self.ready[group] = max(self.t, self.ready[group] - seconds)

    def reset_cd(self, group: str) -> None:
        self.ready[group] = self.t

    def _cdr_ok(self, group: str) -> bool:
        for a in self.actions.values():
            if a.group() == group:
                return a.affected_by_cdr
        return True

    def control(self, seconds: float) -> None:
        """Hard crowd control applied to enemies (seconds, summed over the enemies hit)."""
        self.control_s += seconds

    def gain_mp(self, amount: float) -> None:
        self.mp = min(self.base.mp_max, self.mp + amount)

    def proc(self, key: str, chance: float, icd: float, t: float) -> bool:
        """Expected-value proc: accumulate chance while off internal cooldown."""
        if self.icd.get(key, -1.0) > t + EPS:
            return False
        acc = self.proc_acc.get(key, 0.0) + chance
        if acc >= 1.0 - EPS:
            self.proc_acc[key] = acc - 1.0
            self.icd[key] = t + icd
            return True
        self.proc_acc[key] = acc
        return False

    def stat_mods(self, t: float) -> dict:
        ct, cv, cm = self._mods_cache
        if ct == t and cv == self._ver:
            mods = dict(cm)
        else:
            mods = {}
            for b in self.buffs.values():
                if b.until > t + EPS and b.stats:
                    for k, v in b.stats.items():
                        mods[k] = mods.get(k, 0.0) + v
            for b in self.debuffs.values():
                if b.until > t + EPS and b.stats:
                    for k, v in b.stats.items():
                        mods[k] = mods.get(k, 0.0) + v
            self._mods_cache = (t, self._ver, dict(mods))
        for fn in self.cond_mods:
            for k, v in fn(self, t).items():
                mods[k] = mods.get(k, 0.0) + v
        return mods

    def hit(self, source: str, flat: float, coef: float, *, element: str | None = None,
            tags: tuple = (), n: int = 1, spread: float = 0.0, delay: float = 0.0,
            mult: float = 1.0, mults: list | None = None, on_each: Callable | None = None,
            mods: dict | None = None):
        """Deal ``n`` hits that together sum to (flat + coef*Attack) * mult.

        ``mults`` optionally gives a per-hit multiplier list (e.g. stacking
        fireballs); ``on_each(sim, t, i)`` runs after each hit lands.
        """
        if n <= 0:
            return
        per_flat, per_coef = flat / n, coef / n
        for i in range(n):
            t_hit = self.t + delay + (spread * i / max(1, n - 1) if n > 1 else 0.0)
            m = mult * (mults[i] if mults else 1.0)

            def land(t_hit=t_hit, m=m, i=i):
                self._land(t_hit, source, per_flat, per_coef, element, tags, m, mods)
                if on_each:
                    on_each(self, t_hit, i)
            if t_hit <= self.t + EPS:
                land()
            else:
                self.schedule(t_hit, land)

    def dot(self, name: str, source: str, tick_flat: float, tick_coef: float, interval: float,
            duration: float, *, element: str | None = None, start: float | None = None):
        """Apply/refresh a damage-over-time effect (one instance per name)."""
        t0 = self.t if start is None else start
        d = self.dots.get(name)
        if d and d["until"] > t0 + EPS:
            d["until"] = max(d["until"], t0 + duration)
            d.update(flat=tick_flat, coef=tick_coef)
            self.debuff(name, d["until"] - self.t)
            return
        d = {"until": t0 + duration, "flat": tick_flat, "coef": tick_coef, "interval": interval,
             "element": element, "source": source}
        self.dots[name] = d
        self.debuff(name, duration, t=t0)

        def tick(t_tick=t0 + interval):
            dd = self.dots.get(name)
            if dd is not d or t_tick > d["until"] + EPS:
                return
            self._land(t_tick, d["source"], d["flat"], d["coef"], d["element"], ("dot",), 1.0)
            self.schedule(t_tick + d["interval"], lambda tt=t_tick + d["interval"]: tick(tt))
        self.schedule(t0 + interval, tick)

    # ------------------------------------------------------------- internals
    def _land(self, t: float, source: str, flat: float, coef: float, element, tags, mult,
              extra: dict | None = None):
        if SKILL_MULT and not self.target.is_player:
            mult *= SKILL_MULT.get(source.split(" (")[0], 1.0)
        mods = self.stat_mods(t)
        if extra:
            mods = dict(mods)
            for k, v in extra.items():
                mods[k] = mods.get(k, 0.0) + v
        ctx = HitContext(flat=flat, coef=coef, element=element, tags=tags, mult=mult)
        dmg = expected_hit(self.base, mods, self.target, ctx)
        if self.cfg.record_damage:
            if len(self.damage_events) >= 50000:
                raise ValueError("Final simulation damage trace exceeds 50,000 hits")
            self.damage_events.append([t, dmg])
        self.total += dmg
        self.damage_by[source] = self.damage_by.get(source, 0.0) + dmg
        self.hits_by[source] = self.hits_by.get(source, 0) + 1
        info = {"source": source, "element": element, "tags": tags, "dmg": dmg}
        if self._land_depth >= _MAX_LAND_DEPTH:
            # A hook kept landing more same-instant hits; stop firing hooks here so the chain
            # unwinds instead of overflowing the stack. The hit's own damage is still counted.
            self._degenerate = True
            return
        self._land_depth += 1
        try:
            for hk in self.hooks:
                hk(self, t, info)
        finally:
            self._land_depth -= 1

    def _advance_to(self, t_new: float) -> None:
        drained = 0
        while self.events and self.events[0].t <= t_new + EPS:
            ev = heapq.heappop(self.events)
            self._regen(ev.t)
            self.t = max(self.t, ev.t)
            ev.fn()
            drained += 1
            if drained >= _MAX_EVENTS_PER_ADVANCE:
                # A hit whose hook keeps scheduling more same-instant work (a self-triggering
                # proc under extreme gear) would spin here forever. Drop the remaining backlog so
                # the sim terminates; this only trips on a degenerate build, never a real one.
                self.events.clear()
                self._degenerate = True
                break
        self._regen(t_new)
        self.t = max(self.t, t_new)

    def _regen(self, t: float) -> None:
        if t > self.t:
            self.mp = min(self.base.mp_max, self.mp + self.base.mp_regen * (t - self.t))
            for name, b in self.buffs.items():
                lo, hi = self.t, min(t, b.until)
                if hi > lo:
                    self.buff_time[name] = self.buff_time.get(name, 0.0) + hi - lo
            self.t = t

    def action_time(self, a: Action) -> float:
        mods = self.stat_mods(self.t)
        cs = self.base.combat_speed + mods.get("combat_speed", 0.0) + a.skill_speed
        dur = a.cast / max(0.2, 1.0 + cs)
        if self.cfg.quantize:
            dur = math.ceil(dur / self.cfg.tick - 1e-6) * self.cfg.tick
        return (dur + self.cfg.latency) / (1.0 - self.heal_share)

    def mp_cost(self, a: Action) -> float:
        return a.mp * max(0.0, 1.0 - self.base.mp_cost_red)

    def tactical_blocked(self, a: Action) -> bool:
        """Keep a modeled cooldown group available for explicit assumed uses.

        Fixed post-use exclusions are not shortened by modeled reset hooks.
        Tactical damage, MP and on_cast callbacks are deliberately absent.
        """
        uses = self._tactical_groups.get(a.group(), {})
        if not uses:
            return False
        modeled_cd = a.cooldown * max(0.0, 1.0 - (self.base.cdr if a.affected_by_cdr else 0.0))
        for start, cooldown in uses.items():
            if self.t < start-EPS:
                if self.t + max(modeled_cd, cooldown) > start+EPS:
                    return True
            elif self.t < start+cooldown-EPS:
                return True
        return False

    def usable(self, a: Action) -> bool:
        if a.heal or self.tactical_blocked(a):          # a heal's time is spread over the other actions
            return False
        if (self.target.out_of_reach and a.reach is not None and a.reach < self.target.reach_m
                and any(s <= self.t < e for s, e in self.target.out_of_reach)):
            return False
        if self.action_blocks:
            end = self.t + self.action_time(a)
            if any(self.t < stop-EPS and end > start+EPS for start, stop in self.action_blocks):
                return False
        if self.ready.get(a.group(), 0.0) > self.t + EPS:
            return False
        if self.mp + EPS < self.mp_cost(a):
            return False
        for req in a.requires:
            if req.startswith("!"):
                if self.has_debuff(req[1:]) or self.has_buff(req[1:]):
                    return False
            elif req == "stagger":
                if not any(s <= self.t < e for s, e in self.target.stagger_windows):
                    return False
            elif not (self.has_debuff(req) or self.has_buff(req)):
                return False
        return True

    def choose(self):
        if callable(self.policy):
            return self.policy(self)
        for entry in self.policy:
            key, cond = (entry, None) if isinstance(entry, str) else entry
            a = self.actions.get(key)
            if a is None or not self.usable(a):
                continue
            if cond is not None and not cond(self):
                continue
            return a
        return None

    def cast(self, a: Action) -> float:
        self.mp -= self.mp_cost(a)
        self.mp_floor = min(self.mp_floor, self.mp)
        self.casts[a.key] = self.casts.get(a.key, 0) + 1
        self.timeline.append((self.t, a.key))
        if a.cooldown > 0:
            cd = a.cooldown * (1.0 - (self.base.cdr if a.affected_by_cdr else 0.0))
            self.ready[a.group()] = self.t + cd
        dur = self.action_time(a)
        if a.on_cast:
            a.on_cast(self, a)
        return dur

    def run(self) -> "SimResult":
        T = self.cfg.duration
        idle = 0.0
        steps = 0
        deadline = time.monotonic() + _SIM_WALL_LIMIT_S
        while self.t < T - EPS:
            steps += 1
            if steps > _MAX_RUN_STEPS or (steps & 0x3FFF == 0 and time.monotonic() > deadline):
                # Backstop: the per-advance cap already bounds same-instant chains; these guard the
                # outer loop (by step count and wall-clock) so a sim can never run unbounded —
                # regardless of what a kit schedules or how extreme the imported gear is.
                self._degenerate = True
                break
            blocked = next((stop for start, stop in self.action_blocks if start-EPS <= self.t < stop-EPS), None)
            if blocked is not None:
                idle += blocked-self.t
                self._advance_to(blocked)
                continue
            a = self.choose()
            if a is None:
                next_start = next((start for start, _ in self.action_blocks if start > self.t+EPS), T)
                until = min(T, self.t+0.05, next_start)
                idle += until-self.t if self.action_blocks else 0.05
                self._advance_to(until)
                continue
            # Callable policies may bypass usable(); never start across a pause.
            conflict = next((stop for start, stop in self.action_blocks
                             if self.t < stop-EPS and self.t+self.action_time(a) > start+EPS), None)
            if conflict is not None:
                idle += conflict-self.t
                self._advance_to(conflict)
                continue
            if self.tactical_blocked(a):
                until = min(T, self.t+0.05)
                idle += until-self.t
                self._advance_to(until)
                continue
            dur = self.cast(a)
            self._advance_to(min(T, self.t + dur))
        # let already-scheduled damage inside the window land, ignore the rest
        self._advance_to(T)
        return SimResult(self.total, T, dict(self.damage_by), dict(self.hits_by),
                         dict(self.casts), {k: v / T for k, v in self.buff_time.items()},
                         idle, self.mp_floor, list(self.timeline), list(self._reservation_report),
                         sorted([[min(T, max(0.0, t)), amount] for t, amount in self.damage_events]),
                         control=self.control_s)


@dataclass
class SimResult:
    total: float
    duration: float
    damage_by: dict
    hits_by: dict
    casts: dict
    uptime: dict
    idle: float
    mp_floor: float
    timeline: list
    action_reservations: list = field(default_factory=list)
    damage_events: list = field(default_factory=list)
    control: float = 0.0           # seconds of hard crowd control applied to enemies (World PvP)

    @property
    def dps(self) -> float:
        return self.total / self.duration

    def shares(self) -> dict:
        tot = self.total or 1.0
        return {k: v / tot for k, v in sorted(self.damage_by.items(), key=lambda kv: -kv[1])}
