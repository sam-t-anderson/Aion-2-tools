"""The pictures this window could not read (0.2.475), as asset-health.js keeps a page's image failures: for Settings'
**Export image coverage**, which adds them to the app's own report, and **Retry images**, which forgets them so each
picture is asked for again the next time a view shows it.

Like the web page's, it keeps the pictures on the public hosts alone, by address, at most 200 of them: never a
portrait's or a character's details, and only for as long as the window is open.
"""
from __future__ import annotations

import time
import urllib.parse
import weakref

#: The public hosts the pictures come from (asset-health.js ``hosts``).
HOSTS = {"metabot.gg", "assets.playnccdn.com", "profileimg.plaync.com", "a2dil.com", "gamers4.life", "dbaion2.ru",
         "aion2hub.com"}
LIMIT = 200                                    # addresses kept; the oldest goes when another fails
RETRY_DELAY_S = 300                            # how long the web page shows a failed picture's placeholder
NOTE = ("References identify the assets requested by rendered views, not verified URL-to-ID mappings. Official IDs "
        "stay region-scoped and separate from catalog slugs. Portrait IDs, labels, full URLs and character data are "
        "excluded. Counts are image error events, not unique assets.")

_failures: dict[str, dict] = {}
_evicted = 0
_readers: "weakref.WeakSet" = weakref.WeakSet()   # the pictures' readers, told to read again on Retry images


def _resource(url) -> str | None:
    """A picture's address when it is on one of the public hosts over HTTPS (``resource``), else None."""
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
        if parts.scheme != "https" or parts.hostname not in HOSTS or parts.username or parts.password:
            return None
        if parts.port not in (None, 443):
            return None
    except ValueError:
        return None
    return urllib.parse.urlunsplit(parts)


def failed(url) -> None:
    """A picture that could not be read (the page's ``error`` event)."""
    global _evicted
    address = _resource(url)
    if address is None:
        return
    row = _failures.get(address)
    if row is None and len(_failures) >= LIMIT:
        _failures.pop(next(iter(_failures)))
        _evicted += 1
    if row is None:
        skill = None
        parts = urllib.parse.urlsplit(address)
        if parts.hostname == "metabot.gg" and parts.path.startswith("/web/aion2/skills/") and parts.path.endswith(".webp"):
            stem = parts.path[len("/web/aion2/skills/"):-len(".webp")]
            skill = stem if stem.isdigit() and len(stem) <= 20 else None
        row = {"host": parts.hostname, "skill_id": skill, "count": 0, "references": [], "references_truncated": False}
        if skill is not None:
            row["references"].append({"namespace": "metabot", "kind": "skill", "id": skill})
    row["count"] += 1
    row["last_failed"] = int(time.time() * 1000)
    _failures[address] = row


def report() -> dict:
    """The failures as the web page reports them (``A2AssetHealth.report``)."""
    return {"version": 2, "scope": "This window's lifetime; cleared when it closes or on Retry images",
            "http_status": "Not available from the window's picture reads", "retry_delay_seconds": RETRY_DELAY_S,
            "limit": LIMIT, "reference_limit": 8, "evicted_resources": _evicted, "note": NOTE,
            "failures": [{**row, "references": [dict(r) for r in row["references"]]} for row in _failures.values()]}


def watch(reader) -> None:
    """A pictures' reader with a ``retry_pictures()`` to call on Retry images."""
    _readers.add(reader)


def retry() -> None:
    """Every failure forgotten, and each reader told to read its pictures again when they are next shown
    (``A2AssetHealth.retry``)."""
    global _evicted
    _failures.clear()
    _evicted = 0
    for reader in list(_readers):
        try:
            reader.retry_pictures()
        except RuntimeError:                   # its window has gone
            pass
