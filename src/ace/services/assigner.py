"""Random assignment service with configurable ICR overlap."""

import sqlite3
from dataclasses import dataclass, field
from random import Random

from ace.models.assignment import add_assignment


@dataclass
class AssignmentPreview:
    total_sources: int = 0
    overlap_sources: int = 0
    unique_sources: int = 0
    per_coder: dict = field(default_factory=dict)  # coder_id -> {unique, overlap, total}


def generate_assignments(
    conn: sqlite3.Connection,
    coder_ids: list[str],
    overlap_pct: float,
    seed: int,
    preview_only: bool = False,
) -> AssignmentPreview:
    """Generate random assignments with configurable ICR overlap.

    Algorithm:
    1. Get all source IDs ordered by sort_order.
    2. Compute n_overlap = round(total * overlap_pct / 100).
    3. Shuffle with Random(seed).
    4. First n_overlap sources -> overlap set (each assigned to exactly 2 random coders).
    5. Remaining -> split equally across coders (round-robin).
    6. If not preview_only: create assignment records, store seed in project.
    7. Return preview with per-coder breakdown.
    """
    # 1. Get all source IDs ordered by sort_order
    rows = conn.execute("SELECT id FROM source ORDER BY sort_order").fetchall()
    all_source_ids = [r["id"] for r in rows]
    total = len(all_source_ids)

    # 2. Compute overlap count
    n_overlap = round(total * overlap_pct / 100)
    n_unique = total - n_overlap

    # 3. Shuffle with deterministic seed
    rng = Random(seed)
    shuffled = list(all_source_ids)
    rng.shuffle(shuffled)

    # 4. Split into overlap and unique sets
    overlap_sources = shuffled[:n_overlap]
    unique_sources = shuffled[n_overlap:]

    # Build assignments: coder_id -> list of (source_id, is_overlap)
    coder_assignments: dict[str, list[tuple[str, bool]]] = {cid: [] for cid in coder_ids}

    # 4. Overlap sources: each assigned to exactly 2 random coders
    for src_id in overlap_sources:
        pair = rng.sample(coder_ids, 2)
        for cid in pair:
            coder_assignments[cid].append((src_id, True))

    # 5. Unique sources: round-robin across coders
    for i, src_id in enumerate(unique_sources):
        cid = coder_ids[i % len(coder_ids)]
        coder_assignments[cid].append((src_id, False))

    # Build preview
    preview = AssignmentPreview(
        total_sources=total,
        overlap_sources=n_overlap,
        unique_sources=n_unique,
    )
    for cid in coder_ids:
        assignments = coder_assignments[cid]
        n_ovlp = sum(1 for _, is_ovlp in assignments if is_ovlp)
        n_uniq = sum(1 for _, is_ovlp in assignments if not is_ovlp)
        preview.per_coder[cid] = {
            "unique": n_uniq,
            "overlap": n_ovlp,
            "total": n_uniq + n_ovlp,
        }

    # 6. If not preview_only: persist assignment records and seed
    if not preview_only:
        for cid, assignments in coder_assignments.items():
            for src_id, _ in assignments:
                add_assignment(conn, src_id, cid)
        conn.execute(
            "UPDATE project SET assignment_seed = ?",
            (str(seed),),
        )
        conn.commit()

    return preview
