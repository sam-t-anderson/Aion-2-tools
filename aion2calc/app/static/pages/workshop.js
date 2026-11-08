/* Maps (#/maps) and Crafting (#/crafting): maps.js and crafting.js. */
"use strict";

let workshopView = null;
async function pageWorkshop(kind) {
  app().innerHTML = '<div id="workshop"></div>';
  // The Maps page reads the Abyss PvP heat map from the log server through this app's proxy.
  workshopView = kind === "maps" ? A2Maps.mount($("#workshop"), { api: communityAPI }) : A2Crafting.mount($("#workshop"));
}
