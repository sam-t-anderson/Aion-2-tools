"""The language of the app and the website (static/i18n.js and static/i18n/*.json): every catalog translates
the same English text, keeps its {0} placeholders and leaves nothing empty; every page loads the engine first,
and the website's build and the app's package carry the catalogs."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
LANGS = ("de", "fr", "es", "pt-BR", "ja")


def _catalog(lang):
    return {k: v for k, v in json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8")).items()
            if not k.startswith("_")}


def test_the_catalogs_translate_the_same_text_and_keep_their_placeholders():
    catalogs = {lang: _catalog(lang) for lang in LANGS}
    keys = set(catalogs["de"])
    assert len(keys) > 500
    for lang, catalog in catalogs.items():
        assert set(catalog) == keys, f"{lang} differs: {sorted(set(catalog) ^ keys)[:5]}"
        for source, text in catalog.items():
            assert isinstance(text, str) and text.strip(), (lang, source)
            assert sorted(re.findall(r"\{\d\}", source)) == sorted(re.findall(r"\{\d\}", text)), (lang, source, text)
            assert source == " ".join(source.split()), f"{source!r} is not normalised as i18n.js looks it up"
    # the languages offered are the ones with a catalog, and English needs none
    offered = re.findall(r'\["([a-zA-Z-]+)", "', (STATIC / "i18n.js").read_text(encoding="utf-8").split("const KEY")[0])
    assert offered == ["en", *LANGS]


def test_every_page_loads_the_engine_before_it_draws():
    app = (STATIC / "index.html").read_text(encoding="utf-8")
    head = app.split("</head>")[0]
    assert '<script src="/static/i18n.js"></script>' in head and 'id="lang-slot"' in app
    for page in sorted((ROOT / "site").glob("*.html")):
        text = page.read_text(encoding="utf-8")
        assert '<script src="static/i18n.js"></script>' in text.split("</head>")[0], page.name
    nav = (ROOT / "site" / "navigation.js").read_text(encoding="utf-8")
    assert "A2I18n.picker" in nav


def test_the_site_build_and_the_package_carry_the_catalogs():
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "aion2calc/app/static/i18n.js" in pages and "cp aion2calc/app/static/i18n/*.json _site/static/i18n/" in pages
    assert '"app/static/i18n/*"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_names_from_the_game_and_players_are_left_alone():
    view = (STATIC / "account-view.js").read_text(encoding="utf-8")
    # character, legion and log names are shown under translate="no", which i18n.js never touches
    for shown in ('<h2 translate="no">${esc(st.me.name)}', '<h3 translate="no">${esc(L.name)}',
                  '<td translate="no">${esc(m.character || "—")}', '<td translate="no">${esc(r.character || "—")}',
                  '<td translate="no">${esc(l.uploader || "—")}', 'translate="no">${esc(l.name)}</a>'):
        assert shown in view, shown
    engine = (STATIC / "i18n.js").read_text(encoding="utf-8")
    assert '[translate="no"]' in engine and "isContentEditable" in engine
