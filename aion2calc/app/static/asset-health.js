/* Session-local image failures. Export counts/known skill IDs, never full URLs. */
(function(){
  'use strict';
  const hosts=new Set(['metabot.gg','assets.playnccdn.com','profileimg.plaync.com','a2dil.com']);
  const failures=new Map(),limit=200,wait=5*60*1000;
  const placeholder='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" rx="4" fill="#263048"/><path d="M16 5L25 16L16 27L7 16Z" fill="none" stroke="#e8cf8e"/></svg>');
  function resource(value){try{let url=new URL(value,location.href);if(url.origin===location.origin&&url.pathname==='/api/icon')url=new URL(url.searchParams.get('u'));if(url.protocol!=='https:'||!hosts.has(url.hostname)||url.username||url.password)return null;return url;}catch(_){return null;}}
  document.addEventListener('error',event=>{
    if(!(event.target instanceof HTMLImageElement))return;
    const url=resource(event.target.currentSrc||event.target.src);if(!url)return;
    const now=Date.now(),previous=failures.get(url.href),skill=url.hostname==='metabot.gg'?url.pathname.match(/^\/web\/aion2\/skills\/(\d+)\.webp$/):null;
    if(!previous&&failures.size>=limit)failures.delete(failures.keys().next().value);
    failures.set(url.href,{host:url.hostname,skill_id:skill?skill[1]:null,count:(previous?.count||0)+1,last_failed:now});
  },true);
  window.A2AssetHealth={
    source(value){const url=resource(value),failure=url&&failures.get(url.href);return failure&&Date.now()-failure.last_failed<wait?placeholder:value;},
    report(){return {scope:'This browser session',http_status:'Not available from browser image error events',retry_delay_seconds:wait/1000,limit,failures:Array.from(failures.values()).map(row=>({...row}))};},
    retry(){failures.clear();}
  };
})();
