/**
 * ACE Bridge — client-side utilities for the coding page.
 *
 * Sections:
 *  1. Toast notifications
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
 * 16. CSS Custom Highlight API — annotation rendering
 * 17. Sidebar keyboard navigation (ARIA treeview)
 * 18. DOMContentLoaded init
 */

(function () {
  "use strict";

  /* ================================================================
   * 1. Toast notifications
   * ================================================================ */

  window.aceToast = function (message, duration) {
    duration = duration || 3000;
    var container = document.getElementById("toast");
    if (!container) return;
    var el = document.createElement("div");
    el.className = "toast-msg";
    el.textContent = message;
    container.appendChild(el);
    setTimeout(function () {
      el.classList.add("fade-out");
      el.addEventListener("transitionend", function () { el.remove(); });
    }, duration);
  };

  document.addEventListener("htmx:afterRequest", function (e) {
    var msg = e.detail.xhr && e.detail.xhr.getResponseHeader("X-ACE-Toast");
    if (msg) window.aceToast(msg);
  });

  function _escapeHtml(str) {
    var div = document.createElement("div");
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
    var sentences = _getSentences();
    if (idx < 0 || idx >= sentences.length) return;

    // Remove old focus
    var old = document.querySelector(".ace-sentence--focused");
    if (old) old.classList.remove("ace-sentence--focused");

    // Set new focus
    window.__aceFocusIndex = idx;
    var el = sentences[idx];
    el.classList.add("ace-sentence--focused");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function _restoreFocus() {
    // Delay until after HTMX settling completes (outerHTML swap replaces DOM)
    requestAnimationFrame(function () {
      var idx = window.__aceFocusIndex;
      if (idx >= 0) _focusSentence(idx);
    });
  }

  /* ================================================================
   * 3. Group collapse / expand
   * ================================================================ */

  var _collapsedGroups = {};

  function _setGroupCollapsed(group, header, collapsed) {
    if (collapsed) {
      _collapseGroup(header);
    } else {
      _expandGroup(header);
    }
  }

  function _toggleGroupCollapse(header) {
    if (!header) return;
    var expanded = header.getAttribute("aria-expanded") === "true";
    if (expanded) {
      _collapseGroup(header);
    } else {
      _expandGroup(header);
    }
  }

  function _restoreCollapseState() {
    var headers = document.querySelectorAll(".ace-code-group-header");
    headers.forEach(function (header) {
      var groupName = header.getAttribute("data-group");
      if (_collapsedGroups[groupName]) {
        _collapseGroup(header);
      }
    });
  }

  // Click handler for group headers
  document.addEventListener("click", function (e) {
    var header = e.target.closest(".ace-code-group-header");
    if (header && !e.target.closest(".ace-code-menu")) {
      if (header.getAttribute("tabindex") === "0") {
        // Already focused — toggle collapse
        _toggleGroupCollapse(header);
      } else {
        // Not focused yet — just select it
        _focusTreeItem(header);
      }
    }
  });

  /* ================================================================
   * 4. Keymap — dynamic keycap assignment per tab
   * ================================================================ */

  var _currentKeyMap = []; // array of code IDs in keycap order

  function _updateKeycaps() {
    var tree = document.getElementById("code-tree");
    if (!tree) return;
    var rows = tree.querySelectorAll('.ace-code-row');
    _currentKeyMap = [];
    rows.forEach(function (row) {
      var groupDiv = row.closest('[role="group"]');
      if (groupDiv) {
        var header = groupDiv.previousElementSibling;
        if (header && header.getAttribute("aria-expanded") === "false") return;
      }
      // Also skip rows hidden by search filter
      if (row.style.display === "none") return;
      _currentKeyMap.push(row.getAttribute("data-code-id"));
      var keycap = row.querySelector(".ace-keycap");
      if (keycap) keycap.textContent = _keylabel(_currentKeyMap.length - 1);
      row.setAttribute("aria-keyshortcuts", _keylabel(_currentKeyMap.length - 1));
    });
  }

  function _keylabel(i) {
    if (i < 9) return "" + (i + 1);
    if (i === 9) return "0";
    if (i < 36) return String.fromCharCode(97 + i - 10);
    return "";
  }

  function _keyToPosition(key) {
    if (key >= "1" && key <= "9") return parseInt(key) - 1;
    if (key === "0") return 9;
    var c = key.toLowerCase().charCodeAt(0);
    if (c >= 97 && c <= 122) return c - 97 + 10;
    return -1;
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
    var sel = window.__aceLastSelection;
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
    document.querySelectorAll('.ace-code-row[data-code-id="' + codeId + '"]').forEach(function (r) {
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
    var el = document.activeElement;
    if (!el) return false;
    var tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
  }

  document.addEventListener("keydown", function (e) {
    if (_isTyping()) return;
    if (_menuOpen) return;

    // Only handle keys when text panel (or nothing specific) is focused
    var zone = _activeZone();
    if (zone === "search" || zone === "tree") return;

    var key = e.key;
    var ctrl = e.ctrlKey || e.metaKey;
    var shift = e.shiftKey;

    // Ctrl/Cmd+Shift+Z — Redo
    if (ctrl && shift && key === "Z") {
      e.preventDefault();
      _updateCurrentIndex();
      var redoBtn = document.getElementById("trigger-redo");
      if (redoBtn) htmx.trigger(redoBtn, "click");
      return;
    }

    // Ctrl/Cmd+Z — Undo
    if (ctrl && !shift && key === "z") {
      e.preventDefault();
      _updateCurrentIndex();
      var undoBtn = document.getElementById("trigger-undo");
      if (undoBtn) htmx.trigger(undoBtn, "click");
      return;
    }

    // Skip remaining if modifier keys held
    if (ctrl || e.altKey) return;

    // ↓ — Navigate to next sentence (or focus first if none focused)
    if (key === "ArrowDown") {
      e.preventDefault();
      var sentences = _getSentences();
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
      var sentencesUp = _getSentences();
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

    // F2 — Inline rename selected code
    if (key === "F2" && _lastSelectedCodeId) {
      e.preventDefault();
      _startInlineRename(_lastSelectedCodeId);
      return;
    }

    // Delete/Backspace — double-press to confirm delete selected code
    if ((key === "Delete" || key === "Backspace") && _lastSelectedCodeId && !shift && !ctrl) {
      e.preventDefault();
      if (_deleteTarget === _lastSelectedCodeId) {
        _executeDelete(_lastSelectedCodeId);
      } else {
        _startDeleteConfirm(_lastSelectedCodeId);
      }
      return;
    }

    // Z — Undo (no modifier needed in sentence mode)
    if ((key === "z" || key === "Z") && !ctrl) {
      e.preventDefault();
      _updateCurrentIndex();
      var undoBtn2 = document.getElementById("trigger-undo");
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
      var flagBtn = document.getElementById("trigger-flag");
      if (flagBtn) htmx.trigger(flagBtn, "click");
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
      var cheatSheet = document.getElementById("ace-cheat-sheet");
      if (cheatSheet) { cheatSheet.remove(); return; }

      var dialog = document.querySelector("dialog[open]");
      if (dialog) { dialog.close(); return; }

      var grid = document.getElementById("source-grid-overlay");
      if (grid && !grid.classList.contains("ace-hidden")) {
        grid.classList.add("ace-hidden");
        return;
      }

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
      var pos = _keyToPosition(key);
      if (pos >= 0 && pos < _currentKeyMap.length) {
        e.preventDefault();
        var codeId = _currentKeyMap[pos];
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
    var input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
  }

  /* ================================================================
   * 7. Navigation
   * ================================================================ */

  window.aceNavigate = function (index) {
    if (!Number.isFinite(index) || index < 0 || index >= window.__aceTotalSources) return;
    window.__aceCurrentIndex = index;
    window.__aceFocusIndex = -1;
    window.location.href = "/code?index=" + index;
  };

  window.aceNavigatePrev = function () {
    window.aceNavigate(window.__aceCurrentIndex - 1);
  };

  window.aceNavigateNext = function () {
    window.aceNavigate(window.__aceCurrentIndex + 1);
  };

  /* ================================================================
   * 8. Source grid overlay
   * ================================================================ */

  window.aceToggleGrid = function () {
    var grid = document.getElementById("source-grid-overlay");
    if (!grid) return;
    var wasHidden = grid.classList.contains("ace-hidden");
    grid.classList.toggle("ace-hidden");
    if (wasHidden) {
      // Adaptive cell size to fit within 300x300 popover
      var total = window.__aceTotalSources || 0;
      var popover = grid.querySelector(".ace-grid-popover");
      var innerSize = 300 - 12; // 300px minus 6px padding each side
      // Calculate cell size that fits all sources in a ~square grid within 288px
      var cols = Math.ceil(Math.sqrt(total)) || 1;
      var cellSize = Math.max(4, Math.min(10, Math.floor((innerSize - (cols - 1)) / cols)));
      if (popover) {
        popover.style.setProperty("--ace-grid-cell-size", cellSize + "px");
        var cellsContainer = popover.querySelector(".ace-grid-cells");
        if (cellsContainer) {
          // Snap width to exact multiple of (cellSize + 1px gap)
          var cellStep = cellSize + 1;
          var fitCols = Math.floor(innerSize / cellStep);
          cellsContainer.style.maxWidth = (fitCols * cellStep - 1) + "px";
        }
      }
      var maxWidth = 300;
      // Position anchored below the nav counter, clamped to viewport
      var counter = document.getElementById("nav-counter");
      if (counter) {
        var rect = counter.getBoundingClientRect();
        grid.style.top = (rect.bottom + 4) + "px";
        var idealLeft = rect.left + rect.width / 2 - maxWidth / 2;
        // Clamp so popover doesn't overflow right or left edge
        var clampedLeft = Math.max(4, Math.min(idealLeft, window.innerWidth - maxWidth - 8));
        grid.style.left = clampedLeft + "px";
      }
      // Close on click outside (next tick)
      setTimeout(function () {
        document.addEventListener("click", _onGridOutsideClick);
      }, 0);
    } else {
      document.removeEventListener("click", _onGridOutsideClick);
    }
  };

  function _onGridOutsideClick(e) {
    var grid = document.getElementById("source-grid-overlay");
    if (grid && !grid.contains(e.target) && !e.target.closest(".ace-nav-counter")) {
      grid.classList.add("ace-hidden");
      document.removeEventListener("click", _onGridOutsideClick);
    }
  }

  /* ================================================================
   * 9. Cheat sheet overlay
   * ================================================================ */

  function _toggleCheatSheet() {
    var existing = document.getElementById("ace-cheat-sheet");
    if (existing) { existing.remove(); return; }

    var overlay = document.createElement("div");
    overlay.id = "ace-cheat-sheet";
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;" +
      "justify-content:center;background:rgba(0,0,0,0.45);";

    var card = document.createElement("div");
    card.style.cssText =
      "background:var(--ace-bg,#fff);border:1px solid var(--ace-border,#bdbdbd);" +
      "padding:24px 32px;max-width:520px;width:90%;max-height:80vh;overflow-y:auto;" +
      "font-size:13px;line-height:1.6;";

    card.innerHTML =
      '<h3 style="margin:0 0 12px;font-size:15px;font-weight:600;">Keyboard shortcuts</h3>' +
      '<table style="width:100%;border-collapse:collapse;">' +
      _shortcutRow("↑ / ↓", "Navigate sentences") +
      _shortcutRow("← / →", "Previous / next source") +
      _shortcutRow("Shift + ← / →", "Jump 5 sources") +
      _shortcutRow("1 – 9, 0, a – z", "Apply code (per tab)") +
      _shortcutRow("Q", "Repeat last code") +
      _shortcutRow("X", "Remove code from sentence") +
      _shortcutRow("Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Shift + Z", "Redo") +
      _shortcutRow("Shift + F", "Flag/unflag source") +
      _shortcutRow("F2", "Rename selected code") +
      _shortcutRow("Delete", "Delete selected code (press twice)") +
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
    return '<tr style="border-bottom:1px solid var(--ace-border-light,#e0e0e0);">'
      + '<td style="padding:4px 12px 4px 0;font-family:\'SF Mono\',Menlo,Consolas,monospace;'
      + 'font-size:12px;white-space:nowrap;color:var(--ace-text-muted,#777);">' + key + "</td>"
      + '<td style="padding:4px 0;">' + desc + "</td></tr>";
  }

  /* ================================================================
   * 10. Resize handle
   * ================================================================ */

  function _initResize() {
    var handle = document.getElementById("resize-handle");
    if (!handle) return;
    var split = handle.closest(".ace-three-col");
    if (!split) return;

    var dragging = false;

    handle.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      dragging = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var rect = split.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var min = 150;
      var max = rect.width * 0.4;
      x = Math.max(min, Math.min(max, x));
      document.documentElement.style.setProperty("--ace-sidebar-width", x + "px");
    });

    document.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      var width = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--ace-sidebar-width"), 10);
      if (width) localStorage.setItem("ace-sidebar-width", width);
    });
  }

  /* ================================================================
   * 11. Dialog close cleanup
   * ================================================================ */

  document.addEventListener("close", function (evt) {
    if (evt.target.tagName === "DIALOG") {
      var container = document.getElementById("modal-container");
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
    var container = document.querySelector(".ace-text-panel");
    if (!container) return;

    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      window.__aceLastSelection = null;
      return;
    }

    var range = sel.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      return;
    }

    var text = sel.toString();
    if (!text) { window.__aceLastSelection = null; return; }

    // Find the sentence spans containing the selection endpoints
    var startSrc = _sourceOffset(range.startContainer, range.startOffset);
    var endSrc = _sourceOffset(range.endContainer, range.endOffset);

    if (startSrc < 0 || endSrc < 0 || startSrc === endSrc) {
      window.__aceLastSelection = null;
      return;
    }

    window.__aceLastSelection = { start: startSrc, end: endSrc, text: text };
  });

  function _sourceOffset(node, domOffset) {
    // Walk up to find the containing .ace-sentence span
    var el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    var sentence = el.closest(".ace-sentence");
    if (!sentence) return -1;

    var sentStart = parseInt(sentence.dataset.start, 10);
    if (isNaN(sentStart)) return -1;

    // Compute character offset within this sentence's text content
    var walker = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
    var charPos = 0;
    var current;
    while ((current = walker.nextNode())) {
      if (current === node) return sentStart + charPos + domOffset;
      charPos += current.textContent.length;
    }
    // Fallback: if node is the sentence element itself, use domOffset as child index
    return sentStart + domOffset;
  }

  // Click on sentence to focus it
  document.addEventListener("click", function (e) {
    var sentence = e.target.closest(".ace-sentence");
    if (sentence) {
      var idx = parseInt(sentence.dataset.idx, 10);
      if (!isNaN(idx)) {
        _focusSentence(idx);
        // Clear custom selection if this was a simple click (not drag)
        if (!window.__aceLastSelection) {
          window.getSelection().removeAllRanges();
        }
      }
    }

    // Click on code chip to flash corresponding text ranges
    var chip = e.target.closest(".ace-code-chip");
    if (chip) {
      var codeId = chip.dataset.codeId;
      var colour = chip.dataset.colour || "#ffeb3b";
      var r = parseInt(colour.slice(1, 3), 16);
      var g = parseInt(colour.slice(3, 5), 16);
      var b = parseInt(colour.slice(5, 7), 16);

      if (!CSS.highlights) return;
      var container = document.getElementById("text-panel");
      if (!container) return;
      var dataEl = document.getElementById("ace-ann-data");
      if (!dataEl) return;
      var anns = JSON.parse(dataEl.dataset.annotations || "[]");
      var matching = anns.filter(function (a) { return a.code_id === codeId; });
      if (!matching.length) return;

      // Build ranges using the same text index as _paintHighlights
      var textIndex = _buildTextIndex(container);
      var flashHighlight = new Highlight();
      var firstRange = null;
      matching.forEach(function (ann) {
        var startPos = _findDOMPosition(textIndex, ann.start);
        var endPos = _findDOMPosition(textIndex, ann.end);
        if (!startPos || !endPos) return;
        try {
          var range = new Range();
          range.setStart(startPos.node, startPos.offset);
          range.setEnd(endPos.node, endPos.offset);
          flashHighlight.add(range);
          if (!firstRange) firstRange = range;
        } catch (ex) {}
      });

      // Register flash highlight + inject style
      CSS.highlights.set("ace-flash", flashHighlight);
      var style = document.createElement("style");
      style.id = "ace-flash-style";
      style.textContent = "::highlight(ace-flash) { background-color: rgba(" + r + "," + g + "," + b + ",0.6); }";
      var old = document.getElementById("ace-flash-style");
      if (old) old.remove();
      document.head.appendChild(style);

      // Scroll first match into view
      if (firstRange) {
        var startEl = firstRange.startContainer.parentElement;
        if (startEl) startEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      // Remove after 1.5s
      setTimeout(function () {
        CSS.highlights.delete("ace-flash");
        var s = document.getElementById("ace-flash-style");
        if (s) s.remove();
      }, 1500);
    }
  });

  // --- Focus restoration across HTMX swaps ---

  var _sidebarFocusState = {
    codeId: null,
    searchText: "",
    scrollTop: 0,
    zone: null,
  };

  document.addEventListener("htmx:beforeSwap", function (e) {
    var target = e.detail.target;
    if (!target) return;
    if (target.id !== "code-sidebar" && target.id !== "coding-workspace") return;

    var zone = _activeZone();
    _sidebarFocusState.zone = zone;

    if (zone === "tree") {
      var active = _getActiveTreeItem();
      _sidebarFocusState.codeId = active ? active.getAttribute("data-code-id") : null;
    }

    var search = document.getElementById("code-search-input");
    _sidebarFocusState.searchText = search ? search.value : "";

    var tree = document.getElementById("code-tree");
    _sidebarFocusState.scrollTop = tree ? tree.scrollTop : 0;
  });

  // After HTMX swap: restore focus, rebuild tabs, update keycaps
  // Use afterSettle (not afterSwap) — fires after HTMX finishes all DOM changes
  document.addEventListener("htmx:afterSettle", function (evt) {
    var target = evt.detail.target;
    if (!target) return;

    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _restoreFocus();
      _paintHighlights();
    }

    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      if (!_isDragging) _initSortable();
      _restoreCollapseState();
      _updateKeycaps();

      // Restore focus state
      var search = document.getElementById("code-search-input");
      if (_sidebarFocusState.searchText && search) {
        search.value = _sidebarFocusState.searchText;
        search.dispatchEvent(new Event("input"));
      }

      var tree = document.getElementById("code-tree");
      if (tree && _sidebarFocusState.scrollTop) {
        tree.scrollTop = _sidebarFocusState.scrollTop;
      }

      if (_sidebarFocusState.zone === "tree" && _sidebarFocusState.codeId) {
        var item = tree ? tree.querySelector('[data-code-id="' + _sidebarFocusState.codeId + '"]') : null;
        if (item) {
          _focusTreeItem(item);
        } else {
          // Deleted or gone — focus nearest item
          var items = _getTreeItems();
          if (items.length > 0) _focusTreeItem(items[0]);
        }
      } else if (_sidebarFocusState.zone === "search" && search) {
        search.focus();
      }

      // Reset
      _sidebarFocusState.codeId = null;
      _sidebarFocusState.zone = null;
    }

    // Auto-open dialogs
    if (target.id === "modal-container") {
      var dialog = target.querySelector("dialog");
      if (dialog && !dialog.open) dialog.showModal();
    }
  });

  // Inject current_index into undo/redo/flag hidden trigger requests
  document.addEventListener("htmx:configRequest", function (e) {
    var elt = e.detail.elt;
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
    var detail = e.detail || {};
    if (detail.index !== undefined) {
      window.__aceCurrentIndex = parseInt(detail.index, 10);
    }
    if (detail.total !== undefined) {
      window.__aceTotalSources = parseInt(detail.total, 10);
    }
    window.__aceFocusIndex = -1;
    var input = document.getElementById("current-index");
    if (input) input.value = window.__aceCurrentIndex;
    // Reset scroll position for new source
    var cs = document.getElementById("content-scroll");
    if (cs) cs.scrollTop = 0;
  });

  /* ================================================================
   * 13. Code management helpers
   * ================================================================ */

  var _menuOpen = false;
  var _lastSelectedCodeId = null;

  // No-op stubs — replaced by real implementations in later tasks
  function _closeCodeMenu() {}

  var _COLOUR_PALETTE = ["#A91818","#557FE6","#6DA918","#E655D4","#18A991","#E6A455","#3C18A9","#5BE655","#A91848","#55B0E6","#9DA918","#C855E6","#18A960","#E67355","#1824A9","#8CE655","#A91879","#55E1E6","#A98418","#9755E6","#18A930","#E65567","#1855A9","#BCE655","#A918A9","#55E6BB","#A95418","#6755E6","#30A918","#E65598","#1885A9","#E6E055","#7818A9","#55E68B","#A92318","#5574E6"];

  var _activeColourPopover = null;

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
    var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
    if (!row) return;
    var dot = row.querySelector(".ace-code-dot");
    if (!dot) return;
    var rect = dot.getBoundingClientRect();

    var popover = document.createElement("div");
    popover.className = "ace-colour-popover";

    _COLOUR_PALETTE.forEach(function (hex) {
      var swatch = document.createElement("button");
      swatch.className = "ace-colour-swatch";
      swatch.style.background = hex;
      swatch.addEventListener("click", function () {
        _closeAllPopovers();
        _codeAction("PUT", "/api/codes/" + codeId,
          "colour=" + encodeURIComponent(hex) + "&current_index=" + window.__aceCurrentIndex);
      });
      popover.appendChild(swatch);
    });

    document.body.appendChild(popover);
    _activeColourPopover = popover;

    popover.style.top = (rect.bottom + 4) + "px";
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

  document.addEventListener("click", function (e) {
    var dot = e.target.closest(".ace-code-dot");
    if (!dot) return;
    var row = dot.closest(".ace-code-row");
    if (!row) return;
    e.stopPropagation();
    var codeId = row.getAttribute("data-code-id");
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
      if (!r.ok) { window.aceToast("Action failed"); return Promise.reject(); }
      _refreshSidebar();
    });
  }

  function _startInlineRename(codeId) {
    var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
    if (!row) return;
    var nameEl = row.querySelector(".ace-code-name");
    if (!nameEl) return;

    var original = nameEl.textContent;
    nameEl.contentEditable = "true";
    nameEl.focus();

    var range = document.createRange();
    range.selectNodeContents(nameEl);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    var done = false;
    function save() {
      if (done) return;
      done = true;
      var newName = nameEl.textContent.trim();
      nameEl.contentEditable = "false";
      if (!newName || newName === original) {
        nameEl.textContent = original;
        _focusTreeItem(row);
        return;
      }
      _codeAction("PUT", "/api/codes/" + codeId,
        "name=" + encodeURIComponent(newName) + "&current_index=" + window.__aceCurrentIndex
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
      var text = (e.clipboardData || window.clipboardData).getData("text/plain");
      document.execCommand("insertText", false, text.replace(/\n/g, " "));
    });
  }

  document.addEventListener("dblclick", function (e) {
    var nameEl = e.target.closest(".ace-code-name");
    if (!nameEl) return;
    var row = nameEl.closest(".ace-code-row");
    if (!row) return;
    var codeId = row.getAttribute("data-code-id");
    if (codeId) _startInlineRename(codeId);
  });

  var _deleteTarget = null;
  var _deleteTimer = null;

  function _startDeleteConfirm(codeId) {
    if (_deleteTimer) { clearTimeout(_deleteTimer); _clearDeleteConfirm(); }
    var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
    if (!row) return;
    row.classList.add("ace-code-row--confirm-delete");
    _deleteTarget = codeId;
    _deleteTimer = setTimeout(function () { _clearDeleteConfirm(); }, 2000);
  }

  function _clearDeleteConfirm() {
    if (_deleteTarget) {
      var row = document.querySelector('.ace-code-row[data-code-id="' + _deleteTarget + '"]');
      if (row) row.classList.remove("ace-code-row--confirm-delete");
    }
    _deleteTarget = null;
    if (_deleteTimer) { clearTimeout(_deleteTimer); _deleteTimer = null; }
  }

  function _executeDelete(codeId) {
    _clearDeleteConfirm();
    _lastSelectedCodeId = null;
    _codeAction("DELETE", "/api/codes/" + codeId + "?current_index=" + window.__aceCurrentIndex, null);
  }

  function _moveCode(codeId, direction) {
    var codes = window.__aceCodes || [];
    var ids = codes.map(function (c) { return c.id; });
    var idx = ids.indexOf(codeId);
    if (idx < 0) return;
    var newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= ids.length) return;
    ids[idx] = ids[newIdx];
    ids[newIdx] = codeId;
    _codeAction("POST", "/api/codes/reorder",
      "code_ids=" + encodeURIComponent(JSON.stringify(ids)) + "&current_index=" + window.__aceCurrentIndex);
  }

  function _moveToGroup(codeId, groupName) {
    _codeAction("PUT", "/api/codes/" + codeId,
      "group_name=" + encodeURIComponent(groupName) + "&current_index=" + window.__aceCurrentIndex);
  }

  var _sortableInstances = [];
  var _isDragging = false;

  function _initSortable() {
    _sortableInstances.forEach(function (s) { s.destroy(); });
    _sortableInstances = [];

    var containers = document.querySelectorAll('#code-tree [role="group"]');
    containers.forEach(function (container) {
      var instance = new Sortable(container, {
        group: "codes",
        animation: 150,
        delay: 200,
        delayOnTouchOnly: true,
        draggable: ".ace-code-row",
        ghostClass: "ace-code-row--ghost",
        onStart: function () { _isDragging = true; },
        onEnd: function (evt) {
          _isDragging = false;
          var codeId = evt.item.getAttribute("data-code-id");
          var newHeader = evt.to.previousElementSibling;
          var newGroup = newHeader ? (newHeader.getAttribute("data-group") || "") : "";
          var oldHeader = evt.from.previousElementSibling;
          var oldGroup = oldHeader ? (oldHeader.getAttribute("data-group") || "") : "";

          if (newGroup !== oldGroup && codeId) {
            fetch("/api/codes/" + codeId, {
              method: "PUT",
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              body: "group_name=" + encodeURIComponent(newGroup) + "&current_index=" + window.__aceCurrentIndex,
            });
          }

          var allRows = document.querySelectorAll("#code-tree .ace-code-row");
          var ids = [];
          allRows.forEach(function (row) {
            var id = row.getAttribute("data-code-id");
            if (id) ids.push(id);
          });

          _codeAction("POST", "/api/codes/reorder",
            "code_ids=" + encodeURIComponent(JSON.stringify(ids)) + "&current_index=" + window.__aceCurrentIndex);
        },
      });
      _sortableInstances.push(instance);
    });
  }

  /* ================================================================
   * 14. Code menu dropdown (right-click context menu)
   * ================================================================ */

  var _activeCodeMenu = null;

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

    var menu = document.createElement("div");
    menu.className = "ace-code-menu";

    var items = [
      { label: "Rename", hint: "F2", action: function () { _closeCodeMenu(); _startInlineRename(codeId); } },
      { label: "Colour", hint: "", action: function () { _closeCodeMenu(); _openColourPopover(codeId); } },
      { label: "Move Up", hint: "Alt+Shift+\u2191", action: function () { _closeCodeMenu(); _moveCode(codeId, -1); } },
      { label: "Move Down", hint: "Alt+Shift+\u2193", action: function () { _closeCodeMenu(); _moveCode(codeId, 1); } },
      { label: "Delete", hint: "\u232b", danger: true, action: function () { _closeCodeMenu(); _startDeleteConfirm(codeId); } },
    ];

    // Add "Move to Group" submenu if groups exist
    var groups = _getGroupNames();
    if (groups.length > 0 || true) {  // always show (Ungrouped option is useful)
      var moveItem = document.createElement("div");
      moveItem.className = "ace-code-menu-item ace-code-menu-sub";
      moveItem.textContent = "Move to Group \u25b8";
      var moveHint = document.createElement("span");
      moveHint.className = "ace-code-menu-hint";
      moveHint.textContent = "Alt+\u2192";
      moveItem.appendChild(moveHint);
      var sub = document.createElement("div");
      sub.className = "ace-code-submenu";

      var ungrouped = document.createElement("button");
      ungrouped.className = "ace-code-menu-item";
      ungrouped.textContent = "Ungrouped";
      ungrouped.addEventListener("click", function () { _closeCodeMenu(); _moveToGroup(codeId, ""); });
      sub.appendChild(ungrouped);

      groups.forEach(function (gn) {
        var btn = document.createElement("button");
        btn.className = "ace-code-menu-item";
        btn.textContent = gn;
        btn.addEventListener("click", function () { _closeCodeMenu(); _moveToGroup(codeId, gn); });
        sub.appendChild(btn);
      });

      moveItem.appendChild(sub);
      // Insert after Colour, before Move Up
      items.splice(2, 0, { element: moveItem });
    }

    items.forEach(function (item) {
      if (item.element) { menu.appendChild(item.element); return; }
      var el = document.createElement("button");
      el.className = "ace-code-menu-item";
      if (item.danger) el.classList.add("ace-code-menu-item--danger");
      el.textContent = item.label;
      if (item.hint) {
        var hintEl = document.createElement("span");
        hintEl.className = "ace-code-menu-hint";
        hintEl.textContent = item.hint;
        el.appendChild(hintEl);
      }
      el.addEventListener("click", item.action);
      menu.appendChild(el);
    });

    document.body.appendChild(menu);
    _activeCodeMenu = menu;

    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    menu.style.top = (y + mh > window.innerHeight ? Math.max(0, y - mh) : y) + "px";
    menu.style.left = (x + mw > window.innerWidth ? Math.max(0, x - mw) : x) + "px";

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
    var result = [];
    document.querySelectorAll("#code-tree .ace-code-group-header[data-group]").forEach(function (h) {
      var name = h.getAttribute("data-group");
      if (name) result.push(name);
    });
    return result;
  }

  // Right-click context menu delegation
  document.addEventListener("contextmenu", function (e) {
    var row = e.target.closest(".ace-code-row");
    if (!row) return;
    e.preventDefault();
    var codeId = row.getAttribute("data-code-id");
    if (codeId) _openCodeMenu(e.clientX, e.clientY, codeId);
  });

  /* ================================================================
   * 15. Code search / filter / create
   * ================================================================ */

  document.addEventListener("input", function (e) {
    if (e.target.id !== "code-search-input") return;
    var query = e.target.value.toLowerCase();
    var tree = document.getElementById("code-tree");
    if (!tree) return;

    // Remove any existing "create" prompt
    var oldPrompt = tree.querySelector(".ace-create-prompt");
    if (oldPrompt) oldPrompt.remove();

    if (query && !query.startsWith("/")) {
      // Filter mode
      var rows = tree.querySelectorAll(".ace-code-row");
      var anyMatch = false;
      rows.forEach(function (row) {
        var nameEl = row.querySelector(".ace-code-name");
        if (!nameEl) return;
        var text = nameEl.textContent;
        var match = text.toLowerCase().indexOf(query) >= 0;
        if (match) {
          row.style.display = "";
          anyMatch = true;
          // Highlight match
          var idx = text.toLowerCase().indexOf(query);
          var before = text.substring(0, idx);
          var matched = text.substring(idx, idx + query.length);
          var after = text.substring(idx + query.length);
          nameEl.innerHTML = _escapeHtml(before) + '<mark>' + _escapeHtml(matched) + '</mark>' + _escapeHtml(after);
        } else {
          row.style.display = "none";
          nameEl.textContent = text; // Strip any existing highlight
        }
      });

      // Show/hide group headers based on visible children
      tree.querySelectorAll(".ace-code-group-header").forEach(function (header) {
        var groupDiv = header.nextElementSibling;
        if (!groupDiv || groupDiv.getAttribute("role") !== "group") return;
        var hasVisible = false;
        groupDiv.querySelectorAll(".ace-code-row").forEach(function (r) {
          if (r.style.display !== "none") hasVisible = true;
        });
        header.style.display = hasVisible ? "" : "none";
        groupDiv.style.display = hasVisible ? "" : "none";
      });

      // Show "Create" prompt if no matches
      if (!anyMatch) {
        var prompt = document.createElement("div");
        prompt.className = "ace-create-prompt ace-create-prompt--code";
        prompt.innerHTML = '<span>+</span> Create "<strong>' + _escapeHtml(e.target.value.trim()) + '</strong>"';
        prompt.setAttribute("data-action", "create-code");
        prompt.addEventListener("click", function () {
          _createCodeFromSearch();
        });
        tree.appendChild(prompt);
      }
    } else if (query && query.startsWith("/")) {
      // Group creation mode
      var groupName = query.substring(1).trim();
      // Hide all codes, show group creation prompt
      tree.querySelectorAll(".ace-code-row").forEach(function (r) { r.style.display = "none"; });
      tree.querySelectorAll(".ace-code-group-header").forEach(function (h) { h.style.display = "none"; });
      tree.querySelectorAll('[role="group"]').forEach(function (g) { g.style.display = "none"; });

      if (groupName) {
        var exists = false;
        tree.querySelectorAll(".ace-code-group-header").forEach(function (h) {
          if (h.getAttribute("data-group") === groupName) exists = true;
        });

        var prompt = document.createElement("div");
        if (exists) {
          prompt.className = "ace-create-prompt";
          prompt.innerHTML = 'Group "<strong>' + _escapeHtml(groupName) + '</strong>" already exists';
        } else {
          prompt.className = "ace-create-prompt ace-create-prompt--group";
          prompt.innerHTML = '<span>\u25b8</span> Create group "<strong>' + _escapeHtml(groupName) + '</strong>"';
          prompt.setAttribute("data-action", "create-group");
          prompt.addEventListener("click", function () {
            _createGroupFromSearch();
          });
        }
        tree.appendChild(prompt);
      }
    } else {
      // Empty: restore all rows, clear highlights
      tree.querySelectorAll(".ace-code-row").forEach(function (row) {
        row.style.display = "";
        var nameEl = row.querySelector(".ace-code-name");
        if (nameEl && nameEl.querySelector("mark")) {
          nameEl.textContent = nameEl.textContent; // Strip HTML
        }
      });
      tree.querySelectorAll(".ace-code-group-header").forEach(function (h) { h.style.display = ""; });
      tree.querySelectorAll('[role="group"]').forEach(function (g) { g.style.display = ""; });
      _restoreCollapseState();
    }

    _updateKeycaps();
  });

  function _createCodeFromSearch() {
    var input = document.getElementById("code-search-input");
    if (!input) return;
    var name = input.value.trim();
    if (!name || name.startsWith("/")) return;

    htmx.ajax("POST", "/api/codes", {
      values: { name: name, current_index: window.__aceCurrentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
    });
    input.value = "";
    _announce("Code '" + name + "' created");
  }

  function _createGroupFromSearch() {
    var input = document.getElementById("code-search-input");
    if (!input) return;
    var groupName = input.value.trim().substring(1).trim(); // remove / prefix
    if (!groupName) return;

    var tree = document.getElementById("code-tree");
    if (!tree) return;

    // Remove create prompt if present
    var ref = tree.querySelector(".ace-create-prompt");
    if (ref) ref.remove();

    var header = document.createElement("div");
    header.setAttribute("role", "treeitem");
    header.setAttribute("aria-expanded", "true");
    header.setAttribute("aria-level", "1");
    header.className = "ace-code-group-header";
    header.setAttribute("data-group", groupName);
    header.setAttribute("tabindex", "-1");
    header.textContent = "\u25be " + groupName;

    var groupDiv = document.createElement("div");
    groupDiv.setAttribute("role", "group");

    var emptyMsg = tree.querySelector(".ace-sidebar-empty");
    if (emptyMsg) {
      tree.insertBefore(header, emptyMsg);
      tree.insertBefore(groupDiv, emptyMsg);
      emptyMsg.remove();
    } else {
      tree.appendChild(header);
      tree.appendChild(groupDiv);
    }

    input.value = "";
    input.dispatchEvent(new Event("input"));
    _initSortable();
    _announce("Group '" + groupName + "' created");
  }

  document.addEventListener("keydown", function (e) {
    if (e.target.id !== "code-search-input") return;

    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      if (e.target.value) {
        e.target.value = "";
        e.target.dispatchEvent(new Event("input"));
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
    var val = e.target.value.trim();
    if (!val) return;
    e.preventDefault();

    if (val.startsWith("/")) {
      _createGroupFromSearch();
    } else {
      // Only create if no visible code rows
      var tree = document.getElementById("code-tree");
      var count = 0;
      if (tree) {
        tree.querySelectorAll(".ace-code-row").forEach(function (r) {
          if (r.style.display !== "none") count++;
        });
      }
      if (count === 0) {
        _createCodeFromSearch();
      } else {
        // Has matches — clear and return
        e.target.value = "";
        e.target.dispatchEvent(new Event("input"));
        _focusTextPanel();
      }
    }
  });

  /* ================================================================
   * 16. CSS Custom Highlight API — annotation rendering
   * ================================================================ */

  /**
   * Build a flat list of {node, sourceStart, sourceEnd} entries
   * for all text nodes inside sentence spans in the text panel.
   */
  function _buildTextIndex(container) {
    var index = [];
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var sentence = node.parentElement.closest(".ace-sentence");
      if (!sentence) continue;
      var sentStart = parseInt(sentence.dataset.start, 10);
      if (isNaN(sentStart)) continue;

      var charsBefore = 0;
      var tw = document.createTreeWalker(sentence, NodeFilter.SHOW_TEXT, null);
      var t;
      while ((t = tw.nextNode())) {
        if (t === node) break;
        charsBefore += t.textContent.length;
      }

      var nodeSourceStart = sentStart + charsBefore;
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
    for (var i = 0; i < textIndex.length; i++) {
      var entry = textIndex[i];
      if (sourceOffset >= entry.sourceStart && sourceOffset <= entry.sourceEnd) {
        return { node: entry.node, offset: sourceOffset - entry.sourceStart };
      }
    }
    return null;
  }

  /**
   * Paint all annotation highlights using the CSS Custom Highlight API.
   * Reads annotation data from the hidden #ace-ann-data element,
   * groups by code_id, and registers CSS highlights.
   */
  function _paintHighlights() {
    if (!CSS.highlights) return;
    CSS.highlights.clear();

    // Read annotation data from DOM element (updated by OOB swaps)
    var dataEl = document.getElementById("ace-ann-data");
    if (!dataEl) return;
    var annotations = JSON.parse(dataEl.dataset.annotations || "[]");
    if (!annotations.length) return;

    var container = document.getElementById("text-panel");
    if (!container) return;

    var textIndex = _buildTextIndex(container);
    if (!textIndex.length) return;

    // Group ranges by code_id
    var groups = {};
    for (var i = 0; i < annotations.length; i++) {
      var ann = annotations[i];
      var startPos = _findDOMPosition(textIndex, ann.start);
      var endPos = _findDOMPosition(textIndex, ann.end);
      if (!startPos || !endPos) continue;

      try {
        var range = new Range();
        range.setStart(startPos.node, startPos.offset);
        range.setEnd(endPos.node, endPos.offset);

        // If the range ends at a sentence boundary, extend to cover
        // the trailing whitespace text node (bridges the gap between spans)
        var endSentence = endPos.node.parentElement.closest(".ace-sentence");
        if (endSentence && ann.end >= parseInt(endSentence.dataset.end, 10)) {
          var next = endSentence.nextSibling;
          if (next && next.nodeType === Node.TEXT_NODE) {
            range.setEndAfter(next);
          }
        }

        var codeId = ann.code_id;
        if (!groups[codeId]) groups[codeId] = [];
        groups[codeId].push(range);
      } catch (e) {
        // Invalid range (e.g. end before start) — skip
      }
    }

    // Register highlights
    for (var codeId in groups) {
      if (!groups.hasOwnProperty(codeId)) continue;
      var highlight = new Highlight();
      for (var j = 0; j < groups[codeId].length; j++) {
        highlight.add(groups[codeId][j]);
      }
      CSS.highlights.set("ace-hl-" + codeId, highlight);
    }
  }

  /* ================================================================
   * 17. Sidebar keyboard navigation (ARIA treeview)
   * ================================================================ */

  /** Push a message to the aria-live region for screen readers. */
  function _announce(message) {
    var region = document.getElementById("ace-live-region");
    if (!region) return;
    region.textContent = message;
    setTimeout(function () { region.textContent = ""; }, 3000);
  }

  // --- Zone cycling (Tab / Shift+Tab / Escape / /) ---

  /** Move focus to text panel. */
  function _focusTextPanel() {
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  }

  /** Move focus to search bar. */
  function _focusSearchBar() {
    var sb = document.getElementById("code-search-input");
    if (sb) sb.focus();
  }

  /** Move focus into the code tree (last-focused item or first item). */
  function _focusCodeTree() {
    var active = _getActiveTreeItem();
    if (active) {
      active.focus();
    } else {
      var items = _getTreeItems();
      if (items.length > 0) _focusTreeItem(items[0]);
    }
  }

  /** Determine which zone currently has focus: "text", "search", "tree", or null. */
  function _activeZone() {
    var el = document.activeElement;
    if (!el) return null;
    if (el.id === "text-panel" || el.closest("#text-panel")) return "text";
    if (el.id === "code-search-input") return "search";
    var tree = document.getElementById("code-tree");
    if (tree && tree.contains(el)) return "tree";
    return null;
  }

  // Zone-level Tab cycling — captures Tab before browser default
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;

    var zone = _activeZone();
    if (!zone) return;

    if (!e.shiftKey) {
      // Tab forward
      if (zone === "text") { e.preventDefault(); _focusSearchBar(); return; }
      if (zone === "search") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "tree") { e.preventDefault(); _focusTextPanel(); return; }
    } else {
      // Shift+Tab backward
      if (zone === "text") { e.preventDefault(); _focusCodeTree(); return; }
      if (zone === "search") { e.preventDefault(); _focusTextPanel(); return; }
      if (zone === "tree") { e.preventDefault(); _focusSearchBar(); return; }
    }
  }, true);  // capture phase to intercept before default Tab behaviour

  // --- Roving tabindex ---

  /** Return all visible treeitems (group headers + code rows) in DOM order. */
  function _getTreeItems() {
    var tree = document.getElementById("code-tree");
    if (!tree) return [];
    var items = tree.querySelectorAll('[role="treeitem"]');
    var result = [];
    items.forEach(function (item) {
      if (item.classList.contains("ace-code-row")) {
        var header = item.closest('[role="group"]');
        if (header) {
          var prev = header.previousElementSibling;
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
    var tree = document.getElementById("code-tree");
    if (tree) {
      tree.querySelectorAll('[tabindex="0"]').forEach(function (el) {
        el.setAttribute("tabindex", "-1");
      });
    }
    item.setAttribute("tabindex", "0");
    item.focus();
  }

  /** Get the currently focused treeitem (tabindex="0"). */
  function _getActiveTreeItem() {
    var tree = document.getElementById("code-tree");
    return tree ? tree.querySelector('[role="treeitem"][tabindex="0"]') : null;
  }

  /** Check if a treeitem is a group header. */
  function _isGroupHeader(item) {
    return item && item.classList.contains("ace-code-group-header");
  }

  /** Move a group (header + group div) up or down by one position. */
  function _moveGroupInDirection(header, direction) {
    var groupDiv = header.nextElementSibling;
    if (!groupDiv || groupDiv.getAttribute("role") !== "group") return;
    var tree = document.getElementById("code-tree");
    if (!tree) return;

    if (direction === -1) {
      // Move up: find the previous group's header.
      // The element immediately before `header` is either a role="group" div
      // (from the previous group) or directly a group header (empty group).
      var prevSibling = header.previousElementSibling;
      if (!prevSibling) return;
      var prevHeader;
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
      var nextHeader = groupDiv.nextElementSibling;
      if (!nextHeader || !_isGroupHeader(nextHeader)) return;
      var nextGroupDiv = nextHeader.nextElementSibling;
      if (!nextGroupDiv || nextGroupDiv.getAttribute("role") !== "group") return;
      // Current order: header, groupDiv, nextHeader, nextGroupDiv
      // Target order:  nextHeader, nextGroupDiv, header, groupDiv
      var ref = nextGroupDiv.nextElementSibling; // null → append at end
      tree.insertBefore(header, ref);
      tree.insertBefore(groupDiv, ref);
    }

    // Persist the new code order via the reorder endpoint.
    var allRows = tree.querySelectorAll(".ace-code-row");
    var ids = [];
    allRows.forEach(function (row) {
      var id = row.getAttribute("data-code-id");
      if (id) ids.push(id);
    });
    _codeAction("POST", "/api/codes/reorder",
      "code_ids=" + encodeURIComponent(JSON.stringify(ids)) + "&current_index=" + window.__aceCurrentIndex);

    _updateKeycaps();
    _initSortable();
  }

  // --- Tree keydown handler ---

  document.addEventListener("keydown", function (e) {
    var tree = document.getElementById("code-tree");
    if (!tree || !tree.contains(document.activeElement)) return;
    var active = document.activeElement;
    if (!active || active.getAttribute("role") !== "treeitem") return;
    if (active.querySelector('[contenteditable="true"]')) return;

    var key = e.key;
    var alt = e.altKey;
    var shift = e.shiftKey;
    var items = _getTreeItems();
    var idx = items.indexOf(active);

    // Alt+Shift+↑ — Move code up (or group up if focused on group header)
    if (key === "ArrowUp" && alt && shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(active.getAttribute("data-code-id"), -1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      } else {
        _moveGroupInDirection(active, -1);
        _announce("Group '" + (active.getAttribute("data-group") || "Ungrouped") + "' moved up");
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
        _announce("Group '" + (active.getAttribute("data-group") || "Ungrouped") + "' moved down");
      }
      return;
    }

    // Alt+→ — Indent: move code into nearest group above
    if (key === "ArrowRight" && alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) return;
      var codeId = active.getAttribute("data-code-id");
      if (!codeId) return;

      // Check if already in a group
      var groupDiv = active.closest('[role="group"]');
      if (groupDiv) return; // Already in a group — one level only

      // Find nearest group header above
      var el = active;
      var targetGroup = null;
      while (el) {
        el = el.previousElementSibling;
        if (el && el.getAttribute("role") === "group") {
          var hdr = el.previousElementSibling;
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
        _announce("'" + (active.querySelector(".ace-code-name") || {}).textContent + "' moved into " + (targetGroup || "Ungrouped"));
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
      var codeId2 = active.getAttribute("data-code-id");
      if (!codeId2) return;

      var groupDiv2 = active.closest('[role="group"]');
      if (!groupDiv2) return; // Already ungrouped

      _moveToGroup(codeId2, "");
      _announce("'" + (active.querySelector(".ace-code-name") || {}).textContent + "' moved to ungrouped");
      return;
    }

    // Enter — Apply focused code to current sentence (stay in tree)
    if (key === "Enter" && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        var codeId3 = active.getAttribute("data-code-id");
        if (codeId3 && window.__aceFocusIndex >= 0) {
          _applyCodeToSentence(codeId3);
          // Flash the row briefly to confirm
          active.classList.add("ace-code-row--flash");
          setTimeout(function () { active.classList.remove("ace-code-row--flash"); }, 300);
          var codeName = active.querySelector(".ace-code-name");
          _announce("'" + (codeName ? codeName.textContent : "") + "' applied to sentence " + (window.__aceFocusIndex + 1));
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
      if (!_isGroupHeader(active)) {
        var codeId4 = active.getAttribute("data-code-id");
        if (codeId4) _startInlineRename(codeId4);
      }
      return;
    }

    // Delete / Backspace — Delete code (double-press confirm)
    if ((key === "Delete" || key === "Backspace") && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        var codeId5 = active.getAttribute("data-code-id");
        if (!codeId5) return;
        if (_deleteTarget === codeId5) {
          _executeDelete(codeId5);
        } else {
          _startDeleteConfirm(codeId5);
        }
      }
      return;
    }

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
          var groupDiv3 = active.nextElementSibling;
          if (groupDiv3 && groupDiv3.getAttribute("role") === "group") {
            var firstChild = groupDiv3.querySelector('[role="treeitem"]');
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
        var groupEl = active.closest('[role="group"]');
        if (groupEl) {
          var header2 = groupEl.previousElementSibling;
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
      _focusTextPanel();
      return;
    }
  });

  // --- Group expand / collapse ---

  function _promptNewGroupForCode(codeRow) {
    var input = document.createElement("input");
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
        var name = input.value.trim();
        if (name) {
          var codeId = codeRow.getAttribute("data-code-id");
          var header = document.createElement("div");
          header.setAttribute("role", "treeitem");
          header.setAttribute("aria-expanded", "true");
          header.setAttribute("aria-level", "1");
          header.className = "ace-code-group-header";
          header.setAttribute("data-group", name);
          header.setAttribute("tabindex", "-1");
          header.textContent = "\u25be " + name;

          var groupDiv = document.createElement("div");
          groupDiv.setAttribute("role", "group");

          input.remove();
          codeRow.parentNode.insertBefore(header, codeRow);
          codeRow.parentNode.insertBefore(groupDiv, codeRow);
          groupDiv.appendChild(codeRow);

          _moveToGroup(codeId, name);
          _initSortable();
          _announce("Group '" + name + "' created with code inside");
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

  function _expandGroup(header) {
    header.setAttribute("aria-expanded", "true");
    var groupName = header.getAttribute("data-group");
    header.textContent = "\u25be " + (groupName || "Ungrouped");
    _collapsedGroups[groupName] = false;
    _updateKeycaps();
  }

  function _collapseGroup(header) {
    header.setAttribute("aria-expanded", "false");
    var groupName = header.getAttribute("data-group");
    header.textContent = "\u25b8 " + (groupName || "Ungrouped");
    _collapsedGroups[groupName] = true;
    _updateKeycaps();
  }

  /* ================================================================
   * 18. DOMContentLoaded init
   * ================================================================ */

  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _restoreCollapseState();
    _updateKeycaps();
    _initSortable();
    _paintHighlights();

    // Set initial roving tabindex — first treeitem gets tabindex="0"
    var items = _getTreeItems();
    if (items.length > 0) {
      items[0].setAttribute("tabindex", "0");
    }

    // Auto-focus first sentence so keyboard works immediately
    var sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  });
})();
