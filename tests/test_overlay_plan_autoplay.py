"""The overlay's Plan tab auto-plays a saved raid plan bound to the current fight's
boss, synced to the live pull: it resolves a plan by the target's NPC code, drives the
timeline from the encounter's elapsed seconds, and falls back to the looping preview
when auto-play is off or there's no match. Gated by the overlay_plan_autoplay setting."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / "aion2calc" / "app" / "static" / "overlay.js").read_text(encoding="utf-8")
APP = (ROOT / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")
SERVER = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")


def test_current_target_exposes_mob_code():
    sess = (ROOT / "aion2calc" / "meter" / "session.py").read_text(encoding="utf-8")
    assert '"mob_code": int(mob_code)' in sess          # current_target carries the match key


def test_overlay_resolves_a_plan_by_npc_and_syncs_to_elapsed():
    assert "function planForNpc" in JS
    assert "encounter?.npc_id" in JS                    # matches on the plan's bound NPC id
    # Live view drives the plan time from the encounter's elapsed seconds, clamped.
    assert "function planView" in JS
    assert "Number(snap.duration)" in JS
    assert "current_target" in JS and "mob_code" in JS


def test_autoplay_is_a_setting_on_by_default():
    assert "planAutoplay=ui.overlay_plan_autoplay!==false" in JS
    assert '"overlay_plan_autoplay": True' in SERVER
    assert "overlay_plan_autoplay" in SERVER            # in the bool allowlist too
    assert 'id="ov-plan-autoplay"' in APP


def test_plan_tab_polls_for_live_data_when_autoplaying():
    assert 'tab === "plan" && planAutoplay' in JS
