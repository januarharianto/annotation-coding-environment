# Inter-Coder Agreement Overhaul

**Date:** 2026-04-01
**Branch:** `feat/agreement-overhaul`

## Overview

Replace the current multi-step agreement page (add files → compute → dashboard with metric cards) with a streamlined flow: click tool → file picker → auto-compute → results page. Fix the Overall metric computation (pooled, not macro-averaged). Add a raw data export for reproducibility in R/Python. Minimalist presentation — tables and text only, no cards or panels. Bib-backed references section.

## Flow

```
Landing page → click "Inter-Coder Agreement" → empty state with "Choose files" button
→ native file picker (select 2+ .ace files) → auto-compute → results page
```

Show an empty state: "Select 2 or more .ace files to compute agreement" with a prominent "Choose files" button. Do NOT auto-open the file picker on page load — this is jarring on accidental navigation and may be blocked by browsers.

## Results Page Layout

Top to bottom:

1. **Back link** — `← Home`
2. **Title + export buttons** — "Inter-Coder Agreement" on left, pill-style download buttons on right: `↓ Summary CSV` and `↓ Raw data CSV`
3. **Context bar** — `3 coders · 45 of 50 sources · 8 of 10 codes` + "Choose different files" link
4. **Collapsible warnings** — `<details>` element, hidden by default. Shows unmatched sources/codes per file. Not rendered when no warnings.
5. **Metrics table** — single table with per-code rows and pooled Overall row at bottom
6. **Pairwise table** — flat list, one row per coder pair (not a matrix). Hidden for 2 coders (identical to overall). Sorted by α descending.
7. **References** — numbered list from bib file, superscript markers on column headers

## Title + Export Buttons

```
Inter-Coder Agreement                    [↓ Summary CSV]  [↓ Raw data CSV]
```

- Title: `font-size: 18px`, `font-weight: 700`
- Buttons: grey pill style — `background: #f1f5f9; border: 1px solid #e2e8f0; color: #334155; border-radius: 4px; font-size: 11px; font-weight: 500; padding: 4px 12px`
- `↓` prefix signals download action
- Buttons hover: `background: #e2e8f0`
- Both buttons use the HTML5 `download` attribute and `aria-label` (e.g. `aria-label='Download summary as CSV file'`)

## Context Bar

Plain text, not a card:

```
3 coders · 45 of 50 sources · 8 of 10 codes          Choose different files
```

- Left: coder count, source counts ("N of M" format showing matched/total), code counts (same)
- Right: "Choose different files" link — re-opens the file picker, replaces the current results
- Styled: `--ace-font-size-sm`, `--ace-text-muted`, separator dots `·`, bold numbers
- Border-bottom: `1px solid var(--ace-border)`

## Collapsible Warnings

Uses `<details>` / `<summary>`:

- **Summary text** (always visible): `⚠ 5 sources and 2 codes not shared across all files`
- **Styled:** summary in `#92400e` (passes WCAG AA at 4.7:1 on white)
- Warning emoji is `aria-hidden='true'` with a visually hidden "Warning:" prefix for screen readers. Summary text colour: `#92400e` (passes WCAG AA at 4.7:1 on white).
- **Expanded content:** per-file breakdown — "Sources only in Sarah.ace: Interview_48, Interview_49" etc.
- **Background:** `#fffbeb` with `#fde68a` border
- **Not rendered** when all sources and codes match (no `<details>` element at all)

## Metrics Table

Single table, all 7 metrics visible. No toggle, no hidden columns. Column headers have superscript reference numbers linking to the references section.

### Columns

| Column | Header | Emphasis | Notes |
|--------|--------|----------|-------|
| Code name | Code | Dark | Left-aligned |
| Percent agreement | % | Dark (primary) | Right-aligned, 1 decimal. Ref [1] |
| Krippendorff's alpha | α | Dark (primary) | Right-aligned, 2 decimals. Interpretation label below number. Ref [2] |
| Kappa | κ | Dark (primary) | Cohen's for 2 coders (header: "Cohen κ", ref [3]), Fleiss for 3+ (header: "Fleiss κ", ref [4]) |
| Gwet's AC1 | AC1 | Muted (`#757575`) | Right-aligned, 2 decimals. Ref [6] |
| Conger's kappa | Conger | Muted | Right-aligned, 2 decimals. Ref [5] |
| Brennan-Prediger | B-P | Muted | Right-aligned, 2 decimals. Ref [7] |
| Source count | sources | Muted | Number of sources where at least one coder applied this code |

### Interpretation labels

Each α value has a small muted verbal label below the number (same cell), using the Landis & Koch (1977) scale [8]:

| α range | Label |
|---------|-------|
| < 0.00 | poor |
| 0.00–0.20 | slight |
| 0.21–0.40 | fair |
| 0.41–0.60 | moderate |
| 0.61–0.80 | substantial |
| 0.81–1.00 | almost perfect |

Format: number on first line (`0.62`), label on second line in small muted text (`substantial`). Uses `display: block` so the number column stays aligned via `font-variant-numeric: tabular-nums`.

### Overall row

- **Position:** Last row of the table, separated by a thicker top border (2px)
- **Styling:** Bold text, light grey background (`--ace-bg-muted`)
- **Label:** "Overall (pooled)"
- **Computation:** Pooled across all codes — compute each metric once on the combined character-level vectors, NOT macro-averaged per-code

### Visual styling

- Table font: `--ace-font-size-sm` (12px)
- Numbers: `font-variant-numeric: tabular-nums` for alignment
- Primary columns (%, α, κ): `var(--ace-text)` colour
- Secondary columns (AC1, Conger, B-P, sources): `#757575` colour
- Row borders: `1px solid var(--ace-border-light)`
- Overall row border-top: `2px solid var(--ace-border)`
- Header row border-bottom: `2px solid var(--ace-border)`
- Tables wrapped in `<div style='overflow-x: auto'>` for horizontal scroll on narrow screens
- Code/Pair column uses `position: sticky; left: 0; background: var(--ace-bg)` so the row header stays visible during horizontal scroll
- All `<th>` elements have `scope='col'` or `scope='row'`. Code name cells are `<th scope='row'>`
- Both tables have a `<caption>` element (can be visually hidden)
- Light horizontal rules only — no vertical rules, no zebra striping (per Tufte)
- A subtle increased gap between the primary column group (%, α, κ) and secondary group (AC1, Conger, B-P, sources) to avoid relying on colour alone as differentiator

## Pairwise Table

Flat list — one row per coder pair. Always visible for 3+ coders. Hidden for 2 coders (pairwise = overall, no extra information).

### Columns

| Column | Header | Emphasis | Notes |
|--------|--------|----------|-------|
| Pair | Pair | Dark | "Sarah ↔ Mike" format |
| Percent agreement | % | Dark (primary) | Ref [1] |
| Krippendorff's alpha | α | Dark (primary) | With interpretation label. Ref [2] |
| Cohen's kappa | Cohen κ | Muted | Ref [3] |
| Gwet's AC1 | AC1 | Muted | Ref [6] |

Section label above table: `PAIRWISE AGREEMENT` in uppercase muted small text.

Sorted by α descending (best pairs first, problematic pairs at bottom). Low α values (below 0.60) highlighted in orange (`#9a3412`, passes WCAG AA at 6.4:1).

## Exports

### 1. Summary CSV (existing endpoint, updated)

Per-code metrics table as CSV, plus Overall row.

Columns: `code, percent_agreement, krippendorffs_alpha, cohens_kappa, fleiss_kappa, congers_kappa, gwets_ac1, brennan_prediger, n_sources, n_positions`

Includes a comment header row with metadata: date, file names, coder labels, source count, code count.

### 2. Raw Data CSV (new)

Long-form span-level export. One row per annotation across all loaded files.

Columns: `source_id, start_offset, end_offset, coder_id, code_name`

This format is:
- Directly loadable into NLTK's `AnnotationTask` as `(coder_id, source_id+offset, code_name)` triples
- One `pivot_wider(names_from=coder_id, values_from=code_name)` away from R's irrCAC format (units × raters)
- One pivot + transpose from Python's `krippendorff.alpha()` format (raters × units)
- Compatible with R's `irr`, `irrCAC`, `krippendorffsalpha`, `rel` packages and Python's `krippendorff`, `sklearn.metrics`

Includes a comment header row with metadata (same as summary CSV).

## References Section

Numbered list at the bottom of the page, styled small and muted. Sourced from `src/ace/static/agreement_references.bib` at build/render time.

Superscript markers on column headers (e.g. `α²`) link visually to the numbered list. Not clickable anchors — just visual correspondence. Superscript numbers are `aria-hidden='true'` with a visually hidden full citation for screen readers (e.g. `<span class='visually-hidden'>(Krippendorff, 2011)</span>`).

### Reference entries

1. Holsti (1969). *Content Analysis for the Social Sciences and Humanities.* Addison-Wesley.
2. Krippendorff (2011). Computing Krippendorff's alpha-reliability. *Annenberg School for Communication Departmental Papers, 43.*
3. Cohen (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement, 20*(1), 37–46.
4. Fleiss (1971). Measuring nominal scale agreement among many raters. *Psychological Bulletin, 76*(5), 378–382.
5. Conger (1980). Integration and generalization of kappas for multiple raters. *Psychological Bulletin, 88*(2), 322–328.
6. Gwet (2008). Computing inter-rater reliability and its variance in the presence of high agreement. *British Journal of Mathematical and Statistical Psychology, 61*(1), 29–48.
7. Brennan & Prediger (1981). Coefficient kappa: Some uses, misuses, and alternatives. *Educational and Psychological Measurement, 41*(3), 687–699.
8. Landis & Koch (1977). The measurement of observer agreement for categorical data. *Biometrics, 33*(1), 159–174.

## States

### Empty state (default on page load)
Centred message: "Select 2 or more .ace files to compute agreement" with a prominent "Choose files" button below. No auto-opening of the file picker.

### Loading state
Replaces empty state while computing: "Computing agreement..." with a subtle animation. `<div role="status" aria-live="polite">`.

### Error state
Shown if computation fails (e.g. no overlapping sources, corrupt file). Clear error message with specific guidance and a "Choose different files" button.

### Results state
The full results page as described above. "Choose different files" link in the context bar allows restarting.

## Computation Changes

### Pooled Overall (replaces macro-average)

Current `_macro_average()` computes an unweighted mean of per-code coefficients. Replace with: pool all character-level binary vectors across codes into one combined dataset, then compute each metric once on the pooled data.

### n_sources per code

New metric: count of source documents where at least one coder applied this code. Add to `CodeMetrics` dataclass alongside existing `n_positions`. Display this in the table instead of `n_positions`.

### Kappa column logic

- 2 coders: show Cohen's kappa, column header "Cohen κ"
- 3+ coders: show Fleiss kappa, column header "Fleiss κ"
- The non-applicable metric is still computed (if possible) and included in the CSV, just not displayed

### Pairwise computation

For each coder pair, compute: percent agreement, Krippendorff's α, Cohen's κ, Gwet's AC1. Pool across all codes for each pair.

## Template / Route Changes

### Route: GET /agreement

- Page renders with an empty state: centred message "Select 2 or more .ace files to compute agreement" and a prominent "Choose files" button
- Clicking "Choose files" triggers the native file picker
- If user cancels the picker, the empty state remains (no change)
- If user selects files, auto-submit to the compute endpoint
- While computing, show a loading indicator with `role="status"` and `aria-live="polite"`
- If computation fails (no overlapping sources, corrupt file), show an inline error with "Choose different files" action
- Results render on the same page (no separate results URL)

### Route: POST /api/agreement/compute

- Accepts file paths (from picker)
- Loads files, validates matches, computes agreement
- Returns full HTML results (title bar + context + warnings + table + pairwise + references)
- Renders into `#agreement-results` div

### Route: GET /api/agreement/export/results (existing, updated)

- Updated CSV columns (add n_sources, add Overall row, add metadata header)

### Route: GET /api/agreement/export/raw (new)

- Returns the long-form span-level CSV
- Downloads as `agreement_raw_data.csv`

### "Choose different files" link

- Re-opens the native file picker
- On new selection: clears current results, re-computes, re-renders

## Files Affected

- `src/ace/templates/agreement.html` — rebuild template
- `src/ace/static/css/agreement.css` — update styles (table, context bar, export buttons, references)
- `src/ace/static/agreement_references.bib` — already created, read at render time
- `src/ace/routes/api.py` — update compute endpoint HTML rendering, add raw export endpoint, update summary export
- `src/ace/services/agreement_computer.py` — add pooled overall computation, add n_sources per code, add pairwise metrics
- `src/ace/services/agreement_types.py` — add `n_sources` to `CodeMetrics`, update pairwise result type
- `tests/` — update agreement tests

## Scope Boundaries

### In scope

- Auto-compute flow (file picker → results)
- Minimalist results page (tables and text only)
- Title bar with prominent export pill buttons
- Pooled Overall computation (replaces macro-average)
- n_sources metric per code
- Interpretation labels (Landis & Koch)
- Collapsible warnings
- Pairwise as flat list (not matrix), with %, α, Cohen κ, AC1
- Raw data CSV export (long-form span-level)
- Updated summary CSV export with metadata header and Overall row
- Kappa column logic (Cohen vs Fleiss based on coder count)
- Bib-backed references section with superscript markers
- Low α values highlighted in orange in pairwise table

### Out of scope

- Confidence intervals / standard errors (future enhancement)
- Prevalence / bias diagnostics (future)
- Per-source breakdown table (future — data is computed but not displayed)
- "Copy methods paragraph" feature (future)
- PABAK computation (future)
- Per-coder annotation count diagnostics (future)
- Colour-tinted heatmap matrix (replaced by flat list)
