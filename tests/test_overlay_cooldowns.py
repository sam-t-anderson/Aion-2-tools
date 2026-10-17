"""The overlay's skill-cooldown strip and break-gauge bar (0.2.306): both off by default, wired
through the settings, fed from the engine's live state by the runner, and drawn by the overlay.
The cooldown is the one the game sent with each cast, so nothing here is estimated."""
import pathlib
import types

from aion2calc.app import server
from aion2calc.app.meter_runner import Runner
from aion2calc.app.settings_backup import _clean

ROOT = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app"
APPJS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
OVJS = (ROOT / "static" / "overlay.js").read_text(encoding="utf-8")
OVHTML = (ROOT / "static" / "overlay.html").read_text(encoding="utf-8")
OVCSS = (ROOT / "static" / "overlay.css").read_text(encoding="utf-8")


def test_both_are_off_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    ui = server.ui_settings()
    assert ui["overlay_show_cooldowns"] is False and ui["overlay_show_break_gauge"] is False
    assert ui["overlay_cooldowns_min_s"] == 3 and ui["overlay_cooldowns_max"] == 8
    assert ui["overlay_cooldowns_position"] == "bottom"


def test_the_backup_round_trips_and_checks_them():
    clean = _clean({"overlay_show_cooldowns": True, "overlay_show_break_gauge": True,
                    "overlay_cooldowns_min_s": 10, "overlay_cooldowns_max": 4,
                    "overlay_cooldowns_position": "top"})
    assert clean == {"overlay_show_cooldowns": True, "overlay_show_break_gauge": True,
                     "overlay_cooldowns_min_s": 10, "overlay_cooldowns_max": 4,
                     "overlay_cooldowns_position": "top"}
    for bad in ({"overlay_cooldowns_max": 40}, {"overlay_cooldowns_min_s": 0},
                {"overlay_cooldowns_position": "left"}, {"overlay_show_cooldowns": "yes"}):
        try:
            _clean(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_the_settings_page_and_the_overlay_are_wired():
    for control in ('id="ov-cooldowns"', 'id="ov-cd-min"', 'id="ov-cd-max"', 'id="ov-cd-pos"', 'id="ov-break-gauge"'):
        assert control in APPJS
    for key in ("overlay_show_cooldowns:", "overlay_cooldowns_min_s:", "overlay_cooldowns_max:",
                "overlay_cooldowns_position:", "overlay_show_break_gauge:"):
        assert key in APPJS
    assert 'id="ovcooldowns"' in OVHTML and 'id="ovgauge"' in OVHTML
    assert "ui.overlay_show_cooldowns===true" in OVJS and "ui.overlay_show_break_gauge===true" in OVJS
    assert "function renderCooldowns" in OVJS and "snap.chain_windows" in OVJS and "target.break_gauge" in OVJS
    assert ".ovcooldowns" in OVCSS and ".ovcd-ready" in OVCSS and ".ovgauge" in OVCSS


def _runner(now_ms, **state):
    engine = types.SimpleNamespace(cooldowns={}, chain_windows={}, break_gauges={}, **state)
    return types.SimpleNamespace(packet_engine=engine, _COOLDOWN_READY_MS=Runner._COOLDOWN_READY_MS,
                                 _CHAIN_WINDOW_MS=Runner._CHAIN_WINDOW_MS), now_ms


def test_the_runner_lists_cooldowns_soonest_first(monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr("aion2calc.app.meter_runner.time.time", lambda: now / 1000)
    fake, _ = _runner(now)
    fake.packet_engine.cooldowns = {
        11020000: {"skill": 11020000, "cast_ms": now - 2000, "cooldown_ms": 12000},    # 10 s left
        11030000: {"skill": 11030000, "cast_ms": now - 1000, "cooldown_ms": 4000},     # 3 s left
        11040000: {"skill": 11040000, "cast_ms": now - 500, "cooldown_ms": 2000},      # under the 3 s floor
        11050000: {"skill": 11050000, "cast_ms": now - 7000, "cooldown_ms": 5000},     # ready 2 s ago: lit
        11060000: {"skill": 11060000, "cast_ms": now - 60000, "cooldown_ms": 5000},    # ready long ago
    }
    fake.packet_engine.chain_windows = {11070000: now - 1000, 11080000: now - 30000}
    snap = {}
    Runner._overlay_actions(fake, snap, {"overlay_show_cooldowns": True, "overlay_cooldowns_min_s": 3,
                                         "overlay_cooldowns_max": 8})
    assert [row["family"] for row in snap["cooldowns"]] == [11050000, 11030000, 11020000]
    assert [row["remaining_ms"] for row in snap["cooldowns"]] == [-2000, 3000, 10000]
    assert snap["cooldowns"][2]["cooldown_ms"] == 12000 and snap["cooldowns"][2]["name"]
    assert [chain["family"] for chain in snap["chain_windows"]] == [11070000]   # the stale window is dropped
    snap = {}
    Runner._overlay_actions(fake, snap, {"overlay_show_cooldowns": True, "overlay_cooldowns_min_s": 3,
                                         "overlay_cooldowns_max": 1})
    assert [row["family"] for row in snap["cooldowns"]] == [11050000]


def test_nothing_is_attached_while_the_settings_are_off(monkeypatch):
    fake, now = _runner(1_000_000.0)
    fake.packet_engine.cooldowns = {11020000: {"skill": 11020000, "cast_ms": now, "cooldown_ms": 12000}}
    fake.packet_engine.break_gauges = {9001: (100, 40, now)}
    snap = {"current_target": {"entity_id": 9001}}
    Runner._overlay_actions(fake, snap, {})
    assert "cooldowns" not in snap and "break_gauge" not in snap["current_target"]


def test_the_runner_attaches_the_targets_break_gauge():
    fake, now = _runner(1_000_000.0)
    fake.packet_engine.break_gauges = {9001: (120, 30, now), 9002: (0, 0, now)}
    snap = {"current_target": {"entity_id": 9001}}
    Runner._overlay_actions(fake, snap, {"overlay_show_break_gauge": True})
    assert snap["current_target"]["break_gauge"] == {"max": 120, "current": 30, "pct": 25.0}
    for entity in (9002, 9003, None):       # no maximum, no reading, no entity
        snap = {"current_target": {"entity_id": entity}}
        Runner._overlay_actions(fake, snap, {"overlay_show_break_gauge": True})
        assert "break_gauge" not in snap["current_target"]


def test_the_current_target_carries_its_entity_id():
    from aion2calc.meter.a2parser.engine import MeterEngine
    from aion2calc.meter.a2parser.models import DamageEvent
    from aion2calc.meter.session import CombatSession
    session, engine = CombatSession(), MeterEngine()
    session.pvp = False
    engine.map_id = engine.dungeon_id = 600002
    engine.last_zone_reset_ms = None
    engine.local_player_id = 5001
    engine.names = {5001: "Me"}
    engine.roster = {"Me": {}}
    session.observe(engine, [DamageEvent(actor_id=5001, target_id=9001, skill_code=15210000, damage=500,
                                         timestamp_ms=1000)], timestamp_ms=1000)
    target = session.snapshot(scope="auto", segment_id=None)["current_target"]
    assert target["entity_id"] == 9001
