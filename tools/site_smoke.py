"""Build the public site the way .github/workflows/pages.yml does, open every page in Chromium, and fail
on what a visitor would notice.

For every page, at desktop width and at phone width (390 px):
  - each file the page loads from the site exists (no 404 from the site itself);
  - no script error and nothing logged as an error by the page;
  - one main heading (h1);
  - on a phone nothing scrolls sideways, even with a wide table on the page;
  - on a phone the header's name and buttons share one row, and the opened menu lists the pages one under
    another;
  - with --axe, axe-core reports no serious or critical accessibility problem, in the light theme and
    again in the dark one.
Requests to any other site are blocked, so the check never depends on the log server or a third party.
The Maps page must not contact the interactive-map provider until the visitor asks for the map, a log
page must offer the log server's own link for the log (its preview shows the fight) and, for a PvP fight, its
opponent's side of the fight under Player (checked with axe-core too), the Logs page's
Completed-run speed tab must name a run's bosses and show its time, the Class stats page's spread graph
must end its axis past the highest 90th percentile rather than at one best parse, and the Gathering page must
show everyone's drop rates, each kind of node with where it grows, only the dungeons whose cubes held a
crafting material, and, signed in, the account's own records.
The Logs page's featured encounters
must sit two side by side on a 1080p screen and one under another on a phone. A log's replay must open in the
Raid Planner as itself, asking first about a plan the visitor worked on.

    python tools/site_smoke.py [--axe node_modules/axe-core/axe.min.js] [--out DIR] [--keep]

Needs Playwright with Chromium (pip install playwright, python -m playwright install chromium) and
PyYAML. Exits non-zero and lists the problems when any check fails.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PREFIX = "/Aion-2-tools/"          # GitHub Pages serves the site under the repository name
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1366, "height": 900}
MAP_PROVIDER = "interactivemap.app"


def assemble(out: pathlib.Path) -> None:
    """Run pages.yml's own "Assemble the site" step, so this checks exactly what gets published."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["build"]["steps"]
    script = next(s["run"] for s in steps if s.get("name") == "Assemble the site")
    with tempfile.TemporaryDirectory() as work:
        subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=ROOT, check=True,
                       env={**os.environ, "HOME": work})
    built = ROOT / "_site"
    if out.exists():
        shutil.rmtree(out)
    shutil.move(str(built), out)
    # pages.yml writes config.js from repository settings; an empty server keeps every page offline here
    (out / "config.js").write_text('window.A2CONFIG = {"server": "", "key": ""};\n', encoding="utf-8")


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the built site under PREFIX, like GitHub Pages; anything else is a 404."""

    def translate_path(self, path):
        clean = urllib.parse.urlsplit(path).path
        if not clean.startswith(PREFIX):
            return str(pathlib.Path(self.directory) / "__outside_the_site__")
        return super().translate_path("/" + clean[len(PREFIX):])

    def log_message(self, *args):
        pass


def serve(site: pathlib.Path):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}{PREFIX}"


WIDE_TABLE = """() => {
  const main = document.querySelector('main');
  const t = document.createElement('table');
  t.className = 't'; t.id = '__smoke_wide__';
  const cells = Array.from({length: 12}, (_, i) => '<td>Column ' + i + ' with a long value</td>').join('');
  t.innerHTML = '<tr>' + cells + '</tr>';
  main.appendChild(t);
  const over = document.documentElement.scrollWidth - window.innerWidth;
  t.remove();
  return over;
}"""


# How far apart, top to bottom, the header's visible parts other than the menu sit (0 on one row).
PHONE_HEADER = """() => {
  const tops = [...document.querySelector('.topbar').children]
    .filter(e => !e.matches('.nav') && getComputedStyle(e).display !== 'none').map(e => e.getBoundingClientRect().top);
  return Math.max(...tops) - Math.min(...tops);
}"""
PHONE_MENU = """() => [...document.querySelectorAll('.topbar > .nav a')].map(a => {
  const r = a.getBoundingClientRect(); return [r.left, r.top]; })"""


def check_page(context, base: str, name: str, viewport: dict, axe: str | None, problems: list, scheme: str = "light") -> None:
    page = context.new_page()
    page.set_viewport_size(viewport)
    label = f"{name} ({viewport['width']}px{', dark' if scheme == 'dark' else ''})"
    external, local_errors, logged = [], [], []

    def route(r):
        host = urllib.parse.urlsplit(r.request.url).hostname
        if host in ("127.0.0.1", "localhost") or r.request.url.startswith(("data:", "blob:", "about:")):
            r.continue_()
        else:
            external.append(r.request.url)
            r.abort()

    page.route("**/*", route)
    page.on("response", lambda resp: local_errors.append(f"{resp.status} {resp.url}")
            if resp.url.startswith(base) and resp.status >= 400 else None)
    page.on("pageerror", lambda err: logged.append(f"script error: {err}"))

    def console(msg):
        if msg.type != "error":
            return
        where = (msg.location or {}).get("url", "")
        if where and not where.startswith(base):
            return                                   # a blocked request to another site
        if "net::ERR_FAILED" in msg.text or "ERR_BLOCKED_BY_CLIENT" in msg.text:
            return
        logged.append(f"console error: {msg.text}")

    page.on("console", console)
    page.goto(base + name, wait_until="load")
    page.wait_for_timeout(1500)
    for line in local_errors:
        problems.append(f"{label}: missing file {line}")
    for line in logged:
        problems.append(f"{label}: {line}")
    if page.locator("h1").count() != 1:
        problems.append(f"{label}: has {page.locator('h1').count()} main headings (h1), expected 1")
    if viewport is PHONE:
        over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        if over > 1:
            problems.append(f"{label}: the page scrolls sideways by {over}px on a phone")
        elif page.locator("main").count():
            over = page.evaluate(WIDE_TABLE)
            if over > 1:
                problems.append(f"{label}: a wide table makes the page scroll sideways by {over}px on a phone")
        toggle = page.locator(".topbar .navtoggle")
        if toggle.count():
            if page.evaluate(PHONE_HEADER) > 10:
                problems.append(f"{label}: the header's name and buttons take more than one row on a phone")
            toggle.click()
            links = page.evaluate(PHONE_MENU)
            if not links or any(abs(left - links[0][0]) > 1 for left, _ in links) or any(
                    below <= above for (_, above), (_, below) in zip(links, links[1:])):
                problems.append(f"{label}: the opened menu does not list the pages one under another")
            toggle.click()
    if any(MAP_PROVIDER in url for url in external):
        problems.append(f"{label}: contacted {MAP_PROVIDER} before the visitor asked for the map")
    if axe and viewport is DESKTOP:
        page.add_script_tag(path=axe)
        result = page.evaluate("""async () => {
            const r = await axe.run(document, {resultTypes: ['violations']});
            return r.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
                    .map(v => ({id: v.id, impact: v.impact, help: v.help,
                                nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}));
        }""")
        for v in result:
            problems.append(f"{label}: accessibility ({v['impact']}) {v['id']}: {v['help']} — {', '.join(v['nodes'])}")
    page.close()


def check_maps_button(context, base: str, problems: list) -> None:
    """The map loads once the visitor presses the button."""
    page = context.new_page()
    asked = []
    page.route("**/*", lambda r: (asked.append(r.request.url), r.abort())
               if MAP_PROVIDER in r.request.url else
               (r.continue_() if urllib.parse.urlsplit(r.request.url).hostname in ("127.0.0.1", "localhost")
                else r.abort()))
    page.goto(base + "maps.html", wait_until="load")
    button = page.get_by_role("button", name="Load the interactive map")
    if not button.count():
        problems.append("maps.html: no 'Load the interactive map' button")
    else:
        button.first.click()
        page.wait_for_timeout(800)
        if not any(MAP_PROVIDER in url for url in asked):
            problems.append("maps.html: pressing 'Load the interactive map' did not load the map")
    page.close()


SHARED_LOG = {"format": "a2log", "version": 1, "meta": {"source": "site-smoke", "title": "Boss fight"},
              "players": [{"id": "a", "name": "Sorc", "class": "Sorcerer"}],
              "segments": [{"label": "Boss", "boss": "Boss", "duration": 10,
                            "hits": [{"t": i, "player": "a", "skill": "Hellfire", "damage": 1000} for i in range(10)]}]}


def check_log_share(browser, base: str, problems: list) -> None:
    """A log page offers the log server's own link for the log, which chat apps preview with the fight."""
    context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    server = "https://logs.example"

    def route(r):
        url = r.request.url
        if url.endswith("/config.js"):
            r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
        elif url.startswith(server + "/api/v1/logs/abcdef12/raw"):
            r.fulfill(content_type="application/json", body=json.dumps(SHARED_LOG),
                      headers={"Access-Control-Allow-Origin": "*"})
        elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
            r.continue_()
        else:
            r.abort()

    context.route("**/*", route)
    page = context.new_page()
    page.goto(base + "log.html?id=abcdef12", wait_until="load")
    button = page.locator("#share-log")
    try:
        button.wait_for(state="visible", timeout=8000)
        button.click()
        page.wait_for_function("document.getElementById('share-msg').textContent.length > 0")
        copied = page.evaluate("navigator.clipboard.readText()")
        if copied != server + "/l/abcdef12":
            problems.append(f"log.html: Copy share link copied {copied!r}, expected the server's /l/ link")
    except Exception as exc:                     # the page never offered the button
        problems.append(f"log.html: no working Copy share link ({str(exc).splitlines()[0]})")
    context.close()


# A shared fight with recorded movement: its replay offers "Open in Raid Planner".
MOVING_LOG = {"format": "a2log", "version": 1, "meta": {"source": "site-smoke", "title": "Boss fight"},
              "players": [{"id": "a", "name": "Sorc", "class": "Sorcerer"}],
              "segments": [{"label": "Testboss", "boss": "Testboss", "duration": 20,
                            "entities": [{"id": "boss", "name": "Testboss", "kind": "enemy", "is_boss": True}],
                            "hits": [{"t": i, "player": "a", "skill": "Hellfire", "damage": 1000, "target": "boss"} for i in range(20)],
                            "movement": [{"t": float(t), "entity": "boss", "x": 1000.0 + 10 * t, "y": 1000.0, "z": 0.0, "src": "move"} for t in range(20)]
                            + [{"t": float(t), "entity": "a", "x": 900.0, "y": 900.0 + 5 * t, "z": 0.0, "src": "move"} for t in range(0, 20, 2)]}]}


def check_replay_to_planner(browser, base: str, problems: list) -> None:
    """A log's replay opens in the Raid Planner as itself (until 0.2.372 the planner showed the plan it last showed,
    "My first plan"), and a plan the visitor worked on is asked about first and kept when asked to."""
    context = browser.new_context()
    server = "https://logs.example"

    def route(r):
        url = r.request.url
        if url.endswith("/config.js"):
            r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
        elif url.startswith(server + "/api/v1/logs/abcdef12/raw"):
            r.fulfill(content_type="application/json", body=json.dumps(MOVING_LOG), headers={"Access-Control-Allow-Origin": "*"})
        elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
            r.continue_()
        else:
            r.abort()

    context.route("**/*", route)
    page = context.new_page()
    name = lambda: page.locator("#rname").input_value()                     # noqa: E731
    try:
        page.goto(base + "planner.html", wait_until="load")
        page.wait_for_selector("#rname", timeout=8000)
        if name() != "My first plan":
            problems.append(f"planner.html: a first visit shows {name()!r}, not the starter plan")
        page.goto(base + "log.html?id=abcdef12", wait_until="load")
        page.locator("[data-replay] [data-plan]").click(timeout=8000)
        page.wait_for_url("**/planner.html", timeout=8000)
        page.wait_for_selector("#rname", timeout=8000)
        if name() != "Testboss":
            problems.append(f"planner.html: Open in Raid Planner showed {name()!r}, not the replay")
        page.fill("#rname", "Worked plan")
        page.locator("#rname").dispatch_event("change")
        page.goto(base + "log.html?id=abcdef12", wait_until="load")
        page.locator("[data-replay] [data-plan]").click(timeout=8000)
        ask = page.locator(".rp-ask")
        ask.wait_for(timeout=8000)
        ask.locator('[data-choice="keep"]').click()
        page.wait_for_url("**/planner.html", timeout=8000)
        page.wait_for_selector("#rname", timeout=8000)
        plans = page.locator("#rplan option").all_inner_texts()
        if name() != "Testboss" or not any(p.startswith("Worked plan") for p in plans):
            problems.append(f"planner.html: after Keep the planner shows {name()!r} with the plans {plans!r}")
    except Exception as exc:
        problems.append(f"log.html → planner.html: the replay did not open in the Raid Planner ({str(exc).splitlines()[0]})")
    context.close()


# A one-against-one PvP fight as the log server sends it without its analysis: each side's hits on the other and a
# death of each.
PVP_LOG = {"format": "a2log", "version": 1, "meta": {"source": "site-smoke", "title": "Arena match"},
           "players": [{"id": "a", "name": "Templ", "class": "templar"}],
           "segments": [{"label": "Combat 1", "duration": 20, "encounter_type": "pvp_arena",
                         "entities": [{"id": "foe", "name": "Rang", "kind": "enemy", "is_player": True, "class": "Ranger"}],
                         "hits": [{"t": i + 13, "player": "a", "target": "foe", "skill": "Vicious Strike", "skill_id": 12010000, "damage": 1000} for i in range(6)],
                         "events": [{"t": i + 0.5, "kind": "damage", "source": "foe", "target": "a", "skill": "Tempest Shot", "skill_id": 14340000, "amount": 800}
                                    for i in range(12)]
                         + [{"t": 12.0, "kind": "death", "target": "a", "source": "foe"}]
                         + [{"t": i + 13.0, "kind": "damage", "source": "a", "target": "foe", "skill": "Vicious Strike", "skill_id": 12010000, "amount": 1000}
                            for i in range(6)]
                         + [{"t": 18.5, "kind": "death", "target": "foe", "source": "a"}]}]}


def check_pvp_opponent(browser, base: str, axe: str | None, problems: list) -> None:
    """A PvP log's page offers its opponent under Player, and the opponent chosen shows their side of the fight: whom
    they struck and who struck them, and the recap of their death, with no script error and, with --axe, no serious
    accessibility problem in the light theme or the dark one."""
    server = "https://logs.example"

    def route(r):
        url = r.request.url
        if url.endswith("/config.js"):
            r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
        elif url.startswith(server + "/api/v1/logs/abcdef12/raw"):
            r.fulfill(content_type="application/json", body=json.dumps(PVP_LOG), headers={"Access-Control-Allow-Origin": "*"})
        elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
            r.continue_()
        else:
            r.abort()

    for scheme in ("light", "dark") if axe else ("light",):
        label = f"log.html (a PvP opponent{', dark' if scheme == 'dark' else ''})"
        context = browser.new_context(color_scheme=scheme, viewport=DESKTOP)
        context.route("**/*", route)
        page, errors = context.new_page(), []
        page.on("pageerror", lambda err: errors.append(f"script error: {err}"))
        try:
            page.goto(base + "log.html?id=abcdef12", wait_until="load")
            page.wait_for_selector('[data-control="actor"] optgroup[label="Opponents"]', state="attached", timeout=8000)
            page.select_option('[data-control="actor"]', "foe")
            card = page.locator("[data-opponent]")
            card.wait_for(timeout=8000)
            text = " ".join(card.inner_text().split())
            if "Opponent · Rang" not in text or "9,600 100.0% 12" not in text or "6,000 100.0% 6" not in text:
                problems.append(f"{label}: the opponent's side reads {text[:300]!r}")
            page.click('[data-metric="deaths"]')
            if "18.500s" not in page.locator(".cr-review").inner_text():
                problems.append(f"{label}: no recap of the opponent's death")
            if axe:
                page.add_script_tag(path=axe)
                found = page.evaluate("""async () => {
                    const r = await axe.run(document, {resultTypes: ['violations']});
                    return r.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
                            .map(v => `${v.impact} ${v.id}: ${v.help} — ${v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(', ')}`);
                }""")
                problems += [f"{label}: accessibility {v}" for v in found]
        except Exception as exc:                     # the page never offered the opponent
            problems.append(f"{label}: no opponent's side of the fight ({str(exc).splitlines()[0]})")
        problems += [f"{label}: {e}" for e in errors]
        context.close()


# One run of the log server's /api/v1/run-leaderboard, as the server sends it: the route by catalog key, each
# boss named in its attempts, and the ranked entry-to-final-boss time in elapsed_seconds.
SPEED_RUN = {"log": "abcdef12", "id": "1", "rank": 1, "count": 2, "boss_route": ["npc:2340616"], "elapsed_seconds": 150.5,
             "party_size": 5, "encounter_type": "transcendence", "difficulty": "stage 2", "instance_id": 600055,
             "attempts": [{"boss": "Gelcos", "boss_key": "npc:2340616", "outcome": "kill"}],
             "progression": [{"boss": "Gelcos", "boss_key": "npc:2340616", "kills": 1}]}


def check_run_speed(browser, base: str, problems: list) -> None:
    """The Logs page's Completed-run speed tab names each run's bosses and shows its time."""
    context = browser.new_context()
    server = "https://logs.example"

    def route(r):
        url = r.request.url
        if url.endswith("/config.js"):
            r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
        elif url.startswith(server + "/api/v1/run-leaderboard"):
            r.fulfill(content_type="application/json", headers={"Access-Control-Allow-Origin": "*"},
                      body=json.dumps({"entries": [SPEED_RUN], "samples": 1, "truncated": False, "note": ""}))
        elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
            r.continue_()
        else:
            r.abort()

    context.route("**/*", route)
    page = context.new_page()
    page.goto(base + "logs.html", wait_until="load")
    try:
        page.click('[data-tab="speed"]')
        page.wait_for_selector("#speed-body table", timeout=8000)
        row = page.locator("#speed-body tr").nth(1).inner_text()
        for want in ("Gelcos", "Transcendence · stage 2", "2:31", "1 of 2"):
            if want not in row:
                problems.append(f"logs.html: the Completed-run speed row reads {row!r}, without {want!r}")
    except Exception as exc:
        problems.append(f"logs.html: no Completed-run speed table ({str(exc).splitlines()[0]})")
    context.close()


# Two classes as the log server's /api/v1/stats/<class> sends them, the first with a best parse three times its
# 90th percentile (the live server's assassins had one of 156,833 against 52,489).
STATS = {"assassin": {"median": 19000.0, "p25": 8000.0, "p75": 33000.0, "p90": 52000.0, "max": 157000.0},
         "cleric": {"median": 6400.0, "p25": 3700.0, "p75": 10500.0, "p90": 15900.0, "max": 30000.0}}
SPREAD = """() => [...document.querySelectorAll('svg[data-spread]')].map(svg => ({
  median: +svg.querySelector('line[data-median]').getAttribute('x1'),
  box: [+svg.querySelector('rect').getAttribute('x'), +svg.querySelector('rect').getAttribute('x') + +svg.querySelector('rect').getAttribute('width')],
  ticks: [...svg.querySelectorAll('line:not([data-median]):not(.crs)')].map(l => +l.getAttribute('x1')),
  past: !!svg.querySelector('path[data-past]') }))"""


def check_stats_spread(browser, base: str, problems: list) -> None:
    """The Class stats page's spread graph uses its width: the shared axis ends past the highest 90th percentile,
    not at the single best parse, each median sits in its box, and a best past the axis is an arrow. A class's
    details show its healing per second."""
    context = browser.new_context()
    server = "https://logs.example"

    def route(r):
        url = r.request.url
        path = urllib.parse.urlsplit(url).path
        cors = {"Access-Control-Allow-Origin": "*"}
        if url.endswith("/config.js"):
            r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
        elif url.startswith(server) and path == "/api/v1/stats":
            r.fulfill(content_type="application/json", headers=cors, body=json.dumps(
                {"classes": [{"class": c, "observations": 500, "logs": 50, "best_dps": d["max"]} for c, d in STATS.items()]}))
        elif url.startswith(server) and path.startswith("/api/v1/stats/"):
            d = STATS.get(path.rsplit("/", 1)[1])
            hps = {"median": 2100.0, "p25": 900.0, "p75": 4200.0, "p90": 6800.0, "max": 15200.0, "observations": 480, "healed": 470}
            r.fulfill(content_type="application/json", headers=cors, status=200 if d else 404,
                      body=json.dumps({"observations": 500, "dps": d, "best_dps": d["max"], "hps": hps} if d else {"error": "not found"}))
        elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
            r.continue_()
        else:
            r.abort()

    context.route("**/*", route)
    page = context.new_page()
    page.goto(base + "stats.html", wait_until="load")
    try:
        page.wait_for_selector("svg[data-spread]", timeout=8000)
        head = page.locator("#stats-body th").nth(1).inner_text()
        if "0–60,000" not in head:                 # 52,000 × 1.1, rounded up to a round number
            problems.append(f"stats.html: the spread axis reads {head!r}, not 0–60,000 (past the highest 90th percentile)")
        bars = page.evaluate(SPREAD)
        for name, bar in zip(STATS, bars):
            if not bar["box"][0] <= bar["median"] <= bar["box"][1]:
                problems.append(f"stats.html: the {name} median ({bar['median']:.1f}) is outside its box {bar['box']}")
        if not bars or max(bars[0]["ticks"]) < 75:
            problems.append(f"stats.html: the widest spread's 90th percentile is not across the column ({bars[:1]})")
        if [b["past"] for b in bars] != [True, False]:
            problems.append(f"stats.html: a best past the axis should be an arrow, one inside it a tick ({bars})")
    except Exception as exc:
        problems.append(f"stats.html: no spread graph ({str(exc).splitlines()[0]})")
    # A class's details show its healing per second (log server 0.2.149), the overview does not
    if "HPS" in page.locator("#stats-body").text_content():
        problems.append("stats.html: the overview shows healing per second; it belongs to a class's details")
    page.goto(base + "stats.html?class=cleric", wait_until="load")
    try:
        page.wait_for_selector("#stats-body .kpis", timeout=8000)
        kpi = dict(zip(page.locator("#stats-body .kpi .k").all_text_contents(), page.locator("#stats-body .kpi .v").all_text_contents()))
        wanted = {"Median HPS": "2,100", "Top 25% HPS": "4,200", "Top 10% HPS": "6,800", "Best HPS": "15,200"}
        if any(kpi.get(k) != v for k, v in wanted.items()):
            problems.append(f"stats.html?class=cleric: healing per second reads {[(k, kpi.get(k)) for k in wanted]}, not {wanted}")
        note = page.locator("[data-hps-note]")
        if not note.count() or "470 of the 480 fights include healing" not in note.text_content():
            problems.append("stats.html?class=cleric: no note on which fights include healing")
    except Exception as exc:
        problems.append(f"stats.html?class=cleric: no class details ({str(exc).splitlines()[0]})")
    context.close()


# The log server's /api/v1/gathering/stats (everyone's drop rates) and /api/v1/account/gathering (a signed-in
# account's own records), as the server sends them; the characters are made up.
GATHERING_STATS = {"gathers": 51, "cubes": 5, "reporters": 3, "generated_at": 0,
                   "nodes": [{"node": 1550004, "name": "Orichalcum Ore", "gathers": 40, "reporters": 3,
                              "results": {"normal": 30, "better": 8, "failed": 2},
                              "items": [{"item": 610620013, "name": "Orichalcum Ore", "grade": "Common", "gathers": 30,
                                         "share": 0.75, "average": 1.0}],
                              "kinds": ["open_world"], "places": [{"name": "Altgard", "gathers": 40}]},
                             {"node": 1500062, "name": "Odyle", "gathers": 6, "reporters": 1, "results": {"normal": 6, "better": 0, "failed": 0},
                              "items": [{"item": 610610013, "name": "Odyle", "grade": "Common", "gathers": 6, "share": 1.0, "average": 1.0}],
                              "kinds": ["dungeon"], "places": [{"name": "Ferocious Horn Den (Conquest)", "gathers": 6}]},
                             {"node": 1550000, "name": "Odyle", "gathers": 5, "reporters": 1, "results": {"normal": 5, "better": 0, "failed": 0},
                              "items": [{"item": 610610013, "name": "Odyle", "grade": "Common", "gathers": 5, "share": 1.0, "average": 1.0}],
                              "kinds": ["open_world"], "places": [{"name": "Altgard", "gathers": 5}]}],
                   "dungeons": [{"instance": 600092, "name": "Ferocious Horn Den (Conquest)", "cubes": 5, "reporters": 2,
                                 "items": [{"item": 610511014, "name": "Wrathful Will", "grade": "Unique", "material": True,
                                            "cubes": 1, "share": 0.2, "average": 1.0}]},
                                {"instance": 600068, "name": "Shattered Arkanis (Transcendence 3)", "cubes": 1, "reporters": 1,
                                 "items": [{"item": 930100031, "name": "Kina", "grade": "Common", "material": False,
                                            "cubes": 1, "share": 1.0, "average": 100000.0}]}]}
ACCOUNT_GATHERING = {"gathers": 2, "gathered": 3, "cubes": 0, "results": {"normal": 1, "better": 1, "failed": 0},
                     "nodes": [{"node": 1550004, "name": "Orichalcum Ore", "gathers": 2, "results": {"normal": 1, "better": 1, "failed": 0},
                                "items": [{"item": 610620013, "name": "Orichalcum Ore", "grade": "Common", "gathers": 1, "count": 2, "share": 0.5},
                                          {"item": 610620014, "name": "Fine Orichalcum Ore", "grade": "Rare", "gathers": 1, "count": 1, "share": 0.5}]}],
                     "items": [], "dungeons": [],
                     "recent": [{"id": "a" * 24, "kind": "gather", "t": 1793000000, "place": "Altgard", "character": "Alpha", "item": 610620013,
                                 "name": "Orichalcum Ore", "grade": "Common", "count": 2, "result": "normal"}]}


def check_gathering(browser, base: str, problems: list) -> None:
    """The Gathering page shows everyone's drop rates, each kind of node with where it grows (two kinds of Odyle
    node read apart, 0.2.360) and only the dungeons whose cubes held a crafting material (0.2.372); a signed-in
    visitor sees their account's records too, and a signed-out one is told how to see them."""
    server = "https://logs.example"
    session = {"server": server, "token": "a2web_" + "s" * 32, "name": "Alpha"}
    for signed_in in (False, True):
        context = browser.new_context()

        def route(r):
            url = r.request.url
            path = urllib.parse.urlsplit(url).path
            cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "X-Account-Token, Content-Type"}
            if url.endswith("/config.js"):
                r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
            elif url.startswith(server) and r.request.method == "OPTIONS":
                r.fulfill(status=204, headers={**cors, "Access-Control-Allow-Methods": "GET, POST"})
            elif url.startswith(server) and path == "/api/v1/gathering/stats":
                r.fulfill(content_type="application/json", headers=cors, body=json.dumps(GATHERING_STATS))
            elif url.startswith(server) and path == "/api/v1/account/gathering" and r.request.headers.get("x-account-token") == session["token"]:
                r.fulfill(content_type="application/json", headers=cors, body=json.dumps(ACCOUNT_GATHERING))
            elif url.startswith(server) and path == "/api/v1/account" and signed_in:
                r.fulfill(content_type="application/json", headers=cors, body=json.dumps({"account": {"id": "a1", "name": "Alpha"}, "session": {}}))
            elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
                r.continue_()
            else:
                r.abort()

        context.route("**/*", route)
        if signed_in:
            context.add_init_script(f"try {{ localStorage.setItem('a2-account-v1', {json.dumps(json.dumps(session))}); }} catch (e) {{}}")
        label = "gathering.html" + (" (signed in)" if signed_in else "")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base + "gathering.html", wait_until="load")
        try:
            page.wait_for_selector(".gt-node", timeout=8000)
            headings = [" ".join(t.split()) for t in page.locator(".gt-node h3").all_text_contents()]
            if headings != ["Orichalcum Ore — open-world node 40 gathers · 3 players", "Odyle — dungeon node 6 gathers · 1 players",
                            "Odyle — open-world node 5 gathers · 1 players"]:
                problems.append(f"{label}: everyone's nodes read {headings!r}, not each with where it grows")
            found = [" ".join(t.split()) for t in page.locator(".gt-where").all_text_contents()]
            if found != ["Found in Altgard", "Found in Ferocious Horn Den (Conquest)", "Found in Altgard"]:
                problems.append(f"{label}: the nodes' places read {found!r}")
            # one card per dungeon and difficulty; a dungeon whose cubes held no crafting material is left out (0.2.372)
            page.get_by_role("tab", name="Dungeon materials").click()
            page.wait_for_selector(".gt-dungeon", timeout=8000)
            cards = [" ".join(t.split()) for t in page.locator(".gt-dungeon h3").all_text_contents()]
            if cards != ["Ferocious Horn Den (Conquest) 5 reward cubes · 2 players"]:
                problems.append(f"{label}: the dungeon materials read {cards!r}, not one card with materials")
            page.get_by_role("tab", name="Gathering").click()
            if signed_in:
                kpi = dict(zip(page.locator(".gt-kpis .kpi .k").all_text_contents(), page.locator(".gt-kpis .kpi .v").all_text_contents()))
                if kpi.get("Gathers") != "2" or not kpi.get("Better grade", "").startswith("1"):
                    problems.append(f"{label}: the account's totals read {kpi}, not 2 gathers with 1 better grade")
                page.get_by_role("tab", name="Your log").click()
                logged = " ".join(page.locator(".gt-log tbody").text_content().split())
                if "Orichalcum Ore ×2" not in logged or "Alpha" not in logged:
                    problems.append(f"{label}: the account's log reads {logged!r}")
            elif not page.locator(".gt-signin").count():
                problems.append(f"{label}: signed out, the page does not say how to see your own records")
        except Exception as exc:
            problems.append(f"{label}: no drop rates ({str(exc).splitlines()[0]})")
        problems.extend(f"{label}: script error: {e}" for e in errors)
        context.close()


def _featured(n: int, title: str) -> dict:
    team = {"key": f"party:t{n}", "kind": "party", "name": "Testlongname's party", "server": None, "region": "nae", "members": []}
    summary = {"progress": [{"team": team, "killed": 2, "phases": 2, "complete": True}], "speed": [{"team": team, "elapsed": 363.0}],
               "execution": [{"team": team, "seconds": 212.0, "deaths": 2}], "all_stars": {"dps": [], "tank": [], "support": []},
               "classes": {"dps": [{"class": "assassin", "median": 68787.0}], "tank": [], "support": []}, "teams": 1, "complete": 1, "pulls": 3}
    return {"id": f"fe_{n:010d}", "title": title, "boss": "Testboss", "boss_key": "npc:2390001", "difficulty": "Hard", "icon": "",
            "phases": [], "summary": summary}


FEATURED = {"featured": [_featured(1, "Testlord race"), _featured(2, "Testcave race")], "roles": {}, "note": ""}


def check_featured_layout(browser, base: str, problems: list) -> None:
    """The Logs page's featured encounters sit two side by side on a 1080p screen, with nothing scrolling sideways, and
    one under another on a phone (0.2.359)."""
    server = "https://logs.example"
    for viewport, side_by_side in (({"width": 1920, "height": 1080}, True), (PHONE, False)):
        context = browser.new_context(viewport=viewport)

        def route(r):
            url = r.request.url
            if url.endswith("/config.js"):
                r.fulfill(content_type="text/javascript", body=f'window.A2CONFIG = {{"server": "{server}", "key": ""}};')
            elif url.startswith(server) and urllib.parse.urlsplit(url).path == "/api/v1/featured":
                r.fulfill(content_type="application/json", headers={"Access-Control-Allow-Origin": "*"}, body=json.dumps(FEATURED))
            elif urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost") or url.startswith(("data:", "blob:")):
                r.continue_()
            else:
                r.abort()

        context.route("**/*", route)
        page = context.new_page()
        label = f"logs.html featured encounters ({viewport['width']}px)"
        page.goto(base + "logs.html", wait_until="load")
        try:
            page.wait_for_function("document.querySelectorAll('#featured .fe-zone').length === 2", timeout=8000)
            a, b = page.evaluate("""() => [...document.querySelectorAll('#featured .fe-zone')].map(z => {
                const r = z.getBoundingClientRect(); return {left: r.left, right: r.right, top: r.top, bottom: r.bottom}; })""")
            wide = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            if side_by_side and not (abs(a["top"] - b["top"]) < 1 and a["right"] <= b["left"] and b["right"] <= viewport["width"]):
                problems.append(f"{label}: the two encounters are not side by side ({a}, {b})")
            if not side_by_side and b["top"] < a["bottom"]:
                problems.append(f"{label}: the two encounters are not one under another ({a}, {b})")
            if wide > 1:
                problems.append(f"{label}: the page scrolls sideways by {wide}px")
        except Exception as exc:
            problems.append(f"{label}: no featured encounters ({str(exc).splitlines()[0]})")
        context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--axe", help="path to axe-core's axe.min.js, to run the accessibility checks")
    parser.add_argument("--out", help="build the site here (default: a temporary folder)")
    parser.add_argument("--keep", action="store_true", help="keep the built site")
    args = parser.parse_args()
    out = pathlib.Path(args.out) if args.out else pathlib.Path(tempfile.mkdtemp(prefix="aion2-site-")) / "site"
    assemble(out)
    pages = sorted(p.name for p in out.glob("*.html"))
    server, base = serve(out)
    problems: list[str] = []
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(color_scheme="light")
            for name in pages:
                for viewport in (DESKTOP, PHONE):
                    check_page(context, base, name, viewport, args.axe, problems)
            if args.axe:                                  # the dark theme has its own colours to check
                dark = browser.new_context(color_scheme="dark")
                for name in pages:
                    check_page(dark, base, name, DESKTOP, args.axe, problems, scheme="dark")
            if "maps.html" in pages:
                check_maps_button(context, base, problems)
            if "log.html" in pages:
                check_log_share(browser, base, problems)
                check_pvp_opponent(browser, base, args.axe, problems)
            if "log.html" in pages and "planner.html" in pages:
                check_replay_to_planner(browser, base, problems)
            if "logs.html" in pages:
                check_run_speed(browser, base, problems)
            if "stats.html" in pages:
                check_stats_spread(browser, base, problems)
            if "gathering.html" in pages:
                check_gathering(browser, base, problems)
            if "logs.html" in pages:
                check_featured_layout(browser, base, problems)
            browser.close()
    finally:
        server.shutdown()
        if not args.keep and not args.out:
            shutil.rmtree(out.parent, ignore_errors=True)
    print(f"Checked {len(pages)} pages at {DESKTOP['width']}px and {PHONE['width']}px"
          + (" with axe-core in the light and dark themes" if args.axe else "") + ".")
    if problems:
        print(f"{len(problems)} problem(s):")
        for line in problems:
            print("  - " + line)
        return 1
    print("No problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
