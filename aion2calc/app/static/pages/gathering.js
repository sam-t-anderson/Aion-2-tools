/* Gathering (#/gathering, Game): this computer's gathering log and everyone's drop rates, gathering.js. */
"use strict";

async function pageGathering() {
  app().innerHTML = `<section class="win"><div class="wh"><h2>Gathering</h2><span class="sub">what you gather and take from dungeon reward cubes, and everyone's drop rates</span></div>
    <div class="wb"><p class="small muted" id="gathering-sharing"></p><div id="gathering"></div></div></section>`;
  let sharing = true;
  A2Gathering.mount($("#gathering"), {
    mineLabel: "This computer",
    mine: async () => {
      const mine = await api("/api/gathering");
      sharing = mine.sharing !== false;
      $("#gathering-sharing").innerHTML = sharing
        ? 'The Live Meter records what you gather and what dungeon reward cubes give, and shares it for everyone\'s drop rates ("Share gathering and drop data" in <a href="#/settings">Settings</a>).'
        : 'The Live Meter records what you gather and what dungeon reward cubes give. Sharing is off, so your records stay on this computer (<a href="#/settings">Settings</a>).';
      return mine;
    },
    community: () => communityAPI("/api/v1/gathering/stats"),
  });
}
