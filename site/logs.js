A2LogOwnership.mount(document.getElementById("owned-logs"));
A2Community.mount(document.getElementById("community"),{api:path=>A2.api(path),open:id=>{location.href="log.html?id="+encodeURIComponent(id);}});

let archiveReview;
A2ArchiveUpload.mount(document.getElementById('archive-upload'),{
  files:true,types:A2Community.types,
  context:async()=>{const config=A2.cfg(),url=(A2.base()||config.url||'').replace(/\/+$/,'');
    return {url,key:url===(config.url||'').replace(/\/+$/,'')?config.key:undefined};},
  open:async row=>{const doc=JSON.parse(await row.input.text());if(archiveReview)archiveReview.dispose();
    archiveReview=A2CombatReview.mount(document.getElementById('archive-review'),doc);document.getElementById('archive-review').scrollIntoView({behavior:'smooth'});},
  upload:async(row,batch)=>{
    const text=await row.input.text(),doc=JSON.parse(text);
    if(doc.meta?.capture_active)throw Error('Unfinished checkpoints are excluded; review and export a finished part first.');
    let body=text;const headers={'Content-Type':'application/json'};
    if(batch.key)headers.Authorization='Bearer '+batch.key;
    if(typeof CompressionStream!=='undefined'){
      body=await new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
      headers['Content-Encoding']='gzip';
    }
    const response=await fetch(batch.url+'/api/v1/logs?visibility='+encodeURIComponent(batch.visibility),
      {method:'POST',body,headers,credentials:'omit',redirect:'error',cache:'no-store'});
    const result=await response.json().catch(()=>({error:response.statusText}));
    if(!response.ok || result.error)throw Error('Upload refused ('+response.status+'): '+(result.error||response.statusText));
    try {A2LogOwnership.remember(batch.url,result,doc.meta?.title||row.input.name);}
    catch(e){result.ownership_warning='Uploaded, but could not save ownership on this browser: '+e.message;}
    return result;
  }
});
