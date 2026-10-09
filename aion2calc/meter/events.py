"""The combat event a decoder emits and the meter consumes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class CombatEvent:
    """One thing that happened in a fight, as produced by a decoder.

    ``t`` is a timestamp in seconds (any origin; the meter normalizes to the first event). A
    ``damage`` event is an attacker (``source``) hitting ``target`` with ``skill``. A ``buff`` event
    records ``buff`` active on ``source`` from ``t`` to ``buff_end``.
    """

    t: float
    kind: str = "damage"            # damage | buff | death | info | ping
    ping_ms: float = 0.0            # for kind == "ping": round-trip latency in milliseconds
    source: str = ""                # attacker id (stable key)
    source_name: str = ""           # display name (defaults to source)
    source_class: str | None = None
    owner: str = ""                 # for a pet/summon: its owner's id (empty if the source is a player)
    is_pet: bool = False            # the source is a pet/summon, not a player
    local: bool = False             # the source (or its owner) is the local recording player
    target: str = ""
    skill: str = ""
    skill_id: int | None = None
    damage: float = 0.0
    crit: bool = False
    double: bool = False
    perfect: bool = False
    multi: int = 0                  # extra hits of a multi-hit
    dot: bool = False
    target_boss: bool = False
    buff: str = ""                  # for kind == "buff"
    buff_end: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "CombatEvent":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    def to_dict(self) -> dict:
        return asdict(self)
