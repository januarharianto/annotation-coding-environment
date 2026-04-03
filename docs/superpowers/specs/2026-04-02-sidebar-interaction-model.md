# Sidebar Interaction Model Redesign

**Date:** 2026-04-02
**Branch:** `fix/sidebar-interactions`

## Problem

The sidebar currently overloads clicks — clicking a code row can mean "apply this code to text" or "select this code for management" depending on hidden state (whether the search filter is active). This creates confusion and breaks rename, delete, and selection workflows. Additionally, several bugs exist: keycaps q/x/z conflict with undo/repeat/delete, the search filter doesn't visually clear after apply, and the cheat sheet has incorrect shortcuts.

## Core Principle

**One surface, one intent.** The sidebar code list is always for browsing and management. Applying a code is always an explicit action initiated from the text panel context or via a clearly distinct click target (the keycap badge).

## Interaction Model

### Applying codes

| Method | Trigger | Behaviour |
|--------|---------|-----------|
| **Keycap hotkey** | Press 1-9, 0, a-y from text panel | Applies code at that keycap position to focused sentence (or custom selection) |
| **Repeat** | Q from text panel | Repeats last applied code |
| **Search-to-apply** | `/` → type → Enter | Applies first visible match, clears filter, returns to text |
| **Search-to-apply (navigate)** | `/` → type → ↓ → Enter | Applies the **focused** code (not first match), clears filter, returns to text |
| **Click keycap badge** | Click the keycap label (1, 2, etc.) on a code row | Applies that code. Always works, regardless of filter state. |
| **Tree Enter** | Tab/↓ into tree → arrow to code → Enter | Applies focused code. Returns to text panel (consistent across all apply paths). |

All apply paths check `__aceLastSelection` first — if a custom text selection exists, uses `_applyCodeToSelection`; otherwise uses `_applyCodeToSentence` on the focused sentence.

### Keycap badge click details

- The keycap `<span class="ace-keycap">` stays as a plain `<span>` — no `role="button"` (nesting interactive roles inside `role='treeitem'` is an ARIA violation). The existing `aria-keyshortcuts` attribute on the treeitem row communicates the shortcut to assistive technology. Click handling is via event delegation on `e.target.closest('.ace-keycap')` — no ARIA role needed for that.
- Click handler via event delegation: `e.target.closest(".ace-keycap")`
- On click: `e.stopPropagation()` to prevent the click from also triggering code-row focus
- If no sentence focused AND no custom selection, the click does nothing (consistent with keycap hotkey behaviour)
- After applying, focus returns to text panel via the existing `.then(_restoreFocus)` on `_applyCodeToSentence`
- **Click target size:** Enlarge the keycap hit area to minimum 28px wide with transparent padding (visible badge stays 18px). Add visible hover state (border darkens, subtle background shift) so users discover it's clickable.
- **Click target height:** Click target must be at least 24x24px (WCAG 2.5.8). Add `min-height: 24px` and sufficient vertical padding to the keycap. The visible badge stays 18px wide but the clickable area is padded to 28x24px minimum.
- **Rename guard:** If the code row is in rename mode (`.ace-code-name` has `contenteditable='true'`), the keycap badge click does nothing — bail out early.

### Managing codes (sidebar)

| Method | Trigger | Behaviour |
|--------|---------|-----------|
| **Select/focus** | Click code row (NOT the keycap badge) | Selects code via roving tabindex (`_focusTreeItem`). No code application. Always. |
| **Rename** | Double-click code name, or F2 in tree, or right-click → Rename | Inline rename |
| **Delete** | Delete/Backspace in tree (double-press), or right-click → Delete | Delete with confirmation |
| **Reorder** | Drag, or Alt+Shift+↑↓ in tree | Reorder code |
| **Indent/outdent** | Alt+→/← in tree | Move into/out of group |
| **Colour** | Right-click → Colour | Colour picker popover |
| **Context menu** | Right-click on code row | Full action menu with shortcut hints |

**New: Click-to-focus handler.** Currently no click handler calls `_focusTreeItem` on code rows. Add a delegated click handler: clicking a code row (not the keycap badge, not during drag, not during rename) calls `_focusTreeItem(row)`.

### Group headers

- **Single click** always calls `_focusTreeItem(header)` AND `_toggleGroupCollapse(header)` — immediate toggle, no two-click dance
- Both calls together: sets roving tabindex on the header (for subsequent keyboard navigation) and toggles collapse

### Search-to-apply flow

The search bar is a **transient command palette** for code application:

1. **`/` from text panel** → search bar gets focus, cursor in input
2. **Type** → codes filter in real-time, keycaps renumber to visible codes
3. **First visible match** gets `ace-code-row--search-target` highlight class (visual cue that Enter will apply it)
4. **Enter** → applies the first visible match (the highlighted one), clears filter, returns to text panel
5. **↓** → moves focus into filtered code list. Arrow keys navigate. The search-target highlight moves with focus. Enter applies the **focused** code (which may differ from the first match).
6. **Escape** (with text) → clears search text, stays in search bar
7. **Escape** (empty) → returns to text panel
8. **Escape from tree** (while filter active) → clears filter AND returns to text panel
   - **Implementation:** add an Escape case to the tree keydown handler. If the search input has a value, clear it via `_clearSearchFilter()` and return focus to text panel. If no filter active, just return focus to text panel (existing behaviour).
9. After any apply action → filter clears, all codes visible again, focus returns to text panel
10. **Sortable drag-and-drop is disabled** while the search filter is active (reordering a filtered list is confusing)

Keycap hotkeys are **not active** while the search input has focus (keys go to the search input). The renumbered keycaps are a **visual reference** — they are not active shortcuts during search.

### Removing the click-to-apply on code rows

The current click handler that applies codes when the search filter is active is **removed entirely**. Click on a code row always means "select/focus this code." Application is done via:
- Keycap badge click (mouse)
- Keycap hotkey (keyboard, text panel)
- Search Enter (keyboard, search bar)
- Tree Enter (keyboard, tree zone)

## Bug Fixes

### 1. Reserved keycaps (q, x, z)

Keys `q`, `x`, and `z` are consumed by repeat, delete-annotation, and undo before reaching the keycap handler. But `_updateKeycaps()` still assigns keycap labels at positions that map to these keys.

**Fix:** `_keylabel()` uses a lookup array that skips q, x, z. The sequence becomes: 1-9, 0, a-p, r-w, y (33 usable positions). `_keyToPosition()` updated to match — returns -1 for q, x, z.

Note: `/` and `?` don't need explicit skipping — they are not in the a-z/0-9 range that `_keyToPosition` handles. The `/` handler (line 429) and `?` handler (line 400) both return before reaching the keycap code.

### 2. `_clearSearchFilter()` doesn't restore sidebar visibility

**Fix:** Dispatch the input event after clearing the value, triggering the filter handler's empty-query branch which restores all rows, strips `<mark>` highlights, and calls `_updateKeycaps()`:

```javascript
function _clearSearchFilter() {
  var el = document.getElementById("code-search-input");
  if (el && el.value) {
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
}
```

Must be called **before** any HTMX swap that replaces the sidebar.

### 3. Cheat sheet corrections

- "← / →" → "Shift+← / Shift+→ Previous / next source"
- Remove "Shift + ← / → Jump 5 sources" (doesn't exist)
- "1 – 9, 0, a – z" → "1 – 9, 0, a–p, r–w, y" (or "1–0, a–y except q, x, z")
- F2 and Delete entries should note "(in sidebar)" since they're being removed from the text zone
- Also update the hint bar in coding.html (line ~193) — change `a-z` to match the corrected keycap range

### 4. Remove F2/Delete from text zone

Remove F2 and Delete handlers from the main (text panel) keydown handler. They depend on invisible `_lastSelectedCodeId` (set only by right-click). These operations work correctly in the tree zone — that's where they belong.

### 5. Group header single-click toggle

Replace the current two-step click handler:

```javascript
// Before (buggy — requires two clicks on unfocused header):
if (header.getAttribute("tabindex") === "0") {
  _toggleGroupCollapse(header);
} else {
  _focusTreeItem(header);
}

// After (always toggles immediately):
_focusTreeItem(header);
_toggleGroupCollapse(header);
```

After toggling, call `_announce('Group <name> expanded')` or `_announce('Group <name> collapsed')`.

### 6. Search Enter visual cue (create vs apply)

When the search input has text and visible matches exist, the first visible code row gets `ace-code-row--search-target` CSS class. This is managed inside the existing input event handler (zero extra cost — the handler already walks all rows). When ↓ is pressed to navigate into the tree, the highlight moves to the focused item.

CSS: subtle background tint, e.g. `background: var(--ace-bg-muted)`.

Set `aria-current='true'` on the target row and remove it from all others. This communicates the target to screen readers. Also call `_announce('Enter to apply: <code name>')` when the target changes.

### 7. Consistent apply paths (support custom selection)

All apply paths (keycap badge click, search Enter, tree Enter) check `__aceLastSelection` first:

```javascript
if (window.__aceLastSelection) {
  _applyCodeToSelection(codeId);
} else if (window.__aceFocusIndex >= 0) {
  _applyCodeToSentence(codeId);
}
```

All apply paths should call `_announce()` after applying: e.g. `_announce("'Code name' applied to sentence N")`.

### 8. Disable Sortable during search filter

When the search input has a value, disable Sortable instances to prevent reordering a filtered (partially hidden) list. Re-enable when the filter clears. Use `sortable.option('disabled', true)` on each instance when the search filter activates. Re-enable with `sortable.option('disabled', false)` when the filter clears. Do not destroy/recreate.

### 9. Filtered rows need `aria-hidden="true"`

When the search filter hides rows via `style.display = 'none'`, also set `aria-hidden='true'`. Remove when showing. This ensures the accessibility tree matches the visual state.

## Files Affected

- `src/ace/static/js/bridge.js` — keycap badge click handler, click-to-focus on code rows, remove click-to-apply on rows, fix `_clearSearchFilter`, fix keycap sequence, fix cheat sheet, fix group header click, remove F2/Delete from text zone, search target highlight, consistent apply paths, Escape-from-tree clears filter, disable Sortable during filter
- `src/ace/static/css/coding.css` — keycap badge hover/cursor styles (enlarged click target), search target highlight class. Add `.ace-keycap:focus-visible { outline: 2px solid var(--ace-focus); outline-offset: 1px; }` for keyboard/programmatic focus.
- `src/ace/templates/coding.html` — keycap spans remain plain `<span>` (no `role="button"`)

## Scope Boundaries

### In scope

- Keycap badge click-to-apply with enlarged target and hover state
- Click-to-focus handler for code rows
- Remove click-to-apply on code rows
- Fix reserved keycaps (q, x, z)
- Fix `_clearSearchFilter()` to restore visibility
- Fix cheat sheet shortcuts
- Remove stale F2/Delete from text zone
- Group header single-click toggle
- Search target highlight (moves with ↓ navigation)
- Consistent apply paths (support custom selection everywhere)
- Escape from tree clears active search filter
- Disable Sortable during search filter

### Out of scope

- Floating toolbar at selection site (Atlas.ti pattern — future)
- Keycap hotkeys active during search (conflicts with typing)
- Persistent search filter (filter clears after apply)
- Multiple Escape handler coordination (low priority)
- Visual feedback when keycap badge click has no effect (polish — future)
- `__aceLastSelection` stale after arrow navigation (pre-existing bug, not introduced here)
