"""Event sources: a decoded-JSONL replay (for development/demos) and a live/raw capture that feeds
frames through a decoder."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .events import CombatEvent


def replay_source(path, speed: float = 1.0, realtime: bool = False, stop_event=None):
    """Yield decoded :class:`CombatEvent`s from a JSON-lines file (one event object per line).

    With ``realtime`` the events are paced by their own ``t`` (divided by ``speed``), to feel like a
    live fight; otherwise they come as fast as possible (for tests)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(CombatEvent.from_dict(json.loads(line)))
    rows.sort(key=lambda e: e.t)
    base = rows[0].t if rows else 0.0
    start = time.monotonic()
    for ev in rows:
        if stop_event is not None and stop_event.is_set():
            return
        if realtime:
            delay = (ev.t - base) / max(1e-6, speed) - (time.monotonic() - start)
            if delay > 0:
                if stop_event is not None:
                    if stop_event.wait(delay):
                        return
                else:
                    time.sleep(delay)
        yield ev


def capture_source(decoder, frames):
    """Yield events by feeding each raw frame from ``frames`` (live sniff or a file) to ``decoder``."""
    for frame in frames:
        for ev in decoder.feed(frame):
            yield ev


def live_frames(iface: str | None = None, bpf: str | None = None, host: str | None = None, port: int | None = None):
    """Yield raw transport payloads from a live capture. Requires scapy and capture privileges; the
    import is guarded so the rest of the meter works without it."""
    try:
        from scapy.all import Raw, sniff
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("live capture needs scapy (pip install scapy) and permission to capture packets") from e
    import queue
    import threading

    parts = [p for p in [f"host {host}" if host else "", f"port {port}" if port else "tcp"] if p]
    filt = bpf or " and ".join(parts)
    q: "queue.Queue[bytes]" = queue.Queue()

    def _cb(pkt):
        if Raw in pkt:
            q.put(bytes(pkt[Raw].load))

    threading.Thread(target=lambda: sniff(iface=iface, filter=filt or None, prn=_cb, store=False), daemon=True).start()
    while True:
        yield q.get()
