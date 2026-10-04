const id = location.pathname.split("/").pop();
const tok = new URLSearchParams(location.search).get("t");
const q = (extra) => (tok ? "?t=" + encodeURIComponent(tok) + (extra ? "&" + extra : "") : extra ? "?" + extra : "");
const S = { seg: null, player: null, log: null };

function chart(perS, roll) {
  const W = 1000, H = 160, n = Math.max(1, perS.length), mx = Math.max(...perS, 1);
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart"); svg.setAttribute("preserveAspectRatio", "none");
  perS.forEach((v, i) => { const r = document.createElementNS(NS, "rect"); const bh = (H - 4) * v / mx;
    r.setAttribute("x", (i * W) / n); r.setAttribute("y", H - bh); r.setAttribute("width", Math.max(1, W / n - 1)); r.setAttribute("height", bh); r.setAttribute("fill", "#2c6f8f"); svg.append(r); });
  const p = document.createElementNS(NS, "polyline");
  p.setAttribute("points", roll.map((v, i) => `${(i + 0.5) * W / n},${H - (H - 4) * v / mx}`).join(" "));
  p.setAttribute("fill", "none"); p.setAttribute("stroke", "#e8cf8e"); p.setAttribute("stroke-width", "2");
  svg.append(p);
  return svg;
}

async function showPlayer() {
  const out = $("#player");
  out.replaceChildren(h("div", { class: "empty" }, "Loading…"));
  const a = await getJSON(`/api/v1/logs/${id}/analysis` + q(`segment=${S.seg}&player=${encodeURIComponent(S.player)}`));
  const s = a.summary, m = a.meta;
  const kp = [["DPS", n0(s.dps)], ["Damage", n0(s.total)], ["Duration", Math.round(s.duration) + " s"], ["Casts / min", s.cpm.toFixed(0)],
    ["Crit", pct(s.crit)], ["Double", pct(s.double)], ["Perfect", pct(s.perfect)], ["Multi-hit", pct(s.multi)], ["Back", pct(s.back)], ["Idle", s.idle_seconds.toFixed(1) + " s"]];
  const mxs = Math.max(...a.skills.map((r) => r.share), 0.0001);
  out.replaceChildren(
    win(`${m.player}`, `${cap(m.class || "")} · ${m.target || ""}`,
      h("div", { class: "kpis" }, kp.map(([k, v]) => h("div", { class: "kpi" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v)))),
      chart(a.timeline.per_second, a.timeline.rolling10),
      h("div", { class: "row small muted" }, h("span", {}, "bars: damage per second"), h("span", {}, "line: 10 s average"))),
    win("Damage by skill", "", table(["Skill", "Share", ">Casts", ">Hits", ">Crit", ">Double", ">Perfect", ">Avg hit", ">Max hit"], a.skills.map((r) =>
      h("tr", {}, h("td", {}, r.skill), h("td", { class: "w22" }, bar(r.share / mxs, pct(r.share))), h("td", { class: "r" }, r.kind === "passive" ? "proc" : r.casts),
        h("td", { class: "r" }, r.hits), h("td", { class: "r" }, pct(r.crit, 0)), h("td", { class: "r" }, pct(r.double, 0)), h("td", { class: "r" }, pct(r.perfect, 0)),
        h("td", { class: "r num" }, n0(r.avg_hit)), h("td", { class: "r num" }, n0(r.max_hit)))))),
    h("div", { class: "grid2" },
      win("Opening rotation", "first casts", h("div", { class: "rot" }, a.rotation.map(([t, k]) => h("div", { class: "r" }, h("span", { class: "faint" }, t.toFixed(1)), " ", k)))),
      win("Buff uptime", "", table(["Buff", "Uptime"], a.buffs.slice(0, 20).map((b) => h("tr", {}, h("td", {}, b.name), h("td", {}, bar(b.uptime || 0, pct(b.uptime, 0), true))))),
        Object.keys(a.specs || {}).length ? h("div", { class: "small", }, h("h4", { class: "gold small" }, "SPECIALIZATIONS"),
          Object.entries(a.specs).map(([k, v]) => h("div", {}, `${k}: ${v}`))) : null)));
}

function showSegment() {
  const seg = S.log.segments[S.seg];
  const box = $("#seg");
  const mx = Math.max(...seg.players.map((p) => p.share), 0.0001);
  box.replaceChildren(win(seg.label || seg.boss || "Segment", `${Math.round(seg.duration)} s${seg.killed ? " · killed" : ""}`,
    h("table", { class: "t ptable" }, h("tr", {}, ["Player", "Class", "DPS", "Damage", "Share", "Crit"].map((x, i) => h("th", { class: i > 1 ? "r" : null }, x))),
      seg.players.map((p) => h("tr", { class: p.id === S.player ? "sel" : null, on: { click: () => { S.player = p.id; showSegment(); showPlayer(); } } },
        h("td", {}, p.name), h("td", { class: "muted" }, cap(p.class || "")), h("td", { class: "r num" }, n0(p.dps)), h("td", { class: "r num" }, n0(p.damage)),
        h("td", { class: "r w22" }, bar(p.share / mx, pct(p.share))), h("td", { class: "r" }, pct(p.crit, 0))))),
    h("p", { class: "small faint" }, "Click a player for the breakdown.")));
}

async function main() {
  const L = (S.log = await getJSON(`/api/v1/logs/${id}` + q()));
  const main = L.segments.reduce((b, s, i) => (s.boss && s.duration > (L.segments[b].duration || 0) ? i : b), 0);
  S.seg = main;
  S.player = (L.segments[main].players[0] || L.roster[0]).id;
  const meta = L.meta || {};
  $("#app").replaceChildren(
    win(L.title || "Fight", [meta.region && meta.region.toUpperCase(), meta.recorded_at && new Date(meta.recorded_at).toLocaleString(), meta.source && "from " + meta.source, L.visibility].filter(Boolean).join(" · "),
      L.segments.length > 1 ? h("div", { class: "chips" }, L.segments.map((s, i) => h("button", { class: "btn small" + (i === S.seg ? " primary" : ""), on: { click: (e) => {
        S.seg = i; S.player = (s.players[0] || L.roster[0]).id; document.querySelectorAll(".chips .btn").forEach((b) => b.classList.remove("primary")); e.target.classList.add("primary"); showSegment(); showPlayer(); } } },
        `${s.label || s.boss || "Segment " + (i + 1)} (${Math.round(s.duration)}s)`))) : null,
      h("div", { class: "row small" }, h("a", { href: `/api/v1/logs/${id}/raw` + q() }, "download JSON (a2log)"), h("a", { href: "/docs" }, "about the format"))),
    h("div", { id: "seg" }), h("div", { id: "player" }));
  showSegment();
  await showPlayer();
}
main().catch((e) => $("#app").replaceChildren(h("div", { class: "note" }, e.message)));
