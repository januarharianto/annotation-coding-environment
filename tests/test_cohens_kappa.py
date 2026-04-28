"""Tests for the inline _cohens_kappa implementation."""

from ace.services.agreement_computer import _cohens_kappa


def test_perfect_agreement():
    assert _cohens_kappa([1, 1, 0, 0, 1], [1, 1, 0, 0, 1]) == 1.0


def test_no_agreement():
    # Disagreement worse than chance: raters anti-correlate on mixed inputs.
    k = _cohens_kappa([1, 0, 1, 0], [0, 1, 0, 1])
    assert k is not None
    assert k < 0


def test_partial_agreement():
    k = _cohens_kappa([1, 1, 0, 0, 1, 0], [1, 0, 0, 1, 1, 0])
    assert k is not None
    assert 0 < k < 1


def test_empty_input():
    assert _cohens_kappa([], []) is None


def test_all_same():
    assert _cohens_kappa([1, 1, 1, 1], [1, 1, 1, 1]) == 1.0
