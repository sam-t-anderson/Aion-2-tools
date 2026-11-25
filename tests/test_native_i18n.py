"""The native window in the languages the web interface speaks (0.2.483, ``gui/i18n.py``): the web pages' own word
lists, a text looked up exactly as ``i18n.js`` looks it up (checked against ``i18n.js`` itself, run by Node), and the
window's texts shown in the language chosen where the web page has the same text in its words. The language is the
web pages' choice (``a2-lang``) in the app's interface data; choosing another draws the window again in it."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import shiboken6  # noqa: E402

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QListWidgetItem,  # noqa: E402
                               QPushButton, QTableWidget, QTableWidgetItem, QWidget)

from aion2calc.gui import i18n, interface  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aion2calc" / "app" / "static"
LANGS = [code for code, _name in i18n.LANGS if code != "en"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shown(qapp, monkeypatch):
    """The window's texts in a language for one test, its choices in a store of its own; English again after."""
    monkeypatch.setattr(interface, "_shared", interface._Shared())
    yield i18n.install
    i18n.uninstall()


def settle(done=lambda: True, rounds=200):
    for _ in range(rounds):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
        if done():
            return True
    return done()


def test_the_languages_are_the_web_pages():
    source = (STATIC / "i18n.js").read_text(encoding="utf-8")
    listed = re.search(r"const LANGS = (\[\[.*?\]\]);", source).group(1)
    assert [tuple(pair) for pair in json.loads(listed)] == list(i18n.LANGS)
    assert re.search(r'const KEY = "([^"]+)";', source).group(1) == i18n.KEY
    assert sorted(p.stem for p in (STATIC / "i18n").glob("*.json")) == sorted(LANGS)
    store = interface.InterfaceStore(shared=interface._Shared())
    assert i18n.language(store) == "en"                                       # nothing chosen
    store.setValue("a2-lang", "pt-BR")
    assert i18n.language(store) == "pt-BR"
    store.setValue("a2-lang", "klingon")                                      # not one of them
    assert i18n.language(store) == "en"


def _probes(catalog: dict) -> list[str]:
    """Each entry of a word list, its templates filled in, with the white space a page's text can have (JavaScript's
    own, written from its code points), and texts it has nothing for."""
    space, ideographic, bom, nbsp = " ", chr(0x3000), chr(0xFEFF), chr(0xA0)
    probes = []
    for key in catalog:
        if key.startswith("_"):
            continue
        filled = re.sub(r"\{(\d)\}", lambda m: ("Kaela", "7", "0.2.480", "Vakron Sky Island")[int(m.group(1))], key)
        probes += [key, filled, space * 2 + key + "\n", key.replace(" ", space * 3), ideographic + filled + nbsp,
                   bom + key, key.upper(), key + "!"]
    return probes + ["", "   ", "Kaela", "45.70K", "Page 2 of", "Signed in as", "of 3", "Combat 4 5"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node runs the web pages' own i18n.js")
def test_a_text_reads_in_each_language_as_the_web_page_reads_it(tmp_path):
    harness = tmp_path / "lookup.js"
    harness.write_text("""
        const fs = require("fs");
        const [script, folder, lang, probes, answer] = process.argv.slice(2);
        global.window = global;
        global.localStorage = {getItem: (key) => (key === "a2-lang" ? lang : null)};
        global.document = {currentScript: null, body: null, addEventListener() {},
                           documentElement: {lang: "", classList: {add() {}, remove() {}}}};
        global.MutationObserver = class { observe() {} };
        global.fetch = (url) => Promise.resolve({ok: true, json: () =>
            Promise.resolve(JSON.parse(fs.readFileSync(folder + "/" + url.split("/").pop(), "utf8")))});
        eval(fs.readFileSync(script, "utf8"));
        const parent = {nodeName: "DIV", isContentEditable: false, closest: () => null};
        window.A2I18n.ready.then(() => {
          const out = JSON.parse(fs.readFileSync(probes, "utf8")).map((text) => {
            const node = {nodeType: 3, nodeValue: text, parentElement: parent};
            window.A2I18n.translate(node);                       // as the page swaps a text it shows
            return [node.nodeValue, window.A2I18n.t(text, "Kaela", "7")];
          });
          fs.writeFileSync(answer, JSON.stringify(out));       // a pipe would lose what an exit cuts off
          process.exit(0);
        });""", encoding="utf-8")
    try:
        for lang in LANGS:
            catalog = json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
            probes = _probes(catalog)
            (tmp_path / "probes.json").write_text(json.dumps(probes), encoding="utf-8")
            subprocess.run(["node", str(harness), str(STATIC / "i18n.js"), str(STATIC / "i18n"), lang,
                            str(tmp_path / "probes.json"), str(tmp_path / "answer.json")],
                           capture_output=True, text=True, check=True, timeout=120)
            web = json.loads((tmp_path / "answer.json").read_text(encoding="utf-8"))
            assert i18n.install(lang) == lang
            ours = [[i18n._swap(text), i18n.t(text, "Kaela", "7")] for text in probes]
            differ = [(p, w, o) for p, w, o in zip(probes, web, ours) if w != o]
            assert not differ, (lang, len(differ), differ[:5])
            assert sum(w[0] != p for p, w in zip(probes, web)) > len(catalog) * 2     # most of them in its words
    finally:
        i18n.uninstall()


def test_the_word_lists_rules():
    catalog = i18n.Catalog({"_note": "not a word", "Save": "Speichern", "Empty": "", "Number": 3,
                            "{0} of {1}": "{1} — {0}", "Page {0} of {1}": "Seite {0} von {1}",
                            "a/b {0}": "slashes {0}", "a.b {0}": "dots {0}", "Only {2}": "nur {2} {0}"})
    assert catalog.lookup("  Save ") == "Speichern" and catalog.lookup("_note") is None
    assert catalog.lookup("Empty") is None and catalog.lookup("Number") is None and catalog.lookup("") is None
    assert catalog.lookup("Page 2 of 5") == "Seite 2 von 5"                   # the longer pattern first
    assert catalog.lookup("2 of 5") == "5 — 2"
    assert catalog.lookup("a/b x") == "slashes x" and catalog.lookup("axb x") is None   # "." is not "any character"
    assert catalog.lookup("Only you") == "nur you {0}"                        # a slot with no value stays
    # the patterns in the order JavaScript sorts them: by the length of their source, where a "/" is written "\/" (so
    # "a/b {0}" ties with "a.b {0}" and "Only {2}" and comes first, as listed), the ties as listed
    assert [p[2] for p in catalog.patterns] == ["Seite {0} von {1}", "{1} — {0}", "slashes {0}", "dots {0}",
                                                "nur {2} {0}"]
    assert i18n.fill("{0} and {1}, {2}", ["a", 0]) == "a and 0, {2}"
    assert i18n.norm(chr(0xFEFF) + " a" + chr(0x3000) + chr(0x2028) + "b " + chr(0xA0)) == "a b"
    assert i18n.norm(chr(0x85) + "a" + chr(0x1C)) == chr(0x85) + "a" + chr(0x1C)    # Python's, not JavaScript's


def test_the_windows_texts_in_the_language_chosen(shown):
    assert shown("de") == "de" and i18n.current() == "de"
    assert QLabel("Settings").text() == "Einstellungen"
    label = QLabel()
    label.setText("  Export settings ")
    assert label.text() == "  Einstellungen exportieren "                 # the white space around it kept
    assert QLabel("Theme\nLanguage").text() == "Design\nSprache"           # each line, as each text beside a <br>
    rich = QLabel("<b>Settings</b> &amp; <code>Save</code> <span translate=\"no\">Save</span> &lt;Clear&gt;")
    assert rich.text() == "<b>Einstellungen</b> &amp; <code>Save</code> <span translate=\"no\">Save</span> &lt;Clear&gt;"
    assert QLabel("<p>Profiles &amp; backup</p>").text() == "<p>Profile &amp; Sicherung</p>"
    assert QPushButton("Save").text() == "Speichern" and QCheckBox("Clear").text() == "Leeren"
    assert QPushButton("Profiles && backup").text() == "Profile && Sicherung"     # a button's "&" written "&&"
    box = QComboBox()
    box.addItem("public", "public")
    box.addItems(["private", "unlisted"])
    assert [box.itemText(i) for i in range(3)] == ["öffentlich", "privat", "nicht gelistet"] and box.itemData(0) == "public"
    field = QLineEdit()
    field.setText("Save")                                                  # what is typed stays as it is
    field.setPlaceholderText("Save")
    assert field.text() == "Save" and field.placeholderText() == "Speichern"
    widget = QWidget()
    widget.setToolTip("Settings")
    widget.setAccessibleName("Language")
    assert widget.toolTip() == "Einstellungen" and widget.accessibleName() == "Sprache"
    table = QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(["Save", "Kaela"])
    table.setItem(0, 0, QTableWidgetItem("Clear"))
    assert [table.horizontalHeaderItem(i).text() for i in range(2)] == ["Speichern", "Kaela"]
    assert table.item(0, 0).text() == "Leeren" and QListWidgetItem("Settings").text() == "Einstellungen"
    assert QLabel("Page 2 of 5").text() == "Seite 2 von 5" and QLabel("45.70K").text() == "45.70K"
    assert i18n.t("Page {0} of {1}", 2, 5) == "Seite 2 von 5" and i18n.t("Kaela {0}", 1) == "Kaela 1"
    # a name, or a value shown as it is sent, keeps its words
    kept = i18n.keep_english(QWidget())
    inside = QLabel(kept)
    inside.setText("Save")
    assert inside.text() == "Save" and QLabel("Save", kept).text() == "Save" and QPushButton("Save", kept).text() == "Save"
    with i18n.english():
        assert QLabel("Save").text() == "Save"
    assert QLabel("Save").text() == "Speichern"
    # English, and the Qt calls as they were
    i18n.uninstall()
    assert QLabel("Save").text() == "Save" and QPushButton("Settings").text() == "Settings"
    assert shown("klingon") == "en" and QLabel("Save").text() == "Save"


def test_the_main_window_in_a_language_and_another_chosen(shown, monkeypatch):
    from aion2calc.gui import window as native_window
    from aion2calc.gui.window import MainWindow
    monkeypatch.setattr(native_window.MainWindow, "start", lambda self: None)     # no app to read
    interface.store().setValue("a2-lang", "de")
    shown(i18n.language())
    first = MainWindow(None)
    nav = [first.nav.item(i).text() for i in range(first.nav.count())]
    assert nav[:4] == ["KAMPF", "Live-Meter", "Kampflogs", "Raidplaner"]
    assert "CHARAKTER" in nav and "SPIEL" in nav and nav[-2:] == ["Einstellungen", "Konto"]
    assert first.language.currentText() == "Deutsch" and first.language.accessibleName() == "Language"
    assert [first.language.itemText(i) for i in range(first.language.count())] == [n for _c, n in i18n.LANGS]
    settings = first.page("settings")
    assert settings.language.currentData() == "de"
    first.show_page("settings")
    first.show()
    # another language chosen: kept as the web pages keep it, and the window drawn again in it, in place (0.2.509), on
    # the same page
    settings.language.setCurrentIndex(settings.language.findData("fr"))
    settings.language.activated.emit(settings.language.currentIndex())
    assert interface.store().value("a2-lang") == "fr" and i18n.current() == "fr"
    assert first.current_page() == "settings" and first.isVisible()
    assert [first.nav.item(i).text() for i in range(3)] == ["COMBAT", "Compteur en direct", "Logs de combat"]
    assert first.language.currentData() == "fr" and first.page("settings").language.currentData() == "fr"
    assert settle(lambda: not shiboken6.isValid(settings))           # what it showed before, let go; the window stays
    # and from the window's own list, back to English
    first.language.setCurrentIndex(first.language.findData("en"))
    first.language.activated.emit(first.language.currentIndex())
    assert interface.store().value("a2-lang") == "en" and i18n.current() == "en"
    assert [first.nav.item(i).text() for i in range(3)] == ["COMBAT", "Live Meter", "Combat Logs"]
    first.close()


def test_an_upload_visibility_is_sent_as_it_is(shown):
    from aion2calc.gui import combat as cb
    shown("de")
    box = QComboBox()
    for value in cb.QUEUE_VISIBILITY:
        box.addItem(value, value)
    assert [box.itemText(i) for i in range(box.count())] == ["öffentlich", "nicht gelistet", "privat"]
    assert [box.itemData(i) for i in range(box.count())] == list(cb.QUEUE_VISIBILITY)


def test_the_settings_page_in_a_language_and_another_chosen_there(shown):
    from aion2calc.gui.settings_page import SettingsPage
    shown("de")
    page = SettingsPage(None, lambda _page: None, store=interface.store())
    assert [b.text() for b in page.tab_buttons.values()] == ["Darstellung", "Overlay", "Pet Tracker", "Meter", "Server",
                                                             "Profile && Sicherung", "App && Daten"]
    hotkeys = next(row for row in page.rows if row.title == "Hotkeys (Windows)")       # two texts, as on the web page
    assert hotkeys.name.text().startswith("Tastenkürzel <span") and "(Windows)</span>" in hotkeys.name.text()
    page.show_tab("system")
    assert page.language.currentData() == "de"
    page.language.setCurrentIndex(page.language.findData("es"))
    page.language.activated.emit(page.language.currentIndex())                # no window here to draw again
    assert interface.store().value("a2-lang") == "es" and i18n.current() == "es"
    assert QLabel("Settings").text() == "Ajustes"
