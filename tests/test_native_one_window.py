"""One app window at a time (0.2.505): a native window's process started while the app's window is open (the tray's
Open, the Open-app and Settings hotkeys, the app started again) hands that window the page its address names and ends,
and the window comes forward on it, where a second window opened beside it. Drawn off screen; the new window's process
is a process of its own, as it is in the app.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QDir, QEvent  # noqa: E402
from PySide6.QtNetwork import QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import i18n, interface, theme  # noqa: E402
from aion2calc.gui import one_window as ow  # noqa: E402
from aion2calc.gui import window as native_window  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def server_name(request):
    """A name of this test's own, apart from any app's and from another run's."""
    return f"aion2calc-window-test-{os.getpid()}-{request.node.name[-24:]}"


@pytest.fixture(autouse=True)
def _let_go():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _new_window_process(server: str, *pages: str, wait_ms: int = ow.WAIT_MS) -> list:
    """What a new window's process makes of handing each page over, run as one (the open window answering meanwhile)."""
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(ROOT)!r})
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication([])
        from aion2calc.gui import one_window
        for page in {list(pages)!r}:
            print(one_window.hand_over({server!r}, page, {wait_ms}), flush=True)
    """)
    process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    deadline = time.monotonic() + 30
    while process.poll() is None:
        assert time.monotonic() < deadline, "the new window's process did not end"
        QCoreApplication.processEvents()
        time.sleep(0.005)
    out, err = process.communicate()
    assert process.returncode == 0, err
    return [line == "True" for line in out.split()]


def _waited(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def test_the_name_is_the_apps_address():
    assert ow.name("http://127.0.0.1:8765/") == "aion2calc-window-127-0-0-1-8765"
    assert ow.name("http://127.0.0.1:8766/#/settings") != ow.name("http://127.0.0.1:8765/")   # another app's own
    assert ow.name("http://[::1]:9/") == "aion2calc-window-1-9" and ow.name("") == "aion2calc-window-app"


def test_the_open_window_takes_the_page_and_comes_forward(qapp, server_name):
    asked = []
    listening = ow.Listening(server_name, lambda page: (asked.append(page), len(asked) == 1)[1], qapp)
    assert listening.listening
    # the first shown, the second answered that none is (the window closing): the new process opens its own
    assert _new_window_process(server_name, "/settings", "") == [True, False]
    assert asked == ["/settings", ""]
    listening.close()
    assert _new_window_process(server_name, "") == [False]                 # none listening: it opens its own
    assert asked == ["/settings", ""]


def test_a_window_that_does_not_answer_in_time(qapp, server_name):
    asked = []
    listening = ow.Listening(server_name, lambda page: asked.append(page) or True, qapp)
    started = time.monotonic()
    assert not ow.hand_over(server_name, "", wait_ms=300)                  # it answers only once this has given up
    assert time.monotonic() - started < 2
    listening.close()
    started = time.monotonic()
    assert not ow.hand_over(server_name, "") and time.monotonic() - started < 1   # none listening: at once


@pytest.mark.skipif(sys.platform == "win32", reason="a named pipe goes with its process")
def test_a_socket_file_left_behind_is_replaced(qapp, server_name):
    left = pathlib.Path(QDir.tempPath(), server_name)
    left.write_text("")                                                    # a window's process ended without a word
    listening = ow.Listening(server_name, lambda page: True, qapp)
    assert listening.listening
    assert _new_window_process(server_name, "/raid") == [True]
    listening.close()
    assert not left.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="a socket file's place; a named pipe has none")
def test_a_name_still_taken_is_tried_again(qapp, monkeypatch):
    monkeypatch.setattr(ow, "RETRY_MS", 20)
    where = pathlib.Path(tempfile.mkdtemp(prefix="a2w-"))                  # short: a socket's path has a limit
    try:
        server = str(where / "later" / "aion2calc-window-test")
        listening = ow.Listening(server, lambda page: True, qapp)
        assert not listening.listening and listening.retry.isActive()      # not there yet: tried again
        _waited(0.1)
        assert not listening.listening
        (where / "later").mkdir()
        _waited(0.1)
        assert listening.listening and not listening.retry.isActive()
        assert _new_window_process(server, "") == [True]
        listening.close()
    finally:
        shutil.rmtree(where, ignore_errors=True)


class _Socket:
    """A connection as the open window reads it: what the new process sent, given in pieces."""

    def __init__(self, *pieces):
        self.pieces, self.written, self.ended = list(pieces), b"", None

    def state(self):
        return QLocalSocket.ConnectedState if self.ended is None else QLocalSocket.ClosingState

    def readAll(self):
        return self.pieces.pop(0) if self.pieces else b""

    def write(self, data):
        self.written += data

    def disconnectFromServer(self):
        self.ended = "answered"

    def abort(self):
        self.ended = "let go"

    def deleteLater(self):
        self.deleted = True


def test_a_request_in_pieces_too_long_or_failing(qapp, server_name):
    asked = []
    listening = ow.Listening(server_name, lambda page: asked.append(page) or True, qapp)
    try:
        socket, read = _Socket("/combat-log/".encode(), "shared/x1\nmore".encode()), bytearray()
        listening._read(socket, read)
        assert asked == [] and socket.ended is None                       # not whole yet
        listening._read(socket, read)
        assert asked == ["/combat-log/shared/x1"] and socket.written == ow.SHOWN and socket.ended == "answered"
        listening._read(socket, read)                                     # answered: nothing more read
        assert asked == ["/combat-log/shared/x1"]
        socket, read = _Socket(b"x" * ow.LONGEST), bytearray()
        listening._read(socket, read)
        assert socket.ended == "let go" and socket.written == b"" and socket.deleted and len(asked) == 1
        socket, read = _Socket("é\n".encode()), bytearray()
        listening._read(socket, read)
        assert asked[-1] == "é"

        def failing(page):
            raise RuntimeError("the window could not come forward")
        listening.come_forward = failing
        socket, read = _Socket(b"\n"), bytearray()
        with pytest.raises(RuntimeError):                                  # on record, as every error (0.2.503)
            listening._read(socket, read)
        assert socket.written == ow.NONE and socket.ended == "answered"     # and answered: the new process goes on
    finally:
        listening.close()


def test_the_window_comes_forward_on_the_page_asked(qapp, monkeypatch):
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    assert not native_window._come_forward("")                            # none shown
    window = native_window.MainWindow(None)
    window.show()
    window.show_page("raid")
    window.showMinimized()
    QCoreApplication.processEvents()
    assert native_window._come_forward("")
    assert not window.isMinimized() and window.current_page() == "raid"   # on the page it shows
    window.showMaximized()
    window.showMinimized()
    QCoreApplication.processEvents()
    assert window.come_forward("/settings")
    assert window.isMaximized() and not window.isMinimized() and window.current_page() == "settings"
    window._closing()                                                       # the app closes for its installer
    assert not window.come_forward("/raid") and not native_window._come_forward("/raid")
    assert window.current_page() == "settings"


class _Window:
    """A stand-in for the window: shown and started, nothing more."""

    built = []

    def __init__(self, *args, **kwargs):
        _Window.built.append(args[2])

    def show(self):
        pass

    def start(self):
        pass


def test_a_new_window_process_hands_over_or_listens(qapp, monkeypatch):
    handed, listened = [], []

    class Listening:
        def __init__(self, server, come_forward, parent=None):
            listened.append((server, come_forward))

        def close(self):
            listened.append("closed")

    answer = {"shown": True}
    monkeypatch.setattr(ow, "hand_over", lambda server, page: handed.append((server, page)) or answer["shown"])
    monkeypatch.setattr(ow, "Listening", Listening)
    monkeypatch.setattr(native_window, "MainWindow", _Window)
    monkeypatch.setattr(native_window, "ui_settings", lambda api, ui=None: {})
    monkeypatch.setattr(native_window, "_follow_the_computer", lambda app: None)
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    monkeypatch.setattr(interface, "connect", lambda api, old=None: None)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)                 # the window's error hooks let go after
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    _Window.built = []
    try:
        assert native_window.main(["--url", "http://127.0.0.1:9/#/settings"]) == 0
        assert handed == [("aion2calc-window-127-0-0-1-9", "/settings")]
        assert _Window.built == [] and listened == []                       # the open window took it: none drawn
        answer["shown"] = False
        assert native_window.main(["--url", "http://127.0.0.1:9/"]) == 0
    finally:
        i18n.uninstall()
        theme.apply_look("dark")
    assert handed[-1] == ("aion2calc-window-127-0-0-1-9", "")
    assert _Window.built == ["meter"]                                       # none open: its own window, as before
    assert listened == [("aion2calc-window-127-0-0-1-9", native_window._come_forward), "closed"]
