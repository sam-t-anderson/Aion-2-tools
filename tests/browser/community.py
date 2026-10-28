"""A stand-in log server for the browser tests. The app under test is pointed at it (its saved log-server
settings), so no test reaches a real server, and the pages show made-up fights the tests know.

It answers the routes the app's pages read through the app (``/api/community``, ``/api/plans``) with these
fights, raid plans and field-boss kills, and empty but well-formed answers otherwise; anything posted
(heartbeats, diagnostics) is accepted. Paths it does not know answer 404 and are listed in ``unknown``, so a
test can name a route the pages start using."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOG_ID = "TestLog001"
NOW = 1793000000.0
PLAYERS = [{"id": "p1", "name": "Testsorc", "class": "sorcerer"}, {"id": "p2", "name": "Testcleric", "class": "cleric"}]
FIGHTS = [  # (segment, boss, role, seconds)
    (2, "Gatekeeper Testlord", "final", 95.0),
    (1, "Watcher Testling", "mini", 40.0),
]
# Published raid plans, each bound to a boss (the Raid Planner's browse view).
PLANS = [
    {"id": "TestPlan01", "name": "Testlord tank swap", "boss": "Gatekeeper Testlord", "npc_id": 2390001, "author": "Testsorc",
     "duration": 180.0, "tokens": 6, "classes": ["sorcerer", "cleric"], "has_fight": True},
    {"id": "TestPlan02", "name": "Testling cleave", "boss": "Watcher Testling", "npc_id": 2390002, "author": "Testcleric",
     "duration": 60.0, "tokens": 2, "classes": ["templar"], "has_fight": False},
]
# The highest point totals reported for a class (Highest observed build points; My Character offers them).
PROGRESSION = [{"class_name": "sorcerer", "skill": 130, "stigma": 25, "daevanion": 300, "region": "nae"}]
# Field-boss kills on one server (2102, Zikel): one in an Asmodian zone (map 1100), one in an Elyos zone (map 1000).
KILLS = [
    {"server": 2102, "server_name": "Zikel", "boss": "Testboss Alpha", "map_id": 1100, "killed_at": NOW - 600, "reports": 2},
    {"server": 2102, "server_name": "Zikel", "boss": "Testboss Beta", "map_id": 1000, "killed_at": NOW - 900, "reports": 1},
]


# A featured encounter (log server 0.2.145): two phases, a legion that cleared it and a party still on the mini boss.
FEATURED_ID = "fe_0123456789"
ROLES = {"gladiator": "tank", "templar": "tank", "cleric": "support", "chanter": "support", "assassin": "dps", "ranger": "dps",
         "sorcerer": "dps", "spiritmaster": "dps"}
_LEGION = {"key": "legion:t1", "kind": "legion", "name": "Testers", "server": "2102", "members": [], "region": "nae"}
_PARTY = {"key": "party:t2", "kind": "party", "name": "Testsorc's party", "server": "2102", "region": "nae",
          "members": [{"name": p["name"], "class": p["class"], "server": "2102"} for p in PLAYERS]}
_PHASES = [{"boss_key": "npc:2390002", "boss": FIGHTS[1][1], "icon": ""}, {"boss_key": "npc:2390001", "boss": FIGHTS[0][1], "icon": ""}]
FEATURED = {"id": FEATURED_ID, "title": "Testlord race", "boss": FIGHTS[0][1], "boss_key": "npc:2390001", "difficulty": "Normal",
            "encounter_type": "dungeon", "instance_id": 600999, "starts_at": NOW - 86400, "ends_at": None, "icon": "", "phases": _PHASES}
_TEAMS = [{"rank": 1, "team": _LEGION, "killed": 2, "phases": 2, "complete": True, "best_hp": None, "next_phase": None,
           "first_kill_at": NOW - 3600, "progress_at": NOW - 3600, "position": 1.0, "pulls": 5, "final_pulls": 3, "log": LOG_ID},
          {"rank": 2, "team": _PARTY, "killed": 0, "phases": 2, "complete": False, "best_hp": 35.5, "next_phase": 0,
           "first_kill_at": None, "progress_at": NOW - 1800, "position": 0.3225, "pulls": 2, "final_pulls": 0, "log": LOG_ID}]
_RATES = {"dps": [{"class": "sorcerer", "role": "dps", "count": 3, "p25": 12000.0, "median": 15000.0, "p75": 16000.0, "p95": 17000.0,
                   "max": 17500.0}],
          "tank": [],
          "support": [{"class": "cleric", "role": "support", "count": 2, "p25": 4000.0, "median": 5000.0, "p75": 5500.0, "p95": 5900.0,
                       "max": 6000.0}]}
_SUMMARY = {"progress": _TEAMS, "speed": [{"team": _LEGION, "elapsed": 754.0, "log": LOG_ID, "at": NOW - 3600}],
            "execution": [{"team": _LEGION, "log": LOG_ID, "at": NOW - 3600, "seconds": 95.0, "deaths": 1}],
            "all_stars": {"dps": [{"name": "Testsorc", "class": "sorcerer", "server": "2102", "points": 187.5, "bosses": 2}], "tank": [],
                          "support": [{"name": "Testcleric", "class": "cleric", "server": "2102", "points": 120.0, "bosses": 2}]},
            "classes": _RATES, "teams": 2, "complete": 1, "pulls": 7}
_FEATURED_NOTE = "Built from the public uploads."
_REGIONS = ["kr", "nae"]


def _race(q: dict) -> dict:
    return {"featured": FEATURED, "region": None, "regions": _REGIONS, "total": len(_TEAMS), "teams": _TEAMS, "note": _FEATURED_NOTE,
            "phases": [{**_PHASES[0], "teams": 2, "killed_by": 1, "first_kill": {"team": _LEGION, "at": NOW - 4200}},
                       {**_PHASES[1], "teams": 1, "killed_by": 1, "first_kill": {"team": _LEGION, "at": NOW - 3600}}]}


def _progress(q: dict) -> dict:
    return {"featured": FEATURED, "region": None, "regions": _REGIONS, "page": int(q.get("page", ["1"])[0]), "total": len(_TEAMS),
            "note": _FEATURED_NOTE,
            "progress": [{**t, "killed_bosses": [0, 1] if t["complete"] else []} for t in _TEAMS],
            "kills": [{"rank": 1, "team": _LEGION, "log": LOG_ID, "at": NOW - 3600, "seconds": 95.0, "patch": "version:product:2.0.8.0",
                       "composition": {"cleric": 1, "sorcerer": 1}, "deaths": 1}]}


def _rankings(q: dict) -> dict:
    if q.get("metric", ["dps"])[0] == "speed":
        return {"featured": FEATURED, "metric": "speed", "boss_key": FEATURED["boss_key"], "regions": _REGIONS, "note": _FEATURED_NOTE,
                "entries": [{"rank": 1, "team": _LEGION, "elapsed": 754.0, "log": LOG_ID, "at": NOW - 3600,
                             "patch": "version:product:2.0.8.0"}]}
    boss, wanted = q.get("boss", [FEATURED["boss_key"]])[0], q.get("class", [""])[0]
    rows = [{"log": LOG_ID, "segment": 2 if boss == FEATURED["boss_key"] else 1, "name": p["name"], "class": p["class"], "server": "2102",
             "score": 15000.0 - 5000 * i, "parse": 90.0 - 30 * i, "duration": 95.0, "created_at": NOW} for i, p in enumerate(PLAYERS)]
    return {"featured": FEATURED, "boss_key": boss, "regions": _REGIONS, "entries": [r for r in rows if not wanted or r["class"] == wanted]}


def _statistics(q: dict) -> dict:
    return {"featured": FEATURED, "boss_key": q.get("boss", [FEATURED["boss_key"]])[0], "metric": q.get("metric", ["dps"])[0],
            "region": None, "regions": _REGIONS, "classes": [*_RATES["dps"], *_RATES["support"]], "truncated": False, "roles": ROLES,
            "note": "Recorded rates of the public uploads."}


def _log_row() -> dict:
    return {"id": LOG_ID, "created_at": NOW, "title": "Test run", "region": "nae", "source": "Aion 2 Calc live session",
            "uploader": "Testsorc", "boss": FIGHTS[0][1], "duration": 160.0, "players": PLAYERS, "top_dps": 15000.0,
            "segments": 3, "event_count": 500, "bosses": [], "opponent_classes": [], "shared_uploads": 1, "combat_mode": "pve",
            "contexts": [{"segment": seg, "boss": boss, "boss_role": role, "duration": secs, "difficulty": "Normal",
                          "party_size": 2, "encounter_type": "dungeon", "start": NOW - 100 * seg,
                          "game_patch": "version:product:2.0.8.0", "players": PLAYERS} for seg, boss, role, secs in FIGHTS]}


def _raw_log() -> dict:
    """The fights themselves, as an a2log document (what the review page opens)."""
    segments = []
    for seg in range(3):
        fight = next((f for f in FIGHTS if f[0] == seg), None)
        boss, secs = (fight[1], fight[3]) if fight else ("Combat 1", 25.0)
        hits = [{"t": float(t), "player": "p1" if t % 2 else "p2", "skill": "Flame Arrow" if t % 2 else "Earth's Wrath",
                 "damage": 1500.0} for t in range(int(secs))]
        segments.append({"label": boss, "boss": boss, "duration": secs, "killed": True, "encounter_type": "dungeon",
                         "hits": hits})
    # The final boss fight's movement (0.2.350): Testcleric moves; Testsorc, who recorded it, is placed only by
    # the effects they apply.
    segments[2].update(ping_recorder="p1", movement=sorted(
        [{"t": float(t), "entity": "p2", "x": 1000.0 + 10 * t, "y": 900.0, "z": 50.0, "src": "move"} for t in range(0, 90, 2)]
        + [{"t": float(t), "entity": "p1", "x": 1200.0, "y": 950.0 + 5 * t, "z": 50.0, "src": "applied"} for t in range(0, 90, 10)],
        key=lambda m: m["t"]))
    return {"format": "a2log", "version": 1, "meta": {"title": "Test run", "uploader": {"name": "Testsorc", "verified": False}},
            "players": PLAYERS, "segments": segments}


def _merged_movement(q: dict) -> dict:
    """A fight's movement merged with Testcleric's recording of it (log server 0.2.144). In the final boss fight
    Testsorc's own path comes from there; the mini boss fight, recorded here without movement, has only theirs."""
    segment = int(q.get("segment", ["0"])[0])
    theirs = {"log": "TestLog002", "segment": 0, "title": "Their run", "uploader": "Testcleric", "shared_hits": 40, "offset": -3.0}
    if segment == 1:
        rows = [{"t": float(t), "entity": ref, "x": 500.0 + 6 * t + 40 * i, "y": 700.0, "z": 50.0, "src": "move", "via": 1}
                for t in range(0, 40, 2) for i, ref in enumerate(("p1", "p2"))]
    else:
        rows = [m for m in _raw_log()["segments"][2]["movement"] if m["entity"] == "p2"]
        rows += [{"t": float(t), "entity": "p1", "x": 1200.0 + 4 * t, "y": 950.0, "z": 50.0, "src": "move", "via": 1} for t in range(1, 90, 2)]
    return {"segment": segment, "movement": sorted(rows, key=lambda m: m["t"]), "note": "Merged from public recordings of the same fight.",
            "sources": [{"log": LOG_ID, "segment": segment, "title": "Test run", "uploader": "Testsorc"},
                        {**theirs, "positions": sum(1 for m in rows if m.get("via"))}]}


def _plans(q: dict) -> dict:
    npc = q.get("npc", [""])[0]
    return {"plans": [plan for plan in PLANS if not npc or str(plan["npc_id"]) == npc]}


def _plan(plan: dict) -> dict:
    """A published plan itself, as an a2plan document."""
    return {"format": "a2plan", "version": 1, "meta": {"name": plan["name"]}, "duration": plan["duration"], "tokens": [],
            "encounter": {"boss": plan["boss"], "npc_id": plan["npc_id"]}}


# A run as /api/v1/run-leaderboard sends it: the route by catalog key, each boss named in its attempts, and the
# ranked entry-to-final-boss time in elapsed_seconds.
SPEED_RUN = {"log": LOG_ID, "id": "1", "rank": 1, "count": 2, "boss_route": ["npc:2340616", "npc:2340617"],
             "elapsed_seconds": 150.5, "party_size": 5, "encounter_type": "transcendence", "difficulty": "stage 2",
             "instance_id": 600055, "attempts": [{"boss": "Gelcos", "boss_key": "npc:2340616", "outcome": "kill"}],
             "progression": [{"boss": "Gelcos", "boss_key": "npc:2340616", "kills": 1},
                             {"boss": "Ereshkigal", "boss_key": "npc:2340617", "kills": 1}]}


ANSWERS = {
    "/api/v1/report-facets": lambda q: {"game_patch": ["version:product:2.0.8.0"], "boss": [f[1] for f in FIGHTS],
                                        "difficulty": ["Normal"], "encounter_type": ["dungeon"], "region": ["nae"],
                                        "latest_submitted_patch": "version:product:2.0.8.0", "party_size": [2],
                                        "boss_roles": {f[1]: f[2] for f in FIGHTS}},
    "/api/v1/logs": lambda q: {"logs": [_log_row()] if q.get("page", ["1"])[0] == "1" else [], "total": 1,
                               "page": int(q.get("page", ["1"])[0]), "limit": int(q.get("limit", ["50"])[0])},
    f"/api/v1/logs/{LOG_ID}/raw": lambda q: _raw_log(),
    f"/api/v1/logs/{LOG_ID}/parts": lambda q: {"parts": []},
    f"/api/v1/logs/{LOG_ID}/rankings": lambda q: {"segments": {}},
    f"/api/v1/logs/{LOG_ID}/movement": _merged_movement,
    "/api/v1/run-leaderboard": lambda q: {"entries": [SPEED_RUN], "samples": 1, "truncated": False, "note": ""},
    "/api/v1/encounter-progression": lambda q: {"groups": [], "truncated": False, "note": ""},
    "/api/v1/progression": lambda q: {"observations": [o for o in PROGRESSION if q.get("class", [o["class_name"]])[0] == o["class_name"]],
                                      "note": ""},
    "/api/v1/performance": lambda q: {"groups": [], "metric": "dps", "samples": 0, "excluded_unknown_metadata": 0,
                                      "excluded_unranked_encounter_uploads": 0, "truncated": False, "note": ""},
    "/api/v1/records": lambda q: {"records": [], "total": 0},
    "/api/v1/boss-status": lambda q: {"groups": [], "truncated": False, "generated_at": time.time(), "history_limit": 20, "note": ""},
    "/api/v1/boss-kills": lambda q: {"kills": KILLS, "truncated": False, "generated_at": NOW, "window_seconds": 172800,
                                     "merge_seconds": 600, "note": ""},
    "/api/v1/plans": _plans,
    "/api/v1/plans/bosses": lambda q: {"bosses": [{"npc_id": plan["npc_id"], "boss": plan["boss"], "plans": 1} for plan in PLANS]},
    **{f"/api/v1/plans/{plan['id']}/raw": (lambda q, plan=plan: _plan(plan)) for plan in PLANS},
    "/api/v1/npc-portraits": lambda q: {"version": 1, "status": "ok", "disputed": False, "generated_at": "", "sources": [],
                                        "note": "", "count": 0, "retrieved_at": "", "portraits": {}},
    "/api/v1/news": lambda q: {"entries": [{"id": "n1", "title": "Test patch notes", "category": "Notice", "region": "global",
                                            "preview": "What changed in the test patch.", "image": "", "published_at": "2026-10-20",
                                            "published_epoch": NOW, "publisher": "Test publisher",
                                            "url": "https://news.example/1", "retrieved_at": NOW}],
                               "status": "ready", "fetched_at": NOW, "unavailable_sources": [], "note": "",
                               "region": q.get("region", ["global"])[0], "region_label": "Global",
                               "regions": [{"id": "global", "label": "Global"}, {"id": "kr", "label": "Korea"}],
                               "sources": ["test"]},
    "/api/v1/featured": lambda q: {"featured": [{**FEATURED, "summary": _SUMMARY}], "roles": ROLES, "note": _FEATURED_NOTE},
    f"/api/v1/featured/{FEATURED_ID}": lambda q: {**FEATURED, "summary": _SUMMARY, "roles": ROLES, "note": _FEATURED_NOTE},
    f"/api/v1/featured/{FEATURED_ID}/race": _race,
    f"/api/v1/featured/{FEATURED_ID}/progress": _progress,
    f"/api/v1/featured/{FEATURED_ID}/reports": lambda q: {"featured": FEATURED, "logs": [_log_row()], "total": 1, "page": 1, "limit": 30},
    f"/api/v1/featured/{FEATURED_ID}/rankings": _rankings,
    f"/api/v1/featured/{FEATURED_ID}/statistics": _statistics,
    "/.well-known/a2log.json": lambda q: {"format": "a2log", "canonical_presets_version": 1},
    "/api/v1/account/config": lambda q: {"methods": {"app": True, "passkey": False, "discord": False}, "origins": [],
                                         "note": ""},
}


class Community:
    def __init__(self):
        self.unknown, self.requests = [], []
        community = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                url = urlparse(self.path)
                community.requests.append(("GET", self.path))
                answer = ANSWERS.get(url.path)
                if answer is None:
                    community.unknown.append(self.path)
                    return self.reply(404, {"error": "not served by the test server"})
                self.reply(200, answer(parse_qs(url.query)))

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                community.requests.append(("POST", self.path))
                self.reply(200, {"ok": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def reached(self, page, prefix: str, since: int = 0, timeout_ms: int = 10000) -> bool:
        """Whether a GET for a path starting with `prefix` reaches this server (after its first `since` requests)
        within the time. The page keeps running meanwhile: a page asks as it draws, and on a slow computer it can
        still be asking after the part a test waited for is drawn."""
        from apphelpers import until
        return until(page, lambda: any(method == "GET" and path.startswith(prefix) for method, path in self.requests[since:]),
                     timeout_ms)

    def close(self):
        self.server.shutdown()
