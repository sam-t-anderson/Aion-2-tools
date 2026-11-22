"""The native window's and overlay's choices kept by the app with the web pages' (0.2.482): ``gui/interface.py``
reads the app's interface data once, as a Qt settings file is read, keeps it up to date in memory and sends each
change to the app in the order it was made, off the interface's thread. The settings files the native interface
kept until then (Qt's, in the user's profile) are copied to the app the first time, and never again."""
import os
import threading
import urllib.error
from http.server import ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402

from aion2calc.gui import interface  # noqa: E402
from aion2calc.gui.api import AppApi  # noqa: E402


class FakeApp:
    """The app's ``/api/interface``: what it keeps, and each request it was sent and from which thread."""

    def __init__(self, values=None, fails=False):
        self.values = dict(values or {})
        self.fails = fails
        self.gets, self.posts = 0, []

    def get(self, path, timeout=None):
        assert path == "/api/interface"
        self.gets += 1
        if self.fails:
            raise urllib.error.URLError("refused")
        return {"values": dict(self.values)}

    def post(self, path, payload, timeout=None, origin=False):
        assert path == "/api/interface"
        self.posts.append((payload["set"], threading.current_thread().name))
        if self.fails:
            raise urllib.error.URLError("refused")
        for key, value in payload["set"].items():
            if value is None:
                self.values.pop(key, None)
            else:
                self.values[key] = value
        return {"ok": True}


@pytest.fixture
def shared(monkeypatch):
    """A process's store of its own for each test (the pages a test builds without a store of theirs use it)."""
    fresh = interface._Shared()
    monkeypatch.setattr(interface, "_shared", fresh)
    yield fresh
    if fresh.pool is not None:
        fresh.pool.shutdown(wait=True)


def sent(shared):
    """Wait for the changes on their way to the app."""
    if shared.pool is not None:
        shared.pool.submit(lambda: None).result(timeout=30)


def test_it_reads_and_writes_as_a_settings_file_does(shared):
    app = FakeApp({"meter-scope": "party", "native-overlay/opacity": "85", "native-overlay/locked": "true",
                   "a2-settab": "meter", "skipped": 3})
    interface.connect(app, old=[])
    main, overlay = interface.store(), interface.store(interface.OVERLAY)
    assert app.gets == 1                                          # read once, as the window opens
    assert main.value("meter-scope") == "party" and main.value("missing") is None and main.value("missing", "x") == "x"
    assert not main.contains("skipped")                           # what is not a text is not the app's data
    assert overlay.value("opacity", 100, type=int) == 85 and overlay.value("locked", False, type=bool) is True
    assert overlay.value("opacity", type=float) == 85.0 and overlay.value("missing", 7, type=int) == 7
    assert sorted(overlay.allKeys()) == ["locked", "opacity"] and overlay.contains("opacity")
    assert not overlay.contains("meter-scope") and main.contains("native-overlay/opacity")
    # each change is kept at once, and on its way to the app as a text, as a browser's storage keeps one
    overlay.setValue("opacity", 70)
    overlay.setValue("locked", False)
    main.setValue("a2-settab", "overlay")
    main.setValue("ids", ["1", "2"])                              # a list, as a Qt settings file reads one with commas
    main.remove("meter-scope")
    main.sync()
    assert overlay.value("opacity", type=int) == 70 and overlay.value("locked", True, type=bool) is False
    assert main.value("meter-scope", "all") == "all" and main.value("ids") == "1, 2"
    sent(shared)
    posted = {}
    for changes, _ in app.posts[1:]:
        posted.update(changes)
    assert posted == {"native-overlay/opacity": "70", "native-overlay/locked": "false", "a2-settab": "overlay",
                      "ids": "1, 2", "meter-scope": None}
    assert {thread for _, thread in app.posts} == {"interface-store_0"}       # one worker, never the interface's thread
    assert app.values["a2-settab"] == "overlay" and "meter-scope" not in app.values and app.gets == 1


def test_changes_made_while_one_is_sent_go_together(shared):
    release, started = threading.Event(), threading.Event()

    class SlowApp(FakeApp):
        def post(self, path, payload, timeout=None, origin=False):
            started.set()
            release.wait(30)                                      # the app taking its time over the first
            return super().post(path, payload, timeout, origin)

    app = SlowApp({interface.MOVED: "1"})
    interface.connect(app, old=[])
    overlay = interface.store(interface.OVERLAY)
    overlay.setValue("opacity", 0.9)
    assert started.wait(30)
    for step in (0.8, 0.7, 0.6, 0.5):                             # an opacity dragged
        overlay.setValue("opacity", step)
    overlay.remove("locked")
    release.set()
    sent(shared)
    assert [changes for changes, _ in app.posts] == [{"native-overlay/opacity": "0.9"},
                                                     {"native-overlay/opacity": "0.5", "native-overlay/locked": None}]
    assert app.values == {interface.MOVED: "1", "native-overlay/opacity": "0.5"}
    overlay.setValue("opacity", 0.4)                              # and after, as before
    sent(shared)
    assert app.posts[-1][0] == {"native-overlay/opacity": "0.4"} and len(app.posts) == 3


def test_without_the_app_the_choices_stay_in_memory(shared):
    store = interface.store()
    assert store.value("theme") is None
    store.setValue("theme", "light")
    assert store.value("theme") == "light" and interface.store().value("theme") == "light"     # one store a process
    assert shared.pool is None                                    # nothing to send, nowhere to send it


def test_an_app_that_does_not_answer_leaves_the_window_working(shared):
    app = FakeApp(fails=True)
    interface.connect(app, old=[])
    store = interface.store()
    assert store.allKeys() == []
    store.setValue("meter-scope", "party")                       # sent, refused, and the window goes on
    sent(shared)
    assert store.value("meter-scope") == "party" and [changes for changes, _ in app.posts] == [{"meter-scope": "party"}]


def test_an_app_that_did_not_answer_gets_no_old_file_copied(shared, tmp_path):
    old = QSettings(str(tmp_path / "native-interface.ini"), QSettings.IniFormat)
    old.setValue("a2-settab", "server")
    old.sync()
    app = FakeApp({"a2-settab": "meter"}, fails=True)
    interface.connect(app, [(old, "")])
    sent(shared)
    assert app.posts == [] and interface.store().value("a2-settab") is None    # what the app has is not known
    app.fails = False                                             # the next time the window opens, it answers
    interface.connect(app, [(old, "")])
    sent(shared)
    assert app.values == {"a2-settab": "meter", interface.MOVED: "1"}


def test_the_old_settings_files_are_copied_to_the_app_once(shared, tmp_path):
    window = QSettings(str(tmp_path / "native-interface.ini"), QSettings.IniFormat)
    window.setValue("meter-scope", "party")
    window.setValue("a2-settab", "server")                        # the app has its own of this one: the app's stays
    window.setValue("meter-final-boss-ids", "2400010,2400011")
    window.sync()
    overlay = QSettings(str(tmp_path / "native-overlay.ini"), QSettings.IniFormat)
    overlay.setValue("opacity", 85)
    overlay.setValue("locked", True)
    overlay.sync()
    old = [(QSettings(str(tmp_path / "native-interface.ini"), QSettings.IniFormat), ""),
           (QSettings(str(tmp_path / "native-overlay.ini"), QSettings.IniFormat), interface.OVERLAY)]
    app = FakeApp({"a2-settab": "meter", "theme": "light"})
    interface.connect(app, old)
    sent(shared)
    assert app.values == {"a2-settab": "meter", "theme": "light", "meter-scope": "party",
                          "meter-final-boss-ids": "2400010,2400011", "native-overlay/opacity": "85",
                          "native-overlay/locked": "true", interface.MOVED: "1"}
    assert len(app.posts) == 1                                    # in one request
    assert interface.store(interface.OVERLAY).value("opacity", type=int) == 85
    # the next time the window or the overlay opens, nothing is copied again, even what changed since in the old files
    window.setValue("meter-scope", "all")
    window.sync()
    app.values.pop("meter-scope")
    interface.connect(app, old)
    sent(shared)
    assert len(app.posts) == 1 and interface.store().value("meter-scope") is None and app.gets == 2


def test_the_native_window_and_the_web_pages_find_the_same_choices(shared, tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.app import interface_store, server
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    try:
        interface_store.update({"meter-scope": "party"})          # the web page's choice
        api = AppApi(base)
        interface.connect(api, old=[])
        store = interface.store()
        assert store.value("meter-scope") == "party"
        store.setValue("a2-settab", "overlay")                     # the native window's
        store.remove("meter-scope")
        sent(shared)
        assert interface_store.values() == {"a2-settab": "overlay", interface.MOVED: "1"}
        page = api.get_bytes("/").decode("utf-8")
        assert '"a2-settab":"overlay"' in page and "meter-scope" not in page    # what the web page reads first
    finally:
        srv.shutdown()
