"""End-to-end tests: AgreementLoader -> AgreementComputer."""

from pathlib import Path

from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.source import add_source
from ace.services.agreement_computer import compute_agreement
from ace.services.agreement_loader import AgreementLoader


def _make_coder_file(
    path: Path,
    coder_name: str,
    sources: list[tuple[str, str]],
    code_name: str,
    annotations: list[tuple[int, int, int, int]],
) -> Path:
    """Create an .ace file.

    sources: list of (display_id, text)
    annotations: list of (source_index, code_index_unused, start, end)
    """
    conn = create_project(path, f"Project {coder_name}")

    source_ids = []
    for display_id, text in sources:
        sid = add_source(conn, display_id, text, "row")
        source_ids.append(sid)

    code_id = add_code(conn, code_name, "#4CAF50")

    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute(
        "SELECT id FROM coder WHERE name = ?", (coder_name,)
    ).fetchone()["id"]

    for src_idx, _, start, end in annotations:
        sid = source_ids[src_idx]
        text = sources[src_idx][1]
        add_annotation(conn, sid, coder_id, code_id, start, end, text[start:end])

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
    return path


def test_e2e_two_coders_perfect_agreement(tmp_path):
    sources = [("S001", "I enjoyed the group work but lectures were too fast")]
    _make_coder_file(
        tmp_path / "alice.ace", "Alice", sources, "Positive",
        [(0, 0, 2, 28)],
    )
    _make_coder_file(
        tmp_path / "bob.ace", "Bob", sources, "Positive",
        [(0, 0, 2, 28)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    ds = loader.build_dataset()
    result = compute_agreement(ds)

    assert result.n_coders == 2
    assert result.n_sources == 1
    assert result.overall.percent_agreement > 0.99
    assert result.overall.cohens_kappa is not None
    assert result.overall.cohens_kappa > 0.9
    assert result.overall.krippendorffs_alpha is not None


def test_e2e_three_coders(tmp_path):
    sources = [("S001", "I enjoyed the group work but lectures were too fast")]
    _make_coder_file(
        tmp_path / "alice.ace", "Alice", sources, "Positive",
        [(0, 0, 2, 28)],
    )
    _make_coder_file(
        tmp_path / "bob.ace", "Bob", sources, "Positive",
        [(0, 0, 2, 28)],
    )
    _make_coder_file(
        tmp_path / "carol.ace", "Carol", sources, "Positive",
        [(0, 0, 2, 28)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")
    loader.add_file(tmp_path / "carol.ace")

    ds = loader.build_dataset()
    result = compute_agreement(ds)

    assert result.n_coders == 3
    # With perfect agreement on a single binary category, Fleiss' kappa can be
    # undefined (NaN -> None) due to zero variance.  Accept either a high value
    # or None in that edge case, and verify via Gwet AC1 instead.
    assert result.overall.fleiss_kappa is None or result.overall.fleiss_kappa > 0.9
    assert result.overall.gwets_ac1 is not None
    assert result.overall.gwets_ac1 > 0.9
    assert len(result.pairwise) == 3  # 3 pairs for 3 coders


def test_e2e_multiple_sources(tmp_path):
    sources = [
        ("S001", "I enjoyed the group work sessions."),
        ("S002", "The lectures were too fast-paced."),
    ]
    _make_coder_file(
        tmp_path / "alice.ace", "Alice", sources, "Positive",
        [(0, 0, 2, 9), (1, 0, 4, 12)],
    )
    _make_coder_file(
        tmp_path / "bob.ace", "Bob", sources, "Positive",
        [(0, 0, 2, 9), (1, 0, 4, 15)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    ds = loader.build_dataset()
    result = compute_agreement(ds)

    assert result.n_sources == 2
    assert len(result.per_source) == 2
