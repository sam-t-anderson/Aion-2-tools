"""Uploads are public by default (0.2.323): listed in the community logs and counted in the rankings.
Every install saved the old default, unlisted, on its first launch, so other players' uploads never
reached the community list; a saved "unlisted" is switched to public once, and the app says so."""
import json

import pytest

from aion2calc.combat import share
from aion2calc.paths import data_file, write_user_json


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _saved(**settings):
    write_user_json(settings, "logserver.json")


def _raw():
    return json.loads(data_file("logserver.json").read_text(encoding="utf-8"))


def test_the_old_unlisted_default_becomes_public_once_and_the_app_is_told(home):
    _saved(url="https://logs.test", visibility="unlisted")
    s = share.settings()
    assert s["visibility"] == "public" and s[share.VISIBILITY_NOTICE] is True
    assert _raw()[share.PUBLIC_DEFAULT_KEY] is True                   # written back: done once
    share.dismiss_visibility_notice()
    assert share.VISIBILITY_NOTICE not in share.settings()
    share.save_settings(visibility="unlisted")                       # a choice made after the switch
    assert share.settings()["visibility"] == "unlisted"
    assert share.effective()["visibility"] == "unlisted"


def test_private_stays_private_and_needs_no_notice(home):
    _saved(url="https://logs.test", visibility="private")
    s = share.settings()
    assert s["visibility"] == "private" and share.VISIBILITY_NOTICE not in s


def test_a_first_save_of_unlisted_is_kept(home):
    share.save_settings("https://logs.test", visibility="unlisted")    # no file before this save
    assert share.settings()["visibility"] == "unlisted"


def test_an_upload_with_no_visibility_set_is_public(home, monkeypatch):
    sent = []

    class _Resp:
        def __init__(self, req):
            sent.append(req)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    monkeypatch.setattr(share, "validate", lambda d: d)
    monkeypatch.setattr(share, "discover", lambda url: {})
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test", "is_default": False})
    monkeypatch.setattr(share.urllib.request, "urlopen", lambda req, timeout=None: _Resp(req))
    share.upload({"format": "a2log", "version": 1, "meta": {}, "players": [], "segments": []})
    assert sent and sent[-1].full_url.endswith("?visibility=public")


def test_the_default_server_and_the_app_offer_public_first():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    default = json.loads((root / "aion2calc" / "data" / "global" / "default_server.json").read_text(encoding="utf-8"))
    assert default["visibility"] == "public"
    js = (root / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert '["public", "unlisted", "private"]' in js and 'action: "notice-seen"' in js
    assert "chosenVisibility='public'" in (root / "aion2calc" / "app" / "static" / "archive-upload.js").read_text(encoding="utf-8")
