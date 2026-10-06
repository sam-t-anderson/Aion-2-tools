"""Capture, overlay, updater and shared preset regressions."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))


def test_flow_detection_dynamic_port_buffers_and_rejects_tls():
    from aion2calc.meter.a2parser.capture import CombatFlowDetector
    detector = CombatFlowDetector()
    flow = ("adapter", "10.0.0.2", 43210, "10.0.0.3", 55000)
    assert not detector.feed(flow, b"\x16\x03\x01\x0e\x00\x36", 0, False, 0)
    for i in range(11):
        assert not detector.feed(flow, b"\x0e\x00\x36", i * 3, False, i * .25)
    packets = detector.feed(flow, b"\x0e\x00\x36", 33, False, 2.75)
    assert len(packets) == 12 and detector.selected == flow
    assert not detector.feed(("other", *flow[1:]), b"data", 36, False, 3)
    assert detector.feed(flow, b"data", 36, False, 3)


def test_reassembly_overlap_and_sequence_wrap():
    from aion2calc.meter.a2parser.capture import TCPReassembler
    stream = TCPReassembler()
    assert stream.feed(0xfffffffe, b"ab") == b"ab"
    assert stream.feed(2, b"efgh") == b""
    assert stream.feed(0, b"cdef") == b"cdefgh"
    assert stream.feed(0, b"cdef") == b""


def test_stop_interrupts_replay_before_future_events(tmp_path):
    import time
    from aion2calc.app.meter_runner import Runner
    path = tmp_path / "slow.jsonl"
    path.write_text('\n'.join(json.dumps({"t": t, "source": "a", "target": "boss", "damage": 100})
                              for t in (0, 600)), encoding="utf-8")
    runner = Runner()
    runner.start("replay", path=str(path))
    time.sleep(.05)
    start = time.monotonic()
    runner.stop()
    assert time.monotonic() - start < 1
    assert not runner.running and not runner.thread.is_alive()


def test_imported_decoder_is_saved_without_execution(tmp_path):
    from aion2calc.meter.decoder import import_decoder, load_decoder
    marker = tmp_path / "executed"
    source = f"from pathlib import Path\nPath({str(marker)!r}).touch()\nclass Decoder:\n def feed(self, data): return []\n"
    imported = import_decoder("decoder.py", source)
    assert not marker.exists()
    assert load_decoder(imported["path"]).feed(b"x") == []
    assert marker.exists()
    with pytest.raises(ValueError):
        import_decoder("decoder.txt", source)


def test_overlay_follows_only_game_executable_and_preserves_drag():
    from aion2calc.overlay import _is_game_process, _follow_position
    assert _is_game_process(r"C:\Games\AION2\AION2.exe")
    assert not _is_game_process(r"C:\AION2\aion2calc.exe")
    assert not _is_game_process(r"C:\AION2\chrome.exe")
    assert _follow_position((100, 100, 1000, 800), (200, 300, 1000, 800),
                            (180, 220, 340, 120)) == (280, 420)


def test_overlay_launch_is_single_instance(monkeypatch):
    from aion2calc.app import overlay_launch
    calls = []
    monkeypatch.setattr(overlay_launch, "available", lambda: True)
    monkeypatch.setattr(overlay_launch, "_PROCESS", None)
    monkeypatch.setattr(overlay_launch.subprocess, "Popen", lambda *a, **k:
                        calls.append(a) or SimpleNamespace(poll=lambda: None))
    assert not overlay_launch.launch("http://localhost/overlay")["already_open"]
    assert overlay_launch.launch("http://localhost/overlay")["already_open"]
    assert len(calls) == 1


def test_update_fetch_validates_cached_digest(monkeypatch):
    from aion2calc import update
    data = b"installer"
    asset = {"name": "s.exe", "browser_download_url": "https://example.test/s.exe",
             "size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
    calls = []
    def download(url, dest):
        calls.append(url)
        dest.write_bytes(data)
    monkeypatch.setattr(update, "download", download)
    first = update.fetch({"asset": asset})
    assert update.fetch({"asset": asset}) == first and len(calls) == 1
    first.write_bytes(b"corrupted")
    assert update.fetch({"asset": asset}).read_bytes() == data and len(calls) == 2


def test_installer_waits_for_helper_acknowledgement(monkeypatch, tmp_path):
    from aion2calc import update
    scripts = []
    def spawn(args, **kwargs):
        script = Path(args[-1]); scripts.append(script.read_text(encoding="utf-8"))
        script.with_suffix(".ready").touch()
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(update.subprocess, "Popen", spawn)
    assert update.apply_installer(tmp_path / "setup.exe", silent=False)
    assert "Wait-Process" in scripts[0] and "-ArgumentList @('/NORESTART')" in scripts[0]
    assert "/VERYSILENT" not in scripts[0]
    monkeypatch.setattr(update.subprocess, "Popen", lambda *a, **k: SimpleNamespace(poll=lambda: 1))
    assert not update.apply_installer(tmp_path / "setup.exe", silent=False)


def test_charged_skills_are_never_macro_taps():
    from aion2calc.opt.macro import MacroPolicy
    from aion2calc.sim.engine import Action
    charged = Action("charged", "Charged", 1, 1, requires_charge=True)
    tap = Action("tap", "Tap", 2, 1)
    sim = SimpleNamespace(actions={"charged": charged, "tap": tap}, usable=lambda a: True)
    assert MacroPolicy([], ["charged", "tap"])(sim) is tap
    assert MacroPolicy(["charged"], ["tap"])(sim) is charged


def test_sp_fill_includes_neutral_utility_points(monkeypatch):
    from aion2calc.kit.base import Build, ClassData
    from aion2calc.opt.pipeline import Optimizer
    from aion2calc.scenarios import SCENARIOS
    optimizer = Optimizer("sorcerer", SCENARIOS["boss"]("sorcerer_l45_global_median"),
                          sp_budget=7, verbose=False)
    monkeypatch.setattr(optimizer, "evaluate", lambda *a: 100)
    build = optimizer.spend_remaining_sp(Build(cls="sorcerer"), [])
    assert build.sp_spent() == 7
    assert all(lv <= ClassData("sorcerer").skills[sid].get("buyMax", 10) for sid, lv in build.sp.items())


def test_preset_strips_private_data_and_recomputes_score():
    from aion2calc.paths import resource_root
    from aion2calc.presets import candidate, evaluate
    summary = json.loads((resource_root() / "results/sorcerer_l45/build.json").read_text(encoding="utf-8"))
    summary["loadout"] = "private_character_name"
    summary["dps"] = {"boss": 1e100}
    document = candidate(summary)
    assert "private_character_name" not in json.dumps(document)
    result = evaluate(document)
    assert 0 < result["dps"]["boss"] < 1e100
    from aion2calc.app.views import build_view
    view = build_view(result)
    assert view["hotbar"]["slots"]
    assert not any(s["charged"] for s in view["rotation"]["steps"])


def test_preset_sync_persists_usable_report_and_survives_offline(monkeypatch):
    from io import BytesIO
    from aion2calc.paths import resource_root, read_json
    from aion2calc.combat import share
    from aion2calc.presets import evaluate, candidate
    summary = json.loads((resource_root() / "results/sorcerer_l45/build.json").read_text(encoding="utf-8"))
    canonical = evaluate(candidate(summary))
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://community.test"})
    def get(url, **kwargs):
        value = {"build": canonical, "updated_at": 1} if url.endswith("/sorcerer") else {
            "presets": [{"class_name": "sorcerer", "updated_at": 1}, {"class_name": "../../bad"}]}
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr(share.urllib.request, "urlopen", get)
    assert share.sync_presets() == ["sorcerer"]
    assert share.sync_presets() == []
    monkeypatch.setattr(share.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert share.sync_presets() == []
    assert read_json("community_presets", "sorcerer.json")["build"]["loadout"] == "sorcerer_l45_global_median"
