"""Ranger kit built from the global client's skill tables.

What the generic tooltip model misses for a Ranger, and this kit adds:

* **Precision.**  Marking Shot grants Precision (+Critical Hit for 10s) and
  Deadshot hits 35% harder while it is up — the Ranger keeps Precision rolling.
* **Gale.**  Gale Arrow grants +Combat Speed and +PvE Damage Boost (its
  cooldown roughly equal to its duration, so near-permanent).
* **Charged Deadshot** at full charge, and **Burst Arrow** gated behind the
  Slow that Snare Shot applies.
* **Bleed** (Drill Dart) damage-over-time and the on-hit / on-crit proc passives
  Concentrated Fire, Rooting Eye, Melee Fire and Hunter's Soul, which a Ranger
  keeps feeding by holding a damage-over-time and a Slow on the target.

Every damage number comes from ``data/global/classes/ranger.json``; only the
things the client does not expose live in :data:`TIMING` / :data:`ASSUME`.
"""
from __future__ import annotations

from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, fallback_to_generic, ms, spec_options  # noqa: F401

SID = dict(
    SNIPE=14020000, TEMPEST=14340000, SNARE=14130000, MARK=14090000, DRILL=14050000,
    SCATTER=14330000, GALE=14110000, TRAP=14170000, BURST=14080000, SUPPRESS=14070000,
    DEADSHOT=14010000, DEFI=14260000,
    VIGIL=14710000, CONCFIRE=14720000, WINDVIG=14730000, FOCUSEYE=14740000, HRESOLVE=14750000,
    UNYIELD=14760000, ROOTEYE=14770000, MELEEFIRE=14780000, REVITAL=14790000, HSOUL=14800000,
    EXPLOSIVE=14360000, ILLUSORY=14150000, ASTORM=14270000, VAIZEL=14310000, STEALTH=14190000,
    ASMITE=14700000, SUPPFIRE=14380000, BOWBLESS=14220000, SEALING=14160000, AKICK=14120000,
)

TIMING = {
    "snipe": 0.80, "tempest_shot": 0.80, "snare_shot": 0.90, "marking_shot": 0.80,
    "drill_dart": 0.75, "gale_arrow": 0.90, "explosion_trap": 0.90, "burst_arrow": 0.90,
    "suppressing_arrow": 0.85, "deadshot": 1.10, "chain_followup": 0.50, "stigma": 0.95,
}

ASSUME = {
    "precision_uptime": True,     # Marking Shot keeps Precision up for Deadshot's +35%
    "deadshot_charge": 3,         # assume full charge
    "crit_rate": 0.60,            # for on-crit proc passives (expected-value gate)
    "chain_frac": 0.60,
}


def build_kit(build: Build, cd: ClassData, filler: str = "snipe") -> Kit:
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
    static: dict[str, float] = {}

    def add_static(key, mapping):
        if lv(key) <= 0:
            return
        v = cd.vals(SID[key], lv(key))
        for idx, (field, scale) in mapping.items():
            if idx < len(v) and isinstance(v[idx], (int, float)):
                static[field] = static.get(field, 0.0) + v[idx] * scale

    add_static("FOCUSEYE", {0: ("accuracy", 1.0), 1: ("amp_pve", 0.01), 3: ("double", 0.01)})
    add_static("HRESOLVE", {0: ("crit_dmg", 0.01)})

    # proc passives (hooks): on-hit, on-DoT-target, on-slow-target, on-crit ------
    def proc_def(key, chance_idx, dmg_idx, icd_idx):
        if lv(key) <= 0:
            return None
        v = cd.vals(SID[key], lv(key))
        return (float(v[chance_idx]) / 100.0, float(v[dmg_idx][0]), float(v[dmg_idx][1]) / 100.0, ms(v[icd_idx]))
    conc = proc_def("CONCFIRE", 0, 1, 3)       # vs a target taking DoT
    root = proc_def("ROOTEYE", 0, 1, 3)        # vs a Slowed/Rooted target
    melee = proc_def("MELEEFIRE", 0, 1, 4)     # on any hit
    hsoul = proc_def("HSOUL", 0, 1, 3)         # on a Critical Hit

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        if melee and sim.proc("melee_fire", melee[0], melee[3], t):
            sim.hit("Melee Fire", melee[1], melee[2], tags=("proc",))
        if conc and sim.has_debuff("bleed", t) and sim.proc("concentrated_fire", conc[0], conc[3], t):
            sim.hit("Concentrated Fire", conc[1], conc[2], tags=("proc",))
        if root and sim.has_debuff("slow", t) and sim.proc("rooting_eye", root[0], root[3], t):
            sim.hit("Rooting Eye", root[1], root[2], tags=("proc",))
        if hsoul and sim.proc("hunters_soul", hsoul[0] * ASSUME["crit_rate"], hsoul[3], t):
            sim.hit("Hunter's Soul", hsoul[1], hsoul[2], tags=("proc",))

    # ----------------------------------------------------------------- actives
    sn_f, sn_c = dmg("SNIPE")

    def snipe_cast(sim, a):
        mods = {"multihit": 0.5} if has("SNIPE", 3) else None
        sim.hit("Snipe", sn_f, sn_c, mods=mods)
        sim.gain_mp(120 * (1.2 if has("SNIPE", 1) else 1.0))
        if has("SNIPE", 4):
            sim.reduce_cd("deadshot", 1.0)
        if has("SNIPE", 5):
            k = ASSUME["chain_frac"]
            sim.hit("Tempest Arrow", sn_f * k, sn_c * k, delay=TIMING["chain_followup"])
    A["snipe"] = Action("snipe", "Snipe", SID["SNIPE"], TIMING["snipe"], on_cast=snipe_cast, is_filler=True)

    te_f, te_c = dmg("TEMPEST")

    def tempest_cast(sim, a):
        sim.hit("Tempest Shot", te_f, te_c, mult=1.12 if has("TEMPEST", 3) else 1.0)
    A["tempest_shot"] = Action("tempest_shot", "Tempest Shot", SID["TEMPEST"], TIMING["tempest_shot"],
                               skill_speed=0.2 if has("TEMPEST", 5) else 0.0, on_cast=tempest_cast, is_filler=True)

    # Marking Shot (grants Precision: +Critical Hit)
    mk_f, mk_c = dmg("MARK")
    mkv = cd.vals(SID["MARK"], max(1, lv("MARK")))
    prec_crit = float(mkv[3]) if len(mkv) > 3 and isinstance(mkv[3], (int, float)) else 300.0
    prec_dur = (ms(mkv[2]) if isinstance(mkv[2], dict) else 10.0) + (5.0 if has("MARK", 3) else 0.0)

    def mark_cast(sim, a):
        tags = ("crit", "noparry") if has("MARK", 5) else ()
        sim.hit("Marking Shot", mk_f, mk_c, tags=tags)
        stats = {"crit": prec_crit}
        if has("MARK", 1):
            stats["perfect"] = 0.05
        sim.buff("precision", prec_dur, stats)
    A["marking_shot"] = Action("marking_shot", "Marking Shot", SID["MARK"], TIMING["marking_shot"],
                               cooldown=cd.cd(SID["MARK"], lv("MARK")), mp=cd.mp(SID["MARK"], lv("MARK")),
                               on_cast=mark_cast)

    # Gale Arrow (grants Gale: +Combat Speed, +PvE Damage Boost)
    ga_f, ga_c = dmg("GALE")
    gav = cd.vals(SID["GALE"], max(1, lv("GALE")))
    gale_spd = float(gav[3]) / 100.0 if len(gav) > 3 and isinstance(gav[3], (int, float)) else 0.07
    gale_amp = float(gav[4]) / 100.0 if len(gav) > 4 and isinstance(gav[4], (int, float)) else 0.07
    gale_dur = (ms(gav[2]) if isinstance(gav[2], dict) else 10.0) + (5.0 if has("GALE", 1) else 0.0)
    gale_cd = cd.cd(SID["GALE"], lv("GALE")) - (10 if has("GALE", 5) else 0)

    def gale_cast(sim, a):
        sim.hit("Gale Arrow", ga_f, ga_c)
        sim.buff("gale", gale_dur, {"combat_speed": gale_spd, "amp": gale_amp})
    A["gale_arrow"] = Action("gale_arrow", "Gale Arrow", SID["GALE"], TIMING["gale_arrow"],
                             cooldown=gale_cd, mp=cd.mp(SID["GALE"], lv("GALE")), on_cast=gale_cast)

    # Drill Dart (Bleed DoT)
    dr_f, dr_c = dmg("DRILL")
    drv = cd.vals(SID["DRILL"], max(1, lv("DRILL")))
    bleed_dur = (ms(drv[4]) if len(drv) > 4 and isinstance(drv[4], dict) else 6.0) + (2.0 if has("DRILL", 2) else 0.0)
    bl_f = float(drv[2][0]) / max(1.0, bleed_dur)      # client value is the total; spread per tick
    bl_c = float(drv[2][1]) / 100.0 / max(1.0, bleed_dur)

    def drill_cast(sim, a):
        n = 2 if has("DRILL", 5) else 1
        mods = {"multihit": 0.5} if has("DRILL", 4) else None
        sim.hit("Drill Dart", dr_f, dr_c, n=n, spread=0.2 * (n - 1), mods=mods)
        sim.dot("bleed", "Drill Dart (Bleed)", bl_f, bl_c, 1.0, bleed_dur)
    A["drill_dart"] = Action("drill_dart", "Drill Dart", SID["DRILL"], TIMING["drill_dart"],
                             cooldown=cd.cd(SID["DRILL"], lv("DRILL")),
                             skill_speed=0.2 if has("DRILL", 3) else 0.0, on_cast=drill_cast)

    # Snare Shot (Slow -> gates Burst Arrow)
    sr_f, sr_c = dmg("SNARE")

    def snare_cast(sim, a):
        sim.hit("Snare Shot", sr_f, sr_c)
        sim.debuff("slow", (5.0 if isinstance(cd.vals(SID["SNARE"], lv("SNARE"))[3], dict) else 5.0)
                   + (2.0 if has("SNARE", 5) else 0.0))
    A["snare_shot"] = Action("snare_shot", "Snare Shot", SID["SNARE"], TIMING["snare_shot"],
                             cooldown=cd.cd(SID["SNARE"], lv("SNARE")),
                             skill_speed=0.2 if has("SNARE", 2) else 0.0,
                             mp=cd.mp(SID["SNARE"], lv("SNARE")), on_cast=snare_cast)

    # Burst Arrow (needs a Slowed/Rooted target)
    bu_f, bu_c = dmg("BURST")

    def burst_cast(sim, a):
        mods = {"multihit": 0.5} if has("BURST", 2) else None
        sim.hit("Burst Arrow", bu_f, bu_c, mult=1.12 if has("BURST", 4) else 1.0, mods=mods)
    A["burst_arrow"] = Action("burst_arrow", "Burst Arrow", SID["BURST"], TIMING["burst_arrow"],
                              cooldown=cd.cd(SID["BURST"], lv("BURST")), requires=("slow",), on_cast=burst_cast)

    # Suppressing Arrow
    su_f, su_c = dmg("SUPPRESS")

    def suppress_cast(sim, a):
        mods = {"multihit": 0.5} if has("SUPPRESS", 1) else None
        sim.hit("Suppressing Arrow", su_f, su_c, mods=mods)
    A["suppressing_arrow"] = Action("suppressing_arrow", "Suppressing Arrow", SID["SUPPRESS"],
                                   TIMING["suppressing_arrow"], cooldown=cd.cd(SID["SUPPRESS"], lv("SUPPRESS")),
                                   skill_speed=0.2 if has("SUPPRESS", 3) else 0.0, on_cast=suppress_cast)

    # Explosion Trap
    tr_f, tr_c = dmg("TRAP")
    A["explosion_trap"] = Action("explosion_trap", "Explosion Trap", SID["TRAP"], TIMING["explosion_trap"],
                                 cooldown=cd.cd(SID["TRAP"], lv("TRAP")), mp=cd.mp(SID["TRAP"], lv("TRAP")),
                                 on_cast=lambda sim, a: sim.hit("Explosion Trap", tr_f, tr_c))

    # Deadshot (charge nuke; +35% with Precision)
    dv = cd.vals(SID["DEADSHOT"], max(1, lv("DEADSHOT")))
    ds_idx = 1 if ASSUME["deadshot_charge"] >= 3 else 0
    ds_f, ds_c = float(dv[ds_idx][0]), float(dv[ds_idx][1]) / 100.0

    def deadshot_cast(sim, a):
        mult = 1.35 if sim.has_buff("precision") else 1.0
        tags = ("multi",) if has("DEADSHOT", 4) else ()
        sim.hit("Deadshot", ds_f, ds_c, mult=mult, tags=tags)
    A["deadshot"] = Action("deadshot", "Deadshot", SID["DEADSHOT"], TIMING["deadshot"],
                           cooldown=cd.cd(SID["DEADSHOT"], lv("DEADSHOT")),
                           mp=0.0 if has("DEADSHOT", 1) else cd.mp(SID["DEADSHOT"], lv("DEADSHOT")),
                           skill_speed=0.3 if has("DEADSHOT", 2) else 0.0,
                           on_cast=deadshot_cast, requires_charge=True, charge_level=3)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, stig, st, notes)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes)
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _build_stigmas(A, build, cd, stig, st, notes):
    def sdmg(key):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[0]
        return float(f), float(c) / 100.0

    # Vaizel's Authority: +Attack%; Bow of Blessing: +Critical Hit
    if stig("VAIZEL"):
        vv = cd.vals(SID["VAIZEL"], build.stigmas[SID["VAIZEL"]])
        A["vaizel"] = Action("vaizel", cd.skills[SID["VAIZEL"]]["name"], SID["VAIZEL"], TIMING["stigma"],
                            cooldown=cd.cd(SID["VAIZEL"], build.stigmas[SID["VAIZEL"]]),
                            on_cast=lambda sim, a, s=vv[0] / 100.0: sim.buff("vaizel", 20.0, {"attack_pct": s}))
    if stig("BOWBLESS"):
        bv = cd.vals(SID["BOWBLESS"], build.stigmas[SID["BOWBLESS"]])
        stats = {"crit": float(bv[0])}
        if st("BOWBLESS", 15):
            stats["crit_dmg"] = 0.20
        A["bowbless"] = Action("bowbless", cd.skills[SID["BOWBLESS"]]["name"], SID["BOWBLESS"], TIMING["stigma"],
                              cooldown=cd.cd(SID["BOWBLESS"], build.stigmas[SID["BOWBLESS"]]),
                              on_cast=lambda sim, a, s=stats: sim.buff("bowbless", 20.0, s))

    for key in ("EXPLOSIVE", "ASTORM", "ILLUSORY", "SEALING", "ASMITE"):
        if not stig(key):
            continue
        akey = key.lower()
        f, c = sdmg(key)

        def nuke(sim, a, key=key, f=f, c=c):
            tags = ("crit",) if (key == "EXPLOSIVE" and st("EXPLOSIVE", 15)) else ()
            mult = 1.20 if key == "EXPLOSIVE" else 1.0        # +dmg vs Slow/Root
            sim.hit(a.name, f, c, mult=mult, tags=tags)
            if key == "ASMITE" and st("ASMITE", 5):
                sim.buff("assault_smite", 5.0, {"attack_pct": 0.20})
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]), on_cast=nuke)


def _policy(actions: dict, filler: str) -> list:
    order = ["vaizel", "bowbless", "marking_shot", "gale_arrow", "explosive", "astorm", "illusory",
             "sealing", "asmite", "deadshot", "drill_dart", "snare_shot", "burst_arrow",
             "suppressing_arrow", "explosion_trap", "tempest_shot"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
