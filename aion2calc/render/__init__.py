"""Image renderers (Daevanion boards, build card) and planner links."""
from __future__ import annotations

import io


def save_png(fig, path: str, facecolor: str, dither: bool = False) -> str:
    """Save a figure as a 256-colour PNG (about a third of the size, no visible loss)."""
    from PIL import Image
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=facecolor)
    buf.seek(0)
    im = Image.open(buf).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE).save(path, optimize=True)
    return path
