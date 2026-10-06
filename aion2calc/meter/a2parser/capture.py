"""Optional Scapy/Npcap live TCP payload capture adapter."""

from __future__ import annotations

import queue
import threading
import time

MAX_REORDERED_SEGMENTS = 256
MAX_REORDER_DISTANCE = 1_048_576


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

    def feed(self, sequence: int, payload: bytes, *, syn: bool = False) -> bytes:
        self.last_seen = time.monotonic()
        sequence &= 0xFFFF_FFFF
        if syn:
            sequence = (sequence + 1) & 0xFFFF_FFFF
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
            if delta > MAX_REORDER_DISTANCE or (sequence not in self.waiting
                                                 and len(self.waiting) >= MAX_REORDERED_SEGMENTS):
                return b""
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
        return bytes(output)


class CombatFlowDetector:
    """Identify a game flow with the upstream 12-packet/3-second marker gate."""
    signatures = (b"\x0e\x00\x36", b"\x06\x00\x36")

    def __init__(self):
        self.candidates: dict[tuple, dict] = {}
        self.selected: tuple | None = None
        self.first_candidate: float | None = None

    def feed(self, key: tuple, payload: bytes, sequence: int, syn: bool, now: float) -> list[tuple]:
        if self.selected is not None:
            return [(key, sequence, payload, syn)] if key == self.selected else []
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
        packets = candidate["packets"]
        self.candidates.clear()
        return packets


def capture_packets(stop_event: threading.Event, output_queue: queue.Queue,
                    interface: str | None = None, server_port: int = 50349,
                    generation: int | None = None, host: str | None = None,
                    auto_port: bool = False) -> None:
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
        interfaces = [interface] if interface else available_interfaces()
        if not interfaces:
            raise RuntimeError("No capture adapters are available. Install capture support and restart the app.")
    except Exception as exc:
        emit("error", f"Cannot initialize packet capture: {exc}")
        return
    flows: dict[tuple, TCPReassembler] = {}
    detector = CombatFlowDetector()
    callback_lock = threading.Lock()
    stats = {"packets": 0, "payload_packets": 0, "bytes": 0, "forwarded": 0,
             "auto_port": auto_port, "port": None if auto_port else server_port,
             "interface": interface or "Auto", "interfaces": interfaces, "warnings": [],
             "state": "starting"}
    last_prune = time.monotonic()

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
        payload = bytes(tcp.payload)
        syn = bool(int(tcp.flags) & 0x02)
        with callback_lock:
            if auto_port and detector.selected == key and (int(tcp.flags) & (0x01 | 0x04)):
                detector.selected = None
                detector.first_candidate = None
                detector.candidates.clear()
                stats["port"] = None
            stats["packets"] += 1
            stats["payload_packets"] += bool(payload)
            stats["bytes"] += len(payload)
            if auto_port:
                chunks = detector.feed(key, payload, int(tcp.seq), syn, time.monotonic())
                if detector.selected:
                    stats["port"] = detector.selected[2]
                    stats["interface"] = detector.selected[0]
            else:
                chunks = [(key, int(tcp.seq), payload, syn)]
            for stream_key, sequence, chunk, has_syn in chunks:
                # Shared sequence state suppresses duplicate fixed-port packets
                # seen on several adapters (e.g. VPN plus physical interface).
                flow_key = stream_key if auto_port else stream_key[1:]
                flow = flows.setdefault(flow_key, TCPReassembler())
                reassembled = flow.feed(sequence, chunk, syn=has_syn)
                if reassembled:
                    _, src, sport, dst, dport = stream_key
                    emit("packet", f"{src}:{sport}->{dst}:{dport}", reassembled, time.time_ns() // 1_000_000)
                    stats["forwarded"] += 1
            if int(tcp.flags) & (0x01 | 0x04):
                flows.pop(key if auto_port else key[1:], None)

    sniffers = []
    try:
        bpf_filter = "tcp" if auto_port else f"tcp port {server_port}"
        if host:
            bpf_filter += f" and host {host}"
        for name in interfaces:
            sniffer = AsyncSniffer(iface=name, filter=bpf_filter, prn=on_packet, store=False)
            try:
                sniffer.start()
                sniffers.append((name, sniffer))
            except Exception as exc:
                stats["warnings"].append(f"{name}: {exc}")
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
            with callback_lock:
                if now - last_prune >= 30:
                    for stale_key, flow in tuple(flows.items()):
                        if now - flow.last_seen >= 120:
                            flows.pop(stale_key, None)
                    last_prune = now
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
        stats["state"] = "stopped"
        emit("capture_stats", dict(stats))
        emit("capture_stopped")
