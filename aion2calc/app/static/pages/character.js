/* My Character (#/character): a character imported from the official site, optimized with the gear it wears. */
"use strict";

function mountSkillReserves(root, key, v) {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(key) || "{}") || {};
  } catch (_) {}
  const rows = [...(v.skills?.active || []), ...(v.skills?.passive || [])]
    .map((row) => ({ ...row, field: "sp", level: row.sp, max: row.buy_max || 10 }))
    .concat((v.stigmas || []).map((row) => ({ ...row, field: "stigmas", max: 20 })));
  root.innerHTML = `<details><summary>Retain trained skills and equipped stigmas</summary><p class="small muted">Optional minimums for skills you rely on for defense, control or movement. Applies to both PvE and PvP. Damage is optimized within these constraints. You can also reserve supporting effects on active skills. Trained points, fixed gear bonuses and connected Daevanion nodes jointly fund their unlocks and selection slots within your budgets. Infeasible requests are rejected. Other specialties may change. Use utility skills manually when absent from the rotation. This does not simulate defensive skill use, crowd control, movement or opponent matchups.</p><div class="cr-scroll"><table class="t"><tr><th>Retain</th><th>Skill</th><th>Minimum trained level</th><th>Retain supporting effects</th></tr>${rows.map((row) => `<tr data-reserve-row data-field="${row.field}" data-id="${row.id}"><td><input type="checkbox" data-reserve-enable aria-label="Retain ${esc(row.name)}" ${saved[row.field]?.[row.id] ? "checked" : ""}></td><td>${esc(row.name)}${row.field === "stigmas" ? " · keep equipped" : ""}</td><td><input type="number" data-reserve-level aria-label="Minimum ${esc(row.name)} level" min="1" max="${row.max}" value="${Math.max(1, Math.min(row.max, Number(saved[row.field]?.[row.id] || row.level || 1)))}" style="width:92px"></td><td>${row.field === "sp" && (row.specs || []).length ? `<details><summary>Choose effects</summary>${row.specs.map((effect) => `<label style="display:block;margin-block:3px"><input type="checkbox" data-reserve-effect="${effect.id}" ${saved.specs?.[row.id]?.includes(effect.id) ? "checked" : ""}> ${effect.n}. ${esc(effect.text)} · effect Lv ${effect.unlock}</label>`).join("")}</details>` : "—"}</td></tr>`).join("")}</table></div></details>`;
  function read() {
    const plan = { sp: {}, stigmas: {}, specs: {} };
    root.querySelectorAll("[data-reserve-row]").forEach((row) => {
      const enable = row.querySelector("[data-reserve-enable]"),
        input = row.querySelector("[data-reserve-level]");
      const effects = [...row.querySelectorAll("[data-reserve-effect]:checked")].map((e) =>
        Number(e.dataset.reserveEffect),
      );
      if (effects.length) {
        enable.checked = true;
        plan.specs[row.dataset.id] = effects;
      }
      input.disabled = !enable.checked;
      if (enable.checked) {
        if (!input.checkValidity()) throw new Error("Reserve levels must be whole numbers within the shown range.");
        plan[row.dataset.field][row.dataset.id] = Number(input.value);
      }
    });
    return plan;
  }
  function save() {
    const plan = read();
    try {
      localStorage.setItem(key, JSON.stringify(plan));
    } catch (e) {
      toast("Could not save skill reserves: " + e.message);
    }
    return plan;
  }
  root.onchange = () => {
    try {
      save();
    } catch (e) {
      toast(e.message);
    }
  };
  read();
  return { read: save };
}
function mountSurvivalOptions(root, key, v = {}) {
  const skillChoices = [
    ...(v.skills?.active || []).map((s) => ({ ...s, kind: "active" })),
    ...(v.skills?.passive || []).map((s) => ({ ...s, kind: "passive" })),
    ...(v.stigmas || []).map((s) => ({ ...s, kind: "stigma" })),
  ];
  const skillOptions = (id, actionsOnly = false) => {
    const choices = skillChoices.filter((s) => !actionsOnly || s.kind !== "passive");
    return `<option value="">Unlinked assumption</option>${choices.map((s) => `<option value="${s.id}" ${Number(id) === s.id ? "selected" : ""}>${esc(s.name)} · ${s.kind}</option>`).join("")}${id != null && !choices.some((s) => s.id === Number(id)) ? `<option value="${esc(id)}" selected>Unavailable skill #${esc(id)}</option>` : ""}`;
  };
  const effectOptions = (id, effect) => {
    const skill = skillChoices.find((s) => s.id === Number(id)),
      effects = skill?.kind === "active" ? skill.specs || [] : [];
    return `<option value="">No specific effect</option>${effects.map((e) => `<option value="${e.id}" ${Number(effect) === e.id ? "selected" : ""}>${esc(e.text)} · effect Lv ${esc(e.unlock)}</option>`).join("")}${effect != null && !effects.some((e) => e.id === Number(effect)) ? `<option value="${esc(effect)}" selected>Unavailable effect #${esc(effect)}</option>` : ""}`;
  };
  let settings = { preserve_hp: true, min_node_hp: 0, current_hp: null, opponents: [], action_windows: [] };
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "null");
    if (saved && typeof saved === "object")
      settings = {
        ...settings,
        ...saved,
        opponents: Array.isArray(saved.opponents) ? saved.opponents.slice(0, 8) : [],
        action_windows: Array.isArray(saved.action_windows) ? saved.action_windows.slice(0, 8) : [],
      };
  } catch (_) {}
  const read = () => {
    settings = {
      preserve_hp: root.querySelector("[data-preserve-hp]").checked,
      min_node_hp: Number(root.querySelector("[data-hp-floor]").value),
      current_hp:
        root.querySelector("[data-current-hp]").value === ""
          ? null
          : Number(root.querySelector("[data-current-hp]").value),
      action_windows: [...root.querySelectorAll("[data-action-row]")].map((row) =>
        Object.fromEntries(
          [...row.querySelectorAll("[data-action]")].map((input) => [
            input.dataset.action,
            input.dataset.action === "name"
              ? input.value
              : input.dataset.action === "reserve_cooldown"
                ? input.checked
                : ["skill_id", "effect_id", "cooldown_s"].includes(input.dataset.action) && input.value === ""
                  ? null
                  : Number(input.value),
          ]),
        ),
      ),
      opponents: [...root.querySelectorAll("[data-pressure-row]")].map((row, index) => ({
        ...Object.fromEntries(
          [...row.querySelectorAll("[data-pressure]")].map((input) => [
            input.dataset.pressure,
            input.dataset.pressure === "name"
              ? input.value
              : input.dataset.pressure === "healing_duration_s" && input.value === ""
                ? null
                : Number(input.value),
          ]),
        ),
        reductions: [...row.querySelectorAll("[data-reduction-row]")].map((w) =>
          Object.fromEntries(
            [...w.querySelectorAll("[data-reduction]")].map((input) => [
              input.dataset.reduction,
              ["name", "kind"].includes(input.dataset.reduction)
                ? input.value
                : ["skill_id", "effect_id", "cooldown_s"].includes(input.dataset.reduction) && input.value === ""
                  ? null
                  : Number(input.value),
            ]),
          ),
        ),
        ...(settings.opponents[index]?.recorded_evidence
          ? { recorded_evidence: settings.opponents[index].recorded_evidence }
          : {}),
        ...(settings.opponents[index]?.damage_trace ? { damage_trace: settings.opponents[index].damage_trace } : {}),
        ...(settings.opponents[index]?.opponent_benchmark
          ? { opponent_benchmark: settings.opponents[index].opponent_benchmark }
          : {}),
      })),
    };
    return settings;
  };
  const save = () => {
    read();
    try {
      localStorage.setItem(key, JSON.stringify(settings));
    } catch (e) {
      toast("Could not save survival options: " + e.message);
    }
    return settings;
  };
  let recording = null,
    encounters = [];
  function render() {
    root.innerHTML = `<details><summary>Survivability · preserve HP while optimizing damage</summary><p class="small muted">Protects flat HP from crystal-board nodes. It does not model armor, defensive skills or CC. Incoming scenarios are explicit assumptions, with optional timed expected-hit benchmarks from optimized PvP opponents; these are not decoded boss mechanics or reactive duels.</p>
    <div class="row"><label><input type="checkbox" data-preserve-hp ${settings.preserve_hp ? "checked" : ""}> Preserve current crystal-board HP</label><label>Minimum crystal-board HP <input data-hp-floor type="number" min="0" max="1000000000" value="${esc(settings.min_node_hp)}"></label><label>Current in-game maximum HP (for scenarios) <input data-current-hp type="number" min="1" max="1000000000" value="${esc(settings.current_hp ?? "")}" placeholder="Optional"></label></div>
    <p class="small muted">Use hits and incoming DPS after your mitigation. The requirement is one hit plus the largest ongoing pressure deficit plus a positive HP reserve. Healing begins after the chosen delay and lasts for the entered duration (blank means the rest of the window). Excess healing is not banked. Healing never absorbs the initial hit. These timings are assumptions, not decoded defensive abilities or CC rules. Total HP uses only a flat node-delta proxy; verify the result in game.</p>
    <div class="cr-scroll"><table class="t"><tr><th>Encounter / opponent</th><th>Hit damage</th><th>Incoming DPS</th><th>Seconds</th><th>Assumed HPS</th><th>Healing delay (s)</th><th>Healing duration (s)</th><th>HP reserve</th><th>Timed pressure reductions</th><th><span class="sr-only">Actions</span></th></tr>${settings.opponents
      .map(
        (row, index) =>
          `<tr data-pressure-row><td><input data-pressure="name" maxlength="100" value="${esc(row.name || "Incoming pressure")}">${row.damage_trace ? `<span class="small muted">Timed expected hits · ${row.damage_trace.events.length} hits · ${n0(row.damage_trace.total)} damage · source ${esc(row.opponent_benchmark?.source_start_s)}–${esc(row.opponent_benchmark?.source_end_s)}s</span>` : ""}</td>${[
            ["burst_damage", 0],
            ["pressure_dps", 0],
            ["window_s", 5],
            ["healing_hps", 0],
            ["healing_delay_s", 0],
            ["healing_duration_s", ""],
            ["reserve_hp", 1],
          ]
            .map(
              ([field, fallback]) =>
                `<td><input data-pressure="${field}" ${field === "window_s" && row.damage_trace ? 'readonly title="Re-import this opponent to change its timed window"' : ""} aria-label="${field.replaceAll("_", " ")}" type="number" min="${field === "window_s" ? ".1" : field === "reserve_hp" ? "1" : "0"}" max="${["window_s", "healing_delay_s", "healing_duration_s"].includes(field) ? "120" : "1000000000"}" step="any" value="${esc(row[field] ?? fallback)}" placeholder="${field === "healing_duration_s" ? "Rest of window" : ""}" style="width:109px"></td>`,
            )
            .join("")}<td><details><summary>${row.reductions?.length || 0} assumed windows</summary>${(
            row.reductions || []
          )
            .map(
              (w, j) =>
                `<fieldset data-reduction-row style="display:grid;gap:4px;min-width:220px"><label>Name <input data-reduction="name" maxlength="100" value="${esc(w.name || "Assumed reduction")}"></label><label>Type <select data-reduction="kind">${["defensive", "control", "movement"].map((k) => `<option value="${k}" ${w.kind === k ? "selected" : ""}>${cap(k)}</option>`).join("")}</select></label><label>Retain skill <select data-reduction="skill_id">${skillOptions(w.skill_id)}</select></label><label>Minimum trained level <input data-reduction="min_trained" type="number" min="1" max="${skillChoices.find((s) => s.id === Number(w.skill_id))?.kind === "stigma" ? 20 : skillChoices.find((s) => s.id === Number(w.skill_id))?.buy_max || 10}" step="1" value="${esc(w.min_trained ?? 1)}" ${w.skill_id == null ? "disabled" : ""}></label><label>Retain supporting effect <select data-reduction="effect_id" ${w.skill_id == null ? "disabled" : ""}>${effectOptions(w.skill_id, w.effect_id)}</select></label><label>Assumed effective cooldown (s) <input data-reduction="cooldown_s" type="number" min="0" max="3600" step="any" value="${esc(w.cooldown_s ?? "")}" placeholder="Unknown" ${w.skill_id == null ? "disabled" : ""}></label>${[
                  ["delay_s", "Start (s)", 0, 120],
                  ["duration_s", "Duration (s)", 0, 120],
                  ["reduction_pct", "Pressure reduced (%)", 0, 100],
                ]
                  .map(
                    ([f, label, fallback, max]) =>
                      `<label>${label} <input data-reduction="${f}" type="number" min="0" max="${max}" step="any" value="${esc(w[f] ?? fallback)}" style="width:98px"></label>`,
                  )
                  .join(
                    "",
                  )}<button class="btn small" data-remove-reduction="${index}:${j}">Remove window</button></fieldset>`,
            )
            .join(
              "",
            )}<button class="btn small" data-add-reduction="${index}" ${(row.reductions || []).length >= 8 ? "disabled" : ""}>Add window</button></details></td><td><button class="btn small" data-remove-pressure="${index}">Remove</button></td></tr>`,
      )
      .join("")}</table></div>
    <p class="small muted">Timed reductions apply to ongoing incoming DPS and imported timed hits. Enter assumed successful defense, control or movement windows explicitly; times are relative to the scenario start. No catalog coefficient, immunity, cooldown or success chance is inferred. Overlaps use the strongest percentage, never stack. The initial hit is unchanged. Do not reduce damage twice if your incoming DPS already includes the same effect. Optionally link a skill and supporting effect: their minimums are automatically merged with your reserves below, including zero-duration windows. Unlinked windows remain assumptions. Links retain allocations; they do not cast skills or subtract their time from outgoing DPS. Optionally enter an effective cooldown for each linked skill (blank = unknown, zero = no reuse gap). Repeat spacing is checked within each scenario, with all skills initially ready. Same-start entries count as one activation; the largest entered cooldown for a skill applies. Review this assumption if gear or cooldown reduction changes. Charges, resets and shared cooldown groups are not modeled.</p>
    <fieldset><legend>Outgoing action-time assumptions</legend><p class="small muted">Pause new offensive actions while spending time on defense or movement. Enter one fight's rotation clock, starting at zero. This schedule applies once to each damage scenario and is clipped to its duration; overlaps count once. Actions must finish before a pause. Already scheduled hits, DoTs, pets, cooldown recovery and regeneration continue. Incoming-pressure windows use separate clocks and are not copied here. No tactical skill cast, MP cost, cooldown or defensive success is inferred. Current-character damage uses the same pauses; community references remain unpaused.</p>
    ${settings.action_windows.map((w, i) => `<fieldset data-action-row style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px"><legend>Action-time window ${i + 1}</legend><label>Name <input data-action="name" maxlength="100" value="${esc(w.name || "Tactical time")}"></label><label>Start (s) <input data-action="start_s" type="number" min="0" max="3600" step="any" value="${esc(w.start_s ?? 0)}"></label><label>Duration (s) <input data-action="duration_s" type="number" min="0" max="120" step="any" value="${esc(w.duration_s ?? 0)}"></label><label>Retain active skill / stigma <select data-action="skill_id">${skillOptions(w.skill_id, true)}</select></label><label>Minimum trained level <input data-action="min_trained" type="number" min="1" max="${skillChoices.find((s) => s.id === Number(w.skill_id))?.kind === "stigma" ? 20 : skillChoices.find((s) => s.id === Number(w.skill_id))?.buy_max || 10}" step="1" value="${esc(w.min_trained ?? 1)}" ${w.skill_id == null ? "disabled" : ""}></label><label>Retain supporting effect <select data-action="effect_id" ${w.skill_id == null ? "disabled" : ""}>${effectOptions(w.skill_id, w.effect_id)}</select></label><label>Assumed effective cooldown (s) <input data-action="cooldown_s" type="number" min="0" max="3600" step="any" value="${esc(w.cooldown_s ?? "")}" placeholder="Unknown" ${w.skill_id == null ? "disabled" : ""}></label><label><input data-action="reserve_cooldown" type="checkbox" ${w.reserve_cooldown ? "checked" : ""}> Reserve cooldown in rotation</label><button class="btn small" data-remove-action="${i}">Remove window</button></fieldset>`).join("")}<button class="btn small" data-add-action ${settings.action_windows.length >= 8 ? "disabled" : ""}>Add action-time window</button><p class="small muted">Optional links retain the selected skill/stigma and supporting effect within your budgets, including zero-duration and clipped-out windows. Passive skills cannot be action-time links. A cooldown checks only assumed reuse in each outgoing scenario: blank is unknown, zero imposes no gap. Positive-duration windows starting before scenario end count as uses; same-start entries count once. The largest entered cooldown for a linked skill applies. Incoming-pressure scenarios stay separate. Enable Reserve cooldown in rotation to keep matching modeled skill IDs and explicit cooldown groups available for the assumed use. This requires an entered cooldown: before the use, the larger of that assumption and the modeled offensive cooldown determines the hold; afterward, the group stays excluded for the entered cooldown. Fixed exclusions ignore reset hooks. Unmatched skills are reported. Cross-skill hooks and resource readiness are not verified; exclusions do not prove tactical availability. No tactical MP, damage, shields or success is modeled; unrecorded shared groups and charges remain unknown.</p></fieldset>
    <fieldset><legend>Import recorded incoming damage</legend><input type="file" data-pressure-file accept=".json,.a2log"><div data-pressure-import></div><p class="small muted">Choose an exported a2log JSON file. Uses the largest gross damage window received by the selected player, from all recorded attackers. Healing is excluded; recorded deaths reset the window. Missing death markers can join separate lives. Missing packets understate damage; damage reflects that recipient's gear and defenses. Imported values remain editable assumptions for your build, not a simulated opponent matchup.</p></fieldset>
    <fieldset><legend>Import optimized PvP opponent benchmark</legend><input type="file" data-opponent-file accept=".json" multiple><div class="row"><label>Pressure model <select data-opponent-method><option value="timed">Timed hits · greatest gross-damage window</option><option value="average">Average pressure · supports older results</option></select></label><label>Estimate <select data-opponent-metric><option value="pvp_burst">Burst average (30s by default)</option><option value="pvp">Sustained average (180s by default)</option></select></label><label>Assumed incoming scale <input data-opponent-scale type="number" min="0" max="10" step="any" placeholder="Required · 1 = unchanged"></label><label>Pressure window (s) <input data-opponent-window type="number" min=".1" max="120" step="any" value="5"></label><button class="btn small" data-opponent-use>Import benchmark scenario</button></div><p class="small muted" data-opponent-status>Select up to eight optimized PvP results from Saved Results (re-optimize for timed hits). Timed mode imports each result’s greatest gross-damage window from its complete expected-hit simulation. Healing and reduction windows then use time relative to that selected window. This selection does not maximize the mitigated HP requirement across every possible defense/healing alignment. Choose a scale explicitly for your assumed incoming damage; target defenses are not converted. Average mode uses scalar DPS for older results. These are stationary opponent benchmarks; reactions, random critical spikes, immunity and win probability are not simulated.</p></fieldset>
    <button class="btn small" data-add-pressure ${settings.opponents.length >= 8 ? "disabled" : ""}>Add encounter / opponent scenario</button><p class="small muted">Up to eight scenarios; the strictest HP requirement constrains the build. For PvP, compare several optimized opponent benchmarks; their damage is evaluated separately and the strictest HP requirement wins. Explicit defensive, control and movement windows can retain your skills and supporting effects. Matchup mitigation, reactive opponent behavior and win probability remain unmodeled.</p></details>`;
    root.onchange = (event) => {
      const group =
        event.target.dataset.action === "skill_id"
          ? "action"
          : event.target.dataset.reduction === "skill_id"
            ? "reduction"
            : null;
      if (group) {
        const row = event.target.closest(`[data-${group}-row]`),
          id = event.target.value,
          skill = skillChoices.find((s) => s.id === Number(id));
        const effect = row.querySelector(`[data-${group}="effect_id"]`),
          level = row.querySelector(`[data-${group}="min_trained"]`);
        effect.innerHTML = effectOptions(id, null);
        effect.disabled = !id;
        level.disabled = !id;
        const cooldown = row.querySelector(`[data-${group}="cooldown_s"]`);
        cooldown.value = "";
        cooldown.disabled = !id;
        if (group === "action") row.querySelector('[data-action="reserve_cooldown"]').checked = false;
        level.max = skill?.kind === "stigma" ? 20 : skill?.buy_max || 10;
        level.value = Math.max(1, Math.min(Number(level.max), Number(level.value) || 1));
      }
      save();
    };
    root.querySelector("[data-opponent-use]").onclick = async () => {
      const button = root.querySelector("[data-opponent-use]"),
        status = root.querySelector("[data-opponent-status]");
      button.disabled = true;
      try {
        save();
        if (settings.opponents.length >= 8) throw Error("Remove a scenario first (maximum eight).");
        const files = [...root.querySelector("[data-opponent-file]").files];
        if (!files.length) throw Error("Choose exported optimized PvP result JSON files.");
        if (files.length + settings.opponents.length > 8) throw Error("Use at most eight incoming scenarios in total.");
        if (
          files.some((file) => file.size > 20 * 1024 * 1024) ||
          files.reduce((n, file) => n + file.size, 0) > 20 * 1024 * 1024
        )
          throw Error("Selected results must total at most 20 MiB.");
        const scale = root.querySelector("[data-opponent-scale]");
        if (scale.value === "")
          throw Error("Enter an explicit incoming damage scale; your mitigation is not inferred.");
        const imported = [];
        for (const file of files) {
          status.textContent = `Reading opponent ${imported.length + 1} of ${files.length}: ${file.name}`;
          try {
            const result = await api("/api/character/opponent-pressure", {
              result: JSON.parse(await file.text()),
              metric: root.querySelector("[data-opponent-metric]").value,
              scale: Number(scale.value),
              window_s: Number(root.querySelector("[data-opponent-window]").value),
              method: root.querySelector("[data-opponent-method]").value,
            });
            imported.push(result.scenario);
          } catch (e) {
            throw Error(`${file.name}: ${e.message}. No scenarios from this batch were added.`, { cause: e });
          }
        }
        settings.opponents.push(...imported);
        saveState();
        render();
        root.querySelector("details").open = true;
        toast(
          `${imported.length} opponent benchmarks imported. Review current HP, healing and defensive windows before optimizing.`,
        );
      } catch (e) {
        status.textContent = "Import failed: " + e.message;
        button.disabled = false;
      }
    };
    const importer = root.querySelector("[data-pressure-import]");
    function showImport() {
      importer.innerHTML = encounters.length
        ? `<div class="row"><label>Encounter <select data-pressure-encounter>${encounters.map((e) => `<option value="${e.index}">${esc(e.label)} · ${esc(e.mode)}</option>`).join("")}</select></label><label>Recipient <select data-pressure-target></select></label><label>Window seconds <input data-pressure-window type="number" min=".1" max="120" step="any" value="5"></label><button class="btn small" data-pressure-use>Import pressure scenario</button></div>`
        : "No player-recipient damage events found. Older logs with only outgoing skill hits cannot supply incoming pressure.";
      if (!encounters.length) return;
      const select = importer.querySelector("[data-pressure-encounter]"),
        target = importer.querySelector("[data-pressure-target]");
      function targets() {
        target.innerHTML = encounters
          .find((e) => e.index === Number(select.value))
          .targets.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`)
          .join("");
      }
      select.onchange = targets;
      targets();
      importer.querySelector("[data-pressure-use]").onclick = async () => {
        const button = importer.querySelector("[data-pressure-use]");
        button.disabled = true;
        try {
          save();
          if (settings.opponents.length >= 8) throw Error("Remove a scenario first (maximum eight).");
          const result = await api("/api/character/pressure", {
            log: recording,
            segment: Number(select.value),
            target: target.value,
            window_s: Number(importer.querySelector("[data-pressure-window]").value),
          });
          settings.opponents.push(result.scenario);
          saveState();
          render();
          root.querySelector("details").open = true;
          toast("Recorded pressure imported. Enter your current maximum HP and review the reserve before optimizing.");
        } catch (e) {
          toast(e.message);
          button.disabled = false;
        }
      };
    }
    root.querySelector("[data-pressure-file]").onchange = async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        if (file.size > 32 * 1024 * 1024) throw Error("Choose an a2log JSON file below 32 MiB.");
        importer.textContent = "Reading damage events…";
        recording = JSON.parse(await file.text());
        const result = await api("/api/character/pressure", { log: recording });
        encounters = result.encounters;
        showImport();
      } catch (e) {
        recording = null;
        encounters = [];
        importer.textContent = "Import failed: " + e.message;
      }
    };
    if (recording) showImport();
    root.querySelector("[data-add-action]").onclick = () => {
      save();
      if (settings.action_windows.length >= 8) return;
      settings.action_windows.push({
        name: "Tactical time " + (settings.action_windows.length + 1),
        start_s: 0,
        duration_s: 0,
      });
      saveState();
      render();
      root.querySelector("details").open = true;
    };
    root.querySelectorAll("[data-remove-action]").forEach(
      (button) =>
        (button.onclick = () => {
          save();
          settings.action_windows.splice(Number(button.dataset.removeAction), 1);
          saveState();
          render();
          root.querySelector("details").open = true;
        }),
    );
    root.querySelector("[data-add-pressure]").onclick = () => {
      save();
      settings.opponents.push({
        name: "Pressure " + (settings.opponents.length + 1),
        burst_damage: 0,
        pressure_dps: 0,
        window_s: 5,
        healing_hps: 0,
        healing_delay_s: 0,
        healing_duration_s: null,
        reserve_hp: 1,
      });
      saveState();
      render();
    };
    root.querySelectorAll("[data-add-reduction]").forEach(
      (button) =>
        (button.onclick = () => {
          save();
          const row = settings.opponents[Number(button.dataset.addReduction)];
          row.reductions ??= [];
          if (row.reductions.length >= 8) return;
          row.reductions.push({
            name: "Assumed reduction",
            kind: "defensive",
            delay_s: 0,
            duration_s: 0,
            reduction_pct: 0,
          });
          saveState();
          render();
          root.querySelector("details").open = true;
          const pressureRow = root.querySelectorAll("[data-pressure-row]")[Number(button.dataset.addReduction)];
          pressureRow.querySelector("details").open = true;
        }),
    );
    root.querySelectorAll("[data-remove-reduction]").forEach(
      (button) =>
        (button.onclick = () => {
          save();
          const [i, j] = button.dataset.removeReduction.split(":").map(Number);
          settings.opponents[i].reductions.splice(j, 1);
          saveState();
          render();
          root.querySelector("details").open = true;
          root.querySelectorAll("[data-pressure-row]")[i].querySelector("details").open = true;
        }),
    );
    root.querySelectorAll("[data-remove-pressure]").forEach(
      (button) =>
        (button.onclick = () => {
          save();
          settings.opponents.splice(Number(button.dataset.removePressure), 1);
          saveState();
          render();
        }),
    );
  }
  function saveState() {
    try {
      localStorage.setItem(key, JSON.stringify(settings));
    } catch (e) {
      toast("Could not save survival options: " + e.message);
    }
  }
  render();
  return { read: save };
}

function mountCharacterGenus(root, key) {
  let editor = null,
    ready = false;
  const prefKey = "character-genus-options:" + key;
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(prefKey) || "{}");
  } catch (_) {}
  root.innerHTML = `<details><summary>Pet Genus Insight · PvE and PvP</summary><p class="small muted">Use the saved analysis lines from this character's Gear &amp; Advice inventory. Save edits before optimizing. Current-build and optimized scores use identical lines; Genus rolls are held fixed.</p><label><input type="checkbox" data-use-genus ${saved.enabled === false ? "" : "checked"}> Include saved Genus lines</label><p class="small muted">PvE enemy mix (relative weights; default equal). PvP ignores this mix and excludes genus-specific effects whose applicability to players is unverified.</p><div class="row">${["Cogni", "Fera", "Natura", "Varian", "Special"].map((g) => `<label>${g} <input data-genus-mix="${g}" type="number" min="0" max="100" step="any" value="${esc(saved.mix?.[g] ?? (g === "Special" ? 0 : 25))}" style="width:86px"></label>`).join("")}</div><div data-character-genus-editor role="status">Loading saved lines…</div></details>`;
  const host = root.querySelector("[data-character-genus-editor]");
  api("/api/inventory?character=" + encodeURIComponent(key))
    .then((inv) => {
      if (!root.isConnected) return;
      editor = A2GenusEditor.mount(host, inv.genus || {}, async (draft) => {
        const result = await api("/api/inventory/genus", { character: key, genus: draft });
        return result.genus || {};
      });
      ready = true;
    })
    .catch((e) => {
      if (root.isConnected) host.textContent = "Could not load Genus: " + e.message;
    });
  return {
    read(mode) {
      const enabled = root.querySelector("[data-use-genus]").checked;
      if (enabled && (!ready || editor?.isDirty()))
        throw Error(
          ready
            ? "Save your Genus edits before optimizing."
            : "Wait for Genus lines to load, or disable Genus scoring.",
        );
      const mix = Object.fromEntries(
        [...root.querySelectorAll("[data-genus-mix]")].map((e) => [e.dataset.genusMix, Number(e.value)]),
      );
      if (
        mode === "pve" &&
        enabled &&
        (Object.values(mix).some((x) => !Number.isFinite(x) || x < 0 || x > 100) ||
          !Object.values(mix).some((x) => x > 0))
      )
        throw Error("Set a positive PvE Genus mix using weights from 0 to 100.");
      localStorage.setItem(prefKey, JSON.stringify({ enabled, mix }));
      return mode !== "pve" || !enabled ? { enabled } : { enabled, mix };
    },
  };
}

async function pageCharacter() {
  const st = S.character;
  app().innerHTML = `<section class="win"><div class="wh"><h2>My character</h2><span class="sub">import from the official AION 2 character page, then optimize it with the same gear</span></div>
    <div class="wb"><div class="row"><input id="nm" type="text" placeholder="Character name" style="width:252px">
      <select id="rg" aria-label="Region"><option value="nae">North America</option><option value="eu">Europe</option><option value="as">Asia</option><option value="la">Latin America</option></select>
      <button class="btn primary" id="find">Search</button><span id="cmsg" class="small muted"></span></div>
      <div id="hits" style="margin-top:10px"></div><div id="known" style="margin-top:10px"></div></div></section><div id="cview"></div>`;
  const [known, ui] = await Promise.all([api("/api/characters").catch(() => []), api("/api/ui").catch(() => ({}))]);
  if (known.length)
    $("#known").innerHTML =
      `<div class="small muted">Imported before · newest first (click to fetch current profile): <div class="row">${known
        .slice(0, 8)
        .map(
          (c, i) =>
            `<button class="btn small" data-known-character="${i}">${esc(c.name)} · ${esc(c.class_name)} · ${n0(c.combat_power)}</button>`,
        )
        .join("")}</div></div>`;
  $("#find").onclick = async () => {
    $("#cmsg").innerHTML = '<span class="spinner"></span>';
    try {
      const hits = await api(
        `/api/character/search?name=${encodeURIComponent($("#nm").value)}&region=${$("#rg").value}`,
      );
      $("#cmsg").textContent = `${hits.length} found`;
      $("#hits").innerHTML =
        `<table class="t"><tr><th>Name</th><th>Level</th><th>Server</th><th><span class="sr-only">Actions</span></th></tr>${hits
          .slice(0, 30)
          .map(
            (h, i) =>
              `<tr><td>${esc(h.name)}</td><td>${h.level}</td><td>${esc(h.server)}</td><td class="r"><button class="btn small" data-imp="${i}">Import</button></td></tr>`,
          )
          .join("")}</table>`;
      $$("[data-imp]").forEach((b) => (b.onclick = () => doImport(hits[+b.dataset.imp])));
    } catch (e) {
      $("#cmsg").textContent = e.message;
    }
  };
  // ``cache``: how old (seconds) a saved profile may be to be shown without asking the official site; the
  // auto-open of the last character shows its last snapshot this way unless the refresh setting is on.
  const doImport = async (h, cache) => {
    $("#cview").innerHTML =
      `<div class="empty"><span class="spinner"></span> ${cache ? "opening the last snapshot of " + esc(h.name || "the character") + "…" : "importing from the official site…"}</div>`;
    try {
      const v = await runJob(
        "/api/character/import",
        cache ? { ...h, cache } : h,
        (log) => ($("#cmsg").textContent = log[log.length - 1] || ""),
      );
      st.v = v;
      st.hit = h;
      showChar();
    } catch (e) {
      $("#cview").innerHTML = `<div class="note">${esc(e.message)}</div>`;
    }
  };
  $$("[data-known-character]").forEach(
    (b) =>
      (b.onclick = () => {
        const c = known[Number(b.dataset.knownCharacter)];
        doImport({ character_id: c.character_id, server_id: c.server_id, region: c.region, name: c.name });
      }),
  );
  const showChar = () => {
    const v = st.v;
    let savedBudgets = {};
    try {
      savedBudgets = JSON.parse(localStorage.getItem("character-point-budgets") || "{}")[v.key] || {};
    } catch (_) {}
    const availableBudgets = Object.fromEntries(
      ["skill", "stigma", "daevanion"].map((k) => [
        k,
        Math.max(v.points[k], savedBudgets[k] ?? v.budgets?.[k] ?? v.points[k]),
      ]),
    );
    const rememberBudgets = () => {
      const values = Object.fromEntries(
        [...document.querySelectorAll("[data-character-budget]")].map((e) => [e.dataset.characterBudget, +e.value]),
      );
      let all = {};
      try {
        all = JSON.parse(localStorage.getItem("character-point-budgets") || "{}");
      } catch (_) {}
      all[v.key] = values;
      localStorage.setItem("character-point-budgets", JSON.stringify(all));
      return values;
    };
    $("#cview").innerHTML =
      `<section class="win"><div class="wh"><h2>${esc(v.name)}</h2><span class="sub">${esc(cap(v.class))} · Lv ${v.level} · ${esc(v.server)} · Combat Power ${n0(v.combat_power)}</span>
      <div class="tools"><button class="btn primary" id="opt" data-opt-mode="pve">Optimize PvE build</button><button class="btn" id="optpvp" data-opt-mode="pvp">Optimize PvP damage (experimental)</button><button class="btn" id="optworld" data-opt-mode="world" title="Large fights: area skills on several players, survival and crowd control weighed in">Optimize World PvP (experimental)</button></div></div><div class="wb">
      <div class="kpis">${Object.entries(v.dps || {})
        .map(
          ([k, x]) =>
            `<div class="kpi"><div class="k">${esc(k)} ${v.genus ? "saved build DPS" : "imported DPS (without manual Genus)"}</div><div class="v">${n0(x)}</div></div>`,
        )
        .join("")}
        <div class="kpi"><div class="k">Skill points</div><div class="v">${v.points.skill} / ${v.budgets?.skill ?? "Unknown"}</div></div><div class="kpi"><div class="k">Stigma points</div><div class="v">${v.points.stigma} / ${v.budgets?.stigma ?? "Unknown"}</div></div>
        <div class="kpi"><div class="k">Daevanion</div><div class="v">${v.points.daevanion} / ${v.budgets?.daevanion ?? "Unknown"}</div></div></div>
      ${progressionHTML(v.progression)}${(v.warnings || []).map((w) => `<div class="small muted">• ${esc(w)}</div>`).join("")}<p class="small muted">The profile gives allocated points. Unspent points and some quest rewards may be absent. Enter the total available in your game window (spent + unspent) before optimizing. These values are the observed lower bound, not a verified maximum.</p><div class="row">${["skill", "stigma", "daevanion"].map((k) => `<label>${cap(k)} total <input type="number" data-character-budget="${k}" min="${v.points[k]}" max="10000" value="${availableBudgets[k]}" style="width:103px"></label>`).join("")}<label>Game version (optional) <input id="cpointpatch" maxlength="100" placeholder="Unknown" value="${esc(localStorage.getItem("point-game-patch") || "")}"></label></div><p class="small muted">PvP optimization is an experimental damage-only estimate against a stationary player proxy. It does not score survival, crowd control or win chance. PvE and PvP results are saved separately.</p><label>Damage objective <select id="character-objective"><option value="primary">Primary scenario (existing behavior)</option><option value="balanced">Balanced: PvE boss/dummy or PvP sustained/burst</option></select></label><p class="small muted">Balanced uses 50% of each modeled DPS score and may trade primary damage for the combined score. HP and trained-skill reserves still apply. Rotation search takes longer; macro and skill-share views describe the primary scenario.</p><div id="survival-options"></div><div id="skill-reserves"></div><div id="character-genus"></div><div id="optres"></div></div></section><div id="cwins"></div>`;
    const objectiveSelect = $("#character-objective");
    objectiveSelect.value = localStorage.getItem("character-damage-objective") === "balanced" ? "balanced" : "primary";
    objectiveSelect.onchange = () => localStorage.setItem("character-damage-objective", objectiveSelect.value);
    const survivalOptions = mountSurvivalOptions(
      $("#survival-options"),
      "character-survival:" + JSON.stringify(st.hit || v.key || v.loadout),
      v,
    );
    const reservesOptions = mountSkillReserves(
      $("#skill-reserves"),
      "character-skill-reserves:" + JSON.stringify(st.hit || v.key || v.loadout),
      v,
    );
    const genusOptions = mountCharacterGenus($("#character-genus"), v.key);
    renderWindows(v, st, $("#cwins"));
    st.optMeta = {
      key: v.key,
      name: v.name,
      level: v.level,
      warnings: v.warnings,
      server: v.server,
      combat_power: v.combat_power,
    };
    $("#cpointpatch").onchange = () => localStorage.setItem("point-game-patch", $("#cpointpatch").value.trim());
    document.querySelectorAll("[data-character-budget]").forEach((e) => (e.onchange = rememberBudgets));
    const budgetFields = [...document.querySelectorAll("[data-character-budget]")],
      before = budgetFields.map((e) => e.value);
    // The community's totals come from characters at the level cap: a lower character cannot have them.
    const levelCap = v.level_cap || 45;
    if ((v.level ?? levelCap) < levelCap) {
      const note = document.createElement("p");
      note.className = "small muted";
      note.textContent = `Community point totals are not filled in below level ${levelCap}: they come from characters at the level cap.`;
      budgetFields[0]?.closest(".row")?.after(note);
    } else
      A2ProgressionBudgets.read(communityAPI, v.class, { region: st.hit?.region || "" })
        .then((result) => {
          if (S.character.v !== v || !budgetFields.every((e) => e.isConnected)) return;
          budgetFields.forEach((e, i) => {
            const total = result.points[e.dataset.characterBudget];
            if (total !== null && e.value === before[i]) e.value = Math.max(+e.value, total);
          });
          const note = document.createElement("p");
          note.className = "small muted";
          note.textContent = result.note;
          budgetFields[0]?.closest(".row")?.after(note);
        })
        .catch(() => {});

    document.querySelectorAll("[data-opt-mode]").forEach(
      (button) =>
        (button.onclick = async () => {
          if (S.character.opt?.status === "running") return;
          const mode = button.dataset.optMode;
          S.character.opt = { status: "running", mode, log: [], jobid: null };
          renderOptState();
          try {
            const { job } = await api("/api/character/optimize", {
              ...st.hit,
              mode,
              objective: objectiveSelect.value,
              budgets: rememberBudgets(),
              survival: survivalOptions.read(),
              skill_reserves: reservesOptions.read(),
              genus: genusOptions.read(mode),
              game_patch: $("#cpointpatch").value.trim(),
            });
            S.character.opt.jobid = job;
            pollOpt();
          } catch (e) {
            S.character.opt = { status: "error", error: e.message };
            renderOptState();
          }
        }),
    );
    renderOptState(); // show a job that is still running (or finished) after returning to this tab
  };
  if (st.v) showChar();
  else if (ui.character_auto_open && known.length && !st.autoOpened) {
    // Settings → My Character at launch: the character opened last (the newest import), from its last
    // snapshot, or refreshed from the official site when that setting is on too. Once per app session.
    st.autoOpened = true;
    const c = known[0];
    doImport(
      { character_id: c.character_id, server_id: c.server_id, region: c.region, name: c.name },
      ui.character_auto_refresh ? 0 : 10 * 365 * 86400,
    );
  }
}

// The character optimize runs for minutes on the server; keep its state in S.character so it survives
// switching tabs, and poll it with a background loop that repaints when the character page is shown.
function renderOptResult(r) {
  const st = S.character,
    box = $("#optres");
  if (!box) return;
  const g = r.summary.gain,
    scenario = r.summary.scenario || r.optimized.scenario || "boss";
  const objective = r.summary.objective || r.optimized.objective;
  const score = objective?.score ?? r.optimized.dps[scenario];
  const scoreLabel = objective?.label || (scenario === "pvp" ? "PvP proxy DPS" : "boss DPS");
  const preset = r.preset?.submitted
    ? r.preset.accepted
      ? "This build is now the community preset for its class."
      : "The server kept its current Planner preset: " +
        (r.preset.reason || "no improvement at the shared budgets") +
        ""
    : r.preset?.reason
      ? "Community preset: " + r.preset.reason
      : "";
  box.innerHTML = `<div class="kpis" style="margin-top:12px"><div class="kpi"><div class="k">Optimized ${esc(scoreLabel)}</div><div class="v">${n0(score)}</div></div>
      <div class="kpi"><div class="k">Gain</div><div class="v ${g > 0 ? "good" : ""}">${g == null ? "Unavailable" : (g >= 0 ? "+" : "") + pct(g)}</div></div></div>
      ${r.optimized.model_note ? `<p class="note">${esc(r.optimized.model_note)}</p>` : ""}${preset ? `<p class="small ${r.preset?.accepted ? "good" : "muted"}">${esc(preset)}</p>` : ""}<p class="small muted">The windows below now show the optimized build. What changes:</p><pre class="diff">${esc(r.diff)}</pre>`;
  st.v = Object.assign({}, r.optimized, st.optMeta || {});
  if ($("#cwins")) renderWindows(st.v, st, $("#cwins"));
}
function renderOptState() {
  if (!location.hash.startsWith("#/character")) return;
  const o = S.character.opt,
    box = $("#optres");
  if (!o || !box) return;
  document.querySelectorAll("[data-opt-mode]").forEach((b) => (b.disabled = o.status === "running"));
  if (o.status === "running") {
    const log = o.log || [];
    const last = log.length ? log[log.length - 1] : "starting…";
    box.innerHTML = `<p><span class="spinner"></span> Optimizing ${o.mode === "world" ? "World PvP (experimental)" : o.mode === "pvp" ? "PvP damage (experimental)" : "PvE build"} — <b>${esc(last)}</b></p>
      <pre class="diff small" style="max-height:150px;overflow:auto;margin-top:6px">${esc(log.slice(-8).join("\n"))}</pre>
      <p class="small faint">Runs the rotation, stigma, Daevanion and skill-point search. Progress stays visible during the stigma and skill-level searches; the full optimization may take a few minutes.</p>`;
  } else if (o.status === "error") box.innerHTML = `<div class="note">${esc(o.error || "optimization failed")}</div>`;
  else if (o.status === "done" && o.result) renderOptResult(o.result);
}
function pollOpt() {
  const o = S.character.opt;
  if (!o || o.status !== "running" || !o.jobid) return;
  api("/api/jobs/" + o.jobid)
    .then((j) => {
      if (S.character.opt !== o) return; // a newer run superseded this one
      o.log = j.log || o.log;
      if (j.status === "done") {
        o.status = "done";
        o.result = j.result;
      } else if (j.status === "error") {
        o.status = "error";
        o.error = j.error;
      }
      renderOptState();
      if (o.status === "running") setTimeout(pollOpt, 1200);
    })
    .catch(() => setTimeout(pollOpt, 2500)); // keep polling through transient fetch errors
}
