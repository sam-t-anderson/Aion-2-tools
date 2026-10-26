/* A build's result windows (overview, skills, stigmas, Daevanion, equipment, arcana, titles, hotbar, macro
   and genus), as the Build Planner, My Character and Saved Results show them. */
"use strict";

function winSkills(v, tab = "active") {
  const list = v.skills[tab] || [];
  const bud = v.budgets || {};
  const counter = `<span class="counter"><small>Skill points</small> ${n0(v.points?.skill)} / ${n0(bud.skill)}</span>`;
  const rows = list
    .map((s) => {
      const chosen = s.specs.filter((x) => x.chosen);
      return `<div class="skill ${s.eff <= 1 ? "dim" : ""}">
      <div class="skill-overview"><div class="skill-heading">
        <div class="icon"><img src="${icon(s.icon)}" alt="" loading="lazy"><span class="lv">Lv${s.eff}</span></div>
        <div class="skill-title"><div class="nm">${esc(s.name)}</div>
          <div class="lvl"><b>Lv ${s.eff}</b> = SP ${s.sp} + Daevanion ${s.daev}${s.gear ? ` + gear ${s.gear}` : ""}</div></div>
      </div>${s.specs.length ? `<p class="skill-slot-summary small muted">${esc(s.slots)} selection slot(s)<br>${chosen.length} recommended${s.next_effect_level ? `<br>Next effect at Lv ${esc(s.next_effect_level)}` : ""}</p>` : ""}</div>
      ${s.specs.length ? `<div class="specs" role="list" aria-label="Supporting effects for ${esc(s.name)}">${s.specs.map((x) => `<div class="skill-effect" role="listitem"><span class="spec ${x.chosen ? "on" : x.available ? "av" : ""}" title="${esc(x.chosen ? "Recommended" : x.available ? "Available" : "Locked")}">${esc(x.n)}</span><div class="skill-effect-text">${esc(x.name || x.text)}<small class="${x.chosen ? "effect-recommended" : "faint"}">Lv ${esc(x.unlock)} · ${x.chosen ? "Recommended" : x.available ? "Available" : "Locked"}</small></div></div>`).join("")}</div>` : ""}
    </div>`;
    })
    .join("");
  const copy = v.skills.active
    .concat(v.skills.passive)
    .filter((s) => s.sp > 1 || s.specs.some((x) => x.chosen))
    .map(
      (s) =>
        `${s.name}: train to ${s.sp} (Lv ${s.eff})${
          s.specs.some((x) => x.chosen)
            ? " — specialties " +
              s.specs
                .filter((x) => x.chosen)
                .map((x) => `${x.n}: ${x.text} (effect Lv ${esc(x.unlock)})`)
                .join("; ")
            : ""
        }`,
    )
    .join("\n");
  const tabs = `<div class="tabs">${["active", "passive"].map((t) => `<button data-skilltab="${t}" class="${t === tab ? "on" : ""}">${cap(t)}</button>`).join("")}</div>`;
  const rolls = (v.gear_skill_rolls || []).map((r) => `${r.name} +${r.levels}`).join(", ");
  // a community preset's bonus levels: the skills to put gear rolls and arcana card options on
  const chase = (v.bonus_levels || [])
    .map((r) => `${r.name} +${r.levels}${(r.arcana || []).length ? ` (${r.arcana.join(", ")})` : ""}`)
    .join(", ");
  return win(
    "Skills",
    counter,
    tabs +
      `<div class="skilllist">${rows}</div>` +
      statGrid(
        [
          { label: "Skill points spent", text: `${n0(v.points?.skill)} / ${n0(bud.skill)}` },
          ...(rolls ? [{ label: "Skill levels from gear", text: rolls }] : []),
          ...(chase
            ? [
                {
                  label: "Bonus levels to chase: gear rolls and arcana cards (the cards that can roll each skill)",
                  text: chase,
                },
              ]
            : []),
        ],
        "From this system",
      ),
    { key: "skills", copy: copy + (chase ? "\nBonus levels from gear rolls and arcana cards: " + chase : "") },
  );
}

function winStigmas(v) {
  const bud = v.budgets || {};
  const cards = v.stigmas
    .map(
      (s) => `<div class="stigma">
      <div class="icon"><img src="${icon(s.icon)}" alt="" loading="lazy"><span class="lv">Lv${s.level}</span></div>
      <div class="nm gold"><b>${esc(s.name)}</b></div><div class="small muted">Level ${s.level}</div>
      <ul>${s.specs.map((x) => `<li class="${x.active ? "on" : ""}"><b>${x.n}</b>${esc(x.text)} <span class="faint">(Lv ${x.unlock})</span></li>`).join("")}</ul>
    </div>`,
    )
    .join("");
  const copy = v.stigmas.map((s) => `${s.name}: Lv ${s.level}`).join("\n");
  return win(
    "Stigma",
    `<span class="counter"><small>Stigma points</small> ${n0(v.points?.stigma)} / ${n0(bud.stigma)}</span>`,
    `<div class="stigmas">${cards || '<div class="empty">No stigmas</div>'}</div>` +
      statGrid(
        v.stigmas.map((s) => ({
          label: s.name,
          text: `Lv ${s.level} · ${s.specs.filter((x) => x.active).length} effects`,
        })),
      ),
    { key: "stigma", copy },
  );
}

function winDaevanion(v, boardIdx = 0) {
  const d = v.daevanion;
  const b = d.boards[boardIdx] || d.boards[0];
  if (!b) return win("Daevanion", "", '<div class="empty">No board data</div>');
  const cells = b.nodes
    .map((nd) => {
      const cls = nd.type === "Start" ? "start" : nd.type === "SkillLevel" ? "skill" : nd.type === "None" ? "none" : "";
      const tip =
        nd.type === "SkillLevel"
          ? `${nd.skill} +1 (${nd.grade}, ${nd.cost} pt)`
          : nd.type === "Start"
            ? "Start"
            : `${nd.label} (${nd.grade}, ${nd.cost} pt)`;
      const txt =
        nd.type === "SkillLevel"
          ? (nd.skill || "")
              .split(/\s+/)
              .map((w) => w[0])
              .join("")
              .slice(0, 3)
          : nd.type === "Start"
            ? ""
            : esc(nd.short || "");
      return `<div class="node ${cls} ${nd.selected || nd.type === "Start" ? "sel" : ""}" data-grade="${esc(nd.grade)}"
      style="grid-row:${nd.row};grid-column:${nd.col}" title="${esc(tip)}">${nd.type === "SkillLevel" && Number.isSafeInteger(+nd.skill_id) && +nd.skill_id > 0 ? `<img class="node-skill-icon" src="${esc(icon("https://metabot.gg/web/aion2/skills/" + nd.skill_id + ".webp"))}" alt="${esc(nd.skill || "Skill")}" loading="lazy" onerror="this.hidden=true">` : ""}<span>${txt}</span></div>`;
    })
    .join("");
  const tabs = `<div class="tabs">${d.boards.map((x, i) => `<button data-board="${i}" class="${i === boardIdx ? "on" : ""}">${esc(x.name)} <span class="faint">${x.used}/${x.total}</span></button>`).join("")}</div>`;
  const side = `<div class="daevside">
      <div class="counter"><small>Points used</small> ${d.used} / ${d.budget ?? "Unknown"}</div>
      <h4>${esc(b.name)} board</h4><div class="small">${b.used} / ${b.total} points · ${b.nodes.filter((x) => x.selected).length} nodes</div>
      <h4>Skill levels</h4>${d.skills.map((s) => `<div class="small">${esc(s.name)} <b class="gold">+${s.levels}</b></div>`).join("") || '<div class="faint small">none</div>'}
      <h4>Stats (all boards)</h4>${d.stats.map((s) => `<div class="small">${esc(s.label)} <b>${esc(s.text)}</b></div>`).join("")}
    </div>`;
  const legend = `<div class="legend"><span><i style="background:#c9ccd3"></i>Common 1 pt</span><span><i style="background:#4aa3e6"></i>Rare 2 pt</span>
    <span><i style="background:#a46cf0"></i>Epic 3 pt</span><span><i style="background:#f0bf4a"></i>Unique 4 pt</span>
    <span>squares = stats · circles = +1 skill level · bright = take it</span></div>`;
  const copy =
    d.boards.map((x) => `${x.name}: ${x.used}/${x.total} pts`).join("\n") +
    (v.links?.metabot_daevanion ? `\nPlanner link: ${v.links.metabot_daevanion}` : "");
  const tools = v.links?.metabot_daevanion
    ? `<a class="btn small" target="_blank" href="${esc(v.links.metabot_daevanion)}">Open in metabot planner</a>`
    : "";
  return win(
    "Daevanion",
    "",
    tabs +
      `<div class="daev">${side}<div><div class="board-wrap"><div class="board"
      style="grid-template-columns:repeat(${b.cols},34px);grid-template-rows:repeat(${b.rows},34px)">${cells}</div></div>${legend}</div></div>` +
      statGrid(d.stats),
    { key: "daevanion-" + b.name, copy, tools },
  );
}

const LEFT_SLOTS = [
  "MainHand",
  "SubHand",
  "Helmet",
  "Shoulder",
  "Torso",
  "Pants",
  "Gloves",
  "Boots",
  "Cape",
  "Belt",
  "Main hand",
  "Off-hand",
  "Armor x7",
];
function slotTile(s) {
  const extras = [];
  (s.rolls || []).forEach(([k, val]) => extras.push(`<span class="chip">${esc(k)} ${esc(val)}</span>`));
  (s.manastones || []).forEach(([k, val]) =>
    extras.push(`<span class="chip gold" title="Manastone">${esc(k)} ${esc(val)}</span>`),
  );
  (s.theostones || []).forEach((t) => extras.push(`<span class="chip gold">${esc(t)}</span>`));
  (s.skills || []).forEach(([k, lv]) =>
    extras.push(`<span class="chip" style="color:var(--gold)">${esc(k)} +${lv}</span>`),
  );
  const st = (s.stats || [])
    .slice(0, 4)
    .map((x) => `<b>${esc(x.text)}</b> ${esc(x.label)}`)
    .join(" · ");
  return `<div class="slot" data-grade="${esc(s.grade || "")}">
      <div class="icon sm with-fallback"><span class="asset-placeholder" aria-hidden="true">◇</span>${s.icon ? `<img${assetAttrs("item", s)} src="${icon(s.icon)}" alt="${esc(s.item || s.name || s.slot)}" loading="lazy" onerror="this.hidden=true">` : ""}${s.enchant ? `<span class="lv">+${s.enchant}</span>` : ""}</div>
      <div><div class="sl">${esc(s.slot)}</div><div class="gname">${esc(s.item || s.name || "")}</div>
        <div class="st">${st}</div>${extras.length ? `<div>${extras.join("")}</div>` : ""}${s.source ? `<div class="faint small">${esc(s.source)}</div>` : ""}</div>
    </div>`;
}
function winEquipment(v) {
  const e = v.equipment;
  const left = e.slots.filter((s) => LEFT_SLOTS.includes(s.slot));
  const right = e.slots.filter((s) => !LEFT_SLOTS.includes(s.slot));
  const doll = `<div class="doll"><div><div class="cls">${esc(cap(v.class))}</div><div class="small">${esc(v.name ? `${v.name} · ${v.server}` : v.loadout_name || "")}</div>
      ${v.combat_power ? `<div class="gold">Combat Power ${n0(v.combat_power)}</div>` : ""}</div></div>`;
  let rolls = "";
  if (e.rolls && Object.keys(e.rolls).length) {
    rolls = `<div class="grid2" style="margin-top:12px"><div><h4 class="gold small">KEEP / REROLL TOWARD (best first)</h4>${Object.entries(
      e.rolls,
    )
      .slice(0, 8)
      .map(
        ([slug, rs]) =>
          `<div class="small"><b>${esc(slug.replace(/-/g, " "))}</b>: ${rs.map((r) => esc(r.stat)).join(" › ")}</div>`,
      )
      .join("")}</div>
      <div><h4 class="gold small">ENCHANT PRIORITY</h4>${(e.enchant || []).map((r) => `<div class="small">${esc(r.slot)} <b>${r.dps.toFixed(1)}</b> DPS / level</div>`).join("")}</div></div>`;
  }
  const copy = e.slots.map((s) => `${s.slot}: ${s.item || s.name}`).join("\n");
  return win(
    "Equipment",
    v.equipment_source || (v.name ? "current gear (official profile)" : "loadout used for this build"),
    `<div class="paperdoll"><div class="slots">${left.map(slotTile).join("")}</div>${doll}<div class="slots">${right.map(slotTile).join("")}</div></div>` +
      rolls +
      statGrid(e.total, "Stats from equipment, rolls and manastones"),
    { key: "equipment", copy },
  );
}

function winArcana(v) {
  const ex = v.extras || {};
  let body = "";
  if (v.arcana_items && v.arcana_items.length) {
    body += `<div class="cards">${v.arcana_items
      .map(
        (a) => `<div class="card" data-grade="${esc(a.grade)}">
      <div class="icon" style="margin:0 auto 6px">${a.icon ? `<img src="${icon(a.icon)}">` : ""}<span class="lv">+${a.enchant || 0}</span></div>
      <div class="gname">${esc(a.name)}</div>${(a.skills || []).map(([k, lv]) => `<span class="chip">${esc(k)} +${lv}</span>`).join("")}
      <div class="small muted">${(a.stats || []).map((s) => esc(s.label + " " + s.text)).join(", ")}</div></div>`,
      )
      .join("")}</div>`;
  }
  if (ex.arcana && ex.arcana.length) {
    body += `<h4 class="gold small" style="margin-top:12px">RECOMMENDED VARIANT PER SLOT</h4><div class="cards">${ex.arcana
      .map(
        (a) => `<div class="card">
      <div class="t">${esc(a.slot)}</div><div class="pick">${a.tie ? "Either variant" : esc(a.pick)}</div>
      <div class="alt">${Object.entries(a.variants)
        .map(([k, s]) => `${esc(k)}: ${esc(s)}`)
        .join("<br>")}</div></div>`,
      )
      .join("")}</div>`;
  }
  const rolls = ex.arcana_rolls || {};
  if (Object.keys(rolls).length) {
    const rows = Object.entries(rolls).sort((a, b) => b[1].expected_unique_5 - a[1].expected_unique_5);
    body += `<h4 class="gold small" style="margin-top:14px">SKILL ROLLS — value of each arcana slot (Unique: 4 rolls at +0, 9 at +5)</h4>
      <table class="t"><tr><th>Slot</th><th class="r">Unique +0</th><th class="r">Unique +5</th><th>Best rolls (+1 / +2)</th></tr>
      ${rows
        .map(
          ([
            slot,
            a,
          ]) => `<tr><td class="gold">${esc(cap(slot))}</td><td class="r">+${a.expected_unique_0.toFixed(1)}%</td><td class="r">+${a.expected_unique_5.toFixed(1)}%</td>
        <td class="small">${Object.entries(a.skills)
          .sort((x, y) => y[1][1] - x[1][1])
          .slice(0, 4)
          .map(
            ([k, g]) =>
              `${esc(k)} ${g[0] >= 0 ? "+" : ""}${g[0].toFixed(1)}% / ${g[1] >= 0 ? "+" : ""}${g[1].toFixed(1)}%`,
          )
          .join(" · ")}</td></tr>`,
        )
        .join("")}</table>`;
  }
  const deity = ex.deity || [];
  return (
    win(
      "Arcana",
      "Chalice, Parchment, Compass roll active skills · Bell, Mirror roll passives",
      body || '<div class="empty">No arcana data</div>',
      { key: "arcana", copy: (ex.arcana || []).map((a) => `${a.slot}: ${a.tie ? "either" : a.pick}`).join("\n") },
    ) + (deity.length ? win("Deity & primary stats", "", statGrid(deity, "Totals")) : "")
  );
}

function winTitles(v) {
  const ex = v.extras || {};
  const cur = (ex.titles || [])
    .map(
      (t) => `<div class="slot"><div class="icon sm"></div><div><div class="sl">${esc(t.slot)}</div>
     <div class="gname">${esc(t.item)}</div><div class="st">${t.stats.map((s) => `<b>${esc(s.text)}</b> ${esc(s.label)}`).join(" · ")}</div></div></div>`,
    )
    .join("");
  const rank = (ex.title_ranking || [])
    .map(
      (t) =>
        `<tr><td class="gname" data-grade="${esc(t.grade)}">${esc(t.name)}</td><td class="small">${esc(t.equip)}</td><td class="small muted">${esc(t.owned)}</td></tr>`,
    )
    .join("");
  const wings = (ex.wings || [])
    .map(
      (
        w,
      ) => `<div class="slot" data-grade="Unique"><div class="icon sm">${ex.wing?.icon ? `<img src="${icon(ex.wing.icon)}">` : ""}</div>
     <div><div class="sl">Wings</div><div class="gname">${esc(w.item)}</div><div class="st">${w.stats.map((s) => `<b>${esc(s.text)}</b> ${esc(s.label)}`).join(" · ")}</div></div></div>`,
    )
    .join("");
  const pet = ex.pet
    ? `<div class="slot"><div class="icon sm">${ex.pet.icon ? `<img src="${icon(ex.pet.icon)}">` : ""}</div><div><div class="sl">Pet</div>
     <div class="gname">${esc(ex.pet.name)} <span class="muted">Lv ${esc(ex.pet.level)}</span></div><div class="st">Pet bonuses are mostly against one monster genus.</div></div></div>`
    : "";
  return win(
    "Titles, wings & pet",
    "",
    `<div class="grid2"><div class="slots">${cur}${wings}${pet}</div>
      <div><h4 class="gold small">BEST TITLES FOR THIS BUILD</h4><table class="t"><tr><th>Title</th><th>Equip bonus</th><th>Owned bonus</th></tr>${rank}</table></div></div>` +
      statGrid(ex.titles_total, "Stats from equipped titles"),
    { key: "titles" },
  );
}

function rotationIcon(s) {
  return `<div class="hotbar-icon">${s.icon ? `<img src="${esc(icon(s.icon))}" alt="" onerror="this.hidden=true">` : ""}<b class="hotbar-key">${esc(s.binding || "")}</b><span class="hotbar-level">Lv ${n0(s.level)}</span></div>`;
}
function winHotbar(v) {
  const h = v.hotbar;
  if (!h)
    return win(
      "Skills hotbar",
      "",
      '<div class="empty">Optimize your build to generate its hotbar and macro setup.</div>',
    );
  const rows = [];
  const total = Math.max(12, Math.ceil(h.slots.length / 12) * 12);
  for (let first = 0; first < total; first += 12) {
    rows.push(
      `<div class="hotbar-row"><span class="hotbar-row-label">${first / 12}</span>${Array.from(
        { length: 12 },
        (_, i) => {
          const s = h.slots[first + i];
          return s
            ? `<div class="hotbar-slot ${s.manual ? "manual" : "automatic"}" title="${esc(s.name)} — ${s.manual ? "Manual" : "Macro"}${s.charged ? "; hold to charge" : ""}">
        ${rotationIcon(s)}<span class="hotbar-name">${esc(s.name)}</span><small>${s.charged ? "Hold to charge" : s.manual ? "Manual" : "Macro"}</small></div>`
            : '<div class="hotbar-slot empty-slot"><span>+</span></div>';
        },
      ).join("")}</div>`,
    );
  }
  const copy =
    h.slots
      .map((s) => `${s.binding}: ${s.name} (${s.charged ? "manual hold to charge" : s.manual ? "manual" : "macro"})`)
      .join("\n") + `\nSuggested macro key: ${h.macro_binding}`;
  return win(
    "Skills hotbar",
    "suggested key bindings",
    `<p>Place each skill on your hotbar and assign the key shown on its icon. These are suggested bindings: match your in-game Key Settings, or use your own keys consistently in both tabs.</p>
    <div class="hotbar-wrap">${rows.reverse().join("")}</div>
    <p><b class="gold">Manual / Hold to charge:</b> keep these skills outside the macro. Hold a charge skill’s own key, then release it at the required charge level.</p>
    <p>Reserve <kbd>${esc(h.macro_binding)}</kbd> for the macro, then follow <b>Macro &amp; rotation</b>. Hotbar positions are key bindings; the numbered macro rows are the order the macro tries skills.</p>`,
    { key: "hotbar", copy },
  );
}
function winMacro(v) {
  const m = v.macro,
    r = v.rotation;
  if (!m || !r) return win("Skill Macro", "", '<div class="empty">No macro (run an optimization)</div>');
  const chainNote = (s) =>
    s.chain_of
      ? `<div class="small muted">${esc(s.chain_of)}’s chain: press ${esc(s.chain_of)} again while the chain is open</div>`
      : "";
  const manual = r.manual
    .map(
      (s) =>
        `<div class="manual-skill">${rotationIcon(s)}<div><b>${esc(s.name)}</b>${chainNote(s)}<div class="small muted">${s.charged ? `Hold this skill’s key${s.charge_level ? ` to charge level ${s.charge_level}` : " to charge"}, then release. Never add it as a macro tap.` : "Press manually when ready."}${s.condition ? ` Use ${esc(s.condition)}.` : ""}</div></div></div>`,
    )
    .join("");
  const steps = r.steps
    .map(
      (
        s,
        i,
      ) => `<div class="macro-step"><strong class="macro-number">${i + 1}</strong><div>${rotationIcon(s)}<b>${esc(s.name)}</b>${chainNote(s)}</div><span class="macro-key-label">Hotbar key <kbd>${esc(s.binding)}</kbd></span></div>
    ${i < r.steps.length - 1 ? '<div class="macro-delay"><span></span>Delay <b>10</b> ms<span></span></div>' : ""}`,
    )
    .join("");
  const copy =
    r.steps
      .map(
        (s, i) =>
          `${i + 1}. ${s.name}${s.chain_of ? ` (${s.chain_of}’s chain: ${s.chain_of} again)` : ""} — hotbar key ${s.binding}; delay 10 ms`,
      )
      .join("\n") +
    (r.manual.length
      ? "\nManual: " + r.manual.map((s) => `${s.name} (${s.binding}${s.charged ? "; hold to charge" : ""})`).join(", ")
      : "");
  const body = `<ol class="macro-instructions"><li>Copy the suggested bindings from <b>Skills hotbar</b>, or substitute your own.</li>
    <li>Open <b>Settings → Key Settings → General → Skill Macro</b>. Add the skills below once each, from top to bottom. The large numbers are macro steps, not hotbar keys. A skill’s key presses its chain step while the chain is open, in the macro too; a chain step listed below is its skill added again.</li>
    <li>Set each step’s delay to <b>10 ms</b>, enable <b>Skill Queue</b>, and save the macro to an unused key (suggested: <kbd>${esc(v.hotbar?.macro_binding || "Right-click")}</kbd>).</li>
    <li>Hold the macro key during combat. Release it to use a manual skill; charge skills need their own button held before release. Resume the macro afterwards.</li></ol>
    <div class="macro-layout"><div class="macro-editor"><h3>Macro</h3>${steps || '<p class="muted">This rotation uses manual skills only.</p>'}<div class="macro-save">Save to ${esc(v.hotbar?.macro_binding || "Right-click")} in game</div></div>
    <div><h4 class="gold">MANUAL SKILLS</h4>${manual || '<p class="muted">No manual skills for this rotation.</p>'}
    <p class="small muted">${m.needs_refresh ? "This saved build predates charge-aware macros. Charged skills have been moved to manual controls; optimize again to recalculate the macro estimate." : `Estimated macro + manual execution: ${pct(m.dps_macro / m.dps_priority)} of the ideal priority rotation. This assumes you use the manual skills, including their charges.`}</p>
    <h4 class="gold small">WHEN MULTIPLE SKILLS ARE READY</h4><p class="small muted">This priority list explains the optimizer’s decisions. It is not another macro to copy.</p><ol>${r.priority.map((s) => `<li>${esc(s.name)}${s.chain_of ? ` <span class="muted">(${esc(s.chain_of)}’s chain)</span>` : ""}${s.condition ? ` <span class="muted">(${esc(s.condition)})</span>` : ""}</li>`).join("")}</ol></div></div>`;
  return win("Skill Macro & rotation", "", body, { key: "macro", copy });
}

function cooldownSummary(checks, scope = "reduction windows") {
  if (!checks?.length) return "";
  return `<ul>${checks.map((c) => `<li>${esc(c.skill)} · starts: ${c.activation_starts_s.map((t) => `${esc(t)}s`).join(", ") || "none"} · ${c.status === "no_active_windows" ? `No active ${esc(scope)}` : c.cooldown_s == null ? "Cooldown unknown · reuse not assessed" : `Assumed effective cooldown ${esc(c.cooldown_s)}s · ${c.shortest_reuse_gap_s == null ? "No repeated activation" : `shortest reuse gap ${esc(c.shortest_reuse_gap_s)}s`} · assumed spacing satisfied`}${c.mixed_assumptions ? " · largest of differing assumptions used" : ""}</li>`).join("")}</ul>`;
}
function rotationReservationSummary(rows) {
  if (!rows?.length) return "";
  return `<h4>Cooldown reservations in the damage rotation</h4><ul>${rows.map((r) => `<li>Skill #${esc(r.skill_id)} · assumed use ${esc(r.start_s)}s · entered cooldown ${esc(r.cooldown_s)}s · ${r.status === "reserved" ? `reserved in modeled group(s): ${r.cooldown_groups.map(esc).join(", ")} · matching actions: ${r.matched_actions.map(esc).join(", ")}` : "Unavailable: no matching modeled action; no rotation cooldown reserved"}</li>`).join("")}</ul>`;
}
function actionTimingSummary(timing) {
  if (!timing) return "";
  return `<section class="note"><h3>Outgoing action-time assumptions</h3><ul>${timing.windows.map((w) => `<li>${esc(w.name)} · ${esc(w.start_s)}–${esc(w.end_s)}s${w.reserve_cooldown ? " · Rotation cooldown reservation requested" : ""}${w.skill_requirement ? `<br>Requested retention: ${esc(w.skill_requirement.name)} · trained Lv ${esc(w.skill_requirement.minimum)}${w.skill_requirement.effect ? ` · ${esc(w.skill_requirement.effect)}` : ""}` : " · Unlinked assumption"}</li>`).join("")}</ul>${Object.entries(
    timing.cases,
  )
    .map(
      ([name, c]) =>
        `<p>${esc(name)} · ${esc(c.paused_s)}s unavailable for new actions / ${esc(c.duration_s)}s · clipped interval union: ${c.blocks.map(([a, b]) => `${esc(a)}–${esc(b)}s`).join(", ") || "none"}</p>${cooldownSummary(c.cooldown_checks, "action-time windows in this scenario")}${rotationReservationSummary(c.rotation_reservations)}`,
    )
    .join("")}<p class="small muted">${esc(timing.note)}</p></section>`;
}
function survivalSummary(plan) {
  if (!plan) return "";
  return `<section class="note"><h3>HP reserve · constrained damage optimization</h3><p>Crystal-board flat HP: <b>${n0(plan.selected_node_hp)}</b> · requested floor: ${n0(plan.minimum_node_hp)} · previous contribution: ${n0(plan.reference_node_hp)}. ${plan.meets_node_floor ? "Reserve met." : "Reserve not met."}</p>
    ${plan.estimated_total_hp_proxy != null ? `<p>Estimated total HP proxy: ${n0(plan.estimated_total_hp_proxy)} · worst assumed headroom: ${plan.worst_headroom_hp == null ? "Not assessed" : n0(plan.worst_headroom_hp)}</p>` : ""}
    ${plan.opponents?.length ? `<div class="cr-scroll"><table class="t"><tr><th>Assumed encounter / opponent</th><th>Hit + pressure + reserve</th><th>HP headroom (proxy)</th></tr>${plan.opponents.map((row) => `<tr><td>${esc(row.name)}<br><small>${row.recorded_evidence ? "Imported recording · editable assumption" : "User assumption"} · ${row.window_s}s window${row.recorded_evidence ? `<br>${esc(row.recorded_evidence.title)} · ${esc(row.recorded_evidence.recipient)} · recorded peak ${esc(row.recorded_evidence.damage)} HP (${esc(row.recorded_evidence.start_s)}–${esc(row.recorded_evidence.end_s)}s)` : ""}</small>${row.opponent_benchmark ? `<br><small>Opponent benchmark (editable assumption): ${esc(row.opponent_benchmark.title)} · ${esc(row.opponent_benchmark.metric)} ${esc(row.opponent_benchmark.modeled_dps)} modeled DPS × ${esc(row.opponent_benchmark.scale)} · source duration ${esc(row.opponent_benchmark.source_duration_s)}s. Not measured incoming damage.</small><details><summary>Source benchmark assumptions</summary><div class="small">Class: ${esc(row.opponent_benchmark.class)} · saved timestamp: ${esc(row.opponent_benchmark.created)} · duration: ${esc(row.opponent_benchmark.duration_source)}<p>${esc(row.opponent_benchmark.model_note)}</p><p>Source model version and cross-version comparability are not verified. The original score remains separate from the editable pressure fields.</p></div></details>` : ""}${row.peak_pressure_hp != null ? `<br><small>Peak ongoing pressure ${n0(row.peak_pressure_hp)} HP at ${esc(row.peak_pressure_at_s)}s · healing delay ${esc(row.healing_delay_s)}s · active ${esc(row.healing_active_s)}s</small>` : ""}${row.reductions?.length ? `<details><summary>Assumed defense / control / movement timing</summary><ul>${row.reductions.map((w) => `<li>${esc(w.name)} · ${esc(w.kind)}: ${esc(w.reduction_pct)}% from ${esc(w.start_s)}s to ${esc(w.end_s)}s (${esc(w.active_s)}s active)${w.skill_requirement ? `<br>Retain ${esc(w.skill_requirement.name)} · trained Lv ${esc(w.skill_requirement.minimum)}${w.skill_requirement.effect ? ` · ${esc(w.skill_requirement.effect)}` : ""}` : " · Unlinked assumption"}</li>`).join("")}</ul><p class="small">Same healing without added reductions: ${n0(row.unprotected_required_hp)} HP required. Assumed requirement reduction: ${n0(row.assumed_requirement_reduction_hp)} HP. Initial hit unchanged; strongest overlap only. No skill casts or tactical success are simulated.</p>${cooldownSummary(row.cooldown_checks)}</details>` : ""}</td><td>${n0(row.required_hp)}</td><td>${n0(row.headroom_hp)} · ${row.meets_assumed_pressure ? "Meets assumed HP requirement" : "Below requirement"}</td></tr>`).join("")}</table></div>` : ""}
    <p>${plan.binding_opponents?.length ? `Strictest incoming requirement: ${plan.binding_opponents.map(esc).join(" · ")}` : ""}</p><p class="small muted">${esc(plan.note)}</p>${
      plan.opponents?.some((r) => r.damage_trace)
        ? `<details><summary>Imported expected-hit schedules</summary>${plan.opponents
            .filter((r) => r.damage_trace)
            .map(
              (r) =>
                `<h4>${esc(r.name)}</h4><p>Source ${esc(r.opponent_benchmark?.source_start_s)}–${esc(r.opponent_benchmark?.source_end_s)}s · ${r.damage_trace.events.length} hits · ${n0(r.damage_trace.total)} scaled damage · peak deficit at ${esc(r.peak_pressure_at_s)}s</p><div class="cr-scroll" style="max-height:240px"><table class="t"><tr><th>Window time</th><th>Expected incoming damage</th></tr>${r.damage_trace.events
                  .slice(0, 200)
                  .map(([t, amount]) => `<tr><td>${t.toFixed(3)}s</td><td>${n0(amount)}</td></tr>`)
                  .join(
                    "",
                  )}</table></div>${r.damage_trace.events.length > 200 ? '<p class="small muted">First 200 hits displayed; all saved hits are evaluated.</p>' : ""}`,
            )
            .join("")}</details>`
        : ""
    }<p class="small muted">DPS is maximized subject to this HP floor. These personal constraints are not compared against damage-only community presets.</p></section>`;
}
function skillReserveSummary(plan) {
  if (!plan) return "";
  return `<section class="note"><h3>Trained skill reserves · ${plan.met ? "met" : "not met"}</h3><table class="t"><tr><th>Skill</th><th>Minimum</th><th>Selected</th></tr>${plan.skills.map((row) => `<tr><td>${esc(row.name)}</td><td>${row.minimum}</td><td>${row.selected}</td></tr>`).join("")}</table>${plan.effects?.length ? `<h4>Reserved supporting effects</h4><ul>${plan.effects.map((e) => `<li>${esc(e.skill)} · ${esc(e.text)} (effect Lv ${esc(e.unlock)}) · ${e.selected ? "retained" : "missing"}</li>`).join("")}</ul>` : ""}${plan.effective_levels?.length ? `<h4>Required effective levels</h4><ul>${plan.effective_levels.map((r) => `<li>${esc(r.name)} · Lv ${esc(r.selected)} / required ${esc(r.minimum)} (trained ${esc(r.trained)} + Daevanion ${esc(r.daevanion)} + fixed bonuses ${esc(r.gear)})</li>`).join("")}</ul>` : ""}<p class="small muted">${esc(plan.note)}</p></section>`;
}
function winOverview(v) {
  const dps = v.dps || {};
  const st = v.stats || {};
  const kpis = `<div class="kpis">${Object.entries(dps)
    .map(([k, x]) => `<div class="kpi"><div class="k">${esc(k)} DPS</div><div class="v">${n0(x)}</div></div>`)
    .join("")}
    ${v.baseline ? `<div class="kpi"><div class="k">Typical top build</div><div class="v">${n0(v.baseline.community_optimized_rotation)}</div></div>` : ""}
    <div class="kpi"><div class="k">Crit chance</div><div class="v">${pct(st.crit_chance_vs_target)}</div></div>
    <div class="kpi"><div class="k">Cooldown red.</div><div class="v">${pct(st.cdr)}</div></div>
    <div class="kpi"><div class="k">Combat speed</div><div class="v">${pct(st.combat_speed)}</div></div></div>`;
  const w = (v.weights || [])
    .map(
      (x) =>
        `<tr><td>${esc(x.label)}</td><td class="r num">${x.pct >= 0 ? "+" : ""}${x.pct.toFixed(2)}%</td><td style="width:45%"><div class="bar"><i style="width:${Math.max(0, Math.min(100, x.pct * 25))}%"></i></div></td></tr>`,
    )
    .join("");
  const sh = Object.entries(v.shares || {})
    .slice(0, 12)
    .map(
      ([k, x]) =>
        `<tr><td>${esc(k)}</td><td style="width:55%"><div class="bar"><i style="width:${(100 * x) / Math.max(...Object.values(v.shares))}%"></i><span>${pct(x)}</span></div></td></tr>`,
    )
    .join("");
  return win(
    "Overview",
    esc(v.loadout_name || ""),
    kpis +
      (v.objective
        ? `<div class="note"><b>${esc(v.objective.label)}: ${n0(v.objective.score)}</b><br>${Object.entries(
            v.objective.weights || {},
          )
            .map(
              ([name, weight]) =>
                `${esc(name)} ${pct(weight)}${v.objective.durations?.[name] ? " · " + n0(v.objective.durations[name]) + "s" : ""} · ${n0(v.objective.components?.[name])} DPS`,
            )
            .join(" · ")}<p class="small muted">${esc(v.objective.note)}</p></div>`
        : "") +
      (v.scoring_policy
        ? `<div class="note">${v.preset_source === "community" ? "Community" : "Common comparison"} ${esc((v.scoring_policy.mode || "").toUpperCase())} preset · ${n0(v.score)} weighted modeled DPS<br><span class="small">Equal weighting of ${v.scoring_policy.mode === "pvp" ? "sustained and burst player-target damage" : "boss and training-dummy damage"}. Common gear and comparison point budgets. ${v.preset_checked_at ? "Last checked " + esc(whenAt(v.preset_checked_at * 1000)) : ""}</span><details><summary>Comparison assumptions</summary>${esc(v.scoring_policy.note)}<br>Evaluator ${esc(v.scoring_policy.model)}${v.candidate_generation ? `<br>Candidate search: ${esc(v.candidate_generation.objective)} · ${esc(v.candidate_generation.iterations)} iteration(s). Selected by the common weighted score; not a global optimum.${v.candidate_generation.selection ? `<br>${esc(v.candidate_generation.selection.method)}${(v.candidate_generation.selection.candidates || []).map((c) => `<br>${esc(c.objective)}: ${n0(c.score)} weighted modeled DPS`).join("")}` : ""}` : ""}</details></div>`
        : "") +
      (v.world_pvp
        ? worldPvpHTML(v.world_pvp)
        : v.model_note
          ? `<p class="small muted">${esc(v.model_note)}</p>`
          : "") +
      progressionHTML(v.progression) +
      actionTimingSummary(v.action_timing) +
      survivalSummary(v.survival) +
      skillReserveSummary(v.skill_reserves) +
      `<div class="grid2" style="margin-top:14px"><div><h4 class="gold small">STAT PRIORITY (DPS PER UPGRADE)</h4><table class="t">${w || `<tr><td data-weight-status>${v.weight_job ? "Calculating stat priority…" : "Stat priority is unavailable for this build."}</td></tr>`}</table>${v.scoring_policy ? '<p class="small muted">Weighted upgrade gains with the saved rotation held fixed; timing is not re-optimized.</p>' : ""}</div>
     <div><h4 class="gold small">DAMAGE SHARE</h4><table class="t">${sh}</table></div></div>`,
    { key: "overview" },
  );
}

function worldPvpHTML(w) {
  if (!w) return "";
  const t = w.typical_build || {};
  const row = (label, x, y, fmt) =>
    `<tr><td>${label}</td><td class="r num">${fmt(x)}</td><td class="r num">${y == null ? "—" : fmt(y)}</td></tr>`;
  return `<section class="note" data-world-pvp><h4>World PvP</h4><div class="tablewrap"><table class="t small"><tr><th><span class="sr-only">Measure</span></th><th class="r">This build</th><th class="r">Typical build</th></tr>
    ${row("Score (DPS × share of the fight survived)", w.score, t.score, n0)}${row("Damage on up to " + esc(w.assumptions?.enemies_in_reach ?? 3) + " players (DPS)", w.dps, t.dps, n0)}
    ${row("Share of the fight survived", w.alive_share, t.alive_share, pct)}${row("Effective HP", w.effective_hp, t.effective_hp, n0)}${row("Hard crowd control (s per minute)", w.control_s_per_min, t.control_s_per_min, (x) => x.toFixed(1))}</table></div>
    <p class="small muted">${esc(w.attackers)} attackers · ${pct(w.controlled)} of their time under your crowd control · damage taken ${pct(w.damage_taken)} of an undefended player's.</p><p class="small muted">${esc(w.note || "")}</p></section>`;
}
function genusTargetsHTML(targets) {
  if (!targets) return "";
  const rows = (targets.rows || [])
    .map(
      (r) =>
        `<tr><td>${esc(r.genus)} · ${r.level == null ? "level not recorded" : "Lv " + r.level}</td><td>${r.slot}</td><td>${esc(r.stat)}</td><td>${r.current ? esc(r.current.stat) + " " + esc(r.current.value) : "Not recorded"}</td><td><b>${esc(r.target)}</b><br><small>Catalog range ${esc(r.range)}</small></td><td>${esc(r.status)}</td></tr>`,
    )
    .join("");
  return `<section class="note"><h4>Genus roll targets</h4>${rows ? `<div class="tablewrap"><table class="t"><tr><th>Genus level</th><th>Slot</th><th>Effect</th><th>Saved line</th><th>Target value</th><th>Next step</th></tr>${rows}</table></div>` : ""}<p class="small muted">${esc(targets.note)}</p>${targets.source ? `<p class="small muted">Catalog basis: ${esc(targets.source)}</p>` : ""}</section>`;
}
function genusRollsHTML(rolls, genus) {
  const r = rolls?.genera?.[genus];
  if (!r) return "";
  const best = (r.best || [])
    .map(
      (x) =>
        `<li>Slot ${x.slot}: <b>${esc(x.stat)}</b> <span class="faint">${esc(x.grade)} ${esc(x.range)}</span> <span class="gain up">${sp(x.gain)}</span></li>`,
    )
    .join("");
  const rows = Object.entries(r.slots || {})
    .map(
      ([n, x]) =>
        `<tr><td>${n}</td><td>${x.aim?.[0] ? `<b>${esc(x.aim[0].stat)}</b> <span class="faint">${esc(x.aim[0].grade)} ${esc(x.aim[0].range)}</span> <span class="gain up">${sp(x.aim[0].gain)}</span>` : '<span class="faint">No modeled line</span>'}</td><td>${(
          x.aim || []
        )
          .slice(1, 3)
          .map((y) => `${esc(y.stat)} <span class="faint">${sp(y.gain)}</span>`)
          .join(
            "<br>",
          )}</td><td>${x.current ? esc(x.current.stat) + " " + esc(x.current.value) : "Not recorded"}</td><td>${esc(x.status)}</td><td class="faint">${x.options} (${x.unmodeled} unmodeled)</td></tr>`,
    )
    .join("");
  return `<section class="note" data-genus-rolls><h4>Roll for · ${esc(genus)}</h4>${best ? `<ol class="small">${best}</ol>` : '<p class="small faint">No modeled candidate for this genus.</p>'}<div class="tablewrap"><table class="t small"><tr><th>Slot</th><th>Roll for (best listed grade)</th><th>Then</th><th>Saved line</th><th>Next step</th><th>Options</th></tr>${rows}</table></div><p class="small muted">${esc(rolls.basis || "")}. ${esc(rolls.note || "")}</p></section>`;
}
function genusCoverageHTML(g) {
  const c = g?.coverage;
  if (!c) return "";
  return `<section class="note"><h4>Genus coverage</h4><p>${c.recorded_genera} / 5 levels recorded · ${c.recorded_lines} saved lines · ${c.modeled_lines} damage effects included</p><div class="tablewrap"><table class="t"><tr><th>Genus</th><th>Recorded level</th><th>Saved / unlocked slots</th><th>Next milestone</th></tr>${c.genera.map((r) => `<tr><td>${esc(r.genus)}</td><td>${r.level == null ? "Not recorded" : r.level}</td><td>${r.unlocked_slots == null ? "Unknown" : r.recorded_lines + " / " + r.unlocked_slots}${r.missing_lines ? " · " + r.missing_lines + " not recorded" : ""}</td><td>${r.level == null ? "Enter level" : r.next_slot_level ? "Lv " + r.next_slot_level + " · slot " + r.next_slot_level : r.next_grade_level ? "Lv 10 · grade chances" : "Catalog level cap"}</td></tr>`).join("")}</table></div><p class="small muted">${esc(c.note)}</p><details><summary>Catalog basis</summary><p class="small muted">${esc(c.source)} · catalog cap Lv ${c.catalog_max_level}, ${c.catalog_slots} slots. Current build applicability and owned collection completion are not verified.</p></details></section>`;
}
function progressionHTML(p) {
  if (!p) return "";
  return `<details class="note"><summary>Point budget provenance</summary><div class="tablewrap"><table class="t"><tr><th>Resource</th><th>Observed spent</th><th>Assumed available</th><th>Assumed unspent</th><th>Basis</th><th>Verified maximum</th></tr>${p.resources.map((r) => `<tr><td>${esc(cap(r.resource))}</td><td>${n0(r.observed_spent)}</td><td>${n0(r.available_assumption)}</td><td>${n0(r.assumed_unspent)}</td><td>${esc(r.source)}</td><td>${r.verified_maximum == null ? "Unknown" : n0(r.verified_maximum)}</td></tr>`).join("")}</table></div><p class="small muted">${esc(p.note)}</p></details>`;
}
function winGenus(v, selected = "Cogni") {
  const g = v.genus,
    genera = ["Cogni", "Fera", "Natura", "Varian", "Special"];
  if (!genera.includes(selected)) selected = "Cogni";
  const snapshot = g?.state || {},
    group = snapshot[selected],
    level = Number.isInteger(group?.level) ? group.level : null;
  const rows = Array.from({ length: 9 }, (_, i) => {
    const slot = i + 1,
      line = (group?.lines || []).find((x) => x.slot === slot),
      score = (g?.lines || []).find((x) => x.genus === selected && x.slot === slot),
      locked = level !== null && slot > level;
    return `<tr><td>${slot}</td><td>${locked ? "Locked · opens at Lv " + slot : line ? esc(line.stat) : "Not recorded"}</td><td>${line ? esc(line.value) : "—"}</td><td>${score?.gain == null ? "—" : (100 * score.gain).toFixed(2) + "%"}</td><td>${score ? esc(score.reason || "Included in the damage model") : "—"}</td></tr>`;
  }).join("");
  const anyLines = Object.values(snapshot).some((x) => x?.lines?.length),
    mix = Object.entries(g?.mix || {})
      .map(([k, x]) => `${esc(k)} ${(x * 100).toFixed(1)}%`)
      .join(" · ");
  return win(
    "Pet Genus Insight",
    esc((g?.mode || "").toUpperCase()),
    `
    <p class="note">${anyLines ? (g.enabled ? "Saved manual lines included" : "Genus scoring disabled for this run") : "No Genus analysis lines were recorded in this result."}${g?.roll_targets ? ' "Roll for" below scores every line each slot can roll on this optimized build, whether or not anything is recorded.' : ""} The official profile supplies the equipped pet but does not supply these Insight allocations. <a href="#/character">My Character</a> or <a href="#/gear">Gear &amp; Advice</a> → Pet Genus Insight: enter and save your levels and lines, then recalculate. Saved results keep their original snapshot.</p>
    <div class="genus-report-layout"><div class="genus-selectors" role="group" aria-label="Pet genera">${genera.map((name) => `<button class="btn ${name === selected ? "primary" : ""}" data-result-genus="${name}" aria-pressed="${name === selected}"><b>${esc(name)}</b><small>${Number.isInteger(snapshot[name]?.level) ? "Lv " + esc(snapshot[name].level) : "Not recorded"}</small></button>`).join("")}</div>
    <div>${A2GenusEditor.ringHTML(selected, group)}<p class="small muted">Gold: saved line · gray: not recorded · dim: locked. Recording status, not rarity.</p></div>
    <div class="genus-analysis"><h3>${esc(selected)} Insight · ${level === null ? "Level not recorded" : "Lv " + esc(level) + (level === 10 ? " · MAX" : "")}</h3><div class="tablewrap"><table class="t"><tr><th>Slot</th><th>Analysis effect</th><th>Value</th><th>DPS contribution</th><th>Model status</th></tr>${rows}</table></div></div></div>
    ${genusRollsHTML(g?.roll_targets, selected)}${genusCoverageHTML(g)}${genusTargetsHTML(g?.targets)}${g?.note ? `<details><summary>Model assumptions and line contributions</summary><p class="small muted">${esc(g.note)}</p>${mix ? `<p>${esc(g.mix_source)}: ${mix}</p>` : ""}<p class="small muted">Line contributions are not additive. Defensive effects and roll probabilities are not simulated. No in-game portraits or rarity grades are inferred.</p></details>` : ""}`,
  );
}

const WINDOWS = [
  ["overview", "Overview", "◆"],
  ["skills", "Skills", "✦"],
  ["stigma", "Stigma", "⬢"],
  ["daevanion", "Daevanion", "✧"],
  ["genus", "Pet Genus", "◈"],
  ["equipment", "Equipment", "⚔"],
  ["arcana", "Arcana", "❖"],
  ["titles", "Titles & wings", "♛"],
  ["hotbar", "Skills hotbar", "▦"],
  ["macro", "Macro & rotation", "⌨"],
];
function renderCommonComparisons() {
  document.querySelectorAll("[data-common-comparison]").forEach((root) => {
    const cls = root.dataset.commonClass,
      mode = root.dataset.commonMode,
      key = cls + ":" + mode;
    const state = S.commonComparisons[key],
      running = state?.status === "running";
    const result = state?.result,
      submission = result?.submission;
    let message = state?.message || "";
    if (result)
      message =
        `${result.reused ? "Saved comparison reused" : "Comparison saved"} · ${n0(result.score)} weighted modeled DPS (${result.model}). ` +
        (submission?.reason ||
          (submission?.accepted ? "Community preset updated." : "Current community preset retained."));
    root.innerHTML = `<button class="btn small" data-common-start ${running ? "disabled" : ""}>${running ? "Calculating…" : result ? "Resubmit saved comparison" : "Generate community comparison"}</button><p class="small ${submission?.accepted ? "good" : "muted"}" role="status">${esc(message)}</p>${
      result
        ? `<div class="small muted">${Object.entries(result.dps || {})
            .map(([name, value]) => esc(name) + ": " + n0(value) + " modeled DPS")
            .join(
              " · ",
            )}${submission?.candidate_score != null ? "<br>Server evaluation: " + n0(submission.candidate_score) + " weighted modeled DPS (server policy)." : ""}</div>`
        : ""
    }`;
    root.querySelector("[data-common-start]").onclick = async () => {
      S.commonComparisons[key] = { status: "running", message: "Starting a separate common-budget calculation…" };
      renderCommonComparisons();
      try {
        const { job } = await api("/api/planner/presets/contribute", { class: cls, mode });
        for (;;) {
          await new Promise((resolve) => setTimeout(resolve, 1200));
          const next = await api("/api/jobs/" + job);
          S.commonComparisons[key] = {
            status: next.status,
            message: next.log?.at(-1) || "Waiting for the calculation…",
            result: next.result,
          };
          renderCommonComparisons();
          if (next.status === "error") throw Error(next.error);
          if (next.status === "done") break;
        }
      } catch (error) {
        S.commonComparisons[key] = { status: "error", message: error.message };
        renderCommonComparisons();
      }
    };
  });
}

function renderWindows(v, state, host) {
  const side = `<section class="win sidemenu"><div class="wb">${WINDOWS.map(([k, t, ic]) => `<a href="javascript:void 0" data-win="${k}" class="${state.win === k ? "on" : ""}"><span class="ic">${ic}</span>${t}</a>`).join("")}</div></section>`;
  let body;
  switch (state.win) {
    case "skills":
      body = winSkills(v, state.skilltab || "active");
      break;
    case "stigma":
      body = winStigmas(v);
      break;
    case "daevanion":
      body = winDaevanion(v, state.board || 0);
      break;
    case "genus":
      body = winGenus(v, state.genusTab);
      break;
    case "equipment":
      body = winEquipment(v);
      break;
    case "arcana":
      body = winArcana(v);
      break;
    case "titles":
      body = winTitles(v);
      break;
    case "hotbar":
      body = winHotbar(v);
      break;
    case "macro":
      body = winMacro(v);
      break;
    default:
      body = winOverview(v);
  }
  const comparison =
    (state.win || "overview") === "overview"
      ? `<section class="win" style="margin-top:12px"><div class="wb"><details><summary>Contribute a community comparison</summary><p class="small muted">Generate a separate ${String(v.scenario || "").startsWith("pvp") ? "PvP" : "PvE"} example with common gear and the server’s published point budgets (highest reported totals when available; explicitly labeled example fallback otherwise). Your personal build, Genus and HP/skill reserves stay saved separately. Seed searches and weighted refinement can take several minutes; completed comparisons are reused until the scoring inputs change. Only anonymous allocations are submitted. Stationary damage comparison, not a survival or win-rate model.</p><div data-common-comparison></div></details></div></section>`
      : "";
  host.innerHTML = `<div class="layout"><div>${side}</div><div>${body}${comparison}</div></div>`;
  const common = host.querySelector("[data-common-comparison]");
  if (common) {
    common.dataset.commonClass = v.class;
    common.dataset.commonMode = String(v.scenario || "").startsWith("pvp") ? "pvp" : "pve";
    renderCommonComparisons();
  }
  $$("[data-win]", host).forEach(
    (a) =>
      (a.onclick = () => {
        state.win = a.dataset.win;
        renderWindows(v, state, host);
      }),
  );
  $$("[data-skilltab]", host).forEach(
    (b) =>
      (b.onclick = () => {
        state.skilltab = b.dataset.skilltab;
        renderWindows(v, state, host);
      }),
  );
  $$("[data-result-genus]", host).forEach(
    (b) =>
      (b.onclick = () => {
        state.genusTab = b.dataset.resultGenus;
        renderWindows(v, state, host);
      }),
  );
  $$("[data-board]", host).forEach(
    (b) =>
      (b.onclick = () => {
        state.board = +b.dataset.board;
        renderWindows(v, state, host);
      }),
  );
}
