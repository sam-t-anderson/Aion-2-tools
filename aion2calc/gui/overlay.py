"""The native meter overlay (0.2.413, a preview of the native interface): the meter's reading in a frameless,
always-on-top, see-through Qt window over the game, in place of the overlay page in a pywebview window.

It shows what the overlay page does first: the fight's status, the target with its HP (and the time to kill when
that is on), the counter lines (Odyle Energy, Shugo Keys, Nightmare tickets, the dungeon's weekly runs) and a row
per player, a bar in the class's colour, with the rate (DPS, HPS or damage taken; a click on the metric switches
it) and the share. The window takes the overlay's settings from the app: its width, the rows shown and their
height, the font scale, click-through, and the remembered position, saved where the web overlay keeps it.
"""
from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .api import AppApi, Poller

METRICS = (("dps", "DPS"), ("hps", "HPS"), ("dtps", "Taken"))
DEFAULT_OPACITY = 0.72                    # the overlay page's own starting opacity (overlay.js ``op``)


def _rate(player: dict, metric: str) -> float:
    try:
        return float(player.get(metric) or 0)
    except (TypeError, ValueError):
        return 0.0


def _amount(player: dict, metric: str) -> float:
    if metric == "hps":
        value = player.get("healing")
    elif metric == "dtps":
        value = (player.get("incoming") or {}).get("damage")
    else:
        value = player.get("damage")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def counter_lines(snapshot: dict) -> list[tuple[str, str, str]]:
    """The counter lines the meter's reading carries, each ``(key, full text, short text)``, in the overlay's
    order. The app leaves out a line its setting turns off, so every line here is shown."""
    lines = []
    for key, label, short in (("odyle", "Odyle Energy", "Odyle"), ("shugo_keys", "Shugo Keys", "Keys"),
                              ("nightmare_tickets", "Nightmare Tickets", "Tickets")):
        value = snapshot.get(key)
        if isinstance(value, dict):
            regular, bonus = value.get("regular"), value.get("bonus")
            lines.append((key, f"{label} {theme.count(regular, bonus)}", f"{short} {theme.short_count(regular, bonus)}"))
    weekly = snapshot.get("weekly_runs")
    if isinstance(weekly, dict):
        regular, bonus = int(weekly.get("regular") or 0), int(weekly.get("bonus") or 0)
        left = regular + bonus
        place = " · ".join(part for part in (weekly.get("zone"), weekly.get("difficulty")) if part)
        extra = f" ({regular:,} + {bonus:,} bonus)" if bonus else ""
        text = f"{place + ': ' if place else ''}{left:,} {'run' if left == 1 else 'runs'} left this week{extra}"
        lines.append(("weekly_runs", text, f"Runs {theme.short_count(regular, bonus)}"))
    return lines


class _Card(QWidget):
    """The overlay's rounded card, painted at the overlay's opacity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.opacity = DEFAULT_OPACITY
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        r, g, b = theme.OVERLAY_CARD
        painter.fillPath(path, QColor(r, g, b, int(255 * self.opacity)))
        painter.setPen(QColor(255, 255, 255, 20))
        painter.drawPath(path)


class HpBar(QWidget):
    """The target's HP, a filled bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fraction = 0.0
        self.color = QColor("#e05a5a")
        self.setFixedHeight(6)

    def set_fraction(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, float(fraction or 0)))
        if fraction != self.fraction:
            self.fraction = fraction
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(rect, 3, 3)
        if self.fraction > 0:
            painter.setBrush(self.color)
            painter.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * self.fraction, rect.height()), 3, 3)


class PlayerRow(QWidget):
    """One player: the bar in the class's colour, the name, the rate and the share."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.name, self.rate, self.share, self.fill, self.mine = "", "", "", 0.0, False
        self.color = QColor(theme.FALLBACK_CLASS_COLOR)
        self.setFixedHeight(22)

    def set_player(self, name: str, cls: str, rate: str, share: str, fill: float, mine: bool) -> None:
        state = (name, cls, rate, share, round(fill, 4), mine)
        if state == getattr(self, "_state", None):
            return
        self._state = state
        self.name, self.rate, self.share, self.fill, self.mine = name, rate, share, max(0.0, min(1.0, fill)), mine
        self.color = QColor(theme.class_color(cls))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 14))
        painter.drawRoundedRect(rect, 4, 4)
        if self.fill > 0:
            bar = QColor(self.color)
            bar.setAlpha(200)
            painter.setBrush(bar)
            painter.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * self.fill, rect.height()), 4, 4)
        font = QFont(self.font())
        font.setBold(self.mine)
        painter.setFont(font)
        painter.setPen(QColor(theme.COLORS["text"]))
        text_rect = rect.adjusted(7, 0, -7, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.name)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignRight, f"{self.rate}  {self.share}")


class MeterOverlay(QWidget):
    """The meter overlay window. ``api`` is the app's local API (None in tests, which hand it the readings)."""

    def __init__(self, api: AppApi | None = None, parent_process=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Aion 2 Calc overlay")
        self.api, self.parent_process = api, parent_process
        self.ui: dict = {}
        self.answer: dict = {}
        self.rate_metric = "dps"                 # not ``metric``: QWidget.metric() is Qt's own
        self.click_through = False
        self._drag: QPoint | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = _Card(self)
        outer.addWidget(self.card)
        box = QVBoxLayout(self.card)
        box.setContentsMargins(10, 8, 10, 9)
        box.setSpacing(4)
        head = QHBoxLayout()
        self.status = QLabel("Waiting for the meter")
        self.status.setObjectName("ovstatus")
        head.addWidget(self.status, 1)
        self.metric_buttons = {}
        for key, label in METRICS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFlat(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self.set_metric(k))
            head.addWidget(button)
            self.metric_buttons[key] = button
        box.addLayout(head)
        self.target = QLabel("")
        self.target.setObjectName("ovtarget")
        box.addWidget(self.target)
        self.hp = HpBar(self)
        box.addWidget(self.hp)
        self.lines = QLabel("")
        self.lines.setObjectName("ovlines")
        self.lines.setWordWrap(True)
        box.addWidget(self.lines)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(2)
        box.addLayout(self.rows_box)
        self.rows: list[PlayerRow] = []
        self._style()
        self.set_metric("dps")
        self.apply_ui({})
        self.apply_meter({})
        self._pollers = []
        if api is not None:
            meter = Poller(api, "/api/meter?view=latest", 500, self)
            meter.answered.connect(self.apply_meter)
            meter.failed.connect(lambda why: self.status.setText("The app does not answer"))
            settings = Poller(api, "/api/ui", 3000, self)
            settings.answered.connect(self.apply_ui)
            self._pollers = [meter, settings]
        if parent_process is not None and getattr(parent_process, "watched", lambda: False)():
            self._parent_timer = QTimer(self)
            self._parent_timer.timeout.connect(self._check_parent)
            self._parent_timer.start(2000)

    def start(self) -> None:
        for poller in self._pollers:
            poller.start()

    def _check_parent(self) -> None:
        if not self.parent_process.alive():
            QApplication.quit()

    # ------------------------------------------------------------------ look
    def _style(self) -> None:
        scale = max(50, min(200, int(self.ui.get("overlay_font_scale") or 100))) / 100
        weight = int(self.ui.get("overlay_font_weight") or 600)
        font = QFont(theme.FONT_FAMILIES[0])
        font.setFamilies(theme.FONT_FAMILIES)
        font.setPixelSize(max(8, round(12 * scale)))
        font.setWeight(QFont.Weight(max(100, min(900, weight))))
        self.setFont(font)
        c = theme.COLORS
        self.setStyleSheet(
            f"QLabel {{ color: {c['text']}; background: transparent; }}"
            f"QLabel#ovstatus {{ color: {c['gold']}; font-weight: 700; }}"
            f"QLabel#ovlines {{ color: #e9edf1; }}"
            f"QPushButton {{ color: {c['muted']}; background: transparent; border: none; padding: 0 3px; }}"
            f"QPushButton:checked {{ color: {c['gold']}; text-decoration: underline; }}")

    def apply_ui(self, ui: dict) -> None:
        """Take the overlay's settings from the app's answer to ``/api/ui``."""
        if not isinstance(ui, dict):
            return
        first = not self.ui
        self.ui = ui
        width = max(260, min(800, int(ui.get("overlay_width") or 340)))
        self.setFixedWidth(width)
        row_height = max(16, min(48, int(ui.get("overlay_row_height") or 22)))
        for row in self.rows:
            row.setFixedHeight(row_height)
        self.hp.color = QColor(ui.get("overlay_hp_color") or "#e05a5a")
        self._style()
        self.set_click_through(ui.get("overlay_click_through") is True)
        if first and ui.get("overlay_remember_position") is not False:
            x, y = ui.get("overlay_pos_x"), ui.get("overlay_pos_y")
            if isinstance(x, int) and isinstance(y, int) and not isinstance(x, bool) and not isinstance(y, bool):
                self.move(x, y)
        self.apply_meter(self.answer)

    def set_click_through(self, on: bool) -> None:
        """Let clicks pass through to the game (the overlay's own setting)."""
        if on == self.click_through:
            return
        self.click_through = on
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        if visible:
            self.show()                          # changing a window flag hides the window until it is shown again

    def set_metric(self, metric: str) -> None:
        self.rate_metric = metric if metric in dict(METRICS) else "dps"
        for key, button in self.metric_buttons.items():
            button.setChecked(key == self.rate_metric)
        self.apply_meter(self.answer)

    # ------------------------------------------------------------------ reading
    def apply_meter(self, answer: dict) -> None:
        """Draw the meter's reading (the app's answer to ``/api/meter?view=latest``)."""
        if not isinstance(answer, dict):
            return
        self.answer = answer
        snap = answer.get("snapshot") or {}
        players = [p for p in (snap.get("players") or []) if isinstance(p, dict)]
        metric = self.rate_metric
        players.sort(key=lambda p: _rate(p, metric), reverse=True)
        limit = max(1, min(24, int(self.ui.get("overlay_max_players") or 8)))
        shown = players[:limit]
        total_rate = sum(_rate(p, metric) for p in players)
        total_amount = sum(_amount(p, metric) for p in players) or 1.0
        top = max((_rate(p, metric) for p in shown), default=0.0) or 1.0
        label = dict(METRICS)[metric]
        if not answer.get("running") and not players:
            self.status.setText("Idle")
        elif not players:
            self.status.setText("Idle · waiting for combat")
        else:
            boss = snap.get("boss") or "Combat"
            duration = float(snap.get("duration") or 0)
            self.status.setText(f"{boss} · {duration:.0f}s · {theme.kfmt(total_rate)} raid {label}")
        target = snap.get("current_target") if self.ui.get("overlay_show_target", True) is not False else None
        if isinstance(target, dict) and target.get("name"):
            hp = target.get("hp_pct")
            text = str(target["name"])
            if isinstance(hp, (int, float)):
                text += f"  {hp * 100:.0f}%"
            ttk = target.get("ttk")
            if self.ui.get("overlay_show_ttk") is True and isinstance(ttk, (int, float)) and ttk > 0:
                text += f"  ·  TTK {int(ttk) // 60}:{int(ttk) % 60:02d}"
            self.target.setText(text)
            self.target.show()
            self.hp.set_fraction(hp if isinstance(hp, (int, float)) else 0)
            self.hp.setVisible(isinstance(hp, (int, float)))
        else:
            self.target.hide()
            self.hp.hide()
        lines = counter_lines(snap)
        if lines:
            full = "    ".join(text for _key, text, _short in lines)
            fits = self.lines.fontMetrics().horizontalAdvance(full) <= self.width() - 24
            self.lines.setText(full if fits else "  ·  ".join(short for _key, _text, short in lines))
            self.lines.setToolTip("\n".join(text for _key, text, _short in lines))
            self.lines.show()
        else:
            self.lines.hide()
        local = ((snap.get("identity_status") or {}).get("local_name") or "").casefold()
        while len(self.rows) < len(shown):
            row = PlayerRow(self.card)
            row.setFixedHeight(max(16, min(48, int(self.ui.get("overlay_row_height") or 22))))
            self.rows_box.addWidget(row)
            self.rows.append(row)
        for index, row in enumerate(self.rows):
            if index >= len(shown):
                row.hide()
                continue
            player = shown[index]
            amount = _amount(player, metric)
            row.set_player(str(player.get("name") or "?"), str(player.get("class") or ""),
                           f"{theme.kfmt(_rate(player, metric))}/s", f"{100 * amount / total_amount:.0f}%",
                           _rate(player, metric) / top, str(player.get("name") or "").casefold() == local != "")
            row.show()
        self.adjustSize()

    # ------------------------------------------------------------------ moving
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.save_position()

    def save_position(self) -> None:
        """Keep a dragged position where the web overlay keeps it (``overlay_pos_x``/``_y``), best effort."""
        if self.api is None or self.ui.get("overlay_remember_position") is False:
            return
        try:
            self.api.post("/api/ui", {"overlay_pos_x": int(self.x()), "overlay_pos_y": int(self.y())})
        except (OSError, ValueError):
            pass


def _app_base(url: str) -> str:
    return url.split("/overlay")[0] if "/overlay" in url else url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aion2calc.gui.overlay", description="Aion 2 Calc native overlay")
    parser.add_argument("--url", default=None, help="the app's overlay address (default: the running app's)")
    args = parser.parse_args(argv)
    from ..overlay import _ParentProcess, _default_url
    url = args.url or _default_url()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    window = MeterOverlay(AppApi(_app_base(url)), _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")))
    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
