/* Local allocation drafts. Source profiles and scores remain read-only references. */
(function(){
  'use strict';
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const object=x=>x&&typeof x==='object'&&!Array.isArray(x);
  const copy=x=>JSON.parse(JSON.stringify(x));
  const integer=(x,min,max)=>Number.isInteger(x)&&x>=min&&x<=max;
  const bytes=x=>new Blob([JSON.stringify(x)]).size;
  const MAX=2*1024*1024,STORE='a2-build-drafts-v1';
  function mount(root,io={}){
    let catalog=null,draft=null,reference=io.reference||null,source=io.source||{},tab=io.reference?'reference':'draft',skillFilter='',boardName='',serial=0,disposed=false,dirty=false,evaluation=null,evaluating=false,inputBuffer=null;
    const $=s=>root.querySelector(s),cls=()=>catalog.classes[draft.class];
    const message=text=>{if(!disposed&&root.isConnected)$('[data-message]').textContent=text;};
    const cost=(levels,prices)=>Object.values(levels).reduce((sum,n)=>sum+prices.slice(0,n).reduce((a,b)=>a+b,0),0);
    function fresh(name,mode='pve',level=45){
      const row=catalog.classes[name].budget.filter(b=>b.level<=level).at(-1)||{skill:0,stigma:0};
      return {format:'a2build',version:1,name:name+'_'+level+'_'+mode.toUpperCase(),class:name,level,mode,notes:'',catalog_revision:catalog.revision,
        budgets:{skill:row.skill,stigma:row.stigma+1,daevanion:0,boards:{}},build:{sp:{},stigmas:{},specs:{},bonus:{},daevanion_nodes:[]},reference:null,source:{},loadout:{components:[]},genus:{},genus_mix:{Cogni:25,Fera:25,Natura:25,Varian:25,Special:0}};
    }
    function normalize(value){
      if(!object(value)||value.format!=='a2build'||value.version!==1||!catalog.classes[value.class])throw Error('Choose an a2build v1 document with a known class.');
      if(!integer(value.level,1,45)||!['pve','pvp'].includes(value.mode))throw Error('Choose level 1–45 and PvE or PvP.');
      const out=fresh(value.class,value.mode,value.level),cd=catalog.classes[value.class],skills=new Map(cd.skills.map(s=>[String(s.id),s]));
      out.name=String(value.name||out.name).slice(0,120);out.notes=String(value.notes||'').slice(0,4000);
      out.catalog_revision=String(value.catalog_revision||'unknown').slice(0,64);
      if(!object(value.budgets)||!object(value.build))throw Error('Missing budgets or allocations.');
      for(const key of ['skill','stigma','daevanion']){if(!integer(value.budgets[key],0,10000))throw Error('Invalid '+key+' budget.');out.budgets[key]=value.budgets[key];}
      if(!object(value.budgets.boards||{})||Object.keys(value.budgets.boards||{}).length>cd.boards.length)throw Error('Invalid board budgets.');
      for(const [key,n] of Object.entries(value.budgets.boards||{})){if(!cd.boards.some(b=>b.name===key)||!integer(n,0,10000))throw Error('Unknown board budget.');out.budgets.boards[key]=n;}
      for(const field of ['sp','stigmas','bonus','specs']){
        const values=value.build[field]||{};
        if(!object(values)||Object.keys(values).length>cd.skills.length)throw Error('Invalid '+field+' allocation.');
        for(const [id,v] of Object.entries(values)){
          const sk=skills.get(id);if(!sk)throw Error('Unknown skill ID '+id+'.');
          if(field==='specs'){
            if(sk.kind!=='active'||!Array.isArray(v)||v.length>5||new Set(v).size!==v.length||v.some(n=>!integer(n,1,999999999)||!sk.specs.some(e=>e.id===n)))throw Error('Invalid supporting effects for '+sk.name+'.');
            out.build.specs[id]=v.slice();
          }else{
            const cap=field==='sp'?Math.min(10,sk.buyMax||10):field==='stigmas'?20:30;
            if(!integer(v,field==='bonus'?0:1,cap)||(field==='sp'&& !['active','passive'].includes(sk.kind))||(field==='stigmas'&&sk.kind!=='stigma')||(field==='bonus'&&sk.kind==='stigma'))throw Error('Invalid '+field+' level for '+sk.name+'.');
            out.build[field][id]=v;
          }
        }
      }
      const nodes=value.build.daevanion_nodes;
      const known=new Set(cd.boards.flatMap(b=>b.nodes.map(n=>n.id)));
      if(!Array.isArray(nodes)||nodes.length>2048||new Set(nodes).size!==nodes.length||nodes.some(n=>!Number.isInteger(n)||!known.has(n)))throw Error('Unknown or duplicate Daevanion nodes.');
      out.build.daevanion_nodes=nodes.slice();
      if(value.reference!=null){if(!object(value.reference)||bytes(value.reference)>MAX)throw Error('Reference is too large or invalid.');out.reference=copy(value.reference);}
      if(object(value.source))out.source={log:String(value.source.log||'').slice(0,16),actor:String(value.source.actor||'').slice(0,80),basis:String(value.source.basis||'').slice(0,200)};
      if(value.loadout!=null){if(!object(value.loadout)||!Array.isArray(value.loadout.components)||value.loadout.components.length>64||value.loadout.components.some(c=>!object(c)||!object(c.stats))||bytes(value.loadout)>128*1024)throw Error('Equipment input must contain at most 64 components / 128 KiB.');out.loadout=copy(value.loadout);}
      for(const key of ['genus','genus_mix'])if(value[key]!=null){if(!object(value[key])||bytes(value[key])>32768)throw Error('Invalid '+key+' input.');out[key]=copy(value[key]);}
      return out;
    }
    function levels(){
      const result={},selected=new Set(draft.build.daevanion_nodes);
      for(const s of cls().skills)result[s.id]=s.kind==='stigma'?(draft.build.stigmas[s.id]||0):(draft.build.sp[s.id]||1)+(draft.build.bonus[s.id]||0);
      for(const b of cls().boards)for(const n of b.nodes)if(selected.has(n.id)&&n.skillId)result[n.skillId]=(result[n.skillId]||1)+(n.skillLevels||1);
      return result;
    }
    function assessment(){
      const errors=[],lv=levels(),selected=new Set(draft.build.daevanion_nodes),sp=cost(draft.build.sp,catalog.skill_cost),stigma=cost(draft.build.stigmas,catalog.stigma_cost),boardCosts={};
      if(sp>draft.budgets.skill)errors.push(`Skill cost ${sp} exceeds entered budget ${draft.budgets.skill}.`);
      if(stigma>draft.budgets.stigma)errors.push(`Stigma cost ${stigma} exceeds entered budget ${draft.budgets.stigma}.`);
      const row=cls().budget.filter(b=>b.level<=draft.level).at(-1)||{slots:0};
      if(Object.keys(draft.build.stigmas).length>row.slots)errors.push(`Equipped stigmas exceed the catalog's ${row.slots} slots at this level.`);
      for(const s of cls().skills){
        const trained=s.kind==='stigma'?(draft.build.stigmas[s.id]||0):(draft.build.sp[s.id]||1),need=s.kind==='stigma'?s.unlock:(s.need?.[trained-1]??s.unlock);
        if((trained>1||s.kind==='stigma'&&trained>0)&&draft.level<(need||1))errors.push(s.name+': character level gate not reached.');
        if(s.max&&lv[s.id]>s.max)errors.push(s.name+': effective level exceeds the catalog maximum.');
        if(s.kind==='active'){
          const choices=draft.build.specs[s.id]||[],slots=catalog.spec_slot_levels.filter(n=>lv[s.id]>=n).length;
          if(choices.length&&draft.level<(s.unlock||1))errors.push(s.name+': character level gate not reached.');
          if(choices.length>slots)errors.push(s.name+': too many supporting effects for the effective level.');
          if(choices.some(id=>s.specs.find(e=>e.id===id).unlock>lv[s.id]))errors.push(s.name+': selected supporting effect is locked.');
        }
      }
      for(const b of cls().boards){
        boardCosts[b.name]=b.nodes.filter(n=>selected.has(n.id)).reduce((sum,n)=>sum+(n.cost||0),0);
        const taken=b.nodes.filter(n=>selected.has(n.id));
        if(!taken.length)continue;
        if(draft.level<b.needLevel||taken.some(n=>draft.level<(n.needLevel||b.needLevel)))errors.push(b.name+': character level gate not reached.');
        const start=b.nodes.find(n=>n.type==='Start'),seen=new Set(start?[start.id]:[]),stack=start?[start]:[],positions=new Map(b.nodes.map(n=>[n.row+':'+n.col,n]));
        while(stack.length){const n=stack.pop();for(const [dr,dc] of [[1,0],[-1,0],[0,1],[0,-1]]){const next=positions.get((n.row+dr)+':'+(n.col+dc));if(next&&selected.has(next.id)&&!seen.has(next.id)){seen.add(next.id);stack.push(next);}}}
        if(taken.some(n=>!seen.has(n.id)))errors.push(b.name+': selected nodes must connect to the centre through selected nodes.');
        if(!catalog.crystal_boards.includes(b.name)&&boardCosts[b.name]>(draft.budgets.boards[b.name]||0))errors.push(b.name+': cost exceeds its separate entered board budget.');
      }
      const crystal=catalog.crystal_boards.reduce((sum,b)=>sum+(boardCosts[b]||0),0);
      if(crystal>draft.budgets.daevanion)errors.push(`Crystal board cost ${crystal} exceeds entered budget ${draft.budgets.daevanion}.`);
      return {errors,sp,stigma,crystal,boardCosts,levels:lv};
    }
    function saved(){try{const value=JSON.parse(localStorage.getItem(STORE)||'[]');return Array.isArray(value)?value.slice(0,10):[];}catch(_){return [];}}
    function pendingInputs(){return inputBuffer?.owner===draft&&['loadout','genus','genus_mix'].some(k=>inputBuffer[k]!==JSON.stringify(draft[k],null,2));}
    function download(){try{
      if(pendingInputs()){message('Apply edited equipment/Genus inputs before exporting.');return;}
      const result=assessment();if(result.errors.length){message('Export blocked: fix the catalog validation errors first.');return;}
      const doc=copy(draft);doc.catalog_revision=catalog.revision;doc.reference=reference;doc.source=source;
      const clean=normalize(doc);if(bytes(clean)>MAX){message('Build is too large to export (2 MiB limit).');return;}
      const url=URL.createObjectURL(new Blob([JSON.stringify(clean,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=(draft.name.replace(/[^a-z0-9_-]/gi,'_')||'build')+'.a2build.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('Build export requested. Check Downloads. Source stats were not recalculated.');
      }catch(e){message('Export failed: '+e.message);}
    }
    function save(){
      if(pendingInputs()){message('Apply edited equipment/Genus inputs before saving.');return;}
      try{const doc=normalize({...draft,reference,source}),rows=saved().filter(x=>x.id!==draft.local_id);if(rows.length>=10)throw Error('Ten local drafts are saved. Remove one before saving a new draft.');
        const id=draft.local_id||String(Date.now())+'-'+Math.random().toString(36).slice(2,8),entry={id,updated_at:Date.now(),draft:doc};rows.unshift(entry);
        if(bytes(rows)>MAX)throw Error('Saved drafts exceed 2 MiB. Export a build or remove an older draft.');localStorage.setItem(STORE,JSON.stringify(rows));draft.local_id=id;dirty=false;renderSaved();message(assessment().errors.length?'Draft saved locally with validation errors; export stays blocked.':'Draft saved in this browser.');
      }catch(e){message('Could not save draft: '+e.message);}
    }
    function renderSaved(){
      $('[data-saved]').innerHTML=saved().map(x=>`<div class="row"><button class="btn small" data-load="${esc(x.id)}">${esc(x.draft?.name||'Unnamed draft')}</button><small>${esc(new Date(x.updated_at).toLocaleString())}</small><button class="btn small" data-remove="${esc(x.id)}">Remove</button></div>`).join('')||'<p>No drafts saved in this browser.</p>';
      root.querySelectorAll('[data-load]').forEach(b=>b.onclick=()=>{try{if(dirty&&!confirm('Replace the unsaved draft with this saved draft?'))return;const entry=saved().find(x=>x.id===b.dataset.load);serial++;draft=normalize(entry.draft);draft.local_id=entry.id;reference=draft.reference;source=draft.source;dirty=false;render();message('Saved draft loaded.');}catch(e){message(e.message);}});
      root.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{try{localStorage.setItem(STORE,JSON.stringify(saved().filter(x=>x.id!==b.dataset.remove)));if(draft.local_id===b.dataset.remove)delete draft.local_id;renderSaved();message('Local saved draft removed. The open draft is retained.');}catch(e){message(e.message);}});
    }
    function render(){
      if(disposed||!root.isConnected)return;
      root.innerHTML=`<section class="win"><div class="wh"><h2>Build workspace</h2>${io.backURL?`<a class="btn small" href="${esc(io.backURL)}">← Back to log</a>`:''}</div><div class="wb"><p class="note">Plan a local allocation draft. Source character stats, equipment and optimizer scores remain read-only references. Explicit evaluation uses entered equipment/stat contributions and Genus lines with the existing damage model. It does not recalculate combat power, gear score or survivability.</p><div class="row"><label>Class <select data-class>${Object.keys(catalog.classes).map(c=>`<option ${c===draft.class?'selected':''}>${esc(c)}</option>`).join('')}</select></label><button class="btn small" data-new>New empty draft</button><label>Import profile / optimizer / draft JSON <input type="file" data-import accept=".json,.a2build"></label><button class="btn small" data-canonical>Load current community preset</button></div><div class="row"><label>Draft name <input data-name maxlength="120" value="${esc(draft.name)}"></label><label>Mode <select data-mode><option value="pve" ${draft.mode==='pve'?'selected':''}>PvE</option><option value="pvp" ${draft.mode==='pvp'?'selected':''}>PvP</option></select></label><label>Character level <input type="number" data-level min="1" max="45" value="${draft.level}"></label><button class="btn small" data-save>Save local draft</button><button class="btn small" data-export>Export build JSON</button></div><p data-message role="status" aria-live="polite"></p><details><summary>Saved local drafts</summary><p class="small muted">Up to ten drafts / 2 MiB in this browser. Saved references can contain character information. Nothing is uploaded automatically. Unsaved edits are not retained after leaving this page.</p><div data-saved></div></details><div class="tabs" role="group" aria-label="Build workspace view"><button data-tab="draft" class="${tab==='draft'?'on':''}">Allocation draft</button><button data-tab="inputs" class="${tab==='inputs'?'on':''}">Equipment, Genus &amp; evaluation</button><button data-tab="reference" class="${tab==='reference'?'on':''}">Character / source reference</button></div><div data-body></div></div></section>`;
      $('[data-name]').onchange=e=>{draft.name=e.target.value;serial++;$('[data-canonical]').disabled=false;dirty=true;};
      $('[data-mode]').onchange=e=>{serial++;draft.mode=e.target.value;serial++;$('[data-canonical]').disabled=false;dirty=true;body();message('Draft mode changed. No score was recalculated.');};
      $('[data-level]').onchange=e=>{const n=Number(e.target.value);if(!integer(n,1,45)){message('Choose an integer level from 1 to 45.');e.target.value=draft.level;return;}draft.level=n;serial++;$('[data-canonical]').disabled=false;dirty=true;body();};
      $('[data-class]').onchange=e=>{if(dirty&&!confirm('Replace unsaved allocations with an empty draft for this class?')){e.target.value=draft.class;return;}serial++;draft=fresh(e.target.value,draft.mode);reference=null;source={};serial++;$('[data-canonical]').disabled=false;dirty=true;boardName='';render();};
      $('[data-new]').onclick=()=>{if(dirty&&!confirm('Replace the unsaved draft with an empty draft?'))return;serial++;draft=fresh(draft.class,draft.mode,draft.level);reference=null;source={};serial++;$('[data-canonical]').disabled=false;dirty=true;render();};
      $('[data-import]').onchange=importFile;$('[data-canonical]').onclick=canonical;$('[data-save]').onclick=save;$('[data-export]').onclick=download;
      root.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render();});renderSaved();body();
    }
    function body(){
      if(tab==='inputs'){inputs();return;}
      if(tab==='reference'){
        const snapshot=reference?.snapshot,data=snapshot?.data;
        $('[data-body]').innerHTML=`<h3>Read-only source reference</h3><p class="note">${esc(source.basis||'No source attached.')} ${data?'Official profile totals do not identify trained points, missing bonus levels or selected supporting effects. They are not copied into the draft automatically.':''}</p>${snapshot?`<p>Status: ${esc(snapshot.status||'unavailable')} · ${esc(snapshot.reason||'')}<br>Upload: ${snapshot.uploaded_at?esc(new Date(snapshot.uploaded_at*1000).toLocaleString()):'Not recorded'} · Fetch: ${snapshot.fetched_at?esc(new Date(snapshot.fetched_at*1000).toLocaleString()):'Not recorded'}</p>`:''}${data&&window.A2CharacterView?A2CharacterView.details(data,snapshot.identity?.region||data.region):'<p>No official character snapshot is attached.</p>'}${reference?`<details><summary>Full reference JSON</summary><pre class="cr-profile-json">${esc(JSON.stringify(reference,null,2))}</pre></details>`:''}`;return;
      }
      const a=assessment(),cd=cls();if(!cd.boards.some(b=>b.name===boardName))boardName=cd.boards[0]?.name||'';
      $('[data-body]').innerHTML=`<p class="small muted">${esc(catalog.note)} Revision ${esc(catalog.revision.slice(0,12))}.${draft.catalog_revision!==catalog.revision?' Imported catalog revision differs; this draft is being checked against the bundled catalog.':''} Unentered bonus levels are assumed zero. PvE/PvP labels do not alter allocation rules or verify tactical performance.</p><div class="row">${['skill','stigma','daevanion'].map(k=>`<label>${esc(k==='daevanion'?'Crystal board':k)} budget <input type="number" min="0" max="10000" data-budget="${k}" value="${draft.budgets[k]}"></label>`).join('')}</div><p>Cost / entered budget: skill ${a.sp} / ${draft.budgets.skill} · stigma ${a.stigma} / ${draft.budgets.stigma} · crystal ${a.crystal} / ${draft.budgets.daevanion}. These totals are assumptions, not verified progression maxima.</p><div class="note" data-validation role="status">${a.errors.length?'<strong>Catalog validation errors</strong><ul>'+a.errors.map(e=>'<li>'+esc(e)+'</li>').join('')+'</ul>':'Allocation passes the listed catalog and entered-budget checks. Game legality, ownership and current-build applicability remain unverified.'}</div><h3>Skills, passives and stigmas</h3><label>Search skills <input data-search value="${esc(skillFilter)}"></label><div data-skills class="cr-profile-grid"></div><h3>Daevanion boards</h3><div class="tabs">${cd.boards.map(b=>`<button class="${b.name===boardName?'on':''}" data-board="${esc(b.name)}">${esc(b.name)} · cost ${a.boardCosts[b.name]||0}</button>`).join('')}</div><div data-board-body></div><label>Draft notes<textarea data-notes maxlength="4000" rows="3">${esc(draft.notes)}</textarea></label>`;
      root.querySelectorAll('[data-budget]').forEach(e=>e.onchange=()=>{const n=Number(e.value);if(e.value===''||!integer(n,0,10000)){message('Budget must be an integer from 0 to 10000.');e.value=draft.budgets[e.dataset.budget];return;}draft.budgets[e.dataset.budget]=n;serial++;$('[data-canonical]').disabled=false;dirty=true;body();});
      $('[data-search]').oninput=e=>{skillFilter=e.target.value;skills(a.levels);};
      $('[data-notes]').onchange=e=>{draft.notes=e.target.value;serial++;$('[data-canonical]').disabled=false;dirty=true;};
      root.querySelectorAll('[data-board]').forEach(b=>b.onclick=()=>{boardName=b.dataset.board;body();});skills(a.levels);board();
    }
    function inputs(){
      if(inputBuffer?.owner!==draft)inputBuffer={owner:draft,...Object.fromEntries(['loadout','genus','genus_mix'].map(k=>[k,JSON.stringify(draft[k],null,2)]))};
      const output=evaluation&&evaluation.serial===serial&&!pendingInputs()?evaluation.value:null;
      $('[data-body]').innerHTML=`<h3>Equipment and stat contributions</h3><p class="note">Edit modeled contributions by inventory slot. Percent stats use fractions (5% = 0.05). Do not enter final character totals that already include class base stats, Daevanion or passives; the model adds those separately. Bonus skill levels belong in Allocation draft, not equipment stats. Importing a supported optimizer build copies its frozen loadout when available and moves skill bonuses into the allocation. Source profiles remain unchanged.</p><div class="cr-profile-grid">${(draft.loadout.components||[]).map(c=>`<article class="cr-profile-card"><div><small>${esc(c.slot||'Entered component')}</small><strong>${esc(c.item||'Entered stats')}</strong><span>${esc(Object.keys(c.stats||{}).join(', ')||'No stat contributions')}</span></div></article>`).join('')||'<p>No equipment/stat loadout entered. Import an optimizer build or enter components below.</p>'}</div><label>Equipment/stat components JSON<textarea data-loadout rows="12">${esc(inputBuffer.loadout)}</textarea></label><p class="small muted">Example: {"components":[{"slot":"Weapon","item":"Entered weapon","stats":{"weapon_min":100,"weapon_max":150,"attack":25,"crit":100,"amp_pve":0.05}}]}. Supported stats follow the simulator Stats schema. Unknown/negative/non-finite values are rejected during evaluation; these limits are input safety bounds, not verified gear caps.</p><h3>Pet Genus Insight</h3><p class="small muted">Enter the five known genus names with level 0–10 and unlocked slot/stat/value lines. Values use the in-game text including %. Defensive and unsupported lines are retained but do not receive a damage coefficient. The official profile does not supply these allocations.</p><label>Genus lines JSON<textarea data-genus-input rows="8">${esc(inputBuffer.genus)}</textarea></label><p class="small muted">Example: {"Cogni":{"level":4,"lines":[{"slot":4,"stat":"Cogni Damage Boost","value":"3.6%"}]}}.</p><label>Assumed PvE enemy mix JSON<textarea data-genus-mix rows="3">${esc(inputBuffer.genus_mix)}</textarea></label><p class="small muted">Nonnegative relative weights across Cogni, Fera, Natura, Varian and Special; at least one positive. Not used for player targets.</p><div class="row"><button class="btn small" data-input-apply>Apply inputs to this draft</button><button class="btn primary" data-evaluate ${evaluating?'disabled':''}>${evaluating?'Evaluating…':'Evaluate this draft'}</button></div><p class="small muted">Apply edited JSON before evaluation or saving/exporting the draft. Evaluation sends only allocation, entered budgets, equipment/stat contributions and Genus inputs to ${io.localEvaluation?'this desktop app':'the configured community server'}; character references, names and private log links are excluded. Nothing is published or added to rankings. Default class priority is used; allocations and rotation are not optimized.</p><div data-evaluation role="status">${output?`<h3>Edited draft evaluation</h3><p>Evaluator ${esc(output.evaluator)} · input ${esc(output.input_sha256?.slice(0,16))}</p><div class="row">${Object.entries(output.scenarios||{}).map(([name,r])=>`<div class="note"><strong>${esc(name)}: ${Number(r.dps).toLocaleString(undefined,{maximumFractionDigits:1})} modeled DPS</strong></div>`).join('')}</div><p class="small muted">${esc(output.note)}</p><details><summary>Evaluation detail</summary><pre class="cr-profile-json">${esc(JSON.stringify(output,null,2))}</pre></details>`:evaluation?'<p>Draft changed since its evaluation. Apply inputs and evaluate again.</p>':'<p>No evaluation for this draft.</p>'}</div>`;
      for(const [selector,key] of [['[data-loadout]','loadout'],['[data-genus-input]','genus'],['[data-genus-mix]','genus_mix']])$(selector).oninput=e=>{inputBuffer[key]=e.target.value;dirty=true;$('[data-evaluation]').textContent='Input edits have not been applied or evaluated.';};
      $('[data-input-apply]').onclick=()=>{try{const loadout=JSON.parse($('[data-loadout]').value),genus=JSON.parse($('[data-genus-input]').value),genus_mix=JSON.parse($('[data-genus-mix]').value);const localId=draft.local_id;draft=normalize({...draft,loadout,genus,genus_mix});if(localId)draft.local_id=localId;inputBuffer=null;serial++;dirty=true;evaluation=null;inputs();message('Equipment/Genus inputs applied to the local draft. Save or evaluate explicitly.');}catch(e){message('Inputs not applied: '+e.message);}};
      $('[data-evaluate]').onclick=async()=>{
        if($('[data-loadout]').value!==JSON.stringify(draft.loadout,null,2)||$('[data-genus-input]').value!==JSON.stringify(draft.genus,null,2)||$('[data-genus-mix]').value!==JSON.stringify(draft.genus_mix,null,2)){message('Apply edited inputs before evaluating.');return;}
        if(assessment().errors.length){message('Fix allocation validation errors before evaluating.');return;}
        const current=serial;const request={format:draft.format,version:draft.version,class:draft.class,mode:draft.mode,level:draft.level,build:copy(draft.build),budgets:copy(draft.budgets),loadout:copy(draft.loadout),genus:copy(draft.genus),genus_mix:copy(draft.genus_mix)};
        if(bytes(request)>128*1024){message('Evaluation input exceeds 128 KiB. Reduce equipment/Genus input.');return;}
        evaluating=true;inputs();message('Evaluating entered allocation and loadout…');
        try{if(!io.evaluate)throw Error('Evaluation is unavailable on this host.');const result=await io.evaluate(request);if(current!==serial||disposed)return;evaluation={serial,value:result};message('Evaluation complete. Results are below; source character stats and rankings are unchanged.');}
        catch(e){if(current===serial&&!disposed)message('Evaluation failed: '+e.message);}
        finally{evaluating=false;if(!disposed&&root.isConnected&&tab==='inputs')inputs();}
      };
    }
    function icon(s){const url=String(s.icon||'');return /^https:\/\/metabot\.gg\/web\/aion2\//.test(url)?`<img src="${esc(window.A2AssetHealth?A2AssetHealth.source(url):url)}" alt="" loading="lazy" onerror="this.hidden=true">`:'<span class="cr-profile-empty">◇</span>';}
    function skills(lv){
      const list=cls().skills.filter(s=>['active','passive','stigma'].includes(s.kind)&&s.name.toLocaleLowerCase().includes(skillFilter.toLocaleLowerCase()));
      $('[data-skills]').innerHTML=list.map(s=>{
        const stigma=s.kind==='stigma',trained=stigma?(draft.build.stigmas[s.id]||0):(draft.build.sp[s.id]||1),cap=stigma?20:Math.min(10,s.buyMax||10),slots=catalog.spec_slot_levels.filter(n=>lv[s.id]>=n).length;
        return `<article class="bw-skill"><div class="cr-profile-card">${icon(s)}<div><small>${esc(s.kind)}</small><strong>${esc(s.name)}</strong><span>Effective level ${lv[s.id]||0}${stigma?' · equipped only above zero':' · '+slots+' supporting slots'}</span></div></div><div class="row"><label>${stigma?'Equipped level':'Trained level'} <select data-trained="${s.id}" data-kind="${s.kind}">${Array.from({length:cap+(stigma?1:0)},(_,i)=>i+(stigma?0:1)).map(n=>`<option value="${n}" ${n===trained?'selected':''}>${n}</option>`).join('')}</select></label>${!stigma?`<label>Bonus levels <input type="number" data-bonus="${s.id}" min="0" max="30" value="${draft.build.bonus[s.id]||0}"></label>`:''}</div>${s.specs.length?`<div class="bw-effects">${s.specs.map((e,i)=>`<label><input type="checkbox" data-effect="${e.id}" data-skill="${s.id}" ${(stigma?trained>=e.unlock:(draft.build.specs[s.id]||[]).includes(e.id))?'checked':''} ${stigma?'disabled':''}>${i+1} · ${esc(e.text)} <small>(effect Lv ${e.unlock}${lv[s.id]<e.unlock?' · locked':''}${stigma?' · automatic':''})</small></label>`).join('')}</div>`:''}</article>`;
      }).join('')||'<p>No skills match this search.</p>';
      root.querySelectorAll('[data-trained]').forEach(e=>e.onchange=()=>{const field=e.dataset.kind==='stigma'?'stigmas':'sp',n=Number(e.value);if(n===0)delete draft.build[field][e.dataset.trained];else draft.build[field][e.dataset.trained]=n;serial++;$('[data-canonical]').disabled=false;dirty=true;body();});
      root.querySelectorAll('[data-bonus]').forEach(e=>e.onchange=()=>{const n=Number(e.value);if(e.value===''||!integer(n,0,30)){message('Bonus level must be an integer from 0 to 30.');e.value=draft.build.bonus[e.dataset.bonus]||0;return;}draft.build.bonus[e.dataset.bonus]=n;serial++;$('[data-canonical]').disabled=false;dirty=true;body();});
      root.querySelectorAll('[data-effect]').forEach(e=>e.onchange=()=>{const id=Number(e.dataset.effect),key=e.dataset.skill,chosen=draft.build.specs[key]||[];draft.build.specs[key]=e.checked?[...chosen,id]:chosen.filter(n=>n!==id);serial++;$('[data-canonical]').disabled=false;dirty=true;body();});
    }
    function board(){
      const b=cls().boards.find(b=>b.name===boardName);if(!b)return;
      const selected=new Set(draft.build.daevanion_nodes),rows=b.nodes.map(n=>n.row),cols=b.nodes.map(n=>n.col),minRow=Math.min(...rows),minCol=Math.min(...cols),width=Math.max(...cols)-minCol+1;
      const colors={Unique:'var(--g-unique)',Legend:'var(--g-legend)',Epic:'var(--g-epic)',Rare:'var(--g-rare)'};
      $('[data-board-body]').innerHTML=`<p>${esc(b.name)} · opens at character Lv ${b.needLevel}. Select adjacent paths from the centre. Node icons identify the skill ranked up; hover or focus for node details.</p>${!catalog.crystal_boards.includes(b.name)?`<label>Separate ${esc(b.name)} cost budget <input data-board-budget type="number" min="0" max="10000" value="${draft.budgets.boards[b.name]||0}"></label>`:''}<div class="bw-board-scroll"><div class="bw-board" style="grid-template-columns:repeat(${width},48px)">${b.nodes.map(n=>{const s=cls().skills.find(s=>s.id===n.skillId),start=n.type==='Start',taken=selected.has(n.id),locked=draft.level<(n.needLevel||b.needLevel);return `<button type="button" class="bw-node ${taken||start?'selected':''}" data-node="${n.id}" aria-pressed="${taken||start}" ${start?'disabled':''} style="grid-row:${n.row-minRow+1};grid-column:${n.col-minCol+1};border-color:${colors[n.grade]||'var(--line)'}" title="${esc((n.label||n.type)+' · '+(s?s.name+' +'+(n.skillLevels||1)+' · ':'')+'cost '+(n.cost||0)+(locked?' · level locked':'')+' · '+(n.stats||[]).map(x=>x.stat+' '+x.value).join(', '))}">${s?icon(s):esc(n.short||String(n.type||'').slice(0,2))}<small>${start?'★':taken?'✓':n.cost||0}</small></button>`;}).join('')}</div></div>`;
      root.querySelectorAll('[data-node]').forEach(e=>e.onclick=()=>{const id=Number(e.dataset.node);draft.build.daevanion_nodes=selected.has(id)?draft.build.daevanion_nodes.filter(n=>n!==id):[...draft.build.daevanion_nodes,id];serial++;$('[data-canonical]').disabled=false;dirty=true;body();root.querySelector('[data-node="'+id+'"]')?.focus();});
      const budget=$('[data-board-budget]');if(budget)budget.onchange=()=>{const n=Number(budget.value);if(budget.value===''||!integer(n,0,10000)){message('Board budget must be an integer from 0 to 10000.');return;}draft.budgets.boards[b.name]=n;serial++;$('[data-canonical]').disabled=false;dirty=true;body();};
    }
    function fromSummary(summary){
      if(!object(summary)||!catalog.classes[summary.class]||!object(summary.build))throw Error('Unsupported optimizer summary.');
      const out=fresh(summary.class,String(summary.scenario||'').startsWith('pvp')?'pvp':'pve',summary.level||45),cd=catalog.classes[out.class],byName=new Map(cd.skills.map(s=>[s.name,s]));
      for(const field of ['sp','stigmas'])for(const [name,n] of Object.entries(summary.build[field]||{})){const s=byName.get(name);if(!s)throw Error('Unknown imported skill '+name);out.build[field][s.id]=n;}
      for(const [name,texts] of Object.entries(summary.build.specs||{})){const s=byName.get(name);if(!s||!Array.isArray(texts)||(texts.length&&s.kind!=='active'))throw Error('Unknown imported specialties.');if(!texts.length)continue;out.build.specs[s.id]=texts.map(text=>{const e=s.specs.find(e=>e.text===text);if(!e)throw Error('Unknown specialty for '+name);return e.id;});}
      out.build.daevanion_nodes=summary.build.daevanion_nodes||[];
      for(const key of ['skill','stigma','daevanion'])if(integer(summary.budgets?.[key],0,10000))out.budgets[key]=summary.budgets[key];
      // Effective levels contain gear bonuses in supported exports. Preserve their assumption explicitly.
      const additions={};for(const b of cd.boards)for(const n of b.nodes)if(out.build.daevanion_nodes.includes(n.id)&&n.skillId)additions[n.skillId]=(additions[n.skillId]||0)+(n.skillLevels||1);
      for(const [name,n] of Object.entries(summary.build.effective_levels||{})){const s=byName.get(name);if(!s||s.kind==='stigma')continue;const extra=n-(out.build.sp[s.id]||1)-(additions[s.id]||0);if(!integer(extra,0,30))throw Error('Effective level cannot be decomposed for '+name);out.build.bonus[s.id]=extra;}
      if(object(summary.loadout_snapshot)){out.loadout=copy(summary.loadout_snapshot);out.loadout.components=(out.loadout.components||[]).filter(c=>c.source!=='manual-genus-insight').map(c=>{c=copy(c);if(c.stats)delete c.stats.skill_bonus;return c;});}
      if(object(summary.genus?.state))out.genus=copy(summary.genus.state);
      if(object(summary.genus?.mix)&&Object.keys(summary.genus.mix).length)out.genus_mix=copy(summary.genus.mix);
      out.reference={optimizer:{class:summary.class,scenario:summary.scenario,dps:summary.dps,stats:summary.stats,genus:summary.genus,progression:summary.progression}};
      out.source={basis:'Imported optimizer allocation. Bonus levels are reconstructed from exported effective levels; original stats/scores are reference only.'};
      return normalize(out);
    }
    async function importFile(e){
      const file=e.target.files[0];if(!file)return;const request=++serial;
      try{if(file.size>MAX)throw Error('Choose JSON no larger than 2 MiB.');const value=JSON.parse(await file.text());if(request!==serial||disposed||!root.isConnected)return;if(dirty&&!confirm('Replace the unsaved draft with this import?'))return;
        let next;
        if(value.format==='a2build')next=normalize(value);
        else if(value.class&&value.build)next=fromSummary(value);
        else if(object(value.data?.profile)||object(value.profile)){next=fresh(draft.class,draft.mode);next.reference={snapshot:object(value.data?.profile)?value:{status:'imported',data:value}};next.source={basis:'Imported profile reference; allocations are not inferred from total skill levels.'};next=normalize(next);tab='reference';}
        else throw Error('Choose an a2build draft, optimizer build.json or exported official profile JSON.');
        serial++;draft=next;reference=next.reference;source=next.source;serial++;$('[data-canonical]').disabled=false;dirty=true;render();message('Import loaded. Check the reference and catalog validation before exporting.');
      }catch(err){message('Import failed: '+err.message);}
    }
    async function canonical(){
      if(dirty&&!confirm('Replace the unsaved allocation with the current community preset?'))return;
      const request=++serial,requestedClass=draft.class,mode=draft.mode;$('[data-canonical]').disabled=true;message('Loading server-evaluated community preset…');
      try{if(!io.api)throw Error('Community server unavailable');const result=await io.api('/api/v2/presets/'+requestedClass+'/'+mode);if(request!==serial||disposed||!root.isConnected)return;draft=fromSummary(result.build);reference=draft.reference;source=draft.source;serial++;$('[data-canonical]').disabled=false;dirty=true;render();message('Community preset copied into a local draft. Its original score is reference only; edits are not scored.');}
      catch(e){if(request===serial)message('Could not load preset: '+e.message);}
      finally{if(request===serial&&!disposed&&root.isConnected)$('[data-canonical]').disabled=false;}
    }
    async function load(){
      root.textContent='Loading build catalog…';try{const response=await fetch(io.catalogURL||'/static/build-catalog.json');if(!response.ok)throw Error('Build catalog unavailable');catalog=await response.json();if(disposed||!root.isConnected)return;if(catalog.version!==1)throw Error('Unsupported catalog');
        const initial=io.className&&catalog.classes[io.className]?io.className:Object.keys(catalog.classes)[0];draft=fresh(initial,io.mode==='pvp'?'pvp':'pve',integer(io.level,1,45)?io.level:45);render();
      }catch(e){if(!disposed&&root.isConnected)root.textContent='Could not open build workspace: '+e.message;}
    }
    load();return {dispose:()=>{disposed=true;serial++;}};
  }
  window.A2BuildWorkspace={mount};
})();
