"""Turn an official character profile into an aion2calc Build + loadout.

* skill levels: the profile shows totals; skill points = total − Daevanion
  levels − gear skill rolls (arcana, accessories, armor)
* stigmas: the slotted ones (``equip == 1``) at their levels
* Daevanion: every open node (official node ids equal the planner's)
* stats: every equipped item's main stats (with enchant extras), random rolls
  and manastones; titles; wings; primary/deity totals from the profile
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..kit.base import Build, ClassData, stigma_points_to_reach
from ..model.character import LABEL_MAP, parse_bonus_text
from .official import CLASS_KEYS, key_of

#: official stat id -> (Stats field, scale for plain numbers); "%" values divide by 100
OFFICIAL_IDS = {
    "FixingDamage": ("attack", 1), "Critical": ("crit", 1), "CriticalDamage": ("crit_atk", 1),
    "AmplifyCriticalDamage": ("crit_dmg", 0.01), "AmplifyAllDamage": ("amp_all", 0.01),
    "PvEAmplifyDamage": ("amp_pve", 0.01), "BossAmplifyDamage": ("amp_boss", 0.01),
    "AmplifyWeaponDamage": ("weapon_amp", 0.01), "Perfect": ("perfect", 0.01), "Hard": ("double", 0.01),
    "DefensePierce": ("pen", 1), "CombatSpeed": ("combat_speed", 0.01), "CoolTimeDecrease": ("cdr", 0.01),
    "AdditionalHitRate": ("multihit", 0.01), "WeaponAccuracy": ("accuracy", 1), "Accuracy": ("accuracy", 1),
    "MPMax": ("mp_max", 1), "PvEFixingDamage": ("pve_atk", 1), "BossFixingDamage": ("boss_atk", 1),
    "FrontFixingDamage": ("front_atk", 1), "BackFixingDamage": ("back_atk", 1),
}
#: primary/deity totals on the profile (they already include gear and arcana)
PROFILE_STATS = {"STR": "might", "AGI": "precision", "Justice": "justice", "Freedom": "freedom",
                 "Illusion": "illusion", "Time": "time", "Destruction": "destruction", "Death": "death",
                 "Wisdom": "wisdom"}
#: these ids are part of the profile totals; counting them on items would double count
SKIP_ON_ITEMS = {"STR", "DEX", "INT", "CON", "AGI", "WIS", "Justice", "Freedom", "Illusion", "Life", "Time",
                 "Destruction", "Death", "Wisdom", "Destiny", "Space"}
WINGS = {"Ultimate Daeva Wings": {"accuracy": 40, "pen": 500}}
OWNED_TITLES_ESTIMATE = {"crit": 20, "accuracy": 30, "attack": 4}


def _num(v) -> tuple[float, bool]:
    s = str(v or "0")
    pct = "%" in s
    m = re.search(r"-?[\d,]*\.?\d+", s)
    return (float(m.group(0).replace(",", "")) if m else 0.0), pct


def stat_of(entry: dict) -> dict:
    """One official stat entry -> {field: value} (empty when it does not affect damage)."""
    sid, name = entry.get("id"), entry.get("name", "")
    if sid in SKIP_ON_ITEMS:
        return {}
    val, pct = _num(entry.get("value"))
    extra, _ = _num(entry.get("extra"))
    val += extra
    if sid in OFFICIAL_IDS:
        field, scale = OFFICIAL_IDS[sid]
    elif name in LABEL_MAP:
        field, scale = LABEL_MAP[name]
    else:
        return {}
    if pct:
        return {field: val / 100}
    return {field: val * scale}


@dataclass
class ImportedCharacter:
    key: str
    cls: str
    name: str
    server: str
    level: int
    combat_power: int
    build: Build
    loadout: dict
    systems: dict
    warnings: list = field(default_factory=list)

    def loadout_name(self) -> str:
        return "char_" + re.sub(r"[^a-z0-9]+", "_", f"{self.name}_{self.server}".lower()).strip("_")


def _add(dst: dict, src: dict) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def from_profile(ch: dict) -> ImportedCharacter:
    p = ch["profile"]
    cls = CLASS_KEYS.get(p.get("className"), (p.get("className") or "").lower())
    cd = ClassData(cls)
    warnings = []
    comps, systems = [], {"equipment": [], "arcana": [], "manastones": [], "titles": [], "skills": [],
                          "stigmas": [], "daevanion": {}, "pet": None, "wings": None, "profile_stats": {}}
    gear_bonus: dict[int, int] = {}

    for e in (ch.get("equipment") or {}).get("equipmentList", []):
        it = ch.get("items", {}).get(str(e["slotPos"])) or e
        slot = e.get("slotPosName", "")
        st: dict = {}
        for m in it.get("mainStats") or []:
            if m.get("id") == "WeaponFixingDamage" and slot == "MainHand":
                lo, _ = _num(m.get("minValue") or m.get("value"))
                hi, _ = _num(m.get("value"))
                ex, _ = _num(m.get("extra"))
                _add(st, {"weapon_min": lo, "weapon_max": hi + ex})
            elif m.get("id") == "WeaponFixingDamage":
                v, _ = _num(m.get("value"))
                ex, _ = _num(m.get("extra"))
                _add(st, {"attack": v + ex})
            else:
                _add(st, stat_of(m))
        rolls = [s for s in it.get("subStats") or []]
        for s in rolls:
            _add(st, stat_of(s))
        stones = it.get("magicStoneStat") or []
        for s in stones:
            _add(st, stat_of(s))
            systems["manastones"].append({"slot": slot, "name": s.get("name"), "value": s.get("value"),
                                          "grade": s.get("grade"), "icon": s.get("icon")})
        skills = [(x.get("name"), x.get("level", 1), x.get("id")) for x in it.get("subSkills") or []]
        for nm, lv, sid in skills:
            sk = cd.by_name.get(nm)
            if sk:
                gear_bonus[sk["id"]] = gear_bonus.get(sk["id"], 0) + lv
        row = {"slot": slot, "slot_pos": e.get("slotPos"), "id": e.get("id"), "name": e.get("name"),
               "grade": e.get("grade"), "enchant": e.get("enchantLevel"), "icon": e.get("icon"),
               "stats": st, "rolls": [(s.get("name"), s.get("value")) for s in rolls],
               "manastones": [(s.get("name"), s.get("value")) for s in stones],
               "theostones": [g.get("name") for g in it.get("godStoneStat") or []],
               "skills": [(nm, lv) for nm, lv, _ in skills], "error": it.get("error")}
        (systems["arcana"] if slot.startswith("Arcana") else systems["equipment"]).append(row)
        if it.get("error"):
            warnings.append(f"{slot}: item details unavailable ({it['error'][:60]})")
        comps.append({"slot": slot, "item": f"{e.get('name')} +{e.get('enchantLevel', 0)}", "stats": st})

    # titles (equipped bonus) + an estimate for the collection bonus of owned titles
    for t in (ch.get("title") or {}).get("titleList", []):
        if not t.get("name"):
            continue
        st = {}
        for d in t.get("equipStatList") or []:
            _add(st, parse_bonus_text(d.get("desc", "")))
        systems["titles"].append({"slot": t.get("equipCategory"), "name": t.get("name"), "grade": t.get("grade"),
                                  "equip": [d.get("desc") for d in t.get("equipStatList") or []], "stats": st})
        comps.append({"slot": f"Title ({t.get('equipCategory')})", "item": t["name"], "stats": st})
    comps.append({"slot": "Owned titles", "item": "collection bonus (estimate)", "stats": OWNED_TITLES_ESTIMATE})
    warnings.append("owned-title collection bonus is estimated (the profile lists only equipped titles)")

    pw = ch.get("petwing") or {}
    wing = (pw.get("wing") or {}).get("name")
    systems["wings"], systems["pet"] = pw.get("wing"), pw.get("pet")
    if wing:
        st = WINGS.get(wing, {})
        if not st:
            warnings.append(f"wing stats unknown for {wing}; not counted")
        comps.append({"slot": "Wings", "item": wing, "stats": st})

    prof = {}
    for s in (ch.get("stat") or {}).get("statList", []):
        systems["profile_stats"][s.get("type")] = {"name": s.get("name"), "value": s.get("value"),
                                                   "effects": s.get("statSecondList")}
        if s.get("type") in PROFILE_STATS:
            prof[PROFILE_STATS[s["type"]]] = s.get("value", 0)
    comps.append({"slot": "Primary/deity stats", "item": "official profile totals", "stats": prof})
    if gear_bonus:
        comps.append({"slot": "Gear skill rolls", "item": "arcana, accessories and armor skill options",
                      "stats": {"skill_bonus": {str(k): v for k, v in gear_bonus.items()}}})

    # Daevanion nodes and the levels they give
    nodes = set()
    for bid, det in (ch.get("daevanion_detail") or {}).items():
        open_nodes = [n["nodeId"] for n in det.get("nodeList", []) if n.get("open")]
        nodes |= {n for n in open_nodes if n in cd.node_index}
        systems["daevanion"][bid] = {"open": len(open_nodes),
                                     "stats": [x.get("desc") for x in det.get("openStatEffectList") or []],
                                     "skills": [x.get("desc") for x in det.get("openSkillEffectList") or []]}
    unknown = sum(1 for det in (ch.get("daevanion_detail") or {}).values()
                  for n in det.get("nodeList", []) if n.get("open") and n["nodeId"] not in cd.node_index)
    if unknown:
        warnings.append(f"{unknown} open Daevanion nodes are not in the planner data (sync may be behind)")
    dv = cd.daevanion_levels(nodes)

    b = Build(cls, level=p.get("characterLevel", 45))
    b.daevanion = nodes
    stig = []
    for s in (ch.get("skill") or {}).get("skillList", []):
        sk = cd.skills.get(s.get("id")) or cd.by_name.get(s.get("name"))
        total = s.get("skillLevel") or 0
        systems["skills"].append({"id": s.get("id"), "name": s.get("name"), "category": s.get("category"),
                                  "level": total, "slotted": bool(s.get("equip")), "icon": s.get("icon")})
        if not sk:
            if total:
                warnings.append(f"skill not in planner data: {s.get('name')}")
            continue
        if s.get("category") == "Dp":
            if s.get("equip") and total > 0:
                stig.append((sk["id"], total))
            continue
        if total <= 0:
            continue
        sp = total - dv.get(sk["id"], 0) - gear_bonus.get(sk["id"], 0)
        if sp > 1:
            b.sp[sk["id"]] = max(1, min(sk.get("buyMax", 10), sp))
    slots = cd.budget(b.level)["slots"]
    b.stigmas = dict(sorted(stig, key=lambda kv: -kv[1])[:slots])
    systems["stigmas"] = [{"id": k, "name": cd.skills[k]["name"], "level": v} for k, v in b.stigmas.items()]
    lvl_sp = cd.budget(b.level)["skill"]
    if b.sp_spent() > lvl_sp:
        warnings.append(f"{b.sp_spent()} skill points spent: {lvl_sp} from levels + {b.sp_spent() - lvl_sp} "
                        "from Wisdom Stones (Empyrean Traces); the optimizer uses the same total")
    if b.stigma_spent() > cd.budget(b.level)["stigma"] + 1:
        warnings.append(f"stigma levels cost {b.stigma_spent()} points (> budget)")

    loadout = {"name": f"{p.get('characterName')} ({p.get('serverName')}) - official profile",
               "level": p.get("characterLevel", 45),
               "notes": ["Imported from the official AION 2 character page.", *warnings],
               "components": comps}
    imp = ImportedCharacter(
        key=key_of(ch.get("region", "nae"), p.get("serverId"), p.get("characterId")), cls=cls,
        name=p.get("characterName"), server=p.get("serverName"), level=p.get("characterLevel"),
        combat_power=p.get("combatPower"), build=b, loadout=loadout, systems=systems, warnings=warnings)
    systems["summary"] = {"sp_spent": b.sp_spent(), "stigma_spent": b.stigma_spent(),
                          "daevanion_cost": b.daevanion_cost(cd), "stigma_cost_check": stigma_points_to_reach}
    systems["summary"].pop("stigma_cost_check")
    return imp
