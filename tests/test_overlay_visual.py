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
        "overlay_glow": True, "overlay_glow_color": "#ffcc00", "overlay_hp_color": "#30ff80",
        "overlay_bg_opacity": 60, "overlay_bg_zoom": 150, "overlay_bg_darken": 30,
        "overlay_resizable": True, "overlay_snap_edge": True, "overlay_expand_up": True,
        "overlay_party_enabled": True, "overlay_long_names_scroll": True,
    })
    s = result["settings"]
    assert s["overlay_text_colors"] == {"name": "#aabbcc", "header": "#112233"}
    assert s["overlay_font_family"] == "Verdana" and s["overlay_font_scale"] == 120
    assert s["overlay_glow"] is True and s["overlay_glow_color"] == "#ffcc00"
    assert s["overlay_hp_color"] == "#30ff80"
    assert (s["overlay_bg_opacity"], s["overlay_bg_zoom"], s["overlay_bg_darken"]) == (60, 150, 30)
    assert s["overlay_party_enabled"] is True


def test_per_element_fonts_and_text_effects_round_trip(home):
    result = settings_backup.import_settings({
        "overlay_text_fonts": {"name": {"family": "Consolas", "scale": 130, "weight": 700},
                               "rate": {"scale": 90}, "header": {"family": "", "weight": 800}},
        "overlay_text_halo": True, "overlay_halo_color": "#FFCC00", "overlay_text_retro": True,
    })
    s = result["settings"]
    # Family="" is a non-override and is dropped, leaving only the real weight override.
    assert s["overlay_text_fonts"] == {"name": {"family": "Consolas", "scale": 130, "weight": 700},
                                       "rate": {"scale": 90}, "header": {"weight": 800}}
    assert s["overlay_text_halo"] is True and s["overlay_halo_color"] == "#ffcc00"
    assert s["overlay_text_retro"] is True


def test_per_element_fonts_reject_bad_values(home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_fonts": {"nope": {"scale": 100}}})      # unknown element
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_fonts": {"name": {"scale": 300}}})      # scale out of range
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_fonts": {"name": {"family": "Comic Sans"}}})  # not allowed
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_fonts": {"name": {"weight": 900}}})     # weight out of range
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_fonts": {"name": {"tilt": 5}}})         # unknown property
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_halo_color": "nope"})


def test_name_mode_and_save_records_round_trip(home):
    result = settings_backup.import_settings({"overlay_name_mode": "number", "meter_save_records": False})
    assert result["settings"]["overlay_name_mode"] == "number"
    assert result["settings"]["meter_save_records"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_name_mode": "nicknames"})   # not a valid mode


def test_visual_settings_reject_bad_values(home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_font_family": "Comic Sans"})   # not in the allowlist
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_font_scale": 300})             # out of range
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_colors": {"rate": "red"}})  # not a hex
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_glow_color": "#xyzxyz"})
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_hp_color": "not-a-color"})


# ---- Remember overlay position ----------------------------------------------

def test_overlay_remember_position_round_trips(home):
    # The toggle rides the settings backup (it is a user preference), on and off.
    assert settings_backup.import_settings({"overlay_remember_position": True})["settings"]["overlay_remember_position"] is True
    assert settings_backup.import_settings({"overlay_remember_position": False})["settings"]["overlay_remember_position"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_remember_position": "sometimes"})


def test_overlay_positions_are_machine_local_not_in_backup(home):
    # The actual screen positions are per-machine/monitor and must never travel in
    # the shareable settings backup, so a foreign file cannot move someone's overlay.
    result = settings_backup.import_settings({"overlay_pos_x": 1000, "overlay_pos_y": 20,
                                              "overlay_party_pos_x": 50, "overlay_party_pos_y": 600,
                                              "overlay_remember_position": True})
    for key in ("overlay_pos_x", "overlay_pos_y", "overlay_party_pos_x", "overlay_party_pos_y"):
        assert key not in result["settings"]
    assert result["settings"]["overlay_remember_position"] is True


def test_overlay_remembers_position_by_default(home):
    # Default ON: the overlay reopens where the user last dragged it instead of
    # re-anchoring to the game window each time (the reported stop/reopen bug).
    assert overlay._overlay_prefs()["remember_position"] is True
    from aion2calc.paths import write_user_json
    write_user_json({"overlay_remember_position": False}, "ui.json")
    assert overlay._overlay_prefs()["remember_position"] is False   # still opt-out-able


def test_overlay_prefs_reads_remembered_positions(home):
    from aion2calc.paths import write_user_json
    assert overlay._overlay_prefs()["positions"] == {"meter": None, "party": None}
    write_user_json({"overlay_remember_position": True, "overlay_pos_x": 1200, "overlay_pos_y": -40,
                     "overlay_pos_layout": [[0, 0, 1920, 1080], [1920, 0, 1920, 1080]],
                     "overlay_party_pos_x": 50, "overlay_party_pos_y": 600}, "ui.json")
    prefs = overlay._overlay_prefs()
    assert prefs["remember_position"] is True
    # Each position now carries its top-left and the monitor layout it was saved under.
    assert prefs["positions"]["meter"] == {"xy": (1200, -40), "layout": [[0, 0, 1920, 1080], [1920, 0, 1920, 1080]]}
    assert prefs["positions"]["party"] == {"xy": (50, 600), "layout": None}
    # A bool must not be read as a coordinate.
    write_user_json({"overlay_pos_x": True, "overlay_pos_y": 10}, "ui.json")
    assert overlay._overlay_prefs()["positions"]["meter"] is None


_OGG = "data:audio/ogg;base64,T2dnUwABAA=="  # a tiny valid base64 audio data URL


def test_set_and_clear_overlay_event_sound(home):
    from aion2calc.app.server import set_overlay_event_sound, ui_settings
    assert set_overlay_event_sound({"data": _OGG})["overlay_events_sound_set"] is True
    assert (home / "overlay-event-sound.ogg").exists()
    assert ui_settings()["overlay_events_sound_set"] is True
    # A second upload of a different type replaces the first (only one sound is kept).
    assert set_overlay_event_sound({"data": "data:audio/wav;base64,UklGRg=="})["overlay_events_sound_set"] is True
    assert (home / "overlay-event-sound.wav").exists() and not (home / "overlay-event-sound.ogg").exists()
    assert set_overlay_event_sound({"clear": True})["overlay_events_sound_set"] is False
    assert not (home / "overlay-event-sound.wav").exists()
    assert ui_settings()["overlay_events_sound_set"] is False


def test_overlay_event_sound_rejects_non_audio_and_oversize(home):
    from aion2calc.app.server import set_overlay_event_sound
    import base64
    with pytest.raises(ValueError):
        set_overlay_event_sound({"data": "data:image/png;base64,iVBORw0KGgo="})   # not audio
    with pytest.raises(ValueError):
        set_overlay_event_sound({"data": "not a data url"})
    big = "data:audio/mpeg;base64," + base64.b64encode(b"\0" * (1024 * 1024 + 1)).decode()
    with pytest.raises(ValueError):
        set_overlay_event_sound({"data": big})                                     # over 1 MB
