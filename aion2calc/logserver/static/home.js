async function load() {
  const boss = $("#boss").value.trim();
  const j = await getJSON("/api/v1/logs?limit=50" + (boss ? "&boss=" + encodeURIComponent(boss) : ""));
  const list = $("#list");
  list.replaceChildren();
  if (!j.logs.length) { list.append(h("div", { class: "faint small" }, "No public logs yet.")); return; }
  list.append(table(["Fight", "Players", "Top", ">Top DPS", ">Duration", "Uploaded"], j.logs.map((l) => {
    const top = l.players[0] || {};
    return h("tr", { class: "click", on: { click: () => (location.href = "/l/" + l.id) } },
      h("td", {}, h("a", { href: "/l/" + l.id }, l.title || l.boss || "Fight")), h("td", {}, l.players.length),
      h("td", {}, `${top.name || ""} `, h("span", { class: "faint" }, cap(top.class || ""))), h("td", { class: "r num" }, n0(l.top_dps)),
      h("td", { class: "r" }, Math.round(l.duration) + "s"), h("td", { class: "muted small" }, ago(l.created_at)));
  })));
}
$("#boss").addEventListener("change", load);
load().catch((e) => $("#list").replaceChildren(h("div", { class: "note" }, e.message)));
