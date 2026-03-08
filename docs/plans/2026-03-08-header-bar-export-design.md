# Header Bar + CSV Export Design

## Goal

Add a persistent header bar across all pages and a one-click CSV export action.

## Architecture

A shared `ui.header()` component built as a reusable function in `src/ace/pages/header.py`, called by each page's route function. Thin, minimal bar that stays out of the way.

## Header Layout

- **Left:** Project name (clickable, navigates to `/`)
- **Right:** "Export" button + "More" dropdown menu (placeholder for future items)

## Per-Page Behaviour

| Page | Left | Right |
|------|------|-------|
| `/` (landing) | "ACE" branding | Nothing (no project context yet) |
| `/import` | Project name → `/` | Nothing (no data to export yet) |
| `/code` | Project name → `/` | Export button + More menu |

## Export Behaviour

1. User clicks "Export" in header
2. Backend calls `export_annotations_csv(conn, tmp_path)` (already exists in `src/ace/services/exporter.py`)
3. `ui.download()` triggers browser file download
4. Default filename: `{project_name}_export_{YYYY-MM-DD}.csv`
5. Browser settings control whether it auto-saves or prompts "Save As"

## Out of Scope

- Codebook import UI (#35) — future, will go in "More" menu
- Project instructions (#36) — future
- Multi-coder export filtering (#37) — future
- Export format options (only CSV for now)

## Tech

- NiceGUI `ui.header()` for the bar
- `ui.download()` for triggering browser download
- `tempfile` for writing CSV before serving
- Existing `export_annotations_csv()` backend unchanged
