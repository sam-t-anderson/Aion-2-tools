// Shared helper for the public pages: resolve the share server and call its API.
//
// The server address comes from, in order: the visitor's own saved choice (localStorage, set on the
// Raid Planner), the baked-in default from config.js (the repo's A2LOGS_PUBLIC_URL at build time), or
// the project's live default_server.json on GitHub. Reading the live file last means a changed server
// address (for example, a moved Tailscale Funnel endpoint) reaches the site by editing one file — no rebuild,
// the same file the desktop app reads. If a request fails outright we refresh from that live file once
// and retry, and errors say what actually went wrong instead of a bare "Failed to fetch".
window.A2 = (function () {
  "use strict";
  const LS = "a2server";
  const RETIRED_QUICK_TUNNEL = "try" + "cloudflare.com";
  const DEFAULT = (window.A2CONFIG || {});
  const LIVE_DEFAULT_URL = "https://raw.githubusercontent.com/sam-t-anderson/Aion-2-tools/main/aion2calc/data/global/default_server.json";
  let resolved = null;            // the base URL we settled on
  let triedLive = false;          // have we already consulted the live default this session?

  // Parse the URL and test the real host, so a string that merely *contains*
  // "trycloudflare.com" elsewhere (path, query, a look-alike host) is not mistaken
  // for the retired quick-tunnel endpoint.
  function isRetired(u) {
    try {
      const h = new URL(u).hostname.toLowerCase();
      return h === RETIRED_QUICK_TUNNEL || h.endsWith("." + RETIRED_QUICK_TUNNEL);
    } catch (e) { return false; }
  }
  // A share-server base is used only if it is a well-formed http(s) URL; anything
  // else (javascript:, data:, garbage) resolves to no server rather than a fetch.
  // Return the reparsed origin+path so every request is built from a validated URL.
  function validBase(u) {
    const c = clean(u);
    if (!c) return "";
    try {
      const x = new URL(c);
      if (x.protocol !== "https:" && x.protocol !== "http:") return "";
      return clean(x.origin + x.pathname);
    } catch (e) { return ""; }
  }

  function saved() {
    try {
      const s = JSON.parse(localStorage.getItem(LS) || "null");
      if (s && isRetired(s.url || "")) { localStorage.removeItem(LS); return null; }
      if (s && (s.url || s.key)) return s;
    } catch (e) { /* ignore */ }
    return null;
  }
  function cfg() {
    const choice=saved();
    if(!choice)return {url:DEFAULT.server||"",key:DEFAULT.key||""};
    const url=choice.url||DEFAULT.server||"";
    return {...choice,url,key:choice.key||(clean(url)===clean(DEFAULT.server)?DEFAULT.key||"":"")};
  }
  function clean(u) { return (u || "").replace(/\/+$/, ""); }

  async function liveDefault() {
    triedLive = true;
    try {
      const r = await fetch(LIVE_DEFAULT_URL, { cache: "no-store" });
      if (r.ok) { const j = await r.json(); return isRetired(j.url || "") ? "" : validBase(j.url || ""); }
    } catch (e) { /* offline or blocked: nothing to add */ }
    return "";
  }

  async function ensureBase() {
    if (resolved) return resolved;
    resolved = validBase(cfg().url);
    if (!resolved && !triedLive) resolved = await liveDefault();
    return resolved;
  }

  function base() { return resolved || validBase(cfg().url); }

  async function api(path) {
    let b = await ensureBase();
    if (!b) throw new Error("No share server is set up for this site yet. Open the Raid Planner and set one, or ask the site owner to configure A2LOGS_PUBLIC_URL.");
    if (location.protocol === "https:" && b.startsWith("http://")) {
      throw new Error("The share server address is " + b + " (http), but this site is https, so the browser blocks it. Use the configured HTTPS Tailscale address.");
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
        if (networkFail) throw new Error("Can't reach the share server at " + b + ". It may be offline, or its Tailscale address changed. The live project default is retried automatically.");
        throw e;
      }
    }
  }
  return { cfg, base, api };
})();
