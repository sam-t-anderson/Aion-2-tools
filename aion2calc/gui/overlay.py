"""The native meter overlay (0.2.413; the native interface is the default since 0.2.426): the meter's reading in a
frameless, always-on-top, see-through Qt window over the game, in place of the overlay page in a pywebview window.

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

Since the ninth part (0.2.422) the window is laid out as the web overlay's compact layout: the counters, the target
card and the rows on top, then the fight's clock (its status in the tooltip), your contribution, the identity line
and the events strip as chips, and the ping, the frame rate and the toolbar of icons on a line of their own
(chrome.py). The header line with its status and its metric buttons is gone, as it is on the web overlay.

The tenth part (0.2.423) is arena mode (arena.py): in the Arena of Solitude, the Arena of Cooperation and a
battlefield, the opponent's (or your target's) card in the target card's place and the three metrics in the rows'
place, in the layout the options pick, with the match in the clock. The eleventh (0.2.424) is the raid plan view
(plan.py), behind the toolbar's tabs; the twelfth (0.2.425) the counters across the top with their icons.
"""
from __future__ import annotations

import argparse
import copy
import html
import math
import os
import re
import sys
import time
from urllib.parse import quote

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, QSizeF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontMetricsF, QGuiApplication, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from . import events as schedule
from . import theme
from . import arena as A
from .api import AppApi, Poller, Requests
from .arena import Line, Run, Section, TableHead, Tug, sized
from .chrome import (GREEN, MONOSPACE, RED, TEAL, Chip, FlowLayout, FpsChip, IconButton, MetricChip, Part, clock_mark,
                     forget_icons, icon_mark, picture_mark)
from .chrome import font as sized_font
from .host import WindowHost
from .look import (ANIMATION_MS, CHIP_SHADOW, ROW_SHADOW, TextEffect, TextLook, background_rect, contrast_colour, cycled,
                   draw_text, forget_pictures, hex_colour, reduced_motion, sheen_brush)
from .pictures import ODYLE_ICON, Pictures
from .plan import PlanMap, plan_view

#: The metrics, in the order the metric chip steps through them, with the chip's words (overlay.html ``#ovmetrics``).
METRICS = (("dps", "DPS"), ("hps", "HPS"), ("dtps", "D.Taken"))
DEFAULT_OPACITY = 0.72                    # the overlay page's own starting opacity (overlay.js ``op``)
MAX_OVERLAY_HEIGHT = 800                  # the tallest the overlay window grows (overlay.js ``MAX_OVERLAY_H``)
BACKGROUND_LIMIT = 3200                   # the background image's longest side as kept: an 800-px card at 200% on 2×
GRAPH_LIMIT = 300                         # the readings the live graph keeps (overlay.js ``recordGraph``)
#: The Players scope Start captures with: the web overlay's own when the app's Live Meter page saved none.
START_SCOPE = "party"
#: The toolbar (overlay.html), in the order the web overlay's compact layout gives it: key, icon, words, tooltip.
TOOLS = (("lock", "camera", "Lock", "Freeze the overlay in place for a screenshot"),
         ("split", "new", "New", "Start a new fight — the next combat event begins a fresh encounter (same as Split "
                                 "now in the app)"),
         ("copy", "copy", "Copy", "Copy the current meter as text, to paste in chat or Discord"),
         ("options", "options", "Options", "Overlay options: opacity, pet grouping and damage filters"),
         ("capture", "play", "Start", "Start or stop capturing combat (same as Start/Stop in the app)"),
         ("hide", "close", "Hide", "Hide overlay"))
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


def fmt_ttk(seconds) -> str:
    """overlay.js ``fmtTtk``, as the target card writes its time to kill and enrage timer: 45s, 1m06s, 1h2m."""
    total = theme.js_round(_num(seconds))
    if total >= 3600:
        return f"{total // 3600}h{total % 3600 // 60}m"
    if total >= 60:
        return f"{total // 60}m{total % 60:02d}s"
    return f"{total}s"


def hp_tip(target: dict) -> str:
    """The target's HP readouts' tooltip (overlay.js ``hpTip``): its HP in damage units where the community has
    measured it, else what has been dealt to it and the game's own HP, on its larger scale."""
    kfmt = theme.kfmt
    if target.get("effective_max_hp") is not None:
        samples = target.get("effective_hp_samples") or 0
        return (f"HP ≈ {kfmt(target.get('effective_current_hp'))} / {kfmt(target.get('effective_max_hp'))} in damage "
                f"units — calibrated from {samples} community kill{'' if samples == 1 else 's'} on this game build. "
                f"Effective HP dealt so far ≈ {kfmt(target.get('damage'))}.")
    tip = f"Effective HP so far ≈ {kfmt(target.get('damage'))} (total recorded damage dealt to it)."
    if target.get("current_hp") is not None:
        tip += (f" Game internal HP {kfmt(target.get('current_hp'))}"
                f"{' / ' + kfmt(target.get('max_hp')) if target.get('max_hp') else ''} is on a larger, different "
                f"scale than damage, so it is shown here as a percentage.")
    return tip


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


#: What each counter is, for its tooltip (overlay.js, the lines' titles).
COUNTER_TIPS = {
    "odyle": "Your Odyle Energy, as the game sent it: the regular energy regenerates 15 every 3 hours, and a claimed "
             "reward cube spends it first, then the bonus",
    "shugo_keys": "Your Shugo Festival Reward Keys, as the game sent them: the regular keys, then the bonus ones (the "
                  "same count the festival window shows)",
    "nightmare_tickets": "Your Nightmare tickets, as the game sent them: the regular tickets, then the bonus ones, "
                         "spent one at a time, the regular first",
    "weekly_runs": "This dungeon's weekly entries left, as the game counts them: learned from the counter that went "
                   "down when a run here was rewarded, and kept up to date by the game"}
COUNTER_ICONS = {"shugo_keys": "key", "nightmare_tickets": "ticket", "weekly_runs": "runs"}


def counter_items(snapshot: dict) -> list[tuple[str, str, int, int]]:
    """The counters the meter's reading carries, in the overlay's order, each ``(key, its full words, the regular
    count, the bonus)``."""
    counts = {}
    for key in ("odyle", "shugo_keys", "nightmare_tickets", "weekly_runs"):
        value = snapshot.get(key)
        if isinstance(value, dict):
            counts[key] = (int(_num(value.get("regular"))), int(_num(value.get("bonus"))))
    return [(key, full, *counts[key]) for key, full, _short in counter_lines(snapshot) if key in counts]


def ping_texts(ping) -> tuple[str, str]:
    """The ping chip (overlay.js, the compact layout): the current round trip in whole milliseconds ("—" with no
    samples), and the whole of it for the tooltip."""
    if not isinstance(ping, dict):
        return "—", "Ping: no recorded samples"
    ms = {k: theme.fixed(_num(ping.get(k)), 0) for k in ("current", "avg", "min", "max")}
    return ms["current"], f"Ping {ms['current']} ms · Avg {ms['avg']} ms · Min {ms['min']} / Max {ms['max']} ms"


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
        whole = QRectF(self.contentsRect())       # the live graph's margins lie round it (``margin: 2px 0 4px``)
        painter.translate(whole.topLeft())
        rect = QRectF(0, 0, whole.width(), whole.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 8 if rect.height() > 20 else 3, 8 if rect.height() > 20 else 3)
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
    Background setting). The background image (``background``) lies under the readings in the card or its top
    portion, as the web overlay's ``#ovbg``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.opacity = DEFAULT_OPACITY
        self.mode = "card"
        self.rows_part: QWidget | None = None     # the rows' part: the top portion ends where it begins (``--ov-top-h``)
        self.locked = False                       # Lock: a dashed green edge (``#ov.ov-locked .ovcard``)
        self.hover = "off"                        # hover to interact: "arming" while it counts, "open" once open
        self.background: QPixmap | None = None    # the background image, with its opacity, zoom and darkening
        self.bg_opacity, self.bg_zoom, self.bg_darken = 1.0, 1.0, 0.2
        self._layer: QPixmap | None = None
        self._layer_key = None
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        if self.mode == "none" and self.hover == "off" and not self.locked:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        top = self.mode == "top" and self.rows_part is not None
        end = self.rows_part.geometry().top() if top else 0   # where the top portion ends, as laid out now
        if top and self.hover == "off":           # the panel behind the top portion, down to the rows' part
            rect.setHeight(max(0.0, min(rect.height(), end - 1.0)))
        radius = 10 if top and self.hover == "off" else 12
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        if self.mode != "none":
            r, g, b = theme.OVERLAY_CARD
            painter.fillPath(path, QColor(r, g, b, int(255 * self.opacity)))
            if self.background is not None and not self.background.isNull():
                box = QRectF(self.rect())         # the top portion's alone in the top-only mode (``--ov-top-h``)
                if top:
                    box.setHeight(max(0.0, min(box.height(), float(end))))
                if box.height() >= 1:
                    painter.save()
                    painter.setOpacity(self.bg_opacity)
                    painter.drawPixmap(box.topLeft(), self._background_layer(box))
                    painter.restore()
        if self.hover != "off":                   # the edge says the overlay is opening to clicks, or open
            painter.setPen(QPen(QColor(theme.COLORS["accent"] if self.hover == "arming" else theme.COLORS["gold"]), 2))
            painter.drawPath(path)
        elif self.mode != "none":
            painter.setPen(QColor(255, 255, 255, 20))   # ``--nm-line``
            painter.drawPath(path)
        if self.locked:                           # ``outline: 1px dashed rgba(143, 208, 160, .7); outline-offset: -1px``
            pen = QPen(QColor(143, 208, 160, 179), 1)
            pen.setDashPattern([3, 3])
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 11.5, 11.5)

    def _background_layer(self, box: QRectF) -> QPixmap:
        """The image and its darkening as one layer, as ``#ovbg``'s two backgrounds are one element: its opacity
        then dims the whole of it, where drawn apart at that opacity the darkening would darken the card under the
        image too. Made again only when its size, its image or its settings change."""
        ratio = self.devicePixelRatioF()
        key = (box.width(), box.height(), ratio, self.background.cacheKey(), self.bg_zoom, self.bg_darken)
        if key != self._layer_key:
            layer = QPixmap(max(1, math.ceil(box.width() * ratio)), max(1, math.ceil(box.height() * ratio)))
            layer.setDevicePixelRatio(ratio)
            layer.fill(Qt.transparent)
            inner = QPainter(layer)
            inner.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
            whole = QRectF(0, 0, box.width(), box.height())
            clip = QPainterPath()
            clip.addRoundedRect(whole.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
            inner.setClipPath(clip)
            image = self.background
            inner.drawPixmap(background_rect(whole, image.width(), image.height(), self.bg_zoom), image,
                             QRectF(image.rect()))
            inner.fillRect(whole, QColor(0, 0, 0, round(255 * self.bg_darken)))
            inner.end()
            self._layer, self._layer_key = layer, key
        return self._layer


def _mix(colour, other, share: float) -> QColor:
    """CSS ``color-mix(in srgb, colour share, other)``."""
    one, two = QColor(colour), QColor(other)
    return QColor.fromRgbF(one.redF() * share + two.redF() * (1 - share),
                           one.greenF() * share + two.greenF() * (1 - share),
                           one.blueF() * share + two.blueF() * (1 - share))


class HpBar(QWidget):
    """A filled bar, its colour over a faint track: the player panel's skill and buff bars."""

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


class CardBar(HpBar):
    """A bar inside the target card (overlay.css ``#ov.ov-nm .ovtbar``): a faint track with a fine edge, filled from
    the left. The HP's (``glow``) runs from its colour's darker end to the colour and glows past its end."""

    def __init__(self, parent=None, height: int = 6, glow: bool = False):
        super().__init__(parent)
        self.glow = glow
        self.setFixedHeight(height)

    def shown(self) -> float:
        return self.fraction

    def paint_fill(self, painter: QPainter, fill: QRectF) -> None:
        if not self.glow:
            painter.fillRect(fill, self.color)
            return
        gradient = QLinearGradient(fill.topLeft(), fill.topRight())
        gradient.setColorAt(0, _mix(self.color, "#0c0e11", 0.38))
        gradient.setColorAt(1, self.color)
        painter.fillRect(fill, gradient)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        radius = rect.height() / 2
        track = QPainterPath()
        track.addRoundedRect(rect, radius, radius)
        painter.fillPath(track, QColor(255, 255, 255, 15))
        shown = self.shown()
        if shown > 0:
            painter.save()
            painter.setClipPath(track)            # ``overflow: hidden``: the fill's glow stays in the track
            fill = QRectF(rect.x(), rect.y(), rect.width() * shown, rect.height())
            if self.glow:                         # ``box-shadow: 0 0 6px`` the colour at 40%, past the fill's end
                halo = QColor(self.color)
                halo.setAlphaF(0.4)
                fade = QLinearGradient(fill.right(), 0, fill.right() + 6, 0)
                fade.setColorAt(0, halo)
                fade.setColorAt(1, QColor(halo.red(), halo.green(), halo.blue(), 0))
                painter.fillRect(QRectF(fill.right(), rect.y(), 6, rect.height()), fade)
            shape = QPainterPath()
            r = min(radius, fill.width() / 2)
            shape.addRoundedRect(fill, r, r)
            painter.setClipPath(shape, Qt.IntersectClip)
            self.paint_fill(painter, fill)
            painter.restore()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 13), 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), max(0.0, radius - 0.5), max(0.0, radius - 0.5))


class GaugeBar(CardBar):
    """The target's break gauge (``.ovtbar-gauge``): amber, 4 px; once broken (5% or less left, as the web overlay
    has it) the whole bar in stripes."""

    def __init__(self, parent=None):
        super().__init__(parent, 4)
        self.color = QColor("#e3b35a")

    @property
    def broken(self) -> bool:
        return self.fraction <= 0.05

    def set_fraction(self, fraction: float) -> None:
        was = self.broken
        super().set_fraction(fraction)
        if self.broken != was:
            self.update()

    def shown(self) -> float:
        return 1.0 if self.broken else self.fraction

    def paint_fill(self, painter: QPainter, fill: QRectF) -> None:
        if not self.broken:
            painter.fillRect(fill, self.color)
            return
        x = fill.left()                           # ``repeating-linear-gradient(90deg, #f0c36a 0 6px, #b5832e 6px 12px)``
        while x < fill.right():
            painter.fillRect(QRectF(x, fill.top(), 6, fill.height()), QColor("#f0c36a"))
            painter.fillRect(QRectF(x + 6, fill.top(), 6, fill.height()), QColor("#b5832e"))
            x += 12


class TtkBar(CardBar):
    """The target's time-to-kill bar (overlay.css ``.ovtbar-ttk``): how much of the whole kill has gone by, by time,
    3 px high, in the time-to-kill colour (``overlay_ttk_color``)."""

    def __init__(self, parent=None):
        super().__init__(parent, 3)
        self.color = QColor("#8fb3d0")
        self.setToolTip("Estimated kill progress by time — how much of the whole kill has elapsed (engaged time so "
                        "far vs the time-to-kill still remaining). Packet-sourced; it can run ahead of or behind the "
                        "HP bar when the fight starts slow or finishes fast.")


class MiniBar(HpBar):
    """A skill's or a buff's bar in the player panel: gold, 54 px by 5 (overlay.css ``.ovdskbar``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(theme.COLORS["gold"])
        self.setFixedSize(54, 5)


class Portrait(QWidget):
    """The target's portrait (overlay.css ``#ov.ov-nm .ovtarget .ovtport``): the boss's bundled art filling its 34 px
    rounded square, or the target mark where the app has none."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.picture: QPixmap | None = None
        self.setFixedSize(34, 34)

    def set_picture(self, picture: QPixmap | None) -> None:
        if (picture.cacheKey() if picture is not None else None) != \
                (self.picture.cacheKey() if self.picture is not None else None):
            self.picture = picture
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        square = QPainterPath()
        square.addRoundedRect(rect, 8, 8)
        painter.fillPath(square, QColor(255, 255, 255, 13))
        picture = self.picture
        if picture is not None and not picture.isNull():   # ``object-fit: cover``
            painter.setClipPath(square)
            scale = max(rect.width() / picture.width(), rect.height() / picture.height())
            width, height = picture.width() * scale, picture.height() * scale
            painter.drawPixmap(QRectF(rect.center().x() - width / 2, rect.center().y() - height / 2, width, height),
                               picture, QRectF(picture.rect()))
            return
        painter.translate(rect.center().x() - 11, rect.center().y() - 11)   # ``--nm-ic-target``, 22 px
        painter.scale(22 / 24, 22 / 24)
        painter.setPen(QPen(QColor("#8b95a3"), 2, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(12, 12), 7.5, 7.5)
        painter.drawEllipse(QPointF(12, 12), 2.5, 2.5)
        for x1, y1, x2, y2 in ((12, 2, 12, 6), (12, 18, 12, 22), (2, 12, 6, 12), (18, 12, 22, 12)):
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


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
        self.value_colour = "#ffffff"             # the tiles' values, in the rate's colour (``.ovdtile b``)
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
            tile.setText(f"<div style='font-size:{round(px * 1.05)}px; font-weight:700; color:{self.value_colour}'>"
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


class CooldownStrip(QWidget):
    """Your skills on cooldown (the meter's ``cooldowns``, with the chain windows open), each counting down between
    readings as the web overlay's strip does, and lit for 3 s once ready."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 2, 0, 4)   # ``#ovcooldowns { margin: 2px 0 4px }``
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


COSMETICS = ("gold", "rainbow", "ember", "frost", "aether", "starlight")   # overlay.js ``COSMETICS``, all but none
RANK_COLOURS = ("#f2c84b", "#cfd4dc", "#d08a52")   # overlay.css ``.ovrank-1`` to ``-3``: gold, silver, bronze
#: The combat-power chip's crossed swords (``--nm-ic-cp``), its strokes in a 24-unit square.
SWORDS = ((4, 4, 15, 15), (13, 17, 17, 13), (15, 15, 19, 19), (20, 4, 9, 15), (7, 13, 11, 17), (9, 15, 5, 19))
RAINBOW = ("#ff5e5e", "#ffb75e", "#f6ff5e", "#5eff8a", "#5ed8ff", "#a35eff", "#ff5ee1", "#ff5e5e")
GOLD_RING = ("#f6e27a", "#b8860b", "#fff6c2", "#d4af37", "#f6e27a")
STAR_LOOK = TextLook({"overlay_glow": True, "overlay_glow_color": "#ffe9a6"})   # ``.ov-cos-starlight``'s glow


def rate_text(value) -> str:
    """overlay.js ``rateText`` in the compact layout: a rate in whole digits below ten million, else ``kfmt``."""
    value = _num(value)
    return theme.digits(value) if abs(value) < 1e7 else theme.kfmt(value)


def _eased(phase: float) -> float:
    """CSS ``ease-in-out`` near enough: a smooth step from 0 to 1."""
    phase = max(0.0, min(1.0, phase))
    return phase * phase * (3 - 2 * phase)


def _twinkle(seconds: float | None, period: float, delay: float = 0.0) -> float:
    """``ovtwinkle``: an opacity from 0.45 up to 1 and back each ``period``; 1 held still."""
    if seconds is None:
        return 1.0
    phase = ((seconds - delay) % period) / period
    return 0.45 + 0.55 * _eased(1 - abs(1 - 2 * phase))


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
        # The rows' effects (``overlay_me_cosmetic`` for your row, ``overlay_top_cosmetic`` for the top one) and
        # long names scrolling under the pointer (``overlay_long_names_scroll``).
        self.me_cosmetic = ui.get("overlay_me_cosmetic") if ui.get("overlay_me_cosmetic") in COSMETICS else None
        self.top_cosmetic = ui.get("overlay_top_cosmetic") if ui.get("overlay_top_cosmetic") in COSMETICS else None
        self.scroll_names = ui.get("overlay_long_names_scroll") is True

    def display_name(self, player: dict, mine: bool, unnamed_self: bool) -> str:
        """The web overlay's ``displayName``: the name, "Sorcerer 2" or "P2"; your unnamed row reads "You"."""
        number = player.get("party_number") or "?"
        if self.name_mode == "number":
            return f"P{number}"
        if self.name_mode == "class_number":
            return f"{str(player.get('class') or 'Player').title()} {number}"
        return "You" if unnamed_self else str(player.get("name") or "?")

    def cosmetic(self, mine: bool, index: int) -> str | None:
        """A row's effect: yours on your row, the top one's on the top row (yours wins when both are yours)."""
        return self.me_cosmetic if mine and self.me_cosmetic else self.top_cosmetic if index == 0 else None


class PlayerRow(QWidget):
    """One player as the compact layout draws them (overlay.css ``#ov.ov-nm .ovrow``): a pill with the bar in the
    class's colour filling it to the player's share of the top rate; the rank, the class's emblem (yours with a green
    dot), the name and what goes beside it; the rate in whole digits and the share of the total to a tenth. Your row
    or the top row can carry an effect (``cosmetic``), and a name cut short can scroll under the pointer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.name, self.rate, self.share, self.fill, self.mine = "", "", "", 0.0, False
        self.index, self.dead, self.cp, self.look = 0, False, "", RowLook({})
        self.key, self.open = "", False           # the player's row key, and whether their panel is open
        self.actor, self.crank = "", ""           # "#id" beside a name two players share; the community standing
        self.target, self.amount = 0.0, 0.0       # the reading's rate and amount, for the live tick
        self.text_look = TextLook({})             # the overlay's fonts, colours and effects
        self.seconds: float | None = None         # how far the colour cycle, the sheen and the effects are; None still
        self.color = QColor(theme.FALLBACK_CLASS_COLOR)
        self.emblem: QPixmap | None = None        # the class's emblem, where the app has one
        self.cosmetic: str | None = None          # your row's or the top row's effect
        self.whole = True                         # on the whole card (the background mode), else a pill of its own
        self.moving = True                        # effects may move: not in performance mode or with less motion asked
        self._shade: tuple | None = None          # the emblem's shadow, made once for each emblem
        self._scroll_from: float | None = None    # when a long name began to scroll under the pointer
        self._cut = False                         # the name is cut short
        self._scroll = QTimer(self)
        self._scroll.setInterval(40)
        self._scroll.timeout.connect(self.update)
        self.setFixedHeight(28)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)     # a click opens the player's panel

    def set_player(self, name: str, cls: str, rate: str, share: str, fill: float, mine: bool,
                   index: int = 0, dead: bool = False, cp: str = "", look: RowLook | None = None,
                   key: str = "", open_: bool = False, actor: str = "", crank: str = "",
                   emblem: QPixmap | None = None, whole: bool = True) -> None:
        look = look or self.look
        self.key = key
        cosmetic = look.cosmetic(mine, index)
        state = (name, cls, rate, share, round(fill, 4), mine, index, dead, cp, open_, actor, crank,
                 tuple(sorted(vars(look).items())), emblem.cacheKey() if emblem is not None else None, whole)
        if state == getattr(self, "_state", None):
            return
        self._state = state
        self.name, self.rate, self.share, self.fill, self.mine = name, rate, share, max(0.0, min(1.0, fill)), mine
        self.index, self.dead, self.cp, self.look, self.open = index, dead, cp, look, open_
        self.actor, self.crank, self.emblem, self.whole, self.cosmetic = actor, crank, emblem, whole, cosmetic
        self.color = QColor(theme.class_color(cls))
        self.update()

    def set_text_look(self, look: TextLook) -> None:
        self.text_look, self._state = look, None
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
        """The row's left-hand text in its parts, each with what it is: the rank, the name, the actor id beside a name
        two players share, DEAD, the community standing, the combat power, and ME on your highlighted row."""
        parts = [(f"{self.index + 1}.", "rank")] if self.look.rank_numbers else []
        parts.append((self.name, "name"))
        parts += [(text, kind) for text, kind in (
            (self.actor, "actor"), ("DEAD" if self.dead else "", "dead"), (self.crank, "crank"), (self.cp, "cp"),
            ("ME" if self.mine and self.look.highlight_me else "", "me")) if text]
        return parts

    def label(self) -> str:
        """The row's left-hand text: the rank, the name, and what goes beside it."""
        parts = self.segments()
        rank = parts[0][0] + " " if parts[0][1] == "rank" else ""
        return rank + "  ".join(text for text, kind in parts if kind != "rank")

    def right(self) -> str:
        """The row's right-hand text: the rate, and the share unless the rows are compact."""
        return self.rate if self.look.compact else f"{self.rate}  {self.share}"

    # ------------------------------------------------------------------ the pointer: long names scroll
    def event(self, event):
        if event.type() == QEvent.HoverEnter and self.look.scroll_names and self.moving:
            self._scroll_from = time.monotonic()
            self._scroll.start()
        elif event.type() == QEvent.HoverLeave:
            self._scroll_from = None
            self._scroll.stop()
            self.update()
        return super().event(event)

    def _scrolled(self, width: float) -> float:
        """``ovnamescroll``: a name ``width`` wide held 15% of 4 s, then moved left until its end lies 60 px in, and
        back the same way."""
        elapsed = time.monotonic() - self._scroll_from
        turn, phase = divmod(elapsed / 4.0, 1.0)
        phase = 1 - phase if int(turn) % 2 else phase
        return 0.0 if phase <= 0.15 else (60 - width) * (phase - 0.15) / 0.85

    # ------------------------------------------------------------------ drawing
    def _fonts(self):
        tl = self.text_look
        px = self.font().pixelSize() if self.font().pixelSize() > 0 else 12
        name = tl.font("name", px * 1.12, 700)    # ``.ovname``: 1.12em, 700
        rate = tl.font("rate", px * 1.12, 800)    # ``.ovbar > span``: 1.12em, 800
        share = QFont(rate)                       # ``.ovpct``: .84em of the rate's, 800
        share.setPixelSize(max(6, round(rate.pixelSize() * 0.84)))
        share.setWeight(QFont.ExtraBold)
        chip = QFont(name)                        # ``.ovcp``: .78em of the name's, 700
        chip.setPixelSize(max(6, round(name.pixelSize() * 0.78)))
        chip.setWeight(QFont.Bold)
        return px, name, rate, share, chip

    def _small(self, name: QFont, weight, spacing: float = 0.0) -> QFont:
        """``.ovactor``, ``.ovdead``, ``.ovcrank`` and the ME badge: 9 px."""
        font = QFont(name)
        font.setPixelSize(9)
        font.setWeight(weight)
        if spacing:
            font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        return font

    def _emblem_shade(self) -> QPixmap:
        """The emblem's ``drop-shadow``: its shape in black at 60%."""
        key = self.emblem.cacheKey()
        if self._shade is None or self._shade[0] != key:
            shade = QPixmap(self.emblem.size())
            shade.fill(Qt.transparent)
            painter = QPainter(shade)
            painter.drawPixmap(0, 0, self.emblem)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(shade.rect(), QColor(0, 0, 0, 153))
            painter.end()
            self._shade = (key, shade)
        return self._shade[1]

    def paintEvent(self, event):
        look, tl = self.look, self.text_look
        seconds = self.seconds if self.moving else None
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        if self.dead:
            painter.setOpacity(0.55)              # ``.ovrow-dead``
        rect = QRectF(self.rect())
        height = rect.height()
        radius = height / 2 if look.rounded else 7.0
        pill = QPainterPath()
        pill.addRoundedRect(rect, radius, radius)
        if look.stripes and self.index % 2:      # zebra rows (``:nth-child(even)``)
            ground = QColor(28, 32, 38, 179)
        elif self.whole:                          # on the whole card a faint light (``--nm-row``)
            ground = QColor(255, 255, 255, 11)
        else:                                     # over the game, a dark pill of its own
            ground = QColor(10, 12, 15, 140)
        painter.fillPath(pill, ground)
        if self.fill > 0:                         # the bar (``.ovbar i``), darker toward the card
            bar = QRectF(0, 0, rect.width() * self.fill, height)
            corner = min(radius, bar.width() / 2)
            shape = QPainterPath()
            shape.addRoundedRect(bar, corner, corner)
            gradient = QLinearGradient(bar.topLeft(), bar.topRight())
            if look.gradient:
                gradient.setColorAt(0, self.color)
                gradient.setColorAt(1, _mix(self.color, "#000000", 0.4))
            else:
                gradient.setColorAt(0, _mix(self.color, "#0c0e11", 0.7))
                gradient.setColorAt(1, _mix(self.color, "#0c0e11", 0.86))
            painter.fillPath(shape, gradient)
        edge = QColor(255, 255, 255, 20)          # ``--nm-line``, or your row edged in the glow colour (``.ovrow-me``)
        if self.mine and look.highlight_me:
            edge = QColor(tl.glow_colour)
            edge.setAlphaF(0.6)
        self._edge(painter, rect, radius, edge, 1.0)
        self._paint_text(painter, rect, seconds)
        if self.cosmetic:
            self._paint_cosmetic(painter, rect, pill, radius, seconds)

    @staticmethod
    def _edge(painter: QPainter, rect: QRectF, radius: float, colour, width: float, inset: float = 0.0) -> None:
        """A ring ``width`` thick ``inset`` within the pill (``box-shadow: inset 0 0 0 1px``)."""
        painter.save()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(colour, width))
        half = inset + width / 2
        painter.drawRoundedRect(rect.adjusted(half, half, -half, -half), max(0.0, radius - half),
                                max(0.0, radius - half))
        painter.restore()

    def _paint_right(self, painter: QPainter, rect: QRectF) -> float:
        """The row's right-hand side: the share to a tenth (from 20em of room) and the rate, 9 px in (``.ovbar >
        span``); answers where the names' part ends, where the rate's padding begins."""
        look, tl = self.look, self.text_look
        px, _name_font, rate_font, share_font, _chip_font = self._fonts()
        height = rect.height()
        x = rect.width() - 9
        if not look.compact and rect.width() > 20 * px:
            room = max(QFontMetricsF(share_font).horizontalAdvance(self.share), 3.5 * share_font.pixelSize())
            draw_text(painter, QRectF(x - room, 0, room, height), self.share, share_font,
                      QColor(tl.colour("total", "#f1d27c")), Qt.AlignRight, tl, shadow=ROW_SHADOW)
            x -= room + 9
        x -= draw_text(painter, QRectF(7, 0, max(0.0, x - 7), height), self.rate, rate_font,
                       QColor(tl.colour("rate", "#ffffff")), Qt.AlignRight, tl, shadow=ROW_SHADOW)
        return x - 6

    def _paint_text(self, painter: QPainter, rect: QRectF, seconds: float | None) -> None:
        look, tl = self.look, self.text_look
        px, name_font, rate_font, share_font, chip_font = self._fonts()
        height = rect.height()
        # ``hue-rotate`` over the whole of the names' part (``.ovname``); with the sheen on, its animation takes the
        # cycle's place on the names, as the web overlay's stylesheet has it.
        cycle = tl.cycle and not tl.retro and seconds is not None
        end = self._paint_right(painter, rect)
        painter.save()
        painter.setClipRect(QRectF(0, 0, max(0.0, end), height))   # ``.ovname { overflow: hidden }``
        names = QColor(tl.colour("name", "#e9f7ff"))
        name_colour = _mix(self.color, "#ffffff", 0.55) if look.class_names else names
        shift = (lambda colour: cycled(colour, seconds)) if cycle else None   # the effects turn with them
        brush = None
        if tl.retro and seconds is not None:      # one band across the names' room (``.ovname``)
            brush = sheen_brush(QRectF(0, 0, max(1.0, end), height), cycled(names, seconds) if cycle else names,
                                seconds)

        def colour(value) -> QColor:
            value = names if tl.retro else QColor(value)   # the sheen fills every part in the names' colour
            return cycled(value, seconds) if cycle else value

        def text(left: float, part: str, font: QFont, shade, room: float | None = None, opacity: float = 1.0,
                 fill=None) -> float:
            if room is not None:
                part = QFontMetricsF(font).elidedText(part, Qt.ElideRight, max(0.0, room))
            if opacity != 1.0:
                painter.setOpacity(painter.opacity() * opacity)
            width = draw_text(painter, QRectF(left, 0, max(1.0, end - left), height), part, font, colour(shade),
                              Qt.AlignLeft, tl, fill if fill is not None else brush, shift, shadow=ROW_SHADOW)
            if opacity != 1.0:
                painter.setOpacity(painter.opacity() / opacity)
            return width

        left = 7.0                                # ``.ovname``: 7 px in
        if self.cosmetic == "gold":               # ``.ov-cos-gold .ovname::before``: a twinkling diamond
            diamond = QFont(name_font)
            diamond.setPixelSize(max(6, round(name_font.pixelSize() * 0.8)))
            left += text(left, "◆", diamond, "#f6e27a", opacity=_twinkle(seconds, 1.6)) + 5
        parts = self.segments()
        if parts[0][1] == "rank":                 # ``.ovrank``: the top three in gold, silver and bronze
            rank = QFont(name_font)
            top = self.index < 3
            if top:
                rank.setWeight(QFont.Bold)
            left += text(left, parts[0][0], rank, RANK_COLOURS[self.index] if top else tl.colour("total", "#9aa3b5"),
                         opacity=1.0 if top else 0.7) + 4
        if self.emblem is not None and not self.emblem.isNull():   # ``.ovcicon``: 24 px, 8 px before the name
            size = min(24.0, height - 2)
            box = QRectF(left, (height - size) / 2, size, size)
            painter.drawPixmap(box.translated(0, 1), self._emblem_shade(), QRectF(self.emblem.rect()))
            painter.drawPixmap(box, self.emblem, QRectF(self.emblem.rect()))
            if self.mine:                         # ``.ovrow-self .ovcicon::after``: a green dot, ringed
                dot = QRectF(box.right() + 3 - 8, box.bottom() + 2 - 8, 8, 8)
                painter.save()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#0c0e11"))
                painter.drawEllipse(dot.adjusted(-1.5, -1.5, 1.5, 1.5))
                painter.setBrush(QColor("#3ddc84"))
                painter.drawEllipse(dot)
                painter.restore()
            left += size + 8
        if look.class_swatch:                     # ``.ovclass``: 8 px, 5 px before the name
            swatch = QRectF(left, height / 2 - 4, 8, 8)
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(cycled(self.color, seconds) if cycle else self.color)
            painter.drawRoundedRect(swatch, 2, 2)
            painter.restore()
            left += 8 + 5
        # What follows the name keeps its width; the name gives way first (``text-overflow: ellipsis``).
        after = []
        for part, kind in parts:
            if kind == "actor":
                after.append((part, self._small(name_font, QFont.Normal), "#aab3c5", 4, 1.0))
            elif kind == "dead":
                after.append((part, self._small(name_font, QFont.Bold, 0.5), "#e5706e", 4, 1.0))
            elif kind == "crank":
                after.append((part, self._small(name_font, QFont.Bold, 0.3), "#e8cf8e", 5, 0.9))
            elif kind == "cp" and rect.width() > 26.5 * px:   # ``@container (max-width: 26.5em)``: the chip steps aside
                after.append((part, chip_font, "#63d3e6", 9, 1.0))
            elif kind == "me":
                after.append((part, self._small(name_font, QFont.ExtraBold, 0.6), "#e9a0dd", 6, 1.0))
        reserved = sum(margin + QFontMetricsF(font).horizontalAdvance(part)
                       + (1.3 * font.pixelSize() + 3 if font is chip_font else 0)
                       for part, font, _shade, margin, _opacity in after)
        room = max(0.0, end - left - reserved)
        name_font = QFont(name_font)
        name_font.setUnderline(self.open)        # the row whose panel is open (``.ovrow-detail``)
        full = QFontMetricsF(name_font).horizontalAdvance(self.name)
        self._cut = full > room + 0.5
        rainbow = None
        if self.cosmetic == "rainbow":            # ``.ov-cos-rainbow .ovnametext``: the colours moving left in 3 s
            span = max(1.0, min(full, room)) * 2
            start = left - ((seconds or 0.0) % 3.0) / 3.0 * span
            rainbow = QLinearGradient(start, 0, start + span, 0)
            rainbow.setSpread(QLinearGradient.RepeatSpread)
            for at, shade in enumerate(RAINBOW):
                rainbow.setColorAt(at / (len(RAINBOW) - 1), QColor(shade))
        if self._scroll_from is not None and self._cut:
            painter.save()
            painter.setClipRect(QRectF(left, 0, room, height), Qt.IntersectClip)
            text(left + self._scrolled(full), self.name, name_font, name_colour, fill=rainbow)
            painter.restore()
            left += room
        else:
            if self._scroll_from is not None:
                self._scroll.stop()               # nothing to scroll: the name fits
            left += text(left, self.name, name_font, name_colour, room, fill=rainbow)
        for part, font, shade, margin, opacity in after:
            left += margin
            if font is chip_font:                 # ``.ovcp::before``: the crossed swords, 1.3em, 3 px before
                side = 1.3 * font.pixelSize()
                painter.save()
                painter.translate(left, (height - side) / 2)
                painter.scale(side / 24, side / 24)
                painter.setPen(QPen(colour(shade), 2.2, Qt.SolidLine, Qt.RoundCap))
                for x1, y1, x2, y2 in SWORDS:
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                painter.restore()
                left += side + 3
            left += text(left, part, font, shade, opacity=opacity)
        painter.restore()

    def _paint_cosmetic(self, painter: QPainter, rect: QRectF, pill: QPainterPath, radius: float,
                        seconds: float | None) -> None:
        """Your row's or the top row's effect, over it (overlay.css ``.ov-cos-*``). A glow the web overlay spreads
        round the row is drawn within it here, where the row's own window ends."""
        kind = self.cosmetic
        painter.save()
        painter.setClipPath(pill)
        if kind == "gold":                        # a gold ring turning once in 3 s (``ovspin``)
            angle = ((seconds or 0.0) % 3.0) / 3.0 * 360
            ring = QConicalGradient(rect.center(), 90 - angle)   # CSS turns clockwise from the top; Qt the other way
            for at, shade in enumerate(GOLD_RING):
                ring.setColorAt(1 - at / (len(GOLD_RING) - 1), QColor(shade))
            self._edge(painter, rect, radius, QBrush(ring), 1.5)
        elif kind == "ember" and seconds is not None:   # an orange edge breathing in 1.4 s, there and back
            turn, phase = divmod(seconds / 1.4, 1.0)
            glow = _eased(1 - phase if int(turn) % 2 else phase)
            edge = QColor.fromRgbF(1.0, (120 + 50 * glow) / 255, (40 + 20 * glow) / 255, 0.55 + 0.4 * glow)
            self._edge(painter, rect, radius, edge, 1.0)
            for inset, share in ((1, 0.5), (2, 0.3), (3, 0.15)):
                halo = QColor.fromRgbF(1.0, (90 + 30 * glow) / 255, (10 + 10 * glow) / 255, (0.4 + 0.45 * glow) * share)
                self._edge(painter, rect, radius, halo, 1.0, inset)
        elif kind == "frost":                     # a cold edge and glow, and a sheen across in 2.6 s
            self._edge(painter, rect, radius, QColor(160, 220, 255, 179), 1.0)
            for inset, alpha in ((1, 64), (2, 38), (3, 19)):
                self._edge(painter, rect, radius, QColor(120, 200, 255, alpha), 1.0, inset)
            if seconds is not None:
                self._sheen(painter, rect, 2.2, 2.6, seconds, 110,
                            ((0.4, QColor(220, 245, 255, 0)), (0.5, QColor(220, 245, 255, 97)),
                             (0.6, QColor(220, 245, 255, 0))))
        elif kind == "aether":                    # violet to teal sweeping across in 4 s, lightening what is under it
            painter.setCompositionMode(QPainter.CompositionMode_Screen)
            self._sheen(painter, rect, 3.0, 4.0, seconds, 100,
                        ((0.0, QColor(120, 80, 255, 0)), (1 / 3, QColor(120, 80, 255, 97)),
                         (2 / 3, QColor(60, 220, 200, 97)), (1.0, QColor(120, 80, 255, 0))))
        elif kind == "starlight":                 # two stars twinkling in turn at the corners
            star = QFont(self.font())
            star.setPixelSize(max(6, round((self.font().pixelSize() or 12) * 0.9)))
            for left, top, delay in ((3, 1, 0.0), (None, None, 0.6)):
                metrics = QFontMetricsF(star)
                width = metrics.horizontalAdvance("✦")
                x = left if left is not None else rect.width() - 5 - width
                y = top if top is not None else rect.height() - 1 - metrics.height()
                painter.setOpacity(_twinkle(seconds, 1.2, delay))
                draw_text(painter, QRectF(x, y, width + 1, metrics.height()), "✦", star, QColor("#fff8d6"),
                          Qt.AlignLeft, STAR_LOOK)
        painter.restore()

    @staticmethod
    def _sheen(painter: QPainter, rect: QRectF, size: float, period: float, seconds: float | None, angle: float,
               stops) -> None:
        """A gradient ``size`` times the row's width moved across it from ``background-position: 120%`` to
        ``-120%`` in ``period`` (``ovsheen``), repeated as a background repeats; at 0% held still."""
        width = rect.width()
        tile = size * width
        position = 0.0 if seconds is None else 1.2 - 2.4 * ((seconds % period) / period)
        offset = (width - tile) * position
        step = QPointF(math.sin(math.radians(angle)), -math.cos(math.radians(angle)))
        length = tile * abs(step.x()) + rect.height() * abs(step.y())
        first = offset - math.ceil((offset + tile) / tile) * tile
        x = first
        while x < width:
            if x + tile > 0:
                centre = QPointF(x + tile / 2, rect.center().y())
                gradient = QLinearGradient(centre - step * (length / 2), centre + step * (length / 2))
                for at, shade in stops:
                    gradient.setColorAt(at, shade)
                painter.fillRect(QRectF(max(0.0, x), 0, min(width, x + tile) - max(0.0, x), rect.height()), gradient)
            x += tile


class ArenaRow(PlayerRow):
    """A row of arena mode with a fighter's three figures: ``kind`` "tri" (``.arn-tri``: DPS, damage taken and HPS at
    the right in their colours, the row's bar its DPS) or "table" (a compact table's row, ``.arn-table``: the name in
    the first 44%, then each figure over a 3 px bar of its share of the most, the row with no bar of its own)."""

    COLOURS = ("#f1d27c", "#ff8f86", "#7fe0a0")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "tri"
        self.figures: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.mosts: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def set_figures(self, kind: str, figures, mosts) -> None:
        figures, mosts = tuple(figures), tuple(mosts)
        if (kind, figures, mosts) != (self.kind, self.figures, self.mosts):
            self.kind, self.figures, self.mosts = kind, figures, mosts
            self.update()

    def right(self) -> str:
        return "  ".join(theme.sfmt(value) for value in self.figures)

    def segments(self) -> list[tuple[str, str]]:
        return [part for part in super().segments() if part[1] != "dead"]   # faded, without the word

    def _paint_right(self, painter: QPainter, rect: QRectF) -> float:
        tl = self.text_look
        px, _name_font, rate_font, _share_font, _chip_font = self._fonts()
        height = rect.height()
        if self.kind == "tri":                    # ``.arn-tri b``: .92em of the rate's, each at least 3.6em wide
            figure = QFont(rate_font)
            figure.setPixelSize(max(6, round(rate_font.pixelSize() * 0.92)))
            least, x = 3.6 * figure.pixelSize(), rect.width() - 9
            colours = (tl.colour("rate", "#ffffff"), "#ff8f86", "#7fe0a0")
            for value, colour in reversed(list(zip(self.figures, colours))):
                text = theme.sfmt(value)
                width = max(least, QFontMetricsF(figure).horizontalAdvance(text))
                draw_text(painter, QRectF(x - width, 0, width, height), text, figure, QColor(colour), Qt.AlignRight,
                          tl, shadow=ROW_SHADOW)
                x -= width
            return x - 6
        # The compact table: three columns after the name's 44%, 8 px apart, 4 px in and 9 px from the right.
        start = rect.width() * 0.44
        left, right = start + 4, rect.width() - 9
        cell = max(0.0, (right - left - 16) / 3)
        figure = QFont(self.font())
        figure.setPixelSize(max(6, round(px * 1.02)))   # ``.arn-cell``: 1.02em, 800, white
        figure.setWeight(QFont.ExtraBold)
        line = figure.pixelSize() * 1.05
        top = (height - (line + 6)) / 2
        for index, (value, most, colour) in enumerate(zip(self.figures, self.mosts, self.COLOURS)):
            x = left + index * (cell + 8)
            draw_text(painter, QRectF(x, top, cell, line), theme.sfmt(value), figure, QColor("#ffffff"),
                      Qt.AlignRight, tl, shadow=ROW_SHADOW)
            bar = QRectF(x, top + line + 3, cell, 3)
            track = QPainterPath()
            track.addRoundedRect(bar, 1.5, 1.5)
            painter.fillPath(track, QColor(255, 255, 255, 26))
            if most > 0 and value > 0:
                fill = QPainterPath()
                fill.addRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * min(1.0, value / most), 3), 1.5, 1.5)
                painter.fillPath(fill, QColor(colour))
        return start


class ArenaCard(QWidget):
    """Arena mode's card in place of the target card (``A2Arena.card``). The opponent's, or your target's among the
    enemies: its class's emblem, its name with its server and faction and the Opponent or Target tag, its HP (or
    Dead) and HP bar, then its combat power, gear score, class, level and arena rating, and the match's score (or the
    share of the damage you took it dealt and its deaths). In the versus layout you and the opponent face each other,
    VS between you, each with a line of figures and an HP bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "foe"
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(2, 6, 2, 4)
        self.box.setSpacing(8)
        # The opponent's card.
        self.foe = QWidget(self)
        row = QHBoxLayout(self.foe)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.portrait = Portrait(self.foe)
        row.addWidget(self.portrait, 0, Qt.AlignVCenter)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.head = Line(self.foe)
        self.hp = CardBar(self.foe, 6, glow=True)
        self.power = Line(self.foe)
        self.match = Line(self.foe)
        for part in (self.head, self.hp, self.power, self.match):
            column.addWidget(part)
        row.addLayout(column, 1)
        self.box.addWidget(self.foe, 1)
        # You against the opponent (``.arn-vs``): two sides of equal width, VS between them.
        self.versus = QWidget(self)
        grid = QHBoxLayout(self.versus)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.sides = []
        for right in (False, True):
            side = QWidget(self.versus)
            line = QHBoxLayout(side)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(7)
            portrait = Portrait(side)
            words = QVBoxLayout()
            words.setContentsMargins(0, 0, 0, 0)
            words.setSpacing(1)
            lines = [Line(side) for _index in range(4)]   # the name, two facts and a line of its own
            for part in lines:
                part.align = Qt.AlignRight if right else Qt.AlignLeft
                part.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)   # as wide as its words, or less
                words.addWidget(part)
            hp = SideBar(side, right)
            words.addSpacing(3)
            words.addWidget(hp)
            # ``.arn-sidemain``: as wide as its widest line (the HP bar with it), the rest of the side left empty.
            if right:
                line.addStretch(1)
                line.addLayout(words, 0)
                line.addWidget(portrait, 0, Qt.AlignVCenter)
            else:
                line.addWidget(portrait, 0, Qt.AlignVCenter)
                line.addLayout(words, 0)
                line.addStretch(1)
            self.sides.append((side, portrait, lines, hp))
        self.mark = Line(self.versus)              # ``.arn-vsmark``
        self.mark.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(self.sides[0][0], 1)
        grid.addWidget(self.mark, 0, Qt.AlignVCenter)
        grid.addWidget(self.sides[1][0], 1)
        self.versus.hide()
        self.box.addWidget(self.versus, 1)

    def texts(self) -> list[str]:
        """Its lines' words, as shown."""
        if self.kind == "versus":
            return [line.text() for _side, _portrait, lines, _hp in self.sides for line in lines if not line.isHidden()]
        return [line.text() for line in (self.head, self.power, self.match) if not line.isHidden()]

    def set_foe(self, arena: dict, fighter: dict, emblem, look: TextLook, px: int, hp_colour: QColor,
                shadow) -> None:
        """The opponent's (or your target's) card."""
        self.kind = "foe"
        self.versus.hide()
        self.foe.show()
        size = look.size("target", px)           # the card's em: the text's size at the target's own
        target = look.font("target", px, 400)
        name = sized(target, size * 1.12, 700)
        who = sized(target, size * 0.78, 600)
        tag = sized(target, size * 0.62, 800, 0.8)
        left = [Run(A.name_of(fighter), name, look.colour("target", "#f4f6f8"))]
        if A.where(fighter):
            left.append(Run(A.where(fighter), who, "#a3abb5", 7))
        left.append(Run("OPPONENT" if A.solo(arena) else "TARGET", tag, "#ff9a92", 7, "tag"))
        hp = A.hp_of(fighter)
        hp_font = look.font("hp", size * 1.22, 700)
        right = ([Run(f"{theme.fixed(hp, 1)}%", hp_font, look.colour("hp", "#e7ecea"))] if hp is not None else
                 [Run("Dead", hp_font, "#ff8f86")] if fighter.get("dead") else [])
        self.portrait.set_picture(emblem)
        self.head.set_runs(left, right, look, shadow)
        self.hp.color = hp_colour
        self.hp.set_fraction((hp or 0) / 100)
        self.hp.setVisible(hp is not None)
        line = sized(target, size * 0.86, 400)
        bold = sized(target, size * 0.86, 700)
        chip, runs = A.power(fighter)
        power = ([Run(chip, sized(target, size * 0.86, 700), "#63d3e6", 0, "cp")] if chip else [])
        power += [Run(text, bold if strong else line, "#e9edf1" if strong else "#aab3bd", 6 if power and not index else 0)
                  for index, (text, strong) in enumerate(runs)]
        self.power.set_runs(power, [], look, shadow)
        self.power.setVisible(bool(power))
        match = [Run(text, bold if strong else line, "#e9edf1" if strong else "#aab3bd")
                 for text, strong in A.match(arena, fighter)]
        self.match.set_runs(match, [], look, shadow)
        self.match.setVisible(bool(match))

    def set_versus(self, arena: dict, me: dict, them: dict, emblems, look: TextLook, px: int, hp_colour: QColor,
                   shadow) -> None:
        """You against the opponent (``versusCard``)."""
        self.kind = "versus"
        self.foe.hide()
        self.versus.show()
        size = look.size("target", px)
        target = look.font("target", px, 400)
        name = sized(target, size * 1.05, 700)
        line = sized(target, size * 0.8, 400)
        bold = sized(target, size * 0.8, 700)
        for (side, portrait, lines, hp), fighter, emblem, mine in zip(self.sides, (me, them), emblems, (True, False)):
            facts = []
            if fighter.get("combat_power"):
                facts.append([("CP ", None), (theme.sfmt(fighter["combat_power"]), "#e9edf1")])
            if fighter.get("rating"):
                facts.append([("Rating ", None), (A.grouped(fighter["rating"]), "#e9edf1")])
            elif fighter.get("gear_score"):
                facts.append([("GS ", None), (A.grouped(fighter["gear_score"]), "#e9edf1")])
            if A.solo(arena):
                extra = [(A.where(fighter), None)] if A.where(fighter) else []
            elif mine:
                extra = [(theme.sfmt(fighter.get("dps")), "#f1d27c"), (" · ", None), (theme.sfmt(fighter.get("dtps")),
                         "#ff8f86"), (" · ", None), (theme.sfmt(fighter.get("hps")), "#7fe0a0")]
            else:
                extra = [(A.where(fighter), None)] if A.where(fighter) else []
                if fighter.get("deaths"):
                    extra += ([(" · ", None)] if extra else []) + [("Deaths ", None),
                                                                  (str(int(A.num(fighter["deaths"]))), "#e9edf1")]
            texts = [[(str(fighter.get("name") or ""), "#eef1f4")]] + facts[:2] + ([extra] if extra else [])
            portrait.set_picture(emblem)
            for index, part in enumerate(lines):
                if index < len(texts):
                    made = name if index == 0 else None
                    runs = [Run(text, made or (bold if colour else line), colour or "#aab3bd")
                            for text, colour in texts[index]]
                    part.set_runs(runs, [], look, shadow)
                    part.show()
                else:
                    part.hide()
            value = A.hp_of(fighter)
            hp.colour = QColor("#5bd16b") if mine else hp_colour
            hp.set_fraction(value / 100 if value is not None else None)
        mark = sized(target, size * 0.95, 900, 1.0)
        self.mark.set_runs([Run("VS", mark, "#f1d27c")], [], look, CHIP_SHADOW)
        self.mark.setFixedWidth(int(QFontMetricsF(mark).horizontalAdvance("VS")) + 2)


class SideBar(QWidget):
    """A versus side's HP bar (``.arn-side .hp``): 4 px, a faint track, yours green from the left, the opponent's in
    the HP's colour from the right; none where the meter has no HP."""

    def __init__(self, parent=None, right: bool = False):
        super().__init__(parent)
        self.right, self.fraction = right, None
        self.colour = QColor("#5bd16b")
        self.setFixedHeight(4)

    def set_fraction(self, fraction) -> None:
        self.fraction = fraction
        self.setVisible(fraction is not None)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        track = QPainterPath()
        track.addRoundedRect(rect, 2, 2)
        painter.fillPath(track, QColor(255, 255, 255, 26))
        width = rect.width() * max(0.0, min(1.0, self.fraction or 0.0))
        if width > 0:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(rect.width() - width if self.right else 0, 0, width, rect.height()), 2, 2)
            painter.fillPath(fill, self.colour)


class Grip(QWidget):
    """A resize grip on the overlay's edge (overlay.css ``.ovgrip``, with ``overlay_resizable``): ``right`` drags its
    width (260 to 800 px), ``bottom`` its height (70 to 800), ``corner`` both; on release the size is kept as
    ``overlay_width`` and ``overlay_height``, as the web overlay keeps it."""

    TIPS = {"right": "Drag to resize the overlay width", "bottom": "Drag to resize the overlay height",
            "corner": "Drag to resize the overlay"}

    def __init__(self, edge: str, parent=None):
        super().__init__(parent)
        self.edge = edge
        self.setObjectName("ovgrip")               # WindowHost keeps it live through click-through
        self.setToolTip(self.TIPS[edge])
        self.setCursor({"right": Qt.SizeHorCursor, "bottom": Qt.SizeVerCursor}.get(edge, Qt.SizeFDiagCursor))
        self.setAttribute(Qt.WA_Hover)
        self._from: QPoint | None = None
        self._size = (0, 0)

    def event(self, event):
        if event.type() in (QEvent.HoverEnter, QEvent.HoverLeave):
            self.update()                          # brighter under the pointer
        return super().event(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        hover = self.underMouse()
        rect = QRectF(self.rect())
        gold, clear = QColor(233, 203, 128), QColor(233, 203, 128, 0)
        if self.edge == "corner":                 # 315°: from the corner inward, gone by 60%
            gradient = QLinearGradient(rect.bottomRight(), rect.topLeft())
            gold.setAlphaF(0.8 if hover else 0.5)
            gradient.setColorAt(0, gold)
            gradient.setColorAt(0.6, clear)
            shape = rect.adjusted(-8, -8, 0, 0)    # rounded at its outer corner only
        else:
            gradient = QLinearGradient(rect.topRight() if self.edge == "right" else rect.bottomLeft(), rect.topLeft())
            gold.setAlphaF(0.45 if hover else 0.18)
            gradient.setColorAt(0, gold)
            gradient.setColorAt(1, clear)
            shape = rect.adjusted(-8, 0, 0, 0) if self.edge == "right" else rect.adjusted(0, -8, 0, 0)
        path = QPainterPath()
        path.addRoundedRect(shape, 8, 8)
        painter.setClipRect(rect)
        painter.fillPath(path, gradient)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            overlay = self.window()
            self._from = event.globalPosition().toPoint()
            self._size = (overlay.width(), overlay.card.height())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._from is None:
            return
        delta = event.globalPosition().toPoint() - self._from
        width = max(260, min(800, self._size[0] + delta.x())) if self.edge in ("right", "corner") else None
        height = max(70, min(800, self._size[1] + delta.y())) if self.edge in ("bottom", "corner") else None
        self.window().resize_to(width, height)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._from is not None:
            self._from = None
            self.window().save_size(self.edge)
            event.accept()


class MeterOverlay(QWidget):
    """The meter overlay window. ``api`` is the app's local API (None in tests, which hand it the readings), and
    ``store`` keeps what the web overlay keeps in the page's own storage: the opacity and the metric shown."""

    def __init__(self, api: AppApi | None = None, parent_process=None, store: QSettings | None = None, win32=None):
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
        self.host = WindowHost(self, win32)        # its place on the desktop, the game window and click-through
        self._press: QPoint | None = None        # where a press began, to tell a click from a move
        self._capture_busy = False
        self._seqs: dict = {}                    # the app's command counters as first read (the screenshot hotkey)
        self.text_look = TextLook({})             # the fonts, the text colours and effects (look.py)
        self._shown_look: dict | None = None      # the look as last handed out, to tell when it changes
        self._effects: dict[QLabel, TextEffect] = {}   # the labels' effects, held here: a label does not hold its own
        self._user_width: int | None = None       # a grip's drag, over the saved width and height
        self._user_height: int | None = None
        self._bg_image: QImage | None = None      # the background image (``/overlay-background``) as read
        self._bg_pixmap: QPixmap | None = None
        self._bg_wanted = self._bg_asking = self._bg_failed = False
        self._contrast_key, self._contrast = None, None
        self.target_text = self.dummy_text = self.contribution_text = ""   # their lines as plain text
        self.status_text = ""                     # the fight's status, the clock's tooltip (``#ovstatus``, folded away)
        self.unavailable = False                  # the app did not answer the last reading (``meterUnavailable``)
        self.refresh_error = ""
        self.last_success: float | None = None
        # The card's parts in the compact layout's order (overlay.css ``#ov.ov-nm``): what the app could not answer,
        # the counter lines, the target card, the training-dummy parse, the rows' part, the player panel, the graph
        # and the cooldowns; under them the clock, your contribution, the identity line and the events strip as
        # chips; on a line of their own the ping, the frame rate and the toolbar; the options when open. Each part
        # keeps its margins as the web card's flex items do, none shared.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = _Card(self)
        outer.addWidget(self.card)
        box = QVBoxLayout(self.card)
        box.setContentsMargins(9, 5, 9, 9)        # the whole card's padding (4 8 8) and its 1 px edge
        box.setSpacing(0)
        self.box = box
        self.connection = QWidget(self.card)      # ``#ovconnection``: why, how long since the last reading, Retry
        connection = FlowLayout(self.connection, Qt.AlignLeft, (4, 2))
        connection.setContentsMargins(10, 6, 10, 6)
        self.reason = QLabel("", self.connection)
        self.reason.setObjectName("ovreason")
        self.reason.setWordWrap(True)
        self.retry = QPushButton("Retry", self.connection)
        self.retry.setObjectName("ovretry")
        self.retry.setCursor(Qt.PointingHandCursor)
        self.retry.clicked.connect(self._poll_meter)
        connection.addWidget(self.reason)
        connection.addWidget(self.retry)
        self.connection.hide()
        box.addWidget(self.connection)
        # The counters across the top (``#ovlines``). Its box stays when no counter is shown, as the web overlay's
        # does, its padding above the target card all the same.
        self.lines_part = QWidget(self.card)
        lines = QVBoxLayout(self.lines_part)
        lines.setSpacing(0)
        # Each counter its icon and its count, 22 px apart (``gap: 12px`` and each one's ``margin-right: 10px``).
        self.lines = Chip(self.lines_part, padding=(0, 0, 0, 0), gap=(22.0, 2.0))
        self.lines.hide()
        lines.addWidget(self.lines)
        box.addWidget(self.lines_part)
        # The target card (overlay.js ``targetCard``): the portrait, then the name with the others struck and the HP
        # on one line, the HP, time-to-kill and break bars under them, and the time to kill and the break below.
        self.target_card = QWidget(self.card)
        card_row = QHBoxLayout(self.target_card)
        card_row.setContentsMargins(2, 6, 2, 4)        # ``padding: 6px 2px 4px`` on the whole card
        card_row.setSpacing(8)
        self.target_row = card_row
        self.portrait = Portrait(self.target_card)
        card_row.addWidget(self.portrait, 0, Qt.AlignVCenter)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        head_line = QHBoxLayout()
        head_line.setSpacing(8)
        self.target = QLabel("", self.target_card)   # the name, and the others struck in the same instant
        self.target.setObjectName("ovtarget")
        self.target.setTextFormat(Qt.RichText)
        self.target.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.target_nums = QLabel("", self.target_card)   # its HP in damage units (``.ovhpnum``)
        self.target_nums.setObjectName("ovtnums")
        self.target_hp = QLabel("", self.target_card)     # its HP's share, to a tenth (``.ovhp``)
        self.target_hp.setObjectName("ovthp")
        head_line.addWidget(self.target, 1, Qt.AlignBottom)
        head_line.addWidget(self.target_nums, 0, Qt.AlignBottom)
        head_line.addWidget(self.target_hp, 0, Qt.AlignBottom)
        column.addLayout(head_line)
        self.target_bars = QWidget(self.target_card)      # ``.ovtbars``: 4 px under the name, 3 px apart
        bars = QVBoxLayout(self.target_bars)
        bars.setContentsMargins(0, 4, 0, 0)
        bars.setSpacing(3)
        self.hp = CardBar(self.target_bars, 6, glow=True)
        self.ttk_bar = TtkBar(self.target_bars)
        self.gauge = GaugeBar(self.target_bars)
        for bar in (self.hp, self.ttk_bar, self.gauge):
            bar.hide()
            bars.addWidget(bar)
        column.addWidget(self.target_bars)
        self.target_line = QLabel("", self.target_card)   # the time to kill, the enrage timer, the break (``.ovtline``)
        self.target_line.setObjectName("ovtline")
        self.target_line.setTextFormat(Qt.RichText)
        self.target_line.setWordWrap(True)        # on to a second line between its parts, in a narrow card
        self.target_line.setContentsMargins(0, 4, 0, 0)
        column.addWidget(self.target_line)
        card_row.addLayout(column, 1)
        self.target_card.hide()
        box.addWidget(self.target_card)
        self.arena_card = ArenaCard(self.card)     # arena mode's card in its place (``A2Arena.card``)
        self.arena_card.hide()
        box.addWidget(self.arena_card)
        self.dummy = QLabel("")                   # the training-dummy parse (``#ovdummy``)
        self.dummy.setObjectName("ovdummy")
        self.dummy.setTextFormat(Qt.RichText)
        box.addWidget(self.dummy)
        # The rows' part (``#ovcontent``), 6 px under what is above it: the meter's warning or why there are no rows
        # (each a chip, ``.muted``), then the rows, 4 px apart.
        self.content = QWidget(self.card)
        content = QVBoxLayout(self.content)
        content.setContentsMargins(0, 6, 0, 0)
        content.setSpacing(4)
        self.content_box = content
        self.warning = QLabel("", self.content)   # the meter's warning over the rows
        self.empty = QLabel("", self.content)     # the rows' place when there are none to show
        for note in (self.warning, self.empty):
            note.setObjectName("ovnote")
            note.setWordWrap(True)
            note.setContentsMargins(9, 4, 9, 4)
            note.hide()
            content.addWidget(note, 0, Qt.AlignLeft)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(4)               # ``#ov.ov-nm .ovrow { margin: 0 0 4px }``
        content.addLayout(self.rows_box)
        self.arena_box = QVBoxLayout()            # arena mode's rows in their place (``A2Arena.body``)
        self.arena_box.setSpacing(0)
        content.addLayout(self.arena_box)
        self.plan_map = PlanMap(self.content)     # the raid plan's map in the plan view (``.ovarena``)
        self.plan_map.hide()
        content.addWidget(self.plan_map, 0, Qt.AlignHCenter)
        box.addWidget(self.content)
        self.card.rows_part = self.content
        self.panel = PlayerPanel()
        self.panel.close_button.clicked.connect(self.close_detail)
        self.panel_scroll = QScrollArea(self.card)  # the panel scrolls within the room the screen leaves it
        self.panel_scroll.setWidget(self.panel)
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll.viewport().setAutoFillBackground(False)
        self.panel_scroll.setContentsMargins(0, 2, 0, 4)   # ``#ovdetail { margin: 2px 0 4px }``
        self.panel_scroll.hide()
        box.addWidget(self.panel_scroll)
        self.graph = SparkGraph(self.card, 40)    # the party's total over the fight (overlay_dps_graph)
        self.graph.setContentsMargins(0, 2, 0, 4)   # 34 px, ``margin: 2px 0 4px``
        self.graph.setToolTip("The party's total over the fight, one point per reading")
        self.graph.hide()
        box.addWidget(self.graph)
        self.cooldowns = CooldownStrip(self.card)  # below the meter, the web overlay's default; the setting moves it
        box.addWidget(self.cooldowns)
        # Under the rows (``order: 65`` to ``71``): the fight's clock, your contribution, the identity line and the
        # events strip, chips side by side and on to another line where there is no room.
        self.chips = QWidget(self.card)
        self.chips.setProperty("ovgap", True)     # between the chips is the game, not the overlay
        chips = FlowLayout(self.chips, Qt.AlignLeft, (6, 4), lead=4, centre=False)
        self.clock = Chip(self.chips, padding=(6, 3, 9, 3), gap=(8.0, 2.0))   # ``#ovclock``
        self.contribution = Chip(self.chips, padding=(9, 3, 9, 3))            # ``#ovcontribution``
        self.identity = QLabel("", self.chips)    # who you are, and the actors in doubt (``#ovidentity``)
        self.identity.setObjectName("ovidentity")
        self.identity.setWordWrap(True)
        self.events = QLabel("", self.chips)      # the next events and observed field bosses (``#ovevents``)
        self.events.setObjectName("ovevents")
        self.events.setTextFormat(Qt.RichText)
        for chip in (self.identity, self.events):
            chip.setContentsMargins(9, 3, 9, 3)
        for chip in (self.clock, self.contribution, self.identity, self.events):
            chip.hide()
            chips.addWidget(chip)
        box.addWidget(self.chips)
        # On a line of their own (``order: 80`` to ``83``): the ping, the frame rate and, to the right, the toolbar.
        self.foot = QWidget(self.card)
        self.foot.setProperty("ovgap", True)
        foot = FlowLayout(self.foot, Qt.AlignLeft, (4, 6), lead=6, centre=False)
        self.ping = Chip(self.foot, padding=(8, 3, 8, 3), gap=(4.0, 2.0))   # the capture's round trip (``#ovping``)
        self.ping.hide()
        self.fps = FpsChip(self.foot)             # the overlay's own frame rate (``#ovfps``)
        self.fps.on_count = self._show_fps
        self.fps.hide()
        self.toolbar = QWidget(self.foot)         # ``.ovhd``: the metric chip and the buttons, on to another line too
        tools = FlowLayout(self.toolbar, Qt.AlignRight, (0, 0))
        tools.setContentsMargins(3, 1, 3, 1)
        self.metric_chip = MetricChip(self.toolbar)
        self.metric_chip.clicked.connect(self.next_metric)
        tools.addWidget(self.metric_chip)
        # The views (``.ovtabs``, ``order: 1``): the meter and the raid plan, the tab of the view not shown.
        self.tabs: dict[str, IconButton] = {}
        for view, icon_name, words, tip in (("meter", "meter", "Meter", "The meter"),
                                            ("plan", "plan", "Plan", "The raid plan: your saved Raid Planner plans")):
            tab = IconButton(icon_name, words, tip, self.toolbar)
            tab.clicked.connect(lambda _checked=False, v=view: self.set_view(v))
            tools.addWidget(tab)
            self.tabs[view] = tab
        self.tabs["meter"].hide()
        self.tools: dict[str, IconButton] = {}
        actions = {"lock": self.toggle_lock, "split": self.new_fight, "copy": self.copy,
                   "options": self.toggle_options, "capture": self.toggle_capture, "hide": self.hide_overlay}
        for key, name, text, tip in TOOLS:
            button = IconButton(name, text, tip, self.toolbar)
            button.clicked.connect(actions[key])
            tools.addWidget(button)
            self.tools[key] = button
        self.tools["options"].setCheckable(True)
        for piece in (self.ping, self.fps, self.toolbar):
            foot.addWidget(piece)
        foot.push(self.toolbar)
        box.addWidget(self.foot)
        # The options (``order: 90``, ``91``), folded away until the toolbar's Options opens them: the pet grouping
        # and the damage filters side by side, then the opacity.
        self.options = QWidget(self.card)
        stack = QVBoxLayout(self.options)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        choices = QWidget(self.options)
        flow = FlowLayout(choices, Qt.AlignLeft, (10, 0))
        flow.setContentsMargins(10, 11, 10, 5)    # ``margin-top: 6px; padding: 5px 10px``
        self.combine = QCheckBox("Combine pets with owner", choices)
        self.combine.setToolTip("Group recorded pet damage and healing into the linked owner")
        self.combine.setChecked(True)
        self.combine.clicked.connect(self._combine_clicked)
        self.boss_only = QCheckBox("Boss damage only", choices)
        self.boss_only.setToolTip("Count only the damage dealt to bosses: dungeon bosses, mini-bosses, field and "
                                  "world bosses. Damage to trash mobs and, in the open world (the Abyss), to other "
                                  "players is left out")
        self.boss_only.clicked.connect(lambda checked: self._filter_clicked("overlay_boss_only", checked))
        self.pvp_only = QCheckBox("Player (PvP) damage only", choices)
        self.pvp_only.setToolTip("Count only the damage dealt to other players (PvP), leaving out damage to monsters. "
                                 "With Boss damage only also on, damage to bosses counts too")
        self.pvp_only.clicked.connect(lambda checked: self._filter_clicked("overlay_pvp_only", checked))
        # Arena mode's (0.2.395), saved settings too: arena mode itself, all three metrics for the party, the player
        # cards window (the app opens or closes it), the layout and the cards' style.
        self.arena_checks = {}
        for key, words, tip in (
                ("overlay_arena_mode", "Arena mode", "In the Arena of Solitude, the Arena of Cooperation and a "
                 "battlefield: your DPS, damage taken and HPS at once, and your opponent's (or your target's) card with "
                 "their combat power, arena rating and HP"),
                ("overlay_arena_all3", "All 3 for party", "Arena mode in a team match: DPS, damage taken and HPS for "
                 "every party member, not only for you"),
                ("overlay_players_enabled", "Player cards window", "A second window with a card for every player of the "
                 "PvP match: server, combat power, gear score, HP and damage")):
            check = QCheckBox(words, choices)
            check.setToolTip(tip)
            check.clicked.connect(lambda checked, k=key: self._arena_clicked(k, checked))
            self.arena_checks[key] = check
        self.arena_picks = {}
        picks = []
        for key, words, tip, choices_ in (
                ("overlay_arena_layout", "Arena layout", "How arena mode lays out the three metrics: Stacked (a section "
                 "each), Compact (one row per fighter) or Versus (you against the opponent)",
                 (("stacked", "Stacked"), ("compact", "Compact"), ("versus", "Versus"))),
                ("overlay_players_style", "Player cards", "How the player cards window shows the players: a list, or a "
                 "grid with the two teams side by side", (("list", "List"), ("grid", "Grid")))):
            holder = QWidget(choices)             # ``.ovsel``: its words, then the choice
            line = QHBoxLayout(holder)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(3)
            label = QLabel(words, holder)
            label.setObjectName("ovoption")
            pick = QComboBox(holder)
            pick.setObjectName("ovsel")
            for value, text in choices_:
                pick.addItem(text, value)
            pick.setToolTip(tip)
            holder.setToolTip(tip)
            pick.activated.connect(lambda _index, k=key, p=pick: self._arena_clicked(k, p.currentData()))
            line.addWidget(label)
            line.addWidget(pick)
            self.arena_picks[key] = pick
            picks.append((holder, label))
        self.message = QLabel("", choices)        # why an option could not be changed (``#ovpetstatus``)
        self.message.setObjectName("ovoption")
        self.message.hide()
        for piece in (self.combine, self.boss_only, self.pvp_only, *self.arena_checks.values(),
                      *(holder for holder, _label in picks), self.message):
            flow.addWidget(piece)
        stack.addWidget(choices)
        fade = QWidget(self.options)              # ``.ovfoot``: the opacity, and the app's name
        row = QHBoxLayout(fade)
        row.setContentsMargins(10, 8, 10, 5)      # ``margin-top: 3px; padding: 5px 10px``
        row.setSpacing(8)
        opacity = QLabel("Opacity", fade)
        opacity.setObjectName("ovoption")
        self.slider = QSlider(Qt.Horizontal, fade)
        self.slider.setRange(20, 100)
        self.slider.setToolTip("The card's opacity behind the readings")
        brand = QLabel("Aion 2 Calc", fade)
        brand.setObjectName("ovbrand")
        row.addWidget(opacity)
        row.addWidget(self.slider, 1)
        row.addWidget(brand)
        stack.addWidget(fade)
        self.option_labels = [self.combine, self.boss_only, self.pvp_only, *self.arena_checks.values(),
                              *(label for _holder, label in picks), self.message, opacity, brand]
        self.options.hide()
        box.addWidget(self.options)
        box.addStretch(1)                         # a card taller than its readings (``overlay_height``) ends empty
        self.grips = {edge: Grip(edge, self) for edge in ("right", "bottom", "corner")}   # ``overlay_resizable``
        for grip in self.grips.values():
            grip.hide()
        self.rows: list[PlayerRow] = []
        self.look = RowLook({})
        self._arena_pool: dict[str, list[QWidget]] = {}   # arena mode's widgets, by kind, kept for the next reading
        self._arena_order: list[QWidget] = []
        self.view = "meter"                       # the meter, or the raid plan (``tab``)
        self.plans: dict = {}                     # the Raid Planner's saved plans, as the app keeps them
        self._plans_at = -math.inf
        self._plan_start = time.monotonic()       # the plan view's own clock (``t``), running from the start
        self._plan_timer = QTimer(self)
        self._plan_timer.timeout.connect(self._show_plan)
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
        self._anim_timer = QTimer(self)           # the colour cycle and the sheen
        self._anim_timer.setInterval(ANIMATION_MS)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_start = time.monotonic()
        self._pollers: list[Poller] = []
        self._meter_poller = self._settings_poller = None
        self._catalog: dict | None = None        # event-schedules.json, from the app
        self._catalog_asked = False
        self._announced: set[str] = set()         # the strip's events as last chimed for
        self._primed = False
        self.events_clock = lambda: time.time() * 1000
        self._events_timer = QTimer(self)
        self._events_timer.setInterval(1000)
        self._events_timer.timeout.connect(self.render_events)
        self._events_timer.start()
        self.pictures = Pictures(api, self)        # the classes' emblems and the bosses' portraits
        self.pictures.changed.connect(lambda: self.apply_meter(self.answer))
        self._still = False                       # effects held still: performance mode, or less motion asked
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
        self.host.start()

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
        self.host.stop()
        for poller in self._pollers:
            poller.stop()
        if self.requests is not None:
            self.requests.stop()
        self.pictures.stop()
        self._anim_timer.stop()
        self._plan_timer.stop()
        self.fps.run(False)
        forget_pictures()
        forget_icons()
        super().closeEvent(event)

    # ------------------------------------------------------------------ look
    def _row_height(self) -> int:
        """A row's height: ``--nm-row-h``, the rows' height setting (14 to 48 px) and 6."""
        return theme.clamp_int(self.ui.get("overlay_row_height"), 14, 48, 22) + 6

    def _px(self) -> int:
        """The overlay's text size: 12 px at its font size (``overlay_font_scale``, 80% to 160%)."""
        return max(8, round(12 * self.text_look.scale))

    def _style(self) -> None:
        """The overlay's style sheet, from its look. Its font is the sheet's too: a font set on the window after a
        sheet does not reach the widgets inside it, which keep the family they were first styled with. The footer's
        texts keep the web overlay's own sizes (the contribution 10.5 px, the identity line, the events and the
        options 10 px), which the overlay's text size does not change there either."""
        tl, px = self.text_look, self._px()
        weight = tl.weight
        families = ", ".join(f'"{family}"' for family in tl.families())
        c = theme.COLORS
        header = tl.colour("header", c["gold"])
        target_px, target_weight = tl.size("target", px), tl.weight_of("target", 400)
        target_family = tl.family_css("target")
        sheet = (
            f"QWidget {{ font-family: {families}; font-size: {px}px; font-weight: {weight}; }}"
            f"QLabel {{ color: {c['text']}; background: transparent; }}"
            f"QLabel#ovtarget {{ {tl.css('target', px, 400, '#f4f6f8')} }}"
            f"QLabel#ovtnums {{ color: #a3abb5; {target_family} font-size: {round(target_px * 0.85)}px;"
            f" font-weight: {target_weight}; }}"
            f"QLabel#ovthp {{ {tl.css('hp', target_px * 1.22, 700, '#e7ecea')} }}"
            f"QLabel#ovtline {{ color: #aab3bd; {target_family} font-size: {round(target_px * 0.86)}px;"
            f" font-weight: {target_weight}; }}"
            f"QLabel#ovdummy {{ color: #cdd6e6; font-size: 11px; font-weight: 400; }}"
            f"QLabel#ovdummy[ok=\"true\"] {{ color: #8fd0a0; }}"
            f"QLabel#ovnote {{ color: #9aa3b5; font-weight: 400; }}"
            f"QLabel#ovidentity {{ {tl.css('identity', 10, 400, '#e8cf8e')} }}"
            f"QLabel#ovevents {{ color: #9aa3b5; font-size: 10px; font-weight: 400; }}"
            f"QLabel#ovreason {{ color: #e8cf8e; font-size: 11px; font-weight: 400; }}"
            f"QPushButton {{ color: {c['muted']}; background: transparent; border: none; padding: 0 3px; }}"
            f"QPushButton#ovretry {{ margin: 2px; padding: 1px 6px; border: 1px solid rgba(185, 152, 79, 102);"
            f" border-radius: 4px; background: #1c2438; color: #e9e6df; font-size: 11px; font-weight: 400; }}"
            f"QCheckBox, QLabel#ovoption {{ color: #7f8aa3; background: transparent; font-size: 10px;"
            f" font-weight: 400; spacing: 3px; }}"
            f"QLabel#ovbrand {{ color: rgba(185, 152, 79, 217); font-size: 10px; font-weight: 700; }}"
            f"QCheckBox::indicator {{ width: 11px; height: 11px; border: 1px solid {c['line2']}; border-radius: 3px;"
            f" background: {c['bg2']}; }}"
            f"QCheckBox::indicator:checked {{ background: {c['gold']}; border-color: {c['gold']}; }}"
            f"QScrollArea {{ background: transparent; }}"
            f"QLabel#ovdname {{ color: {tl.colour('name', '#e9f7ff')}; font-weight: 800;"
            f" font-size: {round(px * 1.15)}px; }}"
            f"QLabel#ovdsub {{ color: #9aa8bb; font-size: {round(px * 0.9)}px; }}"
            f"QLabel#ovdsec {{ color: {header}; font-weight: 700; font-size: {round(px * 0.85)}px; }}"
            f"QLabel#ovdtile {{ background: rgba(255, 255, 255, 15); border-radius: 6px; padding: 4px 6px; }}"
            f"QLabel#ovdicon {{ background: rgba(0, 0, 0, 102); border-radius: 4px; color: #cdd6e6; font-size: 9px; }}"
            f"QLabel#ovdval {{ color: {tl.colour('total', '#9aa8bb')}; }}"
            f"QPushButton#ovdclose {{ color: #9aa8bb; font-size: {round(px * 1.15)}px; }}"
            f"QPushButton#ovdclose:hover {{ color: #ffffff; }}")
        if sheet != getattr(self, "_sheet", None):    # the settings come every 3 s: restyle only on a change
            self._sheet = sheet
            self.setStyleSheet(sheet)
            self.panel.reading = {}               # the tiles' sizes follow the font: draw the panel again

    def _apply_look(self) -> None:
        """Hand the look to all that draws text: the style sheet, the rows, the panel's tiles, the time-to-kill bar,
        the toolbar, the labels' effects, and the colour cycle and the sheen."""
        tl = self.text_look
        changed = vars(tl) != self._shown_look    # the settings come every 3 s, mostly the same: nothing to redraw
        self._shown_look = dict(vars(tl))
        self._style()
        self.ttk_bar.color = QColor(tl.ttk_colour)
        self.ttk_bar.update()
        value = tl.colour("rate", "#ffffff")
        if value != self.panel.value_colour:
            self.panel.value_colour, self.panel.reading = value, {}   # the tiles drawn again in it
        if changed:
            for row in self.rows:
                row.set_text_look(tl)
            # The toolbar: its buttons at the text's size and the header's own (``--ov-header-fs``), in the header's
            # colour; the metric chip at the text's size alone.
            header_scale = tl.fonts.get("header", (None, None, None))[1] or 1.0
            for button in self.tools.values():
                button.scale, button.colour = tl.scale * header_scale, tl.colour("header", "#c9d1db")
                button.updateGeometry()
                button.update()
            self.metric_chip.set_look(tl, tl.scale, tl.families("header"))
        # The cycle and the sheen move while either is on, held still in performance mode and when the system asks
        # for less motion (the web overlay's ``ov-perf`` and ``prefers-reduced-motion``).
        self._still = self._perf or reduced_motion()
        for row in self._all_rows():
            row.moving = not self._still
        moving = (tl.cycle or tl.retro or bool(self.look.me_cosmetic or self.look.top_cosmetic)) and not self._still
        if moving and not self._anim_timer.isActive():
            self._anim_start = time.monotonic()
            self._anim_timer.start()
        elif not moving:
            self._anim_timer.stop()
        self._sync_effects(changed)
        self._paint_moment(time.monotonic() - self._anim_start if moving else None)

    def _all_rows(self) -> list[PlayerRow]:
        """The meter's rows and arena mode's."""
        return self.rows + [row for row in self._arena_pool.get("row", []) + self._arena_pool.get("arow", [])]

    def _text_labels(self) -> list[QWidget]:
        """What shows text through a label's effect: the parts at the top and the chips under the rows."""
        return [self.target, self.target_nums, self.target_hp, self.target_line, self.dummy, self.reason,
                *self._chip_labels()]

    def _chip_labels(self) -> list[QWidget]:
        """The labels that float as chips, their text over the chips' shadow in every background (``--nm-shadow``):
        the rows' notes, the identity line, the events strip and the options."""
        return [self.warning, self.empty, self.identity, self.events, *self.option_labels]

    def _sync_effects(self, changed: bool = True) -> None:
        """Each text label's effect (``TextEffect``): the chips' shadow under the floating ones (and under the top
        parts too with no background at all), with the outline, glow or halo, or the blend; none otherwise, since
        drawn through one a label's text loses its sub-pixel smoothing."""
        tl = self.text_look
        floating = set(self._chip_labels())
        bare = self.card.mode == "none"           # ``#ov.ov-nm.ov-bg-none``: the lines, the target, the dummy too
        for label in self._text_labels():
            shadow = CHIP_SHADOW if label in floating or bare else None
            wanted = tl.painted or shadow is not None
            effect = self._effects.get(label)
            if wanted and effect is None:
                effect = TextEffect(tl, label, shadow)
                label.setGraphicsEffect(effect)
                self._effects[label] = effect
            elif wanted:
                if changed or effect.shadow != shadow:
                    effect.set_look(tl, shadow)
            elif effect is not None:
                label.setGraphicsEffect(None)    # Qt deletes it
                del self._effects[label]

    def _animate(self) -> None:
        self._paint_moment(time.monotonic() - self._anim_start)

    def _paint_moment(self, seconds: float | None) -> None:
        """The colour cycle and the sheen ``seconds`` in (None: held still): the rows' names, and the toolbar turning
        through the hues (``#ov.ov-cycle .ovhd``), unless the sheen's animation takes the cycle's place there, as it
        does on the web overlay (where the sheen itself does not show on the toolbar)."""
        tl = self.text_look
        for row in self._all_rows():
            if row.seconds != seconds:
                row.seconds = seconds
                if not row.isHidden() and (tl.cycle or tl.retro or row.cosmetic):
                    row.update()
        turning = seconds if tl.cycle and not tl.retro else None
        for button in (self.metric_chip, *self.tools.values()):
            if button.seconds != turning:
                button.seconds = turning
                button.update()

    # ------------------------------------------------------------------ the background image
    def _want_background(self, ui: dict) -> None:
        """The background image's settings (overlay.js ``applyBackground``): with one set and its opacity above 0 it
        is read from the app once, and again when it could not be read, with the next settings."""
        card = self.card
        card.bg_opacity = theme.clamp_int(ui.get("overlay_bg_opacity"), 0, 100, 100) / 100
        card.bg_zoom = theme.clamp_int(ui.get("overlay_bg_zoom"), 50, 200, 100) / 100
        card.bg_darken = theme.clamp_int(ui.get("overlay_bg_darken"), 0, 100, 20) / 100
        wanted = ui.get("overlay_bg_set") is True and card.bg_opacity > 0
        if not wanted:
            self._bg_image = self._bg_pixmap = None
            self._bg_failed = False
        elif not self._bg_wanted or self._bg_failed:
            self._fetch_background()
        self._bg_wanted = wanted
        self._show_background()

    def _fetch_background(self) -> None:
        if self.requests is None or self._bg_asking:
            return
        self._bg_asking, self._bg_failed = True, False
        self.requests.get_bytes("background", f"/overlay-background?v={int(time.time() * 1000)}")

    def _show_background(self) -> None:
        """The image in the card but in the none mode, and the text's colour for it (overlay.js
        ``applyAutoContrast``, with the image set in any mode): white and blended, or by its luminance; light text
        when it could not be read, the user's own colours while it is read."""
        tl, card = self.text_look, self.card
        card.background = self._bg_pixmap if self._bg_wanted and card.mode != "none" else None
        tl.contrast, tl.blend = None, False
        if self._bg_wanted and tl.autocontrast == "blend":
            tl.contrast, tl.blend = "#ffffff", True
        elif self._bg_wanted and tl.autocontrast == "luminance":
            if self._bg_image is not None:
                key = (self._bg_image.cacheKey(), card.bg_darken)
                if key != self._contrast_key:
                    self._contrast_key, self._contrast = key, contrast_colour(self._bg_image, card.bg_darken)
                tl.contrast = self._contrast
            elif self._bg_failed:
                tl.contrast = "#f4f1ea"
        card.update()

    def _background_read(self, data) -> None:
        self._bg_asking = False
        image = QImage.fromData(bytes(data)) if isinstance(data, (bytes, bytearray)) and data else QImage()
        if image.isNull():
            self._background_lost()
            return
        if max(image.width(), image.height()) > BACKGROUND_LIMIT:
            image = image.scaled(BACKGROUND_LIMIT, BACKGROUND_LIMIT, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._bg_image, self._bg_pixmap, self._bg_failed = image, QPixmap.fromImage(image), False
        self._restyle()

    def _background_lost(self) -> None:
        """The image could not be read (none was uploaded, or the app is gone): none is shown, and it is asked for
        again with the next settings."""
        self._bg_asking, self._bg_failed = False, True
        self._bg_image = self._bg_pixmap = None
        self._restyle()

    def _restyle(self) -> None:
        self._show_background()
        self._apply_look()
        self.apply_meter(self.answer)

    # ------------------------------------------------------------------ resizing
    def resize_to(self, width: int | None, height: int | None) -> None:
        """A grip's drag: the overlay's width, and its card's least height, kept over the saved settings from then
        on (overlay.js ``userWidth`` and ``userHeight``)."""
        if width is not None:
            self._user_width = int(width)
            self.setFixedWidth(self._user_width)
        if height is not None:
            self._user_height = int(height)
            self.card.setMinimumHeight(self._user_height)
        self._relayout()

    def save_size(self, edge: str) -> None:
        """A grip let go: the size it changed is saved, as the web overlay saves it."""
        body = {}
        if edge in ("right", "corner") and self._user_width is not None:
            body["overlay_width"] = self._user_width
        if edge in ("bottom", "corner") and self._user_height is not None:
            body["overlay_height"] = self._user_height
        if body and self.requests is not None:
            self.requests.post("size", "/api/ui", body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width, height = self.width(), self.height()   # overlay.css ``#ovresize``, ``-b`` and ``-c``
        self.grips["right"].setGeometry(width - 12, 4, 12, max(0, height - 20))
        self.grips["bottom"].setGeometry(4, height - 12, max(0, width - 20), 12)
        self.grips["corner"].setGeometry(width - 16, height - 16, 16, 16)
        for grip in self.grips.values():
            grip.raise_()

    def apply_ui(self, ui: dict) -> None:
        """Take the overlay's settings from the app's answer to ``/api/ui``."""
        if not isinstance(ui, dict):
            return
        first = not self.ui
        self.ui = ui
        self.text_look = TextLook(ui)
        self.setFixedWidth(self._user_width or theme.clamp_int(ui.get("overlay_width"), 260, 800, 340))
        height = self._user_height
        self.card.setMinimumHeight(theme.clamp_int(ui.get("overlay_height"), 0, 800, 0) if height is None else height)
        for grip in self.grips.values():          # the edges drag the size (``overlay_resizable``)
            grip.setVisible(ui.get("overlay_resizable") is True)
        row_height = self._row_height()
        for row in self.rows:
            row.setFixedHeight(row_height)
        self.hp.color = QColor(hex_colour(ui.get("overlay_hp_color")) or "#e05a5a")
        self.look = RowLook(ui)
        mode = ui.get("overlay_bg_mode")
        self.card.mode = mode if mode in ("card", "top", "none") else "card"
        self._place_parts(self.card.mode)
        self._want_background(ui)
        top = ui.get("overlay_cooldowns_position") == "top"
        if top != self._cooldowns_top:            # the strip above the player rows, or below them
            self._cooldowns_top = top
            self.box.removeWidget(self.cooldowns)
            self.box.insertWidget(self.box.indexOf(self.dummy) + 1 if top else self.box.indexOf(self.graph) + 1,
                                  self.cooldowns)
        for check, key in ((self.boss_only, "overlay_boss_only"), (self.pvp_only, "overlay_pvp_only")):
            if check.isEnabled():                 # the saved filters; the meter's answer names them too
                check.setChecked(ui.get(key) is True)
        for key, check in self.arena_checks.items():   # arena mode's, on by default; the other two off
            if check.isEnabled():
                check.setChecked(ui.get(key) is not False if key == "overlay_arena_mode" else ui.get(key) is True)
        for key, pick in self.arena_picks.items():
            if pick.isEnabled() and not pick.view().isVisible():
                pick.setCurrentIndex(max(0, pick.findData(self._arena_setting(key))))
        # Performance mode (Settings → App & data): the overlay reads the meter half as often and holds still between
        # readings, the rows' live tick off, the cooldown strip counting down half as often.
        self._perf = ui.get("performance_mode") is True
        self._interpolate = ui.get("overlay_dps_interpolate") is True and not self._perf
        if self._interpolate:
            self._tick_timer.start(theme.clamp_int(ui.get("overlay_interpolate_ms"), 50, 1000, 200))
        else:
            self._tick_timer.stop()
            self._shown_rates.clear()
        self._cooldown_timer.setInterval(500 if self._perf else 250)
        if self.view == "plan":                   # the plan's map a quarter as often in performance mode
            self._plan_timer.start(400 if self._perf else 100)
        # The overlay's frame rate (``overlay_show_fps``): its frames counted while it is on, never in performance
        # mode, where nothing drives a frame each turn of the screen.
        counting = ui.get("overlay_show_fps") is True and not self._perf
        if counting != self.fps.running():
            self.fps.run(counting)
            self.fps.set_parts([], self.text_look)   # nothing until its first second is counted
            self.fps.setVisible(counting)
        if ui.get("overlay_dps_graph") is not True:
            self._graph, self._player_hist = [], {}
        if ui.get("overlay_show_events") is not False and self._catalog is None and not self._catalog_asked \
                and self.requests is not None:
            self._catalog_asked = True            # the schedule the Timers page reads, once
            self.requests.get("catalog", "/static/event-schedules.json")
        self._apply_look()
        self.render_events()
        self.set_click_through(ui.get("overlay_click_through") is True)
        if first:                                 # where it was last put, if that is still on a monitor
            self.host.restore(ui)
        self.apply_meter(self.answer)

    def _place_parts(self, mode: str) -> None:
        """The card's padding and its parts' margins for its background (overlay.css ``#ov.ov-nm``): on the whole
        card 4 px above, 8 px at the sides and below within its edge, the top parts 2 px further in; with the top
        portion only or nothing behind, the card has no padding and the top parts their own 10 px (9 px for a chip
        of its own over the game), so the rows run a pixel from the overlay's edge."""
        whole, bare = mode == "card", mode == "none"
        self.box.setContentsMargins(*((9, 5, 9, 9) if whole else (1, 1, 1, 1)))
        self.connection.layout().setContentsMargins(*((9, 3, 9, 7) if bare else (10, 6, 10, 6)))
        self.lines_part.layout().setContentsMargins(*((2, 5, 2, 0) if whole else (9, 4, 9, 8) if bare else
                                                      (10, 7, 10, 0)))
        self.target_row.setContentsMargins(*((2, 6, 2, 4) if whole else (10, 7, 10, 9)))
        self.arena_card.box.setContentsMargins(*((2, 6, 2, 4) if whole else (10, 7, 10, 9)))
        self.dummy.setContentsMargins(*((2, 0, 2, 4) if whole else (9, 3, 9, 7) if bare else (10, 0, 10, 7)))

    def _content_width(self) -> int:
        """The room inside the card's padding, as wide as the rows."""
        margins = self.box.contentsMargins()
        return self.width() - margins.left() - margins.right()

    def set_click_through(self, on: bool) -> None:
        """Let clicks pass through to the game (the overlay's own setting): by the control on Windows, its buttons
        still pressed (``WindowHost``), else the whole window."""
        if on == self.click_through:
            return
        self.click_through = on
        if self.host.native:
            self.host.set_click_through(on)
            return
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        if visible:
            self.show()                          # changing a window flag hides the window until it is shown again

    def set_metric(self, metric: str) -> None:
        self.rate_metric = metric if metric in dict(METRICS) else "dps"
        words = dict(METRICS)[self.rate_metric]
        self.metric_chip.setText(words)
        self.metric_chip.setAccessibleName(words)
        self.metric_chip.setToolTip(f"{words} — click for the next: DPS, HPS, damage taken")
        self.metric_chip.updateGeometry()
        if self.store is not None:
            self.store.setValue("metric", self.rate_metric)
        self._shown_rates.clear()                 # the rows tick from the new metric's rates, not the old one's
        self.apply_meter(self.answer)

    def set_view(self, view: str) -> None:
        """The meter or the raid plan (the toolbar's tabs): the tab of the other view shows. Opened, the plan view
        asks the app for the saved plans again."""
        view = "plan" if view == "plan" else "meter"
        if view == self.view:
            return
        self.view = view
        for key, tab in self.tabs.items():
            tab.setVisible(key != view)
        if view == "plan":
            self._refresh_plans(True)
            self._plan_timer.start(400 if self._perf else 100)   # the map moves on, a quarter as often in performance mode
        else:
            self._plan_timer.stop()
        self.apply_meter(self.answer)

    def _refresh_plans(self, now: bool = False) -> None:
        """Ask the app for the saved plans (``/api/plans/saved``): at once, or at most every 15 s while the view is
        open."""
        if self.requests is None or (not now and time.monotonic() - self._plans_at < 15):
            return
        self._plans_at = time.monotonic()
        self.requests.get("plans", "/api/plans/saved")

    def _show_plan(self) -> None:
        """The raid plan view (``renderPlan``): the plan's map at its moment in the rows' place, the rest put away
        but the toolbar, the events strip and the options; with no plan saved, where to save one."""
        if self.view != "plan":
            return
        for part in (self.metric_chip, self.ping, self.lines, self.identity, self.target_card, self.arena_card,
                     self.contribution, self.dummy, self.fps, self.graph, self.cooldowns, self.clock, self.connection,
                     self.warning, self.panel_scroll):
            part.hide()
        for row in self.rows:
            row.hide()
        self._show_arena(None, [], lambda _player: False, self.rate_metric)
        self._refresh_plans()
        plan, moment, live, length = plan_view(self.plans, self.answer, self.ui.get("overlay_plan_autoplay") is not False,
                                               time.monotonic() - self._plan_start)
        if plan is None:
            self.plan_map.hide()
            self.empty.setText("No saved plan yet. Plans you save in the app's Raid Planner show here.")
            self.empty.show()
            self.status_text = ""
        else:
            self.empty.hide()
            name = (plan.get("meta") or {}).get("name") or "plan"
            self.status_text = (f"{'▶ live · ' if live else ''}{name} · {theme.fixed(moment, 0)}/"
                                f"{theme.fixed(length, 0)}s")
            self.plan_map.set_moment(plan, moment)
            self.plan_map.setToolTip(self.status_text)
            self.plan_map.show()
        self.content_box.setContentsMargins(0, 8, 0, 2)   # ``.ovarena { margin: 2px auto }``
        self._sync_tools()
        self._relayout()

    def next_metric(self) -> None:
        """A click on the metric chip: the next metric, DPS, HPS, damage taken and round again."""
        keys = [key for key, _words in METRICS]
        self.set_metric(keys[(keys.index(self.rate_metric) + 1) % len(keys)])

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
            self.unavailable, self.refresh_error, self.last_success = False, "", time.time()
            self.apply_meter(answer)

    def _meter_failed(self, why: str) -> None:
        """The app did not answer: the last reading stays, with why and since when over it (``#ovconnection``)."""
        if not self.locked:
            self.unavailable, self.refresh_error = True, str(why or "No answer")[:512]
            self.apply_meter(self.answer)

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
        if self.view == "plan":                   # the reading plays a bound plan with the fight
            self._show_plan()
            return
        self.plan_map.hide()
        self.fps.setVisible(self.fps.running())
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
        total_amount = sum(_amount(p, metric) for p in players) or 1.0
        filtered = filter_label(answer)
        # Only in combat (the web overlay's ``collapse``): between fights the overlay keeps its toolbar alone.
        idle = ui.get("overlay_only_in_combat") is True and (
            not running or over or (paused and snap.get("boss_alive") is not True))
        shown = [] if idle or over else players[:limit]   # a fight that is over says it is ready for the next
        top = max([_rate(p, metric) for p in everyone] + [1.0])   # the rate a whole bar stands for
        # Arena mode (``arenaOf``): in a PvP match its card and its rows in the target card's and the rows' places.
        arena = None if idle else A.arena_of(snap, cleared, self._arena_setting("overlay_arena_mode"))
        local = str((snap.get("identity_status") or {}).get("local_name") or "").casefold()
        is_me = lambda player: bool(local) and str(player.get("name") or "").casefold() == local   # noqa: E731
        drawn = self._show_arena(arena, everyone, is_me, metric)
        if arena is not None:
            shown = []
        duration = snap.get("duration") if metric == "dps" else snap.get("recorded_duration")
        self.status_text = self._status(answer, snap, everyone, metric, filtered, duration, cleared, idle)
        self.copy_text = leaderboard_text(snap, players, metric, filtered, lambda p: self._names(p)[0])
        self._show_connection()
        self._show_counters(snap, idle)
        target = snap.get("current_target")
        if (idle or over or cleared or arena is not None or not isinstance(target, dict) or target.get("is_player")
                or not target.get("contributors")):
            target = None                         # the web overlay's target panel needs damage dealt to it
        self._show_target(target)
        self._show_arena_card(arena, everyone, is_me)
        self._show_dummy(snap, idle or over or cleared, metric)
        warning = snap.get("warning") if not idle and not over and everyone and arena is None else None
        self.warning.setText(str(warning or ""))
        self.warning.setVisible(bool(warning))
        empty = "" if idle or shown or drawn else empty_text(answer, everyone, metric, cleared, filtered)
        self.empty.setText(empty)
        self.empty.setVisible(bool(empty))
        self.content_box.setContentsMargins(0, 6, 0, 4 if shown else 0)   # the last row's own 4 px under it
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
        self._show_clock(answer, snap, everyone, players, metric, filtered, duration,
                         idle or over or cleared or not players, arena, is_me)
        self._show_contribution(snap, idle or over or cleared or arena is not None, metric)
        text, fine = identity_line(snap, everyone, players, players, repeated,
                                   ui.get("overlay_show_combat_power") is not False)
        self.identity.setText(text)
        self.identity.setVisible(bool(text) and not fine and not idle)
        self._show_ping(snap.get("ping"), idle)
        self.metric_chip.setVisible(not idle)     # ``#ovmetrics`` goes with the rest between fights
        identity = snap.get("identity_status") or {}
        local_cp = identity.get("local_combat_power")
        # Live-ticking DPS between readings (overlay_dps_interpolate): the rows ease from the rates they show.
        self._render_at, self._projecting, self._cur_max = time.monotonic(), running and not paused, top
        ticking = self._interpolate and not self.locked
        ranks = ui.get("overlay_show_community_rank") is True
        while len(self.rows) < len(shown):
            row = PlayerRow(self.card)
            row.setFixedHeight(self._row_height())
            row.set_text_look(self.text_look)
            row.moving = not self._still
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
            cls = str(player.get("class") or "")
            row.set_player(name, cls, f"{rate_text(showing)}/s",
                           f"{theme.fixed(100 * _amount(player, metric) / total_amount, 1)}%", showing / top,
                           mine, index, look.show_deaths and player.get("dead") is True,
                           theme.sfmt(cp) if cp > 0 else "", look, key, key == self.detail_key,
                           f"#{player.get('id')}" if look.name_mode == "name" and shared else "",
                           str(rank.get("text") or "") if ranks else "", self.pictures.emblem(cls),
                           self.card.mode == "card")
            row.setToolTip(f"{player.get('name')} · Actor {player.get('key') or player.get('id')}"
                           f"{' · Includes linked pets' if player.get('includes_pets') else ''}"
                           f" · Click for this player's details")
            row.show()
        self._show_panel(snap, everyone, idle or over or cleared)
        self._sync_tools()
        if self._meter_poller is not None:        # twice a second in a fight, once a second out of one
            self._meter_poller.set_interval((500 if running else 1000) * (2 if self._perf else 1))
        self._relayout()
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
            row.set_live(f"{rate_text(shown)}/s", shown / self._cur_max)
        for key in [key for key in self._shown_rates if key not in seen]:
            del self._shown_rates[key]

    def _show_target(self, target) -> None:
        """The target card (overlay.js ``targetCard``): the boss's portrait (or the target mark), its name with the
        others struck in the same instant, its HP in damage units and its share to a tenth when the HP is on, the HP,
        time-to-kill and break bars, and under them the time to kill with the enrage timer and the break gauge, each
        in its own look."""
        ui, tl = self.ui, self.text_look
        if ui.get("overlay_show_target", True) is False or not isinstance(target, dict) or not target.get("name"):
            self.target_card.hide()
            self.target_text = ""
            return
        size = tl.size("target", self._px())     # the card's own size: 12 px, the overlay's and the target's own
        weight = tl.weight_of("target", 400)
        self.portrait.set_picture(self.pictures.portrait(target.get("mob_code")))
        also = [str(name) for name in (target.get("also_targets") or [])]
        tip = hp_tip(target)
        hp = target.get("hp_pct")
        known = ui.get("overlay_show_enemy_hp") is True and isinstance(hp, (int, float)) and not isinstance(hp, bool)
        pct = max(0.0, min(100.0, hp * 100)) if known else 0.0
        nums = ""
        if known and target.get("effective_max_hp") is not None and target.get("effective_current_hp") is not None:
            nums = f"{theme.sfmt(target['effective_current_hp'])} / {theme.sfmt(target['effective_max_hp'])}"
        # ``@container (max-width: 24em)`` on the card's content (the overlay's less 2 × 11 px): they step aside.
        shown_nums = bool(nums) and self.width() - 22 > 24 * size
        self.target_nums.setText(nums)
        self.target_nums.setToolTip(tip)
        self.target_nums.setVisible(shown_nums)
        self.target_hp.setText(f"{theme.fixed(pct, 1)}%")
        self.target_hp.setToolTip(tip)
        self.target_hp.setVisible(known)
        # The name and the others struck: the others' names give way first, then the name; the count is never cut.
        name_font = tl.font("target", size * 1.12, 700)
        also_font = tl.font("also", size * 0.92, 600)
        name, count = str(target["name"]), f"+{len(also)}" if also else ""
        others = f"({', '.join(also)})" if also else ""
        right = sum(QFontMetricsF(label.font()).horizontalAdvance(label.text()) + 8
                    for label in (self.target_nums, self.target_hp) if not label.isHidden())
        room = self.width() - 18 - 34 - 8 - right
        named, alsoed = QFontMetricsF(name_font), QFontMetricsF(also_font)
        counted = alsoed.horizontalAdvance(count) + 5 if count else 0.0
        if others and named.horizontalAdvance(name) + counted + 5 + alsoed.horizontalAdvance(others) > room:
            others = alsoed.elidedText(others, Qt.ElideRight, room - named.horizontalAdvance(name) - counted - 5)
        if not others and named.horizontalAdvance(name) + counted > room:
            name = named.elidedText(name, Qt.ElideRight, max(0.0, room - counted))
        rich = tl.span("target", html.escape(name), "#f4f6f8", size * 1.12, 700)
        for part in (count, others):
            if part:
                rich += "&nbsp;" + tl.span("also", html.escape(part), "#c9a86a", size * 0.92, 600)
        self.target.setText(rich)
        self.target.setToolTip(
            "Most-hit enemy this encounter" + (f" (and {len(also)} more struck in the same instant)" if also else "")
            + ", its remaining HP and time-to-kill from its observed HP-decline rate (all damage sources, so it "
              "reflects how fast it is really dying — not just your party's DPS), and each contributor's DPS to it"
            + (f"\nAlso being hit right now: {', '.join(also)}" if also else ""))   # the count's own title
        # The time to kill, the enrage timer and the break, each as the web overlay's spans have them.
        line, plain, tips = [], [], []
        show_ttk = ui.get("overlay_show_ttk") is True
        small = size * 0.86
        if show_ttk:
            ttk = target.get("ttk")
            if isinstance(ttk, (int, float)) and not isinstance(ttk, bool) and math.isfinite(ttk):
                text = f"TTK {fmt_ttk(ttk)}"
                line.append(tl.span("ttk", text.replace(" ", "&nbsp;"), "#e3ad7f", small, 600))
                plain.append(text)
            enrage = target.get("enrage")
            if isinstance(enrage, dict):
                late = enrage.get("enraged") or enrage.get("before_kill")
                text = "ENRAGED" if enrage.get("enraged") else f"Enrage {fmt_ttk(enrage.get('enrage_in'))}"
                shade = QColor("#ff6b6b" if late else tl.colour("ttk", "#e3ad7f"))
                if not late:
                    shade.setAlphaF(0.85)
                line.append(f'<span style="color:rgba({shade.red()},{shade.green()},{shade.blue()},{shade.alphaF():.2f});'
                            f' font-weight:{700 if late else weight}">{text.replace(" ", "&nbsp;")}</span>')
                plain.append(text)
                tips.append(f"Past this boss's {fmt_ttk(enrage.get('enrage_s'))} enrage timer: it now attacks faster "
                            f"and harder" if enrage.get("enraged") else
                            f"This boss enrages {fmt_ttk(enrage.get('enrage_s'))} after the pull"
                            f"{' (seen in recorded fights)' if enrage.get('measured') else ''}"
                            f"{'; at this pace the kill takes longer than that' if enrage.get('before_kill') else ''}")
        gauge = target.get("break_gauge") if ui.get("overlay_show_break_gauge") is True else None
        gauge_pct = None
        if isinstance(gauge, dict):
            gauge_pct = max(0.0, min(100.0, _num(gauge.get("pct"))))
            broken = gauge_pct <= 5
            text = "BROKEN" if broken else f"Break {theme.js_round(gauge_pct)}%"
            line.append(f'<span style="color:{"#f0c36a" if broken else "#e3b35a"}; font-weight:700'
                        f'{"; letter-spacing:0.4px" if broken else ""}">{text.replace(" ", "&nbsp;")}</span>')
            plain.append(text)
            tips.append("The break gauge is empty: the enemy is broken (staggered) and takes more damage until it "
                        "refills" if broken else "Break gauge left before this enemy breaks (staggers); skills that "
                        "deal Stagger Gauge Damage drain it")
        self.target_line.setText("&nbsp;&nbsp; ".join(line))
        self.target_line.setToolTip("\n".join(tips))
        self.target_line.setVisible(bool(line))
        self.target_text = "  ·  ".join(
            [str(target["name"]) + (f" {count} {'(' + ', '.join(also) + ')'}" if also else "")]
            + ([nums] if shown_nums else []) + ([f"{theme.fixed(pct, 1)}%"] if known else []) + plain)
        self.hp.setVisible(known)
        if known:
            self.hp.set_fraction(pct / 100)
        # How far through the whole kill the fight is by time (``ttk_fraction``), with the time to kill on.
        fraction = target.get("ttk_fraction")
        timed = (show_ttk and isinstance(fraction, (int, float)) and not isinstance(fraction, bool)
                 and math.isfinite(fraction))
        self.ttk_bar.setVisible(timed)
        if timed:
            self.ttk_bar.set_fraction(fraction)
        self.gauge.setVisible(gauge_pct is not None)
        if gauge_pct is not None:
            self.gauge.set_fraction(gauge_pct / 100)
        self.target_bars.setVisible(known or timed or gauge_pct is not None)
        self.target_card.show()

    def _show_counters(self, snap: dict, hidden: bool) -> None:
        """The counters across the top (``#ovlines``): your Odyle Energy, Shugo Keys and Nightmare tickets and the
        dungeon's weekly runs, each after its icon, in the ping's colour and font. In full words where they all fit
        on one line (``compactLines``: their widths and 10 px each), else in their short form, larger: the regular
        count and the bonus in teal (``ov-lines-icons``). Each one's tooltip says it in full and what it is."""
        items = [] if hidden else counter_items(snap)
        if self.card.mode == "top":               # 4 px under the counters when there are any (``:has(...)``)
            self.lines_part.layout().setContentsMargins(10, 7, 10, 4 if items else 0)
        if not items:
            self.lines.hide()
            return
        tl = self.text_look
        families, colour = tl.families("ping"), tl.colour("ping", "#e9edf1")

        def parts(short: bool) -> list[Part]:
            size = tl.size("ping", (12 if short else 10) * tl.scale)
            made = []
            for key, full, regular, bonus in items:
                if short:
                    runs = [(f"{regular:,}", sized_font(families, size, 700), colour)]
                    if bonus:
                        runs.append((f"(+{bonus:,})", sized_font(families, size, 600), TEAL))
                else:
                    runs = [(full, sized_font(families, size, 600), colour)]
                if key == "odyle":                # the game's recharge item, 1.4em, where the app has its art
                    picture = self.pictures.item(ODYLE_ICON)
                    mark = picture_mark(picture) if picture is not None else None
                    side = 1.4 * size
                else:                             # a key, a ticket, a calendar: 1.2em, in the counters' gold
                    mark, side = icon_mark(COUNTER_ICONS[key], "#e8cf8e"), 1.2 * size
                made.append(Part(runs, size * 1.5, mark, QSizeF(side, side) if mark is not None else None,
                                 f"{full}\n{COUNTER_TIPS[key]}"))
            return made

        full = parts(False)
        margins = self.lines_part.layout().contentsMargins()
        room = self._content_width() - margins.left() - margins.right()
        need = sum(part.measure().width() for part in full) + 10 * len(full)
        shadow = CHIP_SHADOW if self.card.mode == "none" else None   # over the game with nothing behind it
        if shadow != self.lines.shadow:
            self.lines.shadow = shadow
            self.lines.update()
        self.lines.set_parts(full if need <= room + 1 else parts(True), tl)
        self.lines.show()

    def _status(self, answer: dict, snap: dict, everyone: list, metric: str, filtered: str, duration, cleared: bool,
                idle: bool) -> str:
        """The fight's status as the web overlay words it (``#ovstatus``), which the compact layout folds away into
        the clock's tooltip."""
        noun = {"hps": "HPS", "dtps": "Damage taken/s"}.get(metric, "DPS")
        running = answer.get("running") is True
        if cleared:
            status = "New fight · waiting for combat"
        else:
            pause = "Paused DPS · " if snap.get("paused") is True and metric == "dps" else ""
            what = snap.get("boss") or ("recording" if running else "idle")
            status = (f"Latest combat · {pause}{what} · {theme.fixed(_num(duration), 0)}s · "
                      f"{theme.kfmt(sum(_rate(p, metric) for p in everyone))} {noun}")
            if filtered and metric == "dps":
                status += f" · {filtered}"
        backlog = snap.get("decode_backlog")
        if isinstance(backlog, dict) and backlog.get("catching_up"):
            status += f" · ⏳ catching up ({_text(backlog.get('queue_depth'))})"
        if answer.get("error"):
            status = f"Capture stopped: {answer['error']}"
        if self.unavailable:
            status = "Refresh failed · retrying"
        if idle:
            status = "Idle · waiting for combat" if running else "Idle"
        return status

    def _show_connection(self) -> None:
        """While the app does not answer (``#ovconnection``): why, how long since the last reading, and Retry."""
        if self.unavailable:
            since = (f"{int(time.time() - self.last_success)}s since last refresh. "
                     if self.last_success is not None else "")
            self.reason.setText(f"{self.refresh_error} · {since}Last readings retained; capture status unknown.")
        self.connection.setVisible(self.unavailable)

    def _show_dummy(self, snap: dict, hidden: bool, metric: str) -> None:
        """The training-dummy parse under the target (``#ovdummy``, the DPS view only), green once its window is
        reached."""
        dummy, text, rich = snap.get("dummy_parse"), "", ""
        if (not hidden and metric == "dps" and isinstance(dummy, dict)
                and self.ui.get("meter_show_dummy_parse", True) is not False):
            you = f" · You {theme.kfmt(dummy['your_dps'])}/s" if dummy.get("your_dps") is not None else ""
            body = (f" {_round(dummy.get('duration'))}s / {_round(dummy.get('window_seconds'))}s"
                    f"{' ✓' if dummy.get('window_reached') else ''}{you} · Total {theme.kfmt(dummy.get('target_dps'))}/s")
            text = "Dummy parse" + body
            rich = self.text_look.inline("label", "Dummy parse", 11, "#e8cf8e", 600) + html.escape(body)
            ok = dummy.get("window_reached") is True
            if self.dummy.property("ok") != ok:
                self.dummy.setProperty("ok", ok)
                self.dummy.style().unpolish(self.dummy)
                self.dummy.style().polish(self.dummy)
        self.dummy_text = text
        self.dummy.setText(rich)
        self.dummy.setVisible(bool(text))

    def _show_clock(self, answer: dict, snap: dict, everyone: list, players: list, metric: str, filtered: str,
                    duration, hidden: bool, arena: dict | None = None, is_me=None) -> None:
        """The fight's clock (``#ovclock``): a mark green while the fight runs and amber while the DPS clock is
        paused, the fight's time, notes (paused, the damage filter, catching up, the capture stopped) and the
        party's total for the metric shown; in arena mode the match, with its score or the party's total, in the
        total's place and no filter. Its tooltip is the fight's status."""
        if hidden:
            self.clock.hide()
            return
        tl, scale = self.text_look, self.text_look.scale
        running, paused = answer.get("running") is True, snap.get("paused") is True
        live = running and not paused
        families = tl.families()
        note, line = sized_font(families, 11 * scale, 600), 11 * scale * 1.35
        seconds = max(0, math.floor(_num(duration)))
        parts = [Part(mark=clock_mark("#5ee04a" if live else "#e3b35a" if paused else "#6b7380", live),
                      size=QSizeF(3, 15)),
                 Part([(f"{seconds // 60:02d}:{seconds % 60:02d}", sized_font(MONOSPACE, 13 * scale, 700, 0.5),
                        "#e9edf1")], 13 * scale * 1.3)]
        if paused and metric == "dps":
            parts.append(Part([("Paused", note, "#e3b35a")], line))
        if metric == "dps" and filtered and arena is None:
            short = {"Boss damage only": "Boss only", "Player damage only": "PvP only"}.get(filtered, "Bosses + PvP")
            parts.append(Part([(short, note, "#8fd0a0")], line, tip=filtered))
        backlog = snap.get("decode_backlog")
        if isinstance(backlog, dict) and backlog.get("catching_up"):
            parts.append(Part([(f"catching up ({_text(backlog.get('queue_depth'))})", note, "#e3b35a")], line))
        if answer.get("error"):
            parts.append(Part([("Capture stopped", note, "#ff8585")], line, tip=str(answer["error"])))
        strong = sized_font(families, 11 * scale, 800)
        if arena is not None:                     # ``A2Arena.clock``
            tail = A.clock_tail(arena, everyone, is_me, metric, self._arena_setting("overlay_arena_all3"))
            parts.append(Part([(text, strong if bold else note, TEAL if bold else "#9aa3b5") for text, bold in tail],
                              line))
        else:
            short = {"hps": "HPS", "dtps": "DTPS"}.get(metric, "DPS")
            parts.append(Part([(f"Party {short} ", note, "#9aa3b5"),
                               (theme.kfmt(sum(_rate(p, metric) for p in everyone)), strong, TEAL)], line))
        self.clock.set_parts(parts, tl)
        self.clock.setToolTip(self.status_text)
        self.clock.setAccessibleName("Fight time")
        self.clock.show()

    def _arena_look(self) -> RowLook:
        """The rows' look for arena mode's rows (``A2Arena``'s ``row``): no rank, swatch, class-coloured name, edge on
        your row or effects; your row has its green dot."""
        look = copy.copy(self.look)
        look.rank_numbers = look.class_swatch = look.class_names = look.highlight_me = False
        look.me_cosmetic = look.top_cosmetic = None
        return look

    def _show_arena_card(self, arena: dict | None, everyone: list, is_me) -> None:
        """Arena mode's card in the target card's place (``A2Arena.card``), behind the target's setting."""
        card = self.arena_card
        them = A.foe(arena) if arena is not None else None
        me = A.you(arena, everyone, is_me) if arena is not None else None
        if arena is None or self.ui.get("overlay_show_target") is False or (them is None and me is None):
            card.hide()
            return
        shadow = CHIP_SHADOW if self.card.mode == "none" else None
        hp_colour = QColor(hex_colour(self.ui.get("overlay_hp_color")) or "#e05a5a")
        if self._arena_setting("overlay_arena_layout") == "versus" and me is not None and them is not None:
            card.set_versus(arena, me, them, (self.pictures.emblem(me.get("class")), self.pictures.emblem(them.get("class"))),
                            self.text_look, self._px(), hp_colour, shadow)
        elif them is not None:
            card.set_foe(arena, them, self.pictures.emblem(them.get("class")), self.text_look, self._px(), hp_colour,
                         shadow)
        else:
            card.hide()
            return
        card.setToolTip("Your opponent: the game's arena roster (name, class, server, level, arena rating), their HP, "
                        "and their combat power from the official character service" if A.solo(arena) else
                        "Your current target among the enemy players: their HP, combat power where known, and their "
                        "share of the damage you took")
        card.show()

    def _show_arena(self, arena: dict | None, everyone: list, is_me, metric: str) -> bool:
        """Arena mode's rows in the meter's place (``A2Arena.body``), each item drawn by a widget of its kind: a
        section's head, a row, a row of three figures, the compact table's head or row, a tug of war; the widgets kept
        for the next reading. Answers whether any is drawn."""
        items = (A.body(arena, everyone, is_me, self._arena_setting("overlay_arena_layout"), metric,
                        self._arena_setting("overlay_arena_all3")) if arena is not None else [])
        tl, look, base = self.text_look, self._arena_look(), QFont(self.font())
        whole, height = self.card.mode == "card", self._row_height()
        used: dict[str, int] = {}
        order: list[QWidget] = []
        for position, item in enumerate(items):
            kind = item[0]
            pool_key = "arow" if kind in ("tri", "table") else kind
            pool = self._arena_pool.setdefault(pool_key, [])
            index = used.get(pool_key, 0)
            used[pool_key] = index + 1
            if index >= len(pool):
                made = {"section": Section, "head": TableHead, "row": PlayerRow, "arow": ArenaRow, "tug": Tug}[pool_key]
                pool.append(made(self.content))
            widget = pool[index]
            if kind == "section":
                widget.set_runs(item[1], tl, base)
            elif kind == "head":
                widget.set_head(item[1], tl, base)
            elif kind == "tug":
                _kind, label, a, b, colour_a, colour_b = item
                widget.setFixedHeight(height)
                widget.set_tug(label, a, b, colour_a, colour_b, tl, base, whole)
            else:
                fighter = item[1]
                cls = str(fighter.get("class") or "")
                if widget.text_look is not tl:
                    widget.set_text_look(tl)
                widget.setFixedHeight(height)
                mine, dead = bool(fighter.get("self")), bool(fighter.get("dead"))
                emblem = self.pictures.emblem(cls)
                if kind == "row":
                    _kind, _f, value, total, most, label, cp = item
                    chip = (theme.sfmt(fighter["combat_power"]) if cp and fighter.get("combat_power")
                            and self.look.show_cp else "")
                    widget.set_player(label or A.name_of(fighter), cls, f"{rate_text(value)}/s", A.share(value, total),
                                      value / most if most > 0 else 0.0, mine, position, dead, chip, look, "", False,
                                      "", "", emblem, whole)
                else:
                    figures = tuple(A.num(fighter.get(key)) for key, _words, _colour in A.METRICS)
                    mosts = (item[2], 0.0, 0.0) if kind == "tri" else tuple(item[2])
                    fill = figures[0] / mosts[0] if kind == "tri" and mosts[0] > 0 else 0.0
                    widget.set_player(A.name_of(fighter), cls, "", "", fill, mine, position, dead, "", look, "", False,
                                      "", "", emblem, whole)
                    widget.set_figures(kind, figures, mosts)
            order.append(widget)
        if order != self._arena_order:            # what is drawn changed: laid out again, 4 px under each row
            while self.arena_box.count():
                self.arena_box.takeAt(0)
            for widget in order:
                self.arena_box.addWidget(widget)
                if isinstance(widget, (PlayerRow, Tug)):
                    self.arena_box.addSpacing(4)
            self._arena_order = order
        for pool in self._arena_pool.values():
            for widget in pool:
                widget.setVisible(any(widget is shown for shown in order))
        return bool(order)

    def _show_contribution(self, snap: dict, hidden: bool, metric: str) -> None:
        """Your share of the fight's damage (``#ovcontribution``), a chip of its own after the clock (DPS only)."""
        contribution = snap.get("contribution")
        show = (not hidden and metric == "dps" and isinstance(contribution, dict)
                and _num(contribution.get("damage")) > 0 and self.ui.get("overlay_show_contribution") is not False)
        self.contribution_text = (f"Your contribution: {_round(_num(contribution.get('share')) * 100)}% · "
                                  f"{theme.kfmt(contribution.get('damage'))} ({theme.kfmt(contribution.get('dps'))}/s)"
                                  if show else "")
        if show:
            self.contribution.set_parts([Part([(self.contribution_text, sized_font(self.text_look.families(), 10.5, 400),
                                                "#88d1d2")], 10.5 * 1.35)], self.text_look)
        self.contribution.setVisible(show)

    def _show_ping(self, ping, hidden: bool) -> None:
        """The capture's round trip (``#ovping``): a signal mark and the current one in milliseconds, the average
        and the range in its tooltip, in the ping's own look."""
        tl = self.text_look
        current, whole = ping_texts(ping)
        size = tl.size("ping", 12 * tl.scale)
        families = tl.families("ping")
        colour = tl.colour("ping", "#eef1f4")
        self.ping.set_parts([Part(mark=icon_mark("signal", "#4ea8ef"), size=QSizeF(1.15 * size, size)),
                             Part([(current, sized_font(families, size, 800), colour),
                                   ("ms", sized_font(families, size, 600), colour)], size * 1.35)], tl)
        self.ping.setToolTip(f"{whole} — Passive TCP RTT for this recording connection; average/minimum/maximum "
                             f"across the capture")
        self.ping.setVisible(not hidden)

    def _show_fps(self) -> None:
        """The frame rate counted over the last second (``#ovfps``): its number, then "FPS"."""
        rate = self.fps.rate
        if rate is None:
            return
        tl, scale = self.text_look, self.text_look.scale
        families = tl.families()
        width = self.fps.sizeHint().width()
        self.fps.set_parts([Part([(str(rate), sized_font(families, 12 * scale, 700), "#eef1f4"),
                                  (" FPS", sized_font(families, 11 * scale, 700), "#4ea8ef")], 12 * scale * 1.5)], tl)
        self.fps.setToolTip("The overlay's own frames each second (the game's can't be read from the capture)")
        if self.fps.sizeHint().width() != width:  # its first count, or a number of another length
            self._relayout()

    def _relayout(self) -> None:
        """Lay the card out for what it now holds, then size the window to it. A row, a line or the panel that came
        or went asks for a layout only at the next turn of the event loop, and a part with its own layout (the rows'
        part, the chips, the toolbar) tells the card its new size only then: sized before it, the window kept its old
        height until then, and its rows lay on top of each other. So each part's own layout is laid out first, the
        innermost first, then the card's."""
        for widget in reversed(self.card.findChildren(QWidget)):
            layout = widget.layout()
            if layout is not None and not widget.isHidden():
                layout.activate()
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

    # ------------------------------------------------------------------ the events strip
    def render_events(self) -> None:
        """The strip of the next events (overlay.js ``renderEvents``): the windows of the region picked on the Timers
        page running or starting within 15 minutes, and the field bosses seen killed, three at most. It stays up
        between fights. A new one entering it chimes once, with the chime on; the first reading does not."""
        ui = self.ui
        if ui.get("overlay_show_events") is False:
            self._hide_events()
            return
        snap = self.answer.get("snapshot") if isinstance(self.answer.get("snapshot"), dict) else {}
        region = ui.get("event_region") if isinstance(ui.get("event_region"), str) else ""
        group = ui.get("event_group") if isinstance(ui.get("event_group"), str) else ""
        now, bosses = self.events_clock(), ui.get("overlay_show_field_bosses") is not False
        if not region and not schedule.observed_kills(snap.get("field_bosses"), now, bosses):
            self._hide_events()                   # no region picked yet and nothing observed
            return
        shown = schedule.strip(self._catalog, region, group, snap.get("field_bosses"), now, bosses)
        keys = {f"{event['id']}:{'active' if event['active'] else 'soon'}" for event in shown}
        if not self._primed:
            self._announced, self._primed = set(keys), True
        else:
            fresh = keys - self._announced
            self._announced = (self._announced & keys) | keys   # one that left can chime when it comes again
            if fresh and ui.get("overlay_events_sound") is True:
                QApplication.beep()               # the system's alert: Qt's bundled modules have no audio
        if not shown:
            self._show_events(False)
            return
        # One line, as the web overlay's (cut with an ellipsis): the events that fit whole, then "…".
        tl, px = self.text_look, self._px()
        bold = QFont(self.events.font())
        bold.setBold(True)                        # measured bold throughout, so a fit is never too tight
        room, metrics = max(40, self._content_width() - 18), QFontMetricsF(bold)   # a chip's whole line
        lead = QFontMetricsF(tl.font("label", px, 700)).horizontalAdvance("Events ")
        count = len(shown)
        while count > 1 and lead + metrics.horizontalAdvance(
                " · ".join(event["text"] for event in shown[:count]) + (" …" if count < len(shown) else "")
        ) > room:
            count -= 1
        label = tl.inline("label", "Events", px, "#e8cf8e", 600)
        self.events.setText(schedule.strip_html(shown[:count], label) + (" …" if count < len(shown) else ""))
        self.events.setToolTip("\n".join(event["tip"] for event in shown))
        self._show_events(True)

    def _hide_events(self) -> None:
        self._primed = False
        self._announced.clear()
        self._show_events(False)

    def _show_events(self, on: bool) -> None:
        if on == self.events.isHidden():          # the strip came or went: the window takes its height
            self.events.setVisible(on)
            self._relayout()

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
        columns = max(1, (self._content_width() - 20 + 4) // 96)   # the panel's margins; 92 px tiles
        self.panel.set_reading(panel_reading(snap, player, self.detail_buffs, self.detail_extra, name, mine), columns)
        graphed = self.ui.get("overlay_dps_graph") is True and player is not None
        self.panel.set_spark(self._player_hist.get(self.detail_key, []) if graphed else [],
                             theme.class_color(player.get("class")) if player is not None else None)
        self.panel_scroll.show()
        self.panel.layout().activate()            # its tiles and lines as they now stand (see _relayout)
        width = self._content_width()
        content = (self.panel.heightForWidth(width) if self.panel.hasHeightForWidth()
                   else self.panel.sizeHint().height()) + 6   # and its margins, 2 px above and 4 below
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
    def _state(button: IconButton, state: str) -> None:
        """How a press went (``data-state``): "ok" green, "err" red, "" its own colour again."""
        button.state = state
        button.update()

    def _flash(self, key: str, text: str, state: str, ms: int, then) -> None:
        """A button says how its press went for a moment, in its colour (and in its words, ``Copied``, ``New ✓``,
        ``Error``, for a screen reader), then ``then`` runs."""
        button = self.tools[key]
        button.setText(text)
        button.setAccessibleName(text)
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
        words = "Stopping…" if finalizing else "Stop" if running else "Start"
        button.setText(words)
        button.setAccessibleName(words)
        button.setEnabled(not finalizing)
        button.setToolTip("Stop capturing combat (same as Stop in the app)" if running else
                          "Start capturing combat (same as Start in the app)")
        on = running or finalizing                # ``#ovcapture.on``: the stop square in red, else the play in green
        button.icon_name, button.tone = ("stop", RED) if on else ("play", GREEN)
        self._state(button, "")

    def _poll_meter(self) -> None:
        if self._meter_poller is not None:
            self._meter_poller.poll()

    def toggle_lock(self) -> None:
        """Lock: the overlay stays where it is and holds its reading for a screenshot; a second press resumes."""
        self.locked = not self.locked
        button = self.tools["lock"]
        button.setText("Unlock" if self.locked else "Lock")
        button.setAccessibleName(button.text())
        button.tone = GREEN if self.locked else None   # ``#ovlock.on``
        button.update()
        self.card.locked = self.locked            # and the card's dashed green edge
        self.card.update()
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
        self.tools["copy"].setAccessibleName("Copy")
        self._state(self.tools["copy"], "")

    def toggle_options(self) -> None:
        self.options.setVisible(self.options.isHidden())   # isHidden, not isVisible: the window may be hidden
        button, open_ = self.tools["options"], not self.options.isHidden()
        button.setChecked(open_)
        button.tone = TEAL if open_ else None     # ``#ovsettings[aria-expanded="true"]``
        button.update()
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
        button.setAccessibleName(button.text())
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

    def _arena_setting(self, key: str):
        """An arena setting as the web overlay reads it: arena mode on unless turned off, all three for the party and
        the player cards window off unless on, the compact layout and the list unless another is named."""
        value = self.ui.get(key)
        if key == "overlay_arena_mode":
            return value is not False
        if key == "overlay_arena_layout":
            return value if value in A.LAYOUTS else "compact"
        if key == "overlay_players_style":
            return "grid" if value == "grid" else "list"
        return value is True

    def _arena_clicked(self, key: str, value) -> None:
        """An arena option changed: saved as a setting (the app opens or closes the player cards window with it), the
        overlay drawn by it as soon as the app has it."""
        if self.requests is None:
            self.ui = {**self.ui, key: value}
            self.apply_meter(self.answer)
            return
        (self.arena_checks.get(key) or self.arena_picks[key]).setEnabled(False)
        self.requests.post("arena:" + key, "/api/ui", {key: value})

    def _say(self, message: str) -> None:
        self.message.setText(message)
        self.message.setVisible(bool(message))

    def _replied(self, name: str, answer) -> None:
        """A toolbar request's answer (``Requests``), on the interface's thread."""
        if name == "catalog":
            if isinstance(answer, dict) and answer.get("version") == 1:
                self._catalog = answer
                self.render_events()
            return
        if name == "background":
            self._background_read(answer)
            return
        if name == "plans":
            if isinstance(answer, dict) and isinstance(answer.get("plans"), dict):
                self.plans = answer["plans"]
                self._show_plan()
            return
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
        elif name.startswith("arena:"):
            key = name[len("arena:"):]
            control = self.arena_checks.get(key) or self.arena_picks[key]
            control.setEnabled(True)
            value = control.isChecked() if isinstance(control, QCheckBox) else control.currentData()
            self.ui = {**self.ui, key: value}
            self._say("")
            self.apply_meter(self.answer)

    def _failed(self, name: str, why: str) -> None:
        if name == "catalog":
            self._catalog_asked = False           # asked again with the next settings
            return
        if name == "background":
            self._background_lost()
            return
        if name == "plans":                       # asked again within 15 s, while the view is open
            return
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
        elif name.startswith("arena:"):
            key = name[len("arena:"):]
            control = self.arena_checks.get(key) or self.arena_picks[key]
            control.setEnabled(True)
            if isinstance(control, QCheckBox):    # back as it was
                control.setChecked(not control.isChecked())
            else:
                control.setCurrentIndex(max(0, control.findData(self._arena_setting(key))))
            self._say("Could not change the arena setting")

    def _split_back(self) -> None:
        button = self.tools["split"]
        button.setText("New")
        button.setAccessibleName("New")
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
        if self._bg_wanted:                       # a background image uploaded since is read afresh
            self._fetch_background()
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
        """Keep the overlay's place where the web overlay keeps it (``overlay_pos_x``/``_y``), with the monitors it
        was put on (``overlay_pos_layout``), best effort."""
        if self.api is None or self.ui.get("overlay_remember_position") is False:
            return
        try:
            self.api.post("/api/ui", self.host.saved_place())
        except (OSError, ValueError):
            pass

    def set_hover_state(self, state: str) -> None:
        """Hover to interact as the host has it: "arming" while the pointer rests, "open" once the whole overlay takes
        clicks, "off" when the pointer leaves; the card's edge shows it."""
        self.card.hover = state if state in ("arming", "open") else "off"
        self.card.setToolTip({"arming": "Keep the pointer here to use the overlay",
                              "open": "The overlay takes clicks until the pointer leaves it"}.get(self.card.hover, ""))
        self.card.update()


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
    from ..overlay import _ParentProcess, _default_url, native_overlay
    url = args.url or _default_url()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    window = MeterOverlay(AppApi(_app_base(url)), _ParentProcess(os.environ.get("AION2CALC_PARENT_PID")),
                          overlay_store(), native_overlay())
    window.show()
    window.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
