"""Read cumulative libpcap counters on the capture thread, never during a concurrent read."""
import sys
import threading
import time

FIELDS = ("pcap_received", "pcap_dropped", "pcap_if_dropped", "pcap_stats_reads")
FLAGS = ("pcap_stats_sampled", "pcap_stats_partial")
NOTE = ("Driver counters cover the capture handle, not just decoded game traffic. "
        "Their meaning and availability vary by platform; a reported zero does not prove loss-free capture. "
        "They must not be added to TCP discard counts to estimate unique lost game packets.")
#: Kernel capture-buffer size to request (Windows/Npcap). AION 2 raids burst far past the old
#: 8 MiB buffer — busy fights were dropping a quarter to a half of their packets — so request a
#: much larger buffer and step down until the backend accepts one. Per capture handle; kept modest
#: enough to stay reasonable across several interfaces in auto mode.
CAPTURE_BUFFER_BYTES = 64 * 1024 * 1024
_BUFFER_CANDIDATES = (CAPTURE_BUFFER_BYTES, 32 * 1024 * 1024, 16 * 1024 * 1024, 8 * 1024 * 1024)


class PcapStats:
    def __init__(self, capture_socket):
        self.socket = capture_socket
        self.lock = threading.Lock()
        self.next_sample = 0.0
        self.values = {key: 0 for key in FIELDS}
        self.error = None
        self.partial = False
        self.buffer_bytes = None
        self.buffer_warning = None
        # Scapy has already activated the handle. Npcap's Windows extension
        # supports resizing here; the portable pre-activation API does not.
        # Do this only before sniffing: resizing discards the old buffer.
        if sys.platform == "win32":
            try:
                from scapy.libs.winpcapy import pcap_setbuff
                handle = getattr(getattr(capture_socket, "pcap_fd", None), "pcap", None)
                if not handle:
                    raise OSError("No capture handle to resize")
                # Request the largest buffer the backend will accept, stepping down from
                # CAPTURE_BUFFER_BYTES. Must run before sniffing; resizing discards the old buffer.
                for want in _BUFFER_CANDIDATES:
                    if pcap_setbuff(handle, want) == 0:
                        self.buffer_bytes = want
                        break
                else:
                    raise OSError("Capture buffer request was not accepted")
            except Exception:
                self.buffer_warning = "Could not enlarge the Windows capture buffer; using the backend default."

    def sample(self, force=False):
        """Call before sniffing, in its packet callback, or after its thread has exited."""
        now = time.monotonic()
        if not force and now < self.next_sample:
            return
        self.next_sample = now + 1
        try:
            if getattr(self.socket, "closed", False):
                raise OSError("Capture handle closed before sampling")
            handle = getattr(getattr(self.socket, "pcap_fd", None), "pcap", None)
            if not handle:
                raise OSError("This capture backend does not expose libpcap statistics")
            from ctypes import byref
            from scapy.libs.winpcapy import pcap_stat, pcap_stats
            counters = pcap_stat()
            if pcap_stats(handle, byref(counters)) != 0:
                raise OSError("The capture backend could not report packet statistics")
            with self.lock:
                # Keep observed loss even if a backend resets or wraps its counters.
                for key, value in zip(FIELDS[:3], (counters.ps_recv, counters.ps_drop, counters.ps_ifdrop)):
                    self.values[key] = max(self.values[key], int(value))
                self.values["pcap_stats_reads"] += 1
                self.error = None
        except Exception:  # Optional backend statistics must never interrupt capture.
            with self.lock:
                self.partial = True
                self.error = "Packet statistics are unavailable for this capture handle/backend."

    def snapshot(self):
        with self.lock:
            return {**self.values, "pcap_stats_sampled": self.values["pcap_stats_reads"] > 0,
                    "pcap_stats_partial": self.partial, "reason": self.error,
                    "capture_buffer_bytes": self.buffer_bytes, "capture_buffer_warning": self.buffer_warning}
