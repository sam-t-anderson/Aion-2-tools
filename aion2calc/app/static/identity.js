/* Community identity: claim the characters you record, choose how other uploaders' public logs
   show you, recover a claim from your own recordings. Shared by the desktop app and the Pages site.
   A claim is proven by the private credentials of your own public recordings (My uploads), never by
   a password; the identity credential the server issues stays on this device/browser. */
(function(){
"use strict";
const KEY='a2id-claims-v1',LIMIT=200,TOKEN=/^a2id_[A-Za-z0-9_-]{20,128}$/;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const when=t=>t?new Date(t*1000).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'}):'';
function clean(row){
 if(!row||typeof row!=='object')throw Error('Invalid identity credential');
 const server=String(row.server||'').replace(/\/+$/,''),u=new URL(server);
 if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash||!u.hostname)throw Error('Invalid server address');
 const name=String(row.name||'').trim().slice(0,60),server_name=String(row.server_name||'').trim().slice(0,40);
 if(!name||!TOKEN.test(String(row.token||'')))throw Error('Invalid character name or identity credential');
 return {server,name,server_name,token:row.token,status:String(row.status||'').slice(0,20),claimed_at:Number(row.claimed_at)||0};
}
function browserRows(){const rows=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(rows)||rows.length>LIMIT)throw Error('Invalid local identity storage');return rows.map(clean);}
function browserSave(rows){if(!Array.isArray(rows)||rows.length>LIMIT)throw Error('Too many identity credentials');const value=rows.map(clean);localStorage.setItem(KEY,JSON.stringify(value));return value;}
async function call(base,path,{method='GET',body,token}={}){
 const response=await fetch(base+path,{method,body:body?JSON.stringify(body):undefined,redirect:'error',cache:'no-store',credentials:'omit',
  headers:{...(body?{'Content-Type':'application/json'}:{}),...(token?{'X-Identity-Token':token}:{})}});
 const out=await response.json().catch(()=>({}));
 if(!response.ok)throw Error(out.error||('Identity request failed ('+response.status+')'));
 return out;
}
const ckey=(name,server)=>String(name||'').trim().toLowerCase()+'|'+String(server||'').trim();
function mount(root,io={}){
 const credentials=io.credentials||(()=>window.A2LogOwnership.rows());
 const server=io.server||(async()=>{try{await window.A2.api('/.well-known/a2log.json');}catch(e){/* the base may still be known */}return window.A2.base();});
 const claims=io.claims||browserRows,save=io.save||browserSave;
 let base='',characters=[],mine=[],statuses=new Map(),message='',minimum=3;
 async function load(){
  try{
   base=String(await server()||'').replace(/\/+$/,'');
   if(!base){root.innerHTML='<details class="note"><summary>Your characters</summary><p class="small muted">Set a share server first; claims live on the server your recordings are uploaded to.</p></details>';return;}
   const creds=(await credentials()).filter(r=>String(r.server||'').replace(/\/+$/,'')===base).slice(-LIMIT);
   mine=(await claims()).filter(c=>c.server===base);
   characters=[];
   if(creds.length){const out=await call(base,'/api/v1/identity/claimable',{method:'POST',body:{evidence:creds.map(r=>({id:r.id,delete_token:r.delete_token}))}});characters=out.characters||[];minimum=out.min_recordings||3;}
   statuses=new Map();
   for(const c of mine){try{statuses.set(ckey(c.name,c.server_name),await call(base,'/api/v1/identity',{token:c.token}));}catch(e){statuses.set(ckey(c.name,c.server_name),{error:e.message});}}
   render();
  }catch(e){root.innerHTML=`<details open class="note"><summary>Your characters</summary><p>${esc(e.message)}</p><button class="btn small" data-reload>Retry</button></details>`;root.querySelector('[data-reload]').onclick=load;}
 }
 function evidence(){return credentials().then(rows=>rows.filter(r=>String(r.server||'').replace(/\/+$/,'')===base).slice(-LIMIT).map(r=>({id:r.id,delete_token:r.delete_token})));}
 async function remember(row){const rows=(await claims()).filter(c=>!(c.server===row.server&&ckey(c.name,c.server_name)===ckey(row.name,row.server_name)));rows.push(clean(row));await save(rows);}
 async function forget(row){await save((await claims()).filter(c=>!(c.server===row.server&&ckey(c.name,c.server_name)===ckey(row.name,row.server_name))));}
 function render(){
  const rows=new Map();
  for(const c of characters)rows.set(ckey(c.name,c.server),{name:c.name,server_name:c.server,info:c});
  for(const c of mine){const k=ckey(c.name,c.server_name);rows.set(k,{...(rows.get(k)||{name:c.name,server_name:c.server_name,info:null}),stored:c,status:statuses.get(k)});}
  const body=[...rows.values()].map((r,i)=>{
   const info=r.info,s=r.status,st=s&&!s.error?s:null,recordings=info?info.recordings:0,claimable=!!(info&&info.claimable);
   let state='',actions='';
   if(st&&st.status==='active'){
    state=`<b>Verified</b> since ${esc(when(st.verified_at))} · ${st.recordings} recording${st.recordings===1?'':'s'}`;
    if(st.challenge)state+=`<p class="note">Another uploader claimed this character with newer recordings. Upload a public recording of yours that is newer than theirs and press <b>Renew</b> before ${esc(when(st.challenge.until))}, or the claim passes to them.</p>`;
    actions=`<label><input type="checkbox" data-optout="${i}" ${st.opt_out?'checked':''}> Hide me in other uploaders' public logs, leaderboards and parse brackets</label><br><button class="btn small" data-claim="${i}" ${claimable?'':'disabled'}>Renew</button> <button class="btn small" data-release="${i}">Release</button>`;
   }else if(st&&st.status==='pending'){
    state=`<b>Pending</b> · becomes yours on ${esc(when(st.activates_at))} unless the current holder renews with a newer recording`;
    actions=`<button class="btn small" data-release="${i}">Withdraw</button>`;
   }else if(r.stored){
    state=`<b>${esc(s?.error?'Credential not accepted':st?.status||'unknown')}</b>${s?.error?' · '+esc(s.error):''}`;
    actions=`<button class="btn small" data-claim="${i}" ${claimable?'':'disabled'}>Claim again</button> <button class="btn small" data-forget="${i}">Forget</button>`;
   }else if(info&&info.claimed){
    state=info.held_with_these_credentials?'Claimed with these recordings on another device':`Held by another uploader (their latest recording ${esc(when(info.holder_latest_recording))})`;
    const newer=!info.held_with_these_credentials&&claimable&&info.latest_recording>(info.holder_latest_recording||0);
    actions=info.held_with_these_credentials?`<button class="btn small" data-claim="${i}" ${claimable?'':'disabled'}>Recover</button>`:`<button class="btn small" data-claim="${i}" ${newer?'':'disabled'} title="${newer?'Your recordings are newer: the holder gets seven days to renew':'Only newer recordings than the holder\'s can challenge a claim'}">Challenge with newer recordings</button>`;
   }else{
    state=claimable?'Not claimed yet':`Needs ${Math.max(0,minimum-recordings)} more public recording${minimum-recordings===1?'':'s'} where you are the recording player`;
    actions=`<button class="btn small" data-claim="${i}" ${claimable?'':'disabled'}>Claim</button>`;
   }
   return `<tr><td>${esc(r.name)}${r.server_name?' <span class="muted">· '+esc(r.server_name)+'</span>':''}</td><td>${recordings}${info?' of '+minimum:''}</td><td>${state}</td><td>${actions}</td></tr>`;
  }).join('')||`<tr><td colspan="4">No characters yet. Upload public recordings where you are the recording player; three of them let you claim the character.</td></tr>`;
  root.innerHTML=`<details open class="note"><summary>Your characters · ${rows.size}</summary><p class="small muted">A claim is proven by your own recordings: the private credentials under My uploads of ${minimum} public recordings where you were the recording player. It marks the character verified wherever it is listed, and lets you hide it in other uploaders' public logs, leaderboards and parse brackets (your own uploads always show your name). Newer recordings win a contested character after a seven-day notice. Claims live on ${esc(base)}; nothing here changes who recorded a log or its ranking.</p><div class="tablewrap"><table class="t"><tr><th>Character</th><th>Public recordings</th><th>Status</th><th>Actions</th></tr>${body}</table></div><div class="row"><button class="btn small" data-reload>Refresh</button><span class="small muted" data-message role="status">${esc(message)}</span></div></details>`;
  const list=[...rows.values()];
  root.querySelector('[data-reload]').onclick=load;
  const run=async fn=>{root.querySelectorAll('button,input').forEach(x=>x.disabled=true);try{await fn();}catch(e){message=e.message;}await load();};
  root.querySelectorAll('[data-claim]').forEach(b=>b.onclick=()=>run(async()=>{
   const r=list[+b.dataset.claim];
   const out=await call(base,'/api/v1/identity/claim',{method:'POST',body:{name:r.name,server:r.server_name||'',evidence:await evidence()},token:r.stored?.token});
   if(out.token)await remember({server:base,name:r.name,server_name:r.server_name||'',token:out.token,status:out.status,claimed_at:out.claimed_at});
   else if(r.stored)await remember({...r.stored,status:out.status});
   message=out.status==='pending'?'Claim recorded; it takes over after the notice period unless the holder renews.':'Claim verified.';
  }));
  root.querySelectorAll('[data-optout]').forEach(b=>b.onchange=()=>run(async()=>{const r=list[+b.dataset.optout];await call(base,'/api/v1/identity/preferences',{method:'POST',body:{opt_out:b.checked},token:r.stored.token});message=b.checked?'Hidden in other uploaders’ public logs, leaderboards and parse brackets.':'Shown by name again.';}));
  root.querySelectorAll('[data-release]').forEach(b=>b.onclick=()=>{if(!confirm('Give this character up? It becomes claimable again (a pending challenger takes it at once).'))return;run(async()=>{const r=list[+b.dataset.release];await call(base,'/api/v1/identity/release',{method:'POST',body:{},token:r.stored.token});await forget(r.stored);message='Released.';});});
  root.querySelectorAll('[data-forget]').forEach(b=>b.onclick=()=>run(async()=>{await forget(list[+b.dataset.forget].stored);message='Local credential forgotten.';}));
  message='';
 }
 load();const manager={refresh:()=>root.isConnected?load():undefined};window.A2YourCharacters=manager;return manager;
}
document.addEventListener('a2log-uploaded',()=>window.A2YourCharacters?.refresh());
window.A2Identity={mount,clean,call};
})();
