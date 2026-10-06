"""Background runner for the live meter and its embedded A2Tools capture engine."""
from __future__ import annotations

import threading
import queue
import time
from pathlib import Path

from ..meter import Meter, load_decoder, replay_source
from ..meter.a2parser.engine import MeterEngine as PacketMeterEngine
from ..meter.a2parser.capture import capture_packets
from ..meter import a2tools

DEMO = Path(__file__).resolve().parent.parent / "meter" / "demo_session.jsonl"


class Runner:
    def __init__(self) -> None:
        self.meter = Meter()
        self.thread: threading.Thread | None = None
        self.running = False
        self.error: str | None = None
        self.source_name: str | None = None
        self.packet_engine: PacketMeterEngine | None = None
        self.packet_stop: threading.Event | None = None
        self.packet_queue: queue.Queue | None = None
        self.packet_capture_thread: threading.Thread | None = None
        self.target_mode = "bossTargets"
        self.diagnostics: dict = {}
        self.started_at: float | None = None
        self.recorder = None
        self._stop = False
        self.replay_stop = threading.Event()
        self.lock = threading.Lock()

    def start(self, source: str = "replay", **opts) -> dict:
        self.stop()
        with self.lock:
            self.meter = Meter()
            self.packet_engine = None
        self.error = None
        self.diagnostics = {}
        from ..meter.diagnostics import Recorder
        self.recorder = Recorder() if opts.get("record_packets") else None
        self.started_at = time.monotonic()
        self._stop = False
        self.replay_stop = threading.Event()
        self.source_name = source
        try:
            if source == "a2tools":
                return self._start_a2tools(**opts)
            if source == "replay":
                path = opts.get("path") or str(DEMO)
                it = replay_source(path, speed=float(opts.get("speed", 1.0)), realtime=opts.get("realtime", True), stop_event=self.replay_stop)
            elif source == "live":
                dec = opts.get("decoder")
                if not dec:
                    self.error = "Import a decoder .py file, or select Live Capture to use the included A2Tools decoder."
                    return self.status()
                return self._start_a2tools(custom_decoder=load_decoder(dec), **opts)
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

    def _start_a2tools(self, **opts) -> dict:
        """Start the bundled A2Tools protocol engine on an Npcap/Scapy stream."""
        try:
            port = int(opts.get("port") or 50349)
        except (TypeError, ValueError):
            self.error = "game server port must be between 1 and 65535"
            return self.status()
        if not 1 <= port <= 65_535:
            self.error = "game server port must be between 1 and 65535"
            return self.status()
        decoder = opts.get("custom_decoder")
        self.packet_engine = None if decoder else PacketMeterEngine()
        if self.packet_engine is not None:
            self.packet_engine.set_server_port(port)
            if opts.get("character_name"):
                self.packet_engine.set_local_character_name(str(opts["character_name"]))
        self.target_mode = str(opts.get("target_mode") or "bossTargets")
        iface = str(opts.get("iface") or "").strip()
        host = str(opts.get("host") or "").strip()
        iface = None if iface.lower() in ("", "auto") else iface
        host = None if host.lower() in ("", "any", "auto") else host
        self.packet_stop = threading.Event()
        self.packet_queue = queue.Queue()
        self.running = True
        self.diagnostics = {"state": "starting", "packets": 0, "bytes": 0, "decoded_events": 0,
                            "auto_port": bool(opts.get("auto_port", decoder is None)), "port": None}
        self.thread = threading.Thread(target=self._run_a2tools,
                                       args=(iface, port, host, decoder, self.diagnostics["auto_port"]),
                                       daemon=True, name="a2tools-meter")
        self.thread.start()
        return self.status()

    def _run_a2tools(self, iface: str | None, port: int, host: str | None, decoder, auto_port: bool) -> None:
        assert self.packet_stop is not None and self.packet_queue is not None
        stop_event, packets, engine = self.packet_stop, self.packet_queue, self.packet_engine
        self.packet_capture_thread = threading.Thread(
            target=capture_packets, args=(stop_event, packets, iface, port, None, host, auto_port, self.recorder),
            daemon=True, name="a2tools-capture")
        self.packet_capture_thread.start()
        try:
            while not stop_event.is_set():
                try:
                    item = packets.get(timeout=0.5)
                except queue.Empty:
                    continue
                kind, *data = item
                if kind == "packet":
                    stream, payload, timestamp_ms = data
                    with self.lock:
                        if engine is not None:
                            events = engine.consume(payload, timestamp_ms, stream)
                        else:
                            events = list(decoder.feed(payload))
                            for event in events:
                                self.meter.add(event)
                        self.diagnostics["decoded_events"] += len(events)
                elif kind == "error":
                    self.error = str(data[0])
                    break
                elif kind == "capture_started":
                    self.diagnostics["state"] = "capturing"
                elif kind == "capture_stats":
                    with self.lock:
                        self.diagnostics.update(data[0])
                        if engine is not None and data[0].get("port"):
                            engine.set_server_port(int(data[0]["port"]))
                elif kind == "capture_stopped":
                    break
        except Exception as exc:
            self.error = f"Decoder failed: {type(exc).__name__}: {exc}"
        finally:
            stop_event.set()
            self.diagnostics["state"] = "error" if self.error else "stopped"
            self.running = False

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
        self.replay_stop.set()
        if self.packet_stop:
            self.packet_stop.set()
        t = self.thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        capture = self.packet_capture_thread
        if capture and capture.is_alive():
            capture.join(timeout=3.0)
        self.running = False
        if self.diagnostics:
            self.diagnostics["state"] = "stopped"

    def status(self) -> dict:
        with self.lock:
            snap = (a2tools.snapshot(self.packet_engine, self.target_mode)
                    if self.packet_engine is not None else self.meter.snapshot())
            diagnostic = dict(self.diagnostics)
        if diagnostic:
            diagnostic["elapsed"] = round(time.monotonic() - self.started_at, 1) if self.started_at else 0
        return {"running": self.running, "source": self.source_name, "error": self.error,
                "snapshot": snap, "diagnostics": diagnostic,
                "recording": {"enabled": self.recorder is not None,
                              **(self.recorder.snapshot(include_rows=False)[0] if self.recorder is not None else {"records": 0})}}

    def to_a2log(self, title: str | None = None) -> dict:
        with self.lock:
            if self.packet_engine is not None:
                return a2tools.to_a2log(self.packet_engine, self.target_mode, title)
            return self.meter.to_a2log(title=title)

    def has_data(self) -> bool:
        with self.lock:
            return bool(self.packet_engine and self.packet_engine.event_log) or bool(self.meter.players)


_RUNNER: Runner | None = None


def runner() -> Runner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = Runner()
    return _RUNNER
