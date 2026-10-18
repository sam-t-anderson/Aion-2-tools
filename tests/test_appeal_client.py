"""Appeals from the client: a held upload is appealed from My uploads with its private upload
credential, a revoked claim from Your characters with its identity credential. The server side
(one appeal per decision, the moderator queue, overturning) lives in the log server."""
import io
import json
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
ROW = {"server": "https://logs.test", "id": "AbC123xy", "delete_token": "t" * 32, "title": "Boss fight"}


@pytest.fixture
def sent(monkeypatch, tmp_path):
    """The requests the ownership helper sends, answered by ``reply`` (an object or an HTTPError)."""
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.combat import ownership, share
    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test"})
    log = {"requests": [], "reply": {"id": "a" * 24, "status": "open"}}

    class Opener:
        def open(self, req, timeout=None):
            log["requests"].append(req)
            if isinstance(log["reply"], Exception):
                raise log["reply"]
            return io.BytesIO(json.dumps(log["reply"]).encode())
    monkeypatch.setattr(ownership.urllib.request, "build_opener", lambda *a: Opener())
    return log


def test_an_appeal_goes_to_the_uploads_own_server_with_its_credential(sent):
    from aion2calc.combat import ownership
    out = ownership.request(dict(ROW), "appeal", None, "  The title names my own character.  ")
    assert out["status"] == "open"
    req = sent["requests"][-1]
    assert (req.get_method(), req.full_url) == ("POST", "https://logs.test/api/v1/logs/AbC123xy/appeal")
    assert req.get_header("X-log-token") == "t" * 32 and req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == {"statement": "The title names my own character."}
    with pytest.raises(ValueError, match="10–1,000"):
        ownership.request(dict(ROW), "appeal", None, "short")
    # The server's reason is the answer when it refuses (already appealed, no hold any more).
    sent["reply"] = urllib.error.HTTPError(ROW["server"], 409, "Conflict", {},
                                           io.BytesIO(b'{"error": "This decision has already been appealed"}'))
    with pytest.raises(ValueError, match=r"Appeal refused \(409\): This decision has already been appealed"):
        ownership.request(dict(ROW), "appeal", None, "The title names my own character.")
    # Another server than the selected one never receives the credential.
    with pytest.raises(ValueError, match="original server"):
        ownership.request(dict(ROW, server="https://elsewhere.test"), "appeal", None, "The title names my own character.")


def test_the_app_passes_the_statement_to_the_helper(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from http.server import ThreadingHTTPServer
    from aion2calc.app.server import Handler
    from aion2calc.combat import ownership
    seen = []
    monkeypatch.setattr(ownership, "request", lambda row, action, visibility=None, statement=None:
                        seen.append((row["id"], action, visibility, statement)) or {"status": "open"})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = {"owner": ROW, "action": "appeal", "statement": "The title names my own character."}
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/log-ownership", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            assert json.loads(r.read()) == {"status": "open"}
    finally:
        srv.shutdown()
    assert seen == [("AbC123xy", "appeal", None, "The title names my own character.")]


def test_both_panels_offer_the_appeal():
    owned = (STATIC / "log-ownership.js").read_text(encoding="utf-8")
    assert "Appeal this hold" in owned and "data-appeal" in owned
    assert "action==='appeal'){path+='/appeal';method='POST'" in owned            # the Pages site calls the server directly
    ident = (STATIC / "identity.js").read_text(encoding="utf-8")
    assert "Appeal the revocation" in ident and "'/api/v1/identity/appeal'" in ident and "st.revocation" in ident
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "action==='appeal'?{owner,action,statement:value}" in app              # the desktop app goes through its proxy
    for name in ("log-ownership.js", "identity.js"):
        subprocess.run(["node", "--check", str(STATIC / name)], check=True)
