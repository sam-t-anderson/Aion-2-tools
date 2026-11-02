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
    # The host is the card's colour, and the card fills the native window (no margin, square
    # corners, no drop shadow), so no dark frame shows around the meter.
    assert native.webview.DefaultBackgroundColor == native.BackColor == (27, 32, 42)
    assert native.Opacity == .72
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static" / "overlay.css").read_text(encoding="utf-8")
    assert "html.native-windows #ov { padding: 0; }" in css
    assert "html.native-windows .ovcard { border-radius: 0;" in css and "html.native-windows #ovbg { border-radius: 0; }" in css


def test_overlay_host_clips_its_window_to_the_shapes_the_page_reports(monkeypatch):
    """The transparent background modes (0.2.368): the page reports the rectangles it draws and the host clips the
    opaque window to their union, so the game shows through between the rows; null draws the whole window again.
    A shape reported before the window exists is applied once it does."""
    import sys
    from types import ModuleType, SimpleNamespace
    from aion2calc.overlay import _OverlayAPI

    class Rectangle:
        def __init__(self, x, y, w, h):
            self.box = (x, y, w, h)

    class Region:
        def __init__(self, rect):
            self.rects = [rect.box]

        def Union(self, rect):
            self.rects.append(rect.box)
    drawing = ModuleType("System.Drawing")
    drawing.Rectangle, drawing.Region = Rectangle, Region
    monkeypatch.setitem(sys.modules, "System.Drawing", drawing)
    api = _OverlayAPI()
    native = SimpleNamespace(Region="untouched")
    api._window = SimpleNamespace(native=native)
    applied = []
    monkeypatch.setattr(api, "_on_ui", lambda callback: applied.append(callback) or callback())
    api.set_window_shape([[0, 0, 340.4, 60], [0, 70, 340, 94.2], ["x", 1, 2, 3], [5, 5, 4, 4]])    # bad rows dropped
    assert api._shape == ((0, 0, 341, 60), (0, 70, 340, 95)) and native.Region == "untouched"      # not ready yet
    api._windows_ready = True
    api._apply_shape()
    assert native.Region.rects == [(0, 0, 341, 60), (0, 70, 340, 25)]
    api.set_window_shape([[10, 10, 50, 20]])
    assert native.Region.rects == [(10, 10, 40, 10)] and len(applied) == 1
    api.set_window_shape(None)
    assert api._shape is None and native.Region is None
    api.set_window_shape([])                                           # nothing drawn: the whole window
    assert api._shape is None and native.Region is None


def test_overlay_host_rounds_the_corners_the_page_reports_and_keeps_square_ones_if_it_cannot(monkeypatch):
    """The see-through modes' compact layout (0.2.370) sends a fifth number with a piece's outline: its corner radius
    in device px. The host draws that piece as a rounded rectangle (its four corner arcs); a radius larger than half
    the piece is held to half; a failure building the rounded shape falls back to square corners, never to no shape."""
    import sys
    from types import ModuleType, SimpleNamespace
    from aion2calc.overlay import _OverlayAPI

    class Rectangle:
        def __init__(self, x, y, w, h):
            self.box = (x, y, w, h)

    class Region:
        def __init__(self, part):
            self.parts = [part]

        def Union(self, part):
            self.parts.append(part)

    class GraphicsPath:
        def __init__(self):
            self.arcs, self.closed = [], False

        def AddArc(self, rect, start, sweep):
            self.arcs.append((rect.box, start, sweep))

        def CloseFigure(self):
            self.closed = True
    drawing, drawing2d = ModuleType("System.Drawing"), ModuleType("System.Drawing.Drawing2D")
    drawing.Rectangle, drawing.Region, drawing2d.GraphicsPath = Rectangle, Region, GraphicsPath
    monkeypatch.setitem(sys.modules, "System.Drawing", drawing)
    monkeypatch.setitem(sys.modules, "System.Drawing.Drawing2D", drawing2d)
    api = _OverlayAPI()
    native = SimpleNamespace(Region=None)
    api._window = SimpleNamespace(native=native)
    api._windows_ready = True
    monkeypatch.setattr(api, "_on_ui", lambda callback: callback())
    api.set_window_shape([[0, 0, 340, 28, 7], [0, 32, 340, 60], [10, 70, 30, 80, 50]])
    assert api._shape == ((0, 0, 340, 28, 7), (0, 32, 340, 60), (10, 70, 30, 80, 5))   # the radius held to half the piece
    rounded, square, small = native.Region.parts
    assert rounded.closed and [arc[1:] for arc in rounded.arcs] == [(180.0, 90.0), (270.0, 90.0), (0.0, 90.0), (90.0, 90.0)]
    assert [arc[0] for arc in rounded.arcs] == [(0, 0, 14, 14), (326, 0, 14, 14), (326, 14, 14, 14), (0, 14, 14, 14)]
    assert square.box == (0, 32, 340, 28) and small.arcs[0][0] == (10, 70, 10, 10)
    written = []
    api.log = SimpleNamespace(write=written.append)

    def broken():
        raise RuntimeError("no GDI+ paths here")
    drawing2d.GraphicsPath = broken                                                     # the rounded shape cannot be built
    api.set_window_shape([[0, 0, 340, 28, 7], [0, 32, 340, 60]])
    assert [part.box for part in native.Region.parts] == [(0, 0, 340, 28), (0, 32, 340, 28)]   # square corners, same pieces
    assert any("square corners" in line for line in written)
