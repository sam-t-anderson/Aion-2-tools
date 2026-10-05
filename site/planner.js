// Standalone raid planner (GitHub Pages). Mounts the shared planner (raid.js) and wires Publish /
// Browse to a self-hosted aion2calc log server the visitor points at. The server is stored only in
// this browser; its API sends CORS headers so cross-origin publish/browse work.
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const LS = "a2server";
  const cfg = () => { try { return JSON.parse(localStorage.getItem(LS) || "{}"); } catch (e) { return {}; } }
  const base = () => (cfg().url || "").replace(/\/+$/, "");

  async function apiGET(path) {
    const r = await fetch(base() + path);
    const j = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  }

  const io = {
    publish: async (plan, vis) => {
      if (!base()) throw new Error("Set your share server at the top of the page first.");
      const headers = { "Content-Type": "application/json" };
      const key = cfg().key;
      if (key) headers.Authorization = "Bearer " + key;
      const r = await fetch(`${base()}/api/v1/plans?visibility=${encodeURIComponent(vis)}`, { method: "POST", headers, body: JSON.stringify(plan) });
      const j = await r.json().catch(() => ({ error: r.statusText }));
      if (!r.ok || j.error) throw new Error(j.error || r.statusText);
      return { url: j.url };
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
  if ($("#srvurl")) $("#srvurl").value = c.url || "";
  if ($("#srvkey") && c.key) $("#srvkey").placeholder = "key saved";
  if ($("#srvmsg")) $("#srvmsg").textContent = base() ? "publishing to " + base() : "publish/browse disabled until you set a server";
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

  window.A2Raid.mount(document.getElementById("app"), io);
})();
