"""Live-meter sessions reach the planner: a2log documents import as encounters (the meter's
Save button and file imports), and the recording player's boss fights from the saved
session files are synced into the encounter history that "Your fights" and the
calibration read."""
import json
import sqlite3

import pytest

from aion2calc import learn
from aion2calc.combat import a2log as F
from aion2calc.combat.adapters import from_text, load
from aion2calc.db import store


def _doc(local="p:2102:1", killed=True):
    hits = [{"t": t * 1.0, "player": local, "target": "boss", "skill_id": 11010000, "damage": 1000.0} for t in range(12)]
    hits += [{"t": 3.0, "player": "p:2102:2", "target": "boss", "skill_id": 17010000, "damage": 50.0}]
    return {"format": "a2log", "version": 1,
            "meta": {"title": "Fire Temple", "capture_scope": "party", "uploader": {"name": "Spirited", "verified": True}},
            "players": [{"id": "p:2102:2", "name": "Mate", "class": "Cleric", "server": "2102"},
                        {"id": local, "name": "Spirited", "class": "Gladiator", "server": "2102"}],
            "segments": [{"label": "Trash", "duration": 8.0, "start": "2026-10-15T23:30:00+00:00",
                          "hits": [{"t": 0.0, "player": local, "skill_id": 11010000, "damage": 10.0}]},
                         {"label": "Black Smoke Murute", "boss": "Black Smoke Murute", "duration": 60.0, "killed": killed,
                          "start": "2026-10-15T23:35:22+00:00", "encounter_type": "expedition", "ping_recorder": local,
                          "entities": [{"id": "boss", "name": "Black Smoke Murute", "kind": "enemy", "is_boss": True, "mob_code": 2300312}],
                          "hits": hits}]}


def test_an_a2log_document_imports_as_the_recording_players_boss_fight():
    enc = from_text(json.dumps(_doc()))                     # what the meter's Save button sends
    m = enc["meta"]
    assert m["source"] == "a2log" and m["player"] == "Spirited" and m["class"] == "gladiator"
    assert m["target"] == "Black Smoke Murute" and m["duration"] == 60.0 and m["boss_killed"] is True
    assert m["started_at"].startswith("2026-10-15T23:35:22") and m["segment"] == 1
    assert len(enc["hits"]) == 12 and all(h["damage"] == 1000.0 for h in enc["hits"])   # the recorder's hits only
    assert enc["meta"]["dps"] == pytest.approx(12000 / 60)


def test_player_and_segment_can_be_chosen_by_name_and_index(tmp_path):
    doc = _doc()
    enc = from_text(json.dumps(doc), player="mate")
    assert enc["meta"]["player"] == "Mate" and enc["meta"]["class"] == "cleric" and len(enc["hits"]) == 1
    path = tmp_path / "session-20261015-233000-abcdef.a2log.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    enc = load(str(path), segment=0)
    assert enc["meta"]["target"] == "Trash" and enc["meta"]["ref"] == str(path)
    with pytest.raises(ValueError):
        from_text(json.dumps(doc), player="Nobody")


def test_select_prefers_the_recorder_then_the_stamp_then_top_damage():
    doc = _doc()
    assert F.select(doc) == ("p:2102:1", 1)                       # ping_recorder names the local player
    for seg in doc["segments"]:
        seg.pop("ping_recorder", None)
    assert F.recording_player(doc) == "p:2102:1"                  # meta.uploader by name
    doc["meta"].pop("uploader")
    assert F.select(doc) == ("p:2102:1", 1)                       # top damage of the chosen segment
    assert F.is_document(doc) and not F.is_document({"players": [], "bossTimeline": []})


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(store.SCHEMA)
    return conn


def test_sync_sessions_adds_each_boss_fight_once(tmp_path, monkeypatch):
    from aion2calc.combat import history
    monkeypatch.setattr(learn, "observe", lambda eid, conn=None: None)
    monkeypatch.setattr(learn, "fit", lambda cls, conn=None: None)
    conn = _conn()
    (tmp_path / "session-20261015-233000-abcdef.a2log.json").write_text(json.dumps(_doc()), encoding="utf-8")
    (tmp_path / "session-20261015-234500-bbbbbb.a2log.json").write_text(json.dumps(_doc(killed=False)), encoding="utf-8")
    (tmp_path / "session-20261015-235900-cccccc.a2log.json").write_text(json.dumps({**_doc(), "meta": {"capture_active": True}}), encoding="utf-8")
    (tmp_path / "session-20261015-230000-dddddd.a2log.json").write_text("{not json", encoding="utf-8")
    result = history.sync_sessions("spirited", "gladiator", conn=conn, folder=tmp_path)
    assert result["added"] == 2 and result["files"] == 2 and result["skipped"] == 1   # trash and open checkpoints skipped
    rows = store.encounters(conn, "gladiator")
    assert [(r["player"], r["boss"], r["source"]) for r in rows] == [("Spirited", "Black Smoke Murute", "session")] * 2
    assert {r["ref"] for r in rows} == {"session-20261015-233000-abcdef.a2log.json#1", "session-20261015-234500-bbbbbb.a2log.json#1"}
    again = history.sync_sessions("Spirited", "gladiator", conn=conn, folder=tmp_path)
    assert again["added"] == 0 and len(store.encounters(conn)) == 2                  # idempotent
    # only the recording player's own fights are synced: a party member advised on this computer
    # gets fights from their own recordings, never from someone else's session files
    assert history.sync_sessions("Mate", "cleric", conn=conn, folder=tmp_path)["added"] == 0
    assert store.encounters(conn, "cleric") == []


def test_fights_of_sees_the_synced_sessions(tmp_path, monkeypatch):
    from aion2calc.combat import history
    from aion2calc.plan import advisor
    monkeypatch.setattr(learn, "observe", lambda eid, conn=None: None)
    monkeypatch.setattr(learn, "fit", lambda cls, conn=None: None)
    conn = _conn()
    monkeypatch.setattr(store, "connect", lambda *a, **k: conn)
    (tmp_path / "session-20261015-233000-abcdef.a2log.json").write_text(json.dumps(_doc()), encoding="utf-8")
    history.sync_sessions("Spirited", "gladiator", conn=conn, folder=tmp_path)
    fights = advisor.fights_of("SPIRITED", "gladiator")
    assert len(fights) == 1 and fights[0]["boss"] == "Black Smoke Murute"
    summary = advisor.fight_summary(fights, {"added": 1})
    assert summary["count"] == 1 and summary["sources"] == {"session": 1} and summary["recent"][0]["boss"] == "Black Smoke Murute"
