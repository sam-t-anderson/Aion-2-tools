/* Regional official headline cards; article bodies and build identity are not inferred. */
(function(){
 'use strict';
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const regions={global:{label:'Global (English)',base:'https://aion2.plaync.com/en-us'},kr:{label:'Korea (Korean)',base:'https://aion2.plaync.com/ko-kr'},tw:{label:'Taiwan (Traditional Chinese)',base:'https://tw.ncsoft.com/aion2'}};
 function official(value,region){try{const u=new URL(value),base=new URL(regions[region].base);return u.origin===base.origin&&!u.username&&!u.password&&new RegExp('^'+base.pathname+'/board/(notice|update)/view$').test(u.pathname)&&/^[a-f0-9]{24}$/.test(u.searchParams.get('articleId')||'')?u.href:'';}catch(_){return '';}}
 function mount(root,io){
  let data=null,busy=false,error='',filter='All',serial=0,disposed=false,region='global';
  try{const saved=localStorage.getItem('a2-news-region');if(regions[saved])region=saved;}catch(_){}
  const date=x=>{const d=new Date(x);return Number.isFinite(d.getTime())?d.toLocaleString():'Date unavailable';};
  function render(){
   if(disposed||!root.isConnected)return;
   const rows=(Array.isArray(data?.entries)?data.entries:[]).slice(0,20).filter(r=>(!r.region?region==='global':r.region===region)&&(filter==='All'||r.category===filter));
   root.innerHTML=`<section class="note"><div class="row"><h2>Official AION 2 news</h2><label>News region <select data-region>${Object.entries(regions).map(([id,r])=>`<option value="${id}" ${id===region?'selected':''}>${esc(r.label)}</option>`).join('')}</select></label><button class="btn small" data-refresh ${busy?'disabled':''}>Refresh</button><label>Show <select data-filter>${['All','Notices','Updates'].map(v=>`<option ${v===filter?'selected':''}>${v}</option>`).join('')}</select></label></div>
   <p class="small muted">Official regional headlines in their original language. This preference does not change your game region or identify the build used in a combat log.</p><p><a href="${regions[region].base}/board/notice/list" target="_blank" rel="noopener noreferrer">Official notices</a> · <a href="${regions[region].base}/board/update/list" target="_blank" rel="noopener noreferrer">Official updates</a></p>
   <div role="status" aria-live="polite">${esc(busy?'Loading '+regions[region].label+' headlines…':error||(!data?'':data.status==='ready'?'Official sources loaded.':'Some official sources are unavailable; retained headlines may be stale.'))}</div>
   ${Array.isArray(data?.unavailable_sources)&&data.unavailable_sources.length?`<p class="small muted">Unavailable sources: ${esc(data.unavailable_sources.join(', '))}</p>`:''}
   <div class="news-cards">${rows.map(r=>{const url=official(r.url,region);return !url?'':`<article class="news-card"><div class="row"><span class="chip">${esc(r.category)}</span><span class="small muted">${esc(date(r.published_at))}</span></div><h3><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a></h3><p class="small muted">${esc(regions[region].label)} · ${esc(r.publisher||'Official AION 2 site')}${Number.isFinite(r.retrieved_at)?' · retrieved '+esc(date(r.retrieved_at*1000)):''}</p><a class="btn small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Read on official site ↗</a></article>`;}).join('')||(!busy?'<p>No retained headlines match this filter. Use the official source links above.</p>':'')}</div>
   ${data?.note?`<p class="small muted">${esc(data.note)}</p>`:''}</section>`;
   root.querySelector('[data-refresh]').onclick=load;
   root.querySelector('[data-filter]').onchange=e=>{filter=e.target.value;render();};
   root.querySelector('[data-region]').onchange=e=>{region=e.target.value;data=null;try{localStorage.setItem('a2-news-region',region);}catch(_){}load();};
  }
  async function load(){
   const request=++serial,requested=region;busy=true;error='';render();
   try{const value=await io.api('/api/v1/news?region='+requested);if(request!==serial||disposed)return;if(!value||requested!=='global'&&value.region!==requested)throw Error('This community server needs an update to serve regional news. Use the official source links.');data=value;}
   catch(e){if(request===serial)error=e.message||'The news feed is unavailable. Use the official source links.';}
   finally{if(request===serial&&!disposed){busy=false;render();}}
  }
  render();load();return {dispose:()=>{disposed=true;serial++;}};
 }
 window.A2News={mount};
})();
