"""The interfaces' own data in the app (0.2.482): what the web pages keep in their browser's storage and the native
window and overlay keep, held by the app in its data folder (``interface.json``), read and changed through
``/api/interface`` on this computer only, and given to each page of the web interface before its first script."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def app(home):
    from aion2calc.app import server
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def call(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            status, raw, kind = answer.status, answer.read(), answer.headers.get("Content-Type", "")
    except urllib.error.HTTPError as refused:
        status, raw, kind = refused.code, refused.read(), refused.headers.get("Content-Type", "")
    return status, (json.loads(raw) if kind.startswith("application/json") else raw.decode("utf-8"))


def test_the_data_is_kept_in_the_data_folder(home):
    from aion2calc.app import interface_store as store
    assert store.values() == {}
    assert store.update({"theme": "light", "a2plans": "[]", "a2-lang": "de"}) == {"ok": True}
    assert store.update({"theme": "dark", "a2plans": None}) == {"ok": True}          # changed, and forgotten
    assert store.values() == {"theme": "dark", "a2-lang": "de"}
    kept = json.loads((home / "data" / "interface.json").read_text(encoding="utf-8"))
    assert kept == {"values": {"theme": "dark", "a2-lang": "de"}}
    # a message between a browser's windows, and a browser's own mark and list, stay in the browser
    store.update({"aion2calc-closing": "1700000000000", "a2-store-browser": "1", "a2-store-pending": "{}"})
    assert store.values() == {"theme": "dark", "a2-lang": "de"}
    # a file that cannot be read holds nothing
    (home / "data" / "interface.json").write_text("{not json", encoding="utf-8")
    assert store.values() == {}


def test_what_is_not_a_set_of_keys_and_texts_is_refused(home, monkeypatch):
    from aion2calc.app import interface_store as store
    for bad in (None, [], {"": "x"}, {"k" * 301: "x"}, {"theme": 1}, {"theme": ["dark"]}):
        with pytest.raises(ValueError):
            store.update(bad)
    store.update({"k": "x"})
    monkeypatch.setattr(store, "LIMIT", 10)
    with pytest.raises(ValueError, match="64 MB"):
        store.update({"big": "y" * 20})
    assert store.values() == {"k": "x"}                                                 # nothing of it kept


def test_a_page_gets_the_data_before_its_first_script(home):
    from aion2calc.app import interface_store as store
    store.update({"theme": "light", "note": '</script><script>alert(1)</script> & ' + chr(0x2028)})
    page = store.page_with_store('<!doctype html><html><head><meta charset="utf-8"><script>first()</script></head></html>')
    head, _, rest = page.partition('<meta charset="utf-8">')
    assert head == "<!doctype html><html><head>"
    data = rest[len("<script>window.A2STORE="):rest.index(";</script>")]
    assert "<" not in data and ">" not in data and "&" not in data and chr(0x2028) not in data
    assert json.loads(data) == store.values()
    assert rest.index('<script src="/static/store.js"></script>') < rest.index("<script>first()</script>")
    assert store.page_with_store("<html><head><title>x</title></head>").startswith("<html><head><script>window.A2STORE=")


def test_the_app_reads_and_keeps_it_for_this_computer(app):
    assert call(app, "/api/interface") == (200, {"values": {}})
    assert call(app, "/api/interface", {"set": {"accent": "azure", "theme": "light"}}) == (200, {"ok": True})
    assert call(app, "/api/interface", {"set": {"theme": None}}) == (200, {"ok": True})
    assert call(app, "/api/interface") == (200, {"values": {"accent": "azure"}})
    status, answer = call(app, "/api/interface", {"set": {"accent": 3}})
    assert status == 500 and "must be a text" in answer["error"]
    # the app's pages come with it: the main page and both overlay windows
    for path in ("/", "/overlay", "/overlay?view=pets"):
        status, page = call(app, path)
        assert status == 200 and 'window.A2STORE={"accent":"azure"};' in page and "/static/store.js" in page, path
    status, script = call(app, "/static/store.js")
    assert status == 200 and "a2-store-browser" in script


def test_another_computer_neither_reads_nor_changes_it(app, monkeypatch):
    from aion2calc.app import server
    call(app, "/api/interface", {"set": {"theme": "light"}})
    local = server.Handler._local
    monkeypatch.setattr(server.Handler, "_local", lambda self: False)
    status, answer = call(app, "/api/interface")
    assert status == 403 and "computer running the app" in answer["error"]
    assert call(app, "/api/interface", {"set": {"theme": "dark"}})[0] == 403
    status, page = call(app, "/")
    assert status == 200 and "A2STORE" not in page and "store.js" not in page            # the page, without the data
    monkeypatch.setattr(server.Handler, "_local", local)
    assert call(app, "/api/interface")[1] == {"values": {"theme": "light"}}
