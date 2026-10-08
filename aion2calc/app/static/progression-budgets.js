/* Highest reported resources; never presented as verified progression caps. */
(function(){
 'use strict';
 const keys=['skill','stigma','daevanion'];
 async function read(api,cls,context={}){
  const query=new URLSearchParams({class:cls});
  for(const k of ['region','game_patch'])if(context[k])query.set(k,context[k]);
  const result=await api('/api/v1/progression?'+query);
  const rows=(result.observations||[]).filter(r=>r.class_name===cls&&keys.every(k=>Number.isInteger(r[k])&&r[k]>=0&&r[k]<=10000));
  const points=Object.fromEntries(keys.map(k=>[k,rows.length?Math.max(...rows.map(r=>r[k])):null]));
  return {points,rows,note:rows.length?'Highest server-reported totals from '+rows.length+' class/context observations; reported totals and allocated lower bounds are not verified game caps. '+(!context.region||!context.game_patch?'Region/build is unspecified; available contexts are pooled.':'Matched region/build only.'):'No server-reported totals for this class/context. Enter available points explicitly.'};
 }
 window.A2ProgressionBudgets={read};
})();
