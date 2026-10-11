"""Overlay visual-settings backend: the background-image store, the native
follow-position math (unchanged by default), and backup/restore of the new
colour/font/background settings."""
import pytest

from aion2calc.app import settings_backup
from aion2calc import overlay


# ---- Native follow-position --------------------------------------------------

def test_follow_position_defaults_are_unchanged():
    # bounds (left, top, width, height); current (x, y, ow, oh)
    bounds, current = (100, 200, 1000, 800), (140, 260, 300, 120)
    # No dragged offset history -> the historical default offset (16, 48).
    assert overlay._follow_position(None, bounds, current) == (116, 248)
    # With a previous game-bounds, the dragged offset is preserved exactly.
    assert overlay._follow_position((100, 200), bounds, current) == (140, 260)


def test_follow_position_snap_pulls_to_the_left_edge():
    bounds, current = (100, 200, 1000, 800), (112, 260, 300, 120)  # 12px from left -> within 24
    assert overlay._follow_position((100, 200), bounds, current, snap=True)[0] == 100


def test_follow_position_expand_up_anchors_near_the_bottom():
    bounds, current = (100, 200, 1000, 800), (140, 260, 300, 120)
    _, ny = overlay._follow_position((100, 200), bounds, current, expand_up=True)
    assert ny == 200 + (800 - 120 - 48)        # bottom-anchored with a 48px margin


# ---- Background store ---------------------------------------------------------

_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
        "AAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def test_set_and_clear_overlay_background(home):
    from aion2calc.app.server import set_overlay_background, ui_settings
    assert set_overlay_background({"data": _PNG})["overlay_bg_set"] is True
    assert (home / "overlay-background.png").exists()
    assert ui_settings()["overlay_bg_set"] is True

    assert set_overlay_background({"clear": True})["overlay_bg_set"] is False
    assert not (home / "overlay-background.png").exists()
    assert ui_settings()["overlay_bg_set"] is False


def test_overlay_background_rejects_non_images(home):
    from aion2calc.app.server import set_overlay_background
    with pytest.raises(ValueError):
        set_overlay_background({"data": "data:text/plain;base64,aGVsbG8="})
    with pytest.raises(ValueError):
        set_overlay_background({"data": "not a data url"})


# ---- Backup / restore of the visual settings ---------------------------------

def test_visual_settings_round_trip(home):
    result = settings_backup.import_settings({
        "overlay_text_colors": {"name": "#aabbcc", "header": "#112233"},
        "overlay_font_family": "Verdana", "overlay_font_scale": 120, "overlay_font_weight": 700,
        "overlay_glow": True, "overlay_glow_color": "#ffcc00",
        "overlay_bg_opacity": 60, "overlay_bg_zoom": 150, "overlay_bg_darken": 30,
        "overlay_resizable": True, "overlay_snap_edge": True, "overlay_expand_up": True,
        "overlay_party_enabled": True, "overlay_long_names_scroll": True,
    })
    s = result["settings"]
    assert s["overlay_text_colors"] == {"name": "#aabbcc", "header": "#112233"}
    assert s["overlay_font_family"] == "Verdana" and s["overlay_font_scale"] == 120
    assert s["overlay_glow"] is True and s["overlay_glow_color"] == "#ffcc00"
    assert (s["overlay_bg_opacity"], s["overlay_bg_zoom"], s["overlay_bg_darken"]) == (60, 150, 30)
    assert s["overlay_party_enabled"] is True


def test_visual_settings_reject_bad_values(home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_font_family": "Comic Sans"})   # not in the allowlist
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_font_scale": 300})             # out of range
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_colors": {"rate": "red"}})  # not a hex
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_glow_color": "#xyzxyz"})
