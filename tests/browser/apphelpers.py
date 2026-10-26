"""Helpers for the browser tests (see conftest.py): a page that reports what goes wrong on it, opening a
page of the app, and axe-core's findings."""


class Watch:
    """What went wrong on a page: script errors, errors it logged and the app's answers of 400 or more."""

    def __init__(self, base: str):
        self.base, self.problems, self.allowed = base, [], []

    def allow(self, text: str) -> None:
        """A problem the test expects (matched as a substring)."""
        self.allowed.append(text)

    def note(self, problem: str) -> None:
        self.problems.append(problem)

    def unexpected(self) -> list[str]:
        return [p for p in self.problems if not any(a in p for a in self.allowed)]


def open_context(browser, base: str, scheme: str = "dark", width: int = 1600):
    """A fresh browser profile (its own storage) that reaches only the app."""
    context = browser.new_context(viewport={"width": width, "height": 1000}, color_scheme=scheme)
    context.route("**/*", lambda r: r.continue_() if r.request.url.startswith((base, "data:", "blob:")) else r.abort())
    return context


def close_context(context) -> None:
    """Close a profile without its route handlers outliving it: a page that polls (the Live Meter) can have a
    request inside a test's handler as the test ends, and that handler would then fail the next test's first
    call on the closed context."""
    for page in context.pages:
        page.unroute_all(behavior="ignoreErrors")
    context.unroute_all(behavior="ignoreErrors")
    context.close()


def watched_page(context, base: str) -> tuple:
    page, watch = context.new_page(), Watch(base)
    page.on("pageerror", lambda err: watch.note(f"script error: {err}"))
    page.on("console", lambda msg: watch.note(f"console error: {msg.text}")
            if msg.type == "error" and "net::ERR_FAILED" not in msg.text else None)
    page.on("response", lambda resp: watch.note(f"{resp.status} {resp.url[len(base) - 1:]}")
            if resp.url.startswith(base) and resp.status >= 400 else None)
    return page, watch


def go(page, base: str, hash_: str) -> None:
    """Open the app on one of its pages, as a fresh launch does, and give the page a moment to draw."""
    if page.url != "about:blank":
        page.goto("about:blank")                    # a new hash alone would not reload the app
    page.goto(base + hash_, wait_until="load")
    page.wait_for_function("document.querySelector('#page-body') && document.querySelector('#page-body').children.length > 0")
    page.wait_for_timeout(1200)                     # its first requests (some pages poll, so no "network idle")


def until(page, done, timeout_ms: int = 10000):
    """Let the page run until done() is true or the time is up, and return done()'s last value: for what a test
    waits on outside the page (a request a route saw, a dialog), which a slow computer brings later."""
    for _ in range(timeout_ms // 100):
        result = done()
        if result:
            return result
        page.wait_for_timeout(100)
    return done()


def on_page(page, name: str) -> None:
    """Wait until the app shows the page with this name (its main heading)."""
    page.wait_for_function("name => (document.querySelector('#page-title') || {}).textContent === name", arg=name)


def axe_findings(page, axe_path: str, impacts=("serious", "critical")) -> list[str]:
    page.add_script_tag(path=axe_path)
    found = page.evaluate("""async () => {
        const r = await axe.run(document, {resultTypes: ['violations']});
        return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,
                                      nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}));
    }""")
    return [f"{v['impact']} {v['id']}: {v['help']} — {', '.join(v['nodes'])}" for v in found if v["impact"] in impacts]


def open_settings(page, base: str, section: str) -> None:
    """Open Settings afresh on one of its sections (the buttons above it: overlay, meter, system…)."""
    go(page, base, "#/settings")
    page.click(f'[data-settab="{section}"]')
    page.wait_for_selector(f'.setrow[data-g="{section}"]:not([hidden])')


def posted(page, action, path: str = "/api/ui") -> dict:
    """The JSON the page posts to ``path`` while ``action`` runs, once the app has answered it (leaving the
    page before then would cancel the request)."""
    import json
    with page.expect_request(lambda r: r.method == "POST" and r.url.split("?")[0].endswith(path)) as request:
        action()
    request.value.response()
    return json.loads(request.value.post_data or "{}")


def put_back(page, settings: dict) -> None:
    """Save settings as the page saves them, to put back what a test changed (the tests share one app)."""
    page.evaluate("settings => api('/api/ui', settings)", settings)
