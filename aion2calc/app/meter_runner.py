"""Background runner for the live meter and its embedded A2Tools capture engine."""
from __future__ import annotations

import threading
import queue
import time
import uuid
from pathlib import Path

from ..meter import Meter, load_decoder, replay_source
from ..meter.a2parser.engine import MeterEngine as PacketMeterEngine
from ..meter.a2parser.capture import capture_packets
from ..meter.session import CombatSession

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
        self.diagnostic_export = None
        self._exported_recorder = None
        self._diagnostic_lock = threading.Lock()
        self._stop = False
        self.replay_stop = threading.Event()
        self.lock = threading.Lock()
        self.session = CombatSession()
        self.metadata = {}
        self.scope = "party"
        self.segment_id = None
        self.enemy_id = None
        self.saved_log = None
        self.session_file = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.a2log.json"

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
        self.scope = str(opts.get("scope") or "party")
        if self.scope not in ("party", "self", "all"):
            self.scope = "party"
        self.session.gap_seconds = min(120, max(3, int(opts.get("segment_gap") or 10)))
        self.session.automatic_splits = bool(opts.get("automatic_splits", True))
        self.segment_id = None
        self.enemy_id = None
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
            self.session.begin_capture()
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
                            self.session.observe(engine, events)
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
            if self.packet_capture_thread:
                self.packet_capture_thread.join(timeout=3.0)
            self.diagnostics["state"] = "error" if self.error else "stopped"
            self.running = False
            self._archive_diagnostics()

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
        # Preserve the opted-in buffer before the next Start replaces it.
        # Repeated Stop/Quit calls must not create duplicate archives.
        self._archive_diagnostics()

    def _archive_diagnostics(self) -> None:
        if self.packet_engine is not None and self.session.records:
            try:
                from ..combat.sessions import save
                with self.lock:
                    doc = self._metadata(self.session.to_a2log(self.scope))
                self.saved_log = str(save(doc, self.session_file))
            except (ValueError, OSError) as exc:
                self.diagnostics["log_save_error"] = str(exc)
        if self.recorder is not None and self.recorder is not self._exported_recorder:
            if self.recorder.snapshot(include_rows=False)[0]["records"]:
                try:
                    self.export_diagnostics()
                except OSError as exc:
                    self.diagnostics["archive_error"] = str(exc)

    def export_diagnostics(self) -> dict:
        with self._diagnostic_lock:
            if self.recorder is not None and self.recorder is self._exported_recorder and self.diagnostic_export and not self.running:
                return self.diagnostic_export
            from ..meter.diagnostics import export
            result = export(self.status(), self.recorder)
            self.diagnostic_export = result
            if not self.running:
                self._exported_recorder = self.recorder
            self.diagnostics.pop("archive_error", None)
            return result

    def status(self) -> dict:
        with self.lock:
            snap = (self.session.snapshot(self.scope, self.segment_id, self.enemy_id)
                    if self.packet_engine is not None else self.meter.snapshot())
            diagnostic = dict(self.diagnostics)
        if diagnostic:
            diagnostic["elapsed"] = round(time.monotonic() - self.started_at, 1) if self.started_at else 0
        return {"running": self.running, "source": self.source_name, "error": self.error,
                "snapshot": snap, "diagnostics": diagnostic,
                "diagnostic_export": self.diagnostic_export,
                "saved_log": self.saved_log,
                "identity": ({"id": self.packet_engine.local_player_id,
                              "name": self.packet_engine.names.get(self.packet_engine.local_player_id),
                              "verified": self.packet_engine.local_identity_from_game,
                              **self.packet_engine.local_profile} if self.packet_engine else None),
                "recording": {"enabled": self.recorder is not None,
                              **(self.recorder.snapshot(include_rows=False)[0] if self.recorder is not None else {"records": 0})}}

    def configure_view(self, body: dict) -> dict:
        with self.lock:
            if "metadata" in body:
                from ..combat.a2log import ENCOUNTER_TYPES
                metadata = body["metadata"]
                if (metadata.get("encounter_type") or "unknown") not in ENCOUNTER_TYPES:
                    raise ValueError("Invalid encounter type")
                if self.running:
                    raise ValueError("Stop capture before changing session classification")
                self.metadata = {k: str(metadata.get(k) or ("unknown" if k == "encounter_type" else "")).strip()[:200] for k in ("game_patch", "difficulty", "encounter_type", "region")}
            if "automatic_splits" in body:
                self.session.automatic_splits = bool(body["automatic_splits"])
            if body.get("segment_gap") is not None:
                self.session.gap_seconds = min(120, max(3, int(body["segment_gap"])))
            if body.get("scope") in ("party", "self", "all"):
                self.scope = body["scope"]
            if "segment" in body:
                self.segment_id = body["segment"] or None
                self.enemy_id = None
            if "enemy" in body:
                self.enemy_id = body["enemy"] or None
            if body.get("character_name") is not None and self.packet_engine is not None:
                self.packet_engine.set_local_character_name(body["character_name"])
                self.session.observe(self.packet_engine, [])
        return self.status()

    def split_now(self) -> dict:
        with self.lock:
            self.session.split_now()
            self.segment_id = None
        return self.status()

    def clear_session(self) -> dict:
        if self.running:
            raise ValueError("Stop capture before clearing session history.")
        with self.lock:
            self.session = CombatSession()
            self.session_file = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.a2log.json"
            self.saved_log = None
            self.segment_id = self.enemy_id = None
        return self.status()

    def to_a2log(self, title: str | None = None) -> dict:
        with self.lock:
            if self.packet_engine is not None:
                return self._metadata(self.session.to_a2log(self.scope, title))
            return self._metadata(self.meter.to_a2log(title=title))

    def review_log(self) -> dict:
        with self.lock:
            if self.packet_engine is not None:
                return self._metadata(self.session.to_a2log(self.scope, segment_id=self.segment_id))
            return self._metadata(self.meter.to_a2log())

    def _metadata(self, doc):
        doc.setdefault("meta", {}).update(self.metadata)
        profile = self.packet_engine.local_profile if self.packet_engine else {}
        if profile.get("serverId"):
            doc["meta"]["server"] = str(profile["serverId"])
        return doc

    def has_data(self) -> bool:
        with self.lock:
            return bool(self.packet_engine and self.session.records) or bool(self.meter.players)


_RUNNER: Runner | None = None


def runner() -> Runner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = Runner()
    return _RUNNER
