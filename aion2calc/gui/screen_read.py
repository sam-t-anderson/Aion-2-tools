"""Reading the game's screen into a page (0.2.442), as pages/screen-read.js's ``screenReadPanel`` does: the Genus
Insight panel (or a page of the Title window), read by the text recognition built into Windows, for the player to
check and save. Three ways: the game screen after a three-second countdown (time to switch to the game), a screenshot
chosen or pasted (Ctrl+V on the row), and the Read the game screen hotkey pressed in the game, whose reads the row
picks up every 2 s while its page is shown. Nothing is saved to a character here.
"""
from __future__ import annotations

import base64
import html
import os
import time
from typing import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import character as c
from .api import Requests
from .timers_page import Fold

#: The newest read each kind of panel has taken in this run of the app: a hotkey read made while the app was in the
#: background is taken once, by the first panel of its kind the player opens.
TAKEN = {"genus": 0, "titles": 0}
POLL_MS = 2000
DELAY_S = 3
MOST_BYTES = 24 * 1024 * 1024
WAIT_S = 60                                          # a read waits its countdown, then the recognition
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".bmp": "image/bmp", ".webp": "image/webp"}


def what(kind: str) -> str:
    return "the Genus Insight panel" if kind == "genus" else "a page of the Title window"


def note(kind: str) -> str:
    return (f"Open {what(kind)} in the game, press <b>Read the game screen</b> and switch to the game within 3 seconds, "
            "or press the <b>Read the game screen</b> hotkey in the game (Settings → Hotkeys). A screenshot works too: "
            "choose it, or click this box and paste it (Ctrl+V).")


def read_text(record: dict) -> tuple[str, list[str]]:
    """What a read says (``screenReadText``, rich text), and what was read when nothing was recognised."""
    lines = record.get("lines") if isinstance(record.get("lines"), list) else []
    if record.get("kind") == "genus":
        checks = len([line for line in lines if isinstance(line, dict) and c._truthy(line.get("check"))])
        level = f" Lv {html.escape(c.esc_text(record.get('level')))}" if c._truthy(record.get("level")) else " (the level was not read)"
        return (f"Read {html.escape(c.esc_text(record.get('genus')))} Insight{level}: {len(lines)} line"
                f"{'' if len(lines) == 1 else 's'}{f', {checks} to check' if checks else ''}.", [])
    if record.get("kind") == "titles":
        titles = record.get("titles") if isinstance(record.get("titles"), list) else []
        only = record.get("unacquired_only")
        box = "ticked" if only is True else "not ticked" if only is False else "not seen"
        return (f"Read a page of the Title window: {len(titles)} title{'' if len(titles) == 1 else 's'}, "
                f"“Show unacquired titles only” {box}.", [])
    notes = record.get("notes") if isinstance(record.get("notes"), list) else []
    words = record.get("error") or (notes[0] if notes else None) or "Nothing was recognised on the screen."
    seen = record.get("seen") if isinstance(record.get("seen"), list) else []
    return html.escape(c.esc_text(words)), [c.esc_text(x) for x in seen]


def other_text(kind: str) -> str:
    """What a read of the other kind of panel says."""
    return ("That is a page of the Title window: it is listed under <b>Titles you own</b> on Gear &amp; Advice."
            if kind == "genus" else "That is the Genus Insight panel: read it under <b>Genus Insight</b>.")


def data_url(path: str) -> str:
    """A screenshot file as the page sends it (``readAsDataURL``)."""
    with open(path, "rb") as handle:
        body = handle.read()
    kind = TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    return f"data:{kind};base64,{base64.b64encode(body).decode('ascii')}"


class ScreenRead(QFrame):
    """A row of ways to read the game into the page (``screenReadPanel``); ``on_read(record)`` gets each read of
    ``kind`` ("genus" or "titles")."""

    def __init__(self, api, kind: str, on_read: Callable[[dict], object], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("screenRead")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"Read {what(kind)} from the game. Paste a screenshot here.")
        self.kind, self.on_read = kind, on_read
        self.other = "titles" if kind == "genus" else "genus"
        self.taken: set = set()
        self.opened = time.time()
        self.requests = Requests(api, self, timeout=WAIT_S) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(6)
        row = QWidget()
        row.setObjectName("plain")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        title = QLabel("Read from the game")
        title.setObjectName("strong")
        line.addWidget(title)
        self.button = QPushButton("Read the game screen")
        self.button.setObjectName("small")
        self.button.clicked.connect(lambda _checked=False: self.read_screen())
        line.addWidget(self.button)
        self.choose = QPushButton("Choose a screenshot…")
        self.choose.setObjectName("small")
        self.choose.clicked.connect(lambda _checked=False: self.choose_file())
        line.addWidget(self.choose)
        line.addStretch(1)
        column.addWidget(row)
        hint = QLabel(note(kind))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.RichText)
        column.addWidget(hint)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setAccessibleName("Read status")
        column.addWidget(self.status)
        self.seen = Fold("What was read")
        self.seen_text = QLabel("")
        self.seen_text.setTextFormat(Qt.PlainText)
        self.seen_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.seen.add(self.seen_text)
        self.seen.hide()
        column.addWidget(self.seen)
        self.left = 0
        self.countdown = QTimer(self)
        self.countdown.setInterval(1000)
        self.countdown.timeout.connect(self._tick)
        self.poller = QTimer(self)
        self.poller.setInterval(POLL_MS)
        self.poller.timeout.connect(self.poll)
        self.available, self.polling = True, False

    # ---------------------------------------------------------------- what it says
    def say(self, words: str, seen: list[str] | None = None) -> None:
        self.status.setText(words)
        self.seen_text.setText("\n".join(seen or []))
        self.seen.setVisible(bool(seen))

    def take(self, record) -> None:
        if not isinstance(record, dict) or record.get("id") in self.taken:
            return
        self.taken.add(record.get("id"))
        if record.get("kind") == self.kind:
            TAKEN[self.kind] = max(TAKEN[self.kind], c.js_number(record.get("id")) if record.get("id") is not None else 0)
            self.on_read(record)
            self.say(*read_text(record))
        elif record.get("kind") == self.other:
            self.say(other_text(self.kind))
        else:
            self.say(*read_text(record))

    # ---------------------------------------------------------------- reading
    def read_screen(self) -> None:
        """The game screen, after a countdown to switch to it."""
        self.button.setEnabled(False)
        self.left = DELAY_S
        self._tick(first=True)
        self.countdown.start()
        self._send({"action": "read", "delay": DELAY_S}, f"Reading in {DELAY_S}… switch to the game now.")

    def _tick(self, first: bool = False) -> None:
        if not first:
            self.left -= 1
        self.say(f"Reading in {self.left}… switch to the game now." if self.left > 0 else "Reading…")
        if self.left <= 0:
            self.countdown.stop()

    def choose_file(self) -> None:
        path, _kind = QFileDialog.getOpenFileName(self, "Choose a screenshot", "",
                                                  "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.read_file(path)

    def read_file(self, path: str) -> None:
        try:
            if os.path.getsize(path) > MOST_BYTES:
                self.say("That screenshot is larger than 24 MB.")
                return
            image = data_url(path)
        except OSError:
            self.say("The screenshot could not be opened.")
            return
        self._send({"action": "image", "image": image}, "Reading the screenshot…")

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Paste):
            image = QGuiApplication.clipboard().image()
            if not image.isNull():
                data = QByteArray()
                buffer = QBuffer(data)
                buffer.open(QIODevice.WriteOnly)
                image.save(buffer, "PNG")
                self._send({"action": "image", "image": "data:image/png;base64," + base64.b64encode(bytes(data)).decode("ascii")},
                           "Reading the screenshot…")
                event.accept()
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self.setFocus(Qt.MouseFocusReason)            # click the box, then paste
        super().mousePressEvent(event)

    def _send(self, body: dict, waiting: str) -> None:
        self.say(waiting)
        if self.requests is not None:
            self.requests.post("read", "/api/screen-read", body)

    # ---------------------------------------------------------------- the hotkey's reads
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.available:
            self.poll()
            self.poller.start()

    def hideEvent(self, event) -> None:
        self.poller.stop()
        super().hideEvent(event)

    def poll(self) -> None:
        """The hotkey's reads since the newest taken (one asking at a time)."""
        if self.requests is not None and not self.polling:
            self.polling = True
            self.requests.get("poll", f"/api/screen-read?since={c.js_string(TAKEN[self.kind])}")

    def _replied(self, name: str, answer) -> None:
        if name == "read":
            self.countdown.stop()
            self.button.setEnabled(self.available)
            self.take(answer)
        elif name == "poll":
            self.polling = False
            if not isinstance(answer, dict):
                return
            if not answer.get("available"):
                self.available = False
                self.poller.stop()
                self.button.setEnabled(False)
                self.choose.setEnabled(False)
                self.say(html.escape(c.esc_text(answer.get("message"))))
                return
            for record in answer.get("reads") if isinstance(answer.get("reads"), list) else []:
                if not isinstance(record, dict):
                    continue
                at = record.get("at")
                if record.get("kind") == self.kind or (record.get("kind") is None and record.get("source") == "hotkey"
                                                       and isinstance(at, (int, float)) and at >= self.opened):
                    self.take(record)
                if isinstance(record.get("id"), (int, float)):
                    TAKEN[self.kind] = max(TAKEN[self.kind], record["id"])

    def _failed(self, name: str, why: str) -> None:
        if name == "poll":
            self.polling = False                      # asked again at the next turn, as the web page's does
        elif name == "read":
            self.countdown.stop()
            self.button.setEnabled(self.available)
            self.say(html.escape("Not read: " + why))
