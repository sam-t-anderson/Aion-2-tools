/* Persistent controls keep tab clicks and slider drags intact while the live content refreshes. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kfmt = (x) => { if (x == null || isNaN(x)) return "—"; const a = Math.abs(x); return a >= 1e6 ? (x / 1e6).toFixed(2) + "M" : a >= 1e3 ? (x / 1e3).toFixed(2) + "K" : Math.round(x).toString(); };
  let tab = "meter", metric = "dps", t = 0, op = 0.72, lastSnap = null, polling = false, nativeReady = false, meterUnavailable = false, refreshError = "", lastSuccess = null;
  const partyMode = new URLSearchParams(location.search).get("view") === "party";
  if (partyMode) document.getElementById("ov").classList.add("ov-party");
  try { const saved=localStorage.getItem("ovmetric"); if(["dps","hps","taken"].includes(saved))metric=saved; } catch(e) { /* optional storage */ }
  try { const v = parseFloat(localStorage.getItem("ovopacity")); if (v >= 0.2 && v <= 1) op = v; } catch (e) { /* optional storage */ }
  let showContribution=true, showTarget=true, showDeaths=true, showEnemyHp=false, showTtk=false, showDummy=true, showCombatPower=true;
  let maxPlayers=8, onlyInCombat=false, autoExpand=false, nameMode="name", classColorNames=false, classSwatch=false, rankNumbers=false, highlightMe=false;
  let interpolate=false, interpolateMs=100, showFps=false, locked=false, userWidth=null, userHeight=null;
  let lastRenderAt=performance.now(), projecting=false, curMax=1;   // for live-ticking DPS between polls
  const shownRates=new Map();   // row key -> currently displayed (eased) rate
  const cap=s=>String(s||'').charAt(0).toUpperCase()+String(s||'').slice(1);
  const displayName=p=>{
    if(nameMode==="number")return "P"+(p.party_number||"?");
    if(nameMode==="class_number")return (cap(p.class)||"Player")+" "+(p.party_number||"?");
    return p.name;
  };
  const clampInt=(v,lo,hi,dflt)=>{v=parseInt(v,10);return Number.isInteger(v)&&v>=lo&&v<=hi?v:dflt;};
  let bgLoaded=false;
  function applyBackground(enabled,op,zoom,dark){
    const el=document.getElementById('ovbg');
    if(!el)return;
    if(!enabled){el.hidden=true;el.style.backgroundImage='';bgLoaded=false;return;}
    if(!bgLoaded){
      // Verify the image loads before showing it, so a missing file is a no-op.
      const probe=new Image();
      probe.onload=()=>{bgLoaded=true;if(lastSnap)renderMeter?.();el.hidden=false;};
      probe.onerror=()=>{bgLoaded=false;el.hidden=true;};
      probe.src='/overlay-background?v='+Date.now();
    }
    const d=Math.max(0,Math.min(1,dark/100));
    el.style.backgroundImage=`linear-gradient(rgba(0,0,0,${d}),rgba(0,0,0,${d})), url('/overlay-background')`;
    el.style.backgroundSize=`auto, ${zoom}%`;
    el.style.backgroundPosition='center';
    el.style.opacity=Math.max(0,Math.min(1,op/100));
    el.hidden=!bgLoaded;
  }
  const syncColors=()=>fetch("/api/ui").then(r=>r.json()).then(ui=>{
    if(ui.combat_colors){try{localStorage.setItem("a2-combat-colors",JSON.stringify(ui.combat_colors));}catch(e){/* optional storage */}}
    for(const key of ['rate','total']){const color=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(`--ov-${key}-text`,/^#[0-9a-f]{6}$/i.test(color||'')?color:'#000000');}
    // Extra text-element colors: name and header (blank = CSS default).
    for(const key of ['name','header']){const c=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(`--ov-${key}-color`,/^#[0-9a-f]{6}$/i.test(c||'')?c:'');}
    // Target-line readout colors: target text, enemy-HP text, TTK text (blank = CSS default).
    for(const [key,cssvar] of [['target','--ov-target-color'],['hp','--ov-hp-text-color'],['ttk','--ov-ttk-text-color']]){const c=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(cssvar,/^#[0-9a-f]{6}$/i.test(c||'')?c:'');}
    // Fonts
    const scale=clampInt(ui.overlay_font_scale,80,160,100), weight=clampInt(ui.overlay_font_weight,400,800,600);
    const fam=typeof ui.overlay_font_family==='string'?ui.overlay_font_family:'';
    document.documentElement.style.setProperty('--ov-font-scale',scale/100);
    document.documentElement.style.setProperty('--ov-font-weight',weight);
    document.documentElement.style.setProperty('--ov-font-family',fam?`"${fam}", "Segoe UI", system-ui, sans-serif`:'');
    // Glow (text-shadow)
    const glow=ui.overlay_glow===true, glowColor=/^#[0-9a-f]{6}$/i.test(ui.overlay_glow_color||'')?ui.overlay_glow_color:'#e8cf8e';
    document.documentElement.style.setProperty('--ov-glow',glow?`0 0 4px ${glowColor}, 0 0 8px ${glowColor}`:'none');
    document.documentElement.style.setProperty('--ov-glow-color',glowColor);
    document.documentElement.style.setProperty('--ov-hp-color',/^#[0-9a-f]{6}$/i.test(ui.overlay_hp_color||'')?ui.overlay_hp_color:'#e05a5a');
    document.documentElement.style.setProperty('--ov-ttk-color',/^#[0-9a-f]{6}$/i.test(ui.overlay_ttk_color||'')?ui.overlay_ttk_color:'#8fb3d0');
    // Crisp text outline for legibility over busy backgrounds (independent of the
    // soft glow; strokes behind the fill). Off by default.
    document.documentElement.style.setProperty('--ov-outline-color',/^#[0-9a-f]{6}$/i.test(ui.overlay_outline_color||'')?ui.overlay_outline_color:'#000000');
    document.getElementById('ov').classList.toggle('ov-outline',ui.overlay_text_outline===true);
    // Animated colour-cycling (palette-shift) on the header and player names.
    // Off by default; respects prefers-reduced-motion (handled in CSS).
    document.getElementById('ov').classList.toggle('ov-cycle',ui.overlay_color_cycle===true);
    // Bar visual styles: gradient fill and rounded corners (per-class bar colour
    // stays, set per row as --bar), and optionally colour player names by class.
    document.getElementById('ov').classList.toggle('ov-bars-gradient',ui.overlay_bar_style==='gradient');
    document.getElementById('ov').classList.toggle('ov-bars-rounded',ui.overlay_bar_rounded===true);
    classColorNames=ui.overlay_class_color_names===true;
    classSwatch=ui.overlay_class_swatch===true;
    rankNumbers=ui.overlay_rank_numbers===true;
    // Highlight your own row so you can find yourself instantly in a party list.
    highlightMe=ui.overlay_highlight_me===true;
    // Zebra striping: a subtle alternating background on the player rows for a
    // clearer list at a glance. Off by default.
    document.getElementById('ov').classList.toggle('ov-stripes',ui.overlay_row_stripes===true);
    // Compact rows: hide each row's trailing total · percent, leaving just the
    // per-second rate — tidier on a narrow overlay. Off by default.
    document.getElementById('ov').classList.toggle('ov-compact',ui.overlay_compact_rows===true);
    // Long-name scrolling
    document.getElementById('ov').classList.toggle('ov-scroll-names',ui.overlay_long_names_scroll===true);
    // Background photo (opacity 0 = none). The image load errors are swallowed.
    const bgOp=clampInt(ui.overlay_bg_opacity,0,100,100), bgZoom=clampInt(ui.overlay_bg_zoom,50,200,100), bgDark=clampInt(ui.overlay_bg_darken,0,100,20);
    applyBackground(ui.overlay_bg_set===true && bgOp>0, bgOp, bgZoom, bgDark);
    showContribution=ui.overlay_show_contribution!==false;
    showTarget=ui.overlay_show_target!==false;
    showDeaths=ui.overlay_show_deaths!==false;
    showEnemyHp=ui.overlay_show_enemy_hp===true;
    showTtk=ui.overlay_show_ttk===true;
    showDummy=ui.meter_show_dummy_parse!==false;
    showCombatPower=ui.overlay_show_combat_power!==false;
    nameMode=["name","class_number","number"].includes(ui.overlay_name_mode)?ui.overlay_name_mode:"name";
    interpolate=ui.overlay_dps_interpolate===true;
    interpolateMs=clampInt(ui.overlay_interpolate_ms,50,1000,50);
    showFps=ui.overlay_show_fps===true;
    $("#ovfps").hidden=!showFps||partyMode;
    // Layout
    maxPlayers=clampInt(ui.overlay_max_players,1,24,8);
    onlyInCombat=ui.overlay_only_in_combat===true;
    autoExpand=ui.overlay_auto_expand===true;
    document.documentElement.style.setProperty('--ov-width',(userWidth??clampInt(ui.overlay_width,260,800,340))+'px');
    const h=userHeight??clampInt(ui.overlay_height,0,800,0);
    document.documentElement.style.setProperty('--ov-height',h>0?h+'px':'0px');
    document.documentElement.style.setProperty('--ov-row-h',clampInt(ui.overlay_row_height,14,48,22)+'px');
    document.getElementById("ov").classList.toggle("ov-resizable",ui.overlay_resizable===true&&!partyMode);
    if(lastSnap)renderMeter();
    fit();
  }).catch(()=>{});
  const fmtTtk=(s)=>{s=Math.round(s);return s>=3600?`${Math.floor(s/3600)}h${Math.floor(s%3600/60)}m`:s>=60?`${Math.floor(s/60)}m${String(s%60).padStart(2,'0')}s`:`${s}s`;};
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
  function renderParty() {
    // The separate Party-DPS overlay: raid-wide aggregates, not per-player rows.
    const s = lastSnap || {}, snap = s.snapshot || {}, players = snap.players || [];
    for(const id of ["#ovmetrics","#ovping","#ovidentity","#ovtarget","#ovhpbar","#ovttkbar","#ovcontribution","#ovdummy","#ovconnection"])$(id).hidden=true;
    const totalDps=players.reduce((n,p)=>n+(Number(p.dps)||0),0);
    const totalHps=players.reduce((n,p)=>n+(Number(p.hps)||0),0);
    const totalTaken=players.reduce((n,p)=>n+(Number(p.dtps)||0),0);
    const total=players.reduce((n,p)=>n+(Number(p.damage)||0),0);
    $("#ovstatus").textContent=`Party · ${snap.boss||(s.running?"recording":"idle")} · ${players.length} players`;
    $("#ovstatus").title=$("#ovstatus").textContent;
    const stat=(label,val,unit)=>`<div class="ovpstat"><span class="ovplabel">${label}</span><span class="ovpval">${kfmt(val)}${unit||''}</span></div>`;
    $("#ovcontent").innerHTML = players.length
      ? stat("Party DPS",totalDps,"/s")+stat("Party HPS",totalHps,"/s")+stat("Damage taken/s",totalTaken,"/s")+stat("Total damage",total,"")
      : `<div class="muted">${esc(s.running?"Waiting for combat data…":"No fight yet. Start the meter in the app.")}</div>`;
  }
  function renderMeter() {
    if(partyMode)return renderParty();
    const s = lastSnap || {}, snap = s.snapshot || {}, players = snap.players || [];
    // Anchor the live-ticking DPS to this snapshot: between polls the displayed
    // average DPS is recomputed from real damage and the elapsing clock (not
    // invented), and only while combat is actually running and unpaused.
    lastRenderAt=performance.now(); projecting=!!(s&&s.running)&&!snap.paused;
    $("#ovmetrics").hidden=false;
    const ping=snap.ping;$('#ovping').hidden=false;
    $('#ovping').textContent=ping?`Ping ${Number(ping.current).toFixed(0)} ms · Avg ${Number(ping.avg).toFixed(0)} ms · Min ${Number(ping.min).toFixed(0)} / Max ${Number(ping.max).toFixed(0)} ms`:'Ping: no recorded samples';
    $('#ovping').title='Passive TCP RTT for this recording connection; average/minimum/maximum across the capture';
    document.querySelectorAll("[data-metric]").forEach(b=>{b.classList.toggle("on",b.dataset.metric===metric);b.setAttribute("aria-pressed",String(b.dataset.metric===metric));});
    if(!$("#ovcombine").disabled) $("#ovcombine").checked=s.combine_pets!==false;
    const amount=p=>Number(metric==="hps"?p.healing:metric==="taken"?p.incoming?.damage:p.damage)||0;
    const rate=p=>Number(metric==="hps"?p.hps:metric==="taken"?p.dtps:p.dps)||0;
    const total=players.reduce((n,p)=>n+amount(p),0), mx=Math.max(...players.map(rate),1);
    curMax=mx;   // the rate the full bar represents, so between-poll ticks can ease bar widths too
    const label=metric==="hps"?"HPS":metric==="taken"?"Damage taken/s":"DPS";
    const visible=players.filter(p=>amount(p)>0), names=new Map();
    visible.forEach(p=>{const name=String(p.name||'').toLocaleLowerCase();names.set(name,(names.get(name)||0)+1);});
    const duplicate=p=>(names.get(String(p.name||'').toLocaleLowerCase())||0)>1;
    const shownCount = autoExpand ? Math.min(24, Math.max(maxPlayers, visible.length)) : maxPlayers;
    // Your own row (matched by the re-acquired local name) can be highlighted.
    const meName = highlightMe && snap.identity_status && snap.identity_status.local_name ? String(snap.identity_status.local_name).toLocaleLowerCase() : "";
    const isMe = p => meName && String(p.name||'').toLocaleLowerCase() === meName;
    const rows = [...visible].sort((a,b)=>rate(b)-rate(a)||amount(b)-amount(a)).slice(0, shownCount).map((p, i) => `<div class="ovrow${showDeaths&&p.dead?' ovrow-dead':''}${isMe(p)?' ovrow-me':''}"><span class="ovname" title="${esc(p.name)} · Actor ${esc(p.key || p.id)}${p.includes_pets?" · Includes linked pets":""}">${rankNumbers?`<span class="ovrank">${i+1}.</span>`:''}${classSwatch?`<i class="ovclass" style="background:${A2CombatReview.color(p.class)}" title="${esc(p.class||'')}"></i>`:''}<span class="ovnametext"${classColorNames?` style="color:${A2CombatReview.color(p.class)}"`:''}>${esc(displayName(p))}</span>${nameMode==="name"&&duplicate(p)?`<small class="ovactor">#${esc(p.id)}</small>`:''}${showDeaths&&p.dead?'<small class="ovdead">DEAD</small>':''}</span>
        <div class="ovbar" title="${esc(label)}: ${kfmt(rate(p))} · Total: ${kfmt(amount(p))}"><i data-k="${esc(p.key||p.id)}" style="width:${100 * rate(p) / mx}%;--bar:${A2CombatReview.color(p.class)}"></i><span><span class="ovrate" data-k="${esc(p.key||p.id)}" data-target="${rate(p)}" data-amt="${amount(p)}">${kfmt(rate(p))}</span>/s <span class="sub">${kfmt(amount(p))} · ${Math.round(100 * amount(p) / (total||1))}%</span></span></div></div>`).join("");
    const duration=metric==="dps"?snap.duration:snap.recorded_duration;
    $("#ovstatus").textContent = `Latest combat · ${snap.paused && metric==="dps" ? "Paused DPS · " : ""}${snap.boss || (s.running ? "recording" : "idle")} · ${(Number(duration) || 0).toFixed(0)}s · ${kfmt(players.reduce((n,p)=>n+rate(p),0))} ${label}`;
    const identity=snap.identity_status, missing=players.length>0&&identity&&(!identity.self_identified||identity.unnamed_actors>0), repeated=visible.some(duplicate);
    // A zone load (tele/port/revive/instance) reassigns your actor id; show the
    // re-acquired identity so a brief "not received" gap is visibly recovered.
    const selfName=identity&&identity.local_name;
    const cp=showCombatPower&&identity&&identity.local_combat_power;
    const selfLine=selfName?`You: ${selfName}${cp?` · CP ${kfmt(identity.local_combat_power)}`:''}`:'';
    $("#ovidentity").hidden=!missing&&!repeated&&!selfName;
    $("#ovidentity").classList.toggle("ok",!missing&&!repeated&&!!selfName);
    $("#ovidentity").textContent=[missing?`${identity.self_identified?"Self identified":"Self identity not received — teleport or change instances to refresh it"} · ${identity.unnamed_actors} unnamed actors · ${identity.linked_pets} linked pets. Grouping needs recorded owner links.`:selfLine,repeated?'Matching names have separate combat actor IDs; names alone do not establish shared identity or ownership.':''].filter(Boolean).join(' ');
    if(s.error) $("#ovstatus").textContent='Capture stopped: '+s.error;
    if(meterUnavailable) $("#ovstatus").textContent='Refresh failed · retrying';
    $("#ovstatus").title=$("#ovstatus").textContent;
    $("#ovconnection").hidden=!meterUnavailable;
    if(meterUnavailable) $("#ovreason").textContent=refreshError+' · '+(lastSuccess ? Math.floor((Date.now()-lastSuccess)/1000)+'s since last refresh. ' : '')+'Last readings retained; capture status unknown.';
    // Reset after battle: once combat has been idle past the delay, clear the live
    // view to a ready state (the data is kept; a selected segment still shows it).
    const over=snap.battle_over===true;
    const empty = s.error || (over ? "Ready — waiting for the next fight." : players.length?`No recorded ${metric==='hps'?'healing':metric==='taken'?'incoming damage':'outgoing damage'} in this combat.`:snap.warning || (s.running ? "Waiting for combat data…" : "No fight yet. Start the meter in the app."));
    $("#ovcontent").innerHTML = over ? `<div class="muted">${esc(empty)}</div>` : (players.length && snap.warning ? `<div class="muted">${esc(snap.warning)}</div>` : "") + (rows || `<div class="muted">${esc(empty)}</div>`);
    // Current target (the enemy you are hitting most) with each contributor's DPS
    // to it; packet-sourced, shown when there is recorded damage and enabled.
    const target=snap.current_target;
    const showT=showTarget&&!over&&target&&!target.is_player&&(target.contributors||[]).length;
    $("#ovtarget").hidden=!showT;
    if(showT){
      const top=(target.contributors||[]).slice(0,3)
        .map(c=>`${esc(c.name)} ${kfmt(c.dps)}/s`).join(' · ');
      const hp=showEnemyHp&&target.hp_pct!=null
        ? ` <span class="ovhp">${Math.round(target.hp_pct*100)}%${target.current_hp!=null?` (${kfmt(target.current_hp)}${target.max_hp?'/'+kfmt(target.max_hp):''})`:''}</span>` : '';
      const ttk=showTtk&&target.ttk!=null&&isFinite(target.ttk)
        ? ` <span class="ovttk">TTK ${fmtTtk(target.ttk)}</span>` : '';
      // When several enemies are being struck in the same instant (AOE/cleave), the
      // single "most-hit" target is one of several — name the others compactly.
      const alsoNames=(target.also_targets||[]);
      const also=alsoNames.length?` <span class="ovalso" title="Also being hit right now: ${esc(alsoNames.join(', '))}">+${alsoNames.length} (${esc(alsoNames.map(n=>String(n)).join(', '))})</span>`:'';
      $("#ovtarget").innerHTML=`<span class="ovtlabel">Target</span> ${esc(target.name)}${also}${hp}${ttk} <span class="sub">${kfmt(target.damage)}</span>${top?` — ${top}`:''}`;
      $("#ovtarget").title=`Most-hit enemy this encounter${alsoNames.length?` (and ${alsoNames.length} more struck in the same instant)`:''}, its remaining HP and time-to-kill from its observed HP-decline rate (all damage sources, so it reflects how fast it is really dying — not just your party's DPS), and each contributor's DPS to it`;
    }
    // Drawn remaining-over-max enemy HP bar, shown with the enemy-HP readout when real HP was captured.
    const showBar=showT&&showEnemyHp&&target&&target.hp_pct!=null;
    $("#ovhpbar").hidden=!showBar;
    if(showBar)$("#ovhpbar").firstElementChild.style.width=Math.max(0,Math.min(100,target.hp_pct*100))+"%";
    // Drawn time-to-kill bar: how far through the estimated whole kill we are by time
    // (seconds engaged so far over engaged + remaining). Shown with the TTK readout
    // when a TTK is available; distinct from the HP bar (health remaining).
    const showTtkBar=showT&&showTtk&&target&&target.ttk_fraction!=null&&isFinite(target.ttk_fraction);
    $("#ovttkbar").hidden=!showTtkBar;
    if(showTtkBar){
      $("#ovttkbar").firstElementChild.style.width=Math.max(0,Math.min(100,target.ttk_fraction*100))+"%";
      $("#ovttkbar").title=`Estimated kill progress by time — how much of the whole kill has elapsed (engaged time so far vs the time-to-kill still remaining). Packet-sourced; it can run ahead of or behind the HP bar when the fight starts slow or finishes fast.`;
    }
    // Training-dummy parse: elapsed vs the standard window, your DPS and the total.
    const dummy=snap.dummy_parse;
    const showD=showDummy&&!over&&dummy&&metric==='dps';
    $("#ovdummy").hidden=!showD;
    if(showD){
      const dur=Math.round(dummy.duration||0), win=Math.round(dummy.window_seconds||0);
      const you=dummy.your_dps!=null?` · You ${kfmt(dummy.your_dps)}/s`:'';
      $("#ovdummy").classList.toggle("ok",!!dummy.window_reached);
      $("#ovdummy").innerHTML=`<span class="ovtlabel">Dummy parse</span> ${dur}s / ${win}s${dummy.window_reached?' ✓':''}${you} · Total ${kfmt(dummy.target_dps)}/s`;
      $("#ovdummy").title=`Training-dummy parse: elapsed vs the standard window (Settings), your DPS and the party total to the dummy`;
    }
    // Your contribution: your share of the shown encounter's damage.
    const c=snap.contribution;
    const showC=showContribution&&!over&&c&&c.damage>0&&metric==='dps';
    $("#ovcontribution").hidden=!showC;
    if(showC) $("#ovcontribution").textContent=`Your contribution: ${Math.round((c.share||0)*100)}% · ${kfmt(c.damage)} (${kfmt(c.dps)}/s)`;
    // Show meter only during combat: collapse to the header when idle (the window
    // then shrinks via fit), so the overlay is unobtrusive between pulls.
    if(onlyInCombat && (!s.running || snap.paused || over)){
      $("#ovcontent").innerHTML='';
      for(const id of ["#ovmetrics","#ovping","#ovtarget","#ovhpbar","#ovttkbar","#ovcontribution","#ovdummy","#ovidentity"])$(id).hidden=true;
      $("#ovstatus").textContent=s.running?'Idle · waiting for combat':'Idle';
      $("#ovstatus").title=$("#ovstatus").textContent;
    }
  }
  function renderPlan() {
    $("#ovmetrics").hidden=true;$("#ovping").hidden=true;$("#ovidentity").hidden=true;
    $("#ovtarget").hidden=true;$("#ovhpbar").hidden=true;$("#ovttkbar").hidden=true;$("#ovcontribution").hidden=true;$("#ovdummy").hidden=true;$("#ovfps").hidden=true;
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
    if (polling || locked) return;   // frozen for a screenshot
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
  setInterval(() => { if (tab === "meter") pollMeter(); }, 500);
  setInterval(() => { t += 0.1; if (tab === "plan") renderPlan(); }, 100);
  window.addEventListener("storage", (event) => { if (event.key === "aion2calc-closing") window.close(); });

  // Drag-to-resize: the frameless window auto-fits the card, so the grips drive the
  // card width/height and the window follows (fit()). A right-edge grip resizes
  // width, a bottom-edge grip resizes height, and a bottom-right corner does both.
  // The new size persists as overlay_width / overlay_height. The grips sit outside
  // the card's drag region so dragging them resizes instead of moving the window.
  // Off unless Settings → Overlay layout enables it.
  const attachResize=(grip,horiz,vert)=>{
    if(!grip)return;
    grip.addEventListener("pointerdown",e=>{
      e.preventDefault(); e.stopPropagation();
      const startX=e.clientX, startY=e.clientY, card=document.querySelector("#ov .ovcard");
      const rect=card?card.getBoundingClientRect():{width:340,height:120};
      const startW=rect.width, startH=rect.height;
      try{grip.setPointerCapture(e.pointerId);}catch(_){}
      const move=ev=>{
        if(horiz){userWidth=Math.max(260,Math.min(800,Math.round(startW+(ev.clientX-startX))));
          document.documentElement.style.setProperty('--ov-width',userWidth+'px');}
        if(vert){userHeight=Math.max(70,Math.min(800,Math.round(startH+(ev.clientY-startY))));
          document.documentElement.style.setProperty('--ov-height',userHeight+'px');}
        fit();
      };
      const up=()=>{
        document.removeEventListener("pointermove",move); document.removeEventListener("pointerup",up);
        const body={};
        if(horiz&&userWidth!=null)body.overlay_width=userWidth;
        if(vert&&userHeight!=null)body.overlay_height=userHeight;
        if(Object.keys(body).length)fetch("/api/ui",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).catch(()=>{});
      };
      document.addEventListener("pointermove",move); document.addEventListener("pointerup",up);
    });
  };
  attachResize($("#ovresize"),true,false);
  attachResize($("#ovresize-b"),false,true);
  attachResize($("#ovresize-c"),true,true);

  // Screenshot & lock: freeze the display and keep the overlay pinned (even when
  // the game loses focus) so it can be captured; a second click resumes.
  const lockBtn=$("#ovlock");
  if(lockBtn)lockBtn.onclick=()=>{
    locked=!locked;
    lockBtn.textContent=locked?"Unlock":"Lock";
    lockBtn.classList.toggle("on",locked);
    document.getElementById("ov").classList.toggle("ov-locked",locked);
    nativeCall("set_locked",locked);
    if(!locked)pollMeter();
  };

  // Live-ticking DPS: between polls, recompute each row's real average rate with
  // the elapsing clock (amount / (elapsed + time-since-poll)) so the number keeps
  // moving in real time instead of freezing on the last poll value, then ease the
  // displayed number toward it for smoothness. Still packet-sourced: the amount is
  // the recorded damage/healing, only the time denominator advances. The refresh
  // interval is user-set so weaker machines can slow or disable it.
  setInterval(()=>{
    if(!interpolate||tab!=="meter"||locked)return;
    const dt=projecting?Math.max(0,(performance.now()-lastRenderAt)/1000):0;
    const seen=new Set();
    document.querySelectorAll("#ovcontent .ovrate").forEach(el=>{
      const key=el.getAttribute("data-k"), target=parseFloat(el.getAttribute("data-target"))||0;
      const amt=parseFloat(el.getAttribute("data-amt"))||0;
      seen.add(key);
      // Project the average rate forward: amount/(amount/target + dt). Decays while
      // no new damage arrives, snaps back up on the next poll's fresh amount/target.
      const live=(dt>0&&amt>0&&target>0)?(amt*target)/(amt+target*dt):target;
      const cur=shownRates.has(key)?shownRates.get(key):live;
      const next=cur+(live-cur)*0.4;   // ease toward the live value (snappier at the higher frame rate)
      const shown=Math.abs(next-live)<0.5?live:next;
      shownRates.set(key,shown);
      el.textContent=kfmt(shown);
      // Ease the bar fill the same way so the length tracks the live number
      // instead of snapping each poll (CSS transition smooths the final step).
      const bar=el.closest(".ovbar");
      if(bar&&bar.firstElementChild)bar.firstElementChild.style.width=Math.max(0,Math.min(100,100*shown/curMax))+"%";
    });
    for(const k of [...shownRates.keys()])if(!seen.has(k))shownRates.delete(k);
  },interpolateMs);

  // Overlay render FPS (the overlay's own frame rate, not the game's — packet
  // capture cannot see game FPS). Off by default.
  let frames=0, fpsAt=performance.now();
  (function fpsLoop(now){
    frames++;
    if(now-fpsAt>=1000){
      if(showFps&&!partyMode){const el=$("#ovfps");if(el)el.textContent="Overlay "+Math.round(frames*1000/(now-fpsAt))+" FPS";}
      frames=0; fpsAt=now;
    }
    requestAnimationFrame(fpsLoop);
  })(performance.now());

  applyOpacity(); renderMeter(); pollMeter();
})();
