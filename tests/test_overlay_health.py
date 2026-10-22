"""The overlay's watchdog (0.2.327): a blank window is detected from its own pixels, healed in steps
(nudge, reload, navigate, restart) with grace periods between them, a dead page skips the nudge, a failure
WebView2 reports is acted on at once, and the app starts a restarted overlay again, a bounded number of
times. The Windows calls are stand-ins here; the decisions are the same on any platform."""
import os
import threading
import time
import types

import pytest

from aion2calc import overlay
from aion2calc.app import overlay_launch
from aion2calc.overlay_health import (BLANK_FRACTION, HOST_COLOR, RESTART_EXIT_CODE, BlankDetector, HealPolicy,
                                      OverlayLog, RelaunchLimiter, host_fraction)

HOST = bytes((HOST_COLOR[2], HOST_COLOR[1], HOST_COLOR[0], 255))
TEXT = bytes((240, 230, 220, 255))


def _frame(pixels, text_pixels=0):
    return HOST * (pixels - text_pixels) + TEXT * text_pixels


def test_the_host_colour_fraction_counts_pixels():
    assert host_fraction(b"") is None
    assert host_fraction(_frame(1000)) == 1.0
    assert host_fraction(_frame(1000, 500)) == 0.5
    assert host_fraction(_frame(100_000, 100)) == 0.999   # 0.1 % content: still blank by the threshold
    assert BLANK_FRACTION == 0.998


def test_blank_detection_arms_only_after_content_was_seen():
    detector = BlankDetector()
    assert detector.verdict(None) is None and detector.verdict(_frame(500)) is None   # nothing seen yet: no verdict
    assert not detector.armed
    assert detector.verdict(_frame(40_800, 2_000)) is False and detector.armed       # a drawn card: 5 % content
    assert detector.verdict(_frame(40_800)) is True                                   # and now a blank frame counts
    assert detector.verdict(_frame(40_800, 60)) is True                               # 0.15 % content is noise


def test_three_bad_looks_start_a_step_and_steps_escalate_with_grace():
    policy = HealPolicy(misses=3, grace=20, calm=120)
    assert [policy.observe(t, True, True) for t in (0, 5, 10)] == [None, None, "nudge"]
    assert policy.reason == "the window drew nothing"
    assert [policy.observe(t, True, True) for t in (15, 20, 25)] == [None, None, None]   # the grace period
    assert [policy.observe(t, True, True) for t in (30, 35, 40)] == [None, None, "reload"]
    assert [policy.observe(t, True, True) for t in (60, 65, 70)] == [None, None, "navigate"]
    assert [policy.observe(t, True, True) for t in (90, 95, 100)] == [None, None, "restart"]
    assert [policy.observe(t, True, True) for t in (120, 125, 130)] == [None, None, "restart"]   # the last step repeats


def test_a_healthy_spell_ends_the_episode_and_a_dead_page_skips_the_nudge():
    policy = HealPolicy()
    assert [policy.observe(t, True, True) for t in (0, 5, 10)][-1] == "nudge"
    assert all(policy.observe(t, True, False) is None for t in range(30, 160, 5))   # two minutes healthy
    assert [policy.observe(t, True, True) for t in (160, 165, 170)][-1] == "nudge"  # back to the gentlest step
    dead = HealPolicy()
    assert [dead.observe(t, False, None) for t in (0, 5, 10)] == [None, None, "reload"]
    assert dead.reason == "the page did not answer"
    assert dead.observe(100, None, None) is None                                      # no probe: no opinion
    forced = HealPolicy()
    assert forced.force(0, "reload", "WebView2 RenderProcessExited") == "reload"
    assert [forced.observe(t, True, True) for t in (25, 30, 35)][-1] == "navigate"   # past the forced step


def test_relaunches_are_limited_to_five_in_ten_minutes():
    limiter = RelaunchLimiter()
    assert all(limiter.allow(t) for t in range(5))
    assert not limiter.allow(10)
    assert limiter.allow(700)                                                        # the first ones have aged out


def test_the_log_is_appended_and_kept_small(tmp_path):
    log = OverlayLog(tmp_path / "overlay.log", "overlay", limit=2_000, keep=500)
    log.write("started")
    assert log.tail().endswith(" overlay: started\n")
    for i in range(200):
        log.write(f"line {i}")
    assert os.path.getsize(log.path) < 2_000 + 100 and "line 199" in log.tail()
    assert OverlayLog(tmp_path / "missing.log").tail() == ""
    OverlayLog("/nonexistent/dir/overlay.log").write("never raises")


class _Native:
    """A stand-in for pywebview's WinForms host: the page's answer, the control, the handle."""

    def __init__(self):
        self.state = "complete"
        self.hang = None                                                   # an Event the page answer waits on
        self.calls = []
        self.browser = types.SimpleNamespace(evaluate_js=self._evaluate, load_url=lambda url: self.calls.append(("load_url", url)))
        self.webview = types.SimpleNamespace(CoreWebView2=types.SimpleNamespace(Reload=lambda: self.calls.append("reload")), Visible=True)
        self.Handle = types.SimpleNamespace(ToInt64=lambda: 1)

    def _evaluate(self, script, parse_json):
        if self.hang is not None:
            self.hang.wait()
        if isinstance(self.state, Exception):
            raise self.state
        return self.state


def _watchdog(frame, now=None):
    native = _Native()
    window = types.SimpleNamespace(native=native, destroyed=False, loaded=[])
    window.load_url = lambda url: window.loaded.append(url)
    window.destroy = lambda: setattr(window, "destroyed", True)
    api = overlay._OverlayAPI()
    api._window, api.url = window, "http://127.0.0.1:8765/overlay"
    api._on_ui = lambda callback: callback()                                # no UI thread here
    api.hook_process_failures = lambda: None
    win32 = types.SimpleNamespace(capture=lambda hwnd: frame["bytes"])
    clock = {"now": 1000.0}
    watchdog = overlay._Watchdog(window, api, win32, clock=lambda: clock["now"])
    watchdog.PROBE_TIMEOUT = 0.5
    watchdog.exit = lambda code: api.log.write(f"exit {code}")
    return watchdog, native, window, api, clock


def test_the_watchdog_leaves_a_drawn_page_alone_and_logs_when_armed(tmp_path):
    frame = {"bytes": _frame(40_800, 2_000)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    for _ in range(4):
        assert watchdog.tick() is None
        clock["now"] += 5
    assert watchdog.detector.armed and "blank detection armed" in api.log.tail()
    assert native.calls == [] and not window.destroyed


def test_a_blank_window_is_nudged_reloaded_navigated_then_restarted(tmp_path):
    frame = {"bytes": _frame(40_800, 2_000)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    watchdog.tick()                                                         # content seen: armed
    frame["bytes"] = _frame(40_800)                                         # from now on the window is blank
    actions = []
    for _ in range(40):
        clock["now"] += 5
        action = watchdog.tick()
        if action:
            actions.append(action)
        if window.destroyed:
            break
    assert actions == ["nudge", "reload", "navigate", "restart"]
    assert native.webview.Visible is True and "reload" in native.calls       # the nudge toggled, the reload reloaded
    assert window.loaded == [api.url] and api._restart and window.destroyed
    log = api.log.tail()
    assert "nudge: the window drew nothing" in log and "restart: the window drew nothing" in log


def test_a_page_that_does_not_answer_is_reloaded_without_a_nudge(tmp_path):
    frame = {"bytes": _frame(40_800, 2_000)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    native.state = RuntimeError("the render process is gone")
    actions = [watchdog.tick() for _ in range(3)]
    assert actions == [None, None, "reload"] and native.calls == ["reload"]
    assert "reload: the page did not answer (the page did not answer)" in api.log.tail()


def test_a_hanging_page_counts_as_silent_and_a_hanging_heal_restarts(tmp_path):
    frame = {"bytes": _frame(40_800, 2_000)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    native.hang = threading.Event()                                         # the UI thread never answers
    native.webview.CoreWebView2.Reload = lambda: native.hang.wait()         # so the reload hangs too
    watchdog.HEAL_TIMEOUT = 0.2
    try:
        for _ in range(3):
            clock["now"] += 5
            watchdog.tick()
        assert "no answer in" in api.log.tail()
        # Neither the hung heal nor its probe ever returns: the watchdog restarts the overlay.
        assert api._restart and "did not finish" in api.log.tail()
    finally:
        native.hang.set()


def test_a_failure_webview2_reports_is_acted_on_at_once(tmp_path):
    frame = {"bytes": _frame(40_800, 2_000)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    api._failure = ("RenderProcessExited", "RenderProcessExited (reason Crashed, exit code -1)")
    assert watchdog.tick() == "reload" and native.calls == ["reload"]
    assert "WebView2 reported RenderProcessExited (reason Crashed" in api.log.tail()
    api._failure = ("BrowserProcessExited", "BrowserProcessExited (reason Unexpected, exit code 1)")
    assert watchdog.tick() == "restart" and window.destroyed and api._restart
    other = _watchdog(frame)
    other[3].log = OverlayLog(tmp_path / "other.log")
    other[3]._reload_requested = 1
    assert other[0].tick() == "reload" and "the app asked for a reload" in other[3].log.tail()


def test_a_hidden_window_is_not_judged_blank(tmp_path):
    frame = {"bytes": _frame(40_800, 2_000)}
    watchdog, native, window, api, clock = _watchdog(frame)
    api.log = OverlayLog(tmp_path / "overlay.log")
    watchdog.tick()
    frame["bytes"] = _frame(40_800)
    api._visible = False                                                    # the game is minimized: no capture
    for _ in range(6):
        clock["now"] += 5
        assert watchdog.tick() is None
    assert native.calls == []


def test_the_process_failed_hook_records_what_webview2_said():
    api = overlay._OverlayAPI()
    api._on_process_failed(None, types.SimpleNamespace(ProcessFailedKind="RenderProcessUnresponsive", Reason="Unresponsive", ExitCode=0))
    assert api._failure == ("RenderProcessUnresponsive", "RenderProcessUnresponsive (reason Unresponsive, exit code 0)")
    api._on_process_failed(None, None)                                      # never raises on the UI thread
    assert api._failure[0] == "an unknown process failure"
    assert RESTART_EXIT_CODE == 3


class _Popen:
    def __init__(self):
        self._done, self.returncode = threading.Event(), None

    def wait(self):
        self._done.wait()
        return self.returncode

    def poll(self):
        return self.returncode if self._done.is_set() else None

    def terminate(self):
        self.end(1)

    def end(self, code):
        self.returncode = code
        self._done.set()


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    spawned = []
    monkeypatch.setattr(overlay_launch, "_spawn", lambda url: spawned.append(_Popen()) or spawned[-1])
    monkeypatch.setattr(overlay_launch, "available", lambda: True)
    monkeypatch.setattr(overlay_launch, "_party_enabled", lambda: False)
    monkeypatch.setattr(overlay_launch, "_PROCESS", None)
    monkeypatch.setattr(overlay_launch, "_PARTY_PROCESS", None)
    monkeypatch.setattr(overlay_launch, "_RELAUNCHES", RelaunchLimiter())
    return spawned


def _wait_for(condition, seconds=3.0):
    deadline = time.time() + seconds
    while not condition() and time.time() < deadline:
        time.sleep(0.01)
    return condition()


def test_the_app_starts_a_restarted_overlay_again_but_not_a_closed_one(launcher, tmp_path):
    spawned = launcher
    assert overlay_launch.launch("http://127.0.0.1:1/overlay") == {"native": True, "already_open": False, "reason": ""}
    spawned[0].end(RESTART_EXIT_CODE)                                       # its watchdog asked for a restart
    assert _wait_for(lambda: len(spawned) == 2) and overlay_launch._PROCESS is spawned[1]
    assert "starting it again" in (tmp_path / "logs" / "overlay.log").read_text(encoding="utf-8")
    spawned[1].end(0)                                                        # Hide: closed on purpose
    assert _wait_for(lambda: overlay_launch._PROCESS is None) and len(spawned) == 2
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    overlay_launch.close()                                                   # the app closes it: terminate, code 1
    assert _wait_for(lambda: spawned[2].poll() is not None)
    time.sleep(0.1)
    assert len(spawned) == 3 and overlay_launch._PROCESS is None


def test_relaunches_stop_after_five_in_ten_minutes(launcher, tmp_path):
    spawned = launcher
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    for i in range(5):
        spawned[-1].end(1)
        assert _wait_for(lambda n=len(spawned): len(spawned) == n + 1)
    spawned[-1].end(1)
    assert _wait_for(lambda: overlay_launch._PROCESS is None) and len(spawned) == 6
    assert "not started again" in (tmp_path / "logs" / "overlay.log").read_text(encoding="utf-8")


def test_open_overlay_while_open_asks_it_to_reload(launcher):
    from aion2calc.app import server
    before = server.OVERLAY_COMMANDS.get("reload_seq", 0)
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    assert overlay_launch.launch("http://127.0.0.1:1/overlay")["already_open"] is True
    assert server.OVERLAY_COMMANDS["reload_seq"] == before                  # a plain launch (app start) does not
    overlay_launch.launch("http://127.0.0.1:1/overlay", reload_if_open=True)
    assert server.OVERLAY_COMMANDS["reload_seq"] == before + 1               # the Open button does


def test_the_page_reports_its_errors_and_the_app_writes_them(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app import server
    monkeypatch.setattr(server, "_OVERLAY_NOTES", [])
    assert server.overlay_health_note({"kind": "error", "message": "x is not defined @ overlay.js:12"}) == {"written": True}
    assert "overlay page: error: x is not defined @ overlay.js:12" in (tmp_path / "logs" / "overlay.log").read_text(encoding="utf-8")
    for _ in range(70):
        server.overlay_health_note({"kind": "error", "message": "again"})
    assert server.overlay_health_note({"kind": "error", "message": "again"}) == {"written": False, "reason": "limit"}
    static = os.path.join(os.path.dirname(overlay.__file__), "app", "static", "overlay.js")
    script = open(static, encoding="utf-8").read()
    assert '"/api/overlay/health"' in script and 'addEventListener("unhandledrejection"' in script
