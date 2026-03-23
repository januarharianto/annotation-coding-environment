# Source Grid Navigator Design

## Problem

Navigation is linear (Prev/Next). With 1000+ sources, finding a specific source requires clicking through one at a time.

## Solution

A toggleable grid panel in the bottom bar showing all sources as small coloured squares. Annotation density encoded as a blue gradient. Click to jump.

## UI

- **Toggle**: Click `Source 3 of 150 ▾` label in bottom bar. Keyboard shortcut: `G`.
- **Grid panel**: Appears between main content and bottom bar. Single `ui.html()` with flex-wrap layout.
- **Cell colours**: Blue gradient (lightest→darkest) for annotation density, normalised to max in project. Zero annotations = near-white.
- **Current source**: White 2px outline (visible against any shade).
- **Flagged sources**: Orange border.
- **Cell size**: Adaptive based on source count — larger when fewer sources.
- **Legend**: One-line legend at top of panel.

## Interaction

- Hover: native `title` tooltip with display ID + annotation count.
- Click cell: jump to source, close grid.
- Click label again or Escape: close grid.

## Implementation

- Single `ui.html(sanitize=False)` for the entire grid — no per-cell NiceGUI elements.
- Event delegation in `bridge.js` — one click listener reads `data-idx`.
- `set_visibility()` toggle for the panel.
- One SQL query for annotation counts: `SELECT source_id, COUNT(*) FROM annotation WHERE deleted_at IS NULL GROUP BY source_id`.
