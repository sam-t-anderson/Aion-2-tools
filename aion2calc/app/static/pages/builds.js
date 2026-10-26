/* Builds (#/builds): build-workspace.js, evaluating builds on this computer. */
"use strict";

let buildWorkspaceView = null,
  buildWorkspaceContext = null;
async function pageBuilds() {
  app().innerHTML = '<div id="build-workspace"></div>';
  buildWorkspaceView = A2BuildWorkspace.mount($("#build-workspace"), {
    api: communityAPI,
    localEvaluation: true,
    evaluate: (doc) => api("/api/build/evaluate", doc),
    ...(buildWorkspaceContext || {}),
  });
  buildWorkspaceContext = null;
}
