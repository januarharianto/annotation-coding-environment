/**
 * ACE Bridge — client-side utilities for the FastAPI + HTMX coding page.
 *
 * Sections:
 *  1. Toast notifications
 *  2. Text selection capture
 *  3. Apply code (click + keyboard)
 *  4. Keyboard shortcuts
 *  5. Navigation
 *  6. Grid toggle
 *  7. Cheat sheet overlay
 *  8. Annotation flash
 *  9. Resize handle
 * 10. SortableJS lifecycle
 * 11. Code filter
 * 12. ace-navigate event listener
 * 13. Dialog close cleanup
 * 14. HTMX request enrichment (inject selection into code apply)
 * 15. DOMContentLoaded init
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
      el.addEventListener("transitionend", function () {
        el.remove();
      });
    }, duration);
  };

  // Listen for HTMX custom events that carry toast messages
  document.addEventListener("htmx:afterRequest", function (e) {
    var msg = e.detail.xhr && e.detail.xhr.getResponseHeader("X-ACE-Toast");
    if (msg) {
      window.aceToast(msg);
    }
  });

  /* ================================================================
   * 2. Text selection capture
   * ================================================================ */

  /**
   * Walk text nodes under `root` and return the cumulative character
   * offset of `node` at `offset` within that text-node stream.
   */
  function getTextOffset(root, node, offset) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var total = 0;
    var current;
    while ((current = walker.nextNode())) {
      if (current === node) return total + offset;
      total += current.textContent.length;
    }
    return total + offset;
  }

  document.addEventListener("mouseup", function () {
    var container = document.querySelector(".ace-text-content");
    if (!container) return;

    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
      window.__aceLastSelection = null;
      return;
    }

    var range = sel.getRangeAt(0);

    // Only capture selections inside the text content area
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
      return;
    }

    var start = getTextOffset(container, range.startContainer, range.startOffset);
    var end = getTextOffset(container, range.endContainer, range.endOffset);
    var text = sel.toString();

    if (!text || start === end) {
      window.__aceLastSelection = null;
      return;
    }

    window.__aceLastSelection = { start: start, end: end, text: text };
  });

  /* ================================================================
   * 3. Apply code (click on code row or keyboard shortcut)
   * ================================================================ */

  /**
   * Apply a code by triggering the HTMX request on a code row.
   * The selection data is injected via the htmx:configRequest listener (section 14).
   */
  window.aceApplyCode = function (codeId) {
    var sel = window.__aceLastSelection;
    if (!sel) return;

    var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
    if (!row) return;

    // Trigger the HTMX request on the row
    htmx.trigger(row, "click");

    window.__aceLastAppliedCodeId = codeId;
    window.__aceLastSelection = null;
    window.getSelection().removeAllRanges();

    // Flash feedback
    _flashRow(row);
  };

  function _flashRow(row) {
    row.classList.add("active");
    setTimeout(function () {
      row.classList.remove("active");
    }, 200);
  }

  // Delegated click handler: flash feedback on code row clicks,
  // but skip if clicking the menu button.
  document.addEventListener("click", function (e) {
    if (e.target.closest(".ace-code-menu-btn")) return;
    var row = e.target.closest(".ace-code-row");
    if (!row) return;

    // Store last applied code
    var codeId = row.getAttribute("data-code-id");
    if (codeId) {
      window.__aceLastAppliedCodeId = codeId;
    }

    // Clear selection after click
    if (window.__aceLastSelection) {
      window.__aceLastSelection = null;
      window.getSelection().removeAllRanges();
    }

    _flashRow(row);
  });

  /* ================================================================
   * 4. Keyboard shortcuts
   * ================================================================ */

  function _isTyping() {
    var tag = document.activeElement && document.activeElement.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  /**
   * Find a code row by its positional index (0-based) in the visible
   * (not display:none) rows. Returns the data-code-id or null.
   */
  function _getCodeIdAtIndex(index) {
    var rows = document.querySelectorAll(".ace-code-row");
    var visibleIndex = 0;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].style.display === "none") continue;
      if (visibleIndex === index) {
        return rows[i].getAttribute("data-code-id");
      }
      visibleIndex++;
    }
    return null;
  }

  document.addEventListener("keydown", function (e) {
    // Don't handle shortcuts while typing in form fields
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

    // Alt+Left — Navigate previous
    if (e.altKey && key === "ArrowLeft") {
      e.preventDefault();
      window.aceNavigate(window.__aceCurrentIndex - 1);
      return;
    }

    // Alt+Right — Navigate next
    if (e.altKey && key === "ArrowRight") {
      e.preventDefault();
      window.aceNavigate(window.__aceCurrentIndex + 1);
      return;
    }

    // Skip remaining shortcuts if modifier keys are held
    if (ctrl || e.altKey) return;

    // G — Toggle source grid
    if (key === "G" && shift) {
      e.preventDefault();
      window.aceToggleGrid();
      return;
    }

    // F — Flag
    if (key === "F" && shift) {
      e.preventDefault();
      _updateCurrentIndex();
      var flagBtn = document.getElementById("trigger-flag");
      if (flagBtn) htmx.trigger(flagBtn, "click");
      return;
    }

    // Q — Apply last used code
    if (key === "Q" && shift) {
      e.preventDefault();
      if (window.__aceLastAppliedCodeId) {
        window.aceApplyCode(window.__aceLastAppliedCodeId);
      }
      return;
    }

    // ? — Toggle cheat sheet
    if (key === "?" || (shift && key === "/")) {
      e.preventDefault();
      _toggleCheatSheet();
      return;
    }

    // Escape — Clear selection / close grid / close dialog / navigate back
    if (key === "Escape") {
      // Close cheat sheet if open
      var cheatSheet = document.getElementById("ace-cheat-sheet");
      if (cheatSheet) {
        cheatSheet.remove();
        return;
      }

      // Close open dialog
      var dialog = document.querySelector("dialog[open]");
      if (dialog) {
        dialog.close();
        return;
      }

      // Close source grid
      var grid = document.getElementById("source-grid");
      if (grid && !grid.classList.contains("ace-hidden")) {
        grid.classList.add("ace-hidden");
        return;
      }

      // Clear text selection
      if (window.__aceLastSelection) {
        window.__aceLastSelection = null;
        window.getSelection().removeAllRanges();
      }
      return;
    }

    // 1-9 — Apply code at index 0-8 (only when text is selected)
    if (key >= "1" && key <= "9") {
      var idx = parseInt(key, 10) - 1;
      var codeId = _getCodeIdAtIndex(idx);
      if (codeId && window.__aceLastSelection) {
        e.preventDefault();
        window.aceApplyCode(codeId);
      }
      return;
    }

    // 0 — Apply code at index 9
    if (key === "0") {
      var codeId0 = _getCodeIdAtIndex(9);
      if (codeId0 && window.__aceLastSelection) {
        e.preventDefault();
        window.aceApplyCode(codeId0);
      }
      return;
    }

    // a-z — Apply code at index 10-35
    if (key >= "a" && key <= "z" && !shift) {
      var letterIdx = key.charCodeAt(0) - 97 + 10;
      var codeIdLetter = _getCodeIdAtIndex(letterIdx);
      if (codeIdLetter && window.__aceLastSelection) {
        e.preventDefault();
        window.aceApplyCode(codeIdLetter);
      }
      return;
    }
  });

  /**
   * Update the hidden current-index input before triggering HTMX actions.
   */
  function _updateCurrentIndex() {
    var input = document.getElementById("current-index");
    if (input) {
      input.value = window.__aceCurrentIndex;
    }
  }

  /* ================================================================
   * 5. Navigation
   * ================================================================ */

  window.aceNavigate = function (index) {
    if (index < 0 || index >= window.__aceTotalSources) return;
    window.__aceCurrentIndex = index;
    window.location.href = "/code?index=" + index;
  };

  /* ================================================================
   * 6. Grid toggle
   * ================================================================ */

  window.aceToggleGrid = function () {
    var grid = document.getElementById("source-grid");
    if (grid) {
      grid.classList.toggle("ace-hidden");
    }
  };

  /* ================================================================
   * 7. Cheat sheet overlay
   * ================================================================ */

  function _toggleCheatSheet() {
    var existing = document.getElementById("ace-cheat-sheet");
    if (existing) {
      existing.remove();
      return;
    }

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
      _shortcutRow("1 – 9", "Apply code 1–9") +
      _shortcutRow("0", "Apply code 10") +
      _shortcutRow("a – z", "Apply code 11–36") +
      _shortcutRow("Q", "Re-apply last used code") +
      _shortcutRow("Ctrl/⌘ + Z", "Undo") +
      _shortcutRow("Ctrl/⌘ + Shift + Z", "Redo") +
      _shortcutRow("Alt + ←", "Previous source") +
      _shortcutRow("Alt + →", "Next source") +
      _shortcutRow("G", "Toggle source grid") +
      _shortcutRow("F", "Flag/unflag source") +
      _shortcutRow("?", "Toggle this cheat sheet") +
      _shortcutRow("Escape", "Close / clear / go back") +
      "</table>";

    overlay.appendChild(card);
    document.body.appendChild(overlay);

    // Close on click outside the card
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) {
        overlay.remove();
      }
    });
  }

  function _shortcutRow(key, desc) {
    return (
      '<tr style="border-bottom:1px solid var(--ace-border-light,#e0e0e0);">' +
      '<td style="padding:4px 12px 4px 0;font-family:\'SF Mono\',Menlo,Consolas,monospace;' +
      'font-size:12px;white-space:nowrap;color:var(--ace-text-muted,#777);">' +
      key +
      "</td>" +
      '<td style="padding:4px 0;">' +
      desc +
      "</td></tr>"
    );
  }

  /* ================================================================
   * 8. Annotation flash
   * ================================================================ */

  window.aceFlashAnnotation = function (annotationId) {
    var el = document.querySelector(
      '.ace-annotation[data-annotation-id="' + annotationId + '"]'
    );
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ace-annotation--flash");
    setTimeout(function () {
      el.classList.remove("ace-annotation--flash");
    }, 600);
  };

  /* ================================================================
   * 9. Resize handle
   * ================================================================ */

  function _initResize() {
    var handle = document.getElementById("resize-handle");
    if (!handle) return;

    var split = handle.closest(".ace-split");
    if (!split) return;

    // Restore saved width
    var saved = localStorage.getItem("ace-sidebar-width");
    if (saved) {
      split.style.gridTemplateColumns = saved + "px 1px 1fr";
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
      var min = 180;
      var max = rect.width * 0.5;
      x = Math.max(min, Math.min(max, x));
      split.style.gridTemplateColumns = x + "px 1px 1fr";
    });

    document.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";

      // Save current width to localStorage
      var cols = split.style.gridTemplateColumns;
      if (cols) {
        var width = parseInt(cols, 10);
        if (width) localStorage.setItem("ace-sidebar-width", width);
      }
    });
  }

  /* ================================================================
   * 10. SortableJS lifecycle
   * ================================================================ */

  var _currentSortable = null;

  function _initSortable() {
    if (_currentSortable) {
      _currentSortable.destroy();
      _currentSortable = null;
    }

    var list = document.getElementById("code-list");
    if (!list || typeof Sortable === "undefined") return;

    _currentSortable = new Sortable(list, {
      animation: 150,
      handle: ".ace-code-row",
      ghostClass: "active",
      onEnd: function () {
        var rows = list.querySelectorAll(".ace-code-row");
        var ids = [];
        rows.forEach(function (row) {
          var id = row.getAttribute("data-code-id");
          if (id) ids.push(id);
        });

        // POST new order to server
        if (typeof htmx !== "undefined") {
          htmx.ajax("POST", "/api/codes/reorder", {
            values: { code_ids: JSON.stringify(ids) },
          });
        }
      },
    });
  }

  // Destroy SortableJS before sidebar swap to avoid stale references
  document.addEventListener("htmx:beforeSwap", function (evt) {
    var target = evt.detail.target;
    if (target && (target.id === "code-sidebar" || target.id === "coding-workspace")) {
      if (_currentSortable) {
        _currentSortable.destroy();
        _currentSortable = null;
      }
    }
  });

  // Re-init SortableJS after sidebar or workspace swap
  document.addEventListener("htmx:afterSwap", function (evt) {
    var target = evt.detail.target;
    if (
      target &&
      (target.id === "code-sidebar" || target.id === "coding-workspace")
    ) {
      _initSortable();
    }

    // Auto-open dialogs loaded into modal-container
    if (target && target.id === "modal-container") {
      var dialog = target.querySelector("dialog");
      if (dialog && !dialog.open) dialog.showModal();
    }
  });

  /* ================================================================
   * 11. Code filter
   * ================================================================ */

  function _initCodeFilter() {
    // Use event delegation so it works after HTMX swaps
    document.addEventListener("input", function (e) {
      if (e.target.id !== "code-filter-input") return;
      var query = e.target.value.toLowerCase();
      var rows = document.querySelectorAll(".ace-code-row");
      rows.forEach(function (row) {
        var name = row.querySelector(".ace-code-name");
        if (!name) return;
        row.style.display =
          name.textContent.toLowerCase().indexOf(query) >= 0 ? "" : "none";
      });

      // Show/hide "no matches" hint
      var visibleCount = document.querySelectorAll('.ace-code-row:not([hidden]):not([style*="display: none"])').length;
      var hint = document.getElementById('filter-no-match-hint');
      if (hint) {
        hint.style.display = (query && visibleCount === 0) ? 'block' : 'none';
      }
    });

    // Enter to create a new code when no matches
    document.addEventListener("keydown", function (e) {
      if (e.target.id !== "code-filter-input") return;
      if (e.key !== "Enter") return;

      var query = e.target.value.trim();
      if (!query) return;

      var rows = document.querySelectorAll(".ace-code-row");
      var hasVisible = false;
      rows.forEach(function (row) {
        if (row.style.display !== "none") hasVisible = true;
      });

      if (!hasVisible && typeof htmx !== "undefined") {
        e.preventDefault();
        htmx.ajax("POST", "/api/codes", {
          values: { name: query },
          target: "#code-sidebar",
          swap: "morph:innerHTML",
        });
        e.target.value = "";
      }
    });
  }

  /* ================================================================
   * 12. ace-navigate event listener
   * ================================================================ */

  // Custom event dispatched by HX-Trigger header after navigation
  document.addEventListener("ace-navigate", function (e) {
    var detail = e.detail || {};
    if (detail.current_index !== undefined) {
      window.__aceCurrentIndex = parseInt(detail.current_index, 10);
    }
    if (detail.total_sources !== undefined) {
      window.__aceTotalSources = parseInt(detail.total_sources, 10);
    }
    var input = document.getElementById("current-index");
    if (input) {
      input.value = window.__aceCurrentIndex;
    }
  });

  /* ================================================================
   * 13. Dialog close cleanup
   * ================================================================ */

  document.addEventListener(
    "close",
    function (evt) {
      if (evt.target.tagName === "DIALOG") {
        var container = document.getElementById("modal-container");
        if (container) container.innerHTML = "";
      }
    },
    true
  );

  /* ================================================================
   * 14. HTMX request enrichment — inject selection data into code apply
   * ================================================================ */

  // Cancel code apply if no text is selected
  document.addEventListener("htmx:confirm", function (e) {
    var elt = e.detail.elt;
    if (!elt || !elt.classList || !elt.classList.contains("ace-code-row")) return;
    if (!window.__aceLastSelection) {
      e.preventDefault();
      aceToast("Select text first");
    }
  });

  document.addEventListener("htmx:configRequest", function (e) {
    // Only inject for code apply requests
    var elt = e.detail.elt;
    if (!elt || !elt.classList || !elt.classList.contains("ace-code-row")) return;

    var sel = window.__aceLastSelection;
    if (sel) {
      e.detail.parameters.start_offset = sel.start;
      e.detail.parameters.end_offset = sel.end;
      e.detail.parameters.selected_text = sel.text;
    }

    // Always include current index
    e.detail.parameters.current_index = window.__aceCurrentIndex;
  });

  /* ================================================================
   * 15. Code menu dropdown
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

    // Position below the button, or above if near bottom
    var menuHeight = menu.offsetHeight;
    var spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < menuHeight + 8) {
      menu.style.top = (rect.top - menuHeight) + "px";
    } else {
      menu.style.top = rect.bottom + "px";
    }
    menu.style.left = Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8) + "px";

    // Close on outside click (next tick so this click doesn't close it)
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
   * 16. DOMContentLoaded init
   * ================================================================ */

  document.addEventListener("DOMContentLoaded", function () {
    _initResize();
    _initSortable();
    _initCodeFilter();
  });
})();
