"""Tests for agreement data structures."""

from ace.services.agreement_types import (
    AgreementDataset,
    AgreementResult,
    CodeMetrics,
    CoderInfo,
    MatchedAnnotation,
    MatchedCode,
    MatchedSource,
)


def test_matched_source_construction():
    src = MatchedSource(
        content_hash="abc123", display_id="S001", content_text="hello world"
    )
    assert src.content_hash == "abc123"
    assert src.display_id == "S001"
    assert src.content_text == "hello world"


def test_agreement_dataset_construction():
    ds = AgreementDataset(sources=[], coders=[], codes=[], annotations=[], warnings=[])
    assert ds.sources == []
    assert ds.warnings == []


def test_code_metrics_defaults():
    m = CodeMetrics(percent_agreement=0.85, n_positions=100)
    assert m.percent_agreement == 0.85
    assert m.cohens_kappa is None
    assert m.krippendorffs_alpha is None
    assert m.fleiss_kappa is None
    assert m.congers_kappa is None
    assert m.gwets_ac1 is None
    assert m.brennan_prediger is None


def test_agreement_result_construction():
    metrics = CodeMetrics(percent_agreement=0.9, n_positions=50)
    result = AgreementResult(
        overall=metrics,
        per_code={"Positive": metrics},
        per_source={"S001": metrics},
        pairwise={("c1", "c2"): 0.85},
        n_coders=2,
        n_sources=1,
        n_codes=1,
    )
    assert result.n_coders == 2
    assert result.pairwise[("c1", "c2")] == 0.85
