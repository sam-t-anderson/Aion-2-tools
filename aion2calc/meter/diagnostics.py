"""Opt-in TCP diagnostics, streamed to disk without a session record limit."""
from __future__ import annotations

from collections import deque
import json
import os
import threading
import time
import uuid
import zipfile


class Recorder:
    def __init__(self, max_bytes: int | None = None, max_records: int | None = None):
        self.rows = deque()
        self.bytes = 0
        self.max_bytes = max_bytes
        self.max_records = max_records
        self.discarded = 0
        self.lock = threading.Lock()
        self.count = 0
        self.spool_bytes = 0
        self.error = None
        self.path = None
        self.writer = None
        # Explicit limits remain available for small callers. Live capture uses
        # the default disk recorder; neither record count nor payload size rolls over.
        if max_bytes is None and max_records is None:
            from ..paths import home
            folder = home() / "diagnostics"
            folder.mkdir(parents=True, exist_ok=True)
            self.path = folder / f"tcp-session-{uuid.uuid4().hex}.jsonl"
            self.writer = self.path.open("xb", buffering=0)

    def record(self, key: tuple, sequence: int, flags: int, payload: bytes, timestamp_ms: int):
        if not payload or (self.max_bytes is not None and len(payload) > self.max_bytes):
            return
        interface, src, sport, dst, dport = key
        row = {"timestamp_ms": timestamp_ms, "interface": interface, "src": src,
               "sport": sport, "dst": dst, "dport": dport,
               "sequence": sequence, "flags": flags, "payload_hex": payload.hex()}
        with self.lock:
            if self.path is not None:
                if self.error:
                    self.discarded += 1
                    return
                data = (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8")
                try:
                    if self.writer is None:
                        raise OSError("Diagnostic recorder is closed")
                    if self.writer.write(data) != len(data):
                        raise OSError("Incomplete diagnostic disk write")
                except OSError as exc:
                    self.error = str(exc)
                    self.discarded += 1
                    return
                self.count += 1
                self.bytes += len(payload)
                self.spool_bytes += len(data)
                return
            self.rows.append((len(payload), row))
            self.bytes += len(payload)
            while ((self.max_bytes is not None and self.bytes > self.max_bytes)
                   or (self.max_records is not None and len(self.rows) > self.max_records)):
                size, _ = self.rows.popleft()
                self.bytes -= size
                self.discarded += 1

    def snapshot(self, include_rows: bool = True):
        with self.lock:
            if self.path is not None:
                return {"records": self.count, "payload_bytes": self.bytes,
                        "discarded_records": self.discarded, "storage": "disk",
                        "record_limit": None, "disk_bytes": self.spool_bytes,
                        "error": self.error}, []
            return {"records": len(self.rows), "payload_bytes": self.bytes,
                    "discarded_records": self.discarded}, ([dict(row) for _, row in self.rows] if include_rows else [])

    def archive_payloads(self, archive):
        """Export a fixed prefix while capture can continue appending to disk."""
        with self.lock:
            counts, rows = self._archive_snapshot()
            size = self.spool_bytes
        with archive.open("tcp-payloads.jsonl", "w", force_zip64=True) as target:
            if self.path is not None:
                with self.path.open("rb") as source:
                    while size:
                        chunk = source.read(min(size, 1024 * 1024))
                        if not chunk:
                            raise OSError("Diagnostic recording ended before its recorded byte count")
                        target.write(chunk)
                        size -= len(chunk)
            else:
                for row in rows:
                    target.write((json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8"))
        return counts

    def _archive_snapshot(self):
        # Caller holds lock; do not reenter snapshot's lock.
        if self.path is not None:
            return {"records": self.count, "payload_bytes": self.bytes,
                    "discarded_records": self.discarded, "storage": "disk",
                    "record_limit": None, "disk_bytes": self.spool_bytes,
                    "error": self.error}, []
        return {"records": len(self.rows), "payload_bytes": self.bytes,
                "discarded_records": self.discarded}, [dict(row) for _, row in self.rows]

    def release(self, remove=False):
        """Close a replaced recorder; remove raw data only after a successful archive."""
        with self.lock:
            if self.writer is not None:
                self.writer.close()
                self.writer = None
            if remove and self.path is not None:
                self.path.unlink(missing_ok=True)


def export(status: dict, recorder: Recorder | None):
    from .. import __version__
    from ..paths import home
    folder = home() / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"meter-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.zip"
    # Omit the display snapshot containing character names. Payloads, if opted in,
    # remain raw and may themselves contain identifying game/network information.
    metadata = {"app_version": __version__, "source": status.get("source"),
                "running": status.get("running"), "error": status.get("error"),
                "capture": status.get("diagnostics")}
    partial = path.with_suffix(".zip.part")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if recorder:
            recording = recorder.archive_payloads(archive)
        else:
            recording = {"records": 0}
            archive.writestr("tcp-payloads.jsonl", "")
        metadata["recording"] = recording
        archive.writestr("diagnostics.json", json.dumps(metadata, indent=2))
        archive.writestr("README.txt", "TCP payloads were recorded only if explicitly enabled before Start.\n"
                         "Live capture records the full session to disk without a record or size cap.\n"
                         "Recording is limited by available disk space; check diagnostics.json for write errors.\n"
                         "Raw payloads may contain character names, IP addresses and other network traffic.\n"
                         "Review before sharing. Nothing is uploaded automatically.\n"
                         "These are original TCP segments: use sequence numbers to reassemble each direction.\n")
    os.replace(partial, path)
    from urllib.parse import quote
    return {"file": str(path), **recording,
            "download_url": "/api/meter/diagnostics?name=" + quote(path.name)}
