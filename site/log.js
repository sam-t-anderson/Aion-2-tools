A2LogOwnership.mount(document.getElementById("owned-logs"));
(async function () {
  const params=new URLSearchParams(location.search), id=params.get("id"),token=params.get("t");
  const query=token?"?t="+encodeURIComponent(token):"";
  const get=id=>{if(!/^[a-z0-9]{6,16}$/i.test(id || ""))throw Error("Invalid public log ID");return window.A2.api("/api/v1/logs/"+id+"/raw"+(id===params.get("id")?query:""));};
  try {window.A2CombatReview.mount(document.getElementById("review"),await get(id),{report:async body=>{const response=await fetch(A2.base()+"/api/v1/logs/"+id+"/reports"+query,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),redirect:'error',cache:'no-store',credentials:'omit'});const result=await response.json();if(!response.ok)throw Error(result.error||'Report submission failed');return result;},importPlan:plan=>{A2Raid.importPlan(plan);location.href="planner.html";},compare:get,rankings:segment=>A2.api("/api/v1/logs/"+id+"/rankings?segment="+segment+(token?"&t="+encodeURIComponent(token):""))});}
  catch(e) {document.getElementById("review").textContent=e.message;}
})();
