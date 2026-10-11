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

_BOOL_KEYS = ("app_window", "auto_update", "overlay_on_start", "tray_on_close",
              "overlay_show_contribution", "overlay_show_target",
              "overlay_show_deaths", "overlay_show_enemy_hp", "overlay_show_ttk",
              "meter_reset_after_battle", "meter_show_dummy_parse", "overlay_show_combat_power",
              "overlay_only_in_combat", "overlay_auto_expand",
              "overlay_resizable", "overlay_snap_edge", "overlay_expand_up",
              "overlay_glow", "overlay_long_names_scroll", "overlay_party_enabled")

# key -> (min, max) for whole-number settings.
_INT_KEYS = {"meter_reset_delay": (1, 120), "meter_max_records": (1, 500),
             "meter_dummy_record_seconds": (5, 3600),
             "overlay_max_players": (1, 24), "overlay_width": (260, 800), "overlay_row_height": (14, 48),
             "overlay_font_scale": (80, 160), "overlay_font_weight": (400, 800),
             "overlay_bg_opacity": (0, 100), "overlay_bg_zoom": (50, 200), "overlay_bg_darken": (0, 100)}

_FONT_FAMILIES = ("", "Segoe UI", "Arial", "Verdana", "Georgia", "Trebuchet MS", "Consolas", "Tahoma")


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
            if not (isinstance(value, dict) and set(value) <= {"rate", "total", "name", "header"}
                    and all(_is_hex(v) for v in value.values())):
                raise ValueError("overlay_text_colors must be six-digit hex colors for rate, total, name or header")
            clean[key] = {k: v.lower() for k, v in value.items()}
        elif key == "overlay_glow_color":
            if not _is_hex(value):
                raise ValueError("overlay_glow_color must be a six-digit hex color")
            clean[key] = value.lower()
        elif key == "overlay_font_family":
            if value not in _FONT_FAMILIES:
                raise ValueError("overlay_font_family must be one of the available fonts")
            clean[key] = value
        elif key == "combat_colors":
            if not (isinstance(value, dict) and all(isinstance(k, str) and _is_hex(v) for k, v in value.items())):
                raise ValueError("combat_colors must map class names to six-digit hex colors")
            clean[key] = {k: v.lower() for k, v in value.items()}
        # Any other key is ignored rather than trusted.
    return clean


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
