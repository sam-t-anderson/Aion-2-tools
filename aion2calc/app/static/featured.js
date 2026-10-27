/* Featured encounters (log server 0.2.145): the bosses the server's operator puts at the top of the Combat Logs pages,
   each with its race summary, progress, reports, rankings and statistics. Shared by the desktop app and the website.

   window.A2Featured.section(root, options)  the landing cards of every featured encounter (nothing when there is none)
   window.A2Featured.page(root, options)     one featured encounter's page: options.id, options.view, options.metric

   options.api(path)       -> the log server's JSON (the website's A2.api, the app's community proxy)
   options.link(id, view, metric) -> the address of a featured encounter's page (metric: the rankings' first one)
   options.logLink(id, segment) -> the address of a public log (at one of its fights when segment is a number)
   options.loaded(f)       -> called with the encounter once its page has it (the website names its tab after it)
   Names from the game and from players are under translate="no": the language toggle (i18n.js) leaves them alone. */
(function () {
"use strict";
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const VIEWS=[["race","Race Summary"],["progress","Progress"],["reports","All Reports"],["rankings","Rankings"],["statistics","Statistics"]];
const ROLES=[["dps","DPS"],["tank","Tank"],["support","Support"]];
const CLASSES=["gladiator","templar","assassin","ranger","sorcerer","spiritmaster","cleric","chanter"];
const PALETTE={gladiator:"#c69b6d",templar:"#f58cba",assassin:"#fff468",ranger:"#aad372",sorcerer:"#3fc7eb",spiritmaster:"#8788ee",cleric:"#ffffff",chanter:"#ff7c0a"};
const REGIONS={nae:"NA",na:"NA",eu:"EU",kr:"KR",tw:"TW",jp:"JP",global:"Global"};
const cap=s=>s?s[0].toUpperCase()+s.slice(1):"";
const n0=x=>x==null||!Number.isFinite(+x)?"—":Math.round(x).toLocaleString("en-US");
const pct=x=>x==null?"—":(+x).toFixed(1)+"%";
const clock=x=>{if(x==null||!Number.isFinite(+x))return "—";x=Math.round(x);const h=Math.floor(x/3600),m=Math.floor(x%3600/60),s=String(x%60).padStart(2,"0");return h?`${h}:${String(m).padStart(2,"0")}:${s}`:`${m}:${s}`;};
// the date with the time of day in the computer's clock: 2026-10-23 15:04
const when=t=>{if(!t)return "—";const d=new Date(t*1000);if(!Number.isFinite(d.getTime()))return "—";const p=v=>String(v).padStart(2,"0");return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;};
const world=id=>id?(window.A2Servers?window.A2Servers.label(id,String(id)):String(id)):"";
const region=r=>r?(REGIONS[String(r).toLowerCase()]||String(r).toUpperCase()):"";
const patch=p=>String(p||"").replace(/^version:product:/,"");
const colour=cls=>(window.A2CombatReview&&window.A2CombatReview.color?window.A2CombatReview.color(cls):PALETTE[cls])||"inherit";
const asset=url=>url&&window.A2AssetHealth?window.A2AssetHealth.source(url):url;
const npcCode=key=>(/^npc:([0-9]+)/.exec(String(key||""))||[])[1];
// a boss's portrait: the bundled art for its NPC, else the one the server knows
const portraitURL=(key,icon)=>{const code=npcCode(key);return (code&&window.A2BundledAssets&&window.A2BundledAssets.npcs&&window.A2BundledAssets.npcs[code])||icon||"";};
function portrait(key,icon,size,alt){
  const url=portraitURL(key,icon);
  return url?`<img class="fe-portrait" src="${esc(asset(url))}" width="${size}" height="${size}" loading="lazy" alt="${esc(alt||"")}">`:`<span class="fe-portrait fe-portrait-none" style="width:${size}px;height:${size}px" aria-hidden="true"></span>`;
}
const classIcon=(cls,size=20)=>CLASSES.includes(cls)?`<img class="fe-class" src="${esc(asset("https://metabot.gg/web/aion2/classes/"+cls+".webp"))}" width="${size}" height="${size}" loading="lazy" alt="${esc(cap(cls))}" title="${esc(cap(cls))}">`:"";
const medal=rank=>`<span class="fe-medal fe-medal-${rank<=3?rank:"n"}">${rank}</span>`;
const where=team=>[team.server?world(team.server):team.kind==="party"?"several servers":"",region(team.region)].filter(Boolean).join(" · ");
// class-coloured text: the colour as --cls, which the light theme darkens (featured.css)
const named=(name,cls)=>`<span class="fe-classed" style="--cls:${esc(colour(cls))}" translate="no">${esc(name)}</span>`;
const teamHTML=team=>`<span class="fe-team ${team.kind==="legion"?"fe-legion":""}" title="${esc(team.kind==="legion"?"Legion":(team.members||[]).map(m=>m.name).join(", "))}" translate="no">${esc(team.name)}</span><small class="fe-sub" translate="no">${esc(where(team))}</small>`;
const playerHTML=p=>`${named(p.name,p.class)}<small class="fe-sub" translate="no">${esc(world(p.server))}</small>`;
const progressText=t=>t.complete?`${t.killed}/${t.phases}`:`${t.killed}/${t.phases}${t.best_hp!=null?` · ${pct(t.best_hp)}`:""}`;
const note=d=>d&&d.note?`<p class="small muted fe-note">${esc(d.note)}</p>`:"";
const failed=e=>`<div class="note">${esc((e&&e.message)||"Could not reach the log server.")}</div>`;
const pager=(d,size)=>{const pages=Math.max(1,Math.ceil((d.total||0)/size));return pages>1?`<div class="row fe-pager"><button class="btn small" data-page="${d.page-1}" ${d.page<=1?"disabled":""}>Previous</button><span>Page ${d.page} of ${pages}</span><button class="btn small" data-page="${d.page+1}" ${d.page>=pages?"disabled":""}>Next</button></div>`:"";};

// ------------------------------------------------------------------ the landing cards
function card(title,rows,more){
  return `<section class="fe-card"><h4>${esc(title)}</h4>${rows.length?`<ol class="fe-rows">${rows.map((r,i)=>`<li>${medal(i+1)}<span class="fe-who">${r[0]}</span><span class="fe-val">${r[1]}</span></li>`).join("")}</ol>`:`<p class="small muted fe-rows">No records yet.</p>`}${more?`<a class="fe-more" href="${esc(more)}">View more…</a>`:""}</section>`;
}
function nav(f,current,options){
  return `<nav class="fe-nav" aria-label="${esc(f.title)} pages">${VIEWS.map(([view,label])=>`<a href="${esc(options.link(f.id,view))}"${view===current?' aria-current="page"':""}>${label}</a>`).join("")}</nav>`;
}
function zone(f,options){
  const s=f.summary||{},link=view=>options.link(f.id,view);
  const cards=[
    card("Progress",(s.progress||[]).map(t=>[teamHTML(t.team),t.complete?"Complete":progressText(t)]),link("progress")),
    card("Speed",(s.speed||[]).map(r=>[teamHTML(r.team),clock(r.elapsed)]),options.link(f.id,"rankings","speed")),
    card("Execution",(s.execution||[]).map(r=>[teamHTML(r.team),`${r.deaths==null?"—":r.deaths} ${r.deaths===1?"death":"deaths"} · ${clock(r.seconds)}`]),link("progress")),
    ...ROLES.map(([role,label])=>card(`All Stars (${label})`,((s.all_stars||{})[role]||[]).map(p=>[playerHTML(p),(+p.points).toFixed(1)]),link("rankings"))),
    ...ROLES.map(([role,label])=>card(role==="dps"?"DPS":`${label} Damage`,((s.classes||{})[role]||[]).map(c=>[`${classIcon(c.class)}<span class="fe-classed" style="--cls:${esc(colour(c.class))}">${esc(cap(c.class))}</span>`,n0(c.median)]),link("statistics"))),
  ];
  return `<article class="fe-zone"><div class="fe-zone-art">${portrait(f.boss_key,f.icon,96,f.boss)}</div><div class="fe-zone-main">
    <header class="fe-head fe-zone-head"><div class="fe-title"><h3 translate="no">${esc(f.title)}</h3><small><span translate="no">${esc(f.boss)}</span> · ${esc(f.difficulty)}</small></div>${nav(f,null,options)}</header>
    <div class="fe-cards">${cards.join("")}</div><p class="small muted">${n0(s.teams)} teams · ${n0(s.complete)} cleared · ${n0(s.pulls)} recorded pulls. Speed is a team's fastest complete run; execution its final-boss kill with the fewest deaths; all stars a character's best parse on each boss, added up; the class cards the median recorded DPS.</p></div></article>`;
}
function section(root,options){
  let alive=true;
  root.innerHTML="";
  options.api("/api/v1/featured").then(d=>{
    if(!alive||!root.isConnected)return;
    const list=(d&&d.featured)||[];
    root.innerHTML=list.length?`<h2 class="fe-heading">Featured encounters</h2>${list.map(f=>zone(f,options)).join("")}${note(d)}`:"";
  }).catch(()=>{if(alive)root.innerHTML="";});
  return {dispose(){alive=false;}};
}

// ------------------------------------------------------------------ the pages
// The race: the phases side by side above one bar, filled as far as the leading team got, each team listed under
// the phase it is on and the teams that finished under Complete!; then a closer look at the leading teams.
function raceHTML(d,f,options){
  const phases=d.phases||[],teams=d.teams||[],n=phases.length||1,done=teams.filter(t=>t.complete);
  const lead=Math.max(0,...teams.map(t=>+t.position||0));
  const fill=i=>Math.round(100*Math.max(0,Math.min(1,lead*n-i)));
  const list=rows=>`<ol class="fe-standing">${rows.slice(0,10).map(t=>`<li><span class="fe-rank">${t.rank}.</span> <span translate="no">${esc(t.team.name)}</span> <small>${t.complete?esc(when(t.first_kill_at)):t.best_hp!=null?pct(t.best_hp):"pulling"}</small></li>`).join("")}</ol>`;
  const heads=phases.map((p,i)=>`<div class="fe-race-head">${portrait(p.boss_key,p.icon,40,"")}<div><strong>Phase ${i+1}</strong><small translate="no">${esc(p.boss)}</small></div></div>`).join("");
  const track=phases.map((p,i)=>`<span class="fe-race-seg"><span style="width:${fill(i)}%"></span></span>`).join("");
  const stats=phases.map(p=>`<p class="small muted">${n0(p.teams)} reached · ${n0(p.killed_by)} killed${p.first_kill?`<br>First: <span translate="no">${esc(p.first_kill.team.name)}</span>, ${esc(when(p.first_kill.at))}`:""}</p>`).join("");
  const lists=phases.map((p,i)=>list(teams.filter(t=>!t.complete&&t.next_phase===i))).join("");
  const furthest=done.length?"a team has completed it":`the leading team is ${Math.round(100*lead)}% of the way`;
  const closer=teams.slice(0,8).map(t=>{
    const art=portraitURL(f.boss_key,f.icon),next=(phases[t.next_phase]||{}).boss||"";
    return `<article class="fe-closer">${art?`<img class="fe-closer-art" src="${esc(asset(art))}" alt="" loading="lazy">`:""}
    <header><h4>${teamHTML(t.team)}</h4><span class="fe-closer-rank"><span class="sr-only">Rank </span>${t.rank}</span></header>
    ${t.team.kind==="party"&&(t.team.members||[]).length?`<p class="fe-members">${t.team.members.map(m=>named(m.name,m.class)).join(", ")}</p>`:t.team.kind==="legion"?`<p class="fe-members small muted">Legion</p>`:""}
    <footer><div><span class="fe-closer-label">Progress</span><strong class="fe-closer-big">${t.killed}/${t.phases}</strong></div>
    <div class="fe-closer-end"><span>Pulls: ${n0(t.pulls)}</span><strong>${t.complete?"Complete!":"Working on"}</strong>${t.complete?`<span>${esc(when(t.first_kill_at))}</span>`:`<span><span translate="no">${esc(next)}</span>${t.best_hp!=null?" · "+pct(t.best_hp):""}</span>`}<a class="fe-more" href="${esc(options.logLink(t.log))}">Open its log</a></div></footer></article>`;}).join("");
  return `<div class="fe-race-wrap"><div class="fe-race" style="--phases:${n}">${heads}<div class="fe-race-head fe-race-done"><strong>Complete!</strong></div>
    <div class="fe-race-track" role="img" aria-label="${esc(`${phases.length} phases: ${furthest}`)}">${track}<span class="fe-race-seg fe-race-seg-done"><span style="width:${done.length?100:0}%"></span></span></div>
    ${stats}<p class="small muted">${n0(done.length)} complete</p>
    ${lists}${done.length?list(done):'<p class="muted small">No team yet</p>'}</div></div>
    <h3>A closer look</h3>${closer?`<div class="fe-closers">${closer}</div>`:`<p class="muted">No team has an attempt on record yet.</p>`}`;
}
function progressHTML(d,f,options){
  const phases=f.phases||[];
  const rows=(d.progress||[]).map(t=>`<tr><td>${t.rank}</td><td>${teamHTML(t.team)}</td><td>${esc(progressText(t))}</td>
    <td class="fe-killed">${(t.killed_bosses||[]).map(i=>phases[i]?portrait(phases[i].boss_key,phases[i].icon,24,phases[i].boss):"").join("")}</td><td>${n0(t.pulls)}</td><td>${esc(when(t.progress_at))}</td></tr>`).join("");
  const kills=(d.kills||[]).map(k=>`<tr><td>${k.rank}</td><td>${teamHTML(k.team)}</td><td>${esc(patch(k.patch))}</td>
    <td class="fe-comp">${Object.entries(k.composition||{}).map(([cls,count])=>`${classIcon(cls,18)}<span>${count}</span>`).join("")}</td><td>${esc(when(k.at))}</td><td>${clock(k.seconds)}</td><td>${k.deaths==null?"—":n0(k.deaths)}</td><td><a href="${esc(options.logLink(k.log))}">Log</a></td></tr>`).join("");
  return `<div class="cr-scroll"><table class="t fe-table"><caption>Teams by progress</caption><thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">Progress</th><th scope="col">Bosses killed</th><th scope="col">Pulls</th><th scope="col">Last progress</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="6">No team has an attempt on record yet.</td></tr>'}</tbody></table></div>${pager(d,50)}
    <div class="cr-scroll"><table class="t fe-table"><caption>Final-boss kills, first first</caption><thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">Game version</th><th scope="col">Party</th><th scope="col">Date</th><th scope="col">Duration</th><th scope="col">Deaths</th><th scope="col">Log</th></tr></thead>
    <tbody>${kills||'<tr><td colspan="8">No kill on record yet.</td></tr>'}</tbody></table></div>`;
}
function reportsHTML(d,options){
  const rows=(d.logs||[]).map(l=>`<tr><td>${esc(when(l.created_at))}</td><td><a href="${esc(options.logLink(l.id))}" translate="no">${esc(l.title||l.boss||l.id)}</a><small class="fe-sub" ${l.uploader?'translate="no"':""}>${esc(l.uploader||"Anonymous")}</small></td>
    <td translate="no">${esc((l.contexts||[]).map(c=>c.boss).filter(Boolean).slice(0,4).join(", "))}</td><td>${clock(l.duration)}</td><td>${(l.players||[]).slice(0,8).map(p=>named(p.name,p.class)).join(", ")}</td></tr>`).join("");
  return `<div class="cr-scroll"><table class="t fe-table"><caption>Public logs of this encounter, newest first</caption><thead><tr><th scope="col">Uploaded</th><th scope="col">Log</th><th scope="col">Bosses</th><th scope="col">Duration</th><th scope="col">Players</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="5">No public log yet.</td></tr>'}</tbody></table></div>${pager(d,d.limit||30)}`;
}
const bossSelect=(f,state)=>`<label>Boss <select data-boss>${(f.phases||[]).map(p=>`<option value="${esc(p.boss_key)}" ${p.boss_key===state.boss?"selected":""} translate="no">${esc(p.boss)}</option>`).join("")}</select></label>`;
// the regions the encounter was fought in (the server lists them), as fflogs' "All regions"
const regionSelect=(d,state)=>(d.regions||[]).length?`<label>Region <select data-region><option value="">All regions</option>${d.regions.map(r=>`<option value="${esc(r)}" ${r===state.region?"selected":""}>${esc(region(r))}</option>`).join("")}</select></label>`:"";
const controls=(...parts)=>{const shown=parts.filter(Boolean);return shown.length?`<div class="row fe-controls">${shown.join("")}</div>`:"";};
function rankingsHTML(d,f,state,options){
  const speed=state.metric==="speed";
  const top=controls(speed?"":bossSelect(f,state),`<label>Ranking <select data-metric>${[["dps","DPS"],["hps","Healing per second"],["speed","Speed (teams)"]].map(([v,l])=>`<option value="${v}" ${v===state.metric?"selected":""}>${l}</option>`).join("")}</select></label>`,
    speed?"":`<label>Class <select data-class><option value="">All classes</option>${CLASSES.map(c=>`<option value="${c}" ${c===state.cls?"selected":""}>${cap(c)}</option>`).join("")}</select></label>`,regionSelect(d,state));
  if(speed){
    const rows=(d.entries||[]).map(r=>`<tr><td>${r.rank}</td><td>${teamHTML(r.team)}</td><td>${clock(r.elapsed)}</td><td>${esc(patch(r.patch))}</td><td>${esc(when(r.at))}</td><td><a href="${esc(options.logLink(r.log))}">Log</a></td></tr>`).join("");
    return top+`<div class="cr-scroll"><table class="t fe-table"><caption>Each team's fastest complete run</caption><thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">Time</th><th scope="col">Game version</th><th scope="col">Date</th><th scope="col">Log</th></tr></thead><tbody>${rows||'<tr><td colspan="6">No complete, speed-eligible run yet.</td></tr>'}</tbody></table></div>`;
  }
  const rows=(d.entries||[]).map((r,i)=>`<tr><td>${i+1}</td><td>${playerHTML(r)}</td><td>${classIcon(r.class)}</td><td>${n0(r.score)}</td><td>${r.parse==null?"—":Math.round(r.parse)}</td><td>${clock(r.duration)}</td><td>${esc(when(r.created_at))}</td><td><a href="${esc(options.logLink(r.log,r.segment))}">Log</a></td></tr>`).join("");
  return top+`<div class="cr-scroll"><table class="t fe-table"><caption><span>${state.metric==="hps"?"Healing per second":"Damage per second"}</span> · <span translate="no">${esc(((f.phases||[]).find(p=>p.boss_key===state.boss)||{}).boss||f.boss)}</span></caption><thead><tr><th scope="col">Rank</th><th scope="col">Player</th><th scope="col">Class</th><th scope="col">${state.metric==="hps"?"HPS":"DPS"}</th><th scope="col">Parse</th><th scope="col">Duration</th><th scope="col">Date</th><th scope="col">Log</th></tr></thead><tbody>${rows||'<tr><td colspan="8">No ranked player yet.</td></tr>'}</tbody></table></div>`;
}
function statisticsHTML(d,f,state){
  const classes=d.classes||[],top=Math.max(1,...classes.map(c=>c.p95||c.max||0));
  const bar=c=>`<span class="fe-bar" aria-hidden="true"><span class="fe-bar-iqr" style="left:${100*c.p25/top}%;width:${100*Math.max(0,c.p75-c.p25)/top}%;--cls:${esc(colour(c.class))}"></span><span class="fe-bar-median" style="left:${100*c.median/top}%"></span></span>`;
  const rows=classes.map(c=>`<tr><td>${classIcon(c.class)} <span class="fe-classed" style="--cls:${esc(colour(c.class))}">${esc(cap(c.class))}</span></td><td>${esc((ROLES.find(r=>r[0]===c.role)||["",""])[1])}</td><td>${n0(c.count)}</td><td>${n0(c.p25)}</td><td>${n0(c.median)}</td><td>${n0(c.p75)}</td><td>${n0(c.p95)}</td><td>${n0(c.max)}</td><td class="fe-bar-cell">${bar(c)}</td></tr>`).join("");
  return controls(bossSelect(f,state),`<label>Rate <select data-metric>${[["dps","DPS"],["hps","Healing per second"]].map(([v,l])=>`<option value="${v}" ${v===state.metric?"selected":""}>${l}</option>`).join("")}</select></label>`,regionSelect(d,state))+`
    <div class="cr-scroll"><table class="t fe-table"><caption>Recorded ${state.metric==="hps"?"healing":"damage"} per second by class</caption><thead><tr><th scope="col">Class</th><th scope="col">Role</th><th scope="col">Samples</th><th scope="col">25th</th><th scope="col">Median</th><th scope="col">75th</th><th scope="col">95th</th><th scope="col">Best</th><th scope="col">Spread</th></tr></thead>
    <tbody>${rows||'<tr><td colspan="9">No ranked sample yet.</td></tr>'}</tbody></table></div><p class="small muted">Roles as the developers group the classes for party synergy: Gladiator and Templar tank, Cleric and Chanter support, the other four deal damage.</p>`;
}
function page(root,options){
  let alive=true,request=0,f=null;
  const view=VIEWS.some(v=>v[0]===options.view)?options.view:"race";
  const state={page:1,boss:"",region:"",metric:["dps","hps","speed"].includes(options.metric)&&(view==="rankings"||options.metric!=="speed")?options.metric:"dps",cls:""};
  root.innerHTML=`<div class="fe-page"><p class="muted">Loading…</p></div>`;
  const pathFor=()=>{
    const base="/api/v1/featured/"+encodeURIComponent(options.id),q=new URLSearchParams();
    if(view==="progress"||view==="reports")q.set("page",state.page);
    if(view==="rankings"||view==="statistics"){
      q.set("metric",state.metric);
      if(state.boss&&state.metric!=="speed")q.set("boss",state.boss);
      if(state.cls&&view==="rankings"&&state.metric!=="speed")q.set("class",state.cls);
    }
    if(state.region&&view!=="reports")q.set("region",state.region);
    return base+"/"+view+(String(q)?"?"+q:"");
  };
  const body=()=>root.querySelector("[data-fe-body]");
  async function load(){
    const mine=++request;
    try{
      const d=await options.api(pathFor());
      if(!alive||mine!==request||!root.isConnected)return;
      const target=body();
      const head=view==="race"||view==="progress"?controls(regionSelect(d,state)):"";
      target.innerHTML=head+(view==="race"?raceHTML(d,f,options):view==="progress"?progressHTML(d,f,options):view==="reports"?reportsHTML(d,options):view==="rankings"?rankingsHTML(d,f,state,options):statisticsHTML(d,f,state))+note(d);
      target.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>{state.page=+b.dataset.page;load();});
      const pick=(selector,apply)=>{const el=target.querySelector(selector);if(el)el.onchange=()=>{apply(el.value);load();};};
      pick("[data-boss]",v=>{state.boss=v;});
      pick("[data-metric]",v=>{state.metric=v;});
      pick("[data-class]",v=>{state.cls=v;});
      pick("[data-region]",v=>{state.region=v;state.page=1;});
    }catch(e){if(alive&&mine===request&&body())body().innerHTML=failed(e);}
  }
  options.api("/api/v1/featured/"+encodeURIComponent(options.id)).then(d=>{
    if(!alive||!root.isConnected)return;
    f=d;state.boss=d.boss_key;
    root.innerHTML=`<div class="fe-page"><header class="fe-head fe-head-page">${portrait(d.boss_key,d.icon,72,d.boss)}<div class="fe-title"><h2 translate="no">${esc(d.title)}</h2><small><span translate="no">${esc(d.boss)}</span> · ${esc(d.difficulty)}${d.starts_at?` · <span>race from ${esc(when(d.starts_at))}</span>`:""}${d.ends_at?` <span>to ${esc(when(d.ends_at))}</span>`:""}</small></div>${nav(d,view,options)}</header><div data-fe-body><p class="muted">Loading…</p></div></div>`;
    if(options.loaded)options.loaded(d);
    load();
  }).catch(e=>{if(alive)root.innerHTML=`<div class="fe-page">${failed(e)}</div>`;});
  return {dispose(){alive=false;request++;}};
}
window.A2Featured={section,page,views:VIEWS.map(v=>v[0])};
})();
