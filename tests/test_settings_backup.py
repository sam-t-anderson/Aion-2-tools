"""Export/restore of overlay & app settings: a round-trip preserves recognised
settings, and import validates types and ignores unknown or tampered keys so a
foreign file can never inject arbitrary state."""
import json

import pytest

from aion2calc.app import settings_backup


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def test_export_then_import_round_trips_recognised_settings(isolated_home):
    from aion2calc.paths import write_user_json
    write_user_json({"tray_on_close": True, "overlay_show_target": False,
                     "overlay_text_colors": {"rate": "#aabbcc", "total": "#112233"}}, "ui.json")

    exported = settings_backup.export_settings()
    assert exported["settings"]["tray_on_close"] is True
    saved = json.loads((isolated_home / exported["file"].split("/")[-1]).read_text())
    assert saved["format"] == settings_backup.FORMAT

    # Wipe the stored settings, then restore from the exported document.
    write_user_json({}, "ui.json")
    result = settings_backup.import_settings(saved)
    assert result["settings"]["tray_on_close"] is True
    assert result["settings"]["overlay_show_target"] is False
    assert result["settings"]["overlay_text_colors"] == {"rate": "#aabbcc", "total": "#112233"}
    assert "tray_on_close" in result["imported"]


def test_import_accepts_a_bare_settings_object(isolated_home):
    result = settings_backup.import_settings({"overlay_show_contribution": False})
    assert result["settings"]["overlay_show_contribution"] is False


def test_import_rejects_a_foreign_format(isolated_home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"format": "someone-elses-app", "settings": {"app_window": False}})


def test_import_rejects_a_bad_type(isolated_home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"tray_on_close": "yes please"})


def test_whole_number_settings_round_trip_and_range_check(isolated_home):
    result = settings_backup.import_settings({"meter_reset_delay": 8, "meter_max_records": 30})
    assert result["settings"]["meter_reset_delay"] == 8
    assert result["settings"]["meter_max_records"] == 30
    with pytest.raises(ValueError):
        settings_backup.import_settings({"meter_reset_delay": 0})        # below range
    with pytest.raises(ValueError):
        settings_backup.import_settings({"meter_max_records": True})     # bool is not a count


def test_overlay_layout_settings_round_trip(isolated_home):
    result = settings_backup.import_settings({"overlay_max_players": 12, "overlay_width": 420,
                                              "overlay_row_height": 28, "overlay_only_in_combat": True,
                                              "overlay_auto_expand": True})
    s = result["settings"]
    assert (s["overlay_max_players"], s["overlay_width"], s["overlay_row_height"]) == (12, 420, 28)
    assert s["overlay_only_in_combat"] is True and s["overlay_auto_expand"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_max_players": 99})     # above range (max 24)
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_width": 100})          # below range (min 260)


def test_overlay_client_render_settings_round_trip(isolated_home):
    result = settings_backup.import_settings({"overlay_dps_interpolate": True,
                                              "overlay_interpolate_ms": 150,
                                              "overlay_show_fps": True})
    s = result["settings"]
    assert s["overlay_dps_interpolate"] is True and s["overlay_show_fps"] is True
    assert s["overlay_interpolate_ms"] == 150
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_interpolate_ms": 10})    # below range (min 50)
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_interpolate_ms": 5000})  # above range (max 1000)


def test_import_ignores_unknown_keys_and_applies_known_ones(isolated_home):
    result = settings_backup.import_settings({"app_window": False, "evil_key": {"x": 1}, "rm": "rf"})
    assert result["settings"]["app_window"] is False
    assert "evil_key" not in result["settings"]
    assert result["imported"] == ["app_window"]


def test_import_rejects_when_nothing_recognised(isolated_home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"totally_unknown": 1})


def test_overlay_presets_round_trip_and_strip_non_visual_keys(isolated_home):
    presets = [
        {"name": "Night", "settings": {"overlay_glow": True, "overlay_glow_color": "#112233",
                                        "overlay_font_scale": 120,
                                        # non-visual and unknown keys are stripped, not stored:
                                        "overlay_width": 500, "evil": {"x": 1}}},
        {"name": "Day", "settings": {"overlay_bg_darken": 10, "overlay_name_mode": "number"}},
    ]
    result = settings_backup.import_settings({"overlay_presets": presets})
    stored = result["settings"]["overlay_presets"]
    assert [p["name"] for p in stored] == ["Night", "Day"]
    night = stored[0]["settings"]
    assert night == {"overlay_glow": True, "overlay_glow_color": "#112233", "overlay_font_scale": 120}
    assert stored[1]["settings"] == {"overlay_bg_darken": 10, "overlay_name_mode": "number"}


def test_overlay_presets_reject_bad_shapes(isolated_home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_presets": {"not": "a list"}})
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_presets": [{"settings": {}}]})         # no name
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_presets": [{"name": "x" * 41, "settings": {}}]})  # name too long
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_presets": [{"name": "A", "settings": "nope"}]})   # settings not an object
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_presets": [{"name": "A", "settings": {}},
                                                             {"name": "a", "settings": {}}]})       # duplicate name


def test_overlay_presets_reject_bad_setting_values(isolated_home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_presets": [
            {"name": "A", "settings": {"overlay_glow_color": "not-a-color"}}]})
