"""Conservative, reproducible ranking eligibility from submitted capture evidence.

This assesses completeness, not authenticity. Uploaded JSON is not anti-cheat proof.
"""
from __future__ import annotations

import re

DECODER = "a2tools-python-v1"
COUNTERS = ("discarded_effects", "discarded_segments", "discarded_telemetry",
            "validation_discarded", "tcp_discarded_payloads", "tcp_unresolved_flows", "capture_errors")
LABELS = {
    "missing_metadata": "Record the game patch, difficulty and encounter category.",
    "unverified_category": "The encounter category has not been identified.",
    "start_unverified": "A boss at full health was not observed at the start of this encounter.",
    "end_unverified": "The deaths of all recorded bosses were not observed.",
    "boss_unverified": "No identified boss NPC was recorded.",
    "identity_unverified": "A participating player is missing a name, server or class.",
    "capture_loss": "Capture data was discarded, interrupted or removed during validation.",
    "transport_unverified": "TCP loss monitoring was unavailable for this capture.",
    "tcp_pending": "The TCP stream still contains unresolved out-of-order data.",
    "decoder_unverified": "The decoder or application version is missing or unsupported.",
    "pvp_boundaries_unverified": "PvP match start/end detection is not yet verified.",
    "no_damage": "No outgoing player damage was recorded.",
    "party_scope_unverified": "A Party capture is required for comparable party encounters.",
    "timing_invalid": "Recorded damage extends beyond the encounter duration.",
}


def assess(doc, segment):
    """Return evidence and reasons; never accept an uploaded eligibility verdict."""
    meta = doc.get("meta") or {}
    capture = meta.get("capture_quality") or {}
    reasons = []
    kind = segment.get("encounter_type") or meta.get("encounter_type") or "unknown"
    if not all(segment.get(k) or meta.get(k) for k in ("game_patch", "difficulty")):
        reasons.append("missing_metadata")
    if kind in ("unknown", "pve_unverified", "pvp_other"):
        reasons.append("unverified_category")
    if capture.get("decoder") != DECODER or not capture.get("app_version"):
        reasons.append("decoder_unverified")
    if capture.get("transport_monitored") is not True:
        reasons.append("transport_unverified")
    if any(capture.get(k, 0) > 0 for k in COUNTERS):
        reasons.append("capture_loss")
    if capture.get("tcp_pending_bytes", 0) > 0:
        reasons.append("tcp_pending")
    if meta.get("capture_scope") != "party":
        reasons.append("party_scope_unverified")
    hits = segment.get("hits") or []
    if any(h.get("t", 0) > segment["duration"]+1 for h in hits):
        reasons.append("timing_invalid")
    if not any(h.get("damage", 0) > 0 for h in hits):
        reasons.append("no_damage")
    participating = {h["player"] for h in hits}
    participating.update(e.get(k) for e in segment.get("events", []) for k in ("source", "target"))
    players = [p for p in doc.get("players", []) if p["id"] in participating]
    if any(not p.get("class") or not p.get("server") or not p.get("name")
           or re.fullmatch(r"(?:Player\s*)?#?\d+", p["name"], re.I) for p in players):
        reasons.append("identity_unverified")
    bosses = {e["id"] for e in segment.get("entities", []) if e.get("is_boss") and e.get("mob_code")}
    starts = set()
    for sample in segment.get("health", []):
        if (sample.get("max", 0) > 0 and sample["current"] >= sample["max"]
                and sample.get("t", 1) <= 0):
            starts.add(sample["entity"])
    deaths = {e.get("target") for e in segment.get("events", []) if e.get("kind") == "death"}
    deaths.update(s["entity"] for s in segment.get("health", []) if s.get("current") == 0)
    if kind.startswith("pvp_"):
        reasons.append("pvp_boundaries_unverified")
    else:
        if not bosses:
            reasons.append("boss_unverified")
        if not bosses or not bosses <= starts:
            reasons.append("start_unverified")
        if not bosses or not bosses <= deaths or not segment.get("killed"):
            reasons.append("end_unverified")
    return {"policy_version": 1, "eligible": not reasons,
            "status": "eligible" if not reasons else "unranked",
            "reasons": reasons, "messages": [LABELS[k] for k in reasons],
            "note": "Completeness checks use submitted telemetry; they do not verify authenticity or prove that every packet was captured."}
