/* Page-local image failures; exports public asset references, never URLs or portraits. */
(function(){
  'use strict';
  const hosts=new Set(['metabot.gg','assets.playnccdn.com','profileimg.plaync.com','a2dil.com']);
  const regions=new Set(['nae','eu','as','la','kr','tw']),kinds=new Set(['item','skill','pet','wing','title','board']);
  const failures=new Map(),limit=200,referenceLimit=8,wait=5*60*1000;
  let evicted=0;
  const placeholder='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" rx="4" fill="#263048"/><path d="M16 5L25 16L16 27L7 16Z" fill="none" stroke="#e8cf8e"/></svg>');
  function resource(value){try{let url=new URL(value,location.href);if(url.origin===location.origin&&url.pathname==='/api/icon')url=new URL(url.searchParams.get('u'));if(url.protocol!=='https:'||!hosts.has(url.hostname)||url.username||url.password||![443,'',null].includes(url.port))return null;return url;}catch(_){return null;}}
  function reference(value){
    if(!value||!kinds.has(value.kind))return null;
    const id=String(value.id??'');
    if(value.namespace==='official'&&regions.has(value.region)&&/^[0-9]{1,20}$/.test(id))return {namespace:'official',kind:value.kind,id,region:value.region};
    if(value.namespace==='metabot'&&value.kind==='skill'&&/^[0-9]{1,20}$/.test(id))return {namespace:'metabot',kind:'skill',id};
    if(value.namespace==='metabot'&&value.kind==='item'&&/^[a-z0-9][a-z0-9-]{0,119}$/.test(id))return {namespace:'metabot',kind:'item',id};
    return null;
  }
  function attributes(value){const ref=reference(value);return ref?Object.entries(ref).map(([key,value])=>` data-asset-${key}="${value}"`).join(''):'';}
  document.addEventListener('error',event=>{
    if(!(event.target instanceof HTMLImageElement))return;
    const img=event.target,url=resource(img.currentSrc||img.src);if(!url)return;
    const now=Date.now(),previous=failures.get(url.href),skill=url.hostname==='metabot.gg'?url.pathname.match(/^\/web\/aion2\/skills\/([0-9]{1,20})\.webp$/):null;
    if(!previous&&failures.size>=limit){failures.delete(failures.keys().next().value);evicted++;}
    const row=previous||{host:url.hostname,skill_id:skill?skill[1]:null,count:0,references:[],references_truncated:false};
    const refs=[reference({namespace:img.dataset.assetNamespace,kind:img.dataset.assetKind,id:img.dataset.assetId,region:img.dataset.assetRegion}),skill?reference({namespace:'metabot',kind:'skill',id:skill[1]}):null];
    for(const ref of refs){if(!ref||row.references.some(r=>JSON.stringify(r)===JSON.stringify(ref)))continue;if(row.references.length<referenceLimit)row.references.push(ref);else row.references_truncated=true;}
    row.count++;row.last_failed=now;failures.set(url.href,row);
  },true);
  function report(){return {version:2,scope:'This page lifetime; cleared on reload or Retry images',http_status:'Not available from browser image error events',retry_delay_seconds:wait/1000,limit,reference_limit:referenceLimit,evicted_resources:evicted,
    note:'References identify the assets requested by rendered views, not verified URL-to-ID mappings. Official IDs stay region-scoped and separate from catalog slugs. Portrait IDs, labels, full URLs and character data are excluded. Counts are image error events, not unique assets.',
    failures:Array.from(failures.values()).map(row=>({...row,references:row.references.map(ref=>({...ref}))}))};}
  window.A2AssetHealth={attributes,report,
    source(value){const url=resource(value),failure=url&&failures.get(url.href);return failure&&Date.now()-failure.last_failed<wait?placeholder:value;},
    exportReport(){const url=URL.createObjectURL(new Blob([JSON.stringify(report(),null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='aion2-image-failures.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);},
    retry(){failures.clear();evicted=0;}
  };
})();
