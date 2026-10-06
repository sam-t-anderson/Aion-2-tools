"""Best-effort fresh official profile lookup, with exact identity checks."""
from __future__ import annotations

import time
from . import official


def lookup(player, region=None, deadline=None):
    if not isinstance(player,dict):
        return {"status":"unavailable", "reason":"Invalid character identity"}
    def check_deadline(*_):
        if deadline is not None and time.time()>deadline:
            raise TimeoutError("Upload-time lookup window expired")
    name = str(player.get("name") or "").strip()
    server = str(player.get("server") or "").strip()
    region = str(player.get("region") or region or "").lower()
    region = {"na":"nae","north america":"nae","europe":"eu","asia":"as","latin america":"la"}.get(region,region)
    base = {"source":"AION 2 official character service","requested_at":time.time(),"status":"unavailable"}
    if not name or "#" in name or len(name)>20 or not any(c.isalpha() for c in name):
        return {**base,"reason":"A character name was not recorded."}
    if not region and not server:
        return {**base,"reason":"Character region/server was not recorded; identity cannot be resolved safely."}
    try:
        server_id = int(server) if server else None
    except ValueError:
        return {**base,"reason":"A numeric character server ID is required."}
    try:
        if region not in official.REGIONS:
            regions = []
            for candidate in official.REGIONS:
                if any(str(s.get("serverId") or s.get("id"))==server for s in official.servers(candidate)):
                    regions.append(candidate)
            if len(regions)!=1:
                return {**base,"reason":"Official server metadata could not resolve a unique region."}
            region = regions[0]
        check_deadline()
        matches = official.search(name,region=region,server_id=server_id,size=100)
        matches = {m["character_id"]:m for m in matches if m["name"].casefold()==name.casefold()
                   and (server_id is None or str(m["server_id"])==str(server_id))}
        if len(matches)!=1:
            return {**base,"reason":"Official search did not identify exactly one matching character."}
        match = next(iter(matches.values()))
        ch = official.fetch_character(match["character_id"],int(match["server_id"]),region,details=True,use_cache=0,progress=check_deadline)
        check_deadline()
        profile = ch.get("profile") or {}
        if str(profile.get("characterName") or "").casefold()!=name.casefold() or str(profile.get("serverId"))!=str(match["server_id"]):
            return {**base,"reason":"Official profile identity did not match the recorded character."}
        cls = official.CLASS_KEYS.get(profile.get("className"))
        recorded_class = str(player.get("class") or "").lower()
        if recorded_class and cls and recorded_class!=cls:
            return {**base,"reason":"Official profile class did not match the recorded character."}
        partial = any(isinstance(v,dict) and "error" in v for field in ("items","daevanion_detail") for v in ch.get(field,{}).values())
        return {**base,"status":"partial" if partial else "ready","fetched_at":time.time(),
                "identity":{"name":match["name"],"server":str(match["server_id"]),"region":region,"character_id":match["character_id"]},
                "data":ch,"reason":"Some item/Daevanion details were unavailable." if partial else ""}
    except Exception:
        return {**base,"reason":"The official profile service was unavailable or its response could not be verified."}
