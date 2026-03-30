# Sidebar Simplification — Spec

## Goal

Replace the 3-tab code sidebar (Recent / Groups / All) with a single compact tree view with collapsible groups.

## Current State

The sidebar has 3 tabs: Recent (client-rendered from last 20 used codes), Groups (server-rendered, default active), and All (client-rendered alphabetical). Tab switching, building Recent/All content, and tracking recent codes adds ~140 lines of JS/CSS/template/Python. Group headers show a ▾ triangle but collapse is not implemented.

## Design

### Single View — Compact Tree

- **Search/create input** at top (unchanged)
- **Group headers** as slim uppercase dividers (smaller font, `THEMES` not `Themes (3)`) with a collapse triangle (▾ expanded, ▸ collapsed)
- **Codes indented** 20px under their group — dot + name + keycap badge
- **Ungrouped codes** appear under an "Ungrouped" divider (or directly if no groups exist)
- **"+ New group"** row stays at the bottom
- **`#view-groups` ID preserved** on the main container — `_updateKeycaps()`, search filter, and Enter-to-create all query this container

### Collapse/Expand

- Clicking a group header toggles its codes visible/hidden
- Collapsed: child `.ace-code-row` elements get `ace-code-row--hidden` class (`display: none`). The group container itself stays in layout (SortableJS needs it).
- Collapsed header shows ▸ (right-pointing triangle), expanded shows ▾
- After toggling, `_updateKeycaps()` is called to reassign keycaps to visible codes only
- All groups start expanded by default

### Collapse State Persistence

Collapse state is stored in a JS variable (`_collapsedGroups` object keyed by group name). After OOB swaps that replace `#code-sidebar`, the afterSettle handler reapplies collapse state from this variable. State is lost on full page reload (groups re-expand — acceptable).

### Search + Collapse Interaction

- Search auto-expands any collapsed group that contains a matching code
- When search is cleared (Escape or empty input), groups return to their previous collapse state
- This ensures search always finds codes regardless of collapse state

### SortableJS + Collapse

- Collapsed groups keep their container in the DOM layout (only children are hidden)
- Dragging into a collapsed group is not supported (the container has no visible drop zone for children, but the group header is visible for reordering groups themselves)

### Keycap Behaviour

Keycaps are assigned positionally to **visible codes only** — those not hidden by collapse or search filter. `_updateKeycaps()` queries `.ace-code-row:not(.ace-code-row--hidden)` within `#view-groups`. This replaces the current fragile `[style*="display: none"]` inline style checks.

## What Gets Deleted

| Code | Location | ~Lines |
|------|----------|--------|
| Tab buttons HTML | `coding.html` | 5 |
| `#view-recent` and `#view-all` containers | `coding.html` | 2 |
| `aceSwitchTab()` | `bridge.js` section 3 | 18 |
| `_buildTabContent()` | `bridge.js` section 3 | 8 |
| `_buildRecentTab()` | `bridge.js` section 3 | 18 |
| `_buildAllTab()` | `bridge.js` section 3 | 10 |
| `_buildCodeRowHtml()` | `bridge.js` section 3 | 7 |
| `_escHtml()` | `bridge.js` section 3 | 3 |
| `_trackRecent()` + call sites | `bridge.js` section 5 | 12 |
| `window.__aceRecentCodeIds` init | `coding.html` scripts | 1 |
| Recent code SQL query | `pages.py` | 10 |
| `recent_code_ids` context key | `pages.py` | 1 |
| Tab rebuild in afterSettle | `bridge.js` section 12 | 2 |
| Tab rebuild in DOMContentLoaded | `bridge.js` section 17 | 2 |
| Tab rebuild in `_refreshSidebar` | `bridge.js` section 13 | 2 |
| `.ace-sidebar-tabs` CSS | `coding.css` | 30 |
| `.ace-sidebar-view` show/hide CSS | `coding.css` | 10 |
| **Total** | | **~140** |

## What Gets Added

| Code | Location | ~Lines |
|------|----------|--------|
| Group header click handler (toggle collapse) | `bridge.js` | 10 |
| `_collapsedGroups` state variable + restore after swap | `bridge.js` | 10 |
| Search auto-expand + restore on clear | `bridge.js` | 8 |
| CSS: collapsed state, indent, slim dividers | `coding.css` | 15 |
| `_updateKeycaps` selector update (`:not(.ace-code-row--hidden)`) | `bridge.js` | 2 |
| **Total** | | **~45** |

## What Gets Modified

- **`_refreshSidebar()`** — remove `_buildTabContent("recent")` and `_buildTabContent("all")` calls from `.then()` callback. Add `_restoreCollapseState()` call.
- **`_updateKeycaps()`** — change selector from `.ace-sidebar-view--active .ace-code-row` to `#view-groups .ace-code-row:not(.ace-code-row--hidden)`
- **Search filter handler** — change `document.querySelector(".ace-sidebar-view--active")` to `document.getElementById("view-groups")`
- **Enter-to-create handler** — same selector change as search filter
- **afterSettle handler** — remove `_buildTabContent` calls, add `_restoreCollapseState()` call

## What Stays Unchanged

- Search/create input and its filter/create logic (selectors updated, logic unchanged)
- Keycap assignment system (selector updated, logic unchanged)
- Right-click context menu (rename, colour, delete, move to group)
- Double-click rename, click-dot colour picker
- SortableJS drag-and-drop between groups (including `#view-groups .ace-code-row` selector in onEnd)
- "Q" repeat last code
- All server-side code management routes
- OOB swap mechanism for sidebar updates

## Files to Change

| File | Change |
|------|--------|
| `src/ace/templates/coding.html` | Remove tab buttons, remove `#view-recent`/`#view-all` divs, remove `__aceRecentCodeIds`, remove `ace-sidebar-view`/`ace-sidebar-view--active` classes from Groups div (keep `id="view-groups"`) |
| `src/ace/static/css/coding.css` | Remove tab CSS, remove view show/hide CSS, add slim divider style, add indent on code rows, add `.ace-code-row--hidden` and collapsed state styles |
| `src/ace/static/js/bridge.js` | Delete section 3 tab functions, delete `_trackRecent` + calls, add group header click/collapse handler, add `_collapsedGroups` state + restore, update selectors in `_updateKeycaps`/search/create, modify `_refreshSidebar`/afterSettle/DOMContentLoaded |
| `src/ace/routes/pages.py` | Remove `recent_code_ids` SQL query and context key |

## Net Effect

~140 lines deleted, ~45 lines added. **Net ~-95 lines.**
