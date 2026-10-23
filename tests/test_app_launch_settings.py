"""The app window and the launch settings of 0.2.329: a 1080p window instead of a maximized one, the text
size, the page the app opens on, My Character opening the character you opened last, and the two notes on
the Live Meter page (Capture diagnostics, the installed game version) folded away until opened."""
import json
import os
import re
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from aion2calc import launcher
from aion2calc.app import server
from aion2calc.app.settings_backup import APP_PAGES, _clean

STATIC = os.path.join(os.path.dirname(__file__), "..", "aion2calc", "app", "static")


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as fh:
        return fh.read()


def test_the_window_is_1080p_or_as_much_of_the_screen_as_there_is_centred():
    assert launcher.WINDOW_SIZE == (1920, 1080)
    assert launcher.window_geometry((2560, 1400)) == (1920, 1080, 320, 160)   # a 1440p screen less its taskbar
    assert launcher.window_geometry((1920, 1032)) == (1920, 1032, 0, 0)       # a 1080p screen with a taskbar
    assert launcher.window_geometry((1536, 864)) == (1536, 864, 0, 0)         # a laptop at 125 %
    assert launcher.window_geometry(None) == (1920, 1080, 0, 0)               # the screen could not be read
    assert launcher.window_geometry((0, 0)) == (1920, 1080, 0, 0)


def test_the_work_area_is_read_or_given_up_on_quietly():
    area = launcher.work_area()
    assert area is None or (len(area) == 2 and all(isinstance(v, int) and v > 0 for v in area))


def test_open_window_sizes_and_places_the_window_instead_of_maximizing_it(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    monkeypatch.setattr(launcher, "app_browser", lambda: "C:/Edge/msedge.exe")
    monkeypatch.setattr(launcher, "work_area", lambda: (2560, 1400))
    launched = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: launched.append(args) or "the process")
    assert launcher.open_window("http://127.0.0.1:1/") == "the process"
    args = launched[0]
    assert args[0] == "C:/Edge/msedge.exe" and "--app=http://127.0.0.1:1/" in args
    assert "--window-size=1920,1080" in args and "--window-position=320,160" in args
    assert not any(a.startswith("--start-maximized") for a in args)
    monkeypatch.setattr(launcher, "work_area", lambda: None)                  # unreadable screen: 1080p at the corner
    launcher.open_window("http://127.0.0.1:1/")
    assert "--window-size=1920,1080" in launched[1] and "--window-position=0,0" in launched[1]


def test_text_size_page_at_launch_and_my_character_settings_have_defaults_and_bounds(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    ui = server.ui_settings()
    assert ui["app_text_scale"] == 100 and ui["app_default_page"] == "meter"
    assert ui["character_auto_open"] is False and ui["character_auto_refresh"] is False
    chosen = {"app_text_scale": 90, "app_default_page": "character", "character_auto_open": True, "character_auto_refresh": True}
    assert _clean(chosen) == chosen                                 # a settings backup carries them
    for bad in ({"app_text_scale": 60}, {"app_text_scale": 160}, {"app_text_scale": "big"},
                {"app_default_page": "nowhere"}, {"character_auto_open": "yes"}, {"character_auto_refresh": 1}):
        with pytest.raises(ValueError):
            _clean(bad)


def test_the_pages_offered_at_launch_are_the_navigations_pages():
    nav = tuple(dict.fromkeys(re.findall(r'href="#/([a-z]+)"', _read("index.html"))))
    assert nav == APP_PAGES                                         # the same ids in the same order, Live Meter first
    pages = re.search(r"const PAGES = \[(.*?)\];", _read("app.js"), re.S).group(1)
    assert tuple(re.findall(r'\["([a-z]+)", "', pages)) == APP_PAGES


def test_the_ui_route_validates_and_stores_them(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(body):
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/ui", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    try:
        saved = post({"app_text_scale": 80, "app_default_page": "character", "character_auto_open": True,
                      "character_auto_refresh": True, "overlay_show_shugo_keys": False})
        assert (saved["app_text_scale"], saved["app_default_page"]) == (80, "character")
        assert saved["character_auto_open"] is True and saved["character_auto_refresh"] is True
        assert saved["overlay_show_shugo_keys"] is False
        assert server.ui_settings()["app_default_page"] == "character"
        for bad in ({"app_text_scale": 50}, {"app_text_scale": 100.5}, {"app_default_page": "nowhere"},
                    {"character_auto_open": "yes"}):
            with pytest.raises(urllib.error.HTTPError):
                post(bad)
        assert server.ui_settings()["app_text_scale"] == 80
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_app_applies_them_at_launch_and_offers_them_in_settings():
    app = _read("app.js")
    # Launch: the text size is applied before the first page, and an empty hash opens the chosen page.
    assert 'document.body.style.zoom = pct === 100 ? "" : String(pct / 100);' in app
    assert "applyTextScale(S.ui);" in app
    assert 'if (!location.hash && page !== "meter") { location.hash = "/" + page; return; }' in app
    # Settings → App & data: the four controls and what each saves.
    assert 'id="textscale"' in app and 'api("/api/ui", { app_text_scale: v })' in app
    assert 'id="defaultpage"' in app and 'api("/api/ui", { app_default_page: $("#defaultpage").value })' in app
    assert 'id="char-auto-open"' in app and 'api("/api/ui", { character_auto_open: $("#char-auto-open").checked })' in app
    assert 'id="char-auto-refresh"' in app and 'api("/api/ui", { character_auto_refresh: $("#char-auto-refresh").checked })' in app
    assert "1920×1080" in app and "not maximized" in app              # the window note under Open as its own window
    # My Character: the newest import opens once per app session, from its snapshot unless the refresh is on.
    assert "ui.character_auto_open && known.length && !st.autoOpened" in app
    assert "ui.character_auto_refresh ? 0 : 10 * 365 * 86400" in app
    assert "cache ? { ...h, cache } : h" in app
    with open(os.path.join(STATIC, "..", "server.py"), encoding="utf-8") as fh:
        assert 'use_cache=float(body.get("cache", 0))' in fh.read()


def test_the_capture_diagnostics_and_game_version_notes_start_folded():
    app, css = _read("app.js"), _read("app.css")
    assert '<details class="note" style="margin-top:10px"><summary><b>Capture diagnostics</b>' in app
    assert '<details class="note small"><summary id="mautometa-sum">' in app
    assert '<div id="mautometa" role="status"></div></details>' in app
    assert "<details open" not in app and 'class="note" open' not in app
    assert '$("#mautometa-sum").textContent' in app               # the installed version reads while folded
    assert "details.note > summary { cursor: pointer; }" in css
