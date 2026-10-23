"""The game's counters: Odyle Energy and the Shugo Festival keys from the counter records, and the framing
of the large bundle a zone load sends.

The counter table (``0b 61``) comes on entering the world and every zone, inside a bundle: a count, then
one entry per counter (73 in the October recordings), each a flags byte, the u32 id and the values the
flags name (``01``/``02`` a u64 first and second value, Kinah-sized; ``04``/``08`` a varint first and
second). The update (``0c 61``) sends one entry when a counter changes. Odyle Energy is counter 60000001:
in the 19 and 20 October recordings its two values were the 840 and 50 noted in game, 15 more on the hour
every three hours, and 80 less at each claimed reward cube (the regular value first, then the bonus). The
Shugo Festival Reward Keys are counter 4 (0.2.329): in the 19 October recording its two values went from
(3, 2) to (0, 0) one key at a time, the first value first, a minute or two apart while festival rewards
were claimed, and came back one at a time. Each zone load also sends a 13-18 KB bundle; the framing gave
up on frames over 16 KB that had not fully arrived and resynced inside it, which lost it and misframed the
bundle after it, the one with the table."""
import os

import lz4.block
import pytest

from aion2calc.app import server
from aion2calc.app.settings_backup import _clean
from aion2calc.meter.a2parser import framing
from aion2calc.meter.a2parser.engine import MeterEngine
from aion2calc.meter.a2parser.parser import ODYLE_ENERGY_ID, SHUGO_KEYS_ID, scan_counters, scan_odyle_energy

SERVER = "1.2.3.4:13328->192.168.1.9:57424"
KINAH = 1_234_567_890_123                                           # more than any varint counter may hold


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
    """An entry with varint values, as the flags name them."""
    return bytes([flags]) + counter_id.to_bytes(4, "little") + b"".join(_varint(v) for v in values)


def _pair(first, second):
    """A two-value entry's flags and values: ``04`` the first, ``08`` the second, a 0 left out."""
    return (0x04 if first else 0) | (0x08 if second else 0), tuple(v for v in (first, second) if v)


def _update(regular, bonus, reason=2, kind=0, amount=0, counter_id=ODYLE_ENERGY_ID):
    flags, values = _pair(regular, bonus)
    body = bytes([kind]) + _counter(flags, counter_id, *values)
    body += bytes([1]) + amount.to_bytes(4, "little") if kind else bytes([reason])
    return _frame(b"\x0c\x61", body)


def _table(regular, bonus, keys=None):
    """The counter table as the recordings send it: a count, then Kinah (counter 3, two u64 values), the
    Shugo Festival keys when given, Odyle Energy and the weekly dungeon entries after it."""
    entries = [bytes([0x03]) + (3).to_bytes(4, "little") + KINAH.to_bytes(8, "little") + bytes(8)]
    if keys is not None:
        entries.append(_counter(*_pair(*keys)[:1], SHUGO_KEYS_ID, *_pair(*keys)[1]))
    flags, values = _pair(regular, bonus)
    entries.append(_counter(flags, ODYLE_ENERGY_ID, *values))
    entries += [_counter(0x04, ODYLE_ENERGY_ID + i, 14) for i in range(1, 10)]
    return _frame(b"\x0b\x61", _varint(len(entries)) + b"".join(entries))


def test_the_counter_table_gives_regular_and_bonus():
    assert scan_odyle_energy(_table(840, 50)) == (840, 50)          # the 19 October Templar, as noted in game
    assert scan_odyle_energy(_table(0, 80)) == (0, 80)              # a value left out is 0


def test_updates_give_both_values_with_their_reason():
    assert scan_odyle_energy(_update(55, 105, reason=2)) == (55, 105)    # 15 regenerated
    assert scan_odyle_energy(_update(0, 80, reason=3)) == (0, 80)        # a cube claimed: 55 regular, then 25 bonus
    assert scan_odyle_energy(_update(55, 50, kind=1, amount=20)) == (55, 50)


def test_the_table_lists_every_counter_kinah_sized_ones_included():
    counters = scan_counters(_table(840, 50, keys=(3, 2)))
    assert counters[ODYLE_ENERGY_ID] == (840, 50) and counters[SHUGO_KEYS_ID] == (3, 2)
    assert counters[3] == (KINAH, 0)                                # two u64 values, the second sent as 0
    assert [counters[ODYLE_ENERGY_ID + i] for i in range(1, 10)] == [(14, 0)] * 9 and len(counters) == 12
    assert scan_counters(_table(840, 50)[:-1]) is None              # an entry cut short: not the table
    assert scan_counters(_table(840, 50) + b"\x00") is None         # a byte after the last entry: not the table
    assert scan_counters(_update(2, 2, reason=3, counter_id=SHUGO_KEYS_ID)) == {SHUGO_KEYS_ID: (2, 2)}
    assert scan_counters(_update(0, 1, kind=1, amount=1, counter_id=SHUGO_KEYS_ID)) == {SHUGO_KEYS_ID: (0, 1)}
    assert scan_counters(_frame(b"\x0c\x61", b"\x00" + _counter(0x04, 12, 14) + b"\x02")) == {12: (14, 0)}


def test_other_counters_and_odd_layouts_are_not_odyle_energy():
    other = _frame(b"\x0c\x61", b"\x00" + _counter(0x04, 12, 14) + b"\x02")
    assert scan_odyle_energy(other) is None
    unknown_flag = _frame(b"\x0c\x61", b"\x00" + _counter(0x14, ODYLE_ENERGY_ID, 55, 1) + b"\x02")
    assert scan_odyle_energy(unknown_flag) is None and scan_counters(unknown_flag) is None
    trailing = _update(55, 105)[:-1] + b"\x02\x07"                  # not a reason byte where it should end
    assert scan_odyle_energy(_frame(b"\x0c\x61", trailing[2:])) is None
    stray = _frame(b"\x0b\x61", b"\x00" * 9 + _counter(0x04, ODYLE_ENERGY_ID, 840) + b"\x00" * 9)
    assert scan_odyle_energy(stray) is None                         # a count of 0: not the table
    assert scan_counters(_frame(b"\x0a\x61", _varint(1) + _counter(0x04, ODYLE_ENERGY_ID, 840))) is None


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


def test_the_shugo_festival_keys_are_counter_4_spent_one_at_a_time():
    engine = MeterEngine()
    engine.set_server_port(13328)
    assert engine.shugo_keys is None and engine.counters == {}
    engine.consume(_bundle([_table(840, 50, keys=(3, 2))]), 1_000, SERVER)
    assert engine.shugo_keys == {"regular": 3, "bonus": 2, "timestamp_ms": 1_000}
    assert engine.counters[ODYLE_ENERGY_ID + 1] == {"first": 14, "second": 0, "timestamp_ms": 1_000}
    # 19 October, 02:54 to 03:02 UTC: one key spent at each festival reward, the first value first.
    for at, keys in enumerate([(2, 2), (1, 2), (0, 2), (0, 1), (0, 0)], start=2):
        engine.consume(_update(*keys, reason=3, counter_id=SHUGO_KEYS_ID), at * 1_000, SERVER)
        assert (engine.shugo_keys["regular"], engine.shugo_keys["bonus"]) == keys
    engine.consume(_update(1, 0, kind=1, amount=1, counter_id=SHUGO_KEYS_ID), 9_000, SERVER)   # one key back
    assert engine.shugo_keys == {"regular": 1, "bonus": 0, "timestamp_ms": 9_000}
    assert (engine.odyle_energy["regular"], engine.odyle_energy["bonus"]) == (840, 50)        # untouched
    engine._reset_zone(10_000)
    assert engine.shugo_keys["regular"] == 1
    restarted = MeterEngine()
    restarted.adopt_identity(engine)
    assert restarted.shugo_keys == engine.shugo_keys
    assert restarted.counters[SHUGO_KEYS_ID] == engine.counters[SHUGO_KEYS_ID] == {"first": 1, "second": 0, "timestamp_ms": 9_000}


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
    # The Shugo Festival keys, the same way, under the Odyle line, with a key icon of their own.
    assert 'id="ovshugo"' in html and "snap.shugo_keys" in overlay and "shugoLine(snap.shugo_keys)" in app
    assert 'class="ovkeyicon"' in overlay and 'class="keyicon"' in app
    assert ".ovkeyicon{" in read("overlay.css") and "p.odyle .keyicon {" in read("app.css")
    assert 'snap["shugo_keys"] = dict(self.packet_engine.shugo_keys)' in runner
    assert overlay.count('"#ovshugo"') == 3 and overlay.count('"#ovodyle"') == 3   # hidden with the rest, in every view


def test_a_setting_on_by_default_shows_or_hides_it(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    assert server.ui_settings()["overlay_show_odyle"] is True
    assert server.ui_settings()["overlay_show_shugo_keys"] is True
    assert _clean({"overlay_show_odyle": False}) == {"overlay_show_odyle": False}
    assert _clean({"overlay_show_shugo_keys": False}) == {"overlay_show_shugo_keys": False}
    with pytest.raises(ValueError):
        _clean({"overlay_show_odyle": "no"})
    with pytest.raises(ValueError):
        _clean({"overlay_show_shugo_keys": "no"})
    static = os.path.join(os.path.dirname(__file__), "..", "aion2calc", "app", "static")
    app = open(os.path.join(static, "app.js"), encoding="utf-8").read()
    assert 'id="ov-odyle"' in app and "overlay_show_odyle: $(\"#ov-odyle\").checked" in app
    assert 'id="ov-shugo"' in app and "overlay_show_shugo_keys: $(\"#ov-shugo\").checked" in app
    runner = open(os.path.join(static, "..", "meter_runner.py"), encoding="utf-8").read()
    assert 'self.packet_engine.odyle_energy and ui.get("overlay_show_odyle") is not False' in runner
    assert 'self.packet_engine.shugo_keys and ui.get("overlay_show_shugo_keys") is not False' in runner
