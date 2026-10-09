"""Assassin kit built from the global client's skill tables.

The Assassin is a crit-and-position class, and the generic tooltip model sees
none of what makes it work.  This kit encodes:

* **Back-attack positioning.**  The Assassin fights behind the boss, so Rear
  Smite's Back Attack Boost, Ambush's +30% and Triniel's Dagger's +30% apply
  (tunable via :data:`ASSUME` ``back_attack``).
* **The Insignia combo system.**  Savage Roar / Savage Fang / Shadowstep engrave
  Insignias; Insignia Explosion consumes them and scales with the stack count
  (modeled at the assumed stack level).
* **Crit payoffs.**  Exploit Weakness (+Critical Hit, +Attack proc) and Assault
  Stance (+Critical Damage) feed Heart Gore, the low-cooldown crit-triggered hit.
* **Apply Poison** damage-over-time and the **Ambush Stance** on-move proc.
* Self crowd control (Shadowstrike stun) gating **Shadow Fall**.

Every damage number comes from ``data/global/classes/assassin.json``; only the
things the client does not expose live in :data:`TIMING` / :data:`ASSUME`.
"""
from __future__ import annotations

from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, fallback_to_generic, ms, spec_options  # noqa: F401

SID = dict(
    QS=13010000, ROAR=13100000, SSTRIKE=13070000, AMBUSH=13060000, HGORE=13350000,
    STORM=13340000, WHIRL=13210000, FLASH=13050000, INFIL=13360000, SFALL=13220000,
    INSIG=13130000, DEFI=13260000,
    SIXTH=13710000, EXPLOIT=13720000, POISON=13730000, REAR=13740000, ASTANCE=13750000,
    IMPACT=13760000, AMBSTANCE=13770000, DEFBREAK=13780000, REVITAL=13790000, DETERM=13800000,
    EVASIONC=13370000, SWALK=13180000, SFANG=13270000, AAMBUSH=13700000, SWIFT=13390000,
    TSHADOW=13020000, SSTEP=13140000, SMOKE=13250000, TRINIEL=13300000, AERIAL=13230000,
    EVASIONS=13080000, ICLONE=13310000,
)

TIMING = {
    "quick_slice": 0.75, "savage_roar": 0.80, "shadowstrike": 0.90, "ambush": 0.80,
    "heart_gore": 0.70, "whirlwind_slice": 0.85, "flash_slice": 0.85, "infiltrate": 0.90,
    "shadow_fall": 0.95, "insignia_explosion": 1.00, "chain_followup": 0.50, "stigma": 0.95,
}

ASSUME = {
    "back_attack": True,          # Assassin is positioned behind the boss
    "back_mult": 1.30,            # +30% from behind (Ambush, Triniel's Dagger)
    "boss_breakable": True,       # self-stun gates Shadow Fall
    "insignia_stacks": 5,         # assume Insignia Explosion is used at full stacks
    "exploit_attack_uptime": 0.80,  # Exploit Weakness's +Attack proc on crit, averaged
    "chain_frac": 0.60,
}


def build_kit(build: Build, cd: ClassData, filler: str = "quick_slice") -> Kit:
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

    back = ASSUME["back_mult"] if ASSUME["back_attack"] else 1.0

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

    add_static("EXPLOIT", {0: ("crit", 1.0)})            # +Critical Hit
    add_static("ASTANCE", {0: ("crit_dmg", 0.01)})       # +Critical Damage Boost
    add_static("IMPACT", {1: ("double", 0.01)})
    # Rear Smite: Back Attack Boost + PvE Boost (the Assassin is behind the boss)
    if lv("REAR") > 0:
        rv = cd.vals(SID["REAR"], lv("REAR"))
        static["amp_pve"] = static.get("amp_pve", 0.0) + \
            (rv[0] / 100.0 if ASSUME["back_attack"] else 0.0) + rv[1] / 100.0
    # Exploit Weakness: chance for +Attack% on crit, averaged over its high uptime
    if lv("EXPLOIT") > 0:
        ev = cd.vals(SID["EXPLOIT"], lv("EXPLOIT"))
        static["attack_pct"] = static.get("attack_pct", 0.0) + \
            (ev[2] / 100.0) * ASSUME["exploit_attack_uptime"]

    # Apply Poison DoT + Ambush Stance on-move proc (hooks) -------------------
    po_f = po_c = po_ticks = 0.0
    po_chance = po_icd = 0.0
    if lv("POISON") > 0:
        pv = cd.vals(SID["POISON"], lv("POISON"))
        po_chance, po_icd = float(pv[0]) / 100.0, ms(pv[5])
        dur = ms(pv[2])
        po_ticks = max(1.0, dur)       # one tick per second
        # the client lists the value as the total over the duration; spread per tick
        po_f, po_c = float(pv[3][0]) / po_ticks, float(pv[3][1]) / 100.0 / po_ticks
        po_dur = dur
    am_chance = am_f = am_c = am_icd = 0.0
    if lv("AMBSTANCE") > 0:
        av = cd.vals(SID["AMBSTANCE"], lv("AMBSTANCE"))
        am_chance, am_icd = float(av[0]) / 100.0, ms(av[3])
        am_f, am_c = float(av[1][0]), float(av[1][1]) / 100.0

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        if po_f and sim.proc("apply_poison", po_chance, po_icd, t):
            sim.dot("apply_poison", "Apply Poison", po_f, po_c, 1.0, po_dur)
        if am_f and sim.proc("ambush_stance", am_chance, am_icd, t):
            sim.hit("Ambush Stance", am_f, am_c, tags=("proc",))

    # ----------------------------------------------------------------- actives
    qs_f, qs_c = dmg("QS")

    def qs_cast(sim, a):
        tags = ("crit", "noparry") if has("QS", 5) else ()
        mods = {"multihit": 0.5} if has("QS", 3) else None
        sim.hit("Quick Slice", qs_f, qs_c, tags=tags, mods=mods)
        sim.gain_mp(100 * (1.2 if has("QS", 1) else 1.0))
        if has("QS", 4):
            sim.reduce_cd("insignia_explosion", 1.0)
    A["quick_slice"] = Action("quick_slice", "Quick Slice", SID["QS"], TIMING["quick_slice"],
                              on_cast=qs_cast, is_filler=True)

    ro_f, ro_c = dmg("ROAR")

    def roar_cast(sim, a):
        sim.hit("Savage Roar", ro_f, ro_c, mult=1.12 if has("ROAR", 3) else 1.0)
        sim.debuff("insignia", 10.0)
    A["savage_roar"] = Action("savage_roar", "Savage Roar", SID["ROAR"], TIMING["savage_roar"],
                              skill_speed=0.2 if has("ROAR", 2) else 0.0, on_cast=roar_cast, is_filler=True)

    # Ambush (Back attack bonus)
    am2_f, am2_c = dmg("AMBUSH")

    def ambush_cast(sim, a):
        sim.hit("Ambush", am2_f, am2_c, mult=back)
        if has("AMBUSH", 1):
            sim.debuff("insignia", 10.0)
    A["ambush"] = Action("ambush", "Ambush", SID["AMBUSH"], TIMING["ambush"],
                         cooldown=cd.cd(SID["AMBUSH"], lv("AMBUSH")), mp=cd.mp(SID["AMBUSH"], lv("AMBUSH")),
                         on_cast=ambush_cast)

    # Heart Gore (crit-triggered; low cooldown)
    hg_f, hg_c = dmg("HGORE")

    def hgore_cast(sim, a):
        tags = ("multi",) if has("HGORE", 4) else ()
        sim.hit("Heart Gore", hg_f, hg_c, tags=tags)
        sim.gain_mp(100)
        if has("HGORE", 2):
            sim.debuff("insignia", 10.0)
    A["heart_gore"] = Action("heart_gore", "Heart Gore", SID["HGORE"], TIMING["heart_gore"],
                             cooldown=cd.cd(SID["HGORE"], lv("HGORE")), on_cast=hgore_cast)

    # Shadowstrike (Stun -> gates Shadow Fall; +Critical Damage buff)
    sk_f, sk_c = dmg("SSTRIKE")

    def sstrike_cast(sim, a):
        sim.hit("Shadowstrike", sk_f, sk_c, mult=back)
        if has("SSTRIKE", 2):
            sim.buff("shadowstrike_cd", 10.0, {"crit_dmg": 0.20})
        if ASSUME["boss_breakable"]:
            sim.debuff("incap", 3.0 + (1.0 if has("SSTRIKE", 1) else 0.0))
    A["shadowstrike"] = Action("shadowstrike", "Shadowstrike", SID["SSTRIKE"], TIMING["shadowstrike"],
                               cooldown=cd.cd(SID["SSTRIKE"], lv("SSTRIKE")), mp=cd.mp(SID["SSTRIKE"], lv("SSTRIKE")),
                               on_cast=sstrike_cast)

    # Whirlwind Slice
    wh_f, wh_c = dmg("WHIRL")

    def whirl_cast(sim, a):
        mods = {"multihit": 0.5} if has("WHIRL", 1) else None
        sim.hit("Whirlwind Slice", wh_f, wh_c, mods=mods)
    A["whirlwind_slice"] = Action("whirlwind_slice", "Whirlwind Slice", SID["WHIRL"], TIMING["whirlwind_slice"],
                                  cooldown=cd.cd(SID["WHIRL"], lv("WHIRL")), on_cast=whirl_cast)

    # Flash Slice
    fl_f, fl_c = dmg("FLASH")
    A["flash_slice"] = Action("flash_slice", "Flash Slice", SID["FLASH"], TIMING["flash_slice"],
                              cooldown=cd.cd(SID["FLASH"], lv("FLASH")), mp=cd.mp(SID["FLASH"], lv("FLASH")),
                              on_cast=lambda sim, a: sim.hit("Flash Slice", fl_f, fl_c))

    # Infiltrate (Back; Dark Strike chain)
    inf_f, inf_c = dmg("INFIL")

    def infil_cast(sim, a):
        sim.hit("Infiltrate", inf_f, inf_c, mult=back)
        if has("INFIL", 4):
            k = ASSUME["chain_frac"]
            sim.hit("Dark Strike", inf_f * k, inf_c * k, mult=back, delay=TIMING["chain_followup"])
    A["infiltrate"] = Action("infiltrate", "Infiltrate", SID["INFIL"], TIMING["infiltrate"],
                             cooldown=cd.cd(SID["INFIL"], lv("INFIL")), on_cast=infil_cast)

    # Shadow Fall (needs Stun)
    sf_f, sf_c = dmg("SFALL")
    sf_cd = cd.cd(SID["SFALL"], lv("SFALL")) - (5 if has("SFALL", 3) else 0)

    def sfall_cast(sim, a):
        sim.hit("Shadow Fall", sf_f, sf_c)
        if has("SFALL", 2):
            sim.debuff("insignia", 10.0)
    A["shadow_fall"] = Action("shadow_fall", "Shadow Fall", SID["SFALL"], TIMING["shadow_fall"],
                              cooldown=sf_cd, mp=cd.mp(SID["SFALL"], lv("SFALL")),
                              requires=("incap",), on_cast=sfall_cast)

    # Insignia Explosion (consumes Insignia; scales with stacks)
    stacks = max(1, min(5, ASSUME["insignia_stacks"]))
    iv = cd.vals(SID["INSIG"], max(1, lv("INSIG")))
    idx = 3 + 3 * (stacks - 1)          # 1 stack -> v[3], 5 stacks -> v[15]
    ins_f, ins_c = (float(iv[idx][0]), float(iv[idx][1]) / 100.0) if idx < len(iv) else dmg("INSIG")

    def insig_cast(sim, a):
        mods = {"multihit": 0.5} if has("INSIG", 2) else None
        sim.hit("Insignia Explosion", ins_f, ins_c, mods=mods)
    A["insignia_explosion"] = Action("insignia_explosion", "Insignia Explosion", SID["INSIG"],
                                     TIMING["insignia_explosion"],
                                     cooldown=cd.cd(SID["INSIG"], lv("INSIG")) - (3 if has("INSIG", 5) else 0),
                                     mp=cd.mp(SID["INSIG"], lv("INSIG")), requires=("insignia",), on_cast=insig_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, stig, st, back, notes)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes)
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _build_stigmas(A, build, cd, stig, st, back, notes):
    def sdmg(key):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[0]
        return float(f), float(c) / 100.0

    # Swift Contract: +Combat Speed buff
    if stig("SWIFT"):
        sv = cd.vals(SID["SWIFT"], build.stigmas[SID["SWIFT"]])
        spd = sv[0] / 100.0 + (0.10 if st("SWIFT", 20) else 0.0)
        A["swift"] = Action("swift", cd.skills[SID["SWIFT"]]["name"], SID["SWIFT"], TIMING["stigma"],
                            cooldown=cd.cd(SID["SWIFT"], build.stigmas[SID["SWIFT"]]),
                            on_cast=lambda sim, a, s=spd: sim.buff("swift", ms(sv[1]) if isinstance(sv[1], dict) else 20.0,
                                                                   {"combat_speed": s}))

    for key in ("TRINIEL", "SFANG", "SMOKE", "AAMBUSH", "SSTEP", "TSHADOW", "AERIAL"):
        if not stig(key):
            continue
        akey = key.lower()
        f, c = sdmg(key)
        behind = back if key in ("TRINIEL",) else 1.0

        def nuke(sim, a, key=key, f=f, c=c, behind=behind):
            tags = ()
            if (key == "SFANG" and st("SFANG", 20)) or (key == "TSHADOW" and st("TSHADOW", 15)):
                tags = ("crit",)
            sim.hit(a.name, f, c, mult=behind, tags=tags)
            if key in ("SFANG", "SSTEP"):
                sim.debuff("insignia", 10.0)             # engrave Insignias
            if key == "SFANG" and st("SFANG", 15):
                sim.buff("savage_fang", 10.0, {"amp": 0.10})
            elif key == "AAMBUSH" and st("AAMBUSH", 5):
                sim.buff("assault_ambush", 5.0, {"attack_pct": 0.20})
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]), on_cast=nuke)


def _policy(actions: dict, filler: str) -> list:
    order = ["swift", "sfang", "aambush", "triniel", "smoke", "sstep", "tshadow", "aerial",
             "shadowstrike", "shadow_fall", "insignia_explosion", "ambush", "heart_gore",
             "infiltrate", "whirlwind_slice", "flash_slice", "savage_roar"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
