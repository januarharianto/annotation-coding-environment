# Changelog

## 0.10.0

### Features

- **Keyboard-centric sidebar** — ARIA treeview with roving tabindex, arrow key navigation, Tab zone cycling (text → header → search → tree), Enter to apply codes, F2 to rename, Alt+arrows to indent/reorder, drag-and-drop for codes and groups
- **Top bar redesign** — ACE wordmark with subtitle over sidebar column, source name centred over text panel, clickable flag toggle with toast feedback, ? help button
- **Agreement overhaul** — streamlined flow (choose files → auto-compute → results), pooled overall computation, expanded pairwise metrics, minimalist tables with interpretation labels, bib-backed references, raw data CSV export for R/Python reproducibility
- **Codebook CSV import** — "Codebook ▾" sidebar menu with Import/Export, native file picker, sidebar-style preview dialog with new/exists badges, empty state link
- **Apply codes from sidebar** — click a code row or Enter on first search match to apply to focused sentence, with filter auto-clear and focus return

### Fixes

- CapsLock keyboard shortcut compatibility
- Focus restoration across HTMX sidebar swaps
- Search bar events bubble correctly for document-level listeners
- Flag toggle preserves header focus state across OOB swaps
- Agreement Overall metric now pooled (was misleading macro-average)

## 0.9.0

### Features

- **Codebook CSV import** — sidebar menu, native file picker, preview dialog
- **Apply codes from sidebar** — click code row, Enter on first search match, filtered ↓ navigation fix

## 0.8.0

### Features

- **Inter-coder agreement overhaul** — streamlined choose-files → auto-compute → results flow, pooled overall, expanded pairwise metrics, minimalist tables with interpretation labels, raw data CSV export, bib-backed references

## 0.7.0

### Features

- **Top bar redesign** — ACE wordmark with subtitle, source name centred, clickable flag toggle, ? help button

## 0.6.0

### Features

- **Keyboard-centric sidebar** — ARIA treeview with roving tabindex, arrow key navigation, Tab zone cycling, keyboard tree operations
- **Focus underline** — simple underline for focused sentence (no outline box)
- **Text panel** — 72ch max-width, centred

## 0.5.0

### Features

- **Bottom code bar** — sticky bar showing applied codes as coloured text chips with flash-highlight on click
- **Simplified sidebar** — single collapsible tree view, removed tabs
- **Source nav** — moved into text panel as breadcrumb line
- **Font size bump** — 10px→11px, 11px→12px for accessibility
- **Sidebar width** — saved and restored before CSS loads (no layout glitch)

## 0.4.0

### Features

- **CSS Custom Highlight API** — seamless cross-sentence annotation highlights
- **Margin panel** — positioned annotation cards with overlap grouping and click-flash
- **Centred navigation** — nav cluster centred in header bar

## 0.3.0

### Features

- **Highlighter-pen backgrounds** — seamless merged highlights replacing underlines
- **Resume last source** — coding page reopens to last viewed source

## 0.2.0

### Features

- **Direct manipulation** — inline rename (double-click), click-dot colour picker, drag-and-drop reorder via SortableJS
- **Delete confirmation** — double-press Delete, Move Up/Down, Move to Group
- **Removed management mode** — all code operations are now inline (no gear button/menus)

## 0.1.2

### Features

- **Search/create input** — filter codes by typing, Enter to create new code
- **Group management** — inline "New group" action, ungrouped codes section
- **Source navigation** — arrow left/right to navigate sources (Shift = jump 5)
- **Auto-merge** — adjacent sentences coded with same code merge automatically

### Fixes

- Sentence focus restoration after HTMX swaps
- Borderless search input until focused

## 0.1.1

### Changes

- Removed code tooltip, annotation click popup, and metadata tags

## 0.1.0

First release of ACE — Annotation Coding Environment.

### Features

- **Project management** — create, open, and resume `.ace` projects from the landing page
- **Source import** — import text sources from CSV files with column mapping
- **Annotation coding** — select text and apply codes with click or keyboard shortcuts (1–9, 0, a–z)
- **Codebook management** — create, rename, recolour, delete, and reorder codes via drag-and-drop
- **Grouped codes** — organise codes into collapsible groups; manage via "Move to Group" menu or CSV import
- **Code import/export** — import codes from CSV (`name,group` columns) with preview dialog; export codebook to CSV
- **Inter-coder agreement** — compute Krippendorff's alpha, Cohen's/Fleiss' kappa across multiple `.ace` files
- **Source navigation** — visual grid overview of all sources with density indicators and keyboard navigation (Alt+←/→)
- **Undo/redo** — undo and redo annotation actions
- **Header bar** — CSV export of all annotations, coder name management
- **Resizable code bar** — adjustable splitter between code list and source panel
