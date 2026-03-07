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

      // 1-9 = apply code (only when there is an active text selection)
      if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key >= "1" && e.key <= "9") {
        var sel = window.getSelection();
        if (sel && !sel.isCollapsed) {
          e.preventDefault();
          emitEvent("shortcut_apply_code", { index: parseInt(e.key) - 1 });
        }
        return;
      }
    });
  }

  // Initialize once DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setupSelectionListener();
      setupAnnotationClickListener();
      setupKeyboardShortcuts();
    });
  } else {
    setupSelectionListener();
    setupAnnotationClickListener();
    setupKeyboardShortcuts();
  }
})();
