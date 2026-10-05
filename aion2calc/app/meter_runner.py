"""Background runner behind the app's /api/meter endpoints: it pulls combat events from a source
(the demo replay, or a live capture through the user's decoder) into a :class:`Meter` the UI polls."""
from __future__ import annotations

import threading
from pathlib import Path

from ..meter import Meter, capture_source, live_frames, load_decoder, replay_source

DEMO = Path(__file__).resolve().parent.parent / "meter" / "demo_session.jsonl"


class Runner:
    def __init__(self) -> None:
        self.meter = Meter()
        self.thread: threading.Thread | None = None
        self.running = False
        self.error: str | None = None
        self.source_name: str | None = None
        self._stop = False
        self.lock = threading.Lock()

    def start(self, source: str = "replay", **opts) -> dict:
        self.stop()
        with self.lock:
            self.meter = Meter()
        self.error = None
        self._stop = False
        self.source_name = source
        try:
            if source == "replay":
                path = opts.get("path") or str(DEMO)
                it = replay_source(path, speed=float(opts.get("speed", 1.0)), realtime=opts.get("realtime", True))
            elif source == "live":
                dec = opts.get("decoder")
                if not dec:
                    self.error = "live capture needs a decoder module (the game protocol decoder is not bundled — supply your own)"
                    return self.status()
                it = capture_source(load_decoder(dec), live_frames(iface=opts.get("iface"), host=opts.get("host"), port=opts.get("port")))
            else:
                self.error = f"unknown source {source!r}"
                return self.status()
        except Exception as e:  # noqa: BLE001 - bad decoder spec etc.
            self.error = f"{type(e).__name__}: {e}"
            return self.status()
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(it,), daemon=True, name="meter")
        self.thread.start()
        return self.status()

    def _run(self, it) -> None:
        try:
            for ev in it:
                if self._stop:
                    break
                with self.lock:
                    self.meter.add(ev)
        except Exception as e:  # noqa: BLE001 - a live source may fail (no scapy, no privileges)
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.running = False

    def stop(self) -> None:
        self._stop = True
        t = self.thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self.running = False

    def status(self) -> dict:
        with self.lock:
            snap = self.meter.snapshot()
        return {"running": self.running, "source": self.source_name, "error": self.error, "snapshot": snap}

    def to_a2log(self, title: str | None = None) -> dict:
        with self.lock:
            return self.meter.to_a2log(title=title)


_RUNNER: Runner | None = None


def runner() -> Runner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = Runner()
    return _RUNNER
