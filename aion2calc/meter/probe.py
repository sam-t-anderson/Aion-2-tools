"""Value probe: which undecoded record carries a number you can see in the game?

A read-only investigation tool over a **diagnostic capture** (the ZIP the Live Meter's Export
diagnostics writes with *raw TCP recording* on, or its ``tcp-payloads.jsonl``). You tell it the
values you saw in the game and when -- hidden cubes collected, Odyle Energy, a quest or entry
counter -- and it searches every server-to-client record near those moments for a field that held
exactly those numbers, then checks how that field behaved across the whole capture. The result is a
ranked list of candidates (opcode, byte offset, encoding), each with the evidence behind it. It
decodes nothing new on its own: a candidate becomes a decoder rule only after a second, independent
capture confirms it, and this module never touches the live decoder.

Safety: the capture is untrusted input. Rows are parsed defensively, the capture is bounded in size,
nothing is executed or written unless an output path is given, and no network is used.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import json
import re
from pathlib import Path
import zipfile

from .a2parser.parser import walk, _damage_frames, read_varint

MAX_CAPTURE_BYTES = 600 * 1024 * 1024      # of payload hex, before decoding
MAX_PENDING_BYTES = 4 * 1024 * 1024        # one flow's unframed backlog before it is dropped
DEFAULT_WINDOW_S = 20.0
ENCODINGS = ("u8", "u16", "u32", "varint")
_TEXT_PREFIXES = (b"{", b"[", b"HTTP/", b"GET ", b"POST ", b"PUT ", b"\"")
_PRINTABLE = frozenset(range(0x20, 0x7F))


@dataclass
class Observation:
    at: float          # epoch seconds
    value: int
    label: str = ""


@dataclass
class Frame:
    at: float
    opcode: int
    body: bytes


@dataclass
class Candidate:
    opcode: int
    offset: int
    encoding: str
    matched: list = field(default_factory=list)       # observation indices with a frame holding the value nearby
    agreement: float = 0.0                              # share of observations whose latest value before the window's end is the observed one
    frames: int = 0                                     # frames of this opcode long enough to hold the field
    distinct_values: int = 0
    first_value: int | None = None
    last_value: int | None = None
    series: list = field(default_factory=list)         # (at, value) samples, bounded

    @property
    def opcode_hex(self) -> str:
        return "%02x %02x" % (self.opcode >> 8, self.opcode & 0xFF)


def parse_when(text: str, *, start: float | None = None, day: str | None = None) -> float:
    """``HH:MM[:SS]`` (local time on the capture's day), ``YYYY-MM-DDTHH:MM[:SS]`` (local, or with
    a zone), epoch seconds, or ``+M:SS`` / ``+S`` after the capture's first packet."""
    text = str(text).strip()
    if text.startswith("+"):
        if start is None:
            raise ValueError("a relative time needs the capture's start")
        parts = text[1:].split(":")
        if not parts or not all(p.isdigit() for p in parts) or len(parts) > 3:
            raise ValueError(f"bad relative time {text!r}")
        seconds = 0
        for p in parts:
            seconds = seconds * 60 + int(p)
        return start + seconds
    if re.fullmatch(r"\d{9,13}(\.\d+)?", text):
        value = float(text)
        return value / 1000 if value > 1e11 else value
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
        if day is None:
            raise ValueError("a clock time needs the capture's day")
        local = datetime.strptime(f"{day} {text}", "%Y-%m-%d %H:%M:%S" if text.count(":") == 2 else "%Y-%m-%d %H:%M")
        return local.astimezone().timestamp()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"unrecognised time {text!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.timestamp()


def parse_known(items, *, start: float | None, day: str | None) -> list[Observation]:
    """``WHEN=VALUE[:label]`` items into observations, oldest first."""
    out = []
    for item in items:
        text = str(item)
        if "=" not in text:
            raise ValueError(f"expected WHEN=VALUE, got {text!r}")
        when, _, rest = text.partition("=")
        value, _, label = rest.partition(":")
        if not re.fullmatch(r"-?\d+", value.strip()):
            raise ValueError(f"the value in {text!r} must be a whole number")
        number = int(value)
        if number < 0:
            raise ValueError("values are unsigned counters; negative numbers cannot be probed")
        out.append(Observation(parse_when(when, start=start, day=day), number, label.strip()))
    out.sort(key=lambda o: o.at)
    return out


def _rows(source: Path):
    """Yield the capture's rows from a ZIP (its tcp-payloads.jsonl) or a .jsonl file."""
    source = Path(source)
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            names = [n for n in archive.namelist() if n.endswith("tcp-payloads.jsonl")]
            if not names:
                raise ValueError("the ZIP holds no tcp-payloads.jsonl (export diagnostics with raw TCP recording on)")
            info = archive.getinfo(names[0])
            if info.file_size > MAX_CAPTURE_BYTES:
                raise ValueError("capture larger than the probe's limit")
            with archive.open(names[0]) as stream:
                yield from io.TextIOWrapper(stream, encoding="utf-8", errors="replace")
    else:
        if source.stat().st_size > MAX_CAPTURE_BYTES:
            raise ValueError("capture larger than the probe's limit")
        with source.open("r", encoding="utf-8", errors="replace") as stream:
            yield from stream


def load_frames(source: Path, *, server_port: int | None = None) -> tuple[list[Frame], dict]:
    """Reassemble the server-to-client packets of a capture into opcode-tagged frames."""
    pending: dict = {}
    frames: list[Frame] = []
    info = {"rows": 0, "skipped_rows": 0, "text_rows": 0, "flows": set(), "first_at": None, "last_at": None}
    for line in _rows(source):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            at_ms, sport, dport = int(row["timestamp_ms"]), int(row["sport"]), int(row["dport"])
            payload = bytes.fromhex(row["payload_hex"])
        except (ValueError, TypeError, KeyError):
            info["skipped_rows"] += 1
            continue
        info["rows"] += 1
        if server_port is not None:
            if sport != server_port:
                continue
        elif sport > dport:
            continue                       # client -> server: the game server listens on the lower, fixed port
        if payload[:5].startswith(_TEXT_PREFIXES) or (len(payload) >= 8 and all(b in _PRINTABLE for b in payload[:8])):
            info["text_rows"] += 1         # another program's text protocol on the interface, not the game
            continue
        key = (row.get("src"), sport, row.get("dst"), dport)
        info["flows"].add(key)
        buf = pending.setdefault(key, bytearray())
        buf.extend(payload)
        framing = walk(bytes(buf))
        if framing.consumed == 0:
            if len(buf) > MAX_PENDING_BYTES:
                del buf[:]
            continue
        complete = bytes(buf[:framing.consumed])
        del buf[:framing.consumed]
        at = at_ms / 1000
        info["first_at"] = at if info["first_at"] is None else min(info["first_at"], at)
        info["last_at"] = at if info["last_at"] is None else max(info["last_at"], at)
        for frame in _damage_frames(complete, inner=False):
            length = read_varint(frame, 0)
            if length.length <= 0 or length.length + 2 > len(frame):
                continue
            pos = length.length
            frames.append(Frame(at, (frame[pos] << 8) | frame[pos + 1], bytes(frame[pos + 2:])))
    frames.sort(key=lambda f: f.at)
    info["flows"] = len(info["flows"])
    info["frames"] = len(frames)
    return frames, info


def decode(body: bytes, offset: int, encoding: str) -> int | None:
    if encoding == "u8":
        return body[offset] if offset < len(body) else None
    if encoding == "u16":
        return int.from_bytes(body[offset:offset + 2], "little") if offset + 2 <= len(body) else None
    if encoding == "u32":
        return int.from_bytes(body[offset:offset + 4], "little") if offset + 4 <= len(body) else None
    if encoding == "varint":
        if offset >= len(body):
            return None
        parsed = read_varint(body, offset)
        return parsed.value if parsed.length > 0 and parsed.value >= 0 else None
    raise ValueError(encoding)


def _positions(body: bytes, value: int):
    """Every (offset, encoding) at which ``value`` sits in ``body``."""
    if value < 256:
        b = bytes([value])
        start = 0
        while (i := body.find(b, start)) >= 0:
            yield i, "u8"
            start = i + 1
    if value < 65536:
        b = value.to_bytes(2, "little")
        start = 0
        while (i := body.find(b, start)) >= 0:
            yield i, "u16"
            start = i + 1
    if value < 2 ** 32:
        b = value.to_bytes(4, "little")
        start = 0
        while (i := body.find(b, start)) >= 0:
            yield i, "u32"
            start = i + 1
    # varint (LEB128, as the game's records use)
    enc = bytearray()
    v = value
    while True:
        byte = v & 0x7F
        v >>= 7
        if v:
            enc.append(byte | 0x80)
        else:
            enc.append(byte)
            break
    if len(enc) > 1:                       # one-byte varints are the u8 case
        start = 0
        while (i := body.find(bytes(enc), start)) >= 0:
            yield i, "varint"
            start = i + 1


def probe(frames: list[Frame], observations: list[Observation], *, window_s: float = DEFAULT_WINDOW_S,
          limit: int = 25, series_cap: int = 400) -> list[Candidate]:
    """Rank the (opcode, offset, encoding) fields that held the observed values when they were observed."""
    if not observations:
        raise ValueError("give at least one observation (WHEN=VALUE)")
    by_key: dict[tuple, Candidate] = {}
    # Pass 1: fields holding the observed value in a frame near its observation.
    for index, obs in enumerate(observations):
        lo, hi = obs.at - window_s, obs.at + window_s
        for frame in frames:
            if frame.at < lo:
                continue
            if frame.at > hi:
                break
            for offset, encoding in _positions(frame.body, obs.value):
                cand = by_key.setdefault((frame.opcode, offset, encoding), Candidate(frame.opcode, offset, encoding))
                if not cand.matched or cand.matched[-1] != index:
                    cand.matched.append(index)
    if not by_key:
        return []
    # Pass 2: how each candidate field behaves over the whole capture.
    by_opcode: dict[int, list[Candidate]] = defaultdict(list)
    for cand in by_key.values():
        by_opcode[cand.opcode].append(cand)
    values_seen: dict[tuple, set] = defaultdict(set)
    for frame in frames:
        for cand in by_opcode.get(frame.opcode, ()):
            value = decode(frame.body, cand.offset, cand.encoding)
            if value is None:
                continue
            cand.frames += 1
            values_seen[(cand.opcode, cand.offset, cand.encoding)].add(value)
            if cand.first_value is None:
                cand.first_value = value
            cand.last_value = value
            if len(cand.series) < series_cap:
                cand.series.append((frame.at, value))
    for cand in by_key.values():
        cand.distinct_values = len(values_seen[(cand.opcode, cand.offset, cand.encoding)])
        agree = 0
        for obs in observations:
            latest = None
            for at, value in cand.series:
                if at <= obs.at + window_s:
                    latest = value
                else:
                    break
            agree += latest == obs.value
        cand.agreement = agree / len(observations)
    # Ties between readings of the same bytes (a counter below 256 matches as a byte and as the low
    # byte of a 16-bit field with identical evidence) go to the wider field: a narrower read is
    # implied by it, and a game counter is rarely a lone byte.
    width = {"u32": 4, "varint": 3, "u16": 2, "u8": 1}
    ranked = sorted(by_key.values(), key=lambda c: (-len(c.matched), -c.agreement, c.distinct_values, c.frames,
                                                    c.opcode, c.offset, -width[c.encoding]))
    return ranked[:limit]


def verdict(cand: Candidate, observations: list[Observation]) -> str:
    distinct_obs = len({observations[i].value for i in cand.matched})
    if len(cand.matched) == len(observations) and distinct_obs >= 3 and cand.agreement == 1.0:
        return "strong"
    if len(cand.matched) >= 2 and distinct_obs >= 2 and cand.agreement >= 0.5:
        return "plausible"
    return "weak"


def report(source: Path, candidates: list[Candidate], observations: list[Observation], info: dict, window_s: float) -> dict:
    return {"format": "a2probe", "version": 1, "source": str(source), "window_seconds": window_s,
            "capture": {k: info.get(k) for k in ("rows", "skipped_rows", "text_rows", "flows", "frames", "first_at", "last_at")},
            "observations": [{"at": o.at, "value": o.value, "label": o.label} for o in observations],
            "candidates": [{"opcode": c.opcode_hex, "offset": c.offset, "encoding": c.encoding,
                            "matched_observations": c.matched, "agreement": round(c.agreement, 3),
                            "frames": c.frames, "distinct_values": c.distinct_values,
                            "first_value": c.first_value, "last_value": c.last_value,
                            "verdict": verdict(c, observations),
                            "series_sample": [[round(at, 3), v] for at, v in c.series[:12]]} for c in candidates],
            "note": ("Candidates are fields that held the observed numbers when they were observed; nothing here is a "
                     "decoder rule. Confirm a candidate on a second, independent capture (different values, different "
                     "session) before reading it live, and prefer the candidate with the fewest distinct values that still "
                     "agrees with every observation.")}


def format_report(data: dict) -> str:
    cap = data["capture"]
    lines = [f"Value probe over {data['source']}",
             f"  {cap['rows']} rows, {cap['frames']} server records in {cap['flows']} flow(s); "
             f"{cap['text_rows']} text rows and {cap['skipped_rows']} malformed rows ignored; window ±{data['window_seconds']:g} s"]
    for o in data["observations"]:
        when = datetime.fromtimestamp(o["at"], tz=timezone.utc).strftime("%H:%M:%S UTC")
        lines.append(f"  observed {o['value']}{' (' + o['label'] + ')' if o['label'] else ''} at {when}")
    if not data["candidates"]:
        lines.append("No record held any observed value near its observation: widen --window, check the times, "
                     "or the value may not travel as a plain integer.")
        return "\n".join(lines)
    lines.append(f"{'verdict':9} {'opcode':7} {'offset':>6} {'enc':6} {'matched':>7} {'agree':>5} {'frames':>7} {'values':>6}  first -> last")
    for c in data["candidates"]:
        lines.append(f"{c['verdict']:9} {c['opcode']:7} {c['offset']:>6} {c['encoding']:6} "
                     f"{len(c['matched_observations']):>3}/{len(data['observations']):<3} {c['agreement']:>5.2f} {c['frames']:>7} {c['distinct_values']:>6}  "
                     f"{c['first_value']} -> {c['last_value']}")
    lines.append(data["note"])
    return "\n".join(lines)


def run(source: str, known: list[str], *, window_s: float = DEFAULT_WINDOW_S, server_port: int | None = None,
        limit: int = 25, out: str | None = None) -> dict:
    path = Path(source)
    frames, info = load_frames(path, server_port=server_port)
    if not frames:
        raise ValueError("no server records could be framed from this capture")
    start = info["first_at"]
    day = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
    observations = parse_known(known, start=start, day=day)
    candidates = probe(frames, observations, window_s=window_s, limit=limit)
    data = report(path, candidates, observations, info, window_s)
    if out:
        Path(out).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data
