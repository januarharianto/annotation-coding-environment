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
  const ctxEl = document.getElementById("cv-ctx");
  const clearBtn = document.getElementById("cv-clear");

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Selection state
  let selectedSources = new Set();          // Set<source idx>
  let selectedExcerpt = null;               // {srcIdx, excerptIdx} | null
  let anchorIdx = null;                     // most recent plain/Cmd click target
  let sortBy = "source";                    // wired in Task 5
  let filterText = "";                      // wired in Task 5

  // --- Static render: tracks ---
  tracksEl.innerHTML = sources.map((s) => {
    const ticks = s.excerpts.map((e, ei) => {
      return `<span class="tick" data-ex="${ei}"
                    style="left:${e.pos_pct.toFixed(2)}%;width:${e.width_pct.toFixed(2)}%"
                    title="excerpt ${ei + 1}"></span>`;
    }).join("");
    const pad = String(s.idx).padStart(2, "0");
    return `<div class="cv-track-row" role="option" aria-selected="false"
                 data-src-idx="${s.idx}">
      <span class="idx">${pad}</span>
      <span class="ct">${s.count}</span>
      <span class="track">${ticks}</span>
    </div>`;
  }).join("");

  const displayOrder = sources.map((s) => s.idx);

  function bySrcIdx(idx) { return sources.find((s) => s.idx === idx); }

  // --- Table rendering (respects selection + sort + filter) ---
  function renderTable() {
    let srcSet;
    if (selectedExcerpt) srcSet = [selectedExcerpt.srcIdx];
    else if (selectedSources.size === 0) srcSet = displayOrder.slice();
    else srcSet = [...selectedSources].sort((a, b) => a - b);

    // Flatten to {src, excerpt, localIdx}
    let items = [];
    srcSet.forEach((idx) => {
      const s = bySrcIdx(idx);
      if (!s) return;
      const excerpts = selectedExcerpt ? [s.excerpts[selectedExcerpt.excerptIdx]] : s.excerpts;
      excerpts.forEach((e, localEi) => {
        const ei = selectedExcerpt ? selectedExcerpt.excerptIdx : localEi;
        items.push({ srcIdx: idx, excerptIdx: ei, pos: e.pos_pct, len: e.text.length, text: e.text });
      });
    });

    // Filter (wired in Task 5; code is here so the shape is ready)
    if (filterText) {
      const q = filterText.toLowerCase();
      items = items.filter((it) => it.text.toLowerCase().includes(q));
    }

    // Sort (wired in Task 5; code is here so the shape is ready)
    if (sortBy === "length") items.sort((a, b) => b.len - a.len);
    else if (sortBy === "position") items.sort((a, b) => a.pos - b.pos);
    // 'source' keeps source-then-offset order (already the case from srcSet iteration)

    let html = `<div class="cv-table-head"><span>#</span><span>Excerpt</span></div>`;
    if (items.length === 0) {
      html += `<div class="cv-empty">No excerpts match the filter.</div>`;
    } else {
      items.forEach((it, i) => {
        const cls = (selectedExcerpt
                     && selectedExcerpt.srcIdx === it.srcIdx
                     && selectedExcerpt.excerptIdx === it.excerptIdx) ? " selected" : "";
        html += `<div class="cv-row${cls}" data-src-idx="${it.srcIdx}" data-ex="${it.excerptIdx}">
          <span class="idx">${i + 1}</span>
          <span class="txt">${escapeHtml(it.text)}</span>
        </div>`;
      });
    }
    tableEl.innerHTML = html;
  }

  function highlightSource(idx) {
    tracksEl.querySelectorAll(".cv-track-row.hovered").forEach((r) => r.classList.remove("hovered"));
    const row = tracksEl.querySelector(`.cv-track-row[data-src-idx="${idx}"]`);
    if (row) row.classList.add("hovered");
  }
  function clearHighlight() {
    tracksEl.querySelectorAll(".cv-track-row.hovered").forEach((r) => r.classList.remove("hovered"));
  }

  // --- Update all UI to match state ---
  function updateUI() {
    // Track row selection + aria-selected
    tracksEl.querySelectorAll(".cv-track-row").forEach((r) => {
      const idx = Number(r.getAttribute("data-src-idx"));
      const isSel = selectedSources.has(idx);
      r.classList.toggle("selected", isSel);
      r.setAttribute("aria-selected", isSel ? "true" : "false");
    });
    // Tick selection (single excerpt)
    tracksEl.querySelectorAll(".tick").forEach((t) => {
      t.classList.remove("selected");
    });
    if (selectedExcerpt) {
      const sel = tracksEl.querySelector(
        `.cv-track-row[data-src-idx="${selectedExcerpt.srcIdx}"] .tick[data-ex="${selectedExcerpt.excerptIdx}"]`,
      );
      if (sel) sel.classList.add("selected");
    }
    // Context bar + Clear
    if (selectedExcerpt) {
      const s = bySrcIdx(selectedExcerpt.srcIdx);
      ctxEl.innerHTML = `Showing excerpt <b>${selectedExcerpt.excerptIdx + 1}</b>
                         from <b>${escapeHtml(s.name)}</b>`;
    } else if (selectedSources.size === 0) {
      ctxEl.innerHTML = `Showing <b>all</b> sources ·
                         <b>${data.stats.excerpts}</b> excerpts`;
    } else if (selectedSources.size === 1) {
      const s = bySrcIdx([...selectedSources][0]);
      ctxEl.innerHTML = `Showing <b>${escapeHtml(s.name)}</b> ·
                         <b>${s.count}</b> excerpts`;
    } else {
      const total = [...selectedSources].reduce((a, idx) => a + (bySrcIdx(idx)?.count || 0), 0);
      ctxEl.innerHTML = `Showing <b>${selectedSources.size} sources</b> ·
                         <b>${total}</b> excerpts`;
    }
    clearBtn.disabled = !selectedExcerpt && selectedSources.size === 0;

    renderTable();
  }

  // --- Mouse handlers on tracks ---
  tracksEl.addEventListener("click", (evt) => {
    const tick = evt.target.closest(".tick");
    const row = evt.target.closest(".cv-track-row");
    if (tick) {
      const srcIdx = Number(row.getAttribute("data-src-idx"));
      const excerptIdx = Number(tick.getAttribute("data-ex"));
      selectedExcerpt = { srcIdx, excerptIdx };
      selectedSources = new Set([srcIdx]);
      anchorIdx = srcIdx;
      updateUI();
      return;
    }
    if (!row) return;
    const idx = Number(row.getAttribute("data-src-idx"));

    // Shift+click with no anchor, or shift+click on the anchor row itself,
    // falls through to the plain-click branch (matches Finder/File Explorer).
    if (evt.shiftKey && anchorIdx !== null && anchorIdx !== idx) {
      const aPos = displayOrder.indexOf(anchorIdx);
      const bPos = displayOrder.indexOf(idx);
      if (aPos >= 0 && bPos >= 0) {
        const [lo, hi] = [Math.min(aPos, bPos), Math.max(aPos, bPos)];
        selectedSources = new Set(displayOrder.slice(lo, hi + 1));
      }
      selectedExcerpt = null;
    } else if (evt.metaKey || evt.ctrlKey) {
      if (selectedSources.has(idx)) selectedSources.delete(idx);
      else selectedSources.add(idx);
      selectedExcerpt = null;
      anchorIdx = idx;
    } else {
      if (selectedSources.size === 1 && selectedSources.has(idx) && !selectedExcerpt) {
        selectedSources.clear();
        anchorIdx = null;
      } else {
        selectedSources = new Set([idx]);
        selectedExcerpt = null;
        anchorIdx = idx;
      }
    }
    updateUI();
  });

  // Delegated hover linkage — set once; survives every table re-render.
  // mouseover/mouseout bubble, unlike mouseenter/mouseleave — use those
  // with a closest() guard so the linkage triggers once per row entry.
  tableEl.addEventListener("mouseover", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row || !tableEl.contains(row)) return;
    // Only fire when entering the row from outside it (mimic mouseenter)
    const related = evt.relatedTarget;
    if (related && row.contains(related)) return;
    highlightSource(Number(row.getAttribute("data-src-idx")));
  });
  tableEl.addEventListener("mouseout", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row) return;
    // Only fire when leaving the row entirely (mimic mouseleave)
    const related = evt.relatedTarget;
    if (related && row.contains(related)) return;
    clearHighlight();
  });

  clearBtn.addEventListener("click", () => {
    selectedSources.clear();
    selectedExcerpt = null;
    anchorIdx = null;
    updateUI();
  });

  updateUI();
})();
