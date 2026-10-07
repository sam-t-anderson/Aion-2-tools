"""Bounded process-local counters for the desktop image proxy; no resource URLs."""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_counts = {}
_STARTED = time.time()
_HOSTS = ("metabot.gg", "assets.playnccdn.com", "profileimg.plaync.com", "a2dil.com")


def record(host, outcome, status=None):
    # Retain approved source domains only, never paths, query strings or exception messages.
    host = next((base for base in _HOSTS if host == base or host.endswith("." + base)), None)
    if host is None or outcome not in ("cache_hit", "http_success", "http_error", "fetch_error", "empty_body"):
        return
    code = status if type(status) is int and 100 <= status <= 599 else None
    key = (host, outcome, code)
    with _lock:
        row = _counts.setdefault(key, {"host":host, "outcome":outcome, "http_status":code, "count":0, "last_observed":0})
        row["count"] += 1
        row["last_observed"] = time.time()


def report():
    with _lock:
        rows = [dict(row) for _, row in sorted(_counts.items(), key=lambda pair: str(pair[0]))]
    return {"scope":"This desktop process", "started_at":_STARTED, "observations":rows,
            "note":"Counts are request attempts, not unique missing assets. Fetch/cache errors have no HTTP status. Cache hits do not check remote availability. Full URLs, image paths, character identities and exception text are not retained. Browser-direct images are reported separately."}
