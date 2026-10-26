/* Database (#/database): the game database's updates and the item catalog. */
"use strict";

async function pageDatabase() {
  app().innerHTML = `<section class="win"><div class="wh"><h2>Game database</h2><span class="sub">updates itself on every launch from the live sources — no code changes needed for new items, skills or classes</span>
    <div class="tools"><button class="btn" id="sync">Check for updates</button><button class="btn small" id="full">Full re-sync</button></div></div><div class="wb" id="dbs"></div></section>
    <section class="win"><div class="wh"><h2>Item catalog</h2></div><div class="wb"><div class="row"><input id="q" type="text" placeholder="search items"><select id="cat" aria-label="Category"><option value="">all categories</option></select>
      <button class="btn" id="srch">Search</button></div><div id="items" style="margin-top:10px"></div><div id="item"></div></div></section>`;
  const show = async () => {
    const s = await api("/api/status");
    const sy = s.sync,
      db = s.db,
      last = db.last_sync;
    $("#dbs").innerHTML =
      `<div class="kpis"><div class="kpi"><div class="k">Items</div><div class="v">${n0(db.items)}</div></div>
      <div class="kpi"><div class="k">Characters</div><div class="v">${db.characters}</div></div><div class="kpi"><div class="k">Encounters</div><div class="v">${db.encounters}</div></div>
      <div class="kpi"><div class="k">Last sync</div><div class="v small">${last ? whenAt(last.at * 1000) : "never"}</div></div></div>
      ${
        sy
          ? `<div style="margin-top:12px"><div class="row small"><b class="gold">${esc(sy.phase)}</b><span class="muted">${esc(sy.message)}</span><span class="faint">${sy.done}/${sy.total}</span></div>
        <div class="prog"><i style="width:${sy.total ? (100 * sy.done) / sy.total : sy.running ? 5 : 100}%"></i></div>
        ${Object.keys(sy.changed || {}).length ? `<div class="small muted" style="margin-top:6px">changed: ${esc(JSON.stringify(sy.changed))}</div>` : ""}
        ${(sy.errors || [])
          .slice(0, 5)
          .map((e) => `<div class="small bad">${esc(e)}</div>`)
          .join("")}</div>`
          : ""
      }
      <p class="small faint">Data folder: ${esc(s.home)}</p>`;
    $("#cat").innerHTML =
      '<option value="">all categories</option>' +
      (db.categories || []).map(([c, k]) => `<option value="${esc(c)}">${esc(c)} (${k})</option>`).join("");
    return sy && sy.running;
  };
  const loop = async () => {
    if (!location.hash.startsWith("#/database")) return;
    const running = await show().catch(() => false);
    setTimeout(loop, running ? 2000 : 15000);
  };
  $("#sync").onclick = async () => {
    await api("/api/sync", {});
    show();
  };
  $("#full").onclick = async () => {
    await api("/api/sync", { force: true, budget: 3600 });
    show();
  };
  $("#srch").onclick = async () => {
    const items = await api(
      `/api/items?search=${encodeURIComponent($("#q").value)}&category=${encodeURIComponent($("#cat").value)}`,
    );
    $("#items").innerHTML =
      `<table class="t"><tr><th><span class="sr-only">Icon</span></th><th>Item</th><th>Category</th><th class="r">Item level</th></tr>${items
        .map(
          (it) =>
            `<tr data-item="${esc(it.slug)}" style="cursor:pointer"><td>${it.icon ? `<span class="icon xs"><img${assetAttrs("item", it)} src="${icon(it.icon)}"></span>` : ""}</td><td class="gname" data-grade="${esc(it.grade)}">${esc(it.name)}</td>
       <td>${esc(it.category)}</td><td class="r">${it.item_level ?? ""}</td></tr>`,
        )
        .join("")}</table>`;
    $$("[data-item]").forEach(
      (tr) =>
        (tr.onclick = async () => {
          const it = await api("/api/items/" + tr.dataset.item);
          $("#item").innerHTML = win(
            it.name || it.slug,
            `${esc(it.grade || "")} ${esc(it.category || "")}`,
            `<div class="grid2"><div><h4 class="gold small">FIXED</h4>${kv(Object.entries(it.fixed || {}).map(([k, v]) => [k, esc(v)]))}
          <h4 class="gold small">ENCHANT</h4>${kv((it.enchant || []).map((e) => [e.step, esc(e.stats)]))}</div>
         <div><h4 class="gold small">RANDOM ROLL POOL</h4>${kv((it.random || []).map((r) => [r.stat, `${esc(r.range)} <span class="faint">${esc(r.chance)}</span>`]))}
          ${
            it.skill_pools && Object.keys(it.skill_pools).length
              ? `<h4 class="gold small">SKILL ROLL POOLS</h4>${Object.entries(it.skill_pools)
                  .map(
                    ([c, p]) =>
                      `<div class="small"><b>${esc(cap(c))}</b> (up to +${p.max_level}): ${p.skills.map(esc).join(", ")}</div>`,
                  )
                  .join("")}`
              : ""
          }</div></div>`,
          );
        }),
    );
  };
  loop();
}
