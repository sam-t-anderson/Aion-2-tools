"""Tiny cached HTTP fetcher used by every scraper.

Pages are cached on disk (``cache`` in the user folder, see
:func:`aion2calc.paths.home`, or ``$AION2CALC_CACHE``) so a full refresh can be
re-run offline and so the sites are not hammered.  Proxies and CA bundles are
taken from the usual environment variables by ``urllib``.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")



def cache_dir() -> Path:
    if os.environ.get("AION2CALC_CACHE"):
        return Path(os.environ["AION2CALC_CACHE"])
    from ..paths import home
    return home() / "cache"

_last_request = 0.0
_lock = threading.Lock()


class NotFound(RuntimeError):
    """The server answered 4xx (page renamed or removed); not worth retrying."""


def _throttle(delay: float) -> None:
    global _last_request
    with _lock:
        wait = delay - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()


def _get(url: str, headers: dict, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if 400 <= err.code < 500 and err.code != 429:
                raise NotFound(f"{err.code} for {url}") from err
            last_err = err
        except Exception as err:  # network hiccups: back off and retry
            last_err = err
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"fetch failed for {url}: {last_err}")


def fetch(url: str, *, max_age: float = 7 * 86400, delay: float = 0.4,
          referer: str | None = None, cache: bool = True) -> str:
    """Return the body of ``url`` as text, using the on-disk cache when fresh.

    ``cache=False`` skips writing the page to disk (bulk syncs parse and drop).
    """
    key = hashlib.sha1(url.encode()).hexdigest()
    path = cache_dir() / f"{key}.html"
    if cache and path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_text(encoding="utf-8", errors="replace")
    _throttle(delay)
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    body = _get(url, headers).decode("utf-8", errors="replace")
    if cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return body


def fetch_json(url: str, params: dict | None = None, *, referer: str | None = None,
               delay: float = 0.3, headers: dict | None = None):
    """GET a JSON API (official site); never cached on disk."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None})
    _throttle(delay)
    h = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    if referer:
        h["Referer"] = referer
    return json.loads(_get(url, h, timeout=30).decode("utf-8", errors="replace"))


def fetch_bytes(url: str, *, max_age: float = 30 * 86400) -> bytes | None:
    """Binary variant of :func:`fetch` (icons); returns None on failure."""
    key = hashlib.sha1(url.encode()).hexdigest()
    path = cache_dir() / f"{key}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            path.write_bytes(data)
            return data
        except Exception:
            time.sleep(1 + attempt)
    return None
