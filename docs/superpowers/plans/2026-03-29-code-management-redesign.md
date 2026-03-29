# Code Management Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove management mode (gear button) and replace with inline direct manipulation — right-click context menu, double-click rename, click-dot colour picker, drag-and-drop reorder, keyboard shortcuts. Net reduction of ~80 lines.

**Architecture:** All code management moves client-side. The 4 dialog endpoints are eliminated. The existing PUT/DELETE/POST endpoints remain. The JS `aceCodeMenu` is rewritten to call inline handlers instead of fetching dialog HTML. SortableJS (already vendored) handles drag-and-drop with `delay: 200`.

**Tech Stack:** Vanilla JS, SortableJS, CSS, FastAPI (endpoint removal only)

---

## File Structure

**Modified files:**
- `src/ace/static/js/bridge.js` — rewrite code menu, add inline rename/colour/delete/drag
- `src/ace/static/css/coding.css` — remove management mode CSS, add contenteditable + colour popover + delete confirmation styles
- `src/ace/templates/coding.html` — remove gear/⋯ buttons/manage-create, wrap groups in containers
- `src/ace/routes/api.py` — remove 4 dialog endpoints, add validation to update route

**No new files.**

---

### Task 1: Remove management mode (template + CSS + JS)

Remove the gear button, ⋯ menu buttons, manage-create input, and all management mode CSS/JS.

**Files:**
- Modify: `src/ace/templates/coding.html`
- Modify: `src/ace/static/css/coding.css`
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Remove management mode elements from template**

In `src/ace/templates/coding.html`, remove:
- The gear button: `<button class="ace-btn-icon ace-manage-toggle" ...>⚙</button>`
- Both `<button class="ace-code-menu-btn" ...>…</button>` (in grouped and ungrouped code loops)
- The `<div class="ace-manage-create">...</div>` block

- [ ] **Step 2: Remove management mode CSS**

In `src/ace/static/css/coding.css`, remove these rules (between the `.ace-sidebar-search:focus` rule and the `/* ---- Touch fallback ---- */` comment):
- `.ace-manage-toggle`
- `.ace-sidebar--manage .ace-code-row`
- `.ace-code-menu-btn` and all its variants
- `.ace-sidebar--manage .ace-code-menu-btn`
- `.ace-sidebar--manage .ace-code-row:hover .ace-code-menu-btn`
- `.ace-sidebar--manage .ace-keycap`
- `.ace-manage-create` and all its variants

Keep `.ace-sidebar-toolbar` and `.ace-sidebar-search` (still used by search input).

- [ ] **Step 3: Remove management mode JS**

In `src/ace/static/js/bridge.js`, remove:
- The `aceToggleManageMode` function and the management mode create-input keydown handler (the section between `/* Management mode toggle */` and `/* 14. Add group */`)

- [ ] **Step 4: Update touch fallback CSS**

Remove the `.ace-code-menu-btn` rule from the `@media (hover: none)` block.

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "refactor: remove management mode (gear button, ⋯ menus, manage-create input)"
```

---

### Task 2: Wrap groups in containers for drag-and-drop

Restructure the template so each group's codes are inside a container `<div>` with `data-group`.

**Files:**
- Modify: `src/ace/templates/coding.html`

- [ ] **Step 1: Wrap grouped codes in containers**

Replace the grouped codes loop in the `view-groups` div:

```html
{% for group_name, group_codes in grouped_codes %}
<div class="ace-code-group" data-group="{{ group_name }}">
  <div class="ace-code-group-header">&#9662; {{ group_name }} ({{ group_codes | length }})</div>
  {% for code in group_codes %}
  <div class="ace-code-row" data-code-id="{{ code['id'] }}">
    <span class="ace-code-dot" style="background: {{ code['colour'] }};"></span>
    <span class="ace-code-name">{{ code['name'] }}</span>
    <span class="ace-keycap"></span>
  </div>
  {% endfor %}
</div>
{% endfor %}
```

- [ ] **Step 2: Wrap ungrouped codes in a container with `data-group=""`**

```html
{% if ungrouped_codes %}
<div class="ace-code-group" data-group="">
  <div class="ace-code-group-header">&#9662; Ungrouped ({{ ungrouped_codes | length }})</div>
  {% for code in ungrouped_codes %}
  <div class="ace-code-row" data-code-id="{{ code['id'] }}">
    <span class="ace-code-dot" style="background: {{ code['colour'] }};"></span>
    <span class="ace-code-name">{{ code['name'] }}</span>
    <span class="ace-keycap"></span>
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 3: Update the search filter JS**

The search filter in bridge.js walks `.ace-code-group-header` siblings. With nesting, update it to walk within `.ace-code-group` containers. In the `input` event handler for `code-search-input`, change the group header visibility logic:

```javascript
// Hide group containers if all their code rows are hidden
var groups = view.querySelectorAll(".ace-code-group");
groups.forEach(function (group) {
  var visibleInGroup = group.querySelectorAll('.ace-code-row:not([style*="display: none"])').length;
  group.style.display = visibleInGroup > 0 ? "" : "none";
});
```

Replace the existing header-walking logic with this.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "refactor: wrap code groups in container divs for drag-and-drop"
```

---

### Task 3: Right-click context menu

Rewrite `aceCodeMenu` to trigger via `contextmenu` event and call inline handlers instead of dialog endpoints.

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add `_isTyping` guard for contenteditable**

Update `_isTyping()`:

```javascript
function _isTyping() {
  var el = document.activeElement;
  if (!el) return false;
  var tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}
```

- [ ] **Step 2: Add `_menuOpen` flag and update keydown guard**

Add near the top of the IIFE:

```javascript
var _menuOpen = false;
var _lastSelectedCodeId = null;
```

In the main `keydown` handler, add after the `_isTyping()` check:

```javascript
if (_menuOpen) return;
```

- [ ] **Step 3: Rewrite `aceCodeMenu` for right-click**

Replace the existing `aceCodeMenu`, `_closeCodeMenu`, `_onCodeMenuOutsideClick`, `_onCodeMenuEscape` with:

```javascript
var _activeCodeMenu = null;

function _closeCodeMenu() {
  if (_activeCodeMenu) {
    _activeCodeMenu.remove();
    _activeCodeMenu = null;
    _menuOpen = false;
  }
  document.removeEventListener("click", _onCodeMenuOutsideClick);
  document.removeEventListener("keydown", _onCodeMenuEscape);
}

function _openCodeMenu(x, y, codeId) {
  _closeCodeMenu();
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

  // Add "Move to Group" submenu
  var groups = _getGroupNames();
  if (groups.length > 0) {
    var moveItem = document.createElement("div");
    moveItem.className = "ace-code-menu-item ace-code-menu-sub";
    moveItem.textContent = "Move to Group ▸";
    var sub = document.createElement("div");
    sub.className = "ace-code-submenu";

    // Ungrouped option
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
    // Insert before Move Up
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

  // Position: ensure within viewport
  var mw = menu.offsetWidth, mh = menu.offsetHeight;
  menu.style.top = (y + mh > window.innerHeight ? Math.max(0, y - mh) : y) + "px";
  menu.style.left = (x + mw > window.innerWidth ? Math.max(0, x - mw) : x) + "px";

  setTimeout(function () {
    document.addEventListener("click", _onCodeMenuOutsideClick);
    document.addEventListener("keydown", _onCodeMenuEscape);
  }, 0);
}

function _onCodeMenuOutsideClick(e) {
  if (_activeCodeMenu && !_activeCodeMenu.contains(e.target)) _closeCodeMenu();
}

function _onCodeMenuEscape(e) {
  if (e.key === "Escape") _closeCodeMenu();
}

function _getGroupNames() {
  var codes = window.__aceCodes || [];
  var seen = {};
  var result = [];
  codes.forEach(function (c) {
    if (c.group_name && !seen[c.group_name]) {
      seen[c.group_name] = true;
      result.push(c.group_name);
    }
  });
  return result;
}
```

- [ ] **Step 4: Add contextmenu event delegation**

```javascript
// Right-click context menu on code rows
document.addEventListener("contextmenu", function (e) {
  var row = e.target.closest(".ace-code-row");
  if (!row) return;
  e.preventDefault();
  var codeId = row.getAttribute("data-code-id");
  if (codeId) _openCodeMenu(e.clientX, e.clientY, codeId);
});
```

- [ ] **Step 5: Add submenu CSS**

In `src/ace/static/css/coding.css`, add after the `.ace-code-menu-item--danger` rule:

```css
.ace-code-menu-sub {
  position: relative;
  cursor: default;
}

.ace-code-submenu {
  display: none;
  position: absolute;
  left: 100%;
  top: 0;
  background: var(--ace-bg);
  border: 1px solid var(--ace-border);
  box-shadow: var(--ace-shadow);
  min-width: 120px;
}

.ace-code-menu-sub:hover .ace-code-submenu {
  display: block;
}
```

- [ ] **Step 6: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "feat: right-click context menu replaces management mode menu buttons"
```

---

### Task 4: Double-click inline rename

**Files:**
- Modify: `src/ace/static/js/bridge.js`
- Modify: `src/ace/static/css/coding.css`

- [ ] **Step 1: Add `_startInlineRename` function**

```javascript
function _startInlineRename(codeId) {
  var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
  if (!row) return;
  var nameEl = row.querySelector(".ace-code-name");
  if (!nameEl) return;

  var original = nameEl.textContent;
  nameEl.contentEditable = "true";
  nameEl.focus();

  // Select all text
  var range = document.createRange();
  range.selectNodeContents(nameEl);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);

  function save() {
    var newName = nameEl.textContent.trim();
    nameEl.contentEditable = "false";
    if (!newName || newName === original) {
      nameEl.textContent = original;
      document.getElementById("text-panel").focus();
      return;
    }
    fetch("/api/codes/" + codeId, {
      method: "PUT",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "name=" + encodeURIComponent(newName) + "&current_index=" + window.__aceCurrentIndex,
    }).then(function (r) {
      if (!r.ok) { nameEl.textContent = original; window.aceToast("Rename failed"); }
      else { return r.text(); }
    }).then(function (html) {
      if (html) {
        var sidebar = document.getElementById("code-sidebar");
        if (sidebar) sidebar.outerHTML = html;
        _buildTabContent("recent");
        _buildTabContent("all");
        _updateKeycaps();
      }
    });
    document.getElementById("text-panel").focus();
  }

  nameEl.addEventListener("keydown", function handler(e) {
    if (e.key === "Enter") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); save(); }
    if (e.key === "Escape") { e.preventDefault(); nameEl.removeEventListener("keydown", handler); nameEl.textContent = original; nameEl.contentEditable = "false"; document.getElementById("text-panel").focus(); }
  });

  nameEl.addEventListener("blur", function blurHandler() {
    nameEl.removeEventListener("blur", blurHandler);
    if (nameEl.contentEditable === "true") save();
  });

  // Paste plain text only
  nameEl.addEventListener("paste", function pasteHandler(e) {
    e.preventDefault();
    var text = (e.clipboardData || window.clipboardData).getData("text/plain");
    document.execCommand("insertText", false, text.replace(/\n/g, " "));
  });
}
```

- [ ] **Step 2: Add double-click event delegation**

```javascript
document.addEventListener("dblclick", function (e) {
  var nameEl = e.target.closest(".ace-code-name");
  if (!nameEl) return;
  var row = nameEl.closest(".ace-code-row");
  if (!row) return;
  var codeId = row.getAttribute("data-code-id");
  if (codeId) _startInlineRename(codeId);
});
```

- [ ] **Step 3: Add F2 shortcut**

In the main keydown handler, after the ArrowRight handler:

```javascript
if (key === "F2" && _lastSelectedCodeId) {
  e.preventDefault();
  _startInlineRename(_lastSelectedCodeId);
  return;
}
```

- [ ] **Step 4: Add contenteditable CSS**

```css
.ace-code-name[contenteditable="true"] {
  outline: 1px solid var(--ace-focus);
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  padding: 0 2px;
}
```

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "feat: double-click inline rename with contenteditable"
```

---

### Task 5: Click-dot colour popover

**Files:**
- Modify: `src/ace/static/js/bridge.js`
- Modify: `src/ace/static/css/coding.css`

- [ ] **Step 1: Add colour palette constant and popover function**

```javascript
var _COLOUR_PALETTE = ["#A91818","#557FE6","#6DA918","#E655D4","#18A991","#E6A455","#3C18A9","#5BE655","#A91848","#55B0E6","#9DA918","#C855E6","#18A960","#E67355","#1824A9","#8CE655","#A91879","#55E1E6","#A98418","#9755E6","#18A930","#E65567","#1855A9","#BCE655","#A918A9","#55E6BB","#A95418","#6755E6","#30A918","#E65598","#1885A9","#E6E055","#7818A9","#55E68B","#A92318","#5574E6"];

var _activeColourPopover = null;

function _openColourPopover(codeId) {
  _closeColourPopover();
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
      _closeColourPopover();
      fetch("/api/codes/" + codeId, {
        method: "PUT",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "colour=" + encodeURIComponent(hex) + "&current_index=" + window.__aceCurrentIndex,
      }).then(function (r) { return r.text(); })
        .then(function (html) {
          if (!html) return;
          var sidebar = document.getElementById("code-sidebar");
          if (sidebar) sidebar.outerHTML = html;
          _buildTabContent("recent");
          _buildTabContent("all");
          _updateKeycaps();
        });
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

function _closeColourPopover() {
  if (_activeColourPopover) {
    _activeColourPopover.remove();
    _activeColourPopover = null;
  }
  document.removeEventListener("click", _onColourOutsideClick);
  document.removeEventListener("keydown", _onColourEscape);
}

function _onColourOutsideClick(e) {
  if (_activeColourPopover && !_activeColourPopover.contains(e.target)) _closeColourPopover();
}

function _onColourEscape(e) {
  if (e.key === "Escape") _closeColourPopover();
}
```

- [ ] **Step 2: Add click-on-dot delegation**

```javascript
document.addEventListener("click", function (e) {
  var dot = e.target.closest(".ace-code-dot");
  if (!dot) return;
  var row = dot.closest(".ace-code-row");
  if (!row) return;
  e.stopPropagation();
  var codeId = row.getAttribute("data-code-id");
  if (codeId) _openColourPopover(codeId);
});
```

- [ ] **Step 3: Add colour popover CSS**

```css
.ace-colour-popover {
  position: fixed;
  z-index: 100;
  background: var(--ace-bg);
  border: 1px solid var(--ace-border);
  box-shadow: var(--ace-shadow);
  padding: 4px;
  display: grid;
  grid-template-columns: repeat(6, 28px);
  gap: 2px;
  border-radius: var(--ace-radius);
}

.ace-colour-swatch {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 2px;
  cursor: pointer;
  padding: 0;
}

.ace-colour-swatch:hover {
  outline: 2px solid var(--ace-text);
  outline-offset: -1px;
}
```

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "feat: click-dot colour swatch popover (client-side, no dialog endpoint)"
```

---

### Task 6: Delete with double-press confirmation + Move Up/Down

**Files:**
- Modify: `src/ace/static/js/bridge.js`
- Modify: `src/ace/static/css/coding.css`

- [ ] **Step 1: Add delete confirmation and move functions**

```javascript
var _deleteTarget = null;
var _deleteTimer = null;

function _startDeleteConfirm(codeId) {
  // Clear previous
  if (_deleteTimer) { clearTimeout(_deleteTimer); _clearDeleteConfirm(); }

  var row = document.querySelector('.ace-code-row[data-code-id="' + codeId + '"]');
  if (!row) return;

  row.classList.add("ace-code-row--confirm-delete");
  _deleteTarget = codeId;

  _deleteTimer = setTimeout(function () {
    _clearDeleteConfirm();
  }, 2000);
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
  fetch("/api/codes/" + codeId + "?current_index=" + window.__aceCurrentIndex, {
    method: "DELETE",
  }).then(function (r) { return r.text(); })
    .then(function (html) {
      if (!html) return;
      var sidebar = document.getElementById("code-sidebar");
      if (sidebar) sidebar.outerHTML = html;
      _buildTabContent("recent");
      _buildTabContent("all");
      _updateKeycaps();
    });
}

function _moveCode(codeId, direction) {
  var codes = window.__aceCodes || [];
  var ids = codes.map(function (c) { return c.id; });
  var idx = ids.indexOf(codeId);
  if (idx < 0) return;
  var newIdx = idx + direction;
  if (newIdx < 0 || newIdx >= ids.length) return;
  // Swap
  ids[idx] = ids[newIdx];
  ids[newIdx] = codeId;
  fetch("/api/codes/reorder", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "code_ids=" + encodeURIComponent(JSON.stringify(ids)) + "&current_index=" + window.__aceCurrentIndex,
  }).then(function (r) { return r.text(); })
    .then(function (html) {
      if (!html) return;
      var sidebar = document.getElementById("code-sidebar");
      if (sidebar) sidebar.outerHTML = html;
      _buildTabContent("recent");
      _buildTabContent("all");
      _updateKeycaps();
    });
}

function _moveToGroup(codeId, groupName) {
  fetch("/api/codes/" + codeId, {
    method: "PUT",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "group_name=" + encodeURIComponent(groupName) + "&current_index=" + window.__aceCurrentIndex,
  }).then(function (r) { return r.text(); })
    .then(function (html) {
      if (!html) return;
      var sidebar = document.getElementById("code-sidebar");
      if (sidebar) sidebar.outerHTML = html;
      _buildTabContent("recent");
      _buildTabContent("all");
      _updateKeycaps();
    });
}
```

- [ ] **Step 2: Add Delete key handler**

In the main keydown handler, after the F2 handler:

```javascript
if ((key === "Delete" || key === "Backspace") && _lastSelectedCodeId && !shift && !ctrl) {
  e.preventDefault();
  if (_deleteTarget === _lastSelectedCodeId) {
    _executeDelete(_lastSelectedCodeId);
  } else {
    _startDeleteConfirm(_lastSelectedCodeId);
  }
  return;
}
```

- [ ] **Step 3: Set `_lastSelectedCodeId` on right-click**

Already done in `_openCodeMenu` (Step 3 of Task 3).

- [ ] **Step 4: Add delete confirmation CSS**

```css
.ace-code-row--confirm-delete {
  background: rgba(198, 40, 40, 0.08);
}

.ace-code-row--confirm-delete::after {
  content: "Delete?";
  font-size: var(--ace-font-size-2xs);
  color: var(--ace-danger);
  position: absolute;
  right: var(--ace-space-2);
  top: 50%;
  transform: translateY(-50%);
}

.ace-code-row {
  position: relative;
}
```

Note: `.ace-code-row` already exists — just add `position: relative` to the existing rule.

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "feat: double-press Delete confirmation + Move Up/Down + Move to Group"
```

---

### Task 7: Drag-and-drop with SortableJS

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add SortableJS initialisation**

```javascript
var _sortableInstances = [];
var _isDragging = false;

function _initSortable() {
  // Destroy existing instances
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

        // If group changed, update group_name
        if (newGroup !== oldGroup && codeId) {
          fetch("/api/codes/" + codeId, {
            method: "PUT",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: "group_name=" + encodeURIComponent(newGroup || "") + "&current_index=" + window.__aceCurrentIndex,
          });
        }

        // Collect new order across all groups
        var allRows = document.querySelectorAll("#view-groups .ace-code-row");
        var ids = [];
        allRows.forEach(function (row) {
          var id = row.getAttribute("data-code-id");
          if (id) ids.push(id);
        });

        fetch("/api/codes/reorder", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: "code_ids=" + encodeURIComponent(JSON.stringify(ids)) + "&current_index=" + window.__aceCurrentIndex,
        });
      },
    });
    _sortableInstances.push(instance);
  });
}
```

- [ ] **Step 2: Init on DOMContentLoaded and afterSettle**

Add `_initSortable()` to the DOMContentLoaded handler.

In the `htmx:afterSettle` handler, add:

```javascript
if (target.id === "code-sidebar" || target.id === "coding-workspace") {
  if (!_isDragging) _initSortable();
}
```

- [ ] **Step 3: Add ghost class CSS**

```css
.ace-code-row--ghost {
  opacity: 0.4;
}
```

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "feat: drag-and-drop reorder via SortableJS with cross-group support"
```

---

### Task 8: Remove dialog endpoints + add server-side validation

**Files:**
- Modify: `src/ace/routes/api.py`

- [ ] **Step 1: Remove 4 dialog endpoints**

Delete the entire "Dialog endpoints" section from `api.py`:
- `rename-dialog` endpoint (~28 lines)
- `colour-dialog` endpoint (~27 lines)
- `delete-dialog` endpoint (~45 lines)
- `move-dialog` endpoint (~70 lines)

- [ ] **Step 2: Add validation to update_code_route**

In the `update_code_route` function, add try/except around `update_code()` and empty name validation:

```python
    conn = _open_project_db(request)
    try:
        kwargs: dict = {}
        if name is not None:
            name = name.strip()
            if not name:
                return _oob_toast("Code name cannot be empty.")
            kwargs["name"] = name
        if colour is not None:
            kwargs["colour"] = colour
        if group_name is not None:
            kwargs["group_name"] = group_name

        try:
            update_code(conn, code_id, **kwargs)
        except Exception:
            return _oob_toast("A code with that name already exists.")

        content = _render_sidebar_and_text(request, conn, coder_id, current_index)
        return HTMLResponse(content)
    finally:
        conn.close()
```

- [ ] **Step 3: Run tests and commit**

```bash
uv run pytest --tb=short -q
git add -u
git commit -m "refactor: remove 4 dialog endpoints, add rename validation"
```

---

### Task 9: Update cheat sheet + final cleanup

**Files:**
- Modify: `src/ace/static/js/bridge.js`

- [ ] **Step 1: Add F2 and Delete to cheat sheet**

In `_toggleCheatSheet()`, add after the existing shortcut rows:

```javascript
_shortcutRow("F2", "Rename selected code") +
_shortcutRow("Delete", "Delete selected code (press twice)") +
```

- [ ] **Step 2: Remove old `window.aceCodeMenu` global export**

The function is no longer called from template `onclick` attributes. Change from `window.aceCodeMenu` to just `_openCodeMenu` (already done in Task 3).

- [ ] **Step 3: Run all tests**

```bash
uv run pytest -v
```

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "feat: update cheat sheet with code management shortcuts, final cleanup"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| Remove gear button | Task 1 |
| Remove ⋯ buttons | Task 1 |
| Remove manage-create input | Task 1 |
| Right-click context menu | Task 3 |
| Double-click rename | Task 4 |
| F2 rename shortcut | Task 4 |
| Click-dot colour popover | Task 5 |
| Drag-and-drop reorder | Task 7 |
| Move to Group submenu | Task 3 |
| Move Up/Down | Task 6 |
| Double-press Delete | Task 6 |
| `_isTyping()` guard update | Task 3 |
| Template group containers | Task 2 |
| Remove 4 dialog endpoints | Task 8 |
| Server-side rename validation | Task 8 |
| Cheat sheet update | Task 9 |
| Paste sanitisation | Task 4 |
| contenteditable CSS | Task 4 |

### Placeholder Scan

No TBD, TODO, or "implement later" found.

### Type Consistency

- `_lastSelectedCodeId` — defined in Task 3, used in Tasks 4, 6
- `_menuOpen` — defined in Task 3, checked in Task 3
- `_startInlineRename(codeId)` — defined in Task 4, called from Tasks 3, 4
- `_openColourPopover(codeId)` — defined in Task 5, called from Task 3
- `_startDeleteConfirm(codeId)` — defined in Task 6, called from Tasks 3, 6
- `_moveCode(codeId, direction)` — defined in Task 6, called from Task 3
- `_moveToGroup(codeId, groupName)` — defined in Task 6, called from Task 3
- `_initSortable()` — defined in Task 7, called from Task 7
