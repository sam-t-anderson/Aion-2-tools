"""Overlay auto-contrast text (0.2.262): keep the overlay text legible against an uploaded
background image, either with mix-blend-mode:difference (dynamic, per-pixel) or a solid
colour computed from the image's WCAG relative luminance. Covers the backend default +
enum validation and the overlay wiring that drives both modes (Settings saves it, and a saved look and a
settings backup carry it: tests/browser/test_browser_settings.py, test_settings_backup.py)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")
OVERLAY_JS = (ROOT / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")
OVERLAY_CSS = (ROOT / "aion2calc" / "app" / "static" / "overlay.css").read_text(encoding="utf-8")


def test_setting_defaults_off_and_validates_the_enum(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app.server import ui_settings
    assert ui_settings()["overlay_text_autocontrast"] == "off"     # inert by default
    # The /api/ui POST accepts exactly the three modes and stores the choice.
    assert '("off", "blend", "luminance")' in SERVER
    assert 'cur["overlay_text_autocontrast"] = body["overlay_text_autocontrast"]' in SERVER


def test_overlay_drives_both_modes():
    # Dynamic mode toggles a CSS class; the card is isolated so the blend reaches only the
    # overlay's own panel + image, not the game behind a transparent window.
    assert "applyAutoContrast" in OVERLAY_JS
    assert "'ov-ac-blend'" in OVERLAY_JS
    assert "mix-blend-mode: difference" in OVERLAY_CSS
    assert "#ov.ov-ac-blend .ovcard { isolation: isolate; }" in OVERLAY_CSS
    # The WCAG relative-luminance coefficients compute the "by brightness" colour.
    assert "0.2126" in OVERLAY_JS and "0.7152" in OVERLAY_JS and "0.0722" in OVERLAY_JS

