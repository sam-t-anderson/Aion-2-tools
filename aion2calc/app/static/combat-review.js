/* Shared combat explorer used by the desktop, Pages and log server. */
(function () {
  "use strict";
const buildLabel=x=>String(x??'').replace(/version:product:([0-9.]+)/g,(_,v)=>'Product version '+v.split('.').slice(0,4).join('.')).replace(/build:steam:[0-9]{1,12}:([0-9]{1,20})/g,'Legacy build $1 · Steam').replace(/build:purple:A2_[A-Z0-9_]{1,80}_PURPLE:([0-9]{1,20})/g,'Legacy build $1 · PURPLE');
  const defaults = {gladiator:"#c69b6d",templar:"#f58cba",assassin:"#fff468",ranger:"#aad372",sorcerer:"#3fc7eb",spiritmaster:"#8788ee",cleric:"#ffffff",chanter:"#ff7c0a"};
  // Named class-colour palettes (app customization presets). Each sets all eight
  // classes at once wherever class colours are used — the meter, combat review,
  // charts and the overlay bars. "Colourblind-friendly" uses the Okabe–Ito set,
  // chosen to stay distinct for the common red/green colour-vision deficiencies.
  const PALETTES = {
    "Default (class colours)": defaults,
    "Colourblind-friendly": {gladiator:"#e69f00",templar:"#cc79a7",assassin:"#f0e442",ranger:"#009e73",sorcerer:"#56b4e9",spiritmaster:"#0072b2",cleric:"#bbbbbb",chanter:"#d55e00"},
    "High contrast": {gladiator:"#ff9f1c",templar:"#ff5dd2",assassin:"#ffe600",ranger:"#4cff4c",sorcerer:"#36d6ff",spiritmaster:"#7c6cff",cleric:"#ffffff",chanter:"#ff5a2a"},
    "Pastel": {gladiator:"#e6c79c",templar:"#f5b8d6",assassin:"#fff3a3",ranger:"#c3e6a3",sorcerer:"#a7dcef",spiritmaster:"#bcbdf0",cleric:"#eaeaea",chanter:"#ffc49c"},
    "Vivid": {gladiator:"#ff8c00",templar:"#ff2fae",assassin:"#ffe000",ranger:"#2ecc40",sorcerer:"#00bfff",spiritmaster:"#6a5cff",cleric:"#f5f5f5",chanter:"#ff4500"},
    // The live overlay's own default tints (overlay.js OVERLAY_CLASS_COLORS); applying it
    // here carries the same colours into the review pages and charts.
    "Overlay (cool)": {gladiator:"#c8474f",templar:"#c9772b",assassin:"#4caf6e",ranger:"#b9962a",sorcerer:"#3a86c8",spiritmaster:"#7a63d8",cleric:"#3fb4b0",chanter:"#b84f9e"}
  };
  const esc = x => String(x ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = x => Math.round(x || 0).toLocaleString();
  // Verified local NPC-role corrections, mirroring the client's
  // meter/a2parser/data/npc_role_overrides.json. A log may carry a stale
  // is_boss flag (recorded or server-classified before the catalog fix), so the
  // viewer suppresses these minibosses everywhere it marks or counts a boss.
  const MINIBOSS_CODES = new Set(["2300907","2310907","2320907"]);   // Shining Mau Totem
  const bossEntity = e => !!(e && e.is_boss && !MINIBOSS_CODES.has(String(e.mob_code)));
  const bossKeyIsMiniboss = key => MINIBOSS_CODES.has(String(key || "").replace(/^npc:/, ""));
  function preferences() { try {return JSON.parse(localStorage.getItem("a2-combat-colors")) || {};} catch (_) {return {}; } }
  function color(cls) { const pref=preferences(); const candidate=(pref.colors || {})[cls] || defaults[cls] || "#e8cf8e"; return pref.enabled === false ? "#e8cf8e" : /^#[0-9a-f]{6}$/i.test(candidate) ? candidate : "#e8cf8e"; }
  function settings(root,onSave) {
    const pref=preferences();
    root.innerHTML=`<label><input type="checkbox" data-enable ${pref.enabled!==false?"checked":""}> Use class colors</label><div class="row" style="gap:6px;margin:6px 0"><label>Palette <select data-palette><option value="">Choose a palette…</option>${Object.keys(PALETTES).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join("")}</select></label><button class="btn small" data-apply-palette>Apply</button></div><div class="cr-colors">${Object.keys(defaults).map(c=>`<label>${esc(c)} <input type="color" data-color="${c}" value="${color(c)}"></label>`).join("")}</div><button class="btn small" data-reset>Reset class colors</button>`;
    const save=()=>{const pref={enabled:root.querySelector("[data-enable]").checked,colors:Object.fromEntries([...root.querySelectorAll("[data-color]")].map(e=>[e.dataset.color,e.value]))};localStorage.setItem("a2-combat-colors",JSON.stringify(pref));if(onSave)onSave(pref);};
    root.onchange=save;root.querySelector("[data-reset]").onclick=()=>{localStorage.removeItem("a2-combat-colors");settings(root,onSave);if(onSave)onSave({});};
    root.querySelector("[data-apply-palette]").onclick=()=>{const pal=PALETTES[root.querySelector("[data-palette]").value];if(!pal)return;root.querySelector("[data-enable]").checked=true;[...root.querySelectorAll("[data-color]")].forEach(e=>{if(pal[e.dataset.color])e.value=pal[e.dataset.color];});save();};
  }
  const table = (headers,rows) => `<div class="cr-scroll"><table class="t"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${headers.length}">No recorded events.</td></tr>`}</tbody></table></div>`;
  // Small inline NPC portrait from the bundled/community asset map (behind the
  // curated table via npc-portraits.js). Self-removes if the image fails to load.
  const npcPortrait = code => {
    const url = code!=null && window.A2BundledAssets && window.A2BundledAssets.npcs && window.A2BundledAssets.npcs[String(code)];
    if(!url) return "";
    const src = window.A2AssetHealth ? A2AssetHealth.source(url) : url;
    return `<img class="cr-npc-portrait" width="22" height="22" loading="lazy" referrerpolicy="no-referrer" src="${esc(src)}" alt="" onerror="this.remove()"> `;
  };
  // NPC display name. The backend labels an id the catalog doesn't map as "#<code>";
  // when a community name overlay (npc-portraits.js) knows that id, show the real name.
  const npcName = e => {
    const nm = (e.name!=null && e.name!=="") ? String(e.name) : String(e.id ?? "");
    if(e.mob_code!=null && /^#\d+$/.test(nm) && window.A2CommunityNames){
      const c = window.A2CommunityNames[String(e.mob_code)];
      if(c) return c;
    }
    return nm;
  };
  function mount(root, doc, options={}) {
    if(doc.meta?.reconstruction || doc.meta?.capture_quality?.reconstructed)options={...options,rankings:undefined,lookupProfile:undefined,publish:undefined,saveMetadata:undefined,report:undefined};
    let state={followLatest:!!options.live,mode:["pve","pvp"].includes(options.mode)?options.mode:"",run:"",segment:0,metric:"summary",view:"table",graph:true,timeline:true,graphMode:"total",timelineWindow:30,timelineStart:0,skills:true,deaths:true,heals:true,pets:true,combine:true,actor:"",page:0,enemy:"",hidden:new Set(),actions:"rotation",hideProcs:true, ...options.state};
    let sourceView=null,archiveFirst=1,archiveLast=doc.meta?.archive?.part || 1;
    let comparisons=[], ranks=null, rankRequest=0, replayFrame=null, profileRequest=0;
    let reportReason='privacy',reportDetails='',reportStatus='',reportBusy=false;
    const previews=new Map();
    let timelineDetail="",graphModel=null;
    const timelineHidden=new Set(),timelineCollapsed=new Set();
    let archivePage=null,archiveOffset=0,archiveBusy=false,archiveError="",archiveOpen=false,archiveRequest=0,disposed=false;
    const clock=(t,precise=false)=>{t=Math.max(0,precise?Math.round(t*100)/100:Math.floor(t));return `${Math.floor(t/60)}:${(precise?(t%60).toFixed(2):String(t%60)).padStart(precise?5:2,'0')}`;};
    const skillSource=id=>{const n=Number(id);if(!Number.isSafeInteger(n)||n<=0)return '';const source=options.skillIcon?options.skillIcon(n):'https://metabot.gg/web/aion2/skills/'+(Math.floor(n/10000)*10000)+'.webp';return window.A2AssetHealth?A2AssetHealth.source(source):source;};
    const modeOf=segment=>(segment.encounter_type||doc.meta?.encounter_type||'').startsWith('pvp_')?'pvp':'pve';
    const matchesMode=segment=>!state.mode||modeOf(segment)===state.mode;
    function selectLatest() {
      if(!options.live || !state.followLatest)return false;
      let index=doc.segments.length-1;
      while(index>=0 && !matchesMode(doc.segments[index]))index--;
      if(index<0)return false;
      state.run='';
      if(index===state.segment)return false;
      timelineHidden.clear();timelineCollapsed.clear();state.segment=index;state.actor='';state.enemy='';state.page=0;state.timelineStart=0;timelineDetail='';ranks=null;
      return true;
    }
    const refs=()=>{
      const segment=doc.segments[state.segment] || {}, active=new Set(segment.party_members || []);
      for(const e of segment.events || []){if(e.source)active.add(e.source);if(e.target)active.add(e.target);}
      for(const h of segment.hits || []){for(const key of ['player','source','target','pet'])if(h[key])active.add(h[key]);}
      const entities=segment.entities || [];
      for(let i=0;i<entities.length;i++)for(const e of entities)if(active.has(e.id) && e.owner)active.add(e.owner);
      // Roster for the selected segment: keep only actors that took part in it (active = its
      // party_members + everyone in its events/hits + pet owners), so a multi-encounter log never
      // shows another encounter's players/builds here. Fall back to all when a segment has no actors.
      const keep=id=>active.size?active.has(id):!state.run;
      const r={};for(const e of [...(doc.players || []).filter(p=>keep(p.id)),...entities.filter(e=>keep(e.id))])r[e.id]={...r[e.id],...e};
      for(const e of [...(doc.players || []),...doc.segments.flatMap(s=>s.entities || [])])if(e.profile_snapshot && r[e.id])r[e.id].profile_snapshot=e.profile_snapshot;
      for(const e of Object.values(r))if(e.owner)e.class=r[e.owner]?.class;
      return r;
    };
    // A claimed character carries the server's verified mark; one hidden by its player shows the
    // server's stand-in name and says so (see the log server's identity module).
    const label=e=>e ? `${e.name || e.id}${e.verified ? " ✓" : ""}${e.pseudonym ? " (hidden by its player)" : ""}${e.server ? " · " + e.server + (e.server_name ? " ("+e.server_name+")" : "") : ""}` : "Unknown / not recorded";
    const character=e=>e && ((doc.players || []).some(p=>p.id===e.id) || e.is_player || e.kind==="player");
    const actorHTML=e=>character(e)?`<button class="btn small" data-character="${esc(e.id)}" style="color:${color(e.class)}">${esc(label(e))}</button>`:esc(label(e));
    function profileHTML() {
      if(!state.character)return "";
      const actor=refs()[state.character];if(!actor)return "";
      const saved=actor.profile_snapshot, preview=previews.get(actor.id), snapshot=preview || saved;
      const stamp=x=>x?new Date(x*1000).toLocaleString():"Not recorded";
      const data=snapshot?.data || {};
      return `<section class="win"><div class="wh"><h3>Character build · ${esc(label(actor))}</h3><button class="btn small" data-profile-close>← Back to log</button></div><div class="wb"><p class="note">${preview?"Current profile preview; this is not the historical build for this encounter.":saved?"Saved at upload time. Gear may have changed between the encounter and the official lookup. This snapshot will not refresh to newer gear.":"No historical official profile was saved with this log."}</p>
        <p>Status: ${esc(snapshot?.status || "unavailable")} · ${esc(snapshot?.reason || "")}<br>Upload received: ${esc(stamp(saved?.uploaded_at))} · Official fetch completed: ${esc(stamp(snapshot?.fetched_at))}</p>
        ${snapshot?.data?`<p>${esc(snapshot.source)} · ${esc(snapshot.identity?.name)} · ${esc(snapshot.identity?.region)} · Server ${esc(snapshot.identity?.server)}</p>${window.A2CharacterView?A2CharacterView.details(data,snapshot.identity?.region||data.region):'<p>Update this viewer to show character details.</p>'}<h3>Full recorded build information</h3><p class="small muted">Expand a section for equipment rolls, specialties, titles, skins, board nodes and other fields supplied by the official service.</p>${Object.entries(data).map(([key,value])=>`<details><summary>${esc(key.replaceAll('_',' '))}</summary><pre class="cr-profile-json">${esc(JSON.stringify(value,null,2))}</pre></details>`).join('')}<button class="btn small" data-profile-download>Export this profile JSON</button>${window.A2AssetHealth?'<button class="btn small" data-export-images>Export image failures</button>':''}`:""}
        ${options.openBuildWorkspace&&saved?.data?'<button class="btn small" data-build-workspace>Open saved character in Builds</button>':""}${preview?'<button class="btn small" data-profile-saved>Return to saved historical profile</button>':""}${options.lookupProfile?`<div class="row"><label>Region <select data-profile-region><option value="">Detect from server ID</option>${Object.entries({nae:"North America",eu:"Europe",as:"Asia",la:"Latin America"}).map(([key,value])=>`<option value="${key}" ${key===(actor.region || doc.meta?.region)?"selected":""}>${value}</option>`).join("")}</select></label><label>Character server ID <input data-profile-server type="number" min="1" step="1" value="${esc(actor.server || '')}" placeholder="Required when not recorded"></label><button class="btn small" data-profile-current>Fetch current official profile (not historical)</button></div><p class="small muted">Use this character's home server, not your own server. Manual lookup only previews current gear; it does not change the saved historical profile.</p>`:""}${snapshot?.status==="pending"?'<p class="small muted">The server is fetching this profile. Reopen the shared log in a moment to load its saved result.</p>':""}<span data-profile-message role="status"></span></div></section>`;
    }
    function bindImageExport(){
      root.querySelectorAll('[data-export-images]').forEach(button=>button.onclick=()=>{
        A2AssetHealth.exportReport();const previous=button.textContent;button.textContent='Export requested · check Downloads';setTimeout(()=>{button.textContent=previous;},4000);
      });
    }
    function bindProfile(){
      bindImageExport();
      const workspace=root.querySelector('[data-build-workspace]');if(workspace)workspace.onclick=()=>options.openBuildWorkspace(refs()[state.character],state.segment);
      const close=root.querySelector('[data-profile-close]');if(close)close.onclick=()=>{state.character="";profileRequest++;render();};
      const saved=root.querySelector('[data-profile-saved]');if(saved)saved.onclick=()=>{previews.delete(state.character);render();};
      const current=root.querySelector('[data-profile-current]');if(current)current.onclick=async()=>{const id=state.character,request=++profileRequest;current.disabled=true;root.querySelector('[data-profile-message]').textContent='Fetching current official profile…';try{const actor=refs()[id],server=root.querySelector('[data-profile-server]').value.trim(),region=root.querySelector('[data-profile-region]').value;if(!server)throw Error('Enter this character’s numeric home server ID before fetching.');const result=await options.lookupProfile({...actor,server,region},region);if(request!==profileRequest)return;previews.set(id,result);render();}catch(e){if(request===profileRequest)root.querySelector('[data-profile-message]').textContent=e.message;}finally{if(current.isConnected)current.disabled=false;}};
      const download=root.querySelector('[data-profile-download]');if(download)download.onclick=()=>{const snapshot=previews.get(state.character) || refs()[state.character]?.profile_snapshot;const url=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='character-profile.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
    }
    const rootOwner=(id,r)=>{const seen=new Set();while(r[id]?.owner && !seen.has(id)){seen.add(id);id=r[id].owner;}return id;};
    const owner=(id,r)=>state.combine?rootOwner(id,r):id;
    function data() {
      const segment=doc.segments[state.segment] || {duration:1,hits:[]};const r=refs();
      const recorded=segment.events || [];
      const events=(recorded.length ? recorded : (segment.hits || []).map(h=>({kind:"damage",t:h.t,source:h.source || h.player,target:h.target,amount:h.damage,skill:h.skill,skill_id:h.skill_id}))).slice().sort((a,b)=>a.t-b.t);
      const friendly=new Set((doc.players || []).map(p=>p.id));
      const seenDeaths=new Set();
      const rows=new Map();
      const row=id=>{const key=owner(id,r);if(!key)return null;if(!rows.has(key)) rows.set(key,{...(r[key] || {id:key,name:key}),damage:0,taken:0,healing:0,deaths:0,revives:0});return rows.get(key);};
      for(const e of events) {
        if(e.kind==="death") {const key=e.target+":"+e.t;if(seenDeaths.has(key))continue;seenDeaths.add(key);if(friendly.has(e.target) || (!state.combine && r[e.target]?.owner)) {const p=row(e.target);if(p)p.deaths++;}continue;}
        if(e.kind==="revive") {if(friendly.has(e.target)) {const p=row(e.target);if(p)p.revives++;}continue;}
        if(e.kind==="damage") {
          if((friendly.has(e.source) || r[e.source]?.owner) && (!state.enemy || e.target===state.enemy)) {const p=row(e.source);if(p)p.damage+=e.amount;}
          if((friendly.has(e.target) || r[e.target]?.owner) && (!state.enemy || e.source===state.enemy)) {const p=row(e.target);if(p)p.taken+=e.amount;}
        }
        if(e.kind==="heal" && (friendly.has(e.source) || r[e.source]?.owner)) {const p=row(e.source);if(p)p.healing+=e.amount;}
      }
      const outgoing=events.filter(e=>e.kind==='damage' && friendly.has(rootOwner(e.source,r)) && !friendly.has(rootOwner(e.target,r)));
      const firstDamage=outgoing.length?outgoing[0].t:0;
      const dpsDuration=Math.max(1,new Set(outgoing.map(e=>Math.floor(Math.max(0,e.t-firstDamage)))).size);
      return {segment,r,events,rows:[...rows.values()],friendly,dpsDuration};
    }
    function visibleEvents(d) {
      return d.events.filter(e=>(!state.actor || owner(e.source,d.r)===state.actor || owner(e.target,d.r)===state.actor)
        && (!state.enemy || e.kind!=="damage" || e.target===state.enemy || e.source===state.enemy)
        && (state.pets || (!d.r[e.source]?.owner && !d.r[e.target]?.owner))
        && (state.metric==="summary" || (state.metric==="damage" && e.kind==="damage" && (d.friendly.has(e.source) || d.r[e.source]?.owner))
          || (state.metric==="taken" && e.kind==="damage" && (d.friendly.has(e.target) || d.r[e.target]?.owner)) || (state.metric==="healing" && e.kind==="heal") || (state.metric==="deaths" && e.kind==="death")));
    }
    function graph(d, events) {
      const duration=Math.max(d.segment.duration,1),step=Math.max(1,Math.ceil(duration/1200)),count=Math.ceil(duration/step),series={};
      const primary=state.metric==='healing'?'Healing':state.metric==='taken'?'Damage taken':'Damage done';
      for(const e of events) {
        if(e.kind==='death')continue;
        let actor,kind;
        if(e.kind==='heal'){actor=owner(e.source,d.r);kind='Healing';}
        else if(d.friendly.has(e.source)||d.r[e.source]?.owner){actor=owner(e.source,d.r);kind='Damage done';}
        else if(d.friendly.has(e.target)||d.r[e.target]?.owner){actor=owner(e.target,d.r);kind='Damage taken';}else continue;
        const key=actor+':'+kind;if(state.hidden.has(key))continue;
        const line=series[key] ||= {actor,kind,values:Array(count).fill(0)};
        const i=Math.max(0,Math.min(count-1,Math.floor(e.t/step)));
        line.values[i]+=(e.amount||0)/Math.max(.001,Math.min(step,duration-i*step));
      }
      const kinds=['Damage done','Healing','Damage taken'];
      const lines=Object.entries(series).sort(([,a],[,b])=>label(d.r[a.actor]).localeCompare(label(d.r[b.actor])) || String(a.actor).localeCompare(String(b.actor)) || kinds.indexOf(a.kind)-kinds.indexOf(b.kind)),total=Array(count).fill(0);
      for(const [,line] of lines)if(line.kind===primary)line.values.forEach((v,i)=>total[i]+=v);
      const roll=total.map((_,i)=>{let amount=0,seconds=0;for(let j=i;j>=0 && (i-j)*step<10;j--){const span=Math.min(step,duration-j*step,10-(i-j)*step);amount+=total[j]*span;seconds+=span;}return amount/Math.max(.001,seconds);});
      let maximum=1;for(const v of [...total,...roll])maximum=Math.max(maximum,v);
      if(state.graphMode==='players')for(const [,s] of lines)for(const v of s.values)maximum=Math.max(maximum,v);
      const x=t=>60+880*t/duration,y=v=>180-v*160/maximum;
      const grid=[0,.25,.5,.75,1].map(f=>`<path d="M60 ${180-f*160}H940" stroke="currentColor" opacity=".12"/><text x="52" y="${184-f*160}" text-anchor="end" fill="currentColor" font-size="11">${number(maximum*f)}</text>`).join('');
      const ticks=Array.from({length:7},(_,i)=>`<text x="${60+i*880/6}" y="205" text-anchor="middle" fill="currentColor" font-size="11">${clock(duration*i/6)}</text>`).join('');
      const bars=total.map((v,i)=>`<rect x="${x(i*step)}" y="${y(v)}" width="${Math.max(.5,880*Math.min(step,duration-i*step)/duration-1)}" height="${180-y(v)}" style="fill:var(--chart-bar,#39c2e047)"/>`).join('');
      const average=`<polyline points="${roll.map((v,i)=>`${x(Math.min(duration,(i+.5)*step))},${y(v)}`).join(' ')}" fill="none" style="stroke:var(--chart-line,#e8cf8e)" stroke-width="2"/>`;
      const paths=state.graphMode==='players'?lines.map(([,s])=>`<polyline fill="none" stroke="${color(d.r[s.actor]?.class)}" stroke-width="2" ${s.kind==='Damage taken'?'stroke-dasharray="7 4"':s.kind==='Healing'?'stroke-dasharray="2 3"':''} points="${s.values.map((v,i)=>`${x(Math.min(duration,(i+.5)*step))},${y(v)}`).join(' ')}"/>`).join(''):bars+average;
      const health=(d.segment.health||[]).filter(s=>s.t>=0 && s.t<=duration && (state.enemy?s.entity===state.enemy:bossEntity(d.r[s.entity])));
      let hpMax=1;for(const s of health)hpMax=Math.max(hpMax,s.max||s.current);
      const hp=[...new Set(health.map(s=>s.entity))].map(id=>`<polyline fill="none" stroke="#ef6262" stroke-width="1.5" points="${health.filter(s=>s.entity===id).map(s=>`${x(s.t)},${180-s.current*160/hpMax}`).join(' ')}"><title>${esc(label(d.r[id]))} HP (right scale)</title></polyline>`).join('');
      graphModel={duration,step,count,total,roll,lines,health,primary};
      return `<div class="cr-graph"><div class="row small"><label>Graph style <select data-graph-mode><option value="total" ${state.graphMode!=='players'?'selected':''}>Live style · bars + 10 s average</option><option value="players" ${state.graphMode==='players'?'selected':''}>Player series</option></select></label><span>${esc(primary)} per second · ${step}s buckets${health.length?' · red: boss HP, right scale':' · Boss HP: not recorded'}</span></div>
        <div class="cr-legend small" aria-label="Graph key">${state.graphMode==='players'?'<span>Class-colored lines: player rates · solid: damage done · dashed: damage taken · dotted: healing</span>':`<span><svg width="18" height="12" aria-hidden="true"><rect width="18" height="12" style="fill:var(--chart-bar,#39c2e047)"/></svg> Bars: total ${esc(primary.toLowerCase())} per second</span><span><svg width="24" height="12" aria-hidden="true"><path d="M0 6H24" style="stroke:var(--chart-line,#e8cf8e)" stroke-width="2"/></svg> Gold line: trailing 10-second average</span>`}${health.length?'<span><svg width="24" height="12" aria-hidden="true"><path d="M0 6H24" stroke="#ef6262" stroke-width="2"/></svg> Red line: boss HP (right axis)</span>':''}</div>
        <svg viewBox="0 0 1000 220" role="img" aria-label="Combat rate chart">${grid}${ticks}${paths}${hp}${health.length?`<text x="948" y="25" fill="#ef6262" font-size="11">${number(hpMax)}</text><text x="948" y="184" fill="#ef6262" font-size="11">0 HP</text>`:''}<path data-graph-cursor d="M60 20V180" stroke="currentColor" stroke-dasharray="3 3" visibility="hidden"/><rect data-graph-hit x="60" y="20" width="880" height="160" fill="transparent" tabindex="0" role="button" aria-label="Inspect graph time; use left and right arrow keys"/></svg>
        <div class="note small" data-graph-detail role="status">Hover or click the graph for rates. In Timeline view, click a time to move the timeline window there.</div><div class="cr-legend">${lines.map(([key,s])=>`<button class="btn small" data-series="${esc(key)}" style="color:${color(d.r[s.actor]?.class)}">${esc(label(d.r[s.actor]))} · ${s.kind}</button>`).join('')}<button class="btn small" data-showall>Show all series</button></div></div>`;
    }
    function latencyHTML(d) {
      const samples=(d.segment.ping || []).filter(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p[0]>=0&&p[0]<=d.segment.duration&&p[1]>=0&&p[1]<=60000);
      if(!samples.length)return '<p class="small muted">Recorder ping: not recorded for this encounter.</p>';
      const values=samples.map(p=>p[1]),avg=values.reduce((a,b)=>a+b,0)/values.length;
      let min=Infinity,max=0;for(const v of values){min=Math.min(min,v);max=Math.max(max,v);}
      const duration=Math.max(.001,d.segment.duration),scale=Math.max(1,max),x=t=>60+880*t/duration,y=v=>130-110*v/scale;
      const plotted=samples.filter((_,i)=>i%Math.max(1,Math.ceil(samples.length/1500))===0 || i===samples.length-1);
      const recorder=d.r[d.segment.ping_recorder];
      return `<section class="cr-graph"><h3>Recorder ping${recorder?' · '+esc(label(recorder)):''}</h3><p>Average ${avg.toFixed(1)} ms · Minimum ${min.toFixed(1)} ms · Maximum ${max.toFixed(1)} ms · ${number(samples.length)} samples</p><p class="small muted">${d.segment.ping_source==='passive_tcp_ack'?'Passive TCP acknowledgement RTT':'Recorded latency; measurement source unavailable'}. These samples describe the recording connection, not every party member or game action latency. Gaps have no samples; the average weights recorded samples equally.</p><svg viewBox="0 0 1000 160" role="img" aria-label="Recorder ping over encounter time"><text x="5" y="25" fill="currentColor" font-size="12">${scale.toFixed(1)} ms</text><text x="10" y="130" fill="currentColor" font-size="12">0 ms</text><path d="M60 20V130H940" fill="none" stroke="currentColor" opacity=".3"/>${plotted.map(p=>`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="2.5" fill="#6bd7ef"><title>${clock(p[0],true)} · ${p[1].toFixed(1)} ms</title></circle>`).join('')}<text x="60" y="150" fill="currentColor" font-size="12">0:00</text><text x="900" y="150" fill="currentColor" font-size="12">${clock(duration)}</text></svg></section>`;
    }
    function bossHPHTML(d) {
      const bosses=(d.segment.entities || []).filter(e=>bossEntity(e) && (!state.enemy || e.id===state.enemy));
      if(!bosses.length)return '';
      return '<h3>Remaining boss HP · latest recorded sample</h3>'+table(['Boss','Remaining HP','Observed maximum','Remaining %','Sample time'],bosses.map(b=>{
        const hp=(d.segment.health || []).filter(h=>h.entity===b.id && h.t<=d.segment.duration).sort((a,b)=>b.t-a.t)[0];
        return `<tr><td>${esc(b.name || b.id)}</td><td>${hp?number(hp.current):'Not recorded'}</td><td>${hp?.max?number(hp.max):'Not recorded'}</td><td>${hp?.max && hp.current<=hp.max?(100*hp.current/hp.max).toFixed(1)+'%':'Unavailable'}</td><td>${hp?clock(hp.t,true):'—'}</td></tr>`;
      }))+'<p class="small muted">HP is observed, not inferred from damage. A last positive sample does not establish the final outcome.</p>';
    }
    function encounters(d) {
      const enemies=(d.segment.entities || []).filter(e=>e.kind==="enemy");
      return `<h3>Enemy encounters</h3>${table(["Enemy","Creature type","Damage received","Observed lifespan"],enemies.map(e=>{
        const ee=d.events.filter(x=>x.source===e.id || x.target===e.id),damage=ee.filter(x=>x.kind==="damage" && x.target===e.id).reduce((n,x)=>n+x.amount,0);
        const name=e.is_player?actorHTML(e):npcPortrait(e.mob_code)+esc(npcName(e));
        return `<tr><td>${name} <button class="btn small" data-enemy-filter="${esc(e.id)}">Filter${e.is_player?" (opponent)":bossEntity(e)?" (boss)":""}</button></td><td>${esc(e.mob_code ?? "Unknown")}</td><td>${number(damage)}</td><td>${ee.length?ee[0].t.toFixed(1)+"–"+ee[ee.length-1].t.toFixed(1)+"s":"—"}</td></tr>`;}))}<button class="btn small" data-clear-enemy>All enemies</button>`;
    }
    function timeline(d, events) {
      const duration=Math.max(1,d.segment.duration),span=Math.min(duration,Number(state.timelineWindow)||duration);
      state.timelineStart=Math.max(0,Math.min(Number(state.timelineStart)||0,duration-span));
      const start=state.timelineStart,end=start+span,width=Math.max(900,Math.min(8000,span*32));
      const inWindow=events.filter(e=>e.t>=start && (e.t<end || end===duration && e.t<=end));
      const ids=[...new Set(events.flatMap(e=>[owner(e.source,d.r),owner(e.target,d.r)]).filter(id=>id && (d.friendly.has(id)||d.r[id]?.owner)))];
      let omitted=0;
      const lanes=ids.filter(id=>!timelineHidden.has(id)).map(id=>{
        const controls=`<button class="btn small" data-timeline-collapse="${esc(id)}" aria-expanded="${!timelineCollapsed.has(id)}">${timelineCollapsed.has(id)?'Expand':'Collapse'}</button><button class="btn small" data-timeline-hide="${esc(id)}">Hide</button>`;
        if(timelineCollapsed.has(id))return `<div class="cr-lane cr-lane-collapsed" style="grid-template-columns:180px ${width}px"><div class="cr-lane-name" style="color:${color(d.r[id]?.class)}">${actorHTML(d.r[id])}</div><div class="row cr-lane-controls">${controls}<span class="small muted">Timeline collapsed</span></div></div>`;
        const all=inWindow.filter(e=>e.kind==='death'?state.deaths && owner(e.target,d.r)===id && (!state.combine||!d.r[e.target]?.owner):e.kind==='heal'?state.heals && owner(e.source,d.r)===id:state.skills && (state.metric==='taken'?owner(e.target,d.r)===id:owner(e.source,d.r)===id));
        const occupied=[-100,-100,-100];let marks='';
        for(const e of all) {
          const x=Math.max(0,Math.min(width-24,(e.t-start)*width/span));
          const lane=occupied.findIndex(last=>x>=last+25);
          if(e.kind!=='death' && lane<0){omitted++;continue;}
          const y=e.kind==='death'?2:3+lane*27;if(e.kind!=='death')occupied[lane]=x;
          const fill=e.kind==='death'?'#ef6262':e.kind==='heal'?'#58d68d':state.metric==='taken'?'#ed9863':color(d.r[id]?.class);
          const detail=esc(clock(e.t,true)+' · '+label(d.r[e.source])+' → '+label(d.r[e.target])+' · '+(e.skill||e.kind)+' · '+number(e.amount));
          const icon=e.kind==='death'?'':skillSource(e.skill_id);
          marks+=`<g class="cr-marker" data-effect-detail="${detail}" tabindex="0" role="button" aria-label="${detail}"><title>${detail}</title>${e.kind==='death'?`<path d="M${x+11} 0V84" stroke="${fill}" stroke-width="2"/><text x="${x}" y="20" fill="${fill}" font-size="21">✝</text>`:`<rect x="${x}" y="${y}" width="23" height="23" rx="2" fill="${fill}" opacity=".45"/><text x="${x+11}" y="${y+15}" text-anchor="middle" fill="currentColor" font-size="9">${esc(String(e.skill_id||e.kind).slice(-3))}</text>${icon?`<image data-skill-icon href="${esc(icon)}" x="${x+1}" y="${y+1}" width="21" height="21" preserveAspectRatio="xMidYMid meet" pointer-events="none"/>`:''}<path d="M${x} ${y+24}h23" stroke="${fill}" stroke-width="2"/>`}</g>`;
        }
        return `<div class="cr-lane" style="grid-template-columns:180px ${width}px"><div class="cr-lane-name" style="color:${color(d.r[id]?.class)}">${actorHTML(d.r[id])}<span class="cr-lane-controls">${controls}</span></div><svg class="cr-track" style="width:${width}px;height:84px" viewBox="0 0 ${width} 84" role="img" aria-label="${esc(label(d.r[id]))} recorded effects">${marks||'<text x="12" y="25" fill="currentColor" font-size="12">No effects in this window</text>'}</svg></div>`;
      }).join('');
      const tick=span<=30?1:span<=120?5:Math.ceil(span/120),major=tick*5;
      let ticks='';for(let t=Math.ceil(start/tick)*tick;t<=end;t+=tick){const x=(t-start)*width/span,long=Math.abs(t/major-Math.round(t/major))<.001;ticks+=`<path d="M${x} ${long?17:24}V32" stroke="currentColor" opacity=".6"/>${long?`<text x="${Math.max(22,Math.min(width-22,x))}" y="13" text-anchor="middle" fill="currentColor" font-size="11">${clock(t)}</text>`:''}`;}
      return `<h3>Recorded effect timeline</h3><details class="note"><summary>Player timeline visibility · ${ids.filter(id=>!timelineHidden.has(id)).length} / ${ids.length} shown</summary><p class="small muted">Display only; graphs, tables and recorded totals are unchanged. Preferences reset when changing encounters.</p><div class="row">${ids.map(id=>`<label><input type="checkbox" data-timeline-visible="${esc(id)}" ${timelineHidden.has(id)?'':'checked'}> ${esc(label(d.r[id]))}</label>`).join('')}<button class="btn small" data-timeline-show-all>Show all</button><button class="btn small" data-timeline-expand-all>Expand all</button></div></details><div class="row small"><label>Window <select data-timeline-window>${[15,30,60,120,0].map(v=>`<option value="${v}" ${v===Number(state.timelineWindow)?'selected':''}>${v?v+' seconds':'Full encounter'}</option>`).join('')}</select></label><button class="btn small" data-time-prev ${start<=0?'disabled':''}>Earlier</button><button class="btn small" data-time-next ${end>=duration?'disabled':''}>Later</button><label>Start <input type="number" data-time-start min="0" max="${Math.max(0,duration-span)}" step=".5" value="${start.toFixed(1)}"></label><span>${clock(start)}–${clock(end)}</span></div><input class="cr-time-scrub" data-time-scrub aria-label="Timeline window start" type="range" min="0" max="${Math.max(0,duration-span)}" step=".5" value="${start}">
        <p class="small muted">Icons are recorded hits/heals, not cast starts or durations. Three stacks separate nearby effects. Green: healing; red: deaths; orange: damage taken. ${omitted?number(omitted)+' crowded markers omitted in this window; zoom in or use Events for every effect.':''} Unavailable skill images keep an ID tile.</p>
        <div class="cr-timeline"><div class="cr-lane cr-ruler" style="grid-template-columns:180px ${width}px"><div class="cr-lane-name">Encounter time</div><svg class="cr-track cr-time-axis" style="width:${width}px;height:34px" viewBox="0 0 ${width} 34">${ticks}</svg></div>${lanes||'No timeline effects recorded for these filters.'}</div><div class="note" data-effect-panel role="status">${esc(timelineDetail||'Hover, focus or click a skill icon to inspect its effect.')}</div><div class="cr-effect-tooltip" data-effect-tooltip role="tooltip" hidden></div>`;
    }
    function classificationHTML(d) {
      const c=d.segment.classification;if(!c)return '';
      const labels={catalog_match:'Catalog match',map_match:'Map match',ambiguous:'Partial match',conflict:'Conflicting evidence',unavailable:'Not identified'};
      return `<details class="note"><summary>Automatic encounter context · ${esc(labels[c.status]||c.status)}${c.basis==='npc_only'?' · NPC-only suggestion':''}</summary><p>${esc(c.note)}</p><p>Recorded map: ${esc(c.recorded_map_id||'not recorded')} · Recorded instance: ${esc(c.recorded_instance_id||'not recorded')} · Catalog instance candidate: ${esc(c.catalog_instance_id||'not identified')} · Basis: ${esc((c.basis||'none').replaceAll('_',' '))}.</p>${[...(c.conflicts||[]),...(c.ambiguities||[])].map(v=>`<p>${esc(v)}</p>`).join('')}${(c.npcs||[]).length?table(['Recorded NPC ID','Catalog instance','Category','Tier'],c.npcs.map(r=>`<tr><td>${esc(r.npc_id)}</td><td>${esc(r.instance_id)}</td><td>${esc(r.category||'Unavailable')}</td><td>${esc(r.tier||'Unavailable')}</td></tr>`)):''}${c.omitted_npcs?`<p>${number(c.omitted_npcs)} additional NPC rows omitted.</p>`:''}</details>`;
    }

    function catalogHTML(d) {
      const c=doc.encounter_insights?.segments?.find(s=>s.segment===state.segment)?.catalog;
      if(!c)return '';
      return `<details class="note"><summary>Mapping coverage · ${c.unmapped.length}${c.omitted?'+':''} unresolved catalog IDs · ${number(c.npc_entities_without_type)} missing NPC types</summary><p>${esc(c.note)}</p><p>Catalog ${esc(c.catalog_revision)} · Map ${esc(c.map_id || 'not recorded')} · Instance ${esc(c.instance_id || 'not recorded')} · ${number(c.npc_entities_without_type)} enemy references have no NPC type. ${c.omitted?`${number(c.omitted)} additional IDs omitted.`:''}</p>${c.catalog_source?.revision?`<p class="small muted">Mapping source: ${esc(c.catalog_source.repository)} · commit ${esc(c.catalog_source.revision.slice(0,12))} · checked ${esc(c.catalog_source.checked_at || 'not recorded')}. English table hashes ${c.catalog_source.english_tables_match_source===true?'match the source snapshot':'not confirmed against the source snapshot'}. Community catalog; game-version association ${esc(c.catalog_source.game_build || 'not established')}.</p>`:''}${table(['Kind','Recorded ID','Entity references','Recorded effects'],c.unmapped.map(r=>`<tr><td>${esc(r.kind)}</td><td>${esc(r.code)}</td><td>${number(r.entity_count)}</td><td>${number(r.effects)}</td></tr>`))}${c.unidentified_entities?.length?`<h4>Enemy references without an NPC type</h4><p class="small muted">These actor references apply only to this recorded session. They are not NPC catalog IDs; a supported spawn/identity record is needed to identify them. ${c.unidentified_omitted?number(c.unidentified_omitted)+' additional references omitted.':''}</p>${table(['Session actor reference','Recorded effects'],c.unidentified_entities.map(r=>`<tr><td>${esc(r.entity)}</td><td>${r.effects==null?'Unavailable':number(r.effects)}</td></tr>`))}`:''}<button class="btn small" data-export-mappings>Export mapping report</button><span data-mapping-status role="status"></span></details>`;
    }
    function insightsHTML(d) {
      const analysis=doc.encounter_insights, s=analysis?.segments?.find(s=>s.segment===state.segment);
      if(!s)return '<p class="note">Encounter insights are unavailable in this older view. Reopen the local file with the updated app, or update the sharing server.</p>';
      const selected=id=>!state.actor || owner(id,d.r)===state.actor;
      const pet=id=>!state.pets && !!d.r[id]?.owner;
      const ability=r=>esc(r.skill || r.name || r.skill_id || 'Unknown ability');
      const omitted=Object.entries(s.omitted || {}).filter(([,n])=>n).map(([key,n])=>`${n} ${key} rows`).join(', ');
      return `<details open class="note"><summary>Encounter insights · observed evidence</summary><p>${esc(analysis.note)} Player and pet filters apply to effect rows; enemy/metric/graph filters do not change these encounter-wide summaries. Pets retain their own source labels, even with owner grouping enabled. HP milestones describe all marked bosses.</p>
        ${omitted || s.omitted_opening?`<p>Session detail limits omitted: ${esc(omitted)}${s.omitted_opening?` · ${s.omitted_opening} opening effects`:''}. Filters apply after limits; use Events for retained underlying effects.</p>`:''}
        <h4>Evidence coverage</h4><p class="small muted">Counts describe this retained encounter. Not recorded does not prove an effect never happened. Missing attribution can limit player-specific summaries.</p>
        ${s.capabilities?table(['Evidence','Status','Records','Basis'],s.capabilities.map(r=>`<tr><td>${esc(r.feature)}</td><td>${r.records===null?'Unavailable':r.records>0?'Recorded':'Not recorded'}</td><td>${r.records===null?'—':number(r.records)}</td><td>${esc(r.basis)}</td></tr>`)):'<p>Update the sharing server or reopen the file with the updated app for evidence coverage and pressure summaries.</p>'}
        ${s.pressure?`<h4>Peak recorded pressure windows</h4><p class="small muted">${esc(s.pressure.note)}</p><p class="small muted">${number(s.pressure.death_boundary_effect_references)} actor/metric effect references excluded at death timestamps; ${number(s.pressure.outside_duration_effects)} effects outside encounter duration excluded. ${number(s.pressure.omitted_windows)} window rows and ${number(s.pressure.omitted_incoming)} incoming-ability rows omitted before filters.</p>
        ${table(['Actor','Metric','Window','Start → end','Observed span','Recorded amount','Effects','Recorded healing received'],s.pressure.windows.filter(r=>selected(r.actor)&&!pet(r.actor)).map(r=>`<tr><td>${actorHTML(d.r[r.actor])}</td><td>${esc({damage_done:'Damage done',healing_done:'Healing done',damage_taken:'Damage taken'}[r.metric] || r.metric)}</td><td>${number(r.window_s)}s</td><td>${r.start_s.toFixed(3)} → ${r.end_s.toFixed(3)}s</td><td>${r.observed_span_s.toFixed(3)}s</td><td>${number(r.amount)}</td><td>${number(r.effects)}</td><td>${r.recorded_healing==null?'—':number(r.recorded_healing)+' · '+number(r.healing_effects)+' effects'}</td></tr>`))}
        <h4>Incoming abilities</h4><p class="small muted">Recorded damage by source, recipient and ability across this encounter. Largest hit is one recorded damage effect. Totals retain effects at death timestamps; peak windows exclude those ambiguous boundaries. No killing blow or avoidability is inferred.</p>
        ${table(['Source','Recipient','Ability','Recorded amount','Effects','Largest hit','First → last'],s.pressure.incoming.filter(r=>selected(r.target)&&!pet(r.target)&&!pet(r.source)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${actorHTML(d.r[r.target])}</td><td>${ability(r)}</td><td>${number(r.amount)}</td><td>${number(r.effects)}</td><td>${number(r.largest_hit)}</td><td>${r.first.toFixed(3)} → ${r.last.toFixed(3)}s</td></tr>`))}`:''}
        <h4>Boss HP milestones</h4><p class="small muted">First recorded sample at or below each threshold. A capture starting late can show several thresholds at the same time. No interpolation, named phase or exact crossing time is inferred; raw HP without an observed maximum cannot establish percentages.</p>
        ${table(['Boss','Threshold','First observed sample','Observed HP'],s.milestones.map(r=>`<tr><td>${esc(label(d.r[r.entity]))}</td><td>≤ ${r.threshold_pct}%</td><td>${r.t.toFixed(3)}s</td><td>${number(r.current)} / ${number(r.max)} (${r.observed_pct.toFixed(1)}%)</td></tr>`))}
        <h4>Healing relationships</h4><p class="small muted">${s.healing_without_source} healing effects lack a source; ${s.healing_without_target} lack a recipient. These are excluded from pairs, not assigned to a player. Recorded amounts include overheal; effective healing on players is below.</p>
        ${table(['Healer','Recipient','Recorded amount','Effects'],s.healing.filter(r=>(selected(r.source)||selected(r.target))&&!pet(r.source)&&!pet(r.target)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${actorHTML(d.r[r.target])}</td><td>${number(r.amount)}</td><td>${r.effects}</td></tr>`))}
        ${s.healing_effect?(()=>{const h=s.healing_effect,c=h.check,over=r=>`${number(r.overheal)}${r.overheal_pct==null?'':` <span class="small muted">${r.overheal_pct.toFixed(1)}%</span>`}`;return `<h4>Effective healing and overheal</h4><p class="small muted">An instant heal on a player restores at most the HP they are missing: that part is effective healing, the rest overheal. Both come from the party HP feed (the target's last HP reading before the heal, and their maximum HP); a heal with no earlier reading or no known maximum is counted under <i>No reading</i>. Heals over time are recorded once with their whole amount while HP rises tick by tick, and some shields are reported as healing, so both are listed apart and not measured (from the skill descriptions; potions heal over time). Check, per read that healed a player: the HP after it matched the HP before plus its effective healing ${number(c.exact)} times in full and ${number(c.capped)} times topped up to maximum HP; ${number(c.other)} reads had other changes in between (damage, ticks) and ${number(c.unchecked)} could not be checked.</p>
        ${table(['Healer','Recorded','Effective','Overheal','Over time','Shields','No reading'],h.healers.filter(r=>selected(r.source)&&!pet(r.source)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${number(r.amount)}</td><td>${number(r.effective)}</td><td>${over(r)}</td><td>${number(r.over_time)}</td><td>${number(r.shield)}</td><td>${number(r.unknown)}</td></tr>`))}
        ${table(['Healer','Recipient','Recorded','Effective','Overheal','Over time','Shields'],h.pairs.filter(r=>(selected(r.source)||selected(r.target))&&!pet(r.source)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${actorHTML(d.r[r.target])}</td><td>${number(r.amount)}</td><td>${number(r.effective)}</td><td>${over(r)}</td><td>${number(r.over_time)}</td><td>${number(r.shield)}</td></tr>`))}${h.omitted_pairs?`<p class="small muted">${number(h.omitted_pairs)} smaller pairs are not listed.</p>`:''}`;})():''}
        <h4>Imported buff windows</h4><p class="small muted">Overlapping windows for the same buff/recipient are merged and clipped to the encounter. Uptime uses total encounter duration. Overlap uses recipient outgoing damage at or after the window start and before its end. It excludes pets and does not measure damage caused by the buff. Buff caster and live buff coverage are unavailable. ${s.invalid_buff_windows} empty/reversed/outside windows excluded.</p>
        ${table(['Recipient','Buff','Observed duration','Encounter uptime','Merged windows','Overlapping damage','Damage effects','Recipient encounter damage'],s.buffs.filter(r=>selected(r.player)&&!pet(r.player)).map(r=>`<tr><td>${actorHTML(d.r[r.player])}</td><td>${ability(r)}</td><td>${r.seconds.toFixed(2)}s</td><td>${r.uptime_pct===null?'Unavailable':r.uptime_pct.toFixed(1)+'%'}</td><td>${r.windows}</td><td>${r.overlap_damage==null?'Unavailable':number(r.overlap_damage)}</td><td>${r.overlap_effects==null?'Unavailable':number(r.overlap_effects)}</td><td>${r.recipient_damage_total==null?'Unavailable':number(r.recipient_damage_total)}</td></tr>`))}
        <h4>Observed ability effects</h4><p class="small muted">Counts describe effects, not casts. First/last timestamps are observed effect times, not cooldown usage or action uptime.</p>
        ${table(['Source','Ability','Kind','Effects','Recorded amount','First → last'],s.skills.filter(r=>selected(r.source)&&!pet(r.source)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${ability(r)}</td><td>${esc(r.kind)}</td><td>${r.effects}</td><td>${number(r.amount)}</td><td>${r.first.toFixed(3)} → ${r.last.toFixed(3)}s</td></tr>`))}
        <h4>Opening effect sequence</h4><p class="small muted">First 20 retained effects per player or pet, capped at 100 per encounter. This is an observed sequence, not a recommended rotation. Equal timestamps do not prove order.</p>
        ${table(['Time','Source','Target','Ability','Kind','Amount'],s.opening.filter(r=>selected(r.source)&&!pet(r.source)).map(r=>`<tr><td>${r.t.toFixed(3)}s</td><td>${actorHTML(d.r[r.source])}</td><td>${actorHTML(d.r[r.target])}</td><td>${ability(r)}</td><td>${esc(r.kind)}</td><td>${number(r.amount)}</td></tr>`))}
      </details>`;
    }
    // Casts, buff and debuff windows, crowd control and the break gauge: the game's own records,
    // kept by the live meter since 0.2.306 and summarised in encounter_insights.actions. Pets act on
    // their own, so the rotation lists players only.
    const signedClock=t=>(t<0?'−':'')+clock(Math.abs(t),true);
    const cooldownText=ms=>ms==null?'—':(ms/1000).toFixed(ms<10000?1:0)+'s';
    const pct=v=>v==null?'—':v.toFixed(1)+'%';
    const skillCell=r=>{const icon=skillSource(r.skill_id);return `${icon?`<img class="cr-skill-icon" src="${esc(icon)}" alt="" width="18" height="18" loading="lazy" onerror="this.remove()"> `:''}${esc(r.skill || r.skill_id || 'Unknown skill')}`;};
    const endedText={expired:'Ran its duration',removed:'Removed early'};
    // One press can send several records of a skill: the cast, which carries the skill's cooldown,
    // then follow-up parts without one. Keep the cooldown-bearing records when the skill has a
    // cooldown, else its aimed records; a skill with neither is a proc or passive effect.
    function presses(casts) {
      const groups=new Map();
      // A family zeroes the rank/spec digits; class system actions (dodge, weapon equip: "xx00") stay whole.
      const family=id=>Math.floor(id/10000)%100===0?id:Math.floor(id/10000)*10000;
      for(const c of casts){const key=c.source+'|'+family(c.skill_id);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(c);}
      const out=[];
      for(const rows of groups.values()) {
        rows.sort((a,b)=>a.t-b.t);
        const timed=rows.filter(c=>c.cooldown_ms),aimed=rows.filter(c=>c.target);
        const kind=timed.length||aimed.length?'skill':'proc',pick=timed.length?timed:aimed.length?aimed:rows;
        pick.forEach((c,i)=>{if(i===0||c.t-pick[i-1].t>0.25)out.push({...c,kind});});
      }
      return out.sort((a,b)=>a.t-b.t);
    }
    function castTimeline(d, rotation) {
      const players=new Set((doc.players || []).map(p=>p.id));
      const shown=presses((d.segment.casts || []).filter(c=>players.has(c.source) && (!state.actor || c.source===state.actor))).filter(c=>!state.hideProcs || c.kind==='skill');
      const ids=[...new Set(rotation.totals.map(r=>r.source))].filter(id=>!state.actor || id===state.actor);
      if(!ids.length)return '';
      const start=Math.min(0,...shown.map(c=>c.t)),end=Math.max(d.segment.duration,...shown.map(c=>c.t)),span=Math.max(1,end-start);
      const width=Math.round(Math.max(900,Math.min(24000,span*36)));   // ~36 px a second: room for 2 presses a second per row
      const x=t=>(t-start)*(width-20)/span;
      const lanes=ids.map(id=>{
        const occupied=[-100,-100,-100];let marks='',omitted=0;
        for(const c of shown.filter(c=>c.source===id)) {
          const left=x(c.t),lane=occupied.findIndex(last=>left>=last+17);
          if(lane<0){omitted++;continue;}
          occupied[lane]=left;
          const y=4+lane*19,fill=c.kind==='proc'?'#8a93a6':color(d.r[id]?.class),icon=skillSource(c.skill_id);
          const detail=esc([signedClock(c.t),c.skill || c.skill_id,c.target?'→ '+label(d.r[c.target]):'',c.cooldown_ms?'cooldown '+cooldownText(c.cooldown_ms):'',c.cast_ms!=null?'cast '+c.cast_ms+' ms':'',c.kind==='proc'?'proc or passive':''].filter(Boolean).join(' · '));
          marks+=`<g class="cr-marker" tabindex="0" aria-label="${detail}"><title>${detail}</title><rect x="${left}" y="${y}" width="16" height="16" rx="2" fill="${fill}" opacity=".45"/>${icon?`<image href="${esc(icon)}" x="${left+1}" y="${y+1}" width="14" height="14" pointer-events="none"/>`:''}${c.cast_ms!=null?`<path d="M${left} ${y+17}h${Math.max(2,c.cast_ms/1000*(width-20)/span)}" stroke="${fill}" stroke-width="2"/>`:''}</g>`;
        }
        return `<div class="cr-lane" style="grid-template-columns:180px ${width}px"><div class="cr-lane-name" style="color:${color(d.r[id]?.class)}">${actorHTML(d.r[id])}${omitted?`<span class="small muted"> ${omitted} not drawn (overlap)</span>`:''}</div><svg class="cr-track" style="width:${width}px;height:64px" viewBox="0 0 ${width} 64" role="img" aria-label="${esc(label(d.r[id]))} casts">${marks||'<text x="12" y="25" fill="currentColor" font-size="12">No casts recorded</text>'}</svg></div>`;
      }).join('');
      const tick=span<=120?5:span<=600?10:30;
      let ticks='';for(let t=Math.ceil(start/tick)*tick;t<=end;t+=tick){const px=x(t);ticks+=`<path d="M${px} 18V30" stroke="currentColor" opacity=".6"/><text x="${Math.max(18,Math.min(width-18,px))}" y="13" text-anchor="middle" fill="currentColor" font-size="11">${signedClock(t).replace(/\.\d+$/,'')}</text>`;}
      return `<h4>Cast timeline</h4><p class="small muted">Each skill press across the fight; hover a cast for its time, target and cooldown. The line under a cast is how long it locked the caster, recorded for the player who made the recording only. Casts before the pull show at negative times.</p><label class="small"><input type="checkbox" data-control="hideProcs" ${state.hideProcs?'checked':''}> Hide procs and passive effects</label><div class="cr-timeline"><div class="cr-lane cr-time-axis" style="grid-template-columns:180px ${width}px"><div></div><svg class="cr-track cr-time-axis" style="width:${width}px;height:32px" viewBox="0 0 ${width} 32" aria-hidden="true">${ticks}</svg></div>${lanes}</div>`;
    }
    function gaugeChart(d, boss) {
      const rows=(d.segment.gauge || []).filter(g=>g.entity===boss.entity).sort((a,b)=>a.t-b.t);
      if(rows.length<2)return '';
      const duration=Math.max(1,d.segment.duration),W=1000,H=110,px=t=>Math.max(0,Math.min(W,t*W/duration)),py=g=>H-4-(H-8)*Math.max(0,Math.min(1,g.current/(g.max||1)));
      const points=rows.map(g=>`${px(g.t).toFixed(1)},${py(g).toFixed(1)}`).join(' ');
      const shade=boss.breaks.map(b=>`<rect x="${px(b.t).toFixed(1)}" y="0" width="${Math.max(2,px(b.end)-px(b.t)).toFixed(1)}" height="${H}" fill="#f0c36a" opacity=".22"><title>Broken ${signedClock(b.t)} → ${signedClock(b.end)} (${b.seconds.toFixed(1)}s)</title></rect>`).join('');
      return `<svg class="cr-gauge" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Break gauge over the fight">${shade}<polyline points="${points}" fill="none" stroke="#e3b35a" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
    }
    function actionsHTML(d) {
      const s=doc.encounter_insights?.segments?.find(s=>s.segment===state.segment)?.actions,seg=d.segment;
      const recorded=(seg.casts || []).length+(seg.effects || []).length+(seg.gauge || []).length+(seg.resources || []).length+(seg.npc_casts || []).length;
      if((doc.meta?.reconstruction?.omitted_actions || []).length)return '<p class="small muted">This combined review leaves out the casts, buffs and break gauge: across these parts they exceed what one review can hold. Open a single part to see them.</p>';
      if(!s || !recorded)return `<p class="small muted">Casts, buffs and debuffs, crowd control and the break gauge are not recorded for this encounter. The live meter records them since 0.2.306${s?'':'; reopen the file with the updated app, or update the sharing server, to see them'}.</p>`;
      const tabs=[["rotation","Rotation"],["effects","Buffs & debuffs"],["cc","Crowd control"],["stagger","Break gauge"],["boss","Boss casts"],["contribution","Buff contribution"],["","Hide"]];
      const mine=id=>!state.actor || id===state.actor;
      const omitted=Object.entries(s.omitted_actions || {}).filter(([,n])=>n).map(([key,n])=>`${number(n)} ${key.replaceAll('_',' ')} rows`).join(', ');
      let body='';
      if(state.actions==='rotation') {
        const r=s.rotation,dodges=new Map(r.dodges.map(x=>[x.source,x.count]));
        body=`<p class="small muted">Casts are the game's own cast records. Cooldown usage compares the casts made with how many fit between the first cast and the end of the fight at the cooldown the game sent (cooldown reduction included). It does not judge priorities or account for mechanics that stop you casting.</p>
          ${table(['Player','Skill casts','Casts per minute','Procs and passives','Dodges'],r.totals.filter(t=>mine(t.source)).map(t=>`<tr><td>${actorHTML(d.r[t.source])}</td><td>${number(t.casts)}</td><td>${t.per_minute.toFixed(1)}</td><td>${number(t.procs)}</td><td>${number(dodges.get(t.source)||0)}</td></tr>`))}
          ${(s.mp || []).some(m=>mine(m.entity))?`<h4>MP</h4><p class="small muted">The recording player's MP: the game sends no one else's. Spent is the sum of every drop (mostly skill costs); restored is regeneration and MP-restoring skills. Below 20% is the time under a fifth of the maximum.</p>${table(['Player','Start → end','Lowest','Maximum','Spent','Spent per minute','Restored','Below 20%'],s.mp.filter(m=>mine(m.entity)).map(m=>`<tr><td>${actorHTML(d.r[m.entity])}</td><td>${number(m.start)} → ${number(m.end)}</td><td>${number(m.lowest)}</td><td>${number(m.max)}${m.max_from_record?'':' <span class="small muted">highest reading</span>'}</td><td>${number(m.spent)}</td><td>${m.spent_per_minute==null?'—':number(m.spent_per_minute)}</td><td>${number(m.restored)}</td><td>${m.seconds_low.toFixed(1)}s <span class="small muted">${pct(m.low_pct)}</span></td></tr>`))}`:''}
          ${castTimeline(d,r)}
          <h4>Skills</h4>${table(['Player','Skill','Casts','Average gap','Cooldown','Cooldown usage','Cast time','First → last'],r.skills.filter(k=>mine(k.source) && (!state.hideProcs || k.kind==='skill')).map(k=>`<tr><td>${actorHTML(d.r[k.source])}</td><td>${skillCell(k)}${k.kind==='proc'?' <span class="small muted">proc</span>':''}</td><td>${number(k.casts)}</td><td>${k.average_gap==null?'—':k.average_gap.toFixed(1)+'s'}</td><td>${cooldownText(k.cooldown_ms)}</td><td>${k.possible?`${number(k.casts)} of ${number(k.possible)} · ${pct(k.usage_pct)}`:'—'}</td><td>${k.cast_ms==null?'—':number(k.cast_ms)+' ms'}</td><td>${signedClock(k.first)} → ${signedClock(k.last)}</td></tr>`))}
          ${r.chains.length?`<h4>Chain skills</h4><p class="small muted">How often the chain skill followed while its window was open (recorded for the player who made the recording).</p>${table(['Player','Chain skill','Windows opened','Followed','Follow rate'],r.chains.filter(c=>mine(c.player)).map(c=>`<tr><td>${actorHTML(d.r[c.player])}</td><td>${skillCell({skill:c.next,skill_id:c.next_id})}</td><td>${number(c.opened)}</td><td>${number(c.used)}</td><td>${pct(c.used_pct)}</td></tr>`))}`:''}`;
      } else if(state.actions==='effects') {
        const sources=x=>x.sources.map(v=>v.source?`${actorHTML(d.r[v.source])} ×${v.applications}`:`Not recorded ×${v.applications}`).join(' ');
        const rows=list=>list.filter(x=>mine(x.target) || x.sources.some(v=>mine(v.source))).map(x=>`<tr><td>${actorHTML(d.r[x.target])}${x.boss?' <span class="small muted">boss</span>':''}</td><td>${skillCell(x)}</td><td>${pct(x.uptime_pct)}</td><td>${x.seconds.toFixed(1)}s</td><td>${number(x.applications)}</td><td>${sources(x)}</td></tr>`);
        body=`<p class="small muted">Windows run from each effect's application to its removal, or to its stated duration when no removal was recorded. Overlapping applications on the same target count once. Uptime is over the whole encounter.</p>
          <h4>Buffs on the party</h4>${table(['Recipient','Buff','Uptime','Time','Applications','Given by'],rows(s.buffs))}
          <h4>Debuffs on enemies</h4>${table(['Enemy','Debuff','Uptime','Time','Applications','Applied by'],rows(s.debuffs))}
          <h4>Enemy effects on the party</h4>${table(['Recipient','Effect','Uptime','Time','Applications','Source'],rows(s.incoming))}`;
      } else if(state.actions==='cc') {
        body=`<p class="small muted">Crowd control your party landed on enemies. The state comes from the skill's description; how long it held comes from the effect's own records. Removed early means the game ended the effect before its duration (an immunity, a break or a phase change, not told apart).</p>
          ${table(['Player','State','Landed (with re-applications)','Total held','Hard crowd control','Removed early'],s.crowd_control_by_source.filter(c=>mine(c.source)).map(c=>`<tr><td>${actorHTML(d.r[c.source])}</td><td>${esc(c.state)}</td><td>${number(c.landed)}</td><td>${c.seconds.toFixed(1)}s</td><td>${number(c.hard)}</td><td>${number(c.broken_early)}</td></tr>`))}
          <h4>Each application</h4>${table(['Time','Player','Target','Skill','State','Held','Ended'],s.crowd_control.filter(c=>mine(c.source)).map(c=>`<tr><td>${signedClock(c.t)}</td><td>${actorHTML(d.r[c.source])}</td><td>${actorHTML(d.r[c.target])}</td><td>${skillCell(c)}</td><td>${esc(c.state)}${c.hard?'':' <span class="small muted">soft</span>'}</td><td>${c.seconds.toFixed(2)}s${c.refreshes?` <span class="small muted">re-applied ${number(c.refreshes)}×</span>`:''}</td><td>${esc(endedText[c.ended] || (c.end>=d.segment.duration-0.01?'Active at the end':'No removal recorded'))}</td></tr>`))}`;
      } else if(state.actions==='contribution') {
        // An estimate built from the recorded effect windows (encounter_insights.contribution); it is
        // never used for rankings or parses.
        const c=doc.encounter_insights?.segments?.find(x=>x.segment===state.segment)?.contribution;
        const per=v=>number(v/Math.max(.001,d.dpsDuration));
        const who=id=>id?(d.r[id]?actorHTML(d.r[id]):'Not in the roster'):'Not recorded';
        const basis={profile:'Official profile',effect:'Effect record (inferred)',typical:'Typical top player (assumed)',fixed:'Same at every level'};
        const kind={aura:'Damage Boost aura',block:'Damage Boost on block',tolerance:'Enemy Damage Tolerance cut'};
        const signed=v=>(v>0?'+':'')+v.toFixed(1)+'%';
        body=(doc.encounter_insights?.version || 0)<4?'<p class="small muted">The buff contribution needs analyzer 0.2.307 or later: reopen the file with the updated app, or update the sharing server.</p>':
          !c?'<p class="small muted">No credited buff was recorded in this encounter, or it is PvP (PvP boosts and tolerances differ), so there is nothing to estimate.</p>':
          `<p class="small muted"><b>An estimate, not a record. It is not used for rankings or parses until it has been checked against real data.</b> <i>From others' buffs</i> is the part of a player's hits that came from other players' damage buffs and debuffs; <i>Added to others</i> is what their own buffs added to other players' hits. Buff-adjusted DPS takes out what others gave; rDPS also credits what the player gave. A buff's size comes from its caster's skill level (the official profile, else the effect record, else the typical top player's). A +X% boost's share of a hit assumes the player's other damage boosts are the typical build's and a 30% boss Damage Tolerance (10% otherwise). Defense cuts and Combat Speed buffs are not credited, and pet hits are not adjusted. Per-second values use the damage table's active clock.</p>
          ${table(['Player','DPS',"From others' buffs",'Buff-adjusted DPS','Added to others','rDPS'],c.players.filter(p=>mine(p.player)).map(p=>`<tr><td>${who(p.player)}</td><td>${per(p.damage)}</td><td>−${per(p.received)} <span class="small muted">${pct(p.received_pct)}</span></td><td>${per(p.adjusted_damage)}</td><td>+${per(p.given)}</td><td>${per(p.contribution_damage)}</td></tr>`))}
          ${c.unlisted_source_damage?`<p class="small muted">${number(c.unlisted_source_damage)} of the damage added came from casters who are not in the roster.</p>`:''}
          <h4>Who added what</h4>${table(['Given by','Buff','To','Damage added','Per second'],c.given.filter(g=>mine(g.source) || mine(g.recipient)).map(g=>`<tr><td>${who(g.source)}</td><td>${skillCell(g)}</td><td>${who(g.recipient)}</td><td>${number(g.damage)}</td><td>${per(g.damage)}</td></tr>`))}
          <h4>Credited buffs</h4>${table(['Caster','Buff','Kind','PvE value','Level','Level from','Windows'],c.buffs.map(b=>`<tr><td>${who(b.source)}</td><td>${skillCell(b)}</td><td>${esc(kind[b.group] || b.group)}</td><td>${b.value_pct.toFixed(1)}%</td><td>${b.level ?? '—'}</td><td>${esc(basis[b.basis] || b.basis)}</td><td>${number(b.windows)}</td></tr>`))}
          ${c.checks.length?`<h4>Check against this fight's hits</h4><p class="small muted">The same player's same-skill plain hits (no critical, double, perfect or periodic damage, outside breaks) with only that buff group up, against none up. One fight rarely has enough hits without the buff to settle it; <code>python -m aion2calc calibrate --buffs</code> pools many fights.</p>${table(['Buffs','Measured gain','Estimated gain','Hits with / without','Skills compared'],c.checks.map(x=>`<tr><td>${esc(kind[x.group] || x.group)}</td><td>${signed(x.measured_pct)}</td><td>${signed(x.estimated_pct)}</td><td>${number(x.hits_on)} / ${number(x.hits_off)}</td><td>${number(x.pairs)}</td></tr>`))}`:''}`;
      } else if(state.actions==='boss') {
        const b=s.boss_casts || {skills:[],timeline:[]};
        body=`<p class="small muted">The skills bosses cast, from the game's own cast records (recorded since 0.2.307 for catalog bosses). Most boss skills have no name in the bundled tables and show their ID. <i>Aimed at</i> is the player a cast targeted; area skills often name none.</p>`+
          (b.skills.length?`${table(['Boss','Skill','Casts','First → last','Aimed at'],b.skills.map(k=>`<tr><td>${actorHTML(d.r[k.source])}</td><td>${skillCell(k)}</td><td>${number(k.casts)}</td><td>${signedClock(k.first)} → ${signedClock(k.last)}</td><td>${k.targets.map(x=>`${actorHTML(d.r[x.target])} ×${x.casts}`).join(' ') || '—'}</td></tr>`))}
          <h4>Casts in order</h4><p class="small muted">Quick repeats of one skill at one target (a channelled skill sends a cast every few hundredths of a second) are one row.</p>${table(['Time','Boss','Skill','Casts','Aimed at'],b.timeline.filter(c=>!state.actor || c.target===state.actor).map(c=>`<tr><td>${signedClock(c.t)}${c.end!=null?` → ${signedClock(c.end)}`:''}</td><td>${actorHTML(d.r[c.source])}</td><td>${skillCell(c)}</td><td>${c.casts>1?'×'+number(c.casts):''}</td><td>${c.target?actorHTML(d.r[c.target]):'—'}</td></tr>`))}${b.omitted_timeline?`<p class="small muted">${number(b.omitted_timeline)} later rows are not listed.</p>`:''}`:'<p>No boss casts were recorded in this encounter.</p>');
      } else if(state.actions==='stagger') {
        body=`<p class="small muted">The break gauge is the game's own reading. A drop belongs to the hits on that enemy in the same read; when several hits share one, it is split by each skill's listed Stagger Gauge Damage (from the skill descriptions), else by what that skill drained alone. A break runs from the gauge emptying to it refilling.</p>`+
          (s.stagger.length?s.stagger.map(b=>`<h4>${esc(label(d.r[b.entity]))}${b.boss?'':' <span class="small muted">elite</span>'}</h4><p class="small">Gauge ${number(b.max)} · ${number(b.readings)} readings · ${number(b.drained)} drained${b.unattributed?` (${number(b.unattributed)} with no matching hit)`:''} · ${b.breaks.length} break${b.breaks.length===1?'':'s'}${b.breaks.length?': '+b.breaks.map(x=>`${signedClock(x.t)} for ${x.seconds.toFixed(1)}s`).join(', '):''}</p>${gaugeChart(d,b)}
            ${table(['Player','Gauge drained','Share','Damage during breaks'],b.players.filter(p=>mine(p.player)).map(p=>`<tr><td>${actorHTML(d.r[p.player])}</td><td>${number(p.amount)}</td><td>${pct(p.share_pct)}</td><td>${number(p.break_damage)}</td></tr>`))}`).join(''):'<p>No break-gauge readings were recorded in this encounter (only bosses and elites carry one).</p>');
      }
      return `<div class="cr-actions"><h3>Casts, buffs and break gauge</h3><div class="cr-tabs">${tabs.map(([v,l])=>`<button class="btn small ${state.actions===v?'primary':''}" data-actions="${v}">${l}</button>`).join('')}</div>${state.actions?body:''}${state.actions&&omitted?`<p class="small muted">Row limits omitted ${esc(omitted)}.</p>`:''}</div>`;
    }
    function recapsHTML(d) {
      const analysis=doc.death_analysis;
      if(!analysis)return '<p class="note">Death recaps are unavailable in this older view. Reopen the local file with the updated app, or update the sharing server.</p>';
      const shown=(analysis.recaps || []).map((r,i)=>({...r,index:i})).filter(r=>r.segment===state.segment && (!state.actor || r.player===state.actor));
      const selected=shown.find(r=>r.index===state.recap) || shown[0];
      const hp=x=>x?number(x.current)+(x.max?' / '+number(x.max):' (maximum unavailable)'):'Unavailable';
      const last=x=>x?`${actorHTML(d.r[x.source])} · ${esc(x.skill || x.skill_id || 'Unknown ability')} · ${number(x.amount)} at ${x.t.toFixed(3)}s`:'Unavailable';
      return `<h3>Player death recaps</h3><p class="small muted">${esc(analysis.note)} Recaps include all recorded incoming sources for the selected player; enemy/metric/pet filters do not remove their context. ${analysis.omitted_recaps?`${analysis.omitted_recaps} recaps omitted by the 200-recap session limit.`:''}</p>${table(['Player','Death marker','Window','Recorded incoming damage','Recorded received healing','Latest recorded HP','Last observed incoming hit'],shown.map(r=>`<tr><td>${actorHTML(d.r[r.player])}<br><button class="btn small" data-recap="${r.index}">Open recap</button></td><td>${r.t.toFixed(3)}s</td><td>${r.window_seconds.toFixed(1)}s${r.short_window?' (short / split boundary)':''}</td><td>${number(r.incoming_damage)}</td><td>${number(r.received_healing)}</td><td>${hp(r.last_hp)}${r.last_hp?` at ${r.last_hp.t.toFixed(3)}s`:''}</td><td>${last(r.last_incoming_hit)}</td></tr>`))}${selected?`<h4>${esc(label(d.r[selected.player]))} · death marker at ${selected.t.toFixed(3)}s</h4><p class="small muted">Negative times are seconds before this marker. Equal timestamps do not establish ordering. Showing the last 200 effects and 200 HP samples; ${selected.omitted_events} effects and ${selected.omitted_health} HP samples omitted. Window totals include omitted effects.</p>${table(['Relative time','Effect','Source','Ability','Recorded amount'],selected.events.map(e=>`<tr><td>${(e.t-selected.t).toFixed(3)}s</td><td>${esc(e.kind)}</td><td>${actorHTML(d.r[e.source])}</td><td>${esc(e.skill || e.skill_id || 'Unknown')}</td><td>${number(e.amount)}</td></tr>`))}${table(['Relative time','Observed HP'],selected.health.map(s=>`<tr><td>${(s.t-selected.t).toFixed(3)}s</td><td>${hp(s)}</td></tr>`))}`:analysis.omitted_recaps?'<p>No recap was retained for this selection; the session limit may have omitted it. Use Events to inspect recorded markers.</p>':'<p>No explicit player death markers were recorded for this selection; this does not prove survival.</p>'}`;
    }
    function ranksHTML(d) {
      if(!options.rankings)return "";
      if(!ranks)return '<div class="small muted">Loading comparisons with public logs…</div>';
      if(ranks.error)return `<div class="small muted">${esc(ranks.error)}</div>`;
      // A null scope was never keyed; distinguish "no verified official profile" (so this
      // character's home server/region is unknown and can't be matched) from a plain
      // missing comparison. A resolved profile with too few peers instead returns an
      // object carrying reasons (e.g. "Insufficient samples"), handled below — that is the
      // "no eligible cohort" case, as opposed to the "no matched profile" case here.
      const unrankedWhy=(ranks.quality && ranks.quality.eligible===false)?(ranks.quality.messages || []).join(' '):'';
      const values=(x,scope,entry,context)=>{
        if(!x){
          if(context==='run'){
            // A timed run one scope cannot place says which scope and why, not "Not a timed run".
            if(ranks.run_detail?.speed_eligible){
              if(scope==='server')
                return 'Unavailable — no verified home world for the party or the recording player, so the run has no Server cohort. Region and World still rank it.';
              if(scope==='region')
                return 'Unavailable — the run’s region is unknown, so only World ranks it.';
              return 'Unavailable — no comparable public runs yet.';
            }
            const why=(ranks.run_detail?.speed_reasons || []).join(' ');
            return `Not a timed run — run speed is ranked only for a complete, cleanly captured instance clear (entry to final boss). ${why}`.trim();
          }
          if(context==='at_upload' && !(entry && entry.uploaded_at) && !(ranks.players || []).some(p=>p.uploaded_at))
            return 'Not uploaded yet — at-upload standings exist only for recordings shared with the log server.';
          if(unrankedWhy)
            return `Unranked — ${unrankedWhy}`;
          if((scope==='server'||scope==='region') && entry && 'character_server' in entry && !entry.character_server)
            return `Unavailable — no verified official profile for this character, so its home ${scope} can’t be matched. World still compares globally.`;
          if((scope==='server'||scope==='region') && entry && !('character_server' in entry))
            return `Unavailable — this player’s home ${scope} is unknown (no server or class on the recording), so only World can compare.`;
          if(scope==='world')
            return 'Unavailable — no comparable public cohort yet. World matching groups logs by the encounter’s boss, game version, difficulty and party size; either this recording lacks that metadata or too few public logs share it so far.';
          return 'Unavailable — no eligible matched comparison yet. Check capture quality and encounter metadata above.';
        }
        return `<span title="${esc((x.reasons || []).join(' '))}">${x.rank===null?'Rank unavailable':`#${x.rank} / ${x.count}`}${x.provisional?' (provisional)':''}<br>${x.percentile===null || x.percentile===undefined?'Percentile unavailable':x.percentile.toFixed(1)+' percentile'}${x.public_samples!==undefined?` · ${x.public_samples} public samples · ${x.identities} distinct identities`:''}${x.basis==='recording_player'?`<br>On the recording player’s world (${esc(x.world)}): the party spans several worlds.`:''}${x.reasons?.length?'<br>'+esc(x.reasons.join(' ')):''}</span>`;
      };
      const scopes=(x,context)=>['server','region','world'].map(s=>`${s[0].toUpperCase()+s.slice(1)}: ${values(x?.[s],s,x,context)}`).join('<br>');
      const unranked=unrankedWhy?`<p class="note">This encounter is <b>unranked</b>: ${esc(unrankedWhy)} Fix what you can on the next recording (start the meter before entering the instance, keep the party roster, let the boss be seen at full health) — the standings below stay unavailable until a recording of this fight is eligible.</p>`:'';
      const noPlayers=!(ranks.players || []).length && !unrankedWhy?`<p class="note">No player standings: ${esc(ranks.note || 'the encounter metadata (boss, game version, difficulty, encounter type) is incomplete.')}</p>`:'';
      return `<h3>Matched public comparisons</h3><p class="small muted">${esc(ranks.note || '')} ${esc(ranks.cohort_note || '')}</p>${unranked}${noPlayers}${table(['Player · party size','Current standings (same game version)','At upload (reconstructed)'],(ranks.players || []).map(p=>`<tr><td>${esc(p.name)} · ${p.party_size || 'Unknown'} players${p.uploaded_at?`<br>Uploaded ${esc(new Date(p.uploaded_at*1000).toLocaleString())}`:''}</td><td>${scopes(p,'current')}</td><td>${scopes(p.at_upload,'at_upload')}</td></tr>`))}<h4>Run speed · lower elapsed time wins</h4>${table(['Current standings (same game version)','At upload (reconstructed)'],[`<tr><td>${scopes(ranks.run,'run')}</td><td>${scopes(ranks.run_at_upload,'run')}</td></tr>`])}`;
    }
    const seconds=x=>x===null || x===undefined?'Unavailable':`${Math.floor(x/60)}:${(x%60).toFixed(1).padStart(4,'0')}`;
    function runsHTML(d) {
      const analysis=doc.run_analysis, all=analysis?.runs || (ranks?.run_detail?[ranks.run_detail]:[]);
      if(!all.length)return '<p class="small muted">Run timing and progression are unavailable in this older recording.</p>';
      const shown=all.filter(r=>!state.run || r.id===state.run), current=all.find(r=>r.id===(d.segment.run_id || 'legacy'));
      // Drop minibosses a stale server classification may have counted as bosses.
      const progression=(current?.progression || []).filter(p=>!bossKeyIsMiniboss(p.boss_key));
      const battempts=(current?.attempts || []).filter(a=>!bossKeyIsMiniboss(a.boss_key));
      if(String(d.segment.encounter_type || doc.meta?.encounter_type || '').startsWith('pvp_'))return `<details class="note"><summary>PvP recorded timing</summary><p class="small muted">These intervals contain observed combat effects. They are not verified rounds or complete matches. Match score, round boundaries and player death coverage remain unverified.</p>${table(['Run','Recorded span','Recorded combat','Gaps / downtime'],shown.map(r=>`<tr><td>${esc(r.id)}</td><td>${seconds(r.recorded_span_seconds)}</td><td>${seconds(r.combat_seconds)}</td><td>${seconds(r.downtime_seconds)}</td></tr>`))}</details>`;
      return `<details class="note"><summary>Run timing and boss progression</summary><p class="small muted">${esc(analysis?.note || '')}</p>${table(['Run','Recorded span','Entry → finish','Recorded combat','Gaps / downtime','Speed status'],shown.map(r=>`<tr><td>${esc(r.id)}</td><td>${seconds(r.recorded_span_seconds)}</td><td>${seconds(r.elapsed_seconds)}</td><td>${seconds(r.combat_seconds)}</td><td>${seconds(r.downtime_seconds)}</td><td>${r.speed_eligible?'Eligible':esc((r.speed_reasons || []).join(' '))}${r.stitched?.parts?.length?` <span class="muted small">(stitched across recording parts ${esc(String(r.stitched.parts[0]))}–${esc(String(r.stitched.parts[r.stitched.parts.length-1]))})</span>`:''}</td></tr>`))}
      ${current && progression.length?`<h4>Run ${esc(current.id)} · boss attempts</h4>${table(['Boss','Recorded attempts','Kills','Observed wipes','Unknown','Attempts to first recorded clear','Best observed wipe HP','Wipe → next pull'],progression.map(p=>`<tr><td>${esc(p.boss)}</td><td>${p.attempts}</td><td>${p.kills}</td><td>${p.wipes}</td><td>${p.unknown}</td><td>${p.attempts_to_first_clear??'Unavailable'}</td><td>${p.best_wipe_hp_pct===null?'Unavailable':p.best_wipe_hp_pct.toFixed(1)+'%'}</td><td>${(p.wipe_recovery_seconds || []).map(seconds).join(', ') || 'Unavailable'}</td></tr>`))}${table(['Attempt','Boss','Outcome','Recorded span','Lowest observed HP','Encounters'],battempts.map(a=>`<tr><td>${a.attempt}</td><td>${esc(a.boss)}</td><td>${esc(a.outcome)}</td><td>${seconds(a.recorded_seconds)}</td><td>${a.best_remaining_hp_pct===null?'Unavailable':a.best_remaining_hp_pct.toFixed(1)+'%'}</td><td>${a.segments.map(i=>`<button class="btn small" data-attempt-segment="${i}">${esc(doc.segments[i]?.label || i+1)}</button>`).join(' ')}</td></tr>`))}`:''}</details>`;
    }
    function combinedHTML() {
      const m=doc.meta?.reconstruction;if(!m)return '';
      const summary=doc.recording_summary?.[state.mode || 'all'];
      return `<section class="note"><h3>Combined recording review · unranked</h3><p>${esc(m.note)}</p>
        <div class="row">${sourceView?'<button class="btn small" data-source-back>Back to source part</button>':''}<button class="btn small" data-combined-export>Export combined review</button><span data-combined-status role="status"></span></div>
        <p class="small">${m.sources.map((r,i)=>`<button class="btn small" data-source-part="${i}">Part ${esc(r.part)}</button>`).join(' ')} · ${m.sources.length} source parts. Each encounter below retains its source boundaries.</p>
        ${doc.recording_runs?`<h3>Run timing across selected parts</h3>${table(['Run','Encounters','Recorded span','Entry → finish','Evidence'],doc.recording_runs.runs.filter(r=>!state.mode || r.mode===state.mode).map((r,i)=>`<tr><td>${i+1}</td><td>${r.encounters}</td><td>${r.recorded_span==null?'Unavailable':seconds(r.recorded_span)}</td><td>${r.entry_to_finish==null?'Unavailable':seconds(r.entry_to_finish)}</td><td>${esc(r.status)}</td></tr>`))}<p class="small muted">${esc(doc.recording_runs.note)} ${doc.recording_runs.legacy_encounters || 0} source encounters have no run provenance and keep their original boundaries.</p>`:''}
        ${summary?`<p class="small">${summary.encounters} encounters · ${seconds(summary.active_seconds)} active outgoing seconds · ${seconds(summary.recorded_seconds)} recorded combat span. DPS uses the shared active clock; HPS and damage taken/s use recorded spans.</p>${table(['Player','Damage','DPS','Healing','HPS','Damage taken','Taken/s'],summary.players.map(p=>`<tr><td>${esc(label(p))}</td><td>${number(p.damage)}</td><td>${number(p.dps)}</td><td>${number(p.healing)}</td><td>${number(p.hps)}</td><td>${number(p.taken)}</td><td>${number(p.dtps)}</td></tr>`))}`:''}</section>`;
    }
    function bindCombined() {
      const back=root.querySelector('[data-source-back]');if(back)back.onclick=()=>{rankRequest++;profileRequest++;doc=sourceView.doc;options=sourceView.options;state=sourceView.state;sourceView=null;ranks=null;previews.clear();render();requestRanks();};
      const exp=root.querySelector('[data-combined-export]');if(exp)exp.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(doc)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='combined-recording.a2log.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);root.querySelector('[data-combined-status]').textContent='Combined review download started. Upload the original parts to share them.';};
      root.querySelectorAll('[data-source-part]').forEach(button=>{button.disabled=!options.openArchivePart;button.onclick=()=>{const row=doc.meta.reconstruction.sources[Number(button.dataset.sourcePart)];if(row && options.openArchivePart)options.openArchivePart(row,state.mode);};});
    }
    function archiveHTML() {
      const archive=doc.meta?.archive;if(!archive)return '';
      const note=`<p class="small muted">Archive ${esc(archive.id)} · Part ${esc(archive.part)}. Each part has separate totals and quality. Entry evidence may be in an earlier part; a storage boundary keeps this part incomplete.</p>`;
      if(!options.archiveParts || !options.openArchivePart || options.live)return `<div class="note">${note}</div>`;
      const rows=archivePage?.rows || [];
      const listing=archivePage?table(['Part','Recording','Recorded span','Encounters','Retained records / continuity','Saved state',''],rows.map((row,index)=>{
        const key=row.file || row.id,current=key===options.archiveCurrent,part=row.archive?.part ?? row.part;
        const c=row.archive?.continuity, evidence=row.continuity_status;
        const range=c?`${number(c.first_sequence)}–${number(c.last_sequence)} · ${number(c.retained_records)} records`:'Range not recorded';
        const saved=row.unfinished?'Recording checkpoint':(row.archive?.closed ?? row.closed)?'Storage boundary saved':'Saved part';
        return `<tr><td>${esc(part)}</td><td>${esc(row.title || key)}</td><td>${seconds(row.duration)}</td><td>${esc(row.segments)}</td><td title="${esc(evidence?.note || 'Submitted metadata only')}">${esc(range)}<br>${esc(evidence?.label || 'Continuity metadata not recorded')}</td><td>${esc(saved)}</td><td>${current?'Current part':`<button class="btn small" data-archive-open="${index}">Open part</button>`}</td></tr>`;
      }))+'<p class="small muted">'+esc(archivePage.note || 'Parts saved on this computer. Matching recording IDs do not establish complete or continuous capture.')+'</p>':'';
      return `<details class="note" data-archive-parts ${archiveOpen?'open':''}><summary>Other parts of this recording</summary>${note}<p class="small muted">Part numbers can have gaps or duplicates. Ranges count retained decoded effects before view filtering, not packets. Counter continuity cannot rule out lost packets or recording downtime. The list keeps source reports separate. Combined review checks submitted links but cannot restore missing events or verify matching archive IDs.</p>${listing}${options.reconstructArchive?`<div class="row"><label>First part <input type="number" min="1" step="1" data-combine-first value="${archiveFirst}" style="width:85px"></label><label>Last part <input type="number" min="2" step="1" data-combine-last value="${archiveLast}" style="width:85px"></label><button class="btn small" data-combine-parts ${archiveBusy?'disabled':''}>Review connected parts</button></div><p class="small muted">Choose 2–32 stopped parts, up to 64 MiB. Gaps, overlaps, duplicate parts and conflicting links block combining. Original encounters stay separate; combined review is unranked.</p>`:''}<p role="status">${archiveBusy?'Loading / checking recording parts…':esc(archiveError || (archivePage?`${rows.length} results on this page · ${archivePage.file_count} available parts`:''))}</p><div class="row"><button class="btn small" data-archive-load ${archiveBusy?'disabled':''}>${archivePage?'Refresh parts':'Find recording parts'}</button>${archivePage?`<button class="btn small" data-archive-prev ${archiveBusy || archiveOffset===0?'disabled':''}>Previous</button><button class="btn small" data-archive-next ${archiveBusy || !archivePage.has_more?'disabled':''}>Next</button>`:''}</div></details>`;
    }
    function bindArchive() {
      const details=root.querySelector('[data-archive-parts]');if(!details)return;
      const combine=root.querySelector('[data-combine-parts]');if(combine)combine.onclick=async()=>{
        archiveFirst=Number(root.querySelector('[data-combine-first]').value);archiveLast=Number(root.querySelector('[data-combine-last]').value);
        if(!Number.isSafeInteger(archiveFirst)||!Number.isSafeInteger(archiveLast)||archiveFirst<1||archiveLast-archiveFirst<1||archiveLast-archiveFirst>=32){archiveError='Choose 2–32 consecutive part numbers.';render();return;}
        const request=++archiveRequest;archiveBusy=true;archiveError='';render();
        try{
          const next=await options.reconstructArchive(archiveFirst,archiveLast);
          if(disposed || request!==archiveRequest)return;
          if(!next?.meta?.reconstruction || !next.recording_summary || !Array.isArray(next.segments))throw Error('The server did not return a combined recording review. Update the server if this feature is unavailable.');
          applyCombined(next,archiveFirst,archiveLast);
        }catch(e){if(!disposed && request===archiveRequest)archiveError=e.message;}
        finally{if(!disposed && request===archiveRequest){archiveBusy=false;if(root.isConnected)render();}}
      };
      details.ontoggle=()=>{archiveOpen=details.open;};
      const load=async offset=>{
        const request=++archiveRequest;archiveBusy=true;archiveError='';archiveOpen=true;render();
        try {
          const result=await options.archiveParts(offset,25,doc.meta.archive.id);
          if(disposed || request!==archiveRequest)return;
          if(!result || !Array.isArray(result.rows))throw Error('The server did not return a recording-part list.');
          archivePage=result;archiveOffset=offset;
        }catch(e){if(!disposed && request===archiveRequest)archiveError=e.message;}
        finally{if(!disposed && request===archiveRequest){archiveBusy=false;if(root.isConnected)render();}}
      };
      const button=root.querySelector('[data-archive-load]');if(button)button.onclick=()=>load(archiveOffset);
      const previous=root.querySelector('[data-archive-prev]');if(previous)previous.onclick=()=>load(Math.max(0,archiveOffset-25));
      const next=root.querySelector('[data-archive-next]');if(next)next.onclick=()=>load(archiveOffset+25);
      root.querySelectorAll('[data-archive-open]').forEach(button=>button.onclick=()=>{const row=archivePage?.rows[Number(button.dataset.archiveOpen)];if(row)options.openArchivePart(row,state.mode);});
    }
    function render() {
      if(replayFrame)cancelAnimationFrame(replayFrame);replayFrame=null;
      if(state.character && refs()[state.character]){root.innerHTML='<div data-profile>'+profileHTML()+'</div>';bindProfile();return;}
      if(!doc.segments.some(matchesMode)){root.innerHTML=combinedHTML()+archiveHTML()+'<p class="note">No encounters recorded for this combat mode.</p><button class="btn small" data-show-all>Show all recorded encounters</button>';bindArchive();bindCombined();root.querySelector('[data-show-all]').onclick=()=>{state.mode='';state.run='';render();requestRanks();};return;}
      if(!doc.segments[state.segment] || !matchesMode(doc.segments[state.segment])){state.segment=doc.segments.findIndex(matchesMode);state.run='';state.actor='';state.enemy='';ranks=null;}
      const d=data(),events=visibleEvents(d),duration=Math.max(1,d.segment.duration),metric=state.metric==="summary"?"damage":state.metric;
      const quality=ranks?.quality || d.segment.quality;
      const driver=quality?.driver_monitoring;
      const driverHTML=driver?`<p>Capture driver: ${driver.sampled?`${driver.partial?'partial coverage · ':''}${number(driver.pcap_received)} received · ${number(driver.pcap_dropped)} capture-buffer drops · ${number(driver.pcap_if_dropped)} interface/driver drops`:'unavailable / not recorded'}. ${esc(driver.note)}</p>`:'';
      const processing=quality?.capture_processing, processingCount=k=>processing?.[k]==null?'not recorded':number(processing[k]);
      const processingHTML=processing?`<p>Capture processing: ${processingCount('decoder_errors')} decoder failures · ${processingCount('recovered_frame_skips')} recovered frame-skips (skipped and continued; a few do not affect ranking) · ${processingCount('shutdown_discarded_payloads')} payloads discarded at shutdown · ${processingCount('shutdown_drained_payloads')} payloads decoded during shutdown. Legacy combined error/discard count: ${processingCount('capture_errors')} (overlaps these counters; do not add them). Successfully drained payloads are retained data, not capture loss.</p>`:'';
      // Log server 0.2.96: a run that rolled over between archive parts is rebuilt under the
      // continuation part (``stitched``; ``merged`` when the rollover cut this boss attempt in two),
      // the cut half points at the whole fight (``continued_in``), and other party members' uploads
      // of the same fight are listed (``shared_uploads``). Other parts / uploads open through the
      // host page's own navigation hook, the same one the recording-parts list uses.
      const partsLabel=p=>Array.isArray(p)&&p.length?`${p[0]}–${p[p.length-1]}`:'';
      const openOther=(log,label)=>options.openArchivePart&&log?`<button class="btn small" data-open-shared="${esc(log)}">${esc(label)}</button>`:esc(label);
      const stitchedHTML=()=>{
        const s=ranks?.stitched,c=ranks?.continued_in;let out='';
        if(s)out+=`<p>${s.merged?`This fight was cut by a storage rollover: its first ${seconds(Math.max(0,s.merged.duration-d.segment.duration))} are in the previous recording part${s.merged.previous?.log?' '+openOther(s.merged.previous.log,'Open previous part'):''}. Rankings use the whole fight — ${seconds(s.merged.duration)}, ${number(s.merged.damage)} damage.`:`Part of a run stitched across recording parts ${esc(partsLabel(s.parts))}: the instance entry was observed in the first part, so this part's fights can rank.`} ${esc(s.note || '')}</p>`;
        if(c)out+=`<p>This fight was cut by a storage rollover and continues in the next part of the recording${c.part?` (part ${esc(String(c.part))})`:''}, where the whole fight is indexed and ranked.${c.log?' '+openOther(c.log,'Open the whole fight'):''}</p>`;
        return out;
      };
      const sharedHTML=()=>{
        const list=ranks?.shared_uploads;
        if(Array.isArray(list) && list.length)return `<p>Also recorded by: ${list.map(u=>openOther(u.log,`${u.uploader || 'Anonymous'} · ${new Date((u.created_at || 0)*1000).toLocaleDateString()}`)).join(' ')} — another party member's upload of the same fight. It counts once per character on the leaderboard.</p>`;
        return ranks?.duplicate?'<p>Another public upload of this encounter was detected. Matching player samples count once.</p>':'';
      };
      const qualityHTML=`<details class="note"><summary>Capture quality · ${quality?.eligible?'Eligible for community rankings':'Unranked / completeness unverified'}</summary>${quality?`<ul>${(quality.messages || []).map(m=>`<li>${esc(m)}</li>`).join('')}</ul><p>${esc(quality.note)}</p>${driverHTML}${processingHTML}`:'<p>This older log does not contain a capture-quality assessment. It remains available for review.</p>'}${stitchedHTML()}${sharedHTML()}</details>`;
      const runs=[...new Set(doc.segments.filter(matchesMode).map(s=>s.run_id || "legacy"))];
      const runMenu=runs.some(id=>id!=="legacy")?`<label>Run <select data-control="run"><option value="">All runs</option>${runs.map(id=>`<option value="${esc(id)}" ${state.run===id?'selected':''}>Run ${esc(id)}</option>`).join('')}</select></label><span class="small muted">Run ${esc(d.segment.run_id || "legacy")} · ${d.segment.run_complete?'Finished':'Unfinished / completion unverified'} · ${esc(d.segment.run_end_reason || '')}</span>`:"";
      const rows=d.rows.filter(p=>!state.actor || p.id===state.actor).sort((a,b)=>b[metric]-a[metric]);
      // Each player's parse: the percentile of their DPS among every character's best on this
      // boss / category / game version / difficulty for their class (100 = the class best), from
      // the server's rankings for this encounter. WCL-style colours; "·" until the rankings
      // arrive or when the encounter is unranked / has no comparable public parses.
      const parseTier=p=>p>=100?'gold':p>=99?'pink':p>=95?'orange':p>=75?'purple':p>=50?'blue':p>=25?'green':'grey';
      const parseOf=id=>(ranks?.players||[]).find(x=>x.id===id);
      const parseHTML=p=>{
        const entry=parseOf(p.id);
        if(!options.rankings)return '';
        if(!ranks)return '<span class="parse q-none" title="Loading the community parse…">·</span>';
        if(!entry || entry.parse===null || entry.parse===undefined)return `<span class="parse q-none" title="${esc(ranks.error || (ranks.players?.length?'No comparable public parses for this class on this encounter yet':ranks.note || 'Unranked encounter'))}">·</span>`;
        const few=(entry.parse_characters||0)<5;
        return `<span class="parse q-${parseTier(entry.parse)}${few?' provisional':''}" title="${entry.parse} percentile among ${entry.parse_characters} ${esc(p.class||'')} character${entry.parse_characters===1?'':'s'} on this encounter${few?' (provisional: fewer than 5 characters)':''}">${Math.round(entry.parse)}</span>`;
      };
      const parseColumn=!!options.rankings;
      const summary=`<p class="small muted">DPS uses shared active damage time (${d.dpsDuration.toFixed(0)}s): one-second buckets with outgoing player damage. Empty buckets are excluded; DPS holds while idle and resumes on the same totals. Deaths do not reset players. Graph rates use elapsed encounter time.${parseColumn?' Parse: percentile among every character\'s best DPS on this encounter for the same class (100 = class best); dimmed when fewer than 5 characters compare.':''}</p>`+table(["Player / server",...(parseColumn?["Parse"]:[]),"Class","Damage done","DPS","Damage taken","Healing","HPS","Deaths"],rows.map(p=>`<tr><td style="color:${color(p.class)}">${actorHTML(p)}</td>${parseColumn?`<td class="r">${parseHTML(p)}</td>`:''}<td>${esc(p.class || "Unknown")}</td><td>${number(p.damage)}</td><td>${number(p.damage/d.dpsDuration)}</td><td>${number(p.taken)}</td><td>${number(p.healing)}</td><td>${number(p.healing/duration)}</td><td>${p.deaths?`${p.deaths}${p.revives?` <span class="muted">(revived ${p.revives})</span>`:''}`:'No markers'}</td></tr>`));
      const skills=new Map();for(const e of events) {if(e.kind==="death" || e.kind==="revive" || (state.metric==="summary" && (e.kind!=="damage" || !(d.friendly.has(e.source) || d.r[e.source]?.owner))))continue;const actor=owner(state.metric==="taken"?e.target:e.source,d.r);const key=actor+":"+e.kind+":"+(e.skill_id || e.skill);const row=skills.get(key) || {actor,kind:e.kind,skill:e.skill || e.skill_id || "Unknown",amount:0,hits:0,min:Infinity,max:0};row.amount+=e.amount || 0;row.hits++;row.min=Math.min(row.min,e.amount || 0);row.max=Math.max(row.max,e.amount || 0);skills.set(key,row);}
      const skillRows=[...skills.values()].sort((a,b)=>b.amount-a.amount),skillTotal=skillRows.reduce((total,s)=>total+s.amount,0);
      const breakdown=table(["Player / server","Ability","Effects","Amount","Share","Per second","Average","Minimum","Maximum"],skillRows.map(s=>`<tr><td style="color:${color(d.r[s.actor]?.class)}">${actorHTML(d.r[s.actor])}</td><td>${esc(s.skill)}${s.kind==="heal"?" (heal)":""}</td><td>${s.hits}</td><td>${number(s.amount)}</td><td>${skillTotal?(100*s.amount/skillTotal).toFixed(1):0}%</td><td>${number(s.amount/(s.kind==='damage' && state.metric!=='taken'?d.dpsDuration:duration))}</td><td>${number(s.amount/s.hits)}</td><td>${number(s.min)}</td><td>${number(s.max)}</td></tr>`));
      const skillChart=state.graph && skillRows.length?`<h3>Ability contribution · ${state.metric==="healing"?"healing":state.metric==="taken"?"damage taken":"damage done"}</h3><p class="small muted">Top 20 player/ability rows; all recorded abilities appear in the table. Select a player to inspect their contribution.</p><svg width="100%" viewBox="0 0 1000 ${Math.min(20,skillRows.length)*30}" role="img" aria-label="Amount by player and ability">${skillRows.slice(0,20).map((s,i)=>`<text x="0" y="${i*30+19}" fill="#c8d3df" font-size="13">${esc((label(d.r[s.actor])+" · "+s.skill).slice(0,55))}</text><rect x="440" y="${i*30+3}" width="${450*s.amount/Math.max(1,skillRows[0].amount)}" height="22" fill="${color(d.r[s.actor]?.class)}"><title>${esc(label(d.r[s.actor])+" · "+s.skill+" · "+number(s.amount))}</title></rect><text x="990" y="${i*30+19}" text-anchor="end" fill="#c8d3df" font-size="13">${number(s.amount)}</text>`).join('')}</svg>`:"";
      const pageCount=Math.max(1,Math.ceil(events.length/100));state.page=Math.min(state.page,pageCount-1);
      const eventTable=table(["Time","Event","Caster / attacker","Recipient / target","Ability","Amount"],events.slice(state.page*100,(state.page+1)*100).map(e=>`<tr><td>${e.t.toFixed(3)}s</td><td>${esc(e.kind)}</td><td>${actorHTML(d.r[e.source])}</td><td>${actorHTML(d.r[e.target])}</td><td>${esc(e.skill || e.skill_id || "—")}</td><td>${e.kind==="death"?"—":number(e.amount)}</td></tr>`));
      root.innerHTML=`<section class="win cr-review"><div class="wh"><h2>${esc(doc.meta?.title || "Combat log")}</h2><span>${duration.toFixed(1)}s</span></div><div class="wb">
        <div class="row"><label>Combat mode <select data-control="mode"><option value="" ${!state.mode?'selected':''}>All recorded modes</option><option value="pve" ${state.mode==='pve'?'selected':''}>PvE</option><option value="pvp" ${state.mode==='pvp'?'selected':''}>PvP</option></select></label>${runMenu}${options.live?`<label><input type="checkbox" data-control="followLatest" ${state.followLatest?'checked':''}> Follow latest encounter</label>`:''}<label>Encounter <select data-control="segment">${doc.segments.map((s,i)=>(!matchesMode(s) || (state.run && (s.run_id || "legacy")!==state.run))?"":`<option value="${i}" ${i===state.segment?"selected":""}>${esc(s.label || s.boss || "Combat "+(i+1))}</option>`).join("")}</select></label><label>Player <select data-control="actor"><option value="">All players</option>${d.rows.map(p=>`<option value="${esc(p.id)}" ${p.id===state.actor?"selected":""}>${esc(label(p))}</option>`).join("")}</select></label><button class="btn small" data-color-settings>Class colors</button>${window.A2AssetHealth?'<button class="btn small" data-retry-images>Retry images</button><button class="btn small" data-export-images>Export image failures</button>':''}<label><input type="checkbox" data-control="insights" ${state.insights?"checked":""}> Encounter insights</label></div>
        ${(d.segment.encounter_type||doc.meta?.encounter_type||'').startsWith('pvp_')?'<p class="note">PvP recording · matched by mode, arena/encounter, ruleset and game version. Opponents are outside the recorded Self/Party roster. Only observed combat effects are shown; match results, objectives and kill credit are not inferred.</p>':''}
        <p class="small muted">${doc.meta?.installed_build?`Installed game version: ${esc(doc.meta.installed_build)} (${esc(doc.meta.installed_build_source)}). `:""}${d.segment.game_patch||doc.meta?.game_patch?`Version source: ${esc(buildLabel(d.segment.game_patch_source||doc.meta?.game_patch_source||"source not recorded"))}. `:""}${d.segment.zone?`Zone: ${esc(d.segment.zone)} · ${esc(d.segment.zone_source || "source not recorded")}. `:""}${d.segment.difficulty?`Difficulty: ${esc(d.segment.difficulty)} · ${esc(d.segment.difficulty_source || "source not recorded")}. `:""}${d.segment.encounter_type_source?`Encounter type source: ${esc(d.segment.encounter_type_source)}. `:""}${doc.meta?.region_source?`Region source: ${esc(doc.meta.region_source)}.`:""}</p>
        ${combinedHTML()}${archiveHTML()}${qualityHTML}${classificationHTML(d)}${catalogHTML(d)}${state.mode?'<p class="small muted">Showing only encounters recorded as '+state.mode.toUpperCase()+'. Whole-run timing is hidden in this filtered view.</p>':runsHTML(d)}<div class="cr-tabs">${["summary","damage","taken","healing","deaths"].map((v,i)=>`<button class="btn small ${state.metric===v?"primary":""}" data-metric="${v}">${["Summary","Damage Done","Damage Taken","Healing","Death recaps"][i]}</button>`).join("")}<span class="cr-spacer"></span>${["table","timeline","events"].map(v=>`<button class="btn small ${state.view===v?"primary":""}" data-view="${v}">${v[0].toUpperCase()+v.slice(1)}</button>`).join("")}</div>
        <div class="cr-options">${[["graph","Graph"],["timeline","Timeline"],["skills","Skills"],["deaths","Deaths"],["heals","Healing"],["pets","Pets"],["combine","Combine pets with owner"]].map(([key,label])=>`<label><input type="checkbox" data-control="${key}" ${state[key]?"checked":""}> ${label}</label>`).join("")}</div>
        <div class="row"><span>Character builds:</span>${Object.values(d.r).filter(character).map(actorHTML).join(" ")}</div><div data-profile>${profileHTML()}</div><div data-colors hidden></div>${state.graph && state.metric!=="deaths"?graph(d,events):""}${latencyHTML(d)}${bossHPHTML(d)}${encounters(d)}${state.metric==="deaths"?recapsHTML(d):""}${state.insights?insightsHTML(d):""}
        ${state.view==="table" ? summary+(state.metric!=="deaths"?skillChart+breakdown:"") : state.view==="events" ? eventTable+`<div class="row"><button class="btn small" data-prev>Previous</button> ${state.page+1} / ${pageCount} · ${events.length} events <button class="btn small" data-next>Next</button></div>` : ""}
        ${state.timeline && state.view==="timeline" ? timeline(d,events):""}
        ${actionsHTML(d)}
        <p class="small muted">${d.events.some(e=>e.kind==="heal"&&!e.target)?"Some healing recipients are not carried by their packet variant. ":""}${!d.events.some(e=>e.kind==="death")?"No death markers recorded; zero counts do not establish a deathless run. ":""}${!(d.segment.positions || []).length?"Movement replay is unavailable: no verified positions were recorded.":""}</p>
        ${reportHTML()}${metadataHTML(d)}${ranksHTML(d)}${options.rankings?'<button class="btn small" data-rank-refresh>Refresh rankings</button>':""}${options.publish?'<details><summary>Publish this log</summary><div class="row"><select data-upload-vis aria-label="Upload visibility"><option>unlisted</option><option>public</option><option>private</option></select><button class="btn small" data-upload>Upload saved session</button><span data-upload-result></span></div></details>':""}<div data-replay></div>
        <div class="row"><input data-compare placeholder="Another public log ID" aria-label="Log ID to compare"><button class="btn small" data-compare-go ${options.compare?"":"disabled"}>Compare log</button><span data-compare-result></span><input type="file" data-compare-file accept=".json" aria-label="Compare a local a2log file"></div>
        <div data-comparison>${comparisonHTML(d)}</div>
      </div></section>`;
      bindArchive();bindCombined();
      root.querySelectorAll("[data-control]").forEach(e=>e.onchange=()=>{
        const key=e.dataset.control;
        if(key==='combine' && e.checked && state.actor)state.actor=refs()[state.actor]?.owner || state.actor;
        state[key]=e.type==='checkbox'?e.checked:key==='segment'?+e.value:e.value;state.page=0;
        if(key==='run' || key==='segment')state.followLatest=false;
        const changedEncounter=['mode','run','segment','followLatest'].includes(key);
        if(key==='mode'){state.run='';state.segment=Math.max(0,doc.segments.findIndex(matchesMode));}
        if(key==='run'){const index=doc.segments.findIndex(s=>matchesMode(s) && (!state.run || (s.run_id || 'legacy')===state.run));state.segment=Math.max(0,index);}
        if(changedEncounter){timelineHidden.clear();timelineCollapsed.clear();state.enemy='';state.actor='';ranks=null;state.timelineStart=0;timelineDetail='';}
        selectLatest();render();if(changedEncounter)requestRanks();
      });
      const mapping=root.querySelector('[data-export-mappings]');if(mapping)mapping.onclick=()=>{const c=doc.encounter_insights.segments.find(s=>s.segment===state.segment).catalog;const url=URL.createObjectURL(new Blob([JSON.stringify(c,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='aion2-mapping-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);root.querySelector('[data-mapping-status]').textContent='Mapping report download started.';};
      root.querySelectorAll("[data-recap]").forEach(e=>e.onclick=()=>{state.recap=+e.dataset.recap;render();});
      root.querySelectorAll("[data-metric]").forEach(e=>e.onclick=()=>{state.metric=e.dataset.metric;state.page=0;render();});
      root.querySelectorAll("[data-actions]").forEach(e=>e.onclick=()=>{state.actions=e.dataset.actions;render();});
      root.querySelectorAll("[data-view]").forEach(e=>e.onclick=()=>{state.view=e.dataset.view;if(state.view==="timeline")state.timeline=true;render();});
      root.querySelectorAll('[data-timeline-collapse]').forEach(b=>b.onclick=()=>{const id=b.dataset.timelineCollapse;timelineCollapsed.has(id)?timelineCollapsed.delete(id):timelineCollapsed.add(id);render();});
      root.querySelectorAll('[data-timeline-hide]').forEach(b=>b.onclick=()=>{timelineHidden.add(b.dataset.timelineHide);render();});
      root.querySelectorAll('[data-timeline-visible]').forEach(b=>b.onchange=()=>{b.checked?timelineHidden.delete(b.dataset.timelineVisible):timelineHidden.add(b.dataset.timelineVisible);render();});
      const showTimelines=root.querySelector('[data-timeline-show-all]');if(showTimelines)showTimelines.onclick=()=>{timelineHidden.clear();render();};
      const expandTimelines=root.querySelector('[data-timeline-expand-all]');if(expandTimelines)expandTimelines.onclick=()=>{timelineCollapsed.clear();render();};
      root.querySelectorAll('[data-attempt-segment]').forEach(e=>e.onclick=()=>{timelineHidden.clear();timelineCollapsed.clear();state.segment=+e.dataset.attemptSegment;state.timelineStart=0;timelineDetail="";state.enemy='';state.actor='';ranks=null;requestRanks();render();});
      root.querySelectorAll("[data-enemy-filter]").forEach(e=>e.onclick=()=>{state.enemy=e.dataset.enemyFilter;render();});
      root.querySelector("[data-clear-enemy]").onclick=()=>{state.enemy="";render();};
      root.querySelectorAll("[data-series]").forEach(e=>e.onclick=()=>{state.hidden.add(e.dataset.series);render();});
      if(root.querySelector("[data-showall]"))root.querySelector("[data-showall]").onclick=()=>{state.hidden.clear();render();};
      if(root.querySelector("[data-prev]"))root.querySelector("[data-prev]").onclick=()=>{state.page=Math.max(0,state.page-1);render();};
      if(root.querySelector("[data-next]"))root.querySelector("[data-next]").onclick=()=>{state.page++;render();};
      bindImageExport();
      const retryImages=root.querySelector('[data-retry-images]');if(retryImages)retryImages.onclick=()=>{A2AssetHealth.retry();render();};
      root.querySelector("[data-color-settings]").onclick=()=>{const box=root.querySelector("[data-colors]");box.hidden=!box.hidden;settings(box);};
      root.querySelector("[data-compare-go]").onclick=async()=>{const id=root.querySelector("[data-compare]").value.trim();const msg=root.querySelector("[data-compare-result]");try{addComparison(await options.compare(id));render();}catch(e){msg.textContent=e.message;}};
      root.querySelector("[data-compare-file]").onchange=async e=>{try{const imported=JSON.parse(await e.target.files[0].text());if(imported.format!=="a2log" || !Array.isArray(imported.segments))throw Error("Choose an a2log JSON file");addComparison(imported);render();}catch(e){root.querySelector("[data-compare-result]").textContent=e.message;}};
      root.querySelectorAll('[data-compare-segment]').forEach(e=>e.onchange=()=>{comparisons[+e.dataset.compareSegment].segment=+e.value;render();});
      root.querySelectorAll('[data-compare-player]').forEach(e=>e.onchange=()=>{comparisons[+e.dataset.index].players[e.dataset.comparePlayer]=e.value;render();});
      root.querySelectorAll('[data-compare-remove]').forEach(e=>e.onclick=()=>{comparisons.splice(+e.dataset.compareRemove,1);render();});
      const save=root.querySelector('[data-meta-save]');if(save)save.onclick=async()=>{
        save.disabled=true;
        try{
          const next=JSON.parse(JSON.stringify(doc)),current=doc.segments[state.segment];
          const runScope=root.querySelector('[data-meta-scope]').value==='run';
          const targets=runScope?next.segments.filter(s=>current.run_id && s.run_id===current.run_id):[next.segments[state.segment]];
          if(!targets.length)throw Error('This encounter has no recorded run ID. Choose this encounter only.');
          root.querySelectorAll('[data-meta]').forEach(e=>{
            const key=e.dataset.meta,value=e.value.trim(),previous=current[key]??doc.meta?.[key]??(key==='encounter_type'?'unknown':'');
            if(value===String(previous))return;
            if(key==='region'){next.meta ||= {};next.meta.region=value;next.meta.region_source='Manual post-capture override';return;}
            // A boss name belongs to its encounter, even when correcting a whole run.
            for(const segment of key==='boss'?[next.segments[state.segment]]:targets){
              segment[key]=value;
              if(['game_patch','zone','difficulty','encounter_type'].includes(key))segment[key+'_source']='Manual post-capture override';
              if(key==='game_patch')segment.game_patch_basis='manual';
            }
          });
          doc=await options.saveMetadata(next);ranks=null;requestRanks();render();
          root.querySelector('[data-meta-result]').textContent='Metadata saved to the local log. Uploaded copies are unchanged.';
        }catch(e){root.querySelector('[data-meta-result]').textContent=e.message;save.disabled=false;}
      };
      if(root.querySelector('[data-rank-refresh]'))root.querySelector('[data-rank-refresh]').onclick=requestRanks;
      root.querySelectorAll('[data-open-shared]').forEach(button=>button.onclick=()=>{if(options.openArchivePart)options.openArchivePart({id:button.dataset.openShared},state.mode);});
      if(root.querySelector('[data-upload]'))root.querySelector('[data-upload]').onclick=async()=>{const button=root.querySelector('[data-upload]');button.disabled=true;try{const r=await options.publish(root.querySelector('[data-upload-vis]').value);root.querySelector('[data-upload-result]').innerHTML=`<a href="${esc(r.url)}" target="_blank" rel="noopener">Open shared log</a>${r.ownership_warning?`<p>${esc(r.ownership_warning)}</p>`:''}`;document.dispatchEvent(new Event('a2log-uploaded'));}catch(e){root.querySelector('[data-upload-result]').textContent=e.message;}finally{button.disabled=false;}};
      root.querySelectorAll('[data-character]').forEach(e=>e.onclick=()=>{state.character=e.dataset.character;render();root.querySelector('[data-profile]').scrollIntoView({block:'nearest'});});
      bindProfile();
      const report=root.querySelector('[data-report-send]');if(report){
        const reason=root.querySelector('[data-report-reason]'),details=root.querySelector('[data-report-details]');reason.value=reportReason;details.value=reportDetails;root.querySelector('[data-report-status]').textContent=reportStatus;report.disabled=reportBusy;
        reason.onchange=()=>{reportReason=reason.value;};details.oninput=()=>{reportDetails=details.value;};
        report.onclick=async()=>{if(reportBusy)return;reportBusy=true;report.disabled=true;try{const result=await options.report({reason:reportReason,details:reportDetails});reportStatus=result.message+' Receipt: '+result.id;reportDetails='';}catch(e){reportStatus=e.message;}finally{reportBusy=false;if(root.isConnected)render();}};
      }
      root.querySelectorAll('[data-effect-detail]').forEach(marker=>{
        const show=e=>{timelineDetail=marker.dataset.effectDetail;const panel=root.querySelector('[data-effect-panel]');if(panel)panel.textContent=timelineDetail;const tip=root.querySelector('[data-effect-tooltip]');if(tip){tip.textContent=timelineDetail;tip.hidden=false;const bounds=marker.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(innerWidth-370,(e?.clientX||bounds.left)+12))+'px';tip.style.top=Math.max(8,Math.min(innerHeight-100,(e?.clientY||bounds.top)+22))+'px';}};
        marker.onpointerenter=show;marker.onpointermove=show;marker.onfocus=show;marker.onclick=show;
        marker.onpointerleave=()=>{const tip=root.querySelector('[data-effect-tooltip]');if(tip)tip.hidden=true;};marker.onblur=marker.onpointerleave;
        marker.onkeydown=e=>{if(e.key==='Enter' || e.key===' '){e.preventDefault();show();}};
      });
      root.querySelectorAll('[data-skill-icon]').forEach(image=>{image.onerror=()=>image.remove();});
      const graphMode=root.querySelector('[data-graph-mode]');if(graphMode)graphMode.onchange=()=>{state.graphMode=graphMode.value;render();};
      const hit=root.querySelector('[data-graph-hit]');
      if(hit && graphModel){
        let inspected=0;
        const inspect=t=>{const m=graphModel;inspected=Math.max(0,Math.min(m.duration,t));const i=Math.min(m.count-1,Math.floor(inspected/m.step));
          const rates=new Map();for(const [,series] of m.lines){const row=rates.get(series.actor)||{};row[series.kind]=series.values[i];rates.set(series.actor,row);}
          const rate=x=>x==null?'—':number(x)+'/s';
          const rows=[...rates].map(([actor,row])=>`<tr><td style="color:${color(d.r[actor]?.class)}">${esc(label(d.r[actor]))}</td><td>${rate(row['Damage done'])}</td><td>${rate(row.Healing)}</td><td>${rate(row['Damage taken'])}</td></tr>`);
          let html=`<p><b>${clock(inspected,true)}</b> · Total ${esc(m.primary.toLowerCase())}: ${rate(m.total[i])} · 10 s average: ${rate(m.roll[i])}</p>`+table(['Player','Damage done','Healing','Damage taken'],rows);
          const hpRows=[];for(const id of new Set(m.health.map(s=>s.entity))){const sample=m.health.filter(s=>s.entity===id && s.t<=inspected).sort((a,b)=>b.t-a.t)[0];if(sample)hpRows.push(`<tr><td>${esc(label(d.r[id]))}</td><td>${number(sample.current)}</td><td>${sample.max?number(sample.max):'Unavailable'}</td><td>${clock(sample.t,true)}</td></tr>`);}
          if(hpRows.length)html+=table(['Boss','Remaining HP','Observed maximum','Sample time'],hpRows);
          root.querySelector('[data-graph-detail]').innerHTML=html;const cursor=root.querySelector('[data-graph-cursor]');cursor.setAttribute('d','M'+(60+880*inspected/m.duration)+' 20V180');cursor.setAttribute('visibility','visible');};
        const time=e=>{const box=hit.getBoundingClientRect();return (e.clientX-box.left)/Math.max(1,box.width)*graphModel.duration;};
        hit.onpointermove=e=>inspect(time(e));hit.onfocus=()=>inspect(inspected);
        hit.onclick=e=>{inspect(time(e));if(state.view==='timeline'){state.timelineStart=Math.max(0,inspected-(Number(state.timelineWindow)||graphModel.duration)/2);render();}};
        hit.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();inspect(inspected+(e.key==='ArrowLeft'?-1:1)*graphModel.step);}};
      }
      const windowControl=root.querySelector('[data-timeline-window]');if(windowControl)windowControl.onchange=()=>{state.timelineWindow=Number(windowControl.value);render();};
      for(const selector of ['[data-time-start]','[data-time-scrub]']){const input=root.querySelector(selector);if(input)input.onchange=()=>{state.timelineStart=Number(input.value);render();};}
      for(const [selector,direction] of [['[data-time-prev]',-1],['[data-time-next]',1]]){const button=root.querySelector(selector);if(button)button.onclick=()=>{state.timelineStart+=(Number(state.timelineWindow)||d.segment.duration)*direction;render();};}
      replay(d);
    }
    function addComparison(other) {
      if(other.format!=="a2log" || !Array.isArray(other.players) || !Array.isArray(other.segments))throw Error("Choose an a2log document");
      comparisons.push({doc:other,segment:0,players:{}});
    }
    const context=(document,segment)=>[segment.boss || segment.label || "Unknown",...['encounter_type','game_patch','difficulty'].map(k=>segment[k] || document.meta?.[k] || "Unknown")];
    function comparisonHTML(d) {
      return comparisons.map((c,index)=>{
        c.segment=Math.min(c.segment,c.doc.segments.length-1);
        const other=c.doc.segments[c.segment];if(!other)return "";
        const sums=new Map();for(const h of other.hits || [])sums.set(h.player,(sums.get(h.player)||0)+h.damage);
        const mismatch=JSON.stringify(context(doc,d.segment))!==JSON.stringify(context(c.doc,other));
        return `<h3>Comparison ${index+1} — ${esc(c.doc.meta?.title || "Other run")}</h3><div class="row"><label>Comparison encounter <select data-compare-segment="${index}">${c.doc.segments.map((s,i)=>`<option value="${i}" ${i===c.segment?'selected':''}>${esc(buildLabel(context(c.doc,s).join(' · ')))}</option>`).join('')}</select></label><button class="btn small" data-compare-remove="${index}">Remove</button></div><p class="small muted">Current: ${esc(buildLabel(context(doc,d.segment).join(' · ')))}. ${mismatch?'Encounter metadata differs. ':''}Recorded DPS is not adjusted for gear or missing packets. Select each player explicitly; multiple players of one class are never paired automatically.</p>${table(['Current player','Class','Current DPS','Comparison player','Comparison DPS','Difference'],d.rows.map(p=>{
          const candidates=(c.doc.players || []).filter(o=>o.class && o.class===p.class);const selected=candidates.find(o=>o.id===c.players[p.id]);
          const theirs=selected?(sums.get(selected.id)||0)/Math.max(.001,other.duration):null;const own=p.damage/Math.max(.001,d.segment.duration);
          return `<tr><td>${actorHTML(p)}</td><td>${esc(p.class)}</td><td>${number(own)}</td><td><select data-compare-player="${esc(p.id)}" data-index="${index}"><option value="">Select same-class player</option>${candidates.map(o=>`<option value="${esc(o.id)}" ${o.id===selected?.id?'selected':''}>${esc(label(o))}</option>`).join('')}</select></td><td>${theirs===null?'Unavailable':number(theirs)}</td><td>${theirs?((own/theirs-1)*100).toFixed(1)+'%':'—'}</td></tr>`;
        }))}`;
      }).join('');
    }
    function reportHTML() {
      if(!options.report)return '';
      return `<details data-report-form ${reportDetails||reportStatus||reportBusy?'open':''}><summary>Report this shared log</summary><p class="small muted">Reports go privately to the server operator for human review. A report is not a verified finding. Do not include credentials or unnecessary personal information.</p><label>Reason <select data-report-reason><option value="privacy">Privacy concern</option><option value="harassment">Harassment</option><option value="suspected_tampering">Suspected data tampering</option><option value="wrong_metadata">Incorrect encounter metadata</option><option value="other">Other</option></select></label><label>Details (10–1,000 characters)<textarea data-report-details minlength="10" maxlength="1000" rows="3"></textarea></label><button class="btn small" data-report-send>Send report</button><p data-report-status role="status"></p></details>`;
    }
    function metadataHTML(d) {
      if(!options.saveMetadata || options.live || doc.meta?.capture_active)return `<p class="small muted">${esc(buildLabel(context(doc,d.segment).join(' · ')))}</p>`;
      return `<details><summary>Encounter metadata for comparisons</summary><p class="small muted">Correct completed recordings here. Choose this encounter or its recorded run for changed game version, category, difficulty and zone fields. Unchanged fields are preserved. Boss name applies only to this encounter; region applies to the session. Saving changes the local log; an uploaded copy is unchanged.</p><div class="row"><label>Apply changed fields to <select data-meta-scope><option value="encounter">This encounter</option>${d.segment.run_id?'<option value="run">All encounters in this run</option>':''}</select></label><label>Encounter type <select data-meta="encounter_type">${Object.entries(window.A2Community?.types || {unknown:'Unknown'}).map(([v,l])=>`<option value="${v}" ${v===(d.segment.encounter_type||doc.meta?.encounter_type||'unknown')?'selected':''}>${esc(l)}</option>`).join('')}</select></label>${['game_patch','difficulty','region','boss','zone'].map(k=>`<label>${esc(k==='game_patch'?'game version':k.replaceAll('_',' '))} <input data-meta="${k}" value="${esc(d.segment[k]||doc.meta?.[k]||'')}" maxlength="200"></label>`).join('')}<button class="btn small" data-meta-save>Save metadata</button><span data-meta-result></span></div></details>`;
    }
    function replay(d) {
      const positions=d.segment.positions || [];if(!positions.length)return;
      const box=root.querySelector("[data-replay]");
      box.innerHTML='<h3>Recorded movement replay</h3><button class="btn small" data-play>Play</button> <button class="btn small" data-rewind>Rewind</button><input data-scrub type="range" min="0" step="0.1" value="0"><output data-clock></output><svg class="cr-arena" viewBox="0 0 100 100" aria-label="Recorded positions"></svg><button class="btn small" data-plan>Import into Raid Planner</button><span data-plan-status role="status"></span>';
      const scrub=box.querySelector("[data-scrub]");scrub.max=d.segment.duration;const tokens={};
      for(const pos of positions)(tokens[pos.entity] ||= []).push(pos);
      const draw=t=>{scrub.value=t;box.querySelector("[data-clock]").textContent=t.toFixed(1)+"s";box.querySelector("svg").innerHTML=Object.entries(tokens).map(([id,frames])=>{const a=frames.filter(p=>p.t<=t).at(-1) || frames[0],b=frames.find(p=>p.t>t) || a,f=(t-a.t)/Math.max(.001,b.t-a.t);return `<circle cx="${100*(a.x+(b.x-a.x)*Math.min(1,f))}" cy="${100*(a.y+(b.y-a.y)*Math.min(1,f))}" r="2" fill="${color(d.r[id]?.class)}"><title>${esc(label(d.r[id]))}</title></circle>`;}).join("");};
      const pause=()=>{if(replayFrame)cancelAnimationFrame(replayFrame);replayFrame=null;box.querySelector("[data-play]").textContent="Play";};
      box.querySelector("[data-play]").onclick=()=>{if(replayFrame){pause();return;}let last=performance.now();box.querySelector("[data-play]").textContent="Pause";const tick=now=>{const t=Math.min(d.segment.duration,+scrub.value+(now-last)/1000);last=now;draw(t);if(t>=d.segment.duration)pause();else replayFrame=requestAnimationFrame(tick);};replayFrame=requestAnimationFrame(tick);};
      box.querySelector("[data-rewind]").onclick=()=>{pause();draw(0);};scrub.oninput=()=>{pause();draw(+scrub.value);};
      box.querySelector("[data-plan]").onclick=()=>{const plan={format:"a2plan",version:1,meta:{name:d.segment.boss || d.segment.label || "Recorded replay"},duration:d.segment.duration,arena:{kind:"square"},tokens:Object.entries(tokens).map(([id,keyframes])=>({id,kind:d.r[id]?.kind==="enemy"?"enemy":"player",label:label(d.r[id]),cls:d.r[id]?.class,color:color(d.r[id]?.class),keyframes})),buffs:[]};if(options.importPlan){try{options.importPlan(plan);}catch(e){box.querySelector("[data-plan-status]").textContent=e.message;}return;}const blob=new Blob([JSON.stringify(plan)],{type:"application/json"}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="recorded-replay.a2plan.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};box.querySelector("[data-plan]").textContent=options.importPlan?"Open in Raid Planner":"Export Raid Planner file";draw(0);
    }
    // Swap the single-part view for a combined recording review (keeping the source part so
    // "Back to source part" and each part's own ranked data stay one click away).
    function applyCombined(next,first,last){
      sourceView={doc,options,state};doc=next;archiveFirst=first;archiveLast=last;
      rankRequest++;profileRequest++;ranks=null;previews.clear();comparisons=[];
      options={...options,rankings:undefined,lookupProfile:undefined,publish:undefined,saveMetadata:undefined,report:undefined};
      state={...state,segment:0,run:'',actor:'',enemy:'',character:'',page:0,hidden:new Set()};
    }
    // Viewing one part of a multi-part recording, open the complete stitched recording as the
    // main view (the server links the parts by archive id and reconstructs them). Best-effort:
    // if the parts can't be combined — an older server, a gap, too many parts, or a private
    // sibling out of view — the single part stays on screen exactly as before.
    async function autoCombine(){
      const a=doc.meta?.archive;
      if(disposed||sourceView||options.live||doc.meta?.reconstruction||!a||!options.reconstructArchive||!options.archiveParts)return;
      if(!(a.part>1||a.closed))return;                       // a lone, still-open current part has no earlier siblings
      const request=++archiveRequest;
      try{
        const parts=await options.archiveParts(0,100,a.id);
        if(disposed||request!==archiveRequest||!parts||!Array.isArray(parts.rows))return;
        const nums=parts.rows.map(r=>r.archive?.part??r.part).filter(n=>Number.isSafeInteger(n));
        const first=Math.min(...nums),last=Math.max(...nums);
        if(nums.length<2||last<=first||last-first>=32)return;  // nothing to combine, or too many parts to stitch
        const next=await options.reconstructArchive(first,last);
        if(disposed||request!==archiveRequest||!next?.meta?.reconstruction||!next.recording_summary||!Array.isArray(next.segments))return;
        applyCombined(next,first,last);
        if(root.isConnected)render();
      }catch(e){/* reconstruction unavailable — leave the single-part view in place */}
    }
    async function requestRanks() {if(!options.rankings)return;const request=++rankRequest;try{const response=await options.rankings(state.segment,doc);if(request!==rankRequest)return;ranks=response;}catch(e){ranks={error:e.message};}if(root.isConnected)render();}
    const api={update(next){doc=next;state.segment=Math.min(state.segment,doc.segments.length-1);const changed=selectLatest();render();if(changed)requestRanks();},state,dispose(){disposed=true;archiveRequest++;rankRequest++;profileRequest++;if(replayFrame)cancelAnimationFrame(replayFrame);}};
    selectLatest();render();requestRanks();autoCombine();return api;
  }
  window.A2CombatReview={mount,color,settings,palettes:PALETTES};
})();
