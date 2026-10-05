"""Live damage meter and the embedded A2Tools packet decoder.

The browser UI uses :mod:`aion2calc.meter.a2parser` for its default live
capture source.  The generic decoder and replay interfaces remain available
for recorded or custom event feeds.
"""
from .decoder import Decoder, JsonLinesDecoder, load_decoder, register_decoder
from .events import CombatEvent
from .meter import Meter
from .sources import capture_source, live_frames, replay_source

__all__ = ["CombatEvent", "Meter", "Decoder", "JsonLinesDecoder", "load_decoder", "register_decoder",
           "replay_source", "capture_source", "live_frames"]
