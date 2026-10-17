"""Export and restore the app's overlay/meter settings as a shareable file.

Export writes the current UI settings to a JSON file in the data folder that the
user can keep or hand to a friend; import validates such a file and merges the
recognised settings back in. Only known keys with checked types are applied, so
a hand-edited or foreign file can never inject arbitrary state.
"""
from __future__ import annotations

import json
import time

from ..paths import home, write_user_json

FORMAT = "aion2calc-settings"
VERSION = 1

_BOOL_KEYS = ("app_window", "auto_update", "overlay_on_start", "tray_on_close", "community_heartbeat",
              "overlay_show_contribution", "overlay_show_target",
              "overlay_show_deaths", "overlay_show_enemy_hp", "overlay_show_ttk",
              "overlay_show_cooldowns", "overlay_show_break_gauge",
              "meter_reset_after_battle", "meter_show_dummy_parse", "overlay_show_combat_power",
              "overlay_only_in_combat", "overlay_auto_expand",
              "overlay_resizable", "overlay_snap_edge", "overlay_expand_up",
              "overlay_glow", "overlay_long_names_scroll", "overlay_party_enabled",
              "meter_save_records", "overlay_dps_interpolate", "overlay_show_fps",
              "overlay_always_visible", "overlay_remember_position", "overlay_click_through",
              "overlay_close_on_stop", "overlay_text_outline", "overlay_text_halo", "overlay_text_retro",
              "overlay_bar_rounded", "overlay_class_color_names", "overlay_color_cycle",
              "overlay_row_stripes", "overlay_class_swatch", "overlay_compact_rows", "overlay_rank_numbers",
              "overlay_highlight_me", "overlay_dps_graph", "overlay_show_community_rank", "overlay_show_events", "overlay_events_sound", "overlay_open_on_app_start", "meter_auto_upload", "meter_upload_before_prune", "meter_report_boss_kills", "meter_report_enemy_hp", "overlay_plan_autoplay", "meter_autostart", "community_contribute_character", "meter_show_server_name", "overlay_live_community_rank", "meter_report_diagnostics")

# key -> (min, max) for whole-number settings.
_INT_KEYS = {"meter_reset_delay": (1, 120), "meter_max_records": (1, 500),
             "meter_dummy_record_seconds": (5, 3600), "meter_log_cache_mb": (0, 1048576),
             "overlay_max_players": (1, 24), "overlay_width": (260, 800), "overlay_height": (0, 800),
             "overlay_row_height": (14, 48),
             "overlay_font_scale": (80, 160), "overlay_font_weight": (400, 800),
             "overlay_bg_opacity": (0, 100), "overlay_bg_zoom": (50, 200), "overlay_bg_darken": (0, 100),
             "overlay_interpolate_ms": (50, 1000),
             "overlay_cooldowns_min_s": (1, 120), "overlay_cooldowns_max": (1, 16)}

_FONT_FAMILIES = ("", "Segoe UI", "Arial", "Verdana", "Georgia", "Trebuchet MS", "Consolas", "Tahoma")

# The look-and-feel settings a named overlay preset may carry (the overlay's
# visual appearance only; never the background image, layout counts or behaviour).
_VISUAL_KEYS = ("overlay_text_colors", "overlay_glow", "overlay_glow_color", "overlay_hp_color",
                "overlay_ttk_color", "overlay_text_outline", "overlay_outline_color",
                "overlay_bar_style", "overlay_bar_rounded", "overlay_class_color_names", "overlay_row_stripes", "overlay_class_swatch", "overlay_compact_rows", "overlay_rank_numbers", "overlay_highlight_me", "overlay_dps_graph",
                "overlay_text_fonts", "overlay_text_halo", "overlay_halo_color", "overlay_text_retro",
                "overlay_font_family", "overlay_font_scale", "overlay_font_weight",
                "overlay_bg_opacity", "overlay_bg_zoom", "overlay_bg_darken",
                "overlay_name_mode", "overlay_long_names_scroll", "combat_colors")


def _is_hex(value) -> bool:
    return (isinstance(value, str) and len(value) == 7 and value[0] == "#"
            and all(c in "0123456789abcdefABCDEF" for c in value[1:]))


def _clean(data: dict) -> dict:
    """Keep only recognised settings, each type-checked. Unknown keys are dropped
    so a newer or tampered file cannot write unexpected state."""
    clean: dict = {}
    for key, value in data.items():
        if key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
            clean[key] = value
        elif key in _INT_KEYS:
            lo, hi = _INT_KEYS[key]
            if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
                raise ValueError(f"{key} must be a whole number from {lo} to {hi}")
            clean[key] = value
        elif key == "overlay_text_colors":
            if not (isinstance(value, dict)
                    and set(value) <= {"rate", "total", "name", "header", "target", "hp", "ttk",
                                       "label", "also", "ping", "identity"}
                    and all(_is_hex(v) for v in value.values())):
                raise ValueError("overlay_text_colors must be six-digit hex colors for rate, total, name, "
                                 "header, target, hp, ttk, label, also, ping or identity")
            clean[key] = {k: v.lower() for k, v in value.items()}
        elif key in ("overlay_glow_color", "overlay_hp_color", "overlay_ttk_color", "overlay_outline_color", "overlay_halo_color"):
            if not _is_hex(value):
                raise ValueError(f"{key} must be a six-digit hex color")
            clean[key] = value.lower()
        elif key == "overlay_text_fonts":
            elements = {"rate", "total", "name", "header", "target", "hp", "ttk", "label", "also", "ping", "identity"}
            if not (isinstance(value, dict) and set(value) <= elements):
                raise ValueError("overlay_text_fonts keys must be known overlay text elements")
            fonts: dict = {}
            for element, spec in value.items():
                if not (isinstance(spec, dict) and set(spec) <= {"family", "scale", "weight"}):
                    raise ValueError("each overlay_text_fonts entry may set family, scale and/or weight")
                entry = {}
                if spec.get("family"):
                    if spec["family"] not in _FONT_FAMILIES:
                        raise ValueError("overlay_text_fonts family must be one of the available fonts")
                    entry["family"] = spec["family"]
                for prop, lo, hi in (("scale", 80, 160), ("weight", 400, 800)):
                    if spec.get(prop) is not None:
                        if not isinstance(spec[prop], int) or isinstance(spec[prop], bool) or not lo <= spec[prop] <= hi:
                            raise ValueError(f"overlay_text_fonts {prop} must be a whole number from {lo} to {hi}")
                        entry[prop] = spec[prop]
                if entry:
                    fonts[element] = entry
            clean[key] = fonts
        elif key == "overlay_font_family":
            if value not in _FONT_FAMILIES:
                raise ValueError("overlay_font_family must be one of the available fonts")
            clean[key] = value
        elif key == "overlay_name_mode":
            if value not in ("name", "class_number", "number"):
                raise ValueError("overlay_name_mode must be name, class_number or number")
            clean[key] = value
        elif key == "overlay_bar_style":
            if value not in ("flat", "gradient"):
                raise ValueError("overlay_bar_style must be flat or gradient")
            clean[key] = value
        elif key == "overlay_cooldowns_position":
            if value not in ("bottom", "top"):
                raise ValueError("overlay_cooldowns_position must be bottom or top")
            clean[key] = value
        elif key == "combat_colors":
            if not (isinstance(value, dict) and all(isinstance(k, str) and _is_hex(v) for k, v in value.items())):
                raise ValueError("combat_colors must map class names to six-digit hex colors")
            clean[key] = {k: v.lower() for k, v in value.items()}
        elif key == "overlay_presets":
            clean[key] = clean_presets(value)
        elif key == "hotkeys":
            from . import hotkeys as _hotkeys
            clean[key] = _hotkeys.clean_hotkeys(value)
        # Any other key is ignored rather than trusted.
    return clean


def clean_presets(value) -> list:
    """Validate a list of named overlay look presets. Each preset carries a name
    and a settings object restricted to the visual keys, type-checked exactly as a
    normal settings import, so a preset can never inject unexpected or unsafe state."""
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError("overlay_presets must be a list of at most 50 presets")
    out, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each overlay preset must be an object")
        name = str(item.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ValueError("each overlay preset needs a name of 1 to 40 characters")
        if name.casefold() in seen:
            raise ValueError("overlay preset names must be unique")
        seen.add(name.casefold())
        settings = item.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("each overlay preset needs a settings object")
        out.append({"name": name, "settings": _clean({k: v for k, v in settings.items() if k in _VISUAL_KEYS})})
    return out


def export_settings() -> dict:
    """Write the current settings to a shareable file; return its path and contents."""
    from .server import ui_settings
    from .. import __version__

    settings = ui_settings()
    document = {"format": FORMAT, "version": VERSION, "app_version": __version__,
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "settings": settings}
    path = home() / f"aion2calc-settings-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"file": str(path), "settings": settings}


def import_settings(payload) -> dict:
    """Validate an exported document (or a bare settings object) and merge the
    recognised settings into the stored UI settings. Returns the result."""
    from .server import ui_settings

    if not isinstance(payload, dict):
        raise ValueError("Settings file must be a JSON object")
    if payload.get("format") not in (None, FORMAT):
        raise ValueError("This file is not an Aion 2 Calc settings backup")
    data = payload.get("settings", payload)
    if not isinstance(data, dict):
        raise ValueError("Settings backup has no settings object")
    clean = _clean(data)
    if not clean:
        raise ValueError("No recognised settings to import")
    current = ui_settings()
    current.update(clean)
    write_user_json(current, "ui.json")
    return {"settings": current, "imported": sorted(clean)}
