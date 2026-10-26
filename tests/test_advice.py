"""Gear & Advice (aion2calc/plan/advisor.py): everything the planners say about one imported character,
ranked by modeled DPS gain. These run it on the test Sorcerer with an AbyssLogs fight saved for it, against
a stand-in log server that serves the class's community calibration and its top players' choices. A
suggestion with no modeled gain ranks below every one that has a gain. (The live-meter session import
that also feeds the saved fights is tested in test_history_sync.py.)"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLAME_ARROW, BLAZE = 15210000, 15050000
CALIBRATION = {"class": "sorcerer", "active": True, "fights": 40, "crit_x0": 1100.0, "rates": {"double": 1.1},
               "skills": {"Flame Arrow": 1.05}}
# the server's class statistics: most of its top players pick Flame Arrow's first specialization, and
# Blaze's first and second, which the character already has
STATS = {"observations": 40, "top_quarter": {"players": 10, "skills": [], "specs": [
    {"skill": "Blaze", "picks": [{"specs": "1, 2", "share": 0.9}], "players": 9},
    {"skill": "Flame Arrow", "picks": [{"specs": "1", "share": 0.75}], "players": 8}]}}


def fight(name="TestSorc"):
    """A 30 s boss fight in which the character presses only Flame Arrow and Blaze."""
    local = "p:1101:1"
    hits = [{"t": t * 2.0, "player": local, "target": "boss", "skill_id": FLAME_ARROW, "damage": 2000.0} for t in range(15)]
    hits += [{"t": 10.0 * t + 1, "player": local, "target": "boss", "skill_id": BLAZE, "damage": 9000.0} for t in range(3)]
    return {"format": "a2log", "version": 1, "meta": {"title": "Fire Temple", "capture_scope": "party",
                                                      "uploader": {"name": name, "verified": True}},
            "players": [{"id": local, "name": name, "class": "Sorcerer", "server": "1101"}],
            "segments": [{"label": "Black Smoke Murute", "boss": "Black Smoke Murute", "duration": 30.0, "killed": True,
                          "start": "2026-10-20T20:00:00+00:00", "encounter_type": "expedition", "ping_recorder": local,
                          "entities": [{"id": "boss", "name": "Black Smoke Murute", "kind": "enemy", "is_boss": True}],
                          "hits": hits}]}


def serve(routes):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            status, body = routes.get(self.path, (404, {"error": "not found"}))
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="module")
def advised(tmp_path_factory):
    """One advice run (about 20 s): the character's evaluation is the bundled build's, so its own lengthy
    rotation search is skipped."""
    home = tmp_path_factory.mktemp("home")
    server = serve({"/api/v1/calibration/sorcerer": (200, CALIBRATION), "/api/v1/stats/sorcerer": (200, STATS)})
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AION2CALC_HOME", str(home))
        from aion2calc.combat import share
        from aion2calc.combat.adapters import from_text
        from aion2calc.db import store
        from aion2calc.plan.advisor import advise
        from aion2calc.sources.character import from_profile
        from test_app import _profile
        share.save_settings(url=f"http://127.0.0.1:{server.server_address[1]}", key="a2l_test")
        imported = from_text(json.dumps(fight()))                    # an AbyssLogs fight: it records specializations
        imported["meta"].update(source="abysslogs", ref="https://abysslogs.test/report/1")
        imported["specs"] = {"Flame Arrow": "2, 3", "Blaze": "1, 2"}
        store.put_encounter(store.connect(), imported)
        bundled = json.loads((ROOT / "results" / "sorcerer_l45" / "build.json").read_text(encoding="utf-8"))
        said = []
        result = advise(from_profile(_profile()), steps=2, progress=said.append,
                        evaluation={"class": "sorcerer", "weights": bundled["weights"],
                                    "build": {"specs": bundled["build"]["specs"]}})
        yield {"advice": result, "said": said, "home": home}
    server.shutdown()


def test_the_advice_names_the_character_and_how_the_model_was_calibrated(advised):
    advice = advised["advice"]
    assert advice["character"] == {"name": "TestSorc", "server": "Siel", "class": "sorcerer", "level": 45}
    assert advice["calibrated"] and advice["dps"] > 0
    assert "community calibration from your log server: 40 fights" in advice["calibration"]
    assert advised["said"] == ["your recorded fights", "scoring the character as it is", "best gear from your inventory",
                               "goal gear per slot", "upgrade path", "arcana", "pantheon", "genus insight", "titles", "your fights"]


def test_suggestions_rank_by_modeled_gain_and_unmodeled_ones_come_last(advised):
    top = advised["advice"]["top"]
    gains = [row["gain"] for row in top]
    modeled = [g for g in gains if g is not None]
    assert modeled == sorted(modeled, reverse=True) and gains == modeled + [None] * (len(gains) - len(modeled))
    areas = {row["area"] for row in top}
    assert {"gear (upgrade)", "arcana", "rotation", "specializations", "community"} <= areas
    assert ("specializations", "Flame Arrow: specs 2, 3 in your fights, 1 in the optimized build") in {
        (row["area"], row["text"]) for row in top}
    community = [row["text"] for row in top if row["area"] == "community"]
    assert community == ["Flame Arrow: 75% of the top players on your log server pick specs 1 (you: 2, 3)"]   # Blaze matches already


def test_the_characters_fights_are_compared_with_the_optimal_rotation(advised):
    advice = advised["advice"]
    fights = advice["fights"]
    assert fights["count"] == 1 and fights["synced"] == 0 and fights["sources"] == {"abysslogs": 1}
    assert [(f["boss"], f["duration"]) for f in fights["recent"]] == [("Black Smoke Murute", 30.0)]
    rotation = advice["rotation"]
    assert rotation["fights"] == 1 and 0 <= rotation["idle_share"] < 1
    under = rotation["under_cast"]
    assert under and all(t["casts"] < 0.8 * t["optimal"] for t in under)
    assert under[0]["text"] == (f"{under[0]['skill']}: cast {under[0]['casts']}x where the optimal rotation casts "
                                f"{under[0]['optimal']}x, in 1 of 1 fights")
    assert under == sorted(under, key=lambda t: -(t["optimal"] - t["casts"]))       # the biggest shortfall first
    assert [d["skill"] for d in rotation["specs"]] == ["Blaze", "Flame Arrow"]


def test_every_gear_slot_shows_what_is_worn_and_what_to_aim_for(advised):
    from aion2calc.plan.items import SLOTS
    doll = advised["advice"]["doll"]
    assert list(doll) == list(SLOTS)
    assert doll["MainHand"]["worn"]["name"] == "Book" and doll["MainHand"]["worn"]["enchant"] == 10
    assert all(row["wear"] is None for row in doll.values())    # the inventory holds only what is worn: nothing to swap
    steps = advised["advice"]["upgrade_path"]["steps"]
    assert steps and all(step["step"] in doll[step["slot"]]["steps"] for step in steps)


def test_the_advice_markdown_and_json_are_written_together(advised, tmp_path):
    from aion2calc.plan.advisor import write_markdown
    advice = advised["advice"]
    path = write_markdown(advice, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert path.name == "ADVICE.md" and json.loads((tmp_path / "advice.json").read_text(encoding="utf-8"))["top"]
    assert text.startswith("# Advice for TestSorc (Siel), Sorcerer Lv 45\n")
    assert f"Simulated boss DPS as equipped: **{advice['dps']:,.0f}** (model calibrated from fights)" in text
    rows = [line for line in text.splitlines() if line.startswith("| ") and line.count("|") == 4]
    assert len([r for r in rows if r.split(" | ")[0][2:] in {t["area"] for t in advice["top"]}]) == len(advice["top"])
    assert "1 saved fight(s): 1 from abysslogs." in text
    assert f"1 fight(s) compared with the optimal rotation; idle {100 * advice['rotation']['idle_share']:.0f}% of the time." in text
    assert "* community calibration from your log server: 40 fights" in text
    for heading in ("## Top changes", "## Skill specialties", "## Gear", "### Goal gear", "### Upgrade path (toward the next goals)",
                    "## Arcana", "## Pantheon", "## Genus insight", "## Your fights", "## Model calibration"):
        assert heading in text


def test_advice_without_fights_or_calibration_says_so(advised, tmp_path):
    from aion2calc.plan.advisor import fight_summary, write_markdown
    advice = {**advised["advice"], "calibrated": False, "fights": fight_summary([]),
              "rotation": {"fights": 0, "idle_share": None, "under_cast": [], "specs": []},
              "equip": {**advised["advice"]["equip"], "empty_slots": ["Wings", "Amulet"]}}
    text = write_markdown(advice, tmp_path).read_text(encoding="utf-8")
    assert "calibrated" not in text.splitlines()[2]
    assert "No saved fights for this character yet: record a boss fight with the live meter" in text
    assert "No inventory items for: Wings, Amulet" in text
    assert fight_summary([{"id": 1, "source": None}])["sources"] == {"unknown": 1}
