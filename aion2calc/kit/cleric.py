"""Cleric kit built from the global client's skill tables.

The Cleric is a healer that deals damage through a debuff-gated rotation, and
the generic model does not see the gating or the buffs.  This kit adds:

* **Chain of Torment -> Condemnation.**  Chain of Torment lays a damage-over-time
  debuff that makes Condemnation (a 3s-cooldown nuke) usable; the Cleric spams
  Condemnation while it is up.
* **Discharge.**  Earth's Retribution's chain follow-up.
* **Divine Aura** (a strong cooldown delivered over its duration) and charged
  **Bolt**.
* **Light of Protection** (+PvE Damage Boost on a 5s cooldown, effectively
  permanent) and Prayer of Amplification (+Attack), plus the Empyrean Lord's
  Grace on-hit rider and the Earth's Grace / Empyrean Lord's Grace crit stats.

Heals carry no damage and are left out of the rotation.  Every damage number
comes from ``data/global/classes/cleric.json``; only values the client does not
expose live in :data:`TIMING` / :data:`ASSUME`.
"""
from __future__ import annotations

from ..sim.engine import Action
from .base import Build, ClassData
from .common import Kit, fallback_to_generic, ms, spec_options  # noqa: F401

__all__ = ["build_kit", "spec_options"]

SID = dict(
    RETRIB=17010000, JUDGMENT=17040000, DMARK=17080000, DAURA=17150000, TORMENT=17070000,
    SCATTER=17370000, CONDEMN=17350000, BOLT=17060000, DEFI=17240000,
    WARM=17710000, ELBEN=17720000, ELGRACE=17730000, HEALENH=17740000, IMMORTAL=17750000,
    HEALBLK=17760000, PRAYERCONC=17770000, EGRACE=17780000, SURVWILL=17790000, RADBEN=17800000,
    VOICE=17300000, EPUNISH=None, POWERBURST=None, ASSAULTMARK=None, PRAYAMP=None,
    LIGHTPROT=None, ROOTST=None,
)

TIMING = {
    "earths_retribution": 0.85, "judgment_thunder": 0.85, "chain_of_torment": 0.95,
    "condemnation": 0.70, "debilitating_mark": 0.90, "divine_aura": 1.00, "bolt": 1.10,
    "chain_followup": 0.55, "stigma": 1.00,
}

ASSUME = {
    "bolt_charge": 3,
    "divine_aura_ticks": 5,       # the aura's listed damage is its total, delivered over 5s
    "crit_rate": 0.60,
    "chain_frac": 0.60,
    "discharge_chance": 0.5,      # Earth's Retribution -> Discharge chain trigger
}

# stigma skills resolved by name (ids vary; look them up from the class data)
_STIG_NAMES = {
    "VOICE": "Voice of Doom", "EPUNISH": "Earth Punishment", "POWERBURST": "Power Burst",
    "ASSAULTMARK": "Assault Mark", "PRAYAMP": "Prayer of Amplification",
    "LIGHTPROT": "Light of Protection", "ROOTST": "Root",
}


def build_kit(build: Build, cd: ClassData, filler: str = "earths_retribution") -> Kit:
    # resolve stigma ids by name (robust to id drift)
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

    add_static("ELGRACE", {0: ("crit", 1.0), 1: ("double", 0.01)})
    add_static("EGRACE", {0: ("crit_dmg", 0.01), 1: ("accuracy", 1.0)})

    # Empyrean Lord's Grace on-hit extra damage (icd 1s)
    elg = None
    if lv("ELGRACE") > 0:
        v = cd.vals(SID["ELGRACE"], lv("ELGRACE"))
        elg = (float(v[2][0]), float(v[2][1]) / 100.0, ms(v[4]) if len(v) > 4 else 1.0)

    def hook(sim, t, info):
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        if elg and sim.proc("empyrean_grace", 1.0, elg[2], t):
            sim.hit("Empyrean Lord's Grace", elg[0], elg[1], tags=("proc",))

    # ----------------------------------------------------------------- actives
    re_f, re_c = dmg("RETRIB")

    def retrib_cast(sim, a):
        mods = {"multihit": 0.5} if has("RETRIB", 3) else None
        sim.hit("Earth's Retribution", re_f, re_c, element="earth", mods=mods)
        sim.gain_mp(110 * (1.2 if has("RETRIB", 1) else 1.0))
        chance = ASSUME["discharge_chance"] + (0.20 if has("RETRIB", 2) else 0.0)
        if sim.proc("discharge", chance, 0.0, sim.t):
            k = ASSUME["chain_frac"]
            sim.hit("Discharge", re_f * k, re_c * k, element="earth", delay=TIMING["chain_followup"])
            if has("RETRIB", 4):
                sim.reduce_cd("bolt", 7.0)
    A["earths_retribution"] = Action("earths_retribution", "Earth's Retribution", SID["RETRIB"],
                                     TIMING["earths_retribution"], element="earth", on_cast=retrib_cast,
                                     is_filler=True)

    ju_f, ju_c = dmg("JUDGMENT")
    A["judgment_thunder"] = Action("judgment_thunder", "Judgment Thunder", SID["JUDGMENT"],
                                   TIMING["judgment_thunder"],
                                   on_cast=lambda sim, a: sim.hit("Judgment Thunder", ju_f, ju_c,
                                                                  mult=1.12 if has("JUDGMENT", 2) else 1.0),
                                   is_filler=True)

    # Chain of Torment (DoT debuff -> gates Condemnation)
    tv = cd.vals(SID["TORMENT"], max(1, lv("TORMENT")))
    to_f, to_c = float(tv[0][0]), float(tv[0][1]) / 100.0
    to_dur = ms(tv[6]) if len(tv) > 6 and isinstance(tv[6], dict) else 10.0
    tdot_f = float(tv[4][0]) / max(1.0, to_dur)
    tdot_c = float(tv[4][1]) / 100.0 / max(1.0, to_dur) if isinstance(tv[4][1], (int, float)) else 0.0

    def torment_cast(sim, a):
        sim.hit("Chain of Torment", to_f, to_c, element="earth")
        sim.dot("torment", "Chain of Torment (DoT)", tdot_f, tdot_c, 1.0, to_dur)
    A["chain_of_torment"] = Action("chain_of_torment", "Chain of Torment", SID["TORMENT"],
                                   TIMING["chain_of_torment"], cooldown=cd.cd(SID["TORMENT"], lv("TORMENT")),
                                   mp=cd.mp(SID["TORMENT"], lv("TORMENT")), element="earth", on_cast=torment_cast)

    # Condemnation (needs Chain of Torment; low cooldown spam)
    co_f, co_c = dmg("CONDEMN")

    def condemn_cast(sim, a):
        sim.hit("Condemnation", co_f, co_c, element="earth")
        if has("CONDEMN", 1):
            sim.gain_mp(100)
    A["condemnation"] = Action("condemnation", "Condemnation", SID["CONDEMN"], TIMING["condemnation"],
                               cooldown=cd.cd(SID["CONDEMN"], lv("CONDEMN")), element="earth",
                               requires=("torment",), on_cast=condemn_cast)

    # Debilitating Mark (DoT)
    dv = cd.vals(SID["DMARK"], max(1, lv("DMARK")))
    dm_f, dm_c = float(dv[0][0]), float(dv[0][1]) / 100.0
    dm_dur = ms(dv[6]) if len(dv) > 6 and isinstance(dv[6], dict) else 10.0
    dmdot_f = float(dv[4][0]) / max(1.0, dm_dur)
    dmdot_c = float(dv[4][1]) / 100.0 / max(1.0, dm_dur) if isinstance(dv[4][1], (int, float)) else 0.0

    def dmark_cast(sim, a):
        sim.hit("Debilitating Mark", dm_f, dm_c)
        sim.dot("debil_mark", "Debilitating Mark (DoT)", dmdot_f, dmdot_c, 1.0, dm_dur)
        if has("DMARK", 1):
            sim.gain_mp(150)
    A["debilitating_mark"] = Action("debilitating_mark", "Debilitating Mark", SID["DMARK"],
                                    TIMING["debilitating_mark"], cooldown=cd.cd(SID["DMARK"], lv("DMARK")),
                                    mp=0.0 if has("DMARK", 1) else cd.mp(SID["DMARK"], lv("DMARK")),
                                    on_cast=dmark_cast)

    # Divine Aura (strong cooldown; total damage delivered over its duration)
    av = cd.vals(SID["DAURA"], max(1, lv("DAURA")))
    da_f, da_c = float(av[0][0]), float(av[0][1]) / 100.0
    da_n = ASSUME["divine_aura_ticks"]
    A["divine_aura"] = Action("divine_aura", "Divine Aura", SID["DAURA"], TIMING["divine_aura"],
                              cooldown=cd.cd(SID["DAURA"], lv("DAURA")),
                              on_cast=lambda sim, a: sim.hit("Divine Aura", da_f, da_c, element="earth",
                                                            n=da_n, spread=5.0))

    # Bolt (charge nuke)
    bv = cd.vals(SID["BOLT"], max(1, lv("BOLT")))
    b_idx = 1 if ASSUME["bolt_charge"] >= 3 else 0
    bo_f, bo_c = float(bv[b_idx][0]), float(bv[b_idx][1]) / 100.0
    A["bolt"] = Action("bolt", "Bolt", SID["BOLT"], TIMING["bolt"], cooldown=cd.cd(SID["BOLT"], lv("BOLT")),
                       mp=cd.mp(SID["BOLT"], lv("BOLT")),
                       on_cast=lambda sim, a: sim.hit("Bolt", bo_f, bo_c), requires_charge=True, charge_level=3)

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

    # Light of Protection: +PvE Damage Boost on a 5s cooldown -> keep it up
    if stig("LIGHTPROT"):
        lv = cd.vals(SID["LIGHTPROT"], build.stigmas[SID["LIGHTPROT"]])
        A["lightprot"] = Action("lightprot", cd.skills[SID["LIGHTPROT"]]["name"], SID["LIGHTPROT"], 0.6,
                               cooldown=cd.cd(SID["LIGHTPROT"], build.stigmas[SID["LIGHTPROT"]]),
                               on_cast=lambda sim, a, s=lv[0] / 100.0: sim.buff("lightprot", 10.0, {"amp": s}))
    # Prayer of Amplification: +Attack%
    if stig("PRAYAMP"):
        pv = cd.vals(SID["PRAYAMP"], build.stigmas[SID["PRAYAMP"]])
        A["prayamp"] = Action("prayamp", cd.skills[SID["PRAYAMP"]]["name"], SID["PRAYAMP"], TIMING["stigma"],
                             cooldown=cd.cd(SID["PRAYAMP"], build.stigmas[SID["PRAYAMP"]]),
                             on_cast=lambda sim, a, s=pv[0] / 100.0: sim.buff("prayamp", 20.0, {"attack_pct": s}))

    for key in ("VOICE", "EPUNISH", "POWERBURST", "ROOTST", "ASSAULTMARK"):
        if not stig(key):
            continue
        akey = key.lower()
        f, c = sdmg(key)
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]),
                         element="earth", on_cast=lambda sim, a, f=f, c=c: sim.hit(a.name, f, c, element="earth"))


def _policy(actions: dict, filler: str) -> list:
    order = ["lightprot", "prayamp", "bolt", "divine_aura", "voice", "epunish", "powerburst",
             "rootst", "assaultmark", "chain_of_torment", "condemnation", "debilitating_mark",
             "judgment_thunder"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
