"""Save browser-rendered application PNGs; never capture the desktop."""
from __future__ import annotations

import base64
import binascii
import io
import time
import uuid

from PIL import Image

from ..paths import home

MAX_PNG = 20 * 1024 * 1024


def save(body: dict) -> dict:
    value = body.get("png")
    prefix = "data:image/png;base64,"
    if not isinstance(value, str) or not value.startswith(prefix) or len(value) > MAX_PNG * 4 // 3 + 100:
        raise ValueError("Provide an application-rendered PNG no larger than 20 MiB.")
    try:
        raw = base64.b64decode(value[len(prefix):], validate=True)
        if len(raw) > MAX_PNG:
            raise ValueError("Application PNG exceeds 20 MiB; collapse long sections and retry.")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.width > 30000 or image.height > 30000 or image.width * image.height > 40000000:
                raise ValueError("Application PNG exceeds supported dimensions.")
            image.verify()
    except (binascii.Error, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Application PNG could not be validated.") from exc
    folder = home() / "screenshots"
    folder.mkdir(exist_ok=True)
    path = folder / f"application-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.png"
    with path.open("xb") as stream:
        stream.write(raw)
    return {"file": str(path), "bytes": len(raw)}
