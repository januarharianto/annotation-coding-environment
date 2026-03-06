"""Tests for inter-coder reliability (ICR) computation service."""

from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.coder import add_coder
from ace.models.assignment import add_assignment
from ace.models.annotation import add_annotation
from ace.services.icr import compute_icr, ICRResult


def _setup_icr_project(tmp_db):
    """Create project with 1 source, 2 codes, 2 coders, both assigned."""
    conn = create_project(tmp_db, "ICR Test")
    source_id = add_source(
        conn,
        "S001",
        "I enjoyed the group work but lectures were too fast",
        "row",
    )
    code_pos_id = add_code(conn, "Positive", "#4CAF50")
    code_neg_id = add_code(conn, "Negative", "#F44336")
    alice_id = add_coder(conn, "Alice")
    bob_id = add_coder(conn, "Bob")
    add_assignment(conn, source_id, alice_id)
    add_assignment(conn, source_id, bob_id)
    return conn, source_id, code_pos_id, code_neg_id, alice_id, bob_id


def test_perfect_agreement(tmp_db):
    conn, source_id, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)

    # Both coders annotate same spans with same codes
    add_annotation(conn, source_id, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, source_id, bob, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, source_id, alice, code_neg, 33, 51, "lectures were too fast")
    add_annotation(conn, source_id, bob, code_neg, 33, 51, "lectures were too fast")

    result = compute_icr(conn)
    assert isinstance(result, ICRResult)
    assert result.overall_kappa > 0.9
    assert result.overlap_sources == 1
    conn.close()


def test_no_agreement(tmp_db):
    conn, source_id, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)

    # Same span, different codes — complete disagreement
    add_annotation(conn, source_id, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, source_id, bob, code_neg, 2, 28, "enjoyed the group work")

    result = compute_icr(conn)
    assert result.overall_kappa < 0.5
    conn.close()


def test_per_code_results(tmp_db):
    conn, source_id, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)

    # Both agree on Positive
    add_annotation(conn, source_id, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, source_id, bob, code_pos, 2, 28, "enjoyed the group work")

    result = compute_icr(conn)
    assert "Positive" in result.per_code
    assert "Negative" in result.per_code
    assert result.per_code["Positive"]["n_positions"] > 0
    conn.close()


def test_multi_code_spans(tmp_db):
    conn, source_id, code_pos, code_neg, alice, bob = _setup_icr_project(tmp_db)

    # Alice applies BOTH Positive AND Negative to chars 2-28
    # Bob applies only Positive to chars 2-28
    add_annotation(conn, source_id, alice, code_pos, 2, 28, "enjoyed the group work")
    add_annotation(conn, source_id, alice, code_neg, 2, 28, "enjoyed the group work")
    add_annotation(conn, source_id, bob, code_pos, 2, 28, "enjoyed the group work")

    result = compute_icr(conn)
    # Positive: both agree on it — high kappa
    # Negative: Alice says yes, Bob says no — lower kappa
    pos_kappa = result.per_code["Positive"]["kappa"]
    neg_kappa = result.per_code["Negative"]["kappa"]
    assert pos_kappa is not None
    assert neg_kappa is not None
    assert pos_kappa > neg_kappa
    conn.close()
