"""Descriptive encounter evidence; effects are never treated as cast records."""
from collections import defaultdict

LIMIT = 100
NOTE = ("Analysis describes retained evidence in this encounter, not cast starts or optimal play. "
        "Effects can include multi-hit attacks, periodic damage and pets. Equal timestamps do not establish order. "
        "Healing is recorded amount, not effective healing, overheal or shielding. Buff windows come from imports; "
        "live buff/cast/resource decoding is unavailable. HP milestones are samples, not named mechanics or exact phase transitions. "
        "Each section retains at most 100 rows per encounter; omitted counts are shown. Capture-quality limits still apply.")


def summarize(doc):
    """Recompute from normalized a2log fields, ignoring uploaded derived verdicts."""
    players = {p["id"] for p in doc.get("players", [])}
    segments = []
    for index, segment in enumerate(doc.get("segments", [])):
        duration = segment["duration"]
        events = segment.get("events") or [
            {"kind":"damage", "t":h["t"], "source":h.get("source") or h["player"],
             "target":h.get("target"), "skill":h.get("skill"), "skill_id":h.get("skill_id"), "amount":h["damage"]}
            for h in segment.get("hits", [])]
        entities = {e["id"]:e for e in segment.get("entities", [])}
        friendly = players | {key for key, e in entities.items() if e.get("owner") in players}
        healing, skills, opening = {}, {}, []
        opening_counts = defaultdict(int)
        omitted_opening = 0
        missing_heal_source = missing_heal_target = 0
        for event in sorted(events, key=lambda e:e["t"]):
            kind, source, target = event["kind"], event.get("source"), event.get("target")
            if kind not in ("damage", "heal"):
                continue
            if kind == "heal":
                missing_heal_source += int(not source)
                missing_heal_target += int(not target)
                if source and target:
                    row = healing.setdefault((source,target), {"source":source,"target":target,"amount":0,"effects":0})
                    row["amount"] += event["amount"]
                    row["effects"] += 1
            if source not in friendly:
                continue
            key = (source, kind, event.get("skill_id"), event.get("skill"))
            row = skills.setdefault(key, {"source":source,"kind":kind,"skill_id":event.get("skill_id"),
                "skill":event.get("skill"),"effects":0,"amount":0,"first":event["t"],"last":event["t"]})
            row["effects"] += 1
            row["amount"] += event["amount"]
            row["last"] = event["t"]
            if opening_counts[source] < 20:
                opening_counts[source] += 1
                if len(opening) < LIMIT:
                    opening.append(event)
                else:
                    omitted_opening += 1
        windows = defaultdict(list)
        buff_labels = {}
        invalid_windows = 0
        for buff in segment.get("buffs", []):
            start, end = max(0,buff["start"]), min(duration,buff["end"])
            if end <= start:
                invalid_windows += 1
                continue
            identity = ("id",buff["skill_id"]) if buff.get("skill_id") is not None else ("name",buff.get("name"))
            key = (buff["player"],identity)
            windows[key].append((start,end))
            buff_labels.setdefault(key, (buff.get("skill_id"),buff.get("name")))
        buffs = []
        for key, spans in windows.items():
            player = key[0]
            skill_id, name = buff_labels[key]
            merged = []
            for start,end in sorted(spans):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(end,merged[-1][1])
                else:
                    merged.append([start,end])
            seconds = sum(end-start for start,end in merged)
            buffs.append({"player":player,"skill_id":skill_id,"name":name,"seconds":seconds,
                          "uptime_pct":100*seconds/duration if duration > 0 else None,"windows":len(merged)})
        milestones, seen = [], set()
        for sample in sorted(segment.get("health", []), key=lambda h:h["t"]):
            entity = sample["entity"]
            maximum = sample.get("max",0)
            if not entities.get(entity,{}).get("is_boss") or maximum <= 0 or not 0 <= sample["current"] <= maximum:
                continue
            pct = 100*sample["current"]/maximum
            for threshold in (75,50,25,0):
                key = (entity,threshold)
                if pct <= threshold and key not in seen:
                    seen.add(key)
                    milestones.append({"entity":entity,"threshold_pct":threshold,"t":sample["t"],
                                       "observed_pct":pct,"current":sample["current"],"max":maximum})
        ordered = {"healing":sorted(healing.values(),key=lambda r:-r["amount"]),
                   "skills":sorted(skills.values(),key=lambda r:-r["amount"]),
                   "buffs":sorted(buffs,key=lambda r:-r["seconds"]),"milestones":milestones}
        segments.append({"segment":index, **{key:rows[:LIMIT] for key,rows in ordered.items()},
            "omitted":{key:max(0,len(rows)-LIMIT) for key,rows in ordered.items()},
            "opening":opening,"omitted_opening":omitted_opening,"invalid_buff_windows":invalid_windows,
            "healing_without_source":missing_heal_source,"healing_without_target":missing_heal_target})
    return {"note":NOTE,"segments":segments}
