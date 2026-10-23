/* Provider-supported interactive map embedding; no inferred game coordinates. Beside it, the
   farming-route catalog (farming-routes.json, built by `python -m aion2calc routes-build`): ordered
   waypoint loops from sources whose terms allow reuse, credited; guide links where no such source
   exists. Nothing here is invented: a zone without a permitted source says so. */
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
 function mount(root){
  root.innerHTML='<section class="win"><div class="wh"><h2>Interactive maps</h2><span class="sub">InteractiveMap.app</span></div><div class="wb"><div class="row"><label>Map <select data-map>'+Object.entries(zones).map(([id,name])=>'<option value="'+id+'">'+name+'</option>').join('')+'</select></label><a class="btn small" data-map-open target="_blank" rel="noopener noreferrer">Open provider ↗</a></div><p class="small muted">Provider-hosted map, markers and controls. Map data and any account/checklist state belong to the provider. This view does not send your combat logs, profile or application credentials. Build/region applicability and marker completeness are not independently verified.</p><div class="map-frame"><iframe data-map-frame title="Interactive AION 2 map" sandbox="allow-scripts allow-same-origin allow-forms allow-popups" allow="fullscreen" referrerpolicy="no-referrer" loading="lazy"></iframe></div><p data-map-status role="status">Loading external interactive map…</p><p class="small muted">If the embedded map is unavailable or browser storage is restricted, use Open provider. More regional map references: <a href="https://shugo.gg/map" target="_blank" rel="noopener noreferrer">Shugo.GG</a> · <a href="https://a2db.ru/en/maps" target="_blank" rel="noopener noreferrer">A2DB</a>.</p></div></section>';
  const select=root.querySelector('[data-map]'),frame=root.querySelector('iframe'),link=root.querySelector('[data-map-open]'),status=root.querySelector('[data-map-status]');
  const load=()=>{const id=Object.prototype.hasOwnProperty.call(zones,select.value)?select.value:Object.keys(zones)[0];const url='https://interactivemap.app/aion2/maps/'+encodeURIComponent(id);link.href=url;status.textContent='Loading external interactive map…';frame.src=url+'?embed=light';frame.title=zones[id]+' interactive map';};
  frame.onload=()=>{status.textContent='Map frame loaded. Use the provider controls to filter markers, zoom and plan routes. If the map is blank, open the provider.';};
  frame.onerror=()=>status.textContent='The external map could not load. Open the provider to retry.';
  select.onchange=load;load();
  const routes=mountRoutes(root,select);
  return {dispose:()=>{frame.onload=null;frame.onerror=null;frame.src='about:blank';routes.dispose();}};
 }
 window.A2Maps={mount,routesHTML};
})();
