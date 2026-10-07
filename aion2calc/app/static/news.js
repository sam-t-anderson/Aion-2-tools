/* Official headline cards; no article HTML or inferred patch assignment. */
(function(){
  'use strict';
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const official=x=>{try{const u=new URL(x);return u.protocol==='https:'&&u.hostname==='aion2.plaync.com'&&!u.username&&!u.password&&/^\/en-us\/board\/(notice|update)\/(list|view)$/.test(u.pathname)?u.href:'';}catch(_){return '';}};
  function mount(root,io){
    let data=null,busy=false,error='',filter='All',serial=0;
    const date=x=>{const d=new Date(x);return Number.isFinite(d.getTime())?d.toLocaleString():'Date unavailable';};
    function render(){
      if(!root.isConnected)return;
      const rows=(Array.isArray(data?.entries)?data.entries:[]).slice(0,20).filter(r=>filter==='All'||r.category===filter);
      root.innerHTML=`<section class="note"><div class="row"><h2>Official AION 2 news</h2><button class="btn small" data-refresh ${busy?'disabled':''}>Refresh</button><label>Show <select data-filter>${['All','Notices','Updates'].map(v=>`<option ${v===filter?'selected':''}>${v}</option>`).join('')}</select></label></div>
        <p class="small muted">English/global headlines from the official site. Announcement dates do not identify the patch installed on your computer or used in a past combat log.</p>
        <p><a href="https://aion2.plaync.com/en-us/board/notice/list" target="_blank" rel="noopener noreferrer">Official notices</a> · <a href="https://aion2.plaync.com/en-us/board/update/list" target="_blank" rel="noopener noreferrer">Official updates</a></p>
        <div role="status" aria-live="polite">${esc(busy?'Loading official headlines…':error||(!data?'':data.status==='ready'?'Official sources loaded.':'Some official sources are unavailable; retained headlines may be stale.'))}</div>
        <div class="news-cards">${rows.map(r=>{const url=official(r.url);if(!url)return '';return `<article class="news-card"><div class="row"><span class="chip">${esc(r.category)}</span><span class="small muted">${esc(date(r.published_at))}</span></div><h3><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a></h3><p class="small muted">${esc(r.publisher||'Official AION 2 site')}${r.retrieved_at?' · retrieved '+esc(date(r.retrieved_at*1000)):''}</p><a class="btn small" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Read on official site ↗</a></article>`;}).join('')||(!busy?'<p>No retained headlines match this filter. Use the official source links above.</p>':'')}</div>
        ${data?.note?`<p class="small muted">${esc(data.note)}</p>`:''}</section>`;
      root.querySelector('[data-refresh]').onclick=load;root.querySelector('[data-filter]').onchange=e=>{filter=e.target.value;render();};
    }
    async function load(){if(busy)return;busy=true;error='';const current=++serial;render();try{const value=await io.api('/api/v1/news');if(current===serial)data=value;}catch(e){if(current===serial)error=e.message||'The news feed is unavailable. Use the official source links.';}finally{if(current===serial){busy=false;render();}}}
    render();load();return {dispose:()=>{serial++;}};
  }
  window.A2News={mount};
})();
