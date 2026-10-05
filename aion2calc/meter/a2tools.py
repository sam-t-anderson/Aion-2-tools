"""Adapter between the migrated A2Tools packet meter and aion2calc's live UI."""
from __future__ import annotations

from datetime import datetime, timezone

from .a2parser.engine import MeterEngine
from .a2parser.lookup import skill_name
from .a2parser.models import SpecialDamage

CLASS_KEYS = {"elementalist": "spiritmaster"}


def _class_key(value: str) -> str | None:
    key = "".join(ch for ch in value.lower() if ch.isalpha())
    return CLASS_KEYS.get(key, key) or None


def snapshot(engine: MeterEngine, target_mode: str = "bossTargets") -> dict:
    """Normalize a packet-meter snapshot for the existing Live Meter page."""
    raw = engine.snapshot(target_mode)
    players = []
    for actor in raw.get("actors", []):
        damage = float(actor.get("damage", 0))
        skills = []
        for skill in actor.get("skills", []):
            hits = int(skill.get("hits", 0))
            skills.append({"skill": skill.get("name") or f"Skill {skill.get('skillCode', 0)}",
                           "skill_id": skill.get("skillCode"), "damage": float(skill.get("damage", 0)),
                           "share": float(skill.get("damage", 0)) / damage if damage else 0.0,
                           "casts": hits, "hits": hits, "crit": float(skill.get("critRate", 0))})
        skills.sort(key=lambda row: -row["damage"])
        players.append({"id": str(actor.get("actorId", "")),
                        "name": actor.get("nickname") or f"#{actor.get('actorId', '?')}",
                        "class": _class_key(str(actor.get("job", ""))), "damage": damage,
                        "dps": float(actor.get("dps", 0)), "share": float(actor.get("contribution", 0)),
                        "hits": sum(row["hits"] for row in skills), "crit": 0.0,
                        "double": 0.0, "perfect": 0.0, "skills": skills})
    return {"duration": raw.get("durationMs", 0) / 1000, "boss": raw.get("targetName") or None,
            "total": float(raw.get("totalDamage", 0)), "dps": float(raw.get("dps", 0)),
            "players": players, "target_mode": target_mode, "ping_ms": raw.get("pingMs"),
            "target_hp": {"current": raw.get("targetCurrentHp"), "max": raw.get("targetMaxHp")}}


def to_a2log(engine: MeterEngine, target_mode: str = "bossTargets",
             title: str | None = None) -> dict:
    """Return an a2log document from decoded events without exposing packets."""
    from ..combat import a2log

    raw = engine.snapshot(target_mode)
    actor_rows = {int(row["actorId"]): row for row in raw.get("actors", [])}
    selected = int(raw.get("targetId") or 0)
    events = [event for event in engine.event_log
              if target_mode == "allTargets" or event.target_id == selected]
    if not events:
        raise ValueError("no decoded damage is available to export")
    start = min(event.timestamp_ms for event in events)
    players, known = [], set()
    for actor_id, row in actor_rows.items():
        player = {"id": str(actor_id), "name": row.get("nickname") or f"#{actor_id}",
                  "class": _class_key(str(row.get("job", "")))}
        if row.get("serverId"):
            player["server"] = str(row["serverId"])
        if row.get("combatPower"):
            player["combat_power"] = row["combatPower"]
        if row.get("gearScore"):
            player["gear_score"] = row["gearScore"]
        players.append(player)
        known.add(player["id"])
    hits = []
    for event in events:
        player_id = str(event.actor_id)
        if player_id not in known:
            players.append({"id": player_id, "name": engine.names.get(event.actor_id, f"#{event.actor_id}")})
            known.add(player_id)
        hit = {"t": round(max(0, event.timestamp_ms - start) / 1000, 3), "player": player_id,
               "skill": skill_name(event.skill_code), "skill_id": event.skill_code,
               "damage": event.total_damage}
        for flag, key in ((SpecialDamage.CRITICAL, "crit"), (SpecialDamage.DOUBLE, "double"),
                          (SpecialDamage.PERFECT, "perfect"), (SpecialDamage.BACK, "back"),
                          (SpecialDamage.FRONTAL, "front")):
            if flag in event.specials:
                hit[key] = True
        if event.is_dot:
            hit["dot"] = True
        if event.multi_hit_count:
            hit["multi"] = event.multi_hit_count
        hits.append(hit)
    segment = {"label": raw.get("targetName") or "Live meter session",
               "duration": max(0.001, (max(event.timestamp_ms for event in events) - start) / 1000),
               "killed": False, "hits": hits}
    if raw.get("targetName"):
        segment["boss"] = raw["targetName"]
    meta = {"source": "aion2calc A2Tools packet meter",
            "recorded_at": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat().replace("+00:00", "Z")}
    if title:
        meta["title"] = title
    return a2log.validate({"format": "a2log", "version": a2log.VERSION, "meta": meta,
                            "players": players, "segments": [segment]})
