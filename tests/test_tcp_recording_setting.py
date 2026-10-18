"""Record TCP payloads is a saved setting that every capture follows, however it is started: the
Live Meter page, the overlay's Start button, the Start/Stop hotkey or the start at launch. Until
0.2.318 only the page's Start read the checkbox, and the box was neither saved nor usable during a
capture, so a capture started any other way recorded nothing with the box ticked."""
import json
import re
import zipfile
from pathlib import Path

import pytest

from aion2calc.app import meter_runner as MR

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = ("eth0", "10.0.0.2", 13328, "10.0.0.1", 50000)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def switches(monkeypatch):
    """The recording switch each capture thread is handed, in place of the real sniffer."""
    seen = []
    monkeypatch.setattr(MR, "capture_packets", lambda *args, **kwargs: seen.append(args[7]))
    return seen


def _tick(on: bool) -> None:
    from aion2calc.app.server import ui_settings
    from aion2calc.paths import write_user_json
    write_user_json({**ui_settings(), "meter_record_packets": on}, "ui.json")


def _start(runner, **opts):
    runner.start("a2tools", auto_port=True, **opts)
    runner.packet_capture_thread.join(2)


@pytest.mark.parametrize("scope", ["party", "auto"])   # the overlay and the launch start use party, the hotkey auto
def test_a_start_that_makes_no_choice_follows_the_saved_setting(home, switches, scope):
    r = MR.Runner()
    _tick(True)
    try:
        _start(r, scope=scope)
        assert r.recorder is not None and switches[-1].recorder is r.recorder
    finally:
        r.stop()
    _tick(False)
    try:
        _start(r, scope=scope)
        assert r.recorder is None and switches[-1].recorder is None
    finally:
        r.stop()


def test_an_explicit_choice_still_wins_and_a_replay_never_records(home, switches):
    _tick(True)
    r = MR.Runner()
    try:
        _start(r, record_packets=False)
        assert r.recorder is None and switches[-1].recorder is None
    finally:
        r.stop()
    try:
        r.start("replay", realtime=False)
        assert r.recorder is None
    finally:
        r.stop()


def test_ticking_the_box_during_a_capture_records_from_then_on(home, switches):
    _tick(False)
    r = MR.Runner()
    try:
        _start(r, scope="party")
        switch = switches[-1]
        switch.record(SEGMENT, 1, 24, b"before", 1000)          # unticked: nothing recorded
        assert r.recorder is None and not r.status()["recording"]["enabled"]
        _tick(True)
        r.apply_record_settings()                                 # what saving the setting does
        assert switch.recorder is r.recorder is not None
        switch.record(SEGMENT, 7, 24, b"during", 2000)
        recording = r.status()["recording"]
        assert recording["enabled"] and recording["records"] == 1
        r.apply_record_settings()                                 # another meter setting saved: no change
        assert switch.recorder is r.recorder
        _tick(False)
        r.apply_record_settings()
        switch.record(SEGMENT, 13, 24, b"after", 3000)            # unticked again: no longer recorded
        recording = r.status()["recording"]
        assert not recording["enabled"] and recording["records"] == 1
    finally:
        r.stop()
    with zipfile.ZipFile(r.diagnostic_export["file"]) as archive:   # the ZIP Stop saved keeps what was recorded
        rows = [json.loads(line) for line in archive.read("tcp-payloads.jsonl").splitlines()]
        assert [bytes.fromhex(row["payload_hex"]) for row in rows] == [b"during"]
        assert "Raw TCP recording: enabled" in archive.read("capture-summary.txt").decode()


def test_ticking_the_box_while_stopped_applies_at_the_next_start(home, switches):
    r = MR.Runner()
    _tick(True)
    r.apply_record_settings()
    assert r.recorder is None                                     # nothing is capturing yet
    try:
        _start(r, scope="party")
        assert switches[-1].recorder is r.recorder is not None
    finally:
        r.stop()


def test_the_overlay_hotkey_and_launch_starts_make_no_choice_of_their_own():
    overlay = (ROOT / "aion2calc/app/static/overlay.js").read_text(encoding="utf-8")
    page = (ROOT / "aion2calc/app/static/app.js").read_text(encoding="utf-8")
    calls = [*re.findall(r'\{action:"start"[^}]*\}', overlay),
             *re.findall(r'\{ action: "start"[^;]*\};', page)]
    for name in ("aion2calc/launcher.py", "aion2calc/app/server.py"):
        calls += re.findall(r'r\.start\("a2tools"[^)]*\)', (ROOT / name).read_text(encoding="utf-8"))
    assert len(calls) == 4 and not [call for call in calls if "record_packets" in call]


def test_the_setting_defaults_off_and_stays_out_of_settings_backups(home):
    from aion2calc.app.server import ui_settings
    from aion2calc.app.settings_backup import _BOOL_KEYS
    assert ui_settings()["meter_record_packets"] is False
    assert "meter_record_packets" not in _BOOL_KEYS
