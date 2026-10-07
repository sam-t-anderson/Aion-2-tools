let logSource='community';
A2LogTabs.mount(document.getElementById('combat-log-tabs'),logSource,value=>{logSource=value;});
A2LogOwnership.mount(document.getElementById("owned-logs"));
A2Community.mount(document.getElementById("community"),{api:path=>A2.api(path),open:id=>{location.href="log.html?id="+encodeURIComponent(id);}});

let archiveReview, previewDocument;
const previewRoot=document.getElementById('archive-review');
function renderPreviewPage(){
  const focused=location.hash==='#local-log' && !!previewDocument;
  for(const child of document.querySelector('main').children)child.hidden=focused?child!==previewRoot:child===previewRoot;
  if(archiveReview){archiveReview.dispose();archiveReview=null;}
  previewRoot.replaceChildren();
  document.title=focused?'Combat log — Aion 2 Calc':'Logs — Aion 2 Calc';
  if(!focused){A2LogTabs.mount(document.getElementById('combat-log-tabs'),logSource,value=>{logSource=value;});return;}
  const back=document.createElement('a');back.className='btn small';back.href='#';back.textContent='← Back to combat logs';
  const heading=document.createElement('p');heading.append(back);const viewer=document.createElement('div');previewRoot.append(heading,viewer);
  archiveReview=A2CombatReview.mount(viewer,previewDocument);
  window.scrollTo(0,0);
}
window.addEventListener('hashchange',renderPreviewPage);
renderPreviewPage();
A2ArchiveUpload.mount(document.getElementById('archive-upload'),{
  files:true,types:A2Community.types,
  context:async()=>{const config=A2.cfg(),url=(A2.base()||config.url||'').replace(/\/+$/,'');
    return {url,key:url===(config.url||'').replace(/\/+$/,'')?config.key:undefined};},
  open:async row=>{previewDocument=JSON.parse(await row.input.text());
    if(location.hash==='#local-log')renderPreviewPage();else location.hash='local-log';},
  upload:async(row,batch)=>{
    const text=await row.input.text(),doc=JSON.parse(text);
    if(doc.meta?.capture_active)throw Error('Unfinished checkpoints are excluded; review and export a finished part first.');
    let body=text;const headers={'Content-Type':'application/json'};
    if(batch.key)headers.Authorization='Bearer '+batch.key;
    if(typeof CompressionStream!=='undefined'){
      body=await new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
      headers['Content-Encoding']='gzip';
    }
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),65000);
    let response,result;
    try {
      response=await fetch(batch.url+'/api/v1/logs?visibility='+encodeURIComponent(batch.visibility),
        {method:'POST',body,headers,credentials:'omit',redirect:'error',cache:'no-store',signal:controller.signal});
      result=await response.json();
    }catch(e){if(e.name==='AbortError')throw Error('Upload timed out; the server outcome is unknown. Check My uploads/server before retrying.');throw e;}
    finally{clearTimeout(timer);}
    if(!response.ok || result.error)throw Error('Upload refused ('+response.status+'): '+(result.error||response.statusText));
    try {A2LogOwnership.remember(batch.url,result,doc.meta?.title||row.input.name);}
    catch(e){result.ownership_warning='Uploaded, but could not save ownership on this browser: '+e.message;}
    return result;
  }
});
