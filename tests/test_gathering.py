"""Gathering and dungeon reward cubes: the records, the engine and the app's gathering log.

In the 19 and 20 October recordings each gather ended with ``33 8d`` to the gatherer: a result byte (0 the
node's plain material, 1 a better grade, 2 a failed gather with a count of 0), 0x3a, the node's entity, the
item and the count, then 12 bytes; 68 gathers of Odyle, Orichalcum Ore, gemstones and logs. The node had come
into view as a ``34 36`` spawn of kind 4 whose code names its kind (1550004 every Orichalcum Ore vein). A claimed
reward cube sent ``15 57``, the run's loot as (item, count) pairs, right after its 80 Odyle Energy were spent.
The frames here are built to those layouts with made-up ids."""
import json
import struct

import pytest

from aion2calc.combat import gathering, items
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.parser import scan_gather_node, scan_gather_result, scan_reward_list

SERVER = "1.2.3.4:13328->192.168.1.9:57424"
ODYLE, FINE_ODYLE, ORE, FINE_ORE = 610610013, 610610014, 610620013, 610620014
REFINING, KINA = 610530001, 930100031
ORE_VEIN, ODYLE_PLANT = 1550004, 1500062


def _varint(value):
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _frame(opcode, body):
    inner = opcode + body
    return _varint(len(inner) + 4) + inner


def _node(entity, code, position=(34590.0, -38764.0, 24980.3), kind=4):
    return _frame(b"\x34\x36", _varint(entity) + kind.to_bytes(2, "little") + code.to_bytes(4, "little")
                  + struct.pack("<fff", *position) + bytes(37))


def _gather(node, item, count=1, result=0, tail=bytes(12)):
    return _frame(b"\x33\x8d", bytes([result, 0x3A]) + _varint(node) + item.to_bytes(4, "little")
                  + count.to_bytes(4, "little") + tail)


def _cube(entries):
    body = b"\x00\x00\x02" + bytes([len(entries)])
    return _frame(b"\x15\x57", body + b"".join(i.to_bytes(4, "little") + n.to_bytes(4, "little") for i, n in entries))


def test_a_gather_names_the_node_the_item_and_how_it_went():
    assert scan_gather_result(_gather(37488, ODYLE)) == {"result": 0, "node": 37488, "item": ODYLE, "count": 1}
    assert scan_gather_result(_gather(56516, FINE_ORE, result=1))["result"] == 1              # a better grade
    assert scan_gather_result(_gather(46588, 610660025, count=0, result=2))["count"] == 0     # failed: nothing
    assert scan_gather_result(_gather(41612, ORE, tail=b"\x01" + bytes(11)))["item"] == ORE   # the byte after it varies
    assert scan_gather_result(_gather(37488, ODYLE, result=3)) is None                        # no such result
    assert scan_gather_result(_gather(37488, ODYLE)[:-1]) is None                             # cut short
    assert scan_gather_result(_gather(37488, 42)) is None                                    # not an item id
    assert scan_gather_result(_frame(b"\x34\x8d", b"\xf2\x05\x00\x3a" + _varint(37488))) is None   # someone's gather


def test_a_gathering_node_spawn_gives_its_code_and_place():
    entity, code, position = scan_gather_node(_node(37488, ODYLE_PLANT))
    assert (entity, code) == (37488, ODYLE_PLANT) and position == pytest.approx((34590.0, -38764.0, 24980.3), abs=0.01)
    assert scan_gather_node(_node(37488, 1100001, kind=1)) is None                           # another kind of object
    assert scan_gather_node(_node(37488, ODYLE_PLANT, position=(float("nan"), 0.0, 0.0))) is None
    assert scan_gather_node(_node(37488, ODYLE_PLANT)[:12]) is None


def test_a_reward_cube_lists_every_item_and_count():
    entries = [(KINA, 800_000), (930100023, 4_000), (110150059, 1), (REFINING, 6), (610530005, 1)]
    assert scan_reward_list(_cube(entries)) == entries
    assert scan_reward_list(_cube(entries)[:-1]) is None                                     # an entry cut short
    assert scan_reward_list(_cube([])) is None
    assert scan_reward_list(_cube([(REFINING, 0)])) is None                                  # a count of 0


def test_the_engine_keeps_each_gather_with_its_node_place_and_character_until_drained():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.map_id, engine.dungeon_id = 600092, 600092
    engine.local_player_id = 754
    engine.names[754] = "Alpha"
    engine.local_profile = {"serverId": 2102}
    engine.consume(_node(37488, ODYLE_PLANT), 1_000, SERVER)
    engine.consume(_gather(37488, ODYLE), 7_000, SERVER)
    engine.consume(_gather(99999, ORE), 8_000, SERVER)                                       # its spawn came before Start
    engine.consume(_cube([(KINA, 800_000), (REFINING, 6)]), 9_000, SERVER)
    first, unseen, cube = engine.drain_gathering()
    assert first == {"kind": "gather", "timestamp_ms": 7_000, "item": ODYLE, "count": 1, "result": 0, "node": ODYLE_PLANT,
                     "position": [34590.0, -38764.0, 24980.3], "map_id": 600092, "instance_id": 600092,
                     "character": "Alpha", "server_id": 2102}
    assert unseen["node"] is None and unseen["position"] is None
    assert cube == {"kind": "reward", "timestamp_ms": 9_000, "items": [[KINA, 800_000], [REFINING, 6]], "map_id": 600092,
                    "instance_id": 600092, "character": "Alpha", "server_id": 2102}
    assert engine.drain_gathering() == []
    engine._reset_zone(10_000)                                                               # node entities are the zone's
    assert engine.gather_nodes == {}


def test_a_restarted_engine_keeps_what_was_not_drained():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_node(37488, ODYLE_PLANT), 1_000, SERVER)
    engine.consume(_gather(37488, ODYLE), 2_000, SERVER)
    restarted = MeterEngine()
    restarted.adopt_identity(engine)
    assert [e["item"] for e in restarted.drain_gathering()] == [ODYLE] and restarted.gather_nodes[37488]["code"] == ODYLE_PLANT


def test_items_are_named_from_the_bundled_table():
    assert items.item_name(FINE_ORE) == "Fine Orichalcum Ore" and items.item_info(FINE_ORE)["grade"] == "Rare"
    assert items.base_material(FINE_ORE) == items.base_material(ORE) == "Orichalcum Ore"
    assert items.is_material(REFINING) and items.is_material(ODYLE) and not items.is_material(KINA)
    assert items.item_name(123) == "Item 123"


def test_the_item_names_stage_from_dbaion2_with_a_review_audit(tmp_path):
    """``python -m aion2calc item-names --out DIR``: names, categories and grades only, staged beside an audit."""
    from aion2calc.scrape import item_names
    source = [{"id": FINE_ORE, "name": " Fine Orichalcum Ore ", "category": "GATHERRESOURCE", "gradeName": "Rare", "price": 9},
              {"id": KINA, "name": "Kina", "category": None, "itemType": "CURRENCY", "gradeName": "Common"},
              {"id": KINA, "name": "Kina (again)", "category": None}]                    # a repeated id keeps its first row
    assert item_names.build(item_names.validate(source)) == {str(FINE_ORE): ["Fine Orichalcum Ore", "GATHERRESOURCE", "Rare"],
                                                               str(KINA): ["Kina", "CURRENCY", "Common"]}
    with pytest.raises(ValueError):
        item_names.validate([{"id": "610620014", "name": "Fine Orichalcum Ore"}])        # the id is not a number
    staged = item_names.stage(tmp_path / "stage", log=lambda *_: None, fetch=lambda url: json.dumps(source).encode())
    written = json.loads((tmp_path / "stage" / "item-names.json").read_text(encoding="utf-8"))
    assert written == staged and written["format"] == "a2item-names" and written["source"]["records"] == 2
    audit = json.loads((tmp_path / "stage" / "item-names-audit.json").read_text(encoding="utf-8"))
    assert audit["diff"]["counts"]["rows"] == 2 and audit["diff"]["counts"]["removed"] > 9000     # against the bundled table
    with pytest.raises(ValueError):
        item_names.stage(tmp_path / "stage", log=lambda *_: None, fetch=lambda url: json.dumps(source).encode())  # never overwrites


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def _drained(**over):
    row = {"kind": "gather", "timestamp_ms": 7_000, "item": ODYLE, "count": 1, "result": 0, "node": ODYLE_PLANT,
           "position": [1.0, 2.0, 3.0], "map_id": 1110, "instance_id": None, "character": "Alpha", "server_id": 2102}
    row.update(over)
    return row


def test_the_log_keeps_each_record_once_with_a_stable_id(home):
    kept = gathering.record([_drained(), _drained(timestamp_ms=8_000, item=FINE_ODYLE, result=1), {"kind": "bogus"}])
    assert [r["result"] for r in kept] == ["normal", "better"] and len({r["id"] for r in kept}) == 2
    assert gathering.normalize(_drained())["id"] == kept[0]["id"]                            # the same record, the same id
    assert [r["id"] for r in gathering.read()] == [r["id"] for r in kept]
    (home / "data" / "gathering" / "log.jsonl").open("a").write("not json\n")
    assert len(gathering.read()) == 2                                                       # a damaged line is skipped


def test_the_summary_gives_each_node_its_grades_and_each_dungeon_its_cube_materials(home):
    gathering.record([_drained(timestamp_ms=t, item=item, result=result, count=0 if result == 2 else 1, node=ORE_VEIN)
                      for t, item, result in ((1, ORE, 0), (2, ORE, 0), (3, FINE_ORE, 1), (4, ORE, 2))])
    gathering.record([{"kind": "reward", "timestamp_ms": t, "items": cube, "map_id": 600092, "instance_id": 600092,
                       "character": "Alpha", "server_id": 2102}
                      for t, cube in ((10, [[KINA, 800_000], [REFINING, 6]]), (11, [[KINA, 400_000], [REFINING, 2], [610530005, 1]]))])
    view = gathering.summary()
    assert (view["gathers"], view["gathered"], view["cubes"]) == (4, 3, 2)
    assert view["results"] == {"normal": 2, "better": 1, "failed": 1}
    (vein,) = view["nodes"]
    assert vein["name"] == "Orichalcum Ore" and vein["node"] == ORE_VEIN and vein["gathers"] == 4
    assert [(i["name"], i["share"]) for i in vein["items"]] == [("Orichalcum Ore", 0.5), ("Fine Orichalcum Ore", 0.25)]
    (dungeon,) = view["dungeons"]
    stones = next(i for i in dungeon["items"] if i["item"] == REFINING)
    assert (dungeon["instance"], dungeon["cubes"], stones["share"], stones["average"], stones["material"]) == (600092, 2, 1.0, 4.0, True)
    expert = next(i for i in dungeon["items"] if i["item"] == 610530005)
    assert expert["share"] == 0.5 and not next(i for i in dungeon["items"] if i["item"] == KINA)["material"]
    assert view["recent"][0]["kind"] == "reward" and view["recent"][0]["items"][1]["name"] == "Refining Stone"


class _Response:
    def __init__(self, body=b'{"accepted": 1}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def test_reports_go_once_in_batches_and_name_the_character_only_when_signed_in(home, monkeypatch):
    sent = []
    monkeypatch.setattr(gathering.share, "effective", lambda: {"url": "https://logs.example", "key": "k"})
    monkeypatch.setattr(gathering.share, "capabilities", lambda base: {"gathering": 1})
    monkeypatch.setattr(gathering, "reporter_key", lambda: "r" * 32)
    token = {"value": None}
    monkeypatch.setattr("aion2calc.combat.account.token_for", lambda url: token["value"])

    def post(request, timeout=0):
        sent.append((dict(request.header_items()), json.loads(request.data)))
        return _Response()
    monkeypatch.setattr(gathering.urllib.request, "urlopen", post)
    gathering.record([_drained(timestamp_ms=t) for t in range(1, 251)])
    assert gathering.report({}, final=True) == "sent 250"
    assert [len(body["events"]) for _, body in sent] == [200, 50]
    headers, body = sent[0]
    assert "X-account-token" not in headers and "character" not in body["events"][0] and body["reporter"] == "r" * 32
    assert body["events"][0] == {"id": body["events"][0]["id"], "kind": "gather", "t": 0.001, "map": 1110, "item": ODYLE,
                                 "count": 1, "result": "normal", "node": ODYLE_PLANT}
    assert gathering.report({}, final=True) == "nothing"                                    # each record goes once
    token["value"] = "a2app_x"
    gathering.record([_drained(timestamp_ms=999)])
    assert gathering.report({}, final=True) == "sent 1"
    headers, body = sent[-1]
    assert headers["X-account-token"] == "a2app_x" and body["events"][0]["character"] == "Alpha" and body["events"][0]["server"] == 2102


def test_nothing_is_sent_when_sharing_is_off_or_the_server_cannot_take_it(home, monkeypatch):
    monkeypatch.setattr(gathering.share, "effective", lambda: {"url": "https://logs.example"})
    monkeypatch.setattr(gathering.urllib.request, "urlopen", lambda *a, **k: pytest.fail("nothing may be sent"))
    gathering.record([_drained()])
    assert gathering.report({"share_gathering": False}, final=True) == "disabled"
    monkeypatch.setattr(gathering.share, "capabilities", lambda base: {})
    assert gathering.report({}, final=True) == "unsupported"
    assert gathering.enabled({}) and not gathering.enabled({"share_gathering": False})     # on by default
