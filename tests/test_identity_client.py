"""Community identity on the client: the Your characters panel (app and Pages site), the local
identity-credential store and its endpoints, and the verified / hidden marks in the lists and
the viewer. The server side (claims, opt-out, recovery, challenges) lives in the log server."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    return tmp_path


def test_identity_credentials_are_validated_and_stored_locally(home):
    from aion2calc.combat import identity
    assert identity.entries() == []
    row = {"server": "https://logs.test/", "name": " Sorc ", "server_name": "Siel", "token": "a2id_" + "x" * 32, "status": "active", "claimed_at": 5}
    saved = identity.replace([row])
    assert saved == [{"server": "https://logs.test", "name": "Sorc", "server_name": "Siel", "token": "a2id_" + "x" * 32, "status": "active", "claimed_at": 5.0}]
    assert identity.entries() == saved
    for bad in ({"server": "javascript:x", "name": "Sorc", "token": "a2id_" + "x" * 32},
                {"server": "https://logs.test", "name": "", "token": "a2id_" + "x" * 32},
                {"server": "https://logs.test", "name": "Sorc", "token": "a2l_notanidentity"}, "junk"):
        with pytest.raises(ValueError):
            identity.replace([bad])
    with pytest.raises(ValueError):
        identity.replace([row] * (identity.LIMIT + 1))
    assert identity.replace([]) == [] and identity.entries() == []


def test_the_app_serves_the_store_to_the_local_page_only(home, monkeypatch):
    from http.server import ThreadingHTTPServer
    from aion2calc.app.server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(method, body=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        req = urllib.request.Request(base + "/api/identity-claims", None if body is None else json.dumps(body).encode(), headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    try:
        assert call("GET") == (200, [])
        row = {"server": "https://logs.test", "name": "Sorc", "server_name": "Siel", "token": "a2id_" + "y" * 32, "status": "active"}
        status, out = call("POST", {"action": "replace", "claims": [row]})
        assert status == 200 and out[0]["token"] == row["token"]
        assert call("GET")[1][0]["name"] == "Sorc"
        assert call("POST", {"action": "steal", "claims": []})[0] >= 400           # the app answers errors as 500s
        # Another origin (a web page in the same browser) gets nothing: the credentials are local.
        status, out = call("GET", origin="https://evil.example")
        assert status >= 400 and "local application origin" in out["error"]
        assert call("POST", {"action": "replace", "claims": []}, origin="https://evil.example")[0] >= 400
        assert call("GET")[1][0]["name"] == "Sorc"                                 # the refusal changed nothing
    finally:
        srv.shutdown()


def test_the_panel_is_shared_by_the_app_and_the_site():
    js = (STATIC / "identity.js").read_text(encoding="utf-8")
    assert "window.A2Identity={mount,clean,call}" in js
    for path in ("/api/v1/identity/claimable", "/api/v1/identity/claim", "/api/v1/identity/preferences", "/api/v1/identity/release", "/api/v1/identity"):
        assert path in js
    assert "'X-Identity-Token'" in js and "redirect:'error'" in js and "credentials:'omit'" in js
    assert "rows:browserRows" in (STATIC / "log-ownership.js").read_text(encoding="utf-8")   # the recordings' credentials feed the claim
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '<div id="my-characters"></div>' in app and "A2Identity.mount($('#my-characters')" in app
    assert "api('/api/identity-claims')" in app
    assert 'src="/static/identity.js"' in (STATIC / "index.html").read_text(encoding="utf-8")
    site_html = (ROOT / "site" / "logs.html").read_text(encoding="utf-8")
    assert '<div id="my-characters"></div>' in site_html and 'src="static/identity.js"' in site_html
    assert 'A2Identity.mount(document.getElementById("my-characters"))' in (ROOT / "site" / "logs.js").read_text(encoding="utf-8")
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert pages.count("aion2calc/app/static/identity.js") == 2            # trigger path and the deploy copy


def test_verified_and_hidden_marks_reach_the_lists_and_the_viewer():
    for path in (STATIC / "logs-view.js", ROOT / "site" / "logs.js"):
        text = path.read_text(encoding="utf-8")
        assert "verified: p.verified === true, pseudonym: p.pseudonym === true" in text
        assert '" · verified"' in text and '" · hidden by its player"' in text
    assert "e.verified?' <span class=\"verified\"" in (ROOT / "site" / "leaderboard.js").read_text(encoding="utf-8")
    review = (STATIC / "combat-review.js").read_text(encoding="utf-8")
    assert '${e.verified ? " ✓" : ""}${e.pseudonym ? " (hidden by its player)" : ""}' in review
    community = (STATIC / "community.js").read_text(encoding="utf-8")
    assert "verified" in community and "hidden by its player" in community
