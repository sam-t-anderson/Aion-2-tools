/* Community NPC name + portrait overlay. Fetches the log server's scraped map
   (aion2logs `portraits` job -> /api/v1/npc-portraits) and merges it as a FALLBACK
   behind the curated bundled table, never overwriting one:
     * portraits merge into window.A2BundledAssets.npcs (only ids with no bundled art);
     * names populate window.A2CommunityNames {id: name} so the UI can show a real
       name for an id the catalog doesn't map yet (shown as "#<code>" otherwise).
   Community-sourced and id-matched, not an official mapping; images hotlink from the
   source and render through A2AssetHealth.source (host-allowlisted). Best-effort and
   silent: any failure leaves the bundled portraits and names exactly as they were. */
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
    const names = (window.A2CommunityNames = window.A2CommunityNames || {});
    let added = 0, namesAdded = 0;
    for (const id of Object.keys(rows)) {
      const row = rows[id];
      const icon = row && typeof row === 'object' ? row.icon : row;
      const name = row && typeof row === 'object' ? row.name : null;
      if (typeof icon === 'string' && icon && !bundled.npcs[id]) { bundled.npcs[id] = icon; added++; }
      if (typeof name === 'string' && name && !names[id]) { names[id] = name; namesAdded++; }
    }
    window.A2CommunityPortraits = { added: added, names: namesAdded, source: 'community_unverified' };
    // Let an already-rendered page pick the new art/names up without a reload.
    if ((added || namesAdded) && typeof window.A2NpcPortraitsLoaded === 'function') {
      try { window.A2NpcPortraitsLoaded(added); } catch (_) {}
    }
  }
  load();
})();
