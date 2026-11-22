"""The native interface in the languages the web interface speaks (0.2.483): English, Deutsch, Français, Español,
Português (Brasil) and 日本語, from the web interface's own word lists (``app/static/i18n/<lang>.json``), read as
``i18n.js`` reads them.

A text is looked up as ``i18n.js`` looks it up: its white space run together and taken off its ends, then the
catalog's own entry for it, else the first of the catalog's templates that matches it whole (``{0}`` and ``{1}``
hold numbers and names; the longest pattern first, as the web page sorts them). What the catalog has none of stays
English, and so do names from the game and from players.

``install`` puts the window's texts in the language chosen where the web page has the same text in its own words: a
label's or a button's text, a check box's, a list's choices, a table's headings and cells, a tooltip (``title``), a
placeholder, an accessible name (``aria-label``). The Qt calls that put those on screen are wrapped, as ``i18n.js``
swaps a page's text and those attributes. What is typed or can be edited is left as it is (a field's text), as is
what a widget marked with ``keep_english`` shows, and in a rich text what is in ``code``, ``pre``, ``kbd`` or
``samp`` or marked ``translate="no"``. Texts the window draws itself (a chart's) stay English, as the web page's
drawn texts do. The overlay stays English, as the web overlay does: only the window installs a language.

The language is the one the web pages keep (``a2-lang``), in the app's interface data since 0.2.482; choosing
another draws the window again in it, as the web page reloads.
"""
from __future__ import annotations

import contextlib
import html
import json
import pathlib
import re

#: The languages, as ``i18n.js`` lists them: each one's code and its own name.
LANGS = (("en", "English"), ("de", "Deutsch"), ("fr", "Français"), ("es", "Español"), ("pt-BR", "Português (Brasil)"),
         ("ja", "日本語"))
KEY = "a2-lang"                                   # where the web pages keep the language chosen
FOLDER = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "i18n"
#: The property a widget marked ``keep_english`` carries (``translate="no"``).
OFF = "a2-i18n-off"

#: What JavaScript's ``\s`` matches (and ``trim`` takes off): its white space and line ends.
_SPACE = "".join(map(chr, (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029,
                           0x202F, 0x205F, 0x3000, 0xFEFF)))
_RUN = re.compile("[" + re.escape(_SPACE) + "]+")
_SLOT = re.compile(r"\{(\d)\}")
_SPECIAL = re.compile(r"[.*+?^${}()|[\]\\]")
#: Elements whose words are never swapped (``i18n.js`` SKIP), and those that hold no words of their own.
_SKIP = {"script", "style", "noscript", "code", "pre", "textarea", "kbd", "samp", "svg"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_TAG = re.compile(r"(<[^>]*>)")
_TAG_NAME = re.compile(r"^</?\s*([A-Za-z][A-Za-z0-9-]*)")
_NO = re.compile(r"""\b(?:translate\s*=\s*["']?no\b|data-i18n\s*=\s*["']?off\b)""", re.I)


def norm(text: str) -> str:
    """``s.replace(/\\s+/g, " ").trim()``."""
    return _RUN.sub(" ", text).strip(_SPACE)


def _quote(text: str) -> str:
    """i18n.js ``quote``: the characters a pattern reads as its own escaped, and no others."""
    return _SPECIAL.sub(lambda m: "\\" + m.group(0), text)


def fill(text: str, values) -> str:
    """i18n.js ``fill``: ``{0}``, ``{1}`` replaced by the values given; one without a value stays as it is."""
    values = list(values) if not isinstance(values, dict) else values

    def value(m):
        i = int(m.group(1))
        if isinstance(values, dict):
            found = values.get(i)
        else:
            found = values[i] if i < len(values) else None
        return m.group(0) if found is None else str(found)
    return _SLOT.sub(value, str(text))


class Catalog:
    """A language's word list, read as ``i18n.js`` ``load`` reads it."""

    def __init__(self, entries: dict):
        self.exact: dict[str, str] = {}
        self.templates: dict[str, str] = {}
        patterns = []
        for src, out in (entries or {}).items():
            if not isinstance(src, str) or src.startswith("_") or not isinstance(out, str) or not out:
                continue
            key = norm(src)
            if _SLOT.search(key):
                order, body = [], []
                for part in re.split(r"(\{\d\})", key):
                    slot = re.fullmatch(r"\{(\d)\}", part)
                    if slot is None:
                        body.append(_quote(part))
                    else:
                        order.append(int(slot.group(1)))
                        body.append("(.+?)")
                source = "^" + "".join(body) + "$"
                # sorted by the length of the pattern as JavaScript writes it (``re.source``: a "/" as "\/")
                patterns.append((len(source) + source.count("/"), re.compile(source), order, out))
                self.templates[key] = out
            else:
                self.exact[key] = out
        self.patterns = [(regex, order, out) for _length, regex, order, out in
                         sorted(patterns, key=lambda p: -p[0])]              # the most specific first; ties as listed
        self._seen: dict[str, str | None] = {}

    def lookup(self, text: str):
        """i18n.js ``lookup``: the text in this language, or None when the catalog has none for it."""
        if text in self._seen:
            return self._seen[text]
        key = norm(text)
        found = None
        if key:
            found = self.exact.get(key)
            if found is None:
                for regex, order, out in self.patterns:
                    m = regex.match(key)
                    if m:
                        found = fill(out, {index: m.group(i + 1) for i, index in enumerate(order)})
                        break
        if len(self._seen) > 20000:
            self._seen.clear()
        self._seen[text] = found
        return found


_catalog: Catalog | None = None
_lang = "en"
_english = 0                                      # inside ``english()``: what is made there keeps its words
_marked = False                                   # whether any widget was marked ``keep_english``


def known(lang) -> bool:
    return any(code == lang for code, _name in LANGS)


def language(store=None) -> str:
    """The language chosen (i18n.js ``stored``): the web pages' choice kept in the app's interface data, English when
    there is none or it is not one of the languages."""
    if store is None:
        from . import interface
        store = interface.store()
    try:
        chosen = store.value(KEY)
    except Exception:
        return "en"
    return chosen if known(chosen) else "en"


def current() -> str:
    """The language the window is in."""
    return _lang


def read_catalog(lang: str) -> Catalog | None:
    """A language's word list; None for English, or a list that cannot be read (the window stays English)."""
    if lang == "en" or not known(lang):
        return None
    try:
        return Catalog(json.loads((FOLDER / f"{lang}.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def install(lang: str) -> str:
    """Show the window's texts in ``lang`` from now on (what is put on screen after this): the Qt calls wrapped once,
    the language's word list read. Returns the language the window is in: English when ``lang`` is not one of the
    languages or its word list cannot be read."""
    global _catalog, _lang
    _hook()
    _catalog = read_catalog(lang)
    _lang = lang if _catalog is not None else "en"
    return _lang


def t(text, *values) -> str:
    """i18n.js ``t``: a text the window writes itself, in the language shown, with ``{0}``, ``{1}`` filled in."""
    key = norm(str(text))
    found = None if _catalog is None else _catalog.exact.get(key, _catalog.templates.get(key))
    return fill(text if found is None else found, values)


def _swap(value: str) -> str:
    """i18n.js ``swapText``: a text in the language shown, the white space around it kept; as it was without an
    entry for it."""
    out = _catalog.lookup(value)
    if out is None:
        return value
    lead = value[:len(value) - len(value.lstrip(_SPACE))]
    trail = value[len(value.rstrip(_SPACE)):] if value.strip(_SPACE) else ""
    return lead + out + trail


def _plain(value: str) -> str:
    """A plain text: as one text, else each of its lines (a line break stands where the web page has a ``<br>``)."""
    out = _swap(value)
    if out is value and "\n" in value:
        return "\n".join(_swap(line) for line in value.split("\n"))
    return out


def _rich(markup: str) -> str:
    """A rich text: each text between its tags swapped as the web page swaps each of its text nodes, but in what is
    not translated (``code``, ``pre``, ``kbd``, ``samp``, ``translate="no"``)."""
    parts = _TAG.split(markup)
    stack: list[tuple[str, bool]] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2:                                 # a tag
            m = _TAG_NAME.match(part)
            if m is None or part.startswith("<!"):
                continue
            name = m.group(1).lower()
            if part.startswith("</"):
                for depth in range(len(stack) - 1, -1, -1):
                    if stack[depth][0] == name:
                        del stack[depth:]
                        break
            elif name not in _VOID and not part.rstrip(">").rstrip().endswith("/"):
                off = (stack[-1][1] if stack else False) or name in _SKIP or bool(_NO.search(part))
                stack.append((name, off))
            continue
        if stack and stack[-1][1]:
            continue
        text = html.unescape(part)
        out = _swap(text)
        if out is not text:
            parts[i] = html.escape(out, quote=False)
    return "".join(parts)


def shown(text, rich: bool = False):
    """What the window shows for ``text`` in the language chosen."""
    if _catalog is None or _english or not isinstance(text, str) or not text:
        return text
    return _rich(text) if rich else _plain(text)


def _kept(widget) -> bool:
    """Whether a widget, or one it is in, keeps its words (``keep_english``)."""
    if _english:
        return True
    if not _marked or widget is None:
        return False
    try:
        while widget is not None:
            if widget.property(OFF):
                return True
            widget = widget.parentWidget()
    except (AttributeError, RuntimeError):
        return False
    return False


def keep_english(widget):
    """A widget (and what is in it) that keeps its words: a name, or a value shown as it is sent
    (``translate="no"``)."""
    global _marked
    _marked = True
    widget.setProperty(OFF, True)
    return widget


@contextlib.contextmanager
def english():
    """What is made inside keeps its words, as a part of the web page marked ``translate="no"`` does."""
    global _english
    _english += 1
    try:
        yield
    finally:
        _english -= 1


def picker(chosen=None):
    """The language list (i18n.js ``picker``): each language in its own name, kept as it is, the one shown chosen;
    ``chosen`` is given the code of another one picked."""
    from PySide6.QtWidgets import QComboBox
    box = QComboBox()
    keep_english(box)
    box.setObjectName("langpick")
    box.setAccessibleName("Language")
    box.setToolTip("Language")
    for code, name in LANGS:
        box.addItem(name, code)
    box.setCurrentIndex(max(0, box.findData(_lang)))

    def picked(_index):
        code = box.currentData()
        if code != _lang and chosen is not None:
            chosen(code)
    box.activated.connect(picked)
    return box


# ------------------------------------------------------------------ the Qt calls that put a text on screen
_originals: list[tuple[type, str, object]] = []


def _rich_label(label, text) -> bool:
    from PySide6.QtGui import Qt                  # QtGui's Qt has mightBeRichText
    try:
        form = label.textFormat()
    except (AttributeError, RuntimeError):
        form = Qt.AutoText
    if form == Qt.RichText:
        return True
    if form == Qt.PlainText or form == getattr(Qt, "MarkdownText", None):
        return False
    return Qt.mightBeRichText(text)


def _made_rich(text) -> bool:
    """A label being made reads its text as Qt does until told otherwise (``AutoText``)."""
    from PySide6.QtGui import Qt
    return isinstance(text, str) and Qt.mightBeRichText(text)


def _button_words(text: str) -> str:
    """A button's text: "&&" is how a button writes "&"."""
    if _catalog is None or _english or not isinstance(text, str) or "&" not in text:
        return shown(text)
    plain = text.replace("&&", "&")
    out = shown(plain)
    return text if out is plain else out.replace("&", "&&")


def _tip(text):
    from PySide6.QtGui import Qt
    return shown(text, rich=isinstance(text, str) and Qt.mightBeRichText(text))


def _first_text(args, kwargs, names, swap):
    """The call's arguments with its first text (or the keyword named) in the language shown."""
    for name in names:
        if isinstance(kwargs.get(name), str):
            return args, {**kwargs, name: swap(kwargs[name])}
    for i, arg in enumerate(args):
        if isinstance(arg, str):
            return args[:i] + (swap(arg),) + args[i + 1:], kwargs
    return args, kwargs


def _self(self, _args, _kwargs):
    return self


def _parent(_self, args, kwargs):
    """A widget being made: the one it is made in, if given (it is not a widget yet itself)."""
    from PySide6.QtWidgets import QWidget
    parent = kwargs.get("parent")
    if parent is None:
        parent = next((arg for arg in args if isinstance(arg, QWidget)), None)
    return parent


def _wrap(cls, name, swap, names=("text",), widget_of=_self):
    original = cls.__dict__.get(name) or getattr(cls, name)
    _originals.append((cls, name, original))

    def wrapped(self, *args, **kwargs):
        if _catalog is not None and not _kept(widget_of(self, args, kwargs)):
            args, kwargs = _first_text(args, kwargs, names, lambda text: swap(self, text))
        return original(self, *args, **kwargs)
    wrapped.__name__ = getattr(original, "__name__", name)
    wrapped.__doc__ = getattr(original, "__doc__", None)
    setattr(cls, name, wrapped)


def _wrap_list(cls, name):
    """A call given a list of texts (``addItems``, a table's headings)."""
    original = cls.__dict__.get(name) or getattr(cls, name)
    _originals.append((cls, name, original))

    def wrapped(self, texts, *args, **kwargs):
        if _catalog is not None and not _kept(self) and isinstance(texts, (list, tuple)):
            texts = [shown(text) for text in texts]
        return original(self, texts, *args, **kwargs)
    wrapped.__name__ = getattr(original, "__name__", name)
    setattr(cls, name, wrapped)


def _item_view(item, _args=(), _kwargs=None):
    try:
        return item.tableWidget() if hasattr(item, "tableWidget") else item.listWidget()
    except RuntimeError:
        return None


def _hook() -> None:
    if _originals:
        return
    from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QGroupBox, QLabel, QLineEdit,
                                   QListWidgetItem, QPlainTextEdit, QPushButton, QRadioButton, QTabBar, QTableWidget,
                                   QTableWidgetItem, QTabWidget, QTextEdit, QWidget)
    plain = lambda _self, text: shown(text)                                    # noqa: E731
    label = lambda self, text: shown(text, rich=_rich_label(self, text))       # noqa: E731
    made = lambda _self, text: shown(text, rich=_made_rich(text))              # noqa: E731
    button = lambda _self, text: _button_words(text)                           # noqa: E731
    tip = lambda _self, text: _tip(text)                                       # noqa: E731
    _wrap(QLabel, "__init__", made, widget_of=_parent)
    _wrap(QLabel, "setText", label)
    for cls in (QPushButton, QCheckBox, QRadioButton):
        _wrap(cls, "__init__", button, widget_of=_parent)
    _wrap(QAbstractButton, "setText", button)
    _wrap(QGroupBox, "__init__", plain, ("title",), widget_of=_parent)
    _wrap(QGroupBox, "setTitle", plain, ("title",))
    _wrap(QWidget, "setToolTip", tip, ("toolTip", "arg__1"))
    _wrap(QWidget, "setAccessibleName", plain, ("name", "arg__1"))
    for cls in (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox):
        _wrap(cls, "setPlaceholderText", plain, ("placeholderText", "arg__1"))
    _wrap(QComboBox, "addItem", plain)
    _wrap(QComboBox, "insertItem", plain)
    _wrap(QComboBox, "setItemText", plain)
    _wrap_list(QComboBox, "addItems")
    _wrap_list(QComboBox, "insertItems")
    for cls in (QTabWidget, QTabBar):
        _wrap(cls, "addTab", plain, ("label", "text"))
        _wrap(cls, "insertTab", plain, ("label", "text"))
        _wrap(cls, "setTabText", plain, ("text",))
        _wrap(cls, "setTabToolTip", tip, ("tip",))
    _wrap_list(QTableWidget, "setHorizontalHeaderLabels")
    _wrap_list(QTableWidget, "setVerticalHeaderLabels")
    for cls in (QTableWidgetItem, QListWidgetItem):
        _wrap(cls, "__init__", plain, ("text",), widget_of=lambda _self, _args, _kwargs: None)
        _wrap(cls, "setText", plain, ("text",), widget_of=_item_view)
        _wrap(cls, "setToolTip", tip, ("toolTip",), widget_of=_item_view)


def uninstall() -> None:
    """The Qt calls as they were, and the window in English (the tests)."""
    global _catalog, _lang
    while _originals:
        cls, name, original = _originals.pop()
        setattr(cls, name, original)
    _catalog, _lang = None, "en"
