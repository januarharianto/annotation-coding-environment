/**
 * ACE Bridge — client-side utilities for the coding page.
 *
 * Sections:
 *  1. Toast notifications
 *  2. Sentence navigation (↑/↓ focus)
 *  3. Tab management (Recent / Groups / All)
 *  4. Keymap (dynamic per-tab keycap assignment)
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
   * 3. Tab management
   * ================================================================ */

  window.aceSwitchTab = function (btn, tabId) {
    // Update tab buttons
    var tabs = btn.parentElement.querySelectorAll(".ace-sidebar-tab");
    tabs.forEach(function (t) { t.classList.remove("ace-sidebar-tab--active"); });
    btn.classList.add("ace-sidebar-tab--active");

    // Update views
    document.querySelectorAll(".ace-sidebar-view").forEach(function (v) {
      v.classList.remove("ace-sidebar-view--active");
    });
    document.getElementById("view-" + tabId).classList.add("ace-sidebar-view--active");

    _buildTabContent(tabId);
    _updateKeycaps();

    // Return focus to text panel
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  };

  function _buildTabContent(tabId) {
    var codes = window.__aceCodes || [];
    if (tabId === "recent") {
      _buildRecentTab(codes);
    } else if (tabId === "all") {
      _buildAllTab(codes);
    }
    // "groups" tab is server-rendered — no client rebuild needed
  }

  function _buildRecentTab(codes) {
    var view = document.getElementById("view-recent");
    if (!view) return;
    var recentIds = window.__aceRecentCodeIds || [];
    if (!recentIds.length) {
      view.innerHTML = '<div class="ace-sidebar-empty">No recent codes</div>';
      return;
    }
    var codeMap = {};
    codes.forEach(function (c) { codeMap[c.id] = c; });
    var html = "";
    recentIds.forEach(function (id) {
      var c = codeMap[id];
      if (!c) return;
      html += _buildCodeRowHtml(c);
    });
    view.innerHTML = html;
  }

  function _buildAllTab(codes) {
    var view = document.getElementById("view-all");
    if (!view) return;
    var sorted = codes.slice().sort(function (a, b) {
      return a.name.localeCompare(b.name);
    });
    var html = "";
    sorted.forEach(function (c) { html += _buildCodeRowHtml(c); });
    view.innerHTML = html;
  }

  function _buildCodeRowHtml(code) {
    var esc = _escHtml(code.name);
    return '<div class="ace-code-row" data-code-id="' + code.id + '">'
      + '<span class="ace-code-dot" style="background:' + code.colour + ';"></span>'
      + '<span class="ace-code-name">' + esc + '</span>'
      + '<span class="ace-keycap"></span>'
      + '</div>';
  }

  function _escHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* ================================================================
   * 4. Keymap — dynamic keycap assignment per tab
   * ================================================================ */

  var _currentKeyMap = []; // array of code IDs in keycap order

  function _updateKeycaps() {
    var view = document.querySelector(".ace-sidebar-view--active");
    if (!view) return;
    var rows = view.querySelectorAll(".ace-code-row");
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
    _trackRecent(codeId);
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
    _trackRecent(codeId);
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

  function _trackRecent(codeId) {
    var recent = window.__aceRecentCodeIds || [];
    var idx = recent.indexOf(codeId);
    if (idx >= 0) recent.splice(idx, 1);
    recent.unshift(codeId);
    if (recent.length > 20) recent.length = 20;
    window.__aceRecentCodeIds = recent;
  }

  /* ================================================================
   * 6. Keyboard shortcuts
   * ================================================================ */

  // Custom selection tracking (for click-drag)
  window.__aceLastSelection = null;

  function _isTyping() {
    var tag = document.activeElement && document.activeElement.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  document.addEventListener("keydown", function (e) {
    if (_isTyping()) return;

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

    // ← / → — Navigate between sources (Shift = jump 5)
    if (key === "ArrowLeft") {
      e.preventDefault();
      var step = shift ? 5 : 1;
      window.aceNavigate(window.__aceCurrentIndex - step);
      return;
    }
    if (key === "ArrowRight") {
      e.preventDefault();
      var step2 = shift ? 5 : 1;
      window.aceNavigate(window.__aceCurrentIndex + step2);
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
    if (index < 0 || index >= window.__aceTotalSources) return;
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

    var saved = localStorage.getItem("ace-sidebar-width");
    if (saved) {
      split.style.gridTemplateColumns = saved + "px 1px 1fr 200px";
    }

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
      split.style.gridTemplateColumns = x + "px 1px 1fr 200px";
    });

    document.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      var cols = split.style.gridTemplateColumns;
      if (cols) {
        var width = parseInt(cols, 10);
        if (width) localStorage.setItem("ace-sidebar-width", width);
      }
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

    // Click on margin note to highlight corresponding sentences
    var note = e.target.closest(".ace-margin-note");
    if (note) {
      var startIdx = parseInt(note.dataset.startIdx, 10);
      if (!isNaN(startIdx)) _focusSentence(startIdx);
    }
  });

  // After HTMX swap: restore focus, rebuild tabs, update keycaps
  // Use afterSettle (not afterSwap) — fires after HTMX finishes all DOM changes
  document.addEventListener("htmx:afterSettle", function (evt) {
    var target = evt.detail.target;
    if (!target) return;

    if (target.id === "text-panel" || target.id === "coding-workspace") {
      _restoreFocus();
    }

    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      _buildTabContent("recent");
      _buildTabContent("all");
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
  });

  /* ================================================================
   * 13. Code management helpers
   * ================================================================ */

  var _menuOpen = false;
  var _lastSelectedCodeId = null;

  // No-op stubs — replaced by real implementations in later tasks
  function _closeCodeMenu() {}
  function _closeColourPopover() {}

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
      _buildTabContent("recent");
      _buildTabContent("all");
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

  /* ================================================================
   * 14. Code menu dropdown (management mode)
   * ================================================================ */

  var _activeCodeMenu = null;

  function _closeCodeMenu() {
    if (_activeCodeMenu) {
      _activeCodeMenu.remove();
      _activeCodeMenu = null;
    }
  }

  window.aceCodeMenu = function (event, codeId) {
    _closeCodeMenu();
    var btn = event.currentTarget;
    var rect = btn.getBoundingClientRect();

    var menu = document.createElement("div");
    menu.className = "ace-code-menu";

    var items = [
      { label: "Rename", endpoint: "rename-dialog" },
      { label: "Colour", endpoint: "colour-dialog" },
      { label: "Move to Group", endpoint: "move-dialog" },
      { label: "Delete", endpoint: "delete-dialog", danger: true },
    ];

    items.forEach(function (item) {
      var el = document.createElement("button");
      el.className = "ace-code-menu-item";
      if (item.danger) el.classList.add("ace-code-menu-item--danger");
      el.textContent = item.label;
      el.addEventListener("click", function () {
        _closeCodeMenu();
        htmx.ajax("GET", "/api/codes/" + codeId + "/" + item.endpoint, {
          target: "#modal-container",
          swap: "innerHTML",
        });
      });
      menu.appendChild(el);
    });

    document.body.appendChild(menu);
    _activeCodeMenu = menu;

    var menuHeight = menu.offsetHeight;
    var spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < menuHeight + 8) {
      menu.style.top = (rect.top - menuHeight) + "px";
    } else {
      menu.style.top = rect.bottom + "px";
    }
    menu.style.left = Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8) + "px";

    setTimeout(function () {
      document.addEventListener("click", _onCodeMenuOutsideClick);
      document.addEventListener("keydown", _onCodeMenuEscape);
    }, 0);
  };

  function _onCodeMenuOutsideClick(e) {
    if (_activeCodeMenu && !_activeCodeMenu.contains(e.target)) {
      _closeCodeMenu();
      document.removeEventListener("click", _onCodeMenuOutsideClick);
      document.removeEventListener("keydown", _onCodeMenuEscape);
    }
  }

  function _onCodeMenuEscape(e) {
    if (e.key === "Escape") {
      _closeCodeMenu();
      document.removeEventListener("click", _onCodeMenuOutsideClick);
      document.removeEventListener("keydown", _onCodeMenuEscape);
    }
  }

  /* ================================================================
   * Management mode toggle
   * ================================================================ */

  window.aceToggleManageMode = function () {
    var sidebar = document.getElementById("code-sidebar");
    if (!sidebar) return;
    sidebar.classList.toggle("ace-sidebar--manage");
  };

  // Create code on Enter in management mode
  document.addEventListener("keydown", function (e) {
    if (e.target.id !== "manage-create-input") return;
    if (e.key !== "Enter") return;
    var name = e.target.value.trim();
    if (!name) return;
    e.preventDefault();
    htmx.ajax("POST", "/api/codes", {
      values: { name: name, current_index: window.__aceCurrentIndex },
      target: "#code-sidebar",
      swap: "outerHTML",
    });
    e.target.value = "";
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
      // Insert an empty group header + placeholder before the "+ New group" row
      var header = document.createElement("div");
      header.className = "ace-code-group-header";
      header.textContent = "▾ " + name + " (0)";
      var placeholder = document.createElement("div");
      placeholder.className = "ace-group-placeholder";
      placeholder.textContent = "No codes assigned";
      el.parentNode.insertBefore(header, el);
      el.parentNode.insertBefore(placeholder, el);
      cancel();
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

  // Filter code rows across all tabs as user types
  document.addEventListener("input", function (e) {
    if (e.target.id !== "code-search-input") return;
    var query = e.target.value.toLowerCase();
    // Filter the active tab's rows
    var view = document.querySelector(".ace-sidebar-view--active");
    if (!view) return;
    var rows = view.querySelectorAll(".ace-code-row");
    var visibleCount = 0;
    rows.forEach(function (row) {
      var name = row.querySelector(".ace-code-name");
      if (!name) return;
      var match = name.textContent.toLowerCase().indexOf(query) >= 0;
      row.style.display = match ? "" : "none";
      if (match) visibleCount++;
    });
    // Also hide group headers if all their children are hidden
    var headers = view.querySelectorAll(".ace-code-group-header");
    headers.forEach(function (header) {
      var next = header.nextElementSibling;
      var anyVisible = false;
      while (next && next.classList.contains("ace-code-row")) {
        if (next.style.display !== "none") anyVisible = true;
        next = next.nextElementSibling;
      }
      header.style.display = anyVisible ? "" : "none";
    });
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
    var view = document.querySelector(".ace-sidebar-view--active");
    var rows = view ? view.querySelectorAll('.ace-code-row:not([style*="display: none"])') : [];
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
   * 17. DOMContentLoaded init
   * ================================================================ */

  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _buildTabContent("recent");
    _buildTabContent("all");
    _updateKeycaps();

    // Auto-focus first sentence so keyboard works immediately
    var sentences = _getSentences();
    if (sentences.length > 0) {
      _focusSentence(0);
    }
    var tp = document.getElementById("text-panel");
    if (tp) tp.focus();
  });
})();
