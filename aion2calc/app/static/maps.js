/* Provider-supported interactive map embedding; no inferred game coordinates. */
(function(){
 'use strict';
 const zones={verteron:'Verteron',altgard:'Altgard',poeta:'Poeta',ishalgen:'Ishalgen'};
 function mount(root){
  root.innerHTML='<section class="win"><div class="wh"><h2>Interactive maps</h2><span class="sub">InteractiveMap.app</span></div><div class="wb"><div class="row"><label>Map <select data-map>'+Object.entries(zones).map(([id,name])=>'<option value="'+id+'">'+name+'</option>').join('')+'</select></label><a class="btn small" data-map-open target="_blank" rel="noopener noreferrer">Open provider ↗</a></div><p class="small muted">Provider-hosted map, markers and controls. Map data and any account/checklist state belong to the provider. This view does not send your combat logs, profile or application credentials. Build/region applicability and marker completeness are not independently verified.</p><div class="map-frame"><iframe data-map-frame title="Interactive AION 2 map" sandbox="allow-scripts allow-same-origin allow-forms allow-popups" allow="fullscreen" referrerpolicy="no-referrer" loading="lazy"></iframe></div><p data-map-status role="status">Loading external interactive map…</p><p class="small muted">If the embedded map is unavailable or browser storage is restricted, use Open provider. More regional map references: <a href="https://shugo.gg/map" target="_blank" rel="noopener noreferrer">Shugo.GG</a> · <a href="https://a2db.ru/en/maps" target="_blank" rel="noopener noreferrer">A2DB</a>.</p></div></section>';
  const select=root.querySelector('[data-map]'),frame=root.querySelector('iframe'),link=root.querySelector('[data-map-open]'),status=root.querySelector('[data-map-status]');
  const load=()=>{const url='https://interactivemap.app/aion2/maps/'+select.value;link.href=url;status.textContent='Loading external interactive map…';frame.src=url+'?embed=light';frame.title=zones[select.value]+' interactive map';};
  frame.onload=()=>{status.textContent='Map frame loaded. Use the provider controls to filter markers, zoom and plan routes. If the map is blank, open the provider.';};
  frame.onerror=()=>status.textContent='The external map could not load. Open the provider to retry.';
  select.onchange=load;load();return {dispose:()=>{frame.onload=null;frame.onerror=null;frame.src='about:blank';}};
 }
 window.A2Maps={mount};
})();
