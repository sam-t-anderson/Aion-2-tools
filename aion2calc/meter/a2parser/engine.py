"""Stateful damage aggregation and a small replay-facing meter API."""

from __future__ import annotations

from collections import defaultdict
from collections import deque
from threading import RLock
from collections.abc import Callable
from copy import deepcopy
import time

from .models import ActorStats, DamageEvent, HealEvent, TargetStats
from .parser import decode_stream, scan_identity, scan_self_profile, scan_character_list, scan_actor_name_bindings, scan_legacy_nicknames, scan_party_roster, scan_summon_links, scan_spawn_metadata, scan_hp_updates, scan_deaths, scan_zone_state, _damage_frames
from .framing import walk, bundle_batch
from .lookup import job_from_skill, skill_name, npc_info, npc_name
from .ping import PingTracker
import json
from importlib.resources import files

IDLE_RESET_MS = 30_000
ALL_TARGETS_WINDOW_MS = 120_000
try:
    OPEN_WORLD_MAPS = set(json.loads(files(__package__).joinpath("data", "open_world_maps.json").read_text(encoding="utf-8"))["maps"])
except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError, KeyError):
    OPEN_WORLD_MAPS = set()


class MeterEngine:
    def __init__(self, *, perf_clock: Callable[[], tuple[int, int]] | None = None) -> None:
        self.targets: dict[int, TargetStats] = {}
        self.local_player_id: int | None = None
        self.local_character_name = ""
        self.local_identity_from_game = False
        self.local_profile: dict[str, int | str] = {}
        self.telemetry: list[dict] = []
        self.last_framing_errors = 0
        self.names: dict[int, str] = {}
        self.known_players: set[int] = set()
        self.jobs: dict[int, str] = {}
        self.roster: dict[str, dict] = {}
        self.roster_complete = False
        self.dungeon_id = 0
        self.healers: dict[int, ActorStats] = {}
        self.summons: set[int] = set()
        self.summon_owners: dict[int, int] = {}
        self.power_scalars: dict[int, set[int]] = defaultdict(set)
        self.known_entities: set[int] = set()
        self.spawn_info: dict[int, dict[str, int]] = {}
        self.npc_scan_calls = 0
        self.npc_candidates_seen = 0
        self.npc_trace = deque(maxlen=128)
        self.npc_trace_omitted = 0
        self.live_hp: dict[int, int] = {}
        self.all_targets_window_ms = ALL_TARGETS_WINDOW_MS
        self.completed_fights: list[dict] = []
        self.ping_tracker = PingTracker(perf_clock=perf_clock)
        self.seen_embedded_damage: set[bytes] = set()
        self.seen_embedded_order: deque[bytes] = deque()
        self._saved_encounters: set[tuple[int, int]] = set()
        self.last_damage_time_ms: int | None = None
        self.last_zone_reset_ms: int | None = None
        self.map_id = 0
        self.server_port = 50349
        self.damage_events = 0
        # A bounded, resolved event trail supports exporting an open a2log
        # document without retaining the raw packet capture.  Actor ids here
        # are already merged into their summon owner where one is known.
        self.event_log: deque[DamageEvent] = deque(maxlen=400_000)
        self._pending: dict[str, bytearray] = defaultdict(bytearray)
        self._lock = RLock()

    def set_actor(self, actor_id: int, *, name: str | None = None, job: str | None = None) -> None:
        with self._lock:
            if name:
                self.names[actor_id] = name
            if job:
                self.jobs[actor_id] = job

    def set_local_character_name(self, name: str) -> None:
        with self._lock:
            if not self.local_identity_from_game and str(name).strip() != self.local_character_name:
                self.local_player_id = None
            self.local_character_name = str(name).strip()
            self._bind_named_character()

    def _bind_named_character(self) -> None:
        """Bind only a unique observed name explicitly supplied by the user."""
        if self.local_player_id is None and self.local_character_name:
            matches = [actor_id for actor_id, name in self.names.items()
                       if name.casefold() == self.local_character_name.casefold()]
            if len(matches) == 1:
                self.local_player_id = matches[0]
                self.known_players.add(matches[0])
                self.known_entities.add(matches[0])

    def _bind_character_list(self, data: bytes) -> None:
        if self.local_identity_from_game or not self.local_character_name:
            return
        match = scan_character_list(data, self.local_character_name)
        if match is not None:
            actor_id, name = match
            self.names[actor_id] = name
            self.known_players.add(actor_id)
            self.known_entities.add(actor_id)
            self.local_player_id = actor_id

    def set_all_targets_window_ms(self, value: int) -> None:
        with self._lock:
            self.all_targets_window_ms = min(900_000, max(10_000, int(value)))

    def set_server_port(self, value: int) -> None:
        if not 1 <= int(value) <= 65_535:
            raise ValueError("server port must be between 1 and 65535")
        with self._lock:
            self.server_port = int(value)

    def reset_stream(self, stream_id: str) -> None:
        """Discard partial framing at a recorded lossy transport boundary."""
        with self._lock:
            self._pending.pop(stream_id, None)

    def consume(self, buffer: bytes, timestamp_ms: int | None = None, stream_id: str = "default") -> list[DamageEvent | HealEvent]:
        with self._lock, bundle_batch() as batch:
            try:
                return self._consume_locked(buffer, timestamp_ms, stream_id)
            finally:
                self.last_framing_errors = batch.rejected

    def _consume_locked(self, buffer: bytes, timestamp_ms: int | None, stream_id: str) -> list[DamageEvent | HealEvent]:
        self.telemetry = []
        self.last_framing_errors = 0
        pending = self._pending[stream_id]
        pending.extend(buffer)
        framing = walk(bytes(pending))
        if framing.consumed == 0:
            return []
        complete = bytes(pending[:framing.consumed])
        del pending[:framing.consumed]
        timestamp_ms = timestamp_ms if timestamp_ms is not None else time.time_ns() // 1_000_000
        client_to_server = (stream_id.lower().startswith("client:") or
                            stream_id.rsplit("->", 1)[-1].endswith(f":{self.server_port}"))
        self.ping_tracker.observe(complete, client_to_server=client_to_server, captured_at_ms=timestamp_ms)
        zone_change, map_id = scan_zone_state(complete)
        if (zone_change
                and (self.last_damage_time_ms is None or timestamp_ms - self.last_damage_time_ms >= 1_500)
                and (self.last_zone_reset_ms is None or timestamp_ms - self.last_zone_reset_ms >= 4_000)):
            # Actor IDs and summon ownership belong to the loaded zone. Reset
            # before reading this packet's new identities, not after them.
            self._reset_zone(timestamp_ms)
        for actor_id, name, is_self, job in scan_identity(complete):
            self.names[actor_id] = name
            self.known_players.add(actor_id)
            self.known_entities.add(actor_id)
            if job:
                self.jobs[actor_id] = job
            if is_self:
                self.local_player_id = actor_id
                self.local_identity_from_game = True
        self._observe_self_profile(complete)
        self._bind_character_list(complete)
        roster = scan_party_roster(complete)
        if roster:
            self._update_roster(*roster)
        summons, links = scan_summon_links(complete, self.names, self.summons)
        self.summons.update(summons)
        self.summon_owners.update(links)
        for actor_id, name in scan_legacy_nicknames(complete):
            if actor_id not in self.summons:
                self.names.setdefault(actor_id, name)
        for entity_id, info in self._scan_spawns(complete, timestamp_ms).items():
            self.spawn_info.setdefault(entity_id, {}).update(info)
            if info.get("maxHp"):
                self.spawn_info[entity_id]["reportedMaxHp"] = info["maxHp"]
                self.telemetry.append({"kind":"hp", "entity":entity_id, "current":info["currentHp"], "max":info["maxHp"], "timestamp_ms":timestamp_ms})
        self.known_entities.update(self.spawn_info)
        self.known_entities.update(links)
        self.known_entities.update(links.values())
        if map_id is not None:
            self.map_id = map_id
            if map_id in OPEN_WORLD_MAPS:
                self.dungeon_id = 0
        current_hp, maximum_hp = scan_hp_updates(complete)
        self.telemetry.extend({"kind": "hp", "entity": eid, "current": hp, "max": maximum_hp.get(eid), "timestamp_ms": timestamp_ms} for eid, hp in current_hp.items())
        self.live_hp.update(current_hp)
        for entity_id, value in current_hp.items():
            info = self.spawn_info.setdefault(entity_id, {})
            info["currentHp"] = value
            if value > info.get("maxHp", 0):
                info["maxHp"] = value
        for entity_id, max_hp in maximum_hp.items():
            self.spawn_info.setdefault(entity_id, {})["maxHp"] = max_hp
            self.spawn_info[entity_id]["reportedMaxHp"] = max_hp
        for entity_id, value in current_hp.items():
            if entity_id in self.targets:
                self.targets[entity_id].current_hp = value
        for packet in _damage_frames(complete, inner=False):
            # Spawn/HP records inside compressed bundles were previously
            # scanned only as compressed bytes, losing the NPC database key.
            for entity_id, info in self._scan_spawns(packet, timestamp_ms).items():
                self.spawn_info.setdefault(entity_id, {}).update(info)
                if info.get("maxHp"):
                    self.spawn_info[entity_id]["reportedMaxHp"] = info["maxHp"]
                    self.telemetry.append({"kind":"hp", "entity":entity_id, "current":info["currentHp"], "max":info["maxHp"], "timestamp_ms":timestamp_ms})
            self.known_entities.update(self.spawn_info)
            current, maximum = scan_hp_updates(packet)
            self.telemetry.extend({"kind": "hp", "entity": eid, "current": hp, "max": maximum.get(eid), "timestamp_ms": timestamp_ms} for eid, hp in current.items())
            self.telemetry.extend({"kind": "death", "entity": eid, "timestamp_ms": timestamp_ms} for eid in scan_deaths(packet))
            self.live_hp.update(current)
            for entity_id, value in maximum.items():
                self.spawn_info.setdefault(entity_id, {})["maxHp"] = value
                self.spawn_info[entity_id]["reportedMaxHp"] = value
            for actor_id, name in scan_actor_name_bindings(packet):
                if actor_id not in self.summons:
                    self.names.setdefault(actor_id, name)
            for actor_id, name in scan_legacy_nicknames(packet):
                if actor_id not in self.summons:
                    self.names.setdefault(actor_id, name)
                    self.known_entities.add(actor_id)
            for actor_id, name, is_self, job in scan_identity(packet):
                self.names[actor_id] = name
                self.known_players.add(actor_id)
                self.known_entities.add(actor_id)
                if job:
                    self.jobs[actor_id] = job
                if is_self:
                    self.local_player_id = actor_id
                    self.local_identity_from_game = True
            self._observe_self_profile(packet)
            self._bind_character_list(packet)
            roster = scan_party_roster(packet)
            if roster:
                self._update_roster(*roster)
            # Owner links can be bundled with combat/identity messages. Scanning
            # only the compressed outer bytes misses these explicit links.
            summons, links = scan_summon_links(packet, self.names, self.summons)
            self.summons.update(summons)
            self.summon_owners.update(links)
            self.known_entities.update(summons)
            self.known_entities.update(links.values())
        self._bind_named_character()
        events = list(decode_stream(complete, timestamp_ms, self.known_entities,
                                   self.seen_embedded_damage, self.seen_embedded_order,
                                   self.known_players))
        for event in events:
            if isinstance(event, HealEvent):
                actor = self._actor_for(event.actor_id)
                actor.healing += event.amount
                if event.is_hot:
                    actor.regeneration += event.amount
                continue
            target = self.targets.get(event.target_id)
            spawn = self.spawn_info.get(event.target_id, {})
            mob_code = spawn.get("mobCode", target.mob_code if target else 0)
            if (npc_info(mob_code).get("isBoss", False) and self.targets
                    and not any(npc_info(row.mob_code).get("isBoss", False)
                                for row in self.targets.values())):
                # The upstream meter begins a clean combat segment when the
                # first boss is engaged, dropping trash damage from the run-up.
                self.targets.clear()
                target = None
            if target is not None and target.last_hit_ms and event.timestamp_ms - target.last_hit_ms > IDLE_RESET_MS:
                if npc_info(target.mob_code).get("isBoss", False):
                    key = (target.target_id, target.first_hit_ms)
                    if key not in self._saved_encounters:
                        self.completed_fights.append(self._fight_record(target))
                        self._saved_encounters.add(key)
                target = None
            if target is None:
                target = self.targets[event.target_id] = TargetStats(event.target_id)
            if target.first_hit_ms == 0:
                target.first_hit_ms = event.timestamp_ms
            target.last_hit_ms = max(target.last_hit_ms, event.timestamp_ms)
            target.damage += event.total_damage
            second = event.timestamp_ms // 1000
            target.damage_by_second[second] = target.damage_by_second.get(second, 0) + event.total_damage
            target.mob_code = spawn.get("mobCode", target.mob_code)
            target.max_hp = spawn.get("maxHp", target.max_hp)
            target.current_hp = spawn.get("currentHp", target.current_hp)
            target.current_hp = self.live_hp.get(event.target_id, target.current_hp)
            actor_id = self._resolve_summon(event.actor_id)
            if actor_id != event.actor_id:
                event = DamageEvent(actor_id, event.target_id, event.skill_code, event.damage,
                                    event.timestamp_ms, event.damage_type, event.specials, event.is_dot,
                                    event.multi_hit_count, event.multi_hit_damage, event.spec_flags,
                                    event.power_scalar)
            actor = target.actors.setdefault(actor_id, ActorStats(actor_id))
            actor.nickname = self.names.get(actor_id, self.names.get(event.actor_id, f"#{actor_id}"))
            actor.job = self.jobs.get(actor_id, self.jobs.get(event.actor_id, "")) or job_from_skill(event.skill_code) or ""
            self._apply_roster(actor)
            actor.add(event)
            if event.power_scalar:
                self.power_scalars[event.actor_id].add(event.power_scalar)
            actor_line = target.actor_damage_by_second.setdefault(actor_id, {})
            actor_line[second] = actor_line.get(second, 0) + event.total_damage
            self.damage_events += 1
            self.event_log.append(event)
            self.last_damage_time_ms = event.timestamp_ms
        # Death is processed after damage from this read so a final hit and
        # death marker arriving together are both represented in the history.
        for entity_id in scan_deaths(complete):
            self.telemetry.append({"kind": "death", "entity": entity_id, "timestamp_ms": timestamp_ms})
            target = self.targets.get(entity_id)
            if target and npc_info(target.mob_code).get("isBoss", False):
                key = (target.target_id, target.first_hit_ms)
                if key not in self._saved_encounters:
                    self.completed_fights.append(self._fight_record(target))
                    self._saved_encounters.add(key)
        return events

    def _scan_spawns(self, data: bytes, timestamp_ms: int) -> dict:
        scan = {"records": [], "candidates": 0}
        found = scan_spawn_metadata(data, scan)
        rows = scan["records"]
        self.npc_scan_calls += 1
        self.npc_candidates_seen += scan["candidates"]
        self.npc_trace_omitted += scan["candidates"]-len(rows)
        for row in rows:
            # Numeric protocol fields only: no packet bytes, text, paths or addresses.
            row["timestamp_ms"] = timestamp_ms
            if self.npc_trace and all(self.npc_trace[-1].get(k) == row.get(k)
                                      for k in ("entity", "mob_code", "status", "timestamp_ms")):
                continue
            if len(self.npc_trace) == self.npc_trace.maxlen:
                self.npc_trace_omitted += 1
            self.npc_trace.append(row)
        return found

    def _reset_zone(self, timestamp_ms: int) -> None:
        for target in self.targets.values():
            if npc_info(target.mob_code).get("isBoss", False):
                key = (target.target_id, target.first_hit_ms)
                if key not in self._saved_encounters:
                    self.completed_fights.append(self._fight_record(target))
                    self._saved_encounters.add(key)
        self.targets.clear()
        self.healers.clear()
        self.live_hp.clear()
        self.spawn_info.clear()
        self.npc_trace.clear()
        self.npc_scan_calls = 0
        self.npc_candidates_seen = 0
        self.npc_trace_omitted = 0
        self.names.clear()
        self.jobs.clear()
        self.known_players.clear()
        self.known_entities.clear()
        self.summons.clear()
        self.summon_owners.clear()
        self.power_scalars.clear()
        self.roster.clear()
        self.roster_complete = False
        self.local_player_id = None
        self.local_identity_from_game = False
        self.local_profile.clear()
        self.dungeon_id = 0
        self.last_zone_reset_ms = timestamp_ms

    def drain_completed_fights(self) -> list[dict]:
        with self._lock:
            fights, self.completed_fights = self.completed_fights, []
            return fights

    def _fight_record(self, target: TargetStats) -> dict:
        target = self._infer_orphan_owners(deepcopy(target))
        return {
            "bossName": npc_name(target.mob_code) if target.mob_code else f"#{target.target_id}",
            "targetId": target.target_id, "mobCode": target.mob_code,
            "startTimeMs": target.first_hit_ms, "durationMs": target.duration_ms,
            "endTimeMs": target.last_hit_ms,
            "totalDamage": target.damage, "dungeonId": self.dungeon_id,
            "actors": [{"actorId": actor.actor_id, "nickname": actor.nickname,
                        "job": actor.job, "damage": actor.damage,
                        "level": actor.level, "gearScore": actor.gear_score,
                        "combatPower": actor.combat_power, "healing": self.healers.get(actor.actor_id, ActorStats(actor.actor_id)).healing,
                        "skills": [{"skillCode": skill.skill_code, "name": skill_name(skill.skill_code),
                                    "damage": skill.damage, "hits": skill.hits,
                                    "minDamage": skill.min_damage if skill.hits else 0,
                                    "maxDamage": skill.max_damage, "crit": skill.crits,
                                    "back": skill.backs, "parry": skill.parries,
                                    "perfect": skill.perfects, "double": skill.doubles,
                                    "frontal": skill.frontal}
                                   for skill in actor.skills.values()]}
                       for actor in sorted(target.actors.values(), key=lambda row: row.damage, reverse=True)],
        }

    def _update_roster(self, members: dict[str, dict], complete: bool, dungeon_id: int) -> None:
        """Apply a complete roster or merge the members from a partial decode."""
        self.dungeon_id = dungeon_id
        self.roster_complete = complete
        if complete:
            self.roster = members
        else:
            self.roster.update(members)

    def _observe_self_profile(self, data: bytes) -> None:
        profile = scan_self_profile(data)
        if profile is None:
            return
        actor_id, server_id, job, level = profile
        self.local_player_id = actor_id
        self.known_players.add(actor_id)
        self.known_entities.add(actor_id)
        self.local_identity_from_game = True
        self.local_profile = {"serverId": server_id, "job": job, "level": level}

    def _actor_for(self, actor_id: int) -> ActorStats:
        actor = self.healers.setdefault(actor_id, ActorStats(actor_id))
        actor.nickname = self.names.get(actor_id, f"#{actor_id}")
        actor.job = self.jobs.get(actor_id, "")
        self._apply_roster(actor)
        return actor

    def _apply_roster(self, actor: ActorStats) -> None:
        info = self.roster.get(actor.nickname)
        if info:
            actor.job = info.get("job") or actor.job
            actor.level = info.get("level", 0)
            actor.gear_score = info.get("gearScore", 0)
            actor.combat_power = info.get("combatPower", 0)
            actor.server_id = info.get("serverId", 0)
        if actor.actor_id == self.local_player_id:
            actor.job = actor.job or str(self.local_profile.get("job", ""))
            actor.level = actor.level or int(self.local_profile.get("level", 0))
            actor.server_id = actor.server_id or int(self.local_profile.get("serverId", 0))

    def _resolve_summon(self, actor_id: int) -> int:
        seen = set()
        while actor_id in self.summon_owners and actor_id not in seen and len(seen) < 16:
            seen.add(actor_id)
            parent = self.summon_owners[actor_id]
            if parent <= 0:
                break
            actor_id = parent
        return actor_id

    def snapshot(self, mode: str = "mostDamage") -> dict:
        with self._lock:
            return self._snapshot_locked(mode)

    def _snapshot_locked(self, mode: str) -> dict:
        if not self.targets:
            return {"targetId": 0, "targetName": "", "durationMs": 0, "totalDamage": 0, "dps": 0.0, "actors": [],
                    "pingMs": self.ping_tracker.current_ms,
                    "dungeonId": self.dungeon_id,
                    "healers": [{"actorId": a.actor_id, "nickname": a.nickname, "job": a.job,
                                 "healing": a.healing, "regeneration": a.regeneration}
                                for a in sorted(self.healers.values(), key=lambda actor: actor.healing, reverse=True)]}
        if mode == "allTargets":
            target = self._combine_targets()
        else:
            targets = [self._infer_orphan_owners(deepcopy(t)) for t in self.targets.values()]
        if mode != "allTargets" and mode == "trainTargets":
            train = [t for t in targets if npc_info(t.mob_code).get("isDummy", False)]
            target = max(train or targets, key=lambda t: (t.damage, t.last_hit_ms))
        elif mode != "allTargets" and mode == "bossTargets":
            bosses = [t for t in targets if npc_info(t.mob_code).get("isBoss", False)]
            target = max(bosses or targets, key=lambda t: (t.damage, t.last_hit_ms))
        elif mode != "allTargets" and mode == "mostRecent":
            target = max(targets, key=lambda t: t.last_hit_ms)
        elif mode != "allTargets" and mode == "lastHitByMe" and self.local_player_id is not None:
            candidates = [t for t in targets if self.local_player_id in t.actors]
            target = max(candidates or targets, key=lambda t: (t.last_hit_ms, t.damage))
        elif mode != "allTargets":
            target = max(targets, key=lambda t: (t.damage, t.last_hit_ms))
        actor_map = dict(target.actors)
        for actor_id, healer in self.healers.items():
            if actor_id in actor_map:
                actor_map[actor_id].healing = healer.healing
                actor_map[actor_id].regeneration = healer.regeneration
            elif mode == "allTargets":
                actor_map[actor_id] = healer
        actors = sorted(actor_map.values(), key=lambda actor: (actor.damage, actor.healing), reverse=True)
        duration = target.duration_ms
        dps_duration = max(1_000, duration)
        total = sum(a.damage for a in actors)
        healer_rows = sorted(self.healers.values(), key=lambda actor: actor.healing, reverse=True)
        return {
            "targetId": target.target_id,
            "targetName": ("All targets" if mode == "allTargets" else npc_name(target.mob_code)
                           if target.mob_code else self.names.get(target.target_id, f"#{target.target_id}")),
            "mobCode": target.mob_code,
            "targetMaxHp": target.max_hp,
            "targetCurrentHp": target.current_hp,
            "isBoss": bool(npc_info(target.mob_code).get("isBoss", False)),
            "timeline": [{"timeMs": second * 1000, "damage": damage}
                         for second, damage in sorted(target.damage_by_second.items())],
            "timelineByActor": {str(actor_id): [{"timeMs": second * 1000, "damage": damage}
                                                  for second, damage in sorted(points.items())]
                                for actor_id, points in target.actor_damage_by_second.items()},
            "targetMode": mode,
            "dungeonId": self.dungeon_id,
            "mapId": self.map_id,
            "pingMs": self.ping_tracker.current_ms,
            "healers": [{"actorId": a.actor_id, "nickname": a.nickname, "job": a.job,
                         "healing": a.healing, "regeneration": a.regeneration,
                         "level": a.level, "gearScore": a.gear_score,
                         "combatPower": a.combat_power} for a in healer_rows],
            "durationMs": duration,
            "totalDamage": total,
            "dps": total * 1000 / dps_duration if total else 0.0,
            "actors": [{"actorId": a.actor_id, "nickname": a.nickname, "job": a.job,
                        "damage": a.damage, "dps": a.damage * 1000 / dps_duration if a.damage else 0.0,
                        "healing": a.healing, "regeneration": a.regeneration,
                        "level": a.level, "gearScore": a.gear_score,
                        "combatPower": a.combat_power, "serverId": a.server_id,
                        "contribution": a.damage / total if total else 0.0,
                        "skills": [{"skillCode": s.skill_code, "name": skill_name(s.skill_code), "damage": s.damage, "hits": s.hits,
                                   "crit": s.crits, "critRate": s.crits / s.hits if s.hits else 0.0,
                                   "back": s.backs, "backRate": s.backs / s.hits if s.hits else 0.0,
                                   "parry": s.parries, "perfect": s.perfects, "double": s.doubles,
                        "frontal": s.frontal, "multiHitCount": s.multi_hit_count,
                                   "multiHitDamage": s.multi_hit_damage,
                                   "specializationFlags": list(s.spec_flags),
                                   "minDamage": s.min_damage if s.hits else 0,
                                   "maxDamage": s.max_damage} for s in a.skills.values()]}
                       for a in actors],
        }

    def _combine_targets(self) -> TargetStats:
        combined = TargetStats(0)
        latest = max((target.last_hit_ms for target in self.targets.values()), default=0)
        cutoff = latest - self.all_targets_window_ms
        max_duration = 0
        for source in self.targets.values():
            if source.last_hit_ms < cutoff:
                continue
            combined.damage += source.damage
            max_duration = max(max_duration, source.duration_ms)
            for second, damage in source.damage_by_second.items():
                combined.damage_by_second[second] = combined.damage_by_second.get(second, 0) + damage
            for actor_id, points in source.actor_damage_by_second.items():
                merged = combined.actor_damage_by_second.setdefault(actor_id, {})
                for second, damage in points.items():
                    merged[second] = merged.get(second, 0) + damage
            for actor_id, source_actor in source.actors.items():
                actor = combined.actors.setdefault(actor_id, ActorStats(actor_id, source_actor.nickname, source_actor.job))
                actor.damage += source_actor.damage
                actor.level = source_actor.level
                actor.gear_score = source_actor.gear_score
                actor.combat_power = source_actor.combat_power
                actor.server_id = source_actor.server_id
                for key, source_skill in source_actor.skills.items():
                    skill = actor.skills.get(key)
                    if skill is None:
                        from copy import deepcopy
                        actor.skills[key] = deepcopy(source_skill)
                    else:
                        skill.damage += source_skill.damage
                        skill.hits += source_skill.hits
                        skill.min_damage = min(skill.min_damage, source_skill.min_damage)
                        skill.max_damage = max(skill.max_damage, source_skill.max_damage)
                        skill.crits += source_skill.crits
                        skill.backs += source_skill.backs
                        skill.parries += source_skill.parries
                        skill.perfects += source_skill.perfects
                        skill.doubles += source_skill.doubles
                        skill.frontal += source_skill.frontal
                        skill.multi_hit_count += source_skill.multi_hit_count
                        skill.multi_hit_damage += source_skill.multi_hit_damage
                        for index, enabled in enumerate(source_skill.spec_flags):
                            skill.spec_flags[index] |= enabled
        # Multi-target battle time is the longest selected target fight, not
        # the wall-clock span from the earliest target to the latest one.
        combined.first_hit_ms = 0
        combined.last_hit_ms = max_duration
        return self._infer_orphan_owners(combined)

    def _infer_orphan_owners(self, target: TargetStats) -> TargetStats:
        """Merge unnamed orphan summons only when a unique owner is evidenced."""
        skill_counts = {actor_id: len(actor.skills) for actor_id, actor in target.actors.items()}
        for orphan_id, orphan in list(target.actors.items()):
            if orphan_id not in target.actors or orphan.nickname and not orphan.nickname.startswith("#"):
                continue
            if orphan_id in self.summon_owners or orphan_id in self.names:
                continue
            if orphan_id in self.known_players and not orphan.job:
                continue
            owner_id = None
            if orphan.job and orphan_id not in self.known_players:
                same_job = [actor_id for actor_id, actor in target.actors.items()
                            if actor_id != orphan_id and actor.job == orphan.job
                            and actor.nickname and not actor.nickname.startswith("#")]
                if len(same_job) == 1:
                    owner_id = same_job[0]
            if owner_id is None:
                my_scalars = self.power_scalars.get(orphan_id, set())
                my_skills = skill_counts.get(orphan_id, 0)
                if not my_scalars or not my_skills:
                    continue
                needs_rotation = orphan_id in self.known_players
                candidates = []
                for candidate_id, candidate in target.actors.items():
                    if candidate_id == orphan_id or candidate_id not in self.known_players:
                        continue
                    if not candidate.nickname or candidate.nickname.startswith("#"):
                        continue
                    if orphan.job and candidate.job != orphan.job:
                        continue
                    if not orphan.job and not candidate.job:
                        continue
                    if needs_rotation and skill_counts.get(candidate_id, 0) < 3 * my_skills:
                        continue
                    if my_scalars.isdisjoint(self.power_scalars.get(candidate_id, set())):
                        continue
                    candidates.append(candidate_id)
                if len(candidates) == 1:
                    owner_id = candidates[0]
            if owner_id is None or owner_id not in target.actors:
                continue
            orphan = target.actors.pop(orphan_id)
            owner = target.actors[owner_id]
            self._merge_actor_stats(owner, orphan)
            orphan_timeline = target.actor_damage_by_second.pop(orphan_id, {})
            owner_timeline = target.actor_damage_by_second.setdefault(owner_id, {})
            for second, damage in orphan_timeline.items():
                owner_timeline[second] = owner_timeline.get(second, 0) + damage
        return target

    @staticmethod
    def _merge_actor_stats(owner: ActorStats, orphan: ActorStats) -> None:
        owner.damage += orphan.damage
        owner.healing += orphan.healing
        owner.regeneration += orphan.regeneration
        for key, source in orphan.skills.items():
            skill = owner.skills.get(key)
            if skill is None:
                owner.skills[key] = deepcopy(source)
                continue
            skill.damage += source.damage
            skill.hits += source.hits
            skill.min_damage = min(skill.min_damage, source.min_damage)
            skill.max_damage = max(skill.max_damage, source.max_damage)
            skill.crits += source.crits
            skill.backs += source.backs
            skill.parries += source.parries
            skill.perfects += source.perfects
            skill.doubles += source.doubles
            skill.frontal += source.frontal
            skill.multi_hit_count += source.multi_hit_count
            skill.multi_hit_damage += source.multi_hit_damage
            for index, enabled in enumerate(source.spec_flags):
                skill.spec_flags[index] |= enabled
