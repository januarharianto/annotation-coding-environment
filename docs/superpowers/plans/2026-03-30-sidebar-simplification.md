# Sidebar Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-tab code sidebar with a single compact collapsible tree view, removing ~140 lines and adding ~45 lines (net -95 lines).

**Architecture:** Delete tab switching infrastructure (JS builders, CSS, template tabs, Recent SQL query). Keep the server-rendered Groups view as the sole view. Add group collapse/expand with state persistence across OOB swaps. Update keycap and search selectors from `.ace-sidebar-view--active` to `#view-groups`.

**Tech Stack:** Jinja2 templates, vanilla JS, CSS, Python (FastAPI)

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `src/ace/templates/coding.html` | Sidebar template — remove tabs, simplify to single view | Modify |
| `src/ace/static/css/coding.css` | Sidebar styles — remove tab CSS, add compact tree styles | Modify |
| `src/ace/static/js/bridge.js` | Delete tab JS, add collapse handler, update selectors | Modify |
| `src/ace/routes/pages.py` | Remove `recent_code_ids` query + context key | Modify |

---

### Task 1: Delete tab infrastructure (template + CSS + Python)

Remove tab buttons, extra view containers, tab CSS, Recent SQL query. Keep `#view-groups` as the sole view but remove the `ace-sidebar-view` wrapper classes.

**Files:**
- Modify: `src/ace/templates/coding.html`
- Modify: `src/ace/static/css/coding.css`
- Modify: `src/ace/routes/pages.py`

- [ ] **Step 1: Simplify the template sidebar block**

In `src/ace/templates/coding.html`, replace the `{% block code_sidebar %}` content (lines 82–126) with:

```html
    {% block code_sidebar %}
    <div id="code-sidebar" class="ace-sidebar">
      <div class="ace-sidebar-toolbar">
        <input type="text" class="ace-sidebar-search" placeholder="Search or create code…"
               id="code-search-input" autocomplete="off">
      </div>
      <div id="view-groups" class="ace-sidebar-codes">
        {% for group_name, group_codes in grouped_codes %}
        <div class="ace-code-group" data-group="{{ group_name }}">
          <div class="ace-code-group-header" data-group="{{ group_name }}">&#9662; {{ group_name }}</div>
          {% for code in group_codes %}
          <div class="ace-code-row" data-code-id="{{ code['id'] }}">
            <span class="ace-code-dot" style="background: {{ code['colour'] }};"></span>
            <span class="ace-code-name">{{ code['name'] }}</span>
            <span class="ace-keycap"></span>
          </div>
          {% endfor %}
        </div>
        {% endfor %}
        {% if ungrouped_codes %}
        <div class="ace-code-group" data-group="">
          <div class="ace-code-group-header" data-group="">&#9662; Ungrouped</div>
          {% for code in ungrouped_codes %}
          <div class="ace-code-row" data-code-id="{{ code['id'] }}">
            <span class="ace-code-dot" style="background: {{ code['colour'] }};"></span>
            <span class="ace-code-name">{{ code['name'] }}</span>
            <span class="ace-keycap"></span>
          </div>
          {% endfor %}
        </div>
        {% endif %}
        {% if not codes %}
        <div class="ace-sidebar-empty">No codes yet. Use management mode to add codes.</div>
        {% endif %}
        <div class="ace-add-group" id="add-group-row" onclick="aceStartAddGroup(this)">+ New group</div>
      </div>
    </div>
    {% endblock %}
```

Key changes from current:
- Removed `<div class="ace-sidebar-tabs">` with 3 buttons
- Removed `<div class="ace-sidebar-view" id="view-recent"></div>`
- Removed `<div class="ace-sidebar-view" id="view-all"></div>`
- Changed `<div class="ace-sidebar-view ace-sidebar-view--active" id="view-groups">` to `<div id="view-groups" class="ace-sidebar-codes">`
- Group headers: removed `(count)`, added `data-group` attribute, kept as slim text
- Codes: indented via CSS (not inline padding)

- [ ] **Step 2: Remove `__aceRecentCodeIds` from scripts block**

In `src/ace/templates/coding.html`, in the `{% block scripts %}` section (around line 219), delete:
```javascript
  window.__aceRecentCodeIds = {{ recent_code_ids | tojson }};
```

- [ ] **Step 3: Update CSS — remove tab styles, add tree styles**

In `src/ace/static/css/coding.css`:

**3a. Delete tab and view CSS** — remove lines 149–188 (everything from `.ace-sidebar-tabs` through `.ace-sidebar-view--active`).

**3b. Replace group header styles** — replace the `.ace-code-group-header` rules (lines 190–203) with compact tree divider styles:

```css
.ace-code-group-header {
  padding: 3px 8px;
  font-size: var(--ace-font-size-2xs);
  color: var(--ace-text-muted);
  cursor: pointer;
  letter-spacing: 0.3px;
  user-select: none;
}

.ace-code-group-header:first-child {
  margin-top: 0;
}
```

**3c. Add collapsed state and indent** — insert after the group header rules:

```css
.ace-code-group--collapsed .ace-code-row {
  display: none;
}

.ace-sidebar-codes {
  flex: 1;
  overflow-y: auto;
  padding: var(--ace-space-1) 0;
}
```

**3d. Add indent to code rows** — find the `.ace-code-row` rule (around line 210) and change the padding to add left indent:

Change:
```css
padding: 3px 10px;
```
To:
```css
padding: 3px 10px 3px 20px;
```

- [ ] **Step 4: Remove recent_code_ids from pages.py**

In `src/ace/routes/pages.py`, delete the recent codes SQL query (lines 133–143):
```python
    # --- New: recent codes (most recently used by this coder) ---
    recent_rows = conn.execute(
        "SELECT code_id, MAX(created_at) AS last_used "
        "FROM annotation "
        "WHERE coder_id = ? AND deleted_at IS NULL "
        "GROUP BY code_id "
        "ORDER BY last_used DESC "
        "LIMIT 20",
        (coder_id,),
    ).fetchall()
    recent_code_ids = [r["code_id"] for r in recent_rows]
```

And remove `"recent_code_ids": recent_code_ids,` from the return dict (line 196).

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: All 242 tests PASS (template changes don't break server-side tests; the SQL query removal is safe since it's only consumed by the template)

- [ ] **Step 6: Do NOT commit yet** — JS still queries `.ace-sidebar-view--active` which was removed. Task 2 updates the selectors. All 3 tasks must be committed together.

---

### Task 2: Delete tab JS + update selectors

Remove all tab-related JS functions and update the 3 selectors that used `.ace-sidebar-view--active` to use `#view-groups`.

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Delete section 3 (tab management)**

Delete the entire section 3 block (lines 82–156) — everything from `/* 3. Tab management */` through `_escHtml()`. This removes:
- `aceSwitchTab()`
- `_buildTabContent()`
- `_buildRecentTab()`
- `_buildAllTab()`
- `_buildCodeRowHtml()`
- `_escHtml()`

- [ ] **Step 2: Delete `_trackRecent()` and its call sites**

Delete the function definition (lines 265–272):
```javascript
  function _trackRecent(codeId) {
    ...
  }
```

Delete the two call sites:
- Line 218 in `_applyCodeToSentence`: delete `_trackRecent(codeId);`
- Line 241 in `_applyCodeToSelection`: delete `_trackRecent(codeId);`

- [ ] **Step 3: Update `_updateKeycaps()` selector**

In `_updateKeycaps()` (section 4), change line 165 from:
```javascript
    var view = document.querySelector(".ace-sidebar-view--active");
    if (!view) return;
    var rows = view.querySelectorAll(".ace-code-row");
```
To:
```javascript
    var view = document.getElementById("view-groups");
    if (!view) return;
    var rows = view.querySelectorAll(".ace-code-row:not(.ace-code-row--hidden)");
```

- [ ] **Step 4: Update search filter selector**

In the search filter input handler (section 16, around line 1218), change:
```javascript
    var view = document.querySelector(".ace-sidebar-view--active");
```
To:
```javascript
    var view = document.getElementById("view-groups");
```

Also update the row visibility check (line 1226) to use the hidden class instead of inline style:
```javascript
      row.style.display = match ? "" : "none";
```
Change to:
```javascript
      if (match) {
        row.classList.remove("ace-code-row--hidden");
      } else {
        row.classList.add("ace-code-row--hidden");
      }
```

And update the group visibility check (line 1232) to use the class:
```javascript
      var visibleInGroup = group.querySelectorAll('.ace-code-row:not([style*="display: none"])').length;
```
Change to:
```javascript
      var visibleInGroup = group.querySelectorAll(".ace-code-row:not(.ace-code-row--hidden)").length;
```

- [ ] **Step 5: Update Enter-to-create selector**

In the Enter keydown handler (section 16, around line 1252), change:
```javascript
    var view = document.querySelector(".ace-sidebar-view--active");
    var rows = view ? view.querySelectorAll('.ace-code-row:not([style*="display: none"])') : [];
```
To:
```javascript
    var view = document.getElementById("view-groups");
    var rows = view ? view.querySelectorAll(".ace-code-row:not(.ace-code-row--hidden)") : [];
```

- [ ] **Step 6: Remove tab rebuilds from afterSettle**

In the `htmx:afterSettle` handler (around line 759–764), remove the `_buildTabContent` calls. Change:
```javascript
    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      _buildTabContent("recent");
      _buildTabContent("all");
      _updateKeycaps();
      if (!_isDragging) _initSortable();
    }
```
To:
```javascript
    if (target.id === "code-sidebar" || target.id === "coding-workspace") {
      if (!_isDragging) _initSortable();
      _restoreCollapseState();
      _updateKeycaps();
    }
```

(`_restoreCollapseState` is defined in Task 3.)

- [ ] **Step 7: Remove tab rebuilds from `_refreshSidebar`**

In `_refreshSidebar()` (around line 884), change the `.then()` callback:
```javascript
    }).then(function () {
      _buildTabContent("recent");
      _buildTabContent("all");
      _updateKeycaps();
      _initSortable();
    });
```
To:
```javascript
    }).then(function () {
      _initSortable();
      _restoreCollapseState();
      _updateKeycaps();
    });
```

- [ ] **Step 8: Remove tab rebuilds from DOMContentLoaded**

In the DOMContentLoaded handler (around line 1451), remove:
```javascript
    _buildTabContent("recent");
    _buildTabContent("all");
```

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest`
Expected: All 242 tests PASS

- [ ] **Step 10: Do NOT commit yet** — Task 3 adds `_restoreCollapseState()` which is referenced in Steps 6 and 7. Commit both tasks together.

---

### Task 3: Add group collapse/expand

Add the collapse click handler, state persistence across OOB swaps, and search auto-expand.

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add collapse state variable and handlers**

Insert a new section before the DOMContentLoaded init block. Use the next available section number (section 3 was deleted, reuse it or use 20 — use 3 since it's now empty):

```javascript
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
```

- [ ] **Step 2: Update search to auto-expand collapsed groups and restore on clear**

In the search filter input handler (section 16), after the row filtering loop and before `_updateKeycaps()`, add logic to auto-expand groups that have matches and collapse them back when search is cleared:

Replace the entire input handler with:
```javascript
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
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All 242 tests PASS

- [ ] **Step 4: Commit all 3 tasks together**

```bash
git add src/ace/templates/coding.html src/ace/static/css/coding.css src/ace/routes/pages.py src/ace/static/js/bridge.js
git commit -m "feat: simplify sidebar — single collapsible tree view, remove tabs"
```

---

### Task 4: Visual verification

**Files:** Any files from Tasks 1–3 that need adjustment.

- [ ] **Step 1: Start the dev server**

Run: `uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 8080 --reload --reload-dir src/ace`

- [ ] **Step 2: Verify sidebar**

Open `http://127.0.0.1:8080/code` in a browser. Test:

1. **No tabs visible** — sidebar shows search input, then groups, no tab bar
2. **Compact tree style** — group headers are slim uppercase dividers, codes indented
3. **Collapse/expand** — click a group header → codes hide, triangle rotates to ▸. Click again → codes show, triangle back to ▾
4. **Keycaps reassign** — collapse a group → keycaps on remaining visible codes shift up (e.g., if group 1 had keys 1-3, collapsing it makes group 2's first code become key 1)
5. **Search filter** — type in search box → rows filter, collapsed groups auto-expand to show matches
6. **Search clear** — press Escape → all rows restored, collapsed groups return to their collapsed state
7. **Enter to create** — type a non-existing name, press Enter → new code created
8. **Drag-and-drop** — drag a code between groups → reorder works
9. **Right-click menu** — right-click a code → context menu works (rename, colour, delete, move to group)
10. **OOB swap persistence** — apply a code (which triggers sidebar OOB swap) → collapsed groups stay collapsed
11. **Hotkeys** — press 1-9/a-z → correct code applied based on visible keycaps

- [ ] **Step 3: Fix any visual issues found**

Common issues:
- Codes not indented → check CSS `padding-left: 20px` on `.ace-code-row`
- Collapse not working → check click handler delegation, `data-group` attribute
- Keycaps wrong after collapse → check `_updateKeycaps` uses `:not(.ace-code-row--hidden)` selector
- Search broken → check selector changed from `.ace-sidebar-view--active` to `#view-groups`
- SortableJS broken → check `#view-groups` ID preserved, `_initSortable` still finds `.ace-code-group` containers

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: visual adjustments for sidebar simplification"
```

(Skip this commit if no fixes needed.)
