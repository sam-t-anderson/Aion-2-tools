/* Numbered parts stay independent reports; this queue never stitches effects. */
(function () {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeLink = x => {try {const u=new URL(x);return ['https:','http:'].includes(u.protocol)?u.href:'';} catch (_) {return '';}};
  const archiveMeta = a => a && typeof a.id==='string' && Number.isSafeInteger(a.part) && a.part>0 ? {id:a.id.slice(0,100),part:a.part,closed:a.closed===true}:undefined;
  const exportedLink = x => {try {const u=new URL(safeLink(x));return !u.search && !u.hash?u.href:undefined;}catch(_){return undefined;}};
  const checkpointKey='a2log-upload-checkpoint-v1';
  function cleanCheckpoint(value){
    if(!value || value.format!=='a2log-upload-checkpoint' || value.version!==1 || !Array.isArray(value.parts) || value.parts.length>100 || JSON.stringify(value).length>256*1024)throw Error('Choose an upload recovery checkpoint with at most 100 files.');
    const server=String(value.server||'').replace(/\/+$/,'');
    if(server){const u=new URL(server);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash)throw Error('Invalid checkpoint server.');}
    const visibility=value.visibility||'unlisted';if(!['public','unlisted','private'].includes(visibility))throw Error('Invalid checkpoint visibility.');
    const seen=new Set(),parts=value.parts.map(r=>{
      if(!r || typeof r.file!=='string'||!r.file||r.file.length>1024||seen.has(r.file))throw Error('Invalid or duplicate checkpoint filename.');seen.add(r.file);
      if(r.fingerprint!=null && !/^[a-f0-9]{64}$/.test(r.fingerprint))throw Error('Invalid file fingerprint.');
      if(r.request_id!=null && !/^[a-f0-9]{32}$/.test(r.request_id))throw Error('Invalid upload request ID.');
      const status=r.status||'pending';if(!['pending','uploading','unknown','failed','uploaded'].includes(status))throw Error('Invalid checkpoint status.');
      if(r.id!=null && !/^[a-z0-9]{6,16}$/i.test(r.id))throw Error('Invalid uploaded report ID.');
      if(status==='uploaded' && (!server||!r.id||!r.fingerprint))throw Error('Successful records require a server, ID and fingerprint.');
      return {file:r.file,name:String(r.name||r.file).slice(0,1024),title:String(r.title||r.file).slice(0,200),fingerprint:r.fingerprint||null,request_id:r.request_id||null,status,id:r.id||null};
    });
    return {format:'a2log-upload-checkpoint',version:1,server,visibility,parts};
  }
  const browserFingerprint=async row=>{if(!row.input)throw Error('Reselect the original JSON files before resuming.');if(!crypto.subtle)throw Error('Secure file fingerprints require HTTPS or localhost.');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',await row.input.arrayBuffer()))].map(v=>v.toString(16).padStart(2,'0')).join('');};
  function mount(root, io) {
    let rows=[], offset=0, more=false, busy=false, cancel=false, message='', filter='', type='', chosenVisibility='unlisted', batch=null,retryUnknown=false,writes=Promise.resolve();
    const selected=new Map(), results=new Map();
    const label=r=>r.title || r.file;
    const checkpoint=()=>cleanCheckpoint({format:'a2log-upload-checkpoint',version:1,server:batch?.url||'',visibility:batch?.visibility||chosenVisibility,
      parts:[...selected.values()].map(r=>{const result=results.get(r.file)||{};return {file:r.file,name:r.input?.name||r.name||r.file,title:label(r),fingerprint:r.fingerprint,request_id:r.request_id,status:result.status||'pending',id:result.id};})});
    const saveCheckpoint=io.saveCheckpoint||(value=>localStorage.setItem(checkpointKey,JSON.stringify(value)));
    const loadCheckpoint=io.loadCheckpoint||(()=>JSON.parse(localStorage.getItem(checkpointKey)||'null'));
    const persist=()=>{const value=checkpoint();writes=writes.catch(()=>{}).then(()=>saveCheckpoint(value));return writes;};
    const remember=()=>persist().catch(e=>{message='Could not save recovery state: '+e.message;render();});
    function exportRecovery(){downloadJSON(checkpoint(),'combat-upload-recovery.json');}
    function downloadJSON(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    async function restore(value){
      if(selected.size)throw Error('Clear the current queue before restoring another.');
      if(!value || !value.parts?.length)throw Error('No saved upload queue is available.');
      const saved=cleanCheckpoint(value);batch=saved.server?{url:saved.server,visibility:saved.visibility}:null;chosenVisibility=saved.visibility;retryUnknown=false;
      for(const item of saved.parts){const row={file:item.file,name:item.name,title:item.title,fingerprint:item.fingerprint,request_id:item.request_id};selected.set(row.file,row);results.set(row.file,{status:item.status==='uploading'?'unknown':item.status,id:item.id,fingerprint:item.fingerprint});}
      if(io.files)rows=[...selected.values()];
      message='Queue restored. '+(io.files?'Reselect the original JSON files to verify their fingerprints. ':'Files are verified before skipping known successes. ')+'Interrupted requests remain uncertain; check My uploads before retrying them.';
      render();
    }
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
        await persist();
        let halted=false;
        for(const row of selected.values()) {
          if(cancel || !root.isConnected)break;
          const fingerprint=await (io.fingerprint||browserFingerprint)(row);
          if(row.fingerprint && row.fingerprint!==fingerprint)throw Error('File changed: '+label(row)+'. Clear the queue and review the new content before uploading.');
          row.fingerprint=fingerprint;
          if(results.get(row.file)?.status==='uploaded')continue;
          if(results.get(row.file)?.status==='unknown' && !retryUnknown)throw Error('Uncertain upload outcome for '+label(row)+'. Check My uploads, then explicitly allow retry if it was not received.');
          if(cancel || !root.isConnected)break;
          row.request_id ||= [...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
          results.set(row.file,{status:'uploading',fingerprint});message='Uploading '+label(row)+'…';render();
          await persist();
          if(cancel || !root.isConnected){results.set(row.file,{status:'pending',fingerprint});await persist();break;}
          try {
            const response=await io.upload(row,batch);
            results.set(row.file,{status:'uploaded',id:response.id,url:response.url,visibility:response.visibility||batch.visibility,
              warning:response.ownership_warning,fingerprint});
            document.dispatchEvent(new Event('a2log-uploaded'));
          } catch(e) {
            const known=/\b(400|401|403|409|410|413|429)\b|file changed|unfinished checkpoints/i.test(e.message);
            results.set(row.file,{status:known?'failed':'unknown',error:e.message,fingerprint});
            if(!known || e instanceof TypeError || /\b(401|403|409|410|429)\b|server changed|failed to fetch|timed out|aborted/i.test(e.message)){halted=true;}
          }
          await persist();
          if(halted)break;
          render();
        }
        const done=[...selected.keys()].filter(file=>results.get(file)?.status==='uploaded').length;
        message=`${done} / ${selected.size} uploaded. ${cancel?'Cancelled between uploads. ':''}${halted?'Stopped after a connection, authentication or rate-limit error; remaining files are pending. ':''}Known successful files are skipped only when their fingerprints match.`;
      } catch(e) {message=e.message;}
      finally {busy=false;render();}
    }
    function render() {
      if(!root.isConnected)return;
      const visible=rows.filter(r=>(!type || r.contexts?.some(c=>c.encounter_type===type)) && (!filter || [label(r),r.archive?.id,r.archive?.part,
        ...(r.contexts||[]).map(c=>c.encounter_type)].join(' ').toLowerCase().includes(filter.toLowerCase())));
      const disabled=busy?'disabled':'';
      root.innerHTML=`<section class="note"><h3>Saved parts · review and batch upload</h3>
        <p class="small muted">Each selected file becomes a separate report. Active/unfinished checkpoints are excluded from the queue. Up to 100 files per queue. Recovery metadata is saved locally without upload keys, private links or ownership credentials. Navigating away stops before the next upload; the in-flight request can finish.</p>
        ${io.files?'<label>Add saved a2log JSON files <input data-files type="file" accept=".json" multiple '+disabled+'></label>':''}
        <div class="row"><button class="btn small" data-restore ${busy||selected.size?'disabled':''}>Restore saved queue</button><label>Import recovery file <input type="file" data-recovery accept=".json" ${busy||selected.size?'disabled':''}></label><button class="btn small" data-export-recovery ${busy||!selected.size?'disabled':''}>Export recovery file</button></div>
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
        <label class="small"><input data-retry-unknown type="checkbox" ${retryUnknown?'checked':''} ${disabled}> I checked My uploads and want to retry uncertain requests (may duplicate an accepted upload).</label>
        <p class="small muted">Public uploads are listed; unlisted uploads can be viewed with their link; private uploads require a secret link. The results manifest can contain unlisted links, but excludes private links and ownership/upload keys. A failed network response can be ambiguous: interrupted requests are marked uncertain and require explicit retry. Updated servers reuse matching request IDs instead of creating duplicate reports. Older servers and legacy uncertain requests without a prior ID can still duplicate. Request IDs are not ownership credentials; retries do not reissue private links or management tokens.</p>
        <div role="status" aria-live="polite">${esc(message)}</div>
        <ul>${[...selected.values()].map(r=>{const s=results.get(r.file);const link=safeLink(s?.url);return `<li><button class="btn small" data-remove="${esc(r.file)}" ${disabled}>Remove</button> ${esc(label(r))}: ${esc(s?.status||'pending')}${s?.error?' — '+esc(s.error):''}${s?.warning?' — '+esc(s.warning):''}${s?.status==='uploaded'&&link?` · <a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Open uploaded report</a>`:''}</li>`;}).join('')}</ul></section>`;
      const $=s=>root.querySelector(s);
      root.querySelectorAll('[data-remove]').forEach(button=>button.onclick=()=>{selected.delete(button.dataset.remove);remember();render();});
      $('[data-filter]').onchange=e=>{filter=e.target.value;render();};
      $('[data-type]').onchange=e=>{type=e.target.value;render();};
      $('[data-visibility]').onchange=e=>{chosenVisibility=e.target.value;remember();};
      $('[data-retry-unknown]').onchange=e=>{retryUnknown=e.target.checked;};
      $('[data-restore]').onclick=async()=>{busy=true;render();try{await writes;await restore(await loadCheckpoint());}catch(e){message=e.message;}finally{busy=false;render();}};
      $('[data-recovery]').onchange=async e=>{const file=e.target.files[0];if(!file)return;busy=true;render();try{if(file.size>256*1024)throw Error('Recovery file exceeds 256 KiB.');await restore(JSON.parse(await file.text()));await persist();}catch(error){message=error.message;}finally{busy=false;render();}};
      $('[data-export-recovery]').onclick=exportRecovery;
      const pick=r=>{if(selected.size>=100 && !selected.has(r.file))throw Error('Queue limit is 100 files. Upload/clear this queue before adding more.');r.fingerprint ||= selected.get(r.file)?.fingerprint || results.get(r.file)?.fingerprint;selected.set(r.file,r);};
      root.querySelectorAll('[data-pick]').forEach(e=>e.onchange=()=>{try{const r=visible[+e.dataset.pick];if(e.checked)pick(r);else selected.delete(r.file);}catch(error){message=error.message;}remember();render();});
      $('[data-select]').onclick=()=>{try{visible.filter(r=>!r.unfinished).forEach(pick);}catch(e){message=e.message;}remember();render();};
      root.querySelectorAll('[data-open]').forEach(e=>e.onclick=async()=>{try{const row=visible[+e.dataset.open];if(io.files && !row.input)throw Error('Reselect this JSON file before opening.');await io.open(row);}catch(error){message=error.message;render();}});
      if(io.list){$('[data-prev]').onclick=()=>load(Math.max(0,offset-25));$('[data-next]').onclick=()=>load(offset+25);}
      if(io.files)$('[data-files]').onchange=async e=>{
        try {const files=[...e.target.files];if(files.length>100)throw Error('Choose at most 100 files at once.');
          busy=true;message='Reading selected files locally…';render();
          for(const file of files){if(file.size>50*1024*1024)throw Error(file.name+': exceeds 50 MiB browser import limit.');
            const doc=JSON.parse(await file.text());if(doc.format!=='a2log'||doc.version!==1||!Array.isArray(doc.segments)||!Array.isArray(doc.players))throw Error(file.name+': choose an a2log v1 JSON file.');
            const id=file.name+':'+file.size+':'+file.lastModified;
            const exact=rows.find(r=>r.file===id),matches=rows.filter(r=>!r.input && r.name===file.name);
            if(!exact && matches.length>1)throw Error('Ambiguous restored filename: '+file.name+'. Restore files with distinct names.');
            const recovered=exact||matches[0];if(recovered){recovered.input=file;recovered.unfinished=!!doc.meta?.capture_active;recovered.segments=doc.segments.length;recovered.contexts=doc.segments.map(s=>({encounter_type:s.encounter_type||doc.meta?.encounter_type||'unknown'}));continue;}
            if(rows.length>=100)throw Error('Queue limit is 100 files.');rows.push({file:id,input:file,title:doc.meta?.title||file.name,archive:doc.meta?.archive,
              unfinished:!!doc.meta?.capture_active,segments:doc.segments.length,contexts:doc.segments.map(s=>({encounter_type:s.encounter_type||doc.meta?.encounter_type||'unknown'}))});}
          message='Files loaded locally. Select new parts or resume the restored queue.';
        }catch(error){message=error.message;}finally{busy=false;render();}
      };
      $('[data-upload]').onclick=run;$('[data-cancel]').onclick=()=>{cancel=true;message='Cancellation requested; the in-flight upload can finish.';render();};
      $('[data-clear]').onclick=()=>{for(const r of new Set([...rows,...selected.values()])){delete r.request_id;delete r.fingerprint;}selected.clear();results.clear();batch=null;retryUnknown=false;if(io.files)rows=[];remember();message='Queue cleared; local files and server uploads remain.';render();};
      $('[data-manifest]').onclick=download;
    }
    render();if(io.list)load(0);
    return {cancel:()=>{cancel=true;}};
  }
  window.A2ArchiveUpload={mount};
})();
