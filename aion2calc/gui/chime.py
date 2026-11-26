"""The overlay's event chime in the app's own windows (0.2.513).

With *Play a sound when an event notification appears* on, the web overlay chimes when a new event enters its event
strip (overlay.js ``playEventSound``): the sound the player uploaded, at 0.6 of its volume, else a short built-in chime,
G5 then C6 0.13 s later, each a sine that rises to 0.22 in 20 ms and falls away over the next 0.31 s. Qt's bundled modules
have no audio, so until 0.2.513 the native overlay played the system's alert instead: Windows' *Default Beep*, a ding at
each new event that sounded like a fault, twice over when the Party window showed the strip too.

On Windows ``play`` sounds the chime itself through the standard library's ``winsound``, a WAV played from memory off the
interface's thread: the built-in chime, made here as the web page makes it, or the uploaded sound when it is a WAV
(``winsound`` plays no MP3, OGG or WebM: those get the built-in chime). Elsewhere it is the system's alert, as before.

``announce`` is the overlay windows': each is a process of its own, and the meter overlay and the Party window both show
the strip, so the events new to a strip are claimed in the app's cache folder and only the first window to claim them
chimes.
"""
from __future__ import annotations

import array
import functools
import hashlib
import io
import math
import os
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Iterable

WINDOWS = sys.platform == "win32"
RATE = 44100
#: the web page's notes: (frequency in Hz, start in seconds)
NOTES = ((784.0, 0.0), (1046.5, 0.13))
#: each note's loudness: from FLOOR up to PEAK in RISE seconds, down to FLOOR at FALL, silent from STOP
PEAK, FLOOR, RISE, FALL, STOP = 0.22, 0.0001, 0.02, 0.33, 0.36
#: the uploaded sound's volume, as the web page plays it
CUSTOM_VOLUME = 0.6
CUSTOM = "overlay-event-sound.wav"
#: how long a claim holds: the windows read the meter every second or so; an event that leaves the strip and comes back
#: (a recurrence) chimes again
CLAIM_S = 60.0
CLAIMS = ("cache", "event-chimes")


def _gain(t: float) -> float:
    """A note's loudness ``t`` seconds after it starts, by exponential ramps (WebAudio's ``exponentialRampToValueAtTime``)."""
    if t < 0 or t >= STOP:
        return 0.0
    if t < RISE:
        return FLOOR * (PEAK / FLOOR) ** (t / RISE)
    if t < FALL:
        return PEAK * (FLOOR / PEAK) ** ((t - RISE) / (FALL - RISE))
    return FLOOR


def _wav(frames: bytes, channels: int, width: int, rate: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames)
    return out.getvalue()


def _samples(frames: bytes) -> array.array:
    samples = array.array("h", frames)
    if sys.byteorder == "big":                           # a WAV's samples are little-endian
        samples.byteswap()
    return samples


def _frames(samples: array.array) -> bytes:
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    return samples.tobytes()


@functools.lru_cache(maxsize=1)
def built_in() -> bytes:
    """The built-in chime, a 16-bit mono WAV of 0.49 s."""
    samples = array.array("h")
    for n in range(int(RATE * (NOTES[-1][1] + STOP))):
        t = n / RATE
        value = sum(_gain(t - start) * math.sin(2 * math.pi * frequency * (t - start)) for frequency, start in NOTES)
        samples.append(max(-32767, min(32767, round(value * 32767))))
    return _wav(_frames(samples), 1, 2, RATE)


def custom(home: Path) -> bytes | None:
    """The uploaded sound at the web page's volume, when it is a WAV (``home/overlay-event-sound.wav``), else None. Its 8-
    and 16-bit samples are scaled down; a WAV of wider samples plays as it is."""
    try:
        raw = (Path(home) / CUSTOM).read_bytes()
        with wave.open(io.BytesIO(raw)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            frames = w.readframes(w.getnframes())
    except (OSError, EOFError, wave.Error):              # none, or not a WAV the standard library reads
        return None
    if width == 2:
        frames = _frames(array.array("h", (round(s * CUSTOM_VOLUME) for s in _samples(frames))))
    elif width == 1:                                     # unsigned, silence at 128
        frames = bytes(round(128 + (b - 128) * CUSTOM_VOLUME) for b in frames)
    else:
        return raw
    return _wav(frames, channels, width, rate)


def _home() -> Path:
    from ..paths import home
    return home()


def _sound(data: bytes) -> None:
    """Play a WAV and wait for its end (on the chime's own thread). Without a sound device, or with a WAV Windows cannot
    play, nothing sounds: never the system's ding."""
    try:
        import winsound
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except Exception:  # noqa: BLE001 - a chime must never disturb the overlay
        pass


def _alert() -> None:
    from PySide6.QtWidgets import QApplication
    QApplication.beep()


def play(custom_sound: bool = False, home: Path | None = None) -> threading.Thread | None:
    """Sound the chime now: on Windows the uploaded WAV (with ``custom_sound``) or the built-in chime, made and played on
    a thread of its own (returned), so the window never waits for either; elsewhere the system's alert."""
    if not WINDOWS:
        _alert()
        return None
    thread = threading.Thread(target=_play, args=(custom_sound, home), name="event-chime", daemon=True)
    thread.start()
    return thread


def _play(custom_sound: bool, home: Path | None) -> None:
    try:
        data = (custom(home or _home()) if custom_sound else None) or built_in()
    except Exception:  # noqa: BLE001 - a chime must never disturb the overlay
        return
    _sound(data)


def claim(keys: Iterable[str], folder: Path, now: float | None = None) -> bool:
    """Whether this window is the first to chime for ``keys``, the events new to its strip. A claim is an empty file in
    ``folder`` named by the keys and the minute: made only by one window (``O_EXCL``), and none is made while the last
    minute's claim on the same keys stands. Claims older than an hour are swept away. Without the folder, every window
    chimes."""
    now = time.time() if now is None else now
    digest = hashlib.sha1("\n".join(sorted(keys)).encode("utf-8")).hexdigest()[:16]
    minute = int(now // CLAIM_S)
    folder = Path(folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:                                      # no folder to share (a file in its place, no right to it)
        return True
    if (folder / f"{digest}-{minute - 1}.claim").exists():
        return False
    try:
        os.close(os.open(folder / f"{digest}-{minute}.claim", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:                              # another window claimed it first
        return False
    except OSError:
        return True
    for old in folder.glob("*.claim"):
        try:
            if now - old.stat().st_mtime > 3600:
                old.unlink()
        except OSError:
            pass
    return True


def announce(keys: Iterable[str], custom_sound: bool = False, home: Path | None = None,
             now: float | None = None) -> bool:
    """Events entered an overlay window's strip (``keys``): chime for them, unless another window already did."""
    base = Path(home) if home is not None else _home()
    if not claim(keys, base.joinpath(*CLAIMS), now):
        return False
    play(custom_sound, base)
    return True
