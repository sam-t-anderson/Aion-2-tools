"""The native overlay's window on the desktop (0.2.418): what the web overlay's host (``aion2calc/overlay.py``) does
around its page, done for the native overlay's own window, with the host's own rules and helpers.

- **The game window.** The overlay shows while the game runs and is not minimized, and hides with it, so it never
  sits over other programs. With *always visible* off it shows only while the game (or the overlay) has the focus.
  Locked for a screenshot, it stays up.
- **Its place.** It opens where it was last put, by the monitor layout it was put under (``resolve_remembered_position``),
  else by the game window's corner, where it stays; a drag saves the new place with the monitors it was put on.
  With *remember position* off it follows the game window, snapping to its edges or growing upward as the
  overlay's settings say.
- **Click-through.** With it on, clicks pass through to the game everywhere but over the overlay's own buttons, and
  resting the pointer on the overlay (*hover to interact*) opens it to clicks until the pointer leaves.

The game window, the screen's pixels and click-through by the control are Windows' (``native_overlay``). Elsewhere
the overlay keeps its own place, and click-through takes the whole window, as before.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QPoint, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractButton, QAbstractSlider, QWidget

from ..overlay import _HoverOpen, _follow_move, _follow_position, resolve_remembered_position

FOLLOW_MS = 250                           # the host's game-window loop (``_run_overlay``)
HIT_MS = 33                               # its click-through loop, about 30 a second (``_click_through_loop``)


class _Dragging:
    """What ``_follow_move`` asks of the host's bridge: whether the player is moving the window."""

    def __init__(self, window):
        self.window = window

    @property
    def _dragging(self) -> bool:
        return getattr(self.window, "_drag", None) is not None


class WindowHost(QObject):
    """The overlay window's place on the desktop. ``win32`` is ``native_overlay()``'s backend (None where the platform
    has none, and a stand-in in tests); ``clock`` the hover's clock."""

    def __init__(self, window, win32=None, clock=time.monotonic):
        super().__init__(window)
        self.window, self.win32, self.clock = window, win32, clock
        self.shown = True                         # as the game window last had it
        self.placed = False                       # opened at its remembered place, or the game's corner
        self.previous = self.previous_hwnd = None # the game window's bounds when the overlay last followed it
        self.applied = None                       # click-through as set: None untouched, True passing clicks
        self.hover = _HoverOpen()
        self.dragging = _Dragging(window)
        self._follow = QTimer(self)
        self._follow.setInterval(FOLLOW_MS)
        self._follow.timeout.connect(self.follow_tick)
        self._hit = QTimer(self)
        self._hit.setInterval(HIT_MS)
        self._hit.timeout.connect(self.hit_tick)

    @property
    def native(self) -> bool:
        """Whether the platform gives the overlay the game window and click-through by the control."""
        return self.win32 is not None

    def start(self) -> None:
        if self.native:
            self._follow.start()

    def stop(self) -> None:
        self._follow.stop()
        self._hit.stop()

    def hwnd(self) -> int:
        return int(self.window.winId())

    # ------------------------------------------------------------------ place
    def monitors(self) -> list:
        """Each monitor's (left, top, width, height): the screen's pixels on Windows, Qt's own elsewhere."""
        if self.native:
            monitors = list(self.win32.monitors() or [])
            if not monitors:
                box = self.win32.virtual_screen()
                monitors = [tuple(box)] if box and box[2] > 0 and box[3] > 0 else []
            return monitors
        return [screen.geometry().getRect() for screen in QGuiApplication.screens()]

    def position(self) -> tuple[int, int]:
        if self.native:
            return tuple(self.win32.rect(self.hwnd())[:2])
        return self.window.x(), self.window.y()

    def move(self, x: int, y: int) -> None:
        if self.native:
            self.win32.move(self.hwnd(), int(x), int(y))
        else:
            self.window.move(int(x), int(y))

    def restore(self, ui: dict) -> bool:
        """Open where the overlay was last put, if that place is still on a monitor (the layout it was saved under
        tells a rearranged desktop from the same one). With remember position off the game window places it."""
        if ui.get("overlay_remember_position") is False:
            return False
        x, y, layout = ui.get("overlay_pos_x"), ui.get("overlay_pos_y"), ui.get("overlay_pos_layout")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y)):
            return False
        place = resolve_remembered_position(x, y, layout if isinstance(layout, list) else None, self.monitors())
        if place is None:
            return False
        self.move(*place)
        self.placed = True
        return True

    def saved_place(self) -> dict:
        """What a drag saves: the place and the monitors it was put on (the web overlay's ``overlay_pos_*``)."""
        x, y = self.position()
        return {"overlay_pos_x": int(x), "overlay_pos_y": int(y),
                "overlay_pos_layout": [[int(v) for v in monitor] for monitor in self.monitors()]}

    # ------------------------------------------------------------------ the game window
    def follow_tick(self) -> None:
        """One turn of the host's game-window loop: show or hide with the game, then keep the overlay's place."""
        try:
            self._follow_game()
        except Exception:                         # noqa: BLE001 - a window hiccup must never stop the loop
            pass

    def _follow_game(self) -> None:
        win32, window, ui = self.win32, self.window, self.window.ui
        game = win32.game_window()
        hwnd = self.hwnd()
        always = ui.get("overlay_always_visible", True) is not False
        show = game is not None and not game.minimized and (
            always or win32.user32.GetForegroundWindow() in (game.hwnd, hwnd))
        if window.locked:                         # held for a screenshot: it stays up and in place
            if not self.shown:
                window.show()
                self.shown = True
            return
        if show != self.shown:
            window.setVisible(show)
            self.shown = show
        if game is None:
            self.previous = self.previous_hwnd = None
            return
        if game.minimized:
            return
        snap, up = ui.get("overlay_snap_edge") is True, ui.get("overlay_expand_up") is True
        if ui.get("overlay_remember_position") is not False:
            if not self.placed:                   # nothing kept yet: by the game window's corner, kept from now on
                anchor = _follow_position(None, game.bounds, win32.rect(hwnd), snap=snap, expand_up=up)
                self.move(*anchor)
                self.placed = True
                window.save_position()
            return
        if game.hwnd != self.previous_hwnd:
            self.previous = None
        place = _follow_move(self.dragging, self.previous, game.bounds, win32.rect(hwnd), snap=snap, expand_up=up)
        if place is not None:
            self.move(*place)
        self.previous, self.previous_hwnd = game.bounds, game.hwnd

    # ------------------------------------------------------------------ click-through
    def set_click_through(self, on: bool) -> None:
        """With the platform's help the overlay passes clicks through by the control, many times a second; the
        loop runs while click-through is on, and once more to give the window its clicks back."""
        if self.native:
            self._hit.start()
            if not on:
                self.hit_tick()
                self._hit.stop()

    def control_rects(self) -> list[tuple[float, float, float, float]]:
        """The overlay's buttons, ticks and sliders in the window's own pixels, as the web overlay reports its
        controls (``reportInteractiveRects``): over these, clicks stay the overlay's."""
        window, ratio = self.window, self.window.devicePixelRatioF()
        rects = []
        controls = (window.findChildren(QAbstractButton) + window.findChildren(QAbstractSlider)
                    + window.findChildren(QWidget, "ovgrip"))   # the resize grips too, as the web overlay's
        for control in controls:
            if not control.isVisibleTo(window) or control.width() <= 0:
                continue
            corner = control.mapTo(window, QPoint(0, 0))
            rects.append((corner.x() * ratio, corner.y() * ratio, (corner.x() + control.width()) * ratio,
                          (corner.y() + control.height()) * ratio))
        return rects

    def over_overlay(self, pos) -> bool:
        """Whether a point of the window is on what the overlay draws: the card, or with the card see-through its
        pieces, so the game between them does not count (the host's ``_over_overlay``)."""
        window = self.window
        if pos is None:
            return False
        ratio = window.devicePixelRatioF()
        point = QPoint(int(pos[0] / ratio), int(pos[1] / ratio))
        if not window.rect().contains(point):
            return False
        if window.card.mode == "card":
            return True
        child = window.childAt(point)              # the gaps between the footer's chips are the game's
        return child is not None and child is not window.card and not child.property("ovgap")

    def hit_tick(self) -> None:
        """One turn of the host's click-through loop: clicks pass through but over a control, or once resting on
        the overlay has opened it (hover to interact)."""
        try:
            self._hit_test()
        except Exception:                         # noqa: BLE001 - a window hiccup must never stop the loop
            pass

    def _hit_test(self) -> None:
        win32, window = self.win32, self.window
        hwnd = self.hwnd()
        if not window.click_through:
            if self.applied:                      # it was passing clicks through: the window takes them again
                win32.set_click_through(hwnd, False)
                self.applied = False
            _opened, said = self.hover.update(False, False, self.clock())
            if said:
                window.set_hover_state(said)
            return
        pos = win32.cursor_in_client(hwnd)
        over_control = pos is not None and any(left <= pos[0] <= right and top <= pos[1] <= bottom
                                               for left, top, right, bottom in self.control_rects())
        opened, said = self.hover.update(window.ui.get("overlay_hover_interact") is True, self.over_overlay(pos),
                                         self.clock())
        if said:
            window.set_hover_state(said)
        passing = not (over_control or opened)
        if passing != self.applied:
            win32.set_click_through(hwnd, passing)
            self.applied = passing
