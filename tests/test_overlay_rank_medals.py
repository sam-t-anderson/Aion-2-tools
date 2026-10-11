"""The overlay's rank numbers give the top three places podium colours
(gold/silver/bronze), like a mature meter's leaderboard. Pure presentation of
the existing ranking — it adds a per-place class only to ranks 1-3 and styles
those classes; nothing below the podium changes."""
import pathlib

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
CSS = (STATIC / "overlay.css").read_text(encoding="utf-8")


def test_js_tags_only_the_top_three_ranks():
    # The rank span gains ovrank-1/2/3 only for the first three rows (i<3).
    assert "i<3?' ovrank-'+(i+1):''" in JS


def test_css_styles_the_three_podium_places():
    for place in ("1", "2", "3"):
        assert f".ovrank-{place}" in CSS
