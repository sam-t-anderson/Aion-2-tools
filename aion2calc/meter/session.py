"""Retained live combat history, independent of the protocol meter's idle resets."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import time
import copy
import uuid

from .a2parser.lookup import job_from_skill, npc_info, npc_name, skill_name
from .a2parser.models import DamageEvent, HealEvent, SpecialDamage


@dataclass(frozen=True, slots=True)
class Record:
    epoch: int
    event: DamageEvent | HealEvent
    party: frozenset[str]
    local_id: int | None
    split: int = 0
    run: int = 1
    sequence: int = 0


class NoIdentifiedPlayerData(ValueError):
    """The selected scope cannot yet form an identified combat report."""


class CombatSession:
    def continuation(self):
        """A storage part continues decoding, but cannot establish run entry."""
        result = CombatSession()
        for key in ("epoch", "gap_seconds", "automatic_splits", "pvp", "manual_split",
                    "sequence", "run", "run_closed", "auto_finish", "_zone_reset", "_context"):
            setattr(result, key, getattr(self, key))
        result.final_boss_ids = set(self.final_boss_ids)
        result._dead = set(self._dead)
        result.capture_evidence = dict(self.capture_evidence)
        result.identities = {self.epoch: copy.deepcopy(self.identities[self.epoch])} if self.epoch in self.identities else {}
        result.runs = {self.run: {**self.runs[self.run], "start_observed": False}}
        if self.runs[self.run].get("start_observed") and self.runs[self.run].get("started_at") is not None:
            result.runs[self.run]["recorded_entry"] = self.runs[self.run]["started_at"]
        result.runs[self.run].pop("started_at", None)
        result._boss_attempt = copy.deepcopy(self._boss_attempt)
        result.wipe_splits = self.wipe_splits
        return result

    def __init__(self):
        self.records = deque(maxlen=400_000)
        self.epoch = 0
        self.identities = {}
        self.discarded = 0
        self.discarded_telemetry = 0
        self.discarded_segments = 0
        self.capture_evidence = {}
        self.gap_seconds = 120
        self._zone_reset = None
        self.automatic_splits = True
        self.pvp = False
        self.manual_split = 0
        self.telemetry = deque(maxlen=100_000)
        self._dead = set()
        self.sequence = 0
        self.run = 1
        self.runs = {1: {"complete":False, "recording_token":uuid.uuid4().hex, "origin_sequence":1}}
        self.run_closed = False
        self.final_boss_ids = set()
        self.auto_finish = True
        self._context = None
        self._pending_run_start = None
        self.storage_groups = 0
        self._storage_last = {}
        self._storage_groups = {}
        self.storage_players = set()
        self._boss_attempt = None
        self.wipe_splits = 0

    def _check_boss_wipe(self, timestamp_ms, engine):
        attempt = self._boss_attempt
        if not attempt:
            return
        if attempt["context"] != (self.epoch, self.manual_split, self.run):
            self._boss_attempt = None
            return
        if (not getattr(engine, "roster_complete", False)
                or frozenset(name.casefold() for name in engine.roster) != attempt["roster"]):
            self._boss_attempt = None
            return
        if any(sample["entity"] in attempt["bosses"] and
               (sample["kind"] == "death" or sample["kind"] == "hp" and sample["current"] == 0)
               for sample in engine.telemetry):
            self._boss_attempt = None
            return
        if (timestamp_ms is not None and attempt["members"] <= attempt["dead"]
                and any(hp > 0 for hp in attempt["boss_hp"].values())
                and timestamp_ms - max(attempt["last_activity"], attempt["last_death"]) >= 2000):
            # Keep the completed attempt's records. Only the next combat gets a
            # new clock; an individual death never resets the party's damage.
            self.manual_split += 1
            self.wipe_splits += 1
            self._boss_attempt = None

    def _track_boss_attempt(self, engine, record, allowed):
        event = record.event
        if not isinstance(event, DamageEvent) or self.pvp:
            return
        identity = self.identities[record.epoch]
        context = (record.epoch, self.manual_split, self.run)
        attempt = self._boss_attempt
        if attempt and attempt["context"] != context:
            self._boss_attempt = attempt = None
        if attempt and event.timestamp_ms - attempt["last_activity"] > self.gap_seconds * 1000:
            self._boss_attempt = attempt = None
        roster = frozenset(name.casefold() for name in engine.roster)
        names = Counter(name.casefold() for name in identity["names"].values())
        members = {actor for actor, name in identity["names"].items()
                   if name.casefold() in roster and names[name.casefold()] == 1
                   and actor not in identity["owners"]}
        complete = (getattr(engine, "roster_complete", False) and bool(roster)
                    and identity["local_id"] in members
                    and {identity["names"][a].casefold() for a in members} == roster)
        if not complete or attempt and (attempt["roster"] != roster or attempt["members"] != members):
            self._boss_attempt = None
            return
        boss = (event.target_id if event.actor_id in allowed and event.target_id not in allowed
                and npc_info(identity["spawns"].get(event.target_id, {}).get("mobCode")).get("isBoss") else None)
        if not attempt and boss is not None:
            attempt = {"context":context, "roster":roster, "members":members,
                       "dead":set(), "boss_hp":{}, "bosses":set(),
                       "last_activity":event.timestamp_ms, "last_death":event.timestamp_ms}
            self._boss_attempt = attempt
        if attempt:
            if boss is not None:
                attempt["bosses"].add(boss)
            if event.actor_id in members and not event.is_dot:
                attempt["dead"].discard(event.actor_id)
            if event.actor_id in allowed or event.target_id in allowed:
                attempt["last_activity"] = max(attempt["last_activity"], event.timestamp_ms)

    def finish_run(self, reason="manual", complete=True, timestamp_ms=None):
        if not any(r.run == self.run for r in self.records) or self.run_closed:
            return
        self.runs[self.run].update(complete=complete, end_reason=reason)
        last = max((r.event.timestamp_ms for r in self.records if r.run == self.run), default=0)
        self.runs[self.run]["ended_at"] = timestamp_ms if timestamp_ms is not None else last
        self.run_closed = True
        self.manual_split += 1

    def _next_run(self):
        self.run += 1
        self.runs[self.run] = {"complete":False, "recording_token":uuid.uuid4().hex, "origin_sequence":self.sequence+1}
        if self._pending_run_start is not None:
            self.runs[self.run].update(start_observed=True, started_at=self._pending_run_start)
            self._pending_run_start = None
        self.run_closed = False

    def split_now(self):
        self.manual_split += 1

    def begin_capture(self):
        self.finish_run("capture_restart", complete=False)
        self._context = None
        self.epoch += 1
        self._zone_reset = None
        self._pending_run_start = None
        if not self.run_closed:
            self.runs[self.run].update(start_observed=False)

    def observe(self, engine, events, timestamp_ms=None):
        context = (engine.map_id, engine.dungeon_id)
        if self._context is not None:
            from .a2parser.engine import OPEN_WORLD_MAPS
            old_map, old_instance = self._context
            changed = (old_instance and engine.dungeon_id and old_instance != engine.dungeon_id
                       or old_map and engine.map_id and old_map != engine.map_id
                       and not (old_instance and old_instance == engine.dungeon_id)
                       or old_instance and not engine.dungeon_id and engine.map_id in OPEN_WORLD_MAPS
                       or not old_instance and engine.dungeon_id and old_map in OPEN_WORLD_MAPS)
            if changed:
                self.finish_run("map_or_instance_change", complete=False)
            if old_map in OPEN_WORLD_MAPS and not old_instance and engine.dungeon_id:
                # Seeing an instance for the first time after starting capture is
                # not entry evidence. Require a previously observed open-world context.
                observed = timestamp_ms
                if observed is None:
                    observed = max((e.timestamp_ms for e in events), default=None)
                if observed is not None:
                    if self.run_closed:
                        self._pending_run_start = observed
                    else:
                        self.runs[self.run].update(start_observed=True, started_at=observed)
        self._context = context
        if self.run_closed and any(isinstance(e,DamageEvent) and
                (self.runs[self.run].get("end_reason") != "configured_final_boss_death"
                 or (self.epoch,e.target_id) not in self._dead
                 or engine.last_zone_reset_ms != self._zone_reset) for e in events):
            self._next_run()
        if not self.run_closed:
            self.runs[self.run].update(map_id=engine.map_id, instance_id=engine.dungeon_id)
        if engine.last_zone_reset_ms != self._zone_reset:
            if self._zone_reset is not None or engine.last_zone_reset_ms is not None:
                self.epoch += 1
            self._zone_reset = engine.last_zone_reset_ms
        identity = self.identities.setdefault(self.epoch, {"names": {}, "spawns": {}, "jobs": {}, "local_id": None, "roster": {}, "owners": {}})
        identity["player_ids"] = set(engine.known_players)
        observed = identity.setdefault("observed_players", set())
        observed.update(engine.known_players)
        observed.update(e.actor_id for e in events if isinstance(e, DamageEvent) and job_from_skill(e.skill_code))
        identity["names"].update(engine.names)
        identity["jobs"].update(engine.jobs)
        identity["spawns"].update({key: dict(value) for key, value in engine.spawn_info.items()})
        identity["roster"].update({name.casefold(): dict(value) for name, value in engine.roster.items()})
        identity["owners"].update(engine.summon_owners)
        identity["profile"] = dict(engine.local_profile)
        if engine.local_player_id is not None:
            identity["local_id"] = engine.local_player_id
        self._check_boss_wipe(timestamp_ms, engine)
        party = frozenset(name.casefold() for name in engine.roster)
        if party and "initial_roster" not in identity:
            # A capture can start before its first roster message. Reconcile only
            # those earlier records, within this identity epoch, against this
            # first observed roster; later joins/disbands must not rewrite it.
            identity["initial_roster"] = party
            identity["initial_roster_sequence"] = self.sequence
        for event in events:
            record = Record(self.epoch, event, party, engine.local_player_id, sequence=self.sequence+1)
            allowed = self._allowed(record, "party")
            self._track_boss_attempt(engine, record, allowed)
            self.storage_players.update((self.epoch, actor) for actor in allowed if actor not in identity["owners"])
            if isinstance(event, DamageEvent):
                # Count the same relevant damage groups as groups(), separately
                # for every selectable scope. Nearby NPC-only effects must not
                # force storage rollovers that clear the player's live view.
                for scope in ("self", "party", "all", "auto"):
                    selected = self._allowed(record, scope)
                    pvp = self._pvp_damage(record, selected)
                    if (self.pvp and not pvp
                            or event.actor_id not in selected and event.target_id not in selected):
                        continue
                    context_key = (self.epoch, self.manual_split, pvp)
                    previous = self._storage_last.get(scope)
                    if (previous is None or context_key != previous[0]
                            or self.automatic_splits and event.timestamp_ms - previous[1] > self.gap_seconds * 1000):
                        self._storage_groups[scope] = self._storage_groups.get(scope, 0) + 1
                    self._storage_last[scope] = (context_key, max(event.timestamp_ms, previous[1])
                                               if previous and context_key == previous[0] else event.timestamp_ms)
                self.storage_groups = max(self._storage_groups.values(), default=0)
            if len(self.records) == self.records.maxlen:
                self.discarded += 1
            self.sequence += 1
            self.records.append(Record(self.epoch, event, party, engine.local_player_id, self.manual_split, self.run, self.sequence))
        for sample in engine.telemetry:
            attempt = self._boss_attempt
            if attempt:
                actor = sample["entity"]
                if actor in attempt["bosses"]:
                    if sample["kind"] == "death" or sample["kind"] == "hp" and sample["current"] == 0:
                        self._boss_attempt = None  # Boss death is not a wipe.
                    elif sample["kind"] == "hp":
                        attempt["boss_hp"][actor] = sample["current"]
                if actor in attempt["members"]:
                    if sample["kind"] == "death":
                        attempt["dead"].add(actor)
                        attempt["last_death"] = max(attempt["last_death"], sample["timestamp_ms"])
                    elif sample["kind"] == "hp" and sample["current"] > 0:
                        attempt["dead"].discard(actor)
            key = (self.epoch, sample["entity"])
            if sample["kind"] == "hp" and sample["current"] > 0:
                self._dead.discard(key)
            if sample["kind"] == "death":
                if key in self._dead:
                    continue
                self._dead.add(key)
            if len(self.telemetry) == self.telemetry.maxlen:
                self.discarded_telemetry += 1
            self.telemetry.append({**sample, "epoch": self.epoch})
            code = identity["spawns"].get(sample["entity"], {}).get("mobCode")
            if (self.auto_finish and not self.pvp and sample["kind"] == "death"
                    and code in self.final_boss_ids and npc_info(code).get("isBoss")
                    and engine.dungeon_id == npc_info(code).get("dungeonId") and engine.dungeon_id
                    and any(r.run == self.run and isinstance(r.event,DamageEvent) and r.event.target_id == sample["entity"] and r.event.actor_id in self._allowed(r,"party") for r in self.records)):
                self.runs[self.run]["recorded_final_boss"] = code
                self.finish_run("configured_final_boss_death", timestamp_ms=sample["timestamp_ms"])
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

    def _late_roster(self, record):
        identity = self.identities[record.epoch]
        return (not record.party and bool(identity.get("initial_roster"))
                and 0 < record.sequence <= identity.get("initial_roster_sequence", 0))

    def _effective_scope(self, scope, epoch):
        if scope != "auto":
            return scope
        # Observed actors are descriptive only; never infer PvP teams or Self.
        return "party" if self.pvp or self.identities[epoch]["local_id"] is not None else "all"

    def _allowed(self, record, scope):
        identity = self.identities[record.epoch]
        scope = self._effective_scope(scope, record.epoch)
        local = record.local_id if record.local_id is not None else identity["local_id"]
        allowed = {local} if local is not None else set()
        if scope == "party":
            late = self._late_roster(record)
            party = identity["initial_roster"] if late else record.party
            counts = Counter(name.casefold() for name in identity["names"].values()) if late else {}
            allowed.update(actor_id for actor_id, name in identity["names"].items()
                           if name.casefold() in party and (not late or counts[name.casefold()] == 1))
        elif scope == "all":
            allowed.update(identity["names"])
            allowed.update(a for a in identity.get("observed_players", ())
                           if not identity["spawns"].get(a, {}).get("mobCode"))
            event = record.event
            if isinstance(event, DamageEvent) and job_from_skill(event.skill_code):
                allowed.add(event.actor_id)
        if scope == "all":
            for actor in tuple(allowed):
                seen = set()
                while actor in identity["owners"] and actor not in seen:
                    seen.add(actor)
                    actor = identity["owners"][actor]
                    if not identity["spawns"].get(actor, {}).get("mobCode"):
                        allowed.add(actor)
        # Include nested linked summons without depending on dictionary order.
        for _ in range(len(identity["owners"])):
            linked = {pet for pet, owner in identity["owners"].items() if owner in allowed}
            if linked <= allowed:
                break
            allowed.update(linked)
        return allowed

    def _allowances(self, scope):
        """Reuse membership sets within one locked read, never across updates."""
        cache = {}
        def allowed(record):
            effective = self._effective_scope(scope, record.epoch)
            actor = (record.event.actor_id if effective == "all"
                     and isinstance(record.event, DamageEvent)
                     and job_from_skill(record.event.skill_code) else None)
            key = (record.epoch, record.local_id, record.party,
                   self._late_roster(record) if effective == "party" else False, actor)
            if key not in cache:
                cache[key] = self._allowed(record, scope)
            return cache[key]
        return allowed

    def _pvp_damage(self, record, allowed):
        event = record.event
        if not isinstance(event,DamageEvent):
            return False
        identity = self.identities[record.epoch]
        opponent = event.target_id if event.actor_id in allowed else event.actor_id
        opponent = identity["owners"].get(opponent,opponent)
        return (not (event.actor_id in allowed and event.target_id in allowed)
                and opponent in identity.get("player_ids",set())
                and not identity["spawns"].get(opponent,{}).get("mobCode"))

    def groups(self, scope="party", allowed_for=None):
        allowed_for = allowed_for or self._allowances(scope)
        groups = []
        for record in self.records:
            event = record.event
            allowed = allowed_for(record)
            pvp = self._pvp_damage(record,allowed)
            if self.pvp and isinstance(event,DamageEvent) and not pvp:
                continue  # Explicit PvP mode excludes unknown NPC/player opponents.
            relevant = event.actor_id in allowed or (event.target_id in allowed)
            if not relevant:
                continue
            if isinstance(event, HealEvent):
                # Out-of-combat regeneration must not create a new fight or
                # keep adjacent pulls joined indefinitely.
                if (groups and groups[-1]["epoch"] == record.epoch
                        and groups[-1]["split"] == record.split
                        and 0 <= event.timestamp_ms - groups[-1]["last_damage"] <= self.gap_seconds * 1000):
                    groups[-1]["records"].append(record)
                    groups[-1]["end"] = max(groups[-1]["end"], event.timestamp_ms)
                continue
            outgoing = event.actor_id in allowed and event.target_id not in allowed
            if (not groups or groups[-1]["epoch"] != record.epoch or groups[-1]["split"] != record.split
                    or groups[-1]["pvp"] != pvp
                    or (self.automatic_splits and outgoing and event.timestamp_ms - groups[-1]["last_damage"] > self.gap_seconds * 1000)):
                groups.append({"id": f"{record.epoch}-{event.timestamp_ms}-{record.sequence}", "epoch": record.epoch,
                               "start": event.timestamp_ms, "end": event.timestamp_ms, "last_damage": event.timestamp_ms, "damage_start": None, "split": record.split, "run":record.run, "pvp":pvp, "records": []})
            group = groups[-1]
            if outgoing:
                if group["damage_start"] is None:
                    group["damage_start"] = event.timestamp_ms
                group["last_damage"] = max(group["last_damage"], event.timestamp_ms)
            group["end"] = max(group["end"], event.timestamp_ms)
            group["records"].append(record)
        deaths = [s for s in self.telemetry if s["kind"] == "death"]
        for group in groups:
            actors = {r.event.actor_id for r in group["records"]} | {r.event.target_id for r in group["records"]}
            for sample in deaths:
                if (sample["kind"] == "death" and sample["epoch"] == group["epoch"] and sample["entity"] in actors
                        and group["end"] <= sample["timestamp_ms"] <= group["last_damage"] + self.gap_seconds*1000):
                    group["end"] = sample["timestamp_ms"]
        self.discarded_segments = max(self.discarded_segments, len(groups) - 200)
        return groups[-200:]

    @staticmethod
    def _actor(actor_id, name, job=None):
        return {"id": str(actor_id), "name": name, "class": (job or "").lower().replace("elementalist", "spiritmaster") or None,
                "damage": 0, "hits": 0, "healing": 0, "skills": {}, "incoming": {"damage": 0, "hits": 0, "parries": 0, "sources": {}},
                "counts": {key: 0 for key in ("crit", "back", "front", "double", "perfect", "multi", "parry")}}

    def _summary(self, groups, scope, enemy_id=None, combine_pets=True, allowed_for=None):
        allowed_for = allowed_for or self._allowances(scope)
        players, enemies = {}, {}
        durations = 0
        for group in groups:
            first = group["damage_start"] if group["damage_start"] is not None else group["start"]
            buckets = {int((record.event.timestamp_ms-first)//1000) for record in group["records"]
                       if isinstance(record.event,DamageEvent)
                       and record.event.actor_id in allowed_for(record)
                       and record.event.target_id not in allowed_for(record)}
            durations += max(1,len(buckets))
        timeline = {}
        offset = 0
        for group in groups:
            identity = self.identities[group["epoch"]]
            for record in group["records"]:
                event, allowed = record.event, allowed_for(record)
                def player(actor_id):
                    # IDs may be reused after a zone/socket change: don't merge
                    # unnamed actors from unrelated contexts into one person.
                    original = actor_id
                    if combine_pets:
                        seen = set()
                        while actor_id in identity["owners"] and actor_id not in seen:
                            seen.add(actor_id)
                            actor_id = identity["owners"][actor_id]
                        if actor_id in seen:
                            actor_id = original  # Never collapse a cyclic owner reference.
                    name = self.name(record.epoch, actor_id)
                    key = f"{record.epoch}:{actor_id}"
                    job = identity["jobs"].get(actor_id) or identity["jobs"].get(identity["owners"].get(actor_id))
                    row = players.setdefault(key, self._actor(actor_id, name, job))
                    if original != actor_id:
                        row["includes_pets"] = True
                    elif actor_id in identity["owners"]:
                        row["owner"] = str(identity["owners"][actor_id])
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
                        "mob_code": identity["spawns"].get(event.target_id, {}).get("mobCode"),
                        "is_player": group["pvp"] or event.target_id in identity["names"],
                        "owner": identity["owners"].get(event.target_id), "players": {}})
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
        elapsed = sum(max(1, (group["end"] - group["start"]) / 1000) for group in groups)
        healing = sum(row["healing"] for row in players.values())
        incoming = sum(row["incoming"]["damage"] for row in players.values())
        for row in players.values():
            row["dps"] = row["damage"] / max(1, durations)
            # Healing and incoming rates use recorded encounter spans, not the
            # outgoing-only active DPS clock. Idle refreshes retain this span.
            row["hps"] = row["healing"] / max(1, elapsed)
            row["dtps"] = row["incoming"]["damage"] / max(1, elapsed)
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
                "total": total, "dps": total / max(1, durations),
                "recorded_duration": elapsed, "healing": healing, "hps": healing / max(1, elapsed),
                "damage_taken": incoming, "dtps": incoming / max(1, elapsed)}

    def snapshot(self, scope="party", segment_id=None, enemy_id=None, combine_pets=True):
        allowed_for = self._allowances(scope)
        groups = self.groups(scope, allowed_for)
        chosen = groups if segment_id == "all" else [next((g for g in groups if g["id"] == segment_id), groups[-1])] if groups else []
        summary = self._summary(chosen, scope, None, combine_pets, allowed_for)
        if enemy_id is not None:
            if any(row["key"] == enemy_id for row in summary["enemies"]):
                summary = self._summary(chosen, scope, enemy_id, combine_pets, allowed_for)
            else:
                enemy_id = None  # A previous encounter's filter must not hide a new pull.
        summary["segments"] = [{"id": group["id"], "label": f"Combat {index + 1}", "start": group["start"],
                                "duration": max(1, (group["end"] - group["start"]) / 1000),
                                "events": len(group["records"])} for index, group in enumerate(groups)]
        summary["selected_segment"] = "all" if segment_id == "all" else chosen[-1]["id"] if chosen else None
        summary["selection_mode"] = "whole" if segment_id == "all" else "encounter" if segment_id else "latest"
        summary["viewing_historical"] = bool(segment_id not in (None, "all") and chosen and chosen[-1]["id"] != groups[-1]["id"])
        summary["selected_enemy"] = enemy_id
        summary["combine_pets"] = combine_pets
        summary["wipe_splits"] = self.wipe_splits
        epochs = {g["epoch"] for g in chosen}
        actors = {(g["epoch"], actor) for g in chosen for r in g["records"]
                  for actor in (r.event.actor_id, r.event.target_id) if actor in allowed_for(r)}
        summary["identity_status"] = {
            "self_identified": bool(epochs) and all(self.identities[e]["local_id"] is not None for e in epochs),
            "unnamed_actors": sum(actor not in self.identities[e]["names"] for e, actor in actors
                                  if actor not in self.identities[e]["owners"]),
            "linked_pets": sum(actor in self.identities[e]["owners"] for e, actor in actors),
        }
        summary["paused"] = bool(chosen and time.time() * 1000 - chosen[-1]["last_damage"] >= 2000)
        summary["recorded_pvp"] = bool(chosen and chosen[-1]["pvp"])
        summary["dps_clock"] = "Shared one-second buckets with outgoing player damage; idle buckets are excluded; deaths do not reset players"
        summary["boss"] = next((row["name"] for row in summary["enemies"] if row["key"] == enemy_id), "All enemies")
        summary["scope"] = scope
        summary["warning"] = ("Waiting for your player identity. Enter your character name before Start; nearby players are excluded until you or party members are identified."
                              if self.records and not groups and scope != "all" else None)
        summary["party_roster_late"] = scope in ("party", "auto") and any(self._late_roster(r) for g in chosen for r in g["records"])
        if summary["party_roster_late"]:
            summary["warning"] = "Party roster arrived late; earlier matching effects are included. Earlier membership is unverified; Self still requires your player identity."
        summary["partial_capture"] = any(self._effective_scope(scope, g["epoch"]) == "all"
                                         or bool(self.runs[g["run"]].get("instance_id")) and not self.runs[g["run"]].get("start_observed") for g in chosen)
        if summary["partial_capture"]:
            observed = any(self._effective_scope(scope, g["epoch"]) == "all" for g in chosen)
            summary["warning"] = ("Partial capture · unranked; excluded from community learning. "
                                  + ("Showing observed players; Self and party membership are unverified. Nearby players may be included. " if observed else "Instance entry was not observed. ")
                                  + "Metrics cover recorded effects only; missing names stay as actor numbers.")
        summary["history_discarded"] = self.discarded
        return summary

    def to_a2log(self, scope="party", title=None, segment_id="all"):
        from ..combat import a2log
        allowed_for = self._allowances(scope)
        groups = self.groups(scope, allowed_for)
        if segment_id != "all":
            groups = [g for g in groups if g["id"] == segment_id] if segment_id else groups[-1:]
        players, segments = {}, []
        for index, group in enumerate(groups):
            identity = self.identities[group["epoch"]]
            hits, events, entities = [], [], {}
            resolving = set()
            actor_refs = {}
            opponents = set()
            roster_allowed = set().union(*(allowed_for(r) for r in group["records"]))
            if group["pvp"]:
                for record in group["records"]:
                    if isinstance(record.event, DamageEvent):
                        allowed_now = allowed_for(record)
                        other = record.event.target_id if record.event.actor_id in allowed_now else record.event.actor_id
                        opponents.add(identity["owners"].get(other, other))
            def reference(actor_id):
                if actor_id is None or actor_id in resolving:
                    return None
                if actor_id in actor_refs:
                    return actor_refs[actor_id]
                pid = f"{group['epoch']}:{actor_id}"
                name = self.name(group["epoch"], actor_id, actor_id not in roster_allowed)
                owners = identity["owners"]
                if actor_id in owners:
                    resolving.add(actor_id)
                    owner = reference(owners[actor_id])
                    resolving.discard(actor_id)
                    entities[pid] = {"id": pid, "name": name, "kind": "pet", "owner": owner}
                elif actor_id in roster_allowed:
                    info = identity["roster"].get(name.casefold(), {})
                    profile = identity.get("profile", {}) if actor_id == identity["local_id"] else {}
                    server = info.get("serverId") or profile.get("serverId")
                    if server and actor_id in identity["names"]:
                        pid = f"p:{server}:" + (str(info["dbid"]) if info.get("dbid") else name.casefold())
                    players[pid] = {"id": pid, "name": name, "class": identity["jobs"].get(actor_id) or info.get("job") or players.get(pid, {}).get("class"),
                        "server": str(server) if server else None,
                        "character_id": str(info["dbid"]) if info.get("dbid") else None,
                        "combat_power": info.get("combatPower"), "gear_score": info.get("gearScore")}
                elif actor_id in identity["names"]:
                    # Identified external healers are references, not party members.
                    entities[pid] = {"id": pid, "name": name, "kind": "enemy" if actor_id in opponents else "player",
                                     "is_player": True, "class": identity["jobs"].get(actor_id)}
                else:
                    code = identity["spawns"].get(actor_id, {}).get("mobCode")
                    entities[pid] = {"id": pid, "name": name, "kind": "enemy", "mob_code": code,
                        "is_boss": bool(npc_info(code).get("isBoss")) if code else False,
                        "is_player": actor_id in opponents, "class": identity["jobs"].get(actor_id)}
                actor_refs[actor_id] = pid
                return pid
            for record in group["records"]:
                event, allowed = record.event, allowed_for(record)
                source = reference(event.actor_id)
                target = reference(event.target_id)
                t = max(0, event.timestamp_ms - group["start"]) / 1000
                if isinstance(event, HealEvent):
                    events.append({"kind": "heal", "t": t, "source": source, "target": target,
                        "skill_id": event.skill_code, "skill": skill_name(event.skill_code), "amount": event.amount})
                    continue
                events.append({"kind": "damage", "t": t, "source": source, "target": target,
                    "skill_id": event.skill_code, "skill": skill_name(event.skill_code), "amount": event.total_damage})
                if event.actor_id not in allowed or event.target_id in allowed:
                    continue
                owner_id, seen = event.actor_id, set()
                while owner_id in identity["owners"] and owner_id not in seen:
                    seen.add(owner_id)
                    owner_id = identity["owners"][owner_id]
                pid = reference(owner_id)
                if pid not in players:
                    continue  # Keep observed events when an owner chain is unresolved/cyclic.
                players[pid]["class"] = players[pid].get("class") or job_from_skill(event.skill_code)
                hit = {"t": t, "player": pid, "source": source, "target": target,
                    "damage": event.total_damage, "skill_id": event.skill_code, "skill": skill_name(event.skill_code)}
                if source != pid:
                    hit["pet"] = source
                for flag, key in ((SpecialDamage.CRITICAL,"crit"),(SpecialDamage.BACK,"back"),(SpecialDamage.FRONTAL,"front"),
                                 (SpecialDamage.DOUBLE,"double"),(SpecialDamage.PERFECT,"perfect")):
                    if flag in event.specials:
                        hit[key] = True
                hits.append(hit)
            # Include the observed roster, not only players who dealt damage.
            members = {a for a in roster_allowed if a not in identity["owners"]}
            party_members = [reference(a) for a in sorted(members)]
            expected = set().union(*(set(r.party) for r in group["records"]))
            known = {identity["names"].get(a, "").casefold() for a in members}
            group_scope = self._effective_scope(scope, group["epoch"])
            roster_late = group_scope == "party" and any(self._late_roster(r) for r in group["records"])
            roster_complete = (group_scope == "party" and expected <= known and bool(expected) and bool(members) and not roster_late
                               and len({r.party for r in group["records"]}) == 1)
            health = []
            # Preserve the latest pre-pull HP evidence, bounded to 30 seconds.
            # A stale earlier full-HP sample must never override a newer low-HP sample.
            initial = {}
            for sample in self.telemetry:
                if (sample["epoch"] == group["epoch"] and sample["kind"] == "hp"
                        and group["start"]-30_000 <= sample["timestamp_ms"] <= group["start"]):
                    initial[sample["entity"]] = sample
            for actor_id, sample in initial.items():
                eid = actor_refs.get(actor_id)
                if eid in entities and entities[eid].get("is_boss"):
                    maximum = sample.get("max") or identity["spawns"].get(actor_id, {}).get("reportedMaxHp")
                    health.append({"t":0, "entity":eid, "current":sample["current"], "max":maximum})
            for sample in self.telemetry:
                if sample["epoch"] != group["epoch"] or not group["start"] <= sample["timestamp_ms"] <= group["end"]:
                    continue
                eid = actor_refs.get(sample["entity"],f"{group['epoch']}:{sample['entity']}")
                if eid not in players and eid not in entities:
                    continue
                t = (sample["timestamp_ms"] - group["start"]) / 1000
                if sample["kind"] == "death":
                    events.append({"kind": "death", "t": t, "target": eid})
                else:
                    health.append({"t": t, "entity": eid, "current": sample["current"],
                        "max": sample.get("max") or identity["spawns"].get(sample["entity"], {}).get("reportedMaxHp")})
            if hits or events:
                bosses = [e for e in entities.values() if e.get("is_boss")]
                run = self.runs[group["run"]]
                from .a2parser.engine import OPEN_WORLD_MAPS
                category = "pvp_open_world" if group["pvp"] else "pve_open_world"
                if run.get("map_id") not in OPEN_WORLD_MAPS:
                    category = "pvp_other" if group["pvp"] else "pve_unverified"
                from .context import classify
                context = classify(run.get("map_id"), run.get("instance_id"), group["pvp"], entities.values())
                category = context.get("encounter_type", category)
                entry = run.get("started_at") if run.get("start_observed") else run.get("recorded_entry")
                run_evidence = {"version":1, "token":run["recording_token"], "origin_sequence":run["origin_sequence"]}
                if entry is not None:
                    run_evidence["entry_at"] = datetime.fromtimestamp(entry/1000,timezone.utc).isoformat()
                if run.get("complete") and run.get("end_reason") == "configured_final_boss_death" and run.get("recorded_final_boss"):
                    run_evidence.update(final_boss_id=run["recorded_final_boss"],
                        finished_at=datetime.fromtimestamp(run["ended_at"]/1000,timezone.utc).isoformat())
                segments.append({**context, "recording_run":run_evidence, "run_id":str(group["run"]), "run_complete":run["complete"],
                    "run_start_observed":run.get("start_observed",False),
                    "run_started_at":datetime.fromtimestamp(run["started_at"]/1000,timezone.utc).isoformat() if run.get("started_at") is not None else None,
                    "run_ended_at":datetime.fromtimestamp(run["ended_at"]/1000,timezone.utc).isoformat() if run.get("ended_at") is not None else None,
                    "partial_capture":group_scope == "all" or bool(run.get("instance_id")) and not run.get("start_observed"),
                    "party_members":party_members, "party_roster_complete":roster_complete, "party_roster_late":roster_late,
                    "run_end_reason":run.get("end_reason", ""), "map_id":run.get("map_id",0),
                    "instance_id":run.get("instance_id",0), "encounter_type":category,
                    "ping_recorder": actor_refs.get(identity.get("local_id")),
                    "id": group["id"], "label": bosses[0]["name"] if bosses else f"Combat {index+1}",
                    "boss": bosses[0]["name"] if bosses else None,
                    "killed": any(e["kind"] == "death" and e["target"] in {b["id"] for b in bosses} for e in events),
                    "hits": hits, "events": sorted(events, key=lambda e: e["t"]), "entities": list(entities.values()), "health": health,
                    "start": datetime.fromtimestamp(group["start"] / 1000, timezone.utc).isoformat(),
                    "duration": max(0.001, (group["end"] - group["start"]) / 1000)})
        if not players:
            raise NoIdentifiedPlayerData("No identified player data is available under the selected party filter.")
        if len(players) > 64:
            raise ValueError("This session contains more than 64 player identities. Export a shorter session or use Party / Self filtering.")
        from .. import __version__
        from ..combat.quality import DECODER
        evidence = {**self.capture_evidence, "decoder":DECODER, "app_version":__version__,
                    "discarded_effects":self.discarded, "discarded_segments":self.discarded_segments,
                    "discarded_telemetry":self.discarded_telemetry}
        exported_scope = scope
        if scope == "auto":
            exported_scope = "all" if any(self._effective_scope(scope, g["epoch"]) == "all" for g in groups) else "party"
        return a2log.validate({"format":"a2log","version":1,"meta":{"source":"Aion 2 Calc live session","title":title or "Live combat session", "capture_scope":exported_scope, "capture_quality":evidence},
                               "players":list(players.values()),"segments":segments})
