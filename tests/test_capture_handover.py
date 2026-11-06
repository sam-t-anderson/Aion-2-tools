"""The flow detector follows the game to a new connection from that connection's first packet.

Entering an instance moves the game to a new connection, usually on another server, and that connection
opens with the zone load: the zone change, the recording player's own record, the other players' records and
the instance id (6.8 s in, in the 19 October recording). Up to 0.2.384 the detector ignored every other
connection until the selected one was seen to close or had been idle five seconds, then waited for the marker
gate from the new connection's first marked packet; with the kernel filter narrowed to the old server, the idle
rule ran only when some other packet passed the filter. In three Krao Cave runs of 4-6 November the zone load
went by meanwhile: the recorder fought the first part of the instance as "Player #N" and the party's hits were
dropped. Now a connection to the game's server port is kept from its first packet and takes over once the old
connection closes or goes quiet.
"""
from aion2calc.meter.a2parser.capture import CombatFlowDetector

OLD = ("eth0", "203.0.113.9", 13328, "192.168.1.20", 50000)       # server->client keys
NEW = ("eth0", "198.51.100.4", 13328, "192.168.1.20", 50001)
OLD_UP = (OLD[0], OLD[3], OLD[4], OLD[1], OLD[2])                  # the old connection's client->server direction
MARK = b"\x0e\x00\x36" + b"\x00" * 11                              # carries a marker (the clock record)


def _selected_on_old():
    detector = CombatFlowDetector()
    for i in range(12):
        detector.feed(OLD, MARK, i * 14, False, i * 0.25)
    assert detector.selected == OLD
    return detector


def _opening(detector, start):
    """The new connection's SYN-ACK and its first, unmarked packet (where the zone load rides)."""
    assert detector.feed(NEW, b"", 999, True, start) == []
    assert detector.feed(NEW, b"zone-load", 1000, False, start + 0.05) == []


def test_a_new_connection_to_the_game_port_takes_over_with_its_first_packets():
    detector = _selected_on_old()
    detector.feed(OLD, MARK, 200, False, 10.0)                       # the old connection's last packet
    _opening(detector, 10.05)
    assert detector.feed(NEW, MARK, 1009, False, 11.5) == []
    assert detector.feed(NEW, MARK, 1023, False, 11.55) == []
    packets = detector.feed(NEW, MARK, 1037, False, 11.6)            # the third marker, the old quiet 1.6 s
    assert detector.selected == NEW and detector.handovers == 1
    assert [(p[1], p[2], p[3]) for p in packets] == [(999, b"", True), (1000, b"zone-load", False),
                                                    (1009, MARK, False), (1023, MARK, False), (1037, MARK, False)]
    assert detector.feed(NEW, b"next", 1051, False, 11.65) == [(NEW, 1051, b"next", False)]
    assert detector.feed(OLD, b"late", 214, False, 11.7) == []       # the abandoned connection is not decoded
    assert detector.is_connection(NEW) and not detector.is_connection(OLD)


def test_a_connection_still_in_use_is_not_left_for_another():
    detector = _selected_on_old()
    _opening(detector, 10.0)
    t = 10.0
    for k in range(200):                                             # both send markers for ten seconds
        t = 10.0 + k * 0.05
        assert detector.feed(OLD, MARK, 300 + 14 * k, False, t)
        assert detector.feed(NEW, MARK, 1009 + 14 * k, False, t + 0.01) == []
    assert detector.selected == OLD and detector.handovers == 0


def test_the_old_connection_closing_hands_over_at_once():
    detector = _selected_on_old()
    _opening(detector, 10.0)
    for k in range(3):
        detector.feed(OLD, MARK, 300 + 14 * k, False, 10.1 + k * 0.05)   # still sending: no handover yet
        detector.feed(NEW, MARK, 1009 + 14 * k, False, 10.12 + k * 0.05)
    assert detector.selected == OLD
    packets = detector.connection_closed(OLD_UP, 10.3)               # the client's FIN on the old connection
    assert detector.selected == NEW and [p[2] for p in packets][:2] == [b"", b"zone-load"]


def test_after_the_old_connection_ends_the_next_one_is_kept_from_its_first_packet():
    detector = _selected_on_old()
    assert detector.connection_closed(OLD, 10.0) == []              # closed before the next one opened
    assert detector.selected is None and detector.game_port == ("eth0", 13328)
    _opening(detector, 10.2)
    detector.feed(NEW, MARK, 1009, False, 11.7)
    detector.feed(NEW, MARK, 1023, False, 11.75)
    packets = detector.feed(NEW, MARK, 1037, False, 11.8)            # no 12-marker gate: the port is the game's
    assert detector.selected == NEW and [p[2] for p in packets][:2] == [b"", b"zone-load"]


def test_an_idle_old_connection_still_gives_way():
    detector = _selected_on_old()
    detector.feed(OLD, MARK, 200, False, 10.0)
    other = ("eth0", "198.51.100.77", 443, "192.168.1.20", 50100)
    detector.feed(other, b"\x17\x03\x03 data", 1, False, 15.5)       # any packet after five idle seconds
    assert detector.selected is None and detector.game_port == ("eth0", 13328)
    _opening(detector, 16.0)
    for k, t in enumerate((17.4, 17.45, 17.5)):
        packets = detector.feed(NEW, MARK, 1009 + 14 * k, False, t)
    assert detector.selected == NEW and packets[1][2] == b"zone-load"


def test_another_port_or_adapter_is_no_successor():
    detector = _selected_on_old()
    elsewhere = ("eth0", "198.51.100.4", 7777, "192.168.1.20", 50002)
    vpn = ("tun0", *NEW[1:])
    for k in range(5):
        assert detector.feed(elsewhere, MARK, k * 14, False, 3.0 + k * 0.05) == []
        assert detector.feed(vpn, MARK, k * 14, False, 3.01 + k * 0.05) == []
    assert not detector.successors and detector.selected == OLD


def test_a_successor_that_never_sends_the_game_markers_is_forgotten():
    detector = _selected_on_old()
    detector.feed(OLD, MARK, 200, False, 10.0)
    detector.feed(NEW, b"not the game", 1000, False, 10.1)
    assert NEW in detector.successors
    later = ("eth0", "198.51.100.5", 13328, "192.168.1.20", 50003)
    detector.feed(later, b"x", 1, False, 10.1 + CombatFlowDetector.SUCCESSOR_TTL_S + 1)
    assert NEW not in detector.successors and later in detector.successors


def test_a_successor_holds_a_bounded_backlog():
    detector = _selected_on_old()
    chunk = b"\x01" * 65_536
    for k in range(40):                                              # 2.5 MB while the old one is busy
        detector.feed(OLD, MARK, 300 + 14 * k, False, 10.0 + k * 0.02)
        detector.feed(NEW, chunk, 1000 + k * len(chunk), False, 10.01 + k * 0.02)
    entry = detector.successors[NEW]
    assert entry["bytes"] <= CombatFlowDetector.SUCCESSOR_BYTES and len(entry["packets"]) < 40


def test_a_closed_successor_is_forgotten_and_a_reset_forgets_the_port():
    detector = _selected_on_old()
    _opening(detector, 10.0)
    detector.connection_closed((NEW[0], NEW[3], NEW[4], NEW[1], NEW[2]), 10.2)
    assert NEW not in detector.successors and detector.selected == OLD
    detector.reset()
    assert detector.game_port is None and detector.selected is None
