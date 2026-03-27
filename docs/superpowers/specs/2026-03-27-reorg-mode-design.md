# Reorganisation Mode for Code List

## Overview

A toggle mode in the coding page's left panel that enables full drag-and-drop reorganisation of codes and groups. Codes can be dragged between groups, and group headers can be dragged to reorder entire groups.

## Entry/Exit

- Toggle button in the Codes header bar (alongside existing sort button), using a reorder-style icon.
- Click to enter, click again or press Escape to exit.
- Active state indicated by subtle highlight (`bg-grey-3`) on the button.
- Mutually exclusive with sort-by-name mode — entering reorg mode disables alphabetical sort.
- Drag handles on individual codes are hidden in reorg mode; the entire row becomes draggable.

## Architecture: Single Flat Sortable

Replace the current multiple `.ace-code-list` containers (one per group) with a single flat Sortable list when in reorg mode. Group headers and code rows are all items in one list. This is the key change that enables cross-group dragging and group reordering.

Normal mode retains the current per-group Sortable containers (within-group reorder only).

## Drag Behaviour

### Codes

- Draggable to any position in the flat list.
- When dropped between codes in a different group, the code's `group_name` updates to match that group.
- When dropped into the "Ungrouped" section, `group_name` is set to NULL.

### Group Headers

- Dragging a header moves the header and all its codes as a unit.
- Can only be dropped between other group boundaries (not inside another group's codes).
- Insertion line appears between groups.

### Visual Feedback

- Dragged item uses the existing `ace-drag-ghost` opacity treatment.
- A horizontal insertion line (2px, `#bdbdbd`) shows the drop position.

## Ungrouped Codes

When groups exist, ungrouped codes display under an explicit "Ungrouped" header (currently they have no header). This section is draggable like any other group. Dragging a code into this section sets `group_name = NULL`.

## Data Model

No schema changes. Existing fields handle everything:

- `sort_order` (integer) — reassigned sequentially after each drag.
- `group_name` (text, nullable) — updated for codes whose group changed.

Group ordering is implicit, derived from the `sort_order` of the first code in each group.

## Event Payload

The JS drag-end event payload changes from `{ code_ids: [...] }` to a structured list reflecting the new order and group boundaries:

```json
{
  "items": [
    { "type": "group", "name": "Positive" },
    { "type": "code", "id": "abc123" },
    { "type": "code", "id": "def456" },
    { "type": "group", "name": "Ungrouped" },
    { "type": "code", "id": "ghi789" }
  ]
}
```

The Python handler walks this list, tracking the current group header, and assigns `group_name` + `sort_order` to each code accordingly.

## Interaction with Existing Features

- **Normal mode (reorg off):** Unchanged — drag handles visible, within-group reorder only, context menu for "Move to Group".
- **Collapsed groups:** Entering reorg mode auto-expands all groups. Exiting restores previous collapse state.
- **Keyboard shortcuts (1-9/0/a-z):** Work in reorg mode, bound to display order which updates after each drag.
- **"Move to Group" context menu:** Still available in reorg mode.
- **New code input:** Visible and functional; new codes appear ungrouped at the bottom.
- **Refresh after drag:** Same pattern — update `sort_order` and `group_name` in DB, then `_refresh_codes()` + `code_list.refresh()`.
