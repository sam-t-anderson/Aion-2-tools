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
    return {"format": "a2log", "version": 1, "meta": {"title": "Test run", "uploader": {"name": "Testsorc", "verified": False}},
            "players": PLAYERS, "segments": segments}


def _plans(q: dict) -> dict:
    npc = q.get("npc", [""])[0]
    return {"plans": [plan for plan in PLANS if not npc or str(plan["npc_id"]) == npc]}


def _plan(plan: dict) -> dict:
    """A published plan itself, as an a2plan document."""
    return {"format": "a2plan", "version": 1, "meta": {"name": plan["name"]}, "duration": plan["duration"], "tokens": [],
            "encounter": {"boss": plan["boss"], "npc_id": plan["npc_id"]}}


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
    "/api/v1/run-leaderboard": lambda q: {"entries": [], "samples": 0, "truncated": False, "note": ""},
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
    "/.well-known/a2log.json": lambda q: {"format": "a2log", "canonical_presets_version": 1},
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

    def close(self):
        self.server.shutdown()
