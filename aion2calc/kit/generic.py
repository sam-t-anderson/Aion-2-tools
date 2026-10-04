"""Data-driven kit for any class.

It reads the global skill table and turns tooltips / specialization texts into
simulator actions with a set of regular expressions.  It covers the mechanics
that move DPS the most (damage, cooldown changes, resets, skill speed,
guaranteed crits / multi-hits, damage and attack buffs, on-hit procs) and
ignores pure utility.  Class-specific kits (e.g. ``sorcerer.py``) override it
where a class has bespoke interactions.
"""
from __future__ import annotations

import re

from ..sim.engine import Action
from .base import Build, ClassData, spec_slots
from .sorcerer import Kit

DEFAULT_CAST = 0.95
BUFF_CAST = 0.60
FILLER_CAST = 0.80


def _ms(v) -> float:
    return v["ms"] / 1000.0 if isinstance(v, dict) and "ms" in v else float(v)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _damage_pairs(vals):
    return [v for v in (vals or []) if isinstance(v, list) and len(v) == 2
            and all(isinstance(x, (int, float)) for x in v)]


PASSIVE_STATS = [
    (r"PvE Damage Boost by \{(\d+)\}%", "amp_pve", 0.01),
    (r"(?<!PvE )(?<!PvP )Damage Boost by \{(\d+)\}%", "amp_all", 0.01),
    (r"Critical Damage Boost by \{(\d+)\}%", "crit_dmg", 0.01),
    (r"Critical Hit by \{(\d+)\}", "crit", 1),
    (r"Double Chance by \{(\d+)\}%", "double", 0.01),
    (r"Perfect Chance by \{(\d+)\}%", "perfect", 0.01),
    (r"Accuracy by \{(\d+)\}", "accuracy", 1),
    (r"Multi-hit Chance by \{(\d+)\}%", "multihit", 0.01),
    (r"Combat Speed by \{(\d+)\}%", "combat_speed", 0.01),
]
CONDITIONAL_PASSIVE = re.compile(r"\bwhen\b|\bfor \{\d+\}|on Block|on Evasion|after", re.I)


def build_kit(build: Build, cd: ClassData, filler: str | None = None) -> Kit:
    L = build.effective_levels(cd)
    specs = {sid: set(v) for sid, v in build.specs.items()}
    name_to_key = {s["name"]: _key(s["name"]) for s in cd.skills.values()}
    A: dict[str, Action] = {}
    static: dict[str, float] = {}
    procs = []
    notes = []

    def chosen(sid):
        s = cd.skills[sid]
        return [x for x in s.get("specs", []) if x["id"] in specs.get(sid, set())
                and x["unlock"] <= L.get(sid, 1)]

    # ---------------------------------------------------------------- passives
    for sid, s in cd.skills.items():
        if s["kind"] != "passive":
            continue
        v = cd.vals(sid, max(1, L.get(sid, 1))) or []
        tip = re.sub(r"<[^>]+>", "", s.get("tip", ""))
        first_sentence = tip.split(".")[0]
        if not CONDITIONAL_PASSIVE.search(first_sentence):
            for pat, field, sc in PASSIVE_STATS:
                for m in re.finditer(pat, first_sentence):
                    idx = int(m.group(1))
                    if idx < len(v) and isinstance(v[idx], (int, float)):
                        static[field] = static.get(field, 0.0) + v[idx] * sc
        cond = _proc_condition(tip, v)
        m = re.search(r"\{(\d+)\}% chance to (?:deal|inflict) \{(\d+)\}-\{\d+\}.*?(?:Cooldown: \{(\d+)\})", tip, re.S)
        if m:
            ci, di, icdi = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if di < len(v) and isinstance(v[di], list):
                procs.append((s["name"], v[ci] / 100.0, v[di], _ms(v[icdi]) if icdi < len(v) else 1.0, cond))
        elif re.search(r"Deals \{0\}-\{1\} (?:extra )?damage", tip) and _damage_pairs(v):
            m2 = re.search(r"Cooldown: \{(\d+)\}", tip)
            icd = _ms(v[int(m2.group(1))]) if m2 and int(m2.group(1)) < len(v) else 1.0
            procs.append((s["name"], 1.0, _damage_pairs(v)[0], icd, cond))

    # ----------------------------------------------------------------- actives
    fillers = []
    apply_dur_by: dict[str, float] = {}
    for sid, s in cd.skills.items():
        if s["kind"] not in ("active", "stigma"):
            continue
        if s["kind"] == "stigma" and sid not in build.stigmas:
            continue
        lvl = build.stigmas[sid] if s["kind"] == "stigma" else max(1, L.get(sid, 1))
        v = cd.vals(sid, lvl) or []
        tip = re.sub(r"<[^>]+>", "", s.get("tip", ""))
        pairs = _damage_pairs(v) if re.search(r"damage", tip, re.I) else []
        cdv = cd.cd(sid, lvl)
        mp = cd.mp(sid, lvl)
        key = name_to_key[s["name"]]
        cast = DEFAULT_CAST
        mult, skill_speed, tags = 1.0, 0.0, []
        on_hit_cd, on_cast_cd, resets, buffs = [], [], [], []
        dur_buff = None
        if s["kind"] == "stigma":
            active_specs = [x["text"] for x in s.get("specs", []) if x["unlock"] <= lvl]
        else:
            active_specs = [x["text"] for x in chosen(sid)]
        for t in active_specs:
            if m := re.match(r"-(\d+)s cooldown$", t):
                cdv = max(0.0, cdv - float(m.group(1)))
            elif m := re.search(r"-(\d+)s \[(.+?)\] cooldown(.*)$", t):
                target = name_to_key.get(m.group(2), _key(m.group(2)))
                if "on hit" in m.group(3) or "per" in m.group(3):
                    on_hit_cd.append((target, float(m.group(1))))
                elif target == key:
                    cdv = max(0.0, cdv - float(m.group(1)))
                else:
                    on_cast_cd.append((target, float(m.group(1))))
            elif m := re.search(r"-(\d+)s all skill cooldowns(.*)$", t):
                (on_hit_cd if "on hit" in m.group(2) else on_cast_cd).append(("all", float(m.group(1))))
            elif m := re.search(r"Reset \[(.+?)\] cooldown", t):
                resets.append(name_to_key.get(m.group(1), _key(m.group(1))))
            elif m := re.search(r"\+(\d+)% Skill Speed", t):
                skill_speed += float(m.group(1)) / 100
            elif re.search(r"Critical Hit on hit|lands as a? ?Critical Hit", t):
                tags.append("crit")
            elif re.search(r"Multi-Hit on hit|lands as Multi-Hit", t) and not t.startswith("+"):
                tags.append("multi")
            elif m := re.match(r"\+(\d+)% Multi-Hit on hit", t):
                tags.append(f"mh{m.group(1)}")
            elif m := re.search(r"Up to \+(\d+)% damage when more targets hit", t):
                mult *= 1 + float(m.group(1)) / 400   # single target: first quarter
            elif m := re.search(r"up to \+?(\d+)% (?:more )?damage when less targets", t, re.I):
                mult *= 1 + float(m.group(1)) / 100
            elif m := re.search(r"\+(\d+)% damage", t):
                mult *= 1 + float(m.group(1)) / 100
            elif m := re.search(r"-(\d+)% MP (?:Cost|consumed)", t):
                mp *= 1 - float(m.group(1)) / 100
            elif m := re.search(r"\+(\d+)% Attack for (\d+)s on hit", t):
                buffs.append(("attack_pct", float(m.group(1)) / 100, float(m.group(2))))
            elif m := re.search(r"\+(\d+)% PvE Damage Boost.*?for (\d+)s", t):
                buffs.append(("amp", float(m.group(1)) / 100, float(m.group(2))))
        # buff skills: "Increases ... Attack by {0}% ... for {n}"
        buff_stats = {}
        if not pairs:
            m = re.search(r"Attack by \{(\d+)\}%", tip)
            md = re.search(r"for \{(\d+)\}", tip)
            if m and md:
                buff_stats["attack_pct"] = v[int(m.group(1))] / 100
                dur_buff = _ms(v[int(md.group(1))])
            m = re.search(r"Damage Boost by \{(\d+)\}%", tip)
            if m and md:
                buff_stats["amp"] = v[int(m.group(1))] / 100
                dur_buff = _ms(v[int(md.group(1))])
            m = re.search(r"Critical Hit by \{(\d+)\}", tip)
            if m and md:
                buff_stats["crit"] = v[int(m.group(1))]
                dur_buff = _ms(v[int(md.group(1))])
            if not buff_stats:
                continue      # utility skill: not part of a DPS rotation
            cast = BUFF_CAST
        hits = cd.hits(sid, 1)
        is_filler = s["kind"] == "active" and cdv <= 0 and bool(pairs)
        if is_filler:
            cast = FILLER_CAST
            fillers.append(key)
        stag = "afflicted with Stagger" in tip
        requires = ("stagger",) if stag else ()
        mreq = re.search(r"afflicted with ([A-Z][\w' :]+?)(?= within| and|,|\.|$)", tip)
        if mreq and mreq.group(1) in name_to_key and mreq.group(1) != s["name"]:
            requires = requires + (name_to_key[mreq.group(1)],)
        if pairs:
            mb = re.search(r"increases the caster's (?:PvE )?Damage Boost by \{(\d+)\}%.*?for \{(\d+)\}", tip)
            if mb and int(mb.group(1)) < len(v) and int(mb.group(2)) < len(v):
                buffs.append(("amp", v[int(mb.group(1))] / 100, _ms(v[int(mb.group(2))])))
            ma = re.search(r"increases the caster's Attack by \{(\d+)\}%.*?for \{(\d+)\}", tip)
            if ma and int(ma.group(1)) < len(v) and int(ma.group(2)) < len(v):
                buffs.append(("attack_pct", v[int(ma.group(1))] / 100, _ms(v[int(ma.group(2))])))
        apply_dur = next((_ms(x) for x in v if isinstance(x, dict) and "ms" in x), 10.0)
        dmg = pairs[0] if pairs else None

        def on_cast(sim, a, dmg=dmg, hits=hits, mult=mult, tags=tuple(tags), on_hit_cd=tuple(on_hit_cd),
                    resets=tuple(resets), buffs=tuple(buffs), buff_stats=buff_stats, dur_buff=dur_buff,
                    on_cast_cd=tuple(on_cast_cd)):
            for g, sec in on_cast_cd:
                if g != a.key:
                    sim.reduce_cd(g, sec)
            mods = None
            htags = tuple(t for t in tags if not t.startswith("mh"))
            for t in tags:
                if t.startswith("mh"):
                    mods = {"multihit": float(t[2:]) / 100}
            if dmg:
                def each(sim, t, i):
                    for g, sec in on_hit_cd:
                        if g != a.key:
                            sim.reduce_cd(g, sec)
                sim.hit(a.name, dmg[0], dmg[1] / 100.0, n=hits, spread=0.3 * (hits - 1),
                        mult=mult, tags=htags, mods=mods, on_each=each if on_hit_cd else None)
            for g in resets:
                sim.reset_cd(g)
            sim.debuff(a.key, apply_dur_by.get(a.key, 10.0))
            for field, val, dur in buffs:
                sim.buff(f"{a.key}_{field}", dur, {field: val})
            if buff_stats and dur_buff:
                sim.buff(a.key, dur_buff, buff_stats)
        apply_dur_by[key] = apply_dur
        A[key] = Action(key, s["name"], sid, cast, cooldown=cdv, mp=mp, requires=requires,
                        skill_speed=skill_speed, on_cast=on_cast, is_filler=is_filler)

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        for name, chance, (f, c), icd, cond in procs:
            p = chance * _cond_factor(sim, t, info, cond)
            if p > 0 and sim.proc(name, p, icd, t):
                sim.hit(name, f, c / 100.0, tags=("proc",))

    order = sorted((k for k, a in A.items() if not a.is_filler),
                   key=lambda k: (A[k].cooldown == 0, -A[k].cooldown))
    filler_key = filler if filler in A else (fillers[0] if fillers else None)
    policy = order + ([filler_key] if filler_key else [])
    notes.append("generic kit: tooltip/spec text parsed automatically; verify class-specific interactions")
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler_key, notes=notes, levels=L)


def _proc_condition(tip: str, v) -> tuple:
    if re.search(r"on (?:landing )?a Critical Hit", tip):
        return ("crit",)
    if re.search(r"afflicted with Stagger", tip):
        return ("stagger",)
    m = re.search(r"target with \{(\d+)\}% HP or less", tip)
    if m and int(m.group(1)) < len(v):
        return ("hp_below", v[int(m.group(1))])
    m = re.search(r"HP is (?:above|more than) \{(\d+)\}%", tip)
    if m and int(m.group(1)) < len(v):
        return ("hp_above", v[int(m.group(1))])
    if re.search(r"when using skills that rush|Damage over Time|afflicted with Slow or Root", tip):
        return ("partial", 0.5)
    return ()


def _cond_factor(sim, t, info, cond) -> float:
    if not cond:
        return 1.0
    kind = cond[0]
    if kind == "crit":
        from ..model.stats import crit_chance
        if "crit" in info["tags"]:
            return 1.0
        return crit_chance(sim.base.crit_stat, sim.target.crit_resist)
    if kind == "stagger":
        return 1.0 if any(s <= t < e for s, e in sim.target.stagger_windows) else 0.0
    hp = sim.target.hp_pct(t, sim.cfg.duration) * 100
    if kind == "hp_below":
        return 1.0 if hp <= cond[1] else 0.0
    if kind == "hp_above":
        return 1.0 if hp > cond[1] else 0.0
    if kind == "partial":
        return cond[1]
    return 1.0


def spec_options(cd: ClassData, build: Build) -> dict[int, list[tuple]]:
    from itertools import combinations
    L = build.effective_levels(cd)
    out = {}
    for sid, s in cd.skills.items():
        if s["kind"] != "active" or not s.get("specs"):
            continue
        lvl = L.get(sid, 1)
        avail = [x["id"] for x in s["specs"] if x["unlock"] <= lvl]
        k = min(spec_slots(lvl), len(avail))
        out[sid] = [tuple(c) for c in combinations(avail, k)] if k > 0 else [()]
    return out
