"""Background runner for the live meter and its embedded A2Tools capture engine."""
from __future__ import annotations

import threading
import copy
import json
import queue
import re
import struct
import time
import traceback
import uuid
from pathlib import Path

from ..meter import CombatEvent, Meter, load_decoder, replay_source
from ..meter.a2parser.engine import MeterEngine as PacketMeterEngine
from ..meter.a2parser.capture import capture_packets
from ..meter.session import CombatSession, NoIdentifiedPlayerData
from ..meter.a2parser.capture_stats import FIELDS as PCAP_FIELDS, FLAGS as PCAP_FLAGS
from ..combat.quality import LIFETIME_COUNTERS, TIMED_LOSS_COUNTERS

CAPTURE_COUNTERS = ("tcp_discarded_payloads", "tcp_unresolved_flows", *PCAP_FIELDS)

DEMO = Path(__file__).resolve().parent.parent / "meter" / "demo_session.jsonl"

# Live community-rank refresh: only act once combat has paused this long (a fight ended),
# and no more than once per this interval, so a per-fight badge never floods the server.
_LIVE_RANK_IDLE_S = 5.0
_LIVE_RANK_THROTTLE_S = 20.0

# Live-meter throughput. One thread decodes packets; a major fight (a world/abyss boss
# with a full raid) can enqueue them faster than it drains them. Draining the burst that
# has piled up and doing the per-burst bookkeeping (run-save / rollover / checkpoint) once
# per batch — instead of once per packet — is what keeps the decoder ahead of the queue.
_DECODE_BATCH_MAX = 256
# A backlog at least this deep means the live view is behind real time: tell the viewer it
# is catching up, and (in _live_snapshot) let the costly recompute step aside so the
# decoder reclaims the shared lock to drain the burst. Normal play sits near zero.
_DECODE_BACKLOG_QUEUE = 48
# While backlogged, stretch the live-snapshot interval by this factor so the recompute
# holds the shared lock ~1/(1+N) of the time (N=3 -> ~25%, vs the ~50% it may take when the
# decoder is keeping up), handing that lock time back to the decoder.
_SNAPSHOT_BACKLOG_DUTY = 3.0
#: Distinct players in scope that make a storage part due (rolled over at the next combat pause)
#: and that force it regardless; both below the a2log export limit of 1024 identities.
_ROLLOVER_PLAYERS_DUE = 400
_ROLLOVER_PLAYERS_HARD = 800


def upload_evictor():
    """A callback for :func:`aion2calc.combat.sessions.prune_logs` that uploads each
    recording to the configured share server right before the size cap deletes it, so a
    long session's rolled-over parts (and their boss kills) reach the community before
    they are reclaimed. Returns ``None`` — meaning "just delete" — when the feature is
    off (``meter_upload_before_prune``, on by default) or no share server is set.

    The returned callable reads the file, uploads it unlisted, and returns whether the
    upload succeeded; it never raises and is safe to call from the prune loop."""
    try:
        from .server import ui_settings
        if ui_settings().get("meter_upload_before_prune", True) is False:
            return None
        from ..combat import share
        if not str(share.effective().get("url") or "").strip():
            return None
    except Exception:
        return None

    def _evict(target) -> bool:
        try:
            import json
            from ..combat import share
            doc = json.loads(Path(target).read_text(encoding="utf-8"))
            if share.already_uploaded(doc):
                return True            # a finished part the server already holds: nothing to send
            if share.automatic_uploads_paused():
                return False           # the server's upload bucket is spent: don't add a rejection
            share.upload(doc, visibility="unlisted")
            return True
        except Exception:
            return False

    return _evict


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
        # Last successfully built status() result, keyed by (compact, follow_latest).
        # Served (marked stale) when the data lock is momentarily held by the capture
        # thread during a heavy-combat burst, so the overlay/meter keeps showing the
        # most recent reading instead of a "capture busy" error that freezes it.
        self._status_cache: dict = {}
        # Short-TTL live-snapshot cache. The app page and the transparent overlay
        # both poll ~twice a second, offset, so without this a large fight gets the
        # full session recompute 2-4x/second while holding the capture lock, which
        # starves the capture thread and freezes the meter. The TTL is adaptive —
        # never recompute more often than the last recompute took — so snapshot work
        # can't exceed ~50% duty no matter how big the fight gets.
        self._snap_cache: tuple | None = None
        self._community_rank: dict = {}   # player id -> {text, scope, percentile} after an upload
        # Live community-rank refresh (opt-in): after a ranked fight ends mid-capture, upload the
        # snapshot unlisted and refresh the badge, throttled, so it updates without a manual Upload.
        self._live_rank_last = 0.0        # monotonic of the last auto-refresh upload
        self._live_rank_key = None        # signature of the fights last auto-uploaded
        self._live_rank_busy = False      # one auto-refresh in flight at a time
        self._last_snap_cost = 0.0
        self._snap_thread: threading.Thread | None = None   # the in-flight off-lock snapshot recompute, if any
        self._last_save_cost = 0.0        # seconds the last checkpoint save took (stretches the cadence)
        self._unsaved_parts: list = []    # rolled-over archive parts detached from the live session, not yet on disk
        #: Every archive part file this process wrote (name -> first write time): the recordings
        #: an automatic upload on Stop, quit or the next launch must still send (see pending_uploads).
        self._written_files: dict = {}
        self._upload_lock = threading.Lock()      # one automatic upload pass at a time
        self._pending_upload_thread = None
        self._flush_thread: threading.Thread | None = None
        self._last_prune = 0.0   # throttle the logs-folder size prune
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
        self._save_thread: threading.Thread | None = None   # the in-flight checkpoint save, if any
        self._previous_engine = None                        # the last capture's engine, for identity carry-over
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
        self.save_records = True   # auto-save finished/periodic session logs (Settings: Save combat records)
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
            self._previous_engine = self.packet_engine
            self.packet_engine = None
            self._snap_cache = None          # never show the previous session's snapshot
            self._community_rank = {}        # a prior session's standings must not leak in
            self._live_rank_last, self._live_rank_key, self._live_rank_busy = 0.0, None, False
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
        self.session.retain_scope = self.scope   # keep only what this scope's log and live view use
        from ..combat.a2log import combat_mode
        self.session.pvp = combat_mode({"meta": self.metadata}) == "pvp"
        if self.session.pvp and self.scope == "all":
            self.error = "PvP capture requires Self or Party scope; opposing teams cannot be inferred from All observed players."
            return self.status()
        self.session.gap_seconds = min(3600, max(120, int(opts.get("segment_gap") or 120)))
        self.session.automatic_splits = bool(opts.get("automatic_splits", True))
        self.session.final_boss_ids = {int(x) for x in opts.get("final_boss_ids",[]) if str(x).isdigit()}
        self.session.auto_finish = bool(opts.get("auto_finish",True))
        self.apply_record_settings()
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
        for key in ("capture_errors", "decoder_errors", "recovered_frame_skips",
                    "shutdown_discarded_payloads", "shutdown_drained_payloads"):
            self.session.capture_evidence.setdefault(key, 0)
        self._capture_loss_baseline = {k:self.session.capture_evidence.get(k, 0) for k in CAPTURE_COUNTERS}
        self._loss_seen = {}            # dated capture-loss counters (see _record_capture_stats)
        if self.session.capture_evidence.get("tcp_pending_bytes", 0):
            self._capture_loss_baseline["tcp_unresolved_flows"] += 1
        self._loss_seen = {k: self._capture_loss_baseline.get(k, 0) for k in TIMED_LOSS_COUNTERS}
        if self.packet_engine is not None:
            self.session.begin_capture()
            self.packet_engine.set_server_port(port)
            previous, self._previous_engine = self._previous_engine, None
            if previous is not None and self.session.records and hasattr(previous, "adopt_identity"):
                # Restarting mid-recording (to export, after a hiccup): the party, your own actor
                # id and the spawns seen are still valid in the zone the client is in. Without
                # this, nobody is identified until the next zone load.
                self.packet_engine.adopt_identity(previous)
            self._seed_boss_hp(self.packet_engine)
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
                            "shutdown_drained_payloads": 0, "shutdown_discarded_payloads": 0,
                            "decoder_errors": 0, "recovered_frame_skips": 0,
                            "queue_depth": 0, "queue_depth_peak": 0}
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
                    first = packets.get(timeout=0.25 if shutdown_deadline is not None else 0.5)
                except queue.Empty:
                    self.diagnostics["queue_depth"] = 0
                    if stop_event.is_set() and not self.packet_capture_thread.is_alive():
                        break
                    if shutdown_deadline is None:
                        self._checkpoint_session()
                    continue
                # Batch only when the decoder is actually falling behind — a resource-heavy
                # boss fight where packets have piled up. For normal encounters and dungeons
                # the queue stays shallow (cap 1), so each packet is taken one at a time with
                # exactly the per-packet bookkeeping and full-cadence snapshot as before:
                # batching, and the snapshot stepping aside, engage only once a backlog forms.
                behind = packets.qsize()
                cap = _DECODE_BATCH_MAX if behind >= _DECODE_BACKLOG_QUEUE else 1
                batch = [first]
                while len(batch) < cap:
                    try:
                        batch.append(packets.get_nowait())
                    except queue.Empty:
                        break
                self.diagnostics["queue_depth"] = packets.qsize()
                self.diagnostics["queue_depth_peak"] = max(self.diagnostics.get("queue_depth_peak", 0), behind + 1)
                self.diagnostics["last_batch"] = len(batch)
                run_before = (self.session.run, self.session.run_closed)
                saw_packet = stop_after_batch = False
                for item in batch:
                    kind, *data = item
                    try:
                        if kind == "packet":
                            stream, payload, timestamp_ms = data
                            saw_packet = True
                            with self.lock:
                                self._last_packet_at = time.monotonic()
                                events = self._decode_packet(engine, decoder, stream, payload, timestamp_ms)
                                self.diagnostics["decoded_events"] += len(events)
                                if stop_event.is_set():
                                    self.diagnostics["shutdown_drained_payloads"] += 1
                                    self.session.capture_evidence["shutdown_drained_payloads"] = self.session.capture_evidence.get("shutdown_drained_payloads", 0) + 1
                                if events:
                                    self._last_combat_at = time.monotonic()
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
                            stop_after_batch = True
                            break
                    except Exception as exc:
                        # A transient failure handling one item (e.g. a zone/instance
                        # transition that resets identities and splits the session mid-save)
                        # must not tear down live capture. Record it and keep going; genuine
                        # adapter failures still arrive as a terminal "error" item above.
                        self.diagnostics["processing_error"] = f"{kind}: {type(exc).__name__}: {exc}"[:300]
                        self.diagnostics["processing_errors"] = self.diagnostics.get("processing_errors", 0) + 1
                        with self.lock:
                            self.session.capture_evidence["processing_errors"] = self.session.capture_evidence.get("processing_errors", 0) + 1
                # Per-burst bookkeeping, once for the whole batch (skipped entirely while
                # draining for shutdown, exactly as the per-packet path was).
                if not stop_event.is_set():
                    if saw_packet and run_before != (self.session.run, self.session.run_closed):
                        self._spawn_save()
                    if engine is not None and saw_packet:
                        self._rollover_session()
                    self._checkpoint_session()
                if stop_after_batch:
                    break
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
                    self._note_loss("capture_errors", 1)
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
                    # A skipped-and-recovered frame is not a decoder failure: the capture
                    # continues. Count it separately so a routine handful does not void
                    # ranking (a perfect frame stream is not achievable); quality.py still
                    # treats a *material* amount as loss.
                    self.session.capture_evidence["recovered_frame_skips"] = \
                        self.session.capture_evidence.get("recovered_frame_skips", 0) + rejected
                    self.diagnostics["recovered_frame_skips"] = self.session.capture_evidence["recovered_frame_skips"]
                    history = self.diagnostics.setdefault("processing_error_log", [])
                    history.append({"at":timestamp_ms, "type":"CompressedFrameRejected", "message":warning, "recoverable":True, "frames":rejected})
                    del history[:-20]
                self.session.observe(engine, events, timestamp_ms=timestamp_ms)
            else:
                events = list(decoder.feed(payload))
                for event in events:
                    self.meter.add(event)
            return events
        except (ValueError, IndexError, KeyError, UnicodeError, struct.error) as exc:
            # A malformed/unsupported packet must not end the entire live recording, and a
            # single recovered one must not void a whole session's ranking (a perfect packet
            # stream is not achievable). It is counted as a recovered skip, not a decoder
            # failure; quality.py still treats a *material* amount of skips as capture loss.
            warning = f"Packet decode skipped: {type(exc).__name__}: {exc}"
            self.diagnostics["decoder_warning"] = warning[:500]
            self.session.capture_evidence["recovered_frame_skips"] = \
                self.session.capture_evidence.get("recovered_frame_skips", 0) + 1
            self.diagnostics["recovered_frame_skips"] = self.session.capture_evidence["recovered_frame_skips"]
            history = self.diagnostics.setdefault("processing_error_log", [])
            history.append({"at": timestamp_ms, "type": type(exc).__name__, "message": str(exc)[:500], "recoverable": True})
            del history[:-20]
            if engine is not None:
                engine.reset_stream(stream)
            return []
        except Exception as exc:
            history = self.diagnostics.setdefault("processing_error_log", [])
            history.append({"at": timestamp_ms, "type": type(exc).__name__, "message": str(exc)[:500], "recoverable": False})
            del history[:-20]
            self.error = f"Decoder failed: {type(exc).__name__}: {exc}"
            self.diagnostics["decoder_errors"] += 1
            self.session.capture_evidence["decoder_errors"] = self.session.capture_evidence.get("decoder_errors", 0) + 1
            self._note_loss("decoder_errors", 1, timestamp_ms)
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
                    self._note_loss(key, 1, final[3] if len(final) > 3 else None)
            elif final[0] == "capture_stats":
                self._record_capture_stats(final[1])
        self.diagnostics["capture_errors"] = self.session.capture_evidence.get("capture_errors", 0)

    def _note_loss(self, key, count, timestamp_ms=None):
        """Place a capture loss in time so the fight it happened in -- not every fight of the
        session -- is charged with it (see CombatSession.note_capture_loss)."""
        self.session.note_capture_loss(key, count, int(time.time() * 1000) if timestamp_ms is None else timestamp_ms)

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
                if key in TIMED_LOSS_COUNTERS:
                    # The capture reports its counters the moment a TCP stream restarts (and
                    # periodically), so the counter's movement dates the loss.
                    seen = self._loss_seen.get(key, self._capture_loss_baseline.get(key, 0))
                    if value > seen:
                        self._note_loss(key, value - seen)
                    self._loss_seen[key] = max(seen, value)
            if key in PCAP_FLAGS:
                value = bool(value or self.session.capture_evidence.get(key, False))
            self.session.capture_evidence[key] = value
        # Record the active capture filter and whether the game flow was located, so an uploaded
        # log reveals whether it fell back to the broad "tcp" capture (the packet-loss culprit).
        for key in ("auto_port", "capture_filter"):
            if stats.get(key) is not None:
                self.session.capture_evidence[key] = stats[key]
        if stats.get("flow_detected"):
            self.session.capture_evidence["flow_detected"] = True

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
        # Every 15 s, but the save worker never takes more than about a quarter of the CPU: a
        # 350k-record part serialises for many seconds, and with Python's GIL that time comes
        # straight out of the decoder's. The cadence stretches with the last save's cost (capped
        # at two minutes) and relaxes again as soon as saves are quick.
        if now - self._last_checkpoint >= min(120.0, max(15.0, 4.0 * self._last_save_cost)):
            if self._spawn_save():
                self._last_checkpoint = now

    def _spawn_save(self) -> bool:
        """Write the session log on a worker thread. Building and serialising an 8 MB document
        took seconds on the decoder thread every 15 s; packets piled up meanwhile (the capture
        buffer overflowed, the overlay froze). The detach under the capture lock is cheap now
        (see ``CombatSession.__deepcopy__``), the rest runs here. One save at a time: a save
        still running when the next is due simply makes that one wait for the next tick."""
        worker = self._save_thread
        if worker is not None and worker.is_alive():
            return False
        self._save_thread = threading.Thread(target=self._save_session, args=(True,), daemon=True, name="session-save")
        self._save_thread.start()
        return True

    def _rollover_session(self) -> None:
        # Keep substantial headroom below both live and import/export limits.
        # Only the decoder thread invokes rollover, between packet batches.
        with self.lock:
            if not self.session.records:
                return  # Idle telemetry alone cannot form an identified combat log.
            # The player bounds sit below the a2log export limit (1024 identities). They used to be
            # 48/60 from an older 64-identity limit: under the All scope in a world-boss crowd that
            # made every packet batch a *hard* rollover (a hundred players are in scope at once),
            # flushing a tiny part and resetting the live view continuously.
            players = len(self.session._storage_players.get(self.scope, self.session.storage_players))
            groups = self.session._storage_groups.get(self.scope, self.session.storage_groups)
            due = (len(self.session.records) >= 100_000 or len(self.session.telemetry) >= 20_000
                   or groups >= 100 or players >= _ROLLOVER_PLAYERS_DUE)
            if not due:
                return
            hard = (len(self.session.records) >= 350_000 or len(self.session.telemetry) >= 40_000
                    or groups >= 180 or players >= _ROLLOVER_PLAYERS_HARD)
            active = self._recent_outgoing(120_000)
            if due and active and not hard and not self.session.run_closed:
                self.diagnostics["archive_deferred"] = "Archive part will be saved after combat pauses; live totals continue."
                return
            if time.monotonic() < self._rollover_retry_at:
                return
            if not self.session._storage_players.get(self.scope, self.session.storage_players):
                # Identity/filter eligibility is not a decoder failure: nothing is identified
                # under the selected filter yet, so the part would be empty. Keep the bounded
                # session intact and retry later; ordinary retention counters expose any
                # history lost while identity remains unresolved.
                self._rollover_retry_at = time.monotonic() + 5
                self.diagnostics["archive_deferred"] = (
                    "Archive rollover is waiting for player data under the selected filter. "
                    "Capture continues; unresolved history remains subject to retention limits.")
                return
            # Detach the finished part under the lock (milliseconds: see
            # ``CombatSession.__deepcopy__``) and carry on recording in a fresh continuation at
            # once. Building and writing the part's document -- seconds for a big part -- happens
            # on a worker (``_flush_parts``): a forced mid-fight rollover used to run it on the
            # decoder thread, which froze the meter for as long as it took.
            detached = copy.deepcopy(self.session)
            detached.capture_evidence["storage_boundary"] = True
            detached.finish_run("storage_rollover", complete=False)
            part = {"session": detached, "metadata": dict(self.metadata), "profile": dict(self.packet_engine.local_profile),
                    "scope": self.scope, "collector": self.capture_metadata, "file": self.session_file,
                    "archive": self._archive_metadata(detached, closed=True),
                    "title": f"Live combat session {self.archive_id[:8]} · Part {self.archive_part}"}
            self.session = self.session.continuation()
            self._snap_cache = None      # the continuation is a fresh session object
            self.session.capture_evidence["storage_boundary"] = True
            # The lifetime counters as they stand when this part begins: the quality gate charges
            # the part only with what accrues after this (a loss during an earlier part is not
            # this part's loss; see quality.LIFETIME_COUNTERS).
            self.session.capture_evidence["part_baseline"] = {
                k: int(self.session.capture_evidence[k]) for k in LIFETIME_COUNTERS
                if isinstance(self.session.capture_evidence.get(k), int) and self.session.capture_evidence[k] > 0}
            self.archive_part += 1
            self.archive_previous = part["archive"].get("continuity")
            self.archive_part_token = uuid.uuid4().hex
            self.session_file = f"session-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.a2log.json"
            self.segment_id = self.enemy_id = None
            self._unsaved_parts.append(part)
            self.diagnostics.pop("archive_deferred", None)
            self._rollover_retry_at = 0.0
        self._last_checkpoint = time.monotonic()
        self._spawn_flush()

    def _recent_outgoing(self, window_ms: int) -> bool:
        """Whether the selected scope landed outgoing damage within ``window_ms`` (tracked by the
        session as records arrive, so this never walks the record history)."""
        last = getattr(self.session, "_last_outgoing", {}).get(self.scope)
        return bool(last) and time.time() * 1000 - last < window_ms

    def _spawn_flush(self) -> bool:
        worker = self._flush_thread
        if worker is not None and worker.is_alive():
            return False
        self._flush_thread = threading.Thread(target=self._flush_parts, daemon=True, name="part-flush")
        self._flush_thread.start()
        return True

    def _flush_parts(self) -> None:
        with self._session_save_lock:
            self._flush_pending_parts()

    def _flush_pending_parts(self) -> None:
        """Write the archive parts a rollover detached, oldest first. Caller holds
        ``_session_save_lock``. A part whose document cannot be built or written yet stays queued
        (in memory) and is retried on the next save; the final save after Stop reports one it
        still cannot write instead of silently dropping it."""
        from ..combat.sessions import save
        while True:
            with self.lock:
                if not self._unsaved_parts:
                    return
                part = self._unsaved_parts[0]
            try:
                document = part["session"].to_a2log(part["scope"], part["title"])
                doc = self._metadata(document, metadata=part["metadata"], profile=part["profile"], collector=part["collector"])
                doc["meta"].update(capture_active=False, checkpoint_at=time.time(), archive=part["archive"])
                saved = str(save(doc, part["file"]))
            except NoIdentifiedPlayerData as exc:
                if self.running:
                    return                      # identity may still resolve for a later part; retry on the next save
                with self.lock:
                    self._unsaved_parts.pop(0)
                self.diagnostics["archive_part_unsaved"] = f"Part {part['archive']['part']}: {exc}"
                continue
            except Exception as exc:   # noqa: BLE001 - a part that cannot be written yet is retried, never lost
                self.diagnostics["archive_save_error"] = f"{type(exc).__name__}: {exc}"[:300]
                return
            with self.lock:
                self._unsaved_parts.pop(0)
                self.saved_log = saved
                self._written_files.setdefault(part["file"], time.time())
                self.diagnostics["archive_parts_saved"] = self.diagnostics.get("archive_parts_saved", 0) + 1
                self.diagnostics["archive_last_part"] = saved
                self.diagnostics.pop("archive_save_error", None)

    def _save_session(self, active: bool) -> None:
        # "Save combat records" off: never auto-write the session log to disk.
        # The user can still Save/Export/Upload a session explicitly.
        if not self.save_records or self.packet_engine is None or not self.session.records:
            return
        # Serialize snapshot and replacement together so an older periodic save
        # cannot overwrite the final snapshot after Stop.
        with self._session_save_lock:
            self._flush_pending_parts()     # rolled-over parts go to disk before the live part
            self._store_boss_hp()
            started = time.monotonic()
            try:
                from ..combat.sessions import save
                doc = self.to_a2log()
                doc["meta"].update(capture_active=bool(active and self.running),
                                   checkpoint_at=time.time(), capture_scope=self.scope)
                self.saved_log = str(save(doc, self.session_file))
                self._written_files.setdefault(self.session_file, time.time())
                self.diagnostics.pop("log_save_error", None)
                self._last_save_cost = time.monotonic() - started
            except Exception as exc:   # noqa: BLE001 - a save must never abort Stop or the
                # diagnostics archive that follows it. Any failure (including an unexpected
                # one on a very large session) is recorded and swallowed so Stop still
                # closes out, writes the diagnostics ZIP, and the last good checkpoint log
                # (saved every 15s) remains available to upload.
                self.diagnostics["log_save_error"] = f"{type(exc).__name__}: {exc}"
                return
            # Opt-in, anonymous world-boss-kill community report (off by default).
            # Best-effort and deduped per kill, so repeated checkpoint saves of the
            # same fight report it at most once; never blocks or raises here.
            try:
                from ..combat import boss_report
                boss_report.report_async(doc)
            except Exception:
                pass
            # Opt-OUT (on by default), anonymous enemy effective-HP community report.
            # Posts how much damage each killed enemy took to die so the server can
            # build a per-build HP consensus; carries nothing identifying, deduped per
            # kill, best-effort, never blocks or raises here.
            try:
                from ..combat import hp_report
                hp_report.report_async(doc, final=not active)
            except Exception:
                pass
            # Opt-OUT (on by default), anonymous diagnostics beacons: ids the catalog
            # doesn't map yet (to fill catalog gaps) and capture-pipeline health (to
            # catch regressions across users). Only on the final save (not every
            # checkpoint), so the counters are complete and it posts once per session.
            if not active:
                try:
                    from ..combat import diag_report
                    diag_report.report_async(doc, dict(self.diagnostics))
                except Exception:
                    pass
            # Keep the logs folder under the user's cache cap (default 1 GB). A long
            # session writes many rollover parts, so prune the oldest here — throttled
            # so it runs at most ~once/minute — never removing the file just written.
            try:
                now = time.monotonic()
                if now - self._last_prune >= 60:
                    self._last_prune = now
                    from ..app import server as _srv
                    cap_mb = _srv.ui_settings().get("meter_log_cache_mb", 1024)
                    if isinstance(cap_mb, int) and not isinstance(cap_mb, bool) and cap_mb > 0:
                        from ..combat.sessions import prune_logs
                        # Upload recordings about to be reclaimed by the cap first (on by
                        # default), so a long session's older parts aren't lost before they
                        # can be shared; the active file is always kept out of the sweep.
                        prune_logs(cap_mb * 1024 * 1024, keep={self.session_file}, evict=upload_evictor())
            except Exception:
                pass

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
            diagnostic["capture_processing"] = {k:self.session.capture_evidence.get(k) for k in ("capture_errors", "decoder_errors", "recovered_frame_skips", "shutdown_discarded_payloads", "shutdown_drained_payloads")}
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

    def _live_snapshot(self, follow_latest: bool) -> dict:
        """The live session snapshot, memoized for a short, self-tuning interval so
        the app and overlay polling together never drive the costly full-session
        recompute more than once per the time that recompute itself takes. Must be
        called with ``self.lock`` held (the caller holds it). The cache only serves
        the live display; save/export/upload call the session directly."""
        key = (self.scope, "__latest__" if follow_latest else self.segment_id,
               None if follow_latest else self.enemy_id, self.combine_pets)
        now = time.monotonic()
        cached = self._snap_cache
        if cached is not None and cached[0] == key:
            # Never recompute more often than the last recompute cost (floor 250ms). When packets
            # have backed up (a heavy fight the decoder is behind on), stretch that interval so
            # the recompute steps further aside — the live number simply updates a little less
            # often until it catches up. The recompute itself runs on a worker from a detached
            # copy of the session (``_schedule_snapshot``): it walks every record, which held the
            # capture lock for seconds in a big fight and starved the decoder. Meanwhile the last
            # completed reading is served.
            busy = self.packet_queue is not None and self.packet_queue.qsize() >= _DECODE_BACKLOG_QUEUE
            interval = max(0.25, self._last_snap_cost) * (_SNAPSHOT_BACKLOG_DUTY if busy else 1.0)
            if now - cached[1] > interval:
                self._schedule_snapshot(key, follow_latest)
            return cached[2]
        # The first reading of a view (a fresh capture, a changed selection): compute it now.
        started = time.monotonic()
        snap = self.session.snapshot(self.scope, None if follow_latest else self.segment_id,
                                     None if follow_latest else self.enemy_id, self.combine_pets)
        self._last_snap_cost = time.monotonic() - started
        self._snap_cache = (key, time.monotonic(), snap)
        return snap

    def _schedule_snapshot(self, key, follow_latest: bool) -> bool:
        """Recompute the live snapshot on a worker from a detached copy of the session. The copy
        takes milliseconds (``CombatSession.__deepcopy__`` shares the record history); one
        recompute runs at a time, and its result is kept only if the view and the live session
        are still the ones it was taken from. Caller holds ``self.lock``."""
        worker = self._snap_thread
        if worker is not None and worker.is_alive():
            return False
        source = self.session
        try:
            detached = copy.deepcopy(source)
        except Exception:   # noqa: BLE001 - a view that cannot be detached is recomputed in place next time
            return False
        args = (key, source, self._capture_generation, detached, self.scope,
                None if follow_latest else self.segment_id, None if follow_latest else self.enemy_id, self.combine_pets)
        self._snap_thread = threading.Thread(target=self._compute_snapshot, args=args, daemon=True, name="live-snapshot")
        self._snap_thread.start()
        return True

    def _compute_snapshot(self, key, source, generation, session, scope, segment_id, enemy_id, combine_pets) -> None:
        # ``source`` is the live session the copy was taken from, held so it cannot be freed and
        # its identity reused by a continuation; the reading is kept only while it is still live.
        started = time.monotonic()
        try:
            snap = session.snapshot(scope, segment_id, enemy_id, combine_pets)
        except Exception as exc:   # noqa: BLE001 - the live view keeps its last reading
            self.diagnostics["snapshot_error"] = f"{type(exc).__name__}: {exc}"[:300]
            return
        cost = time.monotonic() - started
        with self.lock:
            self._last_snap_cost = cost
            if self.session is source and self._capture_generation == generation and (
                    self._snap_cache is None or self._snap_cache[0] == key):
                self._snap_cache = (key, time.monotonic(), snap)

    _BOSS_HP_FILE = ("community", "boss_hp_seen.json")

    def _seed_boss_hp(self, engine) -> None:
        """Prime the engine's boss max-HP memory for the current build from disk (best-effort)."""
        try:
            from ..paths import data_file, read_json
            build = self._game_build()
            if not build or not data_file(*self._BOSS_HP_FILE).exists():
                return
            table = (read_json(*self._BOSS_HP_FILE).get("builds") or {}).get(build) or {}
            for code, hp in table.items():
                try:
                    engine.boss_hp_seen.setdefault(int(code), float(hp))
                except (TypeError, ValueError):
                    continue
        except Exception:
            pass

    def _store_boss_hp(self) -> None:
        """Persist the engine's boss max-HP memory for the current build (best-effort, bounded)."""
        try:
            engine = self.packet_engine
            seen = dict(getattr(engine, "boss_hp_seen", None) or {})
            build = self._game_build()
            if not seen or not build:
                return
            from ..paths import data_file, read_json, write_user_json
            doc = read_json(*self._BOSS_HP_FILE) if data_file(*self._BOSS_HP_FILE).exists() else {}
            builds = doc.get("builds") if isinstance(doc.get("builds"), dict) else {}
            table = dict(builds.get(build) or {})
            table.update({str(code): float(hp) for code, hp in seen.items()})
            builds[build] = dict(list(table.items())[-500:])
            write_user_json({"builds": dict(list(builds.items())[-8:])}, *self._BOSS_HP_FILE)
        except Exception:
            pass

    def _game_build(self) -> str | None:
        """The game build to key community HP lookups on, matching what the enemy-HP
        reporter sends (the content patch first). None when no build is detected yet."""
        meta = self.metadata or {}
        build = meta.get("game_patch")
        if not build and self.capture_metadata is not None:
            try:
                server_id = (self.packet_engine.local_profile or {}).get("serverId") if self.packet_engine else None
                detected = self.capture_metadata.snapshot(server_id)
                build = (detected.get("game_patch") or detected.get("installed_content_build")
                         or detected.get("installed_build"))
            except Exception:
                build = None
        return build if isinstance(build, str) and build.strip() else None

    def status(self, *, follow_latest: bool = False, compact: bool = False) -> dict:
        if not self.lock.acquire(timeout=0.5):
            # The capture thread is mid-burst. Rather than failing (which freezes the
            # overlay on a "refresh failed" message during the busiest moments of a
            # fight), serve the most recent reading, flagged stale, if we have one.
            cached = self._status_cache.get((compact, follow_latest))
            if cached is not None:
                return {**cached, "stale": True}
            raise TimeoutError("Capture data is busy; refresh will retry. Capture diagnostics can still be exported.")
        try:
            finalizing = bool(not self.running and self.thread and self.thread.is_alive())
            snap = (self._live_snapshot(follow_latest)
                    if self.packet_engine is not None else self.meter.snapshot())
            if self.packet_queue is not None:
                # Let the live view (app and overlay both read the snapshot) show when the
                # decoder is behind real time during a burst, instead of looking frozen.
                # Final totals are unaffected — the backlog is drained, never dropped.
                qd = self.packet_queue.qsize()
                snap["decode_backlog"] = {"queue_depth": qd, "catching_up": qd >= _DECODE_BACKLOG_QUEUE}
            if self.packet_engine is not None:
                snap["ping"] = self.meter.ping_summary()   # the session snapshot carries no latency
            # Blend the community effective-HP consensus (confident, per-build, cached
            # on disk) into the enemy/target HP so it reads in damage units. Pure and
            # cached — no network here — and best-effort, so it never affects capture.
            try:
                from ..combat import hp_db
                build = self._game_build()
                hp_db.refresh_async(build)
                hp_db.enrich(snap, build)
            except Exception:
                pass
            # Community rank badges (filled after an upload; off by default). Attach to
            # the snapshot so both the compact overlay view and the full page carry them,
            # keyed per player so the local player and resolved party members all show.
            if self._community_rank:
                engine = self.packet_engine
                local = engine.local_player_id if engine else None
                if local is not None and local in self._community_rank:
                    snap["community_rank"] = self._community_rank[local]
                for p in snap.get("players", []):
                    badge = self._community_rank.get(p.get("id"))
                    if badge:
                        p["community_rank"] = badge
            # Opt-in per-fight refresh of those badges (off by default; cheap-gated, worker-backed).
            self._maybe_live_rank()
            # When the viewer turns the option on, label each player's home world next to their
            # name, resolved from their captured server id via the same official server list used
            # for region. Off by default; best-effort and local (no network in this path).
            if self.capture_metadata is not None:
                from .server import ui_settings
                if ui_settings().get("meter_show_server_name"):
                    for p in snap.get("players", []):
                        server = p.get("server")
                        if server and not p.get("server_name"):
                            name = self.capture_metadata.snapshot(server).get("server_name")
                            if name:
                                p["server_name"] = name
            if self.packet_engine is not None and not follow_latest:
                self.enemy_id = snap.get("selected_enemy")
            if compact:
                result = {"running": self.running, "finalizing": finalizing, "error": self.error,
                          "combine_pets": self.combine_pets, "snapshot": snap}
                self._status_cache[(True, follow_latest)] = result
                return result
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
            diagnostic["capture_processing"] = {k:self.session.capture_evidence.get(k) for k in ("capture_errors", "decoder_errors", "recovered_frame_skips", "shutdown_discarded_payloads", "shutdown_drained_payloads")}
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
        result = {"running": self.running, "finalizing": finalizing, "source": self.source_name, "error": self.error,
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
        self._status_cache[(False, follow_latest)] = result
        return result

    def apply_community_rank(self, doc: dict, upload_result: dict) -> None:
        """After an upload, cache each player's confident community standing for its
        main fight so the overlay can badge the local player and resolved party members.

        Best-effort and fully guarded: it makes one read-only call to the configured
        log server for the just-uploaded log's rankings, and any failure (feature off,
        no server, old server, network error) simply leaves the badges unset. It never
        raises and never touches capture."""
        try:
            from .server import ui_settings
            if not ui_settings().get("overlay_show_community_rank"):
                return   # feature off -> do not call out to the server
            log_id = (upload_result or {}).get("id")
            segments = doc.get("segments") or []
            player_ids = [p["id"] for p in doc.get("players", []) if p.get("id")]
            if not log_id or not segments or not player_ids:
                return
            # The main fight is the segment with the most recorded player damage.
            main = max(range(len(segments)),
                       key=lambda i: sum(h.get("damage", 0) for h in segments[i].get("hits", [])))
            from ..combat import share, community_rank
            data = share.community_request(f"/api/v1/logs/{log_id}/rankings?segment={main}")
            mapped = {}
            for pid, summary in community_rank.badges(data, player_ids).items():
                text = community_rank.badge_text(summary)
                if text:
                    mapped[pid] = {"text": text, "scope": summary["best"]["scope"],
                                   "percentile": summary["best"]["percentile"]}
            self._community_rank = mapped
        except Exception:
            pass

    def _maybe_live_rank(self) -> None:
        """Opt-in: once a fight has paused during live capture, refresh the community-rank
        badge from a fresh unlisted upload, so it updates per-fight instead of only on a
        manual Upload. Cheap-gated here; the upload/ranking run on a worker. Fully guarded,
        throttled, one in flight at a time, and never touches capture."""
        try:
            if not self.running or self._live_rank_busy or self._last_combat_at is None:
                return
            now = time.monotonic()
            if now - self._last_combat_at < _LIVE_RANK_IDLE_S or now - self._live_rank_last < _LIVE_RANK_THROTTLE_S:
                return   # still mid-fight, or refreshed too recently
            from .server import ui_settings
            ui = ui_settings()
            if not (ui.get("overlay_live_community_rank") and ui.get("overlay_show_community_rank")):
                return
            with self.lock:
                key = (len(self.session.records), self.session.run)
            if not key[0] or key == self._live_rank_key:
                return   # no combat yet, or no new fight since the last refresh
            self._live_rank_busy = True
            self._live_rank_key, self._live_rank_last = key, now
            threading.Thread(target=self._live_rank_upload, daemon=True, name="live-rank").start()
        except Exception:
            pass

    def _live_rank_upload(self) -> None:
        """Worker: upload the current snapshot unlisted and refresh the badge, but only for a
        ranked-eligible main fight — so trash pulls neither upload nor wipe a standing."""
        try:
            from ..combat import share, quality
            if not share.effective().get("url") or share.automatic_uploads_paused():
                return   # no server, or its upload bucket is spent (a 429): refresh later
            doc = self.to_a2log()
            segments = doc.get("segments") or []
            if not segments:
                return
            main = max(range(len(segments)),
                       key=lambda i: sum(h.get("damage", 0) for h in segments[i].get("hits", [])))
            if not quality.assess(doc, segments[main]).get("eligible"):
                return   # unranked fight: don't upload it, and leave the last standing in place
            result = share.upload(doc, visibility="unlisted")
            self.apply_community_rank(doc, result)
        except Exception:
            pass
        finally:
            self._live_rank_busy = False

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

    def retry_region(self):
        """Re-attempt the official region/world-name lookup now (it runs once at launch and can
        fail offline or if the source is blocked). Reuses the active capture collector so a live
        session picks up the result; otherwise makes one so the refreshed cache is ready for the
        next capture. Returns the metadata snapshot; the fetch completes in the background."""
        from ..meter.metadata import CaptureMetadata
        with self.lock:
            if self.capture_metadata is None:
                self.capture_metadata = CaptureMetadata()
            collector = self.capture_metadata
        return collector.refresh()

    def apply_record_settings(self) -> None:
        """Copy the user's combat-records preferences onto the live session so the
        snapshot reflects them. Safe to call while running; defaults hold if the
        settings file is unavailable."""
        try:
            from .server import ui_settings
            ui = ui_settings()
        except Exception:
            return
        self.session.reset_after_battle = bool(ui.get("meter_reset_after_battle", False))
        self.session.reset_on_boss_start = bool(ui.get("meter_reset_on_boss_start", True))
        self.session.reset_delay_seconds = min(120, max(1, int(ui.get("meter_reset_delay", 5) or 5)))
        self.session.max_records = min(500, max(0, int(ui.get("meter_max_records", 20) or 0)))
        self.session.dummy_record_seconds = min(3600, max(5, int(ui.get("meter_dummy_record_seconds", 60) or 60)))
        self.save_records = bool(ui.get("meter_save_records", True))

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
                self.session.retain_scope = self.scope   # from now on; a narrower past is not re-widened
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
            self._snap_cache = None
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
            # The live part is open while capture runs; once capture has stopped it is the
            # recording's final, finished part -- closed, so it carries a stable recording key
            # (the server ignores a re-upload of it) and is never mistaken for a checkpoint.
            closed = not self.running
            archive = (self._archive_metadata(session, closed=closed) if isinstance(session, CombatSession)
                       else {"id":self.archive_id, "part":self.archive_part, "closed":closed})
        if isinstance(session, CombatSession) and not title:
            title = f"Live combat session {archive['id'][:8]} Â· Part {archive['part']}"
        doc = session.to_a2log(scope, title) if isinstance(session, CombatSession) else session.to_a2log(title=title)
        if isinstance(session, CombatSession):
            doc["meta"]["archive"] = archive
        return self._metadata(doc, metadata=metadata, profile=profile, collector=collector)

    # ---- automatic uploads of everything this launch recorded ------------------------------
    #: How long the quit path may spend uploading before the app exits regardless.
    QUIT_UPLOAD_BUDGET_S = 20.0
    #: Closed parts from earlier launches no older than this are picked up at launch (an upload
    #: that failed at the previous quit, or a part saved while the server was unreachable).
    CATCH_UP_DAYS = 7
    CATCH_UP_LIMIT = 20

    def pending_uploads(self, *, include_live: bool = False, catch_up_days: float | None = None,
                        limit: int = 50) -> list:
        """The recordings not yet on the configured server, newest first, as
        ``{"file": name | None, "doc": document, "live": bool}``.

        Every archive part this process saved since launch is a candidate: a closed part (one a
        rollover detached, or the final save after Stop) whose recording key is not remembered
        as uploaded. The live part is included first when ``include_live`` -- the Upload button,
        and the automatic upload after Stop -- as the in-memory document (the freshest copy of
        the current part), so its on-disk checkpoint is never sent as well. With
        ``catch_up_days`` the scan also covers closed parts on disk from earlier launches no
        older than that, bounded by ``limit``, so an upload the previous quit ran out of time
        for is not lost. Open checkpoints (capture still active) are never finished recordings."""
        from ..combat import share
        from ..combat.sessions import path as session_path, logs_dir
        names = dict(self._written_files)
        if catch_up_days:
            cutoff = time.time() - catch_up_days * 86400
            for target in logs_dir().glob("session-*.a2log.json"):
                try:
                    stamp = target.stat().st_mtime
                except OSError:
                    continue
                if stamp >= cutoff:
                    names.setdefault(target.name, stamp)
        seen, out = set(), []
        for name in sorted(names, key=lambda n: names[n], reverse=True):
            if name == self.session_file and (self.running or include_live):
                continue   # the live part is sent from memory (below), never from its checkpoint
            try:
                doc = json.loads(session_path(name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            meta = doc.get("meta") if isinstance(doc, dict) else None
            archive = (meta or {}).get("archive") or {}
            if not isinstance(meta, dict) or archive.get("closed") is not True or meta.get("capture_active"):
                continue
            key = share.recording_key(doc)
            if not key or key in seen or share.already_uploaded(doc):
                continue
            seen.add(key)
            out.append({"file": name, "doc": doc, "live": False})
            if len(out) >= limit:
                break
        if include_live and self.has_data():
            try:
                doc = self.to_a2log()
                key = share.recording_key(doc)       # None while capture runs: an open part
                if not (key and (key in seen or share.already_uploaded(doc))):
                    out.insert(0, {"file": None, "doc": doc, "live": True})
            except Exception:
                pass
        return out

    def upload_pending(self, *, log=None, include_live: bool = True, visibility: str | None = None,
                       budget_s: float | None = None, catch_up_days: float | None = None,
                       limit: int = 50, automatic: bool = False) -> dict:
        """Upload every pending recording (``pending_uploads``), newest first, one pass at a time
        so the page's Stop, the overlay's Stop and quit never send the same part twice. Returns
        ``{"uploaded", "failed", "pending", "url", "results"}``; ``url`` is the newest upload's
        link. ``budget_s`` bounds the pass (quit must not hang): what is left over is sent by the
        next Stop, Upload or launch. An ``automatic`` pass stands down while the server's upload
        limit is spent (a recent 429); the Upload button does not."""
        from ..combat import share
        say = log or (lambda *_: None)
        result = {"uploaded": 0, "failed": 0, "pending": 0, "url": None, "results": []}
        if not share.effective().get("url"):
            say("No log server is set; nothing to upload.")
            return result
        if automatic and share.automatic_uploads_paused():
            say("The server's upload limit was reached recently; pending recordings upload later.")
            return result
        with self._upload_lock:
            items = self.pending_uploads(include_live=include_live, catch_up_days=catch_up_days, limit=limit)
            if not items:
                say("Every recording from this session is already on the server.")
                return result
            if len(items) > 1:
                say(f"{len(items)} recordings to upload, newest first…")
            started = time.monotonic()
            for index, item in enumerate(items):
                if budget_s is not None and time.monotonic() - started > budget_s - 3:
                    result["pending"] = len(items) - index
                    say(f"Out of time: {result['pending']} recording(s) will upload at the next Stop or launch.")
                    break
                label = "the current session" if item["live"] else item["file"]
                say(f"Uploading {label}…")
                try:
                    sent = share.upload(item["doc"], visibility=visibility)
                except Exception as exc:   # noqa: BLE001 - one failed part must not stop the rest
                    result["failed"] += 1
                    result["results"].append({"file": item["file"], "error": str(exc)[:300]})
                    say(f"Upload of {label} failed: {exc}")
                    if share.automatic_uploads_paused():
                        result["pending"] += len(items) - index - 1
                        break
                    continue
                result["uploaded"] += 1
                result["results"].append({"file": item["file"], "id": sent.get("id"), "url": sent.get("url")})
                if result["url"] is None:
                    result["url"] = sent.get("url")
                if item["live"]:
                    try:
                        self.apply_community_rank(item["doc"], sent)   # the live fight's standings badge
                    except Exception:
                        pass
            return result

    def upload_pending_async(self, reason: str, **kw) -> bool:
        """Run ``upload_pending`` on a worker when automatic uploads are on (Settings:
        meter_auto_upload) and no pass is running. The launch catch-up pass also needs
        the catch-up setting (meter_catch_up_uploads). Returns whether a worker was started."""
        from ..app import server as _srv
        ui = _srv.ui_settings()
        if not ui.get("meter_auto_upload", True):
            return False
        if reason == "launch" and not ui.get("meter_catch_up_uploads", True):
            return False
        worker = self._pending_upload_thread
        if worker is not None and worker.is_alive():
            return False

        def _run():
            try:
                self.upload_pending(automatic=True, **kw)
            except Exception:
                traceback.print_exc()
        self._pending_upload_thread = threading.Thread(target=_run, daemon=True, name=f"auto-upload-{reason}")
        self._pending_upload_thread.start()
        return True

    def upload_document(self, title: str | None = None):
        """The document(s) the Upload button sends. A single-part session uploads as it
        is. A long session that rolled across a storage boundary into parts uploads the
        **original source parts** — the live current part plus each earlier closed part —
        individually; the server links them under one recording by archive id, so a
        single recording still holds every encounter, not only the latest part.

        The parts are *not* stitched into one combined recording for upload: a combined
        recording is a reconstructed *review*, which the server refuses ("Combined
        recording reviews cannot be uploaded; upload the original source parts"). The
        combined review stays a local-only feature (the Combat Logs review page).

        Returns ``(doc, extras)``: ``doc`` is the current part to upload and ``extras``
        is the list of earlier part documents to upload alongside it (empty for a
        single-part session)."""
        current = self.to_a2log(title)
        try:
            from ..combat.sessions import live_archive_sources
            sources = live_archive_sources(current)
        except Exception:
            sources = None
        if not sources:
            return current, []
        # sources is [earlier closed parts…, current]: upload each part as its own
        # document (earlier parts are finalised a2logs from disk, current is the live
        # part) so the server groups them under one recording by archive id.
        return current, [doc for _, doc in sources[:-1]]

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
            if detected.get("server_name") and not doc["meta"].get("server_name"):
                doc["meta"]["server_name"] = detected["server_name"]
            for actor in doc.get("players", []):
                detected_player = collector.snapshot(actor.get("server"))
                if detected_player.get("region") and not actor.get("region"):
                    actor["region"] = detected_player["region"]
                if detected_player.get("server_name") and not actor.get("server_name"):
                    actor["server_name"] = detected_player["server_name"]
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
        # Stamp who uploaded this log — the local (recording) player — so public logs can show it.
        # Best-effort and never required: if the local player isn't identified, it's left unset and
        # the server/site fall back to "Anonymous". A label only; it never gates anything.
        if "uploader" not in doc["meta"]:
            try:
                uploader = uploader_of(doc, profile, self.packet_engine)
                if uploader:
                    doc["meta"]["uploader"] = uploader
            except Exception:
                pass
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


def uploader_of(doc, profile, engine):
    """The recording (local) player as a ``meta.uploader`` stamp, or None when they cannot be
    named. Resolved from the log's own evidence first: the live engine's name table no longer
    holds the local actor by the time a finished session is saved or uploaded (every zone load
    reassigns the actor id and drops the old binding), which left uploads shown as "Anonymous"
    even with the character configured."""
    players = doc.get("players") or []
    name, official, match = None, False, None
    # Prefer the local player's name exactly as it appears in this log's own roster, matched by
    # official character id (roster ids are "p:<server>:<dbid>"). Robust when the live actor id is
    # an unnamed combat entity, and guaranteed to pass the server's roster check.
    if profile.get("serverId") and profile.get("dbid"):
        want = f"p:{profile['serverId']}:{profile['dbid']}"
        name = next((p.get("name") for p in players if p.get("id") == want), None)
        official = bool(name)
    # Each segment names its recorder -- the local player's roster id, resolved per identity epoch
    # when the segment was built. That is the recording's own answer to "who recorded this".
    if not name:
        recorders = {s.get("ping_recorder") for s in doc.get("segments", []) if s.get("ping_recorder")}
        match = next((p for p in players if p.get("id") in recorders and p.get("name")), None)
        if match:
            name, official = match["name"], bool(match.get("character_id"))
    # The character name the user configured for the meter, when it is in this roster.
    if not name and engine is not None and getattr(engine, "local_character_name", ""):
        wanted = str(engine.local_character_name).strip().casefold()
        match = next((p for p in players if str(p.get("name") or "").strip().casefold() == wanted), None)
        name = match.get("name") if match else None
    # Fall back to the engine's name for the recording actor.
    if not name and engine is not None and engine.local_player_id is not None:
        name = engine.names.get(engine.local_player_id)
    if not name or re.fullmatch(r"(?:Player\s*)?#?\d+", str(name).strip(), re.I):
        return None
    uploader = {"name": str(name).strip()[:60],
                "verified": bool(official or (engine is not None and getattr(engine, "local_identity_from_game", False)))}
    server = profile.get("serverId") or (match or {}).get("server")
    if server:
        uploader["server"] = str(server)
    character_id = profile.get("dbid") or (match or {}).get("character_id")
    if character_id:
        uploader["character_id"] = str(character_id)
    return uploader


_RUNNER: Runner | None = None


def runner() -> Runner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = Runner()
    return _RUNNER
