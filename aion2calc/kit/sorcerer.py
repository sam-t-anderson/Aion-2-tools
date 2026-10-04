"""Sorcerer kit built from the global client's skill tables.

Every number that comes from the game data is read from
``data/global/classes/sorcerer.json`` at the build's effective skill level.
Numbers that the client does not expose (animation lengths, the size of a few
"extra damage" effects) are collected in :data:`TIMING` and :data:`ASSUME` so
they are easy to audit and to override.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..sim.engine import Action
from .base import Build, ClassData, spec_slots

SID = dict(
    FA=15210000, IC=15090000, FS=15040000, BW=15280000, BLAZE=15050000, SCAT=15010000,
    FROST=15150000, SHACK=15110000, FB=15220000, WISH=15310000, HF=15060000, DEF=15240000,
    FIRE_MARK=15710000, ROBE_EARTH=15720000, COLD_SNAP=15730000, ROBE_FLAME=15740000,
    ABSORB=15760000, GRACE_RES=15770000, ROBE_COLD=15750000, GRACE_ENH=15780000,
    REVIT=15790000, VITAL=15800000,
    SOUL_FREEZE=15130000, GLACIAL=15120000, DIVINE=15360000, ASSAULT=15700000,
    STEEL=15160000, COLD_STORM=15200000, EE=15400000, HIBERNATION=15410000,
    FIRE_WALL=15390000, LUMIEL=15300000, CURSE=15140000, ARCTIC=15230000, DELAYED=15320000,
)

#: Action time of each skill in seconds at 0% Combat Speed (not in the client
#: data; estimated from KR dummy logs and community notes — see docs).
TIMING = {
    "flame_arrow": 0.80, "ice_chain": 0.95, "firestorm": 1.25, "bittercold_wind": 1.00,
    "blaze": 0.75, "flame_scattershot": 1.00, "frost": 1.00, "frost_burst": 0.85,
    "winters_shackles": 1.00, "wish": 0.60, "hellfire_charge": 0.50, "hellfire_release": 0.60,
    "element_enhancement": 0.60, "fire_wall": 1.00, "cold_storm": 1.00,
    "delayed_explosion": 0.90, "glacial_smite": 1.00, "divine_burst": 1.00,
    "assault_bombardment": 1.00, "soul_freeze": 1.00, "lumiels_space": 1.00,
    "chain_followup": 0.60,
}

#: Effect sizes the tooltips leave out (assumptions; tune with real logs).
ASSUME = {
    "fa_chain_mult": (1.00, 1.12, 1.33),   # Flame Arrow -> Burst -> Pyroclasm (A2DIL share ratio)
    "blaze_delayed_frac": 0.30,            # Blaze "Delayed Damage after 3s" vs main hit
    "hellfire_dot_frac": 0.25,             # Hellfire "Fire DoT 10s" total vs the hit
    "chain_followup_frac": 0.60,           # Winter's Illusion / The Depths follow-up hit
    "enhanced_proc_icd": 1.0,              # Enhanced Embers / Frostbite internal cooldown
    "bw_ticks": 7, "fire_wall_hits": 5, "firestorm_balls": 5, "scattershot_hits": 4,
    "slow_cold_storm": 3.0,
}


@dataclass
class Kit:
    actions: dict
    hooks: list
    cond_mods: list
    static: dict
    policy: list
    filler: str
    notes: list = field(default_factory=list)
    levels: dict = field(default_factory=dict)


def _ms(v) -> float:
    return v["ms"] / 1000.0 if isinstance(v, dict) and "ms" in v else float(v)


def build_kit(build: Build, cd: ClassData, filler: str = "flame_arrow") -> Kit:
    L = build.effective_levels(cd)
    specs = {sid: set(v) for sid, v in build.specs.items()}

    def lv(key):
        return L.get(SID[key], 0)

    def has(key, idx):
        sid = SID[key]
        return (sid + 10 * idx) in specs.get(sid, set()) and \
            next(s for s in cd.skills[sid]["specs"] if s["id"] == sid + 10 * idx)["unlock"] <= L.get(sid, 1)

    def st(key, threshold):        # stigma specializations switch on with stigma level
        return SID[key] in build.stigmas and build.stigmas[SID[key]] >= threshold

    def dmg(key, idx=0):
        v = cd.vals(SID[key], max(1, lv(key)))
        f, c = v[idx]
        return float(f), float(c) / 100.0

    A: dict[str, Action] = {}
    notes: list[str] = []

    # --------------------------------------------------------------- passives
    static: dict[str, float] = {}
    rof = cd.vals(SID["ROBE_FLAME"], lv("ROBE_FLAME"))       # acc, pve%, pvp%, double%
    static["accuracy"] = static.get("accuracy", 0) + rof[0]
    static["amp_pve"] = static.get("amp_pve", 0) + rof[1] / 100
    static["double"] = static.get("double", 0) + rof[3] / 100
    roe = cd.vals(SID["ROBE_EARTH"], lv("ROBE_EARTH"))       # mp%, regen, crit (MP>=50%)
    static["mp_max_pct"] = roe[0] / 100
    static["mp_regen"] = roe[1] / 3.0
    gre = cd.vals(SID["GRACE_ENH"], lv("GRACE_ENH"))         # pve%, pvp%, chance, dmg, dmg, icd
    fm = cd.vals(SID["FIRE_MARK"], lv("FIRE_MARK"))          # dur, chance, dmg, dmg, icd
    cs = cd.vals(SID["COLD_SNAP"], lv("COLD_SNAP"))          # chance, dmg, dmg, icd
    ab = cd.vals(SID["ABSORB"], lv("ABSORB"))                # ailment%, [mp,0], icd
    ve = cd.vals(SID["VITAL"], lv("VITAL"))                  # dmg, dmg, hp%, icd

    ee_on = SID["EE"] in build.stigmas

    def cond(sim, t):
        out = {}
        frac = sim.mp / max(1.0, sim.base.mp_max)
        ee = ee_on and sim.has_buff("element_enhancement", t)
        if frac >= 0.25 - 1e-9:
            amp = gre[0] / 100
            if ee and st("EE", 15):
                amp *= 1.5
            out["amp"] = amp
        if frac >= 0.50 - 1e-9:
            out["crit"] = roe[2]
        if ee and st("EE", 10):          # x1.5 Robe of Flame while Element Enhancement is up
            out["amp"] = out.get("amp", 0) + 0.5 * rof[1] / 100
            out["double"] = 0.5 * rof[3] / 100
        return out

    fire_wall_tick = [0.0, 0.0]
    cold_storm_tick = [0.0, 0.0]

    def hook(sim, t, info):
        tags = info["tags"]
        if "proc" in tags:
            return
        el = info["element"]
        direct = "dot" not in tags
        if el == "fire":
            if sim.has_debuff("fire_mark", t) and sim.proc("fire_mark", fm[1] / 100, _ms(fm[4]), t):
                f, c = fm[2]
                sim.hit("Fire Mark", f, c / 100, element="fire", tags=("proc",))
            if direct:
                sim.debuff("fire_mark", _ms(fm[0]), t=t)
        if not direct:
            return
        if sim.has_debuff("slow", t) and sim.proc("cold_snap", cs[0] / 100, _ms(cs[3]), t):
            f, c = cs[1]
            sim.hit("Cold Snap", f, c / 100, element="water", tags=("proc",))
        if sim.proc("grace_enh", gre[2] / 100, _ms(gre[5]), t):
            f, c = gre[3]
            sim.hit("Grace of Enhancement", f, c / 100, tags=("proc",))
        if sim.target.hp_pct(t, sim.cfg.duration) * 100 > ve[2] and sim.proc("vital", 1.0, _ms(ve[3]), t):
            f, c = ve[0]
            sim.hit("Vitality Evaporation", f, c / 100, tags=("proc",))
        if sim.proc("absorb", 1.0, _ms(ab[2]), t):
            sim.gain_mp(ab[1][0])
        if st("FIRE_WALL", 5) and sim.has_debuff("embers", t) and \
                sim.proc("enh_embers", 1.0, ASSUME["enhanced_proc_icd"], t):
            sim.hit("Fire Wall", fire_wall_tick[0], fire_wall_tick[1], element="fire", tags=("proc",))
        if st("COLD_STORM", 5) and sim.has_debuff("frostbite", t) and \
                sim.proc("enh_frostbite", 1.0, ASSUME["enhanced_proc_icd"], t):
            sim.hit("Cold Storm", cold_storm_tick[0], cold_storm_tick[1], element="water", tags=("proc",))

    # ------------------------------------------------------------ actives
    # Flame Arrow (3-step basic chain: Flame Arrow -> Burst -> Pyroclasm)
    fa_f, fa_c = dmg("FA")

    def fa_cast(sim, a):
        step, last = sim.chain.get("fa", (0, -99.0))
        if sim.t - last > sim.cfg.chain_window:
            step = 0
        step = step % 3 + 1
        sim.chain["fa"] = (step, sim.t)
        m = ASSUME["fa_chain_mult"][step - 1]
        mods = {"multihit": 0.5} if has("FA", 3) else None
        name = ("Flame Arrow", "Flame Arrow (Burst)", "Flame Arrow (Pyroclasm)")[step - 1]
        sim.hit(name, fa_f, fa_c, element="fire", mult=m, mods=mods)
        sim.gain_mp(100 * (1.2 if has("FA", 1) else 1.0))
        if step == 3:
            if has("FA", 4):
                sim.buff("pyroclasm", 10.0, {"amp_fire": 0.05})
            if has("FA", 5):
                sim.reset_cd("blaze")
    A["flame_arrow"] = Action("flame_arrow", "Flame Arrow", SID["FA"], TIMING["flame_arrow"],
                              on_cast=fa_cast, element="fire", is_filler=True)

    # Ice Chain (cooldown-free heavy attack, costs MP)
    ic_f, ic_c = dmg("IC")

    def ic_cast(sim, a):
        sim.hit("Ice Chain", ic_f, ic_c, element="water", mult=1.12 if has("IC", 3) else 1.0)
        sim.debuff("slow", 5.0)
        if has("IC", 4):
            sim.reduce_cd("winters_shackles", 1.0)
        if has("IC", 5) and sim.proc("ic_frost", 0.05, 0.0, sim.t):
            sim.debuff("frost", 2.0)
    A["ice_chain"] = Action("ice_chain", "Ice Chain", SID["IC"], TIMING["ice_chain"],
                            mp=cd.mp(SID["IC"], lv("IC")) * (0.8 if has("IC", 1) else 1.0),
                            skill_speed=0.2 if has("IC", 2) else 0.0, on_cast=ic_cast,
                            element="water", is_filler=True)

    # Firestorm (5 fireballs)
    fs_f, fs_c = dmg("FS")
    balls = ASSUME["firestorm_balls"]
    fs_mults = [1 + 0.15 * i for i in range(balls)] if has("FS", 5) else None

    def fs_each(sim, t, i):
        if has("FS", 4):
            sim.reduce_cd("hellfire", 2.0)

    def fs_cast(sim, a):
        sim.hit("Firestorm", fs_f, fs_c, element="fire", n=balls, spread=0.8, mults=fs_mults,
                on_each=fs_each)
    A["firestorm"] = Action("firestorm", "Firestorm", SID["FS"], TIMING["firestorm"],
                            cooldown=cd.cd(SID["FS"], lv("FS")),
                            mp=cd.mp(SID["FS"], lv("FS")) * (0.5 if has("FS", 1) else 1.0),
                            skill_speed=0.2 if has("FS", 2) else 0.0, on_cast=fs_cast, element="fire")

    # Bittercold Wind (ground effect, 7 ticks over 2 s)
    bw_f, bw_c = dmg("BW")
    bw_ticks = ASSUME["bw_ticks"]
    bw_scale, bw_n, bw_dur = (1.5, int(round(bw_ticks * 1.5)), 3.0) if has("BW", 1) else (1.0, bw_ticks, 2.0)

    def bw_each(sim, t, i):
        if has("BW", 5):
            sim.reduce_cd("frost", 1.0)

    def bw_cast(sim, a):
        sim.hit("Bittercold Wind", bw_f * bw_scale, bw_c * bw_scale, element="water", n=bw_n,
                spread=bw_dur, tags=("crit",) if has("BW", 4) else (), on_each=bw_each)
    A["bittercold_wind"] = Action("bittercold_wind", "Bittercold Wind", SID["BW"],
                                  TIMING["bittercold_wind"], cooldown=cd.cd(SID["BW"], lv("BW")),
                                  mp=cd.mp(SID["BW"], lv("BW")), on_cast=bw_cast, element="water")

    # Blaze (needs Fire Mark)
    bl_f, bl_c = dmg("BLAZE")

    def bl_cast(sim, a):
        tags = ("multi",) if has("BLAZE", 4) else ()
        sim.hit("Blaze", bl_f, bl_c, element="fire", tags=tags)
        if has("BLAZE", 3):
            k = ASSUME["blaze_delayed_frac"]
            sim.hit("Blaze (delayed)", bl_f * k, bl_c * k, element="fire", delay=3.0)
        sim.gain_mp(100 * (1.5 if has("BLAZE", 2) else 1.0))
        if has("BLAZE", 5):
            sim.reduce_cd("wish", 3.0)
    A["blaze"] = Action("blaze", "Blaze", SID["BLAZE"], TIMING["blaze"],
                        cooldown=cd.cd(SID["BLAZE"], lv("BLAZE")), requires=("fire_mark",),
                        on_cast=bl_cast, element="fire")

    # Flame Scattershot (only on Staggered targets)
    sc_f, sc_c = dmg("SCAT")

    def sc_each(sim, t, i):
        if has("SCAT", 5):
            sim.reduce_cd("all", 1.0)

    def sc_cast(sim, a):
        sim.hit("Flame Scattershot", sc_f, sc_c, element="fire", n=ASSUME["scattershot_hits"],
                spread=0.6, tags=("multi",) if has("SCAT", 4) else (), on_each=sc_each)
        if has("SCAT", 2):
            sim.gain_mp(120)
    A["flame_scattershot"] = Action("flame_scattershot", "Flame Scattershot", SID["SCAT"],
                                    TIMING["flame_scattershot"], requires=("stagger",),
                                    on_cast=sc_cast, element="fire")

    # Frost -> Frost Burst
    fr_f, fr_c = dmg("FROST")

    def fr_cast(sim, a):
        sim.hit("Frost", fr_f, fr_c, element="water")
        sim.debuff("frost", 3.0 + (1.0 if has("FROST", 5) else 0.0))
        if has("FROST", 1):
            sim.gain_mp(200)
        if has("FROST", 3):
            sim.reset_cd("frost_burst")
    A["frost"] = Action("frost", "Frost", SID["FROST"], TIMING["frost"],
                        cooldown=cd.cd(SID["FROST"], lv("FROST")) - (5 if has("FROST", 2) else 0),
                        mp=cd.mp(SID["FROST"], lv("FROST")), on_cast=fr_cast, element="water")

    fb_f, fb_c = dmg("FB")

    def fb_cast(sim, a):
        sim.hit("Frost Burst", fb_f, fb_c, element="water", tags=("crit",) if has("FB", 4) else ())
        if has("FB", 5) and sim.proc("fb_reset", 0.5, 0.0, sim.t):
            sim.reset_cd("frost_burst")
    A["frost_burst"] = Action("frost_burst", "Frost Burst", SID["FB"], TIMING["frost_burst"],
                              cooldown=cd.cd(SID["FB"], lv("FB")), requires=("frost",),
                              on_cast=fb_cast, element="water")

    # Winter's Shackles
    ws_f, ws_c = dmg("SHACK")
    ws_cast_t = TIMING["winters_shackles"] + (TIMING["chain_followup"] if has("SHACK", 4) else 0)

    def ws_cast(sim, a):
        sim.hit("Winter's Shackles", ws_f, ws_c, element="water")
        if has("SHACK", 4):
            k = ASSUME["chain_followup_frac"]
            sim.hit("Winter's Illusion", ws_f * k, ws_c * k, element="water", delay=0.6)
        sim.debuff("slow", 3.0)
        if has("SHACK", 2) and sim.proc("ws_frost", 0.3, 0.0, sim.t):
            sim.debuff("frost", 3.0)
        if has("SHACK", 3):
            sim.buff("shackles", 5.0, {"amp": 0.20})
    A["winters_shackles"] = Action("winters_shackles", "Winter's Shackles", SID["SHACK"], ws_cast_t,
                                   cooldown=cd.cd(SID["SHACK"], lv("SHACK")) - (15 if has("SHACK", 5) else 0),
                                   mp=cd.mp(SID["SHACK"], lv("SHACK")), on_cast=ws_cast, element="water")

    # Wish of Concentration
    wv = cd.vals(SID["WISH"], lv("WISH"))     # attack%, accuracy, duration

    def wish_cast(sim, a):
        stats = {"attack_pct": (wv[0] + (10 if has("WISH", 2) else 0)) / 100}
        if has("WISH", 4):
            stats["combat_speed"] = 0.10
        sim.buff("wish", _ms(wv[2]), stats)
        if has("WISH", 5):
            for g in list(sim.ready):
                if g != "wish":
                    sim.ready[g] = max(sim.t, sim.ready[g] - 10.0)
    A["wish"] = Action("wish", "Wish of Concentration", SID["WISH"], TIMING["wish"],
                       cooldown=cd.cd(SID["WISH"], lv("WISH")),
                       mp=cd.mp(SID["WISH"], lv("WISH")) * (0.9 if has("WISH", 1) else 1.0),
                       on_cast=wish_cast)

    # Hellfire (charge 1..3)
    hv = cd.vals(SID["HF"], max(1, lv("HF")))
    (f1, c1), (f3, c3) = hv[0], hv[1]
    for k in (1, 2, 3):
        fk = f1 + (f3 - f1) * (k - 1) / 2
        ck = (c1 + (c3 - c1) * (k - 1) / 2) / 100

        def hf_cast(sim, a, fk=fk, ck=ck, k=k):
            tags = ("multi", "noparry") if has("HF", 4) else ()
            sim.hit("Hellfire", fk, ck, element="fire", tags=tags, n=2 if k == 3 else 1)
            if has("HF", 2):
                frac = ASSUME["hellfire_dot_frac"]
                sim.dot("hellfire_dot", "Hellfire (DoT)", fk * frac / 10, ck * frac / 10, 1.0, 10.0,
                        element="fire")
        A[f"hellfire_c{k}"] = Action(
            f"hellfire_c{k}", f"Hellfire (charge {k})", SID["HF"],
            TIMING["hellfire_charge"] * k + TIMING["hellfire_release"],
            cooldown=cd.cd(SID["HF"], lv("HF")) - (15 if has("HF", 5) else 0), cd_group="hellfire",
            mp=cd.mp(SID["HF"], lv("HF")), skill_speed=0.3 if has("HF", 1) else 0.0,
            on_cast=hf_cast, element="fire")

    # ------------------------------------------------------------- stigmas
    def stig(key):
        return SID[key] in build.stigmas

    def sdmg(key, idx=0):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[idx]
        return float(f), float(c) / 100.0

    if stig("EE"):
        ev = cd.vals(SID["EE"], build.stigmas[SID["EE"]])

        def ee_cast(sim, a, ev=ev):
            bonus = 0.10 if st("EE", 20) else 0.0
            sim.buff("element_enhancement", _ms(ev[2]),
                     {"fire_amp": ev[0] / 100 + bonus, "water_amp": ev[1] / 100 + bonus})
        A["element_enhancement"] = Action("element_enhancement", "Element Enhancement", SID["EE"],
                                          TIMING["element_enhancement"],
                                          cooldown=cd.cd(SID["EE"], build.stigmas[SID["EE"]]),
                                          on_cast=ee_cast)
    if stig("FIRE_WALL"):
        fv = cd.vals(SID["FIRE_WALL"], build.stigmas[SID["FIRE_WALL"]])
        wall_f, wall_c = fv[0][0], fv[0][1] / 100
        tick_f, tick_c = fv[3][0], fv[3][1] / 100
        fire_wall_tick[:] = [tick_f, tick_c]
        wall_dur = 3.0 + (2.0 if st("FIRE_WALL", 15) else 0.0)
        embers = _ms(fv[2]) + (10.0 if st("FIRE_WALL", 20) else 0.0)
        hits = int(round(ASSUME["fire_wall_hits"] * wall_dur / 3.0))

        def fw_cast(sim, a):
            sim.hit("Fire Wall", wall_f * wall_dur / 3.0, wall_c * wall_dur / 3.0, element="fire",
                    n=hits, spread=wall_dur)
            sim.dot("embers", "Fire Wall (Embers)", tick_f, tick_c, _ms(fv[5]), wall_dur + embers,
                    element="fire")
        A["fire_wall"] = Action("fire_wall", "Fire Wall", SID["FIRE_WALL"], TIMING["fire_wall"],
                                cooldown=cd.cd(SID["FIRE_WALL"], build.stigmas[SID["FIRE_WALL"]]),
                                mp=cd.mp(SID["FIRE_WALL"], build.stigmas[SID["FIRE_WALL"]]),
                                on_cast=fw_cast, element="fire")
    if stig("COLD_STORM"):
        cv = cd.vals(SID["COLD_STORM"], build.stigmas[SID["COLD_STORM"]])
        cold_storm_tick[:] = [cv[2][0], cv[2][1] / 100]
        summon = 7.0 + (3.0 if st("COLD_STORM", 15) else 0.0)
        bite = _ms(cv[5]) + (10.0 if st("COLD_STORM", 20) else 0.0)

        def cst_cast(sim, a):
            f, c = cv[0]
            sim.hit("Cold Storm", f, c / 100, element="water")
            sim.debuff("slow", ASSUME["slow_cold_storm"])
            sim.dot("frostbite", "Cold Storm (Frostbite)", cv[2][0], cv[2][1] / 100, _ms(cv[4]),
                    summon + bite, element="water")
        A["cold_storm"] = Action("cold_storm", "Cold Storm", SID["COLD_STORM"], TIMING["cold_storm"],
                                 cooldown=cd.cd(SID["COLD_STORM"], build.stigmas[SID["COLD_STORM"]]),
                                 mp=cd.mp(SID["COLD_STORM"], build.stigmas[SID["COLD_STORM"]]),
                                 on_cast=cst_cast, element="water")
    if stig("DELAYED"):
        dv = cd.vals(SID["DELAYED"], build.stigmas[SID["DELAYED"]])
        de_f, de_c = dv[0][0], dv[0][1] / 100
        de_delay = _ms(dv[2])
        vuln = 0.15 + (0.10 if st("DELAYED", 20) else 0.0)

        def de_cast(sim, a):
            sim.debuff("delayed_explosion", de_delay, {"vuln": vuln})
            sim.hit("Delayed Explosion", de_f, de_c, element="fire", delay=de_delay - 1e-3)
            if st("DELAYED", 5):
                sim.gain_mp(200)
        A["delayed_explosion"] = Action("delayed_explosion", "Delayed Explosion", SID["DELAYED"],
                                        TIMING["delayed_explosion"],
                                        cooldown=cd.cd(SID["DELAYED"], build.stigmas[SID["DELAYED"]])
                                        - (10 if st("DELAYED", 10) else 0),
                                        mp=cd.mp(SID["DELAYED"], build.stigmas[SID["DELAYED"]]),
                                        on_cast=de_cast, element="fire")
    for key, akey, elem in [("GLACIAL", "glacial_smite", "water"), ("DIVINE", "divine_burst", "fire"),
                            ("ASSAULT", "assault_bombardment", None), ("SOUL_FREEZE", "soul_freeze", "water"),
                            ("LUMIEL", "lumiels_space", None)]:
        if not stig(key):
            continue
        f, c = sdmg(key)
        cdv = cd.cd(SID[key], build.stigmas[SID[key]])
        mult, sspeed, extra_t = 1.0, 0.0, 0.0
        if key == "GLACIAL":
            mult = 1.05 if st(key, 5) else 1.0
            cdv -= 30 if st(key, 10) else 0
        if key == "DIVINE" and st(key, 5):
            sspeed = 0.2
        if key == "LUMIEL":
            mult = 1.05 if st(key, 5) else 1.0
            cdv -= 30 if st(key, 20) else 0
            extra_t = TIMING["chain_followup"] if st(key, 10) else 0.0

        def nuke(sim, a, f=f, c=c, key=key, elem=elem, mult=mult):
            tags = ("multi",) if key == "GLACIAL" and st(key, 20) else ()
            sim.hit(a.name, f, c, element=elem, mult=mult, tags=tags)
            if key == "LUMIEL" and st(key, 10):
                k = ASSUME["chain_followup_frac"]
                sim.hit("The Depths", f * k, c * k, element=elem, delay=0.6)
            if key == "ASSAULT":
                sim.debuff("frost", 3.0)
                if st(key, 5):
                    sim.buff("assault", 5.0, {"attack_pct": 0.20})
            if key == "GLACIAL" and st(key, 15) and sim.proc("gs_frost", 0.5, 0.0, sim.t):
                sim.debuff("frost", 3.0)
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING[akey] + extra_t,
                         cooldown=cdv, mp=cd.mp(SID[key], build.stigmas[SID[key]]),
                         skill_speed=sspeed, on_cast=nuke, element=elem)

    policy = default_policy(A, filler)
    return Kit(actions=A, hooks=[hook], cond_mods=[cond], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def default_policy(actions: dict, filler: str) -> list:
    """A sensible starting priority (the optimizer improves on it)."""
    order = ["element_enhancement", "wish", "delayed_explosion", "fire_wall", "cold_storm",
             "hellfire_c1", "winters_shackles", "blaze", "firestorm", "bittercold_wind",
             "frost_burst", "frost", "glacial_smite", "divine_burst", "assault_bombardment",
             "lumiels_space", "soul_freeze", "flame_scattershot"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol


def spec_options(cd: ClassData, build: Build) -> dict[int, list[tuple]]:
    """All legal spec combinations per active skill at the build's levels."""
    from itertools import combinations
    L = build.effective_levels(cd)
    out = {}
    for sid, s in cd.skills.items():
        if s["kind"] != "active" or not s.get("specs"):
            continue
        lvl = L.get(sid, 1)
        avail = [x["id"] for x in s["specs"] if x["unlock"] <= lvl]
        k = min(spec_slots(lvl), len(avail))
        combos = [tuple(c) for c in combinations(avail, k)] if k > 0 else [()]
        out[sid] = combos
    return out
