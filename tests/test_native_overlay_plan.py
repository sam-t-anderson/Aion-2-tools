"""The native overlay's eleventh part (0.2.424): the raid plan view as the web overlay draws it (overlay.js
``renderPlan``, ``planView``, ``tokenPos``, ``aoeSVG``), off screen.

The toolbar's tabs between the meter and the plan; the saved plans the app keeps for the overlay; the latest plan
looping on the view's own clock, or with auto-play the plan bound to the boss being fought, synced to the fight; its
tokens along their keyframes, hidden or off the map out of their time, and the areas' shapes.
"""
import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui.overlay import MeterOverlay  # noqa: E402
from aion2calc.gui.plan import PlanMap, newest, plan_for, plan_view, shown, token_at  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
sys.path.insert(0, os.path.dirname(__file__))
from test_browser_overlay_look import PLAN, fight  # noqa: E402
from test_native_overlay_toolbar import FakeApp, laid_out_apart, settle  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    """Each test's windows are closed and deleted while Qt's application exists (see test_native_interface.py)."""
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


class PlanApp(FakeApp):
    """The app's local API with the Raid Planner's saved plans (``/api/plans/saved``)."""

    def __init__(self, plans=None, meter=None):
        super().__init__(meter or fight())
        self.plans = plans or {}

    def get(self, path):
        if path == "/api/plans/saved":
            self.calls.append(("GET", path, None))
            return {"plans": self.plans, "updated": None}
        return super().get(path)


def _overlay(meter=None, api=None, **ui):
    window = MeterOverlay(api)
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _plan(name, updated, npc=None, duration=60, tokens=None):
    plan = {**PLAN, "duration": duration, "meta": {"name": name, "updated": updated}}
    if npc is not None:
        plan["encounter"] = {"npc_id": npc}
    if tokens is not None:
        plan["tokens"] = tokens
    return plan


def _near(image: QImage, colour: str, box: QRectF | None = None, reach: int = 40, alpha: int = 150) -> int:
    want, count = QColor(colour), 0
    box = box or QRectF(0, 0, image.width(), image.height())
    for y in range(max(0, int(box.top())), min(image.height(), int(box.bottom()))):
        for x in range(max(0, int(box.left())), min(image.width(), int(box.right()))):
            pixel = image.pixelColor(x, y)
            if max(abs(pixel.red() - want.red()), abs(pixel.green() - want.green()),
                   abs(pixel.blue() - want.blue())) <= reach and pixel.alpha() > alpha:
                count += 1
    return count


# ------------------------------------------------------------------ which plan, and when
def test_the_plan_shown_is_the_latest_or_the_one_bound_to_the_boss_fought():
    old, new, atiel = _plan("Old", 1), _plan("New", 3), _plan("Atiel pull", 2, npc=2340601, duration=90)
    plans = {"a": old, "b": new, "c": atiel}
    assert [plan["meta"]["name"] for plan in newest(plans)] == ["New", "Atiel pull", "Old"]
    assert plan_for(plans, 2340601) is atiel and plan_for(plans, 99) is None and plan_for(plans, None) is None
    meter = fight()                                                   # a running fight against Atiel
    assert plan_view(plans, meter, True, 1234.5)[:3] == (atiel, 75.0, True)   # synced to the fight's 75 s
    meter["snapshot"]["duration"] = 200
    assert plan_view(plans, meter, True, 0)[1:] == (90.0, True, 90.0)          # held at its end
    plan, moment, live, length = plan_view(plans, meter, False, 125.0)         # auto-play off: the latest, looping
    assert (plan, moment, live, length) == (new, 5.0, False, 60.0)
    meter["running"] = False
    assert plan_view(plans, meter, True, 30.0)[0] is new                       # no fight running: the latest
    assert plan_view({}, meter, True, 30.0)[0] is None


def test_a_token_moves_along_its_keyframes_within_its_time():
    token = {"keyframes": [{"t": 10, "x": 0.2, "y": 0.4}, {"t": 30, "x": 0.6, "y": 0.8}]}
    assert token_at(token, 0) == (0.2, 0.4) and token_at(token, 40) == (0.6, 0.8)   # held before and after
    assert token_at(token, 20) == pytest.approx((0.4, 0.6))
    assert token_at({"keyframes": []}, 5) is None
    assert shown(token, 5) and not shown({**token, "hidden": True}, 5)
    assert not shown({**token, "from": 12}, 5) and shown({**token, "from": 12}, 12)   # a recorded add, not yet come
    assert not shown({**token, "until": 3}, 5)                                          # a summon gone
    assert shown({**token, "from": math.nan}, 5)


# ------------------------------------------------------------------ the view
def test_the_tabs_switch_between_the_meter_and_the_plan(qapp):
    api = PlanApp()
    window = _overlay(api=api)
    window.show()
    QCoreApplication.processEvents()
    assert window.tabs["plan"].isVisible() and window.tabs["meter"].isHidden()     # the other view's tab
    tools = window.toolbar.layout()
    assert tools.itemAt(1).widget() is window.tabs["meter"] and tools.itemAt(2).widget() is window.tabs["plan"]
    window.tabs["plan"].click()
    settle(lambda: ("GET", "/api/plans/saved", None) in api.calls)              # asked for at once
    assert window.view == "plan" and window.tabs["meter"].isVisible() and window.tabs["plan"].isHidden()
    assert window.empty.text() == "No saved plan yet. Plans you save in the app's Raid Planner show here."
    for part in (window.metric_chip, window.ping, window.clock, window.target_card, window.plan_map):
        assert part.isHidden()
    assert all(row.isHidden() for row in window.rows)
    api.plans = {"p1": PLAN}
    window.tabs["meter"].click()
    window.tabs["plan"].click()                                                  # the view asks the app again
    settle(lambda: not window.plan_map.isHidden())
    assert "Atiel pull" in window.status_text and window.plan_map.toolTip() == window.status_text
    laid_out_apart(window)
    asked = len([call for call in api.calls if call[1] == "/api/plans/saved"])
    window._show_plan()
    assert len([call for call in api.calls if call[1] == "/api/plans/saved"]) == asked   # not again within 15 s


def test_back_from_the_plan_the_meter_shows_its_rows_again(qapp):
    meter = fight()
    meter["snapshot"]["paused"] = True                                           # a fight that no longer changes
    window = _overlay(meter)
    window.plans = {"p1": PLAN}
    window.set_view("plan")
    assert not window.plan_map.isHidden() and all(row.isHidden() for row in window.rows)
    window.apply_meter(meter)                                                    # a poll in the plan view
    assert all(row.isHidden() for row in window.rows) and window.clock.isHidden()
    window.set_view("meter")
    assert len([row for row in window.rows if not row.isHidden()]) == 3 and window.plan_map.isHidden()
    assert not window.clock.isHidden() and not window.metric_chip.isHidden()


def test_auto_play_plays_the_bound_plan_with_the_fight(qapp):
    window = _overlay()
    window.plans = {"a": _plan("Latest", 5), "b": _plan("Atiel pull", 2, npc=2340601, duration=90)}
    window.set_view("plan")
    assert window.status_text == "▶ live · Atiel pull · 75/90s"
    window.apply_ui({"overlay_width": 340, "overlay_plan_autoplay": False})
    window.apply_meter(fight())
    assert window.status_text.startswith("Latest · ") and window.status_text.endswith("/60s")
    assert window._plan_timer.isActive() and window._plan_timer.interval() == 100
    window.apply_ui({"overlay_width": 340, "performance_mode": True})
    assert window._plan_timer.interval() == 400                                  # a quarter as often
    window.set_view("meter")
    assert not window._plan_timer.isActive()


# ------------------------------------------------------------------ the map
def test_the_map_draws_each_token_at_its_place_in_its_colour(qapp):
    tokens = [{"id": "a", "kind": "player", "color": "#ff0000", "keyframes": [{"t": 0, "x": 0.25, "y": 0.25}]},
              {"id": "b", "kind": "enemy", "color": "#00ff00", "keyframes": [{"t": 0, "x": 0.75, "y": 0.75}]},
              {"id": "c", "kind": "player", "color": "#0000ff", "hidden": True, "keyframes": [{"t": 0, "x": 0.5, "y": 0.5}]}]
    plan_map = PlanMap()
    plan_map.set_moment(_plan("Map", 1, tokens=tokens), 0)
    assert [(token["id"], x, y) for token, x, y in plan_map.places()] == [("a", 25, 25), ("b", 75, 75)]
    image = plan_map.grab().toImage()
    scale = 198 / 100
    assert _near(image, "#ff0000", QRectF(1 + 20 * scale, 1 + 20 * scale, 10 * scale, 10 * scale), 30) > 10
    assert _near(image, "#00ff00", QRectF(1 + 70 * scale, 1 + 70 * scale, 10 * scale, 10 * scale), 30) > 15
    assert _near(image, "#0000ff", reach=60) == 0                                # hidden in the planner


@pytest.mark.parametrize("area, inside, outside", [
    ({"shape": "circle", "radius": 0.2}, (50, 35), (50, 25)),
    ({"shape": "ring", "radius": 0.2, "inner": 0.15}, (50, 32.5), (50, 45)),
    ({"shape": "cone", "radius": 0.3, "angle": 30, "facing": 0}, (70, 50), (30, 50)),
    ({"shape": "line", "length": 0.3, "width": 0.04, "facing": 90}, (50, 30), (50, 70)),
])
def test_an_areas_shape_is_drawn_at_a_quarter_of_its_colour(qapp, area, inside, outside):
    token = {"id": "z", "kind": "aoe", "color": "#ff0000", "keyframes": [{"t": 0, "x": 0.5, "y": 0.5}], **area}
    plan_map = PlanMap()
    plan_map.set_moment(_plan("Areas", 1, tokens=[token]), 0)
    image = plan_map.grab().toImage()
    scale = 198 / 100

    def reddish(point) -> bool:
        pixel = image.pixelColor(round(1 + point[0] * scale), round(1 + point[1] * scale))
        return pixel.red() > pixel.green() + 25

    assert reddish(inside) and not reddish(outside)
