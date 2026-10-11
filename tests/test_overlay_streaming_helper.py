"""The Settings → Overlay "Streaming (OBS / Discord)" helper must stay wired: it
surfaces the overlay's browser-source URL (built from the app's own origin) with
a copy button, and tells the user the two capture paths that actually include an
always-on-top overlay. This guards the honest wording too — a game-window-only
share does not show the overlay, so the helper must not imply it does."""
import pathlib

APPJS = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")


def test_helper_row_and_copy_button_present():
    assert 'id="ov-stream-url"' in APPJS
    assert 'id="ov-stream-copy"' in APPJS
    assert '#ov-stream-copy' in APPJS  # the copy handler


def test_url_is_built_from_the_app_origin_overlay_route():
    assert "${esc(location.origin)}/overlay" in APPJS


def test_helper_names_the_two_working_capture_paths():
    assert "Browser Source" in APPJS
    assert "whole screen" in APPJS  # full-screen Go Live guidance
    # Honest caveat: a window-only share will not include the overlay.
    assert "will <b>not</b> show the overlay" in APPJS
