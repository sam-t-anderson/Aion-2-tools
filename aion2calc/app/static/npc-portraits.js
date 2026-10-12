/* Community NPC portrait overlay. Fetches the log server's scraped portrait map
   (aion2logs `portraits` job -> /api/v1/npc-portraits) and merges it into
   window.A2BundledAssets.npcs as a FALLBACK — only for NPC ids the curated
   bundled table has no art for, never overwriting one. Community-sourced and
   name/id-matched, not an official mapping; images hotlink from the source and
   render through A2AssetHealth.source (host-allowlisted). Best-effort and silent:
   any failure leaves the bundled portraits exactly as they were. */
(function () {
  'use strict';
  const bundled = (window.A2BundledAssets = window.A2BundledAssets || { npcs: {}, files: {}, base: location.href });
  if (!bundled.npcs) bundled.npcs = {};
  // Same-origin on server-hosted log pages; the client app has no such route, so
  // fall back to its community proxy, which reads the configured log server.
  const endpoints = ['/api/v1/npc-portraits', '/api/community?path=' + encodeURIComponent('/api/v1/npc-portraits')];
  async function load() {
    let doc = null;
    for (const url of endpoints) {
      try {
        const r = await fetch(url, { cache: 'no-store', credentials: 'omit' });
        if (r.ok) { doc = await r.json(); break; }
      } catch (_) { /* try the next endpoint */ }
    }
    const rows = doc && (doc.portraits || (typeof doc === 'object' && !Array.isArray(doc) ? doc : null));
    if (!rows || typeof rows !== 'object') return;
    let added = 0;
    for (const id of Object.keys(rows)) {
      const row = rows[id], icon = row && typeof row === 'object' ? row.icon : row;
      if (typeof icon === 'string' && icon && !bundled.npcs[id]) { bundled.npcs[id] = icon; added++; }
    }
    window.A2CommunityPortraits = { added: added, source: 'community_unverified' };
    // Let an already-rendered page pick the new art up without a reload.
    if (added && typeof window.A2NpcPortraitsLoaded === 'function') { try { window.A2NpcPortraitsLoaded(added); } catch (_) {} }
  }
  load();
})();
