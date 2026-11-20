"""The native windows' way into the app: its local API, the one the web pages call (0.2.413).

``AppApi`` sends one request at a time and answers with the decoded JSON. ``Poller`` asks for one path at an
interval off the interface's thread and hands each answer to it as a Qt signal, so a slow answer never freezes
a window; a poll still waiting when the next is due is not sent twice.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, QTimer, Signal


class AppApi:
    """The app's local API at ``base`` (``http://127.0.0.1:8765/``)."""

    def __init__(self, base: str, timeout: float = 4.0):
        self.base = base.split("#", 1)[0].rstrip("/") + "/"
        self.timeout = timeout

    def url(self, path: str) -> str:
        return self.base + path.lstrip("/")

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.url(path), timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(self.url(path), json.dumps(payload).encode("utf-8"),
                                         {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")


class Poller(QObject):
    """Ask the app for ``path`` every ``interval_ms`` and emit ``answered`` (the JSON) or ``failed`` (why)."""

    answered = Signal(object)
    failed = Signal(str)

    def __init__(self, api: AppApi, path: str, interval_ms: int, parent: QObject | None = None):
        super().__init__(parent)
        self.api, self.path = api, path
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gui-poll")
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)

    def start(self) -> None:
        self.poll()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def poll(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._pool.submit(self._ask)

    def _ask(self) -> None:
        try:
            answer = self.api.get(self.path)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self._busy = False
            self.failed.emit(str(exc))            # a signal emitted here is delivered on the interface's thread
            return
        self._busy = False
        self.answered.emit(answer)
