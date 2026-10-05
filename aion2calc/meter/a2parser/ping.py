"""Protocol-aware latency tracker for legacy and current AION 2 clients."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import time

DOTNET_EPOCH_MS = 62_135_596_800_000
UNREAL_CLOCK_OFFSET_MS = 16_777_216 * 1_000
MAX_PING_MS = 9_999
OFFSET_TOLERANCE_MS = 15
PERF_AGREEMENT_MS = 25
PERF_MISSES_TO_DISTRUST = 2
MAX_HISTORY = 10_000
RELAYED_PING_REQUESTS = (b"\x05\x23\x0c\x0f", b"\x05\x23\x0d\x10")

PerfClock = Callable[[], tuple[int, int]]


def system_perf_clock() -> tuple[int, int]:
    """Read a monotonic counter and wall clock close together for live capture."""
    counter_ms = time.perf_counter_ns() // 1_000_000
    wall_ms = time.time_ns() // 1_000_000
    return counter_ms, wall_ms


def _varint(data: bytes, at: int) -> tuple[int, int] | None:
    value = 0
    for width in range(1, 6):
        if at + width > len(data):
            return None
        byte = data[at + width - 1]
        value |= (byte & 0x7F) << (7 * (width - 1))
        if byte & 0x80 == 0:
            return (value, width) if value <= 0x7FFF_FFFF else None
    return None


def has_ping_request(data: bytes) -> bool:
    """Accept clean encrypted client framing or an observed relay wrapper."""
    if any(marker in data for marker in RELAYED_PING_REQUESTS):
        return True
    offset = 0
    found = False
    while offset < len(data):
        decoded = _varint(data, offset)
        if decoded is None:
            return False
        value, prefix_bytes = decoded
        # The request stream uses a one-byte length prefix; the other three
        # bytes are protocol overhead and the remainder is encrypted payload.
        size = value - 3
        if size <= 0 or offset + size > len(data):
            return False
        found |= size in (12, 13)
        offset += size
    return found


def _valid_rtt(value: int) -> bool:
    return 1 <= value <= MAX_PING_MS


class PingTracker:
    """Pair request/response clocks with .NET, Unreal/QPC, and learned offsets."""

    def __init__(self, perf_clock: PerfClock | None = None) -> None:
        self.requests: deque[int] = deque()
        self.history: deque[tuple[int, int]] = deque(maxlen=MAX_HISTORY)
        self.current_ms: int | None = None
        self.perf_clock = perf_clock
        self.clock_offset: int | None = None
        self.previous_offsets: list[int] = []
        self.perf_misses = 0
        self.perf_distrusted = False

    @staticmethod
    def _near(value: int, values: list[int]) -> int | None:
        return next((candidate for candidate in values
                     if abs(candidate - value) <= OFFSET_TOLERANCE_MS), None)

    def _paired_rtt(self, client_sent: int, arrival_ms: int) -> int | None:
        offsets = [sent - client_sent for sent in self.requests
                   if 0 <= arrival_ms - sent <= MAX_PING_MS]
        picked: int | None
        if not offsets:
            picked = None
        elif len(offsets) == 1:
            picked = offsets[0]
        else:
            picked = self._near(self.clock_offset, offsets) if self.clock_offset is not None else None
            if picked is None:
                picked = next((candidate for candidate in offsets
                               if self._near(candidate, self.previous_offsets) is not None), None)

        if picked is not None:
            if (self.clock_offset is not None
                    and abs(picked - self.clock_offset) <= OFFSET_TOLERANCE_MS):
                self.clock_offset = picked
            elif self._near(picked, self.previous_offsets) is not None:
                self.clock_offset = picked
            elif self.clock_offset is not None:
                # A wall-clock step invalidates the learned cross-clock offset.
                self.clock_offset = None
        self.previous_offsets = offsets
        if picked is None:
            return None
        rtt = arrival_ms - (client_sent + picked)
        return rtt if _valid_rtt(rtt) else None

    def _perf_rtt(self, client_sent: int, arrival_ms: int) -> int | None:
        if self.perf_clock is None or self.perf_distrusted:
            return None
        counter_ms, wall_ms = self.perf_clock()
        sent_counter_ms = client_sent - UNREAL_CLOCK_OFFSET_MS
        if not 0 <= sent_counter_ms <= counter_ms:
            return None
        rtt = arrival_ms - (sent_counter_ms + (wall_ms - counter_ms))
        return rtt if _valid_rtt(rtt) else None

    def observe(self, data: bytes, *, client_to_server: bool, captured_at_ms: int) -> int | None:
        if client_to_server:
            if has_ping_request(data):
                self.requests.append(captured_at_ms)
            while self.requests and captured_at_ms - self.requests[0] > MAX_PING_MS:
                self.requests.popleft()
            return None

        pos = 0
        while pos + 12 <= len(data):
            if data[pos:pos + 4] != b"\x03\x36\x00\x00":
                pos += 1
                continue
            client_sent = int.from_bytes(data[pos + 4:pos + 12], "little", signed=True)
            perf_rtt = self._perf_rtt(client_sent, captured_at_ms)
            paired_rtt = self._paired_rtt(client_sent, captured_at_ms)
            if perf_rtt is not None and paired_rtt is not None:
                if abs(perf_rtt - paired_rtt) > PERF_AGREEMENT_MS:
                    perf_rtt = None
                    self.perf_misses += 1
                    if self.perf_misses >= PERF_MISSES_TO_DISTRUST:
                        self.perf_distrusted = True
                else:
                    self.perf_misses = 0

            wall_rtt = captured_at_ms - (client_sent - DOTNET_EPOCH_MS)
            rtt = (perf_rtt if perf_rtt is not None else paired_rtt)
            if rtt is None and _valid_rtt(wall_rtt):
                rtt = wall_rtt
            if rtt is None and self.clock_offset is not None:
                candidate = captured_at_ms - (client_sent + self.clock_offset)
                if _valid_rtt(candidate):
                    rtt = candidate
            if rtt is not None:
                self.current_ms = int(rtt)
                self.history.append((captured_at_ms, self.current_ms))
                return self.current_ms
            pos += 12
        return None

    def reset(self) -> None:
        self.current_ms = None
        self.history.clear()
        self.requests.clear()
        self.clock_offset = None
        self.previous_offsets.clear()
        self.perf_misses = 0
        self.perf_distrusted = False
