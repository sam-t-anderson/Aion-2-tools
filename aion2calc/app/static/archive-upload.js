/* Numbered parts stay independent reports; this queue never stitches effects. */
(function () {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeLink = x => {try {const u=new URL(x);return ['https:','http:'].includes(u.protocol)?u.href:'';} catch (_) {return '';}};
  const archiveMeta = a => a && typeof a.id==='string' && Number.isSafeInteger(a.part) && a.part>0 ? {id:a.id.slice(0,100),part:a.part,closed:a.closed===true}:undefined;
  const exportedLink = x => {try {const u=new URL(safeLink(x));return !u.search && !u.hash?u.href:undefined;}catch(_){return undefined;}};
  function mount(root, io) {
    let rows=[], offset=0, more=false, busy=false, cancel=false, message='', filter='', type='', chosenVisibility='unlisted', batch=null;
    const selected=new Map(), results=new Map();
    const label=r=>r.title || r.file;
    function download() {
      const manifest={format:'a2log-upload-manifest',version:1,server:batch?.url,visibility:batch?.visibility,
        parts:[...selected.values()].map(r=>{const s=results.get(r.file)||{};return {file:r.input?.name||r.file,archive:archiveMeta(r.archive),
          status:s.status||'pending',id:s.id,error:s.error,
          ...(s.status==='uploaded' && s.visibility!=='private'?{url:exportedLink(s.url)}:{})};})};
      const url=URL.createObjectURL(new Blob([JSON.stringify(manifest,null,2)],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download='combat-upload-manifest.json';a.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    async function load(next) {
      busy=true;render();
      try {const page=await io.list(next,25);rows=page.rows;offset=next;more=page.has_more;}
      catch(e){message=e.message;}
      finally {busy=false;render();}
    }
    async function run() {
      if(busy || !selected.size)return;
      const visibility=root.querySelector('[data-visibility]').value;
      busy=true;cancel=false;render();
      try {
        const config=await io.context();
        if(!config.url)throw Error('Set an upload server first.');
        if(batch && (batch.url!==config.url || batch.visibility!==visibility))throw Error('Server or visibility changed. Clear the queue before starting a different batch.');
        batch={...config,visibility};
        let halted=false;
        for(const row of selected.values()) {
          if(cancel || !root.isConnected)break;
          if(results.get(row.file)?.status==='uploaded')continue;
          results.set(row.file,{status:'uploading'});message='Uploading '+label(row)+'…';render();
          try {
            const response=await io.upload(row,batch);
            results.set(row.file,{status:'uploaded',id:response.id,url:response.url,visibility:response.visibility||batch.visibility,
              warning:response.ownership_warning});
            document.dispatchEvent(new Event('a2log-uploaded'));
          } catch(e) {
            results.set(row.file,{status:'failed',error:e.message});
            if(e instanceof TypeError || /\b(401|403|429)\b|server changed|failed to fetch|timed out|aborted/i.test(e.message)){halted=true;break;}
          }
          render();
        }
        const done=[...selected.keys()].filter(file=>results.get(file)?.status==='uploaded').length;
        message=`${done} / ${selected.size} uploaded. ${cancel?'Cancelled between uploads. ':''}${halted?'Stopped after a connection, authentication or rate-limit error; remaining files are pending. ':''}Successful parts are skipped on retry in this queue.`;
      } catch(e) {message=e.message;}
      finally {busy=false;render();}
    }
    function render() {
      if(!root.isConnected)return;
      const visible=rows.filter(r=>(!type || r.contexts?.some(c=>c.encounter_type===type)) && (!filter || [label(r),r.archive?.id,r.archive?.part,
        ...(r.contexts||[]).map(c=>c.encounter_type)].join(' ').toLowerCase().includes(filter.toLowerCase())));
      const disabled=busy?'disabled':'';
      root.innerHTML=`<section class="note"><h3>Saved parts · review and batch upload</h3>
        <p class="small muted">Each selected file becomes a separate report. Active/unfinished checkpoints are excluded from the queue. Up to 100 files per queue. Navigating away stops before the next upload; the in-flight request can finish.</p>
        ${io.files?'<label>Add saved a2log JSON files <input data-files type="file" accept=".json" multiple '+disabled+'></label>':''}
        <div class="row"><label>Filter this page <input data-filter value="${esc(filter)}" placeholder="Archive ID, name or encounter type" ${disabled}></label>
        <label>Encounter type <select data-type ${disabled}><option value="">All</option>${Object.entries(io.types||{}).map(([v,l])=>`<option value="${esc(v)}" ${v===type?'selected':''}>${esc(l)}</option>`).join('')}</select></label>
        <button class="btn small" data-select ${disabled}>Select eligible rows on this page</button>
        ${io.list?`<button class="btn small" data-prev ${busy||!offset?'disabled':''}>Newer</button><span>File slots ${offset+1}–${offset+25}</span><button class="btn small" data-next ${busy||!more?'disabled':''}>Older</button>`:''}</div>
        <div class="cr-scroll"><table class="t"><tr><th>Select</th><th>Session / archive part</th><th>Encounters</th><th>State</th><th></th></tr>
        ${visible.map((r,i)=>`<tr><td><input type="checkbox" data-pick="${i}" aria-label="Select ${esc(label(r))}" ${selected.has(r.file)?'checked':''} ${busy||r.unfinished?'disabled':''}></td>
        <td>${esc(label(r))}${r.archive?`<br><span class="small muted">${esc(r.archive.id)} · Part ${esc(r.archive.part)}</span>`:''}</td>
        <td>${r.segments??'—'}</td><td>${r.unfinished?'Unfinished checkpoint':'Saved file'}</td><td><button class="btn small" data-open="${i}" ${disabled}>Open</button></td></tr>`).join('')||'<tr><td colspan="5">No matching files on this page.</td></tr>'}</table></div>
        <div class="row"><span>${selected.size} selected</span><label>Visibility <select data-visibility ${disabled}>${['unlisted','public','private'].map(v=>`<option ${v===chosenVisibility?'selected':''}>${v}</option>`).join('')}</select></label>
        <button class="btn primary" data-upload ${busy||!selected.size?'disabled':''}>Upload selected / retry remaining</button>
        <button class="btn small" data-cancel ${!busy?'disabled':''}>Cancel after current upload</button>
        <button class="btn small" data-clear ${disabled}>Clear queue</button><button class="btn small" data-manifest ${busy||!results.size?'disabled':''}>Export upload results</button></div>
        <p class="small muted">Public uploads are listed; unlisted uploads can be viewed with their link; private uploads require a secret link. The results manifest can contain unlisted links, but excludes private links and ownership/upload keys. A failed network response can be ambiguous: retry may create a duplicate if the server already accepted it.</p>
        <div role="status" aria-live="polite">${esc(message)}</div>
        <ul>${[...selected.values()].map(r=>{const s=results.get(r.file);const link=safeLink(s?.url);return `<li>${esc(label(r))}: ${esc(s?.status||'pending')}${s?.error?' — '+esc(s.error):''}${s?.warning?' — '+esc(s.warning):''}${s?.status==='uploaded'&&link?` · <a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Open uploaded report</a>`:''}</li>`;}).join('')}</ul></section>`;
      const $=s=>root.querySelector(s);
      $('[data-filter]').onchange=e=>{filter=e.target.value;render();};
      $('[data-type]').onchange=e=>{type=e.target.value;render();};
      $('[data-visibility]').onchange=e=>{chosenVisibility=e.target.value;};
      const pick=r=>{if(selected.size>=100 && !selected.has(r.file))throw Error('Queue limit is 100 files. Upload/clear this queue before adding more.');selected.set(r.file,r);};
      root.querySelectorAll('[data-pick]').forEach(e=>e.onchange=()=>{try{const r=visible[+e.dataset.pick];if(e.checked)pick(r);else selected.delete(r.file);}catch(error){message=error.message;}render();});
      $('[data-select]').onclick=()=>{try{visible.filter(r=>!r.unfinished).forEach(pick);}catch(e){message=e.message;}render();};
      root.querySelectorAll('[data-open]').forEach(e=>e.onclick=async()=>{try{await io.open(visible[+e.dataset.open]);}catch(error){message=error.message;render();}});
      if(io.list){$('[data-prev]').onclick=()=>load(Math.max(0,offset-25));$('[data-next]').onclick=()=>load(offset+25);}
      if(io.files)$('[data-files]').onchange=async e=>{
        try {const files=[...e.target.files];if(rows.length+files.length>100)throw Error('Choose at most 100 files in this queue.');
          busy=true;message='Reading selected files locally…';render();
          for(const file of files){if(file.size>50*1024*1024)throw Error(file.name+': exceeds 50 MiB browser import limit.');
            const doc=JSON.parse(await file.text());if(doc.format!=='a2log'||doc.version!==1||!Array.isArray(doc.segments)||!Array.isArray(doc.players))throw Error(file.name+': choose an a2log v1 JSON file.');
            const id=file.name+':'+file.size+':'+file.lastModified;if(rows.some(r=>r.file===id))continue;rows.push({file:id,input:file,title:doc.meta?.title||file.name,archive:doc.meta?.archive,
              unfinished:!!doc.meta?.capture_active,segments:doc.segments.length,contexts:doc.segments.map(s=>({encounter_type:s.encounter_type||doc.meta?.encounter_type||'unknown'}))});}
          message='Files loaded locally. Select the parts to upload.';
        }catch(error){message=error.message;}finally{busy=false;render();}
      };
      $('[data-upload]').onclick=run;$('[data-cancel]').onclick=()=>{cancel=true;message='Cancellation requested; the in-flight upload can finish.';render();};
      $('[data-clear]').onclick=()=>{selected.clear();results.clear();batch=null;if(io.files)rows=[];message='Queue cleared; local files and server uploads remain.';render();};
      $('[data-manifest]').onclick=download;
    }
    render();if(io.list)load(0);
    return {cancel:()=>{cancel=true;}};
  }
  window.A2ArchiveUpload={mount};
})();
