"""The Hidden Cube radar (0.2.323): it hears a Hidden Cube's jingle in the game's sound, once taught
it beside a cube, and shows its side (stereo balance) and how near it is (loudness) on the overlay.
The audio here is synthetic: a sparkle of bell notes for the jingle, pink noise with footstep-like
bursts for the background, and a voice, music, a different chime and noise bursts that must not
match. Off by default; Windows only; nothing is recorded or uploaded."""
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
    th = math.radians((pan + 90) / 2)
    return np.stack([mono * math.cos(th), mono * math.sin(th)], axis=1)


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


def levels_of(audio):
    ring = np.zeros((R.WINDOW, 2), dtype=np.float32)
    out = []
    for i in range(0, len(audio) - R.HOP + 1, R.HOP):
        ring = np.concatenate([ring, audio[i:i + R.HOP].astype(np.float32)])[-R.WINDOW:]
        out.append(R.band_levels(ring))
    return out


@pytest.fixture(scope="module")
def learned():
    rng = np.random.default_rng(4)
    bg = R.learn_background(levels_of(background(4, rng)))
    template, quality = R.learn_jingle(levels_of(background(6, rng) + jingle(6, rng, level=0.06)), bg)
    return bg, template, quality


def _shown(learned, audio, sensitivity=5):
    bg, template, _ = learned
    matcher, track = R.Matcher(template, bg, sensitivity), R.Track()
    views = []
    for levels in levels_of(audio):
        track.add(matcher.step(levels))
        views.append(track.view())
    return views


# ---- matching ------------------------------------------------------------------------------------

def test_learning_finds_the_jingles_bands(learned):
    _, template, quality = learned
    assert quality["snr_db"] > 15 and quality["bands"] <= 8 and 1800 <= quality["peak_hz"] <= 5000
    weights, region = R.jingle_weights(template)
    centres = R.band_centres()
    assert weights.max() == 1.0 and set(np.nonzero(weights)[0]) <= set(np.nonzero(region)[0])
    assert centres[weights > 0].min() > 1500                       # nothing of it down where voices and bass sit


def test_the_radar_hears_the_jingle_and_its_side(learned):
    rng = np.random.default_rng(7)
    for pan, side in ((45, "right"), (-60, "left"), (0, "middle")):
        views = _shown(learned, background(8, rng) + jingle(8, rng, level=0.02, pan=pan))[60:]
        heard = [v for v in views if v["heard"]]
        assert len(heard) > 0.9 * len(views)
        assert abs(np.median([v["angle"] for v in heard]) - pan) <= 8 and heard[-1]["side"] == side
        assert -15 < np.median([v["level_db"] for v in heard]) < -6               # learned at 3x the level: -9.5 dB
        assert 0.45 < np.median([v["proximity"] for v in heard]) < 0.8


def test_a_far_cube_is_still_heard_and_a_buried_one_is_not_guessed(learned):
    rng = np.random.default_rng(8)
    far = _shown(learned, background(8, rng) + jingle(8, rng, level=0.006, pan=30))[60:]
    assert sum(v["heard"] for v in far) > 0.5 * len(far)
    assert np.median([v["proximity"] for v in far if v["heard"]]) < 0.5
    buried = _shown(learned, background(8, rng) + jingle(8, rng, level=0.001, pan=30))
    assert not any(v["heard"] for v in buried)


@pytest.mark.parametrize("name", ["background", "voice", "loud voice", "music", "another chime", "noise bursts"])
def test_other_sounds_are_not_a_cube(learned, name):
    rng = np.random.default_rng(9)
    n = 10 * RATE
    other = {"background": lambda: background(20, rng, level=0.06),
             "voice": lambda: background(10, rng) + voice(10),
             "loud voice": lambda: background(10, rng) + voice(10, level=0.2),
             "music": lambda: background(10, rng) + music(10),
             "another chime": lambda: background(10, rng) + jingle(10, rng, level=0.2, notes=(880.0, 1318.5, 1760.0), gap=(0.3, 0.6)),
             "noise bursts": lambda: background(10, rng) + rng.standard_normal((n, 2)) * 0.1 * (np.arange(n) % RATE < RATE // 10)[:, None],
             }[name]()
    assert not any(v["heard"] for v in _shown(learned, other))


def test_music_does_not_hide_the_jingle(learned):
    rng = np.random.default_rng(10)
    views = _shown(learned, background(8, rng) + jingle(8, rng, level=0.02, pan=30) + music(8, level=0.05))[60:]
    assert sum(v["heard"] for v in views) > 0.8 * len(views)


def test_louder_is_closer_and_the_trend_says_so(learned):
    rng = np.random.default_rng(11)
    closer = _shown(learned, background(6, rng) + jingle(6, rng, level=0.01, pan=20, ramp=(0.3, 3.0)))
    assert closer[-1]["heard"] and closer[-1]["trend"] == "louder"
    away = _shown(learned, background(6, rng) + jingle(6, rng, level=0.01, pan=20, ramp=(3.0, 0.3)))
    assert any(v["trend"] == "quieter" for v in away[-60:])


def test_the_sensitivity_trades_reach_for_strictness():
    strict, default, loose = (R.thresholds(s) for s in (1, 5, 10))
    assert strict[0] > default[0] > loose[0] and strict[1] > default[1] > loose[1]
    assert R.thresholds(0) == strict and R.thresholds(99) == loose


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


# ---- learning ------------------------------------------------------------------------------------

def test_learning_without_a_jingle_says_what_to_change():
    rng = np.random.default_rng(12)
    bg = R.learn_background(levels_of(background(4, rng)))
    with pytest.raises(R.LearnError, match="did not stand out|Nothing louder"):
        R.learn_jingle(levels_of(background(6, rng)), bg)
    noise = rng.standard_normal((6 * RATE, 2)) * 0.2                 # a fight's or a waterfall's roar
    with pytest.raises(R.LearnError, match="whole range"):
        R.learn_jingle(levels_of(noise), bg)


def test_without_a_background_the_quiet_steps_stand_in_for_it():
    rng = np.random.default_rng(13)
    template, quality = R.learn_jingle(levels_of(background(6, rng) + jingle(6, rng, level=0.06, gap=(0.3, 0.6))))
    assert quality["snr_db"] > 10 and quality["bands"] <= 8


def test_the_profile_round_trips_and_a_foreign_one_is_ignored(tmp_path, learned):
    bg, template, quality = learned
    path = tmp_path / R.PROFILE
    R.save_profile(path, {"background": bg, "jingle": template, "quality": quality, "learned": {"cube": "2026-10-20T12:00:00"}})
    back = R.load_profile(path)
    assert np.allclose(back["background"], bg) and np.allclose(back["jingle"], template)
    assert back["quality"] == quality and back["learned"]["cube"] == "2026-10-20T12:00:00"
    data = path.read_text()
    assert len(data) < 4000                                          # band levels only: no audio is kept
    path.write_text(data.replace('"bands": 40', '"bands": 32'))
    assert R.load_profile(path) == {}
    path.write_text("not json")
    assert R.load_profile(path) == {}


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


def test_the_radar_learns_from_the_sound_and_tracks_a_cube(tmp_path):
    rng = np.random.default_rng(14)
    quiet = background(4, rng)
    scene = {"audio": quiet}
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    assert not radar.state()["ready"] and not radar.state()["listening"]
    radar.learn("background", delay=0, seconds=2.0)
    assert _wait(lambda: radar.state()["learning"] is None)
    assert radar.state()["last_learn"]["ok"] and radar.state()["learned"]["background"]
    scene["audio"] = background(6, rng) + jingle(6, rng, level=0.06)
    radar.learn("cube", delay=0, seconds=4.0)
    assert _wait(lambda: radar.state()["learning"] is None)
    state = radar.state()
    assert state["ready"] and state["last_learn"]["ok"] and "dB over the background" in state["last_learn"]["message"]
    assert (tmp_path / R.PROFILE).exists()
    assert not _wait(lambda: radar.state()["listening"], timeout=0.5)      # not on: it stopped listening
    scene["audio"] = quiet + jingle(4, rng, level=0.02, pan=-50)
    radar.configure(True, 5)
    assert _wait(lambda: radar.state()["heard"])
    state = radar.state()
    assert state["side"] == "left" and state["device"] == "Test speakers" and state["listening"]
    scene["audio"] = quiet
    assert _wait(lambda: not radar.state()["heard"])
    radar.configure(False)
    assert _wait(lambda: not radar.state()["listening"])
    reloaded = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    assert reloaded.state()["ready"]                                 # learned once, kept
    radar.clear()
    assert not radar.state()["ready"] and not (tmp_path / R.PROFILE).exists()


def test_a_learning_counts_down_first_and_can_be_cancelled(tmp_path):
    scene = {"audio": background(2, np.random.default_rng(15))}
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource(scene))
    radar.learn("cube", delay=30)
    learning = radar.state()["learning"]
    assert learning["phase"] == "countdown" and 29 < learning["seconds"] <= 30
    radar.cancel()
    assert radar.state()["learning"] is None
    with pytest.raises(ValueError):
        radar.learn("music")


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
    assert state["setting"] is False and state["enabled"] is False and not state["ready"]


def test_the_control_endpoint_checks_its_requests(fresh_radar, monkeypatch):
    for bad in ({"action": "record"}, {"action": "learn", "kind": "music"}, {}):
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
    assert 'id="ovradar"' in html and ".ovradar" in css and ".ovrblip" in css
    assert "setupRadar(ui.radar_enabled===true)" in js and 'fetch("/api/radar")' in js and "ahead or behind" in js
    for control in ('id="radar-enabled"', 'id="radar-learn-bg"', 'id="radar-learn-cube"', 'id="radar-sens"',
                    'id="radar-clear"', 'id="radar-status"', '"/api/radar"'):
        assert control in app
    assert "nothing is recorded or uploaded" in app
    assert "toggle_cube_radar" in hotkeys.ACTIONS and '"toggle_cube_radar"' in app
    assert "soundcard>=0.4.6; sys_platform == 'win32'" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"soundcard"' in (ROOT / "packaging" / "aion2calc.spec").read_text(encoding="utf-8")


def test_the_learn_hotkeys_listen_at_once_and_the_overlay_shows_how_it_went(fresh_radar, monkeypatch):
    # Ctrl+1 / Ctrl+2 are pressed in the game beside the cube, so they skip the countdown the Settings
    # buttons give for switching back to the game; the overlay then shows the result for a few seconds
    calls = []

    class Fake:
        def learn(self, kind, delay):
            calls.append((kind, delay))

        def state(self):
            return {"learning": None}

    monkeypatch.setattr(server, "_RADAR", Fake())
    monkeypatch.setattr(R, "supported", lambda: True)
    for bad in (-1, 31, "now", True):
        with pytest.raises(ValueError, match="countdown"):
            server.radar_control({"action": "learn", "kind": "cube", "countdown": bad})
    server.radar_control({"action": "learn", "kind": "cube", "countdown": 0})
    server.radar_control({"action": "learn", "kind": "background"})
    assert calls == [("cube", 0.0), ("background", float(R.COUNTDOWN_S))]
    launcher = (ROOT / "aion2calc" / "launcher.py").read_text(encoding="utf-8")
    assert '"radar_learn_cube": lambda: server.radar_control({"action": "learn", "kind": "cube", "countdown": 0})' in launcher
    assert "hotkeys.effective(server.ui_settings())" in launcher
    js = (STATIC / "overlay.js").read_text(encoding="utf-8")
    assert "r.last_learn_s<6" in js


def test_a_finished_learning_says_when_it_finished(tmp_path):
    radar = R.Radar(tmp_path / R.PROFILE, source=lambda: FakeSource({"audio": background(4, np.random.default_rng(16))}))
    assert radar.state()["last_learn_s"] is None
    radar.learn("background", delay=0, seconds=1.0)
    assert _wait(lambda: radar.state()["last_learn"] is not None)
    assert 0 <= radar.state()["last_learn_s"] < 5
