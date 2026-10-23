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


class _FailingRunner(_FakeRunner):
    """A capture whose stop times out (the final save of a long recording), as 0.2.329's quits saw."""

    def __init__(self, order):
        self.order = order

    def stop(self):
        self.order.append("capture")
        raise TimeoutError("Capture is still shutting down")


def test_the_overlays_close_first_even_when_the_capture_stop_fails(monkeypatch):
    order = []
    monkeypatch.setattr("aion2calc.app.meter_runner.runner", lambda: _FailingRunner(order))
    monkeypatch.setattr("aion2calc.app.overlay_launch.close", lambda: order.append("overlays"))
    monkeypatch.setattr(server, "_auto_upload_on_quit", lambda: order.append("upload"))
    icon = _FakeIcon()
    server.TRAY["icon"] = icon
    _run_shutdown()
    assert icon.stopped is True
    assert order == ["overlays", "capture", "upload"]


def test_serve_closes_the_overlays_before_the_capture_stops_and_despite_its_failure(monkeypatch):
    """The window-close path: serve() ends, and its teardown used to stop the capture first and close the
    overlays in the same try, so a capture stop that raised left the overlays open after the app had gone."""
    order = []
    monkeypatch.setattr("aion2calc.app.meter_runner.runner", lambda: _FailingRunner(order))
    monkeypatch.setattr("aion2calc.app.overlay_launch.close", lambda: order.append("overlays"))

    class _Httpd:
        server_address = ("127.0.0.1", 1)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            order.append("server")

    server.serve(open_browser=False, sync=False, httpd=_Httpd(), open_overlay=False)
    assert order == ["overlays", "capture", "server"]
