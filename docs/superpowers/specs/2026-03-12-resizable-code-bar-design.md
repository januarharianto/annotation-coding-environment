# Resizable Code Bar

## Problem

The code bar (left panel) on the coding page is fixed at 280px. Users with long code names or many codes may want it wider; users working on small screens may want it narrower.

## Solution

Replace the current `ui.row()` two-pane layout with NiceGUI's `ui.splitter()` (wraps Quasar `q-splitter`) in pixel mode.

## Specification

### Layout

```
ui.splitter(value=280, limits=(180, 600)).props('unit="px"')
    .classes("full-width col").style("overflow: hidden;")
├── splitter.before  → code bar content (unchanged)
├── splitter.separator  → Quasar drag handle (styled to match theme)
└── splitter.after   → text content area (unchanged)
```

- Default width: 280px
- Min width: 180px
- Max width: 600px (fixed cap — server-side code cannot read client viewport at build time)
- Pixel mode via `.props('unit="px"')`
- Splitter must carry `col` class (flex-grow to fill vertical space, same as current `ui.row()`)

### Persistence

- On resize: save `splitter.value` to `app.storage.general['code_bar_width']`
- On page load: restore from storage, default to 280 if absent
- Use `on_change` callback — NiceGUI throttles this at 50ms during drag, which is acceptable for a single-user local app writing to JSON storage

### Double-click reset

- JS listener in `bridge.js` for `dblclick` on `.q-splitter__separator`
- Must use **delegated event binding** on `document` (e.g. `e.target.closest('.q-splitter__separator')`) since the separator is rendered async by Vue/Quasar — consistent with existing `setupGridClickListener` pattern
- Call `e.preventDefault()` to avoid text selection side-effects
- Emits custom event `code_bar_reset` to Python
- Python handler sets `splitter.value = 280` and clears stored width

### Separator styling

- Match existing border colour: `#bdbdbd`
- Cursor: `col-resize` (built-in from Quasar)
- Minimal visual weight — thin line, no grab handle icon

### Migration notes

- Remove `border-right: 1px solid #bdbdbd` from left panel inline styles (splitter provides its own separator)
- Remove `width: 280px; min-width: 280px` from left panel (splitter controls width)
- Mobile/touch: Quasar splitter supports touch natively; no extra work needed

## Files changed

1. `src/ace/pages/coding.py` — replace `ui.row()` wrapper with `ui.splitter()`, remove fixed width/border from left panel, add persistence callbacks (~15 lines net)
2. `src/ace/static/js/bridge.js` — add delegated dblclick reset listener (~10 lines)
3. `src/ace/static/css/annotator.css` — separator styling if needed (~3 lines)

## What does NOT change

- Code bar content (code list, input, sort, drag reorder)
- Text content area (source header, annotated text, annotation list)
- Bottom bar and source grid navigator
- Any other page or component
