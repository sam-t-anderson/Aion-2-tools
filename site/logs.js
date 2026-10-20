let logSource='community';
A2LogTabs.mount(document.getElementById('combat-log-tabs'),logSource,value=>{logSource=value;});
A2LogOwnership.mount(document.getElementById("owned-logs"));
A2Identity.mount(document.getElementById("my-characters"));
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
    if(doc.meta?.capture_active===true)throw Error('Unfinished checkpoints are excluded; review and export a finished part first.');
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
  // Generic non-boss combat ("Combat 3", etc.) is dropped from the PvE rows; keep it out of the
  // Boss filter dropdown too, so the PvE boss list only offers real bosses.
  const realBoss = (b) => !/^combat\s*\d*$/i.test(String(b).trim());

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

  // Boss progression: one row per (boss, difficulty, region, product) engagement group, sorted
  // alphabetically by boss. Filterable by boss / difficulty / region / product from the server's own
  // facets; the boss portrait (server-resolved from the group's catalog id) sits left of the name.
  const prog = { f: {}, facets: null };
  function progQuery() {
    const p = new URLSearchParams();
    for (const k of ["boss", "difficulty", "region", "game_patch"]) if (prog.f[k]) p.set(k, prog.f[k]);
    return p.toString();
  }
  async function renderProgression() {
    const body = document.getElementById("progression-body");
    if (!body) return;
    commStyle();                                             // shares the boss-cell / mob-ic styles
    if (!prog.facets) { body.innerHTML = '<div class="empty">Loading…</div>'; try { prog.facets = await A2.api("/api/v1/report-facets"); } catch (e) { prog.facets = {}; } }
    const f = prog.facets || {};
    const q = progQuery();
    let d; try { d = await A2.api("/api/v1/encounter-progression" + (q ? "?" + q : "")); } catch (e) { body.innerHTML = errNote(e); return; }
    const groups = ((d && d.groups) || []).slice().sort((a, b) =>
      String(a.boss || "").localeCompare(String(b.boss || "")) || String(a.difficulty || "").localeCompare(String(b.difficulty || "")));
    const filters = '<div class="row comm-filters" style="gap:10px;margin-bottom:12px;align-items:flex-end;flex-wrap:wrap">'
      + field("Boss", `<select id="pf-boss" style="min-width:195px">${options((f.boss || []).filter(realBoss), prog.f.boss)}</select>`)
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
  // uploaded-by, date, product version), 50 encounters per page, filterable by boss. Flattened
  // client-side from /api/v1/logs' per-encounter contexts[]; server pages of logs are fetched and
  // buffered as needed to fill each page. The uploader is shown when the server provides it (new
  // uploads stamp the recording player); older or undetermined uploads show "Anonymous".
  const COMM_PER_PAGE = 50;
  // Filters mirror what the server's /api/v1/logs already honours (combat mode, boss, difficulty,
  // encounter type, region, product/game version, party size); the choices come from the live
  // /api/v1/report-facets so only values that actually exist are offered.
  // Mini-bosses (an earlier boss of a dungeon whose final boss the catalog knows) are hidden
  // unless asked for; the server says each encounter's role (final / mini / field / unknown) from
  // recorded ids, so an unmapped dungeon or a boss without its code is never hidden by a guess.
  const MINI_PREF = "a2.logs.showMiniBosses";
  const readMiniPref = () => { try { return localStorage.getItem(MINI_PREF) === "1"; } catch (e) { return false; } };
  const comm = { page: 1, f: { combat_mode: "pve" }, buf: [], srvPage: 0, done: false, total: 0, facets: null, mini: readMiniPref() };
  const isMini = (name, roles) => !!(roles && roles[name] === "mini");
  const patchOf = (g) => String(g || "").replace(/^version:product:/, "");
  const prettyEnc = (s) => String(s || "").replace(/^pve_|^pvp_/, "").replace(/_/g, " ") || "—";
  // What kind of PvP a fight was: open world (the Abyss and the faction zones), an arena or a
  // battlefield, from the recorded map; anything unrecognised stays "Other PvP".
  const PVP_TYPES = { pvp_open_world: "Open world", pvp_arena: "Arena", pvp_battleground: "Battlefield", pvp_abyss: "Abyss", pvp_rift: "Rift" };
  const pvpType = (t) => PVP_TYPES[t] || "Other PvP";
  // Without the game's party list (never decoded in the Abyss so far) a fight counts only the players
  // recorded in it, which can be fewer than the party: the count is marked so it is not read as the party's.
  const PARTY_UNKNOWN = "The game's party list was not captured in this fight: this counts the players recorded in it, which can be fewer than the party.";
  const day = (ts) => { try { return new Date(ts * 1000).toISOString().slice(0, 10); } catch (e) { return "—"; } };
  const srcOf = (u) => (u && window.A2AssetHealth ? A2AssetHealth.source(u) : u || null);
  const classIconUrl = (cls) => srcOf("https://metabot.gg/web/aion2/classes/" + encodeURIComponent(cls) + ".webp");
  // A party member as their class icon, with the player name (and class) on hover; drops to nothing
  // if the icon can't load so the row never breaks.
  function classIcon(m) {
    const cls = String(m.class || "").toLowerCase();
    if (!cls) return "";
    const label = (m.name ? m.name + " · " + cap(cls) : cap(cls)) + (m.verified ? " · verified" : "") + (m.pseudonym ? " · hidden by its player" : "");
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
  function commReset() { comm.buf = []; comm.srvPage = 0; comm.done = false; comm.total = 0; }
  function commQuery() {
    const p = new URLSearchParams(); p.set("page", comm.srvPage); p.set("limit", "50");
    if (comm.f.combat_mode) p.set("combat_mode", comm.f.combat_mode);
    for (const k of ["boss", "difficulty", "region", "encounter_type", "game_patch", "party_size"]) if (comm.f[k]) p.set(k, comm.f[k]);
    return p.toString();
  }
  async function commFetchMore() {
    comm.srvPage += 1;
    const d = await A2.api("/api/v1/logs?" + commQuery());
    const logs = (d && d.logs) || [];
    if (d && typeof d.total === "number") comm.total = d.total;
    for (const lg of logs) {
      const iconByName = {};
      for (const b of (lg.bosses || [])) if (b && b.name && b.icon) iconByName[b.name] = b.icon;  // server-provided portraits
      const toMembers = (list) => (list || []).filter((p) => p && (p.name || p.class)).map((p) => ({ name: p.name, class: p.class, verified: p.verified === true, pseudonym: p.pseudonym === true }));
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
        // A PvP fight has no boss: name it by its zone (the Abyss, a faction zone, an arena) when the
        // server knows it, else keep its "Combat N" label.
        comm.buf.push({ boss: (comm.f.combat_mode === "pvp" && c.zone) || c.boss, bossIcon: srcOf(iconByName[c.boss]), difficulty: c.difficulty,
          party: c.party_size || members.length || 0, partyKnown: !!c.party_size, members, duration: c.duration, date: lg.created_at, when, type: c.encounter_type,
          patch: patchOf(c.game_patch), id: lg.id, segment: c.segment, uploader,
          shared: Number.isInteger(lg.shared_uploads) ? lg.shared_uploads : 0 });   // other uploads of the same fights
      }
    }
    // Newest encounter at the top, oldest at the bottom; within one upload (one time on an older
    // server) the later segment comes first.
    comm.buf.sort((a, b) => (b.when - a.when) || ((b.segment || 0) - (a.segment || 0)));
    if (!logs.length || (comm.total && comm.srvPage * 50 >= comm.total)) comm.done = true;
  }
  async function loadCommunity() {
    const table = document.getElementById("comm-table"), pager = document.getElementById("comm-pager");
    if (!table) return;
    table.innerHTML = '<div class="empty">Loading…</div>'; if (pager) pager.innerHTML = "";
    try { while (comm.buf.length < comm.page * COMM_PER_PAGE && !comm.done) await commFetchMore(); }
    catch (e) { table.innerHTML = errNote(e); return; }
    const start = (comm.page - 1) * COMM_PER_PAGE;
    const rows = comm.buf.slice(start, start + COMM_PER_PAGE);
    if (!rows.length) { table.innerHTML = '<div class="empty">No encounters match these filters.</div>'; return; }
    const mode = comm.f.combat_mode || "pve";
    const tr = rows.map((r) => `<tr><td><span class="boss-cell">${r.bossIcon ? `<img class="mob-ic" width="22" height="22" loading="lazy" referrerpolicy="no-referrer" src="${esc(r.bossIcon)}" alt="" onerror="this.remove()">` : ""}${esc(r.boss || "—")}</span></td>
      <td>${esc(mode === "pvp" ? pvpType(r.type) : r.difficulty || "—")}</td>
      <td><span class="party-cell"><b>${n0(r.party)}${r.partyKnown ? "" : `<span class="muted" title="${esc(PARTY_UNKNOWN)}">?</span>`}</b>${r.members.map(classIcon).join("")}</span></td>
      <td class="r num">${secs(r.duration)}</td><td>${esc(r.uploader || "Anonymous")}${r.shared ? ` <span class="muted small" title="Other public uploads indexed as the same fight; it counts once per character on the leaderboard">+${n0(r.shared)} more</span>` : ""}</td><td class="muted small">${day(r.when)}</td><td class="muted small">${esc(r.patch || "—")}</td>
      <td><a href="log.html?id=${encodeURIComponent(r.id)}${Number.isInteger(r.segment) ? "&segment=" + r.segment : ""}">view</a></td></tr>`).join("");
    table.innerHTML = `<table class="t"><tr><th>${mode === "pvp" ? "Skirmish" : "Boss"}</th><th>${mode === "pvp" ? "Type" : "Difficulty"}</th><th>Party</th><th class="r">Time</th><th>Uploaded by</th><th>Date</th><th>Product</th><th></th></tr>${tr}</table>`;
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
  const field = (label, inner) => `<label class="small muted">${label}<br>${inner}</label>`;
  const options = (values, cur, fmt) => '<option value="">any</option>' +
    (values || []).map((v) => `<option value="${esc(v)}"${String(v) === String(cur || "") ? " selected" : ""}>${esc(fmt ? fmt(v) : v)}</option>`).join("");
  async function renderCommunity() {
    const root = document.getElementById("community");
    if (!root) return;
    commStyle();
    if (!comm.facets) { root.innerHTML = '<div class="empty">Loading…</div>'; try { comm.facets = await A2.api("/api/v1/report-facets"); } catch (e) { comm.facets = {}; } }
    const f = comm.facets || {};
    const encOpts = (f.encounter_type || []).filter((t) => (comm.f.combat_mode === "pvp") === String(t).startsWith("pvp_"));
    root.innerHTML = '<div class="row comm-filters" style="gap:10px;margin-bottom:12px;align-items:flex-end;flex-wrap:wrap">'
      + field("Mode", `<select id="cf-mode"><option value="pve"${comm.f.combat_mode !== "pvp" ? " selected" : ""}>PvE</option><option value="pvp"${comm.f.combat_mode === "pvp" ? " selected" : ""}>PvP</option></select>`)
      + (comm.f.combat_mode === "pvp" ? "" : field("Boss", `<select id="cf-boss" style="min-width:195px">${options((f.boss || []).filter(realBoss).filter((b) => comm.mini || !isMini(b, f.boss_roles)), comm.f.boss)}</select>`)
      + `<div class="small muted">Mini-bosses<br><label class="small" title="Earlier bosses of a dungeon whose final boss the catalog knows; hidden unless shown"><input type="checkbox" id="cf-mini"${comm.mini ? " checked" : ""}> show</label></div>`)
      + field("Difficulty", `<select id="cf-difficulty">${options([...(f.difficulty || [])].sort((a, b) => String(a).localeCompare(String(b))), comm.f.difficulty)}</select>`)
      + field("Encounter", `<select id="cf-encounter_type">${options(encOpts, comm.f.encounter_type, comm.f.combat_mode === "pvp" ? pvpType : prettyEnc)}</select>`)
      + field("Region", `<select id="cf-region">${options(f.region, comm.f.region)}</select>`)
      + field("Product", `<select id="cf-game_patch">${options(f.game_patch, comm.f.game_patch, patchOf)}</select>`)
      + field("Party", `<select id="cf-party_size">${options(f.party_size, comm.f.party_size)}</select>`)
      + '<button class="btn small" id="cf-clear" type="button">Clear</button>'
      + '</div><div id="comm-table"><div class="empty">Loading…</div></div><div class="row" id="comm-pager" style="gap:8px;margin-top:10px"></div>';
    const change = (id, key) => { const el = root.querySelector("#cf-" + id); if (el) el.onchange = () => { comm.f[key] = el.value || ""; comm.page = 1; commReset(); loadCommunity(); }; };
    for (const [id, key] of [["boss", "boss"], ["difficulty", "difficulty"], ["encounter_type", "encounter_type"], ["region", "region"], ["game_patch", "game_patch"], ["party_size", "party_size"]]) change(id, key);
    root.querySelector("#cf-mode").onchange = (e) => { comm.f.combat_mode = e.target.value; comm.f.encounter_type = ""; comm.f.boss = ""; comm.page = 1; commReset(); renderCommunity(); };
    root.querySelector("#cf-clear").onclick = () => { comm.f = { combat_mode: comm.f.combat_mode }; comm.page = 1; commReset(); renderCommunity(); };
    const miniBox = root.querySelector("#cf-mini");
    if (miniBox) miniBox.onchange = () => {
      comm.mini = miniBox.checked;
      try { localStorage.setItem(MINI_PREF, comm.mini ? "1" : "0"); } catch (e) { /* private mode: not remembered */ }
      if (!comm.mini && isMini(comm.f.boss, f.boss_roles)) comm.f.boss = "";   // a hidden boss cannot stay selected
      comm.page = 1; commReset(); renderCommunity();
    };
    loadCommunity();
  }

  const renderers = { community: renderCommunity, speed: renderSpeed, progression: renderProgression, points: renderPoints };
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
