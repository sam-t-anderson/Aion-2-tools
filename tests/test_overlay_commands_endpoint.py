"""The overlay's command channel answers: ``/api/overlay/commands`` is what the overlay polls for
the reload that Open overlay asks for while it is already open (and the hotkeys' one-shot
commands). Until 0.2.330 the handler passed ``_json`` a keyword it does not take, so every poll
was a 500 and the reload never reached the overlay."""
import json
import threading
import urllib.request

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.app.server import make_server
    srv = make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


def test_the_overlay_command_channel_answers_uncached(app):
    from aion2calc.app import overlay_launch
    with urllib.request.urlopen(app + "/api/overlay/commands", timeout=10) as r:
        assert r.status == 200 and r.headers["Cache-Control"] == "no-store"
        before = json.loads(r.read())
    assert isinstance(before, dict)
    overlay_launch._ask_reload()                      # Open overlay while it is open bumps the counter
    with urllib.request.urlopen(app + "/api/overlay/commands", timeout=10) as r:
        after = json.loads(r.read())
    assert after.get("reload_seq", 0) == before.get("reload_seq", 0) + 1
