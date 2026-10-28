"""Retained live combat history, independent of the protocol meter's idle resets."""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import bisect
from itertools import islice
import time
import copy
import math
import struct
import uuid

from ..combat.a2log import MOVEMENT_SOURCES
from .a2parser.lookup import dungeon_final_bosses, has_skill, is_heal_skill, job_from_skill, normalize_skill, npc_info, npc_name, skill_name, spirit_skill_category
from .a2parser.models import DamageEvent, HealEvent, SpecialDamage
from .a2parser.engine import NPC_SKILLS, _own_class_skill
from .context import party_instance


#: A kept position: epoch, ms, entity, x, y, z, its MOVEMENT_SOURCES index, heading in tenths of a degree.
_POSITION = struct.Struct("<IqIfffBH")
_SOURCE_INDEX = {src: i for i, src in enumerate(MOVEMENT_SOURCES)}
_NO_HEADING = 0xFFFF


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
#: A catalog boss still holds the current fight this long after the party's last damage to it,
#: so an add promoted to major during a long untargetable phase never re-points the live overlay
#: at the add. A major inferred from a sustained engagement (an elite or mini-boss) holds it for
#: RESET_LULL_MS: one the party has not touched that long is no longer being fought.
BOSS_HOLD_MS = 120_000
#: In the live view with "combine pets with owner" OFF, a summon/pet that has not dealt or
#: taken an action for at least this long is treated as de-spawned and its damage rolls into
#: its owner's row, while the owner's still-active pets keep their own rows. Without this, a
#: class that cycles many short-lived summons (a Spiritmaster's spirits) leaves a long tail
#: of tiny dead-pet rows that push off the overlay's row cap, so that damage vanishes from
#: view. Pets attack frequently, so an idle gap this long reliably means the summon is gone.
PET_DESPAWN_IDLE_MS = 8_000
#: Your own hits of both kinds -- on the other faction's players and on NPCs -- within this long of
#: each other are one fight: at a contested field boss an area skill lands on both in the same cast,
#: and the 21 October Kaira recording cut 68 "encounters" out of a minute that way, 54 of them a second
#: or less, one to three hits each. A fight changes kind only once your hits have been of the new kind
#: alone for this long; a hit on a catalog boss still starts the boss fight at once.
MIXED_KIND_WINDOW_MS = 5_000
#: Each special-damage flag and the per-hit counter it feeds in a player's row.
_SPECIAL_COUNTS = ((SpecialDamage.CRITICAL, "crit"), (SpecialDamage.BACK, "back"), (SpecialDamage.FRONTAL, "front"),
                   (SpecialDamage.DOUBLE, "double"), (SpecialDamage.PERFECT, "perfect"), (SpecialDamage.PARRY, "parry"))


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


#: A placeholder effect for scope checks that concern an entity rather than an effect.
_PROBE = HealEvent(actor_id=0, skill_code=0, amount=0, timestamp_ms=0)


class NoIdentifiedPlayerData(ValueError):
    """The selected scope cannot yet form an identified combat report."""


def _newest(items, count):
    """The last ``count`` of ``items`` in order, taken from a deque's right end without walking the rest."""
    if count <= 0:
        return ()
    if count >= len(items):
        return items
    return list(islice(reversed(items), count))[::-1]


class _Grouping:
    """What ``CombatSession.groups`` computed last, so the next call walks only the records that arrived
    since. A value: never changed once built (the next call copies what it continues), so a detached copy
    of the session shares it, and the groups in it reach callers on the same terms. Besides the fights
    it holds what the current epoch's grouping read of its identity -- a record of each kind of scope
    membership with the set it got (``allowed``), the owner links, every actor the records involve
    (``actors``), which of them were known players, their NPC types and the epoch's count of engaged
    majors -- so ``_carry_grouping`` can tell whether a fresh walk would still read the same."""
    __slots__ = ("scope", "config", "first_seq", "last_seq", "groups", "actors_of", "peak", "death_ms", "deaths",
                 "settled", "seen_telemetry", "epoch", "identity", "allowed", "owners", "actors", "players", "codes", "majors")

    def __init__(self, scope, config, first_seq, last_seq, groups, actors_of, peak, death_ms, deaths, settled,
                 seen_telemetry, epoch, identity, allowed, owners, actors, players, codes, majors):
        self.scope, self.config, self.first_seq, self.last_seq = scope, config, first_seq, last_seq
        self.groups, self.actors_of, self.peak = groups, actors_of, peak
        self.death_ms, self.deaths, self.settled, self.seen_telemetry = death_ms, deaths, settled, seen_telemetry
        self.epoch, self.identity, self.allowed, self.owners = epoch, identity, allowed, owners
        self.actors, self.players, self.codes, self.majors = actors, players, codes, majors

    def trimmed(self, records):
        """The carried fights as fresh copies, less the records the history cap evicted since:
        ``(groups, actors_of, peak, deaths, settled)``. The oldest surviving fight keeps the start and
        the id it had, where a full walk would open it at its first surviving record."""
        groups, actors_of, peak = list(self.groups), list(self.actors_of), list(self.peak)
        deaths, settled = list(self.deaths), self.settled
        first = records[0].sequence
        if first > self.first_seq:
            while groups and groups[0]["records"][-1].sequence < first:
                del groups[0], actors_of[0], peak[0]
            if groups and groups[0]["records"][0].sequence < first:
                kept = [r for r in groups[0]["records"] if r.sequence >= first]
                groups[0] = {**groups[0], "records": kept}
                actors_of[0] = {a for r in kept for a in (r.event.actor_id, r.event.target_id)}
            if groups:   # a death closes only a fight it did not precede
                floor = groups[0]["start"]
                keep = [i for i, d in enumerate(deaths) if d["timestamp_ms"] >= floor]
                settled = sum(1 for i in keep if i < settled)
                deaths = [deaths[i] for i in keep]
            else:
                deaths, settled = [], 0
        return groups, actors_of, peak, deaths, settled


class CombatSession:
    def __deepcopy__(self, memo):
        """A detached copy for checkpoint saves and rollovers, taken under the capture lock.

        The two large collections hold immutable records (frozen dataclasses) and append-only
        telemetry samples, so they are shared through a fresh deque (milliseconds) instead of
        copied element by element: a true deep copy of a 100k-record session took 4.6 s with the
        lock held, stalling the decoder and the overlay every 15 s and overflowing the capture
        buffer on busy fights. Everything else (identities, runs, counters) is small and copied.
        A copy only exports, so it needs no held-effect state (that is for pairing what arrives next).
        The carried ``groups`` result and the clock inputs are values (never changed once built): shared."""
        clone = CombatSession.__new__(CombatSession)
        memo[id(self)] = clone
        for key, value in vars(self).items():
            if key in ("records", "telemetry", "actions", "positions"):
                setattr(clone, key, deque(value, maxlen=value.maxlen))
            elif key in ("_effects_held", "_position_kept"):
                setattr(clone, key, {})
            elif key == "_kept_from":
                setattr(clone, key, (None, None))
            elif key in ("_grouping", "clock_inputs"):
                setattr(clone, key, value)
            else:
                setattr(clone, key, copy.deepcopy(value, memo))
        return clone

    def continuation(self):
        """A storage part continues decoding, but cannot establish run entry."""
        result = CombatSession()
        for key in ("epoch", "gap_seconds", "automatic_splits", "pvp", "manual_split",
                    "sequence", "run", "run_closed", "auto_finish", "_zone_reset", "_context",
                    "reset_after_battle", "reset_delay_seconds", "reset_on_boss_start", "max_records", "dummy_record_seconds"):
            setattr(result, key, getattr(self, key))
        result.final_boss_ids = set(self.final_boss_ids)
        result._dead = set(self._dead)
        result._last_outgoing = dict(self._last_outgoing)
        result.retain_scope = self.retain_scope
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
        result.boss_kills = self.boss_kills
        result._boss_killed_ms = self._boss_killed_ms
        result._boss_killed_marker = self._boss_killed_marker
        result._live_boss_reset_ms = self._live_boss_reset_ms
        result._pull_ended_ms = self._pull_ended_ms
        result._pull_leftovers = set(self._pull_leftovers)
        result._gauge_mode = self._gauge_mode
        result._major_history = set(self._major_history)
        # A continuation part never captured the *open* run's entry (that is ``recorded_entry``
        # above). A zone load captured after the party's last combat, though, is still pending: it
        # is the entry evidence of the next run's first combat -- the storage rollover fires
        # during exactly such a pause (leaving one instance, entering the next), and forgetting the
        # load left the next run without an observed start, which a later in-instance reload then
        # mis-stamped (see observe()). The open run itself keeps its combat_seen flag, so the
        # carried load can never re-stamp it.
        last_combat = max(self._last_outgoing.values(), default=None)
        result._zone_reset_seen = bool(self._zone_reset_seen and self._zone_reset is not None
                                       and (last_combat is None or self._zone_reset > last_combat))
        result.capture_losses = []     # the new part's own window; its counters start from part_baseline
        return result

    def __init__(self):
        self.records = deque(maxlen=400_000)
        #: The last ``groups`` result, carried on by the records that arrive after it (see ``groups``).
        self._grouping = None
        #: What the last ``snapshot`` kept for ``refresh_clock``: the small sets its wall-clock fields read.
        self.clock_inputs = None
        #: Per selectable scope, when that scope last landed outgoing damage (capture wall-clock
        #: ms), kept as records arrive so "is combat still active" never walks the history.
        self._last_outgoing: dict[str, int] = {}
        #: The capture scope records are kept for (None keeps everything). In a crowd -- a world
        #: or field boss with a hundred players in range -- the other players' hits are 95%+ of
        #: the effects decoded, and keeping them filled the bounded history in minutes: forced
        #: mid-fight storage rollovers (each resetting the live view), eviction of the party's own
        #: early records, and a live snapshot that walked them all. Under a Party/Self scope only
        #: effects that involve the scope are retained; everything is still kept while the roster
        #: or the local player is unknown (late identification reconciles earlier records), and
        #: under All. Dropped effects are counted as ``out_of_scope`` (not capture loss).
        self.retain_scope = None
        self.out_of_scope = 0
        #: Capture losses placed in time -- ``(timestamp_ms, counter, count)`` -- noted by the
        #: recorder as its counters move, so each exported fight is charged only with the losses
        #: inside its own window (``capture_loss`` per segment) rather than the session's total.
        self.capture_losses = []
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
        # The splits the player asked for (New on the overlay, Split now in the app): the value
        # ``manual_split`` took at each. The live view never re-joins a fight across one.
        self._user_splits = set()
        self.telemetry = deque(maxlen=100_000)
        # The party's combat actions: skill casts and cast ends, chain windows, effects added and
        # removed (buffs on the party, debuffs and crowd control the party applied), break-gauge
        # readings. Exported per segment for the rotation, buff and break-gauge reviews.
        self.actions = deque(maxlen=400_000)
        self.discarded_actions = 0
        # Where the party, their pets and the enemies that matter were (the engine's positions), at most one
        # point per entity every POSITION_EVERY_MS, packed as _POSITION rows (a tuple of Python numbers
        # takes four times the memory): each segment's ``movement``. The recording player's own come from
        # the effects they apply and the casts aimed at them: their movement is not in the traffic
        # (docs/open-investigations.md).
        self.positions = deque(maxlen=400_000)
        self.discarded_positions = 0
        self._position_kept = {}
        self._kept_from = (None, None)
        # The held effect on each (epoch, target, instance): the game re-sends a held effect on the
        # same instance (an aura every second, a re-applied debuff), which extends the kept row
        # instead of adding one, and a removal names only the instance.
        self._effects_held = {}
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
        # Kills of a major (boss / mini-boss / field / world boss) enemy in this capture. The
        # runner's per-fight upload sends the current part once this grows (a pull ended in a
        # kill), so the recording reaches the share server during play. Carried across storage
        # parts, so within one capture it only ever grows.
        self.boss_kills = 0
        # Timestamp of the most recent major (boss / mini-boss / field / world boss) engagement.
        # The live overlay scopes to records from here when ``reset_on_boss_start`` is on.
        self._live_boss_reset_ms = None
        # When the current pull's last live major died (ms). The next outgoing damage after it
        # moves ``_live_boss_reset_ms`` there, so the overlay starts the following fight fresh
        # instead of piling trash (or the next boss) onto the finished pull's numbers.
        self._pull_ended_ms = None
        # The enemies the finished pull was still fighting when its last major died (its adds).
        # Finishing them off keeps the finished fight on the overlay; the first other enemy hit
        # starts the next view.
        self._pull_leftovers = set()
        # Set once the capture decodes a break gauge (0.2.305): from then on only a catalog boss
        # or an enemy with a gauge can reset or hold the live overlay, not a tanky trash mob
        # promoted by elapsed time. Without gauge records the elapsed-time rule applies as before.
        self._gauge_mode = False
        # Every (epoch, enemy) ever engaged as a major, never dropped on its death -- ``groups``
        # uses it to know, after the fact, that a group was a boss / mini-boss fight.
        self._major_history = set()

    @staticmethod
    def _corrected(identity, local):
        """The local id a record was stamped with, after the corrections its epoch made to a
        guessed identity (``local_corrections``: guessed id -> the corrected one)."""
        corrections = identity.get("local_corrections") or {}
        seen = set()
        while local in corrections and local not in seen:
            seen.add(local)
            local = corrections[local]
        return local

    def _first_party_hit(self, ekey, allowed_in, default_ms):
        """When the party first hit this enemy in the open fight, by the identities known now. A
        recorder the meter named only after its first hits (a meter started inside a zone, named by
        its first cast or MP record) or a member a late roster named hit the boss before it counted
        as the party's: dating the engagement from that first hit starts the live view there, so
        those hits stay on it instead of the view resetting at the first hit after the naming."""
        first = default_ms
        for record in reversed(self.records):
            if record.epoch != ekey[0] or record.run != self.run or record.split != self.manual_split:
                break
            event = record.event
            if (isinstance(event, DamageEvent) and event.target_id == ekey[1] and event.timestamp_ms < first
                    and event.actor_id in allowed_in(record, "party")):
                first = event.timestamp_ms
        return first

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
        # A fresh major pull marks where the live overlay resets to, so it shows just this fight
        # when ``reset_on_boss_start`` is on. The reset marks a fight's *start*, so it fires only
        # when no other major is still in play (``_majors_in_play``) — never when an add (or a
        # second boss) is promoted to major mid-fight while the current boss is still up, which
        # would wrongly drop the running boss DPS from the overlay. Display only; segmentation
        # above is unchanged.
        # A leftover of the finished pull (an add first hit before the boss died, promoted by
        # elapsed time afterwards) never starts a new view: it would wipe the finished fight.
        if (new_major and engaged_ms is not None and self._display_major(ekey)
                and ekey not in self._pull_leftovers and not self._majors_in_play(engaged_ms)):
            self._live_boss_reset_ms = engaged_ms
            self._pull_leftovers = set()
        self._engaged_major.add(ekey)
        if engaged_ms is not None:
            self._boss_hit_ms.setdefault(ekey, engaged_ms)   # in play from its engagement on
        if len(self._major_history) > 2048:       # bound; keep this epoch's majors
            self._major_history = {k for k in self._major_history if k[0] == self.epoch}
        self._major_history.add(ekey)

    def _display_major(self, key):
        """Whether an engaged major can reset or hold the live overlay. A catalog boss always can;
        so can an enemy with a break gauge. Trash promoted by elapsed time only counts while the
        capture has shown no gauge at all (an older build, or before the first boss)."""
        spawns = (self.identities.get(key[0]) or {}).get("spawns") or {}
        info = spawns.get(key[1]) or {}
        if npc_info(info.get("mobCode")).get("isBoss"):
            return True
        return bool(info.get("breakGauge")) if self._gauge_mode else True

    def _majors_in_play(self, now_ms, display=True):
        """The engaged majors of this epoch that still hold the current fight: able to hold it
        (``_display_major``, unless ``display`` is off), not seen dying, and damaged by the party
        within ``BOSS_HOLD_MS`` (a catalog boss, whose untargetable phases can run long) or
        ``RESET_LULL_MS`` (a major inferred from a sustained engagement) of ``now_ms``.
        With ``display`` it decides where the live overlay resets; without it, whether an enemy
        back at full health is a wipe's reset or an enemy left behind mid-fight (segmentation).

        Without the recency test, a major that left the fight unseen stayed "alive" for the rest of
        the zone and blocked every later boss-start reset, and the reset after a kill: any enemy
        the party touches is promoted to major twelve seconds after first contact unless its death
        record arrives first, so trash the party hit and moved past -- or that died without a death
        record -- kept the overlay from resetting on the next boss pull."""
        spawns = (self.identities.get(self.epoch) or {}).get("spawns") or {}
        in_play = []
        for key in self._engaged_major:
            if key[0] != self.epoch or key in self._dead or display and not self._display_major(key):
                continue
            last = self._boss_hit_ms.get(key)
            if last is None:
                continue                      # no party damage on record: not being fought
            code = (spawns.get(key[1]) or {}).get("mobCode")
            hold = BOSS_HOLD_MS if code and npc_info(code).get("isBoss") else RESET_LULL_MS
            if now_ms - last < hold:
                in_play.append(key)
        return in_play

    def _keep_actions(self, actions, identity):
        """Keep the decoded actions that concern the party: casts and cast ends by players and pets,
        casts by catalog bosses, the local player's chain windows and MP, effects on players and pets
        or applied by them (an enemy's own buffs are kept only once the party has hit that enemy),
        and break-gauge readings."""
        players, owners, epoch = identity["names"], identity["owners"], self.epoch
        local = identity.get("local_id")
        ours = lambda actor: actor in players or actor in owners or actor == local
        for action in actions:
            kind = action["kind"]
            if kind == "cast" and not ours(action["actor"]):
                code = (identity["spawns"].get(action["actor"]) or {}).get("mobCode")
                keep = bool(code) and bool(npc_info(code).get("isBoss"))
            elif kind in ("cast", "cast_end"):
                keep = ours(action["actor"])
            elif kind == "mp":
                # The game sends only the local player's MP, so readings from before the local player
                # is known are kept too; the export takes those of the player it turned out to be.
                keep = local is None or action["entity"] == local
            elif kind == "effect":
                key = (epoch, action["target"], action["instance"])
                held = self._effects_held.get(key)
                if (held is not None and held["effect"] == action["effect"] and held.get("source") == action.get("source")
                        and (held["duration_ms"] is None
                             or action["timestamp_ms"] <= held.get("refreshed_ms", held["timestamp_ms"]) + held["duration_ms"] + 1500)):
                    held["refreshed_ms"] = action["timestamp_ms"]     # still held: a refresh, not a new application
                    held["duration_ms"] = action["duration_ms"]
                    held["refreshes"] = held.get("refreshes", 0) + 1
                    continue
                keep = ours(action["target"]) or ours(action["source"]) or (epoch, action["target"]) in self._boss_hit_ms
                if not keep and held is not None:                    # the instance now holds another effect
                    held.setdefault("replaced_ms", action["timestamp_ms"])
                    del self._effects_held[key]
            elif kind == "effect_end":
                keep = self._effects_held.pop((epoch, action["target"], action["instance"]), None) is not None
            else:
                keep = True                 # chain windows (the local player's) and gauge readings
            if not keep:
                continue
            if len(self.actions) == self.actions.maxlen:
                self.discarded_actions += 1
            stored = {**action, "epoch": epoch}
            self.actions.append(stored)
            if kind == "effect":
                if len(self._effects_held) >= 10_000:
                    self._forget_lapsed_effects(action["timestamp_ms"])
                self._effects_held[(epoch, action["target"], action["instance"])] = stored

    #: one kept position per entity at most this often; a move's start and stop, a landing and a spawn always
    POSITION_EVERY_MS = 250

    def _keep_positions(self, positions, identity):
        """Keep where the party's players and pets were, and the enemies that matter: catalog bosses, and
        anything the party has hit (an open-world crowd's other movement is left out)."""
        players, owners, spawns, epoch = identity["names"], identity["owners"], identity["spawns"], self.epoch
        local = identity.get("local_id")
        if len(self._position_kept) > 50_000:
            self._position_kept.clear()
        for p in positions:
            entity, ms = p["entity"], p.get("timestamp_ms")
            if ms is None or p["src"] not in _SOURCE_INDEX or not 0 <= entity <= 0xFFFFFFFF:
                continue
            ms = int(ms)
            if not (entity in players or entity in owners or entity == local or (epoch, entity) in self._boss_hit_ms):
                code = (spawns.get(entity) or {}).get("mobCode")
                if not (code and npc_info(code).get("isBoss")):
                    continue
            key = (epoch, entity)
            last = self._position_kept.get(key)
            if last is not None and ms - last < self.POSITION_EVERY_MS and p["src"] not in ("start", "stop", "land", "spawn"):
                continue
            self._position_kept[key] = ms
            if len(self.positions) == self.positions.maxlen:
                self.discarded_positions += 1
            heading = p.get("heading")
            self.positions.append(_POSITION.pack(epoch, ms, entity, p["x"], p["y"], p["z"], _SOURCE_INDEX[p["src"]],
                                                 _NO_HEADING if heading is None else round(heading * 10) % 3600))

    def _forget_lapsed_effects(self, now_ms):
        """Drop held effects that have run out: most expiries send no removal. Permanent effects
        stay until removed, unless they alone fill the map."""
        self._effects_held = {key: held for key, held in self._effects_held.items()
                              if held["duration_ms"] is None
                              or held.get("refreshed_ms", held["timestamp_ms"]) + held["duration_ms"] + 1500 >= now_ms}
        if len(self._effects_held) >= 5_000:
            self._effects_held.clear()

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
            # The wiped pull's bosses are no longer an engagement: the run-back re-pull is a
            # fresh major, so the overlay resets for it (``_engage_major``) rather than keeping
            # the wipe's numbers up because the same boss still counted as engaged.
            self._engaged_major = {k for k in self._engaged_major if k[0] != self.epoch}
            self._major_below = {k for k in self._major_below if k[0] != self.epoch}
            self._pull_ended_ms = timestamp_ms

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
        # The overlay keeps its reset point: the run's last fight (the final boss, when its death
        # finished the run) stays on screen until new combat opens the next run. Clearing it here
        # widened the overlay from the boss fight to the whole run the moment the final boss died.

    def _next_run(self):
        self.run += 1
        self.runs[self.run] = {"complete":False, "recording_token":uuid.uuid4().hex, "origin_sequence":self.sequence+1, "open_epoch":self.epoch}
        self._live_boss_reset_ms = None   # a new run's overlay starts unscoped until its first boss
        self._pull_ended_ms = None
        self._pull_leftovers = set()
        if self._pending_run_start is not None:
            self.runs[self.run].update(start_observed=True, started_at=self._pending_run_start)
            self._pending_run_start = None
        self.run_closed = False

    def split_now(self):
        """The player's own split (New on the overlay, Split now in the app): the next combat starts
        a new encounter, and the live view starts with it (``_live_encounter``)."""
        self.manual_split += 1
        self._user_splits.add(self.manual_split)

    def note_capture_loss(self, key, count, timestamp_ms):
        """A capture counter moved by ``count`` at ``timestamp_ms`` (capture wall-clock ms)."""
        if count > 0 and timestamp_ms is not None:
            self.capture_losses.append((int(timestamp_ms), key, int(count)))
            if len(self.capture_losses) > 20_000:
                del self.capture_losses[:-10_000]

    def losses_within(self, start_ms, end_ms):
        """The timed losses charged to a fight recorded over ``[start_ms, end_ms]``: a loss noted
        up to LOSS_WINDOW_BEFORE_S before it (a TCP restart discards data buffered for seconds
        before the restart) and LOSS_WINDOW_AFTER_S after it."""
        from ..combat.quality import LOSS_WINDOW_BEFORE_S, LOSS_WINDOW_AFTER_S, TIMED_LOSS_COUNTERS
        low, high = start_ms - LOSS_WINDOW_BEFORE_S * 1000, end_ms + LOSS_WINDOW_AFTER_S * 1000
        charged = {}
        for at, key, count in self.capture_losses:
            if key in TIMED_LOSS_COUNTERS and low <= at <= high:
                charged[key] = charged.get(key, 0) + count
        return charged

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
                and any(r.run == self.run for r in self.records)
                and not self._same_instance_reload(engine)):
            self.finish_run("zone_reentry", complete=False)
        # After the final boss's death closed the run, only new combat opens the next one: not a
        # hit landing on the dead (a DoT on the corpse), nor one coming from them (the dead boss's
        # DoT still ticking on a player, which opened a run with no entry), unless a zone load came.
        if self.run_closed and any(isinstance(e,DamageEvent) and
                (self.runs[self.run].get("end_reason") != "configured_final_boss_death"
                 or ((self.epoch,e.target_id) not in self._dead and (self.epoch,e.actor_id) not in self._dead)
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
            if has_damage and not run.get("combat_seen"):
                # The run's first combat. If it began after a zone load we captured, its instance
                # entry was observed; the capture did not join mid-run. Only the *first* combat can
                # say so: a zone load later in the run (a revive, an in-instance teleport to the
                # boss room) is a reload, not an entry, and must not stamp the run's start onto
                # whatever fight follows it -- that made a dungeon clear's "entry" the final-boss
                # pull, the run's elapsed time unusable and its speed unranked.
                # A load decoded in this very batch counts too (it is recorded further down).
                loaded = self._zone_reset_seen or (engine.last_zone_reset_ms != self._zone_reset
                                                   and (self._zone_reset is not None or engine.last_zone_reset_ms is not None))
                if loaded and not run.get("start_observed"):
                    observed = timestamp_ms
                    if observed is None:
                        observed = max((e.timestamp_ms for e in events if isinstance(e, DamageEvent)), default=None)
                    run["start_observed"] = True
                    if observed is not None and run.get("started_at") is None:
                        run["started_at"] = observed
                run["combat_seen"] = True
        if engine.last_zone_reset_ms != self._zone_reset:
            if self._zone_reset is not None or engine.last_zone_reset_ms is not None:
                previous = self.identities.get(self.epoch)
                self.epoch += 1
                self._zone_reset_seen = True
                carried = (previous.get("roster") or previous.get("carried_roster")) if previous else None
                carried_entries = (previous.get("roster") or previous.get("carried_entries")) if previous else None
                if carried:
                    # A zone load (an in-instance teleport to the boss room, a re-entry) clears
                    # the engine's roster until the next roster packet, which under packet loss
                    # may arrive after the fight has begun. The party does not change on a
                    # teleport: carry its names so those first records are not "roster late"
                    # (which unranked every boss-room fight). A later roster packet that lists a
                    # different party still leaves the fight unranked (two distinct rosters).
                    # Chained loads (a teleport followed by the destination's own load seconds
                    # later, before any roster packet) carry the names on again: a capture showed
                    # two resets 7 s apart leaving the party unknown for the next 200 s -- the
                    # overlay showing only the local player, and every fight roster-late.
                    self.identities.setdefault(self.epoch, {"names": {}, "spawns": {}, "jobs": {}, "local_id": None, "roster": {}, "owners": {}})
                    self.identities[self.epoch]["carried_roster"] = frozenset(carried)
                    if carried_entries:
                        # The members' server, character id and class ride along too: until the next
                        # roster packet the party would otherwise export under bare actor ids (no
                        # server, no class) -- "identity unverified", a different-looking party, and
                        # the first fights after every revive unranked.
                        self.identities[self.epoch]["carried_entries"] = {name: dict(info) for name, info in carried_entries.items()}
            self._zone_reset = engine.last_zone_reset_ms
        identity = self.identities.setdefault(self.epoch, {"names": {}, "spawns": {}, "jobs": {}, "local_id": None, "roster": {}, "owners": {}})
        identity["player_ids"] = set(engine.known_players)
        observed = identity.setdefault("observed_players", set())
        observed.update(engine.known_players)
        observed.update(e.actor_id for e in events if isinstance(e, DamageEvent) and job_from_skill(e.skill_code))
        # Actors seen using a class skill (a hit or a heal): who fights here, for the group-instance party.
        identity.setdefault("fighters", set()).update(
            e.actor_id for e in events if isinstance(e, (DamageEvent, HealEvent)) and job_from_skill(e.skill_code))
        # Who struck with a player's own class skill, and who with an NPC's (0.2.354): an actor the capture
        # has no name or spawn record for that struck only with class skills is a player (an arena opponent,
        # a stranger in the Abyss), not an enemy of unknown type. Heals are no evidence: a draining skill's
        # heal record names the enemy it drains as its actor.
        strikes, npc_strikes = identity.setdefault("class_strikes", {}), identity.setdefault("npc_strikes", set())
        for e in events:
            if isinstance(e, DamageEvent):
                if _own_class_skill(e.skill_code):
                    strikes.setdefault(e.actor_id, job_from_skill(e.skill_code))
                elif NPC_SKILLS[0] <= e.skill_code < NPC_SKILLS[1]:
                    npc_strikes.add(e.actor_id)
        identity["names"].update(engine.names)
        identity["jobs"].update(engine.jobs)
        identity["spawns"].update({key: dict(value) for key, value in engine.spawn_info.items()})
        self._gauge_mode = self._gauge_mode or bool(getattr(engine, "break_gauge_seen", False))   # sticky
        identity["npc_diagnostics"] = {"epoch": self.epoch, "scan_calls": engine.npc_scan_calls,
                                       "omitted": engine.npc_trace_omitted, "candidates_seen": engine.npc_candidates_seen,
                                       "records": [dict(row) for row in engine.npc_trace]}
        identity["roster"].update({name.casefold(): dict(value) for name, value in engine.roster.items()})
        from .a2parser.engine import OPEN_WORLD_MAPS
        if not self.pvp and engine.map_id not in OPEN_WORLD_MAPS and party_instance(engine.dungeon_id):
            identity["party_instance"] = True      # every player in it is a party member (see ``_allowed``)
        identity["owners"].update(engine.summon_owners)
        identity["profile"] = dict(engine.local_profile)
        if engine.local_player_id is not None:
            previous = identity["local_id"]
            if previous is not None and previous != engine.local_player_id:
                # The local player changed inside one zone: a best guess from cast-ends that the self or MP
                # record superseded, an identity carried from another zone, or the player re-registered.
                # Either way the effects recorded under the old id belong to the player named now.
                identity.setdefault("local_corrections", {})[previous] = engine.local_player_id
                identity["local_corrections"].pop(engine.local_player_id, None)   # never a loop back
            identity["local_id"] = engine.local_player_id
        self._check_boss_wipe(timestamp_ms, engine)
        party = frozenset(name.casefold() for name in engine.roster) or identity.get("carried_roster", frozenset())
        if party and "initial_roster" not in identity:
            # A capture can start before its first roster message. Reconcile only
            # those earlier records, within this identity epoch, against this
            # first observed roster; later joins/disbands must not rewrite it.
            identity["initial_roster"] = party
            identity["initial_roster_sequence"] = self.sequence
        # Every event in this batch shares the identity state updated above; the allowed set for
        # a scope depends only on that, the record's party / local id and its late-roster status.
        # Memoize per batch: computing it per event and per scope walked every known name four
        # times per hit, which is what made a world-boss crowd (hundreds of names, thousands of
        # hits a second) too expensive to keep up with.
        batch_allowed = {}
        def allowed_in(record, scope):
            key = (scope, record.party, record.local_id, self._late_roster(record))
            value = batch_allowed.get(key)
            if value is None:
                value = batch_allowed[key] = self._allowed(record, scope)
            return value
        for event in events:
            record = Record(self.epoch, event, party, engine.local_player_id, sequence=self.sequence+1)
            allowed = allowed_in(record, "party")
            if (isinstance(event, DamageEvent) and not event.is_dot
                    and (self.epoch, event.actor_id) in self._dead and event.actor_id in identity["names"]):
                # A player marked dead who lands a full cast (not a lingering DoT tick) is alive:
                # the resurrection's HP sample was lost, so the overlay's death indicator would
                # otherwise stay on while they fight on.
                self._dead.discard((self.epoch, event.actor_id))
            self._track_boss_attempt(engine, record, allowed)
            if (self._pull_ended_ms is not None and isinstance(event, DamageEvent)
                    and event.timestamp_ms > self._pull_ended_ms
                    and event.actor_id in allowed and event.target_id not in allowed
                    and (self.epoch, event.target_id) not in self._pull_leftovers):
                # The pull's boss is dead and this is the next outgoing damage: a new fight. With
                # ``reset_on_boss_start`` the overlay starts fresh here, so the finished pull's
                # final numbers stay up through the lull but never absorb the trash (or the next
                # boss) that follows. Display only; segmentation is unchanged.
                if self.reset_on_boss_start:
                    self._live_boss_reset_ms = event.timestamp_ms
                self._pull_ended_ms = None
                self._pull_leftovers = set()
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
                selected = allowed_in(record, scope)
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
                        self._engage_major(ekey, self._first_party_hit(ekey, allowed_in, event.timestamp_ms))
                    elif ekey not in self._engage_span:
                        if len(self._engage_span) > 512:   # bound: forget stale trash contacts
                            self._engage_span.clear()
                        self._engage_span[ekey] = event.timestamp_ms   # first-contact time
                # Count the same relevant damage groups as groups(), separately
                # for every selectable scope. Nearby NPC-only effects must not
                # force storage rollovers that clear the player's live view.
                for scope in ("self", "party", "all", "auto"):
                    selected = allowed_in(record, scope)
                    if event.actor_id in selected and event.target_id not in selected:
                        self._last_outgoing[scope] = max(self._last_outgoing.get(scope, 0), event.timestamp_ms)
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
            if not self._retained(record, party, identity, allowed_in):
                self.out_of_scope += 1
                continue
            if len(self.records) == self.records.maxlen:
                self.discarded += 1
            self.sequence += 1
            self.records.append(Record(self.epoch, event, party, engine.local_player_id, self.manual_split, self.run, self.sequence))
        probe = Record(self.epoch, _PROBE, party, engine.local_player_id, sequence=self.sequence+1)
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
                self.boss_kills += 1
                if self._display_major(key) and not self._majors_in_play(sample["timestamp_ms"]):
                    # No other major of this pull is still in play: the pull is over. The next
                    # outgoing damage to an enemy this pull did not already fight starts the
                    # overlay fresh (see ``observe``); finishing off its adds keeps it on screen.
                    self._pull_ended_ms = sample["timestamp_ms"]
                    # Its leftovers: every enemy the party hit since the pull started, still alive.
                    start = self._live_boss_reset_ms or 0
                    self._pull_leftovers = {k for k, last in self._boss_hit_ms.items()
                                            if k[0] == self.epoch and k != key and last >= start}
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
                        # A real return-to-full after our damage paused: honour it -- unless the
                        # party is fighting another major right now. Then this one was left
                        # behind (an elite pulled, hurt and passed by, healing back once out of
                        # combat), not a wipe: it is no longer engaged, and the fight in progress
                        # goes on. Splitting there cut a boss fight in two (0.2.354).
                        if key in self._engaged_major and (key in self._major_below or self._pending_reset):
                            if any(k != key for k in self._majors_in_play(sample["timestamp_ms"], display=False)):
                                self._engaged_major.discard(key)
                            else:
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
            if not self._retained(probe, party, identity, allowed_in, entity=sample.get("entity")):
                self.out_of_scope += 1
                continue
            if len(self.telemetry) == self.telemetry.maxlen:
                self.discarded_telemetry += 1   # the append evicts the oldest sample
            self.telemetry.append({**sample, "epoch": self.epoch})
            code = identity["spawns"].get(sample["entity"], {}).get("mobCode")
            # A dungeon run finishes (and becomes rankable) when the party kills the final boss.
            # That boss is either an explicit designation (``final_boss_ids``, e.g. from an analysis
            # request) or, with none configured, the current dungeon's curated final boss from the
            # catalog — so a complete live run ranks automatically, no manual setup needed.
            if (self.auto_finish and not self.pvp and sample["kind"] == "death"
                    and (code in self.final_boss_ids or code in dungeon_final_bosses(engine.dungeon_id))
                    and npc_info(code).get("isBoss")
                    and engine.dungeon_id == npc_info(code).get("dungeonId") and engine.dungeon_id
                    and any(r.run == self.run and isinstance(r.event,DamageEvent) and r.event.target_id == sample["entity"] and r.event.actor_id in self._allowed(r,"party") for r in self.records)):
                self.runs[self.run]["recorded_final_boss"] = code
                self.finish_run("configured_final_boss_death", timestamp_ms=sample["timestamp_ms"])
        # The engine's lists hold one read's actions and positions: an observe without a new read (a settings
        # change names the character) must not keep them a second time.
        engine_actions, engine_positions = getattr(engine, "actions", None), getattr(engine, "positions", None)
        if engine_actions and engine_actions is not self._kept_from[0]:
            self._keep_actions(engine_actions, identity)
        if engine_positions and engine_positions is not self._kept_from[1]:
            self._keep_positions(engine_positions, identity)
        self._kept_from = (engine_actions, engine_positions)
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

    def _retained(self, record, party, identity, allowed_in, entity=None):
        """Whether an effect (``record``) or an HP/death sample of ``entity`` is kept under the
        capture scope. Everything is kept with no retention scope, under All, and while the
        party roster or the local player is still unknown; otherwise an effect must involve an
        actor of the scope, and a sample must be of such an actor or of an NPC (bosses and the
        enemies the party fights, whose HP the log and the live view need)."""
        scope = self.retain_scope
        if scope is None or identity["local_id"] is None or not party:
            return True
        if self._effective_scope(scope, record.epoch) == "all":
            return True
        selected = allowed_in(record, scope)
        if entity is not None:
            return entity in selected or bool(identity["spawns"].get(entity, {}).get("mobCode"))
        event = record.event
        return event.actor_id in selected or event.target_id in selected

    def _late_roster(self, record):
        identity = self.identities[record.epoch]
        return (not record.party and bool(identity.get("initial_roster"))
                and 0 < record.sequence <= identity.get("initial_roster_sequence", 0))

    def _fought_alone(self, group, identity, members, scope) -> bool:
        """A PvE fight the recording player fought alone, with no party list: its party is the player.
        The game sends no party list to a player outside a party (a two-hour recording had none until
        its party formed), so every solo fight was exported with an incomplete roster and listed with an
        unknown party size. A party list can also stay unsent for minutes while in a party, so the fight
        must hold nobody else: every actor that hit, healed or was hit is the player, one of its pets or
        an NPC the game named, and no other player hit its enemies meanwhile (with no party list every
        effect is kept, so those hits are in the session even though the fight leaves them out). Another
        player, or an actor with no NPC record, keeps the party unknown."""
        if (scope != "party" or group["pvp"] or any(r.party for r in group["records"]) or identity["roster"]
                or identity.get("carried_entries") or identity.get("initial_roster")):
            return False
        local = {self._corrected(identity, r.local_id) for r in group["records"]} | {identity["local_id"]}
        local.discard(None)
        if len(local) != 1 or set(members) != local:
            return False
        owners = identity["owners"]

        def owner(actor):
            seen = set()
            while actor in owners and actor not in seen:
                seen.add(actor)
                actor = owners[actor]
            return actor

        # In a PvE fight whatever the player hits, or is hit by, is an enemy, even one whose spawn record the
        # capture missed (a meter started inside a zone); another player can only be beside the player.
        enemies = {r.event.target_id for r in group["records"] if isinstance(r.event, DamageEvent) and owner(r.event.actor_id) in local}
        enemies |= {owner(r.event.actor_id) for r in group["records"] if isinstance(r.event, DamageEvent) and r.event.target_id in local}

        def stranger(actor):
            actor = owner(actor)
            return (bool(actor) and actor not in local and actor not in enemies
                    and not identity["spawns"].get(actor, {}).get("mobCode"))

        if any(stranger(r.event.actor_id) or stranger(r.event.target_id) for r in group["records"]):
            return False
        start, end = group["start"] - 2_000, group["end"] + 2_000
        return not any(r.epoch == group["epoch"] and start <= r.event.timestamp_ms <= end
                       and r.event.target_id in enemies | local and stranger(r.event.actor_id) for r in self.records)

    @staticmethod
    def _roster_info(identity, name) -> dict:
        """A party member's roster entry (server, character id, class, gear): this epoch's own
        roster packet first, else the entry carried across the last zone load."""
        key = str(name or "").casefold()
        return identity["roster"].get(key) or identity.get("carried_entries", {}).get(key, {})

    def _same_instance_reload(self, engine) -> bool:
        """True when the zone load that reassigned the local actor id went back into the very
        instance the open run is in: a revive after a wipe, an in-instance teleport. The party is
        still on the same run (same instance id, same map), so the run continues instead of being
        split into a second run whose later fights would carry no entry evidence. Leaving for the
        open world or another instance changes the map or instance id and still closes the run."""
        from .a2parser.engine import OPEN_WORLD_MAPS
        run = self.runs.get(self.run) or {}
        instance = run.get("instance_id")
        # Only an instance the decoder *restored* across the reload counts: a genuine re-entry
        # of the same dungeon arrives with its own roster/entry packet (which names the
        # instance afresh and clears the restore flag) and still opens a new run.
        return bool(instance and getattr(engine, "instance_restored", False) and engine.dungeon_id == instance
                    and engine.map_id == run.get("map_id") and engine.map_id not in OPEN_WORLD_MAPS)

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
        local = self._corrected(identity, record.local_id if record.local_id is not None else identity["local_id"])
        allowed = {local} if local is not None else set()
        if scope == "party":
            late = self._late_roster(record)
            party = identity["initial_roster"] if late else record.party
            counts = Counter(name.casefold() for name in identity["names"].values()) if late else {}
            allowed.update(actor_id for actor_id, name in identity["names"].items()
                           if name.casefold() in party and (not late or counts[name.casefold()] == 1))
            if identity.get("party_instance"):
                # A group instance (a dungeon, a raid) holds only the party, so every named player fighting in
                # it is a member even when the roster packet decoded short. Their effects were otherwise dropped
                # as out of scope: a roster that read one member of five kept under a third of each boss's damage.
                allowed.update(a for a in identity.get("fighters", ()) if a in identity["names"]
                               and a not in identity["owners"] and not identity["spawns"].get(a, {}).get("mobCode"))
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
        """Reuse membership sets within one locked read, never across updates. The callable's
        ``key_of`` names what a record's membership depends on (``groups`` keeps one record per key)."""
        cache, by_record = {}, {}
        def key_of(record):
            effective = self._effective_scope(scope, record.epoch)
            actor = (record.event.actor_id if effective == "all"
                     and isinstance(record.event, DamageEvent)
                     and job_from_skill(record.event.skill_code) else None)
            return (record.epoch, record.local_id, record.party,
                    self._late_roster(record) if effective == "party" else False, actor)
        def allowed(record):
            # A summary asks for the same record's membership several times over; the second
            # answer is a lookup by its sequence rather than the key computed again (0.2.336).
            found = by_record.get(record.sequence)
            if found is not None:
                return found
            key = key_of(record)
            if key not in cache:
                cache[key] = self._allowed(record, scope)
            found = by_record[record.sequence] = cache[key]
            return found
        allowed.key_of = key_of
        return allowed

    def _pvp_damage(self, record, allowed):
        event = record.event
        if not isinstance(event,DamageEvent) or is_heal_skill(event.skill_code):
            return False   # healing is never a hostile act, whoever receives it
        identity = self.identities[record.epoch]
        opponent = event.target_id if event.actor_id in allowed else event.actor_id
        opponent = identity["owners"].get(opponent,opponent)
        return (not (event.actor_id in allowed and event.target_id in allowed)
                and opponent in identity.get("player_ids",set())
                and not identity["spawns"].get(opponent,{}).get("mobCode"))

    def groups(self, scope="party", allowed_for=None):
        """The scope's records cut into fights: a new epoch or manual split, a PvE/PvP switch or, with
        automatic splits, a lull longer than ``gap_seconds`` between your side's hits starts the next
        one, and each enemy's death closes the one fight still fighting it. Returns the newest 200.

        Carried on from the previous call (``_Grouping``) by the records that arrived since, so the
        live view's cost follows the current fight rather than the session: walking every record each
        time cost a two-hour session a quarter second per reading, most of a core (0.2.336). What is
        carried is what a fresh walk gives. Earlier epochs are frozen (``observe`` writes only the
        current epoch's identity); the current epoch's records are kept while every input their
        grouping read still reads the same (``_carry_grouping``), else they are walked again. Of the
        enemy deaths, those since the open fight began are re-applied each call; an earlier one is
        settled, since it can close none of the fights to come."""
        allowed_for = allowed_for or self._allowances(scope)
        key_of = getattr(allowed_for, "key_of", None)
        config = (self.pvp, self.gap_seconds, self.automatic_splits)
        carried = self._carry_grouping(scope, config, allowed_for) if key_of is not None else None
        records = self.records
        if carried is None:
            groups, actors_of, peak, death_ms, deaths, settled, seen_telemetry = [], [], [], {}, [], 0, 0
            new_records = records
        else:
            groups, actors_of, peak, deaths, settled = carried.trimmed(records)
            death_ms, seen_telemetry = dict(carried.death_ms), carried.seen_telemetry
            new_records = _newest(records, records[-1].sequence - carried.last_seq)
            if groups:   # the open fight continues on a copy: the carried one is a shared value
                last = groups[-1]
                groups[-1] = {**last, "records": list(last["records"]), "majors": set(last["majors"])}
                actors_of[-1] = set(actors_of[-1])
        # When each enemy died, (epoch, entity) -> ms, from the recorded deaths. A boss fight is
        # live until its boss dies; that decides below whether a stray effect may cut it.
        seen_now = len(self.telemetry) + self.discarded_telemetry
        for sample in _newest(self.telemetry, seen_now - seen_telemetry):
            if sample["kind"] == "death":
                deaths.append(sample)
                death_ms.setdefault((sample["epoch"], sample["entity"]), sample["timestamp_ms"])
        major_cache = {}
        def is_major(epoch, enemy):
            key = (epoch, enemy)
            if key not in major_cache:
                code = self.identities.get(epoch, {}).get("spawns", {}).get(enemy, {}).get("mobCode")
                major_cache[key] = key in self._major_history or bool(code and npc_info(code).get("isBoss"))
            return major_cache[key]
        # What the current epoch's grouping reads of its identity, for the next call's check.
        current = self.epoch
        identity_now = self.identities.get(current) or {}
        owners_now = identity_now.get("owners", {})
        if carried is not None and carried.epoch == current:
            reps, actors = dict(carried.allowed), set(carried.actors)
        else:
            reps, actors = {}, set()
        for record in new_records:
            event = record.event
            allowed = allowed_for(record)
            if record.epoch == current and key_of is not None:
                key = key_of(record)
                if key not in reps:
                    reps[key] = (record, frozenset(allowed))
                actor, target = event.actor_id, event.target_id
                actors.update((actor, target, owners_now.get(actor, actor), owners_now.get(target, target)))
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
                    actors_of[-1].update((event.actor_id, event.target_id))
                continue
            outgoing = event.actor_id in allowed and event.target_id not in allowed
            switched = bool(groups) and groups[-1]["pvp"] != pvp
            if switched and not outgoing:
                # Only your own side's hits decide what you are fighting. Where players and NPCs
                # both strike you -- the Abyss, a field boss's crowd of both factions -- a hit taken
                # from the other kind is no new encounter: each one cut a segment, ten in a third
                # of a second at one death in the Abyss. The hit joins the current one.
                switched = False
            elif (switched and groups[-1]["damage_start"] is None and groups[-1]["epoch"] == record.epoch
                    and groups[-1]["split"] == record.split):
                # The hits you took before your own first one belong to that fight.
                groups[-1]["pvp"] = pvp
                switched = False
            elif (switched and groups[-1]["epoch"] == record.epoch and groups[-1]["split"] == record.split
                    and groups[-1]["kind_damage"] is not None
                    and 0 <= event.timestamp_ms - groups[-1]["kind_damage"] <= MIXED_KIND_WINDOW_MS
                    and not (not pvp and is_major(record.epoch, event.target_id))):
                # Your own hits of both kinds within seconds of each other: an area skill at a
                # contested field boss strikes the other faction's players and the NPCs around it in
                # the same cast. The hit joins the fight; its kind changes only once your hits have
                # been of the new kind alone for MIXED_KIND_WINDOW_MS. A hit on a boss is the exception:
                # it starts the boss fight, whatever you struck just before.
                switched = False
            if (switched and pvp and groups[-1]["epoch"] == record.epoch and groups[-1]["split"] == record.split
                    and any(death_ms.get((record.epoch, enemy), float("inf")) > event.timestamp_ms
                            for enemy in groups[-1]["majors"])):
                # A PvE boss / mini-boss fight that is still live is one encounter. A single
                # player-vs-player-looking effect in the middle of it -- a party member's AoE or
                # pet clipping an allied NPC the game registers as a player, an unmapped support
                # skill landing on an ally -- is not a switch to PvP and must not cut the fight
                # in two (and back again on the next boss hit): that shredded one pull into
                # dozens of "encounters" and reset the overlay on every cast. The effect joins
                # the fight. A real PvP fight still starts its own encounter once the boss is
                # dead, and explicit PvP mode is unaffected.
                switched = False
            if (not groups or groups[-1]["epoch"] != record.epoch or groups[-1]["split"] != record.split
                    or switched
                    or (self.automatic_splits and outgoing and event.timestamp_ms - groups[-1]["last_damage"] > self.gap_seconds * 1000)):
                groups.append({"id": f"{record.epoch}-{event.timestamp_ms}-{record.sequence}", "epoch": record.epoch,
                               "start": event.timestamp_ms, "end": event.timestamp_ms, "last_damage": event.timestamp_ms, "damage_start": None, "split": record.split, "run":record.run, "pvp":pvp, "records": [], "majors": set(),
                               "kind_damage": None})       # your last hit of the fight's own kind
                actors_of.append(set())
                peak.append(max(peak[-1], event.timestamp_ms) if peak else event.timestamp_ms)
            group = groups[-1]
            if outgoing:
                if group["damage_start"] is None:
                    group["damage_start"] = event.timestamp_ms
                group["last_damage"] = max(group["last_damage"], event.timestamp_ms)
                peak[-1] = max(peak[-1], group["last_damage"])
                if pvp == group["pvp"]:
                    group["kind_damage"] = max(group["kind_damage"] or 0, event.timestamp_ms)
                if is_major(record.epoch, event.target_id):
                    group["majors"].add(event.target_id)
            group["end"] = max(group["end"], event.timestamp_ms)
            group["records"].append(record)
            actors_of[-1].update((event.actor_id, event.target_id))
        # A death closes exactly one encounter: the latest group still fighting that enemy
        # (its records end at or before the death, within the pull gap). Extending every earlier
        # group that ever touched the enemy -- a leashed or wiped attempt, or the pieces of one
        # fight cut by an earlier boundary -- stretched each of them to the kill and marked
        # every one "killed", so a single kill was counted many times over.
        gap_ms = self.gap_seconds * 1000

        def closes(sample, ends):
            """The fight this death closes, as the full pass picks it: of the fights still fighting the
            entity when it died (hit within the pull gap before it, not ended past it, and not followed
            by a fight that had begun before it), the one hit last, the later on a tie. ``peak`` (the
            latest hit up to each fight) bounds the scan: once no earlier fight was hit late enough,
            none can match. ``ends`` holds the deaths applied before this one that are not settled in
            the fights themselves.

            A fight the next one had already cut is over: a later death (a player's, or an add's in
            the fight that followed) stretched it across the next fight, which then appeared twice in
            the recording, its deaths and health in both (0.2.354)."""
            at, epoch, entity = sample["timestamp_ms"], sample["epoch"], sample["entity"]
            best = None
            for index in range(len(groups) - 1, -1, -1):
                if peak[index] + gap_ms < at:
                    break
                group = groups[index]
                if (group["epoch"] == epoch and entity in actors_of[index]
                        and (index + 1 == len(groups) or at <= groups[index + 1]["start"])
                        and ends.get(index, group["end"]) <= at <= group["last_damage"] + gap_ms
                        and (best is None or group["last_damage"] > groups[best]["last_damage"])):
                    best = index
            return best

        # A death before the open fight began can close none of the fights to come, so its effect
        # is settled into the fight it closes (a copy; the carried fights are shared values).
        open_start = groups[-1]["start"] if groups else None
        while settled < len(deaths) and open_start is not None and deaths[settled]["timestamp_ms"] < open_start:
            index = closes(deaths[settled], {})
            if index is not None:
                groups[index] = {**groups[index], "end": deaths[settled]["timestamp_ms"]}
            settled += 1
        ends = {}
        for sample in deaths[settled:]:
            index = closes(sample, ends)
            if index is not None:
                ends[index] = sample["timestamp_ms"]
        spawns_now = identity_now.get("spawns", {})
        player_ids = identity_now.get("player_ids", ())
        self._grouping = _Grouping(scope, config, records[0].sequence if records else 0, records[-1].sequence if records else 0,
                                   groups, actors_of, peak, death_ms, deaths, settled, seen_now, current,
                                   self._identity_key(identity_now), reps, dict(owners_now), frozenset(actors),
                                   frozenset(a for a in actors if a in player_ids),
                                   {a: spawns_now.get(a, {}).get("mobCode") for a in actors},
                                   sum(1 for key in self._major_history if key[0] == current))
        shown = groups
        if ends:
            shown = list(groups)
            for index, at in ends.items():
                shown[index] = {**groups[index], "end": at}
        self.discarded_segments = max(self.discarded_segments, len(groups) - 200)
        return shown[-200:]

    def _carry_grouping(self, scope, config, allowed_for):
        """The previous ``groups`` result when it can be carried on: the same scope and settings, its
        records still in the history and, for the current epoch (the one ``observe`` still writes),
        every input its grouping read reading the same now: each kind of record's scope membership,
        the owner links, which of the actors involved are known players, their NPC types and the
        epoch's count of engaged majors. Earlier epochs' identities are frozen, so their fights need
        no check. None means walk afresh."""
        state = self._grouping
        records = self.records
        if (state is None or state.scope != scope or state.config != config or not records
                or records[0].sequence > state.last_seq or records[-1].sequence < state.last_seq):
            return None
        if state.epoch != self.epoch:
            return state
        identity = self.identities.get(self.epoch)
        if identity is None or state.identity != self._identity_key(identity) or identity["owners"] != state.owners:
            return None
        player_ids = identity.get("player_ids", ())
        spawns = identity["spawns"]
        if (any((actor in player_ids) != (actor in state.players) for actor in state.actors)
                or any(spawns.get(actor, {}).get("mobCode") != code for actor, code in state.codes.items())
                or sum(1 for key in self._major_history if key[0] == self.epoch) != state.majors
                or any(allowed_for(record) != allowed for record, allowed in state.allowed.values())):
            return None
        return state

    @staticmethod
    def _identity_key(identity):
        """The identity fields that decide which of an epoch's records belong to which kind of membership."""
        return (identity.get("local_id"), tuple(sorted((identity.get("local_corrections") or {}).items())),
                identity.get("initial_roster"), identity.get("initial_roster_sequence"))

    def adopt_grouping(self, state):
        """Take over the ``groups`` result a detached copy of this session computed (the live runner's
        recompute runs on one), so the next call here carries on from it rather than from an older one.
        It holds for this session on the terms ``_carry_grouping`` checks, as the session's own would."""
        if state is not None and (self._grouping is None or state.last_seq >= self._grouping.last_seq):
            self._grouping = state

    def state_signature(self):
        """A cheap fingerprint of what ``snapshot`` reads. While it is unchanged, a reading taken earlier
        is still exact but for its wall-clock fields (``refresh_clock``): the live runner serves it again
        instead of recomputing. Lengths stand in for the collections that only grow, the current epoch's
        identity included; anything the snapshot reads must be represented here."""
        identity = self.identities.get(self.epoch) or {}
        run = self.runs.get(self.run) or {}
        profile = identity.get("profile") or {}
        return (len(self.records), self.sequence, self.records[0].sequence if self.records else None,
                len(self.telemetry), self.discarded_telemetry, self.epoch, self.run, self.run_closed, self.manual_split,
                len(self._user_splits),
                len(self.identities), self.discarded, self.discarded_segments, len(self._dead), len(self._engaged_major),
                len(self._major_below), len(self._engage_span), self._pending_reset, self._live_boss_reset_ms,
                len(self._major_history), self.boss_kills, self.wipe_splits, self.reset_splits, self.boss_splits,
                self._pull_ended_ms, len(self._pull_leftovers), self._gauge_mode,
                self.pvp, self.gap_seconds, self.automatic_splits, self.reset_after_battle, self.reset_on_boss_start,
                self.reset_delay_seconds, self.max_records, self.dummy_record_seconds, self.retain_scope,
                run.get("map_id"), run.get("instance_id"), run.get("start_observed"), run.get("recorded_entry"),
                identity.get("local_id"), len(identity.get("names", ())), len(identity.get("jobs", ())),
                len(identity.get("spawns", ())), len(identity.get("owners", ())), len(identity.get("roster", ())),
                len(identity.get("player_ids", ())), len(identity.get("observed_players", ())),
                len(identity.get("fighters", ())), identity.get("party_instance"), identity.get("initial_roster_sequence"),
                len(identity.get("local_corrections", ())), len(identity.get("carried_entries", ())),
                tuple(sorted((key, str(value)) for key, value in profile.items())))

    def refresh_clock(self, summary, clock):
        """Set a ``snapshot`` reading's wall-clock fields as of now: ``idle_ms``, ``boss_alive``,
        ``potential_reset``, ``battle_over`` and ``paused``. ``clock`` is what ``snapshot`` kept for it in
        ``clock_inputs`` (None for an empty view): the newest fight's epoch, its last hit, its attackers and
        its targets, and whether the view follows the latest fight. The live runner calls this on a reading
        it serves again, so the fields advance between recomputes exactly as a recompute sets them."""
        now_ms = time.time() * 1000
        if clock is None:
            summary.update(idle_ms=None, boss_alive=False, potential_reset=self._pending_reset, battle_over=False, paused=False)
            return
        epoch, last_damage, attackers, targets, latest = clock
        idle_ms = now_ms - last_damage
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
        attacker_alive = any((epoch, actor) not in self._dead for actor in attackers)
        fight_live = False
        for target in targets:
            ekey = (epoch, target)
            # Major = a flagged boss / already-promoted engagement, OR a contact that
            # has been engaged >= MAJOR_ENGAGE_MS (covers an early mechanic lull before
            # the promotion pass runs). Live only while it is still below full HP.
            major = ekey in self._engaged_major or (
                ekey in self._engage_span and now_ms - self._engage_span[ekey] >= MAJOR_ENGAGE_MS)
            if major and ekey not in self._dead and ekey in self._major_below:
                fight_live = True
                break
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
        summary["battle_over"] = bool(self.reset_after_battle and latest and idle_ms >= self.reset_delay_seconds * 1000
                                      and (not boss_alive or idle_ms >= self.gap_seconds * 1000))
        summary["paused"] = bool(now_ms - last_damage >= 2000)

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
        stamped = {(r.epoch, r.local_id) for g in groups for r in g["records"] if r.local_id is not None}
        self_ids = {self._corrected(self.identities.get(epoch, {}), local) for epoch, local in stamped}
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
        # The rows of the fights' records, one pass. The helpers below are defined once (a long fight has
        # ten thousand records; defining them per record, and building each row's, enemy's and skill's
        # empty entry on every hit whether or not it existed, was a third of this summary's time, 0.2.336).
        names_seen = {}

        def named(epoch, actor_id, enemy=False):
            found = names_seen.get((epoch, actor_id, enemy))
            if found is None:
                found = names_seen[(epoch, actor_id, enemy)] = self.name(epoch, actor_id, enemy)
            return found

        def resolve(identity, epoch, actor_id):
            # The row an actor's effects land on: (actor_id, name, key, pet_collapsed,
            # inferred). IDs may be reused after a zone/socket change: don't merge
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
                name = named(epoch, actor_id)
                key = key_of(epoch, actor_id)
            return actor_id, name, key, pet_collapsed, inferred

        def player(identity, epoch, actor_id, resolved=None):
            actor_id, name, key, pet_collapsed, inferred = resolved or resolve(identity, epoch, actor_id)
            row = players.get(key)
            if row is None:
                job = identity["jobs"].get(actor_id) or identity["jobs"].get(identity["owners"].get(actor_id))
                row = players[key] = self._actor(actor_id, name, job)
            if inferred:
                row["inferred_identity"] = True
            if pet_collapsed:
                row["includes_pets"] = True
            elif actor_id in identity["owners"]:
                row["owner"] = str(identity["owners"][actor_id])
            if not row.get("server"):
                # Carry each player's home server id (from the party roster, or the local
                # profile for yourself), so the live view can show the world next to a name.
                info = self._roster_info(identity, name)
                srv = info.get("serverId") or (identity.get("profile", {}).get("serverId")
                                                if actor_id == identity.get("local_id") else None)
                if srv:
                    row["server"] = str(srv)
            row["key"] = key
            return row

        for group in groups:
            identity, epoch = self.identities[group["epoch"]], group["epoch"]
            for record in group["records"]:
                event, allowed = record.event, allowed_for(record)
                if isinstance(event, HealEvent):
                    if event.actor_id in allowed:
                        player(identity, epoch, event.actor_id)["healing"] += event.amount
                    continue
                damage = event.total_damage
                if event.actor_id in allowed and event.target_id not in allowed:
                    target_key = key_of(epoch, event.target_id)
                    enemy = enemies.get(target_key)
                    if enemy is None:
                        enemy = enemies[target_key] = {"key": target_key, "id": str(event.target_id),
                            "name": named(epoch, event.target_id, True), "damage": 0, "hits": 0,
                            "mob_code": identity["spawns"].get(event.target_id, {}).get("mobCode"),
                            "is_player": group["pvp"] or event.target_id in identity["names"],
                            "owner": identity["owners"].get(event.target_id), "players": {},
                            "last_ms": 0, "players_last": {}}
                    enemy["damage"] += damage; enemy["hits"] += 1
                    # Each player's damage to this enemy (the overlay's target panel) goes to their
                    # row's id, so a summon counts for its owner and a re-registered ID for its
                    # player, as in the rows -- not as a "Player #id" of its own.
                    resolved = resolve(identity, epoch, event.actor_id)
                    who = str(resolved[0])
                    enemy["players"][who] = enemy["players"].get(who, 0) + damage
                    # Track recency so the overlay's "current target" follows the enemy
                    # being hit now, not whichever accumulated the most damage earlier.
                    enemy["last_ms"] = max(enemy["last_ms"], event.timestamp_ms)
                    enemy["players_last"][str(event.actor_id)] = event.timestamp_ms
                    if enemy_id and target_key != enemy_id:
                        continue
                    row = player(identity, epoch, event.actor_id, resolved)
                    row["class"] = row["class"] or (job_from_skill(event.skill_code) or "").lower().replace("elementalist", "spiritmaster") or None
                    row["damage"] += damage; row["hits"] += 1
                    skill = row["skills"].get((event.skill_code, event.is_dot))
                    if skill is None:
                        skill = row["skills"][(event.skill_code, event.is_dot)] = {
                            "skill_id": event.skill_code, "skill": skill_name(event.skill_code), "damage": 0, "hits": 0,
                            "min": damage, "max": 0}
                    skill["damage"] += damage; skill["hits"] += 1
                    skill["min"] = min(skill["min"], damage); skill["max"] = max(skill["max"], damage)
                    counts, specials = row["counts"], event.specials
                    for flag, key in _SPECIAL_COUNTS:
                        if flag in specials:
                            counts[key] += 1
                    if event.multi_hit_count > 0:
                        counts["multi"] += 1
                    second = (event.timestamp_ms - group["start"]) // 1000
                    points = timeline.setdefault(row["key"], {})
                    # A whole-session graph joins combat intervals without counting idle gaps.
                    points[second + offset] = points.get(second + offset, 0) + damage
                elif event.target_id in allowed:
                    if enemy_id and key_of(epoch, event.actor_id) != enemy_id:
                        continue
                    row = player(identity, epoch, event.target_id)
                    incoming = row["incoming"]
                    incoming["damage"] += damage; incoming["hits"] += 1
                    incoming["parries"] += int(SpecialDamage.PARRY in event.specials)
                    source = named(epoch, event.actor_id, True)
                    incoming["sources"][source] = incoming["sources"].get(source, 0) + damage
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
        mid-fight epoch splits. Stops at a run change, a real combat gap wider
        than ``gap_seconds`` (a genuinely separate pull) or a split the player
        asked for (New, Split now), so only a mechanic's same-run zone transition
        is merged — never two distinct fights. Re-joining across the player's own
        split brought the fight before New back at the first hit after it."""
        if not groups:
            return []
        chosen = [groups[-1]]
        for group in reversed(groups[:-1]):
            nxt = chosen[0]
            if (group["run"] == nxt["run"] and 0 <= nxt["start"] - group["last_damage"] <= self.gap_seconds * 1000
                    and not any(group["split"] < split <= nxt["split"] for split in self._user_splits)):
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
        mid-fight sample can't inflate the max.

        Walks the telemetry from its newest sample back to the oldest shown epoch (samples are
        in epoch order), not the whole history."""
        current, maximum, full_max, latest = None, 0, None, -1
        floor = min(epochs) if epochs else None
        for sample in reversed(self.telemetry):
            epoch = sample.get("epoch")
            if floor is None or (epoch is not None and epoch < floor):
                break
            if sample.get("kind") != "hp" or sample.get("entity") != entity_id or epoch not in epochs:
                continue
            cur, mx = sample.get("current"), sample.get("max")
            if sample["timestamp_ms"] > latest:   # the newest sample; of equal times, the one recorded last
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
        sampled enough to measure a drop, or when HP is flat/rising (healed/reset).

        Reads the newest samples back only as far as the window and the five-sample fallback
        reach (the telemetry is in time order), not the whole history."""
        floor = min(epochs) if epochs else None
        collected, newest = [], None
        for sample in reversed(self.telemetry):
            epoch = sample.get("epoch")
            if floor is None or (epoch is not None and epoch < floor):
                break
            if (sample.get("kind") != "hp" or sample.get("entity") != entity_id or epoch not in epochs
                    or sample.get("current") is None):
                continue
            at = sample["timestamp_ms"]
            if newest is None:
                newest = at
            if len(collected) >= 5 and newest - at > window_ms:
                break
            collected.append((at, sample["current"]))
        samples = sorted(collected)
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
        summary["boss_kills"] = self.boss_kills
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
        # The wall-clock fields -- the idle time, whether a major fight is still live, the
        # reset-after-battle signal and the pause flag -- are set by ``refresh_clock`` from the
        # newest fight's attackers and targets, kept in ``clock_inputs`` so the live runner can
        # bring a reading it serves again up to date without this walk.
        clock = None
        if chosen:
            attackers, targets = set(), set()
            for record in chosen[-1]["records"]:
                event = record.event
                if isinstance(event, DamageEvent):
                    if event.actor_id in allowed_for(record):
                        attackers.add(event.actor_id)
                    targets.add(event.target_id)
            clock = (chosen[-1]["epoch"], chosen[-1]["last_damage"], frozenset(attackers), frozenset(targets), segment_id is None)
        self.clock_inputs = clock
        self.refresh_clock(summary, clock)
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
            # Seconds this target has been fought: from the party's first hit on it to the
            # last, per group, summed across the merged live encounter -- the fight clock for
            # that target, as other meters and the log page measure a boss fight. Scoping to
            # the target keeps earlier pulls and the time before it was engaged out of the
            # rate; an untargetable phase inside the fight counts, as it does on that clock.
            # (Counting only the seconds in which it was hit read about 8% high on a boss
            # with untargetable phases next to other meters.) Only the shown encounter's
            # fights count: every fight the entity was ever in put a wiped attempt's time
            # under this pull's damage, and walked the whole session for it (0.2.336).
            target_secs = 0
            if entity is not None:
                for group in chosen:
                    times = [record.event.timestamp_ms for record in group["records"]
                             if isinstance(record.event, DamageEvent) and record.event.target_id == entity
                             and record.event.actor_id in allowed_for(record)]
                    if times:
                        target_secs += (max(times) - min(times)) // 1000 + 1
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
                # The entity id in the current zone, so the overlay can show its break gauge.
                "entity_id": int(target["id"]) if str(target.get("id", "")).isdigit() else None,
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

    def _actions_by_epoch(self):
        """The kept actions per epoch, in arrival (time) order, with a parallel list of times."""
        out = {}
        for action in self.actions:
            times, rows = out.setdefault(action["epoch"], ([], []))
            times.append(action["timestamp_ms"])
            rows.append(action)
        return out

    def _positions_by_epoch(self):
        """The kept positions per epoch, unpacked, in arrival (time) order, with a parallel list of times."""
        out = {}
        for packed in self.positions:
            row = _POSITION.unpack(packed)
            times, rows = out.setdefault(row[0], ([], []))
            times.append(row[1])
            rows.append(row)
        return out

    def _segment_movement(self, group, actor_refs, players, entities, by_epoch):
        """A segment's ``movement``: where its players, their pets and its enemies were, on the segment's clock.
        Each also gets the last position known in the ten seconds before the fight, at t = 0, so a replay starts
        with everyone placed."""
        from ..combat.a2log import LIMITS
        times, rows = by_epoch.get(group["epoch"], ([], []))
        start, end = group["start"], group["end"]
        before, during = {}, []
        for epoch, ms, entity, x, y, z, src, heading in rows[bisect.bisect_left(times, start - 10_000):bisect.bisect_right(times, end)]:
            ref = actor_refs.get(entity, f"{epoch}:{entity}")
            if ref not in players and ref not in entities:
                continue
            row = {"t": round(max(0, ms - start) / 1000, 3), "entity": ref, "x": round(x, 1), "y": round(y, 1),
                   "z": round(z, 1), "src": MOVEMENT_SOURCES[src]}
            if heading != _NO_HEADING:
                row["heading"] = heading / 10
            if ms < start:
                before[ref] = row
            else:
                during.append(row)
        return (list(before.values()) + during)[:LIMITS["movement"]]

    def _segment_actions(self, group, identity, actor_refs, players, entities, by_epoch):
        """A segment's casts, effects, break-gauge readings and chain windows for its a2log, on the
        segment's clock (seconds from its start). Only actors the segment already references appear:
        party players and their pets cast; effects are those on them or on the enemies they fought.
        A cast can start up to three seconds before the first hit it causes, so casts from just
        before the segment are kept with a negative time; an effect applied earlier and still
        active is kept, clipped to the segment and marked ``before``."""
        times, rows = by_epoch.get(group["epoch"], ([], []))
        start, end = group["start"], group["end"]
        duration = max(0.001, (end - start) / 1000)
        window = rows[bisect.bisect_left(times, start - 600_000):bisect.bisect_right(times, end + 600_000)]
        at = lambda ms: round((ms - start) / 1000, 3)

        def party_ref(actor):
            ref = actor_refs.get(actor)
            pet = entities.get(ref) if ref not in players else None
            return ref if ref in players or (pet and pet.get("kind") == "pet" and pet.get("owner") in players) else None

        ends, removals, applied = {}, {}, {}
        for a in window:
            if a["kind"] == "cast_end":
                ends.setdefault((a["actor"], a["skill"], a["seq"]), []).append(a["timestamp_ms"])
            elif a["kind"] == "effect_end":
                removals.setdefault((a["target"], a["instance"]), []).append((a["timestamp_ms"], a["reason"]))
            elif a["kind"] == "effect":
                applied.setdefault((a["target"], a["instance"]), []).append(a["timestamp_ms"])
        casts, effects, gauge, chains, last_gauge, chain_open = [], [], [], [], {}, {}
        resources, npc_casts, mp_before, mp_last = [], [], {}, {}
        local = actor_refs.get(identity.get("local_id"))
        for a in window:
            kind, ms = a["kind"], a["timestamp_ms"]
            if kind == "mp":
                entity = actor_refs.get(a["entity"])
                if entity not in players or entity != (local or entity) or ms > end:
                    continue
                if ms < start:
                    mp_before[entity] = a["current"]      # the reading in force when the fight began
                    continue
                if entity in mp_before:
                    mp_last[entity] = mp_before.pop(entity)
                    resources.append({"t": 0.0, "entity": entity, "mp": mp_last[entity]})
                if mp_last.get(entity) != a["current"]:
                    mp_last[entity] = a["current"]
                    resources.append({"t": at(ms), "entity": entity, "mp": a["current"]})
                continue
            if kind == "cast" and start - 3000 <= ms <= end + 1000 and party_ref(a["actor"]) is None:
                source = actor_refs.get(a["actor"])
                if source in entities and entities[source].get("is_boss") and start <= ms:
                    row = {"t": at(ms), "source": source, "skill_id": a["skill"], "skill": skill_name(a["skill"])}
                    target = actor_refs.get(a["target"])
                    if a["at_target"] and target and target != source:
                        row["target"] = target
                    npc_casts.append(row)
                continue
            if kind == "cast" and start - 3000 <= ms <= end + 1000:
                source = party_ref(a["actor"])
                if source is None:
                    continue
                skill = normalize_skill(a["skill"])
                row = {"t": at(ms), "source": source, "skill_id": skill, "skill": skill_name(skill)}
                target = actor_refs.get(a["target"])
                if a["at_target"] and target and target != source:
                    row["target"] = target
                if a.get("cooldown_ms"):
                    row["cooldown_ms"] = a["cooldown_ms"]
                finished = [t for t in ends.get((a["actor"], a["skill"], a["seq"]), ()) if 0 <= t - ms <= 5000]
                if finished:
                    row["cast_ms"] = min(finished) - ms
                casts.append(row)
            elif kind == "effect" and ms <= end:
                target = actor_refs.get(a["target"])
                skill = normalize_skill(a.get("skill") or a["effect"] // 10)
                if target is None or not has_skill(skill):
                    continue                # not on a segment actor, or not a named game effect
                # A removal names only the instance, and the game reuses instances: it belongs to the
                # latest application before it, and the next application on the instance ends this one.
                key = (a["target"], a["instance"])
                later = applied.get(key, ())
                following = min((t for t in (next(iter(later[bisect.bisect_right(later, ms):]), None), a.get("replaced_ms"))
                                 if t is not None), default=None)
                removal = next((r for r in removals.get(key, ()) if ms <= r[0] and (following is None or r[0] < following)), None)
                stop = removal[0] if removal else (a.get("refreshed_ms", ms) + a["duration_ms"] if a["duration_ms"] is not None else None)
                if following is not None and (stop is None or following < stop):
                    stop = following
                if stop is not None and stop <= start:
                    continue                # over before the segment began
                row = {"t": max(0.0, at(ms)), "end": round(min(duration, (stop - start) / 1000), 3) if stop is not None else round(duration, 3),
                       "target": target, "skill_id": skill, "skill": skill_name(skill), "effect_id": a["effect"]}
                source = actor_refs.get(a["source"])
                if source:
                    row["source"] = source
                if a["duration_ms"] is not None:
                    row["duration_ms"] = a["duration_ms"]
                if a.get("refreshes"):
                    row["refreshes"] = a["refreshes"]
                if removal and removal[0] <= end:
                    row["ended"] = "expired" if removal[1] == 1 else "removed"
                if ms < start:
                    row["before"] = True
                effects.append(row)
            elif kind == "gauge" and start <= ms <= end:
                entity = actor_refs.get(a["entity"])
                if entity is None or last_gauge.get(entity) == (a["max"], a["current"]):
                    continue
                last_gauge[entity] = (a["max"], a["current"])
                gauge.append({"t": at(ms), "entity": entity, "max": a["max"], "current": a["current"]})
            elif kind in ("chain_open", "chain_close") and local in players and start - 3000 <= ms <= end + 1000:
                if kind == "chain_open":
                    chain_open[a["next"]] = (ms, a["skill"])
                elif a["next"] in chain_open:
                    opened, skill = chain_open.pop(a["next"])
                    chains.append({"t": at(opened), "end": at(ms), "player": local, "skill_id": normalize_skill(skill),
                                   "next_id": normalize_skill(a["next"]), "next": skill_name(normalize_skill(a["next"]))})
        for nxt, (opened, skill) in chain_open.items():
            chains.append({"t": at(opened), "player": local, "skill_id": normalize_skill(skill),
                           "next_id": normalize_skill(nxt), "next": skill_name(normalize_skill(nxt))})
        chains.sort(key=lambda c: c["t"])
        for entity, value in mp_before.items():          # no reading during the fight: the one before it
            resources.append({"t": 0.0, "entity": entity, "mp": value})
        maximum = (identity["spawns"].get(identity.get("local_id")) or {}).get("maxMp")
        if maximum and local in players:
            for row in resources:
                if row["entity"] == local:
                    row["max"] = maximum
        return casts, effects, gauge, chains, resources, npc_casts

    def to_a2log(self, scope="party", title=None, segment_id="all"):
        from ..combat import a2log
        allowed_for = self._allowances(scope)
        groups = self.groups(scope, allowed_for)
        if segment_id != "all":
            groups = [g for g in groups if g["id"] == segment_id] if segment_id else groups[-1:]
        players, segments = {}, []
        by_epoch = self._actions_by_epoch()
        positions_by_epoch = self._positions_by_epoch()
        for index, group in enumerate(groups):
            identity = self.identities[group["epoch"]]
            hits, events, entities = [], [], {}
            resolving = set()
            actor_refs = {}
            opponents = set()
            roster_allowed = set().union(*(allowed_for(r) for r in group["records"]))
            if identity.get("party_instance"):
                # A player counted only because a group instance holds just the party (``_allowed``) is a member
                # of the fights they took part in, not of every fight in the zone context: a party that changed
                # inside one instance otherwise listed both line-ups in every segment.
                # Their own hits and heals, not a summon's: a spirit's single hit, linked to a Spiritmaster of the
                # next line-up, made that player a member of the previous line-up's boss fight.
                acted = {record.event.actor_id for record in group["records"]}
                named = set().union(*(set(r.party) for r in group["records"]))
                if any(self._late_roster(r) for r in group["records"]):        # matched to the first roster seen
                    named |= set(identity.get("initial_roster") or ())
                local = {self._corrected(identity, r.local_id) for r in group["records"]} | {identity["local_id"]}
                roster_allowed = {a for a in roster_allowed if a in acted or a in local or a in identity["owners"]
                                  or identity["names"].get(a, "").casefold() in named}
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
                    info = self._roster_info(identity, name)
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
                elif (not identity["spawns"].get(actor_id, {}).get("mobCode") and identity.get("class_strikes", {}).get(actor_id)
                      and actor_id not in identity.get("npc_strikes", ())):
                    # A player with no identity record, known by the class skills it struck with.
                    entities[pid] = {"id": pid, "name": f"Player #{actor_id}", "kind": "enemy" if actor_id in opponents else "player",
                                     "is_player": True, "class": identity["jobs"].get(actor_id) or identity["class_strikes"][actor_id]}
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
                               and len({r.party for r in group["records"]}) == 1) or self._fought_alone(group, identity, members, group_scope)
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
                # Bosses, and players too: a heal early in the fight needs the HP it started from.
                if eid in entities and entities[eid].get("is_boss") or eid in players:
                    maximum = sample.get("max") or identity["spawns"].get(actor_id, {}).get("reportedMaxHp")
                    health.append({"t":0, "entity":eid, "current":sample["current"], "max":maximum})
            dead_players = set()
            for sample in self.telemetry:
                if sample["epoch"] != group["epoch"] or not group["start"] <= sample["timestamp_ms"] <= group["end"]:
                    continue
                eid = actor_refs.get(sample["entity"],f"{group['epoch']}:{sample['entity']}")
                if eid not in players and eid not in entities:
                    continue
                t = (sample["timestamp_ms"] - group["start"]) / 1000
                if sample["kind"] == "death":
                    events.append({"kind": "death", "t": t, "target": eid})
                    if eid in players:
                        dead_players.add(eid)
                elif eid in dead_players and (sample.get("current") or 0) > 0:
                    # A player's first HP above zero after their death: the resurrection.
                    dead_players.discard(eid)
                    events.append({"kind": "revive", "t": t, "target": eid})
                    health.append({"t": t, "entity": eid, "current": sample["current"],
                        "max": sample.get("max") or identity["spawns"].get(sample["entity"], {}).get("reportedMaxHp")})
                else:
                    health.append({"t": t, "entity": eid, "current": sample["current"],
                        "max": sample.get("max") or identity["spawns"].get(sample["entity"], {}).get("reportedMaxHp")})
            casts, effects, gauge, chains, resources, npc_casts = self._segment_actions(group, identity, actor_refs, players, entities, by_epoch)
            movement = self._segment_movement(group, actor_refs, players, entities, positions_by_epoch)
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
                    "casts": casts, "effects": effects, "gauge": gauge, "chains": chains,
                    "resources": resources, "npc_casts": npc_casts, "movement": movement,
                    "start": datetime.fromtimestamp(group["start"] / 1000, timezone.utc).isoformat(),
                    "duration": max(0.001, (group["end"] - group["start"]) / 1000),
                    "capture_loss": self.losses_within(group["start"], group["end"])})
        if not players:
            raise NoIdentifiedPlayerData("No identified player data is available under the selected party filter.")
        if len(players) > a2log.LIMITS["players"]:
            raise ValueError(f"This session exceeds the {a2log.LIMITS['players']}-identity export safety limit. Export a shorter session or use Party / Self filtering.")
        from .. import __version__
        from ..combat.quality import DECODER
        evidence = {**self.capture_evidence, "decoder":DECODER, "app_version":__version__,
                    "discarded_effects":self.discarded, "discarded_segments":self.discarded_segments, "out_of_scope_effects":self.out_of_scope,
                    "discarded_telemetry":self.discarded_telemetry, "discarded_actions":self.discarded_actions,
                    "discarded_positions":self.discarded_positions,
                    "loss_attribution": "segment"}
        npc_diagnostics = self.npc_diagnostics(g["epoch"] for g in groups)
        exported_scope = scope
        if scope == "auto":
            exported_scope = "all" if any(self._effective_scope(scope, g["epoch"]) == "all" for g in groups) else "party"
        return a2log.validate({"format":"a2log","version":1,"meta":{"source":"Aion 2 Calc live session","title":title or "Live combat session", "capture_scope":exported_scope, "capture_quality":evidence, "npc_diagnostics":npc_diagnostics},
                               "players":list(players.values()),"segments":segments})
