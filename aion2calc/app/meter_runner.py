"""Background runner for the live meter and its embedded A2Tools capture engine."""
from __future__ import annotations

import threading
import copy
import queue
import struct
import time
import uuid
from pathlib import Path

from ..meter import CombatEvent, Meter, load_decoder, replay_source
from ..meter.a2parser.engine import MeterEngine as PacketMeterEngine
from ..meter.a2parser.capture import capture_packets
from ..meter.session import CombatSession, NoIdentifiedPlayerData
from ..meter.a2parser.models import DamageEvent
from ..meter.a2parser.capture_stats import FIELDS as PCAP_FIELDS, FLAGS as PCAP_FLAGS

CAPTURE_COUNTERS = ("tcp_discarded_payloads", "tcp_unresolved_flows", *PCAP_FIELDS)

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
        self._last_display_diagnostics: dict = {}
        self.started_at: float | None = None
        self._last_packet_at: float | None = None
        self._last_combat_at: float | None = None
        self.recorder = None
        self.diagnostic_export = None
        self._exported_recorder = None
        self._capture_generation = 0
        self._exported_generation = -1
        self._diagnostic_lock = threading.Lock()
        self._session_save_lock = threading.Lock()
        self._last_checkpoint = 0.0
        self._rollover_retry_at = 0.0
        self._stop = False
        self.replay_stop = threading.Event()
        self.lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self.session = CombatSession()
        self.metadata = {}
        self.capture_metadata = None
        self.scope = "auto"
        self.combine_pets = True
        self.segment_id = None
        self.enemy_id = None
        self.saved_log = None
        self.session_file = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.a2log.json"
        self.archive_id = uuid.uuid4().hex
        self.archive_part = 1
        self.archive_part_token = uuid.uuid4().hex
        self.archive_previous = None

    def start(self, source: str = "replay", **opts) -> dict:
        with self._lifecycle_lock:
            return self._start(source, **opts)

    def _start(self, source: str, **opts) -> dict:
        self.stop()
        with self.lock:
            self.meter = Meter()
            self.packet_engine = None
        self.error = None
        self._last_display_diagnostics = {}
        self.diagnostics = {}
        self._capture_generation += 1
        self.diagnostic_export = None
        from ..meter.diagnostics import Recorder
        if self.recorder is not None:
            try:
                self.recorder.release(remove=self.recorder is self._exported_recorder)
            except OSError as exc:
                self.diagnostics["recording_cleanup_error"] = str(exc)
        self.recorder = Recorder() if opts.get("record_packets") else None
        self._last_packet_at = self._last_combat_at = None
        self.started_at = time.monotonic()
        self._last_checkpoint = self.started_at
        self._rollover_retry_at = 0.0
        self._stop = False
        self.replay_stop = threading.Event()
        self.source_name = source
        if source in ("a2tools", "live"):
            from ..meter.metadata import CaptureMetadata
            if self.capture_metadata is None or not self.session.records:
                self.capture_metadata = CaptureMetadata()
        else:
            self.capture_metadata = None
        self.scope = str(opts.get("scope") or "auto")
        if self.scope not in ("party", "self", "all", "auto"):
            self.scope = "auto"
        from ..combat.a2log import combat_mode
        self.session.pvp = combat_mode({"meta": self.metadata}) == "pvp"
        if self.session.pvp and self.scope == "all":
            self.error = "PvP capture requires Self or Party scope; opposing teams cannot be inferred from All observed players."
            return self.status()
        self.session.gap_seconds = min(3600, max(120, int(opts.get("segment_gap") or 120)))
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
        for key in ("capture_errors", "decoder_errors", "shutdown_discarded_payloads", "shutdown_drained_payloads"):
            self.session.capture_evidence.setdefault(key, 0)
        self._capture_loss_baseline = {k:self.session.capture_evidence.get(k, 0) for k in CAPTURE_COUNTERS}
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
                            "auto_port": bool(opts.get("auto_port", decoder is None)), "port": None,
                            "shutdown_drained_payloads": 0, "shutdown_discarded_payloads": 0, "decoder_errors": 0}
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
        shutdown_deadline = None
        try:
            while True:
                if stop_event.is_set():
                    if shutdown_deadline is None:
                        shutdown_deadline = time.monotonic() + 5.0
                        self.diagnostics["state"] = "stopping"
                    if time.monotonic() >= shutdown_deadline:
                        self.diagnostics["shutdown_drain_timed_out"] = True
                        break
                try:
                    item = packets.get(timeout=0.25 if shutdown_deadline is not None else 0.5)
                except queue.Empty:
                    if stop_event.is_set() and not self.packet_capture_thread.is_alive():
                        break
                    if shutdown_deadline is None:
                        self._checkpoint_session()
                    continue
                kind, *data = item
                try:
                    if kind == "packet":
                        stream, payload, timestamp_ms = data
                        before_run = (self.session.run, self.session.run_closed)
                        with self.lock:
                            self._last_packet_at = time.monotonic()
                            events = self._decode_packet(engine, decoder, stream, payload, timestamp_ms)
                            self.diagnostics["decoded_events"] += len(events)
                            if stop_event.is_set():
                                self.diagnostics["shutdown_drained_payloads"] += 1
                                self.session.capture_evidence["shutdown_drained_payloads"] = self.session.capture_evidence.get("shutdown_drained_payloads", 0) + 1
                            if events:
                                self._last_combat_at = time.monotonic()
                        if not stop_event.is_set() and before_run != (self.session.run, self.session.run_closed):
                            self._save_session(active=True)
                        if engine is not None and not stop_event.is_set():
                            self._rollover_session()
                    elif kind == "stream_reset":
                        with self.lock:
                            if engine is not None:
                                engine.reset_stream(data[0])
                                self.session.split_now()
                                self.segment_id = self.enemy_id = None
                    elif kind == "error":
                        self.error = str(data[0])
                        stop_event.set()
                    elif kind == "capture_started":
                        self.diagnostics["state"] = "stopping" if stop_event.is_set() else "capturing"
                    elif kind == "capture_stats":
                        with self.lock:
                            self._record_capture_stats(data[0])
                            if stop_event.is_set():
                                self.diagnostics["state"] = "stopping"
                            if engine is not None and data[0].get("port"):
                                engine.set_server_port(int(data[0]["port"]))
                    elif kind == "ping":
                        with self.lock:
                            self.meter.add(CombatEvent(kind="ping", t=float(data[1]) / 1000.0, ping_ms=float(data[0])))
                    elif kind == "capture_stopped":
                        break
                    if not stop_event.is_set():
                        self._checkpoint_session()
                except Exception as exc:
                    # A transient failure handling one item (e.g. a zone/instance
                    # transition that resets identities and splits the session mid-save)
                    # must not tear down live capture. Record it and keep going; genuine
                    # adapter failures still arrive as a terminal "error" item above.
                    self.diagnostics["processing_error"] = f"{kind}: {type(exc).__name__}: {exc}"[:300]
                    self.diagnostics["processing_errors"] = self.diagnostics.get("processing_errors", 0) + 1
                    with self.lock:
                        self.session.capture_evidence["processing_errors"] = self.session.capture_evidence.get("processing_errors", 0) + 1
        except Exception as exc:
            self.error = self.error or f"Capture processing failed: {type(exc).__name__}: {exc}"
        finally:
            stop_event.set()
            if self.packet_capture_thread:
                self.packet_capture_thread.join(timeout=3.0)
            self.diagnostics["state"] = "error" if self.error else "stopped"
            with self.lock:
                if self.error:
                    self.session.capture_evidence["capture_errors"] = self.session.capture_evidence.get("capture_errors", 0) + 1
                self._discard_final_capture_items(packets)
                self.running = bool(self.packet_capture_thread and self.packet_capture_thread.is_alive())
                self.diagnostics["state"] = "stopping" if self.running else "error" if self.error else "stopped"
            if not self.running:
                self._archive_diagnostics()

    def _decode_packet(self, engine, decoder, stream, payload, timestamp_ms):
        # Caller holds the data lock; archive/save failures are not decoder errors.
        try:
            if engine is not None:
                events = engine.consume(payload, timestamp_ms, stream)
                rejected = getattr(engine, "last_framing_errors", 0)
                if rejected:
                    warning = f"Skipped {rejected} malformed or over-limit compressed frames; capture continues"
                    self.diagnostics["decoder_warning"] = warning
                    for key in ("decoder_errors", "capture_errors"):
                        self.session.capture_evidence[key] = self.session.capture_evidence.get(key, 0) + rejected
                        self.diagnostics[key] = self.session.capture_evidence[key]
                    history = self.diagnostics.setdefault("processing_errors", [])
                    history.append({"at":timestamp_ms, "type":"CompressedFrameRejected", "message":warning, "recoverable":True, "frames":rejected})
                    del history[:-20]
                self.session.observe(engine, events, timestamp_ms=timestamp_ms)
            else:
                events = list(decoder.feed(payload))
                for event in events:
                    self.meter.add(event)
            return events
        except (ValueError, IndexError, KeyError, UnicodeError, struct.error) as exc:
            # A malformed/unsupported packet must not end the entire live recording.
            # Keep loss evidence so recovered sessions cannot appear complete.
            warning = f"Packet decode skipped: {type(exc).__name__}: {exc}"
            self.diagnostics["decoder_warning"] = warning[:500]
            self.diagnostics["decoder_errors"] += 1
            for key in ("decoder_errors", "capture_errors"):
                self.session.capture_evidence[key] = self.session.capture_evidence.get(key, 0) + 1
            history = self.diagnostics.setdefault("processing_errors", [])
            history.append({"at": timestamp_ms, "type": type(exc).__name__, "message": str(exc)[:500], "recoverable": True})
            del history[:-20]
            if engine is not None:
                engine.reset_stream(stream)
            return []
        except Exception as exc:
            history = self.diagnostics.setdefault("processing_errors", [])
            history.append({"at": timestamp_ms, "type": type(exc).__name__, "message": str(exc)[:500], "recoverable": False})
            del history[:-20]
            self.error = f"Decoder failed: {type(exc).__name__}: {exc}"
            self.diagnostics["decoder_errors"] += 1
            self.session.capture_evidence["decoder_errors"] = self.session.capture_evidence.get("decoder_errors", 0) + 1
            raise

    def _discard_final_capture_items(self, packets):
        # Caller holds the data lock. After an error/deadline, count actual
        # abandoned payloads separately from decoder exceptions. The legacy
        # capture_errors counter includes both, for older server versions.
        while True:
            try:
                final = packets.get_nowait()
            except queue.Empty:
                break
            if final[0] == "packet":
                self.diagnostics["shutdown_discarded_payloads"] = self.diagnostics.get("shutdown_discarded_payloads", 0) + 1
                for key in ("capture_errors", "shutdown_discarded_payloads"):
                    self.session.capture_evidence[key] = self.session.capture_evidence.get(key, 0) + 1
            elif final[0] == "capture_stats":
                self._record_capture_stats(final[1])
        self.diagnostics["capture_errors"] = self.session.capture_evidence.get("capture_errors", 0)

    def _record_capture_stats(self, stats):
        # Caller holds self.lock; final counters must also reach the visible diagnostics.
        self.diagnostics.update(stats)
        # Packet-source counters do not replace processing counters from this runner.
        for key in ("decoder_errors", "shutdown_discarded_payloads", "shutdown_drained_payloads", "capture_errors"):
            if key in self.session.capture_evidence:
                self.diagnostics[key] = self.session.capture_evidence[key]
        for key in ("transport_monitored", *CAPTURE_COUNTERS, *PCAP_FLAGS, "tcp_pending_bytes"):
            if key not in stats:
                continue
            value = stats[key]
            if key in CAPTURE_COUNTERS:
                value += self._capture_loss_baseline.get(key, 0)
            if key in PCAP_FLAGS:
                value = bool(value or self.session.capture_evidence.get(key, False))
            self.session.capture_evidence[key] = value

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
        with self._lifecycle_lock:
            self._stop_capture()

    def _stop_capture(self) -> None:
        self._stop = True
        self.replay_stop.set()
        if self.packet_stop:
            self.packet_stop.set()
        t = self.thread
        if t and t.is_alive():
            t.join(timeout=8.0)
        capture = self.packet_capture_thread
        if capture and capture.is_alive():
            capture.join(timeout=3.0)
        unfinished = bool(t and t.is_alive() or capture and capture.is_alive())
        if unfinished:
            self.diagnostics["state"] = "stopping" if self.running else "saving"
            raise TimeoutError("Capture is still shutting down. Wait, then press Stop again; export diagnostics if it remains stuck. A new capture cannot replace this worker.")
        self.running = False
        with self.lock:
            if self.packet_queue is not None:
                self._discard_final_capture_items(self.packet_queue)
        if self.diagnostics:
            self.diagnostics["state"] = "error" if self.error else "stopped"
        # Preserve the opted-in buffer before the next Start replaces it.
        # Repeated Stop/Quit calls must not create duplicate archives.
        self._archive_diagnostics()

    def _checkpoint_session(self) -> None:
        now = time.monotonic()
        if now - self._last_checkpoint >= 15:
            self._last_checkpoint = now
            self._save_session(active=True)

    def _rollover_session(self) -> None:
        # Keep substantial headroom below both live and import/export limits.
        # Only the decoder thread invokes rollover, between packet batches.
        with self.lock:
            if not self.session.records:
                return  # Idle telemetry alone cannot form an identified combat log.
            due = (len(self.session.records) >= 100_000 or len(self.session.telemetry) >= 20_000
                   or self.session._storage_groups.get(self.scope, self.session.storage_groups) >= 100
                   or len(self.session._storage_players.get(self.scope, self.session.storage_players)) >= 48)
            if not due:
                return
            hard = (len(self.session.records) >= 350_000 or len(self.session.telemetry) >= 40_000
                    or self.session._storage_groups.get(self.scope, self.session.storage_groups) >= 180
                    or len(self.session._storage_players.get(self.scope, self.session.storage_players)) >= 60)
            last_hit = next((r.event.timestamp_ms for r in reversed(self.session.records)
                            if isinstance(r.event, DamageEvent) and r.event.actor_id in self.session._allowed(r, self.scope)
                            and r.event.target_id not in self.session._allowed(r, self.scope)), 0)
            active = last_hit and time.time() * 1000 - last_hit < 120_000
            if due and active and not hard and not self.session.run_closed:
                self.diagnostics["archive_deferred"] = "Archive part will be saved after combat pauses; live totals continue."
                return
        if not due or time.monotonic() < self._rollover_retry_at:
            return
        from ..combat.sessions import save
        with self._session_save_lock:
            with self.lock:
                detached = copy.deepcopy(self.session)
                metadata = dict(self.metadata)
                profile = dict(self.packet_engine.local_profile)
                scope, collector = self.scope, self.capture_metadata
            detached.capture_evidence["storage_boundary"] = True
            detached.finish_run("storage_rollover", complete=False)
            title = f"Live combat session {self.archive_id[:8]} Â· Part {self.archive_part}"
            try:
                document = detached.to_a2log(scope, title)
            except NoIdentifiedPlayerData:
                # Identity/filter eligibility is not a decoder failure. Keep
                # the bounded session intact and retry without copying it on
                # every subsequent packet. Ordinary retention counters expose
                # any history lost while identity remains unresolved.
                self._rollover_retry_at = time.monotonic() + 5
                self.diagnostics["archive_deferred"] = (
                    "Archive rollover is waiting for player data under the selected filter. "
                    "Capture continues; unresolved history remains subject to retention limits.")
                return
            doc = self._metadata(document, metadata=metadata, profile=profile, collector=collector)
            doc["meta"].update(capture_active=False, checkpoint_at=time.time(),
                               archive=self._archive_metadata(detached, closed=True))
            # Never clear the memory part unless its atomic disk save succeeded.
            # A failed save propagates to the runner and stops capture visibly.
            saved = str(save(doc, self.session_file))
            with self.lock:
                self.session = self.session.continuation()
                self.session.capture_evidence["storage_boundary"] = True
                self.archive_part += 1
                self.archive_previous = doc["meta"]["archive"].get("continuity")
                self.archive_part_token = uuid.uuid4().hex
                self.session_file = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.a2log.json"
                self.segment_id = self.enemy_id = None
                self.saved_log = saved
                self.diagnostics["archive_parts_saved"] = self.archive_part - 1
                self.diagnostics["archive_last_part"] = saved
                self.diagnostics.pop("archive_deferred", None)
                self._rollover_retry_at = 0.0
            self._last_checkpoint = time.monotonic()

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
        if self.started_at is not None:
            try:
                self.export_diagnostics()
            except (OSError, ValueError, TypeError) as exc:
                self.diagnostics["archive_error"] = f"{type(exc).__name__}: {exc}"

    def export_diagnostics(self) -> dict:
        with self._diagnostic_lock:
            if (self._exported_generation == self._capture_generation and self.diagnostic_export and not self.running
                    and Path(self.diagnostic_export["file"]).is_file()):
                return self.diagnostic_export
            from ..meter.diagnostics import export
            result = export(self.diagnostic_status(), self.recorder)
            self.diagnostic_export = result
            if not self.running:
                self._exported_recorder = self.recorder
                self._exported_generation = self._capture_generation
                if self.recorder is not None:
                    try:
                        self.recorder.release(remove=True)
                    except OSError as exc:
                        self.diagnostics["recording_cleanup_error"] = str(exc)
            self.diagnostics.pop("archive_error", None)
            return result

    def record_status_failure(self, exc) -> None:
        # Reporting a failed/blocked display must not wait on the decoder lock.
        self.diagnostics["status_error"] = f"{type(exc).__name__}: {exc}"[:512]
        self.diagnostics["status_error_at"] = time.time()
        self.diagnostics["status_error_count"] = self.diagnostics.get("status_error_count", 0) + 1

    def diagnostic_status(self) -> dict:
        """Counters and metadata without rendering/aggregating combat history.

        A blocked decoder or broken display snapshot must not prevent exporting
        evidence. A timed-out lock produces explicitly best-effort counters.
        """
        acquired = self.lock.acquire(timeout=0.25)
        try:
            diagnostic = dict(self.diagnostics)
            diagnostic["export_consistency"] = "locked" if acquired else "best_effort_decoder_busy"
            if acquired:
                diagnostic["npc_diagnostics"] = self.session.npc_diagnostics()
            diagnostic["raw_recording_enabled"] = self.recorder is not None
            diagnostic["scope"] = self.scope
            diagnostic["capture_processing"] = {k:self.session.capture_evidence.get(k) for k in ("capture_errors", "decoder_errors", "shutdown_discarded_payloads", "shutdown_drained_payloads")}
            diagnostic["retained_effects"] = len(self.session.records)
            diagnostic["retained_telemetry"] = len(self.session.telemetry)
            engine, collector = self.packet_engine, self.capture_metadata
            server = engine.local_profile.get("serverId") if engine else None
            diagnostic["local_identity_available"] = bool(engine and engine.local_player_id is not None)
            diagnostic["roster_entries"] = len(engine.roster) if engine else 0
            now = time.monotonic()
            diagnostic.update(last_packet_age_seconds=round(now-self._last_packet_at,1) if self._last_packet_at is not None else None,
                              last_combat_age_seconds=round(now-self._last_combat_at,1) if self._last_combat_at is not None else None)
            diagnostic["pipeline"] = {"stage": "display_snapshot_skipped", "scope": self.scope,
                                      "raw_recording_enabled": self.recorder is not None,
                                      "local_identity_available": diagnostic["local_identity_available"],
                                      "local_identity_from_game": bool(engine and engine.local_identity_from_game),
                                      "roster_entries": diagnostic["roster_entries"],
                                      "retained_effects": diagnostic["retained_effects"]}
            cached = self._last_display_diagnostics
            diagnostic["display_context_cached_at"] = cached.get("at")
            result = {"source": self.source_name, "running": self.running,
                      "error": self.error, "diagnostics": diagnostic,
                      "automatic_context": cached.get("automatic_context"),
                      "catalog_coverage": cached.get("catalog_coverage")}
        finally:
            if acquired:
                self.lock.release()
        if collector:
            try:
                result["automatic_metadata"] = collector.snapshot(server)
            except Exception as exc:
                diagnostic["metadata_error"] = f"{type(exc).__name__}: {exc}"[:512]
        return result

    def status(self, *, follow_latest: bool = False, compact: bool = False) -> dict:
        if not self.lock.acquire(timeout=0.5):
            raise TimeoutError("Capture data is busy; refresh will retry. Capture diagnostics can still be exported.")
        try:
            finalizing = bool(not self.running and self.thread and self.thread.is_alive())
            snap = (self.session.snapshot(self.scope, None if follow_latest else self.segment_id,
                                          None if follow_latest else self.enemy_id, self.combine_pets)
                    if self.packet_engine is not None else self.meter.snapshot())
            if self.packet_engine is not None:
                snap["ping"] = self.meter.ping_summary()   # the session snapshot carries no latency
            if self.packet_engine is not None and not follow_latest:
                self.enemy_id = snap.get("selected_enemy")
            if compact:
                return {"running": self.running, "finalizing": finalizing, "error": self.error,
                        "combine_pets": self.combine_pets, "snapshot": snap}
            current = dict(self.session.runs[self.session.run])
            run = {"id": self.session.run, "closed": self.session.run_closed, **current}
            engine = self.packet_engine
            identity = ({"id": engine.local_player_id,
                         "name": engine.names.get(engine.local_player_id),
                         "verified": engine.local_identity_from_game,
                         **engine.local_profile} if engine else None)
            collector = self.capture_metadata
            installation_locked = self.running or bool(self.session.records) or bool(self.meter.players)
            diagnostic = dict(self.diagnostics)
            diagnostic["capture_processing"] = {k:self.session.capture_evidence.get(k) for k in ("capture_errors", "decoder_errors", "shutdown_discarded_payloads", "shutdown_drained_payloads")}
            now = time.monotonic()
            if self.source_name in ("a2tools", "live"):
                if self.error:
                    stage = "capture_error"
                elif not diagnostic.get("packets"):
                    stage = "waiting_for_tcp"
                elif not diagnostic.get("payload_packets"):
                    stage = "waiting_for_payloads"
                elif not diagnostic.get("forwarded"):
                    stage = "waiting_for_game_flow" if diagnostic.get("auto_port") and not diagnostic.get("port") else "waiting_for_reassembly"
                elif not diagnostic.get("decoded_events"):
                    stage = "waiting_for_combat_effects"
                elif not snap.get("players"):
                    stage = "no_players_in_selected_view"
                else:
                    stage = "combat_visible"
                diagnostic["pipeline"] = {
                    "stage": stage, "raw_recording_enabled": self.recorder is not None,
                    "scope": self.scope, "visible_players": len(snap.get("players", [])),
                    "retained_effects": len(self.session.records),
                    "local_identity_available": bool(self.packet_engine and self.packet_engine.local_player_id is not None),
                    "local_identity_from_game": bool(self.packet_engine and self.packet_engine.local_identity_from_game),
                    "roster_entries": len(self.packet_engine.roster) if self.packet_engine else 0,
                    "selection_mode": snap.get("selection_mode"),
                }
            diagnostic.update(last_packet_age_seconds=round(now-self._last_packet_at, 1) if self._last_packet_at is not None else None,
                              last_combat_age_seconds=round(now-self._last_combat_at, 1) if self._last_combat_at is not None else None)
        finally:
            self.lock.release()
        if diagnostic:
            diagnostic["elapsed"] = round(time.monotonic() - self.started_at, 1) if self.started_at else 0
        from ..meter.context import classify
        from ..combat.catalog import coverage
        context = classify(current.get("map_id"), current.get("instance_id"), snap.get("recorded_pvp", False),
                           [dict(e, kind="enemy") for e in snap.get("enemies", [])])
        catalog = coverage({**current, **context, "entities": [dict(e, id=e["key"], kind="enemy") for e in snap.get("enemies", [])]})
        self._last_display_diagnostics = {"automatic_context": context, "catalog_coverage": catalog, "at": time.time()}
        return {"running": self.running, "finalizing": finalizing, "source": self.source_name, "error": self.error,
                "combine_pets": self.combine_pets, "installation_locked": installation_locked,
                "automatic_context": context, "catalog_coverage": catalog,
                "snapshot": snap, "diagnostics": diagnostic,
                "automatic_metadata": (collector.snapshot(identity.get("serverId") if identity else None)
                                       if collector else {}),
                "diagnostic_export": self.diagnostic_export,
                "saved_log": self.saved_log,
                "run": run, "identity": identity,
                "recording": {"enabled": self.recorder is not None,
                              **(self.recorder.snapshot(include_rows=False)[0] if self.recorder is not None else {"records": 0})}}

    def select_installation(self, value):
        from ..meter.metadata import choose_installation
        with self.lock:
            if self.running or self.session.records or self.meter.players:
                raise ValueError("Stop capture, save/export retained combat, and clear the session before changing installation.")
            result = choose_installation(value)
            self.capture_metadata = None
        return result

    def set_installation_path(self, path, *, remove=False):
        from ..meter.metadata import set_manual_installation
        with self.lock:
            if self.running or self.session.records or self.meter.players:
                raise ValueError("Stop capture, save/export retained combat, and clear the session before changing installation.")
            result = set_manual_installation(path, remove=remove)
            self.capture_metadata = None
        return result

    def configure_view(self, body: dict) -> dict:
        with self.lock:
            if "metadata" in body:
                raise ValueError("Live capture classification is automatic. Correct a completed saved log per encounter or run.")
            if "combine_pets" in body:
                self.combine_pets = bool(body["combine_pets"])
            if "automatic_splits" in body:
                self.session.automatic_splits = bool(body["automatic_splits"])
            if body.get("segment_gap") is not None:
                self.session.gap_seconds = min(3600, max(120, int(body["segment_gap"])))
            if body.get("scope") == "all" and self.session.pvp:
                raise ValueError("Use Self or Party scope for PvP capture.")
            if body.get("scope") in ("party", "self", "all", "auto"):
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
        with self._lifecycle_lock:
            return self._clear_session()

    def _clear_session(self) -> dict:
        if self.running or any(t and t.is_alive() for t in (self.thread, self.packet_capture_thread)):
            raise ValueError("Stop capture before clearing session history.")
        with self.lock:
            self.session = CombatSession()
            self.meter = Meter()
            self.capture_metadata = None
            self.archive_id = uuid.uuid4().hex
            self.archive_part = 1
            self.archive_part_token = uuid.uuid4().hex
            self.archive_previous = None
            self.session_file = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.a2log.json"
            self.saved_log = None
            self.segment_id = self.enemy_id = None
        return self.status()

    def finish_run(self):
        with self.lock:
            self.session.finish_run()
        self._save_session(active=True)
        return self.status()

    def _archive_metadata(self, session, closed=False):
        from ..combat.archive import retained_range
        archive = {"id":self.archive_id, "part":self.archive_part, "closed":closed}
        continuity = retained_range(session, self.archive_part_token, self.archive_previous)
        if continuity:
            archive["continuity"] = continuity
        return archive

    def to_a2log(self, title: str | None = None) -> dict:
        # Detach quickly under the capture lock. Validation, summaries and upload
        # must never hold that lock while the decoder is receiving new packets.
        with self.lock:
            session = copy.deepcopy(self.session if self.packet_engine is not None else self.meter)
            metadata = dict(self.metadata)
            profile = dict(self.packet_engine.local_profile) if self.packet_engine else {}
            scope = self.scope
            collector = self.capture_metadata
            archive = (self._archive_metadata(session) if isinstance(session, CombatSession)
                       else {"id":self.archive_id, "part":self.archive_part, "closed":False})
        if isinstance(session, CombatSession) and not title:
            title = f"Live combat session {archive['id'][:8]} Â· Part {archive['part']}"
        doc = session.to_a2log(scope, title) if isinstance(session, CombatSession) else session.to_a2log(title=title)
        if isinstance(session, CombatSession):
            doc["meta"]["archive"] = archive
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
            for key in ("installed_build", "installed_build_source", "installed_build_namespace", "installed_build_cohort", "launcher_build", "launcher_build_namespace", "launcher_build_source", "file_version", "installed_content_build", "installed_content_namespace", "installed_content_source"):
                if detected.get(key):
                    doc["meta"][key] = detected[key]
            if not doc["meta"].get("game_patch") and detected.get("game_patch"):
                for key in ("game_patch", "game_patch_source", "game_patch_basis"):
                    doc["meta"][key] = detected[key]
            elif metadata.get("game_patch"):
                doc["meta"].update(game_patch_source="Manual override", game_patch_basis="manual")
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
                    if key in ("zone", "difficulty", "game_patch"):
                        segment[key + "_source"] = "Manual override"
                    if key == "game_patch":
                        segment["game_patch_basis"] = "manual"
            if not segment.get("game_patch") and doc["meta"].get("game_patch"):
                for key in ("game_patch", "game_patch_source", "game_patch_basis"):
                    if doc["meta"].get(key):
                        segment[key] = doc["meta"][key]
        if profile is None:
            profile = self.packet_engine.local_profile if self.packet_engine else {}
        if profile.get("serverId"):
            doc["meta"]["server"] = str(profile["serverId"])
        # Slice by actual encounter origin, never by the time of the newest ping.
        from datetime import datetime
        from ..combat.latency import summarize
        for segment in doc.get("segments", []):
            try:
                stamp = datetime.fromisoformat((segment.get("start") or "").replace("Z", "+00:00"))
                origin = stamp.timestamp() if stamp.tzinfo else None
            except (ValueError, TypeError):
                origin = None
            if origin is None and self.packet_engine is None:
                origin = self.meter.t0
            if origin is not None:
                duration = float(segment["duration"])
                segment["ping"] = [[round(t-origin, 3), round(ms, 2)] for t, ms in self.meter.pings
                                   if 0 <= t-origin <= duration]
                if segment["ping"]:
                    segment["ping_source"] = "passive_tcp_ack"
        samples = [row for segment in doc.get("segments", []) for row in segment.get("ping", [])]
        summary = summarize(samples)
        if summary:
            doc["meta"]["ping"] = summary
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
