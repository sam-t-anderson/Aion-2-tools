"""App accent-colour presets (Settings → Accent colour) must stay wired end to
end: each non-default accent needs a dark rule plus both light overrides in
app.css, the early-apply bootstrap in index.html must whitelist them so there is
no flash, and app.js must expose the same accent list. Keeps a later edit from
shipping an accent that only half-applies."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / "aion2calc" / "app" / "static"
CSS = (ROOT / "app.css").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
APPJS = (ROOT / "app.js").read_text(encoding="utf-8")

ACCENTS = ["crimson", "emerald", "azure", "amethyst", "rose"]


def test_each_accent_has_dark_and_both_light_rules():
    for a in ACCENTS:
        # dark (bare), forced light, and OS-light (:not([data-theme=dark])).
        assert re.search(rf":root\[data-accent={a}\]\s*\{{", CSS), f"{a}: missing dark rule"
        assert f":root[data-accent={a}][data-theme=light]" in CSS, f"{a}: missing forced-light rule"
        assert f":root[data-accent={a}]:not([data-theme=dark])" in CSS, f"{a}: missing OS-light rule"


def test_accent_rules_set_the_core_vars():
    # Each accent rule must recolour at least the brand accent and link accent.
    for block in re.findall(r":root\[data-accent=\w+\][^{]*\{([^}]*)\}", CSS):
        assert "--gold:" in block and "--accent:" in block


def test_index_bootstraps_accent_without_flash():
    assert 'localStorage.getItem("accent")' in INDEX
    for a in ACCENTS:
        assert a in INDEX, f"{a} not whitelisted in index bootstrap"


def test_appjs_exposes_the_same_accents():
    m = re.search(r'const ACCENTS = \[([^\]]*)\]', APPJS)
    assert m, "ACCENTS list not found in app.js"
    listed = set(re.findall(r'"(\w+)"', m.group(1)))
    assert listed == {"gold", *ACCENTS}


SITE = pathlib.Path(__file__).resolve().parents[1] / "site"


def test_site_navigation_offers_the_same_accents():
    nav = (SITE / "navigation.js").read_text(encoding="utf-8")
    m = re.search(r'const accents=\[([^\]]*)\]', nav)
    assert m, "accents list not found in site navigation.js"
    listed = set(re.findall(r'"(\w+)"', m.group(1)))
    assert listed == {"gold", *ACCENTS}


def test_site_pages_bootstrap_accent_without_flash():
    pages = list(SITE.glob("*.html"))
    with_theme = [p for p in pages if 'localStorage.getItem("theme")' in p.read_text(encoding="utf-8")]
    assert with_theme, "no site pages with a theme bootstrap"
    for p in with_theme:
        assert 'localStorage.getItem("accent")' in p.read_text(encoding="utf-8"), f"{p.name} missing accent bootstrap"
