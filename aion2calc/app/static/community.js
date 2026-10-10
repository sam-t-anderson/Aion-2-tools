/* Public community reports, shared by desktop and Pages. */
(function(){
"use strict";
const buildLabel=x=>String(x??'').replace(/version:product:([0-9.]+)/g,(_,v)=>'Product version '+v.split('.').slice(0,4).join('.')).replace(/build:steam:[0-9]{1,12}:([0-9]{1,20})/g,'Legacy build $1 · Steam').replace(/build:purple:A2_[A-Z0-9_]{1,80}_PURPLE:([0-9]{1,20})/g,'Legacy build $1 · PURPLE');
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const types={unknown:"Unknown",pve_open_world:"PvE · Open world",pve_unverified:"PvE · Unverified source",transcendence:"Transcendence dungeon",daily:"Daily dungeon",expedition:"Expedition",ascension:"Ascension trials",nightmare:"Nightmare",sanctuary:"Sanctuary raids",pvp_battleground:"PvP · Battleground",pvp_arena:"PvP · Arena",pvp_abyss:"PvP · Abyss",pvp_rift:"PvP · Rift",pvp_open_world:"PvP · Open world",pvp_other:"PvP · Unverified / other"};
const n=x=>Math.round(x||0).toLocaleString();
const table=(heads,rows)=>`<div class="cr-scroll"><table class="t"><tr>${heads.map(x=>`<th>${x}</th>`).join("")}</tr>${rows.join("")||`<tr><td colspan="${heads.length}">No matching public submissions.</td></tr>`}</table></div>`;
const classes=['gladiator','templar','assassin','ranger','sorcerer','spiritmaster','cleric','chanter'];
function encounterIcons(log,mode){
 const fallback='static/logo.png';
 const rows=mode==='pvp'?[...new Set(log.opponent_classes||[])].filter(c=>classes.includes(c)).map(c=>({name:c,icon:'https://metabot.gg/web/aion2/classes/'+c+'.webp'})):(log.bosses||[]).map(b=>({name:b.name||'Recorded boss',icon:b.icon||window.A2BundledAssets?.npcs?.[b.id]||fallback}));
 if(!rows.length)rows.push({name:mode==='pvp'?'Opponent class not recorded':'No catalog-confirmed boss recorded',icon:fallback});
 return rows.map(row=>`<img src="${esc(window.A2AssetHealth?A2AssetHealth.source(row.icon):row.icon)}" width="30" height="30" loading="lazy" alt="${esc(row.name)}" title="${esc(row.name)}${row.icon===fallback?' (AION 2 emblem placeholder)':''}" style="object-fit:contain;margin:3px;border-radius:3px" onerror="this.onerror=null;this.src='static/logo.png'">`).join('');
}
function mount(root,options){
 let page=1,recordPage=1,loadRequest=0,query={combat_mode:"pve",metric:"dps"},identity={},consistencyRequest=0;
 function bossPortrait(row){const id=/^npc:([0-9]+)$/.exec(String(row.boss_key||''))?.[1],url=id&&window.A2BundledAssets?.npcs?.[id];return `<img width="24" height="24" src="${esc(url?(window.A2AssetHealth?A2AssetHealth.source(url):url):'static/logo.png')}" alt="" loading="lazy" onerror="this.onerror=null;this.src='static/logo.png'">`;}
 root.innerHTML=`<h3>Community combat logs</h3><p class="small muted">Public submissions only. Filters also apply to class performance and personal records. Product versions are recorded or submitted metadata; the latest submitted version may differ from the installed version. Older captures can retain legacy launcher metadata.</p><div class="row" data-filters></div><p data-message class="small muted"></p><div data-logs></div><div class="row"><button class="btn small" data-prev>Previous</button><span data-page></span><button class="btn small" data-next>Next</button></div><details data-boss-panel style="margin:8px 0"><summary>Recorded boss defeats</summary><p class="small muted">Public defeat observations, filtered by game game version and region. Other combat-log filters do not apply here. A recorded defeat does not establish whether a boss is currently available.</p><div class="row"><label class="small">Search displayed bosses <input data-boss-search placeholder="Boss name or NPC ID" aria-label="Search displayed boss observations"></label><button class="btn small" data-boss-refresh>Refresh boss observations</button></div><p class="small muted" data-boss-message role="status">Expand to load recorded defeats.</p><div data-boss-rows></div></details><h3>Completed-run speed</h3><div data-run-ranks></div><h3>Boss progression</h3><div data-encounter-progression></div><h3>Class performance</h3><p class="small muted">Recorded rates, separate PvE/PvP distributions for each boss, difficulty, encounter type and build. Sample size and gear can affect these comparisons.</p><div data-performance></div><h3>Highest observed build points</h3><div data-progression></div><h3>Personal records</h3><div class="row"><input data-name placeholder="Character name" aria-label="Character name"><input data-server placeholder="Character server ID" aria-label="Character server ID"><input data-character placeholder="Database character ID (optional)" aria-label="Database character ID"><button class="btn small" data-record-search>Find records</button></div><p data-record-note class="small muted"></p><div data-records></div><div data-history></div><h3>Character consistency and trends</h3><div data-consistency>Search a character above to compare matched recordings.</div><div class="row"><button class="btn small" data-record-prev>Previous records</button><span data-record-page></span><button class="btn small" data-record-next>Next records</button></div>`;
 const $=s=>root.querySelector(s),params=()=>new URLSearchParams(Object.entries(query).filter(([,v])=>v));
 let bossRequest=0,bossData=null;
 const bossPanel=$('[data-boss-panel]');
 const validTime=x=>typeof x==='number'&&Number.isFinite(x);
 const localTime=x=>validTime(x)?new Date(x*1000).toLocaleString():'Timestamp unavailable';
 const age=x=>!validTime(x)?'Age unavailable':x<60?'Less than a minute ago':x<3600?Math.floor(x/60)+' minutes ago':x<86400?Math.floor(x/3600)+' hours ago':Math.floor(x/86400)+' days ago';
 function renderBosses(){
  if(!bossData)return;
  const term=$('[data-boss-search]').value.trim().toLocaleLowerCase();
  const rows=(bossData.groups||[]).filter(x=>(String(x.boss||'')+' '+String(x.npc_id||'')).toLocaleLowerCase().includes(term));
  $('[data-boss-message]').textContent=`${rows.length} displayed boss/context groups. Snapshot ${localTime(bossData.generated_at)} (local time).${bossData.truncated?' Results capped; search filters only the displayed groups.':''}`;
  $('[data-boss-rows]').innerHTML=table(['Boss / NPC ID','Region · build','Map / instance','Last recorded defeat (local time)','Defeat / party observations','Latest engagement / roster','Current availability','Source log'],rows.map(x=>{
   const last=x.latest_observation||{};
   const id=String(x.last_log_id||'');
   const source=/^[A-Za-z0-9]{6,16}$/.test(id)?`<button class="btn small" data-boss-open="${esc(id)}">Open log${Number.isInteger(x.last_segment)?' · encounter '+(x.last_segment+1):''}</button>`:'Source unavailable';
   return `<tr><td>${esc(x.boss||'Unnamed boss')}<br><span class="small muted">${esc(x.npc_id||'ID unavailable')}</span></td><td>${esc(x.region||'Unknown region')}<br>${esc(buildLabel(x.game_patch||'Unknown game version'))}</td><td>${esc(x.map_id||'Unknown')} / ${esc(x.instance_id||'Unknown')}</td><td>${esc(localTime(x.last_defeat_at))}<br><span class="small muted">${esc(age(x.seconds_since_defeat))}</span>${last.timing_basis&&last.timing_basis!=='recorded_clock'?'<br><span class="small muted">'+esc(last.timing_basis.replaceAll('_',' '))+'</span>':''}</td><td>${n(x.observed_defeats)} / ${n(x.party_observations)}</td><td>${n(last.engaged_roster_members)} engaged<br>${last.recorded_roster_members?n(last.recorded_roster_members)+' recorded roster members'+(last.party_roster_complete?' (complete)':' (partial)'):'Party roster unavailable'}</td><td>Unknown<br><span class="small muted">Respawn rule and location scope unverified</span></td><td>${source}</td></tr>`;
  }));
  $('[data-boss-rows]').insertAdjacentHTML('beforeend','<p class="small muted">Counts describe submitted observations, not verified unique kills or kill credit. Exact duplicate encounters count once; different perspectives can still repeat a defeat. Defeat times use the recording computer clock. Boss roles may include minibosses. Physical server/channel and respawn times are unavailable.</p>');
  root.querySelectorAll('[data-boss-open]').forEach(b=>b.onclick=()=>options.open(b.dataset.bossOpen,'pve'));
 }
 async function loadBosses(){
  if(query.combat_mode!=='pve'||!bossPanel.open)return;
  const request=++bossRequest,q=new URLSearchParams();
  for(const key of ['game_patch','region'])if(query[key])q.set(key,query[key]);
  $('[data-boss-message]').textContent='Loading recorded boss defeats…';
  $('[data-boss-refresh]').disabled=true;
  try{
   const result=await options.api('/api/v1/boss-status?'+q);
   if(request!==bossRequest||!root.isConnected)return;
   bossData=result;renderBosses();
  }catch(e){
   if(request!==bossRequest)return;
   $('[data-boss-message]').textContent='Boss observations could not be loaded. Refresh to retry; this requires an updated community server.';
   $('[data-boss-rows]').replaceChildren();bossData=null;
  }finally{if(request===bossRequest)$('[data-boss-refresh]').disabled=false;}
 }
 function syncBosses(){
  bossRequest++;bossData=null;
  bossPanel.hidden=query.combat_mode!=='pve';
  $('[data-boss-rows]').replaceChildren();
  $('[data-boss-refresh]').disabled=false;
  $('[data-boss-message]').textContent='Expand to load recorded defeats.';
  if(!bossPanel.hidden&&bossPanel.open)loadBosses();
 }
 bossPanel.ontoggle=()=>{if(bossPanel.open&&!bossData)loadBosses();};
 $('[data-boss-search]').oninput=renderBosses;
 $('[data-boss-refresh]').onclick=loadBosses;
 async function load(){
  const request=++loadRequest;
  syncBosses();
  $('[data-message]').textContent='Loading…';
  try{
   const q=params();q.set('page',page);q.set('limit',30);
   const [logs,perf]=await Promise.all([options.api('/api/v1/logs?'+q),options.api('/api/v1/performance?'+params())]);
   if(request!==loadRequest)return;
   $('[data-message]').textContent=`${logs.total||0} matching public logs`;
   $('[data-page]').textContent=`Page ${page}`;
   $('[data-prev]').disabled=page===1;$('[data-next]').disabled=page*30>=logs.total;
   $('[data-logs]').innerHTML=table(['Encounter / session','Events · version · encounters','Players','Top DPS','Recorded'],(logs.logs||[]).map(l=>`<tr><td><div class="community-encounter-name" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><button class="btn small" data-open="${esc(l.id)}">${esc(l.title||l.boss||l.id)}</button></div>${query.combat_mode!=='pvp'?(l.bosses||[]).map(b=>`<div class="community-boss-name" style="display:flex;align-items:center;gap:6px;margin:4px 0"><img width="24" height="24" src="${esc(window.A2AssetHealth?A2AssetHealth.source(b.icon||window.A2BundledAssets?.npcs?.[b.id]||'static/logo.png'):b.icon||window.A2BundledAssets?.npcs?.[b.id]||'static/logo.png')}" alt="" onerror="this.onerror=null;this.src='static/logo.png'"> ${esc(b.name||'Recorded boss')}</div>`).join(''):''}</td><td><div>${l.event_count===undefined?'Event count unavailable':n(l.event_count)+' recorded events'} · ${[...new Set((l.contexts||[]).map(c=>c.game_patch||'Unknown game version'))].map(x=>esc(buildLabel(x))).join(', ')||'Unknown game version'}</div><div aria-label="${query.combat_mode==='pvp'?'Opponent classes':'Recorded bosses'}">${encounterIcons(l,query.combat_mode)}</div></td><td>${l.players?.length||0}</td><td>${n(l.top_dps)}</td><td>${new Date(l.created_at*1000).toLocaleString()}</td></tr>`));
   const timing=x=>x===null || x===undefined?'Unavailable':`${Math.floor(x/60)}:${(x%60).toFixed(1).padStart(4,'0')}`;
   options.api('/api/v1/run-leaderboard?'+params()).then(r=>{if(request!==loadRequest)return;
    $('[data-run-ranks]').innerHTML=`<p class="small muted">${esc(r.note)} ${r.samples||0} run samples; showing up to 50.${r.truncated?' Dataset capped.':''}</p>`+table(['Run','Instance · route','Type · version · difficulty','Party','Matched rank · percentile','Elapsed','Recorded combat','Downtime'],(r.entries||[]).map(x=>`<tr><td><button class="btn small" data-open="${esc(x.log)}">Run ${esc(x.id)}</button></td><td>${esc(x.instance_id)} · ${esc((x.boss_route||[]).join(' → '))}</td><td>${esc(types[x.encounter_type])} · ${esc(buildLabel(x.game_patch))} · ${esc(x.difficulty)}</td><td>${x.party_size}</td><td>#${x.rank} / ${x.count}<br>${x.comparison?.percentile!==null && x.comparison?.percentile!==undefined?x.comparison.percentile.toFixed(1)+' percentile':'Percentile unavailable'}<br>${esc((x.comparison?.reasons||[]).join(' '))}</td><td>${timing(x.elapsed_seconds)}</td><td>${timing(x.combat_seconds)}</td><td>${timing(x.downtime_seconds)}</td></tr>`));bindOpen();
   }).catch(e=>{if(request!==loadRequest)return;$('[data-run-ranks]').textContent='Run rankings unavailable: '+e.message;});
   options.api('/api/v1/encounter-progression?'+params()).then(r=>{if(request!==loadRequest)return;
    $('[data-encounter-progression]').innerHTML=`<p class="small muted">${esc(r.note)}${r.truncated?' Dataset capped.':''}</p>`+table(['Boss','Type · version · difficulty','Recorded attempts','Kills','Observed wipes','Unknown','Kill rate among known outcomes','Best observed wipe HP'],(r.groups||[]).map(x=>`<tr><td><span class="community-boss-name">${bossPortrait(x)}${esc(x.boss)}</span></td><td>${esc(types[x.encounter_type])} · ${esc(buildLabel(x.game_patch||'Unknown'))} · ${esc(x.difficulty||'Unknown')}</td><td>${x.attempts}</td><td>${x.kills}</td><td>${x.wipes}</td><td>${x.unknown}</td><td>${x.observed_kill_rate===null?'Unavailable':(100*x.observed_kill_rate).toFixed(1)+'%'}</td><td>${x.best_wipe_hp_pct===null?'Unavailable':x.best_wipe_hp_pct.toFixed(1)+'%'}</td></tr>`));
   }).catch(e=>{if(request!==loadRequest)return;$('[data-encounter-progression]').textContent='Boss progression unavailable: '+e.message;});
   const buckets=new Map();for(const g of perf.groups||[]){const k=[g.boss,g.boss_key,g.encounter_type,g.game_patch,g.difficulty,'Party '+(g.party_size||'unknown'),'Instance '+(g.instance_id||'unknown')].join(' · ');if(!buckets.has(k))buckets.set(k,[]);buckets.get(k).push(g);}
   $('[data-performance]').innerHTML=`<p class="small muted">${esc(perf.note)} ${perf.samples||0} samples; ${perf.excluded_unknown_metadata||0} excluded for missing metadata.${perf.truncated?' Coverage capped.':''}</p>`+[...buckets].map(([key,groups])=>{
    const maximum=Math.max(1,...groups.map(g=>g.max));
    return `<h4>${esc(buildLabel(key))}</h4>`+table(['Class',query.metric.toUpperCase()+' distribution (min / quartiles / max)','Median '+query.metric.toUpperCase(),'Range','Parses · distinct characters','Coverage'],groups.sort((a,b)=>b.median-a.median).map(g=>`<tr><td style="color:${window.A2CombatReview.color(g.class)}">${esc(g.class)}</td><td><svg viewBox="0 0 360 32" style="min-width:230px;width:100%;max-width:500px" role="img" aria-label="${esc(g.class)} DPS distribution"><title>Min ${n(g.min)}; lower quartile ${n(g.q1)}; median ${n(g.median)}; upper quartile ${n(g.q3)}; max ${n(g.max)}; ${g.count} parses</title><line x1="${g.min/maximum*350}" x2="${g.max/maximum*350}" y1="16" y2="16" stroke="currentColor"/><rect x="${g.q1/maximum*350}" y="6" width="${Math.max(2,(g.q3-g.q1)/maximum*350)}" height="20" fill="${window.A2CombatReview.color(g.class)}"/><line x1="${g.median/maximum*350}" x2="${g.median/maximum*350}" y1="3" y2="29" stroke="currentColor"/></svg></td><td>${n(g.median)}</td><td>${n(g.min)} – ${n(g.max)}</td><td>${g.count} · ${g.comparison?.identities??'Unavailable'}</td><td>${g.comparison?.status==='available'?'Sufficient sample':esc((g.comparison?.reasons||['Coverage unavailable']).join(' '))}</td></tr>`));
   }).join('');bindOpen();
   options.api('/api/v1/progression?'+params()).then(r=>{if(request!==loadRequest)return;$('[data-progression]').innerHTML=`<p class="small muted">${esc(r.note)}</p>`+table(['Class','Region · build','Source','Skill','Stigma','PvE Daevanion','Observations'],(r.observations||[]).map(x=>`<tr><td>${esc(x.class_name)}</td><td>${esc(x.region)} · ${esc(buildLabel(x.game_patch))}</td><td>${esc(x.source)}</td><td>${x.skill}</td><td>${x.stigma}</td><td>${x.daevanion}</td><td>${x.observations}</td></tr>`));}).catch(e=>{if(request!==loadRequest)return;$('[data-progression]').textContent=e.message;});
  }catch(e){if(request!==loadRequest)return;$('[data-message]').textContent=e.message;}
 }
 function bindOpen(){root.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>options.open(b.dataset.open,query.combat_mode));}
 async function records(){try{
  const q=params();Object.entries(identity).forEach(([k,v])=>q.set(k,v));q.set('page',recordPage);
  const request=++consistencyRequest;
  $('[data-consistency]').textContent='Loading matched character trends…';
  options.api('/api/v1/consistency?'+q).then(c=>{
   if(request!==consistencyRequest)return;
   const value=x=>x===null || x===undefined?'Unavailable':n(x);
   $('[data-consistency]').innerHTML=`<p class="small muted">${esc(c.note)} ${esc(c.identity)}. ${c.excluded_missing_evidence||0} samples excluded for missing cohort/metric evidence.${c.truncated?' Dataset capped; variation/trends unavailable.':''}${c.omitted_groups?' Additional groups omitted: '+c.omitted_groups:''}</p>`+(c.groups||[]).map(g=>{
    const history=g.history||[],maximum=Math.max(1,...history.map(x=>x.score));
    const points=history.map((x,i)=>`${history.length>1?i*600/(history.length-1):300},${100-90*x.score/maximum}`).join(' ');
    return `<details><summary>${esc(g.boss)} · ${esc(g.class_name)} · ${esc(buildLabel(g.game_patch))} · ${esc(g.difficulty)} · party ${g.party_size} · instance ${g.instance_id} · ${g.samples} recordings</summary><p>Median ${value(g.median)} ${esc(c.metric.toUpperCase())} · range ${value(g.min)}–${value(g.max)} · relative variation ${g.coefficient_of_variation_pct===null?'Unavailable':g.coefficient_of_variation_pct.toFixed(1)+'%'} · median absolute deviation ${value(g.median_absolute_deviation)} · standard deviation ${value(g.standard_deviation)}</p><p>Recent 5 median ${value(g.recent_five_median)} · preceding 5 ${value(g.previous_five_median)} · change ${g.change_pct===null?'Unavailable':(g.change_pct>0?'+':'')+g.change_pct.toFixed(1)+'%'}${!g.variation_available?' · At least 5 uncapped recordings required for variation.':''}${!g.trend_available?' · At least 10 uncapped recordings required for trend.':''}</p><p class="small muted">Latest up to 50 samples in upload order; this is not a real-time fight timeline. ${g.omitted_history} earlier samples omitted from this view. ${g.observed_death_markers} recorded player death markers across ${g.samples_with_death_markers} recordings with markers; other recordings do not establish zero deaths.</p><svg viewBox="0 0 600 115" role="img" aria-label="Recorded rates in upload order" style="width:100%;max-width:800px"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/>${history.map((x,i)=>`<circle cx="${history.length>1?i*600/(history.length-1):300}" cy="${100-90*x.score/maximum}" r="3" fill="currentColor"><title>${esc(new Date(x.uploaded_at*1000).toLocaleString())}: ${n(x.score)}</title></circle>`).join('')}</svg>${table(['Upload received',c.metric.toUpperCase(),'Recorded player deaths','Log'],history.map(x=>`<tr><td>${esc(new Date(x.uploaded_at*1000).toLocaleString())}</td><td>${n(x.score)}</td><td>${x.recorded_deaths===null?'Unavailable (no markers)':x.recorded_deaths}</td><td><button class="btn small" data-open="${esc(x.log)}">Open encounter ${x.segment+1}</button></td></tr>`))}</details>`;
   }).join('');bindOpen();
  }).catch(e=>{if(request===consistencyRequest)$('[data-consistency]').textContent='Consistency unavailable: '+e.message;});
  const r=await options.api('/api/v1/records?'+q);
  $('[data-record-note]').textContent=r.identity+'. '+r.note;
  $('[data-records]').innerHTML=table(['Encounter','Type · version · difficulty','Class','Best '+query.metric.toUpperCase(),'Attempts'],(r.records||[]).map(x=>`<tr><td><button class="btn small" data-open="${esc(x.log)}">${esc(x.boss)}</button></td><td>${esc(types[x.encounter_type])} · ${esc(buildLabel(x.game_patch||'Unknown'))} · ${esc(x.difficulty||'Unknown')} · party ${x.party_size||'unknown'} · instance ${x.instance_id||'unknown'}</td><td>${esc(x.class||'Unknown')}</td><td>${n(x.best_score??x.best_dps)}</td><td>${x.attempts}</td></tr>`));
  $('[data-history]').innerHTML='<h4>All matching public attempts</h4>'+table(['Encounter','Character · server',query.metric.toUpperCase(),'Ranking status','Recorded'],(r.history||[]).map(x=>`<tr><td><button class="btn small" data-open="${esc(x.log_id)}">${esc(x.boss)}</button></td><td>${esc(x.name)} · ${esc(x.server)}</td><td>${n(x.score??x.dps)}</td><td>${x.ranking_eligible?'Eligible':'Unranked / unverified'}</td><td>${new Date(x.created_at*1000).toLocaleString()}</td></tr>`));
  $('[data-record-page]').textContent=`Page ${recordPage} · ${r.total} attempts`;$('[data-record-prev]').disabled=recordPage===1;$('[data-record-next]').disabled=recordPage*50>=r.total;bindOpen();
 }catch(e){$('[data-record-note]').textContent=e.message;}}
 $('[data-prev]').onclick=()=>{page=Math.max(1,page-1);load();};$('[data-next]').onclick=()=>{page++;load();};
 $('[data-record-search]').onclick=()=>{identity={name:$('[data-name]').value.trim(),server:$('[data-server]').value.trim(),character_id:$('[data-character]').value.trim()};recordPage=1;records();};
 $('[data-record-prev]').onclick=()=>{recordPage=Math.max(1,recordPage-1);records();};$('[data-record-next]').onclick=()=>{recordPage++;records();};
 options.api('/api/v1/report-facets').then(f=>{
  query.game_patch=f.latest_submitted_patch||'';
  $('[data-filters]').innerHTML=['combat_mode','metric','encounter_type','game_patch','boss','difficulty','region','party_size'].map(k=>`<label class="small">${esc(k==='game_patch'?'game version':k.replaceAll('_',' '))} <select data-filter="${k}">${["combat_mode","metric"].includes(k)?"":'<option value="">All</option>'}${(k==='combat_mode'?['pve','pvp']:k==='metric'?['dps','hps','dtps']:k==='encounter_type'?Object.keys(types):f[k]||[]).map(v=>`<option value="${esc(v)}" ${query[k]===v?'selected':''}>${esc(k==='encounter_type'?types[v]:k==='game_patch'?buildLabel(v):v)}</option>`).join('')}</select></label>`).join('')+'<button class="btn small" data-refresh>Refresh</button>';
  root.querySelectorAll('[data-filter]').forEach(e=>e.onchange=()=>{query[e.dataset.filter]=e.value;if(e.dataset.filter==='encounter_type'&&e.value)query.combat_mode=e.value.startsWith('pvp_')?'pvp':'pve';if(e.dataset.filter==='combat_mode')query.encounter_type='';root.querySelector('[data-filter=combat_mode]').value=query.combat_mode;root.querySelector('[data-filter=encounter_type]').value=query.encounter_type||'';page=1;load();if(identity.server){recordPage=1;records();}});$('[data-refresh]').onclick=load;load();
 }).catch(e=>{$('[data-message]').textContent=e.message;});
 return {refresh:load};
}
window.A2Community={mount,types};
})();
