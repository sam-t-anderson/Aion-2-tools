/* Conditional crafting plans from a dated, source-attributed recipe snapshot. */
(function(){
 'use strict';
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const n=x=>Number(x).toLocaleString(undefined,{maximumFractionDigits:3});
 const grades={11:'Common',21:'Rare',31:'Epic',41:'Unique',51:'Heroic'};
 function mount(root,io={}){
  let catalog=null,selected='',search='',profession='',faction='',count=1,effective=null,seed=1,expand=false,result='',disposed=false;
  const stock={},$=s=>root.querySelector(s),item=id=>catalog.items[id]||{name:id},recipe=()=>catalog.recipes[selected];
  const image=id=>{const entry=item(id),url=String(entry.icon||'');const safe=/^https:\/\/gamers4\.life\/aion-2\/database\/icons\/assets\/Game\/[A-Za-z0-9_/-]+\.webp$/.test(url);return safe?`<img ${window.A2AssetHealth?A2AssetHealth.attributes({namespace:'gamers4life',kind:'item',id}):''} src="${esc(window.A2AssetHealth?A2AssetHealth.source(url):url)}" alt="" loading="lazy" onerror="this.hidden=true">`:'<span class="cr-profile-empty">◇</span>';};
  function card(id,detail){return `<article class="cr-profile-card" data-grade="${grades[item(id).grade]||''}">${image(id)}<div><strong>${esc(item(id).name)}</strong><span>${esc(detail)}</span><small>Source item ${esc(id)}</small></div></article>`;}
  function plan(){
   const leaves=new Map(),steps=[],warnings=new Set();let fee=0,visits=0;
   function walk(id,times,path){
    if(++visits>5000||path.length>20)throw Error('Recipe expansion exceeds its bounded depth/work limit. Use direct materials.');
    if(path.includes(id))throw Error('Recipe cycle detected. Use direct materials.');
    const r=catalog.recipes[id];fee+=r.fee*times;steps.push({recipe:id,crafts:times});
    if(!Number.isSafeInteger(fee))throw Error('Material plan exceeds safe numeric limits.');
    for(const input of r.inputs){const amount=input.quantity*times;if(!Number.isSafeInteger(amount))throw Error('Material plan exceeds safe numeric limits.');
     const sub=catalog.recipes[input.recipe];
     if(expand&&sub&&sub.output===input.item&&sub.faction===r.faction&&sub.combo_chance===0){walk(input.recipe,Math.ceil(amount/sub.quantity),[...path,id]);}
     else{leaves.set(input.item,(leaves.get(input.item)||0)+amount);if(expand&&sub&&sub.combo_chance>0)warnings.add('Combo-capable intermediates remain shopping-list items because normal/combo replacement semantics are unknown.');}
    }
   }
   walk(selected,count,[]);
   if([...leaves.values()].some(q=>!Number.isSafeInteger(q)))throw Error('Material plan exceeds safe numeric limits.');
   return {materials:[...leaves].map(([id,quantity])=>({id,quantity,owned:stock[id]||0,remaining:Math.max(0,quantity-(stock[id]||0))})),fee,steps,warnings:[...warnings]};
  }
  function results(){
   const rows=Object.entries(catalog.recipes).filter(([id,r])=>(!profession||r.profession===profession)&&(!faction||r.faction===faction)&&(id.includes(search)||item(r.output).name.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
   $('[data-recipe-list]').innerHTML=rows.slice(0,80).map(([id,r])=>`<button type="button" class="craft-recipe ${id===selected?'on':''}" data-recipe="${id}">${image(r.output)}<span>${esc(item(r.output).name)}<small>${esc(r.profession)} · ${r.faction==='light'?'Elyos':'Asmodian'} · mastery ${r.mastery_level} · ${id}</small></span></button>`).join('')||'<p>No matching recipes.</p>';
   $('[data-recipe-count]').textContent=rows.length+' matching recipes; showing up to 80. Search to narrow the list.';
   root.querySelectorAll('[data-recipe]').forEach(b=>b.onclick=()=>{selected=b.dataset.recipe;effective=null;result='';results();details();});
  }
  function details(){
   const r=recipe();if(!r){$('[data-craft-detail]').textContent='Select a recipe.';return;}
   const chance=effective??r.combo_chance;let p,error='';try{p=plan();}catch(e){error=e.message;}
   $('[data-craft-detail]').innerHTML=`<h2>${esc(item(r.output).name)}</h2><p>${esc(r.profession)} · ${r.faction==='light'?'Elyos':'Asmodian'} · ${esc(r.mastery_group)} mastery ${r.mastery_level} · recipe ${selected}</p><div class="row"><label>Planned completed crafts <input data-crafts type="number" min="1" max="10000" value="${count}"></label><label><input data-expand type="checkbox" ${expand?'checked':''}> Expand source-linked intermediates without combo outcomes</label></div><p class="small muted">Materials/fees assume every planned craft completes and consumes the listed inputs. General success, failures/refunds and modifier rules are unavailable. Intermediate branches round separately to whole normal-output crafts; surplus is not credited. These are planning assumptions, not guaranteed shopping requirements.</p><div class="craft-output"><div><h3>Normal product reference</h3>${card(r.output,n(r.quantity)+' per listed normal output · '+n(r.quantity*count)+' for the planned normal-output crafts')}</div><div><h3>Combo product reference</h3>${r.combo?card(r.combo,'Combo quantity and normal-output replacement rules unavailable'):'<p>No combo output in this recipe record.</p>'}</div></div><div class="note"><strong>Published combo trigger rate: ${n(r.combo_chance*100)}%</strong><p>General success rate: unavailable · ${effective===null?'Using the published combo rate.':'Using your assumed effective combo rate; no modifier formula is verified.'}</p><div class="row"><label>Assumed effective combo rate (%) <input data-chance type="number" min="0" max="100" step=".1" value="${String(Number((chance*100).toFixed(4)))}"></label><button class="btn small" data-rate-reset>Use source rate</button><label>Scenario seed <input data-seed type="number" min="0" max="4294967295" value="${seed}"></label><button class="btn small" data-simulate>Simulate combo checks</button></div><p>Conditional on ${n(count)} independent completed-craft checks with a fixed ${n(chance*100)}% combo rate: expected checks triggering combo ${n(count*chance)}; probability of at least one ${n((chance===1?1:-Math.expm1(count*Math.log1p(-chance)))*100)}%.</p><p data-simulation role="status">${esc(result)}</p></div><h3>Material plan ${expand?'(expanded where supported)':'(direct)'}</h3>${error?`<p class="note">${esc(error)}</p>`:`<div class="cr-profile-grid">${p.materials.map(m=>`<div>${card(m.id,'Required '+n(m.quantity)+' · remaining '+n(m.remaining))}<label>Owned base material <input data-owned="${m.id}" type="number" min="0" max="1000000000000" value="${m.owned}"></label></div>`).join('')}</div><p>Listed fees: ${n(p.fee)} Kinah · ${p.steps.length} recipe branches.</p>${p.warnings.map(w=>`<p class="note">${esc(w)}</p>`).join('')}<p class="small muted">Entered owned quantities subtract only from final material rows; they do not change recipe counts or fees. Nothing is uploaded or persisted automatically.</p><button class="btn small" data-plan-export>Export this material plan</button>`}<p><a href="https://gamers4.life/aion-2/database/en/recipe/${selected}/" target="_blank" rel="noopener noreferrer">View source recipe ↗</a></p>`;
   $('[data-crafts]').onchange=e=>{const x=Number(e.target.value);if(!Number.isInteger(x)||x<1||x>10000){e.target.value=count;return;}count=x;result='';details();};
   $('[data-expand]').onchange=e=>{expand=e.target.checked;details();};
   $('[data-chance]').onchange=e=>{const x=Number(e.target.value);if(e.target.value===''||!Number.isFinite(x)||x<0||x>100){e.target.value=chance*100;return;}effective=x/100;result='';details();};
   $('[data-rate-reset]').onclick=()=>{effective=null;result='';details();};
   $('[data-seed]').onchange=e=>{const x=Number(e.target.value);if(!Number.isInteger(x)||x<0||x>4294967295){e.target.value=seed;return;}seed=x;result='';$('[data-simulation]').textContent='';};
   $('[data-simulate]').onclick=()=>{let state=seed,hits=0;for(let i=0;i<count;i++){state=(state+0x6d2b79f5)>>>0;let x=Math.imul(state^(state>>>15),state|1);x^=x+Math.imul(x^(x>>>7),x|61);if(((x^(x>>>14))>>>0)/4294967296<chance)hits++;}result=`Illustrative scenario, seed ${seed}: ${n(hits)} of ${n(count)} combo checks triggered. This does not predict game outcomes or output quantities.`;$('[data-simulation]').textContent=result;};
   root.querySelectorAll('[data-owned]').forEach(e=>e.onchange=()=>{const x=Number(e.value);if(e.value===''||!Number.isInteger(x)||x<0||x>1e12){e.value=stock[e.dataset.owned]||0;return;}stock[e.dataset.owned]=x;details();});
   const output=$('[data-plan-export]');if(output)output.onclick=()=>{
    const doc={format:'a2craft-plan',version:1,source:catalog.source,source_sha256:catalog.source_sha256,source_retrieved_at:catalog.retrieved_at,game_build:null,recipe:selected,completed_crafts:count,assumed_effective_combo_chance:chance,seed,expand_intermediates:expand,...p,note:catalog.note};
    const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='craft-plan-'+selected+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('[data-simulation]').textContent='Material plan export requested. Check Downloads.';
   };
  }
  async function load(){
   root.textContent='Loading crafting catalog…';try{const response=await fetch(io.catalogURL||'/static/crafting-catalog.json');if(!response.ok)throw Error('Crafting catalog unavailable');catalog=await response.json();if(disposed||!root.isConnected)return;if(catalog.version!==1)throw Error('Unsupported crafting catalog');
    selected=Object.keys(catalog.recipes)[0];
    root.innerHTML=`<section class="win"><div class="wh"><h2>Crafting workshop</h2><span class="sub">Conditional recipe planning</span></div><div class="wb"><details class="note" open><summary>Recipe source and missing rules</summary><p>${esc(catalog.note)}</p><p>${Object.keys(catalog.recipes).length} recipes · ${Object.keys(catalog.items).length} source item references · retrieved ${esc(new Date(catalog.retrieved_at).toLocaleString())} · source SHA256 ${esc(catalog.source_sha256.slice(0,16))} · <a href="${esc(catalog.source_page)}" target="_blank" rel="noopener noreferrer">Gamers4Life source</a>.</p></details><div class="craft-workspace"><aside><div class="row"><label>Search <input data-search placeholder="Item name or recipe ID"></label><label>Profession <select data-profession><option value="">All professions</option>${[...new Set(Object.values(catalog.recipes).map(r=>r.profession))].sort().map(p=>`<option>${esc(p)}</option>`).join('')}</select></label><label>Faction <select data-faction><option value="">Both factions</option><option value="light">Elyos</option><option value="dark">Asmodian</option></select></label></div><p data-recipe-count class="small muted"></p><div data-recipe-list></div></aside><div data-craft-detail></div></div></div></section>`;
    $('[data-search]').oninput=e=>{search=e.target.value;results();};$('[data-profession]').onchange=e=>{profession=e.target.value;results();};$('[data-faction]').onchange=e=>{faction=e.target.value;results();};results();details();
   }catch(e){if(!disposed&&root.isConnected)root.textContent='Could not open crafting workshop: '+e.message;}
  }
  load();return {dispose:()=>{disposed=true;}};
 }
 window.A2Crafting={mount};
})();
