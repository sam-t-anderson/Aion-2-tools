"""World (server) names instead of numbers, everywhere a recording's server shows.

The bundled official server list (``aion2calc/meter/a2parser/data/servers.json``) is rendered by
``tools/export_server_names.py`` into ``aion2calc/app/static/server-names.js`` (``window.A2Servers``),
so the app, the overlay, the GitHub Pages site and the log server's pages resolve 2102 -> "Zikel"
without a request. These tests keep the script current with the list, wired into every page that
shows a server, and used by the scripts that used to print the number."""
import importlib.util
import json
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
SITE = ROOT / "site"
SCRIPT = STATIC / "server-names.js"
LIST = ROOT / "aion2calc" / "meter" / "a2parser" / "data" / "servers.json"


def _tool():
    spec = importlib.util.spec_from_file_location("export_server_names", ROOT / "tools" / "export_server_names.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _node(probe: str) -> str:
    env = {**os.environ, "TZ": "UTC"}
    return subprocess.run(["node", "-e", probe], capture_output=True, text=True, check=True, env=env).stdout.strip()


def test_the_script_is_generated_from_the_bundled_list():
    tool = _tool()
    assert SCRIPT.read_text(encoding="utf-8") == tool.render(), "run tools/export_server_names.py after changing servers.json"
    names = tool.names()
    table = json.loads(LIST.read_text(encoding="utf-8"))["servers"]
    assert names["2102"] == "Zikel" and len(names) == len(table) and set(names) == set(table)
    assert list(names) == sorted(names, key=int)                       # numeric ID order: stable diffs


def test_the_script_agrees_with_the_python_lookup():
    from aion2calc.meter.a2parser.lookup import server_name
    names = _tool().names()
    for sid in ("1001", "2102", "2550", "1510"):
        assert names[sid] == server_name(int(sid))


def test_the_script_resolves_ids_like_a_page_does():
    probe = ("global.window = {}; require(%s); const S = window.A2Servers;"
             "console.log(JSON.stringify([S.name(2102), S.name(' 2102 '), S.name(99999), S.name(null), S.label(2102), S.label(99999),"
             " S.label(99999, 'Server 99999'), S.label(''), S.label(null, 'x'), Object.keys(S.names).length]))" % json.dumps(str(SCRIPT)))
    assert json.loads(_node(probe)) == ["Zikel", "Zikel", None, None, "Zikel", "server 99999", "Server 99999", "", "x", 616]


@pytest.mark.parametrize("page, src", [
    (STATIC / "index.html", "/static/server-names.js"), (STATIC / "overlay.html", "/static/server-names.js"),
    (SITE / "logs.html", "static/server-names.js"), (SITE / "log.html", "static/server-names.js"),
    (SITE / "leaderboard.html", "static/server-names.js"), (SITE / "timers.html", "static/server-names.js"),
    (SITE / "builds.html", "static/server-names.js"),
])
def test_every_page_that_shows_a_server_loads_the_script(page, src):
    html = page.read_text(encoding="utf-8")
    assert f'<script src="{src}"></script>' in html


def test_the_pages_build_copies_the_script():
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert pages.count("aion2calc/app/static/server-names.js") == 2            # the trigger path and the deploy copy


@pytest.mark.parametrize("path, needle", [
    ("community.js", "· ${esc(worldFor(x.server))}"),                            # All matching public attempts: Character · server
    ("combat-review.js", 'worldFor(e.server, e.server_name)'),                   # player labels in the review
    ("combat-review.js", "Server ${esc(worldFor(snapshot.identity?.server))}"),  # the saved profile's server line
    ("app.js", 'worldFor(who.serverId, "server "+who.serverId)'),                # the Live Meter identity line
    ("overlay.js", "A2Servers.label(doc.server,'server '+doc.server)"),          # field-boss tips on the overlay
    ("timers.js", "worldFor(k.server,'Server '+k.server)"),                      # field-boss kill rows
    ("timers.js", "worldFor(identified.server,'server '+identified.server)"),    # the identified-server line
    ("character-view.js", "A2Servers.name(profile.serverId)"),                   # a profile that carries only the ID
    ("identity.js", "esc(worldFor(r.server_name))"),                             # Your characters: a claim's server is its ID
])
def test_the_scripts_show_the_world_name(path, needle):
    assert needle in (STATIC / path).read_text(encoding="utf-8")


def test_the_number_no_longer_shows_where_a_name_is_known():
    assert '" · server "+who.serverId+(worldName' not in (STATIC / "app.js").read_text(encoding="utf-8")
    assert '" · " + e.server + (e.server_name' not in (STATIC / "combat-review.js").read_text(encoding="utf-8")
    assert "· ${esc(x.server)}" not in (STATIC / "community.js").read_text(encoding="utf-8")
