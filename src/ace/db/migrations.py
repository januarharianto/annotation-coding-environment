"""Migration runner for ACE project files."""

import sqlite3
from typing import Callable

from ace.db.schema import SCHEMA_VERSION

# Registry of migration functions keyed by target version.
# Each function takes a connection and migrates from version (key - 1) to key.
# Empty for schema version 1 -- no migrations needed yet.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {}


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
