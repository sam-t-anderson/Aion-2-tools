/* The overlay: a compact live meter (polls /api/meter) plus a mini raid-plan timelapse that plays
 * the most recent locally-saved plan. Meant for a frameless, always-on-top, transparent window over
 * the game, but it also works as a normal browser tab. Same origin as the app, so it shares the
 * app's localStorage (the saved plans). */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const n0 = (x) => (x == null || isNaN(x) ? "—" : Math.round(x).toLocaleString("en-US"));
  const SVGNS = "http://www.w3.org/2000/svg";
  let tab = "meter";
  let t = 0;

  function tokenPos(tk, time) {
    const k = tk.keyframes || [];
    if (!k.length) return null;
    if (time <= k[0].t) return { x: k[0].x, y: k[0].y };
    const last = k[k.length - 1];
    if (time >= last.t) return { x: last.x, y: last.y };
    for (let i = 1; i < k.length; i++) {
      if (time <= k[i].t) { const a = k[i - 1], b = k[i], f = (time - a.t) / Math.max(1e-6, b.t - a.t); return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f }; }
    }
    return { x: last.x, y: last.y };
  }
  function latestPlan() {
    let all = {};
    try { all = JSON.parse(localStorage.getItem("a2plans") || "{}"); } catch (e) { all = {}; }
    const ids = Object.keys(all).sort((a, b) => (all[b].meta?.updated || 0) - (all[a].meta?.updated || 0));
    return ids.length ? all[ids[0]] : null;
  }

  const head = (right) => `<div class="ovhd"><span class="ovtabs"><button data-tab="meter" class="${tab === "meter" ? "on" : ""}">Meter</button>
      <button data-tab="plan" class="${tab === "plan" ? "on" : ""}">Plan</button></span><span class="ovsub">${right}</span></div>`;

  function renderMeter(s) {
    const snap = (s && s.snapshot) || { players: [] };
    const mx = Math.max(...snap.players.map((p) => p.dps), 1);
    const rows = snap.players.slice(0, 8).map((p) => `<div class="ovrow"><span class="ovname" title="${esc(p.name)}">${esc(p.name)}</span>
        <div class="ovbar"><i style="width:${100 * p.dps / mx}%"></i><span>${n0(p.dps)} · ${Math.round(100 * p.share)}%</span></div></div>`).join("");
    const right = s && s.running ? `${(snap.duration || 0).toFixed(0)}s · ${n0(snap.dps || 0)} DPS` : "idle";
    $("#ov").innerHTML = `<div class="ovcard">${head(right)}${rows || '<div class="muted">No fight yet. Start the meter in the app.</div>'}</div>`;
    bindTabs();
  }
  function renderPlan() {
    const p = latestPlan();
    if (!p) { $("#ov").innerHTML = `<div class="ovcard">${head("")}<div class="muted">No saved plan yet.</div></div>`; return bindTabs(); }
    const dur = p.duration || 1;
    const svg = [`<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">`];
    svg.push(`<rect x="1" y="1" width="98" height="98" rx="2" fill="none" stroke="#8886" stroke-width="0.6"/>`);
    for (const tk of p.tokens || []) {
      const pos = tokenPos(tk, t % dur);
      if (!pos) continue;
      const col = tk.color || "#39c2e0";
      if (tk.kind === "aoe") svg.push(`<circle cx="${pos.x * 100}" cy="${pos.y * 100}" r="${(tk.radius || 0.14) * 100}" fill="${col}" fill-opacity="0.25" stroke="${col}" stroke-width="0.5"/>`);
      else svg.push(`<circle cx="${pos.x * 100}" cy="${pos.y * 100}" r="${tk.kind === "enemy" ? 3.4 : 2.6}" fill="${col}" stroke="#0008" stroke-width="0.5"/>`);
    }
    svg.push("</svg>");
    $("#ov").innerHTML = `<div class="ovcard">${head(`${esc(p.meta?.name || "plan")} · ${(t % dur).toFixed(0)}/${dur.toFixed(0)}s`)}<div class="ovarena">${svg.join("")}</div></div>`;
    bindTabs();
  }
  function bindTabs() {
    document.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; (tab === "meter" ? pollMeter() : renderPlan()); }));
  }

  let lastSnap = null;
  async function pollMeter() {
    try { lastSnap = await (await fetch("/api/meter")).json(); } catch (e) { /* keep last */ }
    if (tab === "meter") renderMeter(lastSnap);
  }
  // meter poll loop
  setInterval(() => { if (tab === "meter") pollMeter(); }, 800);
  // plan animation loop
  setInterval(() => { t += 0.1; if (tab === "plan") renderPlan(); }, 100);
  pollMeter();
})();
