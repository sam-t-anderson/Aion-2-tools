"""The optional account on the desktop app (combat/account.py and /api/account): the app keeps the
credential in account.json and never hands it to its pages; uploads and the logs it already holds join
the account; the pages reach only the account and legion routes; a server that ends the sign-in signs the
app out. A small stand-in for the log server's account API answers here."""
import gzip
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

TOKEN = "a2app_" + "k" * 43
HANDOFF = "h" * 43


class FakeServer:
    def __init__(self):
        self.seen = []            # (method, path, X-Account-Token, body)
        self.revoked = False
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _answer(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                if self.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                body = json.loads(raw) if raw else None
                token = self.headers.get("X-Account-Token")
                me.seen.append((method, self.path, token, body))
                path = self.path.split("?")[0]
                profile = {"id": "acc_1", "name": "Seren", "logs": 2, "characters": [], "passkeys": 0, "apps": 1, "discord": None}
                if path == "/api/v1/account/config":
                    return self._answer(200, {"methods": {"app": True, "passkey": True, "discord": False}, "site": "https://players.example/tools/"})
                if path == "/api/v1/account/register":
                    return self._answer(201, {"token": TOKEN, "account": profile})
                if path == "/api/v1/logs":
                    return self._answer(201, {"id": "abcdef12", "delete_token": "d" * 30, "visibility": self.path.split("visibility=")[1]})
                if path == "/api/v1/account/discord/start":
                    return self._answer(200, {"url": "https://discord.com/oauth2/authorize?state=x", "request": "r" * 20,
                                              "secret": "s" * 43, "interval": 3, "expires_in": 600})
                if path == "/api/v1/account/discord/poll":
                    # the server issues the credential only to the poll that brings the browser's handoff
                    if body.get("handoff") != HANDOFF:
                        return self._answer(200, {"status": "pending"})
                    return self._answer(200, {"status": "approved", "token": TOKEN, "account": profile})
                if token != TOKEN or me.revoked:
                    return self._answer(401, {"error": "Sign in again: this sign-in has ended or was revoked"})
                if path == "/api/v1/account":
                    return self._answer(200, {"account": profile, "session": {"id": 1, "kind": "app"}})
                if path == "/api/v1/account/logs/attach":
                    return self._answer(200, {"attached": len(body["evidence"])})
                if path == "/api/v1/account/claims/attach":
                    return self._answer(200, {"added": len(body["tokens"])})
                if path in ("/api/v1/account/logs", "/api/v1/legions/mine", "/api/v1/account/signout"):
                    return self._answer(200, {"logs": [], "legions": [], "signed_out": 1})
                return self._answer(404, {"error": "not found"})

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    fake = FakeServer()
    from aion2calc.combat import share
    share.save_settings(url=fake.url)
    monkeypatch.setattr(share, "discover", lambda url: {"upload_url": url + "/api/v1/logs"})
    yield fake
    fake.httpd.shutdown()


def test_creating_the_account_keeps_the_credential_in_the_app_and_adds_what_it_holds(server, tmp_path):
    from aion2calc.combat import account, identity, ownership
    ownership.merge([{"server": server.url, "id": "abcdef12", "delete_token": "d" * 30, "title": "Mine"},
                     {"server": "https://elsewhere.example", "id": "zzzzzz12", "delete_token": "e" * 30}])
    identity.replace([{"server": server.url, "name": "Seren", "token": "a2id_" + "i" * 30},
                      {"server": "https://elsewhere.example", "name": "Other", "token": "a2id_" + "j" * 30}])
    out = account.register("Seren")
    assert out["signed_in"] and out["here"] and out["account"]["name"] == "Seren"
    assert out["added"] == {"logs": 1, "characters": 1}
    assert TOKEN not in json.dumps(out)                       # the page never sees the credential
    attached = next(b for m, p, t, b in server.seen if p == "/api/v1/account/logs/attach")
    assert attached == {"evidence": [{"id": "abcdef12", "delete_token": "d" * 30}]}  # only this server's
    claims = [b for m, p, t, b in server.seen if p == "/api/v1/account/claims/attach"]
    assert claims == [{"tokens": ["a2id_" + "i" * 30]}]                 # once: the sign-in's sync gave them
    saved = json.loads((tmp_path / "data" / "account.json").read_text()) if (tmp_path / "data" / "account.json").exists() \
        else json.loads(next(tmp_path.rglob("account.json")).read_text())
    assert saved["token"] == TOKEN and saved["server"] == server.url
    with pytest.raises(ValueError):
        account.register("Again")                            # already signed in


def test_the_pages_reach_only_the_account_and_legion_routes(server):
    from aion2calc.combat import account
    account.register(None)
    assert account.request("GET", "/api/v1/legions/mine")["legions"] == []
    assert account.request("GET", "/api/v1/account/logs?page=1&limit=50")["logs"] == []
    for method, path in (("GET", "/api/v1/logs/abcdef12/raw"), ("POST", "/api/v1/account/register"),
                         ("GET", "/api/v1/account/logs?x=\nHost: evil"), ("DELETE", "/api/v1/account"),
                         ("GET", "https://evil.example/api/v1/account"), ("POST", "/api/v1/account/ticket")):
        with pytest.raises(PermissionError):
            account.request(method, path)
    assert all(t == TOKEN for m, p, t, b in server.seen if p.startswith("/api/v1/legions"))


def test_an_ended_sign_in_signs_the_app_out(server):
    from aion2calc.combat import account
    account.register(None)
    server.revoked = True
    with pytest.raises(account.SignedOut):
        account.request("GET", "/api/v1/account/logs")
    assert account.status()["signed_in"] is False and account.token_for(server.url) is None


def test_another_server_in_settings_is_not_signed_in(server):
    from aion2calc.combat import account, share
    account.register(None)
    share.save_settings(url="https://other.example")
    s = account.status()
    assert s["signed_in"] and s["here"] is False and s["account_server"] == server.url
    with pytest.raises(PermissionError):
        account.request("GET", "/api/v1/legions/mine")
    assert account.token_for("https://other.example") is None and account.token_for(server.url) == TOKEN


def _doc():
    return {"format": "a2log", "version": 1, "meta": {"source": "test", "title": "Fight"},
            "players": [{"id": "p0", "name": "Seren", "class": "sorcerer"}],
            "segments": [{"label": "Boss", "duration": 10, "hits": [{"t": 1, "player": "p0", "skill": "Fire", "damage": 10}]}]}


def test_uploads_join_the_account_and_legion_only_needs_it(server):
    from aion2calc.combat import account, share
    out = share.upload(_doc(), visibility="legion")              # not signed in: kept private
    assert out["visibility"] == "private" and "sign in" in out["visibility_note"].lower()
    assert server.seen[-1][2] is None
    account.register(None)
    out = share.upload(_doc(), visibility="legion")
    assert out["visibility"] == "legion" and "visibility_note" not in out
    assert server.seen[-1][1].endswith("visibility=legion") and server.seen[-1][2] == TOKEN
    with pytest.raises(ValueError):
        share.upload(_doc(), visibility="friends")


def test_the_app_endpoint_hides_the_credential_and_refuses_other_sites(server):
    from aion2calc.app.server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(method, body=None, origin=None):
        headers = {"Content-Type": "application/json"} | ({"Origin": origin} if origin else {})
        req = urllib.request.Request(base + "/api/account", None if body is None else json.dumps(body).encode(), headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    try:
        status, out = call("POST", {"action": "register", "name": "Seren"})
        assert status == 200 and out["signed_in"] and TOKEN not in json.dumps(out)
        status, out = call("GET")
        assert status == 200 and out["account"]["name"] == "Seren" and TOKEN not in json.dumps(out)
        assert call("POST", {"action": "request", "method": "GET", "path": "/api/v1/legions/mine"})[1] == {"logs": [], "legions": [], "signed_out": 1}
        assert call("POST", {"action": "signout"}, origin="https://evil.example")[0] == 403
        assert call("POST", {"action": "request", "method": "GET", "path": "/api/v1/logs"})[0] == 403
        assert call("POST", {"action": "nope"})[0] == 500
        assert call("POST", {"action": "signout"}) == (200, {"signed_in": False})
    finally:
        srv.shutdown()


def test_discord_signs_the_app_in_only_with_the_handoff_its_browser_brings_back(server, monkeypatch):
    from aion2calc.combat import account
    opened = []
    monkeypatch.setattr(account.webbrowser, "open", opened.append)
    for elsewhere in ("https://evil.example/api/account/discord-done", "http://127.0.0.1.evil.example:8765/api/account/discord-done",
                      "http://127.0.0.1:8765/elsewhere"):
        with pytest.raises(ValueError):
            account.discord_start(elsewhere)
    back = "http://127.0.0.1:8765/api/account/discord-done"
    assert account.discord_start(back) == {"waiting": True, "interval": 3}
    assert opened == ["https://discord.com/oauth2/authorize?state=x"]
    started = next(b for m, p, t, b in server.seen if p == "/api/v1/account/discord/start")
    assert started == {"purpose": "app", "return_to": back}
    assert account.discord_poll() == {"status": "pending"}                  # nothing has come back yet
    assert account.discord_finish("x" * 43)["status"] == "pending"          # a made-up handoff signs nobody in
    out = account.discord_finish(HANDOFF)
    assert out["status"] == "approved" and out["signed_in"] and TOKEN not in json.dumps(out)
    assert account.discord_poll()["status"] == "approved"                    # the page reads it once
    assert account.discord_poll() == {"status": "expired"}
    assert account.discord_finish(HANDOFF) == {"status": "expired"}         # nothing waits any more
    secrets_sent = [b for m, p, t, b in server.seen if p == "/api/v1/account/discord/poll"]
    assert all(b["secret"] == "s" * 43 and b["request"] == "r" * 20 for b in secrets_sent)


def test_a_refused_discord_sign_in_ends_with_its_reason(server, monkeypatch):
    from aion2calc.combat import account
    monkeypatch.setattr(account.webbrowser, "open", lambda url: None)
    account.discord_start("http://127.0.0.1:8765/api/account/discord-done")
    assert account.discord_finish(None, "Discord sign-in was cancelled") == {"status": "error", "error": "Discord sign-in was cancelled"}
    assert account.discord_poll() == {"status": "error", "error": "Discord sign-in was cancelled"}
    account.discord_start("http://127.0.0.1:8765/api/account/discord-done")
    assert account.discord_finish(None)["error"].startswith("The browser came back from Discord without")


def test_the_browser_returns_to_the_apps_own_page(server, monkeypatch):
    from aion2calc.app.server import Handler
    from aion2calc.combat import account
    monkeypatch.setattr(account.webbrowser, "open", lambda url: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(body):
        req = urllib.request.Request(base + "/api/account", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def page(query):
        with urllib.request.urlopen(base + "/api/account/discord-done?" + query, timeout=30) as r:
            assert r.headers["Content-Type"].startswith("text/html") and r.headers["Cache-Control"] == "no-store"
            return r.read().decode()
    try:
        assert "No Discord sign-in is waiting" in page("a2handoff=" + HANDOFF)
        assert post({"action": "discord-start"})["waiting"] is True
        started = next(b for m, p, t, b in server.seen if p == "/api/v1/account/discord/start")
        assert started["return_to"] == base + "/api/account/discord-done"      # this app's own address
        assert "Signed in with Discord as Seren" in page("a2handoff=" + HANDOFF)
        assert post({"action": "discord-poll"})["status"] == "approved"
        assert post({"action": "signout"}) == {"signed_in": False}
        post({"action": "discord-start"})
        assert "&lt;b&gt;" in page("a2error=" + urllib.parse.quote("<b>refused</b>"))  # the reason, escaped
    finally:
        srv.shutdown()


def test_a_claim_joins_the_signed_in_account_at_once(server):
    from aion2calc.app.server import Handler
    from aion2calc.combat import account
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def save(rows):
        req = urllib.request.Request(base + "/api/identity-claims", json.dumps({"action": "replace", "claims": rows}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    row = {"server": server.url, "name": "Seren", "server_name": "Siel", "token": "a2id_" + "i" * 30}
    try:
        save([row])                                                             # signed out: kept here only
        assert not [p for m, p, t, b in server.seen if p == "/api/v1/account/claims/attach"]
        account.register("Seren")
        server.seen.clear()
        save([row, row | {"name": "Alt", "token": "a2id_" + "j" * 30}])
        attached = [b for m, p, t, b in server.seen if p == "/api/v1/account/claims/attach"]
        assert attached == [{"tokens": ["a2id_" + "i" * 30, "a2id_" + "j" * 30]}]
        server.revoked = True                                                   # the account call fails: the claim stays
        assert len(save([row])) == 1
    finally:
        srv.shutdown()


def test_claims_the_account_lacks_reach_it_without_a_sync(server, monkeypatch):
    from aion2calc.combat import account, identity
    monkeypatch.setattr(account, "_offered", set())
    account.register("Seren")
    identity.replace([{"server": server.url, "name": "Seren", "server_name": "Siel", "token": "a2id_" + "i" * 30}])
    server.seen.clear()                                    # a claim made after signing in, as before 0.2.349
    assert account.status()["signed_in"]
    attached = [b for m, p, t, b in server.seen if p == "/api/v1/account/claims/attach"]
    assert attached == [{"tokens": ["a2id_" + "i" * 30]}]
    server.seen.clear()
    account.status()                                       # offered once per run, not on every refresh
    assert not [p for m, p, t, b in server.seen if p == "/api/v1/account/claims/attach"]
