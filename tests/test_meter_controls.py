"""Meter auto-start + overlay Start/Stop controls, and the Pages dau placement.

- The meter auto-starts on launch by default (a toggleable, backed-up setting).
- The transparent overlay has a Start/Stop button that mirrors the app's.
- Quit auto-uploads only when the upload setting is on and there is data.
- The site's "meters today" count sits left of the colour switcher.
"""
import pathlib

import pytest

from aion2calc.app import server, settings_backup

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
OVERLAY_JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
OVERLAY_HTML = (STATIC / "overlay.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
NAV_JS = (pathlib.Path(__file__).resolve().parents[1] / "site" / "navigation.js").read_text(encoding="utf-8")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def test_meter_autostart_defaults_on(home):
    assert server.ui_settings()["meter_autostart"] is True


def test_meter_autostart_rides_the_settings_backup(home):
    assert settings_backup.import_settings({"meter_autostart": False})["settings"]["meter_autostart"] is False
    assert settings_backup.import_settings({"meter_autostart": True})["settings"]["meter_autostart"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"meter_autostart": "yes"})


def test_auto_upload_on_quit_is_gated(home, monkeypatch):
    # Off when the upload setting is off; a no-op with no session data. Never raises.
    calls = {"n": 0}

    class _R:
        def has_data(self):
            calls["n"] += 1
            return False

    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_auto_upload": False})
    server._auto_upload_on_quit()                      # disabled → returns before touching the runner
    assert calls["n"] == 0

    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_auto_upload": True})
    monkeypatch.setattr("aion2calc.app.meter_runner.runner", lambda: _R())
    server._auto_upload_on_quit()                      # enabled but no data → no upload, no raise
    assert calls["n"] == 1


def test_overlay_has_a_start_stop_button():
    assert 'id="ovcapture"' in OVERLAY_HTML
    assert '#ovcapture' in OVERLAY_JS
    # Toggles on running state and posts the same start/stop actions as the app.
    assert '{action:"stop"}' in OVERLAY_JS
    assert 'action:"start"' in OVERLAY_JS
    assert "syncCapture" in OVERLAY_JS


def test_app_has_the_autostart_toggle():
    assert 'id="rec-autostart"' in APP_JS
    assert "meter_autostart" in APP_JS


def test_status_text_sits_in_the_metric_row_right_of_dtaken():
    # The "Latest combat" status moved out of the header into the metric row, after
    # the D.Taken button (right-aligned via .ovsub margin-left:auto).
    metrics = OVERLAY_HTML.split('id="ovmetrics"', 1)[1].split("</div>", 1)[0]
    assert 'data-metric="taken"' in metrics
    assert 'id="ovstatus"' in metrics
    assert metrics.index('data-metric="taken"') < metrics.index('id="ovstatus"')
    # And it is no longer in the header block.
    header = OVERLAY_HTML.split('class="ovhd"', 1)[1].split("ovmetrics", 1)[0]
    assert 'id="ovstatus"' not in header


def test_resize_coalesces_and_suspends_the_observer():
    # The drag path drives sizing directly and the ResizeObserver stands down.
    assert "fitSuspended" in OVERLAY_JS
    assert "fitNow(" in OVERLAY_JS


def test_fps_frame_loop_runs_only_when_the_readout_is_enabled():
    # A continuous requestAnimationFrame loop keeps the layered always-on-top overlay
    # compositing every frame, which flickers a black edge over a borderless game on
    # some Win10/DWM setups. The loop must be gated on the (default-off) FPS readout.
    assert "fpsRunning" in OVERLAY_JS
    assert "function fpsTick" in OVERLAY_JS
    assert "setFpsLoop(showFps" in OVERLAY_JS
    # The tick bails out when not running, instead of self-perpetuating unconditionally.
    assert "if(!fpsRunning)return;" in OVERLAY_JS


def test_meters_today_sits_left_of_the_colour_switcher():
    # dau is inserted before the accent (colour) button, not just before the theme toggle.
    assert 'document.getElementById("accent") || theme' in NAV_JS
