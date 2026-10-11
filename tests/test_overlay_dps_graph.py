"""The live DPS/HPS overlay graph (Settings → Overlay layout) must stay wired end
to end: the setting is a recognised boolean and a visual-preset key, the server
defaults it off and accepts it, the Settings page offers and saves it, and the
overlay draws it from real per-poll readings. Every point on the sparkline is the
summed live party rate at that moment — nothing is invented — so this guards the
wiring, not a fabricated value."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app"
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
BACKUP = (ROOT / "settings_backup.py").read_text(encoding="utf-8")
APPJS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
OVJS = (ROOT / "static" / "overlay.js").read_text(encoding="utf-8")
OVHTML = (ROOT / "static" / "overlay.html").read_text(encoding="utf-8")
OVCSS = (ROOT / "static" / "overlay.css").read_text(encoding="utf-8")

KEY = "overlay_dps_graph"


def test_server_accepts_and_defaults_the_flag_off():
    # Listed as a boolean UI flag and defaulted to False (off by default).
    assert f'"{KEY}"' in SERVER
    assert f'"{KEY}": False' in SERVER


def test_backup_treats_it_as_a_bool_and_visual_key():
    # So the settings backup round-trips it and an overlay look preset can carry it.
    assert f'"{KEY}"' in BACKUP
    # Appears in both _BOOL_KEYS and _VISUAL_KEYS (two occurrences).
    assert BACKUP.count(f'"{KEY}"') >= 2


def test_appjs_offers_saves_and_shares_the_setting():
    assert 'id="ov-dps-graph"' in APPJS                      # the Settings checkbox
    assert '#ov-dps-graph' in APPJS and f'{KEY}:' in APPJS    # its save handler
    assert f'"{KEY}"' in APPJS                                # in OVERLAY_VISUAL_KEYS


def test_overlay_draws_the_graph_from_the_flag():
    assert 'id="ovgraph"' in OVHTML
    assert f'ui.{KEY}===true' in OVJS                         # reads the flag
    assert 'function recordGraph' in OVJS and 'function drawGraph' in OVJS
    assert 'polyline' in OVJS                                 # the sparkline is a polyline
    assert '.ovgraph' in OVCSS and '.ovgline' in OVCSS        # styled
