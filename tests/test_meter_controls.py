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
    # Off when the upload setting is off; otherwise one bounded automatic pass over everything
    # this launch recorded that is not on the server yet (whether or not capture was running).
    calls = []

    class _R:
        def upload_pending(self, **kw):
            calls.append(kw)
            return {"uploaded": 0, "failed": 0, "pending": 0, "url": None, "results": []}

    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_auto_upload": False})
    monkeypatch.setattr("aion2calc.app.meter_runner.runner", lambda: _R())
    server._auto_upload_on_quit()                      # disabled → returns before touching the runner
    assert calls == []

    monkeypatch.setattr(server, "ui_settings", lambda: {"meter_auto_upload": True})
    server._auto_upload_on_quit()                      # enabled → the pending pass, bounded, never raises
    from aion2calc.app.meter_runner import Runner
    assert len(calls) == 1 and calls[0]["automatic"] is True and calls[0]["budget_s"] == Runner.QUIT_UPLOAD_BUDGET_S


def test_overlay_has_a_start_stop_button():
    assert 'id="ovcapture"' in OVERLAY_HTML
    assert '#ovcapture' in OVERLAY_JS
    # Toggles on running state and posts the same start/stop actions as the app.
    # Stop from the overlay flags from_overlay so it never closes the overlay itself.
    assert 'action:"stop",from_overlay:true' in OVERLAY_JS
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


def test_profile_bundles_the_overlay_background_locally():
    # Saving a customization profile snapshots the overlay background into the
    # profile (stored in this browser, on the user's machine), and applying a
    # profile restores (or clears) that bundled image.
    assert "captureOverlayBackground" in APP_JS
    assert "fetch('/overlay-background?'" in APP_JS
    assert "fresh.overlay_bg_set?await captureOverlayBackground()" in APP_JS
    # Apply pushes the bundled image back (or clears it) via the local background API.
    assert "await api('/api/overlay/background',prof.bg?{data:prof.bg}:{clear:true})" in APP_JS


def test_profile_share_code_strips_the_background_image():
    # The portable share code (and therefore any export to a server) must not carry
    # the bundled background — only colours and settings.
    assert "const encodeProfile=prof=>{const {bg,...rest}=prof;" in APP_JS
    # The decoder rebuilds a clean object with no bg field, so imports never bring one in.
    assert "return {name:String(obj.name||'').slice(0,40)" in APP_JS


OVERLAY_PY = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "overlay.py").read_text(encoding="utf-8")
SERVER_PY = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")


def test_click_through_setting_defaults_off_and_backs_up(home):
    # Off by default so the overlay stays interactive until the user opts in.
    assert server.ui_settings()["overlay_click_through"] is False
    # Rides the settings backup like the other overlay behaviour toggles.
    assert settings_backup.import_settings({"overlay_click_through": True})["settings"]["overlay_click_through"] is True
    assert settings_backup.import_settings({"overlay_click_through": False})["settings"]["overlay_click_through"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_click_through": "yes"})


def test_click_through_toggle_is_wired_in_settings_and_overlay():
    # App settings toggle.
    assert 'id="ov-clickthrough"' in APP_JS
    assert "overlay_click_through" in APP_JS
    # Overlay page reports its controls and the mode across the native bridge.
    assert "applyClickThrough" in OVERLAY_JS
    assert "set_click_through" in OVERLAY_JS
    assert "set_interactive_rects" in OVERLAY_JS
    assert "reportInteractiveRects" in OVERLAY_JS
    assert "devicePixelRatio" in OVERLAY_JS


def test_enemy_hp_shown_as_percentage_not_raw_numbers():
    # Enemy HP is on a much larger scale than damage (verified from captures), so the
    # overlay shows a percentage + bar, not the raw internal current/max numbers that
    # can't line up with damage. The raw values move to a labelled hover tooltip.
    assert ">${Math.round(target.hp_pct*100)}%</span>" in OVERLAY_JS
    assert "Game internal HP " in OVERLAY_JS
    # The raw current/max is no longer printed inline next to the percentage.
    assert "%${target.current_hp" not in OVERLAY_JS
    # Hover shows the effective HP in damage units = total recorded damage to the target.
    assert "Effective HP so far" in OVERLAY_JS
    assert "kfmt(target.damage)" in OVERLAY_JS


def test_capture_toggle_ignores_clicks_not_begun_on_the_button():
    # Dragging the opacity slider can shift the frameless overlay under the cursor,
    # so a synthesized mouse click can land on Start/Stop and stop the meter. The
    # toggle must require the pointerdown to have happened on the button (keyboard
    # activation, click detail 0, still allowed).
    assert "capturePressed" in OVERLAY_JS
    assert "ev.detail!==0&&!capturePressed" in OVERLAY_JS


def test_stop_keeps_the_overlay_open_by_default(home, monkeypatch):
    # Stopping the meter must NOT close the overlay unless the user opted in, and an
    # overlay-initiated stop (from_overlay) must never close it regardless.
    closes = {"n": 0}
    monkeypatch.setattr("aion2calc.app.overlay_launch.close", lambda: closes.__setitem__("n", closes["n"] + 1), raising=False)
    # Default: the flag is off.
    assert server.ui_settings()["overlay_close_on_stop"] is False
    # Backs up like the other overlay toggles.
    assert settings_backup.import_settings({"overlay_close_on_stop": True})["settings"]["overlay_close_on_stop"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_close_on_stop": "nope"})


def test_close_on_stop_toggle_is_wired_in_settings():
    assert 'id="ov-close-on-stop"' in APP_JS
    assert "overlay_close_on_stop" in APP_JS
    # Server only closes the overlay on stop when opted in AND the stop wasn't from the overlay.
    assert 'ui_settings().get("overlay_close_on_stop") and not body.get("from_overlay")' in SERVER_PY


def test_click_through_native_hit_test_present():
    # The native side toggles WS_EX_TRANSPARENT and hit-tests the cursor against the
    # reported control rects so the overlay's own buttons stay clickable.
    assert "def _click_through_loop" in OVERLAY_PY
    assert "def set_click_through" in OVERLAY_PY
    assert "def set_interactive_rects" in OVERLAY_PY
    assert "cursor_in_client" in OVERLAY_PY
    assert "0x00000020" in OVERLAY_PY   # WS_EX_TRANSPARENT


def test_settings_has_a_square_selector_for_bundled_backgrounds():
    # A clickable square (background preview + profile name) per profile that
    # bundles a background, wired to apply that profile.
    assert "function customProfileGallery()" in APP_JS
    assert "custgallery" in APP_JS
    assert "data-cust-tile" in APP_JS
    assert '$$("[data-cust-tile]")' in APP_JS
    assert ".custtile" in (STATIC / "app.css").read_text(encoding="utf-8")
