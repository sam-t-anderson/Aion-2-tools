// Shared helper for the public pages: resolve the share server (baked-in default from config.js, or
// the visitor's own saved choice) and call its API. Same localStorage key the planner uses.
window.A2 = (function () {
  const LS = "a2server";
  const DEFAULT = (window.A2CONFIG || {});
  function cfg() {
    try { const s = JSON.parse(localStorage.getItem(LS) || "null"); if (s && (s.url || s.key)) return s; } catch (e) { /* ignore */ }
    return { url: DEFAULT.server || "", key: DEFAULT.key || "" };
  }
  function base() { return (cfg().url || "").replace(/\/+$/, ""); }
  async function api(path) {
    if (!base()) throw new Error("No server configured yet. Open the Raid Planner and set a share server, or ask the site owner to configure one.");
    const r = await fetch(base() + path);
    const j = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  }
  return { cfg, base, api };
})();
