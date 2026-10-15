"""Shared back-off for the anonymous community beacons and the automatic uploads.

Every beacon is best-effort, but best-effort must never mean "keep hammering": once the log
server answers **429** (its per-IP hourly bucket for that beacon is spent), re-sending every
pending report on the next 15-second checkpoint save produces hundreds more rejections an hour
and nothing else. A :class:`Backoff` remembers the server's ``Retry-After`` (or a default pause)
and the callers skip the network until it passes. A 4xx other than 429/408 means the server will
never accept that exact body, so callers mark it done instead of retrying it forever.
"""
from __future__ import annotations

import time
import urllib.error

DEFAULT_PAUSE_S = 900.0          # when the server sends no Retry-After
MIN_PAUSE_S, MAX_PAUSE_S = 60.0, 3600.0


def retry_after_seconds(headers, default: float = DEFAULT_PAUSE_S) -> float:
    """Seconds to wait from a ``Retry-After`` header (delta-seconds form), bounded to a sane range."""
    value = None
    try:
        raw = headers.get("Retry-After") if headers is not None else None
        if raw is not None:
            value = float(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        value = None
    if value is None or value != value:            # missing, malformed or NaN
        value = default
    return min(MAX_PAUSE_S, max(MIN_PAUSE_S, value))


class Backoff:
    """A pause the caller honours before its next network attempt."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._until = 0.0

    def paused(self) -> bool:
        return self._clock() < self._until

    def remaining(self) -> float:
        return max(0.0, self._until - self._clock())

    def pause(self, headers=None, default: float = DEFAULT_PAUSE_S) -> float:
        wait = retry_after_seconds(headers, default)
        self._until = max(self._until, self._clock() + wait)
        return wait

    def clear(self) -> None:
        self._until = 0.0


def rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code == 429


def permanent_rejection(exc: BaseException) -> bool:
    """A 4xx the server will keep refusing for this body (never 429/408), so it is dropped, not retried."""
    return isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code not in (408, 429)
