"""Bounded descriptive review of explicitly linked recording parts.

No source mutation, content deduplication, inferred entry or ranking upgrade.
"""
from copy import deepcopy
import hashlib
import json
import re

from .archive import clean_continuity
from .runs import stamp

MAX_PARTS = 32
MAX_BYTES = 64 * 1024 * 1024
NOTE = ("Combined review of submitted recording parts. Source encounters and run boundaries remain separate. "
        "Counters do not establish loss-free capture; entry, completion and rankings are not inherited. "
        "Open a source part for its original profile and capture evidence.")


def part_range(first, last):
    if (type(first) is not int or type(last) is not int
            or not 1 <= first <= last <= 2**53-1 or not 2 <= last-first+1 <= MAX_PARTS):
        raise ValueError(f"Choose between 2 and {MAX_PARTS} consecutive recording parts")
    return range(first, last+1)


def clean_manifest(value):
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        return None
    rows = value.get("sources")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_PARTS:
        return None
    sources = []
    for row in rows:
        if (not isinstance(row, dict) or type(row.get("part")) is not int
                or not 1 <= row["part"] <= 2**53-1
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", "")))):
            return None
        source = {"part":row["part"], "sha256":row["sha256"]}
        for key in ("id", "file", "title", "capture_scope"):
            if isinstance(row.get(key), str):
                source[key] = row[key][:200]
        for key in ("first_sequence", "last_sequence", "first_epoch", "last_epoch"):
            if type(row.get(key)) is int and 0 <= row[key] <= 2**53-1:
                source[key] = row[key]
        sources.append(source)
    return {"version":1, "sources":sources, "note":NOTE}


def combine(sources):
    """sources are (bounded public/local descriptor, raw document) pairs."""
    from .a2log import validate, LIMITS
    from .quality import COUNTERS
    if not 2 <= len(sources) <= MAX_PARTS:
        raise ValueError(f"Choose between 2 and {MAX_PARTS} recording parts")
    loaded, byte_count = [], 0
    for source, raw in sources:
        byte_count += len(json.dumps(raw, separators=(",", ":"), allow_nan=False).encode())
        if byte_count > MAX_BYTES:
            raise ValueError("Combined review exceeds 64 MiB; choose a shorter part range")
        doc = validate(raw)
        meta = doc["meta"]
        archive = meta.get("archive") or {}
        c = clean_continuity(archive.get("continuity"))
        if not c or c["retained_records"] != c["last_sequence"]-c["first_sequence"]+1:
            raise ValueError("A selected part has missing or incomplete retained-record evidence")
        if meta.get("capture_active") or meta.get("capture_quality", {}).get("reconstructed"):
            raise ValueError("Stop the recording first; active checkpoints and combined reviews cannot be combined")
        if meta.get("capture_scope") not in ("self", "party", "all"):
            raise ValueError("Capture scope was not recorded for a selected part")
        if c.get("first_epoch") is None:
            raise ValueError("Capture/identity context ranges were not recorded")
        loaded.append((source, doc, archive, c))
    loaded.sort(key=lambda row:row[2]["part"])
    first, last = loaded[0][2]["part"], loaded[-1][2]["part"]
    expected = list(part_range(first, last))
    if [a["part"] for _, _, a, _ in loaded] != expected:
        raise ValueError("Recording part numbers have a gap or duplicate; choose an unambiguous consecutive range")
    archive_id = loaded[0][2].get("id")
    if not archive_id or any(a.get("id") != archive_id for _, _, a, _ in loaded):
        raise ValueError("Selected parts do not belong to the same submitted recording")
    scopes = {d["meta"]["capture_scope"] for _, d, _, _ in loaded}
    if len(scopes) != 1:
        raise ValueError("Capture scopes differ; combining them would mix different effect selections")
    tokens = [c["token"] for _, _, _, c in loaded]
    if len(set(tokens)) != len(tokens):
        raise ValueError("Recording part tokens are duplicated")
    previous, last_end = None, None
    for _, doc, archive, c in loaded:
        if previous:
            parent, prior = previous
            if (not parent.get("closed") or c.get("previous_token") != prior["token"]
                    or c.get("previous_last_sequence") != prior["last_sequence"]
                    or c["first_sequence"] != prior["last_sequence"]+1):
                raise ValueError("Retained-record chain has a gap, overlap, open predecessor or conflicting link")
            if c["first_epoch"] < prior["last_epoch"]:
                raise ValueError("Capture/identity context ranges move backwards")
        for segment in doc["segments"]:
            start = stamp(segment.get("start"))
            if start is None or last_end is not None and start < last_end-0.001:
                raise ValueError("Encounter timestamps are missing, overlapping or out of order")
            if any(e.get("t", 0) > segment["duration"] for key in ("hits", "events", "health", "positions") for e in segment.get(key, [])):
                raise ValueError("Recorded effects extend beyond an encounter boundary")
            last_end = start+segment["duration"]
        previous = archive, c

    players, stable, segments, provenance = [], {}, [], []
    for source, doc, archive, c in loaded:
        prefix = f"part{archive['part']}:"
        refs = {}
        for player in doc["players"]:
            region = player.get("region") or doc["meta"].get("region")
            server, character = player.get("server"), player.get("character_id")
            identity = ((region.lower(), str(int(server)), str(int(character))) if region and region.lower() != "unknown"
                        and str(server or "").isdigit() and int(server) > 0
                        and str(character or "").isdigit() and int(character) > 0 else None)
            existing = stable.get(identity) if identity else None
            if existing:
                if existing.get("class") != player.get("class"):
                    raise ValueError("Stable character identity has conflicting classes")
                refs[player["id"]] = existing["id"]
                # The combined character is not a new encounter-time snapshot.
                for key in ("profile_snapshot", "gear_score", "combat_power", "stats", "specs"):
                    if existing.get(key) != player.get(key):
                        existing.pop(key, None)
                existing["profile_snapshot"] = {"status":"unavailable", "reason":"Combined recording: open a source part for its original profile snapshot."}
            else:
                row = deepcopy(player)
                row["id"] = prefix+player["id"]
                if region:
                    row["region"] = region
                refs[player["id"]] = row["id"]
                players.append(row)
                if identity:
                    stable[identity] = row
        if len(players) > LIMITS["players"]:
            raise ValueError("Combined review exceeds 64 player identities; choose a shorter range")
        for original in doc["segments"]:
            segment = deepcopy(original)
            if any(e["id"] in {p["id"] for p in doc["players"]} for e in segment.get("entities", [])):
                raise ValueError("Player and entity references collide in a source encounter")
            for entity in segment.get("entities", []):
                refs[entity["id"]] = prefix+entity["id"]
            def ref(value):
                return refs.get(value, prefix+value) if isinstance(value, str) else value
            for entity in segment.get("entities", []):
                entity["id"] = ref(entity["id"])
                if entity.get("owner"):
                    entity["owner"] = ref(entity["owner"])
            for key, fields in (("hits", ("player", "source", "target", "pet")), ("events", ("source", "target")),
                                ("buffs", ("player",)), ("health", ("entity",)), ("positions", ("entity",))):
                for event in segment.get(key, []):
                    for field in fields:
                        if field in event:
                            event[field] = ref(event[field])
            segment["party_members"] = [ref(p) for p in segment.get("party_members", [])]
            segment["id"] = prefix+str(segment.get("id", len(segments)))
            segment["run_id"] = prefix+str(segment.get("run_id", "legacy"))
            segment["label"] = f"Part {archive['part']} · " + (segment.get("label") or "Combat")
            for key in ("game_patch", "game_patch_source", "game_patch_basis", "difficulty", "encounter_type", "zone"):
                if not segment.get(key) and doc["meta"].get(key):
                    segment[key] = doc["meta"][key]
            segments.append(segment)
        provenance.append({**{k:source[k] for k in ("id", "file") if k in source}, "part":archive["part"],
            "title":doc["meta"].get("title") or "Saved recording", "capture_scope":doc["meta"]["capture_scope"],
            **{k:c[k] for k in ("first_sequence", "last_sequence", "first_epoch", "last_epoch")},
            "sha256":hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()})
    if len(segments) > LIMITS["segments"]:
        raise ValueError("Combined review exceeds 200 encounters; choose a shorter range")
    for key, limit in (("hits", LIMITS["hits"]), ("events", LIMITS["hits"]), ("health", LIMITS["hp"]), ("positions", LIMITS["hp"])):
        if sum(len(s.get(key, [])) for s in segments) > limit:
            raise ValueError(f"Combined {key} exceeds review limits; choose a shorter range")
    captures = [d["meta"].get("capture_quality", {}) for _, d, _, _ in loaded]
    evidence = {k:max(c.get(k, 0) for c in captures) for k in (*COUNTERS, "tcp_pending_bytes")}
    evidence.update(reconstructed=True, storage_boundary=True,
                    transport_monitored=all(c.get("transport_monitored") is True for c in captures))
    meta = {"source":"Aion 2 Calc combined recording review", "title":f"Recording parts {first}–{last}",
            "capture_scope":next(iter(scopes)), "capture_quality":evidence, "contribute":"no",
            "reconstruction":{"version":1, "sources":provenance}}
    for key in ("region", "game_patch", "installed_build", "installed_build_namespace", "installed_build_cohort", "installed_build_source"):
        values = {d["meta"].get(key) for _, d, _, _ in loaded}
        if len(values) == 1 and next(iter(values)):
            meta[key] = next(iter(values))
    return validate({"format":"a2log", "version":1, "meta":meta, "players":players, "segments":segments})


def summarize(doc):
    from .a2log import combat_mode
    result = {}
    for mode in ("all", "pve", "pvp"):
        segments = [s for s in doc["segments"] if mode == "all" or combat_mode(doc, s) == mode]
        rows = {p["id"]:{"id":p["id"], "name":p["name"], "server":p.get("server"), "class":p.get("class"),
                          "damage":0, "healing":0, "taken":0} for p in doc["players"]}
        active, recorded = 0, 0
        for segment in segments:
            owners = {e["id"]:e.get("owner") for e in segment.get("entities", []) if e.get("owner")}
            def root(actor):
                seen = set()
                while actor in owners and actor not in seen:
                    seen.add(actor)
                    actor = owners[actor]
                return actor if actor not in seen else None
            hits = segment.get("hits", [])
            first = min((h["t"] for h in hits), default=0)
            active += max(1,len({int(max(0,h["t"]-first)) for h in hits})) if hits else 0
            recorded += max(1,segment["duration"])
            for h in hits:
                rows[h["player"]]["damage"] += h["damage"]
            for event in segment.get("events", []):
                source, target = root(event.get("source")), root(event.get("target"))
                if event["kind"] == "heal" and source in rows:
                    rows[source]["healing"] += event.get("amount", 0)
                elif event["kind"] == "damage" and target in rows and source not in rows:
                    rows[target]["taken"] += event.get("amount", 0)
        for row in rows.values():
            row.update(dps=row["damage"]/max(1,active), hps=row["healing"]/max(1,recorded), dtps=row["taken"]/max(1,recorded))
        result[mode] = {"encounters":len(segments), "active_seconds":active, "recorded_seconds":recorded,
                        "players":sorted((r for r in rows.values() if r["damage"] or r["healing"] or r["taken"]), key=lambda r:-r["damage"])}
    return result


def clean_run(value):
    if (not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1
            or not re.fullmatch(r"[0-9a-f]{32}", str(value.get("token", "")))
            or type(value.get("origin_sequence")) is not int or not 1 <= value["origin_sequence"] <= 2**53-1):
        return None
    result = {k:value[k] for k in ("version", "token", "origin_sequence")}
    for key in ("entry_at", "finished_at"):
        if isinstance(value.get(key),str) and len(value[key]) <= 100 and stamp(value[key]) is not None:
            result[key] = value[key]
    if type(value.get("final_boss_id")) is int and 1 <= value["final_boss_id"] <= 2**32-1:
        result["final_boss_id"] = value["final_boss_id"]
    return result


def run_summary(doc):
    from ..meter.a2parser.lookup import npc_info
    sources = doc["meta"]["reconstruction"]["sources"]
    first_seq, last_seq = sources[0].get("first_sequence"), sources[-1].get("last_sequence")
    groups, legacy = {}, 0
    for segment in doc["segments"]:
        ledger = clean_run(segment.get("recording_run"))
        if not ledger:
            legacy += 1
            continue
        groups.setdefault((ledger["token"], combat_mode(doc, segment)), []).append((segment, ledger))
    rows = []
    for (token, mode), selected in groups.items():
        segments = [s for s, _ in selected]
        ledger = [r for _, r in selected]
        contexts = {(s.get("map_id"), s.get("instance_id"), s.get("game_patch"), s.get("difficulty"), s.get("encounter_type")) for s in segments}
        origins = {r["origin_sequence"] for r in ledger}
        entries = {r.get("entry_at") for r in ledger if r.get("entry_at")}
        finishes = {(r.get("finished_at"), r.get("final_boss_id")) for r in ledger if r.get("finished_at")}
        times = [(stamp(s.get("start")), s["duration"]) for s in segments]
        if any(t is None for t, _ in times):
            rows.append({"token":token, "encounters":len(segments), "recorded_span":None, "entry_to_finish":None,
                         "status":"Run timestamps are missing", "eligible":False, "mode":mode})
            continue
        earliest = min(t for t, _ in times)
        latest = max(t+duration for t, duration in times)
        reasons = []
        if len(contexts) != 1 or len(origins) != 1 or len(entries) > 1 or len(finishes) > 1:
            reasons.append("Conflicting run provenance or encounter context")
        origin = next(iter(origins)) if len(origins) == 1 else None
        entry = stamp(next(iter(entries))) if len(entries) == 1 else None
        if not (origin is not None and first_seq is not None and last_seq is not None and first_seq <= origin <= last_seq and entry is not None and entry <= earliest):
            entry = None
            reasons.append("Run entry is outside the selected range or was not observed")
        finish, code = next(iter(finishes)) if len(finishes) == 1 else (None, None)
        ended = stamp(finish)
        observed = False
        if code:
            info = npc_info(code)
            for segment, r in selected:
                if r.get("finished_at") != finish or not info.get("isBoss") or not segment.get("instance_id") or info.get("dungeonId") != segment["instance_id"]:
                    continue
                bosses = {e["id"] for e in segment.get("entities", []) if e.get("mob_code") == code}
                observed |= any(e["kind"] == "death" and e.get("target") in bosses
                    and ended is not None and abs(stamp(segment["start"])+e["t"]-ended) <= 0.001 for e in segment.get("events", []))
        if not observed or ended is None or ended < latest-0.001:
            ended = None
            reasons.append("Configured final-boss death is unavailable or conflicts with run timing")
        elapsed = ended-entry if entry is not None and ended is not None and not reasons else None
        rows.append({"token":token, "encounters":len(segments), "recorded_span":latest-earliest,
                     "entry_at":entry, "finished_at":ended, "entry_to_finish":elapsed,
                     "status":"Submitted entry and final-boss evidence connect" if elapsed is not None else "; ".join(reasons),
                     "eligible":False, "mode":mode})
    return {"runs":rows, "legacy_encounters":legacy,
            "note":"Run tokens and timing are submitted evidence. Combined runs remain unranked; source fights and quality are unchanged."}
