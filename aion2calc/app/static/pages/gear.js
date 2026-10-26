/* Gear & Advice (#/gear): the inventory, and the advice run on it. */
"use strict";

function renderAdviceProgress() {
  const box = $("#gadvice-progress"),
    job = S.gear.adviceJob;
  if (!box) return;
  const current = job && job.key === S.gear.key,
    busy = current && job.status === "running";
  if ($("#gadv")) {
    $("#gadv").disabled = !!busy;
    $("#gadv").textContent = busy ? "Calculating advice…" : "Run advice";
  }
  if ($("#gchar")) $("#gchar").disabled = !!busy;
  box.hidden = !current;
  if (!current) return;
  const elapsed = Math.max(0, Math.floor((Date.now() - job.started) / 1000)),
    lines = job.log || [];
  box.innerHTML = busy
    ? `<p role="status"><span class="spinner"></span> Calculating advice · ${elapsed}s · <b>${esc(lines.at(-1) || "Starting…")}</b></p><progress aria-label="Advice calculation in progress"></progress><pre class="diff small">${esc(lines.slice(-6).join("\n"))}</pre><p class="small muted">Working through your build and recommendations. Results will appear below your inventory; a View results button will be shown here when ready.</p>`
    : job.status === "done"
      ? '<p role="status"><b>Advice complete.</b> Scroll down below your inventory to see the recommendations.</p><button class="btn primary small" data-advice-results>View results ↓</button>'
      : `<p role="alert">Advice did not complete: ${esc(job.error || "Unknown error")}</p>`;
  const view = box.querySelector("[data-advice-results]");
  if (view)
    view.onclick = () => {
      const results = $("#gout");
      if (results) {
        results.scrollIntoView({ behavior: "smooth", block: "start" });
        results.focus({ preventScroll: true });
      }
    };
}

async function pageGear() {
  const st = S.gear || (S.gear = {}),
    shown = stillShown();
  const chars = await api("/api/characters").catch(() => []);
  if (!shown()) return;
  app().innerHTML = `<section class="win"><div class="wh"><h2>Gear &amp; advice</h2><a class="btn small" href="#/history">Saved advice</a><span class="sub">what to wear from your inventory, goal gear, upgrade path, arcana, pantheon, genus insight — on simulated DPS</span></div>
    <div class="wb">${
      chars.length
        ? `<div class="row"><select id="gchar" aria-label="Character">${chars.map((c) => `<option value="${esc(c.key)}" ${c.key === st.key ? "selected" : ""}>${esc(c.name)} · ${esc(c.class_name)} · ${esc(c.region)}</option>`).join("")}</select>
      <button class="btn primary" id="gadv">Run advice</button><span id="gmsg" class="small muted"></span></div>
      <p class="small faint">Import the character on My Character first. The official page shows only equipped items: add bag and warehouse items below so the planner can use them. Fights you import on Combat Logs are matched to the gear the character wore and calibrate the model.</p>`
        : '<div class="note">Import a character on My Character first.</div>'
    }
    <div id="gadvice-progress" class="note advice-progress" hidden></div><div id="ginv"></div></div></section><div id="gout" tabindex="-1"></div>`;
  if (!chars.length) return;
  const key = () => (st.key = $("#gchar").value);
  let genusEditor = null;
  const showInv = async () => {
    const inventoryKey = key();
    const inv = await api("/api/inventory?character=" + encodeURIComponent(inventoryKey));
    if ($("#gchar")?.value !== inventoryKey) return;
    st.inv = inv;
    const rollsOf = (e) =>
      e.rolls_text ||
      (Array.isArray(e.rolls) && e.rolls.length ? e.rolls.map(([s, v]) => `${s} +${v}`).join(", ") : "");
    const rows = inv.items
      .map(
        (
          e,
        ) => `<tr><td>${esc(e.slot || e.category || "")}</td><td class="gname" data-grade="${esc(e.grade)}">${esc(e.name)} +${e.enchant || 0}${e.note ? `<span class="small muted"> · ${esc(e.note)}</span>` : ""}</td>
      <td class="small">${esc(rollsOf(e))}</td><td class="small">${esc((e.skills || []).map(([n, l]) => `${n} +${l}`).join(", "))}</td><td class="small muted">${esc(e.source)}</td>
      <td class="r gacts">${e.source === "inventory" ? `<button class="btn small" data-edit="${esc(e.id)}">Edit</button> <button class="btn small" data-rm="${esc(e.id)}">Remove</button>` : ""}</td></tr>`,
      )
      .join("");
    const genus = inv.genus || {};
    $("#ginv").innerHTML = `<h4 class="gold small" style="margin-top:12px">INVENTORY</h4>
      <table class="t"><tr><th>Slot</th><th>Item</th><th>Rolls</th><th>Skill options</th><th>Source</th><th><span class="sr-only">Actions</span></th></tr>${rows}</table>
      <p class="small faint">Search the catalog below to add bag and warehouse items. The item panel takes the enchant level, the rolled stats and the skill options; <b>Edit</b> changes them later. An item added without its rolls counts the expected rolls of its pool.</p>
      <div id="gedit"></div>
      <div class="row" style="margin-top:8px"><input id="gq" type="text" placeholder="search the catalog to add an item" style="width:320px"><button class="btn small" id="gsrch">Search</button></div>
      <div id="gres"></div>
      <h4 class="gold small" style="margin-top:12px">GENUS INSIGHT</h4>
      <div id="genus-editor"></div>
      <h4 class="gold small" style="margin-top:12px">TITLES YOU OWN</h4>
      <p class="small faint">The official page shows only equipped titles. One title name per line (copy them from the in-game Titles window).</p>
      <textarea id="gtit" rows="4" style="width:100%">${esc((inv.titles_owned || []).join("\n"))}</textarea>
      <button class="btn small" id="gtsave">Save titles</button>`;
    // The item panel: enchant level, rolls and skill options of an item being added or edited.
    const closeEditor = () => {
      if ($("#gedit")) $("#gedit").innerHTML = "";
    };
    const stepText = (opt, lv) => {
      if (!lv) return "";
      const at = opt.enchant_steps.filter((x) => x.level <= lv && (lv <= 15 || x.level > 15)).at(-1);
      const base = lv > 15 ? opt.enchant_steps.find((x) => x.level === 15) : null;
      return [base?.stats, at?.stats].filter(Boolean).join(", then ");
    };
    const renderEditor = (opt, ed) => {
      const box = $("#gedit");
      if (!box) return;
      const slots = opt.skills.base + opt.skills.per_enchant * ed.enchant,
        used = ed.skills.reduce((a, [, l]) => a + (+l || 0), 0);
      const pick = (sel) =>
        `<option value="">— skill —</option>${opt.skills.pool.length ? `<optgroup label="This item's option pool">${opt.skills.pool.map((n) => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("")}</optgroup>` : ""}${opt.skills.others.length ? `<optgroup label="${opt.skills.pool.length ? "Other skills" : "Skills"}">${opt.skills.others.map((n) => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("")}</optgroup>` : ""}`;
      const step = stepText(opt, ed.enchant);
      box.innerHTML = `<div class="gedit" data-grade="${esc(opt.grade)}"><div class="row"><span class="gname">${esc(opt.name)}</span><span class="small muted">${esc([opt.category, opt.item_level ? `item level ${opt.item_level}` : "", opt.grade].filter(Boolean).join(" · "))}</span><span class="small muted">${ed.id ? "editing your inventory entry" : "adding to your inventory"}</span></div>
        <div class="row"><label>Enchant <select data-ge-enchant>${Array.from({ length: opt.max_enchant + 1 }, (_, i) => `<option value="${i}" ${i === ed.enchant ? "selected" : ""}>+${i}</option>`).join("")}</select></label><span class="small muted">${esc(step ? `+${ed.enchant}: ${step}` : opt.enchant_known ? `enhances to +${opt.max_enchant}` : "the catalog lists no enhancement limit for this item")}</span></div>
        ${
          opt.roll_count
            ? `<div class="gelines"><div><b>Random rolls</b> <span class="small muted">${opt.roll_count} on this item, each a different stat. Leave every line empty if you do not know them: the planner then assumes the expected rolls of its pool.</span></div>
          ${ed.rolls
            .map((r, i) => {
              const o = opt.rolls.find((x) => x.stat === r?.stat);
              return `<div class="row"><select data-ge-roll="${i}" aria-label="roll ${i + 1}"><option value="">— not entered —</option>${opt.rolls.map((x) => `<option value="${esc(x.stat)}" ${x.stat === r?.stat ? "selected" : ""}>${esc(x.stat)} (${esc(x.range)})${x.scored ? "" : " · not scored"}</option>`).join("")}</select><input type="number" step="any" data-ge-val="${i}" aria-label="roll ${i + 1} value" value="${esc(r?.value ?? "")}" ${o ? `min="${o.min}" max="${o.max}"` : "disabled"}><span class="small muted" data-ge-unit="${i}">${o?.percent ? "%" : ""}</span></div>`;
            })
            .join("")}</div>`
            : `<p class="small muted">${esc(opt.name)} rolls no random stats.</p>`
        }
        <div class="gelines"><div><b>Skill options</b> <span class="small muted">${opt.arcana ? `A ${esc(opt.grade || "")} card holds ${opt.skills.base} option levels plus one per enchant level, ${slots} at +${ed.enchant}, at most +${opt.skills.max_level} on one skill.` : `One option reaches +${opt.skills.max_level}; ${opt.skills.pool.length ? "the pool lists what this item rolls for your class." : "the catalog lists no option pool for this item."}`}</span></div>
          ${ed.skills.map(([n, l], i) => `<div class="row"><select data-ge-skill="${i}" aria-label="skill option ${i + 1}">${pick(n)}</select><select data-ge-skl="${i}" aria-label="skill option ${i + 1} level">${Array.from({ length: opt.skills.max_level }, (_, k) => `<option value="${k + 1}" ${k + 1 === +l ? "selected" : ""}>+${k + 1}</option>`).join("")}</select><button class="btn small" data-ge-skrm="${i}" title="remove this skill option">×</button></div>`).join("")}
          <button class="btn small" data-ge-skadd ${used >= slots ? "disabled" : ""}>Add a skill option</button></div>
        <div class="row"><label>Note <input type="text" data-ge-note maxlength="200" placeholder="e.g. warehouse, second tab" value="${esc(ed.note)}" style="width:320px"></label></div>
        <div class="row"><button class="btn primary small" data-ge-save>${ed.id ? "Save changes" : "Add to inventory"}</button><button class="btn small" data-ge-cancel>Cancel</button><span class="small" data-ge-msg role="status"></span></div></div>`;
      const collect = () => {
        ed.enchant = +box.querySelector("[data-ge-enchant]").value;
        ed.rolls = ed.rolls.map((_, i) => {
          const s = box.querySelector(`[data-ge-roll="${i}"]`).value,
            v = box.querySelector(`[data-ge-val="${i}"]`).value;
          return s ? { stat: s, value: v } : null;
        });
        ed.skills = ed.skills.map((_, i) => [
          box.querySelector(`[data-ge-skill="${i}"]`).value,
          +box.querySelector(`[data-ge-skl="${i}"]`).value,
        ]);
        ed.note = box.querySelector("[data-ge-note]").value;
      };
      box.querySelector("[data-ge-enchant]").onchange = () => {
        collect();
        renderEditor(opt, ed);
      };
      box.querySelectorAll("[data-ge-roll]").forEach(
        (sel) =>
          (sel.onchange = () => {
            const i = sel.dataset.geRoll,
              o = opt.rolls.find((x) => x.stat === sel.value),
              inp = box.querySelector(`[data-ge-val="${i}"]`);
            inp.disabled = !o;
            inp.value = o ? o.min : "";
            if (o) {
              inp.min = o.min;
              inp.max = o.max;
            }
            box.querySelector(`[data-ge-unit="${i}"]`).textContent = o?.percent ? "%" : "";
          }),
      );
      box.querySelector("[data-ge-skadd]").onclick = () => {
        collect();
        ed.skills.push(["", 1]);
        renderEditor(opt, ed);
      };
      box.querySelectorAll("[data-ge-skrm]").forEach(
        (b) =>
          (b.onclick = () => {
            collect();
            ed.skills.splice(+b.dataset.geSkrm, 1);
            renderEditor(opt, ed);
          }),
      );
      box.querySelector("[data-ge-cancel]").onclick = closeEditor;
      box.querySelector("[data-ge-save]").onclick = async () => {
        collect();
        const msg = box.querySelector("[data-ge-msg]");
        const rolls = ed.rolls.filter(Boolean).map((r) => [r.stat, r.value === "" ? NaN : +r.value]);
        if (rolls.some(([, v]) => Number.isNaN(v))) {
          msg.textContent = "Enter a value for every chosen roll.";
          return;
        }
        if (ed.skills.some(([n]) => !n)) {
          msg.textContent = "Choose a skill on every option line, or remove the line.";
          return;
        }
        const body = { character: inventoryKey, enchant: ed.enchant, rolls, skills: ed.skills, note: ed.note };
        try {
          await api(
            ed.id ? "/api/inventory/update" : "/api/inventory/add",
            ed.id ? { ...body, id: ed.id } : { ...body, slug: ed.slug },
          );
        } catch (e) {
          msg.textContent = e.message.replace(/^\w*Error:\s*/, "");
          return;
        }
        toast(ed.id ? "Saved" : "Added");
        showInv();
      };
    };
    const openEditor = async (slug, entry) => {
      let opt;
      try {
        opt = await api(`/api/items/${encodeURIComponent(slug)}/options?class=${encodeURIComponent(inv.class || "")}`);
      } catch (e) {
        toast(e.message);
        return;
      }
      if ($("#gchar")?.value !== inventoryKey || !$("#gedit")) return;
      const ed = {
        slug,
        id: entry?.id || null,
        enchant: Math.min(+(entry?.enchant || 0), opt.max_enchant),
        rolls: Array.from({ length: opt.roll_count }, (_, i) => {
          const r = entry?.rolls?.[i];
          return r ? { stat: r[0], value: r[1] } : null;
        }),
        skills: (entry?.skills || []).map(([n, l]) => [n, l]),
        note: entry?.note || "",
      };
      renderEditor(opt, ed);
      $("#gedit").scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    $$("[data-edit]").forEach(
      (b) =>
        (b.onclick = () => {
          const e = inv.items.find((x) => x.id === b.dataset.edit);
          if (e?.slug) openEditor(e.slug, e);
          else toast("This entry is not in the catalog: remove it and add it again.");
        }),
    );
    $$("[data-rm]").forEach(
      (b) =>
        (b.onclick = async () => {
          await api("/api/inventory/remove", { character: key(), id: b.dataset.rm });
          showInv();
        }),
    );
    $("#gq").onkeydown = (ev) => {
      if (ev.key === "Enter") $("#gsrch").click();
    };
    $("#gsrch").onclick = async () => {
      st.gq = $("#gq").value;
      const items = await api(`/api/items?search=${encodeURIComponent(st.gq)}&limit=30`);
      $("#gres").innerHTML = `<table class="t">${items
        .map(
          (
            it,
          ) => `<tr><td class="gname" data-grade="${esc(it.grade)}">${esc(it.name)}</td><td>${esc(it.category)}</td><td class="r">${it.item_level ?? ""}</td>
        <td class="r"><button class="btn small" data-add="${esc(it.slug)}">Add…</button></td></tr>`,
        )
        .join("")}</table>`;
      $$("[data-add]").forEach((b) => (b.onclick = () => openEditor(b.dataset.add, null)));
    };
    if (st.gq) {
      $("#gq").value = st.gq;
      $("#gsrch").click();
    } // the last search stays after an add or an edit
    $("#gtsave").onclick = async () => {
      await api("/api/inventory/titles", { character: key(), titles: $("#gtit").value.split("\n") });
      toast("Saved");
      showInv();
    };
    const genusRoot = $("#genus-editor");
    genusEditor = A2GenusEditor.mount(genusRoot, genus, async (draft) => {
      const saved = await api("/api/inventory/genus", { character: inventoryKey, genus: draft });
      if ($("#gmsg")) $("#gmsg").textContent = "";
      st.genusRevision = (st.genusRevision || 0) + 1;
      if (st.key === inventoryKey && genusRoot.isConnected) {
        st.inv = saved;
        st.adv = null;
        $("#gout").innerHTML = '<p class="note">Genus lines saved. Run advice again to update recommendations.</p>';
      }
      return saved.genus || {};
    });
  };
  $("#gchar").onchange = () => {
    st.adv = null;
    $("#gout").innerHTML = "";
    key();
    renderAdviceProgress();
    showInv();
  };
  $("#gadv").onclick = async () => {
    if (st.adviceJob?.status === "running") return;
    if (genusEditor?.isDirty()) {
      $("#gmsg").textContent = "Save your Genus lines before running advice.";
      toast("Save your Genus lines first.");
      return;
    }
    $("#gmsg").textContent = "";
    st.adv = null;
    $("#gout").innerHTML = '<div class="empty"><span class="spinner"></span> Calculating advice…</div>';
    const characterKey = key(),
      revision = st.genusRevision || 0,
      run = (st.adviceRun = (st.adviceRun || 0) + 1);
    const job = (st.adviceJob = { key: characterKey, status: "running", started: Date.now(), log: [] });
    renderAdviceProgress();
    try {
      const advice = await runJob("/api/advice", { character: characterKey }, (lines) => {
        job.log = lines;
        if (st.adviceJob === job) renderAdviceProgress();
      });
      if (st.key !== characterKey || st.adviceRun !== run) return;
      if ((st.genusRevision || 0) !== revision)
        throw Error("Genus allocations changed during calculation. Run advice again.");
      st.adv = advice;
      job.status = "done";
      if ($("#gout")) {
        $("#gout").innerHTML = renderAdvice(advice);
        bindAdvice(advice);
        toast("Advice complete. Scroll down or choose View results.", 7000);
      }
    } catch (e) {
      job.status = "error";
      job.error = e.message;
      if ($("#gout") && st.key === characterKey && st.adviceRun === run)
        $("#gout").innerHTML = `<div class="note">${esc(e.message)}</div>`;
    } finally {
      if (st.adviceJob === job) renderAdviceProgress();
    }
  };
  renderAdviceProgress();
  await showInv();
  if (st.adv) {
    $("#gout").innerHTML = renderAdvice(st.adv);
    bindAdvice(st.adv);
  }
}
