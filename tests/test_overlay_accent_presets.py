"""The overlay look presets named after the app accents (Crimson, Emerald,
Azure, Amethyst, Rose) must actually match those accents: each preset's header
and glow colour equals the accent's `--gold` value defined in app.css, so the
"matched to the accent" promise can't silently drift when an accent is retuned.
Each also needs a dropdown description and must validate as a visual preset."""
import re
import pathlib

from aion2calc.app import settings_backup
from tests.test_settings_backup import _extract_bundled_presets

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
APPJS = (STATIC / "app.js").read_text(encoding="utf-8")

ACCENTS = ["Crimson", "Emerald", "Azure", "Amethyst", "Rose"]


def _accent_gold(name: str) -> str:
    m = re.search(rf":root\[data-accent={name.lower()}\]\s*\{{[^}}]*?--gold:\s*(#[0-9a-fA-F]{{6}})", CSS)
    assert m, f"no --gold for accent {name} in app.css"
    return m.group(1).lower()


def test_accent_presets_exist_and_match_their_accent_colour():
    presets = _extract_bundled_presets()
    for name in ACCENTS:
        assert name in presets, f"{name} preset missing"
        p = presets[name]
        gold = _accent_gold(name)
        assert p["overlay_text_colors"]["header"].lower() == gold, f"{name} header != accent"
        assert p["overlay_glow_color"].lower() == gold, f"{name} glow != accent"
        assert p["overlay_glow"] is True


def test_accent_presets_validate_as_visual_presets():
    presets = _extract_bundled_presets()
    for name in ACCENTS:
        cleaned = settings_backup.clean_presets([{"name": name, "settings": presets[name]}])[0]["settings"]
        assert set(cleaned) == set(presets[name]), f"{name} carries an unrecognised visual key"


def test_accent_presets_have_descriptions():
    for name in ACCENTS:
        assert re.search(rf'"{name}":"[^"]+"', APPJS), f"{name} missing a preset description"
