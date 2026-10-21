"""The Hidden Cube radar (0.2.323; samples, notes and a full circle since 0.2.324): it hears a Hidden
Cube's jingle in the game's sound once taught it in samples, and shows on the overlay where the cube is
around the player (its stereo balance, and ahead or behind from what the game's 3D audio or a surround
output does to it) and how near it is (loudness). The audio here is synthetic: a sparkle of bell notes
for the jingle, pink noise with footstep-like bursts for the background, and a voice, music, other
chimes and noise bursts that must not match; a simple head stands in for the game's 3D audio and a
pairwise-panned 7.1 mix for a surround output. Off by default; Windows only; nothing is recorded or
uploaded."""
import itertools
import json
import math
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from aion2calc.app import radar as R
from aion2calc.app import hotkeys, server

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
RATE = R.RATE
NOTES = (2093.0, 2637.0, 3136.0, 3951.0, 4699.0)
FEATHER = tuple(f * 2 ** (1 / 12) for f in NOTES)       # the same bells a semitone up
_IDS = itertools.count()


# ---- synthetic sound -----------------------------------------------------------------------------

def _pink(n, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / RATE)
    f[0] = 1
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return x / np.std(x)


def background(seconds, rng, level=0.02):
    n = int(seconds * RATE)
    out = np.stack([_pink(n, rng), _pink(n, rng)], axis=1) * level
    t = 0
    while True:                                   # footsteps: short broadband bursts
        t += int(rng.uniform(0.4, 1.2) * RATE)
        if t >= n:
            return out
        m = min(n - t, int(0.06 * RATE))
        out[t:t + m] += rng.standard_normal((m, 2)) * level * 3 * np.exp(-np.arange(m) / (0.015 * RATE))[:, None]


def _bell(freq, seconds=0.6):
    t = np.arange(int(seconds * RATE)) / RATE
    env = np.exp(-t / 0.18) * np.minimum(1, t / 0.003)
    return env * sum(w * np.sin(2 * math.pi * freq * p * t) for p, w in ((1, 1.0), (2.76, 0.45), (5.4, 0.2))
                     if freq * p < RATE / 2)


def _pan(mono, pan):
    th = math.radians((pan + 90) / 2)
    return np.stack([mono * math.cos(th), mono * math.sin(th)], axis=1)


def jingle(seconds, rng, level=0.05, pan=0.0, notes=NOTES, gap=(0.10, 0.25), ramp=None):
    """A sparkle of bell notes panned to ``pan`` degrees (equal-power); ``ramp`` (from, to) fades its
    level across the clip, as walking towards or away from a cube does."""
    n = int(seconds * RATE)
    mono = np.zeros(n)
    t = 0.0
    while t < seconds:
        x = _bell(notes[rng.integers(len(notes))] * rng.uniform(0.995, 1.005))
        i = int(t * RATE)
        m = min(len(x), n - i)
        mono[i:i + m] += x[:m]
        t += rng.uniform(*gap)
    mono *= level / np.sqrt(np.mean(mono ** 2))
    if ramp:
        mono *= np.geomspace(ramp[0], ramp[1], n)
    return _pan(mono, pan)


def clip(seconds, rng, level=0.05, period=1.4):
    """A fixed run of bell notes looped every ``period`` seconds, as a game plays a recorded sound."""
    pattern = np.random.default_rng(99)
    run = [(t, NOTES[pattern.integers(len(NOTES))]) for t in np.arange(0, period - 0.2, 0.17)]
    n = int(seconds * RATE)
    mono = np.zeros(n)
    start = rng.uniform(0, period)
    for k in range(-1, int(seconds / period) + 2):
        for t, f in run:
            i = int((start + (k - 1) * period + t) * RATE)
            if 0 <= i < n:
                x = _bell(f)
                m = min(len(x), n - i)
                mono[i:i + m] += x[:m]
    mono *= level / np.sqrt(np.mean(mono ** 2))
    return _pan(mono, 0)


def head(stereo, az, cues=True):
    """``stereo``'s sound from ``az`` degrees (0 ahead, 90 right) through a simple head: the far ear
    shadowed more at high frequencies and, with ``cues``, the outer ear's dulling of a sound behind and
    lift of one ahead (what a game's 3D audio adds)."""
    mono = stereo.mean(axis=1)
    spec = np.fft.rfft(mono)
    f = np.fft.rfftfreq(len(mono), 1 / RATE)
    th = math.radians(az)
    ild = 20 * math.sin(th) * (f / (f + 1500)) * 0.75
    common = 0.0
    if cues:
        common = (-8 * ((1 - math.cos(th)) / 2) * (f ** 2 / (f ** 2 + 3000 ** 2))
                  + 3 * ((1 + math.cos(th)) / 2) * np.exp(-((f - 4500) / 1500) ** 2))
    return np.stack([np.fft.irfft(spec * 10 ** ((common - ild / 2) / 20), len(mono)),
                     np.fft.irfft(spec * 10 ** ((common + ild / 2) / 20), len(mono))], axis=1)


def surround(stereo, az, rng=None):
    """``stereo``'s sound from ``az`` degrees as a 7.1 output plays it, panned between the two nearest
    speakers (front ±30°, sides ±90°, backs ±150°; Windows' channel order), with a background on the
    front pair when ``rng`` is given."""
    mono = stereo.mean(axis=1) * math.sqrt(2)
    order = sorted({0: -30, 1: 30, 4: -150, 5: 150, 6: -90, 7: 90}.items(), key=lambda kv: kv[1] % 360)
    out = np.zeros((len(mono), 8))
    for (c1, a1), (c2, a2) in zip(order, order[1:] + order[:1]):
        span, off = (a2 - a1) % 360, (az - a1) % 360
        if off <= span:
            out[:, c1] = mono * math.cos(off / span * math.pi / 2)
            out[:, c2] = mono * math.sin(off / span * math.pi / 2)
            break
    if rng is not None:
        out[:, :2] += background(len(mono) / RATE, rng)
    return out


# ---- the radar's own steps -----------------------------------------------------------------------

def steps(audio):
    """Each step as the worker computes it: its band levels, fine spectrum and, from a surround output,
    each channel's band levels."""
    audio = np.asarray(audio, dtype=np.float32)
    fold = R.layout(audio.shape[1])
    ring = np.zeros((R.WINDOW, audio.shape[1]), dtype=np.float32)
    out = []
    for i in range(0, len(audio) - R.HOP + 1, R.HOP):
        ring = np.concatenate([ring, audio[i:i + R.HOP]])[-R.WINDOW:]
        power = R.spectrum(ring)
        fine = fold @ power
        out.append((R.bands(fine), fine, R.bands(power) if len(power) >= 4 else None))
    return out


def learn(kind, audio, samples=(), facing="ahead"):
    """The samples with one more, learned from ``audio`` as the radar learns it."""
    levels, fines = zip(*[(lv, fn) for lv, fn, _ in steps(audio)])
    model = R.Model(list(samples))
    sample = (R.learn_background(list(levels)) if kind == "background"
              else R.learn_jingle(list(levels), list(fines), model.latest_background, facing, model) if kind == "cube"
              else R.learn_other(list(levels), list(fines), model.latest_background))
    sample["id"] = f"s{next(_IDS)}"
    return list(samples) + [sample]


def shown(model, audio, sensitivity=5, matcher=None):
    matcher, track = matcher or R.Matcher(model, sensitivity), R.Track(model.range_db)
    views = []
    for levels, fine, channels in steps(audio):
        track.add(matcher.step(levels, fine, channels))
        views.append(track.view())
    return views


def heard_share(views):
    return sum(v["heard"] for v in views) / len(views)


def bands_only(samples):
    """The same samples without the jingle's notes: what its bands alone hear."""
    return [{**s, "tonal": None, "chunk_kind": "bands"} if s["kind"] == "cube" else s for s in samples]


@pytest.fixture(scope="module")
def taught():
    rng = np.random.default_rng(4)
    samples = learn("background", background(4, rng))
    return learn("cube", background(6, rng) + jingle(6, rng, level=0.06), samples)


@pytest.fixture(scope="module")
def learned(taught):
    return R.Model(taught)


# ---- matching ------------------------------------------------------------------------------------

def test_learning_finds_the_jingles_bands_and_notes(taught, learned):
    quality = taught[1]["quality"]
    assert quality["snr_db"] > 15 and quality["bands"] <= 8 and 1800 <= quality["peak_hz"] <= 5000 and quality["notes"] > 10
    weights, region = learned.weights, learned.region
    assert weights.max() == 1.0 and set(np.nonzero(weights)[0]) <= set(np.nonzero(region)[0])
    assert R.band_centres()[weights > 0].min() > 1500                # nothing of it down where voices and bass sit
    peaks = np.fft.rfftfreq(R.WINDOW, 1 / RATE)[R._LO:R._HI][learned.notes >= 0.5]
    partials = [f * p for f in NOTES for p in (1, 2.76, 5.4)]
    assert len(peaks) and all(min(abs(f / q - 1) for q in partials) < 0.025 for f in peaks)   # the bells' notes


def test_the_radar_hears_the_jingle_and_its_side(learned):
    rng = np.random.default_rng(7)
    for pan, side in ((45, "right"), (-60, "left"), (0, "middle")):
        views = shown(learned, background(8, rng) + jingle(8, rng, level=0.02, pan=pan))[60:]
        heard = [v for v in views if v["heard"]]
        assert len(heard) > 0.9 * len(views)
        assert abs(np.median([v["angle"] for v in heard]) - pan) <= 8 and heard[-1]["side"] == side
        assert -15 < np.median([v["level_db"] for v in heard]) < -6               # learned at 3x the level: -9.5 dB
        assert 0.45 < np.median([v["proximity"] for v in heard]) < 0.8
        # stereo alone cannot tell ahead from behind: the circle shows both places the cube can be
        last = heard[-1]
        mirror = math.copysign(180, last["angle"] or 1) - last["angle"]
        assert last["facing"] is None and abs((last["mirror"] - mirror + 180) % 360 - 180) <= 1
        assert last["direction"].endswith("ahead or behind")


def test_its_notes_hear_a_cube_farther_away_and_a_buried_one_is_not_guessed(taught, learned):
    rng = np.random.default_rng(8)
    far = background(8, rng) + jingle(8, rng, level=0.003, pan=30)       # 26 dB below the learned jingle
    views = shown(learned, far)[60:]
    assert heard_share(views) > 0.8
    assert np.median([v["proximity"] for v in views if v["heard"]]) < 0.25
    assert heard_share(shown(R.Model(bands_only(taught)), far)[60:]) < 0.1   # its bands alone lose it
    buried = background(8, rng) + jingle(8, rng, level=0.001, pan=30)
    assert not any(v["heard"] for v in shown(learned, buried))


@pytest.mark.parametrize("name", ["background", "voice", "loud voice", "music", "another chime",
                                  "a chime 3 % off its notes", "noise bursts"])
def test_other_sounds_are_not_a_cube(learned, name):
    rng = np.random.default_rng(9)
    n = 10 * RATE
    other = {"background": lambda: background(20, rng, level=0.06),
             "voice": lambda: background(10, rng) + voice(10),
             "loud voice": lambda: background(10, rng) + voice(10, level=0.2),
             "music": lambda: background(10, rng) + music(10),
             "another chime": lambda: background(10, rng) + jingle(10, rng, level=0.2, notes=(880.0, 1318.5, 1760.0), gap=(0.3, 0.6)),
             "a chime 3 % off its notes": lambda: background(10, rng) + jingle(10, rng, level=0.1, notes=(2093.0 * 1.03, 3136.0 * 0.97),
                                                                               gap=(0.2, 0.5)),
             "noise bursts": lambda: background(10, rng) + rng.standard_normal((n, 2)) * 0.1 * (np.arange(n) % RATE < RATE // 10)[:, None],
             }[name]()
    assert not any(v["heard"] for v in shown(learned, other))


def test_a_feather_a_semitone_off_is_told_apart_by_its_notes(taught, learned):
    rng = np.random.default_rng(19)
    feather = background(10, rng) + jingle(10, rng, level=0.05, notes=FEATHER)
    assert not any(v["heard"] for v in shown(learned, feather))
    assert heard_share(shown(R.Model(bands_only(taught)), feather)) > 0.2      # its bands alone take it for a cube


def voice(seconds, level=0.05):
    t = np.arange(int(seconds * RATE)) / RATE
    phase = 2 * math.pi * np.cumsum(140 * (1 + 0.1 * np.sin(2 * math.pi * 3 * t))) / RATE
    x = sum((sum(math.exp(-((140 * h - f) / 150) ** 2) for f in (500, 1500, 2500)) + 0.02) * np.sin(h * phase)
            for h in range(1, 40))
    x = x * (0.5 + 0.5 * np.sin(2 * math.pi * 4 * t) ** 2)
    x *= level / np.sqrt(np.mean(x ** 2))
    return np.stack([x, x * 0.8], axis=1)


def music(seconds, level=0.2):
    t = np.arange(int(seconds * RATE)) / RATE
    x = sum(np.sin(2 * math.pi * f * t) * (0.6 + 0.4 * np.sin(2 * math.pi * 0.3 * t + k)) + 0.3 * np.sin(4 * math.pi * f * t)
            for k, f in enumerate((220, 277.2, 329.6, 440, 554.4)))
    x *= level / np.sqrt(np.mean(x ** 2))
    return np.stack([x, x], axis=1)


def test_music_does_not_hide_the_jingle(learned):
    rng = np.random.default_rng(10)
    views = shown(learned, background(8, rng) + jingle(8, rng, level=0.02, pan=30) + music(8, level=0.05))[60:]
    assert heard_share(views) > 0.8


def test_louder_is_closer_and_the_trend_says_so(learned):
    rng = np.random.default_rng(11)
    closer = shown(learned, background(6, rng) + jingle(6, rng, level=0.01, pan=20, ramp=(0.3, 3.0)))
    assert closer[-1]["heard"] and closer[-1]["trend"] == "louder"
    away = shown(learned, background(6, rng) + jingle(6, rng, level=0.01, pan=20, ramp=(3.0, 0.3)))
    assert any(v["trend"] == "quieter" for v in away[-60:])


def test_the_sensitivity_trades_reach_for_strictness():
    for thresholds in (R.thresholds, R.note_thresholds):
        strict, default, loose = (thresholds(s) for s in (1, 5, 10))
        assert strict[0] > default[0] > loose[0] and strict[1] > default[1] > loose[1]
        assert thresholds(0) == strict and thresholds(99) == loose


def test_a_cube_stays_on_the_radar_between_jingles_then_goes():
    track = R.Track()
    hit = {"match": 0.9, "level": 0.5, "balance": 0.5, "heard": True}
    miss = {"match": 0.1, "level": 0.0, "balance": 0.0, "heard": False}
    track.add(hit)
    assert not track.view()["heard"]                                # one matching step is not a jingle yet
    for _ in range(3):
        track.add(hit)
    assert track.view()["heard"]
    for _ in range(int(2.0 * RATE / R.HOP)):
        track.add(miss)
    assert track.view()["heard"]                                    # held between the bursts
    for _ in range(int(1.0 * RATE / R.HOP)):
        track.add(miss)
    view = track.view()
    assert not view["heard"] and view["since"] > R.HOLD_S


def test_ahead_or_behind_is_told_after_a_while_and_flips_only_on_clear_evidence():
    track = R.Track()

    def heard_for(seconds, front):
        for _ in range(int(seconds * RATE / R.HOP)):
            track.add({"match": 0.9, "level": 0.5, "balance": 0.5, "heard": True, "front": front})

    heard_for(1.0, 1.0)
    assert track.view()["facing"] is None and track.view()["mirror"] == 150     # a second is too little to tell
    heard_for(1.0, 1.0)
    view = track.view()
    assert view["facing"] == "ahead" and view["mirror"] is None and view["direction"] == "ahead to your right"
    heard_for(0.3, 0.0)                                             # a moment of doubt does not flip it
    assert track.view()["facing"] == "ahead"
    heard_for(2.0, -1.0)
    view = track.view()
    assert view["facing"] == "behind" and view["angle"] == 150 and view["direction"] == "behind you to the right"


def test_the_direction_in_words():
    assert R.direction(0, "ahead") == "ahead" and R.direction(180, "behind") == "behind you"
    assert R.direction(40, "ahead") == "ahead to your right" and R.direction(-90, "ahead") == "to your left"
    assert R.direction(-140, "behind") == "behind you to the left"
    assert R.direction(40, None) == "to your right, ahead or behind" and R.direction(5, None) == "ahead or behind"
    assert R.direction(-80, None) == "to your left"


# ---- several samples -----------------------------------------------------------------------------

def test_background_samples_set_how_much_each_band_must_rise(taught):
    rng = np.random.default_rng(20)
    places = learn("background", background(4, rng, level=0.04), learn("background", background(4, rng)))
    assert all(s["spread"].shape == (2, R.BANDS) and (s["spread"] >= 1).all() for s in places)
    model = R.Model(places + taught[1:])
    assert model.floor.shape == (2, R.BANDS) and np.allclose(model.latest_background, places[-1]["levels"])
    assert ((model.margin >= R.MARGIN) & (model.margin <= R.MARGIN_MAX)).all()
    assert model.margin.max() > R.MARGIN                            # the footsteps make some bands vary more


def test_a_sample_farther_away_sets_the_rim_and_one_unlike_the_cube_is_refused(taught):
    rng = np.random.default_rng(21)
    samples = learn("cube", background(8, rng) + jingle(8, rng, level=0.004), taught)      # 24 dB below, far off
    model = R.Model(samples)
    assert model.levels_db[samples[-1]["id"]] < -18 and model.range_db > R.RANGE_DB
    assert R.Track(model.range_db).range_db == model.range_db
    with pytest.raises(R.LearnError, match="did not sound like the cube"):
        learn("cube", background(8, rng) + jingle(8, rng, level=0.05, notes=FEATHER), taught)


def test_a_sound_learned_as_not_a_cube_is_no_longer_taken_for_one(taught):
    rng = np.random.default_rng(22)
    feather_sample = learn("other", background(6, rng) + jingle(6, rng, level=0.05, notes=FEATHER), taught)[-1]
    rng = np.random.default_rng(31)
    feather = background(10, rng) + jingle(10, rng, level=0.05, notes=FEATHER)
    cube = background(10, rng) + jingle(10, rng, level=0.01, pan=-40)
    plain = bands_only(taught)                                      # its bands alone take a feather for a cube...
    assert heard_share(shown(R.Model(plain), feather)) > 0.2
    taught_feather = R.Model(plain + [feather_sample])              # ...until a feather is learned as not one
    assert not taught_feather.alike and len(taught_feather.others) == 1
    assert not any(v["heard"] for v in shown(taught_feather, feather))
    assert heard_share(shown(taught_feather, cube)[60:]) > 0.9


def test_a_chime_sharing_some_of_the_cubes_notes_is_told_by_the_notes_it_alone_plays(taught, learned):
    rng = np.random.default_rng(40)
    shared = (2093.0, 3136.0, 2349.3, 2793.8, 3520.0)                # two of the cube's notes and three others
    sample = learn("other", background(6, rng) + jingle(6, rng, level=0.05, notes=shared), taught)[-1]
    rng = np.random.default_rng(41)
    chime = background(10, rng) + jingle(10, rng, level=0.05, notes=shared)
    cube = background(10, rng) + jingle(10, rng, level=0.01, pan=-40)
    assert heard_share(shown(learned, chime)) > 0.8                  # it plays the cube's notes now and then
    taught_chime = R.Model(list(taught) + [sample])
    assert not taught_chime.alike and len(taught_chime.others) == 1
    settled = int(4 * RATE / R.HOP)                                  # once its own notes have rung (and the hold ran out)
    assert not any(v["heard"] for v in shown(taught_chime, chime)[settled:])
    assert heard_share(shown(taught_chime, cube)[60:]) > 0.9


def test_the_cubes_own_sound_cannot_be_learned_as_not_a_cube(taught):
    rng = np.random.default_rng(23)
    samples = learn("other", background(6, rng) + jingle(6, rng, level=0.05), taught)
    model = R.Model(samples)
    assert model.alike == [samples[-1]["id"]] and not model.others        # it would hide the cube: left out


# ---- ahead or behind -----------------------------------------------------------------------------

def _ahead_and_behind(rng, cues):
    samples = learn("background", background(4, rng))
    for level, az, facing in ((0.08, 0, "ahead"), (0.03, 0, "ahead"), (0.03, 180, "behind")):
        samples = learn("cube", background(8, rng) + head(clip(8, rng, level), az, cues), samples, facing)
    return R.Model(samples)


def test_with_3d_audio_samples_ahead_and_behind_tell_where_the_cube_is():
    rng = np.random.default_rng(24)
    model = _ahead_and_behind(rng, cues=True)
    assert model.front_status == "learned" and model.front.accuracy >= R.FrontBack.ACCURACY
    for az in (30, 150, -45, -135):
        last = [v for v in shown(model, background(8, rng) + head(clip(8, rng, 0.02), az)) if v["heard"]][-1]
        assert last["facing"] == ("ahead" if abs(az) < 90 else "behind") and last["mirror"] is None
        assert abs(last["angle"] - az) <= 20 and last["direction"].startswith("behind" if abs(az) > 90 else "ahead")


def test_without_3d_audio_ahead_and_behind_sound_alike_and_both_places_are_shown():
    rng = np.random.default_rng(25)
    model = _ahead_and_behind(rng, cues=False)
    assert model.front_status == "alike" and model.front is None
    last = [v for v in shown(model, background(6, rng) + head(clip(6, rng, 0.02), 150, cues=False)) if v["heard"]][-1]
    assert last["facing"] is None and abs(last["angle"] - 30) <= 20 and abs(last["mirror"] - 150) <= 20


def test_a_surround_output_tells_the_direction_from_its_speakers():
    rng = np.random.default_rng(26)
    quiet = np.zeros((4 * RATE, 8))
    quiet[:, :2] = background(4, rng)
    samples = learn("cube", surround(jingle(8, rng, level=0.06), 0, rng), learn("background", quiet))
    model = R.Model(samples)
    assert model.floor.shape == (3, R.BANDS) and not model.surround   # the jingle ahead played on the front pair only
    matcher = R.Matcher(model)
    ahead = [v for v in shown(model, surround(jingle(6, rng, level=0.02), 0, rng), matcher=matcher) if v["heard"]][-1]
    assert ahead["facing"] is None                                  # nothing behind yet: it could be either
    for az in (120, 30, -60, 180, -135):                            # once it has played behind, the speakers say where
        last = [v for v in shown(model, surround(jingle(6, rng, level=0.02), az, rng), matcher=matcher) if v["heard"]][-1]
        assert last["facing"] == ("ahead" if abs(az) < 90 else "behind") and last["mirror"] is None
        assert abs((last["angle"] - az + 180) % 360 - 180) <= 15


def test_surround_channels_fold_into_left_right_and_behind():
    assert R.layout(2).tolist() == [[1, 0], [0, 1]] and R.layout(1).tolist() == [[1], [1]]
    fold = R.layout(8)                                              # FL FR FC LFE BL BR SL SR
    assert fold.shape == (3, 8) and fold[:, 3].sum() == 0 and fold[0, 2] == fold[1, 2] == 0.5
    assert fold[0].tolist() == [1, 0, 0.5, 0, 1, 0, 1, 0] and fold[2].tolist() == [0, 0, 0, 0, 1, 1, 0.5, 0.5]
    assert R.layout(6)[2].tolist() == [0, 0, 0, 0, 1, 1] and R.layout(4)[2].tolist() == [0, 0, 1, 1]
    assert R.layout(5).shape == (2, 5) and R.speakers(2) is None
    assert np.allclose(R.speakers(8)[4], [math.cos(math.radians(-150)), math.sin(math.radians(-150))])
    assert not R.speakers(8)[3].any()                               # the LFE has no direction


# ---- learning ------------------------------------------------------------------------------------

def test_learning_without_a_jingle_says_what_to_change():
    rng = np.random.default_rng(12)
    samples = learn("background", background(4, rng))
    with pytest.raises(R.LearnError, match="did not stand out|Nothing louder"):
        learn("cube", background(6, rng), samples)
    noise = rng.standard_normal((6 * RATE, 2)) * 0.2                 # a fight's or a waterfall's roar
    with pytest.raises(R.LearnError, match="whole range"):
        learn("cube", noise, samples)


def test_without_a_background_the_quiet_steps_stand_in_for_it():
    rng = np.random.default_rng(13)
    quality = learn("cube", background(6, rng) + jingle(6, rng, level=0.06, gap=(0.3, 0.6)))[-1]["quality"]
    assert quality["snr_db"] > 10 and quality["bands"] <= 8


def test_the_samples_round_trip_and_a_foreign_profile_is_ignored(tmp_path, taught):
    path = tmp_path / R.PROFILE
    R.save_profile(path, taught)
    back = R.load_profile(path)
    assert [(s["kind"], s["id"]) for s in back] == [(s["kind"], s["id"]) for s in taught]
    assert np.allclose(back[0]["levels"], taught[0]["levels"], rtol=1e-4)
    assert np.allclose(back[1]["excess"], taught[1]["excess"], rtol=1e-4) and np.allclose(back[1]["tonal"], taught[1]["tonal"], rtol=1e-4)
    assert back[1]["quality"] == taught[1]["quality"] and back[1]["facing"] == "ahead"
    assert len(back[1]["chunks"]) == len(taught[1]["chunks"]) and R.Model(back).notes is not None
    data = path.read_text()
    assert len(data) < 20000                                         # levels and peaks only: no audio is kept
    path.write_text(data.replace('"bands": 40', '"bands": 32'))
    assert R.load_profile(path) == []
    path.write_text("not json")
    assert R.load_profile(path) == []
    path.write_text(json.dumps({"version": 2, "rate": RATE, "bands": R.BANDS,
                                "samples": [{"kind": "cube", "id": "x", "excess": [[1, 2]]}, "junk", {"kind": "music", "id": "y"},
                                            {"kind": "background", "id": "z", "levels": [[-1] * R.BANDS] * 2}]}))
    assert R.load_profile(path) == []                                # a damaged sample is dropped, not trusted


def test_the_sound_learned_before_samples_is_kept(tmp_path, taught):
    # 0.2.323 kept one background and one jingle: they become a background and a cube sample
    path = tmp_path / R.PROFILE
    path.write_text(json.dumps({"version": 1, "rate": RATE, "bands": R.BANDS, "quality": {"snr_db": 20.0},
                                "learned": {"background": "2026-10-20T11:00:00", "cube": "2026-10-20T12:00:00"},
                                "background": taught[0]["levels"].tolist(),
                                "jingle": taught[1]["excess"][:2].sum(axis=0).tolist()}))
    samples = R.load_profile(path)
    assert [(s["kind"], s["at"]) for s in samples] == [("background", "2026-10-20T11:00:00"), ("cube", "2026-10-20T12:00:00")]
    model = R.Model(samples)
    assert model.ready and model.notes is None                      # heard by its bands until a new sample brings notes
    rng = np.random.default_rng(27)
    assert heard_share(shown(model, background(8, rng) + jingle(8, rng, level=0.02, pan=45))[60:]) > 0.9


# ---- the worker ----------------------------------------------------------------------------------

class FakeSource:
    """Plays whatever ``scene["audio"]`` holds, looped, in blocks of HOP frames."""

    def __init__(self, scene):
        self.scene, self.at, self.name = scene, 0, "Test speakers"

    def read(self):
        audio = self.scene["audio"]
        if self.at + R.HOP > len(audio):
            self.at = 0
        block = audio[self.at:self.at + R.HOP]
        self.at += R.HOP
        time.sleep(0.0005)
        return block

    def close(self):
        self.scene["closed"] = self.scene.get("closed", 0) + 1


def _wait(predicate, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _learned(radar, kind, seconds, facing="ahead"):
    radar.learn(kind, delay=0, seconds=seconds, facing=facing)
    assert _wait(lambda: radar.state()["learning"] is None)
    return radar.state()


def test_the_radar_learns_from_the_sound_and_tracks_a_cube(tmp_path):
    rng = np.random.default_rng(14)
    quiet = background(4, rng)
    scene = {"audio": quiet}
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    assert not radar.state()["ready"] and not radar.state()["listening"]
    state = _learned(radar, "background", 2.0)
    assert state["last_learn"]["ok"] and state["learned"]["background"]
    scene["audio"] = background(6, rng) + jingle(6, rng, level=0.06)
    state = _learned(radar, "cube", 4.0)
    assert state["ready"] and state["last_learn"]["ok"] and "dB over the background" in state["last_learn"]["message"]
    assert [s["kind"] for s in state["samples"]] == ["background", "cube"] and state["model"]["notes"]
    assert (tmp_path / R.PROFILE).exists()
    assert not _wait(lambda: radar.state()["listening"], timeout=0.5)      # not on: it stopped listening
    scene["audio"] = quiet + jingle(4, rng, level=0.02, pan=-50)
    radar.configure(True, 5)
    assert _wait(lambda: radar.state()["heard"])
    state = radar.state()
    assert state["side"] == "left" and state["device"] == "Test speakers" and state["listening"] and state["channels"] == 2
    assert state["direction"] in ("to your left, ahead or behind", "to your left") and state["mirror"] is not None
    scene["audio"] = quiet
    assert _wait(lambda: not radar.state()["heard"])
    radar.configure(False)
    assert _wait(lambda: not radar.state()["listening"])
    reloaded = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    assert reloaded.state()["ready"]                                 # learned once, kept
    radar.clear()
    assert not radar.state()["ready"] and not (tmp_path / R.PROFILE).exists()


def test_the_radar_keeps_the_newest_samples_and_forgets_one(tmp_path, monkeypatch):
    monkeypatch.setitem(R.KEEP, "background", 2)
    rng = np.random.default_rng(28)
    scene = {"audio": background(4, rng)}
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    for n in (1, 2, 3):
        state = _learned(radar, "background", 0.5)
        assert state["last_learn"]["ok"] and state["model"]["backgrounds"] == min(n, 2)
    assert "Background learned (2 samples)." in state["last_learn"]["message"]
    scene["audio"] = background(6, rng) + jingle(6, rng, level=0.06)
    _learned(radar, "cube", 4.0)
    state = _learned(radar, "cube", 4.0, facing="behind")
    assert state["last_learn"]["ok"] and state["last_learn"]["facing"] == "behind"
    assert (state["model"]["ahead"], state["model"]["behind"]) == (1, 1)
    assert state["model"]["front_back"] in ("alike", "need_more")    # the same stereo sound ahead and behind
    first = state["samples"][0]["id"]
    assert radar.forget(first) and not radar.forget(first)
    assert radar.state()["model"]["backgrounds"] == 1 and len(R.load_profile(tmp_path / R.PROFILE)) == 3


def test_a_learning_counts_down_first_and_can_be_cancelled(tmp_path):
    scene = {"audio": background(2, np.random.default_rng(15))}
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    radar.learn("cube", delay=30, facing="behind")
    learning = radar.state()["learning"]
    assert learning["phase"] == "countdown" and 29 < learning["seconds"] <= 30 and learning["facing"] == "behind"
    radar.cancel()
    assert radar.state()["learning"] is None
    with pytest.raises(ValueError):
        radar.learn("music")
    with pytest.raises(ValueError):
        radar.learn("cube", facing="left")


def test_a_missing_sound_device_is_reported_and_retried(tmp_path):
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError("no sound output device")

    radar = R.Radar(tmp_path / R.PROFILE, source=broken)
    radar.RETRY_S = 0.05
    radar.learn("background", delay=0)
    assert _wait(lambda: radar.state()["error"] == "no sound output device")
    assert _wait(lambda: radar.state()["last_learn"] is not None)
    assert not radar.state()["last_learn"]["ok"] and radar.state()["learning"] is None
    radar.configure(True)
    assert _wait(lambda: len(calls) >= 3)                            # keeps retrying while it is on
    radar.configure(False)


def test_the_loopback_source_is_windows_only(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="Windows only"):
        R.LoopbackSource()


# ---- the app ------------------------------------------------------------------------------------

@pytest.fixture
def fresh_radar(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(server, "_RADAR", None)
    monkeypatch.setattr(server, "_RADAR_LOCK", threading.Lock())
    yield tmp_path


def test_the_radar_is_off_by_default_and_its_settings_are_checked(fresh_radar):
    ui = server.ui_settings()
    assert ui["radar_enabled"] is False and ui["radar_sensitivity"] == 5
    source = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")
    assert '"rtss_enabled", "radar_enabled")' in source and '("radar_sensitivity", 1, 10)' in source
    assert 'if any(k.startswith("radar_") for k in body):' in source and "radar_sync(stop=True)" in source
    state = server.radar_state()
    assert state["setting"] is False and state["enabled"] is False and not state["ready"] and state["samples"] == []


def test_the_control_endpoint_checks_its_requests(fresh_radar, monkeypatch):
    for bad in ({"action": "record"}, {"action": "learn", "kind": "music"}, {"action": "learn", "kind": "cube", "facing": "left"},
                {"action": "forget"}, {"action": "forget", "sample": "nope"}, {}):
        with pytest.raises(ValueError):
            server.radar_control(bad)
    monkeypatch.setattr(R.sys, "platform", "linux")
    with pytest.raises(ValueError, match="Windows only"):
        server.radar_control({"action": "learn", "kind": "cube"})
    assert server.radar_control({"action": "clear"})["ready"] is False
    assert server.radar_control({"action": "cancel"})["learning"] is None
    server.radar_sync()                                              # a no-op off Windows
    assert server.cube_radar().state()["enabled"] is False


def test_the_overlay_settings_hotkey_and_bundle_are_wired():
    html = (STATIC / "overlay.html").read_text(encoding="utf-8")
    js = (STATIC / "overlay.js").read_text(encoding="utf-8")
    css = (STATIC / "overlay.css").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="ovradar"' in html and ".ovradar" in css and ".ovrblip" in css and ".ovrghost" in css
    assert "setupRadar(ui.radar_enabled===true)" in js and 'fetch("/api/radar")' in js
    assert 'viewBox="0 0 120 120"' in js and "r.mirror!=null" in js and "r.direction" in js   # the full circle
    for control in ('id="radar-enabled"', 'id="radar-learn-bg"', 'id="radar-learn-cube"', 'id="radar-learn-behind"',
                    'id="radar-learn-other"', 'id="radar-sens"', 'id="radar-clear"', 'id="radar-status"', 'id="radar-samples"',
                    '"/api/radar"', 'action: "forget"', 'facing: "behind"', 'kind: "other"'):
        assert control in app
    assert "nothing is recorded or uploaded" in app
    assert "toggle_cube_radar" in hotkeys.ACTIONS and '"toggle_cube_radar"' in app
    assert "soundcard>=0.4.6; sys_platform == 'win32'" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"soundcard"' in (ROOT / "packaging" / "aion2calc.spec").read_text(encoding="utf-8")


def test_the_settings_name_each_learn_step_by_its_key():
    # the notes said "press 1" and "press 2" beside "Ctrl+1 (step 1)": each step now names the key
    # Settings -> Hotkeys gives it (its button only when it has none), and the 3D audio advice is there
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "press <b>1</b>" not in app and "press <b>2</b>" not in app
    assert "function radarKey(ui, action)" in app and "${radarNotes(ui)}" in app
    for action in hotkeys.RADAR_DEFAULTS:
        assert f'key("{action}", ' in app
    assert "turn 3D audio on" in app and "stereo cannot tell ahead from behind" in app


def test_the_learn_hotkeys_listen_at_once_and_the_overlay_shows_how_it_went(fresh_radar, monkeypatch):
    # the learn keys are pressed in the game beside the cube, so they skip the countdown the Settings
    # buttons give for switching back to the game; the overlay then shows the result for a few seconds
    calls = []

    class Fake:
        def learn(self, kind, delay, facing="ahead"):
            calls.append((kind, delay, facing))

        def state(self):
            return {"learning": None}

    monkeypatch.setattr(server, "_RADAR", Fake())
    monkeypatch.setattr(R, "supported", lambda: True)
    for bad in (-1, 31, "now", True):
        with pytest.raises(ValueError, match="countdown"):
            server.radar_control({"action": "learn", "kind": "cube", "countdown": bad})
    server.radar_control({"action": "learn", "kind": "cube", "countdown": 0})
    server.radar_control({"action": "learn", "kind": "background"})
    server.radar_control({"action": "learn", "kind": "cube", "facing": "behind", "countdown": 0})
    server.radar_control({"action": "learn", "kind": "other", "countdown": 0})
    assert calls == [("cube", 0.0, "ahead"), ("background", float(R.COUNTDOWN_S), "ahead"),
                     ("cube", 0.0, "behind"), ("other", 0.0, "ahead")]
    launcher = (ROOT / "aion2calc" / "launcher.py").read_text(encoding="utf-8")
    assert '"radar_learn_cube": lambda: server.radar_control({"action": "learn", "kind": "cube", "countdown": 0})' in launcher
    assert '{"action": "learn", "kind": "cube", "facing": "behind", "countdown": 0}' in launcher
    assert '"radar_learn_other": lambda: server.radar_control({"action": "learn", "kind": "other", "countdown": 0})' in launcher
    assert "hotkeys.effective(server.ui_settings())" in launcher
    js = (STATIC / "overlay.js").read_text(encoding="utf-8")
    assert "r.last_learn_s<6" in js


def test_a_finished_learning_says_when_it_finished(tmp_path):
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource({"audio": background(4, np.random.default_rng(16))}))
    assert radar.state()["last_learn_s"] is None
    radar.learn("background", delay=0, seconds=1.0)
    assert _wait(lambda: radar.state()["last_learn"] is not None)
    assert 0 <= radar.state()["last_learn_s"] < 5
