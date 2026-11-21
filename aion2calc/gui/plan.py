"""The native overlay's raid plan view (0.2.424): the Raid Planner's saved plans played on the overlay, as the web
overlay's plan view draws them (overlay.js ``renderPlan``, ``planView``, ``tokenPos``, ``aoeSVG``).

The planner keeps its plans in the browser, and hands the app a copy each time it saves (``GET /api/plans/saved``),
which the overlay reads. With *Auto-play* on (``overlay_plan_autoplay``, on by default) and a fight running against a
boss a plan is bound to (its ``encounter.npc_id``), that plan plays synced to the fight's clock; otherwise the latest
saved plan loops on a clock of its own.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

TOKEN = "#39c2e0"                         # a token's colour when the plan gives none


def _num(value, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _updated(plan) -> float:
    return _num((plan.get("meta") or {}).get("updated")) if isinstance(plan, dict) else 0.0


def newest(plans: dict) -> list[dict]:
    """The saved plans, the most recently saved first."""
    found = [plan for plan in (plans or {}).values() if isinstance(plan, dict)]
    return sorted(found, key=_updated, reverse=True)


def plan_for(plans: dict, npc) -> dict | None:
    """The most recently saved plan bound to this boss's NPC code (``planForNpc``), or None."""
    code = _num(npc)
    if not code:
        return None
    return next((plan for plan in newest(plans) if _num((plan.get("encounter") or {}).get("npc_id")) == code), None)


def plan_view(plans: dict, answer: dict, autoplay: bool, clock: float) -> tuple[dict | None, float, bool, float]:
    """What to show (``planView``): the plan, the time into it, whether it plays live with the fight, and its length.
    With auto-play on and a fight running against a boss a plan is bound to, that plan at the fight's time; else the
    latest saved plan at ``clock`` (seconds of the view's own clock), round and round."""
    if autoplay and isinstance(answer, dict) and answer.get("running") is True:
        snap = answer.get("snapshot") if isinstance(answer.get("snapshot"), dict) else {}
        target = snap.get("current_target")
        bound = plan_for(plans, target.get("mob_code")) if isinstance(target, dict) and not target.get("is_player") else None
        if bound is not None:
            length = max(1.0, _num(bound.get("duration"), 1.0))
            return bound, min(max(0.0, _num(snap.get("duration"))), length), True, length
    latest = next(iter(newest(plans)), None)
    length = max(1.0, _num(latest.get("duration"), 1.0)) if latest is not None else 1.0
    return latest, clock % length, False, length


def token_at(token: dict, time: float) -> tuple[float, float] | None:
    """A token's place at ``time`` (``tokenPos``): along its keyframes, held at the first before it and at the last
    after it; None with no keyframes."""
    frames = [frame for frame in (token.get("keyframes") or []) if isinstance(frame, dict)]
    if not frames:
        return None
    first, last = frames[0], frames[-1]
    if time <= _num(first.get("t")):
        return _num(first.get("x")), _num(first.get("y"))
    if time >= _num(last.get("t")):
        return _num(last.get("x")), _num(last.get("y"))
    for before, after in zip(frames, frames[1:]):
        if time <= _num(after.get("t")):
            span = max(1e-6, _num(after.get("t")) - _num(before.get("t")))
            share = (time - _num(before.get("t"))) / span
            return (_num(before.get("x")) + (_num(after.get("x")) - _num(before.get("x"))) * share,
                    _num(before.get("y")) + (_num(after.get("y")) - _num(before.get("y"))) * share)
    return _num(last.get("x")), _num(last.get("y"))


def shown(token: dict, time: float) -> bool:
    """Whether a token is on the map at ``time``: not hidden in the planner, and within its ``from`` and ``until``
    (a recorded add before it appeared, a summon after it faded, are not drawn)."""
    if token.get("hidden"):
        return False
    since, until = token.get("from"), token.get("until")
    if isinstance(since, (int, float)) and math.isfinite(since) and time < since:
        return False
    if isinstance(until, (int, float)) and math.isfinite(until) and time > until:
        return False
    return True


class PlanMap(QWidget):
    """The plan's map (``.ovarena``): a 200 px square, its faint gold edge and dark ground, the planner's 100-unit
    square in it with its frame, and each token where it is at the moment shown: a circle for a player (2.6 units) or
    an enemy (3.4), or an area's shape (a circle, a ring, a cone or a line) at a quarter of its colour."""

    SIDE = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan: dict | None = None
        self.time = 0.0
        self.setFixedSize(self.SIDE, self.SIDE)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(self.SIDE, self.SIDE)

    def set_moment(self, plan: dict | None, time: float) -> None:
        self.plan, self.time = plan, time
        self.update()

    def places(self) -> list[tuple[dict, float, float]]:
        """Each token drawn now, and its place in the planner's units (0 to 100)."""
        out = []
        for token in (self.plan or {}).get("tokens") or []:
            if not isinstance(token, dict) or not shown(token, self.time):
                continue
            place = token_at(token, self.time)
            if place is not None:
                out.append((token, place[0] * 100, place[1] * 100))
        return out

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        ground = QPainterPath()
        ground.addRoundedRect(box, 6, 6)
        painter.fillPath(ground, QColor(6, 9, 15, 128))
        painter.setPen(QPen(QColor(233, 203, 128, 77), 1))
        painter.drawPath(ground)
        inner = QRectF(self.rect()).adjusted(1, 1, -1, -1)   # the picture fills the box inside its edge
        painter.translate(inner.topLeft())
        painter.scale(inner.width() / 100, inner.height() / 100)
        painter.setPen(QPen(QColor(136, 136, 136, 102), 0.6))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(1, 1, 98, 98), 2, 2)
        for token, x, y in self.places():
            colour = QColor(token.get("color") or TOKEN)
            if not colour.isValid():
                colour = QColor(TOKEN)
            if token.get("kind") == "aoe":
                self._area(painter, token, x, y, colour)
            else:
                painter.setPen(QPen(QColor(0, 0, 0, 136), 0.5))
                painter.setBrush(colour)
                radius = 3.4 if token.get("kind") == "enemy" else 2.6
                painter.drawEllipse(QPointF(x, y), radius, radius)

    @staticmethod
    def _area(painter: QPainter, token: dict, x: float, y: float, colour: QColor) -> None:
        """An area token (``aoeSVG``): its colour at a quarter, edged in it; a ring as a wide circle's stroke."""
        facing = _num(token.get("facing")) * math.pi / 180
        reach = (_num(token.get("radius")) or 0.14) * 100
        fill = QColor(colour)
        fill.setAlphaF(0.25)
        painter.setPen(QPen(colour, 0.5))
        painter.setBrush(fill)
        shape = token.get("shape")
        if shape == "ring":
            inner = min(reach * 0.98, _num(token.get("inner")) * 100)
            edge = QColor(colour)
            edge.setAlphaF(0.35)
            painter.setPen(QPen(edge, max(0.4, reach - inner)))
            painter.setBrush(Qt.NoBrush)
            middle = (reach + inner) / 2
            painter.drawEllipse(QPointF(x, y), middle, middle)
            return
        angle = _num(token.get("angle"))
        if shape == "cone" and 0 < angle < 180:
            start = facing - angle * math.pi / 180
            path = QPainterPath(QPointF(x, y))
            path.lineTo(x + reach * math.cos(start), y - reach * math.sin(start))
            # The arc from one edge to the other, counter-clockwise as the web overlay's SVG sweeps it.
            path.arcTo(QRectF(x - reach, y - reach, 2 * reach, 2 * reach), math.degrees(start), 2 * angle)
            path.closeSubpath()
            painter.drawPath(path)
            return
        if shape == "line":
            length = (_num(token.get("length")) or 0.14) * 100
            half = (_num(token.get("width")) or 0.02) * 50
            ux, uy = math.cos(facing), -math.sin(facing)
            px, py = -uy * half, ux * half
            painter.drawPolygon(QPolygonF([QPointF(x + px, y + py), QPointF(x + ux * length + px, y + uy * length + py),
                                           QPointF(x + ux * length - px, y + uy * length - py),
                                           QPointF(x - px, y - py)]))
            return
        painter.drawEllipse(QPointF(x, y), reach, reach)
