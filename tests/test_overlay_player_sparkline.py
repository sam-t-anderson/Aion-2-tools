"""With the DPS graph enabled, a player's panel on the overlay (0.2.364; until 0.2.368
the expanded row) also shows that player's DPS trend as a sparkline, built from real
per-poll readings kept per player. It reuses the same history recorder as the party
graph, is gated by the same overlay_dps_graph toggle, and clears when a new fight starts."""
import pathlib

STATIC = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
JS = (STATIC / "overlay.js").read_text(encoding="utf-8")
CSS = (STATIC / "overlay.css").read_text(encoding="utf-8")


def test_per_player_history_is_recorded_and_reset_with_the_fight():
    assert "playerHist" in JS
    # Cleared when the graph is off and when a new fight starts.
    assert "playerHist.clear()" in JS


def test_sparkline_is_gated_by_the_graph_toggle_and_drawn_in_the_open_panel():
    assert "function sparkLine" in JS
    assert 'const spark=showGraph?sparkLine(playerHist.get(key),barColor(p.class)):""' in JS
    assert "      +spark\n      +`<div class=\"ovdtiles\">" in JS            # above the panel's tiles


def test_sparkline_is_styled():
    assert ".ovpspark" in CSS


def test_sparkline_is_tinted_to_the_players_class_colour():
    # sparkLine takes a colour and the panel passes the player's class colour.
    assert "function sparkLine(series, color)" in JS
    assert "sparkLine(playerHist.get(key),barColor(p.class))" in JS   # the overlay tint (a chosen class colour wins)
    assert ".ovparea" in CSS  # faint class-tinted fill under the line
