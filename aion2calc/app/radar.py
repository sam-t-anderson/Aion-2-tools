"""The Hidden Cube radar: where a Hidden Cube is, from the sound it makes.

A Hidden Cube plays a soft jingle that players near it hear, panned to its side and louder the
closer they are: the cube guides tell players to put headphones on and mute the music and the
ambience to find one by ear. The radar listens to the same sound. It reads what Windows plays (a
loopback recording of the default output, through the ``soundcard`` package), matches the jingle's
spectrum, which the player teaches it once beside a cube, and turns how loud the match is into how
near the cube is and its left/right balance into its side. It needs no decoded record.

What a stereo mix cannot tell: whether the cube is in front or behind (one 30° to the right sounds
as one 150° to the right does). Turning towards it tells them apart: a cube ahead moves to the
middle, one behind further out. An Empyrean Trace feather plays a nearly identical jingle, so the
radar hears feathers as well.

Audio stays in memory: only the learned band levels of the background and of the jingle are saved
(``hidden-cube-sound.json`` in the app's data folder), and nothing is recorded or uploaded. Off by
default; Windows only, like the game. The matching is plain numpy and runs anywhere, so the tests
feed it synthetic audio; only :class:`LoopbackSource` touches the sound card.
"""
from __future__ import annotations

import json
import math
import sys
import threading
import time
import traceback
import warnings
from collections import deque
from pathlib import Path

import numpy as np

RATE = 48000                  # samples a second the loopback is opened at (Windows resamples to it)
HOP = 1024                    # one step: 21 ms
WINDOW = 2048                 # the spectrum's window: 43 ms, half overlapped
LOW_HZ, HIGH_HZ, BANDS = 250.0, 16000.0, 40     # 40 bands, each about a seventh of an octave
SMOOTH = 0.25                 # each step's share of the band levels' moving average (about 80 ms)
MARGIN = 1.5                  # a band counts as sounding 1.8 dB above the background
FLOOR_RISE, FLOOR_FALL = 0.01, 0.05             # the background follows a louder place in 2 s, a quieter in 0.4 s
FLOOR_RISE_HEARD = 0.0005     # and barely moves while the jingle plays, so a cube in earshot stays heard
CONFIRM = (3, 0.5)            # the jingle is heard once 3 steps within half a second match (a word in voice chat
                              # can match one step, a bell rings for several)
HOLD_S = 2.5                  # a cube stays on the radar this long after its jingle last sounded
RANGE_DB = 30.0               # the radar's rim: 30 dB quieter than the jingle learned beside a cube
LEARN_S = {"background": 4.0, "cube": 6.0}
COUNTDOWN_S = 5.0             # time to switch back to the game before a learning starts
PROFILE = "hidden-cube-sound.json"
PROFILE_VERSION = 1
SENSITIVITY = (1, 10, 5)      # least, most, default


class LearnError(ValueError):
    """What was heard while learning cannot be told apart; the message says what to change."""


# ---- the spectrum -------------------------------------------------------------------------------

def band_edges(rate: int = RATE, window: int = WINDOW) -> np.ndarray:
    """The FFT bins each band starts at, and the last band's end: ``BANDS + 1`` increasing indexes,
    every band at least one bin wide."""
    freqs = np.fft.rfftfreq(window, 1.0 / rate)
    idx = np.searchsorted(freqs, np.geomspace(LOW_HZ, min(HIGH_HZ, rate / 2), BANDS + 1))
    for i in range(1, len(idx)):
        idx[i] = max(idx[i], idx[i - 1] + 1)
    return idx


def band_centres(rate: int = RATE, window: int = WINDOW) -> np.ndarray:
    freqs = np.fft.rfftfreq(window, 1.0 / rate)
    idx = band_edges(rate, window)
    return np.sqrt(freqs[idx[:-1]] * freqs[np.minimum(idx[1:], len(freqs) - 1)])


_EDGES = band_edges()
_WIDTHS = np.diff(_EDGES).astype(np.float64)
_HANN = np.hanning(WINDOW)


def band_levels(frame: np.ndarray) -> np.ndarray:
    """``(WINDOW, 2)`` samples -> ``(2, BANDS)``: each band's mean power, left and right."""
    spec = np.fft.rfft(np.asarray(frame, dtype=np.float64).T * _HANN, axis=1)
    power = spec.real ** 2 + spec.imag ** 2
    lo = _EDGES[0]
    return np.add.reduceat(power[:, lo:_EDGES[-1]], _EDGES[:-1] - lo, axis=1) / _WIDTHS


def stereo(block: np.ndarray) -> np.ndarray:
    """A recorded block as ``(n, 2)``: mono doubled, extra channels dropped (the loopback is opened
    as stereo, so Windows has already folded a surround mix into the two)."""
    block = np.asarray(block, dtype=np.float32)
    if block.ndim == 1:
        block = block[:, None]
    if block.shape[1] == 1:
        return np.repeat(block, 2, axis=1)
    return block[:, :2]


# ---- learning ------------------------------------------------------------------------------------

def learn_background(levels: list) -> np.ndarray:
    """The background's band levels per channel, ``(2, BANDS)``: the mean of the quieter half of the
    steps, so a passing sound does not raise it."""
    stack = np.stack(levels)                                   # (n, 2, B)
    total = stack.sum(axis=(1, 2))
    quiet = total <= np.median(total)
    return stack[quiet].mean(axis=0)


def _core(template: np.ndarray, share: float = 0.8) -> np.ndarray:
    """The bands holding ``share`` of the template's power, loudest first."""
    order = np.argsort(template)[::-1]
    cum = np.cumsum(template[order]) / max(float(template.sum()), 1e-30)
    return order[:int(np.searchsorted(cum, share)) + 1]


def learn_jingle(levels: list, background: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """The jingle's band levels above the background, ``(BANDS,)``, from the steps recorded beside a
    cube, and how clearly it stood out. The jingle plays in bursts, so the loudest steps above the
    background are the ones it sounds in. Without a learned background, the quietest fifth of the
    steps stands in for it (the gaps between the bursts).

    Raises :class:`LearnError` when the steps hold nothing that stands out, or a sound spread over
    the whole range (music or a fight rather than a jingle)."""
    stack = np.stack(levels).sum(axis=1)                       # (n, B), both channels
    floor = (np.asarray(background).sum(axis=0) if background is not None
             else np.percentile(stack, 20, axis=0))
    excess = np.clip(stack - floor * MARGIN, 0.0, None)
    energy = excess.sum(axis=1)
    if not energy.any():
        raise LearnError("Nothing louder than the background was heard. Stand beside the cube, with the game's "
                         "sound effects on, and learn it again.")
    loud = energy >= np.quantile(energy, 0.6)
    template = excess[loud].mean(axis=0)
    core = _core(template)
    snr = float(template[core].sum() / max(float(floor[core].sum()), 1e-30))
    if snr < 1.0:
        raise LearnError("The cube's jingle did not stand out from the background. Stand closer, mute the music "
                         "and ambient sound in the game, and learn it again.")
    if len(core) > 0.6 * BANDS:
        raise LearnError("What was heard covers the whole range, not a jingle: mute the music, ambient and "
                         "monster sounds in the game, stand beside the cube and learn it again.")
    centres = band_centres()
    return template, {"snr_db": round(10 * math.log10(snr), 1), "bands": int(len(core)),
                      "peak_hz": int(round(float(centres[int(np.argmax(template))]))),
                      "steps": int(loud.sum())}


# ---- matching ------------------------------------------------------------------------------------

def thresholds(sensitivity: int) -> tuple[float, float]:
    """The share of a step's sound that must lie in the jingle's bands, and how loud it must be over the
    background there (a power ratio), for the step to match, from the sensitivity, 1 (strict) to 10
    (loose)."""
    s = min(max(int(sensitivity), SENSITIVITY[0]), SENSITIVITY[1])
    # Tuned on synthetic jingles, voices, music, chimes and noise: the default hears a jingle 24 dB
    # below the learned one about half the time and no voice; from about 8 a voice in the jingle's
    # range can match.
    return 0.70 - 0.0267 * (s - 1), 0.8 * 0.862 ** (s - 1)


def jingle_weights(template: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """How much each band counts as the jingle's (0-1: its learned level against the median of the
    bands holding most of it, nothing below 5 %), and the region around it, an octave either side,
    whose sound a step is weighed against. A bass note or a footstep far below the jingle cannot hide
    it, and the faint levels learning leaves in other bands cannot make one look like it."""
    template = np.asarray(template, dtype=np.float64)
    core = _core(template)
    centres = band_centres()
    region = (centres >= centres[core].min() / 2) & (centres <= centres[core].max() * 2)
    weights = np.minimum(1.0, template / max(float(np.median(template[core])), 1e-30))
    weights[(weights < 0.05) | ~region] = 0.0
    return weights, region.astype(np.float64)


class Matcher:
    """Follows the background and matches each step against the learned jingle.

    The jingle is a sparkle of notes, a few of them sounding in any one step, so a step is not asked
    to look like the whole learned spectrum: it matches when most of what sounds in the jingle's
    region lies in the jingle's bands, loud enough over the background. ``step(levels)`` takes one
    step's ``(2, BANDS)`` band levels and returns that share (``match``), the jingle's level against
    the learned one (a power ratio, 1 = as loud as beside the cube), its balance (-1 left .. 1 right)
    and whether the step matched."""

    def __init__(self, template: np.ndarray, background: np.ndarray | None = None, sensitivity: int = SENSITIVITY[2]):
        self.template = np.asarray(template, dtype=np.float64)
        self.weights, self.region = jingle_weights(self.template)
        self.ref = float(self.weights @ self.template)         # the learned jingle's level in its bands
        self.floor = None if background is None else np.array(background, dtype=np.float64)
        self.smooth = None
        self.min_match, self.min_snr = thresholds(sensitivity)

    def step(self, levels: np.ndarray) -> dict:
        levels = np.asarray(levels, dtype=np.float64)
        self.smooth = levels.copy() if self.smooth is None else self.smooth + SMOOTH * (levels - self.smooth)
        if self.floor is None:
            self.floor = self.smooth.copy()
        excess = np.clip(self.smooth - self.floor * MARGIN, 0.0, None)     # (2, B)
        total = excess.sum(axis=0)
        around = float(self.region @ total)
        left, right = (float(excess[c] @ self.weights) for c in (0, 1))
        level = left + right
        match = level / around if around > 0 else 0.0
        snr = level / max(float(self.floor.sum(axis=0) @ self.weights), 1e-30)
        heard = match >= self.min_match and snr >= self.min_snr
        delta = self.smooth - self.floor
        self.floor += np.where(delta > 0, FLOOR_RISE_HEARD if heard else FLOOR_RISE, FLOOR_FALL) * delta
        return {"match": min(match, 1.0), "level": level / self.ref if self.ref > 0 else 0.0,
                "balance": (right - left) / level if level > 0 else 0.0, "snr": snr, "heard": heard}


class Track:
    """What the radar shows: the jingle once :data:`CONFIRM` steps match, held for :data:`HOLD_S`
    after the last, its level and balance smoothed, and whether it grows louder.

    Time is the audio's own (steps of ``HOP / RATE`` seconds), so a test feeds it at any speed."""

    def __init__(self):
        self.t = 0.0
        self.last = None              # audio time of the last matched step while the jingle is heard
        self.level = self.balance = None
        self.match = 0.0
        self.recent: deque = deque()  # audio times of the latest matched steps
        self.history: deque = deque()  # (time, dB) of matched steps while heard, for the trend

    def add(self, result: dict, dt: float = HOP / RATE) -> None:
        self.t += dt
        self.match = result["match"]
        if not result["heard"]:
            return
        self.recent.append(self.t)
        while self.t - self.recent[0] > CONFIRM[1]:
            self.recent.popleft()
        held = self.last is not None and self.t - self.last <= HOLD_S
        if not held and len(self.recent) < CONFIRM[0]:
            return
        if not held:                  # a new cube, or the same one after a silence: start over
            self.level = self.balance = None
            self.history.clear()
        self.last = self.t
        db = 10 * math.log10(max(result["level"], 1e-6))
        a = 0.3
        self.level = db if self.level is None else self.level + a * (db - self.level)
        self.balance = result["balance"] if self.balance is None else self.balance + a * (result["balance"] - self.balance)
        self.history.append((self.t, db))
        while self.t - self.history[0][0] > 4.0:
            self.history.popleft()

    def trend(self) -> str | None:
        """Louder or quieter over the last few seconds (1 dB a second either way), from a line through
        the matched steps' levels; None until there are enough of them."""
        if len(self.history) < 10 or self.history[-1][0] - self.history[0][0] < 1.5:
            return None
        t = np.array([h[0] for h in self.history])
        db = np.array([h[1] for h in self.history])
        slope = float(np.polyfit(t - t.mean(), db, 1)[0])
        return "louder" if slope >= 1.0 else "quieter" if slope <= -1.0 else "steady"

    def view(self) -> dict:
        since = None if self.last is None else self.t - self.last
        if since is None or since > HOLD_S:
            return {"heard": False, "since": None if since is None else round(since, 1), "match": round(self.match, 2),
                    "level_db": None, "proximity": None, "balance": None, "angle": None, "side": None, "trend": None}
        balance = max(-1.0, min(1.0, self.balance))
        angle = math.degrees(math.asin(balance))         # equal-power panning: (R - L) / (R + L) = sin(azimuth)
        side = "right" if angle >= 15 else "left" if angle <= -15 else "middle"
        return {"heard": True, "since": round(since, 1), "match": round(self.match, 2),
                "level_db": round(self.level, 1), "proximity": round(max(0.0, min(1.0, 1 + self.level / RANGE_DB)), 2),
                "balance": round(balance, 2), "angle": round(angle), "side": side, "trend": self.trend()}


# ---- the learned profile ------------------------------------------------------------------------

def load_profile(path: Path) -> dict:
    """The saved background and jingle, or an empty profile when there is none or it does not fit
    this version's bands."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != PROFILE_VERSION or data.get("rate") != RATE \
            or data.get("bands") != BANDS:
        return {}
    out = {"learned": data.get("learned") if isinstance(data.get("learned"), dict) else {},
           "quality": data.get("quality") if isinstance(data.get("quality"), dict) else None}
    try:
        if data.get("background") is not None:
            bg = np.asarray(data["background"], dtype=np.float64)
            if bg.shape == (2, BANDS) and np.isfinite(bg).all() and (bg >= 0).all():
                out["background"] = bg
        if data.get("jingle") is not None:
            jingle = np.asarray(data["jingle"], dtype=np.float64)
            if jingle.shape == (BANDS,) and np.isfinite(jingle).all() and (jingle >= 0).all() and jingle.any():
                out["jingle"] = jingle
    except (TypeError, ValueError):
        return {}
    return out


def save_profile(path: Path, profile: dict) -> None:
    data = {"version": PROFILE_VERSION, "rate": RATE, "bands": BANDS,
            "band_hz": [int(round(float(f))) for f in band_centres()],
            "learned": profile.get("learned") or {}, "quality": profile.get("quality"),
            "background": None if profile.get("background") is None else np.asarray(profile["background"]).tolist(),
            "jingle": None if profile.get("jingle") is None else np.asarray(profile["jingle"]).tolist()}
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


# ---- the sound card -----------------------------------------------------------------------------

def supported() -> bool:
    return sys.platform == "win32"


_COM = threading.local()


def _soundcard():
    """``soundcard``, with COM initialised on the calling thread. Its import initialises COM on the
    importing thread, and fails on a thread that already did so itself, so only a thread that did not
    import it initialises COM here."""
    first = "soundcard" not in sys.modules
    import soundcard
    if not first and not getattr(_COM, "ready", False):
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)     # COINIT_MULTITHREADED, as soundcard's own import does
    _COM.ready = True
    return soundcard


class LoopbackSource:
    """What the default output plays, as stereo blocks of :data:`HOP` frames (Windows, WASAPI loopback
    through ``soundcard``). Re-opened when the default output changes (headphones plugged in).

    Open and read it on the radar's worker, one long-lived thread (COM is per thread; see
    :func:`_soundcard`)."""

    CHECK_S = 5.0

    def __init__(self):
        if not supported():
            raise RuntimeError("the Hidden Cube radar listens to Windows' sound output; it runs on Windows only")
        try:
            soundcard = _soundcard()
        except ImportError as err:
            raise RuntimeError("the soundcard package is not installed") from err
        warnings.filterwarnings("ignore", message="data discontinuity")    # a late read, harmless here
        self._sc = soundcard
        speaker = soundcard.default_speaker()
        self.device_id, self.name = speaker.id, speaker.name
        mic = soundcard.get_microphone(id=str(speaker.id), include_loopback=True)
        self._rec = mic.recorder(samplerate=RATE, channels=2, blocksize=HOP)
        self._rec.__enter__()
        self._checked = time.monotonic()

    def read(self) -> np.ndarray:
        return self._rec.record(numframes=HOP)

    def stale(self) -> bool:
        now = time.monotonic()
        if now - self._checked < self.CHECK_S:
            return False
        self._checked = now
        try:
            return self._sc.default_speaker().id != self.device_id
        except Exception:
            return True

    def close(self) -> None:
        try:
            self._rec.__exit__(None, None, None)
        except Exception:
            pass


# ---- the radar ----------------------------------------------------------------------------------

class Radar:
    """The radar's worker: listens while it is on or learning, and keeps the state the overlay draws.

    ``source`` opens the audio (a :class:`LoopbackSource` by default; the tests pass a fake), and
    ``path`` is where the learned profile is kept."""

    RETRY_S = 3.0

    def __init__(self, path: Path, source=LoopbackSource):
        self.path = Path(path)
        self._source_factory = source
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self.profile = load_profile(self.path)
        self.enabled = False
        self.sensitivity = SENSITIVITY[2]
        self.device = None
        self.error = None
        self.listening = False
        self.input_db = None
        self._learn = None            # {"kind", "starts" (monotonic), "steps", "levels"}
        self.last_learn = None        # {"kind", "ok", "message"}
        self._learned_at = None       # monotonic time last_learn was set: the overlay shows it a few seconds
        self._reset_matching()

    # -- control (any thread) --
    def configure(self, enabled: bool, sensitivity: int | None = None) -> None:
        with self._lock:
            changed = sensitivity is not None and sensitivity != self.sensitivity
            if sensitivity is not None:
                self.sensitivity = min(max(int(sensitivity), SENSITIVITY[0]), SENSITIVITY[1])
            self.enabled = bool(enabled)
            if changed:
                self._reset_matching()
        if enabled:
            self._ensure_thread()
        self._wake.set()

    def learn(self, kind: str, delay: float = COUNTDOWN_S, seconds: float | None = None) -> None:
        if kind not in LEARN_S:
            raise ValueError("learn background or cube")
        steps = max(1, int(round((LEARN_S[kind] if seconds is None else seconds) * RATE / HOP)))
        with self._lock:
            self._learn = {"kind": kind, "starts": time.monotonic() + max(0.0, delay), "steps": steps, "levels": []}
            self.last_learn = None
        self._ensure_thread()
        self._wake.set()

    def cancel(self) -> None:
        with self._lock:
            self._learn = None
        self._wake.set()

    def clear(self) -> None:
        with self._lock:
            self.profile = {}
            self.last_learn = None
            self._reset_matching()
        self.path.unlink(missing_ok=True)

    def state(self) -> dict:
        with self._lock:
            learning = None
            if self._learn is not None:
                wait = self._learn["starts"] - time.monotonic()
                learning = ({"kind": self._learn["kind"], "phase": "countdown", "seconds": round(wait, 1)} if wait > 0 else
                            {"kind": self._learn["kind"], "phase": "listening",
                             "seconds": round((self._learn["steps"] - len(self._learn["levels"])) * HOP / RATE, 1)})
            learned = self.profile.get("learned") or {}
            out = {"supported": supported(), "enabled": self.enabled, "listening": self.listening,
                   "device": self.device, "error": self.error, "sensitivity": self.sensitivity,
                   "ready": self.profile.get("jingle") is not None,
                   "learned": {"background": learned.get("background") if self.profile.get("background") is not None else None,
                               "cube": learned.get("cube") if self.profile.get("jingle") is not None else None},
                   "quality": self.profile.get("quality"), "learning": learning, "last_learn": self.last_learn,
                   "last_learn_s": None if self.last_learn is None or self._learned_at is None
                   else round(time.monotonic() - self._learned_at, 1),
                   "input_db": self.input_db}
            out.update(self.track.view() if self.matcher is not None else Track().view())
            return out

    # -- the worker --
    def _reset_matching(self) -> None:
        jingle = self.profile.get("jingle")
        self.matcher = None if jingle is None else Matcher(jingle, self.profile.get("background"), self.sensitivity)
        self.track = Track()

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="cube-radar")
                self._thread.start()

    def _wanted(self) -> bool:
        with self._lock:
            return self.enabled or self._learn is not None

    def _run(self) -> None:
        while True:
            if not self._wanted():
                self._wake.wait()
                self._wake.clear()
                continue
            source = None
            try:
                source = self._source_factory()
                with self._lock:
                    self.device, self.error, self.listening = getattr(source, "name", None), None, True
                self._listen(source)
            except Exception as err:                       # a missing device, an unplugged one, no soundcard
                with self._lock:
                    self.error = str(err) or type(err).__name__
                    if self._learn is not None and self._learn["starts"] <= time.monotonic():
                        self.last_learn = {"kind": self._learn["kind"], "ok": False,
                                           "message": f"Listening stopped: {self.error}"}
                        self._learned_at = time.monotonic()
                        self._learn = None
                if not isinstance(err, RuntimeError):
                    traceback.print_exc()
                self._wake.wait(self.RETRY_S)
                self._wake.clear()
            finally:
                with self._lock:
                    self.listening = False
                if source is not None:
                    source.close()

    def _listen(self, source) -> None:
        ring = np.zeros((WINDOW, 2), dtype=np.float32)
        while self._wanted():
            if getattr(source, "stale", lambda: False)():
                return                                     # the default output changed: open the new one
            block = stereo(source.read())
            if not len(block):
                continue
            ring = np.concatenate([ring, block])[-WINDOW:]
            levels = band_levels(ring)
            self._step(levels, len(block) / RATE)

    def _step(self, levels: np.ndarray, dt: float) -> None:
        with self._lock:
            total = float(levels.sum())
            self.input_db = round(10 * math.log10(total), 1) if total > 0 else None
            if self._learn is not None and time.monotonic() >= self._learn["starts"]:
                self._learn["levels"].append(levels)
                if len(self._learn["levels"]) >= self._learn["steps"]:
                    self._finish_learning()
            if self.matcher is not None and self.enabled:
                self.track.add(self.matcher.step(levels), dt)

    def _finish_learning(self) -> None:
        kind, levels = self._learn["kind"], self._learn["levels"]
        self._learn = None
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            if kind == "background":
                self.profile["background"] = learn_background(levels)
                message = "Background learned." + ("" if self.profile.get("jingle") is not None
                                                   else " Now stand beside a Hidden Cube and learn its sound.")
            else:
                jingle, quality = learn_jingle(levels, self.profile.get("background"))
                self.profile["jingle"], self.profile["quality"] = jingle, quality
                message = (f"Cube sound learned: it stood {quality['snr_db']} dB over the background, "
                           f"loudest near {quality['peak_hz']} Hz.")
        except LearnError as err:
            self.last_learn = {"kind": kind, "ok": False, "message": str(err)}
            self._learned_at = time.monotonic()
            return
        self.profile.setdefault("learned", {})[kind] = stamp
        self.last_learn = {"kind": kind, "ok": True, "message": message}
        self._learned_at = time.monotonic()
        self._reset_matching()
        try:
            save_profile(self.path, self.profile)
        except OSError as err:
            self.last_learn["message"] += f" (not saved: {err})"
