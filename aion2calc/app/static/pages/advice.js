/* Gear & Advice's results (the paper doll, upgrade path, arcana, pantheon, genus, titles and fights), which
   Saved Results shows too. */
"use strict";

const SKILL_ICON = (id) => (id ? "https://metabot.gg/web/aion2/skills/" + id + ".webp" : "");
const DOLL_LEFT = ["MainHand", "SubHand", "Helmet", "Shoulder", "Torso", "Pants", "Gloves", "Boots", "Cape", "Belt"];
const DOLL_RIGHT = ["Necklace", "Earring1", "Earring2", "Ring1", "Ring2", "Bracelet1", "Bracelet2", "Amulet", "Rune1", "Rune2"];
const SLOT_NAME = { MainHand: "Main hand", SubHand: "Off-hand", Torso: "Chest", Pants: "Legs", Cape: "Cloak", Earring1: "Earring", Earring2: "Earring",
  Ring1: "Ring", Ring2: "Ring", Bracelet1: "Bracelet", Bracelet2: "Bracelet", Rune1: "Rune", Rune2: "Rune" };
const itemIcon = (it, cls = "") => `<div class="icon with-fallback ${cls}" data-grade="${esc(it?.grade || "")}"><span class="asset-placeholder" aria-hidden="true">◇</span>${it?.icon ? `<img${assetAttrs("item",it)} src="${icon(it.icon)}" alt="${esc(it.name || "Equipment")}" loading="lazy" onerror="this.hidden=true">` : ""}${it?.enchant ? `<span class="lv">+${it.enchant}</span>` : ""}</div>`;
function itemCard(it, label, gain, extra = "") {
  if (!it) return `<div class="icard empty"><div class="ilabel">${esc(label)}</div><div class="faint small">—</div></div>`;
  return `<div class="icard" data-grade="${esc(it.grade || "")}"><div class="ilabel">${esc(label)}</div>${itemIcon(it, "lg")}
    <div class="gname">${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.name)}</a>` : esc(it.name)}</div>
    <div class="small muted">${it.item_level ? "iLv " + it.item_level + " · " : ""}+${it.enchant || 0}</div>
    ${gain != null ? `<div class="gain ${gain >= 0 ? "up" : "down"}">${sp(gain)}</div>` : ""}${extra}</div>`;
}

function advDoll(a) {
  const d = a.doll;
  const tile = (slot) => {
    const x = d[slot] || {};
    const it = x.worn || x.wear || null;
    const up = x.wear ? x.wear_gain : null;
    const goal = x.next && x.next.gain > 0.02;
    return `<button class="dslot" data-dslot="${slot}" data-grade="${esc(it?.grade || "")}">${itemIcon(it, "sm")}
      <div class="dtxt"><div class="sl">${esc(SLOT_NAME[slot] || slot)}</div><div class="gname">${esc(it?.name || "empty")}</div></div>
      ${up ? `<span class="badge up" title="better item in your inventory">▲ ${sp(up)}</span>` : goal ? `<span class="badge goal" title="next goal">◆ ${sp(x.next.gain)}</span>` : ""}
      ${x.steps.length ? `<span class="badge step" title="upgrade path step">#${x.steps[0]}</span>` : ""}</button>`;
  };
  const arc = ["Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror"];
  return win("Equipment", "click a slot: what you wear → better from your inventory → next goal → best in slot",
    `<div class="pdoll"><div class="dcol">${DOLL_LEFT.map(tile).join("")}</div>
      <div class="dcenter"><div class="cls">${esc(cap(a.character.class))}</div><div class="small">${esc(a.character.name)} · ${esc(a.character.server)}</div>
        <div class="dps">${n0(a.dps)}<small>boss DPS</small></div>
        <div class="legend2"><span class="badge up">▲</span> better item in your inventory<br><span class="badge goal">◆</span> next goal gain<br><span class="badge step">#</span> upgrade path step</div>
        <div class="arow">${arc.map((s) => { const it = d[s]?.worn; return `<button class="dslot mini" data-dslot="${s}" title="${esc(s)}">${itemIcon(it, "sm")}</button>`; }).join("")}</div></div>
      <div class="dcol">${DOLL_RIGHT.map(tile).join("")}</div></div><div id="dslotinfo" class="dinfo"></div>`,
    { key: "adv-equip", copy: Object.entries(d).filter(([, x]) => x.wear || x.next).map(([s, x]) => `${s}: ${x.wear ? "wear " + x.wear.name + " +" + x.wear.enchant + "; " : ""}${x.next ? "next goal " + x.next.name + ((x.next.rolls || []).length ? " (roll toward " + x.next.rolls.map(rollText).join(", ") + ")" : "") : ""}`).join("\n") });
}
function bindDoll(a) {
  const show = (slot) => {
    const x = a.doll[slot] || {};
    $$("[data-dslot]").forEach((b) => b.classList.toggle("on", b.dataset.dslot === slot));
    const chips = (it) => it ? `${(it.skills || []).map(([k, l]) => `<span class="chip gold">${esc(k)} +${l}</span>`).join("")}${(it.rolls || []).map((r) => `<span class="chip">${esc(rollText(r))}</span>`).join("")}` : "";
    // a goal item's rolls are the ones to chase (its best roll stats), not rolls it has
    const chase = (it) => it && (it.rolls || []).length ? `<div class="small faint">roll toward</div><div>${(it.rolls || []).map((r) => `<span class="chip gold" title="a roll worth chasing on this item">${esc(rollText(r))}</span>`).join("")}</div>` : "";
    $("#dslotinfo").innerHTML = `<h4 class="gold small">${esc(SLOT_NAME[slot] || slot).toUpperCase()}</h4><div class="iflow">
      ${itemCard(x.worn, "Wearing", null, `<div>${chips(x.worn)}</div>`)}<div class="arr">➜</div>
      ${itemCard(x.wear, "From your inventory", x.wear_gain, `<div>${chips(x.wear)}</div>`)}<div class="arr">➜</div>
      ${itemCard(x.next, "Next goal", x.next?.gain, chase(x.next))}<div class="arr">➜</div>${itemCard(x.best, "Best in slot", x.best?.gain, chase(x.best))}</div>
      ${x.steps.length ? `<p class="small muted">Upgrade path steps for this slot: ${x.steps.map((n) => "#" + n).join(", ")}</p>` : ""}`;
  };
  $$("[data-dslot]").forEach((b) => (b.onclick = () => show(b.dataset.dslot)));
  const first = Object.keys(a.doll).find((s) => a.doll[s].wear) || Object.keys(a.doll).find((s) => a.doll[s].next) || "MainHand";
  show(first);
}

// A roll as the advice lists it: {stat, range} (a roll to chase), [stat, value] (a roll an item has) or text.
function rollText(r) {
  if (r && typeof r === "object" && !Array.isArray(r)) return `${r.stat || ""}${r.range ? " " + r.range : ""}`.trim();
  return Array.isArray(r) ? r.join(" ") : String(r ?? "");
}

function advPath(a) {
  const steps = a.upgrade_path.steps;
  const kind = { enchant: "＋1", reroll: "⟳", replace: "⇄" };
  const rolls = (s) => (s.rolls || []).length ? `<div class="prolls">${s.rolls.map((r) => `<span class="chip gold" title="a roll worth chasing">${esc(rollText(r))}</span>`).join("")}</div>` : "";
  return win("Upgrade path", "one change at a time, biggest gain first, toward the next goals; a reroll names the stats to chase",
    `<div class="path">${steps.map((s) => `<div class="pstep" data-grade="${esc(s.item?.grade || "")}"><div class="pn">#${s.step}</div>
      <div class="sl">${esc(SLOT_NAME[s.slot] || s.slot)}</div>${itemIcon(s.item, "lg")}<span class="kind" title="${esc(s.kind || "")}">${kind[s.kind] || ""}</span>
      <div class="gname small">${esc(s.item?.name || "")}</div><div class="small faint">${esc(s.action)}</div>${rolls(s)}
      <div class="gain up">${sp(s.gain)}</div><div class="cum"><i style="width:${Math.min(100, 100 * s.total_gain / Math.max(0.0001, steps[steps.length - 1].total_gain))}%"></i><span>${sp(s.total_gain)}</span></div></div>`).join("")}</div>`,
    { key: "adv-path", copy: steps.map((s) => `${s.step}. ${s.slot}: ${s.action} (${sp(s.gain)})`).join("\n") });
}

function advArcana(a) {
  const order = ["Arcana Chalice", "Arcana Parchment", "Arcana Compass", "Arcana Bell", "Arcana Mirror"];
  const cards = order.filter((s) => a.arcana.slots[s]).map((slot) => {
    const x = a.arcana.slots[slot], v = x.variant || {};
    const prio = a.arcana.priority.indexOf(slot) + 1;
    const opts = Object.entries(x.ideal.skills).map(([k, lv]) => `<div class="sk" title="${esc(k)} +${lv}"><div class="icon sm"><img src="${icon(SKILL_ICON(x.skill_ids[k]))}" alt=""><span class="lv">+${lv}</span></div><div class="small">${esc(k)}</div></div>`).join("");
    const owned = x.owned.map((o) => `<div class="owned ${o.verdict === "keep" ? "ok" : "bad"}">${itemIcon(o, "xs")}<span class="small">${esc(o.name)} +${o.enchant}</span>
      <span class="small">${sp(o.gain)}</span><span class="chip ${o.verdict === "keep" ? "gold" : ""}">${o.verdict === "keep" ? "keep" : "replace"}</span></div>`).join("");
    return `<div class="acard" data-grade="${esc(v.grade || "Unique")}"><div class="t">${esc(slot.replace("Arcana ", ""))}<span class="prio">#${prio}</span></div>
      ${itemIcon({ ...v, enchant: 5 }, "xl")}<div class="gname">${esc(v.name || "")}</div>
      <div class="deity">${esc(v.deity || "")} +${v.points ?? ""}</div>
      <div class="sub">TARGET OPTIONS · UNIQUE +5</div><div class="opts">${opts}</div>
      <div class="vals"><span>ideal <b>${sp(x.ideal.gain)}</b></span><span>average <b>${sp(x.expected.unique_5)}</b></span></div>
      ${owned ? `<div class="sub">YOURS</div>${owned}` : ""}</div>`;
  }).join("");
  return win("Arcana", "variant per slot, the skill options to chase (icons = target levels), and your arcana", `<div class="acards">${cards}</div>`,
    { key: "adv-arcana", copy: order.filter((s) => a.arcana.slots[s]).map((s) => { const x = a.arcana.slots[s]; return `${s}: ${x.variant?.name} — ${Object.entries(x.ideal.skills).map(([k, l]) => k + " +" + l).join(", ")}`; }).join("\n") });
}

const LORDS = { "Destruction [Zikel]": ["Zikel", "#d9534f"], "Death [Triniel]": ["Triniel", "#9b59b6"], "Wisdom [Lumiel]": ["Lumiel", "#5bc0de"],
  "Time [Siel]": ["Siel", "#f0ad4e"], "Illusion [Kaisinel]": ["Kaisinel", "#8e7cc3"], "Justice [Nezekan]": ["Nezekan", "#e8cf8e"],
  "Freedom [Vaizel]": ["Vaizel", "#5cb85c"], "Life [Yustiel]": ["Yustiel", "#7fd6a8"], "Destiny [Marchutan]": ["Marchutan", "#c0a16b"], "Space [Israphel]": ["Israphel", "#6fa8dc"] };
const DEITY_FX = { "Destruction [Zikel]": "Attack, Perfect Resist", "Death [Triniel]": "Critical Hit, Regen Penetration", "Wisdom [Lumiel]": "Double chance, MP cost",
  "Time [Siel]": "Combat Speed, Double Resist", "Illusion [Kaisinel]": "Cooldown, Endurance Penetration", "Justice [Nezekan]": "Perfect chance, Defense",
  "Freedom [Vaizel]": "Accuracy, Evasion", "Life [Yustiel]": "HP, Regeneration", "Destiny [Marchutan]": "MP, Endurance", "Space [Israphel]": "Move Speed, Block" };
const KIND_LABEL = { colossus: "Colossus", statue: "Statue", artwork: "Artwork" };
function deityShort(d) { return d.split(" [")[0]; }
function pantheonBoardHTML(b) {
  // The in-game board: the colossus in the centre, four statue stands on the inner ring, twelve
  // artwork stands on the outer ring. Each stand shows the recommended decoration.
  const cx = 230, cy = 230, R1 = 108, R2 = 190;
  const col = (b.board.colossus || [])[0];
  const tip = (r) => r ? `${KIND_LABEL[r.kind]}: ${r.short} — ${Object.entries(r.stats).map(([k, v]) => deityShort(k) + " +" + v).join(", ")} · ${sp(r.gain)} · ${(r.sources || []).join("; ") || "source unknown"}` : "";
  const short = (name, n) => (name || "").length > n ? name.slice(0, n - 1) + "…" : (name || "");
  const hex = (x, y, r) => Array.from({ length: 6 }, (_, i) => { const a = (-90 + i * 60) * Math.PI / 180; return `${(x + r * Math.cos(a)).toFixed(1)},${(y + r * Math.sin(a)).toFixed(1)}`; }).join(" ");
  const statues = (b.board.statue || []);
  const inner = Array.from({ length: 4 }, (_, i) => {
    const a = (45 + i * 90) * Math.PI / 180, x = cx + R1 * Math.cos(a), y = cy + R1 * Math.sin(a), r = statues[i];
    return `<g class="pslot statue ${r ? "set" : "empty"}"><title>${esc(tip(r) || "Statue stand " + (i + 1) + ": no candidate")}</title><polygon points="${hex(x, y, 40)}"/><text x="${x.toFixed(1)}" y="${(y - 4).toFixed(1)}" text-anchor="middle" class="pn">${esc(short(r?.short, 14))}</text><text x="${x.toFixed(1)}" y="${(y + 12).toFixed(1)}" text-anchor="middle" class="pp">${r ? "+" + r.points : "stand " + (i + 1)}</text></g>`;
  }).join("");
  const artworks = (b.board.artwork || []);
  const outer = Array.from({ length: 12 }, (_, i) => {
    const a = (-90 + i * 30) * Math.PI / 180, x = cx + R2 * Math.cos(a), y = cy + R2 * Math.sin(a), r = artworks[i];
    return `<g class="pslot artwork ${r ? "set" : "empty"}"><title>${esc(tip(r) || "Artwork stand " + (i + 1) + ": no candidate")}</title><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="27"/><text x="${x.toFixed(1)}" y="${(y - 2).toFixed(1)}" text-anchor="middle" class="pn">${esc(short(r?.short, 11))}</text><text x="${x.toFixed(1)}" y="${(y + 11).toFixed(1)}" text-anchor="middle" class="pp">${r ? "+" + r.points : ""}</text></g>`;
  }).join("");
  return `<svg class="pboard" viewBox="0 0 460 460" role="img" aria-label="Recommended Pantheon board">
    <circle class="pring" cx="${cx}" cy="${cy}" r="${R2}"/><circle class="pring" cx="${cx}" cy="${cy}" r="${R1}"/>
    ${outer}${inner}
    <g class="pslot colossus ${col ? "set" : "empty"}"><title>${esc(tip(col) || "Colossus stand: no candidate")}</title><polygon points="${hex(cx, cy, 58)}"/><text x="${cx}" y="${cy - 8}" text-anchor="middle" class="pn">${esc(short(col?.short, 16))}</text><text x="${cx}" y="${cy + 10}" text-anchor="middle" class="pp">${col ? "+" + col.points : "Colossus"}</text><text x="${cx}" y="${cy + 26}" text-anchor="middle" class="pk">COLOSSUS</text></g>
  </svg>`;
}
function pantheonListHTML(b) {
  const row = (r) => `<div class="prow" data-grade="${esc(r.grade || "")}"><div class="pname">${esc(r.short)}${r.grade ? ` <span class="chip">${esc(r.grade)}</span>` : ""}${r.faction ? ` <span class="small faint">${esc(r.faction)}</span>` : ""}</div>
    <div class="pstats small">${Object.entries(r.stats).map(([k, v]) => `${esc(deityShort(k))} <b>+${v}</b>`).join(" · ")}</div>
    <div class="gain up">${sp(r.gain)}</div><div class="psrc small muted">${esc((r.sources || []).join("; ") || "source not listed in the catalog")}</div></div>`;
  const ring = (kind, title) => `<div class="pring-list"><h4 class="gold small">${title} · ${(b.board[kind] || []).length}/${b.slots[kind]}</h4>${(b.board[kind] || []).map(row).join("") || '<div class="small faint">No catalogued decoration with a known effect.</div>'}
    ${(b.runners_up[kind] || []).length ? `<details><summary class="small muted">Next best ${KIND_LABEL[kind].toLowerCase()}s</summary>${b.runners_up[kind].map(row).join("")}</details>` : ""}</div>`;
  const totals = Object.entries(b.totals || {}).sort((x, y) => y[1] - x[1]).map(([k, v]) => `<span class="chip" title="${esc(k)}">${esc(deityShort(k))} ${v}</span>`).join(" ");
  return `<div class="ptotals small"><b>Board total</b> ${totals} <span class="gain up">${sp(b.gain)}</span> vs an empty board</div>
    ${ring("colossus", "COLOSSUS · centre")}${ring("statue", "STATUES · inner ring")}${ring("artwork", "ARTWORKS · outer ring")}
    <p class="small faint">${esc(b.note || "")} Candidates: ${b.catalog?.candidates?.colossus ?? 0} colossi, ${b.catalog?.candidates?.statue ?? 0} statues, ${b.catalog?.candidates?.artwork ?? 0} artworks with a known effect${b.faction ? ` (your faction: ${esc(b.faction)})` : " (faction unknown: both factions' pieces shown)"}.</p>`;
}
function advPantheon(a) {
  const p = a.pantheon;
  const mx = Math.max(...p.per_point.map((r) => r.gain_per_point), 1e-9);
  const tiles = Object.keys(LORDS).map((dname) => {
    const r = p.per_point.find((x) => x.deity === dname) || {};
    const [lord, col] = LORDS[dname];
    const best = dname === p.best;
    return `<div class="dtile ${best ? "best" : ""} ${r.field ? "" : "dim"}"><div class="sigil" style="--dc:${col}">${esc(lord[0])}</div>
      <div class="dn">${esc(dname.split(" [")[0])}</div><div class="lord">${esc(lord)}</div><div class="pts">${p.current[dname] ?? 0}</div>
      <div class="fx">${esc(DEITY_FX[dname])}</div><div class="bar"><i style="width:${Math.max(0, 100 * (r.gain_per_point || 0) / mx)}%"></i><span>${sp(10 * (r.gain_per_point || 0))} / 10</span></div>
      ${best ? '<span class="chip gold">best for damage</span>' : ""}</div>`;
  }).join("");
  const choices = p.choices.map((c) => `<div class="pchoice"><span class="muted small">${esc(c.source)}</span> <b>${esc(c.pick)}</b>${c.deity ? ` <span class="small">(${esc(c.deity)})</span>` : ""} <span class="gain up">${sp(c.gain)}</span></div>`).join("");
  const board = p.board ? `<h4 class="gold small" style="margin-top:14px">RECOMMENDED BOARD · colossus, statues, artworks</h4><p class="small muted">The decorations worth placing, by modeled damage on your build (the collection itself is not in the official profile). Hover a stand for the piece's deity points and where it comes from.</p><div class="pwrap"><div>${pantheonBoardHTML(p.board)}</div><div>${pantheonListHTML(p.board)}</div></div>` : "";
  return win("Pantheon", "deity stats: points you have, what 10 more points are worth, and the decorations to place", `<div class="dtiles">${tiles}</div><div class="pchoices">${choices}</div>${board}`,
    { key: "adv-pantheon", copy: p.per_point.map((r) => `${r.deity}: ${sp(10 * r.gain_per_point)} per 10`).concat(p.board ? ["", ...["colossus", "statue", "artwork"].flatMap((k) => (p.board.board[k] || []).map((r) => `${KIND_LABEL[k]}: ${r.short} (${Object.entries(r.stats).map(([d, v]) => deityShort(d) + " +" + v).join(", ")}) ${sp(r.gain)} — ${(r.sources || []).join("; ")}`))] : []).join("\n") });
}

function advGenus(a, inv) {
  const g = a.genus, state = g.state || (inv && inv.genus) || {};
  const genera = ["Cogni", "Fera", "Natura", "Varian", "Special"];
  const S2 = S.gear;
  const cur = S2.genusTab || (g.level_order[0] && g.level_order[0].genus) || "Cogni";
  const st = state[cur] || { level: 0, lines: [] };
  const val = {};
  g.lines.filter((l) => l.genus === cur).forEach((l) => (val[l.slot] = l));
  const chase = g.chase.find((c) => c.genus === cur);
  const rolls = (g.roll_targets && g.roll_targets.genera && g.roll_targets.genera[cur]) || null;
  const aimOf = (n) => (rolls && rolls.slots && rolls.slots[n]) || null;
  const aimText = (x) => x && x.aim && x.aim.length ? `${x.aim[0].stat} <span class="faint">${esc(x.aim[0].grade)} ${esc(x.aim[0].range)}</span> <span class="gain up">${sp(x.aim[0].gain)}</span>` : "";
  const cells = Array.from({ length: 9 }, (_, i) => {
    const n = i + 1, line = (st.lines || []).find((l) => +l.slot === n), v = val[n], x = aimOf(n);
    const known=Number.isInteger(state[cur]?.level),locked = known && n > st.level;
    const special = n === 4;
    const aim = x && x.aim && x.aim.length ? x.aim[0] : null;
    const more = x && x.aim ? x.aim.slice(1, 3).map((r) => `${r.stat} (${r.grade} ${r.range}, ${sp(r.gain)})`).join(", ") : "";
    const title = aim ? `Roll for: ${aim.stat} ${aim.grade} ${aim.range} (${sp(aim.gain)})${more ? "; then " + more : ""}` : "";
    if (locked) return `<div class="gslot locked ${special ? "sp" : ""}" title="${esc(title)}"><div class="gn">${n}</div><div class="small faint">opens at Lv ${n}</div>${aim ? `<div class="gaim small">then roll for ${esc(aim.stat)}</div>` : ""}</div>`;
    if (!line) return `<div class="gslot ${special ? "sp" : ""} ${aim ? "aimed" : ""}" title="${esc(title)}"><div class="gn">${n}</div><div class="small faint">${known ? "Not recorded" : "Level not entered"}</div>${aim ? `<div class="gaim"><span class="small muted">roll for</span><br>${aimText(x)}</div>` : special && chase ? `<div class="small faint">Possible line: ${esc(chase.line)}</div>` : ""}</div>`;
    const dead = v && v.gain != null && v.gain <= 1e-6;
    const keep = aim && line.stat === aim.stat;
    return `<div class="gslot filled ${special ? "sp" : ""} ${dead ? "dead" : ""}" title="${esc(title)}"><div class="gn">${n}</div><div class="gst">${esc(line.stat)}</div><div class="gv">${esc(line.value)}</div>
      ${v?.gain==null?`<div class="small muted">${esc(v?.reason||'Not modeled')}</div>`:v ? `<div class="gain ${dead ? "down" : "up"}">${dead ? "No modeled damage gain" : (v.gain < 0.001 ? "+" + (100 * v.gain).toFixed(2) + "%" : sp(v.gain))}</div>` : ""}
      ${aim ? (keep ? `<div class="gaim small ok">✓ best modeled line for this slot</div>` : `<div class="gaim small"><span class="muted">reroll for</span> ${aimText(x)}</div>`) : ""}</div>`;
  }).join("");
  const mix = Object.entries(g.mix).map(([k, v]) => `<span class="mixseg" style="flex:${v}" title="${esc(k)} ${pct(v, 0)}">${esc(k)} ${pct(v, 0)}</span>`).join("");
  const best = rolls && rolls.best ? rolls.best.map((r) => `<div class="small">slot ${r.slot}: <b>${esc(r.stat)}</b> <span class="faint">${esc(r.grade)} ${esc(r.range)}</span> <span class="gain up">${sp(r.gain)}</span></div>`).join("") : '<div class="small faint">No modeled candidate for this genus.</div>';
  const table = rolls ? `<details class="grolls"><summary class="small">All slots · what each can roll and what to aim for</summary><table class="t small"><tr><th>Slot</th><th>Roll for (best listed grade)</th><th>Then</th><th>Options</th></tr>${Object.entries(rolls.slots).map(([n, x]) => `<tr><td>${n}${+n === 4 ? ' <span class="faint">amp</span>' : ""}</td><td>${x.aim && x.aim[0] ? `<b>${esc(x.aim[0].stat)}</b> <span class="faint">${esc(x.aim[0].grade)} ${esc(x.aim[0].range)}</span> <span class="gain up">${sp(x.aim[0].gain)}</span>` : '<span class="faint">no modeled line</span>'}</td><td>${(x.aim || []).slice(1, 3).map((r) => `${esc(r.stat)} <span class="faint">${sp(r.gain)}</span>`).join("<br>")}</td><td class="faint">${x.options} (${x.unmodeled} unmodeled)</td></tr>`).join("")}</table></details>` : "";
  return win("Genus Insight", "pet genus lines: what each slot can roll, what to roll for, and your saved lines weighted by your fight time per genus",
    `<p class="note">Genus levels and analysis lines are manual inputs; they are not included in the official profile. Enter and save them in the Genus Insight editor above, then run advice again. Blank slots are not recorded, not evidence of a locked Insight. "Roll for" lines come from the Global slot property tables and are modeled damage on your build, whether or not you recorded anything.</p>${genusTargetsHTML(g.targets)}<div class="tabs">${genera.map((x) => `<button data-gtab="${x}" class="${x === cur ? "on" : ""}">${x} <span class="faint">${Number.isInteger(state[x]?.level)?"Lv "+esc(state[x].level):"Not recorded"}</span></button>`).join("")}</div>
     ${genusCoverageHTML(g)}<div class="gwrap"><div>${A2GenusEditor.ringHTML(cur,state[cur])}<div class="ggrid">${cells}</div>${table}</div><div class="gside"><h4 class="gold small">ROLL FOR · ${esc(cur)}</h4>${best}<p class="small muted">${esc(g.roll_targets?.basis || "")}. Gains are not additive across slots.</p><h4 class="gold small">YOUR FIGHT TIME</h4><div class="mix">${mix}</div>
       ${chase ? `<h4 class="gold small">CHASE</h4><div>${esc(chase.line)} · slot ${chase.slot} <span class="small muted">${esc(chase.value)}</span> <span class="gain up">${sp(chase.gain)}</span><p class="small muted">${esc(chase.assumption)}. Damage-only candidate; confirm the defensive tradeoff in game.</p></div>` : ""}
       <h4 class="gold small">LEVEL ORDER</h4>${g.level_order.slice(0, 5).map((r, i) => `<div class="small">${i + 1}. ${esc(r.genus)} <span class="faint">Lv ${Number.isInteger(state[r.genus]?.level)?r.level:"not recorded"} · ${pct(r.share, 0)} of fights${r.next ? (r.next.opens_slot?` · next opens slot ${r.next.opens_slot}`:' · next changes grade chances') : ""}</span></div>`).join("")}</div></div>`,
    { key: "adv-genus", copy: (rolls ? Object.entries(rolls.slots).map(([n, x]) => `${cur} slot ${n}: roll for ${x.aim && x.aim[0] ? x.aim[0].stat + " (" + x.aim[0].grade + " " + x.aim[0].range + ", " + sp(x.aim[0].gain) + ")" : "no modeled line"}`) : []).concat(g.lines.map((l) => `${l.genus} slot ${l.slot}: ${l.stat} ${l.value} (${l.gain==null?(l.reason||'Not modeled'):sp(l.gain)})`)).join("\n") });
}

function titlePlate(t, label, extra = "") {
  if (!t) return `<div class="tplate empty"><div class="ilabel">${esc(label)}</div><div class="faint small">—</div></div>`;
  return `<div class="tplate" data-grade="${esc(t.grade || "")}"><div class="ilabel">${esc(label)}</div>
    <div class="tname gname">❖ ${esc(t.name)} ❖</div><div class="small">${esc(t.equip || "")}</div>
    ${t.owned_bonus && t.owned_bonus !== "—" ? `<div class="small muted">owned: ${esc(t.owned_bonus)}</div>` : ""}
    ${t.gain != null && label !== "Equipped" ? `<div class="gain ${t.gain >= 0 ? "up" : "down"}">${sp(t.gain)}</div>` : ""}
    ${t.how ? `<div class="small faint" title="${esc(t.how)}">${esc(t.how.replace(/^You earn it by /, "").split(/\. How to get it/)[0].slice(0, 110))}</div>` : ""}${extra}</div>`;
}
function advTitles(a) {
  const t = a.titles;
  if (!t) return "";
  const cols = ["Attack", "Defense", "Etc"].map((slot) => { const x = t.slots[slot] || {};
    return `<div class="tcol"><div class="t">${slot === "Etc" ? "Other" : slot} title</div>${titlePlate(x.equipped, "Equipped")}
      ${t.owned_known ? titlePlate(x.best_owned, "Best you own") : ""}
      <div class="sub">BEST IN SLOT</div>${(x.best || []).length ? "" : '<div class="small faint">No title for this slot adds damage.</div>'}${(x.best || []).slice(0, 3).map((r, i) => titlePlate(r, i ? "" : "Best", r.owned ? '<span class="chip gold">owned</span>' : "")).join("")}</div>`; }).join("");
  const coll = t.collect.map((c) => titlePlate({ ...c, equip: "" }, "Collect", "")).join("");
  return win("Titles", "equip bonus per slot, and titles worth collecting for their owned bonus",
    `<div class="tcols">${cols}</div>${t.note ? `<p class="small faint">${esc(t.note)}</p>` : ""}
     ${coll ? `<h4 class="gold small" style="margin-top:12px">WORTH COLLECTING (owned bonus)</h4><div class="tcollect">${coll}</div>` : ""}`,
    { key: "adv-titles", copy: ["Attack", "Defense", "Etc"].map((s) => `${s}: ${(t.slots[s]?.best_owned || t.slots[s]?.best?.[0] || {}).name || "-"}`).join("\n") });
}

function advTop(a) {
  const ic = { titles: "❖", "gear (inventory)": "▲", "gear (upgrade)": "⇧", arcana: "✦", pantheon: "☉", "genus insight": "❖", rotation: "↻", specializations: "◎", community: "☷" };
  return win("Top changes", a.calibrated ? "ranked by simulated DPS gain · model calibrated from fights" : "ranked by simulated DPS gain",
    `<div class="tops">${a.top.map((r) => `<div class="top"><span class="ti">${ic[r.area] || "•"}</span><div><div class="small muted">${esc(r.area)}</div><div>${esc(r.text)}</div></div><div class="gain ${r.gain == null ? "" : "up"}">${r.gain == null ? "" : sp(r.gain)}</div></div>`).join("")}</div>
     <p class="small faint">Saved as <code>${esc(a.file || "")}</code></p>`, { key: "adv-top", copy: a.top.map((r) => `${r.area}: ${r.text} ${r.gain == null ? "" : sp(r.gain)}`).join("\n") });
}

function advSpecialties(a) {
  const rows=a.skill_specialties;
  if(!rows)return win("Skill specialties", "", '<p class="muted">This older saved advice has no specialty snapshot. Recalculate advice to include it.</p>');
  const text=rows.map(r=>`${r.skill} · effective Lv ${esc(r.level)}: ${r.effects.filter(e=>e.selected).map(e=>`#${esc(e.number)}: ${e.text} (effect Lv ${esc(e.unlock)})`).join('; ')||'None unlocked/selected'}`).join('\n');
  return win("Skill specialties", "recommended for your imported equipped build", `<p class="small muted">Effective levels include trained, Daevanion and gear bonuses. These are simulated recommendations; the official profile does not show your selected specialties. Stigma effects activate automatically. Recalculate after changing gear or points.</p><table class="t"><tr><th>Skill / effective level</th><th>Recommended specialties</th><th>Next unlock</th></tr>${rows.map(r=>`<tr><td>${esc(r.skill)} · Lv ${esc(r.level)}<br><span class="small muted">${r.automatic?'Automatic stigma effects':esc(r.slots)+' selection slot(s)'}</span></td><td>${r.effects.filter(e=>e.selected).map(e=>`<div><b>#${esc(e.number)}</b> ${esc(e.text)} <span class="faint">(effect Lv ${esc(e.unlock)})</span></div>`).join('')||'None unlocked/selected'}<details><summary>All effects and requirements</summary>${r.effects.map(e=>`<p class="small">#${esc(e.number)} · Lv ${esc(e.unlock)} · ${e.selected?'Recommended':e.available?'Available':'Locked'}: ${esc(e.text)}</p>`).join('')}</details></td><td>${r.next_effect_level?'Effect Lv '+esc(r.next_effect_level):'All effects unlocked'}${r.next_slot_level?'<br>Selection slot Lv '+esc(r.next_slot_level):''}</td></tr>`).join('')}</table>`, {key:'adv-specialties',copy:text});
}
function fightsHTML(a) {
  const r = a.rotation, f = a.fights || { count: 0, sources: {}, recent: [] };
  const src = { session: "live meter sessions", abysslogs: "AbyssLogs", a2log: "saved logs", a2dil: "A2DIL", csv: "CSV" };
  const summary = f.count ? `<p>${f.count} saved fight(s): ${Object.entries(f.sources).map(([k, n]) => `${n} from ${esc(src[k] || k)}`).join(", ")}${f.synced ? ` · ${f.synced} new from your recorded sessions` : ""}.</p>` : "";
  const recent = (f.recent || []).length ? `<table class="t small"><tr><th>Fight</th><th>Length</th><th>DPS</th><th>Source</th><th>When</th></tr>${f.recent.map((x) => `<tr><td><a href="#/combat-log/analysis/${x.id}">${esc(x.boss || "fight")}</a></td><td>${Math.round(x.duration || 0)} s</td><td>${Math.round(x.dps || 0).toLocaleString()}</td><td>${esc(src[x.source] || x.source || "")}</td><td class="faint">${x.started_at ? whenAt(x.started_at) : x.imported_at ? whenAt(x.imported_at * 1000) : ""}</td></tr>`).join("")}</table>` : "";
  const rot = r.fights ? `<p>${r.fights} fight(s) compared with the optimal rotation; idle ${pct(r.idle_share, 0)} of the time.</p>${r.under_cast.slice(0, 6).map((t) => `<div class="tip">${esc(t.text)}</div>`).join("")}
    ${r.specs.map((d) => `<div class="tip">${esc(d.skill)}: specs ${esc(d.yours)} in your fights, ${esc(d.optimal)} in the optimized build</div>`).join("")}` : f.count ? '<p class="muted">Your fights could not be compared with the optimal rotation yet (run Optimize for this class once).</p>' : '<p class="muted">No saved fights for this character yet. Record a boss fight with the live meter (the party sessions it saves are picked up here automatically) or import an AbyssLogs link on Combat Logs, then run advice again.</p>';
  return summary + rot + recent + (f.note ? `<p class="small faint">${esc(f.note)}</p>` : "");
}
function renderAdvice(a) {
  const rot = fightsHTML(a);
  return advTop(a) + advSpecialties(a) + advDoll(a) + advPath(a) + advArcana(a) + advTitles(a) + advPantheon(a) + advGenus(a, a.inventory_snapshot || S.gear.inv) +
    `<div class="grid2">${win("Your fights", "", rot)}${win("Model calibration", "learned from fights matched to equipped gear", a.calibration.map((x) => `<div class="small">${esc(x)}</div>`).join(""))}</div>`;
}
function bindAdvice(a) {
  bindDoll(a);
  $$("[data-gtab]").forEach((b) => (b.onclick = () => { S.gear.genusTab = b.dataset.gtab; $("#gout").innerHTML = renderAdvice(a); bindAdvice(a); }));
}
