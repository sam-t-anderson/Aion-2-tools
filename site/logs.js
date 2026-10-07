A2LogOwnership.mount(document.getElementById("owned-logs"));
A2Community.mount(document.getElementById("community"),{api:path=>A2.api(path),open:id=>{location.href="log.html?id="+encodeURIComponent(id);}});
