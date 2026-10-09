"""Chanter kit built from the global client's skill tables.

The Chanter is a staff hybrid, and the generic model misses its burst engine
and its mantras.  This kit adds:

* **Spinning Strike -> Dark Crush.**  Spinning Strike is a large nuke that also
  grants a stacking Critical Damage buff and opens a Dark Crush window;
  Impactful Crush opens one too.  Dark Crush (a 5s-cooldown nuke) is used in
  those windows.
* **Self crowd control gating Wave Blow** (Impactful Crush / Tremor Crush stun).
* **Mantras and buffs** — Undefeated Mantra (+PvE Damage Boost on a 5s cooldown,
  effectively permanent), Power of the Storm (+Combat Speed, +cooldown
  reduction) — and the on-hit passives Raging Spell (vs Stagger/Impact) and
  Wind's Promise (on a Critical Hit), plus Inspiring Spell / Attack Preparation
  / Wind's Promise crit stats.

Heals carry no damage and stay out of the rotation.  Every damage number comes
from ``data/global/classes/chanter.json``; only values the client does not
expose live in :data:`TIMING` / :data:`ASSUME`.
"""
from __future__ import annotations

from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, fallback_to_generic, ms, spec_options  # noqa: F401

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

TIMING = {
    "onslaught": 0.80, "incandescent_blow": 0.90, "rushing_smash": 0.90, "impactful_crush": 0.85,
    "dark_crush": 0.70, "heat_wave_blow": 0.90, "tremor_crush": 0.90, "wave_blow": 0.95,
    "spinning_strike": 1.20, "chain_followup": 0.55, "stigma": 1.00,
}

ASSUME = {
    "boss_breakable": True,       # self-stun gates Wave Blow
    "incand_cadence": 6.0,        # Incandescent Blow is a heavy swing, not a spammable basic
    "dark_crush_window": 2.0,     # seconds Dark Crush stays usable after Impactful Crush / Spinning Strike
    "spin_stacks": 2,             # Spinning Strike Critical Damage stacks maintained
    "stagger_uptime": 0.50,       # Raging Spell (extra damage vs Stagger/Impact)
    "crit_rate": 0.60,
    "chain_frac": 0.60,
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

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        if rg_f and sim.proc("raging_spell", ASSUME["stagger_uptime"], 1.0, t):
            sim.hit("Raging Spell", rg_f, rg_c, tags=("proc",))
        if wp and sim.proc("winds_promise", wp[0] * ASSUME["crit_rate"], wp[3], t):
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

    # Incandescent Blow: a hard-hitting swing (coef far above any basic), so it is
    # used on an assumed cadence rather than spammed as a filler.
    ic_f, ic_c = dmg("INCAND")
    A["incandescent_blow"] = Action("incandescent_blow", "Incandescent Blow", SID["INCAND"],
                                    TIMING["incandescent_blow"], cooldown=ASSUME["incand_cadence"],
                                    affected_by_cdr=False,
                                    on_cast=lambda sim, a: sim.hit("Incandescent Blow", ic_f, ic_c))

    rs_f, rs_c = dmg("RSMASH")

    def rsmash_cast(sim, a):
        sim.hit("Rushing Smash", rs_f, rs_c)
        sim.gain_mp(100)
    A["rushing_smash"] = Action("rushing_smash", "Rushing Smash", SID["RSMASH"], TIMING["rushing_smash"],
                                cooldown=cd.cd(SID["RSMASH"], lv("RSMASH")), on_cast=rsmash_cast)

    # Impactful Crush (Stun -> gates Wave Blow; opens the Dark Crush window)
    ip_f, ip_c = dmg("ICRUSH")

    def icrush_cast(sim, a):
        sim.hit("Impactful Crush", ip_f, ip_c)
        sim.buff("dark_crush", ASSUME["dark_crush_window"])
        if ASSUME["boss_breakable"]:
            sim.debuff("incap", 3.0)
    A["impactful_crush"] = Action("impactful_crush", "Impactful Crush", SID["ICRUSH"], TIMING["impactful_crush"],
                                  cooldown=cd.cd(SID["ICRUSH"], lv("ICRUSH")), mp=cd.mp(SID["ICRUSH"], lv("ICRUSH")),
                                  on_cast=icrush_cast)

    # Dark Crush (usable in the window; low cooldown)
    dc_f, dc_c = dmg("DCRUSH")
    A["dark_crush"] = Action("dark_crush", "Dark Crush", SID["DCRUSH"], TIMING["dark_crush"],
                             cooldown=cd.cd(SID["DCRUSH"], lv("DCRUSH")), requires=("dark_crush",),
                             on_cast=lambda sim, a: sim.hit("Dark Crush", dc_f, dc_c))

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

    def spin_cast(sim, a):
        sim.hit("Spinning Strike", sp_f, sp_c)
        sim.buff("spin_critdmg", 30.0, {"crit_dmg": spin_cd * ASSUME["spin_stacks"]})
        sim.buff("dark_crush", ASSUME["dark_crush_window"])
    A["spinning_strike"] = Action("spinning_strike", "Spinning Strike", SID["SPIN"], TIMING["spinning_strike"],
                                  cooldown=cd.cd(SID["SPIN"], lv("SPIN")), mp=cd.mp(SID["SPIN"], lv("SPIN")),
                                  on_cast=spin_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, SID, stig, st, notes)

    policy = _policy(A, filler)
    fallback_to_generic(A, policy, build, cd, notes)
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _build_stigmas(A, build, cd, SID, stig, st, notes):
    def sdmg(key):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[0]
        return float(f), float(c) / 100.0

    # Undefeated Mantra: +PvE Damage Boost on a 5s cooldown -> keep it up
    if stig("UNDEFEATED"):
        uv = cd.vals(SID["UNDEFEATED"], build.stigmas[SID["UNDEFEATED"]])
        A["undefeated"] = Action("undefeated", cd.skills[SID["UNDEFEATED"]]["name"], SID["UNDEFEATED"], 0.6,
                                cooldown=cd.cd(SID["UNDEFEATED"], build.stigmas[SID["UNDEFEATED"]]),
                                on_cast=lambda sim, a, s=uv[0] / 100.0: sim.buff("undefeated", 10.0, {"amp": s}))
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

        def nuke(sim, a, key=key, f=f, c=c):
            sim.hit(a.name, f, c)
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
