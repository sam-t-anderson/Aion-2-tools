"""Optional Scapy/Npcap live TCP payload capture adapter."""

from __future__ import annotations

import queue
import threading
import time

MAX_REORDERED_SEGMENTS = 256
MAX_REORDER_DISTANCE = 1_048_576


def available_interfaces() -> list[str]:
    """Return capture-device identifiers exposed by Scapy/Npcap."""
    try:
        from scapy.all import get_if_list
        return sorted({str(interface) for interface in get_if_list() if str(interface).strip()}, key=str.casefold)
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


def capture_packets(stop_event: threading.Event, output_queue: queue.Queue,
                    interface: str | None = None, server_port: int = 50349,
                    generation: int | None = None, host: str | None = None) -> None:
    """Capture the selected game TCP port and stream reassembled payloads to UI."""
    def emit(kind: str, *data) -> None:
        if generation is None:
            output_queue.put((kind, *data))
        else:
            output_queue.put((kind, generation, *data))

    if not 1 <= int(server_port) <= 65_535:
        emit("error", "The server port must be between 1 and 65535.")
        return
    server_port = int(server_port)
    host = (host or "").strip() or None
    try:
        from scapy.all import AsyncSniffer, IP, IPv6, TCP, Raw
    except ImportError as exc:
        emit("error", f"Scapy is not installed: {exc}")
        return
    flows: dict[tuple[str, int, str, int], TCPReassembler] = {}
    last_prune = time.monotonic()

    def prune_idle_flows() -> None:
        nonlocal last_prune
        now = time.monotonic()
        if now - last_prune < 30:
            return
        for stale_key, stale_flow in tuple(flows.items()):
            if now - stale_flow.last_seen >= 120:
                flows.pop(stale_key, None)
        last_prune = now

    def on_packet(packet) -> None:
        if TCP not in packet:
            return
        ip = packet[IP] if IP in packet else packet[IPv6] if IPv6 in packet else None
        if ip is None:
            return
        tcp = packet[TCP]
        if tcp.sport != server_port and tcp.dport != server_port:
            return
        has_payload = Raw in packet
        syn = bool(int(tcp.flags) & 0x02)
        if not has_payload and not syn:
            return
        source, destination = ip.src, ip.dst
        key = (source, int(tcp.sport), destination, int(tcp.dport))
        flow = flows.setdefault(key, TCPReassembler())
        payload = flow.feed(int(tcp.seq), bytes(packet[Raw].load) if has_payload else b"", syn=syn)
        if payload:
            stream = f"{source}:{tcp.sport}->{destination}:{tcp.dport}"
            emit("packet", stream, payload, time.time_ns() // 1_000_000)
        flags = int(tcp.flags)
        if flags & (0x01 | 0x04):
            flows.pop(key, None)

    sniffer = None
    try:
        bpf_filter = f"tcp port {server_port}"
        if host:
            bpf_filter += f" and host {host}"
        sniffer = AsyncSniffer(iface=interface or None, filter=bpf_filter, prn=on_packet, store=False)
        sniffer.start()
        emit("capture_started")
        while not stop_event.wait(0.25):
            if sniffer.thread is not None and not sniffer.thread.is_alive():
                raise RuntimeError("packet capture stopped unexpectedly; verify Npcap and the selected interface")
            prune_idle_flows()
    except Exception as exc:
        emit("error", str(exc))
    finally:
        # AsyncSniffer marks itself running in its worker, so wait through the short start race
        # before stopping it. This makes an immediate Stop click deterministic.
        thread = getattr(sniffer, "thread", None) if sniffer is not None else None
        while sniffer is not None and thread is not None and thread.is_alive() and not getattr(sniffer, "running", False):
            time.sleep(0.01)
        if sniffer is not None and getattr(sniffer, "running", False):
            try:
                sniffer.stop(join=True)
            except Exception:                                                # capture backends can already be stopped
                pass
        emit("capture_stopped")
