# Sidebar Simplification — Spec

## Goal

Replace the 3-tab code sidebar (Recent / Groups / All) with a single compact tree view with collapsible groups.

## Current State

The sidebar has 3 tabs: Recent (client-rendered from last 20 used codes), Groups (server-rendered, default active), and All (client-rendered alphabetical). Tab switching, building Recent/All content, and tracking recent codes adds ~135 lines of JS/CSS/template/Python. Group headers show a ▾ triangle but collapse is not implemented.

## Design

### Single View — Compact Tree

- **Search/create input** at top (unchanged)
- **Group headers** as slim uppercase dividers (smaller font, `THEMES` not `Themes (3)`) with a collapse triangle (▾ expanded, ▸ collapsed)
- **Codes indented** 20px under their group — dot + name + keycap badge
- **Ungrouped codes** appear under an "Ungrouped" divider (or directly if no groups exist)
- **"+ New group"** row stays at the bottom

### Collapse/Expand

- Clicking a group header toggles its codes visible/hidden
- Collapsed group header shows ▸ (right-pointing triangle)
- Expanded group header shows ▾ (down-pointing triangle)
- After toggling, `_updateKeycaps()` is called to reassign 1-9/0/a-z to visible codes only
- All groups start expanded by default (no localStorage persistence — YAGNI)

### Keycap Behaviour

Keycaps are assigned positionally to **visible codes only**. Collapsing a group removes its codes from the keycap sequence, and remaining visible codes shift up. This is consistent with how search/filter already works.

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
| Tab rebuild in afterSettle | `bridge.js` section 12 | 4 |
| Tab rebuild in DOMContentLoaded | `bridge.js` section 17 | 3 |
| Tab rebuild in `_refreshSidebar` | `bridge.js` section 13 | 3 |
| `.ace-sidebar-tabs` CSS | `coding.css` | 25 |
| `.ace-sidebar-view` show/hide CSS | `coding.css` | 10 |
| **Total** | | **~140** |

## What Gets Added

| Code | Location | ~Lines |
|------|----------|--------|
| Group header click handler (toggle collapse) | `bridge.js` | 8 |
| CSS: collapsed state, indent, slim dividers | `coding.css` | 12 |
| **Total** | | **~20** |

## What Stays Unchanged

- Search/create input and its filter/create logic
- Keycap assignment system (`_updateKeycaps`, `_keylabel`, `_keyToPosition`)
- Right-click context menu (rename, colour, delete, move to group)
- Double-click rename, click-dot colour picker
- SortableJS drag-and-drop between groups
- `_refreshSidebar()` for code management CRUD
- "Q" repeat last code
- All server-side code management routes

## Files to Change

| File | Change |
|------|--------|
| `src/ace/templates/coding.html` | Remove tab buttons, remove `#view-recent`/`#view-all` divs, remove `__aceRecentCodeIds`, make Groups view the only view (remove view wrapper class) |
| `src/ace/static/css/coding.css` | Remove tab CSS, remove view show/hide CSS, add slim divider style, add indent on code rows, add collapsed state |
| `src/ace/static/js/bridge.js` | Delete section 3 tab functions, delete `_trackRecent` + calls, add group header click handler, simplify afterSettle/DOMContentLoaded (remove tab rebuilds) |
| `src/ace/routes/pages.py` | Remove recent_code_ids SQL query and context key |

## Net Effect

~140 lines deleted, ~20 lines added. **Net -120 lines.**
