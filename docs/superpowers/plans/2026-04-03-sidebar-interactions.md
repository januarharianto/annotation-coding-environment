# Sidebar Interaction Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix sidebar interaction conflicts — make keycap badges clickable for code application, stop overloading code-row clicks, fix reserved keycaps, fix broken cheat sheet, and add proper ARIA support for search filtering.

**Architecture:** All changes are in bridge.js (event handlers, keycap logic), coding.css (keycap styles), and coding.html (keycap markup, hint bar). No backend changes. The core change is replacing the click-to-apply handler on code rows with a keycap-badge-specific click handler and a separate click-to-focus handler.

**Tech Stack:** Vanilla JS (bridge.js), CSS, Jinja2 templates

**Spec:** `docs/superpowers/specs/2026-04-02-sidebar-interaction-model.md`

---

### Task 1: Fix Reserved Keycaps (q, x, z)

**Files:**
- Modify: `src/ace/static/js/bridge.js:171-184` (_keylabel, _keyToPosition)
- Modify: `src/ace/static/js/bridge.js:538-570` (cheat sheet)
- Modify: `src/ace/templates/coding.html:190` (hint bar)

- [ ] **Step 1: Replace `_keylabel` with a lookup array**

Replace lines 171-176 in bridge.js:

```javascript
  var _KEYCAP_LABELS = [
    "1","2","3","4","5","6","7","8","9","0",
    "a","b","c","d","e","f","g","h","i","j","k","l","m","n","o","p",
    "r","s","t","u","v","w","y"
  ];

  function _keylabel(i) {
    return i < _KEYCAP_LABELS.length ? _KEYCAP_LABELS[i] : "";
  }
```

That's 10 digits + 23 letters (a-p, r-w, y — skipping q, x, z) = 33 positions.

- [ ] **Step 2: Replace `_keyToPosition` with a reverse lookup**

Replace lines 178-184:

```javascript
  var _KEYCAP_POSITIONS = {};
  _KEYCAP_LABELS.forEach(function (label, i) { _KEYCAP_POSITIONS[label] = i; });

  function _keyToPosition(key) {
    var k = key.toLowerCase();
    var pos = _KEYCAP_POSITIONS[k];
    return pos !== undefined ? pos : -1;
  }
```

This automatically returns -1 for q, x, z since they're not in the lookup.

- [ ] **Step 3: Update the cheat sheet**

In `_toggleCheatSheet` (around line 558), change:
- `"← / →", "Previous / next source"` → `"Shift + ← / →", "Previous / next source"`
- Remove the row `"Shift + ← / →", "Jump 5 sources"` (doesn't exist)
- `"1 – 9, 0, a – z", "Apply code (per tab)"` → `"1 – 9, 0, a–y (not q x z)", "Apply code"`
- `"F2", "Rename selected code"` → `"F2", "Rename code (in sidebar)"`
- `"Delete", "Delete selected code (press twice)"` → `"Delete", "Delete code (in sidebar, press twice)"`

- [ ] **Step 4: Update the hint bar**

In `src/ace/templates/coding.html`, find the hint bar (around line 190). Change:
```html
<kbd>a</kbd>–<kbd>z</kbd> apply
```
to:
```html
<kbd>a</kbd>–<kbd>y</kbd> apply
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest -x -q`

```bash
git add src/ace/static/js/bridge.js src/ace/templates/coding.html
git commit -m "fix: skip reserved keycaps q/x/z, fix cheat sheet shortcuts and hint bar"
```

---

### Task 2: Fix _clearSearchFilter + aria-hidden on Filtered Rows

**Files:**
- Modify: `src/ace/static/js/bridge.js:1330-1333` (_clearSearchFilter)
- Modify: `src/ace/static/js/bridge.js:1339-1438` (search input handler)

- [ ] **Step 1: Fix `_clearSearchFilter` to dispatch input event**

Replace lines 1330-1333:

```javascript
  function _clearSearchFilter() {
    var el = document.getElementById("code-search-input");
    if (el && el.value) {
      el.value = "";
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }
```

- [ ] **Step 2: Add `aria-hidden` toggles to the search filter handler**

In the search input handler (line 1339), find where rows are shown/hidden. In the filter-match branch, when a row is hidden via `row.style.display = "none"`, also add `row.setAttribute("aria-hidden", "true")`. When shown, add `row.removeAttribute("aria-hidden")`.

In the filter code, find the line that sets `row.style.display = "none"` for non-matching rows and add `aria-hidden`:

```javascript
if (match) {
  row.style.display = "";
  row.removeAttribute("aria-hidden");
  // ... highlight logic
} else {
  row.style.display = "none";
  row.setAttribute("aria-hidden", "true");
  // ... strip highlight
}
```

Also do the same for group headers: when hidden, set `aria-hidden="true"`, when shown, remove it.

In the empty-query (restore) branch, remove `aria-hidden` from all rows and headers:

```javascript
row.removeAttribute("aria-hidden");
```

- [ ] **Step 3: Run tests and commit**

Run: `uv run pytest -x -q`

```bash
git add src/ace/static/js/bridge.js
git commit -m "fix: _clearSearchFilter dispatches input event, filtered rows get aria-hidden"
```

---

### Task 3: Fix Group Header + Remove F2/Delete from Text Zone

**Files:**
- Modify: `src/ace/static/js/bridge.js:116-127` (group header click)
- Modify: `src/ace/static/js/bridge.js:343-359` (F2 and Delete in text zone)

- [ ] **Step 1: Fix group header single-click toggle**

Replace lines 116-127:

```javascript
  document.addEventListener("click", function (e) {
    var header = e.target.closest(".ace-code-group-header");
    if (header && !e.target.closest(".ace-code-menu")) {
      _focusTreeItem(header);
      _toggleGroupCollapse(header);
      var groupName = header.getAttribute("data-group") || "Ungrouped";
      var expanded = header.getAttribute("aria-expanded") === "true";
      _announce("Group " + groupName + (expanded ? " expanded" : " collapsed"));
    }
  });
```

This always focuses AND toggles in one click, plus announces the state change.

- [ ] **Step 2: Remove F2 handler from text zone**

Delete lines 343-348 (the `if (key === "F2" && _lastSelectedCodeId)` block) from the main keydown handler. F2 still works in the tree zone (handled by the tree keydown handler).

- [ ] **Step 3: Remove Delete/Backspace handler from text zone**

Delete lines 350-359 (the `if ((key === "Delete" || key === "Backspace") && _lastSelectedCodeId` block) from the main keydown handler. Delete still works in the tree zone.

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest -x -q`

```bash
git add src/ace/static/js/bridge.js
git commit -m "fix: group header single-click toggle, remove stale F2/Delete from text zone"
```

---

### Task 4: Keycap Badge Click + Click-to-Focus on Code Rows

**Files:**
- Modify: `src/ace/static/js/bridge.js:1313-1327` (replace click-to-apply)
- Modify: `src/ace/static/css/coding.css` (keycap hover, target size, focus-visible)
- Modify: `src/ace/templates/coding.html:109,125` (keycap aria-label)

- [ ] **Step 1: Update keycap markup in template**

In `src/ace/templates/coding.html`, find the two `<span class="ace-keycap"></span>` elements (lines 109 and 125). Add `aria-label`:

```html
<span class="ace-keycap" aria-label="Apply code"></span>
```

- [ ] **Step 2: Add keycap CSS styles**

Add to `src/ace/static/css/coding.css` after the existing `.ace-keycap` rule:

```css
.ace-keycap {
  cursor: pointer;
  min-height: 24px;
  min-width: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background var(--ace-transition), border-color var(--ace-transition);
}

.ace-keycap:hover {
  border-color: var(--ace-text-muted);
  background: var(--ace-bg-muted);
}

.ace-keycap:focus-visible {
  outline: 2px solid var(--ace-focus);
  outline-offset: 1px;
}
```

Note: This modifies the existing `.ace-keycap` rule — merge the new properties into it, keeping existing ones (font, border, border-radius, etc.).

- [ ] **Step 3: Replace the click-to-apply handler with keycap badge click + click-to-focus**

Replace lines 1313-1327 (the current click-to-apply handler) with two handlers:

```javascript
  // Keycap badge click: apply code to focused sentence/selection
  document.addEventListener("click", function (e) {
    var keycap = e.target.closest(".ace-keycap");
    if (!keycap) return;
    e.stopPropagation(); // Don't bubble to code-row focus handler
    var row = keycap.closest(".ace-code-row");
    if (!row) return;
    // Bail out during rename
    if (row.querySelector('[contenteditable="true"]')) return;
    var codeId = row.getAttribute("data-code-id");
    if (!codeId) return;
    _clearSearchFilter();
    if (window.__aceLastSelection) {
      _applyCodeToSelection(codeId);
    } else if (window.__aceFocusIndex >= 0) {
      _applyCodeToSentence(codeId);
    }
  });

  // Click on code row (not keycap): focus/select for management
  document.addEventListener("click", function (e) {
    var row = e.target.closest(".ace-code-row");
    if (!row) return;
    // Don't interfere with keycap click, context menu, drag, or rename
    if (e.target.closest(".ace-keycap")) return;
    if (e.target.closest(".ace-code-menu") || _isDragging) return;
    if (e.target.isContentEditable) return;
    _focusTreeItem(row);
  });
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest -x -q`

```bash
git add src/ace/static/js/bridge.js src/ace/static/css/coding.css src/ace/templates/coding.html
git commit -m "feat: keycap badge click-to-apply, click-to-focus on code rows"
```

---

### Task 5: Search Target Highlight + Consistent Apply Paths

**Files:**
- Modify: `src/ace/static/js/bridge.js` (search input handler, tree Enter, search Enter)
- Modify: `src/ace/static/css/coding.css` (search target class)

- [ ] **Step 1: Add search target CSS**

Add to coding.css:

```css
.ace-code-row--search-target {
  background: var(--ace-bg-muted);
}
```

- [ ] **Step 2: Add search target highlight to the input handler**

In the search input handler (line 1339), at the end of the filter-match branch (before `_updateKeycaps()`):

1. Remove any existing search target: `tree.querySelector(".ace-code-row--search-target, [aria-current]")` — remove class and attribute.
2. Find the first visible code row and add the class + `aria-current="true"`.

Add this block right before the `_updateKeycaps()` call at the end of the filter branch:

```javascript
    // Highlight first visible match as search target
    var prevTarget = tree.querySelector(".ace-code-row--search-target");
    if (prevTarget) {
      prevTarget.classList.remove("ace-code-row--search-target");
      prevTarget.removeAttribute("aria-current");
    }
    if (anyMatch) {
      var firstMatch = null;
      tree.querySelectorAll(".ace-code-row").forEach(function (r) {
        if (!firstMatch && r.style.display !== "none") firstMatch = r;
      });
      if (firstMatch) {
        firstMatch.classList.add("ace-code-row--search-target");
        firstMatch.setAttribute("aria-current", "true");
      }
    }
```

In the empty-query (restore) branch, also clean up:

```javascript
    var prevTarget = tree.querySelector(".ace-code-row--search-target");
    if (prevTarget) {
      prevTarget.classList.remove("ace-code-row--search-target");
      prevTarget.removeAttribute("aria-current");
    }
```

- [ ] **Step 3: Make all apply paths consistent**

Create a helper function that all apply paths use:

```javascript
  function _applyCode(codeId) {
    var codeName = "";
    var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
    if (row) {
      var nameEl = row.querySelector(".ace-code-name");
      if (nameEl) codeName = nameEl.textContent;
    }
    if (window.__aceLastSelection) {
      _applyCodeToSelection(codeId);
    } else if (window.__aceFocusIndex >= 0) {
      _applyCodeToSentence(codeId);
    } else {
      return; // Nothing to apply to
    }
    if (codeName) {
      var target = window.__aceLastSelection ? "selection" : "sentence " + (window.__aceFocusIndex + 1);
      _announce("'" + codeName + "' applied to " + target);
    }
  }
```

Then update these call sites to use `_applyCode(codeId)` instead of `_applyCodeToSentence(codeId)`:

1. **Keycap badge click handler** (from Task 4) — replace the `if (__aceLastSelection)` / `else` block with `_applyCode(codeId)`
2. **Search Enter handler** (around line 1536) — replace `_applyCodeToSentence(codeId)` with `_applyCode(codeId)`
3. **Tree Enter handler** (around line 1950) — replace `_applyCodeToSentence(codeId3)` with `_applyCode(codeId3)`

Do NOT change the main keycap hotkey handler (line 437-449) or the Q repeat handler — they already handle custom selection and can keep their existing logic.

- [ ] **Step 4: Update Tree Enter — clear filter and conditionally return focus**

In the tree Enter handler (around line 1950), after calling `_applyCode(codeId3)`, add filter-aware focus logic:

```javascript
          _clearSearchFilter();
          _applyCode(codeId3);
          // If we came from search (filter was active), return to text panel
          // Otherwise stay in tree for multi-code workflow
          var searchInput = document.getElementById("code-search-input");
          // _clearSearchFilter already cleared it, so check if we just cleared
          // Use a flag or check if the tree was entered from search
          // Simplest: always flash the row, the focus handling is in _restoreFocus
          active.classList.add("ace-code-row--flash");
          setTimeout(function () { active.classList.remove("ace-code-row--flash"); }, 300);
```

Actually, the simplest approach per the spec: `_applyCodeToSentence` already calls `.then(_restoreFocus)` which calls `_focusTextPanel()`. So focus always returns to text after apply. This is consistent and correct. Remove the current flash/announce code after the apply since `_applyCode` handles the announce.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest -x -q`

```bash
git add src/ace/static/js/bridge.js src/ace/static/css/coding.css
git commit -m "feat: search target highlight, consistent apply paths with announce"
```

---

### Task 6: Escape from Tree Clears Filter + Disable Sortable + Dropdown Escape

**Files:**
- Modify: `src/ace/static/js/bridge.js` (tree Escape, Sortable, dropdown Escape)

- [ ] **Step 1: Update tree Escape to clear filter**

Find the tree Escape handler (around line 2055). Replace:

```javascript
    // Escape — Return to text panel
    if (key === "Escape" && !alt && !shift) {
      e.preventDefault();
      _focusTextPanel();
      return;
    }
```

With:

```javascript
    // Escape — Clear search filter (if active) and return to text panel
    if (key === "Escape" && !alt && !shift) {
      e.preventDefault();
      _clearSearchFilter();
      _focusTextPanel();
      return;
    }
```

- [ ] **Step 2: Disable Sortable during search filter**

In the search input handler (around line 1339), add Sortable disable/enable:

At the start of the filter branch (when `query && !query.startsWith("/")` is true), add:

```javascript
      _sortableInstances.forEach(function (s) { s.option("disabled", true); });
```

At the start of the empty-query (restore) branch, add:

```javascript
      _sortableInstances.forEach(function (s) { s.option("disabled", false); });
```

Also in the `/group` branch, disable Sortable:

```javascript
      _sortableInstances.forEach(function (s) { s.option("disabled", true); });
```

- [ ] **Step 3: Fix codebook dropdown Escape — add stopPropagation**

Find the codebook dropdown Escape handler (around line 2177). Add `e.stopPropagation()`:

```javascript
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var dropdown = document.getElementById("codebook-dropdown");
      if (dropdown && dropdown.style.display !== "none") {
        dropdown.style.display = "none";
        e.stopPropagation();
      }
    }
  });
```

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest -x -q`

```bash
git add src/ace/static/js/bridge.js
git commit -m "fix: tree Escape clears filter, disable Sortable during search, dropdown Escape stopPropagation"
```

---

### Task 7: Verification + Cleanup

**Files:**
- Modify: `src/ace/static/js/bridge.js` (if needed)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -x -q`
All tests must pass.

- [ ] **Step 2: Verify in browser — complete walkthrough**

1. Keycap badges show correct sequence (1-9, 0, a-p, r-w, y — no q, x, z)
2. Press `q` → repeats last code (NOT apply position 26)
3. Press `x` → removes annotation (NOT apply)
4. Press `z` → undo (NOT apply)
5. Click a keycap badge → applies code to focused sentence → focus returns to text
6. Click a code row (not badge) → focuses/selects the code row (no apply)
7. Double-click code name → inline rename
8. Right-click code → context menu
9. Click group header → immediate toggle (no two-click dance)
10. `/` → type to filter → first match highlighted with background
11. Enter → applies first match → filter clears → focus returns to text
12. `/` → type → ↓↓ → Enter → applies focused code → filter clears
13. Escape from tree (with filter active) → filter clears → focus to text
14. Drag-and-drop disabled while filter is active
15. Cheat sheet (?) shows corrected shortcuts
16. Hint bar shows a–y (not a–z)
17. F2 from text panel does nothing (removed)
18. F2 from tree zone renames focused code

- [ ] **Step 3: Commit if any cleanup needed**

```bash
git add src/ace/static/js/bridge.js
git commit -m "refactor: final cleanup after interaction model verification"
```
