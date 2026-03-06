import sqlite3
import pytest
from ace.db.connection import create_project, open_project, checkpoint_and_close
from ace.db.schema import ACE_APPLICATION_ID


def test_create_project_creates_file(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    conn.close()
    assert tmp_db.exists()


def test_create_project_inserts_manager_role(tmp_db):
    conn = create_project(tmp_db, "Test Project", description="A test")
    row = conn.execute("SELECT name, file_role FROM project").fetchone()
    assert row["name"] == "Test Project"
    assert row["file_role"] == "manager"
    conn.close()


def test_open_project_validates_application_id(tmp_path):
    # Create a plain SQLite file (no ACE schema)
    plain_db = tmp_path / "plain.ace"
    plain_conn = sqlite3.connect(str(plain_db))
    plain_conn.execute("CREATE TABLE dummy (id INTEGER)")
    plain_conn.commit()
    plain_conn.close()

    with pytest.raises(ValueError):
        open_project(plain_db)


def test_open_project_enables_foreign_keys(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    conn.close()

    conn = open_project(tmp_db)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1
    conn.close()


def test_open_project_uses_wal_mode(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    conn.close()

    conn = open_project(tmp_db)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"
    conn.close()


def test_checkpoint_and_close_switches_to_delete_mode(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    checkpoint_and_close(conn)

    # Re-open to check journal mode was switched back
    verify_conn = sqlite3.connect(str(tmp_db))
    row = verify_conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "delete"
    verify_conn.close()
