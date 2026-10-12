"""Extract a player's community standing from a log server ``rankings`` payload.

The log server's ``rankings`` response (see the server's ``reports.rankings``) ranks
each player in three scopes — ``server`` (home world), ``region`` and ``world`` — each
either ``None`` (no eligible matched comparison) or a comparison object carrying a
``percentile``. This helper turns that into a compact per-player badge the overlay can
show for the just-finished, auto-uploaded fight.

Pure and defensive: it never raises on a partial or unexpected payload (the server may
be older, the lookup may not have resolved), so the overlay simply shows nothing until a
real percentile is available. The actual fetch of the rankings (after the auto-upload
completes) is wired by the app; this module only interprets what comes back.
"""
from __future__ import annotations

# Most specific first: a same-world standing is the most meaningful to show, then the
# regional cluster, then the global pool. The badge renders the first one available.
SCOPES = ("server", "region", "world")
LABELS = {"server": "Server", "region": "Region", "world": "World"}


def _percentile(entry):
    """A 0–100 float from a *confident* comparison object, or None.

    Confident means the server itself ranked it: a ``status`` other than
    ``"available"`` (insufficient samples, dataset cap, incomparable metadata) is
    treated as no standing, so a provisional or too-thin cohort shows nothing
    rather than a number that will swing as more logs arrive. A payload without a
    ``status`` key (older server, or a hand-built one) is accepted on its value."""
    if not isinstance(entry, dict):
        return None
    status = entry.get("status")
    if isinstance(status, str) and status != "available":
        return None
    value = entry.get("percentile")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value < 0 or value > 100:
        return None
    return float(value)


def for_player(rankings, player_id):
    """Return ``{"scopes": {scope: pct}, "best": {"scope", "label", "percentile"}}`` for
    one player in a server rankings payload, or ``None`` when nothing can be shown.

    ``best`` is the most specific scope that produced a percentile (server > region >
    world), which is what the overlay badge displays; ``scopes`` keeps every available
    percentile for a fuller tooltip."""
    if not isinstance(rankings, dict):
        return None
    players = rankings.get("players")
    if not isinstance(players, list):
        return None
    entry = next((p for p in players if isinstance(p, dict) and p.get("id") == player_id), None)
    if entry is None:
        return None
    scopes = {}
    for scope in SCOPES:
        pct = _percentile(entry.get(scope))
        if pct is not None:
            scopes[scope] = pct
    if not scopes:
        return None
    best_scope = next(scope for scope in SCOPES if scope in scopes)
    return {"scopes": scopes,
            "best": {"scope": best_scope, "label": LABELS[best_scope], "percentile": scopes[best_scope]}}


def badges(rankings, player_ids):
    """``{player_id: summary}`` for each id that has a confident standing, so the
    overlay can badge the local player and resolved party members alike. Ids with no
    confident scope are omitted."""
    out = {}
    for pid in player_ids or []:
        summary = for_player(rankings, pid)
        if summary is not None:
            out[pid] = summary
    return out


def badge_text(summary):
    """A short overlay label like ``"World Top 8%"`` from a ``for_player`` result, or ""."""
    if not isinstance(summary, dict):
        return ""
    best = summary.get("best") or {}
    pct = best.get("percentile")
    if not isinstance(pct, (int, float)):
        return ""
    # Percentile is "fraction at or below"; a high percentile is a top finish.
    top = max(0.1, round(100 - pct, 1))
    top_text = str(int(top)) if float(top).is_integer() else f"{top:g}"
    return f"{best.get('label', 'World')} Top {top_text}%"
