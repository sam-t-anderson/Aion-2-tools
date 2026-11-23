"""The interfaces' own data as the native window and overlay read and write it (0.2.482): the app keeps it in its data
folder (``app/interface_store.py``), with what the web pages keep in their browser, so both interfaces find the same
choices. Until 0.2.482 the native window and the overlay each kept a settings file of their own (Qt's, in the user's
profile); what those held is copied to the app once, the first time either opens.

``store()`` is read as a Qt settings file is (``value`` and ``setValue``): the app's data is read once, as the window or
overlay opens, and kept up to date in memory; the changes go to the app off the interface's thread, one request after
another, and those made while a request is on its way go together in the next (an opacity dragged changes it at each
step, and the app writes its file for each request). Without the app (a test), the store keeps its values in memory
only.
"""
from __future__ import annotations

import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor

#: The mark the app keeps once the native settings files have been copied to it.
MOVED = "native-settings-moved"
#: Where the overlay's own choices are kept, before each key (its opacity, its metric).
OVERLAY = "native-overlay/"
_FILES = (("native-interface", ""), ("native-overlay", OVERLAY))       # Qt's settings files until 0.2.482


class _Shared:
    """The values of a process, shared by every store it opens, and the one worker that sends the changes."""

    def __init__(self):
        self.api = None
        self.values: dict[str, str] | None = None
        self.answered = False                        # whether the app gave its data as the window opened
        self.lock = threading.Lock()
        self.pool: ThreadPoolExecutor | None = None
        self.outbox: dict[str, str | None] = {}      # the changes not sent yet, by key: the latest of each
        self.sending = False                         # a request on its way, or about to be

    def load(self) -> dict[str, str]:
        with self.lock:
            if self.values is None:
                self.values, self.answered = {}, False
                if self.api is not None:
                    try:
                        kept = self.api.get("/api/interface")
                    except (OSError, ValueError, urllib.error.URLError):
                        kept = None
                    kept = kept.get("values") if isinstance(kept, dict) else None
                    if isinstance(kept, dict):
                        self.values = {k: v for k, v in kept.items() if isinstance(k, str) and isinstance(v, str)}
                        self.answered = True
            return self.values

    def change(self, changes: dict) -> None:
        values = self.load()
        with self.lock:
            for key, value in changes.items():
                if value is None:
                    values.pop(key, None)
                else:
                    values[key] = value
            if self.api is None:
                return
            self.outbox.update(changes)
            if self.sending:
                return                               # the request on its way takes these when it is done
            self.sending = True
            if self.pool is None:
                self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="interface-store")
            pool = self.pool
        try:
            pool.submit(self._send)
        except RuntimeError:                         # the process is closing: what it changed last is not kept
            with self.lock:
                self.sending = False

    def _send(self) -> None:
        while True:
            with self.lock:
                changes, self.outbox = self.outbox, {}
                if not changes:
                    self.sending = False
                    return
            try:
                self.api.post("/api/interface", {"set": changes})
            except (OSError, ValueError, urllib.error.URLError):
                pass                                 # the app is gone; the page goes on with what it shows


_shared = _Shared()


def _text(value) -> str:
    """A value as the store keeps it: a text, as a browser's storage and a Qt settings file keep theirs (a list, as a
    Qt settings file reads a value with commas in it, joined back)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


class InterfaceStore:
    """A view of the app's interface data, read and written as a Qt settings file is; ``prefix`` keeps a window's
    own keys apart (the overlay's)."""

    def __init__(self, prefix: str = "", shared: _Shared | None = None):
        self.prefix = prefix
        self.shared = shared or _shared

    def value(self, key: str, default=None, type=None):
        value = self.shared.load().get(self.prefix + key)
        if value is None:
            return default
        if type is None or type is str:
            return value
        if type is bool:
            return value.strip().lower() in ("1", "true", "yes", "on")
        if type is int:
            return int(float(value))
        return type(value)

    def setValue(self, key: str, value) -> None:
        self.shared.change({self.prefix + key: _text(value)})

    def remove(self, key: str) -> None:
        self.shared.change({self.prefix + key: None})

    def contains(self, key: str) -> bool:
        return self.prefix + key in self.shared.load()

    def allKeys(self) -> list[str]:
        return [k[len(self.prefix):] for k in self.shared.load() if k.startswith(self.prefix)]

    def sync(self) -> None:
        """Nothing to do: each change is on its way to the app as it is made."""


def connect(api, old=None) -> None:
    """The process's store read from the app at ``api`` (as the window or overlay opens), and the native interface's
    settings files until 0.2.482 (``old``: each with the prefix its keys take; Qt's files in the user's profile)
    copied to it the first time, where the app has none of a key. An app that does not answer gets nothing copied:
    what it has is not known."""
    _shared.api, _shared.values = api, None
    values = _shared.load()
    if api is None or not _shared.answered or MOVED in values:
        return
    if old is None:
        from PySide6.QtCore import QSettings
        old = [(QSettings(QSettings.IniFormat, QSettings.UserScope, "Aion 2 Calc", name), prefix)
               for name, prefix in _FILES]
    moved = {}
    for settings, prefix in old:
        for key in settings.allKeys():
            value = settings.value(key)
            if value is not None and prefix + key not in values:
                moved[prefix + key] = _text(value)
    moved[MOVED] = "1"
    _shared.change(moved)


def store(prefix: str = "") -> InterfaceStore:
    """The store the native interface keeps its choices in: the app's, once ``connect`` has read it."""
    return InterfaceStore(prefix)


def connected() -> bool:
    """Whether the store is the app's: ``connect`` has given it the app, where a test's store is kept in memory
    alone."""
    return _shared.api is not None
