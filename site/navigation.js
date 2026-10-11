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

// Accent-colour picker for the public site (matches the app's Settings → Accent
// colour). Cycles gold → crimson → emerald → azure → amethyst → rose, persisted
// in localStorage and applied via data-accent (the rules live in app.css). The
// head bootstrap applies it before paint; this only adds the toggle button.
(function () {
  const accents=["gold","crimson","emerald","azure","amethyst","rose"];
  const theme=document.getElementById("theme");
  if(!theme||!theme.parentNode)return;
  let current="gold";try{const a=localStorage.getItem("accent");if(accents.includes(a))current=a;}catch(_){}
  const btn=document.createElement("button");
  btn.id="accent";btn.className=theme.className||"iconbtn";btn.type="button";btn.textContent="◉";
  function apply(v){
    if(v==="gold")delete document.documentElement.dataset.accent;else document.documentElement.dataset.accent=v;
    btn.title="Accent colour: "+v+" (click to change)";
    btn.style.color=v==="gold"?"":{crimson:"#d05a5a",emerald:"#3fb37a",azure:"#49b8e0",amethyst:"#a07ce0",rose:"#e06aa0"}[v];
  }
  apply(current);
  theme.parentNode.insertBefore(btn,theme);
  btn.onclick=()=>{current=accents[(accents.indexOf(current)+1)%accents.length];try{localStorage.setItem("accent",current);}catch(_){}apply(current);};
})();

// Daily-active-meters count in the top-right header (the public Pages site only —
// never the desktop app, which does not load this script). Anonymous aggregate
// from the configured log server: the number of unique meters that reported in
// today. Multiple app instances on one machine, and updating the app, do not
// change the count (the client's daily token is one per install and survives
// updates). Shows nothing until the server exposes the aggregate, and silently
// hides on any error so it can never break the header.
(function () {
  const bar = document.querySelector(".topbar");
  if (!bar) return;
  const theme = document.getElementById("theme");
  const el = document.createElement("span");
  el.id = "dau"; el.className = "dau"; el.hidden = true;
  el.title = "Unique live meters active today — an anonymous daily count (one per install).";
  if (theme) bar.insertBefore(el, theme); else bar.appendChild(el);

  function pickCount(data) {
    if (!data || typeof data !== "object") return null;
    const n = typeof data.daily === "number" ? data.daily
            : typeof data.active === "number" ? data.active
            : typeof data.count === "number" ? data.count : null;
    return (typeof n === "number" && isFinite(n) && n >= 0) ? Math.floor(n) : null;
  }
  const LIVE_DEFAULT_URL = "https://raw.githubusercontent.com/sam-t-anderson/Aion-2-tools/main/aion2calc/data/global/default_server.json";
  async function resolveBase() {
    // Prefer the page's own resolver when it loaded server.js; otherwise the baked
    // config, then the project's live default (the same file server.js reads last).
    try { if (window.A2 && typeof A2.base === "function") { const b = A2.base(); if (b) return b.replace(/\/+$/, ""); } } catch (e) { /* fall through */ }
    const cfg = ((window.A2CONFIG || {}).server || "").replace(/\/+$/, "");
    if (cfg) return cfg;
    try {
      const r = await fetch(LIVE_DEFAULT_URL, { cache: "no-store" });
      if (r.ok) { const j = await r.json(); return (j && j.url ? String(j.url) : "").replace(/\/+$/, ""); }
    } catch (e) { /* offline or blocked */ }
    return "";
  }
  async function fetchCount() {
    try {
      let data;
      if (window.A2 && typeof A2.api === "function") {
        data = await A2.api("/api/v1/active-meters");          // uses the site's resolved server
      } else {
        const base = await resolveBase();
        if (!base || !/^https?:\/\//i.test(base)) return;      // no usable server here
        const r = await fetch(base + "/api/v1/active-meters");
        if (!r.ok) return;
        data = await r.json();
      }
      const n = pickCount(data);
      if (n == null) return;                                   // endpoint not ready yet
      el.textContent = "● " + n.toLocaleString() + " meter" + (n === 1 ? "" : "s") + " today";
      el.hidden = false;
    } catch (e) { /* server not ready, offline or blocked: show nothing */ }
  }
  fetchCount();
})();

// Accessibility: a "skip to content" link as the first focusable element on every
// site page (they all load this script and all have a <main>). Off-screen until a
// keyboard user tabs to it (styled in app.css); it targets the main landmark.
(function () {
  try {
    if (document.querySelector("a.skip-link")) return;
    const main = document.querySelector("main");
    if (!main) return;
    if (!main.id) main.id = "main-content";
    const link = document.createElement("a");
    link.className = "skip-link";
    link.href = "#" + main.id;
    link.textContent = "Skip to content";
    document.body.insertBefore(link, document.body.firstChild);
  } catch (e) { /* non-critical enhancement */ }
})();
