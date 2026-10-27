"""Featured encounters (log server 0.2.145) in the app and on the website: the app's proxy to the log server lets
the encounters' pages through and nothing next to them, and both the app and the website load the shared script."""
import io
import json
import re
from pathlib import Path

import pytest

from aion2calc.combat import account, share

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
FEATURED = "/api/v1/featured/fe_0123456789"


@pytest.fixture
def sent(monkeypatch):
    """What the proxy asks the log server, which answers {"ok": true}."""
    asked = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout=None):
        asked.append(request.full_url)
        return Answer(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(share, "effective", lambda: {"url": "https://logs.test/"})
    monkeypatch.setattr(account, "token_for", lambda base: None)
    monkeypatch.setattr(share.urllib.request, "urlopen", urlopen)
    return asked


@pytest.mark.parametrize("path", ["/api/v1/featured", FEATURED, FEATURED + "/race", FEATURED + "/race?region=nae",
                                  FEATURED + "/progress?page=2", FEATURED + "/reports?page=1", FEATURED + "/statistics?metric=hps",
                                  FEATURED + "/rankings?metric=dps&boss=npc%3A2390001&class=cleric"])
def test_the_proxy_lets_the_featured_pages_through(sent, path):
    assert share.community_request(path) == {"ok": True}
    assert sent == ["https://logs.test" + path]


@pytest.mark.parametrize("path", ["/api/v1/featured/fe_012345678", "/api/v1/featured/fe_0123456789/../logs",
                                  FEATURED + "/raw", FEATURED + "/race/more", "/api/v1/featured/FE_0123456789",
                                  "/api/v1/featuredx", FEATURED + "#race"])
def test_the_proxy_refuses_anything_else(sent, path):
    with pytest.raises(ValueError, match="Invalid community API path"):
        share.community_request(path)
    with pytest.raises(ValueError, match="Invalid community API path"):
        share.community_request(FEATURED + "/race", {"show": True})       # the pages are read, never written
    assert sent == []


def test_the_app_and_the_website_load_the_featured_pages():
    app = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/featured.css"><script src="/static/featured.js"></script>' in app
    logs = (ROOT / "site" / "logs.html").read_text(encoding="utf-8")
    # the cards sit above the Browse logs tabs
    assert logs.index('<div id="featured"></div>') < logs.index('id="logs-tabs"')
    for page in ("logs.html", "encounter.html"):
        text = (ROOT / "site" / page).read_text(encoding="utf-8")
        assert 'href="static/featured.css"' in text and '<script src="static/featured.js"></script>' in text, page
    encounter = (ROOT / "site" / "encounter.html").read_text(encoding="utf-8")
    assert encounter.index("static/featured.js") < encounter.index('src="encounter.js"')
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "aion2calc/app/static/featured.js aion2calc/app/static/featured.css" in pages
    assert '"aion2calc/app/static/featured.*"' in pages
    # the website's links name the encounter and its page (the app's are checked in the browser tests)
    assert re.search(r"encounter\.html\?'\+new URLSearchParams\(\{f:id,view:view\|\|'race'", (ROOT / "site" / "logs.js").read_text(encoding="utf-8"))
