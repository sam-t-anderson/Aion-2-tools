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


def test_import_ignores_unknown_keys_and_applies_known_ones(isolated_home):
    result = settings_backup.import_settings({"app_window": False, "evil_key": {"x": 1}, "rm": "rf"})
    assert result["settings"]["app_window"] is False
    assert "evil_key" not in result["settings"]
    assert result["imported"] == ["app_window"]


def test_import_rejects_when_nothing_recognised(isolated_home):
    with pytest.raises(ValueError):
        settings_backup.import_settings({"totally_unknown": 1})
