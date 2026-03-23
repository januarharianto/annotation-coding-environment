# Import/Export Codes via CSV Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CSV import and export for the codebook, accessible from the coding page's code bar.

**Architecture:** Rewrite `import_codebook_from_csv()` for robustness (atomic transactions, optional colour, dedup). Add `export_codebook_to_csv()`. Wire both into the coding page via a `more_vert` menu in the Codes header, plus an empty-state message with clickable import link.

**Tech Stack:** Python csv module, NiceGUI `ui.upload`/`ui.download`, SQLite transactions

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/ace/models/codebook.py` | Modify | Rewrite `import_codebook_from_csv()`, add `export_codebook_to_csv()` |
| `tests/test_models/test_codebook.py` | Modify | Tests for import (optional colour, dedup, validation) and export |
| `src/ace/pages/coding.py` | Modify | Menu button, import/export handlers, empty state |

---

## Task 1: Rewrite `import_codebook_from_csv` and add `export_codebook_to_csv`

**Files:**
- Modify: `src/ace/models/codebook.py:87-100`
- Test: `tests/test_models/test_codebook.py`

- [ ] **Step 1: Write failing tests for the new import behaviour**

Add to `tests/test_models/test_codebook.py`:

```python
import re

from ace.models.codebook import export_codebook_to_csv


def test_import_csv_optional_colour(tmp_db, tmp_path):
    """Import CSV with no colour column — colours auto-assigned."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,description\nAlpha,First\nBeta,Second\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert all(re.match(r"^#[0-9A-F]{6}$", c["colour"]) for c in codes)


def test_import_csv_skips_empty_names(tmp_db, tmp_path):
    """Rows with empty name are skipped."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\n,#00FF00\n  ,#0000FF\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 1


def test_import_csv_dedup_names(tmp_db, tmp_path):
    """Duplicate names in CSV: keep first, skip subsequent."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\nAlpha,#00FF00\nBeta,#0000FF\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert codes[0]["colour"] == "#FF0000"  # first occurrence kept


def test_import_csv_invalid_colour_auto_assigns(tmp_db, tmp_path):
    """Invalid colour values get auto-assigned from palette."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,red\nBeta,#00FF00\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert re.match(r"^#[0-9A-F]{6}$", codes[0]["colour"])  # auto-assigned
    assert codes[1]["colour"] == "#00FF00"  # valid, kept


def test_import_csv_atomic_rollback(tmp_db, tmp_path):
    """Import is atomic — nothing committed if an error occurs mid-import."""
    conn = create_project(tmp_db, "Test")
    # Intentionally malformed: missing name column entirely
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("colour\n#FF0000\n#00FF00\n")
    with pytest.raises(ValueError, match="name"):
        import_codebook_from_csv(conn, csv_path)
    assert list_codes(conn) == []


def test_import_csv_utf8_bom(tmp_db, tmp_path):
    """Handle UTF-8 BOM from Excel exports."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_bytes(b"\xef\xbb\xbfname,colour\nAlpha,#FF0000\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 1
    assert list_codes(conn)[0]["name"] == "Alpha"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models/test_codebook.py -v`
Expected: New tests FAIL (existing `import_codebook_from_csv` doesn't handle optional colour, dedup, etc.)

- [ ] **Step 3: Rewrite `import_codebook_from_csv` and add `export_codebook_to_csv`**

Replace `import_codebook_from_csv` (lines 87-100) and add `export_codebook_to_csv` at end of `src/ace/models/codebook.py`:

```python
import re as _re

from ace.services.palette import next_colour

_COLOUR_RE = _re.compile(r"^#[0-9A-Fa-f]{6}$")


def import_codebook_from_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "name" not in reader.fieldnames:
            raise ValueError("CSV must have a 'name' column")

        rows_to_insert = []
        seen_names: set[str] = set()
        for row in reader:
            name = row.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            colour = row.get("colour", "").strip()
            if not _COLOUR_RE.match(colour):
                colour = next_colour(len(rows_to_insert))

            description = row.get("description", "").strip() or None
            rows_to_insert.append((name, colour, description))

    now = datetime.now(timezone.utc).isoformat()
    try:
        for i, (name, colour, description) in enumerate(rows_to_insert):
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code (id, name, description, colour, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code_id, name, description, colour, i + 1, now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows_to_insert)


def export_codebook_to_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    codes = conn.execute(
        "SELECT name, description, colour FROM codebook_code ORDER BY sort_order"
    ).fetchall()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "description", "colour"])
        writer.writeheader()
        for code in codes:
            writer.writerow({
                "name": code["name"],
                "description": code["description"] or "",
                "colour": code["colour"],
            })
    return len(codes)
```

Note: add `import re as _re` at top of file and `from ace.services.palette import next_colour` after existing imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models/test_codebook.py -v`
Expected: All tests PASS (including existing tests)

- [ ] **Step 5: Write and run export test**

Add to `tests/test_models/test_codebook.py`:

```python
def test_export_codebook_to_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000", "First")
    add_code(conn, "Beta", "#00FF00")
    out = tmp_path / "out.csv"
    count = export_codebook_to_csv(conn, out)
    assert count == 2
    content = out.read_text()
    assert "name,description,colour" in content
    assert "Alpha,First,#FF0000" in content
    assert "Beta,,#00FF00" in content
```

Run: `uv run pytest tests/test_models/test_codebook.py::test_export_codebook_to_csv -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/ace/models/codebook.py tests/test_models/test_codebook.py
git commit -m "feat: robust CSV import with validation, add codebook export"
```

---

## Task 2: Add import/export UI to coding page

**Files:**
- Modify: `src/ace/pages/coding.py:267-269` (Codes header row), `src/ace/pages/coding.py:304-308` (code_list refreshable)

- [ ] **Step 1: Add imports at top of coding.py**

Add to the imports section of `src/ace/pages/coding.py`:

```python
import tempfile
from ace.models.codebook import import_codebook_from_csv, export_codebook_to_csv
```

Note: `tempfile` may already be imported — check first. `import_codebook_from_csv` may already be imported — check and add `export_codebook_to_csv` if needed.

- [ ] **Step 2: Add the more_vert menu button in the Codes header row**

In `src/ace/pages/coding.py`, after the sort button tooltip (around line 283), add the menu button inside the same header row:

```python
                with ui.button(icon="more_vert").props(
                    "flat round dense size=sm"
                ).classes("text-grey-7"):
                    with ui.menu():
                        import_item = ui.menu_item(
                            "Import CSV...",
                            on_click=lambda: _import_codes(),
                        )
                        export_item = ui.menu_item(
                            "Export CSV",
                            on_click=lambda: _export_codes(),
                        )
```

- [ ] **Step 3: Add import handler**

Add the `_import_codes` function inside `build()`, near the other handler functions. Use a hidden `ui.upload` element:

```python
            upload = ui.upload(
                on_upload=lambda e: _handle_upload(e),
                auto_upload=True,
            ).props('accept=".csv"').style("display: none;")

            def _import_codes():
                upload.run_method("pickFiles")

            async def _handle_upload(e):
                content = e.content.read().decode("utf-8-sig")
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".csv", delete=False, prefix="ace_import_"
                )
                tmp.write(content.encode("utf-8"))
                tmp.close()
                try:
                    count = import_codebook_from_csv(conn, tmp.name)
                    if count == 0:
                        ui.notify("No valid codes found in CSV.", type="warning")
                    else:
                        ui.notify(f"Imported {count} codes.", type="positive")
                        _refresh_codes()
                        code_list.refresh()
                except ValueError as ex:
                    ui.notify(str(ex), type="negative")
                except Exception as ex:
                    ui.notify(f"Import failed: {ex}", type="negative")
                finally:
                    Path(tmp.name).unlink(missing_ok=True)
                    upload.reset()
```

- [ ] **Step 4: Add export handler**

```python
            def _export_codes():
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".csv", delete=False, prefix="ace_codes_"
                )
                tmp.close()
                count = export_codebook_to_csv(conn, tmp.name)
                if count == 0:
                    ui.notify("No codes to export.", type="info")
                    Path(tmp.name).unlink(missing_ok=True)
                    return
                ui.download(tmp.name, "codes.csv")
```

- [ ] **Step 5: Add empty state to code_list refreshable**

In the `code_list()` refreshable function (around line 308), add an empty state before the `for` loop:

```python
            @ui.refreshable
            def code_list():
                sorting = state.get("sort_codes", False)
                if not codes:
                    ui.label("No codes yet. Type above to add one, or ").classes(
                        "text-caption text-grey-6"
                    )
                    ui.link("import from CSV", target="").classes(
                        "text-caption"
                    ).on("click", lambda: _import_codes(), [])
                    return
                with ui.element("div").classes("full-width ace-code-list").style("flex-shrink: 0;"):
                    # ... existing code list rendering ...
```

Note: The exact approach for the clickable link may need adaptation — `ui.link` with empty target + click handler is one option. An alternative is using `ui.html(sanitize=False)` with an inline `<a>` tag. Choose whichever integrates cleanly.

- [ ] **Step 6: Conditionally enable/disable menu items**

Update the menu items to respect the constraints:
- Import: disabled when codes exist
- Export: disabled when no codes exist

```python
                        import_item = ui.menu_item(
                            "Import CSV...",
                            on_click=lambda: _import_codes(),
                        )
                        if codes:
                            import_item.props("disable")

                        export_item = ui.menu_item(
                            "Export CSV",
                            on_click=lambda: _export_codes(),
                        )
                        if not codes:
                            export_item.props("disable")
```

- [ ] **Step 7: Verify manually**

Run: `uv run ace`

Verify:
- More-vert menu appears in Codes header
- With no codes: empty state shows "No codes yet..." with clickable "import from CSV"
- Import CSV with name-only → codes appear with auto-assigned colours
- Import disabled when codes exist
- Export CSV → downloads `codes.csv` with name, description, colour columns
- Export disabled when no codes
- Round-trip: export then import into a fresh project preserves all data

- [ ] **Step 8: Run all tests**

Run: `uv run pytest -q`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add src/ace/pages/coding.py
git commit -m "feat: add CSV import/export UI for codebook"
```
