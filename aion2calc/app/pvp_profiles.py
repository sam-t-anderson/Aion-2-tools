"""The combat power of the other players in a PvP match (0.2.395).

The game gives the combat power and gear score of your own party in its party list, and nothing of an opponent's:
the arena's roster carries their name, class, server, level and arena rating, no more. For the overlay's arena
mode (the opponent's card, the player cards window) the app looks an opponent up on the official character
service by name and server, the way a log upload looks its players up: one at a time on a worker thread, never on
the overlay's own request, and remembered for the session. A name the service finds more than once on that server
(or not at all) gets no combat power rather than someone else's; an unanswered lookup is asked again after ten
minutes. Gear score is not on the official profile, so an opponent's stays unknown.
"""
from __future__ import annotations

import threading
import time

#: Seconds before a lookup that found nothing (or failed) is asked again.
RETRY_S = 600.0
#: Players remembered at most (the oldest go first).
KEPT = 512

_LOCK = threading.Lock()
_FOUND: dict[tuple[str, str], dict] = {}
_WANTED: dict[tuple[str, str], dict] = {}
_WORKER: threading.Thread | None = None
#: The lookup itself, ``(name, server_id, class_key, region) -> {"combat_power", "level", "region"} | None``.
#: Tests replace it; the app's is :func:`_official`.
fetch = None


def known(name, server, cls=None, region=None) -> dict | None:
    """What the official character service says of a player: ``{"combat_power", "level", "status", "at"}``, with
    ``status`` ``ready`` or ``unavailable``. None until the first answer: the first ask queues the lookup."""
    name = str(name or "").strip()
    server = str(server or "").strip()
    if not name or not server.isdigit() or "#" in name or len(name) > 20 or not any(c.isalpha() for c in name):
        return None
    key = (name.casefold(), server)
    now = time.time()
    with _LOCK:
        found = _FOUND.get(key)
        if found is not None and (found["status"] == "ready" or now - found["at"] < RETRY_S):
            return found
        if key not in _WANTED:
            _WANTED[key] = {"name": name, "server": server, "class": cls, "region": region}
            _start()
    return found


def clear() -> None:
    """Forget every answer and pending lookup (tests)."""
    with _LOCK:
        _FOUND.clear()
        _WANTED.clear()


def _start() -> None:
    """Start the worker when none is running. The caller holds the lock."""
    global _WORKER
    if _WORKER is None or not _WORKER.is_alive():
        _WORKER = threading.Thread(target=_work, name="pvp-profiles", daemon=True)
        _WORKER.start()


def _work() -> None:
    while True:
        with _LOCK:
            if not _WANTED:
                return
            key, want = next(iter(_WANTED.items()))
        try:
            answer = (fetch or _official)(want["name"], int(want["server"]), want.get("class"), want.get("region"))
        except Exception:                                                     # noqa: BLE001 - an answer of nothing
            answer = None
        power = (answer or {}).get("combat_power")
        row = {"combat_power": power if isinstance(power, int) and not isinstance(power, bool) and power > 0 else None,
               "level": (answer or {}).get("level"), "at": time.time()}
        row["status"] = "ready" if row["combat_power"] else "unavailable"
        with _LOCK:
            _WANTED.pop(key, None)
            _FOUND.pop(key, None)
            _FOUND[key] = row
            while len(_FOUND) > KEPT:
                _FOUND.pop(next(iter(_FOUND)))


def _official(name: str, server_id: int, cls: str | None, region: str | None) -> dict | None:
    """One player on the official character service: the search by name on their server (in their region when it is
    known, else in each region), narrowed by class when several share the name, then their profile."""
    from ..sources import official
    regions = [region] if region in official.REGIONS else list(official.REGIONS)
    for reg in regions:
        found = [m for m in official.search(name, region=reg, server_id=server_id, size=20)
                 if str(m.get("name") or "").casefold() == name.casefold() and str(m.get("server_id")) == str(server_id)]
        if len(found) > 1 and cls:
            found = [m for m in found if m.get("class") == cls] or found
        if len(found) > 1:
            return None                       # several characters of that name on that server: none is taken
        if found:
            profile = official.profile(found[0]["character_id"], server_id, reg)
            if str(profile.get("characterName") or "").casefold() != name.casefold():
                return None
            return {"combat_power": profile.get("combatPower"), "level": profile.get("characterLevel"), "region": reg}
    return None
