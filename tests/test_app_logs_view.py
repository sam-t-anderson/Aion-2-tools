"""The desktop app's Combat Logs page mirrors the public GitHub Pages logs page.

The app page gains the website's outer tabs — Community combat logs, Completed-run speed, Boss
progression, Highest observed build points — rendered by a new ``A2LogsView`` module that ports
the site's per-encounter facet table and aggregate leaderboards, reaching the server through the
app's ``/api/community`` proxy and opening logs through the SPA router. The app-only extras the
website omits (boss defeats, class performance, personal records, consistency) move to a dedicated
"Personal records" tab, rendered by A2Community restricted to just those sections. This guards the
new module, the page wiring, the preserved app extras, and the section allow-list in community.js.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
VIEW_JS = (STATIC / "logs-view.js").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
COMMUNITY_JS = (STATIC / "community.js").read_text(encoding="utf-8")
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")


def test_logs_view_module_is_exported():
    assert "window.A2LogsView" in VIEW_JS
    assert "function mount(root" in VIEW_JS


def test_logs_view_ports_the_four_website_renderers():
    for fn in ("renderCommunity", "renderSpeed", "renderProgression", "renderPoints"):
        assert fn in VIEW_JS, f"missing ported renderer {fn}"


def test_logs_view_reads_each_server_endpoint_through_the_app_proxy():
    # Same public endpoints as the website, but via the injected app proxy (communityAPI), not A2.api.
    assert '"/api/v1/run-leaderboard' in VIEW_JS          # Completed-run speed
    assert '"/api/v1/encounter-progression"' in VIEW_JS   # Boss progression
    assert '"/api/v1/progression"' in VIEW_JS              # Highest observed build points
    assert '"/api/v1/logs?"' in VIEW_JS                    # Community combat logs
    assert '"/api/v1/report-facets"' in VIEW_JS            # facet-driven filters
    # The module must not reach the global site client; it takes its api as an injected dependency.
    assert "A2.api(" not in VIEW_JS
    assert "const api = options_.api" in VIEW_JS


def test_logs_view_opens_logs_through_the_injected_router_not_static_links():
    # No static log.html links; opening a log routes through the app via the injected open().
    assert "log.html?id=" not in VIEW_JS
    assert "data-logs-open" in VIEW_JS
    assert "open(b.dataset.logsOpen" in VIEW_JS


def test_logs_view_community_tab_is_one_row_per_encounter_with_icons():
    # The per-encounter facet table ported from the site: contexts[] flattening, 50/page, class
    # icons for the party, the boss portrait, and the Anonymous uploader fallback.
    assert "COMM_PER_PAGE = 50" in VIEW_JS
    assert "contexts" in VIEW_JS
    assert "metabot.gg/web/aion2/classes/" in VIEW_JS
    assert "classIcon" in VIEW_JS and "bossIcon" in VIEW_JS and "mob-ic" in VIEW_JS
    assert "Anonymous" in VIEW_JS
    for col in (">Difficulty<", ">Party<", ">Time<", ">Uploaded by<", ">Date<", ">Product<"):
        assert col in VIEW_JS, f"missing community column {col}"
    # PvE hides generic "Combat N"; PvP keeps skirmishes and relabels the Boss column.
    assert "/^combat" in VIEW_JS
    assert '"Skirmish" : "Boss"' in VIEW_JS


def test_logs_view_progression_tab_has_portraits_filters_and_alpha_sort():
    assert "progression-body" in VIEW_JS
    for sel in ('id="pf-boss"', 'id="pf-difficulty"', 'id="pf-region"', 'id="pf-game_patch"'):
        assert sel in VIEW_JS, f"missing progression filter {sel}"
    assert "<th>Boss</th><th>Difficulty</th><th>Region</th><th>Product</th>" in VIEW_JS
    assert "g.icon" in VIEW_JS and "boss-cell" in VIEW_JS
    assert 'String(a.boss || "").localeCompare(String(b.boss || "")' in VIEW_JS


def test_app_combat_page_has_the_website_outer_tabs_and_panels():
    for tab in ("community", "speed", "progression", "points"):
        assert f'data-tab="{tab}"' in APP_JS, f"missing outer tab button {tab}"
        assert f'data-logs-panel="{tab}"' in APP_JS, f"missing outer panel {tab}"
    for anchor in ('id="logs-tabs"', 'id="logs-view"', 'id="speed-body"', 'id="progression-body"', 'id="points-body"'):
        assert anchor in APP_JS, f"missing page anchor {anchor}"


def test_app_mounts_logs_view_and_keeps_inner_community_workflow():
    # The new module drives the page; the inner Community/My Uploads/Saved tabs and their app
    # extras are preserved (not replaced by the monolith).
    assert "A2LogsView.mount($('#logs-view')" in APP_JS
    for anchor in ('id="combat-log-tabs"', 'id="owned-logs"', 'id="community"', 'id="sessions"',
                   'id="hist"', 'id="ref"'):
        assert anchor in APP_JS, f"lost app workflow anchor {anchor}"
    assert "A2LogTabs.mount($('#combat-log-tabs')" in APP_JS


def test_app_extras_tab_is_a_sectioned_community_mount():
    # The app-only extras (boss defeats, class performance, personal records, consistency) render on
    # a dedicated tab, via A2Community restricted to just those sections so nothing duplicates the
    # website-style tabs above.
    assert 'data-tab="extras"' in APP_JS and 'data-logs-panel="extras"' in APP_JS
    assert 'id="records-extra"' in APP_JS
    assert "A2Community.mount($('#records-extra')" in APP_JS
    assert "sections:['bosses','performance','records']" in APP_JS


def test_community_module_supports_a_section_allow_list():
    # A2Community.mount honours an optional sections allow-list and guards every block/fetch by it,
    # so a subset render (the extras tab) never touches the omitted sections' DOM or endpoints.
    assert "options.sections" in COMMUNITY_JS
    assert "const has=s=>" in COMMUNITY_JS
    for flag in ("has('logs')", "has('bosses')", "has('performance')", "has('records')",
                 "has('speed')", "has('progression')", "has('points')"):
        assert flag in COMMUNITY_JS, f"missing section guard {flag}"
    # Default (no sections) still renders everything — the full page keeps working.
    assert "Array.isArray(options.sections)?options.sections:null" in COMMUNITY_JS


def test_index_loads_logs_view_after_community():
    assert 'src="/static/logs-view.js"' in INDEX_HTML
    assert INDEX_HTML.index('src="/static/community.js"') < INDEX_HTML.index('src="/static/logs-view.js"')


def test_pve_boss_filter_excludes_generic_combat():
    # "Combat N" is dropped from PvE rows; it must also be kept out of the Boss filter dropdown.
    assert "realBoss" in VIEW_JS
    assert VIEW_JS.count(".filter(realBoss)") >= 2   # community + progression boss dropdowns


def test_view_opens_the_specific_encounter_segment():
    # The per-encounter row carries its segment and the view button opens that encounter.
    assert "segment: c.segment" in VIEW_JS
    assert "data-logs-seg" in VIEW_JS
    assert 'openBtn(r.id, mode, "view", r.segment)' in VIEW_JS
    # The app's shared-log open handler threads the segment into the route.
    assert "'&segment='+segment" in APP_JS
