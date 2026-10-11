"""A "skip to content" link is the first focusable element on every page — the
desktop app (static markup) and all website pages (injected by navigation.js) —
hidden until focused, then jumping to the main landmark. Closes the last gap in
docs/accessibility.md; this guards the wiring."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / "aion2calc" / "app" / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "aion2calc" / "app" / "static" / "app.css").read_text(encoding="utf-8")
NAV = (ROOT / "site" / "navigation.js").read_text(encoding="utf-8")


def test_app_has_skip_link_before_the_header():
    assert 'class="skip-link" href="#app"' in INDEX
    # It must come before the topbar so it is the first thing a keyboard reaches.
    assert INDEX.index("skip-link") < INDEX.index('class="topbar"')
    assert '<main id="app">' in INDEX


def test_skip_link_is_hidden_until_focused():
    assert ".skip-link {" in CSS and ".skip-link:focus" in CSS
    # Off-screen by default (negative top), on-screen on focus.
    block = CSS.split(".skip-link {", 1)[1].split("}", 1)[0]
    assert "top: -" in block


def test_site_navigation_injects_a_skip_link():
    assert 'class = "skip-link"' in NAV or 'className = "skip-link"' in NAV
    assert "Skip to content" in NAV
    assert 'querySelector("main")' in NAV
