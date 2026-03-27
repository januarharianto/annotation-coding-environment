# Reorganisation Mode for Code List

## Overview

A toggle mode in the coding page's left panel that enables full drag-and-drop reorganisation of codes and groups. Codes can be dragged between groups, and group headers can be dragged to reorder entire groups.

## Entry/Exit

- Toggle button in the Codes header bar (alongside existing sort button), using a reorder-style icon.
- Click to enter, click again or press Escape to exit.
- Active state indicated by subtle highlight (`bg-grey-3`) on the button.
- Mutually exclusive with sort-by-name mode — entering reorg mode disables alphabetical sort. Exiting reorg always returns to manual order (never re-enables sort-by-name, which would undo the reorganisation).
- Drag handles on individual codes are hidden in reorg mode; the entire row becomes draggable.
- Clicking a code row to apply it is suppressed in reorg mode (full-row drag conflicts with click-to-apply).
- Button is hidden/disabled when no groups exist — flat list reordering is identical to normal mode.

## Architecture: Two-Level Sortable

In reorg mode, use two levels of Sortable instances instead of the current per-group containers:

1. **Outer Sortable** on the parent container. Direct children are group wrapper `<div>`s (header + code list). Dragging a wrapper moves the entire group as a unit. Handle restricted to `.ace-group-header` so only the header initiates the outer drag.

2. **Inner Sortables** on each group's code list `<div>`. All share `group: { name: "codes", pull: true, put: true }`, enabling native cross-group code dragging via Sortable's built-in group mechanism.

This cleanly separates group reordering from code reordering and avoids fighting Sortable's single-item drag model. Group headers can only drop between sibling group wrappers (enforced structurally, no `onMove` filtering needed).

Normal mode retains the current per-group Sortable containers (within-group reorder only).

Use a distinct CSS class (`ace-reorg-list`) for the reorg-mode containers so JS can distinguish modes in `setupCodeListSortable()`.

### MutationObserver Guard

Add a `_dragging` flag (set `true` in `onStart`, `false` in `onEnd`) to prevent the MutationObserver from re-initialising Sortable instances mid-drag.

## Drag Behaviour

### Codes

- Draggable to any position across all inner Sortable containers.
- When dropped into a different group's container, the code's `group_name` updates to match that group.
- When dropped into the "Ungrouped" section, `group_name` is set to `NULL`.

### Group Headers

- Dragging a group header (via the outer Sortable) moves the header and all its codes as a unit.
- Drop targets are between other group wrappers only (enforced by the two-level DOM structure).

### Visual Feedback

- Dragged item uses the existing `ace-drag-ghost` opacity treatment.
- A horizontal insertion line (2px, `#bdbdbd`) shows the drop position.

## Ungrouped Codes

When groups exist, ungrouped codes display under an explicit "Ungrouped" header (currently they have no header). This section is a group wrapper like any other — draggable to reorder among groups, and codes can be dragged into/out of it.

- Dragging a code into this section sets `group_name = NULL`.
- The name "Ungrouped" is reserved — prevent users from creating a literal group with this name (validate in the "New Group" dialog).
- The event payload uses `null` for the ungrouped section's group name, not the string "Ungrouped".

## Empty Groups

If all codes are dragged out of a named group, the group ceases to exist. The `code_list.refresh()` re-render handles this naturally (groups are derived from codes' `group_name` values). A brief notification is shown matching the existing "Move to Group" behaviour.

## Data Model

No schema changes. Existing fields handle everything:

- `sort_order` (integer) — reassigned sequentially (0, 1, 2...) after each drag, ensuring uniqueness.
- `group_name` (text, nullable) — updated for codes whose group changed.

Group ordering is implicit, derived from the `sort_order` of the first code in each group.

### Model Function

The current `reorder_codes()` only updates `sort_order`. A new or modified function is needed that updates both `sort_order` and `group_name` in a single transaction.

## Event Payload

The JS drag-end event emits a nested payload reflecting the two-level DOM structure:

```json
{
  "groups": [
    { "name": "Positive", "code_ids": ["abc123", "def456"] },
    { "name": null, "code_ids": ["ghi789"] }
  ]
}
```

The Python handler iterates groups, assigning sequential `sort_order` values and updating `group_name` for each code. Same event name (`codes_reordered`) with a different payload shape — the handler inspects for the `groups` key to decide which code path to follow.

## Interaction with Existing Features

- **Normal mode (reorg off):** Unchanged — drag handles visible, within-group reorder only, context menu for "Move to Group".
- **Collapsed groups:** Reorg render path ignores the persisted collapsed set — all groups render expanded unconditionally. `app.storage.general` is not modified, so exiting reorg restores previous collapse state automatically.
- **Collapse/expand:** Disabled in reorg mode (group header click does not toggle).
- **Keyboard shortcuts (1-9/0/a-z):** Work in reorg mode, bound to display order which updates after each drag.
- **"Move to Group" context menu:** Still available in reorg mode. Triggers a full re-render (destroying and recreating Sortable instances) to keep DOM in sync.
- **New code input:** Visible and functional; new codes appear at the bottom of the ungrouped section.
- **Refresh after drag:** Update `sort_order` and `group_name` in DB, then `_refresh_codes()` + `code_list.refresh()`.
- **Undo/redo:** Out of scope. Reorg is a deliberate organisational action, not an annotation operation.

## Rendering

The `code_list` `@ui.refreshable` function branches on `state["reorg_mode"]`:

- **Reorg mode:** Renders all codes in two-level wrapper structure (group wrapper > header + code list). No collapse toggles. No drag handles. Full-row dragging.
- **Normal mode:** Existing rendering — per-group containers, collapse/expand, drag handles, click-to-apply.

A `reorg` boolean parameter is passed to `_render_code_row` to control handle visibility, padding, and click behaviour.
