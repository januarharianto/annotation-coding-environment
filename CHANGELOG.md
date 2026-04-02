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
