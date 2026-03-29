# Code Management Redesign — Inline Direct Manipulation

## Goal

Remove the management mode (gear button) and replace it with inline direct manipulation patterns: right-click context menu, double-click rename, click-dot colour picker, drag-and-drop reorder, keyboard shortcuts. Net reduction of ~80 lines.

## Interactions

| Action | Primary | Keyboard | Context menu |
|--------|---------|----------|-------------|
| Create code | Search input + Enter | Enter in search | — |
| Rename | Double-click name | F2 | Right-click > Rename |
| Delete | — | Delete (press twice to confirm) | Right-click > Delete |
| Recolour | Click colour dot | — | Right-click > Colour |
| Reorder | Drag-and-drop | — | — |
| Move to group | Drag onto group header | — | Right-click > Move to Group > submenu |

## What Gets Removed

- **JS:** `aceToggleManageMode()`, management mode create-input handler (~20 lines)
- **CSS:** `.ace-sidebar--manage`, `.ace-code-menu-btn`, `.ace-manage-create` and all management mode variants (~57 lines)
- **Template:** Gear button, ⋯ buttons on code rows, manage-create input (~12 lines)
- **Python:** 4 dialog endpoints — `rename-dialog`, `colour-dialog`, `delete-dialog`, `move-dialog` (~174 lines)

Total removed: ~275 lines

## What Gets Added

### 1. Right-click context menu (~20 JS)

Reuse existing `aceCodeMenu` dropdown but trigger via `contextmenu` event on `.ace-code-row` instead of ⋯ button click. Position at cursor. Menu items:
- Rename (triggers inline rename)
- Colour (opens swatch popover)
- Move to Group > submenu listing existing groups
- Delete (with annotation count warning)

Long-press support for touch devices (~12 lines extra).

### 2. Double-click inline rename (~25 JS/CSS)

Double-click `.ace-code-name` → `contenteditable=true`, select all, focus. Enter/blur saves via `fetch PUT /api/codes/{id}`. Escape reverts. CSS: `[contenteditable] { outline: 1px solid var(--ace-focus); }`.

### 3. Click-dot colour swatch popover (~42 JS/CSS)

Click `.ace-code-dot` → small popover with 36 preset colour swatches (6×6 grid). Click swatch → `fetch PUT /api/codes/{id}` with new colour → update dot background → close. Palette hardcoded as JS constant (same golden-angle algorithm). No server round-trip for the dialog.

### 4. Drag-and-drop via SortableJS (~34 JS/CSS, 6 template)

Template change: wrap each group's code rows in `<div class="ace-code-group" data-group="GroupName">` container. SortableJS with `group: "codes"` for cross-group dragging. `onEnd` callback: detect group change → PUT group_name, collect new order → POST `/api/codes/reorder`. Re-init on `htmx:afterSettle`.

### 5. Double-press Delete (~21 JS/CSS)

Press Delete with a code selected → row flashes red with "Delete?" indicator → press Delete again within 2s → `fetch DELETE /api/codes/{id}` → sidebar refreshes. Timeout resets state. Track `_lastSelectedCodeId` from context menu or click.

### 6. F2 rename shortcut (~3 JS)

F2 triggers inline rename on `_lastSelectedCodeId`. Reuses Feature 2's `_startInlineRename()`.

Total added: ~195 lines

## Template Change for Drag-and-Drop

Current (flat siblings):
```html
<div class="ace-code-group-header">▾ Emotions (3)</div>
<div class="ace-code-row" data-code-id="...">...</div>
<div class="ace-code-row" data-code-id="...">...</div>
```

New (nested containers):
```html
<div class="ace-code-group" data-group="Emotions">
  <div class="ace-code-group-header">▾ Emotions (3)</div>
  <div class="ace-code-row" data-code-id="...">...</div>
  <div class="ace-code-row" data-code-id="...">...</div>
</div>
```

## Existing Endpoints Retained

- `PUT /api/codes/{id}` — update name, colour, group_name
- `DELETE /api/codes/{id}` — delete code
- `POST /api/codes/reorder` — reorder codes
- `POST /api/codes` — create code

## Existing Endpoints Removed

- `GET /api/codes/{id}/rename-dialog`
- `GET /api/codes/{id}/colour-dialog`
- `GET /api/codes/{id}/delete-dialog`
- `GET /api/codes/{id}/move-dialog`
