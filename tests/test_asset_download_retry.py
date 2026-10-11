"""The scheduled asset refresh must survive a transient network blip.

A single read timeout against the external source previously aborted the whole
`Refresh game asset references` workflow. `download()` now retries transient
failures and still fails fast on validation/size errors.
"""
import importlib.util
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "export_item_details",
    Path(__file__).resolve().parents[1] / "tools" / "export_item_details.py",
)
export_item_details = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(export_item_details)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self, _n):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, sequence):
    calls = {"n": 0}

    def fake_urlopen(_request, timeout=0):
        index = calls["n"]
        calls["n"] += 1
        outcome = sequence[index]
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)

    monkeypatch.setattr(export_item_details, "urlopen", fake_urlopen)
    monkeypatch.setattr(export_item_details.time, "sleep", lambda _s: None)
    return calls


def test_download_retries_a_transient_timeout(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [TimeoutError("read timed out"), b"{}"])
    assert export_item_details.download("https://example/item") == b"{}"
    assert calls["n"] == 2  # one failure, one success


def test_download_retries_a_dropped_connection_then_a_5xx(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [
        URLError("connection reset"),
        HTTPError("https://example", 503, "busy", {}, None),
        b"[]",
    ])
    assert export_item_details.download("https://example/item") == b"[]"
    assert calls["n"] == 3


def test_download_gives_up_after_the_retry_budget(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [TimeoutError("x")] * export_item_details.RETRIES)
    with pytest.raises(TimeoutError):
        export_item_details.download("https://example/item")
    assert calls["n"] == export_item_details.RETRIES


def test_download_does_not_retry_a_client_error(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [
        HTTPError("https://example", 404, "missing", {}, None),
        b"{}",
    ])
    with pytest.raises(HTTPError):
        export_item_details.download("https://example/item")
    assert calls["n"] == 1  # 4xx is not transient; no retry


def test_download_enforces_the_size_limit(monkeypatch):
    _patch_urlopen(monkeypatch, [b"x" * 50])
    with pytest.raises(ValueError):
        export_item_details.download("https://example/item", limit=10)
