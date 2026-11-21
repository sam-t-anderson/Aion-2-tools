"""The native Combat Logs page, part 1 (0.2.450): its views and lists, and Saved Logs (a fight analyzed from a link or a
file with its progress, the logs folder, the log server shared to, the encounters analyzed), as pages/combat.js shows
them; since 0.2.451 Saved Logs' recorded encounters by type (saved-logs.js) and its upload queue (archive-upload.js);
since 0.2.452 My Uploads (log-ownership.js) and My Character Identities (identity.js); since 0.2.453 the community's
views (logs-view.js); since 0.2.454 Personal records (community.js); since 0.2.455 the featured encounters (featured.js);
since 0.2.456 an analyzed encounter's page with its parse card (pages/combat.js, parse.js); since 0.2.457 a log's own
page, its review's frame and summary (combat-review.js); since 0.2.458 its graph, ping, boss HP and enemies.
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

from PySide6.QtCore import QBuffer, QCoreApplication, QEvent, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPlainTextEdit,  # noqa: E402
                               QPushButton)

from aion2calc.gui import combat as cb  # noqa: E402
from aion2calc.gui import combat_views as cv  # noqa: E402
from aion2calc.gui import combat_records as cr  # noqa: E402
from aion2calc.gui import combat_featured as cf  # noqa: E402
from aion2calc.gui import combat_analysis as ca  # noqa: E402
from aion2calc.gui.combat_analysis_page import Bar, DpsChart, Donut, ParseCard  # noqa: E402
from aion2calc.gui import combat_review as cw  # noqa: E402
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
SKILL = "https://metabot.gg/web/aion2/skills/11010000.webp"
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

# an analyzed encounter (/api/encounters/<id>): one player's fight, compared with the optimal rotation and the top logs
ANALYSIS = {"id": 3, "file": "/data/logs/3.json",
            "meta": {"player": "TestSorc", "class": "sorcerer", "target": "Ice Queen", "source": "abysslogs",
                     "combat_power": 123456, "url": "https://abysslogs.com/e/abc", "notes": ["party log", "8 players"],
                     "party": [{"name": "TestSorc", "class": "sorcerer", "damage": 900000},
                               {"name": "TestCleric", "class": "cleric", "damage": 120000}]},
            "summary": {"total": 1000000, "dps": 8333.3, "duration": 120, "hits": 410, "cpm": 41.5, "idle_seconds": 3.25,
                        "crit": 0.42, "double": 0.1, "perfect": 0.05, "multi": 0.2, "back": 0.3, "front": 0.6,
                        "biggest_hit": {"skill": "Flame Burst", "damage": 52345}},
            "skills": [{"skill": "Flame Burst", "skill_id": 11010001, "hits": 40, "share": 0.5, "avg_hit": 12500,
                        "max_hit": 52345},
                       {"skill": "Ice Spear", "skill_id": 11020005, "hits": 120, "share": 0.2, "avg_hit": 1666.7,
                        "max_hit": 4000},
                       {"skill": "Frost Nova", "hits": 30, "share": 0.1, "avg_hit": 3333, "max_hit": 5000},
                       {"skill": "Arcane Bolt", "hits": 100, "share": 0.08, "avg_hit": 800, "max_hit": 1200},
                       {"skill": "Wind Cut", "hits": 60, "share": 0.06, "avg_hit": 1000, "max_hit": 1500},
                       {"skill": "Ember", "hits": 40, "share": 0.04, "avg_hit": 1000, "max_hit": 1100},
                       {"skill": "Spark", "hits": 20, "share": 0.02, "avg_hit": 1000, "max_hit": 1000}],
            "rotation": [[0.0, "Flame Burst"], [1.24, "Ice Spear"], [2.5, "Unknown Strike"]],
            "timeline": {"per_second": [8000, 9000, 7000, 12000, 6000], "rolling10": [8000, 8500, 8000, 9000, 8400]},
            "buffs": [{"name": "Arcane Focus", "uptime": 0.8}, {"name": "Haste", "uptime": None}],
            "gaps": [{"start": 10.0, "end": 12.25, "length": 2.25}],
            "vs_optimal": {"share_overlap": 0.71, "comparable_dps": True, "sim_dps": 9800, "actual_dps": 8333.3,
                           "note": "Simulated with the optimized build.", "tips": ["Cast Flame Burst on cooldown."],
                           "skills": [{"skill": "Flame Burst", "share": 0.5, "sim_share": 0.55, "casts": 12, "sim_casts": 14}],
                           "specs": [{"skill": "Flame Burst", "yours": "Spec A", "optimal": "Spec B", "differs": True},
                                     {"skill": "Ice Spear", "yours": None, "optimal": "Spec C", "differs": False}]},
            "vs_top": {"overlap": 0.64, "rows": [{"skill": "Flame Burst", "share": 0.5, "top_share": 0.45, "hpm": 20,
                                                  "top_hpm": 22.4}]}}
CLERIC_ANALYSIS = {**ANALYSIS, "id": 4, "meta": {**ANALYSIS["meta"], "player": "TestCleric", "class": "cleric"},
                   "vs_optimal": {"error": "no optimized build for cleric"}, "vs_top": {"error": "no top logs"}}

# a recorded log (an a2log document): a PvE fight (a player, their spirit, a healer, the boss) and an arena match
REVIEW_LOG = {
    "meta": {"title": "Frost Spire night", "encounter_type": "pve_raid", "installed_build": "2.1.0.3",
             "installed_build_source": "game files", "game_patch": "version:product:2.1",
             "game_patch_source": "version:product:2.1.0.3", "region_source": "server list"},
    "players": [{"id": "p1", "name": "TestSorc", "class": "sorcerer", "server": 2102, "verified": True},
                {"id": "p2", "name": "TestCleric", "class": "cleric"}],
    "run_analysis": {"note": "Runs from the recording.", "runs": [
        {"id": "r1", "recorded_span_seconds": 754.3, "elapsed_seconds": 700, "combat_seconds": 120, "downtime_seconds": 65.04,
         "speed_eligible": True, "progression": [
             {"boss": "Ice Queen", "boss_key": "npc:2001", "attempts": 2, "kills": 1, "wipes": 1, "unknown": 0,
              "attempts_to_first_clear": 2, "best_wipe_hp_pct": 12.34, "wipe_recovery_seconds": [45]},
             {"boss": "Mau Totem", "boss_key": "npc:2300907", "attempts": 1, "kills": 1, "wipes": 0, "unknown": 0}],
         "attempts": [{"attempt": 1, "boss": "Ice Queen", "boss_key": "npc:2001", "outcome": "wipe", "recorded_seconds": 90,
                       "best_remaining_hp_pct": 12.34, "segments": [0]}]},
        {"id": "r2", "recorded_span_seconds": 60, "elapsed_seconds": None, "combat_seconds": 55, "downtime_seconds": 5,
         "speed_eligible": False, "speed_reasons": ["No instance entry."]}]},
    "segments": [
        {"label": "Ice Queen", "boss": "Ice Queen", "duration": 120, "run_id": "r1", "run_complete": True,
         "run_end_reason": "boss killed", "zone": "Frost Spire", "zone_source": "map load", "difficulty": "Hard",
         "difficulty_source": "instance",
         "entities": [{"id": "pet1", "name": "Spirit", "owner": "p1"},
                      {"id": "b1", "name": "Ice Queen", "kind": "enemy", "is_boss": True}],
         "quality": {"eligible": True, "messages": ["Complete capture."], "note": "Checked against the boss's HP.",
                     "driver_monitoring": {"sampled": True, "pcap_received": 1200, "pcap_dropped": 0, "pcap_if_dropped": 0,
                                           "note": "No loss."}},
         "heals_over_time": {"records": 2, "amount": 900, "rebuilt": 450, "skills": {"Renewal": 2}},
         "events": [{"kind": "damage", "t": 0.5, "source": "p1", "target": "b1", "amount": 1000, "skill": "Flame Burst"},
                    {"kind": "damage", "t": 1.2, "source": "pet1", "target": "b1", "amount": 500, "skill": "Spirit Strike"},
                    {"kind": "damage", "t": 2.7, "source": "p1", "target": "b1", "amount": 1500, "skill": "Flame Burst"},
                    {"kind": "damage", "t": 3.1, "source": "b1", "target": "p2", "amount": 800, "skill": "Frost Breath"},
                    {"kind": "heal", "t": 3.5, "source": "p2", "target": "p2", "amount": 600, "skill": "Heal"},
                    {"kind": "death", "t": 5.0, "target": "p2"}, {"kind": "death", "t": 5.0, "target": "p2"},
                    {"kind": "revive", "t": 9.0, "target": "p2"}]},
        {"label": "Arena", "duration": 60, "encounter_type": "pvp_arena", "run_id": "r2",
         "entities": [{"id": "e1", "name": "Rival", "kind": "enemy", "is_player": True, "class": "ranger", "server": 2102}],
         "casts": [{"source": "e1", "t": 1.5}],
         "events": [{"kind": "damage", "t": 1.0, "source": "p1", "target": "e1", "amount": 2000, "skill": "Flame Burst"},
                    {"kind": "damage", "t": 2.0, "source": "e1", "target": "p1", "amount": 900, "skill": "Arrow"},
                    {"kind": "heal", "t": 3.0, "source": "p2", "target": "e1", "amount": 300, "skill": "Heal"},
                    {"kind": "death", "t": 4.0, "target": "e1"}],
         "arena": {"result": "win", "rounds_won": 1, "rounds_lost": 0, "rating": 1512,
                   "fighters": [{"name": "TestSorc", "ref": "p1", "self": True, "class": "sorcerer", "server": 2102,
                                 "faction": "elyos", "rating": 1500},
                                {"name": "Rival", "ref": "e1", "class": "ranger", "server": 2102, "faction": "asmodian",
                                 "rating": 1520}],
                   "rounds": [{"round": 1, "t": 30.25, "winner": 0, "loser": 1}]}}]}
REVIEW_RANKS = {"players": [{"id": "p1", "parse": 98.6, "parse_runs": 12, "parse_rank": 2}, {"id": "p2", "parse": None}],
                "note": "Ranked against public runs."}


def _fight():
    """The recorded log with more to its PvE fight: the boss's HP, two hounds, a summon nobody struck, an NPC the catalog
    names only by its code, and the recorder's ping."""
    fight = json.loads(json.dumps(REVIEW_LOG))
    seg = fight["segments"][0]
    seg["entities"][1]["mob_code"] = 2001
    seg["entities"] += [{"id": "a1", "name": "Frost Hound", "kind": "enemy", "mob_code": 2002},
                        {"id": "a2", "name": "Frost Hound", "kind": "enemy", "mob_code": 2002},
                        {"id": "u1", "name": "Unnamed summon", "kind": "enemy", "mob_code": 9001},
                        {"id": "c1", "name": "#4242", "kind": "enemy", "mob_code": 4242}]
    seg["events"] += [{"kind": "damage", "t": 6.0, "source": "p1", "target": "a1", "amount": 400, "skill": "Flame Burst"},
                      {"kind": "damage", "t": 7.5, "source": "p1", "target": "a2", "amount": 300, "skill": "Flame Burst"},
                      {"kind": "damage", "t": 8.0, "source": "u1", "target": "p2", "amount": 50, "skill": "Spike"},
                      {"kind": "damage", "t": 9.5, "source": "p1", "target": "c1", "amount": 100, "skill": "Flame Burst"}]
    seg["health"] = [{"entity": "b1", "t": 0.0, "current": 10000, "max": 10000},
                     {"entity": "b1", "t": 60.0, "current": 4000, "max": 10000}, {"entity": "b1", "t": 130.0, "current": 0}]
    seg["ping"] = [[0.5, 42.0], [30.0, 55.5], [130, 40], [10, 70000], "bad"]
    seg["ping_source"], seg["ping_recorder"] = "passive_tcp_ack", "p1"
    return fight


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
        self.posted: list[tuple[str, dict]] = []               # what was sent to the server's routes
        self.review_log = REVIEW_LOG                            # the log its raw route gives, and the app's recording
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
        if route.startswith("/api/v1/logs/") and route.endswith("/raw"):
            if route != "/api/v1/logs/log0001/raw":
                raise ValueError("RuntimeError: Community server (404): no such log")
            return json.loads(json.dumps(self.review_log))
        if route.startswith("/api/v1/logs/") and route.endswith("/rankings"):
            return {**json.loads(json.dumps(REVIEW_RANKS)), "segment": int(q["segment"][0])}
        if route == "/api/v1/npc-portraits":
            return {"portraits": {"4242": {"name": "Ice Wraith", "icon": "https://img.example/npc/4242.png"}}}
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
        self.share_refusal = None

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

    def community_post(self, body):
        """What the log server answers to a route posted through the app's proxy (``communityAPI(path, body)``)."""
        self.log_server.posted.append((body["path"], json.loads(json.dumps(body["body"]))))
        if self.log_server.refusal:
            raise ValueError(self.log_server.refusal)
        if body["path"] == "/api/v1/rankings":
            return {**json.loads(json.dumps(REVIEW_RANKS)), "segment": body["body"]["segment"]}
        raise AssertionError(body["path"])

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
        if path in ("/static/game-assets/npc/2001.png", "/static/game-assets/class/sorcerer.png",
                    "/static/game-assets/skill/11010000.png"):
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
        if path.startswith("/api/encounters/"):
            found = {"3": ANALYSIS, "4": CLERIC_ANALYSIS}.get(path.rsplit("/", 1)[1])
            if found is None:
                raise ValueError("No such encounter")
            return json.loads(json.dumps(found))
        if path == "/static/game-assets.json":
            return {"assets": {PORTRAIT: "game-assets/npc/2001.png", SORCERER: "game-assets/class/sorcerer.png",
                               SKILL: "game-assets/skill/11010000.png"},
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
            if "file" in query:
                if query["file"] != ["session-1.a2log.json"]:
                    raise ValueError("No such recording")
                return json.loads(json.dumps(self.log_server.review_log))
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
        if path.startswith("/api/encounters/") and path.endswith("/share"):
            if self.share_refusal:
                raise ValueError(self.share_refusal)
            return {"url": "https://logs.example/log/rep0009", "ownership_warning": "Keep this log's delete token safe."}
        if path == "/api/upload-queue":
            self.queue_kept = json.loads(json.dumps(body))
            return {"ok": True}
        if path == "/api/community":
            return self.community_post(body)
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


def _shown():
    """What was drawn last, shown: the waiting events handled, then the shows a redraw among them queued (a widget
    added to a shown layout is shown by a queued call, so a redraw a timer starts in ``processEvents`` would otherwise
    leave its widgets unshown for the next look)."""
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents()


def _texts(widget):
    _shown()
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
    _button(page.encounters_box, "Open").click()                      # in place of the views since 0.2.456
    settle(lambda: page.analysis_page.isVisibleTo(page) and "TestSorc" in _texts(page.analysis_page))
    assert not page.frame.isVisibleTo(page) and page.analysis_page.identifier == 3 and opened == []
    _button(page, cf.BACK).click()
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
    settle(lambda: page.analysis_page.isVisibleTo(page) and page.analysis_page.identifier == 4)
    _button(page, cf.BACK).click()
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
    _shown()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def _folds(widget):
    _shown()
    return [f for f in widget.findChildren(Section) if f.isVisibleTo(widget)]


def _find(widget, kind, test):
    """The first shown ``kind`` passing ``test``, once what was drawn last has shown."""
    _shown()
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
    _shown()
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
    _shown()
    return [b for b in widget.findChildren(QPushButton) if b.text() == words and b.isVisibleTo(widget)]


def _visibility_boxes(widget):
    _shown()
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
    _shown()
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
    seen = []

    class Refused(FeaturedSection):
        def refused(self, kind, why):          # heard where the section hears it: a listener connected once it has
            seen.append(why)                   # asked could miss a refusal the worker gave at once
            super().refused(kind, why)
    refused = Refused(quiet, lambda *_: None)
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


def test_the_analysis_words():
    import pytest as _pytest
    d = ca.parse_from_encounter(ANALYSIS)
    assert (d["name"], d["cls"], d["cp"], d["dmg"], d["dps"], d["hits"], d["boss"], d["highest"]) == (
        "TestSorc", "sorcerer", 123456, 1000000, 8333.3, 410, "Ice Queen", 52345)
    assert d["gs"] is None and d["contrib"] is None and d["rates"]["crit"] == 0.42 and d["rates"]["front"] == 0.6
    first = d["skills"][0]
    assert (first["skill"], first["damage"], first["min"], first["max"]) == ("Flame Burst", 500000.0, None, 52345)
    assert first["dps"] == _pytest.approx(500000 / 120)
    assert d["rotation"] == [{"t": 0.0, "skill": "Flame Burst", "skill_id": 11010001},
                             {"t": 1.24, "skill": "Ice Spear", "skill_id": 11020005},
                             {"t": 2.5, "skill": "Unknown Strike", "skill_id": None}]
    assert ca.skill_art(11010001) == SKILL and ca.skill_art(None) == ca.skill_art(0) == ""
    assert [ca.rate(None), ca.rate(0.425)] == ["—", "43%"]
    # the parse card
    parts = ca.donut(d)
    assert [(p["label"], p["share"]) for p in parts] == [("Flame Burst", "50%"), ("Ice Spear", "20%"), ("Frost Nova", "10%"),
                                                         ("Arcane Bolt", "8%"), ("Wind Cut", "6%"), ("Other (2)", "6%")]
    assert parts[-1]["colour"] == ca.PALETTE[8]
    arcs = ca.donut_arcs(parts)
    assert arcs[0][0] == -90 and arcs[0][1] == _pytest.approx(180) and sum(a[1] for a in arcs) == _pytest.approx(360)
    assert ca.donut_arcs([]) == [(-90.0, _pytest.approx(359.9964), ca.EMPTY_DONUT)]
    row = ca.skill_rows(d)[0]
    assert {k: row[k] for k in ("hits", "dps", "avg", "min", "max", "damage", "share", "bar")} == {
        "hits": "40", "dps": "4.17K", "avg": "12.50K", "min": "—", "max": "52.34K", "damage": "500.00K", "share": "50%",
        "bar": 1.0}
    assert ca.accuracy(d) == [("Hits", "410"), ("Crit", "42%"), ("Back", "30%"), ("Front", "60%"), ("Double", "10%"),
                              ("Perfect", "5%"), ("Multi", "20%"), ("Parried", "—")]
    assert ca.hits({**d, "hits": None}) == 410 and ca.hits({"skills": [{"skill": "x"}]}) is None
    assert ca.defense(d) is None
    live = {"incoming": {"damage": 54321, "hits": 30, "parries": 2, "shield_blocks": 1, "endurance": 0,
                         "sources": {"Frost Hound": 4321, "Ice Queen": 50000}}, "healing": 1500}
    assert ca.defense(live) == {"cards": [("Damage taken", "54.32K"), ("Incoming hits", "30"), ("Parried hits", "2"),
                                          ("Shield blocks", "1"), ("Endurance", "0"), ("Healing done", "1.50K")],
                                "attackers": [("Ice Queen", "50.00K"), ("Frost Hound", "4.32K")]}
    assert [c["at"] for c in ca.rotation(d)] == ["0s", "1s", "3s"]
    assert ca.head_stats(d) == [("CP", "123.46K", False), ("DMG", "1.00M", False), ("DPS", "8.33K", True)]
    assert ca.head_stats({"gs": 3456, "contrib": 0.456, "dmg": 1000, "dps": 50}) == [
        ("GS", "3,456", False), ("DMG", "1.00K", False), ("DPS", "50", True), ("Contrib", "46%", False)]
    assert ca.head_line(d) == "Sorcerer · Ice Queen" and ca.head_line({}) == ""
    chart = ca.chart(d)
    assert (chart["top"], chart["peak"], len(chart["per"])) == (12000, "peak 10 s: 9,000", 5)
    assert ca.chart({"timeline": None}) is None
    # the analysis page
    assert ca.subtitle(ANALYSIS) == "TestSorc · Sorcerer · Ice Queen · abysslogs · CP 123,456"
    assert ca.party(ANALYSIS) == [{"name": "TestSorc", "class": "sorcerer", "you": True, "tip": "sorcerer · 900,000 damage"},
                                  {"name": "TestCleric", "class": "cleric", "you": False, "tip": "cleric · 120,000 damage"}]
    assert ca.party({"meta": {"party": [{"name": "TestSorc"}]}}) == []
    assert ca.info_html(ANALYSIS, "#39c2e0") == (
        "party log · 8 players · <a href='https://abysslogs.com/e/abc' style='color: #39c2e0;'>open on AbyssLogs</a> · "
        "saved as <code>/data/logs/3.json</code>")
    assert ca.info_html({}, "#39c2e0") == ""
    assert ca.chips(ANALYSIS) == [("Casts / min", "42"), ("Multi-hit", "20.0%"), ("Idle", "3.3 s")]
    assert ca.buffs(ANALYSIS) == [{"name": "Arcane Focus", "bar": 0.8, "words": "80%"}, {"name": "Haste", "bar": 0.0, "words": "—"}]
    assert ca.gaps(ANALYSIS) == "Idle gaps: 10.0–12.3s" and ca.gaps({}) == ""
    assert ca.optimal(ANALYSIS) == {
        "error": "", "note": "Simulated with the optimized build.", "overlap": "71%", "dps": " · optimal DPS 9,800 vs yours 8,333",
        "tips": ["Cast Flame Burst on cooldown."],
        "rows": [{"skill": "Flame Burst", "share": 0.5, "share_words": "50.0%", "sim": 0.55, "sim_words": "55.0%",
                  "casts": "12", "sim_casts": "14"}],
        "specs": [{"skill": "Flame Burst", "yours": "Spec A", "optimal": "Spec B", "differs": True},
                  {"skill": "Ice Spear", "yours": "none", "optimal": "Spec C", "differs": False}]}
    assert ca.optimal(CLERIC_ANALYSIS) == {"error": "no optimized build for cleric"}
    assert ca.top(ANALYSIS) == {"overlap": "64%", "rows": [["Flame Burst", "50.0%", "45.0%", "20", "22"]]}
    assert ca.top(CLERIC_ANALYSIS) is None
    assert ca.import_body(ANALYSIS, "TestCleric") == {"ref": "https://abysslogs.com/e/abc", "player": "TestCleric"}


def test_an_analyzed_encounter(qapp):
    from aion2calc.gui import combat_analysis_page as cap
    links = []
    app = FakeApp()
    page = _page(app, open_link=links.append)
    page.open_analysis(3)
    view = page.analysis_page
    settle(lambda: "TestSorc" in _labels(view) and view.findChildren(ParseCard))
    card = view.findChildren(ParseCard)[0]
    settle(lambda: card.wide and any(not label.pixmap().isNull() for label in card.findChildren(QLabel)
                                     if label.objectName() == "pIcon"))
    assert not page.frame.isVisibleTo(page) and page.featured_box.isVisibleTo(page)
    texts = _labels(view)
    assert "ENCOUNTER" in texts and ca.subtitle(ANALYSIS) in texts and "Sorcerer · Ice Queen" in texts
    # every section at once on a wide card: their headings, the notes in their tooltips, no tabs
    assert all(h in texts for h in ("DAMAGE BY SKILL", "DPS OVER THE FIGHT", "SKILLS", "ACCURACY", "DEFENSE", "SKILL ROTATION"))
    accuracy = _find(card, QLabel, lambda label: label.text() == "ACCURACY")
    assert accuracy.toolTip() == ca.ACCURACY_NOTE and ca.ACCURACY_NOTE not in texts
    assert not [b for b in card.findChildren(QPushButton) if b.objectName() == "pTab" and b.isVisibleTo(card)]
    assert all(t in texts for t in ("123.46K", "1.00M", "8.33K", "52.34K", "4.17K", "12.50K", "Other (2)", "42%", ca.NO_INCOMING,
                                    "0s", "1s", "3s"))
    assert card.findChildren(Donut)[0].value == "8.33K" and len(card.findChildren(Donut)[0].arcs) == 6
    assert card.findChildren(DpsChart)[0].per == [8000, 9000, 7000, 12000, 6000]
    assert any("500.00K" in t and "50%" in t for t in texts)
    # a narrower card: the tabs, one section at a time, the tab chosen kept for the next card
    page.resize(700, 1400)
    settle(lambda: card.wide is False and [b for b in card.findChildren(QPushButton) if b.objectName() == "pTab"
                                           and b.isVisibleTo(card)])
    assert ca.ACCURACY_NOTE not in _labels(card) and "4.17K" in _labels(card)
    _click(card, "Defense")
    assert cap._TAB["chosen"] == "def" and ca.NO_INCOMING in _labels(card) and "4.17K" not in _labels(card)
    _click(card, "Accuracy")
    assert ca.ACCURACY_NOTE in _labels(card) and "42%" in _labels(card)
    _click(card, "DPS")
    page.resize(1200, 1400)
    settle(lambda: card.wide)
    # under the card, the buffs, the optimal rotation and the top logs
    texts = _labels(view)
    assert all(t in texts for t in ("Casts / min: <b>42</b>", "Multi-hit: <b>20.0%</b>", "Idle: <b>3.3 s</b>",
                                    "Idle gaps: 10.0–12.3s", "Cast Flame Burst on cooldown.", "SPECIALIZATIONS (from the log)"))
    bars = [(b.words, b.alt) for b in view.findChildren(Bar) if b.isVisibleTo(view)]
    assert ("80%", True) in bars and ("—", True) in bars and ("50.0%", False) in bars and ("55.0%", True) in bars
    assert any("71%" in t and " · optimal DPS 9,800 vs yours 8,333" in t for t in texts)
    assert f"<span style='color: {theme_colour('bad')};'>Spec A</span>" in texts
    assert any("64%" in t and "top Korean logs" in t for t in texts) and "22" in _cells(view)
    notes = _find(view, QLabel, lambda label: "open on AbyssLogs" in label.text())
    notes.linkActivated.emit("https://abysslogs.com/e/abc")
    assert links == ["https://abysslogs.com/e/abc"]
    # Share link: its link, the warning; or why not
    _click(view, ca.SHARE)
    settle(lambda: any(ca.SHARED in t for t in _labels(view)))
    assert page.toast.text() == "Keep this log's delete token safe."
    _find(view, QLabel, lambda label: ca.SHARED in label.text()).linkActivated.emit("https://logs.example/log/rep0009")
    assert links[-1] == "https://logs.example/log/rep0009"
    app.share_refusal = "Sign in to share"
    _click(view, ca.SHARE)
    settle(lambda: "Sign in to share" in _labels(view))
    # the fight as another of its party: analyzed, then opened
    _find(view, QPushButton, lambda b: b.accessibleName() == "Analyze as TestCleric").click()
    settle(lambda: view.identifier == 4 and "TestCleric · Cleric · Ice Queen · abysslogs · CP 123,456" in _labels(view))
    assert ("/api/encounters/import", {"ref": "https://abysslogs.com/e/abc", "player": "TestCleric"}) in app.posts
    assert "no optimized build for cleric" in _labels(view) and "COMPARED WITH TOP PLAYERS" not in _labels(view)
    # an encounter the app can't read
    page.open_analysis(99)
    settle(lambda: "No such encounter" in _labels(view))
    _click(page, cf.BACK)
    assert page.frame.isVisibleTo(page) and not page.featured_box.isVisibleTo(page)


def theme_colour(name):
    from aion2calc.gui import theme
    return theme.COLORS[name]


def test_a_parse_card_with_incoming_damage(qapp):
    live = {"name": "TestSorc", "cls": "sorcerer", "gs": 3456, "contrib": 0.456, "dmg": 1000, "dps": 50, "healing": 1500,
            "skills": [], "rates": {}, "incoming": {"damage": 54321, "hits": 30, "parries": 2, "shield_blocks": 1, "endurance": 0,
                                                    "sources": {"Frost Hound": 4321, "Ice Queen": 50000}}}
    card = ParseCard(live)
    card.resize(1000, 900)
    card.show()
    settle(lambda: card.wide)
    texts = _labels(card)
    assert all(t in texts for t in ("GS", "3,456", "CONTRIB", "46%", "54.32K", "Ice Queen", "50.00K", "4.32K", ca.NO_SKILLS))
    defense = _find(card, QLabel, lambda label: label.text() == "DEFENSE")
    assert defense.toolTip() == ca.DEFENSE_NOTE
    assert card.findChildren(Donut)[0].arcs == [(-90.0, 359.9964, ca.EMPTY_DONUT)] and not card.findChildren(DpsChart)
    assert "SKILL ROTATION" not in texts


def test_the_window_opens_an_analysis_itself(qapp):
    window = MainWindow(None)
    window.open_web("combat-log/analysis/7")
    combat = window.page("combat")
    assert window.pages.currentWidget() is combat and combat.analysis_page.identifier == "7"
    QCoreApplication.processEvents()
    assert combat.analysis_page.isVisibleTo(combat) and not combat.frame.isVisibleTo(combat)


def test_the_review_words():
    doc = json.loads(json.dumps(REVIEW_LOG))
    assert cw.actor_label({"name": "TestSorc", "verified": True, "server": 2102}) == "TestSorc ✓ · Zikel"
    assert cw.actor_label({"id": "x9", "pseudonym": True}) == "x9 (hidden by its player)"
    assert cw.actor_label(None) == cw.actor_label({}) == cw.UNKNOWN
    r = cw.segment_refs(doc, doc["segments"][0], True)
    assert set(r) == {"p1", "p2", "pet1", "b1"} and r["pet1"]["class"] == "sorcerer"     # a pet takes its owner's class
    assert set(cw.segment_refs(doc, {}, True)) == {"p1", "p2"} and cw.segment_refs(doc, {}, False) == {}
    assert cw.root_owner("pet1", r) == "p1" and cw.root_owner("a", {"a": {"owner": "b"}, "b": {"owner": "a"}}) == "a"
    # the players' totals: a pet's damage its owner's, one death marker recorded twice one death, the active clock
    state = cw.fresh_state()
    d = cw.data(doc, state)
    rows = {p["id"]: p for p in d["rows"]}
    assert (rows["p1"]["damage"], rows["p1"]["hits"], rows["p2"]["taken"], rows["p2"]["healing"]) == (3000, 3, 800, 600)
    assert (rows["p2"]["deaths"], rows["p2"]["revives"], d["dps_duration"]) == (1, 1, 2)
    assert {p["id"]: p["damage"] for p in cw.data(doc, {**state, "combine": False})["rows"]}["pet1"] == 500
    assert all(p["damage"] == 0 for p in cw.data(doc, {**state, "enemy": "zz"})["rows"])
    assert [(x["id"], x["damage"], x["dps"], x["taken"], x["healing"], x["hps"], x["deaths"]) for x in cw.summary_rows(d, d, state)] == [
        ("p1", "3,000", "1,500", "0", "0", "0", "No markers"), ("p2", "0", "0", "800", "600", "5", "1 (revived 1)")]
    assert [x["id"] for x in cw.summary_rows(d, d, {**state, "metric": "taken"})] == ["p2", "p1"]
    assert [x["id"] for x in cw.summary_rows(d, d, {**state, "actor": "p2"})] == ["p2"]
    note = cw.summary_note(d, d, "", True)
    assert note.startswith("DPS uses shared active damage time (2s)") and note.endswith(cw.PARSE_NOTE)
    assert cw.summary_columns(True)[1] == "Parse" and "Parse" not in cw.summary_columns(False)
    # a PvP fight: the heals between the two sides nobody's, an opponent read from their side
    pvp = {**state, "segment": 1}
    d1 = cw.data(doc, pvp)
    assert [e["id"] for e in cw.opponents_of(doc, d1)] == ["e1"] and cw.is_pvp(doc, d1) and not cw.opponents_of(doc, d)
    assert d1["unattributed"] == {"count": 1, "amount": 300.0, "skills": {"Heal": 1}}
    assert cw.unattributed_line(d1["unattributed"]).startswith(
        "Left out of everyone's healing: 1 heal record between the two sides, 300 as recorded (Heal ×1).")
    foe = cw.data(doc, pvp, "e1")
    assert {p["id"]: (p["damage"], p["taken"], p["deaths"]) for p in foe["rows"]} == {"e1": (900, 2000, 1)}
    o = cw.opponent(foe)
    assert o["recorded"] == ("Recorded: 1 hit of theirs, 1 hit on them, 1 cast, 1 death marker. Not recorded: their healing, "
                             "buffs and debuffs on or from them, their HP, their positions.")
    assert [(x["id"], x["amount"], x["share"], x["rate"]) for x in o["dealt"]] == [("p1", "900", "100.0%", "900")]
    assert [(x["id"], x["amount"], x["rate"]) for x in o["taken"]] == [("p1", "2,000", "33")]
    assert cw.summary_note(d1, foe, "e1", False).startswith("An opponent's figures are the recording's records of them")
    a = cw.arena(d1)
    assert a["title"] == "Arena match · Win 1–0 · Rating 1500 → 1512 (+12)"
    assert [(f["name"], f["self"], f["server"], f["faction"], f["rating"], f["won"]) for f in a["fighters"]] == [
        ("TestSorc", True, "Zikel", "Elyos", "1500", "1"), ("Rival", False, "Zikel", "Asmodian", "1520", "0")]
    assert [(x["round"], x["at"], x["winner"]["name"], x["loser"]["name"]) for x in a["rounds"]] == [("1", "0:30.25", "TestSorc", "Rival")]
    assert cw.arena({"segment": {}, "r": {}}) is None
    # the encounters, runs and notes
    assert cw.segment_choices(doc, state) == [(0, "Ice Queen"), (1, "Arena")]
    assert cw.segment_choices(doc, {**state, "mode": "pvp"}) == [(1, "Arena")]
    assert cw.segment_choices(doc, {**state, "run": "r1"}) == [(0, "Ice Queen")]
    assert cw.runs(doc, state) == ["r1", "r2"] and cw.first_of_run(doc, {**state, "run": "r2"}) == 1
    assert cw.run_line(d) == "Run r1 · Finished · boss killed"
    cut = {"segments": [{"label": "Boss"}, {"label": "Boss", "continued_in": 0, "fragment": "after_kill"}, {"boss": "Boss", "continued_in": 0}]}
    assert [w for _i, w in cw.segment_choices(cut, state)] == ["Boss", "Boss (after the kill)", "Boss (piece of a cut fight)"]
    assert cw.pieces(cut, state) == [2]
    assert cw.source_line(doc, d) == ("Installed game version: 2.1.0.3 (game files). Version source: Product version 2.1.0.3. "
                                      "Zone: Frost Spire · map load. Difficulty: Hard · instance. Region source: server list.")
    assert cw.rebuilt_line(doc["segments"][0]["heals_over_time"]).startswith(
        "Heals over time rebuilt: 2 heal records (Renewal ×2), 900 as recorded, now 450.")
    assert cw.rebuilt_line(None) == "" and cw.unattributed_line(None) == ""
    # the capture's quality, and how a cut fight was joined
    q = cw.quality(None, d)
    assert q["summary"] == "Capture quality · Eligible for community rankings" and q["messages"] == ["Complete capture."]
    assert q["driver"] == "Capture driver: 1,200 received · 0 capture-buffer drops · 0 interface/driver drops. No loss."
    assert q["processing"] == "" and q["note"] == "Checked against the boss's HP."
    old = cw.quality({}, {"segment": {}})
    assert old["summary"].endswith("Unranked / completeness unverified") and old["note"] == cw.OLD_QUALITY
    ranked = cw.quality({"quality": {"eligible": False, "capture_processing": {"decoder_errors": 2}}}, d)
    assert ranked["processing"].startswith("Capture processing: 2 decoder failures · not recorded recovered frame-skips")
    lines = cw.stitched({"stitched": {"merged": {"duration": 180, "damage": 5000, "previous": {"log": "log0000"}}},
                         "continued_in": {"part": 3, "log": "log0002"}}, d, doc)
    assert lines[0]["words"].startswith("This fight was cut by a storage rollover: its first 1:00.0 are in the previous recording part.")
    assert (lines[0]["log"], lines[1]["log"]) == ("log0000", "log0002")
    assert lines[1]["words"] == ("This fight was cut by a storage rollover and continues in the next part of the recording (part 3), "
                                 "where the whole fight is indexed and ranked.")
    assert cw.stitched({"stitched": {"parts": [1, 3]}}, d, doc)[0]["words"].startswith("Part of a run stitched across recording parts 1–3")
    piece = cw.stitched(None, {"segment": {"continued_in": 0, "fragment": "opening_blow"}}, doc)
    assert [(x["segment"], x["action"]) for x in piece] == [(0, "Open the fight")]
    runs = cw.run_tables(doc, d, state, None)
    assert runs["kind"] == "pve" and runs["rows"][0] == ["r1", "12:34.3", "11:40.0", "2:00.0", "1:05.0", "Eligible"]
    assert runs["rows"][1][2] == "Unavailable" and runs["rows"][1][-1] == "No instance entry."
    assert [x[0] for x in runs["progression"]["rows"]] == ["Ice Queen"]          # the mini-boss left out
    assert runs["progression"]["rows"][0][6:] == ["12.3%", "0:45.0"]
    assert runs["progression"]["attempts"] == [["1", "Ice Queen", "wipe", "1:30.0", "12.3%", "0"]]
    pvp_runs = cw.run_tables(doc, d1, state, None)
    assert pvp_runs["kind"] == "pvp" and pvp_runs["note"].endswith("from the game's own records.")
    assert cw.run_tables({"segments": [{}]}, {"segment": {}}, state, None)["note"] == cw.NO_RUNS
    # parses
    assert cw.parse_badge(None, "p1", "sorcerer")["tip"] == "Loading the community parse…"
    badge = cw.parse_badge(REVIEW_RANKS, "p1", "sorcerer")
    assert (badge["text"], badge["tier"], badge["provisional"]) == ("99", "orange", False)
    assert badge["tip"] == "Parse 98.6 · rank 2 of 12 ranked sorcerer runs on this encounter"
    assert cw.parse_badge(REVIEW_RANKS, "p2", "cleric")["tip"] == "No comparable public parses for this class on this encounter yet"
    assert cw.parse_badge({"note": "Unranked: no boss."}, "p1", "x")["tip"] == "Unranked: no boss."
    assert cw.parse_badge({"error": "busy"}, "p1", "x")["tip"] == "busy"
    few = cw.parse_badge({"players": [{"id": "p1", "parse": 100, "parse_characters": 3}]}, "p1", "sorcerer")
    assert (few["tier"], few["provisional"]) == ("gold", True) and few["tip"].startswith("Parse 100 among 3 ranked sorcerer runs")
    # times, and the pages
    assert [cw.clock(65.4), cw.clock(30.25, True), cw.seconds(None), cw.seconds(61.25)] == ["1:05", "0:30.25", "Unavailable", "1:01.3"]
    assert cw.read_page("combat-log/shared/log0001?mode=pvp&segment=1") == {"kind": "shared", "value": "log0001", "mode": "pvp",
                                                                             "segment": 1}
    assert cw.read_page("combat-log/local/session%201.json") == {"kind": "local", "value": "session 1.json", "mode": "",
                                                                 "segment": None}
    assert cw.read_page("combat-log/analysis/3") is None and cw.read_page("combat") is None
    assert cw.local_page("session 1.json", "pve", 2) == "combat-log/local/session%201.json?mode=pve&segment=2"
    assert cw.log_path("local", "a b.json") == ("/api/sessions?file=a%20b.json", False)
    assert cw.log_path("shared", "log0001") == ("/api/v1/logs/log0001/raw", True)
    assert cw.rankings_question("shared", "log0001", 1, doc) == ("/api/v1/logs/log0001/rankings?segment=1", None)
    assert cw.rankings_question("local", "x", 0, doc) == ("/api/v1/rankings", {"segment": 0, "log": doc})
    assert not cw.reconstructed(doc) and cw.reconstructed({"meta": {"reconstruction": {"sources": []}}})


def _summary_cell(view, row, column):
    _shown()
    return view.summary.cell(row, column)


def test_a_shared_log_review(qapp):
    from aion2calc.gui.combat_review_page import ReviewPage
    opened, web = [], []
    app = FakeApp()
    page = _page(app, open_web=opened.append, open_in_web=web.append)
    page.open_review("shared", "log0001")
    view = page.review_page
    assert isinstance(view, ReviewPage)
    settle(lambda: "FROST SPIRE NIGHT" in _labels(view) and "99" in _labels(view))
    asked = app.log_server.asked
    assert "/api/v1/logs/log0001/raw" in asked and "/api/v1/logs/log0001/rankings?segment=0" in asked
    assert not page.frame.isVisibleTo(page) and view.isVisibleTo(page)
    # the page's paint metrics are Qt's own (``QWidget.metric``): asking for them leaves the metric chosen as it was
    assert view.logicalDpiY() > 0 and view.state["metric"] == "summary"
    texts = _labels(view)
    assert all(t in texts for t in ("120.0s", "Run r1 · Finished · boss killed", cw.ELSEWHERE, "No markers"))
    assert any(t.startswith("Installed game version: 2.1.0.3") for t in texts)
    assert any(t.startswith("Heals over time rebuilt: 2 heal records") for t in texts)
    assert "<span style='color: #123456;'>TestSorc ✓ · Zikel</span>" in texts          # the user's sorcerer colour
    assert f"1 <span style='color: {theme_colour('muted')};'>(revived 1)</span>" in texts
    cells = _cells(view)
    assert all(c in cells for c in ("sorcerer", "3,000", "1,500", "800", "600", "5"))
    pill = _find(view, QLabel, lambda label: label.text() == "99")
    assert pill.toolTip() == "Parse 98.6 · rank 2 of 12 ranked sorcerer runs on this encounter"
    assert _find(view, QLabel, lambda label: label.text() == "·").toolTip() == (
        "No comparable public parses for this class on this encounter yet")
    # the capture's quality and the run timing, folded
    view.quality_fold.button.click()
    assert "• Complete capture." in _labels(view) and "Checked against the boss's HP." in _labels(view)
    view.runs_fold.button.click()
    assert "12:34.3" in _cells(view) and "Run r1 · boss attempts" in _labels(view)
    # the metric sorts the summary; a player chosen alone
    _click(view, "Damage Taken")
    assert "TestCleric" in _summary_cell(view, 1, 0).text()
    _choose(view, "Player", "p2")
    assert "TestCleric" in _summary_cell(view, 1, 0).text() and view.summary.grid.rowCount() == 2
    _choose(view, "Player", "")
    # another encounter: the arena match, the heals left out, the opponent offered; its parses asked for
    _choose(view, "Encounter", 1)
    settle(lambda: "/api/v1/logs/log0001/rankings?segment=1" in asked and "Arena match · Win 1–0 · Rating 1500 → 1512 (+12)" in _labels(view))
    texts = _labels(view)
    assert cw.CHOOSE_OPPONENT in texts and any(t.startswith("Left out of everyone's healing") for t in texts)
    assert "0:30.25" in _cells(view)
    _choose(view, "Player", "e1")
    texts = _labels(view)
    assert any("Recorded: 1 hit of theirs" in t for t in texts) and "PARSE" not in _cells(view) + [
        h.text() for h in view.summary.findChildren(QLabel) if h.objectName() == "thead"]
    assert any(t.startswith("An opponent's figures") for t in texts)
    # the full review in the web interface, at this encounter
    _click(view, cw.OPEN_WEB)
    assert web == ["combat-log/shared/log0001?mode=&segment=1"]
    # the parses read again; another log the server links the fight to
    count = asked.count("/api/v1/logs/log0001/rankings?segment=1")
    _choose(view, "Player", "")
    _click(view, cw.REFRESH)
    settle(lambda: asked.count("/api/v1/logs/log0001/rankings?segment=1") == count + 1 and view.ranks is not None)
    view.ranks = {**REVIEW_RANKS, "continued_in": {"log": "log0002"}}
    view.draw()
    view.quality_fold.button.click()
    _click(view, "Open the whole fight")
    assert opened[-1] == "combat-log/shared/log0002?mode="
    # a log the server doesn't have; Back
    page.open_review("shared", "nope")
    settle(lambda: "RuntimeError: Community server (404): no such log" in _labels(view))
    _click(page, cf.BACK)
    assert page.frame.isVisibleTo(page)


def test_a_recorded_log_review(qapp):
    app = FakeApp()
    page = _page(app)
    page.open_review("local", "session-1.a2log.json", "pvp")
    view = page.review_page
    settle(lambda: "Arena match · Win 1–0 · Rating 1500 → 1512 (+12)" in _labels(view) and app.log_server.posted)
    sent_path, sent = app.log_server.posted[-1]
    assert sent_path == "/api/v1/rankings" and sent["segment"] == 1 and sent["log"]["meta"]["title"] == "Frost Spire night"
    assert "/api/sessions?file=session-1.a2log.json" in app.calls
    assert any("Showing only encounters recorded as PVP" in t for t in _labels(view))
    _choose(view, "Combat mode", "")
    settle(lambda: len(app.log_server.posted) == 2 and "Ice Queen" in [view.findChildren(QComboBox)[2].itemText(i)
                                                                         for i in range(view.findChildren(QComboBox)[2].count())])
    assert app.log_server.posted[-1][1]["segment"] == 0
    # a mode without encounters: said so, and all of them shown again
    view.doc = {"meta": {}, "players": [], "segments": [{"label": "Training", "duration": 5}]}
    view.state["mode"] = "pvp"
    view.draw()
    settle(lambda: cw.NO_MODE_ENCOUNTERS in _labels(view))                # after the parses asked for before it
    _click(view, cw.SHOW_ALL)
    assert view.state["mode"] == "" and view.state["segment"] == 0
    # a recording the app can't read
    page.open_review("local", "nope.json")
    settle(lambda: "No such recording" in _labels(view))


def test_the_window_opens_a_log_review_itself(qapp):
    window = MainWindow(None)
    window.open_web("combat-log/shared/log0001?mode=pvp&segment=1")
    combat = window.page("combat")
    assert window.pages.currentWidget() is combat and combat.review_page.where == {"kind": "shared", "value": "log0001"}
    assert (combat.review_page.state["mode"], combat.review_page.state["segment"]) == ("pvp", 1)
    window.open_web("combat-log/local/session%201.json")
    assert combat.review_page.where == {"kind": "local", "value": "session 1.json"}
    QCoreApplication.processEvents()
    assert combat.review_page.isVisibleTo(combat) and not combat.frame.isVisibleTo(combat)


def test_the_review_graph_and_enemy_words():
    import pytest as _pytest
    fight = _fight()
    state = cw.fresh_state()
    d = cw.data(fight, state)
    names = cw.community_names({"portraits": {"4242": {"name": "Ice Wraith", "icon": "x"}, "1": "y", "2": {"name": ""}}})
    assert names == {"4242": "Ice Wraith"} and cw.community_names({"4242": {"name": "Ice Wraith"}}) == names
    assert cw.npc_name({"name": "#4242", "mob_code": 4242}, names) == "Ice Wraith"
    assert cw.npc_name({"name": "#4242", "mob_code": 4242}) == "#4242" and cw.npc_name({"name": "", "id": 5}) == "5"
    assert cw.is_boss({"is_boss": True}) and not cw.is_boss({"is_boss": True, "mob_code": 2300907})
    # the events shown: a player's, the metric's, without pets, the enemies chosen
    every = cw.visible_events(d, state)
    assert len(every) == len(d["events"])
    assert len(cw.visible_events(d, {**state, "actor": "p2"})) == 6
    assert [e["kind"] for e in cw.visible_events(d, {**state, "metric": "healing"})] == ["heal"]
    assert not any(e.get("source") == "pet1" for e in cw.visible_events(d, {**state, "pets": False}))
    hounds = cw.visible_events(d, {**state, "enemy": "a1,a2"})
    assert [e.get("target") for e in hounds if e["kind"] == "damage"] == ["a1", "a2"]
    # the rate chart
    model = cw.graph(d, every, state, set())
    assert (model["duration"], model["step"], model["count"], model["primary"], model["maximum"]) == (120, 1, 120, "Damage done", 1500)
    assert [s["key"] for s in model["lines"]] == ["p2:Healing", "p2:Damage taken", "p1:Damage done"]
    assert model["total"][:3] == [1000, 500, 1500] and model["roll"][:3] == [1000, 750, 1000]
    assert model["roll"][9] == _pytest.approx(380) and model["roll"][10] == _pytest.approx(280)
    assert len(model["health"]) == 2 and model["hp_max"] == 10000            # a sample after the fight left out
    assert model["words"] == "Damage done per second · 1s buckets · red: boss HP, right scale"
    detail = cw.graph_detail(model, 2.2, d["r"], "")
    assert detail["head"] == "0:02.20 · Total damage done: 1,500/s · 10 s average: 1,000/s"
    assert [(row["label"], row["cells"]) for row in detail["rows"]] == [
        ("TestCleric", ["—", "0/s", "0/s"]), ("TestSorc ✓ · Zikel", ["1,500/s", "—", "—"])]
    assert detail["hp"] == [["Ice Queen", "10,000", "10,000", "0:00.00"]] and detail["hp_head"][0] == "Boss"
    assert cw.graph(d, every, state, {"p1:Damage done"})["maximum"] == 1.0
    assert cw.graph(d, every, {**state, "graph_mode": "players"}, set())["mode"] == "players"
    pvp = {**state, "segment": 1}
    foe = cw.data(fight, pvp, "e1")
    assert cw.graph(foe, cw.visible_events(foe, pvp), pvp, set())["words"].endswith("· Their HP: not recorded")
    # the ping, the bosses' HP, the enemies
    ping = cw.latency(d)
    assert ping["title"] == "Recorder ping · TestSorc ✓ · Zikel" and len(ping["points"]) == 2
    assert ping["figures"] == "Average 48.8 ms · Minimum 42.0 ms · Maximum 55.5 ms · 2 samples"
    assert ping["source"].startswith("Passive TCP acknowledgement RTT. These samples describe the recording connection")
    assert cw.latency(cw.data(REVIEW_LOG, state)) is None
    assert cw.boss_hp(d, state) == [["Ice Queen", "4,000", "10,000", "40.0%", "1:00.00"]]
    assert cw.boss_hp(d, {**state, "enemy": "a1,a2"}) == []
    found = cw.enemy_encounters(d, state, names)
    assert [(row["name"], row["ids"], row["count"], row["filter"], row["types"], row["damage"], row["lifespan"]) for row in found["rows"]] == [
        ("Ice Queen", "b1", 1, "Filter (boss)", "2001", "3,000", "0.5–3.1s"),
        ("Frost Hound", "a1,a2", 2, "Filter", "2002", "700", "6.0–7.5s"),
        ("Ice Wraith", "c1", 1, "Filter", "4242", "100", "9.5–9.5s")]
    assert not found["named_note"] and found["folded"]["title"] == "1 unnamed summon the party never struck"
    assert found["folded"]["note"] == ("The game data gives it no name. It took no damage and struck the party 1 time: part of "
                                       "the boss's attacks rather than enemies to fight.")
    assert cw.enemy_encounters(cw.data(fight, pvp), pvp)["rows"][0]["filter"] == "Filter (opponent)"


def test_the_review_graph_and_enemies(qapp):
    from PySide6.QtTest import QTest
    from aion2calc.gui.combat_review_charts import PingChart, RateChart
    app = FakeApp()
    app.log_server.review_log = _fight()
    page = _page(app)
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: "Enemy encounters" in _labels(view) and "Ice Wraith" in " ".join(_labels(view)))
    texts = _labels(view)
    assert all(t in texts for t in ("Bars: total damage done per second", "Gold line: trailing 10-second average",
                                    "Red line: boss HP (right axis)", cw.GRAPH_HINT, "Recorder ping · TestSorc ✓ · Zikel",
                                    "Average 48.8 ms · Minimum 42.0 ms · Maximum 55.5 ms · 2 samples", cw.HP_NOTE,
                                    "Damage done per second · 1s buckets · red: boss HP, right scale"))
    assert all(c in _cells(view) for c in ("4,000", "40.0%", "1:00.00", "0.5–3.1s", "700"))
    assert len(view.findChildren(PingChart)[0].ping["points"]) == 2
    assert any("Frost Hound" in t and "×2" in t for t in texts)
    assert "1 unnamed summon the party never struck" in [f.button.text() for f in view.findChildren(Section)]
    settle(lambda: any(label.width() == 22 and not label.pixmap().isNull() for label in view.findChildren(QLabel)
                       if label.isVisibleTo(view)))                         # the boss's bundled portrait
    # the moment inspected: by the pointer's move, a click or the arrow keys
    chart = view.chart
    assert isinstance(chart, RateChart) and chart.model["mode"] == "total"
    chart.inspect(2.2)
    texts = _labels(view)
    assert "<b>0:02.20</b> · Total damage done: 1,500/s · 10 s average: 1,000/s" in texts
    assert "1,500/s" in _cells(view) and "10,000" in _cells(view)
    chart.setFocus()
    QTest.keyClick(chart, Qt.Key_Right)
    assert chart.at == _pytest_approx(3.2)
    # the series: one hidden, all shown again; the players' style
    _click(view, "TestCleric · Healing")
    assert "TestCleric · Healing" not in _buttons(view)
    _click(view, "Show all series")
    assert "TestCleric · Healing" in _buttons(view)
    _choose(view, "Graph style", "players")
    assert view.chart.model["mode"] == "players" and any(t.startswith("Class-colored lines") for t in _labels(view))
    # an enemy chosen narrows the review to it; all again
    _find(view, QPushButton, lambda b: b.accessibleName() == "Filter to Frost Hound").click()
    assert view.state["enemy"] == "a1,a2" and "700" in _cells(view) and "4,000" not in _cells(view)
    assert _find(view, QPushButton, lambda b: b.accessibleName() == "Filter to Frost Hound").objectName() == "primary"
    _click(view, cw.ALL_ENEMIES)
    assert view.state["enemy"] == "" and "4,000" in _cells(view)
    # the options: no graph; pets apart, a pet chosen becoming its owner when they are combined again
    _find(view, QCheckBox, lambda c: c.text() == "Graph").setChecked(False)
    assert not [c for c in view.findChildren(RateChart) if c.isVisibleTo(view)]
    _find(view, QCheckBox, lambda c: c.text() == "Graph").setChecked(True)
    _find(view, QCheckBox, lambda c: c.text() == "Combine pets with owner").setChecked(False)
    assert any("Spirit" in t for t in _labels(view))
    _choose(view, "Player", "pet1")
    _find(view, QCheckBox, lambda c: c.text() == "Combine pets with owner").setChecked(True)
    assert view.state["actor"] == "p1"


def _timed():
    """The fuller fight with its skills' ids (the sorcerer's Flame Burst has its icon bundled, Spark none), and four of
    the sorcerer's Sparks within a second: the timeline's three stacks hold three of them and leave the fourth out."""
    fight = _fight()
    seg = fight["segments"][0]
    for e in seg["events"]:
        if e.get("skill") == "Flame Burst":
            e["skill_id"] = 11010001
    seg["events"] += [{"kind": "damage", "t": 20.0 + i / 10, "source": "p1", "target": "b1", "amount": 10, "skill": "Spark",
                       "skill_id": 13100002} for i in range(4)]
    return fight


def test_the_review_events_and_timeline_words():
    fight = _timed()
    state = cw.fresh_state()
    d = cw.data(fight, state)
    events = cw.visible_events(d, state)
    # the events' list: every event, each column's values by their counts, then their names
    m = cw.event_list(d, events, state)
    assert m["summary"] == ("<b>16</b> events · total <b>5,290</b> · average 378 · smallest 0 · largest 1,500 · 0.500s to "
                            "20.300s") and m["pager"] == "1 / 1 · 16 events" and not m["filtered"] and not m["clear"]
    columns = {c["key"]: c for c in m["columns"]}
    assert [(o["name"], o["count"]) for o in columns["kind"]["values"]] == [("damage", 12), ("death", 2), ("heal", 1),
                                                                             ("revive", 1)]
    assert [(o["name"], o["count"]) for o in columns["source"]["values"]][:3] == [("TestSorc ✓ · Zikel", 9),
                                                                                  (cw.UNKNOWN, 3), ("Ice Queen", 1)]
    assert columns["source"]["values"][1]["value"] == "" and columns["kind"]["caption"] == "Event"
    assert [o["name"] for o in columns["skill"]["values"]][:3] == ["Flame Burst", "Spark", "—"]
    assert m["rows"][0] == {"time": "0.500s", "kind": "damage", "source": "p1", "target": "b1", "skill": "Flame Burst",
                            "amount": "1,000"}
    assert [(r["kind"], r["skill"], r["amount"]) for r in m["rows"] if r["kind"] in ("death", "revive")] == [
        ("death", "—", "—"), ("death", "—", "—"), ("revive", "—", "0")]
    # a column's values chosen and a smallest amount: the column counts what the other filters keep
    state["ef"]["sel"]["kind"] = ["damage"]
    state["ef"]["a0"] = "500"
    m = cw.event_list(d, events, state)
    assert m["summary"] == ("<b>4</b> of 16 events · total <b>3,800</b> · average 950 · smallest 500 · largest 1,500 · "
                            "0.500s to 3.100s") and m["clear"]
    columns = {c["key"]: c for c in m["columns"]}
    assert columns["kind"]["caption"] == "Event · 1 of 2"                      # deaths have no amount to keep
    assert [(o["name"], o["count"]) for o in columns["kind"]["values"]] == [("damage", 4), ("heal", 1)]
    # sorted by amount, largest first, the earlier first of equal amounts
    state["ef"].update(sort="amount", a0="", sel={})
    m = cw.event_list(d, events, state)
    assert [r["amount"] for r in m["rows"][:3]] == ["1,500", "1,000", "800"] and m["clear"] and not m["filtered"]
    assert [r["time"] for r in m["rows"] if r["amount"] == "10"] == ["20.000s", "20.100s", "20.200s", "20.300s"]
    # none kept; a value kept that none of the events has; a time range; bounds as typed
    state["ef"].update(sort="time", sel={"kind": []})
    m = cw.event_list(d, events, state)
    assert m["count"] == 0 and m["summary"] == "" and m["columns"][0]["caption"] == "Event · 0 of 4"
    state["ef"]["sel"] = {"skill": ["Gone"]}
    skills = cw.event_list(d, events, state)["columns"][3]
    assert ("Gone", 0) in [(o["name"], o["count"]) for o in skills["values"]] and skills["caption"] == "Ability · 1 of 8"
    state["ef"].update(sel={}, t0="3", t1=" 6 ")
    assert [r["time"] for r in cw.event_list(d, events, state)["rows"]] == ["3.100s", "3.500s", "5.000s", "5.000s", "6.000s"]
    assert (cw.bound(""), cw.bound("abc"), cw.bound("1e1"), cw.bound(" 5 "), cw.bound(None)) == (None, None, 10.0, 5.0, None)
    # the filters kept for the encounter, fresh for another; a hundred to a page, the page kept within the pages
    assert cw.filters_of(state)["t0"] == "3" and cw.filters_of({**state, "segment": 1})["t0"] == ""
    many = {**d, "events": [{"kind": "damage", "t": i / 10, "source": "p1", "target": "b1", "amount": i} for i in range(250)]}
    state = cw.fresh_state()
    state["page"] = 2
    m = cw.event_list(many, many["events"], state)
    assert (len(m["rows"]), m["pager"], m["rows"][0]["time"]) == (50, "3 / 3 · 250 events", "20.000s")
    state["page"] = 9
    assert cw.event_list(many, many["events"], state)["page"] == 2 and state["page"] == 2
    # the timeline: a lane per player of the party, each effect in the window three stacks deep
    state = cw.fresh_state()
    t = cw.timeline(d, events, state, set(), set(), {})
    assert (t["span"], t["width"], t["range"], t["earlier"], t["later"]) == (30, 960.0, "0:00–0:30", False, True)
    assert [lane["label"] for lane in t["lanes"]] == ["TestSorc ✓ · Zikel", "TestCleric"]
    assert t["visibility"] == "Player timeline visibility · 2 / 2 shown"
    sorc, cleric = t["lanes"]
    assert [(round(k["x"], 1), k["y"], k["tag"]) for k in sorc["marks"]][:2] == [(16.0, 3, "001"), (38.4, 30, "age")]
    assert [k["y"] for k in sorc["marks"] if k["tag"] == "002"] == [3, 30, 57] and t["omitted"] == 1
    assert "1 crowded markers omitted in this window; zoom in or use Events for every effect. Unavailable" in t["note"]
    assert sorc["marks"][0]["icon"] == SKILL and sorc["marks"][0]["fill"] == cr.class_colour("sorcerer", {})
    assert sorc["marks"][0]["detail"] == "0:00.50 · TestSorc ✓ · Zikel → Ice Queen · Flame Burst · 1,000"
    assert [(k["tag"], k["fill"], k["y"]) for k in cleric["marks"]] == [("eal", cw.HEALED, 3), ("ath", cw.DEATH, 2),
                                                                         ("ath", cw.DEATH, 2)]
    assert cleric["marks"][1]["detail"] == "0:05.00 · Unknown / not recorded → TestCleric · death · 0"
    assert [(k["x"], k["text"]) for k in t["ticks"] if k["long"]] == [(0.0, "0:00"), (160.0, "0:05"), (320.0, "0:10"),
                                                                     (480.0, "0:15"), (640.0, "0:20"), (800.0, "0:25"),
                                                                     (960.0, "0:30")]
    assert t["ticks"][0]["at"] == 22.0 and t["ticks"][-1]["at"] == 938.0
    # damage taken: the hits on a player in their lane, in orange; no skills, heals or deaths
    taken = cw.timeline(d, cw.visible_events(d, {**state, "metric": "taken"}), {**state, "metric": "taken"}, set(), set(), {})
    assert [(lane["label"], [k["fill"] for k in lane["marks"]]) for lane in taken["lanes"]] == [
        ("TestCleric", [cw.TAKEN, cw.TAKEN])]
    quiet = cw.timeline(d, events, {**state, "skills": False, "heals": False, "deaths": False}, set(), set(), {})
    assert all(not lane["marks"] for lane in quiet["lanes"])
    # pets apart: the pet's own lane
    apart = {**state, "combine": False}
    d_apart = cw.data(fight, apart)
    assert [lane["label"] for lane in cw.timeline(d_apart, cw.visible_events(d_apart, apart), apart, set(), set(), {})["lanes"]] == [
        "TestSorc ✓ · Zikel", "Spirit", "TestCleric"]
    # a lane hidden, one collapsed; the whole encounter; the window kept within the encounter
    t = cw.timeline(d, events, state, {"p2"}, {"p1"}, {})
    assert t["visibility"] == "Player timeline visibility · 1 / 2 shown" and [p["shown"] for p in t["players"]] == [True, False]
    assert [(lane["id"], lane["collapsed"], lane["marks"]) for lane in t["lanes"]] == [("p1", True, [])]
    whole = cw.timeline(d, events, {**state, "timeline_window": 0}, set(), set(), {})
    assert (whole["span"], whole["width"], whole["range"], whole["latest"]) == (120, 3840.0, "0:00–2:00", 0.0)
    assert [k["text"] for k in whole["ticks"] if k["long"]] == ["0:00", "0:25", "0:50", "1:15", "1:40"]
    late = {**state, "timeline_start": 200}
    assert cw.timeline(d, events, late, set(), set(), {})["range"] == "1:30–2:00" and late["timeline_start"] == 90
    cw.moved_window(late, 120, -1)
    assert late["timeline_start"] == 60
    cw.centred_window(late, 50.0, 120)
    assert late["timeline_start"] == 35
    whole_window = {**late, "timeline_window": 0}
    cw.centred_window(whole_window, 100.0, 120)
    assert whole_window["timeline_start"] == 40
    assert cw.skill_icon(11010001) == SKILL and cw.skill_icon("11010001") == SKILL
    assert cw.skill_icon(0) == cw.skill_icon("abc") == cw.skill_icon(1.5) == cw.skill_icon(None) == ""
    # what the encounter's records leave out
    assert cw.notes_line(d) == ("Movement replay is unavailable: no positions were recorded (recordings made before 0.2.350 "
                                "have none).")
    bare = {"events": [{"kind": "heal", "t": 1, "source": "p2"}], "segment": {"positions": [[0, 0]]}}
    assert cw.notes_line(bare) == ("Some healing recipients are not carried by their packet variant. No death markers "
                                   "recorded; zero counts do not establish a deathless run. ")


def test_the_review_events_and_timeline(qapp):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDoubleSpinBox
    from aion2calc.gui.combat_review_views import FilterPopup, Timeline
    app = FakeApp()
    fight = _timed()
    fight["segments"][0]["events"] += [{"kind": "damage", "t": 30 + i / 10, "source": "p1", "target": "b1", "amount": 1,
                                        "skill": "Tick"} for i in range(140)]
    app.log_server.review_log = fight
    page = _page(app)
    page.open_review("shared", "log0001")
    view = page.review_page
    # drawn with every answer in: the parses, the community's names and the boss's portrait (each draws it again)
    settle(lambda: "Enemy encounters" in _labels(view) and view.ranks is not None and view.names is not None
           and not view.awaiting)

    def chosen(name):
        return _find(view, QPushButton, lambda b: b.accessibleName() == name)
    # the Table view first, with the summary; the note on what the records leave out
    assert view.summary is not None and view.state["view"] == "table"
    assert chosen("Table view").objectName() == "primary" and chosen("Events view").objectName() == "small"
    assert any(t.startswith("Movement replay is unavailable") for t in _labels(view))
    # the Events view: the events' list, a hundred to a page
    chosen("Events view").click()
    assert view.summary is None and view.events_summary.text().startswith("<b>156</b> events · total <b>5,430</b>")
    assert "1 / 2 · 156 events" in _labels(view) and "0.500s" in _cells(view) and "Flame Burst" in _cells(view)
    _click(view, "Next")
    assert "2 / 2 · 156 events" in _labels(view) and "43.900s" in _cells(view) and "0.500s" not in _cells(view)
    _click(view, "Next")
    assert "2 / 2 · 156 events" in _labels(view)
    _click(view, "Previous")
    assert "1 / 2 · 156 events" in _labels(view)
    # a column's filter: its values with their counts, under its button; one left out, the list on its first page
    _click(view, "Next")
    _click(view, "Event ▾")
    popup = view.popup
    assert isinstance(popup, FilterPopup) and popup.isVisible() and view.state["ef_open"] == "kind"
    assert [tick.text() for tick in popup.ticks] == ["damage", "death", "heal", "revive"]
    assert "152" in [label.text() for label in popup.findChildren(QLabel)]
    assert popup.search.accessibleName() == "Find a value of Event"
    popup.ticks[1].setChecked(False)
    assert view.events_summary.text().startswith("<b>154</b> of 156 events") and popup.isVisible()
    assert view.state["page"] == 0 and "Event · 3 of 4 ▾" in _buttons(view)
    assert popup.anchor() is view.filter_buttons["kind"] and view.filter_buttons["kind"].objectName() == "primary"
    # found by the search, only the found kept; none; all again
    popup.search.setText("REV")
    assert [row.isHidden() for row in popup.rows] == [True, True, True, False] and view.state["ef_search"]["kind"] == "REV"
    popup.keep_found()
    assert view.events_summary.text().startswith("<b>1</b> of 156 events") and "Event · 1 of 4 ▾" in _buttons(view)
    popup.keep_none()
    assert cw.NO_MATCH in _labels(view) and "No recorded events." in _labels(view)
    popup.keep_all()
    assert view.events_summary.text().startswith("<b>156</b> events") and "Event ▾" in _buttons(view)
    # its button closes it; opened again, it finds as its search was left
    _click(view, "Event ▾")
    assert not popup.isVisible() and view.state["ef_open"] == ""
    _click(view, "Event ▾")
    assert popup.isVisible() and popup.search.text() == "REV" and [row.isHidden() for row in popup.rows][0]
    popup.hide()
    # a time and an amount range, read once typed; the sort; the filters let go
    field = _find(view, QLineEdit, lambda f: f.accessibleName() == "Time from (seconds)")
    field.setText("20")
    field.editingFinished.emit()
    assert view.events_summary.text().startswith("<b>144</b> of 156 events")
    field = _find(view, QLineEdit, lambda f: f.accessibleName() == "Largest amount")
    field.setText("5")
    field.editingFinished.emit()
    assert view.events_summary.text() == ("<b>140</b> of 156 events · total <b>140</b> · average 1 · smallest 1 · largest "
                                          "1 · 30.000s to 43.900s")
    assert _find(view, QLineEdit, lambda f: f.accessibleName() == "Time from (seconds)").text() == "20"
    _click(view, "Clear filters")
    _choose(view, "Sort", "amount")
    QCoreApplication.processEvents()
    assert view.events_table.cell(1, 0).text() == "2.700s" and view.events_table.cell(1, 5).text() == "1,500"   # largest
    _click(view, "Clear filters")
    assert view.events_summary.text().startswith("<b>156</b> events") and "Clear filters" not in _buttons(view)
    # the Timeline view: the window's ruler over a lane per player
    chosen("Timeline view").click()
    timeline = view.timeline
    assert isinstance(timeline, Timeline) and view.events_summary is not None
    texts = _labels(view)
    assert all(t in texts for t in ("Recorded effect timeline", "Encounter time", "0:00–0:30", cw.EFFECT_HINT))
    assert any(t.startswith("Icons are recorded hits/heals") and "1 crowded markers omitted" in t for t in texts)
    assert view.lanes_fold.button.text() == "Player timeline visibility · 2 / 2 shown"
    names = [label.text() for cell in timeline.cells for label in cell.findChildren(QLabel)]
    assert any("TestSorc ✓ · Zikel" in n for n in names) and any("TestCleric" in n for n in names)
    assert not _find(view, QPushButton, lambda b: b.text() == "Earlier").isEnabled()
    timeline.tracks.grab()                                                     # its markers drawn
    timeline.ruler.grab()
    settle(lambda: view._skill_picture(SKILL) is not None)                     # Flame Burst's bundled icon
    # the window: later, the whole encounter, a start typed, scrubbed
    _click(view, "Later")
    assert "0:30–1:00" in _labels(view) and view.state["timeline_start"] == 30
    _choose(view, "Window", 0)
    assert "0:00–2:00" in _labels(view) and view.timeline_model["width"] == 3840.0
    _choose(view, "Window", 30)
    _find(view, QDoubleSpinBox, lambda s: s.accessibleName() == "Start").setValue(12.5)
    assert "0:12–0:42" in _labels(view)
    view.scrub.setValue(0)
    assert "0:00–0:30" in _labels(view)
    # an effect inspected by a click, then by the arrow keys along a lane and to the lane beside it
    tracks = view.timeline.tracks
    lanes = view.timeline_model["lanes"]
    first = lanes[0]["marks"][0]
    assert tracks.at(QPointF(first["x"] + 5, first["y"] + 5)) == (0, 0) and tracks.at(QPointF(500, 70)) is None
    QTest.mouseClick(tracks, Qt.LeftButton, Qt.NoModifier, QPoint(round(first["x"]) + 5, first["y"] + 5))
    assert view.effect == first["detail"] and view.effect_words.text() == first["detail"]
    QTest.keyClick(tracks, Qt.Key_Right)
    assert view.effect == "0:01.20 · Spirit → Ice Queen · Spirit Strike · 500"
    QTest.keyClick(tracks, Qt.Key_Down)
    assert view.effect == "0:03.50 · TestCleric → TestCleric · Heal · 600"
    # lanes collapsed, hidden, shown again from the lanes' visibility (kept open), all expanded
    chosen("Collapse TestSorc ✓ · Zikel").click()
    assert view.lanes_folded == {"p1"} and "Timeline collapsed" in _labels(view)
    chosen("Expand TestSorc ✓ · Zikel")
    assert view.effect_words.text() == "0:03.50 · TestCleric → TestCleric · Heal · 600"   # the effect kept
    chosen("Hide TestCleric").click()
    assert view.lanes_fold.button.text() == "Player timeline visibility · 1 / 2 shown"
    view.lanes_fold.button.click()
    _find(view, QCheckBox, lambda c: c.text() == "TestCleric").setChecked(True)
    _shown()
    assert view.lanes_fold.button.text() == "Player timeline visibility · 2 / 2 shown" and view.lanes_fold.body.isVisibleTo(view)
    _click(view, "Expand all")
    assert not view.lanes_folded
    # a click on the graph in Timeline view moves the window there
    chart = view.chart
    QTest.mouseClick(chart, Qt.LeftButton, Qt.NoModifier,
                     QPoint(round((60 + 880 * 50 / 120) * chart.width() / 1000), round(100 * chart.height() / 220)))
    assert view.state["timeline_start"] == pytest.approx(35, abs=0.5)
    # the Timeline option turned off; the Timeline view turns it on again
    _find(view, QCheckBox, lambda c: c.text() == "Timeline").setChecked(False)
    assert view.timeline is None and "Recorded effect timeline" not in _labels(view)
    chosen("Timeline view").click()
    assert view.state["timeline"] and view.timeline is not None
    # another encounter: every lane shown and open, the window at its start, nothing inspected
    view.lanes_hidden.add("p2")
    _choose(view, "Encounter", 1)
    assert (view.lanes_hidden, view.lanes_folded, view.effect, view.state["timeline_start"]) == (set(), set(), "", 0.0)
    settle(lambda: view.ranks is not None and not view.awaiting)               # its parses in, drawn again
    chosen("Table view").click()
    assert view.summary is not None and view.timeline is None


def _casting():
    """The timed fight with its casts, summarised by the app's own analyzer (``encounter_insights``): the sorcerer's
    Flame Burst twice on its cooldown (a follow-up record of the first the same press), two Sparks, a Blessing with no
    target or cooldown (a proc), the cleric's Heal once before the pull, the pet's strike (a pet's casts are not the
    party's), and the arena opponent's Arrows."""
    from aion2calc.combat import insights
    fight = _timed()
    fight["segments"][0]["casts"] = [
        {"source": "p1", "t": 0.4, "skill_id": 11010001, "skill": "Flame Burst", "target": "b1", "cooldown_ms": 8000, "cast_ms": 600},
        {"source": "p1", "t": 0.45, "skill_id": 11010001, "skill": "Flame Burst", "target": "b1"},
        {"source": "p1", "t": 8.6, "skill_id": 11010001, "skill": "Flame Burst", "target": "b1", "cooldown_ms": 8000, "cast_ms": 650},
        {"source": "p1", "t": 2.0, "skill_id": 13100002, "skill": "Spark", "target": "b1"},
        {"source": "p1", "t": 3.0, "skill_id": 13100002, "skill": "Spark", "target": "b1"},
        {"source": "p1", "t": 5.0, "skill_id": 11700001, "skill": "Blessing"},
        {"source": "p2", "t": -1.5, "skill_id": 17010001, "skill": "Heal", "target": "p2", "cooldown_ms": 3000},
        {"source": "p2", "t": 3.4, "skill_id": 17010001, "skill": "Heal", "target": "p2", "cooldown_ms": 3000},
        {"source": "pet1", "t": 1.1, "skill_id": 99990001, "skill": "Spirit Strike", "target": "b1"}]
    fight["segments"][1]["casts"] = [
        {"source": "e1", "t": 1.5, "skill_id": 12010001, "skill": "Arrow", "target": "p1", "cooldown_ms": 2000},
        {"source": "e1", "t": 4.0, "skill_id": 12010001, "skill": "Arrow", "target": "p1", "cooldown_ms": 2000}]
    fight["encounter_insights"] = insights.summarize(fight)
    return fight


def test_the_review_abilities_and_skills_words():
    fight = _casting()
    state = cw.fresh_state()
    d = cw.data(fight, state)
    events = cw.visible_events(d, state)
    # the abilities by amount: the party's damage done in the Summary, a pet's its owner's
    found = cw.abilities(d, d, events, state)
    assert [(r["actor"], r["skill"], r["amount"], r["hits"]) for r in found["rows"]] == [
        ("p1", "Flame Burst", 3300, 5), ("p1", "Spirit Strike", 500, 1), ("p1", "Spark", 40, 4)] and found["total"] == 3840
    assert cw.ability_table(found, d, state, cw.duration(d))[0] == {"actor": "p1", "cells": [
        "Flame Burst", "5", "3,300", "85.9%", "550", "660", "100", "1,500"]}          # per second on the active clock
    bars = cw.contribution(found, d["r"], state)
    assert bars["note"].startswith("Damage done by player and ability, the top 20 rows; <i>Abilities</i> lists every one.")
    assert [(b["name"], b["value"], b["share"]) for b in bars["bars"]] == [
        ("TestSorc ✓ · Zikel · Flame Burst", "3,300", 100.0), ("TestSorc ✓ · Zikel · Spirit Strike", "500", 15.15),
        ("TestSorc ✓ · Zikel · Spark", "40", 1.21)]
    taken = {**state, "metric": "taken"}
    found = cw.abilities(d, d, cw.visible_events(d, taken), taken)
    assert [(r["actor"], r["skill"]) for r in found["rows"]] == [("p2", "Frost Breath"), ("p2", "Spike")]
    assert cw.ability_table(found, d, taken, cw.duration(d))[0]["cells"][4] == "7"     # damage taken over the encounter
    healing = {**state, "metric": "healing"}
    found = cw.abilities(d, d, cw.visible_events(d, healing), healing)
    assert cw.ability_table(found, d, healing, cw.duration(d))[0]["cells"][:4] == ["Heal (heal)", "1", "600", "100.0%"]
    assert cw.contribution(found, d["r"], healing)["note"].startswith("Healing by player")
    assert cw.contribution({"rows": [], "total": 0}, d["r"], state) == {"note": cw.NO_ABILITIES, "bars": []}
    assert cw.ability_table({"rows": [{"actor": "p1", "kind": "damage", "skill": "X", "amount": 0, "hits": 1, "min": 0, "max": 0}],
                             "total": 0}, d, state, 120)[0]["cells"][3] == "0%"
    # the words: a family, a moment before the pull, a cooldown, a share
    assert (cw.family(11010001), cw.family(11000005), cw.family(None)) == (11010000, 11000005, None)
    assert (cw.signed_clock(-1.5), cw.signed_clock(65)) == ("−0:01.50", "1:05.00")
    assert (cw.cooldown_text(8000), cw.cooldown_text(12000), cw.cooldown_text(None), cw.percent(13.333), cw.percent(None)) == (
        "8.0s", "12s", "—", "13.3%", "—")
    # the presses: a follow-up record the same press, the cooldown's records counted, a skill with no target or cooldown
    # a proc
    pressed = cw.presses(fight["segments"][0]["casts"])
    assert [(c["source"], c["skill"], c["t"], c["kind"]) for c in pressed] == [
        ("p2", "Heal", -1.5, "skill"), ("p1", "Flame Burst", 0.4, "skill"), ("pet1", "Spirit Strike", 1.1, "skill"),
        ("p1", "Spark", 2.0, "skill"), ("p1", "Spark", 3.0, "skill"), ("p2", "Heal", 3.4, "skill"),
        ("p1", "Blessing", 5.0, "proc"), ("p1", "Flame Burst", 8.6, "skill")]
    # the Skills table, from the analyzer's summary: the procs hidden, then shown; a player alone
    assert cw.casts_missing(fight, d, state) == "" and cw.actions_of(fight, state)["rotation"]["totals"][0]["source"] == "p1"
    rows = cw.skill_rows(fight, d, state)
    assert [(r["source"], r["skill"], r["proc"]) for r in rows] == [("p1", "Flame Burst", False), ("p1", "Spark", False),
                                                                    ("p2", "Heal", False)]
    assert rows[0]["cells"] == ["2", "8.2s", "8.0s", "2 of 15 · 13.3%", "650 ms", "0:00.40 → 0:08.60"]
    assert rows[2]["cells"] == ["2", "4.9s", "3.0s", "2 of 40 · 5.0%", "—", "−0:01.50 → 0:03.40"]
    shown = cw.skill_rows(fight, d, {**state, "hide_procs": False})
    assert ("Blessing", True, ["1", "—", "—", "—", "—", "0:05.00 → 0:05.00"]) in [(r["skill"], r["proc"], r["cells"]) for r in shown]
    assert [r["skill"] for r in cw.skill_rows(fight, d, {**state, "actor": "p2"})] == ["Heal"]
    # why the casts can't be shown: an older log, one without casts, a combined review
    old = {k: v for k, v in fight.items() if k != "encounter_insights"}
    assert cw.casts_missing(old, d, state) == ("Skill casts are not recorded for this encounter. The live meter records them "
                                               "since 0.2.306; reopen the file with the updated app, or update the sharing "
                                               "server, to see them.")
    bare = cw.data(fight, state)
    bare["segment"] = {**bare["segment"], "casts": []}
    assert cw.casts_missing(fight, bare, state).endswith("since 0.2.306.")
    combined = {**fight, "meta": {**fight["meta"], "reconstruction": {"omitted_actions": ["casts"]}}}
    assert cw.casts_missing(combined, d, state) == cw.COMBINED_CASTS
    # an opponent's own casts, summarised here as the analyzer summarises the party's
    pvp = {**state, "segment": 1}
    foe = cw.data(fight, pvp, "e1")
    assert cw.casts_missing(fight, foe, pvp) == ""
    rotation = cw.rotation_of(foe["segment"], "e1")
    assert rotation["totals"] == [{"source": "e1", "casts": 2, "procs": 0, "per_minute": 2.0}]
    arrow = rotation["skills"][0]
    assert (arrow["skill"], arrow["casts"], arrow["average_gap"], arrow["cooldown_ms"], arrow["possible"]) == ("Arrow", 2, 2.5, 2000, 30)
    assert cw.skill_rows(fight, foe, {**pvp, "actor": "e1"})[0]["cells"][3] == "2 of 30 · 6.7%"
    silent = cw.data(fight, pvp, "e1")
    silent["segment"] = {**silent["segment"], "casts": []}
    assert cw.casts_missing(fight, silent, pvp) == cw.NO_FOE_CASTS
    # the cast timeline: a lane per player who cast, every press on the fight's clock from before the pull
    t = cw.cast_timeline(fight, d, state, {})
    assert [lane["label"] for lane in t["lanes"]] == ["TestSorc ✓ · Zikel", "TestCleric"] and t["width"] == 4374.0
    sorc, cleric = t["lanes"]
    assert [m["detail"] for m in sorc["marks"]] == [
        "0:00.40 · Flame Burst · → Ice Queen · cooldown 8.0s · cast 600 ms", "0:02.00 · Spark · → Ice Queen",
        "0:03.00 · Spark · → Ice Queen", "0:08.60 · Flame Burst · → Ice Queen · cooldown 8.0s · cast 650 ms"]
    assert round(sorc["marks"][0]["x"], 1) == 68.1 and round(sorc["marks"][0]["cast"], 1) == 21.5 and sorc["marks"][1]["cast"] is None
    assert sorc["marks"][0]["icon"] == SKILL and sorc["marks"][0]["fill"] == cr.class_colour("sorcerer", {})
    assert cleric["marks"][0]["x"] == 0.0 and cleric["marks"][0]["detail"].startswith("−0:01.50 · Heal")
    assert [k["text"] for k in t["ticks"]][:3] == ["0:00", "0:10", "0:20"] and round(t["ticks"][0]["at"], 2) == 53.75   # 1.5 s in
    procs = cw.cast_timeline(fight, d, {**state, "hide_procs": False}, {})
    assert [(m["detail"], m["fill"]) for m in procs["lanes"][0]["marks"] if "proc" in m["detail"]] == [
        ("0:05.00 · Blessing · proc or passive", cw.PROC)]
    assert [lane["id"] for lane in cw.cast_timeline(fight, d, {**state, "actor": "p2"}, {})["lanes"]] == ["p2"]
    assert cw.cast_timeline(fight, d, {**state, "actor": "pet1"}, {}) is None        # no one in view cast
    crowded = json.loads(json.dumps(fight))
    crowded["segments"][0]["casts"] += [{"source": "p1", "t": 30.0, "skill_id": 13000000 + i * 10000 + 1, "skill": f"Bolt {i}",
                                         "target": "b1"} for i in range(4)]
    assert cw.cast_timeline(crowded, cw.data(crowded, state), state, {})["lanes"][0]["omitted"] == 1


def test_the_review_abilities_and_skills(qapp):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtTest import QTest
    from aion2calc.gui.combat_review_views import ContributionBars, Timeline
    app = FakeApp()
    app.log_server.review_log = _casting()
    page = _page(app)
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: "Abilities and skills" in _labels(view) and view.ranks is not None and view.names is not None
           and not view.awaiting)

    def tab(name):
        return _find(view, QPushButton, lambda b: b.accessibleName() == name)
    # Ability contribution, first: the bars against the largest, their names and amounts on hover
    assert tab("Ability contribution tab").objectName() == "primary"
    bars = _find(view, ContributionBars, lambda w: True)
    assert [b["value"] for b in bars.bars] == ["3,300", "500", "40"] and bars.row_at(bars.ROW + bars.GAP + 2) == 1
    assert bars.height() == 3 * bars.ROW + 2 * bars.GAP and bars.grab() is not None
    # Abilities: the table, and the metric's: damage taken, healing; none in the death recaps
    tab("Abilities tab").click()
    QCoreApplication.processEvents()
    assert [view.ability_table.cell(1, c).text() for c in range(1, 9)] == ["Flame Burst", "5", "3,300", "85.9%", "550", "660",
                                                                          "100", "1,500"]
    _click(view, "Healing")
    assert "Heal (heal)" in _cells(view)
    _click(view, "Death recaps")
    assert cw.DEATHS_ABILITIES in _labels(view) and view.ability_table is None
    _click(view, "Summary")
    # Skills: the analyzer's casts, the procs hidden then shown; a player alone
    tab("Skills tab").click()
    assert cw.SKILLS_NOTE in _labels(view) and "2 of 15 · 13.3%" in _cells(view) and "−0:01.50 → 0:03.40" in _cells(view)
    settle(lambda: any(label.width() == 18 and not label.pixmap().isNull() for label in view.skills_table.findChildren(QLabel)
                       if label.isVisibleTo(view)))                                  # Flame Burst's bundled icon
    assert not any("Blessing" in t for t in _labels(view))
    _find(view, QCheckBox, lambda c: c.text() == cw.HIDE_PROCS).setChecked(False)
    assert any("Blessing" in t and ">proc<" in t for t in _labels(view)) and view.state["hide_procs"] is False
    _choose(view, "Player", "p2")
    assert not any("Flame Burst" in t for t in _labels(view)) and "−0:01.50 → 0:03.40" in _cells(view)
    _choose(view, "Player", "")
    # the cast timeline: a lane per player, a press inspected, the presses that had no room counted
    tab("Cast timeline tab").click()
    casts = view.casts
    assert isinstance(casts, Timeline) and "<b>Cast timeline</b>" in _labels(view) and cw.CASTS_NOTE in _labels(view)
    assert casts.corner.text() == "" and [lane["label"] for lane in view.casts_model["lanes"]] == ["TestSorc ✓ · Zikel", "TestCleric"]
    assert any("proc or passive" in m["detail"] for m in view.casts_model["lanes"][0]["marks"])        # procs shown here too
    first = view.casts_model["lanes"][0]["marks"][0]
    assert casts.tracks.at(QPointF(first["x"] + 4, first["y"] + 4)) == (0, 0)
    QTest.mouseClick(casts.tracks, Qt.LeftButton, Qt.NoModifier, QPoint(round(first["x"]) + 4, first["y"] + 4))
    casts.tracks.grab()
    # an opponent's own casts; an older log's none
    _choose(view, "Encounter", 1)
    settle(lambda: view.ranks is not None and not view.awaiting)
    _choose(view, "Player", "e1")
    tab("Skills tab").click()
    assert "2 of 30 · 6.7%" in _cells(view)
    tab("Hide tab").click()
    assert view.skills_table is None and view.casts is None and view.ability_table is None
    old = json.loads(json.dumps(app.log_server.review_log))
    del old["encounter_insights"]
    app.log_server.review_log = old
    view.state.update(detail="skills", segment=0, actor="")
    view.reload()
    settle(lambda: any(t.startswith("Skill casts are not recorded for this encounter.") for t in _labels(view)))


def _acting():
    """The casting fight with what the analyzer summarises beyond the casts: a buff on the sorcerer, a stun (re-applied)
    and a slow on the boss, the boss's chill on the cleric, its break gauge with a break, the sorcerer's MP, the boss's
    and a hound's casts, a chain skill; in the arena, the opponent's stance, the sorcerer's stun on them, their fear on
    the sorcerer and an imported buff; and a buff contribution estimate, as the analyzer writes one."""
    from aion2calc.combat import insights
    fight = _casting()
    seg, arena = fight["segments"]
    seg["effects"] = [
        {"target": "p1", "source": "p2", "t": 1.0, "end": 11.0, "skill_id": 17150001, "skill": "Blessing of Wind", "ended": "expired"},
        {"target": "b1", "source": "p1", "t": 4.0, "end": 6.0, "skill_id": 13070001, "skill": "Stunning Blow", "ended": "expired",
         "refreshes": 1},
        {"target": "b1", "source": "p1", "t": 8.0, "end": 9.5, "skill_id": 13020001, "skill": "Frost Chain", "ended": "removed"},
        {"target": "p2", "source": "b1", "t": 3.1, "end": 13.1, "skill_id": 90010001, "skill": "Chill"}]
    seg["gauge"] = [{"entity": "b1", "t": 0.0, "current": 1000, "max": 1000}, {"entity": "b1", "t": 2.7, "current": 400, "max": 1000},
                    {"entity": "b1", "t": 6.0, "current": 50, "max": 1000}, {"entity": "b1", "t": 9.0, "current": 1000, "max": 1000}]
    seg["hits"] = [{"t": 2.7, "player": "p1", "target": "b1", "damage": 1500, "skill_id": 11010001},
                   {"t": 6.0, "player": "p2", "target": "b1", "damage": 100, "skill_id": 17010001},
                   {"t": 7.0, "player": "p1", "target": "b1", "damage": 700, "skill_id": 11010001}]
    seg["resources"] = [{"entity": "p1", "t": 0.0, "mp": 1000, "max": 1000}, {"entity": "p1", "t": 5.0, "mp": 150},
                        {"entity": "p1", "t": 10.0, "mp": 600}]
    seg["npc_casts"] = [{"source": "b1", "t": 3.0, "skill_id": 50010001, "skill": "Frost Breath", "target": "p2"},
                        {"source": "b1", "t": 3.5, "skill_id": 50010001, "skill": "Frost Breath", "target": "p2"},
                        {"source": "a1", "t": 6.5, "skill_id": 50020001, "target": "p1"}]
    seg["chains"] = [{"player": "p1", "skill_id": 13010001, "next_id": 13100002, "next": "Spark", "t": 1.0, "end": 3.0}]
    arena["effects"] = [
        {"target": "e1", "source": "e1", "t": 1.0, "end": 5.0, "skill_id": 12150001, "skill": "Bow Stance"},
        {"target": "e1", "source": "p1", "t": 2.0, "end": 4.0, "skill_id": 13070001, "skill": "Stunning Blow", "ended": "expired"},
        {"target": "p1", "source": "e1", "t": 3.0, "end": 3.5, "skill_id": 16070001, "skill": "Terror Shot", "ended": "removed"}]
    arena["buffs"] = [{"player": "e1", "name": "Rage", "skill_id": 12990001, "start": 0.5, "end": 9.0}]
    fight["encounter_insights"] = insights.summarize(fight)
    fight["encounter_insights"]["segments"][0]["contribution"] = {
        "players": [{"player": "p1", "damage": 3300, "received": 300, "received_pct": 9.1, "adjusted_damage": 3000, "given": 0,
                     "contribution_damage": 3000},
                    {"player": "p2", "damage": 0, "received": 0, "received_pct": None, "adjusted_damage": 0, "given": 300,
                     "contribution_damage": 300}],
        "given": [{"source": "p2", "recipient": "p1", "skill": "Blessing of Wind", "skill_id": 17150001, "damage": 300}],
        "buffs": [{"source": "p2", "skill": "Blessing of Wind", "skill_id": 17150001, "group": "aura", "value_pct": 10.0, "level": 5,
                   "basis": "profile", "windows": 1}],
        "checks": [{"group": "aura", "measured_pct": 9.5, "estimated_pct": 10.0, "hits_on": 4, "hits_off": 1, "pairs": 1}],
        "unlisted_source_damage": 0}
    return fight


def _words(cells):
    """A model's rows with each cell as its words: an actor by id, a skill by name, rich text as given."""
    out = []
    for row in cells:
        line = []
        for c in row:
            if not isinstance(c, dict):
                line.append(c)
            elif "actor" in c:
                line.append(("actor", c["actor"]) + (("boss",) if c.get("boss") else ()))
            elif "skill" in c:
                line.append(("skill", c["skill"]))
            elif "html" in c:
                line.append(("html", c["html"]))
            elif "ref" in c:
                line.append(("ref", _dict_id(c["ref"])))
            else:
                line.append(tuple(c.items()))
        out.append(line)
    return out


def _dict_id(x):
    return x.get("id") if isinstance(x, dict) else x


def test_the_review_casts_buffs_and_break_gauge_words():
    from aion2calc.gui.results import MUTED
    fight = _acting()
    state = cw.fresh_state()
    d = cw.data(fight, state)
    muted = lambda words: f" <span style='color: {MUTED};'>{words}</span>"
    # why there's nothing to show: a combined review, an older log, a log without such records
    assert cw.actions_missing(fight, d, state) == "" and cw.omitted_actions(fight, state) == ""
    combined = {**fight, "meta": {**fight["meta"], "reconstruction": {"omitted_actions": ["casts"]}}}
    assert cw.actions_missing(combined, d, state) == cw.COMBINED_ACTIONS
    old = {k: v for k, v in fight.items() if k != "encounter_insights"}
    assert cw.actions_missing(old, d, state).endswith("since 0.2.306; reopen the file with the updated app, or update the "
                                                      "sharing server, to see them.")
    bare = cw.data(fight, state)
    bare["segment"] = {k: v for k, v in bare["segment"].items() if k not in ("casts", "effects", "gauge", "resources", "npc_casts")}
    assert cw.actions_missing(fight, bare, state).endswith("since 0.2.306.")
    limited = json.loads(json.dumps(fight))
    limited["encounter_insights"]["segments"][0]["actions"]["omitted_actions"] = {"buffs": 3, "crowd_control": 1, "debuffs": 0}
    assert cw.omitted_actions(limited, state) == "Row limits omitted 3 buffs rows, 1 crowd control rows."
    # the rotation: each player's casts, the recording player's MP, the chain skill followed
    t = cw.rotation_tab(fight, d, state)
    assert _words(t["totals"]) == [[("actor", "p1"), "4", "2.0", "1", "0"], [("actor", "p2"), "2", "1.0", "0", "0"]]
    assert _words(t["mp"]) == [[("actor", "p1"), "1,000 → 600", "150", ("html", "1,000"), "850", "425", "450",
                                ("html", "5.0s" + muted("4.2%"))]]
    assert _words(t["chains"]) == [[("actor", "p1"), ("skill", "Spark"), "1", "1", "100.0%"]] and t["has_chains"]
    alone = cw.rotation_tab(fight, d, {**state, "actor": "p2"})
    assert (len(alone["totals"]), alone["mp"], alone["chains"], alone["has_chains"]) == (1, [], [], True)
    pvp = {**state, "segment": 1}
    foe = cw.data(fight, pvp, "e1")
    assert _words(cw.rotation_tab(fight, foe, {**pvp, "actor": "e1"})["totals"]) == [[("actor", "e1"), "2", "2.0", "0", "0"]]
    silent = cw.data(fight, pvp, "e1")
    silent["segment"] = {**silent["segment"], "casts": []}
    assert cw.rotation_tab(fight, silent, {**pvp, "actor": "e1"}) == {"missing": cw.NO_FOE_CASTS}
    # the buffs and debuffs: the party's buff, the debuffs on the boss (marked), the boss's effect on the party
    t = cw.effects_tab(fight, d, state)
    assert t["note"] == cw.WINDOWS_NOTE and [x["title"] for x in t["tables"]] == [
        "Buffs on the party", "Debuffs on enemies", "Enemy effects on the party"]
    assert _words(t["tables"][0]["rows"]) == [[("actor", "p1"), ("skill", "Blessing of Wind"), "8.3%", "10.0s", "1",
                                               (("sources", [("p2", 1)]),)]]
    assert [row[0] for row in _words(t["tables"][1]["rows"])] == [("actor", "b1", "boss"), ("actor", "b1", "boss")]
    assert [len(x["rows"]) for x in cw.effects_tab(fight, d, {**state, "actor": "p2"})["tables"]] == [1, 0, 1]
    # an opponent's: on them by their side, by the party, theirs on others, and the imported buff windows
    t = cw.effects_tab(fight, foe, {**pvp, "actor": "e1"})
    assert [(x["title"], _words(x["rows"])) for x in t["tables"]] == [
        ("Buffs on them", [[("actor", "e1"), ("skill", "Bow Stance"), "6.7%", "4.0s", "1", (("sources", [("e1", 1)]),)]]),
        ("Your party's effects on them", [[("actor", "e1"), ("skill", "Stunning Blow"), "3.3%", "2.0s", "1",
                                           (("sources", [("p1", 1)]),)]]),
        ("Their effects on others", [[("actor", "p1"), ("skill", "Terror Shot"), "0.8%", "0.5s", "1", (("sources", [("e1", 1)]),)]]),
        ("Imported buff windows", [[("skill", "Rage"), "0:00.50 → 0:09.00"]])]
    assert cw.effects_tab(fight, silent, {**pvp, "actor": "e1"})["tables"][-1]["title"] == "Imported buff windows"
    nothing = cw.data(fight, pvp, "e1")
    nothing["segment"] = {**nothing["segment"], "effects": [], "buffs": []}
    assert cw.effects_tab(fight, nothing, {**pvp, "actor": "e1"}) == {"missing": cw.NO_EFFECTS_RECORDED}
    groups = cw.effect_groups([{"target": "x", "skill_id": 5, "t": 0, "end": 4, "source": "a"},
                               {"target": "x", "skill_id": 5, "t": 2, "end": 6, "source": "a"},
                               {"target": "x", "skill_id": 5, "t": 8, "end": 9}], 10)
    assert [(g["seconds"], g["applications"], g["sources"]) for g in groups] == [
        (7.0, 3, [{"source": "a", "applications": 2}, {"source": None, "applications": 1}])]   # overlaps once
    # the crowd control: by player, each application with how it ended
    t = cw.cc_tab(fight, d, state)
    assert t["note"] == cw.CC_NOTE and [x["title"] for x in t["tables"]] == ["", "Each application"]
    assert t["tables"][0]["rows"] == [[{"actor": "p1"}, "Stun", "2", "2.0s", "2", "0"], [{"actor": "p1"}, "Slow", "1", "1.5s", "0", "1"]]
    assert _words(t["tables"][1]["rows"]) == [
        ["0:04.00", ("actor", "p1"), ("actor", "b1"), ("skill", "Stunning Blow"), ("html", "Stun"),
         ("html", "2.00s" + muted("re-applied 1×")), "Ran its duration"],
        ["0:08.00", ("actor", "p1"), ("actor", "b1"), ("skill", "Frost Chain"), ("html", "Slow" + muted("soft")), ("html", "1.50s"),
         "Removed early"]]
    t = cw.cc_tab(fight, cw.data(fight, pvp), pvp)                       # PvP: what the opponent landed on the party
    assert [x["title"] for x in t["tables"]] == ["", "Each application", "Crowd control on your party",
                                                "Each application on your party"]
    assert _words(t["tables"][3]["rows"])[0][:5] == ["0:03.00", ("actor", "p1"), ("actor", "e1"), ("skill", "Terror Shot"),
                                                     ("html", "Fear")]
    older = json.loads(json.dumps(fight))
    del older["encounter_insights"]["segments"][1]["actions"]["crowd_control_received"]
    assert cw.cc_tab(older, cw.data(older, pvp), pvp)["tables"][2] == {"title": "Crowd control on your party", "columns": [],
                                                                       "rows": [], "older": True}
    t = cw.cc_tab(fight, foe, {**pvp, "actor": "e1"})
    assert [(x["title"], len(x["rows"])) for x in t["tables"]] == [("Their crowd control on your party", 1),
                                                                   ("Your party's crowd control on them", 1)]
    assert cw.cc_tab(fight, nothing, {**pvp, "actor": "e1"}) == {"missing": cw.NO_CC_RECORDED}
    # the break gauge: its line, readings and break, each player's share
    t = cw.stagger_tab(fight, d, state)
    boss = t["bosses"][0]
    assert (boss["title"], boss["elite"], boss["line"]) == ("Ice Queen", False, "Gauge 1,000 · 4 readings · 950 drained · 1 break: "
                                                                               "0:06.00 for 3.0s")
    assert [(round(x), round(y, 1)) for x, y in boss["gauge"]["points"]] == [(0, 4.0), (22, 65.2), (50, 100.9), (75, 4.0)]
    assert boss["gauge"]["breaks"] == [{"x": 50.0, "width": 25.0, "tip": "Broken 0:06.00 → 0:09.00 (3.0s)"}]
    assert boss["rows"] == [[{"actor": "p1"}, "600", "63.2%", "700"], [{"actor": "p2"}, "350", "36.8%", "100"]]
    assert cw.stagger_tab(fight, cw.data(fight, pvp), pvp)["bosses"] == []
    # the boss casts: a boss's skill aimed at the cleric twice, a hound's (an add), the casts in order
    t = cw.boss_tab(fight, d, state)
    assert _words(t["skills"]) == [
        [("ref", "b1"), ("skill", "Frost Breath"), "2", "0:03.00 → 0:03.50", (("aimed", [("p2", 2)]),)],
        [("html", "Frost Hound" + muted("boss's add")), ("skill", "50020001"), "1", "0:06.50 → 0:06.50", (("aimed", [("p1", 1)]),)]]
    assert _words(t["order"]) == [["0:03.00 → 0:03.50", ("ref", "b1"), ("skill", "Frost Breath"), "×2", ("actor", "p2")]]
    assert t["notes"] == ["Not listed here: 1 cast by the bosses' adds and clones, counted in the skills above and listed on the "
                          "movement replay."]
    assert cw.boss_tab(fight, d, {**state, "actor": "p1"})["order"] == []
    assert cw.boss_tab(fight, cw.data(fight, pvp), pvp) == {"note": cw.BOSS_NOTE, "missing": cw.NO_BOSS_CASTS}
    assert (cw.add_name({"name": "Frost Hound"}), cw.add_name({"name": "Unnamed summon", "mob_code": 9}, {"9": "Ice Wisp"}),
            cw.add_name({"name": "#77", "mob_code": 77}), cw.add_name(None)) == ("Frost Hound", "Ice Wisp", "Clone", "Clone")
    # the buff contribution: per second on the active clock; who added what; the credited buffs; the check
    t = cw.contribution_tab(fight, d, state)
    assert _words(t["players"]) == [[("actor", "p1"), "550", ("html", "−50" + muted("9.1%")), "500", "+0", "500"],
                                    [("actor", "p2"), "0", ("html", "−0" + muted("—")), "0", "+50", "50"]]
    assert _words(t["given"]) == [[("actor", "p2"), ("skill", "Blessing of Wind"), ("actor", "p1"), "300", "50"]]
    assert _words(t["buffs"]) == [[("actor", "p2"), ("skill", "Blessing of Wind"), "Damage Boost aura", "10.0%", "5",
                                   "Official profile", "1"]]
    assert t["checks"] == [["Damage Boost aura", "+9.5%", "+10.0%", "4 / 1", "1"]] and t["unlisted"] == ""
    stranger = json.loads(json.dumps(fight))
    stranger["encounter_insights"]["segments"][0]["contribution"]["given"][0].update(source="zz", recipient=None)
    assert cw.contribution_tab(stranger, d, state)["given"][0][0] == "Not in the roster"
    assert cw.contribution_tab(stranger, d, state)["given"][0][2] == "Not recorded"
    assert cw.contribution_tab(fight, cw.data(fight, pvp), pvp) == {"missing": cw.CONTRIBUTION_NONE}
    early = json.loads(json.dumps(fight))
    early["encounter_insights"]["version"] = 3
    assert cw.contribution_tab(early, d, state) == {"missing": cw.CONTRIBUTION_OLD}


def test_the_review_casts_buffs_and_break_gauge(qapp):
    from aion2calc.gui.combat_review_views import GaugeChart
    app = FakeApp()
    app.log_server.review_log = _acting()
    page = _page(app)
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: "Casts, buffs and break gauge" in _labels(view) and view.ranks is not None and view.names is not None
           and not view.awaiting)

    def tab(name):
        _find(view, QPushButton, lambda b: b.accessibleName() == f"{name} actions").click()
        return _labels(view), _cells(view)
    # Rotation first: the casts, the MP and the chain skill; "&" in a tab's words no shortcut
    assert _find(view, QPushButton, lambda b: b.accessibleName() == "Rotation actions").objectName() == "primary"
    assert _find(view, QPushButton, lambda b: b.accessibleName() == "Buffs & debuffs actions").text() == "Buffs && debuffs"
    labels, cells = _labels(view), _cells(view)
    assert all(t in labels for t in (cw.ROTATION_NOTE, "<b>MP</b>", cw.MP_NOTE, cw.SKILLS_ABOVE, "<b>Chain skills</b>"))
    assert all(c in cells for c in ("2.0", "1,000 → 600", "425", "100.0%"))
    # the buffs and debuffs, the crowd control, the break gauge with its chart
    labels, cells = tab("Buffs & debuffs")
    assert "<b>Debuffs on enemies</b>" in labels and "8.3%" in cells and any("boss</span>" in t for t in labels)
    labels, cells = tab("Crowd control")
    assert cw.CC_NOTE in labels and "<b>Each application</b>" in labels and "Ran its duration" in cells and "Removed early" in cells
    labels, cells = tab("Break gauge")
    assert "Gauge 1,000 · 4 readings · 950 drained · 1 break: 0:06.00 for 3.0s" in labels and "63.2%" in cells
    chart = _find(view, GaugeChart, lambda w: True)
    assert len(chart.gauge["points"]) == 4 and chart.grab() is not None
    # the boss casts, the buff contribution, Hide
    labels, cells = tab("Boss casts")
    assert "×2" in cells and any("Frost Hound" in t and "boss's add" in t for t in labels)
    assert any(t.startswith("Not listed here: 1 cast") for t in labels)
    labels, cells = tab("Buff contribution")
    assert all(c in cells for c in ("550", "+50", "Damage Boost aura", "Official profile", "+9.5%"))
    labels, cells = tab("Hide")
    assert "8.3%" not in cells and "550" not in cells and view.state["actions"] == ""
    # an opponent's own: their buffs and crowd control
    _choose(view, "Encounter", 1)
    settle(lambda: view.ranks is not None and not view.awaiting)
    _choose(view, "Player", "e1")
    labels, cells = tab("Buffs & debuffs")
    assert all(t in labels for t in ("<b>Buffs on them</b>", "<b>Your party's effects on them</b>", "<b>Imported buff windows</b>"))
    labels, cells = tab("Crowd control")
    assert cw.CC_FOE_NOTE in labels and "<b>Their crowd control on your party</b>" in labels
    # a combined review holds none of them
    combined = json.loads(json.dumps(app.log_server.review_log))
    combined["meta"]["reconstruction"] = {"omitted_actions": ["casts"]}
    app.log_server.review_log = combined
    view.reload()
    settle(lambda: cw.COMBINED_ACTIONS in _labels(view))
    assert "Casts, buffs and break gauge" not in _labels(view)


def _dying():
    """The fuller fight with its deaths recapped by the app's own analyzer (``death_analysis``): the cleric's two in the
    PvE fight, with their HP readings; in the arena the opponent's two (their healing on themselves, a hit with no
    skill name, their HP), and three of the party's: one in which the opponent struck, one whose marker names them as
    the round's winner, and one they had no part in."""
    from aion2calc.combat import recaps
    fight = _fight()
    seg, arena = fight["segments"]
    seg["events"] += [{"kind": "death", "t": 12.0, "target": "p2"}]
    seg["health"] += [{"entity": "p2", "t": 3.2, "current": 1200, "max": 2000}, {"entity": "p2", "t": 4.9, "current": 0},
                      {"entity": "p2", "t": 10.0, "current": 2000, "max": 2000}]
    arena["events"] += [{"kind": "damage", "t": 4.0, "source": "p1", "target": "e1", "amount": 100, "skill": "Spark"},
                        {"kind": "damage", "t": 6.0, "source": "p1", "target": "e1", "amount": 300, "skill_id": 13100002},
                        {"kind": "heal", "t": 7.0, "source": "e1", "target": "e1", "amount": 250, "skill": "Mending"},
                        {"kind": "death", "t": 8.0, "target": "e1"},
                        {"kind": "damage", "t": 14.0, "source": "e1", "target": "p2", "amount": 700, "skill": "Arrow"},
                        {"kind": "death", "t": 15.0, "target": "p2"},
                        {"kind": "death", "t": 20.0, "target": "p1", "source": "e1"},
                        {"kind": "death", "t": 30.0, "target": "p2"}]
    arena["health"] = [{"entity": "e1", "t": 3.9, "current": 100, "max": 5000}]
    fight["death_analysis"] = recaps.summarize(fight)
    return fight


def _recaps(fight, segment=0, actor="", recap=None):
    state = cw.fresh_state()
    state.update(segment=segment, actor=actor, recap=recap)
    d = cw.data(fight, state)
    foe = actor if any(e.get("id") == actor for e in cw.opponents_of(fight, d)) else ""
    return cw.recaps(fight, cw.data(fight, state, foe) if foe else d, state)


def _recap_words(rows):
    """A recap table's rows with its first cell as the recap's key and player, and a last hit as its attacker and words."""
    return [[(c["recap"], c["actor"]) if isinstance(c, dict) and "recap" in c else
             (c["hit"], c["words"]) if isinstance(c, dict) and "hit" in c else c for c in row] for row in rows]


def test_the_review_death_recaps_words():
    from aion2calc.combat.recaps import NOTE
    fight = _dying()
    # the cleric's two deaths in the PvE fight, the first opened: a short window from the pull, then back to the first
    m = _recaps(fight)
    assert m["intro"] == f"{NOTE} {cw.RECAPS_CONTEXT} "
    assert _recap_words(m["rows"]) == [
        [("0", "p2"), "5.000s", "5.0s (short / split boundary)", "800", "600", "0 (maximum unavailable) at 4.900s",
         ("b1", " · Frost Breath · 800 at 3.100s")],
        [("1", "p2"), "12.000s", "7.0s (short / split boundary)", "50", "0", "2,000 / 2,000 at 10.000s",
         ("u1", " · Spike · 50 at 8.000s")]]
    assert m["rows"][0][0]["at"] == "5.000s"
    chosen = m["selected"]
    assert chosen["key"] == "0" and chosen["title"] == "TestCleric · death marker at 5.000s"
    assert chosen["note"] == cw.RECAP_NOTE.format(events=0, health=0) and "; 0 effects and 0 HP samples omitted." in chosen["note"]
    assert _words(chosen["events"]) == [["-1.900s", "damage", ("actor", "b1"), "Frost Breath", "800"],
                                        ["-1.500s", "heal", ("actor", "p2"), "Heal", "600"]]
    assert chosen["health"] == [["-1.800s", "1,200 / 2,000"], ["-0.100s", "0 (maximum unavailable)"]]
    # another opened; one that isn't the encounter's opens the first
    chosen = _recaps(fight, recap="1")["selected"]
    assert chosen["title"] == "TestCleric · death marker at 12.000s"
    assert _words(chosen["events"]) == [["-4.000s", "damage", ("actor", "u1"), "Spike", "50"]]
    assert chosen["health"] == [["-2.000s", "2,000 / 2,000"]]
    assert _recaps(fight, recap="3")["selected"]["key"] == "0"
    # a player chosen alone: none for the sorcerer, who didn't die; the session limit's words when it left recaps out
    m = _recaps(fight, actor="p1")
    assert m["rows"] == [] and m["selected"] is None and m["none"] == cw.RECAPS_NONE
    assert [r[0]["recap"] for r in _recaps(fight, actor="p2")["rows"]] == ["0", "1"]
    limited = json.loads(json.dumps(fight))
    limited["death_analysis"]["omitted_recaps"] = 3
    m = _recaps(limited, actor="p1")
    assert m["intro"] == f"{NOTE} {cw.RECAPS_CONTEXT} 3 recaps omitted by the 200-recap session limit."
    assert m["none"] == cw.RECAPS_NONE_OMITTED
    # the arena's: the party's three, one without a hit or HP in its window
    m = _recaps(fight, segment=1)
    assert _recap_words(m["rows"]) == [
        [("2", "p2"), "15.000s", "10.0s", "700", "0", "Unavailable", ("e1", " · Arrow · 700 at 14.000s")],
        [("3", "p1"), "20.000s", "10.0s", "0", "0", "Unavailable", "Unavailable"],
        [("4", "p2"), "30.000s", "10.0s", "0", "0", "Unavailable", "Unavailable"]]
    assert m["selected"]["health"] == []
    # an opponent's: their own two (back to their first death, healing themselves, a hit by its skill's id), and the
    # party's they struck in, by a hit in its window or as the round's winner its marker names, in time order
    m = _recaps(fight, segment=1, actor="e1")
    assert m["intro"] == f"{cw.RECAPS_FOE} {NOTE}"
    assert _recap_words(m["rows"]) == [
        [("o0", "e1"), "4.000s", "4.0s (short / split boundary)", "2,100", "0", "100 / 5,000 at 3.900s",
         ("p1", " · Spark · 100 at 4.000s")],
        [("o1", "e1"), "8.000s", "4.0s (short / split boundary)", "300", "250", "Unavailable",
         ("p1", " · 13100002 · 300 at 6.000s")],
        [("2", "p2"), "15.000s", "10.0s", "700", "0", "Unavailable", ("e1", " · Arrow · 700 at 14.000s")],
        [("3", "p1"), "20.000s", "10.0s", "0", "0", "Unavailable", "Unavailable"]]
    chosen = m["selected"]
    assert chosen["title"] == "Rival · Zikel · death marker at 4.000s"
    assert _words(chosen["events"]) == [["-3.000s", "damage", ("actor", "p1"), "Flame Burst", "2,000"],
                                        ["0.000s", "damage", ("actor", "p1"), "Spark", "100"]]
    assert chosen["health"] == [["-0.100s", "100 / 5,000"]]
    assert _words(_recaps(fight, segment=1, actor="e1", recap="o1")["selected"]["events"]) == [
        ["-2.000s", "damage", ("actor", "p1"), "13100002", "300"], ["-1.000s", "heal", ("actor", "e1"), "Mending", "250"]]
    # an older log: none for the party; an opponent's own still, as the web page builds them
    older = json.loads(json.dumps(fight))
    del older["death_analysis"]
    assert _recaps(older) == {"missing": cw.RECAPS_OLDER}
    m = _recaps(older, segment=1, actor="e1")
    assert m["intro"] == f"{cw.RECAPS_FOE} {cw.RECAPS_FOE_OLDER}" and [r[0]["recap"] for r in m["rows"]] == ["o0", "o1"]
    deathless = json.loads(json.dumps(older))
    deathless["segments"][1]["events"] = [e for e in deathless["segments"][1]["events"] if e["kind"] != "death"]
    m = _recaps(deathless, segment=1, actor="e1")
    assert m["rows"] == [] and m["selected"] is None and m["none"] == cw.RECAPS_NONE_FOE
    # the last 200 effects and HP samples, the rest counted; an HP reading's words
    long = json.loads(json.dumps(older))
    arena = long["segments"][1]
    arena["events"] += [{"kind": "damage", "t": 30.0 + i / 100, "source": "p1", "target": "e1", "amount": 1} for i in range(205)]
    arena["events"].append({"kind": "death", "t": 33.0, "target": "e1"})
    arena["health"] += [{"entity": "e1", "t": 31.0 + i / 1000, "current": 10} for i in range(201)]
    d = cw.data(long, {**cw.fresh_state(), "segment": 1})
    last = cw.recaps_of(d, "e1")[-1]
    assert (last["window_seconds"], last["short_window"], len(last["events"]), last["omitted_events"]) == (10.0, False, 200, 5)
    assert (len(last["health"]), last["omitted_health"], last["incoming_damage"]) == (200, 1, 205)
    assert last["events"][0]["t"] == 30.05 and last["health"][0]["t"] == 31.001
    assert cw.recap_hp(None) == "Unavailable" and cw.recap_hp({"current": 1500.4, "max": 3000}) == "1,500 / 3,000"


def test_the_review_death_recaps(qapp):
    app = FakeApp()
    app.log_server.review_log = _dying()
    page = _page(app)
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: view.summary is not None and view.ranks is not None and view.names is not None and not view.awaiting)
    assert "Player death recaps" not in _labels(view)
    _click(view, "Death recaps")
    labels, cells = _labels(view), _cells(view)
    assert "Player death recaps" in labels and any(t.startswith("Recaps use explicit player death markers") for t in labels)
    assert all(c in cells for c in ("5.000s", "5.0s (short / split boundary)", "800", "600", "0 (maximum unavailable) at 4.900s",
                                    "12.000s", "2,000 / 2,000 at 10.000s"))
    assert "Ice Queen · Frost Breath · 800 at 3.100s" in labels and "Unnamed summon · Spike · 50 at 8.000s" in labels
    assert "<b>TestCleric · death marker at 5.000s</b>" in labels
    assert all(c in cells for c in ("-1.900s", "damage", "Frost Breath", "-0.100s", "1,200 / 2,000"))
    # another recap opened: its effects and HP in place of the first's
    _find(view, QPushButton, lambda b: b.accessibleName() == "Open the recap of TestCleric at 12.000s").click()
    labels, cells = _labels(view), _cells(view)
    assert view.state["recap"] == "1" and "<b>TestCleric · death marker at 12.000s</b>" in labels
    assert "-4.000s" in cells and "-1.900s" not in cells
    # an opponent's: their own and the party's they struck in, the players in their class's colour
    _choose(view, "Encounter", 1)
    settle(lambda: view.ranks is not None and not view.awaiting)
    _choose(view, "Player", "e1")
    labels, cells = _labels(view), _cells(view)
    assert any(t.startswith(cw.RECAPS_FOE) for t in labels) and "<b>Rival · Zikel · death marker at 4.000s</b>" in labels
    assert all(c in cells for c in ("4.000s", "8.000s", "15.000s", "20.000s", "2,100", "100 / 5,000 at 3.900s"))
    assert "30.000s" not in cells
    assert any(t.endswith(" · Spark · 100 at 4.000s") and "TestSorc" in t and "color:" in t for t in labels)
    # a log without the party's recaps: an opponent's own still; for the party the older view's note in place of the
    # section
    older = json.loads(json.dumps(app.log_server.review_log))
    del older["death_analysis"]
    app.log_server.review_log = older
    view.reload()
    settle(lambda: any(t.endswith(cw.RECAPS_FOE_OLDER) for t in _labels(view)) and not view.awaiting)
    assert "8.000s" in _cells(view) and "15.000s" not in _cells(view)
    _choose(view, "Player", "")
    settle(lambda: cw.RECAPS_OLDER in _labels(view))
    assert "Player death recaps" not in _labels(view)


def _buttons(widget):
    """The buttons shown, once what was drawn last has shown."""
    _shown()
    return [b.text() for b in widget.findChildren(QPushButton) if b.isVisibleTo(widget)]


def _pytest_approx(x):
    import pytest as _pytest
    return _pytest.approx(x)


def test_the_window_draws_combat_logs_itself(qapp):
    window = MainWindow(None)
    assert isinstance(window.page("combat"), CombatPage) and not isinstance(window.page("combat"), WebPage)
    assert isinstance(window.page("raid"), WebPage)                      # not moved over yet
