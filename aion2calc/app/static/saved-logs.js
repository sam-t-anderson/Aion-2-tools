/* Saved Logs, grouped by encounter category.
 *
 * window.A2SavedLogs.mount(root, {api, open}) lists the player's own recorded encounters (every
 * segment of every saved session file) split into labelled sections — PvP, World bosses, Field
 * bosses, Raids, Nightmare / Ascension / Expedition / Transcendence / Daily dungeons — so it's
 * easy to tell what each encounter is, the way the website's Community Combat Logs reads. Each row
 * is one encounter with the boss portrait + name, its role (final boss vs mini-boss, or field /
 * world / PvP subtype), difficulty, clear time and date, and opens that encounter in the app.
 *
 *   api(path)           -> the app server (same client the rest of the page uses).
 *   open(file, segment) -> open saved recording `file` at segment index `segment`.
 *
 * The server tags each recorded segment with its category / role / boss (see combat/sessions.py);
 * this view only groups and renders them. Everything is read defensively so a missing field or an
 * unreachable server shows a friendly note instead of breaking.
 */
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const secs = (x) => { if (x == null || isNaN(x)) return "—"; x = Math.round(x); const m = Math.floor(x / 60); return m + ":" + String(x % 60).padStart(2, "0"); };
  // The date with the time of day, in the computer's clock: 2026-10-23 15:04:05.
  const whenAt = (x) => { if (x == null || x === "") return "—"; const d = new Date(x); if (!Number.isFinite(d.getTime())) return "—"; const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
  const day = (ts) => whenAt(ts * 1000);
  const srcOf = (u) => (u && window.A2AssetHealth ? A2AssetHealth.source(u) : u || null);
  const LOGO = "/static/logo.png";
  // Section order and headings. The key is the server's `category`; a recorded encounter lands in
  // exactly one section.
  const SECTIONS = [
    ["pvp", "PvP encounters"],
    ["world_boss", "World bosses"],
    ["field_boss", "Field bosses"],
    ["raid", "Raids"],
    ["nightmare", "Nightmare dungeons"],
    ["ascension", "Ascension trials"],
    ["expedition", "Expeditions"],
    ["transcendence", "Transcendence dungeons"],
    ["daily", "Daily dungeons"],
    ["open_world", "Open world"],
    ["other", "Other / unverified"],
  ];
  const ROLE = { final: "Final boss", mini: "Mini-boss", field: "Field boss", world: "World boss" };
  const PER_SECTION = 200;   // cap the DOM per section; a "+N more" note covers the rest

  function style() {
    if (document.getElementById("saved-logs-style")) return;
    const s = document.createElement("style"); s.id = "saved-logs-style";
    s.textContent = ".sl-sec{margin:10px 0}.sl-sec>summary{cursor:pointer;font-weight:600}"
      + ".sl-boss{display:inline-flex;align-items:center;gap:6px}.sl-ic{border-radius:4px;vertical-align:middle}"
      + ".sl-badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:16px;border:1px solid currentColor;opacity:.85}";
    document.head.appendChild(s);
  }

  function portrait(code) {
    const url = code && window.A2BundledAssets && A2BundledAssets.npcs ? A2BundledAssets.npcs[code] : null;
    return `<img class="sl-ic" width="22" height="22" loading="lazy" referrerpolicy="no-referrer" alt="" src="${esc(srcOf(url) || LOGO)}" onerror="this.onerror=null;this.src='${LOGO}'">`;
  }

  // Filters, as the other log pages have them (0.2.372): boss, type, role (mini-bosses hidden unless shown, the
  // choice the community combat logs keep), difficulty and the dates the recordings were saved. They apply to the
  // recordings loaded so far; "Load more recordings" brings older ones in.
  const MINI_PREF = "a2.logs.showMiniBosses";
  const readMini = () => { try { return localStorage.getItem(MINI_PREF) === "1"; } catch (e) { return false; } };
  const dayStart = (v) => { const t = Date.parse(v + "T00:00:00"); return Number.isFinite(t) ? t / 1000 : null; };
  const field = (label, inner) => `<label class="small muted">${label}<br>${inner}</label>`;
  const choices = (values, cur, fmt) => '<option value="">any</option>' + values.map((v) => `<option value="${esc(v)}"${String(v) === String(cur || "") ? " selected" : ""}>${esc(fmt ? fmt(v) : v)}</option>`).join("");

  function mount(root, options) {
    const api = options.api, open = options.open || (() => {});
    style();
    let encounters = [], offset = 0, hasMore = true, loading = false;
    const f = { boss: "", category: "", role: "", difficulty: "", from: "", to: "" };
    let mini = readMini();
    const shownRole = (e) => mini || e.role !== "mini" || f.boss === e.boss || f.role === "mini";
    const matches = (e) => {
      if (f.boss && e.boss !== f.boss) return false;
      if (f.category && e.category !== f.category) return false;
      if (f.role && (e.category === "pvp" ? "pvp" : e.role || "") !== f.role) return false;
      if (f.difficulty && (e.difficulty || "") !== f.difficulty) return false;
      const from = f.from && dayStart(f.from), to = f.to && dayStart(f.to);
      if (from && !(e.date >= from)) return false;
      if (to && !(e.date < to + 86400)) return false;
      return shownRole(e);
    };
    function filtersHTML() {
      const bosses = [...new Set(encounters.filter((e) => e.boss && (mini || e.role !== "mini")).map((e) => e.boss))].sort((a, b) => a.localeCompare(b));
      const cats = SECTIONS.filter(([k]) => encounters.some((e) => e.category === k));
      const roles = [...new Set(encounters.map((e) => (e.category === "pvp" ? "pvp" : e.role || "")).filter(Boolean))];
      const diffs = [...new Set(encounters.map((e) => e.difficulty).filter((d) => d && d !== "unknown"))].sort();
      const roleName = (r) => (r === "pvp" ? "PvP" : ROLE[r] || r);
      return '<div class="row sl-filters" style="gap:10px;margin:8px 0 12px;align-items:flex-end;flex-wrap:wrap">'
        + field("Boss", `<select data-slf="boss" style="min-width:195px">${choices(bosses, f.boss)}</select>`)
        + `<div class="small muted">Mini-bosses<br><label class="small" title="Earlier bosses of a dungeon whose final boss the catalog knows; hidden unless shown"><input type="checkbox" data-slf-mini${mini ? " checked" : ""}> show</label></div>`
        + field("Type", `<select data-slf="category">${choices(cats.map(([k]) => k), f.category, (k) => (SECTIONS.find(([key]) => key === k) || [k, k])[1])}</select>`)
        + field("Role", `<select data-slf="role">${choices(roles, f.role, roleName)}</select>`)
        + field("Difficulty", `<select data-slf="difficulty">${choices(diffs, f.difficulty, cap)}</select>`)
        + field("Saved from", `<input type="date" data-slf="from" value="${esc(f.from)}">`)
        + field("to", `<input type="date" data-slf="to" value="${esc(f.to)}">`)
        + '<button class="btn small" data-slf-clear type="button">Clear</button></div>';
    }
    const types = () => (window.A2Community && A2Community.types) || {};

    // The label shown as a row's "role": a boss's role in a dungeon, or the PvP sub-type.
    function roleLabel(e) {
      if (e.category === "pvp") { const t = types()[e.enc_type]; return t ? t.replace(/^PvP · /, "") : "PvP"; }
      return ROLE[e.role] || "";
    }

    async function fetchPage() {
      const d = await api("/api/sessions?paged=1&offset=" + offset + "&limit=50&archive=");
      offset += 50;
      hasMore = !!(d && d.has_more);
      for (const r of (d && d.rows) || []) {
        for (const c of r.contexts || []) {
          if (!c || c.boss == null && c.category === "other") continue;   // skip empty non-boss combat
          encounters.push({ boss: c.boss, boss_code: c.boss_code, category: c.category || "other",
            role: c.role, difficulty: c.difficulty, duration: c.duration, killed: c.killed,
            date: r.updated, file: r.file, segment: c.segment, enc_type: c.encounter_type });
        }
      }
    }

    function render() {
      const groups = {}, shown = encounters.filter(matches);
      for (const e of shown) (groups[e.category] = groups[e.category] || []).push(e);
      for (const list of Object.values(groups)) list.sort((a, b) => (b.date || 0) - (a.date || 0));
      const present = SECTIONS.filter(([k]) => (groups[k] || []).length);
      let html;
      if (!encounters.length) {
        html = loading ? '<div class="empty">Loading…</div>'
          : '<div class="empty">No recorded encounters yet. Record a fight with the live meter and it will appear here, grouped by type.</div>';
      } else if (!shown.length) {
        html = `<div class="empty">No recorded encounters match these filters${hasMore ? " among the recordings loaded so far" : ""}.</div>`;
      } else {
        html = present.map(([key, title], idx) => {
          const list = groups[key], shown = list.slice(0, PER_SECTION);
          const rows = shown.map((e) => {
            const role = roleLabel(e);
            return `<tr><td><span class="sl-boss">${portrait(e.boss_code)}${esc(e.boss || "—")}</span></td>
              <td>${role ? `<span class="sl-badge">${esc(role)}</span>` : ""}</td>
              <td>${esc(cap(e.difficulty && e.difficulty !== "unknown" ? e.difficulty : "")) || "—"}</td>
              <td class="r num">${secs(e.duration)}</td><td class="muted small">${day(e.date)}</td>
              <td><button class="btn small" data-open="${esc(e.file)}" data-seg="${esc(e.segment)}" type="button">view</button></td></tr>`;
          }).join("");
          const more = list.length > PER_SECTION ? `<p class="small muted">+${list.length - PER_SECTION} more in this category.</p>` : "";
          return `<details class="sl-sec" ${idx === 0 ? "open" : ""}><summary>${esc(title)} <span class="small muted">(${list.length})</span></summary>`
            + `<table class="t"><tr><th>Boss / encounter</th><th>Role</th><th>Difficulty</th><th class="r">Time</th><th>Date</th><th><span class="sr-only">Actions</span></th></tr>${rows}</table>${more}</details>`;
        }).join("");
      }
      root.innerHTML = `<p class="small muted">Your recorded encounters, grouped by type. Each row opens that encounter.${hasMore ? " The filters apply to the recordings loaded so far." : ""}</p>${encounters.length ? filtersHTML() : ""}${html}`
        + `<div class="row" style="gap:8px;margin-top:8px">${hasMore ? '<button class="btn small" id="sl-more" type="button">Load more recordings</button>' : ""}`
        + `<button class="btn small" id="sl-refresh" type="button">Refresh</button></div>`;
      root.querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => {
        const seg = parseInt(b.dataset.seg, 10);
        open(b.dataset.open, Number.isInteger(seg) ? seg : undefined);
      }));
      root.querySelectorAll("[data-slf]").forEach((el) => (el.onchange = () => { f[el.dataset.slf] = el.value || ""; render(); }));
      const miniBox = root.querySelector("[data-slf-mini]");
      if (miniBox) miniBox.onchange = () => {
        mini = miniBox.checked;
        try { localStorage.setItem(MINI_PREF, mini ? "1" : "0"); } catch (e) { /* private mode: not remembered */ }
        render();
      };
      const clear = root.querySelector("[data-slf-clear]");
      if (clear) clear.onclick = () => { for (const k of Object.keys(f)) f[k] = ""; render(); };
      const more = root.querySelector("#sl-more"); if (more) more.onclick = () => load(false);
      const refresh = root.querySelector("#sl-refresh"); if (refresh) refresh.onclick = () => load(true);
    }

    async function load(reset) {
      if (loading) return;
      if (reset) { encounters = []; offset = 0; hasMore = true; }
      loading = true; render();
      try { await fetchPage(); }
      catch (e) { root.innerHTML = `<div class="note">${esc((e && e.message) || "Could not load saved recordings.")}</div>`
        + '<div class="row" style="margin-top:8px"><button class="btn small" id="sl-refresh" type="button">Retry</button></div>';
        const rb = root.querySelector("#sl-refresh"); if (rb) rb.onclick = () => load(true); loading = false; return; }
      loading = false; render();
    }

    load(true);
    return { reload: () => load(true), refresh: () => load(true) };
  }

  window.A2SavedLogs = { mount };
})();
