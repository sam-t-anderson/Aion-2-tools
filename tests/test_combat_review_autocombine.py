"""Auto-surface the complete recording in the combat viewer.

When a viewer opens one part of a multi-part recording, the explorer stitches the parts
back into the complete recording (via the server's archive reconstruction) and shows that
as the main view, instead of leaving the viewer on a single fragment. It stays best-effort:
the live meter view, an already-combined doc, an older server, a gap or a too-large archive
all fall back to the single part. The manual "Review connected parts" control and the server
reconstruction are unchanged; this only makes the combined view the default for a stored
multi-part recording."""
import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")


def test_autocombine_runs_once_at_mount():
    assert "async function autoCombine()" in SRC
    # It is kicked off when the explorer mounts, after the first render.
    assert "render();requestRanks();autoCombine();return api;" in SRC


def test_autocombine_is_guarded_and_best_effort():
    # Never hijack the live meter view or an already-combined document.
    assert "options.live" in SRC and "doc.meta?.reconstruction" in SRC
    # Needs the server reconstruction callbacks; a lone open current part is skipped.
    assert "options.reconstructArchive" in SRC and "options.archiveParts" in SRC
    assert "a.part>1||a.closed" in SRC
    # Only stitch a real, bounded multi-part range (>=2 parts, under the 32-part cap).
    assert "nums.length<2" in SRC and "last-first>=32" in SRC


def test_combined_swap_is_shared_by_auto_and_manual_paths():
    # One helper performs the swap; both the auto path and the manual button call it.
    assert "function applyCombined(next,first,last)" in SRC
    assert SRC.count("applyCombined(") >= 3          # definition + manual button + autoCombine
    # The combined doc keeps a way back to the source part and its per-part rankings.
    assert "data-source-back" in SRC and "options={...options,rankings:undefined" in SRC
