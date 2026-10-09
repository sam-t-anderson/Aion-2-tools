"""AION 2 stream framing, transcribed from the upstream Rust implementation.

The packet length includes four bytes of protocol overhead in addition to its
payload. Bundles contain an LZ4 block with further framed packets.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum

MAX_PACKET_BYTES = 65_535
MAX_FRAGMENT_WAIT_BYTES = 16_384
MAX_DECOMPRESSED_BYTES = 1_000_000


class FrameKind(str, Enum):
    PACKET = "packet"
    BUNDLE = "bundle"


@dataclass(frozen=True, slots=True)
class Frame:
    kind: FrameKind
    start: int
    end: int
    payload_start: int

    def bytes(self, buffer: bytes) -> bytes:
        return buffer[self.start : self.end]

    def payload(self, buffer: bytes) -> bytes:
        return buffer[self.start + self.payload_start : self.end]


@dataclass(frozen=True, slots=True)
class Framing:
    frames: tuple[Frame, ...]
    consumed: int


@dataclass(frozen=True, slots=True)
class VarInt:
    value: int
    length: int


def read_varint(data: bytes, offset: int = 0) -> VarInt:
    """Read the protocol's unsigned 7-bit continuation varint."""
    if offset < 0 or offset >= len(data):
        return VarInt(-1, -1)
    value = 0
    for width in range(1, 6):
        at = offset + width - 1
        if at >= len(data):
            return VarInt(-1, -1)
        byte = data[at]
        value |= (byte & 0x7F) << (7 * (width - 1))
        if byte & 0x80 == 0:
            # Rust's source stores this as i32; reject values outside that range.
            if value > 0x7FFF_FFFF:
                return VarInt(-1, -1)
            return VarInt(value, width)
    return VarInt(-1, -1)


def frame_size(value: int, varint_bytes: int) -> int | None:
    size = value - 4 + varint_bytes
    return size if size >= varint_bytes and size > 0 else None


def length_value(body_len: int) -> int:
    return body_len + 4


def _tls_record_size(data: bytes) -> int | None:
    if (
        len(data) < 5
        or not 0x14 <= data[0] <= 0x17
        or data[1] != 0x03
        or not 0x01 <= data[2] <= 0x04
    ):
        return None
    size = int.from_bytes(data[3:5], "big")
    return 5 + size if 0 < size <= 16_384 + 256 else None


def _walk(data: bytes, *, inner: bool) -> Framing:
    frames: list[Frame] = []
    offset = 0
    while offset < len(data):
        if data[offset] == 0:
            offset += 1
            continue
        if not inner:
            tls_size = _tls_record_size(data[offset:])
            if tls_size is not None:
                if offset + tls_size > len(data):
                    break
                offset += tls_size
                continue

        length = read_varint(data, offset)
        if length.length <= 0 or length.value <= 0:
            if inner:
                break
            if offset + 5 > len(data):
                break
            offset += 1
            continue
        total = frame_size(length.value, length.length)
        if total is None:
            offset += 1
            continue
        if not inner and total > MAX_PACKET_BYTES:
            offset += 1
            continue
        end = offset + total
        if end > len(data):
            if inner or total <= MAX_FRAGMENT_WAIT_BYTES:
                break
            offset += 1
            continue
        payload_start = length.length
        bundle = (
            total > payload_start + 1
            and data[offset + payload_start : offset + payload_start + 2] == b"\xff\xff"
        )
        frames.append(
            Frame(FrameKind.BUNDLE if bundle else FrameKind.PACKET, offset, end, payload_start)
        )
        offset = end
    return Framing(tuple(frames), offset)


def walk(data: bytes) -> Framing:
    """Frame a TCP stream, resynchronizing across corrupt or partial starts."""
    return _walk(data, inner=False)


def walk_inner(data: bytes) -> Framing:
    """Frame decompressed bundle contents; stop at the first invalid frame."""
    return _walk(data, inner=True)


@dataclass
class BundleBatch:
    cache: dict[bytes, bytes | None] = field(default_factory=dict)
    expanded_bytes: int = 0
    rejected: int = 0


_BUNDLE_BATCH: ContextVar[BundleBatch | None] = ContextVar("bundle_batch", default=None)


@contextmanager
def bundle_batch():
    """Share bounded decompression across scanners without changing frame context."""
    batch = BundleBatch()
    token = _BUNDLE_BATCH.set(batch)
    try:
        yield batch
    finally:
        _BUNDLE_BATCH.reset(token)


def decompress_bundle(payload: bytes) -> bytes | None:
    """Decompress a bundle; retain valid siblings when a compressed block is corrupt."""
    batch = _BUNDLE_BATCH.get()
    if batch is not None and payload in batch.cache:
        return batch.cache[payload]
    result = None
    size = int.from_bytes(payload[2:6], "little") if len(payload) >= 7 else 0
    allowed = 0 < size <= MAX_DECOMPRESSED_BYTES
    if batch is not None:
        allowed = allowed and batch.expanded_bytes + size <= 4_000_000
    if allowed:
        if batch is not None:
            batch.expanded_bytes += size
        try:
            from lz4.block import decompress, LZ4BlockError
        except ImportError:
            pass
        else:
            try:
                expanded = decompress(payload[6:], uncompressed_size=size)
                if len(expanded) == size:
                    result = expanded
            except (ValueError, RuntimeError, LZ4BlockError):
                pass
    if batch is not None:
        batch.cache[payload] = result
        if result is None:
            batch.rejected += 1
    return result


def iter_packets(data: bytes, *, max_depth: int = 8):
    """Yield plain packet payloads, recursively expanding valid LZ4 bundles."""
    if max_depth < 0:
        return
    for frame in walk(data).frames:
        if frame.kind is FrameKind.PACKET:
            yield frame.payload(data)
            continue
        expanded = decompress_bundle(frame.payload(data))
        if expanded is not None:
            yield from _iter_inner_packets(expanded, max_depth - 1)


def _iter_inner_packets(data: bytes, depth: int):
    if depth < 0:
        return
    for frame in walk_inner(data).frames:
        if frame.kind is FrameKind.PACKET:
            yield frame.payload(data)
        else:
            expanded = decompress_bundle(frame.payload(data))
            if expanded is not None:
                yield from _iter_inner_packets(expanded, depth - 1)
