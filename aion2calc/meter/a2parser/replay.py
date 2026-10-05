"""Read the upstream diagnostic replay format: TIMESTAMP|STREAMKEY|HEX_DATA."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .engine import MeterEngine
from .framing import iter_packets


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    timestamp: str
    stream_key: str
    source_port: int
    payload: bytes


def parse_timestamp_ms(value: str) -> int | None:
    """Parse capture timestamps as epoch milliseconds, including ISO-8601."""
    text = value.strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        # Capture tools have emitted both epoch seconds and epoch milliseconds.
        return int(numeric * 1000) if abs(numeric) < 100_000_000_000 else int(numeric)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Naive timestamps represent local capture time, as they do in the upstream
    # diagnostic files. astimezone() applies the machine's local UTC offset.
    return int(parsed.astimezone().timestamp() * 1000)


def read_capture(path: str | Path) -> Iterator[ReplayRecord]:
    """Yield valid records while skipping comments and malformed capture lines."""
    with Path(path).open("r", encoding="utf-8", errors="replace") as capture:
        for line in capture:
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            timestamp, stream_key, hex_data = parts
            try:
                payload = bytes.fromhex(hex_data)
            except ValueError:
                continue
            try:
                source_port = int(stream_key.rsplit(":", 1)[-1])
            except ValueError:
                source_port = 55_555
            if not 0 <= source_port <= 65_535:
                source_port = 55_555
            yield ReplayRecord(timestamp, stream_key, source_port, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect an A2Tools packet replay file")
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    records = packets = byte_count = 0
    engine = MeterEngine()
    for record in read_capture(args.capture):
        records += 1
        byte_count += len(record.payload)
        packets += sum(1 for _ in iter_packets(record.payload))
        timestamp_ms = parse_timestamp_ms(record.timestamp)
        engine.consume(record.payload, timestamp_ms, record.stream_key)
    print(f"Capture records: {records}")
    print(f"Framed packets: {packets}")
    print(f"Payload bytes: {byte_count}")
    result = engine.snapshot()
    print(f"Recognized damage records: {engine.damage_events}")
    print(f"Selected target: {result['targetName']} ({result['targetId']})")
    print(f"Total damage: {result['totalDamage']:,}")
    print(f"DPS: {result['dps']:,.1f}")
    for actor in result["actors"]:
        print(f"  {actor['nickname']:<20} {actor['damage']:>12,}  {actor['dps']:>10,.1f} DPS")


if __name__ == "__main__":
    main()
