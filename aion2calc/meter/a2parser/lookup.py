"""Localized names and class inference backed by the upstream game tables."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

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


@lru_cache(maxsize=1)
def _npc_overrides() -> dict:
    """Verified local corrections to the upstream NPC catalog (boss/role flags),
    kept outside the generated tables so a catalog refresh does not re-introduce
    a fixed error. Keyed by mob code string; each value's fields merge over the
    catalog record (e.g. ``isBoss`` false for an NPC that is a miniboss, not the
    encounter's boss)."""
    resource = files(__package__).joinpath("data", "npc_role_overrides.json")
    try:
        doc = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return {}
    overrides = doc.get("overrides") if isinstance(doc, dict) else None
    return overrides if isinstance(overrides, dict) else {}


# ---------------------------------------------------------- community portraits
#
# A *fallback* portrait overlay behind the curated bundled table: the NPC id ->
# image map scraped by the log server's `aion2logs portraits` job (its
# ``npc-portraits-community.json``). It is community-sourced and name/id-matched,
# not an official or id-verified mapping, so it is only consulted for NPCs the
# bundled table has no art for, and never overrides a curated portrait. The file
# lives on the server (or a client cache); its path is registered by the host or
# read from the ``A2_COMMUNITY_PORTRAITS`` environment variable. Absent/malformed
# files degrade silently to no overlay, so importing or calling this never fails.

_COMMUNITY_PORTRAITS_PATH: str | None = None
_community_cache: dict[str, tuple[float, dict]] = {}


def set_community_portraits(path: str | os.PathLike | None) -> None:
    """Point :func:`npc_info` at a community portrait overlay file (the server's
    scraped ``npc-portraits-community.json``), or ``None`` to clear it. The host
    (the log server) calls this at startup with its data-dir file."""
    global _COMMUNITY_PORTRAITS_PATH
    _COMMUNITY_PORTRAITS_PATH = str(path) if path else None
    _community_cache.clear()


def _community_portraits() -> dict:
    """``{mob_code: icon_url}`` from the configured community overlay file, or
    ``{}``. Cached and transparently re-read when the file's mtime changes (the
    offline scraper rewrites it), and never raises — a missing or malformed file
    simply yields no overlay. Accepts either the scraper envelope
    (``{"portraits": {id: {"icon": ...}}}``) or a flat ``{id: url}`` map."""
    path = _COMMUNITY_PORTRAITS_PATH or os.environ.get("A2_COMMUNITY_PORTRAITS") or None
    if not path:
        return {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        _community_cache.pop(path, None)
        return {}
    cached = _community_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = doc.get("portraits") if isinstance(doc, dict) and "portraits" in doc else doc
    out: dict[str, str] = {}
    if isinstance(rows, dict):
        for code, row in rows.items():
            icon = row.get("icon") if isinstance(row, dict) else row
            if isinstance(icon, str) and icon:
                out[str(code)] = icon
    _community_cache[path] = (mtime, out)
    return out


def npc_info(mob_code: int, locale: str = "en") -> dict:
    info = _table("npcs", locale).get(str(mob_code), {})
    if not isinstance(info, dict):
        info = {}
    override = _npc_overrides().get(str(mob_code))
    if isinstance(override, dict):
        info = {**info, **{k: v for k, v in override.items() if k not in ("source", "note")}}
    if not info:
        return {}
    portrait = _table("npc-portraits", "en").get(str(mob_code), {})
    icon = portrait.get("icon") if isinstance(portrait, dict) else None
    if not icon:                                  # fall back to the community overlay
        icon = _community_portraits().get(str(mob_code))
    return {**info, "icon": icon} if icon else info


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
