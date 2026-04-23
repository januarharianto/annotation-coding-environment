// Coded text view — interactive tracks + excerpt table.
// Design spec: docs/superpowers/specs/2026-04-23-coded-text-view-design.md
// Mockup reference: docs/mockups/coded-text-view-options.html → Option 6C.

"use strict";

(function () {
  const dataEl = document.getElementById("ace-codeview-data");
  if (!dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  const sources = data.sources;

  const tracksEl = document.getElementById("cv-tracks");
  const tableEl = document.getElementById("cv-table");

  // --- Static render: tracks (read-only at this task's scope) ---
  tracksEl.innerHTML = sources.map((s) => {
    const ticks = s.excerpts.map((e, ei) => {
      return `<span class="tick" data-ex="${ei}"
                    style="left:${e.pos_pct.toFixed(2)}%;width:${e.width_pct.toFixed(2)}%"
                    title="excerpt ${ei + 1}"></span>`;
    }).join("");
    const pad = String(s.idx).padStart(2, "0");
    return `<div class="cv-track-row" data-src-idx="${s.idx}">
      <span class="idx">${pad}</span>
      <span class="ct">${s.count}</span>
      <span class="track">${ticks}</span>
    </div>`;
  }).join("");

  // --- Static render: flat excerpt list (all sources, source order) ---
  function renderTable() {
    const rows = [];
    let globalIdx = 1;
    sources.forEach((s) => {
      s.excerpts.forEach((e) => {
        rows.push({ src_idx: s.idx, text: escapeHtml(e.text), n: globalIdx++ });
      });
    });
    let html = `<div class="cv-table-head"><span>#</span><span>Excerpt</span></div>`;
    if (rows.length === 0) {
      html += `<div class="cv-empty">No excerpts.</div>`;
    } else {
      rows.forEach((r) => {
        html += `<div class="cv-row" data-src-idx="${r.src_idx}">
          <span class="idx">${r.n}</span>
          <span class="txt">${r.text}</span>
        </div>`;
      });
    }
    tableEl.innerHTML = html;
  }
  renderTable();

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
})();
