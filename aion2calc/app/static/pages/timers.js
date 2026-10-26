/* Timers (#/timers): timers.js, with the field bosses the Live Meter has seen. */
"use strict";

let eventTimerView = null;
async function pageTimers() {
  app().innerHTML = '<div id="event-timers"></div>';
  eventTimerView = A2Timers.mount($("#event-timers"), {
    api: communityAPI,
    identity: async () => {
      const m = await api("/api/meter?view=latest");
      return (m && m.snapshot && m.snapshot.field_bosses) || null;
    },
    logURL: (id, segment) =>
      "#/combat-log/shared/" +
      encodeURIComponent(id) +
      "?mode=pve" +
      (Number.isInteger(segment) ? "&segment=" + segment : ""),
  });
}
