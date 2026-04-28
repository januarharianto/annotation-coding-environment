"""Tests for agreement_computer: pooled overall and n_sources."""

from ace.services.agreement_computer import compute_agreement
from ace.services.agreement_types import (
    AgreementDataset,
    CoderInfo,
    CodeMetrics,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)


def _make_dataset(sources, coders, codes, annotations):
    return AgreementDataset(
        sources=sources,
        coders=coders,
        codes=codes,
        annotations=annotations,
        warnings=[],
    )


def test_pooled_overall_kappa_differs_from_macro_average():
    """Pooled overall kappa is computed on the combined vector, not averaged.

    With two codes that have opposite agreement patterns (one near-perfect,
    one near-zero), the pooled kappa (computed on the combined vector) differs
    from the macro-average kappa (arithmetic mean of per-code kappas).

    This test proves the overall uses `_compute_metrics()` on pooled vectors
    rather than `_macro_average()` by checking that overall.cohens_kappa does
    not equal the arithmetic mean of the per-code kappas.
    """
    # Single source with two non-overlapping annotation regions.
    # Code A: positions 0-9 (10 chars), near-perfect: c1=1111111111, c2=1111111110
    # Code B: positions 10-13 (4 chars), zero agreement: c1=1100, c2=0011
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="x" * 14)]
    coders = [CoderInfo(id="c1", label="C1", source_file="a.ace"),
              CoderInfo(id="c2", label="C2", source_file="b.ace")]
    codes = [MatchedCode(name="A", present_in={"c1", "c2"}),
             MatchedCode(name="B", present_in={"c1", "c2"})]

    annotations = [
        # code A: c1 covers 0-9, c2 covers 0-8 (misses position 9)
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A",
                          start_offset=0, end_offset=10),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A",
                          start_offset=0, end_offset=9),
        # code B: c1 covers 10-11, c2 covers 12-13 (completely non-overlapping)
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="B",
                          start_offset=10, end_offset=12),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="B",
                          start_offset=12, end_offset=14),
    ]

    dataset = _make_dataset(sources, coders, codes, annotations)
    result = compute_agreement(dataset)

    kappa_a = result.per_code["A"].cohens_kappa
    kappa_b = result.per_code["B"].cohens_kappa
    kappa_overall = result.overall.cohens_kappa

    assert kappa_a is not None
    assert kappa_b is not None
    assert kappa_overall is not None

    macro_kappa = (kappa_a + kappa_b) / 2

    # Pooled computation on combined vectors must differ from macro-average
    assert abs(kappa_overall - macro_kappa) > 1e-9, (
        f"Expected pooled kappa ({kappa_overall:.6f}) != macro kappa ({macro_kappa:.6f}). "
        f"kappa_a={kappa_a:.4f}, kappa_b={kappa_b:.4f}"
    )


def test_overall_n_sources_equals_dataset_sources():
    """overall.n_sources equals the number of sources in the dataset."""
    sources = [
        MatchedSource(content_hash="h1", display_id="S1", content_text="hello world"),
        MatchedSource(content_hash="h2", display_id="S2", content_text="foo bar baz"),
    ]
    coders = [CoderInfo(id="c1", label="C1", source_file="a.ace"),
              CoderInfo(id="c2", label="C2", source_file="b.ace")]
    codes = [MatchedCode(name="X", present_in={"c1", "c2"})]
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="X",
                          start_offset=0, end_offset=5),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="X",
                          start_offset=0, end_offset=5),
        MatchedAnnotation(source_hash="h2", coder_id="c1", code_name="X",
                          start_offset=0, end_offset=3),
        MatchedAnnotation(source_hash="h2", coder_id="c2", code_name="X",
                          start_offset=0, end_offset=3),
    ]
    dataset = _make_dataset(sources, coders, codes, annotations)
    result = compute_agreement(dataset)
    assert result.overall.n_sources == 2


def test_per_code_n_sources_counts_distinct_sources():
    """per_code n_sources counts the distinct sources a code appears in."""
    sources = [
        MatchedSource(content_hash="h1", display_id="S1", content_text="hello world"),
        MatchedSource(content_hash="h2", display_id="S2", content_text="foo bar baz"),
    ]
    coders = [CoderInfo(id="c1", label="C1", source_file="a.ace"),
              CoderInfo(id="c2", label="C2", source_file="b.ace")]
    codes = [MatchedCode(name="A", present_in={"c1", "c2"}),
             MatchedCode(name="B", present_in={"c1"})]
    annotations = [
        # code A appears in both sources
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A",
                          start_offset=0, end_offset=5),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A",
                          start_offset=0, end_offset=5),
        MatchedAnnotation(source_hash="h2", coder_id="c1", code_name="A",
                          start_offset=0, end_offset=3),
        MatchedAnnotation(source_hash="h2", coder_id="c2", code_name="A",
                          start_offset=0, end_offset=3),
        # code B appears in source 1 only
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="B",
                          start_offset=6, end_offset=11),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="B",
                          start_offset=6, end_offset=11),
    ]
    dataset = _make_dataset(sources, coders, codes, annotations)
    result = compute_agreement(dataset)
    assert result.per_code["A"].n_sources == 2
    assert result.per_code["B"].n_sources == 1


def test_empty_dataset_returns_zero_n_sources():
    """Empty dataset returns overall with n_sources=0."""
    dataset = _make_dataset([], [], [], [])
    result = compute_agreement(dataset)
    assert result.overall.n_sources == 0


def test_pooled_overall_single_code_matches_per_code():
    """With a single code, pooled overall should match the per-code metrics."""
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="hello")]
    coders = [CoderInfo(id="c1", label="C1", source_file="a.ace"),
              CoderInfo(id="c2", label="C2", source_file="b.ace")]
    codes = [MatchedCode(name="A", present_in={"c1", "c2"})]
    annotations = [
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A",
                          start_offset=0, end_offset=5),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A",
                          start_offset=0, end_offset=5),
    ]
    dataset = _make_dataset(sources, coders, codes, annotations)
    result = compute_agreement(dataset)
    assert result.overall.percent_agreement == result.per_code["A"].percent_agreement
    assert result.overall.n_positions == result.per_code["A"].n_positions


def test_pairwise_returns_full_code_metrics_for_3_coders():
    """Pairwise produces full CodeMetrics (%, alpha, kappa) for each pair.

    With 3 coders there are 3 pairs. Each pair has 2 coders so Cohen's kappa
    is applicable. Verify all three fields are populated and all 3 pairs exist.
    """
    sources = [MatchedSource(content_hash="h1", display_id="S1", content_text="x" * 20)]
    coders = [
        CoderInfo(id="c1", label="C1", source_file="a.ace"),
        CoderInfo(id="c2", label="C2", source_file="b.ace"),
        CoderInfo(id="c3", label="C3", source_file="c.ace"),
    ]
    codes = [MatchedCode(name="A", present_in={"c1", "c2", "c3"})]
    annotations = [
        # c1 and c2 agree on positions 0-9; c3 agrees only on 0-4
        MatchedAnnotation(source_hash="h1", coder_id="c1", code_name="A",
                          start_offset=0, end_offset=10),
        MatchedAnnotation(source_hash="h1", coder_id="c2", code_name="A",
                          start_offset=0, end_offset=10),
        MatchedAnnotation(source_hash="h1", coder_id="c3", code_name="A",
                          start_offset=0, end_offset=5),
    ]
    dataset = _make_dataset(sources, coders, codes, annotations)
    result = compute_agreement(dataset)

    assert len(result.pairwise) == 3  # 3 pairs for 3 coders

    for pair_key, metrics in result.pairwise.items():
        assert isinstance(metrics, CodeMetrics), f"Expected CodeMetrics for pair {pair_key}"
        assert metrics.percent_agreement is not None
        assert metrics.krippendorffs_alpha is not None
        assert metrics.cohens_kappa is not None, (
            f"cohens_kappa should be set for 2-coder pair {pair_key}"
        )

    # c1/c2 have perfect agreement — their kappa should be highest
    metrics_12 = result.pairwise.get(("c1", "c2"))
    assert metrics_12 is not None
    assert metrics_12.cohens_kappa > 0.9
    assert metrics_12.percent_agreement > 0.9
