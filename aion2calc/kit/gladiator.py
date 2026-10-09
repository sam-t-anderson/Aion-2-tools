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
from .common import Kit, fallback_to_generic, spec_options  # noqa: F401 (spec_options is the module API)

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
#: data; melee swing/recovery estimated from community notes — see docs).
TIMING = {
    "keen_strike": 0.80, "rending_blow": 0.90, "leaping_slam": 1.00, "mocking_blade": 1.10,
    "overhead_slam": 0.70, "ankle_slice": 0.90, "crushing_wave": 1.00, "rush_strike": 0.90,
    "aerial_snare": 1.00, "ruinous_blow": 1.20, "chain_followup": 0.55, "stigma": 1.00,
}

#: Effects the tooltips leave out (assumptions; tune with real logs).
ASSUME = {
    "boss_breakable": True,       # training boss can be knocked down (gates Overhead Slam / Aerial Snare)
    "knockdown_uses": 3,          # Overhead Slams landed per knockdown window once cooldown-free
    "chain_frac": 0.60,           # a chain follow-up vs the base hit
    "stagger_uptime": 0.50,       # share of time the boss carries Stagger/Impact (Destructive Impulse)
    "murderous_stacks": 5,        # attacks to trigger Murderous Burst
    "extra_damage_frac": 0.30,    # "Extra damage on hit" specs that give no number
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
    add_static("EXPCOUNTER", {0: ("amp_pve", 0.01)})  # Front Attack Boost; the dummy is frontal

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
        # Murderous Burst: a stack per attack; at 5 a burst and a Critical Damage buff
        if mb_f:
            state["menace"] += 1
            if state["menace"] >= ASSUME["murderous_stacks"]:
                state["menace"] = 0
                sim.hit("Murderous Burst", mb_f, mb_c, tags=("proc",))
                sim.buff("murderous_burst", 3.0, {"crit_dmg": mb_cd})

    # ----------------------------------------------------------------- actives
    # Keen Strike (filler: 4 targets, restores MP, Reckless Strike chain)
    ke_f, ke_c = dmg("KEEN")

    def keen_cast(sim, a):
        mods = {"multihit": 0.5} if has("KEEN", 3) else None
        sim.hit("Keen Strike", ke_f, ke_c, mods=mods)
        sim.gain_mp(100 * (1.2 if has("KEEN", 1) else 1.0))
        if has("KEEN", 4):
            sim.reduce_cd("ruinous_blow", 1.0)
        if has("KEEN", 5):                      # Reckless Strike chain
            k = ASSUME["chain_frac"]
            sim.hit("Reckless Strike", ke_f * k, ke_c * k, delay=TIMING["chain_followup"])
    A["keen_strike"] = Action("keen_strike", "Keen Strike", SID["KEEN"], TIMING["keen_strike"],
                              on_cast=keen_cast, is_filler=True)

    # Rending Blow (filler: Stagger-gauge builder, strong single-target coef)
    re_f, re_c = dmg("REND")

    def rend_cast(sim, a):
        sim.hit("Rending Blow", re_f, re_c, mult=1.12 if has("REND", 4) else 1.0)
    A["rending_blow"] = Action("rending_blow", "Rending Blow", SID["REND"], TIMING["rending_blow"],
                               mp=cd.mp(SID["REND"], lv("REND")), on_cast=rend_cast, is_filler=True)

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

    # Overhead Slam (only while the target is knocked down; Upward Strike chain)
    ov_f, ov_c = dmg("OVER")
    ov_cd = 0.0 if has("OVER", 5) else cd.cd(SID["OVER"], lv("OVER"))

    def over_cast(sim, a):
        tags = ("crit",) if has("OVER", 4) else ()
        sim.hit("Overhead Slam", ov_f, ov_c, tags=tags)
        if has("OVER", 3):
            k = ASSUME["chain_frac"]
            sim.hit("Upward Strike", ov_f * k, ov_c * k, delay=TIMING["chain_followup"])
    A["overhead_slam"] = Action("overhead_slam", "Overhead Slam", SID["OVER"], TIMING["overhead_slam"],
                                cooldown=ov_cd, requires=("knockdown",), on_cast=over_cast)

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
                               requires=("knockdown",), on_cast=aerial_cast)

    # Ruinous Blow (biggest hit; grants Prepare for Battle for 20s)
    rb_f, rb_c = dmg("RUIN")
    rb_speed = 0.20 if has("RUIN", 1) else 0.0

    def ruin_cast(sim, a):
        tags = ("multi", "noparry") if has("RUIN", 5) else ()
        extra = 1.0 + ASSUME["extra_damage_frac"] if has("RUIN", 4) else 1.0
        crit = ("crit",) if has("RUIN", 3) else ()      # +30% Skill Critical -> treat as guaranteed-ish
        sim.hit("Ruinous Blow", rb_f, rb_c, mult=extra, tags=tags + crit)
        sim.buff("prepare_for_battle", 20.0, _prepare_stats(cd, lv("RUIN")))
    A["ruinous_blow"] = Action("ruinous_blow", "Ruinous Blow", SID["RUIN"], TIMING["ruinous_blow"],
                               cooldown=cd.cd(SID["RUIN"], lv("RUIN")), mp=cd.mp(SID["RUIN"], lv("RUIN")),
                               skill_speed=rb_speed, on_cast=ruin_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, stig, st, notes)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes)
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
    order = ["zikel", "lunge", "ruinous_blow", "rage", "lifesteal", "assault", "forcedrest",
             "wrathwave", "fracrush", "bladetoss", "mocking_blade", "overhead_slam", "aerial_snare",
             "rush_strike", "ankle_slice", "leaping_slam", "crushing_wave", "rending_blow"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
