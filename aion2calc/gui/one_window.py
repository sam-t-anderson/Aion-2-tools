"""One app window at a time (0.2.505): the app opened again while its native window is open (the tray's **Open Aion 2
Calc**, the **Open the app window** and **Open the Settings page** hotkeys, the app started a second time) brings that
window forward, on the page asked for, where each of them opened a second window beside it.

The window's process listens on a local socket named after the app's address (``QLocalServer``: a named pipe on
Windows, a socket file elsewhere), for its own user alone. A window's process started while one listens hands it the
page its address names and ends without drawing a window of its own. One that finds none listening, or none that
answers in time, opens its window as before and listens in turn. A window about to close (it says the app stopped, or
that the app closes for its installer) answers that it shows none, and the new process opens its window; where that
one's name is still taken (on Windows, until the closing window's process ends), it tries again every two seconds.
"""
from __future__ import annotations

import re
import sys
import urllib.parse

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

#: How long a new window's process waits for the open window, to connect and then for its answer.
WAIT_MS = 2000
SHOWN, NONE = b"shown\n", b"none\n"
#: The longest request read (a page's address, then its end of line); a longer one is let go unanswered.
LONGEST = 4096
#: How often a window whose name is still taken tries to listen again.
RETRY_MS = 2000


def name(base: str) -> str:
    """The socket's name for the app at ``base``: its host and port, so one app's window never takes another's."""
    where = urllib.parse.urlsplit(base).netloc or base
    return "aion2calc-window-" + (re.sub(r"[^0-9A-Za-z]+", "-", where).strip("-") or "app")


def hand_over(server: str, page: str, wait_ms: int = WAIT_MS) -> bool:
    """Whether the window listening under ``server`` took ``page`` (an address's fragment: ``/settings``, or empty for
    the page it shows) and came forward. False where none listens, where it shows no window that stays, or where it
    does not answer within ``wait_ms``."""
    socket = QLocalSocket()
    socket.connectToServer(server)
    if not socket.waitForConnected(wait_ms):
        return False
    _let_it_come_forward()
    socket.write(page.replace("\n", " ").encode("utf-8")[:LONGEST - 1] + b"\n")
    socket.waitForBytesWritten(wait_ms)
    answer = b""
    while not answer.endswith(b"\n") and len(answer) < len(SHOWN) and socket.waitForReadyRead(wait_ms):
        answer += bytes(socket.readAll())
    socket.abort()
    return answer == SHOWN


def _let_it_come_forward() -> None:
    """On Windows, the open window is let take the foreground (``AllowSetForegroundWindow``): this process, started
    for a click or a hotkey, may hand that on, and a window that may not take it only flashes on the taskbar."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)        # ASFW_ANY
    except (AttributeError, OSError):
        pass


class Listening(QObject):
    """The open window's side, listening under ``server``: each request read, ``come_forward(page)`` asked to bring
    a window forward on that page (False where it shows none that stays), and the answer sent back."""

    def __init__(self, server: str, come_forward, parent=None):
        super().__init__(parent)
        self.name, self.come_forward = server, come_forward
        self.server = QLocalServer(self)
        # for its own user alone: Qt makes such a socket apart and puts it in place, so a socket file left behind by
        # a window's process that ended without a word is replaced (none answered on it as this window started)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._connected)
        self.retry = QTimer(self)
        self.retry.setInterval(RETRY_MS)
        self.retry.timeout.connect(self._listen)
        self._listen()

    @property
    def listening(self) -> bool:
        return self.server.isListening()

    def _listen(self) -> None:
        if self.server.listen(self.name):
            self.retry.stop()
        elif not self.retry.isActive():
            self.retry.start()                       # the name still taken: tried again a moment later

    def close(self) -> None:
        """No more requests taken (the window's process ending)."""
        self.retry.stop()
        self.server.close()

    def _connected(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnected.connect(socket.deleteLater)
            read = bytearray()
            socket.readyRead.connect(lambda socket=socket, read=read: self._read(socket, read))
            if socket.bytesAvailable():
                self._read(socket, read)

    def _read(self, socket, read: bytearray) -> None:
        if socket.state() != QLocalSocket.ConnectedState:
            return                                   # answered, or let go
        read.extend(bytes(socket.readAll()))
        if b"\n" not in read:
            if len(read) >= LONGEST:
                socket.abort()                       # no request that long: let go unanswered
                socket.deleteLater()
            return
        page = bytes(read).split(b"\n", 1)[0].decode("utf-8", "replace")
        read.clear()
        shown = False
        try:
            shown = bool(self.come_forward(page))
        finally:
            socket.write(SHOWN if shown else NONE)
            socket.disconnectFromServer()
