"""Odyle Energy from the game's counter records, and the framing of the large bundle a zone load sends.

The counter table (``0b 61``) comes on entering the world and every zone, inside a bundle; the update
(``0c 61``) when a counter changes. Odyle Energy is counter 60000001: in the 19 and 20 October recordings
its two values were the 840 and 50 noted in game, 15 more on the hour every three hours, and 80 less at
each claimed reward cube (the regular value first, then the bonus). Each zone load also sends a 13-18 KB
bundle; the framing gave up on frames over 16 KB that had not fully arrived and resynced inside it,
which lost it and misframed the bundle after it, the one with the table."""
import os

import lz4.block
import pytest

from aion2calc.app import server
from aion2calc.app.settings_backup import _clean
from aion2calc.meter.a2parser import framing
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.parser import ODYLE_ENERGY_ID, scan_odyle_energy

SERVER = "1.2.3.4:13328->192.168.1.9:57424"


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


def _bundle(packets):
    raw = b"".join(packets)
    payload = b"\xff\xff" + len(raw).to_bytes(4, "little") + lz4.block.compress(raw, store_size=False)
    return _varint(len(payload) + 4) + payload


def _counter(flags, counter_id, *values):
    return bytes([flags]) + counter_id.to_bytes(4, "little") + b"".join(_varint(v) for v in values)


def _update(regular, bonus, reason=2, kind=0, amount=0):
    flags = (0x04 if regular else 0) | (0x08 if bonus else 0)
    body = bytes([kind]) + _counter(flags, ODYLE_ENERGY_ID, *(v for v in (regular, bonus) if v))
    body += bytes([1]) + amount.to_bytes(4, "little") if kind else bytes([reason])
    return _frame(b"\x0c\x61", body)


def _table(regular, bonus):
    ids = b"".join((10_000_000 + i).to_bytes(4, "little") for i in range(12))       # the id list before the counters
    flags = (0x04 if regular else 0) | (0x08 if bonus else 0)
    counters = _counter(flags, ODYLE_ENERGY_ID, *(v for v in (regular, bonus) if v))
    counters += b"".join(_counter(0x04, ODYLE_ENERGY_ID + i, 14) for i in range(1, 10))
    return _frame(b"\x0b\x61", ids + b"\x98\x00" + counters + b"\x00" * 6)


def test_the_counter_table_gives_regular_and_bonus():
    assert scan_odyle_energy(_table(840, 50)) == (840, 50)          # the 19 October Templar, as noted in game
    assert scan_odyle_energy(_table(0, 80)) == (0, 80)              # a value left out is 0


def test_updates_give_both_values_with_their_reason():
    assert scan_odyle_energy(_update(55, 105, reason=2)) == (55, 105)    # 15 regenerated
    assert scan_odyle_energy(_update(0, 80, reason=3)) == (0, 80)        # a cube claimed: 55 regular, then 25 bonus
    assert scan_odyle_energy(_update(55, 50, kind=1, amount=20)) == (55, 50)


def test_other_counters_and_odd_layouts_are_not_odyle_energy():
    other = _frame(b"\x0c\x61", b"\x00" + _counter(0x04, 12, 14) + b"\x02")
    assert scan_odyle_energy(other) is None
    unknown_flag = _frame(b"\x0c\x61", b"\x00" + _counter(0x14, ODYLE_ENERGY_ID, 55, 1) + b"\x02")
    assert scan_odyle_energy(unknown_flag) is None
    trailing = _update(55, 105)[:-1] + b"\x02\x07"                  # not a reason byte where it should end
    assert scan_odyle_energy(_frame(b"\x0c\x61", trailing[2:])) is None
    stray = _frame(b"\x0b\x61", b"\x00" * 9 + _counter(0x04, ODYLE_ENERGY_ID, 840) + b"\x00" * 9)
    assert scan_odyle_energy(stray) is None                         # no 60000002 after it: not the table


def test_the_engine_follows_the_table_and_its_updates_across_zones():
    engine = MeterEngine()
    engine.set_server_port(13328)
    engine.consume(_bundle([_table(40, 105)]), 1_000, SERVER)
    assert engine.odyle_energy == {"regular": 40, "bonus": 105, "timestamp_ms": 1_000}
    engine.consume(_update(55, 105, reason=2), 2_000, SERVER)
    engine.consume(_update(0, 80, reason=3), 3_000, SERVER)
    assert (engine.odyle_energy["regular"], engine.odyle_energy["bonus"]) == (0, 80)
    engine._reset_zone(4_000)                                       # the character's, not the zone's
    assert engine.odyle_energy["bonus"] == 80
    restarted = MeterEngine()
    restarted.adopt_identity(engine)
    assert restarted.odyle_energy == engine.odyle_energy


def _in_segments(data, size=1_460):
    return [data[i:i + size] for i in range(0, len(data), size)]


def test_a_zone_loads_large_bundle_and_the_one_after_it_survive_tcp_segments():
    large = _bundle([_frame(b"\x83\x56", os.urandom(30_000))])       # 30 KB that LZ4 cannot shrink
    assert len(large) > framing.MAX_FRAGMENT_WAIT_BYTES
    engine = MeterEngine()
    engine.set_server_port(13328)
    for at, chunk in enumerate(_in_segments(large + _bundle([_table(0, 80)]))):
        engine.consume(chunk, 1_000 + at, SERVER)
    assert (engine.odyle_energy["regular"], engine.odyle_energy["bonus"]) == (0, 80)
    engine.consume(_update(15, 80, reason=2), 9_000, SERVER)
    assert (engine.odyle_energy["regular"], engine.odyle_energy["bonus"]) == (15, 80)


def test_only_a_bundle_header_holds_a_large_frame_back():
    head = _varint(40_000 + 4)
    assert framing._awaits_bundle(head + b"\xff\xff" + (90_000).to_bytes(4, "little"), len(head))
    assert not framing._awaits_bundle(head + b"\x12\x34" + bytes(4), len(head))           # a corrupt length
    assert not framing._awaits_bundle(head + b"\xff\xff" + (5_000_000).to_bytes(4, "little"), len(head))
    assert framing._awaits_bundle(head + b"\xff", len(head))                                # header still on the way


def test_the_overlay_and_the_live_meter_show_it_with_the_icon():
    static = os.path.join(os.path.dirname(__file__), "..", "aion2calc", "app", "static")
    read = lambda name: open(os.path.join(static, name), encoding="utf-8").read()
    overlay, app, html = read("overlay.js"), read("app.js"), read("overlay.html")
    assert 'id="ovodyle"' in html and "snap.odyle" in overlay and "odyleLine(snap.odyle)" in app
    icon = "https://metabot.gg/web/aion2/items/icon_item_odenergy_a_001a.webp"
    assert icon in overlay and icon in app and f'"{icon}":' in read("game-assets.js")
    runner = open(os.path.join(static, "..", "meter_runner.py"), encoding="utf-8").read()
    assert 'snap["odyle"] = dict(self.packet_engine.odyle_energy)' in runner


def test_a_setting_on_by_default_shows_or_hides_it(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    assert server.ui_settings()["overlay_show_odyle"] is True
    assert _clean({"overlay_show_odyle": False}) == {"overlay_show_odyle": False}
    with pytest.raises(ValueError):
        _clean({"overlay_show_odyle": "no"})
    static = os.path.join(os.path.dirname(__file__), "..", "aion2calc", "app", "static")
    app = open(os.path.join(static, "app.js"), encoding="utf-8").read()
    assert 'id="ov-odyle"' in app and "overlay_show_odyle: $(\"#ov-odyle\").checked" in app
    runner = open(os.path.join(static, "..", "meter_runner.py"), encoding="utf-8").read()
    assert 'self.packet_engine.odyle_energy and ui.get("overlay_show_odyle") is not False' in runner
