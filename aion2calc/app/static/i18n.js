/* The language of the app and the website: English, or one of the official site's other languages.
   Translations are catalogs (i18n/<lang>.json) from the English text to the language's: a page is drawn in
   English and its words are swapped where it shows them, the text of an element, a title, placeholder,
   label or alternative text, including what a page draws later (a MutationObserver). A catalog entry may
   hold {0}, {1} for numbers and names ("{0} logs"). What is not in the catalog stays English, and so do
   names from the game and from players: nothing under translate="no" is touched, nor code, inputs' text
   or anything editable. Scripts ask A2I18n.t(text, ...values) for what they write themselves. */
(function () {
  "use strict";
  const LANGS = [["en", "English"], ["de", "Deutsch"], ["fr", "Français"], ["es", "Español"], ["pt-BR", "Português (Brasil)"], ["ja", "日本語"]];
  const KEY = "a2-lang";
  const ATTRS = ["title", "placeholder", "aria-label", "alt"];
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "CODE", "PRE", "TEXTAREA", "KBD", "SAMP", "svg", "SVG"]);
  const script = document.currentScript;
  const base = script && script.src ? script.src.replace(/[^/]*$/, "") + "i18n/" : "static/i18n/";

  function stored() {
    try {
      const v = localStorage.getItem(KEY);
      return LANGS.some(([id]) => id === v) ? v : "en";
    } catch (e) {
      return "en";
    }
  }
  const lang = stored();
  const exact = new Map(),
    templates = new Map();
  let patterns = [];
  const fill = (text, values) => String(text).replace(/\{(\d)\}/g, (m, i) => (values[i] ?? m));
  const norm = (s) => s.replace(/\s+/g, " ").trim();
  const quote = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  function load(catalog) {
    for (const [src, out] of Object.entries(catalog || {})) {
      if (src.startsWith("_") || typeof out !== "string" || !out) continue;
      const key = norm(src);
      if (/\{\d\}/.test(key)) {
        const order = [];
        const body = key
          .split(/(\{\d\})/)
          .map((part) => {
            const m = part.match(/^\{(\d)\}$/);
            if (!m) return quote(part);
            order.push(+m[1]);
            return "(.+?)";
          })
          .join("");
        patterns.push({ re: new RegExp("^" + body + "$"), order, out });
        templates.set(key, out);
      } else exact.set(key, out);
    }
    patterns = patterns.sort((a, b) => b.re.source.length - a.re.source.length); // the most specific first
  }

  // A text in the language shown, or null when the catalog has none for it.
  function lookup(text) {
    const key = norm(text);
    if (!key) return null;
    const hit = exact.get(key);
    if (hit !== undefined) return hit;
    for (const p of patterns) {
      const m = key.match(p.re);
      if (m) {
        const values = [];
        p.order.forEach((index, i) => (values[index] = m[i + 1]));
        return fill(p.out, values);
      }
    }
    return null;
  }
  function t(text, ...values) {
    const key = norm(String(text));
    const found = lang === "en" ? null : (exact.get(key) ?? templates.get(key));
    return fill(found ?? text, values);
  }

  // ------------------------------------------------------------ the page's words
  const textSource = new WeakMap(); // a text node → {src, out}
  const attrSource = new WeakMap(); // an element → Map(attribute → {src, out})
  const skipped = (el) => !el || SKIP.has(el.nodeName) || el.isContentEditable || !!el.closest('[translate="no"], [data-i18n="off"]');

  function swapText(node) {
    const seen = textSource.get(node);
    const value = node.nodeValue;
    if (seen && value === seen.out) return;
    const out = lookup(value);
    if (out === null) {
      if (seen) textSource.delete(node);
      return;
    }
    const lead = value.match(/^\s*/)[0],
      trail = value.match(/\s*$/)[0];
    const next = lead + out + trail;
    textSource.set(node, { src: value, out: next });
    if (next !== value) node.nodeValue = next;
  }
  function swapAttrs(el) {
    let seen = attrSource.get(el);
    const names = el.nodeName === "INPUT" && /^(button|submit|reset)$/i.test(el.type) ? [...ATTRS, "value"] : ATTRS;
    for (const name of names) {
      const value = el.getAttribute(name);
      if (!value) continue;
      const was = seen && seen.get(name);
      if (was && value === was.out) continue;
      const out = lookup(value);
      if (out === null) continue;
      if (!seen) attrSource.set(el, (seen = new Map()));
      seen.set(name, { src: value, out });
      if (out !== value) el.setAttribute(name, out);
    }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) {
      if (!skipped(root.parentElement)) swapText(root);
      return;
    }
    if (root.nodeType !== 1 || skipped(root)) return;
    swapAttrs(root);
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (n.nodeType === 1) return SKIP.has(n.nodeName) || n.isContentEditable || n.getAttribute("translate") === "no" || n.dataset.i18n === "off" ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
        return /\S/.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      },
    });
    for (let n = tw.nextNode(); n; n = tw.nextNode()) n.nodeType === 3 ? swapText(n) : swapAttrs(n);
  }
  let queued = new Set(),
    pending = false;
  function flush() {
    pending = false;
    const nodes = queued;
    queued = new Set();
    nodes.forEach((n) => n.isConnected && walk(n));
  }
  function watch() {
    walk(document.body);
    new MutationObserver((records) => {
      for (const r of records) {
        if (r.type === "childList") r.addedNodes.forEach((n) => queued.add(n));
        else if (r.type === "characterData") queued.add(r.target);
        else if (r.type === "attributes") queued.add(r.target);
      }
      if (!pending && queued.size) {
        pending = true;
        queueMicrotask(flush);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: [...ATTRS, "value"] });
  }

  // ------------------------------------------------------------ choosing a language
  function set(value) {
    if (!LANGS.some(([id]) => id === value)) return;
    try {
      localStorage.setItem(KEY, value);
    } catch (e) {}
    location.reload();
  }
  function picker(el, { compact = false } = {}) {
    if (!el) return null;
    const select = document.createElement("select");
    select.className = "lang-pick";
    select.setAttribute("aria-label", "Language");
    select.title = "Language";
    select.setAttribute("translate", "no");
    for (const [id, name] of LANGS) {
      const o = document.createElement("option");
      o.value = id;
      o.textContent = compact ? id.split("-")[0].toUpperCase() + " · " + name : name;
      o.lang = id;
      if (id === lang) o.selected = true;
      select.appendChild(o);
    }
    select.onchange = () => set(select.value);
    el.appendChild(select);
    return select;
  }

  document.documentElement.lang = lang;
  const ready =
    lang === "en"
      ? Promise.resolve()
      : fetch(base + lang + ".json", { cache: "no-cache" })
          .then((r) => (r.ok ? r.json() : {}))
          .then(load)
          .catch(() => {});
  if (lang !== "en") {
    document.documentElement.classList.add("i18n-wait");
    const release = () => document.documentElement.classList.remove("i18n-wait");
    setTimeout(release, 1500); // never keep the page hidden for a missing catalog
    ready.then(() => {
      const start = () => {
        watch();
        release();
      };
      if (document.body) start();
      else document.addEventListener("DOMContentLoaded", start);
    });
  }
  window.A2I18n = { LANGS, lang, t, set, picker, ready, translate: walk };
})();
