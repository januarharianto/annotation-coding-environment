import sqlite3
import pytest
from ace.db.schema import create_schema, ACE_APPLICATION_ID, SCHEMA_VERSION


@pytest.fixture
def schema_conn(tmp_db):
    """Create an in-memory connection with the full schema applied."""
    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    return conn


def test_create_schema_creates_all_tables(schema_conn):
    cursor = schema_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row["name"] for row in cursor.fetchall()}
    expected = {
        "project",
        "source",
        "source_content",
        "codebook_code",
        "coder",
        "assignment",
        "annotation",
        "source_note",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


def test_create_schema_sets_application_id(schema_conn):
    row = schema_conn.execute("PRAGMA application_id").fetchone()
    assert row[0] == ACE_APPLICATION_ID


def test_create_schema_sets_user_version(schema_conn):
    row = schema_conn.execute("PRAGMA user_version").fetchone()
    assert row[0] == SCHEMA_VERSION


def test_create_schema_enables_foreign_keys(schema_conn):
    row = schema_conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1


def test_annotation_check_constraints(schema_conn):
    # Insert prerequisite rows
    schema_conn.execute(
        "INSERT INTO source (id, display_id, source_type, sort_order, created_at) "
        "VALUES ('s1', 'S-001', 'file', 1, '2024-01-01T00:00:00Z')"
    )
    schema_conn.execute(
        "INSERT INTO coder (id, name) VALUES ('c1', 'Alice')"
    )
    schema_conn.execute(
        "INSERT INTO codebook_code (id, name, sort_order, created_at) "
        "VALUES ('code1', 'Theme A', 1, '2024-01-01T00:00:00Z')"
    )

    # Negative start_offset should fail
    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute(
            "INSERT INTO annotation (id, source_id, coder_id, code_id, "
            "start_offset, end_offset, selected_text, created_at, updated_at) "
            "VALUES ('a1', 's1', 'c1', 'code1', -1, 5, 'text', "
            "'2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')"
        )

    # end_offset <= start_offset should fail
    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute(
            "INSERT INTO annotation (id, source_id, coder_id, code_id, "
            "start_offset, end_offset, selected_text, created_at, updated_at) "
            "VALUES ('a2', 's1', 'c1', 'code1', 5, 5, 'text', "
            "'2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')"
        )


def test_assignment_status_check_constraint(schema_conn):
    schema_conn.execute(
        "INSERT INTO source (id, display_id, source_type, sort_order, created_at) "
        "VALUES ('s1', 'S-001', 'file', 1, '2024-01-01T00:00:00Z')"
    )
    schema_conn.execute(
        "INSERT INTO coder (id, name) VALUES ('c1', 'Alice')"
    )

    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute(
            "INSERT INTO assignment (id, source_id, coder_id, status, assigned_at, updated_at) "
            "VALUES ('asgn1', 's1', 'c1', 'invalid_status', "
            "'2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')"
        )


def test_codebook_code_name_unique(schema_conn):
    schema_conn.execute(
        "INSERT INTO codebook_code (id, name, sort_order, created_at) "
        "VALUES ('code1', 'Theme A', 1, '2024-01-01T00:00:00Z')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute(
            "INSERT INTO codebook_code (id, name, sort_order, created_at) "
            "VALUES ('code2', 'Theme A', 2, '2024-01-01T00:00:00Z')"
        )


def test_coder_name_unique(schema_conn):
    schema_conn.execute(
        "INSERT INTO coder (id, name) VALUES ('c1', 'Alice')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        schema_conn.execute(
            "INSERT INTO coder (id, name) VALUES ('c2', 'Alice')"
        )
