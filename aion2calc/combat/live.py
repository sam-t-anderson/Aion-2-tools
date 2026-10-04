"""Interface for a live (real-time) combat source.

Every AION 2 damage meter (AionFlex, A2DIL's recorder, aion2t) works the same
way: it passively captures the game's TCP traffic with npcap on Windows,
reassembles the stream and decodes the game's undocumented, partly compressed
binary protocol, which changes with patches.  That decoder is not public, and
it can only be reverse-engineered from captures of a running game client, so it
is not part of this package.

Anything that can produce hits can plug in here: implement ``LiveSource``
(yield canonical hit dicts, see ``adapters.py``) and pass it to
``record_encounter``; the analyzer, history and comparison with the optimizer
then work unchanged.  Using third-party capture tools may break the game's
terms of service; that risk is the user's to judge.
"""
from __future__ import annotations

import time
from typing import Iterator, Protocol

from .adapters import normalize


class LiveSource(Protocol):
    def hits(self) -> Iterator[dict | None]:
        """Yield canonical hit dicts ({"t", "skill_id", "skill", "damage", "crit", ...}) as they happen,
        and ``None`` about once a second while idle so the recorder can notice the fight ended."""


def record_encounter(source: LiveSource, idle_end: float = 8.0, meta: dict | None = None) -> dict:
    """Collect hits until ``idle_end`` seconds pass without one; return a normalized encounter."""
    hits, last = [], time.time()
    for h in source.hits():
        if h is None:
            if hits and time.time() - last > idle_end:
                break
            continue
        hits.append(h)
        last = time.time()
    t0 = hits[0]["t"] if hits else 0.0
    for h in hits:
        h["t"] -= t0
    return normalize({"meta": {"source": "live", **(meta or {})}, "hits": hits})
