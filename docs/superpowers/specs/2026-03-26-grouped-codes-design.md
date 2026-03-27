# Grouped Codes — Design Spec

## Problem

Codes are currently a flat list. Researchers working with thematic analysis or framework analysis need to organise codes into groups (e.g. "Emotions" → Happy, Sad, Angry). The CSV import format also requires a `colour` column that most users don't care about.

## Design

### CSV Format

```csv
name,group
Happy,Emotions
Sad,Emotions
Identity,Themes
Ungrouped Code,
```

- `name` column required (must be first or present in header)
- `group` column optional — if missing, all codes are ungrouped
- Empty group value = ungrouped
- No `colour` column — colours always auto-assigned from palette
- Old CSVs with `name,colour` still import (colour column ignored)
- Duplicate names: first occurrence kept (unchanged behaviour). If the same code name appears under different groups (e.g. "Happy,Emotions" and "Happy,Wellbeing"), the second is skipped — import dialog shows a warning for dropped duplicates.
- Group names normalised on import: whitespace stripped only (e.g. "  Themes  " → "Themes"). Original casing preserved ("ICR Codes" stays "ICR Codes"). Display consistency via CSS `text-transform: uppercase` on group headers.
- Groups are single-level only. Hierarchical nesting (parent-child codes) is out of scope.

### Database

Add `group_name` column to `codebook_code`:

```sql
ALTER TABLE codebook_code ADD COLUMN group_name TEXT;
```

- Nullable — NULL means ungrouped
- Schema migration v1 → v2 (existing databases get NULL for all codes)
- `sort_order` remains global (not per-group)
- Wire `check_and_migrate(conn)` into `open_project()` in `connection.py` so migrations actually run on database open

### Code List UI

Groups are organisational — visual section headers in the sidebar with collapse/expand.

```
EMOTIONS                [1–2] ▾
  ● Happy                     1
  ● Sad                       2

THEMES                  [3–4] ▾
  ● Identity                  3
  ● Power                     4

UNGROUPED
  ● Other Code                5
```

**Group headers** (`ace-group-header` CSS class):
- 11px, weight 500, `#9e9e9e`, `text-transform: uppercase`, `letter-spacing: 0.05em`
- `border-bottom: 1px solid #e0e0e0`, no background
- `margin-top: 12px` (except first group), `margin-bottom: 2px`
- `padding: 0 4px` — flush-left with code rows
- Clickable to toggle collapse/expand
- Chevron: Material Icon (`expand_more`/`chevron_right`), size `xs`, colour inherited, `transition: transform 0.15s` with rotation (not icon swap)

**Collapse/expand:**
- All groups expanded by default
- Collapse state persisted per project in `app.storage.general` keyed by project path (e.g. `collapsed_groups:/path/to/project.ace`)
- When collapsed, group header shows shortcut range: "EMOTIONS [1–2] ▸" — so the user knows which shortcuts are hidden inside
- Collapsed codes are hidden via CSS `display: none` (keeps DOM flat for Sortable.js)

**Grouped code rows:**
- `padding: 2px 4px 2px 20px` — 16px extra left indent vs ungrouped
- Colour dot + name + shortcut badge (unchanged rendering)
- Keyboard shortcuts numbered sequentially across ALL codes regardless of group or collapse state

**Ungrouped codes:**
- If grouped codes exist, show under an "Ungrouped" label at the bottom (not collapsible)
- Same indent as grouped codes (`padding-left: 20px`) for vertical alignment
- If no codes have groups, render as flat list (same as today, no headers, no extra indent)

**Drag-and-drop:**
- Constrained within each group — codes can only be reordered within their own group
- Cross-group movement via "Move to Group" menu only
- Ungrouped codes can be reordered among themselves
- Sort by name toggle: sorts by `(group_name, name)` tuple

### In-App Group Management

Codes can be assigned to groups from within the app, not just via CSV import:

- The code `⋮` menu gains a "Move to Group" item, separated from editing actions (Rename, Change Colour) and destructive actions (Delete) by `ui.separator()` dividers
- Clicking "Move to Group" shows a `ui.menu()` popup listing:
  - Existing group names in alphabetical order (current group shown with a check icon)
  - `ui.separator()`
  - "New Group..." (opens a small dialog with text input for group name)
  - "Ungrouped"
- Selecting a group updates the code's `group_name`
- "New Group..." prompts for a group name (whitespace stripped, casing preserved)
- Group names are derived from codes — no separate "groups" table. If all codes leave a group, the group disappears — a toast is shown: "'{group}' group removed (no remaining codes)."

### Import Dialog

Same two-section layout (new codes / already in project) but codes within each section are sub-grouped. Group headers have checkboxes for select/deselect all in that group.

```
Import Codes
──────────────────────────
5 new · 2 already in project

New codes (5)              [none]
  ☑ Emotions
    ☑ ● Happy
    ☑ ● Sad
  ☑ Themes
    ☑ ● Identity
    ☑ ● Power
    ☑ ● Agency

Already in project (2)       ▸
  Emotions
    Happy (already exists)
    Angry (already exists)

──────────────────────────
[Cancel]         [Import All 5]
```

- Group-level checkboxes: checking/unchecking a group header toggles all codes in that group
- Tri-state checkbox cycle: indeterminate → all checked → all unchecked → all checked
- Group header checkbox shows indeterminate state when some (not all) codes are checked
- If the CSV has no `group` column, the dialog renders a flat list (same as current)
- Import dialog group headers: 12px font, `#757575`, uppercase, `margin-top: 8px` between groups
- Code rows indented `padding-left: 24px` (past the group checkbox)
- Warning shown for duplicate code names dropped across groups

### Export CSV

Export includes `group` column:

```csv
name,group
Happy,Emotions
Sad,Emotions
Identity,Themes
Ungrouped Code,
```

Exported in `sort_order`. Group column is empty string for ungrouped codes.

### Changes

#### `src/ace/db/schema.py`
- Bump schema version to 2
- Add migration: `ALTER TABLE codebook_code ADD COLUMN group_name TEXT`

#### `src/ace/db/connection.py`
- Call `check_and_migrate(conn)` in `open_project()` after opening the database

#### `src/ace/models/codebook.py`
- `add_code(conn, name, colour, group_name=None)` — new optional parameter
- `update_code(conn, code_id, name=None, colour=None, group_name=_UNSET)` — new optional parameter using a sentinel default. `group_name=None` → don't update (same as other params). `group_name=""` → set to NULL (clear group). `group_name="Emotions"` → set group. The sentinel `_UNSET = object()` distinguishes "not provided" from "set to None".
- `_parse_codebook_csv(path)` — read `group` column if present, ignore `colour` column, strip group name whitespace (preserve casing), return `{"name": str, "group_name": str | None}` dicts. Auto-assign colours from palette.
- `preview_codebook_csv(conn, path)` — include `group_name` in returned dicts
- `import_selected_codes(conn, codes)` — accept and insert `group_name`
- `import_codebook_from_csv(conn, path)` — pass through `group_name`
- `export_codebook_to_csv(conn, path)` — write `name,group` columns (no colour)
- `compute_codebook_hash(conn)` — include `group_name` in hash (note: changes hash for existing files; agreement falls back to name matching which works fine)

#### `src/ace/static/css/annotator.css`
- Add `ace-group-header` class (11px, 500 weight, `#9e9e9e`, uppercase, bottom border, margins)

#### `src/ace/pages/coding.py`
- `code_list()` refreshable — group codes by `group_name`, render collapsible section headers with chevron toggles
- Import dialog — sub-group codes with group-level tri-state checkboxes
- Code `⋮` menu — add "Move to Group" as `ui.menu()` popup, separated by dividers
- Drag-and-drop — constrain within groups (separate Sortable.js instances per group)

#### `src/ace/pages/coding_dialogs.py`
- Add "New Group" dialog: text input for group name, Cancel/Create buttons

#### `tests/test_models/test_codebook.py`
- Update existing import/export tests for new CSV format (no colour column)
- Add tests for group_name in add_code, update_code, list_codes
- Add tests for grouped CSV import/preview/export
- Add tests for group name normalisation (whitespace stripping, casing preserved)

### What Stays the Same

- Annotations, rendering — unchanged
- Agreement computation — matches by code name, ignores groups. Hash change means v1/v2 files won't fast-path match, but name-matching fallback works correctly.
- Colour palette assignment — unchanged (auto-assigns based on index)
- Dialog factories (rename, colour picker, delete) — unchanged

### Edge Cases

- CSV with `name,colour,group` columns — colour ignored, group used
- CSV with only `name` column — all codes ungrouped (backward compatible)
- All codes in same group — renders as one group section
- Empty group name in CSV — treated as ungrouped (NULL in DB)
- Group name normalisation: whitespace stripped only ("  Themes  " → "Themes"), casing preserved ("ICR Codes" stays "ICR Codes")
- Duplicate code name across different groups (e.g. "Happy,Emotions" + "Happy,Wellbeing") — second dropped, warning shown in import dialog
- Last code removed from a group — group header disappears, toast shown
- New code via inline input — always ungrouped; use "Move to Group" to assign
- Collapsed group — codes still receive keyboard shortcuts (shortcuts are global); shortcut range shown on collapsed header
- Re-export of imported codes — group names preserved, colours not (auto-reassigned)
- Old .ace files (schema v1) opened — migration adds group_name as NULL, all codes ungrouped
- Drag-and-drop within group — reorders sort_order within that group only
- Drag-and-drop across groups — not possible; use "Move to Group" instead
- Flat project gains groups (via import) — sidebar transitions from flat to grouped layout on refresh
- All groups removed (all codes ungrouped) — sidebar returns to flat layout, no headers

### Testing

**Schema migration:**
- Fresh DB gets v2 schema with group_name column
- Existing v1 DB migrated: group_name added as NULL for all codes
- `check_and_migrate()` called on `open_project()`

**CSV parsing (`_parse_codebook_csv`):**
- CSV with name + group columns → correct dicts with group_name
- CSV with name only → all group_name values None
- CSV with name + colour + group → colour ignored, group used
- CSV with name + colour (old format) → colour ignored, group_name None
- Empty group values → None
- Group name whitespace stripped: "  Themes  " → "Themes"
- Group casing preserved: "ICR Codes" stays "ICR Codes"
- Duplicate code name across groups → second dropped, warning returned

**Import/export round-trip:**
- Export grouped codes → reimport → same groups preserved
- Export ungrouped codes → reimport → still ungrouped

**`add_code` / `update_code`:**
- Add code with group_name → stored correctly
- Update code group_name → updated correctly
- Update code group_name to empty string → set to NULL
- Add code without group_name → NULL in DB

**In-app group management:**
- Move code to existing group → group_name updated
- Move code to new group → group_name set, new group appears in list
- Move code to "Ungrouped" → group_name set to NULL
- Move last code out of group → group disappears, toast shown
