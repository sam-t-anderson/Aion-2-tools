"""Opening the overlay when the app starts (on by default) must stay wired end to
end and distinct from `overlay_on_start` (which opens it when the *meter* starts).
The server defaults it on and accepts it, the backup round-trips it, the Settings
page offers it, and `serve()` honours it only on a real launch — never a headless
`--no-browser` render/CI server."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER = (ROOT / "aion2calc" / "app" / "server.py").read_text(encoding="utf-8")
BACKUP = (ROOT / "aion2calc" / "app" / "settings_backup.py").read_text(encoding="utf-8")
APPJS = (ROOT / "aion2calc" / "app" / "static" / "app.js").read_text(encoding="utf-8")
MAIN = (ROOT / "aion2calc" / "__main__.py").read_text(encoding="utf-8")

KEY = "overlay_open_on_app_start"


def test_server_defaults_it_on_and_accepts_it():
    assert f'"{KEY}"' in SERVER
    assert f'"{KEY}": True' in SERVER


def test_backup_round_trips_it_as_a_bool():
    assert f'"{KEY}"' in BACKUP


def test_settings_page_offers_and_saves_it():
    assert 'id="ov-open-on-app"' in APPJS
    assert '#ov-open-on-app' in APPJS and f'{KEY}:' in APPJS


def test_serve_honours_the_flag_only_on_a_real_launch():
    # serve() gates on both the open_overlay parameter and the stored setting.
    assert "open_overlay: bool = True" in SERVER
    assert f'open_overlay and ui_settings().get("{KEY}"' in SERVER
    # The app subcommand turns it off for a headless (--no-browser) server.
    assert "open_overlay=not args.no_browser" in MAIN


def test_distinct_from_meter_start_setting():
    # Both settings exist and are different keys.
    assert "overlay_on_start" in SERVER and KEY in SERVER
    assert KEY != "overlay_on_start"
