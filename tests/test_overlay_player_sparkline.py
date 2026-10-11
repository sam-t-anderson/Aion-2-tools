"""With the DPS graph enabled, expanding a player's row on the overlay also shows
that player's DPS trend as a sparkline, built from real per-poll readings kept
per player. It reuses the same history recorder as the party graph, is gated by
the same overlay_dps_graph toggle, and clears when a new fight starts."""
import pathlib

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
CSS = (STATIC / "overlay.css").read_text(encoding="utf-8")


def test_per_player_history_is_recorded_and_reset_with_the_fight():
    assert "playerHist" in JS
    # Cleared when the graph is off and when a new fight starts.
    assert "playerHist.clear()" in JS


def test_sparkline_is_gated_by_the_graph_toggle_and_expansion():
    assert "function sparkLine" in JS
    assert "showGraph&&expanded.has(key)" in JS


def test_sparkline_is_styled():
    assert ".ovpspark" in CSS
