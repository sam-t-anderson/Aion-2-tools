"""The log review and the website Logs tab explain stitched runs and shared fights.

Log server 0.2.96 rebuilds a dungeon run that rolled over between archive parts and recognises
the same fight uploaded by several party members. Its ``rankings`` response carries ``stitched``
(parts/logs, plus ``merged`` when the rollover cut a boss attempt), ``continued_in`` on the cut
half and ``shared_uploads``; ``/api/v1/logs`` rows carry ``shared_uploads`` counts. The shared
combat review renders those as plain notes with buttons that open the other upload / part, and
the Logs tab shows "+N more" next to the uploader.
"""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REVIEW_JS = ROOT / "aion2calc" / "app" / "static" / "combat-review.js"
LOGS_JS = ROOT / "site" / "logs.js"


def test_scripts_parse():
    for path in (REVIEW_JS, LOGS_JS):
        subprocess.run(["node", "--check", str(path)], check=True)


def test_review_explains_stitched_runs_cut_fights_and_shared_uploads():
    script = REVIEW_JS.read_text(encoding="utf-8")
    assert "ranks?.stitched" in script and "stitched across recording parts" in script
    assert "ranks?.continued_in" in script and "continues in the next part" in script
    assert "ranks?.shared_uploads" in script and "Also recorded by" in script
    # Every other upload / part is openable through the host page's navigation (same hook the
    # recording-parts list uses), never a hard-coded URL.
    assert "data-open-shared" in script and "options.openArchivePart" in script
    # The run-timing table marks a stitched run.
    assert "r.stitched?.parts" in script


def test_logs_tab_shows_other_uploads_of_the_same_fight():
    script = LOGS_JS.read_text(encoding="utf-8")
    assert "lg.shared_uploads" in script and "+${n0(r.shared)} more" in script
