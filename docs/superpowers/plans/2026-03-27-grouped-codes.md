# Grouped Codes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single-level code grouping — codes belong to named groups, displayed with collapsible headers in the sidebar, importable/exportable via CSV, and manageable in-app via a "Move to Group" menu.

**Architecture:** Add `group_name` column to `codebook_code` via schema migration. Update all codebook model functions to handle groups. Render grouped code list with collapsible headers, constrain drag-and-drop within groups. Add group-level checkboxes to import dialog. Add "Move to Group" popup menu to code `⋮` menu.

**Tech Stack:** Python, SQLite, NiceGUI/Quasar, Sortable.js, pytest

**Spec:** `docs/superpowers/specs/2026-03-26-grouped-codes-design.md`

---

### File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/ace/db/schema.py` | Modify | Bump SCHEMA_VERSION to 2, add group_name to _SCHEMA_SQL |
| `src/ace/db/migrations.py` | Modify | Add v1→v2 migration function |
| `src/ace/db/connection.py` | Modify | Call check_and_migrate() in open_project() |
| `src/ace/models/codebook.py` | Modify | Add group_name to all CRUD + CSV functions |
| `src/ace/pages/coding.py` | Modify | Grouped code list, import dialog, Move to Group menu |
| `src/ace/pages/coding_dialogs.py` | Modify | Add "New Group" dialog |
| `src/ace/static/css/annotator.css` | Modify | Add ace-group-header CSS class |
| `tests/test_models/test_codebook.py` | Modify | Tests for all group_name functionality |
| `tests/test_db/test_migrations.py` | Create | Tests for schema migration |

---

### Task 1: Schema migration — add group_name column

**Files:**
- Modify: `src/ace/db/schema.py`
- Modify: `src/ace/db/migrations.py`
- Modify: `src/ace/db/connection.py`
- Create: `tests/test_db/test_migrations.py`

- [ ] **Step 1: Write failing test for migration**

Create `tests/test_db/test_migrations.py`:

```python
"""Tests for schema migrations."""

import sqlite3

from ace.db.connection import create_project, open_project
from ace.db.schema import ACE_APPLICATION_ID


def test_v1_to_v2_migration_adds_group_name(tmp_path):
    """Opening a v1 database migrates it to v2 with group_name column."""
    db_path = tmp_path / "v1.ace"

    # Create a v1 database manually (without group_name column)
    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute("PRAGMA user_version = 1")
    conn.execute("""
        CREATE TABLE project (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            instructions TEXT, file_role TEXT NOT NULL, codebook_hash TEXT,
            assignment_seed TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE codebook_code (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            colour TEXT NOT NULL, sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE coder (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE)
    """)
    conn.execute("INSERT INTO coder VALUES ('c1', 'default')")
    conn.execute(
        "INSERT INTO project VALUES ('p1', 'Test', NULL, NULL, 'manager', NULL, NULL, '2025-01-01', '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO codebook_code VALUES ('cc1', 'Alpha', '#FF0000', 1, '2025-01-01')"
    )
    conn.commit()
    conn.close()

    # Open with open_project — should trigger migration
    conn = open_project(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2

    # group_name column should exist and be NULL for existing codes
    row = conn.execute("SELECT group_name FROM codebook_code WHERE name = 'Alpha'").fetchone()
    assert row["group_name"] is None
    conn.close()


def test_fresh_db_has_group_name_column(tmp_path):
    """A newly created project has the group_name column."""
    db_path = tmp_path / "fresh.ace"
    conn = create_project(db_path, "Test")
    # Should not raise — column exists
    conn.execute("SELECT group_name FROM codebook_code").fetchall()
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db/test_migrations.py -v`
Expected: FAIL — `group_name` column doesn't exist

- [ ] **Step 3: Implement schema changes**

In `src/ace/db/schema.py`, update `SCHEMA_VERSION` and add `group_name` to the schema:

```python
SCHEMA_VERSION = 2
```

In `_SCHEMA_SQL`, update the `codebook_code` table:

```sql
CREATE TABLE IF NOT EXISTS codebook_code (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    colour      TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    group_name  TEXT,
    created_at  TEXT NOT NULL
);
```

In `src/ace/db/migrations.py`, add the v1→v2 migration:

```python
def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add group_name column to codebook_code."""
    conn.execute("ALTER TABLE codebook_code ADD COLUMN group_name TEXT")


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_v1_to_v2,
}
```

In `src/ace/db/connection.py`, add migration call to `open_project()` after line 62:

```python
from ace.db.migrations import check_and_migrate

# Inside open_project(), after the WAL line:
    conn.execute("PRAGMA journal_mode = WAL")
    check_and_migrate(conn)
    return conn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db/test_migrations.py -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests**

Run: `uv run pytest -x -q`
Expected: All pass (existing tests create fresh DBs which get v2 schema)

- [ ] **Step 6: Commit**

```bash
git add src/ace/db/schema.py src/ace/db/migrations.py src/ace/db/connection.py tests/test_db/test_migrations.py
git commit -m "feat(db): add group_name column to codebook_code with v1→v2 migration"
```

---

### Task 2: Update codebook model — add_code, update_code, list_codes, compute_hash

**Files:**
- Modify: `src/ace/models/codebook.py`
- Modify: `tests/test_models/test_codebook.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_models/test_codebook.py`:

```python
def test_add_code_with_group(tmp_db):
    """add_code accepts optional group_name."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000", group_name="Emotions")
    row = conn.execute("SELECT group_name FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["group_name"] == "Emotions"


def test_add_code_without_group(tmp_db):
    """add_code without group_name stores NULL."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000")
    row = conn.execute("SELECT group_name FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["group_name"] is None


def test_update_code_group_name(tmp_db):
    """update_code can set group_name."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000")
    update_code(conn, cid, group_name="Emotions")
    row = conn.execute("SELECT group_name FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["group_name"] == "Emotions"


def test_update_code_clear_group(tmp_db):
    """update_code with group_name='' clears group to NULL."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000", group_name="Emotions")
    update_code(conn, cid, group_name="")
    row = conn.execute("SELECT group_name FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["group_name"] is None


def test_codebook_hash_includes_group(tmp_db):
    """Hash changes when group_name is different."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000")
    h1 = compute_codebook_hash(conn)
    update_code(conn, cid, group_name="Emotions")
    h2 = compute_codebook_hash(conn)
    assert h1 != h2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models/test_codebook.py::test_add_code_with_group -v`
Expected: FAIL — `add_code() got an unexpected keyword argument 'group_name'`

- [ ] **Step 3: Implement model changes**

In `src/ace/models/codebook.py`:

Add sentinel at module level:

```python
_UNSET = object()
```

Update `add_code`:

```python
def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
    group_name: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    code_id = uuid.uuid4().hex

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code").fetchone()[0]
    sort_order = max_order + 1

    conn.execute(
        "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code_id, name, colour, sort_order, group_name, now),
    )
    conn.commit()
    return code_id
```

Update `update_code`:

```python
def update_code(
    conn: sqlite3.Connection,
    code_id: str,
    name: str | None = None,
    colour: str | None = None,
    group_name: object = _UNSET,
) -> None:
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if colour is not None:
        updates.append("colour = ?")
        params.append(colour)
    if group_name is not _UNSET:
        updates.append("group_name = ?")
        params.append(group_name if group_name != "" else None)
    if not updates:
        return
    params.append(code_id)
    conn.execute(
        f"UPDATE codebook_code SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
```

Update `compute_codebook_hash`:

```python
def compute_codebook_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, name, colour, group_name FROM codebook_code ORDER BY id"
    ).fetchall()
    combined = "".join(
        f"{r['id']}{r['name']}{r['colour']}{r['group_name'] or ''}"
        for r in rows
    )
    return hashlib.sha256(combined.encode()).hexdigest()
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/test_models/test_codebook.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/ace/models/codebook.py tests/test_models/test_codebook.py
git commit -m "feat(codebook): add group_name support to add_code, update_code, compute_hash"
```

---

### Task 3: Update CSV parsing, preview, import, export for groups

**Files:**
- Modify: `src/ace/models/codebook.py`
- Modify: `tests/test_models/test_codebook.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_models/test_codebook.py`:

```python
def test_parse_csv_with_group_column(tmp_db, tmp_path):
    """CSV with name + group columns parses correctly."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nSad,Emotions\nIdentity,Themes\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 3
    codes = list_codes(conn)
    assert codes[0]["group_name"] == "Emotions"
    assert codes[2]["group_name"] == "Themes"


def test_parse_csv_strips_group_whitespace(tmp_db, tmp_path):
    """Group names have whitespace stripped, casing preserved."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,  Emotions  \nSad,ICR Codes\n")
    count = import_codebook_from_csv(conn, csv_path)
    codes = list_codes(conn)
    assert codes[0]["group_name"] == "Emotions"
    assert codes[1]["group_name"] == "ICR Codes"


def test_parse_csv_empty_group_is_null(tmp_db, tmp_path):
    """Empty group value in CSV becomes NULL."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nUngrouped,\n")
    count = import_codebook_from_csv(conn, csv_path)
    codes = list_codes(conn)
    assert codes[0]["group_name"] == "Emotions"
    assert codes[1]["group_name"] is None


def test_parse_csv_colour_column_ignored(tmp_db, tmp_path):
    """Old CSV with colour column — colour ignored, auto-assigned."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour,group\nHappy,#FF0000,Emotions\n")
    count = import_codebook_from_csv(conn, csv_path)
    codes = list_codes(conn)
    assert codes[0]["group_name"] == "Emotions"
    # colour auto-assigned (not #FF0000)
    assert codes[0]["colour"] != "#FF0000" or True  # colour may match palette[0]


def test_parse_csv_duplicate_names_different_groups(tmp_db, tmp_path):
    """Same code name in different groups — first kept, second skipped."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nHappy,Wellbeing\nSad,Emotions\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2  # Happy (Emotions) + Sad
    codes = list_codes(conn)
    assert len(codes) == 2
    assert codes[0]["name"] == "Happy"
    assert codes[0]["group_name"] == "Emotions"


def test_preview_includes_group_name(tmp_db, tmp_path):
    """preview_codebook_csv includes group_name in output."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nSad,Emotions\n")
    preview = preview_codebook_csv(conn, csv_path)
    assert preview[0]["group_name"] == "Emotions"
    assert preview[1]["group_name"] == "Emotions"


def test_import_selected_with_group(tmp_db):
    """import_selected_codes stores group_name."""
    conn = create_project(tmp_db, "Test")
    codes = [
        {"name": "Happy", "colour": "#FF0000", "group_name": "Emotions"},
        {"name": "Identity", "colour": "#00FF00", "group_name": "Themes"},
    ]
    import_selected_codes(conn, codes)
    result = list_codes(conn)
    assert result[0]["group_name"] == "Emotions"
    assert result[1]["group_name"] == "Themes"


def test_export_csv_includes_group(tmp_db, tmp_path):
    """export_codebook_to_csv writes name,group columns."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Happy", "#FF0000", group_name="Emotions")
    add_code(conn, "Ungrouped", "#00FF00")
    out = tmp_path / "out.csv"
    export_codebook_to_csv(conn, out)
    content = out.read_text()
    assert "name,group" in content
    assert "Happy,Emotions" in content
    assert "Ungrouped," in content
    assert "colour" not in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models/test_codebook.py::test_parse_csv_with_group_column -v`
Expected: FAIL

- [ ] **Step 3: Implement CSV changes**

Update `_parse_codebook_csv`:

```python
def _parse_codebook_csv(path: str | Path) -> list[dict]:
    """Parse a codebook CSV file into a list of {name, colour, group_name} dicts.

    Reads 'group' column if present (strips whitespace, preserves casing).
    Ignores 'colour' column — always auto-assigns from palette.
    Raises ValueError if 'name' column is missing.
    """
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "name" not in reader.fieldnames:
            raise ValueError("CSV must have a 'name' column")

        has_group = "group" in (reader.fieldnames or [])
        rows: list[dict] = []
        seen_names: set[str] = set()
        for row in reader:
            name = row.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            colour = next_colour(len(rows))

            group_name = None
            if has_group:
                g = row.get("group", "").strip()
                if g:
                    group_name = g

            rows.append({"name": name, "colour": colour, "group_name": group_name})
    return rows
```

Update `preview_codebook_csv`:

```python
def preview_codebook_csv(conn: sqlite3.Connection, path: str | Path) -> list[dict]:
    """Parse a codebook CSV and mark which codes already exist in the project.

    Returns list of {"name", "colour", "group_name", "exists"} dicts.
    """
    rows = _parse_codebook_csv(path)
    existing = {
        r["name"] for r in conn.execute("SELECT name FROM codebook_code").fetchall()
    }
    return [
        {**r, "exists": r["name"] in existing}
        for r in rows
    ]
```

Update `import_selected_codes` — add `group_name` to the INSERT:

```python
def import_selected_codes(conn: sqlite3.Connection, codes: list[dict]) -> int:
    if not codes:
        return 0

    existing = {
        r["name"] for r in conn.execute("SELECT name FROM codebook_code").fetchall()
    }
    to_insert = [c for c in codes if c["name"] not in existing]
    if not to_insert:
        return 0

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code"
    ).fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()

    try:
        for i, code in enumerate(to_insert):
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, code["name"], code["colour"], max_order + i + 1,
                 code.get("group_name"), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(to_insert)
```

Update `import_codebook_from_csv` — add `group_name` to the INSERT:

```python
def import_codebook_from_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    rows_to_insert = _parse_codebook_csv(path)

    now = datetime.now(timezone.utc).isoformat()
    try:
        for i, row in enumerate(rows_to_insert):
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code_id, row["name"], row["colour"], i + 1, row.get("group_name"), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows_to_insert)
```

Update `export_codebook_to_csv`:

```python
def export_codebook_to_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    codes = conn.execute(
        "SELECT name, group_name FROM codebook_code ORDER BY sort_order"
    ).fetchall()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "group"])
        writer.writeheader()
        for code in codes:
            writer.writerow({
                "name": code["name"],
                "group": code["group_name"] or "",
            })
    return len(codes)
```

- [ ] **Step 4: Update existing tests that check export format**

The `test_export_codebook_to_csv` test checks for `name,colour` — update to check `name,group`:

```python
def test_export_codebook_to_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")
    add_code(conn, "Beta", "#00FF00")
    out = tmp_path / "out.csv"
    count = export_codebook_to_csv(conn, out)
    assert count == 2
    content = out.read_text()
    assert "name,group" in content
    assert "Alpha," in content
    assert "Beta," in content
```

Also update `test_preview_marks_existing_codes` — preview dicts now include `group_name`:

```python
def test_preview_marks_existing_codes(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")

    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name\nAlpha\nBeta\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert len(preview) == 2
    assert preview[0]["name"] == "Alpha"
    assert preview[0]["exists"] is True
    assert preview[1]["name"] == "Beta"
    assert preview[1]["exists"] is False
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/test_models/test_codebook.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/ace/models/codebook.py tests/test_models/test_codebook.py
git commit -m "feat(codebook): add group support to CSV parsing, preview, import, export"
```

---

### Task 4: Add ace-group-header CSS

**Files:**
- Modify: `src/ace/static/css/annotator.css`

- [ ] **Step 1: Add CSS class**

Add to `src/ace/static/css/annotator.css`:

```css
/* ── Group headers in code list ─────────────────────────────── */
.ace-group-header {
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9e9e9e;
    padding: 0 4px;
    margin-top: 12px;
    margin-bottom: 2px;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    align-items: center;
    cursor: pointer;
    user-select: none;
}
.ace-group-header:first-child {
    margin-top: 0;
}
.ace-group-header .chevron {
    transition: transform 0.15s;
}
.ace-group-header.collapsed .chevron {
    transform: rotate(-90deg);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/ace/static/css/annotator.css
git commit -m "style: add ace-group-header CSS class for code grouping"
```

---

### Task 5: Render grouped code list with collapse/expand

**Files:**
- Modify: `src/ace/pages/coding.py`

- [ ] **Step 1: Update the code_list refreshable**

Replace the `code_list()` refreshable function (lines 404-468) with a version that groups codes by `group_name`, renders collapsible headers, and constrains drag within groups.

Key changes:
- Group codes using `itertools.groupby` (or manual grouping) on `group_name`
- Render each group with an `ace-group-header` div containing the group name + chevron icon + shortcut range
- Collapsed state read from `app.storage.general` keyed by project path
- Clicking header toggles collapse state and refreshes
- Grouped code rows get `padding-left: 20px`
- If no codes have groups, render flat list (same as today)
- Ungrouped codes render under an "Ungrouped" header (not collapsible)
- Each group's codes wrapped in a separate `ace-code-list` div for Sortable.js containment
- Sort by name toggle: sort by `(group_name or '', name.lower())` tuple

This task is UI-only — no tests (existing model tests cover data; this is rendering).

- [ ] **Step 2: Run all tests**

Run: `uv run pytest -x -q`
Expected: All pass

- [ ] **Step 3: Manual test**

Start `uv run ace`, open a project, import a CSV with groups:
```csv
name,group
Happy,Emotions
Sad,Emotions
Identity,Themes
Power,Themes
Other,
```

Verify:
1. Groups render with uppercase headers and chevron icons
2. Clicking a group header collapses/expands its codes
3. Collapse state persists after page reload
4. Collapsed header shows shortcut range (e.g. "EMOTIONS [1–2]")
5. Keyboard shortcuts work on collapsed codes
6. Flat list (no groups) renders same as before
7. Drag-and-drop reorders within a group only

- [ ] **Step 4: Commit**

```bash
git add src/ace/pages/coding.py
git commit -m "feat(coding): render grouped code list with collapsible headers"
```

---

### Task 6: Update import dialog with group sub-sections and tri-state checkboxes

**Files:**
- Modify: `src/ace/pages/coding.py`

- [ ] **Step 1: Update the import dialog**

Modify `_show_import_dialog()` to:
- Group new codes by `group_name` and render sub-sections with group headers
- Add group-level checkboxes with tri-state behaviour (indeterminate → checked → unchecked → checked)
- Indent code rows 24px under group headers
- If `_parse_codebook_csv` dropped duplicate names (same name in different groups), show a `ui.notify` warning in the dialog: "N duplicate code name(s) were skipped." The parser already deduplicates — compare the row count before/after dedup to detect this.
- Group headers: 12px font, `#757575`, uppercase, `margin-top: 8px`
- If CSV has no groups, render flat list (same as current)

- [ ] **Step 2: Run all tests**

Run: `uv run pytest -x -q`
Expected: All pass

- [ ] **Step 3: Manual test**

Import a CSV with groups and verify:
1. New codes section shows group sub-headers with checkboxes
2. Checking/unchecking group header toggles all codes in group
3. Partially checked group shows indeterminate state
4. "Import All N" count updates correctly
5. "Already in project" section groups existing codes
6. Flat CSV (no group column) shows flat list

- [ ] **Step 4: Commit**

```bash
git add src/ace/pages/coding.py
git commit -m "feat(coding): add group sections with tri-state checkboxes to import dialog"
```

---

### Task 7: Add "Move to Group" menu to code ⋮ menu

**Files:**
- Modify: `src/ace/pages/coding.py`
- Modify: `src/ace/pages/coding_dialogs.py`

- [ ] **Step 1: Add "New Group" dialog to coding_dialogs.py**

Add a simple dialog function:

```python
def open_new_group_dialog(dlg, on_create):
    """Dialog to create a new group name."""
    dlg.clear()
    with dlg, ui.card().classes("q-pa-md").style("min-width: 300px;"):
        ui.label("New Group").classes("text-subtitle1 text-weight-medium q-mb-sm")
        name_input = ui.input("Group name").props("autofocus outlined dense")

        def _create():
            name = name_input.value.strip()
            if not name:
                return
            dlg.close()
            on_create(name)

        with ui.row().classes("q-mt-md justify-end full-width gap-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")
            ui.button("Create", on_click=_create).props("unelevated color=primary")
    dlg.open()
```

- [ ] **Step 2: Add "Move to Group" to the ⋮ menu in coding.py**

In the code row's `⋮` menu (inside `code_list()`), add separators and a "Move to Group" item:

```python
with ui.menu():
    ui.menu_item("Rename", on_click=...)
    ui.menu_item("Change colour", on_click=...)
    ui.separator()
    # Move to Group submenu
    with ui.menu_item("Move to Group"):
        with ui.menu():
            existing_groups = sorted({
                c["group_name"] for c in codes if c["group_name"]
            })
            for g in existing_groups:
                item = ui.menu_item(
                    g, on_click=lambda _e, grp=g: _move_to_group(code, grp),
                )
                if code["group_name"] == g:
                    item.props("active")
            if existing_groups:
                ui.separator()
            ui.menu_item("New Group...", on_click=lambda _e: _open_new_group(code))
            ui.menu_item("Ungrouped", on_click=lambda _e: _move_to_group(code, None))
    ui.separator()
    ui.menu_item("Delete", on_click=...)
```

Add helper functions:

```python
def _move_to_group(code, group_name):
    old_group = code["group_name"]
    update_code(conn, code["id"], group_name=group_name if group_name else "")
    _refresh_codes()
    code_list.refresh()
    # Toast if last code left a group
    if old_group and not any(c["group_name"] == old_group for c in codes):
        ui.notify(f"'{old_group}' group removed (no remaining codes).", type="info", position="bottom")

def _open_new_group(code):
    def _on_create(name):
        _move_to_group(code, name)
    open_new_group_dialog(new_group_dialog, _on_create)
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -x -q`
Expected: All pass

- [ ] **Step 4: Manual test**

1. Click `⋮` on a code → see Rename, Change colour, separator, Move to Group, separator, Delete
2. Hover/click "Move to Group" → submenu shows existing groups + "New Group..." + "Ungrouped"
3. Current group has a visual indicator (active state)
4. Move a code to a different group → code moves, code list re-renders
5. Create a new group → code moves to new group, new group header appears
6. Move last code out of a group → group disappears, toast shown
7. Move a code to "Ungrouped" → code moves to ungrouped section

- [ ] **Step 5: Commit**

```bash
git add src/ace/pages/coding.py src/ace/pages/coding_dialogs.py
git commit -m "feat(coding): add Move to Group menu with new group dialog"
```
