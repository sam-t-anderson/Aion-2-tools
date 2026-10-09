"""Spiritmaster kit built from the global client's skill tables.

The Spiritmaster's damage is half pet, and the generic tooltip model sees none
of the pet.  This kit adds:

* **The summoned Spirit as a background damage stream.**  Once summoned the
  Spirit attacks on its own, independent of the caster's global cooldown: a
  basic-attack stream plus its skill on the Spirit Skill Cooldown.  Each Spirit
  skill also triggers Dimensional Control and advances the Four Elements gauge.
* **Elemental Fusion.**  Every four Spirit skills the Four Elements gauge fills
  and Elemental Fusion fires automatically.
* **Jointstrike: Curse** (direct hit + the Spirit's coordinated-assault hit +
  the Curse damage-over-time), and the caster buffs / crit procs (Spirit Strike,
  Corrode, Element Unification, Consecutive Countercurrent).

Every damage number comes from ``data/global/classes/spiritmaster.json``; the
pet cadence and basic-attack size — which the client does not spell out — live
in :data:`TIMING` / :data:`ASSUME` so they are easy to tune against real logs.
"""
from __future__ import annotations

from ..sim.engine import EPS, Action
from .base import Build, ClassData
from .common import Kit, fallback_to_generic, ms, spec_options  # noqa: F401

SID = dict(
    COLD=16010000, COMB=16040000, FIRESP=16100000, WATERSP=16110000, CURSE=16140000,
    SCATTER=16340000, EARTHSP=16130000, DIMCTRL=16330000, WINDSP=16120000, SOULCRY=16070000,
    FUSION=16300000, DEFI=16200000,
    SSTRIKE=16710000, SPROT=16720000, SDESCENT=16730000, CORRODE=16740000, SREVITAL=16750000,
    MFOCUS=16760000, COUNTER=16800000, SCOMMUNION=16770000, REVITAL=16790000, EUNIFY=16780000,
    KAISINEL=16360000, MAGICBLK=16260000, JDESTRUCT=16240000, ENHANCE=16190000,
    ATERROR=16700000, SIPHON=16060000,
)

TIMING = {
    "cold_shock": 0.85, "combustion": 0.85, "jointstrike_curse": 0.95, "soul_cry": 0.95,
    "chain_followup": 0.55, "stigma": 1.00,
    "pet_skill_period": 3.0,      # the Spirit Skill Cooldown listed in the data
    "pet_swing": 1.8,             # Spirit basic-attack interval
}

ASSUME = {
    "spirit": "WATERSP",          # the single-target Spirit a DPS build keeps out
    "pet_basic_frac": 0.35,       # a Spirit basic attack vs its skill (not in the client data)
    "fusion_every": 4,            # Spirit skills per Four Elements -> Elemental Fusion
    "eunify_stacks": 5,           # Element Unification Critical Damage stacks maintained
    "crit_rate": 0.60,
    "chain_frac": 0.60,
}


def build_kit(build: Build, cd: ClassData, filler: str = "cold_shock") -> Kit:
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

    add_static("SSTRIKE", {0: ("amp_pve", 0.01), 2: ("perfect", 0.01)})   # Spirit Strike
    add_static("CORRODE", {0: ("crit", 1.0)})
    add_static("MFOCUS", {1: ("double", 0.01)})
    # Element Unification: +2% Critical Damage per Spirit skill, up to 5 stacks, kept up by the pet
    if lv("EUNIFY") > 0:
        ev = cd.vals(SID["EUNIFY"], lv("EUNIFY"))
        static["crit_dmg"] = static.get("crit_dmg", 0.0) + (ev[0] / 100.0) * ASSUME["eunify_stacks"]

    # --- the Spirit: a background damage stream -----------------------------
    spk = ASSUME["spirit"]
    sp_f, sp_c = (dmg(spk) if lv(spk) > 0 else (0.0, 0.0))
    dc_f, dc_c = (dmg("DIMCTRL") if lv("DIMCTRL") > 0 else (0.0, 0.0))
    fu_f, fu_c = (dmg("FUSION") if lv("FUSION") > 0 else (0.0, 0.0))
    pet = {"started": False, "fusion": 0}

    # crit procs / DoT-rider passives (hooks)
    corrode = _proc(cd, lv, "CORRODE", 1, 2, None)
    counter = _proc(cd, lv, "COUNTER", 0, 1, None)

    def start_pet(sim):
        if pet["started"] or sp_f <= 0:
            return
        pet["started"] = True
        period, swing = TIMING["pet_skill_period"], TIMING["pet_swing"]
        base_f, base_c = sp_f * ASSUME["pet_basic_frac"], sp_c * ASSUME["pet_basic_frac"]

        def pet_skill(t):
            if t > sim.cfg.duration + EPS:
                return
            sim.hit("Spirit Skill", sp_f, sp_c, element="water")
            if dc_f:
                sim.hit("Dimensional Control", dc_f, dc_c)
            pet["fusion"] += 1
            if fu_f and pet["fusion"] >= ASSUME["fusion_every"]:
                pet["fusion"] = 0
                sim.hit("Elemental Fusion", fu_f, fu_c)
            sim.schedule(t + period, lambda tt=t + period: pet_skill(tt))

        def pet_basic(t):
            if t > sim.cfg.duration + EPS:
                return
            sim.hit("Spirit (basic)", base_f, base_c, element="water")
            sim.schedule(t + swing, lambda tt=t + swing: pet_basic(tt))
        sim.schedule(period, lambda: pet_skill(period))
        sim.schedule(swing, lambda: pet_basic(swing))

    def hook(sim, t, info):
        start_pet(sim)                 # the Spirit is out from the opener
        if "proc" in info["tags"] or "dot" in info["tags"]:
            return
        if corrode and sim.proc("corrode", corrode[0] * ASSUME["crit_rate"], 1.0, t):
            sim.hit("Corrode", corrode[1], corrode[2], tags=("proc",))
        if counter and sim.has_debuff("curse", t) and sim.proc("countercurrent", counter[0], 1.0, t):
            sim.hit("Consecutive Countercurrent", counter[1], counter[2], tags=("proc",))

    # ----------------------------------------------------------------- actives
    cs_f, cs_c = dmg("COLD")

    def cold_cast(sim, a):
        mods = {"multihit": 0.5} if has("COLD", 3) else None
        sim.hit("Cold Shock", cs_f, cs_c, element="water", mods=mods)
        sim.gain_mp(100 * (1.2 if has("COLD", 1) else 1.0))
    A["cold_shock"] = Action("cold_shock", "Cold Shock", SID["COLD"], TIMING["cold_shock"],
                             element="water", on_cast=cold_cast, is_filler=True)

    cm_f, cm_c = dmg("COMB")

    def comb_cast(sim, a):
        sim.hit("Combustion", cm_f, cm_c, element="fire", mult=1.12 if has("COMB", 2) else 1.0)
        if has("COMB", 5):
            k = ASSUME["chain_frac"]
            sim.hit("Ashy Call", cm_f * k, cm_c * k, element="fire", delay=TIMING["chain_followup"])
    A["combustion"] = Action("combustion", "Combustion", SID["COMB"], TIMING["combustion"],
                             element="fire", skill_speed=0.2 if has("COMB", 4) else 0.0,
                             on_cast=comb_cast, is_filler=True)

    # Jointstrike: Curse (hit + Spirit coordinated-assault hit + Curse DoT)
    jv = cd.vals(SID["CURSE"], max(1, lv("CURSE")))
    jc_f, jc_c = float(jv[0][0]), float(jv[0][1]) / 100.0
    curse_dur = ms(jv[4]) if len(jv) > 4 and isinstance(jv[4], dict) else 5.0
    cu_f = float(jv[2][0]) / max(1.0, curse_dur)        # client value is the total; spread per tick
    cu_c = float(jv[2][1]) / 100.0 / max(1.0, curse_dur)
    join_f, join_c = (float(jv[7][0]), float(jv[7][1]) / 100.0) if len(jv) > 7 and isinstance(jv[7], list) else (0.0, 0.0)

    def curse_cast(sim, a):
        tags = ("crit", "noparry") if has("CURSE", 5) else ()
        mods = {"multihit": 0.5} if has("CURSE", 2) else None
        sim.hit("Jointstrike: Curse", jc_f, jc_c, tags=tags, mods=mods)
        if join_f:
            sim.hit("Jointstrike: Curse (Spirit)", join_f, join_c, element="water")
        sim.dot("curse", "Curse", cu_f, cu_c, 1.0, curse_dur)
    A["jointstrike_curse"] = Action("jointstrike_curse", "Jointstrike: Curse", SID["CURSE"],
                                    TIMING["jointstrike_curse"], cooldown=cd.cd(SID["CURSE"], lv("CURSE")) - (2 if has("CURSE", 4) else 0),
                                    mp=cd.mp(SID["CURSE"], lv("CURSE")), on_cast=curse_cast)

    sc_f, sc_c = dmg("SOULCRY")

    def soulcry_cast(sim, a):
        mods = {"multihit": 0.5} if has("SOULCRY", 1) else None
        sim.hit("Soul's Cry", sc_f, sc_c, mods=mods)
    A["soul_cry"] = Action("soul_cry", "Soul's Cry", SID["SOULCRY"], TIMING["soul_cry"],
                           cooldown=cd.cd(SID["SOULCRY"], lv("SOULCRY")) - (10 if has("SOULCRY", 4) else 0),
                           mp=cd.mp(SID["SOULCRY"], lv("SOULCRY")), on_cast=soulcry_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, stig, st, notes)

    policy = _policy(A, filler)
    # The Spirit stream (summons), Dimensional Control and Elemental Fusion are
    # accounted for in the pet loop, so the generic reading must not re-add them.
    pet_ids = {SID[k] for k in ("FIRESP", "WATERSP", "EARTHSP", "WINDSP", "DIMCTRL", "FUSION")}
    fallback_to_generic(A, policy, build, cd, notes, exclude=pet_ids)
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L)


def _proc(cd, lv, key, chance_idx, dmg_idx, icd_idx):
    if lv(key) <= 0:
        return None
    v = cd.vals(SID[key], lv(key))
    icd = ms(v[icd_idx]) if icd_idx is not None and icd_idx < len(v) else 1.0
    return (float(v[chance_idx]) / 100.0, float(v[dmg_idx][0]), float(v[dmg_idx][1]) / 100.0, icd)


def _build_stigmas(A, build, cd, stig, st, notes):
    def sdmg(key, idx=0):
        v = cd.vals(SID[key], build.stigmas[SID[key]])
        f, c = v[idx]
        return float(f), float(c) / 100.0

    # Enhance: Spirit's Benediction — +PvE Damage Boost
    if stig("ENHANCE"):
        ev = cd.vals(SID["ENHANCE"], build.stigmas[SID["ENHANCE"]])
        amp = ev[0] / 100.0 + (0.25 if st("ENHANCE", 20) else 0.0)
        A["enhance"] = Action("enhance", cd.skills[SID["ENHANCE"]]["name"], SID["ENHANCE"], TIMING["stigma"],
                             cooldown=cd.cd(SID["ENHANCE"], build.stigmas[SID["ENHANCE"]]),
                             on_cast=lambda sim, a, s=amp: sim.buff("enhance", 10.0, {"amp": s}))

    for key in ("SIPHON", "MAGICBLK", "JDESTRUCT", "ATERROR"):
        if not stig(key):
            continue
        akey = key.lower()
        # Jointstrike: Destructive Attack bundles its own hit with the Water spirit-join hit
        f, c = sdmg(key)
        join = sdmg(key, 2) if key == "JDESTRUCT" else None   # Water idx for the coordinated assault

        def nuke(sim, a, key=key, f=f, c=c, join=join):
            tags = ("crit",) if (key == "JDESTRUCT" and st("JDESTRUCT", 15)) else ()
            sim.hit(a.name, f, c, tags=tags)
            if join:
                sim.hit(a.name + " (Spirit)", join[0], join[1], element="water")
            if key == "ATERROR" and st("ATERROR", 5):
                sim.buff("assault_terror", 5.0, {"attack_pct": 0.20})
        A[akey] = Action(akey, cd.skills[SID[key]]["name"], SID[key], TIMING["stigma"],
                         cooldown=cd.cd(SID[key], build.stigmas[SID[key]]),
                         mp=cd.mp(SID[key], build.stigmas[SID[key]]),
                         skill_speed=0.2 if (key == "SIPHON" and st("SIPHON", 5)) else 0.0, on_cast=nuke)


def _policy(actions: dict, filler: str) -> list:
    order = ["enhance", "siphon", "magicblk", "jdestruct", "aterror", "jointstrike_curse",
             "soul_cry", "combustion"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
