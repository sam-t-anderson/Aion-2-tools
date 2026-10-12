/* Shared regional event-schedule engine: the DST-aware occurrence calculation and
   countdown formatting used by both the Timers page (timers.js) and the overlay's
   event-notification strip (overlay.js). Community forecasts only — a computed
   schedule window is never live status. No DOM here; pure time math over the
   bundled event-schedules.json catalog. */
(function () {
  'use strict';

  // All real local wall-clock occurrences of an event across a short horizon, in a
  // given IANA zone, handling DST (skips nonexistent wall times, keeps repeated
  // ones). Identical to the Timers-page logic — kept here as the single source.
  function occurrences(event, zone, now, cache) {
    const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    const parts = t => Object.fromEntries(formatter.formatToParts(new Date(t)).filter(p => p.type !== 'literal').map(p => [p.type, Number(p.value)]));
    const here = parts(now), result = [];
    for (let delta = -1; delta <= 8; delta++) {
      const day = new Date(Date.UTC(here.year, here.month - 1, here.day + delta));
      if (event.days && !event.days.includes(day.getUTCDay())) continue;
      const base = day.getTime(), key = zone + ':' + base;
      if (!cache.has(key)) {
        const offsets = new Set();
        for (const h of [-24, 0, 12, 24, 48]) {
          const t = base + h * 3600000, p = parts(t);
          offsets.add(Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - t);
        }
        cache.set(key, [...offsets]);
      }
      for (const hour of event.hours) {
        const wall = base + (hour * 60 + event.minute) * 60000;
        for (const offset of cache.get(key)) {
          const t = wall - offset, p = parts(t);
          if (Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) === wall) result.push(t);
        }
      }
    }
    return [...new Set(result)].sort((a, b) => a - b);
  }

  const countdown = ms => { const s = Math.max(0, Math.ceil(ms / 1000)); return `${Math.floor(s / 86400) ? Math.floor(s / 86400) + 'd ' : ''}${String(Math.floor(s / 3600) % 24).padStart(2, '0')}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };

  // A compact countdown for the overlay: "5m", "1h 05m", or "45s".
  const shortCountdown = ms => {
    const s = Math.max(0, Math.ceil(ms / 1000));
    if (s >= 3600) return Math.floor(s / 3600) + 'h ' + String(Math.floor(s / 60) % 60).padStart(2, '0') + 'm';
    if (s >= 60) return Math.floor(s / 60) + 'm';
    return s + 's';
  };

  // Resolve every event for a region/group to its catalog form (applying region
  // overrides and the Korean matching-group time), skipping ones a group has not
  // been chosen for. Mirrors timers.js prepare() without the DOM.
  function resolveEvents(catalog, region, group) {
    const r = (catalog.regions || []).find(x => x.id === region);
    if (!r) return [];
    const out = [];
    for (const raw of catalog.events || []) {
      const event = { ...raw, ...(((catalog.overrides || {})[region] || {})[raw.id] || {}) };
      const unavailable = !!event.group_times && !['1', '2', '3'].includes(String(group));
      if (unavailable) continue;
      if (event.group_times) { const [h, m] = event.group_times[Number(group) - 1].split(':').map(Number); event.hours = [h]; event.minute = m; }
      out.push({ event, zone: event.timezone || r.timezone });
    }
    return out;
  }

  // Normalized event states for display, sorted active-first then soonest-start.
  // Each: {id, name, disputed, zone, active, entryOpen, endsAt, next, startsInMs}.
  function upcoming(catalog, region, group, now) {
    const cache = new Map();
    return resolveEvents(catalog, region, group).map(({ event, zone }) => {
      const times = occurrences(event, zone, now, cache);
      const active = times.filter(t => t <= now && now < t + event.duration_minutes * 60000).at(-1);
      const next = times.find(t => t > now);
      const entryEnd = active === undefined ? null : active + (event.entry_minutes || 0) * 60000;
      const isActive = active !== undefined;
      return {
        id: event.id, name: event.name, disputed: !!event.disputed, zone,
        active: isActive,
        entryOpen: isActive && event.entry_minutes ? now < entryEnd : isActive,
        endsAt: isActive ? (event.entry_minutes && now < entryEnd ? entryEnd : active + event.duration_minutes * 60000) : null,
        next: next === undefined ? null : next,
        startsInMs: next === undefined ? null : next - now,
      };
    }).sort((a, b) => {
      if (a.active !== b.active) return a.active ? -1 : 1;
      if (a.active && b.active) return (a.endsAt || 0) - (b.endsAt || 0);
      return (a.startsInMs == null ? Infinity : a.startsInMs) - (b.startsInMs == null ? Infinity : b.startsInMs);
    });
  }

  // The region/group the player picked on the Timers page (same-origin localStorage,
  // shared with the overlay window). {region, group} or empty strings.
  function savedRegion() {
    try { const p = JSON.parse(localStorage.getItem('a2-event-region') || '{}'); return { region: p.region || '', group: p.group || '' }; }
    catch (_) { return { region: '', group: '' }; }
  }

  window.A2EventSchedule = { occurrences, countdown, shortCountdown, resolveEvents, upcoming, savedRegion };
})();
