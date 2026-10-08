(async function(){
  'use strict';
  const root=document.getElementById('build-workspace'),p=new URLSearchParams(location.search),id=p.get('log'),token=p.get('t');
  const options={catalogURL:'static/build-catalog.json',api:path=>A2.api(path),evaluate:async doc=>{const base=await A2.api('/.well-known/a2log.json').then(()=>A2.base());const r=await fetch(base+'/api/v1/build-evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(doc)});const value=await r.json();if(!r.ok||value.error)throw Error(value.error||'Evaluation unavailable; update the community server.');return value;},mode:p.get('mode')};
  if(id){
    try{
      if(!/^[a-z0-9]{6,16}$/i.test(id))throw Error('Invalid log ID');
      root.textContent='Loading the saved character reference…';
      const doc=await A2.api('/api/v1/logs/'+id+'/raw'+(token?'?t='+encodeURIComponent(token):''));
      const segment=/^\d{1,6}$/.test(p.get('segment')||'')?Number(p.get('segment')):0;
      if(!Array.isArray(doc.segments)||!doc.segments[segment])throw Error('The source encounter is unavailable');
      const player=p.get('player'),entry=doc.segments[segment];
      const actor=(entry.entities||[]).find(x=>x.id===player)||(doc.players||[]).find(x=>x.id===player);
      // Snapshots may be attached to the document-level player rather than segment identity.
      const snapshot=actor?.profile_snapshot||(doc.players||[]).find(x=>x.id===player)?.profile_snapshot;
      if(!actor||!snapshot?.data)throw Error('No saved profile was recorded for this character');
      const back=new URLSearchParams({id,segment:String(segment)});if(p.get('mode'))back.set('mode',p.get('mode'));if(token)back.set('t',token);
      Object.assign(options,{reference:{snapshot},className:actor.class,level:snapshot.data.profile?.characterLevel,source:{log:id,actor:player,basis:'Saved upload-time character profile; this is a reference, not an edited historical build.'},backURL:'log.html?'+back});
    }catch(e){root.textContent='Could not open the saved character: '+e.message;return;}
  }
  A2BuildWorkspace.mount(root,options);
})();
