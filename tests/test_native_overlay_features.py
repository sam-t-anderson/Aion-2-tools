"""The native overlay's second part (0.2.415): the web overlay's row, target and window settings.

Each test turns one of the web overlay's settings on and checks the native overlay draws what the web overlay
draws for it, on the browser tests' meter answers (``tests/browser/test_browser_overlay_look.py``), off screen.
"""
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aion2calc.gui.overlay import MeterOverlay, RowLook  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "browser"))
from test_browser_overlay_look import fight  # noqa: E402


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


def _overlay(meter=None, **ui):
    window = MeterOverlay()
    window.apply_ui({"overlay_width": 340, **ui})
    window.apply_meter(meter or fight())
    return window


def _rows(window):
    return [row for row in window.rows if not row.isHidden()]


def test_the_rows_name_display_rank_numbers_and_compact_rows(qapp):
    meter = fight()
    for number, player in enumerate(meter["snapshot"]["players"], 1):
        player["party_number"] = number
    window = _overlay(meter, overlay_name_mode="class_number", overlay_rank_numbers=True, overlay_compact_rows=True,
                      overlay_show_combat_power=False)
    rows = _rows(window)
    assert [row.label() for row in rows] == ["1. Sorcerer 1", "2. Ranger 2", "3. Cleric 3"]
    assert rows[0].right() == "23,400/s"                                   # compact: the rate alone
    window.apply_ui({"overlay_width": 340, "overlay_name_mode": "number", "overlay_show_combat_power": False})
    assert [row.label() for row in _rows(window)] == ["P1", "P2", "P3"]
    assert _rows(window)[0].right() == "23,400/s  51.2%"


def test_your_unnamed_row_reads_you_and_your_combat_power_rides_beside_it(qapp):
    meter = fight()
    you = meter["snapshot"]["players"][1]                                  # Nyxara, the local name
    you["name"], you["id"] = "Player #7", "7"
    meter["snapshot"]["identity_status"].update(local_id="7", local_name="Player #7")
    window = _overlay(meter)
    labels = [row.label() for row in _rows(window)]
    assert labels[1] == "You  123.5K"                                      # the local combat power, short
    window.apply_ui({"overlay_width": 340, "overlay_show_combat_power": False})
    assert _rows(window)[1].label() == "You"


def test_the_dead_and_the_row_look_settings(qapp):
    meter = fight()
    meter["snapshot"]["players"][2]["dead"] = True
    window = _overlay(meter, overlay_highlight_me=True, overlay_row_stripes=True, overlay_class_swatch=True,
                      overlay_class_color_names=True, overlay_bar_style="gradient", overlay_bar_rounded=True)
    rows = _rows(window)
    assert rows[2].dead and rows[2].label() == "Velmira  DEAD"             # by the name, as the web overlay's
    assert rows[1].mine and rows[1].look.highlight_me
    look = window.look
    assert (look.stripes, look.class_swatch, look.class_names, look.gradient, look.rounded) == (True,) * 5
    window.grab()                                                          # every look paints
    window.apply_ui({"overlay_width": 340, "overlay_show_deaths": False})
    assert not _rows(window)[2].dead


def test_the_target_hp_ttk_enrage_and_break_gauge(qapp):
    meter = fight()
    target = meter["snapshot"]["current_target"]
    target["enrage"] = {"enraged": False, "enrage_in": 95, "enrage_s": 300}
    target["break_gauge"] = {"pct": 62.4}
    window = _overlay(meter)
    assert window.target_text == "Atiel"                                 # each part has its setting
    assert window.hp.isHidden() and window.gauge.isHidden()
    window.apply_ui({"overlay_width": 340, "overlay_show_enemy_hp": True, "overlay_show_ttk": True,
                     "overlay_show_break_gauge": True})
    assert window.target_text == "Atiel  ·  47.0%  ·  TTK 1m06s  ·  Enrage 1m35s  ·  Break 62%"
    assert not window.gauge.isHidden() and window.gauge.fraction == pytest.approx(0.624)
    target["enrage"]["enraged"], target["break_gauge"]["pct"] = True, 3
    window.apply_meter(meter)
    assert window.target_text.endswith("ENRAGED  ·  BROKEN")
    assert window.gauge.broken and window.gauge.shown() == 1.0             # broken: the whole bar in stripes


def test_your_contribution_and_the_dummy_parse(qapp):
    meter = fight()
    meter["snapshot"]["contribution"] = {"damage": 1_170_000, "share": 0.34, "dps": 15_600}
    window = _overlay(meter)
    assert window.contribution_text == "Your contribution: 34% · 1.17M (15.60K/s)"
    assert window.contribution.text() == window.contribution_text and not window.contribution.isHidden()
    assert window.dummy.isHidden()
    window.set_metric("hps")
    assert window.contribution.isHidden()                                  # the DPS view only
    window.set_metric("dps")
    meter["snapshot"]["dummy_parse"] = {"duration": 45.4, "window_seconds": 60, "window_reached": False,
                                        "your_dps": 15_600, "target_dps": 45_700}
    window.apply_meter(meter)
    assert window.dummy_text == "Dummy parse 45s / 60s · You 15.60K/s · Total 45.70K/s"
    assert not window.dummy.isHidden() and not window.contribution.isHidden()   # both: the dummy at the top
    assert window.box.indexOf(window.dummy) < window.box.indexOf(window.content) < window.box.indexOf(window.chips)
    assert window.dummy.property("ok") is False
    meter["snapshot"]["dummy_parse"]["window_reached"] = True
    window.apply_meter(meter)
    assert window.dummy.property("ok") is True and window.dummy_text.startswith("Dummy parse 45s / 60s ✓")
    window.apply_ui({"overlay_width": 340, "meter_show_dummy_parse": False, "overlay_show_contribution": False})
    assert window.dummy.isHidden() and window.contribution.isHidden()


def test_the_cooldown_strip_counts_down_between_readings(qapp):
    meter = fight()
    meter["snapshot"]["cooldowns"] = [{"family": 1, "name": "Flame Bolt", "remaining_ms": 4200, "cooldown_ms": 8000},
                                      {"family": 2, "name": "Frost Spear", "remaining_ms": 0, "cooldown_ms": 6000}]
    meter["snapshot"]["chain_windows"] = [{"family": 3, "name": "Burst"}]
    window = _overlay(meter)
    assert window.cooldowns.isHidden()                                     # off by default
    window.apply_ui({"overlay_width": 340, "overlay_show_cooldowns": True})
    assert not window.cooldowns.isHidden()
    read = window.cooldowns.read_at
    assert window.cooldowns.texts(read) == [("Burst ⛓", True), ("Flame Bolt 4.2s", False), ("Frost Spear ready", True)]
    assert window.cooldowns.texts(read + 2.0)[1] == ("Flame Bolt 2.2s", False)
    assert window.cooldowns.texts(read + 3.5)[1:] == [("Flame Bolt 0.7s", False)]   # ready 3 s ago: gone
    assert window.cooldowns.texts(read + 5.0)[1:] == [("Flame Bolt ready", True)]    # lit once ready
    rows_at = window.box.indexOf(window.cooldowns)
    window.apply_ui({"overlay_width": 340, "overlay_show_cooldowns": True, "overlay_cooldowns_position": "top"})
    assert window.box.indexOf(window.cooldowns) < rows_at                  # moved above the player rows


def test_only_in_combat_auto_expand_and_the_status(qapp):
    meter = fight()
    meter["snapshot"]["players"] += [dict(meter["snapshot"]["players"][2], id=str(9 + i), key=str(9 + i),
                                          name=f"Extra{i}", dps=1000 - i) for i in range(8)]
    window = _overlay(meter, overlay_max_players=4)
    assert len(_rows(window)) == 4
    window.apply_ui({"overlay_width": 340, "overlay_max_players": 4, "overlay_auto_expand": True})
    assert len(_rows(window)) == 11                                        # every player with damage
    meter["snapshot"].update(paused=True, decode_backlog={"catching_up": True, "queue_depth": 1200})
    window.apply_meter(meter)
    assert window.status_text.startswith("Latest combat · Paused DPS · Atiel")
    assert window.status_text.endswith("⏳ catching up (1200)")
    assert window.clock.text() == "01:15 Paused catching up (1200) Party DPS 53.67K"   # the notes, all eleven
    meter["snapshot"].update(battle_over=True)
    window.apply_ui({"overlay_width": 340, "overlay_only_in_combat": True})
    assert window.status_text == "Idle · waiting for combat" and _rows(window) == []
    assert window.target_card.isHidden() and window.lines.isHidden() and window.clock.isHidden()
    assert window.ping.isHidden() and window.metric_chip.isHidden() and not window.toolbar.isHidden()


def test_the_background_modes(qapp):
    window = _overlay()
    assert window.card.mode == "card"
    for mode in ("top", "none"):
        window.apply_ui({"overlay_width": 340, "overlay_bg_mode": mode})
        window.apply_meter(fight())
        assert window.card.mode == mode
        window.grab()
    assert window.card.rows_part is window.content                       # the top mode's panel ends where it begins
    assert window.content.geometry().top() == window.target_card.geometry().bottom() + 1
    window.apply_ui({"overlay_width": 340, "overlay_bg_mode": "nonsense"})
    assert window.card.mode == "card"


def test_the_row_look_defaults_follow_the_web_overlays():
    look = RowLook({})
    assert (look.name_mode, look.show_deaths, look.show_cp, look.compact, look.auto_expand) == ("name", True, True,
                                                                                              False, False)
