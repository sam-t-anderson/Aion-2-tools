"""An open-world party's record (0.2.329). Outside a dungeon the game sends no party list (``02 97``); what it
sends, every two seconds or so for each other member wherever they are, is a member status record
(``1c 92``): the member's character (database id with the server in its top 16 bits), the roster's class
code, map, position, level and legion name, and neither name nor entity. In the 21 October Abyss recording
the recording player's two party members had 551 of them and the legion mates who were not in the party
none. While a member is in view, the HP record of their entity (``1b 92``) comes in the same batch, which
is what names them."""
import struct

from aion2calc.meter.a2parser.parser import hp_record_entity, scan_party_status

SERVER = 2102
LEGION = "Guild"


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


def _status(character_id, class_code=20, level=45, map_id=20, legion=LEGION, points=127_918, server=SERVER):
    dbid = (server << 48) | character_id
    body = (dbid.to_bytes(8, "little") + class_code.to_bytes(4, "little") + map_id.to_bytes(4, "little")
            + (1).to_bytes(4, "little") + (602).to_bytes(4, "little") + struct.pack("<fff", 50148.0, -48674.9, 20422.0)
            + level.to_bytes(4, "little") + bytes(4) + (2575).to_bytes(4, "little")
            + bytes([len(legion.encode())]) + legion.encode() + (2).to_bytes(4, "little") + b"\x01"
            + points.to_bytes(8, "little") + b"\x01")
    return _frame(b"\x1c\x92", body)


def _hp(entity, current=27_061, maximum=27_061):
    return _frame(b"\x1b\x92", _varint(entity) + _varint(current) + _varint(maximum) + bytes(24))


def test_the_status_record_gives_the_member_their_class_level_map_and_legion():
    status = scan_party_status(_status(322_274, class_code=20, level=45))
    assert status == {"dbid": (SERVER << 48) | 322_274, "serverId": SERVER, "characterId": 322_274, "job": "Assassin",
                      "classCode": 20, "mapId": 20, "level": 45, "legion": LEGION}
    assert scan_party_status(_status(287_766, class_code=36, legion=""))["job"] == "Chanter"   # no legion: a 63-byte body
    assert scan_party_status(_status(304_105, class_code=8))["job"] == "Gladiator"


def test_other_records_and_odd_layouts_are_not_a_status():
    assert scan_party_status(_hp(12_193)) is None
    assert scan_party_status(_status(322_274)[:-1]) is None                          # a byte short of its legion-sized length
    assert scan_party_status(_status(322_274) + b"\x00") is None
    assert scan_party_status(_status(322_274, level=0)) is None
    assert scan_party_status(_status(322_274, server=0)) is None
    assert scan_party_status(_frame(b"\x1d\x92", _status(322_274)[3:])) is None    # another opcode
    assert hp_record_entity(_hp(12_193)) == 12_193 and hp_record_entity(_status(322_274)) is None


from aion2calc.meter.a2parser.engine import MeterEngine, PARTY_STATUS_TTL_MS

STREAM = "1.2.3.4:13328->192.168.1.9:57424"
ME, ALLY, HEALER, TANK = 13_303, 12_193, 12_769, 5_499
ALLY_ID, HEALER_ID, TANK_ID = 322_274, 287_766, 280_646


def _engine(names=True):
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.local_player_id = ME
    engine.names[ME] = "Me"
    if names:
        engine.names.update({ALLY: "Ally", HEALER: "Healer", TANK: "Tank"})
    return engine


def test_a_full_batch_pairs_each_member_with_their_entity_and_names_the_party():
    engine = _engine()
    # The batch, in the party's slot order: the HP records of the members in view, then every status.
    batch = _hp(TANK) + _hp(HEALER) + _hp(ALLY) + _status(TANK_ID, 12) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20)
    engine.consume(batch, 1_000, STREAM)
    assert engine.roster_source == "status" and engine.roster_complete is True
    assert engine.roster == {
        "Tank": {"dbid": (SERVER << 48) | TANK_ID, "serverId": SERVER, "job": "Templar", "level": 45, "gearScore": 0, "source": "status"},
        "Healer": {"dbid": (SERVER << 48) | HEALER_ID, "serverId": SERVER, "job": "Chanter", "level": 45, "gearScore": 0, "source": "status"},
        "Ally": {"dbid": (SERVER << 48) | ALLY_ID, "serverId": SERVER, "job": "Assassin", "level": 45, "gearScore": 0, "source": "status"}}
    assert {m["entity"] for m in engine.party_status.values()} == {TANK, HEALER, ALLY}
    assert engine.known_players >= {TANK, HEALER, ALLY} and ME not in engine.party_feed


def test_a_member_out_of_view_leaves_the_batch_short_and_the_feed_still_names_the_others():
    engine = _engine()
    # Two of three in view: the HP records cannot be matched to statuses by position, so no pairing; the
    # named entities of the party HP feed are party members all the same, and the roster is not complete.
    short = _hp(HEALER) + _hp(ALLY) + _status(TANK_ID, 12) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20)
    engine.consume(short, 1_000, STREAM)
    assert set(engine.roster) == {"Healer", "Ally"} and engine.roster_complete is False
    assert engine.roster["Ally"] == {"dbid": None, "serverId": 0, "job": "", "level": 0, "gearScore": 0, "source": "feed"}
    assert all("entity" not in m for m in engine.party_status.values())
    # A later full batch pairs them, and the entries carry the status's class and level from then on.
    engine.consume(_hp(TANK) + _hp(HEALER) + _hp(ALLY) + _status(TANK_ID, 12) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20), 3_000, STREAM)
    assert engine.roster_complete is True and engine.roster["Ally"]["job"] == "Assassin" and engine.roster["Tank"]["source"] == "status"


def test_an_mp_record_between_the_batchs_records_does_not_break_it_but_another_record_does():
    engine = _engine()
    mp = _frame(b"\x00\x8d", bytes(12))
    engine.consume(_hp(HEALER) + mp + _hp(ALLY) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20), 1_000, STREAM)
    assert {m.get("entity") for m in engine.party_status.values()} == {HEALER, ALLY}
    engine = _engine()
    other = _frame(b"\x0c\x61", b"\x00" + bytes([0x04]) + (12).to_bytes(4, "little") + b"\x0e\x02")   # a counter update
    engine.consume(_hp(HEALER) + other + _status(HEALER_ID, 36) + _status(ALLY_ID, 20), 1_000, STREAM)
    assert all("entity" not in m for m in engine.party_status.values())        # the HP record was not this batch's


def test_a_member_whose_status_stops_has_left_and_a_party_list_packet_takes_precedence():
    engine = _engine()
    full = _hp(HEALER) + _hp(ALLY) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20)
    engine.consume(full, 1_000, STREAM)
    assert set(engine.roster) == {"Healer", "Ally"}
    engine.consume(_hp(ALLY) + _status(ALLY_ID, 20), 1_000 + PARTY_STATUS_TTL_MS + 1, STREAM)   # the healer left
    assert set(engine.roster) == {"Ally"} and engine.roster_complete is True
    engine.consume(_frame(b"\x0c\x61", b"\x00" + bytes([0x04]) + (12).to_bytes(4, "little") + b"\x0e\x02"),
                   1_000 + 2 * PARTY_STATUS_TTL_MS + 2, STREAM)                                   # the party disbanded
    assert engine.roster == {} and engine.roster_source is None and engine.party_status == {}
    engine.consume(full, 100_000, STREAM)
    engine._update_roster({"Healer": {"slot": 1, "dbid": 1, "serverId": SERVER, "job": "Chanter", "level": 45, "gearScore": 1}}, True, 600092)
    engine.consume(full, 101_000, STREAM)                                      # a dungeon's list rules while it is there
    assert engine.roster_source == "packet" and set(engine.roster) == {"Healer"}


def test_a_zone_load_keeps_the_party_and_forgets_its_entities_and_a_restart_carries_it():
    engine = _engine()
    engine.consume(_hp(HEALER) + _hp(ALLY) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20), 1_000, STREAM)
    engine._reset_zone(2_000)
    assert set(engine.party_status) == {(SERVER << 48) | HEALER_ID, (SERVER << 48) | ALLY_ID}
    assert all("entity" not in m for m in engine.party_status.values()) and engine.party_feed == {} and engine.roster == {}
    engine.names.update({ALLY + 100: "Ally", HEALER + 100: "Healer"})           # new entities after the load
    engine.consume(_hp(HEALER + 100) + _hp(ALLY + 100) + _status(HEALER_ID, 36) + _status(ALLY_ID, 20), 3_000, STREAM)
    assert set(engine.roster) == {"Healer", "Ally"} and engine.roster_complete is True
    restarted = MeterEngine()
    restarted.adopt_identity(engine)
    assert restarted.roster == engine.roster and restarted.party_status == engine.party_status and restarted.roster_source == "status"
