"""Build the public site the way .github/workflows/pages.yml does, open every page in Chromium, and fail
on what a visitor would notice.

For every page, at desktop width and at phone width (390 px):
  - each file the page loads from the site exists (no 404 from the site itself);
  - no script error and nothing logged as an error by the page;
  - one main heading (h1);
  - on a phone nothing scrolls sideways, even with a wide table on the page;
  - with --axe, axe-core reports no serious or critical accessibility problem, in the light theme and
    again in the dark one.
Requests to any other site are blocked, so the check never depends on the log server or a third party.
The Maps page must not contact the interactive-map provider until the visitor asks for the map.

    python tools/site_smoke.py [--axe node_modules/axe-core/axe.min.js] [--out DIR] [--keep]

Needs Playwright with Chromium (pip install playwright, python -m playwright install chromium) and
PyYAML. Exits non-zero and lists the problems when any check fails.
"""
from __future__ import annotations

import argparse
import functools
import http.server
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
