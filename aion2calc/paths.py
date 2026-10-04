"""Where data lives.

Bundled data ships in ``aion2calc/data`` (works offline from a fresh clone).
Everything the program writes goes into one user folder, :func:`home`:

    Windows        %LOCALAPPDATA%\\aion2calc    (C:\\Users\\<you>\\AppData\\Local\\aion2calc)
    Linux / macOS  ~/.aion2calc
    any system     $AION2CALC_HOME when it is set

Inside it: ``data`` (synced game data), ``aion2.db`` (catalog, characters,
encounters), ``logs`` (one file per combat log), ``results`` (optimizations run
from the app), ``cache`` and ``icons``.

The launch-time sync writes newer copies of the bundled data into ``data``;
every reader goes through :func:`data_file`, which prefers the user copy when
one exists.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PKG_DATA = Path(__file__).resolve().parent / "data"


def _is_windows() -> bool:
    return sys.platform == "win32"


def default_home() -> Path:
    if os.environ.get("AION2CALC_HOME"):
        return Path(os.environ["AION2CALC_HOME"])
    if _is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / "aion2calc" if base else Path.home() / "AppData" / "Local" / "aion2calc"
    return Path.home() / ".aion2calc"


def home() -> Path:
    h = default_home()
    legacy = Path.home() / ".aion2calc"
    if not h.exists() and legacy != h and legacy.is_dir() and not os.environ.get("AION2CALC_HOME"):
        # earlier versions used ~/.aion2calc on Windows too: move it to AppData once
        try:
            h.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(h))
        except OSError:
            h = legacy          # still in use (another copy running): keep using it this time
    h.mkdir(parents=True, exist_ok=True)
    return h


def resource_root() -> Path:
    """Folder with the bundled extras (``results``, ``example``): the installed app's
    bundle when frozen, else the source checkout."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def logs_dir() -> Path:
    d = home() / "logs"
    d.mkdir(exist_ok=True)
    return d


def results_dir() -> Path:
    d = home() / "results"
    d.mkdir(exist_ok=True)
    return d


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
