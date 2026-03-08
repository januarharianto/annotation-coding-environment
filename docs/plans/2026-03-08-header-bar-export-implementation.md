# Header Bar + CSV Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a persistent header bar across all pages with a one-click CSV export button on the coding page.

**Architecture:** A shared `build_header()` function in a new `header.py` module creates a thin `ui.header()` bar. Each page calls it with appropriate params. Export writes CSV to a temp file and triggers `ui.download()`.

**Tech Stack:** NiceGUI (`ui.header`, `ui.download`), existing `export_annotations_csv()` service, Python `tempfile`.

---

### Task 1: Create the shared header module

**Files:**
- Create: `src/ace/pages/header.py`

**Step 1: Create header module with `build_header()` function**

```python
"""Shared header bar for all ACE pages."""

import tempfile
from datetime import date
from pathlib import Path

from nicegui import ui

from ace.models.project import get_project
from ace.services.exporter import export_annotations_csv


def build_header(*, project_name: str | None = None, conn=None) -> None:
    """Build the shared top header bar.

    Args:
        project_name: If set, show as clickable link to home. Otherwise show "ACE" branding.
        conn: If set, show Export button and More menu (for coding page).
    """
    with ui.header().classes("bg-white text-dark items-center q-px-md").style(
        "border-bottom: 1px solid #e0e0e0; min-height: 40px; height: 40px;"
    ):
        with ui.row().classes("items-center full-width no-wrap").style("height: 100%;"):
            # Left: project name or branding
            if project_name:
                ui.button(
                    project_name,
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to("/"),
                ).props("flat dense no-caps").classes(
                    "text-subtitle2 text-weight-bold text-grey-8"
                ).tooltip("Back to home")
            else:
                ui.label("ACE").classes("text-subtitle2 text-weight-bold text-grey-7")

            ui.space()

            # Right: actions (only when conn is provided, i.e. coding page)
            if conn is not None:
                _project = get_project(conn)
                _project_name_for_file = _project["name"] if _project else "project"

                def _export():
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".csv", delete=False, prefix="ace_export_"
                    )
                    tmp.close()
                    count = export_annotations_csv(conn, tmp.name)
                    if count == 0:
                        ui.notify("No annotations to export.", type="info", position="bottom")
                        Path(tmp.name).unlink(missing_ok=True)
                        return
                    safe_name = "".join(
                        c if c.isalnum() or c in (" ", "-", "_") else "_"
                        for c in _project_name_for_file
                    )
                    filename = f"{safe_name}_export_{date.today().isoformat()}.csv"
                    ui.download(tmp.name, filename)

                ui.button("Export", icon="download", on_click=_export).props(
                    "flat dense no-caps"
                ).classes("text-grey-8")

                with ui.button(icon="more_vert").props("flat round dense").classes(
                    "text-grey-6"
                ):
                    with ui.menu():
                        ui.menu_item("Settings (coming soon)").props("disable")
```

**Step 2: Run existing tests to verify nothing is broken**

Run: `uv run pytest -x -q`
Expected: All tests pass (no changes to existing code yet).

**Step 3: Commit**

```bash
git add src/ace/pages/header.py
git commit -m "feat: add shared header bar module"
```

---

### Task 2: Integrate header into coding page

**Files:**
- Modify: `src/ace/pages/coding.py`

This is the most involved integration — the coding page has viewport-height CSS that needs adjusting for the header.

**Step 1: Add header import and call**

At the top of `coding.py`, add to imports:

```python
from ace.pages.header import build_header
```

In the `build()` function, after the project/coder/sources setup but **before** the layout CSS injection (currently line 212), add:

```python
project = get_project(conn)
build_header(project_name=project["name"] if project else "ACE", conn=conn)
```

Note: `get_project` is already imported (line 23).

**Step 2: Fix viewport CSS to account for header**

The current CSS (around line 216-221) sets `.q-page { height: 100vh }` which will overflow with the header. Change:

```python
ui.add_head_html(
    '<style>'
    'html, body { overflow: hidden; height: 100vh; } '
    '.q-page { display: flex; flex-direction: column; height: 100vh; } '
    '.q-page > .nicegui-content { flex: 1; min-height: 0; display: flex; flex-direction: column; }'
    '</style>'
)
```

To:

```python
ui.add_head_html(
    '<style>'
    'html, body { overflow: hidden; height: 100vh; } '
    '.q-page { display: flex; flex-direction: column; height: 100%; } '
    '.q-page > .nicegui-content { flex: 1; min-height: 0; display: flex; flex-direction: column; }'
    '</style>'
)
```

The key change: `.q-page` goes from `height: 100vh` to `height: 100%` — Quasar's layout system automatically reserves space for the header, so `100%` means "remaining viewport height after header".

**Step 3: Remove the old back button + ACE label from the left panel**

Remove these lines (currently around lines 239-243):

```python
# Back button + app name
with ui.row().classes("items-center gap-2").style("flex-shrink: 0;"):
    ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
        "flat round dense"
    ).tooltip("Back to home")
    ui.label("ACE").classes("text-subtitle2 text-weight-bold text-grey-7")
```

The header now handles navigation back to home.

**Step 4: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass.

**Step 5: Manual test**

Run: `uv run ace`
Verify:
- Header bar appears at top of coding page with project name and Export button
- Clicking project name navigates to home
- Left panel no longer has back button / ACE label
- Layout still fills viewport correctly (no scrollbars on the outer page)

**Step 6: Commit**

```bash
git add src/ace/pages/coding.py
git commit -m "feat: integrate header bar into coding page"
```

---

### Task 3: Integrate header into import page

**Files:**
- Modify: `src/ace/pages/import_page.py`

**Step 1: Add header import and call**

Add to imports:

```python
from ace.pages.header import build_header
from ace.models.project import get_project
```

In `_build(conn)`, before the main `ui.column()` layout (line 44), add:

```python
project = get_project(conn)
build_header(project_name=project["name"] if project else "ACE")
```

Note: `conn` is NOT passed here — import page has no export button.

**Step 2: Remove the existing ACE label**

Remove this line (currently line 46 inside the main column):

```python
ui.label("ACE").classes("text-subtitle2 text-weight-bold text-grey-7")
```

**Step 3: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass.

**Step 4: Commit**

```bash
git add src/ace/pages/import_page.py
git commit -m "feat: integrate header bar into import page"
```

---

### Task 4: Integrate header into landing page

**Files:**
- Modify: `src/ace/pages/landing.py`

**Step 1: Add header import and call**

Add to imports:

```python
from ace.pages.header import build_header
```

In the `landing()` function inside `register()`, before the main `ui.column()` layout (line 81), add:

```python
build_header()
```

No project name, no conn — just branding.

**Step 2: Run tests**

Run: `uv run pytest -x -q`
Expected: All tests pass.

**Step 3: Manual test — verify all three pages**

Run: `uv run ace`
Verify:
- `/` — thin header with "ACE", centered content below
- `/import` — header with project name (clickable → home), import form below
- `/code` — header with project name + Export + More menu

**Step 4: Commit**

```bash
git add src/ace/pages/landing.py
git commit -m "feat: integrate header bar into landing page"
```

---

### Task 5: Test CSV export end-to-end

**Step 1: Manual test of export**

Run: `uv run ace`
1. Open a project with annotations
2. Click "Export" in the header
3. Verify: browser downloads a CSV file
4. Open the CSV — verify it contains annotation data with correct columns

**Step 2: Test empty export**

1. Open a project with NO annotations
2. Click "Export"
3. Verify: toast notification "No annotations to export." appears, no file downloaded

**Step 3: Commit plan doc update**

```bash
git add docs/plans/2026-03-08-header-bar-export-implementation.md
git commit -m "docs: add header bar + export implementation plan"
```

---

## Summary of Changes

| File | Action | What |
|------|--------|------|
| `src/ace/pages/header.py` | Create | Shared header with project name, export, more menu |
| `src/ace/pages/coding.py` | Modify | Add header call, fix viewport CSS, remove old back button |
| `src/ace/pages/import_page.py` | Modify | Add header call, remove old ACE label |
| `src/ace/pages/landing.py` | Modify | Add header call |
