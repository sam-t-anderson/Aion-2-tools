"""Opt-out, anonymous enemy *effective-HP* community report.

An enemy's packet HP is on a larger, different scale than the damage needed to
kill it, so the meter cannot turn packets alone into a real "X% of HP". The one
signal every meter *can* measure precisely is how much damage an enemy took to
die. When the meter finalises a session in which an enemy died, this posts one
tiny, anonymous observation per killed enemy to the community server's
``/api/v1/enemy-hp`` endpoint, so the server can build a per-build consensus of
each enemy's effective HP (see ``enemy_hp.py`` on the server) and hand it back
for the client to blend into a real HP%.

Each report carries no account, character, or capture data -- only what the
consensus needs:

* an anonymous, stable **per-install reporter key**, distinct from the boss and
  heartbeat keys, derived from the same local-only salt (never transmitted);
* the enemy's NPC id (mob code), its **effective HP** (total observed damage it
  took to die -- in a party this is the fullest damage we received, which can
  only ever UNDERCOUNT the truth, never overcount, so the server anchors high),
  the game's raw packet max HP (``observed_hp``, a different larger scale, kept
  for version sanity), the number of distinct attackers, and the **game build**
  so a balance patch never mixes HP scales.

Unlike the boss-kill report, this is **opt-out: on by default**. Nothing
identifying is sent, and the user can turn it off with "Share enemy HP data" in
Settings. ``report`` is best-effort, never raises, and reports each distinct
kill at most once (a bounded local marker dedupes repeated checkpoint saves of
the same fight).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.request

from .. import __version__
from ..paths import data_file, read_json, write_user_json
from . import heartbeat, share

_MARK_FILE = ("community", "enemy_hp_reports.json")
_ENDPOINT = "/api/v1/enemy-hp"
#: Keep the local dedup marker bounded; older signatures simply age out.
_MARK_LIMIT = 400
#: Server contract for a game-build string (matches the server's own regex).
_BUILD_RE = re.compile(r"[^A-Za-z0-9 ._:+-]")


def reporter_key() -> str:
    """A stable, anonymous per-install reporter key for enemy-HP reports. Derived
    from the local-only install salt, so it is the same across launches on one
    install and distinct between installs; it never reveals the salt and differs
    from both the daily heartbeat token and the boss-kill reporter key."""
    salt = heartbeat._install_salt()
    return hashlib.sha256(f"{salt}:enemy-hp-reporter".encode("utf-8")).hexdigest()[:32]


def enabled(ui: dict | None = None) -> bool:
    """Opt-OUT: enemy-HP reporting is ON unless the user explicitly turned it off.
    Nothing identifying is sent, so this helps every user by default; a single
    Settings toggle disables it."""
    if ui is None:
        try:
            from ..app import server
            ui = server.ui_settings()
        except Exception:
            ui = {}
    return ui.get("meter_report_enemy_hp", True) is not False


def _build(doc: dict, seg: dict) -> str:
    """The game build to key this observation on, so a balance patch never mixes HP
    scales. Prefers the content patch (what actually changes HP); sanitised to the
    server's allowed character set. Empty string when no build is known."""
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    for value in (seg.get("game_patch"), meta.get("game_patch"),
                  meta.get("installed_content_build"), meta.get("installed_build")):
        if isinstance(value, str) and value.strip():
            cleaned = _BUILD_RE.sub("", value.strip())[:48]
            if cleaned:
                return cleaned
    return ""


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _true_hp(timeline: list[tuple[float, float]], samples: list[tuple[float, float, float]]) -> float | None:
    """Overkill-stripped effective HP for one killed enemy, or None when the HP
    samples can't support it.

    The total observed damage overcounts true HP by the killing blow's overkill (its
    full, unclamped damage is recorded, not just the HP that remained). To strip it we
    use the enemy's own HP packets. At the last packet where the enemy is still ALIVE
    it is at fraction ``f = current/max`` and we have dealt ``D`` damage, so (seeing all
    the damage) ``true_HP = D / (1 - f)`` -- the damage over the fraction of HP it
    removed, in damage units. This keeps every point of HP actually removed and only
    the finisher's overkill is dropped: we stop before the lethal blow and scale the
    remaining ``f`` back up, replacing that blow with exactly the HP it needed.

    We anchor on the DEEPEST still-alive sample (smallest positive ``f``): the closer
    to death, the less we extrapolate and the less an HP-packet error moves the
    estimate. A ``current == 0`` sample is deliberately NOT used -- the damage summed up
    to it already includes the lethal blow's overkill, which would defeat the point.
    Partial visibility makes ``D`` (and so this) an UNDERcount per report -- which is
    fine: the server anchors on a high percentile across reporters, pushing the
    community value back up to the true HP.

    ``timeline`` is this enemy's (t, amount) damage events; ``samples`` its
    (t, current, max) HP packets."""
    if not timeline or not samples:
        return None
    timeline = sorted(timeline)
    best = None                                   # (fraction, t) of the deepest still-alive sample
    for t, current, mx in samples:
        if mx <= 0 or current <= 0 or current >= mx:  # need an alive, below-full packet
            continue
        frac = current / mx
        if best is None or frac < best[0]:
            best = (frac, t)
    if best is None:
        return None
    frac, t = best
    dealt = sum(a for et, a in timeline if et <= t + 1e-6)
    if dealt <= 0:
        return None
    return dealt / (1.0 - frac)


def _segment_observations(seg: dict, reporter: str, build: str) -> list[dict]:
    """Every killed enemy in one finalised segment, as ready-to-post report bodies.
    Effective HP is the enemy's true HP in damage units -- the overkill-stripped
    estimate from its HP packets (see :func:`_true_hp`), falling back to the total
    observed damage when no usable HP sample exists. We only report enemies that
    actually died; a live enemy's running total is a meaningless lower bound."""
    entities = {e["id"]: e for e in (seg.get("entities") or []) if isinstance(e, dict) and e.get("id")}
    dead = {ev.get("target") for ev in (seg.get("events") or [])
            if isinstance(ev, dict) and ev.get("kind") == "death"}
    damage: dict[str, float] = {}
    timeline: dict[str, list] = {}
    for ev in (seg.get("events") or []):
        if not isinstance(ev, dict) or ev.get("kind") != "damage":
            continue
        amount = _num(ev.get("amount"))
        if ev.get("target") is not None and amount and amount > 0:
            damage[ev["target"]] = damage.get(ev["target"], 0.0) + amount
            timeline.setdefault(ev["target"], []).append((_num(ev.get("t")) or 0.0, amount))
    attackers: dict[str, set] = {}
    for hit in (seg.get("hits") or []):
        if isinstance(hit, dict) and hit.get("target") and hit.get("player"):
            attackers.setdefault(hit["target"], set()).add(hit["player"])
    max_hp: dict[str, float] = {}
    health_pts: dict[str, list] = {}
    for sample in (seg.get("health") or []):
        if not isinstance(sample, dict):
            continue
        eid, mx, cur = sample.get("entity"), _num(sample.get("max")), _num(sample.get("current"))
        if not eid or not mx or mx <= 0:
            continue
        max_hp[eid] = max(max_hp.get(eid, 0.0), mx)
        if cur is not None:
            health_pts.setdefault(eid, []).append((_num(sample.get("t")) or 0.0, cur, mx))

    reports = []
    for eid, entity in entities.items():
        # Enemies only: never players (incl. PvP opponents, which carry is_player) or pets.
        if entity.get("kind") != "enemy" or entity.get("is_player"):
            continue
        if eid not in dead:
            continue                       # only a real kill gives a true effective HP
        try:
            code = int(entity.get("mob_code"))
        except (TypeError, ValueError):
            continue
        if not 0 < code < 10 ** 10:
            continue
        # Prefer the overkill-stripped true HP; fall back to total observed damage
        # (overkill-inclusive) only when the HP packets can't support the estimate.
        effective = _true_hp(timeline.get(eid, []), health_pts.get(eid, [])) or damage.get(eid, 0.0)
        observed = max_hp.get(eid, 0.0)
        if effective <= 0 or observed <= 0:
            continue                       # need both to calibrate the two scales
        body = {"reporter": reporter, "npc_id": code, "effective_hp": round(effective, 1),
                "observed_hp": round(observed, 1), "game_build": build,
                "attackers": max(1, len(attackers.get(eid, ()))), "client": __version__}
        for key in ("region", "difficulty"):
            value = seg.get(key)
            if isinstance(value, str) and value.strip():
                body[key] = value.strip()[:32]
        body["_sig"] = f"{code}:{seg.get('id')}:{build}"
        reports.append(body)
    return reports


def observations_from_doc(doc: dict) -> list[dict]:
    """Every killed-enemy effective-HP observation in a finalised a2log document, as
    ready-to-post report bodies (each carrying a private ``_sig`` for dedup, stripped
    before posting). Skips the whole document when no game build is known, since a
    report with no build cannot be keyed and the server would reject it."""
    if not isinstance(doc, dict):
        return []
    reporter = reporter_key()
    reports = []
    for seg in (doc.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        build = _build(doc, seg)
        if not build:
            continue
        reports.extend(_segment_observations(seg, reporter, build))
    return reports


def _already_reported(signatures: set[str]) -> set[str]:
    try:
        seen = read_json(*_MARK_FILE).get("reported") if data_file(*_MARK_FILE).exists() else []
    except Exception:
        return set()
    return {s for s in seen if isinstance(s, str)} & signatures if isinstance(seen, list) else set()


def _mark_reported(new: list[str]) -> None:
    try:
        existing = read_json(*_MARK_FILE).get("reported") if data_file(*_MARK_FILE).exists() else []
        existing = [s for s in existing if isinstance(s, str)] if isinstance(existing, list) else []
    except Exception:
        existing = []
    merged = (existing + [s for s in new if s not in existing])[-_MARK_LIMIT:]
    try:
        write_user_json({"reported": merged}, *_MARK_FILE)
    except Exception:
        pass


def _post(base: str, body: dict, key: str | None) -> None:
    headers = {"Content-Type": "application/json", "User-Agent": "aion2calc"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + _ENDPOINT, data, headers, method="POST")
    with urllib.request.urlopen(req, timeout=8) as response:
        response.read()


def report(doc: dict, ui: dict | None = None) -> str:
    """Best-effort: post any not-yet-reported killed-enemy effective-HP observations
    in ``doc``. Returns a short status string and never raises -- a failure just means
    the observation is not reported. Each kill is reported at most once per install."""
    try:
        if not enabled(ui):
            return "disabled"
        reports = observations_from_doc(doc)
        if not reports:
            return "no-kill"
        server = share.effective()
        base = str(server.get("url") or "").rstrip("/")
        if not base:
            return "no-server"
        by_sig = {b["_sig"]: b for b in reports}
        done = _already_reported(set(by_sig))
        fresh = {sig: body for sig, body in by_sig.items() if sig not in done}
        if not fresh:
            return "already"
        key = server.get("key")
        sent = []
        for sig, body in fresh.items():
            payload = {k: v for k, v in body.items() if k != "_sig"}
            try:
                _post(base, payload, key)
                sent.append(sig)
            except Exception:
                pass          # best-effort per enemy; a failure just retries next save
        if sent:
            _mark_reported(sent)
        return f"sent:{len(sent)}" if sent else "error"
    except Exception as exc:   # a community beacon must never affect the app
        return "error:" + type(exc).__name__


def report_async(doc: dict, ui: dict | None = None) -> None:
    """Fire :func:`report` on a daemon thread so a finalise/save never blocks on the
    network. Failures are swallowed."""
    try:
        if not enabled(ui):
            return
        threading.Thread(target=report, args=(doc, ui), daemon=True,
                         name="aion2-enemy-hp-report").start()
    except Exception:
        pass
