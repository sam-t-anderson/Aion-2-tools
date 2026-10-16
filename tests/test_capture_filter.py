"""The kernel capture filter narrows to the game connection on the live handle, and widens again.

A Fire Temple recording on 0.2.287 ran the whole session on the broad ``tcp`` filter in auto-port
mode: 12.0M of 14.2M packets were dropped by the capture buffer, taking zone-load identity and
spawn packets with them. Once the flow detector has located the game connection, each adapter's
filter now shrinks to that server host and port (plus TCP handshakes, so a replacement connection
is still seen) without reopening the handle, and widens again when the connection ends.
"""
from aion2calc.meter.a2parser import capture


SELECTED = ("Ethernet", "203.0.113.9", 50349, "192.168.1.20", 61234)   # a server->client key


def test_narrow_filter_keeps_the_game_connection_and_every_handshake():
    expr = capture.narrow_filter(SELECTED)
    assert "host 203.0.113.9 and port 50349" in expr
    assert "tcp-syn|tcp-fin|tcp-rst" in expr                 # a new connection's SYN still reaches the callback
    assert capture.narrow_filter(SELECTED, "tcp and host 203.0.113.9").startswith("(tcp and host 203.0.113.9 and host")


def test_kernel_filter_narrows_once_and_widens_when_the_connection_is_gone():
    applied = []
    k = capture.KernelFilter("tcp", apply=lambda sock, expr, iface: applied.append((iface, expr)) or True)
    assert k.narrow("Ethernet", "sock", SELECTED) is True
    assert k.narrowed("Ethernet") and k.expression("Ethernet") == capture.narrow_filter(SELECTED)
    assert k.narrow("Ethernet", "sock", SELECTED) is False       # same connection: nothing to reinstall
    assert k.widen("Ethernet", "sock") is True and not k.narrowed("Ethernet")
    assert k.widen("Ethernet", "sock") is False                  # already broad
    assert [iface for iface, _ in applied] == ["Ethernet", "Ethernet"] and applied[-1][1] == "tcp"
    assert k.expression("Wi-Fi") == "tcp"                        # an adapter never narrowed reads broad


def test_an_adapter_whose_backend_refuses_is_left_alone():
    k = capture.KernelFilter("tcp", apply=lambda sock, expr, iface: False)
    assert k.narrow("Ethernet", "sock", SELECTED) is False
    assert "Ethernet" in k.failed and not k.narrowed("Ethernet")
    assert k.narrow("Ethernet", "sock", SELECTED) is False       # never retried


def test_apply_kernel_filter_uses_the_pcap_wrapper_or_the_inner_socket():
    class _Wrapper:
        def __init__(self):
            self.filters = []
        def setfilter(self, expr):
            self.filters.append(expr)

    class _Sock:
        pass

    sock = _Sock(); sock.pcap_fd = _Wrapper()                  # scapy's libpcap/Npcap socket
    assert capture.apply_kernel_filter(sock, "tcp and port 1", "Ethernet") is True
    assert sock.pcap_fd.filters == ["tcp and port 1"]
    sock2 = _Sock(); sock2.ins = _Wrapper()                    # a wrapper reached through .ins
    assert capture.apply_kernel_filter(sock2, "tcp", None) is True and sock2.ins.filters == ["tcp"]

    class _Refusing:
        def setfilter(self, expr):
            raise OSError("not supported")
    sock3 = _Sock(); sock3.pcap_fd = _Refusing()
    assert capture.apply_kernel_filter(sock3, "tcp", None) is False   # never raises into the capture thread
