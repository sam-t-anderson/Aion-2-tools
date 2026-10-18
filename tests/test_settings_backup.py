"""Export/restore of overlay & app settings: a round-trip preserves recognised
settings, and import validates types and ignores unknown or tampered keys so a
foreign file can never inject arbitrary state."""
import json
import re
from pathlib import Path

import pytest

from aion2calc.app import settings_backup

_APP_JS = Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "app.js"


def _extract_bundled_presets() -> dict:
    """Pull the BUNDLED_PRESETS object literal out of app.js and parse it as JSON.
    The literal uses bare identifier keys and simple string/number/bool/{} values,
    so quoting the identifier keys yields valid JSON."""
    text = _APP_JS.read_text(encoding="utf-8")
    start = text.index("const BUNDLED_PRESETS=") + len("const BUNDLED_PRESETS=")
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                i += 1
                break
        i += 1
    literal = text[start:i]
    # Quote bare identifier keys (already-quoted string keys like "Default (gold)" are left alone).
    literal = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', literal)
    literal = re.sub(r',(\s*[}\]])', r'\1', literal)  # drop JS trailing commas for JSON
    return json.loads(literal)


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
                                              "overlay_height": 260, "overlay_row_height": 28,
                                              "overlay_only_in_combat": True, "overlay_auto_expand": True})
    s = result["settings"]
    assert (s["overlay_max_players"], s["overlay_width"], s["overlay_row_height"]) == (12, 420, 28)
    assert s["overlay_height"] == 260
    assert s["overlay_only_in_combat"] is True and s["overlay_auto_expand"] is True
    # overlay_height 0 means "fit to contents" and is a valid value.
    assert settings_backup.import_settings({"overlay_height": 0})["settings"]["overlay_height"] == 0
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_max_players": 99})     # above range (max 24)
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_width": 100})          # below range (min 260)
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_height": 900})         # above range (max 800)


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


def test_overlay_always_visible_round_trips(isolated_home):
    # Default-on boolean: both true and false survive an import round-trip.
    assert settings_backup.import_settings({"overlay_always_visible": False})["settings"]["overlay_always_visible"] is False
    assert settings_backup.import_settings({"overlay_always_visible": True})["settings"]["overlay_always_visible"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_always_visible": "yes"})


def test_overlay_ttk_color_round_trips_and_validates(isolated_home):
    # The TTK bar colour rides the backup like the other overlay colours.
    s = settings_backup.import_settings({"overlay_ttk_color": "#36D1A0"})["settings"]
    assert s["overlay_ttk_color"] == "#36d1a0"   # normalised to lower-case
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_ttk_color": "nope"})


def test_overlay_text_colors_accepts_target_line_elements(isolated_home):
    # The per-element pickers extend overlay_text_colors with the target-line
    # readouts (target text, enemy-HP text, TTK text); unknown keys are rejected.
    s = settings_backup.import_settings({"overlay_text_colors":
                                         {"target": "#CDd6E6", "hp": "#E58F8F", "ttk": "#8FB3D0"}})["settings"]
    assert s["overlay_text_colors"] == {"target": "#cdd6e6", "hp": "#e58f8f", "ttk": "#8fb3d0"}
    # ...and the secondary text elements (labels, also-targets +N, ping, identity).
    s2 = settings_backup.import_settings({"overlay_text_colors":
                                          {"label": "#E8CF8E", "also": "#C9A86A", "ping": "#9AA3B5",
                                           "identity": "#8FD0A0"}})["settings"]
    assert s2["overlay_text_colors"] == {"label": "#e8cf8e", "also": "#c9a86a", "ping": "#9aa3b5",
                                         "identity": "#8fd0a0"}
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_colors": {"bogus": "#000000"}})
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_colors": {"target": "not-a-hex"}})


def test_bundled_overlay_presets_are_all_valid(isolated_home):
    # Every shipped starter theme must pass the same validation as a user preset:
    # only recognised visual keys, every value well-typed. Catches a typo'd hex or
    # a stray key before it reaches users.
    presets = _extract_bundled_presets()
    assert set(presets) >= {"Default (gold)", "High contrast", "Neon", "Minimal",
                            "Midnight blue", "Ember"}
    for name, settings in presets.items():
        cleaned = settings_backup.clean_presets([{"name": name, "settings": settings}])[0]["settings"]
        # No key was dropped -> every key in the preset is a recognised visual key.
        assert set(cleaned) == set(settings), f"{name} carries an unrecognised visual key"


def test_overlay_bar_style_settings_round_trip_and_validate(isolated_home):
    s = settings_backup.import_settings({"overlay_bar_style": "gradient",
                                         "overlay_bar_rounded": True,
                                         "overlay_class_color_names": True})["settings"]
    assert s["overlay_bar_style"] == "gradient"
    assert s["overlay_bar_rounded"] is True and s["overlay_class_color_names"] is True
    assert settings_backup.import_settings({"overlay_bar_style": "flat"})["settings"]["overlay_bar_style"] == "flat"
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_bar_style": "stripes"})
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_bar_rounded": "yes"})


def test_overlay_rank_numbers_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_rank_numbers": True})["settings"]["overlay_rank_numbers"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_rank_numbers": 0})


def test_overlay_compact_rows_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_compact_rows": True})["settings"]["overlay_compact_rows"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_compact_rows": "x"})


def test_overlay_highlight_me_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_highlight_me": True})["settings"]["overlay_highlight_me"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_highlight_me": 1})


def test_meter_auto_upload_round_trips(isolated_home):
    assert settings_backup.import_settings({"meter_auto_upload": False})["settings"]["meter_auto_upload"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"meter_auto_upload": "yes"})


def test_overlay_open_on_app_start_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_open_on_app_start": False})["settings"]["overlay_open_on_app_start"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_open_on_app_start": "yes"})


def test_overlay_dps_graph_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_dps_graph": True})["settings"]["overlay_dps_graph"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_dps_graph": 1})


def test_overlay_dps_graph_rides_overlay_presets(isolated_home):
    # The live-graph toggle is a visual key, so a named overlay look preset carries it.
    saved = settings_backup.import_settings(
        {"overlay_presets": [{"name": "Graphed", "settings": {"overlay_dps_graph": True}}]}
    )["settings"]
    assert saved["overlay_presets"][0]["settings"]["overlay_dps_graph"] is True


def test_overlay_class_swatch_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_class_swatch": True})["settings"]["overlay_class_swatch"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_class_swatch": 1})


def test_overlay_row_stripes_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_row_stripes": True})["settings"]["overlay_row_stripes"] is True
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_row_stripes": "yes"})


def test_overlay_color_cycle_round_trips(isolated_home):
    assert settings_backup.import_settings({"overlay_color_cycle": True})["settings"]["overlay_color_cycle"] is True
    assert settings_backup.import_settings({"overlay_color_cycle": False})["settings"]["overlay_color_cycle"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_color_cycle": "on"})


def test_overlay_text_outline_round_trips_and_validates(isolated_home):
    # The text-outline toggle (bool) and its colour both ride the backup.
    s = settings_backup.import_settings({"overlay_text_outline": True,
                                         "overlay_outline_color": "#1A2B3C"})["settings"]
    assert s["overlay_text_outline"] is True
    assert s["overlay_outline_color"] == "#1a2b3c"
    assert settings_backup.import_settings({"overlay_text_outline": False})["settings"]["overlay_text_outline"] is False
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_text_outline": "on"})
    with pytest.raises(ValueError):
        settings_backup.import_settings({"overlay_outline_color": "black"})


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


def test_overlay_show_events_is_a_recognised_bool_setting(isolated_home):
    """The overlay event-notifications toggle round-trips and is validated as a
    boolean, so it backs up/restores like the other overlay switches and a foreign
    non-bool value for it is rejected rather than stored."""
    from aion2calc.paths import write_user_json
    assert "overlay_show_events" in settings_backup._BOOL_KEYS
    write_user_json({"overlay_show_events": False}, "ui.json")
    assert settings_backup.export_settings()["settings"]["overlay_show_events"] is False
    result = settings_backup.import_settings({"settings": {"overlay_show_events": True}})
    assert result["settings"]["overlay_show_events"] is True
    # a non-boolean value for it is ignored (type-validated), not stored
    with pytest.raises(ValueError):
        settings_backup.import_settings({"settings": {"overlay_show_events": "yes"}})


def test_overlay_show_events_defaults_on(isolated_home):
    """Event notifications ship on by default (a toggle turns them off)."""
    from aion2calc.app.server import ui_settings
    assert ui_settings()["overlay_show_events"] is True


# Settings → Class colors saves a switch plus one colour per class (combat-review.js);
# "Reset class colors" saves {}.
_CLASS_COLORS = {"enabled": False, "colors": {"gladiator": "#C69B6D", "templar": "#f58cba", "assassin": "#fff468",
                                              "ranger": "#aad372", "sorcerer": "#3fc7eb", "spiritmaster": "#8788ee",
                                              "cleric": "#ffffff", "chanter": "#ff7c0a"}}


def test_class_colors_round_trip_through_the_app_routes(isolated_home):
    # A backup made after any class colour change failed to import, and "Save current look
    # as…" failed the same way: the check wanted a bare {class: colour} map, which the app
    # never saves. Driven through the app's own routes, as the Settings page does.
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from aion2calc.app import server as app
    from aion2calc.paths import write_user_json
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        colors = post("/api/ui", {"combat_colors": _CLASS_COLORS})["combat_colors"]
        assert colors == {"enabled": False, "colors": {k: v.lower() for k, v in _CLASS_COLORS["colors"].items()}}
        post("/api/ui", {"overlay_presets": [{"name": "Mine", "settings": {"combat_colors": colors}}]})
        document = json.loads(Path(post("/api/ui/export", {})["file"]).read_text(encoding="utf-8"))
        write_user_json({}, "ui.json")
        restored = post("/api/ui/import", {"document": document})["settings"]
        assert restored["combat_colors"] == colors
        assert restored["overlay_presets"][0]["settings"]["combat_colors"] == colors
        assert post("/api/ui", {"combat_colors": {}})["combat_colors"] == {}         # Reset class colors
        with pytest.raises(urllib.error.HTTPError):       # the app stores only what an import accepts
            post("/api/ui", {"combat_colors": {"sorcerer": "#3fc7eb"}})
    finally:
        srv.shutdown()


def test_class_colors_reject_other_shapes(isolated_home):
    for bad in ({"sorcerer": "#3fc7eb"},                  # a bare class map: the app reads colors from "colors"
                {"colors": {"bard": "#3fc7eb"}},          # not a class
                {"colors": {"sorcerer": "blue"}},         # not a six-digit hex colour
                {"enabled": "yes"},
                "#3fc7eb"):
        with pytest.raises(ValueError):
            settings_backup.import_settings({"combat_colors": bad})


def test_a_fresh_install_backup_imports(isolated_home):
    # Every default the export writes passes the import's checks.
    document = json.loads(Path(settings_backup.export_settings()["file"]).read_text(encoding="utf-8"))
    assert settings_backup.import_settings(document)["imported"]
