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
from ..model.damage import crit_probability
from .common import Kit, add_stagger_skill, add_weave, fallback_to_generic, ms, spec_options  # noqa: F401

__all__ = ["build_kit", "spec_options"]

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

#: Action time in seconds at 0% Combat Speed.  Measured (0.2.307) from the recorded casts of four
#: global Assassins (docs/methodology.md "Measured action times"); ``quick_slice`` is the whole
#: Quick -> Breaking -> Swift Slice combo pressed on its own (~0.6 s a step), since the kit lands all
#: three hits in one cast.  Whirlwind Slice, Flash Slice and Shadow Fall keep their estimates (too
#: few recorded presses).
TIMING = {
    "quick_slice": 1.93, "savage_roar": 0.63, "shadowstrike": 0.26, "ambush": 0.40,
    "heart_gore": 0.35, "whirlwind_slice": 0.85, "flash_slice": 0.85, "infiltrate": 0.85,
    "shadow_fall": 0.95, "insignia_explosion": 0.42, "chain_followup": 0.50, "stigma": 0.31,
    "storm_rampage": 3.71,        # the presses of a stagger, 19.0 hits at 0.182 s each (0.2.380; docs/methodology.md
                                  #   "Storm Rampage and Flame Scattershot from the recordings"; 4.8 before)
    "roar_chain": 1.5,            # Savage Back Kick then Savage Smash pressed after Savage Roar: 1.13 s recorded
                                  #   at 31 % Combat Speed from the Roar's hit to the Smash's (0.2.368)
}

ASSUME = {
    "back_attack": True,          # Assassin is positioned behind the boss
    "back_mult": 1.30,            # +30% from behind (Ambush, Triniel's Dagger)
    "boss_breakable": True,       # self-stun gates Shadow Fall
    "insignia_stacks": 5,         # assume Insignia Explosion is used at full stacks
    "exploit_attack_uptime": 0.80,  # Exploit Weakness's +Attack proc on crit, averaged
    "chain_frac": 1.5,            # Dark Strike (Infiltrate chain); community parses put detected
                                  #   chains at ~1.4-1.9x, so 1.5 (was 0.85) class-wide
    # Measured (0.2.368) from one global Assassin's 51 recorded boss fights on the log server, 79 minutes of boss
    # time (docs/methodology.md "The Assassin from the log server's uploads"):
    "roar_chain": ((0.30, 3.65), (0.71, 1.58)),
                                  # Savage Back Kick and Savage Smash, the chain steps after Savage Roar: each
                                  #   step's hit against one Savage Roar hit, and its hits per Savage Roar cast
    # Storm Rampage, usable only on a staggered boss: pressed back to back once the opening skills are out, one train
    # of presses a stagger (0.2.380; 6 Assassins, 95 staggers, every fight counted once over its uploads):
    "storm_rampage_hits": 19.0,   # hits a stagger; the hits of a fifth that follow each one inside an Illusive Clone
                                  #   window are the clone's (13.4 hits a channel, doubled with Multi-Hit, before)
    "storm_rampage_hit": 0.16,    # each hit against the tooltip's value, measured against a Heart Gore hit (0.32 before,
                                  #   from hits that counted the clone's; the tooltip split over a press's four hits
                                  #   would be 0.25)
    "clone_echo": 0.07,           # Illusive Clone's extra damage as a share of the damage dealt while it lasts
                                  #   (its tooltip says 20 %; the recorded clone dealt 7 %, in 99 of 99 windows)
    "clone_attack_echo": 0.008,   # Illusive Clone Lv 20 "50% chance to deal extra damage on Critical Hit": the
                                  #   Clone Attack hits were 0.8 % of the damage dealt while the clone lasted
    "exploit_clone_hits": 1.55,   # hits per Exploit Weakness clone proc (bursts of one to four)
    "heart_gore_recast": 0.73,    # at 0 % Combat Speed: with its cooldown gone Heart Gore came back 0.56 s after
                                  #   the previous press (median, at the recorded 31 % Combat Speed)
    # Quick Slice basic-attack combo, measured from a community L45 assassin parse (0.2.256):
    "swift_frac": 0.67,           # Quick Slice -> Swift Slice combo step (~0.67x the base)
    "breaking_frac": 0.76,        # Quick Slice -> Breaking Slice combo step (~0.76x the base)
    "savage_roar_cadence": 8.0,   # one Savage Roar press per 8 s of boss time (in bursts 2.3 s apart): it keeps
                                  #   the Insignia up and opens its chain, and is not the filler (0.2.368)
}

#: The basic-attack chain's three steps (name, share of the woven steps, damage per press against
#: the first step), the woven steps after each press and after any press recorded too rarely (the
#: median of the per-skill rates), from the recorded fights (0.2.309; docs/methodology.md "Woven
#: basic attacks").
WEAVE = {
    "steps": (("Quick Slice", 0.37, 1.00), ("Swift Slice", 0.30, 1.49), ("Breaking Slice", 0.33, 1.14)),
    "after": {"savage_roar": 0.66, "insignia_explosion": 0.04, "heart_gore": 0.02, "ambush": 0.0,
              "shadowstrike": 0.04, "infiltrate": 0.11, "triniel": 0.06,
              "storm_rampage": 2.24},     # inside or right after a train of Storm Rampage presses (0.2.380)
    "per_press": 0.04,
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
    exploit_pct = 0.0
    ec_chance = ec_f = ec_c = 0.0
    ec_icd = 1.0
    if lv("EXPLOIT") > 0:
        ev = cd.vals(SID["EXPLOIT"], lv("EXPLOIT"))
        exploit_pct = (ev[2] / 100.0) * ASSUME["exploit_attack_uptime"]
        static["attack_pct"] = static.get("attack_pct", 0.0) + exploit_pct
        # "{4}% chance to summon up to 5 clones on landing a Critical Hit", each hitting for {5}, once a second;
        # the recorded clones were 2.5 % of the damage
        ec_chance, ec_icd = float(ev[4]) / 100.0, ms(ev[8]) if len(ev) > 8 else 1.0
        ec_f, ec_c = float(ev[5][0]), float(ev[5][1]) / 100.0
    # Determination (passive): extra damage on landing an attack while the target is below its HP threshold,
    # once per its own cooldown; the recorded Assassin's boss fights put it at 1.8% of the damage.
    de_f = de_c = de_win = 0.0
    de_icd = 1.0
    if lv("DETERM") > 0:
        dv = cd.vals(SID["DETERM"], lv("DETERM"))
        de_f, de_c = float(dv[0][0]), float(dv[0][1]) / 100.0
        de_win, de_icd = float(dv[2]) / 100.0, ms(dv[3]) if len(dv) > 3 else 1.0

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
        if de_f and sim.target.hp_pct(t, sim.cfg.duration) <= de_win and sim.proc("determination", 1.0, de_icd, t):
            sim.hit("Determination", de_f, de_c, tags=("proc",))
        if ec_f:                  # Exploit Weakness's clones on a crit; Illusive Clone Lv 15 raises their chance by half
            staggered = sim.target.stagger_crit and any(s <= t < e for s, e in sim.target.stagger_windows)
            p = 1.0 if staggered else crit_probability(sim.base, sim.target, extra=sim.stat_mods(t).get("crit", 0.0))
            boost = 1.5 if st("ICLONE", 15) and sim.has_buff("illusive_clone") else 1.0
            if sim.proc("exploit_clones", ec_chance * boost * p, ec_icd, t):
                k = ASSUME["exploit_clone_hits"]
                sim.hit("Exploit Weakness", ec_f * k, ec_c * k, n=2, tags=("proc",))

    # ----------------------------------------------------------------- actives
    qs_f, qs_c = dmg("QS")

    def qs_cast(sim, a):
        tags = ("crit", "noparry") if has("QS", 5) else ()
        mods = {"multihit": 0.5} if has("QS", 3) else None
        sim.hit("Quick Slice", qs_f, qs_c, tags=tags, mods=mods)
        # Quick Slice is the first step of the melee combo string; Swift Slice and
        # Breaking Slice follow from it (together ~13% of real damage, previously dropped).
        sw = ASSUME["swift_frac"]
        br = ASSUME["breaking_frac"]
        sim.hit("Swift Slice", qs_f * sw, qs_c * sw, tags=tags)
        sim.hit("Breaking Slice", qs_f * br, qs_c * br, tags=tags)
        sim.gain_mp(100 * (1.2 if has("QS", 1) else 1.0))
        if has("QS", 4):
            sim.reduce_cd("insignia_explosion", 1.0)
    A["quick_slice"] = Action("quick_slice", "Quick Slice", SID["QS"], TIMING["quick_slice"],
                              on_cast=qs_cast, is_filler=True)

    ro_f, ro_c = dmg("ROAR")

    def roar_cast(sim, a):
        sim.hit("Savage Roar", ro_f, ro_c, mult=1.12 if has("ROAR", 3) else 1.0)
        sim.debuff("insignia", 10.0)
        if has("ROAR", 4):
            sim.reduce_cd("shadowstrike", 1.0)
        # its chain, Savage Back Kick then Savage Smash, pressed after it (recorded 0.4 s and 1.2 s after the Roar);
        # each step's hit is its ratio of a Roar hit, the per-hit flat add (Penetration) included on both sides
        add = sim.base.flat_add + sim.stat_mods(sim.t).get("flat_add", 0.0)
        for (ratio, n), name, delay in zip(ASSUME["roar_chain"], ("Savage Back Kick", "Savage Smash"), (0.4, 1.2)):
            sim.hit(name, (ratio * (ro_f + add) - add) * n, ro_c * ratio * n, n=max(1, round(n)), delay=delay, spread=0.3)
    # Savage Roar engraves the Insignia and opens its chain; the recorded Assassin pressed it once per 8 s of boss
    # time (in bursts 2.3 s apart), so it keeps a cadence rather than being the filler (Quick Slice's combo is).
    A["savage_roar"] = Action("savage_roar", "Savage Roar", SID["ROAR"], TIMING["savage_roar"] + TIMING["roar_chain"],
                              cooldown=ASSUME["savage_roar_cadence"],
                              skill_speed=0.2 if has("ROAR", 2) else 0.0, on_cast=roar_cast)

    # Ambush (Back attack bonus)
    am2_f, am2_c = dmg("AMBUSH")

    def ambush_cast(sim, a):
        sim.hit("Ambush", am2_f, am2_c, mult=back)
        if has("AMBUSH", 1):
            sim.debuff("insignia", 10.0)
    A["ambush"] = Action("ambush", "Ambush", SID["AMBUSH"], TIMING["ambush"],
                         cooldown=cd.cd(SID["AMBUSH"], lv("AMBUSH")), mp=cd.mp(SID["AMBUSH"], lv("AMBUSH")),
                         on_cast=ambush_cast)

    # Heart Gore (crit-triggered; low cooldown). The recorded Assassin pressed it 19.5 times a minute for 28%
    # of the damage (0.2.368): its Lv 16 effect resets the cooldown on a crit, and Illusive Clone removes it.
    hg_f, hg_c = dmg("HGORE")

    def recast(sim):
        """Heart Gore's wait with its cooldown gone, at the current Combat Speed."""
        return ASSUME["heart_gore_recast"] / (1.0 + sim.base.combat_speed + sim.stat_mods(sim.t).get("combat_speed", 0.0))

    def hgore_cast(sim, a):
        tags = ("multi",) if has("HGORE", 4) else ()
        mods = None
        if has("HGORE", 3):       # "Up to +20% Critical Hit when less targets hit": one target, the whole +20%
            mods = {"crit": 0.20 * (sim.base.crit_stat + sim.stat_mods(sim.t).get("crit", 0.0))}
        sim.hit("Heart Gore", hg_f, hg_c, tags=tags, mods=mods)
        sim.gain_mp(100)
        if has("HGORE", 2):
            sim.debuff("insignia", 10.0)
        if sim.has_buff("illusive_clone"):
            sim.ready["heart_gore"] = sim.t + recast(sim)
        elif has("HGORE", 5):     # "Resets [Heart Gore] cooldown on landing a Critical Hit": the expected wait, the
            extra = sim.stat_mods(sim.t).get("crit", 0.0) + (mods or {}).get("crit", 0.0)   # recast on a crit's share
            p = crit_probability(sim.base, sim.target, extra=extra)
            sim.ready["heart_gore"] = sim.t + p * recast(sim) + (1.0 - p) * (sim.ready["heart_gore"] - sim.t)
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

    # Storm Rampage, usable only on a staggered boss: one train of presses a stagger (0.2.380), as every class's stagger
    # skill. Its Lv 16 option takes a second off every cooldown at each hit (Illusive Clone came back every 46 s against
    # its 80 s cooldown, 0.2.368); its Lv 12 Multi-Hit lands four extra hits inside each hit's record, not the hits of a
    # fifth that follow each one inside an Illusive Clone window (the clone's, as on every skill)
    add_stagger_skill(A, build, cd, L, SID["STORM"], "storm_rampage", hits=ASSUME["storm_rampage_hits"],
                      hit=ASSUME["storm_rampage_hit"], cast=TIMING["storm_rampage"])

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
    # Illusive Clone: for its duration Heart Gore has no cooldown and the clone deals a share of the damage dealt
    # again (the tooltip's 20 %; the recorded clone dealt 7 %); Lv 10 adds Critical Damage Boost, Lv 15 raises
    # Exploit Weakness's effects by half, Lv 20 adds the Clone Attack hits on crits (0.8 % of the damage).
    if stig("ICLONE"):
        iv = cd.vals(SID["ICLONE"], build.stigmas[SID["ICLONE"]])
        ic_share, ic_dur = ASSUME["clone_echo"], ms(iv[1])

        def iclone_cast(sim, a):
            stats = {}
            if st("ICLONE", 10):
                stats["crit_dmg"] = 0.20
            if st("ICLONE", 15) and exploit_pct:
                stats["attack_pct"] = exploit_pct * 0.5
            sim.buff("illusive_clone", ic_dur, stats)
            sim.echo("Illusive Clone", ic_share, ic_dur)
            if st("ICLONE", 20):
                sim.echo("Clone Attack", ASSUME["clone_attack_echo"], ic_dur)
            sim.ready["heart_gore"] = min(sim.ready.get("heart_gore", sim.t), sim.t + recast(sim))
        A["illusive_clone"] = Action("illusive_clone", cd.skills[SID["ICLONE"]]["name"], SID["ICLONE"], TIMING["stigma"],
                                     cooldown=cd.cd(SID["ICLONE"], build.stigmas[SID["ICLONE"]]),
                                     mp=cd.mp(SID["ICLONE"], build.stigmas[SID["ICLONE"]]), on_cast=iclone_cast)
    _build_stigmas(A, build, cd, stig, st, back, notes, lv)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes)
    add_weave(A, WEAVE, qs_f, qs_c, mp=100 * (1.2 if has("QS", 1) else 1.0), skip=("quick_slice",))
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _build_stigmas(A, build, cd, stig, st, back, notes, lv):
    def sdmg(key):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[0]
        return float(f), float(c) / 100.0

    # Swift Contract: +Combat Speed buff; its Lv 10 and 15 effects raise two passives by half for the duration
    if stig("SWIFT"):
        sv = cd.vals(SID["SWIFT"], build.stigmas[SID["SWIFT"]])
        stats = {"combat_speed": sv[0] / 100.0 + (0.10 if st("SWIFT", 20) else 0.0)}
        if st("SWIFT", 10) and lv("REAR") > 0:          # "x1.5 [Rear Smite] effect": its Back Attack and PvE Boost
            rv = cd.vals(SID["REAR"], lv("REAR"))
            stats["amp"] = 0.5 * ((rv[0] / 100.0 if ASSUME["back_attack"] else 0.0) + rv[1] / 100.0)
        if st("SWIFT", 15) and lv("ASTANCE") > 0:       # "x1.5 [Assault Stance] effect": its Critical Damage Boost
            stats["crit_dmg"] = 0.5 * cd.vals(SID["ASTANCE"], lv("ASTANCE"))[0] / 100.0
        A["swift"] = Action("swift", cd.skills[SID["SWIFT"]]["name"], SID["SWIFT"], TIMING["stigma"],
                            cooldown=cd.cd(SID["SWIFT"], build.stigmas[SID["SWIFT"]]),
                            on_cast=lambda sim, a, s=stats: sim.buff("swift", ms(sv[1]) if isinstance(sv[1], dict) else 20.0,
                                                                     dict(s)))

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
            if key == "TRINIEL" and st("TRINIEL", 10):   # "-10% all skill cooldowns on hit"
                sim.reduce_cds_by_share(0.10)
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
    order = ["storm_rampage", "illusive_clone", "swift", "sfang", "aambush", "triniel", "smoke", "sstep", "tshadow", "aerial",
             "shadowstrike", "shadow_fall", "insignia_explosion", "ambush", "heart_gore",
             "infiltrate", "whirlwind_slice", "flash_slice", "savage_roar"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
