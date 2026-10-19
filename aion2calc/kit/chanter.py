"""Chanter kit built from the global client's skill tables.

The Chanter is a staff hybrid, and the generic model misses its burst engine
and its mantras.  This kit adds:

* **Incandescent Blow -> Bursting Blow.**  Incandescent Blow has no cooldown; its MP
  cost (Onslaught's chain and Rushing Smash restore MP) limits it, and its own chain
  skill Bursting Blow follows nearly every press (0.2.319).
* **Spinning Strike -> Dark Crush.**  Spinning Strike is a large nuke that also
  grants a stacking Critical Damage buff and opens a Dark Crush window;
  Impactful Crush and Marchutan's Wrath open one too.  Dark Crush (a 5s-cooldown
  nuke, or pressed back to back with "Removes [Dark Crush] cooldown") is used in
  those windows.
* **Self crowd control gating Wave Blow** (Impactful Crush / Tremor Crush stun).
* **Mantras and buffs** — Undefeated Mantra (+PvE Damage Boost, a toggled aura
  pressed once), Power of the Storm (+Combat Speed, +cooldown
  reduction) — and the on-hit passives Raging Spell (vs Stagger/Impact) and
  Wind's Promise (on a Critical Hit, at the hit's own crit chance), plus Inspiring
  Spell / Attack Preparation / Wind's Promise crit stats.

Heals carry no damage, so no priority list holds them, but since 0.2.319 they take the
Chanter's time in a boss fight as the Cleric's do (:data:`ASSUME` ``heals_per_minute``).
Every damage number comes from ``data/global/classes/chanter.json``; only values the
client does not expose live in :data:`TIMING` / :data:`ASSUME`.
"""
from __future__ import annotations

from ..model.stats import crit_chance
from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, add_weave, fallback_to_generic, ms, spec_options  # noqa: F401

__all__ = ["build_kit", "spec_options"]

SID = dict(
    ONS=18010000, INCAND=18040000, RSMASH=18090000, ICRUSH=18060000, DCRUSH=18100000,
    GUST=18300000, HEATWAVE=18150000, RECUP=18120000, TREMOR=18210000, WAVEBLOW=18080000,
    SPIN=18290000, DEFI=18200000,
    BLESSLIFE=18710000, CROSS=18720000, PROTCIRC=18730000, INSPIRE=18740000, ATKPREP=18750000,
    IMPACT=18760000, RAGING=18770000, EPROMISE=18780000, SURVWILL=18790000, WINDPROM=18800000,
    MARCHUTAN=None, OBLITERATE=None, UNDEFEATED=None, ASSAULTSHOCK=None, ENSNARE=None,
    STORMPOWER=None, FRACBLOW=None,
)

_STIG_NAMES = {
    "MARCHUTAN": "Marchutan's Wrath", "OBLITERATE": "Obliterate", "UNDEFEATED": "Undefeated Mantra",
    "ASSAULTSHOCK": "Assault Shock", "ENSNARE": "Ensnaring Mark", "STORMPOWER": "Power of the Storm",
    "FRACBLOW": "Fracturing Blow",
}

#: Action time in seconds at 0% Combat Speed.  Measured (0.2.307) from the recorded casts of five
#: global Chanters (docs/methodology.md "Measured action times"); ``onslaught`` is a step of the
#: Onslaught -> Resonance Crush -> Bolt Crush chain pressed on its own, and ``bursting_blow`` /
#: ``piercing_strike`` the chain presses, charged to Incandescent Blow / Dark Crush when the chain is
#: taken.  Heat Wave Blow, Tremor Crush, Wave Blow and the stigmas keep their estimates (too few presses).
#: ``heal`` is a heal press (0.2.319), the same measure over 380 heal presses of 14 Chanters in the log
#: server's uploads (followed by another press within 1.5 s).
TIMING = {
    "onslaught": 0.94, "incandescent_blow": 0.63, "rushing_smash": 0.52, "impactful_crush": 0.43,
    "dark_crush": 0.54, "heat_wave_blow": 0.90, "tremor_crush": 0.90, "wave_blow": 0.95,
    "spinning_strike": 0.47, "chain_followup": 0.55, "stigma": 1.00,
    "bursting_blow": 0.82, "piercing_strike": 0.57, "heal": 0.56,
}

ASSUME = {
    "boss_breakable": True,       # self-stun gates Wave Blow
    "dark_crush_window": 2.0,     # seconds Dark Crush stays usable after Impactful Crush / Spinning Strike when their
                                  # tooltips give no number (they give 2 s; Marchutan's Wrath 3 s)
    "spin_stacks": 2,             # Spinning Strike Critical Damage stacks maintained
    "stagger_uptime": 0.02,       # Raging Spell (extra damage vs Stagger/Impact): about 2 procs a minute on bosses,
                                  # each a critical hit, in the log server's uploads (0.2.319; 0.50 before)
    # Measured in the log server's uploads (0.2.319: 175 boss fights of 14 Chanters; a community L45 parse
    # in 0.2.256 before), per press and crits aside:
    "piercing_frac": 1.52,        # a Piercing Strike press vs a Dark Crush press (1.65 before)
    "piercing_chance": 0.92,      # Piercing Strike follows 92% of Dark Crushes once the chain is taken
    "bursting_frac": 1.19,        # a Bursting Blow press vs an Incandescent Blow press (2.23 every 2nd press before)
    "bursting_chance": 0.90,      # Bursting Blow follows 90% of Incandescent Blows, for every Chanter (0.84-0.97):
                                  # it is the skill's own chain, not a specialization's. It costs what Incandescent
                                  # Blow costs (-95 each in the recording Chanters' MP readings, 0.2.319)
    # Heal presses (Recuperation, now and then Healing Touch or Guardian Blessing) a minute of boss fight:
    # 425 in 348 minutes of 175 recorded fights (0.2.319; the median fight 0.91, quartiles 0-2.5).
    "heals_per_minute": 1.2,
}

#: How long a toggled aura stays up once pressed (seconds; longer than any fight).
AURA_UP = 1e6

#: The basic-attack chain's three steps (name, share of the woven steps, damage per press against
#: the first step), the woven steps after each press and after any press recorded too rarely (the
#: median of the per-skill rates), from the recorded fights (0.2.309; re-measured on 175 boss fights in
#: the log server's uploads in 0.2.319; docs/methodology.md "Woven basic attacks").  Incandescent
#: Blow's carries the steps woven after its Bursting Blow too (0.72 + 0.55 at the chain's 90%).
WEAVE = {
    "steps": (("Onslaught", 0.36, 1.00), ("Resonance Crush", 0.33, 1.19), ("Bolt Crush", 0.30, 1.67)),
    "after": {"incandescent_blow": 1.215, "dark_crush": 0.50, "impactful_crush": 0.06, "spinning_strike": 0.07,
              "rushing_smash": 0.21, "marchutan": 0.03, "wave_blow": 0.14, "heat_wave_blow": 0.21,
              "tremor_crush": 0.08},
    "per_press": 0.09,
}


def build_kit(build: Build, cd: ClassData, filler: str = "onslaught") -> Kit:
    for key, name in _STIG_NAMES.items():
        s = cd.by_name.get(name)
        SID[key] = s["id"] if s else None

    L = build.effective_levels(cd)
    specs = {sid: set(v) for sid, v in build.specs.items()}

    def lv(key):
        sid = SID.get(key)
        return L.get(sid, 0) if sid else 0

    def has(key, idx):
        sid = SID[key]
        if sid is None or (sid + 10 * idx) not in specs.get(sid, set()):
            return False
        spec = next((s for s in cd.skills[sid]["specs"] if s["id"] == sid + 10 * idx), None)
        return spec is not None and spec["unlock"] <= L.get(sid, 1)

    def stig(key):
        sid = SID.get(key)
        return sid is not None and sid in build.stigmas

    def st(key, threshold):
        return stig(key) and build.stigmas[SID[key]] >= threshold

    def dmg(key, idx=0):
        v = cd.vals(SID[key], max(1, lv(key)))
        f, c = v[idx]
        return float(f), float(c) / 100.0

    A: dict[str, Action] = {}
    notes: list[str] = []
    static: dict[str, float] = {}

    def add_static(key, mapping):
        if lv(key) <= 0:
            return
        v = cd.vals(SID[key], lv(key))
        for idx, (field, scale) in mapping.items():
            if idx < len(v) and isinstance(v[idx], (int, float)):
                static[field] = static.get(field, 0.0) + v[idx] * scale

    add_static("INSPIRE", {0: ("crit", 1.0), 1: ("perfect", 0.01)})
    add_static("ATKPREP", {0: ("amp_pve", 0.01), 3: ("accuracy", 1.0)})
    add_static("IMPACT", {1: ("double", 0.01)})
    add_static("WINDPROM", {0: ("crit_dmg", 0.01)})

    # on-hit passives (hooks): Raging Spell (vs Stagger/Impact), Wind's Promise (on crit)
    rg_f = rg_c = 0.0
    if lv("RAGING") > 0:
        rv = cd.vals(SID["RAGING"], lv("RAGING"))
        rg_f, rg_c = float(rv[0][0]), float(rv[0][1]) / 100.0
    wp = None
    if lv("WINDPROM") > 0:
        wv = cd.vals(SID["WINDPROM"], lv("WINDPROM"))
        if len(wv) > 2 and isinstance(wv[2], list):
            wp = (float(wv[1]) / 100.0, float(wv[2][0]), float(wv[2][1]) / 100.0, ms(wv[4]) if len(wv) > 4 else 1.0)

    def hit_crit(sim, t, tags):
        """The chance that a hit with ``tags`` landing at ``t`` is critical (Wind's Promise needs one)."""
        if "crit" in tags:
            return 1.0
        return crit_chance(sim.base.crit_stat + sim.stat_mods(t).get("crit", 0.0), sim.target.crit_resist,
                           midpoint=1024.52 if sim.target.is_player else None)

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        # Raging Spell lands on a staggered boss, so it crits (98.8% of 689 recorded hits, 0.2.319).
        if rg_f and sim.proc("raging_spell", ASSUME["stagger_uptime"], 1.0, t):
            sim.hit("Raging Spell", rg_f, rg_c, tags=("proc", "crit"))
        # Wind's Promise: its chance on each critical hit, so at the hit's own crit chance (a flat 60% before
        # 0.2.319, three times the uploaded Chanters' ~20%).
        if wp and sim.proc("winds_promise", wp[0] * hit_crit(sim, t, info["tags"]), wp[3], t):
            sim.hit("Wind's Promise", wp[1], wp[2], tags=("proc",))

    # ----------------------------------------------------------------- actives
    on_f, on_c = dmg("ONS")

    def ons_cast(sim, a):
        mods = {"multihit": 0.5} if has("ONS", 3) else None
        sim.hit("Onslaught", on_f, on_c, mods=mods)
        sim.gain_mp(100 * (1.2 if has("ONS", 1) else 1.0))
        if has("ONS", 4):
            sim.reduce_cd("spinning_strike", 1.0)
    A["onslaught"] = Action("onslaught", "Onslaught", SID["ONS"], TIMING["onslaught"],
                            on_cast=ons_cast, is_filler=True)

    # Incandescent Blow: a hard-hitting swing with no cooldown, limited by its MP (the uploaded Chanters
    # press it 12.9 times a minute, a median 1.6 s apart, 0.2.319), followed by its own chain skill
    # Bursting Blow (1.19x a press; with the earlier 6 s cadence and the chain left to a specialization,
    # the model pressed Onslaught four times as often as the recorded Chanters).
    ic_f, ic_c = dmg("INCAND")
    ic_mult = 1.12 if has("INCAND", 3) else 1.0                  # up to 12% more on fewer targets

    def incand_cast(sim, a):
        sim.hit("Incandescent Blow", ic_f, ic_c, mult=ic_mult)
        if sim.proc("bursting_blow", ASSUME["bursting_chance"], 0.0, sim.t):
            k = ASSUME["bursting_frac"]
            sim.hit("Bursting Blow", ic_f * k, ic_c * k, delay=TIMING["chain_followup"])
    # Bursting Blow and Piercing Strike are their own presses; the kit folds each into its parent, so
    # the parent carries that press's time too, at the chain's rate.
    ic_t = TIMING["incandescent_blow"] + ASSUME["bursting_chance"] * TIMING["bursting_blow"]
    ic_mp = cd.mp(SID["INCAND"], lv("INCAND")) * (0.8 if has("INCAND", 1) else 1.0)
    A["incandescent_blow"] = Action("incandescent_blow", "Incandescent Blow", SID["INCAND"], ic_t,
                                    mp=ic_mp * (1.0 + ASSUME["bursting_chance"]), on_cast=incand_cast)

    rs_f, rs_c = dmg("RSMASH")

    def rsmash_cast(sim, a):
        sim.hit("Rushing Smash", rs_f, rs_c)
        sim.gain_mp(100)
    A["rushing_smash"] = Action("rushing_smash", "Rushing Smash", SID["RSMASH"], TIMING["rushing_smash"],
                                cooldown=cd.cd(SID["RSMASH"], lv("RSMASH")), on_cast=rsmash_cast)

    def window(key, idx):
        """How long a skill's "[Dark Crush] becomes available for {n}" lasts (its tooltip, else the assumption)."""
        v = cd.vals(SID[key], max(1, lv(key) or (build.stigmas.get(SID[key]) or 1)))
        return ms(v[idx]) if len(v) > idx and isinstance(v[idx], dict) else ASSUME["dark_crush_window"]

    # Impactful Crush (Stun -> gates Wave Blow; opens the Dark Crush window)
    ip_f, ip_c = dmg("ICRUSH")
    ip_window = window("ICRUSH", 4)

    def icrush_cast(sim, a):
        sim.hit("Impactful Crush", ip_f, ip_c)
        sim.buff("dark_crush", ip_window)
        if ASSUME["boss_breakable"]:
            sim.debuff("incap", 3.0)
    A["impactful_crush"] = Action("impactful_crush", "Impactful Crush", SID["ICRUSH"], TIMING["impactful_crush"],
                                  cooldown=cd.cd(SID["ICRUSH"], lv("ICRUSH")), mp=cd.mp(SID["ICRUSH"], lv("ICRUSH")),
                                  skill_speed=0.30 if has("ICRUSH", 4) else 0.0, on_cast=icrush_cast)

    # Dark Crush (usable in the window; low cooldown).  Its spec adds the Piercing
    # Strike chain (1.52x a Dark Crush press in the uploads) — previously dropped because the
    # hand-written cast bypassed the generic chain reader. "Critical Hit on hit" makes both certain
    # crits (the uploaders with it crit on every Dark Crush and Piercing Strike, 0.2.319), and
    # "Removes [Dark Crush] cooldown" lets it be pressed back to back in a window (0.6 s apart).
    dc_f, dc_c = dmg("DCRUSH")
    dc_tags = ("crit",) if has("DCRUSH", 3) else ()

    def dark_crush_cast(sim, a):
        sim.hit("Dark Crush", dc_f, dc_c, tags=dc_tags)
        if has("DCRUSH", 4) and sim.proc("piercing_strike", ASSUME["piercing_chance"], 0.0, sim.t):
            k = ASSUME["piercing_frac"]
            sim.hit("Piercing Strike", dc_f * k, dc_c * k, delay=TIMING["chain_followup"], tags=dc_tags)
    dc_t = TIMING["dark_crush"] + (ASSUME["piercing_chance"] * TIMING["piercing_strike"] if has("DCRUSH", 4) else 0.0)
    A["dark_crush"] = Action("dark_crush", "Dark Crush", SID["DCRUSH"], dc_t,
                             cooldown=0.0 if has("DCRUSH", 5) else cd.cd(SID["DCRUSH"], lv("DCRUSH")),
                             requires=("dark_crush",), on_cast=dark_crush_cast)

    hw_f, hw_c = dmg("HEATWAVE")
    A["heat_wave_blow"] = Action("heat_wave_blow", "Heat Wave Blow", SID["HEATWAVE"], TIMING["heat_wave_blow"],
                                 cooldown=cd.cd(SID["HEATWAVE"], lv("HEATWAVE")),
                                 on_cast=lambda sim, a: sim.hit("Heat Wave Blow", hw_f, hw_c))

    tr_f, tr_c = dmg("TREMOR")

    def tremor_cast(sim, a):
        sim.hit("Tremor Crush", tr_f, tr_c)
        if ASSUME["boss_breakable"]:
            sim.debuff("incap", 3.0)
    A["tremor_crush"] = Action("tremor_crush", "Tremor Crush", SID["TREMOR"], TIMING["tremor_crush"],
                               cooldown=cd.cd(SID["TREMOR"], lv("TREMOR")), on_cast=tremor_cast)

    # Wave Blow (needs Stun)
    wb_f, wb_c = dmg("WAVEBLOW")
    A["wave_blow"] = Action("wave_blow", "Wave Blow", SID["WAVEBLOW"], TIMING["wave_blow"],
                            cooldown=cd.cd(SID["WAVEBLOW"], lv("WAVEBLOW")), requires=("incap",),
                            on_cast=lambda sim, a: sim.hit("Wave Blow", wb_f, wb_c))

    # Spinning Strike (big nuke; stacking Critical Damage buff; opens Dark Crush)
    sv = cd.vals(SID["SPIN"], max(1, lv("SPIN")))
    sp_f, sp_c = float(sv[0][0]), float(sv[0][1]) / 100.0
    spin_cd = float(sv[2]) / 100.0 if len(sv) > 2 and isinstance(sv[2], (int, float)) else 0.15
    sp_window = window("SPIN", 4)
    sp_mult = 1.20 if has("SPIN", 3) else 1.0                    # up to +20% on fewer targets
    sp_tags = ("crit", "noparry") if has("SPIN", 5) else ()      # lands as a Critical Hit (100% recorded, 0.2.319)

    def spin_cast(sim, a):
        sim.hit("Spinning Strike", sp_f, sp_c, mult=sp_mult, tags=sp_tags)
        sim.buff("spin_critdmg", 30.0, {"crit_dmg": spin_cd * ASSUME["spin_stacks"]})
        sim.buff("dark_crush", sp_window)
    A["spinning_strike"] = Action("spinning_strike", "Spinning Strike", SID["SPIN"], TIMING["spinning_strike"],
                                  cooldown=cd.cd(SID["SPIN"], lv("SPIN")) - (5.0 if has("SPIN", 1) else 0.0),
                                  mp=cd.mp(SID["SPIN"], lv("SPIN")), on_cast=spin_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, SID, stig, st, notes)

    # Heals: no damage, in a fight whose party takes damage (the boss scenario, not the dummy) their time at
    # the recorded rate is spread over every other press (sim.engine.Action.heal), as the Cleric's.
    if ASSUME["heals_per_minute"] > 0:
        A["heals"] = Action("heals", "Heals", SID["RECUP"], TIMING["heal"],
                            cooldown=60.0 / ASSUME["heals_per_minute"], affected_by_cdr=False, heal=True)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes)
    # Piercing Strike is folded into Dark Crush when the chain is taken, so the steps woven after it are too.
    weave = dict(WEAVE, after=dict(WEAVE["after"]))
    if has("DCRUSH", 4):
        weave["after"]["dark_crush"] += ASSUME["piercing_chance"] * 0.25
    add_weave(A, weave, on_f, on_c, mp=100 * (1.2 if has("ONS", 1) else 1.0), skip=("onslaught",))
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _build_stigmas(A, build, cd, SID, stig, st, notes):
    def sdmg(key):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[0]
        return float(f), float(c) / 100.0

    # Undefeated Mantra: a toggled aura (+PvE Damage Boost; its tooltip gives no duration), so it is pressed
    # once and stays up. The recorded Chanters press it 0.1 times a minute (0.2.319); as a 10 s buff on its
    # 5 s toggle cooldown the kit re-pressed it every few seconds, a tenth of the fight.
    if stig("UNDEFEATED"):
        uv = cd.vals(SID["UNDEFEATED"], build.stigmas[SID["UNDEFEATED"]])
        A["undefeated"] = Action("undefeated", cd.skills[SID["UNDEFEATED"]]["name"], SID["UNDEFEATED"], 0.6,
                                cooldown=AURA_UP, affected_by_cdr=False,
                                on_cast=lambda sim, a, s=uv[0] / 100.0: sim.buff("undefeated", AURA_UP, {"amp": s}))
    # Power of the Storm: +Combat Speed and cooldown reduction
    if stig("STORMPOWER"):
        pv = cd.vals(SID["STORMPOWER"], build.stigmas[SID["STORMPOWER"]])
        A["stormpower"] = Action("stormpower", cd.skills[SID["STORMPOWER"]]["name"], SID["STORMPOWER"], TIMING["stigma"],
                                cooldown=cd.cd(SID["STORMPOWER"], build.stigmas[SID["STORMPOWER"]]),
                                on_cast=lambda sim, a, s=pv[0] / 100.0: sim.buff("stormpower", 20.0, {"combat_speed": s}))

    for key in ("MARCHUTAN", "OBLITERATE", "FRACBLOW", "ENSNARE", "ASSAULTSHOCK"):
        if not stig(key):
            continue
        akey = key.lower()
        f, c = sdmg(key)
        opens = None
        if key == "MARCHUTAN":                       # "[Dark Crush] becomes available for {2} on skill use"
            mv = cd.vals(SID[key], build.stigmas[SID[key]])
            opens = ms(mv[2]) if len(mv) > 2 and isinstance(mv[2], dict) else None

        def nuke(sim, a, key=key, f=f, c=c, opens=opens):
            sim.hit(a.name, f, c)
            if opens:
                sim.buff("dark_crush", opens)
            if key == "ASSAULTSHOCK" and st("ASSAULTSHOCK", 5):
                sim.buff("assault_shock", 5.0, {"attack_pct": 0.20})
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]), on_cast=nuke)


def _policy(actions: dict, filler: str) -> list:
    order = ["undefeated", "stormpower", "spinning_strike", "marchutan", "obliterate", "fracblow",
             "ensnare", "assaultshock", "impactful_crush", "dark_crush", "wave_blow", "heat_wave_blow",
             "tremor_crush", "rushing_smash", "incandescent_blow"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
