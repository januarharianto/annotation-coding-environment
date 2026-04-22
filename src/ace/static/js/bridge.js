/**
 * ACE Bridge — client-side utilities for the coding page.
 *
 * Sections:
 *  2. Sentence navigation (↑/↓ focus)
 *  3. Group collapse / expand
 *  4. Keymap (dynamic keycap assignment)
 *  5. Apply code (sentence-based + custom selection)
 *  6. Keyboard shortcuts
 *  7. Navigation (prev/next source)
 *  8. Source grid overlay
 *  9. Cheat sheet overlay
 * 10. Resize handle
 * 11. Dialog close cleanup
 * 12. HTMX integration (configRequest, afterSwap, afterRequest)
 * 13. Code management helpers
 * 14. Code menu dropdown (with shortcut hints)
 * 15. Code search / filter / create / group
 * 16. SVG overlay — annotation rendering
 * 17. Sidebar keyboard navigation (ARIA treeview)
 * 18. DOMContentLoaded init
 * 19. Import form column-role assignment
 * 20. Codebook menu
 * 21. Source note drawer
 * 22. Source-grid collapse toggle
 */

(function () {
  "use strict";

  function _escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /* ================================================================
   * 2. Sentence navigation
   * ================================================================ */

  function _getSentences() {
    return document.querySelectorAll(".ace-sentence");
  }

  function _focusSentence(idx) {
    const sentences = _getSentences();
    if (idx < 0 || idx >= sentences.length) return;

    // Remove old focus
    const old = document.querySelector(".ace-sentence--focused");
    if (old) old.classList.remove("ace-sentence--focused");

    // Set new focus
    window.__aceFocusIndex = idx;
    let el = sentences[idx];
    el.classList.add("ace-sentence--focused");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function _restoreFocus() {
    // Delay until after HTMX settling completes (outerHTML swap replaces DOM)
    requestAnimationFrame(function () {
      // Don't steal focus from the note drawer textarea during autosave —
      // the save response swaps #text-panel but the textarea lives outside it.
      if (document.activeElement && document.activeElement.id === "note-textarea") return;
      const idx = window.__aceFocusIndex;
      if (idx >= 0) _focusSentence(idx);
      _focusTextPanel();
    });
  }

  /* ================================================================
   * 3. Group collapse / expand
   * ================================================================ */

  const _collapsedGroups = {};

  function _toggleGroupCollapse(header) {
    if (!header) return;
    const expanded = header.getAttribute("aria-expanded") === "true";
    if (expanded) {
      _collapseGroup(header);
    } else {
      _expandGroup(header);
    }
  }

  function _restoreCollapseState() {
    const headers = document.querySelectorAll(".ace-code-group-header");
    headers.forEach(function (header) {
      let groupName = header.getAttribute("data-group");
      if (_collapsedGroups[groupName]) {
        _collapseGroup(header);
      }
    });
  }

  // Click handler for group headers — toggle only on the triangle
  document.addEventListener("click", function (e) {
    const toggle = e.target.closest(".ace-group-toggle");
    if (toggle) {
      const header = toggle.closest(".ace-code-group-header");
      if (header) {
        _focusTreeItem(header);
        _toggleGroupCollapse(header);
        const groupName = header.getAttribute("data-group") || "Ungrouped";
        const expanded = header.getAttribute("aria-expanded") === "true";
        _announce(`Group ${groupName}${expanded ? " expanded" : " collapsed"}`);
      }
      return;
    }
    // Click on the label or header (not toggle) — just focus
    const header = e.target.closest(".ace-code-group-header");
    if (header && !e.target.closest(".ace-code-menu")) {
      _focusTreeItem(header);
    }
  });

  // Double-click on group label — inline rename
  document.addEventListener("dblclick", function (e) {
    const label = e.target.closest(".ace-group-label");
    if (!label) return;
    const header = label.closest(".ace-code-group-header");
    if (!header) return;
    const groupName = header.getAttribute("data-group");
    if (groupName === "") return; // Can't rename "Ungrouped"
    _startGroupRename(header);
  });

  // Sidebar: ? help button (delegated — survives OOB swaps)
  document.addEventListener("click", function (e) {
    if (e.target.closest("#sidebar-help-btn")) {
      _toggleCheatSheet();
    }
  });

  // Nav: flag toggle button (delegated — survives OOB swaps)
  let _pendingFlagAnnounce = false;
  document.addEventListener("click", function (e) {
    if (e.target.closest("#nav-flag-btn")) {
      _updateCurrentIndex();
      _pendingFlagAnnounce = true;
      const triggerFlag = document.getElementById("trigger-flag");
      if (triggerFlag) htmx.trigger(triggerFlag, "click");
    }
  });

  /* ================================================================
   * 4. Keymap — dynamic keycap assignment per tab
   * ================================================================ */

  let _currentKeyMap = []; // array of code IDs in keycap order

  function _updateKeycaps() {
    const tree = document.getElementById("code-tree");
    if (!tree) return;
    const rows = tree.querySelectorAll('.ace-code-row');
    _currentKeyMap = [];
    rows.forEach(function (row) {
      const groupDiv = row.closest('[role="group"]');
      if (groupDiv) {
        const header = groupDiv.previousElementSibling;
        if (header && header.getAttribute("aria-expanded") === "false") return;
      }
      // Also skip rows hidden by search filter
      if (row.style.display === "none") return;
      _currentKeyMap.push(row.getAttribute("data-code-id"));
      const keycap = row.querySelector(".ace-keycap");
      if (keycap) keycap.textContent = _keylabel(_currentKeyMap.length - 1);
      row.setAttribute("aria-keyshortcuts", _keylabel(_currentKeyMap.length - 1));
    });
  }

  // Reserved letters: q (repeat), x (delete), z (undo), n (open note panel)
  const _KEYCAP_LABELS = [
    "1","2","3","4","5","6","7","8","9","0",
    "a","b","c","d","e","f","g","h","i","j","k","l","m","o","p",
    "r","s","t","u","v","w","y"
  ];

  function _keylabel(i) {
    return i < _KEYCAP_LABELS.length ? _KEYCAP_LABELS[i] : "";
  }

  const _KEYCAP_POSITIONS = {};
  _KEYCAP_LABELS.forEach(function (label, i) { _KEYCAP_POSITIONS[label] = i; });

  function _keyToPosition(key) {
    const k = key.toLowerCase();
    const pos = _KEYCAP_POSITIONS[k];
    return pos !== undefined ? pos : -1;
  }

  /* ================================================================
   * 5. Apply code — uses parameter queue to avoid hx-sync race condition
   *
   * IMPORTANT: Do NOT use setAttribute("hx-vals") + htmx.trigger() on
   * shared hidden buttons. With hx-sync="this:queue all", queued requests
   * read hx-vals at execution time (not queue time), so rapid keypresses
   * overwrite each other's params. Instead, push params into a queue and
   * inject them via htmx:configRequest at request time.
   * ================================================================ */

  // Apply/delete use htmx.ajax() directly instead of hidden trigger buttons
  // to avoid issues with hx-sync queuing and param injection timing.

  function _applyCodeToSentence(codeId) {
    if (window.__aceExcerptListActive) return;
    if (window.__aceFocusIndex < 0) return;

    htmx.ajax("POST", "/api/code/apply-sentence", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: codeId,
        sentence_index: window.__aceFocusIndex,
        current_index: window.__aceCurrentIndex,
      },
    }).then(_restoreFocus);

    window.__aceLastCodeId = codeId;
    _flashCodeRow(codeId);
  }

  function _applyCodeToSelection(codeId) {
    const sel = window.__aceLastSelection;
    if (!sel) return;

    htmx.ajax("POST", "/api/code/apply", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        code_id: codeId,
        start_offset: sel.start,
        end_offset: sel.end,
        selected_text: sel.text,
        current_index: window.__aceCurrentIndex,
      },
    }).then(_restoreFocus);

    window.__aceLastCodeId = codeId;
    window.__aceLastSelection = null;
    window.getSelection().removeAllRanges();
    _flashCodeRow(codeId);
  }

  function _deleteSentenceAnnotation() {
    if (window.__aceFocusIndex < 0) return;

    htmx.ajax("POST", "/api/code/delete-sentence", {
      target: "#text-panel",
      swap: "outerHTML",
      values: {
        sentence_index: window.__aceFocusIndex,
        current_index: window.__aceCurrentIndex,
      },
    }).then(_restoreFocus);
  }

  function _flashCodeRow(codeId) {
    document.querySelectorAll(`.ace-code-row[data-code-id="${codeId}"]`).forEach(function (r) {
      r.classList.add("ace-code-row--flash");
      setTimeout(function () { r.classList.remove("ace-code-row--flash"); }, 300);
    });
  }

  /* ================================================================
   * 6. Keyboard shortcuts
   * ================================================================ */

  // Custom selection tracking (for click-drag)
  window.__aceLastSelection = null;

  function _isTyping() {
    let el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  document.addEventListener("keydown", function (e) {
    if (_isTyping()) return;
    if (_menuOpen) return;

    // Only handle keys when text panel (or nothing specific) is focused
    let zone = _activeZone();
    if (zone === "search" || zone === "tree") return;

    const key = e.key;
    const ctrl = e.ctrlKey || e.metaKey;
    const shift = e.shiftKey;

    // Ctrl/Cmd+Shift+Z — Redo
    if (ctrl && shift && key === "Z") {
      e.preventDefault();
      _updateCurrentIndex();
      const redoBtn = document.getElementById("trigger-redo");
      if (redoBtn) htmx.trigger(redoBtn, "click");
      return;
    }

    // Ctrl/Cmd+Z — Undo
    if (ctrl && !shift && (key === "z" || key === "Z")) {
      e.preventDefault();
      _updateCurrentIndex();
      const undoBtn = document.getElementById("trigger-undo");
      if (undoBtn) htmx.trigger(undoBtn, "click");
      return;
    }

    // Skip remaining if modifier keys held
    if (ctrl || e.altKey) return;

    // ↓ — Navigate to next sentence (or focus first if none focused)
    if (key === "ArrowDown") {
      e.preventDefault();
      const sentences = _getSentences();
      if (sentences.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(0);
      } else if (window.__aceFocusIndex < sentences.length - 1) {
        _focusSentence(window.__aceFocusIndex + 1);
      }
      return;
    }

    // ↑ — Navigate to previous sentence (or focus last if none focused)
    if (key === "ArrowUp") {
      e.preventDefault();
      const sentencesUp = _getSentences();
      if (sentencesUp.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(sentencesUp.length - 1);
      } else if (window.__aceFocusIndex > 0) {
        _focusSentence(window.__aceFocusIndex - 1);
      }
      return;
    }

    // Shift+← / Shift+→ — Navigate between sources
    if (key === "ArrowLeft" && shift) {
      e.preventDefault();
      window.aceNavigate(window.__aceCurrentIndex - 1);
      return;
    }
    if (key === "ArrowRight" && shift) {
      e.preventDefault();
      window.aceNavigate(window.__aceCurrentIndex + 1);
      return;
    }

    // ← / → (unmodified) — Aliases for ↑ / ↓ when reading. Text panel has no
    // character cursor, so the horizontal arrows are free. "Forward / back"
    // reads more naturally than strict "up / down" for sequential content.
    if (key === "ArrowRight" && !shift) {
      e.preventDefault();
      const sentencesR = _getSentences();
      if (sentencesR.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(0);
      } else if (window.__aceFocusIndex < sentencesR.length - 1) {
        _focusSentence(window.__aceFocusIndex + 1);
      }
      return;
    }
    if (key === "ArrowLeft" && !shift) {
      e.preventDefault();
      const sentencesL = _getSentences();
      if (sentencesL.length === 0) return;
      if (window.__aceFocusIndex < 0) {
        _focusSentence(sentencesL.length - 1);
      } else if (window.__aceFocusIndex > 0) {
        _focusSentence(window.__aceFocusIndex - 1);
      }
      return;
    }

    // Z — Undo (no modifier needed in sentence mode)
    if ((key === "z" || key === "Z") && !ctrl) {
      e.preventDefault();
      _updateCurrentIndex();
      const undoBtn2 = document.getElementById("trigger-undo");
      if (undoBtn2) htmx.trigger(undoBtn2, "click");
      return;
    }

    // Q — Repeat last code
    if (key === "q" || key === "Q") {
      e.preventDefault();
      if (window.__aceLastCodeId && window.__aceFocusIndex >= 0) {
        if (window.__aceLastSelection) {
          _applyCodeToSelection(window.__aceLastCodeId);
        } else {
          _applyCodeToSentence(window.__aceLastCodeId);
        }
      }
      return;
    }

    // X — Delete annotation on focused sentence
    if (key === "x" || key === "X") {
      e.preventDefault();
      _deleteSentenceAnnotation();
      return;
    }

    // F — Flag (Shift+F)
    if (key === "F" && shift) {
      e.preventDefault();
      _updateCurrentIndex();
      const flagBtn = document.getElementById("trigger-flag");
      if (flagBtn) htmx.trigger(flagBtn, "click");
      return;
    }

    // N — open note drawer (read mode) or enter edit mode if already open
    if ((key === "n" || key === "N") && !shift) {
      e.preventDefault();
      if (!_isDrawerOpen()) {
        aceOpenNoteRead();
      } else {
        aceEnterEditMode();
      }
      return;
    }

    // ? — Toggle cheat sheet
    if (key === "?" || (shift && key === "/")) {
      e.preventDefault();
      _toggleCheatSheet();
      return;
    }

    // Escape cascade
    if (key === "Escape") {
      const cheatSheet = document.getElementById("ace-cheat-sheet");
      if (cheatSheet) { cheatSheet.remove(); return; }

      const dialog = document.querySelector("dialog[open]");
      if (dialog) { dialog.close(); return; }

      // Clear custom selection
      if (window.__aceLastSelection) {
        window.__aceLastSelection = null;
        window.getSelection().removeAllRanges();
      }
      return;
    }

    // / — Jump to sidebar search bar
    if (key === "/" && !shift) {
      e.preventDefault();
      _focusSearchBar();
      return;
    }

    // 1-9, 0, a-z — Apply code at keymap position
    // Guard: only single-character keys (skip ArrowLeft, ArrowRight, etc.)
    if (!shift && key.length === 1) {
      const pos = _keyToPosition(key);
      if (pos >= 0 && pos < _currentKeyMap.length) {
        e.preventDefault();
        let codeId = _currentKeyMap[pos];
        if (window.__aceLastSelection) {
          _applyCodeToSelection(codeId);
        } else if (window.__aceFocusIndex >= 0) {
          _applyCodeToSentence(codeId);
        } else {
          // Auto-focus first sentence if none focused
          _focusSentence(0);
          _applyCodeToSentence(codeId);
        }
      }
    }
  });

  function _updateCurrentIndex() {
    const input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
  }

  /* ================================================================
   * 7. Navigation
   * ================================================================ */

  window.aceNavigate = async function (index) {
    if (!Number.isFinite(index) || index < 0 || index >= window.__aceTotalSources) return;
    // Flush any pending or in-flight note save before tearing down the page.
    // Without this, debounced saves get cancelled by the navigation.
    if (typeof aceFlushNoteIfDirty === "function") {
      try { await aceFlushNoteIfDirty(); } catch (_) {}
    }
    window.__aceCurrentIndex = index;
    window.__aceFocusIndex = -1;
    _setAmbient();
    window.location.href = `/code?index=${index}`;
  };

  window.aceNavigatePrev = function () {
    window.aceNavigate(window.__aceCurrentIndex - 1);
  };

  window.aceNavigateNext = function () {
    window.aceNavigate(window.__aceCurrentIndex + 1);
  };

  /* ================================================================
   * 8. Cheat sheet overlay
   * ================================================================ */

  function _toggleCheatSheet() {
    const existing = document.getElementById("ace-cheat-sheet");
    if (existing) { existing.remove(); return; }

    const overlay = document.createElement("div");
    overlay.id = "ace-cheat-sheet";
    overlay.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.45);";

    const card = document.createElement("div");
    card.style.cssText = "background:var(--ace-bg,#fff);border:1px solid var(--ace-border,#bdbdbd);padding:24px 32px;max-width:520px;width:90%;max-height:80vh;overflow-y:auto;font-size:13px;line-height:1.6;";

    card.innerHTML =
      '<h3 style="margin:0 0 12px;font-size:15px;font-weight:600;">Keyboard shortcuts</h3>' +
      '<table style="width:100%;border-collapse:collapse;">' +
      _shortcutRow("↑ / ↓", "Navigate sentences") +
      _shortcutRow("Shift + ← / →", "Previous / next source") +
      _shortcutRow("1 – 9, 0, a–y (not q x z n)", "Apply code") +
      _shortcutRow("Q", "Repeat last code") +
      _shortcutRow("X", "Remove code from sentence") +
      _shortcutRow("Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Shift + Z", "Redo") +
      _shortcutRow("Shift + F", "Flag/unflag source") +
      _shortcutRow("N", "Open / close note panel") +
      _shortcutRow("F2", "Rename code (in sidebar)") +
      _shortcutRow("Delete", "Delete code (in sidebar, press twice)") +
      _shortcutRow("?", "Toggle this cheat sheet") +
      _shortcutRow("Esc", "Close overlay / clear") +
      "</table>";

    overlay.appendChild(card);
    document.body.appendChild(overlay);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) overlay.remove();
    });
  }

  function _shortcutRow(key, desc) {
    return `<tr style="border-bottom:1px solid var(--ace-border-light,#e0e0e0);"><td style="padding:4px 12px 4px 0;font-family:'SF Mono',Menlo,Consolas,monospace;font-size:12px;white-space:nowrap;color:var(--ace-text-muted,#777);">${key}</td><td style="padding:4px 0;">${desc}</td></tr>`;
  }

  /* ================================================================
   * 10. Resize handle
   * ================================================================ */

  function _initResize() {
    const handle = document.getElementById("resize-handle");
    if (!handle) return;
    const split = handle.closest(".ace-three-col");
    if (!split) return;

    let dragging = false;

    handle.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      dragging = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      const rect = split.getBoundingClientRect();
      let x = e.clientX - rect.left;
      const min = 150;
      const max = rect.width * 0.4;
      x = Math.max(min, Math.min(max, x));
      document.documentElement.style.setProperty("--ace-sidebar-width", `${x}px`);
    });

    document.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      const width = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--ace-sidebar-width"), 10);
      if (width) localStorage.setItem("ace-sidebar-width", width);
    });

    handle.addEventListener("dblclick", function () {
      document.documentElement.style.setProperty("--ace-sidebar-width", "360px");
      localStorage.setItem("ace-sidebar-width", 360);
    });
  }

  function _initGridResize() {
    const handle = document.querySelector(".ace-sidebar-vsplit");
    if (!handle || handle.dataset.aceResizeWired) return;
    handle.dataset.aceResizeWired = "1";

    const DEFAULT_VH = 35;
    const MIN_VH = 10;
    const MAX_VH = 70;
    const KEY_STEP_PX = 8;

    function _vhToPx(vh) { return (window.innerHeight * vh) / 100; }
    function _pxToVh(px) { return (px / window.innerHeight) * 100; }
    function _clampVh(v) { return Math.max(MIN_VH, Math.min(MAX_VH, v)); }

    function _setValue(vh) {
      const clamped = _clampVh(vh);
      document.documentElement.style.setProperty("--ace-grid-height", clamped.toFixed(2) + "vh");
      const rounded = Math.round(clamped);
      handle.setAttribute("aria-valuenow", rounded.toString());
      handle.setAttribute("aria-valuetext", rounded + " percent of viewport height");
      return clamped;
    }

    function _persist(vh) {
      try { localStorage.setItem("ace-grid-height", vh.toFixed(2) + "vh"); } catch (_) {}
    }

    function _currentVh() {
      const computed = getComputedStyle(document.documentElement)
        .getPropertyValue("--ace-grid-height").trim();
      return parseFloat(computed) || DEFAULT_VH;
    }

    // Sync ARIA state with the actual computed starting height — catches
    // values restored from localStorage before the first user interaction.
    _setValue(_currentVh());

    // Pointer drag — all listeners on the handle, with setPointerCapture,
    // so they die cleanly with the subtree when #code-sidebar is replaced
    // by an OOB swap (no document-level listener leak).
    let dragging = false;
    let startY = 0;
    let startVh = DEFAULT_VH;

    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      dragging = true;
      startY = e.clientY;
      startVh = _currentVh();
      handle.setPointerCapture(e.pointerId);
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    handle.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      const dy = startY - e.clientY; // dragging up grows the panel
      const newVh = _pxToVh(_vhToPx(startVh) + dy);
      _setValue(newVh);
    });

    function _endDrag(e) {
      if (!dragging) return;
      dragging = false;
      document.body.style.userSelect = "";
      if (e && typeof e.pointerId === "number" && handle.hasPointerCapture(e.pointerId)) {
        handle.releasePointerCapture(e.pointerId);
      }
      _persist(_clampVh(_currentVh()));
    }

    handle.addEventListener("pointerup", _endDrag);
    handle.addEventListener("pointercancel", _endDrag);

    // Double-click reset
    handle.addEventListener("dblclick", function () {
      document.documentElement.style.removeProperty("--ace-grid-height");
      handle.setAttribute("aria-valuenow", DEFAULT_VH.toString());
      handle.setAttribute("aria-valuetext", DEFAULT_VH + " percent of viewport height");
      try { localStorage.removeItem("ace-grid-height"); } catch (_) {}
    });

    // Keyboard resize
    handle.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      const deltaPx = (e.key === "ArrowUp" ? 1 : -1) * KEY_STEP_PX;
      const newVh = _pxToVh(_vhToPx(_currentVh()) + deltaPx);
      const clamped = _setValue(newVh);
      _persist(clamped);
      e.preventDefault();
    });
  }

  // ==========================================================
  // Source-grid renderer: sparkline minimap + tile viewport
  // ==========================================================

  let _aceSourceGridState = {
    sources: [],
    windowStart: 0,
    visibleCount: 0,
    resizeObs: null,
    hoveredIndex: -1, // -1 means "no hover; show active"
    lastActive: -1,   // last rendered active index; used to decide whether to
                      // auto-centre the viewport (only on active-source change,
                      // so sparkline clicks to a distant range aren't snapped back)
  };

  function _aceInspectorLine(src) {
    if (!src) return "";
    const n = src.index + 1;
    const flags = [];
    if (src.flagged) flags.push("flagged");
    if (src.note)    flags.push("has note");
    const plural = src.count === 1 ? "" : "s";
    const parts = [
      "#" + n,
      src.display_id,
      src.count + " annotation" + plural,
    ];
    if (flags.length) parts.push(flags.join(" · "));
    return parts.join(" · ");
  }

  function _aceUpdateInspector() {
    const el = document.getElementById("ace-grid-inspector");
    if (!el) return;
    const st = _aceSourceGridState;
    let src = null;
    if (st.hoveredIndex >= 0 && st.hoveredIndex < st.sources.length) {
      src = st.sources[st.hoveredIndex];
    } else if (typeof window.__aceCurrentIndex === "number" &&
               window.__aceCurrentIndex >= 0 &&
               window.__aceCurrentIndex < st.sources.length) {
      src = st.sources[window.__aceCurrentIndex];
    }
    el.textContent = _aceInspectorLine(src);
  }

  function _aceRenderTiles() {
    const host = document.getElementById("ace-grid-tiles");
    const label = document.getElementById("ace-grid-range-label");
    if (!host) return;
    const st = _aceSourceGridState;
    const active = typeof window.__aceCurrentIndex === "number"
      ? window.__aceCurrentIndex : 0;

    // Compute visible count from the CONTENT box (exclude padding) so the
    // math matches CSS `repeat(auto-fill, 22px)` — otherwise we overcount
    // columns by ~1 and the extra tiles spill into a row that gets clipped
    // by `overflow: hidden`.
    const cs = getComputedStyle(host);
    const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const padY = parseFloat(cs.paddingTop)  + parseFloat(cs.paddingBottom);
    const rect = host.getBoundingClientRect();
    const contentW = Math.max(0, rect.width  - padX);
    const contentH = Math.max(0, rect.height - padY);
    const TILE = 22, GAP = 2;
    const cols = Math.max(1, Math.floor((contentW + GAP) / (TILE + GAP)));
    const rows = Math.max(1, Math.floor((contentH + GAP) / (TILE + GAP)));
    st.visibleCount = Math.min(st.sources.length, cols * rows);

    // Auto-centre on active ONLY when the active source has changed since
    // the previous render (i.e. real navigation). Otherwise respect
    // st.windowStart so sparkline clicks to a far range aren't snapped back.
    if (active !== st.lastActive &&
        (active < st.windowStart ||
         active >= st.windowStart + st.visibleCount)) {
      st.windowStart = Math.max(0, Math.min(
        st.sources.length - st.visibleCount,
        active - Math.floor(st.visibleCount / 2),
      ));
    }
    // Always clamp so windowStart stays in valid range (e.g. after resize).
    st.windowStart = Math.max(0, Math.min(
      st.windowStart, Math.max(0, st.sources.length - st.visibleCount),
    ));
    st.lastActive = active;

    const from = st.windowStart;
    const to   = Math.min(st.sources.length, from + st.visibleCount);

    if (label) {
      label.textContent = "Sources " + (from + 1) + "–" + to +
        " of " + st.sources.length;
    }

    const frag = document.createDocumentFragment();
    for (let i = from; i < to; i++) {
      const s = st.sources[i];
      const cls = ["ace-grid-tile"];
      if (s.count >= 6) cls.push("hot");
      else if (s.count >= 3) cls.push("warm");
      if (i === active)  cls.push("active");
      if (s.flagged)     cls.push("flagged");
      if (s.note)        cls.push("note");

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = cls.join(" ");
      btn.setAttribute("role", "gridcell");
      btn.dataset.sourceIndex = String(i);
      btn.dataset.count = String(s.count);
      btn.tabIndex = (i === active) ? 0 : -1;
      if (i === active) btn.setAttribute("aria-current", "location");
      btn.title = "#" + (i + 1) + " · " + s.display_id +
        " · " + s.count + " annotation" + (s.count === 1 ? "" : "s");

      const span = document.createElement("span");
      span.textContent = String(s.count);
      btn.appendChild(span);

      btn.addEventListener("click", function () {
        if (typeof window.aceNavigate === "function") {
          window.aceNavigate(i);
        }
      });
      btn.addEventListener("mouseenter", function () {
        _aceSourceGridState.hoveredIndex = i;
        _aceUpdateInspector();
      });
      btn.addEventListener("focus", function () {
        _aceSourceGridState.hoveredIndex = i;
        _aceUpdateInspector();
      });

      frag.appendChild(btn);
    }
    host.replaceChildren(frag);

    // Mouse leaving the tile grid clears hover → inspector falls back to active
    if (!host.dataset.aceMouseleaveWired) {
      host.addEventListener("mouseleave", function () {
        _aceSourceGridState.hoveredIndex = -1;
        _aceUpdateInspector();
      });
      host.dataset.aceMouseleaveWired = "1";
    }

    _aceUpdateInspector();
  }

  function _aceRenderSparkline() {
    const host = document.getElementById("ace-grid-spark");
    if (!host) return;
    const st = _aceSourceGridState;
    const total = st.sources.length;
    if (total === 0) { host.replaceChildren(); return; }

    const W = host.clientWidth || 240;
    const H = 38;
    const padX = 2;
    const innerW = Math.max(1, W - 2 * padX);

    const nPoints = Math.max(40, Math.min(160, Math.floor(innerW / 4)));
    let maxCount = 1;
    for (let k = 0; k < total; k++) {
      if (st.sources[k].count > maxCount) maxCount = st.sources[k].count;
    }

    // Linear interpolation over source counts using the same X mapping the
    // playhead uses (t = i/(nPoints-1), pos = t*(total-1)). This keeps
    // density peaks aligned with source positions for any total.
    const density = new Array(nPoints);
    const span = Math.max(0, total - 1);
    for (let i = 0; i < nPoints; i++) {
      const t = nPoints === 1 ? 0 : i / (nPoints - 1);
      const pos = t * span;
      const lo = Math.floor(pos);
      const hi = Math.min(total - 1, lo + 1);
      const frac = pos - lo;
      density[i] = st.sources[lo].count * (1 - frac) +
                   st.sources[hi].count * frac;
    }

    const pts = density.map(function (d, i) {
      const x = padX + (nPoints === 1 ? 0 : (i / (nPoints - 1)) * innerW);
      const y = H - (d / maxCount) * (H - 4) - 2;
      return [x, y];
    });
    const line = "M" + pts.map(function (p) {
      return p[0].toFixed(1) + "," + p[1].toFixed(1);
    }).join(" L");
    const area = line + " L" + (W - padX).toFixed(1) + "," + H +
                        " L" + padX.toFixed(1) + "," + H + " Z";

    const denom = Math.max(1, total - 1);
    const vpX1 = padX + (st.windowStart / denom) * innerW;
    const vpEnd = Math.min(total, st.windowStart + st.visibleCount) - 1;
    const vpX2 = padX + (Math.max(vpEnd, 0) / denom) * innerW;
    const vpW  = Math.max(6, vpX2 - vpX1);
    const active = typeof window.__aceCurrentIndex === "number"
      ? window.__aceCurrentIndex : 0;
    const playX = padX + (active / denom) * innerW;

    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + (H + 4));
    svg.setAttribute("preserveAspectRatio", "none");

    function mk(tag, attrs) {
      const el = document.createElementNS(NS, tag);
      for (const k in attrs) el.setAttribute(k, attrs[k]);
      return el;
    }
    svg.appendChild(mk("path", { class: "spark-area", d: area }));
    svg.appendChild(mk("path", { class: "spark-line", d: line }));
    svg.appendChild(mk("rect", {
      class: "spark-viewport",
      x: vpX1.toFixed(1), y: 0,
      width: vpW.toFixed(1), height: H,
    }));
    svg.appendChild(mk("line", {
      class: "spark-playhead",
      x1: playX, x2: playX, y1: 0, y2: H,
    }));
    svg.appendChild(mk("circle", {
      class: "spark-playhead-cap",
      cx: playX, cy: H + 2, r: 2,
    }));

    svg.addEventListener("click", function (ev) {
      const r = svg.getBoundingClientRect();
      const x = ev.clientX - r.left;
      const normalised = (x - padX) / innerW;
      const idx = Math.round(Math.max(0, Math.min(1, normalised)) * denom);
      _aceSourceGridState.windowStart = Math.max(0, Math.min(
        total - _aceSourceGridState.visibleCount,
        idx - Math.floor(_aceSourceGridState.visibleCount / 2),
      ));
      _aceRenderSparkline();
      _aceRenderTiles();
    });

    host.replaceChildren(svg);
  }

  function _aceTileCols() {
    const host = document.getElementById("ace-grid-tiles");
    if (!host) return 1;
    const cs = getComputedStyle(host);
    const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const rect = host.getBoundingClientRect();
    const contentW = Math.max(0, rect.width - padX);
    const TILE = 22, GAP = 2;
    return Math.max(1, Math.floor((contentW + GAP) / (TILE + GAP)));
  }

  function _aceNavigateFocus(targetIndex) {
    const st = _aceSourceGridState;
    const total = st.sources.length;
    if (total === 0) return;
    targetIndex = Math.max(0, Math.min(total - 1, targetIndex));

    // Shift window if target is outside; center on target
    if (targetIndex < st.windowStart ||
        targetIndex >= st.windowStart + st.visibleCount) {
      st.windowStart = Math.max(0, Math.min(
        total - st.visibleCount,
        targetIndex - Math.floor(st.visibleCount / 2),
      ));
      _aceRenderTiles();
      _aceRenderSparkline();
    }

    // Focus the destination tile
    const host = document.getElementById("ace-grid-tiles");
    if (!host) return;
    const btn = host.querySelector(
      '[data-source-index="' + targetIndex + '"]');
    if (btn) {
      host.querySelectorAll('.ace-grid-tile').forEach(function (t) {
        t.tabIndex = -1;
      });
      btn.tabIndex = 0;
      btn.focus();
      _aceSourceGridState.hoveredIndex = targetIndex;
      _aceUpdateInspector();
    }
  }

  function _aceInitTileKeyboard() {
    const host = document.getElementById("ace-grid-tiles");
    if (!host || host.dataset.aceKbdWired) return;
    host.dataset.aceKbdWired = "1";

    host.addEventListener("keydown", function (e) {
      const target = e.target.closest(".ace-grid-tile");
      if (!target) return;
      const idx = parseInt(target.dataset.sourceIndex, 10);
      if (Number.isNaN(idx)) return;
      const st = _aceSourceGridState;
      const cols = _aceTileCols();
      const total = st.sources.length;

      let dest = null;
      switch (e.key) {
        case "ArrowLeft":  dest = idx - 1; break;
        case "ArrowRight": dest = idx + 1; break;
        case "ArrowUp":    dest = idx - cols; break;
        case "ArrowDown":  dest = idx + cols; break;
        case "Home":       dest = 0; break;
        case "End":        dest = total - 1; break;
        case "PageUp":     dest = idx - Math.max(cols, st.visibleCount); break;
        case "PageDown":   dest = idx + Math.max(cols, st.visibleCount); break;
        case "Enter":
        case " ": {
          if (typeof window.aceNavigate === "function") {
            window.aceNavigate(idx);
          }
          e.preventDefault();
          return;
        }
        case "Escape": {
          const panel = document.querySelector(".ace-text-panel");
          if (panel) panel.focus();
          e.preventDefault();
          return;
        }
        default:
          return;
      }

      // Clamp to valid range; _aceNavigateFocus also clamps but do it here too
      // so we can tell "key consumed" vs "already at target".
      const clamped = Math.max(0, Math.min(total - 1, dest));
      if (clamped !== idx) {
        _aceNavigateFocus(clamped);
      }
      e.preventDefault();
    });
  }

  window._aceRenderSourceGrid = function () {
    const blob = document.getElementById("ace-sources-data");
    if (!blob) return;
    try {
      _aceSourceGridState.sources = JSON.parse(blob.textContent || "[]");
    } catch (e) {
      _aceSourceGridState.sources = [];
    }
    // HTMX sidebar swaps (e.g. after code CRUD) detach the old tile host,
    // so the existing observer would point at a dead node. Re-observe the
    // current host on every call to stay pointed at live DOM.
    const tiles = document.getElementById("ace-grid-tiles");
    if (_aceSourceGridState.resizeObs) {
      _aceSourceGridState.resizeObs.disconnect();
    }
    if (tiles) {
      _aceSourceGridState.resizeObs = new ResizeObserver(function () {
        _aceRenderTiles();
        _aceRenderSparkline();
      });
      _aceSourceGridState.resizeObs.observe(tiles);
    }
    _aceRenderTiles();
    _aceRenderSparkline();
    _aceInitTileKeyboard();
  };

  /* ================================================================
   * 11. Dialog close cleanup
   * ================================================================ */

  document.addEventListener("close", function (evt) {
    if (evt.target.tagName === "DIALOG") {
      const container = document.getElementById("modal-container");
      if (container) container.innerHTML = "";
    }
  }, true);

  /* ================================================================
   * 12. HTMX integration
   * ================================================================ */

  // Custom selection capture (for click-drag)
  // Uses data-start/data-end attributes on sentence spans to compute
  // source-text offsets (DOM offsets differ due to inter-span whitespace).
  document.addEventListener("mouseup", function () {
    const container = document.querySelector(".ace-text-panel");
    if (!container) return;

    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      window.__aceLastSelection = null;
      return;
    }

    const range = sel.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      return;
    }

    const text = sel.toString();
    if (!text) { window.__aceLastSelection = null; return; }

    // Find the sentence spans containing the selection endpoints
    const startSrc = _sourceOffset(range.startContainer, range.startOffset);
    const endSrc = _sourceOffset(range.endContainer, range.endOffset);

    if (startSrc < 0 || endSrc < 0 || startSrc === endSrc) {
      window.__aceLastSelection = null;
      return;
    }

    window.__aceLastSelection = { start: startSrc, end: endSrc, text: text };
  });

  function _sourceOffset(node, domOffset) {
    // Walk up to find the containing .ace-sentence span
    let el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    let sentence = el.closest(".ace-sentence");
    if (!sentence) return -1;

    const sentStart = parseInt(sentence.dataset.start, 10);
    if (isNaN(sentStart)) return -1;

    // Compute character offset within this sentence's text content
    const walker = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
    let charPos = 0;
    let current;
    while ((current = walker.nextNode())) {
      if (current === node) return sentStart + charPos + domOffset;
      charPos += current.textContent.length;
    }
    // Fallback: if node is the sentence element itself, use domOffset as child index
    return sentStart + domOffset;
  }

  // Click on sentence to focus it
  document.addEventListener("click", function (e) {
    let sentence = e.target.closest(".ace-sentence");
    if (sentence) {
      const idx = parseInt(sentence.dataset.idx, 10);
      if (!isNaN(idx)) {
        _focusSentence(idx);
        // Clear custom selection if this was a simple click (not drag)
        if (!window.__aceLastSelection) {
          window.getSelection().removeAllRanges();
        }
      }
    }

    // Click on code chip to flash highlights in current source
    const chip = e.target.closest(".ace-code-chip");
    if (chip) {
      const codeId = chip.dataset.codeId;
      const body = document.querySelector(".ace-text-body");
      const svg = document.getElementById("ace-hl-overlay");
      if (!body || !svg) return;
      const dataEl = document.getElementById("ace-ann-data");
      if (!dataEl) return;
      const matching = JSON.parse(dataEl.dataset.annotations || "[]")
        .filter(function (a) { return a.code_id === codeId; });
      if (!matching.length) return;

      // Cancel any pending flash cleanup from a previous click so rapid
      // chip clicks don't wipe the newest flash rects prematurely.
      if (_flashTimeout) {
        clearTimeout(_flashTimeout);
        _flashTimeout = null;
      }

      // Clear any previous flash rects
      svg.querySelectorAll("rect.ace-flash").forEach(function (el) { el.remove(); });

      const overlayRect = svg.getBoundingClientRect();
      let firstRange = null;

      // Build the text index ONCE for all matching annotations — O(N+M).
      const textIndex = _buildTextIndex(body);
      if (!textIndex.length) return;

      const paraBreakRects = _paraBreakRects(body);

      for (const ann of matching) {
        const startPos = _findDOMPosition(textIndex, ann.start);
        const endPos = _findDOMPosition(textIndex, ann.end);
        if (!startPos || !endPos) continue;
        let range;
        try {
          range = new Range();
          range.setStart(startPos.node, startPos.offset);
          range.setEnd(endPos.node, endPos.offset);
        } catch (e) {
          continue;
        }
        if (!firstRange) firstRange = range;
        for (const line of _mergeRectsByLine(range.getClientRects(), paraBreakRects)) {
          const x = Math.floor(line.left - overlayRect.left);
          const y = Math.floor(line.top - overlayRect.top);
          const right = Math.ceil(line.right - overlayRect.left);
          const bottom = Math.ceil(line.bottom - overlayRect.top);
          const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          el.setAttribute("class", "ace-flash ace-flash-" + codeId);
          el.setAttribute("x", x);
          el.setAttribute("y", y);
          el.setAttribute("width", right - x);
          el.setAttribute("height", bottom - y);
          svg.appendChild(el);
        }
      }

      // Preserve existing scroll-into-view behaviour
      if (firstRange) {
        const startEl = firstRange.startContainer.parentElement;
        if (startEl) startEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      // Auto-clear all flash rects after 1500ms. Timeout handle is module-level
      // so the next click can cancel it before scheduling a new cleanup.
      _flashTimeout = setTimeout(function () {
        svg.querySelectorAll("rect.ace-flash").forEach(function (el) { el.remove(); });
        _flashTimeout = null;
      }, 1500);
      return;
    }
  });

  // Click on excerpt card to navigate to that source + highlight
  document.addEventListener("click", function(e) {
    const card = e.target.closest(".ace-excerpt-card");
    if (!card) return;
    const sourceIndex = card.getAttribute("data-source-index");
    const startOffset = card.getAttribute("data-start-offset");
    if (sourceIndex !== null) {
      window.location.href = `/code?index=${sourceIndex}&highlight=${startOffset}`;
    }
  });

  // Click on back button to return from excerpt list
  document.addEventListener("click", function(e) {
    if (!e.target.closest(".ace-excerpt-back")) return;
    const idx = window.__aceExcerptReturnIndex;
    if (idx !== undefined && idx !== null) {
      window.aceNavigate(idx);
    }
  });

  // --- Focus restoration across HTMX swaps ---

  const _sidebarFocusState = {
    codeId: null,
    groupName: null,
    searchText: "",
    scrollTop: 0,
    zone: null,
  };

  document.addEventListener("htmx:beforeSwap", function (e) {
    const target = e.detail.target;
    if (!target) return;
    if (target.id !== "code-sidebar" && target.id !== "coding-workspace" && target.id !== "text-panel") return;

    let zone = _activeZone();
    _sidebarFocusState.zone = zone;

    if (zone === "tree") {
      const active = _getActiveTreeItem();
      _sidebarFocusState.codeId = active ? active.getAttribute("data-code-id") : null;
      _sidebarFocusState.groupName = active ? active.getAttribute("data-group") : null;
    }

    let search = document.getElementById("code-search-input");
    _sidebarFocusState.searchText = search ? search.value : "";

    const tree = document.getElementById("code-tree");
    _sidebarFocusState.scrollTop = tree ? tree.scrollTop : 0;
  });

  // After HTMX swap: restore focus, rebuild tabs, update keycaps
  // Use afterSettle (not afterSwap) — fires after HTMX finishes all DOM changes
  document.addEventListener("htmx:afterSettle", function (evt) {
    const target = evt.detail.target;
    if (!target) return;

    if (target.id === "text-panel" || target.id === "coding-workspace") {
      window.__aceExcerptListActive = false;
      _restoreFocus();
      _paintSvg();

      // Full OOB responses (flag, navigate) also replace the sidebar —
      // restore sidebar state here since afterSettle only fires for the
      // primary target, not OOB targets.
      if (document.getElementById("code-tree")) {
        _restoreCollapseState();
        _updateKeycaps();
        _initGridResize();
      }
      // Re-render the source grid if its data blob is in the swapped DOM.
      // Primary swaps don't fire htmx:oobAfterSwap, so without this the
      // grid would stay empty after a sidebar swap that replaced the hosts.
      if (document.getElementById("ace-sources-data") &&
          typeof window._aceRenderSourceGrid === "function") {
        window._aceRenderSourceGrid();
      }

      // Announce flag state and restore focus after flag toggle
      if (_pendingFlagAnnounce) {
        _pendingFlagAnnounce = false;
        const flagBtn = document.getElementById("nav-flag-btn");
        if (flagBtn) {
          const pressed = flagBtn.getAttribute("aria-pressed") === "true";
          _announce(pressed ? "Source flagged" : "Source unflagged");
          flagBtn.focus();
        }
      }
    }

    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      if (!_isDragging) _initSortable();
      _restoreCollapseState();
      _updateKeycaps();
      _initGridResize();

      // Re-render source grid after sidebar swap (code CRUD / reorder) —
      // primary swaps replace #ace-grid-tiles + #ace-sources-data but
      // don't fire htmx:oobAfterSwap, so bind the renderer here.
      if (document.getElementById("ace-sources-data") &&
          typeof window._aceRenderSourceGrid === "function") {
        window._aceRenderSourceGrid();
      }

      // Restore focus state
      let search = document.getElementById("code-search-input");
      if (_sidebarFocusState.searchText && search) {
        search.value = _sidebarFocusState.searchText;
        search.dispatchEvent(new Event("input", { bubbles: true }));
      }

      const tree = document.getElementById("code-tree");
      if (tree && _sidebarFocusState.scrollTop) {
        tree.scrollTop = _sidebarFocusState.scrollTop;
      }

      if (_sidebarFocusState.zone === "tree") {
        let item = null;
        if (_sidebarFocusState.codeId && tree) {
          item = tree.querySelector(`[data-code-id="${_sidebarFocusState.codeId}"]`);
        } else if (_sidebarFocusState.groupName !== null && tree) {
          item = tree.querySelector(`.ace-code-group-header[data-group="${_sidebarFocusState.groupName}"]`);
        }
        if (item) {
          _focusTreeItem(item);
        } else {
          const items = _getTreeItems();
          if (items.length > 0) _focusTreeItem(items[0]);
        }
      } else if (_sidebarFocusState.zone === "search" && search) {
        search.focus();
      }

      // Reset sidebar state
      _sidebarFocusState.codeId = null;
      _sidebarFocusState.groupName = null;
      _sidebarFocusState.searchText = "";
      _sidebarFocusState.zone = null;
    }

    // Auto-open dialogs
    if (target.id === "modal-container") {
      const dialog = target.querySelector("dialog");
      if (dialog && !dialog.open) dialog.showModal();
    }
  });

  // Inject current_index into undo/redo/flag hidden trigger requests
  document.addEventListener("htmx:configRequest", function (e) {
    const elt = e.detail.elt;
    if (!elt || !elt.id) return;

    if (["trigger-undo", "trigger-redo", "trigger-flag"].indexOf(elt.id) >= 0) {
      e.detail.parameters.current_index = window.__aceCurrentIndex;
    }
    if (elt.id === "trigger-flag") {
      e.detail.parameters.source_index = window.__aceCurrentIndex;
    }
  });

  // ace-navigate event from HX-Trigger header
  document.addEventListener("ace-navigate", function (e) {
    const detail = e.detail || {};
    if (detail.index !== undefined) {
      window.__aceCurrentIndex = parseInt(detail.index, 10);
    }
    if (detail.total !== undefined) {
      window.__aceTotalSources = parseInt(detail.total, 10);
    }
    window.__aceFocusIndex = -1;
    const input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
    // Reset scroll position for new source
    const cs = document.getElementById("content-scroll");
    if (cs) cs.scrollTop = 0;
  });

  /* ================================================================
   * 13. Code management helpers
   * ================================================================ */

  let _menuOpen = false;
  let _lastSelectedCodeId = null;

  // No-op stubs — replaced by real implementations in later tasks
  function _closeCodeMenu() {}

  const _COLOUR_PALETTE = ["#A91818","#557FE6","#6DA918","#E655D4","#18A991","#E6A455","#3C18A9","#5BE655","#A91848","#55B0E6","#9DA918","#C855E6","#18A960","#E67355","#1824A9","#8CE655","#A91879","#55E1E6","#A98418","#9755E6","#18A930","#E65567","#1855A9","#BCE655","#A918A9","#55E6BB","#A95418","#6755E6","#30A918","#E65598","#1885A9","#E6E055","#7818A9","#55E68B","#A92318","#5574E6"];

  let _activeColourPopover = null;

  function _closeColourPopover() {
    if (_activeColourPopover) {
      _activeColourPopover.remove();
      _activeColourPopover = null;
    }
    document.removeEventListener("click", _onColourOutsideClick);
    document.removeEventListener("keydown", _onColourEscape);
  }

  function _openColourPopover(codeId) {
    _closeAllPopovers();
    let row = document.querySelector(`.ace-code-row[data-code-id="${codeId}"]`);
    if (!row) return;
    const rect = row.getBoundingClientRect();

    const popover = document.createElement("div");
    popover.className = "ace-colour-popover";

    _COLOUR_PALETTE.forEach(function (hex) {
      const swatch = document.createElement("button");
      swatch.className = "ace-colour-swatch";
      swatch.style.background = hex;
      swatch.addEventListener("click", function () {
        _closeAllPopovers();
        _codeAction("PUT", `/api/codes/${codeId}`,
          `colour=${encodeURIComponent(hex)}&current_index=${window.__aceCurrentIndex}`);
      });
      popover.appendChild(swatch);
    });

    document.body.appendChild(popover);
    _activeColourPopover = popover;

    popover.style.top = `${rect.bottom + 4}px`;
    popover.style.left = rect.left + "px";

    setTimeout(function () {
      document.addEventListener("click", _onColourOutsideClick);
      document.addEventListener("keydown", _onColourEscape);
    }, 0);
  }

  function _onColourOutsideClick(e) {
    if (_activeColourPopover && !_activeColourPopover.contains(e.target)) _closeColourPopover();
  }

  function _onColourEscape(e) {
    if (e.key === "Escape") _closeColourPopover();
  }

  document.addEventListener("contextmenu", function (e) {
    let row = e.target.closest(".ace-code-row");
    if (!row) return;
    e.preventDefault();
    e.stopPropagation();
    let codeId = row.getAttribute("data-code-id");
    if (codeId) _openColourPopover(codeId);
  });

  function _closeAllPopovers() {
    _closeCodeMenu();
    _closeColourPopover();
  }

  function _refreshSidebar() {
    htmx.ajax("POST", "/api/codes/reorder", {
      target: "#code-sidebar",
      swap: "outerHTML",
      values: { code_ids: "[]", current_index: window.__aceCurrentIndex },
    }).then(function () {
      _initSortable();
      _restoreCollapseState();
      _updateKeycaps();
    });
  }

  function _codeAction(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body,
    }).then(function (r) {
      if (!r.ok) { window._setStatus("Action failed", "err"); return Promise.reject(); }
      _refreshSidebar();
    });
  }

  function _startInlineRename(codeId) {
    let row = document.querySelector(`.ace-code-row[data-code-id="${codeId}"]`);
    if (!row) return;
    const nameEl = row.querySelector(".ace-code-name");
    if (!nameEl) return;

    const original = nameEl.textContent;
    nameEl.contentEditable = "true";
    nameEl.focus();

    const range = document.createRange();
    range.selectNodeContents(nameEl);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    let done = false;
    function save() {
      if (done) return;
      done = true;
      const newName = nameEl.textContent.trim();
      nameEl.contentEditable = "false";
      if (!newName || newName === original) {
        nameEl.textContent = original;
        _focusTreeItem(row);
        return;
      }
      _codeAction("PUT", `/api/codes/${codeId}`,
        `name=${encodeURIComponent(newName)}&current_index=${window.__aceCurrentIndex}`
      ).catch(function () { nameEl.textContent = original; });
      _focusTreeItem(row);
    }

    nameEl.addEventListener("keydown", function handler(e) {
      if (e.key === "Enter") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); save(); }
      if (e.key === "Escape") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); done = true; nameEl.textContent = original; nameEl.contentEditable = "false"; _focusTreeItem(row); }
    });

    nameEl.addEventListener("blur", function blurHandler() {
      nameEl.removeEventListener("blur", blurHandler);
      setTimeout(function () { save(); }, 50);
    });

    nameEl.addEventListener("paste", function pasteHandler(e) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text.replace(/\n/g, " "));
    });
  }

  function _startGroupRename(header) {
    const label = header.querySelector(".ace-group-label");
    if (!label) return;
    const original = label.textContent;
    const oldGroup = header.getAttribute("data-group");

    label.contentEditable = "true";
    label.focus();

    const range = document.createRange();
    range.selectNodeContents(label);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    let done = false;
    function save() {
      if (done) return;
      done = true;
      const newName = label.textContent.trim();
      label.contentEditable = "false";
      if (!newName || newName === original) {
        label.textContent = original;
        _focusTreeItem(header);
        return;
      }
      _codeAction("PUT", "/api/codes/rename-group",
        `old_name=${encodeURIComponent(oldGroup)}&new_name=${encodeURIComponent(newName)}&current_index=${window.__aceCurrentIndex}`
      ).catch(function () { label.textContent = original; });
      _focusTreeItem(header);
    }

    label.addEventListener("keydown", function handler(e) {
      if (e.key === "Enter") { e.preventDefault(); label.removeEventListener("keydown", handler); save(); }
      if (e.key === "Escape") { e.preventDefault(); label.removeEventListener("keydown", handler); done = true; label.textContent = original; label.contentEditable = "false"; _focusTreeItem(header); }
    });

    label.addEventListener("blur", function blurHandler() {
      label.removeEventListener("blur", blurHandler);
      setTimeout(function () { save(); }, 50);
    });

    label.addEventListener("paste", function pasteHandler(e) {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text.replace(/\n/g, " "));
    });
  }

  document.addEventListener("dblclick", function (e) {
    const nameEl = e.target.closest(".ace-code-name");
    if (!nameEl) return;
    let row = nameEl.closest(".ace-code-row");
    if (!row) return;
    let codeId = row.getAttribute("data-code-id");
    if (codeId) _startInlineRename(codeId);
  });

  let _deleteTarget = null;
  let _deleteTimer = null;

  function _startDeleteConfirm(codeId) {
    if (_deleteTimer) { clearTimeout(_deleteTimer); _clearDeleteConfirm(); }
    let row = document.querySelector(`.ace-code-row[data-code-id="${codeId}"]`);
    if (!row) return;
    row.classList.add("ace-code-row--confirm-delete");
    _deleteTarget = codeId;
    _deleteTimer = setTimeout(function () { _clearDeleteConfirm(); }, 2000);
  }

  function _clearDeleteConfirm() {
    if (_deleteTarget) {
      let row = document.querySelector(`.ace-code-row[data-code-id="${_deleteTarget}"]`);
      if (row) row.classList.remove("ace-code-row--confirm-delete");
    }
    _deleteTarget = null;
    if (_deleteTimer) { clearTimeout(_deleteTimer); _deleteTimer = null; }
  }

  function _executeDelete(codeId) {
    _clearDeleteConfirm();
    _lastSelectedCodeId = null;
    _codeAction("DELETE", `/api/codes/${codeId}?current_index=${window.__aceCurrentIndex}`, null);
  }

  function _moveCode(codeId, direction) {
    const codes = window.__aceCodes || [];
    const ids = codes.map(function (c) { return c.id; });
    const idx = ids.indexOf(codeId);
    if (idx < 0) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= ids.length) return;
    ids[idx] = ids[newIdx];
    ids[newIdx] = codeId;
    _codeAction("POST", "/api/codes/reorder",
      `code_ids=${encodeURIComponent(JSON.stringify(ids))}&current_index=${window.__aceCurrentIndex}`);
  }

  function _moveToGroup(codeId, groupName) {
    _codeAction("PUT", `/api/codes/${codeId}`,
      `group_name=${encodeURIComponent(groupName)}&current_index=${window.__aceCurrentIndex}`);
  }

  let _sortableInstances = [];
  let _isDragging = false;

  function _initSortable() {
    _sortableInstances.forEach(function (s) { s.destroy(); });
    _sortableInstances = [];

    const containers = document.querySelectorAll('#code-tree [role="group"]');
    containers.forEach(function (container) {
      const instance = new Sortable(container, {
        group: "codes",
        animation: 150,
        delay: 200,
        delayOnTouchOnly: true,
        draggable: ".ace-code-row",
        ghostClass: "ace-code-row--ghost",
        onStart: function () { _isDragging = true; },
        onEnd: function (evt) {
          _isDragging = false;
          let codeId = evt.item.getAttribute("data-code-id");
          const newHeader = evt.to.previousElementSibling;
          const newGroup = newHeader ? (newHeader.getAttribute("data-group") || "") : "";
          const oldHeader = evt.from.previousElementSibling;
          const oldGroup = oldHeader ? (oldHeader.getAttribute("data-group") || "") : "";

          if (newGroup !== oldGroup && codeId) {
            fetch(`/api/codes/${codeId}`, {
              method: "PUT",
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              body: `group_name=${encodeURIComponent(newGroup)}&current_index=${window.__aceCurrentIndex}`,
            });
          }

          _persistCodeOrder();
        },
      });
      _sortableInstances.push(instance);
    });

    // Group-level Sortable: drag group headers to reorder entire groups
    const tree = document.getElementById("code-tree");
    if (tree) {
      const groupSortable = new Sortable(tree, {
        animation: 150,
        delay: 200,
        delayOnTouchOnly: true,
        draggable: ".ace-code-group-header",
        ghostClass: "ace-code-row--ghost",
        filter: '[role="group"], .ace-code-row, .ace-sidebar-empty, .ace-create-prompt',
        onStart: function (evt) {
          _isDragging = true;
          // Stash the associated group div so we can move it in onEnd
          const groupDiv = evt.item.nextElementSibling;
          if (groupDiv && groupDiv.getAttribute("role") === "group") {
            evt.item._groupDiv = groupDiv;
            groupDiv.style.display = "none"; // hide during drag to avoid visual clutter
          }
        },
        onEnd: function (evt) {
          _isDragging = false;
          const header = evt.item;
          const groupDiv = header._groupDiv;
          delete header._groupDiv;

          // Move the group div to follow the header in its new position
          if (groupDiv) {
            groupDiv.style.display = "";
            header.parentNode.insertBefore(groupDiv, header.nextSibling);
          }

          // Persist the new code order (group positions changed)
          _persistCodeOrder();

          _updateKeycaps();
        },
      });
      _sortableInstances.push(groupSortable);
    }
  }

  /* ================================================================
   * 14. Code menu dropdown (right-click context menu)
   * ================================================================ */

  let _activeCodeMenu = null;

  // Override the no-op stub from section 13
  _closeCodeMenu = function () {
    if (_activeCodeMenu) {
      _activeCodeMenu.remove();
      _activeCodeMenu = null;
      _menuOpen = false;
    }
    document.removeEventListener("click", _onMenuOutsideClick);
    document.removeEventListener("keydown", _onMenuEscape);
  };

  function _openCodeMenu(x, y, codeId) {
    _closeAllPopovers();
    _lastSelectedCodeId = codeId;
    _menuOpen = true;

    const menu = document.createElement("div");
    menu.className = "ace-code-menu";

    const items = [
      { label: "Rename", hint: "F2", action: function () { _closeCodeMenu(); _startInlineRename(codeId); } },
      { label: "Colour", hint: "", action: function () { _closeCodeMenu(); _openColourPopover(codeId); } },
      { label: "View coded text", action: function () {
          _closeCodeMenu();
          window.__aceExcerptReturnIndex = window.__aceCurrentIndex;
          htmx.ajax("GET", `/api/code/${codeId}/excerpts`, {
            target: "#text-panel", swap: "outerHTML"
          });
        }
      },
      { label: "Move Up", hint: "Alt+Shift+\u2191", action: function () { _closeCodeMenu(); _moveCode(codeId, -1); } },
      { label: "Move Down", hint: "Alt+Shift+\u2193", action: function () { _closeCodeMenu(); _moveCode(codeId, 1); } },
      { label: "Delete", hint: "\u232b", danger: true, action: function () { _closeCodeMenu(); _startDeleteConfirm(codeId); } },
    ];

    // Add "Move to Group" submenu
    const groups = _getGroupNames();
    const moveItem = document.createElement("div");
    moveItem.className = "ace-code-menu-item ace-code-menu-sub";
    moveItem.textContent = "Move to Group \u25b8";
    const moveHint = document.createElement("span");
    moveHint.className = "ace-code-menu-hint";
    moveHint.textContent = "Alt+\u2192";
    moveItem.appendChild(moveHint);
    const sub = document.createElement("div");
    sub.className = "ace-code-submenu";

    const ungrouped = document.createElement("button");
    ungrouped.className = "ace-code-menu-item";
    ungrouped.textContent = "Ungrouped";
    ungrouped.addEventListener("click", function () { _closeCodeMenu(); _moveToGroup(codeId, ""); });
    sub.appendChild(ungrouped);

    groups.forEach(function (gn) {
      const btn = document.createElement("button");
      btn.className = "ace-code-menu-item";
      btn.textContent = gn;
      btn.addEventListener("click", function () { _closeCodeMenu(); _moveToGroup(codeId, gn); });
      sub.appendChild(btn);
    });

    // "New Group..." option
    const sep = document.createElement("div");
    sep.className = "ace-code-menu-sep";
    sub.appendChild(sep);
    const newGroupBtn = document.createElement("button");
    newGroupBtn.className = "ace-code-menu-item";
    newGroupBtn.textContent = "New Group\u2026";
    newGroupBtn.addEventListener("click", function () {
      _closeCodeMenu();
      let name = prompt("Group name:");
      if (!name || !name.trim()) return;
      _moveToGroup(codeId, name.trim());
    });
    sub.appendChild(newGroupBtn);

    moveItem.appendChild(sub);
    // Insert after Colour, before Move Up
    items.splice(2, 0, { element: moveItem });

    items.forEach(function (item) {
      if (item.element) { menu.appendChild(item.element); return; }
      let el = document.createElement("button");
      el.className = "ace-code-menu-item";
      if (item.danger) el.classList.add("ace-code-menu-item--danger");
      el.textContent = item.label;
      if (item.hint) {
        const hintEl = document.createElement("span");
        hintEl.className = "ace-code-menu-hint";
        hintEl.textContent = item.hint;
        el.appendChild(hintEl);
      }
      el.addEventListener("click", item.action);
      menu.appendChild(el);
    });

    document.body.appendChild(menu);
    _activeCodeMenu = menu;

    const mw = menu.offsetWidth, mh = menu.offsetHeight;
    menu.style.top = `${y + mh > window.innerHeight ? Math.max(0, y - mh) : y}px`;
    menu.style.left = `${x + mw > window.innerWidth ? Math.max(0, x - mw) : x}px`;

    setTimeout(function () {
      document.addEventListener("click", _onMenuOutsideClick);
      document.addEventListener("keydown", _onMenuEscape);
    }, 0);
  }

  function _onMenuOutsideClick(e) {
    if (_activeCodeMenu && !_activeCodeMenu.contains(e.target)) _closeCodeMenu();
  }

  function _onMenuEscape(e) {
    if (e.key === "Escape") _closeCodeMenu();
  }

  function _getGroupNames() {
    const result = [];
    document.querySelectorAll("#code-tree .ace-code-group-header[data-group]").forEach(function (h) {
      let name = h.getAttribute("data-group");
      if (name) result.push(name);
    });
    return result;
  }

  // Right-click context menu delegation
  document.addEventListener("contextmenu", function (e) {
    let row = e.target.closest(".ace-code-row");
    if (!row) return;
    e.preventDefault();
    let codeId = row.getAttribute("data-code-id");
    if (codeId) _openCodeMenu(e.clientX, e.clientY, codeId);
  });

  /** Unified apply helper used by keycap click, search Enter, and tree Enter. */
  function _applyCode(codeId) {
    if (window.__aceExcerptListActive) return;
    let codeName = "";
    let row = document.querySelector(`.ace-code-row[data-code-id="${codeId}"]`);
    if (row) {
      const nameEl = row.querySelector(".ace-code-name");
      if (nameEl) codeName = nameEl.textContent;
    }
    const isSelection = !!window.__aceLastSelection;
    if (isSelection) {
      _applyCodeToSelection(codeId);
    } else if (window.__aceFocusIndex >= 0) {
      _applyCodeToSentence(codeId);
    } else {
      return;
    }
    if (codeName) {
      const target = isSelection ? "selection" : "sentence " + (window.__aceFocusIndex + 1);
      _announce(`'${codeName}' applied to ${target}`);
    }
  }

  // Keycap badge click: apply code to focused sentence/selection
  document.addEventListener("click", function (e) {
    const keycap = e.target.closest(".ace-keycap");
    if (!keycap) return;
    e.stopPropagation();
    let row = keycap.closest(".ace-code-row");
    if (!row) return;
    if (row.querySelector('[contenteditable="true"]')) return;
    let codeId = row.getAttribute("data-code-id");
    if (!codeId) return;
    _clearSearchFilter();
    _applyCode(codeId);
  });

  // Click on code row (not keycap): focus/select for management
  document.addEventListener("click", function (e) {
    let row = e.target.closest(".ace-code-row");
    if (!row) return;
    if (e.target.closest(".ace-keycap")) return;
    if (e.target.closest(".ace-code-menu") || _isDragging) return;
    if (e.target.isContentEditable) return;
    _focusTreeItem(row);
  });

  /** Clear the search filter input and trigger the input handler to restore all rows. */
  function _clearSearchFilter() {
    let el = document.getElementById("code-search-input");
    if (el && el.value) {
      el.value = "";
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  /* ================================================================
   * 15. Code search / filter / create
   * ================================================================ */

  document.addEventListener("input", function (e) {
    if (e.target.id !== "code-search-input") return;
    const query = e.target.value.toLowerCase();
    const tree = document.getElementById("code-tree");
    if (!tree) return;

    // Remove any existing "create" prompt
    const oldPrompt = tree.querySelector(".ace-create-prompt");
    if (oldPrompt) oldPrompt.remove();

    if (query && !query.startsWith("/")) {
      // Filter mode
      _sortableInstances.forEach(function (s) { s.option("disabled", true); });
      const rows = tree.querySelectorAll(".ace-code-row");
      let anyMatch = false;
      rows.forEach(function (row) {
        const nameEl = row.querySelector(".ace-code-name");
        if (!nameEl) return;
        const text = nameEl.textContent;
        const match = text.toLowerCase().indexOf(query) >= 0;
        if (match) {
          row.style.display = "";
          row.removeAttribute("aria-hidden");
          anyMatch = true;
          // Highlight match
          const idx = text.toLowerCase().indexOf(query);
          const before = text.substring(0, idx);
          const matched = text.substring(idx, idx + query.length);
          const after = text.substring(idx + query.length);
          nameEl.innerHTML = `${_escapeHtml(before)}<mark>${_escapeHtml(matched)}</mark>${_escapeHtml(after)}`;
        } else {
          row.style.display = "none";
          row.setAttribute("aria-hidden", "true");
          nameEl.textContent = text; // Strip any existing highlight
        }
      });

      // Show/hide group headers based on visible children
      tree.querySelectorAll(".ace-code-group-header").forEach(function (header) {
        const groupDiv = header.nextElementSibling;
        if (!groupDiv || groupDiv.getAttribute("role") !== "group") return;
        let hasVisible = false;
        groupDiv.querySelectorAll(".ace-code-row").forEach(function (r) {
          if (r.style.display !== "none") hasVisible = true;
        });
        header.style.display = hasVisible ? "" : "none";
        if (hasVisible) { header.removeAttribute("aria-hidden"); } else { header.setAttribute("aria-hidden", "true"); }
        groupDiv.style.display = hasVisible ? "" : "none";
        if (hasVisible) { groupDiv.removeAttribute("aria-hidden"); } else { groupDiv.setAttribute("aria-hidden", "true"); }
      });

      // Show "Create" prompt if no matches
      if (!anyMatch) {
        let prompt = document.createElement("div");
        prompt.className = "ace-create-prompt ace-create-prompt--code";
        prompt.innerHTML = `<span>+</span> Create "<strong>${_escapeHtml(e.target.value.trim())}</strong>"`;
        prompt.setAttribute("data-action", "create-code");
        prompt.addEventListener("click", function () {
          _createCodeFromSearch();
        });
        tree.appendChild(prompt);
      }

      // Highlight first visible match as search target
      const prevTarget = tree.querySelector(".ace-code-row--search-target");
      if (prevTarget) {
        prevTarget.classList.remove("ace-code-row--search-target");
        prevTarget.removeAttribute("aria-current");
      }
      if (anyMatch) {
        const target = Array.from(tree.querySelectorAll(".ace-code-row")).find(function (r) {
          return r.style.display !== "none";
        });
        if (target) {
          target.classList.add("ace-code-row--search-target");
          target.setAttribute("aria-current", "true");
        }
      }
    } else if (query && query.startsWith("/")) {
      // Group creation mode
      _sortableInstances.forEach(function (s) { s.option("disabled", true); });
      let groupName = query.substring(1).trim();
      // Hide all codes, show group creation prompt
      tree.querySelectorAll(".ace-code-row").forEach(function (r) { r.style.display = "none"; r.setAttribute("aria-hidden", "true"); });
      tree.querySelectorAll(".ace-code-group-header").forEach(function (h) { h.style.display = "none"; h.setAttribute("aria-hidden", "true"); });
      tree.querySelectorAll('[role="group"]').forEach(function (g) { g.style.display = "none"; g.setAttribute("aria-hidden", "true"); });

      if (groupName) {
        let exists = false;
        tree.querySelectorAll(".ace-code-group-header").forEach(function (h) {
          if (h.getAttribute("data-group") === groupName) exists = true;
        });

        let prompt = document.createElement("div");
        if (exists) {
          prompt.className = "ace-create-prompt";
          prompt.innerHTML = `Group "<strong>${_escapeHtml(groupName)}</strong>" already exists`;
        } else {
          prompt.className = "ace-create-prompt ace-create-prompt--group";
          prompt.innerHTML = `<span>\u25b8</span> Create group "<strong>${_escapeHtml(groupName)}</strong>"`;
          prompt.setAttribute("data-action", "create-group");
          prompt.addEventListener("click", function () {
            _createGroupFromSearch();
          });
        }
        tree.appendChild(prompt);
      }
    } else {
      // Empty: restore all rows, clear highlights
      _sortableInstances.forEach(function (s) { s.option("disabled", false); });
      tree.querySelectorAll(".ace-code-row").forEach(function (row) {
        row.style.display = "";
        row.removeAttribute("aria-hidden");
        const nameEl = row.querySelector(".ace-code-name");
        if (nameEl && nameEl.querySelector("mark")) {
          nameEl.textContent = nameEl.textContent; // Strip HTML
        }
      });
      tree.querySelectorAll(".ace-code-group-header").forEach(function (h) { h.style.display = ""; h.removeAttribute("aria-hidden"); });
      tree.querySelectorAll('[role="group"]').forEach(function (g) { g.style.display = ""; g.removeAttribute("aria-hidden"); });
      _restoreCollapseState();
      const prevTarget = tree.querySelector(".ace-code-row--search-target");
      if (prevTarget) {
        prevTarget.classList.remove("ace-code-row--search-target");
        prevTarget.removeAttribute("aria-current");
      }
    }

    _updateKeycaps();
  });

  function _createCodeFromSearch() {
    const input = document.getElementById("code-search-input");
    if (!input) return;
    let name = input.value.trim();
    if (!name || name.startsWith("/")) return;

    htmx.ajax("POST", "/api/codes", {
      values: { name: name, current_index: window.__aceCurrentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
    });
    input.value = "";
    _announce(`Code '${name}' created`);
  }

  function _createGroupFromSearch() {
    const input = document.getElementById("code-search-input");
    if (!input) return;
    let groupName = input.value.trim().substring(1).trim(); // remove / prefix
    if (!groupName) return;

    const tree = document.getElementById("code-tree");
    if (!tree) return;

    // Remove create prompt if present
    const ref = tree.querySelector(".ace-create-prompt");
    if (ref) ref.remove();

    const els = _makeGroupElements(groupName);
    const header = els.header;
    const groupDiv = els.groupDiv;

    const emptyMsg = tree.querySelector(".ace-sidebar-empty");
    if (emptyMsg) {
      tree.insertBefore(header, emptyMsg);
      tree.insertBefore(groupDiv, emptyMsg);
      emptyMsg.remove();
    } else {
      tree.appendChild(header);
      tree.appendChild(groupDiv);
    }

    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    _initSortable();
    _announce(`Group '${groupName}' created`);
  }

  document.addEventListener("keydown", function (e) {
    if (e.target.id !== "code-search-input") return;

    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (e.target.value) {
        e.target.value = "";
        e.target.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        _focusTextPanel();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      _focusCodeTree();
      return;
    }

    if (e.key !== "Enter") return;
    const val = e.target.value.trim();
    if (!val) return;
    e.preventDefault();

    if (val.startsWith("/")) {
      _createGroupFromSearch();
    } else {
      // Only create if no visible code rows
      const tree = document.getElementById("code-tree");
      let count = 0;
      if (tree) {
        tree.querySelectorAll(".ace-code-row").forEach(function (r) {
          if (r.style.display !== "none") count++;
        });
      }
      if (count === 0) {
        _createCodeFromSearch();
      } else {
        // Has matches — find first visible match, clear search, apply
        const firstMatch = tree
          ? Array.from(tree.querySelectorAll(".ace-code-row")).find(function (r) { return r.style.display !== "none"; })
          : null;
        _clearSearchFilter();
        if (firstMatch) {
          let codeId = firstMatch.getAttribute("data-code-id");
          if (codeId) _applyCode(codeId);
        }
      }
    }
  });

  /** Collect all code row IDs from the tree and persist the order via API. */
  function _persistCodeOrder() {
    const allRows = document.querySelectorAll("#code-tree .ace-code-row");
    const ids = [];
    allRows.forEach(function (row) {
      let id = row.getAttribute("data-code-id");
      if (id) ids.push(id);
    });
    _codeAction("POST", "/api/codes/reorder",
      `code_ids=${encodeURIComponent(JSON.stringify(ids))}&current_index=${window.__aceCurrentIndex}`);
  }

  /** Create a group header + group container pair for the ARIA tree. */
  function _makeGroupElements(name) {
    const header = document.createElement("div");
    header.setAttribute("role", "treeitem");
    header.setAttribute("aria-expanded", "true");
    header.setAttribute("aria-level", "1");
    header.className = "ace-code-group-header";
    header.setAttribute("data-group", name);
    header.setAttribute("tabindex", "-1");
    const toggle = document.createElement("span");
    toggle.className = "ace-group-toggle";
    toggle.innerHTML = _chevronDown;
    const label = document.createElement("span");
    label.className = "ace-group-label";
    label.textContent = name;
    header.appendChild(toggle);
    header.append(" ");
    header.appendChild(label);

    const groupDiv = document.createElement("div");
    groupDiv.setAttribute("role", "group");

    return { header: header, groupDiv: groupDiv };
  }

  /* ================================================================
   * 16. SVG overlay — annotation rendering
   * ================================================================ */

  /**
   * Build a flat list of {node, sourceStart, sourceEnd} entries
   * for all text nodes inside sentence spans in the text panel.
   */
  function _buildTextIndex(container) {
    let index = [];
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {
      let sentence = node.parentElement.closest(".ace-sentence");
      if (!sentence) continue;
      const sentStart = parseInt(sentence.dataset.start, 10);
      if (isNaN(sentStart)) continue;

      let charsBefore = 0;
      const tw = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
      let t;
      while ((t = tw.nextNode())) {
        if (t === node) break;
        charsBefore += t.textContent.length;
      }

      const nodeSourceStart = sentStart + charsBefore;
      index.push({
        node: node,
        sourceStart: nodeSourceStart,
        sourceEnd: nodeSourceStart + node.textContent.length,
      });
    }
    return index;
  }

  /**
   * Find the DOM position (node + offset) for a source character offset.
   */
  function _findDOMPosition(textIndex, sourceOffset) {
    for (let i = 0; i < textIndex.length; i++) {
      const entry = textIndex[i];
      if (sourceOffset >= entry.sourceStart && sourceOffset <= entry.sourceEnd) {
        return { node: entry.node, offset: sourceOffset - entry.sourceStart };
      }
    }
    return null;
  }

  // Rect-merge tuning.
  // CONTAIN_SLOP is in pixels — the tolerance for "rect A strictly contains rect B"
  // when deduplicating block-element and inline-text rects that overlap.
  // LINE_OVERLAP_RATIO is a proportion — two rects are considered to be on the
  // same visual line when their vertical extents overlap by at least this much
  // of the smaller rect's height.
  const CONTAIN_SLOP = 0.5;
  const LINE_OVERLAP_RATIO = 0.5;

  function _paraBreakRects(body) {
    return Array.from(body.querySelectorAll(".ace-para-break")).map(function (el) {
      return el.getBoundingClientRect();
    });
  }

  /**
   * Merge DOMRectList entries from a Range into per-visual-line rects.
   * Steps:
   *   1. Drop rects whose vertical extent is fully contained within any
   *      .ace-para-break element — WebKit's getClientRects() emits a rect
   *      for block-level elements the range crosses, producing a phantom
   *      highlight in the inter-paragraph gap for cross-paragraph ranges.
   *   2. Drop any rect that strictly contains another rect — kills duplicate
   *      `display: block` element rects when a Range fully contains a list item.
   *   3. Per-line union — sort by top, group rects whose vertical extents
   *      overlap by at least LINE_OVERLAP_RATIO of the smaller height, union
   *      left/right/top/bottom per group. This collapses sub-pixel gaps at
   *      sentence boundaries.
   */
  function _mergeRectsByLine(rects, paraBreakRects) {
    const PARA_SLOP = 1;
    const validInitial = Array.from(rects).filter(function (r) {
      return r.width >= 1 && r.height >= 1;
    });
    const valid = (paraBreakRects && paraBreakRects.length)
      ? validInitial.filter(function (r) {
          return !paraBreakRects.some(function (br) {
            return r.top >= br.top - PARA_SLOP && r.bottom <= br.bottom + PARA_SLOP;
          });
        })
      : validInitial;

    // Step 1: drop any rect that strictly contains another
    const nonContaining = valid.filter(function (r, i) {
      return !valid.some(function (other, j) {
        if (i === j) return false;
        const contains =
          r.left <= other.left + CONTAIN_SLOP &&
          r.top <= other.top + CONTAIN_SLOP &&
          r.right >= other.right - CONTAIN_SLOP &&
          r.bottom >= other.bottom - CONTAIN_SLOP;
        const sameRect =
          Math.abs(r.left - other.left) <= CONTAIN_SLOP &&
          Math.abs(r.top - other.top) <= CONTAIN_SLOP &&
          Math.abs(r.right - other.right) <= CONTAIN_SLOP &&
          Math.abs(r.bottom - other.bottom) <= CONTAIN_SLOP;
        return contains && !sameRect;
      });
    });

    // Step 2: per-line union via Y-overlap
    const sorted = nonContaining.sort(function (a, b) {
      return a.top - b.top || a.left - b.left;
    });
    const lines = [];
    for (const r of sorted) {
      let line = null;
      for (const ln of lines) {
        const overlap = Math.min(ln.bottom, r.bottom) - Math.max(ln.top, r.top);
        const minH = Math.min(ln.bottom - ln.top, r.bottom - r.top);
        if (overlap >= minH * LINE_OVERLAP_RATIO) {
          line = ln;
          break;
        }
      }
      if (line) {
        line.left = Math.min(line.left, r.left);
        line.right = Math.max(line.right, r.right);
        line.top = Math.min(line.top, r.top);
        line.bottom = Math.max(line.bottom, r.bottom);
      } else {
        lines.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right });
      }
    }
    return lines;
  }

  // ResizeObserver state — single observer re-attached after each paint.
  let _resizeObserver = null;
  let _paintRaf = null;
  let _observedBody = null;

  // Chip-click flash cleanup timeout — stored module-level so rapid clicks
  // can cancel any pending cleanup before scheduling a new one.
  let _flashTimeout = null;

  /**
   * Attach the (lazy) ResizeObserver to the current .ace-text-body element.
   * After OOB swaps replace #text-panel, this is called with the new body;
   * the reference comparison detects the swap, unobserves the detached old
   * body, and observes the new one. Paints are debounced to one per
   * animation frame via requestAnimationFrame.
   */
  function _attachResizeObserver(body) {
    if (_observedBody === body) return;
    if (!_resizeObserver) {
      _resizeObserver = new ResizeObserver(function () {
        if (_paintRaf) cancelAnimationFrame(_paintRaf);
        _paintRaf = requestAnimationFrame(function () {
          _paintSvg();
          _paintRaf = null;
        });
      });
    } else if (_observedBody) {
      _resizeObserver.unobserve(_observedBody);
    }
    _resizeObserver.observe(body);
    _observedBody = body;
  }

  /**
   * Detach the ResizeObserver from any previously-observed body and clear
   * all paint state. Called on the early-return paths in _paintSvg when the
   * text body is gone (e.g., after a swap to the excerpt-list view) so we
   * don't retain a reference to a detached DOM node.
   */
  function _detachResizeObserver() {
    if (_resizeObserver && _observedBody) {
      _resizeObserver.unobserve(_observedBody);
    }
    _observedBody = null;
    if (_paintRaf) {
      cancelAnimationFrame(_paintRaf);
      _paintRaf = null;
    }
  }

  /**
   * Paint all annotation highlights as SVG <rect> elements inside
   * #ace-hl-overlay. Reads annotation data from #ace-ann-data, builds a
   * Range per annotation, normalises getClientRects() into per-line rects,
   * and emits one <rect class="ace-hl-{cid}"> element per visual line.
   */
  function _paintSvg() {
    const body = document.querySelector(".ace-text-body");
    if (!body) { _detachResizeObserver(); return; }
    const svg = document.getElementById("ace-hl-overlay");
    if (!svg) { _detachResizeObserver(); return; }

    // Clear existing highlight rects (preserve any in-flight flash rects)
    svg.querySelectorAll('rect[data-ace-hl="1"]').forEach(function (el) { el.remove(); });

    const dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    const annotations = JSON.parse(dataEl.dataset.annotations || "[]");
    if (!annotations.length) {
      _attachResizeObserver(body);
      return;
    }

    // Size the SVG to match its containing block so coordinates are correct.
    const bodyBox = body.getBoundingClientRect();
    svg.setAttribute("width", bodyBox.width);
    svg.setAttribute("height", bodyBox.height);

    const overlayRect = svg.getBoundingClientRect();

    // Build the text index ONCE for all annotations — O(N+M) instead of O(N*M).
    // ResizeObserver re-fires this on every layout change, so per-annotation
    // tree walks compound quickly on large sources.
    const textIndex = _buildTextIndex(body);
    if (!textIndex.length) {
      _attachResizeObserver(body);
      return;
    }

    const paraBreakRects = _paraBreakRects(body);

    for (const ann of annotations) {
      const startPos = _findDOMPosition(textIndex, ann.start);
      const endPos = _findDOMPosition(textIndex, ann.end);
      if (!startPos || !endPos) continue;
      let range;
      try {
        range = new Range();
        range.setStart(startPos.node, startPos.offset);
        range.setEnd(endPos.node, endPos.offset);
      } catch (e) {
        continue;
      }
      const lines = _mergeRectsByLine(range.getClientRects(), paraBreakRects);
      for (const line of lines) {
        const x = Math.floor(line.left - overlayRect.left);
        const y = Math.floor(line.top - overlayRect.top);
        const right = Math.ceil(line.right - overlayRect.left);
        const bottom = Math.ceil(line.bottom - overlayRect.top);
        const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        el.setAttribute("fill", "transparent");
        el.setAttribute("class", "ace-hl-" + ann.code_id);
        el.dataset.aceHl = "1";
        el.setAttribute("x", x);
        el.setAttribute("y", y);
        el.setAttribute("width", right - x);
        el.setAttribute("height", bottom - y);
        svg.appendChild(el);
      }
    }

    _attachResizeObserver(body);
  }

  /* ================================================================
   * 17. Sidebar keyboard navigation (ARIA treeview)
   * ================================================================ */

  /** Push a message to a live region. Polite by default; assertive=true for errors. */
  function _announce(message, assertive) {
    const id = assertive ? "ace-live-region-assertive" : "ace-live-region";
    const region = document.getElementById(id);
    if (!region) return;
    region.textContent = message;
    setTimeout(function () { region.textContent = ""; }, 3000);
  }

  // ---- Status bar helpers ----
  let _statusEventClearTimer = null;

  /** Update the ambient left segment from current DOM state. */
  function _setAmbient() {
    const el = document.querySelector(".ace-statusbar-ambient");
    if (!el) return;
    const parts = [];
    const projName = document.documentElement.dataset.aceProjectName;
    if (projName) parts.push(projName);
    const idx = window.__aceCurrentIndex;
    const total = window.__aceTotalSources;
    if (Number.isFinite(idx) && Number.isFinite(total) && total > 0) {
      parts.push("Source " + (idx + 1) + " / " + total);
    }
    const codeChips = document.querySelectorAll(".ace-code-bar .ace-code-chip");
    if (codeChips.length) {
      parts.push(codeChips.length + (codeChips.length === 1 ? " code" : " codes"));
    }
    const flagBtn = document.getElementById("nav-flag-btn");
    if (flagBtn && flagBtn.classList.contains("ace-flag-btn--active")) {
      parts.push("flagged");
    }
    el.textContent = parts.join(" · ");
  }

  /**
   * Show an ephemeral or sticky message in the status bar event segment.
   *   kind="ok": text for ~2 s then fades (via empty-state CSS + timer clears text).
   *   kind="err": sticky until the next _setStatus() call.
   * Mirrors to the ARIA live region (assertive when kind="err").
   */
  function _setStatus(text, kind) {
    kind = kind || "ok";
    const sbEl = document.querySelector(".ace-statusbar-event");
    const pillEl = document.getElementById("ace-text-event-pill");
    if (!sbEl && !pillEl) return;

    if (_statusEventClearTimer) {
      clearTimeout(_statusEventClearTimer);
      _statusEventClearTimer = null;
    }

    if (sbEl) {
      sbEl.textContent = text || "";
      sbEl.classList.remove("ace-statusbar-event--ok", "ace-statusbar-event--err");
      if (text) sbEl.classList.add("ace-statusbar-event--" + kind);
    }
    if (pillEl) {
      pillEl.textContent = text || "";
      pillEl.classList.remove("ace-text-event-pill--ok", "ace-text-event-pill--err");
      if (text) pillEl.classList.add("ace-text-event-pill--" + kind);
    }

    if (text) _announce(text, kind === "err");

    if (kind === "ok" && text) {
      _statusEventClearTimer = setTimeout(function () {
        if (sbEl) {
          sbEl.textContent = "";
          sbEl.classList.remove("ace-statusbar-event--ok");
        }
        if (pillEl) {
          pillEl.textContent = "";
          pillEl.classList.remove("ace-text-event-pill--ok");
        }
      }, 2000);
    }
  }

  window._setStatus = _setStatus;
  window._setAmbient = _setAmbient;

  /**
   * Briefly swap a control's label to a confirmation, then revert.
   * Used for import/export success feedback — no toast, no status-bar entry.
   * Safe to call repeatedly on the same element; the prior revert timer is
   * cancelled so the label always returns to the cached original.
   */
  function _flashOriginConfirmation(elementId, text, revertMs) {
    const el = document.getElementById(elementId);
    if (!el) return;
    revertMs = revertMs || 1500;
    if (!el.dataset.aceOriginalLabel) {
      el.dataset.aceOriginalLabel = el.textContent;
    }
    el.textContent = text;
    el.classList.add("ace-origin-flash");
    if (el._aceFlashTimer) clearTimeout(el._aceFlashTimer);
    el._aceFlashTimer = setTimeout(function () {
      el.textContent = el.dataset.aceOriginalLabel;
      delete el.dataset.aceOriginalLabel;
      el.classList.remove("ace-origin-flash");
      el._aceFlashTimer = null;
    }, revertMs);
  }
  window._flashOriginConfirmation = _flashOriginConfirmation;

  // --- Zone cycling (Tab / Shift+Tab / Escape / /) ---

  /** Move focus to text panel. */
  function _focusTextPanel() {
    const tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  }

  /** Move focus to search bar. */
  function _focusSearchBar() {
    const sb = document.getElementById("code-search-input");
    if (sb) sb.focus();
  }

  /** Move focus into the code tree (last-focused item or first visible item). */
  function _focusCodeTree() {
    const active = _getActiveTreeItem();
    if (active && active.style.display !== "none") {
      active.focus();
    } else {
      const items = _getTreeItems();
      if (items.length > 0) _focusTreeItem(items[0]);
    }
  }

  /** Determine which zone currently has focus: "text", "search", "tree", or null. */
  function _activeZone() {
    let el = document.activeElement;
    if (!el) return null;
    if (el.id === "text-panel" || el.closest("#text-panel")) return "text";
    if (el.id === "code-search-input") return "search";
    const tree = document.getElementById("code-tree");
    if (tree && tree.contains(el)) return "tree";
    return null;
  }

  // Zone-level Tab cycling — captures Tab before browser default
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;

    let zone = _activeZone();
    if (!zone) return;

    if (!e.shiftKey) {
      if (zone === "text") { e.preventDefault(); _focusSearchBar(); return; }
      if (zone === "search") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "tree") { e.preventDefault(); _focusTextPanel(); return; }
    } else {
      if (zone === "text") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "search") { e.preventDefault(); _focusTextPanel(); return; }
      if (zone === "tree") { e.preventDefault(); _focusSearchBar(); return; }
    }
  }, true);  // capture phase to intercept before default Tab behaviour

  // --- Roving tabindex ---

  /** Return all visible treeitems (group headers + code rows) in DOM order. */
  function _getTreeItems() {
    const tree = document.getElementById("code-tree");
    if (!tree) return [];
    const items = tree.querySelectorAll('[role="treeitem"]');
    const result = [];
    items.forEach(function (item) {
      // Skip items hidden by search filter
      if (item.style.display === "none") return;
      if (item.classList.contains("ace-code-row")) {
        const groupContainer = item.closest('[role="group"]');
        if (groupContainer) {
          const prev = groupContainer.previousElementSibling;
          if (prev && prev.getAttribute("aria-expanded") === "false") return;
        }
      }
      result.push(item);
    });
    return result;
  }

  /** Move roving tabindex to the given treeitem. */
  function _focusTreeItem(item) {
    if (!item) return;
    const prev = _getActiveTreeItem();
    if (prev) prev.setAttribute("tabindex", "-1");
    item.setAttribute("tabindex", "0");
    item.focus();
  }

  /** Get the currently focused treeitem (tabindex="0"). */
  function _getActiveTreeItem() {
    const tree = document.getElementById("code-tree");
    return tree ? tree.querySelector('[role="treeitem"][tabindex="0"]') : null;
  }

  /** Check if a treeitem is a group header. */
  function _isGroupHeader(item) {
    return item && item.classList.contains("ace-code-group-header");
  }

  /** Move a group (header + group div) up or down by one position. */
  function _moveGroupInDirection(header, direction) {
    const groupDiv = header.nextElementSibling;
    if (!groupDiv || groupDiv.getAttribute("role") !== "group") return;
    const tree = document.getElementById("code-tree");
    if (!tree) return;

    if (direction === -1) {
      // Move up: find the previous group's header.
      // The element immediately before `header` is either a role="group" div
      // (from the previous group) or directly a group header (empty group).
      const prevSibling = header.previousElementSibling;
      if (!prevSibling) return;
      let prevHeader;
      if (prevSibling.getAttribute("role") === "group") {
        prevHeader = prevSibling.previousElementSibling;
      } else if (_isGroupHeader(prevSibling)) {
        prevHeader = prevSibling;
      } else {
        return;
      }
      if (!prevHeader || !_isGroupHeader(prevHeader)) return;
      // Current order: prevHeader, prevGroupDiv, header, groupDiv
      // Target order:  header, groupDiv, prevHeader, prevGroupDiv
      tree.insertBefore(header, prevHeader);
      tree.insertBefore(groupDiv, prevHeader);
    } else {
      // Move down: find the next group header + its group div.
      const nextHeader = groupDiv.nextElementSibling;
      if (!nextHeader || !_isGroupHeader(nextHeader)) return;
      const nextGroupDiv = nextHeader.nextElementSibling;
      if (!nextGroupDiv || nextGroupDiv.getAttribute("role") !== "group") return;
      // Current order: header, groupDiv, nextHeader, nextGroupDiv
      // Target order:  nextHeader, nextGroupDiv, header, groupDiv
      const ref = nextGroupDiv.nextElementSibling; // null → append at end
      tree.insertBefore(header, ref);
      tree.insertBefore(groupDiv, ref);
    }

    // Persist the new code order via the reorder endpoint.
    _persistCodeOrder();

    _updateKeycaps();
    _initSortable();
  }

  // --- Tree keydown handler ---

  document.addEventListener("keydown", function (e) {
    const tree = document.getElementById("code-tree");
    if (!tree || !tree.contains(document.activeElement)) return;
    const active = document.activeElement;
    if (!active || active.getAttribute("role") !== "treeitem") return;
    if (window.__aceExcerptListActive) return;
    if (active.querySelector('[contenteditable="true"]')) return;

    const key = e.key;
    const alt = e.altKey;
    const shift = e.shiftKey;

    // Alt+Shift+↑ — Move code up (or group up if focused on group header)
    if (key === "ArrowUp" && alt && shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(active.getAttribute("data-code-id"), -1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      } else {
        _moveGroupInDirection(active, -1);
        _announce(`Group '${active.getAttribute("data-group") || "Ungrouped"}' moved up`);
      }
      return;
    }

    // Alt+Shift+↓ — Move code down (or group down if focused on group header)
    if (key === "ArrowDown" && alt && shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(active.getAttribute("data-code-id"), 1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      } else {
        _moveGroupInDirection(active, 1);
        _announce(`Group '${active.getAttribute("data-group") || "Ungrouped"}' moved down`);
      }
      return;
    }

    // Alt+→ — Indent: move code into nearest group above
    if (key === "ArrowRight" && alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) return;
      let codeId = active.getAttribute("data-code-id");
      if (!codeId) return;

      // Check if already in a group
      const groupDiv = active.closest('[role="group"]');
      if (groupDiv) return; // Already in a group — one level only

      // Find nearest group header above
      let el = active;
      let targetGroup = null;
      while (el) {
        el = el.previousElementSibling;
        if (el && el.getAttribute("role") === "group") {
          const hdr = el.previousElementSibling;
          if (hdr && _isGroupHeader(hdr)) {
            targetGroup = hdr.getAttribute("data-group");
            break;
          }
        }
        if (el && _isGroupHeader(el)) {
          targetGroup = el.getAttribute("data-group");
          break;
        }
      }

      if (targetGroup !== null) {
        _moveToGroup(codeId, targetGroup);
        _announce(`'${(active.querySelector(".ace-code-name") || {}).textContent}' moved into ${targetGroup || "Ungrouped"}`);
      } else {
        // No group above — prompt for new group name
        _promptNewGroupForCode(active);
      }
      return;
    }

    // Alt+← — Outdent: move code out of group (ungrouped)
    if (key === "ArrowLeft" && alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) return;
      const codeId2 = active.getAttribute("data-code-id");
      if (!codeId2) return;

      const groupDiv2 = active.closest('[role="group"]');
      if (!groupDiv2) return; // Already ungrouped

      _moveToGroup(codeId2, "");
      _announce(`'${(active.querySelector(".ace-code-name") || {}).textContent}' moved to ungrouped`);
      return;
    }

    // Enter — Apply focused code to current sentence, return focus to text panel
    if (key === "Enter" && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        const codeId3 = active.getAttribute("data-code-id");
        if (codeId3) {
          _clearSearchFilter();
          _applyCode(codeId3);
        }
      } else {
        // On group header: toggle expand/collapse
        _toggleGroupCollapse(active);
      }
      return;
    }

    // F2 — Inline rename
    if (key === "F2" && !alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) {
        const groupName = active.getAttribute("data-group");
        if (groupName !== "") _startGroupRename(active);
      } else {
        const codeId4 = active.getAttribute("data-code-id");
        if (codeId4) _startInlineRename(codeId4);
      }
      return;
    }

    // Delete / Backspace — Delete code (double-press confirm)
    if ((key === "Delete" || key === "Backspace") && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        const codeId5 = active.getAttribute("data-code-id");
        if (!codeId5) return;
        if (_deleteTarget === codeId5) {
          _executeDelete(codeId5);
        } else {
          _startDeleteConfirm(codeId5);
        }
      }
      return;
    }

    const items = _getTreeItems();
    const idx = items.indexOf(active);

    // ↓ — Next visible treeitem
    if (key === "ArrowDown" && !alt && !shift) {
      e.preventDefault();
      if (idx < items.length - 1) _focusTreeItem(items[idx + 1]);
      return;
    }

    // ↑ — Previous visible treeitem
    if (key === "ArrowUp" && !alt && !shift) {
      e.preventDefault();
      if (idx > 0) _focusTreeItem(items[idx - 1]);
      return;
    }

    // → — Expand group or move to first child
    if (key === "ArrowRight" && !alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) {
        if (active.getAttribute("aria-expanded") === "false") {
          _expandGroup(active);
        } else {
          const groupDiv3 = active.nextElementSibling;
          if (groupDiv3 && groupDiv3.getAttribute("role") === "group") {
            const firstChild = groupDiv3.querySelector('[role="treeitem"]');
            if (firstChild) _focusTreeItem(firstChild);
          }
        }
      }
      return;
    }

    // ← — Collapse group or move to parent header
    if (key === "ArrowLeft" && !alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) {
        if (active.getAttribute("aria-expanded") === "true") {
          _collapseGroup(active);
        }
      } else {
        const groupEl = active.closest('[role="group"]');
        if (groupEl) {
          const header2 = groupEl.previousElementSibling;
          if (header2 && _isGroupHeader(header2)) _focusTreeItem(header2);
        }
      }
      return;
    }

    // Home — First treeitem
    if (key === "Home") {
      e.preventDefault();
      if (items.length > 0) _focusTreeItem(items[0]);
      return;
    }

    // End — Last treeitem
    if (key === "End") {
      e.preventDefault();
      if (items.length > 0) _focusTreeItem(items[items.length - 1]);
      return;
    }

    // Escape — Return to text panel
    if (key === "Escape" && !alt && !shift) {
      e.preventDefault();
      _clearSearchFilter();
      _focusTextPanel();
      return;
    }
  });

  // --- Group expand / collapse ---

  function _promptNewGroupForCode(codeRow) {
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Group name\u2026";
    input.className = "ace-sidebar-search";
    input.style.margin = "2px 10px";
    input.style.padding = "3px 8px";
    input.style.borderColor = "var(--ace-focus)";

    codeRow.parentNode.insertBefore(input, codeRow);
    input.focus();

    function cleanup() {
      if (input.parentNode) input.remove();
      _focusTreeItem(codeRow);
    }

    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        let name = input.value.trim();
        if (name) {
          let codeId = codeRow.getAttribute("data-code-id");
          const els = _makeGroupElements(name);
          const header = els.header;
          const groupDiv = els.groupDiv;

          input.remove();
          codeRow.parentNode.insertBefore(header, codeRow);
          codeRow.parentNode.insertBefore(groupDiv, codeRow);
          groupDiv.appendChild(codeRow);

          _moveToGroup(codeId, name);
          _initSortable();
          _announce(`Group '${name}' created with code inside`);
        } else {
          cleanup();
        }
      }
      if (ev.key === "Escape") {
        ev.preventDefault();
        cleanup();
      }
    });

    input.addEventListener("blur", function () {
      setTimeout(cleanup, 100);
    });
  }

  const _chevronDown = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5l4 4 4-4"/></svg>';
  const _chevronRight = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3l4 4-4 4"/></svg>';

  function _expandGroup(header) {
    header.setAttribute("aria-expanded", "true");
    const toggle = header.querySelector(".ace-group-toggle");
    if (toggle) toggle.innerHTML = _chevronDown;
    const groupName = header.getAttribute("data-group");
    _collapsedGroups[groupName] = false;
  }

  function _collapseGroup(header) {
    header.setAttribute("aria-expanded", "false");
    const toggle = header.querySelector(".ace-group-toggle");
    if (toggle) toggle.innerHTML = _chevronRight;
    const groupName = header.getAttribute("data-group");
    _collapsedGroups[groupName] = true;
  }

  /* ================================================================
   * 18. Codebook menu
   * ================================================================ */

  // Codebook menu: toggle, import, export
  document.addEventListener("click", function (e) {
    const dropdown = document.getElementById("codebook-dropdown");

    // Import button
    if (e.target.closest("#codebook-menu-import-btn")) {
      if (dropdown) dropdown.style.display = "none";
      fetch("/api/native/pick-file", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "accept=.csv"
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.path) return;
          htmx.ajax("POST", "/api/codes/import/preview-path", {
            values: { path: data.path, current_index: window.__aceCurrentIndex },
            target: "#modal-container",
            swap: "innerHTML",
          });
        });
      return;
    }

    // Export codebook button
    if (e.target.closest("#codebook-export-btn")) {
      if (dropdown) dropdown.style.display = "none";
      window.location.href = "/api/codes/export";
      window._setStatus("Exported", "ok");
      return;
    }

    // Export all annotations button
    if (e.target.closest("#export-annotations-btn")) {
      if (dropdown) dropdown.style.display = "none";
      window.location.href = "/api/export/annotations";
      window._setStatus("Exported", "ok");
      return;
    }

    // Export source notes button
    if (e.target.closest("#export-notes-btn")) {
      if (dropdown) dropdown.style.display = "none";
      window.location.href = "/api/export/notes";
      window._setStatus("Exported", "ok");
      return;
    }

    // Fullscreen toggle button
    if (e.target.closest("#fullscreen-btn")) {
      if (dropdown) dropdown.style.display = "none";
      _toggleFullscreen();
      return;
    }

    // Toggle button
    if (e.target.closest("#codebook-menu-btn")) {
      if (dropdown) dropdown.style.display = dropdown.style.display === "none" ? "" : "none";
      e.stopPropagation();
      return;
    }

    // Click outside — close if open
    if (dropdown && dropdown.style.display !== "none") {
      dropdown.style.display = "none";
    }
  });

  // Codebook menu: Escape closes dropdown
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      const dropdown = document.getElementById("codebook-dropdown");
      if (dropdown && dropdown.style.display !== "none") {
        dropdown.style.display = "none";
        e.stopPropagation();
      }
    }
  });

  // Fullscreen toggle
  function _toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(function (err) {
        window._setStatus(`Fullscreen failed: ${err.message}`, "err");
      });
    }
  }

  // Update menu item label when fullscreen state changes
  document.addEventListener("fullscreenchange", function () {
    const btn = document.getElementById("fullscreen-btn");
    if (btn) btn.textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen";
  });

  // Cmd/Ctrl+Shift+F — toggle fullscreen
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === "F" || e.key === "f")) {
      e.preventDefault();
      _toggleFullscreen();
    }
  });

  // Import codes from preview dialog
  window.aceImportFromPreview = function (btn) {
    const codesJson = btn.getAttribute("data-codes");
    const currentIndex = btn.getAttribute("data-current-index") || window.__aceCurrentIndex;
    const dialog = btn.closest("dialog");
    if (dialog) dialog.close();

    let importCount = 0;
    try {
      const parsed = JSON.parse(codesJson);
      if (Array.isArray(parsed)) importCount = parsed.length;
    } catch (_) { /* ignore — fall back to no count */ }
    const successLabel = importCount > 0
      ? "Imported " + importCount + " code" + (importCount === 1 ? "" : "s")
      : "Imported";

    // One-time afterRequest listener — fires the success message only when the
    // import request actually succeeded. _oob_status returns HTTP 200 with an
    // OOB error fragment that overwrites the status bar, so we additionally
    // skip when the response body contains the err-status marker.
    const onAfter = function (evt) {
      if (!evt.detail) return;
      const xhr = evt.detail.xhr;
      if (!xhr || !xhr.responseURL || !xhr.responseURL.endsWith("/api/codes/import")) return;
      document.removeEventListener("htmx:afterRequest", onAfter);
      if (!evt.detail.successful) return;
      const body = xhr.responseText || "";
      if (body.indexOf("ace-statusbar-event--err") !== -1) return;
      window._setStatus(successLabel, "ok");
    };
    document.addEventListener("htmx:afterRequest", onAfter);

    htmx.ajax("POST", "/api/codes/import", {
      values: { codes_json: codesJson, current_index: currentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
    });
  };

  /* ================================================================
   * 19. Import form column-role assignment (delegated)
   * ================================================================ */

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".ace-role-btn");
    if (!btn) return;
    const form = btn.closest("#import-form");
    if (!form) return;
    let row = btn.closest(".ace-glimpse-row");
    let role = btn.dataset.role;
    const wasActive = btn.classList.contains("active");

    if (role === "id") {
      // Radio: clear all other IDs
      form.querySelectorAll('.ace-role-btn[data-role="id"].active').forEach(function (b) {
        b.classList.remove("active");
        b.closest(".ace-glimpse-row").dataset.role = b.closest(".ace-glimpse-row").querySelector('.ace-role-btn[data-role="text"].active') ? "text" : "";
      });
      // Clear text on this row if setting ID
      const textBtn = row.querySelector('.ace-role-btn[data-role="text"]');
      if (textBtn) { textBtn.classList.remove("active"); }
    } else {
      // Clear ID on this row if setting text
      const idBtn = row.querySelector('.ace-role-btn[data-role="id"]');
      if (idBtn) { idBtn.classList.remove("active"); }
    }

    if (wasActive) {
      btn.classList.remove("active");
      row.dataset.role = "";
    } else {
      btn.classList.add("active");
      row.dataset.role = role;
    }

    // Update hidden inputs
    const idRow = form.querySelector('.ace-role-btn[data-role="id"].active');
    document.getElementById("import-id-col").value = idRow ? idRow.closest(".ace-glimpse-row").dataset.col : "";

    const textCols = [];
    form.querySelectorAll('.ace-role-btn[data-role="text"].active').forEach(function (b) {
      textCols.push(b.closest(".ace-glimpse-row").dataset.col);
    });
    document.getElementById("import-text-cols").value = textCols.join(",");

    // Enable/disable submit
    document.getElementById("import-submit").disabled = !(idRow && textCols.length);
  });

  /* ================================================================
   * 20. DOMContentLoaded init
   * ================================================================ */

  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _initGridResize();
    _restoreCollapseState();
    _updateKeycaps();
    _initSortable();
    _paintSvg();
    _setAmbient();

    // Set initial roving tabindex — first treeitem gets tabindex="0"
    const items = _getTreeItems();
    if (items.length > 0) {
      items[0].setAttribute("tabindex", "0");
    }

    // Auto-focus first sentence so keyboard works immediately
    const sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    _focusTextPanel();
  });

  // Keep ambient status bar in sync after every HTMX swap.
  document.addEventListener("htmx:afterSettle", function () {
    _setAmbient();
  });

  /* ================================================================
   * 21. Source note drawer (READ / EDIT / closed)
   * ================================================================ */

  // Three implicit states derived from the DOM:
  //   closed — drawer hidden
  //   READ   — drawer open, textarea unfocused, shortcuts live
  //   EDIT   — drawer open, textarea focused, _isTyping() suppresses shortcuts
  //
  // html[data-ace-note-open="1"] — drawer open (persisted to localStorage so
  //   an inline <head> script can restore it before CSS loads — no flash)
  // html[data-ace-has-note="1"]  — rail dot amber (current source has a note)
  //
  // The EDIT mode visuals (amber ring, dimmed text) come from CSS
  // `:has(#note-textarea:focus)` — no JS mode flag. Focus IS the state.

  let _noteSaveTimer = null;
  let _noteInFlight = null;
  let _noteStatusClearTimer = null;
  let _previouslyFocused = null;

  function _noteEls() {
    return {
      drawer: document.getElementById("note-drawer"),
      textarea: document.getElementById("note-textarea"),
      status: document.getElementById("note-status"),
      pill: document.getElementById("note-pill"),
      rail: document.getElementById("note-rail"),
    };
  }

  function _isDrawerOpen() {
    return document.documentElement.dataset.aceNoteOpen === "1";
  }

  function _isEditing() {
    return document.activeElement?.id === "note-textarea";
  }

  function _setNoteStatus(text, sticky) {
    const { status } = _noteEls();
    if (!status) return;
    status.textContent = text;
    if (_noteStatusClearTimer) {
      clearTimeout(_noteStatusClearTimer);
      _noteStatusClearTimer = null;
    }
    if (!sticky && text) {
      _noteStatusClearTimer = setTimeout(function () {
        status.textContent = "";
      }, 1500);
    }
  }

  function _syncHasNoteAttribute() {
    const { pill } = _noteEls();
    if (pill && pill.classList.contains("ace-note-pill--has-note")) {
      document.documentElement.dataset.aceHasNote = "1";
    } else {
      delete document.documentElement.dataset.aceHasNote;
    }
  }

  function _flushAndBlurTextarea() {
    if (_noteSaveTimer) {
      clearTimeout(_noteSaveTimer);
      _noteSaveTimer = null;
      _doSaveNote();
    }
    const { textarea } = _noteEls();
    if (!textarea) return;
    if (document.activeElement === textarea) textarea.blur();
    textarea.setAttribute("tabindex", "-1");
  }

  function _restoreDrawerFocus() {
    if (_previouslyFocused && document.contains(_previouslyFocused) &&
        typeof _previouslyFocused.focus === "function") {
      _previouslyFocused.focus();
    } else {
      _focusTextPanel();
    }
  }

  function aceOpenNoteRead() {
    const { drawer, pill, rail } = _noteEls();
    if (!drawer) return;
    if (!_previouslyFocused) _previouslyFocused = document.activeElement;
    document.documentElement.dataset.aceNoteOpen = "1";
    drawer.setAttribute("aria-hidden", "false");
    if (pill) pill.setAttribute("aria-expanded", "true");
    if (rail) rail.setAttribute("aria-expanded", "true");
    try { localStorage.setItem("ace-note-open", "1"); } catch (_) {}
    // No focus change — READ mode leaves focus where it was so shortcuts stay live.
  }

  function aceEnterEditMode() {
    const { drawer, textarea } = _noteEls();
    if (!drawer || !textarea) return;
    if (!_isDrawerOpen()) aceOpenNoteRead();
    textarea.setAttribute("tabindex", "0");
    // Deferred so competing afterSettle/navigation handlers don't steal focus back.
    setTimeout(function () {
      textarea.focus();
      const n = textarea.value.length;
      textarea.setSelectionRange(n, n);
    }, 0);
  }

  function aceExitEditMode() {
    _flushAndBlurTextarea();
    _restoreDrawerFocus();
  }
  window.aceExitEditMode = aceExitEditMode;

  function aceCloseNote() {
    const { drawer, pill, rail } = _noteEls();
    if (!drawer) return;
    _flushAndBlurTextarea();
    delete document.documentElement.dataset.aceNoteOpen;
    drawer.setAttribute("aria-hidden", "true");
    if (pill) pill.setAttribute("aria-expanded", "false");
    if (rail) rail.setAttribute("aria-expanded", "false");
    try { localStorage.removeItem("ace-note-open"); } catch (_) {}
    _restoreDrawerFocus();
    _previouslyFocused = null;
  }
  window.aceCloseNote = aceCloseNote;

  function _scheduleNoteSave() {
    if (_noteSaveTimer) clearTimeout(_noteSaveTimer);
    _noteSaveTimer = setTimeout(_doSaveNote, 500);
  }

  function _doSaveNote() {
    _noteSaveTimer = null;
    const { textarea } = _noteEls();
    if (!textarea) return Promise.resolve();
    const sourceId = textarea.getAttribute("data-source-id");
    if (!sourceId) return Promise.resolve();
    const text = textarea.value;
    // Returns the same OOB payload as flag_route — pill, grid strip, and
    // status badge all refresh together.
    const promise = fetch("/api/source-note/" + encodeURIComponent(sourceId), {
      method: "PUT",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "note_text=" + encodeURIComponent(text),
    }).then(function (resp) {
      if (!resp.ok) throw new Error(resp.status);
      var ct = resp.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) return resp.json();
      return { has_note: !!text.trim() };
    }).then(function (data) {
      var pill = document.getElementById("note-pill");
      if (pill) {
        if (data.has_note) {
          pill.classList.add("ace-note-pill--has-note");
        } else {
          pill.classList.remove("ace-note-pill--has-note");
        }
      }
    }).catch(function (err) {
      if (err.name === "AbortError") return;
    });
    _noteInFlight = promise;
    return promise;
  }

  // Resolves once any pending or in-flight save is finished. Awaited by
  // aceNavigate so a full-page reload can't cancel a debounced save.
  function aceFlushNoteIfDirty() {
    if (_noteSaveTimer) {
      clearTimeout(_noteSaveTimer);
      _noteSaveTimer = null;
      return _doSaveNote();
    }
    if (_noteInFlight) return _noteInFlight;
    return Promise.resolve();
  }
  window.aceFlushNoteIfDirty = aceFlushNoteIfDirty;

  document.addEventListener("click", function (e) {
    if (e.target.closest("#note-pill")) {
      e.preventDefault();
      if (!_isDrawerOpen()) {
        aceOpenNoteRead();
      } else if (!_isEditing()) {
        aceEnterEditMode();
      }
      return;
    }
    if (e.target.closest("#note-rail")) {
      e.preventDefault();
      aceOpenNoteRead();
      return;
    }
  });

  document.addEventListener("input", function (e) {
    if (e.target.id === "note-textarea") {
      _scheduleNoteSave();
      if (e.target.value.length > 5000) {
        _setNoteStatus("Long note (over 5,000 characters)", true);
      }
    }
  });

  // Double-Esc pattern: first Esc exits EDIT back to READ, second closes
  // the drawer. Separate listener so it runs even when the textarea has
  // focus (the main keydown handler returns early via _isTyping()).
  // Defers to higher-priority Escape targets (cheat sheet, open dialog,
  // source grid overlay) so closing those doesn't also close the drawer.
  document.addEventListener("mousedown", function (e) {
    if (!_isDrawerOpen()) return;
    if (e.target.closest("#note-drawer") || e.target.closest("#note-pill") || e.target.closest("#note-rail")) return;
    aceCloseNote();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (!_isDrawerOpen()) return;
    if (document.getElementById("ace-cheat-sheet")) return;
    if (document.querySelector("dialog[open]")) return;
    e.preventDefault();
    if (_isEditing()) {
      aceExitEditMode();
    } else {
      aceCloseNote();
    }
  });

  document.body.addEventListener("htmx:afterSettle", function (evt) {
    const target = evt.detail && evt.detail.target;
    if (!target) return;
    if (target.id === "text-panel" || target.id === "coding-workspace") {
      if (_noteSaveTimer) { clearTimeout(_noteSaveTimer); _noteSaveTimer = null; }
      _noteInFlight = null;
      _syncHasNoteAttribute();
    }
  });

  // When the server OOB-swaps a fresh sources payload, re-render the
  // sparkline + tiles from the new data.
  document.body.addEventListener("htmx:oobAfterSwap", function (evt) {
    if (!evt.detail || !evt.detail.target) return;
    if (evt.detail.target.id === "ace-sources-data") {
      if (typeof window._aceRenderSourceGrid === "function") {
        window._aceRenderSourceGrid();
      }
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    _syncHasNoteAttribute();
    if (_isDrawerOpen()) {
      const { drawer, pill, rail } = _noteEls();
      if (drawer) drawer.setAttribute("aria-hidden", "false");
      if (pill) pill.setAttribute("aria-expanded", "true");
      if (rail) rail.setAttribute("aria-expanded", "true");
    }
  });

  /* ================================================================
   * 22. Source-grid collapse toggle
   * ================================================================ */

  /** Toggle the sidebar source-grid panel between expanded and collapsed. */
  function _aceToggleGridCollapse() {
    const wasCollapsed = document.documentElement.dataset.aceGridCollapsed === "1";
    const btn = document.getElementById("ace-grid-collapse-btn");
    if (wasCollapsed) {
      delete document.documentElement.dataset.aceGridCollapsed;
      try { localStorage.removeItem("ace-grid-collapsed"); } catch (_) {}
      if (btn) btn.setAttribute("aria-expanded", "true");
      // Re-render so the ResizeObserver picks up the restored height.
      if (typeof window._aceRenderSourceGrid === "function") {
        window._aceRenderSourceGrid();
      }
    } else {
      document.documentElement.dataset.aceGridCollapsed = "1";
      try { localStorage.setItem("ace-grid-collapsed", "1"); } catch (_) {}
      if (btn) btn.setAttribute("aria-expanded", "false");
    }
  }

  // Event delegation on document — survives HTMX OOB swaps that re-create
  // the button element.
  document.addEventListener("click", function (evt) {
    const btn = evt.target.closest("#ace-grid-collapse-btn");
    if (btn) {
      evt.preventDefault();
      _aceToggleGridCollapse();
    }
  });
})();
