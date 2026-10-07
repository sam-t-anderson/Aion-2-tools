/* Shared combat explorer used by the desktop, Pages and log server. */
(function () {
  "use strict";
const buildLabel=x=>String(x??'').replace(/build:steam:[0-9]{1,12}:([0-9]{1,20})/g,'Build $1 · Steam');
  const defaults = {gladiator:"#c69b6d",templar:"#f58cba",assassin:"#fff468",ranger:"#aad372",sorcerer:"#3fc7eb",spiritmaster:"#8788ee",cleric:"#ffffff",chanter:"#ff7c0a"};
  const esc = x => String(x ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = x => Math.round(x || 0).toLocaleString();
  function preferences() { try {return JSON.parse(localStorage.getItem("a2-combat-colors")) || {};} catch (_) {return {}; } }
  function color(cls) { const pref=preferences(); const candidate=(pref.colors || {})[cls] || defaults[cls] || "#e8cf8e"; return pref.enabled === false ? "#e8cf8e" : /^#[0-9a-f]{6}$/i.test(candidate) ? candidate : "#e8cf8e"; }
  function settings(root,onSave) {
    const pref=preferences();
    root.innerHTML=`<label><input type="checkbox" data-enable ${pref.enabled!==false?"checked":""}> Use class colors</label><div class="cr-colors">${Object.keys(defaults).map(c=>`<label>${esc(c)} <input type="color" data-color="${c}" value="${color(c)}"></label>`).join("")}</div><button class="btn small" data-reset>Reset class colors</button>`;
    const save=()=>{const pref={enabled:root.querySelector("[data-enable]").checked,colors:Object.fromEntries([...root.querySelectorAll("[data-color]")].map(e=>[e.dataset.color,e.value]))};localStorage.setItem("a2-combat-colors",JSON.stringify(pref));if(onSave)onSave(pref);};
    root.onchange=save;root.querySelector("[data-reset]").onclick=()=>{localStorage.removeItem("a2-combat-colors");settings(root,onSave);if(onSave)onSave({});};
  }
  const table = (headers,rows) => `<div class="cr-scroll"><table class="t"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${headers.length}">No recorded events.</td></tr>`}</tbody></table></div>`;
  function mount(root, doc, options={}) {
    let state={followLatest:!!options.live,mode:["pve","pvp"].includes(options.mode)?options.mode:"",run:"",segment:0,metric:"summary",view:"table",graph:true,timeline:true,graphMode:"total",timelineWindow:30,timelineStart:0,skills:true,deaths:true,heals:true,pets:true,combine:true,actor:"",page:0,enemy:"",hidden:new Set(), ...options.state};
    let comparisons=[], ranks=null, rankRequest=0, replayFrame=null, profileRequest=0;
    let reportReason='privacy',reportDetails='',reportStatus='',reportBusy=false;
    const previews=new Map();
    let timelineDetail="",graphModel=null;
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
      state.segment=index;state.actor='';state.enemy='';state.page=0;state.timelineStart=0;timelineDetail='';ranks=null;
      return true;
    }
    const refs=()=>{const r={};for(const e of [...(doc.players || []),...(doc.segments[state.segment]?.entities || [])])r[e.id]={...r[e.id],...e};for(const e of [...(doc.players || []),...doc.segments.flatMap(s=>s.entities || [])])if(e.profile_snapshot && r[e.id])r[e.id].profile_snapshot=e.profile_snapshot;for(const e of Object.values(r))if(e.owner)e.class=r[e.owner]?.class;return r;};
    const label=e=>e ? `${e.name || e.id}${e.server ? " · " + e.server : ""}` : "Unknown / not recorded";
    const character=e=>e && ((doc.players || []).some(p=>p.id===e.id) || e.is_player || e.kind==="player");
    const actorHTML=e=>character(e)?`<button class="btn small" data-character="${esc(e.id)}" style="color:${color(e.class)}">${esc(label(e))}</button>`:esc(label(e));
    const profileImage=value=>{try{const u=new URL(value);return u.protocol==='https:' && ['assets.playnccdn.com','profileimg.plaync.com','metabot.gg','a2dil.com'].includes(u.hostname)?u.href:'';}catch(_){return '';}};
    const profileIcon=(value,label)=>{const url=profileImage(value);return url?`<img src="${esc(window.A2AssetHealth?A2AssetHealth.source(url):url)}" alt="${esc(label)}" loading="lazy" onerror="this.hidden=true">`:'<span class="cr-profile-empty" aria-label="Image unavailable">◇</span>';};
    const profileList=value=>Array.isArray(value)?value:[];
    const statLabel=row=>({아이템레벨:'Gear score (item level)'}[String(row.name||'').replace(/\s/g,'')] || row.name || row.type || 'Unnamed stat');
    const secondaryStat=row=>typeof row==='string'?row.trim():row && typeof row==='object' && (row.name||row.type) && row.value!==undefined && row.value!==null && row.value!==''?`${statLabel(row)}: ${row.value}`:'';
    function profileDetails(data,gear,skills){
      const profile=data.profile||{}, stats=profileList(data.stat?.statList), boards=profileList(data.daevanion?.boardList);
      const score=profile.gearScore ?? stats.find(row=>String(row.name||'').replace(/\s/g,'')==='아이템레벨' || /^(gear score|item level)$/i.test(String(row.name||'').trim()))?.value;
      const item=(entry,slot)=>`<article class="cr-profile-card" data-grade="${esc(entry.grade||'')}">${profileIcon(entry.icon,entry.name||slot)}<div><small>${esc(slot)}</small><strong>${esc(entry.name||entry.itemName||entry.id||'Unknown')}</strong><span>${entry.enchantLevel!==undefined?'+'+esc(entry.enchantLevel)+' · ':''}${esc(entry.grade||'')}${entry.level!==undefined?' · Lv '+esc(entry.level):''}</span></div></article>`;
      return `<div class="cr-profile-hero">${profileIcon(profile.profileImage,profile.characterName||'Character portrait')}<div><h2>${esc(profile.characterName||'Character')}</h2><p>Lv ${esc(profile.characterLevel??'Unavailable')} · ${esc(profile.className||'Unknown class')} · ${esc(profile.raceName||'')}<br>${esc(profile.serverName||profile.serverId||'Unknown server')} · ${esc(profile.regionName||data.region||'Unknown region')}<br>Gear score: ${esc(score??'Unavailable')}<br>Combat power: ${esc(profile.combatPower??'Unavailable')}</p></div></div>
        <h3>Character stats</h3><div class="cr-profile-stats">${stats.map(row=>`<div><strong>${esc(statLabel(row))}</strong><span>${esc(row.value??'Unavailable')}</span>${profileList(row.statSecondList).map(secondaryStat).filter(Boolean).map(text=>`<small>${esc(text)}</small>`).join('')}</div>`).join('')||'Stats were not included in this snapshot.'}</div>
        <h3>Equipment and inventory slots</h3><div class="cr-profile-grid">${gear.map(entry=>item(entry,entry.slotPosName||'Slot '+entry.slotPos)).join('')||'Equipment was not included in this snapshot.'}</div>
        <h3>Skills, passives and stigmas</h3><div class="cr-profile-grid">${skills.map(entry=>`<article class="cr-profile-card">${profileIcon(entry.icon,entry.name||'Skill')}<div><small>${esc(entry.category||'Skill')}</small><strong>${esc(entry.name||entry.skillName||entry.id)}</strong><span>Lv ${esc(entry.skillLevel??entry.level??'Unavailable')} · ${entry.equip===1||entry.equip===true?'Equipped':entry.equip===0||entry.equip===false?'Not equipped':'Equip state unavailable'}</span></div></article>`).join('')||'Skills were not included in this snapshot.'}</div>
        <h3>Pet and wings</h3><div class="cr-profile-grid">${Object.entries(data.petwing||{}).filter(([,entry])=>entry&&typeof entry==='object'&&!Array.isArray(entry)).map(([slot,entry])=>item(entry,slot)).join('')||'Pet and wings were not included in this snapshot.'}</div><p class="small muted">Pet genus is shown only when recorded: ${esc(data.petwing?.pet?.genusName||data.petwing?.pet?.genus||'not included in the official profile snapshot')}.</p>
        <h3>Daevanion boards</h3><div class="cr-profile-grid">${boards.map(entry=>`<article class="cr-profile-card">${profileIcon(entry.icon,entry.name||'Board')}<div><strong>${esc(entry.name||entry.id)}</strong><span>${entry.open?'Open':'Locked'} · ${esc(entry.openNodeCount??'?')} / ${esc(entry.totalNodeCount??'?')} nodes</span></div></article>`).join('')||'Boards were not included in this snapshot.'}</div>`;
    }
    function profileHTML() {
      if(!state.character)return "";
      const actor=refs()[state.character];if(!actor)return "";
      const saved=actor.profile_snapshot, preview=previews.get(actor.id), snapshot=preview || saved;
      const stamp=x=>x?new Date(x*1000).toLocaleString():"Not recorded";
      const data=snapshot?.data || {}, gear=profileList(data.equipment?.equipmentList), skills=profileList(data.skill?.skillList);
      return `<section class="win"><div class="wh"><h3>Character build · ${esc(label(actor))}</h3><button class="btn small" data-profile-close>← Back to log</button></div><div class="wb"><p class="note">${preview?"Current profile preview; this is not the historical build for this encounter.":saved?"Saved at upload time. Gear may have changed between the encounter and the official lookup. This snapshot will not refresh to newer gear.":"No historical official profile was saved with this log."}</p>
        <p>Status: ${esc(snapshot?.status || "unavailable")} · ${esc(snapshot?.reason || "")}<br>Upload received: ${esc(stamp(saved?.uploaded_at))} · Official fetch completed: ${esc(stamp(snapshot?.fetched_at))}</p>
        ${snapshot?.data?`<p>${esc(snapshot.source)} · ${esc(snapshot.identity?.name)} · ${esc(snapshot.identity?.region)} · Server ${esc(snapshot.identity?.server)}</p>${profileDetails(data,gear,skills)}<h3>Full recorded build information</h3><p class="small muted">Expand a section for equipment rolls, specialties, titles, skins, board nodes and other fields supplied by the official service.</p>${Object.entries(data).map(([key,value])=>`<details><summary>${esc(key.replaceAll('_',' '))}</summary><pre class="cr-profile-json">${esc(JSON.stringify(value,null,2))}</pre></details>`).join('')}<button class="btn small" data-profile-download>Export this profile JSON</button>`:""}
        ${preview?'<button class="btn small" data-profile-saved>Return to saved historical profile</button>':""}${options.lookupProfile?`<div class="row"><label>Region <select data-profile-region><option value="">Detect from server ID</option>${Object.entries({nae:"North America",eu:"Europe",as:"Asia",la:"Latin America"}).map(([key,value])=>`<option value="${key}" ${key===(actor.region || doc.meta?.region)?"selected":""}>${value}</option>`).join("")}</select></label><label>Character server ID <input data-profile-server type="number" min="1" step="1" value="${esc(actor.server || '')}" placeholder="Required when not recorded"></label><button class="btn small" data-profile-current>Fetch current official profile (not historical)</button></div><p class="small muted">Use this character's home server, not your own server. Manual lookup only previews current gear; it does not change the saved historical profile.</p>`:""}${snapshot?.status==="pending"?'<p class="small muted">The server is fetching this profile. Reopen the shared log in a moment to load its saved result.</p>':""}<span data-profile-message role="status"></span></div></section>`;
    }
    function bindProfile(){
      const close=root.querySelector('[data-profile-close]');if(close)close.onclick=()=>{state.character="";profileRequest++;render();};
      const saved=root.querySelector('[data-profile-saved]');if(saved)saved.onclick=()=>{previews.delete(state.character);render();};
      const current=root.querySelector('[data-profile-current]');if(current)current.onclick=async()=>{const id=state.character,request=++profileRequest;current.disabled=true;root.querySelector('[data-profile-message]').textContent='Fetching current official profile…';try{const actor=refs()[id],server=root.querySelector('[data-profile-server]').value.trim(),region=root.querySelector('[data-profile-region]').value;if(!server)throw Error('Enter this character’s numeric home server ID before fetching.');const result=await options.lookupProfile({...actor,server,region},region);if(request!==profileRequest)return;previews.set(id,result);render();}catch(e){if(request===profileRequest)root.querySelector('[data-profile-message]').textContent=e.message;}finally{if(current.isConnected)current.disabled=false;}};
      const download=root.querySelector('[data-profile-download]');if(download)download.onclick=()=>{const snapshot=previews.get(state.character) || refs()[state.character]?.profile_snapshot;const url=URL.createObjectURL(new Blob([JSON.stringify(snapshot,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='character-profile.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
    }
    const owner=(id,r)=>state.combine && r[id]?.owner ? r[id].owner : id;
    function data() {
      const segment=doc.segments[state.segment] || {duration:1,hits:[]};const r=refs();
      const recorded=segment.events || [];
      const events=(recorded.length ? recorded : (segment.hits || []).map(h=>({kind:"damage",t:h.t,source:h.source || h.player,target:h.target,amount:h.damage,skill:h.skill,skill_id:h.skill_id}))).slice().sort((a,b)=>a.t-b.t);
      const friendly=new Set((doc.players || []).map(p=>p.id));
      const seenDeaths=new Set();
      const rows=new Map();
      const row=id=>{const key=owner(id,r);if(!key)return null;if(!rows.has(key)) rows.set(key,{...(r[key] || {id:key,name:key}),damage:0,taken:0,healing:0,deaths:0});return rows.get(key);};
      for(const e of events) {
        if(e.kind==="death") {const key=e.target+":"+e.t;if(seenDeaths.has(key))continue;seenDeaths.add(key);if(friendly.has(e.target) || (!state.combine && r[e.target]?.owner)) {const p=row(e.target);if(p)p.deaths++;}continue;}
        if(e.kind==="damage") {
          if((friendly.has(e.source) || r[e.source]?.owner) && (!state.enemy || e.target===state.enemy)) {const p=row(e.source);if(p)p.damage+=e.amount;}
          if((friendly.has(e.target) || r[e.target]?.owner) && (!state.enemy || e.source===state.enemy)) {const p=row(e.target);if(p)p.taken+=e.amount;}
        }
        if(e.kind==="heal" && (friendly.has(e.source) || r[e.source]?.owner)) {const p=row(e.source);if(p)p.healing+=e.amount;}
      }
      return {segment,r,events,rows:[...rows.values()],friendly};
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
      const lines=Object.entries(series),total=Array(count).fill(0);
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
      const health=(d.segment.health||[]).filter(s=>s.t>=0 && s.t<=duration && (state.enemy?s.entity===state.enemy:d.r[s.entity]?.is_boss));
      let hpMax=1;for(const s of health)hpMax=Math.max(hpMax,s.max||s.current);
      const hp=[...new Set(health.map(s=>s.entity))].map(id=>`<polyline fill="none" stroke="#ef6262" stroke-width="1.5" points="${health.filter(s=>s.entity===id).map(s=>`${x(s.t)},${180-s.current*160/hpMax}`).join(' ')}"><title>${esc(label(d.r[id]))} HP (right scale)</title></polyline>`).join('');
      graphModel={duration,step,count,total,roll,lines,health,primary};
      return `<div class="cr-graph"><div class="row small"><label>Graph style <select data-graph-mode><option value="total" ${state.graphMode!=='players'?'selected':''}>Live style · bars + 10 s average</option><option value="players" ${state.graphMode==='players'?'selected':''}>Player series</option></select></label><span>${esc(primary)} per second · ${step}s buckets${health.length?' · red: boss HP, right scale':' · Boss HP: not recorded'}</span></div>
        <svg viewBox="0 0 1000 220" role="img" aria-label="Combat rate chart">${grid}${ticks}${paths}${hp}${health.length?`<text x="948" y="25" fill="#ef6262" font-size="11">${number(hpMax)}</text><text x="948" y="184" fill="#ef6262" font-size="11">0 HP</text>`:''}<path data-graph-cursor d="M60 20V180" stroke="currentColor" stroke-dasharray="3 3" visibility="hidden"/><rect data-graph-hit x="60" y="20" width="880" height="160" fill="transparent" tabindex="0" role="button" aria-label="Inspect graph time; use left and right arrow keys"/></svg>
        <div class="note small" data-graph-detail role="status">Hover or click the graph for rates. In Timeline view, click a time to move the timeline window there.</div><div class="cr-legend">${lines.map(([key,s])=>`<button class="btn small" data-series="${esc(key)}" style="color:${color(d.r[s.actor]?.class)}">${esc(label(d.r[s.actor]))} · ${s.kind}</button>`).join('')}<button class="btn small" data-showall>Show all series</button></div></div>`;
    }
    function encounters(d) {
      const enemies=(d.segment.entities || []).filter(e=>e.kind==="enemy");
      return `<h3>Enemy encounters</h3>${table(["Enemy","Creature type","Damage received","Observed lifespan"],enemies.map(e=>{
        const ee=d.events.filter(x=>x.source===e.id || x.target===e.id),damage=ee.filter(x=>x.kind==="damage" && x.target===e.id).reduce((n,x)=>n+x.amount,0);
        return `<tr><td>${e.is_player?actorHTML(e):esc(e.name || e.id)} <button class="btn small" data-enemy-filter="${esc(e.id)}">Filter${e.is_player?" (opponent)":e.is_boss?" (boss)":""}</button></td><td>${esc(e.mob_code ?? "Unknown")}</td><td>${number(damage)}</td><td>${ee.length?ee[0].t.toFixed(1)+"–"+ee[ee.length-1].t.toFixed(1)+"s":"—"}</td></tr>`;}))}<button class="btn small" data-clear-enemy>All enemies</button>`;
    }
    function timeline(d, events) {
      const duration=Math.max(1,d.segment.duration),span=Math.min(duration,Number(state.timelineWindow)||duration);
      state.timelineStart=Math.max(0,Math.min(Number(state.timelineStart)||0,duration-span));
      const start=state.timelineStart,end=start+span,width=Math.max(900,Math.min(8000,span*32));
      const inWindow=events.filter(e=>e.t>=start && (e.t<end || end===duration && e.t<=end));
      const ids=[...new Set(events.flatMap(e=>[owner(e.source,d.r),owner(e.target,d.r)]).filter(id=>id && (d.friendly.has(id)||d.r[id]?.owner)))];
      let omitted=0;
      const lanes=ids.map(id=>{
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
        return `<div class="cr-lane" style="grid-template-columns:180px ${width}px"><div class="cr-lane-name" style="color:${color(d.r[id]?.class)}">${actorHTML(d.r[id])}</div><svg class="cr-track" style="width:${width}px;height:84px" viewBox="0 0 ${width} 84" role="img" aria-label="${esc(label(d.r[id]))} recorded effects">${marks||'<text x="12" y="25" fill="currentColor" font-size="12">No effects in this window</text>'}</svg></div>`;
      }).join('');
      const tick=span<=30?1:span<=120?5:Math.ceil(span/120),major=tick*5;
      let ticks='';for(let t=Math.ceil(start/tick)*tick;t<=end;t+=tick){const x=(t-start)*width/span,long=Math.abs(t/major-Math.round(t/major))<.001;ticks+=`<path d="M${x} ${long?17:24}V32" stroke="currentColor" opacity=".6"/>${long?`<text x="${Math.max(22,Math.min(width-22,x))}" y="13" text-anchor="middle" fill="currentColor" font-size="11">${clock(t)}</text>`:''}`;}
      return `<h3>Recorded effect timeline</h3><div class="row small"><label>Window <select data-timeline-window>${[15,30,60,120,0].map(v=>`<option value="${v}" ${v===Number(state.timelineWindow)?'selected':''}>${v?v+' seconds':'Full encounter'}</option>`).join('')}</select></label><button class="btn small" data-time-prev ${start<=0?'disabled':''}>Earlier</button><button class="btn small" data-time-next ${end>=duration?'disabled':''}>Later</button><label>Start <input type="number" data-time-start min="0" max="${Math.max(0,duration-span)}" step=".5" value="${start.toFixed(1)}"></label><span>${clock(start)}–${clock(end)}</span></div><input class="cr-time-scrub" data-time-scrub aria-label="Timeline window start" type="range" min="0" max="${Math.max(0,duration-span)}" step=".5" value="${start}">
        <p class="small muted">Icons are recorded hits/heals, not cast starts or durations. Three stacks separate nearby effects. Green: healing; red: deaths; orange: damage taken. ${omitted?number(omitted)+' crowded markers omitted in this window; zoom in or use Events for every effect.':''} Unavailable skill images keep an ID tile.</p>
        <div class="cr-timeline"><div class="cr-lane cr-ruler" style="grid-template-columns:180px ${width}px"><div class="cr-lane-name">Encounter time</div><svg class="cr-track cr-time-axis" style="width:${width}px;height:34px" viewBox="0 0 ${width} 34">${ticks}</svg></div>${lanes||'No timeline effects recorded for these filters.'}</div><div class="note" data-effect-panel role="status">${esc(timelineDetail||'Hover, focus or click a skill icon to inspect its effect.')}</div><div class="cr-effect-tooltip" data-effect-tooltip role="tooltip" hidden></div>`;
    }
    function catalogHTML(d) {
      const c=doc.encounter_insights?.segments?.find(s=>s.segment===state.segment)?.catalog;
      if(!c)return '';
      return `<details class="note"><summary>Mapping coverage · ${c.unmapped.length}${c.omitted?'+':''} unresolved IDs</summary><p>${esc(c.note)}</p><p>Catalog ${esc(c.catalog_revision)} · Map ${esc(c.map_id || 'not recorded')} · Instance ${esc(c.instance_id || 'not recorded')} · ${number(c.npc_entities_without_type)} enemy references have no NPC type. ${c.omitted?`${number(c.omitted)} additional IDs omitted.`:''}</p>${table(['Kind','Recorded ID','Entity references','Recorded effects'],c.unmapped.map(r=>`<tr><td>${esc(r.kind)}</td><td>${esc(r.code)}</td><td>${number(r.entity_count)}</td><td>${number(r.effects)}</td></tr>`))}<button class="btn small" data-export-mappings>Export mapping report</button><span data-mapping-status role="status"></span></details>`;
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
        <h4>Boss HP milestones</h4><p class="small muted">First recorded sample at or below each threshold. A capture starting late can show several thresholds at the same time. No interpolation, named phase or exact crossing time is inferred; raw HP without an observed maximum cannot establish percentages.</p>
        ${table(['Boss','Threshold','First observed sample','Observed HP'],s.milestones.map(r=>`<tr><td>${esc(label(d.r[r.entity]))}</td><td>≤ ${r.threshold_pct}%</td><td>${r.t.toFixed(3)}s</td><td>${number(r.current)} / ${number(r.max)} (${r.observed_pct.toFixed(1)}%)</td></tr>`))}
        <h4>Healing relationships</h4><p class="small muted">${s.healing_without_source} healing effects lack a source; ${s.healing_without_target} lack a recipient. These are excluded from pairs, not assigned to a player. Recorded amounts do not establish effective healing or support contribution.</p>
        ${table(['Healer','Recipient','Recorded amount','Effects'],s.healing.filter(r=>(selected(r.source)||selected(r.target))&&!pet(r.source)&&!pet(r.target)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${actorHTML(d.r[r.target])}</td><td>${number(r.amount)}</td><td>${r.effects}</td></tr>`))}
        <h4>Imported buff windows</h4><p class="small muted">Overlapping windows for the same buff/recipient are merged and clipped to the encounter. Uptime uses total encounter duration. Buff caster, damage contribution and live buff coverage are unavailable. ${s.invalid_buff_windows} empty/reversed/outside windows excluded.</p>
        ${table(['Recipient','Buff','Observed duration','Encounter uptime','Merged windows'],s.buffs.filter(r=>selected(r.player)).map(r=>`<tr><td>${actorHTML(d.r[r.player])}</td><td>${ability(r)}</td><td>${r.seconds.toFixed(2)}s</td><td>${r.uptime_pct===null?'Unavailable':r.uptime_pct.toFixed(1)+'%'}</td><td>${r.windows}</td></tr>`))}
        <h4>Observed ability effects</h4><p class="small muted">Counts describe effects, not casts. First/last timestamps are observed effect times, not cooldown usage or action uptime.</p>
        ${table(['Source','Ability','Kind','Effects','Recorded amount','First → last'],s.skills.filter(r=>selected(r.source)&&!pet(r.source)).map(r=>`<tr><td>${actorHTML(d.r[r.source])}</td><td>${ability(r)}</td><td>${esc(r.kind)}</td><td>${r.effects}</td><td>${number(r.amount)}</td><td>${r.first.toFixed(3)} → ${r.last.toFixed(3)}s</td></tr>`))}
        <h4>Opening effect sequence</h4><p class="small muted">First 20 retained effects per player or pet, capped at 100 per encounter. This is an observed sequence, not a recommended rotation. Equal timestamps do not prove order.</p>
        ${table(['Time','Source','Target','Ability','Kind','Amount'],s.opening.filter(r=>selected(r.source)&&!pet(r.source)).map(r=>`<tr><td>${r.t.toFixed(3)}s</td><td>${actorHTML(d.r[r.source])}</td><td>${actorHTML(d.r[r.target])}</td><td>${ability(r)}</td><td>${esc(r.kind)}</td><td>${number(r.amount)}</td></tr>`))}
      </details>`;
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
      const values=x=>!x?'Unavailable — no eligible matched comparison is available. Check capture quality and encounter metadata above.':`<span title="${esc((x.reasons || []).join(' '))}">${x.rank===null?'Rank unavailable':`#${x.rank} / ${x.count}`}${x.provisional?' (provisional)':''}<br>${x.percentile===null || x.percentile===undefined?'Percentile unavailable':x.percentile.toFixed(1)+' percentile'}${x.public_samples!==undefined?` · ${x.public_samples} public samples · ${x.identities} distinct identities`:''}${x.reasons?.length?'<br>'+esc(x.reasons.join(' ')):''}</span>`;
      const scopes=x=>['server','region','world'].map(s=>`${s[0].toUpperCase()+s.slice(1)}: ${values(x?.[s])}`).join('<br>');
      return `<h3>Matched public comparisons</h3><p class="small muted">${esc(ranks.note || '')} ${esc(ranks.cohort_note || '')}</p>${table(['Player · party size','Current standings (same build)','At upload (reconstructed)'],(ranks.players || []).map(p=>`<tr><td>${esc(p.name)} · ${p.party_size || 'Unknown'} players${p.uploaded_at?`<br>Uploaded ${esc(new Date(p.uploaded_at*1000).toLocaleString())}`:''}</td><td>${scopes(p)}</td><td>${scopes(p.at_upload)}</td></tr>`))}<h4>Run speed · lower elapsed time wins</h4>${table(['Current standings (same build)','At upload (reconstructed)'],[`<tr><td>${scopes(ranks.run)}</td><td>${scopes(ranks.run_at_upload)}</td></tr>`])}`;
    }
    const seconds=x=>x===null || x===undefined?'Unavailable':`${Math.floor(x/60)}:${(x%60).toFixed(1).padStart(4,'0')}`;
    function runsHTML(d) {
      const analysis=doc.run_analysis, all=analysis?.runs || (ranks?.run_detail?[ranks.run_detail]:[]);
      if(!all.length)return '<p class="small muted">Run timing and progression are unavailable in this older recording.</p>';
      const shown=all.filter(r=>!state.run || r.id===state.run), current=all.find(r=>r.id===(d.segment.run_id || 'legacy'));
      if(String(d.segment.encounter_type || doc.meta?.encounter_type || '').startsWith('pvp_'))return `<details open class="note"><summary>PvP recorded timing</summary><p class="small muted">These intervals contain observed combat effects. They are not verified rounds or complete matches. Match score, round boundaries and player death coverage remain unverified.</p>${table(['Run','Recorded span','Recorded combat','Gaps / downtime'],shown.map(r=>`<tr><td>${esc(r.id)}</td><td>${seconds(r.recorded_span_seconds)}</td><td>${seconds(r.combat_seconds)}</td><td>${seconds(r.downtime_seconds)}</td></tr>`))}</details>`;
      return `<details open class="note"><summary>Run timing and boss progression</summary><p class="small muted">${esc(analysis?.note || '')}</p>${table(['Run','Recorded span','Entry → finish','Recorded combat','Gaps / downtime','Speed status'],shown.map(r=>`<tr><td>${esc(r.id)}</td><td>${seconds(r.recorded_span_seconds)}</td><td>${seconds(r.elapsed_seconds)}</td><td>${seconds(r.combat_seconds)}</td><td>${seconds(r.downtime_seconds)}</td><td>${r.speed_eligible?'Eligible':esc((r.speed_reasons || []).join(' '))}</td></tr>`))}
      ${current?`<h4>Run ${esc(current.id)} · boss attempts</h4>${table(['Boss','Recorded attempts','Kills','Observed wipes','Unknown','Attempts to first recorded clear','Best observed wipe HP','Wipe → next pull'],(current.progression || []).map(p=>`<tr><td>${esc(p.boss)}</td><td>${p.attempts}</td><td>${p.kills}</td><td>${p.wipes}</td><td>${p.unknown}</td><td>${p.attempts_to_first_clear??'Unavailable'}</td><td>${p.best_wipe_hp_pct===null?'Unavailable':p.best_wipe_hp_pct.toFixed(1)+'%'}</td><td>${(p.wipe_recovery_seconds || []).map(seconds).join(', ') || 'Unavailable'}</td></tr>`))}${table(['Attempt','Boss','Outcome','Recorded span','Lowest observed HP','Encounters'],(current.attempts || []).map(a=>`<tr><td>${a.attempt}</td><td>${esc(a.boss)}</td><td>${esc(a.outcome)}</td><td>${seconds(a.recorded_seconds)}</td><td>${a.best_remaining_hp_pct===null?'Unavailable':a.best_remaining_hp_pct.toFixed(1)+'%'}</td><td>${a.segments.map(i=>`<button class="btn small" data-attempt-segment="${i}">${esc(doc.segments[i]?.label || i+1)}</button>`).join(' ')}</td></tr>`))}`:''}</details>`;
    }
    function render() {
      if(replayFrame)cancelAnimationFrame(replayFrame);replayFrame=null;
      if(state.character && refs()[state.character]){root.innerHTML='<div data-profile>'+profileHTML()+'</div>';bindProfile();return;}
      if(!doc.segments.some(matchesMode)){root.innerHTML='<p class="note">No encounters recorded for this combat mode.</p><button class="btn small" data-show-all>Show all recorded encounters</button>';root.querySelector('[data-show-all]').onclick=()=>{state.mode='';state.run='';render();requestRanks();};return;}
      if(!doc.segments[state.segment] || !matchesMode(doc.segments[state.segment])){state.segment=doc.segments.findIndex(matchesMode);state.run='';state.actor='';state.enemy='';ranks=null;}
      const d=data(),events=visibleEvents(d),duration=Math.max(1,d.segment.duration),metric=state.metric==="summary"?"damage":state.metric;
      const quality=ranks?.quality || d.segment.quality;
      const driver=quality?.driver_monitoring;
      const driverHTML=driver?`<p>Capture driver: ${driver.sampled?`${driver.partial?'partial coverage · ':''}${number(driver.pcap_received)} received · ${number(driver.pcap_dropped)} capture-buffer drops · ${number(driver.pcap_if_dropped)} interface/driver drops`:'unavailable / not recorded'}. ${esc(driver.note)}</p>`:'';
      const qualityHTML=`<details class="note" open><summary>Capture quality · ${quality?.eligible?'Eligible for community rankings':'Unranked / completeness unverified'}</summary>${quality?`<ul>${(quality.messages || []).map(m=>`<li>${esc(m)}</li>`).join('')}</ul><p>${esc(quality.note)}</p>${driverHTML}`:'<p>This older log does not contain a capture-quality assessment. It remains available for review.</p>'}${ranks?.duplicate?'<p>Another public upload of this encounter was detected. Matching player samples count once.</p>':''}</details>`;
      const runs=[...new Set(doc.segments.filter(matchesMode).map(s=>s.run_id || "legacy"))];
      const runMenu=runs.some(id=>id!=="legacy")?`<label>Run <select data-control="run"><option value="">All runs</option>${runs.map(id=>`<option value="${esc(id)}" ${state.run===id?'selected':''}>Run ${esc(id)}</option>`).join('')}</select></label><span class="small muted">Run ${esc(d.segment.run_id || "legacy")} · ${d.segment.run_complete?'Finished':'Unfinished / completion unverified'} · ${esc(d.segment.run_end_reason || '')}</span>`:"";
      const rows=d.rows.filter(p=>!state.actor || p.id===state.actor).sort((a,b)=>b[metric]-a[metric]);
      const summary=table(["Player / server","Class","Damage done","DPS","Damage taken","Healing","HPS","Deaths"],rows.map(p=>`<tr><td style="color:${color(p.class)}">${actorHTML(p)}</td><td>${esc(p.class || "Unknown")}</td><td>${number(p.damage)}</td><td>${number(p.damage/duration)}</td><td>${number(p.taken)}</td><td>${number(p.healing)}</td><td>${number(p.healing/duration)}</td><td>${p.deaths || 'No markers'}</td></tr>`));
      const skills=new Map();for(const e of events) {if(e.kind==="death" || (state.metric==="summary" && (e.kind!=="damage" || !(d.friendly.has(e.source) || d.r[e.source]?.owner))))continue;const actor=owner(state.metric==="taken"?e.target:e.source,d.r);const key=actor+":"+e.kind+":"+(e.skill_id || e.skill);const row=skills.get(key) || {actor,kind:e.kind,skill:e.skill || e.skill_id || "Unknown",amount:0,hits:0,min:Infinity,max:0};row.amount+=e.amount || 0;row.hits++;row.min=Math.min(row.min,e.amount || 0);row.max=Math.max(row.max,e.amount || 0);skills.set(key,row);}
      const skillRows=[...skills.values()].sort((a,b)=>b.amount-a.amount),skillTotal=skillRows.reduce((total,s)=>total+s.amount,0);
      const breakdown=table(["Player / server","Ability","Effects","Amount","Share","Per second","Average","Minimum","Maximum"],skillRows.map(s=>`<tr><td style="color:${color(d.r[s.actor]?.class)}">${actorHTML(d.r[s.actor])}</td><td>${esc(s.skill)}${s.kind==="heal"?" (heal)":""}</td><td>${s.hits}</td><td>${number(s.amount)}</td><td>${skillTotal?(100*s.amount/skillTotal).toFixed(1):0}%</td><td>${number(s.amount/duration)}</td><td>${number(s.amount/s.hits)}</td><td>${number(s.min)}</td><td>${number(s.max)}</td></tr>`));
      const skillChart=state.graph && skillRows.length?`<h3>Ability contribution · ${state.metric==="healing"?"healing":state.metric==="taken"?"damage taken":"damage done"}</h3><p class="small muted">Top 20 player/ability rows; all recorded abilities appear in the table. Select a player to inspect their contribution.</p><svg width="100%" viewBox="0 0 1000 ${Math.min(20,skillRows.length)*30}" role="img" aria-label="Amount by player and ability">${skillRows.slice(0,20).map((s,i)=>`<text x="0" y="${i*30+19}" fill="#c8d3df" font-size="13">${esc((label(d.r[s.actor])+" · "+s.skill).slice(0,55))}</text><rect x="440" y="${i*30+3}" width="${450*s.amount/Math.max(1,skillRows[0].amount)}" height="22" fill="${color(d.r[s.actor]?.class)}"><title>${esc(label(d.r[s.actor])+" · "+s.skill+" · "+number(s.amount))}</title></rect><text x="990" y="${i*30+19}" text-anchor="end" fill="#c8d3df" font-size="13">${number(s.amount)}</text>`).join('')}</svg>`:"";
      const pageCount=Math.max(1,Math.ceil(events.length/100));state.page=Math.min(state.page,pageCount-1);
      const eventTable=table(["Time","Event","Caster / attacker","Recipient / target","Ability","Amount"],events.slice(state.page*100,(state.page+1)*100).map(e=>`<tr><td>${e.t.toFixed(3)}s</td><td>${esc(e.kind)}</td><td>${actorHTML(d.r[e.source])}</td><td>${actorHTML(d.r[e.target])}</td><td>${esc(e.skill || e.skill_id || "—")}</td><td>${e.kind==="death"?"—":number(e.amount)}</td></tr>`));
      root.innerHTML=`<section class="win cr-review"><div class="wh"><h2>${esc(doc.meta?.title || "Combat log")}</h2><span>${duration.toFixed(1)}s</span></div><div class="wb">
        <div class="row"><label>Combat mode <select data-control="mode"><option value="" ${!state.mode?'selected':''}>All recorded modes</option><option value="pve" ${state.mode==='pve'?'selected':''}>PvE</option><option value="pvp" ${state.mode==='pvp'?'selected':''}>PvP</option></select></label>${runMenu}${options.live?`<label><input type="checkbox" data-control="followLatest" ${state.followLatest?'checked':''}> Follow latest encounter</label>`:''}<label>Encounter <select data-control="segment">${doc.segments.map((s,i)=>(!matchesMode(s) || (state.run && (s.run_id || "legacy")!==state.run))?"":`<option value="${i}" ${i===state.segment?"selected":""}>${esc(s.label || s.boss || "Combat "+(i+1))}</option>`).join("")}</select></label><label>Player <select data-control="actor"><option value="">All players</option>${d.rows.map(p=>`<option value="${esc(p.id)}" ${p.id===state.actor?"selected":""}>${esc(label(p))}</option>`).join("")}</select></label><button class="btn small" data-color-settings>Class colors</button>${window.A2AssetHealth?'<button class="btn small" data-retry-images>Retry images</button>':''}<label><input type="checkbox" data-control="insights" ${state.insights?"checked":""}> Encounter insights</label></div>
        ${(d.segment.encounter_type||doc.meta?.encounter_type||'').startsWith('pvp_')?'<p class="note">PvP recording · matched by mode, arena/encounter, ruleset and build. Opponents are outside the recorded Self/Party roster. Only observed combat effects are shown; match results, objectives and kill credit are not inferred.</p>':''}
        <p class="small muted">${doc.meta?.installed_build?`Installed build: ${esc(doc.meta.installed_build)} (${esc(doc.meta.installed_build_source)}). `:""}${d.segment.game_patch||doc.meta?.game_patch?`Build source: ${esc(buildLabel(d.segment.game_patch_source||doc.meta?.game_patch_source||"source not recorded"))}. `:""}${d.segment.zone?`Zone: ${esc(d.segment.zone)} · ${esc(d.segment.zone_source || "source not recorded")}. `:""}${d.segment.difficulty?`Difficulty: ${esc(d.segment.difficulty)} · ${esc(d.segment.difficulty_source || "source not recorded")}. `:""}${d.segment.encounter_type_source?`Encounter type source: ${esc(d.segment.encounter_type_source)}. `:""}${doc.meta?.region_source?`Region source: ${esc(doc.meta.region_source)}.`:""}</p>
        ${doc.meta?.archive?`<p class="note">Archive ${esc(doc.meta.archive.id)} · Part ${esc(doc.meta.archive.part)}. Other parts are separate logs; this view does not combine their totals.</p>`:''}${qualityHTML}${catalogHTML(d)}${state.mode?'<p class="small muted">Showing only encounters recorded as '+state.mode.toUpperCase()+'. Whole-run timing is hidden in this filtered view.</p>':runsHTML(d)}<div class="cr-tabs">${["summary","damage","taken","healing","deaths"].map((v,i)=>`<button class="btn small ${state.metric===v?"primary":""}" data-metric="${v}">${["Summary","Damage Done","Damage Taken","Healing","Death recaps"][i]}</button>`).join("")}<span class="cr-spacer"></span>${["table","timeline","events"].map(v=>`<button class="btn small ${state.view===v?"primary":""}" data-view="${v}">${v[0].toUpperCase()+v.slice(1)}</button>`).join("")}</div>
        <div class="cr-options">${[["graph","Graph"],["timeline","Timeline"],["skills","Skills"],["deaths","Deaths"],["heals","Healing"],["pets","Pets"],["combine","Combine pets with owner"]].map(([key,label])=>`<label><input type="checkbox" data-control="${key}" ${state[key]?"checked":""}> ${label}</label>`).join("")}</div>
        <div class="row"><span>Character builds:</span>${Object.values(d.r).filter(character).map(actorHTML).join(" ")}</div><div data-profile>${profileHTML()}</div><div data-colors hidden></div>${state.graph && state.metric!=="deaths"?graph(d,events):""}${encounters(d)}${state.metric==="deaths"?recapsHTML(d):""}${state.insights?insightsHTML(d):""}
        ${state.view==="table" ? summary+(state.metric!=="deaths"?skillChart+breakdown:"") : state.view==="events" ? eventTable+`<div class="row"><button class="btn small" data-prev>Previous</button> ${state.page+1} / ${pageCount} · ${events.length} events <button class="btn small" data-next>Next</button></div>` : ""}
        ${state.timeline && state.view==="timeline" ? timeline(d,events):""}
        <p class="small muted">${d.events.some(e=>e.kind==="heal"&&!e.target)?"Some healing recipients are not carried by their packet variant. ":""}${!d.events.some(e=>e.kind==="death")?"No death markers recorded; zero counts do not establish a deathless run. ":""}${!(d.segment.positions || []).length?"Movement replay is unavailable: no verified positions were recorded.":""}</p>
        ${reportHTML()}${metadataHTML(d)}${ranksHTML(d)}${options.rankings?'<button class="btn small" data-rank-refresh>Refresh rankings</button>':""}${options.publish?'<details><summary>Publish this log</summary><div class="row"><select data-upload-vis aria-label="Upload visibility"><option>unlisted</option><option>public</option><option>private</option></select><button class="btn small" data-upload>Upload saved session</button><span data-upload-result></span></div></details>':""}<div data-replay></div>
        <div class="row"><input data-compare placeholder="Another public log ID" aria-label="Log ID to compare"><button class="btn small" data-compare-go ${options.compare?"":"disabled"}>Compare log</button><span data-compare-result></span><input type="file" data-compare-file accept=".json" aria-label="Compare a local a2log file"></div>
        <div data-comparison>${comparisonHTML(d)}</div>
      </div></section>`;
      root.querySelectorAll("[data-control]").forEach(e=>e.onchange=()=>{
        const key=e.dataset.control;
        if(key==='combine' && e.checked && state.actor)state.actor=refs()[state.actor]?.owner || state.actor;
        state[key]=e.type==='checkbox'?e.checked:key==='segment'?+e.value:e.value;state.page=0;
        if(key==='run' || key==='segment')state.followLatest=false;
        const changedEncounter=['mode','run','segment','followLatest'].includes(key);
        if(key==='mode'){state.run='';state.segment=Math.max(0,doc.segments.findIndex(matchesMode));}
        if(key==='run'){const index=doc.segments.findIndex(s=>matchesMode(s) && (!state.run || (s.run_id || 'legacy')===state.run));state.segment=Math.max(0,index);}
        if(changedEncounter){state.enemy='';state.actor='';ranks=null;state.timelineStart=0;timelineDetail='';}
        selectLatest();render();if(changedEncounter)requestRanks();
      });
      const mapping=root.querySelector('[data-export-mappings]');if(mapping)mapping.onclick=()=>{const c=doc.encounter_insights.segments.find(s=>s.segment===state.segment).catalog;const url=URL.createObjectURL(new Blob([JSON.stringify(c,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='aion2-mapping-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);root.querySelector('[data-mapping-status]').textContent='Mapping report download started.';};
      root.querySelectorAll("[data-recap]").forEach(e=>e.onclick=()=>{state.recap=+e.dataset.recap;render();});
      root.querySelectorAll("[data-metric]").forEach(e=>e.onclick=()=>{state.metric=e.dataset.metric;state.page=0;render();});
      root.querySelectorAll("[data-view]").forEach(e=>e.onclick=()=>{state.view=e.dataset.view;if(state.view==="timeline")state.timeline=true;render();});
      root.querySelectorAll('[data-attempt-segment]').forEach(e=>e.onclick=()=>{state.segment=+e.dataset.attemptSegment;state.timelineStart=0;timelineDetail="";state.enemy='';state.actor='';ranks=null;requestRanks();render();});
      root.querySelectorAll("[data-enemy-filter]").forEach(e=>e.onclick=()=>{state.enemy=e.dataset.enemyFilter;render();});
      root.querySelector("[data-clear-enemy]").onclick=()=>{state.enemy="";render();};
      root.querySelectorAll("[data-series]").forEach(e=>e.onclick=()=>{state.hidden.add(e.dataset.series);render();});
      if(root.querySelector("[data-showall]"))root.querySelector("[data-showall]").onclick=()=>{state.hidden.clear();render();};
      if(root.querySelector("[data-prev]"))root.querySelector("[data-prev]").onclick=()=>{state.page=Math.max(0,state.page-1);render();};
      if(root.querySelector("[data-next]"))root.querySelector("[data-next]").onclick=()=>{state.page++;render();};
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
          const parts=[clock(inspected,true),m.primary+': '+number(m.total[i])+'/s','10 s average: '+number(m.roll[i])+'/s'];
          for(const [,s] of m.lines.slice(0,8))parts.push(label(d.r[s.actor])+' · '+s.kind+': '+number(s.values[i])+'/s');
          if(m.lines.length>8)parts.push((m.lines.length-8)+' additional series; select a player for detail');
          for(const id of new Set(m.health.map(s=>s.entity))){const sample=m.health.filter(s=>s.entity===id && s.t<=inspected).at(-1);if(sample)parts.push(label(d.r[id])+' HP: '+number(sample.current)+' (sample '+clock(sample.t,true)+')');}
          root.querySelector('[data-graph-detail]').textContent=parts.join(' · ');const cursor=root.querySelector('[data-graph-cursor]');cursor.setAttribute('d','M'+(60+880*inspected/m.duration)+' 20V180');cursor.setAttribute('visibility','visible');};
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
      return `<details><summary>Encounter metadata for comparisons</summary><p class="small muted">Correct completed recordings here. Choose this encounter or its recorded run for changed build, category, difficulty and zone fields. Unchanged fields are preserved. Boss name applies only to this encounter; region applies to the session. Saving changes the local log; an uploaded copy is unchanged.</p><div class="row"><label>Apply changed fields to <select data-meta-scope><option value="encounter">This encounter</option>${d.segment.run_id?'<option value="run">All encounters in this run</option>':''}</select></label><label>Encounter type <select data-meta="encounter_type">${Object.entries(window.A2Community?.types || {unknown:'Unknown'}).map(([v,l])=>`<option value="${v}" ${v===(d.segment.encounter_type||doc.meta?.encounter_type||'unknown')?'selected':''}>${esc(l)}</option>`).join('')}</select></label>${['game_patch','difficulty','region','boss','zone'].map(k=>`<label>${esc(k==='game_patch'?'game build':k.replaceAll('_',' '))} <input data-meta="${k}" value="${esc(d.segment[k]||doc.meta?.[k]||'')}" maxlength="200"></label>`).join('')}<button class="btn small" data-meta-save>Save metadata</button><span data-meta-result></span></div></details>`;
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
    async function requestRanks() {if(!options.rankings)return;const request=++rankRequest;try{const response=await options.rankings(state.segment,doc);if(request!==rankRequest)return;ranks=response;}catch(e){ranks={error:e.message};}if(root.isConnected)render();}
    const api={update(next){doc=next;state.segment=Math.min(state.segment,doc.segments.length-1);const changed=selectLatest();render();if(changed)requestRanks();},state,dispose(){rankRequest++;profileRequest++;if(replayFrame)cancelAnimationFrame(replayFrame);}};
    selectLatest();render();requestRanks();return api;
  }
  window.A2CombatReview={mount,color,settings};
})();
