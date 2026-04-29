"""Tests for chord assignment in the codebook model layer."""

import sqlite3
from pathlib import Path

import pytest

from ace.db.connection import open_project, create_project
from ace.models.codebook import (
    add_code,
    backfill_chords,
    list_codes,
    set_chord,
    SINGLE_KEY_LIMIT,
)


def _fresh_project(tmp_path):
    path = tmp_path / "fresh.ace"
    create_project(str(path), "Test")
    return str(path)


def test_first_thirty_one_codes_have_null_chord(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(SINGLE_KEY_LIMIT):
            add_code(conn, f"Code {i:02d}", "#A91818")
        codes = list_codes(conn)
        assert all(c["chord"] is None for c in codes)
    finally:
        conn.close()


def test_thirty_second_code_gets_chord(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(SINGLE_KEY_LIMIT):
            add_code(conn, f"Filler {i:02d}", "#A91818")
        # 32nd code with a known mnemonic
        cid = add_code(conn, "Privacy of data", "#557FE6")
        codes = list_codes(conn)
        # First 31 chord-less
        assert all(c["chord"] is None for c in codes[:SINGLE_KEY_LIMIT])
        # 32nd has a chord, length 2
        thirty_second = next(c for c in codes if c["id"] == cid)
        assert thirty_second["chord"] == "pd"
    finally:
        conn.close()


def test_backfill_assigns_chord_to_unchorded_tail(tmp_path):
    """Simulates a post-migration state: codes past slot 31 with NULL chord."""
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        # Add 35 codes manually with NULL chord (bypass add_code's auto-assignment)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for i in range(35):
            cid = f"code-{i:02d}"
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (cid, f"Code {i:02d}", "#A91818", i + 1, now),
            )
        conn.commit()

        backfill_chords(conn)
        conn.commit()

        codes = list_codes(conn)
        # First 31 still chord-less
        assert all(c["chord"] is None for c in codes[:SINGLE_KEY_LIMIT])
        # Codes 32-35 have chords
        assert all(c["chord"] is not None for c in codes[SINGLE_KEY_LIMIT:])
        # All chords unique
        chords = [c["chord"] for c in codes[SINGLE_KEY_LIMIT:]]
        assert len(chords) == len(set(chords))
    finally:
        conn.close()


def test_backfill_is_idempotent(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(35):
            add_code(conn, f"Code {i:02d}", "#A91818")

        before = [(c["id"], c["chord"]) for c in list_codes(conn)]
        backfill_chords(conn)
        conn.commit()
        after = [(c["id"], c["chord"]) for c in list_codes(conn)]

        assert before == after
    finally:
        conn.close()


def test_set_chord_updates_column(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        cid = add_code(conn, "Privacy of data", "#A91818")
        set_chord(conn, cid, "xy")

        row = conn.execute(
            "SELECT chord FROM codebook_code WHERE id = ?", (cid,)
        ).fetchone()
        assert row["chord"] == "xy"
    finally:
        conn.close()


def test_set_chord_rejects_duplicate(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        cid1 = add_code(conn, "Code A", "#A91818")
        cid2 = add_code(conn, "Code B", "#557FE6")

        set_chord(conn, cid1, "pd")  # commits internally now

        with pytest.raises(sqlite3.IntegrityError):
            set_chord(conn, cid2, "pd")  # raises on commit inside set_chord
    finally:
        conn.close()


def test_set_chord_to_none_clears(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        cid = add_code(conn, "Privacy of data", "#A91818")
        set_chord(conn, cid, "xy")

        set_chord(conn, cid, None)

        row = conn.execute(
            "SELECT chord FROM codebook_code WHERE id = ?", (cid,)
        ).fetchone()
        assert row["chord"] is None
    finally:
        conn.close()


def test_backfill_preserves_existing_chords_in_mixed_state(tmp_path):
    """Backfill must not stomp pre-existing chords; only fill the NULL ones."""
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # 31 fillers + 3 chord-tail codes
        for i in range(SINGLE_KEY_LIMIT):
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (f"f-{i:02d}", f"Filler {i:02d}", "#A91818", i + 1, now),
            )
        # Code 32: already chorded (e.g. user manually set "xy")
        conn.execute(
            "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
            "VALUES (?, ?, ?, ?, NULL, ?, ?)",
            ("c-32", "Privacy of data", "#A91818", 32, "xy", now),
        )
        # Code 33, 34: NULL chord, awaiting backfill
        for i, name in [(33, "AI replacing humans"), (34, "Repetitive feedback")]:
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (f"c-{i:02d}", name, "#A91818", i, now),
            )
        conn.commit()

        backfill_chords(conn)
        conn.commit()

        # Code 32 still has its manual chord
        row32 = conn.execute("SELECT chord FROM codebook_code WHERE id = 'c-32'").fetchone()
        assert row32["chord"] == "xy"

        # Codes 33 and 34 now have chords, distinct from "xy" and each other
        row33 = conn.execute("SELECT chord FROM codebook_code WHERE id = 'c-33'").fetchone()
        row34 = conn.execute("SELECT chord FROM codebook_code WHERE id = 'c-34'").fetchone()
        assert row33["chord"] is not None
        assert row34["chord"] is not None
        assert row33["chord"] != "xy"
        assert row34["chord"] != "xy"
        assert row33["chord"] != row34["chord"]
    finally:
        conn.close()


def test_backfill_handles_zero_indexed_sort_order(tmp_path):
    """Codes with 0-indexed sort_orders (e.g. legacy projects) backfill correctly."""
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Insert 33 codes with 0-indexed sort_orders (0..32). Mimics legacy SWA project.
        for i in range(33):
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (f"z-{i:02d}", f"Code {i:02d}", "#A91818", i, now),
            )
        conn.commit()

        backfill_chords(conn)
        conn.commit()

        # Position 0..30 (codes z-00..z-30) have NULL chord
        for i in range(SINGLE_KEY_LIMIT):
            row = conn.execute(
                "SELECT chord FROM codebook_code WHERE id = ?", (f"z-{i:02d}",)
            ).fetchone()
            assert row["chord"] is None, f"position {i} (sort {i}) should be NULL"

        # Position 31, 32 (codes z-31, z-32) have a chord
        for i in [31, 32]:
            row = conn.execute(
                "SELECT chord FROM codebook_code WHERE id = ?", (f"z-{i:02d}",)
            ).fetchone()
            assert row["chord"] is not None, f"position {i} (sort {i}) should have chord"
    finally:
        conn.close()
