# Import/Export Codes via CSV

## Problem

There's no way to bootstrap a project's codebook from an existing set of codes. Users creating multiple projects with the same codes must re-enter them manually.

## Solution

Add CSV import and export for codes, accessible from the coding page's code bar.

## Specification

### UI: Menu button

A `more_vert` icon button in the "Codes" header row, next to the existing sort button. Same flat/dense styling. Opens a `ui.menu()` with:

- **Import CSV...** — enabled only when codebook is empty
- **Export CSV** — enabled only when codes exist

### UI: Empty state

When the code list is empty, show in place of the code list:

> "No codes yet. Type above to add one, or [import from CSV](#)."

- Styled as `text-caption text-grey-6` (matches existing empty states like "No annotations yet.")
- "import from CSV" is a clickable link that triggers the file picker directly (same action as the menu item)
- Implementation: use `ui.html(sanitize=False)` with an `<a>` tag + JS click handler, or `ui.link()` element

### Import flow

1. User clicks "Import CSV..." (menu) or "import from CSV" (empty state link) → native file picker (accept `.csv` only)
2. Parse CSV with `encoding="utf-8-sig"` (handles Excel BOM transparently)
3. Require `name` column header; `description` and `colour` columns are optional
4. Validation per row:
   - Rows with empty/missing `name` are skipped
   - Duplicate names within the CSV: keep first occurrence, skip subsequent
   - Invalid `colour` values (not matching `#RRGGBB`): treat as missing
5. Missing/invalid colours auto-assigned from palette via `next_colour(row_index)` where `row_index` is the row's ordinal position (0, 1, 2, ...)
6. Entire import wrapped in a single transaction (atomic — all or nothing)
7. Codes added to DB, code list refreshes
8. `ui.notify()`: "Imported N codes" (or "No valid codes found in CSV" if N=0)
9. On error (missing `name` column, unreadable file): `ui.notify()` with error message, transaction rolled back

### Export flow

1. User clicks "Export CSV" → generate CSV server-side with columns: `name`, `description`, `colour`
2. Ordered by `sort_order` (matches display order)
3. Instant browser download, filename: `codes.csv`

### CSV format

```csv
name,description,colour
Theme A,First theme,#FF0000
Theme B,,#00FF00
Theme C,,
```

- Header row required on import
- `name` required per row, `description` and `colour` optional
- On export, all three columns always present

### Constraints

- Import only available when codebook is empty (no conflict handling needed)
- Export only available when codes exist (nothing to export otherwise)

## Files changed

1. `src/ace/models/codebook.py` — add `export_codebook_to_csv()` function; rewrite `import_codebook_from_csv()` to:
   - Use `row.get("colour")` instead of `row["colour"]` (current code raises `KeyError` when column is absent)
   - Fall back to `next_colour(index)` for missing/invalid colours
   - Validate colour format (`#RRGGBB` regex)
   - Deduplicate names within CSV (keep first occurrence)
   - Wrap in a single transaction (current code commits per row via `add_code()` — use direct INSERT instead)
   - Open CSV with `encoding="utf-8-sig"`
2. `src/ace/pages/coding.py` — add `more_vert` menu button in Codes header, import/export handlers, empty state text with clickable link

## What does NOT change

- Import page (`/import`)
- Exporter service (annotation export)
- Packager service
- Any other page or component
