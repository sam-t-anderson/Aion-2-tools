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


def test_default_view_is_performance_by_class_with_a_spread_graph():
    # The initial page (no class selected) compares classes, not one class's skills.
    assert "renderOverview" in STATS_JS
    assert "Performance by class" in STATS_JS
    assert "All classes" in STATS_JS
    # ...as an a2tools.app-style spread graph (box/whisker per class on a shared DPS axis).
    assert "function spread" in STATS_JS
    assert "<svg" in STATS_JS
    assert ">Spread" in STATS_JS


def test_overview_and_kpi_columns_say_dps():
    # The user asked the Top 25% / Top 10% columns be clarified as DPS.
    assert "Top 25% DPS" in STATS_JS
    assert "Top 10% DPS" in STATS_JS
    assert "Top 25% from" not in STATS_JS and "Top 10% from" not in STATS_JS


def test_stats_show_best_dps_median_gear_and_combat_power():
    # Headline numbers the user asked for, read from the server aggregate (best_dps/gear_score/combat_power).
    assert "Best DPS" in STATS_JS
    assert "Gear score" in STATS_JS and "Combat power" in STATS_JS
    for field in ("best_dps", "gear_score", "combat_power"):
        assert field in STATS_JS, f"stats.js must read s.{field}"


def test_spread_graph_has_a_cursor_hover_readout():
    # Hovering the spread reports the DPS and percentile band under the cursor.
    assert "wireSpread" in STATS_JS
    assert "data-spread" in STATS_JS      # the SVG carries its markers for the read-out
    assert "spread-tip" in STATS_JS       # the floating tooltip
    assert "mousemove" in STATS_JS


def test_stats_page_marks_itself_active_in_the_nav():
    assert 'href="stats.html" class="on" aria-current="page"' in STATS_HTML


def test_every_site_page_links_to_the_stats_page():
    # The nav is shared across the site; a new top-level page must appear on every page.
    pages = sorted(SITE.glob("*.html"))
    assert pages, "no site pages found"
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert 'href="stats.html"' in html, f"{page.name} is missing the Class stats nav link"
