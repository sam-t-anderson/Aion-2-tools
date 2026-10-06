// Standalone raid planner (GitHub Pages). Mounts the shared planner (raid.js) and wires Publish /
// Browse to a self-hosted aion2calc log server the visitor points at. The server is stored only in
// this browser; its API sends CORS headers so cross-origin publish/browse work.
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const LS = "a2server";
  // A default server (and optional upload key) can be baked in at Pages build from repo variables
  // (config.js -> window.A2CONFIG). The visitor's own entry, if any, overrides it.
  const DEFAULT = (window.A2CONFIG || {});
  const cfg = () => {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(LS) || "null"); } catch (e) { saved = null; }
    if (saved && (saved.url || saved.key)) return saved;
    return { url: DEFAULT.server || "", key: DEFAULT.key || "" };
  };
  const base = () => (cfg().url || "").replace(/\/+$/, "");

  async function apiGET(path) {
    const r = await fetch(base() + path);
    const j = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  }

  const io = {
    server: base,
    refresh: async owner=>{if(owner.server!==base())throw Error("Select the original publication server first");const headers={"X-Plan-Token":owner.edit_token};const get=async path=>{const r=await fetch(base()+path,{headers,cache:"no-store"});const j=await r.json();if(!r.ok)throw Error(j.error||r.statusText);return j;};const summary=await get("/api/v1/plans/"+owner.id);return {plan:await get("/api/v1/plans/"+owner.id+"/raw"),revision:summary.revision};},
    publish: async (plan, vis, owner) => {
      if (!base()) throw new Error("Set your share server at the top of the page first.");
      const headers = { "Content-Type": "application/json" };
      const key = cfg().key;
      if (key) headers.Authorization = "Bearer " + key;
      if(owner){if(owner.server!==base())throw Error('Select the original publication server first');headers['X-Plan-Token']=owner.edit_token;headers['If-Match']=String(owner.revision);}
      const r = await fetch(`${base()}/api/v1/plans${owner?'/'+owner.id:''}?visibility=${encodeURIComponent(vis)}`, { method: owner?'PUT':'POST', headers, body: JSON.stringify(plan) });
      const j = await r.json().catch(() => ({ error: r.statusText }));
      if (!r.ok || j.error) throw new Error(j.error || r.statusText);
      return j;
    },
    browse: async () => {
      if (!base()) throw new Error("Set your share server at the top of the page first.");
      return (await apiGET("/api/v1/plans")).plans;
    },
    fetchPlan: async (id) => apiGET(`/api/v1/plans/${id}/raw`),
  };

  // theme toggle (mirrors the app's three-way switch, stored per browser)
  const THEMES = ["system", "light", "dark"];
  const getTheme = () => { try { return localStorage.getItem("theme") || "system"; } catch (e) { return "system"; } };
  function setTheme(t) {
    try { localStorage.setItem("theme", t); } catch (e) {}
    if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
    const b = $("#theme"); if (b) b.textContent = { system: "◐", light: "☀", dark: "☾" }[t];
  }
  if ($("#theme")) $("#theme").onclick = () => setTheme(THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length]);
  setTheme(getTheme());

  // server config
  const c = cfg();
  let usingDefault = true;
  try { const s = JSON.parse(localStorage.getItem(LS) || "null"); usingDefault = !(s && (s.url || s.key)); } catch (e) { usingDefault = true; }
  if ($("#srvurl")) $("#srvurl").value = c.url || "";
  if ($("#srvkey") && c.key) $("#srvkey").placeholder = "key saved";
  if ($("#srvmsg")) $("#srvmsg").textContent = base()
    ? `publishing to ${base()}${usingDefault ? " (community default)" : ""}`
    : "publish/browse disabled until you set a server";
  if ($("#srvsave")) $("#srvsave").onclick = async () => {
    const url = $("#srvurl").value.trim().replace(/\/+$/, "");
    const key = $("#srvkey").value || cfg().key || "";
    localStorage.setItem(LS, JSON.stringify({ url, key }));
    $("#srvkey").value = "";
    const msg = $("#srvmsg");
    if (!url) { if (msg) msg.textContent = "publish/browse disabled until you set a server"; return; }
    if (msg) msg.textContent = "checking…";
    try { const r = await fetch(url + "/.well-known/a2log.json"); if (msg) msg.textContent = r.ok ? "server reachable — publishing to " + url : "saved · server did not answer"; }
    catch (e) { if (msg) msg.textContent = "saved · server not reachable from this browser"; }
  };

  // plans.html links here as planner.html?plan=<id>; fetch that published plan and make it current
  async function maybeLoadShared() {
    const id = new URLSearchParams(location.search).get("plan");
    if (!id || !base()) return;
    try {
      const entries=JSON.parse(localStorage.getItem('a2plan-owners')||'{}');
      const own=Object.entries(entries).find(([,o])=>o.id===id && o.server===base());
      if(own)return; // Keep the owned local copy and its unpublished edits.
      const token=new URLSearchParams(location.search).get('t');
      const doc = await apiGET(`/api/v1/plans/${encodeURIComponent(id)}/raw`+(token?'?t='+encodeURIComponent(token):''));
      if (doc && doc.format === "a2plan") {
        let all = {};
        try { all = JSON.parse(localStorage.getItem("a2plans") || "{}"); } catch (e) { all = {}; }
        doc.meta = doc.meta || {}; doc.meta.updated = Date.now();
        all["shared-" + id] = doc;
        localStorage.setItem("a2plans", JSON.stringify(all));
      }
    } catch (e) { /* open the planner normally if the fetch fails */ }
  }

  (async () => { await maybeLoadShared(); window.A2Raid.mount(document.getElementById("app"), io); })();
})();
