# Code Reordering Design

## Goal
Allow users to drag-and-drop reorder codes in the left panel. Sort-by-name is a temporary view toggle that doesn't affect stored order.

## Data Layer
- `sort_order` column already exists on `codebook_code` — no schema change
- Add `reorder_codes(conn, code_ids: list[str])` to `codebook.py` — writes `sort_order = index` for each ID
- `list_codes` already returns `ORDER BY sort_order` — no change

## JavaScript
- Vendor `Sortable.min.js` (~10KB) into `src/ace/static/js/`
- In `bridge.js`, initialise SortableJS on `.ace-code-list` container
- Emit `codes_reordered` event with `{code_ids: [...]}` after drag ends
- Disable SortableJS when sort-by-name is active

## UI Changes
- Zero gap between code rows (remove `margin-bottom`)
- Each code row gets `data-code-id` attribute for SortableJS tracking
- Drag handle icon (`drag_indicator`) on left of each row, visible on hover — hidden when sort-by-name active
- Sort-by-name is view-only: sorts in-memory list, toggling off restores DB order via `_refresh_codes()`

## Event Flow
1. User drags code row → SortableJS reorders DOM
2. `bridge.js` emits `codes_reordered` with ordered ID list
3. Python handler calls `reorder_codes(conn, code_ids)`
4. Refreshes in-memory codes list, re-renders text + annotations

## Decisions
- SortableJS vendored locally (no CDN, works offline)
- Sort-by-name never writes to DB — purely a view filter
- New codes always append to end of manual order regardless of sort toggle
