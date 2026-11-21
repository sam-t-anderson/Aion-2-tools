"""The native Combat Logs page, part 1 (0.2.450): its views and lists, and Saved Logs (a fight analyzed from a link or a
file with its progress, the logs folder, the log server shared to, the encounters analyzed), as pages/combat.js shows
them; since 0.2.451 Saved Logs' recorded encounters by type (saved-logs.js) and its upload queue (archive-upload.js);
since 0.2.452 My Uploads (log-ownership.js) and My Character Identities (identity.js); since 0.2.453 the community's
views (logs-view.js); since 0.2.454 Personal records (community.js); since 0.2.455 the featured encounters (featured.js).
Off screen over a fake app answering as the app does, a fake share server and a fake log server behind the app's
community proxy (made-up logs, recordings, credentials, characters, teams and encounters).
"""
import gzip
import hashlib
import json
import os
import sys
import urllib.parse
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPlainTextEdit,  # noqa: E402
                               QPushButton)

from aion2calc.gui import combat as cb  # noqa: E402
from aion2calc.gui import combat_views as cv  # noqa: E402
from aion2calc.gui import combat_records as cr  # noqa: E402
from aion2calc.gui import combat_featured as cf  # noqa: E402
from aion2calc.gui.combat_community import BossProgression, BuildPoints, CommunityLogs, RunSpeed  # noqa: E402
from aion2calc.gui.combat_extras import BoxPlot, PersonalRecords, TrendChart  # noqa: E402
from aion2calc.gui.combat_featured_page import _Closer, _Painted, _Segment, _Spread  # noqa: E402
from aion2calc.gui.combat_page import CombatPage  # noqa: E402
from aion2calc.gui.combat_owned import Identities, OwnedUploads  # noqa: E402
from aion2calc.gui.combat_saved import RecordedEncounters, Section, UploadQueue  # noqa: E402
from aion2calc.gui.window import MainWindow, WebPage  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_native_overlay_toolbar import settle  # noqa: E402

ENCOUNTERS = [{"id": 3, "player": "TestSorc", "class_name": "sorcerer", "boss": "Ice Queen", "source": "abysslogs",
               "duration": 92.4, "dps": 41234.5}]
T0 = datetime(2026, 11, 1, 12, 0).timestamp()       # noon on 1 November, in this computer's clock
DAY = 86400
#: The recordings this computer saved, newest first as the app lists them.
RECORDINGS = [
    {"file": "session-3.a2log.json", "title": "Raid night", "updated": T0 + 3 * DAY, "segments": 2, "unfinished": False,
     "archive": {"id": "rec-1", "part": 2, "closed": True},
     "contexts": [{"segment": 0, "boss": "Ice Queen", "boss_code": 2001, "category": "raid", "role": "final",
                   "difficulty": "hard", "duration": 125.4, "encounter_type": "sanctuary"},
                  {"segment": 1, "boss": "Frost Hound", "boss_code": 2002, "category": "raid", "role": "mini",
                   "difficulty": "hard", "duration": 40, "encounter_type": "sanctuary"}]},
    {"file": "session-2.a2log.json", "title": "", "updated": T0 + DAY, "segments": 1, "unfinished": True, "archive": None,
     "contexts": [{"segment": 0, "boss": None, "category": "pvp", "role": None, "difficulty": "unknown", "duration": 61,
                   "encounter_type": "pvp_arena"}]},
    {"file": "session-1.a2log.json", "title": "Field run", "updated": T0, "segments": 2, "unfinished": False, "archive": None,
     "contexts": [{"segment": 0, "boss": None, "category": "other", "duration": 5, "encounter_type": "unknown"},
                  {"segment": 1, "boss": "Ash Wyrm", "boss_code": 3001, "category": "field_boss", "role": "field",
                   "difficulty": "unknown", "duration": 302, "encounter_type": "pve_open_world"}]},
]
#: An older recording, on the next page.
OLDER = [{"file": "session-0.a2log.json", "title": "Old raid", "updated": T0 - 30 * DAY, "segments": 1, "unfinished": False,
          "archive": {"id": "rec-1", "part": 1, "closed": True},
          "contexts": [{"segment": 0, "boss": "Ice Queen", "boss_code": 2001, "category": "raid", "role": "final",
                        "difficulty": "normal", "duration": 200, "encounter_type": "sanctuary"}]}]
PORTRAIT = "https://img.example/npc/2001.png"
SORCERER = "https://metabot.gg/web/aion2/classes/sorcerer.webp"
#: The log server's public logs, as its pages give them (PvE, then PvP).
COMMUNITY_LOGS = [
    {"id": "log0001", "created_at": T0, "uploader": "Uploader A", "bosses": [{"name": "Ice Queen", "icon": PORTRAIT}],
     "players": [{"name": "TestSorc", "class": "sorcerer"}],
     "contexts": [{"segment": 0, "boss": "Combat 3", "duration": 10},
                  {"segment": 1, "boss": "Frost Hound", "boss_role": "mini", "duration": 40},
                  {"segment": 2, "boss": "Ice Queen", "boss_role": "final", "difficulty": "Hard", "duration": 125,
                   "start": T0 + 60, "party_size": 4, "encounter_type": "sanctuary", "game_patch": "version:product:2.1",
                   "players": [{"name": "TestSorc", "class": "sorcerer", "verified": True},
                               {"name": "TestCleric", "class": "cleric", "pseudonym": True}, {"name": ""}]}]},
    {"id": "log0002", "created_at": T0 - DAY, "players": [{"name": "Solo", "class": "ranger"}],
     "contexts": [{"segment": 0, "boss": "Ash Wyrm", "difficulty": "normal", "duration": 300,
                   "encounter_type": "pve_open_world"}]}]
PVP_LOGS = [{"id": "log0003", "created_at": T0, "contexts": [
    {"segment": 0, "boss": "Combat 1", "zone": "Abyss Gate", "encounter_type": "pvp_abyss", "duration": 30, "party_size": 6},
    {"segment": 1, "boss": "Combat 2", "encounter_type": "pvp_unknown", "duration": 12}]}]


#: The log server's answers for Personal records.
PERFORMANCE = {"note": "Recorded rates.", "samples": 12, "excluded_unknown_metadata": 1, "groups": [
    {"boss": "Ice Queen", "boss_key": "npc:2001", "encounter_type": "sanctuary", "game_patch": "version:product:2.1.0.3.9",
     "difficulty": "Hard", "party_size": 4, "instance_id": 7, "class": "cleric", "min": 1000, "q1": 2000, "median": 2500,
     "q3": 3000, "max": 4000, "count": 3, "comparison": {"status": "thin", "identities": 2, "reasons": ["Too few parses."]}},
    {"boss": "Ice Queen", "boss_key": "npc:2001", "encounter_type": "sanctuary", "game_patch": "version:product:2.1.0.3.9",
     "difficulty": "Hard", "party_size": 4, "instance_id": 7, "class": "sorcerer", "min": 5000, "q1": 6000, "median": 7000,
     "q3": 8000, "max": 9000, "count": 9, "comparison": {"status": "available", "identities": 6}},
    {"boss": "Ash Wyrm", "class": "ranger", "min": 10, "q1": 20, "median": 30, "q3": 40, "max": 50, "count": 1}]}
BOSS_STATUS = {"generated_at": T0, "truncated": True, "groups": [
    {"boss": "Ice Queen", "npc_id": "2001", "region": "NA", "game_patch": "version:product:2.1", "map_id": 300,
     "instance_id": 7, "last_defeat_at": T0 - 3600, "seconds_since_defeat": 7200, "observed_defeats": 3,
     "party_observations": 5, "last_log_id": "log0001", "last_segment": 2,
     "latest_observation": {"timing_basis": "server_clock", "engaged_roster_members": 4, "recorded_roster_members": 6,
                            "party_roster_complete": True}},
    {"boss": None, "npc_id": None, "last_log_id": "bad id"}]}
RECORDS = {"identity": "TestSorc on Zikel", "note": "Public submissions only.", "total": 120, "records": [
    {"boss": "Ice Queen", "log": "log0001", "encounter_type": "sanctuary", "game_patch": "version:product:2.1",
     "difficulty": "Hard", "party_size": 4, "instance_id": 7, "class": "sorcerer", "best_score": 41234.6, "attempts": 3}],
    "history": [{"boss": "Ice Queen", "log_id": "log0001", "name": "TestSorc", "verified": True, "server": 2102,
                 "score": 41234.6, "ranking_eligible": True, "created_at": T0},
                {"boss": "Ash Wyrm", "log_id": "log0002", "name": "Hidden", "pseudonym": True, "server": 99999,
                 "dps": 900, "ranking_eligible": False}]}
CONSISTENCY = {"note": "Matched recordings.", "identity": "TestSorc on Zikel", "metric": "dps", "excluded_missing_evidence": 2,
               "groups": [{"boss": "Ice Queen", "class_name": "sorcerer", "game_patch": "version:product:2.1",
                           "difficulty": "Hard", "party_size": 4, "instance_id": 7, "samples": 3, "median": 40000,
                           "min": 30000, "max": 50000, "coefficient_of_variation_pct": 12.345,
                           "median_absolute_deviation": 5000, "standard_deviation": 6000, "recent_five_median": None,
                           "previous_five_median": None, "change_pct": None, "variation_available": False,
                           "trend_available": False, "omitted_history": 0, "observed_death_markers": 1,
                           "samples_with_death_markers": 1,
                           "history": [{"uploaded_at": T0 - 2 * DAY, "score": 30000, "recorded_deaths": None,
                                        "log": "log0002", "segment": 0},
                                       {"uploaded_at": T0 - DAY, "score": 50000, "recorded_deaths": 1, "log": "log0001",
                                        "segment": 2},
                                       {"uploaded_at": T0, "score": 40000, "recorded_deaths": 0, "log": "log0001",
                                        "segment": 3}]}]}

# the featured encounters: one encounter of two phases, three teams (a party, a legion, a party across servers)
FE_ID = "fe_0123456789"
TEAM_A = {"name": "Night Watch", "kind": "party", "server": 2102, "region": "na",
          "members": [{"name": "TestSorc", "class": "sorcerer"}, {"name": "TestCleric", "class": "cleric"}]}
TEAM_B = {"name": "Old Guard", "kind": "legion", "region": "eu"}
TEAM_C = {"name": "Drifters", "kind": "party", "members": [{"name": "TestRanger", "class": "ranger"}]}
PHASES = [{"boss_key": "npc:2001", "boss": "Ice Queen", "icon": PORTRAIT}, {"boss_key": "npc:2002", "boss": "Frost Hound"}]
FEATURED = {"id": FE_ID, "title": "Frost Spire", "boss": "Ice Queen", "boss_key": "npc:2001", "icon": PORTRAIT,
            "difficulty": "Hard", "starts_at": T0 - 7 * DAY, "phases": PHASES, "summary": {
                "teams": 3, "complete": 1, "pulls": 42,
                "progress": [{"team": TEAM_A, "complete": True, "killed": 2, "phases": 2},
                             {"team": TEAM_B, "complete": False, "killed": 1, "phases": 2, "best_hp": 12.34}],
                "speed": [{"team": TEAM_A, "elapsed": 754}],
                "execution": [{"team": TEAM_A, "deaths": 1, "seconds": 300}, {"team": TEAM_B, "deaths": None}],
                "all_stars": {"dps": [{"name": "TestSorc", "class": "sorcerer", "server": 2102, "points": 187.25}],
                              "support": [{"name": "TestCleric", "class": "cleric", "points": None}]},
                "classes": {"dps": [{"class": "sorcerer", "median": 51234.5}]}}}
RACE = {"phases": [{**PHASES[0], "teams": 3, "killed_by": 1, "first_kill": {"team": TEAM_A, "at": T0 - 2 * DAY}},
                   {**PHASES[1], "teams": 2, "killed_by": 1}],
        "teams": [{"rank": 1, "team": TEAM_A, "complete": True, "first_kill_at": T0 - DAY, "position": 1, "killed": 2,
                   "phases": 2, "pulls": 12, "log": "log0001"},
                  {"rank": 2, "team": TEAM_B, "complete": False, "next_phase": 1, "best_hp": 12.34, "position": 0.62,
                   "killed": 1, "phases": 2, "pulls": 20},
                  {"rank": 3, "team": TEAM_C, "complete": False, "next_phase": 0, "position": 0.1, "killed": 0, "phases": 2,
                   "pulls": 10}],
        "regions": ["na", "eu"], "note": "Public logs only."}
FE_PROGRESS = {"progress": [{"rank": 1, "team": TEAM_A, "complete": True, "killed": 2, "phases": 2, "killed_bosses": [0, 1, 5],
                             "pulls": 12, "progress_at": T0 - DAY},
                            {"rank": 2, "team": TEAM_B, "killed": 1, "phases": 2, "best_hp": 12.34, "killed_bosses": [0],
                             "pulls": 20, "progress_at": T0}],
               "kills": [{"rank": 1, "team": TEAM_A, "patch": "version:product:2.1", "composition": {"sorcerer": 1, "cleric": 1},
                          "at": T0 - DAY, "seconds": 754, "deaths": 1, "log": "log0001"}],
               "total": 120, "page": 1, "regions": ["na", "eu"]}
FE_REPORTS = {"logs": [{"id": "log0001", "title": "Frost Spire clear", "uploader": "Uploader A", "created_at": T0,
                        "contexts": [{"boss": "Ice Queen"}, {"boss": None}, {"boss": "Frost Hound"}], "duration": 3725,
                        "players": [{"name": "TestSorc", "class": "sorcerer"}, {"name": "TestCleric", "class": "cleric"}]},
                       {"id": "log0002", "boss": "Ice Queen", "created_at": T0 - DAY}],
              "total": 31, "page": 1, "limit": 30}
FE_RANKED = {"entries": [{"name": "TestSorc", "class": "sorcerer", "server": 2102, "score": 51234.5, "parse": 98.6,
                          "duration": 185, "created_at": T0, "log": "log0001", "segment": 3},
                         {"name": "TestCleric", "class": "cleric", "score": None, "parse": None}],
             "regions": ["na"]}
FE_SPEED = {"entries": [{"rank": 1, "team": TEAM_A, "elapsed": 754, "patch": "version:product:2.1", "at": T0, "log": "log0001"}]}
FE_STATISTICS = {"classes": [{"class": "sorcerer", "role": "dps", "count": 12, "p25": 40000, "median": 50000, "p75": 60000,
                              "p95": 80000, "max": 90000},
                             {"class": "cleric", "role": "support", "count": 3, "median": 20000, "max": 25000}]}


class LogServer:
    """The log server's public routes behind the app's community proxy, as logs-view.js asks them."""

    def __init__(self):
        self.asked: list[str] = []
        self.refusal = None
        self.many = 0                                       # that many more fights of Ice Queen in the first log
        self.facets = {"boss": ["Ice Queen", "Frost Hound", "Combat 3", "Ash Wyrm"],
                       "boss_roles": {"Frost Hound": "mini", "Ice Queen": "final"},
                       "difficulty": ["normal", "Hard", "easy"],
                       "encounter_type": ["sanctuary", "pve_open_world", "pvp_arena", "pvp_abyss"],
                       "region": ["NA", "EU"], "game_patch": ["version:product:2.1", "version:product:2.0"],
                       "party_size": [4, 8], "latest_submitted_patch": "version:product:2.1"}
        self.speed = {"entries": [
            {"rank": 1, "count": 3, "boss_route": ["iq", "fh"], "attempts": [{"boss_key": "iq", "boss": "Ice Queen"}],
             "encounter_type": "sanctuary", "difficulty": "Hard", "elapsed_seconds": 1234, "party_size": 4, "log": "log0001"},
            {"rank": 2, "count": 1, "boss_route": [], "elapsed_seconds": None, "party_size": None}],
            "note": "Runs from public logs."}
        self.progression = {"groups": [
            {"boss": "Ice Queen", "difficulty": "normal", "region": "NA", "game_patch": "version:product:2.1", "attempts": 10,
             "kills": 4, "wipes": 6, "observed_kill_rate": 0.4, "fastest_kill_seconds": 180, "icon": PORTRAIT},
            {"boss": "Frost Hound", "difficulty": "normal", "attempts": 3, "kills": 3, "wipes": 0},
            {"boss": "Ash Wyrm", "difficulty": "Hard", "attempts": 2, "kills": 0, "wipes": 2, "observed_kill_rate": None,
             "fastest_kill_seconds": 0},
            {"boss": "Ice Queen", "difficulty": "Hard", "region": "EU", "attempts": 5, "kills": 1, "wipes": 4,
             "observed_kill_rate": 0.2, "fastest_kill_seconds": 400}]}
        self.featured: list[dict] = []                       # none featured, unless a test features one
        self.points = {"observations": [
            {"class_name": "sorcerer", "skill": 100, "stigma": 20, "daevanion": 300, "ariel": None, "region": "NA"},
            {"class_name": "sorcerer", "skill": 110, "stigma": 20, "daevanion": 300, "ariel": 5, "region": "EU"},
            {"class_name": "cleric", "skill": 50, "stigma": 10, "daevanion": 100}]}

    def __call__(self, path):
        self.asked.append(path)
        if self.refusal:
            raise ValueError(self.refusal)
        route, _, query = path.partition("?")
        q = urllib.parse.parse_qs(query)
        if route == "/api/v1/report-facets":
            return json.loads(json.dumps(self.facets))
        if route == "/api/v1/logs":
            logs = json.loads(json.dumps(PVP_LOGS if q.get("combat_mode") == ["pvp"] else COMMUNITY_LOGS))
            for i in range(self.many):
                logs[0]["contexts"].append({"segment": 10 + i, "boss": "Ice Queen", "difficulty": "Hard", "duration": 100,
                                            "start": T0 - 2 * DAY - i})
            return {"logs": logs if q["page"] == ["1"] else [], "total": None}
        if route == "/api/v1/run-leaderboard":
            return json.loads(json.dumps(self.speed)) if "boss" not in q else {"entries": []}
        if route == "/api/v1/encounter-progression":
            return json.loads(json.dumps(self.progression))
        if route == "/api/v1/progression":
            return json.loads(json.dumps(self.points))
        if route == "/api/v1/performance":
            return json.loads(json.dumps(PERFORMANCE))
        if route == "/api/v1/boss-status":
            return json.loads(json.dumps(BOSS_STATUS))
        if route == "/api/v1/records":
            return json.loads(json.dumps(RECORDS))
        if route == "/api/v1/consistency":
            return json.loads(json.dumps(CONSISTENCY))
        if route == "/api/v1/featured":
            return {"featured": json.loads(json.dumps(self.featured)), "note": "Featured by the operator."}
        if route.startswith("/api/v1/featured/"):
            fid, _, view = route[len("/api/v1/featured/"):].partition("/")
            if fid != FE_ID:
                raise ValueError("RuntimeError: Community server (404): unknown featured encounter")
            answers = {"": FEATURED, "race": RACE, "progress": FE_PROGRESS, "reports": FE_REPORTS,
                       "rankings": FE_SPEED if q.get("metric") == ["speed"] else FE_RANKED, "statistics": FE_STATISTICS}
            return json.loads(json.dumps(answers[view]))
        raise AssertionError(path)
TOKEN = "t" * 24
#: The private credentials of this computer's uploads, on two servers.
OWNERS = [{"server": "https://logs.example", "id": "abc123", "delete_token": TOKEN, "title": "Raid night"},
          {"server": "https://logs.example", "id": "def456", "delete_token": TOKEN, "title": "Field run"},
          {"server": "https://other.example", "id": "ghi789", "delete_token": TOKEN, "title": "Old arena"}]
#: The identity credentials kept here, for the share server's characters.
CLAIMS = [{"server": "https://logs.example", "name": name, "server_name": "2102", "token": "a2id_" + name.lower() * 5,
           "status": "", "claimed_at": T0} for name in ("Epsilon", "Zeta", "Eta", "Theta")]
CLAIMS.append({"server": "https://other.example", "name": "Iota", "server_name": "2102", "token": "a2id_" + "iota" * 6,
               "status": "", "claimed_at": T0})


class ShareServer:
    """The share server's identity routes, as identity.js asks them."""

    def __init__(self):
        self.asked: list[tuple] = []
        self.characters = [
            {"name": "Alpha", "server": "2102", "recordings": 3, "claimable": True, "claimed": False},
            {"name": "Beta", "server": "1001", "recordings": 1, "claimable": False, "claimed": False},
            {"name": "Gamma", "server": "2102", "recordings": 4, "claimable": True, "claimed": True,
             "held_with_these_credentials": False, "latest_recording": T0, "holder_latest_recording": T0 - DAY},
            {"name": "Delta", "server": "2102", "recordings": 3, "claimable": True, "claimed": True,
             "held_with_these_credentials": True},
            {"name": "Epsilon", "server": "2102", "recordings": 5, "claimable": True, "claimed": True}]
        self.statuses = {
            "Epsilon": {"status": "active", "verified_at": T0, "recordings": 4, "opt_out": False,
                        "challenge": {"until": T0 + 7 * DAY}},
            "Zeta": {"status": "pending", "activates_at": T0 + 7 * DAY},
            "Eta": {"status": "revoked", "revocation": {"at": T0, "note": "shared account"}}}

    def __call__(self, base, path, method="GET", body=None, token=None):
        self.asked.append((base, path, method, json.loads(json.dumps(body)), token))
        if path == "/api/v1/identity/claimable":
            return {"characters": json.loads(json.dumps(self.characters)), "min_recordings": 3}
        if path == "/api/v1/identity":
            name = next(c["name"] for c in CLAIMS if c["token"] == token)
            if name not in self.statuses:
                raise ValueError("Unknown identity credential")
            return json.loads(json.dumps(self.statuses[name]))
        if path == "/api/v1/identity/claim":
            return {"token": "a2id_" + body["name"].lower() * 6, "status": "active", "claimed_at": T0}
        if path in ("/api/v1/identity/preferences", "/api/v1/identity/release", "/api/v1/identity/appeal"):
            return {"ok": True}
        raise AssertionError(path)


def _red_png() -> bytes:
    image = QImage(8, 8, QImage.Format_ARGB32)
    image.fill(QColor("#ff0000"))
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


class FakeApp:
    """The app as Combat Logs asks it; an analysis runs for ``reads`` readings. The recordings come a page at a time
    (``RECORDINGS``, then ``OLDER``); ``refusals`` holds what the log server says to a file's next upload, ``prints``
    a file's fingerprint when it is not its name's."""

    def __init__(self, reads=2, open_refused=False, older=True, recordings_refused=None):
        self.reads, self.open_refused = reads, open_refused
        self.calls, self.posts = [], []
        self.encounters = json.loads(json.dumps(ENCOUNTERS))
        self.recordings = json.loads(json.dumps(RECORDINGS))
        self.older = json.loads(json.dumps(OLDER)) if older else []
        self.recordings_refused = recordings_refused
        self.server = {"url": "https://logs.example", "has_key": True, "visibility": "legion"}
        self.refusals: dict[str, str] = {}
        self.prints: dict[str, str] = {}
        self.queue_kept = None
        self.uploads = 0
        self.owners = json.loads(json.dumps(OWNERS))
        self.states: dict[str, dict] = {}                  # what the log server says of an upload when asked
        self.owner_refusal = None
        self.asked: list[dict] = []                        # what was asked of the uploads' servers
        self.claims = json.loads(json.dumps(CLAIMS))
        self.log_server = LogServer()

    def fingerprint(self, file):
        return self.prints.get(file) or hashlib.sha256(file.encode()).hexdigest()

    def sessions(self, query):
        if self.recordings_refused:
            raise ValueError(self.recordings_refused)
        offset, limit, archive = int(query["offset"][0]), int(query["limit"][0]), query.get("archive", [""])[0]
        rows = [*self.recordings, *self.older]
        if archive:
            rows = sorted((r for r in rows if (r.get("archive") or {}).get("id") == archive), key=lambda r: r["archive"]["part"])
            return {"rows": rows[offset:offset + limit], "has_more": offset + limit < len(rows), "archive": archive}
        page = self.recordings if offset == 0 else self.older if offset == limit else []
        return {"rows": json.loads(json.dumps(page)), "has_more": offset == 0 and bool(self.older)}

    def ownership(self, body):
        """The app's private credentials: imported, forgotten, or used with an upload's server."""
        if body.get("action") == "import":
            kept = {(r["server"], r["id"]): r for r in self.owners}
            for row in body["owners"]:
                kept[(row["server"], row["id"])] = cb.clean_owner(row)
            self.owners = list(kept.values())
            return self.owners
        owner = body["owner"]
        if body["action"] == "forget":
            self.owners = [r for r in self.owners if (r["server"], r["id"]) != (owner["server"], owner["id"])]
            return self.owners
        self.asked.append(json.loads(json.dumps(body)))
        if self.owner_refusal:
            raise ValueError(self.owner_refusal)
        state = self.states.setdefault(owner["id"], {"visibility": "unlisted", "url": f"{owner['server']}/log/{owner['id']}"})
        if body["action"] in ("visibility", "rotate"):
            state.update(visibility=body["visibility"],
                         url=f"{owner['server']}/log/{owner['id']}" + ("?key=n3w" if body["visibility"] == "private" else ""))
        if body["action"] == "appeal":
            state["appeal"] = {"status": "open", "created_at": T0}
        if body["action"] == "delete":
            return {"deleted": True}
        return json.loads(json.dumps(state))

    def get_bytes(self, path, timeout=None):
        self.calls.append(path)
        if path in ("/static/game-assets/npc/2001.png", "/static/game-assets/class/sorcerer.png"):
            return _red_png()
        raise OSError("no such picture")

    def get(self, path, timeout=None):
        self.calls.append(path)
        if path == "/api/logs":
            return {"folder": "/data/logs", "files": 12}
        if path == "/api/logserver":
            return dict(self.server)
        if path == "/api/encounters":
            return json.loads(json.dumps(self.encounters))
        if path == "/static/game-assets.json":
            return {"assets": {PORTRAIT: "game-assets/npc/2001.png", SORCERER: "game-assets/class/sorcerer.png"},
                    "npc_portraits": {"2001": PORTRAIT}}
        if path.startswith("/api/community?path="):
            return self.log_server(urllib.parse.unquote(path.split("=", 1)[1]))
        if path == "/api/ui":
            return {"combat_colors": {"enabled": True, "colors": {"sorcerer": "#123456"}}}
        if path == "/api/upload-queue":
            return json.loads(json.dumps(self.queue_kept))
        if path == "/api/log-ownership":
            return json.loads(json.dumps(self.owners))
        if path == "/api/identity-claims":
            return json.loads(json.dumps(self.claims))
        if path.startswith("/api/sessions?"):
            query = urllib.parse.parse_qs(path.split("?", 1)[1], keep_blank_values=True)
            if "fingerprint" in query:
                return {"fingerprint": self.fingerprint(query["fingerprint"][0])}
            return self.sessions(query)
        if path == "/api/jobs/imp":
            self.reads -= 1
            if self.reads > 0:
                return {"status": "running", "log": ["fetching the log", "reading 812 hits"]}
            self.encounters.append({"id": 4, "player": "Party", "class_name": "cleric", "boss": "Ice Queen", "source": "file",
                                    "duration": 30, "dps": 900})
            return {"status": "done", "result": {"id": 4}}
        raise AssertionError(path)

    def post(self, path, body, timeout=None):
        self.posts.append((path, json.loads(json.dumps(body))))
        if path == "/api/logs/open":
            if self.open_refused:
                raise ValueError("No file manager on this computer")
            return {}
        if path == "/api/logserver":
            return {"url": body["url"], "has_key": True, "visibility": body["visibility"]}
        if path == "/api/encounters/import":
            return {"job": "imp"}
        if path == "/api/upload-queue":
            self.queue_kept = json.loads(json.dumps(body))
            return {"ok": True}
        if path == "/api/log-ownership":
            return self.ownership(body)
        if path == "/api/identity-claims":
            assert body["action"] == "replace"
            self.claims = json.loads(json.dumps(body["claims"]))
            return self.claims
        if path == "/api/sessions/share":
            if body["file"] in self.refusals:
                raise ValueError(self.refusals.pop(body["file"]))
            self.uploads += 1
            report = f"rep{self.uploads:04d}"
            secret = "?key=s3cret" if body["visibility"] == "private" else ""
            return {"id": report, "url": f"https://logs.example/log/{report}{secret}", "visibility": body["visibility"]}
        raise AssertionError(path)


def _page(app, **kwargs):
    kwargs.setdefault("identity_call", ShareServer())           # never the network
    page = CombatPage(app, **kwargs)
    page.job.interval_ms = 10
    page.resize(1200, 1400)
    page.show()
    QCoreApplication.processEvents()
    return page


def _texts(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _button(widget, words):
    def shown():
        return next((b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)), None)
    settle(lambda: shown() is not None)
    return shown()


def test_the_combat_words(tmp_path):
    assert cb.folder_line({"folder": "/data/logs", "files": 3}) == ("/data/logs", "(3 files)")
    assert cb.server_row({"url": "https://logs.example", "has_key": True, "visibility": "legion"}) == {
        "url": "https://logs.example", "key_hint": "key saved", "visibility": "legion"}
    assert cb.server_row({}) == {"url": "", "key_hint": "upload key", "visibility": "public"}
    assert cb.server_row({"visibility": "odd"})["visibility"] == "public"
    assert cb.server_body("https://x", "", "private") == {"url": "https://x", "key": None, "visibility": "private"}
    assert cb.server_body("https://x", "k1", "public")["key"] == "k1"                        # a key typed is sent
    row = cb.encounter_rows(ENCOUNTERS)[0]
    assert row == {"id": 3, "player": "TestSorc", "class": "Sorcerer", "boss": "Ice Queen", "source": "abysslogs",
                   "duration": "92s", "dps": "41,235"}
    assert cb.encounter_rows([{"id": 1}, None])[0]["duration"] == "0s" and cb.encounter_rows("nope") == []
    assert cb.analysis_page(4) == "combat-log/analysis/4" and cb.list_page("owned") == "combat/owned"
    assert cb.import_body("https://abysslogs.com/e/1", "") == {"ref": "https://abysslogs.com/e/1", "player": ""}
    plain, packed = tmp_path / "fight.csv", tmp_path / "segment.json.gz"
    plain.write_text("t,skill,damage\n0,Flame Arrow,100\n", encoding="utf-8")
    packed.write_bytes(gzip.compress(b'{"segment": 1}'))
    assert cb.read_log_file(str(plain)).startswith("t,skill") and cb.read_log_file(str(packed)) == '{"segment": 1}'
    assert cb.file_body("x", "a.csv", "P") == {"text": "x", "name": "a.csv", "player": "P"}
    assert cb.last_line(["a", "b"]) == "b" and cb.last_line([]) == "" and cb.last_line(None) == ""


def test_the_views_and_lists(qapp):
    opened = []
    page = _page(FakeApp(), open_web=opened.append)
    chosen = {b.text(): b.objectName() for b in page.findChildren(QPushButton) if b.property("chosen")}
    assert chosen == {"Browse logs": "small", "Community Combat Logs": "primary"}  # the view underlined, the list gold
    QCoreApplication.processEvents()
    assert [w for w in page.findChildren(CommunityLogs) if w.isVisibleTo(page)]   # drawn here since 0.2.453
    for name, kind in (("Completed-run speed", RunSpeed), ("Boss progression", BossProgression),
                       ("Highest observed build points", BuildPoints), ("Personal records", PersonalRecords)):
        next(b for b in page.findChildren(QPushButton) if b.accessibleName() == name).click()
        QCoreApplication.processEvents()
        assert [w for w in page.findChildren(kind) if w.isVisibleTo(page)]     # every view drawn here since 0.2.454
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Browse logs").click()
    for name, kind in (("My Uploads", OwnedUploads), ("My Character Identities", Identities)):
        next(b for b in page.findChildren(QPushButton) if b.accessibleName() == name).click()
        QCoreApplication.processEvents()
        assert [w for w in page.findChildren(kind) if w.isVisibleTo(page)]           # drawn here since 0.2.452


def test_saved_logs(qapp, tmp_path):
    opened, links = [], []
    packed = tmp_path / "segment.json.gz"
    packed.write_bytes(gzip.compress(b'{"segment": 1}'))
    app = FakeApp()
    page = _page(app, open_web=opened.append, choose_file=lambda: str(packed), open_link=links.append)
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    settle(lambda: "Every analyzed log is saved as a file in" in _texts(page) and "Ice Queen" in _texts(page))
    texts = _texts(page)
    assert "(12 files)" in texts and "<code>/data/logs</code>" in texts and "41,235" in texts and "92s" in texts
    assert "Sorcerer" in texts and "Recorded encounters by type" in texts and "Upload recordings" in texts
    assert page.server_url.text() == "https://logs.example" and page.server_key.placeholderText() == "key saved"
    assert page.server_seen.currentData() == "legion"
    note = next(label for label in page.findChildren(QLabel) if "AbyssLogs meter" in label.text())
    note.linkActivated.emit(cb.ABYSSLOGS)
    assert links == [cb.ABYSSLOGS]
    _button(page.encounters_box, "Open").click()
    assert opened == ["combat-log/analysis/3"]
    _button(page, "Open folder").click()
    settle(lambda: ("/api/logs/open", {}) in app.posts)
    page.server_seen.setCurrentIndex(page.server_seen.findData("private"))
    _button(page, "Save").click()
    settle(lambda: page.toast.text() == "Saved")
    assert ("/api/logserver", {"url": "https://logs.example", "key": None, "visibility": "private"}) in app.posts
    # a fight analyzed from its link: its progress, then its analysis opened and the list read again
    page.ref.setText("https://abysslogs.com/e/123")
    page.player.setText("TestSorc")
    page.analyze.click()
    settle(lambda: page.message.text() == "reading 812 hits")
    settle(lambda: opened[-1] == "combat-log/analysis/4")
    settle(lambda: "Party" in _texts(page))
    assert ("/api/encounters/import", {"ref": "https://abysslogs.com/e/123", "player": "TestSorc"}) in app.posts
    # and from a file, an AbyssLogs segment unpacked
    app.reads = 1
    _button(page, "Choose a file…").click()
    settle(lambda: any(path == "/api/encounters/import" and body.get("name") == "segment.json.gz" for path, body in app.posts))
    sent = next(body for path, body in app.posts if body.get("name") == "segment.json.gz")
    assert sent == {"text": '{"segment": 1}', "name": "segment.json.gz", "player": "TestSorc"}
    # a folder the computer cannot open: why, by the Analyze button
    refused = _page(FakeApp(open_refused=True))
    next(b for b in refused.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    _button(refused, "Open folder").click()
    settle(lambda: refused.message.text() == "No file manager on this computer")


def _store(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)


def test_the_recorded_encounters_words():
    found = cb.recorded({"rows": RECORDINGS, "has_more": True})
    assert [(e["boss"], e["category"], e["segment"]) for e in found] == [
        ("Ice Queen", "raid", 0), ("Frost Hound", "raid", 1), (None, "pvp", 0), ("Ash Wyrm", "field_boss", 1)]
    assert found[0]["date"] == T0 + 3 * DAY and found[0]["file"] == "session-3.a2log.json"   # an empty fight is left out
    assert cb.recorded({"rows": [{"contexts": [{"boss": "X"}], "updated": 1}]})[0]["category"] == "other"
    assert cb.recorded(None) == [] and cb.recorded({"rows": [None, {"contexts": None}]}) == []
    f = dict(cb.NO_FILTERS)
    assert [e["boss"] for e in found if cb.shown(e, f, False)] == ["Ice Queen", None, "Ash Wyrm"]   # a mini-boss hidden
    assert [e["boss"] for e in found if cb.shown(e, f, True)] == ["Ice Queen", "Frost Hound", None, "Ash Wyrm"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "boss": "Frost Hound"}, False)] == ["Frost Hound"]  # chosen
    assert [e["boss"] for e in found if cb.shown(e, {**f, "role": "mini"}, False)] == ["Frost Hound"]
    assert [e["category"] for e in found if cb.shown(e, {**f, "role": "pvp"}, False)] == ["pvp"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "difficulty": "hard"}, True)] == ["Ice Queen", "Frost Hound"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "category": "field_boss"}, False)] == ["Ash Wyrm"]
    # the days saved, in the computer's clock: From's midnight up to the midnight after To
    assert [e["boss"] for e in found if cb.shown(e, {**f, "from": "2026-11-02"}, False)] == ["Ice Queen", None]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "to": "2026-11-02"}, False)] == [None, "Ash Wyrm"]
    assert [e["boss"] for e in found if cb.shown(e, {**f, "from": "2026-11-04", "to": "2026-11-04"}, False)] == ["Ice Queen"]
    assert cb.recorded_choices(found, False) == {
        "boss": [("Ash Wyrm", "Ash Wyrm"), ("Ice Queen", "Ice Queen")],
        "category": [("pvp", "PvP encounters"), ("field_boss", "Field bosses"), ("raid", "Raids")],      # in their order
        "role": [("final", "Final boss"), ("mini", "Mini-boss"), ("pvp", "PvP"), ("field", "Field boss")],
        "difficulty": [("hard", "Hard")]}
    assert [b for b, _ in cb.recorded_choices(found, True)["boss"]] == ["Ash Wyrm", "Frost Hound", "Ice Queen"]
    assert sorted(["beta", "Alpha", "alpha", "Émile", "Echo"], key=cb.locale_key) == ["alpha", "Alpha", "beta", "Echo", "Émile"]
    sections = cb.recorded_sections(found + cb.recorded({"rows": OLDER}), f, False)
    assert [(s["title"], s["count"]) for s in sections] == [("PvP encounters", 1), ("Field bosses", 1), ("Raids", 2)]
    raid = sections[2]["rows"]
    assert [(r["boss"], r["role"], r["difficulty"], r["time"]) for r in raid] == [
        ("Ice Queen", "Final boss", "Hard", "2:05"), ("Ice Queen", "Final boss", "Normal", "3:20")]   # newest first
    assert sections[0]["rows"][0] == {"boss": "—", "code": None, "role": "Arena", "difficulty": "—", "time": "1:01",
                                      "date": cb.saved_at(T0 + DAY), "file": "session-2.a2log.json", "segment": 0}
    assert sections[1]["rows"][0]["difficulty"] == "—" and sections[1]["rows"][0]["role"] == "Field boss"
    assert cb.saved_at(T0) == "2026-11-01 12:00:00" and cb.saved_at(None) == "—"
    many = [dict(found[0], date=T0 + i) for i in range(cb.PER_SECTION + 3)]
    capped = cb.recorded_sections(many, f, False)[0]
    assert len(capped["rows"]) == cb.PER_SECTION and capped["more"] == 3 and capped["count"] == cb.PER_SECTION + 3
    assert cb.secs(None) == "—" and cb.secs(59.5) == "1:00" and cb.secs(3725) == "62:05"
    assert cb.role_label({"category": "pvp", "enc_type": "nope"}) == "PvP" and cb.role_label({"role": "odd"}) == ""
    assert cb.no_match(True) == "No recorded encounters match these filters among the recordings loaded so far."
    assert cb.no_match(False) == "No recorded encounters match these filters."
    assert cb.local_page("session 1.json", 2) == "combat-log/local/session%201.json?segment=2"
    assert cb.local_page("a(b)'!*~.json") == "combat-log/local/a(b)'!*~.json"       # as encodeURIComponent leaves them
    assert cb.sessions_path(25, 25, "rec/1") == "/api/sessions?paged=1&offset=25&limit=25&archive=rec%2F1"


def test_the_upload_queue_words(tmp_path):
    fp, fp2, rid = "a" * 64, "b" * 64, "c" * 32
    kept = {"format": "a2log-upload-checkpoint", "version": 1, "server": "https://logs.example/", "visibility": "private",
            "parts": [{"file": "s1.json", "title": "Raid", "fingerprint": fp, "request_id": rid, "status": "uploaded",
                       "id": "Abc123"},
                      {"file": "s2.json", "fingerprint": fp2, "status": "uploading"}]}
    clean = cb.clean_checkpoint(kept)
    assert clean["server"] == "https://logs.example" and clean["visibility"] == "private"
    assert clean["parts"][1] == {"file": "s2.json", "name": "s2.json", "title": "s2.json", "fingerprint": fp2,
                                 "request_id": None, "status": "uploading", "id": None}

    def refusal(change=None, part=None):
        value = json.loads(json.dumps(kept))
        value.update(change or {})
        value["parts"][0].update(part or {})
        with pytest.raises(ValueError) as problem:
            cb.clean_checkpoint(value)
        return str(problem.value)
    limit = "Choose an upload recovery checkpoint with at most 100 files."
    assert refusal({"format": "other"}) == limit and refusal({"version": True}) == limit and refusal({"version": 2}) == limit
    assert refusal({"parts": [{"file": f"f{i}"} for i in range(101)]}) == limit
    assert refusal({"parts": [{"file": "x", "title": "t" * 300000}]}) == limit
    for server in ("ftp://logs.example", "https://user:pw@logs.example", "https://logs.example/?key=1",
                   "https://logs.example/#k", "logs.example", "https://"):
        assert refusal({"server": server}) == "Invalid checkpoint server.", server
    assert refusal({"visibility": "legion"}) == "Invalid checkpoint visibility."
    assert refusal({"parts": [{"file": "a"}, {"file": "a"}]}) == "Invalid or duplicate checkpoint filename."
    assert refusal(part={"file": ""}) == refusal(part={"file": 5}) == "Invalid or duplicate checkpoint filename."
    assert refusal(part={"fingerprint": "XYZ"}) == "Invalid file fingerprint."
    assert refusal(part={"request_id": "short"}) == "Invalid upload request ID."
    assert refusal(part={"status": "done"}) == "Invalid checkpoint status."
    assert refusal(part={"id": "a b"}) == "Invalid uploaded report ID."
    assert refusal(part={"id": None}) == "Successful records require a server, ID and fingerprint."
    assert refusal({"server": ""}) == "Successful records require a server, ID and fingerprint."
    # restored: an interrupted upload is uncertain; nothing kept is no queue
    batch, chosen, selected, results = cb.restored(kept)
    assert batch == {"url": "https://logs.example", "visibility": "private"} and chosen == "private"
    assert list(selected) == ["s1.json", "s2.json"] and selected["s1.json"]["request_id"] == rid
    assert results["s1.json"] == {"status": "uploaded", "id": "Abc123", "fingerprint": fp}
    assert results["s2.json"]["status"] == "unknown"
    for nothing in (None, {}, {"parts": []}, []):
        with pytest.raises(ValueError, match="No saved upload queue is available."):
            cb.restored(nothing)
    # the checkpoint kept: never a key, a link or a credential
    rows = {"s3.json": {"file": "s3.json", "title": "", "fingerprint": fp, "request_id": rid}}
    point = cb.checkpoint(rows, {"s3.json": {"status": "failed", "error": "HTTP 400"}}, None, "unlisted")
    assert point == {"format": "a2log-upload-checkpoint", "version": 1, "server": "", "visibility": "unlisted",
                     "parts": [{"file": "s3.json", "name": "s3.json", "title": "s3.json", "fingerprint": fp,
                                "request_id": rid, "status": "failed", "id": None}]}
    # the results manifest: a private report's link and a link with a secret left out
    queued = {"a": {"file": "a", "archive": {"id": "rec-1", "part": 2, "closed": True}}, "b": {"file": "b"},
              "c": {"file": "c"}, "d": {"file": "d"}}
    results = {"a": {"status": "uploaded", "id": "rep1", "url": "https://Logs.Example:443/log/rep1", "visibility": "public"},
               "b": {"status": "uploaded", "id": "rep2", "url": "https://logs.example/log/rep2?key=s", "visibility": "unlisted"},
               "c": {"status": "uploaded", "id": "rep3", "url": "https://logs.example/log/rep3", "visibility": "private"},
               "d": {"status": "failed", "error": "HTTP 413: too large"}}
    doc = cb.manifest(queued, results, {"url": "https://logs.example", "visibility": "public", "has_key": True})
    assert doc == {"format": "a2log-upload-manifest", "version": 1, "server": "https://logs.example", "visibility": "public",
                   "parts": [{"file": "a", "archive": {"id": "rec-1", "part": 2, "closed": True}, "status": "uploaded",
                              "id": "rep1", "url": "https://logs.example/log/rep1"},
                             {"file": "b", "status": "uploaded", "id": "rep2"},
                             {"file": "c", "status": "uploaded", "id": "rep3"},
                             {"file": "d", "status": "failed", "error": "HTTP 413: too large"}]}
    assert "server" not in cb.manifest({}, {}, None)
    assert cb.archive_meta({"id": "r", "part": True}) is None and cb.archive_meta({"id": "r", "part": 0}) is None
    assert cb.archive_meta({"id": "r" * 120, "part": 3.0})["id"] == "r" * 100
    assert cb.safe_link("javascript:alert(1)") == "" and cb.safe_link("https://x.example") == "https://x.example/"
    # which refusals fail a file, which leave it uncertain, and which stop the batch
    assert cb.refused("ValueError: HTTP 409: already uploaded") == ("failed", True)
    assert cb.refused("ValueError: HTTP 400: bad log") == ("failed", False)
    assert cb.refused("ValueError: HTTP 413: too large") == ("failed", False)
    assert cb.refused("ValueError: File changed since fingerprint verification") == ("failed", False)
    assert cb.refused("timed out") == ("unknown", True)
    assert cb.refused("ValueError: Upload server changed. Start a new batch with the intended server.") == ("unknown", True)
    assert cb.batch_message(1, 2, True, True) == (
        "1 / 2 uploaded. Cancelled between uploads. Stopped after a connection, authentication or rate-limit error; "
        "remaining files are pending. Known successful files are skipped only when their fingerprints match.")
    # the page's files a filter lets through, and the queue's limit
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "rec-1", "")] == ["session-3.a2log.json"]
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "ARENA", "")] == ["session-2.a2log.json"]
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "", "pve_open_world")] == ["session-1.a2log.json"]
    assert [r["file"] for r in cb.visible_rows(RECORDINGS, "2", "sanctuary")] == ["session-3.a2log.json"]  # its part
    full = {f"f{i}": {"file": f"f{i}"} for i in range(cb.QUEUE_LIMIT)}
    with pytest.raises(ValueError, match="Queue limit is 100 files"):
        cb.pick(full, {}, {"file": "one more"})
    again = {"file": "f1"}
    cb.pick(full, {"f1": {"fingerprint": fp}}, again)
    assert full["f1"] is again and again["fingerprint"] == fp            # picked again, with the fingerprint seen
    assert len(cb.request_id()) == 32 and cb.request_id() != cb.request_id()


def _recorded(app, tmp_path, **kwargs):
    widget = RecordedEncounters(app, store=_store(tmp_path), **kwargs)
    widget.resize(1100, 900)
    widget.show()
    return widget


def _labels(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _folds(widget):
    QCoreApplication.processEvents()
    return [f for f in widget.findChildren(Section) if f.isVisibleTo(widget)]


def _find(widget, kind, test):
    """The first shown ``kind`` passing ``test``, once what was drawn last has shown."""
    QCoreApplication.processEvents()
    return next(w for w in widget.findChildren(kind) if test(w) and w.isVisibleTo(widget))


def test_recorded_encounters(qapp, tmp_path):
    opened = []
    app = FakeApp()
    widget = _recorded(app, tmp_path, open_web=opened.append)
    settle(lambda: not widget.loading and widget.findChildren(Section))
    texts, every = _labels(widget), [label.text() for label in widget.findChildren(QLabel)]
    assert cb.RECORDED_NOTE + cb.RECORDED_LOADED in texts
    assert "Ice Queen" in every and "Frost Hound" not in every                         # a mini-boss hidden
    folds = _folds(widget)
    assert [(f.button.text(), f.body.isVisibleTo(widget)) for f in folds] == [
        ("PvP encounters", True), ("Field bosses", False), ("Raids", False)]             # the first one open
    assert "(1)" in texts and "Arena" in texts and "1:01" in texts
    folds[2].button.click()
    assert "2:05" in _labels(widget) and "Final boss" in _labels(widget) and "Hard" in _labels(widget)
    # the boss's portrait comes; a boss without one keeps the app's logo
    face = next(label for label, code in widget.faces if code == 2001)

    def centre(label):
        image = label.pixmap().toImage()
        return image.pixelColor(image.width() // 2, image.height() // 2)
    settle(lambda: centre(face) == QColor("#ff0000"))
    assert centre(next(label for label, code in widget.faces if code == 3001)) != QColor("#ff0000")
    _find(widget, QPushButton, lambda b: b.text() == "view").click()
    assert opened == ["combat-log/local/session-2.a2log.json?segment=0"]
    # mini-bosses shown, and kept so
    boss = _find(widget, QComboBox, lambda c: c.accessibleName() == "Boss")
    assert [boss.itemText(i) for i in range(boss.count())] == ["any", "Ash Wyrm", "Ice Queen"]
    _find(widget, QCheckBox, lambda c: c.accessibleName() == "Show mini-bosses").setChecked(True)
    assert widget.store.value(cb.MINI_KEY) == "1"
    boss = _find(widget, QComboBox, lambda c: c.accessibleName() == "Boss")
    assert [boss.itemText(i) for i in range(boss.count())] == ["any", "Ash Wyrm", "Frost Hound", "Ice Queen"]
    assert _recorded(app, tmp_path).mini                                    # the next time too
    # a filter: by kind, then by the days saved, then cleared
    kind = _find(widget, QComboBox, lambda c: c.accessibleName() == "Type")
    kind.setCurrentIndex(kind.findData("field_boss"))
    kind.activated.emit(kind.currentIndex())
    assert [f.button.text() for f in _folds(widget)] == ["Field bosses"]
    widget.f["category"] = ""
    widget._filter("from", "2026-11-05")
    assert cb.no_match(True) in _labels(widget)
    _find(widget, QPushButton, lambda b: b.text() == "Clear").click()
    assert widget.f == cb.NO_FILTERS and len(_folds(widget)) == 3
    # the next fifty recordings
    _find(widget, QPushButton, lambda b: b.text() == "Load more recordings").click()
    settle(lambda: not widget.loading and not widget.more)
    assert "/api/sessions?paged=1&offset=50&limit=50&archive=" in app.calls
    assert "(3)" in _labels(widget) and cb.RECORDED_NOTE in _labels(widget)       # the older raid, mini-bosses shown
    assert not any(b.text() == "Load more recordings" for b in widget.findChildren(QPushButton) if b.isVisibleTo(widget))
    # nothing recorded yet, and the recordings not read
    empty = FakeApp(older=False)
    empty.recordings = []
    widget = _recorded(empty, tmp_path)
    settle(lambda: cb.NO_RECORDED in _labels(widget))
    widget = _recorded(FakeApp(recordings_refused="OSError: the logs folder cannot be read"), tmp_path)
    settle(lambda: "OSError: the logs folder cannot be read" in _labels(widget))
    assert any(b.text() == "Retry" for b in widget.findChildren(QPushButton) if b.isVisibleTo(widget))


def _queue(app, **kwargs):
    queue = UploadQueue(app, **kwargs)
    queue.resize(1100, 900)
    queue.show()
    settle(lambda: not queue.busy)
    return queue


def _click(widget, words):
    button = _find(widget, QPushButton, lambda b: b.text() == words)
    assert button.isEnabled(), words
    button.click()


def _picks(queue):
    QCoreApplication.processEvents()
    return {b.accessibleName(): b for b in queue.findChildren(QCheckBox) if b.accessibleName().startswith("Select ")
            and b.isVisibleTo(queue)}


def test_the_upload_queue(qapp, tmp_path):
    links, opened = [], []
    app = FakeApp()
    queue = _queue(app, open_link=links.append, open_web=opened.append)
    texts = _labels(queue)
    assert cb.QUEUE_HEAD in texts and "rec-1 · Part 2" in texts and "Unfinished checkpoint" in texts and "File slots 1–25" in texts
    picks = _picks(queue)
    assert sorted(picks) == ["Select Field run", "Select Raid night", "Select session-2.a2log.json"]
    assert not picks["Select session-2.a2log.json"].isEnabled()           # an unfinished checkpoint stays out
    _click(queue, "Select eligible rows on this page")
    assert list(queue.selected) == ["session-3.a2log.json", "session-1.a2log.json"] and "2 selected" in _labels(queue)
    settle(lambda: app.queue_kept is not None and len(app.queue_kept["parts"]) == 2)
    assert app.queue_kept["server"] == "" and app.queue_kept["visibility"] == "public"
    queue.visibility.setCurrentText("unlisted")
    queue.visibility.activated.emit(queue.visibility.currentIndex())
    settle(lambda: app.queue_kept["visibility"] == "unlisted")
    # the second file refused with a conflict: the batch stops there
    app.refusals["session-1.a2log.json"] = "ValueError: HTTP 409: already uploaded"
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == cb.batch_message(1, 2, False, True)
    shares = [body for path, body in app.posts if path == "/api/sessions/share"]
    assert [body["file"] for body in shares] == ["session-3.a2log.json", "session-1.a2log.json"]
    assert shares[0]["visibility"] == "unlisted" and shares[0]["server"] == "https://logs.example"
    assert shares[0]["completed_only"] is True and shares[0]["fingerprint"] == app.fingerprint("session-3.a2log.json")
    assert len(shares[0]["request_id"]) == 32 and shares[0]["request_id"] != shares[1]["request_id"]
    assert queue.results["session-1.a2log.json"]["status"] == "failed"
    assert app.queue_kept["server"] == "https://logs.example" and [p["status"] for p in app.queue_kept["parts"]] == [
        "uploaded", "failed"]
    texts = _labels(queue)
    assert any(t.startswith("Raid night: uploaded") and "Open uploaded report" in t for t in texts)
    assert any(t == "Field run: failed — ValueError: HTTP 409: already uploaded" for t in texts)
    report = next(label for label in queue.findChildren(QLabel) if "Open uploaded report" in label.text())
    report.linkActivated.emit("https://logs.example/log/rep0001")
    assert links == ["https://logs.example/log/rep0001"]
    # again: the uploaded one skipped (its fingerprint unchanged), the other uploaded
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == cb.batch_message(2, 2, False, False) and app.uploads == 2
    retried = [body for path, body in app.posts if path == "/api/sessions/share"][-1]
    assert retried["file"] == "session-1.a2log.json" and retried["request_id"] == shares[1]["request_id"]  # the same request
    # an outcome not known: retried only once allowed
    app.prints["session-3.a2log.json"] = "d" * 64
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == "File changed: Raid night. Clear the queue and review the new content before uploading."
    del app.prints["session-3.a2log.json"]
    queue.results["session-1.a2log.json"] = {"status": "unknown", "fingerprint": app.fingerprint("session-1.a2log.json")}
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message.startswith("Uncertain upload outcome for Field run. Check My uploads")
    _find(queue, QCheckBox, lambda b: b.text() == cb.RETRY_UNKNOWN).setChecked(True)
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == cb.batch_message(2, 2, False, False) and app.uploads == 3
    # a batch for another server or visibility, and no server at all
    queue.visibility.setCurrentText("private")
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == "Server or visibility changed. Clear the queue before starting a different batch."
    # cancelled before the next upload
    _click(queue, "Clear queue")
    assert queue.message == cb.CLEARED and not queue.selected and queue.batch is None
    settle(lambda: app.queue_kept["parts"] == [])
    _click(queue, "Select eligible rows on this page")
    _click(queue, "Upload selected / retry remaining")
    cancel = next(b for b in queue.findChildren(QPushButton) if b.text() == "Cancel after current upload")
    assert cancel.isEnabled() and queue.busy
    cancel.click()                                       # before the batch's first answer comes back
    assert queue.message == cb.CANCELLING
    settle(lambda: not queue.busy)
    assert queue.message.startswith("0 / 2 uploaded. Cancelled between uploads.")
    app.server["url"] = ""
    _click(queue, "Upload selected / retry remaining")
    settle(lambda: not queue.busy)
    assert queue.message == "Set an upload server first."
    # a file opened at its page; one recording's parts; the next page
    _find(queue, QPushButton, lambda b: b.text() == "Open").click()
    assert opened == ["combat-log/local/session-3.a2log.json"]
    _click(queue, "Show recording")
    settle(lambda: not queue.busy and queue.recording == "rec-1")
    assert app.calls[-1] == "/api/sessions?paged=1&offset=0&limit=25&archive=rec-1"
    assert "Recording rec-1 · parts remain separate reports" in _labels(queue)
    assert sorted(_picks(queue)) == ["Select Old raid", "Select Raid night"]
    _click(queue, "All recordings")
    settle(lambda: not queue.busy and queue.recording == "")
    _click(queue, "Older")
    settle(lambda: not queue.busy and queue.offset == 25)
    assert "File slots 26–50" in _labels(queue) and sorted(_picks(queue)) == ["Select Old raid"]
    _click(queue, "Newer")
    settle(lambda: not queue.busy and queue.offset == 0)
    words = _find(queue, QLineEdit, lambda w: w.accessibleName() == "Filter this page")
    words.setText("field")
    words.editingFinished.emit()
    assert sorted(_picks(queue)) == ["Select Field run"]


def test_the_upload_queue_recovery(qapp, tmp_path):
    fp = hashlib.sha256(b"session-3.a2log.json").hexdigest()
    kept = {"format": "a2log-upload-checkpoint", "version": 1, "server": "https://logs.example", "visibility": "private",
            "parts": [{"file": "session-3.a2log.json", "title": "Raid night", "fingerprint": fp, "status": "uploading",
                       "request_id": "e" * 32}]}
    app = FakeApp()
    app.queue_kept = kept
    saved = tmp_path / "out.json"
    recovery = tmp_path / "recovery.json"
    chosen = [str(recovery)]
    queue = _queue(app, choose_file=lambda: chosen[0], save_file=lambda name: str(saved) if name else "")
    _click(queue, "Restore saved queue")
    settle(lambda: not queue.busy and queue.selected)
    assert queue.message == cb.RESTORED and queue.chosen == "private" and queue.visibility.currentText() == "private"
    assert queue.results["session-3.a2log.json"]["status"] == "unknown"             # it may have been taken
    assert queue.batch == {"url": "https://logs.example", "visibility": "private"}
    assert not _find(queue, QPushButton, lambda b: b.text() == "Restore saved queue").isEnabled()
    _click(queue, "Export recovery file")
    assert json.loads(saved.read_text(encoding="utf-8"))["parts"][0]["status"] == "unknown"
    _click(queue, "Export upload results")
    assert json.loads(saved.read_text(encoding="utf-8"))["parts"] == [{"file": "session-3.a2log.json", "status": "unknown",
                                                                       "id": None}]
    # a recovery file: too large, unreadable, then one restored and kept
    _click(queue, "Clear queue")
    recovery.write_text("x" * (cb.RECOVERY_LIMIT + 1), encoding="utf-8")
    _click(queue, "Import recovery file…")
    assert queue.message == "Recovery file exceeds 256 KiB." and not queue.busy
    recovery.write_text("{not json", encoding="utf-8")
    _click(queue, "Import recovery file…")
    assert queue.message.startswith("Expecting property name") and not queue.selected
    recovery.write_text(json.dumps(dict(kept, visibility="unlisted", server="")), encoding="utf-8")
    _click(queue, "Import recovery file…")
    settle(lambda: not queue.busy)
    assert list(queue.selected) == ["session-3.a2log.json"] and queue.chosen == "unlisted" and queue.batch is None
    assert app.queue_kept["visibility"] == "unlisted"
    _click(queue, "Clear queue")
    app.queue_kept = None
    _click(queue, "Restore saved queue")
    settle(lambda: not queue.busy)
    assert queue.message == "No saved upload queue is available."
    chosen[0] = ""
    _click(queue, "Import recovery file…")                                # nothing chosen: nothing happens
    assert queue.message == "No saved upload queue is available."


def test_saved_logs_keep_their_queue(qapp, tmp_path):
    app = FakeApp()
    page = _page(app, store=_store(tmp_path))
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    settle(lambda: page.queue is not None and not page.queue.busy and page.recorded is not None and not page.recorded.loading)
    queue, recorded = page.queue, page.recorded
    _click(queue, "Select eligible rows on this page")
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Community Combat Logs").click()
    QCoreApplication.processEvents()
    assert not page.saved_panel.isVisible() and page.community_logs.isVisibleTo(page)
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    assert page.queue is queue and page.recorded is recorded and len(queue.selected) == 2     # the same queue
    logs = app.calls.count("/api/logs")
    page.hide()
    page.show()                                                            # shown again: read again
    settle(lambda: app.calls.count("/api/logs") == logs + 1 and not recorded.loading and not queue.busy)
    assert len(queue.selected) == 2


def test_the_my_uploads_and_identities_words():
    row = {"server": "https://logs.example/", "id": "abc123", "delete_token": TOKEN}
    assert cb.clean_owner(row) == {"server": "https://logs.example", "id": "abc123", "delete_token": TOKEN, "title": "abc123"}
    for bad in ({**row, "server": "ftp://logs.example"}, {**row, "server": "https://u:p@logs.example"},
                {**row, "server": "https://logs.example/?k=1"}, {**row, "id": "abc"}, {**row, "id": "abc-123"},
                {**row, "delete_token": "short"}, {**row, "delete_token": "t" * 19 + "!"}, {**row, "server": ""}):
        with pytest.raises(ValueError, match="Invalid original server, ID or private credential"):
            cb.clean_owner(bad)
    with pytest.raises(ValueError, match="Invalid upload credential"):
        cb.clean_owner(None)
    assert cb.owned_visibility(None) == "unchecked" and cb.owned_visibility({"error": "x", "visibility": "public"}) == "unchecked"
    f = {"q": "", "server": "", "visibility": ""}
    assert cb.owned_matches(OWNERS[0], {**f, "q": "RAID"}, None) and cb.owned_matches(OWNERS[0], {**f, "q": "abc1"}, None)
    assert not cb.owned_matches(OWNERS[0], {**f, "server": "https://other.example"}, None)
    assert cb.owned_matches(OWNERS[0], {**f, "visibility": "unchecked"}, None)
    assert cb.owned_matches(OWNERS[0], {**f, "visibility": "private"}, {"visibility": "private"})
    assert cb.owned_servers(OWNERS) == ["https://logs.example", "https://other.example"]
    assert cb.owned_page(0, 3) == 0 and cb.owned_page(26, 5) == 1 and cb.owned_pages(26) == 2 and cb.owned_pages(0) == 1
    assert cb.held(None) == {"lines": [], "appeal": False}
    assert cb.held({"moderation": {"note": "spam"}}) == {
        "lines": ["Moderator review: spam. Visibility changes are paused; you can still delete your upload."], "appeal": True}
    assert cb.held({"moderation": {"note": "spam"}, "appeal": {"status": "open", "created_at": T0}})["lines"][1] == (
        f"Appeal sent {cb.saved_at(T0)}; a moderator will uphold or overturn the hold.")
    assert cb.held({"appeal": {"status": "overturned", "decided_at": T0, "note": "fine"}})["lines"] == [
        f"Appeal overturned {cb.saved_at(T0)}: fine. The upload stays private until you choose its visibility."]
    assert cb.shared_link({"url": "https://logs.example/log/abc123?key=s"}, "https://logs.example") == \
        "https://logs.example/log/abc123?key=s"
    assert cb.shared_link({"url": "https://evil.example/log/abc123"}, "https://logs.example") == ""   # its own server only
    assert cb.shared_link({"url": "javascript:alert(1)"}, "https://logs.example") == ""
    assert cb.owned_state(None) == "Refresh to check" and cb.owned_state({"error": "no"}) == "no"
    assert cb.owned_controls(None) == {"editable": False, "rotate": False, "visibility": "unlisted"}
    assert cb.owned_controls({"visibility": "private"}) == {"editable": True, "rotate": True, "visibility": "private"}
    assert cb.owned_controls({"visibility": "public", "moderation": {"note": "x"}})["editable"] is False
    assert cb.owner_request(OWNERS[0], "appeal", "words") == {"owner": OWNERS[0], "action": "appeal", "statement": "words"}
    assert cb.owner_request(OWNERS[0], "visibility", "public")["visibility"] == "public"
    with pytest.raises(ValueError, match="Choose a private combat-log ownership backup"):
        cb.read_backup({"format": "a2log-owners", "version": True})
    assert cb.read_backup(cb.owned_backup(OWNERS)) == OWNERS
    # identities
    claim = {"server": "https://logs.example/", "name": " Alpha ", "server_name": 2102, "token": "a2id_" + "a" * 20}
    assert cb.clean_claim(claim) == {"server": "https://logs.example", "name": "Alpha", "server_name": "2102",
                                     "token": "a2id_" + "a" * 20, "status": "", "claimed_at": 0}
    for bad, words in (({**claim, "token": "a2id_short"}, "Invalid character name or identity credential"),
                       ({**claim, "name": "  "}, "Invalid character name or identity credential"),
                       ({**claim, "server": "logs.example"}, "Invalid server address"), (5, "Invalid identity credential")):
        with pytest.raises(ValueError, match=words):
            cb.clean_claim(bad)
    assert cb.claim_key(" Alpha ", 2102) == "alpha|2102" and cb.claim_key(None, None) == "|"
    assert cb.evidence(OWNERS, "https://logs.example") == [{"id": "abc123", "delete_token": TOKEN},
                                                         {"id": "def456", "delete_token": TOKEN}]
    kept = cb.kept_claims(CLAIMS, {**CLAIMS[0], "status": "active"})
    assert [c["name"] for c in kept] == ["Zeta", "Eta", "Theta", "Iota", "Epsilon"] and kept[-1]["status"] == "active"
    assert [c["name"] for c in cb.without_claim(CLAIMS, CLAIMS[1])] == ["Epsilon", "Eta", "Theta", "Iota"]
    assert cb.world_label("2102") == "Zikel" and cb.world_label("99999") == "99999" and cb.world_label("") == ""
    server = ShareServer()
    mine = [c for c in CLAIMS if c["server"] == "https://logs.example"]
    statuses = {cb.claim_key(c["name"], c["server_name"]): server.statuses.get(c["name"], {"error": "Unknown identity credential"})
                for c in mine}
    rows = cb.character_rows(server.characters, mine, statuses)
    assert [r["name"] for r in rows] == ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"]
    views = {r["name"]: cb.character_view(r, 3) for r in rows}
    assert views["Alpha"]["state"] == "Not claimed yet" and views["Alpha"]["actions"] == [("claim", "Claim", True, "")]
    assert views["Alpha"]["world"] == "Zikel" and views["Alpha"]["recordings"] == "3 of 3"
    assert views["Beta"]["state"] == "Needs 2 more public recordings where you are the recording player"
    assert views["Beta"]["actions"] == [("claim", "Claim", False, "")]
    assert views["Gamma"]["state"] == f"Held by another uploader (their latest recording {cb.saved_at(T0 - DAY)})"
    assert views["Gamma"]["actions"] == [("claim", "Challenge with newer recordings", True, cb.CHALLENGE_TIP)]
    assert views["Delta"]["actions"] == [("claim", "Recover", True, "")]
    assert views["Epsilon"]["state"] == f"<b>Verified</b> since {cb.saved_at(T0)} · 4 recordings"
    assert "press <b>Renew</b> before" in views["Epsilon"]["notes"][0] and views["Epsilon"]["opt_out"] is False
    assert [a[1] for a in views["Epsilon"]["actions"]] == ["Renew", "Release"] and views["Epsilon"]["recordings"] == "5 of 3"
    assert views["Zeta"]["state"].startswith("<b>Pending</b> · becomes yours on") and views["Zeta"]["recordings"] == "0"
    assert views["Zeta"]["actions"] == [("release", "Withdraw", True, "")]
    assert views["Eta"]["state"] == f"<b>Revoked</b> by a moderator on {cb.saved_at(T0)}: shared account"
    assert views["Eta"]["appeal"] is True and [a[1] for a in views["Eta"]["actions"]] == ["Claim with newer recordings", "Forget"]
    assert views["Theta"]["state"] == "<b>Credential not accepted</b> · Unknown identity credential"
    assert [a[1] for a in views["Theta"]["actions"]] == ["Claim again", "Forget"]
    assert cb.character_view({"name": "<b>", "status": {"status": "revoked", "appeal": {"status": "upheld", "note": "<i>"}}},
                             3)["notes"] == ["Appeal upheld : &lt;i&gt;"]                  # no time said: none shown


def _owned(app, tmp_path, answers=(), **kwargs):
    """My Uploads, its questions answered from ``answers`` (yes when they run out)."""
    asked = []

    def confirm(words):
        asked.append(words)
        return answers[len(asked) - 1] if len(asked) <= len(answers) else True
    widget = OwnedUploads(app, confirm=confirm, **kwargs)
    widget.asked = asked
    widget.resize(1300, 1000)
    widget.show()
    settle(lambda: widget.table_box is not None)
    return widget


def _row_buttons(widget, words):
    QCoreApplication.processEvents()
    return [b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)]


def _visibility_boxes(widget):
    QCoreApplication.processEvents()
    return [c for c in widget.findChildren(QComboBox) if c.accessibleName() == "Upload visibility" and c.isVisibleTo(widget)]


def test_my_uploads(qapp, tmp_path):
    opened, links = [], []
    app = FakeApp()
    widget = _owned(app, tmp_path, open_web=opened.append, open_link=links.append)
    texts = _labels(widget)
    assert widget.fold.button.text() == "My uploads · 3 saved credentials"
    assert "Raid night · abc123\nhttps://logs.example" in texts and texts.count("Refresh to check") == 3
    assert [b.isEnabled() for b in _row_buttons(widget, "Save visibility")] == [False, False, False]
    assert [b.isEnabled() for b in _row_buttons(widget, "Rotate private link")] == [False, False, False]
    # refreshed: its visibility, its link on its own server, and the controls it allows
    app.states["abc123"] = {"visibility": "private", "url": "https://logs.example/log/abc123?key=s3cret"}
    _row_buttons(widget, "Refresh")[0].click()
    settle(lambda: widget.message == "Current server status loaded.")
    assert app.asked[-1] == {"owner": OWNERS[0], "action": "refresh", "visibility": "unlisted"}
    assert "private" in _labels(widget) and _visibility_boxes(widget)[0].currentText() == "private"
    assert [b.isEnabled() for b in _row_buttons(widget, "Rotate private link")] == [True, False, False]
    link = next(label for label in widget.findChildren(QLabel) if "Open shared link" in label.text())
    link.linkActivated.emit("https://logs.example/log/abc123?key=s3cret")
    assert links == ["https://logs.example/log/abc123?key=s3cret"]
    # public only once asked; a private link replaced once asked
    _visibility_boxes(widget)[0].setCurrentText("public")
    widget.asked.clear()
    answers = [False]
    widget.confirm = lambda words: (widget.asked.append(words), answers.pop(0) if answers else True)[1]
    sent = len(app.asked)
    _row_buttons(widget, "Save visibility")[0].click()
    assert widget.asked == [cb.ASK_PUBLIC] and len(app.asked) == sent             # declined: nothing sent
    _row_buttons(widget, "Save visibility")[0].click()
    settle(lambda: widget.message == "Privacy updated. Use the displayed link.")
    assert app.asked[-1]["visibility"] == "public" and "public" in _labels(widget)
    _visibility_boxes(widget)[0].setCurrentText("private")
    _row_buttons(widget, "Save visibility")[0].click()
    settle(lambda: not widget.busy and app.asked[-1]["visibility"] == "private")
    _row_buttons(widget, "Rotate private link")[0].click()
    settle(lambda: not widget.busy and app.asked[-1]["action"] == "rotate")
    assert widget.asked[-1] == cb.ASK_ROTATE and app.asked[-1]["visibility"] == "private"
    # a hold: why, and one appeal (at least ten characters)
    app.states["def456"] = {"visibility": "public", "moderation": {"note": "spam reports"}}
    _row_buttons(widget, "Refresh")[1].click()
    settle(lambda: not widget.busy and "Moderator review: spam reports. Visibility changes are paused; you can still "
           "delete your upload." in _labels(widget))
    assert not _visibility_boxes(widget)[1].isEnabled()
    assert not _row_buttons(widget, "Send appeal")                         # folded until opened
    fold = next(s for s in widget.findChildren(Section) if s.button.text() == "Appeal this hold")
    fold.button.click()
    appeal = next(w for w in widget.findChildren(QPlainTextEdit))
    appeal.setPlainText("too short")
    _row_buttons(widget, "Send appeal")[0].click()
    assert widget.said.text() == cb.SHORT_APPEAL
    appeal.setPlainText("These were my own runs, recorded on my own computer.")
    _row_buttons(widget, "Send appeal")[0].click()
    settle(lambda: widget.message == cb.APPEAL_SENT)
    assert [a["action"] for a in app.asked[-2:]] == ["appeal", "refresh"]
    assert app.asked[-2]["statement"] == "These were my own runs, recorded on my own computer."
    assert f"Appeal sent {cb.saved_at(T0)}; a moderator will uphold or overturn the hold." in _labels(widget)
    # a refusal shown where the upload's state was
    app.owner_refusal = "ValueError: Select this upload's original server in Settings before managing it"
    _row_buttons(widget, "Refresh")[2].click()
    settle(lambda: widget.message == app.owner_refusal)
    assert app.owner_refusal in _labels(widget)
    app.owner_refusal = None
    # the filters
    search = _find(widget, QLineEdit, lambda w: w.accessibleName() == "Title or upload ID")
    search.setText("field")
    assert "1 of 3 uploads match." in _labels(widget) and len(_row_buttons(widget, "Refresh")) == 1
    server = _find(widget, QComboBox, lambda c: c.accessibleName() == "Original server")
    search.setText("")
    server.setCurrentIndex(server.findData("https://other.example"))
    server.activated.emit(server.currentIndex())
    assert len(_row_buttons(widget, "Refresh")) == 1 and "Old arena · ghi789\nhttps://other.example" in _labels(widget)
    _find(widget, QPushButton, lambda b: b.text() == "Clear").click()
    seen = _find(widget, QComboBox, lambda c: c.accessibleName() == "Visibility")
    seen.setCurrentIndex(seen.findData("private"))
    seen.activated.emit(seen.currentIndex())
    assert len(_row_buttons(widget, "Refresh")) == 1 and "1 of 3 uploads match." in _labels(widget)
    _find(widget, QPushButton, lambda b: b.text() == "Clear").click()
    # deleted from its server once asked, then forgotten here; another forgotten
    _row_buttons(widget, "Delete upload")[2].click()
    settle(lambda: widget.message == "Server upload deleted." and len(widget.rows) == 2)
    assert widget.asked[-1] == cb.ASK_DELETE and [a["action"] for a in app.asked[-1:]] == ["delete"]
    _row_buttons(widget, "Forget credential")[1].click()
    settle(lambda: len(widget.rows) == 1)
    assert widget.asked[-1] == cb.ASK_FORGET and widget.said.text() == "Local credential forgotten; server log unchanged."
    _find(widget, QPushButton, lambda b: b.text() == "Open My Uploads on the web page").click()
    assert opened == ["combat/owned"]


def test_my_uploads_backups_and_recovery(qapp, tmp_path):
    app = FakeApp()
    saved, backup = tmp_path / "backup.json", tmp_path / "in.json"
    widget = _owned(app, tmp_path, answers=[False], choose_file=lambda: str(backup), save_file=lambda name: str(saved))
    _click(widget, "Export private credentials")
    assert json.loads(saved.read_text(encoding="utf-8")) == {"format": "a2log-owners", "version": 1, "owners": OWNERS}
    backup.write_text("x" * (cb.OWNED_BACKUP_LIMIT + 1), encoding="utf-8")
    _click(widget, "Import private backup…")
    assert widget.said.text() == "Backup exceeds 2 MiB"
    backup.write_text(json.dumps({"format": "other"}), encoding="utf-8")
    _click(widget, "Import private backup…")
    assert widget.said.text() == "Choose a private combat-log ownership backup"
    more = {"server": "https://logs.example", "id": "jkl012", "delete_token": TOKEN, "title": "Imported"}
    backup.write_text(json.dumps(cb.owned_backup([more])), encoding="utf-8")
    _click(widget, "Import private backup…")                               # declined: nothing stored
    assert widget.asked == [cb.ASK_IMPORT] and len(app.owners) == 3
    _click(widget, "Import private backup…")
    settle(lambda: len(widget.rows) == 4)
    assert widget.said.text() == "Credentials imported. Refresh an upload to verify access."
    # an older upload's credential, saved from its server, ID and delete token
    widget.recover_fold.button.click()
    widget.recover_server.setText("https://logs.example")
    widget.recover_id.setText("no")
    widget.recover_token.setText(TOKEN)
    _click(widget, "Save credential locally")
    assert widget.said.text() == "Invalid original server, ID or private credential" and len(app.owners) == 4
    widget.recover_id.setText(" mno345 ")
    _click(widget, "Save credential locally")
    settle(lambda: len(widget.rows) == 5)
    assert widget.said.text() == "Credential saved locally. Refresh to verify it with the original server."
    assert app.owners[-1] == {"server": "https://logs.example", "id": "mno345", "delete_token": TOKEN, "title": "mno345"}
    # a page at a time
    app.owners = [{"server": "https://logs.example", "id": f"log{i:05d}", "delete_token": TOKEN, "title": f"Run {i}"}
                  for i in range(30)]
    _click(widget, "Reload saved credentials")
    settle(lambda: len(widget.rows) == 30)
    assert "1 / 2" in _labels(widget) and len(_row_buttons(widget, "Refresh")) == 25
    _click(widget, "Next")
    assert "2 / 2" in _labels(widget) and len(_row_buttons(widget, "Refresh")) == 5
    app.owners = []
    _click(widget, "Reload saved credentials")
    settle(lambda: not widget.rows)
    assert cb.NO_OWNED in _labels(widget)


def _identities(app, server, answers=()):
    asked = []

    def confirm(words):
        asked.append(words)
        return answers[len(asked) - 1] if len(asked) <= len(answers) else True
    widget = Identities(app, call=server, confirm=confirm)
    widget.asked = asked
    widget.resize(1300, 1000)
    widget.show()
    settle(lambda: widget.findChildren(Section))
    return widget


def test_my_character_identities(qapp):
    app, server = FakeApp(), ShareServer()
    widget = _identities(app, server, answers=[False])
    texts = _labels(widget)
    assert "Your characters · 8" in [s.button.text() for s in widget.findChildren(Section)]
    assert server.asked[0] == ("https://logs.example", "/api/v1/identity/claimable", "POST",
                               {"evidence": [{"id": "abc123", "delete_token": TOKEN}, {"id": "def456", "delete_token": TOKEN}]},
                               None)                               # the share server's uploads only
    assert [a[4] for a in server.asked[1:]] == [c["token"] for c in CLAIMS[:4]]   # each claim kept for it, by its credential
    assert cb.identity_note(3, "https://logs.example") in texts and "Not claimed yet" in texts
    assert "Needs 2 more public recordings where you are the recording player" in texts
    assert any(t.startswith("Alpha <span") and "· Zikel" in t for t in texts)
    assert "<b>Credential not accepted</b> · Unknown identity credential" in texts
    assert not _find(widget, QPushButton, lambda b: b.text() == "Claim" and not b.isEnabled()).isEnabled()   # Beta
    # a claim: proven by the uploads' credentials, its identity credential kept by the app
    _find(widget, QPushButton, lambda b: b.text() == "Claim" and b.isEnabled()).click()
    settle(lambda: any(c["name"] == "Alpha" for c in app.claims) and not widget.busy)
    claim = next(a for a in server.asked if a[1] == "/api/v1/identity/claim")
    assert claim[4] is None and claim[1:4] == ("/api/v1/identity/claim", "POST", {
        "name": "Alpha", "server": "2102", "evidence": [{"id": "abc123", "delete_token": TOKEN},
                                                        {"id": "def456", "delete_token": TOKEN}]})
    alpha = next(c for c in app.claims if c["name"] == "Alpha")
    assert alpha["token"] == "a2id_" + "alpha" * 6 and alpha["server"] == "https://logs.example" and alpha["status"] == "active"
    assert widget.said.text() == "Claim verified." and widget.message == ""           # said once
    # hidden in other uploaders' public logs
    hide = _find(widget, QCheckBox, lambda c: c.accessibleName() == cb.OPT_OUT)
    hide.setChecked(True)
    settle(lambda: server.asked[-1][1] != "/api/v1/identity/preferences" and not widget.busy
           and any(a[1] == "/api/v1/identity/preferences" for a in server.asked))
    prefs = next(a for a in server.asked if a[1] == "/api/v1/identity/preferences")
    assert prefs[2:] == ("POST", {"opt_out": True}, CLAIMS[0]["token"])
    # a release asked first; declined, then done
    _find(widget, QPushButton, lambda b: b.text() == "Release").click()
    assert widget.asked == [cb.ASK_RELEASE] and not any(a[1] == "/api/v1/identity/release" for a in server.asked)
    _find(widget, QPushButton, lambda b: b.text() == "Release").click()
    settle(lambda: not any(c["name"] == "Epsilon" for c in app.claims) and not widget.busy)
    assert any(a[1:3] == ("/api/v1/identity/release", "POST") and a[4] == CLAIMS[0]["token"] for a in server.asked)
    # a revocation appealed (at least ten characters); a credential forgotten
    fold = next(s for s in widget.findChildren(Section) if s.button.text() == "Appeal the revocation")
    fold.button.click()
    text = next(w for w in widget.findChildren(QPlainTextEdit))
    text.setPlainText("short")
    _find(widget, QPushButton, lambda b: b.text() == "Send appeal").click()
    assert widget.said.text() == cb.SHORT_APPEAL
    text.setPlainText("The account was never shared with anyone.")
    _find(widget, QPushButton, lambda b: b.text() == "Send appeal").click()
    settle(lambda: any(a[1] == "/api/v1/identity/appeal" for a in server.asked) and not widget.busy)
    appeal = next(a for a in server.asked if a[1] == "/api/v1/identity/appeal")
    assert appeal[3:] == ({"statement": "The account was never shared with anyone."}, CLAIMS[2]["token"])
    _row_buttons(widget, "Forget")[-1].click()                             # Theta's credential
    settle(lambda: not any(c["name"] == "Theta" for c in app.claims) and not widget.busy)
    assert any(c["name"] == "Iota" for c in app.claims)                    # another server's claim stays
    # no share server
    app.server["url"] = ""
    widget.load()
    settle(lambda: any(cb.NO_SHARE_SERVER == label.text() for label in widget.findChildren(QLabel)))


def test_an_upload_reads_my_uploads_and_identities_again(qapp, tmp_path):
    app = FakeApp()
    page = _page(app, store=_store(tmp_path))
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "My Uploads").click()
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "My Character Identities").click()
    settle(lambda: page.owned is not None and page.owned.table_box is not None and page.identities.findChildren(Section))
    next(b for b in page.findChildren(QPushButton) if b.accessibleName() == "Saved Logs").click()
    settle(lambda: page.queue is not None and not page.queue.busy)
    lists = app.calls.count("/api/log-ownership")
    page.queue.uploaded.emit()
    settle(lambda: app.calls.count("/api/log-ownership") >= lists + 2)    # My Uploads, and the characters' evidence


def test_the_community_views_words():
    f = {"combat_mode": "pve", "boss": "Ice Queen", "region": "", "party_size": "4"}
    assert cv.community_query(f, 2) == "page=2&limit=50&combat_mode=pve&boss=Ice+Queen&party_size=4"
    assert cv.community_path("/api/v1/logs?page=1&limit=50") == "/api/community?path=%2Fapi%2Fv1%2Flogs%3Fpage%3D1%26limit%3D50"
    assert cv.shared_page("log 1", "pve", 2) == "combat-log/shared/log%201?mode=pve&segment=2"
    assert cv.shared_page("log0001", None) == "combat-log/shared/log0001?mode="
    assert cv.patch_of("version:product:2.1") == "2.1" and cv.patch_of(None) == ""
    assert cv.pretty_enc("pve_open_world") == "open world" and cv.pretty_enc("pvp_pve_x") == "pve x" and cv.pretty_enc("") == "—"
    assert cv.pvp_type("pvp_abyss") == "Abyss" and cv.pvp_type("pvp_unknown") == "Other PvP"
    assert not cv.real_boss(" Combat 3 ") and not cv.real_boss("combat") and cv.real_boss("Combatant")
    # a page of logs as fights: generic combat out in PvE, a mini-boss out unless shown, the fight's own party and time
    pve = {"combat_mode": "pve"}
    rows, total, logs = cv.community_page({"logs": COMMUNITY_LOGS, "total": 7}, pve, False, LogServer().facets)
    assert (total, logs) == (7, 2) and [r["boss"] for r in rows] == ["Ice Queen", "Ash Wyrm"]
    queen, wyrm = rows
    assert queen["icon"] == PORTRAIT and queen["when"] == T0 + 60 and queen["party"] == 4 and queen["known"]
    assert [m["name"] for m in queen["members"]] == ["TestSorc", "TestCleric"] and queen["members"][0]["verified"]
    assert wyrm["party"] == 1 and not wyrm["known"] and wyrm["when"] == T0 - DAY and wyrm["uploader"] is None
    assert [r["boss"] for r in cv.community_page({"logs": COMMUNITY_LOGS}, pve, True, {})[0]] == [
        "Frost Hound", "Ice Queen", "Ash Wyrm"]
    hidden_by_name = [{"id": "x", "contexts": [{"boss": "Frost Hound", "boss_role": "unknown"}]}]
    assert cv.community_page({"logs": hidden_by_name}, pve, False, LogServer().facets)[0] == []
    pvp, _, _ = cv.community_page({"logs": PVP_LOGS}, {"combat_mode": "pvp"}, False, {})
    assert [r["boss"] for r in pvp] == ["Abyss Gate", "Combat 2"]          # a PvP fight named by its zone
    assert [r["boss"] for r in cv.newest_first(rows + pvp)] == ["Ice Queen", "Combat 2", "Abyss Gate", "Ash Wyrm"]
    assert cv.community_done(0, None, 1) and cv.community_done(5, 40, 1) and not cv.community_done(5, 120, 1)
    assert not cv.community_done(5, None, 9)
    assert cv.community_row(queen, "pve") == {"boss": "Ice Queen", "kind": "Hard", "party": "4", "unknown": False,
                                              "time": "2:05", "uploader": "Uploader A", "date": cb.saved_at(T0 + 60),
                                              "patch": "2.1"}
    assert cv.community_row(wyrm, "pve")["uploader"] == "Anonymous" and cv.community_row(wyrm, "pve")["patch"] == "—"
    assert cv.community_row(pvp[0], "pvp")["kind"] == "Abyss" and cv.community_row(pvp[1], "pvp")["kind"] == "Other PvP"
    assert cv.member_tip(queen["members"][0]) == "TestSorc · Sorcerer · verified"
    assert cv.member_tip(queen["members"][1]) == "TestCleric · Cleric · hidden by its player"
    assert cv.member_tip({"class": "ranger"}) == "Ranger"
    assert cv.pager_line(2, 50, 10) == "Page 2 · encounters 51–60"
    facets = LogServer().facets
    choices = cv.community_choices(facets, pve, False)
    assert [b for b, _ in choices["boss"]] == ["Ice Queen", "Ash Wyrm"]     # real bosses; a mini-boss when shown
    assert [b for b, _ in cv.community_choices(facets, pve, True)["boss"]] == ["Ice Queen", "Frost Hound", "Ash Wyrm"]
    assert [d for d, _ in choices["difficulty"]] == ["easy", "Hard", "normal"]
    assert choices["encounter_type"] == [("sanctuary", "sanctuary"), ("pve_open_world", "open world")]
    assert cv.community_choices(facets, {"combat_mode": "pvp"}, False)["encounter_type"] == [
        ("pvp_arena", "Arena"), ("pvp_abyss", "Abyss")]
    assert choices["game_patch"] == [("version:product:2.1", "2.1"), ("version:product:2.0", "2.0")]
    assert choices["party_size"] == [(4, "4"), (8, "8")]
    assert cv.pve_choices(facets, False)["encounter_type"] == choices["encounter_type"]
    assert cv.pve_choices(None, False)["boss"] == []
    # completed-run speed, boss progression, build points
    assert cv.filter_query({"boss": "Ice Queen", "region": ""}, (("limit", "100"),)) == "limit=100&boss=Ice+Queen"
    assert cv.speed_rows(LogServer().speed) == [
        {"rank": "1", "of": "of 3", "route": "Ice Queen → fh", "kind": "Sanctuary · Hard", "time": "20:34", "party": "4",
         "log": "log0001"},
        {"rank": "2", "of": "", "route": "—", "kind": "—", "time": "—", "party": "—", "log": None}]
    groups = cv.progression_rows(LogServer().progression, {}, False, facets)
    assert [(g["boss"], g["difficulty"]) for g in groups] == [("Ash Wyrm", "Hard"), ("Ice Queen", "Hard"),
                                                             ("Ice Queen", "normal")]
    assert groups[0]["rate"] == "—" and groups[0]["fastest"] == "—" and groups[0]["region"] == "—"
    assert groups[2] == {"boss": "Ice Queen", "icon": PORTRAIT, "difficulty": "normal", "region": "NA", "patch": "2.1",
                         "attempts": "10", "kills": "4", "wipes": "6", "rate": "40%", "fastest": "3:00"}
    assert [g["boss"] for g in cv.progression_rows(LogServer().progression, {"boss": "Frost Hound"}, False, facets)] == [
        "Ash Wyrm", "Frost Hound", "Ice Queen", "Ice Queen"]                # a mini-boss chosen shows
    assert cv.points_rows(LogServer().points) == [
        {"class": "Sorcerer", "skill": "110", "stigma": "20", "daevanion": "300", "ariel": "5", "total": "435", "region": "EU"},
        {"class": "Cleric", "skill": "50", "stigma": "10", "daevanion": "100", "ariel": "—", "total": "160", "region": ""}]
    assert cv.points_rows(None) == [] and cv.source_note({"note": "Runs from public logs."}) == "Runs from public logs."


def _view(kind, app, tmp_path, **kwargs):
    from aion2calc.gui.combat_community import Community
    from aion2calc.gui.pictures import Pictures
    shared = kwargs.pop("shared", None) or Community(_store(tmp_path))
    view = kind(app, shared, kwargs.pop("open_web", None), Pictures(app))
    view.resize(1300, 1000)
    view.show()
    return view


def _cells(widget):
    QCoreApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.objectName() == "tcell" and label.isVisibleTo(widget)]


def test_community_combat_logs(qapp, tmp_path):
    opened = []
    app = FakeApp()
    view = _view(CommunityLogs, app, tmp_path, open_web=opened.append)
    settle(lambda: "Uploader A" in _cells(view))
    asked = app.log_server.asked
    assert asked[0] == "/api/v1/report-facets" and asked[1] == "/api/v1/logs?page=1&limit=50&combat_mode=pve"
    assert asked[2] == "/api/v1/logs?page=2&limit=50&combat_mode=pve"   # read until the page is full or the logs end
    cells = _cells(view)
    assert ["Hard", "2:05", "Uploader A", "normal", "5:00", "Anonymous"] == [c for c in cells if c in (
        "Hard", "2:05", "Uploader A", "normal", "5:00", "Anonymous")]       # newest first
    labels = _labels(view)
    assert "Ice Queen" in labels and "Frost Hound" not in labels and "Combat 3" not in labels
    assert "<b>4</b>" in labels and any(t.startswith("<b>1</b>") and ">?<" in t for t in labels)   # a party list not captured
    assert "Page 1 · encounters 1–2" in labels
    unknown = next(label for label in view.findChildren(QLabel) if label.text().startswith("<b>1</b>"))
    assert unknown.toolTip() == cv.PARTY_UNKNOWN
    # the portrait and the class emblem the app bundles, with the player's words
    settle(lambda: any(label.toolTip() == "TestSorc · Sorcerer · verified" for label in view.findChildren(QLabel)))
    settle(lambda: any(label.pixmap() is not None and not label.pixmap().isNull() and label.width() == 22
                       for label in view.findChildren(QLabel)))
    _find(view, QPushButton, lambda b: b.text() == "view").click()
    assert opened == ["combat-log/shared/log0001?mode=pve&segment=2"]
    # a filter, the mini-bosses shown (kept), the mode, Clear
    boss = _find(view, QComboBox, lambda c: c.accessibleName() == "Boss")
    assert [boss.itemText(i) for i in range(boss.count())] == ["any", "Ice Queen", "Ash Wyrm"]
    boss.setCurrentIndex(boss.findData("Ice Queen"))
    boss.activated.emit(boss.currentIndex())
    settle(lambda: asked[-1].endswith("&boss=Ice+Queen") and "Uploader A" in _cells(view))
    _find(view, QCheckBox, lambda c: c.accessibleName() == "Show mini-bosses").setChecked(True)
    settle(lambda: "Frost Hound" in _labels(view))
    assert view.shared.store.value(cb.MINI_KEY) == "1" and view.f["boss"] == "Ice Queen"
    mode = _find(view, QComboBox, lambda c: c.accessibleName() == "Mode")
    mode.setCurrentIndex(1)
    mode.activated.emit(1)
    settle(lambda: "Abyss Gate" in _labels(view))
    assert view.f == {"combat_mode": "pvp", "boss": "", "encounter_type": ""} and "SKIRMISH" in _labels(view)
    assert "Abyss" in _cells(view) and "Other PvP" in _cells(view) and "6" in [t.strip("<b>/") for t in _labels(view)]
    assert not [c for c in view.findChildren(QComboBox) if c.accessibleName() == "Boss" and c.isVisibleTo(view)]
    _find(view, QPushButton, lambda b: b.text() == "Clear").click()
    settle(lambda: "Abyss Gate" in _labels(view))
    assert view.f == {"combat_mode": "pvp"}
    # the next page of fifty
    app.log_server.many = 60
    mode = _find(view, QComboBox, lambda c: c.accessibleName() == "Mode")
    mode.setCurrentIndex(0)
    mode.activated.emit(0)
    settle(lambda: "Page 1 · encounters 1–50" in _labels(view))
    _find(view, QPushButton, lambda b: b.text() == "Next →").click()
    settle(lambda: "Page 2 · encounters 51–63" in _labels(view))
    assert not _find(view, QPushButton, lambda b: b.text() == "Next →").isEnabled()
    _find(view, QPushButton, lambda b: b.text() == "← Prev").click()
    settle(lambda: "Page 1 · encounters 1–50" in _labels(view))
    # an answer to a question asked before the latest is let go; a refusal is said
    before = list(_cells(view))
    view._replied("logs:1", {"logs": PVP_LOGS})
    assert _cells(view) == before
    app.log_server.refusal = "RuntimeError: Community server (503): busy"
    view.refresh()
    settle(lambda: "RuntimeError: Community server (503): busy" in _labels(view))


def test_run_speed_boss_progression_and_build_points(qapp, tmp_path):
    opened = []
    app = FakeApp()
    speed = _view(RunSpeed, app, tmp_path, open_web=opened.append)
    settle(lambda: "Ice Queen → fh" in _cells(speed))
    assert app.log_server.asked[-1] == "/api/v1/run-leaderboard?limit=100"
    cells = _cells(speed)
    assert ["Sanctuary · Hard", "20:34", "4", "—"] == [c for c in cells if c in ("Sanctuary · Hard", "20:34", "4", "—")][:4]
    assert "1 <span style='color: #9aa3b5;'>of 3</span>" in _labels(speed) and "Runs from public logs." in _labels(speed)
    _find(speed, QPushButton, lambda b: b.text() == "view").click()
    assert opened == ["combat-log/shared/log0001?mode=pve"]
    boss = _find(speed, QComboBox, lambda c: c.accessibleName() == "Boss")
    boss.setCurrentIndex(boss.findData("Ash Wyrm"))
    boss.activated.emit(boss.currentIndex())
    settle(lambda: cv.NO_SPEED_MATCH in _labels(speed))
    assert app.log_server.asked[-1] == "/api/v1/run-leaderboard?limit=100&boss=Ash+Wyrm"
    progression = _view(BossProgression, app, tmp_path)
    settle(lambda: "40%" in _cells(progression))
    cells = _cells(progression)
    assert cells.count("Ice Queen") == 0 and "3:00" in cells and "6:40" in cells and "20%" in cells   # bosses in cells
    assert [label.text() for label in progression.findChildren(QLabel) if label.text() in ("Ash Wyrm", "Ice Queen")] == [
        "Ash Wyrm", "Ice Queen", "Ice Queen"]
    assert app.log_server.asked[-1] == "/api/v1/encounter-progression"
    region = _find(progression, QComboBox, lambda c: c.accessibleName() == "Region")
    region.setCurrentIndex(region.findData("EU"))
    region.activated.emit(region.currentIndex())
    settle(lambda: app.log_server.asked[-1] == "/api/v1/encounter-progression?region=EU")
    points = _view(BuildPoints, app, tmp_path)
    settle(lambda: "Sorcerer" in _cells(points))
    assert cv.POINTS_NOTE in _labels(points) and "435" in _cells(points) and "Cleric" in _cells(points)
    app.log_server.refusal = "RuntimeError: Community server (500): down"
    points.refresh()
    settle(lambda: "RuntimeError: Community server (500): down" in _labels(points))
    app.log_server.refusal = None
    app.log_server.points = {"observations": []}
    points.refresh()
    settle(lambda: cv.NO_POINTS in _labels(points))


def test_the_personal_records_words():
    assert cr.build_label("version:product:2.1.0.3.9") == "Product version 2.1.0.3"
    assert cr.build_label("build:steam:123:456 / build:purple:A2_LIVE_PURPLE:789") == (
        "Legacy build 456 · Steam / Legacy build 789 · PURPLE")
    assert cr.n(1234.5) == "1,235" and cr.n(None) == "0" and cr.value_or_unavailable(None) == "Unavailable"
    assert cr.filter_name("game_patch") == "game version" and cr.filter_name("party_size") == "party size"
    facets = LogServer().facets
    assert cr.filter_choices("metric", facets) == [("dps", "dps"), ("hps", "hps"), ("dtps", "dtps")]
    assert cr.filter_choices("encounter_type", facets)[:2] == [("", "All"), ("unknown", "Unknown")]
    assert cr.filter_choices("game_patch", facets) == [("", "All"), ("version:product:2.1", "Product version 2.1"),
                                                       ("version:product:2.0", "Product version 2.0")]
    assert cr.filter_choices("party_size", facets) == [("", "All"), ("4", "4"), ("8", "8")]
    query = {"combat_mode": "pve", "metric": "dps", "game_patch": "v", "encounter_type": "sanctuary"}
    assert cr.query_after(query, "encounter_type", "pvp_arena")["combat_mode"] == "pvp"   # a type sets its mode
    assert cr.query_after(query, "combat_mode", "pvp")["encounter_type"] == ""            # a mode clears the type
    assert cr.params({"combat_mode": "pve", "boss": "", "metric": "dps"}) == "combat_mode=pve&metric=dps"
    groups = cr.server_groups()
    assert groups[0][0] == "North America · Elyos" and groups[1][0] == "North America · Asmodian"
    assert ("2102", "Zikel") in groups[1][1] and [g for g, _ in groups].count("Europe · Elyos") == 1
    assert cr.class_colour("Sorcerer", {"colors": {"sorcerer": "#123456"}}) == "#123456"
    assert cr.class_colour("cleric", {}) == "#ffffff" and cr.class_colour("cleric", {"enabled": False}) == cr.GOLD
    assert cr.class_colour("ranger", {"colors": {"ranger": "red"}}) == cr.GOLD and cr.class_colour(None, {}) == cr.GOLD
    assert cr.local_time(None) == "Timestamp unavailable" and cr.age(30) == "Less than a minute ago"
    assert cr.age(150) == "2 minutes ago" and cr.age(7200) == "2 hours ago" and cr.age(3 * DAY) == "3 days ago"
    assert cr.age("soon") == "Age unavailable"
    # the recorded boss defeats
    assert cr.bosses_path({"game_patch": "v1", "region": "NA", "boss": "x"}) == "/api/v1/boss-status?game_patch=v1&region=NA"
    assert [g["npc_id"] for g in cr.boss_groups(BOSS_STATUS, "2001")] == ["2001"]
    assert len(cr.boss_groups(BOSS_STATUS, " ")) == 2 and cr.boss_groups(BOSS_STATUS, "frost") == []
    assert cr.bosses_message(BOSS_STATUS, 2) == (f"2 displayed boss/context groups. Snapshot {cb.saved_at(T0)} (local time)."
                                                 " Results capped; search filters only the displayed groups.")
    queen, nameless = (cr.boss_row(g) for g in BOSS_STATUS["groups"])
    assert queen == {"boss": "Ice Queen", "npc": "2001", "region": "NA", "build": "Product version 2.1", "place": "300 / 7",
                     "defeated": cb.saved_at(T0 - 3600), "age": "2 hours ago", "basis": "server clock",
                     "observations": "3 / 5", "engaged": "4 engaged", "roster": "6 recorded roster members (complete)",
                     "log": "log0001", "source": "Open log · encounter 3"}
    assert (nameless["boss"], nameless["npc"], nameless["region"], nameless["place"]) == (
        "Unnamed boss", "ID unavailable", "Unknown region", "Unknown / Unknown")
    assert nameless["log"] is None and nameless["source"] == "Source unavailable"
    assert nameless["roster"] == "Party roster unavailable" and nameless["build"] == "Unknown game version"
    # class performance
    assert cr.performance_note(PERFORMANCE) == "Recorded rates. 12 samples; 1 excluded for missing metadata."
    buckets = cr.performance_buckets(PERFORMANCE)
    assert [title for title, _ in buckets] == [
        "Ice Queen · npc:2001 · sanctuary · Product version 2.1.0.3 · Hard · Party 4 · Instance 7",
        "Ash Wyrm ·  ·  ·  ·  · Party unknown · Instance unknown"]
    assert [g["class"] for g in buckets[0][1]] == ["sorcerer", "cleric"]          # highest median first
    sorc, cleric = (cr.performance_row(g) for g in buckets[0][1])
    assert sorc["coverage"] == "Sufficient sample" and sorc["parses"] == "9 · 6" and sorc["range"] == "5,000 – 9,000"
    assert cleric["coverage"] == "Too few parses." and cleric["median"] == "2,500"
    assert cr.performance_row(buckets[1][1][0])["coverage"] == "Coverage unavailable"
    assert cr.performance_row(buckets[1][1][0])["parses"] == "1 · Unavailable"
    assert sorc["tip"] == "Min 5,000; lower quartile 6,000; median 7,000; upper quartile 8,000; max 9,000; 9 parses"
    assert cr.bucket_maximum(buckets[0][1]) == 9000 and cr.bucket_maximum([]) == 1
    # personal records and attempts
    identity = {"name": "TestSorc", "server": "2102", "character_id": ""}
    assert cr.records_query({"combat_mode": "pve", "metric": "dps"}, identity, 2) == (
        "combat_mode=pve&metric=dps&name=TestSorc&server=2102&character_id=&page=2")
    assert cr.record_rows(RECORDS, "DPS") == [
        {"boss": "Ice Queen", "log": "log0001", "class": "sorcerer", "best": "41,235", "attempts": "3",
         "context": "Sanctuary raids · Product version 2.1 · Hard · party 4 · instance 7"}]
    mine, hidden = cr.history_rows(RECORDS)
    assert (mine["server"], mine["verified"], mine["ranking"], mine["recorded"]) == ("Zikel", True, "Eligible", cb.saved_at(T0))
    assert (hidden["server"], hidden["pseudonym"], hidden["score"], hidden["ranking"], hidden["recorded"]) == (
        "99999", True, "900", "Unranked / unverified", "—")
    assert cr.records_pager(RECORDS, 1) == {"line": "Page 1 · 120 attempts", "previous": False, "next": True}
    assert cr.records_pager(RECORDS, 3)["next"] is False
    # consistency and trends
    assert cr.consistency_note(CONSISTENCY) == (
        "Matched recordings. TestSorc on Zikel. 2 samples excluded for missing cohort/metric evidence.")
    group = cr.consistency_group(CONSISTENCY["groups"][0], "DPS")
    assert group["title"] == "Ice Queen · sorcerer · Product version 2.1 · Hard · party 4 · instance 7 · 3 recordings"
    assert group["spread"] == ("Median 40,000 DPS · range 30,000–50,000 · relative variation 12.3% · median absolute "
                               "deviation 5,000 · standard deviation 6,000")
    assert group["trend"] == ("Recent 5 median Unavailable · preceding 5 Unavailable · change Unavailable · At least 5 "
                              "uncapped recordings required for variation. · At least 10 uncapped recordings required for trend.")
    assert [r["deaths"] for r in group["rows"]] == ["Unavailable (no markers)", "1", "0"]
    assert [r["open"] for r in group["rows"]] == ["Open encounter 1", "Open encounter 3", "Open encounter 4"]
    assert [(x, round(y, 1)) for x, y, _ in group["points"]] == [(0.0, 46.0), (300.0, 10.0), (600.0, 28.0)]
    assert cr.consistency_group({**CONSISTENCY["groups"][0], "change_pct": 4.25}, "DPS")["trend"].startswith(
        "Recent 5 median Unavailable · preceding 5 Unavailable · change +4.3%")
    assert cr.trend_points([{"score": 5}])[0][:2] == (300.0, 10.0)


def test_personal_records(qapp, tmp_path):
    from aion2calc.gui.combat_community import Community
    opened = []
    app = FakeApp()
    view = PersonalRecords(app, Community(_store(tmp_path)), opened.append)
    view.resize(1300, 1400)
    view.show()
    settle(lambda: view.findChildren(BoxPlot))
    asked = app.log_server.asked
    assert asked[0] == "/api/v1/report-facets"
    assert asked[1] == "/api/v1/performance?combat_mode=pve&metric=dps&game_patch=version%3Aproduct%3A2.1"
    patch = _find(view, QComboBox, lambda c: c.accessibleName() == "game version")
    assert patch.currentData() == "version:product:2.1"                    # the latest submitted version first
    texts = _labels(view)
    assert cr.RECORDS_NOTE in texts and "Recorded rates. 12 samples; 1 excluded for missing metadata." in texts
    assert "Ice Queen · npc:2001 · sanctuary · Product version 2.1.0.3 · Hard · Party 4 · Instance 7" in texts
    plots = view.findChildren(BoxPlot)
    assert len(plots) == 3 and plots[0].colour.name() == "#123456"        # the user's palette for the sorcerer
    assert plots[0].toolTip().startswith("Min 5,000") and "Too few parses." in _cells(view)
    # the recorded boss defeats: read once opened, searched, read again
    assert not any(p.startswith("/api/v1/boss-status") for p in asked)
    view.bosses.button.click()
    settle(lambda: "Ice Queen" in [label.text().split("<br>")[0] for label in view.findChildren(QLabel)])
    assert asked[-1] == "/api/v1/boss-status?game_patch=version%3Aproduct%3A2.1"
    assert view.boss_said.text() == cr.bosses_message(BOSS_STATUS, 2) and cr.BOSSES_FOOT in _labels(view)
    view.boss_search.setText("2001")
    assert view.boss_said.text().startswith("1 displayed boss/context groups.")
    _find(view, QPushButton, lambda b: b.text() == "Open log · encounter 3").click()
    assert opened == ["combat-log/shared/log0001?mode=pve"]
    # PvP: no boss defeats
    mode = _find(view, QComboBox, lambda c: c.accessibleName() == "combat mode")
    mode.setCurrentIndex(mode.findData("pvp"))
    mode.activated.emit(mode.currentIndex())
    settle(lambda: asked[-1].startswith("/api/v1/performance?combat_mode=pvp"))
    assert not view.bosses.isVisibleTo(view)
    # a character's records, attempts, consistency and trends
    view.name.setText("TestSorc")
    view.server.setCurrentIndex(view.server.findData("2102"))
    _find(view, QPushButton, lambda b: b.text() == "Find records").click()
    settle(lambda: view.findChildren(TrendChart) and "Page 1 · 120 attempts" in _labels(view))
    query = "combat_mode=pvp&metric=dps&game_patch=version%3Aproduct%3A2.1&name=TestSorc&server=2102&character_id=&page=1"
    assert "/api/v1/consistency?" + query in asked and "/api/v1/records?" + query in asked
    assert view.record_note.text() == "TestSorc on Zikel. Public submissions only."
    assert "Sanctuary raids · Product version 2.1 · Hard · party 4 · instance 7" in _cells(view)
    assert any("TestSorc" in t and "✓" in t and "Zikel" in t for t in _labels(view))
    assert view.record_next.isEnabled() and not view.record_previous.isEnabled()
    fold = next(s for s in view.findChildren(Section) if s.button.text().startswith("Ice Queen · sorcerer"))
    fold.button.click()
    assert view.findChildren(TrendChart)[0].points[1][2] == f"{cb.saved_at(T0 - DAY)}: 50,000"
    _find(view, QPushButton, lambda b: b.text() == "Open encounter 3").click()
    assert opened[-1] == "combat-log/shared/log0001?mode=pvp"
    view.record_next.click()
    settle(lambda: asked[-1].endswith("page=2"))
    # a filter with a character searched reads the records again; refusals are said
    app.log_server.refusal = "RuntimeError: Community server (503): busy"
    metric = _find(view, QComboBox, lambda c: c.accessibleName() == "metric")
    metric.setCurrentIndex(metric.findData("hps"))
    metric.activated.emit(metric.currentIndex())
    settle(lambda: view.record_note.text() == "RuntimeError: Community server (503): busy")
    assert "RuntimeError: Community server (503): busy" in _labels(view)
    assert "Consistency unavailable: RuntimeError: Community server (503): busy" in _labels(view)


def test_the_featured_words():
    assert [cf.n0(51234.5), cf.n0(None), cf.n0("12"), cf.n0(True), cf.n0(float("nan"))] == ["51,235", "—", "12", "—", "—"]
    assert [cf.pct(12.345), cf.pct(None), cf.pct("x")] == ["12.3%", "—", "—"]
    assert [cf.clock(754), cf.clock(3725), cf.clock(59.6), cf.clock(None)] == ["12:34", "1:02:05", "1:00", "—"]
    assert cf.when(T0) == "2026-11-01 12:00" and cf.when(0) == cf.when(None) == cf.when("soon") == "—"
    assert [cf.world(2102), cf.world(None), cf.world(99999)] == ["Zikel", "", "99999"]
    assert [cf.region("nae"), cf.region("xx"), cf.region(None)] == ["NA", "XX", ""]
    assert cf.patch("version:product:2.1") == "2.1" and cf.patch(None) == ""
    assert cf.npc_code("npc:2001") == "2001" and cf.npc_code("boss") is None and cf.npc_code(None) is None
    assert cf.valid_id(FE_ID) and not any(cf.valid_id(x) for x in ("fe_xyz", None, FE_ID + "0", "FE_0123456789"))
    assert cf.log_page("log 1", 3) == "combat-log/shared/log%201?segment=3"
    assert cf.log_page("log0001", 2.0) == "combat-log/shared/log0001?segment=2"
    assert cf.log_page("log0001") == cf.log_page("log0001", True) == cf.log_page("log0001", 1.5) == "combat-log/shared/log0001"
    # teams, characters and how far a team got
    assert cf.team_view(TEAM_A) == {"name": "Night Watch", "sub": "Zikel · NA", "legion": False, "kind": "party",
                                    "tip": "TestSorc, TestCleric", "members": [{"name": "TestSorc", "class": "sorcerer"},
                                                                               {"name": "TestCleric", "class": "cleric"}]}
    legion, across = cf.team_view(TEAM_B), cf.team_view(TEAM_C)
    assert (legion["legion"], legion["tip"], legion["sub"]) == (True, "Legion", "EU")
    assert across["sub"] == "several servers" and cf.team_view(None)["name"] == ""
    assert cf.player_view({"name": "TestSorc", "class": "sorcerer", "server": 2102}) == {
        "name": "TestSorc", "class": "sorcerer", "sub": "Zikel"}
    assert cf.progress_text({"killed": 1, "phases": 2, "best_hp": 12.34}) == "1/2 · 12.3%"
    assert cf.progress_text({"complete": True, "killed": 2, "phases": 2, "best_hp": 0}) == "2/2"
    assert cf.progress_text({}) == "—/—"                                    # not "undefined/undefined"
    assert cf.featured_page("nope", "speed") == ("race", "dps") and cf.featured_page("rankings", "speed") == ("rankings", "speed")
    assert cf.featured_page("statistics", "hps") == ("statistics", "hps")
    assert cf.featured_page("statistics", "speed") == ("statistics", "dps")
    # the landing cards
    cards = cf.zone_cards(FEATURED)
    assert [c["title"] for c in cards] == ["Progress", "Speed", "Execution", "All Stars (DPS)", "All Stars (Tank)",
                                           "All Stars (Support)", "DPS", "Tank Damage", "Support Damage"]
    assert [c["more"] for c in cards] == [("progress", None), ("rankings", "speed"), ("progress", None)] + [
        ("rankings", None)] * 3 + [("statistics", None)] * 3
    assert [v for _kind, _who, v in cards[0]["rows"]] == ["Complete", "1/2 · 12.3%"]
    assert [v for _kind, _who, v in cards[1]["rows"]] == ["12:34"]
    assert [v for _kind, _who, v in cards[2]["rows"]] == ["1 death · 5:00", "— deaths · —"]
    assert cards[3]["rows"] == [("player", {"name": "TestSorc", "class": "sorcerer", "sub": "Zikel"}, "187.3")]
    assert cards[4]["rows"] == [] and cards[5]["rows"][0][2] == "—"       # no points: none made up
    assert cards[6]["rows"] == [("class", {"class": "sorcerer", "name": "Sorcerer"}, "51,235")]
    assert cf.zone_note(FEATURED).startswith("3 teams · 1 cleared · 42 recorded pulls. Speed is a team's fastest")
    assert cf.featured_list({"featured": [FEATURED, "x"]}) == [FEATURED] and cf.featured_list(None) == []
    assert cf.note({"note": "Public logs only."}) == "Public logs only." and cf.note({}) == cf.note(None) == ""
    started = cf.when(T0 - 7 * DAY)
    assert cf.header_line(FEATURED) == f"Ice Queen · Hard · race from {started}"
    assert cf.header_line({**FEATURED, "ends_at": T0}) == f"Ice Queen · Hard · race from {started} to 2026-11-01 12:00"
    # each page's question
    state = {"page": 2, "boss": "npc:2001", "region": "eu", "metric": "dps", "cls": "sorcerer"}
    base = f"/api/v1/featured/{FE_ID}/"
    assert cf.featured_path(FE_ID, "race", state) == base + "race?region=eu"
    assert cf.featured_path(FE_ID, "race", {**state, "region": ""}) == base + "race"
    assert cf.featured_path(FE_ID, "progress", state) == base + "progress?page=2&region=eu"
    assert cf.featured_path(FE_ID, "reports", state) == base + "reports?page=2"
    assert cf.featured_path(FE_ID, "rankings", state) == base + "rankings?metric=dps&boss=npc%3A2001&class=sorcerer&region=eu"
    assert cf.featured_path(FE_ID, "rankings", {**state, "metric": "speed"}) == base + "rankings?metric=speed&region=eu"
    assert cf.featured_path(FE_ID, "statistics", {**state, "metric": "hps", "region": ""}) == (
        base + "statistics?metric=hps&boss=npc%3A2001")
    assert cf.pager({"total": 120, "page": 2}, 50) == {"page": 2, "pages": 3, "words": "Page 2 of 3", "previous": True,
                                                       "next": True}
    assert cf.pager({"total": 30, "page": 1}, 30) is None and cf.pager(None, 50) is None
    assert cf.pager({"total": 31, "page": 2}, None)["next"] is False     # thirty a page when the server names no limit
    assert cf.regions_offered({"regions": ["na", "eu"]}) == [("na", "NA"), ("eu", "EU")]
    assert cf.boss_choices(FEATURED) == [("npc:2001", "Ice Queen"), ("npc:2002", "Frost Hound")]
    # the race
    r = cf.race(RACE, FEATURED)
    assert [p["title"] for p in r["phases"]] == ["Phase 1", "Phase 2"] and r["fills"] == [100, 100] and r["done_fill"] == 100
    assert r["stats"][0] == {"line": "3 reached · 1 killed", "first": f"First: Night Watch, {cf.when(T0 - 2 * DAY)}"}
    assert r["stats"][1]["first"] == "" and r["complete"] == "1 complete" and r["label"] == "2 phases: a team has completed it"
    assert r["lists"] == [[{"rank": "3.", "name": "Drifters", "small": "pulling"}],
                          [{"rank": "2.", "name": "Old Guard", "small": "12.3%"}]]
    assert r["done"] == [{"rank": "1.", "name": "Night Watch", "small": cf.when(T0 - DAY)}]
    a, b, c = r["closers"]
    assert (a["state"], a["detail"], a["progress"], a["pulls"], a["log"]) == ("Complete!", cf.when(T0 - DAY), "2/2",
                                                                              "Pulls: 12", "log0001")
    assert [m["name"] for m in a["members"]] == ["TestSorc", "TestCleric"] and b["members"] == [] and b["team"]["legion"]
    assert (b["state"], b["detail"], c["detail"]) == ("Working on", "Frost Hound · 12.3%", "Ice Queen")
    racing = cf.race({**RACE, "teams": RACE["teams"][1:]}, FEATURED)      # no team has finished
    assert racing["fills"] == [100, 24] and racing["done_fill"] == 0 and racing["done"] == []
    assert racing["label"] == "2 phases: the leading team is 62% of the way"
    # progress, kills, reports, rankings and statistics
    rows = cf.progress_rows(FE_PROGRESS, FEATURED)
    assert [(r["rank"], r["progress"], r["pulls"]) for r in rows] == [("1", "2/2", "12"), ("2", "1/2 · 12.3%", "20")]
    assert [k[2] for k in rows[0]["killed"]] == ["Ice Queen", "Frost Hound"]   # a phase the encounter hasn't is left out
    kill = cf.kill_rows(FE_PROGRESS)[0]
    assert (kill["patch"], kill["composition"], kill["time"], kill["deaths"], kill["log"]) == (
        "2.1", [("sorcerer", "1"), ("cleric", "1")], "12:34", "1", "log0001")
    first, second = cf.report_rows(FE_REPORTS)
    assert (first["title"], first["uploader"], first["bosses"], first["time"]) == (
        "Frost Spire clear", "Uploader A", "Ice Queen, Frost Hound", "1:02:05")
    assert [p["name"] for p in first["players"]] == ["TestSorc", "TestCleric"]
    assert (second["title"], second["uploader"], second["time"], second["players"]) == ("Ice Queen", "Anonymous", "—", [])
    assert [(r["time"], r["patch"]) for r in cf.speed_rows(FE_SPEED)] == [("12:34", "2.1")]
    ranked, unranked = cf.ranking_rows(FE_RANKED)
    assert (ranked["rank"], ranked["score"], ranked["parse"], ranked["time"], ranked["segment"]) == ("1", "51,235", "99", "3:05", 3)
    assert (unranked["rank"], unranked["score"], unranked["parse"], unranked["time"], unranked["at"]) == ("2", "—", "—", "—", "—")
    assert cf.ranking_columns("hps")[3] == "HPS" and cf.ranking_columns("dps")[3] == "DPS"
    assert cf.ranking_caption(FEATURED, {"metric": "hps", "boss": "npc:2002"}) == "Healing per second · Frost Hound"
    assert cf.ranking_caption(FEATURED, {"metric": "dps", "boss": "npc:9"}) == "Damage per second · Ice Queen"
    assert cf.statistics_caption("hps") == "Recorded healing per second by class"
    rows, top = cf.statistics_rows(FE_STATISTICS)
    assert top == 80000 and (rows[0]["box"], rows[0]["mark"], rows[0]["role"], rows[0]["median"]) == (
        (0.5, 0.25), 0.625, "DPS", "50,000")
    assert (rows[1]["box"], rows[1]["mark"], rows[1]["role"], rows[1]["p25"]) == (None, 0.25, "Support", "—")  # no box drawn


def _featured(app, **kwargs):
    """Combat Logs with one featured encounter, its cards drawn and their pictures in."""
    app.log_server.featured = [json.loads(json.dumps(FEATURED))]
    page = _page(app, **kwargs)
    settle(lambda: "Frost Spire" in _labels(page.featured) and any(
        not p.pixmap().isNull() for p in page.featured.findChildren(_Painted)) and not page.featured.soon.isActive())
    return page


def _drawn(widget, words):
    """``words`` shown, and the pictures that came meanwhile drawn too."""
    settle(lambda: words in _labels(widget) and not widget.soon.isActive())


def _nav(widget, words):
    _find(widget, QPushButton, lambda b: b.objectName() == "feNav" and b.text() == words).click()


def _choose(widget, name, value):
    pick = _find(widget, QComboBox, lambda c: c.accessibleName() == name)
    pick.setCurrentIndex(pick.findData(value))
    pick.activated.emit(pick.currentIndex())


def test_the_featured_encounters_cards(qapp):
    from PySide6.QtWidgets import QFrame
    from aion2calc.gui.combat_featured_page import FeaturedSection
    app = FakeApp()
    page = _featured(app)
    section = page.featured
    assert page.frame.body.indexOf(section) == 0                          # above the views
    texts = _labels(section)
    assert cf.HEADING in texts and "Ice Queen · Hard" in texts and "Featured by the operator." in texts
    assert cf.zone_note(FEATURED) in texts
    assert all(t in texts for t in ("Progress", "Speed", "Execution", "All Stars (DPS)", "All Stars (Support)", "Tank Damage"))
    assert all(t in texts for t in ("Complete", "1/2 · 12.3%", "12:34", "1 death · 5:00", "— deaths · —", "187.3", "51,235"))
    assert texts.count(cf.NO_RECORDS) == 3                                # the tanks' all stars, the tanks' and supports' damage
    team = _find(section, QLabel, lambda label: label.text() == "Night Watch")
    assert (team.objectName(), team.toolTip()) == ("feTeam", "TestSorc, TestCleric")
    legion = _find(section, QLabel, lambda label: label.text() == "Old Guard")
    assert (legion.objectName(), legion.toolTip()) == ("feLegion", "Legion")
    assert "<span style='color: #123456;'>TestSorc</span>" in texts       # the user's colour for a sorcerer
    assert "<span style='color: #e8cf8e;'>TestCleric</span>" not in texts and "<span style='color: #ffffff;'>TestCleric</span>" in texts
    medals = [label.objectName() for label in section.findChildren(QLabel) if label.objectName().startswith("feMedal")]
    assert medals.count("feMedal1") == 6 and medals.count("feMedal2") == 2
    # View more… opens a page in place of the views; Back returns to them, the cards read again
    speed = _find(section, QFrame, lambda f: f.objectName() == "feCard" and f.accessibleName() == "Speed")
    _find(speed, QPushButton, lambda b: b.text() == cf.MORE).click()
    fp = page.featured_page
    _drawn(fp, cf.SPEED_CAPTION)
    asked = app.log_server.asked
    assert asked.index(f"/api/v1/featured/{FE_ID}") < asked.index(f"/api/v1/featured/{FE_ID}/rankings?metric=speed")
    assert not page.frame.isVisibleTo(page) and page.featured_box.isVisibleTo(page)
    assert _find(fp, QComboBox, lambda c: c.accessibleName() == "Ranking").currentData() == "speed"
    assert not [c for c in fp.findChildren(QComboBox) if c.accessibleName() in ("Boss", "Class") and c.isVisibleTo(fp)]
    count = asked.count("/api/v1/featured")
    old = _find(section, QFrame, lambda f: f.objectName() == "feZone")
    _click(page, cf.BACK)
    assert page.frame.isVisibleTo(page) and not page.featured_box.isVisibleTo(page)
    settle(lambda: asked.count("/api/v1/featured") == count + 1)          # as #/combat reads it
    settle(lambda: any(f is not old and f.isVisibleTo(section) for f in section.findChildren(QFrame)
                       if f.objectName() == "feZone"))                     # and drawn again
    _nav(section, "Statistics")
    _drawn(page.featured_page, "Recorded damage per second by class")
    # nothing featured, or no server: nothing drawn
    quiet = FakeApp()
    empty = FeaturedSection(quiet, lambda *_: None)
    settle(lambda: empty.answer is not None)
    assert not empty.isVisible() and cf.featured_list(empty.answer) == []
    quiet.log_server.refusal = "RuntimeError: Community server (503): busy"
    refused = FeaturedSection(quiet, lambda *_: None)
    seen = []
    refused.requests.failed.connect(lambda name, why: seen.append(why))
    settle(lambda: seen)
    QCoreApplication.processEvents()
    assert seen == ["RuntimeError: Community server (503): busy"] and refused.answer is None and not refused.isVisible()


def test_a_featured_encounters_pages(qapp):
    opened = []
    app = FakeApp()
    page = _featured(app, open_web=opened.append)
    asked = app.log_server.asked
    base = f"/api/v1/featured/{FE_ID}"
    # the race summary
    _nav(page.featured, "Race Summary")
    fp = page.featured_page
    _drawn(fp, cf.CLOSER)
    settle(lambda: any(c.art is not None for c in fp.findChildren(_Closer)) and not fp.soon.isActive())
    assert asked.index(base) < asked.index(base + "/race")
    texts = _labels(fp)
    assert "Frost Spire" in texts and cf.header_line(FEATURED) in texts
    assert [b.text() for b in fp.findChildren(QPushButton) if b.objectName() == "feNav" and b.property("current")] == [
        "Race Summary"]
    assert any(not p.pixmap().isNull() for p in fp.findChildren(_Painted) if p.width() == 72)   # the encounter's portrait
    assert [s.fill for s in fp.findChildren(_Segment) if s.isVisibleTo(fp)] == [100, 100, 100]
    assert f"3 reached · 1 killed<br>First: Night Watch, {cf.when(T0 - 2 * DAY)}" in texts and "1 complete" in texts
    assert "Complete!" in texts and "Public logs only." in texts
    assert any("Drifters" in t and "pulling" in t for t in texts) and any("Old Guard" in t and "12.3%" in t for t in texts)
    closers = [c for c in fp.findChildren(_Closer) if c.isVisibleTo(fp)]
    assert [c.accessibleName() for c in closers] == ["Night Watch", "Old Guard", "Drifters"]
    assert all(c.art is not None for c in closers)                         # the boss faint behind each
    assert "NIGHT WATCH" in texts and "COMPLETE!" in texts and "WORKING ON" in texts and "Frost Hound · 12.3%" in texts
    assert ("<span style='color: #123456;'>TestSorc</span>, <span style='color: #ffffff;'>TestCleric</span>") in texts
    assert "Legion" in texts
    _click(fp, cf.OPEN_LOG)
    assert opened == ["combat-log/shared/log0001"]
    assert len([b for b in fp.findChildren(QPushButton) if b.text() == cf.OPEN_LOG and b.isVisibleTo(fp)]) == 1  # no log, no link
    _choose(fp, "Region", "eu")
    settle(lambda: base + "/race?region=eu" in asked)
    # progress: the teams, the final-boss kills, the pager and a region
    _nav(fp, "Progress")
    _drawn(fp, cf.PROGRESS_CAPTION)
    assert base + "/progress?page=1" in asked and cf.KILLS_CAPTION in _labels(fp)
    cells = _cells(fp)
    assert all(c in cells for c in ("1/2 · 12.3%", "2/2", "2.1", "12:34", f"{cf.when(T0)}"))
    assert sorted(p.toolTip() for p in fp.findChildren(_Painted) if p.width() == 24 and p.isVisibleTo(fp)) == [
        "Frost Hound", "Ice Queen", "Ice Queen"]
    assert "Page 1 of 3" in _labels(fp)
    _click(fp, "Next")
    settle(lambda: base + "/progress?page=2" in asked)
    _drawn(fp, "Page 1 of 3")
    _choose(fp, "Region", "na")
    settle(lambda: base + "/progress?page=1&region=na" in asked)        # a region starts at the first page
    _drawn(fp, cf.KILLS_CAPTION)
    _click(fp, "Log")
    assert opened[-1] == "combat-log/shared/log0001"
    # all reports
    _nav(fp, "All Reports")
    _drawn(fp, cf.REPORTS_CAPTION)
    assert base + "/reports?page=1" in asked
    texts = _labels(fp)
    assert all(t in texts for t in ("Uploader A", "Anonymous", "Ice Queen, Frost Hound", "1:02:05", "Page 1 of 2"))
    _find(fp, QLabel, lambda label: "Frost Spire clear" in label.text()).linkActivated.emit("open")
    assert opened[-1] == "combat-log/shared/log0001"
    # rankings: a boss, a class, then the teams by speed
    _nav(fp, "Rankings")
    _drawn(fp, "Damage per second · Ice Queen")
    assert base + "/rankings?metric=dps&boss=npc%3A2001" in asked
    assert all(c in _cells(fp) for c in ("51,235", "99", "3:05"))
    _click(fp, "Log")
    assert opened[-1] == "combat-log/shared/log0001?segment=3"
    _choose(fp, "Class", "sorcerer")
    settle(lambda: base + "/rankings?metric=dps&boss=npc%3A2001&class=sorcerer" in asked)
    _drawn(fp, "Damage per second · Ice Queen")
    _choose(fp, "Boss", "npc:2002")
    _drawn(fp, "Damage per second · Frost Hound")
    assert base + "/rankings?metric=dps&boss=npc%3A2002&class=sorcerer" in asked
    _choose(fp, "Ranking", "speed")
    _drawn(fp, cf.SPEED_CAPTION)
    assert base + "/rankings?metric=speed" in asked
    # statistics: each class's spread in its colour
    _nav(fp, "Statistics")
    _drawn(fp, "Recorded damage per second by class")
    assert base + "/statistics?metric=dps&boss=npc%3A2001" in asked and cf.ROLES_NOTE in _labels(fp)
    spreads = [s for s in fp.findChildren(_Spread) if s.isVisibleTo(fp)]
    assert [(s.box, s.mark) for s in spreads] == [((0.5, 0.25), 0.625), (None, 0.25)]
    assert spreads[0].colour.name() == "#123456"
    # a view the server refuses keeps the head; an encounter refused says only why
    app.log_server.refusal = "RuntimeError: Community server (503): busy"
    _choose(fp, "Rate", "hps")
    _drawn(fp, "RuntimeError: Community server (503): busy")
    assert "Frost Spire" in _labels(fp)
    page.open_featured(FE_ID, "progress")
    settle(lambda: "RuntimeError: Community server (503): busy" in _labels(fp) and not fp.head.isVisibleTo(fp))
    app.log_server.refusal = None
    # an address that is no featured encounter asks nothing
    count = len(asked)
    page.open_featured("fe_nope")
    assert cf.NO_ADDRESS in _labels(fp) and len(asked) == count
    # a page left before it answers: only the one opened last is drawn
    races = asked.count(base + "/race")
    page.open_featured(FE_ID, "race")
    page.open_featured(FE_ID, "statistics")
    _drawn(fp, "Recorded damage per second by class")
    assert asked.count(base + "/race") == races and cf.CLOSER not in _labels(fp)


def test_the_window_draws_combat_logs_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("combat"), CombatPage) and not isinstance(window.page("combat"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                      # not moved over yet
