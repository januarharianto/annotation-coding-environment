import sqlite3
import pytest
from ace.db.connection import create_project
from ace.db.migrations import check_and_migrate, MIGRATIONS
from ace.db.schema import SCHEMA_VERSION


def test_migration_runner_noop_on_current_version(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    # Should not raise and should not change version
    version = check_and_migrate(conn)
    assert version == SCHEMA_VERSION
    conn.close()


def test_migration_runner_returns_current_version(tmp_db):
    conn = create_project(tmp_db, "Test Project")
    version = check_and_migrate(conn)
    assert version == SCHEMA_VERSION
    assert isinstance(version, int)
    conn.close()
