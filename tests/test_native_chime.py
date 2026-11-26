"""The overlay's event chime in the app's own windows (gui/chime.py, 0.2.513).

Until 0.2.513 the native overlay and Party window rang the system's alert, Windows' "Default Beep", for each event entering
the events strip with *Play a sound when an event notification appears* on: a ding at intervals. The web overlay plays a
short two-note chime, or the sound the player uploaded. On Windows the app's own windows now play the same chime through
``winsound`` (faked here), or the uploaded sound when it is a WAV; one window chimes for a new event, not each.
"""
import array
import io
import math
import os
import sys
import types
import wave

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from aion2calc.gui import chime  # noqa: E402

NOW = 1_795_600_010.0                                    # ten seconds into a minute


def _read(data: bytes):
    with wave.open(io.BytesIO(data)) as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), array.array("h", w.readframes(w.getnframes()))


def _strength(samples, rate: int, start: float, end: float, frequency: float) -> float:
    """How loud ``frequency`` sounds between ``start`` and ``end`` seconds (one bin of a Fourier transform, 0 to 1)."""
    part = samples[int(start * rate):int(end * rate)]
    re = sum(s * math.cos(2 * math.pi * frequency * n / rate) for n, s in enumerate(part))
    im = sum(s * math.sin(2 * math.pi * frequency * n / rate) for n, s in enumerate(part))
    return 2 * math.hypot(re, im) / (len(part) * 32767)


def _wav(values, width: int = 2, rate: int = 22050) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(array.array("h", values).tobytes() if width == 2 else bytes(values))
    return out.getvalue()


class FakeWinsound(types.ModuleType):
    """The standard library's ``winsound``, as far as the chime uses it."""
    SND_NODEFAULT, SND_MEMORY = 2, 4

    def __init__(self):
        super().__init__("winsound")
        self.played = []

    def PlaySound(self, sound, flags):  # noqa: N802 - winsound's name
        self.played.append((bytes(sound), flags))


def test_the_built_in_chime_is_the_web_pages():
    """overlay.js ``playEventSound``: G5, then C6 0.13 s later, each rising to 0.22 in 20 ms and gone by 0.36 s."""
    channels, width, rate, samples = _read(chime.built_in())
    assert (channels, width, rate) == (1, 2, 44100)
    assert len(samples) == int(44100 * 0.49)
    assert 0.2 < max(abs(s) for s in samples) / 32767 < 0.25
    assert max(abs(s) for s in samples[:20]) < 100                    # it starts from silence, without a click
    g5, c6 = 784.0, 1046.5
    assert _strength(samples, rate, 0.02, 0.12, g5) > 5 * _strength(samples, rate, 0.02, 0.12, c6)
    assert _strength(samples, rate, 0.15, 0.30, c6) > 5 * _strength(samples, rate, 0.15, 0.30, g5)


def test_an_uploaded_wav_plays_at_the_web_pages_volume(tmp_path):
    sound = tmp_path / "overlay-event-sound.wav"
    sound.write_bytes(_wav([0, 10000, -20000, 30000]))
    channels, width, rate, samples = _read(chime.custom(tmp_path))
    assert (channels, width, rate) == (1, 2, 22050) and list(samples) == [0, 6000, -12000, 18000]
    sound.write_bytes(_wav([128, 228, 28], width=1))                   # 8-bit samples rest at 128
    with wave.open(io.BytesIO(chime.custom(tmp_path))) as w:
        assert w.readframes(3) == bytes([128, 188, 68])
    sound.write_bytes(b"ID3\x04 an MP3 named .wav")
    assert chime.custom(tmp_path) is None
    sound.unlink()
    (tmp_path / "overlay-event-sound.mp3").write_bytes(b"ID3\x04")   # Windows' PlaySound plays no MP3
    assert chime.custom(tmp_path) is None


def test_windows_plays_the_chime_and_never_the_system_alert(tmp_path, monkeypatch):
    fake = FakeWinsound()
    monkeypatch.setitem(sys.modules, "winsound", fake)
    monkeypatch.setattr(chime, "WINDOWS", True)
    alerts = []
    monkeypatch.setattr(chime, "_alert", lambda: alerts.append(1))
    chime.play(home=tmp_path).join(5)
    assert fake.played == [(chime.built_in(), fake.SND_MEMORY | fake.SND_NODEFAULT)]
    (tmp_path / "overlay-event-sound.wav").write_bytes(_wav([0, 10000]))
    chime.play(custom_sound=True, home=tmp_path).join(5)
    assert fake.played[-1] == (chime.custom(tmp_path), 6)
    chime.play(custom_sound=False, home=tmp_path).join(5)             # the uploaded sound only while it is set
    assert fake.played[-1][0] == chime.built_in()

    def failing(sound, flags):
        raise RuntimeError("Failed to play sound")
    fake.PlaySound = failing                                           # no sound device: silence, not the ding
    chime.play(home=tmp_path).join(5)
    assert alerts == []


def test_other_systems_keep_the_system_alert(monkeypatch):
    monkeypatch.setattr(chime, "WINDOWS", False)
    alerts = []
    monkeypatch.setattr(chime, "_alert", lambda: alerts.append(1))
    assert chime.play() is None and alerts == [1]


def test_one_window_claims_a_new_event(tmp_path):
    claims = tmp_path / "claims"
    assert chime.claim({"rift:soon"}, claims, NOW) is True             # the meter overlay sees the rift first
    assert chime.claim({"rift:soon"}, claims, NOW + 0.8) is False      # the Party window, a moment later
    assert chime.claim({"festival:soon", "rift:soon"}, claims, NOW + 1) is True
    assert chime.claim({"rift:soon", "festival:soon"}, claims, NOW + 2) is False   # the same events, in any order
    assert chime.claim({"rift:active"}, claims, NOW + 3) is True       # the rift's next phase
    assert chime.claim({"rift:soon"}, claims, NOW + 55) is False       # the next minute still holds the claim
    assert chime.claim({"rift:soon"}, claims, NOW + 125) is True       # the rift again, two minutes on
    old = claims / "0123456789abcdef-1.claim"
    old.write_bytes(b"")
    os.utime(old, (NOW - 7200, NOW - 7200))
    assert chime.claim({"boss:soon"}, claims, NOW + 130) is True and not old.exists()   # claims an hour old go
    blocked = tmp_path / "a file"
    blocked.write_bytes(b"")
    assert chime.claim({"rift:soon"}, blocked, NOW) is True             # nowhere to claim: every window chimes


def test_announce_claims_then_chimes(tmp_path, monkeypatch):
    played = []
    monkeypatch.setattr(chime, "play", lambda custom_sound=False, home=None: played.append((custom_sound, home)))
    assert chime.announce({"rift:soon"}, True, home=tmp_path, now=NOW) is True
    assert chime.announce({"rift:soon"}, True, home=tmp_path, now=NOW + 1) is False
    assert played == [(True, tmp_path)]
    assert len(list(tmp_path.joinpath("cache", "event-chimes").glob("*.claim"))) == 1
