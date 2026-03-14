# Inter-Coder Agreement Dashboard

## Overview

A read-only agreement reporting tool that loads multiple `.ace` files, computes inter-coder reliability metrics, and presents results in a publication-ready dashboard with CSV export.

Each coder works independently on their own `.ace` file (same sources, same codebook). When it's time to assess agreement, a researcher loads the coder files into the `/agreement` page, computes metrics, reviews the dashboard, and exports results. No data is persisted — it's a stateless comparison tool.

## Architecture: Approach A (Thin Page, Fat Service)

Follows ACE's existing pattern: services for logic, pages for UI, models for data.

### New Files

- `src/ace/services/agreement_loader.py` — opens .ace files, extracts and matches data
- `src/ace/services/agreement_computer.py` — computes all metrics from matched data
- `src/ace/pages/agreement.py` — `/agreement` route, dashboard UI
- `src/ace/static/css/agreement.css` — dashboard-specific styles (`ace-heatmap` and related classes)
- `tests/test_services/test_agreement_loader.py`
- `tests/test_services/test_agreement_computer.py`

### Modified Files

- `src/ace/pages/landing.py` — add "Check Agreement" button
- `src/ace/app.py` — import and register agreement page route
- `src/ace/static/css/theme.css` — add `ace-metric` and `ace-metric-hero` classes
- `pyproject.toml` — add `krippendorff` dependency, bump `irrCAC` from >=0.3 to >=0.4

### Relationship to Existing `icr.py`

The existing `icr.py` computes Cohen's kappa for 2 coders within a single .ace file using assignment-based overlap detection and hardcoded 2-coder keys. It is currently unused (not imported anywhere in `src/`). The new `AgreementComputer` generalises to N coders across multiple files using annotation-based scoping. The vector-building logic in `icr.py` (lines 87-128) is tightly coupled to its 2-coder assumption and will require a new N-coder interface rather than trivial extraction. The existing `icr.py` can be left as-is or deprecated once the new services are complete.

---

## Data Flow

```
User adds .ace files on /agreement page
        |
        v
AgreementLoader
  - Opens each file read-only (sqlite3 ?mode=ro, URI mode)
  - Warns if WAL files exist alongside the .ace file
  - Extracts: sources, codebook codes, coders, annotations
  - Matches sources across files by content_hash ONLY
    (display_id used only to disambiguate when multiple sources
    share the same hash within a file)
  - Uses codebook_hash as fast-path check; falls back to
    code name matching when hashes differ
  - Each (file, coder) pair treated as a distinct coder identity
  - Auto-validates inline as each file is added
  - Returns AgreementDataset dataclass
        |
        v
AgreementComputer
  - Takes AgreementDataset
  - Scopes to sources with annotations from 2+ coders
    (by annotation presence, not assignment status)
  - Builds character-level binary vectors per code per coder
    (existing approach from icr.py, filtered to positions
    where at least one coder applied at least one code)
  - Computes all metrics at per-code, per-source, and
    pairwise-coder granularity
  - Returns AgreementResult dataclass
        |
        v
/agreement page renders dashboard + CSV export
```

---

## Source Matching Strategy

**Primary key:** `content_hash` (SHA256 of content_text, already stored in `source_content` table).

- Content hash guarantees identical text, which is required for character-level offset alignment.
- **No display_id fallback.** If display_ids match but content differs, character offsets are meaningless and agreement scores would be silently wrong.
- Display_id is used only as a disambiguator when multiple sources within a single file share the same content_hash.
- Sources that exist in some files but not others are excluded from comparison and reported as warnings.
- Partial overlap is supported — the comparison proceeds on the intersection of sources across all files.

## Code Matching Strategy

- **Fast path:** Compare `codebook_hash` from the `project` table across all files. If identical, codebooks were cloned from the same source (e.g., via `packager.py`) — use code IDs directly, skip name matching. Note: `codebook_hash` includes code UUIDs, so independently-created codebooks with identical names/colours will always have different hashes and fall through to the slow path.
- **Slow path:** When hashes differ (codes added/removed/renamed after export, or independently-created codebooks), match by `name` (which is UNIQUE within a file). Unmatched codes are excluded and reported as warnings.

## Coder Identification

- Each `(file, coder_name)` tuple is a distinct coder identity.
- If coder names are ambiguous (e.g., multiple files have a coder named "default"), auto-label as "Coder 1", "Coder 2", etc., derived from filename.
- A single file with multiple coders is supported (e.g., a merged manager file). The loader enumerates all `(file, coder)` pairs.

## Read-Only SQLite Access

- Open with `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` — matching the existing pattern in `packager.py`.
- If a `-wal` file exists alongside the `.ace` file, warn the user the file may have uncommitted changes.
- Close connections promptly after extracting data.

---

## Intermediate Data Structures

```python
@dataclass
class MatchedSource:
    content_hash: str
    display_id: str
    content_text: str

@dataclass
class CoderInfo:
    id: str           # unique across the comparison
    label: str         # display name (coder name or "Coder N")
    source_file: str   # path to the .ace file

@dataclass
class MatchedCode:
    name: str
    present_in: set[str]  # set of coder IDs that have this code

@dataclass
class MatchedAnnotation:
    source_hash: str   # content_hash of the source
    coder_id: str      # CoderInfo.id
    code_name: str     # MatchedCode.name
    start_offset: int
    end_offset: int

@dataclass
class AgreementDataset:
    sources: list[MatchedSource]
    coders: list[CoderInfo]
    codes: list[MatchedCode]
    annotations: list[MatchedAnnotation]
    warnings: list[str]

@dataclass
class CodeMetrics:
    percent_agreement: float
    cohens_kappa: float | None
    krippendorffs_alpha: float | None
    fleiss_kappa: float | None
    congers_kappa: float | None
    gwets_ac1: float | None
    brennan_prediger: float | None
    n_positions: int  # number of character positions evaluated

@dataclass
class AgreementResult:
    overall: CodeMetrics
    per_code: dict[str, CodeMetrics]        # code_name -> metrics
    per_source: dict[str, CodeMetrics]      # display_id -> metrics
    pairwise: dict[tuple[str, str], float]  # (coder_id, coder_id) -> alpha
    n_coders: int
    n_sources: int
    n_codes: int
```

---

## Metrics

### Always Computed

| Metric | Library | When Shown |
|--------|---------|------------|
| Percent agreement | Built-in | Always |
| Cohen's kappa | `scikit-learn` | 2 coders |
| Fleiss' kappa | `irrCAC` | 3+ coders |
| Krippendorff's alpha | `krippendorff` | Always |
| Gwet's AC1 | `irrCAC` | Toggle "Show all metrics" |
| Brennan-Prediger | `irrCAC` (via `bp()`) | Toggle "Show all metrics" |
| Conger's kappa | `irrCAC` (via `conger()`) | Toggle "Show all metrics" |

### Contextual Display Logic

- 2 coders: show Cohen's kappa in primary section, hide Fleiss'/Conger's kappa
- 3+ coders: show Fleiss' kappa in primary section, hide Cohen's kappa
- "Show all metrics" toggle reveals all computed metrics regardless of coder count

### Character-Level Computation

Reuses the existing approach from `icr.py`:
1. For each matched source, build a binary vector of length `len(content_text)` per code per coder
2. Filter to positions where at least one coder applied at least one code (avoids inflating agreement on uncoded passages)
3. Aggregate vectors across sources per code for per-code metrics
4. Aggregate all vectors per source for per-source metrics
5. Feed vectors into each metric's computation function

---

## Page Layout

### Entry Point

"Check Agreement" button on the landing page, alongside existing "New Project" and "Open Project".

### Route

`/agreement` — registered in `agreement.py` via `register()`, called from `app.py` (matching existing pattern for landing, import, and coding pages).

### Header

Uses `build_header()` with no project-specific arguments (like the landing page when no project is open).

### File Selection Mechanism

Since ACE runs as a local desktop app (localhost:8080), use the native macOS file picker (`osascript`) for `.ace` file selection — matching the existing pattern in `landing.py` (`_native_pick_file()`). The picker needs to accept multiple file selection. This avoids uploading/copying SQLite files and works directly with file paths. For future cross-platform support, `ui.upload()` can be added as a fallback.

### Page Structure

#### Setup Area (top, always visible)

- File picker / drop zone: "Drop .ace files here or click to browse"
- File list showing: coder name (prominent), filename (secondary), source count, annotation count, remove button per file
- Inline validation panel (updates as files are added):
  - Green check: "N sources matched across all files"
  - Amber warning: "N sources found in only some files" (expandable)
  - Amber warning: "N codes found in only some files"
  - Red block: "No overlapping sources" or "No shared codes"
  - Informational: "Coders: Alice, Bob, Carol"
- "Compute Agreement" button — greyed out until 2+ files with valid overlap
- After computation: collapses to summary line ("3 files, 2 coders, 45 sources") with "Edit" to re-expand

#### Results Area (tabs, shown after computation)

**Tab 1: Overview**

- Hero card (full width):
  - Krippendorff's alpha as large monospace number (`ace-metric-hero` class)
  - Verbal label: "Substantial" (Landis & Koch scale)
- Two smaller cards in a row:
  - Cohen's kappa (2 coders) or Fleiss' kappa (3+ coders)
  - Percent agreement
- Metadata line (caption text): "Computed across N sources, N codes, N coders"
- Per-code table:
  - Toolbar: section label "Agreement by Code" | "Show all metrics" toggle | "Export CSV" button
  - Default columns: Code Name | % Agreement | K. Alpha | Kappa
  - Toggled columns: + AC1 | B-P | (others)
  - Low-agreement rows: amber background (`#fff3e0`) + warning icon
  - Sortable by any column
- "Copy methods paragraph" button:
  - Generates: "Inter-coder reliability was assessed using Krippendorff's alpha (alpha = 0.82) and Cohen's kappa (kappa = 0.79) across 2 coders and 45 source texts. Per-code agreement ranged from kappa = 0.65 to kappa = 0.94."

**Tab 2: Pairwise (hidden for 2 coders)**

- CSS heatmap table rendered via `ui.html(sanitize=False)`:
  - Coders on both axes
  - Cells show pairwise Krippendorff's alpha
  - Blue gradient: white (#ffffff) to blue (#1565c0)
  - Text colour: dark on light cells, white on dark cells
  - Dashed border on cells below agreement threshold
- Class: `ace-heatmap` in agreement.css

**Tab 3: Per Source**

- Sortable table: Source ID | % Agreement | K. Alpha | Kappa | Annotations per coder
- Default sort: lowest agreement first (find problem sources)
- Click row to expand inline:
  - Source text with annotations overlaid (read-only)
  - Each coder's annotations shown in distinct colours
  - Reuses existing annotation rendering from coding.py/bridge.js

#### Empty State (before files loaded)

- Centred icon (`compare_arrows`, grey-4) + heading + instruction text
- "Add two or more .ace project files to compare annotations and compute agreement metrics."

---

## Visual Design

Extends existing ACE theme — no new visual elements.

- Flat, sharp corners, no box shadows
- White cards with `1px solid #d0d0d0` borders
- Backgrounds: `#f5f5f5` for table headers and heatmap header cells
- Monospace numbers: new `ace-metric` class (`SF Mono`, `Menlo`, `Consolas`)
- Hero number: `ace-metric-hero` (2.5rem, bold, tight letter-spacing)
- Page max-width: `1100px`, centred
- Only colour in results: blue heatmap gradient + amber (`#fff3e0`) for low-agreement rows
- Colourblind safe: shape + colour for all indicators (warning icon + amber, dashed border + light cell)
- Abbreviated column headers when "show all metrics" active, full names in tooltips

### New CSS Classes

In `theme.css` (reusable across pages):

```css
.ace-metric {
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 0.875rem;
}
.ace-metric-hero {
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 2.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}
```

In `agreement.css` (dashboard-specific):

```css
.ace-heatmap {
    border-collapse: collapse;
    width: 100%;
    max-width: 600px;
}
.ace-heatmap th, .ace-heatmap td {
    border: 1px solid #d0d0d0;
    padding: 8px 12px;
    text-align: center;
    font-size: 0.875rem;
}
.ace-heatmap th {
    background: #f5f5f5;
    font-weight: 500;
    color: #616161;
}
```

---

## Export

### CSV Exports

1. **Per-code metrics CSV** — one row per code:
   - Columns: code_name, n_positions, percent_agreement, cohens_kappa, krippendorffs_alpha, fleiss_kappa, gwets_ac1, brennan_prediger, congers_kappa
   - Header comment row with metadata: files compared, date, coder names, N sources

2. **Per-source metrics CSV** — one row per source:
   - Columns: source_display_id, percent_agreement, krippendorffs_alpha, kappa, n_annotations_per_coder (one column per coder)

### Methods Paragraph

"Copy to clipboard" button generates a publication-ready sentence summarising the key metrics, coder count, and source count. Uses the primary metrics (alpha + kappa) and per-code range.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `krippendorff` | >=0.7 | Krippendorff's alpha — standalone package preferred over irrCAC's implementation for verified accuracy against Hayes & Krippendorff (2007) and configurable distance functions |
| `irrCAC` | >=0.4 (existing, bump from >=0.3) | Gwet's AC1, Fleiss' kappa, Conger's kappa, Brennan-Prediger (`bp()` requires >=0.4). Note: `irrCAC.raw.CAC` expects a pandas DataFrame (raters as columns, subjects as rows) |
| `scikit-learn` | (existing) | Cohen's kappa |

---

## Error Handling

| Scenario | Detection | Severity | Message |
|----------|-----------|----------|---------|
| Invalid .ace file | On upload (check application_id) | Blocking (that file) | "'notes.sqlite' is not a valid ACE project file." |
| WAL file exists | On upload (check filesystem) | Warning | "This file may have uncommitted changes. Close ACE on this file first." |
| No overlapping sources | Validation | Blocking | "These files share no source texts. Are they from the same project?" |
| Partial source overlap | Validation | Warning | "3 of 5 sources match. Agreement will be computed on matched sources only." |
| No shared codes | Validation | Blocking | "These files share no codes. Agreement cannot be computed." |
| Partial code overlap | Validation | Warning | "8 of 12 codes match. Unmatched codes will be excluded." |
| No annotations in a file | Validation | Blocking (that file) | "'alice.ace' has no annotations." |
| Same coder name across files | Validation | Warning | Auto-relabel as "Coder 1", "Coder 2", etc. |
| Only 1 file added | Validation | Informational | "Add at least one more coder file." |

---

## Performance Considerations

Character-level binary vectors create O(codes x text_length x sources) memory usage. For typical qualitative datasets (50 sources, 5,000 chars each, 20 codes, 3 coders) this is ~15M integers — negligible. For larger datasets, consider switching from Python lists to numpy arrays. The `irrCAC` library expects a pandas DataFrame, so the character-level vectors need to be assembled into rater-column format before being passed to its API.

---

## Future Extensions (Not In Scope)

- **Merge .ace files** into a single project (uses the same AgreementLoader, adds a write step)
- **Gamma metric** (Mathet 2015) via `pygamma-agreement` for true unitizing reliability
- **Disagreement resolution** (MAXQDA-style "adopt coder 1's solution")
- **Configurable overlap threshold** for fuzzy boundary matching
- **Confidence intervals** on kappa/alpha values
- **Training/test mode** (Dedoose-style iterative calibration)
