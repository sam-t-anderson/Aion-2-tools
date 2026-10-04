// Shared helpers. Every value from a log is inserted as text (never as HTML).
const $ = (s) => document.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "on") for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
    else if (k === "width%") el.style.width = Math.max(0, Math.min(100, v)) + "%";
    else el.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}
const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
const pct = (x, d = 1) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
const ago = (t) => { const s = Date.now() / 1000 - t; return s < 3600 ? Math.round(s / 60) + " min ago" : s < 86400 ? Math.round(s / 3600) + " h ago" : new Date(t * 1000).toLocaleDateString(); };
async function getJSON(u) { const r = await fetch(u); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || r.statusText); return j; }
function win(title, sub, ...body) { return h("section", { class: "win" }, h("div", { class: "wh" }, h("h2", {}, title), sub ? h("span", { class: "sub" }, sub) : null), h("div", { class: "wb" }, ...body)); }
function bar(frac, label, alt) { return h("div", { class: "bar" }, h("i", { class: alt ? "alt" : null, "width%": 100 * frac }), h("span", {}, label)); }
function table(head, rows) { return h("table", { class: "t" }, h("tr", {}, head.map((x) => h("th", { class: x.startsWith(">") ? "r" : null }, x.replace(/^>/, "")))), rows); }
