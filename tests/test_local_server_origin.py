"""The app's local server answers its own pages and the programs on this computer, never a web page on
another site. Any page open in the player's browser can send requests to 127.0.0.1:8765, and a browser
sends a form-like POST without asking first, so until 0.2.340 a site could switch the log server, change
the settings or quit the app. Every request is now refused when its Origin is another site, or when its
Host is not this computer's own name (a site that points its own domain name at 127.0.0.1)."""
import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIL = "https://evil.example"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    from aion2calc.app import server
    from aion2calc.combat import logs
    quits, opened = [], []
    # Were the check ever lost, these refused requests would reach the routes: keep them harmless.
    monkeypatch.setattr(server, "schedule_shutdown", lambda *a, **k: quits.append(1))
    monkeypatch.setattr(logs, "open_folder", lambda *a, **k: opened.append(a) or tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield {"port": port, "base": f"http://127.0.0.1:{port}", "quits": quits, "opened": opened}
    srv.shutdown()


def call(app, path, body=None, headers=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(app["base"] + path, data, headers or {}, method=method or ("GET" if data is None else "POST"))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw or b"null")
    except ValueError:
        return status, raw.decode("utf-8", "replace")             # a page, not JSON


def post_routes() -> list[str]:
    """Every POST route the server has, read from route_post (prefix routes get a suffix), so a route added
    later is covered without editing this test."""
    src = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")
    body = src[src.index("    def route_post(self"):]
    body = body[:body.index("\n    def ", 10)]
    routes = []
    for kind, args in re.findall(r"if path (==|in|\.startswith)\s*\(?\s*([^:]+?)\)?\s*:", body):
        for p in re.findall(r'"(/api/[^"]*)"', args):
            routes.append(p + ("x" if kind == ".startswith" or p.endswith("/") else ""))
    return list(dict.fromkeys(routes))


def test_every_post_route_is_found():
    routes = post_routes()
    assert len(routes) >= 40 and "/api/ui" in routes and "/api/logserver" in routes and "/api/quit" in routes


def test_a_web_page_on_another_site_changes_nothing(app):
    before_server = call(app, "/api/logserver")[1]["url"]
    before_ui = call(app, "/api/ui")[1]
    # what any page can send without a CORS preflight: a "simple" POST, text/plain
    simple = {"Origin": EVIL, "Content-Type": "text/plain;charset=UTF-8"}
    status, out = call(app, "/api/logserver", {"url": EVIL, "visibility": "public"}, simple)
    assert status == 403 and "local application origin" in out["error"]
    status, out = call(app, "/api/ui", {"auto_update": not before_ui.get("auto_update", True)}, simple)
    assert status == 403
    for path in post_routes():                    # every action, the first refusal that fails stops here
        status, out = call(app, path, {}, simple)
        assert status == 403 and "local application origin" in str(out), path
    assert call(app, "/api/logserver")[1]["url"] == before_server
    assert call(app, "/api/ui")[1] == before_ui
    assert app["quits"] == [] and app["opened"] == []


def test_a_site_whose_name_points_at_this_computer_is_refused(app):
    # DNS rebinding: the page and the request both say evil.example, so Origin matches Host
    rebound = {"Host": f"evil.example:{app['port']}", "Origin": f"http://evil.example:{app['port']}"}
    status, out = call(app, "/api/logserver", {"url": EVIL}, rebound)
    assert status == 403 and "local application origin" in out["error"]
    assert call(app, "/api/ui", headers=rebound)[0] == 403                  # nor can it read the answers
    assert call(app, "/api/sessions", headers={"Host": f"evil.example:{app['port']}"})[0] == 403


def test_reading_from_another_site_or_a_sandboxed_page_is_refused(app):
    assert call(app, "/api/ui", headers={"Origin": EVIL})[0] == 403
    assert call(app, "/api/identity-claims", headers={"Origin": EVIL})[0] == 403
    assert call(app, "/api/ui", {"auto_update": False}, {"Origin": "null"})[0] == 403   # file:// or sandboxed


def test_the_apps_own_pages_and_programs_are_served(app):
    port = app["port"]
    # the overlay and the launcher post without an Origin, as programs do
    assert call(app, "/api/ui", {"auto_update": False}, {"Content-Type": "application/json"})[0] == 200
    assert call(app, "/api/ui")[1]["auto_update"] is False
    for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
        own = {"Host": host, "Origin": f"http://{host}", "Content-Type": "application/json"}
        assert call(app, "/api/ui", {"auto_update": True}, own)[0] == 200
        assert call(app, "/api/ui", headers={"Host": host, "Origin": f"http://{host}"})[0] == 200
    assert call(app, "/api/ui")[1]["auto_update"] is True
    assert call(app, "/api/status", headers={"Host": f"[::1]:{port}"})[0] == 200    # an IP address is this computer
    status, page = call(app, "/")
    assert status == 200


def test_refusals_inside_a_route_answer_403():
    from aion2calc.app import server
    src = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")
    for method in ("def do_GET", "def do_POST"):
        block = src[src.index(method):src.index("\n    def ", src.index(method) + 10)]
        assert "except PermissionError" in block and "403" in block
    assert server.Handler._refusal.__doc__
