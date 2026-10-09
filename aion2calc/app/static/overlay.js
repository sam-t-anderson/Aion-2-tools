/* Persistent controls keep tab clicks and slider drags intact while the live content refreshes. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kfmt = (x) => { if (x == null || isNaN(x)) return "—"; const a = Math.abs(x); return a >= 1e6 ? (x / 1e6).toFixed(2) + "M" : a >= 1e3 ? (x / 1e3).toFixed(2) + "K" : Math.round(x).toString(); };
  let tab = "meter", metric = "dps", t = 0, op = 0.72, lastSnap = null, polling = false, nativeReady = false, meterUnavailable = false, refreshError = "", lastSuccess = null;
  try { const saved=localStorage.getItem("ovmetric"); if(["dps","hps","taken"].includes(saved))metric=saved; } catch(e) { /* optional storage */ }
  try { const v = parseFloat(localStorage.getItem("ovopacity")); if (v >= 0.2 && v <= 1) op = v; } catch (e) { /* optional storage */ }
  const syncColors=()=>fetch("/api/ui").then(r=>r.json()).then(ui=>{
    if(ui.combat_colors){try{localStorage.setItem("a2-combat-colors",JSON.stringify(ui.combat_colors));}catch(e){/* optional storage */}}
    for(const key of ['rate','total']){const color=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(`--ov-${key}-text`,/^#[0-9a-f]{6}$/i.test(color||'')?color:'#000000');}
  }).catch(()=>{});
  syncColors();setInterval(syncColors,10000);
  const slider = $("#ovop");
  $("#ovhide").onclick = () => fetch("/api/overlay", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"hide"})}).then(()=>window.close());
  $("#ovcombine").onchange = async () => {
    const input=$("#ovcombine"), message=$("#ovpetstatus"); input.disabled=true;
    try { const response=await fetch("/api/meter",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"view",combine_pets:input.checked})});if(!response.ok)throw Error("Could not change pet grouping");await response.json();message.textContent="";await pollMeter(); }
    catch(e){message.textContent=e.message;}
    finally{input.disabled=false;}
  };
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
    $("#ovmetrics").hidden=false;
    const ping=snap.ping;$('#ovping').hidden=false;
    $('#ovping').textContent=ping?`Ping ${Number(ping.current).toFixed(0)} ms · Avg ${Number(ping.avg).toFixed(0)} ms · Min ${Number(ping.min).toFixed(0)} / Max ${Number(ping.max).toFixed(0)} ms`:'Ping: no recorded samples';
    $('#ovping').title='Passive TCP RTT for this recording connection; average/minimum/maximum across the capture';
    document.querySelectorAll("[data-metric]").forEach(b=>{b.classList.toggle("on",b.dataset.metric===metric);b.setAttribute("aria-pressed",String(b.dataset.metric===metric));});
    if(!$("#ovcombine").disabled) $("#ovcombine").checked=s.combine_pets!==false;
    const amount=p=>Number(metric==="hps"?p.healing:metric==="taken"?p.incoming?.damage:p.damage)||0;
    const rate=p=>Number(metric==="hps"?p.hps:metric==="taken"?p.dtps:p.dps)||0;
    const total=players.reduce((n,p)=>n+amount(p),0), mx=Math.max(...players.map(rate),1);
    const label=metric==="hps"?"HPS":metric==="taken"?"Damage taken/s":"DPS";
    const visible=players.filter(p=>amount(p)>0), names=new Map();
    visible.forEach(p=>{const name=String(p.name||'').toLocaleLowerCase();names.set(name,(names.get(name)||0)+1);});
    const duplicate=p=>(names.get(String(p.name||'').toLocaleLowerCase())||0)>1;
    const rows = [...visible].sort((a,b)=>rate(b)-rate(a)||amount(b)-amount(a)).slice(0, 8).map((p) => `<div class="ovrow"><span class="ovname" title="${esc(p.name)} · Actor ${esc(p.key || p.id)}${p.includes_pets?" · Includes linked pets":""}">${esc(p.name)}${duplicate(p)?`<small class="ovactor">#${esc(p.id)}</small>`:''}</span>
        <div class="ovbar" title="${esc(label)}: ${kfmt(rate(p))} · Total: ${kfmt(amount(p))}"><i style="width:${100 * rate(p) / mx}%;background:${A2CombatReview.color(p.class)}"></i><span>${kfmt(rate(p))}/s <span class="sub">${kfmt(amount(p))} · ${Math.round(100 * amount(p) / (total||1))}%</span></span></div></div>`).join("");
    const duration=metric==="dps"?snap.duration:snap.recorded_duration;
    $("#ovstatus").textContent = `Latest combat · ${snap.paused && metric==="dps" ? "Paused DPS · " : ""}${snap.boss || (s.running ? "recording" : "idle")} · ${(Number(duration) || 0).toFixed(0)}s · ${kfmt(players.reduce((n,p)=>n+rate(p),0))} ${label}`;
    const identity=snap.identity_status, missing=players.length>0&&identity&&(!identity.self_identified||identity.unnamed_actors>0), repeated=visible.some(duplicate);
    $("#ovidentity").hidden=!missing&&!repeated;
    $("#ovidentity").textContent=[missing?`${identity.self_identified?"Self identified":"Self identity not received"} · ${identity.unnamed_actors} unnamed actors · ${identity.linked_pets} linked pets. Grouping needs recorded owner links.`:'',repeated?'Matching names have separate combat actor IDs; names alone do not establish shared identity or ownership.':''].filter(Boolean).join(' ');
    if(s.error) $("#ovstatus").textContent='Capture stopped: '+s.error;
    if(meterUnavailable) $("#ovstatus").textContent='Refresh failed · retrying';
    $("#ovstatus").title=$("#ovstatus").textContent;
    $("#ovconnection").hidden=!meterUnavailable;
    if(meterUnavailable) $("#ovreason").textContent=refreshError+' · '+(lastSuccess ? Math.floor((Date.now()-lastSuccess)/1000)+'s since last refresh. ' : '')+'Last readings retained; capture status unknown.';
    const empty = s.error || (players.length?`No recorded ${metric==='hps'?'healing':metric==='taken'?'incoming damage':'outgoing damage'} in this combat.`:snap.warning || (s.running ? "Waiting for combat data…" : "No fight yet. Start the meter in the app."));
    $("#ovcontent").innerHTML = (players.length && snap.warning ? `<div class="muted">${esc(snap.warning)}</div>` : "") + (rows || `<div class="muted">${esc(empty)}</div>`);
  }
  function renderPlan() {
    $("#ovmetrics").hidden=true;$("#ovping").hidden=true;$("#ovidentity").hidden=true;
    $("#ovconnection").hidden=true;
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
  document.querySelectorAll("[data-metric]").forEach(button=>{button.onclick=()=>{
    metric=button.dataset.metric;
    try{localStorage.setItem("ovmetric",metric);}catch(e){/* optional storage */}
    renderMeter();
  };});
  async function pollMeter() {
    if (polling) return;
    polling = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch("/api/meter?view=latest", { signal: controller.signal });
      let next;
      try { next=await response.json(); }
      catch(e) { throw Error('Invalid meter JSON (HTTP '+response.status+')'); }
      if (!response.ok) throw Error('HTTP '+response.status+': '+String(next.error||response.statusText).slice(0,512));
      if(!next||typeof next.running!=='boolean'||!next.snapshot) throw Error('Invalid meter response');
      lastSnap=next;meterUnavailable=false;refreshError="";lastSuccess=Date.now();
    } catch (e) {
      meterUnavailable=true;
      refreshError=e.name==='AbortError'?'Meter refresh timed out after 4s':String(e.message||e).slice(0,512);
    }
    finally { clearTimeout(timeout); polling = false; }
    if (tab === "meter") renderMeter();
  }
  $("#ovretry").onclick=()=>pollMeter();
  setInterval(() => { if (tab === "meter") pollMeter(); }, 800);
  setInterval(() => { t += 0.1; if (tab === "plan") renderPlan(); }, 100);
  window.addEventListener("storage", (event) => { if (event.key === "aion2calc-closing") window.close(); });
  applyOpacity(); renderMeter(); pollMeter();
})();
