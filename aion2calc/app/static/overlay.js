/* Persistent controls keep tab clicks and slider drags intact while the live content refreshes. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kfmt = (x) => { if (x == null || isNaN(x)) return "—"; const a = Math.abs(x); return a >= 1e6 ? (x / 1e6).toFixed(2) + "M" : a >= 1e3 ? (x / 1e3).toFixed(2) + "K" : Math.round(x).toString(); };
  let tab = "meter", t = 0, op = 0.72, lastSnap = null, polling = false, nativeReady = false;
  try { const v = parseFloat(localStorage.getItem("ovopacity")); if (v >= 0.2 && v <= 1) op = v; } catch (e) { /* optional storage */ }
  const syncColors=()=>fetch("/api/ui").then(r=>r.json()).then(ui=>{if(ui.combat_colors)localStorage.setItem("a2-combat-colors",JSON.stringify(ui.combat_colors));}).catch(()=>{});
  syncColors();setInterval(syncColors,10000);
  const slider = $("#ovop");
  $("#ovhide").onclick = () => fetch("/api/overlay", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"hide"})}).then(()=>window.close());
  slider.value = Math.round(op * 100);
  function nativeCall(name, ...args) {
    const api = nativeReady && window.pywebview?.api;
    if (api && typeof api[name] === "function") api[name](...args).catch(() => {});
  }
  function fit() {
    nativeCall("fit", Math.ceil($("#ov").getBoundingClientRect().width), Math.ceil($("#ov").getBoundingClientRect().height));
  }
  function applyOpacity() {
    document.documentElement.style.setProperty("--ovbg", op);
    nativeCall("set_opacity", op);
  }
  function nativeInit() {
    nativeReady = true;
    document.documentElement.classList.toggle("native-windows", window.pywebview?.platform === "edgechromium");
    applyOpacity(); fit();
  }
  window.addEventListener("pywebviewready", nativeInit);
  if (window.pywebview?.api?.fit) nativeInit();
  new ResizeObserver(fit).observe($("#ov"));

  // These events must not bubble into pywebview's card drag handler.
  document.querySelectorAll("button, input, label").forEach((control) => {
    ["pointerdown", "mousedown", "touchstart"].forEach((type) => control.addEventListener(type, (event) => event.stopPropagation()));
  });
  slider.oninput = () => {
    op = Math.max(0.2, Math.min(1, slider.value / 100)); applyOpacity();
    try { localStorage.setItem("ovopacity", op); } catch (e) { /* optional storage */ }
  };

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
  function renderMeter() {
    const s = lastSnap || {}, snap = s.snapshot || {}, players = snap.players || [];
    const mx = Math.max(...players.map((p) => p.dps || 0), 1);
    const rows = players.slice(0, 8).map((p) => `<div class="ovrow"><span class="ovname" title="${esc(p.name)}">${esc(p.name)}</span>
        <div class="ovbar"><i style="width:${100 * (p.dps || 0) / mx}%;background:${A2CombatReview.color(p.class)}"></i><span>${kfmt(p.dps)}/s <span class="sub">${kfmt(p.damage)} · ${Math.round(100 * (p.share || 0))}%</span></span></div></div>`).join("");
    $("#ovstatus").textContent = `${snap.boss || (s.running ? "recording" : "idle")} · ${(Number(snap.duration) || 0).toFixed(0)}s · ${kfmt(snap.dps || 0)}/s`;
    const empty = s.error || (s.running ? "Waiting for combat data…" : "No fight yet. Start the meter in the app.");
    $("#ovcontent").innerHTML = rows || `<div class="muted">${esc(empty)}</div>`;
  }
  function renderPlan() {
    const p = latestPlan();
    if (!p) {
      $("#ovstatus").textContent = "";
      $("#ovcontent").innerHTML = '<div class="muted">No saved plan yet.</div>';
      return;
    }
    const dur = Math.max(1, Number(p.duration) || 1);
    const svg = ['<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet"><rect x="1" y="1" width="98" height="98" rx="2" fill="none" stroke="#8886" stroke-width="0.6"/>'];
    for (const tk of p.tokens || []) {
      const pos = tokenPos(tk, t % dur);
      if (!pos) continue;
      const col = esc(tk.color || "#39c2e0"), x = Number(pos.x) * 100, y = Number(pos.y) * 100;
      if (tk.kind === "aoe") svg.push(`<circle cx="${x}" cy="${y}" r="${(Number(tk.radius) || 0.14) * 100}" fill="${col}" fill-opacity="0.25" stroke="${col}" stroke-width="0.5"/>`);
      else svg.push(`<circle cx="${x}" cy="${y}" r="${tk.kind === "enemy" ? 3.4 : 2.6}" fill="${col}" stroke="#0008" stroke-width="0.5"/>`);
    }
    svg.push("</svg>");
    $("#ovstatus").textContent = `${p.meta?.name || "plan"} · ${(t % dur).toFixed(0)}/${dur.toFixed(0)}s`;
    $("#ovcontent").innerHTML = `<div class="ovarena">${svg.join("")}</div>`;
  }
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.onclick = () => {
      tab = button.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach((b) => {
        b.classList.toggle("on", b.dataset.tab === tab);
        b.setAttribute("aria-selected", String(b.dataset.tab === tab));
      });
      $("#ovcontent").setAttribute("aria-labelledby", `${tab}-tab`);
      if (tab === "meter") { renderMeter(); pollMeter(); } else renderPlan();
    };
  });
  async function pollMeter() {
    if (polling) return;
    polling = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch("/api/meter", { signal: controller.signal });
      if (response.ok) lastSnap = await response.json();
    } catch (e) { /* Preserve the last meter when the application is temporarily unavailable. */ }
    finally { clearTimeout(timeout); polling = false; }
    if (tab === "meter") renderMeter();
  }
  setInterval(() => { if (tab === "meter") pollMeter(); }, 800);
  setInterval(() => { t += 0.1; if (tab === "plan") renderPlan(); }, 100);
  window.addEventListener("storage", (event) => { if (event.key === "aion2calc-closing") window.close(); });
  applyOpacity(); renderMeter(); pollMeter();
})();
