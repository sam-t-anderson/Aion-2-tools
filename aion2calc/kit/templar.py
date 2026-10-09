"""Templar kit built from the global client's skill tables.

What the tooltip-driven generic kit misses for a Templar, and this kit adds:

* **Judgment windows.**  Shield Smite, Warding Strike, Shield Rush and Doom
  Shield each *Trigger Judgment* for a couple of seconds; Judgment (its own
  cooldown removed by the u16 spec) is the Templar's primary nuke, fired in
  those windows rather than freely or never.
* **Executor.**  Punishment grants +PvE Damage Boost for 20s — a high-uptime
  amp buff the generic kit cannot see.
* **Self crowd control gating Annihilate.**  Shield Smite / Shield Rush stun
  the target (Doom Shield knocks it down); Annihilate is only usable then.
* **The on-hit passives** Punishing Benediction (bonus-damage proc) and
  Insulting Roar (+Attack on a front attack, effectively permanent on a frontal
  boss), plus Fury's front-attack boost.

Every damage number is read from ``data/global/classes/templar.json``; only the
things the client does not expose live in :data:`TIMING` / :data:`ASSUME`.
"""
from __future__ import annotations

from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, fallback_to_generic, ms, spec_options  # noqa: F401

__all__ = ["build_kit", "spec_options"]

SID = dict(
    VIC=12010000, PUM=12040000, POACH=12130000, SMITE=12100000, JUDG=12240000,
    FLASH=12340000, DEBIL=12270000, WARD=12350000, SRUSH=12430000, ANNI=12300000,
    PUNISH=12090000, DEFI=12260000,
    EHP=12710000, WSHIELD=12720000, PBEN=12730000, IRON=12740000, GSEAL=12750000,
    IMPACT=12760000, ROAR=12770000, FURY=12780000, SURVWILL=12790000, BPAIN=12800000,
    SECOND=12190000, GRAPPLE=12220000, ELP=12310000, NEZ=12320000, AFURY=12700000,
    DOOM=12070000, BANNER=12450000, SPROT=12110000, NOBLE=12230000, EXEC=12410000, TAUNT=12120000,
)

TIMING = {
    "vicious_strike": 0.80, "pummel": 0.90, "shield_smite": 0.90, "judgment": 0.70,
    "debilitating_smash": 0.90, "warding_strike": 1.00, "shield_rush": 0.90,
    "annihilate": 1.00, "punishment": 1.20, "chain_followup": 0.55, "stigma": 1.00,
}

ASSUME = {
    "boss_breakable": True,       # training boss can be stunned/knocked down (gates Annihilate)
    "judgment_window": 2.0,       # seconds Judgment stays usable after a trigger skill
    "chain_frac": 0.60,
    "punishment_charge": 3,       # assume the skill is cast at full charge
}


def build_kit(build: Build, cd: ClassData, filler: str = "vicious_strike") -> Kit:
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

    add_static("PBEN", {0: ("crit", 1.0)})               # Punishing Benediction: +Critical Hit
    add_static("IMPACT", {1: ("double", 0.01)})
    add_static("FURY", {0: ("amp_pve", 0.01)})            # Front Attack Boost; dummy is frontal
    # Insulting Roar: +Attack% on a front attack with a short internal cooldown that is
    # shorter than the buff, so on a frontal boss it is effectively always up.
    add_static("ROAR", {1: ("attack_pct", 0.01)})

    # Punishing Benediction proc: chance to deal extra damage on landing an attack (icd 1s)
    pb_chance = pb_f = pb_c = pb_icd = 0.0
    if lv("PBEN") > 0:
        pv = cd.vals(SID["PBEN"], lv("PBEN"))
        pb_chance, pb_icd = float(pv[1]) / 100.0, ms(pv[4])
        pb_f, pb_c = float(pv[2][0]), float(pv[2][1]) / 100.0

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        if pb_f and sim.proc("punishing_benediction", pb_chance, pb_icd, t):
            sim.hit("Punishing Benediction", pb_f, pb_c, tags=("proc",))

    # ----------------------------------------------------------------- actives
    # Vicious Strike (filler: restores MP, Threatening Blow chain)
    vi_f, vi_c = dmg("VIC")

    def vic_cast(sim, a):
        mods = {"multihit": 0.5} if has("VIC", 3) else None
        sim.hit("Vicious Strike", vi_f, vi_c, mods=mods)
        sim.gain_mp(100 * (1.2 if has("VIC", 1) else 1.0))
        if has("VIC", 2):
            sim.reduce_cd("warding_strike", 2.0)
        if has("VIC", 5):
            k = ASSUME["chain_frac"]
            sim.hit("Threatening Blow", vi_f * k, vi_c * k, delay=TIMING["chain_followup"])
    A["vicious_strike"] = Action("vicious_strike", "Vicious Strike", SID["VIC"], TIMING["vicious_strike"],
                                 on_cast=vic_cast, is_filler=True)

    # Pummel (filler: Stagger builder)
    pu_f, pu_c = dmg("PUM")

    def pummel_cast(sim, a):
        sim.hit("Pummel", pu_f, pu_c, mult=1.12 if has("PUM", 3) else 1.0)
    A["pummel"] = Action("pummel", "Pummel", SID["PUM"], TIMING["pummel"],
                         on_cast=pummel_cast, is_filler=True)

    # Judgment (primary nuke; usable in the window the trigger skills open)
    ju_f, ju_c = dmg("JUDG")
    ju_cd = 0.0 if has("JUDG", 5) else cd.cd(SID["JUDG"], lv("JUDG"))

    def judg_cast(sim, a):
        tags = ("crit",) if has("JUDG", 4) else ()
        mult = 1.3 if has("JUDG", 3) else 1.0            # "Extra damage on hit"
        sim.hit("Judgment", ju_f, ju_c, mult=mult, tags=tags)
    A["judgment"] = Action("judgment", "Judgment", SID["JUDG"], TIMING["judgment"],
                           cooldown=ju_cd, requires=("judgment",), on_cast=judg_cast)

    def trigger_judgment(sim):
        sim.buff("judgment", ASSUME["judgment_window"])

    # Shield Smite (Stun -> gates Annihilate; triggers Judgment; Debilitating Smash)
    ss_f, ss_c = dmg("SMITE")
    ss_cd = cd.cd(SID["SMITE"], lv("SMITE")) - (2 if has("SMITE", 4) else 0)

    def smite_cast(sim, a):
        sim.hit("Shield Smite", ss_f, ss_c)
        if ASSUME["boss_breakable"]:
            sim.debuff("incap", 3.0 + (1.0 if has("SMITE", 1) else 0.0))
        trigger_judgment(sim)
    A["shield_smite"] = Action("shield_smite", "Shield Smite", SID["SMITE"], TIMING["shield_smite"],
                               cooldown=ss_cd, mp=cd.mp(SID["SMITE"], lv("SMITE")), on_cast=smite_cast)

    # Debilitating Smash (Defense-down; solid cooldown nuke)
    de_f, de_c = dmg("DEBIL")

    def debil_cast(sim, a):
        tags = ("multi", "noparry") if has("DEBIL", 4) else ()
        sim.hit("Debilitating Smash", de_f, de_c, tags=tags)
    A["debilitating_smash"] = Action("debilitating_smash", "Debilitating Smash", SID["DEBIL"],
                                     TIMING["debilitating_smash"], cooldown=cd.cd(SID["DEBIL"], lv("DEBIL")),
                                     on_cast=debil_cast)

    # Warding Strike (triggers Judgment)
    wa_f, wa_c = dmg("WARD")
    wa_cd = cd.cd(SID["WARD"], lv("WARD")) - (5 if has("WARD", 1) else 0)

    def ward_cast(sim, a):
        sim.hit("Warding Strike", wa_f, wa_c)
        trigger_judgment(sim)
    A["warding_strike"] = Action("warding_strike", "Warding Strike", SID["WARD"], TIMING["warding_strike"],
                                 cooldown=wa_cd, mp=cd.mp(SID["WARD"], lv("WARD")), on_cast=ward_cast)

    # Shield Rush (Stun; triggers Judgment)
    sr_f, sr_c = dmg("SRUSH")
    sr_cd = cd.cd(SID["SRUSH"], lv("SRUSH")) - (10 if has("SRUSH", 4) else 0)

    def srush_cast(sim, a):
        sim.hit("Shield Rush", sr_f, sr_c)
        if ASSUME["boss_breakable"]:
            sim.debuff("incap", 3.0)
        trigger_judgment(sim)
    A["shield_rush"] = Action("shield_rush", "Shield Rush", SID["SRUSH"], TIMING["shield_rush"],
                              cooldown=sr_cd, on_cast=srush_cast)

    # Annihilate (only while the target is stunned/knocked down)
    an_f, an_c = dmg("ANNI")
    an_cd = cd.cd(SID["ANNI"], lv("ANNI")) - (10 if has("ANNI", 4) else 0)

    def anni_cast(sim, a):
        mods = {"multihit": 0.5} if has("ANNI", 1) else None
        sim.hit("Annihilate", an_f, an_c, mods=mods)
    A["annihilate"] = Action("annihilate", "Annihilate", SID["ANNI"], TIMING["annihilate"],
                             cooldown=an_cd, mp=cd.mp(SID["ANNI"], lv("ANNI")),
                             requires=("incap",), on_cast=anni_cast)

    # Punishment (charge nuke + Executor amp buff)
    pv = cd.vals(SID["PUNISH"], max(1, lv("PUNISH")))
    charge_idx = 1 if ASSUME["punishment_charge"] >= 3 else 0
    pn_f, pn_c = float(pv[charge_idx][0]), float(pv[charge_idx][1]) / 100.0
    ex_amp = float(pv[4]) / 100.0 if len(pv) > 4 and isinstance(pv[4], (int, float)) else 0.20
    pn_speed = 0.30 if has("PUNISH", 3) else 0.0

    def punish_cast(sim, a):
        tags = ("crit",) if has("PUNISH", 5) else ()
        sim.hit("Punishment", pn_f, pn_c, tags=tags)
        sim.buff("executor", ms(pv[2]) if isinstance(pv[2], dict) else 20.0, {"amp": ex_amp})
    A["punishment"] = Action("punishment", "Punishment", SID["PUNISH"], TIMING["punishment"],
                             cooldown=cd.cd(SID["PUNISH"], lv("PUNISH")), mp=cd.mp(SID["PUNISH"], lv("PUNISH")),
                             skill_speed=pn_speed, on_cast=punish_cast, requires_charge=True, charge_level=3)

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

    for key in ("EXEC", "DOOM", "ELP", "AFURY", "GRAPPLE", "TAUNT"):
        if not stig(key):
            continue
        akey = key.lower()
        f, c = sdmg(key)

        def nuke(sim, a, key=key, f=f, c=c):
            tags = ("crit",) if (key == "EXEC" and st("EXEC", 15)) else ()
            mult = 1.20 if key == "EXEC" else 1.0        # Executing Blade: +dmg vs Impact status
            sim.hit(a.name, f, c, mult=mult, tags=tags)
            if key == "ELP" and st("ELP", 15):
                sim.buff("elp_boost", 10.0, {"amp": 0.10})
            elif key == "AFURY" and st("AFURY", 5):
                sim.buff("assault_fury", 5.0, {"attack_pct": 0.20})
            elif key == "DOOM" and st("DOOM", 5):
                sim.reset_cd("annihilate")
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]), on_cast=nuke)


def _policy(actions: dict, filler: str) -> list:
    order = ["punishment", "exec", "elp", "doom", "afury", "grapple", "taunt",
             "shield_smite", "shield_rush", "warding_strike", "annihilate", "judgment",
             "debilitating_smash", "pummel"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
