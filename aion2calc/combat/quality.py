"""Conservative, reproducible ranking eligibility from submitted capture evidence.

This assesses completeness, not authenticity. Uploaded JSON is not anti-cheat proof.
"""
from __future__ import annotations

import re

DECODER = "a2tools-python-v1"
COUNTERS = ("discarded_effects", "discarded_segments", "discarded_telemetry",
            "validation_discarded", "tcp_discarded_payloads", "tcp_unresolved_flows", "capture_errors", "decoder_errors", "shutdown_discarded_payloads", "pcap_dropped", "pcap_if_dropped")
# Frames the decoder skipped but recovered from (malformed / over-limit compressed frames, a
# single unsupported packet) are routine — a perfect frame stream is not achievable — so a
# handful never voids ranking. Only a *material* amount (more than RECOVERED_SKIP_FLOOR frames,
# or RECOVERED_SKIP_FRACTION of the packets received, whichever is larger) counts as capture loss.
RECOVERED_SKIP_FLOOR = 200
RECOVERED_SKIP_FRACTION = 0.02
# Kernel/driver packet-buffer drops (``pcap_dropped``/``pcap_if_dropped``) are a *cumulative,
# whole-session* counter stamped onto every fight in the session, so one early buffer overflow
# would otherwise unrank every later fight — including ones that lost nothing. Like the recovered
# frame-skip budget above, a handful of dropped packets is routine; only a *material* share of the
# session's received packets (more than PCAP_DROP_FLOOR, or PCAP_DROP_FRACTION of those received,
# whichever is larger) counts as capture loss. Genuine decode/validation losses below still void
# ranking on any nonzero count.
#: a boss counts as seen at full health when its first sample is within this share of its maximum
#: (the opening hit lands with the sample) and no later than this long after the party's first hit on it
FULL_HEALTH_TOLERANCE = 0.005
FULL_HEALTH_WINDOW_S = 0.5
PCAP_DROP_FLOOR = 500
PCAP_DROP_FRACTION = 0.02
# Counters that are a true per-event processing/validation loss (void ranking on any nonzero count).
# The kernel-buffer drop counters are handled separately with the fraction budget above.
HARD_LOSS_COUNTERS = tuple(k for k in COUNTERS if k not in ("pcap_dropped", "pcap_if_dropped"))
#: Counters that accumulate for the whole capture: every archive part of a recording repeats the
#: total so far, so a loss during the first hour is stamped on a part recorded two hours later.
#: A part's own share is the counter minus ``capture_quality.part_baseline`` -- the values at the
#: part's start, stamped by the recorder on each continuation part (the log server derives the
#: same baseline from the previous part for recordings made before it was stamped).
LIFETIME_COUNTERS = ("tcp_discarded_payloads", "tcp_unresolved_flows", "capture_errors", "decoder_errors",
                     "shutdown_discarded_payloads", "recovered_frame_skips", "pcap_dropped", "pcap_if_dropped",
                     "pcap_received")
#: Losses the recorder places in time (it notes when each one happened), so a fight is charged only
#: with the losses inside its own window: ``segment["capture_loss"]`` on documents whose
#: ``capture_quality.loss_attribution`` is "segment". Retention counters (``discarded_*``) describe
#: the whole part's history and stay part-wide.
TIMED_LOSS_COUNTERS = ("tcp_discarded_payloads", "tcp_unresolved_flows", "capture_errors", "decoder_errors",
                       "shutdown_discarded_payloads")
#: A TCP reassembly restart discards data buffered for up to five seconds before it, so a loss noted
#: at T may have cost a fight data from T - LOSS_WINDOW_BEFORE_S on; a fight whose window overlaps
#: [T - before, T + after] is charged with it.
LOSS_WINDOW_BEFORE_S = 6.0
LOSS_WINDOW_AFTER_S = 1.0
#: Documents from before per-segment validation accounting carry one whole-document
#: ``validation_discarded`` that also counted routine filtering (out-of-range or unreferenced
#: samples the validator dropped) -- not capture loss. Only a count large enough to be a size-cap
#: overflow (which drops recorded evidence) is treated as loss there.
VALIDATION_LEGACY_FLOOR = 100
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
    "frame_skips_material": "A large share of frames were skipped while decoding; the capture is materially incomplete.",
    "transport_unverified": "TCP loss monitoring was unavailable for this capture.",
    "tcp_pending": "The TCP stream still contains unresolved out-of-order data.",
    "decoder_unverified": "The decoder or application version is missing or unsupported.",
    "pvp_boundaries_unverified": "PvP match start/end detection is not yet verified.",
    "no_damage": "No outgoing player damage was recorded.",
    "party_scope_unverified": "A Party capture is required for comparable party encounters.",
    "timing_invalid": "Recorded damage extends beyond the encounter duration.",
}


def part_counter(capture, key):
    """A counter's share for this archive part: lifetime counters less the part's baseline."""
    value = capture.get(key) or 0
    if key in LIFETIME_COUNTERS:
        baseline = capture.get("part_baseline") or {}
        value -= baseline.get(key) or 0
    return max(0, value)


def observed_starts(segment, bosses):
    """The bosses seen at (essentially) full health before the party's first hit on them.

    A boss seen whole before it was pulled started the fight whole. The first HP sample usually
    lands with the opening hit, i.e. a hair below the maximum at t=0; and when trash merges into
    the same combat segment the boss is first seen (at full health) some seconds before it is
    pulled. Both are a start observed from the top."""
    first_hit: dict = {}
    for h in segment.get("hits") or []:
        target = h.get("target")
        if target in bosses and (target not in first_hit or h.get("t", 0) < first_hit[target]):
            first_hit[target] = h.get("t", 0)
    starts = set()
    for sample in segment.get("health") or []:
        entity, maximum, current = sample.get("entity"), sample.get("max") or 0, sample.get("current") or 0
        if maximum <= 0 or entity not in bosses:
            continue
        if (current >= maximum * (1 - FULL_HEALTH_TOLERANCE)
                and sample.get("t", 1) <= max(0.0, first_hit.get(entity, 0.0)) + FULL_HEALTH_WINDOW_S):
            starts.add(entity)
    return starts


def segment_losses(capture, segment):
    """The timed losses charged to this fight, or ``None`` when the recorder did not place its
    losses in time (older recordings: the counters are then read part-wide)."""
    timed = segment.get("capture_loss")
    if capture.get("loss_attribution") == "segment" and isinstance(timed, dict):
        return {k: timed.get(k) or 0 for k in TIMED_LOSS_COUNTERS}
    return None


def lost_data(capture, segment):
    """Whether this fight is charged with capture/driver/validation loss."""
    timed = segment_losses(capture, segment)
    for key in HARD_LOSS_COUNTERS:
        if key == "validation_discarded":
            continue
        if timed is not None and key in TIMED_LOSS_COUNTERS:
            if timed[key] > 0:
                return True
        elif part_counter(capture, key) > 0:
            return True
    validation = segment.get("validation")
    if isinstance(validation, dict) and "capped" in validation:
        return (validation.get("capped") or 0) > 0      # only a size-cap overflow drops recorded evidence
    return (capture.get("validation_discarded") or 0) > VALIDATION_LEGACY_FLOOR


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
    # ``storage_boundary`` is a part-edge property: a saved archive part and its continuation are
    # both flagged, so every long session (which rolls storage over many times) marks every part.
    # It only threatens a fight that could have been *truncated* by the boundary — one whose own
    # start or end fell outside this part. A fight that observed its own start and reached its own
    # verified end (a kill, or a cleanly completed run) is wholly contained in this part and is not
    # boundary-incomplete, so the part rolling over at its edges must not unrank it. Fights that are
    # not self-contained are still caught here (and by partial_capture / start_/end_unverified).
    self_contained = (segment.get("run_start_observed") is True
                      and bool(segment.get("run_complete") or segment.get("killed")))
    if capture.get("storage_boundary") is True and not self_contained:
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
    # Loss is charged to the fights it can have touched: timed losses inside each fight's own window
    # when the recorder placed them, this archive part's own share of the lifetime counters
    # otherwise (see LIFETIME_COUNTERS / TIMED_LOSS_COUNTERS).
    received = part_counter(capture, "pcap_received")
    dropped = part_counter(capture, "pcap_dropped") + part_counter(capture, "pcap_if_dropped")
    drop_budget = max(PCAP_DROP_FLOOR, int(PCAP_DROP_FRACTION * received))
    if lost_data(capture, segment) or dropped > drop_budget:
        reasons.append("capture_loss")
    skip_budget = max(RECOVERED_SKIP_FLOOR, int(RECOVERED_SKIP_FRACTION * received))
    if part_counter(capture, "recovered_frame_skips") > skip_budget:
        reasons.append("frame_skips_material")
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
    starts = observed_starts(segment, bosses)
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
    timed = segment_losses(capture, segment)
    return {"policy_version": 1, "driver_monitoring":monitoring,
            "capture_processing": {k:capture.get(k) for k in ("capture_errors", "decoder_errors", "recovered_frame_skips", "shutdown_discarded_payloads", "shutdown_drained_payloads")},
            # how loss was charged to this fight: its own timed window, this part's share, or the whole session
            "loss_attribution": "segment" if timed is not None else "part" if capture.get("part_baseline") else "session",
            "segment_loss": timed, "validation": segment.get("validation") if isinstance(segment.get("validation"), dict) else None,
            "eligible": not reasons,
            "status": "eligible" if not reasons else "unranked",
            "reasons": reasons, "messages": [LABELS[k] for k in reasons],
            "note": "Completeness checks use submitted telemetry; they do not verify authenticity or prove that every packet was captured."}
