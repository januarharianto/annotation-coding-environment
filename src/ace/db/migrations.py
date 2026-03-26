"""Migration runner for ACE project files."""

import sqlite3
from typing import Callable

from ace.db.schema import SCHEMA_VERSION

def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add group_name column to codebook_code."""
    conn.execute("ALTER TABLE codebook_code ADD COLUMN group_name TEXT")


# Registry of migration functions keyed by target version.
# Each function takes a connection and migrates from version (key - 1) to key.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_v1_to_v2,
}


def check_and_migrate(conn: sqlite3.Connection) -> int:
    """Check user_version and apply sequential migrations if needed.

    Returns the current schema version after any migrations.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    while current < SCHEMA_VERSION:
        next_version = current + 1
        migrate_fn = MIGRATIONS.get(next_version)
        if migrate_fn is None:
            raise RuntimeError(
                f"No migration found for version {current} -> {next_version}"
            )
        migrate_fn(conn)
        conn.execute(f"PRAGMA user_version = {next_version}")
        conn.commit()
        current = next_version

    return current
