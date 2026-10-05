"""Live damage meter: a capture source feeds a pluggable decoder, whose combat events a streaming
:class:`~aion2calc.meter.meter.Meter` aggregates into a live DPS table.

The decoder for the live game's network protocol is intentionally NOT shipped: it cannot be derived
without live captures, and this project will not circumvent the game's encryption. Point
``--decoder your_module`` at your own decoder for live play, or use ``--replay`` to drive the meter
from a recorded session of decoded events (JSON lines) for development and demos.
"""
from .decoder import Decoder, JsonLinesDecoder, load_decoder, register_decoder
from .events import CombatEvent
from .meter import Meter
from .sources import capture_source, live_frames, replay_source

__all__ = ["CombatEvent", "Meter", "Decoder", "JsonLinesDecoder", "load_decoder", "register_decoder",
           "replay_source", "capture_source", "live_frames"]
