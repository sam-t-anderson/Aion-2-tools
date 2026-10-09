"""Bounded, public-safe numeric NPC decoder evidence; never raw packet capture."""


def integer(value, maximum=2**53-1):
    return type(value) is int and 0 <= value <= maximum


def clean(value):
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("epochs"), list):
        return None
    epochs = []
    for epoch in value["epochs"][-32:]:
        if not isinstance(epoch, dict) or not integer(epoch.get("epoch")):
            continue
        records = []
        source = epoch.get("records")
        for row in source[-128:] if isinstance(source, list) else []:
            if (not isinstance(row, dict) or row.get("status") not in ("type_decoded", "type_marker_missing")
                    or row.get("opcode") not in (64, 65)
                    or not all(integer(row.get(k), limit) for k, limit in
                               (("entity", 9999999), ("mob_code", 16777215), ("timestamp_ms", 2**53-1)))):
                continue
            records.append({k: row[k] for k in ("entity", "opcode", "mob_code", "timestamp_ms", "status")})
        epochs.append({"epoch": epoch["epoch"], "records": records,
                       **{k: epoch[k] for k in ("scan_calls", "omitted", "candidates_seen") if integer(epoch.get(k))}})
    return {"version": 1, "epochs": epochs,
            "omitted_epochs": value["omitted_epochs"] if integer(value.get("omitted_epochs")) else 0}
