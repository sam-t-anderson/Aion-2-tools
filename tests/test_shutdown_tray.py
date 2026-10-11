"""Programmatic Quit/update must stop a running collapse-to-tray icon so the
process actually exits (otherwise the auto-updater hangs waiting for the PID),
and applying an update must not block on the quit-upload."""
import time

import pytest

from aion2calc.app import server


class _FakeIcon:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeRunner:
    running = False
    thread = None

    def stop(self):
        pass


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    # Keep shutdown from touching real windows / capture / HTTP server.
    monkeypatch.setattr("aion2calc.app.meter_runner.runner", lambda: _FakeRunner())
    monkeypatch.setattr("aion2calc.app.overlay_launch.close", lambda: None, raising=False)
    monkeypatch.setattr("aion2calc.app.windows.close_app_browser", lambda: None, raising=False)
    server.HTTPD.clear()
    server.APP_WINDOW.clear()
    server.TRAY.clear()
    yield
    server.TRAY.clear()
    server.HTTPD.clear()


def _run_shutdown(**kwargs):
    server.schedule_shutdown(**kwargs)
    # schedule_shutdown works on a daemon thread after a 0.5s grace delay.
    for _ in range(40):
        time.sleep(0.05)
        if server.TRAY.get("icon") and server.TRAY["icon"].stopped:
            return
    time.sleep(0.2)


def test_shutdown_stops_the_tray_icon_so_the_process_can_exit():
    icon = _FakeIcon()
    server.TRAY["icon"] = icon
    _run_shutdown()
    assert icon.stopped is True


def test_update_shutdown_skips_the_quit_upload(monkeypatch):
    called = []
    monkeypatch.setattr(server, "_auto_upload_on_quit", lambda: called.append(1))
    icon = _FakeIcon()
    server.TRAY["icon"] = icon
    _run_shutdown(upload=False)
    assert icon.stopped is True        # still exits the tray
    assert called == []                # but no slow upload on the update path


def test_schedule_shutdown_defaults_to_uploading():
    import inspect
    assert inspect.signature(server.schedule_shutdown).parameters["upload"].default is True
