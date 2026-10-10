"""Deduplicate the same boss defeat seen from several uploaders' perspectives.

When a party kills a boss, each member who records it uploads a separate log of
the one fight. For respawn, availability or clear-count estimates those are one
defeat, not many, so they must be grouped before counting. Two uploads are
treated as the same defeat when they name the same boss in the same region, led
by a shared party (overlapping recorded player identities), for about the same
duration. This is a heuristic on the identities and timing an upload carries,
not proof: identical repeat clears by the same party are deliberately left
separate only by their duration spread, so the result marks confidence and
never collapses fights whose rosters do not overlap.

Input rows are the public log listing (``/api/v1/logs``) or full documents;
both carry ``boss``, ``region``, ``players`` and ``duration``. Rows are
untrusted upload data and only these bounded fields are read.
"""
from __future__ import annotations

#: Name prefixes that mark a placeholder boss, not an identified encounter to dedupe.
_GENERIC = ("combat ", "training", "unknown")


def _roster(row) -> frozenset:
    return frozenset(p.get("id") for p in (row.get("players") or []) if isinstance(p, dict) and p.get("id"))


def _ctx(row, key):
    """Read a bounded context field from a listing row, falling back to the
    first per-segment context block the server attaches (``contexts``)."""
    if row.get(key) not in (None, ""):
        return row.get(key)
    contexts = row.get("contexts")
    if isinstance(contexts, list) and contexts and isinstance(contexts[0], dict):
        return contexts[0].get(key)
    return None


def _difficulty(row):
    d = _ctx(row, "difficulty")
    return str(d).strip().casefold() if d not in (None, "") else None


def _instance(row):
    try:
        iid = int(_ctx(row, "instance_id") or 0)
    except (TypeError, ValueError):
        return 0
    return iid


def _named(row) -> bool:
    boss = str(row.get("boss") or "").strip().casefold()
    return bool(boss) and not any(boss.startswith(g) for g in _GENERIC)


def _same_defeat(a, b, *, min_overlap: float, duration_tol: float) -> bool:
    if str(a.get("boss") or "").casefold() != str(b.get("boss") or "").casefold():
        return False
    if (a.get("region") or None) != (b.get("region") or None):
        return False
    da_diff, db_diff = _difficulty(a), _difficulty(b)
    if da_diff and db_diff and da_diff != db_diff:         # a normal and a nightmare clear are different defeats
        return False
    ia, ib = _instance(a), _instance(b)
    if ia and ib and ia != ib:                             # distinct recorded instances are different defeats
        return False
    ra, rb = _roster(a), _roster(b)
    if not ra or not rb:
        return False
    shared = len(ra & rb)
    jaccard = shared / len(ra | rb)
    if shared < 2 and jaccard < min_overlap:               # a lone shared id is too weak
        return False
    da, db = float(a.get("duration") or 0), float(b.get("duration") or 0)
    if da <= 0 or db <= 0:
        return False
    return abs(da - db) <= max(5.0, duration_tol * max(da, db))


def dedupe_defeats(logs, *, min_overlap: float = 0.5, duration_tol: float = 0.1) -> dict:
    """Group uploads that are the same boss defeat; returns distinct defeats with
    their perspectives, most-corroborated first."""
    named = [row for row in logs if isinstance(row, dict) and _named(row)]
    parent = list(range(len(named)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(named)):
        for j in range(i + 1, len(named)):
            if find(i) != find(j) and _same_defeat(named[i], named[j], min_overlap=min_overlap, duration_tol=duration_tol):
                parent[find(i)] = find(j)
    clusters: dict = {}
    for i, row in enumerate(named):
        clusters.setdefault(find(i), []).append(row)
    groups = []
    for rows in clusters.values():
        rows = sorted(rows, key=lambda r: -float(r.get("duration") or 0))
        rosters = [_roster(r) for r in rows]
        union = frozenset().union(*rosters) if rosters else frozenset()
        groups.append({
            "boss": rows[0].get("boss"), "region": rows[0].get("region"),
            "difficulty": next((_difficulty(r) for r in rows if _difficulty(r)), None),
            "instance_id": next((_instance(r) for r in rows if _instance(r)), 0) or None,
            "perspectives": len(rows),
            "duration": round(float(rows[0].get("duration") or 0), 1),
            "party_size": max((len(r) for r in rosters), default=0),
            "distinct_identities": len(union),
            "logs": [{"id": r.get("id"), "duration": round(float(r.get("duration") or 0), 1),
                      "top_dps": round(float(r.get("top_dps") or 0)) if r.get("top_dps") else None} for r in rows],
            "confidence": "corroborated" if len(rows) > 1 else "single",
        })
    groups.sort(key=lambda g: (-g["perspectives"], str(g["boss"])))
    return {"total_logs": len(logs), "named_logs": len(named), "distinct_defeats": len(groups),
            "duplicate_logs": len(named) - len(groups), "groups": groups,
            "note": ("Same-defeat grouping uses boss, region, difficulty, recorded instance, shared party "
                     "identities and matching duration. It is a heuristic for respawn/availability counting, not "
                     "proof; clears at different difficulties or distinct recorded instances are never merged, "
                     "repeat clears by one party separate only by duration, and non-overlapping rosters are "
                     "never merged.")}


def rows_from_docs(docs) -> list:
    """Flatten saved a2log documents into the same bounded listing rows the
    server returns, one per fight segment, so an operator can dedupe their own
    local corpus offline exactly as :func:`from_server` feeds the server's.

    Each segment becomes one defeat perspective carrying that segment's boss,
    region and duration and the document's recorded player identities; only
    these fields are read. A document holding several fights contributes one
    row per fight, so a single multi-segment upload never looks like duplicate
    perspectives of one defeat (the segment id keeps them distinct)."""
    rows = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        players = [p for p in (doc.get("players") or []) if isinstance(p, dict) and p.get("id")]
        title = (doc.get("meta") or {}).get("title") if isinstance(doc.get("meta"), dict) else None
        for seg in (doc.get("segments") or []):
            if not isinstance(seg, dict):
                continue
            rows.append({
                "id": f"{title or 'local'}#{seg.get('id')}",
                "boss": seg.get("boss"),
                "region": seg.get("region"),
                "duration": seg.get("duration"),
                "difficulty": seg.get("difficulty"),
                "instance_id": seg.get("instance_id"),
                "players": players,
            })
    return rows


def from_server(limit: int = 500, *, base_url: str | None = None):
    """The public log listing from the configured community server, for dedup."""
    import json
    import urllib.request
    from .share import default_server
    base = (base_url or default_server().get("url") or "").rstrip("/")
    if not base:
        return []
    try:
        request = urllib.request.Request(base + f"/api/v1/logs?limit={int(limit)}",
                                         headers={"User-Agent": "Aion2Calc", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            listing = json.load(response)
    except Exception:
        return []
    rows = listing.get("logs", listing) if isinstance(listing, (dict, list)) else []
    return rows if isinstance(rows, list) else []
