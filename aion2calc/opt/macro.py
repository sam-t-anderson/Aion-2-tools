"""Turn an optimized priority list into an AION 2 in-game Skill Macro + manual keys.

The in-game Skill Macro (added in the KR 2026-01-28 build) runs while its key is
held: it presses the hotbar keys on its lines in order, a 10 ms delay apart, and
loops; a line whose key has nothing ready is skipped, and manual presses always
take priority. A hotbar key holds up to four skills (the game's skill priority
stack): pressing it fires the lowest one that is ready, so a key is a small
priority list of its own. Since 0.2.371 the planner builds the macro from such
keys (:func:`plan_macro`, searched by simulation): before, every line held one
skill, which cannot say "Judgment whenever it is up" and left a Templar's
Judgment, ready for only 2-3 s after its triggers, behind a dozen lines. The
basic auto-attack stays on the held left mouse button and fires whenever no key
has a skill ready; where pressing it more often plays better (a Sorcerer short
of MP), the macro also gives it a line of its own. Charge skills stay on their
own keys (a macro only taps them), and a long-cooldown skill may too when
pressing it by hand is clearly worth the extra key. The layout of one skill per line is kept as the
alternative. A chain step is its parent's key pressed while the chain is open,
so a key holding the parent presses either.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..sim.engine import Sim
from .rotation import CONDITIONS

MODEL_VERSION = 4          # 4: macro lines are hotbar keys holding up to four skills (0.2.371)
STACK = 4                  # skills one hotbar key holds; pressing it fires the lowest one that is ready
MACRO_LINES = 20           # lines the in-game macro editor takes
MANUAL_MIN_CD = 30.0       # besides charge skills, only a skill with at least this cooldown goes on its own key
MANUAL_COST = 0.005        # ... and only when it gains this much DPS: every manual key costs the player attention
LINE_COST = 0.0005         # each further macro line must gain this much (a shorter macro is easier to set up)
SEARCH_EVALS = 2500        # simulations the key search may spend


@dataclass
class MacroPlan:
    macro_steps: list                   # macro lines: one skill (str), or a hotbar key's skills (tuple, lowest first)
    manual: list
    dps_macro: float
    dps_priority: float
    alt_steps: list | None = None       # the other layout (one-button or macro + manual keys)
    alt_manual: list | None = None
    dps_alt: float = 0.0
    auto_attack: str | None = None      # left mouse button: the basic auto-attack (the kit filler)
    chains: dict | None = None          # chain step -> the action whose key presses it (Action.chain_of)


class MacroPolicy:
    """Manual keys first (priority order), then the macro lines round-robin, then the held auto-attack.

    A line is one skill or a hotbar key's skills (a tuple, lowest first): the key fires the first of
    them that is ready, and the macro moves to the next line; a line with nothing ready is skipped.
    When no line has anything ready the held left mouse button attacks (``fallback``, the kit's
    basic auto-attack). A chain step has no key of its own (``Action.chain_of``): a macro step for
    it is its parent skill added again, and the parent's key presses the chain step while the chain
    is open and the parent otherwise. So a macro step for either presses whichever of the two is
    usable. Manual keys stay as listed: the player presses a chain step's key when the chain is open."""

    def __init__(self, manual: list, steps: list, fallback: str | None = None):
        self.manual = manual
        self.steps = steps
        self.fallback = fallback
        self.ptr = 0
        self._keys: dict | None = None

    def _presses(self, sim: Sim, step: str):
        if self._keys is None:
            chained: dict = {}
            for a in sim.actions.values():
                if a.chain_of in sim.actions:
                    chained.setdefault(a.chain_of, []).append(a.key)
            self._keys = {k: steps + [parent] for parent, steps in chained.items() for k in steps + [parent]}
        return self._keys.get(step, (step,))

    def __call__(self, sim: Sim):
        for e in self.manual:
            key, cond = (e if isinstance(e, tuple) else (e, None))
            a = sim.actions.get(key)
            if a and sim.usable(a) and (cond is None or CONDITIONS[cond](sim)):
                return a
        n = len(self.steps)
        for k in range(n):
            line = self.steps[(self.ptr + k) % n]
            for skill in (line if isinstance(line, (tuple, list)) else (line,)):
                for key in self._presses(sim, skill):
                    a = sim.actions.get(key)
                    if a and not a.requires_charge and sim.usable(a):
                        self.ptr = (self.ptr + k + 1) % n
                        return a
        for key in self._presses(sim, self.fallback) if self.fallback else ():
            a = sim.actions.get(key)
            if a and not a.requires_charge and sim.usable(a):
                return a
        return None


def plan_macro(derived, kit, policy: list, target, config, macro_cd_limit: float = 20.0,
               evals: int = SEARCH_EVALS) -> MacroPlan:
    """The macro to play ``policy`` (the ideal priority list) with: hotbar keys of up to four skills on the macro's
    lines plus manual keys (:func:`_stacked`), and as the alternative the best layout of one skill per line."""
    keyf = lambda e: e[0] if isinstance(e, tuple) else e
    policy = [e for e in policy if keyf(e) in kit.actions]
    # Left mouse button is the basic auto-attack: the kit's designated filler, never an arbitrary skill.
    auto = kit.filler if kit.filler in kit.actions and kit.actions[kit.filler].is_filler else None
    if auto is None:
        auto = next((keyf(e) for e in policy if kit.actions[keyf(e)].is_filler), None)

    def run(pol):
        if isinstance(pol, MacroPolicy):
            pol.fallback = auto                       # the left mouse button is held beside the macro key
        return Sim(derived, kit.actions, pol, target, config, hooks=kit.hooks,
                   cond_mods=kit.cond_mods).run().dps
    from .rotation import materialize
    dps_pri = run(materialize(policy))
    flat = _flat(run, derived, kit, policy, macro_cd_limit)
    lines, manual, dps = _stacked(run, kit, policy, auto, flat, evals)
    alt = max(flat, key=lambda f: f[2])
    return MacroPlan(lines, manual, dps, dps_pri, alt[0], alt[1], alt[2], auto_attack=auto,
                     chains={k: a.chain_of for k, a in kit.actions.items() if a.chain_of})


def _flat(run, derived, kit, policy: list, macro_cd_limit: float) -> list:
    """The layouts of one skill per macro line (the planner before 0.2.371): the short-cooldown core in the macro
    and the rest on manual keys, and one macro of every skill but the charge skills. ``[(steps, manual, dps)]``."""
    keyf = lambda e: e[0] if isinstance(e, tuple) else e
    manual, steps = [], []
    for e in policy:
        a = kit.actions[keyf(e)]
        if not a.requires_charge and (a.is_filler or (a.cooldown and a.cooldown * (1 - derived.cdr) <= macro_cd_limit
                           and not isinstance(e, tuple))):
            steps.append(keyf(e))
        else:
            manual.append(e)
    import itertools
    # A macro step for a parent skill presses its chain step too while the chain is open (MacroPolicy),
    # so each layout is also tried without its chain steps: a second step for the same key can help
    # (the Templar's Pummel) or crowd the macro (the Cleric's Earth's Retribution).
    chained = {k for k, a in kit.actions.items() if a.chain_of}

    def arrange(manual, steps):
        best_steps, best = steps, run(MacroPolicy(manual, steps))
        # the macro cycles, so a filler that sits first would starve the core: try orders
        fillers = [s for s in steps if kit.actions[s].is_filler]
        core = [s for s in steps if not kit.actions[s].is_filler]
        if len(core) <= 6:
            for perm in itertools.permutations(core):
                cand = list(perm) + fillers
                v = run(MacroPolicy(manual, cand))
                if v > best:
                    best, best_steps = v, cand
        return best_steps, manual, best

    split = arrange(manual, steps)
    lean_steps = [s for s in steps if s not in chained]
    # a chain step whose parent is in the macro needs no manual press either
    lean_manual = [e for e in manual if keyf(e) not in chained or kit.actions[keyf(e)].chain_of not in lean_steps]
    if (lean_steps, lean_manual) != (steps, manual):
        lean = arrange(lean_manual, lean_steps)
        if lean[2] > split[2]:
            split = lean
    # Even the larger macro needs manual charge skills: a macro only taps them.
    charged = [e for e in policy if kit.actions[keyf(e)].requires_charge]
    automatic = [keyf(e) for e in policy if not kit.actions[keyf(e)].requires_charge]
    order = [k for k in automatic if not kit.actions[k].is_filler] + \
        [k for k in automatic if kit.actions[k].is_filler]

    def improve(one):
        one_v = run(MacroPolicy(charged, one))
        improved = True
        while improved:
            improved = False
            for i in range(len(one) - 1):
                cand = one[:i] + [one[i + 1], one[i]] + one[i + 2:]
                v = run(MacroPolicy(charged, cand))
                if v > one_v * (1 + 1e-6):
                    one, one_v, improved = cand, v, True
        return one, charged, one_v

    single = improve(order)
    if any(k in chained for k in order):
        lean = improve([k for k in order if k not in chained])
        if lean[2] > single[2]:
            single = lean
    return [single, split]


def _stacked(run, kit, policy: list, auto: str | None, flat: list, evals: int, seed: int = 7):
    """Hotbar keys (up to :data:`STACK` skills each, lowest first, a no-cooldown filler on top), the macro's lines
    (a key may sit on several, so its skills come up more often) and the manual keys, found by simulation.

    Every skill of the priority list is on one key or on a manual key, never on two keys; a chain step rides its
    parent's key, and the auto-attack stays on the left mouse button. Charge skills are always manual; another
    skill only with a cooldown of at least :data:`MANUAL_MIN_CD`. Layouts are compared on simulated DPS less
    :data:`MANUAL_COST` per extra manual key and :data:`LINE_COST` per further line. The search starts from the
    priority list in keys of three, from keys that put one of the top four skills first on a key the macro presses
    every other line, and from the one-skill-per-line layouts (``flat``), then moves, swaps, merges and repeats keys
    and lines while that improves, within ``evals`` simulations. Returns ``(lines, manual, dps)``: each line is
    the tuple of its key's skills."""
    import random
    keyf = lambda e: e[0] if isinstance(e, tuple) else e
    A = kit.actions
    charged = [e for e in policy if A[keyf(e)].requires_charge]
    order = []
    for e in policy:
        k = keyf(e)
        if A[k].requires_charge:
            continue
        k = A[k].chain_of if A[k].chain_of in A else k        # a chain step is pressed with its parent's key
        if k != auto and k not in order:
            order.append(k)
    if not order:
        return [], list(charged), run(MacroPolicy(list(charged), []))
    filler = {k for k in order if A[k].is_filler}
    may_be_manual = {k for k in order if k not in filler and (A[k].cooldown or 0) >= MANUAL_MIN_CD}
    # The basic attack is held on the left mouse button, and it may also be a macro line of its own (its own key,
    # never stacked with other skills): the line presses it even while a key has a skill ready, which a build
    # short of MP needs (a geared Sorcerer's Flame Arrow restores MP: without such a line its keys fell from the
    # 94 % of one skill per line to 92 %).
    solo = {auto} if auto in A else set()
    rank = {k: i for i, k in enumerate(order)}

    def norm(keys, lines, manual):
        """A canonical layout: fillers on top of each key, no empty key, keys numbered by first line."""
        keys = [[k for k in key if k not in filler] + [k for k in key if k in filler] for key in keys]
        used = [i for i in dict.fromkeys(lines) if keys[i]]
        remap = {old: new for new, old in enumerate(used)}
        return (tuple(tuple(keys[i]) for i in used), tuple(remap[i] for i in lines if i in remap),
                tuple(sorted(manual, key=rank.get)))

    cache: dict = {}

    def value(state):
        if state not in cache:
            keys, lines, manual = state
            dps = run(MacroPolicy(list(charged) + list(manual), [keys[i] for i in lines]))
            cache[state] = (dps * (1 - MANUAL_COST * len(manual) - LINE_COST * max(0, len(lines) - 1)), dps)
        return cache[state]

    def valid(state):
        keys, lines, manual = state
        placed = [k for key in keys for k in key] + list(manual)
        return (all(len(key) <= STACK and sum(k in filler for k in key) <= 1 and (len(key) == 1 or not solo & set(key))
                    for key in keys)
                and len(placed) == len(set(placed)) and set(placed) | filler >= set(order) - filler
                and 0 < len(lines) <= MACRO_LINES and set(manual) <= may_be_manual)

    core = [k for k in order if k not in filler]
    fills = [k for k in order if k in filler]
    seeds = []
    chunks = [core[i:i + STACK - 1] for i in range(0, len(core), STACK - 1)] or [[]]
    for f in [None] + fills:                                       # priority keys of three, a filler on one key
        for at in range(len(chunks)) if f else [0]:
            keys = [list(c) + ([f] if f and i == at else []) for i, c in enumerate(chunks)]
            seeds.append(norm(keys, list(range(len(keys))), ()))
    for top in core[:4]:                                           # one top skill first on every other line
        rest = [k for k in core if k != top]
        head = [top] + rest[:STACK - 2] + fills[:1]
        tail = rest[STACK - 2:]
        others = [tail[i:i + STACK - 1] for i in range(0, len(tail), STACK - 1)]
        keys = [head] + [list(c) for c in others]
        lines = [0]
        for i in range(1, len(keys)):
            lines += [i, 0]
        seeds.append(norm(keys, lines[:-1] if len(lines) > 2 else lines, ()))
    for steps, manual, _ in flat:                                  # one skill per line
        keys, lines = [], []
        for st in steps:
            k = A[st].chain_of if A[st].chain_of in A else st
            if A[k].requires_charge:
                continue
            if [k] not in keys:
                keys.append([k])
            lines.append(keys.index([k]))
        extra = [keyf(e) for e in manual if not A[keyf(e)].requires_charge]
        for k in extra:
            if k not in may_be_manual and [k] not in keys:
                keys.append([k])
                lines.append(len(keys) - 1)
        if lines:
            seeds.append(norm(keys, lines, [k for k in extra if k in may_be_manual]))
    seeds = [st for st in dict.fromkeys(seeds) if valid(st)]
    seeds.sort(key=lambda st: -value(st)[0])
    rnd = random.Random(seed)

    def moves(state):
        keys, lines, manual = [list(map(list, state[0])), list(state[1]), list(state[2])]
        out = []

        def add(k2, l2, m2):
            st = norm(k2, l2, m2)
            if st != state and valid(st):
                out.append(st)
        cp = lambda: ([list(k) for k in keys], list(lines), list(manual))
        placed = {k for key in keys for k in key}
        for i, key in enumerate(keys):
            for j in range(len(key) - 1):                          # reorder a key
                k2, l2, m2 = cp()
                k2[i][j], k2[i][j + 1] = k2[i][j + 1], k2[i][j]
                add(k2, l2, m2)
            for j, sk in enumerate(key):
                for i2 in range(len(keys)):                        # to another key, lowest or highest
                    if i2 != i:
                        for pos in (0, len(keys[i2])):
                            k2, l2, m2 = cp()
                            k2[i][j:j + 1] = []
                            k2[i2].insert(pos, sk)
                            add(k2, l2, m2)
                k2, l2, m2 = cp()                                  # to a key of its own, on a new last line
                k2[i][j:j + 1] = []
                k2.append([sk])
                add(k2, l2 + [len(k2) - 1], m2)
                if sk in may_be_manual:                            # to a manual key
                    k2, l2, m2 = cp()
                    k2[i][j:j + 1] = []
                    add(k2, l2, m2 + [sk])
                if sk in filler or sk in solo:                     # a filler may go: the auto-attack fills in
                    k2, l2, m2 = cp()
                    k2[i][j:j + 1] = []
                    add(k2, l2, m2)
            for i2 in range(len(keys)):                            # merge two keys
                if i2 != i and len(key) + len(keys[i2]) <= STACK:
                    k2, l2, m2 = cp()
                    k2[i] = k2[i] + k2[i2]
                    k2[i2] = []
                    add(k2, [i if x == i2 else x for x in l2], m2)
        for f in fills:                                            # a dropped filler back on a key
            if f not in placed:
                for i in range(len(keys)):
                    k2, l2, m2 = cp()
                    k2[i].append(f)
                    add(k2, l2, m2)
        for f in solo - placed:                                    # the basic attack on a line of its own
            for p in range(len(lines) + 1):
                k2, l2, m2 = cp()
                k2.append([f])
                add(k2, l2[:p] + [len(k2) - 1] + l2[p:], m2)
        for sk in manual:                                          # a manual skill back on a key
            for i in range(len(keys)):
                k2, l2, m2 = cp()
                m2.remove(sk)
                k2[i].insert(0, sk)
                add(k2, l2, m2)
        for p in range(len(lines) + 1):                            # repeat a key on another line
            for i in range(len(keys)):
                add(*(lambda k2, l2, m2: (k2, l2[:p] + [i] + l2[p:], m2))(*cp()))
        for p in range(len(lines)):
            if lines.count(lines[p]) > 1:                          # drop a repeated line
                k2, l2, m2 = cp()
                del l2[p]
                add(k2, l2, m2)
            if p + 1 < len(lines):                                 # swap two lines
                k2, l2, m2 = cp()
                l2[p], l2[p + 1] = l2[p + 1], l2[p]
                add(k2, l2, m2)
        return out

    best = seeds[0]
    for start in seeds:                                            # best start first, while simulations remain
        cur = start
        while len(cache) < evals:
            nb = moves(cur)
            rnd.shuffle(nb)
            here = value(cur)[0]
            nxt = None
            for st in nb:
                if len(cache) >= evals:
                    break
                if value(st)[0] > here * (1 + 1e-5):
                    nxt = st
                    break
            if nxt is None:
                break
            cur = nxt
        if value(cur)[0] > value(best)[0]:
            best = cur
    keys, lines, manual = best
    manual_entries = [e for e in policy if A[keyf(e)].requires_charge or keyf(e) in manual]
    return [keys[i] for i in lines], manual_entries, value(best)[1]


def describe_plan(plan: MacroPlan) -> dict:
    """Report format shared by local reports and downloaded class presets."""
    from .rotation import describe
    return {"model_version": MODEL_VERSION,
            "steps": [list(st) if isinstance(st, tuple) else st for st in plan.macro_steps],
            "manual": describe(plan.manual),
            "dps_macro": plan.dps_macro, "dps_priority": plan.dps_priority,
            "alt_steps": plan.alt_steps, "alt_manual": describe(plan.alt_manual or []),
            "dps_alt": plan.dps_alt, "auto_attack": plan.auto_attack, "chains": plan.chains or {}}
