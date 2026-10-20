/* Persistent controls keep tab clicks and slider drags intact while the live content refreshes. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const kfmt = (x) => { if (x == null || isNaN(x)) return "—"; const a = Math.abs(x); return a >= 1e6 ? (x / 1e6).toFixed(2) + "M" : a >= 1e3 ? (x / 1e3).toFixed(2) + "K" : Math.round(x).toString(); };
  let tab = "meter", metric = "dps", t = 0, op = 0.72, lastSnap = null, polling = false, nativeReady = false, meterUnavailable = false, refreshError = "", lastSuccess = null;
  let clickThrough = false, rectTimer = 0;
  const partyMode = new URLSearchParams(location.search).get("view") === "party";
  if (partyMode) document.getElementById("ov").classList.add("ov-party");
  try { const saved=localStorage.getItem("ovmetric"); if(["dps","hps","taken"].includes(saved))metric=saved; } catch(e) { /* optional storage */ }
  try { const v = parseFloat(localStorage.getItem("ovopacity")); if (v >= 0.2 && v <= 1) op = v; } catch (e) { /* optional storage */ }
  let showContribution=true, showTarget=true, showDeaths=true, showEnemyHp=false, showTtk=false, showDummy=true, showCombatPower=true, planAutoplay=true;
  let showGraph=false;
  // Skill-cooldown strip and the target's break gauge (both off by default), and when the
  // last reading arrived, so the strip counts down between polls.
  let showCooldowns=false, showGauge=false, cooldownsTop=false, cooldownsAt=0;
  const cooldownIcons=new Map();   // strip key -> icon element, kept between renders so icons never reload
  let graphHist=[], graphDur=-1;   // per-poll party-total samples for the live DPS/HPS sparkline, and the last seen fight duration
  const playerHist=new Map();      // per-player DPS samples (key -> [dps,…]) for the expanded-row trend sparkline
  let maxPlayers=8, onlyInCombat=false, autoExpand=false, nameMode="name", classColorNames=false, classSwatch=false, rankNumbers=false, highlightMe=false, showCommunityRank=false, showEvents=true, showFieldBosses=true;
  // Regional event-notification strip: next rift/Shugo/battlefield/field-boss windows
  // from the bundled schedule, for the region the player picked on the Timers page.
  let eventCatalog=null, eventTimer=null, eventRegion="", eventGroup="";
  const EVENT_LEAD_MS=15*60000;   // notify when an event is within 15 minutes
  const OBSERVED_GRACE_MS=30*60000;   // an observed field-boss kill stays listed this long past its expected return
  // Optional chime when a new event enters the strip. Off by default; a built-in
  // WebAudio chime unless the user uploaded a custom sound (served at /overlay-event-sound).
  let eventsSound=false, eventsSoundCustom=false, eventsPrimed=false, actx=null;
  const announcedEvents=new Set();
  let copyText="";   // plain-text leaderboard of the current view, for the Copy button
  const expanded=new Set();   // row keys whose per-skill breakdown is expanded (DPS view)
  let interpolate=false, interpolateMs=100, showFps=false, locked=false, userWidth=null, userHeight=null;
  let lastRenderAt=performance.now(), projecting=false, curMax=1;   // for live-ticking DPS between polls
  const shownRates=new Map();   // row key -> currently displayed (eased) rate
  const cap=s=>String(s||'').charAt(0).toUpperCase()+String(s||'').slice(1);
  // Your actor id: known from your MP record before your name, which only a zone load sends, so a
  // meter started inside a zone shows your row as "You" until then instead of "Player #id".
  let localId=null;
  const unnamedSelf=p=>localId!=null&&String(p.id)===String(localId)&&/^Player #\d+$/.test(String(p.name||''));
  const displayName=p=>{
    if(nameMode==="number")return "P"+(p.party_number||"?");
    if(nameMode==="class_number")return (cap(p.class)||"Player")+" "+(p.party_number||"?");
    return unnamedSelf(p)?"You":p.name;
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
  // Auto-contrast the overlay text to the uploaded background image. "blend" paints the
  // readout text white and uses mix-blend-mode:difference, so each glyph shows as the
  // inverse of whatever is directly behind it (per-pixel, live). "luminance" samples the
  // image's WCAG relative luminance and picks one solid light/dark colour. Both see only
  // the overlay's own layers (panel + image) — a transparent window's game scene is
  // composited by the OS, out of reach — so this pairs with a background image. When off,
  // syncColors restores the user's own text colours (set just above this call).
  const AC_VARS=['--ov-rate-text','--ov-total-text','--ov-name-color','--ov-header-color','--ov-target-color','--ov-hp-text-color','--ov-ttk-text-color','--ov-label-color','--ov-also-color','--ov-ping-color','--ov-identity-color'];
  function setAcColor(cc){const s=document.documentElement.style;AC_VARS.forEach(v=>s.setProperty(v,cc));}
  let acImg=null;
  function computeBgContrast(darkPct){
    const img=acImg||(acImg=new Image());
    img.onload=()=>{
      try{
        const n=24,c=document.createElement('canvas');c.width=c.height=n;
        const ctx=c.getContext('2d',{willReadFrequently:true});
        ctx.drawImage(img,0,0,n,n);
        const data=ctx.getImageData(0,0,n,n).data;
        const lin=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);};
        let sum=0,wt=0;
        for(let i=0;i<data.length;i+=4){const a=data[i+3]/255;sum+=(0.2126*lin(data[i])+0.7152*lin(data[i+1])+0.0722*lin(data[i+2]))*a;wt+=a;}
        const d=Math.max(0,Math.min(1,(darkPct||0)/100));
        const L=(wt?sum/wt:0)*(1-d);              // factor in the image's darken overlay
        setAcColor(L>0.179?'#0a0e16':'#f4f1ea');  // black over a light image, white over a dark one
      }catch(e){setAcColor('#f4f1ea');}           // canvas read failed (same-origin, shouldn't) -> light text
    };
    img.onerror=()=>setAcColor('#f4f1ea');
    img.src='/overlay-background?v='+Date.now();
  }
  function applyAutoContrast(mode,active,darkPct){
    const ov=document.getElementById('ov');
    const blend=active&&mode==='blend';
    ov.classList.toggle('ov-ac-blend',blend);
    if(blend)setAcColor('#ffffff');               // white base; difference inverts it to a contrasting colour
    else if(active&&mode==='luminance')computeBgContrast(darkPct);
  }
  const syncColors=()=>fetch("/api/ui").then(r=>r.json()).then(ui=>{
    if(ui.combat_colors){try{localStorage.setItem("a2-combat-colors",JSON.stringify(ui.combat_colors));}catch(e){/* optional storage */}}
    for(const key of ['rate','total']){const color=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(`--ov-${key}-text`,/^#[0-9a-f]{6}$/i.test(color||'')?color:'');}   // blank = the stylesheet's default (light on the dark bars)
    // Extra text-element colors: name and header (blank = CSS default).
    for(const key of ['name','header']){const c=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(`--ov-${key}-color`,/^#[0-9a-f]{6}$/i.test(c||'')?c:'');}
    // Target-line readout colors: target text, enemy-HP text, TTK text (blank = CSS default).
    for(const [key,cssvar] of [['target','--ov-target-color'],['hp','--ov-hp-text-color'],['ttk','--ov-ttk-text-color']]){const c=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(cssvar,/^#[0-9a-f]{6}$/i.test(c||'')?c:'');}
    // Secondary text colors: the Target/Dummy labels, the also-targets "+N" names,
    // the ping line and the identity line (blank = CSS default).
    for(const [key,cssvar] of [['label','--ov-label-color'],['also','--ov-also-color'],['ping','--ov-ping-color'],['identity','--ov-identity-color']]){const c=ui.overlay_text_colors?.[key];document.documentElement.style.setProperty(cssvar,/^#[0-9a-f]{6}$/i.test(c||'')?c:'');}
    // Fonts
    const scale=clampInt(ui.overlay_font_scale,80,160,100), weight=clampInt(ui.overlay_font_weight,400,800,600);
    const fam=typeof ui.overlay_font_family==='string'?ui.overlay_font_family:'';
    document.documentElement.style.setProperty('--ov-font-scale',scale/100);
    document.documentElement.style.setProperty('--ov-font-weight',weight);
    document.documentElement.style.setProperty('--ov-font-family',fam?`"${fam}", "Segoe UI", system-ui, sans-serif`:'');
    // Per-element font overrides (family / size / weight). A var is set only when that
    // element overrides the default; otherwise it is removed so the CSS var() fallback
    // inherits the global overlay font.
    const perFonts=ui.overlay_text_fonts&&typeof ui.overlay_text_fonts==='object'?ui.overlay_text_fonts:{};
    const rootStyle=document.documentElement.style;
    for(const key of ['rate','total','name','header','target','hp','ttk','label','also','ping','identity']){
      const f=perFonts[key]||{};
      const ff=typeof f.family==='string'&&f.family?`"${f.family}", "Segoe UI", system-ui, sans-serif`:'';
      ff?rootStyle.setProperty(`--ov-${key}-ff`,ff):rootStyle.removeProperty(`--ov-${key}-ff`);
      const fs=Number(f.scale);
      (fs>=80&&fs<=160)?rootStyle.setProperty(`--ov-${key}-fs`,fs/100):rootStyle.removeProperty(`--ov-${key}-fs`);
      const fw=Number(f.weight);
      (fw>=400&&fw<=800)?rootStyle.setProperty(`--ov-${key}-fw`,fw):rootStyle.removeProperty(`--ov-${key}-fw`);
    }
    // Halo (luminous ring) and retroreflection (moving sheen) text effects. Off by default.
    document.getElementById('ov').classList.toggle('ov-halo',ui.overlay_text_halo===true);
    rootStyle.setProperty('--ov-halo-color',/^#[0-9a-f]{6}$/i.test(ui.overlay_halo_color||'')?ui.overlay_halo_color:'#e8cf8e');
    document.getElementById('ov').classList.toggle('ov-retro',ui.overlay_text_retro===true);
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
    // Live DPS/HPS sparkline of the party total over the fight. Off by default.
    showGraph=ui.overlay_dps_graph===true;
    if(!showGraph){graphHist=[];const g=$("#ovgraph");if(g)g.hidden=true;}
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
    // Auto-contrast the text to that background image (off / blend / luminance).
    applyAutoContrast(typeof ui.overlay_text_autocontrast==='string'?ui.overlay_text_autocontrast:'off', ui.overlay_bg_set===true && bgOp>0, bgDark);
    showContribution=ui.overlay_show_contribution!==false;
    showTarget=ui.overlay_show_target!==false;
    showDeaths=ui.overlay_show_deaths!==false;
    showEnemyHp=ui.overlay_show_enemy_hp===true;
    showTtk=ui.overlay_show_ttk===true;
    showCooldowns=ui.overlay_show_cooldowns===true;
    showGauge=ui.overlay_show_break_gauge===true;
    cooldownsTop=ui.overlay_cooldowns_position==="top";
    placeCooldowns();
    showDummy=ui.meter_show_dummy_parse!==false;
    showCombatPower=ui.overlay_show_combat_power!==false;
    showCommunityRank=ui.overlay_show_community_rank===true;
    showEvents=ui.overlay_show_events!==false;   // on by default
    showFieldBosses=ui.overlay_show_field_bosses!==false;   // observed kills in the strip, on by default
    eventsSound=ui.overlay_events_sound===true;  // chime off by default (opt-in audio)
    eventsSoundCustom=ui.overlay_events_sound_set===true;
    // The region/group the Timers page picked, delivered via the server (this overlay
    // window does not share the Timers page's localStorage).
    eventRegion=typeof ui.event_region==="string"?ui.event_region:"";
    eventGroup=typeof ui.event_group==="string"?ui.event_group:"";
    setupEvents();
    setupRadar(ui.radar_enabled===true);   // the Hidden Cube radar, off by default
    nameMode=["name","class_number","number"].includes(ui.overlay_name_mode)?ui.overlay_name_mode:"name";
    interpolate=ui.overlay_dps_interpolate===true;
    interpolateMs=clampInt(ui.overlay_interpolate_ms,50,1000,50);
    showFps=ui.overlay_show_fps===true;
    planAutoplay=ui.overlay_plan_autoplay!==false;   // on by default
    $("#ovfps").hidden=!showFps||partyMode;
    setFpsLoop(showFps&&!partyMode);   // only drive a per-frame loop while the FPS readout is shown
    applyClickThrough(ui.overlay_click_through===true);   // pass clicks to the game, keeping the overlay's buttons live
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
  const copyBtn=$("#ovcopy");
  if(copyBtn)copyBtn.onclick=async()=>{
    if(!copyText)return;
    const done=ok=>{const o=copyBtn.textContent;copyBtn.textContent=ok?"Copied":"Blocked";setTimeout(()=>{if(copyBtn.isConnected)copyBtn.textContent=o;},1200);};
    try{await navigator.clipboard.writeText(copyText);done(true);}
    catch(_){try{const ta=document.createElement("textarea");ta.value=copyText;document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();done(true);}catch(e){done(false);}}
  };
  // New fight: start a fresh encounter split without alt-tabbing to the app. The
  // next combat event begins a new segment (same server action as "Split now").
  const splitBtn=$("#ovsplit");
  if(splitBtn)splitBtn.onclick=async()=>{
    const orig=splitBtn.textContent; splitBtn.disabled=true;
    try{
      const r=await fetch("/api/meter",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"split"})});
      if(!r.ok)throw Error("split failed");
      await r.json();
      graphHist=[];   // the live graph starts clean for the new fight
      splitBtn.textContent="New ✓";
      await pollMeter();
    }catch(_){splitBtn.textContent="Error";}
    finally{setTimeout(()=>{if(splitBtn.isConnected){splitBtn.textContent=orig;splitBtn.disabled=false;}},1200);}
  };
  // Start/Stop capture from the overlay — mirrors the app's button. Stop uses the
  // same action the app does; Start begins built-in (a2tools) live capture with the
  // user's remembered Players scope (shared localStorage, same origin as the app).
  const captureBtn=$("#ovcapture");
  function syncCapture(){
    if(!captureBtn)return;
    const running=!!(lastSnap&&lastSnap.running), finalizing=!!(lastSnap&&lastSnap.finalizing);
    if(captureBtn._busy)return;                       // mid-request: leave the pending label
    captureBtn.textContent=finalizing?"Stopping…":running?"Stop":"Start";
    captureBtn.classList.toggle("on",running||finalizing);
    captureBtn.disabled=finalizing;
    captureBtn.title=running?"Stop capturing combat (same as Stop in the app)":"Start capturing combat (same as Start in the app)";
  }
  // Only toggle capture when the click genuinely began on the Start/Stop button.
  // Dragging the opacity slider (or any control) can shift the frameless overlay
  // under a stationary cursor, so the browser's synthesized mouse click can land
  // on Start/Stop and stop the meter. Requiring the pointerdown to have happened
  // on the button blocks that, while keyboard activation (click detail 0) still
  // works.
  let capturePressed=false;
  if(captureBtn){
    captureBtn.addEventListener("pointerdown",()=>{capturePressed=true;});
    window.addEventListener("pointerup",()=>{setTimeout(()=>{capturePressed=false;},0);},true);
  }
  if(captureBtn)captureBtn.onclick=async(ev)=>{
    if(ev&&ev.detail!==0&&!capturePressed)return;   // a mouse click that didn't start on this button (e.g. the overlay moved under the cursor)
    capturePressed=false;
    const running=!!(lastSnap&&lastSnap.running);
    let scope="party"; try{const v=localStorage.getItem("meter-scope");if(["auto","party","self","all"].includes(v))scope=v;}catch(_){}
    // from_overlay: Stop pressed here must never close the overlay out from under
    // the cursor, regardless of the "close overlay when the meter stops" setting.
    const body=running?{action:"stop",from_overlay:true}:{action:"start",source:"a2tools",auto_port:true,scope};
    captureBtn._busy=true; captureBtn.disabled=true; captureBtn.textContent=running?"Stopping…":"Starting…";
    try{
      const r=await fetch("/api/meter",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      if(!r.ok){let m="";try{m=(await r.json()).error||"";}catch(_){}
        throw Error(m||("HTTP "+r.status));}
      await r.json();
    }catch(e){captureBtn.textContent="Error";captureBtn.title=String(e.message||e).slice(0,256);
      await new Promise(res=>setTimeout(res,1400));}
    finally{captureBtn._busy=false;captureBtn.disabled=false;await pollMeter();syncCapture();}
  };
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
  // Click-through: when on, the native window ignores the mouse so clicks reach the
  // game, except over the overlay's own controls. The native side needs to know
  // where those controls are (it can't use the web page's hover while input is
  // passing through), so we report their bounding boxes in device px — getBoundingClientRect
  // is CSS px, multiplied by devicePixelRatio to match the native client coordinates.
  function reportInteractiveRects() {
    if (!clickThrough) return;
    const dpr = window.devicePixelRatio || 1;
    const rects = [];
    document.querySelectorAll("#ov button, #ov input, #ov select, #ov a").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0)
        rects.push([r.left * dpr, r.top * dpr, r.right * dpr, r.bottom * dpr]);
    });
    nativeCall("set_interactive_rects", rects);
  }
  function applyClickThrough(on) {
    clickThrough = !!on;
    nativeCall("set_click_through", clickThrough);
    clearInterval(rectTimer); rectTimer = 0;
    if (clickThrough) {
      reportInteractiveRects();
      // Controls move as rows/targets appear; refresh the reported rects while on.
      rectTimer = setInterval(reportInteractiveRects, 400);
    }
  }
  // Coalesce native window-resize calls to one per animation frame. Both the
  // ResizeObserver and a drag-resize can ask to fit many times a frame; without
  // this, each call hops the pywebview bridge to resize the native window, and the
  // resulting relayout re-triggers the observer — a feedback loop that made
  // drag-resize jump and lag. `fitSuspended` lets a drag own the sizing outright.
  let fitQueued = false, fitSuspended = false;
  function fitNow() {
    if (fitQueued) return;
    fitQueued = true;
    requestAnimationFrame(() => {
      fitQueued = false;
      const el = $("#ov");
      nativeCall("fit", Math.ceil(el.getBoundingClientRect().width), Math.ceil(el.getBoundingClientRect().height));
    });
  }
  // The ResizeObserver path respects a drag's authority; the drag calls fitNow()
  // directly so the window tracks the pointer without the observer fighting it.
  function fit() { if (!fitSuspended) fitNow(); }
  function applyOpacity() {
    document.documentElement.style.setProperty("--ovbg", op);
    nativeCall("set_opacity", op);
  }
  function nativeInit() {
    nativeReady = true;
    document.documentElement.classList.toggle("native-windows", window.pywebview?.platform === "edgechromium");
    applyOpacity(); fit();
    // The first settings sync may have run before the bridge was ready, so re-push
    // the click-through state (and the control rects) now that native calls land.
    nativeCall("set_click_through", clickThrough);
    if (clickThrough) reportInteractiveRects();
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
  function allPlans() {
    try { return JSON.parse(localStorage.getItem("a2plans") || "{}"); } catch (e) { return {}; }
  }
  function latestPlan() {
    const all = allPlans();
    const ids = Object.keys(all).sort((a, b) => (all[b].meta?.updated || 0) - (all[a].meta?.updated || 0));
    return ids.length ? all[ids[0]] : null;
  }
  // The most-recently-updated saved plan bound to this enemy's NPC code, or null. This is
  // the client-side library index the overlay uses to auto-play the right plan for the
  // fight you are in.
  function planForNpc(code) {
    const npc = Number(code);
    if (!npc) return null;
    const all = allPlans();
    const ids = Object.keys(all).sort((a, b) => (all[b].meta?.updated || 0) - (all[a].meta?.updated || 0));
    for (const id of ids) if (Number(all[id]?.encounter?.npc_id) === npc) return all[id];
    return null;
  }
  // Pick the plan to show and the time to show it at. When auto-play is on and the live
  // meter is in a fight whose current target has a bound plan, play THAT plan synced to
  // the encounter's elapsed seconds (so positions match the real pull); otherwise fall
  // back to the latest saved plan on a free-running, looping clock.
  function planView() {
    if (planAutoplay && lastSnap && lastSnap.running) {
      const snap = lastSnap.snapshot || {}, tgt = snap.current_target;
      const bound = tgt && !tgt.is_player ? planForNpc(tgt.mob_code) : null;
      if (bound) {
        const dur = Math.max(1, Number(bound.duration) || 1);
        const elapsed = Math.max(0, Number(snap.duration) || 0);
        return { plan: bound, time: Math.min(elapsed, dur), live: true, dur };
      }
    }
    const p = latestPlan();
    const dur = Math.max(1, Number(p?.duration) || 1);
    return { plan: p, time: t % dur, live: false, dur };
  }
  function renderParty() {
    // The separate Party-DPS overlay: raid-wide aggregates, not per-player rows.
    const s = lastSnap || {}, snap = s.snapshot || {}, players = snap.players || [];
    for(const id of ["#ovmetrics","#ovping","#ovidentity","#ovtarget","#ovhpbar","#ovttkbar","#ovgauge","#ovcontribution","#ovdummy","#ovconnection","#ovcooldowns"])$(id).hidden=true;
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
    recordGraph(s, snap, players);
  }
  // Live DPS/HPS graph: accumulate one real reading of the party total per poll
  // for the current fight and draw it as a sparkline. Each point is packet-sourced
  // (the summed live rate at that moment) — nothing is invented. The history clears
  // when a new fight starts (the fight clock resets) and is capped so memory is bounded.
  function recordGraph(s, snap, players){
    const g=$("#ovgraph"); if(!g)return;
    if(!showGraph){g.hidden=true;graphHist=[];playerHist.clear();return;}
    const running=!!(s&&s.running), paused=snap.paused===true, over=snap.battle_over===true;
    const duration=Number(snap.duration)||0;
    if(duration+0.001<graphDur){graphHist=[];playerHist.clear();}   // the fight clock went backwards → a new fight began
    graphDur=duration;
    if(running&&!paused&&!over){
      graphHist.push({
        d: players.reduce((n,p)=>n+(Number(p.dps)||0),0),
        h: players.reduce((n,p)=>n+(Number(p.hps)||0),0),
        k: players.reduce((n,p)=>n+(Number(p.dtps)||0),0),
      });
      if(graphHist.length>300) graphHist.shift();
      // Per-player DPS trend, for the sparkline shown when a row is expanded.
      for(const p of players){
        const k=String(p.key||p.id); let arr=playerHist.get(k);
        if(!arr){arr=[];playerHist.set(k,arr);}
        arr.push(Number(p.dps)||0);
        if(arr.length>300) arr.shift();
      }
    }
    drawGraph();
  }
  // A compact DPS trend sparkline for one player's expanded row (shown only when
  // the DPS graph is enabled). Each point is a real per-poll reading.
  function sparkLine(series, color){
    if(!Array.isArray(series)||series.length<2)return "";
    const c=/^#[0-9a-f]{6}$/i.test(color||'')?color:'#e8cf8e';
    const mx=Math.max(...series,1), n=series.length, W=100, H=16;
    const pts=series.map((v,i)=>`${(i/(n-1)*W).toFixed(1)},${(H-(v/mx)*H).toFixed(1)}`).join(" ");
    // Tinted to the player's class colour so the trend matches their bar.
    return `<div class="ovpspark"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><polygon class="ovparea" points="0,${H} ${pts} ${W},${H}" style="fill:${c}"/><polyline points="${pts}" style="stroke:${c}"/></svg></div>`;
  }
  function drawGraph(){
    const g=$("#ovgraph"); if(!g)return;
    const series=graphHist.map(p=>metric==="hps"?p.h:metric==="taken"?p.k:p.d);
    if(!showGraph||series.length<2){g.hidden=true;return;}
    const mx=Math.max(...series,1), n=series.length, W=100, H=30;
    const pts=series.map((v,i)=>`${(i/(n-1)*W).toFixed(2)},${(H-(v/mx)*H).toFixed(2)}`);
    const label=metric==="hps"?"HPS":metric==="taken"?"Taken":"DPS";
    g.hidden=false;
    g.innerHTML=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><polygon class="ovgarea" points="0,${H} ${pts.join(" ")} ${W},${H}"/><polyline class="ovgline" points="${pts.join(" ")}"/></svg><span class="ovglabel">${label} · now ${kfmt(series[series.length-1])} · peak ${kfmt(mx)}</span>`;
  }
  // The class icon badge before a name: the bundled class art (game-assets.js), tinted by the
  // class colour ring. Purely visual; nothing is shown when no art is bundled for the class.
  // The overlay's own class palette (the cool look): a bar/icon tint for all eight
  // classes. A class colour the user chose in Settings → Combat colours (or a palette
  // they applied there) wins, and "Use class colors" off still gives every row the
  // neutral gold, exactly as the shared A2CombatReview.color() decides.
  const OVERLAY_CLASS_COLORS={sorcerer:"#3a86c8",assassin:"#4caf6e",templar:"#c9772b",ranger:"#b9962a",chanter:"#b84f9e",gladiator:"#c8474f",spiritmaster:"#7a63d8",cleric:"#3fb4b0"};
  function barColor(cls){
    const key=String(cls||'').toLowerCase();
    let pref={}; try{pref=JSON.parse(localStorage.getItem("a2-combat-colors"))||{};}catch(_){pref={};}
    const own=(pref.colors||{})[key];
    if(pref.enabled===false||/^#[0-9a-f]{6}$/i.test(own||'')||!OVERLAY_CLASS_COLORS[key]) return A2CombatReview.color(key);
    return OVERLAY_CLASS_COLORS[key];
  }
  function classIcon(cls){
    const key=String(cls||'').toLowerCase(); if(!key) return '';
    const files=window.A2BundledAssets&&window.A2BundledAssets.files, base=window.A2BundledAssets&&window.A2BundledAssets.base;
    const file=files&&files[`https://metabot.gg/web/aion2/classes/${key}.webp`]; if(!file||!base) return '';
    return `<i class="ovcicon" style="background-image:url(${esc(base+file)});--bar:${barColor(key)}" title="${esc(key)}"></i>`;
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
    localId = snap.identity_status && snap.identity_status.local_id != null ? snap.identity_status.local_id : null;
    const meName = highlightMe && snap.identity_status && snap.identity_status.local_name ? String(snap.identity_status.local_name).toLocaleLowerCase() : "";
    const isMe = p => meName && String(p.name||'').toLocaleLowerCase() === meName;
    const ranked = [...visible].sort((a,b)=>rate(b)-rate(a)||amount(b)-amount(a));
    const rows = ranked.slice(0, shownCount).map((p, i) => {
      const key=String(p.key||p.id);
      // Per-skill damage breakdown (DPS view only — the snapshot's skills list is
      // damage). Click a row to expand it; the open rows are remembered in `expanded`.
      const hasSkills=metric==="dps"&&Array.isArray(p.skills)&&p.skills.length;
      // When the DPS graph is on, an expanded row also shows that player's DPS trend.
      const spark=(hasSkills&&showGraph&&expanded.has(key))?sparkLine(playerHist.get(key),barColor(p.class)):"";
      const skills=hasSkills?`<div class="ovskills"${expanded.has(key)?'':' hidden'}>${spark}${p.skills.slice(0,6).map(sk=>`<div class="ovskrow"><span class="ovskname">${esc(sk.skill||sk.skill_id)}</span><span class="ovskval">${kfmt(sk.damage)} · ${Math.round((sk.share||0)*100)}%</span></div>`).join("")}</div>`:"";
      return `<div class="ovrow${showDeaths&&p.dead?' ovrow-dead':''}${isMe(p)?' ovrow-me':''}${hasSkills?' ovrow-x':''}"${hasSkills?` data-exk="${esc(key)}"`:''}><span class="ovname" title="${esc(p.name)} · Actor ${esc(p.key || p.id)}${p.includes_pets?" · Includes linked pets":""}">${rankNumbers?`<span class="ovrank${i<3?' ovrank-'+(i+1):''}">${i+1}.</span>`:''}${classIcon(p.class)}${classSwatch?`<i class="ovclass" style="background:${barColor(p.class)}" title="${esc(p.class||'')}"></i>`:''}<span class="ovnametext"${classColorNames?` style="color:color-mix(in srgb, ${barColor(p.class)} 55%, #ffffff)"`:''}>${esc(displayName(p))}</span>${nameMode==="name"&&duplicate(p)?`<small class="ovactor">#${esc(p.id)}</small>`:''}${showDeaths&&p.dead?'<small class="ovdead">DEAD</small>':''}${showCommunityRank&&p.community_rank&&p.community_rank.text?`<small class="ovcrank" title="Community standing for your last uploaded fight">${esc(p.community_rank.text)}</small>`:''}</span>
        <div class="ovbar" title="${esc(label)}: ${kfmt(rate(p))} · Total: ${kfmt(amount(p))}"><i data-k="${esc(key)}" style="width:${100 * rate(p) / mx}%;--bar:${barColor(p.class)}"></i><span><span class="ovrate" data-k="${esc(key)}" data-target="${rate(p)}" data-amt="${amount(p)}">${kfmt(rate(p))}</span>/s <span class="sub">${kfmt(amount(p))} · ${Math.round(100 * amount(p) / (total||1))}%</span></span></div>${skills}</div>`;
    }).join("");
    const duration=metric==="dps"?snap.duration:snap.recorded_duration;
    // Plain-text leaderboard of the current view, ready to paste into chat/Discord.
    copyText=`${label} · ${snap.boss||'combat'} · ${(Number(duration)||0).toFixed(0)}s\n`+
      ranked.map((p,i)=>`${i+1}. ${displayName(p)}  ${kfmt(rate(p))}/s  (${Math.round(100*amount(p)/(total||1))}%)`).join("\n")+
      `\n— Aion 2 Calc`;
    $("#ovstatus").textContent = `Latest combat · ${snap.paused && metric==="dps" ? "Paused DPS · " : ""}${snap.boss || (s.running ? "recording" : "idle")} · ${(Number(duration) || 0).toFixed(0)}s · ${kfmt(players.reduce((n,p)=>n+rate(p),0))} ${label}`;
    // During a big fight the decoder can fall behind the packet backlog; show it is
    // catching up (and how deep the queue is) so the live view does not look frozen.
    if (snap.decode_backlog && snap.decode_backlog.catching_up) $("#ovstatus").textContent += ` · ⏳ catching up (${snap.decode_backlog.queue_depth})`;
    const identity=snap.identity_status, missing=players.length>0&&identity&&(!identity.self_identified||identity.unnamed_actors>0), repeated=visible.some(duplicate);
    // A player whose combat actor id changed mid-fight (death/revive, instance swap) was
    // correlated into one row by name, class and non-overlapping timing — flagged inferred.
    const inferred=visible.some(p=>p.inferred_identity);
    // A zone load (tele/port/revive/instance) reassigns your actor id; show the
    // re-acquired identity so a brief "not received" gap is visibly recovered.
    const selfName=identity&&identity.local_name;
    const cp=showCombatPower&&identity&&identity.local_combat_power;
    // Your live standing on the current metric, so you know where you place at a glance.
    const meIdx=selfName?ranked.findIndex(p=>String(p.name||'').toLocaleLowerCase()===String(selfName).toLocaleLowerCase()):-1;
    const rankStr=(meIdx>=0&&ranked.length>1)?` · #${meIdx+1} of ${ranked.length}`:'';
    const selfLine=selfName?(/^Player #\d+$/.test(String(selfName))?`You${rankStr} · your name comes with the next zone load`:`You: ${selfName}${rankStr}${cp?` · CP ${kfmt(identity.local_combat_power)}`:''}`):'';
    $("#ovidentity").hidden=!missing&&!repeated&&!inferred&&!selfName;
    $("#ovidentity").classList.toggle("ok",!missing&&!repeated&&!!selfName);
    $("#ovidentity").textContent=[missing?`${identity.self_identified?"Self identified":"Self identity not received — teleport or change instances to refresh it"} · ${identity.unnamed_actors} unnamed actors · ${identity.linked_pets} linked pets. Grouping needs recorded owner links.`:selfLine,repeated?'Matching names have separate combat actor IDs; names alone do not establish shared identity or ownership.':'',inferred?'Combined a player’s re-registered actor IDs (matched by name, class and timing).':''].filter(Boolean).join(' ');
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
      // Enemy HP is shown as a percentage, not the raw current/max numbers: the
      // game's internal HP value is on a much larger scale than damage (verified
      // ~16-19x), so printing it next to your damage invites a comparison that can
      // never line up. The exact percentage (and the bar below) are trustworthy;
      // the raw internal values stay available on hover, clearly labelled.
      // Hover shows the effective HP in damage units — the total recorded damage
      // dealt to this target so far (packet-sourced, exact, and on the same scale
      // as your damage) — alongside the game's raw internal HP for reference.
      // When the community HP database has a confident effective HP for this mob, show
      // its remaining HP in damage units (accurate packet % x damage-unit maximum),
      // calibrated from how many kills the community has pooled for this game build.
      const hpTip=target.effective_max_hp!=null
        ? `HP ≈ ${kfmt(target.effective_current_hp)} / ${kfmt(target.effective_max_hp)} in damage units`
          +` — calibrated from ${target.effective_hp_samples||0} community kill${target.effective_hp_samples===1?'':'s'} on this game build.`
          +` Effective HP dealt so far ≈ ${kfmt(target.damage)}.`
        : `Effective HP so far ≈ ${kfmt(target.damage)} (total recorded damage dealt to it).`
          +(target.current_hp!=null?` Game internal HP ${kfmt(target.current_hp)}${target.max_hp?' / '+kfmt(target.max_hp):''} is on a larger, different scale than damage, so it is shown here as a percentage.`:'');
      const hp=showEnemyHp&&target.hp_pct!=null
        ? ` <span class="ovhp" title="${esc(hpTip)}">${Math.round(target.hp_pct*100)}%</span>` : '';
      const ttk=showTtk&&target.ttk!=null&&isFinite(target.ttk)
        ? ` <span class="ovttk">TTK ${fmtTtk(target.ttk)}</span>` : '';
      const gaugePct=showGauge&&target.break_gauge?Math.max(0,Math.min(100,Number(target.break_gauge.pct)||0)):null;
      const gaugeText=gaugePct==null?'':gaugePct<=5
        ? ` <span class="ovbreak broken" title="The break gauge is empty: the enemy is broken (staggered) and takes more damage until it refills">BROKEN</span>`
        : ` <span class="ovbreak" title="Break gauge left before this enemy breaks (staggers); skills that deal Stagger Gauge Damage drain it">Break ${Math.round(gaugePct)}%</span>`;
      // When several enemies are being struck in the same instant (AOE/cleave), the
      // single "most-hit" target is one of several — name the others compactly.
      const alsoNames=(target.also_targets||[]);
      const alsoTip=`Also being hit right now: ${esc(alsoNames.join(', '))}`;
      const also=alsoNames.length?`<span class="ovalso ovalsocount" title="${alsoTip}">+${alsoNames.length}</span>`
        +`<span class="ovalso ovalsonames" title="${alsoTip}">(${esc(alsoNames.map(n=>String(n)).join(', '))})</span>`:'';
      // Small boss/NPC portrait from the bundled/community asset map (self-removes if it fails to load).
      const portraitUrl=target.mob_code!=null&&window.A2BundledAssets&&window.A2BundledAssets.npcs&&window.A2BundledAssets.npcs[String(target.mob_code)];
      const portrait=portraitUrl?`<img class="ovtportrait" width="18" height="18" referrerpolicy="no-referrer" src="${esc(window.A2AssetHealth?A2AssetHealth.source(portraitUrl):portraitUrl)}" alt="" onerror="this.remove()"> `:'';
      // Same content as always; the name and the secondary readouts are wrapped so the
      // stylesheet can lay the panel out as a boss card (name + HP on top, TTK, damage
      // and contributors beneath). Hidden readouts stay hidden exactly as before.
      $("#ovtarget").innerHTML=`<span class="ovtlabel">Target</span> ${portrait}<span class="ovtwho"><span class="ovtname">${esc(target.name)}</span>${also}</span>${hp}<span class="ovtline">${ttk}${gaugeText} <span class="sub">${kfmt(target.damage)}</span>${top?` — ${top}`:''}</span>`;
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
    // Drawn break gauge: what is left before the target breaks (bosses and elites carry one).
    const gauge=showT&&showGauge&&target&&target.break_gauge;
    $("#ovgauge").hidden=!gauge;
    if(gauge){
      const pct=Math.max(0,Math.min(100,Number(gauge.pct)||0));
      $("#ovgauge").classList.toggle("broken",pct<=5);
      $("#ovgauge").firstElementChild.style.width=pct+"%";
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
    recordGraph(s, snap, players);
    renderCooldowns();
    // Show meter only during combat: collapse to the header when idle (the window
    // then shrinks via fit), so the overlay is unobtrusive between pulls. A brief
    // damage pause while an engaged boss is still alive is a mechanic, not the end of
    // the fight, so keep the meter open through it — never collapse mid-boss.
    if(onlyInCombat && (!s.running || over || (snap.paused && snap.boss_alive!==true))){
      $("#ovcontent").innerHTML='';
      for(const id of ["#ovmetrics","#ovping","#ovtarget","#ovhpbar","#ovttkbar","#ovgauge","#ovcontribution","#ovdummy","#ovidentity","#ovgraph","#ovcooldowns"])$(id).hidden=true;
      $("#ovstatus").textContent=s.running?'Idle · waiting for combat':'Idle';
      $("#ovstatus").title=$("#ovstatus").textContent;
    }
  }
  // Skill-cooldown strip: your skills on cooldown, soonest ready first, each counting down
  // between polls from the time left the meter sent (the cooldown the game sent with the cast,
  // so cooldown reduction is included). A skill lights up as it comes off cooldown, and an open
  // chain-skill window shows first. Only skills used since Start are known.
  const fmtCooldown=ms=>ms>=60000?Math.ceil(ms/60000)+'m':ms>=10000?String(Math.ceil(ms/1000)):(ms/1000).toFixed(1);
  function placeCooldowns(){   // above the player rows, or below the graph (the default)
    const strip=$("#ovcooldowns"), rows=$("#ovcontent"), graph=$("#ovgraph");
    if(!strip||!rows||!graph)return;
    if(cooldownsTop){if(strip.nextElementSibling!==rows)rows.before(strip);}
    else if(graph.nextElementSibling!==strip)graph.after(strip);
  }
  function cooldownIcon(key,family,name){
    let node=cooldownIcons.get(key);
    if(!node){
      node=document.createElement("span");
      const initials=String(name||"").split(/\s+/).filter(Boolean).map(w=>w[0]).join("").slice(0,2);
      const n=Number(family), src=Number.isSafeInteger(n)&&n>0?"https://metabot.gg/web/aion2/skills/"+n+".webp":"";
      node.innerHTML=`<em>${esc(initials)}</em>${src?`<img src="${esc(window.A2AssetHealth?A2AssetHealth.source(src):src)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">`:""}<i></i><b></b>`;
      cooldownIcons.set(key,node);
    }
    return node;
  }
  function renderCooldowns(){
    const strip=$("#ovcooldowns");
    if(!strip)return;
    const s=lastSnap||{}, snap=s.snapshot||{};
    const rows=Array.isArray(snap.cooldowns)?snap.cooldowns:[], chains=Array.isArray(snap.chain_windows)?snap.chain_windows:[];
    const idle=onlyInCombat&&(!s.running||snap.battle_over===true||(snap.paused&&snap.boss_alive!==true));
    const show=showCooldowns&&!partyMode&&tab==="meter"&&!!s.running&&!idle&&(rows.length>0||chains.length>0);
    strip.hidden=!show;
    if(!show){strip.replaceChildren();cooldownIcons.clear();return;}
    const elapsed=Date.now()-cooldownsAt, nodes=[], keys=new Set();
    for(const chain of chains){
      const key="chain:"+chain.family, node=cooldownIcon(key,chain.family,chain.name);
      node.className="ovcd ovcd-chain";node.title=`${chain.name}: chain window open`;
      node.lastElementChild.textContent="";
      keys.add(key);nodes.push(node);
    }
    for(const row of rows){
      const key="cd:"+row.family, left=(Number(row.remaining_ms)||0)-elapsed, total=Math.max(1,Number(row.cooldown_ms)||1);
      if(left<=-3000||keys.has(key))continue;   // lit for 3 s after it comes off cooldown, as the meter does
      const ready=left<=0, node=cooldownIcon(key,row.family,row.name);
      node.className="ovcd"+(ready?" ovcd-ready":"");
      node.style.setProperty("--cd",(ready?0:360*Math.min(1,left/total)).toFixed(1)+"deg");
      node.lastElementChild.textContent=ready?"":fmtCooldown(left);
      node.title=`${row.name}: ${ready?"ready":(left/1000).toFixed(left<10000?1:0)+" s left"} · cooldown ${(total/1000).toFixed(1)} s`;
      keys.add(key);nodes.push(node);
    }
    for(const key of [...cooldownIcons.keys()])if(!keys.has(key))cooldownIcons.delete(key);
    if(nodes.length!==strip.children.length||nodes.some((node,i)=>strip.children[i]!==node))strip.replaceChildren(...nodes);
  }
  setInterval(()=>{ if(showCooldowns&&!locked&&tab==="meter")renderCooldowns(); },250);
  function renderPlan() {
    $("#ovmetrics").hidden=true;$("#ovping").hidden=true;$("#ovidentity").hidden=true;
    $("#ovtarget").hidden=true;$("#ovhpbar").hidden=true;$("#ovttkbar").hidden=true;$("#ovcontribution").hidden=true;$("#ovdummy").hidden=true;$("#ovfps").hidden=true;
    $("#ovgraph").hidden=true;$("#ovgauge").hidden=true;$("#ovcooldowns").hidden=true;
    $("#ovconnection").hidden=true;
    const view = planView(), p = view.plan;
    if (!p) {
      $("#ovstatus").textContent = "";
      $("#ovcontent").innerHTML = '<div class="muted">No saved plan yet.</div>';
      return;
    }
    const dur = view.dur, now = view.time;
    const svg = ['<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet"><rect x="1" y="1" width="98" height="98" rx="2" fill="none" stroke="#8886" stroke-width="0.6"/>'];
    for (const tk of p.tokens || []) {
      const pos = tokenPos(tk, now);
      if (!pos) continue;
      const col = esc(tk.color || "#39c2e0"), x = Number(pos.x) * 100, y = Number(pos.y) * 100;
      if (tk.kind === "aoe") svg.push(`<circle cx="${x}" cy="${y}" r="${(Number(tk.radius) || 0.14) * 100}" fill="${col}" fill-opacity="0.25" stroke="${col}" stroke-width="0.5"/>`);
      else svg.push(`<circle cx="${x}" cy="${y}" r="${tk.kind === "enemy" ? 3.4 : 2.6}" fill="${col}" stroke="#0008" stroke-width="0.5"/>`);
    }
    svg.push("</svg>");
    // "live" marks the plan as auto-synced to the real pull (vs the looping preview).
    $("#ovstatus").textContent = `${view.live ? "▶ live · " : ""}${p.meta?.name || "plan"} · ${now.toFixed(0)}/${dur.toFixed(0)}s`;
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
  // Click a player row to toggle its per-skill breakdown (delegated, since rows
  // are rebuilt each poll; the open set is re-applied on render).
  const ovc=$("#ovcontent");
  if(ovc)ovc.addEventListener("click",e=>{
    const row=e.target.closest(".ovrow[data-exk]");
    if(!row||!ovc.contains(row))return;
    const k=row.getAttribute("data-exk"),panel=row.querySelector(".ovskills");
    if(!panel)return;
    if(expanded.has(k)){expanded.delete(k);panel.hidden=true;}else{expanded.add(k);panel.hidden=false;}
  });
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
      lastSnap=next;meterUnavailable=false;refreshError="";lastSuccess=cooldownsAt=Date.now();
    } catch (e) {
      meterUnavailable=true;
      refreshError=e.name==='AbortError'?'Meter refresh timed out after 4s':String(e.message||e).slice(0,512);
    }
    finally { clearTimeout(timeout); polling = false; }
    if (tab === "meter") renderMeter();
    syncCapture();
  }
  $("#ovretry").onclick=()=>pollMeter();
  // Poll on the meter tab, and on the plan tab when auto-play is on, so the plan can
  // sync to the live pull.
  setInterval(() => { if (tab === "meter" || (tab === "plan" && planAutoplay)) pollMeter(); }, 500);
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
      fitSuspended=true;   // the drag owns sizing; the ResizeObserver must not fight it
      const move=ev=>{
        if(horiz){userWidth=Math.max(260,Math.min(800,Math.round(startW+(ev.clientX-startX))));
          document.documentElement.style.setProperty('--ov-width',userWidth+'px');}
        if(vert){userHeight=Math.max(70,Math.min(800,Math.round(startH+(ev.clientY-startY))));
          document.documentElement.style.setProperty('--ov-height',userHeight+'px');}
        fitNow();
      };
      const up=()=>{
        document.removeEventListener("pointermove",move); document.removeEventListener("pointerup",up);
        fitSuspended=false; fitNow();   // resume observer-driven fit and settle the final size
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

  // Unlock WebAudio on the first interaction so the event chime can sound (browser
  // autoplay policy blocks audio until a user gesture).
  document.addEventListener("pointerdown",()=>{
    try{const Ctx=window.AudioContext||window.webkitAudioContext;if(Ctx){actx=actx||new Ctx();if(actx.state==="suspended")actx.resume().catch(()=>{});}}catch(_){}
  },{once:true});

  // Screenshot & lock: freeze the display and keep the overlay pinned (even when
  // the game loses focus) so it can be captured; a second click resumes.
  const lockBtn=$("#ovlock");
  function toggleLock(){
    locked=!locked;
    if(lockBtn){lockBtn.textContent=locked?"Unlock":"Lock";lockBtn.classList.toggle("on",locked);}
    document.getElementById("ov").classList.toggle("ov-locked",locked);
    nativeCall("set_locked",locked);
    if(!locked)pollMeter();                 // resume the frozen meter poll on unlock
  }
  if(lockBtn)lockBtn.onclick=toggleLock;
  // A global "screenshot lock" hotkey fires in the app process, which can't reach this
  // separate overlay window — so the app bumps a counter and we watch it on a light poll
  // that keeps running even while locked (the meter poll stops when locked, so it can't
  // carry the unlock). First reading seeds the baseline so startup never auto-locks.
  let lastLockSeq=null;
  async function pollCommands(){
    try{
      const r=await fetch("/api/overlay/commands",{cache:"no-store"});
      if(r.ok){const c=await r.json(),seq=Number(c.lock_seq)||0;
        if(lastLockSeq===null)lastLockSeq=seq;
        else if(seq>lastLockSeq){lastLockSeq=seq;toggleLock();}}
    }catch(_){/* best-effort: a missed command poll just delays the next hotkey action */}
  }
  pollCommands(); setInterval(pollCommands,1000);

  // Regional event notifications (on by default): a compact strip of the next
  // rift / Shugo / battlefield / field-boss windows from the bundled schedule, for
  // the region the player picked on the Timers page (same-origin localStorage). A
  // scheduled window is a community forecast, never live status — labelled as such.
  // The built-in chime (a short two-note rise) or, when the user uploaded one, their
  // own sound. Best-effort: browser autoplay policy may mute it until a click, and
  // any failure is swallowed so a missing/!blocked sound never disrupts the overlay.
  function playEventSound(){
    if(eventsSoundCustom){
      try{ const a=new Audio("/overlay-event-sound?v="+Date.now()); a.volume=0.6; a.play().catch(()=>{}); }catch(_){}
      return;
    }
    try{
      const Ctx=window.AudioContext||window.webkitAudioContext; if(!Ctx)return;
      actx=actx||new Ctx(); if(actx.state==="suspended")actx.resume().catch(()=>{});
      const t0=actx.currentTime;
      [[784,0],[1046.5,0.13]].forEach(([f,dt])=>{   // G5 → C6, ~0.5s total
        const o=actx.createOscillator(), g=actx.createGain();
        o.type="sine"; o.frequency.value=f;
        g.gain.setValueAtTime(0.0001,t0+dt);
        g.gain.exponentialRampToValueAtTime(0.22,t0+dt+0.02);
        g.gain.exponentialRampToValueAtTime(0.0001,t0+dt+0.33);
        o.connect(g); g.connect(actx.destination); o.start(t0+dt); o.stop(t0+dt+0.36);
      });
    }catch(_){}
  }
  // Field-boss kills the live meter observed on the player's own server, for their faction's
  // zones and the Abyss (snapshot.field_bosses, read by the app from the share server's kill
  // feed: uploaded recordings and corroborated auto-reports; the Discord bot's manual timers
  // never reach it). A boss whose expected return is near or just passed joins the strip.
  function observedBossEvents(now){
    const doc=lastSnap&&lastSnap.snapshot&&lastSnap.snapshot.field_bosses;
    if(!showFieldBosses||!doc||!doc.faction||!Array.isArray(doc.kills))return [];
    const out=[];
    for(const k of doc.kills){
      if(!Number.isFinite(k.expected_at))continue;
      const at=k.expected_at*1000, startsInMs=at-now;
      if(startsInMs>EVENT_LEAD_MS||startsInMs<-OBSERVED_GRACE_MS)continue;
      const ago=A2EventSchedule.shortCountdown(Math.max(0,now-k.killed_at*1000));
      const who=Number(k.reports)===1?'1 uploader':`${Number(k.reports)||0} uploaders`;
      out.push({id:'fb:'+k.boss+':'+Math.round(k.killed_at),name:k.boss,zone:k.zone||'',observed:true,
        active:startsInMs<=0,startsInMs:startsInMs,endsAt:at+OBSERVED_GRACE_MS,
        tip:`${k.boss} — observed kill ${ago} ago by ${who} on ${doc.server_name||('server '+doc.server)} (live meter recordings, not Discord timers)${k.respawn_basis==='reference'?`; community respawn reference ${k.respawn_minutes} min, unverified`:k.respawn_basis==='measured'?'; respawn measured from repeated kills':''}${k.zone?' · '+k.zone:''}`});
    }
    return out;
  }
  function renderEvents(){
    const box=$("#ovevents");
    if(!box)return;
    if(!showEvents||!window.A2EventSchedule){box.hidden=true;eventsPrimed=false;announcedEvents.clear();return;}
    const saved=A2EventSchedule.savedRegion();
    const region=eventRegion||saved.region, group=eventGroup||saved.group;   // server-provided first, localStorage fallback
    const now=Date.now();
    const observed=observedBossEvents(now);
    if(!region&&!observed.length){box.hidden=true;eventsPrimed=false;announcedEvents.clear();return;}   // no region chosen on the Timers page yet, nothing observed
    const forecast=(region&&eventCatalog)?A2EventSchedule.upcoming(eventCatalog,region,group,now)
      .filter(e=>e.active||(e.startsInMs!=null&&e.startsInMs<=EVENT_LEAD_MS)):[];
    const list=observed.concat(forecast)
      .sort((a,b)=>(a.active?-1:a.startsInMs)-(b.active?-1:b.startsInMs))
      .slice(0,3);
    // Chime once when a new event (or a new phase of one) enters the strip. The first
    // populate primes silently so we don't blast on launch for an already-open window.
    const keys=new Set(list.map(e=>e.id+":"+(e.active?"active":"soon")));
    if(!eventsPrimed){announcedEvents.clear();keys.forEach(k=>announcedEvents.add(k));eventsPrimed=true;}
    else{
      let fresh=false;
      keys.forEach(k=>{if(!announcedEvents.has(k)){fresh=true;announcedEvents.add(k);}});
      [...announcedEvents].forEach(k=>{if(!keys.has(k))announcedEvents.delete(k);});   // let a recurrence re-chime
      if(fresh&&eventsSound)playEventSound();
    }
    if(!list.length){box.hidden=true;return;}
    box.hidden=false;
    box.innerHTML=`<span class="ovelabel">Events</span> `+list.map(e=>{
      if(e.observed){
        const when=e.active?'now':`back in ${A2EventSchedule.shortCountdown(e.startsInMs)}`;
        return `<span class="ovevent ovobserved${e.active?' on':''}" title="${esc(e.tip)}">${esc(e.name)} <b>${when}</b></span>`;
      }
      const when=e.active
        ? (e.entryOpen&&e.endsAt?`entry ${A2EventSchedule.shortCountdown(e.endsAt-now)}`:(e.endsAt?`ends ${A2EventSchedule.shortCountdown(e.endsAt-now)}`:'now'))
        : `in ${A2EventSchedule.shortCountdown(e.startsInMs)}`;
      const tip=`${e.name} — community forecast (${e.zone}), not live status${e.disputed?'; conflicting community reports, confirm in game':''}`;
      return `<span class="ovevent${e.active?' on':''}" title="${esc(tip)}">${esc(e.name)} <b>${when}</b></span>`;
    }).join(" · ");
  }
  function setupEvents(){
    if(!showEvents){ if(eventTimer){clearInterval(eventTimer);eventTimer=null;} const b=$("#ovevents"); if(b)b.hidden=true; return; }
    if(!eventCatalog&&window.A2EventSchedule){
      fetch("/static/event-schedules.json",{cache:"no-store"})
        .then(r=>r.ok?r.json():null)
        .then(d=>{ if(d&&d.version===1){eventCatalog=d;renderEvents();} })
        .catch(()=>{});   // the strip is best-effort; stay silent if the schedule can't load
    }
    if(!eventTimer)eventTimer=setInterval(renderEvents,1000);
    renderEvents();
  }

  // The Hidden Cube radar (off by default): which side a cube's jingle comes from and how loud it
  // is, from the game's sound, which the app listens to in memory (radar.py). It has its own poll so
  // it keeps up while exploring with the meter collapsed between fights.
  let radarOn=false, radarTimer=null, radarBusy=false;
  const RADAR_NEAR=[[0.8,"right here"],[0.5,"close"],[0.25,"nearby"],[0,"far"]];
  function setupRadar(on){
    radarOn=on&&!partyMode;
    if(radarOn&&!radarTimer){radarTimer=setInterval(pollRadar,300);pollRadar();}
    else if(!radarOn&&radarTimer){clearInterval(radarTimer);radarTimer=null;}
    const el=$("#ovradar");
    if(el&&!radarOn&&!el.hidden){el.hidden=true;fit();}
  }
  async function pollRadar(){
    if(radarBusy||locked)return;
    radarBusy=true;
    try{const r=await fetch("/api/radar");if(r.ok)renderRadar(await r.json());}
    catch(e){/* best-effort: the next poll retries */}
    finally{radarBusy=false;}
  }
  function radarText(r){
    if(r.learning){
      const what=r.learning.kind==="cube"?"the cube's sound":"the background";
      return r.learning.phase==="countdown"?`Learning ${what} in ${Math.ceil(r.learning.seconds)} s: switch to the game`:`Listening to ${what}… ${Math.ceil(r.learning.seconds)} s`;
    }
    if(r.last_learn&&r.last_learn_s!=null&&r.last_learn_s<6)return r.last_learn.message;   // a learn just finished (Ctrl+1 / Ctrl+2)
    if(!r.supported)return "Hidden Cube radar: Windows only";
    if(r.error)return "Hidden Cube radar: "+r.error;
    if(!r.ready)return "Hidden Cube radar: teach it the cube's sound in Settings → Overlay";
    if(!r.heard)return "Listening for a Hidden Cube…"+(r.since!=null&&r.since<60?` last heard ${Math.round(r.since)} s ago`:"");
    const near=(RADAR_NEAR.find(([p])=>(r.proximity||0)>=p)||RADAR_NEAR[3])[1];
    const trend=r.trend==="louder"?" · getting closer":r.trend==="quieter"?" · moving away":"";
    return `Hidden Cube ${r.side==="middle"?"ahead or behind":"to your "+r.side} · ${near}${trend}`;
  }
  function renderRadar(r){
    const el=$("#ovradar");
    if(!el)return;
    const show=radarOn&&!!r;
    if(el.hidden===show){el.hidden=!show;fit();}
    if(!show)return;
    if(!el.firstElementChild){   // built once; each poll moves the blip and changes the text only when it differs
      el.innerHTML=`<svg class="ovrsvg" viewBox="0 0 120 62" aria-hidden="true"><path class="ovrring" d="M4 58 A56 56 0 0 1 116 58"/><path class="ovrring" d="M22 58 A38 38 0 0 1 98 58"/><path class="ovrring" d="M40 58 A20 20 0 0 1 80 58"/><line class="ovrtick" x1="60" y1="58" x2="60" y2="4"/><circle class="ovrme" cx="60" cy="58" r="3"/><circle class="ovrblip" cx="60" cy="58" r="5" style="display:none"/></svg><span class="ovrtext"></span>`;
      el.title="The cube's jingle, heard in the game's sound: louder is closer, its side is the stereo balance. Stereo cannot tell ahead from behind: turn towards it; if it moves to the middle it is ahead, if it moves further out it is behind. Empyrean Trace feathers sound alike.";
    }
    const blip=el.querySelector(".ovrblip"), label=el.querySelector(".ovrtext");
    if(r.heard&&!r.learning){
      const a=(r.angle||0)*Math.PI/180, d=6+50*(1-(r.proximity||0));
      blip.setAttribute("cx",(60+d*Math.sin(a)).toFixed(1));
      blip.setAttribute("cy",(58-d*Math.cos(a)).toFixed(1));
      blip.style.opacity=Math.max(0.35,1-(r.since||0)/2.5).toFixed(2);
      blip.style.display="";
    } else blip.style.display="none";
    const text=radarText(r);
    if(label.textContent!==text)label.textContent=text;
  }

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
  // capture cannot see game FPS). Off by default. The frame loop runs ONLY while
  // the FPS readout is enabled: a continuous requestAnimationFrame loop keeps the
  // always-on-top, semi-transparent overlay compositing every frame, which on some
  // GPU/DWM setups flickers a black band at the screen edge over a borderless game.
  // Idle/default overlays must not drive a 60fps repaint for nothing.
  let frames=0, fpsAt=performance.now(), fpsRunning=false;
  function fpsTick(now){
    if(!fpsRunning)return;
    frames++;
    if(now-fpsAt>=1000){
      if(showFps&&!partyMode){const el=$("#ovfps");if(el)el.textContent="Overlay "+Math.round(frames*1000/(now-fpsAt))+" FPS";}
      frames=0; fpsAt=now;
    }
    requestAnimationFrame(fpsTick);
  }
  function setFpsLoop(on){
    if(on&&!fpsRunning){fpsRunning=true;frames=0;fpsAt=performance.now();requestAnimationFrame(fpsTick);}
    else if(!on){fpsRunning=false;}
  }
  setFpsLoop(showFps&&!partyMode);

  applyOpacity(); renderMeter(); pollMeter();
})();
