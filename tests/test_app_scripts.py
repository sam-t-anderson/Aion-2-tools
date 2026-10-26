"""The app's scripts: app.js holds what every page shares (the helpers, the navigation, the router and the
launch) and each page draws itself from its own script in static/pages/. What the pages do is checked in a
browser (tests/browser); this checks that index.html loads every page's script, after app.js."""
import pathlib
import re

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"


def test_index_loads_app_js_and_then_every_page_script_once():
    scripts = re.findall(r'<script src="/static/([^"]+)"', (STATIC / "index.html").read_text(encoding="utf-8"))
    pages = [s for s in scripts if s.startswith("pages/")]
    assert sorted(pages) == sorted(f"pages/{p.name}" for p in (STATIC / "pages").glob("*.js"))
    assert len(set(pages)) == len(pages)
    # the pages use app.js's helpers as they load, and app.js starts the app once they have all loaded
    assert scripts[-len(pages) - 1:] == ["app.js"] + pages


def test_each_page_script_is_strict_like_app_js():
    for path in [STATIC / "app.js", *sorted((STATIC / "pages").glob("*.js"))]:
        code = re.sub(r"^/\*.*?\*/\s*", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert code.startswith('"use strict";'), path.name
