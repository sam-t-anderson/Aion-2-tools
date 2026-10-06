"""Optional, bounded TCP payload recording for diagnosing decoder failures."""
from __future__ import annotations

from collections import deque
import json
import threading
import time
import uuid
import zipfile


class Recorder:
    def __init__(self, max_bytes: int = 4 * 1024 * 1024, max_records: int = 4096):
        self.rows = deque()
        self.bytes = 0
        self.max_bytes = max_bytes
        self.max_records = max_records
        self.discarded = 0
        self.lock = threading.Lock()

    def record(self, key: tuple, sequence: int, flags: int, payload: bytes, timestamp_ms: int):
        if not payload or len(payload) > self.max_bytes:
            return
        interface, src, sport, dst, dport = key
        row = {"timestamp_ms": timestamp_ms, "interface": interface, "src": src,
               "sport": sport, "dst": dst, "dport": dport,
               "sequence": sequence, "flags": flags, "payload_hex": payload.hex()}
        with self.lock:
            self.rows.append((len(payload), row))
            self.bytes += len(payload)
            while self.bytes > self.max_bytes or len(self.rows) > self.max_records:
                size, _ = self.rows.popleft()
                self.bytes -= size
                self.discarded += 1

    def snapshot(self, include_rows: bool = True):
        with self.lock:
            return {"records": len(self.rows), "payload_bytes": self.bytes,
                    "discarded_records": self.discarded}, ([dict(row) for _, row in self.rows] if include_rows else [])


def export(status: dict, recorder: Recorder | None):
    from .. import __version__
    from ..paths import home
    folder = home() / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"meter-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.zip"
    recording, rows = recorder.snapshot() if recorder else ({"records": 0}, [])
    # Omit the display snapshot containing character names. Payloads, if opted in,
    # remain raw and may themselves contain identifying game/network information.
    metadata = {"app_version": __version__, "source": status.get("source"),
                "running": status.get("running"), "error": status.get("error"),
                "capture": status.get("diagnostics"), "recording": recording}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(metadata, indent=2))
        archive.writestr("tcp-payloads.jsonl", "\n".join(json.dumps(row, separators=(",", ":")) for row in rows))
        archive.writestr("README.txt", "TCP payloads were recorded only if explicitly enabled before Start.\n"
                         "The newest records are retained up to 4 MiB or 4096 records.\n"
                         "Raw payloads may contain character names, IP addresses and other network traffic.\n"
                         "Review before sharing. Nothing is uploaded automatically.\n"
                         "These are original TCP segments: use sequence numbers to reassemble each direction.\n")
    from urllib.parse import quote
    return {"file": str(path), "records": len(rows),
            "download_url": "/api/meter/diagnostics?name=" + quote(path.name)}
