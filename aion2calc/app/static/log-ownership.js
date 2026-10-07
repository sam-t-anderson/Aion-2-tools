/* Private upload management. Credentials never enter public a2log documents. */
(function(){
"use strict";
const KEY='a2log-owners-v1',LIMIT=2000;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function clean(row){
 if(!row || typeof row!=='object')throw Error('Invalid upload credential');
 const server=String(row.server||'').replace(/\/+$/,''), u=new URL(server);
 if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash||!u.hostname||!(/^[a-z0-9]{6,16}$/i.test(row.id||''))||!(/^[a-z0-9_-]{20,128}$/i.test(row.delete_token||'')))throw Error('Invalid original server, ID or private credential');
 return {server,id:row.id,delete_token:row.delete_token,title:String(row.title||row.id).slice(0,200)};
}
function browserRows(){const rows=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(rows)||rows.length>LIMIT)throw Error('Invalid local credential storage');return rows.map(clean);}
function browserImport(rows){
 if(!Array.isArray(rows)||rows.length>LIMIT)throw Error('Backup must contain at most 2,000 credentials');
 const validated=rows.map(clean),values=new Map(browserRows().map(r=>[r.server+'|'+r.id,r]));
 validated.forEach(r=>values.set(r.server+'|'+r.id,r));
 if(values.size>LIMIT)throw Error('Credential storage is full; back up and forget unused entries first');
 const result=[...values.values()];localStorage.setItem(KEY,JSON.stringify(result));return result;
}
function download(value){const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='PRIVATE-combat-log-credentials.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function direct(row,action,visibility){
 row=clean(row);let path='/api/v1/logs/'+row.id,method='GET',body;
 if(action==='refresh')path+='/ownership';
 else if(action==='open')path+='/raw';
 else if(action==='delete')method='DELETE';
 else if(['visibility','rotate'].includes(action)){path+='/visibility';method='PUT';body=JSON.stringify({visibility,rotate:action==='rotate'});}
 else throw Error('Unknown management action');
 const response=await fetch(row.server+path,{method,body,redirect:'error',cache:'no-store',credentials:'omit',headers:{'X-Log-Token':row.delete_token,...(body?{'Content-Type':'application/json'}:{})}});
 const result=await response.json();if(!response.ok)throw Error(result.error||'Upload management refused');return result;
}
function mount(root,io={}){
 let rows=[],page=0,status=new Map(),message='';
 const list=io.list||(()=>browserRows()),save=io.import||browserImport;
 const forget=io.forget||(row=>{localStorage.setItem(KEY,JSON.stringify(browserRows().filter(r=>r.server!==row.server||r.id!==row.id)));});
 const request=io.request||direct;
 async function load(){try{rows=await list();render();}catch(e){root.textContent=e.message;}}
 function render(){
  page=Math.min(page,Math.max(0,Math.ceil(rows.length/25)-1));
  root.innerHTML=`<details open class="note"><summary>My uploads · ${rows.length} saved credentials</summary><p class="small muted">Credentials stay on this device/browser. Import a private backup to manage uploads made elsewhere. A character name, shared upload key or view link does not establish ownership. Public: listed and eligible for community comparisons. Unlisted: anyone with the link can view; legacy anonymous calibration can contribute. Private: secret link only; excluded from public comparisons and calibration. Making a log private cannot recall copies already downloaded.</p><div class="row"><button class="btn small" data-backup>Export private credentials</button><label>Import private backup <input type="file" data-import accept=".json"></label><button class="btn small" data-reload>Reload saved credentials</button></div><p class="small muted">Keep backups private: they permit visibility changes, private-link access and permanent deletion. Importing a file stores credentials only; it does not contact its servers. Older uploads need their original delete credential.</p><div data-message role="status">${esc(message)}</div><div class="cr-scroll"><table class="t"><tr><th>Upload · original server</th><th>Current visibility / link</th><th>Controls</th></tr>${rows.slice(page*25,page*25+25).map((r,i)=>{
   const index=page*25+i,s=status.get(r.server+'|'+r.id),known=s&&!s.error;
   let link='';if(known&&s.url){const u=new URL(s.url);if(['http:','https:'].includes(u.protocol)&&u.origin===new URL(r.server).origin)link=`<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">Open shared link</a>`;}
   return `<tr><td>${esc(r.title)} · ${esc(r.id)}<br>${esc(r.server)}</td><td>${esc(s?.error||s?.visibility||'Refresh to check')}<br>${link}</td><td><button class="btn small" data-action="refresh" data-index="${index}">Refresh</button><select data-visibility="${index}" aria-label="Upload visibility" ${known?'':'disabled'}>${['unlisted','public','private'].map(v=>`<option ${s?.visibility===v?'selected':''}>${v}</option>`).join('')}</select><button class="btn small" data-action="visibility" data-index="${index}" ${known?'':'disabled'}>Save visibility</button><button class="btn small" data-action="rotate" data-index="${index}" ${known&&s.visibility==='private'?'':'disabled'}>Rotate private link</button>${io.open?`<button class="btn small" data-action="open" data-index="${index}">Review</button>`:''}<button class="btn small" data-action="delete" data-index="${index}">Delete upload</button><button class="btn small" data-forget="${index}">Forget credential</button></td></tr>`;
  }).join('')||'<tr><td colspan="3">No saved upload credentials. New desktop uploads are saved automatically.</td></tr>'}</table></div><div class="row"><button class="btn small" data-prev ${page?'':'disabled'}>Previous</button>${page+1} / ${Math.max(1,Math.ceil(rows.length/25))}<button class="btn small" data-next ${(page+1)*25>=rows.length?'disabled':''}>Next</button></div></details>`;
  const recovery=document.createElement('details');
  recovery.innerHTML='<summary>Recover an older upload with its original delete credential</summary><div class="row"><input data-server placeholder="Original server URL" aria-label="Original upload server"><input data-id placeholder="Upload ID" aria-label="Upload ID"><input type="password" data-token placeholder="Original delete token" aria-label="Original delete credential"><button class="btn small" data-recover>Save credential locally</button></div>';
  root.querySelector('[data-message]').before(recovery);
  recovery.querySelector('[data-recover]').onclick=async()=>{try{const row=clean({server:recovery.querySelector('[data-server]').value.trim(),id:recovery.querySelector('[data-id]').value.trim(),delete_token:recovery.querySelector('[data-token]').value.trim()});await save([row]);message='Credential saved locally. Refresh to verify it with the original server.';await load();}catch(e){root.querySelector('[data-message]').textContent=e.message;}};
  root.querySelector('[data-backup]').onclick=()=>download({format:'a2log-owners',version:1,owners:rows});
  root.querySelector('[data-import]').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>2*1024*1024)throw Error('Backup exceeds 2 MiB');const backup=JSON.parse(await file.text());if(backup.format!=='a2log-owners'||backup.version!==1)throw Error('Choose a private combat-log ownership backup');if(!confirm('Import private upload credentials? Keep this backup private. No server will be contacted until you use its controls.'))return;await save(backup.owners);message='Credentials imported. Refresh an upload to verify access.';await load();}catch(e){root.querySelector('[data-message]').textContent=e.message;}};
  root.querySelector('[data-reload]').onclick=load;
  root.querySelector('[data-prev]').onclick=()=>{page--;render();};root.querySelector('[data-next]').onclick=()=>{page++;render();};
  root.querySelectorAll('[data-forget]').forEach(b=>b.onclick=async()=>{if(!confirm('Forget this local credential? The uploaded log remains on the server. Export a backup first if you need future access.'))return;try{await forget(rows[+b.dataset.forget]);message='Local credential forgotten; server log unchanged.';await load();}catch(e){root.querySelector('[data-message]').textContent=e.message;}});
  root.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{
   const row=rows[+b.dataset.index],action=b.dataset.action,key=row.server+'|'+row.id;
   const visibility=action==='rotate'?'private':root.querySelector(`[data-visibility="${b.dataset.index}"]`).value;
   if(action==='delete'&&!confirm('Permanently delete this server upload and its stored profiles/statistics? Your local combat file remains.'))return;
   if(action==='rotate'&&!confirm('Replace the private view link? The previous secret link will stop working.'))return;
   if(action==='visibility'&&visibility==='public'&&!confirm('List this upload publicly, including recorded character profiles, and include eligible samples in community comparisons?'))return;
   root.querySelectorAll('button').forEach(x=>x.disabled=true);
   try{const result=await request(row,action,visibility);if(action==='delete'){await forget(row);status.delete(key);message='Server upload deleted.';if(io.deleted)io.deleted(row);await load();}else if(action==='open'){await io.open(result,row);render();}else{status.set(key,result);message=action==='refresh'?'Current server status loaded.':'Privacy updated. Use the displayed link.';render();}}catch(e){message=e.message;status.set(key,{error:e.message});render();}
  });
 }
 load();const manager={refresh:()=>root.isConnected?load():undefined};window.A2OwnedUploads=manager;return manager;
}
document.addEventListener('a2log-uploaded',()=>window.A2OwnedUploads?.refresh());
window.A2LogOwnership={mount,clean,remember:(server,result,title)=>browserImport([{server,id:result.id,delete_token:result.delete_token,title}])};
})();
