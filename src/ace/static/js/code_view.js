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

  // Throttled live-region announcer. Rapid arrow-key extension should
  // announce once at the end of a stream of changes, not on every key.
  const liveEl = document.getElementById("cv-live");
  let liveTimer = null;
  function announce(msg) {
    if (!liveEl) return;
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => { liveEl.textContent = msg; }, 120);
  }

  // Selection state
  let selectedSources = new Set();          // Set<source idx>
  let selectedExcerpt = null;               // {srcIdx, excerptIdx} | null
  let anchorIdx = null;                     // most recent plain/Cmd click target
  let sortBy = "source";                    // wired in Task 5
  let filterText = "";                      // wired in Task 5

  // --- Static render: tracks ---
  tracksEl.innerHTML = sources.map((s, i) => {
    const ticks = s.excerpts.map((e, ei) => {
      return `<span class="tick" data-ex="${ei}"
                    style="left:${e.pos_pct.toFixed(2)}%;width:${e.width_pct.toFixed(2)}%"
                    title="excerpt ${ei + 1}"
                    aria-hidden="true"></span>`;
    }).join("");
    const pad = String(s.idx).padStart(2, "0");
    const tabIdx = i === 0 ? "0" : "-1";
    const label = `Source ${s.idx} — ${s.name}, ${s.count} excerpts`;
    return `<div class="cv-track-row" role="option" aria-selected="false"
                 tabindex="${tabIdx}" data-src-idx="${s.idx}"
                 aria-label="${escapeHtml(label)}">
      <span class="idx" aria-hidden="true">${pad}</span>
      <span class="ct" aria-hidden="true">${s.count}</span>
      <span class="track" aria-hidden="true">${ticks}</span>
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
        html += `<div class="cv-row${cls}" tabindex="0"
                      data-src-idx="${it.srcIdx}" data-ex="${it.excerptIdx}">
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

    // Announce current scope to screen readers (throttled)
    announce(ctxEl.textContent.replace(/\s+/g, " ").trim());
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

  // Keyboard focus on an excerpt row has the same linkage to tracks as hover.
  // focus/blur don't bubble, so use capture phase.
  tableEl.addEventListener("focus", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row) return;
    highlightSource(Number(row.getAttribute("data-src-idx")));
  }, true);
  tableEl.addEventListener("blur", (evt) => {
    const row = evt.target.closest(".cv-row");
    if (!row) return;
    clearHighlight();
  }, true);

  // --- Keyboard navigation on tracks (roving tabindex) ---
  function allRows() {
    return [...tracksEl.querySelectorAll(".cv-track-row")];
  }
  function focusedRowIdx() {
    const rows = allRows();
    return rows.indexOf(document.activeElement);
  }
  function moveFocus(newPos) {
    const rows = allRows();
    if (rows.length === 0) return;
    if (newPos < 0) newPos = 0;
    if (newPos > rows.length - 1) newPos = rows.length - 1;
    rows.forEach((r, i) => r.setAttribute("tabindex", i === newPos ? "0" : "-1"));
    rows[newPos].focus();
  }
  function extendRange(toIdx) {
    if (anchorIdx === null) return;
    const aPos = displayOrder.indexOf(anchorIdx);
    const bPos = displayOrder.indexOf(toIdx);
    if (aPos < 0 || bPos < 0) return;
    const [lo, hi] = [Math.min(aPos, bPos), Math.max(aPos, bPos)];
    selectedSources = new Set(displayOrder.slice(lo, hi + 1));
    selectedExcerpt = null;
  }

  tracksEl.addEventListener("keydown", (evt) => {
    const rows = allRows();
    if (rows.length === 0) return;
    const pos = focusedRowIdx();
    if (pos < 0) return;
    const focusedSrcIdx = Number(rows[pos].getAttribute("data-src-idx"));

    // Navigation — no selection change
    if (evt.key === "ArrowDown" && !evt.shiftKey) {
      evt.preventDefault(); moveFocus(pos + 1); return;
    }
    if (evt.key === "ArrowUp" && !evt.shiftKey) {
      evt.preventDefault(); moveFocus(pos - 1); return;
    }
    if (evt.key === "Home") { evt.preventDefault(); moveFocus(0); return; }
    if (evt.key === "End")  { evt.preventDefault(); moveFocus(rows.length - 1); return; }

    // Shift+Arrow — move focus AND extend range from anchor
    if (evt.shiftKey && (evt.key === "ArrowUp" || evt.key === "ArrowDown")) {
      evt.preventDefault();
      const next = Math.max(0, Math.min(rows.length - 1, pos + (evt.key === "ArrowDown" ? 1 : -1)));
      moveFocus(next);
      const targetIdx = Number(rows[next].getAttribute("data-src-idx"));
      if (anchorIdx === null) anchorIdx = focusedSrcIdx;
      extendRange(targetIdx);
      updateUI();
      return;
    }

    // Space — toggle focused row like a plain click
    if ((evt.key === " " || evt.code === "Space") && !evt.shiftKey) {
      evt.preventDefault();
      if (selectedSources.size === 1 && selectedSources.has(focusedSrcIdx) && !selectedExcerpt) {
        selectedSources.clear();
        anchorIdx = null;
      } else {
        selectedSources = new Set([focusedSrcIdx]);
        selectedExcerpt = null;
        anchorIdx = focusedSrcIdx;
      }
      updateUI();
      return;
    }

    // Shift+Space — extend range from anchor to focused (no focus move)
    if ((evt.key === " " || evt.code === "Space") && evt.shiftKey) {
      evt.preventDefault();
      if (anchorIdx === null) anchorIdx = focusedSrcIdx;
      extendRange(focusedSrcIdx);
      updateUI();
      return;
    }

    // Ctrl/Cmd+A — select all
    if ((evt.metaKey || evt.ctrlKey) && evt.key.toLowerCase() === "a") {
      evt.preventDefault();
      selectedSources = new Set(displayOrder);
      selectedExcerpt = null;
      updateUI();
      return;
    }
  });

  clearBtn.addEventListener("click", () => {
    selectedSources.clear();
    selectedExcerpt = null;
    anchorIdx = null;
    updateUI();
  });

  // --- Global key handlers (Esc two-stage + N exits-and-opens-notes) ---
  // Registered on the capturing phase with stopImmediatePropagation so the
  // page's bridge.js (which also handles N and Esc on the coding page) never
  // sees these events when we're on /code/{id}/view.
  document.addEventListener("keydown", (evt) => {
    // Don't hijack keys while the user is typing in the filter field — but
    // still let Esc clear the field even there.
    const searchEl = document.getElementById("cv-search");
    if (evt.target === searchEl) {
      if (evt.key === "Escape") {
        evt.target.value = "";
        filterText = "";
        evt.target.blur();
        updateUI();
        evt.preventDefault();
        evt.stopImmediatePropagation();
      }
      return;
    }

    if (evt.key === "Escape") {
      if (filterText || selectedSources.size > 0 || selectedExcerpt) {
        filterText = "";
        selectedSources.clear();
        selectedExcerpt = null;
        anchorIdx = null;
        if (searchEl) searchEl.value = "";
        updateUI();
      } else {
        window.location.href = "/code";
      }
      evt.preventDefault();
      evt.stopImmediatePropagation();
      return;
    }

    if (evt.key === "n" || evt.key === "N") {
      // Don't hijack letter-typing in form fields
      const tag = (evt.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || evt.target.isContentEditable) return;
      window.location.href = "/code?note=1";
      evt.preventDefault();
      evt.stopImmediatePropagation();
      return;
    }
  }, true); // capture phase — wins over bridge.js

  // --- Sort chips ---
  const toolbarEl = document.getElementById("cv-toolbar");
  if (toolbarEl) {
    toolbarEl.querySelectorAll("[data-sort]").forEach((chip) => {
      chip.addEventListener("click", () => {
        toolbarEl.querySelectorAll("[data-sort]").forEach((c) =>
          c.setAttribute("aria-pressed", "false"));
        chip.setAttribute("aria-pressed", "true");
        sortBy = chip.getAttribute("data-sort");
        updateUI();
      });
    });
  }

  // --- Text filter ---
  const searchEl = document.getElementById("cv-search");
  if (searchEl) {
    searchEl.addEventListener("input", (evt) => {
      filterText = evt.target.value.trim();
      updateUI();
    });
  }

  // --- Codebook sidebar wiring ---
  // The shared codebook partial is rendered here as well. Mark the currently-
  // viewed code and intercept clicks on rows to navigate instead of apply.
  (function initSidebar() {
    const currentId = data.code.id;
    const currentRow = document.querySelector(
      `#code-sidebar .ace-code-row[data-code-id="${currentId}"]`,
    );
    if (currentRow) currentRow.classList.add("ace-code-row--current");

    // Capture-phase click handler so bridge.js's row handlers don't also act.
    document.addEventListener("click", (evt) => {
      const row = evt.target.closest("#code-sidebar .ace-code-row[data-code-id]");
      if (!row) return;
      // Ignore clicks inside the right-click menu or on the keycap (there
      // shouldn't be any — keycaps are display:none here — but be defensive).
      if (evt.target.closest(".ace-code-menu") || evt.target.closest(".ace-keycap")) return;
      const id = row.getAttribute("data-code-id");
      if (!id) return;
      evt.preventDefault();
      evt.stopImmediatePropagation();
      if (id === currentId) return;   // already here, no-op
      window.location.href = `/code/${id}/view`;
    }, true);
  })();

  // --- Sidebar resize — shared ace-sidebar-width localStorage with /code ---
  // Port of bridge.js::_initResize, tailored to this page's container.
  (function initResize() {
    const handle = document.getElementById("cv-resize-handle");
    const container = document.getElementById("code-view");
    if (!handle || !container) return;
    let dragging = false;
    handle.addEventListener("pointerdown", (e) => {
      dragging = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });
    document.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const rect = container.getBoundingClientRect();
      let x = e.clientX - rect.left;
      const min = 150;
      const max = rect.width * 0.4;
      x = Math.max(min, Math.min(max, x));
      document.documentElement.style.setProperty("--ace-sidebar-width", `${x}px`);
    });
    document.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      const width = parseInt(
        getComputedStyle(document.documentElement).getPropertyValue("--ace-sidebar-width"),
        10,
      );
      if (width) localStorage.setItem("ace-sidebar-width", width);
    });
    handle.addEventListener("dblclick", () => {
      document.documentElement.style.setProperty("--ace-sidebar-width", "360px");
      localStorage.setItem("ace-sidebar-width", 360);
    });
  })();

  updateUI();
})();
