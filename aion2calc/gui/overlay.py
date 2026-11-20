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

The third part (0.2.416) is the web overlay's toolbar and its player panel. Lock freezes the overlay in place for a
screenshot (the app's screenshot hotkey too); New starts a new fight, the meter empty until it begins; Copy puts the
leaderboard on the clipboard as text; Options holds the pet grouping, the damage filters and the opacity; Start or
Stop runs the capture; Hide closes the overlay windows. A click on a player opens their panel under the rows: their
totals and special hits as tiles, their top skills and the buffs on them with their uptime. A fight that is over
gives way to "Ready — waiting for the next fight." as on the web overlay.
"""
from __future__ import annotations

import argparse
import html
import math
import os
import re
import sys
import time
from urllib.parse import quote

from PySide6.QtCore import QPoint, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from . import theme
from .api import AppApi, Poller, Requests

METRICS = (("dps", "DPS"), ("hps", "HPS"), ("dtps", "Taken"))
DEFAULT_OPACITY = 0.72                    # the overlay page's own starting opacity (overlay.js ``op``)
MAX_OVERLAY_HEIGHT = 800                  # the tallest the overlay window grows (overlay.js ``MAX_OVERLAY_H``)
GRAPH_LIMIT = 300                         # the readings the live graph keeps (overlay.js ``recordGraph``)
#: The Players scope Start captures with: the web overlay's own when the app's Live Meter page saved none.
START_SCOPE = "party"
#: The toolbar (overlay.html), in the order the web overlay's compact layout gives it: key, text, tooltip.
TOOLS = (("lock", "Lock", "Freeze the overlay in place for a screenshot"),
         ("split", "New", "Start a new fight — the next combat event begins a fresh encounter (same as Split now in "
                          "the app)"),
         ("copy", "Copy", "Copy the current meter as text, to paste in chat or Discord"),
         ("options", "Options", "Overlay options: opacity, pet grouping and damage filters"),
         ("capture", "Start", "Start or stop capturing combat (same as Start/Stop in the app)"),
         ("hide", "Hide", "Hide overlay"))
#: The player panel's tooltips (overlay.js ``renderDetail``'s ``titles``).
TILE_TITLES = {"Parry": "Share of this player's hits the enemy parried",
               "Front": "Share of hits landed from the front", "Back": "Share of hits landed from behind",
               "Perfect": "Share of perfect hits", "Double": "Share of double hits",
               "Parried in": "Hits on this player that they parried",
               "Shield blocks": "Hits on this player that they blocked with their shield",
               "Endurance": "Hits on this player that their Endurance halved"}
_UNNAMED = re.compile(r"Player #\d+")


def _num(value) -> float:
    """A reading's number, 0 for anything else (JavaScript's ``Number(x) || 0``)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _round(value) -> int:
    """``Math.round`` of a reading's number: a half goes up, as the web overlay rounds."""
    return theme.js_round(_num(value))


def _setting(value, low: int, high: int, default: int) -> int:
    """A whole-number setting in its range, else its default (overlay.js ``clampInt``)."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def _text(value) -> str:
    """A number as JavaScript writes it into text: 100, not 100.0."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def fmt_secs(seconds) -> str:
    """A span as the player panel writes it (overlay.js ``fmtSecs``): 45s, 1m 15s."""
    s = max(0, _round(seconds))
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


def _pct(value) -> str:
    return "—" if value is None else f"{_round(_num(value) * 100)}%"


def _initials(name) -> str:
    """A skill icon's stand-in: the first letters of its words, two at most (overlay.js ``skillIconHTML``)."""
    return "".join(word[0] for word in str(name or "").split())[:2]


def _key(player: dict) -> str:
    """A player row's key, as the snapshot gives it (``String(p.key || p.id)``)."""
    return str(player.get("key") or player.get("id"))


def filter_label(answer: dict) -> str:
    """The damage filters the app applies to the latest fight, named as the web overlay names them."""
    targets = answer.get("targets") if isinstance(answer.get("targets"), list) else []
    boss, player = "boss" in targets, "player" in targets
    if boss and player:
        return "Boss and player damage only"
    return "Boss damage only" if boss else "Player damage only" if player else ""


def leaderboard_text(snap: dict, ranked: list, metric: str, filtered: str, name_of) -> str:
    """The Copy button's text (overlay.js ``copyText``): the view's leaderboard, ready to paste in chat or Discord.
    ``ranked`` are the players with an amount, best first; ``name_of`` names a player as the rows do."""
    label = {"hps": "HPS", "dtps": "Damage taken/s"}.get(metric, "DPS")
    duration = snap.get("duration") if metric == "dps" else snap.get("recorded_duration")
    total = sum(_amount(p, metric) for p in ranked) or 1.0
    only = f" · {filtered}" if filtered and metric == "dps" else ""
    lines = [f"{label}{only} · {snap.get('boss') or 'combat'} · {_round(duration)}s"]
    lines += [f"{i}. {name_of(p)}  {theme.kfmt(_rate(p, metric))}/s  ({_round(100 * _amount(p, metric) / total)}%)"
              for i, p in enumerate(ranked, 1)]
    return "\n".join(lines + ["— Aion 2 Calc"])


def empty_text(answer: dict, everyone: list, metric: str, cleared: bool, filtered: str) -> str:
    """What the rows' place says when it has no rows (overlay.js ``empty``)."""
    snap = answer.get("snapshot") or {}
    if answer.get("error"):
        return str(answer["error"])
    if cleared:
        return "New fight — waiting for the first hit."
    if snap.get("battle_over") is True:
        return "Ready — waiting for the next fight."
    if everyone:
        if metric == "dps" and filtered:
            what = {"Boss damage only": "damage to bosses", "Player damage only": "damage to players"}.get(
                filtered, "damage to bosses or players")
            return f"No {what} in this combat ({filtered})."
        kind = {"hps": "healing", "dtps": "incoming damage"}.get(metric, "outgoing damage")
        return f"No recorded {kind} in this combat."
    if snap.get("warning"):
        return str(snap["warning"])
    return "Waiting for combat data…" if answer.get("running") is True else "No fight yet. Start the meter in the app."


def panel_reading(snap: dict, player: dict | None, buffs, extra, name: str, mine: bool) -> dict:
    """What the player panel shows for ``player`` (overlay.js ``renderDetail``): the head, the tiles with their
    tooltips, the top skills and the buffs on them. ``buffs`` is None while the app is still asked for them, and
    ``extra`` is the app's answer for the player (``/api/meter/player``), None until it comes."""
    if player is None:
        return {"missing": True, "name": "Player", "sub": "", "color": theme.FALLBACK_CLASS_COLOR,
                "line": "This player is no longer in the live view.", "tiles": [], "skills": [], "buffs": [],
                "buffs_note": ""}
    identity = snap.get("identity_status") or {}
    cp = player.get("combat_power") or (identity.get("local_combat_power") if mine else None) or None
    cls = str(player.get("class") or "")
    target = snap.get("current_target")
    where = target.get("name") if isinstance(target, dict) and not target.get("is_player") else snap.get("boss")
    line = (f"Target: {where} · " if where else "") + f"{fmt_secs(snap.get('duration'))} in combat"
    active = extra.get("active_seconds") if isinstance(extra, dict) else None
    active = active if isinstance(active, (int, float)) and not isinstance(active, bool) and math.isfinite(active) \
        else None
    incoming = player.get("incoming") if isinstance(player.get("incoming"), dict) else {}
    tiles = [("Total damage", theme.kfmt(player.get("damage"))), ("DPS", theme.kfmt(player.get("dps")) + "/s"),
             ("Contribution", _pct(player.get("share"))), ("Combat time", fmt_secs(snap.get("duration"))),
             ("Hits", _text(player.get("hits") or 0)), ("Parry", _pct(player.get("parry"))),
             ("Crit", _pct(player.get("crit"))), ("Front", _pct(player.get("front"))),
             ("Back", _pct(player.get("back"))), ("Perfect", _pct(player.get("perfect"))),
             ("Double", _pct(player.get("double"))), ("Parried in", _text(incoming.get("parries") or 0)),
             ("Shield blocks", _text(incoming.get("shield_blocks") or 0)),
             ("Endurance", _text(incoming.get("endurance") or 0))]
    titles = dict(TILE_TITLES, **{"Combat time": f"Fight time; this player dealt damage in {fmt_secs(active)} of it"
                                  if active is not None else "Fight time"})
    skills = [k for k in (player.get("skills") if isinstance(player.get("skills"), list) else []) if isinstance(k, dict)]
    skills = skills[:8]
    top = max([_num(k.get("damage")) for k in skills] + [1.0]) if skills else 1.0
    skill_lines = []
    for k in skills:
        hits = k.get("hits") or 0
        crit = f" · {_pct(k['crit'])}" if k.get("crit") is not None else ""
        tip = (f"{k.get('skill') or k.get('skill_id')}: {theme.kfmt(k.get('damage'))} over {_text(hits)} hits · avg "
               f"{theme.kfmt(_num(k.get('damage')) / _num(hits) if _num(hits) else 0)}"
               + (f" · crit {_pct(k['crit'])}" if k.get("crit") is not None else "")
               + (f" · back {_pct(k['back'])}" if k.get("back") is not None else "")
               + (f" · parried {_pct(k['parry'])}" if k.get("parry") is not None else ""))
        skill_lines.append({"initials": _initials(k.get("skill")), "name": str(k.get("skill") or k.get("skill_id")),
                            "fraction": _round(100 * _num(k.get("damage")) / top) / 100,
                            "value": f"{theme.kfmt(k.get('damage'))} · {_round(_num(k.get('share')) * 100)}% · "
                                     f"{_text(hits)}×{crit}", "tip": tip})
    buff_lines, note = [], ""
    if buffs is None:
        note = "Reading the buffs…"
    elif not buffs:
        note = "No buff records in this fight yet."
    for b in (buffs or [])[:10]:
        if not isinstance(b, dict):
            continue
        uptime = b.get("uptime_pct")
        buff_lines.append({"initials": _initials(b.get("skill")), "name": str(b.get("skill")),
                           "fraction": max(0, min(100, _round(uptime))) / 100,
                           "value": f"{_round(uptime)}% · {fmt_secs(b.get('seconds'))}",
                           "tip": f"{b.get('skill')}: {_text(uptime)}% of the fight ({fmt_secs(b.get('seconds'))}), "
                                  f"applied {_text(b.get('applications'))}×{', by this player' if b.get('self') else ''}"})
    return {"missing": False, "name": name, "sub": cls[:1].upper() + cls[1:] + (f" · CP {theme.kfmt(cp)}" if cp else ""),
            "color": theme.class_color(cls), "line": line + (" · you" if mine else ""),
            "tiles": [(label, value, titles.get(label, "")) for label, value in tiles],
            "skills": skill_lines, "buffs": buff_lines, "buffs_note": note}


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


def ping_texts(ping) -> tuple[str, str]:
    """The ping pill (overlay.js, the compact layout): the current round trip, and the whole of it for the tooltip."""
    if not isinstance(ping, dict):
        return "Ping —", "Ping: no recorded samples"
    ms = {k: theme.fixed(_num(ping.get(k)), 0) for k in ("current", "avg", "min", "max")}
    return (f"Ping {ms['current']} ms",
            f"Ping {ms['current']} ms · Avg {ms['avg']} ms · Min {ms['min']} / Max {ms['max']} ms")


def identity_line(snap: dict, everyone: list, visible: list, ranked: list, repeated: bool, show_cp: bool) -> tuple[str, bool]:
    """The identity line (overlay.js ``#ovidentity``) and whether all is well with it. All is well when you are
    named and no actor is in doubt; the compact layout then leaves the line out, your name, rank and combat power
    being on your row."""
    identity = snap.get("identity_status") if isinstance(snap.get("identity_status"), dict) else None
    missing = bool(everyone) and identity is not None and (
        not identity.get("self_identified") or _num(identity.get("unnamed_actors")) > 0)
    inferred = any(p.get("inferred_identity") for p in visible)
    self_name = identity.get("local_name") if identity else None
    if missing:
        first = (f"{'Self identified' if identity.get('self_identified') else 'Self identity not received — teleport or change instances to refresh it'}"
                 f" · {_text(identity.get('unnamed_actors'))} unnamed actors · {_text(identity.get('linked_pets'))} linked"
                 f" pets. Grouping needs recorded owner links.")
    elif self_name:
        me = next((i for i, p in enumerate(ranked) if str(p.get("name") or "").casefold() == str(self_name).casefold()),
                  -1)
        rank = f" · #{me + 1} of {len(ranked)}" if me >= 0 and len(ranked) > 1 else ""
        cp = identity.get("local_combat_power") if show_cp else None
        first = (f"You{rank} · your name comes with the next zone load" if _UNNAMED.fullmatch(str(self_name)) else
                 f"You: {self_name}{rank}{f' · CP {theme.kfmt(cp)}' if cp else ''}")
    else:
        first = ""
    parts = [first,
             "Matching names have separate combat actor IDs; names alone do not establish shared identity or "
             "ownership." if repeated else "",
             "Combined a player’s re-registered actor IDs (matched by name, class and timing)." if inferred else ""]
    return " ".join(part for part in parts if part), not missing and not repeated and bool(self_name)


class SparkGraph(QWidget):
    """The live graph of the party's total over the fight (overlay.js ``drawGraph``), and the player panel's
    smaller one of a player's DPS (``sparkLine``): one point per reading, the area under it shaded."""

    def __init__(self, parent=None, height: int = 34):
        super().__init__(parent)
        self.series: list[float] = []
        self.label = ""
        self.color = QColor(theme.COLORS["gold"])
        self.setFixedHeight(height)

    def set_series(self, series: list, label: str = "", color: str | None = None) -> None:
        self.series, self.label = [float(v) for v in series], label
        self.color = QColor(color or theme.COLORS["gold"])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 8 if self.height() > 20 else 3, 8 if self.height() > 20 else 3)
        painter.fillPath(path, QColor(255, 255, 255, 13))
        painter.setClipPath(path)
        if len(self.series) >= 2:
            top, n = max(max(self.series), 1.0), len(self.series)
            points = [(rect.width() * i / (n - 1), rect.height() - rect.height() * v / top)
                      for i, v in enumerate(self.series)]
            line = QPainterPath()
            line.moveTo(*points[0])
            for x, y in points[1:]:
                line.lineTo(x, y)
            area = QPainterPath(line)
            area.lineTo(rect.width(), rect.height())
            area.lineTo(0, rect.height())
            area.closeSubpath()
            fill = QColor(self.color)
            fill.setAlphaF(0.2)
            painter.fillPath(area, fill)
            pen = QPen(self.color, 1.4)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawPath(line)
        if self.label:
            font = QFont(self.font())
            font.setPixelSize(9)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 160))      # the label's shadow, under it
            painter.drawText(QRectF(5, 3, rect.width() - 10, 12), Qt.AlignLeft | Qt.AlignVCenter, self.label)
            painter.setPen(QColor("#cdd6e6"))
            painter.drawText(QRectF(5, 2, rect.width() - 10, 12), Qt.AlignLeft | Qt.AlignVCenter, self.label)


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


class MiniBar(HpBar):
    """A skill's or a buff's bar in the player panel: gold, 54 px by 5 (overlay.css ``.ovdskbar``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(theme.COLORS["gold"])
        self.setFixedSize(54, 5)


class SkillLine(QWidget):
    """One skill or buff in the player panel: its icon's initials, its name, a bar and the numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.icon = QLabel(self)
        self.icon.setObjectName("ovdicon")
        self.icon.setFixedSize(20, 20)
        self.icon.setAlignment(Qt.AlignCenter)
        self.name = QLabel(self)
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # a long name gives way to the bar
        self.bar = MiniBar(self)
        self.value = QLabel(self)
        self.value.setObjectName("ovdval")
        box.addWidget(self.icon)
        box.addWidget(self.name, 1)
        box.addWidget(self.bar)
        box.addWidget(self.value)

    def set_line(self, line: dict) -> None:
        self.icon.setText(line["initials"])
        self.name.setText(line["name"])
        self.bar.set_fraction(line["fraction"])
        self.value.setText(line["value"])
        self.setToolTip(line["tip"])

    def texts(self) -> list[str]:
        return [self.icon.text(), self.name.text(), self.value.text()]


class PlayerPanel(QFrame):
    """The player panel under the rows (overlay.js ``renderDetail``): one player's totals and special hits as
    tiles, their top skills and the buffs on them with their uptime, drawn from ``panel_reading``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reading: dict = {}
        self.columns = 0
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 8, 10, 9)
        box.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.swatch = QLabel(self)
        self.swatch.setFixedSize(10, 10)
        self.name = QLabel(self)
        self.name.setObjectName("ovdname")
        self.sub = QLabel(self)
        self.sub.setObjectName("ovdsub")
        self.sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.close_button = QPushButton("✕", self)
        self.close_button.setObjectName("ovdclose")
        self.close_button.setToolTip("Close the player panel")
        self.close_button.setCursor(Qt.PointingHandCursor)
        head.addWidget(self.swatch)
        head.addWidget(self.name)
        head.addWidget(self.sub, 1)
        head.addWidget(self.close_button)
        box.addLayout(head)
        self.line = QLabel(self)
        self.line.setObjectName("ovdsub")
        self.line.setWordWrap(True)
        box.addWidget(self.line)
        self.spark = SparkGraph(self, 16)         # the player's DPS over the fight, with the live graph on
        self.spark.setToolTip("This player's DPS over the fight, one point per reading")
        self.spark.hide()
        box.addWidget(self.spark)
        self.tiles_box = QGridLayout()
        self.tiles_box.setSpacing(4)
        box.addLayout(self.tiles_box)
        self.tiles: list[QLabel] = []
        self.skills_head = QLabel("Top skills", self)
        self.skills_head.setObjectName("ovdsec")
        box.addWidget(self.skills_head)
        self.skills_box = QVBoxLayout()
        self.skills_box.setSpacing(2)
        box.addLayout(self.skills_box)
        self.buffs_head = QLabel("Buff uptime", self)
        self.buffs_head.setObjectName("ovdsec")
        box.addWidget(self.buffs_head)
        self.buffs_note = QLabel(self)
        self.buffs_note.setObjectName("ovnote")
        box.addWidget(self.buffs_note)
        self.buffs_box = QVBoxLayout()
        self.buffs_box.setSpacing(2)
        box.addLayout(self.buffs_box)
        self.skill_lines: list[SkillLine] = []
        self.buff_lines: list[SkillLine] = []

    def set_reading(self, reading: dict, columns: int) -> None:
        if reading == self.reading and columns == self.columns:
            return
        self.reading = reading
        self.swatch.setStyleSheet(f"background: {reading['color']}; border-radius: 2px;")
        self.swatch.setVisible(not reading["missing"])
        self.name.setText(reading["name"])
        self.sub.setText(reading["sub"])
        self.line.setText(reading["line"])
        px = self.font().pixelSize() if self.font().pixelSize() > 0 else 12
        columns, added = max(1, columns), False
        while len(self.tiles) < len(reading["tiles"]):
            tile = QLabel(self)
            tile.setObjectName("ovdtile")
            tile.setTextFormat(Qt.RichText)
            self.tiles.append(tile)
            added = True
        if added or columns != self.columns:      # the tiles fill the panel's width, 92 px or more each
            self.columns = columns
            for tile in self.tiles:
                self.tiles_box.removeWidget(tile)
            for index, tile in enumerate(self.tiles):
                self.tiles_box.addWidget(tile, index // columns, index % columns)
        for index, tile in enumerate(self.tiles):
            if index >= len(reading["tiles"]):
                tile.hide()
                continue
            label, value, title = reading["tiles"][index]
            tile.setText(f"<div style='font-size:{round(px * 1.05)}px; font-weight:700; color:#ffffff'>"
                         f"{html.escape(value)}</div><div style='font-size:{round(px * 0.78)}px; color:#9aa8bb'>"
                         f"{html.escape(label.upper())}</div>")
            tile.setToolTip(title)
            tile.show()
        self._lines(self.skill_lines, self.skills_box, reading["skills"])
        self._lines(self.buff_lines, self.buffs_box, reading["buffs"])
        self.skills_head.setVisible(bool(reading["skills"]))
        self.buffs_head.setVisible(not reading["missing"])
        self.buffs_note.setText(reading["buffs_note"])
        self.buffs_note.setVisible(bool(reading["buffs_note"]))

    def _lines(self, pool: list, box: QVBoxLayout, lines: list) -> None:
        while len(pool) < len(lines):
            line = SkillLine(self)
            box.addWidget(line)
            pool.append(line)
        for index, widget in enumerate(pool):
            if index < len(lines):
                widget.set_line(lines[index])
                widget.show()
            else:
                widget.hide()

    def set_spark(self, series: list, color: str | None) -> None:
        self.spark.setVisible(len(series) >= 2)
        if len(series) >= 2:
            self.spark.set_series(series, "", color)

    def tile_values(self) -> dict:
        return {label: value for label, value, _title in self.reading.get("tiles", [])}

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.fillPath(path, QColor(27, 32, 42, 235))
        painter.setPen(QColor(233, 203, 128, 90))
        painter.drawPath(path)


class _Pill(QWidget):
    """The toolbar's and the options' own backing, a dark rounded pill, where the card does not paint behind them
    (the top-portion and none background modes), as the web overlay's ``--nm-float``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filled = False

    def paintEvent(self, event):
        if not self.filled:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 7, 7)
        painter.fillPath(path, QColor(14, 16, 20, 230))


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
        self.key, self.open = "", False           # the player's row key, and whether their panel is open
        self.actor, self.crank = "", ""           # "#id" beside a name two players share; the community standing
        self.target, self.amount = 0.0, 0.0       # the reading's rate and amount, for the live tick
        self.color = QColor(theme.FALLBACK_CLASS_COLOR)
        self.setFixedHeight(22)
        self.setCursor(Qt.PointingHandCursor)     # a click opens the player's panel

    def set_player(self, name: str, cls: str, rate: str, share: str, fill: float, mine: bool,
                   index: int = 0, dead: bool = False, cp: str = "", look: RowLook | None = None,
                   key: str = "", open_: bool = False, actor: str = "", crank: str = "") -> None:
        look = look or self.look
        self.key = key
        state = (name, cls, rate, share, round(fill, 4), mine, index, dead, cp, open_, actor, crank,
                 tuple(sorted(vars(look).items())))
        if state == getattr(self, "_state", None):
            return
        self._state = state
        self.name, self.rate, self.share, self.fill, self.mine = name, rate, share, max(0.0, min(1.0, fill)), mine
        self.index, self.dead, self.cp, self.look, self.open = index, dead, cp, look, open_
        self.actor, self.crank = actor, crank
        self.color = QColor(theme.class_color(cls))
        self.update()

    def set_live(self, rate: str, fill: float) -> None:
        """Live-ticking DPS between readings: the rate and its bar, eased toward the rate the fight is heading for."""
        fill = max(0.0, min(1.0, fill))
        if rate == self.rate and abs(fill - self.fill) < 0.0005:
            return
        self.rate, self.fill = rate, fill
        self._state = None                        # the next reading draws the row whole again
        self.update()

    def segments(self) -> list[tuple[str, str]]:
        """The row's left-hand text in its parts, each with what it is: the rank and the name, the actor id beside a
        name two players share, the community standing and the combat power."""
        parts = [((f"{self.index + 1}. " if self.look.rank_numbers else "") + self.name, "name")]
        parts += [(text, kind) for text, kind in ((self.actor, "actor"), (self.crank, "crank"), (self.cp, "cp")) if text]
        return parts

    def label(self) -> str:
        """The row's left-hand text: the rank, the name, the actor id, the community standing and the combat power."""
        return "  ".join(text for text, _kind in self.segments())

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
        painter.setPen(QColor(theme.COLORS["text"]))
        right = self.right()
        painter.drawText(QRectF(left, rect.y(), rect.right() - 7 - left, rect.height()),
                         Qt.AlignVCenter | Qt.AlignRight, right)
        end = rect.right() - 7 - QFontMetricsF(font).horizontalAdvance(right) - 8   # the name stops short of the rate
        small = QFont(font)
        small.setBold(False)
        small.setPixelSize(max(8, round((font.pixelSize() if font.pixelSize() > 0 else 12) * 0.78)))
        colours = {"name": self.color.lighter(150) if look.class_names else QColor(theme.COLORS["text"]),
                   "actor": QColor("#aab3c5"), "crank": QColor(theme.COLORS["gold"]), "cp": QColor("#63d3e6")}
        for text, kind in self.segments():
            if left >= end:
                break
            part = QFont(font if kind == "name" else small)
            part.setBold(kind == "crank" or (kind == "name" and self.mine))
            part.setUnderline(kind == "name" and self.open)   # the row whose panel is open (``.ovrow-detail``)
            metrics = QFontMetricsF(part)
            text = metrics.elidedText(text, Qt.ElideRight, end - left)
            painter.setFont(part)
            painter.setPen(colours[kind])
            painter.drawText(QRectF(left, rect.y(), end - left, rect.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
            left += metrics.horizontalAdvance(text) + 5


class MeterOverlay(QWidget):
    """The meter overlay window. ``api`` is the app's local API (None in tests, which hand it the readings), and
    ``store`` keeps what the web overlay keeps in the page's own storage: the opacity and the metric shown."""

    def __init__(self, api: AppApi | None = None, parent_process=None, store: QSettings | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Aion 2 Calc overlay")
        self.api, self.parent_process, self.store = api, parent_process, store
        self.ui: dict = {}
        self.answer: dict = {}
        self.rate_metric = "dps"                 # not ``metric``: QWidget.metric() is Qt's own
        self.click_through = False
        self.locked = False                      # frozen in place for a screenshot
        self.cleared_fight: str | None = None    # New pressed: the fight then shown, until the next one begins
        self.copy_text = ""
        self.detail_key: str | None = None       # the player whose panel is open
        self.detail_buffs: list | None = None    # their buffs, None while the app is asked for them
        self.detail_extra: dict | None = None
        self.detail_at = 0.0
        self.detail_busy = False
        self._drag: QPoint | None = None
        self._press: QPoint | None = None        # where a press began, to tell a click from a move
        self._capture_busy = False
        self._seqs: dict = {}                    # the app's command counters as first read (the screenshot hotkey)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = _Card(self)
        outer.addWidget(self.card)
        box = QVBoxLayout(self.card)
        box.setContentsMargins(10, 8, 10, 9)
        box.setSpacing(4)
        head = QHBoxLayout()
        self.mark = QFrame()                      # green while the fight runs, amber while the DPS clock is paused
        self.mark.setFixedSize(3, 14)
        self.mark.hide()
        self._mark_colour = ""
        head.addWidget(self.mark)
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
        self.warning = QLabel("")                 # the meter's warning over the rows
        self.warning.setObjectName("ovnote")
        self.warning.setWordWrap(True)
        box.addWidget(self.warning)
        self.empty = QLabel("")                   # the rows' place when there are none to show
        self.empty.setObjectName("ovnote")
        self.empty.setWordWrap(True)
        box.addWidget(self.empty)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(2)
        box.addLayout(self.rows_box)
        self.panel = PlayerPanel()
        self.panel.close_button.clicked.connect(self.close_detail)
        self.panel_scroll = QScrollArea(self.card)  # the panel scrolls within the room the screen leaves it
        self.panel_scroll.setWidget(self.panel)
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll.viewport().setAutoFillBackground(False)
        self.panel_scroll.hide()
        box.addWidget(self.panel_scroll)
        self.graph = SparkGraph(self.card)        # the party's total over the fight (overlay_dps_graph)
        self.graph.setToolTip("The party's total over the fight, one point per reading")
        self.graph.hide()
        box.addWidget(self.graph)
        self.cooldowns = CooldownStrip(self.card)  # below the meter, the web overlay's default; the setting moves it
        box.addWidget(self.cooldowns)
        foot = QHBoxLayout()                      # the identity line and the ping, over the toolbar
        foot.setSpacing(8)
        self.identity = QLabel("")                # who you are, and the actors in doubt (overlay.js ``#ovidentity``)
        self.identity.setObjectName("ovidentity")
        self.identity.setWordWrap(True)
        self.identity.hide()
        foot.addWidget(self.identity, 1)
        self.ping = QLabel("")                    # the capture's round trip (overlay.js ``#ovping``)
        self.ping.setObjectName("ovping")
        foot.addWidget(self.ping, 0, Qt.AlignRight | Qt.AlignTop)
        box.addLayout(foot)
        self.toolbar = _Pill(self.card)
        tools = QHBoxLayout(self.toolbar)
        tools.setContentsMargins(3, 1, 3, 1)
        tools.setSpacing(2)
        tools.addStretch(1)
        self.tools: dict[str, QPushButton] = {}
        actions = {"lock": self.toggle_lock, "split": self.new_fight, "copy": self.copy,
                   "options": self.toggle_options, "capture": self.toggle_capture, "hide": self.hide_overlay}
        for key, text, tip in TOOLS:
            button = QPushButton(text, self.toolbar)
            button.setObjectName("ovtool")
            button.setToolTip(tip)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("state", "")
            button.clicked.connect(actions[key])
            tools.addWidget(button)
            self.tools[key] = button
        self.tools["options"].setCheckable(True)
        box.addWidget(self.toolbar)
        self.options = _Pill(self.card)            # Options: the pet grouping, the damage filters and the opacity
        options = QVBoxLayout(self.options)
        options.setContentsMargins(10, 5, 10, 5)
        options.setSpacing(2)
        self.combine = QCheckBox("Combine pets with owner", self.options)
        self.combine.setToolTip("Group recorded pet damage and healing into the linked owner")
        self.combine.setChecked(True)
        self.combine.clicked.connect(self._combine_clicked)
        self.boss_only = QCheckBox("Boss damage only", self.options)
        self.boss_only.setToolTip("Count only the damage dealt to bosses: dungeon bosses, mini-bosses, field and "
                                  "world bosses. Damage to trash mobs and, in the open world (the Abyss), to other "
                                  "players is left out")
        self.boss_only.clicked.connect(lambda checked: self._filter_clicked("overlay_boss_only", checked))
        self.pvp_only = QCheckBox("Player (PvP) damage only", self.options)
        self.pvp_only.setToolTip("Count only the damage dealt to other players (PvP), leaving out damage to monsters. "
                                 "With Boss damage only also on, damage to bosses counts too")
        self.pvp_only.clicked.connect(lambda checked: self._filter_clicked("overlay_pvp_only", checked))
        for check in (self.combine, self.boss_only, self.pvp_only):
            options.addWidget(check)
        fade = QHBoxLayout()
        fade.addWidget(QLabel("Opacity", self.options))
        self.slider = QSlider(Qt.Horizontal, self.options)
        self.slider.setRange(20, 100)
        self.slider.setToolTip("The card's opacity behind the readings")
        fade.addWidget(self.slider, 1)
        options.addLayout(fade)
        self.message = QLabel("", self.options)   # why an option could not be changed
        self.message.setObjectName("ovnote")
        self.message.setWordWrap(True)
        self.message.hide()
        options.addWidget(self.message)
        self.options.hide()
        box.addWidget(self.options)
        self.rows: list[PlayerRow] = []
        self.look = RowLook({})
        self._cooldowns_top = False
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.timeout.connect(lambda: self.cooldowns.tick(time.monotonic()))
        self._cooldown_timer.start(250)
        self._graph: list[tuple] = []             # the party's DPS, HPS and damage taken, one reading each
        self._graph_duration = -1.0
        self._graphed = None                      # the answer last put on the graph
        self._player_hist: dict[str, list] = {}   # each player's DPS, for the panel's sparkline
        self._interpolate, self._perf = False, False
        self._shown_rates: dict[str, float] = {}  # the rates the rows show while they tick between readings
        self._render_at, self._projecting, self._cur_max = time.monotonic(), False, 1.0
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._live_tick)
        self._pollers: list[Poller] = []
        self._meter_poller = self._settings_poller = None
        self.requests = Requests(api, self) if api is not None else None
        if self.requests is not None:
            self.requests.replied.connect(self._replied)
            self.requests.failed.connect(self._failed)
        self.set_opacity(self._stored("opacity", DEFAULT_OPACITY, float))
        self.slider.valueChanged.connect(lambda value: self.set_opacity(value / 100))
        self._style()
        self.set_metric(self._stored("metric", "dps", str))
        self.apply_ui({})
        self.apply_meter({})
        if api is not None:
            self._meter_poller = Poller(api, "/api/meter?view=latest", 500, self)
            self._meter_poller.answered.connect(self._meter_answered)
            self._meter_poller.failed.connect(self._meter_failed)
            self._settings_poller = Poller(api, "/api/ui", 3000, self)
            self._settings_poller.answered.connect(self.apply_ui)
            commands = Poller(api, "/api/overlay/commands", 1000, self)   # the screenshot hotkey, Open overlay
            commands.answered.connect(self._commands)
            self._pollers = [self._meter_poller, self._settings_poller, commands]
        if parent_process is not None and getattr(parent_process, "watched", lambda: False)():
            self._parent_timer = QTimer(self)
            self._parent_timer.timeout.connect(self._check_parent)
            self._parent_timer.start(2000)

    def start(self) -> None:
        for poller in self._pollers:
            poller.start()

    def _stored(self, key: str, default, kind):
        """A value the overlay kept (``store``), or ``default`` when there is none or it cannot be read."""
        if self.store is None:
            return default
        try:
            return self.store.value(key, default, type=kind)
        except (TypeError, ValueError):
            return default

    def _check_parent(self) -> None:
        if not self.parent_process.alive():
            QApplication.quit()

    def closeEvent(self, event):
        for poller in self._pollers:
            poller.stop()
        if self.requests is not None:
            self.requests.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------ look
    def _style(self) -> None:
        scale = max(50, min(200, int(self.ui.get("overlay_font_scale") or 100))) / 100
        weight = int(self.ui.get("overlay_font_weight") or 600)
        px = max(8, round(12 * scale))
        font = QFont(theme.FONT_FAMILIES[0])
        font.setFamilies(theme.FONT_FAMILIES)
        font.setPixelSize(px)
        font.setWeight(QFont.Weight(max(100, min(900, weight))))
        if font != self.font():
            self.setFont(font)
        c = theme.COLORS
        sheet = (
            f"QLabel {{ color: {c['text']}; background: transparent; }}"
            f"QLabel#ovstatus {{ color: {c['gold']}; font-weight: 700; }}"
            f"QLabel#ovlines {{ color: #e9edf1; }}"
            f"QLabel#ovextra, QLabel#ovnote {{ color: {c['muted']}; }}"
            f"QLabel#ovidentity {{ color: {c['gold']}; font-size: {round(px * 0.85)}px; }}"
            f"QLabel#ovping {{ color: #c9d1db; font-weight: 600; font-size: {round(px * 0.9)}px; }}"
            f"QPushButton {{ color: {c['muted']}; background: transparent; border: none; padding: 0 3px; }}"
            f"QPushButton:checked {{ color: {c['gold']}; text-decoration: underline; }}"
            f"QPushButton#ovtool {{ color: #c9d1db; background: rgba(255, 255, 255, 14); border-radius: 6px;"
            f" padding: 2px 7px; }}"
            f"QPushButton#ovtool:hover {{ background: rgba(255, 255, 255, 30); color: #ffffff; }}"
            f"QPushButton#ovtool:checked {{ color: #39c2e0; text-decoration: none; }}"
            f"QPushButton#ovtool:disabled {{ color: #6b7385; }}"
            f"QPushButton#ovtool[state=\"on\"], QPushButton#ovtool[state=\"ok\"],"
            f" QPushButton#ovtool[state=\"start\"] {{ color: #6fe3a3; }}"
            f"QPushButton#ovtool[state=\"err\"], QPushButton#ovtool[state=\"stop\"] {{ color: #ff8585; }}"
            f"QCheckBox {{ color: #9aa8bb; background: transparent; spacing: 5px; }}"
            f"QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid {c['line2']}; border-radius: 3px;"
            f" background: {c['bg2']}; }}"
            f"QCheckBox::indicator:checked {{ background: {c['gold']}; border-color: {c['gold']}; }}"
            f"QScrollArea {{ background: transparent; }}"
            f"QLabel#ovdname {{ color: #e9f7ff; font-weight: 800; font-size: {round(px * 1.15)}px; }}"
            f"QLabel#ovdsub {{ color: #9aa8bb; font-size: {round(px * 0.9)}px; }}"
            f"QLabel#ovdsec {{ color: {c['gold']}; font-weight: 700; font-size: {round(px * 0.85)}px; }}"
            f"QLabel#ovdtile {{ background: rgba(255, 255, 255, 15); border-radius: 6px; padding: 4px 6px; }}"
            f"QLabel#ovdicon {{ background: rgba(0, 0, 0, 102); border-radius: 4px; color: #cdd6e6; font-size: 9px; }}"
            f"QLabel#ovdval {{ color: #9aa8bb; }}"
            f"QPushButton#ovdclose {{ color: #9aa8bb; font-size: {round(px * 1.15)}px; }}"
            f"QPushButton#ovdclose:hover {{ color: #ffffff; }}")
        if sheet != getattr(self, "_sheet", None):    # the settings come every 3 s: restyle only on a change
            self._sheet = sheet
            self.setStyleSheet(sheet)
            self.panel.reading = {}               # the tiles' sizes follow the font: draw the panel again

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
        for pill in (self.toolbar, self.options):
            pill.filled = self.card.mode != "card"
            pill.update()
        top = ui.get("overlay_cooldowns_position") == "top"
        if top != self._cooldowns_top:            # the strip above the player rows, or below them
            self._cooldowns_top = top
            self.box.removeWidget(self.cooldowns)
            self.box.insertWidget(self.box.indexOf(self.extra) + 1 if top else self.box.indexOf(self.graph) + 1,
                                  self.cooldowns)
        for check, key in ((self.boss_only, "overlay_boss_only"), (self.pvp_only, "overlay_pvp_only")):
            if check.isEnabled():                 # the saved filters; the meter's answer names them too
                check.setChecked(ui.get(key) is True)
        # Performance mode (Settings → App & data): the overlay reads the meter half as often and holds still between
        # readings, the rows' live tick off, the cooldown strip counting down half as often.
        self._perf = ui.get("performance_mode") is True
        self._interpolate = ui.get("overlay_dps_interpolate") is True and not self._perf
        if self._interpolate:
            self._tick_timer.start(_setting(ui.get("overlay_interpolate_ms"), 50, 1000, 200))
        else:
            self._tick_timer.stop()
            self._shown_rates.clear()
        self._cooldown_timer.setInterval(500 if self._perf else 250)
        if ui.get("overlay_dps_graph") is not True:
            self._graph, self._player_hist = [], {}
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
        if self.store is not None:
            self.store.setValue("metric", self.rate_metric)
        self._shown_rates.clear()                 # the rows tick from the new metric's rates, not the old one's
        self.apply_meter(self.answer)

    def set_opacity(self, value: float) -> None:
        """The card's opacity, 20% to 100% (the web overlay's slider), kept for the next time."""
        value = max(0.2, min(1.0, float(value)))
        self.card.opacity = value
        self.card.update()
        if self.slider.value() != round(value * 100):
            self.slider.blockSignals(True)
            self.slider.setValue(round(value * 100))
            self.slider.blockSignals(False)
        if self.store is not None:
            self.store.setValue("opacity", value)

    # ------------------------------------------------------------------ reading
    def _meter_answered(self, answer) -> None:
        if not self.locked:                       # locked, the overlay holds the reading it shows
            self.apply_meter(answer)

    def _meter_failed(self, why: str) -> None:
        if not self.locked:
            self.status.setText("The app does not answer")

    def _names(self, player: dict) -> tuple[str, bool, bool]:
        """A player's name as the rows show it, whether it is you, and whether you are still unnamed."""
        identity = (self.answer.get("snapshot") or {}).get("identity_status") or {}
        local = str(identity.get("local_name") or "").casefold()
        local_id = identity.get("local_id")
        name = str(player.get("name") or "")
        mine = bool(local) and name.casefold() == local
        unnamed = local_id is not None and str(player.get("id")) == str(local_id) and bool(_UNNAMED.fullmatch(name))
        return self.look.display_name(player, mine, unnamed), mine, unnamed

    def apply_meter(self, answer: dict) -> None:
        """Draw the meter's reading (the app's answer to ``/api/meter?view=latest``)."""
        if not isinstance(answer, dict):
            return
        self.answer = answer
        ui, look, metric = self.ui, self.look, self.rate_metric
        snap = answer.get("snapshot") if isinstance(answer.get("snapshot"), dict) else {}
        segment = snap.get("selected_segment")
        if self.cleared_fight is not None and ("" if segment is None else str(segment)) != self.cleared_fight:
            self.cleared_fight = None             # the next fight began: its first hit gave it an id of its own
        cleared = self.cleared_fight is not None
        running, over = answer.get("running") is True, snap.get("battle_over") is True
        paused = snap.get("paused") is True
        everyone = [] if cleared else [p for p in (snap.get("players") or []) if isinstance(p, dict)]
        players = [p for p in everyone if _amount(p, metric) > 0]
        players.sort(key=lambda p: (_rate(p, metric), _amount(p, metric)), reverse=True)
        names: dict[str, int] = {}
        for player in players:
            name = str(player.get("name") or "").casefold()
            names[name] = names.get(name, 0) + 1
        repeated = any(count > 1 for count in names.values())   # two rows of one name: separate actors
        limit = max(1, min(24, int(ui.get("overlay_max_players") or 8)))
        if look.auto_expand:
            limit = min(24, max(limit, len(players)))
        total_rate = sum(_rate(p, metric) for p in players)
        total_amount = sum(_amount(p, metric) for p in players) or 1.0
        label = dict(METRICS)[metric]
        filtered = filter_label(answer)
        # Only in combat (the web overlay's ``collapse``): between fights the overlay keeps its header alone.
        idle = ui.get("overlay_only_in_combat") is True and (
            not running or over or (paused and snap.get("boss_alive") is not True))
        shown = [] if idle or over else players[:limit]   # a fight that is over says it is ready for the next
        top = max([_rate(p, metric) for p in everyone] + [1.0])   # the rate a whole bar stands for
        if idle:
            status = "Idle · waiting for combat" if running else "Idle"
        elif answer.get("error"):
            status = f"Capture stopped: {answer['error']}"
        elif cleared:
            status = "New fight · waiting for combat"
        elif not running and not players:
            status = "Idle"
        elif not players:
            status = "Idle · waiting for combat"
        else:
            boss = snap.get("boss") or "Combat"
            pause = "Paused DPS · " if paused and metric == "dps" else ""
            status = f"{pause}{boss} · {_round(snap.get('duration'))}s · {theme.kfmt(total_rate)} raid {label}"
            if filtered and metric == "dps":
                status += f" · {filtered}"
            backlog = snap.get("decode_backlog") or {}
            if isinstance(backlog, dict) and backlog.get("catching_up"):
                status += f" · catching up ({backlog.get('queue_depth')})"
        self.status.setText(status)
        # The fight's mark (the compact layout's clock): green while it runs, amber while the DPS clock is paused.
        colour = "#5ee04a" if running and not paused else "#e3b35a" if paused else "#6b7380"
        if colour != self._mark_colour:
            self._mark_colour = colour
            self.mark.setStyleSheet(f"background: {colour}; border-radius: 1px;")
        self.mark.setVisible(not idle and not over and not cleared and bool(players))
        self.copy_text = leaderboard_text(snap, players, metric, filtered, lambda p: self._names(p)[0])
        target = snap.get("current_target")
        if (idle or over or cleared or not isinstance(target, dict) or target.get("is_player")
                or not target.get("contributors")):
            target = None                         # the web overlay's target panel needs damage dealt to it
        self._show_target(target)
        lines = counter_lines(snap)
        if lines and not idle:
            full = "    ".join(text for _key, text, _short in lines)
            fits = self.lines.fontMetrics().horizontalAdvance(full) <= self.width() - 24
            self.lines.setText(full if fits else "  ·  ".join(short for _key, _text, short in lines))
            self.lines.setToolTip("\n".join(text for _key, text, _short in lines))
            self.lines.show()
        else:
            self.lines.hide()
        self._show_extra(snap, idle or over or cleared, metric)
        warning = snap.get("warning") if not idle and not over and everyone else None
        self.warning.setText(str(warning or ""))
        self.warning.setVisible(bool(warning))
        empty = "" if idle or shown else empty_text(answer, everyone, metric, cleared, filtered)
        self.empty.setText(empty)
        self.empty.setVisible(bool(empty))
        cooling = (ui.get("overlay_show_cooldowns") is True and running and not idle
                   and (snap.get("cooldowns") or snap.get("chain_windows")))
        if cooling:
            self.cooldowns.set_reading(snap.get("cooldowns"), snap.get("chain_windows"),
                                       ui.get("overlay_cooldowns_max") or 8, time.monotonic())
        self.cooldowns.setVisible(bool(cooling))
        if answer is not self._graphed:           # a new reading, not the same one drawn again
            self._graphed = answer
            self._record_graph(answer, snap, everyone)
        self._draw_graph(idle)
        text, fine = identity_line(snap, everyone, players, players, repeated,
                                   ui.get("overlay_show_combat_power") is not False)
        self.identity.setText(text)
        self.identity.setVisible(bool(text) and not fine and not idle)
        ping, whole = ping_texts(snap.get("ping"))
        self.ping.setText(ping)
        self.ping.setVisible(not idle)
        self.ping.setToolTip(f"{whole} — Passive TCP RTT for this recording connection; average/minimum/maximum "
                             f"across the capture")
        identity = snap.get("identity_status") or {}
        local_cp = identity.get("local_combat_power")
        # Live-ticking DPS between readings (overlay_dps_interpolate): the rows ease from the rates they show.
        self._render_at, self._projecting, self._cur_max = time.monotonic(), running and not paused, top
        ticking = self._interpolate and not self.locked
        ranks = ui.get("overlay_show_community_rank") is True
        while len(self.rows) < len(shown):
            row = PlayerRow(self.card)
            row.setFixedHeight(max(16, min(48, int(ui.get("overlay_row_height") or 22))))
            self.rows_box.addWidget(row)
            self.rows.append(row)
        for index, row in enumerate(self.rows):
            if index >= len(shown):
                row.hide()
                continue
            player = shown[index]
            name, mine, _unnamed = self._names(player)
            cp = 0.0
            if look.show_cp:
                cp = float(player.get("combat_power") or (local_cp if mine else 0) or 0)
            key = _key(player)
            rate = _rate(player, metric)
            row.target, row.amount = rate, _amount(player, metric)
            showing = self._shown_rates.get(key, rate) if ticking else rate
            shared = names.get(str(player.get("name") or "").casefold(), 0) > 1
            rank = player.get("community_rank") if isinstance(player.get("community_rank"), dict) else {}
            row.set_player(name, str(player.get("class") or ""), f"{theme.kfmt(showing)}/s",
                           f"{_round(100 * _amount(player, metric) / total_amount)}%", showing / top,
                           mine, index, look.show_deaths and player.get("dead") is True,
                           theme.sfmt(cp) if cp > 0 else "", look, key, key == self.detail_key,
                           f"#{player.get('id')}" if look.name_mode == "name" and shared else "",
                           str(rank.get("text") or "") if ranks else "")
            row.setToolTip(f"{player.get('name')} · Actor {player.get('key') or player.get('id')}"
                           f"{' · Includes linked pets' if player.get('includes_pets') else ''}"
                           f" · Click for this player's details")
            row.show()
        self._show_panel(snap, everyone, idle or over or cleared)
        self._sync_tools()
        if self._meter_poller is not None:        # twice a second in a fight, once a second out of one
            self._meter_poller.set_interval((500 if running else 1000) * (2 if self._perf else 1))
        self._relayout()
        first = next((row for row in self.rows if not row.isHidden()), None)
        self.card.rows_top = first.geometry().top() if first is not None else None
        self.card.update()

    def _record_graph(self, answer: dict, snap: dict, everyone: list) -> None:
        """One reading on the live graph (overlay.js ``recordGraph``): the party's totals while the fight runs, and
        each player's DPS for their panel. Every point is the meter's own reading; a fight clock that went back means
        a new fight, and the graph starts over."""
        if self.ui.get("overlay_dps_graph") is not True:
            self._graph, self._player_hist = [], {}
            return
        duration = _num(snap.get("duration"))
        if duration + 0.001 < self._graph_duration:
            self._graph, self._player_hist = [], {}
        self._graph_duration = duration
        if answer.get("running") is True and snap.get("paused") is not True and snap.get("battle_over") is not True:
            self._graph.append(tuple(sum(_num(p.get(key)) for p in everyone) for key in ("dps", "hps", "dtps")))
            del self._graph[:-GRAPH_LIMIT]
            for player in everyone:
                history = self._player_hist.setdefault(_key(player), [])
                history.append(_num(player.get("dps")))
                del history[:-GRAPH_LIMIT]

    def _draw_graph(self, hidden: bool) -> None:
        column = {"dps": 0, "hps": 1, "dtps": 2}[self.rate_metric]
        series = [sample[column] for sample in self._graph]
        shown = self.ui.get("overlay_dps_graph") is True and len(series) >= 2 and not hidden
        if shown:
            label = {"hps": "HPS", "dtps": "Taken"}.get(self.rate_metric, "DPS")
            self.graph.set_series(series, f"{label} · now {theme.kfmt(series[-1])} · peak "
                                          f"{theme.kfmt(max(max(series), 1.0))}")
        self.graph.setVisible(shown)

    def _live_tick(self) -> None:
        """Between readings each row's rate heads for what the fight's elapsing time makes of it: the damage stays
        the meter's, only the time it is divided by goes on (overlay.js ``liveTick``). It runs while the fight does,
        eases 40% of the way each tick, and holds once there."""
        if not self._interpolate or self.locked:
            return
        elapsed = max(0.0, time.monotonic() - self._render_at) if self._projecting else 0.0
        seen = set()
        for row in self.rows:
            if row.isHidden() or not row.key:
                continue
            seen.add(row.key)
            target, amount = getattr(row, "target", 0.0), getattr(row, "amount", 0.0)
            live = (amount * target) / (amount + target * elapsed) if elapsed > 0 and amount > 0 and target > 0 \
                else target
            current = self._shown_rates.get(row.key, live)
            step = current + (live - current) * 0.4
            shown = live if abs(step - live) < 0.5 else step
            self._shown_rates[row.key] = shown
            row.set_live(f"{theme.kfmt(shown)}/s", shown / self._cur_max)
        for key in [key for key in self._shown_rates if key not in seen]:
            del self._shown_rates[key]

    def _show_target(self, target) -> None:
        """The target line: its name, its HP when that is on, the time to kill with the enrage timer, and the break
        gauge, with their bars."""
        ui = self.ui
        if ui.get("overlay_show_target", True) is False or not isinstance(target, dict) or not target.get("name"):
            for widget in (self.target, self.hp, self.gauge):
                widget.hide()
            return
        also = [str(name) for name in (target.get("also_targets") or [])]
        parts = [str(target["name"]) + (f" +{len(also)}" if also else "")]   # the others struck in the same instant
        self.target.setToolTip("Most-hit enemy this encounter"
                               + (f" (and {len(also)} more struck in the same instant: {', '.join(also)})" if also else "")
                               + ", its remaining HP and time-to-kill from its observed HP-decline rate, and each "
                                 "contributor's DPS to it")
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

    def _relayout(self) -> None:
        """Lay the card out for what it now holds, then size the window to it. A row, a line or the panel that came
        or went asks for a layout only at the next turn of the event loop: sized before it, the window kept its old
        height until then, and its rows lay on top of each other."""
        self.box.activate()
        self.layout().activate()
        self.resize(self.width(), self._content_height())

    def _content_height(self) -> int:
        """The window's height for its width, its wrapped lines whole. Not ``adjustSize``: that keeps a window to two
        thirds of the screen's height, and a taller overlay (the player panel open) had its parts laid over each
        other; nor the layout's size hint, which counts a wrapped line once."""
        layout = self.layout()
        height = (layout.totalHeightForWidth(self.width()) if layout.hasHeightForWidth()
                  else layout.totalSizeHint().height())
        return max(height, layout.totalMinimumSize().height())

    # ------------------------------------------------------------------ the player panel
    def toggle_detail(self, key: str) -> None:
        """A click on a player's row: their panel opens, or closes when it is theirs already."""
        self.open_detail(None if self.detail_key == key else key)

    def close_detail(self) -> None:
        self.open_detail(None)

    def open_detail(self, key: str | None) -> None:
        self.detail_key, self.detail_buffs, self.detail_extra, self.detail_at = key, None, None, 0.0
        if key is not None:
            self._fetch_detail()
        self.apply_meter(self.answer)

    def _fetch_detail(self) -> None:
        """Ask the app for the open player in depth: the seconds they dealt damage and the buffs on them."""
        if self.detail_key is None or self.detail_busy or self.requests is None:
            return
        self.detail_busy = True
        self.requests.get("detail:" + self.detail_key,
                          "/api/meter/player?view=latest&key=" + quote(self.detail_key, safe=""))

    def _detail_answered(self, key: str, answer) -> None:
        self.detail_busy = False
        if key != self.detail_key:
            self._fetch_detail()                  # another player's panel opened meanwhile
            return
        player = answer.get("player") if isinstance(answer, dict) else None
        player = player if isinstance(player, dict) else None
        self.detail_buffs = list(player["buffs"]) if player and isinstance(player.get("buffs"), list) else []
        self.detail_extra, self.detail_at = player, time.monotonic()
        self.apply_meter(self.answer)

    def _show_panel(self, snap: dict, everyone: list, hidden: bool) -> None:
        if self.detail_key is None or hidden:
            self.panel_scroll.hide()
            return
        player = next((p for p in everyone if _key(p) == self.detail_key), None)
        if player is not None and time.monotonic() - self.detail_at > 3 and not self.detail_busy:
            self._fetch_detail()                  # the buffs follow the fight every few seconds
        name, mine, _unnamed = self._names(player) if player is not None else ("Player", False, False)
        columns = max(1, (self.width() - 20 - 20 + 4) // 96)   # the card's and the panel's margins; 92 px tiles
        self.panel.set_reading(panel_reading(snap, player, self.detail_buffs, self.detail_extra, name, mine), columns)
        graphed = self.ui.get("overlay_dps_graph") is True and player is not None
        self.panel.set_spark(self._player_hist.get(self.detail_key, []) if graphed else [],
                             theme.class_color(player.get("class")) if player is not None else None)
        self.panel_scroll.show()
        self.panel.layout().activate()            # its tiles and lines as they now stand (see _relayout)
        width = self.width() - 20
        content = (self.panel.heightForWidth(width) if self.panel.hasHeightForWidth()
                   else self.panel.sizeHint().height())
        self.panel_scroll.setFixedHeight(content)
        screen = self.screen()
        room = min(MAX_OVERLAY_HEIGHT, (screen.availableGeometry().height() - 16) if screen is not None
                   else MAX_OVERLAY_HEIGHT)
        self.box.activate()                       # the card's size as it now stands, its panel whole
        self.layout().activate()
        rest = self._content_height() - content
        self.panel_scroll.setFixedHeight(min(content, max(180, room - rest)))

    # ------------------------------------------------------------------ the toolbar
    @staticmethod
    def _state(button: QPushButton, state: str) -> None:
        button.setProperty("state", state)
        button.style().unpolish(button)
        button.style().polish(button)

    def _flash(self, key: str, text: str, state: str, ms: int, then) -> None:
        """A button says how its press went for a moment (``Copied``, ``New ✓``, ``Error``), then ``then`` runs."""
        button = self.tools[key]
        button.setText(text)
        self._state(button, state)
        QTimer.singleShot(ms, button, then)

    def _sync_tools(self) -> None:
        if self.combine.isEnabled():
            self.combine.setChecked(self.answer.get("combine_pets") is not False)
        targets = self.answer.get("targets")
        if isinstance(targets, list):              # the filters the app applies to the latest fight
            for check, target in ((self.boss_only, "boss"), (self.pvp_only, "player")):
                if check.isEnabled():
                    check.setChecked(target in targets)
        self._sync_capture()

    def _sync_capture(self) -> None:
        if self._capture_busy:                    # mid-request: the pending label stays
            return
        running, finalizing = self.answer.get("running") is True, self.answer.get("finalizing") is True
        button = self.tools["capture"]
        button.setText("Stopping…" if finalizing else "Stop" if running else "Start")
        button.setEnabled(not finalizing)
        button.setToolTip("Stop capturing combat (same as Stop in the app)" if running else
                          "Start capturing combat (same as Start in the app)")
        self._state(button, "stop" if running or finalizing else "start")

    def _poll_meter(self) -> None:
        if self._meter_poller is not None:
            self._meter_poller.poll()

    def toggle_lock(self) -> None:
        """Lock: the overlay stays where it is and holds its reading for a screenshot; a second press resumes."""
        self.locked = not self.locked
        button = self.tools["lock"]
        button.setText("Unlock" if self.locked else "Lock")
        self._state(button, "on" if self.locked else "")
        self.card.setToolTip("Locked for a screenshot: it stays in place and frozen until Unlock (or the screenshot "
                             "hotkey) unlocks it" if self.locked else "")
        if not self.locked:
            self._poll_meter()

    def new_fight(self) -> None:
        """New: a new fight begins with the next combat event (Split now in the app); until then the meter shows
        empty. The app keeps every fight: only this view clears."""
        if self.requests is None:
            return
        self.tools["split"].setEnabled(False)
        self.requests.post("split", "/api/meter", {"action": "split"})

    def copy(self) -> None:
        """Copy: the leaderboard of the view on the clipboard, as text."""
        if not self.copy_text:
            return
        QGuiApplication.clipboard().setText(self.copy_text)
        self._flash("copy", "Copied", "ok", 1200, self._copy_back)

    def _copy_back(self) -> None:
        self.tools["copy"].setText("Copy")
        self._state(self.tools["copy"], "")

    def toggle_options(self) -> None:
        self.options.setVisible(self.options.isHidden())   # isHidden, not isVisible: the window may be hidden
        self.tools["options"].setChecked(not self.options.isHidden())
        self._relayout()

    def toggle_capture(self) -> None:
        """Start or Stop: the capture, as the app's own buttons. Start captures with the built-in decoder and the
        Self + Party players; Stop pressed here never closes the overlay under the cursor."""
        if self.requests is None or self._capture_busy:
            return
        running = self.answer.get("running") is True
        payload = ({"action": "stop", "from_overlay": True} if running else
                   {"action": "start", "source": "a2tools", "auto_port": True, "scope": START_SCOPE})
        self._capture_busy = True
        button = self.tools["capture"]
        button.setEnabled(False)
        button.setText("Stopping…" if running else "Starting…")
        self.requests.post("capture", "/api/meter", payload)

    def _capture_done(self) -> None:
        self._capture_busy = False
        self.tools["capture"].setEnabled(True)
        self._poll_meter()
        self._sync_capture()

    def hide_overlay(self) -> None:
        """Hide: the app closes every overlay window, this one with them."""
        if self.requests is None:
            self._close_now()
            return
        self.tools["hide"].setEnabled(False)
        self.requests.post("hide", "/api/overlay", {"action": "hide", "view": "meter"})

    def _close_now(self) -> None:
        self.close()
        QApplication.quit()                       # a close of our own: the app does not start the overlay again

    def _combine_clicked(self, checked: bool) -> None:
        if self.requests is None:
            return
        self.combine.setEnabled(False)
        self.requests.post("combine", "/api/meter", {"action": "view", "combine_pets": bool(checked)})

    def _filter_clicked(self, key: str, checked: bool) -> None:
        """The damage filters are saved settings, so every overlay window follows them (the web overlay's)."""
        if self.requests is None:
            return
        check = self.boss_only if key == "overlay_boss_only" else self.pvp_only
        check.setEnabled(False)
        self.requests.post("filter:" + key, "/api/ui", {key: bool(checked)})

    def _say(self, message: str) -> None:
        self.message.setText(message)
        self.message.setVisible(bool(message))

    def _replied(self, name: str, answer) -> None:
        """A toolbar request's answer (``Requests``), on the interface's thread."""
        if name.startswith("detail:"):
            self._detail_answered(name[len("detail:"):], answer)
        elif name == "capture":
            self._capture_done()
        elif name == "split":
            segment = (self.answer.get("snapshot") or {}).get("selected_segment")
            self.cleared_fight = "" if segment is None else str(segment)
            self._graph, self._player_hist, self._shown_rates = [], {}, {}   # the graph starts clean for it
            self._flash("split", "New ✓", "ok", 1200, self._split_back)
            self.apply_meter(self.answer)
            self._poll_meter()
        elif name == "hide":
            self._close_now()
        elif name == "combine":
            self.combine.setEnabled(True)
            self._say("")
            self._poll_meter()
        elif name.startswith("filter:"):
            (self.boss_only if name.endswith("boss_only") else self.pvp_only).setEnabled(True)
            self._say("")
            self._poll_meter()

    def _failed(self, name: str, why: str) -> None:
        if name.startswith("detail:"):
            key = name[len("detail:"):]
            self.detail_busy = False
            if key == self.detail_key:
                self.detail_buffs, self.detail_at = [], time.monotonic()
                self.apply_meter(self.answer)
            else:
                self._fetch_detail()
        elif name == "capture":
            button = self.tools["capture"]
            button.setToolTip(why[:256])
            self._flash("capture", "Error", "err", 1400, self._capture_done)
        elif name == "split":
            self._flash("split", "Error", "err", 1200, self._split_back)
        elif name == "hide":
            self._close_now()                     # the app is gone or refused: the overlay closes all the same
        elif name == "combine":
            self.combine.setEnabled(True)
            self._say("Could not change pet grouping")
        elif name.startswith("filter:"):
            check = self.boss_only if name.endswith("boss_only") else self.pvp_only
            check.setEnabled(True)
            check.setChecked(not check.isChecked())
            self._say("Could not change the damage filter")

    def _split_back(self) -> None:
        button = self.tools["split"]
        button.setText("New")
        button.setEnabled(True)
        self._state(button, "")

    def _commands(self, answer) -> None:
        """The app's command counters (``/api/overlay/commands``): the screenshot hotkey toggles the lock, and Open
        overlay while it is open brings it forward with a fresh reading. The first reading is the baseline."""
        if not isinstance(answer, dict):
            return
        for name in ("lock_seq", "reload_seq"):
            try:
                seq = int(answer.get(name) or 0)
            except (TypeError, ValueError):
                continue
            seen = self._seqs.get(name)
            self._seqs[name] = seq if seen is None else max(seen, seq)
            if seen is None or seq <= seen:
                continue
            if name == "lock_seq":
                self.toggle_lock()
            else:
                self.refresh()

    def refresh(self) -> None:
        self.show()
        self.raise_()
        if self._settings_poller is not None:
            self._settings_poller.poll()
        self._poll_meter()

    # ------------------------------------------------------------------ moving, and a click on a player
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._drag = None if self.locked else self._press - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        offset = event.globalPosition().toPoint() - self._press
        moved = math.hypot(offset.x(), offset.y()) > 4   # a press that moved the window is a move, not a click
        dragging = self._drag is not None
        self._press = self._drag = None
        if moved:
            if dragging:
                self.save_position()
            return
        widget = self.childAt(event.position().toPoint())
        while widget is not None and not isinstance(widget, PlayerRow):
            widget = widget.parentWidget()
        if isinstance(widget, PlayerRow) and widget.key:
            self.toggle_detail(widget.key)

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


def overlay_store() -> QSettings:
    """Where the overlay keeps its opacity and metric: the user's own settings file, as the web overlay keeps them
    in its page's storage."""
    return QSettings(QSettings.IniFormat, QSettings.UserScope, "Aion 2 Calc", "native-overlay")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aion2calc.gui.overlay", description="Aion 2 Calc native overlay")
    parser.add_argument("--url", default=None, help="the app's overlay address (default: the running app's)")
    args = parser.parse_args(argv)
    from ..overlay import _ParentProcess, _default_url
    url = args.url or _default_url()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    window = MeterOverlay(AppApi(_app_base(url)), _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")),
                          overlay_store())
    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
