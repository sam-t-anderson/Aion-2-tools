"""The Gear page's item panel: what an added item may take (enchant level, rolls, skill options) and
the catalog check on what it sends. No network: catalog items are written into a temporary database."""
import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.db import store
    monkeypatch.setattr(store, "SEED", tmp_path / "no-seed.json.gz")
    store._local.__dict__.clear()
    yield tmp_path / "home"
    store._local.__dict__.clear()


RING = {"slug": "test-ring", "name": "Test Ring", "grade": "Unique", "category": "Ring", "item_level": 70,
        "fixed": {"Attack": "+200"}, "description": "rolls 2 random stats on top of its fixed stats",
        "random": [{"stat": "Critical Hit", "range": "+30 – +50", "chance": "50%"},
                   {"stat": "Damage Boost", "range": "+1% – +2%", "chance": "25%"},
                   {"stat": "HP", "range": "+200 – +300", "chance": "25%"}],
        "enchant": [{"step": "+0 → +1", "stats": "Attack +5"}, {"step": "+14 → +15", "stats": "Attack +80"},
                    {"step": "+15 → +16", "stats": "Attack +5, Damage Boost +0.5%"}],
        "meta": {"Category": "Ring", "Required Level": "45", "Max enhance": "+15 (+16)"},
        "skill_pools": {"sorcerer": {"max_level": 1, "chances": {"Hellfire": 0.5, "Blaze": 0.5},
                                     "skills": ["Hellfire", "Blaze"]}}}
BELL = {"slug": "test-bell", "name": "Test Bell", "grade": "Unique", "category": "Bell", "item_level": 80,
        "fixed": {"Destiny [Marchutan]": "20"}, "description": "rolls 0 random stats", "random": [], "enchant": [],
        "meta": {"Category": "Bell", "Required Level": "45"},
        "skill_pools": {"sorcerer": {"max_level": 4, "skills": ["Hellfire", "Blaze", "Flame Arrow"]}}}


def _catalog(*items):
    from aion2calc.db import store
    conn = store.connect()
    for it in items:
        store.upsert_item(conn, it, "2026-10-01")
    conn.commit()


def test_item_options_list_what_the_item_panel_can_set(home):
    from aion2calc.plan import inventory as INV
    o = INV.options(RING, "sorcerer")
    assert (o["max_enchant"], o["enchant_known"], o["roll_count"], o["arcana"]) == (16, True, 2, False)
    crit, boost, hp = o["rolls"]
    assert (crit["stat"], crit["min"], crit["max"], crit["percent"], crit["scored"]) == ("Critical Hit", 30, 50, False, True)
    assert (boost["min"], boost["max"], boost["percent"], boost["scored"]) == (1, 2, True, True)
    assert hp["scored"] is False                                              # the damage model does not score HP
    assert {s["level"]: s["stats"] for s in o["enchant_steps"]}[16] == "Attack +5, Damage Boost +0.5%"
    sk = o["skills"]
    assert sk["pool"] == ["Hellfire", "Blaze"] and sk["max_level"] == 1       # the item's pool for the class first
    assert "Flame Arrow" in sk["others"] and "Hellfire" not in sk["others"]   # then the class's other skills, once
    assert all(n != "Element Enhancement" for n in sk["others"])             # stigmas are no gear option
    assert (sk["base"], sk["per_enchant"]) == (INV.MAX_SKILL_LEVELS, 0)
    b = INV.options(BELL, "sorcerer")
    assert (b["arcana"], b["max_enchant"], b["enchant_known"]) == (True, 5, True)
    assert (b["skills"]["base"], b["skills"]["per_enchant"], b["skills"]["max_level"]) == (4, 1, 4)
    nocls = INV.options(RING, None)
    assert nocls["skills"] == {"pool": [], "others": [], "max_level": 1, "base": 9, "per_enchant": 0}
    plain = INV.options({**RING, "meta": {"Category": "Ring"}}, "sorcerer")
    assert (plain["max_enchant"], plain["enchant_known"]) == (INV.UNKNOWN_MAX_ENCHANT, False)


def test_an_added_item_is_checked_against_the_catalog(home):
    from aion2calc.kit.base import ClassData
    from aion2calc.plan import inventory as INV
    _catalog(RING, BELL)
    inv = {"profile": "t", "class": "sorcerer", "items": []}
    e = INV.add(inv, "test-ring", "12", [["Critical Hit", "41"], ["Damage Boost", 1.5]], [["Hellfire", 1]],
                "  warehouse ", strict=True)
    assert (e["enchant"], e["rolls"], e["skills"], e["note"]) == (12, [["Critical Hit", 41], ["Damage Boost", 1.5]],
                                                                 [["Hellfire", 1]], "warehouse")
    assert e["rolls_text"] == "Critical Hit +41, Damage Boost +1.5%"         # shown in the table and on the cards
    gear, _deity, bonus = INV.entry_stats(e, "sorcerer")
    assert gear["crit"] == 41 and abs(gear["amp_all"] - 0.015) < 1e-9        # the entered rolls, not the pool's average
    assert bonus == {ClassData("sorcerer").by_name["Hellfire"]["id"]: 1}
    refused = [
        (dict(enchant=17), "Test Ring enhances to +16"),
        (dict(enchant="lots"), "whole number"),
        (dict(rolls=[["Accuracy", 40]]), "cannot roll Accuracy"),
        (dict(rolls=[["Critical Hit", 41], ["Critical Hit", 42]]), "entered twice"),
        (dict(rolls=[["Critical Hit", 51]]), "Critical Hit rolls +30 – +50 on Test Ring"),
        (dict(rolls=[["Damage Boost", "2.5%"]]), "Damage Boost rolls +1% – +2%"),
        (dict(rolls=[["Critical Hit", 41], ["Damage Boost", 1.5], ["HP", 250]]), "rolls 2 random stats"),
        (dict(rolls=[["Critical Hit", "lots"]]), "enter a number for Critical Hit"),
        (dict(rolls=[["Critical Hit"]]), "[stat, value] pair"),
        (dict(skills=[["Nonsense", 1]]), "Nonsense is not a sorcerer skill"),
        (dict(skills=[["Hellfire", 2]]), "reaches +1"),
        (dict(skills=[["Hellfire", 1], ["Hellfire", 1]]), "entered twice"),
    ]
    for kw, why in refused:
        with pytest.raises(ValueError, match=re.escape(why)):
            INV.add(inv, "test-ring", strict=True, **kw)
    assert len(inv["items"]) == 1                                             # nothing refused was added
    # An arcana card holds its grade's base options plus one per enchant level, at most +4 on one skill.
    card = INV.add(inv, "test-bell", 1, None, [["Hellfire", 4], ["Blaze", 1]], strict=True)
    assert (card["enchant"], card["skills"], card["rolls"]) == (1, [["Hellfire", 4], ["Blaze", 1]], None)
    with pytest.raises(ValueError, match="Test Bell holds 5 option levels at \\+1"):
        INV.add(inv, "test-bell", 1, None, [["Hellfire", 4], ["Blaze", 2]], strict=True)
    with pytest.raises(ValueError, match=re.escape("Test Bell enhances to +5")):
        INV.add(inv, "test-bell", 6, strict=True)
    with pytest.raises(ValueError, match="rolls no random stats"):
        INV.add(inv, "test-bell", 0, [["Critical Hit", 40]], strict=True)
    # The CLI and older callers add what they are given, as before.
    loose = INV.add(inv, "test-ring", 2, rolls=[["HP", 250], ["HP", 250]], skills=[["Whatever", 3]])
    assert loose["rolls"] == [["HP", 250], ["HP", 250]] and loose["skills"] == [["Whatever", 3]]
    assert "rolls_text" not in loose


def test_update_changes_an_added_entry_only(home):
    from aion2calc.plan import inventory as INV
    _catalog(RING)
    worn = {"id": "eq-Ring1", "source": "equipped", "slot": "Ring1", "slug": "test-ring", "name": "Test Ring",
            "category": "Ring", "enchant": 3, "stats": {"attack": 1}}
    inv = {"profile": "t", "class": "sorcerer", "items": [worn]}
    e = INV.add(inv, "test-ring", 2, strict=True)
    u = INV.update(inv, e["id"], enchant=15, rolls=[["Critical Hit", 50]], skills=[["Blaze", 1]], note="bank")
    assert u is e and (e["enchant"], e["rolls"], e["rolls_text"], e["skills"], e["note"]) == \
        (15, [["Critical Hit", 50]], "Critical Hit +50", [["Blaze", 1]], "bank")
    INV.update(inv, e["id"], rolls=[])                                       # [] clears the rolls: expected again
    assert (e["rolls"], e["rolls_text"], e["enchant"], e["skills"], e["note"]) == (None, None, 15, [["Blaze", 1]], "bank")
    INV.update(inv, e["id"], skills=[], note="")
    assert (e["skills"], e["note"]) == ([], None)
    with pytest.raises(ValueError, match="read from the official page"):
        INV.update(inv, "eq-Ring1", enchant=5)
    with pytest.raises(ValueError, match="no inventory entry"):
        INV.update(inv, "nope", enchant=5)
    with pytest.raises(ValueError, match=re.escape("+30 – +50")):
        INV.update(inv, e["id"], enchant=1, rolls=[["Critical Hit", 10]])
    assert (e["enchant"], e["rolls"], worn["enchant"]) == (15, None, 3)      # a refused change leaves it as it was


def test_gear_page_endpoints(home, monkeypatch):
    from aion2calc.app import server
    _catalog(RING)
    inv = {"profile": "t", "class": "sorcerer", "items": []}
    monkeypatch.setattr(server, "_inventory", lambda key: (None, inv))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path):
        try:
            return 200, json.loads(urllib.request.urlopen(base + path, timeout=30).read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as err:
            return json.loads(err.read())
    try:
        code, o = get("/api/items/test-ring/options?class=sorcerer")
        assert code == 200 and o["max_enchant"] == 16 and o["skills"]["pool"] == ["Hellfire", "Blaze"]
        assert [r["stat"] for r in o["rolls"]] == ["Critical Hit", "Damage Boost", "HP"]
        assert get("/api/items/test-ring")[1]["slug"] == "test-ring"          # the item record itself still answers
        assert get("/api/items/none-such/options")[0] == 404
        r = post("/api/inventory/add", {"character": "k", "slug": "test-ring", "enchant": 17})
        assert "Test Ring enhances to +16" in r["error"] and inv["items"] == []
        r = post("/api/inventory/add", {"character": "k", "slug": "test-ring", "enchant": 10,
                                        "rolls": [["Critical Hit", 45]], "skills": [["Hellfire", 1]], "note": "bag"})
        [e] = r["items"]
        assert (e["enchant"], e["rolls_text"], e["skills"], e["note"]) == (10, "Critical Hit +45", [["Hellfire", 1]], "bag")
        r = post("/api/inventory/update", {"character": "k", "id": e["id"], "enchant": 12, "rolls": [], "skills": [],
                                           "note": ""})
        [e] = r["items"]
        assert (e["enchant"], e["rolls"], e["rolls_text"], e["skills"], e["note"]) == (12, None, None, [], None)
        r = post("/api/inventory/update", {"character": "k", "id": e["id"], "rolls": [["HP", 999]]})
        assert "HP rolls +200 – +300" in r["error"] and inv["items"][0]["rolls"] is None
        assert json.loads((home / "inventory" / "t.json").read_text(encoding="utf-8"))["items"][0]["enchant"] == 12
    finally:
        srv.shutdown()


def test_gear_page_statics_carry_the_item_panel():
    js = (ROOT / "aion2calc/app/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "aion2calc/app/static/app.css").read_text(encoding="utf-8")
    for needle in ("/options?class=", "/api/inventory/update", "data-ge-enchant", "data-ge-roll=", "data-ge-skill=",
                   "data-ge-save", 'data-edit="', "<th>Rolls</th>"):
        assert needle in js, needle
    assert '$("#gen")' not in js and '$("#gsk")' not in js                    # the old global enchant/skills inputs
    assert ".gedit" in css and ".gedit .gelines" in css


def test_inventory_cli_takes_rolls_skill_options_and_edits(home, monkeypatch, capsys):
    """``python -m aion2calc inventory``: --options shows the pool, --add/--edit take --roll/--skill/--note through
    the same catalog check as the Gear page, a refusal says why and exits 1."""
    from aion2calc import charopt
    from aion2calc.__main__ import main
    from aion2calc.plan import inventory as INV
    _catalog(RING, BELL)
    inv = {"profile": "t", "class": "sorcerer", "items": []}

    class Imp:
        cls = "sorcerer"
    monkeypatch.setattr(charopt, "find", lambda name, region, server: [{"character_id": 1, "server_id": 1, "region": region}])
    monkeypatch.setattr(charopt, "import_character", lambda *a, **k: Imp())
    monkeypatch.setattr(INV, "from_character", lambda imp, keep=None: inv)
    args = ["inventory", "Name"]
    assert main(args + ["--options", "test-ring"]) == 0
    out = capsys.readouterr().out
    assert "enchant: +0 to +16" in out and "Critical Hit" in out and "+30 – +50" in out
    assert "not scored" in out and "pool: Hellfire, Blaze" in out
    assert main(args + ["--options", "test-bell"]) == 0
    assert "4 option levels for a Unique card plus one per enchant level" in capsys.readouterr().out
    assert main(args + ["--add", "test-ring", "--enchant", "12", "--roll", "Critical Hit=41", "--roll", "Damage Boost=1.5%",
                        "--skill", "Hellfire", "--note", "warehouse"]) == 0
    out = capsys.readouterr().out
    [e] = inv["items"]
    assert (e["enchant"], e["rolls"], e["skills"], e["note"]) == (12, [["Critical Hit", 41], ["Damage Boost", 1.5]],
                                                                 [["Hellfire", 1]], "warehouse")
    assert "added" in out and "rolls Critical Hit +41, Damage Boost +1.5%" in out
    assert "skills Hellfire +1" in out and "note warehouse" in out
    assert main(args + ["--add", "test-ring", "--roll", "Critical Hit=99"]) == 1        # refused: says why, exits 1
    assert "not changed: Critical Hit rolls +30 – +50 on Test Ring" in capsys.readouterr().out and len(inv["items"]) == 1
    assert main(args + ["--add", "test-ring", "--roll", "Critical Hit"]) == 1           # a roll needs its value
    assert "STAT=VALUE" in capsys.readouterr().out and len(inv["items"]) == 1
    assert main(args + ["--edit", e["id"], "--roll", "Critical Hit=50", "--no-skills", "--note", ""]) == 0
    assert (e["enchant"], e["rolls"], e["skills"], e["note"]) == (12, [["Critical Hit", 50]], [], None)   # level kept
    assert "changed" in capsys.readouterr().out
    assert main(args + ["--edit", e["id"], "--enchant", "15", "--no-rolls"]) == 0
    assert (e["enchant"], e["rolls"], e["rolls_text"]) == (15, None, None)
    assert main(args + ["--edit", "nope", "--enchant", "1"]) == 1
    assert "no inventory entry" in capsys.readouterr().out
    saved = json.loads((home / "inventory" / "t.json").read_text(encoding="utf-8"))
    assert saved["items"][0]["enchant"] == 15                                              # written on every change
    assert main(args + ["--remove", e["id"]]) == 0 and inv["items"] == []
