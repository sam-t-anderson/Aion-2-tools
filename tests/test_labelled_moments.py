"""Labelled moments (0.2.365): the player marks what they saw during a capture, from the Live Meter page or the
Mark moment hotkey, and the marks ride in the diagnostic ZIP and the saved log's meta so a recording can be read
against them."""
import json
import zipfile

import pytest

from aion2calc.app import hotkeys


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app.meter_runner import Runner
    return Runner()


def test_a_mark_stamps_the_moment_and_the_latest_can_be_labelled_afterwards(runner):
    assert runner.marks == []
    marks = runner.mark("hotkey", source="hotkey")
    assert len(marks) == 1 and marks[0]["label"] == "hotkey" and marks[0]["source"] == "hotkey"
    assert marks[0]["t_ms"] > 1_700_000_000_000 and marks[0]["at"].endswith("Z") and marks[0]["running"] is False
    marks = runner.relabel(-1, "shield", "  Templar's shield took  the whole hit ")
    assert marks[0]["label"] == "shield" and marks[0]["note"] == "Templar's shield took the whole hit"
    marks = runner.mark("mechanic", "x" * 300)
    assert len(marks) == 2 and len(marks[1]["note"]) == 200                    # bounded
    with pytest.raises(ValueError):
        runner.relabel(5, "miss")


def test_the_marks_ride_in_the_diagnostic_zip_and_the_saved_logs_meta(runner, tmp_path):
    from aion2calc.meter.diagnostics import export
    runner.mark("miss", "the arrow missed the templar")
    status = runner.diagnostic_status()
    assert [m["label"] for m in status["marks"]] == ["miss"]
    result = export(status, None)
    with zipfile.ZipFile(result["file"]) as archive:
        rows = [json.loads(line) for line in archive.read("marks.jsonl").decode("utf-8").splitlines()]
        metadata = json.loads(archive.read("diagnostics.json"))
        summary = archive.read("capture-summary.txt").decode("utf-8")
    assert rows[0]["label"] == "miss" and metadata["marks"][0]["note"] == "the arrow missed the templar"
    assert "Labelled moments: 1" in summary and "marks.jsonl" in result["contents"]
    doc = runner._metadata({"meta": {}, "players": [], "segments": []})
    assert doc["meta"]["marks"][0]["label"] == "miss"


def test_the_hotkey_action_exists_and_the_labels_are_the_evidence_kinds():
    assert "mark_moment" in hotkeys.ACTIONS
    from aion2calc.app.meter_runner import Runner
    assert tuple(Runner.MARK_LABELS)[:7] == ("shield", "interrupt", "miss", "mitigation", "hot", "pvp", "mechanic")
