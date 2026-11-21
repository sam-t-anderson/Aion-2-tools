"""The native log review's movement replay (combat-review.js ``replay``), since 0.2.468: the view and its arena, the
tokens at a moment (their places, sides, kinds, colours, faded and gone, a player greyed while dead), the trails, and
the controls (Play and Pause, Rewind, the speed and the arena's shape kept, the time slider). Off screen over the
Combat Logs tests' fake app and log server (made-up logs and positions).
"""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QSlider  # noqa: E402

from aion2calc.gui import combat_replay as rp  # noqa: E402
from aion2calc.gui import combat_review as cw  # noqa: E402
from aion2calc.gui.combat_records import GOLD, class_colour  # noqa: E402
from aion2calc.gui.combat_replay_view import Arena  # noqa: E402
from test_native_combat import REVIEW_LOG, FakeApp, _click, _find, _labels, _page, _shown  # noqa: E402
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
