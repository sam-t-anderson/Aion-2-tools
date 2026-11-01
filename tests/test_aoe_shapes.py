"""Boss area-of-effect shapes measured from recordings (0.2.365): synthetic fights whose boss casts hit the players
standing inside a known shape, read back from the saved log's casts, damage events and movement."""
import math
import random

from aion2calc.combat import aoe

BOSS, PLAYERS = "e:boss", [f"p:{i}" for i in range(8)]


def _doc(casts, duration=300.0):
    """A one-segment log: the boss at the origin facing +x; players scattered each cast; ``casts`` yields
    (t, skill_id, aim, facing, hit_test) and the hit test says which player positions take the damage."""
    rng = random.Random(7)
    movement, events, npc_casts = [], [], []
    for t, skill_id, aim, facing, inside in casts:
        movement.append({"t": t - 0.5, "entity": BOSS, "x": 0.0, "y": 0.0, "z": 0.0, "src": "move", "heading": facing})
        for p in PLAYERS:
            x, y = rng.uniform(-900, 900), rng.uniform(-900, 900)
            movement.append({"t": t - 0.3, "entity": p, "x": x, "y": y, "z": 0.0, "src": "party"})
            movement.append({"t": t + 2.5, "entity": p, "x": x, "y": y, "z": 0.0, "src": "party"})
            if inside(x, y):
                events.append({"kind": "damage", "t": round(t + 1.2, 3), "source": BOSS, "target": p,
                               "skill_id": 1600000, "skill": "Attack", "amount": 1000.0})
        row = {"t": t, "source": BOSS, "skill_id": skill_id, "skill": f"Skill {skill_id}", "facing": facing}
        if aim is not None:
            row["pos"] = [aim[0], aim[1], 0.0]
        npc_casts.append(row)
    return {"format": "a2log", "version": 1, "players": [{"id": p, "name": p} for p in PLAYERS],
            "segments": [{"duration": duration, "entities": [{"id": BOSS, "name": "Testboss", "is_boss": True, "kind": "enemy"}],
                          "movement": movement, "events": events, "npc_casts": npc_casts, "hits": []}]}


def test_a_circle_around_the_aim_point_a_cone_and_a_line_are_told_apart_with_their_sizes():
    casts = []
    t = 5.0
    for i in range(14):                         # a circle of radius 400 around a ground-placed aim point
        ax, ay = 300.0 * math.cos(i), 300.0 * math.sin(i)
        casts.append((t, 1604390, (ax, ay), 0.0, lambda x, y, ax=ax, ay=ay: math.hypot(x - ax, y - ay) <= 400))
        t += 8
    for i in range(14):                         # a 90 degree cone, 700 long, facing +x
        casts.append((t, 1604400, None, 0.0, lambda x, y: math.hypot(x, y) <= 700 and abs(math.degrees(math.atan2(y, x))) <= 45))
        t += 8
    for i in range(14):                         # a line 100 wide and 800 long along the facing
        casts.append((t, 1604410, None, 0.0, lambda x, y: 0 <= x <= 800 and abs(y) <= 100))
        t += 8
    rows = {r["skill_id"]: r for r in aoe.measure([_doc(casts, duration=t + 10)])}
    circle, cone, line = rows[1604390], rows[1604400], rows[1604410]
    assert circle["shape"] == "circle_aim" and 330 <= circle["radius"] <= 470 and circle["confidence"] == "measured"
    assert circle["aim"] == {"ground": 1.0} and circle["delay"] == 1.2
    assert cone["shape"] == "cone" and cone["angle"] in (45, 60) and 600 <= cone["radius"] <= 800
    assert line["shape"] == "line" and line["half_width"] in (100, 150) and 700 <= line["length"] <= 900
    assert line["anchor"] == "cast" and line["moved"] == 0
    assert all(r["accuracy"] >= 0.9 for r in (circle, cone, line))


def test_a_single_target_melee_swing_is_not_an_area_and_thin_evidence_stays_insufficient():
    casts, t = [], 5.0
    rng = random.Random(3)
    for i in range(10):
        victim = rng.choice(PLAYERS)
        casts.append((t, 1604482, None, 0.0, None))
        t += 6
    doc = _doc([(c[0], c[1], c[2], c[3], lambda x, y: False) for c in casts], duration=t + 10)
    segment = doc["segments"][0]
    # the swing hits exactly the cast's target: one damage event per cast on that player, who is the cast's target
    for row in segment["npc_casts"]:
        victim = rng.choice(PLAYERS)
        row["target"] = victim
        segment["events"].append({"kind": "damage", "t": row["t"] + 0.6, "source": BOSS, "target": victim,
                                  "skill_id": 1600000, "skill": "Attack", "amount": 500.0})
    rows = aoe.measure([doc])
    swing = next(r for r in rows if r["skill_id"] == 1604482)
    assert swing["shape"] == "single_target" and swing["hits_per_cast"] == 1.0
    assert "1604482" not in aoe.catalog(rows)["shapes"]                     # not an area: nothing to draw
    thin = aoe.measure([_doc([(5.0, 1604500, (0.0, 0.0), 0.0, lambda x, y: math.hypot(x, y) <= 300)], duration=20)])
    assert thin[0]["confidence"] == "insufficient"


def test_the_catalog_keeps_the_drawable_shapes_and_the_report_lists_the_evidence():
    casts, t = [], 5.0
    for i in range(12):
        casts.append((t, 1604390, (0.0, 0.0), 0.0, lambda x, y: math.hypot(x, y) <= 500))
        t += 8
    rows = aoe.measure([_doc(casts, duration=t + 10)])
    cat = aoe.catalog(rows)
    assert "units" in cat["unit"] and cat["shapes"]["1604390"]["shape"] in ("circle_aim", "circle_caster")
    assert 420 <= cat["shapes"]["1604390"]["radius"] <= 580 and cat["shapes"]["1604390"]["boss"] == "Testboss"
    table = aoe.report(rows)
    assert "| Testboss | Skill 1604390 (1604390) |" in table and "measured" in table


def test_positions_interpolate_between_fixes_and_go_stale_after_a_gap():
    track = ([0.0, 2.0, 20.0], [(0.0, 0.0, 0.0, None), (2.0, 100.0, 0.0, 90.0), (20.0, 500.0, 0.0, None)])
    assert aoe.position(track, 1.0)[:2] == (50.0, 0.0)                      # between two fixes 2 s apart
    assert aoe.position(track, 5.0)[:2] == (100.0, 0.0)                     # the last fix, 3 s old, still places
    assert aoe.position(track, 10.0) is None                                # 8 s from either fix: unknown
    assert aoe.position(track, 19.0)[:2] == (500.0, 0.0)                    # a fix just ahead places too


def test_a_candidate_that_separates_exactly_backwards_does_not_crash_the_fit():
    """A threshold that keeps every unhit sample inside and every hit sample outside scores a balanced accuracy of
    exactly 0.0, which tied with the search's empty start and went on to compare a float with None: the log server's
    first pass over its 701 public recordings died of it (0.2.367). The fit now takes the first candidate outright."""
    from aion2calc.combat import aoe

    def sample(hit, d):
        return {"hit": hit, "target": False, "d_aim": d, "d_boss": d, "angle": None, "along": None, "across": None}
    samples = [sample(False, 1.0), sample(False, 1.0), sample(True, 5.0), sample(True, 5.0)]
    shape, params, accuracy, scores = aoe.fit(samples)
    assert scores["circle_aim"] == 0.0 and scores["circle_caster"] == 0.0 and shape == "single_target"
    # the same samples through the pooled measurement, as the server's nightly pass runs it
    cast = {"hits": 2, "aim": "player", "delay": 0.5, "facing": 0, "moved": 0, "skill": "Backwards"}
    rows = aoe.measure(extracted=[[[["Boss", 1], cast, samples]]])
    assert rows and rows[0]["shape"] == "single_target" and rows[0]["confidence"] == "insufficient"
