/* Conditional crafting plans from a dated, source-attributed recipe snapshot. */
(function(){
 'use strict';
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const n=x=>Number(x).toLocaleString(undefined,{maximumFractionDigits:3});
 // The date with the time of day, in the computer's clock: 2026-10-23 15:04:05.
 const whenAt = (x) => { if (x == null || x === "") return "—"; const d = new Date(x); if (!Number.isFinite(d.getTime())) return "—"; const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
 const grades={11:'Common',21:'Rare',31:'Epic',41:'Unique',51:'Heroic'};
 const GRADE_ORDER=['Common','Rare','Epic','Unique','Heroic'];
 // Crafting proficiency is a single absolute number in the source (a recipe's mastery_level, e.g. 55),
 // but in game it reads as a tier plus a level within that tier, 50 levels per tier: Novice 1–50,
 // Professional 51–100, Expert 101–150, Master 151–200. So level 55 is Professional level 5. The
 // source's own coarse group label is ignored; tier and within-tier level are derived from the number.
 const TIERS=['Novice','Professional','Expert','Master'],TIER_SPAN=50;
 const tierRank=name=>{const i=TIERS.indexOf(name);return i<0?0:i;};
 // Absolute source proficiency -> {rank, tier name, level within that tier (1..TIER_SPAN)}.
 function band(abs){const a=Math.max(1,Math.round(Number(abs)||1));const rank=Math.min(TIERS.length-1,Math.floor((a-1)/TIER_SPAN));return {rank,tier:TIERS[rank],level:a-TIER_SPAN*rank};}
 const tierLevelLabel=abs=>{const b=band(abs);return `${b.tier} level ${b.level}`;};
 const TYPE_LABELS={Weapon:'Weapon',Armor:'Armor',Accessory:'Accessory',ETC:'Material / other'};
 function mount(root,io={}){
  let catalog=null,success=null,selected='',search='',profession='',faction='',tier='',itype='',myTier='',myLevel='',craftableOnly=false,count=1,effective=null,seed=1,expand=false,result='',disposed=false;
  // The player's absolute proficiency from the entered tier + within-tier level, or null when no
  // level is entered (nothing to compare). A blank tier is read as the lowest (Novice).
  const myAbs=()=>myLevel===''?null:TIER_SPAN*tierRank(myTier||TIERS[0])+Number(myLevel);
  // Community-measured success rate for a recipe (matched by product name), or '' when none.
  // base_success is the measured chance at the recipe's own proficiency; it rises toward a per-tier
  // cap as you out-level it (standard gear never reaches 100%). The base is community-measured
  // (metabot.gg, not official); the over-level projection is an estimate scaled toward that cap.
  function successLine(r){
   const sx=success&&success.recipes?success.recipes[String(item(r.output).name||'').toLowerCase()]:null;
   const src='<span class="muted">community-measured (metabot.gg), not official</span>';
   if(!sx)return '<p class="small muted">Success rate: not available for this recipe in the community dataset.</p>';
   const base=sx.base_success,cap=base>=90?99:base>=78?96.8:base>=75?94.6:93.1,req=sx.mastery,reqLabel=tierLevelLabel(req),a=myAbs();
   if(a===null||a<req)
    return `<p class="small">Success rate: <strong>${base}%</strong> at the required proficiency (${esc(reqLabel)}), rising toward ~${cap}% as you out-level it. ${src}.</p>`;
   const diff=a-req;
   if(diff===0)return `<p class="small">Success rate: <strong>${base}%</strong> at your proficiency. ${src}.</p>`;
   const proj=Math.min(cap,base+(cap-base)*Math.min(diff,42)/42);
   return `<p class="small">Success rate: <strong>${base}%</strong> at the requirement (${esc(reqLabel)}); <strong>~${proj.toFixed(1)}%</strong> estimated at your +${diff} proficiency (projected toward the ~${cap}% cap). Base ${src}; the projection is an estimate.</p>`;
  }
  const enhancements={},stock={},$=s=>root.querySelector(s),item=id=>catalog.items[id]||{name:id},recipe=()=>catalog.recipes[selected];
  const gradeName=id=>grades[item(id).grade]||'';
  const typeOf=id=>{const m=/\/Item\/([A-Za-z0-9]+)\//.exec(String(item(id).icon||''));return m?m[1]:'';};
  // Can a crafter at the entered tier/level attempt this recipe? No level entered → don't gate.
  // Both sides reduce to one absolute proficiency number, so the comparison is a simple >=.
  function canCraft(r){
   const a=myAbs();
   return a===null?true:a>=r.mastery_level;
  }
  const image=id=>{const entry=item(id),url=String(entry.icon||'');const safe=/^https:\/\/gamers4\.life\/aion-2\/database\/icons\/assets\/Game\/[A-Za-z0-9_/-]+\.webp$/.test(url);return safe?`<img ${window.A2AssetHealth?A2AssetHealth.attributes({namespace:'gamers4life',kind:'item',id}):''} src="${esc(window.A2AssetHealth?A2AssetHealth.source(url):url)}" alt="" referrerpolicy="no-referrer" loading="lazy" onerror="this.onerror=null;this.src='static/logo.png';this.title='Source image unavailable'">`:'<span class="cr-profile-empty">◇</span>';};
  function card(id,detail){return `<article class="cr-profile-card" data-grade="${grades[item(id).grade]||''}">${image(id)}<div><strong>${esc(item(id).name)}</strong><span>${esc(detail)}</span><small>Source item ${esc(id)}</small></div></article>`;}
  const statLabel=id=>catalog.stat_display?.labels?.[id]||id;
  const statValue=(id,value)=>catalog.stat_display?.percent?.includes(id)?n(value/100)+'%':n(value);
  function outputStats(id){
   const d=catalog.item_details?.[id];
   if(!d || d.status==='unavailable')return '<p class="small muted">Item stats unavailable in this source record.</p>';
   const levels=d.enhancements||[],level=enhancements[id]||0,bonus=levels.find(e=>e.level===level)?.stats||{},keys=[...new Set([...Object.keys(d.base||{}),...Object.keys(bonus)])];
   const rows=keys.map(key=>`<tr><th scope="row">${esc(statLabel(key))}</th><td>${statValue(key,d.base?.[key]||0)}</td>${level?`<td>${statValue(key,bonus[key]||0)}</td><td>${statValue(key,(d.base?.[key]||0)+(bonus[key]||0))}</td>`:''}</tr>`).join('');
   const rolls=(d.rolls||[]).map(row=>`<tr><th scope="row">${esc(statLabel(row.id))}</th><td>${statValue(row.id,row.min)} – ${statValue(row.id,row.max)}</td></tr>`).join('');
   const source=/^https:\/\/gamers4\.life\/aion-2\/database\/db\/item\/en\/[1-9][0-9]{0,18}\.json$/.test(d.source||'')?`<a href="${esc(d.source)}" target="_blank" rel="noopener noreferrer">Source item record ↗</a>`:'';
   return `<section class="craft-item-stats"><h4>Item stats${d.equipment?.itemLevel?' · item level '+n(d.equipment.itemLevel):''}</h4>${d.variant?`<p class="small muted">Source variant ${esc(d.variant)}</p>`:''}${levels.length?`<label class="small">Enhancement preview <select data-product-enhancement="${esc(id)}"><option value="0">Base (+0)</option>${levels.map(row=>`<option value="${row.level}" ${level===row.level?'selected':''}>+${row.level}</option>`).join('')}</select></label>`:''}${rows?`<div class="craft-stat-scroll"><table class="t"><thead><tr><th>Stat</th><th>Base</th>${level?'<th>Listed bonus</th><th>Preview total</th>':''}</tr></thead><tbody>${rows}</tbody></table></div>`:'<p class="small muted">No base item stats listed in this record.</p>'}${rolls?`<details><summary>Possible random rolls (${d.rolls.length})</summary><p class="small muted">Source ranges only; no roll is selected or included in the preview.</p><div class="craft-stat-scroll"><table class="t"><thead><tr><th>Stat</th><th>Range</th></tr></thead><tbody>${rolls}</tbody></table></div></details>`:''}${d.effect_reference?`<p class="small muted">Use effect: ${esc(d.effect_reference)}. Effect coefficients are unavailable.</p>`:''}<p class="small muted">Preview uses base stats plus the listed bonus for the selected enhancement. Random rolls and breakthrough bonuses are excluded. Source values follow the publisher's display units; unrecognized stat IDs remain raw. ${source}</p></section>`;
  }
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
  // What rarities, item types, mastery tiers and top level the selected profession actually makes
  // (all recipes when no profession is picked), so the filters only offer relevant choices.
  function profMeta(){
   const g=new Set(),t=new Set(),tierMax={};
   for(const r of Object.values(catalog.recipes)){
    if(profession&&r.profession!==profession)continue;
    const gn=gradeName(r.output);if(gn)g.add(gn);
    const ty=typeOf(r.output);if(ty)t.add(ty);
    if(Number.isInteger(r.mastery_level)){const b=band(r.mastery_level);tierMax[b.tier]=Math.max(tierMax[b.tier]||0,b.level);}
   }
   // tiers: only those the profession actually makes recipes in; tierMax[tier]: the highest
   // within-tier level needed there, so the level field caps at the profession's real maximum.
   return {grades:GRADE_ORDER.filter(x=>g.has(x)),types:[...t].sort(),tiers:TIERS.filter(x=>x in tierMax),tierMax};
  }
  // The level cap for the currently selected tier (the profession's own max in that tier, else the
  // 50-level tier span), so "Level" never exceeds the max for that profession's tier.
  const levelCap=meta=>{meta=meta||profMeta();return (myTier&&meta.tierMax[myTier])?meta.tierMax[myTier]:TIER_SPAN;};
  // Rebuild the rarity/type/your-tier options and the level cap for the current profession, dropping
  // any current selection the new profession doesn't offer.
  function renderFilters(){
   const meta=profMeta();
   if(tier&&!meta.grades.includes(tier))tier='';
   if(itype&&!meta.types.includes(itype))itype='';
   if(myTier&&!meta.tiers.includes(myTier))myTier='';
   const cap=levelCap(meta);
   if(myLevel!==''&&Number(myLevel)>cap)myLevel=String(cap);
   $('[data-tier]').innerHTML='<option value="">All rarities</option>'+meta.grades.map(x=>`<option ${x===tier?'selected':''}>${esc(x)}</option>`).join('');
   $('[data-type]').innerHTML='<option value="">All types</option>'+meta.types.map(x=>`<option value="${esc(x)}" ${x===itype?'selected':''}>${esc(TYPE_LABELS[x]||x)}</option>`).join('');
   $('[data-mytier]').innerHTML='<option value="">—</option>'+meta.tiers.map(x=>`<option value="${esc(x)}" ${x===myTier?'selected':''}>${esc(x)}</option>`).join('');
   const lvl=$('[data-mylevel]');lvl.max=cap;lvl.placeholder='1–'+cap;lvl.value=myLevel;
  }
  function results(){
   const rows=Object.entries(catalog.recipes).filter(([id,r])=>(!profession||r.profession===profession)&&(!faction||r.faction===faction)
    &&(!tier||gradeName(r.output)===tier)&&(!itype||typeOf(r.output)===itype)&&(!craftableOnly||canCraft(r))
    &&(id.includes(search)||item(r.output).name.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
   $('[data-recipe-list]').innerHTML=rows.slice(0,80).map(([id,r])=>`<button type="button" class="craft-recipe ${id===selected?'on':''}" data-recipe="${id}">${image(r.output)}<span>${esc(item(r.output).name)}<small>${esc(gradeName(r.output)||'—')} · ${esc(r.profession)} · ${r.faction==='light'?'Elyos':'Asmodian'} · ${esc(tierLevelLabel(r.mastery_level))}${myLevel!==''?(canCraft(r)?' · ✓ you can craft':' · locked for you'):''}</small></span></button>`).join('')||'<p>No matching recipes. Widen the tier, type or profession filters.</p>';
   $('[data-recipe-count]').textContent=rows.length+' matching recipes; showing up to 80. Filter or search to narrow the list.';
   root.querySelectorAll('[data-recipe]').forEach(b=>b.onclick=()=>{selected=b.dataset.recipe;effective=null;result='';results();details();});
  }
  function details(){
   const r=recipe();if(!r){$('[data-craft-detail]').textContent='Select a recipe.';return;}
   const chance=effective??r.combo_chance;let p,error='';try{p=plan();}catch(e){error=e.message;}
   const standing=(()=>{
    const a=myAbs();
    if(a===null)return '<p class="small muted">Enter your crafting tier and level above to see whether you can make this and your level margin.</p>';
    const reqLabel=tierLevelLabel(r.mastery_level),you=`${esc(myTier||TIERS[0])} level ${esc(myLevel)}`,margin=a-r.mastery_level;
    return margin>=0
     ? `<p class="small">You can craft this: your ${you} is ${margin===0?'exactly at':('+'+margin+' above')} the required <strong>${esc(reqLabel)}</strong>. The exact success rate isn't published in the source; a larger margin is typically easier.</p>`
     : `<p class="note">You're ${-margin} level${-margin===1?'':'s'} short: this needs <strong>${esc(reqLabel)}</strong> and you entered ${you}.</p>`;
   })();
   $('[data-craft-detail]').innerHTML=`<h2>${esc(item(r.output).name)}</h2><p>${esc(gradeName(r.output)||'—')} · ${esc(TYPE_LABELS[typeOf(r.output)]||typeOf(r.output)||'item')} · ${esc(r.profession)} · ${r.faction==='light'?'Elyos':'Asmodian'} · ${esc(tierLevelLabel(r.mastery_level))} · recipe ${selected}</p>${standing}${successLine(r)}<div class="row"><label>Planned completed crafts <input data-crafts type="number" min="1" max="10000" value="${count}"></label><label><input data-expand type="checkbox" ${expand?'checked':''}> Expand source-linked intermediates without combo outcomes</label></div><p class="small muted">Materials/fees assume every planned craft completes and consumes the listed inputs. General success, failures/refunds and modifier rules are unavailable. Intermediate branches round separately to whole normal-output crafts; surplus is not credited. These are planning assumptions, not guaranteed shopping requirements.</p><div class="craft-detail-columns"><section class="craft-products"><div class="craft-output"><div><h3>Normal product reference</h3>${card(r.output,n(r.quantity)+' per listed normal output · '+n(r.quantity*count)+' for the planned normal-output crafts')}${outputStats(r.output)}</div><div><h3>Combo product reference</h3>${r.combo?card(r.combo,'Combo quantity and normal-output replacement rules unavailable')+outputStats(r.combo):'<p>No combo output in this recipe record.</p>'}</div></div><div class="note"><strong>Published combo trigger rate: ${n(r.combo_chance*100)}%</strong><p>Craft success rate is shown above (community-measured where available) · ${effective===null?'Using the published combo rate.':'Using your assumed effective combo rate; no modifier formula is verified.'}</p><div class="row"><label>Assumed effective combo rate (%) <input data-chance type="number" min="0" max="100" step=".1" value="${String(Number((chance*100).toFixed(4)))}"></label><button class="btn small" data-rate-reset>Use source rate</button><label>Scenario seed <input data-seed type="number" min="0" max="4294967295" value="${seed}"></label><button class="btn small" data-simulate>Simulate combo checks</button></div><p>Conditional on ${n(count)} independent completed-craft checks with a fixed ${n(chance*100)}% combo rate: expected checks triggering combo ${n(count*chance)}; probability of at least one ${n((chance===1?1:-Math.expm1(count*Math.log1p(-chance)))*100)}%.</p><p data-simulation role="status">${esc(result)}</p></div></section><section class="craft-materials"><h3>Material plan ${expand?'(expanded where supported)':'(direct)'}</h3>${error?`<p class="note">${esc(error)}</p>`:`<div class="cr-profile-grid">${p.materials.map(m=>`<div>${card(m.id,'Required '+n(m.quantity)+' · remaining '+n(m.remaining))}<label>Owned base material <input data-owned="${m.id}" type="number" min="0" max="1000000000000" value="${m.owned}"></label></div>`).join('')}</div><p>Listed fees: ${n(p.fee)} Kinah · ${p.steps.length} recipe branches.</p>${p.warnings.map(w=>`<p class="note">${esc(w)}</p>`).join('')}<p class="small muted">Entered owned quantities subtract only from final material rows; they do not change recipe counts or fees. Nothing is uploaded or persisted automatically.</p><button class="btn small" data-plan-export>Export this material plan</button>`}</section></div><p><a href="https://gamers4.life/aion-2/database/en/recipe/${selected}/" target="_blank" rel="noopener noreferrer">View source recipe ↗</a></p>`;
   $('[data-crafts]').onchange=e=>{const x=Number(e.target.value);if(!Number.isInteger(x)||x<1||x>10000){e.target.value=count;return;}count=x;result='';details();};
   root.querySelectorAll('[data-product-enhancement]').forEach(e=>e.onchange=()=>{const id=e.dataset.productEnhancement,level=Number(e.value);if(level===0||(catalog.item_details[id]?.enhancements||[]).some(row=>row.level===level)){enhancements[id]=level;details();}});
   $('[data-expand]').onchange=e=>{expand=e.target.checked;details();};
   $('[data-chance]').onchange=e=>{const x=Number(e.target.value);if(e.target.value===''||!Number.isFinite(x)||x<0||x>100){e.target.value=chance*100;return;}effective=x/100;result='';details();};
   $('[data-rate-reset]').onclick=()=>{effective=null;result='';details();};
   $('[data-seed]').onchange=e=>{const x=Number(e.target.value);if(!Number.isInteger(x)||x<0||x>4294967295){e.target.value=seed;return;}seed=x;result='';$('[data-simulation]').textContent='';};
   $('[data-simulate]').onclick=()=>{let state=seed,hits=0;for(let i=0;i<count;i++){state=(state+0x6d2b79f5)>>>0;let x=Math.imul(state^(state>>>15),state|1);x^=x+Math.imul(x^(x>>>7),x|61);if(((x^(x>>>14))>>>0)/4294967296<chance)hits++;}result=`Illustrative scenario, seed ${seed}: ${n(hits)} of ${n(count)} combo checks triggered. This does not predict game outcomes or output quantities.`;$('[data-simulation]').textContent=result;};
   root.querySelectorAll('[data-owned]').forEach(e=>e.onchange=()=>{const x=Number(e.value);if(e.value===''||!Number.isInteger(x)||x<0||x>1e12){e.value=stock[e.dataset.owned]||0;return;}stock[e.dataset.owned]=x;details();});
   const output=$('[data-plan-export]');if(output)output.onclick=()=>{
    const doc={format:'a2craft-plan',version:1,source:catalog.source,source_sha256:catalog.source_sha256,source_retrieved_at:catalog.retrieved_at,game_build:null,recipe:selected,products:[r.output,r.combo].filter(Boolean).map(id=>({id,enhancement_preview:enhancements[id]||0,reference:catalog.item_details?.[id]||null})),item_details_retrieved_at:catalog.item_details_retrieved_at,completed_crafts:count,assumed_effective_combo_chance:chance,seed,expand_intermediates:expand,...p,note:catalog.note};
    const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='craft-plan-'+selected+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('[data-simulation]').textContent='Material plan export requested. Check Downloads.';
   };
  }
  async function load(){
   root.textContent='Loading crafting catalog…';try{const response=await fetch(io.catalogURL||'/static/crafting-catalog.json');if(!response.ok)throw Error('Crafting catalog unavailable');catalog=await response.json();if(disposed||!root.isConnected)return;if(catalog.version!==1)throw Error('Unsupported crafting catalog');
    try{const su=await fetch(io.successURL||(io.catalogURL?io.catalogURL.replace(/crafting-catalog\.json(\?.*)?$/,'crafting-success.json'):'/static/crafting-success.json'));if(su.ok){const sd=await su.json();if(sd&&sd.version===1&&sd.recipes)success=sd;}}catch(_){/* success rates are optional; the recipe shows 'not available' without them */}
    selected=Object.keys(catalog.recipes)[0];
    root.innerHTML=`<section class="win"><div class="wh"><h2>Crafting workshop</h2><span class="sub">Conditional recipe planning</span></div><div class="wb"><details class="note" open><summary>Recipe source and missing rules</summary><p>${esc(catalog.note)}</p><p>${esc(catalog.item_details_note||'Item stat references unavailable.')}</p><p>${Object.keys(catalog.recipes).length} recipes · ${Object.keys(catalog.items).length} source item references · retrieved ${esc(whenAt(catalog.retrieved_at))} · source SHA256 ${esc(catalog.source_sha256.slice(0,16))} · <a href="${esc(catalog.source_page)}" target="_blank" rel="noopener noreferrer">Gamers4Life source</a>.</p></details><div class="craft-workspace"><aside><div class="row"><label>Search <input data-search placeholder="Item name or recipe ID"></label><label>Profession <select data-profession><option value="">All professions</option>${[...new Set(Object.values(catalog.recipes).map(r=>r.profession))].sort().map(p=>`<option>${esc(p)}</option>`).join('')}</select></label><label>Faction <select data-faction><option value="">Both factions</option><option value="light">Elyos</option><option value="dark">Asmodian</option></select></label></div><div class="row"><label>Rarity <select data-tier><option value="">All rarities</option>${GRADE_ORDER.map(g=>`<option>${g}</option>`).join('')}</select></label><label>Item type <select data-type><option value="">All types</option>${[...new Set(Object.values(catalog.recipes).map(r=>typeOf(r.output)).filter(Boolean))].sort().map(t=>`<option value="${esc(t)}">${esc(TYPE_LABELS[t]||t)}</option>`).join('')}</select></label></div><fieldset class="row" style="border:0;padding:0;margin:0"><legend class="small muted" style="padding:0">Your crafting mastery (optional — to see what you can make)</legend><label>Tier <select data-mytier><option value="">—</option>${TIERS.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}</select></label><label>Level <input data-mylevel type="number" min="1" max="50" placeholder="1–50" style="width:92px"></label><label><input data-craftable type="checkbox"> Only what I can craft</label></fieldset><p data-recipe-count class="small muted"></p><div data-recipe-list></div></aside><div data-craft-detail></div></div></div></section>`;
    $('[data-search]').oninput=e=>{search=e.target.value;results();};
    $('[data-profession]').onchange=e=>{profession=e.target.value;renderFilters();results();details();};
    $('[data-faction]').onchange=e=>{faction=e.target.value;results();};
    $('[data-tier]').onchange=e=>{tier=e.target.value;results();};$('[data-type]').onchange=e=>{itype=e.target.value;results();};
    $('[data-mytier]').onchange=e=>{myTier=e.target.value;renderFilters();results();details();};
    $('[data-mylevel]').oninput=e=>{const v=e.target.value,cap=levelCap();myLevel=(v===''||(Number.isInteger(+v)&&+v>=1&&+v<=cap))?v:myLevel;e.target.value=myLevel;results();details();};
    $('[data-craftable]').onchange=e=>{craftableOnly=e.target.checked;results();};
    renderFilters();results();details();
   }catch(e){if(!disposed&&root.isConnected)root.textContent='Could not open crafting workshop: '+e.message;}
  }
  load();return {dispose:()=>{disposed=true;}};
 }
 window.A2Crafting={mount};
})();
