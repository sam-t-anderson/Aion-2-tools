"""The native window's colours are the web pages' (0.2.484, ``gui/theme.py``): for each theme (the computer's, light or
dark), each accent colour and the computer's own light or dark, every custom property the native palette reads from
app.css is the one Chromium computes on the app's own page."""
from aion2calc.gui import theme
from apphelpers import close_context, go, open_context, watched_page

READ = """([chosen, accent, names]) => {
    const root = document.documentElement;
    if (chosen === 'system') delete root.dataset.theme; else root.dataset.theme = chosen;
    if (accent === 'gold') delete root.dataset.accent; else root.dataset.accent = accent;
    const style = getComputedStyle(root);
    return names.map((name) => style.getPropertyValue('--' + name.replace(/_/g, '-')).trim());
}"""


def test_the_native_palettes_are_the_browsers(browser, app_url):
    for computer in ("dark", "light"):
        context = open_context(browser, app_url, scheme=computer)
        page, watch = watched_page(context, app_url)
        try:
            go(page, app_url, "#/meter")
            for chosen in theme.THEMES:
                for accent in theme.ACCENTS:
                    shown = computer if chosen == "system" else chosen
                    ours = theme.palette(shown, accent)
                    names = list(ours)
                    theirs = dict(zip(names, page.evaluate(READ, [chosen, accent, names])))
                    assert theirs == ours, (computer, chosen, accent, {k: (theirs[k], ours[k]) for k in ours
                                                                        if theirs[k] != ours[k]})
        finally:
            close_context(context)
        assert not watch.unexpected(), watch.unexpected()
