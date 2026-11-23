"""The app's own icon on its native windows (0.2.501): the logo, the picture the installed app's executable carries,
on the window's title bar, the taskbar and the window switcher, where Qt drew its placeholder. Each native process
(the app's window, the meter overlay, a companion window) sets it on its application. Drawn off screen.
"""
import hashlib
import os
import pathlib
import sys
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, Qt  # noqa: E402
from PySide6.QtGui import QIcon, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui import app_icon as ai  # noqa: E402
from aion2calc.gui import companions as cp  # noqa: E402
from aion2calc.gui import i18n, interface, theme  # noqa: E402
from aion2calc.gui import overlay as native_overlay  # noqa: E402
from aion2calc.gui import window as native_window  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _icon_let_go():
    """Each test starts and ends with Qt's own icon on the application, its windows closed and deleted."""
    app = QApplication.instance()
    if app is not None:
        app.setWindowIcon(QIcon())
    yield
    app = QApplication.instance()
    if app is None:
        return
    app.setWindowIcon(QIcon())
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _image(icon: QIcon, size: int) -> QImage:
    return icon.pixmap(size, size).toImage().convertToFormat(QImage.Format_ARGB32)


def _logo(size: int) -> QImage:
    """The logo as an icon of ``size`` shows it: scaled smoothly to fit."""
    return (QImage(str(ai.LOGO)).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            .convertToFormat(QImage.Format_ARGB32))


def _worst(a: QImage, b: QImage) -> int:
    """The largest difference of any channel of any pixel of two pictures of a size (256 when the sizes differ)."""
    if a.size() != b.size():
        return 256
    worst = 0
    for y in range(a.height()):
        for x in range(a.width()):
            pa, pb = a.pixelColor(x, y), b.pixelColor(x, y)
            worst = max(worst, abs(pa.red() - pb.red()), abs(pa.green() - pb.green()), abs(pa.blue() - pb.blue()),
                        abs(pa.alpha() - pb.alpha()))
    return worst


def _is_logo(icon: QIcon) -> bool:
    """The icon is the logo at a title bar's, a taskbar's and a window switcher's sizes (Qt's own scaling at 256 px is
    a few levels off the picture's own)."""
    return not icon.isNull() and all(_worst(_image(icon, size), _logo(size)) <= 4 for size in (16, 24, 32, 48, 256))


class _Window:
    """A stand-in for a process's window: shown and started, nothing more."""

    def __init__(self, *args, **kwargs):
        pass

    def show(self):
        pass

    def start(self):
        pass


def test_the_icon_is_the_apps_logo(qapp):
    # the picture the build makes the executable's icon from (packaging/aion2calc.png, as aion2calc.ico)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: E731
    assert ai.LOGO.is_file() and digest(ai.LOGO) == digest(ROOT / "packaging" / "aion2calc.png")
    icon = ai.app_icon()
    assert _is_logo(icon)
    image = _image(icon, 32)
    assert image.pixelColor(16, 16).alpha() == 255 and image.pixelColor(0, 0).alpha() == 0     # the round badge
    from aion2calc.gui import header
    assert header.LOGO == ai.LOGO                                                                # the header's logo


def test_the_window_and_every_native_process_take_it(qapp, monkeypatch):
    window = native_window.MainWindow(None)
    assert _is_logo(window.windowIcon())                        # the window's own, where Qt drew its placeholder
    window.close()
    app = QApplication.instance()
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)                # the processes' error hooks let go after
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(interface, "connect", lambda api, old=None: None)
    # the app's window
    monkeypatch.setattr(native_window, "MainWindow", _Window)
    monkeypatch.setattr(native_window, "ui_settings", lambda api, ui=None: {})
    monkeypatch.setattr(native_window, "_follow_the_computer", lambda app: None)
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    try:
        assert native_window.main(["--url", "http://127.0.0.1:9/"]) == 0
    finally:
        i18n.uninstall()
        theme.apply_look("dark")
    assert _is_logo(app.windowIcon())
    # the meter overlay
    app.setWindowIcon(QIcon())
    monkeypatch.setattr(native_overlay, "MeterOverlay", _Window)
    assert native_overlay.main(["--url", "http://127.0.0.1:9/overlay"]) == 0
    assert _is_logo(app.windowIcon())
    # a companion window (the Party-DPS window)
    app.setWindowIcon(QIcon())
    monkeypatch.setattr(cp, "window_class", lambda view: _Window)
    assert cp.main(["--url", "http://127.0.0.1:9/overlay?view=party"]) == 0
    assert _is_logo(app.windowIcon())


def test_without_its_logo_qts_own_icon_stays(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "LOGO", tmp_path / "gone.png")
    app = QApplication.instance()
    assert ai.app_icon().isNull()
    assert ai.apply(app).isNull() and app.windowIcon().cacheKey() == QApplication.windowIcon().cacheKey()
    assert not _is_logo(app.windowIcon())
