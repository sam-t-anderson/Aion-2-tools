"""The overlay's "New" button starts a fresh encounter split without alt-tabbing
to the app. It must stay wired to the existing /api/meter split action (the same
one the Live Meter page's "Split now" uses), be grouped with the framed header
controls, and clear the live graph so the next fight starts clean."""
import pathlib

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
HTML = (STATIC / "overlay.html").read_text(encoding="utf-8")
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
CSS = (STATIC / "overlay.css").read_text(encoding="utf-8")


def test_button_present_in_header():
    assert 'id="ovsplit"' in HTML


def test_button_posts_the_split_action():
    assert "#ovsplit" in JS
    assert 'action:"split"' in JS or '"action":"split"' in JS
    # Starting a new fight clears the live graph history.
    assert "graphHist=[]" in JS


def test_button_is_styled_with_the_other_header_controls():
    # Grouped into the framed button selectors (also fixes the older unstyled Copy).
    assert "#ovsplit" in CSS and "#ovcopy" in CSS
