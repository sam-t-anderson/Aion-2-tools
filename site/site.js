// Landing page: fill in direct download links from the latest GitHub release (falls back to the
// Releases page link already in the HTML if the API call fails).
(async function () {
  const el = document.getElementById("downloads");
  if (!el) return;
  // Only ever navigate to an http(s) URL from the release JSON: a crafted value
  // cannot become a javascript:/data: link or otherwise redirect the visitor.
  const httpUrl = (u) => { try { const x = new URL(u, location.href); return (x.protocol === "https:" || x.protocol === "http:") ? x.href : null; } catch (e) { return null; } };
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
      const href = httpUrl(a.browser_download_url);
      if (!href) return null;
      const el2 = document.createElement("a");
      el2.className = "btn primary"; el2.href = href; el2.textContent = label; return el2;
    }).filter(Boolean);
    if (!btns.length) return;
    const notesHref = httpUrl(rel.html_url);
    if (!notesHref) return;
    const notes = document.createElement("a");
    notes.className = "btn"; notes.href = notesHref; notes.target = "_blank"; notes.rel = "noopener";
    notes.textContent = (rel.tag_name || "latest") + " release notes";
    el.replaceChildren(...btns, notes);
  } catch (e) { /* keep the fallback link */ }
})();
