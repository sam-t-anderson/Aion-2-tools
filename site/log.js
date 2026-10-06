(async function () {
  const params=new URLSearchParams(location.search), id=params.get("id"),token=params.get("t");
  const query=token?"?t="+encodeURIComponent(token):"";
  const get=id=>{if(!/^[a-z0-9]{6,16}$/i.test(id || ""))throw Error("Invalid public log ID");return window.A2.api("/api/v1/logs/"+id+"/raw"+(id===params.get("id")?query:""));};
  try {window.A2CombatReview.mount(document.getElementById("review"),await get(id),{compare:get});}
  catch(e) {document.getElementById("review").textContent=e.message;}
})();
