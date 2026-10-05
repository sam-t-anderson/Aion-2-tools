"""The decoder plugin interface and loader.

A decoder turns raw captured frames (bytes) into :class:`CombatEvent`s. The decoder for the live
game's network protocol is intentionally NOT shipped: it cannot be derived without live captures,
and this project will not circumvent the game's encryption. Supply your own with ``--decoder
your_module`` (or ``your_module:Factory``); it only has to implement :class:`Decoder`.

A tiny ``jsonlines`` decoder is bundled for development: it treats each frame as a UTF-8 JSON object
(or array) of already-decoded events, so a tool that emits decoded JSON — or a recorded frames file —
can drive the meter without any protocol work.
"""
from __future__ import annotations

import importlib
from typing import Protocol, runtime_checkable

from .events import CombatEvent


@runtime_checkable
class Decoder(Protocol):
    def feed(self, data: bytes) -> list[CombatEvent]:
        """Return the combat events decoded from one raw frame (may be empty)."""
        ...


_REGISTRY: dict = {}


def register_decoder(name: str, factory) -> None:
    _REGISTRY[name] = factory


def load_decoder(spec: str):
    """Resolve a decoder from a registered name, ``module:attr``, or a module exposing
    ``make_decoder`` / ``Decoder``."""
    if spec in _REGISTRY:
        return _REGISTRY[spec]()
    if ":" in spec:
        mod_name, attr = spec.split(":", 1)
        obj = getattr(importlib.import_module(mod_name), attr)
        return obj() if isinstance(obj, type) else obj
    mod = importlib.import_module(spec)
    for attr in ("make_decoder", "Decoder", "decoder"):
        if hasattr(mod, attr):
            obj = getattr(mod, attr)
            return obj() if isinstance(obj, type) or (attr == "make_decoder" and callable(obj)) else obj
    raise ValueError(f"module {spec!r} has no decoder (expose make_decoder, Decoder or decoder, or use module:attr)")


class JsonLinesDecoder:
    """Development decoder: each frame is a UTF-8 JSON object/array of CombatEvent fields. Does not
    decode the game protocol."""

    def feed(self, data: bytes) -> list[CombatEvent]:
        import json
        try:
            text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
            obj = json.loads(text)
        except Exception:
            return []
        if isinstance(obj, dict):
            return [CombatEvent.from_dict(obj)]
        if isinstance(obj, list):
            return [CombatEvent.from_dict(x) for x in obj if isinstance(x, dict)]
        return []


register_decoder("jsonlines", JsonLinesDecoder)
