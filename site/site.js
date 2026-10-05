// Landing page: fill in direct download links from the latest GitHub release (falls back to the
// Releases page link already in the HTML if the API call fails).
(async function () {
  const el = document.getElementById("downloads");
  if (!el) return;
  try {
    const r = await fetch("https://api.github.com/repos/sam-t-anderson/Aion-2-tools/releases/latest");
    if (!r.ok) return;
    const rel = await r.json();
    const pick = (test) => (rel.assets || []).find((a) => test(a.name.toLowerCase()));
    const order = [
      ["Windows installer", pick((n) => n.endsWith(".exe"))],
      ["Windows (portable)", pick((n) => n.includes("windows") && n.endsWith(".zip"))],
      ["macOS", pick((n) => n.includes("mac"))],
      ["Linux", pick((n) => n.includes("linux"))],
    ];
    const btns = order.filter(([, a]) => a).map(([label, a]) => {
      const el2 = document.createElement("a");
      el2.className = "btn primary"; el2.href = a.browser_download_url; el2.textContent = label; return el2;
    });
    if (!btns.length) return;
    const notes = document.createElement("a");
    notes.className = "btn"; notes.href = rel.html_url; notes.target = "_blank"; notes.rel = "noopener";
    notes.textContent = (rel.tag_name || "latest") + " release notes";
    el.replaceChildren(...btns, notes);
  } catch (e) { /* keep the fallback link */ }
})();
