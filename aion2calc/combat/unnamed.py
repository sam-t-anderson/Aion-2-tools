"""Labels for what a recording could only call "???", and the arena matches against players it had no
names for.

The game gives no name to the invisible summons a boss's mechanics strike with, to a class's ground
effects (a Sorcerer's Bittercold Wind, Fire Wall and Cold Storm are summons of their own) or to flags
and timers: it shows "???", the community catalog lists them so in every language, and a meter of
0.2.354 or earlier exported that. An NPC is labelled by what its catalog row is (``lookup.npc_info``:
"Unnamed summon"), and a player's summon by the skill it strikes with, the ground effect's own name.
The meter applies this to what it exports and the log server whenever it loads a stored recording;
the stored upload is never changed. Nothing is named from a guess: a summon that struck with no named
skill stays an unnamed summon.

An arena's opponents are often players the capture has no identity record for: known only by the
class skills they strike with (0.2.354), they did not make the fight PvP, and it was typed unverified
PvE on the arena's own map. A fight on a confirmed arena map where such players struck the party is
the arena match (``arena_matches``); the meter of 0.2.355 types it so itself.

Its heals lose the Stamina and MP a skill restores (``healing.drop_restores``): the game sends them in
the layout of an HP restore, and a meter of 0.2.354 or earlier recorded them as healing. In a log a meter
before 0.2.399 recorded, its heals over time are rebuilt into what each tick took (``healing.heals_over_time``,
0.2.403): such a meter recorded a heal over time's pool when it was cast and then what was left of it.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from ..meter.a2parser.lookup import UNNAMED_LABELS, UNNAMED_NPC, has_skill, npc_info, skill_family, skill_name, unnamed

UNNAMED_SUMMON = UNNAMED_LABELS["Summon"]


def _skill(hit):
    """The hit's skill name, or its family's when the tables lack the rank (``Skill 15200012`` is a
    Cold Storm), else None: never the ``Skill <id>`` an unknown id is shown as."""
    name, sid = hit.get("skill"), hit.get("skill_id")
    if isinstance(name, str) and name.strip() and not (name.startswith("Skill ") and name[6:].isdigit()):
        return name
    if isinstance(sid, int) and not isinstance(sid, bool) and has_skill(skill_family(sid)):
        return skill_name(skill_family(sid))
    return None


def arena_matches(segment) -> bool:
    """Retype a segment on a confirmed arena map, typed PvE, whose damage records show players the
    capture could not name striking the party, as the arena match it was. Whether it did so."""
    from ..meter.context import PVP_MAPS
    from .catalog import struck_as_players
    map_id = segment.get("map_id")
    if map_id not in PVP_MAPS or str(segment.get("encounter_type") or "").startswith("pvp_"):
        return False
    strangers = {s for s in struck_as_players(segment) if not str(s).startswith("p:")}
    if not any(e.get("source") in strangers and str(e.get("target") or "").startswith("p:")
               for e in segment.get("events") or () if isinstance(e, dict) and e.get("kind") == "damage"):
        return False
    record = PVP_MAPS[map_id]
    segment.update(encounter_type="pvp_arena", zone=record["zone"], zone_source=record["evidence"],
                   encounter_type_source="Recorded map + players struck the party with class skills + confirmed arena capture")
    return True


def renamed_zone(segment) -> bool:
    """Give a segment whose zone is a name the catalog has since replaced the current one: apps before 0.2.361
    saved map 61 as *Arena (map 61)*, the Impetusium Arena. Whether it did so."""
    from ..meter.context import PVP_MAPS
    map_id = segment.get("map_id")
    record = PVP_MAPS.get(map_id) if isinstance(map_id, int) else None
    if not record or segment.get("zone") not in record.get("formerly", ()):
        return False
    segment.update(zone=record["zone"], zone_source=record["evidence"])
    return True


def rename_zones(doc):
    """``doc`` with each segment's replaced zone name made current (``renamed_zone``), in place."""
    for segment in (doc.get("segments") if isinstance(doc, dict) else None) or []:
        if isinstance(segment, dict):
            renamed_zone(segment)
    return doc


def relabel(doc):
    """``doc`` with each entity named "???" given its label, each arena match against players the
    capture could not name typed so, each zone name the catalog has replaced made current, the Stamina
    and MP restores left out of its heals, in a log a meter before 0.2.399 recorded its heals over time
    rebuilt into what each tick took (``healing.heals_over_time``, 0.2.403), and in PvP the heals between
    the two sides (a shield's absorb as such a meter recorded it) left out and counted, in place
    (returned for chaining). A rebuild recomputes the summaries the log carries of its heals: the
    encounter insights' effective healing and the death recaps."""
    from .healing import drop_restores, heals_over_time, records_pools, unattributed_heals
    players = {p.get("id") for p in (doc.get("players") if isinstance(doc, dict) else None) or [] if isinstance(p, dict)}
    rebuild = records_pools(doc)
    rebuilt = False
    for segment in (doc.get("segments") if isinstance(doc, dict) else None) or []:
        if not isinstance(segment, dict):
            continue
        renamed_zone(segment)
        arena_matches(segment)
        drop_restores(segment)
        if rebuild and heals_over_time(segment):
            rebuilt = True
        unattributed_heals(segment, players)
        pending = [e for e in segment.get("entities") or [] if isinstance(e, dict) and unnamed(e.get("name"))]
        if not pending:
            continue
        skills = defaultdict(Counter)
        for hit in segment.get("hits") or []:
            if isinstance(hit, dict) and isinstance(hit.get("pet"), str) and (name := _skill(hit)):
                skills[hit["pet"]][name] += 1
        for entity in pending:
            if entity.get("kind") == "pet":
                used = skills.get(entity.get("id"))
                entity["name"] = min(used.items(), key=lambda kv: (-kv[1], kv[0]))[0] if used else UNNAMED_SUMMON
                continue
            code = entity.get("mob_code")
            info = npc_info(code) if isinstance(code, int) and not isinstance(code, bool) else {}
            entity["name"] = info["name"] if not unnamed(info.get("name")) else UNNAMED_NPC
    if rebuilt:
        _summaries_again(doc)
    return doc


def rebuild_heals(doc) -> bool:
    """In a log a meter before 0.2.399 recorded, rebuild each segment's heals over time into what each tick took
    (``healing.heals_over_time``) and recompute the summaries of its heals, in place: what the app's review of a
    saved log and of a recording's parts reads (``relabel`` does the same among its other repairs). Whether
    anything was rebuilt."""
    from .healing import heals_over_time, records_pools
    if not isinstance(doc, dict) or not records_pools(doc):
        return False
    rebuilt = False
    for segment in doc.get("segments") or []:
        if isinstance(segment, dict) and heals_over_time(segment):
            rebuilt = True
    if rebuilt:
        _summaries_again(doc)
    return rebuilt


def _summaries_again(doc) -> None:
    """Recompute, in place, the summaries a stored log carries that add up its heals, after its heals over time were
    rebuilt: the encounter insights (effective healing) and the death recaps (healing received). A summary that
    cannot be recomputed is kept as it was."""
    if isinstance(doc.get("encounter_insights"), dict):
        from .insights import summarize as encounter_insights
        try:
            doc["encounter_insights"] = encounter_insights(doc)
        except Exception:                      # noqa: BLE001 - a malformed log keeps the insights it carried
            pass
    if isinstance(doc.get("death_analysis"), dict):
        from .recaps import summarize as death_recaps
        try:
            doc["death_analysis"] = death_recaps(doc)
        except Exception:                      # noqa: BLE001 - as above
            pass
