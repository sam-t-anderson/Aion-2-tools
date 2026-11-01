"""The other parts of a recording are offered, never swapped in on their own.

When a viewer opens one part of a multi-part recording, the explorer looks the other parts up
(via the server's or the app's archive listing) and offers the complete stitched recording with
one button, "Review all N parts together". From 0.2.263 to 0.2.366 it reconstructed the parts on
its own and replaced the page a few seconds after it opened, starting from the first encounter of
part 1: the fight the link named gave way to another fight, often on another character, and the
page lost its rankings, profile lookups and the other recordings' movement. It stays best-effort:
the live meter view, an already-combined doc, an older server, a gap or a too-large archive all
leave the single part alone. The manual "Review connected parts" control and the reconstruction
are unchanged, and both ways into the stitched recording keep the fight in view (0.2.367)."""
import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "aion2calc" / "app" / "static" / "combat-review.js").read_text(encoding="utf-8")


def _body(name):
    start = SRC.index(f"async function {name}(")
    return SRC[start:SRC.index("\n    }\n", start)]


def test_autocombine_runs_once_at_mount():
    assert "async function autoCombine()" in SRC
    # It is kicked off when the explorer mounts, after the first render.
    assert "render();requestRanks();autoCombine();return api;" in SRC


def test_autocombine_is_guarded_and_best_effort():
    body = _body("autoCombine")
    # Never touch the live meter view or an already-combined document.
    assert "options.live" in body and "doc.meta?.reconstruction" in body
    # Needs the archive callbacks; a lone open current part is skipped.
    assert "options.reconstructArchive" in body and "options.archiveParts" in body
    assert "a.part>1||a.closed" in body
    # Only a real, bounded multi-part range is offered (>=2 parts, under the 32-part cap).
    assert "nums.length<2" in body and "last-first>=32" in body


def test_the_other_parts_are_offered_not_swapped_in():
    body = _body("autoCombine")
    # The lookup ends in an offer: the parts list is kept and the page re-rendered with the button.
    assert "archiveOffer=new Set(nums).size" in body and "archivePage=parts" in body
    # It never reconstructs or swaps the document by itself.
    assert "reconstructArchive(" not in body and "applyCombined(" not in body
    # The offer names the part and the count, and its button shares the manual path's routine.
    assert re.search(r"This is part \$\{esc\(archive\.part\)\} of a recording in \$\{archiveOffer\} parts", SRC)
    assert "data-combine-all" in SRC and "Review all ${archiveOffer} parts together" in SRC
    assert "const combineParts=async()=>" in SRC
    assert "all.onclick=()=>combineParts()" in SRC and "combine.onclick=()=>{archiveFirst=" in SRC


def test_the_swap_keeps_the_fight_in_view():
    # One helper performs the swap; only the (manual or offered) combine routine calls it.
    assert "function applyCombined(next,first,last)" in SRC
    assert SRC.count("applyCombined(") == 2                     # definition + combineParts
    start = SRC.index("function applyCombined(next,first,last)")
    body = SRC[start:SRC.index("\n    }\n", start)]
    # The combined recording names each part's encounters part<N>:<id>; the one in view is found again.
    assert "`part${part}:${current.id}`" in body and "segment:same>=0?same:0" in body
    # The combined doc keeps a way back to the source part and drops the per-part services.
    assert "data-source-back" in SRC and "options={...options,rankings:undefined" in body
