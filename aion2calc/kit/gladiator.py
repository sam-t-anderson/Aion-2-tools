"""Gladiator kit built from the global client's skill tables.

Every damage number comes from ``data/global/classes/gladiator.json`` at the
build's effective level.  What the tooltip-driven generic kit cannot see — and
what this kit adds — is the melee structure that actually produces a
Gladiator's damage:

* **Self crowd control that gates a follow-up.**  Mocking Blade / Rush Strike
  knock the target down; Overhead Slam and Aerial Snare are only usable while
  that is true.  On a breakable training boss this is a real combo, not free
  spam (see :data:`ASSUME` ``boss_breakable``).
* **Chain skills.**  Keen Strike -> Reckless Strike, Overhead Slam -> Upward
  Strike, Ankle Slice -> Ankle Smash, Aerial Snare -> Forced Fall.  The generic
  kit ignores every chain follow-up; they are a large slice of melee damage.
* **Damage-amp buffs with real uptime.**  Ruinous Blow's *Prepare for Battle*
  (+PvE Boost, +Critical Hit for 20s), Zikel's Blessing (+Attack%), Rage Burst
  (+PvE Boost), Lunge Stance (+Combat Speed).
* **The on-hit passives** Murderous Burst (5-stack burst + Critical Damage
  Boost) and Destructive Impulse (flat extra vs Stagger/Impact).

Anything this kit does not model falls back to the generic tooltip reading, so
new content is still simulated.  Numbers the client does not expose live in
:data:`TIMING` and :data:`ASSUME` so they are easy to audit and to tune against
real combat-log captures.
"""
from __future__ import annotations

from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, add_weave, fallback_to_generic, spec_options  # noqa: F401 (spec_options is the module API)

__all__ = ["build_kit", "spec_options"]

SID = dict(
    KEEN=11020000, REND=11010000, LEAP=11190000, MOCK=11290000, OVER=11170000,
    SAR=11280000, ANKLE=11200000, CRUSH=11050000, RUSH=11360000, AERIAL=11300000,
    RUIN=11100000, DEFI=11260000,
    # passives
    SURV=11710000, PROT=11720000, BLOOD=11730000, IDENT=11740000, ATKPREP=11750000,
    IMPACT=11760000, DESTIMP=11770000, EXPCOUNTER=11780000, SURVWILL=11790000, MURDER=11800000,
    # stigmas
    BLADETOSS=11080000, FORCEDREST=11430000, WRATHWAVE=11240000, LUNGE=11400000,
    TENAC=11380000, ASSAULT=11700000, FRACRUSH=11450000, ZIKEL=11250000,
    LIFESTEAL=11340000, RAGE=11390000, FOCUSBLOCK=11110000, WAVEARMOR=11410000, ARMORBAL=11130000,
)

#: Action time of each skill in seconds at 0% Combat Speed (not in the client
#: data).  Measured (0.2.307) from the recorded casts of six global Gladiators:
#: the median time from a press to that player's next press (gaps up to 1.5 s)
#: plus the basic-attack steps woven in after it, less the 30 ms latency, at the
#: typical build's Combat Speed — see docs/methodology.md "Measured action
#: times".  ``keen_strike`` is a step of the basic-attack chain pressed on its
#: own, ``basic_combo`` Smashing Blow, ``upward_strike`` the Overhead Slam chain
#: press (charged to Overhead Slam when the chain is taken) and ``stigma`` the
#: stigma presses pooled.
#: ``chain_followup`` is the chain hit's delay, not an action time.
TIMING = {
    "keen_strike": 0.40, "rending_blow": 0.45, "leaping_slam": 0.47, "mocking_blade": 0.89,
    "overhead_slam": 0.40, "ankle_slice": 0.94, "crushing_wave": 0.93, "rush_strike": 0.54,
    "aerial_snare": 0.78, "ruinous_blow": 0.40, "chain_followup": 0.30, "stigma": 0.19,
    "basic_combo": 0.42, "upward_strike": 0.15,
}

#: Effects the tooltips leave out (assumptions; several were calibrated to a real
#: Gladiator dummy parse in 0.2.254 and re-measured on the log server's uploads in
#: 0.2.319 — see docs/methodology.md).  The skills below with no client coefficient
#: (Upward Strike and Smashing Blow) are measured relative to an Overhead Slam press.
#: Overhead Slam, Rending Blow and Smashing Blow land each press as two equal records
#: (together the tooltip once), so per-press ratios are the ones that hold.
ASSUME = {
    "boss_breakable": True,       # training boss stays knocked down, so Overhead Slam / Aerial Snare are available
    "chain_frac": 0.60,           # a generic chain follow-up vs the base hit (chains with no measured value)
    "upward_frac": 1.08,          # an Upward Strike press vs an Overhead Slam press, crits aside — measured
                                  # (0.2.319: 1.08 in the uploads; the 0.2.254 parse's 2.09 set it against one of
                                  # Overhead Slam's two records)
    "upward_chance": 0.90,        # Upward Strike follows ~90% of Overhead Slams once the chain is taken (0.2.319: 0.89
                                  # and 0.97 for the two uploaders with the most presses; 0.50 before)
    "overhead_spam_cd": 1.00,     # effective Overhead Slam cycle once "Remove cooldown" is taken — recorded casts
                                  # (0.2.307): never under ~1 s apart (10th percentile 0.97 s, median 1.18 s,
                                  # 223 intervals); the uploaders with the spec send no cooldown and press it
                                  # 0.95-0.98 s apart at the 10th percentile (0.2.319)
    "basic_frac": 0.47,           # a Smashing Blow press vs an Overhead Slam press, crits aside — measured (0.2.319
                                  # uploads: 0.47; 0.54 before)
    "ruinous_hits": 1,            # Ruinous Blow lands its tooltip once a press: 1.33 of it against Overhead Slam's
                                  # 1.00 at the uploaders' own levels and Attack (0.2.319), as one hit with the
                                  # extra-damage spec's +30% makes; its smaller follow-up record is part of that
                                  # (3 strikes before)
    "skill_crit": 0.30,           # "+30% Skill Critical Hit": 30% more Critical Hit for that skill, not a certain
                                  # crit — no uploader's Ruinous Blow crit every time (0.2.319)
    "murderous_icd": 3.0,         # Murderous Burst internal cooldown (parse: ~1 proc / 3s)
    "stagger_uptime": 0.0,        # share of time the boss carries Stagger/Impact (Destructive Impulse): no Destructive
                                  # Impulse hit landed on a boss in 115 minutes of the uploads' boss fights, nor in
                                  # the KR dummy logs; it lands on adds (0.2.319; 0.50 before)
    "murderous_stacks": 5,        # attacks to trigger Murderous Burst
    "extra_damage_frac": 0.30,    # "Extra damage on hit" specs that give no number
    "rage_frac": 0.25,            # Rage Burst's hit against its tooltip, relative to Overhead Slam's (0.2.319 uploads:
                                  # 0.24 at the uploaders' own levels, 0.25 at the typical ones)
    "keen_frac": 0.65,            # the basic chain's steps against Keen Strike's tooltip, relative to Overhead Slam's
                                  # (0.2.319 uploads: 0.65 at the uploaders' own levels, 0.61 at the typical ones)
    # MP the recording Gladiators' readings show (0.2.319, two players, 103 fights): Rending Blow and Smashing
    # Blow cost the same (-93 each, Rending Blow's tooltip 120 less its -20% specialization), Overhead Slam and
    # Upward Strike restore 50 a press, and a basic-chain step 180 (with its +20% specialization; the
    # tooltip says 100). Over the fights the MP gained and spent balance (4,362 and 4,387 a minute).
    "overhead_mp": 50,
    "step_mp": 150,
}

#: The basic-attack chain's three steps (name, share of the woven steps, damage per press against
#: Keen Strike), the woven steps after each press and after any press recorded too rarely (the
#: median of the per-skill rates), from the recorded fights (0.2.309; the main presses re-measured on
#: 45 boss fights in the log server's uploads in 0.2.319; docs/methodology.md "Woven basic
#: attacks").  Every step restores MP: the recorded MP reading rises 140-180 a step, Keen Strike's
#: tooltip says 100.
WEAVE = {
    "steps": (("Keen Strike", 0.40, 1.00), ("Rupture Strike", 0.32, 1.17), ("Wrathful Strike", 0.28, 1.60)),
    "after": {"rending_blow": 0.22, "basic_combo": 0.25, "overhead_slam": 0.10, "leaping_slam": 0.06,
              "ruinous_blow": 0.13, "rage": 0.01, "crushing_wave": 0.53, "mocking_blade": 0.41, "lunge": 0.05,
              "rush_strike": 0.10, "zikel": 0.0, "aerial_snare": 0.0, "ankle_slice": 1.06},
    "per_press": 0.10,
}


def build_kit(build: Build, cd: ClassData, filler: str = "keen_strike") -> Kit:
    L = build.effective_levels(cd)
    specs = {sid: set(v) for sid, v in build.specs.items()}

    def lv(key):
        return L.get(SID[key], 0)

    def has(key, idx):
        sid = SID[key]
        if (sid + 10 * idx) not in specs.get(sid, set()):
            return False
        spec = next((s for s in cd.skills[sid]["specs"] if s["id"] == sid + 10 * idx), None)
        return spec is not None and spec["unlock"] <= L.get(sid, 1)

    def stig(key):
        return SID[key] in build.stigmas

    def st(key, threshold):
        return stig(key) and build.stigmas[SID[key]] >= threshold

    def dmg(key, idx=0):
        v = cd.vals(SID[key], max(1, lv(key)))
        f, c = v[idx]
        return float(f), float(c) / 100.0

    A: dict[str, Action] = {}
    notes: list[str] = []

    # ---------------------------------------------------------------- passives
    static: dict[str, float] = {}

    def add_static(key, mapping):
        if lv(key) <= 0:
            return
        v = cd.vals(SID[key], lv(key))
        for idx, (field, scale) in mapping.items():
            if idx < len(v) and isinstance(v[idx], (int, float)):
                static[field] = static.get(field, 0.0) + v[idx] * scale

    add_static("IDENT", {0: ("crit", 1.0), 1: ("perfect", 0.01)})
    add_static("ATKPREP", {0: ("amp_pve", 0.01), 3: ("accuracy", 1.0)})
    add_static("IMPACT", {1: ("double", 0.01)})
    add_static("EXPCOUNTER", {0: ("front_amp", 0.01)})  # Front Attack Damage Boost (its own bucket)

    # on-hit passives ------------------------------------------------- hooks
    di_f = di_c = 0.0
    if lv("DESTIMP") > 0:
        di = cd.vals(SID["DESTIMP"], lv("DESTIMP"))
        di_f, di_c = float(di[0][0]), float(di[0][1]) / 100.0
    mb_f = mb_c = mb_cd = 0.0
    if lv("MURDER") > 0:
        mv = cd.vals(SID["MURDER"], lv("MURDER"))
        mb_f, mb_c, mb_cd = float(mv[1][0]), float(mv[1][1]) / 100.0, mv[3] / 100.0

    def hook(sim, t, info):
        state = sim.kit_state.setdefault("gladiator", {"menace": 0})
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        # Destructive Impulse: extra damage while the target carries Stagger/Impact.
        # Modeled as an on-hit rider with a ~1s internal cooldown (the client lists
        # no per-hit cooldown; a per-hit rider at this coefficient is implausibly
        # large), gated by how often the boss actually carries the status.
        if di_f and sim.proc("destructive_impulse", ASSUME["stagger_uptime"], 1.0, t):
            sim.hit("Destructive Impulse", di_f, di_c, tags=("proc",))
        # Murderous Burst: a stack per attack; at 5 stacks a burst and a Critical Damage
        # buff. A real parse bursts ~once every 3s (not once per 5 of this model's dense
        # attacks), so an internal cooldown gates it to the measured rate.
        if mb_f:
            state["menace"] += 1
            if state["menace"] >= ASSUME["murderous_stacks"] and t - state.get("mb_last", -1e9) >= ASSUME["murderous_icd"]:
                state["menace"] = 0
                state["mb_last"] = t
                sim.hit("Murderous Burst", mb_f, mb_c, tags=("proc",))
                sim.buff("murderous_burst", 3.0, {"crit_dmg": mb_cd})

    # ----------------------------------------------------------------- actives
    # The basic-attack chain pressed on its own (the filler): Keen Strike -> Rupture Strike ->
    # Wrathful Strike, one step a press, each restoring MP. Keen Strike's specs (4 targets, Reckless
    # Strike chain) ride its own step.
    ke_f, ke_c = dmg("KEEN")
    kb_f, kb_c = ke_f * ASSUME["keen_frac"], ke_c * ASSUME["keen_frac"]     # the steps as recorded
    keen_mp = ASSUME["step_mp"] * (1.2 if has("KEEN", 1) else 1.0)

    def keen_cast(sim, a):
        step, last = sim.chain.get("keen", (0, -99.0))
        if sim.t - last > sim.cfg.chain_window:
            step = 0
        step = step % len(WEAVE["steps"]) + 1
        sim.chain["keen"] = (step, sim.t)
        name, _, ratio = WEAVE["steps"][step - 1]
        mods = {"multihit": 0.5} if step == 1 and has("KEEN", 3) else None
        sim.hit(name, kb_f * ratio, kb_c * ratio, mods=mods)
        sim.gain_mp(keen_mp)
        if step == 1 and has("KEEN", 4):
            sim.reduce_cd("ruinous_blow", 1.0)
        if step == 1 and has("KEEN", 5):        # Reckless Strike chain
            k = ASSUME["chain_frac"]
            sim.hit("Reckless Strike", ke_f * k, ke_c * k, delay=TIMING["chain_followup"])
    A["keen_strike"] = Action("keen_strike", "Keen Strike", SID["KEEN"], TIMING["keen_strike"],
                              on_cast=keen_cast, is_filler=True)

    # Rending Blow (Stagger-gauge builder, strong single-target coef); Smashing Blow follows it
    re_f, re_c = dmg("REND")

    def rend_cast(sim, a):
        sim.hit("Rending Blow", re_f, re_c, mult=1.12 if has("REND", 4) else 1.0)
        sim.buff("rending_chain", sim.cfg.chain_window)
    rend_mp = cd.mp(SID["REND"], lv("REND")) * (0.8 if has("REND", 1) else 1.0)
    # While its chain is open Rending Blow's key presses Smashing Blow, so Rending Blow comes back only after
    # that step or once the window lapses (as the Templar's Pummel, 0.2.323).
    A["rending_blow"] = Action("rending_blow", "Rending Blow", SID["REND"], TIMING["rending_blow"],
                               mp=rend_mp, on_cast=rend_cast, requires=("!rending_chain",))

    # Leaping Slam (gap closer; Prepare for Battle on the caster at u8)
    ls_f, ls_c = dmg("LEAP")

    def leap_cast(sim, a):
        sim.hit("Leaping Slam", ls_f, ls_c)
        if has("LEAP", 1):
            sim.buff("prepare_for_battle", 3.0, _prepare_stats(cd, lv("RUIN")))
    A["leaping_slam"] = Action("leaping_slam", "Leaping Slam", SID["LEAP"], TIMING["leaping_slam"],
                               cooldown=cd.cd(SID["LEAP"], lv("LEAP")), on_cast=leap_cast)

    # Mocking Blade (Knockdown -> opens the Overhead Slam / Aerial Snare window)
    mo_f, mo_c = dmg("MOCK")
    kd_dur = 3.0 + (1.0 if has("MOCK", 4) else 0.0)

    def mock_cast(sim, a):
        n = 3 if has("MOCK", 3) else 1
        tags = ("multi", "noparry") if has("MOCK", 5) else ()
        sim.hit("Mocking Blade", mo_f, mo_c, n=n, spread=0.3 * (n - 1), tags=tags)
        if ASSUME["boss_breakable"]:
            sim.debuff("knockdown", kd_dur)
    A["mocking_blade"] = Action("mocking_blade", "Mocking Blade", SID["MOCK"], TIMING["mocking_blade"],
                                cooldown=cd.cd(SID["MOCK"], lv("MOCK")), mp=cd.mp(SID["MOCK"], lv("MOCK")),
                                on_cast=mock_cast)

    # Overhead Slam (the core single-target spam; its Upward Strike chain is the top
    # damage source). "Remove cooldown" turns its 5s cooldown into a fast spam cycle,
    # not literally 0 — recorded casts never repeat it faster than ~1 s, with Upward Strike
    # (measured at 1.08x an Overhead Slam press, following ~90% of them) the biggest hit in the
    # rotation. "Critical Hit on hit" makes both certain crits: the uploaders with it crit on every
    # Overhead Slam and every Upward Strike (0.2.319). On a breakable training target the knockdown
    # it needs is kept up, so it is available.
    ov_f, ov_c = dmg("OVER")
    ov_cd = ASSUME["overhead_spam_cd"] if has("OVER", 5) else cd.cd(SID["OVER"], lv("OVER"))
    gated = () if ASSUME["boss_breakable"] else ("knockdown",)

    def over_cast(sim, a):
        tags = ("crit",) if has("OVER", 4) else ()
        sim.hit("Overhead Slam", ov_f, ov_c, tags=tags)
        sim.gain_mp(ASSUME["overhead_mp"])
        if has("OVER", 3) and sim.proc("upward_strike", ASSUME["upward_chance"], 0.0, sim.t):
            k = ASSUME["upward_frac"]
            sim.hit("Upward Strike", ov_f * k, ov_c * k, delay=TIMING["chain_followup"], tags=tags)
            sim.gain_mp(ASSUME["overhead_mp"])
    # Upward Strike is its own press; the kit folds it into Overhead Slam, so its time is too.
    ov_t = TIMING["overhead_slam"] + (ASSUME["upward_chance"] * TIMING["upward_strike"] if has("OVER", 3) else 0.0)
    A["overhead_slam"] = Action("overhead_slam", "Overhead Slam", SID["OVER"], ov_t,
                                cooldown=ov_cd, requires=gated, on_cast=over_cast)

    # Ankle Slice (4 targets, Root; Ankle Smash chain)
    an_f, an_c = dmg("ANKLE")

    def ankle_cast(sim, a):
        tags = ("multi", "noparry") if has("ANKLE", 4) else ()
        sim.hit("Ankle Slice", an_f, an_c, tags=tags)
        if has("ANKLE", 2):
            k = ASSUME["chain_frac"]
            sim.hit("Ankle Smash", an_f * k, an_c * k, delay=TIMING["chain_followup"])
    A["ankle_slice"] = Action("ankle_slice", "Ankle Slice", SID["ANKLE"], TIMING["ankle_slice"],
                              cooldown=cd.cd(SID["ANKLE"], lv("ANKLE")), on_cast=ankle_cast)

    # Rush Strike (gap closer; Knockdown on NPC -> also opens the window)
    ru_f, ru_c = dmg("RUSH")
    rush_cd = cd.cd(SID["RUSH"], lv("RUSH")) - (10 if has("RUSH", 4) else 0)

    def rush_cast(sim, a):
        sim.hit("Rush Strike", ru_f, ru_c)
        if ASSUME["boss_breakable"]:
            sim.debuff("knockdown", 3.0)
    A["rush_strike"] = Action("rush_strike", "Rush Strike", SID["RUSH"], TIMING["rush_strike"],
                              cooldown=rush_cd, on_cast=rush_cast)

    # Aerial Snare (needs Knockdown; Airborne; Forced Fall chain)
    ae_f, ae_c = dmg("AERIAL")
    ae_cd = cd.cd(SID["AERIAL"], lv("AERIAL")) * (0.5 if has("AERIAL", 5) else 1.0)

    def aerial_cast(sim, a):
        tags = ("multi",) if has("AERIAL", 1) else ()
        sim.hit("Aerial Snare", ae_f, ae_c, tags=tags)
        if has("AERIAL", 4):
            k = ASSUME["chain_frac"]
            sim.hit("Forced Fall", ae_f * k, ae_c * k, delay=TIMING["chain_followup"])
    A["aerial_snare"] = Action("aerial_snare", "Aerial Snare", SID["AERIAL"], TIMING["aerial_snare"],
                               cooldown=ae_cd, mp=cd.mp(SID["AERIAL"], lv("AERIAL")),
                               requires=gated, on_cast=aerial_cast)

    # Smashing Blow: Rending Blow's follow-up, pressed within a few seconds of it (recorded after
    # 85-94% of Rending Blows, never more than 2.9 s later, and almost never without one). It has no
    # client coefficient, so it is measured at ~0.47x an Overhead Slam press in the uploads; ~14% of
    # real damage. It costs what Rending Blow costs (the recorded MP readings, 0.2.319).
    sb_f, sb_c = ov_f * ASSUME["basic_frac"], ov_c * ASSUME["basic_frac"]

    def smash_cast(sim, a):
        sim.buff("rending_chain", 0.0)                # spent
        sim.hit("Smashing Blow", sb_f, sb_c)
    A["basic_combo"] = Action("basic_combo", "Smashing Blow", 11420000, TIMING["basic_combo"], mp=rend_mp,
                              requires=("rending_chain",), on_cast=smash_cast, chain_of="rending_blow")

    # Ruinous Blow (biggest hit; grants Prepare for Battle for 20s)
    rb_f, rb_c = dmg("RUIN")
    rb_speed = 0.20 if has("RUIN", 1) else 0.0

    def ruin_cast(sim, a):
        tags = ("multi", "noparry") if has("RUIN", 5) else ()
        extra = 1.0 + ASSUME["extra_damage_frac"] if has("RUIN", 4) else 1.0
        mods = None
        if has("RUIN", 3):                              # +30% Skill Critical Hit: more Critical Hit, not a certain crit
            mods = {"crit": ASSUME["skill_crit"] * (sim.base.crit_stat + sim.stat_mods(sim.t).get("crit", 0.0))}
        # n splits one hit's damage, so mult restores each strike to the full coef (one strike since 0.2.319).
        hits = ASSUME["ruinous_hits"]
        sim.hit("Ruinous Blow", rb_f, rb_c, n=hits, spread=0.3, mult=extra * hits, tags=tags, mods=mods)
        sim.buff("prepare_for_battle", 20.0, _prepare_stats(cd, lv("RUIN")))
    A["ruinous_blow"] = Action("ruinous_blow", "Ruinous Blow", SID["RUIN"], TIMING["ruinous_blow"],
                               cooldown=cd.cd(SID["RUIN"], lv("RUIN")), mp=cd.mp(SID["RUIN"], lv("RUIN")),
                               skill_speed=rb_speed, on_cast=ruin_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, stig, st, notes)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes, timing=TIMING)
    # Upward Strike is folded into Overhead Slam, so the steps woven after it are too.
    weave = dict(WEAVE, after=dict(WEAVE["after"]))
    if has("OVER", 3):
        weave["after"]["overhead_slam"] += ASSUME["upward_chance"] * 0.01
    add_weave(A, weave, kb_f, kb_c, mp=keen_mp, skip=("keen_strike",))
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _prepare_stats(cd: ClassData, ruin_lv: int) -> dict:
    """Prepare for Battle: +PvE Damage Boost and +Critical Hit (from Ruinous Blow)."""
    v = cd.vals(SID["RUIN"], max(1, ruin_lv))
    amp = float(v[4]) / 100.0 if len(v) > 4 and isinstance(v[4], (int, float)) else 0.20
    crit = float(v[6]) if len(v) > 6 and isinstance(v[6], (int, float)) else 100.0
    return {"amp": amp, "crit": crit}


#: Equipped damage/buff stigmas modeled by hand: (flat/coef idx, extra on_cast).
_STIGMA_BUFF = {
    "ZIKEL": ("buff", {"attack_pct": 0.20}, 20.0),       # Zikel's Blessing: +20% Attack
    "LUNGE": ("buff", {"combat_speed": 0.20}, 20.0),     # Lunge Stance: +20% Combat Speed
}


def _build_stigmas(A, build, cd, stig, st, notes):
    def sdmg(key):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[0]
        return float(f), float(c) / 100.0

    # pure buff stigmas
    for key, (_, stats, dur) in _STIGMA_BUFF.items():
        if not stig(key):
            continue
        akey = key.lower()
        extra = dict(stats)
        if key == "ZIKEL" and st("ZIKEL", 10):
            extra["amp"] = extra.get("amp", 0.0) + 0.10     # +10% PvE Damage Boost
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]),
                         on_cast=(lambda sim, a, s=extra, d=dur: sim.buff(a.key, d, s)))

    # damage stigmas (with the notable rider each one carries)
    for key in ("RAGE", "LIFESTEAL", "WRATHWAVE", "FORCEDREST", "ASSAULT", "FRACRUSH", "BLADETOSS"):
        if not stig(key):
            continue
        akey = key.lower()
        f, c = sdmg(key)
        if key == "RAGE":                               # its hit lands a quarter of the tooltip (0.2.319)
            f, c = f * ASSUME["rage_frac"], c * ASSUME["rage_frac"]

        def nuke(sim, a, key=key, f=f, c=c):
            sim.hit(a.name, f, c)
            if key == "RAGE":
                amp = 0.10 + (0.10 if st("RAGE", 20) else 0.0)
                sim.buff("rage_burst", 10.0, {"amp": amp})
            elif key == "ASSAULT" and st("ASSAULT", 5):
                sim.buff("assault_strike", 5.0, {"attack_pct": 0.20})
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]), on_cast=nuke)


def _policy(actions: dict, filler: str) -> list:
    # Buffs, then the Ruinous Blow nuke, the Overhead Slam + Upward Strike core and Rending Blow
    # with the Smashing Blow that follows it (the highest-frequency damage skills in a real parse;
    # Smashing Blow first, as it is only there in Rending Blow's chain window and costs the same MP),
    # then the damage stigmas. The basic chain comes next: it is the Gladiator's MP engine (every
    # step restores MP), so it must out-prioritise the low-damage crowd-control / gap-closers —
    # otherwise, when Rending Blow has drained MP, the engine would cast a non-restoring CC skill
    # instead and the rotation would starve. A real dummy parse skips the CC skills entirely, so
    # leaving them below the always-available filler matches it (they stay for completeness /
    # other kits' callers, but a DPS rotation on a dummy never needs them).
    damage = ["zikel", "lunge", "ruinous_blow", "overhead_slam", "basic_combo", "rending_blow",
              "rage", "lifesteal", "assault", "forcedrest", "wrathwave", "fracrush", "bladetoss"]
    cc = ["aerial_snare", "leaping_slam", "mocking_blade", "rush_strike", "ankle_slice", "crushing_wave"]
    pol = [k for k in damage if k in actions]
    if filler in actions:
        pol.append(filler)                       # the MP-restoring basic chain, above the CC skills
    pol += [k for k in cc if k in actions and k != filler]
    return pol
