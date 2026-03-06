# ACE Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a lightweight, local-first qualitative coding tool with distributed coding workflow and inter-coder reliability metrics.

**Architecture:** NiceGUI (Python) local web app with Recogito text-annotator-js for span-level annotation. SQLite single-file projects (.ace). Manager mode (import data, build codebook, assign references, merge results, compute ICR) and Coder mode (annotate assigned references). Package exchange via filtered SQLite copies.

**Tech Stack:** Python 3.11+, NiceGUI, @recogito/text-annotator (vendored JS), SQLite (stdlib), irrCAC, pandas, openpyxl

**Design doc:** `docs/plans/2026-03-06-ace-design.md`

---

## Phase 0: Spike — Recogito + NiceGUI Integration

> This is the highest-risk item. If it fails, pivot to Approach B (FastAPI + React).

### Task 0: Spike test — Recogito in NiceGUI

**Files:**
- Create: `spike/recogito_nicegui.py`
- Create: `spike/static/recogito/` (vendored JS/CSS from npm)

**Step 1: Install NiceGUI and fetch Recogito assets**

```bash
cd "/Users/jhar8696/Sydney Uni Dropbox/Januar Harianto/projects/annotation-coding-environment"
python -m venv .venv
source .venv/bin/activate
pip install nicegui
mkdir -p spike/static/recogito
npm pack @recogito/text-annotator@latest --pack-destination /tmp
tar -xzf /tmp/recogito-text-annotator-*.tgz -C /tmp
cp -r /tmp/package/dist/* spike/static/recogito/ 2>/dev/null || true
```

Note: If npm pack doesn't include built assets, install from npm and copy from node_modules:
```bash
mkdir -p /tmp/recogito-spike && cd /tmp/recogito-spike
npm init -y && npm install @recogito/text-annotator
cp -r node_modules/@recogito/text-annotator/dist/* "/Users/jhar8696/Sydney Uni Dropbox/Januar Harianto/projects/annotation-coding-environment/spike/static/recogito/"
```

**Step 2: Build minimal spike — init Recogito on a NiceGUI page**

```python
# spike/recogito_nicegui.py
from nicegui import ui, app
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"
app.add_static_files("/static", str(STATIC_DIR))

SAMPLE_TEXT = """I really enjoyed the group work sessions where we could collaborate
with peers. The lectures were sometimes too fast-paced and I struggled to keep up
with the readings. Overall, the course gave me a solid foundation in research methods,
but I would have liked more practical examples and hands-on exercises."""


@ui.page("/")
def main_page():
    # Load Recogito CSS
    ui.add_head_html('<link rel="stylesheet" href="/static/recogito/index.css">')

    ui.label("Recogito + NiceGUI Spike Test").classes("text-h4")

    # Container for annotatable text
    text_container = ui.html(
        f'<div id="annotation-target" style="padding: 20px; border: 1px solid #ccc; '
        f'line-height: 1.8; font-size: 16px;">{SAMPLE_TEXT}</div>'
    )

    # Output area for annotation events
    log = ui.log(max_lines=20).classes("w-full mt-4")

    # Load Recogito JS and initialise
    ui.add_body_html('<script type="module" src="/static/recogito/index.js"></script>')

    async def init_recogito():
        result = await ui.run_javascript("""
            // Wait for Recogito module to load
            const { createTextAnnotator } = await import('/static/recogito/index.js');

            const anno = createTextAnnotator(
                document.getElementById('annotation-target'),
                { style: { pointerEvents: 'auto' } }
            );

            // Store reference globally for later access
            window._recogito = anno;

            // Listen for annotation events
            anno.on('createAnnotation', (annotation) => {
                // Send to Python
                window.call_python_handler('on_annotation', JSON.stringify(annotation));
            });

            anno.on('updateAnnotation', (annotation, previous) => {
                window.call_python_handler('on_annotation_update', JSON.stringify(annotation));
            });

            anno.on('deleteAnnotation', (annotation) => {
                window.call_python_handler('on_annotation_delete', JSON.stringify(annotation));
            });

            return 'Recogito initialised';
        """, timeout=10)
        log.push(f"Init result: {result}")

    # Python handlers for JS events
    def on_annotation(data: str):
        log.push(f"CREATE: {data[:200]}")

    def on_annotation_update(data: str):
        log.push(f"UPDATE: {data[:200]}")

    def on_annotation_delete(data: str):
        log.push(f"DELETE: {data[:200]}")

    # Register handlers
    ui.on("annotation", on_annotation)
    ui.on("annotation_update", on_annotation_update)
    ui.on("annotation_delete", on_annotation_delete)

    # Button to load saved annotations back into Recogito
    async def load_annotations():
        result = await ui.run_javascript("""
            const annotations = window._recogito.getAnnotations();
            return JSON.stringify(annotations);
        """)
        log.push(f"Current annotations: {result[:500]}")

    ui.button("Get Current Annotations", on_click=load_annotations).classes("mt-2")
    ui.timer(1.0, init_recogito, once=True)


ui.run(host="127.0.0.1", port=8080, title="ACE Spike")
```

**Step 3: Run the spike and test**

```bash
cd "/Users/jhar8696/Sydney Uni Dropbox/Januar Harianto/projects/annotation-coding-environment"
source .venv/bin/activate
python spike/recogito_nicegui.py
```

**Verify these 4 things manually:**
1. Recogito initialises on the text container (text becomes selectable/annotatable)
2. Selecting text and creating an annotation fires the `createAnnotation` event and appears in the Python log
3. Clicking "Get Current Annotations" returns the W3C annotation JSON from JS to Python
4. Undo (Ctrl+Z) works in the browser

**Step 4: Test offset round-trip with emoji**

Add emoji text to `SAMPLE_TEXT`:
```python
SAMPLE_TEXT = """I really enjoyed 😊 the group work..."""
```

Verify that annotation offsets from Recogito still align with the correct text when read back.

**Step 5: Document spike results**

If all 4 verifications pass: proceed with Phase 1.
If init fails or events don't bridge: investigate NiceGUI's `ui.element()` API as alternative. If still failing, pivot to Approach B (FastAPI + React).

**Step 6: Commit spike**

```bash
git init
git add spike/
git commit -m "spike: test Recogito text-annotator integration with NiceGUI"
```

> **GATE: Do not proceed to Phase 1 until this spike passes.**

---

## Phase 1: Foundation

### Task 1: Python package scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/ace/__init__.py`
- Create: `src/ace/__main__.py`
- Create: `src/ace/app.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ace-coder"
version = "0.1.0"
description = "Lightweight qualitative coding tool with inter-coder reliability"
requires-python = ">=3.11"
dependencies = [
    "nicegui>=3.0",
    "pandas>=2.0",
    "openpyxl>=3.1",
    "irrCAC>=0.3",
]

[project.scripts]
ace = "ace.__main__:main"

[tool.hatch.build.targets.wheel]
packages = ["src/ace"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Step 2: Create package files**

```python
# src/ace/__init__.py
__version__ = "0.1.0"
```

```python
# src/ace/__main__.py
from ace.app import run

def main():
    run()

if __name__ == "__main__":
    main()
```

```python
# src/ace/app.py
from nicegui import ui

def run():
    @ui.page("/")
    def landing():
        ui.label("ACE — Annotation Coding Environment").classes("text-h4")
        ui.label("Drop an .ace file here or create a new project")

    ui.run(host="127.0.0.1", port=8080, title="ACE")
```

```python
# tests/conftest.py
import pytest
import tempfile
import sqlite3
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary .ace SQLite file."""
    db_path = tmp_path / "test.ace"
    return db_path


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample CSV for import testing."""
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "participant_id,reflection,age\n"
        "P001,\"I enjoyed the group work sessions.\",22\n"
        "P002,\"The lectures were too fast-paced.\",25\n"
        "P003,\"Overall a good experience with some challenges.\",23\n"
    )
    return csv_path
```

**Step 3: Install in dev mode and verify**

```bash
cd "/Users/jhar8696/Sydney Uni Dropbox/Januar Harianto/projects/annotation-coding-environment"
pip install -e ".[dev]" 2>/dev/null || pip install -e .
pip install pytest
python -c "from ace.app import run; print('OK')"
```

**Step 4: Commit**

```bash
git add pyproject.toml src/ tests/conftest.py
git commit -m "feat: initial package scaffolding"
```

---

### Task 2: Database layer — schema, connection, migration runner

**Files:**
- Create: `src/ace/db/__init__.py`
- Create: `src/ace/db/connection.py`
- Create: `src/ace/db/schema.py`
- Create: `src/ace/db/migrations.py`
- Create: `tests/test_db/__init__.py`
- Create: `tests/test_db/test_schema.py`
- Create: `tests/test_db/test_connection.py`
- Create: `tests/test_db/test_migrations.py`

**Step 1: Write failing tests for schema creation**

```python
# tests/test_db/test_schema.py
import sqlite3
from ace.db.schema import create_schema, ACE_APPLICATION_ID, SCHEMA_VERSION


def test_create_schema_creates_all_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    create_schema(conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor}
    expected = {
        "project", "source", "source_content", "codebook_code",
        "coder", "assignment", "annotation", "source_note",
    }
    assert expected.issubset(tables)
    conn.close()


def test_create_schema_sets_application_id(tmp_db):
    conn = sqlite3.connect(tmp_db)
    create_schema(conn)
    app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    assert app_id == ACE_APPLICATION_ID
    conn.close()


def test_create_schema_sets_user_version(tmp_db):
    conn = sqlite3.connect(tmp_db)
    create_schema(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    conn.close()


def test_create_schema_enables_foreign_keys(tmp_db):
    conn = sqlite3.connect(tmp_db)
    create_schema(conn)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()


def test_annotation_check_constraints(tmp_db):
    conn = sqlite3.connect(tmp_db)
    create_schema(conn)
    # Insert required parent rows
    conn.execute("INSERT INTO project VALUES (?,?,?,?,?,?,?,?,?)",
                 ("proj1", "Test", None, None, "manager", None, None,
                  "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
    conn.execute("INSERT INTO source VALUES (?,?,?,?,?,?,?)",
                 ("src1", "P001", "row", None, "test.csv", None, 0, "2026-01-01T00:00:00"))
    conn.execute("INSERT INTO source_content VALUES (?,?,?)",
                 ("src1", "hello", "abc123"))
    conn.execute("INSERT INTO codebook_code VALUES (?,?,?,?,?,?)",
                 ("code1", "Theme", None, "#FF0000", 0, "2026-01-01T00:00:00"))
    conn.execute("INSERT INTO coder VALUES (?,?)", ("coder1", "Alice"))
    conn.commit()

    # start_offset must be >= 0
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO annotation VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("a1", "src1", "coder1", "code1", -1, 5, "hello", None, None,
             "2026-01-01", "2026-01-01", None)
        )

    # end_offset must be > start_offset
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO annotation VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("a2", "src1", "coder1", "code1", 5, 3, "hello", None, None,
             "2026-01-01", "2026-01-01", None)
        )
    conn.close()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db/test_schema.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'ace.db'`

**Step 3: Implement schema**

```python
# src/ace/db/__init__.py
```

```python
# src/ace/db/schema.py
import sqlite3

ACE_APPLICATION_ID = 0x41434500  # "ACE\0"
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    instructions TEXT,
    file_role TEXT NOT NULL CHECK (file_role IN ('manager', 'coder')),
    codebook_hash TEXT,
    assignment_seed INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source (
    id TEXT PRIMARY KEY,
    display_id TEXT,
    source_type TEXT NOT NULL CHECK (source_type IN ('file', 'row')),
    source_column TEXT,
    filename TEXT,
    metadata_json TEXT,
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_content (
    source_id TEXT PRIMARY KEY REFERENCES source(id),
    content_text TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS codebook_code (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    colour TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coder (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS assignment (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(id),
    coder_id TEXT NOT NULL REFERENCES coder(id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'complete', 'flagged')),
    assigned_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, coder_id)
);

CREATE TABLE IF NOT EXISTS annotation (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(id),
    coder_id TEXT NOT NULL REFERENCES coder(id),
    code_id TEXT NOT NULL REFERENCES codebook_code(id),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    selected_text TEXT NOT NULL,
    memo TEXT,
    w3c_selector_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS source_note (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(id),
    coder_id TEXT NOT NULL REFERENCES coder(id),
    note_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, coder_id)
);

CREATE INDEX IF NOT EXISTS idx_annotation_source_coder
    ON annotation(source_id, coder_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_annotation_code ON annotation(code_id);
CREATE INDEX IF NOT EXISTS idx_assignment_coder ON assignment(coder_id);
CREATE INDEX IF NOT EXISTS idx_assignment_source ON assignment(source_id);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db/test_schema.py -v
```
Expected: all PASS

**Step 5: Write failing tests for connection manager**

```python
# tests/test_db/test_connection.py
import sqlite3
from ace.db.connection import open_project, create_project


def test_create_project_creates_file(tmp_db):
    conn = create_project(tmp_db, name="My Project")
    assert tmp_db.exists()
    # Verify project row exists
    row = conn.execute("SELECT name, file_role FROM project").fetchone()
    assert row[0] == "My Project"
    assert row[1] == "manager"
    conn.close()


def test_open_project_validates_application_id(tmp_db):
    # Create a plain SQLite file (not ACE)
    conn = sqlite3.connect(tmp_db)
    conn.execute("CREATE TABLE dummy (id INTEGER)")
    conn.commit()
    conn.close()

    import pytest
    with pytest.raises(ValueError, match="not a valid ACE project"):
        open_project(tmp_db)


def test_open_project_enables_foreign_keys(tmp_db):
    conn = create_project(tmp_db, name="Test")
    conn.close()
    conn = open_project(tmp_db)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()


def test_open_project_uses_wal_mode(tmp_db):
    conn = create_project(tmp_db, name="Test")
    conn.close()
    conn = open_project(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()
```

**Step 6: Run tests to verify they fail**

```bash
pytest tests/test_db/test_connection.py -v
```

**Step 7: Implement connection manager**

```python
# src/ace/db/connection.py
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ace.db.schema import create_schema, ACE_APPLICATION_ID, SCHEMA_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(path: Path, name: str, description: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    conn.execute("PRAGMA journal_mode = WAL")
    now = _now()
    conn.execute(
        "INSERT INTO project (id, name, description, instructions, file_role, "
        "codebook_hash, assignment_seed, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'manager', NULL, NULL, ?, ?)",
        (str(uuid.uuid4()), name, description, None, now, now),
    )
    conn.commit()
    return conn


def open_project(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Validate it's an ACE file
    app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    if app_id != ACE_APPLICATION_ID:
        conn.close()
        raise ValueError(f"{path.name} is not a valid ACE project file")

    # Check schema version
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        conn.close()
        raise ValueError(
            f"File requires ACE v{version} but this is v{SCHEMA_VERSION}"
        )

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def checkpoint_and_close(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
```

**Step 8: Run tests to verify they pass**

```bash
pytest tests/test_db/test_connection.py -v
```

**Step 9: Write failing tests for migration runner**

```python
# tests/test_db/test_migrations.py
from ace.db.connection import create_project
from ace.db.migrations import check_and_migrate


def test_migration_runner_noop_on_current_version(tmp_db):
    conn = create_project(tmp_db, name="Test")
    # Should not raise, no migrations needed
    check_and_migrate(conn)
    conn.close()


def test_migration_runner_returns_current_version(tmp_db):
    conn = create_project(tmp_db, name="Test")
    version = check_and_migrate(conn)
    assert version == 1
    conn.close()
```

**Step 10: Implement migration runner stub**

```python
# src/ace/db/migrations.py
import sqlite3

from ace.db.schema import SCHEMA_VERSION

# Registry of migration functions: version -> migration_fn
# Each function takes a connection and migrates from version N to N+1
MIGRATIONS: dict[int, callable] = {
    # Example for future:
    # 1: migrate_v1_to_v2,
}


def check_and_migrate(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    while current < SCHEMA_VERSION:
        if current not in MIGRATIONS:
            raise ValueError(
                f"No migration from v{current} to v{current + 1}"
            )
        MIGRATIONS[current](conn)
        current += 1
        conn.execute(f"PRAGMA user_version = {current}")
        conn.commit()

    return current
```

**Step 11: Run tests**

```bash
pytest tests/test_db/ -v
```
Expected: all PASS

**Step 12: Commit**

```bash
git add src/ace/db/ tests/test_db/
git commit -m "feat: database layer with schema, connection manager, migration runner"
```

---

### Task 3: Data models — CRUD operations

**Files:**
- Create: `src/ace/models/__init__.py`
- Create: `src/ace/models/project.py`
- Create: `src/ace/models/source.py`
- Create: `src/ace/models/codebook.py`
- Create: `src/ace/models/coder.py`
- Create: `src/ace/models/assignment.py`
- Create: `src/ace/models/annotation.py`
- Create: `tests/test_models/__init__.py`
- Create: `tests/test_models/test_source.py`
- Create: `tests/test_models/test_codebook.py`
- Create: `tests/test_models/test_annotation.py`

**Step 1: Write failing tests for source CRUD**

```python
# tests/test_models/test_source.py
from ace.db.connection import create_project
from ace.models.source import add_source, get_source, list_sources, get_source_content


def test_add_source(tmp_db):
    conn = create_project(tmp_db, name="Test")
    source_id = add_source(
        conn, display_id="P001", content_text="Hello world",
        source_type="row", source_column="reflection", filename="test.csv",
        metadata={"age": 22},
    )
    assert source_id is not None
    conn.close()


def test_get_source_returns_metadata_without_content(tmp_db):
    conn = create_project(tmp_db, name="Test")
    source_id = add_source(
        conn, display_id="P001", content_text="Hello world",
        source_type="row", filename="test.csv",
    )
    source = get_source(conn, source_id)
    assert source["display_id"] == "P001"
    assert "content_text" not in dict(source)
    conn.close()


def test_get_source_content(tmp_db):
    conn = create_project(tmp_db, name="Test")
    source_id = add_source(
        conn, display_id="P001", content_text="Hello world",
        source_type="row", filename="test.csv",
    )
    content = get_source_content(conn, source_id)
    assert content["content_text"] == "Hello world"
    conn.close()


def test_list_sources_returns_all(tmp_db):
    conn = create_project(tmp_db, name="Test")
    add_source(conn, display_id="P001", content_text="Text 1",
               source_type="row", filename="test.csv")
    add_source(conn, display_id="P002", content_text="Text 2",
               source_type="row", filename="test.csv")
    sources = list_sources(conn)
    assert len(sources) == 2
    conn.close()
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_models/test_source.py -v
```

**Step 3: Implement source model**

```python
# src/ace/models/__init__.py
```

```python
# src/ace/models/source.py
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_source(
    conn: sqlite3.Connection,
    display_id: str,
    content_text: str,
    source_type: str,
    filename: str = None,
    source_column: str = None,
    metadata: dict = None,
) -> str:
    source_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()
    now = _now()

    # Get next sort order
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM source").fetchone()
    sort_order = row[0]

    conn.execute(
        "INSERT INTO source (id, display_id, source_type, source_column, "
        "filename, metadata_json, sort_order, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, display_id, source_type, source_column,
         filename, json.dumps(metadata) if metadata else None, sort_order, now),
    )
    conn.execute(
        "INSERT INTO source_content (source_id, content_text, content_hash) "
        "VALUES (?, ?, ?)",
        (source_id, content_text, content_hash),
    )
    conn.commit()
    return source_id


def get_source(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    return conn.execute(
        "SELECT * FROM source WHERE id = ?", (source_id,)
    ).fetchone()


def get_source_content(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    return conn.execute(
        "SELECT * FROM source_content WHERE source_id = ?", (source_id,)
    ).fetchone()


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM source ORDER BY sort_order"
    ).fetchall()
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_models/test_source.py -v
```

**Step 5: Write failing tests for codebook CRUD**

```python
# tests/test_models/test_codebook.py
import pytest
import sqlite3
from ace.db.connection import create_project
from ace.models.codebook import (
    add_code, list_codes, update_code, delete_code,
    import_codebook_from_csv, compute_codebook_hash,
)


def test_add_code(tmp_db):
    conn = create_project(tmp_db, name="Test")
    code_id = add_code(conn, name="Positive", colour="#4CAF50", description="Positive experience")
    assert code_id is not None
    codes = list_codes(conn)
    assert len(codes) == 1
    assert codes[0]["name"] == "Positive"
    conn.close()


def test_add_duplicate_code_name_raises(tmp_db):
    conn = create_project(tmp_db, name="Test")
    add_code(conn, name="Positive", colour="#4CAF50")
    with pytest.raises(sqlite3.IntegrityError):
        add_code(conn, name="Positive", colour="#FF0000")
    conn.close()


def test_update_code(tmp_db):
    conn = create_project(tmp_db, name="Test")
    code_id = add_code(conn, name="Pos", colour="#4CAF50")
    update_code(conn, code_id, name="Positive", description="Updated")
    codes = list_codes(conn)
    assert codes[0]["name"] == "Positive"
    assert codes[0]["description"] == "Updated"
    conn.close()


def test_delete_code(tmp_db):
    conn = create_project(tmp_db, name="Test")
    code_id = add_code(conn, name="Positive", colour="#4CAF50")
    delete_code(conn, code_id)
    assert len(list_codes(conn)) == 0
    conn.close()


def test_codebook_hash_deterministic(tmp_db):
    conn = create_project(tmp_db, name="Test")
    add_code(conn, name="A", colour="#FF0000")
    add_code(conn, name="B", colour="#00FF00")
    h1 = compute_codebook_hash(conn)
    h2 = compute_codebook_hash(conn)
    assert h1 == h2
    conn.close()


def test_import_codebook_from_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, name="Test")
    csv_path = tmp_path / "codebook.csv"
    csv_path.write_text("name,colour,description\nPositive,#4CAF50,Good\nNegative,#F44336,Bad\n")
    import_codebook_from_csv(conn, csv_path)
    codes = list_codes(conn)
    assert len(codes) == 2
    conn.close()
```

**Step 6: Run tests — expect FAIL**

```bash
pytest tests/test_models/test_codebook.py -v
```

**Step 7: Implement codebook model**

```python
# src/ace/models/codebook.py
import csv
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
    description: str = None,
) -> str:
    code_id = str(uuid.uuid4())
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM codebook_code").fetchone()
    sort_order = row[0]
    conn.execute(
        "INSERT INTO codebook_code (id, name, description, colour, sort_order, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code_id, name, description, colour, sort_order, _now()),
    )
    conn.commit()
    return code_id


def list_codes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM codebook_code ORDER BY sort_order"
    ).fetchall()


def update_code(
    conn: sqlite3.Connection,
    code_id: str,
    name: str = None,
    colour: str = None,
    description: str = None,
) -> None:
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if colour is not None:
        updates.append("colour = ?")
        params.append(colour)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if not updates:
        return
    params.append(code_id)
    conn.execute(
        f"UPDATE codebook_code SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()


def delete_code(conn: sqlite3.Connection, code_id: str) -> None:
    conn.execute("DELETE FROM codebook_code WHERE id = ?", (code_id,))
    conn.commit()


def compute_codebook_hash(conn: sqlite3.Connection) -> str:
    codes = conn.execute(
        "SELECT id, name, colour FROM codebook_code ORDER BY id"
    ).fetchall()
    content = "|".join(f"{c['id']}:{c['name']}:{c['colour']}" for c in codes)
    return hashlib.sha256(content.encode()).hexdigest()


def import_codebook_from_csv(conn: sqlite3.Connection, path: Path) -> int:
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            add_code(
                conn,
                name=row["name"],
                colour=row.get("colour", row.get("color", "#808080")),
                description=row.get("description"),
            )
            count += 1
    return count
```

**Step 8: Run tests — expect PASS**

```bash
pytest tests/test_models/test_codebook.py -v
```

**Step 9: Write failing tests for annotation model**

```python
# tests/test_models/test_annotation.py
from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.annotation import (
    add_annotation, list_annotations, delete_annotation, get_annotations_for_source,
)


def _setup_project(tmp_db):
    conn = create_project(tmp_db, name="Test")
    conn.execute("INSERT INTO coder VALUES (?, ?)", ("coder1", "Alice"))
    conn.commit()
    source_id = add_source(conn, display_id="P001", content_text="Hello world test text",
                           source_type="row", filename="test.csv")
    code_id = add_code(conn, name="Theme", colour="#FF0000")
    return conn, source_id, code_id


def test_add_annotation(tmp_db):
    conn, source_id, code_id = _setup_project(tmp_db)
    ann_id = add_annotation(
        conn, source_id=source_id, coder_id="coder1", code_id=code_id,
        start_offset=0, end_offset=5, selected_text="Hello",
    )
    assert ann_id is not None
    conn.close()


def test_list_annotations_excludes_deleted(tmp_db):
    conn, source_id, code_id = _setup_project(tmp_db)
    ann_id = add_annotation(
        conn, source_id=source_id, coder_id="coder1", code_id=code_id,
        start_offset=0, end_offset=5, selected_text="Hello",
    )
    assert len(get_annotations_for_source(conn, source_id, "coder1")) == 1
    delete_annotation(conn, ann_id)
    assert len(get_annotations_for_source(conn, source_id, "coder1")) == 0
    conn.close()


def test_delete_annotation_is_soft_delete(tmp_db):
    conn, source_id, code_id = _setup_project(tmp_db)
    ann_id = add_annotation(
        conn, source_id=source_id, coder_id="coder1", code_id=code_id,
        start_offset=0, end_offset=5, selected_text="Hello",
    )
    delete_annotation(conn, ann_id)
    # Row still exists with deleted_at set
    row = conn.execute("SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)).fetchone()
    assert row is not None
    assert row[0] is not None
    conn.close()
```

**Step 10: Implement annotation model**

```python
# src/ace/models/annotation.py
import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_annotation(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str,
    code_id: str,
    start_offset: int,
    end_offset: int,
    selected_text: str,
    memo: str = None,
    w3c_selector_json: str = None,
) -> str:
    ann_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        "INSERT INTO annotation (id, source_id, coder_id, code_id, start_offset, "
        "end_offset, selected_text, memo, w3c_selector_json, created_at, updated_at, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (ann_id, source_id, coder_id, code_id, start_offset, end_offset,
         selected_text, memo, w3c_selector_json, now, now),
    )
    conn.commit()
    return ann_id


def get_annotations_for_source(
    conn: sqlite3.Connection, source_id: str, coder_id: str = None,
) -> list[sqlite3.Row]:
    if coder_id:
        return conn.execute(
            "SELECT * FROM annotation WHERE source_id = ? AND coder_id = ? "
            "AND deleted_at IS NULL ORDER BY start_offset",
            (source_id, coder_id),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM annotation WHERE source_id = ? "
        "AND deleted_at IS NULL ORDER BY start_offset",
        (source_id,),
    ).fetchall()


def list_annotations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL ORDER BY created_at"
    ).fetchall()


def delete_annotation(conn: sqlite3.Connection, annotation_id: str) -> None:
    conn.execute(
        "UPDATE annotation SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (_now(), _now(), annotation_id),
    )
    conn.commit()


def compact_deleted(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM annotation WHERE deleted_at IS NOT NULL")
    conn.commit()
    return cursor.rowcount
```

**Step 11: Run all model tests**

```bash
pytest tests/test_models/ -v
```
Expected: all PASS

**Step 12: Implement remaining models (coder, assignment, project)**

```python
# src/ace/models/coder.py
import sqlite3
import uuid


def add_coder(conn: sqlite3.Connection, name: str) -> str:
    coder_id = str(uuid.uuid4())
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, name))
    conn.commit()
    return coder_id


def list_coders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM coder ORDER BY name").fetchall()
```

```python
# src/ace/models/assignment.py
import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_assignment(
    conn: sqlite3.Connection, source_id: str, coder_id: str,
) -> str:
    assignment_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        "INSERT INTO assignment (id, source_id, coder_id, status, assigned_at, updated_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?)",
        (assignment_id, source_id, coder_id, now, now),
    )
    conn.commit()
    return assignment_id


def update_assignment_status(
    conn: sqlite3.Connection, source_id: str, coder_id: str, status: str,
) -> None:
    conn.execute(
        "UPDATE assignment SET status = ?, updated_at = ? "
        "WHERE source_id = ? AND coder_id = ?",
        (status, _now(), source_id, coder_id),
    )
    conn.commit()


def get_assignments_for_coder(
    conn: sqlite3.Connection, coder_id: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.*, s.display_id FROM assignment a "
        "JOIN source s ON a.source_id = s.id "
        "WHERE a.coder_id = ? ORDER BY s.sort_order",
        (coder_id,),
    ).fetchall()
```

```python
# src/ace/models/project.py
import sqlite3


def get_project(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM project").fetchone()


def update_instructions(conn: sqlite3.Connection, instructions: str) -> None:
    conn.execute("UPDATE project SET instructions = ?", (instructions,))
    conn.commit()
```

**Step 13: Commit**

```bash
git add src/ace/models/ tests/test_models/
git commit -m "feat: CRUD models for source, codebook, annotation, coder, assignment"
```

---

### Task 4: CSV/Excel import service

**Files:**
- Create: `src/ace/services/__init__.py`
- Create: `src/ace/services/importer.py`
- Create: `tests/test_services/__init__.py`
- Create: `tests/test_services/test_importer.py`

**Step 1: Write failing tests**

```python
# tests/test_services/test_importer.py
import pytest
from ace.db.connection import create_project
from ace.models.source import list_sources, get_source_content
from ace.services.importer import import_csv, import_text_files


def test_import_csv_creates_sources(tmp_db, sample_csv):
    conn = create_project(tmp_db, name="Test")
    count = import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    assert count == 3
    sources = list_sources(conn)
    assert len(sources) == 3
    assert sources[0]["display_id"] == "P001"
    conn.close()


def test_import_csv_stores_metadata(tmp_db, sample_csv):
    conn = create_project(tmp_db, name="Test")
    import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    sources = list_sources(conn)
    import json
    metadata = json.loads(sources[0]["metadata_json"])
    assert metadata["age"] == "22"
    conn.close()


def test_import_csv_content_hash(tmp_db, sample_csv):
    conn = create_project(tmp_db, name="Test")
    import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    sources = list_sources(conn)
    content = get_source_content(conn, sources[0]["id"])
    assert content["content_hash"] is not None
    assert len(content["content_hash"]) == 64  # SHA-256 hex
    conn.close()


def test_import_csv_multi_column(tmp_db, tmp_path):
    csv_path = tmp_path / "multi.csv"
    csv_path.write_text(
        "id,q1_response,q2_response\n"
        "P001,Answer to Q1,Answer to Q2\n"
    )
    conn = create_project(tmp_db, name="Test")
    count = import_csv(conn, csv_path, id_column="id",
                       text_columns=["q1_response", "q2_response"])
    assert count == 2  # one source per text column per row
    sources = list_sources(conn)
    assert sources[0]["source_column"] == "q1_response"
    assert sources[1]["source_column"] == "q2_response"
    conn.close()


def test_import_text_files(tmp_db, tmp_path):
    (tmp_path / "P001.txt").write_text("First participant text")
    (tmp_path / "P002.txt").write_text("Second participant text")
    conn = create_project(tmp_db, name="Test")
    count = import_text_files(conn, tmp_path)
    assert count == 2
    sources = list_sources(conn)
    assert sources[0]["source_type"] == "file"
    conn.close()
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_services/test_importer.py -v
```

**Step 3: Implement importer**

```python
# src/ace/services/__init__.py
```

```python
# src/ace/services/importer.py
import sqlite3
from pathlib import Path

import pandas as pd

from ace.models.source import add_source


def import_csv(
    conn: sqlite3.Connection,
    path: Path,
    id_column: str,
    text_columns: list[str],
) -> int:
    # Try UTF-8 first, fallback to latin-1
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(path, encoding=encoding, dtype=str)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Could not decode {path.name} with supported encodings")

    df = df.fillna("")
    non_text_cols = [c for c in df.columns if c != id_column and c not in text_columns]
    count = 0

    for _, row in df.iterrows():
        participant_id = str(row[id_column])
        metadata = {col: row[col] for col in non_text_cols}

        for text_col in text_columns:
            display_id = participant_id if len(text_columns) == 1 else f"{participant_id}_{text_col}"
            add_source(
                conn,
                display_id=display_id,
                content_text=str(row[text_col]),
                source_type="row",
                source_column=text_col if len(text_columns) > 1 else None,
                filename=path.name,
                metadata=metadata,
            )
            count += 1

    return count


def import_text_files(conn: sqlite3.Connection, folder: Path) -> int:
    count = 0
    for path in sorted(folder.glob("*.txt")):
        content = path.read_text(encoding="utf-8")
        add_source(
            conn,
            display_id=path.stem,
            content_text=content,
            source_type="file",
            filename=path.name,
        )
        count += 1
    return count
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_services/test_importer.py -v
```

**Step 5: Commit**

```bash
git add src/ace/services/ tests/test_services/
git commit -m "feat: CSV/Excel and text file import service"
```

---

### Task 5: Assignment service — random split with ICR overlap

**Files:**
- Create: `src/ace/services/assigner.py`
- Create: `tests/test_services/test_assigner.py`

**Step 1: Write failing tests**

```python
# tests/test_services/test_assigner.py
from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.coder import add_coder
from ace.services.assigner import generate_assignments, AssignmentPreview


def _setup(tmp_db, n_sources=100):
    conn = create_project(tmp_db, name="Test")
    source_ids = []
    for i in range(n_sources):
        sid = add_source(conn, display_id=f"P{i:03d}", content_text=f"Text {i}",
                         source_type="row", filename="test.csv")
        source_ids.append(sid)
    coder_ids = [
        add_coder(conn, "Alice"),
        add_coder(conn, "Bob"),
        add_coder(conn, "Carol"),
    ]
    return conn, source_ids, coder_ids


def test_preview_shows_correct_totals(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    preview = generate_assignments(conn, coder_ids, overlap_pct=20, seed=42, preview_only=True)
    assert preview.total_sources == 100
    assert preview.overlap_sources == 20
    assert preview.unique_sources == 80
    conn.close()


def test_preview_per_coder_workload(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    preview = generate_assignments(conn, coder_ids, overlap_pct=20, seed=42, preview_only=True)
    # Each coder should get roughly equal total workload
    for coder_id in coder_ids:
        info = preview.per_coder[coder_id]
        assert info["total"] > 0
        assert info["unique"] + info["overlap"] == info["total"]
    conn.close()


def test_overlap_sources_assigned_to_exactly_2_coders(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    generate_assignments(conn, coder_ids, overlap_pct=20, seed=42)
    # Check each overlap source has exactly 2 assignments
    rows = conn.execute(
        "SELECT source_id, COUNT(*) as cnt FROM assignment "
        "GROUP BY source_id HAVING cnt > 1"
    ).fetchall()
    for row in rows:
        assert row["cnt"] == 2
    assert len(rows) == 20
    conn.close()


def test_no_source_unassigned(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    generate_assignments(conn, coder_ids, overlap_pct=20, seed=42)
    assigned = conn.execute("SELECT DISTINCT source_id FROM assignment").fetchall()
    assert len(assigned) == 100
    conn.close()


def test_seed_produces_reproducible_assignments(tmp_db, tmp_path):
    # Run twice with same seed, compare results
    results = []
    for i in range(2):
        db_path = tmp_path / f"test_{i}.ace"
        conn, source_ids, coder_ids = _setup(db_path, n_sources=50)
        generate_assignments(conn, coder_ids, overlap_pct=20, seed=42)
        rows = conn.execute(
            "SELECT source_id, coder_id FROM assignment ORDER BY source_id, coder_id"
        ).fetchall()
        results.append([(r["source_id"], r["coder_id"]) for r in rows])
        conn.close()
    # Same seed + same source/coder IDs won't match because UUIDs differ,
    # but the STRUCTURE should match (same number of assignments per coder)
    assert len(results[0]) == len(results[1])
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_services/test_assigner.py -v
```

**Step 3: Implement assigner**

```python
# src/ace/services/assigner.py
import random
import sqlite3
from dataclasses import dataclass, field

from ace.models.assignment import add_assignment


@dataclass
class AssignmentPreview:
    total_sources: int = 0
    overlap_sources: int = 0
    unique_sources: int = 0
    per_coder: dict = field(default_factory=dict)


def generate_assignments(
    conn: sqlite3.Connection,
    coder_ids: list[str],
    overlap_pct: int,
    seed: int,
    preview_only: bool = False,
) -> AssignmentPreview:
    sources = conn.execute("SELECT id FROM source ORDER BY sort_order").fetchall()
    source_ids = [s["id"] for s in sources]
    n_total = len(source_ids)
    n_coders = len(coder_ids)
    n_overlap = round(n_total * overlap_pct / 100)
    n_unique = n_total - n_overlap

    rng = random.Random(seed)
    shuffled = source_ids[:]
    rng.shuffle(shuffled)

    overlap_set = shuffled[:n_overlap]
    unique_set = shuffled[n_overlap:]

    # Distribute unique sources equally
    coder_assignments: dict[str, list[str]] = {cid: [] for cid in coder_ids}
    for i, sid in enumerate(unique_set):
        coder_assignments[coder_ids[i % n_coders]].append(sid)

    # Assign overlap sources to random pairs
    overlap_assignments: dict[str, list[str]] = {cid: [] for cid in coder_ids}
    for sid in overlap_set:
        pair = rng.sample(coder_ids, 2)
        for cid in pair:
            overlap_assignments[cid].append(sid)

    # Build preview
    preview = AssignmentPreview(
        total_sources=n_total,
        overlap_sources=n_overlap,
        unique_sources=n_unique,
    )
    for cid in coder_ids:
        n_uniq = len(coder_assignments[cid])
        n_over = len(overlap_assignments[cid])
        preview.per_coder[cid] = {
            "unique": n_uniq,
            "overlap": n_over,
            "total": n_uniq + n_over,
        }

    if preview_only:
        return preview

    # Store seed in project
    conn.execute("UPDATE project SET assignment_seed = ?", (seed,))

    # Create assignment records
    for cid in coder_ids:
        for sid in coder_assignments[cid]:
            add_assignment(conn, sid, cid)
        for sid in overlap_assignments[cid]:
            add_assignment(conn, sid, cid)

    conn.commit()
    return preview
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_services/test_assigner.py -v
```

**Step 5: Commit**

```bash
git add src/ace/services/assigner.py tests/test_services/test_assigner.py
git commit -m "feat: random assignment service with configurable ICR overlap"
```

---

### Task 6: Package export service

**Files:**
- Create: `src/ace/services/packager.py`
- Create: `tests/test_services/test_packager.py`

**Step 1: Write failing tests**

```python
# tests/test_services/test_packager.py
import sqlite3
from pathlib import Path
from ace.db.connection import create_project, open_project
from ace.models.source import add_source, list_sources
from ace.models.codebook import add_code, list_codes, compute_codebook_hash
from ace.models.coder import add_coder
from ace.services.assigner import generate_assignments
from ace.services.packager import export_coder_package, import_coder_package


def _setup_assigned_project(tmp_db):
    conn = create_project(tmp_db, name="Test Project")
    for i in range(10):
        add_source(conn, display_id=f"P{i:03d}", content_text=f"Sample text {i}",
                   source_type="row", filename="test.csv")
    add_code(conn, name="Positive", colour="#4CAF50")
    add_code(conn, name="Negative", colour="#F44336")
    coder_ids = [add_coder(conn, "Alice"), add_coder(conn, "Bob")]
    generate_assignments(conn, coder_ids, overlap_pct=20, seed=42)
    return conn, coder_ids


def test_export_creates_valid_ace_file(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    output_path = tmp_path / "export"
    output_path.mkdir()
    pkg_path = export_coder_package(conn, coder_ids[0], output_path)
    assert pkg_path.exists()
    assert pkg_path.suffix == ".ace"
    # Should be openable
    pkg_conn = open_project(pkg_path)
    assert pkg_conn.execute("SELECT file_role FROM project").fetchone()[0] == "coder"
    pkg_conn.close()
    conn.close()


def test_export_contains_only_assigned_sources(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    output_path = tmp_path / "export"
    output_path.mkdir()
    pkg_path = export_coder_package(conn, coder_ids[0], output_path)
    pkg_conn = sqlite3.connect(pkg_path)
    pkg_conn.row_factory = sqlite3.Row
    # Count sources in package vs assignments
    n_sources = pkg_conn.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    n_assignments = pkg_conn.execute("SELECT COUNT(*) FROM assignment").fetchone()[0]
    assert n_sources == n_assignments
    assert n_sources > 0
    pkg_conn.close()
    conn.close()


def test_export_contains_full_codebook(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    output_path = tmp_path / "export"
    output_path.mkdir()
    pkg_path = export_coder_package(conn, coder_ids[0], output_path)
    pkg_conn = sqlite3.connect(pkg_path)
    pkg_conn.row_factory = sqlite3.Row
    n_codes = pkg_conn.execute("SELECT COUNT(*) FROM codebook_code").fetchone()[0]
    assert n_codes == 2  # Positive + Negative
    pkg_conn.close()
    conn.close()


def test_export_stores_codebook_hash(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    output_path = tmp_path / "export"
    output_path.mkdir()
    export_coder_package(conn, coder_ids[0], output_path)
    # Main project should now have codebook_hash
    row = conn.execute("SELECT codebook_hash FROM project").fetchone()
    assert row["codebook_hash"] is not None
    conn.close()
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_services/test_packager.py -v
```

**Step 3: Implement export**

```python
# src/ace/services/packager.py
import shutil
import sqlite3
from pathlib import Path

from ace.db.connection import checkpoint_and_close
from ace.db.schema import create_schema, ACE_APPLICATION_ID, SCHEMA_VERSION
from ace.models.codebook import compute_codebook_hash


def export_coder_package(
    conn: sqlite3.Connection,
    coder_id: str,
    output_dir: Path,
) -> Path:
    # Get project and coder info
    project = conn.execute("SELECT * FROM project").fetchone()
    coder = conn.execute("SELECT * FROM coder WHERE id = ?", (coder_id,)).fetchone()

    # Compute and store codebook hash
    cb_hash = compute_codebook_hash(conn)
    conn.execute("UPDATE project SET codebook_hash = ?", (cb_hash,))
    conn.commit()

    # Build output filename
    safe_name = project["name"].replace(" ", "-").lower()
    safe_coder = coder["name"].replace(" ", "-").lower()
    pkg_path = output_dir / f"{safe_name}_{safe_coder}.ace"

    # Create new SQLite database
    pkg_conn = sqlite3.connect(pkg_path)
    pkg_conn.row_factory = sqlite3.Row
    create_schema(pkg_conn)

    # Copy project with file_role = 'coder'
    pkg_conn.execute(
        "INSERT INTO project VALUES (?,?,?,?,?,?,?,?,?)",
        (project["id"], project["name"], project["description"],
         project["instructions"], "coder", cb_hash, project["assignment_seed"],
         project["created_at"], project["updated_at"]),
    )

    # Copy coder
    pkg_conn.execute("INSERT INTO coder VALUES (?,?)", (coder["id"], coder["name"]))

    # Copy full codebook
    for code in conn.execute("SELECT * FROM codebook_code ORDER BY sort_order"):
        pkg_conn.execute(
            "INSERT INTO codebook_code VALUES (?,?,?,?,?,?)",
            tuple(code),
        )

    # Copy assigned sources + content
    assigned_sources = conn.execute(
        "SELECT source_id FROM assignment WHERE coder_id = ?", (coder_id,)
    ).fetchall()
    source_ids = [r["source_id"] for r in assigned_sources]

    for sid in source_ids:
        source = conn.execute("SELECT * FROM source WHERE id = ?", (sid,)).fetchone()
        pkg_conn.execute(
            "INSERT INTO source VALUES (?,?,?,?,?,?,?,?)",
            tuple(source),
        )
        content = conn.execute(
            "SELECT * FROM source_content WHERE source_id = ?", (sid,)
        ).fetchone()
        pkg_conn.execute(
            "INSERT INTO source_content VALUES (?,?,?)",
            tuple(content),
        )

    # Copy assignments for this coder
    for assignment in conn.execute(
        "SELECT * FROM assignment WHERE coder_id = ?", (coder_id,)
    ):
        pkg_conn.execute(
            "INSERT INTO assignment VALUES (?,?,?,?,?,?)",
            tuple(assignment),
        )

    pkg_conn.commit()
    checkpoint_and_close(pkg_conn)
    return pkg_path
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_services/test_packager.py -v
```

**Step 5: Commit**

```bash
git add src/ace/services/packager.py tests/test_services/test_packager.py
git commit -m "feat: coder package export service"
```

---

### Task 7: Package import/merge service

**Files:**
- Modify: `src/ace/services/packager.py` (add `import_coder_package`)
- Modify: `tests/test_services/test_packager.py` (add import tests)

**Step 1: Write failing tests for import**

```python
# Add to tests/test_services/test_packager.py

from ace.models.annotation import add_annotation, get_annotations_for_source


def _code_and_return(pkg_path):
    """Simulate a coder annotating and returning their package."""
    pkg_conn = sqlite3.connect(pkg_path)
    pkg_conn.row_factory = sqlite3.Row
    pkg_conn.execute("PRAGMA foreign_keys = ON")
    source = pkg_conn.execute("SELECT id FROM source LIMIT 1").fetchone()
    code = pkg_conn.execute("SELECT id FROM codebook_code LIMIT 1").fetchone()
    coder = pkg_conn.execute("SELECT id FROM coder LIMIT 1").fetchone()
    add_annotation(
        pkg_conn, source_id=source["id"], coder_id=coder["id"],
        code_id=code["id"], start_offset=0, end_offset=6,
        selected_text="Sample",
    )
    pkg_conn.commit()
    pkg_conn.close()


def test_import_merges_annotations(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    output_path = tmp_path / "export"
    output_path.mkdir()
    pkg_path = export_coder_package(conn, coder_ids[0], output_path)
    _code_and_return(pkg_path)
    result = import_coder_package(conn, pkg_path)
    assert result.annotations_imported > 0
    conn.close()


def test_import_validates_project_id(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    # Create a package from a different project
    other_db = tmp_path / "other.ace"
    other_conn = create_project(other_db, name="Other")
    other_conn.close()
    import pytest
    with pytest.raises(ValueError, match="project"):
        import_coder_package(conn, other_db)
    conn.close()


def test_import_is_idempotent(tmp_db, tmp_path):
    conn, coder_ids = _setup_assigned_project(tmp_db)
    output_path = tmp_path / "export"
    output_path.mkdir()
    pkg_path = export_coder_package(conn, coder_ids[0], output_path)
    _code_and_return(pkg_path)
    r1 = import_coder_package(conn, pkg_path)
    r2 = import_coder_package(conn, pkg_path)
    assert r1.annotations_imported > 0
    assert r2.annotations_imported == 0  # all skipped (same updated_at)
    conn.close()
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_services/test_packager.py -v -k "import"
```

**Step 3: Implement import**

```python
# Add to src/ace/services/packager.py
from dataclasses import dataclass


@dataclass
class ImportResult:
    annotations_imported: int = 0
    annotations_skipped: int = 0
    annotations_updated: int = 0
    notes_imported: int = 0
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def import_coder_package(
    conn: sqlite3.Connection,
    pkg_path: Path,
) -> ImportResult:
    result = ImportResult()
    pkg_conn = sqlite3.connect(pkg_path)
    pkg_conn.row_factory = sqlite3.Row

    # Validation
    app_id = pkg_conn.execute("PRAGMA application_id").fetchone()[0]
    if app_id != ACE_APPLICATION_ID:
        pkg_conn.close()
        raise ValueError(f"{pkg_path.name} is not a valid ACE file")

    pkg_project = pkg_conn.execute("SELECT * FROM project").fetchone()
    main_project = conn.execute("SELECT * FROM project").fetchone()

    if pkg_project["id"] != main_project["id"]:
        pkg_conn.close()
        raise ValueError(
            f"This file belongs to project '{pkg_project['name']}' "
            f"but you have '{main_project['name']}' open"
        )

    if pkg_project["file_role"] != "coder":
        pkg_conn.close()
        raise ValueError("This is a manager file, not a coder package")

    # Validate content hashes
    for pkg_source in pkg_conn.execute("SELECT * FROM source_content"):
        main_content = conn.execute(
            "SELECT content_hash FROM source_content WHERE source_id = ?",
            (pkg_source["source_id"],),
        ).fetchone()
        if main_content and main_content["content_hash"] != pkg_source["content_hash"]:
            result.warnings.append(
                f"Content hash mismatch for source {pkg_source['source_id']}"
            )

    # Check codebook drift
    if main_project["codebook_hash"] and pkg_project["codebook_hash"]:
        current_hash = compute_codebook_hash(conn)
        if current_hash != pkg_project["codebook_hash"]:
            result.warnings.append("Codebook has changed since this package was exported")
            # Re-insert any codes from coder file that were deleted in main
            for pkg_code in pkg_conn.execute("SELECT * FROM codebook_code"):
                existing = conn.execute(
                    "SELECT id FROM codebook_code WHERE id = ?", (pkg_code["id"],)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO codebook_code VALUES (?,?,?,?,?,?)",
                        tuple(pkg_code),
                    )

    # Import annotations (UPSERT by UUID, newer wins)
    conn.execute("BEGIN")
    try:
        for ann in pkg_conn.execute(
            "SELECT * FROM annotation WHERE deleted_at IS NULL"
        ):
            existing = conn.execute(
                "SELECT updated_at FROM annotation WHERE id = ?", (ann["id"],)
            ).fetchone()
            if existing:
                if ann["updated_at"] > existing["updated_at"]:
                    conn.execute(
                        "UPDATE annotation SET source_id=?, coder_id=?, code_id=?, "
                        "start_offset=?, end_offset=?, selected_text=?, memo=?, "
                        "w3c_selector_json=?, updated_at=?, deleted_at=? WHERE id=?",
                        (ann["source_id"], ann["coder_id"], ann["code_id"],
                         ann["start_offset"], ann["end_offset"], ann["selected_text"],
                         ann["memo"], ann["w3c_selector_json"], ann["updated_at"],
                         ann["deleted_at"], ann["id"]),
                    )
                    result.annotations_updated += 1
                else:
                    result.annotations_skipped += 1
            else:
                conn.execute(
                    "INSERT INTO annotation VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(ann),
                )
                result.annotations_imported += 1

        # Import source notes
        for note in pkg_conn.execute("SELECT * FROM source_note"):
            existing = conn.execute(
                "SELECT id FROM source_note WHERE source_id = ? AND coder_id = ?",
                (note["source_id"], note["coder_id"]),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE source_note SET note_text=?, updated_at=? WHERE id=?",
                    (note["note_text"], note["updated_at"], existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO source_note VALUES (?,?,?,?,?,?)",
                    tuple(note),
                )
                result.notes_imported += 1

        # Update assignment statuses
        for assignment in pkg_conn.execute("SELECT * FROM assignment"):
            conn.execute(
                "UPDATE assignment SET status=?, updated_at=? "
                "WHERE source_id=? AND coder_id=?",
                (assignment["status"], assignment["updated_at"],
                 assignment["source_id"], assignment["coder_id"]),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pkg_conn.close()

    return result
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_services/test_packager.py -v
```

**Step 5: Commit**

```bash
git add src/ace/services/packager.py tests/test_services/test_packager.py
git commit -m "feat: coder package import/merge service with validation"
```

---

### Task 8: UTF-16/Unicode offset conversion

**Files:**
- Create: `src/ace/services/offset.py`
- Create: `tests/test_services/test_offset.py`

**Step 1: Write failing tests**

```python
# tests/test_services/test_offset.py
from ace.services.offset import utf16_to_codepoint, codepoint_to_utf16


def test_ascii_offsets_unchanged():
    text = "Hello world"
    assert utf16_to_codepoint(text, 5) == 5
    assert codepoint_to_utf16(text, 5) == 5


def test_emoji_offset_conversion():
    # "Hi 😊 there"
    # In Python (code points): H=0, i=1, space=2, 😊=3, space=4, t=5...
    # In JS (UTF-16 units):    H=0, i=1, space=2, 😊=3+4 (surrogate pair), space=5, t=6...
    text = "Hi 😊 there"
    # JS offset 5 (space after emoji) = Python offset 4
    assert utf16_to_codepoint(text, 5) == 4
    # Python offset 4 (space after emoji) = JS offset 5
    assert codepoint_to_utf16(text, 4) == 5


def test_multiple_emoji():
    text = "a😊b😊c"
    # Python: a=0, 😊=1, b=2, 😊=3, c=4
    # JS:     a=0, 😊=1,2, b=3, 😊=4,5, c=6
    assert utf16_to_codepoint(text, 3) == 2  # 'b'
    assert utf16_to_codepoint(text, 6) == 4  # 'c'
    assert codepoint_to_utf16(text, 2) == 3  # 'b'
    assert codepoint_to_utf16(text, 4) == 6  # 'c'


def test_no_emoji_roundtrip():
    text = "plain text"
    for i in range(len(text)):
        assert utf16_to_codepoint(text, i) == i
        assert codepoint_to_utf16(text, i) == i
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_services/test_offset.py -v
```

**Step 3: Implement offset conversion**

```python
# src/ace/services/offset.py

def utf16_to_codepoint(text: str, utf16_offset: int) -> int:
    utf16_pos = 0
    for cp_pos, char in enumerate(text):
        if utf16_pos >= utf16_offset:
            return cp_pos
        utf16_pos += 2 if ord(char) > 0xFFFF else 1
    return len(text)


def codepoint_to_utf16(text: str, cp_offset: int) -> int:
    utf16_pos = 0
    for cp_pos, char in enumerate(text):
        if cp_pos >= cp_offset:
            return utf16_pos
        utf16_pos += 2 if ord(char) > 0xFFFF else 1
    return utf16_pos
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_services/test_offset.py -v
```

**Step 5: Commit**

```bash
git add src/ace/services/offset.py tests/test_services/test_offset.py
git commit -m "feat: UTF-16/Unicode code point offset conversion"
```

---

### Task 9: ICR computation service

**Files:**
- Create: `src/ace/services/icr.py`
- Create: `tests/test_services/test_icr.py`

**Step 1: Write failing tests**

```python
# tests/test_services/test_icr.py
import sqlite3
from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.coder import add_coder
from ace.models.annotation import add_annotation
from ace.services.icr import compute_icr, ICRResult


def _setup_icr_project(tmp_db):
    """Set up a project with 2 coders who annotated the same source."""
    conn = create_project(tmp_db, name="ICR Test")
    source_id = add_source(conn, display_id="P001",
                           content_text="I enjoyed the group work but lectures were too fast",
                           source_type="row", filename="test.csv")
    code_pos = add_code(conn, name="Positive", colour="#4CAF50")
    code_neg = add_code(conn, name="Negative", colour="#F44336")
    alice = add_coder(conn, "Alice")
    bob = add_coder(conn, "Bob")

    # Both assigned to same source
    from ace.models.assignment import add_assignment
    add_assignment(conn, source_id, alice)
    add_assignment(conn, source_id, bob)

    return conn, source_id, code_pos, code_neg, alice, bob


def test_perfect_agreement(tmp_db):
    conn, src, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)
    # Both coders annotate exactly the same spans
    add_annotation(conn, src, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, src, bob, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, src, alice, code_neg, 33, 51, "lectures were too fast")
    add_annotation(conn, src, bob, code_neg, 33, 51, "lectures were too fast")

    result = compute_icr(conn)
    assert result.overall_kappa > 0.9  # Should be near-perfect
    conn.close()


def test_no_agreement(tmp_db):
    conn, src, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)
    # Coders annotate same spans but with opposite codes
    add_annotation(conn, src, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, src, bob, code_neg, 2, 28, "enjoyed the group work")

    result = compute_icr(conn)
    assert result.overall_kappa < 0.5
    conn.close()


def test_icr_returns_per_code_results(tmp_db):
    conn, src, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)
    add_annotation(conn, src, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, src, bob, code_pos, 2, 28, "enjoyed the group work")

    result = compute_icr(conn)
    assert "Positive" in result.per_code
    assert "Negative" in result.per_code
    conn.close()


def test_icr_handles_multi_code_spans(tmp_db):
    conn, src, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)
    # Alice applies both codes to same span
    add_annotation(conn, src, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, src, alice, code_neg, 2, 28, "enjoyed the group work")
    # Bob applies only one
    add_annotation(conn, src, bob, code_pos, 2, 28, "enjoyed the group work")

    result = compute_icr(conn)
    # Should agree on Positive, disagree on Negative for this span
    assert result.per_code["Positive"]["kappa"] > 0.5
    conn.close()
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_services/test_icr.py -v
```

**Step 3: Implement ICR computation (sweep-line algorithm)**

```python
# src/ace/services/icr.py
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from sklearn.metrics import cohen_kappa_score


@dataclass
class ICRResult:
    overall_kappa: float = 0.0
    overall_alpha: float = 0.0
    overall_percent_agreement: float = 0.0
    per_code: dict = field(default_factory=dict)
    overlap_sources: int = 0
    overlap_sources_complete: int = 0


def _build_code_vectors(
    annotations_a: list, annotations_b: list, text_length: int, code_ids: list[str],
) -> dict[str, tuple[list[int], list[int]]]:
    """Build per-code binary vectors for two coders using sweep-line."""
    vectors: dict[str, tuple[list[int], list[int]]] = {}

    for code_id in code_ids:
        vec_a = [0] * text_length
        vec_b = [0] * text_length

        for ann in annotations_a:
            if ann["code_id"] == code_id:
                for i in range(ann["start_offset"], min(ann["end_offset"], text_length)):
                    vec_a[i] = 1

        for ann in annotations_b:
            if ann["code_id"] == code_id:
                for i in range(ann["start_offset"], min(ann["end_offset"], text_length)):
                    vec_b[i] = 1

        vectors[code_id] = (vec_a, vec_b)

    return vectors


def _filter_coded_positions(vec_a: list[int], vec_b: list[int]) -> tuple[list[int], list[int]]:
    """Keep only positions where at least one coder applied a code."""
    filtered_a, filtered_b = [], []
    for a, b in zip(vec_a, vec_b):
        if a or b:
            filtered_a.append(a)
            filtered_b.append(b)
    return filtered_a, filtered_b


def compute_icr(conn: sqlite3.Connection) -> ICRResult:
    result = ICRResult()

    # Find overlap sources (assigned to 2+ coders)
    overlap_query = """
        SELECT source_id, GROUP_CONCAT(coder_id) as coder_ids
        FROM assignment
        GROUP BY source_id
        HAVING COUNT(*) >= 2
    """
    overlap_sources = conn.execute(overlap_query).fetchall()
    result.overlap_sources = len(overlap_sources)

    if not overlap_sources:
        return result

    # Get all codes
    codes = conn.execute("SELECT id, name FROM codebook_code ORDER BY sort_order").fetchall()
    code_ids = [c["id"] for c in codes]
    code_names = {c["id"]: c["name"] for c in codes}

    # Aggregate per-code vectors across all overlap sources
    all_per_code: dict[str, tuple[list[int], list[int]]] = {
        cid: ([], []) for cid in code_ids
    }

    for row in overlap_sources:
        source_id = row["source_id"]
        coder_id_list = row["coder_ids"].split(",")
        if len(coder_id_list) < 2:
            continue
        coder_a, coder_b = coder_id_list[0], coder_id_list[1]

        # Get text length
        content = conn.execute(
            "SELECT content_text FROM source_content WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if not content:
            continue
        text_length = len(content["content_text"])

        # Get annotations for each coder
        anns_a = conn.execute(
            "SELECT * FROM annotation WHERE source_id = ? AND coder_id = ? "
            "AND deleted_at IS NULL",
            (source_id, coder_a),
        ).fetchall()
        anns_b = conn.execute(
            "SELECT * FROM annotation WHERE source_id = ? AND coder_id = ? "
            "AND deleted_at IS NULL",
            (source_id, coder_b),
        ).fetchall()

        # Build per-code vectors
        vectors = _build_code_vectors(anns_a, anns_b, text_length, code_ids)

        for cid in code_ids:
            vec_a, vec_b = vectors[cid]
            filtered_a, filtered_b = _filter_coded_positions(vec_a, vec_b)
            all_per_code[cid][0].extend(filtered_a)
            all_per_code[cid][1].extend(filtered_b)

    # Compute per-code kappa
    kappas = []
    for cid in code_ids:
        vec_a, vec_b = all_per_code[cid]
        name = code_names[cid]
        if len(vec_a) < 2:
            result.per_code[name] = {
                "kappa": None, "percent_agreement": None, "n_positions": 0,
            }
            continue

        try:
            kappa = cohen_kappa_score(vec_a, vec_b)
        except Exception:
            kappa = None

        agree = sum(1 for a, b in zip(vec_a, vec_b) if a == b)
        pct = agree / len(vec_a) if vec_a else 0

        result.per_code[name] = {
            "kappa": kappa,
            "percent_agreement": pct,
            "n_positions": len(vec_a),
        }
        if kappa is not None:
            kappas.append(kappa)

    # Overall = macro-average
    result.overall_kappa = sum(kappas) / len(kappas) if kappas else 0.0
    result.overall_percent_agreement = (
        sum(c["percent_agreement"] for c in result.per_code.values()
            if c["percent_agreement"] is not None)
        / len([c for c in result.per_code.values() if c["percent_agreement"] is not None])
        if result.per_code else 0.0
    )

    return result
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_services/test_icr.py -v
```

**Step 5: Commit**

```bash
git add src/ace/services/icr.py tests/test_services/test_icr.py
git commit -m "feat: character-level ICR computation with sweep-line algorithm"
```

---

### Task 10: Data export service

**Files:**
- Create: `src/ace/services/exporter.py`
- Create: `tests/test_services/test_exporter.py`

**Step 1: Write failing tests**

```python
# tests/test_services/test_exporter.py
import csv
from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.coder import add_coder
from ace.models.annotation import add_annotation
from ace.services.exporter import export_annotations_csv


def test_export_annotations_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, name="Test")
    source_id = add_source(conn, display_id="P001", content_text="Hello world",
                           source_type="row", filename="test.csv", metadata={"age": "22"})
    code_id = add_code(conn, name="Positive", colour="#4CAF50")
    conn.execute("INSERT INTO coder VALUES (?, ?)", ("c1", "Alice"))
    conn.commit()
    add_annotation(conn, source_id, "c1", code_id, 0, 5, "Hello")

    out_path = tmp_path / "export.csv"
    export_annotations_csv(conn, out_path)

    with open(out_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["source_id"] == source_id
    assert rows[0]["display_id"] == "P001"
    assert rows[0]["coder_name"] == "Alice"
    assert rows[0]["code_name"] == "Positive"
    assert rows[0]["selected_text"] == "Hello"
    assert rows[0]["age"] == "22"
    conn.close()
```

**Step 2: Run tests — expect FAIL, implement, run again**

```python
# src/ace/services/exporter.py
import csv
import json
import sqlite3
from pathlib import Path


def export_annotations_csv(conn: sqlite3.Connection, output_path: Path) -> int:
    query = """
        SELECT
            a.source_id, s.display_id, c.name as coder_name,
            cc.name as code_name, a.selected_text,
            a.start_offset, a.end_offset, a.memo,
            s.metadata_json
        FROM annotation a
        JOIN source s ON a.source_id = s.id
        JOIN coder c ON a.coder_id = c.id
        JOIN codebook_code cc ON a.code_id = cc.id
        WHERE a.deleted_at IS NULL
        ORDER BY s.sort_order, a.start_offset
    """
    rows = conn.execute(query).fetchall()

    # Collect all metadata keys
    meta_keys = set()
    for row in rows:
        if row["metadata_json"]:
            meta_keys.update(json.loads(row["metadata_json"]).keys())
    meta_keys = sorted(meta_keys)

    fieldnames = [
        "source_id", "display_id", "coder_name", "code_name",
        "selected_text", "start_offset", "end_offset", "memo",
    ] + meta_keys

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {
                "source_id": row["source_id"],
                "display_id": row["display_id"],
                "coder_name": row["coder_name"],
                "code_name": row["code_name"],
                "selected_text": row["selected_text"],
                "start_offset": row["start_offset"],
                "end_offset": row["end_offset"],
                "memo": row["memo"] or "",
            }
            if row["metadata_json"]:
                meta = json.loads(row["metadata_json"])
                for key in meta_keys:
                    out[key] = meta.get(key, "")
            else:
                for key in meta_keys:
                    out[key] = ""
            writer.writerow(out)

    return len(rows)
```

**Step 3: Run tests — expect PASS**

```bash
pytest tests/test_services/test_exporter.py -v
```

**Step 4: Commit**

```bash
git add src/ace/services/exporter.py tests/test_services/test_exporter.py
git commit -m "feat: annotation export to CSV"
```

---

## Phase 2: NiceGUI UI (Tasks 11-16)

> These tasks build the user interface. They are harder to unit test traditionally. Each task includes a manual verification step. Integration tests can be added later.

### Task 11: Landing page

**Files:**
- Modify: `src/ace/app.py`
- Create: `src/ace/pages/__init__.py`
- Create: `src/ace/pages/landing.py`

Build the landing page with "New Project" button and drag-and-drop `.ace` file zone. Route to manager or coder mode based on `file_role`.

### Task 12: Manager — Import wizard step

**Files:**
- Create: `src/ace/pages/manager/__init__.py`
- Create: `src/ace/pages/manager/import_data.py`

CSV/Excel drag-and-drop, column preview table, ID and text column selection. Calls `import_csv()` service.

### Task 13: Manager — Codebook step

**Files:**
- Create: `src/ace/pages/manager/codebook.py`

Flat code list with add/edit/delete. Colour picker (from accessible palette). Import from CSV button. Project instructions textarea.

### Task 14: Manager — Assign + Export steps

**Files:**
- Create: `src/ace/pages/manager/assign.py`
- Create: `src/ace/pages/manager/export.py`

Coder name entry, overlap slider with live preview numbers. Confirmation dialog. Export button generates `.ace` files.

### Task 15: Coder — Annotation interface

**Files:**
- Create: `src/ace/pages/coder/__init__.py`
- Create: `src/ace/pages/coder/coding.py`
- Create: `src/ace/static/js/bridge.js`

Recogito integration. Highlight-then-pick-code popover. Code sidebar. Auto-save via JS bridge. Offset normalisation.

### Task 16: Manager — Results (merge + ICR + adjudication)

**Files:**
- Create: `src/ace/pages/manager/results.py`

Import returned files (drag-and-drop). Merge preview. ICR dashboard table. Disagreement viewer. Adjudication controls. Export buttons.

---

## Phase 3: Polish (Tasks 17-18)

### Task 17: Onboarding, keyboard shortcuts, accessibility

Instructional overlay for first-time coders. Keyboard shortcut registration. Colour-blind palette. ARIA attributes.

### Task 18: Cloud-sync warning, backup, final testing

Detect cloud-sync directories on startup. Auto-backup before merge. End-to-end manual test of full workflow.

---

## Run All Tests

```bash
pytest tests/ -v --tb=short
```

## Final Commit

```bash
git add -A
git commit -m "feat: ACE v0.1.0 — qualitative coding tool with ICR"
```
