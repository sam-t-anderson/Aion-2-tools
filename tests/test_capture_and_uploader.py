"""Capture-buffer sizing and uploader attribution (0.2.269).

At the old 8 MiB kernel capture buffer, busy fights dropped a quarter to a half of their packets —
which unranked them and left enemies unidentified (their spawn packets were among the dropped). The
capture now requests a much larger buffer, stepping down until the backend accepts one. Separately,
a public log now records the uploading (local) player so community logs can show who shared it;
when the local player isn't established the log stays anonymous.
"""
import pathlib

from aion2calc.meter.a2parser.capture_stats import CAPTURE_BUFFER_BYTES, _BUFFER_CANDIDATES

ROOT = pathlib.Path(__file__).resolve().parents[1]
METER_RUNNER = (ROOT / "aion2calc" / "app" / "meter_runner.py").read_text(encoding="utf-8")


def test_capture_buffer_is_much_larger_than_the_old_8mib():
    assert CAPTURE_BUFFER_BYTES >= 64 * 1024 * 1024    # old default was 8 MiB; raids need far more


def test_buffer_candidates_descend_to_the_old_default():
    assert _BUFFER_CANDIDATES[0] == CAPTURE_BUFFER_BYTES
    assert list(_BUFFER_CANDIDATES) == sorted(_BUFFER_CANDIDATES, reverse=True)
    assert _BUFFER_CANDIDATES[-1] == 8 * 1024 * 1024    # still falls back to the previous size


def test_metadata_stamps_the_uploader_from_the_local_player():
    # The export chokepoint (_metadata, used by both the live-save and upload paths) records the
    # local/recording player as meta.uploader, best-effort, so public logs can attribute uploads.
    assert 'doc["meta"]["uploader"]' in METER_RUNNER
    assert "local_player_id" in METER_RUNNER
    assert '"verified"' in METER_RUNNER     # marks whether the identity came from the game
