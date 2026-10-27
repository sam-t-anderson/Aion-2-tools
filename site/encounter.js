// encounter.html?f=<id>&view=race|progress|reports|rankings|statistics[&metric=dps|hps|speed]: a featured encounter's
// pages (static/featured.js), from the log server's public routes.
(function () {
  const params=new URLSearchParams(location.search),id=params.get('f')||'',root=document.getElementById('encounter');
  const link=(f,view,metric)=>'encounter.html?'+new URLSearchParams({f,view:view||'race',...(metric?{metric}:{})});
  if(!/^fe_[0-9a-f]{10}$/.test(id)){
    root.innerHTML='<div class="note">This address names no featured encounter. The featured encounters are at the top of <a href="logs.html">Combat logs</a>.</div>';
    return;
  }
  A2Featured.page(root,{api:A2.api,id,view:params.get('view'),metric:params.get('metric'),link,
    logLink:(log,segment)=>'log.html?id='+encodeURIComponent(log)+(Number.isInteger(segment)?'&segment='+segment:''),loaded:f=>{document.title=f.title+' — Aion 2 Calc';}});
})();
