"""Browser tests: the app's own pages in Chromium, served by the real app (``python -m aion2calc app``) from a
fresh data folder, with every request to another site blocked. The app's log server is a stand-in run by the
tests (community.py), so the community pages show known, made-up fights and no test reaches a real server.

They need Playwright and its Chromium (``pip install playwright`` then ``python -m playwright install
chromium``) and are skipped without them, except where ``AION2CALC_BROWSER_TESTS=1`` (CI's "App in a
browser" job), where a missing browser fails the run. ``AXE_CORE_JS`` names axe-core's ``axe.min.js`` for
the accessibility checks, which are skipped without it.

Every test's page fails the test on a script error, an error logged by the page, or an answer of 400 or
more from the app, unless the test expects it (``watch.allow``)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from apphelpers import open_context, watched_page

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = os.environ.get("AION2CALC_BROWSER_TESTS") == "1"


def _unavailable(why: str):
    if REQUIRED:
        pytest.fail(f"browser tests are required here, but {why}")
    pytest.skip(why)


@pytest.fixture(scope="session")
def community():
    """The stand-in log server the app under test uses."""
    from community import Community
    server = Community()
    yield server
    server.close()


@pytest.fixture(scope="session")
def app_home(tmp_path_factory, community):
    """The data folder the app under test runs with (its settings, logs and caches), its log server set to the
    stand-in with an upload key, as a player's saved choice is (the project's default server is never asked)."""
    import json
    from aion2calc.combat.share import PUBLIC_DEFAULT_KEY
    home = tmp_path_factory.mktemp("home")
    (home / "data").mkdir()
    (home / "data" / "logserver.json").write_text(json.dumps({"url": community.url, "key": "a2l_browser-tests",
                                                              "visibility": "public", PUBLIC_DEFAULT_KEY: True}), encoding="utf-8")
    return home


@pytest.fixture(scope="session")
def app_url(app_home, tmp_path_factory):
    """The app, started as a player starts it without a window: its own server on a free port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "AION2CALC_HOME": str(app_home), "PYTHONUNBUFFERED": "1"}
    log = open(tmp_path_factory.mktemp("log") / "app.log", "w+", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "aion2calc", "app", "--no-browser", "--no-sync", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 60
    while True:
        try:
            with urllib.request.urlopen(url + "api/ui", timeout=2):
                break
        except OSError:
            if proc.poll() is not None or time.time() > deadline:
                log.seek(0)
                proc.kill()
                pytest.fail("the app did not start:\n" + log.read()[-3000:])
            time.sleep(0.2)
    yield url
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


@pytest.fixture(scope="module")
def browser():
    """Chromium for one test module: Playwright's sync API allows one instance per thread, so it stops before
    the other tests that start their own (the overlay tests) run."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        _unavailable("Playwright is not installed")
    pw = sync_playwright().start()
    try:
        chromium = pw.chromium.launch()
    except Error as exc:
        pw.stop()
        _unavailable(f"Chromium does not start ({str(exc).splitlines()[0]})")
    yield chromium
    chromium.close()
    pw.stop()


@pytest.fixture
def app_page(browser, app_url):
    """A page of the app in a fresh profile; the test fails on anything the page gets wrong."""
    context = open_context(browser, app_url)
    page, watch = watched_page(context, app_url)
    page.watch = watch
    yield page
    context.close()
    assert not watch.unexpected(), watch.unexpected()


@pytest.fixture(scope="session")
def axe_js():
    path = os.environ.get("AXE_CORE_JS")
    if not path or not Path(path).is_file():
        if REQUIRED:
            pytest.fail("AXE_CORE_JS must name axe-core's axe.min.js for the accessibility checks")
        pytest.skip("AXE_CORE_JS is not set (axe-core's axe.min.js)")
    return path
