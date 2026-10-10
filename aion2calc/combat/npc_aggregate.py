"""Aggregate the bounded NPC decoder evidence carried in uploaded logs.

Each upload may carry ``meta.npc_diagnostics`` (see :mod:`npc_diagnostics`): a
bounded, public-safe record of what the live decoder observed for opcodes 64/65
— ``entity``, ``mob_code``, ``timestamp_ms`` and a decode ``status`` of
``type_decoded`` or ``type_marker_missing``. One upload rarely proves anything,
but across many uploads and uploaders the same numeric ``mob_code`` recurring
with a consistent decode is real evidence that it is a stable NPC type ID.

This module aggregates that evidence across a corpus and reports:

* **candidate NPC types** — numeric ``mob_code`` observations grouped by whether
  the bundled catalog already names them, names them with a placeholder
  (``???`` — Ascension content that is observed but unnamed), or does not know
  them at all. Only observations meeting support thresholds are *promoted*; the
  rest are kept with an explicit abstain reason. Names are never invented: a
  code is labelled only from the catalog.
* **identity / packet variants** — the decode-status mix per opcode, and the
  entities/records where the type marker was missing (``mob_code`` 0), which is
  the packet variant the decoder cannot yet classify.

Input documents are untrusted (uploaded by anyone), so every ``npc_diagnostics``
block is re-validated through :func:`npc_diagnostics.clean` before use, and only
its bounded numeric fields are read.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .npc_diagnostics import clean


def _placeholder(name) -> bool:
    return not name or str(name).strip(" ?") == "" or str(name).strip() == "???"


def aggregate(docs) -> dict:
    """Aggregate ``meta.npc_diagnostics`` across an iterable of a2log documents.

    Returns per-``mob_code`` observation counts (distinct uploads, epochs,
    records, opcodes, decode statuses) with the catalog name when known, plus a
    corpus-wide opcode/variant summary. Pure counting; it decides nothing.
    """
    from ..meter.a2parser.lookup import npc_info
    uploads = 0
    with_diag = 0
    per_code_logs: dict[int, set] = defaultdict(set)
    per_code_epochs: dict[int, set] = defaultdict(set)
    records = Counter()
    opcodes: dict[int, Counter] = defaultdict(Counter)
    statuses: dict[int, Counter] = defaultdict(Counter)
    opcode_status = defaultdict(Counter)
    marker_missing_entities: set = set()
    for index, doc in enumerate(docs):
        uploads += 1
        meta = doc.get("meta") if isinstance(doc, dict) else None
        diag = clean((meta or {}).get("npc_diagnostics")) if isinstance(meta, dict) else None
        if not diag or not diag.get("epochs"):
            continue
        with_diag += 1
        upload_id = doc.get("id") or doc.get("meta", {}).get("title") or index
        for epoch in diag["epochs"]:
            epoch_id = (upload_id, epoch.get("epoch"))
            for rec in epoch.get("records", []):
                code = rec.get("mob_code")
                op = rec.get("opcode")
                status = rec.get("status")
                records[code] += 1
                per_code_logs[code].add(upload_id)
                per_code_epochs[code].add(epoch_id)
                opcodes[code][op] += 1
                statuses[code][status] += 1
                opcode_status[op][status] += 1
                if status == "type_marker_missing" or code == 0:
                    marker_missing_entities.add((upload_id, rec.get("entity")))
    codes = []
    for code in sorted(records, key=lambda c: (-len(per_code_logs[c]), -records[c], c)):
        decoded = statuses[code].get("type_decoded", 0)
        total = sum(statuses[code].values()) or 1
        info = npc_info(code) if code else {}
        name = info.get("name") if info else None
        codes.append({
            "mob_code": code,
            "name": name,
            "known": bool(info),
            "placeholder": bool(code) and (not info or _placeholder(name)),
            "logs": len(per_code_logs[code]),
            "epochs": len(per_code_epochs[code]),
            "records": records[code],
            "opcodes": dict(opcodes[code]),
            "statuses": dict(statuses[code]),
            "decoded_fraction": round(decoded / total, 3),
        })
    return {
        "uploads": uploads,
        "uploads_with_diagnostics": with_diag,
        "distinct_mob_codes": len([c for c in records if c]),
        "total_records": sum(records.values()),
        "codes": codes,
        "opcode_status": {op: dict(counter) for op, counter in sorted(opcode_status.items())},
        "marker_missing_observations": len(marker_missing_entities),
    }


def candidates(agg: dict, *, min_logs: int = 2, min_records: int = 5, min_decoded: float = 0.8) -> dict:
    """Split the aggregate's observed NPC types into promote / abstain groups.

    A ``mob_code`` is *promoted* as a stably observed NPC type only when it is
    non-zero, decoded consistently (``decoded_fraction >= min_decoded``) and seen
    across at least ``min_logs`` independent uploads with at least ``min_records``
    records. Promoted codes are bucketed by catalog state so the Ascension work
    is obvious: ``named`` (catalog already names it — a decoder confirmation),
    ``needs_name`` (observed and stable but the catalog name is a placeholder or
    the code is unknown — the real candidates to identify from source evidence).
    Everything else is returned under ``abstain`` with a reason; nothing is named
    that the catalog does not already name.
    """
    named, needs_name, abstain = [], [], []
    for c in agg.get("codes", []):
        if not c["mob_code"]:
            continue                                            # type-marker-missing bucket, not an NPC id
        promoted = c["logs"] >= min_logs and c["records"] >= min_records and c["decoded_fraction"] >= min_decoded
        if not promoted:
            reason = []
            if c["logs"] < min_logs:
                reason.append(f"seen in {c['logs']}/{min_logs} uploads")
            if c["records"] < min_records:
                reason.append(f"{c['records']}/{min_records} records")
            if c["decoded_fraction"] < min_decoded:
                reason.append(f"decoded {c['decoded_fraction']:.0%} < {min_decoded:.0%}")
            abstain.append({**c, "reason": "; ".join(reason)})
        elif c["known"] and not c["placeholder"]:
            named.append(c)
        else:
            needs_name.append(c)
    return {"thresholds": {"min_logs": min_logs, "min_records": min_records, "min_decoded": min_decoded},
            "named": named, "needs_name": needs_name, "abstain": abstain,
            "note": ("Promoted codes are seen across independent uploads with a consistent decode. "
                     "'needs_name' are stable observed NPC type IDs the bundled catalog cannot name "
                     "(placeholder or unknown) — candidates to identify from source evidence, not to guess. "
                     "'abstain' lack support yet and grow as more uploads arrive.")}


def variants(agg: dict) -> dict:
    """Identity / packet-variant evidence from the aggregate.

    Reports the decode-status mix per opcode (a low decoded rate on an opcode is
    a packet variant the decoder does not yet classify) and how many entity
    observations carried no type marker (``mob_code`` 0)."""
    rows = []
    for op, counts in agg.get("opcode_status", {}).items():
        total = sum(counts.values()) or 1
        rows.append({"opcode": op, "records": total, "statuses": counts,
                     "decoded_fraction": round(counts.get("type_decoded", 0) / total, 3)})
    rows.sort(key=lambda r: (-r["records"], r["opcode"]))
    return {"opcodes": rows, "marker_missing_observations": agg.get("marker_missing_observations", 0),
            "note": "Opcodes with a low decoded fraction, and marker-missing observations, are the identity/packet "
                    "variants the decoder cannot classify yet; they need verified protocol evidence, not guesses."}


def from_server(limit: int = 500, *, base_url: str | None = None, key: str | None = None, timeout: float = 30.0):
    """Fetch public/unlisted uploads from the configured log server for aggregation.

    Uses the project's configured default server unless ``base_url`` is given.
    Returns a list of full log documents (untrusted data). Network and parse
    errors are skipped per-log so a thin or partly unreachable corpus still
    yields what it can.
    """
    import json
    import urllib.request
    from .share import default_server
    base = (base_url or default_server().get("url") or "").rstrip("/")
    if not base:
        return []
    key = key or default_server().get("key")

    def _get(path):
        request = urllib.request.Request(base + path, headers={"User-Agent": "Aion2Calc", "Accept": "application/json",
                                                               **({"X-Upload-Key": key} if key else {})})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    try:
        listing = _get(f"/api/v1/logs?limit={int(limit)}")
    except Exception:
        return []
    rows = listing.get("logs", listing) if isinstance(listing, (dict, list)) else []
    docs = []
    for row in rows if isinstance(rows, list) else []:
        log_id = row.get("id") if isinstance(row, dict) else None
        if not log_id:
            continue
        try:
            docs.append(_get("/api/v1/logs/" + str(log_id)))
        except Exception:
            continue
    return docs
