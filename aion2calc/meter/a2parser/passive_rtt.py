"""Bounded passive TCP ACK timing; retransmitted observations are ambiguous."""
from __future__ import annotations

class PassiveRTT:
    def __init__(self):
        self.flows = {}
        self.last_emit = 0.0

    def observe(self, connection, sequence, ack, flags, length, outgoing, now):
        if flags & (0x02 | 0x01 | 0x04):
            self.flows.pop(connection, None)
            return None
        pending = self.flows.get(connection, {})
        pending = {end: row for end, row in pending.items() if now-row[0] <= 60}
        if outgoing and length:
            end = (sequence+length) & 0xffffffff
            # Duplicate adapters or retransmissions make the original send ambiguous.
            pending[end] = (pending[end][0], True) if end in pending else (now, False)
            if len(pending) > 64:
                pending.pop(next(iter(pending)))
            if connection not in self.flows and len(self.flows) >= 128:
                self.flows.pop(next(iter(self.flows)))
            self.flows[connection] = pending
            return None
        if outgoing or not flags & 0x10:
            return None
        matched = [row for end, row in pending.items() if ((ack-end)&0xffffffff) < 0x80000000]
        self.flows[connection] = {end: row for end, row in pending.items() if ((ack-end)&0xffffffff) >= 0x80000000}
        if not matched or any(ambiguous for _, ambiguous in matched) or now-self.last_emit < 1:
            return None
        elapsed = (now-max(sent for sent, _ in matched))*1000
        if not 0 <= elapsed <= 60000:
            return None
        self.last_emit = now
        return round(elapsed, 2)
