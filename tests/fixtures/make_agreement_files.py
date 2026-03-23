"""Generate sample .ace files for manually testing the agreement dashboard.

Usage:
    uv run python tests/fixtures/make_agreement_files.py

Creates 3 .ace files in tmp/ at the project root:
  - alice.ace  — Coder "Alice"  (11 annotations)
  - bob.ace    — Coder "Bob"    (10 annotations)
  - carol.ace  — Coder "Carol"  (12 annotations)

All three share the same 5 source texts and 3 codes (Positive, Negative,
Suggestion). Annotations vary between coders to produce a realistic mix
of agreement and disagreement — some spans match exactly, some overlap
partially, some are unique to one coder.
"""

import sys
from pathlib import Path

# Add src to path so we can import ace modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from ace.db.connection import checkpoint_and_close, create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.source import add_source

# ── Source texts (shared across all coder files) ──────────────────────

SOURCES = [
    (
        "S001",
        "I really enjoyed the group work sessions. They helped me "
        "understand the material better and I made some great friends "
        "along the way.",
    ),
    (
        "S002",
        "The lectures were too fast-paced and hard to follow. I often "
        "felt lost and had to rely on the textbook to catch up afterwards.",
    ),
    (
        "S003",
        "The assessment was fair overall but the final exam was much "
        "harder than expected. I wish there had been more practice "
        "questions available.",
    ),
    (
        "S004",
        "The tutor was incredibly helpful and always made time for my "
        "questions. I felt supported throughout the semester.",
    ),
    (
        "S005",
        "I found the online discussion forums pointless. Nobody posted "
        "anything useful and the participation requirement felt like "
        "busywork.",
    ),
]

# ── Codes (shared codebook) ──────────────────────────────────────────

CODES = [
    ("Positive", "#4CAF50"),
    ("Negative", "#F44336"),
    ("Suggestion", "#2196F3"),
]

# ── Annotations per coder ────────────────────────────────────────────
# Each entry: (source_index, code_name, start_offset, end_offset)

ALICE_ANNOTATIONS = [
    # S001: "enjoyed the group work sessions" — Positive
    (0, "Positive", 9, 42),
    # S001: "helped me understand the material better" — Positive
    (0, "Positive", 49, 89),
    # S002: "too fast-paced and hard to follow" — Negative
    (1, "Negative", 18, 51),
    # S002: "felt lost" — Negative
    (1, "Negative", 60, 69),
    # S003: "fair overall" — Positive
    (2, "Positive", 20, 32),
    # S003: "much harder than expected" — Negative
    (2, "Negative", 56, 80),
    # S003: "more practice questions" — Suggestion
    (2, "Suggestion", 104, 127),
    # S004: "incredibly helpful" — Positive
    (3, "Positive", 14, 32),
    # S004: "felt supported throughout" — Positive
    (3, "Positive", 73, 97),
    # S005: "pointless" — Negative
    (4, "Negative", 43, 52),
    # S005: "felt like busywork" — Negative
    (4, "Negative", 109, 127),
]

BOB_ANNOTATIONS = [
    # S001: "enjoyed the group work sessions" — Positive (agrees with Alice)
    (0, "Positive", 9, 42),
    # S001: "made some great friends" — Positive (different span)
    (0, "Positive", 100, 123),
    # S002: "too fast-paced" — Negative (narrower than Alice)
    (1, "Negative", 18, 32),
    # S002: "rely on the textbook to catch up" — Suggestion (Alice didn't mark)
    (1, "Suggestion", 80, 112),
    # S003: "fair overall" — Positive (agrees with Alice)
    (2, "Positive", 20, 32),
    # S003: "final exam was much harder than expected" — Negative (wider)
    (2, "Negative", 41, 80),
    # S003: "more practice questions available" — Suggestion (wider)
    (2, "Suggestion", 104, 136),
    # S004: "incredibly helpful and always made time" — Positive (wider)
    (3, "Positive", 14, 51),
    # S005: "pointless" — Negative (agrees with Alice)
    (4, "Negative", 43, 52),
    # S005: "participation requirement felt like busywork" — Negative (wider)
    (4, "Negative", 83, 127),
]

CAROL_ANNOTATIONS = [
    # S001: "enjoyed the group work" — Positive (narrower)
    (0, "Positive", 9, 31),
    # S001: "understand the material better" — Positive (overlaps Alice)
    (0, "Positive", 59, 89),
    # S002: "too fast-paced and hard to follow" — Negative (agrees with Alice)
    (1, "Negative", 18, 51),
    # S002: "felt lost" — Negative (agrees with Alice)
    (1, "Negative", 60, 69),
    # S002: "rely on the textbook" — Suggestion
    (1, "Suggestion", 80, 100),
    # S003: "fair overall" — Positive (all three agree)
    (2, "Positive", 20, 32),
    # S003: "harder than expected" — Negative (narrower)
    (2, "Negative", 61, 80),
    # S004: "incredibly helpful" — Positive (agrees with Alice)
    (3, "Positive", 14, 32),
    # S004: "always made time for my questions" — Positive
    (3, "Positive", 37, 70),
    # S004: "felt supported" — Positive (agrees with Alice)
    (3, "Positive", 73, 87),
    # S005: "pointless" — Negative (all three agree)
    (4, "Negative", 43, 52),
    # S005: "busywork" — Negative
    (4, "Negative", 119, 127),
]


def make_coder_file(
    path: Path,
    coder_name: str,
    annotations: list[tuple[int, str, int, int]],
) -> None:
    """Create a single .ace file with shared sources/codes and coder-specific annotations."""
    if path.exists():
        path.unlink()

    conn = create_project(path, f"Agreement Test — {coder_name}")

    source_ids = []
    for display_id, text in SOURCES:
        sid = add_source(conn, display_id, text, "row")
        source_ids.append(sid)

    code_ids = {}
    for code_name, colour in CODES:
        code_ids[code_name] = add_code(conn, code_name, colour)

    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute(
        "SELECT id FROM coder WHERE name = ?", (coder_name,)
    ).fetchone()["id"]

    for src_idx, code_name, start, end in annotations:
        sid = source_ids[src_idx]
        text = SOURCES[src_idx][1]
        add_annotation(conn, sid, coder_id, code_ids[code_name], start, end, text[start:end])

    checkpoint_and_close(conn)


def main():
    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir = project_root / "tmp"
    output_dir.mkdir(exist_ok=True)

    coders = [
        ("alice.ace", "Alice", ALICE_ANNOTATIONS),
        ("bob.ace", "Bob", BOB_ANNOTATIONS),
        ("carol.ace", "Carol", CAROL_ANNOTATIONS),
    ]

    for filename, coder_name, annotations in coders:
        path = output_dir / filename
        make_coder_file(path, coder_name, annotations)
        print(f"  {path.name} — {coder_name}, {len(annotations)} annotations")

    print(f"\nFiles in: {output_dir}")
    print(f"\nTo test:")
    print(f"  1. uv run ace")
    print(f"  2. Click 'Check Agreement' on the landing page")
    print(f"  3. Click 'Add File' and select 2 or 3 .ace files from tmp/")
    print(f"  4. Click 'Compute Agreement'")


if __name__ == "__main__":
    main()
