import json
import os
import zipfile


def test_recording_is_bounded_and_exports_original_segments(tmp_path, monkeypatch):
    from aion2calc.meter.diagnostics import Recorder, export
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    recorder = Recorder(max_bytes=6, max_records=3)
    key = ("adapter", "10.0.0.1", 50349, "10.0.0.2", 60000)
    for i in range(4):
        recorder.record(key, 100 + i * 2, 16, b"ab", 1000 + i)
    counts, rows = recorder.snapshot()
    assert counts == {"records": 3, "payload_bytes": 6, "discarded_records": 1}
    assert rows[0]["sequence"] == 102
    result = export({"source": "a2tools", "diagnostics": {"packets": 4},
                     "snapshot": {"players": [{"name": "private-name"}]}}, recorder)
    with zipfile.ZipFile(result["file"]) as archive:
        assert "private-name" not in archive.read("diagnostics.json").decode()
        data = [json.loads(line) for line in archive.read("tcp-payloads.jsonl").splitlines()]
        assert len(data) == 3 and bytes.fromhex(data[0]["payload_hex"]) == b"ab"


def test_metadata_export_does_not_require_raw_recording(tmp_path, monkeypatch):
    from aion2calc.meter.diagnostics import export
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    result = export({"diagnostics": {"packets": 10}}, None)
    assert result["records"] == 0
    with zipfile.ZipFile(result["file"]) as archive:
        assert archive.read("tcp-payloads.jsonl") == b""


def test_update_cleanup_retains_two_packages_and_helper_logs(tmp_path, monkeypatch):
    from aion2calc.update import cleanup_updates
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    folder = tmp_path / "updates"
    folder.mkdir()
    for i in range(4):
        path = folder / f"aion2calc-setup-0.2.{i}.exe"
        path.touch()
        os.utime(path, (i + 100, i + 100))
    for name in ("apply-update.ps1", "apply-update.log", "aion2calc-setup-new.exe.part", "unrelated.exe"):
        (folder / name).touch()
    current = folder / "aion2calc-setup-0.2.1.exe"
    cleanup_updates(current)
    assert current.exists() and (folder / "aion2calc-setup-0.2.3.exe").exists()
    assert len(list(folder.glob("aion2calc-*.exe"))) == 2
    assert (folder / "apply-update.log").exists() and (folder / "unrelated.exe").exists()


def test_browser_close_matches_only_dedicated_profile(tmp_path):
    from aion2calc.app.windows import _owns_profile
    profile = tmp_path / "window"
    assert _owns_profile(["chrome.exe", f"--user-data-dir={profile}"], profile)
    assert _owns_profile(["chrome.exe", "--user-data-dir", str(profile)], profile)
    assert not _owns_profile(["chrome.exe", f"--user-data-dir={profile}-other"], profile)
    assert not _owns_profile(["chrome.exe"], profile)


def test_overlay_host_accepts_input_without_color_key(monkeypatch):
    import ctypes
    import sys
    from types import ModuleType, SimpleNamespace
    from aion2calc.overlay import _OverlayAPI
    color = SimpleNamespace(Empty="empty", FromArgb=lambda *args: args)
    drawing = ModuleType("System.Drawing")
    drawing.Color = color
    monkeypatch.setitem(sys.modules, "System.Drawing", drawing)
    style = 0x00040000 | 0x20 | 0x08000000
    changed = []
    get_style = lambda *args: style
    set_style = lambda *args: changed.append(args[-1]) or style
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: SimpleNamespace(
        GetWindowLongPtrW=get_style, SetWindowLongPtrW=set_style), raising=False)
    native = SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 7), webview=SimpleNamespace())
    api = _OverlayAPI()
    api._window = SimpleNamespace(native=native)
    monkeypatch.setattr(api, "_on_ui", lambda callback: callback())
    api._configure_windows()
    assert not changed[0] & 0x20 and changed[0] & 0x80
    assert native.TransparencyKey == "empty"
    assert native.webview.DefaultBackgroundColor == (10, 14, 22)
    assert native.Opacity == .72
