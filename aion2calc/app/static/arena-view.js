// The overlay's arena mode (0.2.395): what the meter overlay shows in the Arena of Solitude, the Arena of Cooperation
// and a battlefield, and what the player cards window shows. Pure builders of the overlay's own markup: the overlay
// page hands them the meter's `arena` reading (aion2calc/meter/session.py `_live_arena`) and its own helpers (`ctx`),
// and writes what they return into its target card, its rows, its clock line and the player cards window.
//
// Layouts: "stacked" (the opponent's card, then DPS, D.Taken and HPS as three sections of the usual bars), "compact"
// (one row per fighter with the three side by side, the default) and "versus" (you and the opponent face each other
// on one card and each metric is a tug-of-war bar). In a team match your own three come first, then the party in the
// metric the overlay's metric chip picks, or all three for everyone with "All 3 for party" on.
(function () {
  "use strict";
  const METRICS = [
    ["dps", "DPS", "d"],
    ["dtps", "D.Taken", "t"],
    ["hps", "HPS", "h"],
  ];
  const num = (v) => Number(v) || 0;
  const pct = (v, total) => (total > 0 ? ((100 * v) / total).toFixed(1) + "%" : "—");

  function fighters(arena) {
    return Array.isArray(arena && arena.fighters) ? arena.fighters : [];
  }
  function find(arena, key) {
    return key ? fighters(arena).find((f) => f.key === key) || null : null;
  }
  // You: your fighter, else your meter row (a match without a roster names you through the party list).
  function you(arena, ctx) {
    const own = find(arena, arena.you) || fighters(arena).find((f) => f.self);
    if (own) return own;
    const row = (ctx.players || []).find((p) => ctx.isMe(p));
    return row ? { key: "row:" + (row.key || row.id), name: row.name, class: row.class, side: "ally", self: true, dps: row.dps, dtps: row.dtps, hps: row.hps } : null;
  }
  // The card's fighter: the opponent of a one-against-one match, else your current target among the enemies.
  function foe(arena) {
    return find(arena, arena.opponent) || find(arena, arena.target);
  }
  const solo = (arena) => arena && arena.kind === "solitude";

  // ---- the card at the top ----------------------------------------------------------------------------------------
  function where(f, ctx) {
    const server = f.server_name || (f.server ? "server " + f.server : "");
    const faction = f.faction ? String(f.faction).replace(/^./, (c) => c.toUpperCase()) : "";
    return [server, faction].filter(Boolean).map(ctx.esc).join(" · ");
  }
  function powerLine(f, ctx) {
    const bits = [];
    if (f.combat_power)
      bits.push(
        `<span class="ovcp" title="Combat power ${num(f.combat_power).toLocaleString()}${f.cp_source === "official" ? ", from the official character service" : ""}">${ctx.sfmt(f.combat_power)}</span>`,
      );
    if (f.gear_score) bits.push(`GS <b>${num(f.gear_score).toLocaleString()}</b>`);
    if (f.class) bits.push(ctx.esc(ctx.cap(f.class)));
    if (f.level) bits.push(`Lv ${ctx.esc(f.level)}`);
    if (f.rating) bits.push(`Rating <b>${num(f.rating).toLocaleString()}</b>`);
    return bits.join(" · ").replace(/<\/span> · /, "</span>");
  }
  function matchLine(arena, f, ctx) {
    if (solo(arena)) {
      const won = num(arena.won),
        lost = num(arena.lost);
      if (arena.result) return `${arena.result === "win" ? "You won" : "You lost"} <b>${won}–${lost}</b>${arena.rating_after ? ` · rating now <b>${num(arena.rating_after).toLocaleString()}</b>` : ""}`;
      if (arena.round) return `Round ${ctx.esc(arena.round)} · ${won > lost ? "you lead" : won < lost ? "you trail" : "level"} <b>${won}–${lost}</b>`;
      return "";
    }
    const bits = [];
    if (f.share_of_your_damage_taken != null) bits.push(`Dealt <b>${Math.round(100 * f.share_of_your_damage_taken)}%</b> of the damage you took`);
    if (f.deaths) bits.push(`Deaths <b>${num(f.deaths)}</b>`);
    return bits.join(" · ");
  }
  function hpOf(f) {
    return f.hp_pct != null && isFinite(f.hp_pct) ? Math.max(0, Math.min(100, 100 * f.hp_pct)) : null;
  }
  function foeCard(arena, ctx) {
    const f = foe(arena);
    if (!f) return "";
    const hp = hpOf(f);
    const art = ctx.classArt(f.class);
    const portrait = `<span class="ovtport" aria-hidden="true">${art ? `<img class="ovtportimg" width="34" height="34" src="${ctx.esc(art)}" alt="">` : ""}</span>`;
    const line2 = matchLine(arena, f, ctx);
    return (
      `${portrait}<span class="ovtmain"><span class="ovthead"><span class="ovtwho"><span class="ovtname">${ctx.esc(f.name)}</span>` +
      `<span class="arn-who">${where(f, ctx)}</span><span class="arn-tag">${solo(arena) ? "Opponent" : "Target"}</span></span>` +
      `${hp != null ? `<span class="ovhp">${hp.toFixed(1)}%</span>` : f.dead ? '<span class="ovhp arn-dead">Dead</span>' : ""}</span>` +
      `${hp != null ? `<span class="ovtbars"><i class="ovtbar ovtbar-hp"><b style="width:${hp.toFixed(1)}%"></b></i></span>` : ""}` +
      `<span class="ovtline">${powerLine(f, ctx)}</span>${line2 ? `<span class="ovtline">${line2}</span>` : ""}</span>`
    );
  }
  function versusSide(f, ctx, right, line) {
    const hp = hpOf(f);
    const art = ctx.classArt(f.class);
    // Two short lines a side: the combat power, then the arena rating (or the gear score where there is none).
    const facts = [f.combat_power ? `CP <b>${ctx.sfmt(f.combat_power)}</b>` : "", f.rating ? `Rating <b>${num(f.rating).toLocaleString()}</b>` : f.gear_score ? `GS <b>${num(f.gear_score).toLocaleString()}</b>` : ""]
      .filter(Boolean)
      .map((fact) => `<div class="ln">${fact}</div>`)
      .join("");
    return (
      `<div class="arn-side${right ? " r" : ""}"><span class="ovtport" aria-hidden="true">${art ? `<img class="ovtportimg" width="34" height="34" src="${ctx.esc(art)}" alt="">` : ""}</span>` +
      `<div class="arn-sidemain"><div class="nm">${ctx.esc(f.name)}</div>${facts}${line ? `<div class="ln">${line}</div>` : ""}` +
      `${hp != null ? `<span class="hp"><b style="width:${hp.toFixed(0)}%"></b></span>` : ""}</div></div>`
    );
  }
  function versusCard(arena, ctx) {
    const me = you(arena, ctx),
      f = foe(arena);
    if (!me || !f) return foeCard(arena, ctx);
    const mine = solo(arena) ? where(me, ctx) : `<b class="d" title="DPS">${ctx.sfmt(me.dps)}</b> · <b class="t" title="Damage taken per second">${ctx.sfmt(me.dtps)}</b> · <b class="h" title="HPS">${ctx.sfmt(me.hps)}</b>`;
    const theirs = solo(arena) ? where(f, ctx) : [where(f, ctx), f.deaths ? `Deaths <b>${num(f.deaths)}</b>` : ""].filter(Boolean).join(" · ");
    return `<div class="arn-vs">${versusSide(me, ctx, false, mine)}<span class="arn-vsmark">VS</span>${versusSide(f, ctx, true, theirs)}</div>`;
  }
  function card(arena, ctx) {
    return ctx.layout === "versus" ? versusCard(arena, ctx) : foeCard(arena, ctx);
  }

  // ---- the rows ---------------------------------------------------------------------------------------------------
  const sec = (html) => `<div class="arn-sec">${html}</div>`;
  const metricLabel = (m) => {
    const found = METRICS.find(([key]) => key === m) || METRICS[0];
    return `<span class="${found[2]}">${found[1]}</span>`;
  };
  // One bar of the meter, as the overlay draws its rows: the class emblem, a name, the rate and the share.
  function row(ctx, f, value, total, max, opts = {}) {
    const name = opts.label || ctx.esc(ctx.name(f));
    const cp = opts.cp && f.combat_power && ctx.showCombatPower ? `<span class="ovcp" title="Combat power ${num(f.combat_power).toLocaleString()}">${ctx.sfmt(f.combat_power)}</span>` : "";
    const dead = f.dead ? '<small class="ovdead">DEAD</small>' : "";
    return (
      `<div class="ovrow arn-row${f.self ? " ovrow-self" : ""}${f.dead ? " ovrow-dead" : ""}"><span class="ovname">${ctx.classIcon(f.class)}<span class="ovnametext">${name}</span>${dead}${cp}</span>` +
      `<div class="ovbar"><i style="width:${max > 0 ? ((100 * num(value)) / max).toFixed(1) : 0}%;--bar:${ctx.barColor(f.class)}"></i><span><span class="ovrate">${ctx.rateText(value)}</span>/s <span class="sub"></span><span class="ovpct">${pct(num(value), total)}</span></span></div></div>`
    );
  }
  function triRow(ctx, f, max) {
    const cp = "";
    return (
      `<div class="ovrow arn-row${f.self ? " ovrow-self" : ""}${f.dead ? " ovrow-dead" : ""}"><span class="ovname">${ctx.classIcon(f.class)}<span class="ovnametext">${ctx.esc(ctx.name(f))}</span>${cp}</span>` +
      `<div class="ovbar"><i style="width:${max > 0 ? ((100 * num(f.dps)) / max).toFixed(1) : 0}%;--bar:${ctx.barColor(f.class)}"></i><span><span class="arn-tri"><b>${ctx.sfmt(f.dps)}</b><b class="t">${ctx.sfmt(f.dtps)}</b><b class="h">${ctx.sfmt(f.hps)}</b></span></span></div></div>`
    );
  }
  function tableHead(first) {
    return `<div class="arn-thead"><span>${first}</span><span class="d">DPS</span><span class="t">D.Taken</span><span class="h">HPS</span></div>`;
  }
  function tableRow(ctx, f, max) {
    const cell = (v, m, cls) => `<div class="arn-cell ${cls}">${ctx.sfmt(v)}<i><b style="width:${m > 0 ? ((100 * num(v)) / m).toFixed(1) : 0}%"></b></i></div>`;
    return (
      `<div class="ovrow arn-table${f.self ? " ovrow-self" : ""}${f.dead ? " ovrow-dead" : ""}"><span class="ovname">${ctx.classIcon(f.class)}<span class="ovnametext">${ctx.esc(ctx.name(f))}</span></span>` +
      `<div class="arn-cols">${cell(f.dps, max[0], "d")}${cell(f.dtps, max[1], "t")}${cell(f.hps, max[2], "h")}</div></div>`
    );
  }
  function tug(ctx, label, a, b, ca, cb) {
    const total = num(a) + num(b),
      share = total > 0 ? (100 * num(a)) / total : 50;
    return (
      `<div class="arn-tug" style="--a:${ca};--b:${cb}"><i class="l" style="width:${share.toFixed(1)}%"></i><i class="r" style="width:${(100 - share).toFixed(1)}%"></i>` +
      `<span>${ctx.sfmt(a)}/s</span><span class="mid">${label}</span><span>${ctx.sfmt(b)}/s</span></div>`
    );
  }
  // The party's rows: the meter's own (the same players, order and figures as outside arena mode).
  function partyFighters(arena, ctx) {
    const rows = (ctx.players || []).map((p) => {
      const own = fighters(arena).find((f) => f.id != null && String(f.id) === String(p.id));
      return { ...(own || {}), key: "row:" + (p.key || p.id), name: p.name, class: p.class || (own && own.class), side: "ally", self: ctx.isMe(p) || !!(own && own.self), dps: p.dps, dtps: p.dtps, hps: p.hps, dead: p.dead, combat_power: p.combat_power || (own && own.combat_power) };
    });
    return rows.length ? rows : fighters(arena).filter((f) => f.side === "ally");
  }
  const maxOf = (list) => METRICS.map(([key]) => Math.max(0, ...list.map((f) => num(f[key]))));
  const sumOf = (list) => METRICS.map(([key]) => list.reduce((n, f) => n + num(f[key]), 0));

  function soloBody(arena, ctx) {
    const me = you(arena, ctx),
      f = foe(arena);
    const pair = [me, f].filter(Boolean);
    if (!pair.length) return "";
    if (ctx.layout === "compact") return tableHead("Fighter") + pair.map((p) => tableRow(ctx, p, maxOf(pair))).join("");
    if (ctx.layout === "versus" && me && f) {
      const [ca, cb] = [ctx.barColor(me.class), ctx.barColor(f.class)];
      return sec(`You <span class="arn-vsword">vs</span> ${ctx.esc(f.name)}`) + METRICS.map(([key, label, cls]) => tug(ctx, `<span class="${cls}">${label}</span>`, me[key], f[key], ca, cb)).join("");
    }
    const max = maxOf(pair),
      sum = sumOf(pair);
    return METRICS.map(([key], i) => sec(metricLabel(key)) + pair.map((p) => row(ctx, p, p[key], sum[i], max[i], { cp: i === 0 })).join("")).join("");
  }
  function teamBody(arena, ctx) {
    const party = partyFighters(arena, ctx);
    const me = you(arena, ctx);
    const max = maxOf(party.length ? party : [me].filter(Boolean)),
      sum = sumOf(party);
    let out = "";
    // Compact with "All 3 for party" is one table, your row marked among the party's: a "You" row above it repeated it (0.2.396).
    if (me && ctx.layout !== "versus" && !(ctx.layout === "compact" && ctx.all3)) {
      if (ctx.layout === "compact") out += tableHead("You") + tableRow(ctx, me, max);
      else
        out +=
          sec(`You · ${ctx.esc(ctx.name(me))}`) +
          METRICS.map(([key, label], i) => row(ctx, me, me[key], sum[i], max[i], { label })).join("");
    }
    if (ctx.all3) {
      if (ctx.layout === "compact") return tableHead("Party") + party.map((p) => tableRow(ctx, p, max)).join("");
      return out + sec(`Party · ${METRICS.map(([key]) => metricLabel(key)).join(" · ")}`) + party.map((p) => triRow(ctx, p, max[0])).join("");
    }
    const key = ctx.metric === "hps" ? "hps" : ctx.metric === "taken" ? "dtps" : "dps";
    const i = METRICS.findIndex(([k]) => k === key);
    const ranked = [...party].sort((a, b) => num(b[key]) - num(a[key]));
    return out + sec(`Party · ${metricLabel(key)}`) + ranked.map((p) => row(ctx, p, p[key], sum[i], max[i], { cp: true })).join("");
  }
  function body(arena, ctx) {
    return solo(arena) ? soloBody(arena, ctx) : teamBody(arena, ctx);
  }

  // ---- the clock line ---------------------------------------------------------------------------------------------
  function clock(arena, ctx) {
    const label = ctx.esc(arena.label || "PvP match");
    if (solo(arena)) {
      const score = arena.round || arena.result ? ` · <b>${num(arena.won)}–${num(arena.lost)}</b>` : "";
      return `<span class="ovclkparty">${label}${score}</span>`;
    }
    const party = partyFighters(arena, ctx);
    const key = ctx.all3 ? "dps" : ctx.metric === "hps" ? "hps" : ctx.metric === "taken" ? "dtps" : "dps";
    const short = key === "hps" ? "HPS" : key === "dtps" ? "DTPS" : "DPS";
    return `<span class="ovclkparty">${label} · Party ${short} <b>${ctx.kfmt(party.reduce((n, p) => n + num(p[key]), 0))}</b></span>`;
  }

  // ---- the player cards window ------------------------------------------------------------------------------------
  function playerCard(ctx, f, grid) {
    const hp = hpOf(f);
    const facts = [f.combat_power ? `<span class="ovcp" title="Combat power ${num(f.combat_power).toLocaleString()}">${ctx.sfmt(f.combat_power)}</span>` : "", f.gear_score ? `GS <b>${num(f.gear_score).toLocaleString()}</b>` : "", f.rating ? `Rating <b>${num(f.rating).toLocaleString()}</b>` : ""].filter(Boolean);
    const dead = f.dead ? ' · <b class="arn-deadtxt">dead</b>' : "";
    const server = ctx.esc(f.server_name || (f.server ? "server " + f.server : ""));
    const you = f.self ? ' <span class="arn-you">you</span>' : "";
    const damage = num(f.dps) * num(ctx.duration);
    if (grid)
      return (
        `<div class="arn-mini ${f.side === "enemy" ? "foe" : "ally"}${f.dead ? " dead" : ""}"><div class="l1">${ctx.classIcon(f.class)}<span class="nm">${ctx.esc(f.name)}</span></div>` +
        `<div class="l2">${server}${you}<br>${facts.join(" · ") || ctx.esc(ctx.cap(f.class || ""))}<br><b>${ctx.sfmt(damage)}</b> damage${dead}</div>` +
        `<span class="hp"><b style="width:${hp != null ? hp.toFixed(0) : f.dead ? 0 : 100}%"></b></span></div>`
      );
    return (
      `<div class="arn-card ${f.side === "enemy" ? "foe" : "ally"}${f.dead ? " dead" : ""}">${ctx.classIcon(f.class)}<div class="who"><div class="l1"><span class="nm">${ctx.esc(f.name)}</span><small>${server}</small>${you}</div>` +
      `<div class="l2">${facts.join(" ") || ctx.esc(ctx.cap(f.class || ""))}${dead}</div><span class="hp"><b style="width:${hp != null ? hp.toFixed(0) : f.dead ? 0 : 100}%"></b></span></div>` +
      `<div class="dmg">${ctx.sfmt(damage)}<small>damage</small></div></div>`
    );
  }
  function players(arena, ctx) {
    const all = fighters(arena);
    const allies = all.filter((f) => f.side !== "enemy"),
      enemies = all.filter((f) => f.side === "enemy");
    const order = (list) => [...list].sort((a, b) => num(b.dps) - num(a.dps));
    const head = (cls, label, list) => sec(`<span class="${cls}">${label} · ${list.length}</span>`);
    if (ctx.style === "grid")
      return (
        `<div class="arn-grid"><div>${head("arn-allies", "Allies", allies)}<div class="cards">${order(allies).map((f) => playerCard(ctx, f, true)).join("")}</div></div>` +
        `<div>${head("arn-enemies", "Enemies", enemies)}<div class="cards">${order(enemies).map((f) => playerCard(ctx, f, true)).join("")}</div></div></div>`
      );
    return head("arn-allies", "Allies", allies) + order(allies).map((f) => playerCard(ctx, f, false)).join("") + head("arn-enemies", "Enemies", enemies) + order(enemies).map((f) => playerCard(ctx, f, false)).join("");
  }
  function playersHead(arena, ctx) {
    const counts = fighters(arena).reduce((n, f) => ((n[f.side === "enemy" ? 1 : 0] += 1), n), [0, 0]);
    return `<div class="arn-head"><span class="ovtname">Players</span><span class="arn-badge">${ctx.esc(arena.label || "PvP")} · ${counts[0]}v${counts[1]}</span></div>`;
  }

  window.A2Arena = { card, body, clock, players, playersHead, you, foe };
})();
