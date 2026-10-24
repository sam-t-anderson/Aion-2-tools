"""The capture's raw-frame parser reads what scapy's dissection read, in a fraction of the time."""
import socket
import struct
import threading
import time

import pytest

from aion2calc.meter.a2parser import capture as C


def _ipv4(payload=b"", *, src="10.0.0.1", dst="10.0.0.2", sport=50349, dport=61000, flags=0x18, seq=1, ack=2,
          options=b"", pad=b"", frag=0, proto=6, ihl_options=b""):
    tcp_header = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, ((20 + len(options)) // 4) << 4, flags & 0xFF, 65535, 0, 0) + options
    total = 20 + len(ihl_options) + len(tcp_header) + len(payload)
    ip = struct.pack("!BBHHHBBH4s4s", 0x40 | (5 + len(ihl_options) // 4), 0, total, 1, frag, 64, proto, 0,
                     socket.inet_aton(src), socket.inet_aton(dst)) + ihl_options
    return ip + tcp_header + payload + pad


def _ether(inner, ethertype=0x0800, vlan=None):
    tag = struct.pack("!HH", 0x8100, vlan) if vlan is not None else b""
    return b"\x00\x11\x22\x33\x44\x55" + b"\x66\x77\x88\x99\xaa\xbb" + tag + struct.pack("!H", ethertype) + inner


def test_parses_an_ethernet_ipv4_tcp_frame_and_drops_the_padding():
    frame = _ether(_ipv4(b"hello", pad=b"\x00" * 7))
    assert C.parse_frame("Ether", frame) == ("10.0.0.1", "10.0.0.2", 50349, 61000, 0x18, 1, 2, b"hello")


def test_reads_vlan_tags_options_flags_and_sequence_numbers():
    frame = _ether(_ipv4(b"x" * 3, options=b"\x01\x01\x08\x0a" + b"\x00" * 8, flags=0x012, seq=0xFFFF_FFF0, ack=7,
                         ihl_options=b"\x00" * 4), vlan=100)
    src, dst, sport, dport, flags, seq, ack, payload = C.parse_frame("Ether", frame)
    assert (flags, seq, ack, payload) == (0x012, 0xFFFF_FFF0, 7, b"xxx")
    assert C.parse_frame("Ether", _ether(_ipv4(), vlan=1)[:16]) is None          # a tag cut short: scapy's


def test_other_protocols_and_truncated_segments_hold_no_segment():
    assert C.parse_frame("Ether", _ether(_ipv4(proto=17))) is C.NOT_TCP            # UDP
    assert C.parse_frame("Ether", _ether(b"\x00" * 28, ethertype=0x0806)) is C.NOT_TCP   # ARP
    assert C.parse_frame("Ether", _ether(_ipv4())[:40]) is C.NOT_TCP               # a TCP header cut short
    assert C.parse_frame("Ether", _ether(_ipv4(frag=0x2000))) is None             # a fragment: scapy's
    assert C.parse_frame("Ether", b"\x00" * 10) is None
    assert C.parse_frame("SomeOtherLink", _ether(_ipv4())) is None


def test_reads_loopback_cooked_and_raw_ip_frames():
    inner = _ipv4(b"ab")
    assert C.parse_frame("Loopback", struct.pack("<I", 2) + inner)[-1] == b"ab"
    assert C.parse_frame("IP", inner)[-1] == b"ab"
    sll = struct.pack("!HHH", 0, 1, 6) + b"\x00" * 8 + struct.pack("!H", 0x0800) + inner
    assert C.parse_frame("CookedLinux", sll)[:4] == ("10.0.0.1", "10.0.0.2", 50349, 61000)
    sll2 = struct.pack("!HHIHBB", 0x0800, 0, 2, 1, 0, 6) + b"\x00" * 8 + inner
    assert C.parse_frame("CookedLinuxV2", sll2)[-1] == b"ab"


def test_reads_an_ipv6_segment_and_leaves_extension_headers_to_scapy():
    tcp = struct.pack("!HHIIBBHHH", 40000, 50349, 9, 8, 5 << 4, 0x10, 1000, 0, 0) + b"payload"
    def v6(next_header, body):
        return struct.pack("!IHBB16s16s", 6 << 28, len(body), next_header, 64,
                           socket.inet_pton(socket.AF_INET6, "2001:db8::1"), socket.inet_pton(socket.AF_INET6, "2001:db8::2")) + body
    frame = _ether(v6(6, tcp) + b"\x00" * 4, ethertype=0x86DD)
    assert C.parse_frame("Ether", frame) == ("2001:db8::1", "2001:db8::2", 40000, 50349, 0x10, 9, 8, b"payload")
    assert C.parse_frame("Ether", _ether(v6(60, b"\x06\x00" + b"\x00" * 6 + tcp), ethertype=0x86DD)) is None
    assert C.parse_frame("Ether", _ether(v6(17, b"\x00" * 8), ethertype=0x86DD)) is C.NOT_TCP


def test_parser_agrees_with_scapy_dissection():
    scapy = pytest.importorskip("scapy.all")
    Ether, IP, IPv6, TCP, Raw, Dot1Q, Padding = (getattr(scapy, n) for n in ("Ether", "IP", "IPv6", "TCP", "Raw", "Dot1Q", "Padding"))
    packets = [
        Ether() / IP(src="192.168.1.10", dst="10.20.30.40") / TCP(sport=50349, dport=52000, flags="PA", seq=12345, ack=678) / Raw(b"\x0e\x00\x36abc"),
        Ether() / IP(src="1.2.3.4", dst="5.6.7.8") / TCP(sport=443, dport=5000, flags="S", seq=1, options=[("MSS", 1460), ("NOP", None), ("WScale", 8)]),
        Ether() / Dot1Q(vlan=7) / IP(src="1.2.3.4", dst="5.6.7.8") / TCP(sport=1, dport=2, flags="FA") / Raw(b"z") / Padding(b"\x00" * 10),
        Ether() / IPv6(src="fe80::1", dst="fe80::2") / TCP(sport=50349, dport=60000, flags="A", seq=5, ack=6) / Raw(b"ipv6 payload"),
        Ether() / IP(src="9.9.9.9", dst="8.8.8.8") / TCP(sport=10, dport=20, flags="SEC"),   # ECN flags above the low byte's usual ones
        Ether() / IP(src="9.9.9.9", dst="8.8.8.8", flags="MF") / TCP(sport=10, dport=20),     # a fragment: handed to scapy
    ]
    for packet in packets:
        raw = bytes(packet)
        parsed = C.parse_frame("Ether", raw)
        if parsed is None:
            parsed = C.segment_of(Ether(raw))
        assert parsed == C.segment_of(Ether(raw)), packet.summary()


class _FakeSocket:
    """A capture handle: ``select`` says whether frames wait, ``recv_raw`` hands one over."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False

    def select(self, sockets, remain=None):
        return sockets if self.frames else []

    def recv_raw(self, x=65535):
        if not self.frames:
            return None, None, None
        item = self.frames.pop(0)
        if isinstance(item, Exception):
            raise item
        return "Ether", item, time.time()


def test_adapter_sniffer_hands_frames_over_then_stops_and_reports_a_failure():
    seen = []
    sniffer = C.AdapterSniffer("eth0", _FakeSocket([b"one", b"two"]), lambda link, data: seen.append((link, data)))
    sniffer.start()
    deadline = time.time() + 2
    while len(seen) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert seen == [("Ether", b"one"), ("Ether", b"two")] and sniffer.running and sniffer.exception is None
    sniffer.stop(join=True)
    assert not sniffer.running and not sniffer.thread.is_alive()
    failing = C.AdapterSniffer("eth1", _FakeSocket([b"x", OSError("adapter gone")]), lambda link, data: None)
    failing.start()
    failing.thread.join(2)
    assert not failing.running and isinstance(failing.exception, OSError)


def test_capture_hands_parsed_segments_to_the_reassembler(monkeypatch):
    """The whole capture over fake handles: frames parsed from bytes reach the queue as game payloads."""
    pytest.importorskip("scapy.all")
    import queue
    from scapy.all import Ether, IP, TCP, Raw
    frames = [bytes(Ether() / IP(src="10.0.0.5", dst="10.0.0.9") / TCP(sport=50349, dport=61000, flags="PA", seq=100 + i * 4, ack=1) / Raw(b"abcd"))
              for i in range(3)]
    handles = {}

    class _Handle(_FakeSocket):
        def close(self):
            self.closed = True

    class _Iface:
        def l2listen(self):
            def make(iface, filter, promisc):
                handles[iface] = _Handle(frames)
                return handles[iface]
            return make

    monkeypatch.setattr(C, "available_interfaces", lambda: ["fake0"])
    import scapy.interfaces
    monkeypatch.setattr(scapy.interfaces, "resolve_iface", lambda name: _Iface())
    from aion2calc.meter.a2parser import capture_stats
    monkeypatch.setattr(capture_stats.PcapStats, "__init__", lambda self, sock: setattr(self, "buffer_warning", None) or setattr(self, "partial", False))
    monkeypatch.setattr(capture_stats.PcapStats, "sample", lambda self, force=False: None)
    monkeypatch.setattr(capture_stats.PcapStats, "snapshot", lambda self: {k: 0 for k in capture_stats.FIELDS} | {"pcap_stats_sampled": False, "pcap_stats_partial": False})
    stop, out = threading.Event(), queue.Queue()
    worker = threading.Thread(target=C.capture_packets, args=(stop, out), kwargs={"interface": "fake0", "server_port": 50349}, daemon=True)
    worker.start()
    payloads = []
    deadline = time.time() + 5
    while time.time() < deadline and len(payloads) < 3:
        try:
            item = out.get(timeout=0.2)
        except queue.Empty:
            continue
        if item[0] == "packet":
            payloads.append(item[2])
        elif item[0] == "error":
            raise AssertionError(item[1])
    stop.set()
    worker.join(5)
    assert payloads == [b"abcd"] * 3 and handles["fake0"].closed
