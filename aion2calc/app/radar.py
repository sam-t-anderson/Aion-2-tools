"""The Hidden Cube radar: where a Hidden Cube is, from the sound it makes.

A Hidden Cube plays a soft jingle that players near it hear, panned to its side and louder the
closer they are: the cube guides tell players to put headphones on and mute the music and the
ambience to find one by ear. The radar listens to the same sound. It reads what Windows plays (a
loopback recording of the default output, through the ``soundcard`` package) and matches it against
samples the player teaches it:

* the background, in one place or several: each band's level and how much it varies, which the
  radar takes off before it looks for the jingle (the more places, the better it knows what is not
  a cube);
* the jingle, beside a cube and farther away: its bands, its notes (the peaks of the fine spectrum,
  which stand out of the background far better than a band does, so a distant cube is heard and
  another chime is not taken for one) and how loud it is near and far (the radar's rings);
* the jingle with the cube behind the player, beside one taken facing it: what the game's 3D audio
  (or a surround output's rear channels) changes between the two, from which the radar tells ahead
  from behind;
* sounds that are not a cube (an Empyrean Trace feather, a voice): what it must not take for one.

It turns how loud the match is into how near the cube is and its left/right balance into its side,
and draws it on a full circle around the player. A stereo mix alone cannot tell ahead from behind
(a cube 30° to the right sounds as one 150° to the right does): until the samples ahead and behind
teach it the difference, the radar shows both places the cube can be. It needs no decoded record.

Audio stays in memory: only the samples' band levels and peak frequencies are saved
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
import uuid
import warnings
from collections import deque
from pathlib import Path

import numpy as np

RATE = 48000                  # samples a second the loopback is opened at (Windows resamples to it)
HOP = 1024                    # one step: 21 ms
WINDOW = 2048                 # the spectrum's window: 43 ms, half overlapped
LOW_HZ, HIGH_HZ, BANDS = 250.0, 16000.0, 40     # 40 bands, each about a seventh of an octave
SMOOTH = 0.25                 # each step's share of the levels' moving average (about 80 ms)
MARGIN = 1.5                  # a band counts as sounding 1.8 dB above the background, more where it varies:
MARGIN_MAX = 3.0              # up to 4.8 dB, from how far the background samples' levels rose
FLOOR_RISE, FLOOR_FALL = 0.01, 0.05             # the background follows a louder place in 2 s, a quieter in 0.4 s
FLOOR_RISE_HEARD = 0.0005     # and barely moves while the jingle plays, so a cube in earshot stays heard
NEIGHBOURS = 8                # a fine bin's neighbourhood: the 8 bins (190 Hz) either side
PEAK = 2.0                    # a bin is a peak 3 dB over its neighbourhood's median
BROAD = 0.5                   # a step sounding in over half the bands is a footstep or a blast, not a jingle
NOTE_VETO = 0.45              # a step whose peaks are mostly not the jingle's notes is not the jingle, whatever its bands
SHARE_S = 0.125               # (that share is the last eighth of a second's, so one note of another chime cannot pass)
EVIDENCE_S = 1.5              # a sound learned as not a cube hides it while it rang more than the cube lately
CONFIRM = (3, 0.5)            # the jingle is heard once 3 steps within half a second match (a word in voice chat
                              # can match one step, a bell rings for several)
HOLD_S = 2.5                  # a cube stays on the radar this long after its jingle last sounded
RANGE_DB = 30.0               # the radar's rim: 30 dB quieter than the loudest sample, or 6 dB past the quietest
RANGE_MAX_DB = 50.0
CHUNK_S = 2.0                 # ahead or behind is told from the last two seconds of the jingle
FACING = (0.4, 1.5)           # once its score (1 like the samples ahead, -1 behind) passes 0.4 after 1.5 s
LEARN_S = {"background": 4.0, "cube": 8.0, "other": 6.0}
KEEP = {"background": 6, "ahead": 6, "behind": 4, "other": 6}     # the newest samples of each kind kept
FACINGS = ("ahead", "behind")
COUNTDOWN_S = 5.0             # time to switch back to the game before a learning starts
PROFILE = "hidden-cube-sound.json"
PROFILE_VERSION = 2
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
_LO, _HI = int(_EDGES[0]), int(_EDGES[-1])     # the fine spectrum: the FFT bins the bands cover
_STARTS = _EDGES[:-1] - _LO
_WIDTHS = np.diff(_EDGES).astype(np.float64)
_BAND_OF = np.repeat(np.arange(BANDS), np.diff(_EDGES))           # each fine bin's band
_HANN = np.hanning(WINDOW)


def spectrum(frame: np.ndarray) -> np.ndarray:
    """``(WINDOW, C)`` samples -> ``(C, bins)``: each FFT bin's power over the bands' range."""
    spec = np.fft.rfft(np.asarray(frame, dtype=np.float64).T * _HANN, axis=1)[:, _LO:_HI]
    return spec.real ** 2 + spec.imag ** 2


def bands(fine: np.ndarray) -> np.ndarray:
    """A fine spectrum ``(..., bins)`` -> ``(..., BANDS)``: each band's mean power."""
    return np.add.reduceat(fine, _STARTS, axis=-1) / _WIDTHS


def band_levels(frame: np.ndarray) -> np.ndarray:
    """``(WINDOW, C)`` samples -> ``(C, BANDS)``: each band's mean power per channel."""
    return bands(spectrum(frame))


def layout(channels: int) -> np.ndarray:
    """How a recording's channels fold into the radar's (their powers add): ``(2, C)`` left and right,
    or ``(3, C)`` with a third row for what plays behind, from a surround output (quad, 5.1 or 7.1 in
    Windows' channel order: front left and right, centre, LFE, then the back and side pairs). The
    centre counts half to each side and the LFE not at all; side speakers count half behind. Mono is
    both sides; another layout, its first two channels."""
    if channels <= 1:
        return np.ones((2, 1))
    fold = np.zeros((2, channels))
    fold[0, 0] = fold[1, 1] = 1.0
    if channels not in (4, 6, 8):
        return fold
    rear = np.zeros(channels)
    if channels == 4:
        pairs, behind = ((2, 3),), {2: 1.0, 3: 1.0}
    else:
        fold[:, 2] = 0.5
        pairs = ((4, 5), (6, 7)) if channels == 8 else ((4, 5),)
        behind = {4: 1.0, 5: 1.0, 6: 0.5, 7: 0.5} if channels == 8 else {4: 1.0, 5: 1.0}
    for left, right in pairs:
        fold[0, left] = fold[1, right] = 1.0
    for channel, share in behind.items():
        rear[channel] = share
    return np.vstack([fold, rear])


_SPEAKERS = {4: (-45, 45, -135, 135), 6: (-30, 30, 0, None, -110, 110), 8: (-30, 30, 0, None, -150, 150, -90, 90)}


def speakers(channels: int) -> np.ndarray | None:
    """Where a surround layout's speakers stand, in Windows' channel order: unit vectors ``(C, 2)``,
    ahead and to the right (the LFE nowhere); None for stereo and other layouts."""
    az = _SPEAKERS.get(channels)
    if az is None:
        return None
    return np.array([(0.0, 0.0) if a is None else (math.cos(math.radians(a)), math.sin(math.radians(a))) for a in az])


def _peaks(fine: np.ndarray, floor: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """The part of each fine bin's power that stands out as a peak, and its neighbourhood's median.
    A peak is over :data:`PEAK` times that median and, where the bin's own background is followed,
    over it too: a steady tone in the background is not a note."""
    pad = np.pad(fine, [(0, 0)] * (fine.ndim - 1) + [(NEIGHBOURS, NEIGHBOURS)], mode="edge")
    window = np.lib.stride_tricks.sliding_window_view(pad, 2 * NEIGHBOURS + 1, axis=-1)
    median = np.partition(window, NEIGHBOURS, axis=-1)[..., NEIGHBOURS]
    ref = PEAK * median if floor is None else np.maximum(PEAK * median, MARGIN * floor)
    return np.clip(fine - ref, 0.0, None), median


def _profile(peaks: np.ndarray | None) -> np.ndarray | None:
    """A sample's notes, ``(bins,)`` 0-1: its peaks against the strongest, nothing under 5 %, widened a
    bin either side (a note's pitch wavers a little)."""
    if peaks is None:
        return None
    top = float(np.max(peaks)) if np.size(peaks) else 0.0
    if top <= 0:
        return None
    p = np.where(peaks >= 0.05 * top, peaks / top, 0.0)
    return np.maximum(p, np.maximum(np.r_[p[1:], 0.0], np.r_[0.0, p[:-1]]))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b) / (na * nb) if na > 0 and nb > 0 else 0.0


# ---- learning ------------------------------------------------------------------------------------

def _smoothed(stack: np.ndarray) -> np.ndarray:
    """The matcher's moving average over a sample's steps."""
    out = np.empty_like(stack)
    s = stack[0]
    for i in range(len(stack)):
        s = stack[0] if i == 0 else s + SMOOTH * (stack[i] - s)
        out[i] = s
    return out


def learn_background(levels: list) -> dict:
    """A background sample: each band's level per channel, ``(V, BANDS)`` (the mean of the quieter half
    of the steps, so a passing sound does not raise it), and how far each rose over the background the
    radar follows (the 90th percentile, once it settled), which sets that band's margin: a band that
    varies a lot needs more before it counts as sounding."""
    stack = np.stack(levels).astype(np.float64)                # (n, V, B)
    total = stack.sum(axis=(1, 2))
    mean = stack[total <= np.median(total)].mean(axis=0)
    floor, ratios = mean.copy(), []
    settle = min(int(RATE / HOP), len(stack) // 3)
    for i, s in enumerate(_smoothed(stack)):
        if i >= settle:
            ratios.append(s / np.maximum(floor, 1e-30))
        delta = s - floor
        floor += np.where(delta > 0, FLOOR_RISE, FLOOR_FALL) * delta
    spread = np.quantile(np.stack(ratios), 0.9, axis=0) if ratios else np.full_like(mean, MARGIN)
    return {"kind": "background", "levels": mean, "spread": spread}


def _core(template: np.ndarray, share: float = 0.8) -> np.ndarray:
    """The bands holding ``share`` of the template's power, loudest first."""
    order = np.argsort(template)[::-1]
    cum = np.cumsum(template[order]) / max(float(template.sum()), 1e-30)
    return order[:int(np.searchsorted(cum, share)) + 1]


def _band_sums(fine: np.ndarray) -> np.ndarray:
    return np.add.reduceat(fine, _STARTS, axis=-1)


def _over_background(levels: list, background, silent: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A sample's steps over the background: their excess ``(n, V, B)``, the background ``(V, B)`` and the
    loudest 40 % of the steps (a jingle plays in bursts: the loudest steps are the ones it sounds in),
    leaving out the steps a footstep or a blast fills most bands of. Without a learned background, the
    quietest fifth of the steps stands in for it (the gaps)."""
    stack = np.stack(levels).astype(np.float64)
    floor = np.percentile(stack, 20, axis=0)
    if background is not None:
        bg = np.asarray(background, dtype=np.float64)
        rows = min(len(bg), len(floor))
        floor[:rows] = bg[:rows]
    excess = np.clip(stack - floor * MARGIN, 0.0, None)
    lr = excess[:, :2].sum(axis=1)
    if not lr.any():
        raise LearnError(silent)
    broad = (lr > 0).mean(axis=1) > BROAD
    if broad.all():                                # all of it fills the range: the caller says so
        return excess, floor, broad
    energy = lr.sum(axis=1)
    return excess, floor, ~broad & (energy >= np.quantile(energy[~broad], 0.6))


def _step_peaks(fines: list) -> tuple[np.ndarray, np.ndarray]:
    """A sample's fine spectra smoothed as the matcher smooths them, and each step's peaks ``(n, V, bins)``."""
    smooth = _smoothed(np.stack(fines).astype(np.float64))
    return smooth, np.stack([_peaks(s)[0] for s in smooth])


def _notes_of(smooth: np.ndarray, steps: np.ndarray, loud: np.ndarray, inside: np.ndarray, floor: np.ndarray):
    """A sample's own notes: the mean of its loud steps' peaks within the jingle's region ``(bins,)``;
    None when the sound is no sparkle of notes (most of what it adds over the background is not in
    peaks, or its peaks cover the region)."""
    mean = steps[loud][:, :2].sum(axis=1).mean(axis=0)
    mean[~inside] = 0.0
    over = np.clip(smooth[loud][:, :2].sum(axis=1).mean(axis=0) - (floor[:2].sum(axis=0) * MARGIN)[_BAND_OF], 0.0, None)
    notes = _profile(mean)
    if notes is None or mean.sum() < 0.35 * over[inside].sum() or (notes > 0).sum() > 0.3 * inside.sum():
        return None
    return np.where(mean >= 0.02 * mean.max(), mean, 0.0)


def _on_notes(steps: np.ndarray, loud: np.ndarray, notes: np.ndarray, inside: np.ndarray) -> tuple[np.ndarray, float]:
    """A sample's peaks on the notes learned before: their mean over its loud steps ``(bins,)``, and the
    median share of each step's peaks in the region that they hold."""
    both = steps[loud][:, :2].sum(axis=1)
    around = both[:, inside].sum(axis=1)
    on = both * (notes > 0)
    sounding = around > 0
    share = float(np.median(on[sounding].sum(axis=1) / around[sounding])) if sounding.any() else 0.0
    return on.mean(axis=0), share


def _alike(a: np.ndarray, b: np.ndarray) -> float:
    """How alike two sounds' notes are, 0-1: the cosine of their square roots, so that which notes they
    are counts more than how often each happened to ring while it was learned."""
    return _cosine(np.sqrt(a), np.sqrt(b))


def _note_bands(tonal: np.ndarray) -> np.ndarray:
    """The bands a sample's notes are in, and their neighbours: the rest of its excess was something else."""
    held = np.zeros(BANDS, dtype=bool)
    held[np.unique(_BAND_OF[tonal > 0])] = True
    return (held | np.r_[held[1:], False] | np.r_[False, held[:-1]]).astype(np.float64)


_FAINT = ("The cube's jingle did not stand out from the background. Stand closer, mute the music and ambient sound "
          "in the game, and learn it again.")
_UNLIKE = ("That did not sound like the cube learned before: learn it again while the cube jingles, or forget the "
           "old samples if this is the right sound.")
_WHOLE = ("What was heard covers the whole range, not a jingle: mute the music, ambient and monster sounds in the "
          "game, stand beside the cube and learn it again.")


def learn_jingle(levels: list, fines: list | None = None, background=None, facing: str = "ahead",
                 model: "Model | None" = None) -> dict:
    """A cube sample from the steps recorded with a cube in earshot: the jingle's band levels per
    channel over the background, ``(V, BANDS)``, its notes (when it is a sparkle of them), two-second
    chunks of it (from which the samples ahead and behind are told apart) and how clearly it stood out.

    ``model`` holds what the samples learned before. A later sample may be fainter (taken farther
    away, or with the cube behind) but must be the same jingle: most of its peaks on the jingle's
    notes, when those are learned, or its bands shaped like the jingle's. Only what lies in the
    jingle's notes or bands is kept of it: farther away, a footstep or a breeze is as loud as the
    jingle.

    Raises :class:`LearnError` when the steps hold nothing that stands out, a sound spread over the
    whole range (music or a fight rather than a jingle), or one unlike the cube learned before."""
    known = model if model is not None and model.ready else None
    excess, floor, loud = _over_background(levels, background, "Nothing louder than the background was heard. Stand "
                                           "beside the cube, with the game's sound effects on, and learn it again.")
    template = excess[loud].mean(axis=0)                       # (V, B)
    total = template[:2].sum(axis=0)
    core = _core(total)
    snr = float(total[core].sum() / max(float(floor[:2].sum(axis=0)[core].sum()), 1e-30))
    smooth, steps = _step_peaks(fines) if fines else (None, None)
    if known is None:
        if snr < 1.0:
            raise LearnError(_FAINT)
        if len(core) > 0.6 * BANDS:
            raise LearnError(_WHOLE)
        inside = jingle_weights(total)[1][_BAND_OF] > 0
        tonal = None if steps is None else _notes_of(smooth, steps, loud, inside, floor)
        mask = None if tonal is None else _note_bands(tonal)
    else:
        inside = known.region[_BAND_OF] > 0
        tonal = None if steps is None else _notes_of(smooth, steps, loud, inside, floor)
        if known.notes is not None and steps is not None:
            if tonal is None or _alike(tonal, known.notes) < 0.5:     # measured on the jingle's notes
                tonal, share = _on_notes(steps, loud, known.notes, inside)
                if share < 0.4 or not tonal.any():
                    raise LearnError(_FAINT if snr < 0.5 else _UNLIKE)
        else:
            if snr < 0.5:
                raise LearnError(_FAINT)
            if len(core) > 0.6 * BANDS:
                raise LearnError(_WHOLE)
            if _cosine(total * known.region, known.shape * known.region) < 0.6:
                raise LearnError(_UNLIKE)
        mask = (_note_bands(tonal) if tonal is not None
                else np.convolve((known.weights > 0).astype(np.float64), np.ones(3), "same") > 0)
    if mask is not None:
        template = template * mask
        excess = excess * mask
        total = template[:2].sum(axis=0)
        core = _core(total)
        snr = float(total[core].sum() / max(float(floor[:2].sum(axis=0)[core].sum()), 1e-30))
    per_step = excess if tonal is None else _band_sums(steps * (_profile(tonal) > 0))
    width = max(1, int(round(CHUNK_S * RATE / HOP)))
    chunks = [per_step[i:i + width].sum(axis=0) for i in range(0, len(per_step) - width + 1, width)]
    centres = band_centres()
    return {"kind": "cube", "facing": facing, "excess": template, "tonal": tonal,
            "chunks": [c for c in chunks if c[:2].sum() > 0], "chunk_kind": "bands" if tonal is None else "notes",
            "quality": {"snr_db": round(10 * math.log10(max(snr, 1e-6)), 1), "bands": int(len(core)),
                        "peak_hz": int(round(float(centres[int(np.argmax(total))]))), "steps": int(loud.sum()),
                        "notes": 0 if tonal is None else int((tonal > 0).sum())}}


def learn_other(levels: list, fines: list | None = None, background=None) -> dict:
    """A sample of a sound that is not a cube: its band levels and notes over the background, as a cube
    sample's, without the checks that it is a jingle."""
    excess, floor, loud = _over_background(levels, background, "Nothing louder than the background was heard: "
                                           "learn it while the sound plays.")
    template = excess[loud].mean(axis=0)
    total = template[:2].sum(axis=0)
    tonal = None
    if fines:
        smooth, steps = _step_peaks(fines)
        tonal = _notes_of(smooth, steps, loud, jingle_weights(total)[1][_BAND_OF] > 0, floor)
    if tonal is not None:
        template = template * _note_bands(tonal)
        total = template[:2].sum(axis=0)
    return {"kind": "other", "excess": template, "tonal": tonal,
            "quality": {"peak_hz": int(round(float(band_centres()[int(np.argmax(total))]))),
                        "bands": int(len(_core(total)))}}


# ---- what the samples teach together ------------------------------------------------------------

def thresholds(sensitivity: int) -> tuple[float, float]:
    """The share of a step's sound that must lie in the jingle's bands, and how loud it must be over the
    background there (a power ratio), for the step to match, from the sensitivity, 1 (strict) to 10
    (loose)."""
    s = min(max(int(sensitivity), SENSITIVITY[0]), SENSITIVITY[1])
    # Tuned on synthetic jingles, voices, music, chimes and noise: the default hears a jingle 24 dB
    # below the learned one about half the time and no voice; from about 8 a voice in the jingle's
    # range can match.
    return 0.70 - 0.0267 * (s - 1), 0.8 * 0.862 ** (s - 1)


def note_thresholds(sensitivity: int) -> tuple[float, float]:
    """With the jingle's notes learned, the share of a step's peaks in its region that must be the
    jingle's notes, and how far those must stand over their neighbourhoods, for the step to match."""
    s = min(max(int(sensitivity), SENSITIVITY[0]), SENSITIVITY[1])
    return 0.60 - 0.025 * (s - 1), 0.5 * 0.85 ** (s - 1)


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


def _lda(ahead: np.ndarray, behind: np.ndarray):
    """A line through the features that best parts the chunks ahead from those behind (each feature
    weighed by how little it varies within each), scaled so the mean ahead scores 1 and the mean
    behind -1, and the midpoint; None when it parts nothing."""
    mu_a, mu_b = ahead.mean(axis=0), behind.mean(axis=0)
    var = (np.concatenate([ahead - mu_a, behind - mu_b]) ** 2).mean(axis=0)
    var = var + 0.01 * np.concatenate([ahead, behind]).var(axis=0) + 1e-9
    w = (mu_a - mu_b) / var
    mid = (mu_a + mu_b) / 2
    scale = float(w @ (mu_a - mid))
    return (w / scale, mid) if scale > 0 else None


class FrontBack:
    """Tells ahead from behind on two seconds of the jingle, from what its samples taken facing the cube
    and with it behind differ in: the balance of its low, middle and high notes (the game's 3D audio
    dulls a sound behind the listener) and, from a surround output, how much of it the rear channels
    play. Fitted on the samples' two-second chunks, and kept only when it tells held-out ones apart:
    each chunk is judged by a fit to all the others, and 85 % of them must come out on their own side."""

    MIN_CHUNKS = 3
    ACCURACY = 0.85

    def __init__(self, groups: list, weights: np.ndarray, rear: bool, w: np.ndarray, mid: np.ndarray, accuracy: float):
        self.groups, self.weights, self.rear = groups, weights, rear
        self.w, self.mid, self.accuracy = w, mid, accuracy

    @staticmethod
    def groups_for(weights: np.ndarray, shape: np.ndarray) -> list:
        """The jingle's bands in up to three runs of about equal energy, low to high."""
        index = np.nonzero(weights > 0)[0]
        if len(index) < 2:
            return []
        energy = shape[index] / max(float(shape[index].sum()), 1e-30)
        runs = min(3, len(index))
        group = np.minimum(runs - 1, ((np.cumsum(energy) - energy / 2) * runs).astype(int))
        groups = [index[group == g] for g in range(runs) if (group == g).any()]
        return groups if len(groups) >= 2 else []

    @staticmethod
    def features(energy: np.ndarray, groups: list, weights: np.ndarray, rear: bool) -> np.ndarray:
        lr = energy[0] + energy[1]
        total = float(lr.sum())
        e = 10 * np.log10(np.maximum([float(lr[g].sum()) for g in groups], 1e-3 * total + 1e-30)) if groups else []
        out = [] if not groups else [e[-1] - e[0]] + ([e[1] - (e[0] + e[2]) / 2] if len(groups) == 3 else [])
        if rear:
            out.append(float(energy[2] @ weights) / max(float(lr @ weights), 1e-30))
        return np.array(out, dtype=np.float64)

    @classmethod
    def fit(cls, cubes: list, model: "Model"):
        """``(FrontBack or None, status)``: "learned"; "alike" when ahead and behind sound the same;
        "need_ahead" with samples behind only, "need_more" when too little of the jingle was heard to
        judge; None without a sample behind."""
        kind = "bands" if model.notes is None else "notes"
        chunks = {f: [np.asarray(c) for s in cubes if s.get("facing") == f and s.get("chunk_kind") == kind
                      for c in s.get("chunks") or ()] for f in FACINGS}
        if not chunks["behind"]:
            return None, None
        if not chunks["ahead"]:
            return None, "need_ahead"
        rows = {c.shape[0] for f in FACINGS for c in chunks[f]}
        rear = rows == {3}
        if len(rows) > 1:                          # learned on different outputs: only left and right compare
            chunks = {f: [c[:2] for c in chunks[f]] for f in FACINGS}
        groups = cls.groups_for(model.weights, model.shape)
        if not groups and not rear:
            return None, "alike"
        a = np.array([cls.features(c, groups, model.weights, rear) for c in chunks["ahead"]])
        b = np.array([cls.features(c, groups, model.weights, rear) for c in chunks["behind"]])
        if len(a) < cls.MIN_CHUNKS or len(b) < cls.MIN_CHUNKS:
            return None, "need_more"
        x, y = np.concatenate([a, b]), np.r_[np.ones(len(a)), -np.ones(len(b))]
        right = 0
        for i in range(len(x)):
            keep = np.arange(len(x)) != i
            fit = _lda(x[keep & (y > 0)], x[keep & (y < 0)])
            right += fit is not None and np.sign(float((x[i] - fit[1]) @ fit[0])) == y[i]
        fit = _lda(a, b)
        if fit is None or right / len(x) < cls.ACCURACY:
            return None, "alike"
        return cls(groups, model.weights, rear, fit[0], fit[1], round(right / len(x), 2)), "learned"

    def score(self, energy: np.ndarray) -> float | None:
        """How much two seconds of the jingle sound like the samples ahead (1) or behind (-1)."""
        if self.rear and energy.shape[0] < 3:
            return None
        return float((self.features(energy[:3] if self.rear else energy[:2], self.groups, self.weights, self.rear)
                      - self.mid) @ self.w)


class Model:
    """What the samples teach together: the background to take off (the median of the background
    samples, and each band's margin from how much it varied), the jingle's bands, notes and levels near
    and far, the sounds that are not a cube, and how ahead differs from behind."""

    def __init__(self, samples=()):
        self.samples = list(samples)
        for i, s in enumerate(self.samples):
            s.setdefault("id", f"s{i}")
        backgrounds = [s for s in self.samples if s["kind"] == "background"]
        cubes = [s for s in self.samples if s["kind"] == "cube"]
        self.floor = self.margin = self.latest_background = None
        if backgrounds:
            rows = np.shape(backgrounds[-1]["levels"])
            same = [s for s in backgrounds if np.shape(s["levels"]) == rows]
            self.floor = np.median(np.stack([s["levels"] for s in same]), axis=0)
            self.margin = np.clip(np.median(np.stack([s["spread"] for s in same]), axis=0), MARGIN, MARGIN_MAX)
            self.latest_background = np.asarray(backgrounds[-1]["levels"])
        self.ready = bool(cubes)
        self.shape = self.weights = self.region = self.unit = self.notes = self.note_region = self.front = None
        self.ref = self.note_ref = 0.0
        self.levels_db, self.others, self.alike = {}, [], []
        self.range_db, self.front_status, self.surround = RANGE_DB, None, False
        if not cubes:
            return
        totals = [np.asarray(s["excess"])[:2].sum(axis=0) for s in cubes]
        self.shape = np.mean([t / max(float(t[_core(t)].sum()), 1e-30) for t in totals], axis=0)
        self.weights, self.region = jingle_weights(self.shape)
        self.unit = self.shape * self.region / max(float(np.linalg.norm(self.shape * self.region)), 1e-30)
        levels = np.array([float(self.weights @ t) for t in totals])
        self.ref = float(levels.max())
        self.levels_db = {s["id"]: 10 * math.log10(max(lv / self.ref, 1e-6)) for s, lv in zip(cubes, levels)}
        loudest = cubes[int(np.argmax(levels))]
        tonal = [s for s in cubes if s.get("tonal") is not None]
        if loudest.get("tonal") is not None:     # the notes, when the loudest sample (beside the cube) found them
            self.notes = np.max([_profile(s["tonal"]) for s in tonal], axis=0)
            self.note_region = (self.region[_BAND_OF] > 0).astype(np.float64)
            note_levels = {s["id"]: float(self.notes @ s["tonal"]) for s in tonal}
            self.note_ref = max(note_levels.values())
            self.levels_db.update({k: 10 * math.log10(max(v / self.note_ref, 1e-6)) for k, v in note_levels.items()})
        if len(cubes) > 1:
            self.range_db = min(RANGE_MAX_DB, max(RANGE_DB, 6.0 - min(self.levels_db.values())))
        for s in self.samples:
            if s["kind"] == "other":
                self._add_other(s)
        for s in cubes:                            # a surround output played a sample on its rear channels
            e = np.asarray(s["excess"])
            lr = float((e[0] + e[1]) @ self.weights)
            self.surround = self.surround or (len(e) == 3 and lr > 0 and float(e[2] @ self.weights) / lr >= 0.25)
        self.front, self.front_status = FrontBack.fit(cubes, self)

    def _add_other(self, sample: dict) -> None:
        """A sound learned as not a cube, by what tells it from the cube: the notes only one of the two
        plays (when both were learned with their notes), else each band's log ratio of the two."""
        shape = np.asarray(sample["excess"])[:2].sum(axis=0) * self.region
        notes = _profile(sample.get("tonal"))
        if notes is not None and self.notes is not None:
            if _alike(notes, self.notes) >= 0.85:      # the radar could not tell it from the cube: it would hide it
                self.alike.append(sample["id"])
                return
            self.others.append({"only": notes * ((notes >= 0.2) & (self.notes == 0)),
                                "cube_only": self.notes * ((self.notes >= 0.2) & (notes == 0))})
            return
        if _cosine(shape, self.shape * self.region) >= 0.97:
            self.alike.append(sample["id"])
            return
        ratio = np.log(np.maximum(shape / max(float(np.linalg.norm(shape)), 1e-30), 0.02) / np.maximum(self.unit, 0.02))
        self.others.append({"bands": True, "only": np.maximum(ratio, 0.0), "cube_only": np.maximum(-ratio, 0.0)})

    def facing(self, energy: np.ndarray) -> float | None:
        """How much the last two seconds of the jingle sound like the samples ahead (1) or behind (-1); from
        a surround output without them, a jingle mostly on the rear channels is behind (-1). None when
        it cannot tell."""
        if self.front is not None:
            score = self.front.score(energy)
            if score is not None:
                return score
        if len(energy) == 3:
            lr = float((energy[0] + energy[1]) @ self.weights)
            if lr > 0 and float(energy[2] @ self.weights) / lr >= 0.6:
                return -1.0
        return None


# ---- matching ------------------------------------------------------------------------------------

class Matcher:
    """Follows the background and matches each step against what the samples learned.

    The jingle is a sparkle of notes, a few of them sounding in any one step, so a step is not asked
    to look like the whole learned spectrum: it matches when most of what sounds in the jingle's
    region lies in the jingle's bands, loud enough over the background. Once its notes are learned, a
    step also matches when most of the region's peaks are the jingle's notes, far enough over their
    neighbourhoods (which hears a cube farther away), and a step whose peaks are other notes does not
    match however its bands look; nor does one closer to a sound learned as not a cube.

    ``step(levels, fine, channels)`` takes one step's ``(V, BANDS)`` band levels, its fine spectrum and,
    from a surround output, each channel's band levels; it returns that share (``match``), the jingle's
    level against the loudest sample (a power ratio, 1 = as loud as beside the cube), its balance (-1
    left .. 1 right), whether the step matched, how much the last two seconds sounded like the samples
    ahead or behind (``front``) and, once a surround output has played the jingle on its rear channels
    (so the game renders it in surround), its direction from the speakers (``vector``, degrees)."""

    def __init__(self, model: Model, sensitivity: int = SENSITIVITY[2]):
        self.model = model
        self.weights, self.region = model.weights, model.region
        self.min_match, self.min_snr = thresholds(sensitivity)
        self.min_share, self.min_note_snr = note_thresholds(sensitivity)
        self.window = max(1, int(round(CHUNK_S * RATE / HOP)))
        self.surround = model.surround
        self.smooth = None

    def _reset(self, rows: tuple) -> None:
        """Start over (on the first step, and when the recording's channels change)."""
        def fits(learned):
            return learned is not None and learned.shape[0] >= rows[0] and learned.shape[1:] == rows[1:]
        self.smooth = None
        self.floor = self.model.floor[:rows[0]].copy() if fits(self.model.floor) else None
        self.margin = self.model.margin[:rows[0]] if fits(self.model.margin) else MARGIN
        self.fine = self.fine_floor = self.chan_smooth = self.chan_floor = None
        self.recent, self.recent_sum = deque(), None
        self.evidence = [[0.0, 0.0] for _ in self.model.others]   # (the cube's, that sound's) lately
        self.shares, self.on, self.around = deque(), 0.0, 0.0

    def step(self, levels: np.ndarray, fine: np.ndarray | None = None, channels: np.ndarray | None = None) -> dict:
        levels = np.asarray(levels, dtype=np.float64)
        if self.smooth is None or self.smooth.shape != levels.shape:
            self._reset(levels.shape)
        self.smooth = levels.copy() if self.smooth is None else self.smooth + SMOOTH * (levels - self.smooth)
        if self.floor is None:
            self.floor = self.smooth.copy()
        excess = np.clip(self.smooth - self.floor * self.margin, 0.0, None)     # (V, B)
        total = excess[:2].sum(axis=0)
        around = float(self.region @ total)
        left, right = (float(excess[c] @ self.weights) for c in (0, 1))
        level = left + right
        match = level / around if around > 0 else 0.0
        snr = level / max(float(self.floor[:2].sum(axis=0) @ self.weights), 1e-30)
        heard = match >= self.min_match and snr >= self.min_snr
        out = {"match": min(match, 1.0), "level": level / self.model.ref if self.model.ref > 0 else 0.0,
               "balance": (right - left) / level if level > 0 else 0.0, "snr": snr}
        energy, notes, peaks = excess, self.model.notes, None
        if notes is not None and fine is not None:
            heard, energy, peaks = self._notes(np.asarray(fine, dtype=np.float64), heard, out)
        if self.model.others and self._like_another(total, peaks) and heard:
            heard = False                          # the sound learned as not a cube
        if peaks is not None:
            delta = self.fine - self.fine_floor
            self.fine_floor += np.where(delta > 0, FLOOR_RISE_HEARD if heard else FLOOR_RISE, FLOOR_FALL) * delta
        vector = None if channels is None else self._vector(np.asarray(channels, dtype=np.float64), heard)
        delta = self.smooth - self.floor
        self.floor += np.where(delta > 0, FLOOR_RISE_HEARD if heard else FLOOR_RISE, FLOOR_FALL) * delta
        self.recent.append(energy)
        self.recent_sum = energy.copy() if self.recent_sum is None else self.recent_sum + energy
        if len(self.recent) > self.window:
            self.recent_sum = np.clip(self.recent_sum - self.recent.popleft(), 0.0, None)
        if heard and len(energy) == 3 and not self.surround:
            lr = float((self.recent_sum[0] + self.recent_sum[1]) @ self.weights)
            self.surround = lr > 0 and float(self.recent_sum[2] @ self.weights) / lr >= 0.25
        out["heard"] = heard
        out["front"] = self.model.facing(self.recent_sum) if heard else None
        out["vector"] = vector if heard and self.surround else None
        return out

    def _vector(self, channels: np.ndarray, heard: bool) -> float | None:
        """The jingle's direction from a surround output's own channels (degrees): its speakers'
        directions, weighed by how much of the jingle each plays; None when none plays it."""
        units = speakers(len(channels))
        if units is None:
            return None
        if self.chan_smooth is None or self.chan_smooth.shape != channels.shape:
            self.chan_smooth, self.chan_floor = channels.copy(), channels.copy()
        else:
            self.chan_smooth += SMOOTH * (channels - self.chan_smooth)
        each = np.clip(self.chan_smooth - self.chan_floor * MARGIN, 0.0, None) @ self.weights
        delta = self.chan_smooth - self.chan_floor
        self.chan_floor += np.where(delta > 0, FLOOR_RISE_HEARD if heard else FLOOR_RISE, FLOOR_FALL) * delta
        x, y = each @ units
        return math.degrees(math.atan2(y, x)) if x or y else None

    def _like_another(self, total: np.ndarray, peaks: np.ndarray | None) -> bool:
        """Whether a sound learned as not a cube rang more than the cube over the last second and a
        half, in what only one of the two plays: its notes and the cube's that the other lacks (a note
        both play says nothing), else the bands each holds more of, by how much more."""
        rate = HOP / RATE / EVIDENCE_S
        v = total * self.region
        like = False
        for other, evidence in zip(self.model.others, self.evidence):
            if other.get("bands"):
                cube, it = float(v @ other["cube_only"]), float(v @ other["only"])
            elif peaks is not None:
                cube, it = float(peaks @ other["cube_only"]), float(peaks @ other["only"])
            else:
                continue
            evidence[0] += rate * (cube - evidence[0])
            evidence[1] += rate * (it - evidence[1])
            like = like or evidence[1] > evidence[0]
        return like

    def _notes(self, fine: np.ndarray, heard: bool, out: dict) -> tuple[bool, np.ndarray, np.ndarray]:
        """The notes' side of a step: whether it matches with them, the jingle's energy per band (its
        notes' peaks) for telling ahead from behind, and both channels' peaks; the level and balance
        come from the notes."""
        model, notes = self.model, self.model.notes
        if self.fine is None or self.fine.shape != fine.shape:
            self.fine, self.fine_floor = fine.copy(), fine.copy()
        else:
            self.fine += SMOOTH * (fine - self.fine)
        peaks, median = _peaks(self.fine, self.fine_floor)
        on_left, on_right = float(peaks[0] @ notes), float(peaks[1] @ notes)
        on = on_left + on_right
        both = peaks[:2].sum(axis=0)
        around = float(both @ model.note_region)
        self.shares.append((on, around))
        self.on, self.around = self.on + on, self.around + around
        if len(self.shares) > max(1, int(round(SHARE_S * RATE / HOP))):
            old_on, old_around = self.shares.popleft()
            self.on, self.around = max(0.0, self.on - old_on), max(0.0, self.around - old_around)
        share = min(1.0, self.on / self.around) if self.around > 0 else 0.0
        note_snr = on / max(float(notes @ median[:2].sum(axis=0)), 1e-30)
        heard = (heard and share >= NOTE_VETO) or (share >= self.min_share and note_snr >= self.min_note_snr)
        out.update(level=on / model.note_ref if model.note_ref > 0 else 0.0,
                   balance=(on_right - on_left) / on if on > 0 else 0.0, share=round(share, 2))
        return heard, _band_sums(peaks * (notes > 0)), both


def direction(angle: float, facing: str | None) -> str:
    """Where the cube is, in words: one of eight directions once ahead and behind are told apart, else
    its side (the radar shows both places it can be)."""
    side = "right" if angle > 0 else "left"
    a = abs(angle)
    if facing is None:
        a = min(a, 180 - a)
        return "ahead or behind" if a <= 15 else f"to your {side}" if a >= 67.5 else f"to your {side}, ahead or behind"
    if a <= 22.5:
        return "ahead"
    if a <= 67.5:
        return f"ahead to your {side}"
    if a <= 112.5:
        return f"to your {side}"
    return f"behind you to the {side}" if a <= 157.5 else "behind you"


class Track:
    """What the radar shows: the jingle once :data:`CONFIRM` steps match, held for :data:`HOLD_S`
    after the last, its level and balance smoothed, whether it grows louder, and whether it is ahead
    or behind once 1.5 seconds of it say so (until it clearly says otherwise); from a surround output,
    its direction from the speakers.

    Time is the audio's own (steps of ``HOP / RATE`` seconds), so a test feeds it at any speed."""

    def __init__(self, range_db: float = RANGE_DB):
        self.range_db = range_db
        self.t = 0.0
        self.last = None              # audio time of the last matched step while the jingle is heard
        self.level = self.balance = None
        self.match = 0.0
        self.recent: deque = deque()  # audio times of the latest matched steps
        self.history: deque = deque()  # (time, dB) of matched steps while heard, for the trend
        self._new_cube()

    def _new_cube(self) -> None:
        self.front = self.front_since = self.facing = self.vector = None

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
            self._new_cube()
        self.last = self.t
        db = 10 * math.log10(max(result["level"], 1e-6))
        a = 0.3
        self.level = db if self.level is None else self.level + a * (db - self.level)
        self.balance = result["balance"] if self.balance is None else self.balance + a * (result["balance"] - self.balance)
        self.history.append((self.t, db))
        while self.t - self.history[0][0] > 4.0:
            self.history.popleft()
        if result.get("vector") is not None:
            v = np.array([math.cos(math.radians(result["vector"])), math.sin(math.radians(result["vector"]))])
            self.vector = v if self.vector is None else self.vector + a * (v - self.vector)
        front = result.get("front")
        if front is not None:
            front = max(-2.0, min(2.0, front))
            self.front = front if self.front is None else self.front + 0.05 * (front - self.front)
            self.front_since = self.t if self.front_since is None else self.front_since
            if self.t - self.front_since >= FACING[1]:
                if self.front >= FACING[0]:
                    self.facing = "ahead"
                elif self.front <= -FACING[0]:
                    self.facing = "behind"

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
                    "level_db": None, "proximity": None, "balance": None, "angle": None, "mirror": None,
                    "facing": None, "side": None, "direction": None, "trend": None}
        balance = max(-1.0, min(1.0, self.balance))
        if self.vector is not None and self.vector.any():   # a surround output: its speakers tell the direction
            angle = math.degrees(math.atan2(self.vector[1], self.vector[0]))
            facing, mirror = ("ahead" if abs(angle) <= 90 else "behind"), None
        else:
            front = math.degrees(math.asin(balance))      # equal-power panning: (R - L) / (R + L) = sin(azimuth)
            behind = math.copysign(180.0, front or 1.0) - front
            facing = self.facing
            angle, mirror = (behind, None) if facing == "behind" else (front, None if facing else behind)
        side = "right" if 15 <= angle <= 165 else "left" if -165 <= angle <= -15 else "middle"
        return {"heard": True, "since": round(since, 1), "match": round(self.match, 2),
                "level_db": round(self.level, 1),
                "proximity": round(max(0.0, min(1.0, 1 + self.level / self.range_db)), 2),
                "balance": round(balance, 2), "angle": round(angle), "mirror": None if mirror is None else round(mirror),
                "facing": facing, "side": side, "direction": direction(angle, facing), "trend": self.trend()}


# ---- the learned profile ------------------------------------------------------------------------

def _rounded(a) -> list:
    """An array as nested lists, five significant digits (the file stays small; nothing hangs on more)."""
    a = np.asarray(a, dtype=np.float64)
    return [float(f"{v:.5g}") for v in a] if a.ndim == 1 else [_rounded(r) for r in a]


def _array(value, shapes: tuple) -> np.ndarray | None:
    """A saved array, if it has one of ``shapes`` and holds finite, non-negative levels."""
    try:
        a = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    return a if a.shape in shapes and np.isfinite(a).all() and (a >= 0).all() else None


_ROWS = ((2, BANDS), (3, BANDS))
_BINS = _HI - _LO


def _sample_from(data) -> dict | None:
    """A sample as saved, checked; None when it does not fit this version's bands."""
    if not isinstance(data, dict) or data.get("kind") not in ("background", "cube", "other") \
            or not isinstance(data.get("id"), str):
        return None
    out = {"kind": data["kind"], "id": data["id"][:16], "at": data.get("at") if isinstance(data.get("at"), str) else None,
           "quality": data.get("quality") if isinstance(data.get("quality"), dict) else None}
    if data["kind"] == "background":
        levels, spread = _array(data.get("levels"), _ROWS), _array(data.get("spread"), _ROWS)
        if levels is None or spread is None or spread.shape != levels.shape:
            return None
        return {**out, "levels": levels, "spread": spread}
    excess = _array(data.get("excess"), _ROWS)
    if excess is None or not excess[:2].any():
        return None
    tonal = None
    if data.get("tonal") is not None:
        try:
            tonal = np.zeros(_BINS)
            for k, v in data["tonal"]:
                if isinstance(k, int) and 0 <= k < _BINS and isinstance(v, (int, float)) and math.isfinite(v) and v >= 0:
                    tonal[k] = v
        except (TypeError, ValueError):
            tonal = None
        if tonal is not None and not tonal.any():
            tonal = None
    out.update(excess=excess, tonal=tonal)
    if data["kind"] == "cube":
        raw = data["chunks"] if isinstance(data.get("chunks"), list) else []
        chunks = [c for c in (_array(c, _ROWS) for c in raw) if c is not None]
        out.update(facing=data.get("facing") if data.get("facing") in FACINGS else "ahead", chunks=chunks,
                   chunk_kind="notes" if data.get("chunk_kind") == "notes" and tonal is not None else "bands")
    return out


def _sample_to(sample: dict) -> dict:
    out = {k: sample.get(k) for k in ("kind", "id", "at", "quality")}
    if sample["kind"] == "background":
        return {**out, "levels": _rounded(sample["levels"]), "spread": _rounded(sample["spread"])}
    tonal = sample.get("tonal")
    out.update(excess=_rounded(sample["excess"]),
               tonal=None if tonal is None else [[int(k), float(f"{tonal[k]:.5g}")] for k in np.nonzero(tonal)[0]])
    if sample["kind"] == "cube":
        out.update(facing=sample.get("facing", "ahead"), chunk_kind=sample.get("chunk_kind", "bands"),
                   chunks=[_rounded(c) for c in sample.get("chunks") or ()])
    return out


def _from_version_1(data: dict) -> list:
    """The one background and jingle the radar learned before samples (0.2.323), as samples."""
    learned = data.get("learned") if isinstance(data.get("learned"), dict) else {}
    samples = []
    background = _array(data.get("background"), ((2, BANDS),))
    if background is not None:
        samples.append({"kind": "background", "id": "v1-background", "at": learned.get("background"),
                        "quality": None, "levels": background, "spread": np.full_like(background, MARGIN)})
    jingle = _array(data.get("jingle"), ((BANDS,),))
    if jingle is not None and jingle.any():
        samples.append({"kind": "cube", "id": "v1-cube", "at": learned.get("cube"), "facing": "ahead",
                        "quality": data.get("quality") if isinstance(data.get("quality"), dict) else None,
                        "excess": np.stack([jingle / 2, jingle / 2]), "tonal": None, "chunks": [], "chunk_kind": "bands"})
    return samples


def load_profile(path: Path) -> list:
    """The saved samples, oldest first; none when there is no profile or it does not fit this version's
    bands. A profile from before samples becomes a background and a cube sample."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or data.get("rate") != RATE or data.get("bands") != BANDS:
        return []
    if data.get("version") == 1:
        return _from_version_1(data)
    if data.get("version") != PROFILE_VERSION or not isinstance(data.get("samples"), list):
        return []
    return [s for s in (_sample_from(d) for d in data["samples"]) if s is not None]


def save_profile(path: Path, samples: list) -> None:
    data = {"version": PROFILE_VERSION, "rate": RATE, "bands": BANDS,
            "band_hz": [int(round(float(f))) for f in band_centres()], "fine_hz": [_LO * RATE / WINDOW, RATE / WINDOW],
            "samples": [_sample_to(s) for s in samples]}
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
    """What the default output plays, in blocks of :data:`HOP` frames (Windows, WASAPI loopback through
    ``soundcard``): stereo, or a surround output's own channels (quad, 5.1, 7.1), so that what it
    plays behind can be heard. Re-opened when the default output changes (headphones plugged in).

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
        try:
            native = int(speaker.channels)
        except Exception:
            native = 2
        self._rec = None
        if native in (4, 6, 8):
            try:
                self._rec = mic.recorder(samplerate=RATE, channels=native, blocksize=HOP)
                self._rec.__enter__()
            except Exception:
                self._rec = None
        if self._rec is None:
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
    ``path`` is where the learned samples are kept."""

    RETRY_S = 3.0

    def __init__(self, path: Path, source=LoopbackSource):
        self.path = Path(path)
        self._source_factory = source
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self.samples = load_profile(self.path)
        self.model = Model(self.samples)
        self.enabled = False
        self.sensitivity = SENSITIVITY[2]
        self.device = None
        self.channels = None
        self.error = None
        self.listening = False
        self.input_db = None
        self._learn = None            # {"kind", "facing", "starts" (monotonic), "steps", "levels", "fines"}
        self.last_learn = None        # {"kind", "facing", "ok", "message"}
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

    def learn(self, kind: str, delay: float = COUNTDOWN_S, seconds: float | None = None, facing: str = "ahead") -> None:
        """Listen for a sample: of the background, of the cube's jingle (``facing`` it, or with it
        behind), or of another sound that is not a cube."""
        if kind not in LEARN_S:
            raise ValueError("learn background, cube or other")
        if facing not in FACINGS:
            raise ValueError("facing must be ahead or behind")
        steps = max(1, int(round((LEARN_S[kind] if seconds is None else seconds) * RATE / HOP)))
        with self._lock:
            self._learn = {"kind": kind, "facing": facing, "starts": time.monotonic() + max(0.0, delay), "steps": steps,
                           "levels": [], "fines": []}
            self.last_learn = None
        self._ensure_thread()
        self._wake.set()

    def cancel(self) -> None:
        with self._lock:
            self._learn = None
        self._wake.set()

    def forget(self, sample_id: str) -> bool:
        """Drop one sample; False when there is none by that id."""
        with self._lock:
            kept = [s for s in self.samples if s["id"] != sample_id]
            if len(kept) == len(self.samples):
                return False
            self.samples, self.model, self.last_learn = kept, Model(kept), None
            self._reset_matching()
            samples = list(kept)
        if samples:
            save_profile(self.path, samples)
        else:
            self.path.unlink(missing_ok=True)
        return True

    def clear(self) -> None:
        with self._lock:
            self.samples, self.model, self.last_learn = [], Model(), None
            self._reset_matching()
        self.path.unlink(missing_ok=True)

    def state(self) -> dict:
        with self._lock:
            learning = None
            if self._learn is not None:
                wait = self._learn["starts"] - time.monotonic()
                base = {"kind": self._learn["kind"], "facing": self._learn["facing"]}
                learning = ({**base, "phase": "countdown", "seconds": round(wait, 1)} if wait > 0 else
                            {**base, "phase": "listening",
                             "seconds": round((self._learn["steps"] - len(self._learn["levels"])) * HOP / RATE, 1)})
            model = self.model
            newest = {}
            for s in self.samples:
                newest[s["kind"]] = s.get("at")
            cubes = [s for s in self.samples if s["kind"] == "cube"]
            reference = max(cubes, key=lambda s: model.levels_db.get(s["id"], -99.0), default=None)
            out = {"supported": supported(), "enabled": self.enabled, "listening": self.listening,
                   "device": self.device, "channels": self.channels, "error": self.error,
                   "sensitivity": self.sensitivity, "ready": model.ready,
                   "learned": {"background": newest.get("background"), "cube": newest.get("cube")},
                   "quality": None if reference is None else reference.get("quality"),
                   "samples": [{"id": s["id"], "kind": s["kind"], "facing": s.get("facing"), "at": s.get("at"),
                                "level_db": None if s["id"] not in model.levels_db else round(model.levels_db[s["id"]]),
                                "notes": s.get("tonal") is not None if s["kind"] != "background" else None,
                                "alike": s["id"] in model.alike} for s in self.samples],
                   "model": {"backgrounds": sum(s["kind"] == "background" for s in self.samples),
                             "cubes": len(cubes), "ahead": sum(s.get("facing") == "ahead" for s in cubes),
                             "behind": sum(s.get("facing") == "behind" for s in cubes),
                             "others": sum(s["kind"] == "other" for s in self.samples), "notes": model.notes is not None,
                             "front_back": model.front_status,
                             "accuracy": None if model.front is None else model.front.accuracy,
                             "range_db": round(model.range_db)},
                   "learning": learning, "last_learn": self.last_learn,
                   "last_learn_s": None if self.last_learn is None or self._learned_at is None
                   else round(time.monotonic() - self._learned_at, 1),
                   "input_db": self.input_db}
            out.update(self.track.view() if self.matcher is not None else Track().view())
            return out

    # -- the worker --
    def _reset_matching(self) -> None:
        self.matcher = Matcher(self.model, self.sensitivity) if self.model.ready else None
        self.track = Track(self.model.range_db)

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
                        self.last_learn = {"kind": self._learn["kind"], "facing": self._learn["facing"], "ok": False,
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
        ring = fold = None
        while self._wanted():
            if getattr(source, "stale", lambda: False)():
                return                                     # the default output changed: open the new one
            block = np.asarray(source.read(), dtype=np.float32)
            if block.ndim == 1:
                block = block[:, None]
            if not len(block):
                continue
            if ring is None or ring.shape[1] != block.shape[1]:
                ring, fold = np.zeros((WINDOW, block.shape[1]), dtype=np.float32), layout(block.shape[1])
                with self._lock:
                    self.channels = int(block.shape[1])
            ring = np.concatenate([ring, block])[-WINDOW:]
            power = spectrum(ring)
            fine = fold @ power
            self._step(bands(fine), fine, len(block) / RATE, bands(power) if len(power) >= 4 else None)

    def _step(self, levels: np.ndarray, fine: np.ndarray, dt: float, channels: np.ndarray | None = None) -> None:
        with self._lock:
            total = float(levels.sum())
            self.input_db = round(10 * math.log10(total), 1) if total > 0 else None
            if self._learn is not None and time.monotonic() >= self._learn["starts"]:
                self._learn["levels"].append(levels)
                self._learn["fines"].append(fine)
                if len(self._learn["levels"]) >= self._learn["steps"]:
                    self._finish_learning()
            if self.matcher is not None and self.enabled:
                self.track.add(self.matcher.step(levels, fine, channels), dt)

    def _finish_learning(self) -> None:
        learn, self._learn = self._learn, None
        kind, facing = learn["kind"], learn["facing"]
        model = self.model
        try:
            if kind == "background":
                sample = learn_background(learn["levels"])
            elif kind == "cube":
                sample = learn_jingle(learn["levels"], learn["fines"], model.latest_background, facing, model)
            else:
                sample = learn_other(learn["levels"], learn["fines"], model.latest_background)
        except LearnError as err:
            self._learned(kind, facing, False, str(err))
            return
        sample.update(id=uuid.uuid4().hex[:8], at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        samples = self.samples + [sample]
        group = facing if kind == "cube" else kind
        same = [s for s in samples if (s.get("facing") if s["kind"] == "cube" else s["kind"]) == group]
        drop = {s["id"] for s in same[:max(0, len(same) - KEEP[group])]}
        model = Model([s for s in samples if s["id"] not in drop])
        if sample["id"] in model.alike:
            self._learned(kind, facing, False, "That sounds the same as the cube to the radar, so it could not tell them "
                                               "apart: not kept.")
            return
        self.samples, self.model = model.samples, model
        self._learned(kind, facing, True, self._message(sample))
        self._reset_matching()
        try:
            save_profile(self.path, self.samples)
        except OSError as err:
            self.last_learn["message"] += f" (not saved: {err})"

    def _learned(self, kind: str, facing: str, ok: bool, message: str) -> None:
        self.last_learn = {"kind": kind, "facing": facing, "ok": ok, "message": message}
        self._learned_at = time.monotonic()

    def _message(self, sample: dict) -> str:
        model, kind = self.model, sample["kind"]
        if kind == "background":
            n = sum(s["kind"] == "background" for s in model.samples)
            return (f"Background learned ({n} sample{'s' if n != 1 else ''})."
                    + ("" if model.ready else " Now learn the cube's sound beside one."))
        if kind == "other":
            return "Learned a sound that is not a cube: the radar will not take it for one."
        cubes = [s for s in model.samples if s["kind"] == "cube"]
        q = sample["quality"]
        if len(cubes) == 1:
            text = (f"Cube sound learned: it stood {q['snr_db']} dB over the background, loudest near {q['peak_hz']} Hz"
                    + (", with its notes." if sample.get("tonal") is not None else "."))
        else:
            db = model.levels_db.get(sample["id"], 0.0)
            text = (f"Cube sound learned {'with it behind you' if sample['facing'] == 'behind' else 'facing it'}"
                    + (f", {round(-db)} dB below the loudest" if db <= -1.5 else "") + f" ({len(cubes)} cube samples).")
        status = {"learned": "It now tells ahead from behind.",
                  "alike": "Ahead and behind sound alike to it: turn on the game's 3D audio, then learn both again a "
                           "few steps from the cube.",
                  "need_ahead": "Now learn it facing the cube from the same spot.",
                  "need_more": "Too little of the jingle was heard to tell ahead from behind: learn both again a little "
                               "closer."}.get(model.front_status)
        return text + (" " + status if status and (sample["facing"] == "behind" or model.front_status == "learned") else "")
