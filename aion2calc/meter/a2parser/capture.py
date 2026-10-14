"""Optional Scapy/Npcap live TCP payload capture adapter."""

from __future__ import annotations

import queue
import threading
import time

MAX_REORDERED_SEGMENTS = 256
MAX_REORDER_DISTANCE = 1_048_576
MAX_GAP_WAIT_SECONDS = 5.0


def interface_details() -> list[dict[str, str]]:
    """Return Npcap identifiers with readable names; keep errors visible to the UI."""
    from scapy.all import conf
    conf.ifaces.reload()
    rows = []
    for device in conf.ifaces.values():
        name = str(device.network_name)
        if name and name != "any":
            label = str(device.description or device.name or name)
            rows.append({"name": name, "label": label, "address": str(device.ip or "")})
    return sorted({row["name"]: row for row in rows}.values(), key=lambda row: row["label"].casefold())


def available_interfaces() -> list[str]:
    """Return capture-device identifiers exposed by Scapy/Npcap."""
    try:
        return [row["name"] for row in interface_details()]
    except Exception:
        return []


class TCPReassembler:
    """Small per-direction TCP sequence reassembler with overlap suppression."""

    def __init__(self) -> None:
        self.next_seq: int | None = None
        self.waiting: dict[int, bytes] = {}
        self.last_seen = time.monotonic()
        self.discarded_payloads = 0
        self.gap_started: float | None = None
        self.generation = 0

    def feed(self, sequence: int, payload: bytes, *, syn: bool = False) -> bytes:
        self.last_seen = time.monotonic()
        sequence &= 0xFFFF_FFFF
        if syn:
            sequence = (sequence + 1) & 0xFFFF_FFFF
            if self.next_seq is not None and self.next_seq != sequence:
                self._restart(sequence)
        if self.next_seq is None:
            self.next_seq = sequence
        if not payload:
            return b""
        delta = (sequence - self.next_seq) & 0xFFFF_FFFF
        if delta >= 0x8000_0000:
            overlap = (self.next_seq - sequence) & 0xFFFF_FFFF
            if overlap >= len(payload):
                return b""
            payload = payload[overlap:]
            sequence = self.next_seq
            delta = 0
        if delta:
            if self.gap_started is None:
                self.gap_started = self.last_seen
            if (self.last_seen - self.gap_started >= MAX_GAP_WAIT_SECONDS
                    or delta > MAX_REORDER_DISTANCE
                    or sequence not in self.waiting and len(self.waiting) >= MAX_REORDERED_SEGMENTS):
                # A missed capture chunk may never be retransmitted to this
                # observer. Resume from fresh bytes instead of buffering forever.
                # This is a lossy boundary, never reconstruction of missing data.
                self._restart(sequence)
            else:
                previous = self.waiting.get(sequence)
                if previous is None or (len(payload) > len(previous) and payload.startswith(previous)):
                    self.waiting[sequence] = payload
                return b""
        output = bytearray(payload)
        self.next_seq = (self.next_seq + len(payload)) & 0xFFFF_FFFF
        while self.waiting:
            ready = self.waiting.pop(self.next_seq, None)
            if ready is not None:
                chunk = ready
            else:
                # Discard fully-covered queued retransmissions, or trim an
                # overlapping segment to its unseen suffix. TCP sequence
                # distances are compared modulo 2^32 (all queues stay <2^31).
                chunk = None
                for waiting_seq, waiting_data in tuple(self.waiting.items()):
                    overlap = (self.next_seq - waiting_seq) & 0xFFFF_FFFF
                    if overlap >= 0x8000_0000:
                        continue
                    self.waiting.pop(waiting_seq)
                    if overlap < len(waiting_data):
                        chunk = waiting_data[overlap:]
                        break
                if chunk is None:
                    break
            output.extend(chunk)
            self.next_seq = (self.next_seq + len(chunk)) & 0xFFFF_FFFF
        if not self.waiting:
            self.gap_started = None
        return bytes(output)

    def _restart(self, sequence: int) -> None:
        self.discarded_payloads += max(1, len(self.waiting))
        self.waiting.clear()
        self.next_seq = sequence
        self.gap_started = None
        self.generation += 1


class CombatFlowDetector:
    """Identify a game flow with the upstream 12-packet/3-second marker gate."""
    signatures = (b"\x0e\x00\x36", b"\x06\x00\x36")

    def __init__(self):
        self.candidates: dict[tuple, dict] = {}
        self.selected: tuple | None = None
        self.first_candidate: float | None = None
        self.selected_last_seen: float | None = None

    def reset(self) -> None:
        self.selected = None
        self.selected_last_seen = None
        self.first_candidate = None
        self.candidates.clear()

    def is_connection(self, key: tuple) -> bool:
        if self.selected is None:
            return False
        selected = self.selected
        return key == selected or key == (selected[0], selected[3], selected[4], selected[1], selected[2])

    def feed(self, key: tuple, payload: bytes, sequence: int, syn: bool, now: float) -> list[tuple]:
        if self.selected is not None:
            if key == self.selected:
                if payload:
                    self.selected_last_seen = now
                return [(key, sequence, payload, syn)]
            # Zone changes can replace the socket without a captured FIN/RST.
            # Resume the marker gate when the previous server stream goes idle.
            if self.selected_last_seen is not None and now - self.selected_last_seen >= 5.0:
                self.reset()
            else:
                return []
        if not payload or (len(payload) >= 3 and 0x14 <= payload[0] <= 0x17 and payload[1] == 3):
            return []
        marked = any(signature in payload for signature in self.signatures)
        candidate = self.candidates.get(key)
        if candidate is None:
            if not marked:
                return []
            if len(self.candidates) >= 64:
                oldest = min(self.candidates, key=lambda item: self.candidates[item]["last"])
                self.candidates.pop(oldest)
            candidate = self.candidates[key] = {"hits": [], "packets": [], "bytes": 0, "last": now}
            if self.first_candidate is None:
                self.first_candidate = now
        candidate["last"] = now
        candidate["hits"] = [stamp for stamp in candidate["hits"] if now - stamp <= 3.0]
        if marked:
            candidate["hits"].append(now)
        candidate["packets"].append((key, sequence, payload, syn))
        candidate["bytes"] += len(payload)
        while candidate["bytes"] > 524_288 and len(candidate["packets"]) > 1:
            candidate["bytes"] -= len(candidate["packets"].pop(0)[2])
        loopback = key[1] in ("127.0.0.1", "::1") or "loopback" in key[0].lower()
        if len(candidate["hits"]) < 12 or (not loopback and now - self.first_candidate < 2.5):
            return []
        self.selected = key
        self.selected_last_seen = now
        packets = candidate["packets"]
        self.candidates.clear()
        return packets


def tcp_payload(ip, tcp) -> bytes:
    """Use network-layer lengths: Ethernet padding is not TCP stream data."""
    raw = bytes(tcp.payload)
    header = int(tcp.dataofs or 5) * 4
    if ip.version == 4:
        size = int(ip.len) - int(ip.ihl or 5) * 4 - header
    else:
        # IPv6 plen includes extension headers before TCP, but excludes its
        # 40-byte base header. Serialized lengths cancel any trailing padding.
        extensions = len(bytes(ip.payload)) - len(bytes(tcp))
        size = int(ip.plen) - extensions - header
    return raw[:max(0, size)]


def capture_packets(stop_event: threading.Event, output_queue: queue.Queue,
                    interface: str | None = None, server_port: int = 50349,
                    generation: int | None = None, host: str | None = None,
                    auto_port: bool = False, recorder=None) -> None:
    """Capture on usable adapters, optionally detect the game flow, and reassemble it."""
    def emit(kind: str, *data) -> None:
        output_queue.put((kind, *data) if generation is None else (kind, generation, *data))

    if not 1 <= int(server_port) <= 65_535:
        emit("error", "The server port must be between 1 and 65535.")
        return
    server_port = int(server_port)
    host = (host or "").strip() or None
    if host:
        import ipaddress
        try:
            host = str(ipaddress.ip_address(host))
        except ValueError:
            emit("error", "Game host must be an IPv4 or IPv6 address, or any.")
            return
    try:
        from scapy.all import AsyncSniffer, IP, IPv6, TCP
        from scapy.interfaces import resolve_iface
        from .capture_stats import PcapStats, FIELDS, NOTE
        interfaces = [interface] if interface else available_interfaces()
        if not interfaces:
            raise RuntimeError("No capture adapters are available. Install capture support and restart the app.")
    except Exception as exc:
        emit("error", f"Cannot initialize packet capture: {exc}")
        return
    flows: dict[tuple, TCPReassembler] = {}
    detector = CombatFlowDetector()
    callback_lock = threading.Lock()
    from .passive_rtt import PassiveRTT
    rtt = PassiveRTT()  # Accessed only under callback_lock, like detector state.
    stats = {"packets": 0, "payload_packets": 0, "bytes": 0, "forwarded": 0,
             "auto_port": auto_port, "port": None if auto_port else server_port,
             "flow_detected": False, "capture_filter": None,
             "interface": interface or "Auto", "interfaces": interfaces, "warnings": [],
             "state": "starting", "signature_packets": 0, "candidate_flows": [],
             "transport_monitored": True, "tcp_discarded_payloads": 0, "tcp_unresolved_flows": 0,
             "tcp_pending_bytes": 0, "tcp_stream_resets": 0}
    last_prune = time.monotonic()
    # Kernel BPF filter management. In auto mode it starts broad ("tcp" — every TCP packet on the
    # machine, which floods the capture buffer and drops packets); once the game flow is located we
    # reopen capture narrowed to just that connection so the kernel discards everything else before it
    # ever reaches the buffer. If the narrowed flow goes silent (zone change, disconnect) we widen back
    # to re-detect. Fixed-port mode keeps its single filter and never switches.
    broad_filter = "tcp" if auto_port else f"tcp port {server_port}"
    if host:
        broad_filter += f" and host {host}"
    capture_state = {"filter": broad_filter}
    driver_base: dict[str, int] = {}
    NARROW_IDLE_WIDEN = 15.0

    def flow_filter(selected) -> str:
        # selected = (iface, src, sport, dst, dport). host+port on either endpoint of the connection
        # matches both directions of just that socket, so the kernel passes only the game flow.
        return f"tcp and host {selected[1]} and port {int(selected[2])}"

    def on_packet(packet) -> None:
        if TCP not in packet:
            return
        ip = packet[IP] if IP in packet else packet[IPv6] if IPv6 in packet else None
        if ip is None:
            return
        tcp = packet[TCP]
        if not auto_port and tcp.sport != server_port and tcp.dport != server_port:
            return
        source, destination = ip.src, ip.dst
        key = (str(getattr(packet, "sniffed_on", "")), source, int(tcp.sport), destination, int(tcp.dport))
        payload = tcp_payload(ip, tcp)
        syn = bool(int(tcp.flags) & 0x02)
        if recorder is not None:
            recorder.record(key, int(tcp.seq), int(tcp.flags), payload, time.time_ns() // 1_000_000)
        with callback_lock:
            # Auto mode measures only the selected game connection, not every socket
            # sharing its port. Fixed-port mode respects the configured host filter.
            selected = not auto_port or detector.selected and detector.is_connection(key)
            srv_port = detector.selected[2] if auto_port and detector.selected else server_port
            if selected and srv_port:
                connection = frozenset(((source, int(tcp.sport)), (destination, int(tcp.dport))))
                rtt_ms = rtt.observe(connection, int(tcp.seq), int(tcp.ack), int(tcp.flags),
                                     len(payload), int(tcp.dport) == srv_port, time.monotonic())
                if rtt_ms is not None:
                    emit("ping", rtt_ms, time.time_ns() // 1_000_000)
            stats["packets"] += 1
            stats["payload_packets"] += bool(payload)
            stats["bytes"] += len(payload)
            stats["signature_packets"] += int(any(marker in payload for marker in detector.signatures))
            if auto_port:
                chunks = detector.feed(key, payload, int(tcp.seq), syn, time.monotonic())
                stats["port"] = detector.selected[2] if detector.selected else None
                if detector.selected:
                    stats["interface"] = detector.selected[0]
                    stats["flow_detected"] = True   # the game flow was located (so the kernel filter could be narrowed to it)
            else:
                chunks = [(key, int(tcp.seq), payload, syn)]
            for stream_key, sequence, chunk, has_syn in chunks:
                # Shared sequence state suppresses duplicate fixed-port packets
                # seen on several adapters (e.g. VPN plus physical interface).
                flow_key = stream_key if auto_port else stream_key[1:]
                flow = flows.setdefault(flow_key, TCPReassembler())
                before, generation_before = flow.discarded_payloads, flow.generation
                reassembled = flow.feed(sequence, chunk, syn=has_syn)
                stats["tcp_discarded_payloads"] += flow.discarded_payloads - before
                _, src, sport, dst, dport = stream_key
                stream_id = f"{src}:{sport}->{dst}:{dport}"
                if flow.generation != generation_before:
                    stats["tcp_stream_resets"] += 1
                    emit("stream_reset", stream_id)
                    # Record loss before subsequent combat can trigger a save.
                    emit("capture_stats", dict(stats))
                if reassembled:
                    emit("packet", stream_id, reassembled, time.time_ns() // 1_000_000)
                    stats["forwarded"] += 1
            if int(tcp.flags) & (0x01 | 0x04):
                closed = flows.pop(key if auto_port else key[1:], None)
                stats["tcp_unresolved_flows"] += int(bool(closed and closed.waiting))
                if auto_port and detector.is_connection(key):
                    detector.reset()
                    stats["port"] = None

    sniffers = []
    resources = []

    def driver_snapshot():
        rows = [{"interface": name, **monitor.snapshot()} for name, _, monitor, _ in resources]
        return {**{key: driver_base.get(key, 0) + sum(row[key] for row in rows) for key in FIELDS},
                "pcap_stats_sampled": any(row["pcap_stats_sampled"] for row in rows),
                "pcap_stats_partial": len(resources) < len(interfaces) or any(row["pcap_stats_partial"] for row in rows),
                "pcap_interfaces": rows, "pcap_stats_note": NOTE}

    def packet_callback(monitor):
        def receive(packet):
            monitor.sample()  # Same thread as libpcap recv; no cross-thread handle calls.
            on_packet(packet)
        return receive

    def open_all(bpf_filter: str) -> int:
        """Open a capture socket + sniffer on every interface for this BPF filter; return how many opened."""
        opened = 0
        for name in interfaces:
            capture_socket = None
            try:
                capture_socket = resolve_iface(name).l2listen()(iface=name, filter=bpf_filter, promisc=False)
                monitor = PcapStats(capture_socket)
                if monitor.buffer_warning:
                    stats["warnings"].append(f"{name}: {monitor.buffer_warning}")
                monitor.sample(force=True)
                sniffer = AsyncSniffer(opened_socket={capture_socket: name}, prn=packet_callback(monitor), store=False)
                sniffer.start()
                resources.append((name, capture_socket, monitor, sniffer))
                sniffers.append((name, sniffer))
                opened += 1
            except Exception as exc:
                if capture_socket is not None:
                    try:
                        capture_socket.close()
                    except Exception:
                        pass
                stats["warnings"].append(f"{name}: {exc}")
        return opened

    def retire(entries) -> None:
        """Stop/close a set of capture entries, folding their final driver stats into the running base so
        lifetime totals stay monotonic across a filter switch. Must not run while holding callback_lock."""
        for _, _, _, sniffer in entries:
            if getattr(sniffer, "running", False):
                try:
                    sniffer.stop(join=False)
                except Exception:
                    pass
        deadline = time.monotonic() + 2
        for name, capture_socket, monitor, sniffer in entries:
            thread = getattr(sniffer, "thread", None)
            if thread is not None:
                thread.join(timeout=max(0, deadline - time.monotonic()))
            if thread is not None and thread.is_alive():
                stats["warnings"].append(f"{name}: capture thread did not stop while reconfiguring the filter")
                monitor.partial = True
                def close_after_exit(thread=thread, capture_socket=capture_socket):
                    thread.join()
                    try:
                        capture_socket.close()
                    except Exception:
                        pass
                threading.Thread(target=close_after_exit, daemon=True, name="capture-cleanup").start()
            else:
                monitor.sample(force=True)
                try:
                    capture_socket.close()
                except Exception as exc:
                    stats["warnings"].append(f"{name}: capture handle cleanup failed: {exc}")
        for key in FIELDS:
            driver_base[key] = driver_base.get(key, 0) + sum(monitor.snapshot()[key] for _, _, monitor, _ in entries)

    def switch_filter(new_filter: str) -> None:
        """Reopen capture under a new BPF filter, never leaving capture dark: if a narrowed filter opens
        no adapter, fall back to the broad one so the meter keeps seeing traffic."""
        old = list(resources)
        resources.clear()
        sniffers.clear()
        retire(old)
        if not open_all(new_filter) and new_filter != broad_filter:
            stats["warnings"].append("Narrowed capture could not be opened; fell back to the broad filter.")
            new_filter = broad_filter
            open_all(broad_filter)
        with callback_lock:
            capture_state["filter"] = new_filter
            stats["capture_filter"] = new_filter   # recorded in capture_quality: broad "tcp" vs. the narrowed flow

    try:
        stats["capture_filter"] = capture_state["filter"]
        open_all(capture_state["filter"])
        stats["state"] = "capturing"
        emit("capture_started")
        while not stop_event.wait(0.25):
            for name, sniffer in tuple(sniffers):
                thread = getattr(sniffer, "thread", None)
                if thread is not None and not thread.is_alive():
                    reason = getattr(sniffer, "exception", None) or "capture stopped unexpectedly"
                    stats["warnings"].append(f"{name}: {reason}")
                    sniffers.remove((name, sniffer))
            if not sniffers:
                raise RuntimeError("No capture adapter could be opened. " + "; ".join(stats["warnings"]) +
                                   ". Check capture permissions and Npcap, then restart the app.")
            now = time.monotonic()
            desired_filter = None
            with callback_lock:
                if now - last_prune >= 30:
                    for stale_key, flow in tuple(flows.items()):
                        if now - flow.last_seen >= 120:
                            stats["tcp_unresolved_flows"] += int(bool(flow.waiting))
                            flows.pop(stale_key, None)
                    last_prune = now
                if auto_port:
                    selected = detector.selected
                    # While narrowed, a flow that goes silent leaves us blind to any new flow, so drop it
                    # and widen to re-detect. (Broad mode keeps the detector's own reset behaviour.)
                    if (selected is not None and capture_state["filter"] != broad_filter
                            and detector.selected_last_seen is not None
                            and now - detector.selected_last_seen >= NARROW_IDLE_WIDEN):
                        detector.reset()
                        selected = None
                        stats["port"] = None
                    desired_filter = flow_filter(selected) if selected is not None else broad_filter
                stats["candidate_flows"] = [{"interface": key[0], "src": key[1], "sport": key[2], "dst": key[3], "dport": key[4], "signature_hits": len(value["hits"])} for key, value in detector.candidates.items()]
                stats["selected_flow"] = detector.selected
                stats["tcp_pending_bytes"] = sum(len(data) for flow in flows.values() for data in flow.waiting.values())
                stats.update(driver_snapshot())
                emit("capture_stats", dict(stats))
            # Narrow to (or widen from) the detected flow outside the lock: retiring the old sniffers joins
            # their callback threads, which take callback_lock, so holding it here would deadlock.
            if desired_filter is not None and desired_filter != capture_state["filter"]:
                switch_filter(desired_filter)
                with callback_lock:
                    emit("capture_stats", dict(stats))
    except Exception as exc:
        emit("error", str(exc))
    finally:
        # Stop every sniffer before waiting so shutdown time does not multiply
        # with the number of installed network adapters.
        for _, sniffer in sniffers:
            if getattr(sniffer, "running", False):
                try:
                    sniffer.stop(join=False)
                except Exception:
                    pass
        deadline = time.monotonic() + 2
        for _, sniffer in sniffers:
            thread = getattr(sniffer, "thread", None)
            if thread is not None:
                thread.join(timeout=max(0, deadline - time.monotonic()))
            if getattr(sniffer, "running", False):
                try:
                    sniffer.stop(join=False)
                except Exception:
                    pass
        for name, capture_socket, monitor, sniffer in resources:
            thread = getattr(sniffer, "thread", None)
            if thread is not None and thread.is_alive():
                stats["warnings"].append(f"{name}: capture thread did not stop before the final statistics snapshot")
                monitor.partial = True
                # Do not close a handle or call pcap_stats while recv is still using it.
                def close_after_exit(thread=thread, capture_socket=capture_socket):
                    thread.join()
                    try:
                        capture_socket.close()
                    except Exception:
                        pass
                threading.Thread(target=close_after_exit, daemon=True, name="capture-cleanup").start()
            else:
                monitor.sample(force=True)
                try:
                    capture_socket.close()
                except Exception as exc:
                    stats["warnings"].append(f"{name}: capture handle cleanup failed: {exc}")
        stats.update(driver_snapshot())
        stats["state"] = "stopped"
        with callback_lock:
            stats["tcp_pending_bytes"] = sum(len(data) for flow in flows.values() for data in flow.waiting.values())
        emit("capture_stats", dict(stats))
        emit("capture_stopped")
