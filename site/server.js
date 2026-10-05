// Shared helper for the public pages: resolve the share server and call its API.
//
// The server address comes from, in order: the visitor's own saved choice (localStorage, set on the
// Raid Planner), the baked-in default from config.js (the repo's A2LOGS_PUBLIC_URL at build time), or
// the project's live default_server.json on GitHub. Reading the live file last means a changed server
// address (e.g. a new Cloudflare quick-tunnel URL) reaches the site by editing one file — no rebuild,
// the same file the desktop app reads. If a request fails outright we refresh from that live file once
// and retry, and errors say what actually went wrong instead of a bare "Failed to fetch".
window.A2 = (function () {
  "use strict";
  const LS = "a2server";
  const DEFAULT = (window.A2CONFIG || {});
  const LIVE_DEFAULT_URL = "https://raw.githubusercontent.com/sam-t-anderson/Aion-2-tools/main/aion2calc/data/global/default_server.json";
  let resolved = null;            // the base URL we settled on
  let triedLive = false;          // have we already consulted the live default this session?

  function saved() {
    try { const s = JSON.parse(localStorage.getItem(LS) || "null"); if (s && (s.url || s.key)) return s; } catch (e) { /* ignore */ }
    return null;
  }
  function cfg() { return saved() || { url: DEFAULT.server || "", key: DEFAULT.key || "" }; }
  function clean(u) { return (u || "").replace(/\/+$/, ""); }

  async function liveDefault() {
    triedLive = true;
    try {
      const r = await fetch(LIVE_DEFAULT_URL, { cache: "no-store" });
      if (r.ok) { const j = await r.json(); return clean(j.url || ""); }
    } catch (e) { /* offline or blocked: nothing to add */ }
    return "";
  }

  async function ensureBase() {
    if (resolved) return resolved;
    resolved = clean(cfg().url);
    if (!resolved && !triedLive) resolved = await liveDefault();
    return resolved;
  }

  function base() { return resolved || clean(cfg().url); }

  async function api(path) {
    let b = await ensureBase();
    if (!b) throw new Error("No share server is set up for this site yet. Open the Raid Planner and set one, or ask the site owner to configure A2LOGS_PUBLIC_URL.");
    if (location.protocol === "https:" && b.startsWith("http://")) {
      throw new Error("The share server address is " + b + " (http), but this site is https, so the browser blocks it. Use an https address (a Cloudflare Tunnel gives you one).");
    }
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const r = await fetch(b + path);
        const j = await r.json().catch(() => ({ error: r.statusText }));
        if (!r.ok || j.error) throw new Error(j.error || r.statusText);
        return j;
      } catch (e) {
        const networkFail = (e instanceof TypeError);     // DNS/offline/expired tunnel/CORS -> "Failed to fetch"
        if (networkFail && !triedLive) {                  // the baked address may be stale: try the live default once
          const live = await liveDefault();
          if (live && live !== b) { resolved = b = live; continue; }
        }
        if (networkFail) throw new Error("Can't reach the share server at " + b + ". It may be offline, or its address changed (a Cloudflare quick tunnel gets a new URL every restart — use a named tunnel for a stable one).");
        throw e;
      }
    }
  }
  return { cfg, base, api };
})();
