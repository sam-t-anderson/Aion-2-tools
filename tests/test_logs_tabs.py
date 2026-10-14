"""The public Logs page splits into five views, each backed by a live server endpoint.

Beyond the existing Community browse/upload/review workflow (kept intact), the page adds four
aggregate-leaderboard tabs — Completed-run speed, Boss progression, Class performance and Highest
observed build points — each rendered from the server's own public endpoint through ``A2.api`` and
read defensively so a missing field or an unreachable/empty endpoint never breaks the page. This
guards the tab wiring, the endpoint references, and that the upload/review workflow is preserved."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
LOGS_HTML = (SITE / "logs.html").read_text(encoding="utf-8")
LOGS_JS = (SITE / "logs.js").read_text(encoding="utf-8")


def test_logs_page_has_the_five_tabs():
    for tab in ("community", "speed", "progression", "classes", "points"):
        assert f'data-tab="{tab}"' in LOGS_HTML, f"missing tab button {tab}"
        assert f'data-logs-panel="{tab}"' in LOGS_HTML, f"missing panel {tab}"


def test_each_analytical_tab_reads_its_server_endpoint():
    # The same public endpoints the server already serves; via the shared A2 client, not raw fetch.
    assert '"/api/v1/run-leaderboard' in LOGS_JS          # Completed-run speed
    assert '"/api/v1/encounter-progression"' in LOGS_JS   # Boss progression
    assert '"/api/v1/stats"' in LOGS_JS                    # Class performance
    assert '"/api/v1/progression"' in LOGS_JS              # Highest observed build points
    assert "A2.api(" in LOGS_JS


def test_community_upload_and_review_workflow_is_preserved():
    # The new tabs must not drop the existing upload/review wiring.
    for anchor in ('id="combat-log-tabs"', 'id="archive-upload"', 'id="archive-review"', 'id="community"'):
        assert anchor in LOGS_HTML, f"lost workflow anchor {anchor}"
    assert "A2ArchiveUpload.mount" in LOGS_JS


def test_community_tab_is_one_row_per_encounter():
    # The Community combat logs view is a per-encounter table (flattened from /api/v1/logs
    # contexts[]), filterable by boss, not the old per-log browse widget.
    assert "renderCommunity" in LOGS_JS
    assert "/api/v1/logs?page=" in LOGS_JS
    assert "contexts" in LOGS_JS
    # Columns the user asked for: boss, difficulty, party, time, date, product version.
    for col in (">Boss<", ">Difficulty<", ">Party<", ">Time<", ">Date<", ">Product<"):
        assert col in LOGS_JS, f"missing community column {col}"


def test_logs_page_loads_server_before_logs_script():
    for dep in ("config.js", "server.js", "logs.js", "navigation.js"):
        assert f'src="{dep}"' in LOGS_HTML, f"logs.html must load {dep}"
    assert LOGS_HTML.index('src="server.js"') < LOGS_HTML.index('src="logs.js"')
