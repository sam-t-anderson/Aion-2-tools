"""Conservative, reproducible ranking eligibility from submitted capture evidence.

This assesses completeness, not authenticity. Uploaded JSON is not anti-cheat proof.
"""
from __future__ import annotations

import re

DECODER = "a2tools-python-v1"
COUNTERS = ("discarded_effects", "discarded_segments", "discarded_telemetry",
            "validation_discarded", "tcp_discarded_payloads", "tcp_unresolved_flows", "capture_errors", "decoder_errors", "shutdown_discarded_payloads", "pcap_dropped", "pcap_if_dropped")
LABELS = {
    "classification_conflict": "Recorded map/instance and catalog evidence conflict; review encounter classification.",
    "classification_map_only": "A catalog map match suggests an instance, but its instance/entry evidence was not recorded; metrics remain descriptive.",
    "classification_npc_only": "NPC catalog matches suggest an instance, but its map/entry was not recorded; metrics remain descriptive.",
    "reconstructed": "Combined recording review: source-part completeness and ranking eligibility are not inherited.",
    "partial_capture": "Partial capture: instance entry or player membership was not established; metrics are descriptive only.",
    "party_roster_late": "The first party roster arrived after combat; earlier party membership is unverified.",
    "storage_boundary": "This archive part crosses a storage boundary; full fight/run completeness is not established.",
    "missing_metadata": "Record the game version, difficulty and encounter category.",
    "unverified_category": "The encounter category has not been identified.",
    "start_unverified": "A boss at full health was not observed at the start of this encounter.",
    "end_unverified": "The deaths of all recorded bosses were not observed.",
    "boss_unverified": "No identified boss NPC was recorded.",
    "identity_unverified": "A participating player is missing a name, server or class.",
    "capture_loss": "Capture/driver reported discarded data, interruption or validation loss.",
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
    classification = segment.get("classification") or {}
    if classification.get("status") == "conflict":
        reasons.append("classification_conflict")
    if classification.get("basis") == "recorded_map" and classification.get("catalog_instance_id") and not classification.get("recorded_instance_id"):
        reasons.append("classification_map_only")
    if classification.get("basis") == "npc_only":
        reasons.append("classification_npc_only")
    if capture.get("reconstructed") is True or meta.get("reconstruction"):
        reasons.append("reconstructed")
    if (segment.get("partial_capture") is True
            or bool(segment.get("instance_id")) and segment.get("run_start_observed") is False
            or meta.get("capture_scope") == "all"):
        reasons.append("partial_capture")
    if capture.get("storage_boundary") is True:
        reasons.append("storage_boundary")
    if segment.get("party_roster_late") is True:
        reasons.append("party_roster_late")
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
    from ..meter.a2parser.capture_stats import NOTE
    monitoring = {"sampled":capture.get("pcap_stats_sampled") is True,
                  "partial":capture.get("pcap_stats_partial") is True,
                  **{k:capture.get(k) for k in ("pcap_received", "pcap_dropped", "pcap_if_dropped", "pcap_stats_reads")},
                  "note":NOTE}
    return {"policy_version": 1, "driver_monitoring":monitoring,
            "capture_processing": {k:capture.get(k) for k in ("capture_errors", "decoder_errors", "shutdown_discarded_payloads", "shutdown_drained_payloads")}, "eligible": not reasons,
            "status": "eligible" if not reasons else "unranked",
            "reasons": reasons, "messages": [LABELS[k] for k in reasons],
            "note": "Completeness checks use submitted telemetry; they do not verify authenticity or prove that every packet was captured."}
