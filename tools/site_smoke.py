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
page must offer the log server's own link for the log (its preview shows the fight), and the Logs page's
Completed-run speed tab must name a run's bosses and show its time.

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
            if "logs.html" in pages:
                check_run_speed(browser, base, problems)
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
