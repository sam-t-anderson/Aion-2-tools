/* Maps (#/maps) and Crafting (#/crafting): maps.js and crafting.js. */
"use strict";

let workshopView = null;
async function pageWorkshop(kind) {
  app().innerHTML = '<div id="workshop"></div>';
  workshopView = (kind === "maps" ? A2Maps : A2Crafting).mount($("#workshop"));
}
