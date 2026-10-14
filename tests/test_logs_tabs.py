"""The public Logs page splits into four views, each backed by a live server endpoint.

Beyond the existing Community browse/upload/review workflow (kept intact), the page adds three
aggregate-leaderboard tabs — Completed-run speed, Boss progression and Highest observed build
points — each rendered from the server's own public endpoint through ``A2.api`` and read
defensively so a missing field or an unreachable/empty endpoint never breaks the page. The old
Class-performance tab was removed as redundant with the Class stats page. This guards the tab
wiring, the endpoint references, and that the upload/review workflow is preserved."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
LOGS_HTML = (SITE / "logs.html").read_text(encoding="utf-8")
LOGS_JS = (SITE / "logs.js").read_text(encoding="utf-8")


def test_logs_page_has_the_four_tabs():
    for tab in ("community", "speed", "progression", "points"):
        assert f'data-tab="{tab}"' in LOGS_HTML, f"missing tab button {tab}"
        assert f'data-logs-panel="{tab}"' in LOGS_HTML, f"missing panel {tab}"


def test_class_performance_tab_was_removed():
    # Redundant with the dedicated Class stats page; dropped so it isn't a near-empty duplicate.
    assert 'data-tab="classes"' not in LOGS_HTML
    assert "renderClasses" not in LOGS_JS


def test_each_analytical_tab_reads_its_server_endpoint():
    # The same public endpoints the server already serves; via the shared A2 client, not raw fetch.
    assert '"/api/v1/run-leaderboard' in LOGS_JS          # Completed-run speed
    assert '"/api/v1/encounter-progression"' in LOGS_JS   # Boss progression
    assert '"/api/v1/progression"' in LOGS_JS              # Highest observed build points
    assert "A2.api(" in LOGS_JS


def test_community_upload_and_review_workflow_is_preserved():
    # The new tabs must not drop the existing upload/review wiring.
    for anchor in ('id="combat-log-tabs"', 'id="archive-upload"', 'id="archive-review"', 'id="community"'):
        assert anchor in LOGS_HTML, f"lost workflow anchor {anchor}"
    assert "A2ArchiveUpload.mount" in LOGS_JS


def test_progression_tab_has_icons_filters_region_product_and_alpha_sort():
    # Boss progression: boss portrait left of the name, facet filters (boss/difficulty/region/product),
    # Region + Product columns, and an alphabetical (by boss) sort.
    assert "progression-body" in LOGS_JS
    for sel in ('id="pf-boss"', 'id="pf-difficulty"', 'id="pf-region"', 'id="pf-game_patch"'):
        assert sel in LOGS_JS, f"missing progression filter {sel}"
    # Region + Product columns added alongside the existing Boss / Difficulty columns.
    assert "<th>Boss</th><th>Difficulty</th><th>Region</th><th>Product</th>" in LOGS_JS
    # The boss portrait (server-resolved per group) sits in the shared boss-cell with the mob-ic style.
    assert "g.icon" in LOGS_JS and "boss-cell" in LOGS_JS
    # Alphabetical sort by boss name (then difficulty), not by attempt count.
    assert 'String(a.boss || "").localeCompare(String(b.boss || "")' in LOGS_JS
    # Driven by the server's own facets, and the filters are passed to the progression endpoint.
    assert "/api/v1/report-facets" in LOGS_JS and "/api/v1/encounter-progression" in LOGS_JS


def test_community_tab_is_one_row_per_encounter():
    # The Community combat logs view is a per-encounter table (flattened from /api/v1/logs
    # contexts[]), filterable by boss, not the old per-log browse widget.
    assert "renderCommunity" in LOGS_JS
    assert "/api/v1/logs?" in LOGS_JS and 'p.set("page"' in LOGS_JS   # paged request, now with filter params
    assert "contexts" in LOGS_JS
    # Columns the user asked for: boss, difficulty, party, time, uploaded-by, date, product version.
    for col in (">Boss<", ">Difficulty<", ">Party<", ">Time<", ">Uploaded by<", ">Date<", ">Product<"):
        assert col in LOGS_JS, f"missing community column {col}"
    # Anonymous fallback when the server has no uploader for a log.
    assert "Anonymous" in LOGS_JS


def test_community_pagination_is_50_per_page():
    assert "COMM_PER_PAGE = 50" in LOGS_JS


def test_community_drops_generic_combat_rows_in_pve_only():
    # PvE hides generic non-boss "Combat N" encounters; PvP keeps its skirmishes.
    assert "/^combat" in LOGS_JS
    assert '!== "pvp"' in LOGS_JS


def test_community_difficulty_dropdown_is_sorted():
    assert "localeCompare" in LOGS_JS


def test_community_pvp_relabels_boss_as_skirmish_and_hides_boss_filter():
    # In PvP the Boss column becomes "Skirmish" and the Boss filter dropdown is hidden.
    assert '"Skirmish" : "Boss"' in LOGS_JS
    assert '? "" : field("Boss"' in LOGS_JS


def test_community_filters_are_facet_driven_dropdowns():
    # Filter choices come from the server's own facets; each maps to a param /api/v1/logs honours.
    assert "/api/v1/report-facets" in LOGS_JS
    for sel in ('id="cf-mode"', 'id="cf-boss"', 'id="cf-difficulty"', 'id="cf-encounter_type"',
                'id="cf-region"', 'id="cf-game_patch"', 'id="cf-party_size"'):
        assert sel in LOGS_JS, f"missing filter control {sel}"
    assert "combat_mode" in LOGS_JS   # PvE / PvP toggle


def test_community_party_uses_class_icons_and_boss_portrait():
    # Party members render as class icons (name on hover), and the boss shows its portrait.
    assert "metabot.gg/web/aion2/classes/" in LOGS_JS   # class-icon source
    assert "classIcon" in LOGS_JS and 'title="' in LOGS_JS   # name shown on hover
    assert "bossIcon" in LOGS_JS and "mob-ic" in LOGS_JS      # mob portrait beside the boss name
    assert "A2AssetHealth" in LOGS_JS                          # resolves bundled / cached copies


def test_combat_log_pages_use_the_wide_enlarged_layout():
    # Community logs and the combat-review page opt into full-width, 200%-scaled layout.
    assert 'class="site wide-2x"' in LOGS_HTML
    log_html = (SITE / "log.html").read_text(encoding="utf-8")
    assert 'class="site wide-2x"' in log_html
    css = (SITE / "site.css").read_text(encoding="utf-8")
    assert ".site.wide-2x" in css and "zoom: 1.5" in css


def test_combat_review_roster_is_scoped_to_the_selected_encounter():
    # The log-details roster (and the builds it links) shows only the selected segment's
    # participants, not every player across a multi-encounter log.
    cr = (ROOT / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")
    assert "active.size?active.has(id):!state.run" in cr


def test_logs_page_loads_server_before_logs_script():
    for dep in ("config.js", "server.js", "logs.js", "navigation.js"):
        assert f'src="{dep}"' in LOGS_HTML, f"logs.html must load {dep}"
    assert LOGS_HTML.index('src="server.js"') < LOGS_HTML.index('src="logs.js"')
