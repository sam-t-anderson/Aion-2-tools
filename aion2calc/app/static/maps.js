/* Provider-supported interactive map embedding; no inferred game coordinates. Beside it, the
   farming-route catalog (farming-routes.json, built by `python -m aion2calc routes-build`): ordered
   waypoint loops from sources whose terms allow reuse, credited; guide links where no such source
   exists. Nothing here is invented: a zone without a permitted source says so. And the Abyss PvP heat
   map (0.2.389): the log server's /api/v1/pvp-heat, the recorded world positions of PvP hits and kills
   in public logs, drawn on a base map made of where recordings have been, refreshed every 15 minutes. */
(function(){
 'use strict';
 const zones={verteron:'Verteron',altgard:'Altgard',poeta:'Poeta',ishalgen:'Ishalgen'};
 // The date with the time of day, in the computer's clock: 2026-10-23 15:04:05.
 const whenAt = (x) => { if (x == null || x === "") return "—"; const d = new Date(x); if (!Number.isFinite(d.getTime())) return "—"; const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
 const CATALOG_URL=(()=>{try{return new URL('farming-routes.json',document.currentScript.src).href;}catch(e){return 'farming-routes.json';}})();
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let catalogPromise=null;
 const catalog=()=>catalogPromise||(catalogPromise=fetch(CATALOG_URL,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Route catalog unavailable ('+r.status+')');return r.json();}));
 function routeText(zone,route,source){
  const lines=[`${zone.name} · ${route.title} · ${route.count} ${route.item}`,
   `Source: ${source?source.name+' ('+source.license+', '+source.url+', commit '+String(source.revision||'').slice(0,12)+')':route.source}`,
   route.method,''];
  for(const w of route.waypoints)lines.push(`${w.n}. ${w.area||'—'} (${w.x}, ${w.y})`);
  return lines.join('\n');
 }
 function routesHTML(zone,data){
  const sources=data.sources||{};
  const routes=(zone.routes||[]).map((route,i)=>{
   const src=sources[route.source];
   const one=String(route.item).replace(/s$/,'');
   const legs=route.legs.map(l=>`<li>${esc(l.area||'unnamed area')} — ${l.count} ${esc(l.count===1?one:route.item)} <span class="muted">(${l.count===1?'waypoint '+l.from:'waypoints '+l.from+'–'+l.to})</span></li>`).join('');
   const points=route.waypoints.map(w=>`<li>${esc(w.area||'—')} <span class="muted">(${w.x}, ${w.y})</span></li>`).join('');
   return `<details ${i===0?'open':''} class="note" data-route="${i}"><summary>${esc(route.title)} · ${route.count} ${esc(route.item)} · ${route.legs.length} leg${route.legs.length===1?'':'s'}${route.start&&route.start.area?' · starts in '+esc(route.start.area)+(route.start.near_teleport?' (near a teleport)':''):''}</summary>
    <p class="small muted">${esc(route.note)} ${esc(route.method)}</p>
    <p class="small">Source: ${src?`<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">${esc(src.name)}</a> · <a href="${esc(src.license_url)}" target="_blank" rel="noopener noreferrer">${esc(src.license)}</a> · ${esc(src.attribution)} · commit ${esc(String(src.revision||'').slice(0,12))}`:esc(route.source)}</p>
    <ol class="route-legs">${legs}</ol>
    <details><summary>All ${route.count} waypoints in order</summary><ol class="route-points">${points}</ol></details>
    <div class="row"><button class="btn small" data-copy-route="${i}">Copy as text</button><span class="small muted" data-route-msg="${i}" role="status"></span></div></details>`;
  }).join('');
  const guides=(zone.guides||[]).map(g=>`<li><a href="${esc(g.url)}" target="_blank" rel="noopener noreferrer">${esc(g.title)}</a>${g.topic?' <span class="muted">— '+esc(g.topic)+'</span>':''}</li>`).join('');
  return `${(zone.notes||[]).map(n=>`<p class="small muted">${esc(n)}</p>`).join('')}${routes||'<p class="small">No route is listed for this zone.</p>'}
   <h4>Guides (links only — no reuse terms, so nothing from them is copied)</h4>${guides?`<ul class="route-guides">${guides}</ul>`:'<p class="small muted">No guide links were found for this zone.</p>'}`;
 }
 function mountRoutes(root,mapSelect){
  const section=document.createElement('section');section.className='win routes-panel';
  section.innerHTML='<div class="wh"><h2>Farming routes</h2><span class="sub">Attributed waypoint loops · guide links</span></div><div class="wb"><div class="row"><label>Zone <select data-routes-zone></select></label></div><div data-routes-body><p class="small muted">Loading the route catalog…</p></div></div>';
  root.appendChild(section);
  const select=section.querySelector('[data-routes-zone]'),body=section.querySelector('[data-routes-body]');
  let data=null;
  const render=()=>{
   if(!data)return;
   const zone=data.zones.find(z=>z.id===select.value)||data.zones[0];
   if(!zone){body.innerHTML='<p class="small muted">The catalog has no zones.</p>';return;}
   body.innerHTML=routesHTML(zone,data)+`<p class="small muted">${esc(data.note||'')} Catalog built ${esc(whenAt(data.generated_at))}.</p>`;
   body.querySelectorAll('[data-copy-route]').forEach(b=>b.onclick=async()=>{const i=+b.dataset.copyRoute,msg=body.querySelector(`[data-route-msg="${i}"]`);try{await navigator.clipboard.writeText(routeText(zone,zone.routes[i],(data.sources||{})[zone.routes[i].source]));if(msg)msg.textContent='Copied.';}catch(e){if(msg)msg.textContent='Clipboard blocked; select the list and copy it.';}});
  };
  catalog().then(d=>{
   data=d;
   select.innerHTML=d.zones.map(z=>`<option value="${esc(z.id)}">${esc(z.name)}${z.faction&&z.faction!=='both'?' ('+esc(z.faction)+')':''}</option>`).join('');
   const current=mapSelect&&d.zones.find(z=>z.provider_map===mapSelect.value);
   if(current)select.value=current.id;
   render();
  }).catch(e=>{body.innerHTML=`<p class="small">${esc(e.message)}</p>`;});
  select.onchange=render;
  if(mapSelect)mapSelect.addEventListener('change',()=>{if(!data)return;const zone=d=>d.zones.find(z=>z.provider_map===mapSelect.value);const z=zone(data);if(z){select.value=z.id;render();}});
  return {dispose:()=>{section.remove();}};
 }

 // ---- The Abyss PvP heat map (0.2.389) ------------------------------------------------------------
 // GET /api/v1/pvp-heat (log server 0.2.168): squares of PvP hits and kills over the shortest recent window
 // three uploaders fill, a square only where two of them recorded fights, the ground recordings have covered
 // and the recorded bosses' places. World positions as recorded, x to the right and y up (north up, as the
 // movement replay draws them). The colours are one hue, light to dark by hits (dark to light on the dark theme).
 const HEAT_DETAIL='aion2.maps.heatCell',HEAT_CELLS=[[2000,'Normal squares (2,000)'],[1000,'Fine squares (1,000)'],[4000,'Coarse squares (4,000)']];
 const HEAT_WINDOWS={1800:'the last 30 minutes',7200:'the last 2 hours',21600:'the last 6 hours',86400:'the last 24 hours',604800:'the last 7 days'};
 const num=n=>Number(n||0).toLocaleString('en-US'),plural=(n,one,many)=>num(n)+' '+(Number(n)===1?one:many);
 function rememberedCell(){try{const v=Number(localStorage.getItem(HEAT_DETAIL));return HEAT_CELLS.some(c=>c[0]===v)?v:2000;}catch(_){return 2000;}}
 function rememberCell(v){try{localStorage.setItem(HEAT_DETAIL,String(v));}catch(_){/* storage blocked: the default next time */}}
 // Five steps of the ramp, by hits on a log scale from 1 to the busiest square.
 function heatStep(hits,max){return max<=1?4:Math.max(0,Math.min(4,Math.floor(5*Math.log(hits)/Math.log(max+1e-9)-1e-9)));}
 function heatHTML(){
  return '<section class="win heat-panel" data-heat><div class="wh"><h2>Abyss PvP heat map</h2><span class="sub">Where players fight players, refreshed every 15 minutes</span></div><div class="wb">'
   +'<div class="row"><label>Squares <select data-heat-cell>'+HEAT_CELLS.map(([v,t])=>'<option value="'+v+'">'+t+'</option>').join('')+'</select></label><button class="btn small" type="button" data-heat-refresh>Refresh</button></div>'
   +'<p class="small" data-heat-status role="status">Loading the heat map…</p>'
   +'<div class="heat-frame" data-heat-frame hidden><canvas data-heat-canvas role="img" aria-label="Abyss PvP heat map"></canvas><div class="heat-tip" data-heat-tip hidden></div></div>'
   +'<div class="heat-legend small" data-heat-legend hidden></div>'
   +'<details class="heat-table" data-heat-table hidden><summary>The squares as a table</summary><div data-heat-rows></div></details>'
   +'<p class="small muted" data-heat-note></p></div></section>';
 }
 function mountHeat(root,io){
  const section=document.createElement('div');section.innerHTML=heatHTML();
  const panel=section.firstChild;root.appendChild(panel);
  const $=sel=>panel.querySelector(sel);
  const status=$('[data-heat-status]'),frame=$('[data-heat-frame]'),canvas=$('[data-heat-canvas]'),tip=$('[data-heat-tip]'),
   legend=$('[data-heat-legend]'),table=$('[data-heat-table]'),rows=$('[data-heat-rows]'),note=$('[data-heat-note]'),cellSelect=$('[data-heat-cell]'),refresh=$('[data-heat-refresh]');
  const api=(io&&io.api)||(window.A2&&typeof window.A2.api==='function'?p=>window.A2.api(p):null);
  let data=null,view=null,hover=null,serial=0,timer=null,loadedAt=0,disposed=false,raf=0;
  cellSelect.value=String(rememberedCell());
  const tokens=()=>{const cs=getComputedStyle(panel),v=n=>cs.getPropertyValue(n).trim();
   return {ramp:[1,2,3,4,5].map(i=>v('--heat-'+i)),ground:v('--heat-ground'),surface:v('--heat-surface'),text:v('--text')||'#e9e6df',muted:v('--muted')||'#9aa3b5'};};
  function layout(){
   if(!data||!data.bounds){view=null;return;}
   const cell=data.cell_size,[x0,x1]=data.bounds.x,[y0,y1]=data.bounds.y,pad=12;
   const width=Math.max(240,frame.clientWidth||panel.clientWidth||600),maxH=Math.max(260,Math.min(720,Math.round((window.innerHeight||900)*.72)));
   const s=Math.min((width-2*pad)/Math.max(1,x1-x0),(maxH-2*pad)/Math.max(1,y1-y0));
   const w=Math.round((x1-x0)*s+2*pad),h=Math.round((y1-y0)*s+2*pad),ox=Math.round((width-w)/2);
   view={cell,x0,y1,s,pad,ox,w,h,width};
   const dpr=window.devicePixelRatio||1;
   canvas.style.width=width+'px';canvas.style.height=h+'px';canvas.width=Math.round(width*dpr);canvas.height=Math.round(h*dpr);
  }
  const box=(cx,cy)=>{const v=view,c=v.cell;return [v.ox+v.pad+(cx*c-v.x0)*v.s,v.pad+(v.y1-(cy+1)*c)*v.s,c*v.s];};
  const at=(x,y)=>[view.ox+view.pad+(x-view.x0)*view.s,view.pad+(view.y1-y)*view.s];
  function draw(){
   if(!data||!view)return;
   const t=tokens(),ctx=canvas.getContext('2d'),dpr=window.devicePixelRatio||1,max=Math.max(1,...data.cells.map(c=>c[2]));
   ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,view.width,view.h);
   ctx.fillStyle=t.surface;ctx.fillRect(view.ox,0,view.w,view.h);
   ctx.fillStyle=t.ground;                                   // the ground recordings have covered: no gaps, recessive
   for(const [cx,cy] of data.footprint||[]){const [x,y,z]=box(cx,cy);ctx.fillRect(x,y,z+.5,z+.5);}
   for(const c of data.cells){                               // heat: a 2px surface gap between squares big enough for one
    const [x,y,z]=box(c[0],c[1]),g=z>=6?1:0;ctx.fillStyle=t.ramp[heatStep(c[2],max)];
    ctx.beginPath();if(ctx.roundRect&&z>=8)ctx.roundRect(x+g,y+g,z-2*g,z-2*g,Math.min(3,z/4));else ctx.rect(x+g,y+g,z-2*g,z-2*g);ctx.fill();
   }
   for(const c of data.cells){if(!c[3])continue;            // a kill: a dot with a surface ring
    const [x,y,z]=box(c[0],c[1]),r=Math.max(3,Math.min(5,z*.18));
    ctx.beginPath();ctx.arc(x+z/2,y+z/2,r,0,2*Math.PI);ctx.fillStyle=t.text;ctx.fill();ctx.lineWidth=2;ctx.strokeStyle=t.surface;ctx.stroke();}
   ctx.font='12px '+(getComputedStyle(document.body).fontFamily||'sans-serif');ctx.textBaseline='middle';
   for(const b of data.landmarks||[]){                       // the bosses' places: a diamond and the name in text ink
    const [x,y]=at(b.x,b.y);ctx.beginPath();ctx.moveTo(x,y-6);ctx.lineTo(x+6,y);ctx.lineTo(x,y+6);ctx.lineTo(x-6,y);ctx.closePath();
    ctx.fillStyle=t.surface;ctx.fill();ctx.lineWidth=2;ctx.strokeStyle=t.text;ctx.stroke();
    const label=String(b.name||''),wide=ctx.measureText(label).width,left=x+10+wide>view.ox+view.w;
    ctx.textAlign=left?'right':'left';ctx.lineJoin='round';ctx.lineWidth=3;ctx.strokeStyle=t.surface;ctx.strokeText(label,left?x-10:x+10,y);   // a surface halo over squares
    ctx.fillStyle=t.muted;ctx.fillText(label,left?x-10:x+10,y);}
   if(hover&&hover.cell){const [x,y,z]=box(hover.cell[0],hover.cell[1]);ctx.lineWidth=2;ctx.strokeStyle=t.text;ctx.strokeRect(x+1,y+1,z-2,z-2);}
  }
  function render(){
   layout();draw();
   const cell=data.cell_size,max=Math.max(1,...data.cells.map(c=>c[2]));
   legend.replaceChildren();
   if(data.cells.length){
    const lead=document.createElement('span');lead.textContent='PvP hits per square: ';legend.appendChild(lead);
    const lo=document.createElement('span');lo.textContent='1 ';legend.appendChild(lo);
    for(let i=1;i<=5;i++){const sw=document.createElement('span');sw.className='heat-swatch';sw.style.background='var(--heat-'+i+')';legend.appendChild(sw);}   // follows the theme
    const hi=document.createElement('span');hi.textContent=' '+num(max);legend.appendChild(hi);
    if(data.cells.some(c=>c[3])){const k=document.createElement('span');k.className='heat-key heat-key-kill';k.textContent='a square with a kill';legend.appendChild(k);}
   }
   if((data.footprint||[]).length){const g=document.createElement('span');g.className='heat-key heat-key-ground';g.textContent='ground recordings have covered';legend.appendChild(g);}
   if((data.landmarks||[]).length){const b=document.createElement('span');b.className='heat-key heat-key-boss';b.textContent='a recorded boss';legend.appendChild(b);}
   legend.hidden=!legend.children.length;
   const busiest=data.cells.slice().sort((a,b)=>b[2]-a[2]||b[3]-a[3]).slice(0,25);
   rows.replaceChildren();
   if(busiest.length){
    const tbl=document.createElement('table');tbl.className='t';
    const head=tbl.createTHead().insertRow();for(const h of ['Square: x','Square: y','PvP hits','Kills']){const th=document.createElement('th');th.textContent=h;head.appendChild(th);}
    const body=tbl.createTBody();
    for(const c of busiest){const r=body.insertRow();for(const v of [num(c[0]*cell)+' to '+num((c[0]+1)*cell),num(c[1]*cell)+' to '+num((c[1]+1)*cell),num(c[2]),num(c[3])]){const td=r.insertCell();td.textContent=v;}}
    rows.appendChild(tbl);
    if(data.cells.length>busiest.length){const more=document.createElement('p');more.className='small muted';more.textContent='The 25 busiest of '+num(data.cells.length)+' squares.';rows.appendChild(more);}
   }
   table.hidden=!busiest.length;
   frame.hidden=!view;
   canvas.setAttribute('aria-label',data.available&&data.cells.length?`Abyss PvP heat map: ${plural(data.cells.length,'square','squares')} with PvP over ${HEAT_WINDOWS[data.window_seconds]||'the window shown'}, the busiest with ${plural(max,'hit','hits')}. The table below lists them.`:'The ground recordings have covered in the Abyss, with no PvP squares to show.');
  }
  function describe(){
   const when=new Date((data.generated_at||Date.now()/1000)*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
   if(data.available){
    status.textContent=`${HEAT_WINDOWS[data.window_seconds]?HEAT_WINDOWS[data.window_seconds].replace(/^the l/,'L'):'Recent fights'}: ${plural(data.fights,'fight','fights')} from ${plural(data.uploaders,'uploader','uploaders')}, ${plural(data.hits,'PvP hit','PvP hits')} and ${plural(data.kills,'kill','kills')} in ${plural(data.cells.length,'square','squares')}${data.hidden_cells?` (${plural(data.hidden_cells,'square','squares')} only one uploader recorded ${data.hidden_cells===1?'is':'are'} left out)`:''}. Updated ${when}.`;
   }else{
    const week=(data.windows||[]).find(w=>w.seconds===604800)||{uploaders:0};
    status.textContent=`Not enough recorded Abyss PvP yet: the map needs fights from at least ${data.min_uploaders||3} uploaders within 7 days, and has ${plural(week.uploaders,'uploader','uploaders')}. Public Live Meter logs of Abyss fights add to it.${(data.footprint||[]).length?' Meanwhile the map shows the ground recordings have covered.':''}`;
   }
   note.textContent=data.note||'';
  }
  async function load(){
   const n=++serial;refresh.disabled=true;
   try{
    if(!api)throw Error('No community server is set up.');
    const d=await api('/api/v1/pvp-heat?map=20&cell='+encodeURIComponent(cellSelect.value));
    if(n!==serial||disposed)return;
    if(!d||!Array.isArray(d.cells))throw Error('The community server does not offer the PvP heat map yet.');
    data=d;loadedAt=Date.now();hover=null;tip.hidden=true;
    if(!d.bounds){frame.hidden=true;legend.hidden=true;table.hidden=true;}else render();
    describe();
    const every=Math.max(300,Number(d.refresh_seconds)||900)*1000;
    if(timer)clearInterval(timer);
    timer=setInterval(()=>{if(!document.hidden)load();},every);
   }catch(e){
    if(n!==serial||disposed)return;
    const msg=String(e&&e.message||e);
    status.textContent=/not found|404|not served/i.test(msg)?'The community server does not offer the PvP heat map yet.':'The PvP heat map could not be loaded: '+msg;
    if(!data){frame.hidden=true;legend.hidden=true;table.hidden=true;}
   }finally{if(n===serial&&!disposed)refresh.disabled=false;}
  }
  function pointer(ev){
   if(!data||!view)return;
   const r=canvas.getBoundingClientRect(),px=ev.clientX-r.left,py=ev.clientY-r.top;
   const x=view.x0+(px-view.ox-view.pad)/view.s,y=view.y1-(py-view.pad)/view.s,cell=data.cell_size;
   const cx=Math.floor(x/cell),cy=Math.floor(y/cell);
   const found=data.cells.find(c=>c[0]===cx&&c[1]===cy);
   const boss=(data.landmarks||[]).find(b=>{const [bx,by]=at(b.x,b.y);return Math.hypot(bx-px,by-py)<=9;});
   const next=found?{cell:found}:boss?{boss}:null;
   if((next&&next.cell)!==(hover&&hover.cell)||(next&&next.boss)!==(hover&&hover.boss)){hover=next;draw();}
   if(!next){tip.hidden=true;return;}
   tip.replaceChildren();
   const lead=document.createElement('strong'),line=document.createElement('div'),where=document.createElement('div');
   where.className='muted';
   if(next.cell){
    const c=next.cell;lead.textContent=plural(c[2],'PvP hit','PvP hits');line.textContent=c[3]?plural(c[3],'kill','kills'):'no kills';
    where.textContent=`x ${num(c[0]*cell)} to ${num((c[0]+1)*cell)} · y ${num(c[1]*cell)} to ${num((c[1]+1)*cell)}`;
   }else{
    lead.textContent=String(next.boss.name||'');line.textContent='a recorded boss';where.textContent=`x ${num(next.boss.x)} · y ${num(next.boss.y)}`;
   }
   tip.append(lead,line,where);tip.hidden=false;
   const fr=frame.getBoundingClientRect(),left=Math.min(Math.max(4,ev.clientX-fr.left+14),fr.width-tip.offsetWidth-4),top=Math.max(4,ev.clientY-fr.top-tip.offsetHeight-10);
   tip.style.left=left+'px';tip.style.top=(top<4?ev.clientY-fr.top+16:top)+'px';
  }
  const leave=()=>{if(hover){hover=null;draw();}tip.hidden=true;};
  canvas.addEventListener('pointermove',pointer);canvas.addEventListener('pointerleave',leave);
  cellSelect.onchange=()=>{rememberCell(Number(cellSelect.value));load();};
  refresh.onclick=load;
  const redraw=()=>{if(raf)cancelAnimationFrame(raf);raf=requestAnimationFrame(()=>{raf=0;if(data&&data.bounds){layout();draw();}});};
  const visible=()=>{if(!document.hidden&&loadedAt&&Date.now()-loadedAt>((data&&data.refresh_seconds)||900)*1000)load();};
  document.addEventListener('visibilitychange',visible);
  const themes=new MutationObserver(redraw);themes.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  const scheme=window.matchMedia?window.matchMedia('(prefers-color-scheme: dark)'):null;if(scheme&&scheme.addEventListener)scheme.addEventListener('change',redraw);
  const sized=typeof ResizeObserver==='function'?new ResizeObserver(redraw):null;if(sized)sized.observe(panel);else window.addEventListener('resize',redraw);
  load();
  return {dispose:()=>{disposed=true;serial++;if(timer)clearInterval(timer);if(raf)cancelAnimationFrame(raf);document.removeEventListener('visibilitychange',visible);
   themes.disconnect();if(scheme&&scheme.removeEventListener)scheme.removeEventListener('change',redraw);if(sized)sized.disconnect();else window.removeEventListener('resize',redraw);panel.remove();}};
 }
 const AUTOLOAD='aion2.maps.autoload';
 function rememberedAutoload(){try{return localStorage.getItem(AUTOLOAD)==='1';}catch(_){return false;}}
 function rememberAutoload(on){try{if(on)localStorage.setItem(AUTOLOAD,'1');else localStorage.removeItem(AUTOLOAD);}catch(_){/* storage blocked: ask each time */}}
 function mount(root,io){
  root.innerHTML='<section class="win"><div class="wh"><h2>Interactive maps</h2><span class="sub">InteractiveMap.app</span></div><div class="wb"><div class="row"><label>Map <select data-map>'+Object.entries(zones).map(([id,name])=>'<option value="'+id+'">'+name+'</option>').join('')+'</select></label><a class="btn small" data-map-open target="_blank" rel="noopener noreferrer">Open provider ↗</a><label class="small"><input type="checkbox" data-map-auto> Load the map automatically</label></div><p class="small muted">Provider-hosted map, markers and controls. Map data and any account/checklist state belong to the provider. This view does not send your combat logs, profile or application credentials. Build/region applicability and marker completeness are not independently verified.</p><div class="map-frame"><div class="map-gate" data-map-gate><p>The map is hosted by InteractiveMap.app. Loading it downloads about 10–14 MB from the provider, including its advertising and tracking scripts.</p><button class="btn primary" type="button" data-map-load>Load the interactive map</button></div><iframe data-map-frame title="Interactive AION 2 map" sandbox="allow-scripts allow-same-origin allow-forms allow-popups" allow="fullscreen" referrerpolicy="no-referrer" hidden></iframe></div><p data-map-status role="status">The interactive map loads when you ask for it.</p><p class="small muted">If the embedded map is unavailable or browser storage is restricted, use Open provider. More regional map references: <a href="https://shugo.gg/map" target="_blank" rel="noopener noreferrer">Shugo.GG</a> · <a href="https://a2db.ru/en/maps" target="_blank" rel="noopener noreferrer">A2DB</a>.</p></div></section>';
  const select=root.querySelector('[data-map]'),frame=root.querySelector('iframe'),link=root.querySelector('[data-map-open]'),status=root.querySelector('[data-map-status]'),gate=root.querySelector('[data-map-gate]'),auto=root.querySelector('[data-map-auto]');
  // The provider's page is heavy and carries ad trackers, so it loads only when asked (or when the visitor chose to always load it).
  let shown=false;
  const load=()=>{const id=Object.prototype.hasOwnProperty.call(zones,select.value)?select.value:Object.keys(zones)[0];const url='https://interactivemap.app/aion2/maps/'+encodeURIComponent(id);link.href=url;if(!shown)return;status.textContent='Loading external interactive map…';frame.src=url+'?embed=light';frame.title=zones[id]+' interactive map';};
  const show=()=>{shown=true;gate.hidden=true;frame.hidden=false;load();};
  frame.onload=()=>{if(shown)status.textContent='Map frame loaded. Use the provider controls to filter markers, zoom and plan routes. If the map is blank, open the provider.';};
  frame.onerror=()=>status.textContent='The external map could not load. Open the provider to retry.';
  root.querySelector('[data-map-load]').onclick=show;
  auto.checked=rememberedAutoload();
  auto.onchange=()=>{rememberAutoload(auto.checked);if(auto.checked&&!shown)show();};
  select.onchange=load;load();
  if(auto.checked)show();
  const heat=mountHeat(root,io),routes=mountRoutes(root,select);
  return {dispose:()=>{frame.onload=null;frame.onerror=null;frame.src='about:blank';heat.dispose();routes.dispose();}};
 }
 window.A2Maps={mount,routesHTML,heatStep};
})();
