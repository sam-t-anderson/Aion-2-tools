"""The value probe: given the numbers you saw in the game and when, it finds the record field that
held them (opcode, offset, encoding) in a diagnostic capture, ranks candidates by evidence, and
never calls any of them a decoder rule. Read-only, bounded, works on the ZIP or its jsonl."""
import json
import struct
import zipfile

import pytest

from aion2calc.meter import probe


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _packet(opcode: bytes, body: bytes) -> bytes:
    """One game frame as the walker expects it: the length varint counts the opcode and body plus
    four bytes of protocol overhead (framing.length_value), then the opcode and body follow."""
    inner = opcode + body
    return _varint(len(inner) + 4) + inner


def _row(t_ms, payload, *, sport=13328, dport=57424):
    return json.dumps({"timestamp_ms": t_ms, "interface": "x", "src": "1.2.3.4", "sport": sport, "dst": "192.168.1.9",
                       "dport": dport, "sequence": 1, "flags": 24, "payload_hex": payload.hex()})


def _capture(tmp_path, counter_values, *, noise=True):
    """A status record (opcode 0x5a36) every 2 s carrying a u16 counter at offset 6, plus noise
    records (opcode 0x4136) carrying unrelated numbers, and a client->server row that must be ignored."""
    t0 = 1_800_000_000_000
    rows = []
    for i in range(0, 120):
        t = t0 + i * 2000
        value = counter_values(i)
        body = b"\x01\x02\x03\x04\x05\x06" + struct.pack("<H", value) + b"\x00\x09" + struct.pack("<I", 777_000 + i)
        rows.append(_row(t, _packet(b"\x5a\x36", body)))
        if noise:
            rows.append(_row(t + 500, _packet(b"\x41\x36", struct.pack("<I", 3000 + i) + struct.pack("<H", 12))))
        rows.append(_row(t + 700, _packet(b"\x5a\x36", b"\x00"), sport=57424, dport=13328))   # client -> server
    rows.append(json.dumps({"garbage": True}))
    rows.append(_row(t0 + 1000, b'{"json": "text from another program"}'))
    path = tmp_path / "tcp-payloads.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path, t0 / 1000


def test_finds_the_counter_field_and_marks_it_strong(tmp_path):
    path, start = _capture(tmp_path, lambda i: 37 + i // 40)        # 37 for 80 s, 38 for 80 s, 39 after
    frames, info = probe.load_frames(path)
    assert info["frames"] == 240 and info["text_rows"] == 1 and info["skipped_rows"] == 1
    obs = probe.parse_known(["+0:30=37:cubes", "+1:40=38", "+3:20=39"], start=start, day="2027-01-01")
    ranked = probe.probe(frames, obs, window_s=10)
    best = ranked[0]
    assert (best.opcode_hex, best.offset, best.encoding) == ("5a 36", 6, "u16")
    assert best.matched == [0, 1, 2] and best.agreement == 1.0 and best.distinct_values == 3
    assert probe.verdict(best, obs) == "strong"
    # The same bytes read as a wider field or at another offset never outrank the true field.
    assert all((c.opcode_hex, c.offset, c.encoding) != ("5a 36", 6, "u16") for c in ranked[1:])


def test_random_fields_rank_below_and_one_observation_is_weak(tmp_path):
    path, start = _capture(tmp_path, lambda i: 40 + i)                # a counter that changes every record
    frames, _ = probe.load_frames(path)
    obs = probe.parse_known(["+0:20=50"], start=start, day="2027-01-01")
    ranked = probe.probe(frames, obs, window_s=5)
    assert ranked and probe.verdict(ranked[0], obs) == "weak"         # one observation proves nothing


def test_run_reads_a_zip_and_writes_a_report(tmp_path):
    path, start = _capture(tmp_path, lambda i: 5 if i < 60 else 6)
    archive = tmp_path / "meter-diag.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(path, "tcp-payloads.jsonl")
        z.writestr("README.txt", "x")
    out = tmp_path / "probe.json"
    data = probe.run(str(archive), ["+0:10=5", "+3:00=6"], window_s=8, out=str(out))
    assert data["format"] == "a2probe" and data["capture"]["frames"] == 240
    top = data["candidates"][0]
    assert top["opcode"] == "5a 36" and top["offset"] == 6 and top["encoding"] == "u16" and top["verdict"] == "plausible"
    assert json.loads(out.read_text(encoding="utf-8"))["candidates"][0]["opcode"] == "5a 36"
    text = probe.format_report(data)
    assert "5a 36" in text and "never" not in text.split("\n")[0] and "decoder rule" in text


def test_time_parsing_forms():
    assert probe.parse_when("+1:30", start=100.0) == 190.0
    assert probe.parse_when("+45", start=100.0) == 145.0
    assert probe.parse_when("1800000000") == 1_800_000_000.0
    assert probe.parse_when("1800000000500") == 1_800_000_000.5
    clock = probe.parse_when("19:59:30", day="2026-10-15")
    assert abs(clock - probe.parse_when("2026-10-15T19:59:30")) < 1e-6   # same local instant
    with pytest.raises(ValueError):
        probe.parse_when("+1:30")                                       # relative needs a start
    with pytest.raises(ValueError):
        probe.parse_when("noon", start=1.0, day="2026-10-15")
    with pytest.raises(ValueError):
        probe.parse_known(["+1=-3"], start=1.0, day="2026-10-15")       # unsigned counters only
    with pytest.raises(ValueError):
        probe.parse_known(["+1"], start=1.0, day="2026-10-15")


def test_positions_cover_every_encoding():
    body = b"\x2a" + (300).to_bytes(2, "little") + (70_000).to_bytes(4, "little") + _varint(300)
    found = set(probe._positions(body, 300))
    assert (1, "u16") in found and (7, "varint") in found
    assert set(probe._positions(body, 42)) == {(0, "u8")}
    assert (3, "u32") in set(probe._positions(body, 70_000))
    assert probe.decode(body, 1, "u16") == 300 and probe.decode(body, 7, "varint") == 300 and probe.decode(body, 90, "u8") is None
