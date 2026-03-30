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
 * 14. Code menu dropdown (management mode)
 * 15. Add group (inline)
 * 16. Code search / filter / create
 * 17. DOMContentLoaded init
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
    var groupName = header.getAttribute("data-group");
    if (collapsed) {
      group.classList.add("ace-code-group--collapsed");
      group.querySelectorAll(".ace-code-row").forEach(function (r) {
        r.classList.add("ace-code-row--hidden");
      });
      header.textContent = "\u25b8 " + (groupName || "Ungrouped");
    } else {
      group.classList.remove("ace-code-group--collapsed");
      group.querySelectorAll(".ace-code-row").forEach(function (r) {
        r.classList.remove("ace-code-row--hidden");
      });
      header.textContent = "\u25be " + (groupName || "Ungrouped");
    }
    _collapsedGroups[groupName] = collapsed;
  }

  function _toggleGroupCollapse(header) {
    var group = header.closest(".ace-code-group");
    if (!group) return;
    var isCollapsed = !group.classList.contains("ace-code-group--collapsed");
    _setGroupCollapsed(group, header, isCollapsed);
    _updateKeycaps();
  }

  function _restoreCollapseState() {
    var groups = document.querySelectorAll(".ace-code-group");
    groups.forEach(function (group) {
      var header = group.querySelector(".ace-code-group-header");
      if (!header) return;
      var groupName = header.getAttribute("data-group");
      if (_collapsedGroups[groupName]) {
        _setGroupCollapsed(group, header, true);
      }
    });
  }

  // Click handler for group headers
  document.addEventListener("click", function (e) {
    var header = e.target.closest(".ace-code-group-header");
    if (header && !e.target.closest(".ace-code-menu")) {
      _toggleGroupCollapse(header);
    }
  });

  /* ================================================================
   * 4. Keymap — dynamic keycap assignment per tab
   * ================================================================ */

  var _currentKeyMap = []; // array of code IDs in keycap order

  function _updateKeycaps() {
    var view = document.getElementById("view-groups");
    if (!view) return;
    var rows = view.querySelectorAll(".ace-code-row:not(.ace-code-row--hidden)");
    _currentKeyMap = [];
    rows.forEach(function (row, i) {
      _currentKeyMap.push(row.getAttribute("data-code-id"));
      var keycap = row.querySelector(".ace-keycap");
      if (keycap) keycap.textContent = _keylabel(i);
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

    // Click on code chip to flash corresponding sentences
    var chip = e.target.closest(".ace-code-chip");
    if (chip) {
      var codeId = chip.dataset.codeId;
      var colour = chip.dataset.colour || "#ffeb3b";
      var r = parseInt(colour.slice(1, 3), 16);
      var g = parseInt(colour.slice(3, 5), 16);
      var b = parseInt(colour.slice(5, 7), 16);

      // Read annotations from #ace-ann-data
      var dataEl = document.getElementById("ace-ann-data");
      if (!dataEl) return;
      var anns = JSON.parse(dataEl.dataset.annotations || "[]");
      var matching = anns.filter(function (a) { return a.code_id === codeId; });

      // Find overlapping sentences and flash them
      var sentences = document.querySelectorAll(".ace-sentence");
      var flashed = [];
      matching.forEach(function (ann) {
        sentences.forEach(function (s) {
          var ss = parseInt(s.dataset.start, 10);
          var se = parseInt(s.dataset.end, 10);
          if (ann.start < se && ann.end > ss && flashed.indexOf(s) < 0) {
            flashed.push(s);
          }
        });
      });

      // Flash each sentence with the code's colour (strong opacity, then fade)
      flashed.forEach(function (s) {
        s.style.transition = "none";
        s.style.background = "rgba(" + r + "," + g + "," + b + ",0.7)";
        s.style.outline = "2px solid rgba(" + r + "," + g + "," + b + ",0.8)";
        s.style.outlineOffset = "1px";
        void s.offsetWidth;
        s.style.transition = "background 1.5s ease-out, outline-color 1.5s ease-out";
        s.style.background = "";
        s.style.outlineColor = "transparent";
        setTimeout(function () {
          s.style.outline = "";
          s.style.outlineOffset = "";
        }, 1600);
      });

      // Scroll first flashed sentence into view
      if (flashed.length) {
        flashed[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
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
        document.getElementById("text-panel").focus();
        return;
      }
      _codeAction("PUT", "/api/codes/" + codeId,
        "name=" + encodeURIComponent(newName) + "&current_index=" + window.__aceCurrentIndex
      ).catch(function () { nameEl.textContent = original; });
      document.getElementById("text-panel").focus();
    }

    nameEl.addEventListener("keydown", function handler(e) {
      if (e.key === "Enter") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); save(); }
      if (e.key === "Escape") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); done = true; nameEl.textContent = original; nameEl.contentEditable = "false"; document.getElementById("text-panel").focus(); }
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

    var containers = document.querySelectorAll(".ace-code-group");
    containers.forEach(function (container) {
      var instance = new Sortable(container, {
        group: "codes",
        animation: 150,
        delay: 200,
        delayOnTouchOnly: true,
        draggable: ".ace-code-row",
        ghostClass: "ace-code-row--ghost",
        filter: ".ace-code-group-header",
        onStart: function () { _isDragging = true; },
        onEnd: function (evt) {
          _isDragging = false;
          var codeId = evt.item.getAttribute("data-code-id");
          var newGroup = evt.to.getAttribute("data-group");
          var oldGroup = evt.from.getAttribute("data-group");

          if (newGroup !== oldGroup && codeId) {
            fetch("/api/codes/" + codeId, {
              method: "PUT",
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              body: "group_name=" + encodeURIComponent(newGroup || "") + "&current_index=" + window.__aceCurrentIndex,
            });
          }

          var allRows = document.querySelectorAll("#view-groups .ace-code-row");
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
      { label: "Rename", action: function () { _closeCodeMenu(); _startInlineRename(codeId); } },
      { label: "Colour", action: function () { _closeCodeMenu(); _openColourPopover(codeId); } },
      { label: "Move Up", action: function () { _closeCodeMenu(); _moveCode(codeId, -1); } },
      { label: "Move Down", action: function () { _closeCodeMenu(); _moveCode(codeId, 1); } },
      { label: "Delete", danger: true, action: function () { _closeCodeMenu(); _startDeleteConfirm(codeId); } },
    ];

    // Add "Move to Group" submenu if groups exist
    var groups = _getGroupNames();
    if (groups.length > 0 || true) {  // always show (Ungrouped option is useful)
      var moveItem = document.createElement("div");
      moveItem.className = "ace-code-menu-item ace-code-menu-sub";
      moveItem.textContent = "Move to Group \u25b8";
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
    document.querySelectorAll("#view-groups .ace-code-group[data-group]").forEach(function (g) {
      var name = g.getAttribute("data-group");
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
   * 15. Add group (inline)
   * ================================================================ */

  window.aceStartAddGroup = function (el) {
    var original = el.textContent;
    el.innerHTML = '<input type="text" placeholder="Group name…" autocomplete="off">';
    var input = el.querySelector("input");
    input.focus();

    function submit() {
      var name = input.value.trim();
      if (!name) { cancel(); return; }
      // Create a proper group container so SortableJS and _getGroupNames work
      var group = document.createElement("div");
      group.className = "ace-code-group";
      group.setAttribute("data-group", name);
      var header = document.createElement("div");
      header.className = "ace-code-group-header";
      header.setAttribute("data-group", name);
      header.textContent = "\u25be " + name;
      group.appendChild(header);
      el.parentNode.insertBefore(group, el);
      cancel();
      _initSortable();
    }

    function cancel() {
      el.innerHTML = "";
      el.textContent = original;
    }

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      if (e.key === "Escape") { e.preventDefault(); cancel(); }
    });
  };

  /* ================================================================
   * 16. Code search / filter / create
   * ================================================================ */

  // Filter code rows as user types
  document.addEventListener("input", function (e) {
    if (e.target.id !== "code-search-input") return;
    var query = e.target.value.toLowerCase();
    var view = document.getElementById("view-groups");
    if (!view) return;

    if (query) {
      // Filter: show matching rows, auto-expand groups with matches
      var rows = view.querySelectorAll(".ace-code-row");
      rows.forEach(function (row) {
        var name = row.querySelector(".ace-code-name");
        if (!name) return;
        var match = name.textContent.toLowerCase().indexOf(query) >= 0;
        if (match) {
          row.classList.remove("ace-code-row--hidden");
        } else {
          row.classList.add("ace-code-row--hidden");
        }
      });
      // Auto-expand groups with matches, hide empty groups
      var groups = view.querySelectorAll(".ace-code-group");
      groups.forEach(function (group) {
        var visibleInGroup = group.querySelectorAll(".ace-code-row:not(.ace-code-row--hidden)").length;
        group.style.display = visibleInGroup > 0 ? "" : "none";
        if (visibleInGroup > 0) {
          group.classList.remove("ace-code-group--collapsed");
        }
      });
    } else {
      // Clear: restore all rows and collapse state
      view.querySelectorAll(".ace-code-row").forEach(function (row) {
        row.classList.remove("ace-code-row--hidden");
      });
      view.querySelectorAll(".ace-code-group").forEach(function (group) {
        group.style.display = "";
      });
      _restoreCollapseState();
    }

    _updateKeycaps();
  });

  // Enter in search: create new code if no visible matches
  document.addEventListener("keydown", function (e) {
    if (e.target.id !== "code-search-input") return;
    if (e.key === "Escape") {
      e.target.value = "";
      e.target.dispatchEvent(new Event("input"));
      document.getElementById("text-panel").focus();
      return;
    }
    if (e.key !== "Enter") return;
    var name = e.target.value.trim();
    if (!name) return;

    // Check if any visible rows match exactly
    var view = document.getElementById("view-groups");
    var rows = view ? view.querySelectorAll(".ace-code-row:not(.ace-code-row--hidden)") : [];
    if (rows.length > 0) {
      // Has matches — don't create, just clear and refocus
      e.target.value = "";
      e.target.dispatchEvent(new Event("input"));
      document.getElementById("text-panel").focus();
      return;
    }

    // No matches — create new code
    e.preventDefault();
    htmx.ajax("POST", "/api/codes", {
      values: { name: name, current_index: window.__aceCurrentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
    });
    e.target.value = "";
  });

  /* ================================================================
   * 18. CSS Custom Highlight API — annotation rendering
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
   * 17. DOMContentLoaded init
   * ================================================================ */

  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _restoreCollapseState();
    _updateKeycaps();
    _initSortable();
    _paintHighlights();

    // Auto-focus first sentence so keyboard works immediately
    var sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  });
})();
