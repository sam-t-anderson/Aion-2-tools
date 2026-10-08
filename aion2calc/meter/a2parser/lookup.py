"""Localized names and class inference backed by the upstream game tables."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

CLASS_PREFIXES = {
    11: "Gladiator", 12: "Templar", 13: "Assassin", 14: "Ranger",
    15: "Sorcerer", 16: "Elementalist", 17: "Cleric", 18: "Chanter", 19: "Fighter",
}
ROSTER_CLASSES = ((5, 8, "Gladiator"), (9, 12, "Templar"), (13, 16, "Ranger"),
                  (17, 20, "Assassin"), (21, 24, "Elementalist"), (25, 28, "Sorcerer"),
                  (29, 32, "Cleric"), (33, 36, "Chanter"))


@lru_cache(maxsize=32)
def _table(category: str, locale: str):
    resource = files(__package__).joinpath("data", "i18n", category, f"{locale}.json")
    try:
        return json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError):
        return {}


def skill_name(skill_id: int, locale: str = "en") -> str:
    return _table("skills", locale).get(str(skill_id), f"Skill {skill_id}")


def has_skill(skill_id: int, locale: str = "en") -> bool:
    return str(skill_id) in _table("skills", locale)


def normalize_skill(skill_id: int, locale: str = "en") -> int:
    if 30_000_000 <= skill_id <= 30_999_999:
        return skill_id
    base = skill_id - skill_id % 10_000
    base_name = _table("skills", locale).get(str(base), "")
    raw_name = _table("skills", locale).get(str(skill_id), "")
    if not base_name:
        return skill_id
    if not raw_name:
        return base
    return skill_id if raw_name != base_name else base


def decode_spec_flags(raw_skill_id: int) -> tuple[bool, bool, bool, bool, bool]:
    flags = [False] * 5
    if 30_000_000 <= raw_skill_id <= 30_999_999:
        return tuple(flags)
    suffix = (raw_skill_id % 10_000) // 10
    if suffix <= 0:
        return tuple(flags)
    while suffix:
        slot = suffix % 10
        if not 1 <= slot <= 5:
            return (False, False, False, False, False)
        flags[slot - 1] = True
        suffix //= 10
    return tuple(flags)


def npc_info(mob_code: int, locale: str = "en") -> dict:
    info = _table("npcs", locale).get(str(mob_code), {})
    if not isinstance(info, dict):
        return {}
    portrait = _table("npc-portraits", "en").get(str(mob_code), {})
    return {**info, "icon": portrait["icon"]} if portrait.get("icon") else info


def npc_name(mob_code: int, locale: str = "en") -> str:
    return npc_info(mob_code, locale).get("name", f"#{mob_code}")


def job_from_roster(value: int) -> str | None:
    return next((name for low, high, name in ROSTER_CLASSES if low <= value <= high), None)


def job_from_skill(skill_code: int, *, loose: bool = False) -> str | None:
    if 100_510 <= skill_code <= 103_500 or 109_300 <= skill_code <= 109_362:
        return "Elementalist"
    if not 10_000_000 <= skill_code <= 19_999_999:
        return None
    prefix = skill_code // 1_000_000
    sub = skill_code // 10_000 % 100
    if sub == 0:
        if prefix == 16 and 11 <= skill_code // 100 % 100 <= 13:
            return "Elementalist"
        return None
    if prefix == 16 and not loose and sub not in {
        1, 2, 3, 4, 5, 6, 7, 8, 14, 15, 17, 19, 21, 22, 23, 24, 25, 26,
        30, 31, 32, 34, 35, 36, 37, 70, 71, 72, 73, 74, 75, 76, 80,
    }:
        return None
    return CLASS_PREFIXES.get(prefix)
