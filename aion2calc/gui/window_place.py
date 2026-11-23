"""The native window's place kept between launches (0.2.504): its size, its position, the screen it is on and whether
it is maximized, as Qt keeps them (``saveGeometry``), in the interfaces' data under ``native-window/place``.

The window opens there again (``restore``); where the screen it was on is gone, Qt puts it on one that is there. Its
place is kept a moment after each move, resize or maximize, and again as the window closes, where it changed since.
Keeping it only as the window closes would not do: **Quit** stops the app before its window closes, and the
interfaces' data goes to the app off the interface's thread, so a place kept only then would be lost.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QObject, QTimer

KEY = "native-window/place"
#: How long after its last move, resize or maximize the window's place is kept.
SAVE_MS = 600


class WindowPlace(QObject):
    """``window``'s place, kept in ``store`` (a store as ``interface.store()`` gives) under ``key``."""

    def __init__(self, window, store, key: str = KEY, save_ms: int | None = None):
        super().__init__(window)
        self.window, self.store, self.key = window, store, key
        self.kept: str | None = None                       # the place last kept (or put back), not kept again
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(SAVE_MS if save_ms is None else save_ms)
        self.timer.timeout.connect(self.save)
        window.installEventFilter(self)

    def restore(self) -> bool:
        """The window put back where it was left; False where no place is kept, or none Qt can read."""
        kept = self.store.value(self.key, "")
        if not isinstance(kept, str) or not kept:
            return False
        try:
            data = QByteArray.fromBase64(kept.encode("ascii"))
        except UnicodeEncodeError:
            return False
        if data.isEmpty() or not self.window.restoreGeometry(data):
            return False
        self.kept = kept
        return True

    def eventFilter(self, watched, event) -> bool:
        if watched is self.window:
            kind = event.type()
            if kind in (QEvent.Move, QEvent.Resize, QEvent.WindowStateChange):
                self.timer.start()
            elif kind == QEvent.Close:
                self.timer.stop()
                self.save()                                # the last change, kept before the window goes
        return False

    def save(self) -> None:
        """The window's place kept, while it is shown and where it has changed."""
        if not self.window.isVisible():
            return
        place = bytes(self.window.saveGeometry().toBase64()).decode("ascii")
        if place != self.kept:
            self.kept = place
            self.store.setValue(self.key, place)
