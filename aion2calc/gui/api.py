"""The native windows' way into the app: its local API, the one the web pages call (0.2.413).

``AppApi`` sends one request at a time and answers with the decoded JSON. ``Poller`` asks for one path at an
interval off the interface's thread and hands each answer to it as a Qt signal, so a slow answer never freezes
a window; a poll still waiting when the next is due is not sent twice. ``Requests`` sends a window's one-off
requests (a button's action, 0.2.416) the same way, each answered under the name the window gave it. ``Job`` runs
one of the app's jobs (an optimization, 0.2.439) as app.js's ``runJob`` does: started, then read every 1.2 s.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import urllib.error
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, QTimer, Signal


def why(exc: BaseException) -> str:
    """What went wrong, as the web pages say it: the app's own ``error`` for a request it refused (the JSON of
    its answer), else the reason the connection gave."""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            message = json.loads(exc.read().decode("utf-8") or "{}").get("error")
        except (OSError, ValueError, AttributeError):
            message = None
        return str(message or f"HTTP {exc.code}")
    return str(getattr(exc, "reason", None) or exc)


class AppApi:
    """The app's local API at ``base`` (``http://127.0.0.1:8765/``)."""

    def __init__(self, base: str, timeout: float = 4.0):
        self.base = base.split("#", 1)[0].rstrip("/") + "/"
        self.timeout = timeout

    def url(self, path: str) -> str:
        return self.base + path.lstrip("/")

    def get(self, path: str, timeout: float | None = None) -> dict:
        with urllib.request.urlopen(self.url(path), timeout=timeout or self.timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def get_bytes(self, path: str, timeout: float | None = None) -> bytes:
        """``path``'s body as it comes (an image), not its JSON."""
        with urllib.request.urlopen(self.url(path), timeout=timeout or self.timeout) as response:
            return response.read()

    def post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        request = urllib.request.Request(self.url(path), json.dumps(payload).encode("utf-8"),
                                         {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
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

    def set_interval(self, interval_ms: int) -> None:
        """Ask at another pace from the next poll on (the overlay reads the meter less often out of a fight)."""
        if self._timer.interval() != interval_ms:
            self._timer.setInterval(interval_ms)

    def poll(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            self._pool.submit(self._ask)
        except RuntimeError:                     # stopped: its window has closed
            self._busy = False

    def _ask(self) -> None:
        try:
            answer = self.api.get(self.path)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self._busy = False
            self.failed.emit(str(exc))            # a signal emitted here is delivered on the interface's thread
            return
        self._busy = False
        self.answered.emit(answer)


class Requests(QObject):
    """A window's one-off requests (a button's action), sent off the interface's thread in the order asked. Each
    is answered as ``replied(name, answer)`` or ``failed(name, why)``, ``name`` being what the window called it.
    Connect them to a window's own methods: those run on the interface's thread. ``timeout`` is how long each may
    take to answer when not the API's own few seconds: a page whose requests can take a while (My Character's search on
    the official site, a large recording read, 0.2.441) waits as a browser would."""

    replied = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, api: AppApi, parent: QObject | None = None, timeout: float | None = None):
        super().__init__(parent)
        self.api, self.timeout = api, timeout
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gui-call")

    def get(self, name: str, path: str) -> None:
        self._submit(name, path, None)

    def get_bytes(self, name: str, path: str) -> None:
        """As ``get``, answered with the body's bytes (an image) rather than its JSON."""
        self._submit(name, path, None, raw=True)

    def post(self, name: str, path: str, payload: dict) -> None:
        self._submit(name, path, payload)

    def _submit(self, name: str, path: str, payload: dict | None, raw: bool = False) -> None:
        try:
            self._pool.submit(self._send, name, path, payload, raw)
        except RuntimeError:                     # stopped: its window has closed, and nothing waits for the answer
            pass

    def stop(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _send(self, name: str, path: str, payload: dict | None, raw: bool = False) -> None:
        wait = {} if self.timeout is None else {"timeout": self.timeout}
        try:
            if raw:
                answer = self.api.get_bytes(path, **wait)
            else:
                answer = self.api.get(path, **wait) if payload is None else self.api.post(path, payload, **wait)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self.failed.emit(name, why(exc))
            return
        self.replied.emit(name, answer)


class Job(QObject):
    """One of the app's jobs, as app.js's ``runJob`` runs it: ``start`` sends its request (answered with the job's id),
    then the job is read from ``/api/jobs/<id>`` every 1.2 s; each reading's log comes as ``logged``, then its result
    as ``done`` or its error (or why a request failed) as ``failed``. A ``patient`` job reads again 2.5 s after a
    reading that failed, as My Character's ``pollOpt`` keeps polling through a passing error. One job at a time."""

    logged = Signal(list)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, api: AppApi, parent: QObject | None = None, interval_ms: int = 1200, patient: bool = False):
        super().__init__(parent)
        self.interval_ms, self.patient = interval_ms, patient
        self.requests = Requests(api, self)
        self.requests.replied.connect(self._replied)
        self.requests.failed.connect(self._failed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._read)
        self.id, self.running, self.turn = "", False, 0

    def start(self, path: str, body: dict) -> None:
        self.turn += 1                                     # a job started anew: what an earlier one answers is dropped
        self.id, self.running = "", True
        self.requests.post(f"start:{self.turn}", path, body)

    def _read(self) -> None:
        self.requests.get(f"read:{self.turn}", "/api/jobs/" + urllib.parse.quote(self.id, safe=""))

    def _replied(self, name: str, answer) -> None:
        kind, _, turn = name.partition(":")
        if turn != str(self.turn) or not self.running:
            return
        answer = answer if isinstance(answer, dict) else {}
        if kind == "start":
            self.id = str(answer.get("job") or "")
            if not self.id:
                self._end("The app did not start the job.")
                return
            self.timer.start(self.interval_ms)
            return
        log = answer.get("log")
        self.logged.emit(list(log) if isinstance(log, list) else [])
        if answer.get("status") == "done":
            self.running = False
            self.done.emit(answer.get("result"))
        elif answer.get("status") == "error":
            self._end(str(answer.get("error") or ""))
        else:
            self.timer.start(self.interval_ms)

    def _failed(self, name: str, why: str) -> None:
        kind, _, turn = name.partition(":")
        if turn != str(self.turn) or not self.running:
            return
        if self.patient and kind == "read":
            self.timer.start(max(self.interval_ms, 2500))         # a passing error: read again a little later
            return
        self._end(why)

    def _end(self, why: str) -> None:
        self.running = False
        self.failed.emit(why)

    def stop(self) -> None:
        self.timer.stop()
        self.running = False
        self.requests.stop()
