/**
 * ACE Annotation Bridge
 *
 * Handles text selection capture and annotation click events.
 * Communicates with NiceGUI backend via emitEvent.
 */

(function () {
  "use strict";

  /**
   * Calculate the text offset of a given DOM node + offset within the
   * .ace-text-content container.  Walks all text nodes in document order
   * and sums their lengths until we reach the anchor/focus node.
   */
  function getTextOffset(container, node, offset) {
    var walker = document.createTreeWalker(
      container,
      NodeFilter.SHOW_TEXT,
      null,
      false
    );
    var pos = 0;
    var current;
    while ((current = walker.nextNode())) {
      if (current === node) {
        return pos + offset;
      }
      pos += current.textContent.length;
    }
    // Fallback: if node is an element, try to resolve via child offset
    if (node.nodeType === Node.ELEMENT_NODE) {
      var childNodes = [];
      walker = document.createTreeWalker(
        container,
        NodeFilter.SHOW_TEXT,
        null,
        false
      );
      pos = 0;
      var idx = 0;
      while ((current = walker.nextNode())) {
        // Count how many text nodes we've passed
        // The offset for an element node means "before the offset-th child"
        if (current.parentNode === node && idx >= offset) {
          return pos;
        }
        pos += current.textContent.length;
        if (current.parentNode === node) {
          idx++;
        }
      }
      return pos;
    }
    return pos;
  }

  function setupSelectionListener() {
    document.addEventListener("mouseup", function (e) {
      var container = document.querySelector(".ace-text-content");
      if (!container) return;

      var sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;

      var range = sel.getRangeAt(0);

      // Check that the selection is within our container
      if (
        !container.contains(range.startContainer) ||
        !container.contains(range.endContainer)
      ) {
        return;
      }

      var startOffset = getTextOffset(
        container,
        range.startContainer,
        range.startOffset
      );
      var endOffset = getTextOffset(
        container,
        range.endContainer,
        range.endOffset
      );
      var selectedText = sel.toString();

      if (startOffset === endOffset || !selectedText.trim()) return;

      // Ensure start < end
      if (startOffset > endOffset) {
        var tmp = startOffset;
        startOffset = endOffset;
        endOffset = tmp;
      }

      var data = {
        start: startOffset,
        end: endOffset,
        text: selectedText,
      };

      // Store as fallback for when emitEvent doesn't deliver in time
      window.__aceLastSelection = data;

      emitEvent("text_selected", data);
    });
  }

  function setupAnnotationClickListener() {
    document.addEventListener("click", function (e) {
      var span = e.target.closest(".ace-annotation");
      if (!span) return;

      // Collect all annotation IDs from nested spans at the click point
      var ids = [];
      var el = span;
      while (el) {
        if (
          el.classList &&
          el.classList.contains("ace-annotation") &&
          el.dataset.annotationId
        ) {
          ids.push(el.dataset.annotationId);
        }
        el = el.parentElement;
        if (el && el.classList && el.classList.contains("ace-text-content"))
          break;
      }

      if (ids.length > 0) {
        emitEvent("annotation_clicked", { annotation_ids: ids });
      }
    });
  }

  function setupCodeListSortable() {
    var _currentContainer = null;
    var _sortable = null;

    function initSortable() {
      var container = document.querySelector(".ace-code-list");
      if (!container || container === _currentContainer) return;

      if (_sortable) {
        _sortable.destroy();
        _sortable = null;
      }
      _currentContainer = container;

      // Only init if drag handles are present (not in sort-by-name mode)
      if (!container.querySelector(".ace-drag-handle")) return;

      _sortable = Sortable.create(container, {
        animation: 150,
        handle: ".ace-drag-handle",
        ghostClass: "ace-drag-ghost",
        onEnd: function () {
          var items = container.querySelectorAll("[data-code-id]");
          var ids = [];
          for (var i = 0; i < items.length; i++) {
            ids.push(items[i].dataset.codeId);
          }
          emitEvent("codes_reordered", { code_ids: ids });
        },
      });
    }

    new MutationObserver(initSortable).observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", function (e) {
      // Don't capture when typing in input/textarea fields
      var tag = (e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (e.target.isContentEditable) return;

      // Ctrl/Cmd+Z = undo, Ctrl/Cmd+Shift+Z = redo
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          emitEvent("shortcut_redo", {});
        } else {
          emitEvent("shortcut_undo", {});
        }
        return;
      }

      // Escape = dismiss (clear selection)
      if (e.key === "Escape") {
        emitEvent("shortcut_escape", {});
        return;
      }

      // Alt+ArrowLeft / Alt+ArrowRight = prev/next source
      if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        e.preventDefault();
        emitEvent(e.key === "ArrowLeft" ? "shortcut_prev_source" : "shortcut_next_source", {});
        return;
      }

      // 1-9, 0, a-z = apply code (only when there is an active text selection)
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        var codeIndex = -1;
        if (e.key >= "1" && e.key <= "9") {
          codeIndex = parseInt(e.key) - 1; // 1-9 → indices 0-8
        } else if (e.key === "0") {
          codeIndex = 9; // 0 → index 9
        } else if (e.key >= "a" && e.key <= "z") {
          codeIndex = 10 + (e.key.charCodeAt(0) - 97); // a-z → indices 10-35
        }
        if (codeIndex >= 0) {
          var sel = window.getSelection();
          if (sel && !sel.isCollapsed) {
            e.preventDefault();
            emitEvent("shortcut_apply_code", { index: codeIndex });
          }
          return;
        }
      }
    });
  }

  // Scroll to and flash an annotation span by ID
  window.aceFlashAnnotation = function (annotationId) {
    var el = document.querySelector(
      '[data-annotation-id="' + annotationId + '"]'
    );
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("ace-annotation-flash");
    void el.offsetWidth;
    el.classList.add("ace-annotation-flash");
    el.addEventListener(
      "animationend",
      function () {
        el.classList.remove("ace-annotation-flash");
      },
      { once: true }
    );
  };

  // Initialize once DOM is ready
  function initAll() {
    setupSelectionListener();
    setupAnnotationClickListener();
    setupKeyboardShortcuts();
    setupCodeListSortable();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
