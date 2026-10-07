"""Background runner for the live meter and its embedded A2Tools capture engine."""
from __future__ import annotations

import threading
import copy
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
        self._session_save_lock = threading.Lock()
        self._last_checkpoint = 0.0
        self._stop = False
        self.replay_stop = threading.Event()
        self.lock = threading.Lock()
        self.session = CombatSession()
        self.metadata = {}
        self.capture_metadata = None
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
        if self.recorder is not None:
            try:
                self.recorder.release(remove=self.recorder is self._exported_recorder)
            except OSError as exc:
                self.diagnostics["recording_cleanup_error"] = str(exc)
        self.recorder = Recorder() if opts.get("record_packets") else None
        self.started_at = time.monotonic()
        self._last_checkpoint = self.started_at
        self._stop = False
        self.replay_stop = threading.Event()
        self.source_name = source
        if source in ("a2tools", "live"):
            from ..meter.metadata import CaptureMetadata
            self.capture_metadata = CaptureMetadata()
        else:
            self.capture_metadata = None
        self.scope = str(opts.get("scope") or "party")
        if self.scope not in ("party", "self", "all"):
            self.scope = "party"
        from ..combat.a2log import combat_mode
        self.session.pvp = combat_mode({"meta": self.metadata}) == "pvp"
        if self.session.pvp and self.scope == "all":
            self.error = "PvP capture requires Self or Party scope; opposing teams cannot be inferred from All observed players."
            return self.status()
        self.session.gap_seconds = min(120, max(3, int(opts.get("segment_gap") or 10)))
        self.session.automatic_splits = bool(opts.get("automatic_splits", True))
        self.session.final_boss_ids = {int(x) for x in opts.get("final_boss_ids",[]) if str(x).isdigit()}
        self.session.auto_finish = bool(opts.get("auto_finish",True))
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
        self._capture_loss_baseline = {k:self.session.capture_evidence.get(k, 0) for k in ("tcp_discarded_payloads", "tcp_unresolved_flows")}
        if self.session.capture_evidence.get("tcp_pending_bytes", 0):
            self._capture_loss_baseline["tcp_unresolved_flows"] += 1
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
                    self._checkpoint_session()
                    continue
                kind, *data = item
                if kind == "packet":
                    stream, payload, timestamp_ms = data
                    before_run = (self.session.run, self.session.run_closed)
                    with self.lock:
                        if engine is not None:
                            events = engine.consume(payload, timestamp_ms, stream)
                            self.session.observe(engine, events, timestamp_ms=timestamp_ms)
                        else:
                            events = list(decoder.feed(payload))
                            for event in events:
                                self.meter.add(event)
                        self.diagnostics["decoded_events"] += len(events)
                    if before_run != (self.session.run, self.session.run_closed):
                        self._save_session(active=True)
                elif kind == "error":
                    self.error = str(data[0])
                    break
                elif kind == "capture_started":
                    self.diagnostics["state"] = "capturing"
                elif kind == "capture_stats":
                    with self.lock:
                        self.diagnostics.update(data[0])
                        for key in ("transport_monitored", "tcp_discarded_payloads", "tcp_unresolved_flows", "tcp_pending_bytes"):
                            if key in data[0]:
                                value = data[0][key]
                                if key in ("tcp_discarded_payloads", "tcp_unresolved_flows"):
                                    value += self._capture_loss_baseline.get(key, 0)
                                self.session.capture_evidence[key] = value
                        if engine is not None and data[0].get("port"):
                            engine.set_server_port(int(data[0]["port"]))
                elif kind == "capture_stopped":
                    break
                self._checkpoint_session()
        except Exception as exc:
            self.error = f"Decoder failed: {type(exc).__name__}: {exc}"
        finally:
            stop_event.set()
            if self.packet_capture_thread:
                self.packet_capture_thread.join(timeout=3.0)
            self.diagnostics["state"] = "error" if self.error else "stopped"
            with self.lock:
                if self.error:
                    self.session.capture_evidence["capture_errors"] = self.session.capture_evidence.get("capture_errors", 0) + 1
                # Drain final counters after the capture thread has stopped.
                while not packets.empty():
                    final = packets.get_nowait()
                    if final[0] == "packet":
                        self.session.capture_evidence["capture_errors"] = self.session.capture_evidence.get("capture_errors", 0) + 1
                    if final[0] == "capture_stats":
                        for key in ("transport_monitored", "tcp_discarded_payloads", "tcp_unresolved_flows", "tcp_pending_bytes"):
                            if key in final[1]:
                                self.session.capture_evidence[key] = final[1][key] + self._capture_loss_baseline.get(key, 0) if key in ("tcp_discarded_payloads", "tcp_unresolved_flows") else final[1][key]
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

    def _checkpoint_session(self) -> None:
        now = time.monotonic()
        if now - self._last_checkpoint >= 15:
            self._last_checkpoint = now
            self._save_session(active=True)

    def _save_session(self, active: bool) -> None:
        if self.packet_engine is None or not self.session.records:
            return
        # Serialize snapshot and replacement together so an older periodic save
        # cannot overwrite the final snapshot after Stop.
        with self._session_save_lock:
            try:
                from ..combat.sessions import save
                doc = self.to_a2log()
                doc["meta"].update(capture_active=bool(active and self.running),
                                   checkpoint_at=time.time(), capture_scope=self.scope)
                self.saved_log = str(save(doc, self.session_file))
                self.diagnostics.pop("log_save_error", None)
            except (ValueError, OSError) as exc:
                self.diagnostics["log_save_error"] = str(exc)

    def _archive_diagnostics(self) -> None:
        self._save_session(active=False)
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
                if self.recorder is not None:
                    try:
                        self.recorder.release(remove=True)
                    except OSError as exc:
                        self.diagnostics["recording_cleanup_error"] = str(exc)
            self.diagnostics.pop("archive_error", None)
            return result

    def status(self) -> dict:
        with self.lock:
            snap = (self.session.snapshot(self.scope, self.segment_id, self.enemy_id)
                    if self.packet_engine is not None else self.meter.snapshot())
            diagnostic = dict(self.diagnostics)
        if diagnostic:
            diagnostic["elapsed"] = round(time.monotonic() - self.started_at, 1) if self.started_at else 0
        from ..meter.context import classify
        current = self.session.runs[self.session.run]
        context = classify(current.get("map_id"), current.get("instance_id"), self.session.pvp)
        return {"running": self.running, "source": self.source_name, "error": self.error,
                "automatic_context": context,
                "snapshot": snap, "diagnostics": diagnostic,
                "automatic_metadata": (self.capture_metadata.snapshot(self.packet_engine.local_profile.get("serverId") if self.packet_engine else None)
                                       if self.capture_metadata else {}),
                "diagnostic_export": self.diagnostic_export,
                "saved_log": self.saved_log,
                "run": {"id":self.session.run, "closed":self.session.run_closed, **self.session.runs[self.session.run]},
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
                from ..combat.a2log import combat_mode
                if self.session.records and combat_mode({"meta":metadata}) != combat_mode({"meta":self.metadata}):
                    raise ValueError("Clear session before switching between PvE and PvP.")
                self.metadata = {k: str(metadata.get(k) or ("unknown" if k == "encounter_type" else "")).strip()[:200] for k in ("game_patch", "difficulty", "encounter_type", "region", "zone")}
                self.session.pvp = combat_mode({"meta": self.metadata}) == "pvp"
            if "automatic_splits" in body:
                self.session.automatic_splits = bool(body["automatic_splits"])
            if body.get("segment_gap") is not None:
                self.session.gap_seconds = min(120, max(3, int(body["segment_gap"])))
            if body.get("scope") == "all" and self.session.pvp:
                raise ValueError("Use Self or Party scope for PvP capture.")
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

    def finish_run(self):
        with self.lock:
            self.session.finish_run()
        self._save_session(active=True)
        return self.status()

    def to_a2log(self, title: str | None = None) -> dict:
        # Detach quickly under the capture lock. Validation, summaries and upload
        # must never hold that lock while the decoder is receiving new packets.
        with self.lock:
            session = copy.deepcopy(self.session if self.packet_engine is not None else self.meter)
            metadata = dict(self.metadata)
            profile = dict(self.packet_engine.local_profile) if self.packet_engine else {}
            scope = self.scope
            collector = self.capture_metadata
        doc = session.to_a2log(scope, title) if isinstance(session, CombatSession) else session.to_a2log(title=title)
        return self._metadata(doc, metadata=metadata, profile=profile, collector=collector)

    def review_log(self) -> dict:
        with self.lock:
            session = copy.deepcopy(self.session if self.packet_engine is not None else self.meter)
            metadata = dict(self.metadata)
            profile = dict(self.packet_engine.local_profile) if self.packet_engine else {}
            scope, segment_id = self.scope, self.segment_id
            collector = self.capture_metadata
        doc = session.to_a2log(scope, segment_id=segment_id) if isinstance(session, CombatSession) else session.to_a2log()
        return self._metadata(doc, metadata=metadata, profile=profile, collector=collector)

    def _metadata(self, doc, *, metadata=None, profile=None, collector=None):
        metadata = self.metadata if metadata is None else metadata
        doc.setdefault("meta", {}).update(metadata)
        if collector:
            detected = collector.snapshot((profile or {}).get("serverId"))
            for key in ("installed_build", "installed_build_source"):
                if detected.get(key):
                    doc["meta"][key] = detected[key]
            if not doc["meta"].get("region") and detected.get("region"):
                doc["meta"].update(region=detected["region"], region_source=detected["region_source"])
            elif metadata.get("region"):
                doc["meta"]["region_source"] = "Manual override"
            for actor in doc.get("players", []):
                region = collector.snapshot(actor.get("server")).get("region")
                if region and not actor.get("region"):
                    actor["region"] = region
        for segment in doc.get("segments",[]):
            if (metadata.get("encounter_type") not in (None,"","unknown")
                    and segment.get("encounter_type","").startswith("pvp_") == metadata["encounter_type"].startswith("pvp_")):
                segment["encounter_type"] = metadata["encounter_type"]
                segment["encounter_type_source"] = "Manual override"
            for key in ("game_patch","difficulty","zone"):
                if metadata.get(key):
                    segment[key] = metadata[key]
                    if key == "zone":
                        segment["zone_source"] = "Manual override"
        if profile is None:
            profile = self.packet_engine.local_profile if self.packet_engine else {}
        if profile.get("serverId"):
            doc["meta"]["server"] = str(profile["serverId"])
        from ..combat.quality import assess
        for segment in doc.get("segments", []):
            segment["quality"] = assess(doc, segment)
        from ..combat.runs import summarize
        doc["run_analysis"] = summarize(doc)
        from ..combat.recaps import summarize as death_recaps
        doc["death_analysis"] = death_recaps(doc)
        from ..combat.insights import summarize as encounter_insights
        doc["encounter_insights"] = encounter_insights(doc)
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
