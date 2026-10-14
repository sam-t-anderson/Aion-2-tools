let logSource='community';
A2LogTabs.mount(document.getElementById('combat-log-tabs'),logSource,value=>{logSource=value;});
A2LogOwnership.mount(document.getElementById("owned-logs"));
// The "Community Combat Logs" sub-tab is rendered as a one-row-per-encounter table by the tab
// controller below (renderCommunity); A2Community stays loaded for its upload types (used below).

let archiveReview, previewDocument;
const previewRoot=document.getElementById('archive-review');
function renderPreviewPage(){
  const focused=location.hash==='#local-log' && !!previewDocument;
  for(const child of document.querySelector('main').children)child.hidden=focused?child!==previewRoot:child===previewRoot;
  if(archiveReview){archiveReview.dispose();archiveReview=null;}
  previewRoot.replaceChildren();
  document.title=focused?'Combat log — Aion 2 Calc':'Logs — Aion 2 Calc';
  if(!focused){A2LogTabs.mount(document.getElementById('combat-log-tabs'),logSource,value=>{logSource=value;});return;}
  const back=document.createElement('a');back.className='btn small';back.href='#';back.textContent='← Back to combat logs';
  const heading=document.createElement('p');heading.append(back);const viewer=document.createElement('div');previewRoot.append(heading,viewer);
  archiveReview=A2CombatReview.mount(viewer,previewDocument);
  window.scrollTo(0,0);
}
window.addEventListener('hashchange',renderPreviewPage);
renderPreviewPage();
A2ArchiveUpload.mount(document.getElementById('archive-upload'),{
  files:true,types:A2Community.types,
  context:async()=>{const config=A2.cfg(),url=(A2.base()||config.url||'').replace(/\/+$/,'');
    return {url,key:url===(config.url||'').replace(/\/+$/,'')?config.key:undefined};},
  open:async row=>{previewDocument=JSON.parse(await row.input.text());
    if(location.hash==='#local-log')renderPreviewPage();else location.hash='local-log';},
  upload:async(row,batch)=>{
    const text=await row.input.text(),doc=JSON.parse(text);
    if(doc.meta?.capture_active)throw Error('Unfinished checkpoints are excluded; review and export a finished part first.');
    let body=text;const headers={'Content-Type':'application/json'};
    if(batch.key)headers.Authorization='Bearer '+batch.key;
    if(row.request_id)headers['Idempotency-Key']=row.request_id;
    if(typeof CompressionStream!=='undefined'){
      body=await new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
      headers['Content-Encoding']='gzip';
    }
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),65000);
    let response,result;
    try {
      response=await fetch(batch.url+'/api/v1/logs?visibility='+encodeURIComponent(batch.visibility),
        {method:'POST',body,headers,credentials:'omit',redirect:'error',cache:'no-store',signal:controller.signal});
      result=await response.json();
    }catch(e){if(e.name==='AbortError')throw Error('Upload timed out; the server outcome is unknown. Check My uploads/server before retrying.');throw e;}
    finally{clearTimeout(timer);}
    if(!response.ok || result.error)throw Error('Upload refused ('+response.status+'): '+(result.error||response.statusText));
    try {if(!result.replayed)A2LogOwnership.remember(batch.url,result,doc.meta?.title||row.input.name);}
    catch(e){result.ownership_warning='Uploaded, but could not save ownership on this browser: '+e.message;}
    return result;
  }
});

// Aggregate leaderboard tabs (Completed-run speed, Boss progression, Class performance, Highest
// observed build points), each from the server's own public endpoint via A2.api. Every field is
// read defensively: an unreachable server or a missing field shows a friendly message instead of
// breaking, and an empty endpoint shows a graceful "nothing yet" note. The Community tab keeps the
// existing browse/upload/review workflow above. Each tab renders lazily on first view.
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const pct = (x, d = 0) => (x == null || isNaN(x) ? "—" : (100 * x).toFixed(d) + "%");
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const secs = (x) => { if (x == null || isNaN(x)) return "—"; x = Math.round(x); const m = Math.floor(x / 60); return m + ":" + String(x % 60).padStart(2, "0"); };
  const errNote = (e) => `<div class="note">${esc((e && e.message) || "Could not reach the stats server.")}</div>`;
  const srcNote = (d) => (d && d.note ? `<p class="small muted" style="margin-top:10px">${esc(d.note)}</p>` : "");

  async function renderSpeed() {
    const body = document.getElementById("speed-body");
    let d; try { d = await A2.api("/api/v1/run-leaderboard?limit=100"); } catch (e) { body.innerHTML = errNote(e); return; }
    const rows = (d && d.entries) || [];
    if (!rows.length) { body.innerHTML = '<div class="empty">No eligible speed clears yet. A completed run ranks here once its capture is clean and complete enough to qualify.</div>' + srcNote(d); return; }
    const tr = rows.map((r) => {
      const s = r.summary || r;
      const boss = s.boss || s.final_boss || s.route || r.boss || "—";
      const elapsed = r.elapsed != null ? r.elapsed : s.elapsed;
      const party = s.party_size != null ? s.party_size : r.party_size;
      return `<tr><td class="r">${n0(r.rank)}</td><td>${esc(boss)}</td><td class="r num">${secs(elapsed)}</td><td class="r">${n0(party)}</td><td>${r.log ? `<a href="log.html?id=${encodeURIComponent(r.log)}">view</a>` : ""}</td></tr>`;
    }).join("");
    body.innerHTML = `<table class="t"><tr><th class="r">Rank</th><th>Boss / route</th><th class="r">Time</th><th class="r">Party</th><th></th></tr>${tr}</table>` + srcNote(d);
  }

  async function renderProgression() {
    const body = document.getElementById("progression-body");
    let d; try { d = await A2.api("/api/v1/encounter-progression"); } catch (e) { body.innerHTML = errNote(e); return; }
    const groups = ((d && d.groups) || []).slice().sort((a, b) => (b.attempts || 0) - (a.attempts || 0));
    if (!groups.length) { body.innerHTML = '<div class="empty">No boss engagements recorded yet.</div>' + srcNote(d); return; }
    const tr = groups.map((g) => `<tr><td>${esc(g.boss || "—")}${g.difficulty ? ` <span class="muted small">${esc(g.difficulty)}</span>` : ""}</td>
      <td class="r">${n0(g.attempts)}</td><td class="r">${n0(g.kills)}</td><td class="r">${n0(g.wipes)}</td>
      <td class="r">${g.observed_kill_rate == null ? "—" : pct(g.observed_kill_rate)}</td>
      <td class="r num">${g.fastest_kill_seconds ? secs(g.fastest_kill_seconds) : "—"}</td></tr>`).join("");
    body.innerHTML = `<table class="t"><tr><th>Boss</th><th class="r">Attempts</th><th class="r">Kills</th><th class="r">Wipes</th><th class="r">Kill rate</th><th class="r">Fastest</th></tr>${tr}</table>` + srcNote(d);
  }

  async function renderClasses() {
    const body = document.getElementById("classes-body");
    let d; try { d = await A2.api("/api/v1/stats"); } catch (e) { body.innerHTML = errNote(e); return; }
    const classes = ((d && d.classes) || []).slice().sort((a, b) => (b.observations || 0) - (a.observations || 0));
    if (!classes.length) { body.innerHTML = '<div class="empty">No fights uploaded yet. Share public logs from the app to populate class performance.</div>'; return; }
    const tr = classes.map((c) => `<tr><td>${esc(cap(c.class))}</td><td class="r">${n0(c.observations)}</td><td><a href="stats.html?class=${encodeURIComponent(c.class)}">details →</a></td></tr>`).join("");
    body.innerHTML = `<p class="small muted">Median DPS, hit rates, tempo and damage-by-skill per class live on the <a href="stats.html">Class stats</a> page. Fights observed per class:</p>
      <table class="t"><tr><th>Class</th><th class="r">Observations</th><th></th></tr>${tr}</table>`;
  }

  async function renderPoints() {
    const body = document.getElementById("points-body");
    let d; try { d = await A2.api("/api/v1/progression"); } catch (e) { body.innerHTML = errNote(e); return; }
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
  // date, product version), paged, filterable by boss. Uploads are anonymous (no uploader identity
  // is recorded), so the party roster shows who was in the fight. Flattened client-side from
  // /api/v1/logs, whose rows already carry a per-encounter contexts[] array.
  const comm = { page: 1, boss: "" };
  const patchOf = (g) => String(g || "").replace(/^version:product:/, "");
  const day = (ts) => { try { return new Date(ts * 1000).toISOString().slice(0, 10); } catch (e) { return "—"; } };
  async function loadCommunity() {
    const table = document.getElementById("comm-table"), pager = document.getElementById("comm-pager");
    if (!table) return;
    table.innerHTML = '<div class="empty">Loading…</div>'; if (pager) pager.innerHTML = "";
    let d; try { d = await A2.api(`/api/v1/logs?page=${comm.page}&limit=25` + (comm.boss ? "&boss=" + encodeURIComponent(comm.boss) : "")); }
    catch (e) { table.innerHTML = errNote(e); return; }
    const rows = [];
    for (const lg of ((d && d.logs) || [])) {
      const roster = (lg.players || []).map((p) => p.name).filter(Boolean);
      for (const c of (lg.contexts || [])) {
        rows.push({ boss: c.boss, difficulty: c.difficulty, party: c.party_size || roster.length || 0, roster,
          duration: c.duration, date: lg.created_at, patch: patchOf(c.game_patch), id: lg.id });
      }
    }
    if (!rows.length) { table.innerHTML = `<div class="empty">No encounters found${comm.boss ? ' for "' + esc(comm.boss) + '"' : ""}.</div>`; return; }
    const tr = rows.map((r) => `<tr><td>${esc(r.boss || "—")}</td><td>${esc(r.difficulty || "—")}</td>
      <td>${n0(r.party)}${r.roster.length ? ` <span class="muted small">${esc(r.roster.slice(0, 3).join(", "))}${r.roster.length > 3 ? "…" : ""}</span>` : ""}</td>
      <td class="r num">${secs(r.duration)}</td><td class="muted small">${day(r.date)}</td><td class="muted small">${esc(r.patch || "—")}</td>
      <td><a href="log.html?id=${encodeURIComponent(r.id)}">view</a></td></tr>`).join("");
    table.innerHTML = `<table class="t"><tr><th>Boss</th><th>Difficulty</th><th>Party</th><th class="r">Time</th><th>Date</th><th>Product</th><th></th></tr>${tr}</table>`;
    const total = d.total || rows.length, limit = d.limit || 25, page = d.page || comm.page, pages = Math.max(1, Math.ceil(total / limit));
    if (pager) {
      pager.innerHTML = `<button class="btn small" ${page <= 1 ? "disabled" : ""} id="comm-prev" type="button">← Prev</button>`
        + `<span class="small muted" style="align-self:center">Page ${page} of ${pages} · ${n0(total)} logs</span>`
        + `<button class="btn small" ${page >= pages ? "disabled" : ""} id="comm-next" type="button">Next →</button>`;
      const prev = pager.querySelector("#comm-prev"), next = pager.querySelector("#comm-next");
      if (prev) prev.onclick = () => { if (comm.page > 1) { comm.page--; loadCommunity(); } };
      if (next) next.onclick = () => { if (page < pages) { comm.page++; loadCommunity(); } };
    }
  }
  function renderCommunity() {
    const root = document.getElementById("community");
    if (!root) return;
    root.innerHTML = '<div class="row" style="gap:8px;margin-bottom:10px;align-items:flex-end">'
      + '<label class="small muted">Boss<br><input id="comm-boss" type="text" placeholder="any boss" style="min-width:180px;margin-top:3px"></label>'
      + '<button class="btn small" id="comm-apply" type="button">Filter</button></div>'
      + '<div id="comm-table"><div class="empty">Loading…</div></div>'
      + '<div class="row" id="comm-pager" style="gap:8px;margin-top:10px"></div>';
    const input = root.querySelector("#comm-boss");
    input.value = comm.boss;
    const apply = () => { comm.boss = input.value.trim(); comm.page = 1; loadCommunity(); };
    root.querySelector("#comm-apply").onclick = apply;
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") apply(); });
    loadCommunity();
  }

  const renderers = { community: renderCommunity, speed: renderSpeed, progression: renderProgression, classes: renderClasses, points: renderPoints };
  const bar = document.getElementById("logs-tabs");
  const panels = [].slice.call(document.querySelectorAll("[data-logs-panel]"));
  const loaded = {};
  function show(name) {
    for (const b of bar.querySelectorAll("[data-tab]")) {
      const on = b.dataset.tab === name;
      b.setAttribute("aria-selected", on ? "true" : "false");
      b.style.fontWeight = on ? "700" : "";
      b.style.textDecoration = on ? "underline" : "";
    }
    for (const p of panels) p.hidden = p.dataset.logsPanel !== name;
    if (name !== "community") { const ar = document.getElementById("archive-review"); if (ar) ar.hidden = true; }
    if (!loaded[name] && renderers[name]) { loaded[name] = true; try { renderers[name](); } catch (e) { /* a tab must never break the page */ } }
  }
  if (bar && panels.length) {
    bar.addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (b) show(b.dataset.tab); });
    show("community");
  }
})();
