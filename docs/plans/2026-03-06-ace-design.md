# ACE: Annotation Coding Environment - Design Document

**Date:** 2026-03-06
**Status:** Approved (revised after expert review)
**Author:** Januar Harianto + Claude

## 1. Overview

ACE is a lightweight, local-first qualitative coding tool designed for small research teams (2-5 coders). It focuses on three things and does them well:

1. **Span-level text coding** with a clean annotation interface
2. **Distributed coding workflow** — split data across coders, merge results
3. **Inter-coder reliability** — compute agreement metrics on overlapping assignments

It is NOT a full NVivo replacement. It targets focused ICR studies where a team codes text data, needs reliable agreement metrics, and wants a tool that is free, lightweight, and pip-installable.

## 2. Architecture

### Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| App framework | NiceGUI (Python, FastAPI + Vue/Quasar) | Single language, pip installable, rich UI components, local web app |
| Annotation UI | @recogito/text-annotator (vanilla JS) | W3C compliant, overlapping spans, actively maintained |
| Storage | SQLite (single .ace file per project) | Portable, zero-config, proven in QualCoder/NVivo |
| ICR computation | irrCAC | Comprehensive: Cohen's kappa, Fleiss' kappa, Krippendorff's alpha, Gwet's AC1 |
| Distribution | pip install | `pip install ace-coder` then `ace` command opens browser |

### Deployment Model

- Local web app: runs a local server, opens in default browser
- Binds to `127.0.0.1` only (not accessible from network)
- No authentication needed (single-user local app)
- Landing page with:
  - **"New Project"** button for managers starting fresh
  - **Drag-and-drop zone** for opening existing `.ace` files (manager or coder)
- Recogito JS/CSS **vendored** as static assets in the Python package (works offline via `app.add_static_files()`)

## 3. User Modes

Mode is determined by the `file_role` field in the project table: `manager` or `coder`. The app reads this on file open and routes to the correct interface. If a coder drags a manager file, the app warns and refuses to open it in coder mode (and vice versa).

### Manager Mode

Wizard with **back-navigation** (can return to previous steps). Warning shown if going back to Codebook after assignments exist. Project dashboard for returning to Results later.

**Step 1 — Import:**
- Drag CSV/Excel file (with encoding detection: UTF-8 default, fallback to Latin-1/Windows-1252)
- Preview table of data
- Select ID column (participant identifier)
- Select text column(s) to code — each selected text column becomes a separate source row, with a `source_column` field recording which column it came from. `display_id` combines participant ID + column name.
- Other columns preserved as queryable metadata
- Also supports: drag a folder of .txt files (filename = ID, content = text)

**Step 2 — Codebook:**
- Flat list of codes: name, colour (colour-blind accessible palette), description
- Add, edit, delete, reorder codes
- Import codebook from CSV (columns: name, colour, description)
- Project-level coding instructions (free text, visible to all coders)
- **After coder packages are exported:** code deletion is locked (prevented). Adding new codes and editing descriptions/colours is allowed. This prevents FK violations on import while allowing codebook refinement.

**Step 3 — Assign:**
- Enter coder names
- Set ICR overlap % via slider
- Live preview showing **concrete numbers** per coder (sources unique + sources shared, total workload)
- Semantics: overlap % = percentage of total sources assigned to exactly **2 coders** (pairwise, not all coders)
- **Algorithm:** uniform random selection without replacement. Random seed stored in project for reproducibility. Overlap sources assigned to random pairs of coders. Remaining sources distributed equally.
- Confirmation step: "You are about to create N coder packages. Each coder will receive approximately X documents. Y documents will be coded by 2 coders for reliability checking. This cannot be changed after export."

**Step 4 — Export:**
- Generate one `.ace` file per coder
- Save to a chosen folder
- Files named `project-name_coder-name.ace`
- Codebook hash stored in project table at export time

**Step 5 — Results (separate entry point, accessible when reopening project):**
- Import returned `.ace` files (drag and drop)
- **Auto-backup:** main `.ace` file is copied before any merge operation
- Merge preview: completion stats per coder, overlap coverage, flagged sources count
- Validation: check project ID, schema version, codebook hash, content hashes
- Clear error messages (e.g. "This file belongs to project X but you have project Y open")
- Merge: copy annotations into main project
- ICR dashboard: per-code binary agreement table (kappa, alpha, percent agreement) + overall macro-averaged agreement + disagreement viewer
- Adjudication: for disagreements, accept Coder A / accept Coder B / create consensus annotation (attributed to a virtual "consensus" coder). Rejected annotations preserved with a `rejected` flag, not deleted.
- Data export: annotations to CSV/Excel with columns: source_id, display_id, coder_name, code_name, selected_text, start_offset, end_offset, memo, source_note, plus all metadata columns
- ICR report export to CSV

### Coder Mode

Single screen, opened by dragging a coder `.ace` file onto the landing page.

**Layout:**
- Left sidebar: flat code list with colour dots, names, and number shortcuts (1-9). Codes 10+ have no shortcut in v1 (acknowledged limitation).
- Code descriptions shown on hover (tooltip)
- Centre: text content with coloured span annotations
- Bottom bar: source navigation + progress
- Collapsible metadata panel (other CSV columns visible for context)
- Notes field per source (free text, travels back to manager)

**Interaction model: highlight-then-pick-code**
1. Coder reads text naturally
2. Selects a span of text (standard browser selection)
3. Floating popover appears near the selection with compact code list. Popover anchored to selection midpoint, repositioned to avoid viewport clipping.
4. Click a code (or press 1-9 keyboard shortcut) to apply. Shortcuts work whenever there is an active text selection (popover need not be visible).
5. Text highlights with code colour (brief fade-in animation, ~150ms), popover dismisses, selection clears
6. Clicking an existing annotation shows: all applied code names, "Remove [code]" option per code, "Add code" option. For overlapping multi-code spans, all codes are listed.
7. Multiple codes can be applied to the same span (overlapping annotations supported)

**Overlapping annotation rendering:** Semi-transparent background colours layered. Tooltip on hover shows all applied code names. Spike test Recogito's default rendering in week 1; if insufficient, implement CSS Custom Highlight API fallback.

**Navigation:**
- Document list panel (collapsible, shows all assigned sources with completion status icon)
- Jump to any source directly
- Filter: show only incomplete / flagged
- Prev/next keyboard shortcuts

**Onboarding:**
- First-time coder sees a **dismissible instructional overlay** on their first source:
  - "Read the text below. Highlight passages and click a code to annotate them."
  - Shows the project-level coding instructions from the manager
  - Shows code descriptions in a compact list
  - "Got it" button dismisses and never appears again
- No separate practice document (deferred to v2)

**Completion:**
- Per-source status: `pending` / `in_progress` / `complete` / `flagged`
  - Status auto-transitions from `pending` to `in_progress` when coder opens a source
  - "Mark Complete" is a **toggle** (reversible — coder can go back and revise)
  - "Flag for Review" marks the source for manager attention (appears prominently in merge view)
- When last source is marked complete: "You're finished!" with a **"Reveal in Finder/Explorer"** button showing the `.ace` file location, plus manager name to send it to
- Annotations auto-save on every annotation event (create/update/delete). No explicit save needed. Coder's file is always up to date.

**Undo/redo:**
- Scope: **per-source, in-memory, lost on navigation between sources or app restart**
- Covers: annotation create, update, delete
- Does NOT cover: navigation, Mark Complete, Flag for Review
- Soft-deleted annotation rows are **compacted** (permanently removed) when the source is marked complete or when the file is exported back to the manager

**Keyboard shortcuts:**
- `1-9`: apply code to current selection (matching sidebar order)
- `Ctrl/Cmd+Z`: undo
- `Ctrl/Cmd+Shift+Z`: redo
- `Alt+Left/Right` or configurable: prev/next source
- `Escape`: dismiss popover
- `Ctrl/Cmd+Enter`: mark source complete

## 4. Data Model

All IDs are UUIDs (not autoincrement) to prevent collisions on merge.

```sql
-- Schema version tracking
PRAGMA user_version = 1;
PRAGMA application_id = 0x41434500; -- "ACE\0"

CREATE TABLE project (
    id TEXT PRIMARY KEY,           -- UUID
    name TEXT NOT NULL,
    description TEXT,
    instructions TEXT,             -- project-level coding instructions for coders
    file_role TEXT NOT NULL,       -- 'manager' or 'coder'
    codebook_hash TEXT,            -- SHA-256 of codebook state at export time
    assignment_seed INTEGER,       -- random seed for reproducible assignment
    created_at TEXT NOT NULL,      -- ISO 8601
    updated_at TEXT NOT NULL
);

-- Metadata only (no content_text). Lazy-load content from source_content.
CREATE TABLE source (
    id TEXT PRIMARY KEY,           -- UUID
    display_id TEXT,               -- participant ID from CSV (for display)
    source_type TEXT NOT NULL CHECK (source_type IN ('file', 'row')),
    source_column TEXT,            -- which CSV column this text came from (if multi-column)
    filename TEXT,                 -- original filename or CSV name
    metadata_json TEXT,            -- other CSV columns as JSON object
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- Separate table for structural lazy loading
CREATE TABLE source_content (
    source_id TEXT PRIMARY KEY REFERENCES source(id),
    content_text TEXT NOT NULL,    -- the text to be coded
    content_hash TEXT NOT NULL     -- SHA-256 of content_text (integrity check)
);

CREATE TABLE codebook_code (
    id TEXT PRIMARY KEY,           -- UUID
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    colour TEXT NOT NULL,          -- hex colour, from accessible palette
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE coder (
    id TEXT PRIMARY KEY,           -- UUID
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE assignment (
    id TEXT PRIMARY KEY,           -- UUID
    source_id TEXT NOT NULL REFERENCES source(id),
    coder_id TEXT NOT NULL REFERENCES coder(id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'complete', 'flagged')),
    assigned_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, coder_id)
);

CREATE TABLE annotation (
    id TEXT PRIMARY KEY,           -- UUID (also used as W3C annotation ID)
    source_id TEXT NOT NULL REFERENCES source(id),
    coder_id TEXT NOT NULL REFERENCES coder(id),
    code_id TEXT NOT NULL REFERENCES codebook_code(id),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    selected_text TEXT NOT NULL,    -- denormalised for integrity verification
    memo TEXT,                      -- optional coder justification/note on this annotation
    w3c_selector_json TEXT,         -- full W3C TextQuoteSelector + TextPositionSelector
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT                  -- soft delete for undo support
);

CREATE TABLE source_note (
    id TEXT PRIMARY KEY,           -- UUID
    source_id TEXT NOT NULL REFERENCES source(id),
    coder_id TEXT NOT NULL REFERENCES coder(id),
    note_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, coder_id)
);

-- Indexes
CREATE INDEX idx_annotation_source_coder ON annotation(source_id, coder_id)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_annotation_code ON annotation(code_id);
CREATE INDEX idx_assignment_coder ON assignment(coder_id);
CREATE INDEX idx_assignment_source ON assignment(source_id);
```

### SQLite Configuration

- `PRAGMA foreign_keys = ON` on every connection open
- WAL mode during active editing for performance
- Checkpoint + switch to DELETE mode before export/close (prevents sidecar file loss)
- `PRAGMA integrity_check` on import of returned files
- Warn if `.ace` file is detected in a known cloud-sync directory (Dropbox, OneDrive, iCloud, Google Drive)

### Schema Migration

- `PRAGMA user_version` checked on every file open
- Sequential migration functions: `migrate_v1_to_v2()`, `migrate_v2_to_v3()`, etc.
- Migrations applied automatically on open (after backup prompt)
- Migration runner stubbed from day one, even with no migrations yet
- Content hash verified on coder-side file open (detect corruption in transit)

## 5. Package Exchange Format

### Export (Manager -> Coder)

A coder's `.ace` file is a filtered copy of the main project SQLite database containing:
- `project` table (full, with instructions, `file_role` set to `'coder'`, `codebook_hash` populated)
- `source` + `source_content` tables (only sources assigned to this coder)
- `codebook_code` table (full codebook)
- `coder` table (only this coder)
- `assignment` table (only this coder's assignments)
- `annotation` table (empty — ready to be filled)
- `source_note` table (empty)

Implementation: `ATTACH DATABASE` + `INSERT INTO ... SELECT` for atomic, fast export.

### Import (Coder -> Manager)

**Pre-import:** Auto-backup of main `.ace` file (timestamped copy).

Validation steps (in order):
1. `PRAGMA integrity_check` — reject corrupted files
2. Verify `application_id` matches ACE
3. Verify `user_version` (schema version) is compatible
4. Verify `file_role` = `'coder'` (reject manager files)
5. Verify `project.id` matches the main project (clear error if wrong project)
6. For each source: verify `content_hash` matches main project (detect text modification)
7. Codebook hash comparison: if changed, warn user but allow import (annotations reference code UUIDs which are stable; deleted codes in main project are re-inserted from coder file before annotation import)

Import process:
1. Open returned `.ace` file as read-only
2. Begin transaction on main project database
3. For annotations: **UPSERT by UUID** — if annotation UUID exists, compare `updated_at` and keep the newer version. If new UUID, insert. Skip rows where `deleted_at IS NOT NULL`.
4. Copy all source_notes into main project (UPSERT by source_id + coder_id)
5. Update assignment statuses
6. Commit transaction (atomic — all or nothing)

### Robustness

- Double-import safe: UPSERT by UUID, newer version wins
- Codebook drift: deleted codes re-inserted from coder file; new codes in main project are not affected
- Partial completion supported: import whatever the coder finished
- Late annotations (coder submits after initial import): new UUIDs are inserted, updated UUIDs get newer version
- Never interpolate values from imported files into SQL strings (prevent injection from crafted files)

## 6. Inter-Coder Reliability

### Method: Character-Level Binary Agreement (v1)

For each source assigned to multiple coders:

1. For each code, create a **per-code binary vector** over character positions: 1 if the coder applied that code to that character, 0 if not
2. **Filter** to only character positions where at least one coder applied at least one code (avoid inflating agreement with uncoded characters). Document this caveat for users: systematic omissions are invisible to the metric.
3. Compute **per-code agreement**: for code X, compare binary vectors across coders using Cohen's kappa (2 coders) or Fleiss' kappa (3+ coders, though v1 overlap is pairwise)
4. Compute **overall agreement**: macro-average of per-code kappa values across all codes
5. Also report: Krippendorff's alpha, percent agreement per code
6. Multi-code spans: handled naturally — each code has its own binary vector, so a character with codes {X, Y} from Coder A and code {X} from Coder B is agreement on X, disagreement on Y

**Implementation:** Sweep-line algorithm — iterate annotation spans and increment/decrement code counters at boundaries. O(annotations) rather than O(characters * coders * codes).

### Offset Normalisation

JavaScript (Recogito) uses UTF-16 code units. Python uses Unicode code points. Non-BMP characters (emoji, some CJK) cause offset mismatches.

**Solution:** Normalise all offsets to Python code points at the JS/Python boundary. On annotation save, convert JS UTF-16 offsets to Python code point offsets before storing. On annotation load, convert back. **Test with emoji text in week 1.**

### ICR Dashboard

- Summary table: one row per code, columns for kappa, alpha, percent agreement
- Overall project agreement (macro-average across codes)
- Disagreement viewer: for each overlapping source, show side-by-side annotations from each coder with the text
- Adjudication controls: accept Coder A / accept Coder B / create consensus (attributed to virtual "consensus" coder). Rejected annotations flagged, not deleted.
- Export ICR report to CSV
- Progress indicator during computation (sweep-line is fast, but show progress for large projects)

## 7. Accessibility

- Colour-blind accessible default palette (Okabe-Ito or ColorBrewer qualitative)
- Text labels always visible alongside colours (sidebar + annotation tooltips)
- Full keyboard navigation (Tab between panels, shortcuts for all actions)
- Touch targets minimum 44x44px in popovers
- `aria-label` on annotated spans describing applied code(s)
- Progress in `aria-live` region
- Annotation create/remove: brief visual animation (150ms fade) for feedback

## 8. Performance Considerations

- Bulk CSV import wrapped in single transaction (not one INSERT per row)
- Lazy-load source content — `source_content` table split from `source` (structural, not convention-based)
- ICR computation: sweep-line algorithm, run in background thread, results cached, progress indicator shown
- WAL mode during editing for fast writes; checkpoint on close/export
- Virtual scrolling for document lists exceeding ~100 items (Quasar table supports this)
- Test Recogito rendering with 200+ annotations on a single long text early (week 1 spike)
- Auto-save fires on every Recogito annotation event (negligible SQLite write latency locally)

## 9. v1 Scope Summary

### In scope
- CSV/Excel import with column selection (incl. multi-column, encoding detection)
- Folder of .txt files import
- Flat codebook (name, colour, description) with import from CSV
- Project-level coding instructions
- Random assignment with configurable ICR overlap % (pairwise, reproducible seed)
- Coder package export/import (.ace files)
- Span-level text annotation (highlight-then-pick-code)
- Multi-code on same span (overlapping annotations)
- Keyboard shortcuts (1-9 for codes)
- Document list with completion status + jump-to
- Coder notes per source
- Flag for Review status on sources
- Code descriptions on hover
- Instructional overlay for first-time coders
- Merge with validation, preview, and auto-backup
- Character-level ICR (per-code binary kappa, macro-averaged overall, Krippendorff's alpha)
- Disagreement adjudication (accept/reject/consensus)
- Data export to CSV/Excel (annotations + ICR report)
- Undo/redo (per-source, in-memory)
- Auto-save on every annotation event
- Colour-blind accessible palette
- UUIDs for all entities
- Schema versioning with migration runner
- Cloud-sync directory warning
- Manager/coder file role detection

### Deferred to v2+
- Hierarchical codes
- REFI-QDA import/export
- Manual assignment (drag-and-drop)
- Stratified random assignment (by metadata)
- AI-assisted coding
- Audio/video/image coding
- Memos/journals (beyond per-source notes)
- Search/query across annotations
- Annotation audit trail
- Practice document for onboarding
- Krippendorff's alpha-unitised (alpha-U)
- Server mode for shared hosting
- File association / native desktop packaging
- Keyboard shortcuts beyond 9 codes

## 10. Technical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Recogito integration with NiceGUI | High | Spike test in week 1: init on `ui.html()`, receive events in Python, round-trip 50+ annotations, test undo sync. Fallback: FastAPI + React. |
| UTF-16 / Unicode offset mismatch | High | Normalisation layer at JS/Python boundary. Test with emoji text in week 1. |
| Overlapping annotation rendering | Medium | Spike test Recogito's default rendering. Fallback: CSS Custom Highlight API. |
| WAL sidecar file loss | Medium | Checkpoint on close/export. Warn if file in cloud-sync directory. |
| Large annotation count rendering | Medium | Test with 200+ annotations early. Virtual scrolling if needed. |
| Span-level ICR validity | Medium | Document method clearly. Character-level is well-established in NLP. Caveat about filtered uncoded characters. |
| Codebook drift between export and import | Medium | Lock code deletion after export. Re-insert deleted codes from coder file on import. |
| irrCAC API stability | Low | Pin version. Library is mature. |

## 11. Open Questions

1. App name: is "ACE" final? Check for conflicts with existing packages on PyPI.
2. File extension: `.ace` — check for conflicts with other tools.
3. Recogito v3 (`@recogito/text-annotator`) vs older `recogito-js` — spike test needed. v3 has a different API (Annotorious 3.x family).
4. NiceGUI native mode (`ui.run(native=True)`) vs browser-only — test on target platforms.
5. How to handle Recogito state vs SQLite state sync — Recogito owns annotation state during editing, persisted to SQLite on each event. Dirty indicator if save fails.
