"""Candidate marks (0.2.366): moments of a capture that look like one of the items still gated on labelled
evidence, offered on the Live Meter page for the player to confirm or dismiss.

They are suggestions, never evidence: a confirmed candidate becomes an ordinary mark, a dismissed one is kept as
such in the diagnostics (a pattern that was *not* the thing is worth knowing too). The scanner runs only while a
capture records raw TCP payloads, since without them a mark points at nothing to decode. It reads what the
engine decoded for each packet -- the damage and heal events, the cast, cast-end and effect actions, the HP
telemetry -- and keeps a little state per fight:

* **shield** -- a hit on a party player who has a shield effect up, and whose HP reading did not drop by the hit;
* **interrupt** -- a boss cast that ended well short of the length its earlier casts took, right after a party
  member applied an effect on the caster (a stun, a knockdown, a silence);
* **miss** -- a boss skill that dealt damage on its earlier casts and dealt none on this one;
* **mitigation** -- a hit far below the earlier hits of the same skill on the same player, not a decoded parry;
* **hot** -- a heal over time: ticks of one skill on one target in a steady rhythm (the game sends one record
  for the whole amount, so the ticks it does send are what a labelled capture settles);
* **mechanic** -- a boss skill whose hits landed on three or more party members at once.

Each kind is rate-limited per key and the whole capture is capped, so the list stays something a player can
answer between pulls.
"""
from __future__ import annotations

import statistics
import time

from ..meter.a2parser.lookup import normalize_skill, npc_info, skill_name
from ..meter.a2parser.models import DamageEvent, HealEvent, SpecialDamage

SHIELD_WORDS = ("shield", "barrier", "protection", "poach", "guarding seal", "aegis", "ward")
COOLDOWN_MS = 15_000            # the same kind on the same key is offered again only after this long
PER_FIGHT = 40                  # candidates a fight may raise
PER_CAPTURE = 200               # and a whole capture
HIT_WINDOW_MS = 4_000           # a boss cast's hits land within this of the cast (the aoe module's window)
CC_BEFORE_END_MS = 1_500        # an effect applied on the caster this long before its cast ended
SHORT_CAST = 0.6                # a cast ending in under this share of its usual length looks cut short
LOW_HIT = 0.55                  # a hit under this share of the skill's median on the player looks reduced
HP_SETTLE_MS = 1_500            # an HP reading within this after a hit says whether the hit landed on HP


def _name(skill):
    try:
        return skill_name(normalize_skill(int(skill)))
    except (TypeError, ValueError):
        return str(skill)


def _iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{int(ms) % 1000:03d}Z"


class CandidateScanner:
    """Per-capture state; ``observe`` returns the candidate rows a packet's decoded data raised."""

    def __init__(self, per_fight: int = PER_FIGHT, per_capture: int = PER_CAPTURE):
        self.per_fight, self.per_capture = per_fight, per_capture
        self.raised = 0
        self.fight_raised = {}          # boss entity id -> candidates raised while it was the fight
        self.last = {}                  # (kind, key) -> timestamp_ms of the last candidate
        self.shields = {}               # player id -> list of {"skill", "start", "end"}
        self.hp = {}                    # entity id -> (timestamp_ms, current)
        self.pending_hp = []            # hits waiting for an HP reading: (deadline_ms, player, damage, before, skill, shield)
        self.casting = {}               # boss id -> {"skill", "t"}
        self.cast_lengths = {}          # (boss id, skill) -> [ms]
        self.recent_cc = {}             # boss id -> [(timestamp_ms, source)]
        self.hit_counts = {}            # (boss id, skill) -> casts that dealt damage
        self.open_casts = []            # boss casts awaiting their damage: {"boss","skill","t","deadline","targets","hits"}
        self.cast_total = {}            # (boss id, skill) -> casts seen
        self.amounts = {}               # (skill_code, target) -> [damage]
        self.ticks = {}                 # (skill_code, target) -> [(timestamp_ms, amount)]
        self.hot_raised = set()

    # ---- helpers ---------------------------------------------------------------------------------------------
    @staticmethod
    def _identity(session):
        try:
            return session.identities.get(session.epoch) or {}
        except AttributeError:
            return {}

    @staticmethod
    def _is_boss(identity, entity) -> bool:
        code = ((identity.get("spawns") or {}).get(entity) or {}).get("mobCode")
        return bool(code) and bool(npc_info(code).get("isBoss"))

    @staticmethod
    def _party(identity) -> set:
        names, owners, local = identity.get("names") or {}, identity.get("owners") or {}, identity.get("local_id")
        party = set(names) | set(owners.values())
        if local is not None:
            party.add(local)
        return party

    def _allowed(self, kind: str, key, boss, now_ms: int) -> bool:
        if self.raised >= self.per_capture:
            return False
        if boss is not None and self.fight_raised.get(boss, 0) >= self.per_fight:
            return False
        last = self.last.get((kind, key))
        return last is None or now_ms - last >= COOLDOWN_MS

    def _raise(self, out, kind, key, boss, now_ms, why, context):
        if not self._allowed(kind, key, boss, now_ms):
            return
        self.last[(kind, key)] = now_ms
        self.raised += 1
        if boss is not None:
            self.fight_raised[boss] = self.fight_raised.get(boss, 0) + 1
        row = {"kind": "candidate", "status": "pending", "label": kind, "source": "auto", "note": "",
               "at": _iso(now_ms), "t_ms": int(now_ms), "why": why[:300], "context": {k: v for k, v in context.items() if v is not None}}
        out.append(row)

    # ---- the scan ----------------------------------------------------------------------------------------------
    def observe(self, session, engine, events, timestamp_ms=None) -> list[dict]:
        identity = self._identity(session)
        party = self._party(identity)
        label = lambda eid: (identity.get("names") or {}).get(eid) or str(eid)
        out = []
        actions = list(getattr(engine, "actions", None) or [])
        telemetry = list(getattr(engine, "telemetry", None) or [])
        now = timestamp_ms
        for row in telemetry:
            if row.get("kind") == "hp" and row.get("current") is not None:
                self.hp[row["entity"]] = (row["timestamp_ms"], row["current"])
                now = max(now or 0, row["timestamp_ms"])
        for a in actions:
            now = max(now or 0, a.get("timestamp_ms") or 0)
            kind = a.get("kind")
            if kind == "effect":
                self._effect(a, identity, party)
            elif kind == "effect_end":
                for window in self.shields.get(a.get("target"), ()):
                    if window.get("instance") == a.get("instance") and window["end"] is None:
                        window["end"] = a["timestamp_ms"]
            elif kind == "cast" and self._is_boss(identity, a.get("actor")):
                self._boss_cast(a, out, label)
            elif kind == "cast_end" and self._is_boss(identity, a.get("actor")):
                self._boss_cast_end(a, out, identity, label)
        for e in events:
            if isinstance(e, DamageEvent):
                now = max(now or 0, e.timestamp_ms)
                if e.target_id in party and e.actor_id not in party:
                    self._hit_on_player(e, identity, out, label)
                if self._is_boss(identity, e.actor_id):
                    for cast in self.open_casts:
                        if cast["boss"] == e.actor_id and cast["t"] - 50 <= e.timestamp_ms <= cast["deadline"]:
                            cast["hits"] += 1
                            if e.target_id in party:
                                cast["targets"].add(e.target_id)
            elif isinstance(e, HealEvent) and e.target_id in party:
                now = max(now or 0, e.timestamp_ms)
                self._heal(e, out, label)
        if now:
            self._settle(now, out, identity, label)
        return out

    # ---- detectors --------------------------------------------------------------------------------------------
    def _effect(self, a, identity, party):
        target, source, t = a.get("target"), a.get("source"), a.get("timestamp_ms")
        name = _name(a.get("skill") or (a.get("effect") or 0) // 10)
        if target in party and any(word in name.casefold() for word in SHIELD_WORDS):
            windows = self.shields.setdefault(target, [])
            windows.append({"skill": name, "start": t, "end": (t + a["duration_ms"]) if a.get("duration_ms") else None,
                            "instance": a.get("instance")})
            del windows[:-12]
        if source in party and self._is_boss(identity, target):
            recent = self.recent_cc.setdefault(target, [])
            recent.append((t, source, name))
            del recent[:-20]

    def _shield_up(self, player, t):
        for window in reversed(self.shields.get(player, ())):
            if window["start"] - 50 <= t <= (window["end"] if window["end"] is not None else window["start"] + 30_000):
                return window["skill"]
        return None

    def _hit_on_player(self, e, identity, out, label):
        player, t, damage = e.target_id, e.timestamp_ms, e.total_damage
        boss = e.actor_id if self._is_boss(identity, e.actor_id) else None
        skill = _name(e.skill_code)
        # shield: the hit meets a shield; whether HP moved is settled by the next reading
        shield = self._shield_up(player, t)
        if shield:
            before = self.hp.get(player)
            self.pending_hp.append({"deadline": t + HP_SETTLE_MS, "player": player, "damage": damage, "before": before,
                                    "skill": skill, "shield": shield, "boss": boss, "t": t})
        # mitigation: far below this skill's earlier hits on this player, and not a decoded parry
        key = (e.skill_code, player)
        earlier = self.amounts.setdefault(key, [])
        if damage > 0 and len(earlier) >= 4 and SpecialDamage.PARRY not in e.specials:
            median = statistics.median(earlier)
            if median > 0 and damage < LOW_HIT * median:
                self._raise(out, "mitigation", key, boss, t,
                            f"{skill} hit {label(player)} for {damage:,}, against a usual {int(median):,} on them in this fight",
                            {"skill": skill, "player": label(player), "damage": damage, "usual": int(median)})
        if damage > 0 and SpecialDamage.PARRY not in e.specials:
            earlier.append(damage)
            del earlier[:-30]

    def _boss_cast(self, a, out, label):
        boss, skill, t = a["actor"], a.get("skill"), a["timestamp_ms"]
        self.casting[boss] = {"skill": skill, "t": t}
        key = (boss, skill)
        self.cast_total[key] = self.cast_total.get(key, 0) + 1
        # the previous open cast of this boss is over: judge it now
        self._close_casts(out, label, boss=boss, at=t - 50)
        self.open_casts.append({"boss": boss, "skill": skill, "t": t, "deadline": t + HIT_WINDOW_MS, "targets": set(), "hits": 0,
                                "target": a.get("target")})

    def _boss_cast_end(self, a, out, identity, label):
        boss, skill, t = a["actor"], a.get("skill"), a["timestamp_ms"]
        started = self.casting.pop(boss, None)
        if not started or started["skill"] != skill:
            return
        length = t - started["t"]
        key = (boss, skill)
        history = self.cast_lengths.setdefault(key, [])
        cc = [(ts, src, name) for ts, src, name in self.recent_cc.get(boss, ()) if 0 <= t - ts <= CC_BEFORE_END_MS]
        if len(history) >= 2:
            usual = statistics.median(history)
            if usual >= 800 and length < SHORT_CAST * usual and (cc or length < 0.4 * usual):
                who = f" right after {label(cc[-1][1])}'s {cc[-1][2]}" if cc else ""
                self._raise(out, "interrupt", key, boss, t,
                            f"{_name(skill)} ended after {length / 1000:.1f} s, usually {usual / 1000:.1f} s{who}",
                            {"skill": _name(skill), "length_ms": int(length), "usual_ms": int(usual),
                             "after": label(cc[-1][1]) if cc else None})
        if length > 0:
            history.append(length)
            del history[:-20]

    def _close_casts(self, out, label, boss=None, at=None):
        keep = []
        for cast in self.open_casts:
            done = (boss is not None and cast["boss"] == boss and at is not None) or (at is not None and at >= cast["deadline"])
            if not done:
                keep.append(cast)
                continue
            key = (cast["boss"], cast["skill"])
            if cast["hits"]:
                self.hit_counts[key] = self.hit_counts.get(key, 0) + 1
                if len(cast["targets"]) >= 3:
                    self._raise(out, "mechanic", key, cast["boss"], cast["t"],
                                f"{_name(cast['skill'])} hit {len(cast['targets'])} party members at once",
                                {"skill": _name(cast["skill"]), "players_hit": len(cast["targets"])})
            elif self.hit_counts.get(key, 0) >= 2:
                self._raise(out, "miss", key, cast["boss"], cast["t"],
                            f"{_name(cast['skill'])} dealt no damage this cast after hitting on {self.hit_counts[key]} earlier casts"
                            + (f" (aimed at {label(cast['target'])})" if cast.get("target") else ""),
                            {"skill": _name(cast["skill"]), "earlier_hits": self.hit_counts[key],
                             "target": label(cast["target"]) if cast.get("target") else None})
        self.open_casts = keep

    def _heal(self, e, out, label):
        key = (e.skill_code, e.target_id)
        if key in self.hot_raised:
            return
        ticks = self.ticks.setdefault(key, [])
        ticks.append((e.timestamp_ms, e.amount))
        del ticks[:-8]
        if e.is_hot or len(ticks) >= 3:
            gaps = [b[0] - a[0] for a, b in zip(ticks, ticks[1:])]
            steady = len(gaps) >= 2 and all(500 <= g <= 4_000 for g in gaps) and max(gaps) - min(gaps) <= 600
            equal = len({amt for _, amt in ticks[-3:]}) == 1
            if e.is_hot or (steady and equal):
                self.hot_raised.add(key)
                self._raise(out, "hot", key, None, e.timestamp_ms,
                            f"{_name(e.skill_code)} healed {label(e.target_id)} {len(ticks)} times in a steady rhythm ({e.amount:,} a tick)",
                            {"skill": _name(e.skill_code), "player": label(e.target_id), "tick": e.amount, "ticks": len(ticks)})

    def _settle(self, now, out, identity, label):
        self._close_casts(out, label, at=now)
        keep = []
        for pend in self.pending_hp:
            after = self.hp.get(pend["player"])
            fresh = after is not None and after[0] >= pend["t"]
            if not fresh and now < pend["deadline"]:
                keep.append(pend)
                continue
            before = pend["before"]
            if fresh and before is not None:
                drop = before[1] - after[1]
                landed = drop >= 0.5 * pend["damage"]
                if landed:
                    continue                # the hit took its HP: no absorption there
                why = (f"{pend['skill']} hit {label(pend['player'])} for {pend['damage']:,} with {pend['shield']} up; "
                       f"HP read {before[1]:,} before and {after[1]:,} after")
            else:
                why = f"{pend['skill']} hit {label(pend['player'])} for {pend['damage']:,} with {pend['shield']} up (no HP reading to compare)"
            self._raise(out, "shield", (pend["player"], pend["shield"]), pend["boss"], pend["t"], why,
                        {"skill": pend["skill"], "player": label(pend["player"]), "shield": pend["shield"], "damage": pend["damage"]})
        self.pending_hp = keep
