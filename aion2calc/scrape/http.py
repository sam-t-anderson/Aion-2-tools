"""Tiny cached HTTP fetcher used by every scraper.

Pages are cached on disk (default ``.cache/aion2calc``) so a full refresh can be
re-run offline and so the sites are not hammered.  Proxies and CA bundles are
taken from the usual environment variables by ``urllib``.
"""
from __future__ import annotations

import hashlib
import os
import time
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CACHE_DIR = Path(os.environ.get("AION2CALC_CACHE", ".cache/aion2calc"))
_last_request = 0.0


def fetch(url: str, *, max_age: float = 7 * 86400, delay: float = 0.4,
          referer: str | None = None) -> str:
    """Return the body of ``url`` as text, using the on-disk cache when fresh."""
    global _last_request
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    path = CACHE_DIR / f"{key}.html"
    if path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_text(encoding="utf-8", errors="replace")
    wait = delay - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            break
        except Exception as err:  # network hiccups: back off and retry
            last_err = err
            time.sleep(2 ** (attempt + 1))
    else:
        raise RuntimeError(f"fetch failed for {url}: {last_err}")
    _last_request = time.time()
    path.write_text(body, encoding="utf-8")
    return body


def fetch_bytes(url: str, *, max_age: float = 30 * 86400) -> bytes | None:
    """Binary variant of :func:`fetch` (icons); returns None on failure."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    path = CACHE_DIR / f"{key}.bin"
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
