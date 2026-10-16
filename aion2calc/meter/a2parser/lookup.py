"""Localized names and class inference backed by the upstream game tables."""

from __future__ import annotations

import json
import os
import re
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


#: Skill families (id with the per-rank/spec suffix zeroed) known to only restore HP: the
#: cleric and chanter heals and heal procs seen in live recordings. A floor under the
#: data-driven set below, so these decode as healing even if the bundled class data is missing.
_KNOWN_HEAL_FAMILIES = frozenset({
    17090000,   # Light of Regeneration
    17100000,   # Healing Light
    17120000,   # Radiant Recovery
    17160000,   # Benevolence
    17290000,   # Absolution
    17800000,   # Radiant Benediction (passive: heals the party on landing an attack)
    18120000,   # Recuperation
    18170000,   # Healing Touch
    18420000,   # Guardian Blessing
})
_HEAL_TIP = re.compile(r"\b(?:restores?|recovers?|heals?|healing)\b.{0,80}\bHP\b|\bHP\b.{0,40}\b(?:restor|recover|heal)", re.I | re.S)
_DAMAGE_TIP = re.compile(r"\bdamage\b", re.I)


@lru_cache(maxsize=1)
def heal_skill_families() -> frozenset[int]:
    """Skill families whose only effect on a target is restoring HP (a cleric/chanter heal,
    a passive heal proc on the party), from the bundled class skill data: a skill whose
    description restores HP and never mentions dealing damage. Lifesteal / drain attacks
    describe their damage and stay damage. ``_KNOWN_HEAL_FAMILIES`` is always included."""
    families = set(_KNOWN_HEAL_FAMILIES)
    try:
        from ...paths import list_names, read_json
        for cls in list_names("global", "classes"):
            try:
                doc = read_json("global", "classes", f"{cls}.json")
            except Exception:
                continue
            for skill in (doc.get("skills") or []) if isinstance(doc, dict) else []:
                sid, tip = skill.get("id"), skill.get("tip")
                if (isinstance(sid, int) and not isinstance(sid, bool) and isinstance(tip, str)
                        and _HEAL_TIP.search(tip) and not _DAMAGE_TIP.search(tip)):
                    families.add(sid - sid % 10_000)
    except Exception:
        pass
    return frozenset(families)


def is_heal_skill(skill_code) -> bool:
    """Whether this skill only restores HP, so its effect on another entity is healing --
    never damage, and never a hostile (PvP) act -- whoever receives it."""
    try:
        code = int(skill_code)
    except (TypeError, ValueError):
        return False
    return (code - code % 10_000) in heal_skill_families()


#: A Spiritmaster's basic elemental spirits (one out at a time) vs the Ancient Spirit
#: (which can be out alongside a basic spirit). Their own attack skills are named
#: "<Element> Spirit: <skill>" in the game tables; that element decides the category.
_SPIRIT_BASIC_ELEMENTS = frozenset({"Fire", "Water", "Wind", "Earth"})


@lru_cache(maxsize=1)
def _spirit_skill_sets() -> tuple[frozenset[int], frozenset[int]]:
    """Skill IDs of a basic spirit's and the Ancient Spirit's own attacks, read once from the
    shipped English skill table. Classifying a summon by the IDs it attacks with is independent
    of the game client's locale (the IDs are numeric), unlike the summoned entity's name."""
    basic: set[int] = set()
    ancient: set[int] = set()
    for sid, name in _table("skills", "en").items():
        parts = name.split(" Spirit:", 1)   # the spirit's own attacks; "Summon:"/"Dismiss:" lack the colon
        if len(parts) != 2:
            continue
        element = parts[0].split()[-1]
        if element in _SPIRIT_BASIC_ELEMENTS:
            basic.add(int(sid))
        elif element == "Ancient":
            ancient.add(int(sid))
    return frozenset(basic), frozenset(ancient)


def spirit_skill_category(skill_id: int) -> str | None:
    """'basic' for a Fire/Water/Wind/Earth spirit's attack, 'ancient' for the Ancient Spirit's,
    or None for any other skill. Locale-independent (keys on the numeric skill ID)."""
    basic, ancient = _spirit_skill_sets()
    if skill_id in basic:
        return "basic"
    if skill_id in ancient:
        return "ancient"
    return None


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


@lru_cache(maxsize=1)
def _dungeon_final_bosses() -> dict:
    """Curated ``{dungeonId: frozenset(mob_code, …)}`` of each dungeon's final boss, read
    once from the shipped ``dungeon_final_bosses.json``. It lets the meter auto-mark a
    dungeon run complete (and rankable) when the party kills the final boss, without any
    manual ``final_boss_ids`` configuration. A missing or malformed file degrades to an
    empty map, so detection simply falls back to a manual designation and nothing breaks."""
    resource = files(__package__).joinpath("data", "dungeon_final_bosses.json")
    try:
        doc = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return {}
    raw = doc.get("final_bosses") if isinstance(doc, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: dict[int, frozenset] = {}
    def take(did, codes):
        try:
            key = int(did)
        except (TypeError, ValueError):
            return
        if key > 0 and key not in out and isinstance(codes, list):
            members = frozenset(c for c in codes if isinstance(c, int) and 0 < c <= 2**32 - 1)
            if members:
                out[key] = members
    for did, codes in raw.items():
        take(did, codes)
    # Tiers of a curated dungeon the catalog attributes no NPC to: their final boss is the sibling
    # tiers' final boss under its other tier codes (``derived_final_bosses``, each entry naming
    # the siblings and codes it was derived from). A curated entry always wins.
    derived = doc.get("derived_final_bosses")
    if isinstance(derived, dict):
        for did, entry in derived.items():
            if isinstance(entry, dict):
                take(did, entry.get("codes"))
    return out


def dungeon_final_bosses(dungeon_id: int) -> frozenset:
    """The curated final-boss mob codes for a catalog ``dungeonId`` (its HP-bar phases /
    variants), or an empty set when the dungeon is unknown or deliberately unmapped."""
    if not isinstance(dungeon_id, int) or dungeon_id <= 0:
        return frozenset()
    return _dungeon_final_bosses().get(dungeon_id, frozenset())


@lru_cache(maxsize=1)
def _servers_table() -> dict:
    """The bundled ``serverId -> {locale: world name}`` table, read once. Used only as a fallback
    for the world/server name when the live official metadata source did not carry it."""
    resource = files(__package__).joinpath("data", "servers.json")
    try:
        doc = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return {}
    servers = doc.get("servers") if isinstance(doc, dict) else None
    return servers if isinstance(servers, dict) else {}


def server_name(server_id, locale: str = "en") -> str | None:
    """The world/server name for a server ID from the bundled table (e.g. 2102 -> "Zikel"), or
    None when unknown. Prefers the requested locale, then English, then any available name."""
    row = _servers_table().get(str(server_id))
    if not isinstance(row, dict):
        return None
    name = row.get(locale) or row.get("en") or next((v for v in row.values() if isinstance(v, str) and v.strip()), None)
    return name if isinstance(name, str) and name.strip() else None


# ----------------------------------------------------- community name + portrait overlay
#
# A *fallback* overlay behind the curated bundled table: the NPC id -> {name, icon}
# map scraped by the log server's `aion2logs portraits` job (its
# ``npc-portraits-community.json``). It is community-sourced and id-matched, not an
# official or id-verified mapping, so it is a fallback only — it never overrides a
# curated name or portrait. Two uses:
#   * portrait: art for a catalog NPC the bundled table has no image for; and
#   * name: for an id the curated catalog does not map at all (new content upstream
#     hasn't published), so we can show a real name instead of ``#<code>``. A
#     name-less entry (a flat ``{id: url}`` map) never invents an NPC — an unmapped
#     id with no scraped name stays unknown.
# The file lives on the server (or a client cache); its path is registered by the host
# or read from the ``A2_COMMUNITY_PORTRAITS`` environment variable. Absent/malformed
# files degrade silently to no overlay, so importing or calling this never fails.

_COMMUNITY_PORTRAITS_PATH: str | None = None
_community_cache: dict[str, tuple[float, dict]] = {}


def set_community_portraits(path: str | os.PathLike | None) -> None:
    """Point :func:`npc_info` at a community name/portrait overlay file (the server's
    scraped ``npc-portraits-community.json``), or ``None`` to clear it. The host
    (the log server) calls this at startup with its data-dir file."""
    global _COMMUNITY_PORTRAITS_PATH
    _COMMUNITY_PORTRAITS_PATH = str(path) if path else None
    _community_cache.clear()


def _community_overlay() -> dict:
    """``{mob_code: {"name": str|None, "icon": str|None}}`` from the configured overlay
    file, or ``{}``. Cached and transparently re-read when the file's mtime changes (the
    offline scraper rewrites it), and never raises — a missing or malformed file simply
    yields no overlay. Accepts either the scraper envelope
    (``{"portraits": {id: {"name": ..., "icon": ...}}}``) or a flat ``{id: url}`` map
    (icon only, no name)."""
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
    out: dict[str, dict] = {}
    if isinstance(rows, dict):
        for code, row in rows.items():
            if isinstance(row, dict):
                name, icon = row.get("name"), row.get("icon")
            else:
                name, icon = None, row                       # flat {id: url}: icon only
            name = name if isinstance(name, str) and name.strip() else None
            icon = icon if isinstance(icon, str) and icon else None
            if name or icon:
                out[str(code)] = {"name": name, "icon": icon}
    _community_cache[path] = (mtime, out)
    return out


def npc_info(mob_code: int, locale: str = "en") -> dict:
    info = _table("npcs", locale).get(str(mob_code), {})
    if not isinstance(info, dict):
        info = {}
    override = _npc_overrides().get(str(mob_code))
    if isinstance(override, dict):
        info = {**info, **{k: v for k, v in override.items() if k not in ("source", "note")}}
    comm = _community_overlay().get(str(mob_code), {})
    if not info:
        # Unknown to the curated catalog: fall back to the community name overlay for new
        # content the bundled table hasn't mapped yet (shown as ``#<code>`` otherwise). A
        # scraped name is required — a name-less overlay entry never invents an NPC.
        name = comm.get("name")
        if not name:
            return {}
        info = {"name": name, "community": True}
    portrait = _table("npc-portraits", "en").get(str(mob_code), {})
    icon = portrait.get("icon") if isinstance(portrait, dict) else None
    if not icon:                                  # fall back to the community overlay
        icon = comm.get("icon")
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
