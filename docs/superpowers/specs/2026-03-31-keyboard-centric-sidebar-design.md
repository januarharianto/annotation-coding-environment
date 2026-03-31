# Keyboard-Centric Sidebar Redesign

**Date:** 2026-03-31
**Branch:** `feat/coding-sidebar`
**Approach:** B — Outline-Native (ARIA treeview with roving tabindex)

## Overview

Rebuild the coding sidebar as a keyboard-centric ARIA treeview. The sidebar becomes a proper focusable zone with arrow-key navigation, inline editing, and structural operations (indent, reorder), while preserving mouse/drag-and-drop as a parallel path. The search bar doubles as a unified command line for filtering, code creation, and group creation.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Focus model | Three-zone Tab cycle (text → search → tree → text) | VS Code model — focus location determines key routing, no modes to toggle |
| Group nesting | One level only (group → codes) | Matches data model (`group_name` string), matches qualitative coding conventions |
| Indent/outdent keys | Alt+→ / Alt+← | ARIA treeview reserves Tab for zone navigation; Alt creates coherent "restructure" modifier family with Alt+Shift+↑↓ |
| Enter in tree | Apply code, stay in tree | Supports multi-code workflows; Escape is the explicit exit |
| Create-and-apply | Auto-applies if a sentence is focused | Contextual — no extra UI; just creates if no sentence focused |
| Context menu | Keep as mouse fallback with shortcut hints | Aids discoverability, teaches keyboard workflow, low maintenance cost |
| Undo | Sidebar operations structured as reversible commands | Undo-ready by design; plugs into future global undo/redo system |
| Delete safety | Double-press confirmation (⌫ then ⌫) | Lightweight inline confirm until global undo lands |

## Section 1: Keyboard Interaction Model

### Zone Navigation

Standard Tab cycle with one accelerator:

```
Text Panel  ──Tab──▸  Search Bar  ──Tab──▸  Code Tree  ──Tab──▸  (back to Text Panel)
            ◂─Shift+Tab─  ◂─Shift+Tab─         ◂─Shift+Tab─
```

- **`/`** from text panel → jumps directly to search bar (accelerator)
- **Escape** from anywhere in sidebar → returns to text panel

### Text Panel Keys (unchanged)

| Key | Action |
|-----|--------|
| `1-9`, `0`, `a-z` | Apply code by keycap shortcut |
| `↑` / `↓` | Navigate sentences |
| `Shift+←` / `Shift+→` | Navigate sources |
| `Q` | Repeat last code |
| `Z` | Undo |
| `X` | Delete annotation |
| `/` | Jump to search bar |
| `Tab` | Move focus to search bar |

### Search Bar Keys

| Key | Action |
|-----|--------|
| Typing | Filter codes in real-time |
| `Enter` | Create new code (if no codes visible after filtering); auto-applies if sentence focused |
| `↓` | Jump into code tree |
| `Escape` | 1st press: clear text. 2nd press (or if empty): return to text panel |
| `Tab` | Move focus to code tree |
| `Shift+Tab` | Move focus to text panel |

### Code Tree Keys

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate between codes |
| `←` / `→` | Collapse/expand group (on header); jump to parent/child |
| `Enter` | Apply focused code to current sentence (stay in tree) |
| `F2` | Inline rename focused code |
| `Alt+→` | Indent code into nearest group above |
| `Alt+←` | Outdent code from group (move to ungrouped) |
| `Alt+Shift+↑` / `Alt+Shift+↓` | Reorder code up/down |
| `Delete` / `Backspace` | Delete code (with double-press confirmation) |
| `Escape` | Return focus to text panel |
| `Tab` | Move focus to text panel |
| `Shift+Tab` | Move focus to search bar |

## Section 2: Search Bar & Group Creation

The search bar serves three functions:

### Flow 1: Filter existing codes

Type to filter. Non-matching codes are hidden. Groups with no visible codes are hidden. Matching text is highlighted in code names. Keycaps renumber to reflect visible codes only.

### Flow 2: Create new code

When no codes match the typed text, a green "Create" prompt appears below the search bar. Press Enter to create. If a sentence is currently focused in the text panel, the new code is also applied to it. Search bar clears after creation.

### Flow 3: Create new group

Type `/` as the first character to enter group creation mode. The `/` prefix is displayed visually (purple). Text after it becomes the group name. Press Enter to create an empty group. If a group with that name already exists, the search filters to show that group instead.

### Flow 4: Indent to create group (from code tree)

Focus an ungrouped code and press Alt+→. If there is a group directly above, the code moves into it. If there is no group above, an inline prompt appears asking for a group name. Enter confirms, Escape cancels. The new group is created with the code inside it.

## Section 3: Visual States

Six states for code tree items, all using existing design tokens:

| State | Visual treatment |
|-------|-----------------|
| **Idle** (text panel has focus) | No focus ring, keycaps visible, passive reference |
| **Focused** (arrow keys navigating) | Solid blue outline (`--ace-focus`), light blue background tint |
| **Rename** (F2 pressed) | Name becomes inline editable with text selected, blue selection highlight, keycap hidden |
| **Reorder** (Alt+Shift+Arrow) | Dashed blue outline on moving item, keycaps update in real time |
| **Delete confirm** (⌫ pressed) | Red outline, red tinted background, "Delete?" text replaces keycap. ⌫ again confirms, Escape cancels |
| **Collapsed group** | Group header shows ▸ triangle + code count, keycaps skip hidden codes |

No new colours introduced. All states use `--ace-focus` and `--ace-danger` tokens.

## Section 4: Context Menu

The existing right-click context menu is preserved as a mouse fallback with keyboard shortcut hints added to each item:

| Menu item | Shortcut hint |
|-----------|---------------|
| Rename | `F2` |
| Colour | (no shortcut) |
| Move Up | `Alt+Shift+↑` |
| Move Down | `Alt+Shift+↓` |
| Move to Group ▸ | `Alt+→` |
| Delete | `⌫` |

Separator lines between rename/colour, move operations, and delete (as current).

## Section 5: Accessibility

### ARIA Tree Structure

- Outer container: `role="tree"` with `aria-label="Code list"`
- Group headers: `role="treeitem"` with `aria-expanded="true|false"`, `aria-level="1"`
- Group children wrapper: `role="group"`
- Code rows: `role="treeitem"` with `aria-level="2"` (in group) or `aria-level="1"` (ungrouped)
- Keycap shortcuts: `aria-keyshortcuts` attribute on each code row (e.g. `aria-keyshortcuts="1"`)
- Search input: `<input type="search">` with `aria-controls` pointing to tree ID, placeholder text "Filter codes (/)" to hint at the `/` accelerator

### Focus Management (Roving Tabindex)

- Focused treeitem gets `tabindex="0"`, all others get `tabindex="-1"`
- Arrow keys swap tabindex values and call `.focus()`
- Tree is a single Tab stop — Tab enters, Tab exits

### Screen Reader Announcements

Hidden `aria-live="polite"` region. Messages pushed after each action:

| Action | Announcement |
|--------|-------------|
| Create code | "Code 'Resilience' created" |
| Apply code | "'Theme A' applied to sentence 4" |
| Rename code | "Code renamed to 'Revised Theme'" |
| Delete code | "Code 'Power' deleted" |
| Reorder code | "'Belonging' moved to position 3" |
| Indent into group | "'Power' moved into Themes" |
| Create group | "Group 'Emotions' created" |

### Focus Restoration After HTMX Swaps

HTMX replaces sidebar HTML after every server action, destroying the focused element. Restoration protocol:

1. **Before swap:** record `data-code-id` of focused treeitem
2. **After `htmx:afterSettle`:** find element with same `data-code-id`
3. **Restore:** set `tabindex="0"` and call `.focus()`
4. **Fallback:** if element was deleted, focus nearest sibling; if no siblings, focus tree root

Also restores: group collapse state (existing `_collapsedGroups`), scroll position, and search bar text if filtering was active.

### Visible Focus Indicators

All focusable elements must have visible focus indicators with minimum 3:1 contrast ratio against adjacent colours (WCAG 2.2 SC 1.4.11). The existing `--ace-focus` blue token meets this against the slate background.

## Scope Boundaries

### In scope

- ARIA treeview rebuild of sidebar template and JS
- Keyboard navigation (roving tabindex, arrow keys)
- Search bar: filter + create code + create group (`/prefix`)
- Inline rename, keyboard reorder, keyboard indent/outdent
- Context menu shortcut hints
- Focus restoration after HTMX swaps
- aria-live announcements
- Sidebar operations structured as reversible commands (undo-ready)

### Out of scope

- Global undo/redo system (separate feature)
- Multi-select in tree
- Nested groups beyond one level
- Command palette (Cmd+K)
- Keyboard shortcut legend/help overlay (can be added later)
- Changes to text panel or API routes
