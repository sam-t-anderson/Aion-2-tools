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


def test_overlay_host_drops_the_backdrop_pywebview_asks_for_when_windows_runs_apps_dark(monkeypatch):
    """pywebview asks DWM for a Mica backdrop on its windows when Windows runs apps dark, and DWM paints that backdrop
    across the whole window rectangle, outside the window's region: the see-through modes showed a dark box around
    their pieces on a dark desktop (0.2.371). The host sets the backdrop to none (DWMWA_SYSTEMBACKDROP_TYPE 38,
    DWMSBT_NONE 1), logs it once, and keeps quiet when the call cannot be made."""
    import ctypes
    from types import SimpleNamespace
    from aion2calc.overlay import _OverlayAPI
    calls, backdrop = [], {"kind": 2}                                     # Mica, as pywebview asks for it

    def dwm_set(hwnd, attribute, value, size):
        calls.append((hwnd.value, attribute, ctypes.cast(value, ctypes.POINTER(ctypes.c_int)).contents.value, size))
        backdrop["kind"] = ctypes.cast(value, ctypes.POINTER(ctypes.c_int)).contents.value
        return 0

    def dwm_get(hwnd, attribute, value, size):
        ctypes.cast(value, ctypes.POINTER(ctypes.c_int)).contents.value = backdrop["kind"]
        return 0
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=dwm_set,
                                                                                DwmGetWindowAttribute=dwm_get)), raising=False)
    api, written = _OverlayAPI(), []
    api.log = SimpleNamespace(write=written.append)
    api._drop_backdrop()
    assert calls == []                                                       # no window yet: nothing to ask
    api._hwnd = 4242
    api._drop_backdrop()
    api._drop_backdrop()                                                     # the watchdog looks every few seconds
    assert calls == [(4242, 38, 1, 4)] and written == ["window backdrop: none"]   # set once, while it was Mica
    backdrop["kind"] = 2                                                     # pywebview asked again (a settings change)
    api._drop_backdrop()
    assert calls == [(4242, 38, 1, 4)] * 2 and written == ["window backdrop: none"]

    def refused(*args):
        return 0x80070057                                                    # a Windows without system backdrops
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=refused,
                                                                                DwmGetWindowAttribute=refused)), raising=False)
    api._drop_backdrop()
    assert written[-1] == "window backdrop: left as it is (DwmSetWindowAttribute 0x80070057)"


def test_overlay_host_moves_the_window_with_the_cursor_until_the_button_is_up(monkeypatch):
    """The card's native drag (0.2.371): the window keeps its offset from the cursor, in screen pixels, while the
    primary button is down, and stops when it is up, wherever the cursor is; the screenshot lock and a drag already
    under way refuse a new one."""
    import ctypes
    import sys
    import threading
    from types import SimpleNamespace
    from aion2calc.overlay import _OverlayAPI
    cursor = iter([(500, 300), (510, 305), (510, 305), (560, 340), (600, 350)])
    pressed = iter([True, True, True, False])
    moves = []

    def cursor_pos(point):
        point[0], point[1] = next(cursor)

    def window_rect(hwnd, rect):
        rect[0], rect[1], rect[2], rect[3] = 420, 260, 760, 400
    user32 = SimpleNamespace(GetAsyncKeyState=lambda button: 0x8000 if next(pressed) else 0, GetSystemMetrics=lambda index: 0,
                             GetCursorPos=cursor_pos, GetWindowRect=window_rect,
                             SetWindowPos=lambda hwnd, after, x, y, w, h, flags: moves.append((x, y)))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: user32, raising=False)
    api = _OverlayAPI()
    api._window = SimpleNamespace(native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 7)))
    api._dragging = True
    api._drag(poll=0)
    assert moves == [(430, 265), (480, 300)] and api._dragging is False     # the offset kept; still cursor, no move
    started = []
    monkeypatch.setattr(api, "_drag", lambda: started.append(1))
    monkeypatch.setattr(sys, "platform", "win32")
    api._locked = True
    api.begin_drag()
    under_way = threading.Event()
    api._locked, api._dragging = False, True
    api._drag_thread = threading.Thread(target=under_way.wait, daemon=True)
    api._drag_thread.start()
    api.begin_drag()
    assert started == []
    under_way.set()
    api._drag_thread.join(2)
    api._dragging = False
    api.begin_drag()
    api._drag_thread.join(2)
    assert started == [1] and api._dragging is True                          # the stand-in drag never clears it
    # 0.2.373: a flag left set by a drag whose thread is gone does not refuse every move after it
    api.begin_drag()
    api._drag_thread.join(2)
    assert started == [1, 1]


def test_the_app_keeps_the_raid_planners_saved_plans_for_the_overlay(monkeypatch, tmp_path):
    """The overlay's window cannot read the planner's browser storage: the planner hands its whole set of saved plans
    to the app on every save, and the overlay's plan view reads them back (0.2.371)."""
    import pytest
    from aion2calc.app import server
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    assert server.saved_plans() == {"plans": {}, "updated": None}
    plan = {"format": "a2plan", "version": 1, "meta": {"name": "Atiel pull"}, "tokens": []}
    assert server.save_plans({"p1": plan})["count"] == 1
    kept = server.saved_plans()
    assert kept["plans"] == {"p1": plan} and kept["updated"] > 0
    assert server.save_plans({})["count"] == 0 and server.saved_plans()["plans"] == {}   # a delete reaches the app too
    for bad in (None, [], {"": plan}, {"p1": "plan"}, {"x" * 65: plan}):
        with pytest.raises(ValueError):
            server.save_plans(bad)
    monkeypatch.setattr(server, "SAVED_PLANS_MAX", 1)
    with pytest.raises(ValueError):
        server.save_plans({"p1": plan, "p2": plan})


def test_hover_to_interact_opens_a_click_through_overlay_after_a_rest_and_closes_when_the_pointer_leaves():
    """Hover-to-interact (0.2.371): over what the overlay draws (a piece of its shape, or anywhere without one) for
    the hold time, the overlay takes clicks; leaving closes it again. The page hears each change once."""
    from aion2calc.overlay import _HoverOpen, _over_overlay
    hover = _HoverOpen(hold=5.0)
    assert hover.update(True, False, 0.0) == (False, None)                 # not over it: nothing to say
    assert hover.update(True, True, 1.0) == (False, "arming")
    assert hover.update(True, True, 5.9) == (False, None)                  # 4.9 s in
    assert hover.update(True, True, 6.0) == (True, "open")
    assert hover.update(True, True, 9.0) == (True, None)
    assert hover.update(True, False, 9.1) == (False, "off")                # left: clicks pass through again
    assert hover.update(True, True, 9.2) == (False, "arming")              # and the count starts over
    assert hover.update(False, True, 20.0) == (False, "off")               # the setting turned off
    shape = ((0, 0, 100, 30, 6), (0, 40, 100, 70))
    assert _over_overlay(shape, (50, 20)) and _over_overlay(shape, (50, 60))
    assert not _over_overlay(shape, (50, 35))                              # the game between two pieces
    assert _over_overlay(None, (500, 500)) and not _over_overlay(shape, None)


def test_the_click_through_loop_opens_the_window_after_the_hover_hold(monkeypatch):
    """The host's loop: transparent while the pointer is merely over the overlay, opaque once it rested for the hold,
    transparent again after it leaves; the page is told "arming", "open" and "off"."""
    import threading
    import time
    from types import SimpleNamespace
    from aion2calc import overlay as ov
    monkeypatch.setattr(ov, "HOVER_INTERACT_S", 0.15)
    pointer = {"pos": (20, 20)}
    applied, said = [], []
    win32 = SimpleNamespace(cursor_in_client=lambda hwnd: pointer["pos"],
                            set_click_through=lambda hwnd, value: applied.append(value))
    window = SimpleNamespace(native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 9)))
    api = SimpleNamespace(_click_through=True, _hover_interact=True, _interactive=(), _shape=((0, 0, 100, 50),),
                          _on_ui=lambda fn: fn(), _say_hover=said.append)
    closed = threading.Event()
    loop = threading.Thread(target=ov._click_through_loop, args=(window, api, win32, closed), daemon=True)
    loop.start()
    try:
        deadline = time.monotonic() + 3
        while "open" not in said and time.monotonic() < deadline:
            time.sleep(0.02)
        pointer["pos"] = (20, 80)                                           # off the shape: over the game
        while "off" not in said and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        closed.set()
        loop.join(2)
    assert said == ["arming", "open", "off"]
    assert applied == [True, False, True]
