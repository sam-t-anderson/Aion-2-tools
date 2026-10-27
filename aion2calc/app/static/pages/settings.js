/* Settings (#/settings). */
"use strict";

// Preview the overlay event-notification sound: the uploaded sound if one is set,
// otherwise the same built-in two-note chime the overlay plays. Falls back to the
// chime if the custom file is absent. Called from a Test button (a user gesture).
function previewEventSound() {
  const chime = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const a = new Ctx();
      const t0 = a.currentTime;
      [
        [784, 0],
        [1046.5, 0.13],
      ].forEach(([f, dt]) => {
        const o = a.createOscillator(),
          g = a.createGain();
        o.type = "sine";
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t0 + dt);
        g.gain.exponentialRampToValueAtTime(0.22, t0 + dt + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.33);
        o.connect(g);
        g.connect(a.destination);
        o.start(t0 + dt);
        o.stop(t0 + dt + 0.36);
      });
    } catch (_) {}
  };
  try {
    const audio = new Audio("/overlay-event-sound?v=" + Date.now());
    audio.volume = 0.6;
    audio.onerror = () => chime();
    audio.play().catch(() => chime());
  } catch (_) {
    chime();
  }
}

async function showMaintenance() {
  const target = $("#maintenance-details");
  if (!target) return;
  target.textContent = "Inspecting managed cache and update files…";
  try {
    const r = await api("/api/maintenance");
    if (!target.isConnected) return;
    target.innerHTML = `<p class="small muted">${esc(r.note)}</p>${r.external_web_cache ? '<p class="note">An external web cache is configured; this tool leaves it untouched.</p>' : ""}${r.truncated ? '<p class="note">Scan limit reached; counts are lower bounds.</p>' : ""}<table class="t"><thead><tr><th>Category</th><th>Files</th><th>MiB</th><th>Oldest (days)</th><th>Cache cleanup eligible</th></tr></thead><tbody>${r.groups.map((g) => `<tr><td>${esc(g.category)}</td><td>${g.files}</td><td>${(g.bytes / 1048576).toFixed(2)}</td><td>${g.oldest_days}</td><td>${g.eligible_files} files / ${(g.eligible_bytes / 1048576).toFixed(2)} MiB</td></tr>`).join("")}</tbody></table>`;
  } catch (e) {
    if (target.isConnected) target.textContent = e.message;
  }
}
// Overlay look presets: a named bundle of the overlay's visual settings. These are
// the keys a preset may carry (mirrors settings_backup._VISUAL_KEYS).
const OVERLAY_VISUAL_KEYS = [
  "overlay_text_colors",
  "overlay_text_fonts",
  "overlay_text_halo",
  "overlay_halo_color",
  "overlay_text_retro",
  "overlay_glow",
  "overlay_glow_color",
  "overlay_hp_color",
  "overlay_ttk_color",
  "overlay_text_outline",
  "overlay_outline_color",
  "overlay_color_cycle",
  "overlay_bar_style",
  "overlay_bar_rounded",
  "overlay_class_color_names",
  "overlay_row_stripes",
  "overlay_class_swatch",
  "overlay_compact_rows",
  "overlay_rank_numbers",
  "overlay_highlight_me",
  "overlay_dps_graph",
  "overlay_font_family",
  "overlay_font_scale",
  "overlay_font_weight",
  "overlay_bg_opacity",
  "overlay_bg_zoom",
  "overlay_bg_darken",
  "overlay_text_autocontrast",
  "overlay_name_mode",
  "overlay_long_names_scroll",
  "combat_colors",
];
const BUNDLED_PRESETS = {
  "Default (gold)": {
    overlay_text_colors: {
      rate: "#ffffff",
      total: "#9bb1c1",
      name: "#e9f7ff",
      header: "#e8cf8e",
      target: "#f0d6da",
      hp: "#e9a4b6",
      ttk: "#e3ad7f",
    },
    overlay_text_fonts: {},
    overlay_text_halo: false,
    overlay_halo_color: "#e8cf8e",
    overlay_text_retro: false,
    overlay_glow: false,
    overlay_glow_color: "#e8cf8e",
    overlay_hp_color: "#e4808f",
    overlay_ttk_color: "#86a9c6",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "flat",
    overlay_bar_rounded: false,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 20,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  "Bold & large": {
    overlay_font_family: "Segoe UI",
    overlay_font_scale: 130,
    overlay_font_weight: 800,
    overlay_glow: true,
    overlay_glow_color: "#000000",
  },
  "High contrast": {
    overlay_text_colors: {
      rate: "#ffffff",
      total: "#ffffff",
      name: "#ffffff",
      header: "#ffd54a",
      target: "#ffffff",
      hp: "#ff6b6b",
      ttk: "#7fd0ff",
    },
    overlay_glow: false,
    overlay_glow_color: "#000000",
    overlay_hp_color: "#ff5a5a",
    overlay_ttk_color: "#7fd0ff",
    overlay_text_outline: true,
    overlay_outline_color: "#000000",
    overlay_bar_style: "flat",
    overlay_bar_rounded: false,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 106,
    overlay_font_weight: 700,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 50,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Neon: {
    overlay_text_colors: {
      rate: "#06121a",
      total: "#9ad8ff",
      name: "#39ff14",
      header: "#ff2fe6",
      target: "#00e5ff",
      hp: "#ff2d55",
      ttk: "#00e5ff",
    },
    overlay_glow: true,
    overlay_glow_color: "#00e5ff",
    overlay_hp_color: "#ff2d55",
    overlay_ttk_color: "#39ff14",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "Consolas",
    overlay_font_scale: 104,
    overlay_font_weight: 700,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 40,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Minimal: {
    overlay_text_colors: {
      rate: "#0a0a0a",
      total: "#0a0a0a",
      name: "#c8ccd4",
      header: "#9aa3b5",
      target: "#aeb6c6",
      hp: "#c89a9a",
      ttk: "#9ab3c6",
    },
    overlay_glow: false,
    overlay_glow_color: "#000000",
    overlay_hp_color: "#b06a6a",
    overlay_ttk_color: "#7f97aa",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "flat",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 92,
    overlay_font_weight: 400,
    overlay_bg_opacity: 84,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 14,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  "Midnight blue": {
    overlay_text_colors: {
      rate: "#0a0f1a",
      total: "#0a0f1a",
      name: "#cfe0ff",
      header: "#6fa8ff",
      target: "#a9c4ff",
      hp: "#ff8fb0",
      ttk: "#7fe0ff",
    },
    overlay_glow: true,
    overlay_glow_color: "#2b63c7",
    overlay_hp_color: "#ff6a9a",
    overlay_ttk_color: "#6fd0ff",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 32,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Ember: {
    overlay_text_colors: {
      rate: "#140804",
      total: "#140804",
      name: "#ffd9b0",
      header: "#ff9a3c",
      target: "#ffc08a",
      hp: "#ff6a3c",
      ttk: "#ffd27f",
    },
    overlay_glow: true,
    overlay_glow_color: "#ff6a1a",
    overlay_hp_color: "#ff5a2a",
    overlay_ttk_color: "#ffbf5a",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 700,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 36,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Aurora: {
    overlay_text_colors: {
      rate: "#04120e",
      total: "#bdeadd",
      name: "#39e0b0",
      header: "#7cf0c0",
      target: "#6fe0c8",
      hp: "#ff8fb0",
      ttk: "#7fe0ff",
    },
    overlay_glow: true,
    overlay_glow_color: "#2fd0a0",
    overlay_hp_color: "#ff6a9a",
    overlay_ttk_color: "#4fe0c0",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: true,
    overlay_font_family: "",
    overlay_font_scale: 102,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 34,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Sunset: {
    overlay_text_colors: {
      rate: "#1a0a04",
      total: "#ffd9c0",
      name: "#ffb37a",
      header: "#ff7e5f",
      target: "#ffc0a0",
      hp: "#ff5a6a",
      ttk: "#ffd27f",
    },
    overlay_glow: true,
    overlay_glow_color: "#ff7e5f",
    overlay_hp_color: "#ff4a6a",
    overlay_ttk_color: "#ffbf5a",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 102,
    overlay_font_weight: 700,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 36,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Crimson: {
    overlay_text_colors: {
      rate: "#140606",
      total: "#ffd9d9",
      name: "#ffd9d9",
      header: "#e98a8a",
      target: "#cdd6e6",
      hp: "#ff6a6a",
      ttk: "#8fb3d0",
    },
    overlay_glow: true,
    overlay_glow_color: "#e98a8a",
    overlay_hp_color: "#ff5a5a",
    overlay_ttk_color: "#8fb3d0",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 30,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Emerald: {
    overlay_text_colors: {
      rate: "#06120b",
      total: "#d7f5e1",
      name: "#d7f5e1",
      header: "#8fe0a8",
      target: "#cdd6e6",
      hp: "#ff8f8f",
      ttk: "#7fe0c0",
    },
    overlay_glow: true,
    overlay_glow_color: "#8fe0a8",
    overlay_hp_color: "#ff6a9a",
    overlay_ttk_color: "#4fe0c0",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 30,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Azure: {
    overlay_text_colors: {
      rate: "#06101a",
      total: "#d7ecf8",
      name: "#d7ecf8",
      header: "#8fc3e8",
      target: "#cdd6e6",
      hp: "#ff8fb0",
      ttk: "#7fe0ff",
    },
    overlay_glow: true,
    overlay_glow_color: "#8fc3e8",
    overlay_hp_color: "#ff6a9a",
    overlay_ttk_color: "#6fd0ff",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 30,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Amethyst: {
    overlay_text_colors: {
      rate: "#0f0818",
      total: "#ecdffb",
      name: "#ecdffb",
      header: "#c6a8f0",
      target: "#cdd6e6",
      hp: "#ff8fb0",
      ttk: "#8fb3d0",
    },
    overlay_glow: true,
    overlay_glow_color: "#c6a8f0",
    overlay_hp_color: "#ff6a9a",
    overlay_ttk_color: "#b07cff",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 30,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Rose: {
    overlay_text_colors: {
      rate: "#160810",
      total: "#fbdfeb",
      name: "#fbdfeb",
      header: "#f0a8c6",
      target: "#cdd6e6",
      hp: "#ff6a9a",
      ttk: "#8fb3d0",
    },
    overlay_glow: true,
    overlay_glow_color: "#f0a8c6",
    overlay_hp_color: "#ff4a7a",
    overlay_ttk_color: "#8fb3d0",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: false,
    overlay_font_family: "",
    overlay_font_scale: 100,
    overlay_font_weight: 600,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 30,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  Streamer: {
    overlay_text_colors: {
      rate: "#120d02",
      total: "#ffe6a8",
      name: "#ffe9c2",
      header: "#ffcf6b",
      target: "#cdd6e6",
      hp: "#ff8f8f",
      ttk: "#8fd0ff",
    },
    overlay_glow: true,
    overlay_glow_color: "#ffcf6b",
    overlay_hp_color: "#ff6a6a",
    overlay_ttk_color: "#7fc0ff",
    overlay_text_outline: true,
    overlay_outline_color: "#000000",
    overlay_bar_style: "gradient",
    overlay_bar_rounded: true,
    overlay_class_color_names: true,
    overlay_row_stripes: true,
    overlay_class_swatch: true,
    overlay_compact_rows: false,
    overlay_rank_numbers: true,
    overlay_highlight_me: true,
    overlay_font_family: "Segoe UI",
    overlay_font_scale: 118,
    overlay_font_weight: 700,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 34,
    overlay_name_mode: "name",
    overlay_long_names_scroll: true,
    combat_colors: {},
  },
  Tournament: {
    overlay_text_colors: {
      rate: "#ffffff",
      total: "#ffffff",
      name: "#ffffff",
      header: "#ffd54a",
      target: "#ffffff",
      hp: "#ff6b6b",
      ttk: "#7fd0ff",
    },
    overlay_glow: false,
    overlay_glow_color: "#000000",
    overlay_hp_color: "#ff5a5a",
    overlay_ttk_color: "#7fd0ff",
    overlay_text_outline: true,
    overlay_outline_color: "#000000",
    overlay_bar_style: "flat",
    overlay_bar_rounded: false,
    overlay_class_color_names: false,
    overlay_row_stripes: true,
    overlay_class_swatch: false,
    overlay_compact_rows: false,
    overlay_rank_numbers: true,
    overlay_highlight_me: true,
    overlay_font_family: "",
    overlay_font_scale: 108,
    overlay_font_weight: 700,
    overlay_bg_opacity: 100,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 55,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
  "Compact raid": {
    overlay_text_colors: {
      rate: "#0a0a0a",
      total: "#c8ccd4",
      name: "#d7dbe3",
      header: "#9aa3b5",
      target: "#aeb6c6",
      hp: "#c89a9a",
      ttk: "#9ab3c6",
    },
    overlay_glow: false,
    overlay_glow_color: "#000000",
    overlay_hp_color: "#b06a6a",
    overlay_ttk_color: "#7f97aa",
    overlay_text_outline: false,
    overlay_outline_color: "#000000",
    overlay_bar_style: "flat",
    overlay_bar_rounded: true,
    overlay_class_color_names: true,
    overlay_row_stripes: true,
    overlay_class_swatch: true,
    overlay_compact_rows: true,
    overlay_rank_numbers: true,
    overlay_highlight_me: true,
    overlay_font_family: "",
    overlay_font_scale: 90,
    overlay_font_weight: 500,
    overlay_bg_opacity: 92,
    overlay_bg_zoom: 100,
    overlay_bg_darken: 20,
    overlay_name_mode: "name",
    overlay_long_names_scroll: false,
    combat_colors: {},
  },
};
const BUNDLED_PRESET_DESC = {
  "Default (gold)": "The classic look — gold header, light names, black numbers on flat class-coloured bars.",
  "Bold & large":
    "Bigger, heavy Segoe UI with a dark glow for readability at a glance (layers onto your current colours).",
  "High contrast": "White text with a black outline on a darkened card — maximum readability over any scene.",
  Neon: "Vivid cyan/green/magenta with a glow, a monospace font and rounded gradient bars — a bright arcade look.",
  Minimal: "Muted greys, thin weight, slightly smaller and more transparent — unobtrusive, with soft rounded bars.",
  "Midnight blue": "Cool blue palette with a soft blue glow and rounded gradient bars.",
  Ember: "Warm reds and oranges with a fiery glow and rounded gradient bars.",
  Aurora: "Teal-and-green with a soft glow, gradient rounded bars and class-coloured names.",
  Sunset: "Pink-to-orange warmth with a glow and rounded gradient bars.",
  Crimson: "Overlay look matched to the Crimson app accent — red header and glow on rounded gradient bars.",
  Emerald: "Overlay look matched to the Emerald app accent — green header and glow on rounded gradient bars.",
  Azure: "Overlay look matched to the Azure app accent — blue header and glow on rounded gradient bars.",
  Amethyst: "Overlay look matched to the Amethyst app accent — purple header and glow on rounded gradient bars.",
  Rose: "Overlay look matched to the Rose app accent — pink header and glow on rounded gradient bars.",
  Streamer:
    "A showcase look for stream capture — big outlined gold text, rounded gradient bars, class swatches, rank numbers, zebra rows and your own row highlighted.",
  Tournament:
    "Maximum readability for competition — white outlined text on a strongly darkened card, flat bars, zebra rows, rank numbers and your own row highlighted.",
  "Compact raid":
    "Dense full-raid view — small class-coloured names, class swatches, rank numbers, compact rows (rate only), zebra striping and your own row highlighted.",
};
function overlayPresetOptions(ui) {
  const saved = Array.isArray(ui.overlay_presets) ? ui.overlay_presets : [];
  const opt = (v, l) => `<option value="${esc(v)}">${esc(l)}</option>`;
  const bundled = Object.keys(BUNDLED_PRESETS)
    .map((n) => opt("b::" + n, n))
    .join("");
  const user = saved.map((p) => opt("s::" + p.name, p.name)).join("");
  return (
    `<optgroup label="Starter presets">${bundled}</optgroup>` +
    (user ? `<optgroup label="Saved presets">${user}</optgroup>` : "")
  );
}
// Customization profiles: a named bundle of the whole app look — theme, accent,
// class colours and the overlay look — that the user can switch between. Stored
// in this browser (theme and accent are per-browser already).
function getCustomProfiles() {
  try {
    const a = JSON.parse(localStorage.getItem("a2-custom-profiles") || "[]");
    return Array.isArray(a) ? a : [];
  } catch (_) {
    return [];
  }
}
function saveCustomProfiles(list) {
  try {
    localStorage.setItem("a2-custom-profiles", JSON.stringify(list));
  } catch (_) {}
}
function customProfileOptions() {
  const list = getCustomProfiles();
  return (
    `<option value="">${list.length ? "Choose a profile…" : "No saved profiles yet"}</option>` +
    list.map((p) => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join("")
  );
}
// Downscale an image blob to a JPEG data URL small enough to live beside the
// profile in this browser's localStorage (overlay backgrounds can be up to 8 MB,
// but localStorage is ~5 MB total, so bundled copies are capped in size).
function downscaleImageToDataUrl(blob, maxDim, quality) {
  return new Promise((res) => {
    const url = URL.createObjectURL(blob),
      img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      try {
        let w = img.naturalWidth || img.width,
          h = img.naturalHeight || img.height;
        const s = Math.min(1, maxDim / Math.max(w, h || 1));
        w = Math.max(1, Math.round(w * s));
        h = Math.max(1, Math.round(h * s));
        const c = document.createElement("canvas");
        c.width = w;
        c.height = h;
        c.getContext("2d").drawImage(img, 0, 0, w, h);
        res(c.toDataURL("image/jpeg", quality));
      } catch (_) {
        res("");
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      res("");
    };
    img.src = url;
  });
}
// Snapshot the overlay's current background (served from the local app) as a
// downscaled data URL to bundle into a profile. Stays on this machine; never
// uploaded and never put in a share code. Returns '' when none is set.
async function captureOverlayBackground() {
  try {
    const resp = await fetch("/overlay-background?" + Date.now());
    if (!resp.ok) return "";
    const blob = await resp.blob();
    if (!blob || !blob.size) return "";
    return await downscaleImageToDataUrl(blob, 1400, 0.82);
  } catch (_) {
    return "";
  }
}
// A grid of square tiles — one per profile that bundles a background — showing
// the background preview and the profile name; clicking a tile applies it.
function customProfileGallery() {
  const list = getCustomProfiles().filter((p) => typeof p.bg === "string" && p.bg);
  if (!list.length) return "";
  return (
    `<div class="custgallery" role="group" aria-label="Profiles with a bundled background">` +
    list
      .map(
        (p) =>
          `<button type="button" class="custtile" data-cust-tile="${esc(p.name)}" title="Apply ${esc(p.name)}"><span class="custtile-img" style="background-image:url('${esc(p.bg)}')"></span><span class="custtile-name">${esc(p.name)}</span></button>`,
      )
      .join("") +
    `</div>`
  );
}
// The Hidden Cube radar's learn steps and their keys: hotkeys.py RADAR_DEFAULTS unless Settings -> Hotkeys
// changed them ("" leaves one unbound), so the settings name the keys the game actually gives the app.
const RADAR_STEPS = {
  radar_learn_background: "Ctrl+1",
  radar_learn_cube: "Ctrl+2",
  radar_learn_cube_behind: "Ctrl+3",
  radar_learn_other: "Ctrl+4",
};
function radarKey(ui, action) {
  const saved = ui && ui.hotkeys && typeof ui.hotkeys === "object" ? ui.hotkeys : {};
  return action in saved ? saved[action] || "" : RADAR_STEPS[action];
}
function radarNotes(ui) {
  const key = (action, button) => (radarKey(ui, action) ? `<b>${esc(radarKey(ui, action))}</b>` : button);
  return `<div class="small muted" style="margin:2px 0 6px 22px">
      <p style="margin:0 0 4px">Put headphones on and, in the game's sound settings, turn 3D audio on and mute the music, ambient, monster and your own character's sounds, keeping the effect volume up (what the cube guides advise). Then teach the radar the game's sound in samples. In the game, while the radar is on, each step's key listens at once; its button here waits 5 seconds first, so you can switch back to the game.</p>
      <ol style="margin:0 0 4px;padding-left:18px">
        <li>${key("radar_learn_background", "Button 1")} where no cube or feather can be heard, for the background (it listens 4 seconds). Take one in each kind of place you search: the radar takes off what it learned of each before it listens for the jingle.</li>
        <li>${key("radar_learn_cube", "Button 2")} facing a Hidden Cube while it jingles (8 seconds): first beside it, then a few steps away, then as far off as you can still hear it. The farther samples teach it the jingle at a distance and set how far its rings reach.</li>
        <li>${key("radar_learn_cube_behind", "Button 3")} from where you took one, with your back to the cube: it learns how the game's 3D audio changes the jingle behind you, and then shows whether the cube is ahead of you or behind.</li>
      </ol>
      <p style="margin:0 0 4px">${key("radar_learn_other", "The “not a cube” button")} while a sound the radar takes for a cube plays (an Empyrean Trace feather, a voice in voice chat; 6 seconds): it no longer takes that sound for one, unless it sounds the same as the cube's.</p>
      <p style="margin:0">The overlay then shows the cube on a circle around you, ahead of you at the top: louder is closer. Without the game's 3D audio or a surround output, stereo cannot tell ahead from behind: the radar shows both places the cube can be, and turning towards it tells which (a cube ahead moves to the middle, one behind further out), as does walking forward (one ahead grows louder). Raise the sensitivity to hear a cube farther away, lower it if voice chat sets it off. Settings → Hotkeys changes the keys. The app reads what Windows plays, in memory, and keeps only the samples' levels in 40 frequency bands and the jingle's peak frequencies: nothing is recorded or uploaded.</p></div>`;
}
async function pageSettings() {
  const shown = stillShown();
  const [s, srv, ui] = await Promise.all([
    api("/api/status"),
    api("/api/logserver").catch(() => ({})),
    api("/api/ui").catch(() => ({})),
  ]);
  if (!shown()) return;
  const t = getTheme();
  // Pickers show the overlay stylesheet's own defaults until a colour is chosen (saving writes every key).
  const OVERLAY_TEXT_DEFAULTS = {
    rate: "#ffffff",
    total: "#9bb1c1",
    name: "#e9f7ff",
    header: "#e8cf8e",
    target: "#f0d6da",
    hp: "#e9a4b6",
    ttk: "#e3ad7f",
    label: "#b39aa2",
    also: "#c9a86a",
    ping: "#76c59d",
    identity: "#e8cf8e",
  };
  const overlayColors = ui.overlay_text_colors || {},
    overlayText = (key) =>
      /^#[0-9a-f]{6}$/i.test(overlayColors[key] || "") ? overlayColors[key] : OVERLAY_TEXT_DEFAULTS[key];
  app().innerHTML = win(
    "Settings",
    "",
    `
    <div class="settabs" role="group" aria-label="Settings sections">${[
      ["appearance", "Appearance"],
      ["overlay", "Overlay"],
      ["pettracker", "Pet Tracker"],
      ["meter", "Meter"],
      ["server", "Server"],
      ["backup", "Profiles &amp; backup"],
      ["system", "App &amp; data"],
    ]
      .map(([g, l]) => `<button type="button" data-settab="${g}" aria-pressed="false">${l}</button>`)
      .join("")}</div>
    <div class="setrow" data-g="appearance"><div class="lbl">Theme</div><div><div class="seg">${THEMES.map((x) => `<button data-th="${x}" class="${x === t ? "on" : ""}">${{ system: "Follow computer", light: "Light", dark: "Dark" }[x]}</button>`).join("")}</div></div></div>
    <div class="setrow" data-g="appearance"><div class="lbl">Accent colour</div><div><div class="seg">${ACCENTS.map((x) => `<button data-accent-btn="${x}" class="${x === getAccent() ? "on" : ""}">${x[0].toUpperCase() + x.slice(1)}</button>`).join("")}</div><p class="small muted">Recolours the app's accent on top of your light/dark theme.</p></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Open as its own window</div><div><label><input type="checkbox" id="appwin" ${ui.app_window !== false ? "checked" : ""}> start in a separate app window (Edge or Chrome) instead of a browser tab; closing it stops the app</label><p class="small muted">The window opens at 1920×1080, or as large as the screen allows when it is smaller, centred; it is not maximized, so you can place and size it.</p></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Text size</div><div><label>Size of the app's text <select id="textscale">${[70, 80, 90, 100, 110, 120, 130, 140, 150].map((p) => `<option value="${p}" ${(parseInt(ui.app_text_scale, 10) || 100) === p ? "selected" : ""}>${p}%</option>`).join("")}</select></label><p class="small muted">Scales every word in the app, and the layout with it, like the browser's zoom; 100% is the size the app ships with. The overlay's text has its own size under Live meter overlay.</p></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Language</div><div><span id="setlang" class="lang-slot"></span><p class="small muted">The app's buttons, headings and short texts; the game's names, long explanations, the overlay and the reports stay in English. The same choice as at the top of the page.</p></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Page at launch</div><div><label>Open the app on <select id="defaultpage">${LAUNCH_PAGES.map(([id, label]) => `<option value="${id}" ${(ui.app_default_page || "meter") === id ? "selected" : ""}>${label}</option>`).join("")}</select></label><p class="small muted">The page the app shows when it starts, and when the tray icon or the Open-app hotkey brings it back. Links to the other pages work as before.</p></div></div>
    <div class="setrow" data-g="system"><div class="lbl">My Character at launch</div><div><label><input type="checkbox" id="char-auto-open" ${ui.character_auto_open === true ? "checked" : ""}> Show the character you opened last when My Character opens <span class="muted">(off by default)</span></label>
      <p class="small muted">With My Character as the page at launch, the app opens straight on your character: the newest of the characters imported before, from the snapshot saved at its last import, so it shows at once and without the official site.</p>
      <label><input type="checkbox" id="char-auto-refresh" ${ui.character_auto_refresh === true ? "checked" : ""}> Refresh that character from the official site when the app opens, instead of showing the last snapshot <span class="muted">(off by default; needs the setting above)</span></label></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Collapse to tray</div><div><label><input type="checkbox" id="trayclose" ${ui.tray_on_close ? "checked" : ""}> keep running in the system tray when the window is closed (Windows, macOS, Linux); Quit from the tray icon. Takes effect on next launch.</label></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Your data</div><div><code>${esc(s.home)}</code> <button class="btn small" data-open="data">Open folder</button> <button class="btn small" data-open="logs">Combat logs</button> <button class="btn small" data-open="results">Advice &amp; results</button></div></div>
    <div class="setrow" data-g="server"><div class="lbl">Log server</div><div><div class="row"><input id="surl" type="text" placeholder="${srv.is_default && srv.url ? esc(srv.url) + " (default)" : "https://logs.example.com"}" value="${srv.is_default ? "" : esc(srv.url || "")}" style="width:320px">
      <input id="skey" type="password" placeholder="${srv.has_key ? "key saved" : "upload key (optional)"}" style="width:229px">
      <select id="svis" aria-label="Who can see your uploads" title="Public uploads are listed in the community logs and count in the rankings; unlisted ones open only with their link; legion only ones open for the members of your legions (signed in, Account); private ones need the secret link">${["public", "unlisted", "legion", "private"].map((v) => `<option value="${v}" ${v === (srv.visibility || "public") ? "selected" : ""}>${v === "legion" ? "legion only" : v}</option>`).join("")}</select>
      <button class="btn small" id="ssave">Save</button><button class="btn small" id="scheck">Check saved server</button><span id="smsg" class="small muted"></span></div>
      ${srv.is_default && srv.url ? '<div class="small muted" style="margin-top:4px">Using the community default server. Enter your own above to override it.</div>' : ""}</div></div>
    <div class="setrow" data-g="server"><div class="lbl">Community stats</div><div><label><input type="checkbox" id="community-heartbeat" ${ui.community_heartbeat !== false ? "checked" : ""}> Contribute to the anonymous daily-active-meters count (on by default)</label>
      <p class="small muted">Once a day the app tells the configured log server that a meter ran, so the community can see how many are active. It sends only an anonymous token that rotates every day (it can't be traced to you or linked across days), the date, and the app version — never your name, character, server, IP or any combat data. Uncheck to opt out.</p>
      <label style="margin-top:6px"><input type="checkbox" id="contribute-character" ${ui.community_contribute_character !== false ? "checked" : ""}> Share your build's point totals when you collect a character (on by default)</label>
      <p class="small muted">When you collect a character in My Character, send its spent skill, stigma and Daevanion point totals to the community "highest observed build points" so the shared budgets stay current. Anonymous: only the class, region, game version and the three point totals — never your name, character, server, IP or gear. Running Optimize already shares these; this adds the same from a plain collect. Uncheck to opt out.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Live meter overlay</div><div><label><input type="checkbox" id="ov-open-on-app" ${ui.overlay_open_on_app_start !== false ? "checked" : ""}> Open the overlay when the app starts (on by default)</label><p class="small muted">The overlay opens with the app and waits for the game; it still follows the AION 2 window when that appears.</p>
      <label><input type="checkbox" id="ov-on-start" ${ui.overlay_on_start !== false ? "checked" : ""}> Show overlay when starting the live meter</label><p class="small muted">Also available beside Start on the Live Meter page.</p>
      <label><input type="checkbox" id="ov-close-on-stop" ${ui.overlay_close_on_stop === true ? "checked" : ""}> Close the overlay when I stop the meter (off by default — the overlay stays up showing the last fight, and its own Stop button never closes it)</label>
      <label><input type="checkbox" id="ov-contribution" ${ui.overlay_show_contribution !== false ? "checked" : ""}> Show your contribution (your share of the encounter's damage)</label>
      <label><input type="checkbox" id="ov-target" ${ui.overlay_show_target !== false ? "checked" : ""}> Show the current target and each player's DPS to it</label>
      <label><input type="checkbox" id="ov-deaths" ${ui.overlay_show_deaths !== false ? "checked" : ""}> Mark party members who are dead (row shows DEAD until they recover)</label>
      <label><input type="checkbox" id="ov-enemy-hp" ${ui.overlay_show_enemy_hp === true ? "checked" : ""}> Show the current target's remaining HP as a percentage and bar (only when the game reports it). The game's internal HP value is on a much larger scale than damage numbers, so it is shown as a percentage, not a raw number that won't match your damage.</label>
      <label><input type="checkbox" id="ov-ttk" ${ui.overlay_show_ttk === true ? "checked" : ""}> Show estimated time-to-kill for the current target, as a number and a progress bar (from the target's observed HP-decline rate)</label>
      <label><input type="checkbox" id="ov-break-gauge" ${ui.overlay_show_break_gauge === true ? "checked" : ""}> Show the current target's break (stagger) gauge, as a readout and a bar <span class="muted">(bosses and elites carry one; off by default)</span></label>
      <label><input type="checkbox" id="ov-cooldowns" ${ui.overlay_show_cooldowns === true ? "checked" : ""}> Show a strip of your skills on cooldown, each counting down <span class="muted">(off by default)</span></label>
      <div class="row" style="gap:10px;margin:0 0 2px 22px"><label>Shortest cooldown shown <input type="number" id="ov-cd-min" min="1" max="120" value="${Number.isFinite(+ui.overlay_cooldowns_min_s) ? +ui.overlay_cooldowns_min_s : 3}" style="width:74px"> s</label><label>Icons <input type="number" id="ov-cd-max" min="1" max="16" value="${Number.isFinite(+ui.overlay_cooldowns_max) ? +ui.overlay_cooldowns_max : 8}" style="width:74px"></label><label>Position <select id="ov-cd-pos"><option value="bottom" ${ui.overlay_cooldowns_position !== "top" ? "selected" : ""}>Below the meter</option><option value="top" ${ui.overlay_cooldowns_position === "top" ? "selected" : ""}>Above the player rows</option></select></label></div>
      <p class="small muted" style="margin:0 0 6px 22px">Uses the cooldown the game sends with each of your casts, so your cooldown reduction is already included and there is nothing to set up. It only knows skills you have used since Start. A skill lights up as it comes off cooldown, and an open chain-skill window shows first. If a proc resets a cooldown, the strip catches up on your next cast.</p>
      <label><input type="checkbox" id="ov-cp" ${ui.overlay_show_combat_power !== false ? "checked" : ""}> Show your combat power beside your name (when the game reports it)</label>
      <label title="The game's own count, sent when you enter the world, at every zone load and whenever it changes"><input type="checkbox" id="ov-odyle" ${ui.overlay_show_odyle !== false ? "checked" : ""}> Show your Odyle Energy on the overlay and the Live Meter page <span class="muted">(on by default)</span></label>
      <label title="The game's own count of your Shugo Festival Reward Keys, sent with the same counters as Odyle Energy"><input type="checkbox" id="ov-shugo" ${ui.overlay_show_shugo_keys !== false ? "checked" : ""}> Show your Shugo Festival keys on the overlay and the Live Meter page <span class="muted">(on by default)</span></label>
      <label title="The game's own count of your Nightmare tickets, sent with the same counters as Odyle Energy"><input type="checkbox" id="ov-nightmare" ${ui.overlay_show_nightmare_tickets !== false ? "checked" : ""}> Show your Nightmare tickets on the overlay and the Live Meter page <span class="muted">(on by default)</span></label>
      <label title="After a fight auto-uploads, show your community standing (e.g. “World Top 8%”) for that encounter beside your name"><input type="checkbox" id="ov-community-rank" ${ui.overlay_show_community_rank === true ? "checked" : ""}> Show your community rank for your last uploaded fight <span class="muted">(needs auto-upload; off by default)</span></label>
      <label title="While capturing, refresh your community-rank badge after each ranked fight by uploading it, instead of only when you press Upload"><input type="checkbox" id="ov-live-rank" ${ui.overlay_live_community_rank === true ? "checked" : ""}> Update the rank live after each fight <span class="muted">(needs the rank badge on + a share server; uploads each ranked fight at your upload visibility; off by default)</span></label>
      <label title="Shows the next rift / Shugo / battlefield / field-boss windows for your region when one is active or within 15 minutes"><input type="checkbox" id="ov-events" ${ui.overlay_show_events !== false ? "checked" : ""}> Show regional event notifications on the overlay <span class="muted">(uses the region you pick on the Timers page; community forecast, on by default)</span></label>
      <label title="Field and world bosses the live meter saw die on your server count down to their return in the event strip"><input type="checkbox" id="ov-field-bosses" ${ui.overlay_show_field_bosses !== false ? "checked" : ""}> Include observed field-boss timers in the event strip <span class="muted">(kills recorded on your server and faction; on by default)</span></label>
      <label title="Play a short chime when an event notification appears on the overlay"><input type="checkbox" id="ov-events-sound" ${ui.overlay_events_sound === true ? "checked" : ""}> Play a sound when an event notification appears <span class="muted">(off by default)</span></label>
      <div class="row" style="gap:6px;margin:0 0 4px 22px"><label class="btn small" for="ov-events-sound-file">Upload sound</label><input type="file" id="ov-events-sound-file" accept="audio/mpeg,audio/ogg,audio/wav,audio/webm" style="display:none"><button class="btn small" id="ov-events-sound-test" type="button">Test</button><button class="btn small" id="ov-events-sound-clear" type="button">Use default chime</button><span id="ov-events-sound-msg" class="small muted" role="status">${ui.overlay_events_sound_set ? "Custom sound set (≤2s recommended)." : "Built-in chime."}</span></div>
      <label><input type="checkbox" id="ov-plan-autoplay" ${ui.overlay_plan_autoplay !== false ? "checked" : ""}> Auto-play a saved raid plan on the overlay's Plan tab when you fight the boss it is bound to, synced to the pull (on by default)</label><p class="small muted">Bind a plan to a boss in the Raid planner (set its Boss / NPC id). When the meter is in that fight, the Plan tab plays that plan at the encounter's elapsed time; otherwise it loops the latest plan as a preview.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Hidden Cube radar</div><div><label><input type="checkbox" id="radar-enabled" ${ui.radar_enabled === true ? "checked" : ""}> Show where a Hidden Cube is around you and how near, from the jingle it plays <span class="muted">(Windows; off by default)</span></label>
      <p class="small muted" style="margin:2px 0 4px 22px">The radar is its own small overlay window, opened beside the meter overlay while it is on, with its own opacity slider, Lock and Hide; it remembers where you drag it. After Hide, <b>Open overlay</b> or the radar's on/off hotkey brings it back.</p>
      <div class="row" style="gap:6px;margin:4px 0 2px 22px;flex-wrap:wrap"><button class="btn small" id="radar-learn-bg" type="button">1. Learn the background</button><button class="btn small" id="radar-learn-cube" type="button">2. Learn the cube, facing it</button><button class="btn small" id="radar-learn-behind" type="button">3. Learn the cube behind you</button><button class="btn small" id="radar-learn-other" type="button">Learn a sound that is not a cube</button><button class="btn small" id="radar-cancel" type="button" hidden>Cancel</button><button class="btn small" id="radar-clear" type="button">Forget every sample</button><label>Sensitivity <input type="range" id="radar-sens" min="1" max="10" value="${Number.isInteger(+ui.radar_sensitivity) && +ui.radar_sensitivity >= 1 && +ui.radar_sensitivity <= 10 ? +ui.radar_sensitivity : 5}" style="width:110px;vertical-align:middle"></label></div>
      <p id="radar-status" class="small muted" style="margin:2px 0 4px 22px" role="status">Radar status unknown.</p>
      <ul id="radar-samples" class="small" style="margin:2px 0 4px 22px;padding-left:18px" aria-label="Learned sound samples" hidden></ul>
      ${radarNotes(ui)}</div></div>
    <div class="setrow" data-g="pettracker"><div class="lbl">Pet Tracker</div><div><p>Pet Tracker, by 0Fox2Give, shows your pet ranks and how many souls you still need while you farm. Aion 2 Calc can install it, run its capture, and show its pets in an overlay window of its own and on the <a href="#/pets">Pet Tracker page</a>.</p><div id="pt-set-status" class="small muted" role="status">Checking Pet Tracker…</div><p id="pt-set-note" class="small" role="status"></p></div></div>
    <div class="setrow" data-g="pettracker"><div class="lbl">Use Pet Tracker</div><div><label><input type="checkbox" id="pt-set-enabled" ${ui.pettracker_enabled === true ? "checked" : ""}> Run Pet Tracker's capture with Aion 2 Calc <span class="muted">(Windows; off by default)</span></label><p class="small muted">It starts with the app, before you log into your character, so your collection syncs at login. When the app quits it stops too, unless Pet Tracker's own window is open and still using it.</p></div></div>
    <div class="setrow" data-g="pettracker"><div class="lbl">Pet Tracker overlay</div><div><div class="row"><label><input type="checkbox" id="pt-set-overlay" ${ui.pettracker_overlay === true ? "checked" : ""}> Show the Pet Tracker overlay while the game runs</label><select id="pt-set-style" aria-label="Which window"><option value="app" ${ui.pettracker_overlay_style !== "pettracker" ? "selected" : ""}>in Aion 2 Calc's own window</option><option value="pettracker" ${ui.pettracker_overlay_style === "pettracker" ? "selected" : ""}>as Pet Tracker's own window</option></select></div><p class="small muted">Aion 2 Calc's window is a separate overlay with its own Lock, Hide and opacity, and it remembers where you put it. While it is open, a running Pet Tracker's own overlay is hidden, so one shows, not two; it comes back when the window closes. Pet Tracker's own window adds Find a pet, farming maps and the Black Cloud Merchant list; if Pet Tracker started minimized, show it once from its tray icon. A hotkey can show and hide either (Overlay → Hotkeys).</p></div></div>
    <div class="setrow" data-g="pettracker"><div class="lbl">Pet Tracker folder</div><div><div class="row"><input id="pt-set-path" type="text" placeholder="Found automatically" value="${esc(ui.pettracker_path || "")}" style="width:380px" aria-label="Pet Tracker folder"><button class="btn small" id="pt-set-path-save">Save</button><span id="pt-set-msg" class="small muted" role="status"></span></div><p class="small muted">Only for a copy of Pet Tracker unpacked in a folder of your own (its portable ZIP). Leave it empty to use the installed one.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">In-game (RTSS)</div><div><label><input type="checkbox" id="rtss-enabled" ${ui.rtss_enabled === true ? "checked" : ""}> Draw the meter inside the game through RivaTuner Statistics Server <span class="muted">(Windows; off by default; needs RTSS running with its on-screen display enabled)</span></label>
      <div class="row" style="gap:10px;margin:4px 0 2px 22px"><label>Rows <input type="number" id="rtss-rows" min="1" max="24" value="${Number.isFinite(+ui.rtss_rows) ? +ui.rtss_rows : 5}" style="width:80px"></label><label>Metric <select id="rtss-metric"><option value="dps" ${(ui.rtss_metric || "dps") === "dps" ? "selected" : ""}>DPS</option><option value="hps" ${ui.rtss_metric === "hps" ? "selected" : ""}>HPS</option><option value="dtps" ${ui.rtss_metric === "dtps" ? "selected" : ""}>Damage taken</option></select></label><label>Style <select id="rtss-style"><option value="plain" ${(ui.rtss_style || "plain") === "plain" ? "selected" : ""}>Plain text</option><option value="colored" ${ui.rtss_style === "colored" ? "selected" : ""}>Class colours (RTSS colour tags)</option></select></label><label>Refresh <input type="number" id="rtss-interval" min="100" max="5000" step="50" value="${Number.isFinite(+ui.rtss_interval_ms) ? +ui.rtss_interval_ms : 500}" style="width:92px"> ms</label></div>
      <p id="rtss-status" class="small muted" style="margin:2px 0 4px 22px" role="status">RTSS status unknown.</p>
      <p class="small muted" style="margin:2px 0 6px 22px">The app writes the meter text into RTSS's own shared memory (an OSD slot named Aion2Calc); RTSS draws it inside the game the way it draws its frame counter. Nothing is injected into or loaded by the game by this app; RTSS does its own hooking under its own terms. Position, font and size come from RTSS's settings. A first draft: please report what you see.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Streaming (OBS / Discord)</div><div><div class="row"><input id="ov-stream-url" type="text" readonly value="${esc(location.origin)}/overlay" style="width:343px" aria-label="Overlay browser-source URL"><button class="btn small" id="ov-stream-copy">Copy URL</button><span id="ov-stream-msg" class="small muted" role="status"></span></div>
      <p class="small muted">Add this as an <b>OBS / Streamlabs Browser Source</b> (it renders transparent) and composite it over your game-capture scene, then stream that scene to Discord — the overlay shows on your stream. To go through Discord <b>Go&nbsp;Live</b> directly instead, share your <b>whole screen</b> (not just the game window) so the always-on-top overlay is included.</p>
      <p class="small muted">A game-<i>window</i>-only share will <b>not</b> show the overlay: it's a separate window layered on top, not part of the game's own frame, so a per-window capture never includes it (the same reason most meter overlays don't appear in window captures). Use a Browser Source or full-screen share.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Overlay layout</div><div><div class="row"><label>Players shown <input type="number" id="ov-maxp" min="1" max="24" value="${Number(ui.overlay_max_players) || 8}" style="width:74px"></label><label>Width <input type="number" id="ov-width" min="260" max="800" value="${Number(ui.overlay_width) || 340}" style="width:80px"> px</label><label>Height <input type="number" id="ov-height" min="0" max="800" value="${Number(ui.overlay_height) || 0}" style="width:74px"> px <span class="muted small">(0 = fit to contents)</span></label><label>Row height <input type="number" id="ov-rowh" min="14" max="48" value="${Number(ui.overlay_row_height) || 22}" style="width:74px"> px</label><span id="ov-layout-msg" class="small muted" role="status"></span></div>
      <label><input type="checkbox" id="ov-autoexp" ${ui.overlay_auto_expand === true ? "checked" : ""}> Auto-expand to show every captured player (beyond the limit above)</label>
      <label><input type="checkbox" id="ov-onlycombat" ${ui.overlay_only_in_combat === true ? "checked" : ""}> Show the meter only during combat (collapse between pulls)</label>
      <label>Name display <select id="ov-namemode">${[
        ["name", "Character names"],
        ["class_number", "Class + party number"],
        ["number", "Party number only"],
      ]
        .map(
          ([v, l]) => `<option value="${v}" ${v === (ui.overlay_name_mode || "name") ? "selected" : ""}>${l}</option>`,
        )
        .join("")}</select></label>
      <label><input type="checkbox" id="ov-scrollnames" ${ui.overlay_long_names_scroll === true ? "checked" : ""}> Scroll long names on hover</label>
      <label>Bar style <select id="ov-barstyle">${[
        ["flat", "Flat class colour"],
        ["gradient", "Gradient"],
      ]
        .map(
          ([v, l]) => `<option value="${v}" ${v === (ui.overlay_bar_style || "flat") ? "selected" : ""}>${l}</option>`,
        )
        .join("")}</select></label>
      <label><input type="checkbox" id="ov-barrounded" ${ui.overlay_bar_rounded === true ? "checked" : ""}> Rounded bar corners</label>
      <label><input type="checkbox" id="ov-classnames" ${ui.overlay_class_color_names === true ? "checked" : ""}> Colour player names by class</label>
      <label><input type="checkbox" id="ov-stripes" ${ui.overlay_row_stripes === true ? "checked" : ""}> Zebra-stripe the player rows</label>
      <label><input type="checkbox" id="ov-classswatch" ${ui.overlay_class_swatch === true ? "checked" : ""}> Show a class-colour swatch before each name</label>
      <label><input type="checkbox" id="ov-compact" ${ui.overlay_compact_rows === true ? "checked" : ""}> Compact rows (hide the total &amp; percent, keep the per-second rate)</label>
      <label><input type="checkbox" id="ov-rank" ${ui.overlay_rank_numbers === true ? "checked" : ""}> Show rank numbers (1., 2., 3. …) before each name</label>
      <label><input type="checkbox" id="ov-highlight-me" ${ui.overlay_highlight_me === true ? "checked" : ""}> Highlight my own row (accent bar, so you can find yourself at a glance)</label>
      <label><input type="checkbox" id="ov-interp" ${ui.overlay_dps_interpolate === true ? "checked" : ""}> Live-ticking DPS numbers (recompute between polls for a real-time feel; on by default) <input type="number" id="ov-interp-ms" min="50" max="1000" value="${Number(ui.overlay_interpolate_ms) || 200}" style="width:74px"> ms</label>
      <label><input type="checkbox" id="ov-dps-graph" ${ui.overlay_dps_graph === true ? "checked" : ""}> Show a live DPS/HPS graph (a sparkline of the party total over the fight, from real per-poll readings)</label>
      <label><input type="checkbox" id="ov-fps" ${ui.overlay_show_fps === true ? "checked" : ""}> Show the overlay's own render FPS (the game's FPS can't be read from capture)</label>
      <label><input type="checkbox" id="ov-clickthrough" ${ui.overlay_click_through === true ? "checked" : ""}> Click through the overlay — let the mouse pass through to the game, so the overlay never eats a click <span class="muted small">(Windows; the overlay's own buttons/sliders still work when you hover them)</span></label>
      <label><input type="checkbox" id="ov-party" ${ui.overlay_party_enabled === true ? "checked" : ""}> Open a separate Party-DPS overlay (raid totals) alongside the meter</label>
      <p class="small muted" style="margin-top:6px">These need the overlay reopened to apply:</p>
      <label><input type="checkbox" id="ov-always" ${ui.overlay_always_visible !== false ? "checked" : ""}> Keep the overlay visible even when the game is not in focus (on by default; so clicking another overlay, the app window or a game popup never hides it)</label>
      <label><input type="checkbox" id="ov-remember-pos" ${ui.overlay_remember_position !== false ? "checked" : ""}> Remember where I drag the overlay and reopen it there, instead of following the game window (on by default, Windows; each overlay remembers its own spot — uncheck to follow the game window instead)</label>
      <label><input type="checkbox" id="ov-resizable" ${ui.overlay_resizable === true ? "checked" : ""}> Resize the overlay by dragging its edges/corners</label>
      <label><input type="checkbox" id="ov-snap" ${ui.overlay_snap_edge === true ? "checked" : ""}> Snap to the game window's edges</label>
      <label><input type="checkbox" id="ov-expandup" ${ui.overlay_expand_up === true ? "checked" : ""}> Expand upward (anchor the overlay near the bottom of the game window)</label>
      <p class="small muted">Applies to the live overlay; changes reach an open overlay within 10 seconds.</p></div></div>
    <div class="setrow" data-g="meter"><div class="lbl">Combat records</div><div><label><input type="checkbox" id="rec-reset" ${ui.meter_reset_after_battle === true ? "checked" : ""}> Clear the live meter after a battle ends (off by default — the last fight's numbers stay on the overlay until the next fight, a wipe or a manual clear)</label>
      <label><input type="checkbox" id="rec-boss-reset" ${ui.meter_reset_on_boss_start !== false ? "checked" : ""}> Reset the live meter when a boss fight starts (on by default — a boss, mini-boss, field boss or world boss pull clears the overlay so each fight shows fresh)</label>
      <div class="row" style="margin-top:4px"><label>Reset delay <input type="number" id="rec-delay" min="1" max="120" value="${Number(ui.meter_reset_delay) || 5}" style="width:74px"> s</label><label>Keep up to <input type="number" id="rec-max" min="1" max="500" value="${Number(ui.meter_max_records) || 20}" style="width:80px"> past combats</label><span id="rec-msg" class="small muted" role="status"></span></div>
      <label><input type="checkbox" id="rec-save" ${ui.meter_save_records !== false ? "checked" : ""}> Save combat records automatically (write each session to the logs folder)</label>
      <div class="row" style="margin-top:4px"><label>Keep the logs folder under <input type="number" id="rec-logcache" min="0" max="1048576" step="128" value="${Number.isFinite(+ui.meter_log_cache_mb) ? +ui.meter_log_cache_mb : 1024}" style="width:103px"> MB</label><span id="rec-logcache-msg" class="small muted" role="status"></span></div>
      <p class="small muted" style="margin:2px 0 6px 14px">A long session writes many rollover parts; when the logs folder passes this size the oldest recordings are deleted automatically to make room (the one being captured is never deleted). Default 1024 MB (1 GB); set 0 to never auto-delete.</p>
      <label><input type="checkbox" id="rec-upload-before-prune" ${ui.meter_upload_before_prune !== false ? "checked" : ""}> Upload a recording to the server before auto-delete reclaims it (on by default)</label>
      <p class="small muted" style="margin:2px 0 6px 14px">When the logs folder is over its size cap (above) and a recording is about to be deleted to make room, upload it first so its data — boss kills included — isn't lost. Only matters while auto-delete is on and a share server is set; it uploads at your upload visibility (Log server, public unless you change it), like the stop/quit auto-upload.</p>
      <label><input type="checkbox" id="rec-autostart" ${ui.meter_autostart !== false ? "checked" : ""}> Start the meter automatically when the app launches (on by default — it runs in the background and the overlay shows data without pressing Start)</label>
      <label><input type="checkbox" id="rec-server-name" ${ui.meter_show_server_name === true ? "checked" : ""}> Show each player's server (world) name next to their name on the live meter <span class="muted">(off by default; needs the region/world list — use Retry region detection if it hasn't resolved)</span></label>
      <label><input type="checkbox" id="rec-autoupload" ${ui.meter_auto_upload !== false ? "checked" : ""}> Upload every recording of this session that is not on the configured server yet when the meter stops (from the app, the overlay or its hotkey) or the app quits (on by default)</label>
      <label><input type="checkbox" id="rec-catchup" ${ui.meter_catch_up_uploads !== false ? "checked" : ""}> Catch up at the next launch: upload recordings from the last 7 days that are still not on the server (needs the option above; on by default)</label>
      <label><input type="checkbox" id="rec-perfight" ${ui.meter_upload_per_fight !== false ? "checked" : ""}> Upload the recording each time a boss fight ends, so its kill, standings and timers reach the community during play (needs automatic uploads; on by default)</label>
      <p class="small muted" style="margin:2px 0 6px 14px">Sends the current recording once a boss, mini-boss, field or world boss has died and the fight has paused, at most every 30 seconds; the share server updates the same log in place, so the upload at Stop and these are one log, never duplicates.</p>
      <label style="margin-top:4px"><input type="checkbox" id="rec-report-boss" ${ui.meter_report_boss_kills !== false ? "checked" : ""}> Report open-world boss kills to the community world-boss feed <span class="muted">(anonymous per-install; shown only once two installs agree; on by default)</span></label>
      <p class="small muted" style="margin:2px 0 6px 14px">Anonymous and opt-in: sends only the boss, server and kill time (no account, character, log or IP). Two different installs must report the same kill before it shows, so the public world-boss availability feed stays corroborated.</p>
      <label style="margin-top:4px"><input type="checkbox" id="rec-report-enemy-hp" ${ui.meter_report_enemy_hp !== false ? "checked" : ""}> Share enemy HP data to improve everyone's HP bars (on by default)</label>
      <p class="small muted" style="margin:2px 0 6px 14px">Anonymous and opt-out: when an enemy dies, sends only how much damage it took to die, its NPC id and the game build (no account, character, log or IP). The server pools these across players — including party kills — to learn each enemy's real HP so the meter can show an accurate HP %. The more players share, the better the bars for all.</p>
      <label style="margin-top:4px"><input type="checkbox" id="rec-report-diagnostics" ${ui.meter_report_diagnostics !== false ? "checked" : ""}> Share anonymous diagnostics to improve the catalog and catch meter bugs (on by default)</label>
      <p class="small muted" style="margin:2px 0 6px 14px">Anonymous and opt-out: after a fight, sends only the NPC/skill ids the app couldn't name yet (so new content gets added to the catalog) and a few capture-health counters like rollover and dropped-packet totals (so meter bugs such as a mid-fight reset show up across players). No account, character, combat log or IP — just ids, small numbers, the game build and region.</p>
      <label style="margin-top:4px"><input type="checkbox" id="rec-dummy" ${ui.meter_show_dummy_parse !== false ? "checked" : ""}> Show a training-dummy parse readout when hitting a dummy</label>
      <div class="row"><label>Training-dummy parse window <input type="number" id="rec-dummy-secs" min="5" max="3600" value="${Number(ui.meter_dummy_record_seconds) || 60}" style="width:80px"> s</label></div>
      <p class="small muted">Applies to the live meter and overlay. A cleared battle's details stay available in the segment list until replaced.</p></div></div>
    <div class="setrow" data-g="backup"><div class="lbl">Customization profiles</div><div><div class="row"><select id="cust-profile" aria-label="Customization profile" style="min-width:229px">${customProfileOptions()}</select><button class="btn small" id="cust-apply">Apply</button><button class="btn small" id="cust-save">Save current as…</button><button class="btn small" id="cust-delete">Delete</button><button class="btn small" id="cust-copy">Copy share code</button><button class="btn small" id="cust-import">Paste a shared code…</button><span id="cust-msg" class="small muted" role="status"></span></div>
      ${customProfileGallery()}
      <p class="small muted">A profile bundles your whole look — <strong>theme</strong>, <strong>accent colour</strong>, <strong>class colours</strong>, the <strong>overlay look</strong> and your <strong>overlay background image</strong> — into one named set you can switch between in a click. Stored in this browser, on your machine. Any profile that carries a background shows as a square above; click it to apply. The bundled image stays on your machine — it is never uploaded and is left out of the <strong>Copy share code</strong> (which carries only your colours and settings), and it is kept at a reduced size so it fits.</p></div></div>
    <div class="setrow" data-g="backup"><div class="lbl">Settings backup</div><div><div class="row"><button class="btn small" id="settings-export">Export settings</button><label class="btn small" for="settings-import-file">Import settings</label><input type="file" id="settings-import-file" accept="application/json,.json" style="display:none"><span id="settings-backup-msg" class="small muted" role="status"></span></div><p class="small muted">Save the overlay and app settings to a file you can restore or share, then import it back. What belongs to this computer stays out of it: the Pet Tracker folder, the overlay's background image and event sound, raw traffic recording, and the Timers region and group.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Overlay colors &amp; fonts</div><div><div class="row"><label>Rate text <input type="color" id="ov-rate-color" value="${esc(overlayText("rate"))}"></label><label>Total / share text <input type="color" id="ov-total-color" value="${esc(overlayText("total"))}"></label><label>Player name <input type="color" id="ov-name-color" value="${esc(overlayText("name"))}"></label><label>Header <input type="color" id="ov-header-color" value="${esc(overlayText("header"))}"></label><label>Target text <input type="color" id="ov-target-color" value="${esc(overlayText("target"))}"></label><label>Enemy-HP text <input type="color" id="ov-hptext-color" value="${esc(overlayText("hp"))}"></label><label>TTK text <input type="color" id="ov-ttktext-color" value="${esc(overlayText("ttk"))}"></label><label>Labels <input type="color" id="ov-label-color" value="${esc(overlayText("label"))}"></label><label>Also-targets +N <input type="color" id="ov-also-color" value="${esc(overlayText("also"))}"></label><label>Ping line <input type="color" id="ov-ping-color" value="${esc(overlayText("ping"))}"></label><label>Identity line <input type="color" id="ov-identity-color" value="${esc(overlayText("identity"))}"></label><button class="btn small" id="ov-color-reset">Reset number colors</button><span class="small muted" id="ov-color-msg" role="status"></span></div>
      <div class="row"><label>Font <select id="ov-font-fam">${["", "Segoe UI", "Arial", "Verdana", "Georgia", "Trebuchet MS", "Consolas", "Tahoma"].map((f) => `<option value="${esc(f)}" ${f === (ui.overlay_font_family || "") ? "selected" : ""}>${f || "Default"}</option>`).join("")}</select></label><label>Size <input type="number" id="ov-font-scale" min="80" max="160" value="${Number(ui.overlay_font_scale) || 100}" style="width:74px"> %</label><label>Weight <select id="ov-font-weight">${[400, 500, 600, 700, 800].map((w) => `<option value="${w}" ${w === (Number(ui.overlay_font_weight) || 600) ? "selected" : ""}>${w}</option>`).join("")}</select></label><label><input type="checkbox" id="ov-glow" ${ui.overlay_glow === true ? "checked" : ""}> Text glow</label><label>Glow color <input type="color" id="ov-glow-color" value="${esc(/^#[0-9a-f]{6}$/i.test(ui.overlay_glow_color || "") ? ui.overlay_glow_color : "#e8cf8e")}"></label><label>Enemy HP bar color <input type="color" id="ov-hp-color" value="${esc(/^#[0-9a-f]{6}$/i.test(ui.overlay_hp_color || "") ? ui.overlay_hp_color : "#e4808f")}"></label><label>TTK bar color <input type="color" id="ov-ttk-color" value="${esc(/^#[0-9a-f]{6}$/i.test(ui.overlay_ttk_color || "") ? ui.overlay_ttk_color : "#86a9c6")}"></label><label title="A crisp outline around the text for legibility over busy backgrounds (separate from the soft glow)"><input type="checkbox" id="ov-outline" ${ui.overlay_text_outline === true ? "checked" : ""}> Text outline</label><label>Outline color <input type="color" id="ov-outline-color" value="${esc(/^#[0-9a-f]{6}$/i.test(ui.overlay_outline_color || "") ? ui.overlay_outline_color : "#000000")}"></label><label title="Slowly cycle the header and player names through the colour spectrum (respects your reduced-motion setting)"><input type="checkbox" id="ov-cycle" ${ui.overlay_color_cycle === true ? "checked" : ""}> Colour-cycle</label><span class="small muted" id="ov-font-msg" role="status"></span></div>
      <p class="small muted">Number colors apply to DPS, HPS and D.Taken. Changes reach an open overlay within 10 seconds.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Overlay text effects &amp; per-element fonts</div><div>
      <div class="row"><label title="A soft luminous ring around the overlay text, layered on top of any glow"><input type="checkbox" id="ov-halo" ${ui.overlay_text_halo === true ? "checked" : ""}> Halo</label><label>Halo color <input type="color" id="ov-halo-color" value="${esc(/^#[0-9a-f]{6}$/i.test(ui.overlay_halo_color || "") ? ui.overlay_halo_color : "#e8cf8e")}"></label><label title="A subtle sheen sweeping across the headline text, like reflective material catching light (respects your reduced-motion setting)"><input type="checkbox" id="ov-retro" ${ui.overlay_text_retro === true ? "checked" : ""}> Retroreflection</label></div>
      <div class="row"><label>Element <select id="ov-fe-el">${[
        ["rate", "Rate (DPS/HPS)"],
        ["total", "Total · percent"],
        ["name", "Player name"],
        ["header", "Header"],
        ["target", "Target line"],
        ["hp", "Target HP"],
        ["ttk", "Target TTK"],
        ["label", "Target label"],
        ["also", "Also-targets +N"],
        ["ping", "Ping line"],
        ["identity", "Identity line"],
      ]
        .map(([k, l]) => `<option value="${k}">${l}</option>`)
        .join(
          "",
        )}</select></label><label>Font <select id="ov-fe-fam">${["", "Segoe UI", "Arial", "Verdana", "Georgia", "Trebuchet MS", "Consolas", "Tahoma"].map((f) => `<option value="${esc(f)}">${f || "Inherit"}</option>`).join("")}</select></label><label>Size <input type="number" id="ov-fe-size" min="80" max="160" placeholder="auto" style="width:74px"> %</label><label>Weight <select id="ov-fe-weight"><option value="">Auto</option>${[400, 500, 600, 700, 800].map((w) => `<option value="${w}">${w}</option>`).join("")}</select></label><button class="btn small" id="ov-fe-clear">Reset element</button><span class="small muted" id="ov-fe-msg" role="status"></span></div>
      <p class="small muted">Each element's font falls back to the overlay font above when left on Inherit/Auto. Changes reach an open overlay within 10 seconds.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Overlay background</div><div><div class="row"><label class="btn small" for="ov-bg-file">Choose image</label><input type="file" id="ov-bg-file" accept="image/png,image/jpeg" style="display:none"><button class="btn small" id="ov-bg-clear">Remove</button><span id="ov-bg-msg" class="small muted" role="status">${ui.overlay_bg_set ? "An image is set." : "No image set."}</span></div>
      <div class="row"><label>Visibility <input type="number" id="ov-bg-opacity" min="0" max="100" value="${ui.overlay_bg_opacity ?? 100}" style="width:74px"> %</label><label>Zoom <input type="number" id="ov-bg-zoom" min="50" max="200" value="${Number(ui.overlay_bg_zoom) || 100}" style="width:74px"> %</label><label>Darken <input type="number" id="ov-bg-darken" min="0" max="100" value="${ui.overlay_bg_darken ?? 20}" style="width:74px"> %</label></div>
      <div class="row"><label>Auto-contrast text to image <select id="ov-bg-autocontrast">${[
        ["off", "Off"],
        ["blend", "Dynamic (per-pixel blend)"],
        ["luminance", "By brightness (computed)"],
      ]
        .map(
          ([v, l]) =>
            `<option value="${v}" ${v === (ui.overlay_text_autocontrast || "off") ? "selected" : ""}>${l}</option>`,
        )
        .join("")}</select></label></div>
      <p class="small muted">A PNG or JPEG (8 MB max) shown behind the overlay card. Set Visibility above 0 to show it. The image is stored locally, not in the settings backup. <strong>Auto-contrast</strong> keeps the text legible against that image: <em>Dynamic</em> paints each glyph as the inverse of whatever is behind it (a <code>mix-blend-mode</code>); <em>By brightness</em> picks one light or dark colour from the image's relative luminance. It only reads the overlay's own image — not the game behind a transparent window — so set a background image to use it.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Overlay look presets</div><div><div class="row"><select id="ov-preset" aria-label="Overlay look preset" style="min-width:229px">${overlayPresetOptions(ui)}</select><button class="btn small" id="ov-preset-apply">Apply</button><button class="btn small" id="ov-preset-save">Save current look as…</button><button class="btn small" id="ov-preset-delete">Delete</button><button class="btn small" id="ov-preset-copy">Copy share code</button><button class="btn small" id="ov-preset-import">Paste a shared code…</button><span id="ov-preset-msg" class="small muted" role="status"></span></div>
      <p class="small muted">A preset bundles the overlay's colors, fonts, glow, enemy-HP color, background sliders, name display and per-class bar colors (not the background image). Saved presets ride the settings backup file. <strong>Copy share code</strong> turns the selected preset into a short code to send a friend; <strong>Paste a shared code</strong> saves one they sent you.</p></div></div>
    <div class="setrow" data-g="overlay"><div class="lbl">Hotkeys <span class="muted small">(Windows)</span></div><div>
      <div id="hotkey-rows"></div>
      <div class="row" style="margin-top:6px"><button class="btn small" id="hotkeys-save">Save hotkeys</button><span id="hotkeys-msg" class="small muted" role="status"></span></div>
      <p class="small muted">Global shortcuts that work even while the game is focused (Windows only). Click a field and press the key combo (e.g. Ctrl+Shift+M), then <strong>Save hotkeys</strong>; <strong>Clear</strong> unbinds. Changes take effect within a couple of seconds. Leave all blank for no hotkeys (the default). Ride the settings backup.</p></div></div>
    <div class="setrow" data-g="appearance"><div class="lbl">Combat class colors</div><div id="class-colors"></div></div><div class="setrow" data-g="system"><div class="lbl">Game database</div><div>${n0(s.db.items)} items · last update ${s.db.last_sync ? whenAt(s.db.last_sync.at * 1000) : "never"} <button class="btn small" id="sync">Check now</button> <button class="btn small" id="asset-reindex">Re-index cached icons</button> <button class="btn small" id="asset-report">Export image coverage</button> <button class="btn small" id="retry-images">Retry images</button><span id="asset-msg" class="small muted" role="status" aria-live="polite"></span></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Storage maintenance</div><div><div class="row"><button class="btn small" id="storage-inspect">Inspect cache / updates</button><button class="btn small" id="storage-cache">Clean old disposable cache</button><button class="btn small" id="storage-updates">Clean old update files</button></div><p class="small muted">Web/comparison cache: 7 days; images: 30 days. Updates retain two packages, helpers for 7 days, and at least five logs / 30 days. Active or uninspectable helpers are preserved. Cache images may need downloading again.</p><p id="storage-message" role="status"></p><div id="maintenance-details"></div></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Updates</div><div><label><input type="checkbox" id="autoupd" ${ui.auto_update !== false ? "checked" : ""}> check and prompt for updates on launch</label></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Version</div><div>Aion 2 Calc ${esc(s.version)} ${s.update ? `· version ${esc(s.update.version)} available <button class="btn small" id="instupd">Install now</button> <a href="${esc(s.update.url)}" target="_blank" rel="noopener">release notes</a>` : `<span class="muted" id="updstate">${updateStateText(s.update_state)}</span> <button class="btn small" id="chkupd">Check now</button>`} <span id="updmsg" class="small muted"></span></div></div>
    <div class="setrow" data-g="system"><div class="lbl">Community</div><div><a href="${DISCORD}" target="_blank" rel="noopener">Join the aion2calc Discord</a> — questions, builds and help</div></div>
    <div class="setrow" data-g="system"><div class="lbl">Stop the app</div><div><button class="btn small" id="quit2">Quit aion2calc</button></div></div>
    <div class="setrow" data-g="system" style="border-top:1px solid var(--line);margin-top:8px;padding-top:10px"><div class="lbl">Author</div><div class="muted">Spirited - Zikel : Asmodian&nbsp;&nbsp;|&nbsp;&nbsp;Legion: WhaleWatch</div></div>`,
  );
  // Settings subtabs: show one group of rows at a time (all stay in the DOM, so
  // every control's wiring below still binds). The chosen tab is remembered.
  (function () {
    const tabs = $$("[data-settab]"),
      rows = $$(".setrow[data-g]");
    let cur = "appearance";
    try {
      cur = localStorage.getItem("a2-settab") || "appearance";
    } catch (_) {}
    if (!tabs.some((b) => b.dataset.settab === cur)) cur = "appearance";
    const show = (g) => {
      try {
        localStorage.setItem("a2-settab", g);
      } catch (_) {}
      tabs.forEach((b) => {
        b.classList.toggle("on", b.dataset.settab === g);
        b.setAttribute("aria-pressed", String(b.dataset.settab === g));
      });
      rows.forEach((r) => {
        r.hidden = r.dataset.g !== g;
      });
    };
    tabs.forEach((b) => (b.onclick = () => show(b.dataset.settab)));
    show(cur);
  })();
  $("#storage-inspect").onclick = showMaintenance;
  for (const [id, action] of [
    ["storage-cache", "caches"],
    ["storage-updates", "updates"],
  ])
    $("#" + id).onclick = async () => {
      const b = $("#" + id),
        message = $("#storage-message");
      b.disabled = true;
      message.textContent = "Cleaning eligible files…";
      try {
        const r = await api("/api/maintenance", { action });
        if (message.isConnected)
          message.textContent = `Removed ${r.deleted} files; ${r.skipped || 0} changed, active, locked or uninspectable files preserved.`;
        await showMaintenance();
      } catch (e) {
        if (message.isConnected) message.textContent = e.message;
      } finally {
        if (b.isConnected) b.disabled = false;
      }
    };
  if (ui.combat_colors) localStorage.setItem("a2-combat-colors", JSON.stringify(ui.combat_colors));
  A2CombatReview.settings($("#class-colors"), (pref) => api("/api/ui", { combat_colors: pref }));
  $("#ov-preset").onchange = () => {
    const sel = $("#ov-preset").value,
      msg = $("#ov-preset-msg");
    if (sel.slice(0, 1) === "b") {
      msg.textContent = BUNDLED_PRESET_DESC[sel.slice(3)] || "";
    } else {
      msg.textContent = "Your saved preset.";
    }
  };
  $("#ov-preset-apply").onclick = async () => {
    const sel = $("#ov-preset").value;
    if (!sel) return;
    const kind = sel.slice(0, 1),
      name = sel.slice(3);
    const settings =
      kind === "b"
        ? BUNDLED_PRESETS[name]
        : (Array.isArray(ui.overlay_presets) ? ui.overlay_presets : []).find((p) => p.name === name)?.settings;
    const msg = $("#ov-preset-msg");
    if (!settings) {
      msg.textContent = "Preset not found.";
      return;
    }
    msg.textContent = "Applying…";
    try {
      await api("/api/ui", settings);
      toast("Preset applied");
      pageSettings();
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#ov-preset-save").onclick = async () => {
    const name = (prompt("Name this preset:") || "").trim();
    if (!name) return;
    const msg = $("#ov-preset-msg");
    if (name.length > 40) {
      msg.textContent = "Name must be 40 characters or fewer.";
      return;
    }
    msg.textContent = "Saving…";
    try {
      const fresh = await api("/api/ui");
      const settings = {};
      for (const k of OVERLAY_VISUAL_KEYS) if (fresh[k] !== undefined) settings[k] = fresh[k];
      const list = (Array.isArray(fresh.overlay_presets) ? fresh.overlay_presets : []).filter(
        (p) => p.name.toLowerCase() !== name.toLowerCase(),
      );
      list.push({ name, settings });
      await api("/api/ui", { overlay_presets: list });
      toast("Preset saved");
      pageSettings();
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#ov-preset-delete").onclick = async () => {
    const sel = $("#ov-preset").value,
      msg = $("#ov-preset-msg");
    if (!sel || sel.slice(0, 1) !== "s") {
      msg.textContent = "Pick a saved preset to delete.";
      return;
    }
    const name = sel.slice(3);
    msg.textContent = "Deleting…";
    try {
      const fresh = await api("/api/ui");
      const list = (Array.isArray(fresh.overlay_presets) ? fresh.overlay_presets : []).filter((p) => p.name !== name);
      await api("/api/ui", { overlay_presets: list });
      toast("Preset deleted");
      pageSettings();
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  const PRESET_CODE_PREFIX = "A2P1:";
  const encodePreset = (name, settings) =>
    PRESET_CODE_PREFIX + btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify({ name, settings }))));
  const decodePreset = (code) => {
    const raw = String(code || "").trim(),
      b64 = raw.startsWith(PRESET_CODE_PREFIX) ? raw.slice(PRESET_CODE_PREFIX.length) : raw;
    const obj = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))));
    if (
      !obj ||
      typeof obj !== "object" ||
      typeof obj.name !== "string" ||
      !obj.settings ||
      typeof obj.settings !== "object"
    )
      throw Error("not a preset");
    const settings = {};
    for (const k of OVERLAY_VISUAL_KEYS) if (obj.settings[k] !== undefined) settings[k] = obj.settings[k];
    if (!Object.keys(settings).length) throw Error("no recognised look settings");
    return { name: String(obj.name).slice(0, 40) || "Shared preset", settings };
  };
  $("#ov-preset-copy").onclick = async () => {
    const sel = $("#ov-preset").value,
      msg = $("#ov-preset-msg");
    let name, settings;
    if (sel) {
      const kind = sel.slice(0, 1);
      name = sel.slice(3);
      settings =
        kind === "b"
          ? BUNDLED_PRESETS[name]
          : (Array.isArray(ui.overlay_presets) ? ui.overlay_presets : []).find((p) => p.name === name)?.settings;
    }
    if (!settings) {
      try {
        const fresh = await api("/api/ui");
        settings = {};
        for (const k of OVERLAY_VISUAL_KEYS) if (fresh[k] !== undefined) settings[k] = fresh[k];
        name = "My overlay look";
      } catch (e) {
        msg.textContent = e.message;
        return;
      }
    }
    const code = encodePreset(name, settings);
    try {
      await navigator.clipboard.writeText(code);
      msg.textContent = "Share code copied — send it to a friend.";
    } catch (_) {
      prompt("Copy this preset share code:", code);
      msg.textContent = "Share code ready.";
    }
  };
  $("#ov-preset-import").onclick = async () => {
    const code = (prompt("Paste a preset share code:") || "").trim();
    if (!code) return;
    const msg = $("#ov-preset-msg");
    let preset;
    try {
      preset = decodePreset(code);
    } catch (_) {
      msg.textContent = "That is not a valid preset share code.";
      return;
    }
    const name = (prompt("Save the shared preset as:", preset.name) || "").trim();
    if (!name) return;
    if (name.length > 40) {
      msg.textContent = "Name must be 40 characters or fewer.";
      return;
    }
    msg.textContent = "Saving…";
    try {
      const fresh = await api("/api/ui");
      const list = (Array.isArray(fresh.overlay_presets) ? fresh.overlay_presets : []).filter(
        (p) => p.name.toLowerCase() !== name.toLowerCase(),
      );
      list.push({ name, settings: preset.settings });
      await api("/api/ui", { overlay_presets: list });
      toast("Shared preset saved");
      pageSettings();
    } catch (e) {
      msg.textContent = "Could not save: " + e.message;
    }
  };
  // Customization profiles (theme + accent + class colours + overlay look).
  $("#cust-save").onclick = async () => {
    const name = (prompt("Name this customization profile:") || "").trim();
    if (!name) return;
    const msg = $("#cust-msg");
    if (name.length > 40) {
      msg.textContent = "Name must be 40 characters or fewer.";
      return;
    }
    msg.textContent = "Saving…";
    try {
      const fresh = await api("/api/ui");
      const look = {};
      for (const k of OVERLAY_VISUAL_KEYS) if (fresh[k] !== undefined) look[k] = fresh[k];
      if (fresh.combat_colors !== undefined) look.combat_colors = fresh.combat_colors;
      // Bundle the overlay background with the profile (local only — see help text).
      // A string (possibly empty) marks a new-format profile: '' means "no background".
      const bg = fresh.overlay_bg_set ? await captureOverlayBackground() : "";
      const list = getCustomProfiles().filter((p) => p.name.toLowerCase() !== name.toLowerCase());
      let entry;
      try {
        entry = { name, theme: getTheme(), accent: getAccent(), ui: look, bg };
        list.push(entry);
        saveCustomProfiles(list);
      } catch (_) {
        /* localStorage full: keep the profile but drop the heavy image */ entry.bg = "";
        saveCustomProfiles(list);
      }
      // If the image didn't survive the save (quota), say so rather than imply it did.
      const kept = getCustomProfiles().find((p) => p.name.toLowerCase() === name.toLowerCase());
      toast(bg && kept && kept.bg ? "Profile saved with its background" : "Profile saved");
      if (bg && (!kept || !kept.bg))
        msg.textContent = "Saved, but the background was too large to bundle in this browser.";
      pageSettings();
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  // Apply a whole profile: theme, accent, class colours, overlay look, and the
  // bundled background when the profile carries one (new-format profiles store a
  // bg string — '' clears the current image; an absent bg leaves it untouched).
  const applyCustomProfile = async (prof) => {
    setTheme(prof.theme || "system");
    setAccent(prof.accent || "gold");
    const look = prof.ui || {};
    if (look.combat_colors !== undefined) {
      try {
        localStorage.setItem("a2-combat-colors", JSON.stringify(look.combat_colors));
      } catch (_) {}
    }
    if (Object.keys(look).length) await api("/api/ui", look);
    if (typeof prof.bg === "string")
      await api("/api/overlay/background", prof.bg ? { data: prof.bg } : { clear: true });
  };
  $("#cust-apply").onclick = async () => {
    const sel = $("#cust-profile").value,
      msg = $("#cust-msg");
    if (!sel) {
      msg.textContent = "Pick a profile to apply.";
      return;
    }
    const prof = getCustomProfiles().find((p) => p.name === sel);
    if (!prof) {
      msg.textContent = "Profile not found.";
      return;
    }
    msg.textContent = "Applying…";
    try {
      await applyCustomProfile(prof);
      toast("Profile applied");
      pageSettings();
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $$("[data-cust-tile]").forEach(
    (btn) =>
      (btn.onclick = async () => {
        const prof = getCustomProfiles().find((p) => p.name === btn.dataset.custTile);
        if (!prof) return;
        const msg = $("#cust-msg");
        msg.textContent = "Applying…";
        try {
          await applyCustomProfile(prof);
          toast("Profile applied");
          pageSettings();
        } catch (e) {
          msg.textContent = e.message;
        }
      }),
  );
  $("#cust-delete").onclick = () => {
    const sel = $("#cust-profile").value,
      msg = $("#cust-msg");
    if (!sel) {
      msg.textContent = "Pick a profile to delete.";
      return;
    }
    saveCustomProfiles(getCustomProfiles().filter((p) => p.name !== sel));
    toast("Profile deleted");
    pageSettings();
  };
  // Share a whole customization profile as a portable code (theme + accent + look).
  const PROFILE_CODE_PREFIX = "A2PROF1:";
  // Share codes carry colours and settings only — the bundled background image is
  // stripped so it stays on this machine (avoids the bloat/privacy of embedding it).
  const encodeProfile = (prof) => {
    const { bg, ...rest } = prof;
    return PROFILE_CODE_PREFIX + btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(rest))));
  };
  const decodeProfile = (code) => {
    const raw = String(code || "").trim(),
      b64 = raw.startsWith(PROFILE_CODE_PREFIX) ? raw.slice(PROFILE_CODE_PREFIX.length) : raw;
    const obj = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))));
    if (!obj || typeof obj !== "object") throw Error("not a profile");
    const theme = THEMES.includes(obj.theme) ? obj.theme : "system";
    const accent = ACCENTS.includes(obj.accent) ? obj.accent : "gold";
    const src = obj.ui && typeof obj.ui === "object" ? obj.ui : {};
    const ui = {};
    for (const k of OVERLAY_VISUAL_KEYS) if (src[k] !== undefined) ui[k] = src[k];
    if (src.combat_colors !== undefined) ui.combat_colors = src.combat_colors;
    return { name: String(obj.name || "").slice(0, 40) || "Shared profile", theme, accent, ui };
  };
  $("#cust-copy").onclick = async () => {
    const sel = $("#cust-profile").value,
      msg = $("#cust-msg");
    if (!sel) {
      msg.textContent = "Pick a profile to copy.";
      return;
    }
    const prof = getCustomProfiles().find((p) => p.name === sel);
    if (!prof) {
      msg.textContent = "Profile not found.";
      return;
    }
    const code = encodeProfile(prof);
    try {
      await navigator.clipboard.writeText(code);
      msg.textContent = "Share code copied — send it to a friend.";
    } catch (_) {
      prompt("Copy this profile share code:", code);
      msg.textContent = "Share code ready.";
    }
  };
  $("#cust-import").onclick = () => {
    const code = (prompt("Paste a profile share code:") || "").trim();
    if (!code) return;
    const msg = $("#cust-msg");
    let prof;
    try {
      prof = decodeProfile(code);
    } catch (_) {
      msg.textContent = "That is not a valid profile share code.";
      return;
    }
    const name = (prompt("Save the shared profile as:", prof.name) || "").trim();
    if (!name) return;
    if (name.length > 40) {
      msg.textContent = "Name must be 40 characters or fewer.";
      return;
    }
    const list = getCustomProfiles().filter((p) => p.name.toLowerCase() !== name.toLowerCase());
    list.push({ name, theme: prof.theme, accent: prof.accent, ui: prof.ui });
    saveCustomProfiles(list);
    toast("Shared profile saved");
    pageSettings();
  };
  const saveOverlayColors = async () => {
    const msg = $("#ov-color-msg");
    msg.textContent = "Saving…";
    try {
      await api("/api/ui", {
        overlay_text_colors: {
          rate: $("#ov-rate-color").value,
          total: $("#ov-total-color").value,
          name: $("#ov-name-color").value,
          header: $("#ov-header-color").value,
          target: $("#ov-target-color").value,
          hp: $("#ov-hptext-color").value,
          ttk: $("#ov-ttktext-color").value,
          label: $("#ov-label-color").value,
          also: $("#ov-also-color").value,
          ping: $("#ov-ping-color").value,
          identity: $("#ov-identity-color").value,
        },
      });
      msg.textContent = "Saved";
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  for (const id of [
    "ov-rate-color",
    "ov-total-color",
    "ov-name-color",
    "ov-header-color",
    "ov-target-color",
    "ov-hptext-color",
    "ov-ttktext-color",
    "ov-label-color",
    "ov-also-color",
    "ov-ping-color",
    "ov-identity-color",
  ])
    $("#" + id).onchange = saveOverlayColors;
  $("#ov-color-reset").onclick = () => {
    $("#ov-rate-color").value = OVERLAY_TEXT_DEFAULTS.rate;
    $("#ov-total-color").value = OVERLAY_TEXT_DEFAULTS.total;
    saveOverlayColors();
  };
  const saveFont = async (key, val) => {
    const msg = $("#ov-font-msg");
    msg.textContent = "Saving…";
    try {
      await api("/api/ui", { [key]: val });
      msg.textContent = "Saved";
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#ov-font-fam").onchange = () => saveFont("overlay_font_family", $("#ov-font-fam").value);
  $("#ov-font-weight").onchange = () => saveFont("overlay_font_weight", parseInt($("#ov-font-weight").value, 10));
  $("#ov-font-scale").onchange = () => {
    const n = parseInt($("#ov-font-scale").value, 10);
    if (n >= 80 && n <= 160) saveFont("overlay_font_scale", n);
    else $("#ov-font-msg").textContent = "Size must be 80–160%.";
  };
  $("#ov-glow").onchange = () => saveFont("overlay_glow", $("#ov-glow").checked);
  $("#ov-glow-color").onchange = () => saveFont("overlay_glow_color", $("#ov-glow-color").value);
  $("#ov-hp-color").onchange = () => saveFont("overlay_hp_color", $("#ov-hp-color").value);
  $("#ov-ttk-color").onchange = () => saveFont("overlay_ttk_color", $("#ov-ttk-color").value);
  $("#ov-outline").onchange = () => saveFont("overlay_text_outline", $("#ov-outline").checked);
  $("#ov-outline-color").onchange = () => saveFont("overlay_outline_color", $("#ov-outline-color").value);
  $("#ov-cycle").onchange = () => saveFont("overlay_color_cycle", $("#ov-cycle").checked);
  $("#ov-halo") && ($("#ov-halo").onchange = () => saveFont("overlay_text_halo", $("#ov-halo").checked));
  $("#ov-halo-color") &&
    ($("#ov-halo-color").onchange = () => saveFont("overlay_halo_color", $("#ov-halo-color").value));
  $("#ov-retro") && ($("#ov-retro").onchange = () => saveFont("overlay_text_retro", $("#ov-retro").checked));
  // Per-element font overrides edit one entry of the overlay_text_fonts map at a time.
  const overlayFonts = {
    ...(ui.overlay_text_fonts && typeof ui.overlay_text_fonts === "object" ? ui.overlay_text_fonts : {}),
  };
  const feEl = $("#ov-fe-el"),
    feFam = $("#ov-fe-fam"),
    feSize = $("#ov-fe-size"),
    feWeight = $("#ov-fe-weight"),
    feMsg = $("#ov-fe-msg");
  if (feEl) {
    const feLoad = () => {
      const e = overlayFonts[feEl.value] || {};
      feFam.value = e.family || "";
      feSize.value = Number.isFinite(e.scale) ? e.scale : "";
      feWeight.value = Number.isFinite(e.weight) ? String(e.weight) : "";
    };
    const feSave = async () => {
      const entry = {};
      if (feFam.value) entry.family = feFam.value;
      if (feSize.value !== "") {
        const s = parseInt(feSize.value, 10);
        if (!(s >= 80 && s <= 160)) {
          feMsg.textContent = "Size must be 80–160%.";
          return;
        }
        entry.scale = s;
      }
      if (feWeight.value !== "") entry.weight = parseInt(feWeight.value, 10);
      if (Object.keys(entry).length) overlayFonts[feEl.value] = entry;
      else delete overlayFonts[feEl.value];
      feMsg.textContent = "Saving…";
      try {
        await api("/api/ui", { overlay_text_fonts: overlayFonts });
        feMsg.textContent = "Saved";
      } catch (e) {
        feMsg.textContent = e.message;
      }
    };
    feEl.onchange = feLoad;
    feFam.onchange = feSave;
    feSize.onchange = feSave;
    feWeight.onchange = feSave;
    $("#ov-fe-clear").onclick = () => {
      delete overlayFonts[feEl.value];
      feLoad();
      feSave();
    };
    feLoad();
  }
  const saveBgNum = async (id, key, lo, hi) => {
    const n = parseInt($("#" + id).value, 10),
      msg = $("#ov-bg-msg");
    if (!(n >= lo && n <= hi)) {
      msg.textContent = `Enter ${lo}–${hi}.`;
      return;
    }
    try {
      await api("/api/ui", { [key]: n });
      msg.textContent = "Saved";
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#ov-bg-opacity").onchange = () => saveBgNum("ov-bg-opacity", "overlay_bg_opacity", 0, 100);
  $("#ov-bg-zoom").onchange = () => saveBgNum("ov-bg-zoom", "overlay_bg_zoom", 50, 200);
  $("#ov-bg-darken").onchange = () => saveBgNum("ov-bg-darken", "overlay_bg_darken", 0, 100);
  $("#ov-bg-clear").onclick = async () => {
    const msg = $("#ov-bg-msg");
    try {
      await api("/api/overlay/background", { clear: true });
      msg.textContent = "Removed.";
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#ov-bg-file").onchange = async (ev) => {
    const file = ev.target.files && ev.target.files[0],
      msg = $("#ov-bg-msg");
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      msg.textContent = "Image must be 8 MB or smaller.";
      ev.target.value = "";
      return;
    }
    msg.textContent = "Uploading…";
    try {
      const data = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = () => rej(Error("Could not read the file"));
        r.readAsDataURL(file);
      });
      await api("/api/overlay/background", { data });
      msg.textContent = "Image set. Set Visibility above 0 to show it.";
    } catch (e) {
      msg.textContent = e.message;
    } finally {
      ev.target.value = "";
    }
  };
  $$("[data-th]").forEach(
    (b) =>
      (b.onclick = () => {
        setTheme(b.dataset.th);
        pageSettings();
      }),
  );
  $$("[data-accent-btn]").forEach(
    (b) =>
      (b.onclick = () => {
        setAccent(b.dataset.accentBtn);
        pageSettings();
      }),
  );
  $("#ov-on-start").onchange = async () => {
    const control = $("#ov-on-start"),
      selected = control.checked;
    try {
      await api("/api/ui", { overlay_on_start: selected });
      toast("Saved");
    } catch (e) {
      control.checked = !selected;
      toast("Could not save overlay preference: " + e.message);
    }
  };
  $("#ov-open-on-app").onchange = () =>
    api("/api/ui", { overlay_open_on_app_start: $("#ov-open-on-app").checked }).then(() =>
      toast("Saved · applies on next launch"),
    );
  $("#ov-close-on-stop").onchange = () =>
    api("/api/ui", { overlay_close_on_stop: $("#ov-close-on-stop").checked }).then(() => toast("Saved"));
  // Global hotkeys: a capture field per bindable action. Keep the action list in
  // sync with aion2calc/app/hotkeys.py ACTIONS.
  (function () {
    const host = $("#hotkey-rows");
    if (!host) return;
    const ACTIONS = [
      ["toggle_overlay", "Show / hide the overlay"],
      ["toggle_meter", "Start / stop the meter"],
      ["clear_meter", "Clear the meter (battle reset)"],
      ["toggle_click_through", "Toggle click-through"],
      ["toggle_party_overlay", "Show / hide the Party-DPS overlay"],
      ["open_app", "Open the app window"],
      ["open_settings", "Open the Settings page"],
      ["toggle_events", "Show / hide overlay event notifications"],
      ["toggle_field_bosses", "Show / hide field-boss timers on the overlay"],
      ["toggle_combat_assist", "Show / hide combat assist (skill cooldowns, break gauge)"],
      ["toggle_cube_radar", "Turn the Hidden Cube radar on / off"],
      ["toggle_pet_tracker", "Show / hide the Pet Tracker overlay"],
      ["radar_learn_background", "Hidden Cube radar: learn the background (step 1)"],
      ["radar_learn_cube", "Hidden Cube radar: learn the cube's sound, facing it (step 2)"],
      ["radar_learn_cube_behind", "Hidden Cube radar: learn the cube's sound with it behind you (step 3)"],
      ["radar_learn_other", "Hidden Cube radar: learn a sound that is not a cube"],
      ["read_screen", "Read the game screen into the app (Genus Insight, Title window)"],
      ["screenshot_lock", "Screenshot lock (freeze the overlay)"],
      ["quit", "Exit Aion 2 Calc"],
    ];
    const saved = ui && ui.hotkeys && typeof ui.hotkeys === "object" ? ui.hotkeys : {};
    // The radar's learn steps are bound by default while the radar is on (hotkeys.py RADAR_DEFAULTS); a cleared
    // one is saved as "" so it stays cleared.
    const RADAR_KEYS = RADAR_STEPS;
    const shown = (a) => (a in RADAR_KEYS && !(a in saved) ? RADAR_KEYS[a] : saved[a] || "");
    host.innerHTML =
      ACTIONS.map(
        ([a, label]) =>
          `<div class="row" style="gap:8px;margin:2px 0"><span style="min-width:230px">${esc(label)}</span><input type="text" readonly class="hotkey-input" data-action="${esc(a)}" value="${esc(shown(a))}" placeholder="Click, then press keys" style="width:206px"><button type="button" class="btn small hotkey-clear" data-action="${esc(a)}">Clear</button></div>`,
      ).join("") +
      `<p class="small muted">The Hidden Cube radar's learn steps work only while the radar is on, and are Ctrl+1 to Ctrl+4 unless you change them. While they are bound, Windows gives those keys to this app instead of the game: clear them or pick other keys if the game uses them.</p>`;
    const NAMED = {
      " ": "Space",
      Escape: "Esc",
      ArrowUp: "Up",
      ArrowDown: "Down",
      ArrowLeft: "Left",
      ArrowRight: "Right",
      Enter: "Enter",
      Tab: "Tab",
      Backspace: "Backspace",
      Delete: "Delete",
      Insert: "Insert",
      Home: "Home",
      End: "End",
      PageUp: "PageUp",
      PageDown: "PageDown",
    };
    function comboFromEvent(e) {
      if (["Control", "Alt", "Shift", "Meta", "OS"].includes(e.key)) return null; // modifier alone
      const mods = [];
      if (e.ctrlKey) mods.push("Ctrl");
      if (e.altKey) mods.push("Alt");
      if (e.shiftKey) mods.push("Shift");
      if (e.metaKey) mods.push("Win");
      let k = e.key;
      if (NAMED[k]) k = NAMED[k];
      else if (/^F([1-9]|1[0-9]|2[0-4])$/i.test(k)) k = k.toUpperCase();
      else if (k.length === 1) k = k.toUpperCase();
      else if (e.code && e.code.indexOf("Digit") === 0) k = e.code.slice(5);
      else return null;
      return mods.concat([k]).join("+");
    }
    $$(".hotkey-input").forEach((inp) => {
      inp.onkeydown = (e) => {
        e.preventDefault();
        const c = comboFromEvent(e);
        if (c) inp.value = c;
      };
    });
    $$(".hotkey-clear").forEach(
      (btn) =>
        (btn.onclick = () => {
          const inp = host.querySelector('.hotkey-input[data-action="' + btn.dataset.action + '"]');
          if (inp) inp.value = "";
        }),
    );
    $("#hotkeys-save").onclick = async () => {
      const map = {};
      $$(".hotkey-input").forEach((inp) => {
        const v = inp.value.trim();
        if (v || inp.dataset.action in RADAR_KEYS) map[inp.dataset.action] = v;
      });
      const msg = $("#hotkeys-msg");
      const used = {},
        clash = Object.entries(map).find(
          ([a, v]) => v && (used[v.toLowerCase()] = (used[v.toLowerCase()] || 0) + 1) > 1,
        );
      if (clash) {
        msg.textContent = `${clash[1]} is bound to two actions; give each action its own keys.`;
        return;
      }
      msg.textContent = "Saving…";
      try {
        await api("/api/ui", { hotkeys: map });
        msg.textContent = "Saved";
      } catch (e) {
        msg.textContent = e.message;
      }
    };
  })();
  $("#ov-stream-copy").onclick = () => {
    const u = $("#ov-stream-url");
    u.select?.();
    copyText(u.value);
    const m = $("#ov-stream-msg");
    if (m) {
      m.textContent = "Copied — paste into an OBS Browser Source.";
      setTimeout(() => {
        if (m.isConnected) m.textContent = "";
      }, 2000);
    }
  };
  $("#appwin").onchange = () => api("/api/ui", { app_window: $("#appwin").checked }).then(() => toast("Saved"));
  $("#textscale").onchange = () => {
    const v = parseInt($("#textscale").value, 10) || 100;
    S.ui.app_text_scale = v;
    applyTextScale(S.ui);
    api("/api/ui", { app_text_scale: v }).then(() => toast("Saved"));
  };
  if (window.A2I18n) window.A2I18n.picker($("#setlang")); // choosing reloads the app in that language
  $("#defaultpage").onchange = () =>
    api("/api/ui", { app_default_page: $("#defaultpage").value }).then(() => {
      S.ui.app_default_page = $("#defaultpage").value;
      toast("Saved");
    });
  $("#char-auto-open").onchange = () =>
    api("/api/ui", { character_auto_open: $("#char-auto-open").checked }).then(() => toast("Saved"));
  $("#char-auto-refresh").onchange = () =>
    api("/api/ui", { character_auto_refresh: $("#char-auto-refresh").checked }).then(() => toast("Saved"));
  $("#community-heartbeat").onchange = () =>
    api("/api/ui", { community_heartbeat: $("#community-heartbeat").checked }).then(() => toast("Saved"));
  $("#contribute-character").onchange = () =>
    api("/api/ui", { community_contribute_character: $("#contribute-character").checked }).then(() => toast("Saved"));
  $("#trayclose").onchange = () =>
    api("/api/ui", { tray_on_close: $("#trayclose").checked }).then(() => toast("Saved · applies on next launch"));
  if ($("#pt-set-enabled")) {
    // Settings → Pet Tracker: the same settings the Pet Tracker page has, and Install when it is missing.
    let ptTimer = 0;
    const ptStatus = async () => {
      clearTimeout(ptTimer);
      const box = $("#pt-set-status");
      if (!box) return;
      try {
        const s = await (await fetch("/api/pettracker", { cache: "no-store" })).json();
        const setup = petSetupText(s.setup),
          busy = ["finding", "downloading", "installing", "started"].includes((s.setup || {}).status);
        box.innerHTML = !s.supported
          ? "Pet Tracker runs on Windows only."
          : s.installed
            ? `Installed${s.installed.version ? ": version " + esc(s.installed.version) : ""}, in ${esc(s.installed.folder)}. ${esc(window.A2Pets ? window.A2Pets.status(s).text : "")}${petUpdateNotice(s, "pt-set-update")}`
            : `Not installed on this computer. <button type="button" class="btn small" id="pt-set-install" ${busy && s.setup.status !== "started" ? "disabled" : ""}>Install Pet Tracker</button> ${esc(setup)}<br>It downloads Pet Tracker's official installer and starts it only once it matches the release its publisher signed.`;
        if (busy) ptTimer = setTimeout(ptStatus, 2000);
      } catch (e) {
        box.textContent = e.message;
      }
    };
    $("#pt-set-status").addEventListener("click", (e) => {
      if (e.target.closest("#pt-set-install"))
        window.A2Pets.control({ action: "install" })
          .then(ptStatus)
          .catch((err) => {
            $("#pt-set-status").textContent = err.message;
          });
      if (e.target.closest("#pt-set-update"))
        window.A2Pets.control({ action: "update" })
          .then((s) => {
            $("#pt-set-note").textContent = s.message || "";
            ptStatus();
          })
          .catch((err) => {
            $("#pt-set-note").textContent = err.message;
          });
    });
    $("#pt-set-enabled").onchange = () =>
      api("/api/ui", { pettracker_enabled: $("#pt-set-enabled").checked }).then(() => {
        toast("Saved");
        setTimeout(ptStatus, 800);
      });
    $("#pt-set-overlay").onchange = () =>
      api("/api/ui", { pettracker_overlay: $("#pt-set-overlay").checked }).then(() => toast("Saved"));
    $("#pt-set-style").onchange = () =>
      api("/api/ui", { pettracker_overlay_style: $("#pt-set-style").value }).then(() => toast("Saved"));
    $("#pt-set-path-save").onclick = () =>
      api("/api/ui", { pettracker_path: $("#pt-set-path").value.trim() })
        .then(() => {
          $("#pt-set-msg").textContent = "Saved";
          ptStatus();
        })
        .catch((e) => {
          $("#pt-set-msg").textContent = e.message;
        });
    ptStatus();
  }
  $("#ov-contribution").onchange = () =>
    api("/api/ui", { overlay_show_contribution: $("#ov-contribution").checked }).then(() => toast("Saved"));
  $("#ov-target").onchange = () =>
    api("/api/ui", { overlay_show_target: $("#ov-target").checked }).then(() => toast("Saved"));
  $("#ov-deaths").onchange = () =>
    api("/api/ui", { overlay_show_deaths: $("#ov-deaths").checked }).then(() => toast("Saved"));
  $("#ov-enemy-hp").onchange = () =>
    api("/api/ui", { overlay_show_enemy_hp: $("#ov-enemy-hp").checked }).then(() => toast("Saved"));
  $("#ov-plan-autoplay").onchange = () =>
    api("/api/ui", { overlay_plan_autoplay: $("#ov-plan-autoplay").checked }).then(() => toast("Saved"));
  $("#ov-ttk").onchange = () => api("/api/ui", { overlay_show_ttk: $("#ov-ttk").checked }).then(() => toast("Saved"));
  $("#ov-break-gauge").onchange = () =>
    api("/api/ui", { overlay_show_break_gauge: $("#ov-break-gauge").checked }).then(() => toast("Saved"));
  $("#ov-cooldowns").onchange = () =>
    api("/api/ui", { overlay_show_cooldowns: $("#ov-cooldowns").checked }).then(() => toast("Saved"));
  $("#ov-cd-min").onchange = () =>
    api("/api/ui", {
      overlay_cooldowns_min_s: Math.max(1, Math.min(120, parseInt($("#ov-cd-min").value, 10) || 3)),
    }).then(() => toast("Saved"));
  $("#ov-cd-max").onchange = () =>
    api("/api/ui", { overlay_cooldowns_max: Math.max(1, Math.min(16, parseInt($("#ov-cd-max").value, 10) || 8)) }).then(
      () => toast("Saved"),
    );
  $("#ov-cd-pos").onchange = () =>
    api("/api/ui", { overlay_cooldowns_position: $("#ov-cd-pos").value }).then(() => toast("Saved"));
  $("#ov-cp").onchange = () =>
    api("/api/ui", { overlay_show_combat_power: $("#ov-cp").checked }).then(() => toast("Saved"));
  $("#ov-odyle").onchange = () =>
    api("/api/ui", { overlay_show_odyle: $("#ov-odyle").checked }).then(() => toast("Saved"));
  $("#ov-shugo").onchange = () =>
    api("/api/ui", { overlay_show_shugo_keys: $("#ov-shugo").checked }).then(() => toast("Saved"));
  $("#ov-nightmare").onchange = () =>
    api("/api/ui", { overlay_show_nightmare_tickets: $("#ov-nightmare").checked }).then(() => toast("Saved"));
  $("#ov-community-rank") &&
    ($("#ov-community-rank").onchange = () =>
      api("/api/ui", { overlay_show_community_rank: $("#ov-community-rank").checked }).then(() => toast("Saved")));
  $("#ov-live-rank") &&
    ($("#ov-live-rank").onchange = () =>
      api("/api/ui", { overlay_live_community_rank: $("#ov-live-rank").checked }).then(() => toast("Saved")));
  $("#ov-events") &&
    ($("#ov-events").onchange = () =>
      api("/api/ui", { overlay_show_events: $("#ov-events").checked }).then(() => toast("Saved")));
  $("#ov-field-bosses") &&
    ($("#ov-field-bosses").onchange = () =>
      api("/api/ui", { overlay_show_field_bosses: $("#ov-field-bosses").checked }).then(() => toast("Saved")));
  const rtssStatus = async () => {
    const el = $("#rtss-status");
    if (!el) return;
    try {
      const s = await apiState("/api/rtss");
      el.textContent = !s.supported
        ? "RTSS output is available on Windows only."
        : !s.enabled
          ? "Off."
          : s.connected
            ? `Drawing in RTSS OSD slot ${s.slot} (shared memory v${s.version}, ${s.updates} updates).`
            : s.error || "Waiting for RTSS…";
    } catch (_) {
      el.textContent = "RTSS status unavailable.";
    }
  };
  if ($("#radar-enabled")) {
    const RADAR_NEAR = [
      [0.8, "right here"],
      [0.5, "close"],
      [0.25, "nearby"],
      [0, "far"],
    ];
    const near = (r) => (RADAR_NEAR.find(([p]) => (r.proximity || 0) >= p) || RADAR_NEAR[3])[1];
    const what = (l) =>
      l.kind === "background"
        ? "the background"
        : l.kind === "other"
          ? "a sound that is not a cube"
          : l.facing === "behind"
            ? "the cube's sound behind you"
            : "the cube's sound";
    const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
    const LAYOUTS = { 4: "quad", 6: "5.1", 8: "7.1" };
    const learnedText = (r) => {
      const m = r.model || {};
      if (!r.ready)
        return m.backgrounds
          ? `${plural(m.backgrounds, "background sample")} learned: now learn the cube's sound (step 2).`
          : "Nothing learned yet: step 1, then step 2.";
      const bits = [
        plural(m.cubes, "cube sample") + (m.behind ? ` (${m.ahead} facing it, ${m.behind} behind you)` : ""),
        m.backgrounds ? plural(m.backgrounds, "background sample") : "no background (step 1 improves it)",
      ];
      if (m.others) bits.push(plural(m.others, "sound that is not a cube", "sounds that are not a cube"));
      const facing =
        {
          learned: "It tells ahead from behind.",
          alike:
            "Ahead and behind sound alike to it: turn on the game's 3D audio, then learn both again a few steps from the cube.",
          need_ahead: "Learn it facing the cube too (step 2) to tell ahead from behind.",
          need_more: "Too little of the jingle was heard to tell ahead from behind: learn both again a little closer.",
        }[m.front_back] || (r.channels >= 4 ? "" : "Learn it behind you too (step 3) to tell ahead from behind.");
      return `Learned ${bits.join(", ")}${m.notes ? ", with the jingle's notes" : ""}. ${facing}`.trim();
    };
    const sampleRow = (s) => {
      const bits = [
        s.kind === "cube"
          ? s.facing === "behind"
            ? "Cube, behind you"
            : "Cube, facing it"
          : s.kind === "other"
            ? "Not a cube"
            : "Background",
      ];
      if (s.kind === "cube" && s.level_db != null)
        bits.push(s.level_db >= -1 ? "the loudest" : `${-s.level_db} dB below the loudest`);
      if (s.kind !== "background" && s.notes) bits.push("with its notes");
      if (s.alike) bits.push("sounds the same as the cube, so it is not used");
      if (s.at) bits.push(s.at.replace("T", " "));
      return `<li>${esc(bits.join(" · "))} <button class="btn small radar-forget" type="button" data-id="${esc(s.id)}" aria-label="Forget this sample">Forget</button></li>`;
    };
    let shownSamples = null;
    const radarStatus = async () => {
      const el = $("#radar-status");
      if (!el) return;
      let r;
      try {
        r = await apiState("/api/radar");
      } catch (e) {
        el.textContent = "Radar status unavailable.";
        return;
      }
      const learning = r.learning,
        last = r.last_learn;
      $("#radar-cancel").hidden = !learning;
      const parts = [];
      if (!r.supported) parts.push("The radar listens to Windows' sound output; it runs on Windows only.");
      else if (learning)
        parts.push(
          learning.phase === "countdown"
            ? `Learning ${what(learning)} in ${Math.ceil(learning.seconds)} s: switch to the game.`
            : `Listening to ${what(learning)}… ${Math.ceil(learning.seconds)} s left.`,
        );
      else {
        if (last) parts.push(last.message);
        parts.push(learnedText(r));
        if (r.error) parts.push("Not listening: " + r.error + ".");
        else if (r.enabled && r.listening)
          parts.push(
            r.heard
              ? `Hearing a cube ${r.direction}, ${near(r)} (match ${Math.round((r.match || 0) * 100)} %).`
              : `Listening${r.device ? " to " + r.device : ""}${r.channels >= 4 ? ` (${LAYOUTS[r.channels] || r.channels + " channels"}: it hears the rear channels)` : ""}: no cube heard.`,
          );
        else if (!r.setting) parts.push("Off.");
      }
      el.textContent = parts.join(" ");
      const samples = r.samples || [],
        key = JSON.stringify(samples);
      if (key !== shownSamples) {
        // rebuilt only when the samples change, so a Forget button keeps its focus
        shownSamples = key;
        const list = $("#radar-samples");
        list.innerHTML = samples.map(sampleRow).join("");
        list.hidden = !samples.length;
        list.querySelectorAll(".radar-forget").forEach((b) => {
          b.onclick = () => radarControl({ action: "forget", sample: b.dataset.id });
        });
      }
    };
    $("#radar-enabled").onchange = () =>
      api("/api/ui", { radar_enabled: $("#radar-enabled").checked }).then(() => {
        toast("Saved");
        setTimeout(radarStatus, 400);
      });
    $("#radar-sens").onchange = () =>
      api("/api/ui", { radar_sensitivity: Math.max(1, Math.min(10, parseInt($("#radar-sens").value, 10) || 5)) }).then(
        () => toast("Saved"),
      );
    const radarControl = (body) =>
      api("/api/radar", body)
        .then(radarStatus)
        .catch((e) => toast(String(e.message || e)));
    $("#radar-learn-bg").onclick = () => radarControl({ action: "learn", kind: "background" });
    $("#radar-learn-cube").onclick = () => radarControl({ action: "learn", kind: "cube" });
    $("#radar-learn-behind").onclick = () => radarControl({ action: "learn", kind: "cube", facing: "behind" });
    $("#radar-learn-other").onclick = () => radarControl({ action: "learn", kind: "other" });
    $("#radar-cancel").onclick = () => radarControl({ action: "cancel" });
    $("#radar-clear").onclick = () => {
      if (confirm("Forget every learned sample: the backgrounds, the cube's sound and the sounds that are not a cube?"))
        radarControl({ action: "clear" });
    };
    radarStatus();
    const radarTimer = setInterval(() => {
      const el = document.getElementById("radar-status");
      if (!el) {
        clearInterval(radarTimer);
        return;
      }
      if (el.offsetParent !== null) radarStatus(); // only while the Overlay tab shows it
    }, 500);
  }
  if ($("#rtss-enabled")) {
    $("#rtss-enabled").onchange = () =>
      api("/api/ui", { rtss_enabled: $("#rtss-enabled").checked }).then(() => {
        toast("Saved");
        setTimeout(rtssStatus, 800);
      });
    $("#rtss-rows").onchange = () =>
      api("/api/ui", { rtss_rows: Math.max(1, Math.min(24, parseInt($("#rtss-rows").value, 10) || 5)) }).then(() =>
        toast("Saved"),
      );
    $("#rtss-metric").onchange = () =>
      api("/api/ui", { rtss_metric: $("#rtss-metric").value }).then(() => toast("Saved"));
    $("#rtss-style").onchange = () => api("/api/ui", { rtss_style: $("#rtss-style").value }).then(() => toast("Saved"));
    $("#rtss-interval").onchange = () =>
      api("/api/ui", {
        rtss_interval_ms: Math.max(100, Math.min(5000, parseInt($("#rtss-interval").value, 10) || 500)),
      }).then(() => toast("Saved"));
    rtssStatus();
  }
  $("#ov-events-sound") &&
    ($("#ov-events-sound").onchange = () =>
      api("/api/ui", { overlay_events_sound: $("#ov-events-sound").checked }).then(() => toast("Saved")));
  if ($("#ov-events-sound-file")) {
    const smsg = $("#ov-events-sound-msg");
    $("#ov-events-sound-file").onchange = async (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      if (file.size > 1024 * 1024) {
        smsg.textContent = "Sound must be 1 MB or smaller — keep it short (~2s).";
        ev.target.value = "";
        return;
      }
      smsg.textContent = "Uploading…";
      try {
        const data = await new Promise((res, rej) => {
          const r = new FileReader();
          r.onload = () => res(r.result);
          r.onerror = () => rej(Error("Could not read the file"));
          r.readAsDataURL(file);
        });
        await api("/api/overlay/event-sound", { data });
        smsg.textContent = "Custom sound set. Use Test to hear it.";
      } catch (e) {
        smsg.textContent = e.message;
      } finally {
        ev.target.value = "";
      }
    };
    $("#ov-events-sound-clear").onclick = async () => {
      try {
        await api("/api/overlay/event-sound", { clear: true });
        smsg.textContent = "Using the built-in chime.";
      } catch (e) {
        smsg.textContent = e.message;
      }
    };
    $("#ov-events-sound-test").onclick = () => previewEventSound();
  }
  $("#ov-autoexp").onchange = () =>
    api("/api/ui", { overlay_auto_expand: $("#ov-autoexp").checked }).then(() => toast("Saved"));
  $("#ov-onlycombat").onchange = () =>
    api("/api/ui", { overlay_only_in_combat: $("#ov-onlycombat").checked }).then(() => toast("Saved"));
  $("#ov-scrollnames").onchange = () =>
    api("/api/ui", { overlay_long_names_scroll: $("#ov-scrollnames").checked }).then(() => toast("Saved"));
  $("#ov-namemode").onchange = () =>
    api("/api/ui", { overlay_name_mode: $("#ov-namemode").value }).then(() => toast("Saved"));
  $("#ov-barstyle").onchange = () =>
    api("/api/ui", { overlay_bar_style: $("#ov-barstyle").value }).then(() => toast("Saved"));
  if ($("#ov-bg-autocontrast"))
    $("#ov-bg-autocontrast").onchange = () =>
      api("/api/ui", { overlay_text_autocontrast: $("#ov-bg-autocontrast").value }).then(() => toast("Saved"));
  $("#ov-barrounded").onchange = () =>
    api("/api/ui", { overlay_bar_rounded: $("#ov-barrounded").checked }).then(() => toast("Saved"));
  $("#ov-classnames").onchange = () =>
    api("/api/ui", { overlay_class_color_names: $("#ov-classnames").checked }).then(() => toast("Saved"));
  $("#ov-stripes").onchange = () =>
    api("/api/ui", { overlay_row_stripes: $("#ov-stripes").checked }).then(() => toast("Saved"));
  $("#ov-classswatch").onchange = () =>
    api("/api/ui", { overlay_class_swatch: $("#ov-classswatch").checked }).then(() => toast("Saved"));
  $("#ov-compact").onchange = () =>
    api("/api/ui", { overlay_compact_rows: $("#ov-compact").checked }).then(() => toast("Saved"));
  $("#ov-rank").onchange = () =>
    api("/api/ui", { overlay_rank_numbers: $("#ov-rank").checked }).then(() => toast("Saved"));
  $("#ov-highlight-me").onchange = () =>
    api("/api/ui", { overlay_highlight_me: $("#ov-highlight-me").checked }).then(() => toast("Saved"));
  $("#ov-dps-graph").onchange = () =>
    api("/api/ui", { overlay_dps_graph: $("#ov-dps-graph").checked }).then(() => toast("Saved"));
  $("#ov-party").onchange = () =>
    api("/api/ui", { overlay_party_enabled: $("#ov-party").checked }).then(() => toast("Saved"));
  $("#ov-always").onchange = () =>
    api("/api/ui", { overlay_always_visible: $("#ov-always").checked }).then(() =>
      toast("Saved · reopen the overlay to apply"),
    );
  $("#ov-remember-pos").onchange = () =>
    api("/api/ui", { overlay_remember_position: $("#ov-remember-pos").checked }).then(() =>
      toast("Saved · reopen the overlay to apply"),
    );
  $("#ov-resizable").onchange = () =>
    api("/api/ui", { overlay_resizable: $("#ov-resizable").checked }).then(() =>
      toast("Saved · reopen the overlay to apply"),
    );
  $("#ov-snap").onchange = () =>
    api("/api/ui", { overlay_snap_edge: $("#ov-snap").checked }).then(() =>
      toast("Saved · reopen the overlay to apply"),
    );
  $("#ov-expandup").onchange = () =>
    api("/api/ui", { overlay_expand_up: $("#ov-expandup").checked }).then(() =>
      toast("Saved · reopen the overlay to apply"),
    );
  const saveLayoutNum = async (id, key, lo, hi) => {
    const el = $("#" + id),
      msg = $("#ov-layout-msg"),
      n = parseInt(el.value, 10);
    if (!Number.isInteger(n) || n < lo || n > hi) {
      msg.textContent = `Enter a whole number from ${lo} to ${hi}.`;
      return;
    }
    try {
      await api("/api/ui", { [key]: n });
      msg.textContent = "Saved";
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#ov-maxp").onchange = () => saveLayoutNum("ov-maxp", "overlay_max_players", 1, 24);
  $("#ov-width").onchange = () => saveLayoutNum("ov-width", "overlay_width", 260, 800);
  $("#ov-height").onchange = () => saveLayoutNum("ov-height", "overlay_height", 0, 800);
  $("#ov-rowh").onchange = () => saveLayoutNum("ov-rowh", "overlay_row_height", 14, 48);
  $("#ov-interp").onchange = () =>
    api("/api/ui", { overlay_dps_interpolate: $("#ov-interp").checked }).then(() => toast("Saved"));
  $("#ov-interp-ms").onchange = () => saveLayoutNum("ov-interp-ms", "overlay_interpolate_ms", 50, 1000);
  $("#ov-fps").onchange = () => api("/api/ui", { overlay_show_fps: $("#ov-fps").checked }).then(() => toast("Saved"));
  $("#ov-clickthrough").onchange = () =>
    api("/api/ui", { overlay_click_through: $("#ov-clickthrough").checked }).then(() =>
      toast("Saved · applies to the open overlay within 10s"),
    );
  $("#rec-reset").onchange = () =>
    api("/api/ui", { meter_reset_after_battle: $("#rec-reset").checked }).then(() => toast("Saved"));
  $("#rec-boss-reset").onchange = () =>
    api("/api/ui", { meter_reset_on_boss_start: $("#rec-boss-reset").checked }).then(() => toast("Saved"));
  const saveRecNum = async (id, key, lo, hi) => {
    const el = $("#" + id),
      msg = $("#rec-msg"),
      n = parseInt(el.value, 10);
    if (!Number.isInteger(n) || n < lo || n > hi) {
      msg.textContent = `Enter a whole number from ${lo} to ${hi}.`;
      return;
    }
    try {
      await api("/api/ui", { [key]: n });
      msg.textContent = "Saved";
    } catch (e) {
      msg.textContent = e.message;
    }
  };
  $("#rec-delay").onchange = () => saveRecNum("rec-delay", "meter_reset_delay", 1, 120);
  $("#rec-max").onchange = () => saveRecNum("rec-max", "meter_max_records", 1, 500);
  $("#rec-save").onchange = () =>
    api("/api/ui", { meter_save_records: $("#rec-save").checked }).then(() =>
      toast("Saved · applies to the next capture"),
    );
  $("#rec-logcache").onchange = () => {
    const v = Math.max(0, Math.min(1048576, Math.round(+$("#rec-logcache").value || 0)));
    $("#rec-logcache").value = v;
    api("/api/ui", { meter_log_cache_mb: v }).then(() => {
      const m = $("#rec-logcache-msg");
      if (m) {
        m.textContent = v ? "Saved · logs kept under " + v + " MB" : "Saved · auto-delete off";
        setTimeout(() => {
          if (m) m.textContent = "";
        }, 2500);
      }
    });
  };
  $("#rec-upload-before-prune").onchange = () =>
    api("/api/ui", { meter_upload_before_prune: $("#rec-upload-before-prune").checked }).then(() => toast("Saved"));
  $("#rec-autostart").onchange = () =>
    api("/api/ui", { meter_autostart: $("#rec-autostart").checked }).then(() =>
      toast("Saved · applies on next launch"),
    );
  $("#rec-server-name").onchange = () =>
    api("/api/ui", { meter_show_server_name: $("#rec-server-name").checked }).then(() => toast("Saved"));
  $("#rec-autoupload").onchange = () =>
    api("/api/ui", { meter_auto_upload: $("#rec-autoupload").checked }).then(() => toast("Saved"));
  $("#rec-catchup").onchange = () =>
    api("/api/ui", { meter_catch_up_uploads: $("#rec-catchup").checked }).then(() => toast("Saved"));
  $("#rec-perfight").onchange = () =>
    api("/api/ui", { meter_upload_per_fight: $("#rec-perfight").checked }).then(() => toast("Saved"));
  $("#rec-report-boss").onchange = () =>
    api("/api/ui", { meter_report_boss_kills: $("#rec-report-boss").checked }).then(() => toast("Saved"));
  $("#rec-report-enemy-hp").onchange = () =>
    api("/api/ui", { meter_report_enemy_hp: $("#rec-report-enemy-hp").checked }).then(() => toast("Saved"));
  $("#rec-report-diagnostics").onchange = () =>
    api("/api/ui", { meter_report_diagnostics: $("#rec-report-diagnostics").checked }).then(() => toast("Saved"));
  $("#rec-dummy").onchange = () =>
    api("/api/ui", { meter_show_dummy_parse: $("#rec-dummy").checked }).then(() => toast("Saved"));
  $("#rec-dummy-secs").onchange = () => saveRecNum("rec-dummy-secs", "meter_dummy_record_seconds", 5, 3600);
  $("#settings-export").onclick = async () => {
    const msg = $("#settings-backup-msg");
    $("#settings-export").disabled = true;
    msg.textContent = "Exporting…";
    try {
      const r = await api("/api/ui/export", {});
      msg.textContent = "Saved to " + r.file;
    } catch (e) {
      msg.textContent = e.message;
    } finally {
      $("#settings-export").disabled = false;
    }
  };
  $("#settings-import-file").onchange = async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    const msg = $("#settings-backup-msg");
    if (!file) return;
    msg.textContent = "Importing…";
    try {
      const document = JSON.parse(await file.text());
      const r = await api("/api/ui/import", { document });
      msg.textContent = "Imported: " + (r.imported || []).join(", ") + ". Reopen the overlay to apply.";
      pageSettings();
    } catch (e) {
      msg.textContent = "Could not import: " + e.message;
    } finally {
      ev.target.value = "";
    }
  };
  $("#autoupd").onchange = () => api("/api/ui", { auto_update: $("#autoupd").checked }).then(() => toast("Saved"));
  if ($("#chkupd"))
    $("#chkupd").onclick = async () => {
      const button = $("#chkupd");
      button.disabled = true;
      $("#updstate").textContent = "· checking for updates…";
      try {
        const r = await api("/api/update/check", {});
        if (r.update) {
          pageSettings();
          return;
        } // a release is out: show Install now
        if ($("#updstate")) $("#updstate").innerHTML = updateStateText(r.update_state); // escaped inside
      } catch (e) {
        if ($("#updstate")) $("#updstate").textContent = "· could not check: " + e.message;
      } finally {
        if (button.isConnected) button.disabled = false;
      }
    };
  if ($("#instupd"))
    $("#instupd").onclick = async () => {
      $("#instupd").disabled = true;
      $("#updmsg").textContent = "Downloading and checking the installer…";
      try {
        const r = await api("/api/update", {});
        if (r.status === "launching") {
          document.body.innerHTML =
            '<div class="empty" style="margin-top:20vh">Aion 2 Calc is closing. The installer will open in a moment.</div>';
          return;
        }
        $("#instupd").disabled = false;
        $("#updmsg").textContent =
          {
            "launch-failed":
              "The installer helper did not start. Your app is still running; open the updates folder to run the setup file.",
            applying: "installing — the app will restart",
            launching: "closing the app, then opening the installer — follow its prompts",
            downloaded: "downloaded — open your data folder’s “updates” to run it",
            "download-failed": "download failed",
            "check-failed": "could not reach GitHub for the update; try again in a minute",
            "up-to-date": "already up to date",
          }[r.status] || r.status;
      } catch (e) {
        if ($("#updmsg")) $("#updmsg").textContent = e.message;
        if ($("#instupd")) $("#instupd").disabled = false;
      }
    };
  $$("[data-open]").forEach(
    (b) => (b.onclick = () => api("/api/open", { what: b.dataset.open }).catch((e) => toast(e.message))),
  );
  const serverVersionText = (r) =>
    r.software?.server || r.software?.analyzer
      ? ` · server ${r.software?.server || "not reported"} · analyzer ${r.software?.analyzer || "not reported"}`
      : " · runtime versions not reported by this server";
  $("#scheck").onclick = async () => {
    const button = $("#scheck"),
      message = $("#smsg");
    button.disabled = true;
    message.textContent = "Checking saved server runtime…";
    try {
      const r = await api("/api/logserver/check");
      if (message.isConnected)
        message.textContent = r.ok
          ? "Server reachable" + serverVersionText(r)
          : "Check failed: " + (r.detail || "unavailable");
    } catch (e) {
      if (message.isConnected) message.textContent = e.message;
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  };
  $("#ssave").onclick = async () => {
    await api("/api/logserver", { url: $("#surl").value, key: $("#skey").value || null, visibility: $("#svis").value });
    $("#smsg").textContent = "saved · checking…";
    // The app (not the browser) probes the server, so CORS and http/https rules don't give a false negative.
    try {
      const r = await api("/api/logserver/check");
      $("#smsg").textContent = r.ok
        ? "saved · server reachable" + (r.name ? " — " + esc(r.name) : "") + serverVersionText(r)
        : "saved · can't reach the server" + (r.detail ? " (" + esc(r.detail) + ")" : "");
    } catch (e) {
      $("#smsg").textContent = "saved · could not check: " + e.message;
    }
  };
  $("#sync").onclick = async () => {
    await api("/api/sync", {});
    toast("Checking for game updates");
  };
  $("#asset-reindex").onclick = async () => {
    const button = $("#asset-reindex"),
      message = $("#asset-msg");
    button.disabled = true;
    message.textContent = "Re-indexing cached official references…";
    try {
      const r = await runJob("/api/assets/reindex", {}, (lines) => {
        message.textContent = lines.at(-1) || "Re-indexing…";
      });
      message.textContent = `Re-indexed ${n0(r.profiles)} profiles · ${n0(r.references)} references examined · ${n0(r.skipped)} skipped. Reopen the affected view to reload icons.`;
      toast("Cached icon re-index complete");
    } catch (e) {
      message.textContent = "Could not re-index icons: " + e.message;
    } finally {
      button.disabled = false;
    }
  };
  $("#asset-report").onclick = async () => {
    const button = $("#asset-report"),
      message = $("#asset-msg");
    button.disabled = true;
    message.textContent = "Collecting image references…";
    try {
      const data = await api("/api/assets");
      data.browser_images = window.A2AssetHealth?.report();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })),
        link = document.createElement("a");
      link.href = url;
      link.download = "aion2-asset-coverage.json";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message.textContent = "Image coverage export requested. Check your Downloads folder.";
    } catch (e) {
      message.textContent = "Could not export image coverage: " + e.message;
    } finally {
      button.disabled = false;
    }
  };
  $("#retry-images").onclick = () => {
    window.A2AssetHealth?.retry();
    $("#asset-msg").textContent = "Image retries enabled. Reopen the affected view to reload its images.";
  };
  $("#quit2").onclick = () => $("#quit").click();
}

// The Settings line for the last release check: a failed check is reported as such, never as "up to date".
function updateStateText(state) {
  const st = state || {};
  if (st.checking) return "· checking for updates…";
  if (st.error) return `· could not check for updates (${esc(st.error)}); trying again shortly`;
  if (st.checked_at) return `· up to date (checked ${esc(clockAt(st.checked_at * 1000))})`;
  return "· up to date";
}
