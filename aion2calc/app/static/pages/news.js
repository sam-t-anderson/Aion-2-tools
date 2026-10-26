/* News (#/news): news.js, through the app's proxy to the log server. */
"use strict";

async function pageNews() {
  app().innerHTML = '<div id="official-news"></div>';
  A2News.mount($("#official-news"), { api: communityAPI });
}
