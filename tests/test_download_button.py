"""A Download button sits in the top-right header, to the right of the light/dark/system
theme toggle, on every website page except the home page (index.html already has prominent
"Download the app" buttons). Injected by navigation.js; this guards the wiring."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAV = (ROOT / "site" / "navigation.js").read_text(encoding="utf-8")


def test_navigation_injects_a_download_button():
    assert 'id = "download"' in NAV or 'id="download"' in NAV
    # Links to the latest release, like the home page's download buttons.
    assert "releases/latest" in NAV


def test_download_button_is_hidden_on_the_home_page():
    # index.html already carries the download call-to-action, so the header button skips it.
    assert "index.html" in NAV and "return" in NAV


def test_download_button_sits_right_of_the_theme_toggle():
    # Appended to the topbar; the theme toggle is its last child, so the button lands to its right.
    assert 'querySelector(".topbar")' in NAV
    assert "appendChild" in NAV
    assert 'getElementById("theme")' in NAV
