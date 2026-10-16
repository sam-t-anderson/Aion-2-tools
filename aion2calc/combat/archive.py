"""Submitted storage-part continuity; not capture authenticity or completeness."""
import re


def clean_continuity(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        return None
    token = value.get("token")
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        return None
    keys = ("first_sequence", "last_sequence", "retained_records")
    if any(type(value.get(k)) is not int or not 1 <= value[k] <= 2**53-1 for k in keys):
        return None
    first, last, count = (value[k] for k in keys)
    if first > last or count > last-first+1:
        return None
    result = {"version":1, "token":token, **{k:value[k] for k in keys}}
    if "first_epoch" in value or "last_epoch" in value:
        if any(type(value.get(k)) is not int or not 0 <= value[k] <= 2**53-1 for k in ("first_epoch", "last_epoch")) or value["first_epoch"] > value["last_epoch"]:
            return None
        result.update(first_epoch=value["first_epoch"], last_epoch=value["last_epoch"])
    previous = value.get("previous_token")
    if previous is not None:
        end = value.get("previous_last_sequence")
        if (not isinstance(previous, str) or not re.fullmatch(r"[0-9a-f]{32}", previous)
                or type(end) is not int or not 1 <= end <= 2**53-1):
            return None
        result.update(previous_token=previous, previous_last_sequence=end)
    return result


def retained_range(session, token, previous=None):
    if not session.records:
        return None
    result = {"version":1, "token":token, "first_sequence":session.records[0].sequence,
              "last_sequence":session.records[-1].sequence, "retained_records":len(session.records),
              "first_epoch":session.records[0].epoch, "last_epoch":session.records[-1].epoch}
    if previous:
        result.update(previous_token=previous["token"], previous_last_sequence=previous["last_sequence"])
    return clean_continuity(result)


def describe(archive, previous=None, duplicate=False):
    """How a saved part's retained-record range relates to its predecessor's, from the submitted
    counters and part links alone.

    Record sequence continuity is the evidence: ``connected`` means the continuation's first
    retained record is the very next one after the predecessor's last, so no decoded record is
    missing or repeated between the two. A capture or identity context (the record epoch, which
    advances on every zone load -- a dungeon run has several, and the storage rollover fires in the
    pause between dungeons, right after one) may advance within a part or across the boundary
    without breaking that; the combined review accepts the same nondecreasing contexts. Only a
    context that goes *backwards* across the boundary contradicts the part link. Such a part is
    reported ``connected`` with ``context_changed`` set, never as a break: treating every zone load
    as one kept almost every real recording's parts apart (and its runs unstitched)."""
    current = clean_continuity(archive.get("continuity"))
    def status(code, label, **extra):
        return {"code":code, "label":label, **extra,
                "note":"Submitted record counters and part links; not verified packet continuity, identity or run completion."}
    if duplicate:
        return status("duplicate", "Multiple uploads/files for this part")
    if not current:
        return status("unavailable", "Continuity metadata not recorded")
    if current["retained_records"] != current["last_sequence"]-current["first_sequence"]+1:
        return status("internal_gap", "Gap within retained record range")
    changed_within = current.get("first_epoch") is not None and current.get("first_epoch") != current.get("last_epoch")
    if archive.get("part") == 1:
        if current["first_sequence"] == 1 and not current.get("previous_token"):
            return status("start", "Starts at retained record 1" + (" (capture or identity context changed within the part)" if changed_within else ""),
                          context_changed=changed_within)
        return status("start_gap", "Earlier retained records unavailable", context_changed=changed_within)
    parent = clean_continuity((previous or {}).get("continuity"))
    if not parent:
        return status("parent_unavailable", "Previous part unavailable or ambiguous in this list")
    if current.get("previous_token") != parent["token"] or current.get("previous_last_sequence") != parent["last_sequence"]:
        return status("parent_mismatch", "Predecessor does not match this saved part")
    delta = current["first_sequence"]-parent["last_sequence"]-1
    if delta < 0:
        return status("overlap", "Overlapping retained record ranges")
    if delta > 0:
        # An unfinished (snapshot) predecessor is missing its tail: that is the gap. A snapshot whose
        # last record the continuation follows directly holds everything up to the rollover.
        if not previous.get("closed"):
            return status("parent_open", "Previous part is an unfinished storage part")
        return status("gap", "Gap between retained record ranges")
    if (current.get("first_epoch") is not None and parent.get("last_epoch") is not None
            and current["first_epoch"] < parent["last_epoch"]):
        return status("context_change", "Capture or identity context goes backwards across the parts")
    changed = changed_within or (current.get("first_epoch") is not None and parent.get("last_epoch") is not None
                                 and current["first_epoch"] != parent["last_epoch"])
    return status("connected", "Submitted ranges connect" + (" (capture or identity context changed)" if changed else ""),
                  context_changed=changed)
