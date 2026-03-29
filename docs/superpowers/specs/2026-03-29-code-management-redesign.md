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
| Reorder | Drag handle | Move Up/Down (on selected code) | Right-click > Move Up / Move Down |
| Move to group | Drag onto group header | — | Right-click > Move to Group > submenu |

## What Gets Removed

- **JS:** `aceToggleManageMode()`, management mode create-input handler (~20 lines), `aceCodeMenu()` dialog-endpoint calls (rewritten, not removed)
- **CSS:** `.ace-sidebar--manage`, `.ace-code-menu-btn`, `.ace-manage-create` and all management mode variants (~57 lines)
- **Template:** Gear button, ⋯ buttons on code rows, manage-create input (~12 lines)
- **Python:** 4 dialog endpoints — `rename-dialog`, `colour-dialog`, `delete-dialog`, `move-dialog` (~174 lines)

Total removed: ~275 lines

## What Gets Added

### 1. Right-click context menu (~20 JS)

Rewrite `aceCodeMenu` to be triggered via `contextmenu` event on `.ace-code-row` (delegated listener on sidebar). Position at cursor (`e.clientX`, `e.clientY`). Menu items call inline handlers directly (no dialog endpoint fetches):
- Rename → triggers `_startInlineRename(codeId)`
- Colour → triggers `_openColourPopover(codeId, dotElement)`
- Move to Group → submenu listing groups from `window.__aceCodes`
- Move Up / Move Down → reorder via fetch POST
- Delete → double-press confirmation flow

Long-press support for touch: 500ms threshold via `pointerdown`/`pointerup` timer. Add `-webkit-touch-callout: none` on `.ace-code-row` to suppress native iOS callout.

When context menu is open, suppress keyboard shortcuts by checking a `_menuOpen` flag in the keydown handler.

### 2. Double-click inline rename (~30 JS/CSS)

Double-click `.ace-code-name` → set `contenteditable=true`, select all, focus.

**Keyboard handling during edit:**
- Enter → `e.preventDefault()`, save via `fetch PUT /api/codes/{id}`, remove contenteditable
- Escape → revert to original text, remove contenteditable
- All other keys → type normally (no code shortcuts — see `_isTyping` fix below)

**Paste sanitisation:** Intercept `paste` event, insert `text/plain` only.

**Validation:** Reject empty names (revert to original). Server-side: add try/except on `update_code()` for UNIQUE constraint → return toast on duplicate name.

**CSS overrides for contenteditable:**
```css
.ace-code-name[contenteditable] {
  outline: 1px solid var(--ace-focus);
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
}
```

**Focus after save:** Return focus to `#text-panel`.

### 3. Click-dot colour swatch popover (~42 JS/CSS)

Click `.ace-code-dot` → small popover with 36 preset colour swatches (6×6 grid, ~28px per swatch). Palette hardcoded as JS constant (same golden-angle algorithm as Python). No server round-trip for the dialog.

Click swatch → `fetch PUT /api/codes/{id}` with new colour → update dot background + update `<style id="code-colours">` block (regenerate from `window.__aceCodes` with updated colour) → close popover.

**Focus after colour change:** Return focus to `#text-panel`.

### 4. Drag-and-drop via SortableJS (~40 JS/CSS, 6 template)

**No drag handle.** SortableJS `delay: 200` — hold anywhere on the row for 200ms to start dragging. Double-click fires before 200ms so rename is not affected. No extra DOM elements, no grid column changes, no CSS changes. Move Up/Move Down in context menu provides keyboard-accessible alternative.

**Template change:** Wrap each group's code rows in `<div class="ace-code-group" data-group="GroupName">` container. Ungrouped codes in `<div class="ace-code-group" data-group="">` (explicit empty string, not absent attribute).

SortableJS with `group: "codes"` for cross-group dragging. `onEnd` callback:
1. Read destination container's `data-group`
2. If group changed → `fetch PUT /api/codes/{id}` with `group_name` (empty string for Ungrouped)
3. Collect all code IDs in new order → `fetch POST /api/codes/reorder`

**HTMX swap safety:** Track drag state via `onStart`/`onEnd` flags. In `htmx:afterSettle`, only re-init SortableJS if no drag is in progress. If drag is active, defer re-init until `onEnd` fires.

**Re-init on `htmx:afterSettle`** when sidebar is swapped.

### 5. Double-press Delete (~21 JS/CSS)

Press Delete with `_lastSelectedCodeId` set → row gets `ace-code-row--confirm-delete` class (red flash) → press Delete again within 2s → `fetch DELETE /api/codes/{id}` → trigger sidebar refresh. Timeout resets visual state.

`_lastSelectedCodeId` is set by right-click (context menu) or by clicking a code row. Not set by left-click-to-apply (which applies annotations).

**Focus after delete:** Focus next sibling `.ace-code-row`, or previous if last, or `#text-panel` if none remain.

### 6. F2 rename shortcut (~3 JS)

F2 triggers `_startInlineRename(_lastSelectedCodeId)`. Added to cheat sheet.

### 7. `_isTyping()` guard update (~2 JS)

Add `|| (document.activeElement && document.activeElement.isContentEditable)` to the existing `_isTyping()` check. Prevents keyboard shortcuts from firing during inline rename.

Also add check for `_menuOpen` flag to suppress shortcuts while context menu is open.

Total added: ~195 lines

## Template Change for Drag-and-Drop

Current (flat siblings):
```html
<div class="ace-code-group-header">▾ Emotions (3)</div>
<div class="ace-code-row" data-code-id="...">...</div>
```

New (nested containers, no extra elements):
```html
<div class="ace-code-group" data-group="Emotions">
  <div class="ace-code-group-header">▾ Emotions (3)</div>
  <div class="ace-code-row" data-code-id="...">
    <span class="ace-code-dot" style="background: #e53935;"></span>
    <span class="ace-code-name">Frustration</span>
    <span class="ace-keycap">1</span>
  </div>
</div>
```
No visual change to code rows. SortableJS `delay: 200` handles drag vs click.

Ungrouped codes use `data-group=""` (explicit empty string):
```html
<div class="ace-code-group" data-group="">
  <div class="ace-code-group-header">▾ Ungrouped (5)</div>
  ...
</div>
```

## Server-Side Fixes

- `PUT /api/codes/{id}`: Add try/except for `IntegrityError` → return toast "Name already exists"
- `PUT /api/codes/{id}`: Reject empty name → return toast "Name cannot be empty"

## Existing Endpoints Retained

- `PUT /api/codes/{id}` — update name, colour, group_name
- `DELETE /api/codes/{id}` — delete code (with cascade)
- `POST /api/codes/reorder` — reorder codes
- `POST /api/codes` — create code

## Existing Endpoints Removed

- `GET /api/codes/{id}/rename-dialog`
- `GET /api/codes/{id}/colour-dialog`
- `GET /api/codes/{id}/delete-dialog`
- `GET /api/codes/{id}/move-dialog`

## Cheat Sheet Updates

Add to `_toggleCheatSheet()`:
- F2 — Rename selected code
- Delete — Delete selected code (press twice)
