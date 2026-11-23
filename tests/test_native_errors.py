"""The native interface's errors on record (0.2.503): every uncaught Python error of a native process, raised in a Qt
handler, a thread or as it starts, written with its traceback to ``logs/native.log`` under the process's name, where
the installed app (built without a console) let it go unseen; the capture diagnostics carry the log's end.
"""
import os
import sys
import threading
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from aion2calc.gui import companions as cp  # noqa: E402
from aion2calc.gui import errors  # noqa: E402
from aion2calc.gui import i18n, interface, theme  # noqa: E402
from aion2calc.gui import overlay as native_overlay  # noqa: E402
from aion2calc.gui import window as native_window  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _hooks_kept(monkeypatch):
    """Each test's hooks are let go after it (the test's own stand-ins, then Python's)."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _raised(error):
    try:
        raise error
    except type(error) as caught:
        return type(caught), caught, caught.__traceback__


class _Window:
    """A stand-in for a process's window: shown and started, nothing more."""

    def __init__(self, *args, **kwargs):
        pass

    def show(self):
        pass

    def start(self):
        pass


def test_an_error_is_written_with_its_traceback_and_handed_on(tmp_path, monkeypatch):
    handed = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: handed.append(str(value)))
    log = tmp_path / "native.log"
    errors.record("window", log)
    sys.excepthook(*_raised(ValueError("the reply was not a list")))
    text = log.read_text(encoding="utf-8")
    assert " window: Traceback (most recent call last):" in text and "ValueError: the reply was not a list" in text
    assert "_raised" in text and handed == ["the reply was not a list"]                  # its traceback, then handed on
    # a hook before it that fails (no console to print on) costs nothing more
    monkeypatch.setattr(sys, "excepthook", lambda *args: 1 / 0)
    errors.record("window", log)
    sys.excepthook(*_raised(KeyError("cls")))
    assert "KeyError: 'cls'" in log.read_text(encoding="utf-8")
    assert errors.log_path().name == "native.log" and errors.log_path().parent.name == "logs"


def test_qt_handlers_and_threads_errors_are_on_record(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", lambda *args: None)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    log = tmp_path / "native.log"
    errors.record("overlay", log)

    def timer():
        raise RuntimeError("a timer's")
    QTimer.singleShot(0, timer)
    for _ in range(5):
        QCoreApplication.processEvents()
    button = QPushButton()
    button.clicked.connect(lambda: 1 / 0)
    button.click()

    class Replies(QObject):
        replied = Signal(str)

    def handler(name):
        raise LookupError(f"no {name}")
    replies = Replies()
    replies.replied.connect(handler)
    replies.replied.emit("meter")
    worker = threading.Thread(target=lambda: [][1])
    worker.start()
    worker.join()
    ended = threading.Thread(target=lambda: sys.exit(0))             # a thread's own end is no error
    ended.start()
    ended.join()
    text = log.read_text(encoding="utf-8")
    for words in ("RuntimeError: a timer's", "ZeroDivisionError: division by zero", "LookupError: no meter",
                  "IndexError: list index out of range"):
        assert words in text
    assert text.count(" overlay: Traceback") == 4 and "SystemExit" not in text


def test_each_native_process_records_under_its_name(qapp, monkeypatch):
    recorded = []
    monkeypatch.setattr(errors, "record", lambda who, path=None: recorded.append(who))
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(interface, "connect", lambda api, old=None: None)
    monkeypatch.setattr(native_window, "MainWindow", _Window)
    monkeypatch.setattr(native_window, "ui_settings", lambda api, ui=None: {})
    monkeypatch.setattr(native_window, "_follow_the_computer", lambda app: None)
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    try:
        assert native_window.main(["--url", "http://127.0.0.1:9/"]) == 0
    finally:
        i18n.uninstall()
        theme.apply_look("dark")
    monkeypatch.setattr(native_overlay, "MeterOverlay", _Window)
    assert native_overlay.main(["--url", "http://127.0.0.1:9/overlay"]) == 0
    monkeypatch.setattr(cp, "window_class", lambda view: _Window)
    assert native_overlay.main(["--url", "http://127.0.0.1:9/overlay?view=radar"]) == 0    # the overlay hands it on
    assert cp.main(["--url", "http://127.0.0.1:9/overlay?view=pets"]) == 0
    assert recorded == ["window", "overlay", "radar window", "pets window"]                  # once each, by its name


def test_the_capture_diagnostics_carry_the_log(tmp_path, monkeypatch):
    from aion2calc.meter.diagnostics import export
    from aion2calc.paths import logs_dir
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    result = export({"diagnostics": {"packets": 1}}, None)
    assert "native.log" not in result["contents"]                                          # none yet: none carried
    with zipfile.ZipFile(result["file"]) as archive:
        assert "native.log" not in archive.namelist()
    monkeypatch.setattr(sys, "excepthook", lambda *args: None)
    errors.record("party window", logs_dir() / "native.log")
    sys.excepthook(*_raised(TypeError("'NoneType' object is not subscriptable")))
    result = export({"diagnostics": {"packets": 1}}, None)
    assert result["contents"][-1] == "native.log"
    with zipfile.ZipFile(result["file"]) as archive:
        carried = archive.read("native.log").decode("utf-8")
        assert " party window: Traceback" in carried and "TypeError" in carried
        assert "native.log, when present" in archive.read("README.txt").decode("utf-8")
