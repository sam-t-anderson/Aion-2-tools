"""Streaming aggregator: combat events in, a live DPS table (and an a2log) out."""
from __future__ import annotations

from .events import CombatEvent


class Meter:
    """Accumulates :class:`CombatEvent` into per-player and per-skill totals. Thread-unsafe by
    itself; the app's runner feeds it from one thread and reads snapshots under a lock."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.t0: float | None = None
        self.last: float | None = None
        self.players: dict = {}
        self.buffs: list[CombatEvent] = []
        self.events: list[CombatEvent] = []
        self.boss: str | None = None

    @property
    def duration(self) -> float:
        if self.t0 is None:
            return 0.0
        return max(0.0, (self.last if self.last is not None else self.t0) - self.t0)

    def add(self, ev: CombatEvent) -> None:
        if self.t0 is None:
            self.t0 = ev.t
        if self.last is None or ev.t > self.last:
            self.last = ev.t
        self.events.append(ev)
        if len(self.events) > 500_000:
            self.events = self.events[-400_000:]
        if ev.kind == "buff":
            self.buffs.append(ev)
            return
        if ev.kind != "damage":
            return
        p = self.players.get(ev.source)
        if p is None:
            p = self.players[ev.source] = {"name": ev.source_name or ev.source, "class": ev.source_class,
                                           "damage": 0.0, "hits": 0, "crit": 0, "double": 0, "perfect": 0, "skills": {}}
        if ev.source_class and not p["class"]:
            p["class"] = ev.source_class
        p["damage"] += ev.damage
        p["hits"] += 1
        p["crit"] += 1 if ev.crit else 0
        p["double"] += 1 if ev.double else 0
        p["perfect"] += 1 if ev.perfect else 0
        key = ev.skill or (str(ev.skill_id) if ev.skill_id else "?")
        sk = p["skills"].get(key)
        if sk is None:
            sk = p["skills"][key] = {"damage": 0.0, "hits": 0, "casts": 0, "crit": 0, "skill_id": ev.skill_id}
        sk["damage"] += ev.damage
        sk["hits"] += 1
        sk["crit"] += 1 if ev.crit else 0
        if not ev.dot and ev.multi == 0:          # approximate casts: primary (non-dot, non-multi) hits
            sk["casts"] += 1
        if ev.target_boss and not self.boss:
            self.boss = ev.target or self.boss

    def snapshot(self) -> dict:
        dur = self.duration or 1e-9
        total = sum(p["damage"] for p in self.players.values()) or 1.0
        rows = []
        for pid, p in self.players.items():
            hits = p["hits"] or 1
            skills = [{"skill": s, "damage": d["damage"], "share": d["damage"] / (p["damage"] or 1.0),
                       "casts": d["casts"], "hits": d["hits"], "crit": (d["crit"] / d["hits"]) if d["hits"] else 0.0,
                       "skill_id": d["skill_id"]} for s, d in p["skills"].items()]
            skills.sort(key=lambda s: -s["damage"])
            rows.append({"id": pid, "name": p["name"], "class": p["class"], "damage": p["damage"],
                         "dps": p["damage"] / dur, "share": p["damage"] / total, "hits": p["hits"],
                         "crit": p["crit"] / hits, "double": p["double"] / hits, "perfect": p["perfect"] / hits,
                         "skills": skills})
        rows.sort(key=lambda r: -r["damage"])
        return {"duration": round(self.duration, 2), "boss": self.boss, "total": total,
                "dps": total / dur, "players": rows}

    def to_a2log(self, source: str = "aion2calc-meter", title: str | None = None, region: str | None = None) -> dict:
        """Build and validate an a2log document for the session, so it can be saved, analyzed and
        shared through the existing pipeline."""
        from ..combat import a2log as F
        ids = {}
        players = []
        for i, (pid, p) in enumerate(self.players.items()):
            ids[pid] = pid or f"p{i}"
            pl = {"id": ids[pid], "name": p["name"]}
            if p.get("class"):
                pl["class"] = str(p["class"]).lower()
            players.append(pl)
        hits = []
        for ev in self.events:
            if ev.kind != "damage":
                continue
            h = {"t": round(ev.t - (self.t0 or 0.0), 3), "player": ids.get(ev.source, ev.source), "damage": ev.damage}
            if ev.skill:
                h["skill"] = ev.skill
            if ev.skill_id:
                h["skill_id"] = ev.skill_id
            for k in ("crit", "double", "perfect", "dot"):
                if getattr(ev, k):
                    h[k] = True
            if ev.multi:
                h["multi"] = ev.multi
            hits.append(h)
        buffs = []
        for ev in self.buffs:
            buffs.append({"player": ids.get(ev.source, ev.source), "name": ev.buff or ev.skill or "buff",
                          "start": round(ev.t - (self.t0 or 0.0), 3),
                          "end": round((ev.buff_end if ev.buff_end is not None else (self.last or ev.t)) - (self.t0 or 0.0), 3)})
        seg = {"label": self.boss or "Live session", "duration": round(self.duration, 3) or 0.001,
               "killed": False, "hits": hits}
        if self.boss:
            seg["boss"] = self.boss
        if buffs:
            seg["buffs"] = buffs
        meta = {"source": source}
        if title:
            meta["title"] = title
        if region:
            meta["region"] = region
        return F.validate({"format": "a2log", "version": F.VERSION, "meta": meta, "players": players, "segments": [seg]})
