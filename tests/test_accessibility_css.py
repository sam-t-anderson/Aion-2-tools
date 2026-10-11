"""Accessibility baseline in the shared stylesheet (loaded by both the app and the
GitHub Pages site): the operating system's reduce-motion preference is honored, and
keyboard focus stays visible on every interactive control. Guards against a later
edit dropping either — both are claimed in docs/accessibility.md."""
import re
import pathlib

CSS = (pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "app.css").read_text(encoding="utf-8")


def test_reduced_motion_preference_is_honored():
    m = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.+?\})\s*\}", CSS, re.S)
    assert m, "no prefers-reduced-motion block in app.css"
    block = m.group(1)
    assert "animation-duration" in block and "transition-duration" in block


def test_keyboard_focus_is_visible():
    # A :focus-visible rule gives interactive controls an outline (not 'none').
    assert ":focus-visible" in CSS
    m = re.search(r":focus-visible\s*\{[^}]*\}", CSS)
    assert m and "outline:" in m.group(0) and "outline: none" not in m.group(0)
    # The form fields that drop the outline on plain :focus must restore it on :focus-visible.
    assert "input:focus-visible" in CSS
