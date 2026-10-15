"""Retained live combat history, independent of the protocol meter's idle resets."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import time
import copy
import math
import uuid

from .a2parser.lookup import job_from_skill, npc_info, npc_name, skill_name, spirit_skill_category
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


#: Being engaged with one enemy for at least this long (ms since first contact) marks it
#: a "major" engagement — a mini-boss or elite — so the overlay holds through its mechanic
#: lulls and segments it like a boss. The catalog does not flag mini-bosses, so this
#: sustained engagement is the inferred signal; quick trash dies well inside it and never
#: qualifies. Measured as elapsed time since first contact (not a hit span), so an early
#: mechanic pause is still covered once the threshold passes.
MAJOR_ENGAGE_MS = 12_000
#: A boss seen back at full HP only counts as a leash/reset (a fresh attempt) after our
#: damage to it has paused at least this long. Boss HP packets are sparse and can read
#: stale/over-max mid-fight, so without a real lull one spurious "full" reading would split
#: a single continuous fight into many phantom attempts. A genuine wipe/leash stops our
#: damage (party dead, or ran out of range) well beyond this; a battle-rez, where others
#: keep hitting, never pauses it. Tunable.
RESET_LULL_MS = 26_000
#: In the live view with "combine pets with owner" OFF, a summon/pet that has not dealt or
#: taken an action for at least this long is treated as de-spawned and its damage rolls into
#: its owner's row, while the owner's still-active pets keep their own rows. Without this, a
#: class that cycles many short-lived summons (a Spiritmaster's spirits) leaves a long tail
#: of tiny dead-pet rows that push off the overlay's row cap, so that damage vanishes from
#: view. Pets attack frequently, so an idle gap this long reliably means the summon is gone.
PET_DESPAWN_IDLE_MS = 8_000


def _summon_label(skill_id: int) -> str:
    # "Summon: Fire Spirit" -> "Fire Spirit": the summoned entity carries the bare name.
    return skill_name(skill_id).split(": ", 1)[-1]


#: The Spiritmaster (class 16) keeps a single "basic" elemental spirit out at a time: summoning
#: a new one replaces the one before it. So in the live view a basic spirit that a newer one has
#: replaced should fold into its owner the moment the successor appears, rather than lingering as
#: a stale row until PET_DESPAWN_IDLE_MS elapses — the spirits cycle far faster than that idle
#: window, so without this several dead basic-spirit rows pile up at once. Ancient Spirit (a
#: stigma summon) can be out alongside a basic spirit, so it is exempt from this one-at-a-time
#: replacement and only the idle rule applies to it. A summon is classified primarily by the
#: skill IDs it attacks with (see spirit_skill_category — numeric, so correct on any client
#: locale); these names, taken from the summon skills, are only a fallback for a summon that
#: hasn't attacked with an identifying skill yet.
BASIC_SPIRIT_NAMES = frozenset(_summon_label(s) for s in (16100000, 16110000, 16120000, 16130000))
ANCIENT_SPIRIT_NAME = _summon_label(16250000)


class NoIdentifiedPlayerData(ValueError):
    """The selected scope cannot yet form an identified combat report."""


class CombatSession:
    def continuation(self):
        """A storage part continues decoding, but cannot establish run entry."""
        result = CombatSession()
        for key in ("epoch", "gap_seconds", "automatic_splits", "pvp", "manual_split",
                    "sequence", "run", "run_closed", "auto_finish", "_zone_reset", "_context",
                    "reset_after_battle", "reset_delay_seconds", "reset_on_boss_start", "max_records", "dummy_record_seconds"):
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
        result._engaged_major = set(self._engaged_major)
        result._major_below = set(self._major_below)
        result._engage_span = dict(self._engage_span)
        result.reset_splits = self.reset_splits
        result._pending_reset = self._pending_reset
        result._boss_hit_ms = dict(self._boss_hit_ms)
        result.boss_splits = self.boss_splits
        result._boss_killed_ms = self._boss_killed_ms
        result._boss_killed_marker = self._boss_killed_marker
        result._live_boss_reset_ms = self._live_boss_reset_ms
        result._zone_reset_seen = False  # A continuation part never captured the run's entry.
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
        # Combat-records settings (set by the live runner from the user's UI):
        # clear the live view once combat has been idle this long, and cap how
        # many past encounters the segment list keeps. Defaults are inert so the
        # replay/offline paths and tests are unaffected until a runner opts in.
        self.reset_after_battle = False
        self.reset_delay_seconds = 5
        # Live overlay only: clear the shown stats to just the current fight the moment a boss,
        # mini-boss, field boss or world boss is engaged, so each pull starts fresh on the overlay
        # (the saved log and its segments are unchanged). On by default. See ``_since_boss_pull``.
        self.reset_on_boss_start = True
        self.max_records = 0
        self.dummy_record_seconds = 60   # standard training-dummy parse window
        self._zone_reset = None
        self.automatic_splits = True
        self.pvp = False
        self.manual_split = 0
        self.telemetry = deque(maxlen=100_000)
        self._dead = set()
        self.sequence = 0
        self.run = 1
        self.runs = {1: {"complete":False, "recording_token":uuid.uuid4().hex, "origin_sequence":1, "open_epoch":0}}
        self.run_closed = False
        self._zone_reset_seen = False
        self.final_boss_ids = set()
        self.auto_finish = True
        self._context = None
        self._pending_run_start = None
        self.storage_groups = 0
        self._storage_last = {}
        self._storage_groups = {}
        self.storage_players = set()
        self._storage_players = {}
        self._boss_attempt = None
        self.wipe_splits = 0
        # Bosses (epoch, entity) a party/self attack has engaged, and the subset seen
        # currently below full HP. A "major" engagement is a flagged boss OR any enemy
        # the party has been fighting for at least MAJOR_ENGAGE_MS (a mini-boss or elite:
        # the catalog does not flag mini-bosses, so we infer a worth-holding fight from a
        # sustained engagement, while quick trash — which dies in seconds — never qualifies
        # and still clears between pulls). A major engagement that climbs back to full HP
        # is a leash/reset (the party wiped or ran out — more reliable than player-death
        # telemetry, which is missed when its zone goes out of packet range), so it starts
        # a fresh attempt. ``reset_splits`` counts those, mirroring ``wipe_splits``.
        self._engaged_major = set()
        self._major_below = set()
        self._engage_span = {}        # (epoch, enemy not yet major) -> first-contact ms
        # (epoch, enemy) -> timestamp of the last party damage to it. A boss seen back at
        # full HP only counts as a leash/reset after a real lull (>= RESET_LULL_MS) in that
        # damage, so a stale/erratic "full" reading during continuous combat never splits it.
        self._boss_hit_ms = {}
        self.reset_splits = 0
        # Staged ("potential") reset: the local player revived after dying during a boss
        # engagement (a graveyard release / runback). Never resets on its own — a
        # battle-rez mid-fight also revives — it only becomes a real reset once an engaged
        # boss is actually seen back at full HP, which is what confirms the attempt
        # restarted. Cleared on that confirmation, and on a boss kill (which is not a reset).
        self._pending_reset = False
        # A kill ends a boss encounter. ``_boss_killed_ms`` is the time a major (boss /
        # mini-boss) enemy was last killed; when the next major boss is engaged after it,
        # that kill closes the previous encounter and the new boss starts a fresh segment —
        # so a continuous dungeon run of back-to-back bosses is split per boss instead of
        # collapsing into one long encounter. ``_boss_killed_marker`` is the (split, run)
        # the kill happened in: if any other boundary (a wipe, reset, finish or run change)
        # has since started a new segment, the pending kill is stale and never adds a
        # second split. ``boss_splits`` counts these, like ``wipe_splits`` / ``reset_splits``.
        self._boss_killed_ms = None
        self._boss_killed_marker = None
        self.boss_splits = 0
        # Timestamp of the most recent major (boss / mini-boss / field / world boss) engagement.
        # The live overlay scopes to records from here when ``reset_on_boss_start`` is on.
        self._live_boss_reset_ms = None

    def _engage_major(self, ekey, engaged_ms):
        """Mark a boss / mini-boss as engaged. If a previous boss was killed earlier in the
        same segment and this engagement is after that kill, split first so each boss is its
        own encounter. The ``engaged_ms >= kill`` guard means a trash mob already being
        fought *before* the kill (promoted to major only later) never splits the fight it
        belonged to; the marker guard means a kill already closed by another boundary never
        splits twice."""
        new_major = ekey not in self._engaged_major
        if (self._boss_killed_ms is not None and engaged_ms is not None
                and engaged_ms >= self._boss_killed_ms
                and self._boss_killed_marker == (self.manual_split, self.run)
                and new_major):
            self.manual_split += 1
            self.boss_splits += 1
            self._boss_killed_ms = None
            self._boss_killed_marker = None
        # A fresh major pull (boss / mini-boss / field / world boss) marks where the live overlay
        # resets to, so it shows just this fight when ``reset_on_boss_start`` is on. Display only.
        if new_major and engaged_ms is not None:
            self._live_boss_reset_ms = engaged_ms
        self._engaged_major.add(ekey)

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
        self._live_boss_reset_ms = None   # a new run's overlay starts unscoped until its first boss

    def _next_run(self):
        self.run += 1
        self.runs[self.run] = {"complete":False, "recording_token":uuid.uuid4().hex, "origin_sequence":self.sequence+1, "open_epoch":self.epoch}
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
        self._zone_reset_seen = False
        self._pending_run_start = None
        if not self.run_closed:
            self.runs[self.run].update(start_observed=False, open_epoch=self.epoch)

    def observe(self, engine, events, timestamp_ms=None):
        context = (engine.map_id, engine.dungeon_id)
        local_id = engine.local_player_id
        has_damage = any(isinstance(e, DamageEvent) for e in events)
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
        # A genuine zone load reassigns the local player's actor id. When the open
        # run already recorded combat and a zone reset since then reloaded the
        # player under a different id, they left and re-entered a zone (re-run, port,
        # revive into a new instance): close the run so the next damage opens a fresh
        # one. An in-instance phase teleport keeps the same actor id (and a late
        # identity resolves within the same epoch), so a mechanic that only pauses
        # DPS never resets the live view (see 0.2.121); the epoch gate requires a
        # real zone reset, not merely a first identification, before splitting.
        if (not self.run_closed and has_damage and local_id is not None
                and local_id != self.runs[self.run].get("local_id")
                and self.epoch != self.runs[self.run].get("open_epoch")
                and any(r.run == self.run for r in self.records)):
            self.finish_run("zone_reentry", complete=False)
        if self.run_closed and any(isinstance(e,DamageEvent) and
                (self.runs[self.run].get("end_reason") != "configured_final_boss_death"
                 or (self.epoch,e.target_id) not in self._dead
                 or engine.last_zone_reset_ms != self._zone_reset) for e in events):
            self._next_run()
        if not self.run_closed:
            run = self.runs[self.run]
            run.update(map_id=engine.map_id, instance_id=engine.dungeon_id)
            if has_damage and local_id is not None and run.get("local_id") is None:
                # Bind the run to the identity its combat is recorded under, not to
                # an identity packet that merely arrived before the next zone's
                # first damage (which belongs to the next run, not this one).
                run["local_id"] = local_id
            if has_damage and self._zone_reset_seen and not run.get("start_observed"):
                # This run's combat began after a zone load we captured, so its
                # instance entry was observed; the capture did not join mid-run.
                observed = timestamp_ms
                if observed is None:
                    observed = max((e.timestamp_ms for e in events if isinstance(e, DamageEvent)), default=None)
                run["start_observed"] = True
                if observed is not None and run.get("started_at") is None:
                    run["started_at"] = observed
        if engine.last_zone_reset_ms != self._zone_reset:
            if self._zone_reset is not None or engine.last_zone_reset_ms is not None:
                self.epoch += 1
                self._zone_reset_seen = True
            self._zone_reset = engine.last_zone_reset_ms
        identity = self.identities.setdefault(self.epoch, {"names": {}, "spawns": {}, "jobs": {}, "local_id": None, "roster": {}, "owners": {}})
        identity["player_ids"] = set(engine.known_players)
        observed = identity.setdefault("observed_players", set())
        observed.update(engine.known_players)
        observed.update(e.actor_id for e in events if isinstance(e, DamageEvent) and job_from_skill(e.skill_code))
        identity["names"].update(engine.names)
        identity["jobs"].update(engine.jobs)
        identity["spawns"].update({key: dict(value) for key, value in engine.spawn_info.items()})
        identity["npc_diagnostics"] = {"epoch": self.epoch, "scan_calls": engine.npc_scan_calls,
                                       "omitted": engine.npc_trace_omitted, "candidates_seen": engine.npc_candidates_seen,
                                       "records": [dict(row) for row in engine.npc_trace]}
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
            # Bound the rollover on distinct *players*, not entity ids. Keying on the actor
            # (0.2.243) stopped epoch churn from inflating this; keying on identity now stops ID
            # churn. Collapse a summon/pet to its owner and a player to its NAME, so a class that
            # spams fresh-id summons, or a party member who re-registers under a new id (after a
            # death or a phase teleport in an instance), can't look like dozens of distinct players
            # and trip the 48-player rollover again and again — which flushes a part and resets the
            # live view each time (the Vakron Sky Island / summon-heavy expedition case).
            owners, pnames, pspawns = identity["owners"], identity["names"], identity["spawns"]
            def _player_key(actor, _o=owners, _n=pnames, _s=pspawns):
                seen = set()
                while actor in _o and actor not in seen:   # a summon/pet resolves to its owner once linked,
                    seen.add(actor)                         # so its damage is attributed there, not counted apart
                    actor = _o[actor]
                if _s.get(actor, {}).get("mobCode"):        # a spawned entity (summon/pet/turret) is never a
                    return None                             # party member — unlinked, it adds nothing to the count
                name = _n.get(actor)                        # a re-registered player counts as its name
                return name.casefold() if isinstance(name, str) and name else actor
            # Only real players count toward the rollover bound; pets are excluded (None), so a
            # class' summons never increase the player total whether or not their owner link has
            # resolved — and once it does, their damage lands on the owner (see _summary).
            self.storage_players.update(
                key for a in allowed if a not in owners and (key := _player_key(a)) is not None)
            for scope in ("self", "party", "all", "auto"):
                selected = self._allowed(record, scope)
                source = selected if self._effective_scope(scope, self.epoch) == "party" \
                    else [a for a in (event.actor_id, event.target_id) if a in selected]
                keys = {key for a in source if (key := _player_key(a)) is not None}
                self._storage_players.setdefault(scope, set()).update(keys)
            if isinstance(event, DamageEvent):
                # Classify the enemies our party actually engaged, so a later return to
                # full HP (leash/reset) is told apart from an unrelated nearby enemy. An
                # enemy is "major" (worth holding through lulls, and segmented like a
                # boss) once it is a flagged boss OR we have been fighting it for at least
                # MAJOR_ENGAGE_MS — the inferred mini-boss/elite signal, since the catalog
                # does not flag mini-bosses. Quick trash dies well inside that span.
                target_code = identity["spawns"].get(event.target_id, {}).get("mobCode")
                ekey = (self.epoch, event.target_id)
                if event.actor_id in allowed and target_code:
                    self._boss_hit_ms[ekey] = event.timestamp_ms      # last party damage to this enemy
                    if len(self._boss_hit_ms) > 2048:                 # bound; keep this enemy's mark
                        self._boss_hit_ms = {ekey: event.timestamp_ms}
                if event.actor_id in allowed and target_code and ekey not in self._engaged_major:
                    if npc_info(target_code).get("isBoss"):
                        self._engage_major(ekey, event.timestamp_ms)
                    elif ekey not in self._engage_span:
                        if len(self._engage_span) > 512:   # bound: forget stale trash contacts
                            self._engage_span.clear()
                        self._engage_span[ekey] = event.timestamp_ms   # first-contact time
                # Count the same relevant damage groups as groups(), separately
                # for every selectable scope. Nearby NPC-only effects must not
                # force storage rollovers that clear the player's live view.
                for scope in ("self", "party", "all", "auto"):
                    selected = self._allowed(record, scope)
                    pvp = self._pvp_damage(record, selected)
                    if (self.pvp and not pvp
                            or event.actor_id not in selected and event.target_id not in selected):
                        continue
                    # Likewise, a storage group is a real combat segment (a manual split, a PvE/PvP
                    # switch, or a > gap_seconds lull), not an epoch tick: keeping epoch here let a
                    # zone-reset storm manufacture a new group on every bump and roll the part over.
                    context_key = (self.manual_split, pvp)
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
            if sample["kind"] == "death":
                self._engage_span.pop(key, None)   # a dead enemy's engagement span is moot
                self._boss_hit_ms.pop(key, None)   # and its last-damage mark
            if sample["kind"] == "death" and key in self._engaged_major:
                # The engaged major enemy died (a kill, not a reset): forget it, and drop
                # any staged reset so a later full-HP respawn of a new encounter is not
                # mistaken for this attempt restarting. Record the kill time so the next
                # boss engaged in this run opens a fresh encounter (split per boss).
                self._engaged_major.discard(key)
                self._major_below.discard(key)
                self._pending_reset = False
                self._boss_killed_ms = sample["timestamp_ms"]
                self._boss_killed_marker = (self.manual_split, self.run)
            if sample["kind"] == "hp" and (key in self._engaged_major or key in self._engage_span):
                # Track an engaged enemy's HP against its max (for not-yet-major contacts
                # too, so the below-full evidence is ready the moment a sustained
                # engagement is promoted mid-lull). Dropping below full marks the attempt
                # live; a *major* enemy climbing back to full confirms a leash/reset, so
                # start a fresh attempt — the reliable boundary when a wipe's player deaths
                # are missed out of range, or the party runs back to a no-lockout boss that
                # healed up. A staged potential reset (local respawn) also confirms here,
                # never on the respawn alone.
                #
                # But only a boss that climbs back to full *after a real lull in our damage*
                # is a leash/reset. Boss HP packets are sparse and erratic — stale or over-max
                # readings make the boss briefly read "full" while the party is still hitting
                # it — so without this gate a single such reading splits one continuous fight
                # into dozens of phantom "attempts". A genuine wipe/leash stops our damage
                # (everyone dead, or out of range) for well over RESET_LULL_MS before the boss
                # is seen at full, which this honours; a battle-rez, where others keep hitting,
                # never pauses our damage and so correctly never resets. The reading is still
                # recorded in telemetry below, for a whole-history log.
                maximum = sample.get("max") or identity["spawns"].get(sample["entity"], {}).get("reportedMaxHp")
                if maximum and sample["current"] < maximum:
                    self._major_below.add(key)
                elif maximum and sample["current"] >= maximum:
                    lull = sample["timestamp_ms"] - self._boss_hit_ms.get(key, sample["timestamp_ms"])
                    if lull >= RESET_LULL_MS:
                        # A real return-to-full after our damage paused: honour it.
                        if key in self._engaged_major and (key in self._major_below or self._pending_reset):
                            self.manual_split += 1
                            self.reset_splits += 1
                            self._engaged_major.discard(key)
                            self._pending_reset = False
                        self._major_below.discard(key)
                    # A "full" reading with no damage lull is spurious (a stale/over-max packet
                    # during continuous combat): ignore it entirely — no reset, and keep the
                    # below-full evidence, since the boss is not really at full.
            if sample["kind"] == "hp" and sample["current"] > 0:
                # A local-player revive after death, mid boss engagement, stages a
                # potential reset (graveyard release / runback). It commits only when an
                # engaged boss is next seen at full HP (above); a battle-rez, where the
                # boss never returns to full, never resets the meter.
                if (key in self._dead and sample["entity"] == engine.local_player_id
                        and self._engaged_major):
                    self._pending_reset = True
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
        # Promote a sustained engagement to "major" by elapsed time since first contact,
        # not just by a hit span — so a mini-boss crosses the threshold and is held even
        # when its mechanic pause comes early (the crossing lands during the lull, driven
        # by the HP packets that keep arriving, or the next idle observe).
        now_ms = timestamp_ms if timestamp_ms is not None else max((e.timestamp_ms for e in events), default=None)
        if now_ms is not None and self._engage_span:
            for ekey, first in list(self._engage_span.items()):
                if ekey[0] == self.epoch and now_ms - first >= MAJOR_ENGAGE_MS:
                    self._engage_major(ekey, first)
                    self._engage_span.pop(ekey, None)
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

    @staticmethod
    def _entry_observed(run) -> bool:
        """Whether this run's instance entry was captured — directly in this part
        (``start_observed``) or carried over from an earlier storage part as
        ``recorded_entry``. A long run that rolled over into a new archive part
        keeps its observed entry, so it must not be mis-flagged a partial capture."""
        return bool(run.get("start_observed") or run.get("recorded_entry"))

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

    def _correlate_identities(self, groups, allowed_for, self_ids):
        """Fold a player's re-registered combat actor IDs together for the live view.
        A death/revive or instance change hands the character a new actor ID, so one
        player would otherwise show as two rows. Past the authoritative local-player
        link already in ``self_ids`` (``record.local_id``), this adds a conservative
        behavioural match for party members: identical player name, a compatible
        inferred class (the same skills imply the same class), and damage activity that
        never overlaps — a hand-off, not two people hitting at the same time. Two
        different players who share a name but are active together are never merged.

        Returns ``(self_ids, rereg, rereg_name)``: ``self_ids`` grown to absorb a
        hand-off chain that includes you, ``rereg`` mapping each other re-registered ID
        to the latest-active ID of its group, and ``rereg_name`` that group's name."""
        stats = {}
        for group in groups:
            identity = self.identities[group["epoch"]]
            names, owners, jobs = identity["names"], identity["owners"], identity["jobs"]
            for record in group["records"]:
                event = record.event
                if (not isinstance(event, DamageEvent) or event.actor_id in owners
                        or event.actor_id not in allowed_for(record)):
                    continue
                label = names.get(event.actor_id)
                if not isinstance(label, str) or not label:
                    continue  # unnamed actors never correlate by name
                row = stats.setdefault(event.actor_id, {"name": label.casefold(), "display": label,
                    "jobs": set(), "first": event.timestamp_ms, "last": event.timestamp_ms})
                row["first"] = min(row["first"], event.timestamp_ms)
                row["last"] = max(row["last"], event.timestamp_ms)
                job = jobs.get(event.actor_id) or job_from_skill(event.skill_code)
                if job:
                    row["jobs"].add(job)
        by_name = {}
        for actor, row in stats.items():
            by_name.setdefault(row["name"], []).append(actor)
        rereg, rereg_name = {}, {}
        for actors in by_name.values():
            if len(actors) < 2:
                continue
            order = sorted(actors, key=lambda a: stats[a]["first"])
            disjoint = all(stats[order[i]]["last"] <= stats[order[i + 1]]["first"] for i in range(len(order) - 1))
            jobs = set().union(*(stats[a]["jobs"] for a in actors))
            if not (disjoint and len(jobs) <= 1):
                continue  # concurrent, or conflicting classes → genuinely different players
            if self_ids & set(actors):
                self_ids = self_ids | set(actors)   # a hand-off chain that includes you is all you
                continue
            canon = max(actors, key=lambda a: stats[a]["last"])
            for actor in actors:
                rereg[actor] = canon
            rereg_name[canon] = stats[canon]["display"]
        return self_ids, rereg, rereg_name

    def _summary(self, groups, scope, enemy_id=None, combine_pets=True, allowed_for=None, merge_epochs=False):
        allowed_for = allowed_for or self._allowances(scope)
        # The live view may merge the trailing groups of one continuing run that a
        # mid-fight self zone-transition (a mechanic teleport/phase) split into new
        # epochs. Within one run an actor ID is the same entity, so key by the ID
        # alone there, letting a player's totals carry across the split instead of
        # resetting. Saved logs and specific-segment views keep epoch-scoped keys.
        key_of = (lambda epoch, actor: str(actor)) if merge_epochs else (lambda epoch, actor: f"{epoch}:{actor}")
        # Merge the local player's re-registered actor IDs into one "you" row. A
        # death/revive or instance change reassigns your actor ID mid-fight, so keying
        # on the raw ID alone splits one player ("Spirited") into two. record.local_id
        # is the engine's recorded local-player ID at capture time — re-acquired after
        # a tele/port/revive — so this folds in only IDs the engine itself confirmed as
        # yours. It never merges by name, so a different player who shares your name is
        # never counted as you.
        self_ids = {r.local_id for g in groups for r in g["records"] if r.local_id is not None}
        self_canon = self_name = None
        for g in reversed(groups):
            lid = self.identities.get(g["epoch"], {}).get("local_id")
            if lid is not None:
                self_canon, self_name = lid, self.name(g["epoch"], lid)
                break
        # Beyond that authoritative link, correlate a party member's re-registered IDs
        # by behaviour (same name, compatible class, non-overlapping activity). These
        # inferred merges are flagged so the view can mark them as best-effort.
        self_ids, rereg, rereg_name = self._correlate_identities(groups, allowed_for, self_ids)
        players, enemies = {}, {}
        durations = 0
        for group in groups:
            first = group["damage_start"] if group["damage_start"] is not None else group["start"]
            buckets = {int((record.event.timestamp_ms-first)//1000) for record in group["records"]
                       if isinstance(record.event,DamageEvent)
                       and record.event.actor_id in allowed_for(record)
                       and record.event.target_id not in allowed_for(record)}
            durations += max(1,len(buckets))
        # Latest activity per actor and overall, so the live view can fold a summon that has
        # gone quiet (de-spawned) into its owner when pets are shown separately. "Now" is the
        # newest event in view; a pet idle PET_DESPAWN_IDLE_MS past it reads as gone. First-seen
        # time per actor (first_act) orders a Spiritmaster's basic spirits so a replaced one folds
        # in as soon as its successor appears — see replaced_basic below.
        now_ms, last_act, first_act = 0, {}, {}
        basic_by_owner, spirit_kind = {}, {}
        for group in groups:
            owners = self.identities[group["epoch"]]["owners"]
            for record in group["records"]:
                event = record.event
                ts, actor = event.timestamp_ms, event.actor_id
                if ts > now_ms:
                    now_ms = ts
                if ts > last_act.get(actor, 0):
                    last_act[actor] = ts
                if ts < first_act.get(actor, ts + 1):
                    first_act[actor] = ts
                # Classify a Spiritmaster summon as a "basic" elemental spirit or the
                # (coexisting) Ancient Spirit by the skill IDs it attacks with — numeric, so
                # independent of the game client's locale — and fall back to its displayed name
                # only until an identifying skill is seen. Keying on skills lets the one-at-a-time
                # replacement work on non-English clients too, where the name won't match.
                if actor in owners and actor not in spirit_kind:
                    kind = spirit_skill_category(event.skill_code) if isinstance(event, DamageEvent) else None
                    if kind is None:
                        name = self.name(group["epoch"], actor)
                        kind = "basic" if name in BASIC_SPIRIT_NAMES else ("ancient" if name == ANCIENT_SPIRIT_NAME else None)
                    if kind is not None:
                        spirit_kind[actor] = kind
                        if kind == "basic":
                            seen = set()
                            owner = actor
                            while owner in owners and owner not in seen:
                                seen.add(owner)
                                owner = owners[owner]
                            basic_by_owner.setdefault(owner, set()).add(actor)
        # A Spiritmaster can have only one basic spirit out at a time, so once a newer basic
        # spirit appears for the same owner, the earlier one is gone — fold it into the owner now
        # (even if it acted within the idle window) instead of leaving a stale row. Only basic
        # spirits that first appeared *before* the owner's newest basic spirit are superseded;
        # the current one keeps its row (and Ancient Spirit, never in this set, is untouched). If
        # two tie as newest, neither is superseded and the idle rule decides.
        replaced_basic = set()
        for owner, spirits in basic_by_owner.items():
            if len(spirits) < 2:
                continue
            newest = max(first_act.get(a, 0) for a in spirits)
            replaced_basic.update(a for a in spirits if first_act.get(a, 0) < newest)
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
                    # Collapse a pet into its owner when pets are combined, and — even when
                    # they are shown separately — once a pet has gone quiet long enough to be
                    # de-spawned, or (for a Spiritmaster's basic spirit) once a newer basic spirit
                    # has replaced it, so its damage stays on the owner instead of lingering as a
                    # dead row that falls off the overlay. The owner's still-active pets (recent
                    # activity, and the current basic spirit) keep their own rows.
                    despawned = (original in identity["owners"]
                                 and now_ms - last_act.get(original, now_ms) >= PET_DESPAWN_IDLE_MS)
                    superseded = original in replaced_basic
                    if combine_pets or despawned or superseded:
                        seen = set()
                        while actor_id in identity["owners"] and actor_id not in seen:
                            seen.add(actor_id)
                            actor_id = identity["owners"][actor_id]
                        if actor_id in seen:
                            actor_id = original  # Never collapse a cyclic owner reference.
                    pet_collapsed = original != actor_id
                    inferred = False
                    if self_canon is not None and actor_id in self_ids:
                        # All of your re-registered actor IDs are one person: one "you" row.
                        actor_id, name, key = self_canon, self_name, "self"
                    elif actor_id in rereg:
                        # A party member's re-registered IDs, correlated by behaviour.
                        actor_id = rereg[actor_id]
                        name, key, inferred = rereg_name[actor_id], f"id:{actor_id}", True
                    else:
                        name = self.name(record.epoch, actor_id)
                        key = key_of(record.epoch, actor_id)
                    job = identity["jobs"].get(actor_id) or identity["jobs"].get(identity["owners"].get(actor_id))
                    row = players.setdefault(key, self._actor(actor_id, name, job))
                    if inferred:
                        row["inferred_identity"] = True
                    if pet_collapsed:
                        row["includes_pets"] = True
                    elif actor_id in identity["owners"]:
                        row["owner"] = str(identity["owners"][actor_id])
                    if not row.get("server"):
                        # Carry each player's home server id (from the party roster, or the local
                        # profile for yourself), so the live view can show the world next to a name.
                        info = identity["roster"].get(name.casefold(), {})
                        srv = info.get("serverId") or (identity.get("profile", {}).get("serverId")
                                                        if actor_id == identity.get("local_id") else None)
                        if srv:
                            row["server"] = str(srv)
                    row["key"] = key
                    return row
                if isinstance(event, HealEvent):
                    if event.actor_id in allowed:
                        player(event.actor_id)["healing"] += event.amount
                    continue
                if event.actor_id in allowed and event.target_id not in allowed:
                    target_key = key_of(record.epoch, event.target_id)
                    enemy = enemies.setdefault(target_key, {"key": target_key, "id": str(event.target_id),
                        "name": self.name(record.epoch, event.target_id, True), "damage": 0, "hits": 0,
                        "mob_code": identity["spawns"].get(event.target_id, {}).get("mobCode"),
                        "is_player": group["pvp"] or event.target_id in identity["names"],
                        "owner": identity["owners"].get(event.target_id), "players": {},
                        "last_ms": 0, "players_last": {}})
                    enemy["damage"] += event.total_damage; enemy["hits"] += 1
                    enemy["players"][str(event.actor_id)] = enemy["players"].get(str(event.actor_id), 0) + event.total_damage
                    # Track recency so the overlay's "current target" follows the enemy
                    # being hit now, not whichever accumulated the most damage earlier.
                    enemy["last_ms"] = max(enemy["last_ms"], event.timestamp_ms)
                    enemy["players_last"][str(event.actor_id)] = event.timestamp_ms
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
                    if enemy_id and key_of(record.epoch, event.actor_id) != enemy_id:
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

    def _live_encounter(self, groups):
        """The trailing groups of the current continuing run, re-joined across
        mid-fight epoch splits. Stops at a run change or a real combat gap wider
        than ``gap_seconds`` (a genuinely separate pull), so only a mechanic's
        same-run zone transition is merged — never two distinct fights."""
        if not groups:
            return []
        chosen = [groups[-1]]
        for group in reversed(groups[:-1]):
            nxt = chosen[0]
            if group["run"] == nxt["run"] and 0 <= nxt["start"] - group["last_damage"] <= self.gap_seconds * 1000:
                chosen.insert(0, group)
            else:
                break
        return chosen

    def _since_boss_pull(self, chosen, cutoff, allowed_for):
        """Live overlay only: trim the shown encounter to records from the latest major pull
        (``cutoff`` = when a boss / mini-boss / field / world boss was engaged) onward, so each
        pull starts the overlay fresh. Rebuilds each trimmed group's timing fields the way
        ``groups`` does, so duration and DPS stay correct. Returns the view unchanged when the
        cutoff is before this encounter (nothing to trim), never an empty view."""
        if not chosen or chosen[-1]["end"] < cutoff:
            return chosen
        trimmed = []
        for group in chosen:
            if group["end"] < cutoff:
                continue
            records = [r for r in group["records"] if r.event.timestamp_ms >= cutoff]
            if not records:
                continue
            new = dict(group)
            new["records"] = records
            new["start"] = records[0].event.timestamp_ms
            new["end"] = max(r.event.timestamp_ms for r in records)
            new["damage_start"] = None
            new["last_damage"] = records[0].event.timestamp_ms
            for record in records:
                event = record.event
                allowed = allowed_for(record)
                if isinstance(event, DamageEvent) and event.actor_id in allowed and event.target_id not in allowed:
                    if new["damage_start"] is None:
                        new["damage_start"] = event.timestamp_ms
                    new["last_damage"] = max(new["last_damage"], event.timestamp_ms)
            trimmed.append(new)
        return trimmed or chosen

    def _latest_hp(self, entity_id, epochs):
        """The entity's most recent observed current HP and its max HP, within the
        shown epochs. Either may be None when HP was never captured.

        Max HP is taken from a sample observed at (or above) full HP — i.e. where
        current >= max — which is the reliable "real" max the game reports at spawn
        (this mirrors reference meters, which record max HP only when currentHp >=
        maxHp). Only when the entity was never seen at full (e.g. we joined the
        fight mid-pull) does it fall back to the largest max value seen, so a lone
        mid-fight sample can't inflate the max."""
        current, maximum, full_max, latest = None, 0, None, -1
        for sample in self.telemetry:
            if sample.get("kind") != "hp" or sample.get("entity") != entity_id or sample.get("epoch") not in epochs:
                continue
            cur, mx = sample.get("current"), sample.get("max")
            if sample["timestamp_ms"] >= latest:
                latest, current = sample["timestamp_ms"], cur
            if mx:
                maximum = max(maximum, mx)
                if cur is not None and cur >= mx:
                    full_max = mx if full_max is None else max(full_max, mx)
        return current, (full_max or maximum or None)

    def _hp_decline_rate(self, entity_id, epochs, window_ms=20000):
        """How fast the entity's observed HP is dropping, in HP per second, measured
        from its recorded HP samples over a recent window. This reflects the *real*
        rate the enemy is dying at — all damage sources, not just the observed party —
        so a time-to-kill built on it is accurate even when other players (whose
        damage the meter never sees) are also hitting it. Returns None when HP wasn't
        sampled enough to measure a drop, or when HP is flat/rising (healed/reset)."""
        samples = sorted((s["timestamp_ms"], s["current"]) for s in self.telemetry
                         if s.get("kind") == "hp" and s.get("entity") == entity_id
                         and s.get("epoch") in epochs and s.get("current") is not None)
        if len(samples) < 2:
            return None
        last_t, last_hp = samples[-1]
        window = [(t, hp) for t, hp in samples if last_t - t <= window_ms] or samples[-5:]
        first_t, first_hp = window[0]
        elapsed = (last_t - first_t) / 1000.0
        drop = first_hp - last_hp
        if elapsed <= 0 or drop <= 0:
            return None
        return drop / elapsed

    def snapshot(self, scope="party", segment_id=None, enemy_id=None, combine_pets=True):
        allowed_for = self._allowances(scope)
        groups = self.groups(scope, allowed_for)
        # Latest-encounter view (segment_id is None): follow the whole continuing
        # run, re-joining the trailing groups a mid-fight self zone-transition split
        # into new epochs (no real >gap_seconds combat break), so a mechanic that
        # pauses DPS does not reset the live meter/overlay. Explicit segment and
        # whole-session selections are unchanged.
        if segment_id == "all":
            chosen, merge = groups, False
        elif segment_id is not None:
            chosen, merge = ([next((g for g in groups if g["id"] == segment_id), groups[-1])] if groups else []), False
        else:
            chosen, merge = self._live_encounter(groups), True
            if self.reset_on_boss_start and self._live_boss_reset_ms is not None:
                chosen = self._since_boss_pull(chosen, self._live_boss_reset_ms, allowed_for)
        summary = self._summary(chosen, scope, None, combine_pets, allowed_for, merge)
        if enemy_id is not None:
            if any(row["key"] == enemy_id for row in summary["enemies"]):
                summary = self._summary(chosen, scope, enemy_id, combine_pets, allowed_for, merge)
            else:
                enemy_id = None  # A previous encounter's filter must not hide a new pull.
        segments = [{"id": group["id"], "label": f"Combat {index + 1}", "start": group["start"],
                     "duration": max(1, (group["end"] - group["start"]) / 1000),
                     "events": len(group["records"])} for index, group in enumerate(groups)]
        # Keep only the most recent records when the user caps the history.
        summary["segments"] = segments[-self.max_records:] if self.max_records else segments
        summary["selected_segment"] = "all" if segment_id == "all" else chosen[-1]["id"] if chosen else None
        summary["selection_mode"] = "whole" if segment_id == "all" else "encounter" if segment_id else "latest"
        summary["viewing_historical"] = bool(segment_id not in (None, "all") and chosen and chosen[-1]["id"] != groups[-1]["id"])
        summary["selected_enemy"] = enemy_id
        summary["combine_pets"] = combine_pets
        summary["wipe_splits"] = self.wipe_splits
        epochs = {g["epoch"] for g in chosen}
        actors = {(g["epoch"], actor) for g in chosen for r in g["records"]
                  for actor in (r.event.actor_id, r.event.target_id) if actor in allowed_for(r)}
        current_epoch = chosen[-1]["epoch"] if chosen else None
        local_id = self.identities[current_epoch]["local_id"] if current_epoch is not None else None
        summary["identity_status"] = {
            "self_identified": bool(epochs) and all(self.identities[e]["local_id"] is not None for e in epochs),
            "unnamed_actors": sum(actor not in self.identities[e]["names"] for e, actor in actors
                                  if actor not in self.identities[e]["owners"]),
            "linked_pets": sum(actor in self.identities[e]["owners"] for e, actor in actors),
            # The current run's local player, re-acquired after each zone load
            # (tele/port/revive/instance reassigns the actor id), so the overlay can
            # confirm who it is tracking once identity is picked up again.
            "local_id": local_id,
            "local_name": self.name(current_epoch, local_id) if local_id is not None else None,
            # Combat power from the same recorded character info the saved log uses
            # (identity spawns), so the overlay can show it; None when not captured.
            "local_combat_power": (self.identities[current_epoch]["spawns"].get(local_id, {}).get("combatPower")
                                   if current_epoch is not None and local_id is not None else None) or None,
        }
        idle_ms = (time.time() * 1000 - chosen[-1]["last_damage"]) if chosen else None
        summary["idle_ms"] = idle_ms
        # A major fight (boss OR a sustained mini-boss/elite) is still "live" — so a
        # multi-second pause in damage is a mechanic (shield/phase/forced movement), not
        # the end — only while BOTH the engaged enemy is still below full HP and at least
        # one party attacker is alive. Requiring a living attacker is what makes a wipe end
        # the fight: a gradual wipe holds until the last member dies, then clears;
        # respawning and re-engaging (which revives the attacker in ``_dead``) makes it
        # live again. An enemy back at full HP has leashed/reset (dropped from
        # ``_major_below``), and a dead one is not live. ``_dead`` is cleared on revive, so
        # membership in it means currently-dead. Used below to hold off "battle over".
        boss_alive = False
        if chosen:
            epoch = chosen[-1]["epoch"]
            now_ms = time.time() * 1000
            attacker_alive = fight_live = False
            for record in chosen[-1]["records"]:
                event = record.event
                if not isinstance(event, DamageEvent):
                    continue
                allowed = allowed_for(record)
                if event.actor_id in allowed and (epoch, event.actor_id) not in self._dead:
                    attacker_alive = True
                ekey = (epoch, event.target_id)
                # Major = a flagged boss / already-promoted engagement, OR a contact that
                # has been engaged >= MAJOR_ENGAGE_MS (covers an early mechanic lull before
                # the promotion pass runs). Live only while it is still below full HP.
                major = ekey in self._engaged_major or (
                    ekey in self._engage_span and now_ms - self._engage_span[ekey] >= MAJOR_ENGAGE_MS)
                if major and ekey not in self._dead and ekey in self._major_below:
                    fight_live = True
            boss_alive = fight_live and attacker_alive
        summary["boss_alive"] = boss_alive
        # A local respawn mid-engagement staged a reset that the boss returning to full
        # has not yet confirmed (e.g. a battle-rez, or still running back). Surfaced so
        # the live view can hint "attempt may be resetting" without clearing anything —
        # the actual reset only lands when boss_alive turns false.
        summary["potential_reset"] = self._pending_reset
        # Reset-after-battle: once combat has been idle past the delay, signal that
        # the fight is over so the live view can clear to a ready state. The data is
        # unchanged — a selected segment or the whole-session view still shows it. While
        # an engaged boss is still alive we hold this off until the pull is genuinely
        # abandoned (idle past the pull-gap), so a boss mechanic that halts damage for a
        # few seconds never clears or hides the overlay mid-fight.
        summary["battle_over"] = bool(self.reset_after_battle and segment_id is None
                                      and idle_ms is not None and idle_ms >= self.reset_delay_seconds * 1000
                                      and (not boss_alive or idle_ms >= self.gap_seconds * 1000))
        summary["paused"] = bool(chosen and time.time() * 1000 - chosen[-1]["last_damage"] >= 2000)
        summary["recorded_pvp"] = bool(chosen and chosen[-1]["pvp"])
        summary["dps_clock"] = "Shared one-second buckets with outgoing player damage; idle buckets are excluded; deaths do not reset players"
        summary["boss"] = next((row["name"] for row in summary["enemies"] if row["key"] == enemy_id), "All enemies")
        summary["scope"] = scope
        summary["warning"] = ("Waiting for your player identity. Teleport or change instances (zone in or out) so the game resends it, or enter your character name before Start; nearby players are excluded until you or party members are identified."
                              if self.records and not groups and scope != "all" else None)
        summary["party_roster_late"] = scope in ("party", "auto") and any(self._late_roster(r) for g in chosen for r in g["records"])
        if summary["party_roster_late"]:
            summary["warning"] = "Party roster arrived late; earlier matching effects are included. Earlier membership is unverified; Self still requires your player identity."
        # "Partial capture" only applies to instanced content with a defined entry.
        # Open-world zones (abyss, the starter/overworld maps, etc.) have no encounter
        # boundary to join mid-way, so they are never flagged partial.
        from .a2parser.engine import OPEN_WORLD_MAPS
        summary["partial_capture"] = any(self.runs[g["run"]].get("map_id") not in OPEN_WORLD_MAPS
                                         and (self._effective_scope(scope, g["epoch"]) == "all"
                                              or bool(self.runs[g["run"]].get("instance_id")) and not self._entry_observed(self.runs[g["run"]])) for g in chosen)
        if summary["partial_capture"]:
            observed = any(self._effective_scope(scope, g["epoch"]) == "all" for g in chosen)
            summary["warning"] = ("Partial capture · unranked; excluded from community learning. "
                                  + ("Showing observed players; Self and party membership are unverified. Nearby players may be included. " if observed
                                     else "Instance entry was not observed. If you did not start the meter mid-instance, this may not be a real partial capture — teleport or change instances (zone out and back) so the meter observes a fresh entry and can rank the run. ")
                                  + "Metrics cover recorded effects only; missing names stay as actor numbers.")
        # Packet-sourced combat info for the overlay: the local player's share of
        # the shown encounter, and the enemy they are hitting most with each
        # contributor's damage/DPS to it. Both are derived from the same recorded
        # damage as the player/enemy tables — nothing is invented.
        name_by_id = {row["id"]: row["name"] for row in summary["players"]}
        # Stable 1-based party number per player (by key, independent of damage
        # order) so the overlay can show "P1"/class+number instead of names.
        for index, row in enumerate(sorted(summary["players"], key=lambda r: r.get("key") or ""), start=1):
            row["party_number"] = index
        duration = max(1, summary.get("duration") or 0)
        contribution = None
        if local_id is not None:
            row = next((r for r in summary["players"] if r["id"] == str(local_id)), None)
            if row is not None:
                contribution = {"name": row["name"], "share": row["share"],
                                "damage": row["damage"], "dps": row["dps"]}
        summary["contribution"] = contribution
        current_target = None
        if summary["enemies"]:
            target = None
            if local_id is not None:
                # The enemy the local player hit most recently (then by total damage),
                # so the readout follows a target switch instead of sticking to a
                # just-killed mob with the highest accumulated damage.
                hit = [e for e in summary["enemies"] if e["players"].get(str(local_id), 0) > 0]
                if hit:
                    target = max(hit, key=lambda e: (e.get("players_last", {}).get(str(local_id), 0),
                                                      e["players"].get(str(local_id), 0)))
            # Fall back to the most recently damaged enemy overall, else the top one.
            target = target or max(summary["enemies"], key=lambda e: e.get("last_ms", 0)) or summary["enemies"][0]
            try:
                entity = int(target["id"])
            except (TypeError, ValueError):
                entity = None
            # Seconds this target was actually being hit, counted in one-second buckets
            # per group (the same way the meter measures DPS) and summed across the
            # merged live encounter. Scoping to the target — not the whole encounter —
            # keeps time spent on other enemies, and earlier pulls the live view merged
            # in, from diluting the rate and inflating time-to-kill.
            target_secs = 0
            if entity is not None:
                for group in groups:
                    base = group["damage_start"] if group["damage_start"] is not None else group["start"]
                    hit_seconds = {int((record.event.timestamp_ms - base) // 1000)
                                   for record in group["records"]
                                   if isinstance(record.event, DamageEvent) and record.event.target_id == entity
                                   and record.event.actor_id in allowed_for(record)}
                    target_secs += len(hit_seconds)
            target_secs = max(1, target_secs)
            contributors = sorted(
                [{"id": actor, "name": name_by_id.get(actor, f"Player #{actor}"),
                  "damage": dmg, "dps": dmg / target_secs} for actor, dmg in target["players"].items()],
                key=lambda c: -c["damage"])[:8]
            # Enemy HP (latest observed current, and the largest max seen) drives the
            # remaining-HP readout and the time-to-kill estimate. Both stay blank when
            # no HP was captured for this target — never guessed.
            current_hp, max_hp = self._latest_hp(entity, epochs) if entity is not None else (None, None)
            hp_pct = (current_hp / max_hp) if (current_hp is not None and max_hp) else None
            party_dps = sum(c["dps"] for c in contributors)
            # Time-to-kill from the enemy's actual observed HP-decline rate when we have
            # enough HP samples — this counts every damage source (including other
            # players we can't see, e.g. in the open world), so it matches how fast the
            # mob is really dying. Fall back to the party's DPS to this target only when
            # the HP drop can't be measured yet.
            hp_rate = self._hp_decline_rate(entity, epochs) if entity is not None else None
            if current_hp and hp_rate and hp_rate > 0:
                ttk = current_hp / hp_rate
            elif current_hp and party_dps > 0:
                ttk = current_hp / party_dps
            else:
                ttk = None
            # Fraction of the estimated whole kill that has elapsed, for the optional
            # time-based TTK bar: seconds engaged so far over (engaged + remaining).
            # Distinct from the HP bar (health remaining) — it can run ahead of or
            # behind the HP bar when the fight starts slow or finishes fast. Blank
            # whenever TTK itself is blank (never guessed).
            ttk_fraction = None
            if ttk is not None and math.isfinite(ttk) and ttk > 0:
                ttk_fraction = max(0.0, min(1.0, target_secs / (target_secs + ttk)))
            # When the local player is striking several enemies at once — AOE/cleave
            # landing in the same ~1-second bucket as the current target's latest hit —
            # the single "most-hit" target is genuinely one of several, so name the
            # others too. A sequential target switch does NOT trigger this: the mob you
            # left was last hit in an earlier second, so its bucket won't match. Scoped
            # to the local player when known (else the most recent enemies overall).
            def _recency(enemy):
                return (enemy.get("players_last", {}).get(str(local_id), 0)
                        if local_id is not None else enemy.get("last_ms", 0))
            also_targets = []
            primary_last = _recency(target)
            if primary_last:
                primary_bucket = int(primary_last // 1000)
                cohort = [e for e in summary["enemies"]
                          if e is not target and not e.get("is_player")
                          and _recency(e) and int(_recency(e) // 1000) == primary_bucket]
                also_targets = [e["name"] for e in sorted(cohort, key=lambda e: -_recency(e))][:3]
            mob_code = target.get("mob_code")
            is_dummy = bool(mob_code and npc_info(mob_code).get("isDummy"))
            current_target = {
                "name": target["name"], "key": target["key"], "damage": target["damage"],
                "is_player": target.get("is_player", False), "contributors": contributors,
                "current_hp": current_hp, "max_hp": max_hp, "hp_pct": hp_pct, "ttk": ttk,
                "ttk_fraction": ttk_fraction, "is_dummy": is_dummy, "also_targets": also_targets,
                # The enemy's NPC code, so a bound raid plan can be matched and auto-played
                # in the overlay for the fight you are in.
                "mob_code": int(mob_code) if isinstance(mob_code, int) or (isinstance(mob_code, str) and mob_code.isdigit()) else None,
            }
        summary["current_target"] = current_target
        for _enemy in summary["enemies"]:   # drop internal recency bookkeeping from the output
            _enemy.pop("last_ms", None); _enemy.pop("players_last", None)
        # Training-dummy parse: when the current target is a dummy, surface a parse
        # readout (your DPS and the party's against it, elapsed vs the standard
        # window). Packet-sourced from the recorded damage; blank off a dummy.
        dummy_parse = None
        if current_target and current_target.get("is_dummy"):
            your_dps = contribution["dps"] if contribution else None
            dummy_parse = {"name": current_target["name"], "duration": summary.get("duration") or 0,
                           "your_dps": your_dps, "target_dps": current_target["damage"] / duration,
                           "damage": current_target["damage"], "window_seconds": self.dummy_record_seconds,
                           "window_reached": (summary.get("duration") or 0) >= self.dummy_record_seconds}
        summary["dummy_parse"] = dummy_parse
        # Party-member death indicator: an actor whose latest telemetry in the shown
        # epochs is a death with no later revival (tracked live in ``_dead``).
        dead_ids = {actor for (ep, actor) in self._dead if ep in epochs}
        for row in summary["players"]:
            try:
                row["dead"] = int(row["id"]) in dead_ids
            except (TypeError, ValueError):
                row["dead"] = False
        summary["history_discarded"] = self.discarded
        return summary

    def npc_diagnostics(self, epochs=None):
        from ..combat.npc_diagnostics import clean
        selected = set(self.identities) if epochs is None else set(epochs)
        rows = [self.identities[key].get("npc_diagnostics") for key in sorted(selected)
                if key in self.identities]
        rows = [row for row in rows if row]
        return clean({"version": 1, "epochs": rows[-32:], "omitted_epochs": max(0, len(rows)-32)})

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
            group_scope = self._effective_scope(scope, group["epoch"])
            members = {a for a in roster_allowed if a not in identity["owners"]}
            if group_scope == "all":
                # Nearby named actors are not an observed party. Keep only actors
                # actually referenced by this segment; never invent roster membership.
                members = {a for a, ref in actor_refs.items() if ref in players and a not in identity["owners"]}
            party_members = [reference(a) for a in sorted(members)] if group_scope != "all" else []
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
                    "partial_capture":run.get("map_id") not in OPEN_WORLD_MAPS and (group_scope == "all" or bool(run.get("instance_id")) and not self._entry_observed(run)),
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
        if len(players) > a2log.LIMITS["players"]:
            raise ValueError(f"This session exceeds the {a2log.LIMITS['players']}-identity export safety limit. Export a shorter session or use Party / Self filtering.")
        from .. import __version__
        from ..combat.quality import DECODER
        evidence = {**self.capture_evidence, "decoder":DECODER, "app_version":__version__,
                    "discarded_effects":self.discarded, "discarded_segments":self.discarded_segments,
                    "discarded_telemetry":self.discarded_telemetry}
        npc_diagnostics = self.npc_diagnostics(g["epoch"] for g in groups)
        exported_scope = scope
        if scope == "auto":
            exported_scope = "all" if any(self._effective_scope(scope, g["epoch"]) == "all" for g in groups) else "party"
        return a2log.validate({"format":"a2log","version":1,"meta":{"source":"Aion 2 Calc live session","title":title or "Live combat session", "capture_scope":exported_scope, "capture_quality":evidence, "npc_diagnostics":npc_diagnostics},
                               "players":list(players.values()),"segments":segments})
