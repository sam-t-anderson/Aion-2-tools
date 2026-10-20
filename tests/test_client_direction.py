"""The client-to-server direction is encrypted. The engine parsed it like the server's broadcast, so a byte
run that happened to frame as a zone-state record named a map that does not exist: a two-hour replay of
both directions gave six such map ids, stamped on fights, and nothing else (the same events, zone resets
and identities as the server's direction alone). Fixed-port capture and replays feed both directions."""
from aion2calc.meter.a2parser.engine import MeterEngine

SERVER = "1.2.3.4:13328->192.168.1.9:57424"
CLIENT = "192.168.1.9:57424->1.2.3.4:13328"


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


def _map_record(map_id):
    return _frame(b"\x21\x36", b"\x00" * 4 + map_id.to_bytes(4, "little") + b"\x00" * 4)


def test_only_the_servers_direction_names_the_map():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_map_record(1110), 1_000, SERVER)
    assert engine.map_id == 1110
    engine.consume(_map_record(2419904778), 2_000, CLIENT)
    assert engine.map_id == 1110


def test_the_clients_direction_never_resets_the_zone():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.local_player_id, engine.local_identity_from_game = 4212, True
    engine.consume(_frame(b"\x23\x36", _varint(0) + b"\x00" * 8), 10_000, CLIENT)
    assert engine.local_player_id == 4212 and engine.last_zone_reset_ms is None
    engine.consume(_frame(b"\x23\x36", _varint(0) + b"\x00" * 8), 20_000, SERVER)
    assert engine.last_zone_reset_ms == 20_000
