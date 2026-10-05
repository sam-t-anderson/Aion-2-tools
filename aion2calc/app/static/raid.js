/* Shared raid & boss planner — used by the aion2calc app and the planner site (GitHub Pages).
 *
 *   A2Raid.mount(rootEl, io)
 *
 * renders the planner into rootEl. `io` supplies the host's data/IO (all optional):
 *   io.encounters()        -> [{id, player, boss, duration}]      (Compare-with-a-fight list)
 *   io.encounter(id)       -> {rotation, buffs, summary:{duration}} (overlay a saved fight)
 *   io.publish(plan, vis)  -> {url}                                (Publish; button hidden if absent)
 *   io.browse()            -> [{id, name, author, duration, tokens, buffs, has_fight, classes}]
 *   io.fetchPlan(id)       -> an a2plan document                  (used by Browse)
 *
 * A plan is an "a2plan" document: tokens (players, enemies, markers, AoE zones) whose positions are
 * keyframed over a timeline and interpolated linearly, so a time slider plays the movement back,
 * plus party-buff windows. Plans live in localStorage; they can be exported, imported, shared as a
 * code, and (when io.publish/io.browse are given) published to and browsed from a server.
 */
(function () {
  "use strict";

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  function toast(msg) {
    const d = document.createElement("div");
    d.textContent = msg;
    Object.assign(d.style, { position: "fixed", bottom: "20px", left: "50%", transform: "translateX(-50%)", background: "#1c2438",
      border: "1px solid rgba(233,203,128,.6)", padding: "8px 16px", borderRadius: "6px", zIndex: 99, color: "#e8cf8e" });
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 1800);
  }
  function copyText(t) { navigator.clipboard?.writeText(t).then(() => toast("Copied to clipboard"), () => toast("Copy failed")); }
  function win(title, sub, body) {
    return `<section class="win"><div class="wh"><h2>${esc(title)}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}</div><div class="wb">${body}</div></section>`;
  }

  const A2PLAN_KEY = "a2plans";
  const RAID_CLASSES = ["Templar", "Gladiator", "Assassin", "Ranger", "Sorcerer", "Spiritmaster", "Cleric", "Chanter"];
  const TOKEN_COLORS = ["#e66a5a", "#39c2e0", "#6fcf7a", "#e9a43a", "#a46cf0", "#f05a8c", "#5bc0de", "#b9984f", "#7fd6a8", "#6fa8dc", "#d4b45a", "#9fd36f"];
  const RAID_MARKERS = ["A", "B", "C", "D", "1", "2", "3", "4"];

  function raidPlans() { try { return JSON.parse(localStorage.getItem(A2PLAN_KEY) || "{}"); } catch (e) { return {}; } }
  function saveRaidPlans(all) { try { localStorage.setItem(A2PLAN_KEY, JSON.stringify(all)); } catch (e) { toast("Could not save — browser storage is full"); } }
  function uid() { return Math.random().toString(36).slice(2, 9); }
  function newPlan(name) {
    return { format: "a2plan", version: 1,
      meta: { name: name || "New plan", author: "", notes: "", created: Date.now(), updated: Date.now() },
      arena: { kind: "square" }, duration: 60, tokens: [], buffs: [], source: {} };
  }
  function tokenPos(tk, t) {
    const k = tk.keyframes || [];
    if (!k.length) return null;
    if (t <= k[0].t) return { x: k[0].x, y: k[0].y };
    const last = k[k.length - 1];
    if (t >= last.t) return { x: last.x, y: last.y };
    for (let i = 1; i < k.length; i++) {
      if (t <= k[i].t) { const a = k[i - 1], b = k[i], f = (t - a.t) / Math.max(1e-6, b.t - a.t); return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f }; }
    }
    return { x: last.x, y: last.y };
  }
  function setKeyframe(tk, t, x, y) {
    t = Math.round(t * 10) / 10;
    x = Math.max(0, Math.min(1, x)); y = Math.max(0, Math.min(1, y));
    tk.keyframes = tk.keyframes || [];
    const i = tk.keyframes.findIndex((kf) => Math.abs(kf.t - t) < 0.05);
    if (i >= 0) { tk.keyframes[i].x = x; tk.keyframes[i].y = y; }
    else { tk.keyframes.push({ t, x, y }); tk.keyframes.sort((a, b) => a.t - b.t); }
  }
  function planToCode(p) { const b = new TextEncoder().encode(JSON.stringify(p)); let s = ""; b.forEach((c) => (s += String.fromCharCode(c))); return btoa(s); }
  function codeToPlan(code) {
    const bin = atob(code.trim()), b = Uint8Array.from(bin, (c) => c.charCodeAt(0)), p = JSON.parse(new TextDecoder().decode(b));
    if (!p || p.format !== "a2plan") throw new Error("That is not an a2plan share code");
    return p;
  }
  function download(name, text, type = "application/json") {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function importDoc(p) {                                    // store an a2plan as a new local plan, make it current
    p.meta = p.meta || {}; p.meta.updated = Date.now();
    const all = raidPlans(), id = uid(); all[id] = p; saveRaidPlans(all);
    st.id = id; st.sel = null; st.t = 0; st.actual = null;
  }

  const st = { id: null, plan: null, t: 0, speed: 1, sel: null, playing: false, timer: null, actual: null, encounters: [], io: {}, root: null, browsing: null };

  function persist() {
    if (!st.id || !st.plan) return;
    st.plan.meta = st.plan.meta || {}; st.plan.meta.updated = Date.now();
    const all = raidPlans(); all[st.id] = st.plan; saveRaidPlans(all);
  }

  function render() {
    const p = st.plan, dur = p.duration || 1, io = st.io;
    const all = raidPlans();
    const planOpts = Object.entries(all).sort((a, b) => (b[1].meta?.updated || 0) - (a[1].meta?.updated || 0))
      .map(([id, pl]) => `<option value="${esc(id)}" ${id === st.id ? "selected" : ""}>${esc(pl.meta?.name || "Untitled")}</option>`).join("");
    const sel = p.tokens.find((x) => x.id === st.sel) || null;
    const players = p.tokens.filter((x) => x.kind === "player");

    const shareBtns = (io.publish ? `<button class="btn small" id="rpublish">Publish</button>` : "")
      + (io.browse ? `<button class="btn small" id="rbrowse">Browse plans</button>` : "");
    const hint = io.publish
      ? `<span class="faint small">Plans are saved on this computer; Publish shares one to the server.</span>`
      : `<span class="faint small">Plans are saved on this computer.</span>`;
    const header = `<div class="row"><label class="muted small">Plan</label><select id="rplan" style="min-width:180px">${planOpts}</select>
        <button class="btn small" id="rnew">New</button><button class="btn small" id="rdup">Duplicate</button><button class="btn small" id="rdel">Delete</button></div>
      <div class="row" style="margin-top:8px"><input id="rname" type="text" value="${esc(p.meta?.name || "")}" placeholder="Plan name" style="width:200px">
        <input id="rauthor" type="text" value="${esc(p.meta?.author || "")}" placeholder="Author (optional)" style="width:160px">
        <label class="muted small">Length</label><input id="rdur" type="number" min="5" max="1800" value="${dur}" style="width:80px"><span class="muted small">s</span>
        <label class="muted small">Arena</label><select id="rarena"><option value="square" ${p.arena?.kind !== "circle" ? "selected" : ""}>Square</option><option value="circle" ${p.arena?.kind === "circle" ? "selected" : ""}>Circle</option></select></div>
      <div class="row" style="margin-top:8px"><button class="btn small" id="rexport">Export file</button>
        <label class="btn small" style="cursor:pointer">Import file<input id="rimport" type="file" accept=".json,.a2plan" hidden></label>
        <button class="btn small" id="rcode">Copy share code</button><button class="btn small" id="rload">Load from code</button>${shareBtns}${hint}</div>
      <div class="row small" id="rpubmsg"></div>`;

    const tokensHtml = p.tokens.map((tk) => {
      const s = tk.id === st.sel ? " sel" : "";
      if (tk.kind === "aoe") return `<div class="rtoken aoe${s}" id="tok-${tk.id}" data-tid="${tk.id}" style="--tc:${esc(tk.color)}" title="${esc(tk.label || "AoE zone")}"></div>`;
      const glyph = tk.kind === "marker" ? esc(tk.label || "?") : esc((tk.label && tk.label[0]) || (tk.cls && tk.cls[0]) || (tk.kind === "enemy" ? "B" : "P")).toUpperCase();
      return `<div class="rtoken ${tk.kind}${s}" id="tok-${tk.id}" data-tid="${tk.id}" style="--tc:${esc(tk.color)}" title="${esc(tk.label || tk.cls || tk.kind)}"><span class="rl">${glyph}</span></div>`;
    }).join("");

    const buffColor = (bf) => { const by = players.find((x) => (x.label || x.cls) === bf.by); return by ? by.color : "var(--gold)"; };
    const buffBars = p.buffs.map((bf) => {
      const l = 100 * Math.max(0, bf.start) / dur, w = 100 * Math.max(0, bf.end - bf.start) / dur;
      return `<div class="bufbar" data-start="${bf.start}" data-end="${bf.end}" style="left:${l}%;width:${w}%;--tc:${buffColor(bf)}" title="${esc(bf.name)}${bf.by ? " · " + esc(bf.by) : ""}">${esc(bf.name)}</div>`;
    }).join("");
    const actualLane = st.actual ? `<div class="rlane"><div class="lanehd">Actual casts</div><div class="lanebody">
        ${st.actual.rotation.map(([ct]) => `<i class="casttick" style="left:${100 * ct / dur}%"></i>`).join("")}</div></div><div class="row small" id="castnow"></div>` : "";

    const left = `<div class="arena ${p.arena?.kind === "circle" ? "circle" : ""}" id="arena"><svg class="rpath" id="rpath" viewBox="0 0 100 100" preserveAspectRatio="none"></svg>${tokensHtml}
        ${p.tokens.length ? "" : '<div class="arenahint">Add players, enemies, markers or AoE zones from the panel, then drag them on the map.</div>'}</div>
      <div class="rtransport"><button class="btn small" id="rstart" title="Back to start">⏮</button>
        <button class="btn small primary" id="rplay">${st.playing ? "⏸ Pause" : "▶ Play"}</button>
        <select id="rspeed" title="Playback speed">${[0.5, 1, 2, 4].map((x) => `<option value="${x}" ${st.speed === x ? "selected" : ""}>${x}×</option>`).join("")}</select>
        <input type="range" id="rscrub" min="0" max="${dur}" step="0.1" value="${st.t}" style="flex:1">
        <span id="rtime" class="small muted mono"></span></div>
      <div class="rlane"><div class="lanehd">Party buffs</div><div class="lanebody" id="buflane">${buffBars || '<span class="faint small" style="padding:0 6px">add buffs in the panel →</span>'}</div></div>
      <div class="row small" id="bufnow"></div>${actualLane}`;

    let editor = '<p class="faint small">Select a token on the map to edit it.</p>';
    if (sel) {
      const kfs = (sel.keyframes || []).map((k, i) => `<div class="kfrow"><button class="btn small" data-kgo="${k.t}">${k.t.toFixed(1)}s</button>
          <span class="small muted">x ${(k.x * 100).toFixed(0)} · y ${(k.y * 100).toFixed(0)}</span>${(sel.keyframes.length > 1) ? `<button class="btn small" data-kdel="${i}" title="Delete this keyframe">✕</button>` : ""}</div>`).join("");
      editor = `<div class="row"><input id="slabel" type="text" value="${esc(sel.label || "")}" placeholder="Label" style="width:120px">
          <input id="scolor" type="color" value="${esc(sel.color || "#39c2e0")}" style="width:40px;padding:2px">
          ${sel.kind === "player" ? `<select id="scls">${RAID_CLASSES.map((c) => `<option ${c === sel.cls ? "selected" : ""}>${c}</option>`).join("")}</select>` : ""}</div>
        ${sel.kind === "aoe" ? `<div class="row" style="margin-top:6px"><label class="muted small">Radius</label><input id="srad" type="range" min="4" max="50" value="${Math.round((sel.radius || 0.14) * 100)}" style="flex:1"></div>` : ""}
        <div class="kflist" style="margin-top:8px"><div class="small muted">Keyframes (position over time)</div>${kfs || '<div class="faint small">none</div>'}
          <button class="btn small" id="kadd" style="margin-top:4px">Set position at ${st.t.toFixed(1)}s</button></div>
        <button class="btn small" id="sdel" style="margin-top:8px">Remove token</button>`;
    }

    const buffList = p.buffs.map((bf, i) => `<div class="row small bufedit"><input data-bf="${i}" data-k="name" value="${esc(bf.name)}" style="width:110px">
        <select data-bf="${i}" data-k="by" style="width:90px"><option value="">—</option>${players.map((pl) => { const nm = pl.label || pl.cls; return `<option ${nm === bf.by ? "selected" : ""}>${esc(nm)}</option>`; }).join("")}</select>
        <input data-bf="${i}" data-k="start" type="number" min="0" value="${bf.start}" style="width:58px"><span class="faint">–</span>
        <input data-bf="${i}" data-k="end" type="number" min="0" value="${bf.end}" style="width:58px"><button class="btn small" data-bfdel="${i}">✕</button></div>`).join("");

    const fightRow = io.encounters ? `<h4 class="gold small">COMPARE WITH A FIGHT</h4>
        <div class="row"><select id="ractual"><option value="">— none —</option>${(st.encounters || []).map((e) => `<option value="${e.id}" ${st.actual && st.actual.id === e.id ? "selected" : ""}>#${e.id} ${esc(e.player || "")} ${esc(e.boss || "")} ${(e.duration || 0).toFixed(0)}s</option>`).join("")}</select></div>
        <p class="small faint">Overlay a saved combat log so its skill casts and buff windows play on the same timeline. Planner-only data defaults to unlisted; attaching a fight shares the real run too.</p>` : "";

    const side = `<div class="rpanel"><h4 class="gold small">ADD</h4>
        <div class="row"><select id="rcls">${RAID_CLASSES.map((c) => `<option>${c}</option>`).join("")}</select><button class="btn small primary" id="raddp">+ Player</button></div>
        <div class="row" style="margin-top:6px"><button class="btn small" id="radde">+ Enemy</button><button class="btn small" id="raddm">+ Marker</button><button class="btn small" id="radda">+ AoE</button></div>
        <p class="small faint">Move the slider to a moment, then drag a token to where it should be then. The planner interpolates the movement in between.</p>
        <h4 class="gold small">SELECTED TOKEN</h4>${editor}
        <h4 class="gold small">PARTY BUFFS</h4><div class="bufedits">${buffList || '<div class="faint small">none yet</div>'}</div>
        <div class="row small" style="margin-top:6px"><input id="bfname" placeholder="Buff name" style="width:110px"><select id="bfby" style="width:90px"><option value="">source…</option>${players.map((pl) => { const nm = pl.label || pl.cls; return `<option>${esc(nm)}</option>`; }).join("")}</select>
          <input id="bfstart" type="number" min="0" value="0" style="width:52px"><span class="faint">–</span><input id="bfend" type="number" min="0" value="10" style="width:52px"><button class="btn small" id="bfadd">Add</button></div>
        ${fightRow}
        <h4 class="gold small">NOTES</h4><textarea id="rnotes" rows="4" style="width:100%" placeholder="Callouts, phases, assignments…">${esc(p.meta?.notes || "")}</textarea></div>`;

    st.root.innerHTML = win("Raid & boss planner", "drag player tokens on the map and scrub the timeline to plan movement, cooldowns and party buffs",
      header + `<div class="raidwrap"><div>${left}</div>${side}</div>`);
    bind();
  }

  function renderBrowse(list) {
    const cards = list.length ? list.map((pl) => `<div class="pcard"><div class="gname">${esc(pl.name || "Plan")}</div>
        <div class="small muted">${esc(pl.author || "unknown")} · ${(pl.duration || 0).toFixed(0)}s · ${pl.tokens || 0} tokens${pl.has_fight ? " · with a fight" : ""}</div>
        <div class="small">${(pl.classes || []).map((c) => `<span class="chip">${esc(c)}</span>`).join(" ")}</div>
        <button class="btn small primary" data-open="${esc(pl.id)}" style="margin-top:6px">Open</button></div>`).join("")
      : '<div class="empty">No public plans yet.</div>';
    st.root.innerHTML = win("Browse published plans", "open one to copy it into your own plans",
      `<div class="row"><button class="btn small" id="rback">← Back to the planner</button></div><div class="pcards" style="margin-top:12px">${cards}</div>`);
    $("#rback").onclick = () => { st.browsing = null; render(); };
    $$("[data-open]").forEach((b) => (b.onclick = async () => {
      try { const doc = await st.io.fetchPlan(b.dataset.open); importDoc(doc); st.browsing = null; render(); toast("Plan opened"); }
      catch (e) { toast(e.message); }
    }));
  }

  function bind() {
    const p = st.plan, io = st.io;
    const arena = $("#arena", st.root);

    const layout = () => {
      const t = st.t, dur = p.duration || 1;
      if (!arena) return;
      p.tokens.forEach((tk) => {
        const el = arena.querySelector("#tok-" + tk.id); if (!el) return;
        const pos = tokenPos(tk, t);
        if (!pos) { el.style.display = "none"; return; }
        el.style.display = ""; el.style.left = (pos.x * 100) + "%"; el.style.top = (pos.y * 100) + "%";
        if (tk.kind === "aoe") { const d = (tk.radius || 0.14) * 2 * 100; el.style.width = d + "%"; el.style.height = d + "%"; }
      });
      const path = $("#rpath", st.root), tk = p.tokens.find((x) => x.id === st.sel);
      if (path) path.innerHTML = !tk || !tk.keyframes ? "" :
        (tk.keyframes.length > 1 ? `<polyline points="${tk.keyframes.map((k) => `${k.x * 100},${k.y * 100}`).join(" ")}"/>` : "")
        + tk.keyframes.map((k) => `<circle cx="${k.x * 100}" cy="${k.y * 100}" r="1.6" class="${Math.abs(k.t - t) < 0.06 ? "kon" : ""}"/>`).join("");
      const rd = $("#rtime", st.root); if (rd) rd.textContent = t.toFixed(1) + " / " + dur + "s";
      const sc = $("#rscrub", st.root); if (sc && document.activeElement !== sc) sc.value = String(t);
      $$(".bufbar", st.root).forEach((b) => b.classList.toggle("on", +b.dataset.start <= t && t <= +b.dataset.end));
      const now = p.buffs.filter((bf) => bf.start <= t && t <= bf.end), bn = $("#bufnow", st.root);
      if (bn) bn.innerHTML = `<span class="muted">Buffs now:</span> ` + (now.length ? now.map((bf) => `<span class="chip gold">${esc(bf.name)}${bf.by ? " · " + esc(bf.by) : ""}</span>`).join(" ") : '<span class="faint">none</span>');
      if (st.actual) { const near = st.actual.rotation.filter(([ct]) => Math.abs(ct - t) < 0.4).map(([, k]) => k), cn = $("#castnow", st.root);
        if (cn) cn.innerHTML = `<span class="muted">Casts:</span> ` + (near.length ? near.map((k) => `<span class="chip">${esc(k)}</span>`).join(" ") : '<span class="faint">—</span>'); }
    };
    st.layout = layout;

    const setBtn = () => { const b = $("#rplay", st.root); if (b) b.textContent = st.playing ? "⏸ Pause" : "▶ Play"; };
    const startTimer = () => {
      if (st.timer) return;
      st.timer = setInterval(() => {
        if (!document.body.contains(arena)) { clearInterval(st.timer); st.timer = null; st.playing = false; return; }
        st.t = Math.round((st.t + 0.05 * (st.speed || 1)) * 100) / 100;
        if (st.t >= (p.duration || 1)) { st.t = p.duration || 1; layout(); pause(); return; }
        layout();
      }, 50);
    };
    const pause = () => { if (st.timer) { clearInterval(st.timer); st.timer = null; } st.playing = false; setBtn(); };
    const play = () => { st.playing = true; setBtn(); startTimer(); };

    // --- plan management
    const reload = () => { st.plan = raidPlans()[st.id]; st.sel = null; st.t = 0; st.actual = null; render(); };
    $("#rplan", st.root).onchange = (e) => { st.id = e.target.value; reload(); };
    $("#rnew", st.root).onclick = () => { const all = raidPlans(), id = uid(); all[id] = newPlan("New plan"); saveRaidPlans(all); st.id = id; reload(); };
    $("#rdup", st.root).onclick = () => { const all = raidPlans(), id = uid(), copy = JSON.parse(JSON.stringify(p)); copy.meta.name = (p.meta?.name || "Plan") + " copy"; copy.meta.created = copy.meta.updated = Date.now(); all[id] = copy; saveRaidPlans(all); st.id = id; reload(); };
    $("#rdel", st.root).onclick = () => { if (!confirm("Delete this plan?")) return; const all = raidPlans(); delete all[st.id]; saveRaidPlans(all); st.id = null; st.plan = null; mountPlan(); render(); };
    $("#rname", st.root).onchange = (e) => { p.meta.name = e.target.value; persist(); };
    $("#rauthor", st.root).onchange = (e) => { p.meta.author = e.target.value; persist(); };
    $("#rdur", st.root).onchange = (e) => { p.duration = Math.max(5, +e.target.value || 60); persist(); render(); };
    $("#rarena", st.root).onchange = (e) => { p.arena.kind = e.target.value; persist(); render(); };
    $("#rnotes", st.root).onchange = (e) => { p.meta.notes = e.target.value; persist(); };
    $("#rexport", st.root).onclick = () => download((p.meta?.name || "plan").replace(/[^\w-]+/g, "_") + ".a2plan", JSON.stringify(p, null, 2));
    $("#rimport", st.root).onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try { const pl = JSON.parse(await f.text()); if (pl.format !== "a2plan") throw new Error("Not an a2plan file"); importDoc(pl); render(); toast("Plan imported"); }
      catch (err) { toast(err.message); }
    };
    $("#rcode", st.root).onclick = () => { copyText(planToCode(p)); };
    $("#rload", st.root).onclick = () => {
      const code = prompt("Paste an a2plan share code:"); if (!code) return;
      try { importDoc(codeToPlan(code)); render(); toast("Plan loaded"); } catch (err) { toast(err.message); }
    };
    if ($("#rpublish", st.root)) $("#rpublish", st.root).onclick = async () => {
      const msg = $("#rpubmsg", st.root);
      const vis = (p.source && p.source.encounterId) ? "public" : "unlisted";   // default: share actual data, keep planner-only unlisted
      if (msg) msg.textContent = "Publishing…";
      try {
        const r = await io.publish(p, vis);
        if (msg) { msg.innerHTML = `Published (${vis}): <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url)}</a> `;
          const c = document.createElement("button"); c.className = "btn small"; c.textContent = "Copy link"; c.onclick = () => copyText(r.url); msg.appendChild(c); }
      } catch (e) { if (msg) msg.textContent = e.message; }
    };
    if ($("#rbrowse", st.root)) $("#rbrowse", st.root).onclick = async () => {
      try { const list = await io.browse(); st.browsing = list; renderBrowse(list); } catch (e) { toast(e.message); }
    };

    // --- add tokens
    const pickColor = () => { const used = new Set(p.tokens.map((t) => t.color)); return TOKEN_COLORS.find((c) => !used.has(c)) || TOKEN_COLORS[p.tokens.length % TOKEN_COLORS.length]; };
    const addToken = (tk) => { setKeyframe(tk, 0, 0.5 + (Math.random() - 0.5) * 0.3, 0.5 + (Math.random() - 0.5) * 0.3); p.tokens.push(tk); st.sel = tk.id; persist(); render(); };
    $("#raddp", st.root).onclick = () => { const cls = $("#rcls", st.root).value; addToken({ id: uid(), kind: "player", label: cls, cls, color: pickColor(), keyframes: [] }); };
    $("#radde", st.root).onclick = () => addToken({ id: uid(), kind: "enemy", label: "Boss", color: "#d33939", keyframes: [] });
    $("#raddm", st.root).onclick = () => { const used = p.tokens.filter((t) => t.kind === "marker").length; addToken({ id: uid(), kind: "marker", label: RAID_MARKERS[used % RAID_MARKERS.length], color: "#e9cf8e", keyframes: [] }); };
    $("#radda", st.root).onclick = () => addToken({ id: uid(), kind: "aoe", label: "AoE", color: "#e9a43a", radius: 0.16, keyframes: [] });

    // --- selected token editor
    if (st.sel) {
      const tk = p.tokens.find((x) => x.id === st.sel);
      if ($("#slabel", st.root)) $("#slabel", st.root).onchange = (e) => { tk.label = e.target.value; persist(); render(); };
      if ($("#scolor", st.root)) $("#scolor", st.root).onchange = (e) => { tk.color = e.target.value; persist(); render(); };
      if ($("#scls", st.root)) $("#scls", st.root).onchange = (e) => { tk.cls = e.target.value; if (!tk.label || RAID_CLASSES.includes(tk.label)) tk.label = e.target.value; persist(); render(); };
      if ($("#srad", st.root)) $("#srad", st.root).oninput = (e) => { tk.radius = (+e.target.value) / 100; layout(); };
      if ($("#srad", st.root)) $("#srad", st.root).onchange = () => persist();
      if ($("#kadd", st.root)) $("#kadd", st.root).onclick = () => { const pos = tokenPos(tk, st.t) || { x: 0.5, y: 0.5 }; setKeyframe(tk, st.t, pos.x, pos.y); persist(); render(); };
      $$("[data-kgo]", st.root).forEach((b) => (b.onclick = () => { st.t = +b.dataset.kgo; layout(); }));
      $$("[data-kdel]", st.root).forEach((b) => (b.onclick = () => { tk.keyframes.splice(+b.dataset.kdel, 1); persist(); render(); }));
      if ($("#sdel", st.root)) $("#sdel", st.root).onclick = () => { p.tokens = p.tokens.filter((x) => x.id !== st.sel); st.sel = null; persist(); render(); };
    }

    // --- buffs
    $$("[data-bf]", st.root).forEach((inp) => (inp.onchange = () => {
      const bf = p.buffs[+inp.dataset.bf]; if (!bf) return;
      const k = inp.dataset.k; bf[k] = (k === "start" || k === "end") ? (+inp.value || 0) : inp.value;
      persist(); render();
    }));
    $$("[data-bfdel]", st.root).forEach((b) => (b.onclick = () => { p.buffs.splice(+b.dataset.bfdel, 1); persist(); render(); }));
    if ($("#bfadd", st.root)) $("#bfadd", st.root).onclick = () => {
      const name = $("#bfname", st.root).value.trim(); if (!name) { toast("Name the buff"); return; }
      p.buffs.push({ id: uid(), name, by: $("#bfby", st.root).value, start: +$("#bfstart", st.root).value || 0, end: +$("#bfend", st.root).value || 0, note: "" });
      persist(); render();
    };

    // --- compare-with-a-fight overlay
    if ($("#ractual", st.root)) $("#ractual", st.root).onchange = async (e) => {
      const id = e.target.value;
      if (!id) { st.actual = null; render(); return; }
      try {
        const a = await io.encounter(id);
        st.actual = { id: +id, rotation: a.rotation || [], buffs: a.buffs || [], duration: a.summary?.duration || p.duration };
        if (st.actual.duration > p.duration) { p.duration = Math.ceil(st.actual.duration); persist(); }
        render();
      } catch (err) { toast(err.message); }
    };

    // --- transport
    if ($("#rplay", st.root)) $("#rplay", st.root).onclick = () => (st.playing ? pause() : play());
    if ($("#rstart", st.root)) $("#rstart", st.root).onclick = () => { st.t = 0; layout(); };
    if ($("#rspeed", st.root)) $("#rspeed", st.root).onchange = (e) => { st.speed = +e.target.value; };
    if ($("#rscrub", st.root)) $("#rscrub", st.root).oninput = (e) => { if (st.playing) pause(); st.t = +e.target.value; layout(); };

    // --- drag tokens on the map (sets a keyframe at the current time)
    let drag = null;
    const norm = (ev, rect) => ({ x: Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height)) });
    if (arena) {
      arena.addEventListener("pointerdown", (ev) => {
        const el = ev.target.closest(".rtoken"); if (!el) return;
        if (st.playing) pause();
        const tid = el.dataset.tid;
        st.sel = tid; $$(".rtoken", arena).forEach((x) => x.classList.toggle("sel", x.dataset.tid === tid)); layout();
        drag = { tid, el, rect: arena.getBoundingClientRect(), moved: false };
        try { el.setPointerCapture(ev.pointerId); } catch (e) {}
        ev.preventDefault();
      });
      arena.addEventListener("pointermove", (ev) => {
        if (!drag) return;
        const q = norm(ev, drag.rect); drag.x = q.x; drag.y = q.y; drag.moved = true;
        drag.el.style.left = (q.x * 100) + "%"; drag.el.style.top = (q.y * 100) + "%";
        const tk = p.tokens.find((x) => x.id === drag.tid), path = $("#rpath", st.root);
        if (tk && path) { const pts = (tk.keyframes || []).map((k) => Math.abs(k.t - st.t) < 0.06 ? `${q.x * 100},${q.y * 100}` : `${k.x * 100},${k.y * 100}`);
          path.innerHTML = (pts.length > 1 ? `<polyline points="${pts.join(" ")}"/>` : "") + `<circle cx="${q.x * 100}" cy="${q.y * 100}" r="1.6" class="kon"/>`; }
      });
      const drop = () => {
        if (!drag) return; const d = drag; drag = null;
        if (d.moved) { const tk = p.tokens.find((x) => x.id === d.tid); if (tk) { setKeyframe(tk, st.t, d.x, d.y); persist(); } }
        render();
      };
      arena.addEventListener("pointerup", drop);
      arena.addEventListener("pointercancel", drop);
    }

    setBtn();
    if (st.playing) startTimer();     // keep playing across re-renders
    layout();
  }

  function mountPlan() {                 // ensure st.id/st.plan point at a stored plan
    const all = raidPlans();
    if (!st.id || !all[st.id]) {
      const ids = Object.keys(all).sort((a, b) => (all[b].meta?.updated || 0) - (all[a].meta?.updated || 0));
      if (ids.length) st.id = ids[0];
      else { const pl = newPlan("My first plan"); st.id = uid(); all[st.id] = pl; saveRaidPlans(all); }
    }
    st.plan = raidPlans()[st.id];
  }

  async function mount(root, io) {
    if (st.timer) { clearInterval(st.timer); st.timer = null; }
    st.playing = false; st.browsing = null;
    st.root = root; st.io = io || {};
    if (st.speed == null) st.speed = 1;
    if (st.t == null) st.t = 0;
    mountPlan();
    st.encounters = st.io.encounters ? await st.io.encounters().catch(() => []) : [];
    render();
  }

  window.A2Raid = { mount };
})();
