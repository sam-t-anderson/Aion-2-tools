"""Spiritmaster kit built from the global client's skill tables.

The Spiritmaster's damage is half pet, and the generic tooltip model sees none
of the pet.  This kit adds:

* **The summon cycle.**  The four summons are pressed on cooldown.  Each brings
  its Spirit, which uses its skill on arrival and, while it stays, again on the
  Spirit Skill Cooldown; the Spirits' basic attacks are small.  How many skill
  uses and basic attacks a summon yields is measured from recorded fights.
* **Dimensional Control and Elemental Fusion as presses.**  Every Spirit skill
  opens Dimensional Control for about a second and adds an element; four
  elements grant Four Elements, which Elemental Fusion spends.  Both are pressed
  by the caster, so their action time is charged (0.2.309; before, they fired
  on their own and the time went to Combustion).
* **The Ancient Spirit** (stigma): 30 s of basic attacks, its skill every seventh
  one, each skill granting Four Elements.
* **Jointstrike: Curse** (direct hit + the Spirit's coordinated-assault hit +
  the Curse damage-over-time), and the caster buffs / procs (Spirit Strike,
  Corrode, Element Unification, Consecutive Countercurrent, Spirit's Descent).
  The caster's procs fire on the caster's own hits, not the Spirits'.

Every damage number comes from ``data/global/classes/spiritmaster.json``; the
pet cadence and basic-attack size — which the client does not spell out — live
in :data:`TIMING` / :data:`ASSUME` so they are easy to tune against real logs.
"""
from __future__ import annotations

from ..sim.engine import EPS, Action
from .base import Build, ClassData
from .common import Kit, add_weave, fallback_to_generic, ms, spec_options  # noqa: F401

__all__ = ["build_kit", "spec_options"]

SID = dict(
    COLD=16010000, COMB=16040000, FIRESP=16100000, WATERSP=16110000, CURSE=16140000,
    SCATTER=16340000, EARTHSP=16130000, DIMCTRL=16330000, WINDSP=16120000, SOULCRY=16070000,
    FUSION=16300000, DEFI=16200000,
    SSTRIKE=16710000, SPROT=16720000, SDESCENT=16730000, CORRODE=16740000, SREVITAL=16750000,
    MFOCUS=16760000, COUNTER=16800000, SCOMMUNION=16770000, REVITAL=16790000, EUNIFY=16780000,
    KAISINEL=16360000, MAGICBLK=16260000, JDESTRUCT=16240000, ENHANCE=16190000,
    ATERROR=16700000, SIPHON=16060000, ANCIENT=16250000,
)

#: Action time in seconds at 0% Combat Speed.  Combustion, Jointstrike: Curse (0.2.307), the summons,
#: Dimensional Control and Elemental Fusion (0.2.309) are measured from recorded casts (docs/methodology.md
#: "Measured action times"); the rest keep their estimates: the captures only weave Cold Shock between
#: skills, and Soul's Cry and the stigmas have too few presses.
TIMING = {
    "cold_shock": 0.85, "combustion": 0.50, "jointstrike_curse": 0.46, "soul_cry": 0.95,
    "chain_followup": 0.55, "stigma": 1.00,
    "summon": 0.24, "dimensional_control": 0.36, "elemental_fusion": 0.34,
    "spirit_arrival": 0.30,       # summon press -> the Spirit uses its skill (recorded pet casts)
    "dc_window": 1.0,             # how long a Spirit skill keeps Dimensional Control usable (recorded:
                                  #   97% of presses within 1 s of a Spirit skill)
    "pet_skill_period": 3.0,      # the Spirit Skill Cooldown listed in the data
    "pet_swing": 0.5,             # a Spirit's basic-attack interval (recorded)
    "ancient_swing": 1.4,         # the Ancient Spirit's basic attacks spread over its 30 s (recorded: 21)
}

ASSUME = {
    # Per summon, recorded in two Spiritmasters' boss fights (0.2.309): the Spirit's skill uses after its
    # arrival skill (the Fire and Earth Spirits stay and keep casting; Water and Wind rarely do) ...
    "follow_ups": {"FIRESP": 1.8, "EARTHSP": 1.35, "WINDSP": 0.5, "WATERSP": 0.15},
    # ... and its basic attacks.
    "basics": {"FIRESP": 3.3, "EARTHSP": 1.9, "WINDSP": 2.3, "WATERSP": 0.85},
    "pet_basic_frac": 0.10,       # a Spirit basic attack vs its skill hit (recorded 0.06-0.15; was 0.35)
    "ancient_basic_frac": 0.19,   # an Ancient Spirit basic attack vs its skill hit (recorded 0.18-0.20)
    "dc_delayed_frac": 0.36,      # Dimensional Control "Extra damage after 3s" vs its hit (recorded 0.35-0.38)
    "fusion_delayed_frac": 0.24,  # Elemental Fusion "Extra damage after 3s" vs its hit (recorded 0.23-0.25)
    "fusion_every": 4,            # Spirit skills per Four Elements -> Elemental Fusion
    "eunify_stacks": 5,           # Element Unification Critical Damage stacks maintained
    "ancient_duration": 30.0,     # Ancient Spirit stigma: a 30s window of a much stronger pet
    "crit_rate": 0.60,
    "chain_frac": 1.5,            # Ashy Call (Combustion chain); community L45 parses put detected
                                  #   chains at ~1.4-1.9x, so 1.5 (was 0.60) class-wide
}

#: The basic-attack chain's three steps (name, share of the woven steps, damage per press against
#: the first step), the woven steps after each press and after any press recorded too rarely (the
#: median of the per-skill rates), from the recorded fights (0.2.309; docs/methodology.md "Woven
#: basic attacks").
WEAVE = {
    "steps": (("Cold Shock", 0.44, 1.00), ("Vacuum Explosion", 0.32, 1.29), ("Earth Tremor", 0.24, 1.45)),
    "after": {"combustion": 0.34, "dimensional_control": 0.09, "elemental_fusion": 0.0, "jointstrike_curse": 0.06,
              "summon_fire": 0.0, "summon_earth": 0.03, "summon_water": 0.0, "summon_wind": 0.0},
    "per_press": 0.02,
}

#: The four summons: kit key, Spirit name, element.
SPIRITS = (("FIRESP", "Fire", "fire"), ("EARTHSP", "Earth", "earth"), ("WATERSP", "Water", "water"),
           ("WINDSP", "Wind", "wind"))
#: Four Elements stays until Elemental Fusion spends it.
_HELD = 1.0e6


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

    # --- the Spirits ------------------------------------------------------------
    dc_f, dc_c = (dmg("DIMCTRL") if lv("DIMCTRL") > 0 else (0.0, 0.0))
    fu_f, fu_c = (dmg("FUSION") if lv("FUSION") > 0 else (0.0, 0.0))
    # Ancient Spirit (stigma) is the real endgame pet: a much stronger summon for 30s.
    anc_f = anc_c = 0.0
    anc_mult = 1.0
    if stig("ANCIENT"):
        av = cd.vals(SID["ANCIENT"], build.stigmas[SID["ANCIENT"]])
        anc_f, anc_c = float(av[0][0]), float(av[0][1]) / 100.0
        anc_mult = (1.1 if st("ANCIENT", 5) else 1.0) * (1.2 if st("ANCIENT", 20) else 1.0)

    # crit procs / DoT-rider passives (hooks)
    corrode = _proc(cd, lv, "CORRODE", 1, 2, None)
    counter = _proc(cd, lv, "COUNTER", 0, 1, None)
    descent = _proc(cd, lv, "SDESCENT", 0, 1, None)

    def spirit_skill(sim, four=False):
        """A Spirit used its skill: Dimensional Control opens briefly and an element is gained (the
        Ancient Spirit grants Four Elements outright); none is gained while Four Elements is up."""
        if dc_f:
            sim.buff("dc_window", TIMING["dc_window"])
        if not fu_f or sim.has_buff("four_elements"):
            return
        pet = sim.kit_state.setdefault("spiritmaster_pet", {"elements": 0})
        pet["elements"] = ASSUME["fusion_every"] if four else pet["elements"] + 1
        if pet["elements"] >= ASSUME["fusion_every"]:
            pet["elements"] = 0
            sim.buff("four_elements", _HELD)

    def descend(sim, seconds):
        # Spirit's Descent: the caster's hits can proc it for 10 s after a summon (30 s after the Ancient's)
        cur = sim.buffs.get("spirit_descent")
        if cur is None or cur.until < sim.t + seconds:
            sim.buff("spirit_descent", seconds)

    def hook(sim, t, info):
        if {"proc", "dot", "pet"} & set(info["tags"]):
            return
        if corrode and sim.proc("corrode", corrode[0] * ASSUME["crit_rate"], 1.0, t):
            sim.hit("Corrode", corrode[1], corrode[2], tags=("proc",))
        if counter and sim.has_debuff("curse", t) and sim.proc("countercurrent", counter[0], 1.0, t):
            sim.hit("Consecutive Countercurrent", counter[1], counter[2], tags=("proc",))
        if descent and sim.has_buff("spirit_descent", t):
            boost = 1.5 if sim.has_buff("descent_boost", t) else 1.0     # Ancient Spirit level 10
            if sim.proc("descent", min(1.0, descent[0] * boost), 1.0, t):
                sim.hit("Spirit's Descent", descent[1], descent[2], mult=boost, tags=("proc",))

    def summon_action(key, label, element):
        f, c = dmg(key)
        if key == "WATERSP" and has(key, 2):
            c *= 1.1                                  # +10% Water Spirit Attack
        mods = {"crit_dmg": 0.2} if key == "FIRESP" and has(key, 2) else None
        name, period = cd.skills[SID[key]]["name"], TIMING["pet_skill_period"]
        follow, basics = ASSUME["follow_ups"][key], ASSUME["basics"][key]
        kb = ASSUME["pet_basic_frac"] * basics

        def use(sim):
            sim.hit(name, f, c, element=element, tags=("pet",), mods=mods)
            spirit_skill(sim)

        def maybe_use(sim, frac):
            if sim.proc(f"{key.lower()}_follow_up", frac, 0.0, sim.t):
                use(sim)

        def summon_cast(sim, a):
            t0 = sim.t + TIMING["spirit_arrival"]
            descend(sim, 10.0)
            sim.schedule(t0, lambda: use(sim))
            whole = int(follow)
            for i in range(1, whole + 1):
                sim.schedule(t0 + i * period, lambda: use(sim))
            if follow > whole:
                sim.schedule(t0 + (whole + 1) * period, lambda: maybe_use(sim, follow - whole))
            if kb:
                n = max(1, round(basics))
                sim.hit(f"{label} Spirit (basic)", f * kb, c * kb, element=element, tags=("pet",), mods=mods,
                        n=n, spread=TIMING["pet_swing"] * (n - 1), delay=TIMING["spirit_arrival"] + TIMING["pet_swing"])
        return Action(f"summon_{label.lower()}", name, SID[key], TIMING["summon"],
                      cooldown=cd.cd(SID[key], lv(key)), mp=cd.mp(SID[key], lv(key)) * (0.5 if has(key, 1) else 1.0),
                      element=element, on_cast=summon_cast)

    for key, label, element in SPIRITS:
        if lv(key) > 0:
            A[f"summon_{label.lower()}"] = summon_action(key, label, element)

    if dc_f:
        dc_mods = {"multihit": 0.5} if has("DIMCTRL", 3) else None

        def dc_cast(sim, a):
            sim.buff("dc_window", 0.0)                    # spent
            sim.hit("Dimensional Control", dc_f, dc_c, mods=dc_mods)
            if has("DIMCTRL", 2):
                k = ASSUME["dc_delayed_frac"]
                sim.hit("Dimensional Control (delayed)", dc_f * k, dc_c * k, delay=3.0)
            sim.gain_mp(100)
        A["dimensional_control"] = Action("dimensional_control", "Dimensional Control", SID["DIMCTRL"],
                                          TIMING["dimensional_control"], requires=("dc_window",), on_cast=dc_cast)

    if fu_f:
        def fusion_cast(sim, a):
            sim.buff("four_elements", 0.0)                # spent
            sim.hit("Elemental Fusion", fu_f, fu_c)
            if has("FUSION", 2):
                k = ASSUME["fusion_delayed_frac"]
                sim.hit("Elemental Fusion (delayed)", fu_f * k, fu_c * k, delay=3.0)
            if has("FUSION", 5) and sim.proc("four_elements_regain", 0.25, 0.0, sim.t):
                sim.buff("four_elements", _HELD)
        A["elemental_fusion"] = Action("elemental_fusion", "Elemental Fusion", SID["FUSION"],
                                       TIMING["elemental_fusion"], requires=("four_elements",), on_cast=fusion_cast)

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
            sim.hit("Jointstrike: Curse (Spirit)", join_f, join_c, element="water", tags=("pet",))
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

    # Ancient Spirit (stigma): 30 s of basic attacks with its skill every seventh (fifth at level 15);
    # each skill grants Four Elements.
    if stig("ANCIENT"):
        every = 5 if st("ANCIENT", 15) else 7
        kb = ASSUME["ancient_basic_frac"]

        def ancient_skill(sim, name):
            sim.hit(name, anc_f, anc_c, mult=anc_mult, tags=("pet",))
            spirit_skill(sim, four=True)

        def ancient_basic(sim, i, end):
            if sim.t > end + EPS:
                return
            sim.hit("Ancient Spirit (basic)", anc_f * kb, anc_c * kb, mult=anc_mult, tags=("pet",))
            if i % every == 0:
                ancient_skill(sim, "Ancient Spirit Skill")
            sim.schedule(sim.t + TIMING["ancient_swing"], lambda: ancient_basic(sim, i + 1, end))

        def ancient_cast(sim, a):
            t0, end = sim.t + TIMING["spirit_arrival"], sim.t + ASSUME["ancient_duration"]
            descend(sim, ASSUME["ancient_duration"])
            if st("ANCIENT", 10):
                sim.buff("descent_boost", ASSUME["ancient_duration"])
            sim.schedule(t0, lambda: ancient_skill(sim, a.name))
            sim.schedule(t0 + TIMING["ancient_swing"], lambda: ancient_basic(sim, 1, end))
        A["ancient_spirit"] = Action("ancient_spirit", cd.skills[SID["ANCIENT"]]["name"], SID["ANCIENT"],
                                     TIMING["stigma"], cooldown=cd.cd(SID["ANCIENT"], build.stigmas[SID["ANCIENT"]]),
                                     mp=cd.mp(SID["ANCIENT"], build.stigmas[SID["ANCIENT"]]), on_cast=ancient_cast)

    # ------------------------------------------------------------- stigmas
    _build_stigmas(A, build, cd, stig, st, notes)

    policy = _policy(A, filler)
    # The summons, Dimensional Control, Elemental Fusion and the Ancient Spirit are modelled above
    # (an unlevelled one is left out on purpose); the generic reading must not re-add them.
    pet_ids = {SID[k] for k in ("FIRESP", "WATERSP", "EARTHSP", "WINDSP", "DIMCTRL", "FUSION", "ANCIENT")}
    fallback_to_generic(A, policy, build, cd, notes, exclude=pet_ids)
    add_weave(A, WEAVE, cs_f, cs_c, mp=100 * (1.2 if has("COLD", 1) else 1.0), element="water", skip=("cold_shock",))
    essential = tuple(k for k in policy if k == "dimensional_control" or k == "elemental_fusion"
                      or k.startswith("summon_"))
    return Kit(actions=A, hooks=[hook], cond_mods=[], static=static, policy=policy,
               filler=filler, notes=notes, levels=L, essential=essential)


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
    # Dimensional Control's window is brief and an element is lost while Four Elements waits, so both
    # come before the summons that feed them.
    order = ["ancient_spirit", "enhance", "siphon", "magicblk", "jdestruct", "aterror",
             "dimensional_control", "elemental_fusion", "summon_fire", "summon_earth", "summon_water",
             "summon_wind", "jointstrike_curse", "soul_cry", "combustion"]
    pol = [k for k in order if k in actions]
    pol.append(filler)
    return pol
