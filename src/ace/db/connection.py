"""Connection manager for ACE project files."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ace.db.schema import ACE_APPLICATION_ID, create_schema


def create_project(
    path: str | Path, name: str, description: str | None = None
) -> sqlite3.Connection:
    """Create a new .ace project file with schema and initial project row.

    Returns an open connection in WAL mode with foreign keys enabled.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Project file already exists: {path}")

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    create_schema(conn)

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO project (id, name, description, file_role, created_at, updated_at) "
        "VALUES (?, ?, ?, 'manager', ?, ?)",
        (uuid.uuid4().hex, name, description, now, now),
    )
    conn.commit()
    return conn


def open_project(path: str | Path) -> sqlite3.Connection:
    """Open an existing .ace project file.

    Validates the application_id, enables foreign keys, and uses WAL mode.
    Raises ValueError if the file is not a valid ACE project.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project file not found: {path}")

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    if app_id != ACE_APPLICATION_ID:
        conn.close()
        raise ValueError(
            f"Not a valid ACE project file (application_id={app_id:#x}, "
            f"expected {ACE_APPLICATION_ID:#x})"
        )

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def checkpoint_and_close(conn: sqlite3.Connection) -> None:
    """WAL checkpoint, switch to DELETE journal mode, then close."""
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
