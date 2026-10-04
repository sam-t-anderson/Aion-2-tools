// Class statistics learned from every public and unlisted upload (anonymous).
const params = new URLSearchParams(location.search);
async function main() {
  const idx = await getJSON("/api/v1/stats");
  const app = $("#app");
  if (!idx.classes.length) { app.replaceChildren(win("Class statistics", "", h("p", { class: "muted" }, "No fights uploaded yet."))); return; }
  const cls = params.get("class") || idx.classes[0].class;
  const boss = params.get("boss") || "";
  const go = (c, b) => { const u = new URLSearchParams(); u.set("class", c); if (b) u.set("boss", b); location.search = u.toString(); };
  const [s, cal] = await Promise.all([getJSON(`/api/v1/stats/${cls}` + (boss ? "?boss=" + encodeURIComponent(boss) : "")), getJSON(`/api/v1/calibration/${cls}`)]);
  const picker = h("div", { class: "chips" }, idx.classes.map((c) => h("button", { class: "btn small" + (c.class === cls ? " primary" : ""), on: { click: () => go(c.class, "") } },
    `${cap(c.class)} (${c.observations})`)));
  const bosses = h("div", { class: "chips" }, h("button", { class: "btn small" + (!boss ? " primary" : ""), on: { click: () => go(cls, "") } }, "all fights"),
    (s.bosses || []).map(([b, n]) => h("button", { class: "btn small" + (b === boss ? " primary" : ""), on: { click: () => go(cls, b) } }, `${b} (${n})`)));
  if (!s.observations) { app.replaceChildren(win("Class statistics", "", picker, bosses, h("p", { class: "muted" }, "No data for this selection."))); return; }
  const kp = [["Players", s.observations], ["Median DPS", n0(s.dps.median)], ["Top 25% from", n0(s.dps.p75)], ["Top 10% from", n0(s.dps.p90)],
    ["Crit", pct(s.rates.crit)], ["Double", pct(s.rates.double)], ["Perfect", pct(s.rates.perfect)], ["Casts / min", s.tempo.cpm.toFixed(0)],
    ["Idle (all)", pct(s.tempo.idle_share)], ["Idle (top 25%)", pct(s.top_quarter.tempo.idle_share)]];
  const mx = Math.max(...s.top_quarter.skills.map((r) => r.share), 0.0001);
  const allShare = Object.fromEntries(s.all.skills.map((r) => [r.skill, r.share]));
  app.replaceChildren(
    win("Class statistics", "learned from every public and unlisted upload; no names are kept", picker, bosses,
      h("div", { class: "kpis" }, kp.map(([k, v]) => h("div", { class: "kpi" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v))))),
    h("div", { class: "grid2" },
      win("Top 25% of players: damage by skill", "median share and casts per minute",
        table(["Skill", "Share (top 25%)", ">All players", ">Casts / min", ">Used by"], s.top_quarter.skills.map((r) =>
          h("tr", {}, h("td", {}, r.skill), h("td", { class: "w22" }, bar(r.share / mx, pct(r.share))), h("td", { class: "r" }, pct(allShare[r.skill] ?? 0)),
            h("td", { class: "r" }, r.cpm.toFixed(1)), h("td", { class: "r" }, pct(r.used_by, 0)))))),
      win("Top 25% of players: specializations", "most picked slots per skill",
        table(["Skill", "Picks", ">Players"], s.top_quarter.specs.map((r) => h("tr", {}, h("td", {}, r.skill),
          h("td", {}, r.picks.map((p) => `${p.specs} (${pct(p.share, 0)})`).join(" · ")), h("td", { class: "r" }, r.players)))))),
    h("div", { class: "grid2" },
      win("DPS by combat power", "median per 10k bracket", table(["Combat power", ">Players", ">Median DPS"], s.by_combat_power.map((b) =>
        h("tr", {}, h("td", {}, `${n0(b.from)}–${n0(b.to)}`), h("td", { class: "r" }, b.players), h("td", { class: "r num" }, n0(b.median_dps)))))),
      win("Community calibration", `${cal.fights} fights${cal.active ? "" : " (turns on at 5)"} · ${cal.with_stats || 0} with stats`,
        h("p", { class: "small faint" }, "aion2calc apps can use this as a starting point for their simulations: GET /api/v1/calibration/" + cls),
        table(["Skill", ">Damage factor"], Object.entries(cal.skills || {}).sort((a, b) => Math.abs(b[1] - 1) - Math.abs(a[1] - 1)).slice(0, 12).map(([k, v]) =>
          h("tr", {}, h("td", {}, k), h("td", { class: "r num" }, v.toFixed(2) + "×")))),
        Object.keys(cal.rates || {}).length ? h("p", { class: "small" }, Object.entries(cal.rates).map(([k, v]) => `${k} ${v.toFixed(2)}×`).join(" · ")) : null)));
}
main().catch((e) => $("#app").replaceChildren(h("div", { class: "note" }, e.message)));
