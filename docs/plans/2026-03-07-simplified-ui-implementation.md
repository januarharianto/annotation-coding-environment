# Simplified Single-Coder UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the manager/coder split with a single-user flow: Landing → Import → Coding (two-pane: codes left, text right).

**Architecture:** Rewrite the coding page as a new two-pane layout with inline code creation. Remove the manager stepper, role-based routing, and assignment system. A default coder row is auto-created at project creation. All sources become directly accessible without assignment.

**Tech Stack:** NiceGUI (Python), SQLite, existing models/services.

---

### Task 1: Move colour palette to shared location

The colour palette currently lives in `src/ace/pages/manager/codebook.py`. The new coding page needs it too.

**Files:**
- Create: `src/ace/services/palette.py`
- Modify: `src/ace/pages/manager/codebook.py` (update import)

**Step 1: Create palette module**

```python
# src/ace/services/palette.py
"""Colourblind-accessible colour palette for annotation codes."""

COLOUR_PALETTE = [
    ("#E69F00", "Orange"),
    ("#56B4E9", "Sky blue"),
    ("#009E73", "Teal"),
    ("#F0E442", "Yellow"),
    ("#0072B2", "Blue"),
    ("#D55E00", "Red-orange"),
    ("#CC79A7", "Pink"),
    ("#999999", "Grey"),
    ("#332288", "Indigo"),
    ("#44AA99", "Cyan"),
]


def next_colour(existing_count: int) -> str:
    """Return the next colour from the palette, cycling if needed."""
    return COLOUR_PALETTE[existing_count % len(COLOUR_PALETTE)][0]
```

**Step 2: Update codebook.py import**

In `src/ace/pages/manager/codebook.py`, replace the inline `COLOUR_PALETTE` definition with:
```python
from ace.services.palette import COLOUR_PALETTE
```
Delete lines 19-30 (the old definition).

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: All 85 tests pass (no tests reference the palette directly).

**Step 4: Commit**

```bash
git add src/ace/services/palette.py src/ace/pages/manager/codebook.py
git commit -m "refactor: extract colour palette to shared module"
```

---

### Task 2: Auto-create default coder at project creation

The new flow has no separate coder creation step. A default coder is created automatically when the project is created.

**Files:**
- Modify: `src/ace/db/connection.py:11-34` (add default coder + remove `file_role='manager'`)

**Step 1: Write the failing test**

In `tests/test_db/test_connection.py`, add:
```python
def test_create_project_creates_default_coder(tmp_path):
    from ace.db.connection import create_project, checkpoint_and_close
    path = tmp_path / "test.ace"
    conn = create_project(path, "Test")
    row = conn.execute("SELECT * FROM coder").fetchone()
    assert row is not None
    assert row["name"] == "default"
    checkpoint_and_close(conn)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db/test_connection.py::test_create_project_creates_default_coder -v`
Expected: FAIL — no coder row exists.

**Step 3: Update create_project**

In `src/ace/db/connection.py`, modify `create_project` to:
1. Insert the project row with `file_role='manager'` (keep for backwards compat)
2. Insert a default coder row:

```python
# After the project INSERT, add:
coder_id = uuid.uuid4().hex
conn.execute(
    "INSERT INTO coder (id, name) VALUES (?, ?)",
    (coder_id, "default"),
)
conn.commit()
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db/test_connection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ace/db/connection.py tests/test_db/test_connection.py
git commit -m "feat: auto-create default coder on project creation"
```

---

### Task 3: Create the import page as a standalone route

The current import logic lives in the manager stepper. Create a standalone `/import` page that shows after project creation.

**Files:**
- Create: `src/ace/pages/import_page.py`
- Modify: `src/ace/app.py` (register new route)
- Modify: `src/ace/pages/landing.py:142` (route to `/import` instead of `/manager`)

**Step 1: Create import_page.py**

Adapt `src/ace/pages/manager/import_data.py` into a standalone page. Key differences:
- It's a full page route (`/import`), not a stepper step
- After successful import, a "Start Coding" button navigates to `/code`
- No `stepper` parameter; standalone layout
- Reuse the existing `import_csv` and `import_text_files` from `ace.services.importer`

```python
"""Import page — upload data before coding."""

import tempfile
from pathlib import Path

import pandas as pd
from nicegui import app, events, ui

from ace.db.connection import checkpoint_and_close, open_project
from ace.models.source import list_sources
from ace.services.importer import import_csv, import_text_files


def register() -> None:
    @ui.page("/import")
    def import_page():
        project_path = app.storage.general.get("project_path")
        if not project_path:
            ui.navigate.to("/")
            return
        try:
            conn = open_project(project_path)
        except (ValueError, FileNotFoundError) as exc:
            ui.notify(str(exc), type="negative")
            ui.navigate.to("/")
            return

        _build_import_ui(conn)


def _build_import_ui(conn):
    state = {
        "df": None,
        "file_path": None,
        "file_name": None,
        "folder_path": None,
        "import_mode": None,
    }

    with ui.column().classes("q-pa-lg").style("max-width: 700px; margin: 0 auto;"):
        ui.label("Import Data").classes("text-h5 text-weight-bold q-mb-md")

        existing = list_sources(conn)
        if existing:
            ui.label(f"Already {len(existing)} source(s) imported.").classes(
                "text-body2 q-mb-sm"
            )
            ui.button(
                "Start Coding", icon="arrow_forward",
                on_click=lambda: ui.navigate.to("/code"),
            ).props("unelevated color=primary")
            ui.separator().classes("q-my-md")

        ui.label("Upload a CSV or Excel file").classes("text-body1 q-mb-sm")
        ui.upload(
            label="Drop CSV/Excel file here (or click to browse)",
            auto_upload=True,
            on_upload=lambda e: _handle_upload(e, state, preview, col_select, actions),
        ).props('accept=".csv,.xlsx,.xls" flat bordered').classes("full-width")

        # Preview, column selection, and action containers (hidden until needed)
        preview = ui.column().classes("full-width q-mt-md")
        preview.set_visibility(False)
        col_select = ui.column().classes("full-width q-mt-sm")
        col_select.set_visibility(False)
        actions = ui.column().classes("full-width q-mt-sm")
        actions.set_visibility(False)

        _build_actions(state, conn, actions, preview, col_select)
```

The upload handler, preview, column selection, and import logic follow the same pattern as the existing `import_data.py` — adapt rather than copy. The final action after import shows a "Start Coding →" button that navigates to `/code`.

**Step 2: Register the route in app.py**

In `src/ace/app.py`, add:
```python
from ace.pages import import_page
import_page.register()
```

**Step 3: Update landing.py routing**

In `src/ace/pages/landing.py:142`, change:
```python
ui.navigate.to("/manager")
```
to:
```python
ui.navigate.to("/import")
```

**Step 4: Update _store_and_route**

In `src/ace/pages/landing.py`, simplify `_store_and_route` to always route to `/code` (for existing projects with sources) or `/import` (for new projects):

```python
def _store_and_route(file_path: Path) -> None:
    try:
        conn = open_project(file_path)
    except (ValueError, FileNotFoundError) as exc:
        ui.notify(str(exc), type="negative")
        return

    app.storage.general["project_path"] = str(file_path)

    if is_cloud_sync_path(file_path):
        ui.notify(
            "Warning: This file is in a cloud-sync folder. "
            "SQLite WAL files may not sync correctly.",
            type="warning", timeout=10000,
        )

    # Route based on whether sources exist
    from ace.models.source import list_sources
    sources = list_sources(conn)
    checkpoint_and_close(conn)

    if sources:
        ui.navigate.to("/code")
    else:
        ui.navigate.to("/import")
```

**Step 5: Run tests and verify**

Run: `.venv/bin/python -m pytest tests/ -q`

**Step 6: Commit**

```bash
git add src/ace/pages/import_page.py src/ace/app.py src/ace/pages/landing.py
git commit -m "feat: add standalone import page, simplify routing"
```

---

### Task 4: Rewrite coding page as two-pane layout

This is the main task. Rewrite `src/ace/pages/coder/coding.py` (or create new `src/ace/pages/coding.py`) with the new layout.

**Files:**
- Create: `src/ace/pages/coding.py` (new simplified coding page)
- Modify: `src/ace/app.py` (register `/code` route)

**Key design decisions:**
- Route: `/code` (not `/coder` — no role distinction)
- No assignments — iterate directly over all sources in the DB
- Default coder is used for all annotations
- Left panel: code input + code list with "..." menus
- Right panel: annotated text
- Bottom bar: prev/next + progress

**Step 1: Create the new coding page skeleton**

`src/ace/pages/coding.py` — the `build(conn)` function sets up:

```
Layout:
┌──────────────────────┬─────────────────────────────────────┐
│ Left panel (280px)   │ Right panel (flex)                  │
│                      │                                      │
│ [+ New code input]   │ #ace-text-content                   │
│                      │ (annotated text)                     │
│ ■ Code1 [1] ...      │                                      │
│ ■ Code2 [2] ...      │                                      │
│                      │                                      │
│                      │ Annotations list                     │
│                      │ Notes textarea                       │
├──────────────────────┴─────────────────────────────────────┤
│ ◄ Prev │ ■■■■○○○ 4/7 │ Next ►    [Complete] [Flag]       │
└────────────────────────────────────────────────────────────┘
```

Core differences from old `coding.py`:
- Sources come from `list_sources(conn)` directly, not assignments
- Coder ID comes from `list_coders(conn)[0]["id"]` (the default coder)
- Status tracking uses a simple dict or the assignment table with auto-created assignments
- Left panel has an `ui.input` at top for creating codes + `@ui.refreshable` code list
- Each code row has a "..." `ui.menu` with Rename / Change colour / Delete options
- Clicking a code (when text is selected) applies annotation — no dialog
- Text selection stores `state["pending_selection"]`; clicking a code checks for it

**Step 2: Implement source iteration without assignments**

Since we're removing the assignment system, we need a way to track status per source. Simplest approach: auto-create assignment rows for the default coder when the page loads.

```python
def _ensure_assignments(conn, coder_id, sources):
    """Create assignment rows for any sources that don't have one."""
    for src in sources:
        existing = conn.execute(
            "SELECT id FROM assignment WHERE source_id = ? AND coder_id = ?",
            (src["id"], coder_id),
        ).fetchone()
        if not existing:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO assignment (id, source_id, coder_id, status, assigned_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (uuid.uuid4().hex, src["id"], coder_id, now, now),
            )
    conn.commit()
```

This lets us reuse the existing `update_assignment_status` and status tracking.

**Step 3: Implement the left panel with inline code creation**

```python
# Inside build():
with ui.column().classes("q-pa-md").style(
    "width: 280px; min-width: 280px; overflow-y: auto; border-right: 1px solid #e0e0e0;"
):
    # Back button
    ui.button(icon="arrow_back", on_click=lambda: _go_home(conn)).props(
        "flat round dense"
    ).tooltip("Back to home")

    ui.label("Codes").classes("text-subtitle2 text-weight-medium q-mt-sm")

    # Always-visible input for new codes
    new_code_input = ui.input(placeholder="+ New code...").props(
        "dense outlined"
    ).classes("full-width q-mb-sm")

    async def _create_code():
        name = new_code_input.value.strip()
        if not name:
            return
        colour = next_colour(len(list_codes(conn)))
        try:
            add_code(conn, name=name, colour=colour)
        except Exception as exc:
            ui.notify(str(exc), type="negative")
            return
        new_code_input.value = ""
        _refresh_codes()  # reload codes list, codes_by_id, re-render code_list

    new_code_input.on("keydown.enter", _create_code)

    @ui.refreshable
    def code_list():
        codes = list_codes(conn)
        for i, code in enumerate(codes):
            shortcut = str(i + 1) if i < 9 else ""
            colour = code["colour"] or "#999999"
            with ui.row().classes("items-center q-py-xs full-width").style("gap: 8px;"):
                ui.element("div").classes("ace-code-dot").style(
                    f"background-color: {colour};"
                )
                ui.label(code["name"]).classes(
                    "text-body2 col cursor-pointer"
                ).on("click", lambda _e, c=code: _apply_code_if_selection(c))
                if shortcut:
                    ui.label(shortcut).classes("text-caption text-grey-5").style(
                        "background: #eee; padding: 0 5px; font-family: monospace;"
                    )
                # "..." menu
                with ui.button(icon="more_vert").props("flat round dense size=xs"):
                    with ui.menu():
                        ui.menu_item("Rename", on_click=lambda c=code: _rename_code(c))
                        ui.menu_item("Change colour", on_click=lambda c=code: _change_colour(c))
                        ui.menu_item("Delete", on_click=lambda c=code: _delete_code_confirm(c))

    code_list()
```

**Step 4: Implement the right panel**

Reuse the existing `render_annotated_text`, `_render_text`, annotation list, and notes area from the old `coding.py`. These work unchanged — they just need `source_id` and `coder_id`.

**Step 5: Implement the bottom bar**

Same as current but using sources directly instead of assignments for counting. Keep prev/next, progress, Complete/Flag buttons.

**Step 6: Implement code management (rename, colour, delete)**

```python
def _rename_code(code):
    with ui.dialog(value=True) as d, ui.card().classes("q-pa-md"):
        ui.label("Rename Code").classes("text-subtitle1")
        name_input = ui.input(value=code["name"]).props("autofocus")
        with ui.row().classes("justify-end full-width gap-2 q-mt-sm"):
            ui.button("Cancel", on_click=d.close).props("flat")
            def _save():
                update_code(conn, code["id"], name=name_input.value.strip())
                d.close()
                _refresh_codes()
            ui.button("Save", on_click=_save).props("unelevated color=primary")

def _change_colour(code):
    # Dialog with colour palette swatches
    ...

def _delete_code_confirm(code):
    with ui.dialog(value=True) as d, ui.card().classes("q-pa-md"):
        ui.label(f'Delete "{code["name"]}"?').classes("text-subtitle1")
        ui.label("Annotations using this code will be orphaned.").classes("text-caption text-grey-7")
        with ui.row().classes("justify-end full-width gap-2 q-mt-sm"):
            ui.button("Cancel", on_click=d.close).props("flat")
            def _confirm():
                delete_code(conn, code["id"])
                d.close()
                _refresh_codes()
                _re_render_text()
            ui.button("Delete", on_click=_confirm).props("unelevated color=negative")
```

**Step 7: Wire up apply-code-on-click (no dialog)**

When text is selected (`state["pending_selection"]` is set), clicking a code on the left panel applies it directly:

```python
def _apply_code_if_selection(code):
    if state.get("pending_selection"):
        _apply_code(code, ...)
    # If no selection, do nothing (could show a toast)
```

**Step 8: Port event handlers and keyboard shortcuts**

Copy the `text_selected`, `annotation_clicked`, shortcut handlers, undo/redo from old `coding.py`. They work the same way.

**Step 9: Register the route**

In `src/ace/app.py`:
```python
from ace.pages import coding
coding.register()
```

**Step 10: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q`

**Step 11: Commit**

```bash
git add src/ace/pages/coding.py src/ace/app.py
git commit -m "feat: new two-pane coding interface with inline code creation"
```

---

### Task 5: Remove old manager pages and coder routing

Clean up code that's no longer used.

**Files:**
- Delete: `src/ace/pages/manager/` (entire directory)
- Delete: `src/ace/pages/coder/` (entire directory — replaced by `coding.py`)
- Modify: `src/ace/app.py` (remove manager and coder imports/registrations)
- Modify: `src/ace/pages/landing.py` (remove role-based routing, remove `get_project` import)

**Step 1: Remove old page registrations from app.py**

```python
# Remove:
from ace.pages import coder, manager
manager.register()
coder.register()
```

**Step 2: Delete old page directories**

```bash
rm -rf src/ace/pages/manager/
rm -rf src/ace/pages/coder/
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q`

Some tests may reference old pages. Fix any import errors in test files. The `test_pages/test_render.py` file imports from `coding.py` — update the import path.

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove manager stepper and old coder pages"
```

---

### Task 6: Update tests for new flow

**Files:**
- Modify: `tests/test_pages/test_render.py` (update import from new coding.py)
- Modify: `tests/test_db/test_connection.py` (if create_project tests need updating)
- Remove tests that reference deleted code (packager tests reference manager workflow)

**Step 1: Update render test imports**

Change:
```python
from ace.pages.coder.coding import render_annotated_text
```
to:
```python
from ace.pages.coding import render_annotated_text
```

**Step 2: Evaluate which tests to keep**

Keep:
- `test_db/` — all (schema, connection, migrations)
- `test_models/` — all (source, codebook, annotation)
- `test_services/test_importer.py` — keep
- `test_services/test_offset.py` — keep
- `test_services/test_undo.py` — keep
- `test_services/test_cloud_detect.py` — keep
- `test_services/test_exporter.py` — keep (export still useful)
- `test_pages/test_render.py` — keep (update import)

Keep but may need adjustment:
- `test_services/test_assigner.py` — still valid code, keep for now
- `test_services/test_packager.py` — still valid code, keep for now
- `test_services/test_icr.py` — still valid code, keep for now

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: All pass.

**Step 4: Commit**

```bash
git add -A
git commit -m "test: update tests for simplified UI"
```

---

### Task 7: Final cleanup and push

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`

**Step 2: Start the app and smoke-test manually**

Run: `.venv/bin/python -m ace`

Verify:
- Landing page shows New/Open project
- New Project → Import page
- Upload CSV → preview → import → Start Coding
- Coding page shows two-pane layout
- Can type new code name, press Enter
- Can select text, click code to annotate
- Can use "..." menu to rename/recolour/delete codes
- Prev/Next navigation works
- Undo/redo works

**Step 3: Push**

```bash
git push
```

**Step 4: Close relevant issues**

```bash
gh issue close 2 --repo januarharianto/annotation-coding-environment -c "Resolved as part of UI redesign — import page is now standalone"
```
