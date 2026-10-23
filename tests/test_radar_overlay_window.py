"""The Hidden Cube radar's own small overlay window (0.2.329): opened beside the meter overlay while the radar is
on, following the setting live, with its own opacity, Lock and a Hide that closes that window alone, and a
remembered position of its own; the meter overlay no longer draws the radar in the native host."""
import os
import time

import pytest

from aion2calc import overlay
from aion2calc.app import overlay_launch, server
from aion2calc.app.settings_backup import import_settings
from aion2calc.overlay_health import RelaunchLimiter

STATIC = os.path.join(os.path.dirname(__file__), "..", "aion2calc", "app", "static")


def _read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as fh:
        return fh.read()


class _Popen:
    def __init__(self, url):
        self.url = url
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self):
        while self.returncode is None:
            time.sleep(0.01)
        return self.returncode

    def terminate(self):
        self.returncode = 1


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    spawned = []
    monkeypatch.setattr(overlay_launch, "_spawn", lambda url: spawned.append(_Popen(url)) or spawned[-1])
    monkeypatch.setattr(overlay_launch, "available", lambda: True)
    flags = {"party": False, "radar": False}
    monkeypatch.setattr(overlay_launch, "_party_enabled", lambda: flags["party"])
    monkeypatch.setattr(overlay_launch, "_radar_enabled", lambda: flags["radar"])
    for slot in ("_PROCESS", "_PARTY_PROCESS", "_RADAR_PROCESS"):
        monkeypatch.setattr(overlay_launch, slot, None)
    monkeypatch.setattr(overlay_launch, "_URL", "")
    monkeypatch.setattr(overlay_launch, "_RELAUNCHES", RelaunchLimiter())
    overlay_launch._HIDDEN.clear()
    yield spawned, flags
    overlay_launch.close()


def _urls(spawned):
    return [p.url for p in spawned if p.poll() is None]


def test_the_radar_window_opens_with_the_overlay_while_the_radar_is_on(launcher):
    spawned, flags = launcher
    flags["radar"] = True
    assert overlay_launch.launch("http://127.0.0.1:1/overlay")["native"] is True
    assert _urls(spawned) == ["http://127.0.0.1:1/overlay", "http://127.0.0.1:1/overlay?view=radar"]
    overlay_launch.close()
    assert _urls(spawned) == []                                            # the app's close takes every window


def test_the_radar_window_follows_the_setting_while_the_overlay_is_open(launcher):
    spawned, flags = launcher
    overlay_launch.sync_companions()                                       # nothing open yet: nothing happens
    assert spawned == []
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    assert _urls(spawned) == ["http://127.0.0.1:1/overlay"]
    flags["radar"] = True
    overlay_launch.sync_companions()                                       # the radar turned on: its window opens
    assert _urls(spawned)[-1].endswith("?view=radar") and overlay_launch._RADAR_PROCESS is spawned[-1]
    overlay_launch.sync_companions()                                       # already open: no second one
    assert len(spawned) == 2
    flags["radar"] = False
    overlay_launch.sync_companions()                                       # turned off: its window closes, the meter's stays
    assert _urls(spawned) == ["http://127.0.0.1:1/overlay"] and overlay_launch._RADAR_PROCESS is None
    flags["party"] = True
    overlay_launch.sync_companions()                                       # the Party-DPS window follows its setting the same way
    assert _urls(spawned)[-1].endswith("?view=party")


def test_hide_on_the_radar_window_closes_it_alone_until_open_overlay_or_the_setting_flips(launcher):
    spawned, flags = launcher
    flags["radar"] = True
    overlay_launch.launch("http://127.0.0.1:1/overlay")
    overlay_launch.close_view("radar")
    assert _urls(spawned) == ["http://127.0.0.1:1/overlay"]
    overlay_launch.sync_companions()                                       # a sensitivity change must not bring it back
    assert _urls(spawned) == ["http://127.0.0.1:1/overlay"]
    overlay_launch.launch("http://127.0.0.1:1/overlay")                    # Open overlay does
    assert _urls(spawned)[-1].endswith("?view=radar")
    overlay_launch.close_view("radar")
    flags["radar"] = False
    overlay_launch.sync_companions()
    flags["radar"] = True
    overlay_launch.sync_companions()                                       # off and on again does too
    assert _urls(spawned)[-1].endswith("?view=radar")
    overlay_launch.close_view("meter")                                     # the meter overlay's Hide closes everything
    assert _urls(spawned) == []


def test_the_hide_route_tells_the_windows_apart():
    src = open(os.path.join(STATIC, "..", "server.py"), encoding="utf-8").read()
    assert 'close_view(view) if isinstance(view, str) and view in ("party", "radar") else close()' in src
    js = _read("overlay.js")
    assert 'body:JSON.stringify({action:"hide",view})' in js


def test_the_native_host_knows_the_radar_window(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    from aion2calc.paths import write_user_json
    assert overlay._overlay_prefs()["positions"] == {"meter": None, "party": None, "radar": None}
    write_user_json({"overlay_radar_pos_x": 300, "overlay_radar_pos_y": 40,
                     "overlay_radar_pos_layout": [[0, 0, 2560, 1440]]}, "ui.json")
    assert overlay._overlay_prefs()["positions"]["radar"] == {"xy": (300, 40), "layout": [[0, 0, 2560, 1440]]}
    assert overlay._view_key("radar") == "radar" and overlay._view_key(True) == "party" and overlay._view_key(False) == "meter"
    sent = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n=-1):
            return b"{}"
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: sent.append(req) or _Response())
    overlay._save_overlay_position("http://127.0.0.1:1", "radar", (300, 40), [(0, 0, 2560, 1440)])
    import json
    assert json.loads(sent[0].data) == {"overlay_radar_pos_x": 300, "overlay_radar_pos_y": 40, "overlay_radar_pos_layout": [[0, 0, 2560, 1440]]}
    overlay._save_overlay_position("http://127.0.0.1:1", True, (1, 2))
    assert json.loads(sent[1].data) == {"overlay_party_pos_x": 1, "overlay_party_pos_y": 2}
    # The radar's window may be narrower than the meter's (its card is 232 px wide).
    window = lambda: type("W", (), {"resize": lambda self, w, h: setattr(self, "size", (w, h))})()
    api = overlay._OverlayAPI(min_width=180)
    api._window = window()
    api.fit(232, 120)
    assert api._window.size == (232, 120)
    api = overlay._OverlayAPI()                                            # the meter's keeps its 260 px floor
    api._window = window()
    api.fit(232, 120)
    assert api._window.size == (260, 120)
    src = open(os.path.join(STATIC, "..", "..", "overlay.py"), encoding="utf-8").read()
    assert '"radar": "Aion 2 Calc Radar Overlay"' in src and 'min_size=(180 if party == "radar" else 260, 70)' in src


def test_the_radar_position_is_accepted_by_the_app_and_stays_out_of_backups(monkeypatch, tmp_path):
    monkeypatch.setenv("AION2CALC_HOME", str(tmp_path))
    src = open(os.path.join(STATIC, "..", "server.py"), encoding="utf-8").read()
    assert '("overlay_radar_pos_x", -30000, 30000), ("overlay_radar_pos_y", -30000, 30000)' in src
    assert '"overlay_radar_pos_layout"' in src
    result = import_settings({"overlay_radar_pos_x": 300, "overlay_radar_pos_y": 40, "overlay_remember_position": True})
    assert "overlay_radar_pos_x" not in result["settings"] and result["settings"]["overlay_remember_position"] is True


def test_the_overlay_page_draws_the_radar_in_its_own_window_only():
    js, css, html, app = _read("overlay.js"), _read("overlay.css"), _read("overlay.html"), _read("app.js")
    assert 'const partyMode = view === "party", radarMode = view === "radar";' in js
    assert 'document.getElementById("ov").classList.add("ov-radar")' in js
    assert 'const OPACITY_KEY = radarMode ? "ovopacity-radar" : "ovopacity";' in js      # its own opacity
    assert js.count("localStorage.getItem(OPACITY_KEY)") == 1 and js.count("localStorage.setItem(OPACITY_KEY, op)") == 1
    assert "radarOn=on&&(radarMode||(!partyMode&&!nativeHost));" in js       # the meter overlay draws it only in the browser fallback
    assert "setupRadar(radarSetting);   // in the native host the radar is drawn by its own window" in js
    assert "if(radarMode)return;                       // the radar's window shows the radar alone" in js
    assert 'id="ovviewtitle"' in html and 'vt.textContent="Hidden Cube radar"' in js
    assert "#ov.ov-radar .ovcard { width: var(--ov-width, 232px);" in css and "#ov.ov-radar #ovcapture" in css
    assert "#ov.ov-radar .ovtabs" in css and "#ov.ov-radar #ovcontent" in css        # nothing of the meter in it
    assert "The radar is its own small overlay window" in app
    # The radar's settings still reach the window: the server syncs the companions on every radar_ change.
    src = open(os.path.join(STATIC, "..", "server.py"), encoding="utf-8").read()
    assert "from .overlay_launch import sync_companions" in src
    ui = server.ui_settings()
    assert ui["radar_enabled"] is False
