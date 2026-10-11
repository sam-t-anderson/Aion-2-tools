"""The class-colour palette presets (app customization presets in
combat-review.js) must stay well-formed: every inline palette assigns all eight
classes a six-digit hex colour, so applying one can never leave a class
uncoloured. Extracted from the JS the same way the bundled overlay-preset test
reads app.js."""
import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")

CLASSES = {"gladiator", "templar", "assassin", "ranger",
           "sorcerer", "spiritmaster", "cleric", "chanter"}


def test_default_palette_reuses_defaults():
    # The Default palette must point at the same `defaults` map the app ships,
    # so "Default" always matches an unset / reset state.
    assert '"Default (class colours)": defaults' in SRC


def test_inline_palettes_cover_all_classes_with_hex():
    blocks = re.findall(r'\{gladiator:"#[0-9a-f]{6}"[^}]*\}', SRC)
    # Colourblind-friendly, High contrast, Pastel, Vivid.
    assert len(blocks) >= 4
    for block in blocks:
        pairs = dict(re.findall(r'(\w+):"(#[0-9a-f]{6})"', block))
        assert set(pairs) == CLASSES, f"palette missing/extra classes: {set(pairs) ^ CLASSES}"
        assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in pairs.values())


def test_colourblind_palette_is_present():
    # Accessibility preset must stay available by name.
    assert '"Colourblind-friendly":' in SRC
