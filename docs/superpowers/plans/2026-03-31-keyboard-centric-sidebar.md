# Keyboard-Centric Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the coding sidebar as an ARIA-compliant treeview with full keyboard navigation, search-bar code/group creation, and focus restoration across HTMX swaps.

**Architecture:** The sidebar HTML template gets ARIA tree roles. bridge.js gains a new "Sidebar keyboard navigation" section implementing roving tabindex, zone cycling (Tab), tree operations (arrow keys, F2, Alt+arrows, Delete), and enhanced search bar. CSS additions are minimal — focus ring and reorder/delete states. API routes and data model are unchanged.

**Tech Stack:** Jinja2 templates, vanilla JS (no new libraries), CSS, ARIA treeview pattern, existing HTMX + Sortable.js

**Spec:** `docs/superpowers/specs/2026-03-31-keyboard-centric-sidebar-design.md`

---

### Task 1: ARIA Treeview Template

**Files:**
- Modify: `src/ace/templates/coding.html:74-111`
- Test: `tests/test_coding_routes.py`

- [ ] **Step 1: Write failing test — sidebar has ARIA tree roles**

Add to `tests/test_coding_routes.py`:

```python
def test_sidebar_has_aria_tree_roles(client_with_sources):
    """Sidebar renders with ARIA treeview roles."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert 'role="tree"' in html
    assert 'aria-label="Code list"' in html
    assert 'role="treeitem"' in html
    assert 'role="group"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coding_routes.py::test_sidebar_has_aria_tree_roles -v`
Expected: FAIL — current template has no ARIA roles.

- [ ] **Step 3: Rebuild sidebar template with ARIA roles**

Replace `{% block code_sidebar %}` in `src/ace/templates/coding.html` (lines 74-111) with:

```html
{% block code_sidebar %}
<div id="code-sidebar" class="ace-sidebar">
  <div class="ace-sidebar-toolbar">
    <input type="search" class="ace-sidebar-search" placeholder="Filter codes (/)"
           id="code-search-input" autocomplete="off"
           aria-controls="code-tree">
  </div>
  <div id="code-tree" role="tree" aria-label="Code list" class="ace-sidebar-codes">
    {% for group_name, group_codes in grouped_codes %}
    <div role="treeitem" aria-expanded="true" aria-level="1"
         class="ace-code-group-header" data-group="{{ group_name }}"
         tabindex="-1">&#9662; {{ group_name }}</div>
    <div role="group">
      {% for code in group_codes %}
      <div role="treeitem" aria-level="2"
           class="ace-code-row" data-code-id="{{ code['id'] }}"
           tabindex="-1">
        <span class="ace-code-dot" style="background: {{ code['colour'] }};"></span>
        <span class="ace-code-name">{{ code['name'] }}</span>
        <span class="ace-keycap"></span>
      </div>
      {% endfor %}
    </div>
    {% endfor %}
    {% if ungrouped_codes %}
    <div role="treeitem" aria-expanded="true" aria-level="1"
         class="ace-code-group-header" data-group=""
         tabindex="-1">&#9662; Ungrouped</div>
    <div role="group">
      {% for code in ungrouped_codes %}
      <div role="treeitem" aria-level="2"
           class="ace-code-row" data-code-id="{{ code['id'] }}"
           tabindex="-1">
        <span class="ace-code-dot" style="background: {{ code['colour'] }};"></span>
        <span class="ace-code-name">{{ code['name'] }}</span>
        <span class="ace-keycap"></span>
      </div>
      {% endfor %}
    </div>
    {% endif %}
    {% if not codes %}
    <div class="ace-sidebar-empty">No codes yet. Type a name above and press Enter.</div>
    {% endif %}
  </div>
  <div aria-live="polite" class="ace-sr-only" id="ace-live-region"></div>
</div>
{% endblock %}
```

Key changes from current template:
- `<input type="text">` → `<input type="search">` with `aria-controls="code-tree"`
- Placeholder "Search or create code…" → "Filter codes (/)"
- `#view-groups` → `#code-tree` with `role="tree"` and `aria-label`
- Group wrapper `<div class="ace-code-group">` removed — group headers are `role="treeitem"` with `aria-expanded`, children wrapped in `role="group"` div
- All code rows get `role="treeitem"`, `aria-level`, `tabindex="-1"`
- `#add-group-row` removed (group creation moves to search bar `/prefix`)
- Added hidden `#ace-live-region` for screen reader announcements
- Empty state text updated (no more "management mode" reference)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_coding_routes.py::test_sidebar_has_aria_tree_roles -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -x -q`
Expected: All tests pass. Some tests may need updating if they assert on old sidebar HTML (e.g. checking for `id="view-groups"` or `class="ace-code-group"`). Fix any failures by updating selectors.

- [ ] **Step 6: Commit**

```bash
git add src/ace/templates/coding.html tests/test_coding_routes.py
git commit -m "feat: rebuild sidebar template with ARIA treeview roles"
```

---

### Task 2: Sidebar CSS Updates

**Files:**
- Modify: `src/ace/static/css/coding.css:157-297`

- [ ] **Step 1: Add focus, reorder, and sr-only styles**

Add to `coding.css` after the existing `.ace-code-row` styles (around line 207):

```css
/* Focused treeitem (roving tabindex) */
.ace-code-row:focus {
  background: var(--ace-bg-muted);
  outline: 2px solid var(--ace-focus);
  outline-offset: -2px;
  border-radius: var(--ace-radius);
}

.ace-code-row:focus .ace-code-name {
  font-weight: 600;
}

/* Focused group header */
.ace-code-group-header:focus {
  outline: 2px solid var(--ace-focus);
  outline-offset: -2px;
  border-radius: var(--ace-radius);
  background: var(--ace-bg-muted);
}

/* Reorder-in-progress (dashed outline) */
.ace-code-row--reordering {
  outline: 2px dashed var(--ace-focus);
  outline-offset: -2px;
  background: rgba(59, 130, 246, 0.08);
  border-radius: var(--ace-radius);
}

/* Screen reader only (visually hidden, accessible) */
.ace-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

- [ ] **Step 2: Update group header styles for new DOM structure**

The old template wrapped groups in `.ace-code-group` divs — the new template has flat `role="treeitem"` headers with `role="group"` siblings. Update `.ace-code-group-header` styles and the collapse class.

Replace the existing `.ace-code-group--collapsed .ace-code-row` rule (line ~177) with:

```css
/* Collapsed group: hide the role="group" sibling's children */
.ace-code-group-header[aria-expanded="false"] + [role="group"] .ace-code-row {
  display: none;
}
```

- [ ] **Step 3: Add shortcut hint style for context menu**

Add after the existing `.ace-code-menu-item` styles:

```css
.ace-code-menu-hint {
  font-size: var(--ace-font-size-2xs);
  font-family: var(--ace-font-mono);
  color: var(--ace-text-muted);
  margin-left: auto;
  padding-left: var(--ace-space-3);
}
```

- [ ] **Step 4: Add create-prompt style for search bar**

```css
.ace-create-prompt {
  padding: 5px 10px;
  font-size: var(--ace-font-size-sm);
  color: var(--ace-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--ace-space-1);
}

.ace-create-prompt:hover {
  background: var(--ace-bg-muted);
}

.ace-create-prompt--code {
  color: #166534;
  background: rgba(34, 197, 94, 0.06);
}

.ace-create-prompt--group {
  color: #6b21a8;
  background: rgba(168, 85, 247, 0.06);
}
```

- [ ] **Step 5: Verify styles render in browser**

Open http://127.0.0.1:8080/code and confirm:
- No visual regressions (sidebar looks the same as before at rest)
- Group collapse still works (click headers)
- Code rows show focus ring when clicked

- [ ] **Step 6: Commit**

```bash
git add src/ace/static/css/coding.css
git commit -m "style: add ARIA focus states, reorder visual, create-prompt styles"
```

---

### Task 3: Roving Tabindex & Arrow Key Navigation

**Files:**
- Modify: `src/ace/static/js/bridge.js`

This task adds the core tree navigation: roving tabindex management and arrow key movement within the code tree. All new code goes in a new section "18. Sidebar keyboard navigation" before section 17 (DOMContentLoaded).

- [ ] **Step 1: Add roving tabindex helper functions**

Add new section before the DOMContentLoaded section (before line 1388):

```javascript
  /* ================================================================
   * 18. Sidebar keyboard navigation (ARIA treeview)
   * ================================================================ */

  // --- Roving tabindex ---

  /** Return all visible treeitems (group headers + code rows) in DOM order. */
  function _getTreeItems() {
    var tree = document.getElementById("code-tree");
    if (!tree) return [];
    // Select all treeitems, then filter out hidden ones
    var items = tree.querySelectorAll('[role="treeitem"]');
    var result = [];
    items.forEach(function (item) {
      // Skip code rows inside collapsed groups
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
    // Remove tabindex="0" from all treeitems
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
```

- [ ] **Step 2: Add arrow key handler for the code tree**

Add immediately after the helpers:

```javascript
  // --- Tree keydown handler ---

  document.addEventListener("keydown", function (e) {
    var tree = document.getElementById("code-tree");
    if (!tree || !tree.contains(document.activeElement)) return;
    // Only handle when a treeitem is focused (not during rename/editing)
    var active = document.activeElement;
    if (!active || active.getAttribute("role") !== "treeitem") return;
    if (active.querySelector('[contenteditable="true"]')) return;

    var key = e.key;
    var alt = e.altKey;
    var shift = e.shiftKey;
    var items = _getTreeItems();
    var idx = items.indexOf(active);

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
          // Expand
          _expandGroup(active);
        } else {
          // Move to first child
          var groupDiv = active.nextElementSibling;
          if (groupDiv && groupDiv.getAttribute("role") === "group") {
            var firstChild = groupDiv.querySelector('[role="treeitem"]');
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
        // Code row: jump to parent group header
        var groupEl = active.closest('[role="group"]');
        if (groupEl) {
          var header = groupEl.previousElementSibling;
          if (header && _isGroupHeader(header)) _focusTreeItem(header);
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
  });
```

- [ ] **Step 3: Add expand/collapse helpers using aria-expanded**

Add after the arrow key handler:

```javascript
  // --- Group expand / collapse ---

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
```

- [ ] **Step 4: Update existing collapse functions to use aria-expanded**

The old `_setGroupCollapsed` (lines 87-103) uses class `ace-code-group--collapsed` on a parent div that no longer exists. Replace it:

```javascript
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
```

- [ ] **Step 5: Update click handler for group headers**

The existing click handler (around line 125) uses `.closest(".ace-code-group")` which no longer exists. Update:

```javascript
  document.addEventListener("click", function (e) {
    var header = e.target.closest(".ace-code-group-header");
    if (header && !e.target.closest(".ace-code-menu")) {
      _toggleGroupCollapse(header);
    }
  });
```

This should still work since it only depends on `.ace-code-group-header`, not `.ace-code-group`.

- [ ] **Step 6: Update _updateKeycaps to work with new DOM**

The current `_updateKeycaps` queries `#view-groups .ace-code-row:not(.ace-code-row--hidden)`. Update to use `#code-tree` and check `aria-expanded`:

```javascript
  function _updateKeycaps() {
    var tree = document.getElementById("code-tree");
    if (!tree) return;
    // Get all code rows, skip ones in collapsed groups
    var rows = tree.querySelectorAll('.ace-code-row');
    _currentKeyMap = [];
    rows.forEach(function (row) {
      // Check if inside a collapsed group
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
    });
  }
```

- [ ] **Step 7: Update _initSortable to work with new DOM**

The current Sortable targets `.ace-code-group` containers. With the new DOM, draggable code rows live inside `[role="group"]` divs. Update:

```javascript
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
          // Determine new group from the header preceding the container
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
```

- [ ] **Step 8: Update htmx:afterSettle to use new IDs**

Update the afterSettle handler (line ~749) to reference `code-tree` instead of `code-sidebar`:

```javascript
    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      if (!_isDragging) _initSortable();
      _restoreCollapseState();
      _updateKeycaps();
    }
```

This stays the same — the target is still `code-sidebar` (the outer swap target). No change needed here since the inner `#code-tree` is inside `#code-sidebar`.

- [ ] **Step 9: Verify in browser**

Open http://127.0.0.1:8080/code and verify:
- Click a code row → it gets focus ring
- Press ↑/↓ → focus moves between codes and group headers
- Press ← on expanded group header → collapses
- Press → on collapsed group header → expands
- Press → on expanded group header → jumps to first child
- Press ← on code row → jumps to parent group header
- Home/End jump to first/last item
- Group collapse/expand still works by click
- Drag-and-drop still works

- [ ] **Step 10: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: add roving tabindex and arrow key navigation to code tree"
```

---

### Task 4: Tab Zone Cycling & Escape

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add zone cycling logic**

Add to the section 18 block in bridge.js:

```javascript
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
```

- [ ] **Step 2: Add Tab/Shift+Tab zone cycling handler**

Add a keydown handler that intercepts Tab at the zone level. This must run before the tree's arrow key handler since it handles Tab within the tree:

```javascript
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
```

- [ ] **Step 3: Add `/` shortcut from text panel to search bar**

In the existing main keydown handler (around line 404, the `key.length === 1` block), add a check for `/` BEFORE the keycap code-apply logic:

```javascript
    // / — Jump to sidebar search bar
    if (key === "/" && !shift) {
      e.preventDefault();
      _focusSearchBar();
      return;
    }
```

Insert this just before the `if (!shift && key.length === 1)` block.

- [ ] **Step 4: Add Escape handling in tree keydown handler**

Add to the tree keydown handler (from Task 3, Step 2), inside the handler function:

```javascript
    // Escape — Return to text panel
    if (key === "Escape" && !alt && !shift) {
      e.preventDefault();
      _focusTextPanel();
      return;
    }
```

- [ ] **Step 5: Update search bar Escape to be layered**

Replace the existing Escape handler in the search bar keydown (around line 1247):

```javascript
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    if (e.target.value) {
      // First press: clear search text
      e.target.value = "";
      e.target.dispatchEvent(new Event("input"));
    } else {
      // Second press (or already empty): return to text panel
      _focusTextPanel();
    }
    return;
  }
```

- [ ] **Step 6: Add ↓ from search bar to tree**

In the search bar keydown handler, add:

```javascript
  if (e.key === "ArrowDown") {
    e.preventDefault();
    _focusCodeTree();
    return;
  }
```

- [ ] **Step 7: Guard main keydown handler to text-panel-only**

The main keydown handler (line 252) currently fires for all non-typing keydowns. With the tree now handling its own keys, the main handler should only fire when text panel has focus. Update the guard at the top:

```javascript
  document.addEventListener("keydown", function (e) {
    if (_isTyping()) return;
    if (_menuOpen) return;
    // Only handle keys when text panel (or no sidebar element) is focused
    var zone = _activeZone();
    if (zone === "search" || zone === "tree") return;
```

- [ ] **Step 8: Verify in browser**

- From text panel: Tab → search bar → Tab → code tree → Tab → text panel
- Shift+Tab reverses the cycle
- `/` from text panel → search bar gets focus
- Escape from search (with text) → clears text, stays in search
- Escape from search (empty) → text panel
- Escape from tree → text panel
- Keycap shortcuts (1-9, a-z) only work when text panel has focus

- [ ] **Step 9: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: add Tab zone cycling, / shortcut, and layered Escape"
```

---

### Task 5: Enhanced Search Bar (Filter Highlight, Create Prompt, /Group)

**Files:**
- Modify: `src/ace/static/js/bridge.js`
- Test: `tests/test_coding_routes.py`

- [ ] **Step 1: Write failing test — create code via search bar auto-applies**

```python
def test_create_code_applies_to_sentence(client_with_sources):
    """Creating a code with current_index set applies to the focused sentence."""
    client, coder_id = client_with_sources
    # Create a new code — the API endpoint is POST /api/codes
    resp = client.post("/api/codes", data={"name": "NewCode", "current_index": "0"})
    assert resp.status_code == 200
    # The code should exist in the returned sidebar HTML
    assert "NewCode" in resp.text
```

- [ ] **Step 2: Run test to verify it passes (existing behaviour)**

Run: `uv run pytest tests/test_coding_routes.py::test_create_code_applies_to_sentence -v`
Expected: PASS — this verifies the API already handles creation. The auto-apply on creation is client-side JS (the htmx.ajax call chains an apply after create).

- [ ] **Step 3: Add filter match highlighting**

Update the search input handler in bridge.js (the `document.addEventListener("input", ...)` handler around line 1200). After showing/hiding rows, add highlight to matching text:

```javascript
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
          nameEl.textContent = text; // Clear highlight
        }
      });

      // Show/hide group headers based on visible children
      tree.querySelectorAll(".ace-code-group-header").forEach(function (header) {
        var groupDiv = header.nextElementSibling;
        if (!groupDiv || groupDiv.getAttribute("role") !== "group") return;
        var visible = groupDiv.querySelectorAll('.ace-code-row[style=""], .ace-code-row:not([style])');
        // More reliable: check computed display
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
        // Check if group already exists
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
          prompt.innerHTML = '<span>▸</span> Create group "<strong>' + _escapeHtml(groupName) + '</strong>"';
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
```

- [ ] **Step 4: Add _escapeHtml helper**

Add near the top of the IIFE (after the toast section):

```javascript
  function _escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
```

- [ ] **Step 5: Add create-code and create-group functions**

Replace the existing search Enter handler (around line 1243) with:

```javascript
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

    // Create group by inserting DOM (same as old aceStartAddGroup, but server-side on next action)
    var tree = document.getElementById("code-tree");
    if (!tree) return;

    // Find insertion point (before first existing group header, or at start)
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

    // Insert before the empty-state or at end
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

  // Search bar keydown: Enter to create, ↓ to tree
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
      var visibleRows = tree ? tree.querySelectorAll('.ace-code-row[style=""], .ace-code-row:not([style*="none"])') : [];
      // More robust: count rows not hidden
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
```

- [ ] **Step 6: Add _announce helper for aria-live**

```javascript
  /** Push a message to the aria-live region for screen readers. */
  function _announce(message) {
    var region = document.getElementById("ace-live-region");
    if (!region) return;
    region.textContent = message;
    // Clear after a delay so repeated messages are announced
    setTimeout(function () { region.textContent = ""; }, 3000);
  }
```

- [ ] **Step 7: Remove old search handler and aceStartAddGroup**

Delete the old `document.addEventListener("input", ...)` for `code-search-input` (lines ~1200-1240) and the old `document.addEventListener("keydown", ...)` for search Enter (lines ~1243-1274). Also delete `window.aceStartAddGroup` (lines ~1161-1193) since group creation now happens via `/prefix` in search bar.

- [ ] **Step 8: Verify in browser**

- Type in search bar → codes filter live, matching text highlighted in `<mark>`
- Type non-matching text → green "Create" prompt appears
- Press Enter with no matches → code created
- Type `/Emotions` → purple "Create group" prompt appears
- Press Enter → group created
- Type `/Themes` (existing) → "already exists" message
- Escape with text → clears, Escape again → text panel

- [ ] **Step 9: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: enhanced search bar with filter highlights, create prompts, /group creation"
```

---

### Task 6: Tree Keyboard Operations (F2, Alt+Arrows, Delete)

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add Enter-to-apply in the tree keydown handler**

Add to the tree keydown handler (from Task 3, Step 2):

```javascript
    // Enter — Apply focused code to current sentence (stay in tree)
    if (key === "Enter" && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        var codeId = active.getAttribute("data-code-id");
        if (codeId && window.__aceFocusIndex >= 0) {
          _applyCodeToSentence(codeId);
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
```

- [ ] **Step 2: Add F2 rename in the tree keydown handler**

```javascript
    // F2 — Inline rename
    if (key === "F2" && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        var codeId = active.getAttribute("data-code-id");
        if (codeId) _startInlineRename(codeId);
      }
      return;
    }
```

- [ ] **Step 3: Add Delete/Backspace in the tree keydown handler**

```javascript
    // Delete / Backspace — Delete code (double-press confirm)
    if ((key === "Delete" || key === "Backspace") && !alt && !shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        var codeId = active.getAttribute("data-code-id");
        if (!codeId) return;
        if (_deleteTarget === codeId) {
          _executeDelete(codeId);
        } else {
          _startDeleteConfirm(codeId);
        }
      }
      return;
    }
```

- [ ] **Step 4: Add Alt+Shift+↑/↓ for keyboard reordering**

```javascript
    // Alt+Shift+↑ — Move code up
    if (key === "ArrowUp" && alt && shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(active.getAttribute("data-code-id"), -1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      }
      return;
    }

    // Alt+Shift+↓ — Move code down
    if (key === "ArrowDown" && alt && shift) {
      e.preventDefault();
      if (!_isGroupHeader(active)) {
        active.classList.add("ace-code-row--reordering");
        _moveCode(active.getAttribute("data-code-id"), 1);
        setTimeout(function () { active.classList.remove("ace-code-row--reordering"); }, 300);
      }
      return;
    }
```

- [ ] **Step 5: Add Alt+→ for indent (move into group)**

```javascript
    // Alt+→ — Indent: move code into nearest group above
    if (key === "ArrowRight" && alt && !shift) {
      e.preventDefault();
      if (_isGroupHeader(active)) return;
      var codeId = active.getAttribute("data-code-id");
      if (!codeId) return;

      // Find the nearest group header above this code
      var prev = active.previousElementSibling;
      var targetGroup = null;
      // Walk backwards to find a role="group" or group header
      var groupDiv = active.closest('[role="group"]');
      if (groupDiv) {
        // Already in a group — do nothing (one level only)
        return;
      }
      // Ungrouped code — find nearest group header above
      var el = active;
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
      var codeId = active.getAttribute("data-code-id");
      if (!codeId) return;

      var groupDiv = active.closest('[role="group"]');
      if (!groupDiv) return; // Already ungrouped

      _moveToGroup(codeId, "");
      _announce("'" + (active.querySelector(".ace-code-name") || {}).textContent + "' moved to ungrouped");
      return;
    }
```

- [ ] **Step 6: Add inline group-name prompt for indent-without-group**

```javascript
  function _promptNewGroupForCode(codeRow) {
    // Show a small inline input above the code row asking for group name
    var input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Group name…";
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
          // Create the group then move the code into it
          var codeId = codeRow.getAttribute("data-code-id");
          // Insert group header + group div before the code
          var tree = document.getElementById("code-tree");
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
          // Move the code row into the group
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
```

- [ ] **Step 7: Update _startInlineRename to restore tree focus**

The current `_startInlineRename` (lines 896-944) refocuses the text panel after rename. Update the `save()` function to restore focus to the code row instead:

In `_startInlineRename`, change `document.getElementById("text-panel").focus();` (in both save and Escape paths) to:

```javascript
    // After rename, restore focus to the tree item
    _focusTreeItem(row);
```

And in the Escape handler similarly:

```javascript
    if (e.key === "Escape") {
      e.preventDefault();
      nameEl.removeEventListener("keydown", handler);
      done = true;
      nameEl.textContent = original;
      nameEl.contentEditable = "false";
      _focusTreeItem(row);
    }
```

- [ ] **Step 8: Verify in browser**

- Focus a code in tree → Enter → flash + code applied to sentence
- Focus a code → F2 → inline rename, Enter saves, Escape cancels, focus returns to row
- Focus a code → Alt+Shift+↑ → code moves up (dashed outline briefly)
- Focus a code → Alt+Shift+↓ → code moves down
- Focus ungrouped code → Alt+→ → moves into group above (or prompts for name)
- Focus grouped code → Alt+← → moves to ungrouped
- Focus a code → Delete → red confirm → Delete again → deleted
- Focus group header → Enter → toggles expand/collapse

- [ ] **Step 9: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: keyboard tree operations — Enter apply, F2 rename, Alt+arrows indent/reorder, Delete"
```

---

### Task 7: Context Menu Shortcut Hints

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add shortcut hints to context menu items**

Update `_openCodeMenu` (around line 1064). Change the `items` array to include hints:

```javascript
  var items = [
    { label: "Rename", hint: "F2", action: function () { _closeCodeMenu(); _startInlineRename(codeId); } },
    { label: "Colour", hint: "", action: function () { _closeCodeMenu(); _openColourPopover(codeId); } },
    { label: "Move Up", hint: "Alt+Shift+\u2191", action: function () { _closeCodeMenu(); _moveCode(codeId, -1); } },
    { label: "Move Down", hint: "Alt+Shift+\u2193", action: function () { _closeCodeMenu(); _moveCode(codeId, 1); } },
    { label: "Delete", hint: "\u232b", danger: true, action: function () { _closeCodeMenu(); _startDeleteConfirm(codeId); } },
  ];
```

And in the "Move to Group" submenu item, add hint:

```javascript
    moveItem.textContent = "Move to Group \u25b8";
    // Add hint
    var moveHint = document.createElement("span");
    moveHint.className = "ace-code-menu-hint";
    moveHint.textContent = "Alt+\u2192";
    moveItem.appendChild(moveHint);
```

Update the rendering loop to include hints:

```javascript
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
```

- [ ] **Step 2: Verify in browser**

Right-click a code → menu shows shortcut hints aligned right in muted monospace text.

- [ ] **Step 3: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: add keyboard shortcut hints to context menu"
```

---

### Task 8: Focus Restoration After HTMX Swaps

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Track focused treeitem before HTMX swap**

Add a `htmx:beforeSwap` listener that records the currently focused code ID and search bar state:

```javascript
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
```

- [ ] **Step 2: Restore focus after HTMX swap**

Update the existing `htmx:afterSettle` handler. After the sidebar restoration block (`_initSortable`, `_restoreCollapseState`, `_updateKeycaps`), add:

```javascript
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
```

- [ ] **Step 3: Add aria-keyshortcuts to code rows on keycap update**

Update `_updateKeycaps` to set `aria-keyshortcuts`:

After `if (keycap) keycap.textContent = _keylabel(_currentKeyMap.length - 1);` add:

```javascript
      row.setAttribute("aria-keyshortcuts", _keylabel(_currentKeyMap.length - 1));
```

- [ ] **Step 4: Verify in browser**

- Focus a code in tree → apply with Enter (triggers HTMX swap) → focus returns to same code
- Focus a code → delete → focus moves to next code
- Type in search bar → create code (HTMX swap) → search bar clears, sidebar updated
- Scroll down in long code list → do an action → scroll position preserved

- [ ] **Step 5: Commit**

```bash
git add src/ace/static/js/bridge.js
git commit -m "feat: focus and scroll restoration across HTMX sidebar swaps"
```

---

### Task 9: DOMContentLoaded Update & Cleanup

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Update DOMContentLoaded init**

Update the init block (line 1392) to set initial roving tabindex:

```javascript
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
```

- [ ] **Step 2: Update section comment header**

Update the section list at the top of bridge.js to reflect new sections:

```javascript
/**
 * ACE Bridge — client-side utilities for the coding page.
 *
 * Sections:
 *  1. Toast notifications
 *  2. Sentence navigation (↑/↓ focus)
 *  3. Group collapse / expand
 *  4. Keymap (dynamic keycap assignment)
 *  5. Apply code (sentence-based + custom selection)
 *  6. Keyboard shortcuts (text panel)
 *  7. Navigation (prev/next source)
 *  8. Source grid overlay
 *  9. Cheat sheet overlay
 * 10. Resize handle
 * 11. Dialog close cleanup
 * 12. HTMX integration (configRequest, afterSwap, afterRequest)
 * 13. Code management helpers
 * 14. Code menu dropdown (with shortcut hints)
 * 15. Code search / filter / create / group
 * 16. Sortable.js drag-and-drop
 * 17. Sidebar keyboard navigation (ARIA treeview)
 * 18. Focus restoration across HTMX swaps
 * 19. DOMContentLoaded init
 */
```

- [ ] **Step 3: Remove dead code**

Remove any remaining references to:
- `#view-groups` (replaced by `#code-tree`)
- `.ace-code-group` class (replaced by `[role="group"]` + `.ace-code-group-header`)
- `aceStartAddGroup` (replaced by `/prefix` search)
- `ace-code-row--hidden` class (replaced by `style.display = "none"` during filtering)
- `#add-group-row` (removed from template)

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass.

- [ ] **Step 5: Verify complete keyboard flow in browser**

Full walkthrough:
1. Page loads → text panel focused → keycap shortcuts work
2. Press `/` → search bar focused → type "bel" → "Belonging" filtered with highlight
3. Clear → type "NewCode" → green prompt → Enter → code created
4. Press Escape → text panel
5. Press Tab → search bar → Tab → code tree (first item focused)
6. ↑/↓ navigate → Enter applies code → flash confirms → stay in tree
7. F2 → rename inline → Enter saves → focus returns to row
8. Alt+Shift+↓ → reorder → dashed outline
9. Alt+→ on ungrouped → moves into group
10. Alt+← → moves back to ungrouped
11. Type `/NewGroup` in search → Enter → group created
12. Right-click code → menu shows shortcut hints
13. Delete → red confirm → Delete again → deleted → focus moves to next
14. Escape → text panel → keycap shortcuts work again

- [ ] **Step 6: Commit**

```bash
git add src/ace/static/js/bridge.js src/ace/static/css/coding.css src/ace/templates/coding.html
git commit -m "feat: complete keyboard-centric sidebar with ARIA treeview navigation"
```
