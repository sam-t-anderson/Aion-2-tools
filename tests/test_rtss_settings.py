"""The RTSS in-game output is a setting like any other: whitelisted and validated by /api/ui,
off by default, with a status endpoint the Settings page reads and a sync hook that starts or
stops the pusher. Off Windows the sync is a no-op and the state says so."""
import pathlib

from aion2calc.app import server

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")
SERVER = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")


def test_defaults_are_off_and_sane(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    ui = server.ui_settings()
    assert ui["rtss_enabled"] is False and ui["rtss_rows"] == 5 and ui["rtss_metric"] == "dps"
    assert ui["rtss_style"] == "plain" and ui["rtss_interval_ms"] == 500


def test_settings_are_validated_and_hooked():
    assert '"rtss_enabled")' in SERVER                                   # a boolean flag
    assert '("rtss_rows", 1, 24), ("rtss_interval_ms", 100, 5000)' in SERVER
    assert '("rtss_metric", ("dps", "hps", "dtps")), ("rtss_style", ("plain", "colored"))' in SERVER
    assert '"event_region", "event_group", "rtss_metric", "rtss_style",' in SERVER   # stored
    assert 'if any(k.startswith("rtss_") for k in body):' in SERVER       # the sync hook
    assert 'if path == "/api/rtss":' in SERVER
    assert "rtss_sync(stop=True)" in SERVER                               # cleared on quit


def test_state_and_sync_off_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app import rtss
    monkeypatch.setattr(rtss.sys, "platform", "linux")
    server.rtss_sync()                                                    # no-op without raising
    state = server.rtss_state()
    assert state["supported"] is False and state["setting"] is False and "last_text" not in state


def test_settings_page_has_the_group():
    assert 'id="rtss-enabled"' in APP and 'id="rtss-rows"' in APP and 'id="rtss-metric"' in APP
    assert 'id="rtss-style"' in APP and 'id="rtss-interval"' in APP and "api('/api/rtss')" in APP
    assert "Nothing is injected into or loaded by the game" in APP
