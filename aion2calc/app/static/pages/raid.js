/* Raid Planner (#/raid). The raid & boss planner is a shared module (static/raid.js), used here and on the
   planner site. In the app it is wired to your saved combat logs so a fight can be overlaid on the plan's
   timeline. */
"use strict";

async function pageRaid() {
  const shown = stillShown();
  const publicationServer=await api("/api/logserver");
  if (!shown()) return;
  await window.A2Raid.mount(app(), {
    encounters: () => api("/api/encounters"),
    encounter: (id) => api("/api/encounters/" + id),
    server:()=>publicationServer.url.replace(/\/+$/, ""),
    publish: (plan, visibility, owner) => api("/api/plans", {plan, visibility,owner}),
    refresh:owner=>api("/api/plans",{id:owner.id,owner}),
    browse: async (filter) => {
      const q = [];
      if (filter && filter.npc) q.push("npc=" + encodeURIComponent(filter.npc));
      else if (filter && filter.boss) q.push("boss=" + encodeURIComponent(filter.boss));
      return (await api("/api/plans" + (q.length ? "?" + q.join("&") : ""))).plans;
    },
    bosses: async () => (await api("/api/plans/bosses")).bosses || [],
    fetchPlan: (id) => api("/api/plans?id=" + encodeURIComponent(id)),
  });
}
