"""The overlay's regional event strip (world bosses / Shugo / rift / battlefield) showed
nothing because the region the player picks on the Timers page was saved only to
localStorage — which the separate overlay window does not share. Every other overlay
setting already travels through the server's /api/ui; the region now does too, so the
overlay can read it. (0.2.259)
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")
TIMERS = (ROOT / "aion2calc" / "app" / "static" / "timers.js").read_text(encoding="utf-8")
OVERLAY = (ROOT / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")


def test_server_defaults_and_accepts_the_region_keys():
    assert '"event_region": ""' in SERVER and '"event_group": ""' in SERVER   # defaults
    # Persisted through the /api/ui POST (validated as short strings, then stored).
    assert '("event_region", "event_group")' in SERVER
    assert '"event_region", "event_group",' in SERVER   # included in the stored-key update set


def test_timers_page_mirrors_the_region_to_the_server():
    # save() still writes localStorage, and now also POSTs the region to /api/ui.
    assert "a2-event-region" in TIMERS
    assert "/api/ui" in TIMERS and "event_region" in TIMERS and "event_group" in TIMERS


def test_overlay_reads_the_region_from_the_server_with_a_localstorage_fallback():
    # The overlay takes the region from the /api/ui settings object first, then falls
    # back to its own localStorage (same-window / legacy).
    assert "ui.event_region" in OVERLAY and "ui.event_group" in OVERLAY
    assert "eventRegion||saved.region" in OVERLAY
    assert "eventGroup||saved.group" in OVERLAY
