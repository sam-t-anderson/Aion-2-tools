"""The quiet update in the native window (0.2.493): app.js's ``syncPill`` (its release part) and ``updateBar``.

The window asks the app for its status (``/api/status``) as the web pages' top bar does: first asking for a fresh
release check, then every 20 s (each second while an update downloads, every 2 s while a check runs and 2.5 s while
the database updates). A newer release downloads in the background (the app's own doing since 0.2.353). The bar at
the window's bottom left shows its progress, then **Update ready** with **Update now** (the app closes and its
installer opens) and **Update when the app closes**. Where nothing downloads (a copy run from source, updates turned
off, or a download that failed), the window names the newer release instead, as a link to its page.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from . import theme
from .api import AppApi, Requests
from .combat import js_string
from .results import _dict, _truthy

# ------------------------------------------------------------------ app.js's words
UPDATE_NOW, SHOW_DOWNLOAD = "Update now", "Show the download"
ON_CLOSE = "Update when the app closes"
CLOSING = "Aion 2 Calc is closing. The installer will open in a moment."
INSTALLS_ON_CLOSE, WAITS = "The update installs when the app closes", "The update waits for Update now"
FAILED = "Update failed: "
#: What Update now's answer says (``UPDATE_SAID``); any other status is said as it is.
UPDATE_SAID = {
    "downloaded": "Update downloaded. Open the updates folder to install it.",
    "download-failed": "The update download failed.",
    "check-failed": "Could not reach GitHub for the update. Try again in a minute.",
    "up-to-date": "Already up to date.",
    "launch-failed": "The installer helper did not start. Your app is still running; open the updates folder to run "
                     "the setup file.",
}
#: how long the next status waits (``syncPill``'s timeout), in milliseconds
SYNCING_MS, DOWNLOADING_MS, CHECKING_MS, IDLE_MS = 2500, 1000, 2000, 20000
UPDATE_TIMEOUT = 900                     # Update now downloads and checks the installer first when it is not ready
PROGRESS_WIDTH = 160                     # ``.updbar progress { width: 160px }``


def _words(value) -> str:
    """``${value}``: undefined and null as JavaScript writes them."""
    return "undefined" if value is None else js_string(value)


def poll_ms(s) -> int:
    """When the window asks for the status again: sooner while the database updates, an update downloads or a release
    check runs. A status without the database's count while it does not update is one the web page's line cannot read
    (``s.db.items`` throws): asked for again in 20 s, as after a refusal."""
    s = _dict(s)
    if _truthy(_dict(s.get("sync")).get("running")):
        return SYNCING_MS
    if s.get("db") is None:
        return IDLE_MS
    if _dict(s.get("update_download")).get("state") == "downloading":
        return DOWNLOADING_MS
    if not _truthy(s.get("update")) and _truthy(_dict(s.get("update_state")).get("checking")):
        return CHECKING_MS
    return IDLE_MS


def bar_state(s) -> dict | None:
    """What the bar shows (``updateBar``): the download's progress, or the update ready with what installs it; None
    while it hides."""
    s = _dict(s)
    d = _dict(s.get("update_download"))
    if d.get("state") == "downloading":
        total, received = d.get("total"), d.get("received")
        pct = 0
        if _truthy(total) and isinstance(total, (int, float)) and isinstance(received, (int, float)):
            share = 100 * received / total
            pct = min(100, math.floor(share)) if math.isfinite(share) else 0
        return {"kind": "downloading", "words": f"Downloading version {_words(d.get('version'))}…", "pct": pct,
                "key": "downloading"}
    if d.get("state") == "ready":
        installer = d.get("kind") == "installer"
        return {"kind": "ready", "words": f"Update ready: version {_words(d.get('version'))}",
                "button": UPDATE_NOW if installer else SHOW_DOWNLOAD, "installer": installer,
                "on_close": s.get("update_on_close") is not False, "key": f"ready:{_words(d.get('version'))}"}
    return None


def available(s, quiet: bool) -> dict | None:
    """The newer release named where nothing downloads (the header's ``#update``): its words and its page."""
    update = _dict(_dict(s).get("update"))
    if quiet or not update:
        return None
    return {"words": f"Version {_words(update.get('version'))} available", "url": _words(update.get("url"))}


def said(status) -> str:
    """What Update now's answer is said as (``UPDATE_SAID[r.status] || r.status``)."""
    if isinstance(status, str) and status in UPDATE_SAID:
        return UPDATE_SAID[status]
    return _words(status)


# ------------------------------------------------------------------ the bar
class UpdateBar(QFrame):
    """``#updbar``: at the bottom left of the window, over the page. ``update_now`` and ``on_close`` are its button's
    and its check box's actions."""

    def __init__(self, parent: QWidget, update_now, on_close):
        super().__init__(parent)
        self.setObjectName("updbar")
        self.setAccessibleName("Update")
        self.update_now, self.on_close = update_now, on_close
        self.key: str | None = None
        self.text = QLabel()
        self.progress: QProgressBar | None = None
        self.pct: QLabel | None = None
        self.button: QPushButton | None = None
        self.close_box: QCheckBox | None = None
        self.line = QHBoxLayout(self)
        self.line.setContentsMargins(12, 8, 12, 8)
        self.line.setSpacing(10)
        self.hide()

    def show_state(self, state: dict | None) -> bool:
        """The bar as the status has it; True while it shows."""
        if state is None:
            self.hide()
            self.key = None
            return False
        if state["key"] != self.key:                        # drawn afresh for another state or version
            self._build(state)
        self.text.setText(state["words"])
        if state["kind"] == "downloading":
            self.progress.setValue(state["pct"])
            self.pct.setText(f"{state['pct']}%")
        elif self.close_box is not None and not self.close_box.hasFocus():
            self.close_box.blockSignals(True)
            self.close_box.setChecked(state["on_close"])
            self.close_box.blockSignals(False)
        self.place()
        self.show()
        self.raise_()
        return True

    def _build(self, state: dict) -> None:
        while self.line.count():
            item = self.line.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.text:
                widget.hide()
                widget.setParent(None)                       # gone at once, not drawn until deleted
                widget.deleteLater()
        self.progress = self.pct = self.button = self.close_box = None
        self.key = state["key"]
        self.line.addWidget(self.text)
        if state["kind"] == "downloading":
            self.progress = QProgressBar()
            self.progress.setRange(0, 100)
            self.progress.setTextVisible(False)
            self.progress.setFixedWidth(PROGRESS_WIDTH)
            self.progress.setAccessibleName("Update download")
            self.pct = QLabel()
            self.pct.setObjectName("small")
            self.line.addWidget(self.progress)
            self.line.addWidget(self.pct)
        else:
            self.button = QPushButton(state["button"])
            self.button.setObjectName("primary")
            self.button.clicked.connect(lambda _checked=False: self.update_now())
            self.line.addWidget(self.button)
            if state["installer"]:
                self.close_box = QCheckBox(ON_CLOSE)
                self.close_box.setChecked(state["on_close"])
                self.close_box.toggled.connect(self.on_close)
                self.line.addWidget(self.close_box)
        for i in range(self.line.count()):                  # shown now, so the bar's size counts them
            self.line.itemAt(i).widget().show()
        self.adjustSize()

    def place(self) -> None:
        """``left: 12px; bottom: 12px``, no wider than the window allows."""
        window = self.parentWidget()
        self.setMaximumWidth(max(120, min(860, window.width() - 24)))
        self.adjustSize()
        self.move(12, max(0, window.height() - self.height() - 12))


def stylesheet() -> str:
    c = theme.COLORS
    return f"""
        QFrame#updbar {{ border: 1px solid {c['line']}; border-radius: 8px; background: {theme.css('panel2')}; }}
        QFrame#updbar QLabel, QFrame#updbar QCheckBox {{ background: transparent; }}
        QFrame#updbar QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b5523,
            stop:1 #3f3215); border: 1px solid {theme.css('frame_hi')}; color: #fff3cf; border-radius: 4px;
            padding: 5px 12px; font-weight: 600; }}
        QLabel#updchip {{ background: rgba(233, 203, 128, 0.12); border: 1px solid {theme.css('frame')};
            border-radius: 10px; padding: 2px 10px; margin: 6px 10px 0 10px; }}
        """


# ------------------------------------------------------------------ the status, asked for again and again
class UpdateWatch(QObject):
    """The window's status asked for (``syncPill``): ``changed(status)`` each time it comes; ``said(words)`` for the
    message Update now's answer, or the check box's, gives; ``closing()`` once the app closes for its installer."""

    changed = Signal(object)
    said = Signal(str)
    closing = Signal()

    def __init__(self, api: AppApi | None, parent: QObject | None = None):
        super().__init__(parent)
        self.api = api
        self.first = True                                  # the first asks for a fresh release check
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.ask)
        self.requests = Requests(api, self) if api is not None else None
        self.slow = Requests(api, self, timeout=UPDATE_TIMEOUT) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
            self.slow.replied.connect(self._replied)
            self.slow.failed.connect(self._failed)

    def start(self) -> None:
        if self.requests is not None:
            self.ask()

    def stop(self) -> None:
        self.timer.stop()
        if self.requests is not None:
            self.requests.stop()
            self.slow.stop()

    def ask(self) -> None:
        if self.requests is None:
            return
        self.requests.get("status", "/api/status" + ("?fresh=1" if self.first else ""))
        self.first = False

    def update_now(self) -> None:
        """Update now (``updateNow``): the app installs the update (closing for its installer), or says why not."""
        if self.slow is not None:
            self.slow.post("update", "/api/update", {})

    def on_close(self, checked: bool) -> None:
        """Update when the app closes: kept by the app (``update_on_close``)."""
        if self.requests is not None:
            self.requests.post(f"on_close:{int(bool(checked))}", "/api/ui", {"update_on_close": bool(checked)})

    def _replied(self, name: str, answer) -> None:
        if name == "status":
            self.changed.emit(answer)
            self.timer.start(poll_ms(answer))
        elif name == "update":
            status = _dict(answer).get("status")
            if status == "launching":
                self.stop()
                self.closing.emit()
            else:
                self.said.emit(said(status))
        elif name.startswith("on_close:"):
            self.said.emit(INSTALLS_ON_CLOSE if name.endswith(":1") else WAITS)

    def _failed(self, name: str, why: str) -> None:
        if name == "status":
            self.timer.start(IDLE_MS)
        elif name == "update":
            self.said.emit(FAILED + why)
        elif name.startswith("on_close:"):
            self.said.emit(why)
