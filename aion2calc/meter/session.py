"""Retained live combat history, independent of the protocol meter's idle resets."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from .a2parser.lookup import job_from_skill, npc_name, skill_name
from .a2parser.models import DamageEvent, HealEvent, SpecialDamage


@dataclass(frozen=True, slots=True)
class Record:
    epoch: int
    event: DamageEvent | HealEvent
    party: frozenset[str]
    local_id: int | None


class CombatSession:
    def __init__(self):
        self.records = deque(maxlen=400_000)
        self.epoch = 0
        self.identities = {}
        self.discarded = 0
        self.gap_seconds = 10
        self._zone_reset = None

    def begin_capture(self):
        self.epoch += 1
        self._zone_reset = None

    def observe(self, engine, events):
        if engine.last_zone_reset_ms != self._zone_reset:
            if self._zone_reset is not None or engine.last_zone_reset_ms is not None:
                self.epoch += 1
            self._zone_reset = engine.last_zone_reset_ms
        identity = self.identities.setdefault(self.epoch, {"names": {}, "spawns": {}, "jobs": {}, "local_id": None})
        identity["names"].update(engine.names)
        identity["jobs"].update(engine.jobs)
        identity["spawns"].update({key: dict(value) for key, value in engine.spawn_info.items()})
        if engine.local_player_id is not None:
            identity["local_id"] = engine.local_player_id
        party = frozenset(name.casefold() for name in engine.roster)
        for event in events:
            if len(self.records) == self.records.maxlen:
                self.discarded += 1
            self.records.append(Record(self.epoch, event, party, engine.local_player_id))
        # Remove identity contexts when their bounded event history expires.
        if len(self.identities) > 250:
            retained = {record.epoch for record in self.records}
            for epoch in tuple(self.identities):
                if epoch not in retained and epoch != self.epoch:
                    self.identities.pop(epoch)

    def name(self, epoch, actor_id, enemy=False):
        identity = self.identities[epoch]
        if actor_id in identity["names"]:
            return identity["names"][actor_id]
        code = identity["spawns"].get(actor_id, {}).get("mobCode")
        if code:
            name = npc_name(code)
            return name if not name.startswith("#") else f"Enemy #{actor_id} (type {code})"
        return f"{'Enemy' if enemy else 'Player'} #{actor_id}"

    def _allowed(self, record, scope):
        identity = self.identities[record.epoch]
        local = record.local_id if record.local_id is not None else identity["local_id"]
        allowed = {local} if local is not None else set()
        if scope == "party":
            allowed.update(actor_id for actor_id, name in identity["names"].items()
                           if name.casefold() in record.party)
        elif scope == "all":
            allowed.update(identity["names"])
            event = record.event
            if isinstance(event, DamageEvent) and job_from_skill(event.skill_code):
                allowed.add(event.actor_id)
        return allowed

    def groups(self, scope="party"):
        groups = []
        for record in self.records:
            event = record.event
            allowed = self._allowed(record, scope)
            relevant = event.actor_id in allowed or (isinstance(event, DamageEvent) and event.target_id in allowed)
            if not relevant:
                continue
            if (not groups or groups[-1]["epoch"] != record.epoch
                    or event.timestamp_ms - groups[-1]["end"] > self.gap_seconds * 1000):
                groups.append({"id": f"{record.epoch}-{event.timestamp_ms}", "epoch": record.epoch,
                               "start": event.timestamp_ms, "end": event.timestamp_ms, "records": []})
            group = groups[-1]
            group["end"] = max(group["end"], event.timestamp_ms)
            group["records"].append(record)
        return groups[-200:]

    @staticmethod
    def _actor(actor_id, name, job=None):
        return {"id": str(actor_id), "name": name, "class": (job or "").lower().replace("elementalist", "spiritmaster") or None,
                "damage": 0, "hits": 0, "healing": 0, "skills": {}, "incoming": {"damage": 0, "hits": 0, "parries": 0, "sources": {}},
                "counts": {key: 0 for key in ("crit", "back", "front", "double", "perfect", "multi", "parry")}}

    def _summary(self, groups, scope, enemy_id=None):
        players, enemies = {}, {}
        durations = sum(max(1.0, (g["end"] - g["start"]) / 1000) for g in groups)
        timeline = {}
        offset = 0
        for group in groups:
            identity = self.identities[group["epoch"]]
            for record in group["records"]:
                event, allowed = record.event, self._allowed(record, scope)
                def player(actor_id):
                    # IDs may be reused after a zone/socket change: don't merge
                    # unnamed actors from unrelated contexts into one person.
                    name = self.name(record.epoch, actor_id)
                    key = f"{record.epoch}:{actor_id}"
                    row = players.setdefault(key, self._actor(actor_id, name, identity["jobs"].get(actor_id)))
                    row["key"] = key
                    return row
                if isinstance(event, HealEvent):
                    if event.actor_id in allowed:
                        player(event.actor_id)["healing"] += event.amount
                    continue
                if event.actor_id in allowed and event.target_id not in allowed:
                    target_key = f"{record.epoch}:{event.target_id}"
                    enemy = enemies.setdefault(target_key, {"key": target_key, "id": str(event.target_id),
                        "name": self.name(record.epoch, event.target_id, True), "damage": 0, "hits": 0,
                        "mob_code": identity["spawns"].get(event.target_id, {}).get("mobCode"), "players": {}})
                    enemy["damage"] += event.total_damage; enemy["hits"] += 1
                    enemy["players"][str(event.actor_id)] = enemy["players"].get(str(event.actor_id), 0) + event.total_damage
                    if enemy_id and target_key != enemy_id:
                        continue
                    row = player(event.actor_id)
                    row["class"] = row["class"] or (job_from_skill(event.skill_code) or "").lower().replace("elementalist", "spiritmaster") or None
                    row["damage"] += event.total_damage; row["hits"] += 1
                    skill = row["skills"].setdefault((event.skill_code, event.is_dot), {
                        "skill_id": event.skill_code, "skill": skill_name(event.skill_code), "damage": 0, "hits": 0,
                        "min": event.total_damage, "max": 0})
                    skill["damage"] += event.total_damage; skill["hits"] += 1
                    skill["min"] = min(skill["min"], event.total_damage); skill["max"] = max(skill["max"], event.total_damage)
                    for flag, key in ((SpecialDamage.CRITICAL, "crit"), (SpecialDamage.BACK, "back"),
                                      (SpecialDamage.FRONTAL, "front"), (SpecialDamage.DOUBLE, "double"),
                                      (SpecialDamage.PERFECT, "perfect"), (SpecialDamage.PARRY, "parry")):
                        row["counts"][key] += int(flag in event.specials)
                    row["counts"]["multi"] += int(event.multi_hit_count > 0)
                    second = (event.timestamp_ms - group["start"]) // 1000
                    points = timeline.setdefault(row["key"], {})
                    # A whole-session graph joins combat intervals without counting idle gaps.
                    points[second + offset] = points.get(second + offset, 0) + event.total_damage
                elif event.target_id in allowed:
                    if enemy_id and f"{record.epoch}:{event.actor_id}" != enemy_id:
                        continue
                    row = player(event.target_id)
                    incoming = row["incoming"]
                    incoming["damage"] += event.total_damage; incoming["hits"] += 1
                    incoming["parries"] += int(SpecialDamage.PARRY in event.specials)
                    source = self.name(record.epoch, event.actor_id, True)
                    incoming["sources"][source] = incoming["sources"].get(source, 0) + event.total_damage
            offset += max(1, int((group["end"] - group["start"]) / 1000) + 1)
        total = sum(row["damage"] for row in players.values())
        for row in players.values():
            row["dps"] = row["damage"] / max(1, durations)
            row["share"] = row["damage"] / total if total else 0
            for key, value in row.pop("counts").items():
                row[key] = value / row["hits"] if row["hits"] else None
            row["skills"] = sorted(row["skills"].values(), key=lambda skill: -skill["damage"])
            for skill in row["skills"]:
                skill["share"] = skill["damage"] / row["damage"] if row["damage"] else 0
            points = timeline.get(row["key"], {})
            values = [points.get(index, 0) for index in range(max(points, default=-1) + 1)]
            row["timeline"] = {"per_second": values, "rolling10": [sum(values[max(0,i-9):i+1]) / min(i+1,10) for i in range(len(values))]}
        for enemy in enemies.values():
            enemy["dps"] = enemy["damage"] / max(1, durations)
        return {"players": sorted(players.values(), key=lambda row: (-row["damage"], -row["incoming"]["damage"], row["key"])),
                "enemies": sorted(enemies.values(), key=lambda row: -row["damage"]), "duration": durations,
                "total": total, "dps": total / max(1, durations)}

    def snapshot(self, scope="party", segment_id=None, enemy_id=None):
        groups = self.groups(scope)
        chosen = groups if segment_id == "all" else [next((g for g in groups if g["id"] == segment_id), groups[-1])] if groups else []
        summary = self._summary(chosen, scope, enemy_id)
        summary["segments"] = [{"id": group["id"], "label": f"Combat {index + 1}", "start": group["start"],
                                "duration": max(1, (group["end"] - group["start"]) / 1000),
                                "events": len(group["records"])} for index, group in enumerate(groups)]
        summary["selected_segment"] = "all" if segment_id == "all" else chosen[-1]["id"] if chosen else None
        summary["selected_enemy"] = enemy_id
        summary["boss"] = next((row["name"] for row in summary["enemies"] if row["key"] == enemy_id), "All enemies")
        summary["scope"] = scope
        summary["warning"] = ("Waiting for your player identity. Enter your character name before Start; nearby players are excluded until you or party members are identified."
                              if self.records and not groups and scope != "all" else None)
        summary["history_discarded"] = self.discarded
        return summary

    def to_a2log(self, scope="party", title=None):
        from ..combat import a2log
        groups = self.groups(scope)
        players, segments = {}, []
        for index, group in enumerate(groups):
            hits = []
            for record in group["records"]:
                event = record.event
                allowed = self._allowed(record, scope)
                if not isinstance(event, DamageEvent) or event.actor_id not in allowed or event.target_id in allowed:
                    continue
                identity = self.identities[record.epoch]
                pid = f"{record.epoch}:{event.actor_id}"
                players[pid] = {"id": pid, "name": self.name(record.epoch, event.actor_id),
                                "class": identity["jobs"].get(event.actor_id) or job_from_skill(event.skill_code)}
                hit = {"t": max(0, event.timestamp_ms - group["start"]) / 1000, "player": pid,
                       "damage": event.total_damage, "skill_id": event.skill_code, "skill": skill_name(event.skill_code)}
                for flag,key in ((SpecialDamage.CRITICAL,"crit"),(SpecialDamage.BACK,"back"),(SpecialDamage.FRONTAL,"front"),
                                 (SpecialDamage.DOUBLE,"double"),(SpecialDamage.PERFECT,"perfect")):
                    if flag in event.specials: hit[key] = True
                if event.multi_hit_count: hit["multi"] = event.multi_hit_count
                if event.is_dot: hit["dot"] = True
                hits.append(hit)
            if hits:
                segments.append({"id": group["id"], "label": f"Combat {index+1}", "hits": hits,
                                 "start": datetime.fromtimestamp(group["start"] / 1000, timezone.utc).isoformat(),
                                 "duration": max(0.001, (group["end"] - group["start"]) / 1000)})
        if not players:
            raise ValueError("No identified player damage is available under the selected party filter.")
        if len(players) > 64:
            raise ValueError("This session contains more than 64 player identities. Export a shorter session or use Party / Self filtering.")
        return a2log.validate({"format":"a2log","version":1,"meta":{"source":"Aion 2 Calc live session","title":title or "Live combat session"},
                               "players":list(players.values()),"segments":segments})
