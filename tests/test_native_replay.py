"""The native log review's movement replay (combat-review.js ``replay``), since 0.2.468: the view and its arena, the
tokens at a moment (their places, sides, kinds, colours, faded and gone, a player greyed while dead), the trails, and
the controls (Play and Pause, Rewind, the speed and the arena's shape kept, the time slider). Since 0.2.469 the boss
casts with their measured areas, the appearances, deaths, revives and add hits, drawn under the tokens, listed beside
the arena and ticked on the slider. Off screen over the Combat Logs tests' fake app and log server (made-up logs,
positions and measured areas).
"""
import json
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QBoxLayout, QComboBox, QLabel, QLineEdit, QSlider  # noqa: E402

from aion2calc.gui import combat_replay as rp  # noqa: E402
from aion2calc.gui import combat_review as cw  # noqa: E402
from aion2calc.gui.combat_records import GOLD, class_colour  # noqa: E402
from aion2calc.gui.combat_replay_view import NARROW, STATE_ROLE, Arena, mark_drawing  # noqa: E402
from test_native_combat import (REVIEW_LOG, REVIEW_RANKS, T0, FakeApp, _buttons, _click, _find, _labels, _page,  # noqa: E402
                                _shown)
from test_native_overlay_toolbar import settle  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _windows_closed():
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def _store(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "interface.ini"), QSettings.IniFormat)


def _at(t, entity, x, y, src="move", **extra):
    return {"t": t, "entity": entity, "x": x, "y": y, "z": 0.0, "src": src, **extra}


def _moving() -> dict:
    """The review log's boss fight with its recorded movement: the boss walking its room; the recording player's
    positions where they applied an effect or a cast aimed at them; the cleric, dead from 5 s and revived at 9 s; the
    sorcerer's spirit; a clone of the boss (an NPC the game data gives no name) that struck the cleric; and a wolf far
    off, last seen at 10 s."""
    log = json.loads(json.dumps(REVIEW_LOG))
    fight = log["segments"][0]
    fight["ping_recorder"] = "p1"
    fight["entities"] += [{"id": "a1", "name": "Unnamed NPC", "kind": "enemy", "mob_code": 2300100},
                          {"id": "w1", "name": "Wolf", "kind": "enemy"}]
    fight["events"].append({"kind": "damage", "t": 4.0, "source": "a1", "target": "p2", "amount": 300, "skill": "Attack",
                            "skill_id": 1800000})
    fight["movement"] = [
        _at(0, "b1", 10000, 20000), _at(4, "b1", 10400, 20000), _at(8, "b1", 10400, 20400), _at(60, "b1", 10000, 20000),
        _at(1, "p1", 9000, 19000, "applied"), _at(3, "p1", 9200, 19000, "targeted"), _at(30, "p1", 9400, 19200, "applied"),
        _at(0, "p2", 11000, 21000, "party"), _at(2, "p2", 11200, 21000, "party"), _at(5, "p2", 11200, 21200, "party"),
        _at(9.5, "p2", 11000, 21000, "party"),
        _at(1, "pet1", 9100, 19100), _at(3, "pet1", 9300, 19100),
        _at(3.5, "a1", 11100, 21100, "spawn"),
        _at(0, "w1", 40000, 60000), _at(10, "w1", 40100, 60000)]
    return log


def _replay(log=None, colours=None, names=None) -> rp.Replay:
    log = log or _moving()
    return rp.Replay(log, cw.data(log, cw.fresh_state()), colours or {}, names or {})


def _casting() -> dict:
    """The moving fight with the boss's casts: aimed at the cleric, around itself, on the ground near the sorcerer, at
    the sorcerer without a place, and unnamed; the boss walking on from 14 s, facing north-east at 18 s; a second clone
    appearing at 19 s that strikes the sorcerer; the clones' Shatter at once (20 s and 20.3 s) and again at 20.6 s; and a
    cast by an NPC without a position and one without a time, both left out."""
    log = _moving()
    fight = log["segments"][0]
    fight["entities"].append({"id": "a2", "name": "Unnamed NPC", "kind": "enemy", "mob_code": 2300100})
    fight["movement"] += [_at(14, "b1", 10000, 20400), _at(18, "b1", 10000, 20000, heading=45.0), _at(22, "b1", 10400, 20000),
                          _at(19, "a2", 10800, 20800, "spawn")]
    fight["events"].append({"kind": "damage", "t": 21.0, "source": "a2", "target": "p1", "amount": 100, "skill": "Shard",
                            "skill_id": 2300101})
    fight["npc_casts"] = [
        {"t": 2.0, "source": "b1", "skill_id": 123, "skill": "Frost Nova", "target": "p2", "pos": [11220.0, 21010.0, 0.0],
         "facing": 90.0},
        {"t": 12.0, "source": "b1", "skill_id": 124, "skill": "Ice Ring", "pos": [10420.0, 20410.0, 0.0]},
        {"t": 14.0, "source": "b1", "skill_id": 125, "skill": "Meteor", "target": "p1", "pos": [9400.0, 19600.0, 0.0]},
        {"t": 16.0, "source": "b1", "skill_id": 126, "skill": "Chill", "target": "p1"},
        {"t": 18.0, "source": "b1", "skill_id": 127},
        {"t": 20.0, "source": "a1", "skill_id": 128, "skill": "Shatter"},
        {"t": 20.3, "source": "a2", "skill_id": 128, "skill": "Shatter"},
        {"t": 20.6, "source": "a1", "skill_id": 128, "skill": "Shatter"},
        {"t": 24.0, "source": "b1", "skill_id": 129, "skill": "Lance", "facing": 0.0},
        {"t": 26.0, "source": "b1", "skill_id": 130, "skill": "Whirl"},
        {"t": 28.0, "source": "b1", "skill_id": 131, "skill": "Hail", "pos": [12000.0, 22000.0, 0.0]},
        {"t": 30.0, "source": "ghost", "skill_id": 132, "skill": "Nothing"},
        {"t": "soon", "source": "b1", "skill_id": 133}]
    return log


#: The bosses' skills' measured areas (``aoe-shapes.json``, made up): a dash in place of an older circle, a ring, wedges
#: with a safe gap, a trail, a cone by the boss's name for a generic skill, a circle round the caster from its hit, a
#: line, a cone all round and a circle at the aim.
CATALOG = {
    "123": {"shape": "circle_aim", "radius": 300.0, "delay": 1.0, "confidence": "high", "casts": 9, "accuracy": 0.9,
            "path": {"shape": "dash", "half_width": 200.0, "span": 3.0, "accuracy": 1.0, "confidence": "measured", "casts": 10}},
    "124": {"shape": "ring", "radius": 900.0, "inner": 300.0, "accuracy": 0.95, "confidence": "measured", "casts": 9},
    "125": {"shape": "arcs", "radius": 800.0, "inner": 0, "segments": [[-60, -30], [30, 60]], "anchor": "cast",
            "accuracy": 1.0, "confidence": "measured", "casts": 10},
    "126": {"shape": "trail", "half_width": 150.0, "span": 4.0, "duration": 3.0, "accuracy": 0.95, "confidence": "measured",
            "casts": 12},
    "Ice Queen|127": {"shape": "cone", "radius": 800.0, "angle": 45.0, "delay": 0.5, "confidence": "tentative", "casts": 4},
    "128": {"shape": "circle_caster", "radius": 650.0, "anchor": "hit", "delay": 1.2, "accuracy": 0.905,
            "confidence": "measured", "casts": 33},
    "129": {"shape": "line", "length": 2000.0, "half_width": 300.0, "accuracy": 0.85, "confidence": "measured", "casts": 16},
    "130": {"shape": "cone", "radius": 500.0, "angle": 180.0, "accuracy": 0.9, "confidence": "measured", "casts": 20},
    "131": {"shape": "circle_aim", "radius": 300.0, "delay": 1.0, "accuracy": 0.893, "confidence": "measured", "casts": 21}}


def test_the_view_and_its_arena():
    # the smallest circle holding the points: a pair's middle, a square's corners, points in a line, none
    assert rp.enclosing_circle([(0, 0), (2, 0), (1, 1)]) == {"x": 1.0, "y": 0.0, "r": 1.0}
    square = rp.enclosing_circle([(0, 0), (2, 0), (2, 2), (0, 2)])
    assert (square["x"], square["y"]) == pytest.approx((1, 1)) and square["r"] == pytest.approx(2 ** 0.5)
    assert rp.enclosing_circle([(0, 0), (1, 0), (3, 0)]) == {"x": 1.5, "y": 0.0, "r": 1.5}
    assert rp.enclosing_circle([(5, 5)]) == {"x": 5.0, "y": 5.0, "r": 0.0}
    assert rp.enclosing_circle([]) == {"x": 0.0, "y": 0.0, "r": 0.0}
    # without a boss: the middle 90% of the positions framed a tenth larger, north up; nothing beyond is lost
    world = [{"entity": "p", "x": 1000.0 * i, "y": 500.0 * i} for i in range(21)]
    at, rooms, scale = rp.frame_movement(world, lambda key: False, False)
    assert rooms is None
    x, y, out = at({"x": 10000, "y": 5000})                          # the middle of the ground
    assert (x, y, out) == (pytest.approx(50), pytest.approx(50), False)
    assert at({"x": 0, "y": 0})[1] > 50                              # south is down
    assert at({"x": 90000, "y": 0}) == (99, pytest.approx(at({"x": 0, "y": 0})[1]), True)   # at the edge, outside
    assert scale(1000) == pytest.approx(100 * 1000 / (20000 * 1.1))
    # a boss fight: its room as a circle and as a square, both in the view, the view fitting both
    rooms = _replay().rooms
    assert set(rooms) == {"circle", "square"}
    assert rooms["circle"]["r"] == pytest.approx(100 / 2.08)          # the larger shape across the view, a 25th to spare
    assert all(0 < a["x"] - a["r"] and a["x"] + a["r"] < 100 for a in rooms.values())


def test_the_replays_words():
    assert [rp.skill_class(v) for v in (16001234, "11000001", 19999999, 2e7, 1800000, None, "x")] == [
        "spiritmaster", "gladiator", "brawler", None, None, None, None]
    assert (rp.room_shape("square"), rp.room_shape(None), rp.room_shape("triangle")) == ("square", "circle", "circle")
    assert [rp.replay_speed(v) for v in ("2", "0.25", None, "3", "fast")] == [2, 0.25, 1, 1, 1]
    assert [rp.speed_words(v) for v in rp.SPEEDS] == ["0.25×", "0.5×", "1×", "2×", "4×", "8×"]
    assert rp.js_key_order(["b", "10", "2", "a", "01"]) == ["2", "10", "b", "a", "01"]   # as ``Object.keys`` lists them
    names = {"2300100": "Frost Wraith"}
    assert rp.add_name({"name": "Unnamed NPC", "mob_code": 2300100}, names) == "Frost Wraith"
    assert rp.add_name({"name": "Unnamed NPC", "mob_code": 2300100}) == "Clone"
    assert rp.add_name({"name": "#2300100", "mob_code": 2300100}) == "Clone"
    assert rp.add_name({"name": "Shade"}) == "Shade"
    replay = _replay()
    assert replay.note == ("16 recorded positions of 6 players and enemies. The game does not send the recording player's "
                           "own movement: 3 of their 3 positions are where they applied an effect or a cast aimed at them, "
                           "and the path is drawn between them. A party member's upload of the same fight records their "
                           "movement.")
    log = _moving()
    for row in log["segments"][0]["movement"]:
        if row["entity"] == "p1" and row["t"] == 30:
            row["via"] = 1                                           # a position of theirs from another recording
    assert _replay(log).note.endswith("comes from 1 positions in the other recordings of this fight; 3 more are where they "
                                      "applied an effect or a cast aimed at them.")


def test_each_tokens_side_kind_and_colour():
    replay = _replay(colours={"colors": {"cleric": "#00ff00"}})
    assert replay.order == ["b1", "p1", "p2", "pet1", "a1", "w1"]
    assert {k: replay.kind_of(k) for k in replay.order} == {"b1": "boss", "p1": "player", "p2": "player", "pet1": "pet",
                                                             "a1": "add", "w1": "enemy"}
    assert {k: replay.side_of(k) for k in replay.order} == {"b1": "enemy", "p1": "ally", "p2": "ally", "pet1": "ally",
                                                             "a1": "enemy", "w1": "enemy"}
    sorcerer = class_colour("sorcerer", {})
    assert [replay.shade(k) for k in replay.order] == [rp.ENEMY_RED, sorcerer, "#00ff00", sorcerer, rp.ENEMY_RED,
                                                       rp.NEUTRAL_GREY]
    # A summon the recording did not link to an owner, placed by what it did: a party class's skills on the boss make it
    # the party's; striking two party members, the other side's; nothing to tell, neither side's.
    log = _moving()
    fight = log["segments"][0]
    fight["entities"] += [{"id": "s1", "name": "Spirit", "kind": "pet"}, {"id": "s2", "name": "Spirit", "kind": "pet"},
                          {"id": "s3", "name": "Spirit", "kind": "pet"}]
    fight["events"] += [{"kind": "damage", "t": 6, "source": "s1", "target": "b1", "amount": 1, "skill_id": 15001000},
                        {"kind": "damage", "t": 6, "source": "s2", "target": "p1", "amount": 1},
                        {"kind": "damage", "t": 7, "source": "s2", "target": "p2", "amount": 1},
                        {"kind": "damage", "t": 6, "source": "e9", "target": "s3", "amount": 1}]
    fight["entities"].append({"id": "e9", "name": "Rogue", "kind": "enemy", "is_player": True, "class": "assassin"})
    fight["movement"] += [_at(6, "s1", 10000, 20000), _at(6, "s2", 10000, 20000), _at(6, "s3", 10000, 20000)]
    replay = _replay(log)
    assert [replay.side_of(k) for k in ("s1", "s2", "s3")] == ["ally", "enemy", "neutral"]
    assert [replay.kind_of(k) for k in ("s1", "s2", "s3")] == ["pet", "enemy", "pet"]
    assert replay.r["s1"]["class"] == "sorcerer"                      # its skills' class, for its colour
    assert replay.shade("s1") == sorcerer and replay.shade("s3") == GOLD   # a summon without a class: gold, as ``color`` gives


def test_the_tokens_at_a_moment():
    replay = _replay()

    def at(t):
        return {token["id"]: token for token in replay.frame(t)}
    start = at(0)
    assert list(start) == ["b1", "p2", "w1"]                         # the others not seen yet
    boss = start["b1"]
    assert (boss["radius"], boss["opacity"], boss["ring"], boss["tip"]) == (3.0, 1.0, False, "Ice Queen · move at 0.0s")
    assert boss["trail"] == [replay.at(_at(0, "b1", 10000, 20000))[:2], (boss["x"], boss["y"])]
    wolf = start["w1"]                                               # far off: at the view's edge, faded
    assert (wolf["x"], wolf["y"], wolf["opacity"], wolf["radius"], wolf["trail"]) == (99, 1, 0.35, 1.4, [])
    assert wolf["tip"] == "Wolf · move at 0.0s · outside the fight area"
    # a step between two positions at most 6 s apart
    two = at(2)
    assert two["b1"]["x"] == pytest.approx((replay.at({"x": 10000, "y": 0})[0] + replay.at({"x": 10400, "y": 0})[0]) / 2)
    assert two["p1"]["ring"] and two["p1"]["tip"] == "TestSorc ✓ · Zikel · applied at 1.0s"
    assert len(two["p2"]["trail"]) == 3 and two["pet1"]["trail"] == []
    assert at(3.5)["a1"]["tip"] == "Clone · spawn at 3.5s" and at(3.5)["a1"]["radius"] == 1.8
    # dead from 5 s: greyed, until revived at 9 s
    assert at(6)["p2"]["opacity"] == 0.2 and at(6)["p2"]["tip"] == "TestCleric · dead since 5.0s · party at 5.0s"
    assert at(9.6)["p2"]["opacity"] == 1.0
    # last seen over 8 s ago: faded; unseen 20 s, an enemy leaves, a player or a boss after a minute
    later = at(35)
    assert later["b1"]["opacity"] == 0.35 and later["p2"]["opacity"] == 0.35 and "w1" not in later
    assert list(at(70)) == ["b1", "p1"]
    assert at(70)["p1"]["opacity"] == 0.35


def test_an_older_recordings_positions():
    log = json.loads(json.dumps(REVIEW_LOG))
    fight = log["segments"][0]
    fight["positions"] = [{"t": 0, "entity": "b1", "x": 0.5, "y": 0.5}, {"t": 2, "entity": "b1", "x": 0.6, "y": 0.5},
                          {"t": 1, "entity": "p1", "x": 0.2, "y": 0.3}, {"t": 1, "entity": "p1", "x": 0.2, "y": "far"}]
    replay = _replay(log)
    assert replay.note == "" and replay.rooms is None and not replay.world
    tokens = {token["id"]: token for token in replay.frame(1)}
    assert (tokens["b1"]["x"], tokens["b1"]["y"], tokens["b1"]["trail"]) == (pytest.approx(55), 50, [])
    assert (tokens["p1"]["x"], tokens["p1"]["y"]) == (20, 30)
    assert len(replay.tokens["p1"]) == 1                             # a position without a place is left out


def test_the_arena_draws_and_names_what_is_under_the_pointer(qapp):
    arena = Arena()
    arena.resize(800, 320)
    replay = _replay()
    arena.show_moment(replay.frame(0), {**replay.rooms["circle"], "shape": "circle"})
    left, top, unit = arena.view()
    assert (left, top, unit) == (240, 0, 3.2)                        # the 100-unit view in the middle, 320 px square
    boss = replay.frame(0)[0]
    assert arena.tip_at(left + boss["x"] * unit, top + boss["y"] * unit) == "Ice Queen · move at 0.0s"
    assert arena.tip_at(left + 50 * unit, top + 95 * unit) == rp.ARENA_TIP
    assert arena.tip_at(5, 5) == ""                                  # outside the arena
    arena.show_moment([], {**replay.rooms["square"], "shape": "square"})
    corner = replay.rooms["square"]
    assert arena.tip_at(left + (corner["x"] + corner["r"] - 0.5) * unit, top + (corner["y"] + corner["r"] - 0.5) * unit) == rp.ARENA_TIP
    image = arena.grab().toImage()                                   # drawn: the ground, the room and no token
    assert image.pixelColor(5, 5).alpha() == 255 and image.width() == 800


def test_the_replay_plays_on_a_logs_page(qapp, tmp_path):
    app = FakeApp()
    app.log_server.review_log = _moving()
    store = _store(tmp_path)
    store.setValue(rp.SPEED_KEY, "2")
    page = _page(app, store=store)
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: view.replay is not None and not view.awaiting)
    panel = view.replay
    labels = _labels(view)
    assert rp.HEAD in labels and _replay().note in labels
    # after the publish form, before another log to compare
    body = panel.parentWidget().layout()
    compare = _find(view, QLineEdit, lambda f: f.accessibleName() == "Link or ID of the log to compare").parentWidget()
    assert body.indexOf(panel) == body.indexOf(compare) - 1
    assert panel.clock_label.text() == "0.0s" and panel.speed == 2
    speed = _find(view, QComboBox, lambda c: c.accessibleName() == "Playback speed")
    assert speed.currentText() == "2×" and [speed.itemText(i) for i in range(speed.count())] == [
        "0.25×", "0.5×", "1×", "2×", "4×", "8×"]
    shape = _find(view, QComboBox, lambda c: c.accessibleName() == "Arena")
    assert shape.currentData() == "circle" and panel.arena.room["shape"] == "circle"
    scrub = _find(view, QSlider, lambda s: s.accessibleName() == "Replay time")
    assert (scrub.minimum(), scrub.maximum(), scrub.value()) == (0, 1200, 0)
    # Play: the fight's seconds at the speed chosen, on the replay's own clock
    clock = [100.0]
    panel.now = lambda: clock[0]
    _click(view, "Play")
    assert panel.playing() and panel.play.text() == "Pause"
    clock[0] += 1.5
    panel._tick()
    assert panel.clock == pytest.approx(3.0) and panel.clock_label.text() == "3.0s" and scrub.value() == 30
    assert {t["id"] for t in panel.arena.tokens} == {"b1", "p1", "p2", "pet1", "w1"}
    _click(view, "Pause")
    assert not panel.playing() and panel.play.text() == "Play"
    # the slider: a moment chosen, playing paused
    _click(view, "Play")
    scrub.setValue(60)
    assert not panel.playing() and panel.clock == 6.0 and panel.clock_label.text() == "6.0s"
    assert next(t for t in panel.arena.tokens if t["id"] == "p2")["opacity"] == 0.2
    # played to the end, it stops there
    _click(view, "Play")
    clock[0] += 1000
    panel._tick()
    assert panel.clock == 120 and not panel.playing() and scrub.value() == 1200
    _click(view, "Rewind")
    assert panel.clock == 0 and scrub.value() == 0
    # the speed and the arena's shape are kept for every log
    speed.setCurrentIndex(5)
    speed.activated.emit(5)
    shape.setCurrentIndex(1)
    shape.activated.emit(1)
    assert store.value(rp.SPEED_KEY) == "8" and store.value(rp.ROOM_KEY) == "square" and panel.arena.room["shape"] == "square"
    # the page drawn again stops the replay that was playing, and draws it anew from the start
    _click(view, "Play")
    view.draw()
    _shown()
    assert not panel.playing() and view.replay is not panel and view.replay.clock == 0
    assert view.replay.speed == 8 and view.replay.shape == "square"
    view.stop()
    assert view.replay is None


def test_a_log_without_movement(qapp, tmp_path):
    app = FakeApp()
    page = _page(app, store=_store(tmp_path))
    # a recording here holding none: no replay
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: view.doc is not None and not view.awaiting)
    assert view.replay is None and rp.HEAD not in _labels(view)
    # a shared log holding none: said so, as another public recording of the fight may hold it
    page.open_review("shared", "log0001")
    settle(lambda: view.where.get("kind") == "shared" and view.doc is not None and not view.awaiting)
    labels = _labels(view)
    assert rp.HEAD in labels and rp.NO_MOVEMENT + rp.MAY_HOLD in labels and view.replay is None

def test_another_log_after_a_replay(qapp, tmp_path):
    """The replay drawn is let go as the page clears for another log or for a log that cannot be read: its panel is
    deleted once the app's event loop runs, and the page draws the next log without reaching for it."""
    app = FakeApp()
    app.log_server.review_log = _moving()
    page = _page(app, store=_store(tmp_path))
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: view.replay is not None and not view.awaiting)
    first = view.replay
    _click(view, "Play")
    page.open_review("local", "session-1.a2log.json", None, 0)
    assert view.replay is None and not first.playing()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)       # as the app's event loop does
    settle(lambda: view.replay is not None and not view.awaiting)
    assert view.replay is not first and rp.HEAD in _labels(view)
    # the log read again, and no longer there: said so, the replay let go with the page
    app.log_server.review_log = {"error": "No such recording"}
    view.reload()
    settle(lambda: "No such recording" in _labels(view))
    assert view.replay is None
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.log_server.review_log = _moving()
    view.reload()
    settle(lambda: view.replay is not None and not view.awaiting)
    assert rp.HEAD in _labels(view)


def test_the_measured_areas_in_words():
    assert [rp.metres(v) for v in (500, 999, 1000, 2674, None)] == ["5.0 m", "10.0 m", "10 m", "27 m", "NaN m"]
    # an area shows for the longer of 1.5 s and its first hit's delay and one
    assert (rp.aoe_life({"delay": 1.2}), rp.aoe_life({}), rp.aoe_life({"delay": 0.3})) == (pytest.approx(2.2), 1.5, 1.5)
    # a dash or trail and wedges: the skill's own, or the skill itself as one
    dash = {"shape": "dash", "half_width": 200.0, "span": 3.0}
    wedges = {"shape": "arcs", "radius": 800.0, "segments": [[-60, -30], [30, 60]]}
    both = {"shape": "circle_aim", "radius": 300.0, "path": dash, "arcs": wedges}
    assert rp.aoe_extras(dash) == (dash, None) and rp.aoe_extras(wedges) == (None, wedges)
    assert rp.aoe_extras(both) == (dash, wedges) and rp.aoe_extras({"shape": "cone"}) == (None, None)
    # how long a cast's area stays: a dash through its span and a moment, a trail through its last part
    trail = {"shape": "trail", "half_width": 150, "span": 4, "duration": 3}
    assert (rp.area_life(dash), rp.area_life(trail), rp.area_life(both)) == (pytest.approx(3.6), 7, pytest.approx(3.6))
    assert rp.area_life({**wedges, "delay": 2.0}) == 3.0 and rp.area_life({"shape": "cone", "delay": 0.2}) == 1.5
    # the older shapes, a shape not known and none
    assert [rp.aoe_text(a) for a in (
        {"shape": "circle_aim", "radius": 300}, {"shape": "circle_caster", "radius": 650},
        {"shape": "cone", "radius": 800, "angle": 45}, {"shape": "cone", "radius": 800, "angle": 22.5},
        {"shape": "line", "length": 2230, "half_width": 400}, {"shape": "ring", "radius": 2674, "inner": 985},
        {"shape": "blob"}, {})] == [
        "circle of 3.0 m around the aim", "circle of 6.5 m around the caster", "90° cone 8.0 m long", "45° cone 8.0 m long",
        "line 22 m long, 8.0 m wide", "ring from 9.8 m to 27 m around the caster", "blob", "undefined"]
    # a dash, a trail and wedges, in place of the skill's older shape
    assert rp.aoe_text(dash) == "dash 4.0 m wide along its path for 3.0 s"
    assert rp.aoe_text(trail) == "trail 3.0 m wide along its path for 4.0 s, each part staying 3.0 s"
    assert rp.aoe_text(wedges) == "2 wedges of 8.0 m around the caster, safe between them"
    assert rp.aoe_text({"shape": "arcs", "radius": 800, "segments": [[0, 30]]}) == "1 wedge of 8.0 m around the caster"
    assert rp.aoe_text(both) == ("dash 4.0 m wide along its path for 3.0 s and 2 wedges of 8.0 m around the caster, safe "
                                 "between them")
    # and how well each fits: its own fit, else the skill's
    fit = {"confidence": "high", "casts": 9, "accuracy": 0.905}
    assert rp.measured_text({"shape": "circle_aim", "radius": 300, **fit}) == (
        "circle of 3.0 m around the aim (high, 9 casts, 91% of the positions explained)")
    assert rp.measured_text({"shape": "cone", "radius": 800, "angle": 45, "casts": 0}) == "90° cone 8.0 m long (0 casts)"
    assert rp.measured_text({"shape": "cone", "radius": 800, "angle": 45}) == "90° cone 8.0 m long ()"
    own = {**dash, "confidence": "measured", "casts": 10, "accuracy": 1.0}
    assert rp.measured_text({**both, **fit, "path": own}) == (
        "dash 4.0 m wide along its path for 3.0 s (measured, 10 casts, 100% of the positions explained) and 2 wedges of "
        "8.0 m around the caster, safe between them (high, 9 casts, 91% of the positions explained)")


def test_the_casts_and_events_listed():
    replay = _replay(_casting())
    # the casts with a caster on the replay and a time, in time order; the enemies that appeared after the first second;
    # the deaths and revives; where a clone or add struck a player
    assert [c["t"] for c in replay.casts] == [2.0, 12.0, 14.0, 16.0, 18.0, 20.0, 20.3, 20.6, 24.0, 26.0, 28.0]
    assert [(s["id"], s["t"]) for s in replay.spawns] == [("a1", 3.5), ("a2", 19)]
    assert [(life["kind"], life["t"]) for life in replay.lives] == [("death", 5.0), ("revive", 9.0)]
    assert [(h["source"], h["target"], h["t"]) for h in replay.add_hits] == [("a1", "p2", 4.0), ("a2", "p1", 21.0)]
    # the slider's ticks: each one's tenth, once
    assert replay.ticked and replay.ticks() == [2.0, 12.0, 14.0, 16.0, 18.0, 20.0, 20.3, 20.6, 24.0, 26.0, 28.0, 3.5, 19.0,
                                                5.0, 9.0, 4.0, 21.0]

    def rows():
        return [(e["kind"], rp.fixed(e["t"], 1), e["who"], e["what"], e["where"], e["area"], e["n"], e["show"])
                for e in replay.event_rows()]
    # where each cast was aimed: at its target, around the boss itself, on the ground (near its target), or untold;
    # an unnamed skill by its number; the clones' Shatter at once one row with a count, again 0.6 s on another
    assert rows() == [
        ("cast", "2.0", "Ice Queen", "Frost Nova", "at TestCleric", "", 1, 2.5),
        ("spawn", "3.5", "Clone", "", "", "", 1, 3),
        ("hit", "4.0", "Clone", "", "TestCleric · Cleric", "", 1, 2),
        ("death", "5.0", "TestCleric · Cleric", "", "", "", 1, 3),
        ("revive", "9.0", "TestCleric · Cleric", "", "", "", 1, 3),
        ("cast", "12.0", "Ice Queen", "Ice Ring", "around itself", "", 1, 2.5),
        ("cast", "14.0", "Ice Queen", "Meteor", "on the ground near TestSorc", "", 1, 2.5),
        ("cast", "16.0", "Ice Queen", "Chill", "at TestSorc", "", 1, 2.5),
        ("cast", "18.0", "Ice Queen", "127", "", "", 1, 2.5),
        ("spawn", "19.0", "Clone", "", "", "", 1, 3),
        ("cast", "20.0", "Clone", "Shatter", "", "", 2, 2.5),
        ("cast", "20.6", "Clone", "Shatter", "", "", 1, 2.5),
        ("hit", "21.0", "Clone", "Shard", "TestSorc · Sorcerer", "", 1, 2),
        ("cast", "24.0", "Ice Queen", "Lance", "", "", 1, 2.5),
        ("cast", "26.0", "Ice Queen", "Whirl", "", "", 1, 2.5),
        ("cast", "28.0", "Ice Queen", "Hail", "on the ground", "", 1, 2.5)]
    # a row before its time, while it shows (from its first to its last and its time to show), and after
    shatter = replay.event_rows()[10]
    assert shatter["last"] == 20.3
    assert [rp.Replay.event_state(shatter, t) for t in (19.9, 20.0, 22.7, 22.9)] == ["next", "now", "now", "past"]
    # a hit's skill unless it is the plain Attack
    assert [rp.Replay.hit_skill(h) for h in ({"skill_id": 1800000, "skill": "Swipe"}, {"skill": "Attack", "skill_id": 5}, {},
                                             {"skill_id": 2300101}, {"skill": "Shard", "skill_id": 2300101})] == [
        "", "", "", "2300101", "Shard"]
    # the measured areas, once given: by the skill, else by its caster's name and the skill; each with its words, and
    # shown as long as it stays
    assert replay.aoe_of(replay.casts[0]) is None
    replay.shapes = CATALOG
    assert replay.aoe_of(replay.casts[4]) is CATALOG["Ice Queen|127"] and replay.aoe_of({"source": "b1", "skill_id": 9}) is None
    assert [(r[1], r[5], r[7]) for r in rows() if r[0] == "cast"] == [
        ("2.0", "dash 4.0 m wide along its path for 3.0 s", pytest.approx(3.6)),
        ("12.0", "ring from 3.0 m to 9.0 m around the caster", 2.5),
        ("14.0", "2 wedges of 8.0 m around the caster, safe between them", 2.5),
        ("16.0", "trail 3.0 m wide along its path for 4.0 s, each part staying 3.0 s", 7),
        ("18.0", "90° cone 8.0 m long", 2.5),
        ("20.0", "circle of 6.5 m around the caster", 2.5),
        ("20.6", "circle of 6.5 m around the caster", 2.5),
        ("24.0", "line 20 m long, 6.0 m wide", 2.5),
        ("26.0", "360° cone 5.0 m long", 2.5),
        ("28.0", "circle of 3.0 m around the aim", 2.5)]
    # an older recording's positions have no view to scale an area to, nor casts or events to list
    log = json.loads(json.dumps(REVIEW_LOG))
    log["segments"][0]["positions"] = [{"t": 0, "entity": "b1", "x": 0.5, "y": 0.5}]
    log["segments"][0]["npc_casts"] = [{"t": 2.0, "source": "b1", "skill_id": 123}]
    older = _replay(log)
    older.shapes = CATALOG
    assert not older.ticked and older.ticks() == [] and older.event_rows() == []
    assert older.aoe_of({"source": "b1", "skill_id": 123}) is None


def _near(points):
    """Points as near as floating point gives them."""
    return [pytest.approx(tuple(point)) for point in points]


def test_the_marks_at_a_moment():
    replay = _replay(_casting())
    replay.shapes = CATALOG
    scale = replay.scale

    def place(key, t):
        return pytest.approx(tuple(replay.place(replay.tokens[key], t)[:2]))

    def view(x, y):
        return replay.at({"x": x, "y": y})[:2]

    def marks(t, kind=None):
        return [m for m in replay.marks(t) if kind is None or m["kind"] == kind]

    def xy(m):
        return m["x"], m["y"]
    # A cast as it happens: its area (here the skill's dash, the boss's way from the cast to 3 s after it), a ring on the
    # boss, a wedge the way it faced (north), a line to where it was aimed and a marker there.
    area, ring, face, aimline, aim = marks(2.0)
    assert [m["kind"] for m in (area, ring, face, aimline, aim)] == ["area", "castring", "face", "aimline", "aim"]
    title = "Ice Queen: Frost Nova at TestCleric · 2.0s"
    assert (area["shape"], area["opacity"], area["width"]) == ("path", 0.9, pytest.approx(2 * scale(200)))
    assert area["points"] == [place("b1", 2.0), pytest.approx(view(10400, 20000)), place("b1", 5.0)]
    assert area["tip"] == f"{title} · measured dash 4.0 m wide along its path for 3.0 s (measured, 10 casts, 100% of the positions explained)"
    assert (xy(ring), ring["r"], ring["alpha"], ring["tip"]) == (place("b1", 2.0), 3.2, 1.0, title)
    x, y = ring["x"], ring["y"]
    assert face["points"] == _near([(x, y), (x + 9 * math.cos(math.radians(60)), y - 9 * math.sin(math.radians(60))),
                                    (x + 9 * math.cos(math.radians(120)), y - 9 * math.sin(math.radians(120)))])
    assert (face["alpha"], face["tip"]) == (0.25, "")
    assert ((aimline["x1"], aimline["y1"]), (aimline["x2"], aimline["y2"]), aimline["tip"]) == ((x, y), view(11220, 21010), "")
    assert (xy(aim), aim["r"], aim["tip"]) == (view(11220, 21010), 2.0, title)
    # growing and fading over 2.5 s; the dash fading 0.6 s once the boss is through it
    later = {m["kind"]: m for m in marks(3.0)}
    assert (later["castring"]["r"], later["castring"]["alpha"], later["face"]["alpha"], later["aim"]["r"]) == (
        pytest.approx(4.4), pytest.approx(0.6), pytest.approx(0.15), pytest.approx(3.0))
    assert xy(later["castring"]) == place("b1", 3.0)                          # on the boss where it is now
    assert [m["kind"] for m in marks(5.3) if m["tip"].startswith(title)] == ["area"]
    assert marks(5.3, "area")[0]["opacity"] == pytest.approx(0.45) and not marks(5.7, "area")
    # an enemy's appearance, ringed where it appeared for 3 s
    spawn, = marks(5.0, "spawn")
    assert (xy(spawn), spawn["r"], spawn["alpha"], spawn["tip"]) == (
        view(11100, 21100), pytest.approx(5.5), pytest.approx(0.5), "Clone appeared here at 3.5s")
    assert not marks(6.6, "spawn")
    # a clone's hit, where the player stood as it struck; a death's ✕ where they fell, until revived; the revive's ring
    hit, = marks(5.0, "hit")
    assert (xy(hit), hit["r"], hit["alpha"], hit["tip"]) == (place("p2", 4.0), 4.0, 0.5, "Clone hit TestCleric · Cleric · 4.0s")
    death, = marks(8.9, "death")
    spot = replay.place(replay.tokens["p2"], 5.0)
    assert (xy(death), death["tip"]) == ((spot[0], spot[1] + 2.1), "TestCleric died here at 5.0s")
    assert not marks(9.0, "death")
    revive, = marks(10.5, "revive")
    assert (xy(revive), revive["r"], revive["alpha"], revive["tip"]) == (
        place("p2", 10.5), pytest.approx(4.4), pytest.approx(0.5), "TestCleric revived at 9.0s")
    assert not marks(12.1, "revive")
    assert marks(21.0, "hit")[0]["tip"] == "Clone hit TestSorc · Sorcerer · Shard · 21.0s"
    # The areas: a ring around where the boss last stood when it cast (its position at 8 s), not where it is drawn now
    ring, = marks(12.5, "area")
    assert (ring["shape"], xy(ring), ring["opacity"]) == ("ring", view(10400, 20400), pytest.approx(0.6))
    assert (ring["r"], ring["width"]) == (pytest.approx((scale(900) + scale(300)) / 2), pytest.approx(scale(900) - scale(300)))
    assert xy(marks(12.5, "castring")[0]) == place("b1", 12.5) != view(10400, 20400)
    # wedges either side of the way to a distant aim (the cast holds no facing), the gap between them left out
    wedges, = marks(14.0, "area")
    facing = math.degrees(math.atan2(19600 - 20400, 9400 - 10000))
    assert (wedges["shape"], xy(wedges), wedges["r"], wedges["inner"]) == ("wedges", view(10000, 20400), pytest.approx(scale(800)), 0)
    assert wedges["wedges"] == [{"from": pytest.approx(facing - 60), "sweep": 30}, {"from": pytest.approx(facing + 30), "sweep": 30}]
    # a trail: where the boss passed in the last 3 s of its 4 s span, then the part still staying
    assert marks(17.0, "area")[0]["points"] == [place("b1", 16.0), place("b1", 17.0)]
    trail, = [m for m in marks(21.0, "area") if m["shape"] == "path"]
    assert (trail["points"], trail["width"]) == ([place("b1", 18.0), place("b1", 20.0)], pytest.approx(2 * scale(150)))
    assert not [m for m in marks(23.5, "area") if m["shape"] == "path"]
    # a cone the way the boss's position faced (north-east), for the skill measured by its name
    cone = marks(18.0, "area")[-1]
    assert (cone["shape"], xy(cone), cone["from"], cone["sweep"], cone["r"]) == ("cone", view(10000, 20000), 0, 90, pytest.approx(scale(800)))
    assert cone["tip"] == "Ice Queen: 127 · 18.0s · measured 90° cone 8.0 m long (tentative, 4 casts)"
    # a circle around each clone where it stood at the skill's hit (1.2 s on), fading over 2.2 s
    first, second, third = [m for m in marks(21.0, "area") if m["shape"] == "circle"]
    assert (xy(first), first["r"], first["opacity"]) == (view(11100, 21100), pytest.approx(scale(650)), pytest.approx(0.9 * (1 - 1 / 2.2)))
    assert (xy(second), second["opacity"]) == (view(10800, 20800), pytest.approx(0.9 * (1 - 0.7 / 2.2)))
    assert (xy(third), third["opacity"]) == (xy(first), pytest.approx(0.9 * (1 - 0.4 / 2.2)))
    # a line ahead of the boss, east; a cone all round drawn as a circle; a circle at an aim beyond the view, at its edge
    line, = marks(24.0, "area")
    (bx, by), long, half = view(10400, 20000), scale(2000), scale(300)
    assert line["shape"] == "polygon" and line["points"] == _near([(bx, by + half), (bx + long, by + half),
                                                                  (bx + long, by - half), (bx, by - half)])
    whirl, = marks(26.0, "area")
    assert (whirl["shape"], xy(whirl), whirl["r"]) == ("circle", (bx, by), pytest.approx(scale(500)))
    hail, = marks(28.0, "area")
    assert (hail["shape"], xy(hail), hail["r"]) == ("circle", (99, 1), pytest.approx(scale(300)))
    # an area that needs a facing none is known for draws nothing; without the catalog no area is drawn
    replay.shapes = {**CATALOG, "124": {"shape": "cone", "radius": 800.0, "angle": 45.0}}
    assert [m["kind"] for m in marks(12.2)] == ["castring", "aimline", "aim"]
    replay.shapes = None
    assert not marks(14.0, "area") and [m["kind"] for m in marks(14.0)] == ["castring", "aimline", "aim", "castring", "aimline", "aim"]


def test_the_arena_draws_the_marks(qapp):
    arena = Arena()
    arena.resize(800, 320)
    marks = [{"kind": "area", "shape": "circle", "x": 30, "y": 30, "r": 10, "opacity": 0.9, "tip": "Boss: Nova · measured"},
             {"kind": "castring", "x": 70, "y": 30, "r": 4, "alpha": 1.0, "tip": "Boss: Nova"},
             {"kind": "aimline", "x1": 74, "y1": 30, "x2": 90, "y2": 30, "alpha": 1.0, "tip": ""},
             {"kind": "area", "shape": "wedges", "x": 50, "y": 75, "r": 20, "inner": 0, "opacity": 0.9, "tip": "Boss: Meteor",
              "wedges": [{"from": 30, "sweep": 30}, {"from": 120, "sweep": 30}]},
             {"kind": "death", "x": 20, "y": 72.1, "alpha": 1.0, "tip": "Cleric died here at 5.0s"}]
    arena.show_moment([], None, marks)
    left, top, unit = arena.view()

    def tip(x, y):
        return arena.tip_at(left + x * unit, top + y * unit)
    # a filled area anywhere inside it, a ring on its line only, a mark without a tip never, a wedge inside it but not in
    # the safe gap beside it, and a death's ✕
    assert (tip(30, 30), tip(38, 30)) == ("Boss: Nova · measured", "Boss: Nova · measured")
    assert (tip(74, 30), tip(70, 30), tip(85, 30)) == ("Boss: Nova", "", "")
    at = (50 + 15 * math.cos(math.radians(45)), 75 - 15 * math.sin(math.radians(45)))
    gap = (50 + 15 * math.cos(math.radians(90)), 75 - 15 * math.sin(math.radians(90)))
    assert (tip(*at), tip(*gap)) == ("Boss: Meteor", "")
    assert (tip(20, 70), tip(20, 76)) == ("Cleric died here at 5.0s", "")
    # drawn under the tokens: the area's red over the ground, the ✕ in the text's light colour
    image = arena.grab().toImage()
    red = image.pixelColor(int(left + 30 * unit), int(top + 30 * unit))
    assert red.red() > red.green() + 20
    assert max(image.pixelColor(int(left + 20 * unit), int(top + y * unit)).lightness() for y in (69, 69.5, 70, 70.5)) > 120
    # how each mark is drawn, as the replay's styles draw it: an aim filled a third as clear as its edge; a dash's band
    # with round ends under its dashed way
    (_path, pen, fill, opacity), = mark_drawing({"kind": "aim", "x": 1, "y": 1, "r": 2, "alpha": 0.5, "tip": ""})
    assert (pen.widthF(), pen.color().alphaF(), fill.alphaF(), opacity) == (0.5, pytest.approx(0.5, abs=0.01),
                                                                            pytest.approx(0.175, abs=0.01), 1.0)
    band, way = mark_drawing({"kind": "area", "shape": "path", "points": [(0, 0), (5, 0)], "width": 4, "opacity": 0.45, "tip": ""})
    assert (band[1].widthF(), band[1].capStyle(), band[1].color().alphaF(), band[3]) == (4, Qt.RoundCap, pytest.approx(0.3, abs=0.01), 0.45)
    assert (way[1].widthF(), way[1].dashPattern(), way[1].capStyle()) == (0.4, [pytest.approx(3.0), pytest.approx(2.0)], Qt.RoundCap)
    # a hit: a fading ring, and a dot whose edge stays
    ring, dot = mark_drawing({"kind": "hit", "x": 1, "y": 1, "r": 3, "alpha": 0.4, "tip": ""})
    assert (ring[2], dot[1].color().alphaF(), dot[2].alphaF()) == (None, 1.0, pytest.approx(0.4, abs=0.01))


def _drawn(view) -> bool:
    """The log's page drawn with all it asked for: the replay, the encounter's parses (drawn again as they come) and
    any picture it waits for."""
    return view.replay is not None and view.ranks is not None and not view.awaiting


def _rows(panel):
    """Each row of the list as read out: its time and words."""
    _shown()
    model = panel.events.model
    return [model.data(model.index(i), Qt.AccessibleTextRole) for i in range(model.rowCount())]


def _edge(panel, row):
    """The colour of a row's left edge as drawn."""
    _shown()
    view = panel.events.view
    image = view.viewport().grab().toImage()
    return image.pixelColor(1, view.visualRect(panel.events.model.index(row)).center().y())


def test_the_casts_and_events_beside_the_arena(qapp, tmp_path):
    app = FakeApp()
    app.log_server.review_log = _casting()
    page = _page(app, store=_store(tmp_path))
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: _drawn(view))
    panel = view.replay
    events = panel.events
    _shown()
    # beside the arena, as tall; its head; a row for each cast and event, in time order
    assert panel.body.direction() == QBoxLayout.LeftToRight and events.height() == panel.arena.height() == 320
    assert panel.body.indexOf(panel.arena) == 0 and panel.body.indexOf(events) == 1 and events.isVisibleTo(view)
    head = events.findChildren(QLabel, "crEventsHead")[0]
    assert "Casts and events" in head.text() and rp.EVENTS_HINT in head.text()
    assert _rows(panel)[:6] == ["2.0s Ice Queen: Frost Nova at TestCleric", "3.5s Clone appeared",
                                "4.0s Clone hit TestCleric · Cleric", "5.0s TestCleric · Cleric died",
                                "9.0s TestCleric · Cleric revived", "12.0s Ice Queen: Ice Ring around itself"]
    assert _rows(panel)[10:13] == ["20.0s Clone: Shatter ×2", "20.6s Clone: Shatter", "21.0s Clone hit TestSorc · Sorcerer · Shard"]
    # the slider's ticks, in tenths of a second
    assert panel.scrub.ticks == [20, 120, 140, 160, 180, 200, 203, 206, 240, 260, 280, 35, 190, 50, 90, 40, 210]
    # at the start every row is to come; a moment chosen marks the rows reached, those in progress among them, drawn
    # with an edge (an appearance's green, any other's gold, as the web page draws them), the rest without
    model, rows = events.model, events.view
    assert set(model.states) == {"next"}
    panel.scrub.setValue(46)
    assert model.states[:4] == ["past", "now", "now", "next"] and set(model.states[4:]) == {"next"}
    assert [model.data(model.index(i), STATE_ROLE) for i in range(4)] == ["past", "now", "now", "next"]
    spawn, hit, past = _edge(panel, 1), _edge(panel, 2), _edge(panel, 0)
    assert spawn.green() > spawn.red() + 40 and (hit.red(), hit.green(), hit.blue()) == (240, 192, 80) and past.lightness() < 60
    # a row chosen with the pointer goes to its time, paused; with Enter or Space too
    _click(view, "Play")
    QTest.mouseClick(rows.viewport(), Qt.LeftButton, Qt.NoModifier, rows.visualRect(model.index(7)).center())
    assert not panel.playing() and panel.clock == 16.0 and panel.scrub.value() == 160 and panel.clock_label.text() == "16.0s"
    assert model.states[5:9] == ["past", "now", "now", "next"] and set(model.states[:5]) == {"past"}
    rows.setCurrentIndex(model.index(9))
    QTest.keyClick(rows, Qt.Key_Return)
    assert panel.clock == 19 and model.states[9] == "now"
    rows.setCurrentIndex(model.index(2))
    QTest.keyClick(rows, Qt.Key_Space)
    assert panel.clock == 4.0 and model.states[2:4] == ["now", "next"] and set(model.states[4:]) == {"next"}
    # the list follows the replay: the row reached brought into view a third of the way down, and back at the start
    bar = rows.verticalScrollBar()
    panel.scrub.setValue(280)
    _shown()
    last = rows.visualRect(model.index(model.rowCount() - 1))
    assert bar.maximum() > 0 and bar.value() > 0
    assert last.top() >= 0 and last.bottom() < rows.viewport().height()
    assert model.states[-1] == "now" and set(model.states[:-3]) == {"past"}
    _click(view, "Rewind")
    assert bar.value() == 0 and set(model.states) == {"next"}
    # The measured areas come once the app gives them: the rows name them; the page asks for them once.
    assert app.calls.count("/static/aoe-shapes.json") == 1 and view.aoe_shapes is None
    app.aoe_shapes = {"shapes": CATALOG}
    page.open_review("local", "session-1.a2log.json")
    settle(lambda: _drawn(view) and view.replay is not panel)
    assert app.calls.count("/static/aoe-shapes.json") == 1 and view.replay.replay.shapes is None
    view.aoe_shapes = None
    view.asked.pop("aoe")                                               # as a page opened anew would ask
    page.open_review("local", "session-1.a2log.json")
    settle(lambda: view.aoe_shapes is not None and _drawn(view))
    panel = view.replay
    assert panel.replay.shapes == CATALOG
    assert _rows(panel)[0] == "2.0s Ice Queen: Frost Nova at TestCleric · dash 4.0 m wide along its path for 3.0 s"
    # given after the replay was drawn: the list and the moment drawn again with them
    panel.set_shapes(None)
    assert _rows(panel)[0] == "2.0s Ice Queen: Frost Nova at TestCleric"
    panel.scrub.setValue(30)
    assert not [m for m in panel.arena.marks if m["kind"] == "area"]
    panel.set_shapes(CATALOG)
    assert _rows(panel)[5] == "12.0s Ice Queen: Ice Ring around itself · ring from 3.0 m to 9.0 m around the caster"
    assert [m["shape"] for m in panel.arena.marks if m["kind"] == "area"] == ["path"] and panel.clock == 3.0
    # narrow, under the arena and shorter
    panel.resize(NARROW - 1, panel.height())
    assert panel.body.direction() == QBoxLayout.TopToBottom and panel.events.height() == 220
    panel.resize(NARROW + 200, panel.height())
    assert panel.body.direction() == QBoxLayout.LeftToRight and panel.events.height() == 320
    assert panel.events.width() == max(260, int((NARROW + 200) * 0.34))


def test_a_fight_without_casts_or_events(qapp, tmp_path):
    log = json.loads(json.dumps(REVIEW_LOG))
    log["segments"][0]["movement"] = [_at(0, "b1", 10000, 20000), _at(4, "b1", 10400, 20000), _at(0.5, "p1", 9000, 19000)]
    replay = _replay(log)
    assert not replay.ticked and replay.event_rows() == [] and replay.marks(5) == []
    app = FakeApp()
    app.log_server.review_log = log
    page = _page(app, store=_store(tmp_path))
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: view.replay is not None and not view.awaiting)
    panel = view.replay
    assert panel.events is None and panel.scrub.ticks == [] and panel.body.count() == 1


def test_the_keys_entries():
    replay = _replay(_casting())
    sorcerer, cleric = class_colour("sorcerer", {}), class_colour("cleric", {})
    entries = [(item["key"], item["text"]) for item in replay.key()]
    assert entries == [("boss", "Boss"), (None, "Recording player"), ("pet", "Pet or summon, in its owner's class colour"),
                       ("add", rp.ADD_KEY), ("enemy", "Other enemy"), ("trail", "Movement in the last 6 seconds"),
                       (None, rp.FADED_KEY), ("arena", "Arena"), ("casts", rp.CAST_KEY), ("spawns", rp.SPAWN_KEY),
                       ("lives", rp.LIVES_KEY), ("hits", rp.HITS_KEY)]
    assert replay.key()[1]["swatch"] == ("dot", sorcerer, 3, True, 1.0)            # the recording player, ringed
    assert rp.FADED_KEY.startswith("Faded: last seen over 8 seconds ago") and "unseen for 20 seconds" in rp.FADED_KEY
    # the measured areas' entries once the catalog has the skills; the dash, trail and wedges' when it has them
    replay.shapes = CATALOG
    keys = [item["key"] for item in replay.key()]
    assert keys[keys.index("casts") + 1:keys.index("spawns")] == ["aoe", None]
    assert replay.key()[keys.index("aoe") + 1]["text"] == rp.EXTRAS_KEY
    replay.shapes = {"131": CATALOG["131"]}
    assert [item["key"] for item in replay.key()][keys.index("casts") + 1] == "aoe" and rp.EXTRAS_KEY not in [
        item["text"] for item in replay.key()]
    # the players, the recording player first; with over twelve, their classes
    title, people = replay.key_people()
    assert title == "Players" and [(p["key"], p["text"], p["swatch"]) for p in people] == [
        ("id:p1", cw.actor_label(replay.r["p1"]) + " · Sorcerer", ("dot", sorcerer, 3, True, 1.0)),
        ("id:p2", "TestCleric · Cleric", ("dot", cleric, 3, False, 1.0))]
    log = _moving()
    many = [{"id": f"q{i}", "name": f"Ally{i:02d}", "class": ("templar", "ranger", "cleric")[i % 3]} for i in range(12)]
    log["players"] += many
    log["segments"][0]["movement"] += [_at(1, p["id"], 9000 + 10 * i, 19000) for i, p in enumerate(many)]
    title, people = _replay(log).key_people()
    assert title == "Classes" and [(p["key"], p["text"]) for p in people] == [
        ("class:cleric", "Cleric"), ("class:ranger", "Ranger"), ("class:sorcerer", "Sorcerer"), ("class:templar", "Templar")]
    # an older recording's positions: neither trails nor the arena
    older = json.loads(json.dumps(REVIEW_LOG))
    older["segments"][0]["positions"] = [{"t": 0, "entity": "b1", "x": 0.5, "y": 0.5}]
    assert [item["key"] for item in _replay(older).key()] == ["boss", None]


def test_the_key_hides_what_it_names():
    replay = _replay(_casting())
    replay.shapes = CATALOG

    def tokens(t):
        return {token["id"]: token for token in replay.frame(t)}

    def kinds(t):
        return [m["kind"] for m in replay.marks(t)]

    def rows():
        return [(e["kind"], rp.fixed(e["t"], 1)) for e in replay.event_rows()]
    every = rows()
    # a player by their own entry or their class's: their token, death, revive and the hit on them
    for hidden in ({"id:p2"}, {"class:cleric"}):
        replay.hidden.clear()
        replay.hidden.update(hidden)
        assert "p2" not in tokens(4.5) and "hit" not in kinds(4.5) and "death" not in kinds(6) and "revive" not in kinds(10)
        assert [r for r in every if r not in rows()] == [("hit", "4.0"), ("death", "5.0"), ("revive", "9.0")]
    # a kind: the bosses' tokens and casts; the adds' tokens, casts and appearances, not the hits on players
    replay.hidden.clear()
    replay.hidden.add("boss")
    assert "b1" not in tokens(2) and kinds(2) == [] and all(r[0] != "cast" or r[1] in ("20.0", "20.6") for r in rows())
    replay.hidden.clear()
    replay.hidden.add("add")
    assert "a1" not in tokens(4) and "spawn" not in kinds(4) and "hit" in kinds(4)
    assert [r for r in every if r not in rows()] == [("spawn", "3.5"), ("spawn", "19.0"), ("cast", "20.0"), ("cast", "20.6")]
    # the trails; the casts; their areas alone; the appearances; the deaths and revives (no player greyed); the hits
    replay.hidden.clear()
    replay.hidden.add("trail")
    assert all(token["trail"] == [] for token in replay.frame(6))
    replay.hidden.clear()
    replay.hidden.add("casts")
    assert {"castring", "area", "aim"}.isdisjoint(kinds(2)) and [r for r in rows() if r[0] == "cast"] == []
    replay.hidden.clear()
    replay.hidden.add("aoe")
    assert "area" not in kinds(2) and "castring" in kinds(2)
    assert {e["area"] for e in replay.event_rows()} == {""} and replay.event_rows()[0]["show"] == rp.CAST_SHOW
    replay.hidden.clear()
    replay.hidden.update({"spawns", "lives", "hits"})
    assert {"spawn", "death", "revive", "hit"}.isdisjoint(kinds(4.5) + kinds(6) + kinds(10))
    assert tokens(6)["p2"]["opacity"] == 1.0 and {r[0] for r in rows()} == {"cast"}


def test_the_key_on_a_logs_page(qapp, tmp_path):
    from aion2calc.gui.combat_replay_view import KeyEntry, swatch_pixmap
    app = FakeApp()
    app.log_server.review_log = _casting()
    page = _page(app, store=_store(tmp_path))
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: _drawn(view))
    panel = view.replay
    _shown()
    key = panel.key
    labels = _labels(view)
    assert rp.KEY_HEAD in "".join(labels) and rp.KEY_NOTE in labels and not key.show_all.isVisible()
    assert panel.parentWidget() is not None and key.isVisibleTo(view)
    entries = {e.item["text"]: e for e in key.findChildren(KeyEntry)}
    assert [e.item["text"] for e in key.entries][:3] == ["Boss", "Recording player", "Pet or summon, in its owner's class colour"]
    assert entries["Recording player"].box is None and entries["Boss"].box.isChecked()
    # unticked: hidden on the replay, the entry dimmed and struck through, Show all offered
    boss = entries["Boss"]
    QTest.mouseClick(boss.words, Qt.LeftButton)                     # anywhere on the entry, as on its label
    assert not boss.box.isChecked() and view.replay_hidden == {"boss"} and key.show_all.isVisibleTo(view)
    assert boss.words.font().strikeOut() and boss.graphicsEffect() is not None
    assert "b1" not in {t["id"] for t in panel.arena.tokens}
    rows = _rows(panel)
    assert not any(r.startswith("2.0s Ice Queen") for r in rows) and rows[0] == "3.5s Clone appeared"
    # the arena: none while unticked; the key's swatch in the shape chosen
    entries["Arena"].box.setChecked(False)
    assert panel.arena.room is None and view.replay_hidden == {"boss", "arena"}
    shape = _find(view, QComboBox, lambda c: c.accessibleName() == "Arena")
    shape.setCurrentIndex(1)
    shape.activated.emit(1)
    room = next(s for s, part in entries["Arena"].swatches if part == ("room",))

    def drawn(shape):
        probe = QLabel()
        probe.setPixmap(swatch_pixmap(("room",), shape))
        return probe.pixmap().toImage()
    assert room.pixmap().toImage() == drawn("square") != drawn("circle")
    # kept while the page is drawn again; Show all ticks every entry again
    view.draw()
    _shown()
    panel, key = view.replay, view.replay.key
    assert {e.item["key"] for e in key.entries if e.box is not None and not e.box.isChecked()} == {"boss", "arena"}
    assert "b1" not in {t["id"] for t in panel.arena.tokens} and panel.arena.room is None
    _click(view, rp.SHOW_ALL)
    assert view.replay_hidden == set() and all(e.box.isChecked() for e in key.entries if e.box is not None)
    assert not key.show_all.isVisibleTo(view) and panel.arena.room is not None and "b1" in {t["id"] for t in panel.arena.tokens}
    # every cast and event hidden: the list says so
    for key_ in ("casts", "spawns", "lives", "hits"):
        next(e for e in key.entries if e.item["key"] == key_).box.setChecked(False)
    _shown()
    assert panel.events.none.isVisibleTo(view) and panel.events.none.text() == rp.NO_EVENTS
    assert not panel.events.view.isVisibleTo(view) and panel.events.model.rowCount() == 0
    _click(view, rp.SHOW_ALL)
    assert panel.events.model.rowCount() == 16 and not panel.events.none.isVisibleTo(view)
    # a player's entry; the key as it starts for another log
    players = {e.item["key"]: e for e in key.entries if e.item["key"] and e.item["key"].startswith("id:")}
    players["id:p2"].box.setChecked(False)
    assert "p2" not in {t["id"] for t in panel.arena.tokens} and view.replay_hidden == {"id:p2"}
    page.open_review("local", "session-1.a2log.json")
    settle(lambda: _drawn(view) and view.replay is not panel)
    assert view.replay_hidden == set() and view.replay.replay.hidden is view.replay_hidden


def _merged(log) -> dict:
    """The log server's merge of the fight's movement with its other public recordings (made up): this recording's
    movement and another's, which holds the recording player's own; a third left out."""
    movement = json.loads(json.dumps(log["segments"][0].get("movement") or []))
    movement += [_at(2, "p1", 9100, 19000, via=1), _at(4, "p1", 9300, 19100, via=1)]
    return {"movement": movement, "note": "Clocks matched by shared hits.",
            "sources": [{"log": "log0001", "uploader": "Uploader A"},
                        {"log": "log0002", "uploader": "Uploader B", "offset": 0.5, "shared_hits": 1234, "positions": 300},
                        {"log": "log0003", "skipped": "another fight"}]}


def test_other_recordings_movement(qapp, tmp_path):
    from PySide6.QtWidgets import QPushButton
    app = FakeApp()
    log = _moving()
    app.log_server.review_log = log
    page = _page(app, store=_store(tmp_path))
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: _drawn(view))
    asked = app.log_server.asked
    # a shared log's replay offers the merge; asked for, it says so while the log server is asked
    assert rp.MERGE in _buttons(view) and not any("/movement" in a for a in asked)
    _click(view, rp.MERGE)
    waiting = next(b for b in view.replay.findChildren(QPushButton) if b.text() == rp.MERGING)
    assert not waiting.isEnabled()
    # refused: why, and the merge offered again
    settle(lambda: "/api/v1/logs/log0001/movement?segment=0" in asked and rp.MERGE in _buttons(view))
    assert any("no other public recording of this fight" in label for label in _labels(view))
    # merged: the other recordings' movement on the replay, what each gave, and no button
    app.log_server.movement = _merged(log)
    _click(view, rp.MERGE)
    settle(lambda: view.replay is not None and view.replay.replay.merged is not None)
    replay = view.replay.replay
    assert rp.MERGE not in _buttons(view) and rp.MERGING not in _buttons(view)
    assert replay.sources_note() == (
        f"Merged with 1 of 2 other recordings of this fight: Uploader B's recording (clock +0.50 s from {cw.number(1234)} shared "
        "hits, 300 positions); Anonymous's recording (another fight). Clocks matched by shared hits.")
    labels = _labels(view)
    assert replay.sources_note() in labels and replay.note.endswith(
        "comes from 2 positions in the other recordings of this fight; 3 more are where they applied an effect or a cast "
        "aimed at them.")
    me = next(token for token in replay.frame(2) if token["id"] == "p1")
    assert me["tip"].endswith("· move at 2.0s · from Uploader B's recording")
    assert (replay.source_name(2), replay.source_name(9), replay.source_name("1")) == (
        "Anonymous's recording", "another recording", "another recording")
    assert asked.count("/api/v1/logs/log0001/movement?segment=0") == 2
    # the log server's combined fight shares the merged movement
    app.log_server.combined = json.loads(json.dumps(log))
    app.log_server.combined["meta"]["combined"] = {"note": "Two recordings joined.", "sources": [
        {"log": "log0001", "uploader": "Uploader A"}, {"log": "log0002", "uploader": "Uploader B", "offset": 0.5}]}
    del app.log_server.combined["segments"][0]["movement"]
    view._view_combined()                                           # **Combine all N recordings of this fight**
    settle(lambda: view.fight["own"] is not None and _drawn(view))
    assert view.replay.replay.merged is replay.merged and rp.MERGE not in _buttons(view)
    # another party member's upload named by the parses: merged unasked, once
    app = FakeApp()
    app.log_server.review_log = log
    app.log_server.ranks = {**REVIEW_RANKS, "shared_uploads": [{"log": "log0002", "uploader": "Uploader B", "created_at": T0}]}
    app.log_server.movement = _merged(log)
    page = _page(app, store=_store(tmp_path))
    page.open_review("shared", "log0001")
    view = page.review_page
    settle(lambda: view.replay is not None and view.replay.replay.merged is not None and _drawn(view))
    view.draw()
    _shown()
    assert app.log_server.asked.count("/api/v1/logs/log0001/movement?segment=0") == 1 and view.replay.replay.merged
    # a recording here is not offered it
    app = FakeApp()
    app.log_server.review_log = log
    page = _page(app, store=_store(tmp_path))
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: _drawn(view))
    assert rp.MERGE not in _buttons(view)


def test_movement_from_other_recordings_alone(qapp, tmp_path):
    app = FakeApp()
    app.log_server.movement = _merged(_moving())
    page = _page(app, store=_store(tmp_path))
    page.open_review("shared", "log0001")                            # the review log: no movement of its own
    view = page.review_page
    settle(lambda: view.doc is not None and view.ranks is not None and not view.awaiting)
    assert rp.NO_MOVEMENT + rp.MAY_HOLD in _labels(view) and rp.MERGE in _buttons(view) and view.replay is None
    _click(view, rp.MERGE)
    settle(lambda: view.replay is not None and view.replay.replay.merged is not None)
    assert view.replay.replay.world and rp.MERGE not in _buttons(view)
    # merged, and none of the recordings held movement: said so, with what each gave
    app.log_server.movement = {**_merged(_moving()), "movement": []}
    page.open_review("shared", "log0001")
    settle(lambda: view.doc is not None and view.ranks is not None and not view.awaiting)
    _click(view, rp.MERGE)
    settle(lambda: view.replay is None and rp.NO_MOVEMENT in _labels(view))
    labels = _labels(view)
    assert rp.NO_MOVEMENT + rp.MAY_HOLD not in labels and any(label.startswith("Merged with 1 of 2") for label in labels)


# ------------------------------------------------------------------ the replay as a Raid Planner plan (0.2.492)
def test_the_replay_and_a_recordings_fight_as_raid_planner_plans():
    from aion2calc.gui import builds as b
    log = _casting()
    replay = _replay(log, {"enabled": False})
    replay.shapes = CATALOG
    plan = json.loads(b.stringify(replay.plan("square")))
    assert {k: plan[k] for k in ("format", "version", "meta", "duration", "arena", "buffs")} == {
        "format": "a2plan", "version": 1, "meta": {"name": "Ice Queen"}, "duration": 120, "arena": {"kind": "square"},
        "buffs": []}
    actors = {t["id"]: t for t in plan["tokens"] if t["kind"] != "aoe"}
    # each that moved: on the map from its first place (a clone that came mid-fight) to 8 s after its last
    assert [(k, t["kind"], t.get("from"), t.get("until"), len(t["keyframes"])) for k, t in actors.items()] == [
        ("b1", "enemy", None, 68, 7), ("p1", "player", None, 38, 3), ("p2", "player", None, 17.5, 4),
        ("pet1", "player", None, 11, 2), ("a1", "enemy", 3.5, 11.5, 1), ("w1", "enemy", None, 18, 2),
        ("a2", "enemy", 19, 27, 1)]
    assert actors["p1"]["label"] == "TestSorc ✓ · Zikel" and actors["p1"]["cls"] == "sorcerer" and actors["p1"]["color"] == GOLD
    assert "cls" not in actors["b1"] and actors["pet1"]["cls"] == "sorcerer"      # a pet in its owner's class
    assert actors["w1"]["keyframes"][0] == {"t": 0, "x": 1, "y": 0}               # beyond the arena: at its corner
    # the boss casts' measured areas, each where and for as long as the replay draws it
    areas = [t for t in plan["tokens"] if t["kind"] == "aoe"]
    assert [(a["shape"], a["from"], a["until"]) for a in areas] == [
        ("line", 2, 5.6), ("ring", 12, 13.5), ("cone", 14, 15.5), ("cone", 14, 15.5), ("line", 16, 23), ("cone", 18, 19.5),
        ("circle", 20, 22.2), ("circle", 20.3, 22.5), ("circle", 20.6, 22.8), ("line", 24, 25.5), ("circle", 26, 27.5),
        ("circle", 28, 30)]
    assert areas[1] == {"id": "aoe:1", "kind": "aoe", "label": "Ice Queen: Ice Ring", "color": "#f06060", "shape": "ring",
                        "radius": 0.3719, "inner": 0.124, "from": 12, "until": 13.5,
                        "keyframes": [{"t": 12, "x": 0.6239669421487604, "y": 0.37603305785123964}]}
    assert (areas[2]["angle"], areas[2]["facing"], areas[3]["facing"]) == (15, -171.9, -81.9)       # wedges either side
    assert areas[5]["label"] == "Ice Queen: 127" and areas[5]["facing"] == 45                        # by the boss's name
    # what the key hides: a token kept but hidden; the areas with the casts
    replay.hidden.update({"pet", "casts"})
    hidden = replay.plan("circle")
    assert [t["id"] for t in hidden["tokens"] if t.get("hidden")] == ["pet1"] and hidden["arena"] == {"kind": "circle"}
    assert not [t for t in hidden["tokens"] if t["kind"] == "aoe"]
    # an older recording's positions, already on the view: the whole view, square, no areas
    old = _moving()
    fight = old["segments"][0]
    fight["positions"] = [{"t": 1, "entity": "b1", "x": 0.5, "y": 0.25}, {"t": 2, "entity": "p1", "x": 1.2, "y": -0.1}]
    del fight["movement"]
    flat = rp.Replay(old, cw.data(old, cw.fresh_state()), {}, {}).plan("circle")
    assert flat["arena"] == {"kind": "square"}
    assert [t["keyframes"] for t in flat["tokens"]] == [[{"t": 1, "x": 0.5, "y": 0.25}], [{"t": 2, "x": 1, "y": 0}]]
    # the planner's import: the fights that hold movement, then one as a plan (the fight's own actors alone)
    assert rp.movement_fights(log) == [{"index": 0, "name": "Ice Queen", "duration": 120, "positions": 20, "boss": True}]
    imported = rp.movement_plan(log, 0, "circle", CATALOG, {})
    assert imported["arena"] == {"kind": "circle"} and len(imported["tokens"]) == 19
    assert [t["label"] for t in imported["tokens"] if t["kind"] != "aoe"][5] == "Unknown / not recorded"   # the wolf did nothing
    with pytest.raises(ValueError, match=rp.NO_FIGHT_MOVEMENT):
        rp.movement_plan(log, 3, "circle")
    # Math.hypot as V8 works it out (Python's own differs in the last place here)
    assert rp.js_hypot(2398.985747399307, 4223.24996665417) == 4857.053931867491
    assert rp.js_hypot(3, 4) == 5 and rp.js_hypot(math.nan, math.inf) == math.inf and math.isnan(rp.js_hypot(1, math.nan))


def test_open_in_raid_planner_under_the_key(qapp, tmp_path):
    from aion2calc.gui import builds as b
    from aion2calc.gui.combat_replay_view import PLAN_EXPORT, PLAN_FILE, PLAN_OPEN, ReplayPanel
    from aion2calc.gui.raid import INVALID_REPLAY, PlanError
    app = FakeApp()
    app.log_server.review_log = _moving()
    opened = []
    page = _page(app, store=_store(tmp_path), open_replay=opened.append)
    page.open_review("local", "session-1.a2log.json")
    view = page.review_page
    settle(lambda: view.replay is not None and not view.awaiting)
    panel = view.replay
    assert panel.plan_button.text() == PLAN_OPEN
    _click(view, PLAN_OPEN)
    assert opened == [panel.replay.plan(panel.shape)] and opened[0]["meta"] == {"name": "Ice Queen"}

    def refuse(plan):
        raise PlanError(INVALID_REPLAY)
    panel.open_replay = refuse                                     # the planner refusing it: why, beside the button
    _click(view, PLAN_OPEN)
    assert panel.plan_status.text() == INVALID_REPLAY
    # without the planner: the replay's Raid Planner file, saved where asked
    asked = []
    alone = ReplayPanel(_replay(), _store(tmp_path), save_file=lambda name: asked.append(name) or str(tmp_path / "p.json"))
    assert alone.plan_button.text() == PLAN_EXPORT
    alone.plan_button.click()
    assert asked == [PLAN_FILE]
    assert (tmp_path / "p.json").read_text(encoding="utf-8") == b.stringify(alone.replay.plan(alone.shape))
