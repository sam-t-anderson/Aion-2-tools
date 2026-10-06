(function () {
  const themes=["system","light","dark"];
  const button=document.getElementById("theme");
  function apply(value) {
    if(value==="system")delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=value;
    if(button)button.textContent={system:"◐",light:"☀",dark:"☾"}[value] || "◐";
  }
  let current="system";try{current=localStorage.getItem("theme") || "system";}catch (_){}
  apply(current);
  if(button)button.onclick=()=>{current=themes[(themes.indexOf(current)+1)%themes.length];try{localStorage.setItem("theme",current);}catch(_){}apply(current);};
})();
