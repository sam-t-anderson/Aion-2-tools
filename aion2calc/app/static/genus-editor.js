/* Manual genus allocations: preserve the draft across all five tabs. */
(function(){
  'use strict';
  const genera=['Cogni','Fera','Natura','Varian','Special'];
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function ringHTML(genus,group){
    const known=group && Number.isInteger(group.level),level=known?group.level:null,lines=Array.isArray(group?.lines)?group.lines:[];
    const nodes=Array.from({length:9},(_,i)=>{
      const slot=i+1,angle=(-90+i*40)*Math.PI/180,x=160+124*Math.cos(angle),y=160+124*Math.sin(angle),line=lines.find(l=>l?.slot===slot);
      const locked=known && slot>level,status=locked?'Locked · opens at Lv '+slot:line?line.stat+' '+line.value:'Not recorded';
      return `<g class="genus-node ${locked?'locked':line?'filled':'unknown'}" tabindex="0" role="img" aria-label="${esc('Slot '+slot+': '+status)}"><title>${esc('Slot '+slot+': '+status)}</title><circle cx="${x}" cy="${y}" r="18"/><text x="${x}" y="${y+5}" text-anchor="middle">${slot}</text></g>`;
    }).join('');
    return `<svg class="genus-ring" viewBox="0 0 320 320" role="img" aria-label="${esc(genus)} Insight: nine analysis slots"><circle class="genus-ring-track" cx="160" cy="160" r="124"/><circle class="genus-ring-center" cx="160" cy="160" r="87"/><circle class="genus-ring-inner" cx="160" cy="160" r="78"/><text class="genus-ring-sigil" x="160" y="145" text-anchor="middle">${esc(genus==='Special'?'✦':genus.slice(0,1))}</text><text class="genus-ring-name" x="160" y="178" text-anchor="middle">${esc(genus)} Insight</text><text class="genus-ring-level" x="160" y="202" text-anchor="middle">${known?'Lv '+esc(level)+(level===10?' · MAX':''):'Level not recorded'}</text>${nodes}</svg>`;
  }
  function mount(root,initial,save){
    let dirty=false;
    let state=JSON.parse(JSON.stringify(initial||{})),selected=genera[0],busy=false,message='',jsonDraft=null,repair=false;
    if(!state||typeof state!=='object'||Array.isArray(state)){jsonDraft=JSON.stringify(state,null,2);state={};repair=true;message='Older genus data needs repair in Advanced JSON.';}
    const current=()=>{if(!state[selected]||typeof state[selected]!=='object'||Array.isArray(state[selected]))state[selected]={level:0,lines:[]};return state[selected];};
    const entries=()=>Array.isArray(current().lines)?current().lines:[];
    const update=(slot,field,value)=>{dirty=true;const item=current();if(!Array.isArray(item.lines))item.lines=[];let row=item.lines.find(x=>x&&x.slot===slot);if(!row){row={slot,stat:'',value:''};item.lines.push(row);}row[field]=value;jsonDraft=null;const textarea=root.querySelector("[data-genus-json]");if(textarea)textarea.value=JSON.stringify(state,null,2);const ring=root.querySelector('.genus-editor-preview svg');if(ring)ring.outerHTML=ringHTML(selected,item);};
    function render(){
      if(!root.isConnected)return;
      const group=state[selected],validGroup=!group||(typeof group==='object'&&!Array.isArray(group)&&(!Object.hasOwn(group,'lines')||Array.isArray(group.lines)));
      const item=state[selected]||{level:0,lines:[]},rows=Array.isArray(item.lines)?item.lines:[],level=Number(item.level)||0;
      const unusual=Object.keys(state).some(k=>!genera.includes(k))||genera.some(g=>{const x=state[g];return x&&(typeof x!=='object'||Array.isArray(x)||(Object.hasOwn(x,'lines')&&!Array.isArray(x.lines))||(Array.isArray(x.lines)&&x.lines.some(l=>!l||!Number.isInteger(l.slot)||l.slot<1||l.slot>9)));});
      root.innerHTML=`<p class="small muted">Enter your in-game Pet Genus Insight levels and analysis lines. The official profile does not provide these allocations. Changes apply to advice and PvE/PvP character optimization after saving and recalculating.</p>
        <div class="tabs" role="group" aria-label="Pet genera">${genera.map(g=>`<button type="button" aria-pressed="${g===selected}" data-genus-tab="${g}" class="${g===selected?'on':''}" ${busy?'disabled':''}>${g} · ${Number.isInteger(state[g]?.level)?'Lv '+esc(state[g].level):'Not recorded'}</button>`).join('')}</div>
        <div class="row"><h4>${esc(selected)} Insight</h4><label>Insight level <input data-genus-level type="number" min="0" max="10" step="1" value="${esc(group?.level??'')}" placeholder="Not recorded" ${busy||repair||!validGroup?'disabled':''}></label><span class="small muted">Nine analysis slots · level 10 changes grade chances</span></div>
        ${unusual?'<p class="note">Some saved entries need review. They are retained in Advanced JSON; correct their genus/slot before saving.</p>':''}
        <div class="genus-editor-layout"><div class="genus-editor-preview">${ringHTML(selected,group)}<p class="small muted">Gold: saved line · gray: not recorded · dim: locked. Colors indicate recording status, not in-game rarity.</p></div><div class="genus-editor-grid">${Array.from({length:9},(_,i)=>{const slot=i+1,row=rows.find(x=>x&&x.slot===slot)||{},unknown=!Number.isInteger(group?.level),locked=unknown||slot>level;return `<section class="gslot ${slot===4||slot===7?'sp':''} ${locked?'locked':''}"><b>Slot ${slot}</b><span class="small muted">${unknown?'Enter the Insight level first':locked?'Opens at level '+slot:slot===4||slot===7?'Genus damage-line slot':'Analysis line'}</span><label>Stat <input data-genus-slot="${slot}" data-genus-field="stat" type="text" maxlength="100" value="${esc(row.stat||'')}" placeholder="${esc(selected)} Damage Boost" ${locked||busy||repair||!validGroup?'disabled':''}></label><label>Value <input data-genus-slot="${slot}" data-genus-field="value" type="text" maxlength="40" value="${esc(row.value??'')}" placeholder="3.6%" ${locked||busy||repair||!validGroup?'disabled':''}></label><button type="button" class="btn small" data-genus-clear="${slot}" ${busy||!rows.some(x=>x&&x.slot===slot)?'disabled':''}>Clear slot</button></section>`;}).join('')}</div>
        </div><p class="small muted">Copy numeric values exactly, including % when shown. Defensive lines are retained, but the current advice model scores damage effects only. Clear occupied slots before lowering the Insight level. Leave a level blank when unrecorded; 0 means you explicitly recorded level 0.</p>
        <details><summary>Advanced JSON / repair older entries</summary><p class="small muted">Apply JSON before changing genus tabs. Nothing is saved until Save genus lines succeeds.</p><textarea data-genus-json rows="8">${esc(jsonDraft??JSON.stringify(state,null,2))}</textarea><button type="button" class="btn small" data-genus-apply ${busy?'disabled':''}>Apply JSON to draft</button></details>
        <div class="row"><button type="button" class="btn primary" data-genus-save ${busy?'disabled':''}>${busy?'Saving…':'Save genus lines'}</button><span role="status" aria-live="polite">${esc(message)}</span></div>`;
      root.querySelectorAll('[data-genus-tab]').forEach(button=>button.onclick=()=>{selected=button.dataset.genusTab;message='';render();});
      root.querySelector('[data-genus-level]').onchange=e=>{if(e.target.value===''){if(entries().length){message='Clear saved lines before removing the recorded level.';render();return;}delete state[selected];}else{const value=Number(e.target.value);if(!Number.isInteger(value)||value<0||value>10){message='Use a whole level from 0 to 10.';render();return;}current().level=value;}dirty=true;jsonDraft=null;render();};
      root.querySelectorAll('[data-genus-field]').forEach(input=>input.oninput=()=>update(Number(input.dataset.genusSlot),input.dataset.genusField,input.value));
      root.querySelectorAll('[data-genus-clear]').forEach(button=>button.onclick=()=>{dirty=true;current().lines=entries().filter(x=>!x||x.slot!==Number(button.dataset.genusClear));jsonDraft=null;render();});
      root.querySelector('[data-genus-json]').oninput=e=>{dirty=true;jsonDraft=e.target.value;};
      root.querySelector('[data-genus-apply]').onclick=()=>{try{const next=JSON.parse(jsonDraft??root.querySelector('[data-genus-json]').value);if(!next||typeof next!=='object'||Array.isArray(next))throw Error('Use an object keyed by genus.');dirty=true;state=next;repair=false;jsonDraft=null;message='Draft applied. Review and save.';render();}catch(e){message='JSON could not be applied: '+e.message;render();}};
      root.querySelector('[data-genus-save]').onclick=async()=>{if(jsonDraft!==null){message='Apply the edited JSON before saving.';render();return;}busy=true;message='Saving genus lines…';render();try{const result=await save(state);state=JSON.parse(JSON.stringify(result));dirty=false;message='Genus lines saved. Optimize or run advice again to recalculate.';}catch(e){message='Not saved: '+e.message;}finally{busy=false;render();}};
    }
    render();
    return {isDirty:()=>dirty||busy||repair||jsonDraft!==null};
  }
  window.A2GenusEditor={mount,ringHTML};
})();
