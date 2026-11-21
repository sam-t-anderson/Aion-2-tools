"""The movement replay's drawing and controls (combat-review.js ``replay``'s SVG and its buttons), in the native
interface since 0.2.468; its model is ``combat_replay``.

- **The arena** (``.cr-arena``): 320 px tall across the width, its 100 × 100 view in the middle (``xMidYMid meet``) on
  a faint ground. The boss room is behind the tokens, then each token's trail and the token. The tip of whatever is
  under the pointer shows, as the SVG's ``title`` does.
- **The controls**: Play and Pause, Rewind, the speed (kept), the time slider and its clock, and the arena's shape
  (kept). At 1× the replay plays the fight in real seconds, on a 16 ms timer in place of the web page's animation
  frames.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QComboBox, QLabel, QSlider, QToolTip, QVBoxLayout, QWidget

from . import combat_replay as rp
from . import theme
from .chrome import FlowLayout
from .combat_saved import _button, _head, _label
from .combat import js_string

GROUND = QColor(136, 136, 136, 34)       # ``background: #8882``
TEXT = QColor(theme.COLORS["text"])      # ``currentColor``
HEIGHT = 320                             # ``.cr-arena { height: 320px }``
SCRUB_MOST = 500                         # ``[data-scrub] { width: min(50%, 500px) }``


def _with(colour: QColor | str, alpha: float) -> QColor:
    shade = QColor(colour)
    shade.setAlphaF(alpha)
    return shade


class Arena(QWidget):
    """The replay's arena (``.cr-arena``): the room and the tokens at the moment shown."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.tokens: list[dict] = []
        self.room: dict | None = None             # the arena drawn: its shape, and its middle and radius in view units
        self.setFixedHeight(HEIGHT)
        self.setAccessibleName("Recorded positions")

    def sizeHint(self) -> QSize:
        return QSize(HEIGHT, HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, HEIGHT)

    def view(self) -> tuple[float, float, float]:
        """Where the 100-unit view sits (``preserveAspectRatio="xMidYMid meet"``): its left, its top, and a unit's
        pixels."""
        unit = min(self.width(), self.height()) / 100
        return (self.width() - 100 * unit) / 2, (self.height() - 100 * unit) / 2, unit

    def show_moment(self, tokens: list[dict], room: dict | None) -> None:
        self.tokens, self.room = tokens, room
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), GROUND)
        left, top, unit = self.view()
        painter.translate(left, top)
        painter.scale(unit, unit)
        a = self.room
        if a is not None:                                            # ``.cr-room``
            painter.setPen(self._pen(_with(TEXT, 0.6), 0.6))
            painter.setBrush(_with(TEXT, 0.06))
            if a["shape"] == "circle":
                painter.drawEllipse(QPointF(a["x"], a["y"]), a["r"], a["r"])
            else:
                painter.drawRect(QRectF(a["x"] - a["r"], a["y"] - a["r"], 2 * a["r"], 2 * a["r"]))
        for token in self.tokens:
            if token["trail"]:
                painter.setPen(self._pen(_with(token["colour"], 0.35), 0.6))
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in token["trail"]]))
            if token["ring"]:                                        # the recording player: a white dashed edge
                pen = self._pen(QColor("#ffffff"), 0.5)
                pen.setDashPattern([2, 2])                           # ``stroke-dasharray="1 1"`` in pen widths
                painter.setPen(pen)
            else:
                painter.setPen(Qt.NoPen)
            painter.setBrush(_with(token["colour"], token["opacity"]))
            painter.drawEllipse(QPointF(token["x"], token["y"]), token["radius"], token["radius"])
        painter.end()

    @staticmethod
    def _pen(colour: QColor, width: float) -> QPen:
        pen = QPen(colour, width)
        pen.setCapStyle(Qt.FlatCap)                                  # SVG's butt ends and mitred corners
        pen.setJoinStyle(Qt.MiterJoin)
        return pen

    def tip_at(self, x: float, y: float) -> str:
        """The tip under a point of the widget: the topmost token's, else the arena's."""
        left, top, unit = self.view()
        vx, vy = (x - left) / unit, (y - top) / unit
        for token in reversed(self.tokens):
            if math.hypot(vx - token["x"], vy - token["y"]) <= token["radius"] + (0.25 if token["ring"] else 0):
                return token["tip"]
        a = self.room
        if a is not None:
            edge = a["r"] + 0.3                                      # the edge's half width
            inside = (math.hypot(vx - a["x"], vy - a["y"]) <= edge if a["shape"] == "circle"
                      else abs(vx - a["x"]) <= edge and abs(vy - a["y"]) <= edge)
            if inside:
                return rp.ARENA_TIP
        return ""

    def event(self, event) -> bool:
        if event.type() == QEvent.ToolTip:
            tip = self.tip_at(event.pos().x(), event.pos().y())
            if tip:
                QToolTip.showText(event.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class ReplayPanel(QWidget):
    """The replay with its controls (``replay``'s box): its heading and note, Play and Rewind, the speed, the time
    slider and its clock, the arena's shape, and the arena. ``store`` keeps the speed and the shape for every log."""

    def __init__(self, replay: rp.Replay, store, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("plain")
        self.replay, self.store = replay, store
        self.clock = 0.0                          # the replay's own time: the slider's tenths would swallow a frame's ms
        self.speed = rp.replay_speed(store.value(rp.SPEED_KEY))
        self.shape = rp.room_shape(store.value(rp.ROOM_KEY))
        self.now = time.monotonic
        self.last = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(_head(rp.HEAD))
        if replay.note:
            column.addWidget(_label(replay.note, "small"))
        controls = QWidget()
        controls.setObjectName("plain")
        flow = FlowLayout(controls, align=Qt.AlignLeft, gap=(8, 6))
        self.play = _button("Play", self.toggle)
        flow.addWidget(self.play)
        flow.addWidget(_button("Rewind", self.rewind))
        speed = QComboBox()
        speed.setAccessibleName("Playback speed")
        for value in rp.SPEEDS:
            speed.addItem(rp.speed_words(value), value)
        speed.setCurrentIndex(rp.SPEEDS.index(self.speed))
        speed.activated.connect(lambda _index: self._speed_chosen(speed.currentData()))
        flow.addWidget(self._named("Speed", speed))
        self.scrub = QSlider(Qt.Horizontal)
        self.scrub.setAccessibleName("Replay time")
        self.scrub.setRange(0, max(0, math.floor(replay.duration * 10 + 1e-9)))   # tenths of a second (``step="0.1"``)
        self.scrub.valueChanged.connect(self._scrubbed)
        flow.addWidget(self.scrub)
        self.clock_label = QLabel()
        flow.addWidget(self.clock_label)
        if replay.rooms is not None:
            shape = QComboBox()
            shape.setAccessibleName("Arena")
            for value, words in rp.SHAPES:
                shape.addItem(words, value)
            shape.setCurrentIndex(0 if self.shape == "circle" else 1)
            shape.activated.connect(lambda _index: self._shape_chosen(shape.currentData()))
            flow.addWidget(self._named("Arena", shape))
        column.addWidget(controls)
        self.arena = Arena()
        column.addWidget(self.arena)
        self.draw(0.0)

    @staticmethod
    def _named(words: str, field: QWidget) -> QWidget:
        """A choice with its name before it (``<label>Speed <select>``)."""
        box = QWidget()
        box.setObjectName("plain")
        line = FlowLayout(box, align=Qt.AlignLeft, gap=(6, 0))
        line.addWidget(_label(words, wrap=False))
        line.addWidget(field)
        return box

    def resizeEvent(self, event) -> None:
        self.scrub.setFixedWidth(max(60, min(self.width() // 2, SCRUB_MOST)))
        super().resizeEvent(event)

    def room(self) -> dict | None:
        """The arena drawn: the room in the shape chosen (``drawRoom``)."""
        rooms = self.replay.rooms
        return {**rooms[self.shape], "shape": self.shape} if rooms is not None else None

    def draw(self, t: float) -> None:
        """The moment ``t`` (``draw``): the slider, the clock and the arena."""
        self.clock = t
        self.scrub.blockSignals(True)
        self.scrub.setValue(min(rp._js_round(t * 10), self.scrub.maximum()))
        self.scrub.blockSignals(False)
        self.clock_label.setText(f"{theme.fixed(t, 1)}s")
        self.arena.show_moment(self.replay.frame(t), self.room())

    def playing(self) -> bool:
        return self.timer.isActive()

    def toggle(self) -> None:
        """Play, or Pause while playing (``data-play``)."""
        if self.timer.isActive():
            self.pause()
            return
        self.last = self.now()
        self.play.setText("Pause")
        self.timer.start()

    def _tick(self) -> None:
        now = self.now()
        t = min(self.replay.duration, self.clock + max(0.0, now - self.last) * self.speed)
        self.last = now
        self.draw(t)
        if t >= self.replay.duration:
            self.pause()

    def pause(self) -> None:
        self.timer.stop()
        self.play.setText("Play")

    def rewind(self) -> None:
        """Back to the fight's start (``data-rewind``)."""
        self.pause()
        self.draw(0.0)

    def _scrubbed(self, value: int) -> None:
        """A time chosen on the slider (``data-scrub``)."""
        self.pause()
        self.draw(value / 10)

    def _speed_chosen(self, value) -> None:
        """The playback speed (``data-speed``): kept for every log."""
        self.speed = value or 1
        self.store.setValue(rp.SPEED_KEY, js_string(self.speed))

    def _shape_chosen(self, value) -> None:
        """The arena's shape (``data-room-shape``): kept for every log."""
        self.shape = rp.room_shape(value)
        self.store.setValue(rp.ROOM_KEY, self.shape)
        self.arena.show_moment(self.arena.tokens, self.room())

    def stop(self) -> None:
        """Playing stopped (the web page's ``cancelAnimationFrame`` as it draws the review again)."""
        self.timer.stop()
