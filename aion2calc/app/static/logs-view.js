/* Combat-logs views for the desktop app, matching the public GitHub Pages logs page.
 *
 * window.A2LogsView.mount(root, {api, open, extras, initial, onTab}) wires the outer tabs
 * (Community combat logs / Completed-run speed / Boss progression / Highest observed build
 * points, plus an optional app-only "extras" tab) that already exist in `root`, and renders
 * each from the community server's own public endpoints. This is the same per-encounter facet
 * table and aggregate leaderboards the website shows; it is ported here (not shared with
 * site/logs.js) so the app can reach the server through its local proxy and open logs through
 * the SPA router instead of static log.html links.
 *
 *   api(path)        -> the community proxy (communityAPI); same shape as the site's A2.api.
 *   open(id, mode)   -> open a shared log in the app (router navigation).
 *   extras()         -> called once, lazily, the first time the extras tab is shown.
 *   initial          -> tab to show first ("community" when omitted).
 *   onTab(name)      -> notified whenever the visible outer tab changes (for state memory).
 *
 * Every field is read defensively: an unreachable server or a missing field shows a friendly
 * message instead of breaking, and an empty endpoint shows a graceful "nothing yet" note. Each
 * tab renders lazily on first view, and a failing tab never breaks the rest of the page.
 */
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const pct = (x, d = 0) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const secs = (x) => { if (x == null || isNaN(x)) return "—"; x = Math.round(x); const m = Math.floor(x / 60); return m + ":" + String(x % 60).padStart(2, "0"); };
  const errNote = (e) => `<div class="note">${esc((e && e.message) || "Could not reach the stats server.")}</div>`;
  const srcNote = (d) => (d && d.note ? `<p class="small muted" style="margin-top:10px">${esc(d.note)}</p>` : "");
  const patchOf = (g) => String(g || "").replace(/^version:product:/, "");
  const prettyEnc = (s) => String(s || "").replace(/^pve_|^pvp_/, "").replace(/_/g, " ") || "—";
  const day = (ts) => { try { return new Date(ts * 1000).toISOString().slice(0, 10); } catch (e) { return "—"; } };
  const srcOf = (u) => (u && window.A2AssetHealth ? A2AssetHealth.source(u) : u || null);
  const classIconUrl = (cls) => srcOf("https://metabot.gg/web/aion2/classes/" + encodeURIComponent(cls) + ".webp");
  const field = (label, inner) => `<label class="small muted">${label}<br>${inner}</label>`;
  const options = (values, cur, fmt) => '<option value="">any</option>' +
    (values || []).map((v) => `<option value="${esc(v)}"${String(v) === String(cur || "") ? " selected" : ""}>${esc(fmt ? fmt(v) : v)}</option>`).join("");
  // Generic non-boss combat ("Combat 3", etc.) is dropped from the PvE rows; keep it out of the
  // Boss filter dropdown too, so the PvE boss list only offers real bosses.
  const realBoss = (b) => !/^combat\s*\d*$/i.test(String(b).trim());

  function classIcon(m) {
    const cls = String(m.class || "").toLowerCase();
    if (!cls) return "";
    const label = m.name ? m.name + " · " + cap(cls) : cap(cls);
    return `<img class="cls-ic" width="20" height="20" loading="lazy" referrerpolicy="no-referrer" alt="${esc(cls)}" title="${esc(label)}" src="${esc(classIconUrl(cls))}" onerror="this.remove()">`;
  }
  function commStyle() {
    if (document.getElementById("comm-style")) return;
    const s = document.createElement("style"); s.id = "comm-style";
    s.textContent = ".comm-filters select{margin-top:3px;min-width:120px}.boss-cell{display:inline-flex;align-items:center;gap:6px}"
      + ".mob-ic{border-radius:4px;vertical-align:middle}.party-cell{display:inline-flex;align-items:center;gap:3px;flex-wrap:wrap}"
      + ".party-cell b{margin-right:4px}.cls-ic{border-radius:4px;vertical-align:middle}";
    document.head.appendChild(s);
  }

  function mount(root, options_) {
    const api = options_.api, open = options_.open || (() => {});
    const sel = (id) => root.querySelector("#" + id);
    // A log-opening control for inside a table string: a button that routes through the app. When a
    // segment index is given, opening jumps straight to that encounter rather than the log's start.
    const openBtn = (id, mode, label, segment) => id ? `<button class="btn small" data-logs-open="${esc(id)}" data-logs-mode="${esc(mode || "pve")}"${Number.isInteger(segment) ? ` data-logs-seg="${segment}"` : ""} type="button">${esc(label || "view")}</button>` : "";
    const bindOpen = (container) => { (container || root).querySelectorAll("[data-logs-open]").forEach((b) => (b.onclick = () => { const s = parseInt(b.dataset.logsSeg, 10); open(b.dataset.logsOpen, b.dataset.logsMode || "pve", Number.isInteger(s) ? s : undefined); })); };

    async function renderSpeed() {
      const body = sel("speed-body"); if (!body) return;
      let d; try { d = await api("/api/v1/run-leaderboard?limit=100"); } catch (e) { body.innerHTML = errNote(e); return; }
      const rows = (d && d.entries) || [];
      if (!rows.length) { body.innerHTML = '<div class="empty">No eligible speed clears yet. A completed run ranks here once its capture is clean and complete enough to qualify.</div>' + srcNote(d); return; }
      const tr = rows.map((r) => {
        const s = r.summary || r;
        const boss = s.boss || s.final_boss || s.route || r.boss || (Array.isArray(r.boss_route) ? r.boss_route.join(" → ") : "") || "—";
        const elapsed = r.elapsed != null ? r.elapsed : (r.elapsed_seconds != null ? r.elapsed_seconds : s.elapsed);
        const party = s.party_size != null ? s.party_size : r.party_size;
        return `<tr><td class="r">${n0(r.rank)}</td><td>${esc(boss)}</td><td class="r num">${secs(elapsed)}</td><td class="r">${n0(party)}</td><td>${openBtn(r.log, "pve")}</td></tr>`;
      }).join("");
      body.innerHTML = `<table class="t"><tr><th class="r">Rank</th><th>Boss / route</th><th class="r">Time</th><th class="r">Party</th><th></th></tr>${tr}</table>` + srcNote(d);
      bindOpen(body);
    }

    // Boss progression: one row per (boss, difficulty, region, product) engagement group, sorted
    // alphabetically by boss. Filterable by boss / difficulty / region / product from the server's
    // own facets; the boss portrait (server-resolved from the group's catalog id) sits left of the name.
    const prog = { f: {}, facets: null };
    function progQuery() {
      const p = new URLSearchParams();
      for (const k of ["boss", "difficulty", "region", "game_patch"]) if (prog.f[k]) p.set(k, prog.f[k]);
      return p.toString();
    }
    async function renderProgression() {
      const body = sel("progression-body"); if (!body) return;
      commStyle();
      if (!prog.facets) { body.innerHTML = '<div class="empty">Loading…</div>'; try { prog.facets = await api("/api/v1/report-facets"); } catch (e) { prog.facets = {}; } }
      const f = prog.facets || {};
      const q = progQuery();
      let d; try { d = await api("/api/v1/encounter-progression" + (q ? "?" + q : "")); } catch (e) { body.innerHTML = errNote(e); return; }
      const groups = ((d && d.groups) || []).slice().sort((a, b) =>
        String(a.boss || "").localeCompare(String(b.boss || "")) || String(a.difficulty || "").localeCompare(String(b.difficulty || "")));
      const filters = '<div class="row comm-filters" style="gap:10px;margin-bottom:12px;align-items:flex-end;flex-wrap:wrap">'
        + field("Boss", `<select id="pf-boss" style="min-width:170px">${options((f.boss || []).filter(realBoss), prog.f.boss)}</select>`)
        + field("Difficulty", `<select id="pf-difficulty">${options([...(f.difficulty || [])].sort((a, b) => String(a).localeCompare(String(b))), prog.f.difficulty)}</select>`)
        + field("Region", `<select id="pf-region">${options(f.region, prog.f.region)}</select>`)
        + field("Product", `<select id="pf-game_patch">${options(f.game_patch, prog.f.game_patch, patchOf)}</select>`)
        + '<button class="btn small" id="pf-clear" type="button">Clear</button></div>';
      const table = !groups.length ? '<div class="empty">No boss engagements match these filters.</div>'
        : `<table class="t"><tr><th>Boss</th><th>Difficulty</th><th>Region</th><th>Product</th><th class="r">Attempts</th><th class="r">Kills</th><th class="r">Wipes</th><th class="r">Kill rate</th><th class="r">Fastest</th></tr>`
          + groups.map((g) => { const ic = srcOf(g.icon);
            return `<tr><td><span class="boss-cell">${ic ? `<img class="mob-ic" width="22" height="22" loading="lazy" referrerpolicy="no-referrer" src="${esc(ic)}" alt="" onerror="this.remove()">` : ""}${esc(g.boss || "—")}</span></td>
            <td>${esc(g.difficulty || "—")}</td><td>${esc(g.region || "—")}</td><td class="muted small">${esc(patchOf(g.game_patch) || "—")}</td>
            <td class="r">${n0(g.attempts)}</td><td class="r">${n0(g.kills)}</td><td class="r">${n0(g.wipes)}</td>
            <td class="r">${g.observed_kill_rate == null ? "—" : pct(g.observed_kill_rate)}</td>
            <td class="r num">${g.fastest_kill_seconds ? secs(g.fastest_kill_seconds) : "—"}</td></tr>`; }).join("")
          + `</table>`;
      body.innerHTML = filters + table + srcNote(d);
      const change = (id, key) => { const el = body.querySelector("#pf-" + id); if (el) el.onchange = () => { prog.f[key] = el.value || ""; renderProgression(); }; };
      for (const [id, key] of [["boss", "boss"], ["difficulty", "difficulty"], ["region", "region"], ["game_patch", "game_patch"]]) change(id, key);
      const clear = body.querySelector("#pf-clear"); if (clear) clear.onclick = () => { prog.f = {}; renderProgression(); };
    }

    async function renderPoints() {
      const body = sel("points-body"); if (!body) return;
      let d; try { d = await api("/api/v1/progression"); } catch (e) { body.innerHTML = errNote(e); return; }
      const obs = (d && d.observations) || [];
      if (!obs.length) { body.innerHTML = '<div class="empty">No build-point observations yet.</div>' + srcNote(d); return; }
      const best = {};
      for (const o of obs) {
        const total = (o.skill || 0) + (o.stigma || 0) + (o.daevanion || 0);
        const k = o.class_name || "?";
        if (!best[k] || total > best[k]._t) best[k] = Object.assign({}, o, { _t: total });
      }
      const rows = Object.values(best).sort((a, b) => b._t - a._t);
      const tr = rows.map((o) => `<tr><td>${esc(cap(o.class_name))}</td><td class="r">${n0(o.skill)}</td><td class="r">${n0(o.stigma)}</td><td class="r">${n0(o.daevanion)}</td><td class="r num">${n0(o._t)}</td><td class="muted small">${esc(o.region || "")}</td></tr>`).join("");
      body.innerHTML = `<p class="small muted">Highest observed skill / stigma / daevanion points per class, from optimization submissions (reported lower bounds, not verified game caps).</p>
        <table class="t"><tr><th>Class</th><th class="r">Skill</th><th class="r">Stigma</th><th class="r">Daevanion</th><th class="r">Total</th><th>Region</th></tr>${tr}</table>` + srcNote(d);
    }

    // Community combat logs: one row per encounter (boss, difficulty, party + roster, clear time,
    // uploaded-by, date, product version), 50 encounters per page, filterable. Flattened client-side
    // from /api/v1/logs' per-encounter contexts[]; server pages of logs are fetched and buffered as
    // needed to fill each page.
    const COMM_PER_PAGE = 50;
    // Mini-bosses (an earlier boss of a dungeon whose final boss the catalog knows) are hidden
    // unless asked for; the server says each encounter's role (final / mini / field / unknown) from
    // recorded ids, so an unmapped dungeon or a boss without its code is never hidden by a guess.
    const MINI_PREF = "a2.logs.showMiniBosses";
    const readMiniPref = () => { try { return localStorage.getItem(MINI_PREF) === "1"; } catch (e) { return false; } };
    const comm = { page: 1, f: { combat_mode: "pve" }, buf: [], srvPage: 0, done: false, total: 0, facets: null, mini: readMiniPref() };
    const isMini = (name, roles) => !!(roles && roles[name] === "mini");
    function commReset() { comm.buf = []; comm.srvPage = 0; comm.done = false; comm.total = 0; }
    function commQuery() {
      const p = new URLSearchParams(); p.set("page", comm.srvPage); p.set("limit", "50");
      if (comm.f.combat_mode) p.set("combat_mode", comm.f.combat_mode);
      for (const k of ["boss", "difficulty", "region", "encounter_type", "game_patch", "party_size"]) if (comm.f[k]) p.set(k, comm.f[k]);
      return p.toString();
    }
    async function commFetchMore() {
      comm.srvPage += 1;
      const d = await api("/api/v1/logs?" + commQuery());
      const logs = (d && d.logs) || [];
      if (d && typeof d.total === "number") comm.total = d.total;
      for (const lg of logs) {
        const iconByName = {};
        for (const b of (lg.bosses || [])) if (b && b.name && b.icon) iconByName[b.name] = b.icon;  // server-provided portraits
        const toMembers = (list) => (list || []).filter((p) => p && (p.name || p.class)).map((p) => ({ name: p.name, class: p.class }));
        const roster = toMembers(lg.players);  // whole-log roster, fallback only
        const uploader = typeof lg.uploader === "string" ? lg.uploader : null;  // server-provided; else anonymous
        for (const c of (lg.contexts || [])) {
          // Drop generic non-boss combat ("Combat 3", etc.) in PvE only; PvP skirmishes without a
          // named boss are kept.
          if ((comm.f.combat_mode || "pve") !== "pvp" && (!c.boss || /^combat\s*\d*$/i.test(String(c.boss).trim()))) continue;
          if ((comm.f.combat_mode || "pve") !== "pvp" && !comm.mini && c.boss_role === "mini") continue;   // hidden unless asked for
          // Per-encounter participants when the server provides them, so one encounter's party is
          // never shown on another in a multi-encounter log; fall back to the whole-log roster.
          const members = Array.isArray(c.players) && c.players.length ? toMembers(c.players) : roster;
          // The encounter's own time (the server sends each segment's start) so the list runs newest
          // to oldest by fight rather than by upload; an older server only gives the upload time.
          const when = typeof c.start === "number" ? c.start : lg.created_at;
          comm.buf.push({ boss: c.boss, bossIcon: srcOf(iconByName[c.boss]), difficulty: c.difficulty,
            party: c.party_size || members.length || 0, members, duration: c.duration, date: lg.created_at, when,
            patch: patchOf(c.game_patch), id: lg.id, segment: c.segment, uploader });
        }
      }
      // Newest encounter at the top, oldest at the bottom; within one upload (one time on an older
      // server) the later segment comes first.
      comm.buf.sort((a, b) => (b.when - a.when) || ((b.segment || 0) - (a.segment || 0)));
      if (!logs.length || (comm.total && comm.srvPage * 50 >= comm.total)) comm.done = true;
    }
    async function loadCommunity() {
      const table = sel("comm-table"), pager = sel("comm-pager");
      if (!table) return;
      table.innerHTML = '<div class="empty">Loading…</div>'; if (pager) pager.innerHTML = "";
      try { while (comm.buf.length < comm.page * COMM_PER_PAGE && !comm.done) await commFetchMore(); }
      catch (e) { table.innerHTML = errNote(e); return; }
      const start = (comm.page - 1) * COMM_PER_PAGE;
      const rows = comm.buf.slice(start, start + COMM_PER_PAGE);
      if (!rows.length) { table.innerHTML = '<div class="empty">No encounters match these filters.</div>'; return; }
      const mode = comm.f.combat_mode || "pve";
      const tr = rows.map((r) => `<tr><td><span class="boss-cell">${r.bossIcon ? `<img class="mob-ic" width="22" height="22" loading="lazy" referrerpolicy="no-referrer" src="${esc(r.bossIcon)}" alt="" onerror="this.remove()">` : ""}${esc(r.boss || "—")}</span></td>
        <td>${esc(r.difficulty || "—")}</td>
        <td><span class="party-cell"><b>${n0(r.party)}</b>${r.members.map(classIcon).join("")}</span></td>
        <td class="r num">${secs(r.duration)}</td><td>${esc(r.uploader || "Anonymous")}</td><td class="muted small">${day(r.when)}</td><td class="muted small">${esc(r.patch || "—")}</td>
        <td>${openBtn(r.id, mode, "view", r.segment)}</td></tr>`).join("");
      table.innerHTML = `<table class="t"><tr><th>${mode === "pvp" ? "Skirmish" : "Boss"}</th><th>Difficulty</th><th>Party</th><th class="r">Time</th><th>Uploaded by</th><th>Date</th><th>Product</th><th></th></tr>${tr}</table>`;
      bindOpen(table);
      const hasNext = comm.buf.length > comm.page * COMM_PER_PAGE || !comm.done;
      if (pager) {
        pager.innerHTML = `<button class="btn small" ${comm.page <= 1 ? "disabled" : ""} id="comm-prev" type="button">← Prev</button>`
          + `<span class="small muted" style="align-self:center">Page ${comm.page} · encounters ${n0(start + 1)}–${n0(start + rows.length)}</span>`
          + `<button class="btn small" ${hasNext ? "" : "disabled"} id="comm-next" type="button">Next →</button>`;
        const prev = pager.querySelector("#comm-prev"), next = pager.querySelector("#comm-next");
        if (prev) prev.onclick = () => { if (comm.page > 1) { comm.page--; loadCommunity(); } };
        if (next) next.onclick = () => { if (hasNext) { comm.page++; loadCommunity(); } };
      }
    }
    async function renderCommunity() {
      const r = sel("community");
      if (!r) return;
      commStyle();
      if (!comm.facets) { r.innerHTML = '<div class="empty">Loading…</div>'; try { comm.facets = await api("/api/v1/report-facets"); } catch (e) { comm.facets = {}; } }
      const f = comm.facets || {};
      const encOpts = (f.encounter_type || []).filter((t) => (comm.f.combat_mode === "pvp") === String(t).startsWith("pvp_"));
      r.innerHTML = '<div class="row comm-filters" style="gap:10px;margin-bottom:12px;align-items:flex-end;flex-wrap:wrap">'
        + field("Mode", `<select id="cf-mode"><option value="pve"${comm.f.combat_mode !== "pvp" ? " selected" : ""}>PvE</option><option value="pvp"${comm.f.combat_mode === "pvp" ? " selected" : ""}>PvP</option></select>`)
        + (comm.f.combat_mode === "pvp" ? "" : field("Boss", `<select id="cf-boss" style="min-width:170px">${options((f.boss || []).filter(realBoss).filter((b) => comm.mini || !isMini(b, f.boss_roles)), comm.f.boss)}</select>`)
        + `<div class="small muted">Mini-bosses<br><label class="small" title="Earlier bosses of a dungeon whose final boss the catalog knows; hidden unless shown"><input type="checkbox" id="cf-mini"${comm.mini ? " checked" : ""}> show</label></div>`)
        + field("Difficulty", `<select id="cf-difficulty">${options([...(f.difficulty || [])].sort((a, b) => String(a).localeCompare(String(b))), comm.f.difficulty)}</select>`)
        + field("Encounter", `<select id="cf-encounter_type">${options(encOpts, comm.f.encounter_type, prettyEnc)}</select>`)
        + field("Region", `<select id="cf-region">${options(f.region, comm.f.region)}</select>`)
        + field("Product", `<select id="cf-game_patch">${options(f.game_patch, comm.f.game_patch, patchOf)}</select>`)
        + field("Party", `<select id="cf-party_size">${options(f.party_size, comm.f.party_size)}</select>`)
        + '<button class="btn small" id="cf-clear" type="button">Clear</button>'
        + '</div><div id="comm-table"><div class="empty">Loading…</div></div><div class="row" id="comm-pager" style="gap:8px;margin-top:10px"></div>';
      const change = (id, key) => { const el = r.querySelector("#cf-" + id); if (el) el.onchange = () => { comm.f[key] = el.value || ""; comm.page = 1; commReset(); loadCommunity(); }; };
      for (const [id, key] of [["boss", "boss"], ["difficulty", "difficulty"], ["encounter_type", "encounter_type"], ["region", "region"], ["game_patch", "game_patch"], ["party_size", "party_size"]]) change(id, key);
      r.querySelector("#cf-mode").onchange = (e) => { comm.f.combat_mode = e.target.value; comm.f.encounter_type = ""; comm.f.boss = ""; comm.page = 1; commReset(); renderCommunity(); };
      r.querySelector("#cf-clear").onclick = () => { comm.f = { combat_mode: comm.f.combat_mode }; comm.page = 1; commReset(); renderCommunity(); };
      const miniBox = r.querySelector("#cf-mini");
      if (miniBox) miniBox.onchange = () => {
        comm.mini = miniBox.checked;
        try { localStorage.setItem(MINI_PREF, comm.mini ? "1" : "0"); } catch (e) { /* private mode: not remembered */ }
        if (!comm.mini && isMini(comm.f.boss, f.boss_roles)) comm.f.boss = "";   // a hidden boss cannot stay selected
        comm.page = 1; commReset(); renderCommunity();
      };
      loadCommunity();
    }

    const renderers = { community: renderCommunity, speed: renderSpeed, progression: renderProgression, points: renderPoints };
    if (typeof options_.extras === "function") renderers.extras = options_.extras;
    const bar = sel("logs-tabs");
    const panels = [].slice.call(root.querySelectorAll("[data-logs-panel]"));
    const loaded = {};
    function show(name) {
      for (const b of bar.querySelectorAll("[data-tab]")) {
        const on = b.dataset.tab === name;
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.style.fontWeight = on ? "700" : "";
        b.style.textDecoration = on ? "underline" : "";
      }
      for (const p of panels) p.hidden = p.dataset.logsPanel !== name;
      if (typeof options_.onTab === "function") options_.onTab(name);
      if (!loaded[name] && renderers[name]) { loaded[name] = true; try { renderers[name](); } catch (e) { /* a tab must never break the page */ } }
    }
    if (bar && panels.length) {
      bar.addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (b) show(b.dataset.tab); });
      const start = options_.initial && renderers[options_.initial] ? options_.initial : "community";
      show(start);
    }
    return { show, render: (name) => { if (renderers[name]) renderers[name](); } };
  }

  window.A2LogsView = { mount };
})();
