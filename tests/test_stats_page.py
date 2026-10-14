"""The public Class-stats page (GitHub Pages) renders the server's class statistics.

``site/stats.js`` reads the server's ``/api/v1/stats`` (the class index) and
``/api/v1/stats/<class>`` (per-class medians, hit rates, tempo and damage-by-skill)
through ``A2.api`` — the same data the server's own ``/stats`` page uses — and renders
it defensively so a missing field or an unreachable server never breaks the page. The
page must load ``server.js`` (which defines ``window.A2``) before ``stats.js``, and the
nav on every site page must link to it. This guards that wiring."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
STATS_HTML = (SITE / "stats.html").read_text(encoding="utf-8")
STATS_JS = (SITE / "stats.js").read_text(encoding="utf-8")


def test_stats_js_reads_the_real_server_endpoints():
    # The class index and the per-class detail — the same endpoints the server's /stats uses.
    assert '"/api/v1/stats"' in STATS_JS
    assert "/api/v1/stats/" in STATS_JS
    # Goes through the shared A2 client (resolves the share server, retries), not a raw fetch.
    assert "A2.api(" in STATS_JS


def test_stats_html_loads_server_before_stats():
    for dep in ("config.js", "server.js", "stats.js", "navigation.js"):
        assert f'src="{dep}"' in STATS_HTML, f"stats.html must load {dep}"
    # stats.js calls A2.api at load, so server.js (which defines window.A2) must come first.
    assert STATS_HTML.index('src="server.js"') < STATS_HTML.index('src="stats.js"')


def test_filters_are_dropdowns_not_buttons():
    # Class and boss filters are <select> dropdowns (replacing the old chip buttons).
    assert 'id="class-select"' in STATS_HTML and "<select" in STATS_HTML
    assert 'id="boss-select"' in STATS_HTML


def test_default_view_is_performance_by_class():
    # The initial page (no class selected) compares classes by median DPS, not one class's skills.
    assert "renderOverview" in STATS_JS
    assert "Performance by class" in STATS_JS
    # ...with a bar graph (the shared .bar component) of median DPS.
    assert "All classes" in STATS_JS
    assert 'class="bar"' in STATS_JS


def test_stats_page_marks_itself_active_in_the_nav():
    assert 'href="stats.html" class="on" aria-current="page"' in STATS_HTML


def test_every_site_page_links_to_the_stats_page():
    # The nav is shared across the site; a new top-level page must appear on every page.
    pages = sorted(SITE.glob("*.html"))
    assert pages, "no site pages found"
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert 'href="stats.html"' in html, f"{page.name} is missing the Class stats nav link"
