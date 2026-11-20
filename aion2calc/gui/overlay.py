"""The native meter overlay (0.2.413, a preview of the native interface): the meter's reading in a frameless,
always-on-top, see-through Qt window over the game, in place of the overlay page in a pywebview window.

It shows what the overlay page does first: the fight's status, the target with its HP (and the time to kill when
that is on), the counter lines (Odyle Energy, Shugo Keys, Nightmare tickets, the dungeon's weekly runs) and a row
per player, a bar in the class's colour, with the rate (DPS, HPS or damage taken; a click on the metric switches
it) and the share. The window takes the overlay's settings from the app: its width, the rows shown and their
height, the font scale, click-through, and the remembered position, saved where the web overlay keeps it.

The second part (0.2.415) follows the web overlay's settings for the rows (name display, rank numbers, class swatch
and class-coloured names, your own row highlighted, compact rows, stripes, gradient and rounded bars, the dead,
combat power, auto-expand), the target (its HP, the time to kill with the enrage timer, the break gauge), your
contribution, the training-dummy parse, the cooldown strip, only-in-combat and the three background modes.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .api import AppApi, Poller

METRICS = (("dps", "DPS"), ("hps", "HPS"), ("dtps", "Taken"))
DEFAULT_OPACITY = 0.72                    # the overlay page's own starting opacity (overlay.js ``op``)


def _clock(seconds) -> str:
    """A time as the overlay writes its TTK and enrage timer: m:ss."""
    try:
        seconds = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


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
    """The overlay's rounded card, painted at the overlay's opacity: the whole card, its top portion only (the
    header, the target and the counter lines, down to the first player row) or none (``mode``, the overlay's
    Background setting)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.opacity = DEFAULT_OPACITY
        self.mode = "card"
        self.rows_top = None                      # where the first player row starts, for the top-only mode
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        if self.mode == "none":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.mode == "top" and self.rows_top is not None:
            rect.setHeight(max(0.0, min(rect.height(), self.rows_top - 2.0)))
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
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


class GaugeBar(HpBar):
    """The target's break gauge: amber, red once broken (5% or less, as the web overlay has it)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor("#e9a43a")
        self.setFixedHeight(4)

    def set_fraction(self, fraction: float) -> None:
        super().set_fraction(fraction)
        self.color = QColor("#e66a5a" if self.fraction <= 0.05 else "#e9a43a")


class CooldownStrip(QWidget):
    """Your skills on cooldown (the meter's ``cooldowns``, with the chain windows open), each counting down between
    readings as the web overlay's strip does, and lit for 3 s once ready."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(4)
        self.chips: list[QLabel] = []
        self.rows: list = []
        self.chains: list = []
        self.read_at = 0.0
        self.limit = 8

    def set_reading(self, rows, chains, limit: int, now: float) -> None:
        self.rows = [row for row in (rows or []) if isinstance(row, dict)]
        self.chains = [chain for chain in (chains or []) if isinstance(chain, dict)]
        self.limit, self.read_at = max(1, int(limit or 8)), now
        self.tick(now)

    def texts(self, now: float) -> list[tuple[str, bool]]:
        """Each chip's text and whether it is lit (ready or a chain window), as of ``now`` (monotonic seconds)."""
        elapsed = (now - self.read_at) * 1000
        chips, seen = [], set()
        for chain in self.chains:
            seen.add(chain.get("family"))
            chips.append((f"{chain.get('name') or 'Chain'} ⛓", True))
        for row in self.rows:
            if row.get("family") in seen:
                continue
            left = float(row.get("remaining_ms") or 0) - elapsed
            if left <= -3000:
                continue
            name = str(row.get("name") or "Skill")
            chips.append((f"{name} ready", True) if left <= 0 else
                         (f"{name} {left / 1000:.1f}s" if left < 10000 else f"{name} {left / 1000:.0f}s", False))
        return chips[:self.limit]

    def tick(self, now: float) -> None:
        chips = self.texts(now)
        while len(self.chips) < len(chips):
            chip = QLabel(self)
            self.box.addWidget(chip)
            self.chips.append(chip)
        for index, chip in enumerate(self.chips):
            if index >= len(chips):
                chip.hide()
                continue
            text, lit = chips[index]
            chip.setText(text)
            chip.setStyleSheet("color: #e8cf8e; font-weight: 700;" if lit else "color: #9aa3b5;")
            chip.show()


class RowLook:
    """How the rows look, from the overlay's settings (the web overlay's ``nameMode``, ``rankNumbers`` ...)."""

    def __init__(self, ui: dict):
        mode = ui.get("overlay_name_mode")
        self.name_mode = mode if mode in ("name", "class_number", "number") else "name"
        self.rank_numbers = ui.get("overlay_rank_numbers") is True
        self.class_swatch = ui.get("overlay_class_swatch") is True
        self.class_names = ui.get("overlay_class_color_names") is True
        self.highlight_me = ui.get("overlay_highlight_me") is True
        self.compact = ui.get("overlay_compact_rows") is True
        self.stripes = ui.get("overlay_row_stripes") is True
        self.gradient = ui.get("overlay_bar_style") == "gradient"
        self.rounded = ui.get("overlay_bar_rounded") is True
        self.show_deaths = ui.get("overlay_show_deaths") is not False
        self.show_cp = ui.get("overlay_show_combat_power") is not False
        self.auto_expand = ui.get("overlay_auto_expand") is True

    def display_name(self, player: dict, mine: bool, unnamed_self: bool) -> str:
        """The web overlay's ``displayName``: the name, "Sorcerer 2" or "P2"; your unnamed row reads "You"."""
        number = player.get("party_number") or "?"
        if self.name_mode == "number":
            return f"P{number}"
        if self.name_mode == "class_number":
            return f"{str(player.get('class') or 'Player').title()} {number}"
        return "You" if unnamed_self else str(player.get("name") or "?")


class PlayerRow(QWidget):
    """One player: the bar in the class's colour, the name, the rate and the share, as the row's look has it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.name, self.rate, self.share, self.fill, self.mine = "", "", "", 0.0, False
        self.index, self.dead, self.cp, self.look = 0, False, "", RowLook({})
        self.color = QColor(theme.FALLBACK_CLASS_COLOR)
        self.setFixedHeight(22)

    def set_player(self, name: str, cls: str, rate: str, share: str, fill: float, mine: bool,
                   index: int = 0, dead: bool = False, cp: str = "", look: RowLook | None = None) -> None:
        look = look or self.look
        state = (name, cls, rate, share, round(fill, 4), mine, index, dead, cp, tuple(sorted(vars(look).items())))
        if state == getattr(self, "_state", None):
            return
        self._state = state
        self.name, self.rate, self.share, self.fill, self.mine = name, rate, share, max(0.0, min(1.0, fill)), mine
        self.index, self.dead, self.cp, self.look = index, dead, cp, look
        self.color = QColor(theme.class_color(cls))
        self.update()

    def label(self) -> str:
        """The row's left-hand text: the rank, the name and its combat power."""
        text = (f"{self.index + 1}. " if self.look.rank_numbers else "") + self.name
        return f"{text}  {self.cp}" if self.cp else text

    def right(self) -> str:
        """The row's right-hand text: DEAD for the dead, the rate, and the share unless the rows are compact."""
        dead = "DEAD  " if self.dead else ""
        return f"{dead}{self.rate}" if self.look.compact else f"{dead}{self.rate}  {self.share}"

    def paintEvent(self, event):
        look = self.look
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.dead:
            painter.setOpacity(0.45)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        radius = 4 if look.rounded else 1.5
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 26 if look.stripes and self.index % 2 else 14))
        painter.drawRoundedRect(rect, radius, radius)
        if self.fill > 0:
            bar_rect = QRectF(rect.x(), rect.y(), rect.width() * self.fill, rect.height())
            bar = QColor(self.color)
            bar.setAlpha(200)
            if look.gradient:
                gradient = QLinearGradient(bar_rect.topLeft(), bar_rect.topRight())
                gradient.setColorAt(0, bar)
                fade = QColor(bar)
                fade.setAlpha(70)
                gradient.setColorAt(1, fade)
                painter.setBrush(gradient)
            else:
                painter.setBrush(bar)
            painter.drawRoundedRect(bar_rect, radius, radius)
        if self.mine and look.highlight_me:
            painter.setBrush(QColor(theme.COLORS["gold"]))
            painter.drawRect(QRectF(rect.x(), rect.y(), 3, rect.height()))
        left = rect.x() + 7
        if look.class_swatch:
            painter.setBrush(self.color)
            side = min(10.0, rect.height() - 6)
            painter.drawRoundedRect(QRectF(left, rect.center().y() - side / 2, side, side), 2, 2)
            left += side + 5
        font = QFont(self.font())
        font.setBold(self.mine)
        painter.setFont(font)
        painter.setPen(self.color.lighter(150) if look.class_names else QColor(theme.COLORS["text"]))
        text_rect = QRectF(left, rect.y(), rect.right() - 7 - left, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.label())
        painter.setPen(QColor(theme.COLORS["text"]))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignRight, self.right())


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
        self.gauge = GaugeBar(self)
        box.addWidget(self.gauge)
        self.lines = QLabel("")
        self.lines.setObjectName("ovlines")
        self.lines.setWordWrap(True)
        box.addWidget(self.lines)
        self.extra = QLabel("")                   # your contribution, or the training-dummy parse
        self.extra.setObjectName("ovextra")
        box.addWidget(self.extra)
        self.box = box
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(2)
        box.addLayout(self.rows_box)
        self.cooldowns = CooldownStrip(self.card)  # below the meter, the web overlay's default; the setting moves it
        box.addWidget(self.cooldowns)
        self.rows: list[PlayerRow] = []
        self.look = RowLook({})
        self._cooldowns_top = False
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.timeout.connect(lambda: self.cooldowns.tick(time.monotonic()))
        self._cooldown_timer.start(250)
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
            f"QLabel#ovextra {{ color: {c['muted']}; }}"
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
        self.look = RowLook(ui)
        mode = ui.get("overlay_bg_mode")
        self.card.mode = mode if mode in ("card", "top", "none") else "card"
        top = ui.get("overlay_cooldowns_position") == "top"
        if top != self._cooldowns_top:            # the strip above the player rows, or below them
            self._cooldowns_top = top
            self.box.removeWidget(self.cooldowns)
            self.box.insertWidget(self.box.indexOf(self.extra) + 1 if top else self.box.count(), self.cooldowns)
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
        ui, look, metric = self.ui, self.look, self.rate_metric
        snap = answer.get("snapshot") or {}
        running, over = answer.get("running") is True, snap.get("battle_over") is True
        players = [p for p in (snap.get("players") or []) if isinstance(p, dict) and _amount(p, metric) > 0]
        players.sort(key=lambda p: (_rate(p, metric), _amount(p, metric)), reverse=True)
        limit = max(1, min(24, int(ui.get("overlay_max_players") or 8)))
        if look.auto_expand:
            limit = min(24, max(limit, len(players)))
        shown = players[:limit]
        total_rate = sum(_rate(p, metric) for p in players)
        total_amount = sum(_amount(p, metric) for p in players) or 1.0
        top = max((_rate(p, metric) for p in shown), default=0.0) or 1.0
        label = dict(METRICS)[metric]
        # Only in combat (the web overlay's ``collapse``): between fights the overlay keeps its header alone.
        idle = ui.get("overlay_only_in_combat") is True and (
            not running or over or (snap.get("paused") is True and snap.get("boss_alive") is not True))
        if not running and not players:
            self.status.setText("Idle")
        elif not players or idle:
            self.status.setText("Idle · waiting for combat")
        else:
            boss = snap.get("boss") or "Combat"
            duration = float(snap.get("duration") or 0)
            paused = "Paused DPS · " if snap.get("paused") is True and metric == "dps" else ""
            status = f"{paused}{boss} · {duration:.0f}s · {theme.kfmt(total_rate)} raid {label}"
            backlog = snap.get("decode_backlog") or {}
            if isinstance(backlog, dict) and backlog.get("catching_up"):
                status += f" · catching up ({backlog.get('queue_depth')})"
            self.status.setText(status)
        self._show_target(None if idle else snap.get("current_target"))
        lines = counter_lines(snap)
        if lines and not idle:
            full = "    ".join(text for _key, text, _short in lines)
            fits = self.lines.fontMetrics().horizontalAdvance(full) <= self.width() - 24
            self.lines.setText(full if fits else "  ·  ".join(short for _key, _text, short in lines))
            self.lines.setToolTip("\n".join(text for _key, text, _short in lines))
            self.lines.show()
        else:
            self.lines.hide()
        self._show_extra(snap, idle or over, metric)
        cooling = (ui.get("overlay_show_cooldowns") is True and running and not idle
                   and (snap.get("cooldowns") or snap.get("chain_windows")))
        if cooling:
            self.cooldowns.set_reading(snap.get("cooldowns"), snap.get("chain_windows"),
                                       ui.get("overlay_cooldowns_max") or 8, time.monotonic())
        self.cooldowns.setVisible(bool(cooling))
        identity = snap.get("identity_status") or {}
        local = str(identity.get("local_name") or "").casefold()
        local_id, local_cp = identity.get("local_id"), identity.get("local_combat_power")
        while len(self.rows) < len(shown):
            row = PlayerRow(self.card)
            row.setFixedHeight(max(16, min(48, int(ui.get("overlay_row_height") or 22))))
            self.rows_box.addWidget(row)
            self.rows.append(row)
        for index, row in enumerate(self.rows):
            if idle or index >= len(shown):
                row.hide()
                continue
            player = shown[index]
            name = str(player.get("name") or "")
            mine = bool(local) and name.casefold() == local
            unnamed_self = (local_id is not None and str(player.get("id")) == str(local_id)
                            and name.startswith("Player #"))
            cp = 0.0
            if look.show_cp:
                cp = float(player.get("combat_power") or (local_cp if mine else 0) or 0)
            row.set_player(look.display_name(player, mine, unnamed_self), str(player.get("class") or ""),
                           f"{theme.kfmt(_rate(player, metric))}/s",
                           f"{100 * _amount(player, metric) / total_amount:.0f}%", _rate(player, metric) / top,
                           mine, index, look.show_deaths and player.get("dead") is True,
                           theme.sfmt(cp) if cp > 0 else "", look)
            row.show()
        self.adjustSize()
        first = next((row for row in self.rows if not row.isHidden()), None)
        self.card.rows_top = first.geometry().top() if first is not None else None
        self.card.update()

    def _show_target(self, target) -> None:
        """The target line: its name, its HP when that is on, the time to kill with the enrage timer, and the break
        gauge, with their bars."""
        ui = self.ui
        if ui.get("overlay_show_target", True) is False or not isinstance(target, dict) or not target.get("name"):
            for widget in (self.target, self.hp, self.gauge):
                widget.hide()
            return
        parts = [str(target["name"])]
        hp = target.get("hp_pct")
        show_hp = ui.get("overlay_show_enemy_hp") is True and isinstance(hp, (int, float))
        if show_hp:
            parts.append(f"{hp * 100:.0f}%")
        if ui.get("overlay_show_ttk") is True:
            ttk = target.get("ttk")
            if isinstance(ttk, (int, float)) and ttk > 0:
                parts.append(f"TTK {_clock(ttk)}")
            enrage = target.get("enrage")
            if isinstance(enrage, dict):
                parts.append("ENRAGED" if enrage.get("enraged") else f"Enrage {_clock(enrage.get('enrage_in'))}")
        gauge = target.get("break_gauge") if ui.get("overlay_show_break_gauge") is True else None
        pct = None
        if isinstance(gauge, dict):
            pct = max(0.0, min(100.0, float(gauge.get("pct") or 0)))
            parts.append("BROKEN" if pct <= 5 else f"Break {pct:.0f}%")
        self.target.setText("  ·  ".join(parts))
        self.target.show()
        self.hp.setVisible(show_hp)
        if show_hp:
            self.hp.set_fraction(hp)
        self.gauge.setVisible(pct is not None)
        if pct is not None:
            self.gauge.set_fraction(pct / 100)

    def _show_extra(self, snap: dict, hidden: bool, metric: str) -> None:
        """Your contribution to the fight, or the training-dummy parse, under the target (DPS view only)."""
        text = ""
        contribution, dummy = snap.get("contribution"), snap.get("dummy_parse")
        if not hidden and metric == "dps":
            if isinstance(dummy, dict) and self.ui.get("meter_show_dummy_parse", True) is not False:
                you = f" · You {theme.kfmt(dummy['your_dps'])}/s" if dummy.get("your_dps") is not None else ""
                text = (f"Dummy parse {round(float(dummy.get('duration') or 0))}s / "
                        f"{round(float(dummy.get('window_seconds') or 0))}s{' ✓' if dummy.get('window_reached') else ''}"
                        f"{you} · Total {theme.kfmt(dummy.get('target_dps'))}/s")
            elif (isinstance(contribution, dict) and float(contribution.get("damage") or 0) > 0
                  and self.ui.get("overlay_show_contribution") is not False):
                text = (f"Your contribution: {round(float(contribution.get('share') or 0) * 100)}% · "
                        f"{theme.kfmt(contribution.get('damage'))} ({theme.kfmt(contribution.get('dps'))}/s)")
        self.extra.setText(text)
        self.extra.setVisible(bool(text))

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
