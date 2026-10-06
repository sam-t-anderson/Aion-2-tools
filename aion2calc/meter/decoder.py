"""The decoder plugin interface and loader.

A decoder turns captured TCP payloads into :class:`CombatEvent`s. Live Capture
uses the bundled A2Tools engine; custom decoders can be imported from a Python
file or selected with ``--decoder your_module`` / ``your_module:Factory``.

A tiny ``jsonlines`` decoder is bundled for development: it treats each frame as a UTF-8 JSON object
(or array) of already-decoded events, so a tool that emits decoded JSON — or a recorded frames file —
can drive the meter without any protocol work.
"""
from __future__ import annotations

import importlib
import importlib.util
import hashlib
from pathlib import Path
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
    if Path(spec).suffix.lower() == ".py":
        path = Path(spec).resolve(strict=True)
        name = "aion2calc_user_decoder_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
        module_spec = importlib.util.spec_from_file_location(name, path)
        if module_spec is None or module_spec.loader is None:
            raise ValueError("Cannot load that Python decoder file")
        mod = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(mod)
        return _module_decoder(mod, str(path))
    if spec in _REGISTRY:
        return _REGISTRY[spec]()
    if ":" in spec:
        mod_name, attr = spec.split(":", 1)
        obj = getattr(importlib.import_module(mod_name), attr)
        return obj() if isinstance(obj, type) else obj
    mod = importlib.import_module(spec)
    return _module_decoder(mod, spec)


def _module_decoder(mod, spec: str):
    for attr in ("make_decoder", "Decoder", "decoder"):
        if hasattr(mod, attr):
            obj = getattr(mod, attr)
            decoder = obj() if isinstance(obj, type) or (attr == "make_decoder" and callable(obj)) else obj
            if not callable(getattr(decoder, "feed", None)):
                raise ValueError("Decoder must provide feed(bytes), returning CombatEvent objects")
            return decoder
    raise ValueError(f"module {spec!r} has no decoder (expose make_decoder, Decoder or decoder, or use module:attr)")


def import_decoder(name: str, source: str) -> dict:
    """Save a user-selected .py file without running it until capture starts."""
    from ..paths import home
    if Path(name).suffix.lower() != ".py":
        raise ValueError("Choose a Python (.py) decoder file")
    if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > 1_048_576:
        raise ValueError("The decoder must be a nonempty Python file smaller than 1 MiB")
    compile(source, name, "exec")
    folder = home() / "decoders"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hashlib.sha256(source.encode("utf-8")).hexdigest() + ".py")
    path.write_text(source, encoding="utf-8")
    return {"path": str(path), "name": Path(name).name}


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
