"""Where data lives.

Bundled data ships in ``aion2calc/data`` (works offline from a fresh clone).
The launch-time sync writes newer copies into the user's data directory
(``~/.aion2calc/data`` or ``$AION2CALC_HOME/data``); every reader goes through
:func:`data_file`, which prefers the user copy when one exists.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

PKG_DATA = Path(__file__).resolve().parent / "data"


def home() -> Path:
    h = Path(os.environ.get("AION2CALC_HOME") or Path.home() / ".aion2calc")
    h.mkdir(parents=True, exist_ok=True)
    return h


def user_data() -> Path:
    return home() / "data"


def data_file(*parts: str) -> Path:
    """User overlay copy if present, else the bundled file."""
    u = user_data().joinpath(*parts)
    return u if u.exists() else PKG_DATA.joinpath(*parts)


def read_json(*parts: str):
    return json.loads(data_file(*parts).read_text(encoding="utf-8"))


def write_user_json(obj, *parts: str) -> Path:
    """Atomically write ``obj`` into the user overlay."""
    path = user_data().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def list_names(*parts: str, suffix: str = ".json") -> list[str]:
    """File stems in a data folder, bundled and user overlay combined."""
    names = set()
    for root in (PKG_DATA, user_data()):
        d = root.joinpath(*parts)
        if d.is_dir():
            names |= {p.stem for p in d.glob(f"*{suffix}")}
    return sorted(names)
